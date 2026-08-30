# PM 统一控制入口

> `scripts/pm-orchestrate.sh`；本页适配 `multi-agent-orchestration` v2.10.1。

## 目录

1. 模式解析
2. 命令
3. Supervised 收口顺序
4. PR 先行与本地集成
5. 安全边界

## 1. 模式解析

脚本读取 `<worktree>/.claude/agent-sessions/<session>/METADATA.json`：

| METADATA | 模式 | 控制面 |
|---|---|---|
| 有 `supervised.dispatch_id` | `orca_supervised` | Dispatch/Delivery/worker-read |
| 仅有 `terminal_handle` | `orca_terminal` | terminal send/read/wait |
| 两者都无 | `tmux` | send-keys/capture-pane |

不要手工覆盖模式；缺 METADATA 时 fail-loud。

### 1.1 手动 register 的路由恢复（Task-092）

`orca-supervised-register.sh` 在 `worker-start` 和 Dispatch 绑定完成后，会从精确 `worktree id/path + terminal handle` 反查唯一 Session Context，并原子补写完整的 `.session.orca.supervised` 合同。成功输出：

```text
ORCAREG_METADATA_BIND=ok
```

如果 worktree 查询失败、Session Context 缺失/不唯一、terminal handle 不匹配、目标是符号链接或写入失败，脚本输出 `ORCAREG_METADATA_BIND=manual-required`，但不重启已经活跃的 worker。此时 PM：

1. 用 `orca worktree show --worktree id:<worktree_id> --json` 核对返回的 id/path 与 register 回执完全一致；
2. 在该精确 path 下查找唯一 `.claude/agent-sessions/*/METADATA.json`，并核对 `.session.orca.terminal_handle`；
3. 仅在身份唯一时，按 register 的 `ORCAREG_RUN_ID/TASK_ID/DISPATCH_ID/COORDINATOR_HANDLE/DISPATCH_BIND` 补写与正常 spawn 相同的 supervised 合同；
4. 立即用 `pm-orchestrate show` 复验路由。身份仍不唯一时保留现场并升级人工处理，不猜 session、不重试 spawn。

在 metadata 尚未恢复时，只能把 `orca terminal show --terminal <handle> --json` 的 `preview` 与 `lastOutputAt` 作为临时活性证据；它们不能证明业务完成，也不能替代 Dispatch/Delivery 生命周期。

## 2. 命令

```bash
# 每个 Wave 一次；输出 .result.run.id
pm-orchestrate.sh run-create --objective "Wave objective"

# 三种模式通用
pm-orchestrate.sh send --worktree "$WT" --session "$S" --text "..."
pm-orchestrate.sh read --worktree "$WT" --session "$S" --lines 50
pm-orchestrate.sh read --worktree "$WT" --session "$S" --lines 5000 --cursor 0
pm-orchestrate.sh peek --worktree "$WT" --session "$S"
pm-orchestrate.sh wait --worktree "$WT" --session "$S" --timeout 900

# supervised 专用
pm-orchestrate.sh show --worktree "$WT" --session "$S"
pm-orchestrate.sh reply --worktree "$WT" --session "$S" --message-id "$MID" --text "..."
pm-orchestrate.sh release --worktree "$WT" --session "$S"
pm-orchestrate.sh retain --worktree "$WT" --session "$S"
pm-orchestrate.sh ack --worktree "$WT" --session "$S" --delivery-id "$DID"
pm-orchestrate.sh settle --worktree "$WT" --session "$S" --reason "..." [--force] [--destroy]
pm-orchestrate.sh reauthorize --worktree "$WT" --session "$S" \
  --allow-cmd "make test" --resume-text "断点续接说明" [--task-id ID]
```

supervised `send` 是结构化 inbox mail，不是 terminal prompt injection；`read` 输出 Orca JSON 并保留 `source/cursor/fallbackReason`，便于 PM 判断读到的是精确 transcript 还是 terminal fallback。除只读 `read/show` 外，supervised 命令先对当前 PM terminal 执行 `run-use --id`，刷新 METADATA 的 coordinator handle；`wait/ack` 随后消费当前绑定 Run，不传陈旧 `--run`。

Orca terminal-managed `read` 同样透传 `--cursor`。alternate-screen TUI 首次从 `0` 读取并保存响应里的 `nextCursor`；后续按 cursor 增量读取，避免默认 tail 只剩 spinner。`wait` 的 `tui-idle` 只表示当前可交互/空闲，不是业务终态。

terminal/tmux 的超长 prompt（>500 字或含反引号、`$`、`|`）会写入 session context 的 `WORKER_PROMPT.md`，再投短 Read 指令。supervised guidance 直接写消息 body，不创建新的 prompt 文件。

`reauthorize`（Task-058）用于 worker 被 `SHELL_COMMAND_NOT_ALLOWLISTED` 拦验证且根因是 spawn 授权快照缺命令时：guard 读 `launch.sh` 内联的 `WORKER_INSTALL_AUTH_B64`（进程环境，运行中改授权文件无效），本命令合并 `--allow-cmd` 进授权文件后重写 B64（回验解码一致）、把被提问/中止翻成 failed 的 Task 复位 ready、在同一 worktree 创建新终端并复用 Task 重注册（worker-start 重注入完整任务）、改写 METADATA 的 terminal_handle/dispatch_id、可选发送 `--resume-text`、最后关闭旧终端句柄。未提交的工作区改动全部保留；provider lease 的 transport 记账留给 release/clean-worktree 阶段。

## 3. Supervised 收口顺序

