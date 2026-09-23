# 变更日志

## [1.6.0] - 2026-09-21

### 新增

- **专家套件无清单发布链路**：新增 `validate-expert-suites.py`，直接以 `expert-suites/<id>/skills/*` 相对符号链接为成员真值，校验链接逃逸、目标跟踪状态、Skill 名称、README 成员表、版本下载链接和许可证，不引入 `suite.yaml`。
- **自包含套件 ZIP**：新增 `build-suite-zips.sh`，从指定 Git tree 导出成员真实目录，保留套件 README、CHANGELOG、LICENSE 和各成员许可证；产物命名为 `suite-<id>-<semver>.zip`，失败时不覆盖上一批完整产物。
- **确定性回归测试**：新增静态校验 7 项单测、README 回写 3 项离线单测和端到端打包 fixture，覆盖损坏链接阻断、符号链接展开、下载资产精确匹配、精确 tag 渲染、路径逃逸拦截、模拟安装与失败回滚。
- **Release Notes 专家套件适配**：`generate-release-notes.py` 新增「专家套件」清单节——遍历 `expert_suites_root`（默认 `expert-suites/`）下各套件的 README（标题/一句话简介）与 CHANGELOG（semver）并统计成员数；`{total}` 计数排除 `suite-` 前缀产物，新增 `{suites}` 占位符（套件数），杜绝套件 ZIP 混入 skill 总数。
- **README 版本列与改名死链自动回写**：`update-readme.py` 回写不再按链接自身 slug 映射，改为按**行内声明的技能名**（HTML 表行 `href="skills/<name>/"`、套件 md 行 `](../skills/<name>/)`）重映射——根治改名残留死链（如 skill-publish-sync 行曾长期指向旧名 clawhub-sync 的 zip）；同时把紧邻下载列的版本号列对齐到 zip 实际版本（含 `vA.B.C→vX.Y.Z` 区间写法），链接已最新而版本列滞后的存量状态重跑即可修复。独立仓库下载行（链接域名非本仓库）整行不动。v2026.09.21 存量实测：一次运行修复 1 个死链 + 对齐 25 处版本列，49 行全部三方一致。
- **README 结构性同步入册（发版必查环节）**：SKILL.md 模式 B 新增「README 结构性同步」段——自动回写只覆盖已有表行的链接与版本列，加行/分节归属/描述属结构性维护，发版时须跑覆盖校验 + 分节归属自查（通用工具不进法律专业应用节）+ 描述与 SKILL.md frontmatter 对齐；发布完成检查清单与 monorepo-release.md「发布后」清单同步加条。背景：v2026.08.06–09.21 期间 15 个技能缺行/缺链接、invoice-organizer 分节错位，均因发版环节无人负责 README 结构性维护（已另行修复，main 24c76d0286）。
- **README 覆盖校验脚本 `check-readme-coverage.py`**：对照最新 Release 资产与 README 技能表，缺行/缺链接即拦截（独立仓库下载行豁免，`--assets-json` 离线可用）——把"新技能漏维护 README 表格行"从静默缺失变成显式拦截（v2026.09.21 曾有 15 个技能缺行/缺链接达 46 天未被发现）。处置写入 `monorepo-release.md`「已知摩擦与处置」摩擦三。
- **套件成员链接对齐脚本 `align-suite-links.py`**：把"main 上 Skill 升版本 → 长期 PR merge main 后套件 README 成员链接过时 → validate 拦截"的处置固化为脚本（按各 Skill CHANGELOG 当前 semver 批量改写，`--dry-run` 预览）；配合 `monorepo-release.md` 新增的「已知摩擦与处置」小节（含 README 版本列 merge 冲突取 PR 侧的时态原则），处置知识不再依赖个人记忆。

### 改进

