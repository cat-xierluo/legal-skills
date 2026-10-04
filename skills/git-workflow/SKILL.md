---
name: git-workflow
description: Git 工作流安全助手。本技能应在需要执行 GitHub Actions 额度治理（CI 分钟耗尽停挂止血、workflow 停挂/恢复）、分支管理、长期集成分支（long-lived integration branch）、Monorepo 安全合并、PR 创建/审查/合并、冲突处理、cherry-pick、安全回退、stale/已合并/冗余分支审计与清理（branch cleanup，含 squash/rebase merge 校验；用户以「分支有点多」「冗余分支」「清理一下分支」等口语提出时同样适用，先跑 scripts/branch-audit.sh 只读盘点再确认执行）、过期/失效 worktree 审计与批量清理（worktree cleanup；多 Agent 派发沉淀的一次性 worktree，用户以「清理 worktree」「过期 worktree」「失效 worktree」等口语提出时同样适用，先跑 scripts/worktree-audit.sh 只读盘点——按进程占用/dirty/分支补丁/PR 状态四维分类，绝不自行删除——再确认执行）、本地仓库 worktree→PR→merge 标准流程（maoscripts 类仓库 SOP）、开 worktree 前 base 同步检查（防 main drift 致 PR not mergeable；先跑 scripts/pre-worktree-check.sh 只读判读 IN_SYNC/AHEAD/BEHIND/DIVERGED，--pre-pr 模式以 merge-tree 做提 PR 前本地冲突模拟）、多 worktree 并行时 main worktree 占用处理、Git 提交身份自检与身份污染排查（identity-audit.sh whoami/history：提交前身份来源链自检、全仓 author/committer/Co-authored-by 尾注审计；用户以「提交身份不对」「多出 coauthor」「陌生作者」「冒出别的署名」等口语提出时同样适用）、敏感/私有文件误提交远端的全历史撤回（history rewrite；用户以「私有数据被上传了」「从历史里删掉」「把这个提交撤回」等口语提出时同样适用——先只读排查泄露范围与凭证暴露，再隔离 clone 做 filter-repo 重写、防复发 ignore 规则、全分支 force push 与主工作区深度分叉对齐，绝不在主工作区直接重写）、仓库膨胀审计与历史瘦身（repo slim；用户以「.git 太大」「仓库怎么这么大」「历史里有大文件」「瘦身」等口语提出时同样适用——先只读盘点 pack 构成/最大 blob/不可达对象/本地远端分叉，再谈 ignore 治理与历史重写授权；filter-repo 方向门与事故恢复见 §13）、常见 Git 事故恢复（accident recovery；用户以「amend 错了」「stash 找不到了」「分支误删了」「reset 丢了东西」等口语提出时同样适用——先 reflog/fsck 只读定位，恢复优先新建引用而非改写现态，reset/force 类补救仍须明确授权，详见 references/accident-recovery.md）时使用。不要用于：批量生成提交信息、项目任务分配、长期任务状态管理或本地多 Agent 会话编排。
license: MIT
metadata:
  version: "1.14.0"
  homepage: https://github.com/cat-xierluo/legal-skills
  author: 杨卫薪律师（微信ywxlaw）
---

# Git 全流程工作流

## 触发场景

- 分支创建、切换、管理
- 长期集成分支及其子 PR、里程碑 PR 管理
- 合并代码到 main（特别是 Monorepo 仓库）
- 创建、审查、合并 PR
- 解决合并冲突
- Git 操作前的安全检查

## 1. Git 安全协议

以下操作**必须获得用户明确指示**才能执行：

| 禁止操作 | 原因 |
|:---------|:-----|
| `git push --force`（特别是 main/master） | 覆盖他人提交 |
| `git reset --hard` | 丢弃未提交的修改 |
| `git checkout .` / `git restore .` | 丢弃工作区改动 |
| `git clean -f` | 删除未跟踪文件 |
| `git branch -D` | 强制删除分支 |
| `--no-verify` 跳过 hooks | 绕过安全检查 |
| `--no-gpg-sign` 跳过签名 | 绕过完整性验证 |

**安全原则**：
- 永远创建新 commit，而非 amend 已有 commit（除非用户明确要求）
- 暂存文件时，优先按文件名 `git add <file>` 而非 `git add .`
- 检测到 lock 文件时，先调查持有进程而非直接删除
- 遇到 pre-commit hook 失败时，修复问题后创建新 commit，不跳过 hook

### Git 身份隔离与 push 前门禁

worktree 隔离文件和 HEAD，但同一仓库的 worktree 默认共享仓库级 `.git/config`。因此 worker **禁止**运行 `git config user.name ...`、`git config user.email ...` 或带 `--local` 的同类命令；这些写入会污染其他并发 worktree。只有项目已明确启用 `extensions.worktreeConfig` 且用户授权时，才可讨论 `git config --worktree`。默认用单次环境变量绑定本次提交身份：

```bash
GIT_AUTHOR_NAME="<name>" GIT_AUTHOR_EMAIL="<email>" \
GIT_COMMITTER_NAME="<name>" GIT_COMMITTER_EMAIL="<email>" \
  git commit -m "<title>" -m "<body>"
```

push 必须走身份与隐私绑定的 `safe-push.sh`，核验**完整 PR range**后只 push 已核验的 immutable OID；不得直接 `git push`，也不得只看 `git log -1` 或 HEAD：

```bash
# integration base 必须显式是远端跟踪 ref；不要用 HEAD~1 缩窄范围
bash scripts/safe-push.sh \
  --base origin/main \
  --remote origin \
  --branch feat/example \
  --expected-name "<name>" \
  --expected-email "<email>"

# 只读诊断可单独运行门禁；不替代 safe-push
bash scripts/check-outgoing-identities.sh \
  --base origin/main \
  --expected-name "<name>" \
  --expected-email "<email>"
```

门禁逐 commit 比较 author name/email 与 committer name/email，只接受当前 worktree HEAD 与远端跟踪 base。当前 feature branch 若已跟踪同名 `origin/feat/...`，自动 upstream 会隐藏已 push 的早期 commit，因此判为 ambiguous，必须显式传 PR base。以下任一情况均 fail-closed：base 不明或不是远端跟踪 ref、用 `HEAD~1`/本地 ref 任意缩窄范围、bad revision、base 不是 HEAD 祖先、range 为空、Git 命令出错、身份字段为空或任一 commit 身份不一致。`safe-push.sh` 刷新明确的 integration base ref，固定 base/head OID；身份门禁与共享隐私 checker 核验相同范围。隐私 checker 逐笔读取 message、patch、变更 blob，覆盖中间提交泄露后删除；浅克隆、缺对象、不可读历史或内容均停止。核验期间 HEAD/base 改变即拒绝，再把该 OID 精确推到目标分支。

### 提交前身份自检与身份污染排查（v1.9.0，2026-09-30 Hermes 实录新增）

仓库级 `.git/config` 可能被并行会话或 agent 写入他人身份（实录：private-skills 被写入 `Hermes(info-assistant)`，190 个提交作者与全部 PR squash 的 Co-authored-by 尾注被污染）。上面的 push 门禁只核验"传入的期望身份"，期望值若取自被污染 config 则形同虚设；且 Co-authored-by 尾注完全不在门禁检查范围——GitHub squash 合并把分支提交作者自动转成尾注，**尾注问题的根源在分支提交作者，不在 PR 本身**。

每次 commit 前（至少 push 前）跑一次只读自检：

```bash
bash scripts/identity-audit.sh whoami
# 可选硬门禁：与期望身份不符即非 0 退出
bash scripts/identity-audit.sh whoami \
  --expected-name "<name>" --expected-email "<email>"
```

覆盖四类风险，任一命中即非 0 退出（先排查再提交）：

