---
name: git-workflow
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.6.0"
license: MIT
description: Git 工作流安全助手。本技能应在需要执行分支管理、Monorepo 安全合并、PR 创建/审查/合并、冲突处理、cherry-pick、安全回退、stale/已合并分支审计与清理（branch cleanup，含 squash/rebase merge 校验）、开 worktree 前 base 同步检查（防 main drift 致 PR not mergeable）、多 worktree 并行时 main worktree 占用处理时使用。不要用于：批量生成提交信息、项目任务分配、长期任务状态管理或本地多 Agent 会话编排。
---

# Git 全流程工作流

## 触发场景

- 分支创建、切换、管理
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

push 必须走身份绑定的 `safe-push.sh`，核验**完整 PR range**后只 push 已核验的 immutable OID；不得直接 `git push`，也不得只看 `git log -1` 或 HEAD：

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

门禁逐 commit 比较 author name/email 与 committer name/email，只接受当前 worktree HEAD 与远端跟踪 base。当前 feature branch 若已跟踪同名 `origin/feat/...`，自动 upstream 会隐藏已 push 的早期 commit，因此判为 ambiguous，必须显式传 PR base。以下任一情况均 fail-closed：base 不明或不是远端跟踪 ref、用 `HEAD~1`/本地 ref 任意缩窄范围、bad revision、base 不是 HEAD 祖先、range 为空、Git 命令出错、身份字段为空或任一 commit 身份不一致。`safe-push.sh` 刷新 integration base，核验当前 HEAD，确认核验期间 HEAD 未变化，再把该 OID 精确推到目标分支，使证据绑定实际 push 对象。

## 2. 分支管理

### 创建新分支

```bash
# 从最新 main 创建
git checkout main && git pull origin main
git checkout -b <type>/<short-description>

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

### 分支清理

合并后的分支应及时删除：

```bash
# 删除本地分支
git branch -d <branch-name>

# 删除远程分支
git push origin --delete <branch-name>
```

### 批量审计：已合并分支清理

仓库累积了一批已合并 PR 后做集中清理时，**不要**只用 `git branch --merged main` 判断。

**核心陷阱**：`git branch --merged` 只识别"提交可达"，对 **squash merge** / **rebase merge** 一律失效——main 上的合并 commit 是新生 SHA，原分支 tip 不在 main 历史里，分支会被误判为未合并。

**陷阱 2（活跃分支误判,2026-06-30 实战教训）**：`--merged main` 也会**反向误判**——一个**刚创建、工作还没 commit** 的活跃分支会停在 main commit（没分叉），从而显示"已合并"。只看 `--merged` 会把"刚开展、未提交"的进行中工作当成 stale 删掉。**`--merged main` 两个方向都不可靠**：squash merge 漏判（陷阱 1）+ 活跃分支误判（陷阱 2）。

**权威依据**：PR 在远端的 `state == MERGED` **+ 分支最后提交时间**。时间是最稳的"活跃度"信号——见下方时间过滤。

#### 时间过滤（活跃度判定的主信号,2026-06-30 加）

`--merged` / PR 状态只能判"工作是否进 main",判不了"分支是否还在被用"。**最后提交时间**才是活跃度主信号：

```bash
# 远程分支 + 最后提交日期(旧→新排序)
git for-each-ref --sort=committerdate refs/remotes/origin/ \
  --format='%(committerdate:short) %(refname:short)' | grep -v 'origin/HEAD'
# 本地分支同理:refs/heads/
```

**默认阈值:最后提交 < 24h 的分支一律保留(活跃,可能是刚开展/重跑的工作),不得删除。** 只有 > 24h(可配置,如 7 天更稳)的才进删除候选。时间过滤 + PR 状态 + 下面三查,缺一不可。

#### 审计流程

```bash
# 1. 快照当前状态
git branch -vv                   # 本地分支 + 跟踪信息
git branch -r                    # 远程分支
git worktree list                # worktree 占用情况

# 2. 列候选（仅作为参考，不能作为删除依据）
git branch --merged main
git branch -r --merged origin/main | grep -v 'origin/main\|origin/HEAD'
git branch --no-merged main
git branch -r --no-merged origin/main | grep -v 'origin/main\|origin/HEAD'

# 3. 关键：用 PR 状态交叉验证（squash/rebase merge 必须）
gh pr list --state merged --search "head:<branch>" \
  --json number,title,mergedAt

