#!/usr/bin/env bash
# pm-orchestrate.sh — PM 控制 worker 的统一入口（ORCA 模式 + tmux 模式自动判断）。
#
# 解决"PM 在 ORCA 里控制 worker 要手敲 orca terminal send/read"的手感缝隙。
# 读 session_context/METADATA 自动判断 worker 类型：
#   - session.orca.terminal_handle 有值 → orca terminal send/read/wait
#   - 否则 → tmux send-keys/capture-pane（session.id 作 tmux session 名）
# PM 一个命令管两种 worker，不用关心类型。
#
# 用法：
#   pm-orchestrate.sh <command> --worktree PATH --session NAME [command options]
#
# Commands:
#   send   投 prompt（超长 / 含特殊字符自动走 WORKER_PROMPT.md + 短指令，SKILL §5.2）
#   read   读 worker 输出（默认 50 行）
#   peek   尾部快速看（15 行）
#   wait   等 worker TUI idle（ORCA 原生；tmux 无原生，简化 sleep）
#
# 退出码：0 成功；64 参数错误；1 命令失败。

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

usage() {
  cat >&2 <<'USAGE'
Usage:
  pm-orchestrate.sh <command> --worktree PATH --session NAME [options]

Common:
  --worktree PATH   Worker worktree path（session_context = worktree/.claude/agent-sessions/<session>）
  --session NAME    Worker session id（spawn-worker --session）

Commands:
  send   投 prompt
    --text "..."        直接投文本
    --prompt-file PATH  从文件读 prompt 投递
    （超长 >500 字符 或 含反引号/$/|/表格 自动走 WORKER_PROMPT.md + 短 Read 指令）
  read   读 worker 输出
    --lines N           尾部行数（默认 50）
  peek   尾部快速看（15 行，等价 read --lines 15）
  wait   等 worker TUI idle（claude/codex 处理完当前 prompt）
    --timeout SECONDS   超时（默认 60s；ORCA 原生 tui-idle；tmux 简化 sleep）

示例：
  pm-orchestrate.sh send --worktree .claude/worktrees/tmux-w1 --session w1 --text "请修复 X"
  pm-orchestrate.sh send --worktree $WT --session w1 --prompt-file ./full-prompt.md
  pm-orchestrate.sh read --worktree $WT --session w1 --lines 30
  pm-orchestrate.sh peek --worktree $WT --session w1
  pm-orchestrate.sh wait --worktree $WT --session w1 --timeout 120
USAGE
}

# ---------- 参数解析 ----------
COMMAND=""
WORKTREE=""
SESSION=""
SEND_TEXT=""
PROMPT_FILE=""
LINES=50
WAIT_TIMEOUT=60

if [ $# -lt 1 ]; then
  usage; exit 64
fi
COMMAND="$1"
shift

while [[ $# -gt 0 ]]; do
  case "$1" in
    --worktree) WORKTREE="$2"; shift 2 ;;
    --session) SESSION="$2"; shift 2 ;;
    --text) SEND_TEXT="$2"; shift 2 ;;
    --prompt-file) PROMPT_FILE="$2"; shift 2 ;;
    --lines) LINES="$2"; shift 2 ;;
    --timeout) WAIT_TIMEOUT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage; exit 64 ;;
  esac
done

case "$COMMAND" in
  send|read|peek|wait) ;;
  *) echo "ERROR: unknown command: $COMMAND (send|read|peek|wait)" >&2; usage; exit 64 ;;
esac

[ -n "$WORKTREE" ] || { echo "ERROR: --worktree is required" >&2; exit 64; }
[ -n "$SESSION" ] || { echo "ERROR: --session is required" >&2; exit 64; }
command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required" >&2; exit 64; }

# 解析物理路径
WORKTREE=$(cd "$WORKTREE" && pwd -P 2>/dev/null || echo "$WORKTREE")
SESSION_CONTEXT="$WORKTREE/.claude/agent-sessions/$SESSION"
METADATA="$SESSION_CONTEXT/METADATA.json"

# ---------- resolve_worker：判断模式 + 句柄 ----------
# 自动判断：METADATA session.orca.terminal_handle 有值 → ORCA；否则 tmux（session 名 = SESSION）。
WORKER_MODE=""
WORKER_HANDLE=""

resolve_worker() {
  if [ ! -f "$METADATA" ]; then
    echo "ERROR: METADATA not found: $METADATA（确认 --worktree + --session 是否匹配 spawn-worker 记录）" >&2
    exit 64
  fi
  local orca_handle
  orca_handle=$(jq -r '.session.orca.terminal_handle // empty' "$METADATA" 2>/dev/null || echo "")
  if [ -n "$orca_handle" ]; then
    WORKER_MODE="orca"
    WORKER_HANDLE="$orca_handle"
  else
    WORKER_MODE="tmux"
    WORKER_HANDLE="$SESSION"  # spawn-worker tmux new-session -s "$SESSION"
  fi
}

