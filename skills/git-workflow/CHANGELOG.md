# 变更日志

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
