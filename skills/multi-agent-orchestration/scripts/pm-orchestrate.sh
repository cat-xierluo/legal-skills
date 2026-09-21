#!/usr/bin/env bash
# Unified PM control plane for Orca supervised workers, Orca terminals and tmux.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=orca-runtime.sh
source "$SCRIPT_DIR/orca-runtime.sh"
# shellcheck source=orca-coordinator.sh
source "$SCRIPT_DIR/orca-coordinator.sh"
# shellcheck source=provider-lease-root.sh
source "$SCRIPT_DIR/provider-lease-root.sh"

usage() {
  cat >&2 <<'USAGE'
Usage:
  pm-orchestrate.sh run-create --objective TEXT
  pm-orchestrate.sh reconcile --snapshot PATH --output PATH
  pm-orchestrate.sh pr-audit --worktree PATH --base-ref main --head-ref BRANCH --head-sha SHA [--task-id ID] [--agent-id ID]
  pm-orchestrate.sh <command> --worktree PATH --session NAME [options]

Commands:
  run-create  Create and bind one Orca Run for a Wave
  reconcile   Derive settlement from captured exact observations; no Orca lifecycle mutation
  pr-audit    Read-only classification of open PRs for one frozen worker head
  send        Send guidance: Dispatch inbox for supervised, terminal input otherwise
  inbox       Read-only Orca inbox snapshot (`check --peek`); never advances Delivery
  read|peek   Read exact worker transcript/terminal output; peek uses 15 rows
  show        Show supervised Dispatch state
  wait        Wait for Run Delivery (supervised) or TUI idle (terminal)
  ack         Acknowledge a processed Orca Delivery (`--delivery-id`)
  reply       Reply to a worker question (`--message-id` + `--text`); an exact
               unknown-outcome recovery may reuse the same `--retry-request`
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
               (Task-113) worker_done 结算后（task failed/settled、Delivery release+ack）
               注册返回 TASK_REUSED 时不再误判为仍 dispatched：先复核状态，确认仍是
               failed/settled 才复位 ready 并只重试一次注册；复核翻回 dispatched（漂移）
               或 unknown/其他状态一律回滚新终端 fail-closed 不复位。
               (Task-116) 任何 mutation 之前先读权威 Dispatch 状态（worker-show）：仅
               未 released/acked/settled 的 live 目标可继续；已进入结算链或状态不可证
               的目标稳定输出 REAUTHORIZE_NOT_LIVE，零副作用（授权文件/launch.sh/
               终端/METADATA 均不变）。已结算目标的恢复走 release/ack 正常收口或
               quota-park/明确恢复入口。
  quota-park  Quota-stall recovery handoff (v2.11.0 P0-③)：精确 fence + stop 旧
               supervised Dispatch（worker-stop），完整保留 worktree/session/checkpoint，
               释放 METADATA 记录的 provider lease，之后同 worktree 可用新 session id
               重启或切 provider（重启仍要过 spawn-worker 的 quota preflight）。
               任何一步失败立即中止：不释放 lease、不写 marker，绝不产生
               "worker 活着 + 额度已放" 的双活窗口。需要 --reason；worker 仍活/
               不确定时只有 --force（PM 人工确认配额卡死）可停靠。

Common:
  --snapshot PATH  With reconcile: verified observation snapshot
  --output PATH    With reconcile: immutable settlement receipt destination
  --worktree PATH   Worker worktree path
  --session NAME    spawn-worker session id
  --from HANDLE     Explicit PM sender; otherwise use this session's recorded coordinator
  --text TEXT       Prompt, guidance or reply body
  --prompt-file P   Read prompt/guidance from a file
  --message-contract Enable the versioned Orca message contract for supervised `send`
  --subject TEXT    Contract message subject (default: PM guidance)
  --message-type T  Contract type: status|dispatch|merge_ready|handoff|decision_gate|question
  --priority LEVEL  Contract priority: normal|high|urgent (normal is omitted from native argv)
  --thread-id ID    Stable business thread id; with `inbox`, optional exact-match filter
  --correlation-id ID
                    Business correlation id; with `inbox`, optional exact-match filter
  --retry-request ID
                    Orca mutation retry id; reuse only for the exact same send or reply attempt
  --expected-action TEXT
                    One requested next action; informational, never grants authority
  --evidence-ref REF
                    Repeatable typed reference: git:|path:|pr:|test:|message:|task:|report:
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
PM_FROM=""
MESSAGE_CONTRACT=0
MESSAGE_CONTRACT_FIELD_SEEN=0
MESSAGE_SEND_ONLY_FIELD_SEEN=0
MESSAGE_SUBJECT="PM guidance"
MESSAGE_TYPE="status"
MESSAGE_PRIORITY="normal"
MESSAGE_THREAD_ID=""
MESSAGE_CORRELATION_ID=""
MESSAGE_RETRY_REQUEST=""
REPLY_RETRY_REQUEST=""
MESSAGE_EXPECTED_ACTION=""
MESSAGE_EVIDENCE_REFS=()
MESSAGE_CONTRACT_SHA256=""
MESSAGE_RETRY_FOUND=0
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
RECON_SNAPSHOT=""
RECON_OUTPUT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --snapshot) RECON_SNAPSHOT="${2:?--snapshot needs a path}"; shift 2 ;;
    --output) RECON_OUTPUT="${2:?--output needs a path}"; shift 2 ;;
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
    --from) PM_FROM="${2:?--from needs a handle}"; shift 2 ;;
    --message-contract) MESSAGE_CONTRACT=1; shift ;;
    --subject) MESSAGE_SUBJECT="${2:?--subject needs text}"; MESSAGE_CONTRACT_FIELD_SEEN=1; MESSAGE_SEND_ONLY_FIELD_SEEN=1; shift 2 ;;
    --message-type) MESSAGE_TYPE="${2:?--message-type needs a value}"; MESSAGE_CONTRACT_FIELD_SEEN=1; MESSAGE_SEND_ONLY_FIELD_SEEN=1; shift 2 ;;
    --priority) MESSAGE_PRIORITY="${2:?--priority needs a value}"; MESSAGE_CONTRACT_FIELD_SEEN=1; MESSAGE_SEND_ONLY_FIELD_SEEN=1; shift 2 ;;
    --thread-id) MESSAGE_THREAD_ID="${2:?--thread-id needs an id}"; MESSAGE_CONTRACT_FIELD_SEEN=1; shift 2 ;;
    --correlation-id) MESSAGE_CORRELATION_ID="${2:?--correlation-id needs an id}"; MESSAGE_CONTRACT_FIELD_SEEN=1; shift 2 ;;
    --retry-request)
      if [ "$COMMAND" = "reply" ]; then
        REPLY_RETRY_REQUEST="${2:?--retry-request needs an id}"
      else
        MESSAGE_RETRY_REQUEST="${2:?--retry-request needs an id}"
        MESSAGE_CONTRACT_FIELD_SEEN=1
        MESSAGE_SEND_ONLY_FIELD_SEEN=1
      fi
      shift 2
      ;;
    --expected-action) MESSAGE_EXPECTED_ACTION="${2:?--expected-action needs text}"; MESSAGE_CONTRACT_FIELD_SEEN=1; MESSAGE_SEND_ONLY_FIELD_SEEN=1; shift 2 ;;
    --evidence-ref) MESSAGE_EVIDENCE_REFS+=("${2:?--evidence-ref needs a typed reference}"); MESSAGE_CONTRACT_FIELD_SEEN=1; MESSAGE_SEND_ONLY_FIELD_SEEN=1; shift 2 ;;
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
  run-create|pr-audit|reconcile|send|inbox|read|peek|show|wait|ack|reply|release|retain|settle|reauthorize|quota-park) ;;
  *) echo "ERROR: unknown command: $COMMAND" >&2; usage; exit 64 ;;
esac
if [ "$COMMAND" = "send" ]; then
  [ "$MESSAGE_CONTRACT_FIELD_SEEN" -eq 0 ] || [ "$MESSAGE_CONTRACT" -eq 1 ] || {
    echo "PM_MESSAGE_CONTRACT_REQUIRED: contract fields require --message-contract" >&2
    exit 64
  }
elif [ "$COMMAND" = "inbox" ]; then
  [ "$MESSAGE_CONTRACT" -eq 0 ] || {
    echo "PM_MESSAGE_CONTRACT_COMMAND_UNSUPPORTED: inbox is a read-only observer and does not accept --message-contract" >&2
    exit 64
  }
  [ "$MESSAGE_SEND_ONLY_FIELD_SEEN" -eq 0 ] || {
    echo "PM_MESSAGE_INBOX_FILTER_UNSUPPORTED: inbox accepts only --thread-id and --correlation-id message fields" >&2
    exit 64
  }
  if { [ -n "$MESSAGE_THREAD_ID" ] && [ -z "$MESSAGE_CORRELATION_ID" ]; } || \
     { [ -z "$MESSAGE_THREAD_ID" ] && [ -n "$MESSAGE_CORRELATION_ID" ]; }; then
    echo "PM_MESSAGE_INBOX_FILTER_INCOMPLETE: provide both --thread-id and --correlation-id, or neither" >&2
    exit 64
  fi
