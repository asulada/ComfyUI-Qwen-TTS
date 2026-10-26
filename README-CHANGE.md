# README Changes in This Fork

English | [中文版](README-CHANGE_CN.md) · [Back to README](README.md)

This repository is a fork of [flybirdxx/ComfyUI-Qwen-TTS](https://github.com/flybirdxx/ComfyUI-Qwen-TTS).
`README.md` and `README_CN.md` are kept verbatim to upstream so they can be re-synced without
conflicts; everything this fork adds or changes is documented here instead.

- **Upstream baseline**: `a1328c8` (2026-09-22, "Merge pull request #109 from JWLHS/codex/xpu-adaptation")
- **This fork adds**: the `EmotionalTTSNode`, `instruct` / `speed` / inline markup for
  `DialogueInferenceNode`, and a multi-directory voice library for `SaveVoice` / `LoadSpeaker`
- **Design conclusions** (Chinese): `docs/DECISIONS.md`; code: `emotion_utils.py`, `voice_store.py`, `nodes.py`
- **Upstream changelog** `doc/update.md` is left untouched for the same reason; this fork's
  history lives in `docs/DECISIONS.md` and in the sections below

> The text below is this fork's wording, in the order it appeared in `README.md` before the split.
> The Chinese README carried additional fork sections (changelog entry, feature bullets,
> a voice-library directory section and extra best-practice notes); see
> [README-CHANGE_CN.md](README-CHANGE_CN.md).

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
  - `filename`: Every voice found in the scanned directories, shown as `<label>/<file>` so two libraries with the same filename stay distinguishable.
  - `directory` (optional): An extra directory to scan. Absolute, or relative to `models/qwen-tts`. It affects the dropdown after the next workflow reload.
  - `file_path` (optional): An absolute path or `<label>/<file>` that overrides the dropdown — use it to load a just-saved voice without reloading.
- **Scanned directories**, in order: `models/qwen-tts/voices`, every root registered for the `qwen-tts` folder type (including `extra_model_paths.yaml`, checking both the root and its `voices/` child), each path in `QWEN_TTS_VOICE_DIRS` (`os.pathsep`-separated), then the node's own `directory`.

### 9. Qwen3-TTS Save Voice (`SaveVoiceNode`) [New] — heading number + inputs

Upstream heading was `### 8.`, shifted for the same reason. After the one-line description:

- **Inputs**:
  - `output_dir` (optional): Empty keeps the historical `models/qwen-tts/voices`. A relative value goes under `models/qwen-tts/`, an absolute value is used as-is. The directory is created when missing.
  - `subfolder` (optional): A sub-directory inside `output_dir`, e.g. `audiobook/ch1`.
  - `overwrite` (optional): Refuse to clobber an existing voice when disabled.
