#!/usr/bin/env bash
# Register an existing Orca agent terminal into one supervised Run/Task/Dispatch.
# worker-start is the only prompt injector on this path.
#
# Task-106（旧发布别名 Task-076-Dispatch）：worker-start 成功后的 Dispatch 绑定自检与自动补绑。
# Run/Task/worker-start 阶段失败仍然 exit 1 fail-loud；仅「dispatch 绑定缺失」
# （worker-start 成功、receipt 与 dispatch-show 均无 id）改为自动补绑三步，
# 并以 ORCAREG_DISPATCH_BIND=ok|manual-required 显式汇报，manual-required
# 不再以 exit 1 阻断 spawn（terminal/任务注入已生效，阻断只会制造半活 worker）。
#
# Task-092：手动 register 也要把 supervised 路由写回 Session Context。
# 脚本用 Orca 返回的精确 worktree path + terminal_handle 自动定位唯一
# METADATA.json；找不到或出现歧义时不重试 worker-start，只显式要求手工补写。

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

patch_supervised_metadata() {
  local show_out resolved_identity resolved_id resolved_path metadata_root candidate
  local tmp_meta
  local -a matches=()

  ORCAREG_METADATA_BIND="manual-required"

  if ! show_out=$(orca_cli worktree show --worktree "id:$WORKTREE_ID" --json 2>&1); then
    echo "ORCAREG_METADATA_LOOKUP_FAILED: worktree show 失败；worker 已注册，请按 runbook 手工补写 METADATA: $show_out" >&2
    return 0
  fi
  if ! resolved_identity=$(printf '%s' "$show_out" | jq -er '
    .result.worktree
    | select(type == "object")
    | [.id, .path]
    | select(all(.[]; type == "string" and length > 0))
    | @tsv
  ' 2>/dev/null); then
    echo "ORCAREG_METADATA_LOOKUP_FAILED: Orca worktree JSON 非法或缺少 id/path；worker 已注册，请按 runbook 手工补写 METADATA" >&2
    return 0
  fi
  IFS=$'\t' read -r resolved_id resolved_path <<< "$resolved_identity"
  if [ "$resolved_id" != "$WORKTREE_ID" ] || [ ! -d "$resolved_path" ]; then
    echo "ORCAREG_METADATA_LOOKUP_FAILED: Orca worktree identity/path 缺失或错配；worker 已注册，请按 runbook 手工补写 METADATA" >&2
    return 0
  fi

  metadata_root="$resolved_path/.claude/agent-sessions"
  if [ ! -d "$metadata_root" ] || [ -L "$metadata_root" ]; then
    echo "ORCAREG_METADATA_NOT_FOUND: $metadata_root 不存在或是符号链接；worker 已注册，请按 runbook 手工补写 METADATA" >&2
    return 0
  fi

  while IFS= read -r -d '' candidate; do
    [ -f "$candidate" ] && [ ! -L "$candidate" ] || continue
    if jq -e --arg terminal "$TERMINAL_HANDLE" --arg worktree "$WORKTREE_ID" \
      '.session.orca.terminal_handle == $terminal
       and (.session.orca.worktree_id // $worktree) == $worktree' \
      "$candidate" >/dev/null 2>&1; then
      matches+=("$candidate")
    fi
  done < <(find "$metadata_root" -mindepth 2 -maxdepth 2 -type f -name METADATA.json -print0 2>/dev/null)

  if [ "${#matches[@]}" -ne 1 ]; then
    echo "ORCAREG_METADATA_AMBIGUOUS: terminal=$TERMINAL_HANDLE 匹配 ${#matches[@]} 个 METADATA.json；worker 已注册，请按 runbook 手工补写" >&2
    return 0
  fi

  candidate="${matches[0]}"
  tmp_meta=$(mktemp "${candidate}.tmp.XXXXXX") || {
    echo "ORCAREG_METADATA_WRITE_FAILED: 无法创建同目录临时文件；worker 已注册，请按 runbook 手工补写" >&2
    return 0
  }
  if jq --arg run "$RUN_ID" --arg task "$TASK_ID" --arg disp "$DISPATCH_ID" \
    --arg coordinator "$COORDINATOR_HANDLE" --arg bind "$DISPATCH_BIND" \
    '.session.orca.supervised = {run_id: $run, coordinator_handle: $coordinator, task_id: $task, dispatch_id: $disp, dispatch_bind: $bind, contract: "orca.orchestration.contract.v1", completion_authority: "worker_done", terminal_ownership: "external"}' \
    "$candidate" > "$tmp_meta" && mv "$tmp_meta" "$candidate"; then
    ORCAREG_METADATA_BIND="ok"
    echo "ORCAREG_METADATA_UPDATED: $candidate" >&2
  else
    rm -f "$tmp_meta"
    echo "ORCAREG_METADATA_WRITE_FAILED: worker 已注册但 METADATA 原子写回失败，请按 runbook 手工补写" >&2
  fi
}

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

# Task-106/Task-107：worker-start 成功后的 Dispatch 绑定自检。
# 实现已抽公共函数 orchestration_dispatch_bind_selfcheck（orca-supervised-protocol.sh），
# 与 spawn-worker-launch.sh 的 launch 路径共用同一份；此处只做调用与 KV 导出。
orchestration_dispatch_bind_selfcheck "$TASK_ID" "$TERMINAL_HANDLE" "$RUN_ID" "$start_out"
DISPATCH_ID="$ORCAREG_BIND_DISPATCH_ID"
DISPATCH_BIND="$ORCAREG_BIND_STATUS"
patch_supervised_metadata

echo "ORCAREG_WORKER_REGISTERED: dispatch=${DISPATCH_ID:-none} bind=$DISPATCH_BIND" >&2
printf 'ORCAREG_RUN_ID=%s\n' "$RUN_ID"
printf 'ORCAREG_COORDINATOR_HANDLE=%s\n' "$COORDINATOR_HANDLE"
printf 'ORCAREG_TASK_ID=%s\n' "$TASK_ID"
printf 'ORCAREG_DISPATCH_ID=%s\n' "$DISPATCH_ID"
printf 'ORCAREG_DISPATCH_BIND=%s\n' "$DISPATCH_BIND"
printf 'ORCAREG_METADATA_BIND=%s\n' "$ORCAREG_METADATA_BIND"
