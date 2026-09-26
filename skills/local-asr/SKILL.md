---
name: local-asr
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "2.2.0"
license: MIT
description: 使用本地 ASR 服务将音频或视频文件转录为带时间戳和说话人的 Markdown，Apple Silicon 默认使用 MOSS-MLX，保留 FunASR 原生及 ONNX 管线供显式选择；支持认领式声纹注册，本人声纹注册后自动识别标注。支持 mp4、mov、mp3、wav、m4a 等格式；用于会议记录、电话录音、视频字幕和播客转录。
---
# 本地 ASR 语音转文字（MOSS 默认）

本 skill 提供本地语音识别服务，将音频或视频文件转换为结构化的 Markdown 文档。
本技能原名 `funasr-transcribe`；现以 `local-asr` 统一入口，默认引擎为 MOSS-MLX，FunASR 为可显式选择的保留后端。

## 功能概述

- 支持多种音视频格式（mp4、mov、mp3、wav、m4a、flac 等）
- 自动生成时间戳
- 支持说话人分离（diarization，默认启用）
- **ONNX 加速模式**：支持 `paraformer-onnx` 与实验性的 `SenseVoice-Small ONNX`
- **MOSS-MLX 默认模式**：Apple Silicon 上使用 MOSS 同时转写、标时间戳和区分匿名说话人；长录音分段后用 CAM++ 链接跨段标签
- **FunASR 保留模式**：显式指定 `--model paraformer` 或 `--model paraformer-onnx` 调用原管线
- **单人快速模式**：`--fast` / `"fast": true` 关闭 diarization，不改变所选模型
- **Paraformer ONNX 后处理优化**：`paraformer-onnx` 单人/多人路径都会先 VAD 分段，再清理文本输出、恢复标点并输出句子级时间戳；单人路径使用全局标点恢复，多人路径使用逐段标点以保留 speaker 对齐
- **视频关键帧截图提取**：视频默认自动提取，`--no-slides` 可跳过耗时截图步骤
- **声纹注册与说话人识别**：本人声纹经认领注册后，后续转录自动识别并直接标注注册名；详见 [`references/speaker-registry.md`](references/speaker-registry.md)
- 转录后自动附带 AI 总结提示词，Agent 可一步完成总结
- API 返回转录、截图、归档、摘要等阶段耗时；可通过 `include_summary_prompt=false` 跳过摘要准备
- 输出 Markdown 格式，便于阅读和编辑

## 依赖

### 系统依赖

| 依赖 | 安装方式 |
|------|----------|
| Apple Silicon 原生 Python 3.10–3.12（建议 3.11；完整旧管线也需此范围） | macOS: `brew install python@3.11` |
| curl | macOS 通常自带；如缺失可执行 `brew install curl` |
| ffmpeg（MOSS 音频归一化必需，也用于视频处理） | macOS: `brew install ffmpeg` |

### Python 包

| 包名 | 用途 | 安装命令 |
|------|------|----------|
| `funasr` | FunASR 原生推理与 CAM++ diarization | `pip install -r assets/requirements.txt` |
| `funasr-onnx` | Paraformer / SenseVoice ONNX 加速 | `pip install -r assets/requirements.txt` |
| `opencv-python`、`imagehash` | 视频关键帧提取 | `pip install -r assets/requirements.txt` |
| `mlx-audio[stt]` | Apple Silicon 默认 MOSS 后端 | `python3 -m pip install -r assets/requirements-moss-mlx.txt` |

默认安装在 Apple Silicon 上同时保留 FunASR/CAM++ 依赖并安装 MOSS-MLX；`python3 scripts/setup.py --legacy` 只安装原 FunASR 管线。非 Apple Silicon 使用旧管线时，启动服务前设置 `FUNASR_SERVER_DEFAULT_MODEL=paraformer`，或运行 `server-onnx.py`；CLI 仍须显式传 `--model paraformer`（或 `--model paraformer-onnx`）。
`funasr-onnx` 0.4.1 要求 NumPy ≤1.26.4，因此两套后端同装需 Python 3.10–3.12；Python 3.13+ 的 NumPy 2 环境不能据此保证旧 ONNX 路线可用。

首次安装或更换后端时，按 [`references/model-backends.md`](references/model-backends.md) 核对设备、依赖、权重 ID、下载时机和启用命令；下方保留默认后端的最短安装路径。

推荐使用技能目录内被 Git 忽略的虚拟环境，避免把 MLX-Audio 依赖装进系统 Python：

```bash
cd <skill目录>
/opt/homebrew/bin/python3.11 -m venv venv
source venv/bin/activate
python3 scripts/setup.py
```