else
  [ "$MESSAGE_CONTRACT_FIELD_SEEN" -eq 0 ] && [ "$MESSAGE_CONTRACT" -eq 0 ] || {
    echo "PM_MESSAGE_CONTRACT_COMMAND_UNSUPPORTED: message contract fields are accepted only by send or inbox filters" >&2
    exit 64
  }
fi
# Reconciliation must not pass through coordinator binding or metadata mutation.
if [ "$COMMAND" = "reconcile" ]; then
  [ -n "$RECON_SNAPSHOT" ] && [ -n "$RECON_OUTPUT" ] || {
    echo "ERROR: reconcile requires --snapshot and --output" >&2; exit 64;
  }
  [ "$FORCE" -eq 0 ] && [ "$DESTROY" -eq 0 ] || {
    echo "ERROR: reconcile never accepts --force or --destroy" >&2; exit 64;
  }
  command -v python3 >/dev/null 2>&1 || {
    echo "ERROR: Python 3 is required for runtime reconciliation" >&2; exit 64;
  }
  exec python3 "$SCRIPT_DIR/runtime-reconcile.py" reconcile --snapshot "$RECON_SNAPSHOT" --output "$RECON_OUTPUT"
fi
[ -z "$RECON_SNAPSHOT$RECON_OUTPUT" ] || {
  echo "ERROR: --snapshot/--output are only accepted by reconcile" >&2; exit 64;
}
command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required" >&2; exit 64; }

if [ "$COMMAND" = "run-create" ]; then
  [ -n "$OBJECTIVE" ] || { echo "ERROR: run-create requires --objective" >&2; exit 64; }
  recorded_sender=""
  recorded_runtime=""
  allow_environment=1
  if [ -n "$WORKTREE$SESSION" ]; then
    [ -n "$WORKTREE" ] && [ -n "$SESSION" ] || {
      echo "ERROR: run-create session context requires both --worktree and --session" >&2; exit 64;
    }
    metadata="$WORKTREE/.claude/agent-sessions/$SESSION/METADATA.json"
    [ -f "$metadata" ] || { echo "ERROR: METADATA not found: $metadata" >&2; exit 64; }
    recorded_sender=$(jq -r '.session.orca.supervised.coordinator_handle // empty' "$metadata")
    recorded_runtime=$(jq -r '.session.orca.runtime_id // empty' "$metadata")
    allow_environment=0
  fi
  orca_coordinator_select "$PM_FROM" "$recorded_sender" "$allow_environment" || exit $?
  orca_coordinator_prepare create "" "$recorded_runtime" "$OBJECTIVE" || exit $?
  printf '%s\n' "$ORCA_PM_RUN_RECEIPT"
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
ORCA_TASK_ID=""
ORCA_DISPATCH_ID=""
ORCA_COORDINATOR_HANDLE=""
ORCA_RECORDED_RUNTIME_ID=""
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
  ORCA_TASK_ID=$(jq -r '.session.orca.supervised.task_id // empty' "$METADATA")
  ORCA_DISPATCH_ID=$(jq -r '.session.orca.supervised.dispatch_id // empty' "$METADATA")
  ORCA_COORDINATOR_HANDLE=$(jq -r '.session.orca.supervised.coordinator_handle // empty' "$METADATA")
  ORCA_RECORDED_RUNTIME_ID=$(jq -r '.session.orca.runtime_id // empty' "$METADATA")
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
  orca_coordinator_select "$PM_FROM" "$ORCA_COORDINATOR_HANDLE" 0 || return $?
  if [ -z "$ORCA_RECORDED_RUNTIME_ID" ]; then
    # Legacy metadata can establish a current binding, never historical continuity.
    orca_coordinator_prepare verify "$ORCA_RUN_ID" || return $?
    echo "PM_ORCHESTRATE_RUNTIME_REVERIFIED: legacy metadata; historical continuity NOT_VERIFIED" >&2
    ORCA_RECORDED_RUNTIME_ID="$ORCA_PM_RUNTIME_ID"
  fi
  orca_coordinator_prepare use "$ORCA_RUN_ID" "$ORCA_RECORDED_RUNTIME_ID" || return $?
  if [ "$ORCA_PM_SENDER" != "$ORCA_COORDINATOR_HANDLE" ] || \
    [ "$(jq -r '.session.orca.runtime_id // empty' "$METADATA")" != "$ORCA_PM_RUNTIME_ID" ]; then
    local tmp_meta
    tmp_meta=$(mktemp "${METADATA}.tmp.XXXXXX") || return 2
    if jq --arg coordinator "$ORCA_PM_SENDER" --arg runtime "$ORCA_PM_RUNTIME_ID" \
        '.session.orca.supervised.coordinator_handle = $coordinator | .session.orca.runtime_id = $runtime' "$METADATA" > "$tmp_meta" \
        && mv "$tmp_meta" "$METADATA"; then
      echo "PM_ORCHESTRATE_COORDINATOR_REBOUND: run=$ORCA_RUN_ID handle=$ORCA_PM_SENDER" >&2
    else
      rm -f "$tmp_meta"
      echo "ERROR: Run rebound but METADATA could not be refreshed; inspect binding before retrying" >&2
      return 2
    fi
  fi
  ORCA_COORDINATOR_HANDLE="$ORCA_PM_SENDER"
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

message_contract_fail() {
  local code="$1"
  shift
  echo "$code: $*" >&2
  return 64
}

message_contract_identifier_valid() {
  local value="$1"
  [[ "$value" =~ ^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$ ]]
}

orca_retry_request_valid() {
  local value="$1"
  [[ "$value" =~ ^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$ ]]
}

message_contract_sensitive() {
  local value="$1"
  printf '%s' "$value" | LC_ALL=C grep -Eiq -- \
    '(-----BEGIN ([A-Z0-9 ]+ )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|Authorization:[[:space:]]*(Bearer|Basic)[[:space:]]+[A-Za-z0-9._~+/=-]{8,}|(api[_-]?key|token|access[_-]?token|refresh[_-]?token|password|passwd|secret)[[:space:]]*[:=][[:space:]]*[^[:space:]]{8,})'
}

validate_message_contract() {
  if [ "$WORKER_MODE" != "orca_supervised" ]; then
    message_contract_fail "PM_MESSAGE_CONTRACT_REQUIRES_ORCA_SUPERVISED" "structured messages require an exact Dispatch" || return $?
  fi
  if [ -z "$ORCA_RUN_ID" ] || [ -z "$ORCA_TASK_ID" ] || [ -z "$ORCA_DISPATCH_ID" ] || \
    [ -z "$ORCA_COORDINATOR_HANDLE" ] || [ -z "$ORCA_RECORDED_RUNTIME_ID" ] || [ -z "$WORKER_HANDLE" ]; then
    message_contract_fail "PM_MESSAGE_CONTRACT_IDENTITY_MISSING" "run/task/dispatch/coordinator/runtime/worker metadata must all be present" || return $?
  fi
  case "$MESSAGE_TYPE" in
    status|dispatch|merge_ready|handoff|decision_gate|question) ;;
    *) message_contract_fail "PM_MESSAGE_CONTRACT_TYPE_REJECTED" "unsupported coordinator message type: $MESSAGE_TYPE" || return $? ;;
  esac
  case "$MESSAGE_PRIORITY" in
    normal|high|urgent) ;;
    *) message_contract_fail "PM_MESSAGE_CONTRACT_PRIORITY_REJECTED" "priority must be normal, high or urgent" || return $? ;;
  esac
  if [ -z "$MESSAGE_THREAD_ID" ] || ! message_contract_identifier_valid "$MESSAGE_THREAD_ID"; then
    message_contract_fail "PM_MESSAGE_CONTRACT_THREAD_INVALID" "--thread-id must be 1-128 safe identifier characters" || return $?
  fi
  if [ -z "$MESSAGE_CORRELATION_ID" ] || ! message_contract_identifier_valid "$MESSAGE_CORRELATION_ID"; then
    message_contract_fail "PM_MESSAGE_CONTRACT_CORRELATION_INVALID" "--correlation-id must be 1-128 safe identifier characters" || return $?
  fi
  if [ -z "$MESSAGE_EXPECTED_ACTION" ] || [ "${#MESSAGE_EXPECTED_ACTION}" -gt 500 ]; then
    message_contract_fail "PM_MESSAGE_CONTRACT_ACTION_INVALID" "--expected-action is required and limited to 500 characters" || return $?
  fi
  if [ -z "$MESSAGE_SUBJECT" ] || [ "${#MESSAGE_SUBJECT}" -gt 200 ]; then
    message_contract_fail "PM_MESSAGE_CONTRACT_SUBJECT_INVALID" "--subject is required and limited to 200 characters" || return $?
  fi
  if message_contract_sensitive "$MESSAGE_SUBJECT" || \
    message_contract_sensitive "$PM_FROM" || \
    message_contract_sensitive "$ORCA_COORDINATOR_HANDLE" || \
    message_contract_sensitive "$WORKER_HANDLE" || \
    message_contract_sensitive "$MESSAGE_THREAD_ID" || \
    message_contract_sensitive "$MESSAGE_CORRELATION_ID" || \
    message_contract_sensitive "$MESSAGE_RETRY_REQUEST" || \
    message_contract_sensitive "$MESSAGE_EXPECTED_ACTION" || \
    message_contract_sensitive "$1"; then
    message_contract_fail "PM_MESSAGE_CONTRACT_SENSITIVE_REJECTED" "message fields resemble sensitive authentication material" || return $?
  fi
  if [ -n "$MESSAGE_RETRY_REQUEST" ] && ! orca_retry_request_valid "$MESSAGE_RETRY_REQUEST"; then
    message_contract_fail "PM_MESSAGE_CONTRACT_RETRY_INVALID" "--retry-request must be the UUID Orca reported for the exact unknown-outcome mutation; omit it on a new send" || return $?
  fi
  local ref path_value
  for ref in "${MESSAGE_EVIDENCE_REFS[@]}"; do
    if [ -z "$ref" ] || [ "${#ref}" -gt 512 ]; then
      message_contract_fail "PM_MESSAGE_CONTRACT_EVIDENCE_INVALID" "evidence references must be 1-512 characters" || return $?
    fi
    case "$ref" in
      *$'\n'*|*$'\r'*) message_contract_fail "PM_MESSAGE_CONTRACT_EVIDENCE_INVALID" "evidence references must be single-line" || return $? ;;
    esac
    case "$ref" in
      git:*|pr:*|test:*|message:*|task:*|report:*) ;;
      path:*)
        path_value="${ref#path:}"
        case "$path_value" in
          ""|/*|../*|*/../*|*/..) message_contract_fail "PM_MESSAGE_CONTRACT_EVIDENCE_INVALID" "path evidence must be repository-relative without parent traversal" || return $? ;;
        esac
        ;;
      *) message_contract_fail "PM_MESSAGE_CONTRACT_EVIDENCE_INVALID" "evidence reference requires an allowed type prefix" || return $? ;;
    esac
    if message_contract_sensitive "$ref"; then
      message_contract_fail "PM_MESSAGE_CONTRACT_SENSITIVE_REJECTED" "evidence reference resembles a credential" || return $?
    fi
  done
}

