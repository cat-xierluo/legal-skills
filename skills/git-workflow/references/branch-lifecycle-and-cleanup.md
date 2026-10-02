# 分支生命周期与清理

> 在单 Worker 验收收口、长期功能线关闭，或批量审计 stale 分支时读取。删除动作必须先完成对应证据与授权门禁。

## 1. 先判定生命周期

`integration_target` 是接收子 PR 的默认主干或长期功能基线；`head` 是本次交付的源分支。两者必须分开建模。

| 生命周期 | 典型用途 | 单任务收口 |
|---|---|---|
| `ephemeral-worker` | 一个可独立验收的 Worker 任务 | 交付和身份均已证明后，默认清理 head、临时 Worktree 与本地 ref |
| `long-lived` | 跨多个 Worker/PR/波次的功能或集成基线 | 保留远端 ref、本地 ref 与固定 Worktree |

普通 Worker 默认为 `ephemeral-worker`。只有项目任务合同明确指定集成者、固定 Worktree、里程碑和退出条件时，才把源分支标记为 `long-lived`。分支“已经合并”不是生命周期证据；调用方不得把持久 metadata 中的 `long-lived` 降级。

短 Worker 合入长期分支时，只清理 Worker head，绝不清理 integration target。长期分支是否最终删除属于功能线关闭决策，需要独立授权，不能由某个子任务验收推导。

## 2. 单 Worker 验收后的自动清理

PM 不等待批量审计，在交付成功的同一收口流程中处理一次性资源。授权只覆盖绑定到同一 canonical repo、PR、head branch、40 位 immutable tip、worktree、Session 与 delivery commit 的精确对象。

执行顺序：

1. 证明交付：远端合并要求 PR `state == MERGED`、`mergedAt` 非空、`mergeCommit.oid` 精确匹配；本地集成要求 delivery commit 已进入最新远端 integration target。
2. PR `headRefName`/OID 必须仍等于冻结值，`baseRefName` 必须等于声明的 `integration_target`。
3. 查询并核对远端 head tip；查询失败不能当作分支不存在。本地集成后 PR 仍 open 时保留远端 head，避免破坏活 PR。
4. 核对 Worktree 干净、worker lifecycle 已 settlement，再移除精确 Worktree。dirty、active、unknown、release pending 或身份漂移一律保留。
5. 确认没有 Worktree 检出该分支后删除本地 ref。普通 merge 可先用 `git branch -d`；squash/rebase 造成 `-d` 拒绝时，只能在上述证据齐全后执行 expected-tip 绑定的原子删除：

```bash
git update-ref -d refs/heads/<branch> <expected-tip>
```

不得升级为无条件 `git branch -D`。tip 漂移时删除失败，保留现场。

`multi-agent-orchestration` 的 `pm-closeout.sh` / `pm-cleanup-worker.sh` 实现该协议。结果必须归一为：

- `CLEANED`：本次一次性资源均已安全清理。
- `RETAINED_WITH_REASON`：按生命周期或具名理由保留。
- `CLEANUP_PENDING`：交付已确认，但资源清理仍有独立债务。

交付确认后的清理失败不得触发 merge/push 重放。只有 `CLEANED` 或有明确理由的 `RETAINED_WITH_REASON` 才能声称资源闭环。

## 3. 批量审计 stale 分支

批量清理不是单 Worker 自动清理的延伸，必须先展示候选并取得用户确认。不要只用 `git branch --merged main`：

- squash/rebase merge 会让原 tip 不可达 main，形成“已合并但显示未合并”的漏判。
- 刚创建、尚未 commit 的活跃分支仍停在 main，会形成“活跃但显示已合并”的误判。

权威组合是 PR 状态、最后提交时间、Worktree/未提交状态和分支身份；ahead/behind 只作辅助指纹。

### 3.1 快照与候选

```bash
git branch -vv
git branch -r
git worktree list

git for-each-ref --sort=committerdate refs/remotes/origin/ \
  --format='%(committerdate:short) %(refname:short)'

gh pr list --state all --limit 100 \
  --json number,state,headRefName,baseRefName,mergedAt,closedAt
```

默认最后提交不足 24 小时的分支一律视为活跃并保留；项目可以把阈值调大。对每个候选检查对应 Worktree：

```bash
git -C <worktree> status --short
```