以后从同一环境运行 `python3 scripts/server.py` 和 `python3 scripts/auto_transcribe.py`。已配置旧环境的用户可在该环境安装 MOSS 依赖；本机如果已经使用 `venv/`，可直接运行 `venv/bin/python`。

若已有旧版环境，首次使用默认 MOSS 前，在**启动 `server.py` 的同一个 Python 环境**安装 MOSS 依赖：

```bash
python3 -m pip install -r assets/requirements-moss-mlx.txt
```

`setup.py` 默认从 ModelScope 下载 MOSS 权重与 CAM++；若跳过模型下载，首次调用会优先从 Hugging Face 获取 MOSS，失败时改用 ModelScope。显式选择旧 FunASR 管线不需要 MOSS 依赖。MLX 后端仅支持 Apple Silicon macOS；长录音需要现有的 CAM++ 模型链接分段说话人。MOSS 的 `[S01]` 等标签只表示同一份录音中的匿名说话人，不识别真实姓名。

如需离线运行或固定模型路径，可通过已安装的 `modelscope` 预下载模型，并把实际输出目录传给 `--model-id`：

```bash
python3 -c "from modelscope.hub.snapshot_download import snapshot_download; print(snapshot_download('OpenMOSS/MOSS-Transcribe-Diarize'))"
python3 scripts/transcribe.py /path/to/meeting.m4a --model-id /path/to/downloaded/model
```

MOSS 长录音默认按约 600 秒切段，并在目标点附近选择连续静音；`FUNASR_MOSS_CHUNK_SECONDS=300` 可缩短为约 5 分钟（须重启服务）。分段说话人由 CAM++ 声纹启发式链接，短插话仍可能拆成多个标签；总发言不足 3 秒的说话人会在 `warnings` 中提示人工核对。输出时间戳越界、缺失标签或达到生成上限时会报错；近乎零波形能量的整段会跳过推理，幻觉句会被剔除并提示。此处不保证实际会议中的说话人准确率，需要对真实样本人工复核。

### MOSS 性能与可选量化

默认使用原始 MOSS 权重。MLX-Audio 可把本地权重转换为 4-bit 或 8-bit 模型；量化主要减少权重与运行内存，**不保证更快或维持同样的说话人标签**。在 M1 Max 上，约 4 分半的重复合成双人语音中，原始权重两次用时 13.4/14.7 秒，4-bit 为 18.4/19.4 秒，8-bit 为 21.6/20.3 秒；量化模型更慢。短真实通话片段的量化输出还出现额外的短说话人标签，未经人工真值核对。此测试不能代替真实长录音验收。

若设备内存不足，可从**已下载的原始模型目录**生成独立量化副本，再显式选择它（目录应放在技能仓库外；首次转换需要足够的临时磁盘空间）：

```bash
python3 -m mlx_audio.convert --hf-path /path/to/original-moss-model --mlx-path /path/to/moss-q8 --quantize --q-bits 8 --model-domain stt
python3 scripts/transcribe.py /path/to/meeting.m4a --model-id /path/to/moss-q8
```

常驻服务可设置 `FUNASR_MOSS_MODEL_ID=/path/to/moss-q8` 后重启；恢复默认时移除该环境变量。API 请求中的 `quantize` 只控制旧 ONNX INT8 路线，**不会**量化 MOSS；CLI 没有 MOSS 自动量化开关。`FUNASR_MOSS_CHUNK_SECONDS` 可在 60–600 秒间调整输出预算与切点，但更短的分段会增加 CAM++ 跨段链接和切点风险，不应仅凭速度更改默认值。

## 所需权限与安全说明

读取用户指定的本地音视频，写入 Markdown、截图及技能目录下的 `archive/`。服务默认只监听 `127.0.0.1:8765`；CLI 经本机 HTTP 调用该服务，不上传音频到云端。首次安装依赖或模型时会联网访问包索引、ModelScope 或 Hugging Face，之后本地缓存可复用。脚本会调用 `ffmpeg`、Python 子进程和本地文件操作；无需 ASR API Key。含客户录音的 `archive/` 与本机生成的 `assets/skill-env.json` 仅供本地使用，不属于分享材料。

首次需要运行 ONNX 模式时，直接执行：

```bash
python3 scripts/setup.py --legacy
```

即可同时安装 `funasr-onnx` 及其依赖；`SenseVoiceSmall` 仅在显式指定 `model=sensevoice` 时按需下载。

### ONNX 质量调参

