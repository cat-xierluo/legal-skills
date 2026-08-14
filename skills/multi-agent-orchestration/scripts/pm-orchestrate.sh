#!/usr/bin/env bash
# Unified PM control plane for Orca supervised workers, Orca terminals and tmux.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=orca-runtime.sh
source "$SCRIPT_DIR/orca-runtime.sh"
# shellcheck source=provider-lease-root.sh
source "$SCRIPT_DIR/provider-lease-root.sh"

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
  settle      Force-settle a deadlocked supervised worker (Task-047R): verify the worker
               is dead, then use Orca worker-stop to fence + stop the exact Dispatch;
               --destroy additionally removes the exact Orca/Git worktree and files.
               Use only when worker process is dead but dispatch is stuck in `dispatched`.

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
  --destroy          With `settle`: additionally remove worktree/files (default: fence+stop only)
  --reason TEXT      Required audit reason for settle (persisted under the Git common dir)
  --force            With `settle`: override an inconclusive liveness gate after manual verification

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
REASON=""
FORCE=0
DESTROY=0

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
    --destroy) DESTROY=1; shift ;;
    --reason) REASON="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage; exit 64 ;;
  esac
done

case "$COMMAND" in
  run-create|send|read|peek|show|wait|ack|reply|release|retain|settle) ;;
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
ORCA_DISPATCH_ID=""
ORCA_COORDINATOR_HANDLE=""
ORCA_WORKTREE_ID=""
PROVIDER_LEASE_FILE=""
PROJECT_DIR=""
GIT_COMMON_DIR=""
SETTLE_AUDIT_FILE=""

resolve_worker() {
  [ -f "$METADATA" ] || {
    echo "ERROR: METADATA not found: $METADATA" >&2
    exit 64
  }
  WORKER_HANDLE=$(jq -r '.session.orca.terminal_handle // empty' "$METADATA")
  ORCA_RUN_ID=$(jq -r '.session.orca.supervised.run_id // empty' "$METADATA")
  ORCA_DISPATCH_ID=$(jq -r '.session.orca.supervised.dispatch_id // empty' "$METADATA")
  ORCA_COORDINATOR_HANDLE=$(jq -r '.session.orca.supervised.coordinator_handle // empty' "$METADATA")
  ORCA_WORKTREE_ID=$(jq -r '.session.orca.worktree_id // empty' "$METADATA")
  PROVIDER_LEASE_FILE=$(jq -r '.runtime.provider_lease.file // empty' "$METADATA")
  PROJECT_DIR=$(jq -r '.project // empty' "$METADATA")
  if [ -n "$ORCA_DISPATCH_ID" ]; then
    WORKER_MODE="orca_supervised"
  elif [ -n "$WORKER_HANDLE" ]; then
    WORKER_MODE="orca_terminal"
  else
    WORKER_MODE="tmux"
    WORKER_HANDLE="$SESSION"
  fi
}

