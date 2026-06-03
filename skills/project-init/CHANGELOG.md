# Changelog

All notable changes to this project will be documented in this file.

## [v1.1.1] - 2026-06-03

### Changed
- **TASKS.md 模板：** 任务编号从 `#` 改为显式的 `Task-NNN` 格式（`Task-001`、`Task-002` …），跨文档全局唯一。原 `ISS-NNN` 写法不再使用，因多个 Task 常对应同一 Issue/PR，容易造成 1:1 映射的歧义。

## [v1.1.0] - 2026-06-01

### Changed
- **精简项目类型为 4 种：** 开发项目、Skill 开发、法律文档、内容写作；移除前端和数据分析两个 profile
- **开发项目：** 新增 git-workflow、release-workflow、multi-agent-orchestration、cross-agent-coordination、agent-email；移除 skill-lint、repo-research
- **法律文档项目：** 用 legal-ocr 替代 mineru-ocr + paddle-ocr；新增 pdf-processor、pdf-organizer、img2pdf、yuandian-law-search
- **移除 private-skills 和 myagents 技能源**，仅保留 legal-skills

## [v1.0.0] - 2026-05-16

### Added
- **项目类型检测：** 自动识别 6 种项目类型（开发、Skill、前端、数据分析、法律文档、内容写作）
- **配置驱动：** YAML 格式配置文件，支持自定义项目类型、Skill 列表和检测规则
- **Skill 安装：** 委托 skill-manager 处理符号链接创建
- **CLAUDE.md 生成指南：** 6 种项目类型的段落定义、结构模板和脱敏范例（simple / development / frontend / comprehensive-development / data-analysis / skill-project），通过 `@include ~/.claude/CLAUDE.md` 引入全局协议
- **大型项目可选段落：** 架构分层、禁止事项、测试层级、并行调度、实施范围说明等结构模板，按需组装
- **项目文档模板：** ROADMAP.md、DECISIONS.md、TASKS.md、ARCHITECTURE.md、DESIGN.md、CHANGELOG.md，格式对齐全局协议
- **settings 模板：** 权限配置参考模板
- **.gitignore 模板：** 通用 gitignore 模板
- **Skill 项目脚手架：** 目录结构 + SKILL.md 模板 + LICENSE.txt
- **示例配置：** profiles.example.yaml 供其他用户自定义
