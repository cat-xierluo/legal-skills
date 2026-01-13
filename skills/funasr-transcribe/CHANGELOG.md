# 变更日志

本项目的所有重要变更都将记录在此文件。

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