日常巡检可先跑只读盘点脚本生成三档候选表（脚本绝不删除；gh 缺失或未认证时自动降级为 merge-base+日期判定并标注「PR 状态未核对」，squash 分支会漏判为 NEEDS_CONFIRM——宁漏勿错）：

```bash
scripts/branch-audit.sh [base-ref] [remote]   # 默认 origin/main origin
```

对单个分支精查其 PR 命运（squash 判死的核心实操）：

```bash
gh pr list --state merged --head <branch> --json number,mergedAt   # 有 MERGED 记录 = 内容已进 base
gh pr list --state open   --head <branch>                          # open = 活 PR，保留
```

### 3.2 判定

| 信号 | 处理 |
|---|---|
| PR 为 `MERGED`，身份一致，超过活跃阈值，无 dirty Worktree | 可列为删除候选 |
| PR 为 `CLOSED` 且非 `MERGED` | 询问用户；废弃不等于允许删除 |
| 无远端 PR、仅本地存在或有未推送 commit | 询问用户；可能是 WIP |
| metadata 为 `long-lived` 或分支是 integration target | 排除，不进入常规 stale 清理 |
| 远端已无该 ref，只剩 remote-tracking ref | `git fetch --prune` 清理本地引用 |
| 最后提交不足阈值，或 Worktree dirty/状态未知 | 保留 |

候选表至少展示分支、本地/远端存在性、PR、最后提交时间、Worktree/dirty 状态、生命周期和判定。取得用户确认后才执行远端批量删除：

```bash
git push origin --delete <b1> <b2> <b3>
git branch -d <local-branch>
git fetch --prune
```

### 3.3 批量删除的执行细节与已验证的坑

候选表生成、用户确认、执行删除三者之间，仓库可能被并行会话持续改动（实战：盘点时 7 个 open PR，执行时已多出 4 个新分支、1 个 PR 刚被合并）：

- **执行前重跑 open PR 防护**：删除前重新 `gh pr list --state open` 拉 head 名单与待删名单求交，命中即从名单剔除。
- **squash 判死不受 merge-base 迷惑**：PR `MERGED` 即内容已进 base，merge-base 显示「未合并」是 squash 的预期，不是风险信号；但判定必须来自 PR 状态而非分支名或日期。
- **本地复用保护**：远端分支若存在本地同名分支且 ahead（有未推送提交），从删除名单剔除——该分支可能已被新工作复用（实战：某分支 PR 合并后被主工作区改作新任务的开发线，含 7 个未推送提交）。
- **批量删除遇缺 ref 会整批失败**：`git push origin --delete b1 b2 ...` 中任一 ref 已不存在（如 GitHub 侧已自动删除）会导致整批报错。先 `git fetch --prune`，再对「仍存在」的名单重推补删。
- **代理环境**：全局 `http.proxy` 可能致 push 失败或挂起，用 `git -c http.proxy= -c https.proxy= push ...` 显式绕过。
- **只删远端 ref 不影响本地**：远端删除不动本地分支与 Worktree 检出；本地分支删除前对每条重跑 `git merge-base --is-ancestor` 校验，通过才 `-D`。

### 3.4 patch-id 判死与 worktree 批量清理（261002 实战）

多 Agent 派发（PM→worker、Orca/Codex 并行会话）会沉淀大量一次性 worktree 与分支，其共同形态是「commit 对 base 不可达、但补丁内容已在 base」——squash 合并或 cherry-pick 后 merge-base 全部落空。判死与清理的手法：

#### patch-id 判死（git cherry）

```bash
git rev-list --count origin/main..<branch>                    # ahead N（squash 后虚高）
git cherry origin/main <branch> | grep -c '^+'                # 补丁不在 base 的条数
# ahead>0 但 cherry '+' 计数为 0 → 补丁等价已全部在 base，分支纯死
```

- 优先级：**MERGED PR 记录 > patch-id > merge-base**。多 commit 被 squash 成单个时 patch-id 不匹配（归 NEEDS_CONFIRM，宁漏勿错）；PR 已 MERGED 则直接判死，不受任何 git 指标迷惑。
- 每分支 PR 命运精查：`gh pr list --state all --head <branch> --json number,state --limit 1`。CLOSED 且非 MERGED 的分支**内容未进 base**，删除即丢失——先看评论确认是否被后续 PR 取代（见下）。

#### worktree 批量清理五步（先展示后执行）

