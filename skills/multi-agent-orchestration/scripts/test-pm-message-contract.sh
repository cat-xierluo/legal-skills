#!/usr/bin/env bash
# Regression contract for PM -> worker Orca messaging and read-only inbox inspection.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PM="$SCRIPT_DIR/pm-orchestrate.sh"
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT

pass=0
fail=0
ok() { printf '  ✓ %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  ✗ %s\n' "$1" >&2; fail=$((fail + 1)); }
assert_true() {
  local description="$1"
  shift
  if "$@"; then ok "$description"; else bad "$description"; fi
}
assert_eq() {
  local description="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    ok "$description"
  else
    bad "$description (expected=$expected actual=$actual)"
  fi
}

FAKE="$TMP_ROOT/fake-orca"
export FAKE_ORCA_LOG="$TMP_ROOT/orca.ndjson"
export FAKE_ORCA_STATE="$TMP_ROOT/state"
mkdir -p "$FAKE_ORCA_STATE"

cat > "$FAKE" <<'FAKE'
#!/usr/bin/env bash
set -euo pipefail
jq -cn --args '$ARGS.positional' -- "$@" >> "$FAKE_ORCA_LOG"

arg_value() {
  local wanted="$1"
  shift
  while [ "$#" -gt 0 ]; do
    if [ "$1" = "$wanted" ]; then
      printf '%s' "${2:-}"
      return 0
    fi
    shift
  done
  return 1
}

