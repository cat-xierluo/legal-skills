---
name: git-workflow
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.1.0"
license: MIT
description: Git 全流程工作流助手。覆盖分支创建、Monorepo 安全合并、PR 管理、合并冲突解决、常规 Git 操作。当用户进行分支管理、合并代码、创建/审查 PR、解决冲突等 Git 操作时自动触发。
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

| 前缀 | 用途 | 示例 |
|:-----|:-----|:-----|
| `feat/` | 新功能 | `feat/batch-export` |
| `fix/` | Bug 修复 | `fix/null-pointer` |
| `docs/` | 文档 | `docs/api-guide` |
| `refactor/` | 重构 | `refactor/parser` |
| `chore/` | 杂项 | `chore/update-deps` |

### 分支清理

合并后的分支应及时删除：

```bash
# 删除本地分支
git branch -d <branch-name>

# 删除远程分支
git push origin --delete <branch-name>
```

### Worktree（工作树）

当需要同时在多个分支上工作时，使用 worktree 避免频繁切换分支：

```bash
# 创建 worktree（自动创建新分支）
git worktree add ../feature-ocr feat/ocr-support

# 在 worktree 中工作
cd ../feature-ocr
# ... 编辑、提交 ...

# 完成后回到主工作目录
cd -

# 删除 worktree
git worktree remove ../feature-ocr

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
## Summary
- 关键变更 1
- 关键变更 2

## Test plan
- [ ] 验证项 1
- [ ] 验证项 2
EOF
)"
```

### PR 正文最低要求

创建或审查 PR 时，正文至少包含：

| 区块 | 要求 |
|------|------|
| `Summary` | 说明改了什么，避免只有“update files” |
| `Test plan` | 列出已运行或未能运行的验证；未运行要写原因 |
| `Agent Attribution` | 若由 Agent 完成，写明 Agent ID、Git author、触发来源 |
| `Issue/Task` | 关联 GitHub Issue、`docs/ISSUES.md` Issue ID 或用户指定任务 |
| `Risk` | 涉及迁移、删除、权限、安全、跨模块改动时说明风险和回退方式 |

缺失 `Summary` 或 `Test plan` 时，不应 approve；缺失 `Agent Attribution` 时，要求补齐后再合并。

### PR 标题格式

```
<类型>(<模块>): <描述>
```

与 commit 格式一致，multi-skill 仓库必须带模块名。

### 审查 PR

```bash
# 查看 PR 详情
gh pr view <number>

# 查看 PR 文件变更
gh pr diff <number>

# 添加 review
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

### Fail-Closed 合并门禁

以下任一情况出现时，不得自动合并，必须停下并让人类确认或先修复信号来源：

| 阻断条件 | 处理 |
|----------|------|
| `gh pr diff` 失败、diff 为空或不可读 | 不 approve，不 merge；先确认分支和权限 |
| CI/checks 失败、等待中、缺失或状态未知 | 不 merge；需要明确通过或用户显式确认 |
| review 结论缺失、互相矛盾或只是摘要没有 verdict | 不 merge；补一次明确 review |
| PR diff 超出声明范围，尤其是 Monorepo 误删文件 | 不 merge；先缩小 diff 或拆分 PR |
| 分支保护、required checks、linked issue 状态不清楚 | 不 merge；先查清仓库规则 |

`git-workflow` 只维护这些 Git 安全规则；任务状态仍由 `cross-agent-collab` / `docs/ISSUES.md` 管理，本地 Agent 会话由 `parallel-agent-workflow` 管理。

### PR 状态检查

```bash
# 查看 CI 状态
gh pr checks <number>

# 查看所有 PR 列表
gh pr list --state open

# 更新 PR 分支（同步最新 main）
gh pr update-branch <number>
```

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

```bash
# 删除 lock 文件，重新生成
rm package-lock.json
npm install   # 或 pnpm install
git add package-lock.json
```

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

本节只管理 GitHub Issue / PR 的命名和合并提交格式。项目常规任务状态、依赖和可领取判断仍由 `cross-agent-collab` 基于 `docs/ISSUES.md` 维护。

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

Multi-Skill 仓库必须带模块名：
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

## 8. 提交规范

提交信息使用英文类型前缀 + 中文内容。每个 commit 必须有正文，不能只有标题。

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

### Multi-Skill / Multi-Module 规则

Multi-Skill 仓库必须在标题中写明模块名：

```text
feat(skill-name): 添加批量导出

- 新增导出入口
- 补充参数校验
```

一次修改涉及多个独立 Skill 或模块时，应拆成多个 commit。每个 commit 只表达一个目的。

## 参考资源

- `references/issue-pr-format.md` — Issue 与 PR 命名详细规范
- `references/gh-cli-quickref.md` — gh CLI 常用命令速查
- `TASKS.md` — 本 Skill 的维护任务和后续上下文
