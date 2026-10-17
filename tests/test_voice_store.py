import os
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice_store import (
    build_filename_choices,
    collect_voice_dirs,
    dir_label,
    list_voice_files,
    parse_env_dirs,
    resolve_input_path,
    resolve_output_dir,
    sibling_metadata_paths,
    split_display_name,
)


class CollectVoiceDirsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.models = os.path.join(self.root, "models")
        self.default = os.path.join(self.models, "qwen-tts", "voices")
        os.makedirs(self.default)

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_dir_only(self):
        dirs = collect_voice_dirs(self.models)
        self.assertEqual(dirs, [os.path.abspath(self.default)])

    def test_default_dir_missing_is_skipped(self):
        default = os.path.join(self.models, "qwen-tts", "voices")
        os.rmdir(default)
        self.assertEqual(collect_voice_dirs(self.models), [])

    def test_registered_root_with_voices_child(self):
        extra = os.path.join(self.root, "extra", "qwen-tts")
        os.makedirs(os.path.join(extra, "voices"))

        dirs = collect_voice_dirs(self.models, [extra])

        self.assertIn(os.path.abspath(os.path.join(extra, "voices")), dirs)

    def test_registered_root_flat_layout(self):
        extra = os.path.join(self.root, "flat")
        os.makedirs(extra)

        dirs = collect_voice_dirs(self.models, [extra])

        self.assertIn(os.path.abspath(extra), dirs)

    def test_env_dirs(self):
        other = os.path.join(self.root, "other")
        os.makedirs(other)

        dirs = collect_voice_dirs(self.models, env_value=other)

        self.assertIn(os.path.abspath(other), dirs)

    def test_duplicates_are_removed(self):
        dirs = collect_voice_dirs(
            self.models,
            [os.path.join(self.models, "qwen-tts")],
            env_value=self.default,
        )
        self.assertEqual(len(dirs), len({os.path.normcase(d) for d in dirs}))

    def test_default_dir_is_first(self):
        other = os.path.join(self.root, "other")
        os.makedirs(other)
        dirs = collect_voice_dirs(self.models, env_value=other)
        self.assertEqual(dirs[0], os.path.abspath(self.default))

    def test_parse_env_dirs(self):
        raw = f"{os.sep}tmp{os.sep}a{os.pathsep}{os.sep}tmp{os.sep}b"
        self.assertEqual(len(parse_env_dirs(raw)), 2)
        self.assertEqual(parse_env_dirs(""), [])
        self.assertEqual(parse_env_dirs(None if os.environ.get("QWEN_TTS_VOICE_DIRS") is None else ""), [])


class LabelTests(unittest.TestCase):
    def test_default_label(self):
        models = os.path.join(os.sep, "m")
        path = os.path.join(models, "qwen-tts", "voices")
        self.assertEqual(dir_label(path, models), "voices")

    def test_named_dir_uses_basename(self):
        models = os.path.join(os.sep, "m")
        self.assertEqual(dir_label(os.path.join(os.sep, "lib", "narration"), models), "narration")

    def test_voices_dir_in_other_root_uses_parent(self):
        models = os.path.join(os.sep, "m")
        path = os.path.join(os.sep, "lib", "shared", "voices")
        self.assertEqual(dir_label(path, models), "shared")


class ListVoiceFilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.a = os.path.join(self.root, "voices")
        self.b = os.path.join(self.root, "custom")
        os.makedirs(self.a)
        os.makedirs(self.b)
        for name in ("z.wav", "a.WAV", "notes.txt"):
            open(os.path.join(self.a, name), "w").close()
        open(os.path.join(self.b, "hero.flac"), "w").close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_lists_audio_only_and_sorted(self):
        entries = list_voice_files([self.a])
        names = [n for n, _ in entries]
        self.assertEqual(names, ["voices/a.WAV", "voices/z.wav"])

    def test_multiple_dirs(self):
        entries = list_voice_files([self.a, self.b])
        names = [n for n, _ in entries]
        self.assertIn("custom/hero.flac", names)
        self.assertEqual(len(names), 3)
        self.assertEqual(names, sorted(names, key=str.lower))

    def test_missing_dir_is_ignored(self):
        entries = list_voice_files([os.path.join(self.root, "nope")])
        self.assertEqual(entries, [])

    def test_build_choices(self):
        entries = list_voice_files([self.a])
        self.assertEqual(len(build_filename_choices(entries)), 2)
        self.assertEqual(build_filename_choices([], empty=True), ["None"])

    def test_split_display_name(self):
        self.assertEqual(split_display_name("voices/a.wav"), ("voices", "a.wav"))
        self.assertEqual(split_display_name("a.wav"), (None, "a.wav"))
        self.assertEqual(split_display_name("voices\\a.wav"), ("voices", "a.wav"))


class ResolvePathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.models = os.path.join(self.root, "models")
        self.default = os.path.join(self.models, "qwen-tts", "voices")
        os.makedirs(self.default)
        open(os.path.join(self.default, "hero.wav"), "w").close()
        self.custom = os.path.join(self.root, "custom")
        os.makedirs(self.custom)
        open(os.path.join(self.custom, "villain.wav"), "w").close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_output_uses_default_and_creates(self):
        target = resolve_output_dir("", self.models)
        self.assertEqual(target, os.path.abspath(self.default))

    def test_relative_output_is_under_qwen_tts(self):
        target = resolve_output_dir("my_lib", self.models)
        self.assertEqual(target, os.path.abspath(os.path.join(self.models, "qwen-tts", "my_lib")))
        self.assertTrue(os.path.isdir(target))

    def test_absolute_output_is_honoured(self):
        target = resolve_output_dir(self.custom, self.models)
        self.assertEqual(target, os.path.abspath(self.custom))

    def test_output_creates_missing_nested_dir(self):
        target = resolve_output_dir(os.path.join(self.root, "a", "b"), self.models)
        self.assertTrue(os.path.isdir(target))

    def test_resolve_by_label(self):
        path = resolve_input_path("custom/villain.wav", [self.default, self.custom], self.models)
        self.assertEqual(path, os.path.abspath(os.path.join(self.custom, "villain.wav")))

    def test_resolve_by_bare_name_searches_all_dirs(self):
        path = resolve_input_path("villain.wav", [self.default, self.custom], self.models)
        self.assertEqual(path, os.path.abspath(os.path.join(self.custom, "villain.wav")))

    def test_resolve_absolute_path(self):
        full = os.path.join(self.custom, "villain.wav")
        self.assertEqual(resolve_input_path(full, [self.default], self.models), os.path.abspath(full))

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            resolve_input_path("nope.wav", [self.default], self.models)

    def test_empty_input_raises(self):
        with self.assertRaises(ValueError):
            resolve_input_path("", [self.default], self.models)

    def test_sibling_metadata_paths(self):
        paths = sibling_metadata_paths(os.path.join(self.custom, "villain.wav"))
        self.assertEqual(paths["qvp"], os.path.join(self.custom, "villain.qvp"))
        self.assertEqual(paths["json"], os.path.join(self.custom, "villain.json"))


if __name__ == "__main__":
    unittest.main()
