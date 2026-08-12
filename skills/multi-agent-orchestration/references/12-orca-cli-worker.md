# 12. ORCA CLI Worker Backend

> Level 2 reference。配合 SKILL.md §6.5「ORCA 终端模式」阅读。
> 版本：v1.21.0（DEC-114，2026-08-12）。

## 1. 边界

**适用**：PM 在 ORCA 桌面端的内嵌终端里调用 `spawn-worker.sh`，希望 ORCA UI 直接反映 worker 生命周期（spawn 立即出卡、终态自动切 workspace-status、stale 时 in-review 提示）。

**不适用**：
- 非 ORCA 终端（iTerm2 / Terminal.app / VS Code terminal / Codex App / 其它）—— `TERM_PROGRAM != Orca`，自动回落 tmux 路径。
- 跨 repo 调用 —— `ORCA_WORKTREE_ID` 的 path 段与 `PROJECT_DIR` 的 git toplevel 不一致，自动回落 tmux（防误触发）。
- `--no-worktree` 轻量模式 —— ORCA worktree 必须有 git 仓，与轻量模式互斥（打印 `SPAWN_WORKER_ORCA_LIGHTWEIGHT_FORCES_TMUX` 后回落 tmux）。
- ORCA 桌面端未运行 / `orca` CLI 不在 PATH —— fail-loud，`exit 64`（建议跑 `orca open` 或传 `--no-orca-mode`）。

## 2. 检测协议

`spawn-worker.sh` 的 `detect_orca_mode()` 函数按优先级短路判定，输出 4 选 1：

| 模式 | 触发条件 | 行为 |
|------|----------|------|
| `auto` | `TERM_PROGRAM=Orca` + `ORCA_WORKTREE_ID` 非空 + path 段 = `PROJECT_DIR` git toplevel + `orca status --json` 成功 + capability 含 `terminal.multiplex.v1` | 走 ORCA worktree + terminal 路径 |
| `force_tmux` | `--no-orca-mode` 显式 opt-out / 非 ORCA 终端 / 跨 repo path 不匹配 | 走原 tmux + git worktree 路径，零 ORCA 调用 |
| `lightweight_forces_tmux` | `--no-worktree` 启用（无论是否在 ORCA 内） | 走轻量模式 tmux 路径，打印 `SPAWN_WORKER_ORCA_LIGHTWEIGHT_FORCES_TMUX` |
| `missing_orca` | `TERM_PROGRAM=Orca` 但 `orca` 不在 PATH，或 `orca status` 失败 / 缺 capability | `exit 64` fail-loud |

`ORCA_WORKTREE_ID` 形如 `<repoId>::<worktreePath>`，由 ORCA 桌面端在启动内嵌终端时注入。`detect_orca_mode` 取 `::` 后半段与 `git -C "$PROJECT_DIR" rev-parse --show-toplevel` 比对，匹配才进 `auto`，避免在 ORCA 终端里跑其它 repo 时误触发。

## 3. ORCA API 速查

`auto` 模式下 spawn-worker.sh 实际调用的 ORCA 命令链（完整文档见 `orca skills get orca-cli`）：

```bash
# 1. 建独立 ORCA worktree（spawn-worker.sh 的 orca_worktree_create helper）
orca worktree create \
  --name "tmux-$SESSION" \
  --no-parent \
  --base-branch "$BASE_REF" \
  --json
# → 响应 .result.worktreeId = "<repoId>::<worktreePath>"

# 2. 在新 worktree 开一个 terminal，跑 worker COMMAND（含 provider env / wrapper / launch.sh）
#    spawn-worker.sh 的 orca_terminal_create_and_send helper
orca terminal create \
  --worktree "id:$ORCA_WORKTREE_ID" \
  --title "$SESSION" \
  --command "$WORKER_COMMAND" \
  --json
# → 响应 .result.handle = "term_xxx"

# 3. 等 worker TUI 就绪（不等也能投 prompt，但等了更稳）
orca terminal wait --terminal "$HANDLE" --for tui-idle --timeout-ms 60000 --json

# 4. 投 prompt（spawn-worker 默认投一条占位指令；PM 后续用 orca terminal send 追加）
orca terminal send --terminal "$HANDLE" --text "..." --enter --json

# 5. spawn 完立即给 ORCA UI 设 in-progress
orca worktree set --worktree "id:$ORCA_WORKTREE_ID" \
  --workspace-status in-progress \
  --comment "spawn-worker.sh ORCA mode: worker command launched, waiting STATUS.json" --json

# 6. PM 巡检 / 收口用（只读）
orca worktree show --worktree "id:$ORCA_WORKTREE_ID" --json   # 查 workspace-status / comment
orca terminal read --terminal "$HANDLE" --limit 100 --json    # 查 worker 输出

# 7. sentinel 终态时同步 + clean-worktree 清理
orca worktree set --worktree "id:$ORCA_WORKTREE_ID" --workspace-status completed --comment "..." --json
orca worktree rm --worktree "id:$ORCA_WORKTREE_ID" --force --json
```