build_message_contract_payload() {
  local evidence_json
  if [ "${#MESSAGE_EVIDENCE_REFS[@]}" -gt 0 ]; then
    evidence_json=$(printf '%s\n' "${MESSAGE_EVIDENCE_REFS[@]}" | jq -R . | jq -s .) || return 2
  else
    evidence_json='[]'
  fi
  jq -cn \
    --arg schema "multi-agent-orchestration.message-contract.v1" \
    --arg correlation_id "$MESSAGE_CORRELATION_ID" \
    --arg expected_action "$MESSAGE_EXPECTED_ACTION" \
    --arg message_type "$MESSAGE_TYPE" \
    --arg priority "$MESSAGE_PRIORITY" \
    --arg thread_id "$MESSAGE_THREAD_ID" \
    --arg sender "$ORCA_COORDINATOR_HANDLE" \
    --arg run_id "$ORCA_RUN_ID" \
    --arg task_id "$ORCA_TASK_ID" \
    --arg dispatch_id "$ORCA_DISPATCH_ID" \
    --argjson evidence_refs "$evidence_json" \
    '{
      schema: $schema,
      correlation_id: $correlation_id,
      expected_action: $expected_action,
      evidence_refs: $evidence_refs,
      authority: "informational_only",
      message: {type: $message_type, priority: $priority, thread_id: $thread_id},
      sender: {role: "coordinator", terminal_handle: $sender},
      recipient: {kind: "dispatch", dispatch_id: $dispatch_id},
      context: {run_id: $run_id, task_id: $task_id, dispatch_id: $dispatch_id}
    }' | jq -cS .
}

message_contract_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 | awk '{print $1}'
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())'
  else
    message_contract_fail "PM_MESSAGE_CONTRACT_DIGEST_UNAVAILABLE" "sha256sum, shasum or Python 3 is required" || return $?
  fi
}

build_message_contract_digest_input() {
  local body="$1" payload="$2"
  jq -cn \
    --arg schema "multi-agent-orchestration.send-request.v1" \
    --arg to "dispatch:$ORCA_DISPATCH_ID" \
    --arg run "$ORCA_RUN_ID" \
    --arg from "$ORCA_COORDINATOR_HANDLE" \
    --arg message_type "$MESSAGE_TYPE" \
    --arg priority "$MESSAGE_PRIORITY" \
    --arg subject "$MESSAGE_SUBJECT" \
    --arg body "$body" \
    --arg thread_id "$MESSAGE_THREAD_ID" \
    --arg correlation_id "$MESSAGE_CORRELATION_ID" \
    --argjson payload "$payload" \
    '{
      schema: $schema,
      routing: {to: $to, run_id: $run, sender_handle: $from},
      message: {
        type: $message_type,
        priority: $priority,
        subject: $subject,
        body: $body,
        logical_thread_id: $thread_id,
        native_thread_id: $correlation_id
      },
      payload: $payload
    }' | jq -cS .
}

message_retry_ledger_path() {
  printf '%s' "$SESSION_CONTEXT/MESSAGE_RETRY_FINGERPRINTS.ndjson"
}

message_retry_check() {
  MESSAGE_RETRY_FOUND=0
  [ -n "$MESSAGE_RETRY_REQUEST" ] || return 0
  local ledger summary
  ledger=$(message_retry_ledger_path)
  if [ -L "$ledger" ] || { [ -e "$ledger" ] && [ ! -f "$ledger" ]; }; then
    message_contract_fail "PM_MESSAGE_RETRY_LEDGER_UNSAFE" "retry fingerprint ledger must be a regular non-symlink file" || return $?
  fi
  [ -f "$ledger" ] || return 0
  summary=$(jq -cs --arg retry "$MESSAGE_RETRY_REQUEST" --arg digest "$MESSAGE_CONTRACT_SHA256" '
    [ .[] | select(.schema == "multi-agent-orchestration.message-retry-fingerprint.v1" and .retry_request == $retry) ] as $rows
    | {count: ($rows | length), conflict: ([$rows[] | select(.contract_sha256 != $digest)] | length)}
  ' "$ledger" 2>/dev/null) || {
    message_contract_fail "PM_MESSAGE_RETRY_LEDGER_INVALID" "retry fingerprint ledger is not valid NDJSON" || return $?
  }
  if [ "$(printf '%s' "$summary" | jq -r '.conflict')" != "0" ]; then
    message_contract_fail "PM_MESSAGE_RETRY_CONTRACT_MISMATCH" "--retry-request is already bound to a different contract digest" || return $?
  fi
  if [ "$(printf '%s' "$summary" | jq -r '.count')" != "0" ]; then
    MESSAGE_RETRY_FOUND=1
  fi
}

message_retry_record() {
  [ -n "$MESSAGE_RETRY_REQUEST" ] || return 0
  local ledger lock record rc=0
  ledger=$(message_retry_ledger_path)
  lock="${ledger}.lock"
  [ -d "$SESSION_CONTEXT" ] && [ ! -L "$SESSION_CONTEXT" ] || {
    message_contract_fail "PM_MESSAGE_RETRY_LEDGER_UNSAFE" "Session Context must be a real directory" || return $?
  }
  if ! mkdir "$lock" 2>/dev/null; then
    message_contract_fail "PM_MESSAGE_RETRY_LEDGER_BUSY" "another sender is updating the retry fingerprint ledger" || return $?
  fi
  message_retry_check || rc=$?
  if [ "$rc" -eq 0 ] && [ "$MESSAGE_RETRY_FOUND" -eq 0 ]; then
    record=$(jq -cn \
      --arg schema "multi-agent-orchestration.message-retry-fingerprint.v1" \
      --arg retry "$MESSAGE_RETRY_REQUEST" \
      --arg digest "$MESSAGE_CONTRACT_SHA256" \
      --arg thread "$MESSAGE_THREAD_ID" \
      --arg correlation "$MESSAGE_CORRELATION_ID" \
      '{schema:$schema,retry_request:$retry,contract_sha256:$digest,thread_id:$thread,correlation_id:$correlation}') || {
      echo "PM_MESSAGE_RETRY_LEDGER_WRITE_FAILED: could not encode retry fingerprint" >&2
      rc=2
    }
    if [ "$rc" -eq 0 ]; then
      umask 077
      printf '%s\n' "$record" >> "$ledger" || {
        echo "PM_MESSAGE_RETRY_LEDGER_WRITE_FAILED: could not append retry fingerprint" >&2
        rc=2
      }
    fi
  fi
  rmdir "$lock" 2>/dev/null || {
    echo "PM_MESSAGE_RETRY_LEDGER_UNLOCK_FAILED: inspect $lock before retrying" >&2
    [ "$rc" -ne 0 ] || rc=2
  }
  [ "$rc" -eq 0 ] || return "$rc"
}

