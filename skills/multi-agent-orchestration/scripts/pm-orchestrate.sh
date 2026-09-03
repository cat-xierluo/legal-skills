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
  pm-orchestrate.sh pr-audit --worktree PATH --base-ref main --head-ref BRANCH --head-sha SHA [--task-id ID] [--agent-id ID]
  pm-orchestrate.sh <command> --worktree PATH --session NAME [options]

Commands:
  run-create  Create and bind one Orca Run for a Wave
  pr-audit    Read-only classification of open PRs for one frozen worker head
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
  reauthorize Refresh a live supervised worker's spawn authorization snapshot
               (Task-058): guard 的 WORKER_INSTALL_AUTH_B64 内联在 launch.sh 且随进程
               环境固化，运行中改授权文件不生效。本命令合并 --allow-cmd 进授权文件、
               重写 launch.sh B64、把 failed/blocked Task 复位 ready、在同一 worktree
               创建新终端并复用 Task 重注册（worker-start 重注入）、改写 METADATA 路由、
               可选发 --resume-text、最后关闭旧终端句柄。未提交的工作区改动全部保留。
               (Task-081) task 仍 dispatched（如 worker 卡 escalation/question 等待）时
               不再被 TASK_REUSED 拒绝：先把 --resume-text 作为 reply 消费等待，再走
               同一链路；若注册仍被单活 fencing 拒绝，回滚新终端（不双活）并输出
               runbook #18 manual-recovery 指引。新终端建立后任何中间失败都会先关新
               终端、保留旧终端（重复调用不累积终端）。
  quota-park  Quota-stall recovery handoff (v2.11.0 P0-③)：精确 fence + stop 旧
               supervised Dispatch（worker-stop），完整保留 worktree/session/checkpoint，
               释放 METADATA 记录的 provider lease，之后同 worktree 可用新 session id
               重启或切 provider（重启仍要过 spawn-worker 的 quota preflight）。
               任何一步失败立即中止：不释放 lease、不写 marker，绝不产生
               "worker 活着 + 额度已放" 的双活窗口。需要 --reason；worker 仍活/
               不确定时只有 --force（PM 人工确认配额卡死）可停靠。

Common:
  --worktree PATH   Worker worktree path
  --session NAME    spawn-worker session id
  --text TEXT       Prompt, guidance or reply body
  --prompt-file P   Read prompt/guidance from a file
  --lines N         Read limit (default: 50); --limit accepted as an alias (orca terminal read spelling)
  --cursor VALUE    Opaque worker-read cursor
  --timeout SEC     Wait timeout (default: 60)
  --delivery-id ID  Delivery to acknowledge
  --message-id ID   Question message to answer
  --objective TEXT  Run objective
  --destroy          With `settle`: additionally remove worktree/files (default: fence+stop only)
  --reason TEXT      Required audit reason for settle (persisted under the Git common dir)
  --force            With `settle`: override an inconclusive liveness gate after manual verification
  --allow-cmd CMD    With `reauthorize`: append one exact shell command to the allowlist
                     (repeatable; merged into INSTALL_AUTHORIZATION.json before B64 refresh)
  --resume-text TEXT With `reauthorize`: short continuation note sent to the new terminal
                     after worker-start re-injection (e.g. progress preserved, continue from X)
  --task-id ID       With `reauthorize`: task override when METADATA lacks task_id
                     With `pr-audit`: optional task ownership marker
  --agent-id ID      With `pr-audit`: optional Agent ownership marker
  --base-ref NAME    With `pr-audit`: expected PR base (default: main)
  --head-ref NAME    With `pr-audit`: exact worker head branch
  --head-sha SHA     With `pr-audit`: frozen full worker commit id

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
ALLOW_CMDS=()
REAUTH_RESUME_TEXT=""
REAUTH_TASK_ID=""
PR_BASE_REF="main"
PR_HEAD_REF=""
PR_HEAD_SHA=""
PR_TASK_ID=""
PR_AGENT_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --worktree) WORKTREE="$2"; shift 2 ;;
    --session) SESSION="$2"; shift 2 ;;
    --text) SEND_TEXT="$2"; shift 2 ;;
    --prompt-file) PROMPT_FILE="$2"; shift 2 ;;
    --lines|--limit) LINES="$2"; shift 2 ;;  # --limit 是 orca terminal read 的参数名，此处接受两者
    --cursor) CURSOR="$2"; shift 2 ;;
    --timeout) WAIT_TIMEOUT="$2"; shift 2 ;;
    --delivery-id) DELIVERY_ID="$2"; shift 2 ;;
    --message-id) MESSAGE_ID="$2"; shift 2 ;;
    --objective) OBJECTIVE="$2"; shift 2 ;;
    --destroy) DESTROY=1; shift ;;
    --reason) REASON="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    --allow-cmd) ALLOW_CMDS+=("$2"); shift 2 ;;
    --resume-text) REAUTH_RESUME_TEXT="$2"; shift 2 ;;
    --task-id) REAUTH_TASK_ID="$2"; PR_TASK_ID="$2"; shift 2 ;;
    --agent-id) PR_AGENT_ID="$2"; shift 2 ;;
    --base-ref) PR_BASE_REF="$2"; shift 2 ;;
    --head-ref) PR_HEAD_REF="$2"; shift 2 ;;
    --head-sha) PR_HEAD_SHA="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage; exit 64 ;;
  esac
