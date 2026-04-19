# API 参考文档

## 端点列表

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/transcribe` | 转录单个文件 |
| POST | `/batch_transcribe` | 批量转录目录 |

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
  "service": "FunASR Transcribe",
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
  "model": "paraformer-onnx",
  "fast": false
}
```

**请求参数**

| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `file_path` | string | 是 | 要转录的文件绝对路径 |
| `output_path` | string | 否 | 输出 Markdown 文件路径（默认：原文件同目录下的 .md 文件） |
| `diarize` | boolean | 否 | 是否启用说话人分离（默认：true） |
| `model` | string | 否 | 逻辑模型名：`paraformer`、`paraformer-onnx`、`sensevoice`、`sensevoice-onnx` |
| `model_id` | string | 否 | 自定义底层模型 ID |
| `fast` | boolean | 否 | 单人快速模式；关闭 diarization，默认保留 `paraformer` |
| `quantize` | boolean | 否 | ONNX 模式是否启用 INT8 量化 |

> `paraformer-onnx` 单人和多人路径都会先使用 ONNX VAD 分段，再补做 ONNX 文本清理、标点恢复和句子级时间戳映射；`diarize=false` 时使用全局标点恢复，`diarize=true` 时使用逐段标点并额外执行 CAM++ 说话人聚类。质量优先时仍建议使用原生 `paraformer`。
> 默认文本源为清理后的 `preds`；如需回退到 `raw_tokens`，可在启动服务前设置 `FUNASR_ONNX_TEXT_SOURCE=raw_tokens`。

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
  "resolved_model": "paraformer-onnx",
  "resolved_runtime": "onnx",
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
| `resolved_runtime` | string | 最终运行时（`torch` / `onnx`） |
| `warnings` | array | 自动路由或兼容性提示 |
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

# 单人快速模式（关闭说话人分离，保留默认 Paraformer）
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
  "diarize": true,
  "model": "paraformer"
}
```

**请求参数**

| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `directory` | string | 是 | 要转录的目录绝对路径 |
| `output_dir` | string | 否 | 输出目录（默认：同输入目录） |
| `diarize` | boolean | 否 | 是否启用说话人分离（默认：true） |
| `model` | string | 否 | 逻辑模型名 |
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

# 批量单人快速模式（关闭说话人分离，保留默认 Paraformer）
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
- 保留发言人上下文和对话流程
- 自动识别发言人顺序（speaker_0, speaker_1 等）
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
      "speaker_order": "发言人1",
      "speaker_name": "如能识别请写姓名，否则写未知",
      "summary": "至少180字，涵盖该发言人的观点、依据、数据、态度与潜在影响"
    }
  ],
  "highlights": ["6-10条重点，每条60-100字，明确事实/数据/结论/行动"],
  "keywords": ["5-8个关键词"]
}

请确保逐字稿中出现的每一位发言人（发言人1、发言人2……）都提供总结，不得遗漏或虚构。

以下是完整文本：
[转录文本内容...]

请输出 JSON 格式的总结。
============================================================
```
