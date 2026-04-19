# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/lang/zh-CN/).

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
