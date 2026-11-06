import os
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice_store import (
    PROMPT_EXTENSIONS,
    SOURCE_AUDIO,
    SOURCE_PROMPT,
    SOURCE_STEM,
    audio_stems_without_prompt,
    build_filename_choices,
    collect_voice_dirs,
    describe_source,
    detect_source_kind,
    dir_label,
    list_prompt_files,
    list_voice_files,
    parse_env_dirs,
    read_voice_metadata,
    relative_voice_path,
    resolve_bare_name,
    resolve_input_path,
    resolve_output_dir,
    resolve_voice_source,
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


class ListPromptFilesTests(unittest.TestCase):
    """The .qvp dropdown must not leak into the audio dropdown."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.voices = os.path.join(self.root, "voices")
        os.makedirs(self.voices)
        for name in ("hero.wav", "hero.qvp", "solo.qvp", "solo.json", "notes.txt"):
            open(os.path.join(self.voices, name), "w").close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_prompt_listing_contains_only_qvp(self):
        displays = [d for d, _ in list_prompt_files([self.voices])]
        self.assertEqual(displays, ["voices/hero.qvp", "voices/solo.qvp"])

    def test_audio_listing_is_unchanged_by_default(self):
        # Existing callers must keep seeing audio only.
        displays = [d for d, _ in list_voice_files([self.voices])]
        self.assertEqual(displays, ["voices/hero.wav"])

    def test_audio_stems_without_prompt_drops_covered_voices(self):
        # hero is covered by hero.qvp, so only... nothing remains here.
        remaining = audio_stems_without_prompt(
            list_voice_files([self.voices]), list_prompt_files([self.voices])
        )
        self.assertEqual(remaining, [])

    def test_audio_stems_without_prompt_keeps_uncovered_voices(self):
        open(os.path.join(self.voices, "only_audio.wav"), "w").close()
        remaining = audio_stems_without_prompt(
            list_voice_files([self.voices]), list_prompt_files([self.voices])
        )
        self.assertEqual([d for d, _ in remaining], ["voices/only_audio.wav"])

    def test_no_prompts_means_audio_unchanged(self):
        remaining = audio_stems_without_prompt(list_voice_files([self.voices]), [])
        self.assertEqual([d for d, _ in remaining], ["voices/hero.wav"])

    def test_prompt_and_audio_dropdowns_have_no_duplicate_voice(self):
        prompts = [d for d, _ in list_prompt_files([self.voices])]
        audios = [
            d
            for d, _ in audio_stems_without_prompt(
                list_voice_files([self.voices]), list_prompt_files([self.voices])
            )
        ]

        def stems(names):
            return {os.path.splitext(name)[0] for name in names}

        self.assertEqual(stems(prompts) & stems(audios), set())

    def test_recursive_still_applies_to_prompts(self):
        nested = os.path.join(self.voices, "batch1")
        os.makedirs(nested)
        open(os.path.join(nested, "deep.qvp"), "w").close()
        displays = [d for d, _ in list_prompt_files([self.voices])]
        self.assertIn("voices/batch1/deep.qvp", displays)

    def test_missing_dir_is_ignored(self):
        self.assertEqual(list_prompt_files([os.path.join(self.root, "nope")]), [])


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


class DetectSourceKindTests(unittest.TestCase):
    def test_qvp_is_a_prompt(self):
        self.assertEqual(detect_source_kind("voices/柳如烟.qvp"), SOURCE_PROMPT)

    def test_qvp_extension_is_case_insensitive(self):
        self.assertEqual(detect_source_kind("voices/A.QVP"), SOURCE_PROMPT)

    def test_audio_extensions(self):
        for name in ("a.wav", "a.mp3", "a.flac", "a.ogg", "a.m4a"):
            self.assertEqual(detect_source_kind(name), SOURCE_AUDIO, name)

    def test_no_extension_is_a_stem(self):
        self.assertEqual(detect_source_kind("my_voice"), SOURCE_STEM)
        self.assertEqual(detect_source_kind(""), SOURCE_STEM)

    def test_prompt_extensions_exported(self):
        self.assertEqual(PROMPT_EXTENSIONS, (".qvp",))


class ResolveVoiceSourceTests(unittest.TestCase):
    """A `.qvp` path must load the prompt, never silently fall back to audio."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.models = os.path.join(self.root, "models")
        self.voices = os.path.join(self.models, "qwen-tts", "voices")
        os.makedirs(self.voices)

    def tearDown(self):
        self.tmp.cleanup()

    def _touch(self, name):
        path = os.path.join(self.voices, name)
        open(path, "w").close()
        return path

    def _json(self, stem, payload):
        import json

        with open(os.path.join(self.voices, stem + ".json"), "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def test_qvp_absolute_path_is_a_prompt(self):
        qvp = self._touch("hero.qvp")
        voice = resolve_voice_source(qvp, [self.voices], self.models)
        self.assertEqual(voice.path, os.path.abspath(qvp))
        self.assertEqual(voice.kind, SOURCE_PROMPT)
        self.assertTrue(voice.is_prompt)
        self.assertFalse(voice.is_audio)

    def test_wav_absolute_path_is_audio(self):
        wav = self._touch("hero.wav")
        voice = resolve_voice_source(wav, [self.voices], self.models)
        self.assertEqual(voice.kind, SOURCE_AUDIO)
        self.assertTrue(voice.is_audio)

    def test_bare_stem_prefers_qvp_over_audio(self):
        wav = self._touch("hero.wav")
        qvp = self._touch("hero.qvp")
        voice = resolve_voice_source("hero", [self.voices], self.models)
        self.assertEqual(voice.path, os.path.abspath(qvp))
        self.assertNotEqual(voice.path, os.path.abspath(wav))

    def test_bare_stem_falls_back_to_audio(self):
        wav = self._touch("hero.wav")
        voice = resolve_voice_source("hero", [self.voices], self.models)
        self.assertEqual(voice.path, os.path.abspath(wav))
        self.assertEqual(voice.kind, SOURCE_AUDIO)

    def test_qvp_ref_text_comes_from_sidecar_json(self):
        qvp = self._touch("hero.qvp")
        self._json("hero", {"ref_text": "参考文本"})
        voice = resolve_voice_source(qvp, [self.voices], self.models)
        self.assertEqual(voice.ref_text, "参考文本")

    def test_dropdown_label_form_resolves_qvp(self):
        self._touch("hero.qvp")
        voice = resolve_voice_source("voices/hero.qvp", [self.voices], self.models)
        self.assertEqual(voice.kind, SOURCE_PROMPT)

    def test_missing_stem_lists_extensions(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            resolve_voice_source("ghost", [self.voices], self.models)
        self.assertIn(".qvp", str(ctx.exception))
        self.assertIn(".wav", str(ctx.exception))

    def test_missing_path_lists_directories(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            resolve_voice_source("voices/ghost.qvp", [self.voices], self.models)
        self.assertIn(self.voices, str(ctx.exception))

    def test_empty_input_raises_value_error(self):
        with self.assertRaises(ValueError):
            resolve_voice_source("   ", [self.voices], self.models)

    def test_quotes_and_whitespace_are_stripped(self):
        qvp = self._touch("hero.qvp")
        voice = resolve_voice_source(f'  "{qvp}"  ', [self.voices], self.models)
        self.assertEqual(voice.path, os.path.abspath(qvp))

    def test_stem_without_models_dir_still_matches_directory(self):
        qvp = self._touch("hero.qvp")
        voice = resolve_voice_source("hero", [self.voices])
        self.assertEqual(voice.kind, SOURCE_PROMPT)
        self.assertEqual(voice.path, os.path.abspath(qvp))

    def test_describe_source_names_the_kind(self):
        qvp = self._touch("hero.qvp")
        wav = self._touch("other.wav")
        self.assertIn("saved prompt", describe_source(resolve_voice_source(qvp, [], "")))
        self.assertIn("reference audio", describe_source(resolve_voice_source(wav, [], "")))


class SubfolderTests(unittest.TestCase):
    """voices saved with SaveVoice(subfolder=...) must be listable and loadable."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.voices = os.path.join(self.root, "voices")
        self.nested = os.path.join(self.voices, "verify", "batch1")
        os.makedirs(self.nested)
        open(os.path.join(self.voices, "top.wav"), "w").close()
        open(os.path.join(self.nested, "saved_probe.wav"), "w").close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_recursive_listing_includes_subfolders(self):
        displays = [d for d, _ in list_voice_files([self.voices])]
        self.assertEqual(displays, ["voices/top.wav", "voices/verify/batch1/saved_probe.wav"])

    def test_non_recursive_listing_skips_subfolders(self):
        displays = [d for d, _ in list_voice_files([self.voices], recursive=False)]
        self.assertEqual(displays, ["voices/top.wav"])

    def test_resolve_label_with_nested_path(self):
        path = resolve_input_path(
            "voices/verify/batch1/saved_probe.wav", [self.voices], self.root
        )
        self.assertEqual(path, os.path.abspath(os.path.join(self.nested, "saved_probe.wav")))

    def test_resolve_plain_relative_path(self):
        path = resolve_input_path(
            "verify/batch1/saved_probe.wav", [self.voices], self.root
        )
        self.assertEqual(path, os.path.abspath(os.path.join(self.nested, "saved_probe.wav")))


if __name__ == "__main__":
    unittest.main()