1. 仓库级（`--local`）或工作树级（`--worktree`）`user.*` 覆盖——本技能规范 worker 本就禁止写入；
2. `GIT_AUTHOR_*`/`GIT_COMMITTER_*` env 覆盖——只影响单次提交但会静默压过 config；
3. 可疑身份模式——邮箱 `*.local`/`*.invalid`/`*.test`/`@example.*`/`noreply@`（`users.noreply.github.com` 的 noreply 不贴着 @，不误伤），姓名 hermes/openclaw/codex/claude/checkpointer/minimax/glm/bot/agent/worker/dashboard/assistant（大小写不敏感；模式据 260930 全仓实测归纳）；
4. `--expected-name/--expected-email` 不符。

发现属本人身份（自定义域邮箱、本人设置的仓库级覆盖等）时用 `--allow-email`/`--allow-name`/`--allow-local-override` 精确放行，不要放宽模式。

身份问题排查入口：

| 症状 | 动作 |
|:-----|:-----|
| PR/合并提交多出陌生 Co-authored-by 尾注 | `bash scripts/identity-audit.sh history --all` 看尾注分布；根源=分支提交作者，清洗须改写分支作者（`git rebase -r --exec 'git commit --amend --reset-author --no-edit'`）后重推，且必须用户授权 |
| 提交作者不是我 | `whoami` 来源链定位写入层（env → worktree → repo-local → global，`--show-origin` 给出具体文件）；修复用 `git config --local --unset user.name user.email` 类命令回落全局，确认后再提交 |
| 全仓身份体检（交接/发版/公开化前） | `history --all` 输出 author/committer/尾注三张分布表，可疑项自动标注；大仓用 `--max-commits` 控制上限 |
| 已合并历史对账出现 `GitHub <noreply@github.com>` 提交 | `bash scripts/identity-audit.sh receipt --range <base>..<head>`（单个提交也可传 `<oid>`）：gh 自查本仓 MERGED 回执，完整 OID 精确绑定才 ACCEPT；完整查询无绑定才 DENY_FORGED。网络/格式失败或达到 `--merged-limit` 上限且未命中为 UNKNOWN、非零退出，不放行也不判为伪造；显式扩大上限后重跑。仅核已合并历史，不改变 push 门禁 |

发现身份污染时**先报告用户**，不得擅自改写历史或 force push（§1 安全协议）。与 `check-outgoing-identities.sh` 的分工：`whoami` 管"提交前我是谁、身份哪来的"，push 门禁管"push 前 range 内每一笔是谁"——两者互补，不可互替。

## 2. 分支管理

### 创建新分支

普通短分支从最新默认主干创建；项目若已显式声明长期集成目标，则 worker 短分支必须从最新远端集成目标创建，不能仍默认从 `main` 起步。

```bash
# 在干净隔离检出从最新远端 main 创建；不切换共享主工作区
git fetch origin
git switch -c <type>/<short-description> origin/main

# 从长期集成目标创建 worker 短分支
git fetch origin
git switch -c <type>/<short-description> origin/<integration-branch>

# 命名规范
feat/add-ocr-support
fix/empty-description-retry
docs/update-readme
refactor/sync-logic
```

### 分支命名规范

分支名是远端协作和 PR 的公共标识，必须按任务语义命名，不按本地执行来源命名。不要在分支名前加 `tmux-`、`subagent-`、`team-`、`agentteam-` 等前缀；这些前缀属于本地 worktree 或 session 名称，由 `parallel-agent-workflow` 管理。

| 前缀 | 用途 | 示例 |
|:-----|:-----|:-----|
| `feat/` | 新功能 | `feat/batch-export` |
| `fix/` | Bug 修复 | `fix/null-pointer` |
| `docs/` | 文档 | `docs/api-guide` |
| `research/` | 调研/素材 | `research/issue-13-ch08-materials` |
| `refactor/` | 重构 | `refactor/parser` |
| `chore/` | 杂项 | `chore/update-deps` |

推荐示例：

```bash
docs/ch01-agent-intro
research/issue-13-ch08-materials
fix/agent-session-shell
```

反例：

```bash
tmux-ch01
subagent-fix-copy
team-feature-a
```

### 长期集成分支模式

仅当一个大型功能需要跨多个可独立验收的子 PR 或多个开发波次、但整体尚不应进入默认主干时，才显式建立长期集成分支。普通功能仍使用短分支直接向默认主干提 PR；不要把长期分支当作无门禁 WIP 仓库。

长期集成分支是单一功能线的阶段主干（mini-main），必须遵守与默认主干同等级的 review、测试、身份和 push 门禁：

- 默认主干保存项目稳定基线；长期集成分支只聚合该功能线；worker 短分支承载一次性子任务。
- 长期分支由固定集成者/PM Worktree 独占检出；worker 从最新 `origin/<integration-branch>` 建独立短分支和 Worktree，并显式把 PR base 指向该集成分支。
- 子 PR 经独立验收后 squash merge 到长期分支；达到预先命名且有退出条件的里程碑后，才由长期分支向默认主干提集成 PR。
- 默认主干的通用修复先进入默认主干，再在无待合并子 PR 的波次边界 merge 到长期分支；同步后冻结本波 base，避免 worker 基线漂移。
- 长期分支禁止 rebase、force-push 或随子 PR 删除；里程碑合入默认主干后也继续保留，直到功能线被明确关闭。
- 功能线推进期只开子 PR，里程碑达成后再提默认主干 PR。Monorepo 按具名功能边界建最少必要功能线；PR池审计/窄采用、最终工程与独审证据关系、核心CI的SKIP分计、波次同步和已发布GitHub身份差异，统一读取 references/long-lived-integration-branch.md。

执行建线、同步、PR、里程碑和清理时，读取 `references/long-lived-integration-branch.md`。项目专属的分支名、固定 Worktree 路径、任务字段和里程碑门禁留在项目规则中，不写入本通用 Skill。

### 分支清理

先区分生命周期，再决定清理范围：

- 一次性 `ephemeral-worker` 在交付、PR/head、expected tip、干净 Worktree 与 lifecycle settlement 全部绑定后，默认随单任务收口清理。
- `long-lived` 功能/集成分支及固定 Worktree 不进入单任务自动清理，也不进入常规 stale 批量候选；短 Worker 合入长期分支时只清理 head，绝不触碰 `integration_target`。
- 单任务收口结果必须是 `CLEANED`、`RETAINED_WITH_REASON` 或 `CLEANUP_PENDING`。交付已确认后的清理失败不得重放 push/merge，也不得被隐去。
- 批量审计必须组合 PR 状态、最后提交时间、Worktree/dirty 状态和分支身份，向用户展示候选并取得确认；不得仅凭 `--merged`、ahead/behind 或分支名删除。squash/cherry-pick 合并后 commit 对 base 不可达但补丁已在 base——用 patch-id 判死（`git cherry <base> <branch>` 的 `+` 计数为 0 = 补丁等价已全部在 base）；判定优先级为 MERGED PR 记录 > patch-id > merge-base。

完整的单 Worker 自动清理、squash/rebase expected-tip 删除、批量 stale 审计、长期功能线关闭与红线统一读取 `references/branch-lifecycle-and-cleanup.md`。日常批量巡检先跑 `scripts/branch-audit.sh`（只读盘点，输出 SAFE_DELETE / NEEDS_CONFIRM / KEEP 三档候选表，含 patch-id 判死，绝不自行删除），再按 references §3.2 判定展示候选并取得用户确认，执行细节见其 §3.3。

**过期/失效 worktree 清理**（多 Agent 派发沉淀的一次性 worktree；用户以「清理 worktree」「过期 worktree」「失效 worktree」等口语提出时同样适用）：先跑 `scripts/worktree-audit.sh`（只读盘点，按进程占用 lsof / dirty / 分支补丁 / PR 状态四维输出 GONE、KEEP_ACTIVE、KEEP_DIRTY、KEEP_OPEN_PR、REMOVE_ALL 分类，绝不自行删除），再按 references §3.4 五步执行（prune 悬空记录 → 查进程占用 → dirty 分类 → 按分支死活定删除范围 → 逐个删）。硬保护：有进程 cwd 占用的绝不删；untracked 材料无入库备份的不删；分支是 open PR head 或有未交付补丁时只删 worktree 保分支。

### Worktree（工作树）

