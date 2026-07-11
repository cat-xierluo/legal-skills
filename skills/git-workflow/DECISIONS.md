# 决策记录与工作日志

## 第一部分：决策记录

### [DEC-001] - 2026-05-15 - 创建独立的 git-workflow skill

**背景**
private-skills 仓库 PR #6 合并时因 feature 分支基于旧 commit，`git merge` 误删 2,262 个文件。事后在 AGENTS.md v1.7.4 新增了 Monorepo 合并规范，但日常 Git 操作（分支管理、PR、冲突解决）缺乏统一指引。

**选项**
1. 扩展 git-batch-commit，增加非提交相关的 Git 规范
2. 创建独立的 git-workflow skill

**决策**
选择选项 2。

**理由**
- git-batch-commit 的本职是"提交分类与批量提交"，有 Python 脚本和交互式工具，职责清晰
- 分支管理、PR、冲突解决与"提交"是完全不同的 Git 操作阶段
- 单个 skill 职责过多会增加触发歧义和维护成本

**影响**
新增 private-skills/git-workflow skill，git-batch-commit 保持聚焦。

### [DEC-002] - 2026-05-15 - 将 Issue/PR 命名规范从 git-batch-commit 迁移到 git-workflow

**背景**
git-batch-commit v1.2.5 新增了 `references/issue-pr-format.md`，但 Issue 和 PR 的命名属于 Git 全流程中的创建/管理阶段，与"提交"操作无直接关系。

**决策**
将 `issue-pr-format.md` 从 git-batch-commit 迁移到 git-workflow，git-batch-commit 升级到 v1.4.0。

**理由**
- Issue 创建 → 分支创建 → 开发 → 提交 → PR 创建 → PR 合并，这是一个完整链路
- Issue/PR 命名规范应与分支管理、PR 工作流放在一起，便于理解完整流程
- git-batch-commit 只负责这条链路中的"提交"环节

**影响**
git-batch-commit 不再包含 Issue/PR 规范，git-workflow 成为 Git 全流程规范的唯一入口。

### [DEC-003] - 2026-05-15 - 参考外部 skill 整合而非原创

**背景**
skills.sh 生态中存在多个 Git 相关 skill，但功能碎片化（commit 格式、gh CLI、冲突解决各自独立），没有单一综合方案。

**参考来源**

| 来源 | 安装量 | 采用内容 |
|:-----|:-------|:---------|
| github/awesome-copilot@git-commit | 30.8K | Git 安全协议、提交格式规范 |
| github/awesome-copilot@gh-cli | 21.3K | gh CLI PR/Issue/Repo 操作参考 |
| cursor/plugins@fix-merge-conflicts | 114 | 合并冲突解决原则与流程 |
| cursor/plugins@new-branch-and-pr | 34 | 分支创建与 PR 工作流 |

**决策**
将上述 skill 的核心规则提炼后整合到 git-workflow，保持简洁实用。

**理由**
- 外部 skill 大多是长篇参考文档，适合精简为操作速查
- Monorepo 安全合并是本项目特有的需求，外部 skill 没有覆盖

### [DEC-004] - 2026-05-16 - 新增 Rebase 冲突恢复规范

**背景**
push private-skills 时 `git pull --rebase` 遇到冲突：远程 PR #6 误删了 legal-material-organizer，rebase 时 AI 盲目接受远程删除（`git rm`），导致本地修改丢失。后通过 `git reflog` 找到本地提交 `fcb22f1`，用 `git checkout <commit> -- <dir>/` 恢复。

**决策**
在 git-workflow SKILL.md 的 Monorepo 安全合并章节新增"Rebase 冲突时的恢复"小节。

**理由**
- Monorepo 中远程 PR 误删文件是高频场景（已发生两次：2,262 文件和 legal-material-organizer）
- rebase 冲突提示只说"resolve conflicts"，不区分"有意删除"和"误删"
- `git reflog` 是恢复关键，但容易被忽略

**影响**
SKILL.md 第 3 节新增恢复流程，包含判断原则和操作步骤。

