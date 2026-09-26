# API 参考文档

各后端的依赖、模型权重下载与启用方式见 [`model-backends.md`](model-backends.md)。

## 端点列表

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/transcribe` | 转录单个文件 |
| POST | `/batch_transcribe` | 批量转录目录 |
| POST | `/speaker/register` | 认领注册说话人声纹 |
| GET | `/speaker/list` | 列出已注册说话人 |
| POST | `/speaker/remove` | 删除已注册说话人 |
| POST | `/speaker/test` | 音频声纹与库比对 |

## 1. 健康检查

检查服务状态和运行信息。

**请求**

```bash
GET /health
```

**响应示例**

```json
{
  "status": "ok",
  "service": "Local ASR",
  "uptime": 300,
  "idle_time": 120
}
```

**响应字段**

| 字段 | 类型 | 描述 |
|------|------|------|
| `status` | string | 服务状态，"ok" 表示正常运行 |
| `service` | string | 服务名称 |
| `uptime` | integer | 服务运行时间（秒） |
| `idle_time` | integer | 当前空闲时间（秒） |

## 2. 转录单个文件

将音频或视频文件转录为 Markdown 文档。

**请求**

```bash
POST /transcribe
Content-Type: application/json

{
  "file_path": "/path/to/audio.mp3",
  "output_path": "/path/to/output.md",
  "diarize": true,
  "fast": false
}
```

**请求参数**

| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `file_path` | string | 是 | 要转录的文件绝对路径 |
| `output_path` | string | 否 | 输出 Markdown 文件路径（默认：原文件同目录下的 .md 文件） |
| `diarize` | boolean | 否 | 是否启用说话人分离（默认：true） |
| `model` | string | 否 | 省略时默认 `moss-mlx`；旧管线可显式选 `paraformer`、`paraformer-onnx`，另有 `sensevoice`、`sensevoice-onnx` |
| `model_id` | string | 否 | 自定义底层模型 ID |
| `fast` | boolean | 否 | 单人快速模式；关闭 diarization，不改变所选模型（省略 `model` 时仍为 MOSS） |
| `quantize` | boolean | 否 | ONNX 模式是否启用 INT8 量化 |
| `hotwords` | string[] | 否 | MOSS-MLX 热词，最多 30 个；FunASR 路径会明确报不支持 |
| `extract_slides` | boolean/null | 否 | 视频默认自动截图；`false` 显式跳过；`true` 显式提取 |
| `slide_threshold` | number/null | 否 | 场景检测阈值；省略（null）时使用服务默认 20.0（与提取器/CLI 同一权威源），显式传入时覆盖 |
| `include_summary_prompt` | boolean | 否 | 是否准备 AI 总结提示词，默认 true |

> 保留的 `paraformer-onnx` 单人和多人路径都会先使用 ONNX VAD 分段，再补做 ONNX 文本清理、标点恢复和句子级时间戳映射；`diarize=false` 时使用全局标点恢复，`diarize=true` 时使用逐段标点并额外执行 CAM++ 说话人聚类。
> 默认文本源为清理后的 `preds`；如需回退到 `raw_tokens`，可在启动服务前设置 `FUNASR_ONNX_TEXT_SOURCE=raw_tokens`。
> ONNX 句子级时间戳通过字符比例近似映射 token 时间戳，适合段落级定位，不代表逐字强对齐。
> 默认 `moss-mlx` 仅支持 Apple Silicon。短录音由模型同时生成转写、时间戳和匿名说话人；长录音按约 600 秒分段，再用 CAM++ 声纹链接跨段标签。可在启动服务前设置 `FUNASR_MOSS_MODEL_ID` 指向本地权重目录，或设置 `FUNASR_MOSS_CHUNK_SECONDS=300` 缩短分段（限制 60–600 秒）。说话人匹配为启发式，输出须人工复核。非 Apple Silicon 可设置 `FUNASR_SERVER_DEFAULT_MODEL=paraformer` 启动旧管线服务；CLI 还需显式传 `--model paraformer`，API 请求也可显式传 `"model": "paraformer"`。不会静默回退。

**支持的格式**

- **视频**：mp4, avi, mov, mkv, wmv, webm
- **音频**：mp3, wav, m4a, flac, aac, opus, wma, caf

**响应示例（成功）**

```json
{
  "success": true,
  "output_path": "/path/to/audio.md",
  "text": "这是转录的文本内容...",
  "sentence_count": 25,
  "resolved_model": "moss-mlx",
  "resolved_runtime": "mlx",
  "warnings": []
}
```

**响应字段**

| 字段 | 类型 | 描述 |
|------|------|------|
| `success` | boolean | 转录是否成功 |
| `output_path` | string | 生成的 Markdown 文件路径 |
| `text` | string | 转录的纯文本内容 |
| `sentence_count` | integer | 转录句子数量 |
| `resolved_model` | string | 最终生效的逻辑模型 |
| `resolved_runtime` | string | 最终运行时（`mlx` / `torch` / `onnx`） |
| `warnings` | array | 自动路由或兼容性提示 |
| `timings` | object | 阶段墙钟耗时（秒）；`total_s` 为请求整体耗时 |
| `speaker_scope` | string/null | MOSS 返回 `global`（文件内匿名标签）或 `none` |
| `segments` | array/null | MOSS 结构化段：`start/end` 秒、`speaker`、`text` |
| `speaker_identification` | object/null | MOSS diarize 时逐人返回：文件内标签 → `{"name","score"}`（score 为归一化余弦相似度，达阈值才命中）或 `null`；空库全部为 `null` |
| `speaker_states` | object/null | MOSS diarize 时逐人返回：`{"status": "matched"/"unknown"/"insufficient_audio"/"extraction_failed"/"disabled", "name", "detail"}`；认领流程只对 `unknown` 执行 |
| `speaker_embeddings` | object/null | MOSS：文件内标签 → 单位声纹向量（192 维，认领注册用；默认输出不倾倒给人类终端） |
| `error` | string | 错误信息（仅失败时返回） |

**响应示例（失败）**

```json
{
  "success": false,
  "error": "文件不存在: /path/to/audio.mp3"
}
```

**完整示例**

```bash
# 基础转录
curl -X POST http://127.0.0.1:8765/transcribe \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/path/to/audio.mp3"}'