本地隔离 Worktree→验证→身份/隐私→PR→合并→增量安装→清理的当前通用 SOP，见 `references/local-worktree-sop.md`。原空文件已按当前规则补齐；未知的旧 Node/Raycast 步骤不推断补全，宿主构建/发布沿项目既有规则。

#### 开 worktree 前的必做 3 查（防止 base 过期导致 PR 报 not mergeable）

先跑 `scripts/pre-worktree-check.sh`（只读：fetch 后自动按下方判读表输出 `IN_SYNC` / `AHEAD` / `BEHIND` / `DIVERGED` 四态判定与对应处理路径，绝不创建/删除/重置任何东西；退出码 0=可开，1=先处理再开，2=用法/环境错误）。下列命令与判读表保留为透明判读依据，也是脚本降级（离线 fetch 失败）时的手动路径。

**核心陷阱**：本地 `main` 可能落后于 `origin/main`（本地独有未 push 的 commit / fetch 滞后 / 别的 session 在 origin 推了新内容）。基于这种"过期 main"开的新 worktree 提 PR 时，GitHub 会报 `not mergeable: the merge commit cannot be cleanly created`，且 PR 的 base 不包含 origin/main 已合的内容——你不知道原来已经合了什么，DECISIONS 编号可能撞车、TASKS 已勾的项要重做。

**3 查清单**（开 worktree 前必跑，逐项确认）：

```bash
# 1. fetch 远端最新
git fetch origin

# 2. 看本地 main 与 origin/main 是否分叉
echo "本地 main:    $(git rev-parse --short main)"
echo "origin/main:  $(git rev-parse --short origin/main)"
echo "merge-base:   $(git merge-base main origin/main | head -c 12)"

# 3. 看本地是否有未推送独有 commit
git status --short
git log --oneline origin/main..main   # 本地 main 独有、未 push 的 commits
```

**判读规则**：

| 情况 | 现象 | 处理 |
|---|---|---|
| 本地 main = origin/main（无分叉） | merge-base = main = origin/main | 直接开 worktree，放心 |
| 本地 main 领先 origin/main | `git log origin/main..main` 有 commit（本地独有未 push） | 保留独有成果，以最新远端目标开隔离候选；处理见下表 |
| 本地 main 落后 origin/main | `git log main..origin/main` 有 commit（origin 已合，本地没 fetch） | **先 `git pull --no-rebase`（merge origin/main）再开 worktree** |
| 本地与 origin/main 双向分叉 | 双方各有独有 commit | 保留双方成果，在隔离候选内对账；不重置共享主源 |

**禁止** 基于"过期 main"开 worktree 后再补救。会引发：PR 报 not mergeable → 本地 rebase 解决 → 决策编号撞车（如 DECISIONS.md 在 main 与 PR 都有新增）→ 重新编号 + push `--force-with-lease`。一次性 3 查可避免。

#### 本地独有 commit 未 push 的处理（3 查清单的延续）

`git log origin/main..main` 显示本地独有 commit 时，三选一：

| 选项 | 适用场景 | 操作 |
|---|---|---|
| **A. 经 PR 交付** | 独有 commit 需要发布（如 docs 标记、版本号） | 从最新远端目标开隔离短分支，窄采用有效差异，验收后走 safe-push / safe-pr；不直接 push main |
| **B. Merge origin/main 保留**（推荐） | 独有 commit 是本地工作，希望下次 main 上有 | `git merge origin/main --no-ff -m "merge: bring origin/main into local main + preserve <描述>"` |
| **C. 放弃独有 commit** | 独有 commit 已不需要或重复 | `git reset --hard origin/main`（**破坏性**，必须用户明确指示） |

**禁止** 擅自 `git reset --hard` 丢弃本地独有 commit（Git 安全协议 §1）。

#### 创建 worktree

当需要同时在多个分支上工作时，使用 worktree 避免频繁切换分支：

```bash
# 创建 worktree（自动创建新分支）
git worktree add ../pm-feature-ocr feat/ocr-support

# 在 worktree 中工作
cd ../pm-feature-ocr
# ... 编辑、提交 ...

# 完成后回到主工作目录
cd -

# 删除 worktree
git worktree remove ../pm-feature-ocr

# 查看所有 worktree
git worktree list
```

**使用场景**：
- 一个分支在跑耗时任务（训练/测试），同时需要在另一个分支工作
- 需要对比两个分支的代码
- Code review 时需要拉取 PR 分支到本地测试

**注意事项**：
- 同一分支不能同时被两个 worktree 检出
- worktree 中的修改是独立的，需要单独 push
- 删除 worktree 前确认已提交或推送改动

## 3. Monorepo 安全合并

### 核心规则

**禁止本地 `git merge` 直接将 feature 分支合入 main。** 旧基线、整目录替换和错误的冲突取舍可能带入跨模块变化或删除；按明确范围保留当前全仓基线。默认主干 merge 到长期功能线属于另一同步方向，按功能线专页核验。

### 目录级采用

先核隔离目标现场干净、用户授权与实际文件清单。以下目录级 checkout 只适用于该目录整树已验、与当前目标差异完整对账的候选；旧目录含未验或过时内容时按精确文件/增量 patch 窄采用，共享文档保留双边当前内容，不在 dirty 主源暂存或覆盖。

```bash
git checkout main && git pull origin main
git checkout <feature-branch> -- <skill-directory>/
git diff --cached --stat   # 确认只改了目标目录
git commit -m "feat(<skill>): 描述"
```

### 多 Skill 合并

涉及多个 Skill 时逐个目录 checkout，每个目录一个提交：

```bash
git checkout main && git pull origin main
git checkout <feature-branch> -- skill-a/
git diff --cached --stat
git commit -m "feat(skill-a): 描述"

git checkout <feature-branch> -- skill-b/
git diff --cached --stat
git commit -m "feat(skill-b): 描述"
```

### 合并后验证

```bash
git diff HEAD~1 --stat    # 确认无误删
ls .gitignore .env 2>/dev/null  # 确认关键文件还在
```

### GitHub PR 合并

若用 GitHub PR 合并 Monorepo 中的某个 Skill 改动：

> 下列 rebase 流程只适用于普通短分支。已声明为长期集成分支的阶段主干禁止 rebase/force-push，改为按 `references/long-lived-integration-branch.md` 在波次边界 merge 最新默认主干；其 worker 短分支仍按项目策略处理。

1. 在干净隔离现场刷新真实 PR 目标。未发表短分支可按项目策略 rebase；已发表分支须核 owner 和历史重写授权，不能以冲突自动授权 force。
2. 确认最终 PR diff 只涉及允许范围，并保留目标侧其他模块与共享记录；改 base/head 后重新验收。
3. 用 safe-push / safe-pr 创建与 squash，提交标题包含模块名和 PR 编号。safe-push 当前不支持 force；拒绝非快进时保留原成果，优先按授权窄采用到新短分支，不能退回裸 push 绕门。

**批量验收合并与取代关闭**（用户拍板「把这些 PR 合并」「合并新 PR、关闭旧 PR」后执行；含合并前复核、同族窄采用 PR 串行合并与连锁文档冲突解法、关闭评论四要素、收尾清理）统一读取 `references/branch-lifecycle-and-cleanup.md` §3.5。单 PR 日常合并同样适用其复核与确认要求。

### Rebase 冲突时的恢复

`git pull --rebase` 遇到冲突时，**不要盲目接受远程的删除**。Monorepo 中远程 PR 误删文件是常见情况。

**判断原则**：
1. 如果冲突是"远程删除 vs 本地修改"，先确认远程的删除是否是有意为之
2. 如果该 Skill 目录在远程 main 仍存在但被删除，很可能是合并误删，应保留本地版本
3. 如果确认是误删，用 `git checkout <本地commit> -- <skill-directory>/` 恢复

**恢复流程**：