### [DEC-005] - 2026-05-17 - PR review / merge 采用 fail-closed 默认策略

**背景**
`git-task-orchestrator` 旧方案中的自动 review / merge gate 已经证明一个原则：自动合并链路遇到未知状态时必须阻断，而不是放行。当前边界收口后，Git 安全规则应集中到 `git-workflow`。

**决策**
吸收 fail-closed 原则，但不迁入 Review Session 状态机。`git-workflow` 只规定 Git 安全门禁：diff 不可读、CI/checks 未知、review 结论不明确、PR diff 超范围或分支保护状态不清楚时，不得自动合并。

**理由**
Git 安全层应该只回答“此 PR 是否可以安全操作”，不拥有任务状态和本地会话状态。fail-closed 能避免工具故障被误解为审核通过。

**影响**
SKILL.md PR 工作流新增 Fail-Closed 合并门禁；自动化调用方必须提供明确 diff、review 和 checks 信号后才可合并。

### [DEC-006] - 2026-05-17 - Git Workflow 内置提交规范，不依赖跨 Skill 引用

**背景**
`git-workflow` 在 PR、merge commit 和常规 Git 操作中需要使用提交格式规范。此前主文档引用外部提交工具的规范文档，容易让触发边界变模糊。

**决策**
在 `git-workflow/SKILL.md` 内直接保留一份提交规范速查，包括 commit 格式、支持类型、正文必填和 Multi-Skill 模块名规则。

**理由**
Git 流程 Skill 在执行 PR / merge / 常规提交判断时应自足，不应为了基本格式再加载另一个 Skill。批量拆分与自动生成 commit 的能力仍归专门的提交工具。

**影响**
`git-workflow` 的主流程不再依赖跨 Skill 引用；提交工具继续负责已暂存改动的分类和多 commit 生成。

### [DEC-007] - 2026-05-17 - 增加 TASKS.md 作为 Skill 维护上下文

**背景**
`git-workflow` 已经承担 Git 安全规则和流程入口职责，但目录中缺少任务清单，后续代理难以判断哪些规则已经完成、哪些只是待补充方向。

**决策**
新增 `TASKS.md`，记录已完成能力、当前关注、后续优化和边界提醒。

**理由**
本仓库的私有 Skill 维护习惯依赖技能级 `TASKS.md` 提供交接上下文。该文件只服务 Skill 自身维护，不作为项目任务状态源。

**影响**
后续优化 `git-workflow` 时先查看 `TASKS.md`；不得把它扩张成项目任务登记簿，项目任务仍归 `cross-agent-collab` / `docs/TASKS.md`。

### [DEC-008] - 2026-05-17 - PR 合并与 Cherry-pick 使用低自由度安全流程

**背景**
PR 合并和 Cherry-pick 都是高风险 Git 操作。PR 合并如果只写 `gh pr merge`，容易忽略 draft、checks、review 和 diff 范围；Cherry-pick 如果只写基础命令，容易把无关文件或 merge commit 误带入目标分支。

**决策**
将 PR 合并和 Cherry-pick 改为低自由度流程：合并前必须读取 PR 状态、diff 文件列表和 checks；Cherry-pick 前必须工作区干净并查看 commit 范围，跨分支回补默认使用 `-x`，Monorepo 场景优先目录级提取。

**理由**
这两类操作的错误成本高，靠经验判断不稳定。把检查命令和阻断条件写进主文档，可以让 Agent 在执行前先获得必要信号。

**影响**
`SKILL.md` 增加合并前检查和 Cherry-pick 安全流程；`gh-cli-quickref.md` 补充 fail-closed merge gate；`TASKS.md` 标记相关优化完成。

### [DEC-009] - 2026-05-17 - GitHub Issue 命名不承接项目任务状态

**背景**
`git-workflow` 包含 Issue / PR 命名参考，但新的协作边界已经明确：项目常规任务状态、依赖和可领取判断由 `cross-agent-collab` 读取 `docs/TASKS.md` 维护。若 GitHub Issue 参考继续写成“AI 读取 Issue 后生成分支执行”，容易被误解为第二套任务源。