case "${1:-} ${2:-}" in
  "status --json")
    if [ -f "$FAKE_ORCA_STATE/runtime-drift" ]; then
      runtime="runtime-other"
    else
      runtime="runtime-contract"
    fi
    jq -cn --arg runtime "$runtime" '{ok:true,result:{runtime:{reachable:true,runtimeId:$runtime}}}'
    ;;
  "terminal show")
    handle=$(arg_value --terminal "$@")
    if [ -f "$FAKE_ORCA_STATE/stale-terminal" ] || [ "$handle" != "term-pm-contract" ]; then
      writable=false
    else
      writable=true
    fi
    jq -cn --arg handle "$handle" --argjson writable "$writable" \
      '{ok:true,_meta:{runtimeId:"runtime-contract"},result:{terminal:{handle:$handle,connected:$writable,writable:$writable,orphaned:false,exitCause:null}}}'
    ;;
  "orchestration run-use"|"orchestration run-current")
    sender=$(arg_value --from "$@")
    jq -cn --arg sender "$sender" \
      '{ok:true,_meta:{runtimeId:"runtime-contract"},result:{run:{id:"run-contract",coordinator_handle:$sender}}}'
    ;;
  "orchestration worker-show")
    if [ -f "$FAKE_ORCA_STATE/binding-mismatch" ]; then
      task="task-other"
    else
      task="task-contract"
    fi
    if [ -f "$FAKE_ORCA_STATE/settled-worker" ]; then
      dispatch_status="completed"
      worker_state="succeeded"
    else
      dispatch_status="dispatched"
      worker_state="active"
    fi
    jq -cn --arg task "$task" --arg dispatch_status "$dispatch_status" --arg worker_state "$worker_state" '{
      ok:true,
      _meta:{runtimeId:"runtime-contract"},
      result:{
        dispatch:{id:"ctx-contract",task_id:$task,run_id:"run-contract",assignee_handle:"term-worker-contract",status:$dispatch_status},
        worker:{dispatch_id:"ctx-contract",agent_terminal_handle:"term-worker-contract",state:$worker_state}
      }
    }'
    ;;
  "orchestration send")
    if [ -f "$FAKE_ORCA_STATE/send-malformed" ]; then
      printf '%s\n' 'not-json'
    elif [ -f "$FAKE_ORCA_STATE/send-no-id" ]; then
      printf '%s\n' '{"ok":true,"result":{}}'
    elif [ -f "$FAKE_ORCA_STATE/send-rejected" ]; then
      printf '%s\n' '{"ok":false,"error":{"code":"SEND_REJECTED"}}'
    elif [ -f "$FAKE_ORCA_STATE/send-wrong-destination" ]; then
      printf '%s\n' '{"ok":true,"result":{"relay":{"messageId":"msg-contract-1","dispatchId":"ctx-contract","destination":"run"}}}'
    elif [ -f "$FAKE_ORCA_STATE/send-wrong-dispatch" ]; then
      printf '%s\n' '{"ok":true,"result":{"relay":{"messageId":"msg-contract-1","dispatchId":"ctx-other","destination":"worker"}}}'
    elif [ -f "$FAKE_ORCA_STATE/send-legacy-message" ]; then
      printf '%s\n' '{"ok":true,"result":{"message":{"id":"msg-contract-1"}}}'
    elif [ -f "$FAKE_ORCA_STATE/send-relay-no-id-side-id" ]; then
      printf '%s\n' '{"ok":true,"result":{"relay":{"dispatchId":"ctx-contract","destination":"worker"},"message":{"id":"msg-side-channel"}}}'
    else
      printf '%s\n' '{"ok":true,"result":{"relay":{"messageId":"msg-contract-1","dispatchId":"ctx-contract","destination":"worker"}}}'
    fi
    ;;
  "orchestration check")
    if [ -f "$FAKE_ORCA_STATE/no-messages" ]; then
      printf '%s\n' '{"ok":true,"result":{"count":0,"messages":[]}}'
    elif [ -f "$FAKE_ORCA_STATE/unrelated-only" ]; then
      printf '%s\n' '{"ok":true,"result":{"count":1,"messages":[{"id":"msg-other","type":"question","run_id":"run-contract","from_handle":"term-worker-contract","to_handle":"term-pm-contract","thread_id":"corr.task-contract.1","payload":"{\"taskId\":\"task-other\",\"dispatchId\":\"ctx-other\",\"message\":{\"threadId\":\"thread.task-contract\"},\"correlationId\":\"corr.task-contract.1\"}"}]}}'
    elif [ -f "$FAKE_ORCA_STATE/missing-provenance" ]; then
      printf '%s\n' '{"ok":true,"result":{"count":1,"messages":[{"id":"msg-unproven","type":"question","run_id":"run-contract","from_handle":"term-worker-contract","to_handle":"term-pm-contract","thread_id":"corr.task-contract.1","payload":"{\"message\":{\"thread_id\":\"thread.task-contract\"},\"correlation_id\":\"corr.task-contract.1\"}"}]}}'
    elif [ -f "$FAKE_ORCA_STATE/missing-run" ]; then
      printf '%s\n' '{"ok":true,"result":{"count":1,"messages":[{"id":"msg-no-run","type":"question","from_handle":"term-worker-contract","to_handle":"term-pm-contract","thread_id":"corr.task-contract.1","payload":"{\"taskId\":\"task-contract\",\"dispatchId\":\"ctx-contract\",\"message\":{\"threadId\":\"thread.task-contract\"},\"correlationId\":\"corr.task-contract.1\"}"}]}}'
    elif [ -f "$FAKE_ORCA_STATE/missing-sender" ]; then
      printf '%s\n' '{"ok":true,"result":{"count":1,"messages":[{"id":"msg-no-sender","type":"question","run_id":"run-contract","to_handle":"term-pm-contract","thread_id":"corr.task-contract.1","payload":"{\"taskId\":\"task-contract\",\"dispatchId\":\"ctx-contract\",\"message\":{\"threadId\":\"thread.task-contract\"},\"correlationId\":\"corr.task-contract.1\"}"}]}}'
    elif [ -f "$FAKE_ORCA_STATE/wrong-sender" ]; then
      printf '%s\n' '{"ok":true,"result":{"count":1,"messages":[{"id":"msg-wrong-sender","type":"question","run_id":"run-contract","from_handle":"term-other","to_handle":"term-pm-contract","thread_id":"corr.task-contract.1","payload":"{\"taskId\":\"task-contract\",\"dispatchId\":\"ctx-contract\",\"message\":{\"threadId\":\"thread.task-contract\"},\"correlationId\":\"corr.task-contract.1\"}"}]}}'
    elif [ -f "$FAKE_ORCA_STATE/native-reply" ]; then
      printf '%s\n' '{"ok":true,"result":{"count":1,"messages":[{"id":"msg-native-reply","runId":"run-contract","from":"term-worker-contract","to":"term-pm-contract","threadId":"corr.task-contract.1","subject":"Re: Review request","body":"Reviewed with evidence."}]}}'
    elif [ -f "$FAKE_ORCA_STATE/alias-conflict" ]; then
      printf '%s\n' '{"ok":true,"result":{"count":1,"messages":[{"id":"msg-alias-conflict","type":"question","run_id":"run-contract","from_handle":"term-worker-contract","to_handle":"term-pm-contract","thread_id":"corr.task-contract.1","payload":"{\"context\":{\"task_id\":\"task-contract\",\"dispatch_id\":\"ctx-contract\"},\"taskId\":\"task-other\",\"dispatchId\":\"ctx-other\",\"message\":{\"thread_id\":\"thread.task-contract\"},\"correlation_id\":\"corr.task-contract.1\"}"}]}}'
    elif [ -f "$FAKE_ORCA_STATE/type-alias-conflict" ]; then
      printf '%s\n' '{"ok":true,"result":{"count":1,"messages":[{"id":"msg-type-conflict","type":"question","messageType":"status","run_id":"run-contract","from_handle":"term-worker-contract","to_handle":"term-pm-contract","thread_id":"corr.task-contract.1","payload":"{\"taskId\":\"task-contract\",\"dispatchId\":\"ctx-contract\",\"message\":{\"type\":\"question\",\"threadId\":\"thread.task-contract\"},\"correlationId\":\"corr.task-contract.1\"}"}]}}'
    elif [ -f "$FAKE_ORCA_STATE/payload-type-conflict" ]; then
      printf '%s\n' '{"ok":true,"result":{"count":1,"messages":[{"id":"msg-payload-type-conflict","type":"question","run_id":"run-contract","from_handle":"term-worker-contract","to_handle":"term-pm-contract","thread_id":"corr.task-contract.1","payload":"{\"taskId\":\"task-contract\",\"dispatchId\":\"ctx-contract\",\"message\":{\"messageType\":\"status\",\"threadId\":\"thread.task-contract\"},\"correlationId\":\"corr.task-contract.1\"}"}]}}'
    elif [ -f "$FAKE_ORCA_STATE/payload-sender-conflict" ]; then
      printf '%s\n' '{"ok":true,"result":{"count":1,"messages":[{"id":"msg-sender-conflict","type":"question","run_id":"run-contract","from_handle":"term-worker-contract","to_handle":"term-pm-contract","thread_id":"corr.task-contract.1","payload":"{\"taskId\":\"task-contract\",\"dispatchId\":\"ctx-contract\",\"sender\":{\"role\":\"worker\",\"terminalHandle\":\"term-other\"},\"message\":{\"type\":\"question\",\"threadId\":\"thread.task-contract\"},\"correlationId\":\"corr.task-contract.1\"}"}]}}'
    elif [ -f "$FAKE_ORCA_STATE/payload-sender-role-conflict" ]; then
      printf '%s\n' '{"ok":true,"result":{"count":1,"messages":[{"id":"msg-sender-role-conflict","type":"question","run_id":"run-contract","from_handle":"term-worker-contract","to_handle":"term-pm-contract","thread_id":"corr.task-contract.1","payload":"{\"taskId\":\"task-contract\",\"dispatchId\":\"ctx-contract\",\"sender\":{\"role\":\"coordinator\",\"terminalHandle\":\"term-worker-contract\"},\"message\":{\"type\":\"question\",\"threadId\":\"thread.task-contract\"},\"correlationId\":\"corr.task-contract.1\"}"}]}}'
    elif [ -f "$FAKE_ORCA_STATE/payload-recipient-id-conflict" ]; then
      printf '%s\n' '{"ok":true,"result":{"count":1,"messages":[{"id":"msg-recipient-id-conflict","type":"question","run_id":"run-contract","from_handle":"term-worker-contract","to_handle":"term-pm-contract","thread_id":"corr.task-contract.1","payload":"{\"taskId\":\"task-contract\",\"dispatchId\":\"ctx-contract\",\"recipient\":{\"kind\":\"dispatch\",\"dispatchId\":\"ctx-other\"},\"message\":{\"type\":\"question\",\"threadId\":\"thread.task-contract\"},\"correlationId\":\"corr.task-contract.1\"}"}]}}'
    elif [ -f "$FAKE_ORCA_STATE/payload-recipient-kind-conflict" ]; then
      printf '%s\n' '{"ok":true,"result":{"count":1,"messages":[{"id":"msg-recipient-kind-conflict","type":"question","run_id":"run-contract","from_handle":"term-worker-contract","to_handle":"term-pm-contract","thread_id":"corr.task-contract.1","payload":"{\"taskId\":\"task-contract\",\"dispatchId\":\"ctx-contract\",\"recipient\":{\"kind\":\"run\",\"dispatchId\":\"ctx-contract\"},\"message\":{\"type\":\"question\",\"threadId\":\"thread.task-contract\"},\"correlationId\":\"corr.task-contract.1\"}"}]}}'
    elif [ -f "$FAKE_ORCA_STATE/missing-recipient" ]; then
      printf '%s\n' '{"ok":true,"result":{"count":1,"messages":[{"id":"msg-no-recipient","type":"question","run_id":"run-contract","from_handle":"term-worker-contract","thread_id":"corr.task-contract.1","payload":"{\"taskId\":\"task-contract\",\"dispatchId\":\"ctx-contract\",\"message\":{\"type\":\"question\",\"threadId\":\"thread.task-contract\"},\"correlationId\":\"corr.task-contract.1\"}"}]}}'
    elif [ -f "$FAKE_ORCA_STATE/wrong-recipient" ]; then
      printf '%s\n' '{"ok":true,"result":{"count":1,"messages":[{"id":"msg-wrong-recipient","type":"question","run_id":"run-contract","from_handle":"term-worker-contract","to_handle":"term-other","thread_id":"corr.task-contract.1","payload":"{\"taskId\":\"task-contract\",\"dispatchId\":\"ctx-contract\",\"message\":{\"type\":\"question\",\"threadId\":\"thread.task-contract\"},\"correlationId\":\"corr.task-contract.1\"}"}]}}'
    else
      printf '%s\n' '{"ok":true,"result":{"count":2,"messages":[{"id":"msg-other","type":"question","run_id":"run-contract","from_handle":"term-other","to_handle":"term-pm-contract","payload":"{\"taskId\":\"task-other\",\"dispatchId\":\"ctx-other\"}"},{"id":"msg-worker-1","type":"question","run_id":"run-contract","from_handle":"term-worker-contract","to_handle":"term-pm-contract","thread_id":"corr.task-contract.1","payload":"{\"taskId\":\"task-contract\",\"dispatchId\":\"ctx-contract\",\"sender\":{\"role\":\"worker\",\"terminalHandle\":\"term-worker-contract\"},\"recipient\":{\"kind\":\"dispatch\",\"dispatchId\":\"ctx-contract\"},\"message\":{\"type\":\"question\",\"threadId\":\"thread.task-contract\"},\"correlationId\":\"corr.task-contract.1\"}"}]}}'
    fi
    ;;
  *)
    printf 'FAKE_ORCA_UNSUPPORTED: %q ' "$@" >&2
    printf '\n' >&2
    exit 64
    ;;
