---
name: funasr-transcribe
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.6.0"
license: Complete terms in LICENSE.txt
description: 使用本地 FunASR 服务将音频或视频文件转录为带时间戳的 Markdown 文件，支持 mp4、mov、mp3、wav、m4a 等常见格式。本技能应在用户需要语音转文字、会议记录、视频字幕、播客转录时使用。
---
# FunASR 语音转文字

本 skill 提供本地语音识别服务，将音频或视频文件转换为结构化的 Markdown 文档。

## 功能概述

- 支持多种音视频格式（mp4、mov、mp3、wav、m4a、flac 等）
- 自动生成时间戳
- 支持说话人分离（diarization，默认启用）
- **视频关键帧截图提取**：自动检测并提取 PPT 幻灯片，插入到转录稿对应位置
- 转录后自动附带 AI 总结提示词，Agent 可一步完成总结
- 输出 Markdown 格式，便于阅读和编辑

## Agent 默认工作流（转录 + 自动总结）

当用户请求转录音频/视频时，应遵循以下流程，**一次性完成转录和 AI 总结**：

### 步骤 0：环境检测（自动）

在执行转录前，检查 skill 目录下是否存在 `skill-env.json`。如果不存在，先运行环境检测：

```bash
cd <skill目录> && python3 scripts/init_env.py
```

如果检测失败（退出码非0），按提示运行安装脚本：

```bash
cd <skill目录> && python3 scripts/setup.py
```

安装完成后会自动重新检测并生成 `skill-env.json`。

### 步骤 1：启动/检查服务

```bash
curl -s http://127.0.0.1:8765/health
```

如果服务未运行，后台启动：

```bash
cd <skill目录> && python3 scripts/server.py --idle-timeout 600 &
```

等待服务就绪（轮询 `/health` 直到返回 200）。

### 步骤 2：转录文件

```bash
curl -s -X POST http://127.0.0.1:8765/transcribe \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/path/to/audio.aac"}'
```

> 注意：`diarize` 默认为 `true`，无需显式传入。如需禁用，传 `"diarize": false`。

响应中包含以下关键字段：
- `output_path`: 转录输出的 Markdown 文件路径
- `text`: 转录全文
- `summary_prompt`: AI 总结提示词（**已自动附带**，无需额外调用 `/summary`）
- `text_preview`: 转录文本前 500 字预览

### 步骤 3：生成 AI 总结

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

### 步骤 4：注入总结到文件

将生成的总结格式化为 Markdown，调用 `/inject_summary` 注入：

```bash
curl -s -X POST http://127.0.0.1:8765/inject_summary \
  -H "Content-Type: application/json" \
  -d '{
    "md_path": "/path/to/audio.md",
    "summary_content": "## AI 摘要\n\n### 全文总结\n...\n\n### 发言人总结\n...\n\n### 重点内容\n...\n\n### 关键词\n..."
  }'
```

### 完整流程示例

```
用户：转录这个音频
  ↓
Agent：
  1. 检查/启动服务
  2. POST /transcribe {"file_path": "xxx.aac"}  ← 一次调用拿到转录+提示词
  3. 根据转录内容直接生成总结 JSON
  4. POST /inject_summary 注入总结
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
python3 scripts/setup.py
```

安装脚本会自动：

1. 检查 Python 版本（需要 >= 3.8）
2. 安装依赖包（FastAPI、Uvicorn、FunASR、PyTorch）
3. 下载 ASR 模型到 `~/.cache/modelscope/hub/models/`

验证安装状态：

```bash
python3 scripts/setup.py --verify
```

### 启动转录服务

```bash
python3 scripts/server.py
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

# 批量转录目录
python3 scripts/transcribe.py /path/to/media_folder/

# 提取视频关键帧截图（PPT幻灯片）
python3 scripts/transcribe.py /path/to/video.mp4 --slides

# 自定义场景检测阈值（值越低越灵敏，默认27.0）
python3 scripts/transcribe.py /path/to/video.mp4 --slides --slide-threshold 20.0
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
  "service": "FunASR Transcribe",
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
| `scripts/transcribe.py`    | 命令行客户端                        |
| `scripts/auto_transcribe.py` | **自动化转录脚本（推荐）**         |

---

## 自动转录 + 总结流程

本 skill 支持在任意 Agent 平台中自动完成**转录 + 总结**全流程。

### 方式一：使用自动化脚本（推荐）

```bash
# 自动转录 + 获取总结提示词（说话人分离默认启用）
python3 scripts/auto_transcribe.py /path/to/audio.aac

# 禁用说话人分离
python3 scripts/auto_transcribe.py /path/to/audio.aac --no-diarize

# 只获取总结提示词，不生成总结
python3 scripts/auto_transcribe.py /path/to/audio.aac --prompt-only
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
- VAD 模型 - 4MB
- 标点模型 - 283MB
- 说话人分离模型 - 28MB

## 故障排除

**视频截图功能依赖：**

如需使用 `--slides` 视频关键帧提取功能，需额外安装：
```bash
pip install scenedetect[opencv] imagehash
```
如未安装，服务端会输出提示但不影响普通转录功能。

服务启动失败时，运行验证命令检查安装状态：

```bash
python3 scripts/setup.py --verify
```

重新下载模型：

```bash
python3 scripts/setup.py --skip-deps
```