1. **prune 悬空记录**：`git worktree prune` 先清掉目录已不存在的挂载（worktree list 仍显示但 remove 报 "not a working tree" 的都是这类）。
2. **查进程占用（硬保护）**：`lsof -w -d cwd -F n | sed -n 's/^n//p'` 拿全量 cwd 路径，与 worktree 路径前缀匹配。有占用的（活跃 PM/agent 会话）**绝不删**——lsof 列宽截断用 `-F n` 全路径输出规避，路径匹配用 awk `index($0,p)==1`（防空格/正则元字符）。日常巡检直接跑 `scripts/worktree-audit.sh`（只读，含占用/dirty/patch/PR 四维分类）。
3. **dirty 分类**：`git -C <wt> status --porcelain`——modified/untracked 是**会话工作现场**：已终结会话的实验残留可 `--force` 删（正式交付已在 main），但 untracked 可能是无备份的研究材料（实战：R15 研究脚本只存在于 worktree 未提交区）——删除前确认正式版已入库，必要时拷出归档。
4. **按分支死活定删除范围**：补丁全在 base/PR 已合并 → worktree+本地分支一起删；分支是 open PR head 或有补丁未交付 → **只删 worktree 保分支**（内容在分支/远端，返修时重新 checkout）。
5. **执行**：`git worktree remove [--force] <wt>` → `git branch -D <branch>`（patch0/PR merged 已验证）→ 远端 `git -c http.proxy= push origin --delete <b>` 逐个删（勿批量，见 §3.3）。

#### 已验证的坑

- **orca 工作区目录 Permission denied**：worktree remove 删目录失败但分支照删，空壳目录留给用户手动 `sudo rm`，勿反复重试。
- **detached HEAD worktree**：先确认不是其他工具自管目录（eval-harness sources 等）再处置。
- **/tmp 下的 worktree**：系统清理可能已删目录，prune 后再处理。
- **删除与盘点间仓库在变**：并行会话持续新开分支/推 PR，执行前重跑 open PR 名单求交（§3.3 同款防护）。

#### PR 取代关系（窄采用入口模式）

研究/返修型工作常见结构：旧 PR（研究基线，head 停在旧 main）→ 新 PR（「固定已验候选窄采用入口」，基于最新 main 只导入已验部分，body 注明「不自动关闭旧 PR」）。判定：新 PR 的 body 明确声明覆盖旧 PR 的研究树、且带独立审计指纹/PM 签收时，**合并新 PR 后关闭旧 PR**是安全动作；「不自动关闭」是流程礼貌而非保留理由。反向坑：旧 PR 被 main 甩出冲突（CONFLICTING）不等于过时——先读 body 看它是否在等用户创意决策（实战：#273 等样张择优）。

#### 无 PR、有补丁分支的分组处置

批量审计必然产出一批「有提交、没开 PR」的分支（PM 线的中间产物、当日未交付工作）。处置：**当日的保留**（可能还在写）；隔日的按体量与日期列成清单交给用户三选一——让对应 PM 线验收开 PR / 确认过时后删 / 指定归档。不要替用户处置这类分支（红线 §5）。

## 4. 长期功能线关闭

长期分支即使里程碑已合入默认主干也继续保留，直到同时满足：

- 功能线已明确完成或取消；
- open 子 PR、未推送 commit、dirty Worktree 与其他未决工作均已处置；
- 最终状态已写回项目任务源；
- 用户或项目规则对精确分支与 Worktree 给出删除授权。

关闭时仍执行 PR 状态、最后提交时间、Worktree dirty 与 exact tip 检查。删除的是明确关闭的功能线资源，不借机扩大到其他 stale 分支。

## 5. 红线

- 仅凭 `--merged`、ahead/behind、分支名或“已经合并”删除。
- 把 `CLOSED` 当 `MERGED`，或查询失败当“远端不存在”。
- 删除有进程 cwd 占用（lsof 检出或占用未知）的 worktree。
- 删除 untracked 材料无入库备份、且未向用户确认放弃的 dirty worktree。
- 替用户处置「无 PR、有补丁」的未交付分支（列清单交用户三选一：验收开 PR / 过时删 / 归档）。
- 跳过用户确认执行批量远端删除。
- 删除最后提交不足活跃阈值、dirty、active、unknown 或 `long-lived` 的分支/Worktree。
- 使用 `git worktree remove --force`、无条件 `git branch -D` 或未绑定 expected tip 的 ref 删除绕过证据。
- 清理一次性 Worker 时触碰 integration target，或把清理失败隐藏成完全闭环。