esac
FAKE
chmod +x "$FAKE"
export ORCA_CLI_COMMAND="$FAKE"

WT="$TMP_ROOT/worker"
SESSION="contract-worker"
CONTEXT="$WT/.claude/agent-sessions/$SESSION"
METADATA="$CONTEXT/METADATA.json"
mkdir -p "$CONTEXT"
jq -n --arg worktree "$WT" --arg session "$SESSION" '
  {
    project: $worktree,
    worktree: $worktree,
    session: {
      id: $session,
      orca: {
        runtime_id: "runtime-contract",
        worktree_id: "repo-contract::worker",
        terminal_handle: "term-worker-contract",
        supervised: {
          run_id: "run-contract",
          task_id: "task-contract",
          dispatch_id: "ctx-contract",
          coordinator_handle: "term-pm-contract"
        }
      }
    },
    runtime: {provider_lease: {file: ""}}
  }
' > "$METADATA"

LAST_RC=0
run_pm() {
  : > "$FAKE_ORCA_LOG"
  rm -f "$FAKE_ORCA_STATE/runtime-drift" \
    "$FAKE_ORCA_STATE/stale-terminal" \
    "$FAKE_ORCA_STATE/send-malformed" \
    "$FAKE_ORCA_STATE/send-rejected" \
    "$FAKE_ORCA_STATE/send-wrong-destination" \
    "$FAKE_ORCA_STATE/send-wrong-dispatch" \
    "$FAKE_ORCA_STATE/send-legacy-message" \
    "$FAKE_ORCA_STATE/send-relay-no-id-side-id" \
    "$FAKE_ORCA_STATE/no-messages" \
    "$FAKE_ORCA_STATE/unrelated-only" \
    "$FAKE_ORCA_STATE/missing-provenance" \
    "$FAKE_ORCA_STATE/missing-run" \
    "$FAKE_ORCA_STATE/missing-sender" \
    "$FAKE_ORCA_STATE/wrong-sender" \
    "$FAKE_ORCA_STATE/native-reply" \
    "$FAKE_ORCA_STATE/alias-conflict" \
    "$FAKE_ORCA_STATE/type-alias-conflict" \
    "$FAKE_ORCA_STATE/payload-type-conflict" \
    "$FAKE_ORCA_STATE/payload-sender-conflict" \
    "$FAKE_ORCA_STATE/payload-sender-role-conflict" \
    "$FAKE_ORCA_STATE/payload-recipient-id-conflict" \
    "$FAKE_ORCA_STATE/payload-recipient-kind-conflict" \
    "$FAKE_ORCA_STATE/missing-recipient" \
    "$FAKE_ORCA_STATE/wrong-recipient" \
    "$FAKE_ORCA_STATE/binding-mismatch" \
    "$FAKE_ORCA_STATE/settled-worker" \
    "$FAKE_ORCA_STATE/send-no-id"
  set +e
  bash "$PM" "$@" > "$TMP_ROOT/stdout" 2> "$TMP_ROOT/stderr"
  LAST_RC=$?
  set -e
}

