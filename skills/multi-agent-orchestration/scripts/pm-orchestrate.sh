#!/usr/bin/env bash
# Unified PM control plane for Orca supervised workers, Orca terminals and tmux.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=orca-runtime.sh
source "$SCRIPT_DIR/orca-runtime.sh"

usage() {
  cat >&2 <<'USAGE'
Usage:
  pm-orchestrate.sh run-create --objective TEXT
  pm-orchestrate.sh <command> --worktree PATH --session NAME [options]

Commands:
  run-create  Create and bind one Orca Run for a Wave
  send        Send guidance: Dispatch inbox for supervised, terminal input otherwise
  read|peek   Read exact worker transcript/terminal output; peek uses 15 rows
  show        Show supervised Dispatch state
  wait        Wait for Run Delivery (supervised) or TUI idle (terminal)
  ack         Acknowledge a processed Orca Delivery (`--delivery-id`)
  reply       Reply to a worker question (`--message-id` + `--text`)
  release     Release a settled supervised worker terminal
  retain      Retain a settled supervised worker terminal for debugging

Common:
  --worktree PATH   Worker worktree path
  --session NAME    spawn-worker session id
  --text TEXT       Prompt, guidance or reply body
  --prompt-file P   Read prompt/guidance from a file
  --lines N         Read limit (default: 50)
  --cursor VALUE    Opaque worker-read cursor
  --timeout SEC     Wait timeout (default: 60)
  --delivery-id ID  Delivery to acknowledge
  --message-id ID   Question message to answer
  --objective TEXT  Run objective

Supervised wait prints the complete Delivery JSON and never auto-acks it. Process every
message and decide release/reuse/retain before running `ack`.
USAGE
}

COMMAND="${1:-}"
[ -n "$COMMAND" ] || { usage; exit 64; }
shift

WORKTREE=""
SESSION=""
SEND_TEXT=""
PROMPT_FILE=""
LINES=50
CURSOR=""
WAIT_TIMEOUT=60
DELIVERY_ID=""
MESSAGE_ID=""
OBJECTIVE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --worktree) WORKTREE="$2"; shift 2 ;;
    --session) SESSION="$2"; shift 2 ;;
    --text) SEND_TEXT="$2"; shift 2 ;;
    --prompt-file) PROMPT_FILE="$2"; shift 2 ;;
    --lines) LINES="$2"; shift 2 ;;
    --cursor) CURSOR="$2"; shift 2 ;;
    --timeout) WAIT_TIMEOUT="$2"; shift 2 ;;
    --delivery-id) DELIVERY_ID="$2"; shift 2 ;;
    --message-id) MESSAGE_ID="$2"; shift 2 ;;
    --objective) OBJECTIVE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage; exit 64 ;;
  esac
done

case "$COMMAND" in
  run-create|send|read|peek|show|wait|ack|reply|release|retain) ;;
  *) echo "ERROR: unknown command: $COMMAND" >&2; usage; exit 64 ;;
esac
command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required" >&2; exit 64; }

if [ "$COMMAND" = "run-create" ]; then
  [ -n "$OBJECTIVE" ] || { echo "ERROR: run-create requires --objective" >&2; exit 64; }
  orca_runtime_init
  orca_cli orchestration run-create --objective "$OBJECTIVE" --json
  exit 0
fi

[ -n "$WORKTREE" ] || { echo "ERROR: --worktree is required" >&2; exit 64; }
[ -n "$SESSION" ] || { echo "ERROR: --session is required" >&2; exit 64; }
[[ "$LINES" =~ ^[0-9]+$ ]] || { echo "ERROR: --lines must be an integer" >&2; exit 64; }
[[ "$WAIT_TIMEOUT" =~ ^[0-9]+$ ]] || { echo "ERROR: --timeout must be an integer" >&2; exit 64; }

WORKTREE=$(cd "$WORKTREE" && pwd -P 2>/dev/null || printf '%s' "$WORKTREE")
SESSION_CONTEXT="$WORKTREE/.claude/agent-sessions/$SESSION"
METADATA="$SESSION_CONTEXT/METADATA.json"
WORKER_MODE=""
WORKER_HANDLE=""
ORCA_RUN_ID=""
ORCA_TASK_ID=""
ORCA_DISPATCH_ID=""

resolve_worker() {
  [ -f "$METADATA" ] || {
    echo "ERROR: METADATA not found: $METADATA" >&2
    exit 64
  }
  WORKER_HANDLE=$(jq -r '.session.orca.terminal_handle // empty' "$METADATA")
  ORCA_RUN_ID=$(jq -r '.session.orca.supervised.run_id // empty' "$METADATA")
  ORCA_TASK_ID=$(jq -r '.session.orca.supervised.task_id // empty' "$METADATA")
  ORCA_DISPATCH_ID=$(jq -r '.session.orca.supervised.dispatch_id // empty' "$METADATA")
  if [ -n "$ORCA_DISPATCH_ID" ]; then
    WORKER_MODE="orca_supervised"
  elif [ -n "$WORKER_HANDLE" ]; then
    WORKER_MODE="orca_terminal"
  else
    WORKER_MODE="tmux"
    WORKER_HANDLE="$SESSION"
  fi
}

load_text() {
  if [ -n "$PROMPT_FILE" ]; then
    [ -f "$PROMPT_FILE" ] || { echo "ERROR: --prompt-file not found: $PROMPT_FILE" >&2; exit 64; }
    cat "$PROMPT_FILE"
  elif [ -n "$SEND_TEXT" ]; then
    printf '%s' "$SEND_TEXT"
  else
    echo "ERROR: command requires --text or --prompt-file" >&2
    exit 64
  fi
}

