# PM spawn 后 postflight cheatsheet

> 配套 `SKILL.md §3.8` / §6 / §7.1。**spawn 是 fire-and-forget；不要 block 等 worker 跑完。**

## 何时用

每 spawn 一个 worker 完，**立刻**跑下面 4 条（30 秒内）。Wave 内 N 个 worker 跑 N 轮。

spawn-worker.sh 退出立刻返回这个清单，不要等 `STATUS.json`、不要 attach tmux、不要用 `TaskOutput block=true`。

## 4 条核验命令（必须按顺序）

> 把下面命令里 `$SESSION` / `$WORKTREE` 替换成实际值（spawn-worker.sh 输出 `SPAWN_WORKER_SESSION` / `SPAWN_WORKER_WORKTREE`）。

### 1. tmux session 是否真存活（< 1s）

```bash
tmux has-session -t "$SESSION" 2>/dev/null && echo "OK: $SESSION" || echo "MISSING: $SESSION"
```

如果 MISSING → 重跑 `spawn-worker.sh` 或检查 pane 创建日志（`SPAWN_WORKER_RUN: ...` 行）。

### 2. pane cwd / prompt 是否已就位（< 1s）

```bash
tmux capture-pane -t "$SESSION" -p | tail -5
```

看最后 5 行：

- 看到 worker 初始化 banner / `Welcome` / 提示符 → 就位，可以投 prompt
- 仍是空白 pane → 等 5 秒再 capture 一次；**不要 attach**
- 看到 trust / permission dialog → 看 §3.5 / §3.8.4，本 cheatsheet 不处理 dialog 路径

### 3. Session Context METADATA.json 是否已落盘（< 1s）

```bash
ls -la "$WORKTREE/.claude/agent-sessions/$SESSION/METADATA.json"
```

确认 base / runtime / verification / `isolation_mode` 字段都齐。如果文件不存在或字段缺失 → spawn-worker.sh 内部 metadata 写入流程失败，重跑或查日志。

### 4. STATUS.json 是否在 1-2 分钟内出现（异步等，不阻塞 PM）

```bash
timeout 120 bash -c '
  until [ -f "$WORKTREE/.claude/agent-sessions/$SESSION/STATUS.json" ]; do
    sleep 5
  done
  echo "STATUS_READY: $SESSION"
'
```

120s 还没出现 → 触发 `SKILL.md §2.1` 纠偏：发 checkpoint-only 纠偏（`tmux send-keys` 推 bootstrap correction），或重启 worker。

**绝对不要**把 PM 自己 hang 在这个 timeout 上等所有 worker。

## 跑完 4 条后

PM **立刻**返回主循环，做下一件事（下一个 worker spawn / 已有 worker review / 用户消息）。

后续 worker 终态由 `sentinel.sh`（`SKILL.md §7.2`）事件驱动唤醒，或 `pm-monitor.sh --log-file`（`§7.1`）后台巡检。**不要 PM 自己 poll 等**。

## 反例（踩坑历史 · 2026-07-10 某多 worker Wave 实战）

| 反模式 | 实测后果 |
|--------|---------|
| `TaskOutput block=true` 等 `spawn-worker.sh` 退出 | PM 主回合 hang，单次白等 ~90s × N worker，并行价值归零 |
| `tmux attach -t "$SESSION"` 跟 worker 一起看 | 占 PM 主会话、无纠偏能力 |
| `while ! [ -f STATUS.json ]; do sleep 1; done` 不带 timeout | PM 可能永久挂 |
| spawn 完 6 worker 立刻 poll 等全部 done | Wave 串行化，与 §3.1 设计目的冲突 |
| `spawn-worker.sh` 内部 fork sentinel / pm-monitor | auto mode 拒多 background（CHANGELOG v1.18.1） |
| 等 W1 STATUS.json 才派 W2 | 等于把 Wave 串行化，多花一轮 |

## 多 worker 并行 spawn 提示（与 §3.8.2 配套）

文件域独立时（`SKILL.md §3.1` 上行 218），从一开始就别串行 spawn：

```bash
for w in w1 w2 w3 w4 w5 w6; do
  bash scripts/spawn-worker.sh --project "$PROJ" --branch "vN/$w" --session "$w" \
    --worker-backend claude-code --with-sentinel --command "$W_CMD_$w"
  bash scripts/sentinel.sh --status-file "$WORKTREE/.claude/agent-sessions/$w/STATUS.json" \
    --tmux-session "$w" --poll-interval 5 --max-wait 7200  # run_in_background=true
done
# ↑ 6 个 spawn 完，下面跑 6 轮 4 条核验 → 立即投 prompt + 切回主循环
```

详细 cheatsheet + 决策树见 `SKILL.md §3.8`。