```bash
# 1. 先中止 rebase，回到安全状态
git rebase --abort

# 2. 获取 rebase 前的本地提交（通过 reflog）
git reflog | head -10

# 3. 在干净隔离候选中，从最新远端目标逐文件恢复实际误删内容
# 不用旧整目录覆盖目标侧的新成果
git restore --source=<本地commit-hash> -- <已核误删文件>

# 4. 核范围、精确暂存并验证，按 §1 身份协议提交含正文的恢复提交
# 再走 safe-push / safe-pr；不直接向 main push
```

**关键**：`git reflog` 保存了所有操作历史，即使 rebase 后本地提交也不会真正丢失。

## 4. PR 工作流

### 隐私预检与依赖

共享 `scripts/privacy_check.py` 需要 Python 3.10+ 和 Git，无第三方 Python 包；`scripts/safe-pr.py` 还需已认证的 gh CLI。未安装时先按本技能依赖要求准备，不能绕过检查。

案号仅为待核对项：公开裁判和虚构测试可以带来源的精确审查记录放行，不允许目录忽略；本地黑名单不得发布。诊断不打印敏感原文。使用、策略格式、失败关闭条件与能力边界见 [隐私预检](references/privacy-preflight.md)。人工审查、身份、授权和 CI 门禁仍须独立满足。

### 创建 PR

先通过 `scripts/safe-push.sh` 推送核验的不可变 OID，再准备最终单行标题文件和完整正文文件（建议放在 Git 目录或仓库外）：

```bash
python3 scripts/safe-pr.py create \
  --base main --head <branch-name> --expected-head <完整已核验head-OID> \
  --title-file <最终标题文件> --body-file <最终正文文件>
```

默认创建 draft。helper 读取一次最终文本并直接传给 gh，重新检查远端完整 PR range，创建后核对 head/base/title/body。禁止 `--fill` 或自动拼接未经检查的提交说明。GitHub 创建接口不支持原子 head 条件，使用独占分支并检查后验结果；失败先只读确认远端状态，不能盲目重试。

### PR 正文最低要求

创建或审查 PR 时，正文至少包含：

| 区块 | 要求 |
|------|------|
| 摘要 | 说明改了什么，避免只有“update files” |
| 测试计划 | 列出已运行或未能运行的验证；未运行要写原因 |
| Agent 归属 | 若由 Agent 完成，写明 Agent ID、Git author、触发来源 |
| 关联任务 | 关联 GitHub Issue、项目任务 ID 或用户指定任务 |
| 风险 | 涉及迁移、删除、权限、安全、跨模块改动时说明风险和回退方式 |

缺失「摘要」或「测试计划」时，不应 approve；缺失「Agent 归属」时，要求补齐后再合并。

### PR 标题格式

```
<类型>(<模块>): <描述>
```

与 commit 格式一致，多 Skill 仓库必须带模块名。

### 审查 PR

```bash
# 查看 PR 详情
gh pr view <number>

# 查看 PR 文件变更
gh pr diff <number>

# 提交 review
gh pr review <number> --approve --body "LGTM"
gh pr review <number> --request-changes --body "建议修改..."
```

### 审查外部 PR：分层审查——必要性 gate 先于代码审查

**核心教训**：对外部贡献者的 PR 先做代码级深审，最后才在「项目要不要这个改动」层面否决——代码审查投入全部沉没（实例：某 PR 深审后列出多个代码缺陷，最终以"功能不在路线图、无用户诉求"关闭，缺陷分析全部白做）。

**第一层：项目契合度 gate（先于看 diff / 任何代码检查）**，只回答一个问题——"这个改动是不是这个项目现在需要的"：

1. **有无需求来源**：对应 issue / ROADMAP / TASKS / 项目规则里的既定规划？逐项核对，引用出处。
2. **无来源时的判据**：是否服务项目核心主张（README 一句话定位）？还是贡献者自己的个性化偏好？个性化偏好不是错，但不应由维护者承担合并与长期维护成本。
3. **伪需求识别**：issue 里的"遗留场景"在当前架构下是否仍存在（例："打开文档替换当前内容"的确认场景在多标签架构下已不适用——不要把历史场景描述当成"要新增单文档模式"的诉求）。
4. **gate 不通过 → 直接关闭，不进入代码审查**。留言模板：感谢贡献 → 说明不在路线图/无用户诉求（对事不对人，不评价代码质量）→ 给重启路径（欢迎开 issue 讨论需求场景，有真实需求时基于此思路重启）。

**第二层：代码审查**（gate 通过才投入）：

- diff 范围检查（见下方 Monorepo PR Diff 检查清单）
- 本地验证走隔离 worktree（见「本地验证的环境卫生」）
- 按正文最低要求、Fail-Closed 合并门禁逐项过

必要性依据（ROADMAP、issue、核心主张）是**项目级答案**，本 Skill 只约束流程顺序：先 gate 后代码。答案缺失时问用户或查项目规则，不要用"代码看起来没问题"替代 gate 判断。

### 审查外部 PR：本地验证的环境卫生（防遗留状态污染结论）

**核心陷阱**：审自己的 PR 时主工作区通常就是干净的；审**他人**的 PR（尤其多 PR 串行接力审查时）主工作区可能残留上一轮的中间态——未完成的 merge/rebase（`.git/MERGE_HEAD` 存在、`UU` 冲突文件）、未提交的 `M` 文件。此时 `gh pr checkout <N>` 会把遗留变更叠加到 PR 检出上形成「混血工作区」，之后跑 typecheck / test 得到的错误可能来自**遗留状态而非 PR 本身**——把别的 PR 的缺陷误写进当前 PR 的 review 结论（假阳性）。实例：审 PR-A 前主工作区残留审 PR-B 时中断的 merge，checkout PR-A 后 typecheck 报错全属 PR-B，险些误判 PR-A 不合格。

**规则**：审查/验证他人 PR 一律用隔离 worktree，永不在主工作区 `gh pr checkout`：

```bash
# 1. 动手前主工作区体检：有 UU / MERGE_HEAD / 未提交变更 → 先恢复干净再动手
git status --short && ls .git/MERGE_HEAD 2>/dev/null

# 2. 隔离 worktree 检出 PR（不污染主工作区）
git fetch origin pull/<N>/head
git worktree add /tmp/pr-<N> FETCH_HEAD

# 3. typecheck / test 全部在 worktree 里跑；node_modules 可符号链接主仓库复用
ln -sfn <主仓库>/node_modules /tmp/pr-<N>/node_modules

# 4. 审完清理
git worktree remove /tmp/pr-<N> && git worktree prune
```

**收尾纪律**：会话内做过的 merge / rebase / checkout 试验，结束前要么完成要么 `--abort`；新会话接手审查前先 `git status` 确认无中间态。清理 merge 中间态不丢数据——遗留内容都在 git 对象中（MERGE_HEAD 指向的提交、分支 tip 均可随时恢复）。

**判读参照**：typecheck/test 报错与 PR diff 对不上（报错文件不在 `gh pr diff --name-only` 列表里）→ 先怀疑工作区污染，切干净 worktree 复跑后再写 review 结论。

### 合并 PR

合并默认采用 fail-closed 策略。只有在 diff 可读、review 结论明确、CI/checks 明确通过时，才允许自动或半自动合并。

合并前先做最小检查：

```bash
gh pr view <number> --json title,state,isDraft,mergeable,reviewDecision,headRefName,baseRefName
gh pr diff <number> --name-only
gh pr checks <number>
```

判断规则：
- `state` 不是 `OPEN` 或 `isDraft` 为 `true`：不合并
- `mergeable` 为 `UNKNOWN` / `CONFLICTING` / 空值：不合并，先更新分支或人工检查
- `reviewDecision` 为 `CHANGES_REQUESTED`，或应有 review 但没有明确通过：不合并
- `gh pr checks` 有失败、等待中、未知状态，或无法读取：不合并
- `gh pr diff --name-only` 显示跨模块污染、误删大量文件、敏感配置文件：不合并

### Monorepo PR Diff 检查清单

对 Monorepo 或多 Skill 仓库，合并前必须检查文件范围：

```bash
gh pr diff <number> --name-only
gh pr diff <number> --stat
```