# 或批量映射近期 PR ↔ 分支
gh pr list --state all --limit 50 \
  --json number,state,headRefName,mergedAt,closedAt
```

#### 判定规则

| 信号 | 处理 |
|------|------|
| 分支 tip 可达 `main`（Step 2 "merged" 输出） | 安全删除（merge commit 形式） |
| `gh pr list --state merged` 能查到对应 PR | 安全删除（squash / rebase merge） |
| `gh pr list` 显示 `state == CLOSED` 且非 `MERGED` | **询问用户**：工作可能已废弃，但分支不一定该删 |
| 本地分支无对应远程 PR 且未推送 | **询问用户**：可能是未推送的 WIP |
| 远程跟踪 ref 在远端已不存在 | `git fetch --prune` 或 `git remote prune origin` 清理本地引用 |
| **最后提交 < 24h**(任一分支,本地/远程) | **保留——活跃,可能是刚开展或刚重跑的工作**(陷阱 2)。即使 `--merged main` 也别删 |
| worktree 有未提交改动(`git -C <wt> status` 非空) | **保留 worktree + 分支,绝不 `--force` 删**。`--force` 会丢弃未提交工作 |

辅助指纹：`git rev-list --left-right --count main...origin/<branch>` 返回 "ahead N, behind 1" 是 squash-merged 的典型形态（分支自身的 commits 不在 main，main 的 squash commit 不在分支）。它是**提示**而非证据，仍以 `gh pr list` 为准。

#### 删除（fail-closed，必须先取得用户确认）

向用户展示候选表后再批量删除：

| 分支 | 本地 | 远程 | PR | 判定 |
|------|------|------|----|----|
| feat/foo | 无 | 有 | #27 MERGED | 安全删除 |
| fix/bar | 有 | 有 | #28 MERGED | 安全删除 |
| wip/baz | 有 | 无 | — | 询问用户 |

```bash
# 批量删除远程分支
git push origin --delete <b1> <b2> <b3>

# 删除本地分支（先 -d；refuse 后再讨论是否升级到 -D）
git branch -d <branch>

# 清理本地的 stale 远程跟踪 ref
git fetch --prune
# 或 git remote prune origin
```

#### 红线（fail-closed）

- ❌ **仅凭 `git branch --merged` 删除**：在 squash/rebase merge 仓库会漏判，在 merge commit 仓库才完整。
- ❌ **仅凭 ahead/behind 删除**：WIP 分支也会"ahead 多个 commit"。
- ❌ **把 `CLOSED` 当 `MERGED`**：closed-without-merge 是被废弃，删除前必须问用户。
- ❌ **跳过用户确认直接 `git push origin --delete`**：远端删除对协作者可见，难撤销。
- ❌ **删最后提交 < 24h 的分支**(2026-06-30 教训):活跃分支可能停在 main commit、`--merged` 显示已合并,但实际是刚开展/重跑的工作。必须先 `git for-each-ref`(时间)过滤。
- ❌ **盲用 `git worktree remove --force`**:先 `git -C <worktree> status --short`,有未提交改动就停——`--force` 会丢弃。误删活跃 worktree 的未提交工作只能靠重跑恢复。
- ❌ **只凭 `--merged main` 删本地分支/worktree**:陷阱 1(squash 漏判)+ 陷阱 2(活跃分支误判)两个方向都不可靠;必须 PR 状态 + 时间 + 未提交三查。
- ❌ **用 `git branch -D` 强删本地以"对齐远端"**：会丢未推送的 WIP。

### Worktree（工作树）

#### 开 worktree 前的必做 3 查（防止 base 过期导致 PR 报 not mergeable）

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
| 本地 main 领先 origin/main | `git log origin/main..main` 有 commit（本地独有未 push） | **先 push 或 merge origin/main**，决定见下方"本地独有 commit 处理" |
| 本地 main 落后 origin/main | `git log main..origin/main` 有 commit（origin 已合，本地没 fetch） | **先 `git pull --no-rebase`（merge origin/main）再开 worktree** |
| 本地与 origin/main 双向分叉 | 双方各有独有 commit | **先 rebase 或 merge**，避免 PR 冲突 + 重新编号 |

**禁止** 基于"过期 main"开 worktree 后再补救。会引发：PR 报 not mergeable → 本地 rebase 解决 → 决策编号撞车（如 DECISIONS.md 在 main 与 PR 都有新增）→ 重新编号 + push `--force-with-lease`。一次性 3 查可避免。

#### 本地独有 commit 未 push 的处理（3 查清单的延续）

`git log origin/main..main` 显示本地独有 commit 时，三选一：

| 选项 | 适用场景 | 操作 |
|---|---|---|
| **A. Push 到 origin** | 独有 commit 是想让 origin 看的（如 docs 标记、版本号） | `git push origin main`（**禁止**直接 push main，先确认无保护规则；如保护则改 PR 流程） |
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

**禁止 `git merge` 直接合并 feature 分支到 main。** Feature 分支若从旧 commit 创建，直接合并会误删所有不在分支里的文件。

### 正确做法：目录级 checkout

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

1. **先 rebase** feature 分支到最新 main，确保 base commit 包含所有文件
2. 确认 PR diff 只涉及目标 Skill 目录
3. 使用 squash merge，commit 标题包含模块名和 PR 编号

```bash
# rebase feature 分支
git checkout <feature-branch>
git rebase origin/main
git push --force-with-lease  # rebase 后需要 force push
```

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

# 3. 从本地提交恢复被误删的目录
git checkout <本地commit-hash> -- <skill-directory>/

# 4. 单独提交恢复的文件
git diff --cached --stat   # 确认恢复的文件
git commit -m "feat(<skill>): 恢复被误删的文件"
git push origin main
```