done

case "$COMMAND" in
  run-create|pr-audit|send|read|peek|show|wait|ack|reply|release|retain|settle|reauthorize|quota-park) ;;
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
[ "$COMMAND" != "pr-audit" ] || {
  [ -n "$PR_HEAD_REF" ] && [ -n "$PR_HEAD_SHA" ] || {
    echo "ERROR: pr-audit requires --head-ref and --head-sha" >&2
    exit 64
  }
  audit_args=(
    --repo "$WORKTREE" --base-ref "$PR_BASE_REF"
    --head-ref "$PR_HEAD_REF" --head-sha "$PR_HEAD_SHA"
  )
  [ -z "$PR_TASK_ID" ] || audit_args+=(--task-id "$PR_TASK_ID")
  [ -z "$PR_AGENT_ID" ] || audit_args+=(--agent-id "$PR_AGENT_ID")
  audit_json=$(python3 "$SCRIPT_DIR/pr-audit.py" "${audit_args[@]}") || exit $?
  audit_decision=$(printf '%s' "$audit_json" | jq -er '.decision') || {
    echo "ERROR: pr-audit helper returned invalid JSON" >&2
    exit 2
  }
  audit_exact=$(printf '%s' "$audit_json" | jq -er '.counts.exact')
  audit_suspected=$(printf '%s' "$audit_json" | jq -er '.counts.suspected')
  audit_unrelated=$(printf '%s' "$audit_json" | jq -er '.counts.unrelated')
  echo "PM_ORCHESTRATE_PR_AUDIT: decision=$audit_decision exact=$audit_exact suspected=$audit_suspected unrelated=$audit_unrelated" >&2
  printf '%s\n' "$audit_json"
  exit 0
}
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

