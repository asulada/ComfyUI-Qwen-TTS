import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from emotion_utils import (
    EMOTION_CHOICES,
    build_emotion_instruct,
    build_segment_plans,
    normalize_emotion,
    parse_rich_text,
    time_stretch,
)


class EmotionPresetTests(unittest.TestCase):
    def test_none_preset_returns_extra_instruct_only(self):
        self.assertEqual(build_emotion_instruct("none", 1.0, "温柔一点"), "温柔一点")
        self.assertEqual(build_emotion_instruct("none", 1.0, ""), "")

    def test_preset_is_used_verbatim(self):
        text = build_emotion_instruct("sad", 1.0)
        self.assertIn("悲伤", text)
        self.assertNotIn("情绪", text)

    def test_steer_weight_changes_intensity(self):
        weak = build_emotion_instruct("sad", 0.3)
        strong = build_emotion_instruct("sad", 1.8)
        self.assertTrue(weak.startswith("情绪只是轻微表露"))
        self.assertTrue(strong.startswith("情绪极其强烈"))

    def test_steer_weight_clamped(self):
        self.assertTrue(build_emotion_instruct("sad", -5).startswith("情绪只是轻微表露"))
        self.assertTrue(build_emotion_instruct("sad", 99).startswith("情绪极其强烈"))

    def test_extra_instruct_is_appended(self):
        text = build_emotion_instruct("whisper", 1.0, "靠近麦克风")
        self.assertTrue(text.endswith("靠近麦克风"))

    def test_aliases(self):
        self.assertEqual(normalize_emotion("低语"), "whisper")
        self.assertEqual(normalize_emotion("SAD"), "sad")
        self.assertEqual(normalize_emotion("neutral"), "none")
        self.assertIsNone(normalize_emotion("nonsense"))

    def test_choices_have_no_duplicates(self):
        self.assertEqual(len(EMOTION_CHOICES), len(set(EMOTION_CHOICES)))
        self.assertEqual(EMOTION_CHOICES[0], "none")


class RichTextTests(unittest.TestCase):
    def test_plain_text_single_segment(self):
        segments = parse_rich_text("hello world")
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].text, "hello world")
        self.assertIsNone(segments[0].emotion)

    def test_emotion_is_sticky_across_later_text(self):
        segments = parse_rich_text("[sad]他走了。再也不会回来了。")
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].emotion, "sad")
        self.assertIn("再也不会回来了", segments[0].text)

    def test_emotion_switch_creates_segments(self):
        segments = parse_rich_text("我简直不敢相信！[excited]这真是太好了！")
        self.assertEqual([s.emotion for s in segments], [None, "excited"])
        self.assertEqual(segments[0].text, "我简直不敢相信！")

    def test_emotion_explicit_syntax(self):
        segments = parse_rich_text("[emotion:sad]他走了")
        self.assertEqual(segments[0].emotion, "sad")

    def test_chinese_alias_tag(self):
        segments = parse_rich_text("[低语]别出声")
        self.assertEqual(segments[0].emotion, "whisper")

    def test_pause_tag_attaches_to_previous_segment(self):
        segments = parse_rich_text("[sad]他走了。[pause:800ms]再也不会回来了。")
        self.assertEqual(len(segments), 2)
        self.assertAlmostEqual(segments[0].pause_after, 0.8)
        self.assertEqual(segments[1].emotion, "sad")

    def test_leading_pause_becomes_leading_pause(self):
        segments = parse_rich_text("[pause:500ms]开场")
        self.assertEqual(len(segments), 1)
        self.assertAlmostEqual(segments[0].leading_pause, 0.5)

    def test_bare_large_pause_is_milliseconds(self):
        segments = parse_rich_text("a[pause:800]b")
        self.assertAlmostEqual(segments[0].pause_after, 0.8)

    def test_break_tag_compat(self):
        segments = parse_rich_text("[break=1.5]Hello")
        self.assertAlmostEqual(segments[0].leading_pause, 1.5)

    def test_rate_tag_is_sticky(self):
        segments = parse_rich_text("[rate:1.2]快一点[rate:0.8]慢一点")
        self.assertEqual([s.rate for s in segments], [1.2, 0.8])

    def test_none_emotion_clears_state(self):
        segments = parse_rich_text("[sad]a[none]b")
        self.assertEqual([s.emotion for s in segments], ["sad", None])

    def test_unknown_tag_is_kept_as_text(self):
        segments = parse_rich_text("[laugh]哈哈哈")
        self.assertEqual(segments[0].text, "[laugh]哈哈哈")

    def test_linebreak_becomes_pause(self):
        segments = parse_rich_text("a\nb", linebreak_pause=0.5)
        self.assertEqual(len(segments), 2)
        self.assertAlmostEqual(segments[0].pause_after, 0.5)

    def test_empty_text(self):
        self.assertEqual(parse_rich_text(""), [])
        self.assertEqual(parse_rich_text("   "), [])