阻断条件：
- PR 声称只改一个模块，但 diff 涉及多个无关目录。
- 出现大量 `deleted` 或目录整体删除，且 PR 正文没有解释。
- 改动包含 `.env`、`config/secrets.*`、`credentials.json`、私钥或 token 文件。
- lockfile、schema、迁移文件、生成物变化无法对应到 Summary / Test plan。
- `README.md`、Marketplace 清单、版本号、CHANGELOG 中的版本不一致。

处理方式：要求拆 PR、缩小 diff、补说明或补测试。不要用“看起来问题不大”替代文件级检查。

```bash
# Squash merge：上面的 review/CI/授权门禁已全部通过后
# 最终标题须包含 (#PR编号)，正文须明确写入，不用 GitHub 自动汇总
python3 scripts/safe-pr.py squash --number <number> \
  --expected-head <完整已审核head-OID> \
  --title-file <最终squash标题文件> --body-file <最终squash正文文件>
```

合并前同时检查当前 PR 标题/正文与最终 squash 标题/正文，helper 会检查每笔历史并用 `--match-head-commit` 绑定 head。其他合并方法或 API 也必须检查最终确切说明和完整提交范围，不得依赖自动生成文本。

**重要**：通过 API 执行 squash merge 时，`commit_title` 不会自动追加 `(#N)`，必须手动写入。

### 自 PR 自 review 限制（GitHub 强制）

GitHub **不允许 PR 作者自 approve 自已的 PR**：

```
gh pr review <N> --approve
# → failed to create review: GraphQL: Review Can not approve your own pull request (addPullRequestReview)
```

GitHub 的自 approve 限制不改变本技能的独立 review/CI/身份/隐私要求。无强制 GitHub approval 的仓库可采用实际不同角色、绑定当前候选的外部审查证据；保护要求他人 approval 时满足该规则，不因自 PR 使用 admin override。完成门禁后使用 safe-pr.py squash，合并与删除分别核授权。

多 Worktree 的清理命令报错时，先读取实际 MERGED/mergedAt/mergeCommit，再登记残留资源；清理失败不重放合并，长期功能线不随子 PR 删除。

### 本地拉取 PR 到 main 的提交格式

当用户要求“拉取 PR 到主分支 / 把 PR 拉进 main / 合入这个 PR”时，默认目标是让 `main` 历史中能直接看出来源 PR。不要用 `git pull --ff-only origin pull/<N>/head` 作为最终合入方式，因为 fast-forward 会保留 PR 原提交标题，通常不会显示 `(#N)`。

默认通过已验正式 PR 的 safe-pr.py squash 生成带 PR 编号的主干提交，后验真实合并回执。本地采用不得绕开 Monorepo 范围门或直接 push main：在最新主干的干净隔离短分支窄采用目标范围，核验后提出 PR；确有项目授权的本地 squash 流程也要满足完整范围、精确文本与身份/隐私门，不能将 CLOSED 冒称为 GitHub MERGED。

提交标题示例：

```text
docs: 设定章节撰写默认使用 tmux Codex session (#7)
docs(ch01): 从 Chatbot 到 Agent (#10)
research(issue13): ch08 迭代解耦素材包 (#11)
```

若 PR 标题已经包含 `(#<N>)`，不要重复追加。若用户明确要求保留 PR 中多个原子 commit，不做 squash；但仍应提醒用户这种方式可能无法在每个 commit 标题中显示 PR 编号。

### Fail-Closed 合并门禁

以下任一情况出现时，不得自动合并，必须停下并让人类确认或先修复信号来源：

| 阻断条件 | 处理 |
|----------|------|
| `gh pr diff` 失败、diff 为空或不可读 | 不 approve，不 merge；先确认分支和权限 |
| CI/checks 失败、等待中、缺失或状态未知 | 不 merge；需要明确通过或用户显式确认 |
| review 结论缺失、互相矛盾或只是摘要没有 verdict | 不 merge；补一次明确 review |
| PR diff 超出声明范围，尤其是 Monorepo 误删文件 | 不 merge；先缩小 diff 或拆分 PR |
| 分支保护、required checks、linked issue 状态不清楚 | 不 merge；先查清仓库规则 |

`git-workflow` 只维护这些 Git 安全规则；任务状态仍由 `cross-agent-collab` 和项目任务源管理，本地 Agent 会话由 `parallel-agent-workflow` 管理。

### PR 状态检查

```bash
# 查看 CI 状态
gh pr checks <number>

# 查看所有 PR 列表
gh pr list --state open
```

### PR 创建后立即跑 mergeable 检查（强制）

更早的前置：PR 创建后的 mergeable 检查无法搬到「开 worktree 前」——PR 对象那时还不存在。能前置的是「提 PR 前」：`bash scripts/pre-worktree-check.sh --pre-pr <branch>` 用 `git merge-tree --write-tree` 在本地模拟 base+head 合并，不创建 PR、不触碰工作区与 index、不耗 GitHub API，把冲突提前到 push 前暴露（需 Git 2.38+）。本地模拟干净不豁免本节的 PR 后验——GitHub 侧 mergeable 仍以创建后检查为准。

Agent 在 `gh pr create` 返回 PR URL 后，**不要等用户/PM 拍板合并**，立即跑一次完整状态检查，捕获 base 落后或 mergeable 冲突：

```bash
gh pr view <N> --json state,mergeable,mergeStateStatus,baseRefName,headRefName,files
```

判读规则：

| `mergeable` | `mergeStateStatus` | 含义 | 处理 |
|---|---|---|---|
| `MERGEABLE` | `CLEAN` | 可直接合并 | 进入 review → 合并流程 |
| `UNKNOWN` | 空 | CI 还在跑或权限不足 | 等 CI / 确认权限后再查 |
| `CONFLICTING` | `DIRTY` | 有内容冲突 | **不要**直接 `gh pr update-branch`，按下方「base 落后 / 冲突处理决策表」选三选一方案 |
| `MERGEABLE` | `BLOCKED` / `BEHIND` | base 落后但无内容冲突 | `gh pr update-branch <N>` 拉 base；如果失败再走决策表 |

### base 落后 / 冲突处理决策表

当 PR 出现 base 落后、有冲突、或 update branch 失败时，按下表三选一：

| 情况 | 现象 | 推荐方案 |
|---|---|---|
| 冲突仅在 docs 同步文件（CHANGELOG / DECISIONS / TASKS） | 实际差异为版本、决策编号、任务状态等共享记录 | 保留双方有效记录，串行分配版本/编号并按文件解决；未发表短分支可 rebase，已发表历史按单独授权处理。 |
| 冲突在共享代码 / 实质代码 | 实际允许范围含多文件实现或组合依赖 | 在最新目标基线上开隔离窄采用候选，保留原 PR/分支及来源映射；新候选实际合入目标、采用/未采用项处置完成后才按取代合同关闭旧 PR。 |
| 冲突极少 / 1-2 个文件 | 改动小且冲突集中 | 本地按文件解决并检查最终 message/patch/blob；如经 GitHub UI 处理，也要核完整发布文本/范围和实际服务端结果，不能绕身份/隐私门。 |

功能线始终普通 merge 主干，不 rebase/reset；不因冲突自动关 PR、删除分支或 `switch -C` 重建同名 head。每项核真实 exit，候选变化后重跑受影响验证和最终 CI。历史重写需精确授权，当前 safe-push 不支持 force，不能改用裸 push 绕过。

### PR 创建后：可选文档体检扩展

若当前项目明确配置了 `doc-curator` subagent 或同等文档体检流程，Agent 在 `gh pr create` 成功返回 PR URL 后，可以按项目协议触发一次文档体检；未配置时跳过，不影响本 Skill 的 Git 流程。

目的：在 PR 进入 review 前，发现当次变更是否引入文档膨胀、超出归档指针、违反硬性规则；如果有问题，由项目内的文档体检流程在 PR 自身或单独的 maintenance PR 内修正，不让膨胀项进入 main。

调用方式：

