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
  settle      Force-settle a deadlocked supervised worker (Task-047 v2): fence dispatch
               via Orca worker-abandon + stop terminal via worker-stop (default, safe);
               --destroy additionally removes worktree/files (uses clean-worktree path).
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
  --reason TEXT      Required audit reason for settle (persisted to SETTLE_AUDIT.log)

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
ORCA_TASK_ID=""
ORCA_DISPATCH_ID=""
PROVIDER_LEASE_FILE=""

resolve_worker() {
  [ -f "$METADATA" ] || {
    echo "ERROR: METADATA not found: $METADATA" >&2
    exit 64
  }
  WORKER_HANDLE=$(jq -r '.session.orca.terminal_handle // empty' "$METADATA")
  ORCA_RUN_ID=$(jq -r '.session.orca.supervised.run_id // empty' "$METADATA")
  ORCA_TASK_ID=$(jq -r '.session.orca.supervised.task_id // empty' "$METADATA")
  ORCA_DISPATCH_ID=$(jq -r '.session.orca.supervised.dispatch_id // empty' "$METADATA")
  PROVIDER_LEASE_FILE=$(jq -r '.runtime.provider_lease.file // empty' "$METADATA")
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

# Task-047 v2：supervised dispatch 死锁兜底。
#
# 与 v1 的核心区别：v1 手撸 "terminal stop + lease release + worktree rm + rm -rf"，
# 没用 Orca 官方 lifecycle 命令（worker-abandon fence / worker-stop stop /
# worker-release release），且 liveness gate 字段名 `.result.workerSession` 在真 Orca
# 响应里不存在（永远 DEAD 等于无门槛），reviewer 抓 BLOCKER 1+2。
#
# v2 设计：
# - 走 Orca 官方 lifecycle：worker-abandon fence dispatch → worker-stop 停 terminal。
#   默认不动文件（METADATA 保留，PM 后续可跑 clean-worktree 完整清理）。
# - --destroy 才动文件（symlink unlink + dirty 检查 + git worktree remove + lease
#   release + orca worktree rm + session_context 清），内联 clean-worktree.sh:282-340。
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
  # gate 逻辑：拒绝"活"信号（active/input_accepted），允许"死/退出"信号
  # （exited/missing/succeeded/failed/stopped），ABSENT（字段缺失/schema 变）保守拒绝。
  # 注：completed dispatch 的 observation.status 在 GC 后是 "missing"（非 exited），
  # 死锁 dispatch（worker 死、dispatch dispatched）的 observation 未真测，但非 active
  # 即视为可 settle——gate 目的是"别误杀活 worker"，活 worker 的 observation 必为 active。
  if [ "$obs_status" = "active" ] || [ "$obs_status" = "input_accepted" ] \
     || [ "$worker_state" = "active" ] || [ "$worker_state" = "input_accepted" ]; then
    if [ "$force" -ne 1 ]; then
      echo "REFUSED: observation.status=$obs_status worker.state=$worker_state (worker still active); confirm worker process is dead and re-run with --force" >&2
      exit 2
    fi
    echo "WARN: liveness check suggests worker may be active (obs=$obs_status, state=$worker_state); --force overrides" >&2
    return 0
  fi
  if [ "$obs_status" = "ABSENT" ] && [ "$worker_state" = "ABSENT" ]; then
    if [ "$force" -ne 1 ]; then
      echo "REFUSED: observation.status and worker.state both ABSENT (schema changed or unparseable); re-run with --force after manual verification" >&2
      exit 2
    fi
    echo "WARN: both fields ABSENT but --force given; assuming DEAD" >&2
  fi
  return 0
}

