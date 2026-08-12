#!/usr/bin/env bash
# sentinel.sh — event-driven watcher that wakes PM via harness task-notification
# when a worker reaches a terminal STATUS.json state.
#
# Designed to run as a single Bash run_in_background=true task per worker.
# On terminal status: capture tmux pane tail (best-effort), then optionally
# kill the worker's tmux session, then exit. Harness re-invokes the parent
# agent via task-notification regardless of exit code.
#
# Validated 2026-06-05 by 3-phase spike (see references/04-sentinel-design.md).

set -euo pipefail

STATUS_FILE=""
TMUX_SESSION=""
TERMINAL_HANDLE=""
WORKTREE_ID=""
DISPATCH_ID=""  # v2.1.1（Task-033）：ORCA supervised dispatch id（ctx_xxx），终态时 worker-release/stop
POLL_INTERVAL=5
MAX_WAIT=7200
LOG_FILE=""
KEEP_TMUX=0
PANE_TAIL_LINES=80
# v2.1（DEC-114）：sentinel 双路径 worker session——TMUX_SESSION 走原 tmux capture-pane / kill-session，
# TERMINAL_HANDLE 走 orca terminal read / orca terminal close。worker_session_type 派生：
#   "tmux"           — 老路径，零行为变化
#   "orca_terminal"  — ORCA 终端模式，spawn-worker.sh ORCA 分支配对传 --terminal-handle --worktree-id
WORKER_SESSION_TYPE=""

usage() {
  cat >&2 <<'USAGE'
Usage:
  sentinel.sh --status-file PATH (--tmux-session NAME | --terminal-handle HANDLE --worktree-id ID) [options]

Required (one of two worker session specs):
  --status-file PATH     Worker STATUS.json path (e.g. .claude/agent-sessions/<id>/STATUS.json)
  --tmux-session NAME    Worker tmux session name (legacy / non-ORCA mode)
  --terminal-handle HANDLE
                         Worker ORCA terminal handle (ORCA mode, paired with --worktree-id)
  --worktree-id ID       Worker ORCA worktree id (ORCA mode, format: <repoId>::<path>)

Optional:
  --poll-interval N      Seconds between STATUS.json polls. Default: 5
  --max-wait SECONDS     Hard cap on total runtime. Default: 7200 (2h)
  --log-file PATH        Override SENTINEL_OUT.log path
  --pane-tail-lines N    Capture last N lines of tmux pane before kill. Default: 80, 0 disables
  --keep-tmux-on-terminal
                         Do NOT kill tmux / close terminal on terminal state (review phase use)

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
    --terminal-handle)  # v2.1（DEC-114）：ORCA 模式 worker session 句柄
      TERMINAL_HANDLE="$2"
      shift 2
      ;;
    --worktree-id)  # v2.1（DEC-114）：ORCA 模式 worktree id（用于 ORCA UI 同步）
      WORKTREE_ID="$2"
      shift 2
      ;;
    --dispatch-id)  # v2.1.1（Task-033）：ORCA supervised dispatch id（终态时 worker-release/stop）
      DISPATCH_ID="$2"
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

[ -n "$STATUS_FILE" ] || { echo "ERROR: --status-file is required" >&2; usage; exit 64; }
if [ -n "$TERMINAL_HANDLE" ]; then
  WORKER_SESSION_TYPE="orca_terminal"
  [ -n "$WORKTREE_ID" ] || { echo "ERROR: --terminal-handle requires --worktree-id" >&2; usage; exit 64; }
elif [ -n "$TMUX_SESSION" ]; then
  WORKER_SESSION_TYPE="tmux"
else
  echo "ERROR: must pass --tmux-session (legacy) or --terminal-handle + --worktree-id (ORCA mode)" >&2
  usage; exit 64
