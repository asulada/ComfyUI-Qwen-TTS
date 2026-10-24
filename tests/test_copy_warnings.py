"""Tests for the defensive warnings added to the copy nodes.

The warnings exist because both failure modes are silent: a clone keeps its
timbre without `instruct` but loses its pitch range, and a mistyped role name
makes a whole dialogue line vanish.  Each helper is pure (prints only), so the
tests capture stdout instead of mocking ComfyUI.
"""

import contextlib
import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# nodes.py imports torch, folder_paths and comfy at module level, which are not
# available in a bare interpreter.  Load the two helpers from source instead.
import ast  # noqa: E402


def _load_helpers():
    source = (ROOT / "nodes.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted = {"warn_on_missing_instruct", "warn_on_missing_role"}
    picked = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    module = ast.Module(body=picked, type_ignores=[])
    namespace = {"Dict": dict, "Any": object}
    exec(compile(module, str(ROOT / "nodes.py"), "exec"), namespace)
    return namespace["warn_on_missing_instruct"], namespace["warn_on_missing_role"]


warn_on_missing_instruct, warn_on_missing_role = _load_helpers()


def capture(fn, *args):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        fn(*args)
    return buffer.getvalue()


class MissingInstructTests(unittest.TestCase):
    def test_warns_when_clone_has_no_instruct(self):
        out = capture(warn_on_missing_instruct, "", True, "VoiceClone")
        self.assertIn("VoiceClone", out)
        self.assertIn("instruct", out)
        self.assertIn("pitch", out.lower())

    def test_warns_on_whitespace_only_instruct(self):
        out = capture(warn_on_missing_instruct, "   \n\t ", True, "VoiceClone")
        self.assertTrue(out.strip())

    def test_silent_when_instruct_present(self):
        out = capture(warn_on_missing_instruct, "中高音区，音色清亮", True, "VoiceClone")
        self.assertEqual(out, "")

    def test_silent_without_clone_prompt(self):
        # CustomVoice speakers do not need instruct, so no warning there.
        out = capture(warn_on_missing_instruct, "", False, "VoiceClone")
        self.assertEqual(out, "")

    def test_message_mentions_drift_risk(self):
        out = capture(warn_on_missing_instruct, "", True, "EmotionalTTS")
        self.assertIn("EmotionalTTS", out)
        self.assertIn("octave", out.lower())


class MissingRoleTests(unittest.TestCase):
    def test_warns_for_unknown_role(self):
        bank = {"老大": object(), "小弟": object()}
        out = capture(warn_on_missing_role, "柳如烟", bank, 3)
        self.assertIn("柳如烟", out)
        self.assertIn("line 3", out)
        self.assertIn("老大", out)

    def test_silent_for_known_role(self):
        bank = {"老大": object()}
        out = capture(warn_on_missing_role, "老大", bank, 1)
        self.assertEqual(out, "")

    def test_handles_empty_bank(self):
        out = capture(warn_on_missing_role, "老大", {}, 1)
        self.assertIn("角色银行为空", out)


class SaveVoiceWarningTests(unittest.TestCase):
    """The SaveVoice message must state the consequence, not just the cause."""

    def test_wording_names_the_consequence(self):
        source = (ROOT / "nodes.py").read_text(encoding="utf-8")
        # Adjacent string literals are joined at runtime; check each fragment.
        flat = " ".join(source.split())
        self.assertIn("NOT appear in LoadSpeaker's dropdown", flat)
        self.assertIn("cannot be re-cloned", flat)


if __name__ == "__main__":
    unittest.main()
