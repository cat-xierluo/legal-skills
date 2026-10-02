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
EXPECTED_RUNTIME_ID=""
AUTHORITY_RECEIPT_FILE=""
METADATA_FILE=""
NATIVE_AGENT=""
LAUNCH_REQUEST_ROOT=""
TERMINAL_OWNERSHIP="external"
REPLACEMENT_BIND=""
RETRY_OF=""
CLOSED_RECOVERY=""
RETRY_REQUEST=""

usage() {
  cat >&2 <<'USAGE'
Usage:
  orca-supervised-register.sh --worktree-id ID --terminal-handle HANDLE --task-spec TEXT [options]

Required:
  --worktree-id ID         Exact Orca worktree id
  --agent zcode            Opt-in native creation (mutually exclusive with --terminal-handle);
                           requires --metadata-file and --launch-request-root.
  --launch-request-root DIR Owner-only preconfigured native launcher request directory
  --terminal-handle HANDLE Existing terminal running an Orca-recognized agent
  --task-spec TEXT         Complete worker task (required unless --task-id is supplied)
  --authority-receipt PATH PM launch-bound authority receipt

Optional:
  --task-title TEXT        Concise task title
  --run-id ID              Reuse one Run for all workers in a Wave
  --task-id ID             Reuse a Task created by orca-wave-prepare.sh
  --coordinator-handle ID  Reuse the coordinator handle from the Wave receipt;
                           required with --task-id to avoid concurrent run-use rebinding
  --objective TEXT         Objective for a newly created Run
  --runtime-id ID          Wave receipt _meta.runtimeId; check before mutations
                           and every worker-start. Legacy omission is UNVERIFIED.
  --metadata-file PATH     Exact existing Session Context to reroute after a
                           successful replacement registration. The path,
                           worktree, Run, Task and authority receipt are verified.
  --timeout-ms N           worker-start readiness timeout (default: 60000)
  --retry-of ID            Exact failed Dispatch; requires --closed-recovery intent.
  --closed-recovery PATH   Verified closed-provider intent, single-use retry/adoption.
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
    --agent) NATIVE_AGENT="$2"; shift 2 ;;
    --launch-request-root) LAUNCH_REQUEST_ROOT="$2"; shift 2 ;;
    --terminal-handle) TERMINAL_HANDLE="$2"; shift 2 ;;
    --task-spec) TASK_SPEC="$2"; shift 2 ;;
    --task-title) TASK_TITLE="$2"; shift 2 ;;
    --task-id) TASK_ID="$2"; shift 2 ;;
    --run-id) RUN_ID="$2"; shift 2 ;;
    --coordinator-handle) COORDINATOR_HANDLE="$2"; shift 2 ;;
    --runtime-id)
      EXPECTED_RUNTIME_ID="$2"
      [ -n "$EXPECTED_RUNTIME_ID" ] || { echo "ERROR: --runtime-id cannot be empty" >&2; exit 64; }
      shift 2 ;;
    --authority-receipt) AUTHORITY_RECEIPT_FILE="$2"; shift 2 ;;
    --metadata-file) METADATA_FILE="$2"; shift 2 ;;
    --objective) OBJECTIVE="$2"; shift 2 ;;
    --timeout-ms) TIMEOUT_MS="$2"; shift 2 ;;
    --retry-of) RETRY_OF="$2"; shift 2 ;;
    --closed-recovery) CLOSED_RECOVERY="$2"; shift 2 ;;
    --reset-failed) RESET_FAILED=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage; exit 64 ;;
  esac
done

if [ -n "$RETRY_OF" ] || [ -n "$CLOSED_RECOVERY" ]; then
  [ -n "$RETRY_OF" ] && [ -n "$CLOSED_RECOVERY" ] && [ -n "$TASK_ID" ] && [ -n "$RUN_ID" ] &&
    [ -n "$EXPECTED_RUNTIME_ID" ] && [ -n "$TERMINAL_HANDLE" ] && [ -n "$METADATA_FILE" ] &&
    [ -z "$NATIVE_AGENT" ] && [ "$RESET_FAILED" -eq 0 ] || {
      echo "ERROR: closed retry requires exact intent/task/run/runtime/terminal/metadata; excludes reset/native-first" >&2; exit 64;
    }
