# 变更日志

## [1.2.0] - 2026-06-08

### 新增

- 新增 `## ⚠️ Release ≠ 测试 — 强制约束` 章节：把 release workflow 当作 CI 验证机制（"打 tag 看一下"）是反模式，强制禁止。
- 新增打 tag 前五问自检清单：是否给真实用户、CHANGELOG 是否就绪、距上次 tag 是否 ≥ 24h、是否有实质改动、能否合并到下次。
- 新增反模式表（7 类禁止行为）+ 借口反驳表（9 类常见借口）+ 红灯列表（7 类立即停止信号）。
- `description` 触发词补充："Actions 配额告急"、"短时间内多次发版"、"打 tag 看一下"等反模式场景。

### 变更

- 发布完成检查清单拆分为"打 tag 前（强制）"和"发布完成后"两段，强制自检放在前。
- 适用场景从"完整发布周期"扩展为"包含反模式识别和拒绝"。

### 触发背景

Folia 项目在 2026-06 账单周期（6/1-6/30）使用 1825/2000 Actions 分钟（91%），根因是把 release workflow 当作 CI 验证机制使用：6/1 一天发 3 个 patch 版本，22 天发 15 个版本，其中大部分是"看一下 build 行不行"而非真实用户发布。

## [1.1.2] - 2026-06-01

### 变更

- 固定桌面应用 Release Notes 结构为摘要、Highlights、新增、变更、修复、Warning、下载和完整变更日志。
- 新增 `release_notes` 项目配置示例，用于为 Folia 等项目指定专门的 Release Notes profile 和必备分区。

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