- `release.yml` 在单 Skill ZIP 之后构建并上传专家套件 ZIP；新增 PR Preview 工作流，正式 tag 前即可下载和检查套件产物。
- `update-readme.py` 统一扫描根 README 与全部专家套件 README，同时刷新整套和成员下载链接，并修复 `releases/latest/download/` 链接未被旧正则识别的问题。
- `release-monorepo.sh` 增加套件构建、套件数量门禁和 Release 资产总数核对；dry-run 不再创建临时 tag，正式发布要求五问确认、干净 main、远端 HEAD 对齐、tagger 身份与不可变 tag OID 绑定，并移除本地脚本直接提交、推送 README 的高风险路径。
- **README 回写双保险定稿**：`release.yml` 内嵌回写步骤（checkout main → 调重写版 `update-readme.py` → commit + push）为主路径；`update-readme.yml` 以 `workflow_run`（Release workflow 成功后）+ `workflow_dispatch` 作兜底，checkout 显式 `ref: main` 修复 workflow_run 默认 checkout 在 tag SHA 上 detached 导致 `git push` 失败的问题。两处均调用同一份技能脚本并覆盖套件 README，无 inline 副本。

### 文档完善

- 更新 monorepo 发布说明、项目配置和专家套件设计稿，明确源码符号链接与 Release 自包含目录的边界。
- **README 结构约定显式化**：`references/monorepo-release.md` 新增「monorepo-skills README 结构约定」一节——表行回写（链接刷新/版本列对齐/改名死链自愈）是 `type: monorepo-skills` 的类型级约定而非单仓库个性化补丁，`projects.yaml` 的 `type` 字段即通用/个性分界；确属单仓库的差异走 `notes:` 配置。

## [1.5.1] - 2026-09-21

### 修复（v2026.09.21 发布暴露的三个链路缺陷）

- **`scripts/generate-release-notes.py` 本版 skill 总数误报**：`{total}` 原优先读 README badge（`Skills-<数字>`），badge 已不存在时静默回退到最近更新条数（top_n=5），v2026.09.21 Release Notes 因此误写"本版包含 5 个 skill"（实际 64 个，事后人工 `gh release edit` 修正）。现优先数 `OUTPUT_DIR`（默认 `pack-skills/`）下的 zip 数量——release.yml 中 `build-zips.sh` 先于本脚本执行，产物必在；badge 降为次选，recent 条数仍为最后兜底；完成提示行输出总数便于 CI 日志核对。
- **`.github/workflows/update-readme.yml` 触发机制从未生效**：release.yml 用内置 GITHUB_TOKEN 创建 Release，GitHub 防递归机制下该事件不会级联触发 `on: release: published` 的其他 workflow（v1.4.0 已观察到现象，本次定位根因）。该 workflow 新增 `workflow_dispatch` 手动兜底，并改为调用 `scripts/update-readme.py`——删除漂移的 inline 旧副本（其正则只认 `latest/download` 占位形式，与 README 实际使用的显式 tag 形式不匹配，即使触发也替换不上）。
- **`.github/workflows/release.yml` 新增内嵌 README 回写**：上传 zip 后 checkout main → 调 `scripts/update-readme.py`（v1.4.1 已修好正则的版本）→ commit + push。此前该回写只存在于 `release-monorepo.sh` 本地驱动路径；直接 push tag 走 CI 发版时（v2026.09.21 的实际路径）README 下载链接滞留旧 tag，需人工经 API 补写（commit 0c7a798f）。

### 文档完善

- `SKILL.md` 模式 B 核心流程与 `references/monorepo-release.md` 端到端流程同步新机制：README 回写以两条发布路径（CI 的 release.yml 内嵌步骤 / 本地的 release-monorepo.sh）为准，`update-readme.yml` 降为 `workflow_dispatch` 手动兜底，并注明 GITHUB_TOKEN 防递归根因。

## [1.5.0] - 2026-09-21

### 新增

