# ComfyUI-Qwen-TTS

[English](README.md) | 中文版

> **⚠️ 重要提醒：transformers 版本要求**
>
> Qwen3-TTS 支持 **transformers 4.57.3** 以及 **transformers >= 5.0**。v5.0+ 的兼容性由 `tools/transformers5_shim.py` 提供，并在导入时自动应用；在 transformers < 5 上这些补丁为空操作，4.57.3 路径的行为保持不变：
> ```bash
> pip install transformers==4.57.3   # v4 路径（补丁不生效）
> # 或
> pip install "transformers>=5.0"    # v5 路径（自动应用补丁）
> ```
> 请勿使用 4.57.3 与 5.0 之间的其他版本（例如 4.58.x）。

![节点截图](example/example.png)

基于阿里巴巴 Qwen 团队开源的 **Qwen3-TTS** 项目，为 ComfyUI 实现的语音合成自定义节点。

## 📋 更新日志

- **2026-10-17**: 新增 `EmotionalTTSNode`（情感预设 / 句内情感切换 / 内联停顿 / 语速）；三个 TTS 节点与多角色对话节点支持 `speed`；`DialogueInferenceNode` 补上 `instruct`；`SaveVoice` / `LoadSpeaker` 支持多目录
- **2026-04-12 (v1.0.7)**: 移除 `QwenTTSConfigNode`（因分段生成导致音色不一致）；修复 MPS 精度 bug 和 CustomVoice 通道不匹配问题；代码清理 ([update.md](doc/update.md))
- **2026-02-04**: 添加 `extra_model_paths.yaml` 支持 ([update.md](doc/update.md))
- **2026-01-29**: 功能更新：支持加载自定义微调模型和 Speaker ([update.md](doc/update.md))
  - *注意：微调功能目前为实验性；推荐直接使用声音克隆以获得最佳效果。*
- **2026-01-27**：功能优化：精简 LoadSpeaker UI，修复 PyTorch 兼容性 ([update.md](doc/update.md))
- **2026-01-26**：功能更新：新增声音持久化系统 (SaveVoice / LoadSpeaker) ([update.md](doc/update.md))
- **2026-01-24**：添加注意力机制选择和模型内存管理功能 ([update.md](doc/update.md))
- **2026-01-24**：为所有 TTS 节点添加生成参数 (top_p, top_k, temperature, repetition_penalty) ([update.md](doc/update.md))
- **2026-01-23**：依赖兼容性与 Mac (MPS) 支持，新增节点：VoiceClonePromptNode, DialogueInferenceNode ([update.md](doc/update.md))

## 在线工作流 (Online Workflows)

