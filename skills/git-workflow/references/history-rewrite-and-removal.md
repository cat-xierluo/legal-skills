# 敏感文件历史重写与全量撤回 SOP

> 适用：敏感/私有内容（数据导出、个人材料、凭证）已被 commit 并 push 到远端（尤其公开仓），需要从**全部历史**抹除。实例基线：2026-10-03 legal-skills star 数据撤回（main + 30 分支全量重写 + 主工作区深度分叉对齐）。
>
> 不适用：只需撤销最近一次提交（用 revert/reset 即可）；只需删除当前版本但历史可留（`git rm` + commit）。

## 0. 判定与红线

- **revert 不等于撤回**：revert 只让最新树不含该文件，任何人都还能从历史提交读到。真撤回必须重写历史 + force push。
- **凭证类（token/key/密码）先撤销再重写**：平台侧撤销 Key 优先级最高——历史重写不解决"已被复制"的问题。确认凭证是否曾入库：`git log --all --oneline -- <路径>`（输出为空 = 从未提交过，只需处理现存数据）+ 全历史内容扫描。
- **破坏性等级最高**：force push 重写远端 + reset 主工作区。每一步都要用户明确授权；本 SOP 的命令清单不构成免授权。

## 1. 前置排查（全部只读，不动任何东西）

```bash
# a. 泄露范围：哪些文件被追踪、全历史哪些提交涉及
git ls-files | grep <关键词>
git log --all --oneline -- <敏感路径>

# b. 凭证是否曾入库（.env 类）
git log --all --oneline -- <env路径>          # 空 = 从未提交
git ls-files <env路径>                         # 空 = 当前未追踪

# c. 受影响分支面：泄露提交在多少远端分支上
git branch -r --contains <泄露提交SHA>

# d. fork 检查（fork 不跟随上游重写，是最常见残留）
gh api repos/<fork所有者>/<repo>/contents/<敏感路径> --jq '.size'

# e. 主工作区分叉状态（决定 §5 对齐难度）
git rev-list --left-right --count main...origin/main
```

注意：`git log --all` 只覆盖本地 fetch 到的 refs；GitHub 上可能有本地未 fetch 的分支提交（用 `gh api repos/<owner>/<repo>/commits?path=<路径>` 交叉验证）。

## 2. 隔离重写（绝不在主工作区跑 filter-repo）

```bash
# a. 全新 clone（与主工作区完全隔离，不受未提交改动影响）
git clone <url> /tmp/<repo>-rewrite && cd /tmp/<repo>-rewrite

# b. 为所有远端分支建本地分支（filter-repo 重写所有 refs）
git branch -r | grep 'origin/' | grep -v HEAD | sed 's| *origin/||' \
  | while read b; do git branch -f "$b" "origin/$b"; done

# c. 重写：抹除敏感路径的全部历史
git filter-repo --force --invert-paths \
  --path <敏感路径1> --path <敏感路径2>

# d. 验证：全历史无该路径、涉及它的提交已被剪除
git log --all --oneline -- <敏感路径>          # 必须为空
```

filter-repo 行为须知：会**移除 origin remote**（推送前重新 `git remote add`）；会把 `refs/remotes/origin/*` 转成本地分支；空提交（重写后无差异）默认被剪除。

## 3. 防复发规则与推送

在重写后的 main 上，把 `.gitignore` 规则作为**顶部提交**（规则与重写一次到位，之后任何人 clone 下来就带防护）：

```bash
cat >> .gitignore << 'EOF'
# <skill> 运行导出产物含私有数据，仅限本地
<敏感目录>/
EOF
git add .gitignore && git commit -m "chore(<模块>): 忽略 <产物> 目录，防止私有数据入库"
```

推送（先 main 后分支，逐个推，别批量拼 refspec——见下方坑）：

```bash
git remote add origin <url>
git -c http.proxy= push --force origin main
for b in $(git branch --format='%(refname:short)' | grep -v '^main$'); do
  git -c http.proxy= push --force origin "$b"
done
```

**zsh 大坑（实测）**：`git push origin "refs/heads/$b:refs/heads/$b"` 里的 `$b:r` 被 zsh 解析为变量修饰符（去扩展名），refspec 静默损坏成 `...readiness-261002efs/heads/...`，推送全部失败且易被输出过滤吞掉。**批量推分支一律用 `git push origin "$b"` 简单形式**。

推送后验证三件套：

```bash
# 1. SHA 对齐：本地每个分支 == 远端对应分支（fetch 后逐个 rev-parse 对比，0 不一致）
# 2. API 验证：gh api repos/<o>/<r>/contents/<敏感路径>            → 404
#              gh api "repos/<o>/<r>/commits?path=<敏感路径>" --jq 'length' → 0
# 3. 分支抽查：gh api "repos/<o>/<r>/contents/<敏感路径>?ref=<分支>" → 404（抽 3+ 个）
```

## 4. 残留与边界（必须如实告知用户，不催办不隐瞒）

| 残留 | 性质 | 处置 |
|---|---|---|
| GitHub dangling 提交（旧 SHA 仍可直接访问） | force push 后 GitHub 不立即物理删除 | 彻底清除需联系 GitHub 支持；用户可自行评估接受与否 |
| fork 上的副本 | fork **不跟随**上游重写 | 同上；实例中 fork 副本与泄露内容敏感度相同时一并列出 |
| 其他本地分支/worktree 仍指旧历史 | 重写必然结果 | 各自会话 push 时遇 non-fast-forward，自行 rebase；不代劳 |
| 公开窗口时长 | 数据已暴露的时间 | 由用户评估实际风险，AI 只给事实（起止时间、内容类型、条数） |

## 5. 主工作区对齐（深度分叉剧本）

