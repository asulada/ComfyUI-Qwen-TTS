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
from typing import Dict, Iterable, List, Optional, Tuple

VOICES_SUBDIR = "voices"
VOICE_DIRS_ENV = "QWEN_TTS_VOICE_DIRS"

AUDIO_EXTENSIONS = (".wav", ".mp3", ".flac", ".ogg", ".m4a")

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


def list_voice_files(directories: Iterable[str], recursive: bool = True) -> List[Tuple[str, str]]:
    """Return ``(display_name, absolute_path)`` for every audio file found.

    ``display_name`` is ``"<label>/<relative/path/file.wav>"``.  Sub-directories
    created through SaveVoice's ``subfolder`` are included when ``recursive`` is
    true, so they show up in the dropdown instead of becoming unreachable.
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
                if not name.lower().endswith(AUDIO_EXTENSIONS):
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