# settle_destroy_worktree: 物理清理段。顺序与 clean-worktree.sh:282-340 **故意偏离**——
# settle 先 git worktree remove（git 拥有文件系统），再 orca worktree rm；clean-worktree
# 先 orca worktree rm 再 git。两侧因所有权语义不同而顺序不同，非同步关系。MAJOR 5/3 修复。
settle_destroy_worktree() {
  local worktree_path="$1" dispatch_id="$2"
  local session_context="$worktree_path/.claude/agent-sessions/$SESSION"

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

  # 3. git worktree remove（MAJOR 5：spawn-worker 时主仓 git worktree add 注册过）。
  if git -C "$PROJECT_DIR" worktree list --porcelain 2>/dev/null | grep -qF "^worktree $worktree_path"; then
    if git -C "$PROJECT_DIR" worktree remove --force "$worktree_path"; then
      echo "PM_ORCHESTRATE_SETTLE_GIT_WT_REMOVED: $worktree_path"
    else
      echo "ERROR: git worktree remove failed: $worktree_path" >&2
      return 2
    fi
  fi

  # 4. orca worktree rm（settle --destroy 完整清理路径）。
  if [ -n "$dispatch_id" ]; then
    local wt_id
    wt_id=$(jq -r '.session.orca.worktree_id // empty' "$METADATA" 2>/dev/null)
    if [ -z "$wt_id" ]; then
      echo "WARN: no orca worktree_id in METADATA; skipping orca worktree rm" >&2
    elif orca_cli worktree rm --worktree "id:$wt_id" --force --json; then
      echo "PM_ORCHESTRATE_SETTLE_ORCA_WT_REMOVED: $wt_id"
    else
      echo "ERROR: orca worktree rm failed: $wt_id" >&2
      return 2
    fi
  fi

  # 5. provider lease release（MAJOR 4：fail-loud，不吞 stderr）。
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
        echo "ERROR: provider lease release failed (manual cleanup needed: $PROVIDER_LEASE_FILE)" >&2
        return 2
      fi
    else
      echo "ERROR: cannot derive trusted provider lease root for $PROJECT_DIR (manual lease cleanup needed)" >&2
      return 2
    fi
  fi

  # 6. session_context 清理。
  if [ -d "$session_context" ]; then
    if rm -rf "$session_context"; then
      echo "PM_ORCHESTRATE_SETTLE_SESSION_CONTEXT_REMOVED: $session_context"
    else
      echo "WARN: session context cleanup non-zero (not blocking): $session_context" >&2
    fi
  fi
}

cmd_settle() {
  [ "$WORKER_MODE" = "orca_supervised" ] || { echo "ERROR: settle requires an Orca supervised worker (dispatch deadlock bypass)" >&2; exit 64; }

  # --force/--destroy/--reason 由全局 args 解析（FORCE/DESTROY/REASON），
  # cmd_settle 直接读全局变量。$@ 在 dispatch 时为空（全局 while 已消耗）。
  local settle_force="${FORCE:-0}" settle_destroy="${DESTROY:-0}" settle_reason="${REASON:-}"

  [ -n "$settle_reason" ] || { echo "ERROR: settle requires --reason (audit)" >&2; exit 64; }
  [ -n "$ORCA_DISPATCH_ID" ] || { echo "ERROR: settle: missing dispatch_id in METADATA" >&2; exit 64; }

  orca_runtime_init

  local worktree_id show_json session_context
  worktree_id=$(jq -r '.session.orca.worktree_id // empty' "$METADATA")
  session_context="$WORKTREE/.claude/agent-sessions/$SESSION"

  echo "PM_ORCHESTRATE_SETTLE_START: dispatch=$ORCA_DISPATCH_ID worktree=$worktree_id destroy=$settle_destroy force=$settle_force reason=$settle_reason"
  # M2: --reason 持久化到 SETTLE_AUDIT.log（审计可追溯）
  printf '%s dispatch=%s session=%s destroy=%s force=%s reason=%s\n'     "$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || echo 'unknown-time')"     "$ORCA_DISPATCH_ID" "$SESSION" "$settle_destroy" "$settle_force" "$settle_reason"     >> "$SESSION_CONTEXT/SETTLE_AUDIT.log" 2>/dev/null || echo "WARN: cannot write SETTLE_AUDIT.log (read-only context?)" >&2

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

  # Step 2: worker-abandon fence dispatch (BLOCKER 2: 保留 METADATA)。
  if orca_cli orchestration worker-abandon --dispatch "$ORCA_DISPATCH_ID" --json; then
    echo "PM_ORCHESTRATE_SETTLE_FENCED: dispatch=$ORCA_DISPATCH_ID"
  else
    echo "ERROR: worker-abandon failed; dispatch NOT fenced, aborting settle" >&2
    exit 2
  fi

  # Step 3: worker-stop 停 terminal（已 fence, stop 失败 WARN 不阻塞）。
  # set +e 保护：worker-stop 失败不应击穿脚本（已 fence，terminal 自然回收）。
  set +e
  if orca_cli orchestration worker-stop --dispatch "$ORCA_DISPATCH_ID" --json; then
    echo "PM_ORCHESTRATE_SETTLE_STOPPED: dispatch=$ORCA_DISPATCH_ID"
  else
    echo "WARN: worker-stop failed (already stopped?)" >&2
  fi
  set -e

  # Step 4: --destroy 才动文件。默认只 fence + stop, 提示 PM 后续跑 clean-worktree。
  if [ "$settle_destroy" -eq 1 ]; then
    echo "PM_ORCHESTRATE_SETTLE_DESTROY_START: cleaning worktree/files"
    settle_destroy_worktree "$WORKTREE" "$ORCA_DISPATCH_ID" || exit 2
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
