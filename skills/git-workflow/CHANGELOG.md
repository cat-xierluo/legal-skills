# 变更日志

## [1.8.2] - 2026-09-05

### 改进

- **清理规则单一来源**：新增 `references/branch-lifecycle-and-cleanup.md`，集中承载一次性/长期分支生命周期、单 Worker delivery-bound 清理、squash/rebase expected-tip 删除、批量 stale 审计和长期功能线关闭。
- `SKILL.md` 的分支管理章节改为最短判定入口，删除与 reference 重复的命令、候选表和红线；长期集成分支 reference 继续负责建线/同步/里程碑，职责不混杂。

### 安全

- 保持 `long-lived`、integration target、24 小时活跃阈值、dirty Worktree、用户确认和 expected-tip 原子删除等既有边界；本次为结构优化，不放宽删除授权。

## [1.8.1] - 2026-09-05

### 修复

- 收窄“合并后清理”为仅清理 `ephemeral-worker` 一次性 head；长期功能/集成分支及其固定 Worktree 即使里程碑已合入默认主干，也不因单 Worker 验收自动删除。
- 分离 PR head 与 `integration_target`：短 Worker 合入长期分支时只清理 head，并要求 PR `baseRefName` 精确匹配；持久元数据声明 `long-lived` 后，调用方不得降级绕过保护。

### 关联

- 机械实现位于 `multi-agent-orchestration` v2.16.1；确定性回归覆盖长期目标保留、长期源分支全资源保留和生命周期防降级。

## [1.8.0] - 2026-09-05

### 新增

- 新增编排 worker 的验收后单任务清理协议：交付完成后默认收口远端分支、worktree 与本地分支，并统一输出 `CLEANED`、`RETAINED_WITH_REASON`、`CLEANUP_PENDING`。

### 安全

- 清理绑定 exact PR/head、40 位 worker tip、delivery commit、远端 tip、干净 worktree 和已结算 lifecycle；查询失败、未知状态或身份漂移一律失败关闭。
- squash/rebase merge 下不使用无条件 `git branch -D`，改为 worktree 移除后以 expected tip 为 old-value 精确删除本地 ref；清理失败作为独立债务，不重放已经确认的 merge/push。

### 关联

- 机械实现位于 `multi-agent-orchestration` v2.16.0 的 `pm-closeout.sh` 与 `pm-cleanup-worker.sh`；本 Skill 保持 Git 安全判据与批量清理授权边界。

## [1.7.1] - 2026-09-05

### 改进

- 「分支清理」的 24h 时间过滤段新增机械执行指引：PR 已 `MERGED` 且分支无消费者时的即时清理，由 `multi-agent-orchestration` 的 `scripts/post-merge-cleanup.sh` 按 git-workflow 删除资格真值机械化（唯一 MERGED PR + headRefOid 精确一致 + 无 stacked child + worktree 干净 + 非长期/默认分支 + 生命周期已结算，删除后强制零残留验证）。明确即时清理是「已合并且无消费者」对 24h 规则的显式例外，只针对显式指定的单个分支；批量审计仍必须走本节完整流程。本 Skill 未改脚本与规则本身。

## [1.7.0] - 2026-09-04

### 新增

- 新增长期集成分支模式：大型功能跨多个子 PR 或开发波次时，以具名长期分支作为功能线 `mini-main`，worker 从其最新远端基线创建短分支并显式向该分支提 PR。
- 新增 `references/long-lived-integration-branch.md`，固定建线合同、通用修复与功能专属修改的流向、波次同步冻结、里程碑集成 PR 和分支生命周期。

### 安全

- 长期集成分支按默认主干同等级门禁维护，禁止 rebase、force-push、无门禁堆积或随子 PR 删除；默认主干只在无待合并子 PR 的波次边界向长期分支同步。
- 明确 Monorepo 普通短分支的 rebase 建议不适用于长期集成主干，避免公开协作基线被改写。

### 改进

- 新建短分支不再一律假定以 `main` 为 base；项目声明 `integration_target` 时，从对应远端集成分支起步，并以该 ref 作为 safe-push 的完整 PR range 基线。

### 决策依据

- 来源：Badminton Lab 教学课程分析线需要跨多个独立 Worker/PR 长期推进，同时保持阶段成果可验收，并在具名里程碑后再集成回 `main`。
- 职责边界：分支拓扑、Worktree、PR base、同步与合并归 `git-workflow`；`git-batch-commit` 继续只负责提交拆分与提交信息生成。

## [1.6.0] - 2026-07-13

### 新增