- **贡献者致谢（Attribution）规则**：`references/release-notes-guide.md` 新增「贡献者致谢」章节——外部贡献者 PR（含被「承接 #N」重做的原始 PR、Co-Authored-By 外部作者）必须在 Release Notes 致谢：条目行内 `(#N, @user)`（必选）+ 文末「贡献者」汇总节（推荐）；维护者自身与 bot 不标。`desktop-standard` 固定结构新增第 9 项「贡献者」节（无外部贡献者时省略），推荐模板同步补充。
- **SKILL.md 第 2 步新增来源 3（PR 作者识别）**：`gh pr list --state merged` 列本版本区间 PR 与作者；第 6 步验证清单加「外部贡献者致谢检查」；发布完成检查清单加对应确认项。
- **`config/projects.yaml` / `projects.example.yaml`**：`release_notes.always_include` 新增 `contributor_attribution` 约束键（folia / faropdf 已启用）。
- **调研补充**：调研来源表新增 eslint（全条目行内作者括注）、stablyai/orca（GitHub 原生 generate-notes：`by @user in #PR` + Contributors 头像墙）；新增 generate-notes API 调用作为漏识别兜底。

### 触发背景

Folia v0.8.1 发布后 Release Notes 整版遗漏外部贡献者致谢——该版三个修复全部源自外部贡献者 @Yillan-lamb（#169 直接合入；#166 / #167 为 #171 / #170 的承接来源），notes 与 CHANGELOG 均无一字提及。

## [1.4.1] - 2026-08-06

### 修复
- **`scripts/update-readme.py` 链接匹配范围扩大**：原正则只识别 `releases/latest/download/<skill>-<semver>.zip` 占位形式，但 legal-skills README 实际使用显式 tag 形式 `releases/download/<tag>/<skill>-<semver>.zip`，导致每次发版只刷新恰好已是新 tag 的少数链接，其余链接滞留旧 tag（指向过期版本快照）。现同时匹配「占位形式」与「显式 tag 形式」，统一改写为最新 release 的真实 `browser_download_url`（含正确 tag + 文件名版本），保证一次发版全量刷新。
- **按文件名版本对齐**：改写时以最新 release 资产的实际 `<skill>-<semver>.zip` 文件名为准，自动修正链接内滞留的旧版本号（如 `legal-case-analysis-0.3.3` → `1.0.0`）。
- **幂等性修正**：仅当 URL 实际变化时才计数并写回，已最新的 README 重跑报告「已是最新」而非误报「已更新 N 个」。
- **跨仓库安全**：仅改写与 `owner/repo` 一致的链接，独立仓库（如 `trademark-assistant.skill`、`de-ai-polish.skill`）链接不受影响。

### 文档完善

- 仓库停用 Cloud Plugin Marketplace 并删除 `.claude-plugin/` 配置后，monorepo 发布前检查改为同步各 Skill 版本、CHANGELOG、根 README 与实际启用渠道；发布脚本行为不变。

## [1.4.0] - 2026-06-30

### 新增

- **monorepo-skills 项目类型**：支持一次性发布多个 skill 的 zip（legal-skills 实例）。与现有 tauri / cli / web / library 类型并列，通过 `config/projects.yaml` 的 `type` 字段路由
- **新增脚本 `scripts/build-zips.sh`**：遍历 `skills/*/`、跳过 symlink 与已归档 skill、从 CHANGELOG 头部读 semver、用 `git archive --worktree-attributes` 干净打包到 `pack-skills/<skill>-<semver>.zip`
- **新增脚本 `scripts/release-monorepo.sh`**：主发布驱动（build → tag → push → gh run watch → 验证 assets → **内嵌 README 回写**），支持 `--dry-run` 模式（不消耗 Actions 配额）
- **新增脚本 `scripts/update-readme.py`**：从最新 release assets 取真实 `browser_download_url` 替换 README 占位 URL。原本由 `.github/workflows/update-readme.yml` 触发，但首次 release 观察到该 workflow 未自动触发，内嵌到 `release-monorepo.sh` 第 6 步保证 100% 执行
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
