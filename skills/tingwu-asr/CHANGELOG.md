# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/lang/zh-CN/).

## [0.3.0] - 2026-07-19

### Added
- 给链接自动转录:`paths` 支持 http(s) 链接,自动用 yt-dlp 下载(小宇宙 episode、YouTube、B站等),无需手动下载音频
- SKILL.md 补充「链接转写与说话人分离」设计取舍说明

### Changed
- `--speakers` 默认值确认为 2:经实测听悟 roleSplitNum **仅 `2` 为有效分离值(分 2 人)**,`3` 与 `4` 均不分离(原注释"4=多人"为误注,已更正)
- `requirements.txt` 补充 yt-dlp 依赖

### 已知限制(Playwright 实测听悟网页端 API 确认)
- 听悟网页端「播客链接转写」(底层 net_source 网络源通道)的「区分发言人」选项**不生效**:即使选中"多人讨论",提交的 roleSplitNum 仍被强制为 0,结果不做分离。故 skill 给链接时走"yt-dlp 下载 → 本地上传"路径以保证分离生效
- roleSplitNum **仅 `2` 有效(分 2 人)**,`0/1/3/4` 实测均不分离

## [0.2.0] - 2026-04-20

### Added
- 多文件并行转录：支持传入多个文件路径，自动并行上传（最大并发数可通过 `--parallel` 参数控制，默认3）
- 转录结果双路径保存：结果同时保存到源文件所在目录和 archive 目录
- `--parallel N` 参数：指定并行转录的最大文件数

### Changed
- CLI 参数 `path` 改为 `paths`，支持多个文件路径
- 批量模式（`--batch`）下目录内的文件也会并行处理

## [0.1.0] - 2026-04-18

### Added
- 核心功能：通过逆向通义听悟网页端 REST API 实现云端音频/视频转录
- 完整 6 步 API 流程：generatePutLink → OSS STS 上传 → syncPutLink → startTrans → 轮询状态 → getTransResult
- 支持语言：中文、英文、日文、粤语、中英文混合
- 说话人分离：不区分 / 单人 / 两人 / 多人
- 输出 funasr-transcribe 兼容的 Markdown 格式
- Playwright Cookie 提取登录（`login.py`）
- Cookie 认证检查（`check_auth.py`）
- 批量转录模式（`--batch`）
- 转录结果归档到 `archive/` 目录
- 复用 funasr-transcribe 的 `summary.py` 注入 AI 总结
