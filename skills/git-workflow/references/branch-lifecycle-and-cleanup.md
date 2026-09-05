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
- 跳过用户确认执行批量远端删除。
- 删除最后提交不足活跃阈值、dirty、active、unknown 或 `long-lived` 的分支/Worktree。
- 使用 `git worktree remove --force`、无条件 `git branch -D` 或未绑定 expected tip 的 ref 删除绕过证据。
- 清理一次性 Worker 时触碰 integration target，或把清理失败隐藏成完全闭环。