# v2.11.0（P0-③，2026-09 复盘修复）：配额停滞恢复交接（quota-park）。
#
# 背景：worker 撞 provider 配额判停线/冻结时，PM 需要"先精确 fence 旧 dispatch，
# 再解锁同 worktree 重启或切 provider"。此前兜底只有 settle（面向死锁，--destroy
# 会删 worktree）或手工 provider-lease release——后者在 worker 仍活时释放额度会
# 造成双活（两个 worker 消费同一 provider lane）。
#
# 与 settle 的差异：只做恢复交接，绝不删除 worktree/session/checkpoint：
#   Step 1  liveness gate（复用 settle 的真字段检查）；active/不确定时仅 --force
#           可继续，表示 PM 已人工确认 worker 因配额卡死
#   Step 2  worker-stop 原子 fence+stop；失败 → 仅尝试 worker-abandon fence，
#           绝不释放 provider lease（旧 worker 可能仍消费额度）
#   Step 3  释放 METADATA 记录的 provider lease（--resource-settled，依赖 Orca
#           terminal liveness 证明资源已死）；失败 → 不写 marker（额度不放）
#   Step 4  METADATA .recovery.quota_park 落 marker；同 worktree 重启必须用新
#           session id（authority receipt 每会话唯一，fail-closed）；切 provider
#           后仍会过 spawn-worker 的 quota preflight。
# 顺序保证：lease 释放永远在 worker-stop 成功之后 → 任何失败路径都不产生
# "worker 活着 + lease 已释放"的双活窗口。
cmd_quota_park() {
  [ "$WORKER_MODE" = "orca_supervised" ] || { echo "ERROR: quota-park requires an Orca supervised worker (dispatch fencing is the double-active guard)" >&2; exit 64; }
  [ -n "$REASON" ] || { echo "ERROR: quota-park requires --reason (audit)" >&2; exit 64; }
  [ -n "$ORCA_DISPATCH_ID" ] || { echo "ERROR: quota-park: missing dispatch_id in METADATA" >&2; exit 64; }

  local show_json show_rc stop_rc abandon_rc lease_root parked_at tmp_meta
  resolve_project_identity || exit 2
  orca_runtime_init
  ensure_coordinator_binding || exit 2

  echo "PM_ORCHESTRATE_QUOTA_PARK_START: dispatch=$ORCA_DISPATCH_ID worktree=$ORCA_WORKTREE_ID force=$FORCE reason=$REASON"
  write_settle_audit quota_park_started "liveness check pending; worktree/session/checkpoint will be preserved" || {
    echo "ERROR: cannot persist quota-park audit under Git common dir; refusing mutation" >&2
    exit 2
  }

  # Step 1: liveness gate — active/不确定 只能被显式 --force 停靠（PM 人工确认配额卡死）。
  set +e
  show_json=$(orca_cli orchestration worker-show --dispatch "$ORCA_DISPATCH_ID" --json 2>&1)
  show_rc=$?
  set -e
  if [ "$show_rc" -ne 0 ]; then
    if [ "$FORCE" -ne 1 ]; then
      echo "REFUSED: worker-show failed (rc=$show_rc, cannot determine liveness); re-run with --force" >&2
      exit 2
    fi
    echo "WARN: worker-show failed (rc=$show_rc) but --force given; assuming quota-stalled" >&2
    show_json=""
  fi
  settle_liveness_check "$show_json" "$FORCE"

  # Step 2: worker-stop 原子 fence+stop。失败 → 只 fence（abandon 兜底），绝不释放 lease。
  set +e
  if orca_cli orchestration worker-stop --dispatch "$ORCA_DISPATCH_ID" --json; then
    stop_rc=0
    echo "PM_ORCHESTRATE_QUOTA_PARK_STOPPED: dispatch=$ORCA_DISPATCH_ID"
  else
    stop_rc=$?
  fi
  set -e
  if [ "$stop_rc" -ne 0 ]; then
    set +e
    orca_cli orchestration worker-abandon --dispatch "$ORCA_DISPATCH_ID" --json
    abandon_rc=$?
    set -e
    write_settle_audit quota_park_stop_failed "worker-stop rc=$stop_rc; worker-abandon rc=$abandon_rc; provider lease retained" || true
    echo "ERROR: worker-stop failed (rc=$stop_rc); provider lease retained, same-worktree restart NOT authorized (no double-active, fail-closed)" >&2
    exit 2
  fi
  write_settle_audit quota_park_stopped "worker-stop fenced and stopped the old dispatch" || {
    echo "ERROR: cannot persist post-stop audit; provider lease retained" >&2
    exit 2
  }

  # Step 3: 释放 provider lease（同 worktree 重启/切 provider 的解锁点）。
  # worker 已被 fence+stop；此处 liveness 证明失败只会卡额度，不会双活。
  if [ -n "$PROVIDER_LEASE_FILE" ]; then
    lease_root=$(provider_lease_root_for_project "$PROJECT_DIR") || {
      echo "ERROR: cannot derive trusted provider lease root for $PROJECT_DIR (lease retained)" >&2
      exit 2
    }
    if python3 "$SCRIPT_DIR/provider-lease.py" release \
        --root "$lease_root" \
        --lease-file "$PROVIDER_LEASE_FILE" --session "$SESSION" \
        --resource-settled --orca-cli "$ORCA_CLI_BIN"; then
      echo "PM_ORCHESTRATE_QUOTA_PARK_LEASE_RELEASED: $PROVIDER_LEASE_FILE"
    else
      write_settle_audit quota_park_lease_release_failed "provider-lease release failed; marker not written" || true
      echo "ERROR: provider lease release failed; park aborted, same-worktree restart NOT authorized (fail-closed)" >&2
      exit 2
    fi
  else
    echo "PM_ORCHESTRATE_QUOTA_PARK_LEASE_NONE: METADATA has no provider lease; nothing to release"
  fi
  write_settle_audit quota_park_lease_released "provider lease released (or absent)" || {
    echo "ERROR: cannot persist lease-release audit" >&2
    exit 2
  }

  # Step 4: METADATA .recovery.quota_park marker（worktree/session/checkpoint 不动）。
  parked_at=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
  tmp_meta=$(mktemp)
  if jq --arg parked_at "$parked_at" --arg reason "$REASON" \
      --arg dispatch "$ORCA_DISPATCH_ID" --arg lease_file "$PROVIDER_LEASE_FILE" \
      --arg worktree_id "$ORCA_WORKTREE_ID" \
      '.recovery.quota_park = {
         parked_at: $parked_at,
         reason: $reason,
         dispatch_id: $dispatch,
         provider_lease_file: $lease_file,
         orca_worktree_id: $worktree_id,
         restart: "same worktree requires a NEW session id (authority receipt is per-session, fail-closed); provider switch allowed and still subject to spawn-worker quota preflight"
       }' "$METADATA" > "$tmp_meta" && mv "$tmp_meta" "$METADATA"; then
    echo "PM_ORCHESTRATE_QUOTA_PARK_MARKER: $METADATA"
  else
    rm -f "$tmp_meta"
    write_settle_audit quota_park_marker_failed "METADATA marker write failed; lease already released" || true
    echo "ERROR: failed to write quota_park marker into METADATA (lease already released; worktree/session preserved)" >&2
    exit 2
  fi

  write_settle_audit quota_park_parked "park complete; same-worktree restart (new session id) or provider switch authorized" || {
    echo "ERROR: cannot persist final quota-park audit" >&2
    exit 2
  }
  echo "PM_ORCHESTRATE_QUOTA_PARK_DONE: dispatch=$ORCA_DISPATCH_ID parked; worktree/session/checkpoint preserved at $WORKTREE"
  echo "PM_ORCHESTRATE_QUOTA_PARK_NEXT: restart on the SAME worktree with a NEW session id (spawn-worker --worktree $WORKTREE --session <new-id> ...), or switch provider; both still pass quota preflight before any side effect"
}

