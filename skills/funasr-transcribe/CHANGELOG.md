# 变更日志

本项目的所有重要变更都将记录在此文件。

## [1.4.0] - 2026-04-05

### 改进

- **说话人分离默认启用** — `diarize` 参数默认值从 `false` 改为 `true`
  - 两方以上对话是常态，默认启用更符合实际使用场景
  - CLI 新增 `--no-diarize` 参数用于显式禁用
- **转录后自动附带总结提示词** — `/transcribe` 响应新增 `summary_prompt` 和 `text_preview` 字段
  - Agent 一次调用即可拿到转录结果 + 总结提示词，无需额外请求 `/summary`
  - 直接生成总结 JSON 后调用 `/inject_summary` 即可完成全流程
- **SKILL.md 新增默认工作流** — 平台无关的 Agent 工作流章节，任何 Agent 平台均可遵循
- **移除环境检测** — 删除 `detect_agent_environment()` 函数，总结由 Agent 自行完成，server 无需感知运行平台

### 清理

- 移除 `detect_agent_environment()` 环境检测函数，server 无需感知运行平台
- 移除 SKILL.md 中对特定平台的绑定描述（OpenClaw、Claude Code 等）
- 移除 Nano/E2E 模型死代码（`get_model_type()` 函数、`init_model()` 中的 E2E 分支、`--model` 参数）
- 移除 `models.json` 中不可用的 Nano 模型条目
- 移除 `--claude-code` 参数（功能已被 `/transcribe` 返回 `summary_prompt` 取代）
- 移除未使用的全局变量 `model`/`model_with_spk` 和 `inject_summary_to_file` 导入
- 修复 API 文档字符串中 `diarize` 默认值描述（false → true）
- 简化 `transcribe.py` 帮助文本，移除 Nano 模型示例

## [1.3.0] - 2026-04-05

### 新增

- **视频关键帧（PPT 幻灯片）自动提取** — 转录视频时可同时提取画面变化截图
  - 四层过滤流水线：场景检测+兜底采样 → pHash 去重 → 空白回查补帧 → 最终过滤
  - PySceneDetect 检测画面变化 + 每 3 分钟兜底采样防止空白
  - 5 分钟以上无变化区域自动回查补帧
  - 截图插入转录文本对应时间戳位置
  - 通过 `--slides` 参数启用
- **转录归档（Archive）机制** — 每次转录自动归档完整记录
  - 归档目录：`archive/YYYYMMDD_HHMMSS_文件名/`
  - 包含：Markdown 副本、截图副本（如有）、`transcription_meta.json` 元数据
  - API 响应新增 `archive_path` 字段

### 改进

- `result_to_markdown()` 支持在转录段落间插入截图引用
- `/transcribe` 端点新增 `extract_slides`、`slide_threshold` 参数
- `auto_transcribe.py` 新增 `--slides`、`--slide-threshold` 命令行参数
- `assets/requirements.txt` 新增 `scenedetect[opencv]`、`imagehash` 依赖

### 依赖

- `scenedetect[opencv]>=0.6.4` — 视频场景检测
- `imagehash>=4.3.1` — 感知哈希去重

## [1.2.0] - 2026-02-14

### 修复

- **时间戳分段输出** - 修复非说话人分离模式下转录结果为整段文本的问题
  - 之前：FunASR 返回 `timestamp` 字段而非 `sentence_info`，导致代码 fallback 到整段输出
  - 现在：正确处理 `timestamp` 字段，按句子（。！？）分割文本并分配时间戳
  - 新增 `split_text_by_sentences()` 函数，支持中文句子分割

### 技术变更

- `result_to_markdown()` 函数重构，新增 `timestamp` 字段处理分支
- 根据字符位置比例计算每个句子对应的时间戳索引
- 支持处理没有结束符的剩余文本段落

### 效果对比

- 修复前：1 个大段落，时间戳固定为 00:00
- 修复后：按句子分成 74 个段落，每个段落有对应的准确时间戳

## [1.1.1] - 2025-01-07

### 改进

- **代码精简** - summary.py 从 475 行精简到 285 行(-40%)
  - 移除所有外部 API 集成代码(OpenAI, SiliconFlow)
  - 移除环境变量加载和配置文件处理
  - 专注 Claude Code 环境原生能力