contract_args=(
  send --worktree "$WT" --session "$SESSION"
  --message-contract
  --subject "Review request"
  --message-type decision_gate
  --priority high
  --thread-id "thread.task-contract"
  --correlation-id "corr.task-contract.1"
  --retry-request "retry.task-contract.1"
  --expected-action "Review the frozen head and reply with evidence."
  --evidence-ref "git:abc123"
  --evidence-ref "path:skills/multi-agent-orchestration/SKILL.md"
  --text "Please review the frozen candidate."
)

printf '%s\n' "Case 1: structured send binds exact identities and only proves durable enqueue"
run_pm "${contract_args[@]}"
assert_eq "contract send succeeds" "0" "$LAST_RC"
assert_true "receipt names durable enqueue and excludes later states" jq -e '
  .mao_message_receipt.state == "durably_enqueued"
  and .mao_message_receipt.message_id == "msg-contract-1"
  and .mao_message_receipt.sender_handle == "term-pm-contract"
  and .mao_message_receipt.thread_id == "thread.task-contract"
  and .mao_message_receipt.native_thread_id == "corr.task-contract.1"
  and .mao_message_receipt.correlation_id == "corr.task-contract.1"
  and .mao_message_receipt.retry_request == "retry.task-contract.1"
  and (.mao_message_receipt.contract_sha256 | test("^[0-9a-f]{64}$"))
  and (.mao_message_receipt.does_not_prove == ["delivered_visible","consumed","replied","action_started","business_completed"])
' "$TMP_ROOT/stdout" >/dev/null
assert_true "native send receives exact routing, type, priority, thread and retry identity" jq -s -e '
  def after($flag): . as $a | ($a | index($flag)) as $i | if $i == null then null else $a[$i + 1] end;
  .[-1]
  | .[0:2] == ["orchestration","send"]
    and after("--to") == "dispatch:ctx-contract"
    and after("--run") == "run-contract"
    and after("--from") == "term-pm-contract"
    and after("--type") == "decision_gate"
    and after("--priority") == "high"
    and after("--thread-id") == "corr.task-contract.1"
    and after("--retry-request") == "retry.task-contract.1"
    and index("--task-id") == null
    and index("--dispatch-id") == null
' "$FAKE_ORCA_LOG" >/dev/null
assert_true "worker-show relationship is proven before run binding and send" jq -s -e '
  [to_entries[] | select(.value[0:2] == ["orchestration","worker-show"]) | .key][0] as $show
  | [to_entries[] | select(.value[0:2] == ["orchestration","run-use"]) | .key][0] as $use
  | [to_entries[] | select(.value[0:2] == ["orchestration","send"]) | .key][0] as $send
  | $show < $use and $use < $send
' "$FAKE_ORCA_LOG" >/dev/null
assert_true "payload freezes context, correlation, action and typed evidence" jq -s -e '
  def after($flag): . as $a | ($a | index($flag)) as $i | if $i == null then null else $a[$i + 1] end;
  .[-1] | after("--payload") | fromjson
  | .schema == "multi-agent-orchestration.message-contract.v1"
    and .correlation_id == "corr.task-contract.1"
    and .retry_request == "retry.task-contract.1"
    and .expected_action == "Review the frozen head and reply with evidence."
    and .authority == "informational_only"
    and .message.thread_id == "thread.task-contract"
    and .evidence_refs == ["git:abc123","path:skills/multi-agent-orchestration/SKILL.md"]
    and .sender == {role:"coordinator",terminal_handle:"term-pm-contract"}
    and .recipient == {kind:"dispatch",dispatch_id:"ctx-contract"}
    and .context == {run_id:"run-contract",task_id:"task-contract",dispatch_id:"ctx-contract"}
