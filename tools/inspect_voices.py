#!/usr/bin/env python3
"""Report the state of a Qwen3-TTS voice library.

For every voice (stored as ``<stem>.wav`` + ``<stem>.qvp`` + ``<stem>.json``)
this prints whether it can actually be loaded and, more importantly, whether
its clone prompt is ICL or x-vector-only.

Why that matters: ``create_voice_clone_prompt`` drops ``ref_code`` when
``x_vector_only=True``, so such a prompt keeps only the averaged speaker
embedding.  Timbre/age/accent similarity is capped at that point and cannot be
recovered later -- the voice has to be re-created from its reference audio.
See ``qwen_tts/inference/qwen3_tts_model.py:create_voice_clone_prompt``.

Usage (run with ComfyUI's Python, which has torch)::

    python tools/inspect_voices.py --models-dir /path/to/ComfyUI/models
    python tools/inspect_voices.py --dir "D:/voices/audiobook" --dir "D:/voices/game"
    python tools/inspect_voices.py --models-dir ... --verbose

Without ``--dir``/``--models-dir`` the usual ComfyUI layout is inferred from
this file's location (``custom_nodes/<plugin>/tools/``).
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from voice_store import (  # noqa: E402  (path set up above)
    AUDIO_EXTENSIONS,
    VOICE_DIRS_ENV,
    collect_voice_dirs,
    parse_env_dirs,
)


# ---------------------------------------------------------------------------
# Reading .qvp files
# ---------------------------------------------------------------------------

# ``torch.save`` pickles ``VoiceClonePromptItem`` instances by qualified name.
# Loading them normally would import qwen_tts -> transformers -> torch, which is
# slow and unnecessary: the script only needs three attributes.  Registering a
# stand-in class keeps the load cheap and works even when the model package is
# not importable.
_STUB_MODULE = "qwen_tts.inference.qwen3_tts_model"
_STUB_CLASS = "VoiceClonePromptItem"


class _PromptItemStub:
    """Placeholder for the unpickled ``VoiceClonePromptItem``."""

    ref_code: Any = None
    ref_spk_embedding: Any = None
    x_vector_only_mode: bool = False
    icl_mode: bool = False
    ref_text: Optional[str] = None


def _install_pickle_stub() -> None:
    import types

    for name in ("qwen_tts", "qwen_tts.inference"):
        if name not in sys.modules:
            module = types.ModuleType(name)
            module.__path__ = []  # type: ignore[attr-defined]
            sys.modules[name] = module
    if _STUB_MODULE not in sys.modules:
        module = types.ModuleType(_STUB_MODULE)
        setattr(module, _STUB_CLASS, _PromptItemStub)
        sys.modules[_STUB_MODULE] = module


def _load_qvp(path: str) -> Tuple[Optional[List[Any]], str]:
    """Return ``(prompt_items, error)``; items is None when unreadable."""
    try:
        import torch  # noqa: F401
    except ImportError:
        return None, "torch not installed in this interpreter"

    _install_pickle_stub()

    import torch

    try:
        try:
            data = torch.load(path, map_location="cpu", weights_only=False)
        except TypeError:  # torch < 2.0 has no weights_only
            data = torch.load(path, map_location="cpu")
    except Exception as exc:  # corrupt file, unknown class, ...
        # A real import may succeed where the stub failed (e.g. unusual pickles).
        try:
            sys.modules.pop(_STUB_MODULE, None)
            import qwen_tts  # noqa: F401
            data = torch.load(path, map_location="cpu", weights_only=False)
        except Exception:
            return None, f"{type(exc).__name__}: {exc}"

    # Both the packaged dict form and the raw list form appear in the wild.
    if isinstance(data, dict):
        items = data.get("prompt", data.get("prompt_items"))
        if items is None:
            return None, "dict without a 'prompt' entry"
    else:
        items = data

    if not isinstance(items, (list, tuple)):
        items = [items]

    if not items:
        return None, "empty prompt list"

    # Guard against payloads that unpickle fine but are not clone prompts at
    # all: without these attributes the model cannot dispatch on the mode.
    for item in items:
        if not hasattr(item, "icl_mode") and not hasattr(item, "x_vector_only_mode"):
            return None, f"{type(item).__name__} is not a VoiceClonePromptItem"
    return list(items), ""


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


@dataclass
class VoiceReport:
    rel_path: str
    directory: str
    stem: str
    has_wav: bool
    has_qvp: bool
    has_json: bool
    wav_ext: str = ""
    ref_text: str = ""
    duration: Optional[float] = None   # seconds of the reference audio
    sample_rate: Optional[int] = None
    duration_error: str = ""
    mode: str = "unknown"          # "icl" | "xvec" | "unknown" | "unreadable"
    item_count: int = 0
    notes: List[str] = field(default_factory=list)

    @property
    def ref_text_chars(self) -> int:
        return len(self.ref_text.strip())

    @property
    def chars_per_second(self) -> Optional[float]:
        """Rough speech-density proxy: too high means text and audio disagree."""
        if not self.duration or self.duration <= 0 or not self.ref_text_chars:
            return None
        return self.ref_text_chars / self.duration

    @property
    def loadable(self) -> bool:
        """LoadSpeaker resolves the voice from its audio file, not the .qvp."""
        return self.has_wav

    @property
    def needs_rebuild(self) -> bool:
        return self.mode == "xvec" or (self.mode == "icl" and self.ref_text_chars == 0)


def _describe_items(items: List[Any]) -> Tuple[str, int, List[str]]:
    """Infer the clone mode from unpickled prompt items."""
    modes = set()
    notes: List[str] = []
    for item in items:
        xvec = bool(getattr(item, "x_vector_only_mode", False))
        icl = bool(getattr(item, "icl_mode", False))
        ref_code = getattr(item, "ref_code", None)
        if xvec and not icl:
            modes.add("xvec")
            if ref_code is not None:
                notes.append("xvec flagged but ref_code present (unexpected)")
        elif icl:
            if ref_code is None:
                modes.add("broken")
                notes.append("icl_mode=True but ref_code is None")
            else:
                modes.add("icl")
        else:
            # Neither flag: the model falls back to the speaker-embedding path.
            modes.add("xvec")
            notes.append("neither icl_mode nor x_vector_only_mode set")

    if not modes:
        return "unknown", len(items), notes
    if "broken" in modes:
        return "broken", len(items), notes
    if modes == {"icl"}:
        return "icl", len(items), notes
    if modes == {"xvec"}:
        return "xvec", len(items), notes
    return "mixed", len(items), notes


def _read_json_ref_text(path: str) -> str:
    import json

    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("ref_text") or "").strip()


def probe_audio_duration(path: str) -> Tuple[Optional[float], Optional[int], str]:
    """Return ``(seconds, sample_rate, error)`` for an audio file.

    Uses the stdlib ``wave`` reader first (WAV only, no dependencies), then
    falls back to ``soundfile`` for mp3/flac/ogg/m4a.  Duration is what makes
    the ref_text column meaningful: a 40-character transcript over 4 seconds
    of audio means text and recording do not match, which breaks ICL.
    """
    ext = os.path.splitext(path)[1].lower()

    if ext == ".wav":
        try:
            import wave

            with wave.open(path, "rb") as handle:
                frames = handle.getnframes()
                rate = handle.getframerate()
                if rate > 0:
                    return frames / float(rate), rate, ""
                return None, None, "wave header reports sample rate 0"
        except wave.Error as exc:
            wav_error = f"wave: {exc}"
        except Exception as exc:
            wav_error = f"{type(exc).__name__}: {exc}"
    else:
        wav_error = ""

    try:
        import soundfile as sf

        info = sf.info(path)
        if info.samplerate > 0:
            return info.frames / float(info.samplerate), info.samplerate, ""
        return None, None, "soundfile reports sample rate 0"
    except ImportError:
        return None, None, wav_error or "install soundfile to probe non-WAV audio"
    except Exception as exc:
        detail = f"soundfile: {type(exc).__name__}: {exc}"
        return None, None, f"{wav_error}; {detail}" if wav_error else detail


def _annotate_reference_quality(report: VoiceReport) -> None:
    """Flag reference audio that is too short or inconsistent with its transcript.

    Thresholds come from the official guidance (5-15 s of clean single-speaker
    audio) plus a speech-density sanity check for Chinese and for space-delimited
    languages.  CJK runs at roughly 3.5-7.5 characters per second; a ratio far
    outside that means ref_text and the recording describe different things,
    which corrupts the ICL prefix instead of helping it.
    """
    if report.duration is None or report.duration <= 0:
        return

    if report.duration < 5.0:
        report.notes.append(
            f"reference audio is only {report.duration:.1f}s (official guidance: 5-15s)"
        )
    elif report.duration > 15.0:
        report.notes.append(
            f"reference audio is {report.duration:.1f}s (longer than the 15s guidance)"
        )

    cps = report.chars_per_second
    if cps is not None and report.mode in ("icl", "none"):
        # CJK text carries far more characters per spoken second than Latin.
        cjk_chars = sum(1 for ch in report.ref_text if "\u4e00" <= ch <= "\u9fff")
        is_cjk = cjk_chars * 2 >= len(report.ref_text.strip())
        low, high = (3.0, 8.5) if is_cjk else (1.5, 4.5)
        if cps < low:
            report.notes.append(
                f"ref_text is sparse for {report.duration:.1f}s "
                f"({cps:.1f} chars/s): transcript may be incomplete"
            )
        elif cps > high:
            report.notes.append(
                f"ref_text is dense for {report.duration:.1f}s "
                f"({cps:.1f} chars/s): transcript may not match the audio"
            )


def scan_directories(directories: List[str], verbose: bool = False) -> List[VoiceReport]:
    """Group every ``.wav`` / ``.qvp`` / ``.json`` sibling set into a report."""
    reports: List[VoiceReport] = []

    for directory in directories:
        if not directory or not os.path.isdir(directory):
            continue

        groups: Dict[str, Dict[str, str]] = {}
        for root, _dirs, files in os.walk(directory):
            for name in files:
                stem, ext = os.path.splitext(name)
                ext = ext.lower()
                if ext in AUDIO_EXTENSIONS:
                    slot = "wav"
                elif ext == ".qvp":
                    slot = "qvp"
                elif ext == ".json":
                    slot = "json"
                else:
                    continue
                key = os.path.join(root, stem)
                groups.setdefault(key, {})[slot] = os.path.join(root, name)

        for key in sorted(groups, key=str.lower):
            group = groups[key]
            root = os.path.dirname(key)
            rel = os.path.relpath(key, directory).replace("\\", "/")
            report = VoiceReport(
                rel_path=rel,
                directory=directory,
                stem=os.path.basename(key),
                has_wav="wav" in group,
                has_qvp="qvp" in group,
                has_json="json" in group,
            )
            if report.has_wav:
                report.wav_ext = os.path.splitext(group["wav"])[1].lower()
                duration, rate, error = probe_audio_duration(group["wav"])
                report.duration = duration
                report.sample_rate = rate
                report.duration_error = error
                if error:
                    report.notes.append(f"duration probe failed: {error}")

            if report.has_json:
                report.ref_text = _read_json_ref_text(group["json"])

            if report.has_qvp:
                items, error = _load_qvp(group["qvp"])
                if items is None:
                    report.mode = "unreadable"
                    report.notes.append(error)
                else:
                    report.mode, report.item_count, notes = _describe_items(items)
                    report.notes.extend(notes)
                    if not report.ref_text:
                        for item in items:
                            text = getattr(item, "ref_text", None)
                            if text and str(text).strip():
                                report.ref_text = str(text).strip()
                                break
            else:
                # No cached prompt: LoadSpeaker returns None and the downstream
                # clone node re-encodes from the wav on every run.
                report.mode = "none"

            if not report.has_wav:
                report.notes.append("no audio file: LoadSpeaker cannot resolve this voice")
            if report.has_qvp and not report.has_json:
                report.notes.append("no .json sidecar: ref_text metadata is missing")
            if report.mode == "none" and report.has_wav and not report.has_json:
                report.notes.append("wav without .qvp/.json: encoding happens at load time")

            _annotate_reference_quality(report)

            if verbose and report.notes:
                for note in report.notes:
                    print(f"    note [{rel}]: {note}")

            reports.append(report)

    return reports


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _display_width(text: str) -> int:
    """Terminal column count, counting East Asian wide chars as two."""
    import unicodedata

    return sum(
        2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text
    )


def _fmt(value: str, width: int) -> str:
    # Keep columns aligned without assuming a CJK-aware terminal.
    text = value
    while _display_width(text) > width and len(text) > 1:
        text = text[:-1]
    return text + " " * max(0, width - _display_width(text))


def _verdict_for(report: VoiceReport) -> str:
    """One-line summary of what (if anything) needs fixing."""
    if not report.has_wav:
        return "MISSING AUDIO - unloadable"
    if report.mode == "xvec":
        return "x-vector only - rebuild for likeness"
    if report.mode == "broken":
        return "broken prompt - rebuild"
    if report.mode == "unreadable":
        return "unreadable .qvp - rebuild"
    if report.mode == "icl" and not report.ref_text_chars:
        return "ICL without ref_text - rebuild"
    if report.mode == "none":
        return "no cache - encodes at load (works)"
    if report.mode not in ("icl",):
        return "review"

    # Mode and metadata are fine; the remaining risk is reference quality.
    cps = report.chars_per_second
    if report.duration is not None and report.duration < 4.0:
        return f"VERY SHORT audio ({report.duration:.1f}s) - rebuild"
    if report.duration is not None and report.duration < 5.0:
        return f"short audio ({report.duration:.1f}s) - consider rebuilding"
    if cps is not None:
        cjk_chars = sum(1 for ch in report.ref_text if "\u4e00" <= ch <= "\u9fff")
        is_cjk = cjk_chars * 2 >= len(report.ref_text.strip())
        low, high = (3.0, 8.5) if is_cjk else (1.5, 4.5)
        if cps > high:
            return f"transcript likely mismatched ({cps:.1f} c/s) - verify"
        if cps < low:
            return f"sparse transcript ({cps:.1f} c/s) - ref_text likely incomplete"
    return "ok"


def print_report(reports: List[VoiceReport], directories: List[str]) -> int:
    print("Scanned directories:")
    for directory in directories:
        print(f"  - {directory}")
    print()

    if not reports:
        print("No voices found.")
        return 0

    header = (
        _fmt("voice", 32)
        + _fmt("wav", 5)
        + _fmt("qvp", 5)
        + _fmt("json", 6)
        + _fmt("mode", 11)
        + _fmt("secs", 7)
        + _fmt("chars", 7)
        + _fmt("c/s", 7)
        + "verdict"
    )
    print(header)
    print("-" * len(header))

    problems = 0
    for report in reports:
        verdict = _verdict_for(report)
        if verdict != "ok" and not verdict.startswith("no cache"):
            problems += 1

        secs = f"{report.duration:.1f}" if report.duration else "-"
        cps = report.chars_per_second
        cps_text = f"{cps:.1f}" if cps is not None else "-"

        print(
            _fmt(report.rel_path, 32)
            + _fmt("yes" if report.has_wav else "NO", 5)
            + _fmt("yes" if report.has_qvp else "-", 5)
            + _fmt("yes" if report.has_json else "-", 6)
            + _fmt(report.mode, 11)
            + _fmt(secs, 7)
            + _fmt(str(report.ref_text_chars), 7)
            + _fmt(cps_text, 7)
            + verdict
        )

    print()
    icl = sum(1 for r in reports if _verdict_for(r) == "ok")
    xvec = sum(1 for r in reports if r.mode == "xvec")
    no_audio = sum(1 for r in reports if not r.has_wav)
    short = sum(
        1 for r in reports
        if r.duration is not None and 0 < r.duration < 5.0 and r.mode in ("icl", "none")
    )
    print(
        f"Total {len(reports)}: {icl} usable ICL, {xvec} x-vector-only, "
        f"{no_audio} without audio, {short} with short reference audio, "
        f"{problems} needing attention."
    )
    if xvec or no_audio:
        print()
        print("Rebuild recipe for a flagged voice:")
        print("  1. VoiceClonePromptNode: connect the original reference audio,")
        print("     leave x_vector_only OFF, fill ref_text with the exact transcript.")
        print("  2. SaveVoice: connect both voice_clone_prompt AND audio, then")
        print("     overwrite the old files.")
    return len(reports)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _infer_models_dir() -> Optional[str]:
    """From ``custom_nodes/<plugin>/tools/`` walk up to ``models/``."""
    candidate = os.path.abspath(os.path.join(REPO_ROOT, os.pardir, os.pardir, "models"))
    return candidate if os.path.isdir(candidate) else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect a Qwen3-TTS voice library: loadability and clone mode.",
    )
    parser.add_argument(
        "--models-dir",
        default=None,
        help="ComfyUI models directory (default: inferred from this file's location)",
    )
    parser.add_argument(
        "--dir",
        action="append",
        default=None,
        dest="extra_dirs",
        help="Scan this directory instead of the ComfyUI layout (repeatable)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print every per-voice note",
    )
    return parser


def resolve_directories(args: argparse.Namespace) -> List[str]:
    if args.extra_dirs:
        return [os.path.abspath(d) for d in args.extra_dirs]

    models_dir = args.models_dir or _infer_models_dir()
    if not models_dir:
        raise SystemExit(
            "Could not infer the ComfyUI models directory. Pass --models-dir or --dir."
        )
    return collect_voice_dirs(models_dir, [], parse_env_dirs(os.environ.get(VOICE_DIRS_ENV, "")))


def main(argv: Optional[List[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    args = build_parser().parse_args(argv)
    directories = resolve_directories(args)
    existing = [d for d in directories if os.path.isdir(d)]
    if not existing:
        print("No voice directory exists yet:")
        for directory in directories:
            print(f"  - {directory}")
        return 0

    reports = scan_directories(existing, verbose=args.verbose)
    print_report(reports, existing)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
