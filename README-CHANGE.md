# README Changes in This Fork

English | [中文版](README-CHANGE_CN.md) · [Back to README](README.md)

This repository is a fork of [flybirdxx/ComfyUI-Qwen-TTS](https://github.com/flybirdxx/ComfyUI-Qwen-TTS).
`README.md` and `README_CN.md` are kept verbatim to upstream so they can be re-synced without
conflicts; everything this fork adds or changes is documented here instead.

- **Upstream baseline**: `a1328c8` (2026-09-22, "Merge pull request #109 from JWLHS/codex/xpu-adaptation")
- **This fork adds**: the `EmotionalTTSNode`, `instruct` / `speed` / inline markup for
  `DialogueInferenceNode`, a multi-directory voice library for `SaveVoice` / `LoadSpeaker`, and
  path-based voice inputs (`ref_voice_path` / `voice_path_N`) that accept a saved `.qvp`
- **Design conclusions** (Chinese): `docs/DECISIONS.md`; code: `emotion_utils.py`, `voice_store.py`, `nodes.py`
- **Upstream changelog** `doc/update.md` is left untouched for the same reason; this fork's
  history lives in `docs/DECISIONS.md` and in the sections below

> The text below is this fork's wording, in the order it appeared in `README.md` before the split.
> The Chinese README carried additional fork sections (changelog entry, feature bullets,
> a voice-library directory section and extra best-practice notes); see
> [README-CHANGE_CN.md](README-CHANGE_CN.md).

## Voice paths

Upstream only accepts wired inputs (`AUDIO` / `VOICE_CLONE_PROMPT`). This fork adds string path
inputs so a voice can be named in the node itself:

| Node | New input | Replaces |
|------|-----------|----------|
| `VoiceCloneNode` | `ref_voice_path` | `ref_audio` and `voice_clone_prompt` |
| `EmotionalTTSNode` | `ref_voice_path` | `voice_clone_prompt` |
| `VoiceClonePromptNode` | `ref_voice_path` | `ref_audio` |
| `RoleBankNode` | `voice_path_1..8` | that role's `prompt_N` |
| `LoadSpeakerNode` | `prompt_file` (dropdown) | `filename` (audio dropdown) |
| `LoadSpeakerNode` | `file_path` (extended) | the dropdowns |

**`LoadSpeaker`'s two dropdowns**

- `prompt_file`: scanned `.qvp` files, default `None`. **Outranks `filename`** because a prompt *is*
  the saved prompt and loads without re-encoding.
- `filename`: the audio dropdown. Voices already covered by a `.qvp` are hidden here, so the same
  voice never appears twice and the user never has to guess which entry wins.
- Precedence: `file_path` > `prompt_file` > `filename`. The `"None"` placeholder is filtered out
  as empty, so a workflow that only ever used `filename` behaves exactly as before.

Accepted forms:

1. a `.qvp` path — loaded as the prompt directly, **no model load, no re-encoding**, so the
   timbre is bit-for-bit what `SaveVoice` stored;
2. an audio file (`.wav` / `.mp3` / `.flac` / `.ogg` / `.m4a`) — decoded and encoded into a prompt;
3. `<label>/<file>` (the dropdown form);
4. a bare name without extension, resolved against the scanned directories, `.qvp` first.

A non-empty path wins over the wired input, and the log prints
`ℹ️ ... ignoring the connected ...` so a leftover link cannot silently override a hand-typed path.

`.qvp` beats same-named audio: pointing at a `.wav` whose sibling `.qvp` exists still loads the
`.qvp`. The reverse never happens — pointing at a `.qvp` never falls back to audio, which would
swap the saved timbre out without saying so.

**Missing `ref_text`**: audio needs a transcript in ICL mode. A path input has nowhere to put one,
so when no sibling `.json` exists the node warns and switches to `x_vector_only` (speaker
embedding only). Use the `.qvp` when ICL quality matters — it carries `ref_text` with it.

**`ref_audio` moved**: in `VoiceClonePromptNode` it is now `optional` instead of `required`;
otherwise a path-only run could not execute. Workflows that connect it behave exactly as before.


## Nodes List (§6–§9)

### 6. Qwen3-TTS Multi-role Dialogue (`DialogueInferenceNode`) — added inputs

Append after `batch_size`:

- `instruct`: Style instruction applied to every line (e.g. "whispering, very slow"). **The 0.6B model ignores this.**
- `speed`: Speech rate multiplier (pitch-preserving). 1.0 is the model's native pace; configured pauses are not scaled.
- **Inline markup**: Every script line accepts the same markup as `EmotionalTTS` (`[sad]` / `[style:...]` / `[pause:800ms]` / `[rate:1.2]`). Markup is resolved **before** the punctuation split, so sticky state (emotion / style / rate) carries across periods and commas, and **one role can change emotion inside a line** while its timbre (`voice_clone_prompt`) stays fixed. `[rate:x]` applies per fragment and overrides the node-level `speed`. A leading `[break=...]` is deprecated; use `[pause:...]`.

> ⚠️ The node-level `instruct` is **global**: it is appended to every line of every
> role. In a multi-role script, a low-pitched middle-aged character and a bright
> teenager cannot share one description. Use the per-role voice card below, or put
> the wording into an inline `[style:...]` tag instead.

### 4. Qwen3-TTS Role Bank (`RoleBankNode`) — per-role voice card

> Refers to upstream §4; only the changed inputs are listed here.

Add an `instruct_{i}` input (multiline) after `role_name_i` / `prompt_i`:

- `instruct_{i}`: this role's voice card, e.g. "early twenties, mid-high pitch,
  bright timbre, medium pace". Applied to **every line that role speaks**, so it
  does not have to be retyped per line. Leave empty to fall back to the
  node-level `instruct`.

Composition order is: emotion preset → inline `[style:...]` → **voice card** →
node-level `instruct`, later entries being more specific and taking precedence.

Roles without a card keep the bare prompt in `role_bank`, so **existing workflows
need no changes**.

> Either way a role stores a **single** prompt; the card only contributes text to
> `instruct` and never changes the prompt's shape.

### 7. Qwen3-TTS Emotional TTS (`EmotionalTTSNode`) [New] — new section

Insert as §7, i.e. before Load Speaker; the upstream §7 / §8 (Load Speaker / Save Voice)
become §8 / §9. Full section text:

Layer emotion presets, in-sentence emotion switching, pauses and rate control onto a preset speaker.

> ⚠️ Qwen3-TTS has **no** native `emotion` / `steer_weight` / `rate` arguments, no built-in emotion preset table, and no `[excited]`-style emotion tags. This node implements equivalent behaviour on top of the existing inference API, so the result is "instruction-guided + post-processing" rather than an engine-level emotion model.

- **Inputs**:
  - `text`: Script with optional inline markup (see below).
  - `speaker`: Preset voice.
  - `emotion`: Global preset (`happy / sad / angry / whisper / weak / tender / thoughtful / excited / dramatic / news / calm / fearful / gentle / serious`), default `none`.
  - `steer_weight`: Emotion intensity 0–2. 1.0 = preset as written, >1 amplifies, <1 softens.
  - `speed`: Global rate multiplier (pitch-preserving); inline `[rate:x]` overrides per segment.
  - `model_choice`: **Must be 1.7B** — the 0.6B CustomVoice model discards `instruct`, so emotion cannot take effect (the node raises instead of silently ignoring it).
  - `voice_clone_prompt`: Optional reference timbre (from `VoiceClonePromptNode` / `LoadSpeakerNode`). Connecting it switches to the **Base** model and makes `speaker` inactive; emotions still apply per segment.
  - `instruct`: Extra description appended to every segment's instruction.
  - `linebreak_pause`: Silence inserted for each newline.
  - `scale_pauses_with_speed`: Also scale silences with the rate (default off, so dramatic pauses survive a faster delivery).
  - `batch_size`: Segments generated per model call.
- **Inline markup**:
  | Markup | Effect | Notes |
  |--------|--------|-------|
  | `[sad]` `[whisper]` `[emotion:tender]` | Switch emotion | **Sticky**: applies to all following text until changed |
  | `[none]` | Clear emotion | Back to no instruction |
  | `[style:laughing under the breath]` `[instruct:...]` | Free-form style | **Sticky**; the text is merged into that segment's instruction, no preset table involved |
  | `[pause:800ms]` `[pause:1.2s]` | Insert silence | Attached after the previous segment; at the start it becomes a leading pause |
  | `[rate:1.2]` | Switch rate | Also sticky; affects only following segments |
- **Unknown tags**: stripped by default (otherwise the model reads the brackets aloud) and reported in the log. Use `[style:...]` for anything the preset table does not cover. `preserve_unknown_tags=True` keeps them verbatim.
- **Deprecated**: `[break=0.5]` is no longer parsed; it is stripped with a hint to use `[pause:0.5s]`.
- **Example**:
  ```text
  [sad]He left.[pause:800ms]He's never coming back.
  [whisper]Don't make a sound...[pause:1s][tender]I just wanted to see you once more.
  [style:as if chatting with an old friend]I knew it all along.
  ```
- **Capabilities**: Suited to audiobooks and character monologues that need emotion shifts inside one scene. Shifts are realized by generating segments separately, so joins are hard cuts (minor timbre/breath discontinuity possible).

### 8. Qwen3-TTS Load Speaker (`LoadSpeakerNode`) [New] — heading number + inputs

Upstream heading was `### 7.`; it moves down one slot because §7 is taken by `EmotionalTTSNode`.
After the one-line description:

- **Inputs**:
  - `filename`: Scanned audio voices, shown as `<label>/<file>` so two libraries with the same filename stay distinguishable. Voices covered by a `.qvp` are not listed here — pick those in `prompt_file` instead.
  - `prompt_file` (optional): Scanned `.qvp` prompts, default `None`. **Outranks `filename`** and loads the prompt as-is.
  - `directory` (optional): An extra directory to scan. Absolute, or relative to `models/qwen-tts`. It affects the dropdown after the next workflow reload.
  - `file_path` (optional): Overrides both dropdowns. Accepts a `.qvp` path, an audio path, `<label>/<file>`, or a bare name without extension (`.qvp` preferred over audio) — use it to load a just-saved voice without reloading.
- **Precedence**: `file_path` > `prompt_file` > `filename`.
- **`.qvp` is loaded directly**: it is read with `torch.load` and returned as the prompt; the sibling `.wav` only feeds the `audio` preview output (empty when absent, no error). It is *not* passed to `librosa.load`.
- **Scanned directories**, in order: `models/qwen-tts/voices`, every root registered for the `qwen-tts` folder type (including `extra_model_paths.yaml`, checking both the root and its `voices/` child), each path in `QWEN_TTS_VOICE_DIRS` (`os.pathsep`-separated), then the node's own `directory`.

### 9. Qwen3-TTS Save Voice (`SaveVoiceNode`) [New] — heading number + inputs

Upstream heading was `### 8.`, shifted for the same reason. After the one-line description:

- **Inputs**:
  - `output_dir` (optional): Empty keeps the historical `models/qwen-tts/voices`. A relative value goes under `models/qwen-tts/`, an absolute value is used as-is. The directory is created when missing.
  - `subfolder` (optional): A sub-directory inside `output_dir`, e.g. `audiobook/ch1`.
  - `overwrite` (optional): Refuse to clobber an existing voice when disabled.
  - `instruct` (optional): A voice card (pitch range / timbre / rate). **Stored inside the `.qvp`** and restored on load, because a prompt cannot carry style text.

**How the saved card and a typed instruct are combined**

They are **concatenated**, not one replacing the other, with the card first:

```text
final instruct = <card>，<typed>
e.g. 二十出头，中高音区，音色清亮，语速中等，这一句要压低声音
```

- Replacement would silently drop one description, and both the card's pitch/timbre and the
  run's own style change how a line sounds;
- The card leads because it is the voice's baseline; the typed text lands last, where the
  model weighs it more;
- Exact overlap is not duplicated: if either value already contains the other, the longer one
  is kept, so the model never reads "中高音区，中高音区";
- `DialogueInference` behaves the same way — the `.qvp` card is merged with that role's
  `instruct_N`, typed text last.
  - `ref_text` (optional): Empty keeps the transcript already inside the prompt. **The `.qvp` value wins**: a `VoiceClonePromptItem` carries the transcript it was built with, which is what the model actually conditioned on; a typed value is only stored when the prompt has none, and a mismatch prints a warning.

**`.qvp` on-disk format**

- New files are a package dict: `{"prompt": ..., "ref_text": ..., "instruct": ..., "source": ..., "version": "1.2"}`.
- Legacy files (a bare prompt with no `ref_text` / `instruct`) **still load**; the sidecar `.json` fills the gap.
- Read order is uniform: "value inside the `.qvp`" → "sidecar `.json`" → empty. The `.json` is now a summary/fallback, not the authority.
