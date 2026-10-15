#!/usr/bin/env bash
# wait-worker.sh — wait for one worker checkpoint to reach a terminal status.
#
# Use cases:
#   Claude Code PM: run this from Bash with run_in_background=true.
#   Codex PM: use this as a quick checker from a thread heartbeat or manual poll.

set -euo pipefail

STATUS_FILE=""
SESSION_CONTEXT=""
WORKTREE=""
SESSION=""
INTERVAL=30
TIMEOUT=0
ONCE=0
RESULT_TAIL_LINES=40
TMUX_SESSION=""
PANE_TAIL_LINES=80
INCLUDE_PANE_ON="missing,stale,terminal"
STALE_THRESHOLD=300
LAST_PANE_REASON=""

usage() {
  cat >&2 <<'USAGE'
Usage:
  wait-worker.sh --status-file PATH [--once] [--interval 30] [--timeout 0]
  wait-worker.sh --session-context PATH [--once] [--interval 30] [--timeout 0]
  wait-worker.sh --worktree PATH --session NAME [--once] [--interval 30] [--timeout 0]

Optional tmux diagnostics:
  --tmux-session NAME
  --pane-tail-lines 80
  --include-pane-on missing,stale,terminal  # missing|stale|terminal|always|never, comma-separated
  --stale-threshold 300

Exit codes:
  0   done, or non-terminal status when --once is used
  2   failed / blocked / stopped
  64  usage error
  124 timeout
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --status-file)
      STATUS_FILE="$2"
      shift 2
      ;;
    --session-context)
      SESSION_CONTEXT="$2"
      shift 2
      ;;
    --worktree)
      WORKTREE="$2"
      shift 2
      ;;
    --session)
      SESSION="$2"
      shift 2
      ;;
    --interval)
      INTERVAL="$2"
      shift 2
      ;;
    --timeout)
      TIMEOUT="$2"
      shift 2
      ;;
    --once)
      ONCE=1
      shift
      ;;
    --result-tail-lines)
      RESULT_TAIL_LINES="$2"
      shift 2
      ;;
    --tmux-session)
      TMUX_SESSION="$2"
      shift 2
      ;;
    --pane-tail-lines)
      PANE_TAIL_LINES="$2"
      shift 2
      ;;
    --include-pane-on)
      INCLUDE_PANE_ON="$2"
      shift 2
      ;;
    --stale-threshold)
      STALE_THRESHOLD="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 64
      ;;
  esac
done

command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required" >&2; exit 64; }

if [ -z "$STATUS_FILE" ]; then
  if [ -n "$SESSION_CONTEXT" ]; then
    STATUS_FILE="$SESSION_CONTEXT/STATUS.json"
  elif [ -n "$WORKTREE" ] && [ -n "$SESSION" ]; then
    STATUS_FILE="$WORKTREE/.claude/agent-sessions/$SESSION/STATUS.json"
  else
    usage
    exit 64
  fi
fi

SESSION_CONTEXT=$(dirname "$STATUS_FILE")
RESULT_FILE="$SESSION_CONTEXT/RESULT.md"
PATCH_FILE="$SESSION_CONTEXT/PATCH_SUMMARY.md"
START_EPOCH=$(date +%s)
LAST_KEY=""

parse_iso_epoch() {
  local ts="$1"
  [ -z "$ts" ] && { echo "0"; return; }

  local ts_clean is_utc
  is_utc=0
  case "$ts" in
    *Z) is_utc=1 ;;
  esac
  ts_clean=$(echo "$ts" | sed 's/[+-][0-9][0-9]:..$//' | sed 's/Z$//' | sed 's/\..*$//')
  if [ "$is_utc" -eq 1 ]; then
    date -j -u -f "%Y-%m-%dT%H:%M:%S" "$ts_clean" "+%s" 2>/dev/null \
      || date -d "$ts" "+%s" 2>/dev/null \
      || echo "0"
  else
    date -j -f "%Y-%m-%dT%H:%M:%S" "$ts_clean" "+%s" 2>/dev/null \
      || date -d "$ts" "+%s" 2>/dev/null \
      || echo "0"
  fi
}

should_include_pane() {
  local reason="$1"
  [ -n "$TMUX_SESSION" ] || return 1
  [ "$INCLUDE_PANE_ON" != "never" ] || return 1
  [ "$INCLUDE_PANE_ON" = "always" ] && return 0

  case ",$INCLUDE_PANE_ON," in
    *",$reason,"*) return 0 ;;
    *) return 1 ;;
  esac
}

emit_tmux_pane() {
  local reason="$1"
  should_include_pane "$reason" || return 0

  if [ "$reason" != "always" ] && [ "$reason" = "$LAST_PANE_REASON" ]; then
    return 0
  fi

  if ! command -v tmux >/dev/null 2>&1; then
    echo "WAIT_WORKER_TMUX_UNAVAILABLE: tmux command not found"
    return 0
  fi

  if ! tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    echo "WAIT_WORKER_TMUX_UNAVAILABLE: session=$TMUX_SESSION"
    LAST_PANE_REASON="$reason"
    return 0
  fi

  echo "WAIT_WORKER_TMUX_TAIL: reason=$reason session=$TMUX_SESSION lines=$PANE_TAIL_LINES"
  tmux capture-pane -t "$TMUX_SESSION" -p -S "-$PANE_TAIL_LINES" 2>/dev/null \
    | sed '/^[[:space:]]*$/d' \
    | tail -n "$PANE_TAIL_LINES" \
    | redact_sensitive_stream || true
  LAST_PANE_REASON="$reason"
  return 0
}

