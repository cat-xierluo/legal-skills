# 更新日志

本文件记录 minimax-web-search 技能的所有重要变更。

## [0.1.0] - 2026-02-18

### 新增

- **初始版本**: minimax-web-search 技能
  - 通过 MiniMax MCP 进行网络搜索
  - 支持实时信息搜索、网络最新动态查询
  - 提供命令行和 Python API 两种调用方式

### 格式优化

- 按照 Skill 开发指南规范重构 SKILL.md
  - 添加 YAML frontmatter（name、description、license）
  - 添加依赖章节（系统依赖、Python 包）
  - 在 description 和正文中强调适用于 OpenClaw 平台
  - Claude Code 用户应在 description 中看到忽略提示