' "$FAKE_ORCA_LOG" >/dev/null
assert_true "retry fingerprint ledger stores only request identity and digest" jq -s -e '
  length == 1
  and .[0].schema == "multi-agent-orchestration.message-retry-fingerprint.v1"
  and .[0].retry_request == "retry.task-contract.1"
  and (.[0].contract_sha256 | test("^[0-9a-f]{64}$"))
  and (.[0] | has("body") | not)
' "$CONTEXT/MESSAGE_RETRY_FINGERPRINTS.ndjson" >/dev/null

run_pm "${contract_args[@]}"
assert_eq "exact native retry succeeds" "0" "$LAST_RC"
assert_eq "exact retry does not duplicate the fingerprint" "1" "$(wc -l < "$CONTEXT/MESSAGE_RETRY_FINGERPRINTS.ndjson" | tr -d ' ')"

printf '%s\n' "Case 2: normal priority is contract metadata, not a native Orca flag"
normal_args=("${contract_args[@]}")
for index in "${!normal_args[@]}"; do
  if [ "${normal_args[index]}" = "high" ]; then normal_args[index]="normal"; fi
  if [ "${normal_args[index]}" = "retry.task-contract.1" ]; then normal_args[index]="retry.task-contract.normal"; fi
done
run_pm "${normal_args[@]}"
assert_eq "normal-priority send succeeds" "0" "$LAST_RC"
assert_true "native argv omits normal priority" jq -s -e '.[-1] | index("--priority") == null' "$FAKE_ORCA_LOG" >/dev/null
assert_true "payload retains normal priority semantics" jq -s -e '
  def after($flag): . as $a | ($a | index($flag)) as $i | $a[$i + 1];
  .[-1] | after("--payload") | fromjson | .message.priority == "normal"
' "$FAKE_ORCA_LOG" >/dev/null

assert_zero_orca_rejection() {
  local description="$1" expected_code="$2"
  assert_eq "$description exits with usage error" "64" "$LAST_RC"
  assert_eq "$description makes zero Orca calls" "0" "$(wc -l < "$FAKE_ORCA_LOG" | tr -d ' ')"
  assert_true "$description exposes stable reason" grep -qF "$expected_code" "$TMP_ROOT/stderr"
}

printf '%s\n' "Case 3: invalid contract inputs are rejected before any Orca call"
changed_retry_args=("${contract_args[@]}")
for index in "${!changed_retry_args[@]}"; do
  if [ "${changed_retry_args[index]}" = "Please review the frozen candidate." ]; then
    changed_retry_args[index]="Changed body under the same retry identity."
  fi
done
run_pm "${changed_retry_args[@]}"
assert_zero_orca_rejection "changed payload under one retry id" "PM_MESSAGE_RETRY_CONTRACT_MISMATCH"

run_pm send --worktree "$WT" --session "$SESSION" --message-contract \
  --message-type worker_done --thread-id thread-1 --correlation-id corr-1 \
  --expected-action act --text body
assert_zero_orca_rejection "worker-only type" "PM_MESSAGE_CONTRACT_TYPE_REJECTED"

run_pm send --worktree "$WT" --session "$SESSION" --message-contract \
  --thread-id thread-1 --expected-action act --text body
assert_zero_orca_rejection "missing correlation" "PM_MESSAGE_CONTRACT_CORRELATION_INVALID"

run_pm send --worktree "$WT" --session "$SESSION" --message-contract \
  --thread-id thread-1 --correlation-id corr-1 --expected-action act \
  --text 'api_key=sk-abcdefghijklmnopqrstuv'
assert_zero_orca_rejection "credential-like body" "PM_MESSAGE_CONTRACT_SENSITIVE_REJECTED"

run_pm send --worktree "$WT" --session "$SESSION" --message-contract \
  --thread-id thread-1 --correlation-id github_pat_abcdefghijklmnopqrstuv \
  --expected-action act --text body
assert_zero_orca_rejection "credential-like correlation id" "PM_MESSAGE_CONTRACT_SENSITIVE_REJECTED"

run_pm send --worktree "$WT" --session "$SESSION" --message-contract \
  --thread-id sk-abcdefghijklmnopqrstuv --correlation-id corr-1 \
  --expected-action act --text body
assert_zero_orca_rejection "credential-like thread id" "PM_MESSAGE_CONTRACT_SENSITIVE_REJECTED"

run_pm send --worktree "$WT" --session "$SESSION" --message-contract \
  --thread-id thread-1 --correlation-id corr-1 --retry-request ghp_abcdefghijklmnopqrstuv \
  --expected-action act --text body
assert_zero_orca_rejection "credential-like retry id" "PM_MESSAGE_CONTRACT_SENSITIVE_REJECTED"

run_pm send --worktree "$WT" --session "$SESSION" --message-contract \
  --thread-id thread-1 --correlation-id corr-1 --expected-action act \
  --text 'token=abcdefghijklmnopqrstuv'
assert_zero_orca_rejection "bare token assignment" "PM_MESSAGE_CONTRACT_SENSITIVE_REJECTED"

run_pm send --worktree "$WT" --session "$SESSION" --message-contract \
  --thread-id thread-1 --correlation-id corr-1 --expected-action act \
  --evidence-ref path:/etc/passwd --text body
