#!/usr/bin/env bash
# Register an existing Orca agent terminal into one supervised Run/Task/Dispatch.
# worker-start is the only prompt injector on this path.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=orca-runtime.sh
source "$SCRIPT_DIR/orca-runtime.sh"
# shellcheck source=orca-supervised-protocol.sh
source "$SCRIPT_DIR/orca-supervised-protocol.sh"

WORKTREE_ID=""
TERMINAL_HANDLE=""
TASK_SPEC=""
TASK_TITLE=""
TASK_ID=""
RUN_ID=""
OBJECTIVE=""
TIMEOUT_MS=60000
RESET_FAILED=0
COORDINATOR_HANDLE=""

usage() {
  cat >&2 <<'USAGE'
Usage:
  orca-supervised-register.sh --worktree-id ID --terminal-handle HANDLE --task-spec TEXT [options]

Required:
  --worktree-id ID         Exact Orca worktree id
  --terminal-handle HANDLE Existing terminal running an Orca-recognized agent
  --task-spec TEXT         Complete worker task (required unless --task-id is supplied)

Optional:
  --task-title TEXT        Concise task title
  --run-id ID              Reuse one Run for all workers in a Wave
  --task-id ID             Reuse a Task created by orca-wave-prepare.sh
  --coordinator-handle ID  Reuse the coordinator handle from the Wave receipt;
                           required with --task-id to avoid concurrent run-use rebinding
  --objective TEXT         Objective for a newly created Run
  --timeout-ms N           worker-start readiness timeout (default: 60000)
  --reset-failed           When worker-start is rejected with task_not_startable
                           (Task flipped to failed/blocked by a prior worker's ask
                           or abort), reset that Task to ready once and retry
                           registration (Task-060; badminton-lab Wave 2 lesson)

Stdout contains only shell-safe KEY=VALUE receipts.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --worktree-id) WORKTREE_ID="$2"; shift 2 ;;
    --terminal-handle) TERMINAL_HANDLE="$2"; shift 2 ;;
    --task-spec) TASK_SPEC="$2"; shift 2 ;;
    --task-title) TASK_TITLE="$2"; shift 2 ;;
    --task-id) TASK_ID="$2"; shift 2 ;;
    --run-id) RUN_ID="$2"; shift 2 ;;
    --coordinator-handle) COORDINATOR_HANDLE="$2"; shift 2 ;;
    --objective) OBJECTIVE="$2"; shift 2 ;;
    --timeout-ms) TIMEOUT_MS="$2"; shift 2 ;;
    --reset-failed) RESET_FAILED=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage; exit 64 ;;
  esac
done

[ -n "$WORKTREE_ID" ] || { echo "ERROR: --worktree-id is required" >&2; exit 64; }
[ -n "$TERMINAL_HANDLE" ] || { echo "ERROR: --terminal-handle is required" >&2; exit 64; }
[ -n "$TASK_SPEC" ] || [ -n "$TASK_ID" ] || { echo "ERROR: --task-spec or --task-id is required" >&2; exit 64; }
[ -z "$TASK_ID" ] || [ -n "$RUN_ID" ] || { echo "ERROR: --task-id requires --run-id" >&2; exit 64; }
[ -z "$TASK_ID" ] || [ -n "$COORDINATOR_HANDLE" ] || { echo "ERROR: --task-id requires --coordinator-handle from the Wave receipt" >&2; exit 64; }
[[ "$TIMEOUT_MS" =~ ^[0-9]+$ ]] || { echo "ERROR: --timeout-ms must be an integer" >&2; exit 64; }
command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required" >&2; exit 64; }
orca_runtime_init

[ -n "$TASK_TITLE" ] || TASK_TITLE="spawn-worker supervised worker"
[ -n "$OBJECTIVE" ] || OBJECTIVE="$TASK_SPEC"

if [ -z "$RUN_ID" ]; then
  run_out=$(orca_cli orchestration run-create --objective "$OBJECTIVE" --json 2>&1) || {
    echo "ERROR: run-create failed: $run_out" >&2; exit 1; }
  RUN_ID=$(printf '%s' "$run_out" | jq -r '.result.run.id // empty')
  [ -n "$RUN_ID" ] || { echo "ERROR: run-create response missing .result.run.id" >&2; exit 1; }
  COORDINATOR_HANDLE=$(printf '%s' "$run_out" | jq -r '.result.run.coordinator_handle // .result.run.coordinatorHandle // empty')
  echo "ORCAREG_RUN_CREATED: $RUN_ID" >&2
