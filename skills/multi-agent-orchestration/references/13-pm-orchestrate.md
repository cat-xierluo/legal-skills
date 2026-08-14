# PM 统一控制入口

> `scripts/pm-orchestrate.sh`，版本 v2.3.0。

## 目录

1. 模式解析
2. 命令
3. Supervised 收口顺序
4. 安全边界

## 1. 模式解析

脚本读取 `<worktree>/.claude/agent-sessions/<session>/METADATA.json`：

| METADATA | 模式 | 控制面 |
|---|---|---|
| 有 `supervised.dispatch_id` | `orca_supervised` | Dispatch/Delivery/worker-read |
| 仅有 `terminal_handle` | `orca_terminal` | terminal send/read/wait |
| 两者都无 | `tmux` | send-keys/capture-pane |

不要手工覆盖模式；缺 METADATA 时 fail-loud。

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
```

supervised `send` 是结构化 inbox mail，不是 terminal prompt injection；`read` 输出 Orca JSON 并保留 `source/cursor/fallbackReason`，便于 PM 判断读到的是精确 transcript 还是 terminal fallback。

Orca terminal-managed `read` 同样透传 `--cursor`。alternate-screen TUI 首次从 `0` 读取并保存响应里的 `nextCursor`；后续按 cursor 增量读取，避免默认 tail 只剩 spinner。`wait` 的 `tui-idle` 只表示当前可交互/空闲，不是业务终态。

terminal/tmux 的超长 prompt（>500 字或含反引号、`$`、`|`）会写入 session context 的 `WORKER_PROMPT.md`，再投短 Read 指令。supervised guidance 直接写消息 body，不创建新的 prompt 文件。

## 3. Supervised 收口顺序

1. `wait` 获取完整 Delivery；不要立即 ack。
2. 处理每条 `question/escalation/worker_done`。
3. 用 `show` 核对 accepted settlement，用 `read` 和真实 diff/tests 验收。
4. 每个 settled worker 选择立即复用、`release` 或用户明确要求时 `retain`。
5. 全部处理完后 `ack --delivery-id ...`。
6. 继续 `wait`，直到所有预期 Dispatch settle。

`wait` timeout 是 checkpoint，不是 failure；不要因此 stop/release worker。

## 4. 安全边界

- 脚本不自动 ack Delivery、不自动 release active worker、不删除 worktree（`settle` 例外兜底，但需 `--destroy` 显式升级）。
- `release/retain/reply/ack/settle` 仅对有 supervised metadata 的 worker 生效。`settle` 需 `--reason`（审计），默认 fence+stop 不动文件；`--destroy` 才动 worktree/files（一站式清理，不再跑 clean-worktree）。
- stale terminal handle 要先按 worktree 重新解析；禁止同时给旧/新 handle 双发。
- 普通 terminal worker 没有 `worker_done` 义务；不要用 terminal 文本伪造 Dispatch 完成。
- 对 external supervised terminal，`release` 后 retained 不必然是错误；文件清理仍须由 `clean-worktree.sh` 验证 settled 状态、external ownership、retained reason 和精确句柄后处理。