assert_zero_orca_rejection "absolute evidence path" "PM_MESSAGE_CONTRACT_EVIDENCE_INVALID"

run_pm send --worktree "$WT" --session "$SESSION" \
  --thread-id thread-1 --text body
assert_zero_orca_rejection "contract field without opt-in" "PM_MESSAGE_CONTRACT_REQUIRED"

run_pm inbox --worktree "$WT" --session "$SESSION" --thread-id thread-1
assert_zero_orca_rejection "partial inbox correlation filter" "PM_MESSAGE_INBOX_FILTER_INCOMPLETE"

run_pm inbox --worktree "$WT" --session "$SESSION" \
  --thread-id '../thread' --correlation-id corr-1
assert_zero_orca_rejection "unsafe inbox thread filter" "PM_MESSAGE_INBOX_THREAD_INVALID"

run_pm inbox --worktree "$WT" --session "$SESSION" \
  --from github_pat_abcdefghijklmnopqrstuv
assert_zero_orca_rejection "credential-like explicit inbox sender" "PM_MESSAGE_INBOX_SENSITIVE_REJECTED"

cp "$METADATA" "$TMP_ROOT/clean-metadata.json"
jq '.session.orca.supervised.coordinator_handle = "github_pat_abcdefghijklmnopqrstuv"' \
  "$TMP_ROOT/clean-metadata.json" > "$METADATA"
run_pm inbox --worktree "$WT" --session "$SESSION"
assert_zero_orca_rejection "credential-like recorded inbox sender" "PM_MESSAGE_INBOX_SENSITIVE_REJECTED"

jq '.session.orca.terminal_handle = "github_pat_abcdefghijklmnopqrstuv"' \
  "$TMP_ROOT/clean-metadata.json" > "$METADATA"
run_pm inbox --worktree "$WT" --session "$SESSION"
assert_zero_orca_rejection "credential-like inbox worker handle" "PM_MESSAGE_INBOX_SENSITIVE_REJECTED"
cp "$TMP_ROOT/clean-metadata.json" "$METADATA"

: > "$FAKE_ORCA_LOG"
touch "$FAKE_ORCA_STATE/binding-mismatch"
set +e
bash "$PM" send --worktree "$WT" --session "$SESSION" --message-contract \
  --thread-id thread.binding --correlation-id corr.binding.1 \
  --expected-action act --text body > "$TMP_ROOT/stdout" 2> "$TMP_ROOT/stderr"
LAST_RC=$?
set -e
assert_eq "mismatched Task/Dispatch binding is rejected" "3" "$LAST_RC"
assert_true "binding mismatch reaches read-only worker-show only" jq -s -e '
  (map(select(.[0:2] == ["orchestration","worker-show"])) | length == 1)
  and (map(select(index("run-use") != null or .[0:2] == ["orchestration","send"])) | length == 0)
' "$FAKE_ORCA_LOG" >/dev/null
assert_true "binding mismatch exposes stable reason" grep -qF "PM_MESSAGE_DISPATCH_BINDING_INVALID" "$TMP_ROOT/stderr"
rm -f "$FAKE_ORCA_STATE/binding-mismatch"

: > "$FAKE_ORCA_LOG"
touch "$FAKE_ORCA_STATE/settled-worker"
set +e
bash "$PM" send --worktree "$WT" --session "$SESSION" --message-contract \
  --thread-id thread.settled --correlation-id corr.settled.1 \
  --expected-action act --text body > "$TMP_ROOT/stdout" 2> "$TMP_ROOT/stderr"
LAST_RC=$?
set -e
assert_eq "settled Dispatch cannot receive a new contract action" "3" "$LAST_RC"
assert_true "settled Dispatch rejects before run-use or send" jq -s -e '
  (map(select(.[0:2] == ["orchestration","worker-show"])) | length == 1)
  and (map(select(index("run-use") != null or .[0:2] == ["orchestration","send"])) | length == 0)
' "$FAKE_ORCA_LOG" >/dev/null
rm -f "$FAKE_ORCA_STATE/settled-worker"

printf '%s\n' "Case 4: structured contract cannot fall back to terminal or tmux transport"
cp "$METADATA" "$TMP_ROOT/supervised-metadata.json"
jq 'del(.session.orca.supervised)' "$TMP_ROOT/supervised-metadata.json" > "$METADATA"
run_pm send --worktree "$WT" --session "$SESSION" --message-contract \
  --thread-id thread-1 --correlation-id corr-1 --expected-action act --text body
assert_zero_orca_rejection "non-supervised transport" "PM_MESSAGE_CONTRACT_REQUIRES_ORCA_SUPERVISED"
cp "$TMP_ROOT/supervised-metadata.json" "$METADATA"

printf '%s\n' "Case 5: legacy supervised send remains backward compatible"
run_pm send --worktree "$WT" --session "$SESSION" --text "legacy guidance"
assert_eq "legacy send succeeds" "0" "$LAST_RC"
assert_true "legacy send keeps original exact argv surface" jq -s -e '
  def after($flag): . as $a | ($a | index($flag)) as $i | if $i == null then null else $a[$i + 1] end;
  .[-1]
  | after("--to") == "dispatch:ctx-contract"
    and after("--type") == "status"
    and after("--subject") == "PM guidance"
    and after("--body") == "legacy guidance"
    and index("--payload") == null
    and index("--thread-id") == null
    and index("--run") == null
' "$FAKE_ORCA_LOG" >/dev/null