1. `wait` 获取完整 Delivery；不要立即 ack。
2. 处理每条 `question/escalation/worker_done`。
3. 用 `show` 核对 accepted settlement，用 `read` 和真实 diff/tests 验收。只读状态与业务验收不能替代生命周期 settlement。
4. 每个 settled worker 选择立即复用、`release` 或用户明确要求时 `retain`。
5. 全部处理完后 `ack --delivery-id ...`。
6. 继续 `wait`，直到所有预期 Dispatch settle。

`wait` timeout 是 checkpoint，不是 failure；不要因此 stop/release worker。

## 4. PR 先行与本地集成

Orca worktree/terminal 是高频执行面；PR 是 PM 收口时的审阅边界。默认顺序是：

```text
worker 分支提交
  → safe-push
  → 创建或接管唯一匹配 PR
  → 冻结 PR base/head SHA、diff、checks 与 review
  → 在最新 origin/main 上建立本地集成候选
  → 复跑最终门禁
  → 按仓库规则本地推入 main，或交给 GitHub PR merge
  → 核对远端结果后再清理
```

这只是默认顺序，不是外部写入授权。没有用户或项目授权时，PM 停在只读 PR 审计与本地候选验证，不 push main、不 merge、不 close PR。

### 4.1 先查已有 PR，避免双开

worker 可能已经自行 push/开 PR。PM 在 `gh pr create` 前先按精确 head 分支列出 open PR，并核对 `baseRefName`、`headRefName`、`headRefOid`、任务范围和 Agent 归属：

```bash
gh pr list --state open --head "$BRANCH" \
  --json number,url,baseRefName,headRefName,headRefOid,title
```

- 恰有一个 PR 且 head SHA 等于本轮冻结的 worker tip：接管该 PR 做验收，不再创建。
- 没有匹配 PR：完成 safe-push 后创建一个显式 `--head "$BRANCH"` 的 PR。
- 多个候选、同分支但 SHA 不同、或不同分支出现疑似同内容 PR：失败关闭，逐个比较 diff 后由 PM 选择；不得猜测、不得再开一个 PR。
- 接管 worker 自建 PR 不降低门禁：仍检查完整 diff、identity、checks、review、敏感文件和声明范围。

Task-097 将把上述检查机械化为 `pr-audit` 与 `pm-closeout` 的 create 前门禁；完成前按本节手工执行，不能声称已有自动去重。

> **当前脚本能力告警**：`pm-closeout.sh` 目前是一体化的 `safe-push → gh pr create → gh pr merge`，没有“创建 PR 后暂停并转本地集成”的开关。选择 `LOCAL_INTEGRATE` 时不得运行这条旧的一体化路径；先按本节手工分段，等 Task-097 为脚本补齐显式三态后再恢复自动收口。

### 4.2 本地集成的三种结果

| 结果 | 适用条件 | 行为 |
|---|---|---|
| `LOCAL_INTEGRATE` | 用户/项目允许 PM 更新 main，main 无保护阻断，存在干净且身份唯一的 main worktree | 从最新 `origin/main` 建本地候选，导入冻结的 PR head，复跑门禁，生成带 `(#PR)` 的本地集成提交，再按 `git-workflow` 安全推送 main |
| `REMOTE_PR_MERGE` | main 有 branch protection、required review/checks，或项目明确以 GitHub 为合并权威 | 本地候选只做验证；确认 PR head 未漂移后用 GitHub squash/merge，并复核 `state/mergedAt/mergeCommit` |
| `VALIDATE_ONLY` | main worktree dirty/身份不明、PR 不唯一、checks/review 未决、授权不足或范围不清 | 只报告证据与阻塞，不修改 main、不关闭 PR |

本地集成必须基于再次 fetch 后的最新 `origin/main`，并绑定已经审阅的精确 PR head SHA；任一 SHA、diff 或 checks 在验证期间变化，都回到 PR 审计，不沿用旧结论。

Monorepo 禁止直接 `git merge <feature>`。只导入任务声明范围：单 Skill 优先按目录级 checkout；仓库已明确允许 squash 时，仍须先确认 PR 已基于最新 main、diff 仅含声明目录且无意外删除。具体命令、身份门禁和提交格式以 `git-workflow` 为准。

### 4.3 远端结果与清理

- 本地集成提交成功推入 main 后，原 PR 若未被 GitHub 自动标为 merged，使用包含 main commit SHA 的说明关闭；不得把 `CLOSED` 伪报成 GitHub `MERGED`。
- GitHub 合并路径以 `state == MERGED`、非空 `mergedAt` 和 `mergeCommit.oid` 为成功证据。
- 只有远端结果已确认且 worker/worktree 无未提交改动，才进入 release、分支和 worktree 清理。自动清理仍属于 Task-103，当前不得假装已实现。

## 5. 安全边界

- 脚本不自动 ack Delivery、不自动 release active worker、不删除 worktree（`settle` 例外兜底，但需 `--destroy` 显式升级）。worker 仍活着却漏发 `worker_done` 时先发结构化提醒；确认已死才 settle。
- `release/retain/reply/ack/settle` 仅对有 supervised metadata 的 worker 生效。`settle` 需 `--reason` 并先持久审计，默认以 `worker-stop` 原子 fence+stop 后不动文件；stop 失败时 `worker-abandon` 只作 fence 兜底且禁止 destroy。`--destroy` 仅在 stop 成功后释放 lease并删除精确 Orca/Git worktree。
- `--force` 只覆盖 liveness gate；不会绕过仓库身份、审计落盘、worker-stop、lease 或 worktree 删除失败。
- stale terminal handle 要先按 worktree 重新解析；禁止同时给旧/新 handle 双发。
- 普通 terminal worker 没有 `worker_done` 义务；不要用 terminal 文本伪造 Dispatch 完成。
- 对 external supervised terminal，`release` 后 retained 不必然是错误；文件清理仍须由 `clean-worktree.sh` 验证 settled 状态、external ownership、retained reason 和精确句柄后处理。