**关键 flag**：
- `--no-parent`：独立顶层 worktree，不挂在当前 worktree 下（ORCA 默认会推断 parent，多 worker 场景必须显式 `--no-parent`）。
- `--base-branch`：git base ref。spawn-worker 优先用 `BRANCH`（若已存在），否则 `BASE_REF`。
- `--worktree id:<repoId>::<path>`：完整 worktree id，不能只用 repoId。
- `--command`：worker 启动命令，保留 spawn-worker 的 launch.sh 包装（路径含空格也安全）。
- `--for tui-idle`：等 worker CLI TUI 进入 idle 状态（Claude Code / Codex / codebuddy 都适用）。

## 4. METADATA.json 锚点字段

`auto` 模式下 `write_metadata()` 在 `session` 块下加 `orca` 子块：

```json
{
  "session": {
    "id": "w1",
    "context": "/path/.claude/agent-sessions/w1",
    "orca": {
      "mode": "auto",
      "worktree_id": "<repoId>::/Users/.../orca/workspaces/tmux-w1",
      "worktree_path": "/Users/.../orca/workspaces/tmux-w1",
      "terminal_handle": "term_abc123",
      "tui_ready_method": "orca_terminal_wait_tui-idle",
      "app_version": "1.4.180",
      "capabilities": ["terminal.multiplex.v1", "agent-session.session-boundary.v1", "..."]
    }
  }
}
```

**字段含义**：
- `mode`：4 选 1（见 §2）。PM 巡检时一眼判断这个 worker 走的是 ORCA 还是 tmux。
- `worktree_id`：ORCA worktree 完整 id。sentinel / pm-monitor / clean-worktree 全靠这个字段定位 ORCA worktree。
- `worktree_path`：ORCA worktree 实际路径（可能与 `PROJECT_DIR` 不同——ORCA 默认放 `~/orca/workspaces/<name>`）。
- `terminal_handle`：ORCA terminal 句柄，runtime-scoped。ORCA 重启后会 stale，需 `orca terminal list` 重新获取。
- `app_version` / `capabilities`：spawn 时从 `orca status --json` 抓取的快照，排障用。

`force_tmux` / `lightweight_forces_tmux` 模式下 `orca` 子块仍写（`worktree_id` / `terminal_handle` 为空字符串），让 PM 明确知道这个 worker 没走 ORCA。

## 5. sentinel 双路径

`sentinel.sh`（v2.1）支持两套 worker session 参数：

| 参数组合 | WORKER_SESSION_TYPE | 行为 |
|----------|---------------------|------|
| `--tmux-session NAME` | `tmux` | 老路径：`tmux capture-pane` + `tmux kill-session` |
| `--terminal-handle HANDLE --worktree-id ID` | `orca_terminal` | ORCA 路径：`orca terminal read` + `orca terminal close` |

**终态同步**（`sync_orca_worktree_status()`，仅 `orca_terminal` 模式触发）：

| STATUS.json | ORCA workspace-status | comment |
|-------------|----------------------|---------|
| `done` / 同义词 | `completed` | `sentinel observed done at <UTC>` |
| `failed` / `blocked` / `stopped` / 同义词 | `in-review` | `sentinel observed non-success ... PM review` |
| timeout（`--max-wait` 到了） | `in-review` | `sentinel timeout <Ns> (PM investigate)` |