# ---------- do_send：底层投递 ----------
do_send() {
  local text="$1"
  if [ "$WORKER_MODE" = "orca" ]; then
    command -v orca >/dev/null 2>&1 || { echo "ERROR: orca CLI not found" >&2; exit 64; }
    orca terminal send --terminal "$WORKER_HANDLE" --text "$text" --enter --json >/dev/null 2>&1 || {
      echo "ERROR: orca terminal send failed（handle=$WORKER_HANDLE 可能 stale，跑 orca terminal list 重新获取）" >&2; exit 1; }
  else
    command -v tmux >/dev/null 2>&1 || { echo "ERROR: tmux not found" >&2; exit 64; }
    tmux has-session -t "$WORKER_HANDLE" 2>/dev/null || { echo "ERROR: tmux session 不存在: $WORKER_HANDLE" >&2; exit 1; }
    tmux send-keys -t "$WORKER_HANDLE" -l -- "$text"
    sleep 0.1
    tmux send-keys -t "$WORKER_HANDLE" Enter
  fi
}

# ---------- 判断 prompt 是否需要走 WORKER_PROMPT.md（超长 / 特殊字符）----------
# 超长（>500 字符）或含反引号 / $ / | / 换行表格 → tmux/orca 直接投有转义风险，走文件 + 短指令。
needs_prompt_file() {
  local text="$1"
  local len=${#text}
  [ "$len" -gt 500 ] && return 0
  # 含反引号、$、|、或连续特殊 markdown 字符
  case "$text" in
    *'`'*|*'$'*|*'|'*|*'```'*) return 0 ;;
  esac
  return 1
}

# ---------- send ----------
cmd_send() {
  resolve_worker
  local text=""
  if [ -n "$PROMPT_FILE" ]; then
    [ -f "$PROMPT_FILE" ] || { echo "ERROR: --prompt-file 不存在: $PROMPT_FILE" >&2; exit 64; }
    text=$(cat "$PROMPT_FILE")
  elif [ -n "$SEND_TEXT" ]; then
    text="$SEND_TEXT"
  else
    echo "ERROR: send 需要 --text 或 --prompt-file" >&2; exit 64
  fi

  if needs_prompt_file "$text"; then
    # SKILL §5.2 标准模式：写 WORKER_PROMPT.md + 投短 Read 指令
    local prompt_file="$SESSION_CONTEXT/WORKER_PROMPT.md"
    mkdir -p "$SESSION_CONTEXT"
    printf '%s\n' "$text" > "$prompt_file"
    local short="请 Read .claude/agent-sessions/${SESSION}/WORKER_PROMPT.md 并严格按其指示执行"
    echo "PM_ORCHESTRATE_SEND: prompt_file（len=${#text} > 500 或含特殊字符，走 WORKER_PROMPT.md）" >&2
    do_send "$short"
  else
    echo "PM_ORCHESTRATE_SEND: inline（mode=$WORKER_MODE handle=$WORKER_HANDLE len=${#text}）" >&2
    do_send "$text"
  fi
}

# ---------- read ----------
cmd_read() {
  resolve_worker
  if [ "$WORKER_MODE" = "orca" ]; then
    command -v orca >/dev/null 2>&1 || { echo "ERROR: orca CLI not found" >&2; exit 64; }
    orca terminal read --terminal "$WORKER_HANDLE" --limit "$LINES" --json 2>/dev/null \
      | jq -r '.result.terminal.tail[]? // empty' 2>/dev/null
  else
    command -v tmux >/dev/null 2>&1 || { echo "ERROR: tmux not found" >&2; exit 64; }
    tmux has-session -t "$WORKER_HANDLE" 2>/dev/null || { echo "ERROR: tmux session 不存在: $WORKER_HANDLE" >&2; exit 1; }
    tmux capture-pane -t "$WORKER_HANDLE" -p -S "-$LINES" 2>/dev/null | sed '/^[[:space:]]*$/d' | tail -n "$LINES"
  fi
}

# ---------- peek ----------
cmd_peek() {
  LINES=15
  cmd_read
}

# ---------- wait ----------
cmd_wait() {
  resolve_worker
  if [ "$WORKER_MODE" = "orca" ]; then
    command -v orca >/dev/null 2>&1 || { echo "ERROR: orca CLI not found" >&2; exit 64; }
    local timeout_ms=$(( WAIT_TIMEOUT * 1000 ))
    orca terminal wait --terminal "$WORKER_HANDLE" --for tui-idle --timeout-ms "$timeout_ms" --json 2>/dev/null \
      | jq -r '"PM_ORCHESTRATE_WAIT: condition=\(.result.condition // "unknown") waited_ms=\(.result.waitedMs // 0)"' 2>/dev/null || true
  else
    # tmux 不解析 TUI 状态（claude/codex idle），无原生 wait。建议用 sentinel / pm-monitor。
    echo "PM_ORCHESTRATE_WAIT: tmux 模式无原生 tui-idle（建议用 sentinel.sh / pm-monitor.sh 等终态），简化 sleep ${WAIT_TIMEOUT}s" >&2
    sleep "$WAIT_TIMEOUT"
  fi
}

# ---------- dispatch ----------
case "$COMMAND" in
  send) cmd_send ;;
  read) cmd_read ;;
  peek) cmd_peek ;;
  wait) cmd_wait ;;
esac
