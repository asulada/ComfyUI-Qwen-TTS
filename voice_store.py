"""Voice directory discovery and path resolution.

The voice library used to live in exactly one place
(``models/qwen-tts/voices``).  These helpers let the Save/Load nodes work with
any number of directories instead:

* the default ``models/qwen-tts/voices``
* every ``qwen-tts`` folder registered in ComfyUI (``extra_model_paths.yaml``)
* extra directories from ``QWEN_TTS_VOICE_DIRS`` (``os.pathsep`` separated)
* a per-node directory typed by the user

Everything here is plain Python: no torch, no ComfyUI imports, so it stays
unit-testable without the ComfyUI runtime.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

VOICES_SUBDIR = "voices"
VOICE_DIRS_ENV = "QWEN_TTS_VOICE_DIRS"

AUDIO_EXTENSIONS = (".wav", ".mp3", ".flac", ".ogg", ".m4a")

# ``.qvp`` is the saved voice-clone prompt (``torch.save`` of the prompt
# items).  It is not playable audio, but it *is* a first-class way to name a
# voice: loading it skips re-encoding the reference audio and reproduces the
# exact timbre that was saved.
PROMPT_EXTENSIONS = (".qvp",)

VOICE_EXTENSIONS = AUDIO_EXTENSIONS + PROMPT_EXTENSIONS

# Display names are "<label>/<filename>"; this label is used for the
# traditional single-directory location.
DEFAULT_LABEL = "voices"


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def parse_env_dirs(raw: Optional[str] = None) -> List[str]:
    """Split the ``QWEN_TTS_VOICE_DIRS`` value into individual paths."""
    if raw is None:
        raw = os.environ.get(VOICE_DIRS_ENV, "")
    return [p.strip() for p in str(raw).split(os.pathsep) if p.strip()]


def _unique_paths(paths: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for path in paths:
        if not path:
            continue
        key = _norm(path)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(os.path.abspath(path))
    return ordered


def collect_voice_dirs(
    models_dir: str,
    registered_qwen_dirs: Iterable[str] = (),
    env_value: Optional[str] = None,
    include_missing: bool = False,
) -> List[str]:
    """Build the ordered list of candidate voice directories.

    The default directory always comes first so existing workflows keep
    resolving to the same files.  ``registered_qwen_dirs`` are the roots from
    ``folder_paths.get_folder_paths("qwen-tts")``; each is probed for a
    ``voices`` child, and the root itself is kept as a fallback so a flat
    ``extra_model_paths.yaml`` layout also works.
    """
    candidates: List[str] = [os.path.join(models_dir, "qwen-tts", VOICES_SUBDIR)]

    for root in registered_qwen_dirs or []:
        if not root:
            continue
        child = os.path.join(root, VOICES_SUBDIR)
        candidates.append(child)
        candidates.append(root)

    candidates.extend(parse_env_dirs(env_value))

    if not include_missing:
        candidates = [p for p in candidates if os.path.isdir(p)]

    return _unique_paths(candidates)


def dir_label(path: str, models_dir: str) -> str:
    """Human-friendly, collision-resistant label for a directory."""
    default = _norm(os.path.join(models_dir, "qwen-tts", VOICES_SUBDIR))
    if _norm(path) == default:
        return DEFAULT_LABEL

    parent = os.path.basename(os.path.dirname(os.path.abspath(path))) or "dir"
    name = os.path.basename(os.path.abspath(path)) or "dir"
    if name.lower() == DEFAULT_LABEL:
        name = parent
    return name


def list_voice_files(
    directories: Iterable[str],
    recursive: bool = True,
    extensions: Tuple[str, ...] = AUDIO_EXTENSIONS,
) -> List[Tuple[str, str]]:
    """Return ``(display_name, absolute_path)`` for every matching file found.

    ``display_name`` is ``"<label>/<relative/path/file.wav>"``.  Sub-directories
    created through SaveVoice's ``subfolder`` are included when ``recursive`` is
    true, so they show up in the dropdown instead of becoming unreachable.

    ``extensions`` defaults to audio, which keeps every existing caller
    unchanged.  Pass ``PROMPT_EXTENSIONS`` (via ``list_prompt_files``) to build
    a dropdown of saved prompts instead.
    """
    dirs = [d for d in directories if d and os.path.isdir(d)]
    if not dirs:
        return []

    # De-duplicate labels by appending an index when needed.
    base_labels: List[str] = []
    for path in dirs:
        name = os.path.basename(os.path.abspath(path)) or "dir"
        parent = os.path.basename(os.path.dirname(os.path.abspath(path))) or ""
        base_labels.append(name)
        if base_labels.count(name) > 1 and parent:
            base_labels[-1] = f"{parent}-{name}"

    entries: List[Tuple[str, str]] = []
    seen = set()
    for path, label in zip(dirs, base_labels):
        try:
            if recursive:
                walker = (
                    (root, files)
                    for root, _dirs, files in os.walk(path)
                )
            else:
                walker = [(path, os.listdir(path))]
        except OSError:
            continue

        for root, names in walker:
            for name in sorted(names):
                if not name.lower().endswith(tuple(extensions)):
                    continue
                full = os.path.join(root, name)
                if not os.path.isfile(full):
                    continue
                key = _norm(full)
                if key in seen:
                    continue
                seen.add(key)
                rel = os.path.relpath(full, path).replace("\\", "/")
                entries.append((f"{label}/{rel}", full))

    entries.sort(key=lambda item: item[0].lower())
    return entries


def list_prompt_files(
    directories: Iterable[str],
    recursive: bool = True,
) -> List[Tuple[str, str]]:
    """``(display_name, absolute_path)`` for every saved prompt (``.qvp``).

    Kept separate from ``list_voice_files`` so the audio dropdown stays exactly
    as it was.  A ``.qvp`` carries the prompt itself, so it is the more precise
    of the two choices; the UI lists it first for that reason.
    """
    return list_voice_files(directories, recursive=recursive, extensions=PROMPT_EXTENSIONS)


def audio_stems_without_prompt(
    audio_entries: Iterable[Tuple[str, str]],
    prompt_entries: Iterable[Tuple[str, str]],
) -> List[Tuple[str, str]]:
    """Audio entries that have no same-stem ``.qvp`` among ``prompt_entries``.

    Both lists are needed because the audio scan only sees audio: it cannot
    know a prompt exists unless the prompt scan is passed in.  Offering both
    ``voices/hero.qvp`` and ``voices/hero.wav`` would make the user guess which
    one wins, when the answer is always the prompt.
    """
    stems_with_prompt = {
        _norm(os.path.splitext(path)[0]) for _display, path in prompt_entries
    }
    if not stems_with_prompt:
        return list(audio_entries)

    return [
        (display, path)
        for display, path in audio_entries
        if _norm(os.path.splitext(path)[0]) not in stems_with_prompt
    ]


def split_display_name(display: str) -> Tuple[Optional[str], str]:
    """Split ``"label/file.wav"`` into ``("label", "file.wav")``.

    A bare filename keeps its historical meaning and yields ``(None, name)``.
    """
    text = (display or "").strip().replace("\\", "/")
    if "/" in text:
        label, name = text.split("/", 1)
        return label, name
    return None, text


def resolve_output_dir(
    user_path: str,
    models_dir: str,
    create: bool = True,
) -> str:
    """Resolve the directory a voice should be saved into.

    An empty value means the default voice directory.  Relative paths are
    resolved against ``models/qwen-tts``; absolute paths are used as-is.  The
    directory is created when ``create`` is true.
    """
    text = (user_path or "").strip().strip('"')

    if not text:
        target = os.path.join(models_dir, "qwen-tts", VOICES_SUBDIR)
    elif os.path.isabs(text) or (len(text) > 1 and text[1] == ":"):
        target = text
    else:
        target = os.path.join(models_dir, "qwen-tts", text)

    target = os.path.abspath(target)
    if create:
        os.makedirs(target, exist_ok=True)
    return target


def relative_voice_path(audio_path: str, directory: str) -> str:
    """Path of a voice file relative to the directory that owns it.

    Used for the ``relative_path`` metadata field so a voice can be found
    again even when two libraries contain the same filename.
    """
    try:
        rel = os.path.relpath(os.path.abspath(audio_path), os.path.abspath(directory))
    except ValueError:
        return ""
    return rel.replace("\\", "/")


def read_voice_metadata(audio_path: str) -> Dict[str, str]:
    """Read the sidecar JSON next to an audio file; empty dict when absent."""
    import json

    path = sibling_metadata_paths(audio_path)["json"]
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def resolve_input_path(
    display_or_path: str,
    directories: Iterable[str],
    models_dir: str,
) -> str:
    """Resolve what the Load node was given to a concrete audio file.

    Accepts:
      1. an absolute path to a file
      2. ``"<label>/<relative/path/file.wav>"`` — the dropdown form, where the
         label is a scanned directory and the rest may include sub-directories
      3. a path relative to a scanned directory (e.g. ``"sub/file.wav"``)

    Bare filenames are handled by ``resolve_bare_name`` and must live in the
    default directory, so no cross-library guessing happens here.
    """
    text = (display_or_path or "").strip().strip('"')
    if not text:
        raise ValueError("No voice file specified")

    if os.path.isabs(text) or (len(text) > 1 and text[1] == ":"):
        if os.path.isfile(text):
            return os.path.abspath(text)
        raise FileNotFoundError(f"Voice file not found: {text}")

    dirs = [d for d in directories if d and os.path.isdir(d)]
    label, name = split_display_name(text)

    # 1. "<label>/<path>" — match the label, then join the remaining path.
    if label:
        for path in dirs:
            if dir_label(path, models_dir).lower() != label.lower():
                continue
            candidate = os.path.join(path, *[p for p in name.split("/") if p not in ("", ".")])
            if os.path.isfile(candidate):
                return os.path.abspath(candidate)

        # A label can also be a sub-directory name; try it as a plain relative
        # path before giving up (handles "verify/batch1/voice.wav").
        for path in dirs:
            candidate = os.path.join(path, *[p for p in text.split("/") if p not in ("", ".")])
            if os.path.isfile(candidate):
                return os.path.abspath(candidate)

    for path in dirs:
        candidate = os.path.join(path, name)
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)

    raise FileNotFoundError(f"Voice file not found: {text}")


def find_bare_matches(
    bare_name: str,
    directories: Iterable[str],
) -> List[str]:
    """Absolute paths of every scanned directory entry named ``bare_name``."""
    wanted = (bare_name or "").strip().lower()
    if not wanted:
        return []

    found: List[str] = []
    seen = set()
    for path in directories:
        if not path or not os.path.isdir(path):
            continue
        try:
            names = os.listdir(path)
        except OSError:
            continue
        for name in names:
            if name.lower() != wanted:
                continue
            full = os.path.join(path, name)
            if not os.path.isfile(full):
                continue
            key = _norm(full)
            if key in seen:
                continue
            seen.add(key)
            found.append(os.path.abspath(full))
    return found


def resolve_bare_name(
    bare_name: str,
    directories: Iterable[str],
) -> str:
    """Resolve a bare filename against the default voice directory only.

    The dropdown always yields ``"<label>/<file>"``, so a bare name can only
    come from a hand-edited workflow or an explicitly wrong value.  Rather
    than guessing across libraries, it must exist in the first scanned
    directory (the default ``voices/``); everything else is a hard error.
    """
    dirs = [d for d in directories if d and os.path.isdir(d)]
    text = (bare_name or "").strip()
    if not text:
        raise ValueError("No voice file specified")

    if dirs:
        candidate = os.path.join(dirs[0], text)
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)

    others = find_bare_matches(text, dirs[1:])
    if others:
        raise RuntimeError(
            f"'{text}' is not in the default voice directory. It was found elsewhere: "
            + ", ".join(others)
            + ". Select the '<label>/<file>' entry instead."
        )

    raise FileNotFoundError(f"Voice file not found: {text}")


def build_filename_choices(entries: Iterable[Tuple[str, str]], empty: bool = False) -> List[str]:
    """Dropdown values: one ``"<label>/<file>"`` entry per voice.

    No bare-filename aliases are added: every value carries its directory, so
    two libraries holding the same filename stay unambiguous.
    """
    names = [display for display, _ in entries]
    if not names:
        return ["None"] if empty else []
    return names


def sibling_metadata_paths(audio_path: str) -> Dict[str, str]:
    """Matching ``.qvp`` / ``.json`` files that live next to an audio file."""
    stem = os.path.splitext(audio_path)[0]
    return {
        "qvp": stem + ".qvp",
        "json": stem + ".json",
    }


# ---------------------------------------------------------------------------
# Voice sources
#
# A voice can be named three ways, and the order matters:
#
#   "prompt" -> a saved ``.qvp``        (exact, no re-encoding)
#   "audio"  -> a ``.wav``/``.mp3``/...  (needs a prompt build)
#   "stem"   -> a bare name with no extension; resolved against the library
#
# ``.qvp`` wins whenever it is what the user actually pointed at, and an
# audio file next to a ``.qvp`` is *not* silently swapped in: dropping the
# saved prompt would change the timbre the user picked.
# ---------------------------------------------------------------------------

SOURCE_PROMPT = "prompt"
SOURCE_AUDIO = "audio"
SOURCE_STEM = "stem"


@dataclass(frozen=True)
class VoiceSource:
    """What a path input resolved to.

    ``path`` is the absolute file that will be loaded.  ``payload`` is
    ``.qvp`` (the file *is* the prompt), ``audio`` (a waveform that still needs
    ``create_voice_clone_prompt``), or ``stem`` (nothing exists yet — the
    caller must look for ``<stem>.qvp`` / ``<stem>.wav`` itself).
    ``ref_text`` and ``instruct`` come from the sidecar JSON when one exists.
    They are only fallbacks: a ``.qvp`` carries its own copies, and those
    describe what was actually saved.
    """

    path: str
    kind: str
    ref_text: str = ""
    instruct: str = ""

    @property
    def is_prompt(self) -> bool:
        return self.kind == SOURCE_PROMPT

    @property
    def is_audio(self) -> bool:
        return self.kind == SOURCE_AUDIO

    @property
    def has_file(self) -> bool:
        return self.kind in (SOURCE_PROMPT, SOURCE_AUDIO)


def detect_source_kind(path: str) -> str:
    """Classify a voice path by extension.

    Returns ``SOURCE_PROMPT`` for ``.qvp``, ``SOURCE_AUDIO`` for anything in
    ``AUDIO_EXTENSIONS``, and ``SOURCE_STEM`` otherwise (including no
    extension at all).
    """
    ext = os.path.splitext(path or "")[1].lower()
    if ext in PROMPT_EXTENSIONS:
        return SOURCE_PROMPT
    if ext in AUDIO_EXTENSIONS:
        return SOURCE_AUDIO
    return SOURCE_STEM


def describe_source(voice: VoiceSource) -> str:
    """Short human label for logs: ``"prompt <path>"`` / ``"audio <path>"``."""
    if voice.kind == SOURCE_PROMPT:
        return f"saved prompt {voice.path}"
    if voice.kind == SOURCE_AUDIO:
        return f"reference audio {voice.path}"
    return f"voice name {voice.path}"


def _read_sidecar(path: str) -> Tuple[str, str]:
    """``(ref_text, instruct)`` from the sidecar JSON; empty strings if absent."""
    metadata = read_voice_metadata(path)
    ref_text = metadata.get("ref_text", "")
    instruct = metadata.get("instruct", "")
    return (
        ref_text if isinstance(ref_text, str) else "",
        instruct if isinstance(instruct, str) else "",
    )


def _source(path: str) -> "VoiceSource":
    """Build a ``VoiceSource`` for ``path``, filling in sidecar values."""
    ref_text, instruct = _read_sidecar(path)
    return VoiceSource(path, detect_source_kind(path), ref_text, instruct)


def resolve_voice_source(
    path_or_name: str,
    directories: Iterable[str] = (),
    models_dir: str = "",
) -> VoiceSource:
    """Resolve a path input to a concrete ``VoiceSource``.

    Accepted, in this order:

    1. an existing file (absolute, or relative to the current directory) —
       ``.qvp`` -> prompt, audio extension -> audio;
    2. a bare name without an extension (``my_voice``) — ``my_voice.qvp``
       preferred over ``my_voice.wav`` in the scanned directories;
    3. the dropdown form ``"<label>/<file>"`` and plain relative paths,
       matched against ``directories``.

    Raises ``FileNotFoundError`` with the scanned directories listed, so a
    typo points at what was actually searched instead of failing deeper in
    the model with an obscure tokenizer error.
    """
    text = (path_or_name or "").strip().strip('"')
    if not text:
        raise ValueError("No voice file specified")

    # 1. A real file, given absolutely or relative to the process cwd.
    if os.path.isfile(text):
        absolute = os.path.abspath(text)
        return _source(absolute)

    dirs = [d for d in directories if d and os.path.isdir(d)]

    # 2. A bare name: try the library directories with the known extensions.
    kind = detect_source_kind(text)
    if kind == SOURCE_STEM and "/" not in text.replace("\\", "/"):
        for extension in PROMPT_EXTENSIONS + AUDIO_EXTENSIONS:
            candidate = text + extension
            for directory in dirs:
                full = os.path.join(directory, candidate)
                if os.path.isfile(full):
                    full = os.path.abspath(full)
                    return _source(full)
        raise FileNotFoundError(
            f"Voice not found: {text!r}. Looked for {', '.join(PROMPT_EXTENSIONS + AUDIO_EXTENSIONS)}. "
            f"Scanned directories: {', '.join(dirs) or '(none)'}"
        )

    # 3. Dropdown form / relative path against the scanned directories.
    if models_dir:
        try:
            resolved = resolve_input_path(text, dirs, models_dir)
            return _source(resolved)
        except FileNotFoundError:
            pass
    else:
        for directory in dirs:
            candidate = os.path.join(directory, *[p for p in text.replace("\\", "/").split("/") if p not in ("", ".")])
            if os.path.isfile(candidate):
                candidate = os.path.abspath(candidate)
                return _source(candidate)

    raise FileNotFoundError(
        f"Voice not found: {text!r}. Scanned directories: {', '.join(dirs) or '(none)'}"
    )
