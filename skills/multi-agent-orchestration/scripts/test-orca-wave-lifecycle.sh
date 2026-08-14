#!/usr/bin/env bash
# Fake-Orca integration for Wave task preparation, pre-created Task reuse and PM rebinding.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WAVE="$SCRIPT_DIR/orca-wave-prepare.sh"
REGISTER="$SCRIPT_DIR/orca-supervised-register.sh"
PM="$SCRIPT_DIR/pm-orchestrate.sh"
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT

pass=0
fail=0
ok() { echo "  ✓ $1"; pass=$((pass + 1)); }
bad() { echo "  ✗ $1" >&2; fail=$((fail + 1)); }

FAKE="$TMP_ROOT/fake-orca"
export FAKE_ORCA_LOG="$TMP_ROOT/orca.log"
export FAKE_ORCA_STATE="$TMP_ROOT/orca-state"
: > "$FAKE_ORCA_LOG"
: > "$FAKE_ORCA_STATE"

cat > "$FAKE" <<'FAKE'
#!/usr/bin/env bash
set -euo pipefail
{
  for arg in "$@"; do printf '%q ' "$arg"; done
  printf '\n'
} >> "$FAKE_ORCA_LOG"
case "$1 $2" in
  "orchestration run-create")
    echo '{"ok":true,"result":{"run":{"id":"run-wave","coordinator_handle":"term-pm"}}}'
    ;;
  "orchestration run-use")
    echo '{"ok":true,"result":{"run":{"id":"run-wave","coordinator_handle":"term-pm-rebound"}}}'
    ;;
  "orchestration task-create")
    count=$(wc -l < "$FAKE_ORCA_STATE" | tr -d ' ')
    count=$((count + 1))
    printf '%s\n' "$count" >> "$FAKE_ORCA_STATE"
    printf '{"ok":true,"result":{"task":{"id":"task-%s"}}}\n' "$count"
    ;;
  "orchestration worker-start")
    task=""
    while [ "$#" -gt 0 ]; do
      if [ "$1" = "--task" ]; then task="$2"; break; fi
      shift
    done
    printf '{"ok":true,"result":{"dispatch":{"id":"ctx-%s"}}}\n' "$task"
    ;;
  "orchestration check")
    echo '{"ok":true,"result":{"count":0}}'
    ;;
  *)
    echo '{"ok":true,"result":{}}'
    ;;
esac
FAKE
chmod +x "$FAKE"
export ORCA_CLI_COMMAND="$FAKE"

MANIFEST="$TMP_ROOT/wave.json"
cat > "$MANIFEST" <<'JSON'
{
  "objective": "harden lifecycle",
  "tasks": [
    {"key": "api", "title": "API", "spec": "Change API only; run API tests."},
    {"key": "ui", "title": "UI", "spec": "Change UI only; run UI tests."}
  ]
}
JSON

echo "Case 1: Wave creates one Run and every Task before worker start"
RECEIPT="$TMP_ROOT/wave-receipt.json"
bash "$WAVE" --manifest "$MANIFEST" --receipt "$RECEIPT" > "$TMP_ROOT/wave.out"
if jq -e '.run_id == "run-wave" and (.tasks | length == 2) and .tasks[0].task_id == "task-1" and .tasks[1].task_id == "task-2"' "$RECEIPT" >/dev/null; then
  ok "Wave receipt contains one Run and two Tasks"
else
  bad "Wave receipt is incomplete"
fi
[ "$(grep -c '^orchestration run-create ' "$FAKE_ORCA_LOG")" -eq 1 ] && ok "run-create called once" || bad "run-create was not called exactly once"
[ "$(grep -c '^orchestration task-create ' "$FAKE_ORCA_LOG")" -eq 2 ] && ok "both Tasks pre-created" || bad "expected two task-create calls"
prefixed_spec=$(bash -c 'source "$1"; orca_supervised_task_spec "BUSINESS SPEC"' _ "$SCRIPT_DIR/orca-supervised-protocol.sh")
if [[ "$prefixed_spec" == SUPERVISED\ COMPLETION\ PROTOCOL* ]] \
  && [[ "$prefixed_spec" == *$'\n\nBUSINESS SPEC' ]] \
  && grep -q 'SUPERVISED.*COMPLETION.*PROTOCOL' "$FAKE_ORCA_LOG"; then
  ok "worker_done reminder is the first Task-spec paragraph"