### 功能优化

- **默认启用总结** - 转录完成后自动显示总结提示词
- **简化参数** - 移除 `--summary`,新增 `--no-summary` 禁用选项
- **移除配置** - 删除 `config/summarization.env`(无需外部 API 配置)
- **优化交互** - 移除 input() 交互,直接输出提示词供 Claude 使用

### 技术变更

- summary.py 专注 Claude Code 环境功能
- transcribe.py 默认启用总结流程
- 清理所有外部 API 依赖代码

## [1.1.0] - 2025-01-07

### 新增

- **AI 智能总结功能** - 转录完成后可自动生成结构化会议纪要
- **Claude Code 环境原生支持** - 使用 Claude Code 内置 AI 能力生成总结,无需外部 API
- **结构化总结输出** - 包含全文总结、发言人总结、重点内容、关键词等模块
- **说话人视角识别** - 自动识别发言人顺序并保留对话上下文
- **总结注入功能** - 自动将生成的总结注入到 Markdown 文件的对应位置
- **交互式总结流程** - 转录完成后自动提示是否需要生成 AI 总结

### 技术实现

- **summary.py** - AI 总结工具模块
  - `summarize_file_for_claude()` - 为 Claude Code 环境准备总结提示词
  - `inject_summary_to_file()` - 将总结注入到 Markdown 文件
  - `get_transcription_text()` - 提取纯文本转录内容
  - `create_summary_prompt()` - 生成结构化总结提示词
  - `_extract_speaker_orders()` - 智能识别发言人顺序
  - `_build_summary_markdown()` - 构建 Markdown 格式总结
- **中文对话优化** - 专门针对中文口语化对话的提示词模板
- **JSON 结构化输出** - 支持解析和格式化 AI 生成的总结结果

### 总结内容

- **全文总结** - 400+ 字,包含背景、问题、关键事实
- **发言人总结** - 每个发言人的观点、态度和贡献
- **重点内容** - 6-10 条核心要点
- **关键词** - 5-8 个关键术语

### 使用改进

- 转录完成后自动提示是否生成总结
- 支持命令行参数 `--summary` 自动启用总结
- 交互式输入 AI 生成的总结结果
- 自动解析 JSON 或纯文本格式总结

### 依赖更新

- `openai` - AI 总结 API 支持（保留用于向后兼容）
- `httpx` - 异步 HTTP 客户端

## [1.0.0] - 2025-01-07

### 初始功能

- FunASR 语音转文字技能初始版本
- 支持多种音视频格式（mp4、mov、mp3、wav、m4a、flac、aac、opus、wma、caf）
- 自动生成带时间戳的 Markdown 转录结果
- 说话人分离（diarization）功能
- 单文件转录 API
- 批量目录转录 API
- 健康检查 API
- 一键安装脚本（自动检测系统环境）
- 自动下载和配置 ASR 模型

### 核心技术

- 基于 FunASR 和 ModelScope 的本地 ASR 服务
- FastAPI HTTP API 服务器（替代 Flask）
- Uvicorn ASGI 服务器
- VAD + ASR + Punctuation + Speaker Diarization 完整流程
- PyTorch 和 torchaudio 深度学习框架
- 自动模型缓存系统（~/.cache/modelscope/hub/models/）

### 智能特性

- **自动启动**：首次请求时自动加载模型
- **空闲关闭**：默认 10 分钟无活动后自动关闭以节约资源
- **可配置超时**：支持自定义空闲超时时间（--idle-timeout 参数）
- **后台监控**：独立的空闲监控线程
- **优雅关闭**：支持 SIGTERM/SIGINT 信号处理

### 文档

- 完整的 SKILL.md 使用指南
- 详细的 API 参考文档（references/api-reference.md）
- 交互式 Swagger UI 文档（/docs）
- 系统环境检测和故障排除指南
- 服务生命周期管理说明

### 服务架构

- RESTful API 设计
- Pydantic 数据模型验证
- HTTP 中件间自动活动时间跟踪
- 线程安全的模型管理
- 跨平台支持（Windows、macOS、Linux）