class SegmentPlanTests(unittest.TestCase):
    def test_global_emotion_applies_to_all_segments(self):
        segments = parse_rich_text("第一句。[pause:0.3s]第二句。")
        plans = build_segment_plans(segments, global_emotion="sad")

        self.assertEqual(len(plans), 2)
        self.assertTrue(all("悲伤" in plan.instruct for plan in plans))

    def test_text_without_markup_stays_one_segment(self):
        segments = parse_rich_text("第一句。第二句。")
        plans = build_segment_plans(segments, global_emotion="sad")

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].text, "第一句。第二句。")

    def test_inline_emotion_overrides_global(self):
        segments = parse_rich_text("普通。[whisper]悄悄话")
        plans = build_segment_plans(segments, global_emotion="sad")

        self.assertIn("悲伤", plans[0].instruct)
        self.assertIn("耳语", plans[1].instruct)

    def test_inline_rate_overrides_global(self):
        segments = parse_rich_text("慢[rate:1.5]快")
        plans = build_segment_plans(segments, global_rate=0.9)

        self.assertEqual([plan.rate for plan in plans], [0.9, 1.5])

    def test_pauses_are_not_scaled_by_default(self):
        segments = parse_rich_text("a[pause:1s]b")
        plans = build_segment_plans(segments, global_rate=2.0)

        self.assertAlmostEqual(plans[0].pause_after, 1.0)

    def test_pauses_scale_when_requested(self):
        segments = parse_rich_text("a[pause:1s]b")
        plans = build_segment_plans(segments, global_rate=2.0, scale_pauses_with_speed=True)

        self.assertAlmostEqual(plans[0].pause_after, 0.5)

    def test_invalid_rate_falls_back_to_one(self):
        segments = parse_rich_text("[rate:0]a")
        plans = build_segment_plans(segments)

        self.assertEqual(plans[0].rate, 1.0)

    def test_segments_without_text_are_dropped(self):
        segments = parse_rich_text("[sad]   [whisper]hi")
        plans = build_segment_plans(segments)

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].text, "hi")


class TimeStretchTests(unittest.TestCase):
    def test_rate_one_is_identity(self):
        wav = [0.0, 0.1, -0.1, 0.0]
        self.assertIs(time_stretch(wav, 1.0), wav)

    def test_rate_change_shortens_audio(self):
        try:
            import numpy as np
        except ImportError:  # pragma: no cover
            self.skipTest("numpy unavailable")

        sr = 24000
        t = np.arange(sr, dtype=np.float32) / sr
        wav = np.sin(2 * np.pi * 220 * t).astype(np.float32)

        faster = time_stretch(wav, 1.25)
        slower = time_stretch(wav, 0.8)

        self.assertLess(len(faster), len(wav))
        self.assertGreater(len(slower), len(wav))


if __name__ == "__main__":
    unittest.main()