ORCA 不可用 / 调用失败时静默返回（sentinel 不能因 ORCA 故障阻塞主监控，降级到只 kill tmux / close terminal + exit）。

## 6. pm-monitor 同步点

`pm-monitor.sh` 在两个 stale 事件 emit 后调 `orca_worktree_set_status()`：

| 事件 | 触发条件 | ORCA workspace-status | comment |
|------|----------|----------------------|---------|
| `CHECKPOINT_STALE` | STATUS.json `updated_at` 超阈值（默认 300s，可被 `heartbeat_interval_seconds` 覆盖） | `in-review` | `checkpoint stale <Ns> (pm-monitor)` |
| `WORKER_STALE_NO_COMMIT` | tmux 存活但 `COMMIT_STALE_THRESHOLD`（默认 1800s）内无新 commit | `in-review` | `no commit in <Ns> (pm-monitor)` |

**防抖**：复用现有 `last_checkpoint_stale` / `last_commit_stale` bucket 模式（key 变化才触发），`orca_worktree_set_status()` 不再额外防抖，避免重复打 ORCA。

**失败容忍**：`orca_worktree_set_status()` 任何失败（无 orca 字段 / ORCA 不可用 / 调用失败）都静默返回，pm-monitor 主监控不受影响。

## 7. clean-worktree ORCA 清理

`clean-worktree.sh` 在 tmux kill 后、git worktree remove 前加 ORCA 清理：

```bash
if [ -n "${metadata_orca_worktree_id:-}" ] && [ "$KEEP_WORKTREE" -eq 0 ]; then
  if command -v orca >/dev/null 2>&1; then
    run orca worktree rm --worktree "id:$metadata_orca_worktree_id" --force
  else
    echo "CLEAN_WORKTREE_ORCA: orca CLI not found, skip ORCA worktree rm"
  fi
fi
```

**dry-run 友好**：用现有 `run()` 包装，`EXECUTE=0` 时只打印计划命令（`CLEAN_WORKTREE_RUN: orca worktree rm ...`），`EXECUTE=1` 才真删。

**顺序**：tmux kill → ORCA worktree rm → git worktree remove → branch delete。ORCA rm 放在 git remove 前的原因：ORCA worktree rm 失败不阻塞 git 清理（ORCA 不可用时只打印提示），保证 worker 至少在 git 层面被清掉。

## 8. 已知限制与降级

| 场景 | 表现 | 降级 |
|------|------|------|
| ORCA app 未运行 | `orca status --json` 失败 | spawn-worker `exit 64`，提示 `orca open` 或 `--no-orca-mode` |
| `orca` CLI 不在 PATH | `command -v orca` 失败 | 同上；或 `ensure_in_path orca` 后重试（候选目录含 `/Applications/Orca.app/Contents/Resources/bin`） |
| ORCA 版本太旧（无 `terminal.multiplex.v1`） | `detect_orca_mode` capability 校验失败 | spawn-worker `exit 64`，提示升级到 ≥1.4.x |
| ORCA 重启后 terminal handle stale | `orca terminal read/close` 返回 `terminal_handle_stale` | sentinel 日志 `SENTINEL_ORCA_TERMINAL_CLOSE_FAILED`，不阻塞 exit；PM 需 `orca terminal list --worktree id:$WT_ID` 重新获取 handle |
| `--no-worktree` 轻量模式 | ORCA 模式互斥 | 自动回落 tmux + 打印 `SPAWN_WORKER_ORCA_LIGHTWEIGHT_FORCES_TMUX` |
| 跨 repo（ORCA 终端里跑别的 repo） | `ORCA_WORKTREE_ID` path 不匹配 | 自动回落 tmux + 打印 `SPAWN_WORKER_ORCA_PATH_MISMATCH` |
| ORCA CLI 命令格式变更（未来版本） | jq 解析 `.result.worktreeId` / `.result.handle` 失败 | helper 函数（`orca_worktree_create` / `orca_terminal_create_and_send`）集中报错，改动只在这两处 |

## 9. 实战范例

待补：真实 ORCA 终端内 spawn worker → sentinel 等 done → ORCA UI 状态变化的端到端日志（参考 `smoke-orca-worker.sh` 的 3 步验证）。
