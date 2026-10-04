# 敏感文件历史重写与全量撤回 SOP

> 适用：敏感/私有内容（数据导出、个人材料、凭证）已被 commit 并 push 到远端（尤其公开仓），需要从**全部历史**抹除。实例基线：2026-10-03 legal-skills star 数据撤回（main + 30 分支全量重写 + 主工作区深度分叉对齐）。
>
> 不适用：只需撤销最近一次提交（用 revert/reset 即可）；只需删除当前版本但历史可留（`git rm` + commit）。

## 0. 判定与红线

- **revert 不等于撤回**：revert 只让最新树不含该文件，任何人都还能从历史提交读到。真撤回必须重写历史 + force push。
- **凭证类（token/key/密码）先撤销再重写**：平台侧撤销 Key 优先级最高——历史重写不解决"已被复制"的问题。确认凭证是否曾入库：`git log --all --oneline -- <路径>`（空结果仅覆盖当前已取回 refs 和路径，不证明从未泄露）并核全历史内容及其他路径/副本。
- **破坏性等级最高**：force push 重写远端 + reset 主工作区。核已有授权覆盖的精确路径、refs、备份和维护窗口；不足时先补范围，授权已成立不重复问。命令清单不构成授权。普通 safe-push 不支持 force，已授权维护按下述独立路径执行，不能用于发表未验功能。

## 1. 前置排查（全部只读，不动任何东西）

```bash
# a. 泄露范围：哪些文件被追踪、全历史哪些提交涉及
git ls-files | grep <关键词>
git log --all --oneline -- <敏感路径>

# b. 凭证是否曾入库（.env 类）
git log --all --oneline -- <env路径>          # 空仅表示当前已取回历史无此路径
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

在执行前冻结全部受影响远端 refs/OID、当前服务端状态及回滚方案；保存原对象与文件、index、dirty/untracked/ignored 的仓外备份，核可恢复。备份可能含敏感内容，私有保存、不公开提交。暂停同一目标的并发写入须已有明确授权；无法取得安全窗口时停。分支以外的 tag/其他 refs 亦须纳入泄露范围，不自动删除未核对象。filter-repo 的 --force 只用于已授权隔离副本，不能搬到共享源。

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
git add -- .gitignore
# 先按身份/隐私合同核实际身份及最终说明
git commit -m "chore(<模块>): 忽略私有运行产物" -m "增加已核范围的防复发规则，记录验证结果。"
```

推送是已授权历史维护例外：核重写后的完整历史、message/patch/blob、正确树构成和泄露移除，核原作者归属、防复发提交的实际身份及最终说明。先完整验证所有候选，再逐 ref 对冻结远端 tip 进行精确 lease；远端漂移、保护不允许或任一步失败时停止，保存已成功/未执行列表，不自动解除保护或重放。

```bash
# 在隔离重写副本中；变量来自具名授权及已核清单
git remote add origin '<已核原远端 URL>'
git push --force-with-lease="refs/heads/${branch}:${expected_remote_tip}" \
  origin "${verified_rewritten_oid}:refs/heads/${branch}"
```

不无条件 --force，不推未列明分支。zsh refspec 中用 `${变量}` 边界，避免 `$b:r` 被解析为变量修饰符。网络异常先读取真实远端 refs，核此次是否已生效，再决定后续；不默认改代理或绕过通道直推。

推送后验证三件套：

```bash
# 1. refs 对齐：对授权清单全部 branch/tag/其他受影响 refs 逐项核远端 OID、预期存在状态及内容；不只核 main
# 2. API 验证：gh api repos/<o>/<r>/contents/<敏感路径>            → 404
#              gh api "repos/<o>/<r>/commits?path=<敏感路径>" --jq 'length' → 0
# 3. 内容后验：全部受影响 refs 检查路径和泄露内容移除；API 分支抽查仅作辅助，不替代完整 ref 清单与内容核验
```

