# 常见事故恢复路径（误 amend / 误 stash / 误删分支）

覆盖四类高频 Git 事故的只读定位与安全恢复。全部恢复动作遵守两条总纪律：**先只读定位、后恢复**（reflog / fsck / show 核实内容再动引用）；**恢复优先新建、不改写**（新建分支或引用不动任何现态，天然可逆；reset / force 类操作必须用户明确指示）。

## 0. 第一现场：reflog 与 fsck

- `git reflog` 默认保留 90 天（`gc.reflogExpire`），不可达条目 30 天（`gc.reflogExpireUnreachable`）。事故后**先不要跑 `git gc --prune=now`**——那会真的清掉待恢复对象。
- 误删的分支有自己的 reflog：`git reflog show <branch>` 在删除后仍可读（reflog 文件 `logs/refs/heads/<name>` 保留到过期）。
- 找无引用指向的悬空提交：`git fsck --no-reflogs --unreachable | grep commit`；确认内容再用：`git show <sha> --stat` / `git log --oneline <sha>`。

## 1. 误 amend（改错内容 / 丢了原提交信息，且未 push）

原理：amend 创建新提交，旧提交是完整对象，只是失去引用——reflog 里就是 `commit (amend)` 的**上一条**。

```bash
# 1. 定位旧提交（amend 前的原 tip）
git reflog -5                 # 找 "commit (amend)" 行的前一条

# 2. 核实旧提交内容确实是想要的
git show <old-tip> --stat

# 3a. 整体回到旧提交（保留工作区，amend 后的改动回到暂存区）
git reset --soft <old-tip>

# 3b. 只找回提交信息（保留 amend 后的树）：从旧提交拷 message
git log -1 --format=%B <old-tip>
```

红线：

- 已 push 的 amend = 历史重写，回到主 Skill §1 授权边界；本技能 safe-push 不支持 force，不退回裸 push。
- `reset --soft` 在误 amend 的分支上是撤销 amend（新提交仍留在 reflog 可再找回），但执行前确认没有并行会话已基于 amend 后的提交工作。

## 2. 误 stash（pop 冲突以为丢了 / drop 错了）

关键事实（先读再动手，多数"丢 stash"是误判）：

- `git stash pop` **有冲突时 stash 条目不会被删**——冲突解决完、`git status` 干净后它仍在 `git stash list`，需要手动 `git stash drop`。pop 冲突时工作区呈现「Updated upstream / Stashed changes」两段语义，那是冲突标记不是丢数据。
- `git stash apply` 永远不删条目；不确定时用 apply，确认后再 drop。
- untracked 文件（`stash -u`）存在 stash 提交的**第三个 parent**（`stash@{0}^3`），找回时别只看第一个 parent。

误 drop / pop 后想反悔的恢复：

```bash
# 1. 找悬空的 stash 提交
git fsck --no-reflogs --unreachable | grep commit
# 或直接看候选内容（逐个确认，stash 提交有 2-3 个 parent）
git show --stat <sha>

# 2. 重新登记为 stash 条目（不动工作区）
git stash store -m "recovered stash" <sha>
git stash list                    # 确认回来了
git stash show -p 'stash@{0}'     # 核内容再决定 apply
```

## 3. 误删本地分支（branch -d / -D 后）

原理：删分支只删引用；提交仍通过分支自己的 reflog 与对象库可达（§0）。

```bash
# 1. 读被删分支自己的 reflog，最后一条就是删除前的 tip
git reflog show <deleted-branch> | head -3

# 2. 核内容
git log --oneline <tip> -5

# 3. 新建引用恢复（不动任何现态，随时可再删）
git branch <deleted-branch> <tip>
```

找不到 reflog 时（关了 reflog / 已被 gc）：按 §0 fsck 找悬空提交，逐个 `git show` 认领。

预防（与 [branch-lifecycle-and-cleanup.md](branch-lifecycle-and-cleanup.md) 一致）：删除前先跑 `scripts/branch-audit.sh` 只读盘点，squash/rebase 合并的分支用 MERGED PR 记录与 patch-id 双核对判死，不凭 `-D` 强删。

## 4. 误删远端分支（push origin --delete 错了）

- 本地有同名分支或 reflog：重新 `git push origin <branch>` 即可恢复。
- 本地也没有：GitHub 上 PR 的 head 分支被删后，PR 页面提供 **Restore branch** 按钮（GitHub 侧保留提交），恢复后本地 `git fetch` 取回。
- 无 PR 且无人有副本：提交仍可按 SHA 访问（GitHub dangling 对象），但引用恢复没有机械路径——如实报告，不臆测。

## 5. 误 reset --hard / checkout . / clean -f（丢弃工作区未提交内容）

- **已提交**的内容：按 §0 reflog 找回 tip，`git branch backup/<desc> <tip>` 新建引用恢复。
- **未提交**的内容：Git 层面无法恢复——这正是主 Skill §1 把这些操作列为禁止项的原因。可尝试的非 Git 途径：IDE 本地历史（JetBrains Local History / VS Code Timeline）、Time Machine、项目的整目录 rsync 备份纪律（见 [history-rewrite-and-removal.md](history-rewrite-and-removal.md) 的三层备份——untracked 的本地特有文件 git 备份盖不住）。

## 6. 误 commit 到错分支（落到并行会话的分支上）

不自创恢复路径，按主 Skill §10「共享检出的分支身份核验」的既定处理：不 `git branch -f` 强移并行会话正在检出的分支；开独立 worktree 从正确 base 重做提交并推送，原误落提交保留并在提交信息注明「整理时应丢弃，以 main 为准」。