# 指定输出路径
curl -X POST http://127.0.0.1:8765/transcribe \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/path/to/video.mp4", "output_path": "/path/to/transcript.md"}'

# 启用说话人分离
curl -X POST http://127.0.0.1:8765/transcribe \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/path/to/meeting.m4a", "diarize": true}'

# Paraformer ONNX + diarization
curl -X POST http://127.0.0.1:8765/transcribe \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/path/to/meeting.m4a", "model": "paraformer-onnx", "diarize": true}'

# Paraformer ONNX 单人路径（VAD 分段 ASR，不做说话人聚类）
curl -X POST http://127.0.0.1:8765/transcribe \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/path/to/course.m4a", "model": "paraformer-onnx", "diarize": false}'

# MOSS-MLX：匿名说话人、时间戳与热词
curl -X POST http://127.0.0.1:8765/transcribe \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/path/to/meeting.m4a", "model": "moss-mlx", "hotwords": ["请求权基础", "DeepSeek"], "include_summary_prompt": false}'

# 单人快速模式（关闭说话人分离，仍使用默认 MOSS）
curl -X POST http://127.0.0.1:8765/transcribe \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/path/to/course.m4a", "fast": true}'
```

## 3. 批量转录

转录目录中的所有支持文件。

**请求**

```bash
POST /batch_transcribe
Content-Type: application/json

{
  "directory": "/path/to/media_folder",
  "output_dir": "/path/to/output_folder",
  "diarize": true
}
```

**请求参数**

| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `directory` | string | 是 | 要转录的目录绝对路径 |
| `output_dir` | string | 否 | 输出目录（默认：同输入目录） |
| `diarize` | boolean | 否 | 是否启用说话人分离（默认：true） |
| `model` | string | 否 | 省略时默认 `moss-mlx`；可显式选择旧 FunASR 管线 |
| `fast` | boolean | 否 | 单人快速模式 |

**响应示例（成功）**

```json
{
  "success": true,
  "total": 3,
  "results": [
    {
      "file": "/path/to/audio1.mp3",
      "output": "/path/to/output/audio1.md",
      "success": true
    },
    {
      "file": "/path/to/audio2.wav",
      "output": "/path/to/output/audio2.md",
      "success": true
    },
    {
      "file": "/path/to/video.mp4",
      "output": "/path/to/output/video.md",
      "success": false,
      "error": "文件格式不支持"
    }
  ]
}
```

**响应字段**

| 字段 | 类型 | 描述 |
|------|------|------|
| `success` | boolean | 批量操作是否成功 |
| `total` | integer | 要转录的文件总数 |
| `results` | array | 每个文件的转录结果 |
| `results[].file` | string | 原始文件路径 |
| `results[].output` | string | 输出文件路径（仅成功时） |
| `results[].success` | boolean | 单文件转录是否成功 |
| `results[].error` | string | 错误信息（仅失败时） |
| `error` | string | 批量操作错误信息（仅失败时返回） |

**完整示例**

```bash
# 批量转录目录
curl -X POST http://127.0.0.1:8765/batch_transcribe \
  -H "Content-Type: application/json" \
  -d '{"directory": "/path/to/media_folder"}'

