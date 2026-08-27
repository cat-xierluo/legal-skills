#!/usr/bin/env bash
# Register an existing Orca agent terminal into one supervised Run/Task/Dispatch.
# worker-start is the only prompt injector on this path.
#
# Task-076：worker-start 成功后的 Dispatch 绑定自检与自动补绑。
# Run/Task/worker-start 阶段失败仍然 exit 1 fail-loud；仅「dispatch 绑定缺失」
# （worker-start 成功、receipt 与 dispatch-show 均无 id）改为自动补绑三步，
# 并以 ORCAREG_DISPATCH_BIND=ok|manual-required 显式汇报，manual-required
# 不再以 exit 1 阻断 spawn（terminal/任务注入已生效，阻断只会制造半活 worker）。

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

# Task-076：worker-start 成功后的 Dispatch 绑定自检。
# 2026-08-27 三波实战（badminton-lab Wave17/18/19）中，worker-start 拉起 TUI 并注入
# 任务，但 Orca 不识别终端内 agent（agent_unconfigured / no recognized agent 家族）
# 导致 Dispatch 未绑——Task 停 [ready]、dispatch-show --task 为空、worker_done 无通道。
# 该缺口此前只能靠 PM 人肉发现并按 runbook #18 三步补绑；现在 spawn 收尾主动核对，
# 为空时自动补绑，并把结果以 ORCAREG_DISPATCH_BIND=ok|manual-required 汇报给调用方。
DISPATCH_BIND="ok"
receipt_id=$(printf '%s' "$start_out" | jq -r '
  .result.dispatch.id
  // .result.worker.dispatch.id
  // .result.dispatchId
  // .result.worker.dispatchId
  // empty' 2>/dev/null || true)
# 主动只读核对（旧 runtime 缺 dispatch-show 子命令时容错为空，不阻断）。
show_out=$(orca_cli orchestration dispatch-show --task "$TASK_ID" --json 2>&1) || show_out=""
show_id=$(printf '%s' "$show_out" | jq -r '
  .result.dispatch.id
  // .result.dispatch.dispatchId
  // .result.dispatchId
  // empty' 2>/dev/null || true)
if [ -n "$show_id" ]; then
  DISPATCH_ID="$show_id"
  if [ -n "$receipt_id" ] && [ "$receipt_id" != "$show_id" ]; then
    echo "WARN: worker-start receipt dispatch ($receipt_id) differs from dispatch-show ($show_id); using dispatch-show as canonical" >&2
  fi
elif [ -n "$receipt_id" ]; then
  DISPATCH_ID="$receipt_id"
  echo "ORCAREG_DISPATCH_SHOW_EMPTY: dispatch-show 未回显 id，按 worker-start mutation receipt 采信: $receipt_id" >&2
else
  # 绑定缺失：按 runbook #18 自动补绑三步。
  # ① dispatch 无 --inject 建绑定并返回 preamble（agent 不被识别时 --inject 会直接报错）
  # ② 从响应/preamble 提取真实 ctx id ③ 单行 terminal send 注入 worker_done/ask 命令形式
  echo "ORCAREG_DISPATCH_MISSING: worker-start 成功但 dispatch 绑定缺失（receipt 与 dispatch-show 均为空）；执行 runbook #18 三步自动补绑" >&2
  rebind_out=""
  rebind_out=$(orca_cli orchestration dispatch --task "$TASK_ID" --to "$TERMINAL_HANDLE" \
    --run "$RUN_ID" --return-preamble 2>&1) || rebind_out=""
  if [ -n "$rebind_out" ]; then
    printf 'ORCAREG_DISPATCH_REBIND_RECEIPT: %s\n' "$rebind_out" >&2
  fi
  rebind_id=$(printf '%s' "$rebind_out" | jq -r '
    .result.dispatch.id
    // .result.dispatch.dispatchId
    // .result.dispatchId
    // .result.worker.dispatch.id
    // empty' 2>/dev/null || true)
  if [ -z "$rebind_id" ]; then
    # 响应可能不是 JSON（--return-preamble 文本形态）：从 preamble 提取 ctx id；
    # 出现多个不同 ctx id 时视为歧义，宁拒不猜（PM 手动裁定）。
    rebind_id=$(printf '%s' "$rebind_out" | grep -oE 'ctx_[A-Za-z0-9_-]+' | sort -u | sed -n '1p' || true)
    rebind_unique=$(printf '%s' "$rebind_out" | grep -oE 'ctx_[A-Za-z0-9_-]+' | sort -u | wc -l | tr -d ' ' || true)
    if [ "${rebind_unique:-0}" -gt 1 ]; then
      echo "WARN: 补绑响应含 ${rebind_unique} 个不同 ctx id，拒绝猜测" >&2
      rebind_id=""
    fi
  fi
  verify_out=$(orca_cli orchestration dispatch-show --task "$TASK_ID" --json 2>&1) || verify_out=""
  verify_id=$(printf '%s' "$verify_out" | jq -r '
    .result.dispatch.id
    // .result.dispatch.dispatchId
    // .result.dispatchId
    // empty' 2>/dev/null || true)
  if [ -n "$verify_id" ]; then
    DISPATCH_ID="$verify_id"
  elif [ -n "$rebind_id" ]; then
    DISPATCH_ID="$rebind_id"
    echo "ORCAREG_DISPATCH_BIND_BY_RECEIPT: dispatch-show 二次核对仍未回显，按补绑响应采信: $rebind_id" >&2
  else
    DISPATCH_ID=""
  fi
  if [ -n "$DISPATCH_ID" ]; then
    # 第三步：单行注入 worker_done/ask 精确命令形式。
    # 必须单行：多行文本会在 TUI 里被提前回车逐行提交。
    printf -v inject_text \
      '[dispatch-bind 自动补绑] task_id=%s dispatch_id=%s。完成时精确执行一次: orca orchestration send --from %s --type worker_done --subject "worker 完成" --body "三句内摘要" --task-id %s --dispatch-id %s --outcome succeeded --files-modified "改动文件路径列表"。阻塞时: orca orchestration ask --from %s --question "阻塞问题" --timeout-ms 600000。其余仍按已注入任务执行。' \
      "$TASK_ID" "$DISPATCH_ID" "$TERMINAL_HANDLE" "$TASK_ID" "$DISPATCH_ID" "$TERMINAL_HANDLE"
    if orca_cli terminal send --terminal "$TERMINAL_HANDLE" --text "$inject_text" --enter --json >/dev/null 2>&1; then
      echo "ORCAREG_DISPATCH_INJECTED: 已向 $TERMINAL_HANDLE 单行注入 worker_done/ask 命令形式" >&2
    else
      DISPATCH_BIND="manual-required"
      echo "WARN: dispatch 已补绑($DISPATCH_ID)但命令形式注入失败；PM 需手动单行 terminal send 注入 worker_done 命令形式" >&2
    fi
  else
    DISPATCH_BIND="manual-required"
    echo "WARN: 自动补绑失败（dispatch mutation 无 id 且 dispatch-show 复核为空）。spawn 不阻断，但 worker_done 无通道。PM 手动三步补绑: ① orca orchestration dispatch --task $TASK_ID --to $TERMINAL_HANDLE --run $RUN_ID --return-preamble（不带 --inject，agent 不被识别时 --inject 会直接报错） ② 从返回 preamble 提取真实 ctx id ③ orca terminal send --terminal $TERMINAL_HANDLE --text \"<单行 worker_done/ask 命令形式>\" --enter（必须单行）。" >&2
  fi
fi

echo "ORCAREG_WORKER_REGISTERED: dispatch=${DISPATCH_ID:-none} bind=$DISPATCH_BIND" >&2
printf 'ORCAREG_RUN_ID=%s\n' "$RUN_ID"
printf 'ORCAREG_COORDINATOR_HANDLE=%s\n' "$COORDINATOR_HANDLE"
printf 'ORCAREG_TASK_ID=%s\n' "$TASK_ID"
printf 'ORCAREG_DISPATCH_ID=%s\n' "$DISPATCH_ID"
printf 'ORCAREG_DISPATCH_BIND=%s\n' "$DISPATCH_BIND"