fi
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
  if [ "$WORKER_SESSION_TYPE" = "orca_terminal" ]; then
    # v2.1（DEC-114）：ORCA 模式用 orca terminal read 替代 tmux capture-pane。
    command -v orca >/dev/null 2>&1 || { log "SENTINEL_ORCA_UNAVAILABLE: orca CLI not found, skip pane capture"; return 0; }
    log "SENTINEL_ORCA_TERMINAL_TAIL: handle=$TERMINAL_HANDLE lines=$PANE_TAIL_LINES"
    orca terminal read --terminal "$TERMINAL_HANDLE" --limit "$PANE_TAIL_LINES" --json 2>/dev/null \
      | jq -r '(.result.terminal.tail // []) | .[]? // empty' 2>/dev/null \
      | redact_sensitive_stream \
      | while IFS= read -r line; do log "$line"; done
    return 0
  fi
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
    if [ "$WORKER_SESSION_TYPE" = "orca_terminal" ]; then
      log "SENTINEL_KEEP_ORCA_TERMINAL: handle=$TERMINAL_HANDLE"
    else
      log "SENTINEL_KEEP_TMUX: session=$TMUX_SESSION"
    fi
    return 0
  fi
  if [ "$WORKER_SESSION_TYPE" = "orca_terminal" ]; then
    # v2.1（DEC-114）：ORCA 模式用 orca terminal close 替代 tmux kill-session。
    if ! command -v orca >/dev/null 2>&1; then
      log "SENTINEL_ORCA_UNAVAILABLE: orca CLI not found, skip terminal close"
      return 0
    fi
    orca terminal close --terminal "$TERMINAL_HANDLE" 2>/dev/null || {
      log "SENTINEL_ORCA_TERMINAL_CLOSE_FAILED: handle=$TERMINAL_HANDLE"
      return 0
    }
    log "SENTINEL_ORCA_TERMINAL_CLOSED: handle=$TERMINAL_HANDLE"
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

# v2.1（DEC-114）：ORCA UI 同步——把 worker 终态写进 ORCA workspace-status + comment。
# 仅 ORCA 模式触发；ORCA 不可用 / 调用失败时静默返回（sentinel 不能因 ORCA 故障阻塞主监控）。
sync_orca_worktree_status() {
  local status_value="$1" comment="$2"
  [ "$WORKER_SESSION_TYPE" = "orca_terminal" ] || return 0
  command -v orca >/dev/null 2>&1 || { log "SENTINEL_ORCA_SYNC_SKIPPED: orca CLI not found"; return 0; }
  orca worktree set --worktree "id:$WORKTREE_ID" \
    --workspace-status "$status_value" \
    --comment "$comment" --json >/dev/null 2>&1 || {
    log "SENTINEL_ORCA_SYNC_FAILED: workspace_status=$status_value"
    return 0
  }
  log "SENTINEL_ORCA_SYNCED: workspace_status=$status_value"
}

# v2.1.1（Task-033）：ORCA supervised worker 终态释放。有 dispatch_id 时（--orca-supervised 注册过），
# done → worker-release（settled 释放 terminal）；failed/timeout → worker-stop（fence stop）。
# 无 dispatch_id（非 supervised 模式）/ ORCA 不可用 / 调用失败时静默返回（不阻塞 sentinel）。
sync_orca_supervised_release() {
  local action="$1"  # release / stop
  [ "$WORKER_SESSION_TYPE" = "orca_terminal" ] || return 0
  [ -n "$DISPATCH_ID" ] || return 0
  command -v orca >/dev/null 2>&1 || { log "SENTINEL_ORCA_SUPERVISED_SKIPPED: orca CLI not found"; return 0; }
  if [ "$action" = "release" ]; then
    orca orchestration worker-release --dispatch "$DISPATCH_ID" --json >/dev/null 2>&1 || {
      log "SENTINEL_ORCA_WORKER_RELEASE_FAILED: dispatch=$DISPATCH_ID（可能 worker 未 settled，忽略）"; return 0; }
    log "SENTINEL_ORCA_WORKER_RELEASED: dispatch=$DISPATCH_ID"
  else
    orca orchestration worker-stop --dispatch "$DISPATCH_ID" --json >/dev/null 2>&1 || {
      log "SENTINEL_ORCA_WORKER_STOP_FAILED: dispatch=$DISPATCH_ID（忽略）"; return 0; }
    log "SENTINEL_ORCA_WORKER_STOPPED: dispatch=$DISPATCH_ID"
  fi
}

