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


def list_voice_files(directories: Iterable[str]) -> List[Tuple[str, str]]:
    """Return ``(display_name, absolute_path)`` for every audio file found.

    ``display_name`` is ``"<label>/<filename>"``.  Labels are de-duplicated so
    two directories with the same base name stay distinguishable.
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
            names = sorted(os.listdir(path))
        except OSError:
            continue
        for name in names:
            if not name.lower().endswith(AUDIO_EXTENSIONS):
                continue
            full = os.path.join(path, name)
            if not os.path.isfile(full):
                continue
            key = _norm(full)
            if key in seen:
                continue
            seen.add(key)
            entries.append((f"{label}/{name}", full))

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


def resolve_input_path(
    display_or_path: str,
    directories: Iterable[str],
    models_dir: str,
) -> str:
    """Resolve what the Load node was given to a concrete audio file.

    Accepts, in order of precedence:
      1. an absolute path to a file
      2. a bare filename found in one of the scanned directories
      3. a ``"<label>/<filename>"`` display name
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

    if label:
        for path in dirs:
            if dir_label(path, models_dir).lower() != label.lower():
                continue
            candidate = os.path.join(path, name)
            if os.path.isfile(candidate):
                return os.path.abspath(candidate)

    for path in dirs:
        candidate = os.path.join(path, name)
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)

    raise FileNotFoundError(f"Voice file not found: {text}")


def build_filename_choices(entries: Iterable[Tuple[str, str]], empty: bool = False) -> List[str]:
    """Dropdown values; keeps a ``"None"`` entry when nothing was found."""
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