# Task-081：reauthorize 对 dispatched(等待中) worker 的原地重授权支撑函数。
# 背景：2026-08-30 FaroPDF 编排实测——worker 卡 escalation 等待（task 仍 dispatched）
# 时跑 reauthorize，worker-start 被 TASK_REUSED 拒绝后直接 exit 2，而新 terminal 已
# 创建、旧 terminal 未关闭 → 双活终端泄漏。以下三个辅助函数分别负责：
#   ① 状态预检（task-list 尽力而为；旧 runtime 缺子命令降级 unknown，既有路径零变化）
#   ② 等待消费（dispatched 且有未消费 escalation/question 时，把 --resume-text 或
#      缺省续接说明作为 reply 发给该 dispatch，worker 解锁继续；task 保持 dispatched）
#   ③ 终端回滚（新 terminal 建立后任何中间失败先关新终端、保留旧终端——任何时刻
#      至多一个活终端，重复调用 reauthorize 不累积终端）
reauthorize_task_state() {
  local task_id="$1" state="unknown" list_out
  if list_out=$(orca_cli orchestration task-list --run "$ORCA_RUN_ID" --json 2>/dev/null); then
    set +e +o pipefail
    state=$(printf '%s' "$list_out" | jq -r --arg task "$task_id" '
      [(.result.tasks // .result // [])[]?
        | select(((.id // .taskId // "") == $task))
        | (.status // .state // "unknown")][0] // "unknown"' 2>/dev/null)
    set -e -o pipefail
    [ -n "$state" ] || state="unknown"
  fi
  printf '%s' "$state"
}

reauthorize_consume_pending_wait() {
  local resume_text="$1" dispatch_id="$2" check_out msg_id body
  check_out=$(orca_cli orchestration check --json 2>/dev/null) || check_out=""
  msg_id=""
  if [ -n "$check_out" ]; then
    set +e +o pipefail
    msg_id=$(printf '%s' "$check_out" | jq -r --arg dispatch "$dispatch_id" '
      [(.result.messages // .result.deliveries // .messages // .deliveries // [])[]?
        | select((((.type // .message_type // "") | ascii_downcase) == "escalation")
              or (((.type // .message_type // "") | ascii_downcase) == "question"))
        | select(((.dispatch_id // .dispatchId // .to // "") | tostring) as $d
            | ($d == $dispatch or $d == ("dispatch:" + $dispatch)))
        | (.id // .message_id // .messageId // .delivery_id // .deliveryId // empty)][0]
      // empty' 2>/dev/null)
    set -e -o pipefail
  fi
  if [ -z "$msg_id" ]; then
    echo "PM_REAUTHORIZE_WAIT_NONE: 无未消费 escalation/question（check 为空、不可用或无匹配消息）；跳过等待消费"
    return 0
  fi
  body="$resume_text"
  [ -n "$body" ] || body="PM reauthorize: 授权快照已刷新，请继续执行当前任务"
  if orca_cli orchestration reply --id "$msg_id" --body "$body" --json >/dev/null 2>&1; then
    echo "PM_REAUTHORIZE_WAIT_CONSUMED: message=${msg_id}（worker 等待已解锁；task 保持 dispatched）"
  else
    echo "WARN: reply $msg_id 失败；worker 等待未被消费，后续重注册预计仍被 TASK_REUSED 拒绝" >&2
  fi
}

reauthorize_rollback_new_terminal() {
  local new_handle="$1" why="$2"
  [ -n "$new_handle" ] || return 0
  [ "$new_handle" != "$WORKER_HANDLE" ] || return 0
  if orca_cli terminal close --terminal "$new_handle" --json >/dev/null 2>&1; then
    echo "PM_REAUTHORIZE_NEW_TERMINAL_ROLLED_BACK: ${new_handle}（${why}）；旧终端 $WORKER_HANDLE 保留"
  else
    echo "WARN: 新终端 $new_handle 回滚关闭失败（${why}）；请手动关闭: orca terminal close --terminal $new_handle" >&2
  fi
}

cmd_reauthorize() {
  # Task-058: spawn 授权快照的运行时刷新。guard 的 load_authorization() 中
  # WORKER_INSTALL_AUTH_B64（launch.sh 内联、进程环境）绝对优先于授权文件且
  # 运行中不可刷新——PM 直接编辑 INSTALL_AUTHORIZATION.json 对已启动 worker
  # 无效（badminton-lab 2026-08-25 Wave 2 事故：worker 全部门禁被
  # SHELL_COMMAND_NOT_ALLOWLISTED 拦截，TDD 卡死）。
  # 本命令封装当次验证过的恢复链路，全部步骤 fail-closed：
  #   1) 合并 --allow-cmd 进 INSTALL_AUTHORIZATION.json（去重、保留原条目）
  #   2) 从授权文件重新编码 B64 并重写 launch.sh（恰好一处赋值，改写后回验）
  #   3) 同 worktree 创建新终端（复用重写后的 launch.sh，未提交改动全保留）
  #   4) 复用 Task 重注册（worker-start 重注入）；若 Task 因 worker 提问/中止
  #      翻成 failed 被 task_not_startable 拦截，先复位 ready 再重试一次
  #   5) METADATA 的 terminal_handle/dispatch_id 改路由到新句柄
  #   6) 可选 --resume-text 作为续接说明发新终端
  #   7) 关闭旧终端句柄（register 成功之后；provider lease 的 transport 记账
  #      留给 release/clean-worktree 阶段处理）
  [ "$WORKER_MODE" = "orca_supervised" ] || {
    echo "ERROR: reauthorize requires an Orca supervised worker" >&2
    exit 64
  }
  local task_id="$REAUTH_TASK_ID"
  [ -n "$task_id" ] || task_id=$(jq -r '.session.orca.supervised.task_id // empty' "$METADATA")
  [ -n "$task_id" ] || { echo "ERROR: METADATA is missing supervised.task_id; pass --task-id" >&2; exit 64; }
  [ -n "$ORCA_WORKTREE_ID" ] || { echo "ERROR: METADATA is missing orca.worktree_id" >&2; exit 64; }
  [ -n "$ORCA_COORDINATOR_HANDLE" ] || { echo "ERROR: METADATA is missing coordinator handle" >&2; exit 64; }

  local auth_file="$SESSION_CONTEXT/INSTALL_AUTHORIZATION.json"
  local launch_sh="$SESSION_CONTEXT/launch.sh"
  [ -f "$auth_file" ] || { echo "ERROR: authorization file not found: $auth_file" >&2; exit 64; }
  [ -f "$launch_sh" ] || { echo "ERROR: launch.sh not found: $launch_sh" >&2; exit 64; }
  ensure_coordinator_binding || exit 2

  # Step 0 (Task-081)：dispatched 等待态探测与消费。仅 dispatched 分支有额外动作；
  # ready/failed/blocked/completed/unknown 走原有链路零变化。
  local reauth_task_state
  reauth_task_state=$(reauthorize_task_state "$task_id")
  echo "PM_REAUTHORIZE_TASK_STATE: $reauth_task_state"
  if [ "$reauth_task_state" = "dispatched" ]; then
    reauthorize_consume_pending_wait "$REAUTH_RESUME_TEXT" "$ORCA_DISPATCH_ID"
  fi

  # Step 1: merge --allow-cmd（无 --allow-cmd 时仅刷新快照，仍支持 PM 手改文件后的场景）
  if [ "${#ALLOW_CMDS[@]}" -gt 0 ]; then
    local extra_json tmp_auth
    extra_json=$(printf '%s\n' "${ALLOW_CMDS[@]}" | jq -R . | jq -s .)
    tmp_auth=$(mktemp)
    jq --argjson extra "$extra_json" \
      '.allowed_shell_commands = ((.allowed_shell_commands // []) + $extra | unique)' \
      "$auth_file" > "$tmp_auth" || {
      rm -f "$tmp_auth"
      echo "ERROR: failed to merge --allow-cmd into $auth_file" >&2
      exit 2
    }
    mv "$tmp_auth" "$auth_file"
    echo "PM_REAUTHORIZE_AUTH_MERGED: ${#ALLOW_CMDS[@]} command(s) merged into authorization file"
  fi

  # Step 2: re-encode B64 and rewrite launch.sh（恰好一处赋值；回验解码一致）
  local rewrite_err
  if ! rewrite_err=$(python3 - "$auth_file" "$launch_sh" <<'PY'
import base64, json, re, sys
auth_path, launch_path = sys.argv[1], sys.argv[2]
snapshot = json.load(open(auth_path))
new_b64 = base64.b64encode(json.dumps(snapshot, ensure_ascii=False).encode()).decode()
s = open(launch_path).read()
new_s, n = re.subn(r"(WORKER_INSTALL_AUTH_B64=)[A-Za-z0-9+/=]+",
                   lambda m: m.group(1) + new_b64, s)
if n != 1:
    sys.exit(f"expected exactly one WORKER_INSTALL_AUTH_B64 assignment, found {n}")
m = re.search(r"WORKER_INSTALL_AUTH_B64=([A-Za-z0-9+/=]+)", new_s)
if json.loads(base64.b64decode(m.group(1))) != snapshot:
    sys.exit("roundtrip verification failed")
open(launch_path, "w").write(new_s)
PY
  ); then
    echo "ERROR: launch.sh B64 rewrite failed: $rewrite_err" >&2
    exit 2
  fi
  echo "PM_REAUTHORIZE_LAUNCH_REFRESHED: B64 snapshot rewritten and verified"

  # Step 3: new terminal in the same worktree
  local create_json new_handle
  create_json=$(orca_cli terminal create --worktree "path:$WORKTREE" --title "$SESSION" \
    --command "bash $(printf '%q' "$launch_sh")" --json 2>&1) || {
    echo "ERROR: terminal create failed: $create_json" >&2
    exit 2
  }
  new_handle=$(printf '%s' "$create_json" | jq -r '.result.terminal.handle // empty')
  [ -n "$new_handle" ] || { echo "ERROR: terminal create returned no handle: $create_json" >&2; exit 2; }
  echo "PM_REAUTHORIZE_TERMINAL_CREATED: $new_handle"

  # Step 4: re-register（Task 若被翻成 failed 先复位 ready 再重试一次）
  local register_cmd="$SCRIPT_DIR/orca-supervised-register.sh"
  [ -f "$register_cmd" ] || { echo "ERROR: orca-supervised-register.sh not found: $register_cmd" >&2; exit 64; }
  local register_out
  if ! register_out=$(bash "$register_cmd" \
      --worktree-id "$ORCA_WORKTREE_ID" \
      --terminal-handle "$new_handle" \
      --run-id "$ORCA_RUN_ID" \
      --task-id "$task_id" \
      --coordinator-handle "$ORCA_COORDINATOR_HANDLE" 2>&1); then
    if printf '%s' "$register_out" | grep -q "task_not_startable"; then
      echo "PM_REAUTHORIZE_TASK_RESET: task $task_id not startable; resetting to ready"
      orca_cli orchestration task-update --id "$task_id" --status ready \
        --run "$ORCA_RUN_ID" --from "$ORCA_COORDINATOR_HANDLE" >/dev/null || {
        reauthorize_rollback_new_terminal "$new_handle" "task-update 复位失败"
        echo "ERROR: failed to reset task $task_id to ready" >&2
        exit 2
      }
      register_out=$(bash "$register_cmd" \
        --worktree-id "$ORCA_WORKTREE_ID" \
        --terminal-handle "$new_handle" \
        --run-id "$ORCA_RUN_ID" \
        --task-id "$task_id" \
        --coordinator-handle "$ORCA_COORDINATOR_HANDLE" 2>&1) || {
        reauthorize_rollback_new_terminal "$new_handle" "复位后重注册仍失败"
        echo "ERROR: re-registration failed after task reset: $register_out" >&2
        exit 2
      }
    elif printf '%s' "$register_out" | grep -qi "task_reused"; then
      # Task-081 ③：dispatched task 的注册通道硬限制（单活 fencing：活 Dispatch 未
      # 结算前 worker-start 必被拒）。不裸抛 TASK_REUSED——先回滚新终端防双活，再给
      # manual-recovery 指引（等待已在 Step 0 消费，worker 可继续用旧终端跑）。
      reauthorize_rollback_new_terminal "$new_handle" "task 仍 dispatched，重注册被单活 fencing 拒绝"
      {
        echo "PM_REAUTHORIZE_REGISTER_TASK_REUSED: task $task_id 仍处于 dispatched（活 Dispatch 未结算），Orca 拒绝重复注册"
        echo "PM_REAUTHORIZE_MANUAL_RECOVERY: 已完成：授权文件合并 + launch.sh B64 刷新（下次启动生效）+ 等待消费。后续三选一："
        echo "  1) worker 仍在跑：等它发 worker_done 自然结算（task 翻转）后重跑本命令，届时走既有换终端链"
        echo "  2) worker 进程已死：先 settle 再重跑本命令——pm-orchestrate settle --worktree <WT> --session $SESSION --reason \"...\"（fence+stop 翻转 task 后 reauthorize 即可正常换终端）"
        echo "  3) 按 runbook #18 三步补绑手工重建通道：① orca orchestration dispatch --task $task_id --to $WORKER_HANDLE --run $ORCA_RUN_ID --return-preamble（不带 --inject） ② 从返回 preamble 提取真实 ctx id ③ orca terminal send --terminal $WORKER_HANDLE --text \"<单行 worker_done/ask 命令形式>\" --enter（必须单行）"
      } >&2
      exit 2
    else
      # Task-081 ②：中间失败不得留双活终端——先回滚新终端再报错
      reauthorize_rollback_new_terminal "$new_handle" "重注册失败"
      echo "ERROR: re-registration failed: $register_out" >&2
      exit 2
    fi
  fi
  local new_dispatch
  new_dispatch=$(printf '%s' "$register_out" | grep 'ORCAREG_DISPATCH_ID=' | tail -1 | cut -d= -f2)
  [ -n "$new_dispatch" ] || { echo "ERROR: register output missing dispatch id: $register_out" >&2; exit 2; }
  echo "PM_REAUTHORIZE_REGISTERED: dispatch=$new_dispatch task=$task_id"

  # Step 5: METADATA reroute
  local tmp_meta
  tmp_meta=$(mktemp)
  jq --arg th "$new_handle" --arg di "$new_dispatch" \
    '.session.orca.terminal_handle = $th | .session.orca.supervised.dispatch_id = $di' \
    "$METADATA" > "$tmp_meta" && mv "$tmp_meta" "$METADATA" || {
    rm -f "$tmp_meta"
    reauthorize_rollback_new_terminal "$new_handle" "METADATA 改路由失败"
    echo "ERROR: METADATA reroute failed" >&2
    exit 2
  }
  echo "PM_REAUTHORIZE_METADATA_REROUTED: terminal=$new_handle dispatch=$new_dispatch"

  # Step 6: optional resume note（worker-start 注入完成后再发，避免与 preamble 竞争）
  if [ -n "$REAUTH_RESUME_TEXT" ]; then
    sleep 3
    if orca_cli terminal send --terminal "$new_handle" --text "$REAUTH_RESUME_TEXT" --enter --json >/dev/null 2>&1; then
      echo "PM_REAUTHORIZE_RESUME_SENT"
    else
      echo "WARN: resume text could not be sent to $new_handle; send manually via pm-orchestrate send"
    fi
  fi

  # Step 7: close the old terminal by exact handle（最后做；失败只警告，PM 可手动关）
  if [ -n "$WORKER_HANDLE" ] && [ "$WORKER_HANDLE" != "$new_handle" ]; then
    if orca_cli terminal close --terminal "$WORKER_HANDLE" --json >/dev/null 2>&1; then
      echo "PM_REAUTHORIZE_OLD_TERMINAL_CLOSED: $WORKER_HANDLE"
    else
      echo "WARN: old terminal $WORKER_HANDLE could not be closed; close it manually"
    fi
  fi
  echo "PM_REAUTHORIZE_DONE: worker $SESSION now on $new_handle (uncommitted worktree changes preserved)"
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
  reauthorize) cmd_reauthorize ;;
  quota-park) cmd_quota_park ;;
esac