else
  bad "Task-spec completion reminder missing or misplaced"
fi

echo "Case 2: pre-created Tasks are reused without task-create races"
bash "$REGISTER" --worktree-id 'repo::/tmp/api' --terminal-handle term-api \
  --run-id run-wave --coordinator-handle term-pm --task-id task-1 > "$TMP_ROOT/register-api.out"
bash "$REGISTER" --worktree-id 'repo::/tmp/ui' --terminal-handle term-ui \
  --run-id run-wave --coordinator-handle term-pm --task-id task-2 > "$TMP_ROOT/register-ui.out"
[ "$(grep -c '^orchestration task-create ' "$FAKE_ORCA_LOG")" -eq 2 ] && ok "register reused Tasks without creating more" || bad "register created a Task during worker start"
[ "$(grep -c '^orchestration worker-start ' "$FAKE_ORCA_LOG")" -eq 2 ] && ok "both workers started from pre-created Tasks" || bad "expected two worker-start calls"
if ! grep -q '^orchestration run-use ' "$FAKE_ORCA_LOG"; then
  ok "parallel registration reuses the receipt handle without run-use rebinding"
else
  bad "pre-created Task registration unexpectedly rebound the Run"
fi

echo "Case 3: PM wait rebinds the Run before consuming Delivery"
REPO="$TMP_ROOT/repo"
WT="$TMP_ROOT/pm-worker"
SESSION=pm-rebind
mkdir -p "$REPO"
git -C "$REPO" init -q
printf '%s\n' base > "$REPO/base.txt"
git -C "$REPO" add base.txt
GIT_AUTHOR_NAME=Test GIT_AUTHOR_EMAIL=test@example.invalid \
  GIT_COMMITTER_NAME=Test GIT_COMMITTER_EMAIL=test@example.invalid \
  git -C "$REPO" commit -q -m base
git -C "$REPO" worktree add -q -b test-pm-rebind "$WT"
mkdir -p "$WT/.claude/agent-sessions/$SESSION"
jq -n --arg project "$REPO" --arg worktree "$WT" --arg session "$SESSION" \
  '{project:$project,worktree:$worktree,session:{id:$session,orca:{worktree_id:"repo::worker",terminal_handle:"term-worker",supervised:{run_id:"run-wave",coordinator_handle:"term-old",task_id:"task-1",dispatch_id:"ctx-task-1"}}},runtime:{provider_lease:{file:""}}}' \
  > "$WT/.claude/agent-sessions/$SESSION/METADATA.json"
: > "$FAKE_ORCA_LOG"
bash "$PM" wait --worktree "$WT" --session "$SESSION" --timeout 1 > "$TMP_ROOT/wait.out"
first_call=$(sed -n '1p' "$FAKE_ORCA_LOG")
second_call=$(sed -n '2p' "$FAKE_ORCA_LOG")
[[ "$first_call" == orchestration\ run-use* ]] && ok "run-use happens before check" || bad "first PM call was not run-use"
[[ "$second_call" == orchestration\ check* ]] && [[ "$second_call" != *'--run'* ]] && ok "check consumes the bound Run without stale --run routing" || bad "check did not use rebound coordinator"
[ "$(jq -r '.session.orca.supervised.coordinator_handle' "$WT/.claude/agent-sessions/$SESSION/METADATA.json")" = "term-pm-rebound" ] && ok "rebound coordinator handle persisted" || bad "METADATA coordinator handle was not refreshed"

echo ""
echo "Result: $pass pass, $fail fail"
[ "$fail" -eq 0 ]