**决策**
在 `SKILL.md` 和 `references/issue-pr-format.md` 中明确：Issue / PR 参考只管理 GitHub 标题、关闭标记和合并提交格式，不维护项目任务状态；存在 `docs/TASKS.md` 时，以 `cross-agent-collab` 的解析结果为准。

**理由**
GitHub Issue 是远程协作入口和外部问题追踪入口，不应和项目内 `docs/TASKS.md` 竞争唯一状态源。这样能保持三层边界稳定：任务状态归协作层，Git 规则归 Git Workflow。

**影响**
后续 Agent 不应从 `git-workflow` 的 Issue 命名文档中推导项目任务状态，只能把它用于 GitHub Issue/PR 命名和关闭标记。

### [DEC-010] - 2026-05-17 - 正式迁入 legal-skills/skills

**背景**
`git-workflow` 已经从私有协作 Skill 演进为通用 Git 安全层，职责边界稳定：只维护 Git 流程和安全规则，不承接任务状态或本地 Agent 会话状态。

**决策**
将 `git-workflow` 复制到 `legal-skills/skills/git-workflow/` 正式技能目录，并同步 README 与 Marketplace 清单。正式发布版本从 `1.0.0` 开始，私有开发阶段版本记录保留在 CHANGELOG 中。

**理由**
Git 工作流规则已经具备跨项目复用价值，适合进入正式技能集合；复制而非删除私有仓库版本，可以避免破坏当前仍在维护的私有上下文。

**影响**
公开技能集合新增 `git-workflow`。后续对正式版的修改应同步更新本目录的 `CHANGELOG.md`、`DECISIONS.md` 和 README 条目。

### [DEC-011] - 2026-05-17 - PR 模板和 Monorepo diff 检查纳入合并门禁

**背景**
仅检查 PR 状态、review 和 CI 仍不足以覆盖 Agent 协作中的常见风险。Agent PR 可能缺少 Summary/Test plan/Attribution，Monorepo PR 也可能出现跨模块污染、大量误删或版本清单不一致。

**决策**
将 PR 正文最低要求和 Monorepo diff 检查清单纳入 `git-workflow` 主流程。缺失 Summary、Test plan、Agent Attribution 或 Issue/Task 关联时不 approve；diff 超范围、敏感配置、lockfile/schema/版本清单不一致时不 merge。

**理由**
这些检查属于 Git 安全层，而不是任务协调层或本地执行层。把它们写入 `git-workflow` 可以让合并前判断更稳定，避免依赖 Agent 的临场经验。

**影响**
`SKILL.md` 和 `gh-cli-quickref.md` 增加 PR 模板与 Monorepo diff 检查；`TASKS.md` 标记对应优化完成。

### [DEC-012] - 2026-06-03 - 文档描述部分中文化，保留英文类型前缀

**背景**
git-workflow 在 PR 模板、commit 规范和表格示例中包含大量英文文字（`## Summary`、`## Test plan`、区块名 `Summary`/`Test plan`/`Agent Attribution` 等），与日常中文协作语境不一致；但完全中文化类型前缀会失去与 GitHub 标签、Conventional Commit 工具链（release-please、semantic-release 等）的兼容性。

**选项**
1. 保持现状，全英文描述
2. 描述部分中文化，保留英文类型前缀（feat/fix/docs/...）
3. 类型前缀与描述全部中文化

**决策**
选择选项 2。

**理由**
- 英文类型前缀是 GitHub 自动标签、Conventional Commit 工具链的硬性要求，改成中文会破坏下游集成。
- 描述、注释、表格内容、PR body 区块标题、命令注释等属于"使用语境"，可读性比与工具链兼容更重要。
- 通用 Git 术语（rebase、merge、squash、cherry-pick、worktree、Monorepo、CI、checks、PR、commit、review 等）保留英文更精确，避免"Rebase 合并"等生硬翻译。