git_common_dir_for_path() {
  local path="$1" common
  common=$(git -C "$path" rev-parse --git-common-dir 2>/dev/null) || return 1
  case "$common" in
    /*) ;;
    *) common="$path/$common" ;;
  esac
  (cd "$common" 2>/dev/null && pwd -P)
}

resolve_project_identity() {
  [ -n "$PROJECT_DIR" ] || {
    echo "ERROR: METADATA.project is missing; refusing repository mutation" >&2
    return 2
  }
  [ -d "$PROJECT_DIR" ] || {
    echo "ERROR: METADATA.project is not a directory: $PROJECT_DIR" >&2
    return 2
  }

  local project_top project_common worktree_common
  project_top=$(git -C "$PROJECT_DIR" rev-parse --show-toplevel 2>/dev/null) || {
    echo "ERROR: METADATA.project is not a Git worktree: $PROJECT_DIR" >&2
    return 2
  }
  project_top=$(cd "$project_top" && pwd -P)
  project_common=$(git_common_dir_for_path "$project_top") || {
    echo "ERROR: cannot resolve Git common dir for project: $project_top" >&2
    return 2
  }
  worktree_common=$(git_common_dir_for_path "$WORKTREE") || {
    echo "ERROR: cannot resolve Git common dir for worker worktree: $WORKTREE" >&2
    return 2
  }
  [ "$project_common" = "$worktree_common" ] || {
    echo "ERROR: METADATA.project and worker worktree belong to different repositories" >&2
    return 2
  }

  PROJECT_DIR="$project_top"
  GIT_COMMON_DIR="$project_common"
  SETTLE_AUDIT_FILE="$GIT_COMMON_DIR/orchestration/settle-audit.ndjson"
}

write_settle_audit() {
  local event="$1" detail="${2:-}" timestamp audit_dir record
  [ -n "$SETTLE_AUDIT_FILE" ] || return 2
  audit_dir=$(dirname "$SETTLE_AUDIT_FILE")
  umask 077
  mkdir -p "$audit_dir" || return 2
  timestamp=$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || printf '%s' 'unknown-time')
  record=$(jq -cn \
    --arg timestamp "$timestamp" \
    --arg event "$event" \
    --arg dispatch_id "$ORCA_DISPATCH_ID" \
    --arg session "$SESSION" \
    --arg worktree "$WORKTREE" \
    --arg reason "$REASON" \
    --arg detail "$detail" \
    --argjson destroy "${DESTROY:-0}" \
    --argjson force "${FORCE:-0}" \
    '{timestamp:$timestamp,event:$event,dispatch_id:$dispatch_id,session:$session,worktree:$worktree,destroy:($destroy == 1),force:($force == 1),reason:$reason,detail:$detail}') || return 2
  printf '%s\n' "$record" >> "$SETTLE_AUDIT_FILE" || return 2
  echo "PM_ORCHESTRATE_SETTLE_AUDIT: $SETTLE_AUDIT_FILE event=$event" >&2
}

ensure_coordinator_binding() {
  [ "$WORKER_MODE" = "orca_supervised" ] || return 0
  [ -n "$ORCA_RUN_ID" ] || {
    echo "ERROR: supervised METADATA is missing run_id" >&2
    return 2
  }
  orca_runtime_init
  local use_out rebound_handle
  use_out=$(orca_cli orchestration run-use --id "$ORCA_RUN_ID" --json 2>&1) || {
    echo "ERROR: cannot bind the invoking PM terminal to Run $ORCA_RUN_ID: $use_out" >&2
    echo "RECOVERY: use read-only show/dispatch-show for inspection; do not ack or clean an active Dispatch" >&2
    return 2
  }
  rebound_handle=$(printf '%s' "$use_out" | jq -r '.result.run.coordinator_handle // .result.run.coordinatorHandle // empty')
  [ -n "$rebound_handle" ] || {
    echo "ERROR: run-use succeeded without a coordinator handle" >&2
    return 2
  }
  if [ "$rebound_handle" != "$ORCA_COORDINATOR_HANDLE" ]; then
    ORCA_COORDINATOR_HANDLE="$rebound_handle"
    local tmp_meta
    tmp_meta=$(mktemp)
    if jq --arg coordinator "$rebound_handle" \
        '.session.orca.supervised.coordinator_handle = $coordinator' "$METADATA" > "$tmp_meta" \
        && mv "$tmp_meta" "$METADATA"; then
      echo "PM_ORCHESTRATE_COORDINATOR_REBOUND: run=$ORCA_RUN_ID handle=$rebound_handle" >&2
    else
      rm -f "$tmp_meta"
      echo "WARN: Run rebound but METADATA coordinator handle could not be refreshed" >&2
    fi
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
  case "$text" in *'```'*|*'`'*|*'$'*|*'|'*) return 0 ;; esac
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
    ensure_coordinator_binding || exit 2
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
    ensure_coordinator_binding || exit 2
    # A timeout is a liveness checkpoint, not failure. The JSON remains unacknowledged.
    orca_cli orchestration check --wait \
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
  ensure_coordinator_binding || exit 2
  orca_cli orchestration check --ack "$DELIVERY_ID" --json
}

cmd_reply() {
  [ "$WORKER_MODE" = "orca_supervised" ] || { echo "ERROR: reply requires an Orca supervised worker" >&2; exit 64; }
  [ -n "$MESSAGE_ID" ] || { echo "ERROR: reply requires --message-id" >&2; exit 64; }
  local text
  text=$(load_text)
  ensure_coordinator_binding || exit 2
  orca_cli orchestration reply --id "$MESSAGE_ID" --body "$text" --json
}

cmd_account() {
  [ "$WORKER_MODE" = "orca_supervised" ] || { echo "ERROR: $COMMAND requires an Orca supervised worker" >&2; exit 64; }
  ensure_coordinator_binding || exit 2
  local result
  result=$(orca_cli orchestration "worker-$COMMAND" --dispatch "$ORCA_DISPATCH_ID" --json) || return $?
  printf '%s\n' "$result"
  if [ "$COMMAND" = "release" ] && [ -n "$PROVIDER_LEASE_FILE" ]; then
    local workers terminal_state lease_root
    workers=$(orca_cli orchestration worker-list --json 2>/dev/null || echo '{}')
    terminal_state=$(printf '%s' "$workers" | jq -r --arg dispatch "$ORCA_DISPATCH_ID" '
      [(.result.workers // [])[]?
        | select((.dispatch_id // .dispatchId // .id) == $dispatch)
        | (.terminal_state // .terminalState // .accounting_state // .accountingState // "unknown")][0]
      // "unknown"
    ')
    if [ "$terminal_state" = "released" ]; then
      lease_root=$(provider_lease_root_for_project "$WORKTREE") || {
        echo "ERROR: cannot derive trusted provider lease root" >&2
        return 2
      }
      python3 "$SCRIPT_DIR/provider-lease.py" release \
        --root "$lease_root" \
        --lease-file "$PROVIDER_LEASE_FILE" --session "$SESSION" \
        --resource-settled --orca-cli "$ORCA_CLI_BIN" >/dev/null || {
        echo "ERROR: Orca terminal released but provider lease release failed" >&2
        return 2
      }
      echo "PM_ORCHESTRATE_PROVIDER_LEASE_RELEASED: session=$SESSION" >&2
    else
      echo "PM_ORCHESTRATE_PROVIDER_LEASE_RETAINED: terminal_state=$terminal_state; close/account resource before releasing quota" >&2
    fi
  fi
}

# Task-047R：supervised dispatch 死锁兜底。
#
# 与旧实现的核心区别：旧实现手撸 "terminal stop + lease release + worktree rm"，
# 且 liveness gate 字段名 `.result.workerSession` 在真 Orca 响应里不存在，
# 等同于无门槛。当前实现只使用精确 Dispatch 的官方 lifecycle mutation。
#
# v2 设计：
# - 走 Orca 官方 lifecycle：worker-stop 原子 fence+stop；失败时 worker-abandon 仅作
#   非破坏性 fence 兜底，随后立即失败并保留 worktree。
#   默认不动文件（METADATA 保留，PM 后续可跑 clean-worktree 完整清理）。
# - --destroy 才动文件（symlink unlink + dirty 检查 + lease release + Orca worktree rm
#   + exact Git fallback）。审计在 Git common dir，不依赖 Session Context 存活。
# - liveness gate 用真字段 `.result.observation.status`（exited 即 OK）和
#   `.result.worker.state`（succeeded/failed/stopped 即 OK），任一失败保守拒绝。
# - 任何资源动作 fail-loud（禁止吞 stderr/stdout）。
#
# 测试：scripts/test-settle-liveness.sh 用真 Orca worker-show response fixture 覆盖
# exited/active/missing-field 三场景。
settle_liveness_check() {
  # $1 = worker-show JSON string. Exits 0 if worker dead, 2 if active or unparseable.
  local show_json="$1"
  local force="${2:-0}"
  if [ -z "$show_json" ]; then
    if [ "$force" -ne 1 ]; then
      echo "REFUSED: worker-show returned empty (cannot determine liveness)" >&2
      exit 2
    fi
    echo "WARN: worker-show empty but --force given; assuming DEAD" >&2
    return 0
  fi
  local obs_status worker_state
  # script runs under `set -euo pipefail`; locally disable to keep PARSE_ERROR fallback
  # reachable and produce the intended diagnostic instead of silent exit.
  set +e +o pipefail
  obs_status=$(printf '%s' "$show_json" | jq -r '.result.observation.status // "ABSENT"' 2>/dev/null)
  worker_state=$(printf '%s' "$show_json" | jq -r '.result.worker.state // "ABSENT"' 2>/dev/null)
  set -e -o pipefail
  obs_status=${obs_status:-PARSE_ERROR}
  worker_state=${worker_state:-PARSE_ERROR}
  # Fail closed on every combination except a pair of known-dead signals. Unknown future
  # states must not silently inherit deletion authority.
  case "$obs_status" in
    exited|missing) ;;
    *)
      if [ "$force" -ne 1 ]; then
        echo "REFUSED: observation.status=$obs_status is not a known-dead state (expected exited|missing)" >&2
        exit 2
      fi
      echo "WARN: observation.status=$obs_status is inconclusive; --force overrides" >&2
      ;;
  esac
  case "$worker_state" in
    succeeded|failed|stopped) ;;
    *)
      if [ "$force" -ne 1 ]; then
        echo "REFUSED: worker.state=$worker_state is not a known-dead state (expected succeeded|failed|stopped)" >&2
        exit 2
      fi
      echo "WARN: worker.state=$worker_state is inconclusive; --force overrides" >&2
      ;;
  esac
  return 0
}

# settle_destroy_worktree: 物理清理段。Orca 先删除它拥有的 worktree；若旧 runtime
# 只删资源未清 Git registration，再对完整路径精确匹配后执行 Git fallback。
settle_destroy_worktree() {
  local worktree_path="$1" dispatch_id="$2"

  # 1. symlink unlink（MAJOR 3：spawn-worker-deps 注入的 node_modules 软链）。
  if [ -L "$worktree_path/node_modules" ]; then
    if rm -f "$worktree_path/node_modules"; then
      echo "PM_ORCHESTRATE_SETTLE_DEPS_UNLINKED: node_modules symlink"
    else
      echo "ERROR: failed to unlink node_modules symlink: $worktree_path/node_modules" >&2
      return 2
    fi
  fi

  # 2. dirty 检查（MAJOR 5）。默认拒绝；--destroy 隐含 --force-remove-dirty
  #   （settle 的本意就是"进程死了，磁盘上有未提交工作也无所谓了"）。
  if git -C "$worktree_path" rev-parse --git-dir >/dev/null 2>&1; then
    local dirty_count
    dirty_count=$(git -C "$worktree_path" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
    echo "PM_ORCHESTRATE_SETTLE_DIRTY: $dirty_count (settle --destroy accepts dirty; clean-worktree refused this)"
    if [ "$dirty_count" != "0" ]; then
      echo "PM_ORCHESTRATE_SETTLE_DIRTY_NOTE: worker output not preserved by --destroy; back up $worktree_path if needed"
    fi
  fi

  # 3. provider lease release。终端已由 worker-stop 结算；先释放额度，失败时保留
  # worktree 供人工恢复，不进入破坏性文件删除。
  if [ -n "$PROVIDER_LEASE_FILE" ]; then
    local lease_root
    lease_root=$(provider_lease_root_for_project "$PROJECT_DIR" 2>/dev/null) || lease_root=""
    if [ -n "$lease_root" ]; then
      if python3 "$SCRIPT_DIR/provider-lease.py" release \
          --root "$lease_root" \
          --lease-file "$PROVIDER_LEASE_FILE" --session "$SESSION" \
          --resource-settled --orca-cli "$ORCA_CLI_BIN"; then
        echo "PM_ORCHESTRATE_SETTLE_LEASE_RELEASED: session=$SESSION"
      else
        echo "ERROR: provider lease release failed (worktree retained): $PROVIDER_LEASE_FILE" >&2
        return 2
      fi
    else
      echo "ERROR: cannot derive trusted provider lease root for $PROJECT_DIR (worktree retained)" >&2
      return 2
    fi
  fi

  # 4. Orca owns Orca-managed worktree teardown. ORCA_WORKTREE_ID was loaded before
  # deleting the Session Context, so cleanup never rereads a vanished METADATA file.
  if [ -n "$dispatch_id" ]; then
    if [ -z "$ORCA_WORKTREE_ID" ]; then
      echo "ERROR: no orca worktree_id in METADATA; refusing --destroy" >&2
      return 2
    elif orca_cli worktree rm --worktree "id:$ORCA_WORKTREE_ID" --force --json; then
      echo "PM_ORCHESTRATE_SETTLE_ORCA_WT_REMOVED: $ORCA_WORKTREE_ID"
    else
      echo "ERROR: orca worktree rm failed: $ORCA_WORKTREE_ID" >&2
      return 2
    fi
  fi

  # 5. Exact Git fallback. Orca normally removes the checkout and registration; a
  # fake/older runtime may leave the Git worktree registered, so match the full path.
  if git -C "$PROJECT_DIR" worktree list --porcelain 2>/dev/null | awk -v target="$worktree_path" '
      /^worktree / { path=$0; sub(/^worktree /, "", path); if (path == target) found=1 }
      END { exit(found ? 0 : 1) }
    '; then
    if git -C "$PROJECT_DIR" worktree remove --force "$worktree_path"; then
      echo "PM_ORCHESTRATE_SETTLE_GIT_WT_REMOVED: $worktree_path"
    else
      echo "ERROR: git worktree remove failed: $worktree_path" >&2
      return 2
    fi
  fi

  if [ -e "$worktree_path" ]; then
    echo "ERROR: --destroy finished lifecycle cleanup but worktree path still exists: $worktree_path" >&2
    return 2
  fi
}

cmd_settle() {
  [ "$WORKER_MODE" = "orca_supervised" ] || { echo "ERROR: settle requires an Orca supervised worker (dispatch deadlock bypass)" >&2; exit 64; }

  # --force/--destroy/--reason 由全局 args 解析（FORCE/DESTROY/REASON），
  # cmd_settle 直接读全局变量。$@ 在 dispatch 时为空（全局 while 已消耗）。
  local settle_force="${FORCE:-0}" settle_destroy="${DESTROY:-0}" settle_reason="${REASON:-}"

  [ -n "$settle_reason" ] || { echo "ERROR: settle requires --reason (audit)" >&2; exit 64; }
  [ -n "$ORCA_DISPATCH_ID" ] || { echo "ERROR: settle: missing dispatch_id in METADATA" >&2; exit 64; }

  resolve_project_identity || exit 2
  orca_runtime_init
  ensure_coordinator_binding || exit 2

  local show_json session_context
  session_context="$WORKTREE/.claude/agent-sessions/$SESSION"

  echo "PM_ORCHESTRATE_SETTLE_START: dispatch=$ORCA_DISPATCH_ID worktree=$ORCA_WORKTREE_ID destroy=$settle_destroy force=$settle_force reason=$settle_reason"
  write_settle_audit start "liveness check pending" || {
    echo "ERROR: cannot persist settle audit under Git common dir; refusing mutation" >&2
    exit 2
  }

  # Step 1: liveness gate (BLOCKER 1: 用真字段)。
  set +e
  show_json=$(orca_cli orchestration worker-show --dispatch "$ORCA_DISPATCH_ID" --json 2>&1)
  local show_rc=$?
  set -e
  if [ "$show_rc" -ne 0 ]; then
    if [ "$settle_force" -ne 1 ]; then
      echo "REFUSED: worker-show failed (rc=$show_rc, cannot determine liveness); re-run with --force" >&2
      exit 2
    fi
    echo "WARN: worker-show failed (rc=$show_rc) but --force given; assuming DEAD" >&2
    show_json=""
  fi
  settle_liveness_check "$show_json" "$settle_force"

  # Step 2: worker-stop is the current Orca atomic fence+stop operation. If it
  # fails, make one non-destructive worker-abandon attempt to fence uncertainty,
  # but never continue into --destroy.
  set +e
  if orca_cli orchestration worker-stop --dispatch "$ORCA_DISPATCH_ID" --json; then
    local stop_rc=0
    echo "PM_ORCHESTRATE_SETTLE_STOPPED: dispatch=$ORCA_DISPATCH_ID"
  else
    local stop_rc=$?
  fi
  set -e
  if [ "$stop_rc" -ne 0 ]; then
    set +e
    orca_cli orchestration worker-abandon --dispatch "$ORCA_DISPATCH_ID" --json
    local abandon_rc=$?
    set -e
    write_settle_audit stop_failed "worker-stop rc=$stop_rc; worker-abandon rc=$abandon_rc" || true
    echo "ERROR: worker-stop failed (rc=$stop_rc); dispatch may be fenced by worker-abandon, but worktree is retained" >&2
    exit 2
  fi
  write_settle_audit stopped "worker-stop fenced and stopped the Dispatch" || {
    echo "ERROR: cannot persist post-stop audit; worktree retained" >&2
    exit 2
  }

  # Step 3: --destroy 才动文件。默认只 fence + stop, 提示 PM 后续跑 clean-worktree。
  if [ "$settle_destroy" -eq 1 ]; then
    echo "PM_ORCHESTRATE_SETTLE_DESTROY_START: cleaning worktree/files"
    settle_destroy_worktree "$WORKTREE" "$ORCA_DISPATCH_ID" || exit 2
    write_settle_audit destroyed "Orca/Git worktree removed" || {
      echo "ERROR: worktree removed but final audit write failed: $SETTLE_AUDIT_FILE" >&2
      exit 2
    }
    echo "PM_ORCHESTRATE_SETTLE_DESTROYED: see PM_ORCHESTRATE_SETTLE_* lines above"
  else
    echo "PM_ORCHESTRATE_SETTLE_FENCED_ONLY: dispatch fenced + terminal stopped. Run \`clean-worktree.sh --execute --force-remove-dirty\` to clean worktree/files. METADATA preserved at $session_context."
  fi
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
  settle) cmd_settle "$@" ;;
esac
