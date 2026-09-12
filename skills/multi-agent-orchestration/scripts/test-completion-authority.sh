#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CASE_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/completion-authority.XXXXXX")
trap 'rm -rf "$CASE_ROOT"' EXIT

# shellcheck source=orca-supervised-protocol.sh
source "$SCRIPT_DIR/orca-supervised-protocol.sh"

passed=0
failed=0
ok() { printf 'PASS: %s\n' "$1"; passed=$((passed + 1)); }
bad() { printf 'FAIL: %s\n' "$1" >&2; failed=$((failed + 1)); }

authority_file="$CASE_ROOT/agent-authority/session.json"
completion_file="$CASE_ROOT/agent-authority/session.completion.json"
metadata_file="$CASE_ROOT/METADATA.json"
mkdir -p "$(dirname "$authority_file")"
printf '%s\n' '{"schema":"multi-agent-orchestration.authority-receipt.v1"}' > "$authority_file"
jq -n --arg authority "$authority_file" '{execution_authority:{authority_receipt_file:$authority}}' > "$metadata_file"

TASK_ID=task_123
DISPATCH_ID=ctx_456
TERMINAL_HANDLE=term_789
RUN_ID=run_abc
CAPABILITY='dcap_runtime_secret_never_persisted'
CAPABILITY_HASH=$(printf '%s' "$CAPABILITY" | shasum -a 256 | awk '{print $1}')
PROCESS_INCARNATION='terminal-process-incarnation-fixture'

orca_cli() {
  [ "$1 $2" = "orchestration dispatch-show" ] || return 64
  jq -n \
    --arg task "${FAKE_TASK_ID:-$TASK_ID}" \
    --arg dispatch "${FAKE_DISPATCH_ID:-$DISPATCH_ID}" \
    --arg terminal "${FAKE_TERMINAL_HANDLE:-$TERMINAL_HANDLE}" \
    --arg run "${FAKE_RUN_ID:-$RUN_ID}" \
    --arg capability_hash "${FAKE_CAPABILITY_HASH:-$CAPABILITY_HASH}" \
    --arg process "${FAKE_PROCESS_INCARNATION:-$PROCESS_INCARNATION}" \
    '{ok:true,_meta:{runtimeId:"runtime-fixture"},result:{dispatch:{id:$dispatch,task_id:$task,assignee_handle:$terminal,
      run_id:$run,capability_hash:$capability_hash,process_incarnation:$process}}}'
}

if orchestration_completion_authority_write \
  "$TASK_ID" "$DISPATCH_ID" "$TERMINAL_HANDLE" "$RUN_ID" "$metadata_file" "$authority_file" \
  >"$CASE_ROOT/success.out" 2>"$CASE_ROOT/success.err"; then
  if jq -e --arg task "$TASK_ID" --arg dispatch "$DISPATCH_ID" --arg terminal "$TERMINAL_HANDLE" \
    --arg run "$RUN_ID" --arg hash "$CAPABILITY_HASH" --arg process "$PROCESS_INCARNATION" \
    '.schema == "multi-agent-orchestration.completion-authority.v1" and .state == "active"
     and .task_id == $task and .dispatch_id == $dispatch and .terminal_handle == $terminal
     and .run_id == $run and .capability_hash == $hash and .process_incarnation == $process' \
    "$completion_file" >/dev/null; then
    ok "post-start receipt binds task/dispatch/terminal/run/capability hash/incarnation"
  else
    bad "post-start receipt binds task/dispatch/terminal/run/capability hash/incarnation"
  fi
else
  cat "$CASE_ROOT/success.err" >&2
  bad "post-start receipt is created"
fi

if grep -R -Fq "$CAPABILITY" "$CASE_ROOT"; then
  bad "runtime capability plaintext never enters receipt or metadata"
else
  ok "runtime capability plaintext never enters receipt or metadata"
fi
mode=$(stat -f '%Lp' "$completion_file" 2>/dev/null || stat -c '%a' "$completion_file")
if [ "$mode" = "600" ]; then ok "completion receipt is owner-only"; else bad "completion receipt is owner-only"; fi

first_sha=$(shasum -a 256 "$completion_file" | awk '{print $1}')
if orchestration_completion_authority_write \
  "$TASK_ID" "$DISPATCH_ID" "$TERMINAL_HANDLE" "$RUN_ID" "$metadata_file" "$authority_file" \
  >/dev/null 2>"$CASE_ROOT/idempotent.err" && \
  [ "$(shasum -a 256 "$completion_file" | awk '{print $1}')" = "$first_sha" ]; then
  ok "identical registration is idempotent and does not rewrite the receipt"
else
  bad "identical registration is idempotent and does not rewrite the receipt"
fi

rm -f "$completion_file"
FAKE_TASK_ID=task_wrong
if orchestration_completion_authority_write \
  "$TASK_ID" "$DISPATCH_ID" "$TERMINAL_HANDLE" "$RUN_ID" "$metadata_file" "$authority_file" \
  >/dev/null 2>"$CASE_ROOT/drift.err" || [ -e "$completion_file" ]; then
  bad "Dispatch identity drift fails before receipt creation"
else
  ok "Dispatch identity drift fails before receipt creation"
fi
unset FAKE_TASK_ID

printf '%s\n' '{"schema":"multi-agent-orchestration.completion-authority.v1","state":"active","task_id":"task_stale"}' > "$completion_file"
if orchestration_completion_authority_write \
  "$TASK_ID" "$DISPATCH_ID" "$TERMINAL_HANDLE" "$RUN_ID" "$metadata_file" "$authority_file" \
  >/dev/null 2>"$CASE_ROOT/stale.err"; then
  bad "different existing receipt is rejected"
else
  ok "different existing receipt is rejected"
fi

if orchestration_completion_authority_write \
  "$TASK_ID" "$DISPATCH_ID" "$TERMINAL_HANDLE" "$RUN_ID" "$metadata_file" "$CASE_ROOT/forged.json" \
  >/dev/null 2>"$CASE_ROOT/forged.err"; then
  bad "worker-writable metadata cannot select a different authority path"
else
  ok "worker-writable metadata cannot select a different authority path"
fi
mv "$CASE_ROOT/agent-authority" "$CASE_ROOT/saved-authority"
ln -s "$CASE_ROOT/saved-authority" "$CASE_ROOT/agent-authority"
if orchestration_completion_authority_write \
  "$TASK_ID" "$DISPATCH_ID" "$TERMINAL_HANDLE" "$RUN_ID" "$metadata_file" "$authority_file" \
  >/dev/null 2>"$CASE_ROOT/parent-link.err"; then
  bad "receipt producer rejects a symlinked authority directory"
else
  ok "receipt producer rejects a symlinked authority directory"
fi

printf 'completion authority tests: %s passed, %s failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