**影响**
- `SKILL.md` PR body 模板的 `## Summary` / `## Test plan` 改为 `## 摘要` / `## 测试计划`；PR 正文最低要求表的中文标题用「摘要」「测试计划」「Agent 归属」「关联任务」「风险」。
- `references/issue-pr-format.md` 表格和说明中的"Multi-Skill"等改为"多 Skill"。
- 通用技术术语（Rebase merge、Squash merge、Merge commit、cherry-pick、commit、PR 等）保留英文。
- `git-workflow` 升级为 v1.2.0。

### [DEC-013] - 2026-06-06 - 新增「已合并分支审计与清理」子流程，覆盖 squash/rebase merge 场景

**背景**
Folia 项目 2026-06-06 集中清理已合并分支时，4 个已 squash-merge 的远程分支（feat/statusbar-copy / fix/about-qr-align / fix/font-preview-live / fix/settings-flash）跑 `git branch --merged origin/main` 完全没有输出。Agent 第一时间没意识到 squash merge 会让"提交可达"检查失效，差点漏判；后续靠 `gh pr list --state all` 交叉验证才确认它们对应 PR #27/#28/#29/#31 都已 MERGED。
此外 git-workflow §2「分支清理」原内容只有两条命令（`git branch -d` / `git push origin --delete`），缺少审计流程；§6 速查里 `git remote prune origin` 只解决"远端已删、本地 ref 残留"的反向场景，不覆盖"本地/远端分支都在但 PR 已合并"。

**选项**
1. 新建独立 user-level skill `cleanup-merged-branches`，专门承接审计 + 清理职责
2. 扩充 `git-workflow` §2，在原「分支清理」之后增加「批量审计：已合并分支清理」子节
3. 仅在 §6 速查表中加一行"squash merge 注意事项"

**决策**
选择选项 2。

**理由**
- 分支清理本来就是 git-workflow 的核心职责，把规则独立成新 skill 反而割裂 Git 流程入口。
- §6 速查只能放一行注释，无法承载完整流程、判定规则表和 fail-closed 红线。
- 新增子节既能复用现有协议（CHANGELOG / DECISIONS / TASKS / version bump），也保留与 §2 原小节「单分支删除」的承接关系。

**影响**
- `SKILL.md` §2 新增「批量审计：已合并分支清理」子节：审计流程、判定规则表、候选确认表、删除命令序列、5 条红线（仅凭 `git branch --merged` 删 / 仅凭 ahead-behind 删 / 把 CLOSED 当 MERGED / 跳过确认就推删除 / `-D` 强删本地以"对齐远端"）。
- `description` 增补关键词："已合并分支审计""清理已合并的远程分支""branch cleanup""有没有分支没清理"。
- `SKILL.md` §6 速查的 `git remote prune origin` / `git push origin --delete` 下方加导引指针。
- `git-workflow` 升级为 v1.4.0。
- 同期清理：先前误建的 user-level skill `~/.claude/skills/cleanup-merged-branches/` 删除，统一以 git-workflow 为入口。

### [DEC-014] - 2026-06-06 - 精简公开触发描述并同步发布索引

**背景**
`git-workflow` v1.4.0 为了覆盖 branch cleanup 场景，在 frontmatter `description` 中加入了具体命令依据、触发词和 `doc-curator` 后置动作。该写法能提高触发命中率，但对公开 Skill 来说过长，且 `doc-curator` 并不是所有项目都具备的内置能力。与此同时，README 和 Marketplace 中的 `git-workflow` 版本仍停留在旧版本，`DECISIONS.md` / `TASKS.md` 也被根目录 `.gitignore` 忽略，导致技能级记录无法随仓库追踪。

**决策**
将本次收口作为 `git-workflow` v1.4.1：精简 frontmatter `description`，保留核心触发边界和负向边界；把 `doc-curator` 改为“项目配置后才执行”的可选文档体检扩展；同步 README、Marketplace 和最近更新区；为 `skills/git-workflow/DECISIONS.md` 与 `skills/git-workflow/TASKS.md` 增加 `.gitignore` 例外。

