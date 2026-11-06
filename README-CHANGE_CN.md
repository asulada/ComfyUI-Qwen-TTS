# 本仓库的 README 变更

[English](README-CHANGE.md) | 中文版 · [返回 README](README.md)

本仓库 fork 自 [flybirdxx/ComfyUI-Qwen-TTS](https://github.com/flybirdxx/ComfyUI-Qwen-TTS)。
`README.md` / `README_CN.md` 保持与上游一致，方便日后同步上游而不产生冲突；本仓库新增或修改的
内容统一记录在这里。

- **上游基线**：`a1328c8`（2026-09-22，"Merge pull request #109 from JWLHS/codex/xpu-adaptation"）
- **本仓库新增**：`EmotionalTTSNode`；`DialogueInferenceNode` 的 `instruct` / `speed` / 内联标记；
  `SaveVoice` / `LoadSpeaker` 多目录声音库
- **设计结论**：见 `docs/DECISIONS.md`；代码见 `emotion_utils.py`、`voice_store.py`、`nodes.py`
- **上游更新日志** `doc/update.md` 同样保持原样；本仓库的变更历史记录在 `docs/DECISIONS.md` 与下文

> 以下内容按拆分前在 `README_CN.md` 中出现的顺序排列。中文 README 的改动比英文版更多
> （还包含更新日志、功能要点、声音库目录章节与最佳实践），因此两份变更记录的条目并不一一对应。

## 顶部：transformers 版本要求

上游中文 README 写的是「与 `transformers >= 5.0` **不兼容**」，本仓库已支持 v5，该段整块替换为：

> **⚠️ 重要提醒：transformers 版本要求**
>
> Qwen3-TTS 支持 **transformers 4.57.3** 以及 **transformers >= 5.0**。v5.0+ 的兼容性由 `tools/transformers5_shim.py` 提供，并在导入时自动应用；在 transformers < 5 上这些补丁为空操作，4.57.3 路径的行为保持不变：
> ```bash
> pip install transformers==4.57.3   # v4 路径（补丁不生效）
> # 或
> pip install "transformers>=5.0"    # v5 路径（自动应用补丁）
> ```
> 请勿使用 4.57.3 与 5.0 之间的其他版本（例如 4.58.x）。

（英文 README 上游已包含等价说明，本仓库无需改动。）

## 更新日志：新增条目

在 `## 📋 更新日志` 首条之前加一行：

- **2026-10-17**: 新增 `EmotionalTTSNode`（情感预设 / 句内情感切换 / 内联停顿 / 语速）；三个 TTS 节点与多角色对话节点支持 `speed`；`DialogueInferenceNode` 补上 `instruct`；`SaveVoice` / `LoadSpeaker` 支持多目录
- **2026-11-06**: 音色可直接按路径指定（`.qvp` 一等公民）：`VoiceClone` / `EmotionalTTS` / `VoiceClonePrompt` 新增 `ref_voice_path`，`RoleBank` 新增 `voice_path_1..8`，`LoadSpeaker.file_path` 支持 `.qvp` 与裸名

## 功能特性：新增两条

在 `## 功能特性` 列表末尾追加：

- 🎭 **情感与语速**: 提供情感预设与内联标记（`[sad]` / `[pause:800ms]` / `[rate:1.2]`），并可对任意节点做保音高变速。
- 📚 **多目录声音库**: `SaveVoice` / `LoadSpeaker` 可读写多个目录，支持 `extra_model_paths.yaml` 与环境变量。
- 🔗 **按路径选音色**: 所有需要参考音色的节点都能直接填 `.qvp` 或音频文件路径，不必中转 `LoadSpeaker`。

## 音色路径输入（本次新增）

上游没有「按路径指定音色」的输入，只有 `AUDIO` / `VOICE_CLONE_PROMPT` 连线。本仓库补上字符串路径输入：

| 节点 | 新增输入 | 覆盖对象 |
|------|----------|----------|
| `VoiceCloneNode` | `ref_voice_path` | `ref_audio` 与 `voice_clone_prompt` |
| `EmotionalTTSNode` | `ref_voice_path` | `voice_clone_prompt` |
| `VoiceClonePromptNode` | `ref_voice_path` | `ref_audio` |
| `RoleBankNode` | `voice_path_1..8` | 对应角色的 `prompt_N` |
| `LoadSpeakerNode` | `prompt_file`（下拉） | `filename`（音频下拉） |
| `LoadSpeakerNode` | `file_path`（语义扩展） | 两个下拉 |

**`LoadSpeaker` 的两个下拉**

- `prompt_file`: 扫描到的 `.qvp`，默认 `None`。**优先于 `filename`**——`.qvp` 就是保存好的 prompt 本身，直通加载、不重编码；
- `filename`: 音频下拉。**已被 `.qvp` 覆盖的音色会从这个下拉里隐藏**，避免同一个音色出现两条、用户还得猜哪条生效；
- 取值优先级: `file_path` > `prompt_file` > `filename`。默认值 `"None"` 会被当作空值滤掉，因此旧工作流只选 `filename` 时行为完全不变。

**接受的形式**

1. `.qvp` 绝对路径或相对路径 —— 直接当 prompt 加载，**不加载模型、不重新编码**，音色与当初 `SaveVoice` 保存的逐位一致；
2. 音频文件（`.wav` / `.mp3` / `.flac` / `.ogg` / `.m4a`）—— 解码后调 `create_voice_clone_prompt` 提取；
3. `<目录标签>/<文件名>`（下拉框的值）；
4. 裸名（不含扩展名），按 `.qvp` → 音频的顺序在扫描目录中查找。

**优先级**: 路径非空即生效，并忽略对应节点上的连线，日志会打印一行 `ℹ️ ... ignoring the connected ...`，避免工作流里残留的旧连线悄悄盖掉手填路径。

**`.qvp` 优先于同名音频**: 如果指向音频而旁边存在同名 `.qvp`，`LoadSpeaker` 会读该 `.qvp`。反过来，明确指向 `.qvp` 时不会回落到音频——否则保存时的音色会被无声替换。

**没有 `ref_text` 时**: 音频在 ICL 模式下需要参考文本。填路径时没有地方写文本，若旁边没有同名 `.json`，节点会提示并改用 `x_vector_only`（仅说话人向量）模式。想保住 ICL 质量，请改填 `.qvp`——它自带 `ref_text`。

**`ref_audio` 的位置变化**: `VoiceClonePromptNode` 的 `ref_audio` 从 `required` 移到 `optional`，否则只填路径时节点无法执行。已有工作流把 `ref_audio` 连线后行为不变。


## 节点列表（§6–§9）

### 6. Qwen3-TTS 多角色对话 (`DialogueInferenceNode`) — 新增输入

在 `batch_size` 之后追加：

- `instruct`: 适用于所有台词的风格指令（例如："低声耳语，语速缓慢"）。**0.6B 模型会忽略该参数。**
- `speed`: 语速倍率（保音高）。1.0 为模型原生语速，配置好的停顿时长不会随之缩放。
- **内联标记**: 每行台词支持与 `EmotionalTTS` 相同的标记语法（`[sad]` / `[style:...]` / `[pause:800ms]` / `[rate:1.2]`）。
  解析顺序是**先解析标记、再按标点切分**，因此粘滞状态（情感 / 风格 / 语速）会跨句号、逗号继续生效；
  **同一角色可以在一行内切换情感**，而音色（`voice_clone_prompt`）保持不变。
  `[rate:x]` 逐片段生效，优先于节点级 `speed`。
  行首的 `[break=...]` 已废弃，改用 `[pause:...]`。

> ⚠️ 节点级 `instruct` 是**全局**的：它会被拼接到每一行、每个角色的指令末尾。
> 多角色剧本里，低音的中年角色和高音的少年角色无法共用同一句描述。
> 请改用下文的**每角色声线卡**，或把描述写进行内的 `[style:...]`。

### 4. Qwen3-TTS 角色银行 (`RoleBankNode`) — 新增每角色声线卡

> 对应上游 §4。此处列出变更内容，实际插入位置仍是上游 §4。

为每个角色新增一个 `instruct_{i}` 输入（多行文本框），在 `role_name_i` / `prompt_i` 之后追加：

- `instruct_{i}`: 该角色的声线卡，例如「二十出头，中高音区，音色清亮，语速中等」。
  **应用到该角色说出的每一行**，无需在脚本里重复书写。留空则回落到节点级 `instruct`。

组合顺序为：情感预设 → 行内 `[style:...]` → **声线卡** → 节点级 `instruct`，
越靠后越具体、优先级越高。

未填写声线卡的角色，`role_bank` 中仍是原来的裸 prompt，**旧工作流无需改动**。

> 无论是否填写声线卡，`role_bank` 里每个角色存的都是**单条** prompt，
> 两条路径的取值形状一致；声线卡只影响 `instruct` 文本，不影响 prompt 本身。

### 7. Qwen3-TTS 情感合成 (`EmotionalTTSNode`) [新增] — 新增章节

插入为 §7（即原「加载声音」之前），上游的 §7 / §8（加载声音 / 保存声音）顺延为 §8 / §9。整节内容：

在预设音色上叠加情感、句内情感切换、停顿与语速控制。

> ⚠️ Qwen3-TTS **没有**原生的 `emotion` / `steer_weight` / `rate` 参数，也没有内置情感预设表或 `[excited]` 之类的情感标签。本节点在推理接口之上实现等价能力，因此效果是"指令引导 + 后处理"，而非引擎级情感模型。

- **输入**:
  - `text`: 台词，支持内联标记（见下）。
  - `speaker`: 预设音色。
  - `emotion`: 全局情感预设（`happy / sad / angry / whisper / weak / tender / thoughtful / excited / dramatic / news / calm / fearful / gentle / serious`），默认 `none`。
  - `steer_weight`: 情感强度 0–2，1.0 为预设原强度，>1 放大、<1 减弱。
  - `speed`: 全局语速倍率（保音高），内联 `[rate:x]` 可按段覆盖。
  - `model_choice`: **必须 1.7B**——0.6B 的 CustomVoice 会丢弃 `instruct`，情感无法生效（节点会直接报错）。
  - `voice_clone_prompt`: 可选，接入参考音色（来自 `VoiceClonePromptNode` / `LoadSpeakerNode`）。接入后自动切换到 **Base** 模型，此时 `speaker` 被忽略；情感仍按段生效。
  - `instruct`: 追加到每段指令后的补充描述。
  - `linebreak_pause`: 每个换行对应的停顿时长。
  - `scale_pauses_with_speed`: 是否让停顿时长也随语速缩放（默认关闭，避免加速后戏剧性停顿被吃掉）。
  - `batch_size`: 每批同时生成的片段数。
- **内联标记**:
  | 标记 | 作用 | 说明 |
  |------|------|------|
  | `[sad]` `[低语]` `[emotion:tender]` | 切换情感 | **粘滞**，对后续文本持续生效，直到下一个标签 |
  | `[none]` | 清除情感 | 回到无指令状态 |
  | `[style:冷笑着压低声音]` `[instruct:...]` | 自由风格描述 | **粘滞**；括号内文字直接并入该段 instruct，不受预设表限制 |
  | `[pause:800ms]` `[pause:1.2s]` | 插入静音 | 附着到前一段之后；出现在开头则成为前置停顿 |
  | `[rate:1.2]` | 切换语速 | 同样粘滞，只影响其后的片段 |
- **未知标签**: 默认剥离（否则模型会把方括号念出来），并在日志中提示被丢弃的标签。
  想写预设表以外的风格请用 `[style:...]`。需要保留原样可设 `preserve_unknown_tags=True`。
- **已废弃**: `[break=0.5]` 不再解析，会被剥离并提示改用 `[pause:0.5s]`。
- **示例**:
  ```text
  [sad]他走了。[pause:800ms]再也不会回来了。
  [whisper]别出声……[pause:1s][tender]我只是想再看看你。
  [style:像是在跟老朋友聊天，随性一点]其实我早就知道了。
  ```
- **能力**: 适合有声书、角色独白等需要句内情绪起伏的场景；情感切换通过分段生成实现，段与段之间为硬拼接（存在轻微音色/气息跳变）。

### 8. Qwen3-TTS 加载声音 (`LoadSpeakerNode`) [新增] — 编号 + 输入

上游标题为 `### 7.`，因为 §7 被 `EmotionalTTSNode` 占用而顺延；原来的一行
「**输入**: 选择已保存的 `.wav` 文件。」替换为：

- **输入**:
  - `filename`: 扫描到的音频音色，显示为 `<目录标签>/<文件名>`，同名音色也能区分。已被 `.qvp` 覆盖的音色不在此列表（改在 `prompt_file` 里选）。
  - `prompt_file`（可选）: 扫描到的 `.qvp`，默认 `None`。**优先于 `filename`**，选中即直通加载。
  - `directory`（可选）: 额外扫描的目录。可填绝对路径，或相对 `models/qwen-tts` 的路径；下拉列表在下次加载工作流时生效。
  - `file_path`（可选）: 优先于两个下拉，接受 `.qvp` 路径、音频路径、`<目录标签>/<文件名>`，或不含扩展名的裸名（`.qvp` 优先于音频）。用于不等刷新就加载刚保存的音色。
- **取值优先级**: `file_path` > `prompt_file` > `filename`。
- **`.qvp` 直接加载**: 填 `.qvp` 时不再走 `librosa.load`，而是 `torch.load` 出 prompt 直接返回，同目录的 `.wav` 只用于 `audio` 预览输出（没有就返回空 `AUDIO`，不报错）。
- **扫描顺序**: `models/qwen-tts/voices` → 所有注册为 `qwen-tts` 的根目录（含 `extra_model_paths.yaml`，同时探测根目录与其 `voices/` 子目录）→ 环境变量 `QWEN_TTS_VOICE_DIRS`（用 `os.pathsep` 分隔）→ 节点自身的 `directory`。

### 9. Qwen3-TTS 保存声音 (`SaveVoiceNode`) [新增] — 编号 + 输入

上游标题为 `### 8.`，同样顺延；描述之后追加：

- **输入**:
  - `output_dir`（可选）: 留空保持原有的 `models/qwen-tts/voices`；相对路径会落在 `models/qwen-tts/` 下；绝对路径原样使用。目录不存在会自动创建。
  - `subfolder`（可选）: `output_dir` 内的子目录，例如 `audiobook/ch1`。
  - `overwrite`（可选）: 关闭后同名音色已存在时报错而不是覆盖。
  - `instruct`（可选）: 声线卡（音区/音色/语速）。**写进 `.qvp`**，加载时自动恢复，因为 prompt 本身装不下风格文本。

**加载时如何合并 `.qvp` 的卡与手填的 instruct**

两者**拼接**而非互相覆盖，卡在前、手填在后：

```text
最终 instruct = <卡>，<手填>
例：二十出头，中高音区，音色清亮，语速中等，这一句要压低声音
```

- 覆盖会让其中一方静默消失——卡的音高/音色和手填的本次风格都影响听感，丢任一个都会改变声音；
- 卡在前是因为它是音色的基线，手填是本次的细化，放在最后（模型对靠后的描述权重更高）；
- 完全重复时不重复拼接：若手填已包含卡、或卡已包含手填，则保留较长的那个，避免「中高音区，中高音区」；
- `DialogueInference` 同理：`.qvp` 的卡与该角色的 `instruct_N` 拼接，`instruct_N` 在后。
  - `ref_text`（可选）: 留空 = 保留 prompt 里的转写。**`.qvp` 内嵌值为准**：`VoiceClonePromptItem` 自带它被构建时用的转写，那才是模型实际条件过的文本；手填值只有在 prompt 没有转写时才写入，两者不同会打印警告。

**`.qvp` 的存储格式**

- 新格式是 package dict：`{"prompt": ..., "ref_text": ..., "instruct": ..., "source": ..., "version": "1.2"}`；
- 旧格式（裸 prompt，无 `ref_text` / `instruct`）**仍可读取**，此时回落到同名 `.json`；
- 读取优先级统一为「`.qvp` 内嵌值 → 同名 `.json` → 空」。`.json` 降级为纯摘要/兜底，不再是权威来源。

## 新增「声音库目录」小节

在 `## 安装` 的模型目录结构之后、`extra_model_paths.yaml` 提示之前插入（该提示同时被改写为
`### extra_model_paths.yaml 示例` 小节）：

### 声音库目录

`SaveVoice` / `LoadSpeaker` 会按以下顺序扫描并合并音色，无需只依赖一个目录：

1. `models/qwen-tts/voices`（默认，优先级最高）
2. 所有注册为 `qwen-tts` 的根目录（含 `extra_model_paths.yaml`），同时探测根目录本身与其 `voices/` 子目录
3. 环境变量 `QWEN_TTS_VOICE_DIRS`，多个路径用系统路径分隔符（Windows 为 `;`，Linux/macOS 为 `:`）
4. `LoadSpeakerNode` 上的 `directory` 输入

```bash
# 例：把额外两个声音库加入扫描
export QWEN_TTS_VOICE_DIRS="/data/voices-a:/data/voices-b"   # Windows 用 set 并以 ; 分隔
```

保存时用 `output_dir` 指定目标目录（留空 = 默认目录，相对路径落在 `models/qwen-tts/` 下，绝对路径原样使用），`subfolder` 可再分一层子目录。加载时下拉框只提供 `<目录标签>/<文件名>`，同名文件不会混淆；`file_path` 可直接填入绝对路径，无需等待下拉刷新。

新增或删除音色后，下拉列表在**下次执行任务时**刷新（ComfyUI 每次提交都会重新调用 `INPUT_TYPES()`），不需要重启服务。但工作流里已经保存的旧值不会自动改写：若那个音色已被删除，任务会因 `Value not in list` 失败，重新选一个即可。

### `extra_model_paths.yaml` 示例

```yaml
qwen-tts: D:\MyAI\Models\Qwen
```

该根目录下的 `voices/` 子目录（以及根目录本身）都会自动纳入声音扫描，因此放在这里的音色无需额外配置。

## 最佳实践：新增段落

`### 对话生成` 中的「暂停」一条（上游原文为「调整 `pause_seconds` 以控制对话段之间的 timing。」）
改为：

- **暂停**: 使用 `pause_linebreak` / `period_pause` / `comma_pause` 等控制句间与标点停顿。

并在其后追加两条：

- **风格**: 用 `instruct` 给整段对话指定统一语气（0.6B 会忽略该参数）。
- **语速**: `speed` 只改变语音本身，已配置的停顿时长保持不变。

其后新增两节：

### 情感与语速
- **先写指令，再调 `speed`**：情感、情绪和快慢建议优先用 `instruct` / 情感预设表达，`speed` 只做小幅微调。
- **低语要谨慎加速**：气声能量集中在噪声上，时间伸缩最容易产生水下感或金属感，建议控制在 0.95–1.05。
- **悲伤 / 沉思靠停顿**：这类情绪依赖拖音与停顿，加速会让听感从"沉"变"急"，可保持 `scale_pauses_with_speed` 关闭。
- **0.6B 不遵循 instruct**：CustomVoice 0.6B 会直接丢弃该参数，情感相关用法请选 1.7B 或使用参考音色（Base 模型）。
- **参考音色与情感可共存**：`EmotionalTTSNode` 接入 `voice_clone_prompt` 后会切到 Base 模型，情感仍按段生效，但模型会在 CustomVoice / Base 之间重新加载。

### 声音库
- **多目录**：用 `QWEN_TTS_VOICE_DIRS` 或 `extra_model_paths.yaml` 组织多个声音库，避免把所有音色塞进同一个目录。
- **子目录归档**：保存时用 `subfolder`（如 `audiobook/ch1`）分组，加载时按 `<目录标签>/<文件名>` 选择。
- **防覆盖**：批量生成时把 `overwrite` 关掉，重名会直接报错而不是静默覆盖旧样本。

### 音色路径
- **优先填 `.qvp`，不要填音频**：`.qvp` 是当初保存的 prompt 本身，加载时既不重编码也不会漂移；填音频会重新提取，参考文本缺失时还会退化成仅说话人向量模式。
- **路径会盖掉连线**：同一节点上既有连线又填了路径时用路径，并在日志里说明；若发现音色不对，先检查是不是忘了清空 `ref_voice_path`。
- **一部剧一个 `.qvp`**：`VoiceClone` / `EmotionalTTS` / `VoiceClonePrompt` 都能直接填同一条路径，无需为每个节点再挂一个 `LoadSpeaker`。
- **多角色用 `voice_path_N`**：在 `RoleBankNode` 里给每个角色填 `.qvp`，`DialogueInference` 会按角色各解析一次，200 行的脚本也只有一次加载成本。
