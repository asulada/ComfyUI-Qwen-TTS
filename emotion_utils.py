"""Emotion presets, inline markup parsing and time-stretching helpers.

Qwen3-TTS itself has no ``emotion`` / ``steer_weight`` / ``rate`` knobs: the
only conditioning channel is the natural-language ``instruct`` prompt.  This
module therefore *simulates* those controls on top of the existing API:

* emotion presets + steer weight -> a calibrated ``instruct`` sentence
* inline markup (``[sad]``, ``[pause:800ms]``, ``[rate:1.2]``) -> a list of
  segments, each with its own instruction / speed / trailing silence
* ``[rate:x]`` and the node-level speed -> pitch-preserving time stretching

Nothing here imports torch, so the parsing helpers stay unit-testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Emotion presets
# ---------------------------------------------------------------------------

# Each value is a natural-language instruction in the wording Qwen3-TTS is
# known to follow (emotion + prosody + pace + pause hints).
EMOTION_PRESETS: Dict[str, str] = {
    "none": "",
    "happy": "轻快愉悦，语气明亮上扬，带着笑意，语速偏快",
    "sad": "低沉悲伤，语气沉重，尾音下坠并拖长，语速缓慢，句间有明显停顿",
    "angry": "愤怒，音量偏大，语气强硬急促，咬字用力",
    "whisper": "耳语气声，音量很低，贴近麦克风小声说话，气息感强",
    "weak": "虚弱无力，气息不稳，音量偏小，语速缓慢，略带喘息",
    "tender": "温柔深情，声音柔和，语速轻柔偏慢，句尾自然延长",
    "thoughtful": "沉思般的自言自语，语速缓慢，语调平缓，句间有思考的停顿",
    "excited": "兴奋激动，音调偏高，语速快，情绪饱满",
    "dramatic": "戏剧化演绎，情绪起伏强烈，重音夸张，节奏张弛有度",
    "news": "新闻播报，字正腔圆，语速平稳均匀，客观冷静",
    "calm": "平静从容，语调平稳，语速适中偏慢",
    "fearful": "恐惧不安，声音发颤，语速忽快忽慢，气息紧张",
    "gentle": "温和亲切，声音轻柔，语速平缓",
    "serious": "严肃郑重，语调沉稳，语速偏慢，重音清晰",
}

# English spellings / Chinese aliases accepted in inline tags.
EMOTION_ALIASES: Dict[str, str] = {key: key for key in EMOTION_PRESETS}
EMOTION_ALIASES.update(
    {
        "neutral": "none",
        "normal": "none",
        "joy": "happy",
        "sadness": "sad",
        "anger": "angry",
        "whispering": "whisper",
        "breathy": "whisper",
        "tired": "weak",
        "soft": "tender",
        "affectionate": "tender",
        "pensive": "thoughtful",
        "reflective": "thoughtful",
        "excitement": "excited",
        "theatrical": "dramatic",
        "newsreader": "news",
        "fear": "fearful",
        "worried": "fearful",
        "warm": "gentle",
        "stern": "serious",
        # Chinese aliases
        "中性": "none",
        "正常": "none",
        "开心": "happy",
        "快乐": "happy",
        "高兴": "happy",
        "悲伤": "sad",
        "难过": "sad",
        "愤怒": "angry",
        "生气": "angry",
        "低语": "whisper",
        "耳语": "whisper",
        "气声": "whisper",
        "虚弱": "weak",
        "无力": "weak",
        "深情": "tender",
        "温柔": "gentle",
        "沉思": "thoughtful",
        "思考": "thoughtful",
        "兴奋": "excited",
        "激动": "excited",
        "戏剧": "dramatic",
        "新闻": "news",
        "平静": "calm",
        "恐惧": "fearful",
        "害怕": "fearful",
        "严肃": "serious",
    }
)

# Dropdown choices, "none" first so it is the default.
EMOTION_CHOICES: List[str] = ["none"] + [k for k in EMOTION_PRESETS if k != "none"]


def normalize_emotion(name: Optional[str]) -> Optional[str]:
    """Resolve a preset name / alias to a canonical preset key.

    Returns ``None`` when the name is unknown so callers can keep the original
    bracket text instead of silently swallowing it.
    """
    if name is None:
        return None
    key = str(name).strip().lower()
    if not key:
        return None
    return EMOTION_ALIASES.get(key)


def _steer_clause(steer_weight: float) -> str:
    """Map a 0..2 intensity dial onto a leading clause.

    A leading clause works for every preset regardless of its wording, unlike
    a bare adverb ("非常" + "新闻播报" reads badly).
    """
    try:
        weight = float(steer_weight)
    except (TypeError, ValueError):
        return ""
    weight = max(0.0, min(2.0, weight))

    if weight < 0.5:
        return "情绪只是轻微表露，"
    if weight < 0.85:
        return "情绪稍有流露，"
    if weight <= 1.2:
        return ""
    if weight < 1.6:
        return "情绪非常强烈，"
    return "情绪极其强烈，"


def build_emotion_instruct(
    preset: str = "none",
    steer_weight: float = 1.0,
    extra_instruct: str = "",
) -> str:
    """Compose the ``instruct`` string for one segment.

    ``preset`` is a canonical key or any alias; unknown values are treated as
    "none".  ``extra_instruct`` is appended after the preset so user text wins
    on the details it mentions.
    """
    key = normalize_emotion(preset) or "none"
    base = EMOTION_PRESETS.get(key, "").strip()
    extra = (extra_instruct or "").strip()

    if not base:
        return extra

    text = f"{_steer_clause(steer_weight)}{base}"
    if extra:
        text = f"{text}，{extra}"
    return text


# ---------------------------------------------------------------------------
# Inline markup
# ---------------------------------------------------------------------------


@dataclass
class RichSegment:
    """One contiguous piece of text with its own performance settings."""

    text: str
    emotion: Optional[str] = None
    rate: Optional[float] = None
    pause_after: float = 0.0
    leading_pause: float = 0.0


# [sad] | [emotion:sad] | [pause:800ms] | [break=0.5] | [rate:1.2]
_TAG_RE = re.compile(
    r"\[\s*(?:"
    r"(?:(?:emotion|emo)\s*[:=]\s*(?P<emotion>[^\[\]]+?))"
    r"|(?:(?P<pause_kw>pause|break)\s*[:=]\s*(?P<pause_num>[0-9]*\.?[0-9]+)\s*(?P<pause_unit>ms|s)?)"
    r"|(?:(?:rate|speed)\s*[:=]\s*(?P<rate>[0-9]*\.?[0-9]+))"
    r"|(?P<bare>[A-Za-z_\u4e00-\u9fa5][A-Za-z0-9_\u4e00-\u9fa5]*)"
    r")\s*\]",
    re.IGNORECASE,
)

_MAX_PAUSE_SECONDS = 60.0


def _pause_seconds(raw: str, unit: Optional[str]) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0

    unit = (unit or "").lower()
    if unit == "ms":
        value /= 1000.0
    elif not unit and value >= 50:
        # "[pause:800]" -- a bare 800 almost certainly means milliseconds.
        value /= 1000.0

    return max(0.0, min(_MAX_PAUSE_SECONDS, value))


def _expand_linebreaks(text: str, linebreak_pause: float) -> str:
    if linebreak_pause and linebreak_pause > 0:
        return re.sub(r"\n+", f" [pause:{linebreak_pause}s] ", text)
    return re.sub(r"\n+", " ", text)


def parse_rich_text(text: str, linebreak_pause: float = 0.0) -> List[RichSegment]:
    """Split text into segments at markup tags.

    Emotion and rate tags are *sticky*: they keep applying to later text until
    changed, so a single ``[sad]`` can cover a whole paragraph.  Pause tags
    close the current segment and become silence after it; a pause with no text
    before it becomes ``leading_pause`` of the next segment.

    Unknown bracket tags (e.g. ``[laugh]``) are preserved verbatim as text.
    """
    if not text or not text.strip():
        return []

    text = _expand_linebreaks(text, linebreak_pause)

    segments: List[RichSegment] = []
    buf: List[str] = []
    state_emotion: Optional[str] = None
    state_rate: Optional[float] = None
    leading_pause = 0.0

    def flush() -> Optional[RichSegment]:
        nonlocal leading_pause
        chunk = "".join(buf).strip()
        buf.clear()
        if not chunk:
            return None
        segment = RichSegment(
            text=chunk,
            emotion=state_emotion,
            rate=state_rate,
            leading_pause=leading_pause,
        )
        leading_pause = 0.0
        segments.append(segment)
        return segment

    last = 0
    for match in _TAG_RE.finditer(text):
        buf.append(text[last:match.start()])
        last = match.end()

        emotion_name = match.group("emotion")
        if emotion_name is not None:
            key = normalize_emotion(emotion_name)
            if key is None:
                buf.append(match.group(0))
                continue
            flush()
            state_emotion = None if key == "none" else key
            continue

        if match.group("pause_kw") is not None:
            pause = _pause_seconds(match.group("pause_num"), match.group("pause_unit"))
            segment = flush()
            if segment is not None:
                segment.pause_after += pause
            else:
                leading_pause += pause
            continue

        if match.group("rate") is not None:
            flush()
            try:
                state_rate = float(match.group("rate"))
            except ValueError:
                state_rate = None
            continue

        key = normalize_emotion(match.group("bare"))
        if key is None:
            buf.append(match.group(0))
            continue
        flush()
        state_emotion = None if key == "none" else key

    buf.append(text[last:])
    flush()
    return segments


# ---------------------------------------------------------------------------
# Segment plan
# ---------------------------------------------------------------------------


@dataclass
class SegmentPlan:
    """Everything the node needs to render one segment."""

    text: str
    instruct: str
    rate: float
    leading_pause: float
    pause_after: float


def build_segment_plans(
    segments: List[RichSegment],
    global_emotion: str = "none",
    steer_weight: float = 1.0,
    extra_instruct: str = "",
    global_rate: float = 1.0,
    scale_pauses_with_speed: bool = False,
) -> List[SegmentPlan]:
    """Resolve per-segment instruct / rate / silence timings.

    Inline emotion tags override ``global_emotion``; inline ``[rate:x]``
    overrides ``global_rate``.  Silence is *not* stretched by default, so a
    faster delivery does not also eat the dramatic pauses.
    """
    plans: List[SegmentPlan] = []

    for seg in segments:
        if not seg.text.strip():
            continue

        preset = seg.emotion if seg.emotion is not None else global_emotion
        rate = seg.rate if seg.rate is not None else global_rate

        try:
            rate = float(rate)
        except (TypeError, ValueError):
            rate = 1.0
        if rate <= 0:
            rate = 1.0

        leading = max(0.0, seg.leading_pause)
        tail = max(0.0, seg.pause_after)
        if scale_pauses_with_speed:
            leading /= rate
            tail /= rate

        plans.append(
            SegmentPlan(
                text=seg.text,
                instruct=build_emotion_instruct(preset, steer_weight, extra_instruct),
                rate=rate,
                leading_pause=leading,
                pause_after=tail,
            )
        )

    return plans


# ---------------------------------------------------------------------------
# Time stretching
# ---------------------------------------------------------------------------


def time_stretch(
    wav,
    rate: float = 1.0,
    n_fft: int = 1024,
):
    """Pitch-preserving speed change for a mono float waveform.

    ``rate > 1`` speeds the audio up (output gets shorter), matching
    ``librosa.effects.time_stretch``.  A rate of 1.0 returns the input
    untouched so the default path is bit-identical to the original output.
    """
    try:
        rate = float(rate)
    except (TypeError, ValueError):
        rate = 1.0

    if abs(rate - 1.0) < 1e-3:
        return wav

    import librosa
    import numpy as np

    y = np.asarray(wav, dtype=np.float32)
    if y.ndim > 1:
        y = y.mean(axis=0)
    if y.size == 0:
        return y

    try:
        # librosa >= 0.10 forwards **kwargs to stft; a smaller n_fft keeps the
        # time resolution tight, which matters for breathy / whispered speech.
        out = librosa.effects.time_stretch(y=y, rate=rate, n_fft=n_fft)
    except TypeError:
        out = librosa.effects.time_stretch(y, rate=rate)

    return np.asarray(out, dtype=np.float32)