**理由**
- Frontmatter description 的主要职责是触发和边界，不应承载完整操作细节。
- `doc-curator` 属于项目可选扩展；公开 Git 工作流 Skill 应能在未配置该 subagent 的仓库中正常使用。
- 公开 Skill 的版本号必须在 `SKILL.md`、`CHANGELOG.md`、README 和 Marketplace 中保持一致。
- `git-workflow` 是高风险操作类 Skill，决策记录和任务清单应可追踪。

**影响**
- `SKILL.md` version 升级为 `1.4.1`，description 改为更短的第三人称触发描述，并明确不要用于提交生成、任务分配、任务状态管理或本地多 Agent 会话编排。
- `SKILL.md` 中 `doc-curator` 相关小节保留为可选扩展，不再要求所有项目默认执行。
- `CHANGELOG.md` 新增 `[1.4.1]`，并将最近版本记录中的英文分类标签改为中文。
- README 技能列表、最近更新区和 `.claude-plugin/marketplace.json` 同步到 `v1.4.1`。
- `.gitignore` 增加 `git-workflow` 的 `DECISIONS.md` / `TASKS.md` 例外。

---

### [DEC-015] - 2026-07-11 - 开 worktree 前必做 3 查 + 多 worktree 并行与 main 占用处理

**背景**

2026-07-11 vision-extract 模型池项目（PR #45）合并实战暴露两个痛点：

1. **本地 main drift**：本地独有 12a97ee docs 未 push，origin 已合 PR #44 f6c8f15。基于这种"过期 main"开的 PR worktree 报 `not mergeable: the merge commit cannot be cleanly created`，且 DECISIONS.md 出现撞车（本地 main 写的"决策 P:方案 B" + origin 已有"决策 P:通用化"），需要 rebase + 重新编号 + `--force-with-lease` push 才能合。

2. **多 worktree 并行时 main 占用**：主仓库 attach 到 `main` + 多个 PR worktree 并存，`gh pr merge --delete-branch` cleanup 阶段报 `'main' 已经被工作区 '<主仓库路径>' 使用`。这是 warning，合并本身已成功（`mergedAt` 时间戳写入），但报错干扰判断。

**选项**

1. 文档级解决方案（本决策）：在 §2 Worktree 加"开 worktree 前必做 3 查"，新增 §10 "多 worktree 并行与 main worktree 占用"，§4 PR 工作流加"自 PR 自 review 限制 + 绕过方案"。
2. 工具级解决方案：写脚本（`pre-worktree-check.sh`）自动跑 3 查，不通过则拒绝开 worktree。
3. 不做规范，等下次踩坑再说。

**决策**

选择选项 1。

**理由**

- 选项 2 过度工程，文档级 3 查清单已覆盖主流程风险。
- 选项 3 不可接受，已踩坑两次（本地 main drift + main 占用）。
- §2 是"创建分支/Worktree"的天然位置，§4 是"PR 工作流"的天然位置，§10 作为新小节集中处理多 worktree 并行场景。

**影响**

- `git-workflow` 升级为 v1.5.0。
- `SKILL.md` §2 Worktree 小节加"开 worktree 前必做 3 查"块（防 base 过期）。
- `SKILL.md` 新增 §10 "多 worktree 并行与 main worktree 占用"（3 方案：方案 A 主仓库不 attach main / 方案 B main 单独 worktree / 方案 C 临时释放 main）。
- `SKILL.md` §4 PR 工作流加"自 PR 自 review 限制"子节（GitHub 不允许自 approve，自 PR 用 `gh pr merge --squash` 绕过）。
- description frontmatter 增补关键词："worktree 前检查""main drift""gh pr merge 报错"。

---

## 第二部分：工作日志

### 2026-06-06 (Codex)

- **目标:** 收口 `git-workflow` v1.4.0 后的发布元数据和触发描述。
- **操作:** 精简 `SKILL.md` description；将 `doc-curator` 从默认动作改为可选项目扩展；新增 `CHANGELOG.md` [1.4.1]；同步 README 技能列表、最近更新区和 Marketplace 版本；为 `DECISIONS.md` / `TASKS.md` 增加 `.gitignore` 例外。
- **结果:** `git-workflow` v1.4.1；公开触发描述更短，版本索引一致，技能级记录可被 Git 跟踪。
- **下一步:** 如继续压缩 `SKILL.md` 行数，可把 PR 体检扩展和常规速查拆到 `references/`。

