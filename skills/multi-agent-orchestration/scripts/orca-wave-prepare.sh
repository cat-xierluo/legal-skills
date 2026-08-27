#!/usr/bin/env bash
# Create/bind one Orca Run and pre-create every independent Task before workers start.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=orca-runtime.sh
source "$SCRIPT_DIR/orca-runtime.sh"
# shellcheck source=orca-supervised-protocol.sh
source "$SCRIPT_DIR/orca-supervised-protocol.sh"

MANIFEST=""
RECEIPT=""
RUN_ID=""

usage() {
  cat >&2 <<'USAGE'
Usage:
  orca-wave-prepare.sh --manifest FILE [--run-id ID] [--receipt FILE]

Manifest schema:
  {
    "objective": "Wave objective",
    "tasks": [
      {"key": "api", "title": "API worker", "spec": "scope + verification"},
      {"key": "ui",  "title": "UI worker",  "spec": "scope + verification"}
    ]
  }

All tasks must be independent and have unique non-empty keys/specs. The command creates
or binds one Run, creates every Task serially, then emits one JSON receipt. Only after this
command succeeds may callers start workers in parallel with the receipt's run_id,
coordinator_handle and task_id values.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --manifest) MANIFEST="$2"; shift 2 ;;
    --run-id) RUN_ID="$2"; shift 2 ;;
    --receipt) RECEIPT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage; exit 64 ;;
  esac
done

[ -f "$MANIFEST" ] || { echo "ERROR: --manifest must name a readable file" >&2; exit 64; }
command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required" >&2; exit 64; }
jq -e '
  type == "object"
  and (.objective | type == "string" and length > 0)
  and (.tasks | type == "array" and length > 0)
  and ([.tasks[] | (type == "object" and (.key | type == "string" and length > 0) and (.spec | type == "string" and length > 0))] | all)
  and ((.tasks | map(.key) | unique | length) == (.tasks | length))
' "$MANIFEST" >/dev/null || {
  echo "ERROR: invalid Wave manifest (objective/tasks/key/spec/unique-key contract failed)" >&2
  exit 64
}

if [ -n "$RECEIPT" ] && [ -e "$RECEIPT" ]; then
  echo "ERROR: receipt already exists; refusing to recreate a Wave: $RECEIPT" >&2
  exit 64
fi

# Task-059: spec 内的 branch 名不得含 '/'。Orca worktree --name 会把 '/' 规范成 '-'，
# spawn-worker.sh 也用 safe_branch 把斜杠换成连字符；若 manifest spec 写了斜杠名，
# worker 的隔离门禁按 spec 文本比对实际分支时会误判 blocked（badminton-lab Wave 1
# 三个 worker 同时跑偏的根因）。这里 fail-closed 拒绝，逼 PM 在 spec 里写连字符名。
if ! slash_specs=$(jq -r '.tasks[] | select(.spec | test("branch[:=][[:space:]]*[^[:space:]]+/")) | .key' "$MANIFEST" 2>/dev/null); then
  echo "ERROR: Wave manifest changed or became unreadable during branch validation" >&2
  exit 64
fi
if [ -n "$slash_specs" ]; then
  echo "ERROR: spec mentions branch names containing slash; Orca normalizes slash to hyphen (worktree --name + safe_branch), so the worker isolation gate compares against the hyphen form and would misjudge blocked. Rewrite branch names in these specs with hyphens (feat/bl-x -> feat-bl-x):" >&2
  while IFS= read -r task_key; do
    printf '  - %s\n' "$task_key" >&2
  done <<< "$slash_specs"
  exit 64
fi

orca_runtime_init
OBJECTIVE=$(jq -r '.objective' "$MANIFEST")
COORDINATOR_HANDLE=""

if [ -z "$RUN_ID" ]; then
  run_out=$(orca_cli orchestration run-create --objective "$OBJECTIVE" --json 2>&1) || {
    echo "ERROR: run-create failed; do not retry blindly: $run_out" >&2
    exit 1
  }
  RUN_ID=$(printf '%s' "$run_out" | jq -r '.result.run.id // empty')
  COORDINATOR_HANDLE=$(printf '%s' "$run_out" | jq -r '.result.run.coordinator_handle // .result.run.coordinatorHandle // empty')
else
  run_out=$(orca_cli orchestration run-use --id "$RUN_ID" --json 2>&1) || {
    echo "ERROR: run-use failed for $RUN_ID: $run_out" >&2
    exit 1
  }
  COORDINATOR_HANDLE=$(printf '%s' "$run_out" | jq -r '.result.run.coordinator_handle // .result.run.coordinatorHandle // empty')
fi
[ -n "$RUN_ID" ] && [ -n "$COORDINATOR_HANDLE" ] || {
  echo "ERROR: Run receipt missing run id or coordinator handle" >&2
  exit 1
}

TASKS_TMP=$(mktemp)
RECEIPT_TMP=""
cleanup() {
  rm -f "$TASKS_TMP"
  [ -z "$RECEIPT_TMP" ] || rm -f "$RECEIPT_TMP"
}
trap cleanup EXIT

while IFS= read -r task_json; do
  key=$(printf '%s' "$task_json" | jq -r '.key')
  title=$(printf '%s' "$task_json" | jq -r '.title // .key')
  spec=$(printf '%s' "$task_json" | jq -r '.spec')
  effective_spec=$(orca_supervised_task_spec "$spec")
  task_out=$(orca_cli orchestration task-create \
    --spec "$effective_spec" --task-title "$title" \
    --run "$RUN_ID" --from "$COORDINATOR_HANDLE" --json 2>&1) || {
      echo "ERROR: task-create failed after Run $RUN_ID was created/bound (key=$key). Inspect the existing Run; do not rerun the whole manifest blindly: $task_out" >&2
      exit 1
    }
  task_id=$(printf '%s' "$task_out" | jq -r '.result.task.id // empty')
  [ -n "$task_id" ] || {
    echo "ERROR: task-create response missing .result.task.id (key=$key)" >&2
    exit 1
  }
  jq -cn --arg key "$key" --arg title "$title" --arg task_id "$task_id" \
    '{key:$key,title:$title,task_id:$task_id}' >> "$TASKS_TMP"
  echo "ORCA_WAVE_TASK_CREATED: key=$key task=$task_id" >&2
done < <(jq -c '.tasks[]' "$MANIFEST")

created_at=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
RESULT=$(jq -s \
  --arg schema 'multi-agent-orchestration.wave-receipt.v1' \
  --arg created_at "$created_at" \
  --arg objective "$OBJECTIVE" \
  --arg run_id "$RUN_ID" \
  --arg coordinator_handle "$COORDINATOR_HANDLE" \
  '{schema:$schema,created_at:$created_at,objective:$objective,run_id:$run_id,coordinator_handle:$coordinator_handle,tasks:.,launch_contract:"start workers only after this receipt exists; pass --orca-run-id, --orca-coordinator-handle and each --orca-task-id"}' \
  "$TASKS_TMP")

if [ -n "$RECEIPT" ]; then
  receipt_dir=$(dirname "$RECEIPT")
  [ -d "$receipt_dir" ] || { echo "ERROR: receipt parent does not exist: $receipt_dir" >&2; exit 64; }
  RECEIPT_TMP="$RECEIPT.tmp.$$"
  umask 077
  printf '%s\n' "$RESULT" > "$RECEIPT_TMP"
  mv "$RECEIPT_TMP" "$RECEIPT"
  RECEIPT_TMP=""
  echo "ORCA_WAVE_RECEIPT_WRITTEN: $RECEIPT" >&2
fi

printf '%s\n' "$RESULT"
