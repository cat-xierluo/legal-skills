# 13. PM 控制 worker 统一入口（pm-orchestrate.sh）

> Level 2 reference。配合 SKILL §7.1 ORCA PM 分支 + §10 scripts 列表。
> 版本：v2.2.0（Task-034，2026-08-12）。

## 1. 边界

**适用**：PM 在任何环境下用统一命令控制 worker，不用关心 worker 是 ORCA terminal 还是 tmux session。

**不适用**：
- 控制 ORCA 内未通过 spawn-worker 起的 terminal（METADATA 缺，模式判断失败）
- 跨 worktree 的批量控制（pm-orchestrate 一次只控一个 worker）
- 投递路径控制 / task 依赖 / decision gate（用 ORCA orchestration 体系 / pm-monitor）

## 2. 双模式自动判断

pm-orchestrate.sh 读 `<worktree>/.claude/agent-sessions/<session>/METADATA.json`：

| 判定 | 路径 |
|---|---|
| `session.orca.terminal_handle` 非空 | ORCA 模式：`orca terminal send/read/wait` |
| 上述字段空（或 ORCA app 不可用降级） | tmux 模式：`tmux send-keys/capture-pane`（session 名 = `<session>`） |

PM 一个命令管两种 worker，不用关心类型。失败容忍：ORCA 模式 ORCA 不可用 → exit 64；tmux 模式 tmux 不在 PATH → exit 64。

## 3. 子命令

### `send` —— 投 prompt

```bash
pm-orchestrate.sh send --worktree $WT --session $S --text "请修复 X bug"
pm-orchestrate.sh send --worktree $WT --session $S --prompt-file ./full-spec.md
```

**超长自动 WORKER_PROMPT.md**（SKILL §5.2 标准模式）：文本 >500 字符 或含反引号/`$`/`|`/` ``` ``` 时，**不直接投**（避免 tmux/orca 终端转义问题），写 `<session_context>/WORKER_PROMPT.md` + 投短指令 `请 Read .claude/agent-sessions/<session>/WORKER_PROMPT.md 并严格按其指示执行`。PM 不用自己判断长度。

### `read` —— 读 worker 输出

```bash
pm-orchestrate.sh read --worktree $WT --session $S --lines 50   # 默认 50
```

读 worker 尾部 `--lines` 行（ORCA: `orca terminal read --limit`；tmux: `capture-pane -S -N`）。

### `peek` —— 快速尾部（15 行）

```bash
pm-orchestrate.sh peek --worktree $WT --session $S
```

等价 `read --lines 15`。PM 快速看 worker 状态时常用。

### `wait` —— 等 worker TUI idle

```bash
pm-orchestrate.sh wait --worktree $WT --session $S --timeout 60
```

- ORCA 模式：`orca terminal wait --for tui-idle --timeout-ms $((timeout*1000))`
- tmux 模式：**无原生 tui-idle 检测**（tmux 不解析 TUI 状态），降级为 `sleep $timeout`。建议 tmux 模式改用 `sentinel.sh` / `pm-monitor.sh` 等真终态机制，不要用 `wait`。

## 4. 与其它控制层的关系

| 层 | 命令 | 何时用 |
|---|---|---|
| pm-orchestrate（首选） | `pm-orchestrate send/read/peek/wait` | PM 一次性交互（投 prompt / 读响应 / 快速 peek） |
| sentinel（终态监控） | `bash sentinel.sh ... &` | 长时间等 worker done，harness task-notification 唤醒 PM |
| pm-monitor（多 worker 巡检） | `bash pm-monitor.sh --log-file ... &` | 多 worker Wave 周期巡检 |
| 直接 ORCA CLI | `orca terminal send ...` | pm-orchestrate 不够用时的低层兜底 |
| 直接 tmux | `tmux send-keys -t session ...` | 同上 |

**核心原则**：PM 90% 场景用 `pm-orchestrate` 一个统一入口；sentinel/pm-monitor 处理后台监控；直接 ORCA/tmux CLI 是兜底。

## 5. 实战范例

ORCA 模式 worker（W1 = claude，spawn-worker ORCA 模式自动建）：

```bash
# 1. 投任务
pm-orchestrate send --worktree $WT --session W1 --text "请用 bash 跑 ls -la"

# 2. 等 TUI idle（claude 处理完当前 prompt）
pm-orchestrate wait --worktree $WT --session W1 --timeout 60

# 3. 看响应
pm-orchestrate read --worktree $WT --session W1 --lines 30

# 4. 超长任务规范
pm-orchestrate send --worktree $WT --session W1 --prompt-file ./long-spec.md
# → 自动写 WORKER_PROMPT.md，投短 Read 指令
```

tmux 模式 worker（spawn-worker 默认或 --no-orca-mode 强制）：

```bash
# 完全相同命令，pm-orchestrate 自动走 tmux 路径
pm-orchestrate send --worktree $WT --session W1 --text "..."
pm-orchestrate peek --worktree $WT --session W1
```

## 6. 已知限制

| 场景 | 表现 | 降级 |
|---|---|---|
| ORCA 模式但 ORCA app 未运行 | `orca CLI not found` exit 64 | 提示 `orca open` |
| ORCA mode 但 terminal handle stale（ORCA 重启后） | `orca terminal send` 失败 | 提示跑 `orca terminal list` 重新获取 handle |
| tmux mode + worker 不在 tmux 里（ORCA-only 误判） | `tmux session 不存在` exit 1 | 用 `pm-orchestrate peek` 确认 mode + handle |
| 超长 + 特殊字符同时存在 | 仍走 WORKER_PROMPT.md（自动检测覆盖两者） | — |
| tmux `wait` 子命令 | sleep 等时（无 TUI 状态检测） | 改用 `sentinel.sh` 真终态 |