`paraformer-onnx` 默认使用质量优先的参数组合；单人路径会复用多人路径的 ONNX VAD 分段 ASR，但不执行 CAM++ 说话人聚类：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `FUNASR_ONNX_TEXT_SOURCE` | `preds` | 使用清理后的 ONNX `preds` 文本；如遇到异常可设为 `raw_tokens` 回退 |
| `FUNASR_SERVER_ONNX_THREADS` | `4` | ONNX Runtime 推理线程数，主要影响速度，不直接改善识别质量 |
| `FUNASR_ONNX_COMPAT_CACHE` | `~/.cache/funasr-onnx-compat` | ONNX 兼容导出缓存目录；兼容导出会复制模型目录，可删除该缓存后重新生成 |

单人 `paraformer-onnx` 会将各 VAD 片段的识别文本先拼接，再做一次全局标点恢复；这样比逐片段恢复标点更接近原生 `paraformer`，也能减少重复调用标点模型的耗时。

ONNX 句子级时间戳是根据字符位置和 token 时间戳做的近似映射，适合定位段落和发言轮次，不应视为逐字强对齐结果。

已验证不建议作为默认的调参方向：

- 调大 VAD 静音阈值会减少切段并提速，但 90 秒多人样本上文本相似度下降明显。
- 合并相邻 VAD 段或整段转录更容易出现错字、重复和长音频塌缩，因此单人和多人 ONNX 都不再默认整段转录。
- 给 VAD 片段额外 padding 会引入边界重复，整体质量不如默认切段。

## Agent 默认工作流（转录 + 自动总结）

当用户请求转录音频/视频时，应遵循以下流程，**一次性完成转录和 AI 总结**：

**前置步骤（必须第一个执行）：进入技能目录并设置 PATH。** 某些执行环境（如 agent-executor headless 模式）的 PATH 被限制为只有插件目录，`curl`、`python3` 等系统命令找不到。必须先执行：

```bash
cd <skill目录> && export PATH="$PWD/venv/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
```

> 之后所有 bash 命令都必须在同一命令块中跟在这行后面，或在每个命令块开头重复。`venv/` 不存在时先按上文创建并安装。

### 步骤 0：环境检测（自动）

在执行转录前，检查 `assets/skill-env.json` 是否存在，且其中 `FUNASR_SERVER_DEFAULT_MODEL` 为 `moss-mlx`、`FUNASR_PYTHON` 指向已安装 MLX-Audio 的 Python。旧配置需要加 `--force` 重新检测：

```bash
cd <skill目录> && export PATH="$PWD/venv/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH" && python3 scripts/init_env.py
```

若配置仍指向旧环境，运行 `python3 scripts/init_env.py --force`，并确认其中的 `FUNASR_PYTHON` 指向 `venv/bin/python`。

如果检测失败（退出码非0），按提示运行安装脚本：

```bash
cd <skill目录> && export PATH="$PWD/venv/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH" && python3 scripts/setup.py
```

安装完成后会自动重新检测并生成 `skill-env.json`。

### 步骤 1：启动/检查服务

```bash
cd <skill目录> && export PATH="$PWD/venv/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH" && curl -s http://127.0.0.1:8765/health
```

如果服务未运行，后台启动：

```bash
cd <skill目录> && export PATH="$PWD/venv/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH" && python3 scripts/server.py --idle-timeout 600 &
```

等待服务就绪（轮询 `/health` 直到返回 200）。

### 步骤 2：转录文件

```bash
cd <skill目录> && export PATH="$PWD/venv/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH" && curl -s -X POST http://127.0.0.1:8765/transcribe \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/path/to/audio.aac"}'
```

> 注意：`diarize` 默认为 `true`，无需显式传入。如需禁用，传 `"diarize": false`。
> 视频文件（mp4、mov 等）会自动启用关键帧截图提取（`extract_slides`），无需手动传入。如需禁用，显式传 `"extract_slides": false`。
> 单人讲课/语音可传 `"fast": true` 关闭说话人分离，仍使用默认 MOSS；`"model": "paraformer"` 或 `"model": "paraformer-onnx"` 可调用原 FunASR 管线。

响应中包含以下关键字段：
- `output_path`: 转录输出的 Markdown 文件路径
- `text`: 转录全文
- `summary_prompt`: AI 总结提示词（**已自动附带**，无需额外调用 `/summary`）
- `text_preview`: 转录文本前 500 字预览

### 步骤 3：说话人识别与认领（默认 MOSS 路径）

转录响应中的 `speaker_identification` 逐人显示每个说话人是否已被声纹库识别（`{"S01": {"name": "杨律师", "score": 0.74}, "S02": null}`；首次空库时全部为 null）。已命中的说话人在 Markdown 中直接显示注册名。