needs_prompt_file() {
  local text="$1"
  [ "${#text}" -gt 500 ] && return 0
  case "$text" in *'`'*|*'$'*|*'|'*|*'```'*) return 0 ;; esac
  return 1
}

send_terminal_text() {
  local text="$1"
  if [ "$WORKER_MODE" = "orca_terminal" ]; then
    orca_runtime_init
    orca_cli terminal send --terminal "$WORKER_HANDLE" --text "$text" --enter --json >/dev/null
  else
    command -v tmux >/dev/null 2>&1 || { echo "ERROR: tmux not found" >&2; exit 64; }
    tmux has-session -t "$WORKER_HANDLE" 2>/dev/null || { echo "ERROR: tmux session not found: $WORKER_HANDLE" >&2; exit 1; }
    tmux send-keys -t "$WORKER_HANDLE" -l -- "$text"
    sleep 0.1
    tmux send-keys -t "$WORKER_HANDLE" Enter
  fi
}

cmd_send() {
  local text
  text=$(load_text)
  if [ "$WORKER_MODE" = "orca_supervised" ]; then
    orca_runtime_init
    orca_cli orchestration send --to "dispatch:$ORCA_DISPATCH_ID" \
      --type status --subject "PM guidance" --body "$text" --json
    return
  fi
  if needs_prompt_file "$text"; then
    local local_prompt="$SESSION_CONTEXT/WORKER_PROMPT.md"
    mkdir -p "$SESSION_CONTEXT"
    printf '%s\n' "$text" > "$local_prompt"
    send_terminal_text "请 Read .claude/agent-sessions/${SESSION}/WORKER_PROMPT.md 并严格按其指示执行"
  else
    send_terminal_text "$text"
  fi
}

cmd_read() {
  if [ "$WORKER_MODE" = "orca_supervised" ]; then
    orca_runtime_init
    local args=(orchestration worker-read --dispatch "$ORCA_DISPATCH_ID" --limit "$LINES")
    [ -z "$CURSOR" ] || args+=(--cursor "$CURSOR")
    orca_cli "${args[@]}" --json
  elif [ "$WORKER_MODE" = "orca_terminal" ]; then
    orca_runtime_init
    local args=(terminal read --terminal "$WORKER_HANDLE" --limit "$LINES")
    [ -z "$CURSOR" ] || args+=(--cursor "$CURSOR")
    orca_cli "${args[@]}" --json
  else
    command -v tmux >/dev/null 2>&1 || { echo "ERROR: tmux not found" >&2; exit 64; }
    tmux has-session -t "$WORKER_HANDLE" 2>/dev/null || { echo "ERROR: tmux session not found: $WORKER_HANDLE" >&2; exit 1; }
    tmux capture-pane -t "$WORKER_HANDLE" -p -S "-$LINES" | sed '/^[[:space:]]*$/d' | tail -n "$LINES"
  fi
}

cmd_show() {
  [ "$WORKER_MODE" = "orca_supervised" ] || { echo "ERROR: show requires an Orca supervised worker" >&2; exit 64; }
  orca_runtime_init
  orca_cli orchestration worker-show --dispatch "$ORCA_DISPATCH_ID" --json
}

cmd_wait() {
  local timeout_ms=$(( WAIT_TIMEOUT * 1000 ))
  if [ "$WORKER_MODE" = "orca_supervised" ]; then
    orca_runtime_init
    # A timeout is a liveness checkpoint, not failure. The JSON remains unacknowledged.
    orca_cli orchestration check --run "$ORCA_RUN_ID" --wait \
      --types worker_done,escalation,question --timeout-ms "$timeout_ms" --json
  elif [ "$WORKER_MODE" = "orca_terminal" ]; then
    orca_runtime_init
    orca_cli terminal wait --terminal "$WORKER_HANDLE" --for tui-idle --timeout-ms "$timeout_ms" --json
  else
    echo "PM_ORCHESTRATE_WAIT: tmux has no TUI-idle contract; sleeping ${WAIT_TIMEOUT}s (use sentinel for task terminal state)" >&2
    sleep "$WAIT_TIMEOUT"
  fi
}

cmd_ack() {
  [ "$WORKER_MODE" = "orca_supervised" ] || { echo "ERROR: ack requires an Orca supervised worker" >&2; exit 64; }
  [ -n "$DELIVERY_ID" ] || { echo "ERROR: ack requires --delivery-id" >&2; exit 64; }
  orca_runtime_init
  orca_cli orchestration check --run "$ORCA_RUN_ID" --ack "$DELIVERY_ID" --json
}

cmd_reply() {
  [ "$WORKER_MODE" = "orca_supervised" ] || { echo "ERROR: reply requires an Orca supervised worker" >&2; exit 64; }
  [ -n "$MESSAGE_ID" ] || { echo "ERROR: reply requires --message-id" >&2; exit 64; }
  local text
  text=$(load_text)
  orca_runtime_init
  orca_cli orchestration reply --id "$MESSAGE_ID" --body "$text" --json
}

cmd_account() {
  [ "$WORKER_MODE" = "orca_supervised" ] || { echo "ERROR: $COMMAND requires an Orca supervised worker" >&2; exit 64; }
  orca_runtime_init
  orca_cli orchestration "worker-$COMMAND" --dispatch "$ORCA_DISPATCH_ID" --json
}

resolve_worker
case "$COMMAND" in
  send) cmd_send ;;
  read) cmd_read ;;
  peek) LINES=15; cmd_read ;;
  show) cmd_show ;;
  wait) cmd_wait ;;
  ack) cmd_ack ;;
  reply) cmd_reply ;;
  release|retain) cmd_account ;;
esac
