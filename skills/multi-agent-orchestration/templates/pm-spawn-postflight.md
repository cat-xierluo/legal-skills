# PM spawn 后 postflight cheatsheet

> 配套 `SKILL.md` §2、§3.3、§4 与 §7。先识别控制模式，再选择对应核验；不要把 tmux、terminal-managed 和 supervised 的完成信号混用。

## Wave 准备屏障

supervised Wave 必须先完成：

1. 写 manifest，确认 Task 相互独立且 key 唯一。
2. 运行 `orca-wave-prepare.sh --manifest ... --receipt ...`。
3. 核对 receipt 同时含 `run_id`、`coordinator_handle` 和全部 `task_id`。
4. receipt 成功后才并行启动 worker，并同时传 `--orca-run-id`、`--orca-coordinator-handle` 与对应 `--orca-task-id`。

不得并发执行 `run-create/run-use/task-create`。单 worker 可以跳过 manifest，让 helper 自建 Run/Task。

## 通用即时核验

每个 `spawn-worker.sh` 返回后立即核验，不等待业务完成：

```bash
test -f "$WORKTREE/.claude/agent-sessions/$SESSION/METADATA.json"
jq '{worktree,branch,session,runtime}' \
  "$WORKTREE/.claude/agent-sessions/$SESSION/METADATA.json"
git -C "$WORKTREE" status --short --branch
```

确认 cwd/worktree/branch/session、Harness authority、安装门禁、provider lease 与允许文件范围符合任务卡。核验失败就停止派发，不由 PM 静默接管业务实现。

## Orca supervised

即时核验真实 Dispatch，而不是 tmux session：

```bash
bash scripts/pm-orchestrate.sh show --worktree "$WORKTREE" --session "$SESSION"
bash scripts/pm-orchestrate.sh read --worktree "$WORKTREE" --session "$SESSION" --lines 80
```

必须看到 METADATA 的 `run_id/coordinator_handle/task_id/dispatch_id` 与 `worker-show` 对应。后续用 bounded wait：

```bash
bash scripts/pm-orchestrate.sh wait --worktree "$WORKTREE" --session "$SESSION" --timeout 900
```

- `worker_done → Delivery` 才是 lifecycle 完成；STATUS、commit、tests、heartbeat、idle 都不是。
- Delivery 要逐条处理，settled worker 选择 reuse/release/retain，最后才 ack。
- `worker-show/dispatch-show` 与 diff/tests 可以用于业务验收，但不能替代 lifecycle settlement。
- worker 仍存活但漏发 `worker_done`：用结构化 `send` 提醒它执行 live preamble 中的精确命令。
- worker 已死：满足严格 liveness gate 后才用 `pm-orchestrate settle --reason ...`；stop 失败不得 destroy。

不要给 supervised terminal 再发完整 task prompt，也不要用 Sentinel/pm-monitor 判完成。

## Orca terminal-managed

没有 `supervised.dispatch_id` 时只使用 terminal 控制面：

```bash
bash scripts/pm-orchestrate.sh read --worktree "$WORKTREE" --session "$SESSION" --lines 5000 --cursor 0
bash scripts/pm-orchestrate.sh wait --worktree "$WORKTREE" --session "$SESSION" --timeout 30
```

保存 `nextCursor` 后增量读取。`tui-idle` 仅表示当前可交互，不证明业务完成；最终以 STATUS/RESULT、真实 diff/tests/artifacts 和 PM 验收为准。terminal-managed 没有 `worker_done` 义务。

## tmux 回退

只有 METADATA 不含 Orca terminal/Dispatch 时才核验 tmux：

```bash
tmux has-session -t "$SESSION" 2>/dev/null
tmux display-message -p -t "$SESSION" '#{pane_current_path}'
tmux capture-pane -t "$SESSION" -p | tail -20
```

STATUS/RESULT 用于 checkpoint；Sentinel/pm-monitor 可作事件与低频观察器，但仍需真实产物验收。不要 attach，不要无界轮询，不要让 PM 因等待 STATUS 阻塞下一次派发。

## 并发纪律

Wave receipt 是准备屏障；屏障之后，文件域正交的 worker 启动与 postflight 可并行。共享 schema、锁文件、迁移或同一任务源的写入必须按依赖顺序执行。spawn 返回后立即回到 PM 主循环，使用 bounded wait/事件巡检，不做 `while ... sleep` 无界等待。