# 指定输出目录
curl -X POST http://127.0.0.1:8765/batch_transcribe \
  -H "Content-Type: application/json" \
  -d '{"directory": "/path/to/media_folder", "output_dir": "/path/to/output"}'

# 启用说话人分离
curl -X POST http://127.0.0.1:8765/batch_transcribe \
  -H "Content-Type: application/json" \
  -d '{"directory": "/path/to/meetings", "diarize": true}'

# 批量单人快速模式（关闭说话人分离，仍使用默认 MOSS）
curl -X POST http://127.0.0.1:8765/batch_transcribe \
  -H "Content-Type: application/json" \
  -d '{"directory": "/path/to/courses", "fast": true}'
```

## 4. AI 总结功能（Claude Code 环境）

转录完成后，可以使用 AI 总结功能对转录内容进行智能分析和总结。

**注意**：AI 总结功能专为 Claude Code 环境设计，使用 Claude 的原生 AI 能力，无需配置外部 API。

### 4.1 工作流程

1. 执行转录命令
2. 转录完成后自动生成总结提示词
3. 将提示词发送给 Claude AI 生成结构化总结
4. Claude 返回 JSON 格式的总结结果
5. 将总结注入到 Markdown 文件

### 4.2 使用方法

#### 默认模式（推荐）

```bash
# 转录单个文件（自动启用总结）
python scripts/transcribe.py /path/to/audio.mp3

# 启用说话人分离并生成总结
python scripts/transcribe.py /path/to/meeting.m4a --diarize
```

转录完成后会自动显示总结提示词。

#### 禁用总结

```bash
# 转录但不生成总结
python scripts/transcribe.py /path/to/audio.mp3 --no-summary
```

### 4.3 总结内容结构

AI 总结功能会生成：

1. **全文总结** - 至少 400 字，分成 2-3 段，包含背景、问题、关键事实、数据、风险与行动建议
2. **发言人总结** - 每个发言人的观点、依据、数据、态度与潜在影响（至少 180 字/人）
3. **重点内容** - 6-10 条重点，每条 60-100 字，明确事实/数据/结论/行动
4. **关键词** - 5-8 个关键词

总结结果会直接插入到转录的 Markdown 文件中，使用 `<!-- AI-SUMMARY:START -->` 和 `<!-- AI-SUMMARY:END -->` 标记。

### 4.4 提示词特点

- 专门针对中文口语化对话优化
- 保留发言人上下文和对话流程（提取文本时保留每行的发言标签归属）
- 要求 `speaker_order` 逐字使用逐字稿行首的发言标签（`发言人N` 或实名），不得改写、合并或新造
- 结构化 JSON 输出便于解析和格式化

### 4.5 示例

**转录输出示例**：

```text
✅ 转录完成
📄 输出: /path/to/audio.md
📝 句子数: 25

🤖 正在准备 AI 总结...

============================================================
📋 请将以下提示词发送给 Claude AI 以生成总结：
============================================================
你是一位擅长处理口语化中文对话的专业纪要分析师。请从非结构化逐字稿中提炼事件脉络、各方观点、关键数据和行动建议，保持客观，不捏造信息。

