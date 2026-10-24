import json
import os
import sys
import tempfile
import types
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import inspect_voices as iv  # noqa: E402


def write_wav(path, seconds, rate=24000):
    frames = int(seconds * rate)
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * frames)


def make_item(xvec=False, icl=True, code="codes", text="参考文本"):
    item = iv._PromptItemStub()
    item.x_vector_only_mode = xvec
    item.icl_mode = icl
    item.ref_code = code
    item.ref_text = text
    return item


class DescribeItemsTests(unittest.TestCase):
    def test_icl_item(self):
        mode, count, notes = iv._describe_items([make_item()])
        self.assertEqual((mode, count, notes), ("icl", 1, []))

    def test_xvec_item(self):
        mode, count, notes = iv._describe_items([make_item(xvec=True, icl=False, code=None)])
        self.assertEqual((mode, count), ("xvec", 1))
        self.assertEqual(notes, [])

    def test_icl_without_ref_code_is_broken(self):
        mode, _count, notes = iv._describe_items([make_item(code=None)])
        self.assertEqual(mode, "broken")
        self.assertTrue(notes)

    def test_flags_absent_falls_back_to_xvec(self):
        mode, _count, notes = iv._describe_items([make_item(icl=False, code=None)])
        self.assertEqual(mode, "xvec")
        self.assertTrue(notes)

    def test_mixed_batch(self):
        mode, count, _notes = iv._describe_items([make_item(), make_item(xvec=True, icl=False, code=None)])
        self.assertEqual((mode, count), ("mixed", 2))

    def test_empty_list(self):
        self.assertEqual(iv._describe_items([]), ("unknown", 0, []))


class LoadQvpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.payloads = {}
        self._saved_torch = sys.modules.get("torch")
        fake = types.ModuleType("torch")
        fake.load = lambda path, *a, **kw: self.payloads[os.path.basename(path)]
        sys.modules["torch"] = fake

    def tearDown(self):
        if self._saved_torch is None:
            sys.modules.pop("torch", None)
        else:
            sys.modules["torch"] = self._saved_torch

    def _write(self, name, payload):
        path = os.path.join(self.tmp.name, name)
        with open(path, "wb") as handle:
            handle.write(b"stub")
        self.payloads[name] = payload
        return path

    def test_raw_list(self):
        path = self._write("a.qvp", [make_item()])
        items, error = iv._load_qvp(path)
        self.assertEqual(error, "")
        self.assertEqual(len(items), 1)

    def test_packaged_dict(self):
        path = self._write("b.qvp", {"prompt": [make_item()], "ref_text": "x"})
        items, error = iv._load_qvp(path)
        self.assertEqual(error, "")
        self.assertEqual(len(items), 1)

    def test_packaged_without_prompt_key(self):
        path = self._write("c.qvp", {"ref_text": "x"})
        self.assertIsNone(iv._load_qvp(path)[0])

    def test_non_prompt_payload_is_rejected(self):
        path = self._write("d.qvp", "not a prompt")
        items, error = iv._load_qvp(path)
        self.assertIsNone(items)
        self.assertIn("not a VoiceClonePromptItem", error)

    def test_empty_prompt_list(self):
        path = self._write("e.qvp", [])
        items, error = iv._load_qvp(path)
        self.assertIsNone(items)
        self.assertIn("empty", error)


class DurationProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_wav_duration_and_rate(self):
        path = os.path.join(self.tmp.name, "a.wav")
        write_wav(path, 7.5, rate=16000)
        duration, rate, error = iv.probe_audio_duration(path)
        self.assertEqual(error, "")
        self.assertAlmostEqual(duration, 7.5, places=3)
        self.assertEqual(rate, 16000)

    def test_corrupt_wav_reports_error(self):
        path = os.path.join(self.tmp.name, "broken.wav")
        with open(path, "wb") as handle:
            handle.write(b"not a wav")
        duration, _rate, error = iv.probe_audio_duration(path)
        self.assertIsNone(duration)
        self.assertTrue(error)

    def test_missing_file_reports_error(self):
        duration, _rate, error = iv.probe_audio_duration(
            os.path.join(self.tmp.name, "nope.wav")
        )
        self.assertIsNone(duration)
        self.assertTrue(error)