`speaker_states` 为每位说话人给出完整状态，按状态决定下一步动作：
- `matched`：已命中注册声纹（`name` 为注册名），无需询问；
- `unknown`：有声纹向量但未达阈值，**可认领注册**——按下述流程询问用户；
- `insufficient_audio`：总发言不足 3 秒，无声纹向量，**只能根据用户说明在 Markdown 中为本稿标注，不能注册**；
- `extraction_failed`：声纹提取/识别失败，本次无法识别或认领，可提示用户重试；
- `disabled`：说话人声纹识别未启用（fast/显式关闭/CAM++ 不可用），跳过认领流程。

**当存在 `unknown` 状态的说话人时，必须先向用户逐一确认身份再继续。**询问前，先根据响应 `segments`（每段含 speaker 与 text）为**每位未识别说话人生成一段简要叙述**，随问题一并呈现，供用户凭内容判断身份——这是打标的主要依据，不要只报编号：

叙述格式（每位说话人 2-3 句，基于其全部发言归纳）：
- **发言占比**：该说话人发言时长/段数占全会的比例；
- **内容概述**：他说了什么——诉求、立场、给出的信息、向谁发问；
- **身份线索**：自称（"我是杨律师"）、被对方称呼（"张女士"）、角色口吻（咨询方/解答方/主导方）。

示例呈现："转录完成，共 2 位说话人。**发言人1**（占 35% 发言）：自述是房东，询问拖欠房租的起诉流程，多次被对方称为'张女士'。**发言人2**（占 65% 发言）：以律师口吻分析证据和诉讼策略，开头说'诶，张女士'。请问这两位分别是谁？"

用户回答"是我"、"客户张三"或"不用标"后，对命名的说话人执行认领注册：

```bash
curl -s -X POST http://127.0.0.1:8765/speaker/register \
  -H "Content-Type: application/json" \
  -d '{"name": "<用户确认的名字>", "embedding": <响应 speaker_embeddings 中该标签的数组>, "source_file": "<文件名>", "source_label": "S01"}'
```

- 认领完成后当前 Markdown 无需重跑；下一份录音中同一人将自动识别标注。
- 用户表示"不用标"的说话人保持匿名，不注册。用户只是说明某说话人**本稿身份**而不愿长期注册时，直接在 Markdown 中标注，不调用注册。
- 客户或第三方声纹的注册须先取得其单独同意（声纹属敏感个人信息）；本人声纹无此要求。完整流程、阈值与纠错见 [`references/speaker-registry.md`](references/speaker-registry.md)。
- 推荐入口（`auto_transcribe.py`）可用 `--json` 获取完整响应（含识别结果与向量）、`--save-result` 保存结果文件；认领时用 `python3 scripts/speaker_registry.py claim <名字> --result <结果JSON> --label S01` 按标签确定性取向量，避免手工复制 192 个浮点数。

### 步骤 4：生成 AI 总结

根据 `summary_prompt`（或直接根据 `text` 内容），Agent 生成结构化 JSON 总结：

```json
{
  "full_summary": "至少400字，分成2-3段，交代背景、问题、关键事实、数据、风险与行动建议",
  "speaker_summary": [
    {
      "speaker_order": "发言人1",
      "speaker_name": "如能识别请写姓名，否则写未知",
      "summary": "至少180字，涵盖该发言人的观点、依据、数据、态度与潜在影响"
    }
  ],
  "highlights": ["6-10条重点，每条60-100字"],
  "keywords": ["5-8个关键词"]
}
```

### 步骤 5：注入总结到文件

**重要：不要只描述注入操作，必须实际执行以下命令。**

将步骤 3 生成的 JSON 写入临时文件，然后调用脚本注入（比 curl 注入更可靠，无需 JSON 转义）：

```bash
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH" && cat > /tmp/summary_<文件名>.json << 'JSONEOF'
{步骤3生成的JSON内容}
JSONEOF
python3 <skill目录>/scripts/summary.py inject "<output_path>" /tmp/summary_<文件名>.json
```

脚本会自动：
- 解析 JSON 并格式化为 Markdown
- 注入到 Markdown 文件的正确位置
- 添加 `<!-- AI-SUMMARY:START -->` / `<!-- AI-SUMMARY:END -->` 标记

### 步骤 6：验证注入结果（必须执行）

**注入后必须执行验证，确认摘要确实写入文件。如果验证失败，必须重试步骤 5。**

```bash
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH" && python3 <skill目录>/scripts/summary.py verify "<output_path>"
```