- 新增只读 `scripts/check-outgoing-identities.sh`：仅接受当前 HEAD 与远端跟踪 PR base，逐 commit 核验 author 与 committer 的 name/email；同名 feature upstream 判为 ambiguous，拒绝用 `HEAD~1` / 本地 ref 缩窄范围。
- 新增 `scripts/safe-push.sh`：刷新 integration base 后运行身份门禁，确认 HEAD 未变化，只把已核验 immutable OID 推到目标远端分支，使检查证据绑定实际 push 对象。
- 新增 11 项故障注入，覆盖早期污染但 HEAD 正常、feature upstream 隐藏已 push 污染、非远端 base、committer 单独污染、空 range，以及 safe-push 远端 ref 与核验 OID 一致。

### 安全

- 固化 worktree 身份隔离边界：worker 禁止写 repo-local `git config user.*`，提交默认使用单次 `GIT_AUTHOR_*` / `GIT_COMMITTER_*`；禁止 raw push，必须通过 identity-bound safe-push 核验完整 PR range。

### 关联

- 来源：法律 AI 书项目 T158 / DEC-131 的并发 worktree 身份污染实战。

## [1.5.0] - 2026-07-11

### 新增

- **§2 Worktree 加"开 worktree 前必做 3 查"块**：本地 `main` 可能落后 `origin/main`（本地独有未 push / fetch 滞后 / 别的 session 在 origin 推了新内容）。基于"过期 main"开 worktree 提 PR 时 GitHub 报 `not mergeable: the merge commit cannot be cleanly created`，且 PR diff 不包含 origin/main 已合内容，DECISIONS 编号可能撞车、TASKS 已勾项要重做。3 查清单 = `git fetch origin` + `git rev-parse main/origin/main/merge-base` + `git log origin/main..main` 看独有 commit。判读规则表覆盖 4 种情况（无分叉 / 本地领先 / 本地落后 / 双向分叉）。**禁止**基于过期 main 开 worktree 后再补救。
- **§2 加"本地独有 commit 未 push 的处理"**：`git log origin/main..main` 显示本地独有时 3 选 1（push / merge origin/main 保留 / reset 放弃），明确禁止擅自 `git reset --hard` 丢弃独有 commit。
- **§4 PR 工作流加"自 PR 自 review 限制"子节**：GitHub 不允许 PR 作者自 approve（`gh pr review --approve` 报 `Review Can not approve your own pull request`）。自 PR 用 `gh pr merge --squash --delete-branch` 直接合（无需 review approval），前提是仓库无强制 review 的 branch protection。`gh pr merge --delete-branch` cleanup 阶段报 `'main' 已经被工作区使用` 是 warning，不影响合并本身（`mergedAt` 时间戳写入即成功）。
- **§10 新增「多 worktree 并行与 main worktree 占用」**：并行推进多个任务时，主仓库 attach 到 `main` 会导致 `gh pr merge` cleanup 报错。3 方案：方案 A（推荐）主仓库不 attach main / 方案 B `git worktree add` 给 main 单独 worktree / 方案 C 临时释放 main。附 `gh pr merge` cleanup warning 时的快速判断流程（state/mergedAt/mergeCommit 三查）。

### 决策依据

- 来源：vision-extract 模型池项目（PR #45）合并实战（2026-07-11）。
- 主要痛点：本地 main drift（12a97ee docs 未 push，origin 已合 PR #44）+ 多 worktree 并行（主仓库 + PR worktree + v0.9.1 端到端 worktree）时 main 被占用。
- 解法：文档级 3 查清单 + 3 个 main 占用解决方案，把实战教训沉淀进 git-workflow 主流程规范。

## [1.4.2] - 2026-06-30

### 新增
- **分支清理加 24h 时间过滤 + 陷阱 2(活跃分支误判)**:`--merged main` 两方向都不可靠(陷阱 1 squash 漏判 + 陷阱 2 活跃分支停在 main commit 误判已合并)。新增"最后提交 < 24h 一律保留"时间过滤(主活跃度信号),`git for-each-ref --sort=committerdate` 取日期。判定规则加时间行 + worktree-未提交行。红线加三条:删<24h 分支 / 盲 `--force` 删 worktree(先查 `git -C <wt> status`)/ 仅凭 `--merged` 删。来自 book repo 误删活跃 deai 分支的实战教训。

## [1.4.1] - 2026-06-06

### 改进
- 精简 `SKILL.md` frontmatter `description`：保留分支管理、Monorepo 安全合并、PR、冲突处理、cherry-pick、安全回退和 branch cleanup 等触发边界，删除具体命令细节和项目特定后置动作。
- 将 `doc-curator` 文档体检从默认动作调整为可选项目扩展：仅在当前项目明确配置 `doc-curator` subagent 或同等流程时执行；未配置时跳过，不影响 Git 工作流。

