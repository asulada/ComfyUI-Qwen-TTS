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
    build_emotion_instruct,
    build_segment_plans,
    parse_rich_text,
    time_stretch,
)


def _load_nodes_helpers():
    """Extract the pure helper functions from nodes.py.

    nodes.py imports torch/folder_paths/comfy at module level, so it cannot be
    imported directly in a bare test environment.  These helpers are deliberately
    free of those dependencies, which lets the parser behaviour be tested without
    a ComfyUI install.
    """
    source = (ROOT / "nodes.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted = {"expand_dialogue_line", "split_text_by_pauses", "unpack_role"}
    picked = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    namespace = {
        "Dict": dict, "List": list, "Tuple": tuple, "Any": object,
        "re": __import__("re"),
        "build_segment_plans": build_segment_plans,
        "build_emotion_instruct": build_emotion_instruct,
        "parse_rich_text": parse_rich_text,
    }
    exec(compile(ast.Module(body=picked, type_ignores=[]),
                 str(ROOT / "nodes.py"), "exec"), namespace)
    return namespace


_helpers = _load_nodes_helpers()
expand_dialogue_line = _helpers["expand_dialogue_line"]
unpack_role = _helpers["unpack_role"]

NO_PAUSES = {
    "pause_linebreak": 0.0, "period_pause": 0.0, "comma_pause": 0.0,
    "question_pause": 0.0, "hyphen_pause": 0.0,
}


class PlainLineTests(unittest.TestCase):
    def test_no_markup_is_a_single_unit(self):
        units = expand_dialogue_line("你好世界", NO_PAUSES)
        self.assertEqual(len(units), 1)
        text, instruct, _lead, _pause, _dropped, _rate = units[0]
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


class StickyAcrossPunctuationTests(unittest.TestCase):
    """Sticky state must survive the punctuation split.

    Regression: markup used to be resolved *after* `split_text_by_pauses`, so a
    `[sad]` at the start of a line was cut off at the first full stop and only
    the first fragment got the instruction.  Markup is now resolved first.
    """

    PAUSES = dict(NO_PAUSES, period_pause=0.4)

    def test_emotion_carries_past_a_period(self):
        units = expand_dialogue_line("[sad]第一句。第二句。", self.PAUSES)
        self.assertEqual(len(units), 2)
        for unit in units:
            self.assertIn("悲伤", unit[1])

    def test_style_carries_past_a_period(self):
        units = expand_dialogue_line("[style:压低嗓音]第一句。第二句。", self.PAUSES)
        self.assertEqual(len(units), 2)
        for unit in units:
            self.assertIn("压低嗓音", unit[1])

    def test_emotion_carries_past_a_comma(self):
        config = dict(NO_PAUSES, comma_pause=0.2)
        units = expand_dialogue_line("[sad]第一句，第二句。", config)
        self.assertEqual(len(units), 2)
        self.assertTrue(all("悲伤" in u[1] for u in units if u[1]))

    def test_later_tag_still_overrides(self):
        units = expand_dialogue_line("[sad]第一句。[tender]第二句。", self.PAUSES)
        self.assertIn("悲伤", units[0][1])
        self.assertNotIn("悲伤", units[1][1])

    def test_dropped_tag_reported_once_per_segment(self):
        units = expand_dialogue_line("[laugh]第一句。第二句。", self.PAUSES)
        reported = [u[4] for u in units]
        self.assertEqual(reported[0], ["[laugh]"])
        self.assertEqual(reported[1], [])

    def test_leading_pause_only_on_first_fragment(self):
        units = expand_dialogue_line("[pause:500ms]第一句。第二句。", self.PAUSES)
        self.assertAlmostEqual(units[0][2], 0.5)
        self.assertAlmostEqual(units[1][2], 0.0)


class PerFragmentRateTests(unittest.TestCase):
    """[rate:x] must reach the caller; it used to be silently dropped."""

    def test_rate_is_returned(self):
        units = expand_dialogue_line("[rate:1.5]快一点。", NO_PAUSES)
        self.assertAlmostEqual(units[0][5], 1.5)

    def test_rate_defaults_to_global(self):
        units = expand_dialogue_line("正常速度。", NO_PAUSES, global_rate=1.2)
        self.assertAlmostEqual(units[0][5], 1.2)

    def test_rate_falls_back_to_one_when_global_is_zero(self):
        units = expand_dialogue_line("文本。", NO_PAUSES, global_rate=0.0)
        self.assertAlmostEqual(units[0][5], 1.0)

    def test_rate_is_sticky_within_a_line(self):
        config = dict(NO_PAUSES, period_pause=0.4)
        units = expand_dialogue_line("[rate:0.8]第一句。第二句。", config)
        self.assertTrue(all(u[5] == 0.8 for u in units))

    def test_rate_changes_mid_line(self):
        config = dict(NO_PAUSES, period_pause=0.4)
        units = expand_dialogue_line("[rate:1.4]快。\n[rate:0.7]慢。", config)
        self.assertEqual(units[0][5], 1.4)
        self.assertEqual(units[1][5], 0.7)

    def test_pauses_scale_with_rate_when_requested(self):
        config = dict(NO_PAUSES, period_pause=1.0)
        units = expand_dialogue_line("[rate:2.0]第一句。第二句。", config,
                                     scale_pauses_with_speed=True)
        self.assertAlmostEqual(units[0][3], 0.5)

    def test_pauses_untouched_by_default(self):
        config = dict(NO_PAUSES, period_pause=1.0)
        units = expand_dialogue_line("[rate:2.0]第一句。第二句。", config)
        self.assertAlmostEqual(units[0][3], 1.0)


class RoleVoiceCardTests(unittest.TestCase):
    """A role can carry its own voice card, so roles need not share one instruct.

    Before this, DialogueInferenceNode had a single node-level `instruct` that was
    appended to every line, so a low-pitched forty-year-old and a bright-voiced
    teenager could not both be described correctly.
    """

    OLD_BOSS = "四十岁男性，低音区，嗓音沙哑，语速偏慢"
    YOUNG_KID = "十八岁少年，高音区，音色清亮，语速略快"

    def test_voice_card_reaches_instruct(self):
        units = expand_dialogue_line("你再说一遍。", NO_PAUSES, voice_card=self.OLD_BOSS)
        self.assertIn(self.OLD_BOSS, units[0][1])

    def test_different_roles_get_different_cards(self):
        boss = expand_dialogue_line("你再说一遍。", NO_PAUSES, voice_card=self.OLD_BOSS)
        kid = expand_dialogue_line("我错了。", NO_PAUSES, voice_card=self.YOUNG_KID)
        self.assertIn("四十岁", boss[0][1])
        self.assertNotIn("四十岁", kid[0][1])
        self.assertIn("十八岁", kid[0][1])
        self.assertNotIn("十八岁", boss[0][1])

    def test_card_sits_after_style_and_before_node_instruct(self):
        units = expand_dialogue_line(
            "[style:放下戒备]算了。", NO_PAUSES,
            voice_card=self.OLD_BOSS, extra_instruct="全局补充",
        )
        instruct = units[0][1]
        self.assertLess(instruct.index("放下戒备"), instruct.index("四十岁"))
        self.assertLess(instruct.index("四十岁"), instruct.index("全局补充"))

    def test_card_stacks_with_emotion_preset(self):
        units = expand_dialogue_line("[angry]你再说一遍。", NO_PAUSES,
                                     voice_card=self.OLD_BOSS)
        instruct = units[0][1]
        self.assertIn("愤怒", instruct)
        self.assertIn(self.OLD_BOSS, instruct)

    def test_card_covers_every_fragment_of_a_line(self):
        config = dict(NO_PAUSES, period_pause=0.4)
        units = expand_dialogue_line("第一句。第二句。", config, voice_card=self.OLD_BOSS)
        self.assertEqual(len(units), 2)
        for unit in units:
            self.assertIn(self.OLD_BOSS, unit[1])

    def test_empty_card_is_a_no_op(self):
        with_card = expand_dialogue_line("他走了。", NO_PAUSES, voice_card="")
        without = expand_dialogue_line("他走了。", NO_PAUSES)
        self.assertEqual(with_card[0][1], without[0][1])


class UnpackRoleTests(unittest.TestCase):
    """Bank entries must work in all three shapes that can reach the node."""

    def test_bare_prompt_dict_has_no_card(self):
        entry = {"prompt": "ignored", "x_vector_only_mode": False, "ref_text": "x"}
        # A packaged prompt dict is returned as-is; only the {"prompt": ...}
        # wrapper introduced for voice cards is unpacked.
        prompt, card = unpack_role({"ref_code": "c", "x_vector_only_mode": False})
        self.assertEqual(card, "")
        self.assertIsInstance(prompt, dict)

    def test_list_returns_first_item(self):
        prompt, card = unpack_role(["item-a", "item-b"])
        self.assertEqual(prompt, "item-a")
        self.assertEqual(card, "")

    def test_wrapper_with_card(self):
        prompt, card = unpack_role({"prompt": "P", "instruct": self.OLD})
        self.assertEqual(prompt, "P")
        self.assertEqual(card, self.OLD)

    def test_wrapper_without_card(self):
        prompt, card = unpack_role({"prompt": "P", "instruct": ""})
        self.assertEqual(prompt, "P")
        self.assertEqual(card, "")

    def test_wrapper_missing_instruct_key(self):
        prompt, card = unpack_role({"prompt": "P"})
        self.assertEqual(prompt, "P")
        self.assertEqual(card, "")

    def test_scalar_passes_through(self):
        prompt, card = unpack_role("raw")
        self.assertEqual(prompt, "raw")
        self.assertEqual(card, "")

    # --- regression: a card must not change the prompt's *shape* -------------
    # DialogueInferenceNode repeats one prompt per line to build a batch, and
    # the model indexes it as a list of prompt items.  When the card branch
    # returned the list unwrapped, the batch became [[item], [item]] and
    # generation died on `it.ref_code`.  Bare and wrapped entries must hand
    # back the same single item.

    def test_wrapper_containing_a_prompt_list_is_unwrapped(self):
        item = object()
        prompt, card = unpack_role({"prompt": [item], "instruct": self.OLD})
        self.assertIs(prompt, item)
        self.assertEqual(card, self.OLD)

    def test_wrapped_and_bare_prompt_have_the_same_shape(self):
        item = object()
        bare_prompt, _ = unpack_role([item])
        wrapped_prompt, _ = unpack_role({"prompt": [item], "instruct": self.OLD})
        self.assertIs(bare_prompt, wrapped_prompt)

    def test_wrapped_multi_item_list_still_yields_one_item(self):
        # One role has one voice; a stray multi-item list must not leak a batch
        # dimension into the per-line batch.
        prompt, _ = unpack_role({"prompt": ["a", "b"], "instruct": self.OLD})
        self.assertEqual(prompt, "a")

    def test_wrapped_empty_list_is_none(self):
        prompt, card = unpack_role({"prompt": [], "instruct": self.OLD})
        self.assertIsNone(prompt)
        self.assertEqual(card, self.OLD)

    def test_bare_empty_list_is_none(self):
        prompt, card = unpack_role([])
        self.assertIsNone(prompt)
        self.assertEqual(card, "")

    OLD = "四十岁男性，低音区"


if __name__ == "__main__":
    unittest.main()