- 如果输出 `✅ 摘要已存在` 且 `✅ 发言人覆盖完整` → 成功，向用户报告完成
- 如果输出 `❌ 摘要不存在` → 失败，回到步骤 5 重试
- 如果输出 `❌ 摘要遗漏发言人` / `❌ 摘要出现稿件中不存在的发言人`（退出码非零）→ 说明总结遗漏或虚构了发言人，回到步骤 4 按 `speaker_states`/正文标签重新生成总结后再次注入；**覆盖不完整的摘要不得作为已验收交付**
- 输出 `⚠️ 发言人覆盖无法验证`（fast/无发言行结构稿件）→ 章节完整即可交付，如实说明覆盖未验证

### 完整流程示例

```
用户：转录这个音频
  ↓
Agent：
  1. 检查/启动服务
  2. POST /transcribe {"file_path": "xxx.aac"}  ← 一次调用拿到转录+识别结果+提示词
  3. 按 speaker_states 处理：unknown 说话人询问用户身份 → POST /speaker/register 认领注册
     （insufficient_audio 只能本稿标注，不能注册）
  4. 根据转录内容直接生成总结 JSON（speaker_order 逐字用稿件发言标签）
  5. 写 JSON 到临时文件 → python3 summary.py inject 注入
  6. python3 summary.py verify 验证（含发言人覆盖）→ 失败则重试步骤 4-5
  ↓
用户：收到带 AI 总结的 Markdown 文件
```

## 使用流程

### 首次使用：环境检测与依赖安装

**重要：首次使用前必须先检测环境是否满足要求。**

运行环境检测：

```bash
python3 scripts/check_env.py
```

检测脚本会检查以下环境要求：

| 必需项 | 要求 | 检测命令 |
|--------|------|----------|
| Python | >= 3.8，`python3` 命令可用 | `python3 --version` |
| curl | HTTP 客户端（用于 API 调用） | `curl --version` |
| 基本命令 | `ls`, `ps`, `grep` | shell 内置 |

**如果环境检测失败：**

1. **Python3 命令不可用**：
   ```bash
   # macOS 使用 homebrew 安装 Python
   brew install python@3.14
   ```

2. **curl 不可用**：
   ```bash
   # macOS 确保 curl 已安装
   brew install curl
   ```

3. **验证环境修复后**，重新运行检测：
   ```bash
   python3 scripts/check_env.py
   ```

### 首次使用：安装依赖和下载模型

运行安装脚本完成环境配置：

```bash
/opt/homebrew/bin/python3.11 -m venv venv
source venv/bin/activate
python3 scripts/setup.py
```

安装脚本会自动：

1. 检查 Apple Silicon 和 Python 版本（默认双后端安装需 3.10–3.12）
2. 安装依赖包（FastAPI、FunASR/CAM++、MLX-Audio 等；旧管线依赖一并保留）
3. 下载 MOSS 和 CAM++ 模型到 ModelScope 缓存；`--legacy` 只安装旧 FunASR 模型

验证安装状态：

```bash
python3 scripts/setup.py --verify
```

### 启动转录服务

```bash
python3 scripts/server.py
```

如需运行保留的 ONNX 旧管线，使用：

```bash
python3 scripts/server-onnx.py --preload
```

服务默认运行在 `http://127.0.0.1:8765`

**智能特性：**

- **自动启动**：首次请求时自动加载模型
- **空闲关闭**：默认 10 分钟无活动后自动关闭以节约资源
- **可配置超时**：使用 `--idle-timeout` 参数自定义空闲超时时间（秒）

**服务生命周期：**

1. 启动后进入空闲监控状态
2. 接收到请求时自动加载模型并执行转录
3. 每次请求都会重置空闲计时器
4. 连续 10 分钟无请求时自动关闭
5. 下次请求时重新启动

**重要提示：**

- ⚠️ **请勿手动关闭服务** - 转录完成后让服务继续运行，它会自动在 10 分钟无活动后关闭
- 这样可以连续转录多个文件，无需重复启动服务
- 如需立即关闭服务，按 `Ctrl+C` 或等待 10 分钟空闲超时

**示例**：自定义 30 分钟空闲超时

```bash
python3 scripts/server.py --idle-timeout 1800
```

### 执行转录

使用客户端脚本转录文件：

