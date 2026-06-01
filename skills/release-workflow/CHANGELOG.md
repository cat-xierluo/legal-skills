# 变更日志

## [1.1.1] - 2026-06-01

### 变更

- Release Notes 模板移除正文顶部的版本标题，避免与 GitHub Release 页面标题重复。
- 发布完成检查清单增加“正文没有重复版本标题”的要求。

## [1.1.0] - 2026-05-20

### 变更

- SKILL.md 从 Tauri 专用改为通用发布工作流，适用于桌面应用、CLI 工具、Web 应用、库/SDK 等任何 GitHub 项目
- Tauri 特定内容下沉到 `references/tauri-release.md`
- CI 故障排查改为通用指南，不再绑定 Tauri
- 新增 `references/release-notes-guide.md`：Release Notes 撰写指南（含模板、设计决策、不同项目类型适配）

### 新增

- `references/tauri-release.md` 新增「常见配置问题与优化」章节（6 个问题），来源于 Funes 项目审查
- `references/tauri-release.md` 参考项目表格增加 Folia 和 Funes 对比

## [1.0.0] - 2026-05-20

### 新增

- SKILL.md：7 步发布流程 + Release Notes 模板
- references/ci-troubleshooting.md：CI 故障排查
- 通过 Folia v0.3.7 发布验证全流程