fi
[ -n "$WORKTREE_ID" ] || { echo "ERROR: --worktree-id is required" >&2; exit 64; }
if [ -n "$NATIVE_AGENT" ]; then
  [ "$NATIVE_AGENT" = "zcode" ] && [ -z "$TERMINAL_HANDLE" ] && [ -n "$METADATA_FILE" ] && [ -n "$LAUNCH_REQUEST_ROOT" ] && [ "$RESET_FAILED" -eq 0 ] || {
    echo "ERROR: native --agent zcode requires explicit metadata/request root, excludes terminal/reset-failed" >&2; exit 64;
  }
  TERMINAL_OWNERSHIP="created"
else
  [ -n "$TERMINAL_HANDLE" ] || { echo "ERROR: --terminal-handle or --agent zcode is required" >&2; exit 64; }
  [ -z "$LAUNCH_REQUEST_ROOT" ] || { echo "ERROR: request root requires native --agent zcode" >&2; exit 64; }
  REPLACEMENT_BIND="${METADATA_FILE:+1}"
fi
[ -n "$TASK_SPEC" ] || [ -n "$TASK_ID" ] || { echo "ERROR: --task-spec or --task-id is required" >&2; exit 64; }
[ -z "$TASK_ID" ] || [ -n "$RUN_ID" ] || { echo "ERROR: --task-id requires --run-id" >&2; exit 64; }
[ -z "$TASK_ID" ] || [ -n "$COORDINATOR_HANDLE" ] || { echo "ERROR: --task-id requires --coordinator-handle from the Wave receipt" >&2; exit 64; }
[[ "$TIMEOUT_MS" =~ ^[0-9]+$ ]] || { echo "ERROR: --timeout-ms must be an integer" >&2; exit 64; }
command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required" >&2; exit 64; }
[ -n "$AUTHORITY_RECEIPT_FILE" ] || { echo "ERROR: --authority-receipt is required before worker-start" >&2; exit 64; }
python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); from completion_authority import load_authority; load_authority(sys.argv[2])' \
  "$SCRIPT_DIR" "$AUTHORITY_RECEIPT_FILE" || { echo "ERROR: invalid PM authority receipt; worker-start was not attempted" >&2; exit 64; }
orca_runtime_init
if [ -n "$COORDINATOR_HANDLE" ] || [ -n "$EXPECTED_RUNTIME_ID" ]; then
  orca_runtime_require_identity "$EXPECTED_RUNTIME_ID" || exit $?
fi

if [ -n "$CLOSED_RECOVERY" ]; then
  python3 - "$SCRIPT_DIR" "$CLOSED_RECOVERY" "$METADATA_FILE" "$AUTHORITY_RECEIPT_FILE" "$EXPECTED_RUNTIME_ID" "$WORKTREE_ID" "$COORDINATOR_HANDLE" "$ORCA_CLI_BIN" <<'PY_RECOVERY'
import sys
sys.path.insert(0,sys.argv[1])
from zcode_closed_recovery import load_intent,require
r=load_intent(sys.argv[2])
require((r['metadata'],r['authority'],r['runtime_id'],r['worktree_id'],r['orca_bin'])==tuple(sys.argv[3:7]+[sys.argv[8]]),'register intent identity mismatch')
import json
m=json.loads(open(r['metadata']).read())
from zcode_closed_recovery import run_owner
require(run_owner(r['orca_bin'],r['failed']['run_id'],r['runtime_id'])==r['owner'] and r['owner']['handle']==sys.argv[7],'current official Run coordinator mismatch')
PY_RECOVERY
  python3 "$SCRIPT_DIR/zcode_closed_recovery.py" admit-retry --intent "$CLOSED_RECOVERY"     --task "$TASK_ID" --dispatch "$RETRY_OF" --terminal "$TERMINAL_HANDLE" --run "$RUN_ID" >/dev/null || exit 64
fi

if [ -n "$NATIVE_AGENT" ]; then
  native_status=$(orca_cli status --json) || exit 64
  native_version=$(printf '%s' "$native_status" | jq -er '.result.runtime.appVersion') || exit 64
  [ -n "$EXPECTED_RUNTIME_ID" ] || EXPECTED_RUNTIME_ID=$(printf '%s' "$native_status" | jq -er '.result.runtime.runtimeId | select(type == "string" and length > 0 and . != "none")') || exit 64
  orca_runtime_require_identity "$EXPECTED_RUNTIME_ID" || exit $?
  python3 "$SCRIPT_DIR/zcode-orca-launcher.py" preflight --requests-root "$LAUNCH_REQUEST_ROOT" --app-version "$native_version" >/dev/null || exit 64