```bash
# 转录单个文件
python3 scripts/transcribe.py /path/to/audio.mp3

# 指定输出路径
python3 scripts/transcribe.py /path/to/video.mp4 -o transcript.md

# 启用说话人分离
python3 scripts/transcribe.py /path/to/meeting.m4a --diarize

# 保留的 FunASR 原生管线
python3 scripts/transcribe.py /path/to/meeting.m4a --model paraformer

# 保留的 Paraformer ONNX 管线
python3 scripts/transcribe.py /path/to/meeting.m4a --model paraformer-onnx

# Paraformer ONNX 单人路径（VAD 分段 ASR，不做说话人聚类）
python3 scripts/transcribe.py /path/to/course.m4a --model paraformer-onnx --no-diarize

# 单人讲课快速模式（关闭说话人分离，仍使用默认 MOSS）
python3 scripts/transcribe.py /path/to/course.m4a --fast

# 默认 MOSS 说话人转录与法律术语热词
python3 scripts/transcribe.py /path/to/meeting.m4a --hotword 请求权基础 --hotword DeepSeek

# 批量转录目录
python3 scripts/transcribe.py /path/to/media_folder/

# 提取视频关键帧截图（PPT幻灯片）
python3 scripts/transcribe.py /path/to/video.mp4 --slides

# 视频只转录，不提取截图
python3 scripts/transcribe.py /path/to/video.mp4 --no-slides

# 自定义场景检测阈值（值越低越灵敏，默认20.0）
python3 scripts/transcribe.py /path/to/video.mp4 --slides --slide-threshold 15.0
```

### AI 智能总结（Claude Code 环境）

转录完成后，可以生成 AI 智能总结，充分利用 Claude Code 的原生 AI 能力。

**自动模式（推荐）：**

使用 `--auto-summary` 参数，转录完成后自动生成并注入总结：

```bash
# 转录并自动生成总结（Claude Code 原生环境，无需配置 API Key）
python3 scripts/transcribe.py /path/to/audio.m4a --auto-summary

# 完整流程：说话人分离 + 自动总结
python3 scripts/transcribe.py /path/to/meeting.m4a --diarize --auto-summary
```

**工作原理：**
- 脚本输出结构化总结请求（`AI_SUMMARY_REQUEST`）
- Claude Code 自动识别并利用内置 AI 能力生成总结
- 无需任何外部 API Key 配置

**手动模式：**

1. 执行转录后，脚本会自动准备总结提示词
2. 将提示词发送给 Claude AI 生成结构化总结
3. 将 Claude 返回的 JSON 结果粘贴回脚本
4. 自动将总结注入到 Markdown 文件

```bash
# 转录单个文件（输出提示词供手动调用）
python3 scripts/transcribe.py /path/to/audio.mp3

# 禁用自动总结（只输出提示词）
python3 scripts/transcribe.py /path/to/audio.m4a --no-summary
```

**总结内容结构：**

- **全文总结** - 400+ 字，包含背景、问题、关键事实
- **发言人总结** - 每个发言人的观点、态度和贡献
- **重点内容** - 6-10 条核心要点
- **关键词** - 5-8 个关键术语

**提示词特点：**

- 专门针对中文口语化对话优化
- 保留发言人上下文和对话流程
- 结构化 JSON 输出便于解析和格式化

详细文档请查看：<references/api-reference.md>

### 通过 HTTP API 调用

**检查服务状态**：

```bash
curl http://127.0.0.1:8765/health
```

使用 curl 直接调用 API：

```bash
curl -X POST http://127.0.0.1:8765/transcribe \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/path/to/audio.mp3"}'

# 单人快速模式（关闭说话人分离，仍使用默认 MOSS）
curl -X POST http://127.0.0.1:8765/transcribe \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/path/to/course.m4a", "fast": true}'

# 指定 Paraformer ONNX（默认启用 diarization）
curl -X POST http://127.0.0.1:8765/transcribe \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/path/to/meeting.m4a", "model": "paraformer-onnx"}'

# Paraformer ONNX 单人路径（VAD 分段 ASR，不做说话人聚类）
curl -X POST http://127.0.0.1:8765/transcribe \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/path/to/course.m4a", "model": "paraformer-onnx", "diarize": false}'

# 提取视频关键帧截图
curl -X POST http://127.0.0.1:8765/transcribe \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/path/to/video.mp4", "extract_slides": true}'
```

**API 文档（Swagger UI）**：