```bash
# 在 Agent 流程里，PR 创建完成后：
# 1. 调起项目配置的文档体检流程（如存在）
#    - 工作目录：仓库根
#    - 输入：刚 push 的 commit hash（可选）
#    - 期望输出：markdown 报告 + JSON 行

# 2. 解析报告（subagent 内部完成），按规则分支：
#    - 全部 ok → 不动作，继续 review 流程
#    - 软提示 → 把提示写入 PR 描述的"跟进事项"小节，不阻断
#    - 硬性 / 自适应告警 → 走 maintenance-pr.sh：
#      - 工作区干净 → 自动创建维护分支、提一个 maintenance PR
#      - 工作区不干净 → 仅报告，提示用户先清理

# 3. 不阻塞当前 PR：把 maintenance PR 链接追加到当前 PR 描述，让 review 知道"已发现 N 项"
```

约束：

- 这是 post-action 调起，不是 pre-PR 门禁（避免锁死 PR 创建流程）。
- 文档体检扩展不得改 `src/` / `src-tauri/` / `tests/`；改动仅限于 `docs/` 维护类动作。
- 文档体检扩展不写 `CHANGELOG.md`（CHANGELOG 由 `release-workflow` 或项目发布流程维护）。
- 当前 PR 已 push 但 review 还没合并时，maintenance PR 与当前 PR 并行存在；用户决定合并顺序。

### PR 合并后：可选文档体检扩展

若当前项目明确配置了 `doc-curator` subagent 或同等文档体检流程，Agent 在 `gh pr merge` 成功（或 squash 推送 main 完成）后，可以按项目协议触发一次完整体检；未配置时跳过。

目的：合并后文档库状态更新（新增 ISS 归档指针、DEC 编号推进、文件行数变化），基线可能漂移；及时发现新合并项是否引入膨胀，必要时自动提 maintenance PR。

调用方式：

```bash
# 在 Agent 流程里，PR 合并完成后：
# 1. 调起项目配置的文档体检流程跑体检（如存在）
# 2. 解析报告：
#    - 全部 ok → 不动作，结束
#    - 软提示 → 报告给用户，不自动 PR
#    - 硬性 / 自适应告警 → 走 maintenance-pr.sh：
#      - 工作区干净 → 自动提 maintenance PR（按项目协议）
#      - 工作区不干净 → 仅报告，让用户处理
# 3. 如果报告项触发了 state.json 的基线更新（adaptive 阈值漂移），下一次体检会按新基线判定
```

约束：

- 与"PR 创建后体检"互补：创建后体检关注"这次提交带来的变化"，合并后体检关注"main 整体健康度"。
- 合并后体检**不阻塞合并动作**：它发生在合并完成之后，只用于发现后续问题。
- 同一 PR 不重复触发两次（创建 + 合并各一次即可，不在中间 review 轮次再触发）。
- 文档体检扩展不会因为"发现 main 不健康"而尝试 revert 刚合入的 commit；它只做文档级维护，不动代码与决策。

### 总结：本 Skill 与文档体检扩展的关系

| 时机 | 谁调起 | 做什么 | 阻塞？ |
|:-----|:-------|:-------|:-------|
| `gh pr create` 成功 | 本 Skill（如项目配置） | 体检本次变更 | 不阻塞，输出报告 + 可选 maintenance PR |
| `gh pr merge` 成功 | 本 Skill（如项目配置） | 体检 main | 不阻塞，输出报告 + 可选 maintenance PR |
| 用户手动跑 `scan.sh` | 用户 | 体检 | 不阻塞 |
| SessionEnd / pre-commit | — | 不在本 Skill 范围 | — |

`git-workflow` 只负责说明可选体检时机；具体体检逻辑、维护动作、PR 生成全部由项目配置的文档体检流程负责。两者通过 subagent 或项目协议解耦：git-workflow 不直接执行文档 trim。

## 5. 合并冲突解决

### 检测冲突

```bash
# 尝试 merge，查看冲突文件
git merge <branch> --no-commit --no-ff
git diff --name-only --diff-filter=U   # 列出冲突文件
```

### 解决原则

1. **理解双方意图**：阅读冲突标记两侧的代码，理解各自修改的目的
2. **优先保留双方**：如果双方修改不矛盾，尽量都保留
3. **最小修改**：只修改冲突区域，不要顺便重构
4. **验证**：解决后运行编译/lint/测试

### 解决流程

```bash
# 1. 查看冲突文件列表
git diff --name-only --diff-filter=U

# 2. 逐个文件解决冲突
# 编辑文件，移除 <<<<<<< ======= >>>>>>> 标记

# 3. 标记为已解决
git add <resolved-file>

# 4. 验证
# 运行编译/lint/测试确保无破坏

# 5. 完成合并
git commit
```

### lock 文件冲突

`package-lock.json`、`pnpm-lock.yaml` 等锁文件冲突时：

不要默认删除 lock 文件并重装依赖。先理解冲突两侧的依赖变更，优先用包管理器支持的锁文件合并/重算流程；确需重新生成时，`npm install` / `pnpm install` 属于依赖安装与环境写入，必须先取得用户或项目规则对**精确命令**的明确授权，并由编排层记录授权来源。无授权或工具缺失时保持阻塞并报告，不得为完成验证自行安装。

## 6. 常用 Git 操作速查

### 撤销与回退

```bash
# 撤销工作区修改（未 add）
git restore <file>

# 撤销暂存（已 add，未 commit）
git restore --staged <file>

# 查看某个文件的修改历史
git log --oneline -- <file>

# 查看某次 commit 的内容
git show <commit-hash>
```

### 暂存工作

```bash
git stash save "描述"
git stash list
git stash pop        # 恢复最近的 stash
git stash pop stash@{2}  # 恢复指定 stash
```

### Cherry-pick

Cherry-pick 用于把某个已存在 commit 回补到当前分支。它容易把无关文件一起带入，必须先确认范围。

安全流程：

```bash
# 1. 工作区必须干净
git status --short

# 2. 先看 commit 内容和影响范围
git show --stat --oneline <commit-hash>

# 3. 回补完整 commit，并保留来源记录
git cherry-pick -x <commit-hash>

# 4. 回补后确认范围
git diff HEAD~1 --stat
```

Monorepo 或只需要部分文件时，不直接 cherry-pick 整个 commit，改用目录级提取：

```bash
git checkout <commit-hash> -- <directory>/
git diff --cached --stat
git commit -m "fix(<module>): 回补指定改动"
```

关键规则：
- 跨分支 backport 默认使用 `git cherry-pick -x`，保留来源 commit。
- 不直接 cherry-pick merge commit；确需处理时，必须明确父提交并使用 `git cherry-pick -m <parent-number> -x <merge-commit>`。
- 冲突后若范围变大、意图不清或出现跨模块污染，先 `git cherry-pick --abort` 回到安全状态。
- 冲突解决后必须重新查看 `git diff --stat`，确认只包含目标改动。
- 不把 cherry-pick 当作批量同步工具；多个无关 commit 应逐个处理和验证。

### 查看状态

```bash
git status
git log --oneline -20    # 最近 20 条
git diff --stat           # 概览变更文件
git blame <file>          # 查看每行的修改者
git remote prune origin   # 清理已不存在的远端 ref（合并后清理 stale ref）
git push origin --delete <stale-branch>  # 手动删某个远端分支
# 集中审计 squash/rebase merge 后未清理的分支 → 见 §2「批量审计：已合并分支清理」
```

### Tag 管理

```bash
git tag v1.0.0
git push origin v1.0.0
git tag -d v1.0.0        # 删除本地 tag
git push origin --delete v1.0.0  # 删除远程 tag
```

### 常见事故恢复（误 amend / 误 stash / 误删分支 / 误 reset）

用户以「amend 错了」「stash 找不到了」「分支误删了」「reset 丢了东西」等口语提出时，读 `references/accident-recovery.md`。纪律：第一现场是删除输出、HEAD reflog、仍存在的引用与对象库（事故后**先不要 `git gc --prune=now`**，那会清掉待恢复对象）；恢复优先新建引用（`git branch <name> <tip>`、`git stash store <sha>`）而非改写现态，天然可逆；已 push 的事故进入历史重写授权边界（§12），`reset --hard` / force 类补救仍须用户明确指示（§1）。

