"""Tests for per-fragment markup inside a dialogue line.

`expand_dialogue_line` is the shared entry point that lets DialogueInference
apply inline markup without duplicating the parser logic.  It runs two passes:
punctuation splitting (existing behaviour, keeps pauses natural) and then
markup resolution (new, lets emotion change mid-line).

The function is imported from source so the tests do not need torch/ComfyUI.
"""

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from emotion_utils import (  # noqa: E402
    build_segment_plans,
    parse_rich_text,
    time_stretch,
)


def _load_expand():
    source = (ROOT / "nodes.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted = {"expand_dialogue_line", "split_text_by_pauses"}
    picked = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    namespace = {
        "Dict": dict, "List": list, "Tuple": tuple, "re": __import__("re"),
        "build_segment_plans": build_segment_plans,
        "parse_rich_text": parse_rich_text,
    }
    exec(compile(ast.Module(body=picked, type_ignores=[]),
                 str(ROOT / "nodes.py"), "exec"), namespace)
    return namespace["expand_dialogue_line"]


expand_dialogue_line = _load_expand()

NO_PAUSES = {
    "pause_linebreak": 0.0, "period_pause": 0.0, "comma_pause": 0.0,
    "question_pause": 0.0, "hyphen_pause": 0.0,
}


class PlainLineTests(unittest.TestCase):
    def test_no_markup_is_a_single_unit(self):
        units = expand_dialogue_line("你好世界", NO_PAUSES)
        self.assertEqual(len(units), 1)
        text, instruct, _lead, _pause, _dropped = units[0]
        self.assertEqual(text, "你好世界")
        self.assertEqual(instruct, "")

    def test_node_level_instruct_applies_to_every_unit(self):
        units = expand_dialogue_line("甲[question_pause]", NO_PAUSES,
                                     extra_instruct="青年男声")
        self.assertTrue(all(u[1] == "青年男声" for u in units))

    def test_punctuation_split_still_works(self):
        config = dict(NO_PAUSES, period_pause=0.4)
        units = expand_dialogue_line("第一句。第二句。", config)
        self.assertEqual(len(units), 2)
        self.assertAlmostEqual(units[0][3], 0.4)

    def test_empty_fragments_are_skipped(self):
        config = dict(NO_PAUSES, period_pause=0.3)
        self.assertEqual(expand_dialogue_line("。。。", config), [])


class MarkupTests(unittest.TestCase):
    def test_emotion_tag_sets_instruct_for_that_unit(self):
        units = expand_dialogue_line("[sad]他走了", NO_PAUSES)
        self.assertEqual(len(units), 1)
        self.assertIn("悲伤", units[0][1])
        # The tag itself must not reach the model as text.
        self.assertEqual(units[0][0], "他走了")

    def test_emotion_changes_mid_line(self):
        units = expand_dialogue_line("[sad]甲[sad]乙", NO_PAUSES)
        self.assertEqual(len(units), 2)
        self.assertTrue(all("悲伤" in u[1] for u in units))

    def test_style_tag_reaches_instruct(self):
        units = expand_dialogue_line("[style:压低嗓音]你确定？", NO_PAUSES)
        self.assertIn("压低嗓音", units[0][1])
        self.assertEqual(units[0][0], "你确定？")

    def test_unknown_tag_is_dropped_and_reported(self):
        units = expand_dialogue_line("[laugh]哈哈哈", NO_PAUSES)
        self.assertEqual(units[0][0], "哈哈哈")
        self.assertTrue(units[0][4])

    def test_pause_tag_adds_to_unit_pause(self):
        units = expand_dialogue_line("说完了[pause:500ms]下一句", NO_PAUSES)
        self.assertEqual(len(units), 2)
        self.assertAlmostEqual(units[0][3], 0.5)

    def test_trailing_flat_punctuation_is_stripped(self):
        units = expand_dialogue_line("好的。", NO_PAUSES)
        self.assertEqual(units[0][0], "好的")

    def test_question_mark_is_kept(self):
        units = expand_dialogue_line("真的吗？", NO_PAUSES)
        self.assertEqual(units[0][0], "真的吗？")

    def test_leading_pause_from_break_tag_is_gone(self):
        # [break=] is deprecated: dropped, with a report, and no pause.
        units = expand_dialogue_line("[break=1.5]你好", NO_PAUSES)
        self.assertEqual(units[0][0], "你好")
        self.assertAlmostEqual(units[0][2], 0.0)


class InstructIsolationTests(unittest.TestCase):
    """Each role keeps its own timbre; only the delivery text changes."""

    def test_each_unit_carries_its_own_instruct(self):
        units = expand_dialogue_line(
            "[sad]第一段[sad]第二段[style:带笑]第三段", NO_PAUSES
        )
        # [sad] flushes the preceding text, but [style:] only changes sticky
        # state, so the text after it joins the current segment.
        self.assertEqual(len(units), 2)
        self.assertIn("悲伤", units[0][1])
        self.assertNotIn("带笑", units[0][1])
        self.assertEqual(units[0][0], "第一段")
        self.assertEqual(units[1][0], "第二段第三段")
        self.assertIn("带笑", units[1][1])
        self.assertIn("悲伤", units[1][1])


if __name__ == "__main__":
    unittest.main()