远端全量重写后，泄露提交**之后**的所有提交 SHA 全变，本地 main 与新远端的共同祖先退到泄露点之前——`git cherry`/patch-id 全部失效，不能按常规 rebase 处理。

### 5.1 备份三层（动手前全部完成）

```bash
# 1. git 层：旧历史完整保留
git branch backup/main-pre-rewrite-<日期> main

# 2. 文件层：整个文件夹全量备份（含 untracked 的本地特有文件，如被 .gitignore
#    排除的 DECISIONS/TASKS——git 备份覆盖不到它们）
rsync -a <仓库>/ ~/<repo>-backup-<日期>/

# 3. 差异层：本地 vs 新远端的完整反向补丁（回溯单文件用）
git fetch origin && git diff origin/main main > /tmp/<repo>/main-pre-rewrite-vs-origin.patch
```

**数据文件单独备份（实测坑）**：若之前做过 `git rm --cached`（staged deletion 挂在 index），`reset --hard` + `stash pop` 会把该文件从磁盘**删掉**——stash 记录了 deletion，pop 时会应用。任何要保留的敏感数据文件，reset 前先 `cp` 到仓库外。

### 5.2 甄别是否需要 cherry-pick

本地 main 顶端的"独有"提交可能只是 SHA 不同、内容已通过 PR 在远端：

```bash
# 提交涉及文件在两侧的树差异为 0 行 = 内容等价已在远端，无需回放
files=$(git show --name-only --format="" <SHA> | tr '\n' ' ')
git diff origin/main main -- $files | wc -l
```

全部为 0 → 直接 reset 对齐，不 cherry-pick 任何东西。注意甄别结论与全仓 diff 不矛盾：全仓反向 diff 仍会有"本地比远端旧"的旧侧差异（远端三个月演进的另一面），那是预期噪声。

### 5.3 对齐执行

```bash
# 1. stash（不带 -u：untracked 留在磁盘且不受 reset 影响）
git stash push -m "pre-align-<日期>-同步前保底"

# 2. reset 到新历史
git reset --hard origin/main

# 3. 恢复未提交改动
git stash pop        # 有冲突见 5.4；pop 失败时 stash 条目自动保留，不丢数据

# 4. 恢复数据文件到原位（现在受新 .gitignore 保护，untracked）
cp <备份>/<文件> <原路径>/
```

### 5.4 冲突解决（stash pop 冲突的特殊语义）

冲突标记：`<<<<<<< Updated upstream` = **新 HEAD 侧**（重写后的远端），`>>>>>>> Stashed changes` = **本地未提交改动侧**。

| 冲突形态 | 判定 | 解法 |
|---|---|---|
| 远端侧空、本地有 | 本地未提交的新工作（版本演进、新段落） | 取本地 |
| 本地侧空、远端有 | 远端已合并内容 | 取远端 |
| 两侧都有，且一侧是另一侧的演进（版本号更新、内容超集） | 本地通常是 PR 合并后的继续演进 | 取本地 |
| 两侧是**不同条目**（任务台账 TASKS 各自新增任务卡、CHANGELOG 各自版本号） | 谁都不能丢 | 两侧全保留拼接 |
| 同一文件的同一功能两侧各写一半（如两个脚本配套改动） | 必须同侧一致 | 同取本地或同取远端，禁止各取一半 |

批量技巧：先用脚本按"单侧为空"批量解（只动冲突块、不动已自动合并的非冲突区），剩余"两侧都有"逐块人工判断：

```python
import re
pattern = re.compile(r'<<<<<<< Updated upstream\n(.*?)=======\n(.*?)>>>>>>> Stashed changes\n', re.S)
def resolve(m):
    up, th = m.group(1), m.group(2)
    if not up.strip() and th.strip(): return th    # 远端空 → 本地
    if up.strip() and not th.strip(): return up    # 本地空 → 远端
    return m.group(0)                              # 留待人工
```

### 5.5 收尾验证

```bash
git log --oneline -1                      # = 新 origin/main 顶部
git rev-list --count origin/main..main    # = 0（零分叉）
grep -rl "^<<<<<<< " .                    # 无残留冲突标记
ls <敏感路径> && git check-ignore <敏感文件>   # 数据文件在 + 已被忽略
git worktree list                          # worktree 正常、基于新历史
```

untracked 的本地特有文件（DECISIONS/TASKS 等）不受 reset 影响，抽查确认即可；数量变化只是新版 `.gitignore` 规则改变了 status 显示，不是文件消失（`git status --ignored` 可复核）。

## 6. 源头排查要点（泄露怎么进来的）

按成本从低到高：定时任务（`crontab -l`、`launchctl list`、LaunchAgents）→ skill 自身是否有自动提交逻辑（grep scripts/ 里的 git 命令）→ 会话记录（Codex `~/.codex/sessions/`、Claude `~/.claude/projects/`、按敏感文件名 grep）→ 提交元数据（作者/提交者是否 bot 邮箱、提交信息风格、有无 PR 号——**直推 main 无 PR 号 + 凌晨时段**是自动任务的典型指纹）。排查无果时存档线索、不猜结论。

## 7. 实战时间线参考

261003 legal-skills 实例：发现（用户）→ 只读排查（范围/凭证/分支面/fork）→ 隔离 clone + filter-repo 抹 2 文件 → 防复发 .gitignore 进 main 顶部 → force push main + 30 分支（含 zsh refspec 坑返工一次）→ 三件套验证 → 残留告知（fork + dangling，用户按数据敏感度结案）→ 主工作区三层备份 + 数据文件单独备份 → 甄别（5 提交内容全在远端，零 cherry-pick）→ stash/reset/pop + 16 文件 42 处冲突全解 → 零分叉收尾。