## 7. Issue 与 PR 命名规范

详细规范见 `references/issue-pr-format.md`，此处为速查。

本节只管理 GitHub Issue / PR 的命名和合并提交格式。项目常规任务状态、依赖和可领取判断仍由 `cross-agent-collab` 基于项目任务源维护。

### Issue 格式

```
<类型>: <描述>
```

| 类型 | 示例 |
|:-----|:-----|
| `feat` | `feat: skill-manager 支持版本检查` |
| `bug` | `bug: 解析空文件时崩溃` |
| `enhancement` | `enhancement: 添加批量导出` |
| `docs` | `docs: 更新使用说明` |
| `question` | `question: 能接入 xxx 吗` |

关闭时添加状态标记：`[done]`（自己）、`[resolved]`（外部）、`[wontfix]`、`[duplicate]`。

### PR 格式

```
<类型>(<模块>): <描述>
```

多 Skill 仓库必须带模块名：
```
feat(skill-manager): 添加版本检查功能
fix(pdf-processor): 修复大文件解析崩溃
docs(litigation-analysis): 更新模板文档
```

### PR 合并 Commit 格式

```
<类型>(<模块>): <描述> (#<PR编号>)
```

通过 API 执行 squash merge 时，`commit_title` 不会自动追加 `(#N)`，必须手动写入。

### 直接解决 Issue 的 Commit 格式

不是每个 Issue 都会通过“分支 + PR”解决。若用户要求直接在当前分支或 `main` 上修复/关闭某个 Issue，提交标题也必须显式带 Issue 编号，让 `git log --oneline` 能直接看出来源：

```text
<类型>(<模块>): <描述> (#<Issue编号>)
```

提交正文用关闭关键字绑定 GitHub Issue：

```text
Closes #<Issue编号>

- 关键变更 1
- 关键变更 2
```

示例：

```text
docs: 清理过期待定事项 (#1)

Closes #1

- 删除过期决策记录
- 清理不再需要的待定项
```

如果编号来自项目本地任务源，而不是 GitHub Issue，不要使用 `Closes #N` 误关 GitHub Issue；改用正文标注：

```text
Refs: project-task Issue #13
```

## 8. 提交规范

提交信息使用英文类型前缀 + 中文内容。每个 commit 必须有正文，不能只有标题。

### 与 git-batch-commit 的职责边界

`git-batch-commit` 是显式调用的提交快捷按钮，适合用户要求“git 提交 / 批量提交 / 拆分提交 / 整理提交”时，把已暂存变更按类型或模块拆成多个 commit。它可以把 GitHub Issue 写成标题后缀 `(#N)`，也可以在正文写 `Refs #N` 或本地任务引用。

`git-workflow` 是 Git 规则层，负责分支、PR、push、merge、安全门禁和 Issue 关闭语义。凡涉及“合并 PR”“拉 PR 到 main”“推送到远端”“关闭 Issue”“是否使用 `Closes #N`”，都以本 Skill 为准。

### Commit 格式

```text
<类型>: <标题>

- 关键变更 1
- 关键变更 2
```

### 支持类型

| 类型 | 用途 |
|------|------|
| `docs` | 文档变更 |
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `refactor` | 代码重构 |
| `style` | 代码风格变更 |
| `chore` | 构建工具、依赖、工具链 |
| `test` | 测试添加或修改 |
| `config` | 配置变更 |
| `license` | License 文件更新 |

### 多 Skill / 多模块规则

多 Skill 仓库必须在标题中写明模块名：

```text
feat(skill-name): 添加批量导出

- 新增导出入口
- 补充参数校验
```

一次修改涉及多个独立 Skill 或模块时，应拆成多个 commit。每个 commit 只表达一个目的。

## 10. 多 worktree 并行与 main worktree 占用

### 共享检出的分支身份核验（提交前必查，2026-09-30 实录新增）

共享主检出可能被并行会话切到**它自己的 feature 分支**；此时 `git status` 干净、`git log` 正常——一切看起来可提交，但提交会落在别人的分支上随其 PR 走。规则：

```bash
# 在任何共享检出直接 commit 之前，必查当前分支身份
git branch --show-current
# 辅助警觉信号：reflog 顶部出现 checkout: moving 记录 = 有会话/操作刚切过分支
git reflog -3
```

**status/log 干净 ≠ 在你以为的分支上。** 分支对了还要核对人：commit 前跑 §1「提交前身份自检」（`bash scripts/identity-audit.sh whoami`），防共享检出被并行会话写入他人 git 身份（2026-09-30 Hermes 实录）。

误落补救（2026-09-30 private-skills 实录：迁移提交落在并行会话的 `feat/lawyer-video-cut-subtitle-pipeline` 上）：

1. **不要** `git branch -f` / `update-ref` 强移并行会话正在检出的分支——会污染它的 status 与工作树。
2. 开独立 worktree 从 `origin/main` 重做正确提交并推送（内容为准）；原误落提交保留在原分支，其提交信息注明「整理时应丢弃，以 main 为准」。
3. 并行会话的分支重整（rebase/整理）时自然丢弃该重复提交。

### 场景

并行推进多个任务时，主仓库目录（默认 attach 到 `main` 分支）与多个 PR worktree 同时存在。`gh pr merge` 在某些情况下会报 `'main' 已经被工作区 '<主仓库路径>' 使用`，原因是 gh CLI 检测到 `main` 分支被某个本地 worktree 检出（主仓库 attach 到 main）。这条 warning 常见于 cleanup 阶段，**不影响合并本身**（`mergedAt` 时间戳写入即成功）。

判断方法：

```bash
# 哪个 worktree 占用了 main？
git worktree list
# 输出示例：
# /path/to/main-repo           abc1234 [main]              ← 主仓库 attach 到 main
# /path/to/pr-45-worktree      def5678 [feat/xxx]         ← PR worktree 没事
# /path/to/main-worktree       9990000 [main]              ← 另一个 worktree 也 attach 到 main
```

### 在当前任务内处理占用

先读取 `gh pr view <N> --json state,mergedAt,mergeCommit,headRefOid,baseRefName`，核服务器实际状态。`MERGED`、时间戳和 merge OID 均存在后，检查真实交付树；本机 dirty/clean 不能证明远端是否合并。UNKNOWN、网络失败或清理报错先只读对账，不盲目重放合并。

正式合并走 safe-pr.py 的完整 range/文本预检与精确 head 绑定，默认不附删除参数。main 被其他 Worktree 检出时保持其归属和现场，不为解除提示切换共享源、不重建未声明的 develop 功能线，也不删除占用 Worktree。

确有本机同步需求时，在已有授权、归属明确的干净检出内 ff/merge；涉及长期功能线时读取其波次合同。无法同步则记录本机待同步，与已确认的云端交付分别报告。清理按独立合同进行，失败保留 CLEANUP_PENDING，不能重放已完成的 push/merge。

## 11. GitHub Actions 额度治理（CI 停挂止血）

**与 release-workflow 的职责边界**：本节负责日常 CI/Actions 配额治理——停挂止血、workflow_dispatch 化、仓级总闸与恢复。release-workflow 只在发版流程内做 CI 构建监控与配额红灯检查（打 tag 前的成本约束），不做治理动作。用户报「CI 分钟耗尽 / 停挂 / 配额告急」时以本节为准；发版语境下的 CI 故障先读 release-workflow 的发布门禁与 `references/ci-troubleshooting.md`。

### 场景

账号级 GitHub Actions 分钟额度耗尽或告警；私有仓 CI 在 push/pull_request 上高频自动触发。

### 最短判定

1. 额度是账号级且公共仓免费——先 `gh api /users/<owner>/settings/billing/actions` 看用量，
   再逐私有仓统计近 30 天 `(workflow × event)` 触发数定位大户；`push+pull_request` 双开
   即双计费。
2. 检查类（lint/unittest/build）→ 停挂为 `workflow_dispatch`（文件内注释保留原触发器与
   本地等价命令，走 PR 合并，本次 PR 不再计费）；release/deploy/签名/跨平台 → 保留；
   被 `uses:` 复用的 workflow 必须保留 `workflow_call:`。