# v2.1.1（Task-032）：查 ORCA worktree ps 里这个 worker 的 agent state。
# ORCA 检测是进程层客观信号（claude 在调什么工具、idle/working），独立于 STATUS.json
# （worker 自报告，可能 LLM 幻觉谎报 done）。双信号终态判定用：ORCA state=done/idle 且
# STATUS.json=done 才认为真终态；ORCA state=working 时即使 STATUS=done 也打 CONFLICT 不 exit。
#
# 输出（stdout）：agent state 字符串（working/idle/done/gone/unknown）；查询失败输出 "unknown"。
# 用 WORKTREE_ID（--worktree-id 传入）匹配 worktree ps 里的 agents。
orca_agent_state() {
  [ "$WORKER_SESSION_TYPE" = "orca_terminal" ] || { echo "non_orca"; return 0; }
  command -v orca >/dev/null 2>&1 || { echo "unknown"; return 0; }
  local ps_out agent_state
  ps_out=$(orca worktree ps --json 2>/dev/null) || { echo "unknown"; return 0; }
  # worktree ps 的字段是 .worktreeId（不是 .id）；agents[0].state 是 ORCA 检测的进程层状态
  # （working/idle/done/gone）。一个 ORCA worktree 通常一个 worker agent（spawn-worker 建独立 worktree）。
  agent_state=$(printf '%s' "$ps_out" | jq -r --arg wt "$WORKTREE_ID" '
    .result.worktrees[]?
    | select(.worktreeId == $wt)
    | .agents[0].state // "unknown"
  ' 2>/dev/null)
  echo "${agent_state:-unknown}"
}

if [ "$WORKER_SESSION_TYPE" = "orca_terminal" ]; then
  log "SENTINEL_START: status=$STATUS_FILE orca_terminal=$TERMINAL_HANDLE worktree=$WORKTREE_ID poll=${POLL_INTERVAL}s max_wait=${MAX_WAIT}s log=$LOG_FILE"
else
  log "SENTINEL_START: status=$STATUS_FILE tmux=$TMUX_SESSION poll=${POLL_INTERVAL}s max_wait=${MAX_WAIT}s log=$LOG_FILE"
fi

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
        # v2.1.1（Task-032）：ORCA 模式双信号终态判定。STATUS.json=done 但 ORCA agent state
        # 仍 working 时，可能是 worker LLM 谎报 done——打 CONFLICT 不 exit，等下次 poll 再判。
        # 非 ORCA 模式 / ORCA 查询失败时 orca_agent_state 返回 non_orca/unknown，跳过双信号直接终态。
        orca_state=$(orca_agent_state)
        if [ "$orca_state" = "working" ]; then
          log "SENTINEL_ORCA_STATUS_CONFLICT: STATUS=$status but ORCA agent_state=working (worker 可能谎报 done，不杀，等下次 poll)"
          # 不 sync、不 kill、不 exit；继续 poll（受 MAX_WAIT 总上限保护）
        else
          capture_pane_tail
          log "SENTINEL_TERMINAL: status=$status file=$STATUS_FILE orca_state=$orca_state"
          sync_orca_worktree_status "completed" "sentinel observed done at $(date -u +%FT%TZ) (status=$status, orca_state=$orca_state)"
          sync_orca_supervised_release "release"
          kill_tmux_if_requested
          exit 0
        fi
        ;;
      # Canonical failure terminals: failed | blocked | stopped. Defensive
      # synonyms added for the same reason as above. PM should still use
      # the canonical strings, but a worker that wrote "aborted" or
      # "cancelled" is also recognized as a non-success terminal.
      failed|blocked|stopped|aborted|cancelled)
        capture_pane_tail
        log "SENTINEL_TERMINAL: status=$status file=$STATUS_FILE"
        sync_orca_worktree_status "in-review" "sentinel observed non-success at $(date -u +%FT%TZ) (status=$status; PM review)"
        sync_orca_supervised_release "stop"
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
    sync_orca_worktree_status "in-review" "sentinel timeout ${elapsed}s (PM investigate)"
    sync_orca_supervised_release "stop"
    kill_tmux_if_requested
    exit 124
  fi

  sleep "$POLL_INTERVAL"
done