FastAPI 自动生成交互式 API 文档，访问：[http://127.0.0.1:8765/docs](http://127.0.0.1:8765/docs)

可在此页面中：

- 查看所有 API 端点
- 在线测试 API（不需要 curl）
- 查看请求/响应格式
- 查看详细参数说明

**响应示例**（健康检查）：

```json
{
  "status": "ok",
  "service": "Local ASR",
  "uptime": 300,
  "idle_time": 120
}
```

返回字段说明：

- `uptime`：服务运行时间（秒）
- `idle_time`：当前空闲时间（秒）

### 完整 API 文档

详细的 API 参考文档请查看：<references/api-reference.md>

包含：

- 所有 API 端点的完整规范
- 请求/响应格式详解
- 参数说明和示例
- 完整的 curl 命令示例

## 脚本说明

| 脚本                         | 用途                                |
| ---------------------------- | ----------------------------------- |
| `scripts/init_env.py`      | **环境检测 + 生成 skill-env.json** |
| `scripts/check_env.py`     | 环境检测（简化版）                  |
| `scripts/setup.py`         | 一键安装依赖和下载模型              |
| `scripts/server.py`        | 启动 HTTP API 服务                  |
| `scripts/server-onnx.py`   | 启动默认 ONNX 加速服务             |
| `scripts/transcribe.py`    | 命令行客户端                        |
| `scripts/auto_transcribe.py` | **自动化转录脚本（推荐）**         |
| `scripts/speaker_registry.py` | 声纹库管理（list / remove / claim / test） |

---

## 自动转录 + 总结流程

本 skill 支持在任意 Agent 平台中自动完成**转录 + 总结**全流程。

### 方式一：使用自动化脚本（推荐）

```bash
# 自动转录 + 获取总结提示词（说话人分离默认启用）
python3 scripts/auto_transcribe.py /path/to/audio.aac

# 禁用说话人分离
python3 scripts/auto_transcribe.py /path/to/audio.aac --no-diarize

# 单人快速模式（关闭说话人分离，仍使用默认 MOSS）
python3 scripts/auto_transcribe.py /path/to/course.m4a --fast

# 只获取总结提示词，不生成总结
python3 scripts/auto_transcribe.py /path/to/audio.aac --prompt-only

# 机器模式：stdout 仅输出完整响应 JSON（含说话人识别/向量/段落），日志走 stderr
python3 scripts/auto_transcribe.py /path/to/audio.aac --json

# 保存完整响应 JSON 到文件（0600 权限；含声纹向量，注意保密）
python3 scripts/auto_transcribe.py /path/to/audio.aac --json --save-result /tmp/asr-result.json

# 认领注册：从结果 JSON 按标签取声纹向量（需用户确认身份且同意长期注册）
python3 scripts/speaker_registry.py claim <用户确认的名字> --result /tmp/asr-result.json --label S01
```

### 方式二：HTTP API 调用

#### 1. 转录音频（响应中已自动附带总结提示词）

```bash
curl -X POST http://127.0.0.1:8765/transcribe \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/path/to/audio.aac"}'
```

响应中包含 `summary_prompt` 字段，可直接用于生成总结，无需额外调用 `/summary`。

#### 2. 注入 AI 总结

生成总结后，调用：

```bash
curl -X POST http://127.0.0.1:8765/inject_summary \
  -H "Content-Type: application/json" \
  -d '{
    "md_path": "/path/to/audio.md",
    "summary_content": "## AI 摘要\n\n### 全文总结\n...\n\n### 重点内容\n- ...\n\n### 关键词\n..."
  }'
```

---

### API 端点汇总

| 端点                   | 方法 | 功能                        |
| ---------------------- | ---- | --------------------------- |
| `/health`             | GET  | 健康检查                    |
| `/transcribe`         | POST | 转录音频/视频              |
| `/batch_transcribe`   | POST | 批量转录目录               |
| `/summary`            | POST | 生成 AI 总结提示词         |
| `/inject_summary`     | POST | 将总结注入 Markdown 文件    |
| `/verify_summary`     | POST | 验证摘要是否已注入          |
| `/speaker/register`   | POST | 认领注册说话人声纹          |
| `/speaker/list`       | GET  | 列出已注册说话人            |
| `/speaker/remove`     | POST | 删除已注册说话人            |
| `/speaker/test`       | POST | 音频声纹与库比对            |

## 配置文件

| 文件                        | 说明             |
| --------------------------- | ---------------- |
| `assets/models.json`      | ASR 模型配置清单 |
| `assets/requirements.txt` | Python 依赖清单  |

## 输出格式

转录结果保存为 Markdown 文件，包含：

1. **标题** - 文件名（无转录时间戳）
2. **转录内容** - 格式：`发言人N HH:MM:SS` 换行 `内容`
3. **AI 摘要**（可选）- 包含全文总结、发言人总结、重点内容、关键词

**示例格式（视频含截图）：**

```markdown
# 转录：视频.mp4

## 转录内容

发言人1 00:02:49
![](slides/slide_001_02m49s.jpg)
各位好，今天我们来讲...

发言人1 00:03:30
![](slides/slide_002_03m30s.jpg)
这是第二段的内容...
```

## 模型信息

模型存储在 ModelScope 默认缓存目录 `~/.cache/modelscope/hub/models/`：

- ASR 主模型 (Paraformer) - 867MB
- SenseVoice-Small（实验性单人 ONNX 路径）- 显式指定时按需下载
- VAD 模型 - 4MB
- 标点模型 - 283MB
- 说话人分离模型 - 28MB
- MOSS-Transcribe-Diarize（默认）- 模型权重约 1.8GB，运行内存高于权重大小

## STT 转录优先级（重要）

**默认顺序**：先使用 MOSS-MLX；若 MOSS 失败，检查错误、依赖与模型路径。需要继续处理时可显式改用 `--model paraformer` 或 `--model paraformer-onnx`，并向用户说明已切换管线；不要静默回退。非 Apple Silicon 用旧管线时先设置 `FUNASR_SERVER_DEFAULT_MODEL=paraformer` 启动服务，再在 CLI 显式指定旧模型。

### MOSS 失败时的排查步骤

1. 在启动服务的同一 Python 环境运行 `python3 scripts/setup.py --verify`，核对 MLX-Audio、ffmpeg 与模型缓存。
2. 检查服务日志；若 Hugging Face 下载失败，可设置 `FUNASR_MOSS_MODEL_ID` 为本地模型目录后重启。
3. 时间戳缺失、输出截断或短发言标签不稳时，保留错误/警告并人工复核；必要时显式调用原 FunASR 管线对照。

### Whisper CLI 应急路径（需明确选择）

```bash
# 提取音频（16kHz 单声道）
ffmpeg -i "/path/to/video.mp4" -vn -acodec pcm_s16le -ar 16000 -ac 1 -y "/tmp/audio.wav"

# Whisper 转录（tiny 模型最快，medium 质量更好）
/opt/homebrew/bin/whisper "/tmp/audio.wav" \
  --model tiny \
  --language Chinese \
  --output_dir /tmp/transcript \
  --output_format all
```

性能参考：19 分钟音频，tiny 模型约 3-5 分钟（Mac CPU）。

## 故障排除

### cv2 / opencv 导入失败

**症状**：`POST /transcribe` 返回 `{"detail":"No module named 'cv2'"}`，但 `pip show opencv-python-headless` 显示已安装。

**根因**：服务进程使用的 Python 环境与 pip 安装目标不同。常见于 macOS Homebrew Python 3.14 环境，pip 安装到了系统 site-packages，但服务进程加载的是 Homebrew 路径。

**排查步骤**：
1. 在终端验证 cv2 是否可导入：`python3 -c "import cv2; print('ok')"`
2. 如果导入失败，执行：`python3 -m pip install opencv-python-headless --break-system-packages`
3. 确认服务进程的 Python 路径：`lsof -p <server_pid> | grep python`

**正确启动流程**：
```bash
# 确认 cv2 可用后再启动服务
python3 -c "import cv2; print('cv2 ok')"

# 如需重启，先核对占用进程确为本技能的 server.py，再正常停止该进程
lsof -nP -iTCP:8765 -sTCP:LISTEN

# 重启服务
python3 scripts/server.py --idle-timeout 600 &
```

### 服务端口被占用

**症状**：`Address already in use`（Errno 48）

先运行 `lsof -nP -iTCP:8765 -sTCP:LISTEN` 查明占用者。若是其他服务，保留该进程，并为本技能指定其他空闲端口：

```bash
python3 scripts/server.py --port 8766
python3 scripts/transcribe.py /path/to/audio.mp3 --server http://127.0.0.1:8766
```

自动转录入口可改用 `python3 scripts/auto_transcribe.py /path/to/audio.mp3 --api http://127.0.0.1:8766`，其自动启动服务也会使用指定端口。两个客户端会核对 `/health` 的服务标识，避免把其他服务误判为本地 ASR。

### FunASR 服务无响应 / 模型加载慢

首次转录需要下载模型（约 1-2GB），耐心等待。后续请求模型已缓存，速度会快很多。

**视频截图功能：**

视频文件（mp4、mov、avi、mkv、wmv、webm）转录时会自动启用关键帧提取。
依赖 `opencv-python` 和 `imagehash` 已包含在 requirements.txt 中，`setup.py` 安装时会一并安装。
如未安装这些依赖，服务端会输出提示但不影响普通转录功能。

服务启动失败时，运行验证命令检查安装状态：

```bash
python3 scripts/setup.py --verify
```

重新下载模型：

```bash
python3 scripts/setup.py --skip-deps
```