3. 立即止血可用仓级总闸 `actions/permissions -f enabled=false`（可逆、不在 git 里可见）。

完整诊断脚本、`on:` 块改写模板、验证与事故备忘见 `references/github-actions-quota-guard.md`。

## 12. 敏感文件历史重写与全量撤回

**触发**：敏感/私有文件（数据导出、个人材料、凭证）已被 commit 并 push 到远端，用户要求"从历史里删掉/撤回提交/私有数据被上传了"。

核心纪律（详见 `references/history-rewrite-and-removal.md`）：

- **revert 不等于撤回**——历史里仍可访问；真撤回 = filter-repo 重写 + 全分支 force push。凭证类先撤销平台侧 Key，再做重写。
- **先只读排查**：泄露范围（`git log --all -- 路径`）、凭证是否曾入库、受影响远端分支面（`git branch -r --contains`）、fork 副本（`gh api` contents 查）。
- **重写绝不在主工作区跑**：全新 clone 到 /tmp → 为全部远端分支建本地分支 → `git filter-repo --invert-paths` → 验证全历史为空 → 防复发 `.gitignore` 规则作为重写后 main 的顶部提交 → force push main + 逐分支推送（zsh 下禁用 `$b:refs/...` 冒号 refspec，`$b:r` 会被解析成修饰符）→ 三件套验证（SHA 对齐 / API 404 / 分支抽查）。
- **主工作区对齐走深度分叉剧本**（全量重写后 patch-id 失效，不能常规 rebase）：三层备份（backup 分支 + **整个文件夹 rsync 全量备份**——untracked 的本地特有文件 git 备份盖不住 + 反向 diff patch）→ 敏感数据文件单独 cp 出仓（`rm --cached` 的 staged deletion 会在 reset+pop 时删掉磁盘文件）→ 甄别本地提交是否需 cherry-pick（涉及文件两侧树 diff 为 0 = 内容已在远端）→ stash（不带 -u）→ `reset --hard origin/main` → pop 解冲突 → 数据文件放回原位。
- **残留如实告知不催办**：GitHub dangling 提交仍可按 SHA 访问、fork 不跟随重写、其他本地分支/worktree 需各自 rebase、公开窗口时长——由用户评估，AI 只给事实。

## 13. 仓库膨胀审计与瘦身

**触发**：仓库或 `.git` 体积异常增长（「仓库怎么这么大」「.git 太大」「历史里有大文件」「瘦身」），高发于每日 auto-commit 的配置同步仓（dotfile/工具配置）——二进制运行时与 DB 每轮快照都进历史。

核心纪律（完整五步审计、归因矩阵与事故恢复实录见 `references/repo-bloat-audit-and-slim.md`）：

- **先只读审计，不改任何东西**：pack 构成 → 历史最大 blob 定名（`verify-pack` 排序 + `rev-list --objects` 反查；路径为空 = 不可达尸体）→ 当前跟踪构成 → `fsck --unreachable` → **本地/远端分叉检查**（配置同步仓高频病：远端早被别处重写、本地 push 长期静默失败，胖历史只活在本地一条线上）。
- **ignore 治理是治本**：配置同步仓无论私有公开一律白名单制——只入库文本配置；二进制运行时（工具链/浏览器/venv）、DB 及其一切备份形态（`*.db*`/`*.bak`/retired-wal）、缓存、会话附件、日志全部排除。gitignore 对已跟踪文件无效，老文件随历史重写一并剥离。公开仓库另跑 privacy-preflight。
- **重写前先造兜底**：filter-repo 自带 `gc --prune=now`，旧对象立即不可恢复——先确认远端完整（fetch 比对），再整目录 rsync 一份到仓外。
- **方向门（漏 `--invert-paths` = 语义反转）**：`--path X --invert-paths` 才是「删 X」；漏写变成「只留 X」，配置全被剥掉且 checkout 连带删除工作区文件。重写后**立即** `git ls-files` 按顶层核对构成 + `git log` 核对提交数，方向不对马上停——此时尚未深埋、远端未动，恢复成本最低。
- **预判两个连带损伤**：①被剥离路径的原跟踪文件会被 checkout 从磁盘删掉——是运行时目录时先确认可重装或提前 `git archive origin/main` 落盘备份；②重写前只动了被剥离路径的 chore 提交会被 prune 成空提交消失。
- **私有/公开分轨**：私有单人仓经用户明示可 force 重写全史；公开/多人仓的重写协调边界见 §12（其隔离 clone 流程同样适用瘦身场景）。
- **事故恢复按优先级**：远端未动 = 第一恢复源（fetch + reset --hard 可救回被删工作区文件）→ 应用自备份目录 → 运行中进程 `ps eww` 静默重建 env（只回填已有键，值不外显）→ APFS 快照 / Time Machine。全部落盘核对后才重推。

## 参考资源

- `references/branch-lifecycle-and-cleanup.md` — 一次性/长期分支判定、单 Worker 自动清理、批量 stale 审计、批量删除执行坑与长期功能线关闭
- `scripts/branch-audit.sh` — 分支冗余只读盘点（SAFE_DELETE / NEEDS_CONFIRM / KEEP 三档候选表，gh 缺失自动降级，绝不删除）
- `references/long-lived-integration-branch.md` — 长期集成分支的适用条件、拓扑、同步方向、波次与里程碑门禁
- `references/issue-pr-format.md` — Issue 与 PR 命名详细规范
- `references/gh-cli-quickref.md` — gh CLI 常用命令速查
- `references/github-actions-quota-guard.md` — Actions 额度诊断、停挂配方（workflow_dispatch 化）、仓级总闸、恢复与红线
- `references/history-rewrite-and-removal.md` — 敏感文件全历史撤回 SOP：只读排查、隔离 filter-repo 重写、全分支 force push、主工作区深度分叉对齐（含 stash 冲突语义与 zsh refspec 坑）、残留边界
- `references/repo-bloat-audit-and-slim.md` — 仓库膨胀审计与瘦身 SOP：五步只读审计、四类膨胀源归因矩阵、配置同步仓 ignore 白名单制、filter-repo 方向门与连带损伤预判、四级事故恢复路径（2026-10-04 Hermes 实录）
- `scripts/check-outgoing-identities.sh` — feature/PR push 前完整 PR range 的 author/committer 身份门禁
- `scripts/safe-push.sh` — 把身份与隐私核验绑定实际 immutable OID push
- `scripts/privacy_check.py` — staged/message/完整历史共用隐私检查器
- `scripts/safe-pr.py` — 检查最终 PR/squash 文本并绑定已审核 head
- `scripts/test_privacy_check.py` — 隔离隐私故障回归
- `references/privacy-preflight.md` — 精确审查、调用方法和能力边界
- `scripts/test-check-outgoing-identities.sh` — 身份门禁故障注入测试
- `scripts/identity-audit.sh` — 提交前身份自检（whoami：来源链/覆盖/env/可疑模式）、全仓 author/committer/Co-authored-by 尾注审计（history）与服务端合并回执核验（receipt）
- `scripts/test-identity-audit.sh` — 身份审计故障注入测试，含离线 gh 夹具的精确绑定、完整无绑定、截断与错误路径
- `scripts/pre-worktree-check.sh` — 开 worktree 前 3 查只读判读（IN_SYNC/AHEAD/BEHIND/DIVERGED 四态+处理路径）；`--pre-pr <branch>` 模式以 merge-tree 做提 PR 前本地合并模拟
- `scripts/test-pre-worktree-check.sh` — 3 查判读与合并模拟的故障注入测试
- `scripts/test-accident-recovery.sh` — 只用 Bash/Git 的离线恢复回归，在临时仓覆盖删除分支与曾暂存 blob 的真实恢复边界；不修改调用者仓库
- `references/accident-recovery.md` — 误 amend/误 stash/误删本地/远端分支/误 reset 的恢复路径：reflog/fsck 只读定位，恢复优先新建引用
