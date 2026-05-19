# Changelog

All notable changes to this project will be documented in this file.

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