class ReferenceQualityTests(unittest.TestCase):
    def _report(self, seconds, ref_text, mode="icl"):
        report = iv.VoiceReport(
            rel_path="v", directory=".", stem="v",
            has_wav=True, has_qvp=True, has_json=True,
        )
        report.duration = seconds
        report.ref_text = ref_text
        report.mode = mode
        return report

    def test_chars_per_second_none_without_duration(self):
        report = self._report(None, "文本")
        self.assertIsNone(report.chars_per_second)

    def test_chars_per_second_none_without_text(self):
        report = self._report(5.0, "")
        self.assertIsNone(report.chars_per_second)

    def test_short_audio_gets_rebuild_verdict(self):
        report = self._report(3.2, "我叫阿珍，你叫什么名字")
        self.assertIn("VERY SHORT", iv._verdict_for(report))
        iv._annotate_reference_quality(report)
        self.assertTrue(any("5-15s" in note for note in report.notes))

    def test_borderline_audio_is_flagged_softly(self):
        report = self._report(4.5, "一段四点五秒的参考文本内容")
        self.assertIn("short audio", iv._verdict_for(report))

    def test_healthy_audio_is_ok(self):
        report = self._report(9.5, "这是一段比较长的参考录音文本用来验证时长和字数比例是否匹配")
        self.assertEqual(iv._verdict_for(report), "ok")
        iv._annotate_reference_quality(report)
        self.assertEqual(report.notes, [])

    def test_dense_transcript_is_flagged(self):
        report = self._report(6.0, "这是一段明显过长的参考文本内容并不匹配实际录音时长" * 3)
        self.assertGreater(report.chars_per_second, 8.5)
        self.assertIn("transcript likely mismatched", iv._verdict_for(report))

    def test_sparse_transcript_is_flagged(self):
        report = self._report(12.0, "短")
        iv._annotate_reference_quality(report)
        self.assertTrue(any("sparse" in note for note in report.notes))

    def test_sparse_transcript_shows_in_verdict(self):
        # 21 chars over 11s = 1.9 c/s, well under the Chinese floor of 3.0.
        report = self._report(11.0, "这是一段只有二十一个字的参考录音文本内容呀")
        self.assertLess(report.chars_per_second, 3.0)
        self.assertIn("sparse transcript", iv._verdict_for(report))

    def test_verdict_and_notes_agree(self):
        # A voice must never be "ok" while its verbose notes flag a problem.
        cases = [
            (2.5, "我叫阿珍，你叫什么名字"),
            (11.0, "这是一段只有二十一个字的参考录音文本内容呀"),
            (6.0, "这是一段明显过长的参考文本内容并不匹配实际录音时长" * 3),
            (5.7, "这是一段比较正常的参考录音文本大约三十三个字符长度"),
        ]
        for seconds, text in cases:
            report = self._report(seconds, text)
            iv._annotate_reference_quality(report)
            self.assertEqual(
                bool(report.notes),
                iv._verdict_for(report) != "ok",
                f"mismatch for {seconds}s / {len(text)} chars: "
                f"verdict={iv._verdict_for(report)!r} notes={report.notes}",
            )

    def test_long_audio_note(self):
        report = self._report(20.0, "这是一段二十秒长的参考录音文本用于测试上限提醒")
        iv._annotate_reference_quality(report)
        self.assertTrue(any("15s guidance" in note for note in report.notes))

    def test_latin_density_threshold_differs(self):
        # 24 chars over 6s = 4 c/s: fine for Latin, dense is > 4.5.
        report = self._report(6.0, "This is a short reference transcript")
        self.assertEqual(report.ref_text_chars, 36)
        self.assertTrue(iv._verdict_for(report).startswith("transcript likely mismatched"))

    def test_unknown_mode_returns_review(self):
        report = self._report(9.0, "正常的参考文本内容", mode="unknown")
        self.assertEqual(iv._verdict_for(report), "review")


class ScanIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name

    def test_duration_is_populated_for_wav(self):
        write_wav(os.path.join(self.dir, "voice.wav"), 6.25)
        report = {r.rel_path: r for r in iv.scan_directories([self.dir])}["voice"]
        self.assertAlmostEqual(report.duration, 6.25, places=3)
        self.assertEqual(report.sample_rate, 24000)
        self.assertEqual(report.duration_error, "")

    def test_short_wav_produces_note(self):
        write_wav(os.path.join(self.dir, "thin.wav"), 3.0)
        report = {r.rel_path: r for r in iv.scan_directories([self.dir])}["thin"]
        self.assertTrue(any("5-15s" in note for note in report.notes))


class ScanDirectoriesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name

    def _touch(self, name):
        with open(os.path.join(self.dir, name), "wb") as handle:
            handle.write(b"x")

    def _reports(self):
        return {report.rel_path: report for report in iv.scan_directories([self.dir])}

    def test_no_cache_voice_is_reported_as_none(self):
        self._touch("plain.wav")
        report = self._reports()["plain"]
        self.assertEqual(report.mode, "none")
        self.assertTrue(report.loadable)

    def test_json_only_group_is_unloadable(self):
        self._touch("meta.json")
        report = self._reports()["meta"]
        self.assertFalse(report.has_wav)
        self.assertFalse(report.loadable)

    def test_ref_text_length_comes_from_json(self):
        self._touch("voice.wav")
        self._touch("voice.json")
        with open(os.path.join(self.dir, "voice.json"), "w", encoding="utf-8") as handle:
            json.dump({"ref_text": "一二三四五"}, handle, ensure_ascii=False)
        report = self._reports()["voice"]
        self.assertEqual(report.ref_text_chars, 5)

    def test_subdirectories_are_scanned(self):
        nested = os.path.join(self.dir, "chapter1")
        os.makedirs(nested)
        with open(os.path.join(nested, "heroine.wav"), "wb") as handle:
            handle.write(b"x")
        self.assertIn("chapter1/heroine", self._reports())

    def test_audio_extension_case_insensitive(self):
        self._touch("LOUD.WAV")
        self.assertIn("LOUD", self._reports())


if __name__ == "__main__":
    unittest.main()