## 4. 残留与边界（必须如实告知用户，不催办不隐瞒）

| 残留 | 性质 | 处置 |
|---|---|---|
| GitHub dangling 提交（旧 SHA 仍可直接访问） | force push 后 GitHub 不立即物理删除 | 彻底清除需联系 GitHub 支持；用户可自行评估接受与否 |
| fork 上的副本 | fork **不跟随**上游重写 | 同上；实例中 fork 副本与泄露内容敏感度相同时一并列出 |
| 其他本地分支/worktree 仍指旧历史 | 重写必然结果 | 保留旧成果，按归属与范围对账；不能盲目 rebase 或重新发表泄露历史 |
| 公开窗口时长 | 数据已暴露的时间 | 由用户评估实际风险，AI 只给事实（起止时间、内容类型、条数） |

## 5. 主工作区对齐（深度分叉剧本）

远端全量重写后，泄露提交**之后**的所有提交 SHA 全变，本地 main 与新远端的共同祖先退到泄露点之前——祖先与逐提交 patch-id 未必能反映真实采用关系；先比较最终内容、来源与授权，不盲目 rebase。

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

全部为 0 只是指定文件当前内容等价，不证明所有本地成果可丢弃。核完整本地提交/范围、后续改动、备份和具体 reset 授权后才选择对齐，不自动 reset 或回放。注意甄别结论与全仓 diff 不矛盾：全仓反向 diff 仍会有"本地比远端旧"的旧侧差异（远端三个月演进的另一面），那是预期噪声。

### 5.3 对齐执行

```bash
# 以下仅限归属明确、已完成全部材料备份且已授权具体 reset 的独占现场
# 1. stash（不带 -u；不能当作 untracked/ignored 的完整备份）
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
| 两侧都有，且一侧是另一侧的演进（版本号更新、内容超集） | 须核两侧真实来源及最新有效状态 | 保留已核有效变化，不默认选本地 |
| 两侧是**不同条目**（任务台账 TASKS 各自新增任务卡、CHANGELOG 各自版本号） | 谁都不能丢 | 两侧全保留拼接 |
| 同一文件的同一功能两侧各写一半（如两个脚本配套改动） | 必须同侧一致 | 同取本地或同取远端，禁止各取一半 |

下表和单侧为空只能定位候选，不能证明删除/新增意图。逐块核两侧当前来源、任务和有效内容，不自动运行正则批量消除冲突；旧示例仅供理解 marker，不作为执行器：

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

reset 可能删除阻挡目标跟踪路径的 untracked 文件，不能承诺本地特有文件不受影响。按备份逐项核字节、权限、index/原 dirty 与 Session 材料；status 显示变化不能代替材料守恒。存在并发或持锁时停，完成后不影响其他树/分支。

## 6. 源头排查要点（泄露怎么进来的）

按成本从低到高：定时任务（`crontab -l`、`launchctl list`、LaunchAgents）→ skill 自身是否有自动提交逻辑（grep scripts/ 里的 git 命令）→ 会话记录（Codex `~/.codex/sessions/`、Claude `~/.claude/projects/`、按敏感文件名 grep）→ 提交元数据（作者/提交者是否 bot 邮箱、提交信息风格、有无 PR 号——**直推 main 无 PR 号 + 凌晨时段**是自动任务的典型指纹）。排查无果时存档线索、不猜结论。

## 7. 实战时间线参考

261003 legal-skills 实例：发现（用户）→ 只读排查（范围/凭证/分支面/fork）→ 隔离 clone + filter-repo 抹 2 文件 → 防复发 .gitignore 进 main 顶部 → force push main + 30 分支（含 zsh refspec 坑返工一次）→ 三件套验证 → 残留告知（fork + dangling，用户按数据敏感度结案）→ 主工作区三层备份 + 数据文件单独备份 → 甄别（5 提交内容全在远端，零 cherry-pick）→ stash/reset/pop + 16 文件 42 处冲突全解 → 零分叉收尾。