emit_message_contract_receipt() {
  local raw="$1" operation="$2" state="$3"
  printf '%s' "$raw" | jq -e \
    --arg operation "$operation" \
    --arg state "$state" \
    --arg run_id "$ORCA_RUN_ID" \
    --arg task_id "$ORCA_TASK_ID" \
    --arg dispatch_id "$ORCA_DISPATCH_ID" \
    --arg sender "$ORCA_COORDINATOR_HANDLE" \
    --arg thread_id "$MESSAGE_THREAD_ID" \
    --arg correlation_id "$MESSAGE_CORRELATION_ID" \
    --arg retry_request "$MESSAGE_RETRY_REQUEST" \
    --arg contract_sha256 "$MESSAGE_CONTRACT_SHA256" \
    --arg message_type "$MESSAGE_TYPE" \
    --arg priority "$MESSAGE_PRIORITY" \
    'select(.ok == true)
    | (.result.relay // null) as $relay
    | select(
        ($relay | type) == "object"
        and $relay.destination == "worker"
        and $relay.dispatchId == $dispatch_id
      )
    | ($relay.messageId // "") as $message_id
    | select(($message_id | type) == "string" and ($message_id | length) > 0)
    | . + {
      mao_message_receipt: {
        schema: "multi-agent-orchestration.message-receipt.v1",
        operation: $operation,
        state: $state,
        message_id: $message_id,
        run_id: $run_id,
        task_id: $task_id,
        dispatch_id: $dispatch_id,
        sender_handle: $sender,
        thread_id: $thread_id,
        native_thread_id: $correlation_id,
        correlation_id: $correlation_id,
        retry_request: (if $retry_request == "" then null else $retry_request end),
        message_type: $message_type,
        priority: $priority,
        contract_sha256: $contract_sha256,
        does_not_prove: ["delivered_visible", "consumed", "replied", "action_started", "business_completed"]
      }
    }' || {
      echo "PM_MESSAGE_CONTRACT_RECEIPT_INVALID: Orca did not return a successful JSON receipt" >&2
      return 2
    }
}

verify_coordinator_binding_readonly() {
  [ "$WORKER_MODE" = "orca_supervised" ] || return 0
  [ -n "$ORCA_RUN_ID" ] || {
    echo "ERROR: supervised METADATA is missing run_id" >&2
    return 2
  }
  orca_coordinator_select "$PM_FROM" "$ORCA_COORDINATOR_HANDLE" 0 || return $?
  orca_coordinator_prepare verify "$ORCA_RUN_ID" "$ORCA_RECORDED_RUNTIME_ID" || return $?
  ORCA_COORDINATOR_HANDLE="$ORCA_PM_SENDER"
}

verify_message_dispatch_binding() {
  local mode="${1:-inspect}" raw
  case "$mode" in send|inspect) ;; *) return 64 ;; esac
  [ -n "$ORCA_RECORDED_RUNTIME_ID" ] && [ -n "$WORKER_HANDLE" ] || {
    message_contract_fail "PM_MESSAGE_DISPATCH_BINDING_MISSING" "runtime and worker terminal identities are required" || return $?
  }
  orca_runtime_current_runtime_id || {
    echo "PM_MESSAGE_DISPATCH_BINDING_UNVERIFIED: current Orca runtime identity is unavailable" >&2
    return 3
  }
  [ "$ORCA_RUNTIME_ID_NOW" = "$ORCA_RECORDED_RUNTIME_ID" ] || {
    echo "PM_MESSAGE_DISPATCH_BINDING_STALE: recorded runtime differs from current runtime" >&2
    return 3
  }
  raw=$(orca_cli orchestration worker-show --dispatch "$ORCA_DISPATCH_ID" --json 2>&1) || {
    echo "PM_MESSAGE_DISPATCH_BINDING_UNVERIFIED: worker-show failed: $raw" >&2
    return 3
  }
  printf '%s' "$raw" | jq -e \
    --arg runtime "$ORCA_RECORDED_RUNTIME_ID" \
    --arg run "$ORCA_RUN_ID" \
    --arg task "$ORCA_TASK_ID" \
    --arg dispatch "$ORCA_DISPATCH_ID" \
    --arg worker "$WORKER_HANDLE" \
    --arg mode "$mode" '
      .ok == true
      and ._meta.runtimeId == $runtime
      and ((.result.dispatch.id // .result.dispatch.dispatchId) == $dispatch)
      and ((.result.dispatch.task_id // .result.dispatch.taskId) == $task)
      and ((.result.dispatch.run_id // .result.dispatch.runId) == $run)
      and ((.result.dispatch.assignee_handle // .result.dispatch.assigneeHandle) == $worker)
      and ((.result.worker.dispatch_id // .result.worker.dispatchId) == $dispatch)
      and ((.result.worker.agent_terminal_handle // .result.worker.agentTerminalHandle) == $worker)
      and ($mode != "send" or (
        (.result.dispatch.status == "dispatched")
        and (.result.worker.state == "active")
      ))
    ' >/dev/null 2>&1 || {
    echo "PM_MESSAGE_DISPATCH_BINDING_INVALID: worker-show must prove exact runtime/run/task/dispatch/worker identity and required lifecycle state" >&2
    return 3
  }
}

validate_inbox_filters() {
  if [ -n "$MESSAGE_THREAD_ID" ] && ! message_contract_identifier_valid "$MESSAGE_THREAD_ID"; then
    message_contract_fail "PM_MESSAGE_INBOX_THREAD_INVALID" "--thread-id must be 1-128 safe identifier characters" || return $?
  fi
  if [ -n "$MESSAGE_CORRELATION_ID" ] && ! message_contract_identifier_valid "$MESSAGE_CORRELATION_ID"; then
    message_contract_fail "PM_MESSAGE_INBOX_CORRELATION_INVALID" "--correlation-id must be 1-128 safe identifier characters" || return $?
  fi
  if message_contract_sensitive "$PM_FROM" || \
    message_contract_sensitive "$ORCA_COORDINATOR_HANDLE" || \
    message_contract_sensitive "$WORKER_HANDLE" || \
    message_contract_sensitive "$MESSAGE_THREAD_ID" || \
    message_contract_sensitive "$MESSAGE_CORRELATION_ID"; then
    message_contract_fail "PM_MESSAGE_INBOX_SENSITIVE_REJECTED" "inbox sender, worker or filters resemble sensitive authentication material" || return $?
  fi
}

cmd_send() {
  local text payload raw
  text=$(load_text)
  if [ "$MESSAGE_CONTRACT" -eq 1 ]; then
    # Fail before the first Orca call so malformed, misrouted or sensitive
    # messages have no binding, Delivery or transport side effect.
    validate_message_contract "$text" || exit $?
    orca_coordinator_select "$PM_FROM" "$ORCA_COORDINATOR_HANDLE" 0 || exit $?
    ORCA_COORDINATOR_HANDLE="$ORCA_PM_SENDER"
    payload=$(build_message_contract_payload) || exit 2
    MESSAGE_CONTRACT_SHA256=$(build_message_contract_digest_input "$text" "$payload" | message_contract_sha256) || exit $?
    message_retry_check || exit $?
    verify_message_dispatch_binding send || exit $?
    orca_coordinator_probe "$ORCA_RECORDED_RUNTIME_ID" || exit $?
    message_retry_record || exit $?
    ensure_coordinator_binding || exit 2
    local args=(
      orchestration send
      --to "dispatch:$ORCA_DISPATCH_ID"
      --run "$ORCA_RUN_ID"
      --type "$MESSAGE_TYPE"
      --subject "$MESSAGE_SUBJECT"
      --body "$text"
      --from "$ORCA_COORDINATOR_HANDLE"
      --thread-id "$MESSAGE_CORRELATION_ID"
      --payload "$payload"
    )
    [ "$MESSAGE_PRIORITY" = "normal" ] || args+=(--priority "$MESSAGE_PRIORITY")
    [ -z "$MESSAGE_RETRY_REQUEST" ] || args+=(--retry-request "$MESSAGE_RETRY_REQUEST")
    raw=$(orca_cli "${args[@]}" --json) || exit $?
    emit_message_contract_receipt "$raw" "send" "durably_enqueued" || exit $?
    return
  fi
  if [ "$WORKER_MODE" = "orca_supervised" ]; then
    ensure_coordinator_binding || exit 2
    orca_cli orchestration send --to "dispatch:$ORCA_DISPATCH_ID" \
      --type status --subject "PM guidance" --body "$text" --from "$ORCA_COORDINATOR_HANDLE" --json
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

cmd_inbox() {
  [ "$WORKER_MODE" = "orca_supervised" ] || {
    echo "PM_MESSAGE_INBOX_REQUIRES_ORCA_SUPERVISED: inbox requires an exact Dispatch-backed Run" >&2
    exit 64
  }
  validate_inbox_filters || exit $?
  verify_message_dispatch_binding inspect || exit $?
  verify_coordinator_binding_readonly || exit $?
  local raw
  raw=$(orca_cli orchestration check --peek --terminal "$ORCA_COORDINATOR_HANDLE" --json) || exit $?
  printf '%s' "$raw" | jq -e \
    --arg run_id "$ORCA_RUN_ID" \
    --arg task_id "$ORCA_TASK_ID" \
    --arg dispatch_id "$ORCA_DISPATCH_ID" \
    --arg worker_handle "$WORKER_HANDLE" \
    --arg coordinator_handle "$ORCA_COORDINATOR_HANDLE" \
    --arg thread_id "$MESSAGE_THREAD_ID" \
    --arg correlation_id "$MESSAGE_CORRELATION_ID" \
    '
    def payload_object:
      (.payload // null) as $payload
      | if ($payload | type) == "object" then $payload
        elif ($payload | type) == "string" then (try ($payload | fromjson) catch {})
        else {} end;
    select(.ok == true)
    | [(.result.messages // [])[]?
        | . as $message
        | (payload_object) as $payload
        | [$message.id, $message.message_id, $message.messageId] | map(select(. != null)) as $message_ids
        | [$message.type, $message.message_type, $message.messageType, $payload.message.type, $payload.message.message_type, $payload.message.messageType] | map(select(. != null)) as $message_types
        | [$message.run_id, $message.runId] | map(select(. != null)) as $top_runs
        | [$message.task_id, $message.taskId] | map(select(. != null)) as $top_tasks
        | [$message.dispatch_id, $message.dispatchId] | map(select(. != null)) as $top_dispatches
        | [$payload.context.run_id, $payload.context.runId, $payload.run_id, $payload.runId] | map(select(. != null)) as $payload_runs
        | [$payload.context.task_id, $payload.context.taskId, $payload.task_id, $payload.taskId] | map(select(. != null)) as $payload_tasks
        | [$payload.context.dispatch_id, $payload.context.dispatchId, $payload.dispatch_id, $payload.dispatchId, $payload.recipient.dispatch_id, $payload.recipient.dispatchId] | map(select(. != null)) as $payload_dispatches
        | [$message.from, $message.from_handle, $message.fromHandle, $payload.sender.terminal_handle, $payload.sender.terminalHandle, $payload.sender_handle, $payload.senderHandle] | map(select(. != null)) as $message_senders
        | [$payload.sender.role, $payload.sender_role, $payload.senderRole] | map(select(. != null)) as $payload_sender_roles
        | [$message.to, $message.to_handle, $message.toHandle] | map(select(. != null)) as $message_recipients
        | [$payload.recipient.kind, $payload.recipient_kind, $payload.recipientKind] | map(select(. != null)) as $payload_recipient_kinds
        | [$message.thread_id, $message.threadId] | map(select(. != null)) as $native_threads
        | [$payload.message.thread_id, $payload.message.threadId, $payload.thread_id, $payload.threadId] | map(select(. != null)) as $logical_threads
        | [$message.correlation_id, $message.correlationId, $payload.correlation_id, $payload.correlationId] | map(select(. != null)) as $correlations
        | select(
            ($message_ids | length) > 0
            and all($message_ids[]; type == "string" and length > 0)
            and ($message_ids | unique | length) == 1
          )
        | select(
            all($message_types[]; type == "string" and length > 0)
            and ($message_types | unique | length) <= 1
          )
        | select(($message_senders | length) > 0 and all($message_senders[]; . == $worker_handle))
        | select(all($payload_sender_roles[]; . == "worker"))
        | select(($message_recipients | length) > 0 and all($message_recipients[]; . == $coordinator_handle))
        | select(all($payload_recipient_kinds[]; . == "dispatch"))
        | select(($top_runs | length) > 0 and all($top_runs[]; . == $run_id))
        | select(all($top_tasks[]; . == $task_id))
        | select(all($top_dispatches[]; . == $dispatch_id))
        | select(all($payload_runs[]; . == $run_id))
        | select(all($payload_tasks[]; . == $task_id))
        | select(all($payload_dispatches[]; . == $dispatch_id))
        | select(all($native_threads[]; type == "string" and length > 0) and ($native_threads | unique | length) <= 1)
        | select(all($logical_threads[]; type == "string" and length > 0) and ($logical_threads | unique | length) <= 1)
        | select(all($correlations[]; type == "string" and length > 0) and ($correlations | unique | length) <= 1)
        | select(all($message_recipients[]; type == "string" and length > 0) and ($message_recipients | unique | length) == 1)
        | ((($payload_tasks | length) > 0) and (($payload_dispatches | length) > 0)) as $structured_payload
        | (
            $thread_id != ""
            and $correlation_id != ""
            and ($top_tasks | length) == 0
            and ($top_dispatches | length) == 0
            and ($payload_runs | length) == 0
            and ($payload_tasks | length) == 0
            and ($payload_dispatches | length) == 0
            and ($logical_threads | length) == 0
            and ($correlations | length) == 0
            and (($message | has("payload") | not) or $message.payload == null)
            and ($native_threads | length) > 0
            and all($native_threads[]; . == $correlation_id)
          ) as $native_thread_correlation
        | select(
            if $thread_id == "" then
              $structured_payload
            elif $structured_payload then
              ($logical_threads | length) > 0
              and all($logical_threads[]; . == $thread_id)
              and ($correlations | length) > 0
              and all($correlations[]; . == $correlation_id)
              and ($native_threads | length) > 0
              and all($native_threads[]; . == $correlation_id)
            else
              $native_thread_correlation
            end
          )
        | {
            id: $message_ids[0],
            type: (if ($message_types | length) > 0 then $message_types[0] else "unknown" end),
            sender_handle: $worker_handle,
            match_basis: (if $structured_payload then "structured_payload" else "native_thread_correlation" end),
            native_thread_id: (if ($native_threads | length) > 0 then $native_threads[0] else null end),
            thread_id: (if ($logical_threads | length) > 0 then $logical_threads[0] else null end),
            correlation_id: (
              if ($correlations | length) > 0 then $correlations[0]
              elif $native_thread_correlation then $native_threads[0]
              else null end
            )
          }
      ] as $matched
    | . + {
      mao_message_receipt: {
        schema: "multi-agent-orchestration.message-receipt.v1",
        operation: "inbox",
        state: "read_only_snapshot",
        run_id: $run_id,
        task_id: $task_id,
        dispatch_id: $dispatch_id,
        thread_id: (if $thread_id == "" then null else $thread_id end),
        correlation_id: (if $correlation_id == "" then null else $correlation_id end),
        advances_delivery: false,
        observed_message_state: (if ($matched | length) > 0 then "delivered_visible" else "none_visible" end),
        matched_message_count: ($matched | length),
        matched_messages: $matched,
        does_not_prove: ["consumed", "replied", "action_started", "business_completed"]
      }
    }' || {
      echo "PM_MESSAGE_INBOX_RECEIPT_INVALID: Orca did not return a successful JSON inbox snapshot" >&2
      exit 2
    }
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
  local timeout_ms=$(( WAIT_TIMEOUT * 1000 )) result
  if [ "$WORKER_MODE" = "orca_supervised" ]; then
    ensure_coordinator_binding || exit 2
    # A timeout is a liveness checkpoint, not failure. The JSON remains unacknowledged.
    result=$(orca_cli orchestration check --wait \
      --types worker_done,escalation,question --timeout-ms "$timeout_ms" --terminal "$ORCA_COORDINATOR_HANDLE" --json) || return $?
    printf '%s' "$result" | jq -e \
      --arg run_id "$ORCA_RUN_ID" \
      --arg coordinator "$ORCA_COORDINATOR_HANDLE" '
      def aliases($object; $keys):
        [$keys[] as $key | select($object | has($key)) | $object[$key]];
      select(.ok == true and (.result | type) == "object")
      | . as $root
      | (.result.messages // null) as $messages
      | select(($messages | type) == "array")
      | select(
          (.result.count | type) == "number"
          and .result.count >= 0
          and (.result.count | floor) == .result.count
          and .result.count == ($messages | length)
        )
      | select(($messages | length) <= 50)
      | aliases(.result; ["runId", "run_id"]) as $run_ids
      | aliases(.result; ["deliveryId", "delivery_id"]) as $delivery_ids
      | select(
          ($run_ids | length) > 0
          and all($run_ids[]; type == "string" and length > 0 and . == $run_id)
          and ($run_ids | unique | length) == 1
        )
      | select(
          if ($messages | length) == 0 then
            ($delivery_ids | length) > 0
            and all($delivery_ids[]; . == null)
          else
            ($delivery_ids | length) > 0
            and all($delivery_ids[]; type == "string" and length > 0)
            and ($delivery_ids | unique | length) == 1
          end
        )
      | [range(0; $messages | length) as $index
          | $messages[$index]
          | . as $message
          | aliases($message; ["id", "message_id", "messageId"]) as $ids
          | aliases($message; ["type", "message_type", "messageType"]) as $types
          | aliases($message; ["run_id", "runId"]) as $message_runs
          | select(
              ($ids | length) > 0
              and all($ids[]; type == "string" and length > 0)
              and ($ids | unique | length) == 1
              and ($types | length) > 0
              and all($types[]; type == "string" and length > 0)
              and ($types | unique | length) == 1
              and ($message_runs | length) > 0
              and all($message_runs[]; type == "string" and length > 0 and . == $run_id)
              and ($message_runs | unique | length) == 1
            )
          | {
              position: ($index + 1),
              message_id: $ids[0],
              message_type: $types[0],
              required_action: (
                if $types[0] == "question" then "reply_required"
                elif $types[0] == "escalation" then "intervention_required"
                elif $types[0] == "worker_done" then "validate_and_account_terminal"
                else "review_required" end
              )
            }
        ] as $ordered
      | select(($ordered | length) == ($messages | length))
      | $root + {
          mao_delivery_receipt: {
            schema: "multi-agent-orchestration.delivery-receipt.v1",
            operation: "wait",
            state: (if ($messages | length) == 0 then "checkpoint_empty" else "delivery_consumed_unacknowledged" end),
            run_id: $run_id,
            coordinator_handle: $coordinator,
            delivery_id: (if ($messages | length) == 0 then null else $delivery_ids[0] end),
            message_count: ($messages | length),
            fifo_limit: 50,
            ordered_messages: $ordered,
            whole_delivery_must_be_processed_before_ack: true,
            acknowledged: false,
            does_not_prove: ["replied", "guidance_executed", "business_validated", "terminal_accounted"]
          }
        }' || {
      echo "PM_DELIVERY_RECEIPT_INVALID: Orca wait did not return one valid complete FIFO Delivery" >&2
      return 2
    }
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
  local result
  result=$(orca_cli orchestration check --ack "$DELIVERY_ID" --terminal "$ORCA_COORDINATOR_HANDLE" --json) || return $?
  printf '%s' "$result" | jq -e \
    --arg run_id "$ORCA_RUN_ID" \
    --arg coordinator "$ORCA_COORDINATOR_HANDLE" \
    --arg delivery_id "$DELIVERY_ID" '
    def aliases($object; $keys):
      [$keys[] as $key | select($object | has($key)) | $object[$key]];
    select(.ok == true and (.result | type) == "object")
    | . as $root
    | (.result.messages // null) as $messages
    | select(($messages | type) == "array")
    | aliases(.result; ["runId", "run_id"]) as $run_ids
    | aliases(.result; ["acknowledged", "acknowledgedDeliveryId", "acknowledged_delivery_id"]) as $ack_ids
    | aliases(.result; ["deliveryId", "delivery_id"]) as $next_delivery_ids
    | select(
        ($run_ids | length) > 0
        and all($run_ids[]; type == "string" and length > 0 and . == $run_id)
        and ($run_ids | unique | length) == 1
        and ($ack_ids | length) > 0
        and all($ack_ids[]; type == "string" and length > 0 and . == $delivery_id)
        and ($ack_ids | unique | length) == 1
      )
    | select(
        (.result.count | type) == "number"
        and .result.count >= 0
        and (.result.count | floor) == .result.count
        and .result.count == ($messages | length)
        and ($messages | length) <= 50
      )
    | select(
        if ($messages | length) == 0 then
          ($next_delivery_ids | length) > 0
          and all($next_delivery_ids[]; . == null)
        else
          ($next_delivery_ids | length) > 0
          and all($next_delivery_ids[]; type == "string" and length > 0)
          and ($next_delivery_ids | unique | length) == 1
          and all($next_delivery_ids[]; . != $delivery_id)
        end
      )
    | [range(0; $messages | length) as $index
        | $messages[$index]
        | . as $message
        | aliases($message; ["id", "message_id", "messageId"]) as $ids
        | aliases($message; ["type", "message_type", "messageType"]) as $types
        | aliases($message; ["run_id", "runId"]) as $message_runs
        | select(
            ($ids | length) > 0
            and all($ids[]; type == "string" and length > 0)
            and ($ids | unique | length) == 1
            and ($types | length) > 0
            and all($types[]; type == "string" and length > 0)
            and ($types | unique | length) == 1
            and ($message_runs | length) > 0
            and all($message_runs[]; type == "string" and length > 0 and . == $run_id)
            and ($message_runs | unique | length) == 1
          )
        | {
            position: ($index + 1),
            message_id: $ids[0],
            message_type: $types[0],
            required_action: (
              if $types[0] == "question" then "reply_required"
              elif $types[0] == "escalation" then "intervention_required"
              elif $types[0] == "worker_done" then "validate_and_account_terminal"
              else "review_required" end
            )
          }
      ] as $ordered
    | select(($ordered | length) == ($messages | length))
    | $root + {
        mao_delivery_receipt: {
          schema: "multi-agent-orchestration.delivery-receipt.v1",
          operation: "ack",
          state: "delivery_acknowledged",
          run_id: $run_id,
          coordinator_handle: $coordinator,
          acknowledged_delivery_id: $delivery_id,
          next_delivery_id: (if ($messages | length) == 0 then null else $next_delivery_ids[0] end),
          next_message_count: ($messages | length),
          next_ordered_messages: $ordered,
          next_delivery_acknowledged: false,
          whole_next_delivery_must_be_processed_before_ack: true,
          does_not_prove: ["all_messages_processed", "questions_replied", "business_validated", "terminal_accounted"]
        }
      }' || {
    echo "PM_DELIVERY_ACK_NOT_VERIFIED: Orca did not positively acknowledge the exact Run and requested Delivery" >&2
    return 2
  }
}

cmd_reply() {
  [ "$WORKER_MODE" = "orca_supervised" ] || { echo "ERROR: reply requires an Orca supervised worker" >&2; exit 64; }
  [ -n "$MESSAGE_ID" ] || { echo "ERROR: reply requires --message-id" >&2; exit 64; }
  local text
  text=$(load_text)
  if [ -n "$REPLY_RETRY_REQUEST" ]; then
    if message_contract_sensitive "$REPLY_RETRY_REQUEST"; then
      echo "PM_REPLY_RETRY_SENSITIVE_REJECTED: --retry-request resembles sensitive authentication material" >&2
      return 64
    fi
    if ! orca_retry_request_valid "$REPLY_RETRY_REQUEST"; then
      echo "PM_REPLY_RETRY_INVALID: --retry-request must be the UUID Orca reported for the exact unknown-outcome reply; omit it on a new reply" >&2
      return 64
    fi
  fi
  verify_message_dispatch_binding inspect || return $?
  ensure_coordinator_binding || exit 2
  local target_delivery reply_delivery_id
  target_delivery=$(orca_cli orchestration check --terminal "$ORCA_COORDINATOR_HANDLE" --json) || return $?
  reply_delivery_id=$(printf '%s' "$target_delivery" | jq -er \
    --arg run_id "$ORCA_RUN_ID" \
    --arg task_id "$ORCA_TASK_ID" \
    --arg dispatch_id "$ORCA_DISPATCH_ID" \
    --arg message_id "$MESSAGE_ID" '
    def aliases($object; $keys):
      [$keys[] as $key | select($object | has($key)) | $object[$key]];
    select(.ok == true and (.result | type) == "object")
    | (.result.messages // null) as $messages
    | select(($messages | type) == "array")
    | aliases(.result; ["runId", "run_id"]) as $delivery_runs
    | aliases(.result; ["deliveryId", "delivery_id"]) as $delivery_ids
    | select(
        (.result.count | type) == "number"
        and .result.count >= 1
        and (.result.count | floor) == .result.count
        and .result.count == ($messages | length)
        and ($messages | length) <= 50
        and ($delivery_runs | length) > 0
        and all($delivery_runs[]; type == "string" and length > 0 and . == $run_id)
        and ($delivery_runs | unique | length) == 1
        and ($delivery_ids | length) > 0
        and all($delivery_ids[]; type == "string" and length > 0)
        and ($delivery_ids | unique | length) == 1
      )
    | ([$messages[]
        | . as $candidate
        | aliases($candidate; ["id", "message_id", "messageId"]) as $candidate_ids
        | select(any($candidate_ids[]; . == $message_id))
      ]) as $target_rows
    | select(($target_rows | length) == 1)
    | [$target_rows[]
      | . as $message
        | aliases($message; ["id", "message_id", "messageId"]) as $ids
        | aliases($message; ["type", "message_type", "messageType"]) as $types
        | aliases($message; ["run_id", "runId"]) as $runs
        | aliases($message; ["from_handle", "fromHandle", "from"]) as $senders
        | aliases($message; ["to_handle", "toHandle", "to"]) as $recipients
        | aliases($message; ["thread_id", "threadId"]) as $threads
        | ($message.payload | if type == "string" then try fromjson catch null else null end) as $payload
        | aliases($payload; ["task_id", "taskId"]) as $tasks
        | aliases($payload; ["dispatch_id", "dispatchId"]) as $dispatches
        | select(
            ($ids | length) > 0
            and all($ids[]; type == "string" and length > 0 and . == $message_id)
            and ($ids | unique | length) == 1
            and ($types | length) > 0
            and all($types[]; . == "question")
            and ($types | unique | length) == 1
            and ($runs | length) > 0
            and all($runs[]; type == "string" and length > 0 and . == $run_id)
            and ($runs | unique | length) == 1
            and ($payload | type) == "object"
            and ($tasks | length) > 0
            and all($tasks[]; type == "string" and length > 0 and . == $task_id)
            and ($tasks | unique | length) == 1
            and ($dispatches | length) > 0
            and all($dispatches[]; type == "string" and length > 0 and . == $dispatch_id)
            and ($dispatches | unique | length) == 1
            and ($senders | length) > 0
            and all($senders[]; type == "string" and . == ("dispatch:" + $dispatch_id))
            and ($senders | unique | length) == 1
            and ($recipients | length) > 0
            and all($recipients[]; type == "string" and . == ("run:" + $run_id))
            and ($recipients | unique | length) == 1
            and ($threads | length) > 0
            and all($threads[]; type == "string" and . == $message_id)
            and ($threads | unique | length) == 1
          )
      ]
    | select(length == 1)
    | $delivery_ids[0]') || {
    echo "PM_REPLY_TARGET_INVALID: message must be one question in the current unacknowledged Delivery for this exact Run/Dispatch/worker" >&2
    return 2
  }
  local args=(orchestration reply --id "$MESSAGE_ID" --body "$text" --from "$ORCA_COORDINATOR_HANDLE")
  [ -z "$REPLY_RETRY_REQUEST" ] || args+=(--retry-request "$REPLY_RETRY_REQUEST")
  local result
  result=$(orca_cli "${args[@]}" --json) || return $?
  printf '%s' "$result" | jq -e \
    --arg run_id "$ORCA_RUN_ID" \
    --arg task_id "$ORCA_TASK_ID" \
    --arg dispatch_id "$ORCA_DISPATCH_ID" \
    --arg worker_handle "$WORKER_HANDLE" \
    --arg coordinator "$ORCA_COORDINATOR_HANDLE" \
    --arg source_delivery_id "$reply_delivery_id" \
    --arg question_message_id "$MESSAGE_ID" \
    --arg answer_body "$text" \
    --arg retry_request "$REPLY_RETRY_REQUEST" '
    def aliases($object; $keys):
      [$keys[] as $key | select($object | has($key)) | $object[$key]];
    select(.ok == true and (.result.message | type) == "object")
    | aliases(.result.message; ["id", "message_id", "messageId"]) as $reply_ids
    | aliases(.result.message; ["run_id", "runId"]) as $reply_runs
    | aliases(.result.message; ["from_handle", "fromHandle", "from"]) as $reply_senders
    | aliases(.result.message; ["to_handle", "toHandle", "to"]) as $reply_recipients
    | aliases(.result.message; ["thread_id", "threadId"]) as $reply_threads
    | aliases(.result.message; ["body"]) as $reply_bodies
    | aliases(.result.question; ["message_id", "messageId"]) as $question_ids
    | aliases(.result.question; ["run_id", "runId"]) as $question_runs
    | aliases(.result.question; ["dispatch_id", "dispatchId"]) as $question_dispatches
    | aliases(.result.question; ["asker_handle", "askerHandle"]) as $question_askers
    | aliases(.result.question; ["answer_message_id", "answerMessageId"]) as $answer_ids
    | aliases(.result.question; ["answer_body", "answerBody"]) as $answer_bodies
    | select(
        (.result.question | type) == "object"
        and ($reply_ids | length) > 0
        and all($reply_ids[]; type == "string" and length > 0)
        and ($reply_ids | unique | length) == 1
        and all($reply_ids[]; . != $question_message_id)
        and ($reply_runs | length) > 0
        and all($reply_runs[]; . == $run_id)
        and ($reply_runs | unique | length) == 1
        and ($reply_senders | length) > 0
        and all($reply_senders[]; . == ("run:" + $run_id))
        and ($reply_senders | unique | length) == 1
        and ($reply_recipients | length) > 0
        and all($reply_recipients[]; . == ("dispatch:" + $dispatch_id))
        and ($reply_recipients | unique | length) == 1
        and ($reply_threads | length) > 0
        and all($reply_threads[]; . == $question_message_id)
        and ($reply_threads | unique | length) == 1
        and ($reply_bodies | length) > 0
        and all($reply_bodies[]; . == $answer_body)
        and ($question_ids | length) > 0
        and all($question_ids[]; . == $question_message_id)
        and ($question_ids | unique | length) == 1
        and ($question_runs | length) > 0
        and all($question_runs[]; . == $run_id)
        and ($question_runs | unique | length) == 1
        and ($question_dispatches | length) > 0
        and all($question_dispatches[]; . == $dispatch_id)
        and ($question_dispatches | unique | length) == 1
        and ($question_askers | length) > 0
        and all($question_askers[]; . == $worker_handle)
        and ($question_askers | unique | length) == 1
        and .result.question.status == "answered"
        and ($answer_ids | length) > 0
        and all($answer_ids[]; . == $reply_ids[0])
        and ($answer_ids | unique | length) == 1
        and ($answer_bodies | length) > 0
        and all($answer_bodies[]; . == $answer_body)
        and (.result | has("duplicate"))
        and (.result.duplicate | type) == "boolean"
      )
    | . + {
        mao_reply_receipt: {
          schema: "multi-agent-orchestration.reply-receipt.v1",
          state: (if (.result.duplicate // false) then "reply_existing_same_answer" else "reply_committed" end),
          run_id: $run_id,
          task_id: $task_id,
          dispatch_id: $dispatch_id,
          worker_handle: $worker_handle,
          coordinator_handle: $coordinator,
          source_delivery_id: $source_delivery_id,
          question_message_id: $question_message_id,
          reply_message_id: $reply_ids[0],
          duplicate: (.result.duplicate // false),
          retry_request: (if $retry_request == "" then null else $retry_request end),
          does_not_prove: ["worker_consumed_reply", "guidance_executed", "business_completed"]
        }
      }' || {
    echo "PM_REPLY_RECEIPT_INVALID: Orca did not return a successful reply message receipt" >&2
    return 2
  }
}

cmd_account() {
  [ "$WORKER_MODE" = "orca_supervised" ] || { echo "ERROR: $COMMAND requires an Orca supervised worker" >&2; exit 64; }
  ensure_coordinator_binding || exit 2
  local result
  result=$(orca_cli orchestration "worker-$COMMAND" --dispatch "$ORCA_DISPATCH_ID" --json) || return $?
  printf '%s\n' "$result"
  if [ "$COMMAND" = "release" ] && [ -n "$PROVIDER_LEASE_FILE" ]; then
    local workers terminal_state lease_root
    workers=$(orca_cli orchestration worker-list --run "$ORCA_RUN_ID" --json 2>/dev/null || echo '{}')
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
# Task-113：TASK_REUSED 不再固定解释为「仍 dispatched」。注册返回 TASK_REUSED 时按
#   预检状态有界区分：failed/settled（worker_done 结算后的残留态）复核一致后复位
#   ready 并只重试一次注册；dispatched 维持单活 fencing 回滚；unknown/漂移 fail-closed。
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
  check_out=$(orca_cli orchestration check --terminal "$ORCA_COORDINATOR_HANDLE" --json 2>/dev/null) || check_out=""
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
  if orca_cli orchestration reply --id "$msg_id" --body "$body" --from "$ORCA_COORDINATOR_HANDLE" --json >/dev/null 2>&1; then
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

# reauthorize 必须复用原始 spawn 在 Git common-dir 冻结的 PM authority receipt。
# receipt 路径由 worktree/session 推导，METADATA 只做交叉核对，不能选择授权来源；
# 校验在 run-use、授权合并、launch.sh 改写和新终端创建等副作用之前完成。
resolve_reauthorize_authority_receipt() {
  resolve_project_identity || return 2
  local expected="$GIT_COMMON_DIR/agent-authority/$SESSION.json"
  python3 - "$SCRIPT_DIR" "$WORKTREE" "$SESSION" "$METADATA" "$expected" <<'PY'
import json
from pathlib import Path
import stat
import subprocess
import sys

sys.path.insert(0, sys.argv[1])
from completion_authority import load_authority

worktree = Path(sys.argv[2])
session = sys.argv[3]
metadata = Path(sys.argv[4])
authority = Path(sys.argv[5])

def git(*args):
    return subprocess.run(
        ["git", "-C", str(worktree), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

try:
    if Path(git("rev-parse", "--show-toplevel")).resolve(strict=True) != worktree:
        raise ValueError("worktree must be the exact Git root")
    branch = git("symbolic-ref", "--quiet", "--short", "HEAD")
    current = worktree
    for part in metadata.relative_to(worktree).parts:
        current = current / part
        if stat.S_ISLNK(current.lstat().st_mode):
            raise ValueError("Session Context must not contain symlinks")
    data = json.loads(metadata.read_text(encoding="utf-8"))
    receipt, _ = load_authority(str(authority))
    if receipt.get("session") != session or receipt.get("branch") != branch:
        raise ValueError("PM receipt session/branch does not match the worker")
    if not isinstance(receipt.get("worktree"), str) or Path(receipt["worktree"]).resolve(strict=True) != worktree:
        raise ValueError("PM receipt belongs to a different worktree")
    if data.get("session", {}).get("id") != session or data.get("worktree") != str(worktree):
        raise ValueError("Session Context identity does not match the worker")
    if data.get("execution_authority", {}).get("authority_receipt_file") != str(authority):
        raise ValueError("metadata cannot select a different PM authority receipt")
    print(authority)
except (AttributeError, KeyError, OSError, TypeError, ValueError, subprocess.SubprocessError) as exc:
    print("PM_REAUTHORIZE_AUTHORITY_INVALID: " + str(exc), file=sys.stderr)
    raise SystemExit(1)
PY
}

# Task-116（Badminton Lab 实测事故①）：reauthorize liveness 预门禁。
# 旧 Dispatch 已 worker_done → release → ack → settled 后，METADATA 残留的 dispatch_id
# 会让本命令把死目标当 live：先合并授权、重写 launch.sh B64、创建替换终端，直到注册
# 阶段才发现目标已结算并回滚——授权/终端副作用全部白做。本预门禁在任何 mutation
# （包括 ensure_coordinator_binding 的 run-use/METADATA 改写）之前读取权威 Dispatch
# 状态（worker-show）：只有调用可达、Dispatch 记录仍存在、且未进入结算链
# （terminalResource.releaseState 仍是 not_requested/缺省）的 live 目标才允许继续；
# released/released_retained/settled、记录缺失、调用失败等其余一切状态一律输出稳定
# 机器码 REAUTHORIZE_NOT_LIVE 并零副作用退出（fail-closed）。已有 Worktree/Task 的
# 恢复必须走 reauthorize（仅限 live 目标）/quota-park/明确恢复入口，不在死目标上做副作用。
reauthorize_liveness_pregate() {
  local show_json show_rc release_state dispatch_status
  set +e
  show_json=$(orca_cli orchestration worker-show --dispatch "$ORCA_DISPATCH_ID" --json 2>&1)
  show_rc=$?
  set -e
  if [ "$show_rc" -ne 0 ]; then
    echo "REAUTHORIZE_NOT_LIVE: worker-show 不可达（rc=${show_rc}），无法证明 Dispatch 仍 live；未知状态 fail-closed，未做任何变更" >&2
    exit 2
  fi
  if [ -z "$(printf '%s' "$show_json" | jq -r '.result.dispatch.id // empty' 2>/dev/null)" ]; then
    echo "REAUTHORIZE_NOT_LIVE: worker-show 无 Dispatch 记录（已 GC 或契约不完整），无法证明仍 live；零副作用拒绝" >&2
    exit 2
  fi
  release_state=$(printf '%s' "$show_json" | jq -r '.result.terminalResource.releaseState // .result.terminal_resource.releaseState // empty' 2>/dev/null)
  dispatch_status=$(printf '%s' "$show_json" | jq -r '.result.dispatch.status // empty' 2>/dev/null)
  case "$release_state" in
    ""|null|"not_requested") ;;
    *)
      echo "REAUTHORIZE_NOT_LIVE: Dispatch 已进入结算链（releaseState=${release_state}），worker_done 已被 release/ack/settled；请按正常收口处理或走明确恢复入口，reauthorize 零副作用拒绝" >&2
      exit 2
      ;;
  esac
  if [ "$dispatch_status" = "settled" ]; then
    echo "REAUTHORIZE_NOT_LIVE: Dispatch status=settled（worker_done 已结算），reauthorize 零副作用拒绝" >&2
    exit 2
  fi
  echo "PM_REAUTHORIZE_LIVENESS_OK: dispatch=$ORCA_DISPATCH_ID releaseState=${release_state:-not_requested} status=${dispatch_status:-unknown}"
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
  local authority_receipt
  [ -f "$auth_file" ] || { echo "ERROR: authorization file not found: $auth_file" >&2; exit 64; }
  [ -f "$launch_sh" ] || { echo "ERROR: launch.sh not found: $launch_sh" >&2; exit 64; }
  authority_receipt=$(resolve_reauthorize_authority_receipt) || {
    echo "ERROR: original PM authority receipt is missing, mismatched or untrusted; reauthorize made no changes" >&2
    exit 2
  }
  # Task-116：任何 mutation（run-use/METADATA 改写、授权合并、B64 重写、新终端）之前
  # 先证明目标 Dispatch 仍 live；settled/released/acked/未知一律 REAUTHORIZE_NOT_LIVE。
  reauthorize_liveness_pregate
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
      --coordinator-handle "$ORCA_COORDINATOR_HANDLE" \
      --runtime-id "$ORCA_RECORDED_RUNTIME_ID" \
      --metadata-file "$METADATA" \
      --authority-receipt "$authority_receipt" 2>&1); then
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
        --coordinator-handle "$ORCA_COORDINATOR_HANDLE" \
        --runtime-id "$ORCA_RECORDED_RUNTIME_ID" \
        --metadata-file "$METADATA" \
        --authority-receipt "$authority_receipt" 2>&1) || {
        reauthorize_rollback_new_terminal "$new_handle" "复位后重注册仍失败"
        echo "ERROR: re-registration failed after task reset: $register_out" >&2
        exit 2
      }
    elif printf '%s' "$register_out" | grep -qi "task_reused"; then
      # Task-081 ③ + Task-113：TASK_REUSED 有两种互斥语义，按 Step 0 预检状态有界区分，
      # 不放宽任何身份/fencing/Delivery 门槛：
      #   a) 真单活（预检 dispatched）：活 Dispatch 未结算，worker-start 必被拒 →
      #      维持回滚新终端 + manual-recovery 指引（等待已在 Step 0 消费）。
      #   b) 已结算残留（Task-113 实测：worker_done outcome=failed 结算、Delivery
      #      release+ack 之后 task=failed/dispatch settled，注册仍返回 TASK_REUSED）：
      #      旧实现固定解释为仍 dispatched，已结算任务永远无法换终端恢复。此处先复核
      #      一次状态，仅当复核仍是 failed/settled 才复位 ready 并只重试一次注册。
      #   其余（unknown/其他）：无法区分真单活与结算残留，fail-closed 回滚不复位。
      if [ "$reauth_task_state" = "failed" ] || [ "$reauth_task_state" = "settled" ]; then
        local recheck_state
        recheck_state=$(reauthorize_task_state "$task_id")
        if [ "$recheck_state" != "failed" ] && [ "$recheck_state" != "settled" ]; then
          reauthorize_rollback_new_terminal "$new_handle" "TASK_REUSED 复核状态漂移（${reauth_task_state} → ${recheck_state}）"
          echo "PM_REAUTHORIZE_TASK_STATE_DRIFT: task $task_id 预检 ${reauth_task_state} → 复核 ${recheck_state}，疑似真单活出现"
          echo "ERROR: task $task_id 状态漂移（${reauth_task_state} → ${recheck_state}），fail-closed 不复位" >&2
          exit 2
        fi
        echo "PM_REAUTHORIZE_TASK_RESET: task $task_id 已结算（${reauth_task_state}）且复核一致，TASK_REUSED 为结算残留；复位 ready 重试一次"
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
          --coordinator-handle "$ORCA_COORDINATOR_HANDLE" \
          --runtime-id "$ORCA_RECORDED_RUNTIME_ID" \
          --metadata-file "$METADATA" \
          --authority-receipt "$authority_receipt" 2>&1) || {
          reauthorize_rollback_new_terminal "$new_handle" "复位后重注册仍失败"
          echo "ERROR: re-registration failed after settled-task reset: $register_out" >&2
          exit 2
        }
      elif [ "$reauth_task_state" = "dispatched" ]; then
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
        # unknown/其他状态：不猜测语义，fail-closed（不比旧实现差，仅补充状态指引）。
        reauthorize_rollback_new_terminal "$new_handle" "task 状态 ${reauth_task_state} 下 TASK_REUSED 语义不可判定"
        {
          echo "PM_REAUTHORIZE_REGISTER_TASK_REUSED: task $task_id 预检状态为 ${reauth_task_state}（非 dispatched，也非 failed/settled），无法安全区分单活 fencing 与结算残留，fail-closed 不复位"
          echo "PM_REAUTHORIZE_MANUAL_RECOVERY: 已回滚新终端。先人工核实状态：orca orchestration task-list --run $ORCA_RUN_ID --json；确认已结算（failed/settled）后重跑本命令即走 Task-113 复位恢复链，确认仍 dispatched 则按 runbook #18 三步补绑处理"
        } >&2
        exit 2
      fi
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
  inbox) cmd_inbox ;;
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