fi

patch_supervised_metadata() {
  local show_out resolved_identity resolved_id resolved_path metadata_root candidate
  local tmp_meta metadata_required=0
  local -a matches=()

  ORCAREG_METADATA_BIND="manual-required"
  [ "$DISPATCH_BIND" != "ok" ] || metadata_required=1

  if ! show_out=$(orca_cli worktree show --worktree "id:$WORKTREE_ID" --json 2>&1); then
    echo "ORCAREG_METADATA_LOOKUP_FAILED: worktree show 失败；worker 已注册，请按 runbook 手工补写 METADATA: $show_out" >&2
    return "$metadata_required"
  fi
  if ! resolved_identity=$(printf '%s' "$show_out" | jq -er '
    .result.worktree
    | select(type == "object")
    | [.id, .path]
    | select(all(.[]; type == "string" and length > 0))
    | @tsv
  ' 2>/dev/null); then
    echo "ORCAREG_METADATA_LOOKUP_FAILED: Orca worktree JSON 非法或缺少 id/path；worker 已注册，请按 runbook 手工补写 METADATA" >&2
    return "$metadata_required"
  fi
  IFS=$'\t' read -r resolved_id resolved_path <<< "$resolved_identity"
  if [ "$resolved_id" != "$WORKTREE_ID" ] || [ ! -d "$resolved_path" ]; then
    echo "ORCAREG_METADATA_LOOKUP_FAILED: Orca worktree identity/path 缺失或错配；worker 已注册，请按 runbook 手工补写 METADATA" >&2
    return "$metadata_required"
  fi

  metadata_root="$resolved_path/.claude/agent-sessions"
  if [ ! -d "$metadata_root" ] || [ -L "$metadata_root" ]; then
    echo "ORCAREG_METADATA_NOT_FOUND: $metadata_root 不存在或是符号链接；worker 已注册，请按 runbook 手工补写 METADATA" >&2
    return "$metadata_required"
  fi

  if [ -n "$METADATA_FILE" ]; then
    if ! candidate=$(python3 - "$metadata_root" "$METADATA_FILE" <<'PY'
from pathlib import Path
import stat
import sys

root = Path(sys.argv[1]).resolve(strict=True)
candidate = Path(sys.argv[2])
try:
    if not candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("metadata path must be absolute without traversal")
    relative = candidate.relative_to(root)
    if len(relative.parts) != 2 or relative.parts[-1] != "METADATA.json":
        raise ValueError("metadata must be one session below the resolved worktree root")
    current = root
    for part in relative.parts:
        current = current / part
        if stat.S_ISLNK(current.lstat().st_mode):
            raise ValueError("metadata path must not contain symlinks")
    resolved = candidate.resolve(strict=True)
    if resolved.name != "METADATA.json" or resolved.parent.parent != root:
        raise ValueError("metadata must be one session below the resolved worktree root")
    if not resolved.is_file():
        raise ValueError("metadata is not a regular file")
    print(resolved)
except (OSError, ValueError) as exc:
    print("ORCAREG_METADATA_EXPLICIT_INVALID: " + str(exc), file=sys.stderr)
    raise SystemExit(1)
PY
    ); then
      echo "ORCAREG_METADATA_EXPLICIT_INVALID: replacement metadata path is not trusted" >&2
      return "$metadata_required"
    fi
    if [ -n "$NATIVE_AGENT" ]; then
      if jq -e --arg worktree "$WORKTREE_ID" --arg authority "$AUTHORITY_RECEIPT_FILE" \
        '.session.orca.worktree_id == $worktree and (.session.orca.terminal_handle // "") == ""
         and .execution_authority.authority_receipt_file == $authority
         and .runtime.worker_backend == "zcode-cli"' "$candidate" >/dev/null 2>&1; then
        matches+=("$candidate")
      fi
    elif jq -e --arg worktree "$WORKTREE_ID" --arg run "$RUN_ID" --arg task "$TASK_ID" \
      --arg authority "$AUTHORITY_RECEIPT_FILE" \
      '.session.orca.worktree_id == $worktree
       and .session.orca.supervised.run_id == $run
       and .session.orca.supervised.task_id == $task
       and .execution_authority.authority_receipt_file == $authority' \
      "$candidate" >/dev/null 2>&1; then
      matches+=("$candidate")
    fi
  else
    while IFS= read -r -d '' candidate; do
      [ -f "$candidate" ] && [ ! -L "$candidate" ] || continue
      if jq -e --arg terminal "$TERMINAL_HANDLE" --arg worktree "$WORKTREE_ID" \
        '.session.orca.terminal_handle == $terminal
         and (.session.orca.worktree_id // $worktree) == $worktree' \
        "$candidate" >/dev/null 2>&1; then
        matches+=("$candidate")
      fi
    done < <(find "$metadata_root" -mindepth 2 -maxdepth 2 -type f -name METADATA.json -print0 2>/dev/null)
  fi

  if [ "${#matches[@]}" -ne 1 ]; then
    echo "ORCAREG_METADATA_AMBIGUOUS: terminal=$TERMINAL_HANDLE 匹配 ${#matches[@]} 个可信 METADATA.json；worker 已注册，请按 runbook 手工补写" >&2
    return "$metadata_required"
  fi

  candidate="${matches[0]}"
  if [ "$DISPATCH_BIND" = "ok" ]; then
    if ! orchestration_completion_authority_write \
      "$TASK_ID" "$DISPATCH_ID" "$TERMINAL_HANDLE" "$RUN_ID" "$candidate" \
      "$AUTHORITY_RECEIPT_FILE" "$REPLACEMENT_BIND"; then
      echo "ORCAREG_COMPLETION_AUTHORITY_FAILED: worker 已启动，但 completion transport 未进入实际 hook authority" >&2
      return 1
    fi
  fi
  tmp_meta=$(mktemp "${candidate}.tmp.XXXXXX") || {
    if ! orchestration_completion_authority_rollback; then
      echo "ORCAREG_METADATA_ROLLBACK_FAILED: prior completion authority may require manual restoration" >&2
    fi
    echo "ORCAREG_METADATA_WRITE_FAILED: 无法创建同目录临时文件；worker 已注册，请按 runbook 手工补写" >&2
    return "$metadata_required"
  }
  if jq --arg run "$RUN_ID" --arg task "$TASK_ID" --arg disp "$DISPATCH_ID" \
    --arg terminal "$TERMINAL_HANDLE" --arg ownership "$TERMINAL_OWNERSHIP" \
    --arg native_agent "$NATIVE_AGENT" \
    --arg coordinator "$COORDINATOR_HANDLE" --arg bind "$DISPATCH_BIND" \
    --arg completion_file "${ORCAREG_COMPLETION_AUTHORITY_FILE:-}" \
    --arg completion_sha "${ORCAREG_COMPLETION_AUTHORITY_SHA256:-}" \
    '.session.orca.terminal_handle = $terminal
     | if $native_agent != "" then .session.orca.tui_ready_method = "orca_native_worker_start_fresh_composer" else . end
     | .session.orca.supervised = {run_id: $run, coordinator_handle: $coordinator, task_id: $task, dispatch_id: $disp, dispatch_bind: $bind, contract: "orca.orchestration.contract.v1", completion_authority: "worker_done", terminal_ownership: $ownership}
     | if $completion_file != "" then
         .execution_authority.completion_authority_file = $completion_file
         | .execution_authority.completion_authority_sha256 = $completion_sha
       else . end' \
    "$candidate" > "$tmp_meta" && mv "$tmp_meta" "$candidate"; then
    orchestration_completion_authority_commit
    ORCAREG_METADATA_BIND="ok"
    echo "ORCAREG_METADATA_UPDATED: $candidate" >&2
  else
    if ! orchestration_completion_authority_rollback; then
      echo "ORCAREG_METADATA_ROLLBACK_FAILED: prior completion authority may require manual restoration" >&2
    fi
    rm -f "$tmp_meta"
    echo "ORCAREG_METADATA_WRITE_FAILED: worker 已注册但 METADATA 原子写回失败，请按 runbook 手工补写" >&2
    return "$metadata_required"
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

if [ -n "$NATIVE_AGENT" ]; then
  prepare_out=$(python3 "$SCRIPT_DIR/zcode-orca-launcher.py" prepare \
    --requests-root "$LAUNCH_REQUEST_ROOT" --metadata "$METADATA_FILE" \
    --authority "$AUTHORITY_RECEIPT_FILE" --orca-bin "$ORCA_CLI_BIN" \
    --runtime-id "$EXPECTED_RUNTIME_ID" --worktree-id "$WORKTREE_ID" \
    --run-id "$RUN_ID" --task-id "$TASK_ID" --coordinator-handle "$COORDINATOR_HANDLE") || exit 64
  REQUEST_FILE=$(printf '%s' "$prepare_out" | jq -er '.request_file') || exit 64
  echo "ORCAREG_NATIVE_REQUEST: $REQUEST_FILE" >&2
fi

worker_start_once() {
  if [ -n "$EXPECTED_RUNTIME_ID" ]; then
    orca_runtime_require_identity "$EXPECTED_RUNTIME_ID" || return $?
  fi
  local -a launch_selector=(--terminal "$TERMINAL_HANDLE")
  [ -z "$NATIVE_AGENT" ] || launch_selector=(--agent "$NATIVE_AGENT")
  local -a retry_selector=()
  [ -z "$RETRY_OF" ] || retry_selector=(--retry-of "$RETRY_OF" --retry-request "$RETRY_REQUEST")
  orca_cli orchestration worker-start \
    "${retry_selector[@]}" \
    --task "$TASK_ID" \
    "${launch_selector[@]}" \
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

if [ -n "$CLOSED_RECOVERY" ]; then
  DISPATCH_ID=$(printf '%s' "$start_out" | jq -er '.result | select(.state == "ready") | .dispatchId | select(type == "string" and length > 0)') || {
    echo "ERROR: retry response unknown; intent consumed; inspect native operation, never repeat business" >&2; exit 1;
  }
  if ! orchestration_closed_recovery_adopt "$CLOSED_RECOVERY" "$DISPATCH_ID"; then
    echo "ERROR: native retry started but adoption refused; exact dispatch=$DISPATCH_ID terminal=$TERMINAL_HANDLE intent=$CLOSED_RECOVERY; do not repeat business" >&2; exit 1
  fi
  printf 'ORCAREG_RUN_ID=%s\nORCAREG_TASK_ID=%s\nORCAREG_DISPATCH_ID=%s\nORCAREG_DISPATCH_BIND=ok\nORCAREG_METADATA_BIND=ok\n' "$RUN_ID" "$TASK_ID" "$DISPATCH_ID"
  exit 0
fi

if [ -n "$NATIVE_AGENT" ]; then
  native_receipt=$(mktemp "$LAUNCH_REQUEST_ROOT/native-receipt.XXXXXX") || exit 1
  chmod 600 "$native_receipt"
  printf '%s' "$start_out" > "$native_receipt"
  if ! bound_out=$(python3 "$SCRIPT_DIR/zcode-orca-launcher.py" bind-receipt --requests-root "$LAUNCH_REQUEST_ROOT" --request-file "$REQUEST_FILE" --receipt "$native_receipt"); then
    echo "ERROR: native receipt/claim mismatch; receipt=$native_receipt request=$REQUEST_FILE; inspect residualResources; no retry" >&2
    echo "$start_out" >&2
    exit 1
  fi
  TERMINAL_HANDLE=$(printf '%s' "$bound_out" | jq -er '.terminal_handle') || exit 1
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
printf 'ORCAREG_COMPLETION_AUTHORITY_FILE=%s\n' "${ORCAREG_COMPLETION_AUTHORITY_FILE:-}"
printf 'ORCAREG_COMPLETION_AUTHORITY_SHA256=%s\n' "${ORCAREG_COMPLETION_AUTHORITY_SHA256:-}"
printf 'ORCAREG_METADATA_BIND=%s\n' "$ORCAREG_METADATA_BIND"

printf 'ORCAREG_TERMINAL_HANDLE=%s\n' "$TERMINAL_HANDLE"
printf 'ORCAREG_TERMINAL_OWNERSHIP=%s\n' "$TERMINAL_OWNERSHIP"