请阅读以下逐字稿，输出 JSON 结果，其结构必须为：
{
  "full_summary": "至少400字，分成2-3段，交代背景、问题、关键事实、数据、风险与行动建议",
  "speaker_summary": [
    {
      "speaker_order": "逐字使用逐字稿中行首的发言标签，例如 发言人1 或实名",
      "speaker_name": "如能识别请写姓名，否则写未知",
      "summary": "至少180字，涵盖该发言人的观点、依据、数据、态度与潜在影响"
    }
  ],
  "highlights": ["6-10条重点，每条60-100字，明确事实/数据/结论/行动"],
  "keywords": ["5-8个关键词"]
}

要求：
- speaker_summary 必须覆盖逐字稿中出现的每一位发言人，不得遗漏、重复或虚构。
- speaker_order 必须逐字使用逐字稿行首的发言标签（如"发言人1"、"杨律师"），不得改写、合并或新造标签。
- 每条总结只基于该发言人的实际发言，不得把他人观点归属给该发言人。

以下是完整文本：
[转录文本内容...]

请输出 JSON 格式的总结。
============================================================
```

## 5. 声纹端点

声纹库文件 `assets/speaker-profiles.json` 属本地个人数据（.gitignore 排除）。读写由服务与 CLI 共用的存储层保护：注册向量按当前模型（CAM++，192 维）显式校验；写入为原子替换并加进程间锁；库损坏时读路径降级告警、写路径拒绝并保留原件；库与锁文件仅当前用户可读写。

### POST /speaker/register

认领注册：把转录响应 `speaker_embeddings` 中某标签的向量以指定名称写入声纹库。同名重复注册视为重新认领，覆盖旧向量。

```bash
curl -s -X POST http://127.0.0.1:8765/speaker/register \
  -H "Content-Type: application/json" \
  -d '{"name": "杨律师", "embedding": [...192 维数组...], "source_file": "meeting.m4a", "source_label": "S01"}'
```

| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `name` | string | 是 | 说话人名称（非空） |
| `embedding` | number[] | 是 | 声纹向量；必须为当前模型维度（192）、数值有限、范数有效 |
| `source_file` | string | 否 | 认领来源录音名 |
| `source_label` | string | 否 | 认领来源文件内标签（如 S01） |

响应：`{"success": true, "name": "...", "replaced": bool, "total": n}`。

**错误语义**：`400` = name 为空或向量校验失败（维度不符/含 NaN·Inf/float32 溢出/零向量，detail 给出具体原因）；`409` = 声纹库损坏，拒绝写入以保护原有记录（此时应人工检查库文件，不会被静默当作空库覆盖）。

### GET /speaker/list

列出声纹库（不含向量本体）。响应含 `total`、`profiles`（name/created_at/source_file/source_label/dim/model）及坏条目信息：`isolated_count`、`isolated_issues`（坏条目原因，不含向量原文）、`corrupt`（库整体是否损坏）。

### POST /speaker/remove

按名称删除；`404` = 无此说话人；`409` = 库损坏拒绝写入。历史坏条目不会被删除操作顺带清理。

### POST /speaker/test

提取一段音频的声纹并与库比对。`score` 为归一化向量的**余弦相似度（声纹相似度）**，不是经过校准的身份正确概率，也不是证据级身份认定。

响应字段：`scores`（每个注册名一条，向量维度不一致时 `score` 为 null 并附 note）、`best`（最高分候选）、`best_is_match`（best 是否达到阈值）、`identified`（达到阈值时为 `{"name","score"}`，否则 null——最高分低于阈值时明确"未识别"，不把最佳候选当命中）、`threshold`、`note`。

### 认领流程（Agent）

1. 转录响应中检查 `speaker_states`：只对 `unknown`（有声纹、未达阈值）执行认领；
2. 按 `segments` 为每位 `unknown` 说话人生成叙述，向用户确认身份；
3. 用户同意长期注册后注册：推荐入口为 `python3 scripts/speaker_registry.py claim <名字> --result <结果JSON> --label <标签>`（确定性取向量），或直接 POST `/speaker/register`；
4. `insufficient_audio`/`extraction_failed`/`disabled` 无合格向量或未启用，不得引导用户注册——前者只能根据用户说明在 Markdown 中为本稿标注。

CLI 等价：`speaker_registry.py list / remove / claim / test`；`remove` 与 `list` 直接读写库文件无需服务，`claim`/`test` 需服务运行。声纹属敏感个人信息：注册本人无合规障碍；注册客户或第三方须先取得其单独同意。
