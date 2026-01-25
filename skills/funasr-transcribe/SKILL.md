---
name: funasr-transcribe
description: 使用本地 FunASR 服务将音频或视频文件转录为带时间戳的 Markdown 文件，支持 mp4、mov、mp3、wav、m4a 等常见格式。本技能应在用户需要语音转文字、会议记录、视频字幕、播客转录时使用。
license: Complete terms in LICENSE.txt
---
# FunASR 语音转文字

本 skill 提供本地语音识别服务，将音频或视频文件转换为结构化的 Markdown 文档。

## 功能概述

- 支持多种音视频格式（mp4、mov、mp3、wav、m4a、flac 等）
- 自动生成时间戳
- 支持说话人分离（diarization）
- 输出 Markdown 格式，便于阅读和编辑

## 使用流程

### 首次使用：安装依赖和下载模型

运行安装脚本完成环境配置：

```bash
python scripts/setup.py
```

安装脚本会自动：

1. 检查 Python 版本（需要 >= 3.8）
2. 安装依赖包（FastAPI、Uvicorn、FunASR、PyTorch）
3. 下载 ASR 模型到 `~/.cache/modelscope/hub/models/`

验证安装状态：

```bash
python scripts/setup.py --verify
```

### 启动转录服务

```bash
python scripts/server.py
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
python scripts/server.py --idle-timeout 1800
```

### 执行转录

使用客户端脚本转录文件：

```bash
# 转录单个文件
python scripts/transcribe.py /path/to/audio.mp3

# 指定输出路径
python scripts/transcribe.py /path/to/video.mp4 -o transcript.md

# 启用说话人分离
python scripts/transcribe.py /path/to/meeting.m4a --diarize

# 批量转录目录
python scripts/transcribe.py /path/to/media_folder/
```

### AI 智能总结（Claude Code 环境）

转录完成后，可以生成 AI 智能总结，充分利用 Claude Code 的原生 AI 能力。

**工作流程：**

1. 执行转录后，脚本会自动准备总结提示词
2. 将提示词发送给 Claude AI 生成结构化总结
3. 将 Claude 返回的 JSON 结果粘贴回脚本
4. 自动将总结注入到 Markdown 文件

**使用方法：**

```bash
# 转录单个文件（会自动提示是否生成总结）
python scripts/transcribe.py /path/to/audio.mp3

# 启用说话人分离并生成总结
python scripts/transcribe.py /path/to/meeting.m4a --diarize --summary
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

| 脚本                      | 用途                   |
| ------------------------- | ---------------------- |
| `scripts/setup.py`      | 一键安装依赖和下载模型 |
| `scripts/server.py`     | 启动 HTTP API 服务     |
| `scripts/transcribe.py` | 命令行客户端           |

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

**示例格式：**

```markdown
# 转录：filename.mp4

## 转录内容

发言人1 00:00:01
这是第一句话的内容。

发言人2 00:00:05
这是第二句话的内容。
```

## 模型信息

模型存储在 ModelScope 默认缓存目录 `~/.cache/modelscope/hub/models/`：

- ASR 主模型 (Paraformer) - 867MB
- VAD 模型 - 4MB
- 标点模型 - 283MB
- 说话人分离模型 - 28MB

## 故障排除

服务启动失败时，运行验证命令检查安装状态：

```bash
python scripts/setup.py --verify
```

重新下载模型：

```bash
python scripts/setup.py --skip-deps
```
