# 变更日志

## [1.4.0] - 2026-06-30

### 新增

- **monorepo-skills 项目类型**：支持一次性发布多个 skill 的 zip（legal-skills 实例）。与现有 tauri / cli / web / library 类型并列，通过 `config/projects.yaml` 的 `type` 字段路由
- **新增脚本 `scripts/build-zips.sh`**：遍历 `skills/*/`、跳过 symlink 与已归档 skill、从 CHANGELOG 头部读 semver、用 `git archive --worktree-attributes` 干净打包到 `pack-skills/<skill>-<semver>.zip`
- **新增脚本 `scripts/release-monorepo.sh`**：主发布驱动（build → tag → push → gh run watch → 验证 assets），支持 `--dry-run` 模式（不消耗 Actions 配额）
- **新增 reference `references/monorepo-release.md`**：完整 SOP 文档，含端到端流程、关键设计决策、已知限制
- **新增 release-notes profile `monorepo-skills`**：与 desktop-standard 并列，适用于 GitHub Release 含 N 个 skill zip 的场景
- **`config/projects.yaml` 新增 `legal-skills` 条目**：定义 skills_root、output_dir、exclude_globs、CalVer tag 模板

### 改进

- `SKILL.md` description 触发词追加："monorepo"、"批量打包"、"多 skill 发布"、"skill zip"
- `SKILL.md` 新增「## 模式 B:monorepo 多组件批量发布」章节，与现有 7 步流程（模式 A）并列
- 现有 Folia/Funes/FaroPDF 等 monorepo subrepo 发布流程**完全未动**（仅追加式扩展）

### 触发背景

legal-skills 用户下载 skill 必须懂 Git（`git clone` + 手动 cp 子目录），门槛高。本版本把 release-workflow 扩展支持 monorepo 多 skill 批量发布，使每个 skill 可独立 zip 下载，无需 Git。详见 plan：`docs/plans/2026-06-30-ski-github-release.md`。

## [1.3.0] - 2026-06-20

### 新增

- **「修复 hotfix 与 CI retry 边界」章节**：明确 hotfix 真实修复 vs 把 release 当测试的判定信号；transient vs 真实 bug 快速判定清单（build job / publish job 各自的失败信号）；修复 hotfix 标准动作序列；重打 tag 总次数上限 3 次。来源：Folia v0.4.0 → v0.4.1 hotfix 真实案例，3 次重打 tag 后修好（双层根因：bundle.targets 缺 "app" + includeUpdaterJson: false）。
- **打 tag 前产物完整矩阵对照表**：三平台（darwin-aarch64 / darwin-x86_64 / windows-x86_64）逐行勾选安装包 / updater binary / .sig / latest.json entry。带自动更新项目必查——缺一个 sig 都让用户升不上 vX.Y.Z。
- **Step 3 加 `git show <tag> --stat` 校验**：重打 hotfix 时常见坑是只改了 release.yml 没把 4 处版本号文件升到新版本号，导致产物文件名仍带旧版本号（Folia v0.4.1 第一次重打的实际教训）。
- **Step 6 加产物完整矩阵对照**：发布前必须按矩阵逐行勾选，缺任一产物**不 publish draft release**，先修再重打。
- **Step 1 加 PATCH 注释 "hotfix patch"**：明确 PATCH 版本可以是新功能累积或 hotfix 单一修复。

### 变更

- 5 问自检从「软建议」升级为「AI 不得跳过的硬约束」：AI 代理被请求发布新版本时必须主动逐条打印结果让用户确认，明确禁止跳过（v0.4.0 真实教训）。
- `references/tauri-release.md`：`includeUpdaterJson` 示例值从 `false` 改为 `true`（项目启用 Tauri 自动更新时必须为 true，否则 macOS updater 产物链断裂），添加详细原因说明。
- `references/tauri-release.md` 新增「`tauri.conf.json` bundle.targets 必含 `"app"`」章节：解释 macOS updater binary 来源（"app" target 派生 `.app.tar.gz`），列出常见错配场景（DEC-093 收窄 target 时误删 "app"）。
- `references/tauri-release.md` 新增「打 tag 前产物完整矩阵预检」章节：把矩阵对照表与产物预检流程整合。
- `references/tauri-release.md` 现有产物表从「安装包 / 更新器产物 / 签名」三段扩展为包含 latest.json entry 的四列。
- `references/tauri-release.md` 第 8 个红线（在「跨平台 CI 必踩坑」后追加）：publish job 失败时按 `includeUpdaterJson` + `bundle.targets` 顺序排查产物链断裂。

### 触发背景

Folia v0.4.0 发布后用户实际收到 broken build（macOS 自动更新不可用），追溯根因时发现：

1. `bundle.targets` 在 DEC-093 收窄时误删了 `"app"` target（macOS updater binary 来源）
2. `release.yml` 的 `includeUpdaterJson: false` 让 tauri-action 不生成 `.sig`
3. skill 文档没有产物矩阵预检 + hotfix 边界 + 5 问硬约束，导致 AI 跳过了关键的发布前自检

v0.4.1 hotfix 经历 3 次重打 tag（首次修 release.yml、二次加 bundle.targets + 版本号同步、三次 retry transient CI 失败），每次都有真实进展但成本是 1.5× 标准 release。skill 改进后下次类似情况可以 1 次重打搞定。

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