redact_sensitive_stream() {
  awk '
    {
      line = $0
      low = tolower(line)
      if (low ~ /(anthropic_|openai_|azure_openai_|google_api_key|gemini_|claude_api|codex_|authorization|bearer[[:space:]]|private[_-]?key|access[_-]?key|refresh[_-]?token|id[_-]?token|auth[_-]?token|api[_-]?key)/ || low ~ /(^|[^a-z0-9_])(token|key|secret|auth|password|passwd)[[:space:]]*[=:]/) {
        print "[redacted sensitive line]"
        next
      }
      gsub(/sk-[A-Za-z0-9_-][A-Za-z0-9_-]*/, "[redacted-secret]", line)
      gsub(/gh[pousr]_[A-Za-z0-9_][A-Za-z0-9_]*/, "[redacted-secret]", line)
      gsub(/glpat-[A-Za-z0-9_-][A-Za-z0-9_-]*/, "[redacted-secret]", line)
      gsub(/xox[baprs]-[A-Za-z0-9-][A-Za-z0-9-]*/, "[redacted-secret]", line)
      print line
    }
  '
}

emit_status() {
  local status="$1"
  local phase="$2"
  local progress="$3"
  local updated_at="$4"
  local current_action="$5"
  local next_action="$6"
  local pr_url="$7"

  echo "WAIT_WORKER_STATUS: status=${status:-unknown} phase=${phase:-n/a} progress=${progress:-n/a} updated_at=${updated_at:-n/a}"
  echo "WAIT_WORKER_ACTION: current=${current_action:-n/a} next=${next_action:-n/a}"
  [ -n "$pr_url" ] && echo "WAIT_WORKER_PR: $pr_url"
  return 0
}

emit_terminal_files() {
  if [ -f "$RESULT_FILE" ]; then
    echo "WAIT_WORKER_RESULT: $RESULT_FILE"
    tail -n "$RESULT_TAIL_LINES" "$RESULT_FILE" 2>/dev/null | redact_sensitive_stream || true
  fi
  if [ -f "$PATCH_FILE" ]; then
    echo "WAIT_WORKER_PATCH_SUMMARY: $PATCH_FILE"
  fi
  return 0
}

echo "WAIT_WORKER_STARTED: $STATUS_FILE"

while true; do
  if [ ! -f "$STATUS_FILE" ]; then
    echo "WAIT_WORKER_PENDING: status file not found"
    emit_tmux_pane "missing"
  else
    status=$(jq -r '.status // "unknown"' "$STATUS_FILE" 2>/dev/null || echo "unknown")
    phase=$(jq -r '.phase // ""' "$STATUS_FILE" 2>/dev/null || echo "")
    progress=$(jq -r '.progress // ""' "$STATUS_FILE" 2>/dev/null || echo "")
    updated_at=$(jq -r '.updated_at // ""' "$STATUS_FILE" 2>/dev/null || echo "")
    current_action=$(jq -r '.current_action // ""' "$STATUS_FILE" 2>/dev/null || echo "")
    next_action=$(jq -r '.next_action // ""' "$STATUS_FILE" 2>/dev/null || echo "")
    pr_url=$(jq -r '.git.pr_url // .pr_url // ""' "$STATUS_FILE" 2>/dev/null || echo "")
    key="$status|$phase|$progress|$updated_at|$current_action|$next_action|$pr_url"

    if [ "$key" != "$LAST_KEY" ]; then
      emit_status "$status" "$phase" "$progress" "$updated_at" "$current_action" "$next_action" "$pr_url"
      LAST_KEY="$key"
    fi

    if [ "$status" != "done" ] && [ -n "$updated_at" ]; then
      updated_epoch=$(parse_iso_epoch "$updated_at")
      if [ "$updated_epoch" -gt 0 ]; then
        stale_seconds=$(( $(date +%s) - updated_epoch ))
        if [ "$stale_seconds" -gt "$STALE_THRESHOLD" ]; then
          echo "WAIT_WORKER_STALE: ${stale_seconds}s threshold=${STALE_THRESHOLD}s file=$STATUS_FILE"
          emit_tmux_pane "stale"
        fi
      fi
    fi

    case "$status" in
      done)
        echo "WAIT_WORKER_DONE: $STATUS_FILE"
        emit_terminal_files
        emit_tmux_pane "terminal"
        exit 0
        ;;
      failed|blocked|stopped)
        echo "WAIT_WORKER_TERMINAL: status=$status file=$STATUS_FILE"
        emit_terminal_files
        emit_tmux_pane "terminal"
        exit 2
        ;;
    esac

    emit_tmux_pane "always"
  fi

  if [ "$ONCE" -eq 1 ]; then
    echo "WAIT_WORKER_NOT_DONE: $STATUS_FILE"
    exit 0
  fi

  if [ "$TIMEOUT" -gt 0 ]; then
    elapsed=$(( $(date +%s) - START_EPOCH ))
    if [ "$elapsed" -ge "$TIMEOUT" ]; then
      echo "WAIT_WORKER_TIMEOUT: ${elapsed}s $STATUS_FILE"
      exit 124
    fi
  fi

  sleep "$INTERVAL"
done