**关键**：`git reflog` 保存了所有操作历史，即使 rebase 后本地提交也不会真正丢失。

## 4. PR 工作流

### 创建 PR

```bash
# 推送分支
git push -u origin <branch-name>

# 创建 PR
gh pr create \
  --title "feat(module): 简短描述" \
  --body "$(cat <<'EOF'
## 摘要
- 关键变更 1
- 关键变更 2

## 测试计划
- [ ] 验证项 1
- [ ] 验证项 2
EOF
)"
```

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
# Squash merge（推荐）
gh pr merge <number> --squash \
  --subject "feat(module): 描述 (#<number>)" \
  --body "关键变更说明"

# Merge commit
gh pr merge <number> --merge

# Rebase merge
gh pr merge <number> --rebase
```

**重要**：通过 API 执行 squash merge 时，`commit_title` 不会自动追加 `(#N)`，必须手动写入。

### 自 PR 自 review 限制（GitHub 强制）

GitHub **不允许 PR 作者自 approve 自已的 PR**：

```
gh pr review <N> --approve
# → failed to create review: GraphQL: Review Can not approve your own pull request (addPullRequestReview)
```

这是 GitHub 设计，无法绕过。但 **`gh pr merge --squash --delete-branch` 不需要 review approval**（前提：仓库无强制 review 的 branch protection）。常见场景：

| 场景 | 处理 |
|---|---|
| 无 branch protection 或不要求 review | `gh pr merge <N> --squash --delete-branch` 直接合 |
| 要求 ≥ 1 个 review | 找他人 review；或 admin override `gh pr merge <N> --squash --admin`（谨慎，记录原因） |
| 自 PR 自 review 完全禁止 | 用其他账号 review；或拆 PR 让别人创建 |

**常见坑**：`gh pr merge --delete-branch` 在 cleanup 阶段可能报 `'main' 已经被工作区 '<主仓库路径>' 使用`（多 worktree 场景，见 §10），这是 warning，不影响合并本身——`mergedAt` 时间戳写入 GitHub 即代表合并成功。

### 本地拉取 PR 到 main 的提交格式

当用户要求“拉取 PR 到主分支 / 把 PR 拉进 main / 合入这个 PR”时，默认目标是让 `main` 历史中能直接看出来源 PR。不要用 `git pull --ff-only origin pull/<N>/head` 作为最终合入方式，因为 fast-forward 会保留 PR 原提交标题，通常不会显示 `(#N)`。

默认使用 squash commit 方式在 `main` 上生成一个带 PR 编号的提交：

```bash
# 1. 更新 main
git checkout main
git pull --ff-only origin main

# 2. 检查 PR 状态与 diff
gh pr view <N> --json title,state,isDraft,mergeable,reviewDecision,headRefName,baseRefName,url
gh pr diff <N> --name-only
gh pr checks <N>

# 3. 拉取 PR head 并 squash 到暂存区
git fetch origin pull/<N>/head
git merge --squash FETCH_HEAD
git diff --cached --stat

# 4. 使用 PR 标题 + PR 编号提交
git commit -m "<PR 标题> (#<N>)" \
  -m "PR: <PR URL>"

# 5. 推送 main，并关闭原 PR（若 GitHub 未自动标记 merged）
git push origin main
gh pr close <N> --comment "已通过提交 <sha> 合入 main。"
```

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
| 冲突仅在 docs 同步文件（CHANGELOG / DECISIONS / TASKS） | `git diff main..HEAD -- docs/` 显示 diff 是 docs 同步段（版本号、DEC 编号、ISS 任务卡进度） | **方案 A：本地 rebase + 解决冲突**。接受 base 新内容，把 head 的 docs 段重新编号（如 DEC-026 → DEC-030）后 `git rebase --continue`；push 用 `--force-with-lease`。 |
| 冲突在共享代码 / 实质代码 | `git diff main..HEAD` 涉及 src/ src-tauri/ src/shared/ 等多文件 | **方案 B：关掉 PR + 重建**。`gh pr close <N> --delete-branch`；`git switch -C <branch> origin/main`；cherry-pick 实质代码 commit（跳过 docs 同步 commit）；重新写 docs 同步（使用最新 main 已占用的编号 +1）；push + new PR。 |
| 冲突极少 / 1-2 个文件 | `git diff main..HEAD` 改动小且冲突集中 | **方案 C：GitHub PR UI 手动解决**。在 PR 页面 "Resolve conflicts" → 编辑 → commit。 |

**禁止** `git push --force`（不带 `--force-with-lease`），可能在远端已有他人 push 时覆盖。

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

### 解决方案三选一

#### 方案 A：主仓库不 attach 到 main（推荐）

让主仓库 attach 到一个长期开发分支（如 `develop`）或 detached，避免占用 main：

```bash
# 主仓库切到 develop
git checkout develop

# gh pr merge 在任意位置跑都不再受 main 占用影响
gh pr merge <N> --squash --delete-branch
```

**适用**：日常开发主仓库不直接在 main 上工作。

#### 方案 B：用 `git worktree add` 给 main 单独一个 worktree

主仓库 detached，专门开一个 `main` worktree：

```bash
# 主仓库 detached（不 attach 任何分支）
git checkout --detach HEAD

# main 用专门 worktree
git worktree add ~/.config/superpowers/worktrees/main main

# gh pr merge 在主仓库跑：main reference 现在属于独立 worktree，不冲突
gh pr merge <N> --squash --delete-branch
```

**适用**：希望保留 main 在本地随时可见，但要避免主仓库占用。

#### 方案 C：先释放 main 再合并

临时操作，merge 完恢复：

```bash
# 主仓库暂时切到其他分支（或 detached）
git checkout --detach HEAD

# 合并 PR
gh pr merge <N> --squash --delete-branch

# merge 完成后回到 main（如需要）
git checkout main
```

**适用**：一次性操作，不愿长期改动主仓库 attach 状态。

### 推荐

**方案 A 最简单**：让主仓库 attach 到长期分支（`develop` / `main-next` 等），`gh pr merge` 不再受 main 占用影响。`git worktree list` 命令随时可查 worktree 占用情况。

`gh pr merge` cleanup warning 时的快速判断流程：

```
1. 看 gh pr view <N> --json state,mergedAt,mergeCommit
   - state == "MERGED" + mergedAt 有值 + mergeCommit 有 oid → 合并成功，warning 可忽略
   - state != "MERGED" → 合并真失败，需重新执行

2. 看主仓库 git status --short
   - 干净 → 真合了
   - 有冲突标记 → 合并中途退出，需手工恢复
```

## 参考资源

- `references/issue-pr-format.md` — Issue 与 PR 命名详细规范
- `references/gh-cli-quickref.md` — gh CLI 常用命令速查
- `scripts/check-outgoing-identities.sh` — feature/PR push 前完整 PR range 的 author/committer 身份门禁
- `scripts/safe-push.sh` — 把身份核验绑定实际 immutable OID push
- `scripts/test-check-outgoing-identities.sh` — 身份门禁故障注入测试