printf '%s\n' "Case 6: inbox is read-only and does not advance Delivery"
run_pm inbox --worktree "$WT" --session "$SESSION" \
  --thread-id thread.task-contract --correlation-id corr.task-contract.1
assert_eq "inbox succeeds" "0" "$LAST_RC"
assert_true "inbox reports only the exact dispatch/thread/correlation match" jq -e '
  .mao_message_receipt.operation == "inbox"
  and .mao_message_receipt.state == "read_only_snapshot"
  and .mao_message_receipt.advances_delivery == false
  and .mao_message_receipt.observed_message_state == "delivered_visible"
  and .mao_message_receipt.matched_message_count == 1
  and .mao_message_receipt.matched_messages == [{id:"msg-worker-1",type:"question",sender_handle:"term-worker-contract",match_basis:"structured_payload",native_thread_id:"corr.task-contract.1",thread_id:"thread.task-contract",correlation_id:"corr.task-contract.1"}]
' "$TMP_ROOT/stdout" >/dev/null
assert_true "inbox calls check --peek and no mutation command" jq -s -e '
  (.[-1] == ["orchestration","check","--peek","--terminal","term-pm-contract","--json"])
  and (map(select(index("run-use") != null or index("send") != null or index("--ack") != null)) | length == 0)
' "$FAKE_ORCA_LOG" >/dev/null

touch "$FAKE_ORCA_STATE/no-messages"
: > "$FAKE_ORCA_LOG"
set +e
bash "$PM" inbox --worktree "$WT" --session "$SESSION" > "$TMP_ROOT/stdout" 2> "$TMP_ROOT/stderr"
LAST_RC=$?
set -e
assert_eq "empty inbox succeeds" "0" "$LAST_RC"
assert_true "empty inbox does not claim message visibility" jq -e '.mao_message_receipt.observed_message_state == "none_visible"' "$TMP_ROOT/stdout" >/dev/null
rm -f "$FAKE_ORCA_STATE/no-messages"

: > "$FAKE_ORCA_LOG"
touch "$FAKE_ORCA_STATE/unrelated-only"
set +e
bash "$PM" inbox --worktree "$WT" --session "$SESSION" > "$TMP_ROOT/stdout" 2> "$TMP_ROOT/stderr"
LAST_RC=$?
set -e
assert_eq "unrelated-only inbox succeeds" "0" "$LAST_RC"
assert_true "same-Run message from the exact worker cannot cross Dispatch identity" jq -e '
  .result.count == 1
  and .mao_message_receipt.observed_message_state == "none_visible"
  and .mao_message_receipt.matched_message_count == 0
  and .mao_message_receipt.matched_messages == []
' "$TMP_ROOT/stdout" >/dev/null
rm -f "$FAKE_ORCA_STATE/unrelated-only"

: > "$FAKE_ORCA_LOG"
touch "$FAKE_ORCA_STATE/native-reply"
set +e
bash "$PM" inbox --worktree "$WT" --session "$SESSION" \
  --thread-id thread.task-contract --correlation-id corr.task-contract.1 \
  > "$TMP_ROOT/stdout" 2> "$TMP_ROOT/stderr"
LAST_RC=$?
set -e
assert_eq "native reply shape is visible through the correlation thread bridge" "0" "$LAST_RC"
assert_true "native reply bridge reports only correlation visibility, not a reply claim" jq -e '
  .mao_message_receipt.observed_message_state == "delivered_visible"
  and .mao_message_receipt.matched_message_count == 1
  and .mao_message_receipt.matched_messages == [{id:"msg-native-reply",type:"unknown",sender_handle:"term-worker-contract",match_basis:"native_thread_correlation",native_thread_id:"corr.task-contract.1",thread_id:null,correlation_id:"corr.task-contract.1"}]
  and (.mao_message_receipt.does_not_prove | index("replied") != null)
' "$TMP_ROOT/stdout" >/dev/null

: > "$FAKE_ORCA_LOG"
set +e
bash "$PM" inbox --worktree "$WT" --session "$SESSION" > "$TMP_ROOT/stdout" 2> "$TMP_ROOT/stderr"
LAST_RC=$?
set -e
assert_eq "payloadless native reply without both filters is a valid empty snapshot" "0" "$LAST_RC"
assert_true "unfiltered native reply cannot be attributed to one Task/Dispatch" jq -e '
  .mao_message_receipt.observed_message_state == "none_visible"
  and .mao_message_receipt.matched_message_count == 0
' "$TMP_ROOT/stdout" >/dev/null
rm -f "$FAKE_ORCA_STATE/native-reply"

: > "$FAKE_ORCA_LOG"
touch "$FAKE_ORCA_STATE/alias-conflict"
set +e
bash "$PM" inbox --worktree "$WT" --session "$SESSION" \
  --thread-id thread.task-contract --correlation-id corr.task-contract.1 \
  > "$TMP_ROOT/stdout" 2> "$TMP_ROOT/stderr"
LAST_RC=$?
set -e
assert_eq "conflicting identity aliases yield a valid empty snapshot" "0" "$LAST_RC"
assert_true "a correct context alias cannot hide conflicting root aliases" jq -e '
  .mao_message_receipt.observed_message_state == "none_visible"
  and .mao_message_receipt.matched_message_count == 0
' "$TMP_ROOT/stdout" >/dev/null
rm -f "$FAKE_ORCA_STATE/alias-conflict"

