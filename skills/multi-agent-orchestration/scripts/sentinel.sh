#!/usr/bin/env bash
# sentinel.sh — event-driven watcher that wakes PM via harness task-notification
# when a worker reaches a terminal STATUS.json state.
#
# Designed to run as a single Bash run_in_background=true task per worker.
# On terminal status: capture tmux pane tail (best-effort), then optionally
# kill the worker's tmux session, then exit. Harness re-invokes the parent
# agent via task-notification regardless of exit code.
#
# Validated 2026-06-05 by 3-phase spike (see references/sentinel-design.md).

set -euo pipefail

STATUS_FILE=""
TMUX_SESSION=""
POLL_INTERVAL=5
MAX_WAIT=7200
LOG_FILE=""
KEEP_TMUX=0
PANE_TAIL_LINES=80

usage() {
  cat >&2 <<'USAGE'
Usage:
  sentinel.sh --status-file PATH --tmux-session NAME [options]

Required:
  --status-file PATH     Worker STATUS.json path (e.g. .claude/agent-sessions/<id>/STATUS.json)
  --tmux-session NAME    Worker tmux session name (must match spawn-worker.sh --session)

Optional:
  --poll-interval N      Seconds between STATUS.json polls. Default: 5
  --max-wait SECONDS     Hard cap on total runtime. Default: 7200 (2h)
  --log-file PATH        Override SENTINEL_OUT.log path
  --pane-tail-lines N    Capture last N lines of tmux pane before kill. Default: 80, 0 disables
  --keep-tmux-on-terminal
                         Do NOT kill tmux on terminal state (review phase use)

Exit codes:
  0   done
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
    --tmux-session)
      TMUX_SESSION="$2"
      shift 2
      ;;
    --poll-interval)
      POLL_INTERVAL="$2"
      shift 2
      ;;
    --max-wait)
      MAX_WAIT="$2"
      shift 2
      ;;
    --log-file)
      LOG_FILE="$2"
      shift 2
      ;;
    --pane-tail-lines)
      PANE_TAIL_LINES="$2"
      shift 2
      ;;
    --keep-tmux-on-terminal)
      KEEP_TMUX=1
      shift
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

[ -n "$STATUS_FILE" ] || { usage; exit 64; }
[ -n "$TMUX_SESSION" ] || { usage; exit 64; }
command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required" >&2; exit 64; }

if [ -z "$LOG_FILE" ]; then
  LOG_FILE="$(dirname "$STATUS_FILE")/SENTINEL_OUT.log"
fi

# Best-effort logging; do not let a log write failure abort the sentinel.
log() {
  printf '%s\n' "$*" >> "$LOG_FILE" 2>/dev/null || true
}

# Inline copy of wait-worker.sh:187-203 redact function. Kept local to avoid
# cross-script dependency. Updates to that file should be mirrored here.
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

capture_pane_tail() {
  [ "$PANE_TAIL_LINES" -gt 0 ] || return 0
  command -v tmux >/dev/null 2>&1 || return 0
  tmux has-session -t "$TMUX_SESSION" 2>/dev/null || {
    log "SENTINEL_PANE_GONE: session=$TMUX_SESSION reason=not_found"
    return 0
  }
  log "SENTINEL_PANE_TAIL: session=$TMUX_SESSION lines=$PANE_TAIL_LINES"
  tmux capture-pane -t "$TMUX_SESSION" -p -S "-$PANE_TAIL_LINES" 2>/dev/null \
    | sed '/^[[:space:]]*$/d' \
    | tail -n "$PANE_TAIL_LINES" \
    | redact_sensitive_stream \
    | while IFS= read -r line; do log "$line"; done
}

kill_tmux_if_requested() {
  if [ "$KEEP_TMUX" -eq 1 ]; then
    log "SENTINEL_KEEP_TMUX: session=$TMUX_SESSION"
    return 0
  fi
  if ! command -v tmux >/dev/null 2>&1; then
    log "SENTINEL_TMUX_UNAVAILABLE: tmux command not found"
    return 0
  fi
  if ! tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    log "SENTINEL_TMUX_GONE: session=$TMUX_SESSION (already killed externally)"
    return 0
  fi
  tmux kill-session -t "$TMUX_SESSION" 2>/dev/null || {
    log "SENTINEL_KILL_FAILED: session=$TMUX_SESSION"
    return 0
  }
  log "SENTINEL_TMUX_KILLED: session=$TMUX_SESSION"
}

log "SENTINEL_START: status=$STATUS_FILE tmux=$TMUX_SESSION poll=${POLL_INTERVAL}s max_wait=${MAX_WAIT}s log=$LOG_FILE"

START_EPOCH=$(date +%s)

while true; do
  if [ ! -f "$STATUS_FILE" ]; then
    log "SENTINEL_PENDING: status_file_missing path=$STATUS_FILE"
  else
    status=$(jq -r '.status // "unknown"' "$STATUS_FILE" 2>/dev/null || echo "unknown")
    case "$status" in
      # Canonical success terminal is "done". The synonym set
      # (completed|finished|complete) is defensive: worker LLM providers
      # occasionally drift from the canonical string. PM should still write
      # status="done" exactly per templates/worker-prompt.md, but the sentinel
      # will not get stuck polling if the worker wrote a synonym.
      done|completed|finished|complete)
        capture_pane_tail
        log "SENTINEL_TERMINAL: status=$status file=$STATUS_FILE"
        kill_tmux_if_requested
        exit 0
        ;;
      # Canonical failure terminals: failed | blocked | stopped. Defensive
      # synonyms added for the same reason as above. PM should still use
      # the canonical strings, but a worker that wrote "aborted" or
      # "cancelled" is also recognized as a non-success terminal.
      failed|blocked|stopped|aborted|cancelled)
        capture_pane_tail
        log "SENTINEL_TERMINAL: status=$status file=$STATUS_FILE"
        kill_tmux_if_requested
        exit 2
        ;;
      running|unknown|"")
        :
        ;;
      *)
        log "SENTINEL_UNKNOWN_STATUS: status=$status file=$STATUS_FILE"
        ;;
    esac
  fi

  elapsed=$(( $(date +%s) - START_EPOCH ))
  if [ "$elapsed" -ge "$MAX_WAIT" ]; then
    log "SENTINEL_TIMEOUT: ${elapsed}s max_wait=${MAX_WAIT}s file=$STATUS_FILE"
    kill_tmux_if_requested
    exit 124
  fi

  sleep "$POLL_INTERVAL"
done