elif [ -z "$COORDINATOR_HANDLE" ]; then
  # Bind the coordinator terminal before adding another task to this Wave Run.
  use_out=$(orca_cli orchestration run-use --id "$RUN_ID" --json 2>&1) || {
    echo "ERROR: run-use failed for $RUN_ID: $use_out" >&2; exit 1; }
  COORDINATOR_HANDLE=$(printf '%s' "$use_out" | jq -r '.result.run.coordinator_handle // .result.run.coordinatorHandle // empty')
fi
[ -n "$COORDINATOR_HANDLE" ] || {
  echo "ERROR: Run receipt missing coordinator handle; cannot satisfy Orca consumer fencing" >&2
  exit 1
}

if [ -z "$TASK_ID" ]; then
  EFFECTIVE_TASK_SPEC=$(orca_supervised_task_spec "$TASK_SPEC")
  task_out=$(orca_cli orchestration task-create --spec "$EFFECTIVE_TASK_SPEC" --task-title "$TASK_TITLE" \
    --run "$RUN_ID" --from "$COORDINATOR_HANDLE" --json 2>&1) || {
    echo "ERROR: task-create failed: $task_out" >&2; exit 1; }
  TASK_ID=$(printf '%s' "$task_out" | jq -r '.result.task.id // empty')
  [ -n "$TASK_ID" ] || { echo "ERROR: task-create response missing .result.task.id" >&2; exit 1; }
  echo "ORCAREG_TASK_CREATED: $TASK_ID" >&2
else
  echo "ORCAREG_TASK_REUSED: $TASK_ID" >&2
fi

worker_start_once() {
  orca_cli orchestration worker-start \
    --task "$TASK_ID" \
    --terminal "$TERMINAL_HANDLE" \
    --worktree "id:$WORKTREE_ID" \
    --run "$RUN_ID" \
    --from "$COORDINATOR_HANDLE" \
    --timeout-ms "$TIMEOUT_MS" \
    --json 2>&1
}

if ! start_out=$(worker_start_once); then
  # Task-060：前任 worker 的 ask/中止会把 Task 翻成 failed，重注册被
  # task_not_startable 拦截（badminton-lab Wave 2 实测）。--reset-failed 时
  # 复位 ready 重试一次；未带旗标保持 fail-closed。
  if [ "$RESET_FAILED" -eq 1 ] && printf '%s' "$start_out" | grep -q "task_not_startable"; then
    echo "ORCAREG_TASK_RESET: task $TASK_ID not startable; resetting to ready and retrying once" >&2
    orca_cli orchestration task-update --id "$TASK_ID" --status ready \
      --run "$RUN_ID" --from "$COORDINATOR_HANDLE" >/dev/null || {
        echo "ERROR: --reset-failed task-update failed for $TASK_ID" >&2
        exit 1
      }
    start_out=$(worker_start_once) || {
      echo "ERROR: worker-start failed after --reset-failed retry: $start_out" >&2
      exit 1
    }
  else
    echo "ERROR: worker-start failed; inspect this exact receipt and residualResources before retrying: $start_out" >&2
    exit 1
  fi
fi

# Prefer the mutation receipt. dispatch-show is a read-only exact recovery if a
# runtime version omits the dispatch id from worker-start's response.
DISPATCH_ID=$(printf '%s' "$start_out" | jq -r '
  .result.dispatch.id
  // .result.worker.dispatch.id
  // .result.dispatchId
  // .result.worker.dispatchId
  // empty' 2>/dev/null)
if [ -z "$DISPATCH_ID" ]; then
  dispatch_out=$(orca_cli orchestration dispatch-show --task "$TASK_ID" --json 2>&1) || {
    echo "ERROR: worker-start succeeded but dispatch-show failed: $dispatch_out" >&2; exit 1; }
  DISPATCH_ID=$(printf '%s' "$dispatch_out" | jq -r '
    .result.dispatch.id
    // .result.dispatch.dispatchId
    // .result.dispatchId
    // empty' 2>/dev/null)
fi
[ -n "$DISPATCH_ID" ] || {
  echo "ERROR: worker-start succeeded but no dispatch id was recoverable; inspect task $TASK_ID" >&2
  exit 1
}

echo "ORCAREG_WORKER_REGISTERED: dispatch=$DISPATCH_ID" >&2
printf 'ORCAREG_RUN_ID=%s\n' "$RUN_ID"
printf 'ORCAREG_COORDINATOR_HANDLE=%s\n' "$COORDINATOR_HANDLE"
printf 'ORCAREG_TASK_ID=%s\n' "$TASK_ID"
printf 'ORCAREG_DISPATCH_ID=%s\n' "$DISPATCH_ID"