for conflict_state in \
  type-alias-conflict \
  payload-type-conflict \
  payload-sender-conflict \
  payload-sender-role-conflict \
  payload-recipient-id-conflict \
  payload-recipient-kind-conflict \
  missing-recipient \
  wrong-recipient; do
  : > "$FAKE_ORCA_LOG"
  touch "$FAKE_ORCA_STATE/$conflict_state"
  set +e
  bash "$PM" inbox --worktree "$WT" --session "$SESSION" \
    --thread-id thread.task-contract --correlation-id corr.task-contract.1 \
    > "$TMP_ROOT/stdout" 2> "$TMP_ROOT/stderr"
  LAST_RC=$?
  set -e
  assert_eq "$conflict_state yields a valid empty snapshot" "0" "$LAST_RC"
  assert_true "$conflict_state cannot hide behind valid provenance aliases" jq -e '
    .mao_message_receipt.observed_message_state == "none_visible"
    and .mao_message_receipt.matched_message_count == 0
  ' "$TMP_ROOT/stdout" >/dev/null
  rm -f "$FAKE_ORCA_STATE/$conflict_state"
done

: > "$FAKE_ORCA_LOG"
touch "$FAKE_ORCA_STATE/missing-provenance"
set +e
bash "$PM" inbox --worktree "$WT" --session "$SESSION" > "$TMP_ROOT/stdout" 2> "$TMP_ROOT/stderr"
LAST_RC=$?
set -e
assert_eq "message without exact Task/Dispatch provenance is a valid empty snapshot" "0" "$LAST_RC"
assert_true "missing provenance cannot be attributed to the selected worker" jq -e '
  .mao_message_receipt.observed_message_state == "none_visible"
  and .mao_message_receipt.matched_message_count == 0
' "$TMP_ROOT/stdout" >/dev/null
rm -f "$FAKE_ORCA_STATE/missing-provenance"

: > "$FAKE_ORCA_LOG"
touch "$FAKE_ORCA_STATE/missing-run"
set +e
bash "$PM" inbox --worktree "$WT" --session "$SESSION" > "$TMP_ROOT/stdout" 2> "$TMP_ROOT/stderr"
LAST_RC=$?
set -e
assert_eq "message without an exact top-level Run succeeds as an empty snapshot" "0" "$LAST_RC"
assert_true "missing top-level Run cannot be attributed to the selected worker" jq -e '
  .mao_message_receipt.observed_message_state == "none_visible"
  and .mao_message_receipt.matched_message_count == 0
' "$TMP_ROOT/stdout" >/dev/null
rm -f "$FAKE_ORCA_STATE/missing-run"

for sender_state in missing-sender wrong-sender; do
  : > "$FAKE_ORCA_LOG"
  touch "$FAKE_ORCA_STATE/$sender_state"
  set +e
  bash "$PM" inbox --worktree "$WT" --session "$SESSION" > "$TMP_ROOT/stdout" 2> "$TMP_ROOT/stderr"
  LAST_RC=$?
  set -e
  assert_eq "$sender_state inbox succeeds as an empty snapshot" "0" "$LAST_RC"
  assert_true "$sender_state cannot impersonate the selected worker" jq -e '
    .mao_message_receipt.observed_message_state == "none_visible"
    and .mao_message_receipt.matched_message_count == 0
  ' "$TMP_ROOT/stdout" >/dev/null
  rm -f "$FAKE_ORCA_STATE/$sender_state"
done

printf '%s\n' "Case 7: stale runtime or sender fails before send/check"
: > "$FAKE_ORCA_LOG"
touch "$FAKE_ORCA_STATE/runtime-drift"
set +e
bash "$PM" inbox --worktree "$WT" --session "$SESSION" > "$TMP_ROOT/stdout" 2> "$TMP_ROOT/stderr"
LAST_RC=$?
set -e
assert_eq "runtime drift rejects inbox" "3" "$LAST_RC"
assert_true "runtime drift never reaches check" jq -s -e 'map(select(index("check") != null)) | length == 0' "$FAKE_ORCA_LOG" >/dev/null
rm -f "$FAKE_ORCA_STATE/runtime-drift"

: > "$FAKE_ORCA_LOG"
touch "$FAKE_ORCA_STATE/stale-terminal"
set +e
bash "$PM" "${contract_args[@]}" > "$TMP_ROOT/stdout" 2> "$TMP_ROOT/stderr"
LAST_RC=$?
set -e
assert_eq "stale sender rejects contract send" "3" "$LAST_RC"
assert_true "stale sender never reaches send" jq -s -e 'map(select(.[0:2] == ["orchestration","send"])) | length == 0' "$FAKE_ORCA_LOG" >/dev/null
rm -f "$FAKE_ORCA_STATE/stale-terminal"

printf '%s\n' "Case 8: rejected, malformed or misrouted Orca receipts cannot masquerade as enqueue"
for state in send-rejected send-malformed send-no-id send-wrong-destination send-wrong-dispatch send-legacy-message send-relay-no-id-side-id; do
  : > "$FAKE_ORCA_LOG"
  touch "$FAKE_ORCA_STATE/$state"
  set +e
  bash "$PM" "${contract_args[@]}" > "$TMP_ROOT/stdout" 2> "$TMP_ROOT/stderr"
  LAST_RC=$?
  set -e
  assert_eq "$state receipt rejects" "2" "$LAST_RC"
  assert_true "$state exposes stable receipt error" grep -qF "PM_MESSAGE_CONTRACT_RECEIPT_INVALID" "$TMP_ROOT/stderr"
  rm -f "$FAKE_ORCA_STATE/$state"
done

printf '\nResult: %s pass, %s fail\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