### 文档完善
- 同步 README 技能列表、最近更新区和 Marketplace 清单中的 `git-workflow` 描述与版本号。
- 为 `skills/git-workflow/DECISIONS.md` 和 `skills/git-workflow/TASKS.md` 增加 `.gitignore` 例外，使技能级决策与任务记录可随仓库追踪。
- 将最近版本记录中的 `Added` / `Reason` 标签调整为中文分类，符合本项目 CHANGELOG 规范。

## [1.4.0] - 2026-06-06

### 新增
- **§2 新增「批量审计：已合并分支清理」子节**：仓库累积一批已合并 PR 后做集中清理时，权威依据是 `gh pr list --state merged`，不能仅信 `git branch --merged`。
  - 核心陷阱：`git branch --merged` 只识别"提交可达"，对 **squash merge** / **rebase merge** 一律失效（main 上的合并 commit 是新生 SHA，原分支 tip 不在 main 历史里，分支被误判为未合并）。
  - 完整流程：snapshot → 列候选（参考用）→ `gh pr list --state merged --search "head:<branch>"` 交叉验证 → 候选表展示 → 用户确认 → 批量删除 → `git fetch --prune`。
  - 判定规则表（merge commit / squash-rebase merge / closed 非 merged / 未推送 WIP / stale ref）。
  - 辅助指纹：`git rev-list --left-right --count main...origin/<branch>` 返回 "ahead N, behind 1" 是 squash-merged 的典型形态，**仅是提示**，仍以 PR 状态为准。
  - 红线（fail-closed）：仅凭 `git branch --merged` 删 / 仅凭 ahead-behind 删 / 把 CLOSED 当 MERGED / 跳过确认就推删除 / `-D` 强删本地以"对齐远端"。
- **description / frontmatter 关键词扩充**："已合并分支审计""清理已合并的远程分支""branch cleanup""有没有分支没清理"加入自动触发词。
- **§6 速查**：`git remote prune origin` / `git push origin --delete` 两行下方加导引指针，指向 §2 完整流程。

### 决策依据
- 来源：Folia 2026-06-06 实操。4 个已 squash-merge 的远程分支（feat/statusbar-copy / fix/about-qr-align / fix/font-preview-live / fix/settings-flash）跑 `git branch --merged origin/main` 完全没有输出，Agent 第一时间没意识到 squash merge 会让这条检查失效，差点漏判。
- 现状：§2 原「分支清理」只列了 `git branch -d` / `git push origin --delete` 两条命令，没说明何时安全何时不安全；§6 速查的 `git remote prune origin` 注释只解决"远端已删，本地 ref 还在"的反向场景，不覆盖"本地/远端分支还在，但 PR 已合并"。
- 决策：在 §2 新增完整子流程，保留 §6 速查命令但加导引指针，避免速查表膨胀。

## [1.3.0] - 2026-06-03

### 新增
- **「PR 创建后立即跑 mergeable 检查（强制）」**：Agent 在 `gh pr create` 成功后立即跑 `gh pr view <N> --json state,mergeable,mergeStateStatus,baseRefName,headRefName,files`。`mergeable=CONFLICTING` 时**不要**直接 `gh pr update-branch`，先按决策表选方案。
- **「base 落后 / 冲突处理决策表」**：三选一方案：
  - 方案 A：冲突仅在 docs 同步文件 → 本地 rebase + 重新编号 + `--force-with-lease` push
  - 方案 B：冲突在共享代码 / 实质代码 → `gh pr close --delete-branch` + 重建分支 + cherry-pick 实质代码 + 重新写 docs + new PR
  - 方案 C：冲突极少 / 1-2 个文件 → GitHub PR UI 手动解决
  - **禁止** `git push --force`（不带 `--force-with-lease`）
- **「远端 stale ref 清理」**：合入后跑 `git remote prune origin` 清理不存在的远端 ref；手动删某个远端分支用 `git push origin --delete <name>`。

### 决策依据
- 来源：FaroPDF v0.1 Wave 1 真实合并 PR #18 / #19 前的根因复盘。
- 主要根因：提 PR 后没立即查 mergeable；本地 main 与 origin/main drift 后 push 报 non-fast-forward；squash merge 引入的"内容相同但 history 不同"被误判为冲突；多个 PR 共享 CHANGELOG 段、DEC 编号无 PM 收口。

## [1.2.0] - 2026-06-03

### 改进