### 2026-06-06 (Claude)

- **目标:** 把"squash/rebase merge 后 `git branch --merged` 不可信"这条规则固化到 git-workflow，避免下次踩同一个坑。
- **触发场景:** Folia 项目集中清理已合并分支时，4 个 squash-merged 远程分支在 `git branch --merged origin/main` 下完全没出现，只能靠 `gh pr list --state all` 反查 PR `state == MERGED` 才能识别。
- **操作:**
  - `SKILL.md` §2 在原「分支清理」后新增「批量审计：已合并分支清理」子节（核心陷阱说明、审计流程、判定规则表、候选确认表、删除序列、5 条 fail-closed 红线、来源备注）。
  - `SKILL.md` frontmatter 升 version 到 1.4.0；description 增补"已合并分支审计""清理已合并的远程分支""branch cleanup""有没有分支没清理"等触发词。
  - `SKILL.md` §6 速查的 `git remote prune origin` / `git push origin --delete` 下方加导引指针。
  - 追加 `CHANGELOG.md` [1.4.0]、`DECISIONS.md` DEC-013、`TASKS.md` 已完成项。
  - 同期删除先前误建的 user-level skill `~/.claude/skills/cleanup-merged-branches/`，统一以 git-workflow 为入口。
- **结果:** `git-workflow` v1.4.0；下次遇到"清理分支""有没有分支没清理"类触发词时，Agent 会被引导到 §2 完整流程，而不是只靠 `git branch --merged`。
- **下一步:** git-workflow 仍未通过 symlink 链接到 `~/.claude/skills/`，需由用户决定何时建立链接让 Claude Code 自动加载（已建议命令）。

### 2026-06-03 (Claude)

- **目标:** 中文化 git-workflow 文档描述，保留英文类型前缀。
- **操作:** 在 `SKILL.md` 将 PR body 模板的 `## Summary`/`## Test plan` 改为 `## 摘要`/`## 测试计划`；PR 正文最低要求表的区块改为「摘要」「测试计划」「Agent 归属」「关联任务」「风险」；`references/issue-pr-format.md` 表格和说明中的"Multi-Skill"改为"多 Skill"；通用技术术语（Rebase merge、Squash merge、Merge commit、cherry-pick、commit、PR 等）保留英文。版本号升为 1.2.0。
- **结果:** `git-workflow` 描述部分全面中文化，类型前缀保持英文以兼容 GitHub 标签和 Conventional Commit 工具链。
- **下一步:** 如调整提交工具的生成模板，需要同步检查是否需要把 commit 描述也按中文化规则生成。

### 2026-05-29 (Codex)

- **目标:** 记录 `agent-worktree` 对 Git 安全层的可借鉴点。
- **操作:** 在 `TASKS.md` 新增 `wt sync` / 原子 `wt merge` 的安全评估项，并修正边界提醒中的旧 Skill 名称。
- **结果:** 后续如借鉴 `agent-worktree`，会先评估其 sync/merge 思路是否能转化为检查流程，而不是绕过 Monorepo 安全合并规范。
- **下一步:** 需要实现时，优先补只读检查或操作前提示，避免把 `git-workflow` 扩张成 worktree runtime。

### 2026-05-17 (Codex)

- **目标:** 补齐 PR 模板和 Monorepo diff 合并门禁。
- **操作:** 在 `SKILL.md` 添加 PR 正文最低要求和 diff 检查清单；同步 gh CLI 速查、CHANGELOG、DECISIONS、TASKS。
- **结果:** `git-workflow` 升级为 v1.1.0，PR 合并前能检查模板、归属、Issue 关联和跨模块风险。
- **下一步:** 如需要自动化，可在不扩张为提交生成器的前提下增加只读检查脚本。

