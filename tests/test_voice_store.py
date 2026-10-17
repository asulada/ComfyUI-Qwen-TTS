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
    read_voice_metadata,
    relative_voice_path,
    resolve_bare_name,
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
        choices = build_filename_choices(entries)
        self.assertEqual(choices, ["voices/a.WAV", "voices/z.wav"])
        self.assertEqual(build_filename_choices([], empty=True), ["None"])

    def test_choices_never_contain_bare_names(self):
        entries = list_voice_files([self.a, self.b])
        choices = build_filename_choices(entries)
        self.assertTrue(all("/" in c for c in choices))
        self.assertNotIn("z.wav", choices)

    def test_same_filename_in_two_dirs_stays_distinct(self):
        dup_a = os.path.join(self.root, "libA")
        dup_b = os.path.join(self.root, "libB")
        os.makedirs(dup_a)
        os.makedirs(dup_b)
        open(os.path.join(dup_a, "same.wav"), "w").close()
        open(os.path.join(dup_b, "same.wav"), "w").close()

        choices = build_filename_choices(list_voice_files([dup_a, dup_b]))

        self.assertEqual(len([c for c in choices if c.endswith("/same.wav")]), 2)
        self.assertNotIn("same.wav", choices)

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


class BareNameResolutionTests(unittest.TestCase):
    """A bare filename must never silently load a different speaker."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.default = os.path.join(self.root, "voices")
        self.lib = os.path.join(self.root, "libB")
        self.lib2 = os.path.join(self.root, "libC")
        for d in (self.default, self.lib, self.lib2):
            os.makedirs(d)

    def tearDown(self):
        self.tmp.cleanup()

    def _touch(self, directory, name="hero.wav"):
        path = os.path.join(directory, name)
        open(path, "w").close()
        return path

    def test_default_directory_resolves(self):
        self._touch(self.default)

        resolved = resolve_bare_name("hero.wav", [self.default, self.lib])

        self.assertEqual(resolved, os.path.abspath(os.path.join(self.default, "hero.wav")))

    def test_other_directory_only_is_an_error(self):
        self._touch(self.lib)

        with self.assertRaises(RuntimeError) as ctx:
            resolve_bare_name("hero.wav", [self.default, self.lib])

        self.assertIn("not in the default voice directory", str(ctx.exception))
        self.assertIn("<label>/<file>", str(ctx.exception))

    def test_multiple_other_matches_still_error(self):
        self._touch(self.lib)
        self._touch(self.lib2)

        with self.assertRaises(RuntimeError):
            resolve_bare_name("hero.wav", [self.default, self.lib, self.lib2])

    def test_missing_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            resolve_bare_name("hero.wav", [self.default, self.lib])


class MetadataPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.lib = os.path.join(self.root, "libA")
        os.makedirs(os.path.join(self.lib, "sub"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_relative_path_is_forward_slashed(self):
        audio = os.path.join(self.lib, "sub", "hero.wav")
        open(audio, "w").close()
        self.assertEqual(relative_voice_path(audio, self.lib), "sub/hero.wav")

    def test_relative_path_at_root(self):
        audio = os.path.join(self.lib, "hero.wav")
        open(audio, "w").close()
        self.assertEqual(relative_voice_path(audio, self.lib), "hero.wav")

    def test_read_voice_metadata_missing_returns_empty(self):
        self.assertEqual(read_voice_metadata(os.path.join(self.lib, "nope.wav")), {})

    def test_read_voice_metadata_reads_relative_path(self):
        import json

        audio = os.path.join(self.lib, "hero.wav")
        open(audio, "w").close()
        with open(os.path.join(self.lib, "hero.json"), "w", encoding="utf-8") as f:
            json.dump({"relative_path": "hero.wav", "ref_text": "hi"}, f)

        meta = read_voice_metadata(audio)

        self.assertEqual(meta["relative_path"], "hero.wav")
        self.assertEqual(meta["ref_text"], "hi")


if __name__ == "__main__":
    unittest.main()