- **Qwen3-TTS 多角色多轮对话生成工作流**:
  - [workflow](https://www.runninghub.cn/post/2014703508829769729/?inviteCode=rh-v1041)
- **Qwen3-TTS 3-in-1 (克隆、设计、自定义) 工作流**:
  - [workflow](https://www.runninghub.cn/post/2014962110224142337/?inviteCode=rh-v1041)

## 功能特性

- 🎵 **语音合成**: 高质量的文本转语音功能。
- 🎭 **声音克隆**: 支持从短音频示例进行零样本（Zero-shot）声音克隆。
- 🎨 **声音设计**: 支持通过自然语言描述自定义声音特质。
- 🚀 **高效推理**: 支持 12Hz 和 25Hz 的语音 Tokenizer 架构。
- 🎯 **多语言支持**: 原生支持 10 种主要语言（中文、英文、日文、韩文、德文、法文、俄文、葡萄牙文、西班牙文和意大利文）。
- ⚡ **集成加载**: 无需独立的加载器节点；模型加载按需管理，并带有全局缓存。
- ⏱️ **超低延迟**: 基于创新架构，支持极速语音重建与流式生成。
- 🧠 **注意力机制选择**: 支持多种注意力实现 (sage_attn, flash_attn, sdpa, eager)，自动检测并优雅降级。
- 💾 **内存管理**: 可选择在生成后卸载模型，释放 GPU 内存。
- 🎭 **情感与语速**: 提供情感预设与内联标记（`[sad]` / `[pause:800ms]` / `[rate:1.2]`），并可对任意节点做保音高变速。
- 📚 **多目录声音库**: `SaveVoice` / `LoadSpeaker` 可读写多个目录，支持 `extra_model_paths.yaml` 与环境变量。

## 节点列表

### 1. Qwen3-TTS 声音设计 (`VoiceDesignNode`)
根据文本描述生成独有的声音。
- **输入**:
  - `text`: 要合成的目标文本。
  - `instruct`: 声音描述指令（例如："一个温和的高音女声"）。
  - `model_choice`: 目前声音设计功能锁定为 **1.7B** 模型。
  - `attention`: 注意力机制 (auto, sage_attn, flash_attn, sdpa, eager)。
  - `unload_model_after_generate`: 生成后从内存卸载模型以释放 GPU 内存。
- **能力**: 最适合创建"想象中的"声音或特定的人设。

### 2. Qwen3-TTS 声音克隆 (`VoiceCloneNode`)
从参考音频剪辑中克隆声音。
- **输入**:
  - `ref_audio`: 一段短的（5-15秒）参考音频。
  - `ref_text`: 参考音频中的文本内容（有助于提高质量）。
  - `target_text`: 你希望克隆声音说出的新文本。
  - `model_choice`: 可选择 **0.6B**（速度快）或 **1.7B**（质量高）。
  - `attention`: 注意力机制 (auto, sage_attn, flash_attn, sdpa, eager)。
  - `unload_model_after_generate`: 生成后从内存卸载模型以释放 GPU 内存。

### 3. Qwen3-TTS 预设声音 (`CustomVoiceNode`)
使用预设说话人的标准 TTS。
- **输入**:
  - `text`: 目标文本。
  - `speaker`: 从预设声音中选择（Aiden, Eric, Serena 等）。
  - `instruct`: 可选的风格指令。
  - `attention`: 注意力机制 (auto, sage_attn, flash_attn, sdpa, eager)。
  - `unload_model_after_generate`: 生成后从内存卸载模型以释放 GPU 内存。

### 4. Qwen3-TTS 角色银行 (`RoleBankNode`) [新增]
收集和管理多个声音提示，用于对话生成。
- **输入**:
  - 最多 8 个角色，每个角色包含:
    - `role_name_N`: 角色名称（例如："Alice", "Bob", "旁白"）
    - `prompt_N`: 来自 `VoiceClonePromptNode` 的声音克隆提示
- **能力**: 创建命名的声音注册表，用于 `DialogueInferenceNode`。每个银行最多支持 8 种不同的声音。

### 5. Qwen3-TTS 声音克隆 Prompt (`VoiceClonePromptNode`) [新增]
从参考音频中提取并复用声音特征。
- **输入**:
  - `ref_audio`: 一段短的（5-15秒）参考音频。
  - `ref_text`: 参考音频中的文本内容（强烈推荐以提高质量）。
  - `model_choice`: 可选择 **0.6B**（速度快）或 **1.7B**（质量高）。
  - `attention`: 注意力机制 (auto, sage_attn, flash_attn, sdpa, eager)。
  - `unload_model_after_generate`: 生成后从内存卸载模型以释放 GPU 内存。
- **能力**: 只需提取一次"Prompt 节点"，即可在多个 `VoiceCloneNode` 实例中复用，提高生成效率并保证音质一致性。

### 6. Qwen3-TTS 多角色对话 (`DialogueInferenceNode`) [新增]
支持多角色、多说话人的复杂对话合成。
- **输入**:
  - `script`: 对话脚本，格式为"角色名: 文本"。
  - `role_bank`: 来自 `RoleBankNode` 的角色银行，包含声音提示。
  - `model_choice`: 可选择 **0.6B**（速度快）或 **1.7B**（质量高）。
  - `attention`: 注意力机制 (auto, sage_attn, flash_attn, sdpa, eager)。
  - `unload_model_after_generate`: 生成后从内存卸载模型以释放 GPU 内存。
  - `pause_seconds`: 句子之间的静音持续时间。
  - `merge_outputs`: 将所有对话片段合并为一段长音频。
  - `batch_size`: 并行处理的行数（越大越快，但占用更多显存）。
  - `instruct`: 适用于所有台词的风格指令（例如："低声耳语，语速缓慢"）。**0.6B 模型会忽略该参数。**
  - `speed`: 语速倍率（保音高）。1.0 为模型原生语速，配置好的停顿时长不会随之缩放。
- **能力**: 在单个节点内处理多角色语音合成，非常适合有声书制作或角色扮演场景。

### 7. Qwen3-TTS 情感合成 (`EmotionalTTSNode`) [新增]
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
  | `[pause:800ms]` `[pause:1.2s]` `[break=0.5]` | 插入静音 | 附着到前一段之后；出现在开头则成为前置停顿 |
  | `[rate:1.2]` | 切换语速 | 同样粘滞，只影响其后的片段 |
- **示例**:
  ```text
  [sad]他走了。[pause:800ms]再也不会回来了。
  [whisper]别出声……[pause:1s][tender]我只是想再看看你。
  ```
- **能力**: 适合有声书、角色独白等需要句内情绪起伏的场景；情感切换通过分段生成实现，段与段之间为硬拼接（存在轻微音色/气息跳变）。

### 8. Qwen3-TTS 加载声音 (`LoadSpeakerNode`) [新增]
加载已保存的声音特征与元数据。
- **输入**:
  - `filename`: 扫描到的全部音色，显示为 `<目录标签>/<文件名>`，同名音色也能区分。
  - `directory`（可选）: 额外扫描的目录。可填绝对路径，或相对 `models/qwen-tts` 的路径；下拉列表在下次加载工作流时生效。
  - `file_path`（可选）: 绝对路径或 `<目录标签>/<文件名>`，优先于下拉选择；用于不等刷新就加载刚保存的音色。
- **扫描顺序**: `models/qwen-tts/voices` → 所有注册为 `qwen-tts` 的根目录（含 `extra_model_paths.yaml`，同时探测根目录与其 `voices/` 子目录）→ 环境变量 `QWEN_TTS_VOICE_DIRS`（用 `os.pathsep` 分隔）→ 节点自身的 `directory`。
- **能力**: 实现“一键加载”体验，自动同步加载预计算特征和参考文本。

### 9. Qwen3-TTS 保存声音 (`SaveVoiceNode`) [新增]
将克隆的声音特征及其参考文本永久保存到磁盘。
- **输入**:
  - `output_dir`（可选）: 留空保持原有的 `models/qwen-tts/voices`；相对路径会落在 `models/qwen-tts/` 下；绝对路径原样使用。目录不存在会自动创建。
  - `subfolder`（可选）: `output_dir` 内的子目录，例如 `audiobook/ch1`。
  - `overwrite`（可选）: 关闭后同名音色已存在时报错而不是覆盖。
- **能力**: 建立个性化声音库。保存后可通过 `LoadSpeakerNode` 极速调用。

## 注意力机制

所有节点支持多种注意力实现，具有自动检测和优雅降级功能：

| 机制 | 描述 | 速度 | 安装 |
|------|------|------|------|
| **sage_attn** | SAGE 注意力实现 | ⚡⚡⚡ 最快 | `pip install sage_attn` |
| **flash_attn** | Flash Attention 2 | ⚡⚡ 快 | `pip install flash_attn` |
| **sdpa** | 缩放点积注意力 (PyTorch 内置) | ⚡ 中等 | 内置（无需安装） |
| **eager** | 标准注意力（回退方案） | 🐢 最慢 | 内置（无需安装） |
| **auto** | 自动选择最佳可用选项 | 视情况而定 | 不适用 |

### 自动检测优先级

当选择 `attention: "auto"` 时，系统按以下顺序检查：
1. **sage_attn** → 如果已安装，使用 SAGE 注意力（最快）
2. **flash_attn** → 如果已安装，使用 Flash Attention 2
3. **sdpa** → 始终可用（PyTorch 内置）
4. **eager** → 始终可用（回退方案）

选择的机制会记录在控制台以供透明查看。

### 优雅降级

如果你选择的注意力机制不可用：
- 降级到 `sdpa`（如果可用）
- 降级到 `eager`（作为最后手段）
- 记录降级决策并显示警告信息

### 旧款 NVIDIA 显卡 / CUDA 内核缺失

对于 GTX 1080 Ti（计算能力 6.1）等 Ampere 之前的显卡，加载器使用 `eager`
注意力，并将 `bf16` 调整为 `fp32`；`device=auto` 时同样生效。
这一保守兼容模式也会覆盖手动选择的加速注意力。FP32 占用更多显存，可考虑 0.6B 模型。

CUDA 下载或加载权重前会先执行一个小型运算。若出现
`no kernel image is available for execution on the device` 或 `invalid device function`，
说明 CUDA 内核无法在该显卡执行。错误现在会包含显卡、PyTorch/CUDA 版本和构建架构，
并直接停止，不再以注意力回退为由重复尝试相同 CUDA 配置。
请在 **ComfyUI 使用的 Python 环境**中安装支持该显卡且相互匹配的 PyTorch/torchaudio
构建及 CUDA 扩展，然后重启 ComfyUI。切换注意力无法补齐 PyTorch 缺失的内核。
也可以选择 `device=cpu`、`precision=fp32`、`attention=eager`（速度较慢，需要系统内存）。
小型运算检查通过不代表模型使用的所有内核均已兼容。

### 模型缓存

- 模型缓存包含注意力特定密钥
- 更改注意力机制会自动清除缓存并重新加载模型
- 同一模型可以不同注意力机制共存于缓存中

## 内存管理

### 生成后卸载模型

所有节点都提供 `unload_model_after_generate` 开关：
- **启用**: 清除模型缓存、GPU 内存，并运行垃圾回收
- **禁用**: 模型保留在缓存中以加快后续生成速度（默认）

**使用场景**:
- ✅ 如果显存有限（< 8GB）请启用
- ✅ 如果需要连续运行多个不同模型请启用
- ✅ 如果完成生成并希望释放内存请启用
- ❌ 如果使用相同模型生成多个片段请禁用（更快）

**控制台输出**:
```
🗑️ [Qwen3-TTS] 正在卸载 1 个缓存的模型...
✅ [Qwen3-TTS] 模型缓存和 GPU 内存已清除
```


## 安装

确保已安装以下依赖：
```bash
pip install torch torchaudio transformers librosa accelerate
```

### 模型目录结构示意

目前插件按以下顺序自动搜索模型：

```text
ComfyUI/
├── models/
│   └── qwen-tts/
│       ├── Qwen/Qwen3-TTS-12Hz-1.7B-Base/
│       ├── Qwen/Qwen3-TTS-12Hz-0.6B-Base/
│       ├── Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign/
│       ├── Qwen/Qwen3-TTS-Tokenizer-12Hz/
│       └── voices/ (保存的预设 .wav/.qvp)
```

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

保存时用 `output_dir` 指定目标目录（留空 = 默认目录，相对路径落在 `models/qwen-tts/` 下，绝对路径原样使用），`subfolder` 可再分一层子目录。加载时下拉框显示为 `<目录标签>/<文件名>`，同名文件不会互相覆盖；`file_path` 可直接填入绝对路径，无需等待下拉刷新。

### `extra_model_paths.yaml` 示例

```yaml
qwen-tts: D:\MyAI\Models\Qwen
```

该根目录下的 `voices/` 子目录（以及根目录本身）都会自动纳入声音扫描，因此放在这里的音色无需额外配置。

## 最佳实践技巧

### 音频质量
- **克隆**: 使用清晰、无背景噪音的参考音频（5-15 秒）。
- **参考文本**: 提供参考音频中说的文本可显著提高质量。
- **语言**: 选择正确的语言以获得最佳发音和韵律。

### 性能与内存
- **显存**: 使用 `bf16` 精度可以在几乎不损失质量的情况下大幅节省内存。
- **注意力**: 使用 `attention: "auto"` 自动选择最快的可用机制。
- **模型卸载**: 如果显存有限（< 8GB）或需要运行多个不同模型，请启用 `unload_model_after_generate`。
- **本地模型**: 预先将权重下载到 `models/qwen-tts/` 以优先进行本地加载，避免 HuggingFace 连接超时。

### 注意力机制
- **最佳性能**: 安装 `sage_attn` 或 `flash_attn` 可获得比 sdpa 快 2-3 倍的速度。
- **兼容性**: 使用 `sdpa`（默认）以获得最大兼容性 - 无需安装。
- **显存不足**: 如果其他机制导致 OOM 错误，请将 `eager` 与较小的模型（0.6B）配合使用。

### 对话生成
- **批量大小**: 增加 `batch_size` 以加快生成速度（占用更多显存）。
- **暂停**: 使用 `pause_linebreak` / `period_pause` / `comma_pause` 等控制句间与标点停顿。
- **合并**: 启用 `merge_outputs` 以获得连续对话；禁用以分别生成片段。
- **风格**: 用 `instruct` 给整段对话指定统一语气（0.6B 会忽略该参数）。
- **语速**: `speed` 只改变语音本身，已配置的停顿时长保持不变。

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

## 致谢

- [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS): 阿里巴巴 Qwen 团队官方开源仓库。

## 许可证

- 本项目采用 **Apache License 2.0** 许可证。
- 模型权重请参考 [Qwen3-TTS 许可协议](https://github.com/QwenLM/Qwen3-TTS#License)。

## 作者 (Author)

- **Bilibili**: [个人空间](https://space.bilibili.com/5594117?spm_id_from=333.1007.0.0)
- **YouTube**: [频道](https://www.youtube.com/channel/UCx5L-wKf93YNbcP_55vDCeg)