### 2026-05-17 (Codex)

- **目标:** 将 `git-workflow` 迁入正式 `skills/` 目录。
- **操作:** 复制私有 Skill 到 `skills/git-workflow/`，补齐正式版本元数据、MIT 许可证、README 技能列表和 Marketplace 条目。
- **结果:** `git-workflow` 作为 `v1.0.0` 正式进入 legal-skills 技能集合。
- **下一步:** 后续维护以正式目录为主，必要时再同步私有实验版本。

### 2026-05-17 (Codex)

- **目标:** 补强 PR 合并与 Cherry-pick 规则。
- **操作:** 在 `SKILL.md` 增加合并前检查命令、阻断条件和 Cherry-pick 安全流程；同步更新 gh CLI 速查、CHANGELOG、DECISIONS、TASKS。
- **结果:** `git-workflow` v0.3.0 对 PR 合并和 Cherry-pick 都具备明确安全流程，并补齐 GitHub Issue 命名与 `docs/TASKS.md` 主状态源的边界。
- **下一步:** 继续补 PR 模板检查和 Monorepo PR diff 检查清单。

### 2026-05-17 (Codex)

- **目标:** 补齐 `git-workflow` 的任务上下文。
- **操作:** 新增 `TASKS.md`，并在 `SKILL.md` 参考资源、CHANGELOG、DECISIONS 中记录。
- **结果:** `git-workflow` v0.2.2 具备技能级维护任务清单。
- **下一步:** 按 `TASKS.md` 继续补 gh CLI 速查、PR 模板检查和 Monorepo diff 检查清单。

### 2026-05-17 (Codex)

- **目标:** 取消 `git-workflow` 对外部提交规范的运行时引用。
- **操作:** 将提交格式、支持类型、正文必填和 Multi-Skill 规则复制进 `SKILL.md` 第 8 节，并更新版本记录。
- **结果:** `git-workflow` v0.2.1 自包含提交规范；提交工具仍保持批量提交职责。
- **下一步:** 如后续调整提交格式，应同步检查提交工具的生成模板是否一致。

### 2026-05-17 (Codex)

- **目标:** 将旧编排方案中成熟的 fail-closed 原则迁入 `git-workflow`。
- **操作:** 在 PR 合并流程中新增阻断条件表，明确任务状态和本地会话不由本 Skill 管理。
- **结果:** `git-workflow` 升级为 v0.2.0，成为 Git 安全规则唯一入口。
- **下一步:** 如后续新增 PR 自动化脚本，应以本门禁作为默认策略。

### 2026-05-16 (Claude)

- **目标:** 新增 Rebase 冲突恢复规范
- **操作:**
  - 在 SKILL.md 第 3 节 Monorepo 安全合并下新增"Rebase 冲突时的恢复"小节
  - 新增 DEC-004 决策记录
- **结果:** v0.1.0 补充了 rebase 恢复流程
- **下一步:** 用户确认后提交

- **目标:** 完善-git-workflow 上下文，迁移 git-batch-commit 中的 Issue/PR 规范
- **操作:**
  - 将 `issue-pr-format.md` 从 git-batch-commit 迁移到 git-workflow
  - git-batch-commit 升级 v1.4.0，移除资源文件引用，更新 CHANGELOG
  - git-workflow 新增第 7 节 Issue/PR 命名规范速查
  - 新增 Worktree 使用规则（第 2 节）
  - 创建 DECISIONS.md 记录设计决策
- **结果:** git-workflow v0.1.0 完成，职责边界清晰
- **下一步:** 用户确认后可发布或继续迭代

### 2026-05-15 (Claude)

- **目标:** 创建 git-workflow skill 初稿
- **操作:**
  - 搜索 skills.sh 生态中的 Git 相关 skill
  - 调研 5 个外部 skill 的内容质量
  - 创建 git-workflow/SKILL.md（7 个章节）
  - 创建 references/gh-cli-quickref.md
- **结果:** v0.1.0 初稿完成
- **下一步:** 用户反馈后调整内容