- 描述部分中文化：PR body 模板的 `## Summary` / `## Test plan` 改为 `## 摘要` / `## 测试计划`，PR 正文最低要求表区块改为「摘要」「测试计划」「Agent 归属」「关联任务」「风险」。
- 表格与命令注释中文化：分支命名、Monorepo 合并、PR 合并、PR 状态检查等章节的表格与代码注释改为中文。
- `references/issue-pr-format.md` 表格和说明中的 `Multi-Skill` 改为「多 Skill」。

### 保留

- 英文类型前缀（`feat` / `fix` / `docs` / `chore` / `refactor` 等）以兼容 GitHub 标签和 Conventional Commit 工具链。
- 通用 Git 术语（`Rebase merge` / `Squash merge` / `Merge commit` / `cherry-pick` / `worktree` / `Monorepo` / `commit` / `PR` / `CI` / `checks` / `review` 等）保留英文，避免生硬翻译。

## [1.1.0] - 2026-05-17

### 新增

- PR 正文最低要求：`Summary`、`Test plan`、`Agent Attribution`、`Issue/Task` 和风险说明。
- Monorepo PR diff 检查清单：跨目录污染、大量删除、敏感配置、lockfile/schema/版本清单不一致时阻断合并。

### 改进

- `references/gh-cli-quickref.md` 增加 `gh pr diff --stat` 和 PR 模板缺失时的 fail-closed 提醒。

## [1.0.0] - 2026-05-17

### 新增

- 正式迁入 `legal-skills/skills/git-workflow/`，作为公开技能集合中的 Git 全流程工作流 Skill。
- 补齐正式发布元数据：`homepage`、MIT 许可证文件、README 技能列表和 Marketplace 条目。

### 改进

- 按正式发布版本规则将 Skill 版本设为 `1.0.0`，保留私有开发阶段 `0.3.0` 及以下历史记录。

## [0.3.0] - 2026-05-17

### 新增

- PR 合并前检查命令序列：读取 PR 状态、draft 状态、mergeable、reviewDecision、diff 文件列表和 checks。
- Cherry-pick 安全流程：工作区干净、先看 commit 范围、默认 `-x` 保留来源、回补后检查范围。
- Monorepo 场景下的目录级提取规则，避免 cherry-pick 整个 commit 带入无关文件。
- Issue / PR 命名参考增加边界说明：GitHub Issue 不作为项目常规任务状态源，项目任务仍以项目配置的任务源为准。

### 改进

- `references/gh-cli-quickref.md` 增加 fail-closed merge gate 速查。
- `TASKS.md` 同步标记 PR 合并检查和 Cherry-pick 规则已完成。

## [0.2.2] - 2026-05-17

### 新增

- 新增 `TASKS.md`，补齐 `git-workflow` 的维护任务上下文。

### 改进

- `SKILL.md` 参考资源增加 `TASKS.md`，方便后续代理查看当前关注和后续优化方向。

## [0.2.1] - 2026-05-17

### 改进

- 将提交规范内置到 `SKILL.md`，不再在主流程中引用其他 Skill 的提交规范文档。
- 保持职责边界：`git-workflow` 拥有 Git 流程中需要用到的提交格式要求，批量提交自动化仍由专门的提交工具负责。

## [0.2.0] - 2026-05-17

### 新增

- PR review / merge 默认 fail-closed：diff 不可读、CI/checks 未知、review 结论不明确时不得自动合并。
- 明确 `git-workflow` 只拥有 Git 安全规则；任务状态归 `cross-agent-collab`，本地 Agent 会话归 `parallel-agent-workflow`。

## [0.1.0] - 2026-05-15

### 新增

- 创建 git-workflow skill，覆盖 Git 全流程操作
- Git 安全协议：禁止操作清单和安全原则
- 分支管理：命名规范、创建/清理流程、Worktree 使用
- Monorepo 安全合并：目录级 checkout 规范（从 AGENTS.md v1.7.4 迁移）
- PR 工作流：创建/审查/合并（基于 gh CLI）
- 合并冲突解决：检测、解决原则、lock 文件处理
- Issue 与 PR 命名规范（从 git-batch-commit v1.2.5 迁移）
- 常用 Git 操作速查：撤销、暂存、cherry-pick、tag
- `references/gh-cli-quickref.md`：gh CLI 命令速查
- `references/issue-pr-format.md`：Issue 与 PR 命名详细规范

### 参考

- 整合自 github/awesome-copilot@git-commit（30.8K 安装）
- 整合自 github/awesome-copilot@gh-cli（21.3K 安装）
- 整合自 cursor/plugins@fix-merge-conflicts
- 整合自 cursor/plugins@new-branch-and-pr
