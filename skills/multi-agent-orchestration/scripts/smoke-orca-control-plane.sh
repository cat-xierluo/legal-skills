#!/usr/bin/env bash
# Deterministic smoke for Orca registration and PM routing. Uses a local fake
# CLI, creates no Orca resources and never starts a real Agent.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TMP_ROOT=$(mktemp -d)
TMP_ROOT=$(cd "$TMP_ROOT" && pwd -P)
FAKE_ORCA="$TMP_ROOT/orca-fake"
FAKE_LOG="$TMP_ROOT/orca.log"
WT="$TMP_ROOT/worktree"
SESSION="worker-a"
CTX="$WT/.claude/agent-sessions/$SESSION"

cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

assert_log_contains() {
  local needle="$1"
  if ! grep -qF -- "$needle" "$FAKE_LOG"; then
    echo "FAIL: fake Orca log missing: $needle" >&2
    sed -n '1,160p' "$FAKE_LOG" >&2
    exit 1
  fi
}

assert_log_not_contains() {
  local needle="$1"
  if grep -qF -- "$needle" "$FAKE_LOG"; then
    echo "FAIL: fake Orca log unexpectedly contains: $needle" >&2
    sed -n '1,160p' "$FAKE_LOG" >&2
    exit 1
  fi
}

cat > "$FAKE_ORCA" <<'FAKE'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$ORCA_FAKE_LOG"
case "$1 $2" in
  "orchestration run-create") printf '%s\n' '{"ok":true,"result":{"run":{"id":"run_test","coordinator_handle":"term_pm"}}}' ;;
  "orchestration run-use") printf '%s\n' '{"ok":true,"result":{"run":{"id":"run_test","coordinator_handle":"term_pm"}}}' ;;
  "orchestration task-create") printf '%s\n' '{"ok":true,"result":{"task":{"id":"task_test"}}}' ;;
  "orchestration worker-start") printf '%s\n' '{"ok":true,"result":{"dispatch":{"id":"ctx_test"}}}' ;;
  "orchestration worker-read") printf '%s\n' '{"ok":true,"result":{"source":"transcript","cursor":"cursor_2","rows":[]}}' ;;
  "orchestration worker-show") printf '%s\n' '{"ok":true,"result":{"worker":{"state":"ready","task_status":"dispatched","dispatch_status":"dispatched"}}}' ;;
  "orchestration check") printf '%s\n' '{"ok":true,"result":{"delivery":{"id":"delivery_test","messages":[]}}}' ;;
  "orchestration worker-list") printf '%s\n' "{\"ok\":true,\"result\":{\"workers\":[{\"dispatch_id\":\"ctx_external\",\"worker_state\":\"succeeded\",\"dispatch_status\":\"completed\",\"terminal_state\":\"retained\",\"agentTerminalHandle\":\"${ORCA_FAKE_RESOURCE_HANDLE:-term_external}\",\"resource\":{\"ownershipState\":\"external\",\"retainedReason\":\"external_terminal\"}}]}}" ;;
  "terminal read") printf '%s\n' '{"ok":true,"result":{"terminal":{"nextCursor":"terminal_cursor_2","tail":[]}}}' ;;
  *) printf '%s\n' '{"ok":true,"result":{}}' ;;
esac
FAKE
chmod +x "$FAKE_ORCA"
mkdir -p "$CTX"
: > "$FAKE_LOG"

echo "=== register: one mutation sequence, worker-start is the injector ==="
register_out=$(ORCA_CLI_COMMAND="$FAKE_ORCA" ORCA_FAKE_LOG="$FAKE_LOG" \
  bash "$SCRIPT_DIR/orca-supervised-register.sh" \
  --worktree-id 'repo::/tmp/worker-a' --terminal-handle term_test \
  --task-title 'worker-a' --task-spec '完成限定任务并验证')
printf '%s\n' "$register_out" | grep -qF 'ORCAREG_RUN_ID=run_test'
printf '%s\n' "$register_out" | grep -qF 'ORCAREG_COORDINATOR_HANDLE=term_pm'
printf '%s\n' "$register_out" | grep -qF 'ORCAREG_TASK_ID=task_test'
printf '%s\n' "$register_out" | grep -qF 'ORCAREG_DISPATCH_ID=ctx_test'
assert_log_contains 'orchestration run-create --objective 完成限定任务并验证 --json'
assert_log_contains 'orchestration task-create --spec SUPERVISED COMPLETION PROTOCOL (MANDATORY):'
assert_log_contains '完成限定任务并验证 --task-title worker-a --run run_test --from term_pm --json'
assert_log_contains 'orchestration worker-start --task task_test --terminal term_test --worktree id:repo::/tmp/worker-a --run run_test --from term_pm --timeout-ms 60000 --json'

cat > "$CTX/METADATA.json" <<'JSON'
{
  "session": {
    "orca": {
      "terminal_handle": "term_test",
      "supervised": {
        "run_id": "run_test",
        "task_id": "task_test",
        "dispatch_id": "ctx_test"
      }
    }
  }
}
JSON

echo "=== PM send/read/show: supervised routes by Dispatch, never TUI prompt ==="
: > "$FAKE_LOG"
ORCA_CLI_COMMAND="$FAKE_ORCA" ORCA_FAKE_LOG="$FAKE_LOG" \
  bash "$SCRIPT_DIR/pm-orchestrate.sh" send --worktree "$WT" --session "$SESSION" --text '只修测试'
ORCA_CLI_COMMAND="$FAKE_ORCA" ORCA_FAKE_LOG="$FAKE_LOG" \
  bash "$SCRIPT_DIR/pm-orchestrate.sh" read --worktree "$WT" --session "$SESSION" --lines 12 --cursor cursor_1 >/dev/null
ORCA_CLI_COMMAND="$FAKE_ORCA" ORCA_FAKE_LOG="$FAKE_LOG" \
  bash "$SCRIPT_DIR/pm-orchestrate.sh" show --worktree "$WT" --session "$SESSION" >/dev/null
assert_log_contains 'orchestration send --to dispatch:ctx_test --type status --subject PM guidance --body 只修测试 --json'
assert_log_contains 'orchestration worker-read --dispatch ctx_test --limit 12 --cursor cursor_1 --json'
assert_log_contains 'orchestration worker-show --dispatch ctx_test --json'
assert_log_not_contains 'terminal send'

echo "=== PM wait/account/ack: Delivery is not auto-acked ==="
: > "$FAKE_LOG"
ORCA_CLI_COMMAND="$FAKE_ORCA" ORCA_FAKE_LOG="$FAKE_LOG" \
  bash "$SCRIPT_DIR/pm-orchestrate.sh" wait --worktree "$WT" --session "$SESSION" --timeout 3 >/dev/null
assert_log_contains 'orchestration run-use --id run_test --json'
assert_log_contains 'orchestration check --wait --types worker_done,escalation,question --timeout-ms 3000 --json'
assert_log_not_contains '--ack'
ORCA_CLI_COMMAND="$FAKE_ORCA" ORCA_FAKE_LOG="$FAKE_LOG" \
  bash "$SCRIPT_DIR/pm-orchestrate.sh" release --worktree "$WT" --session "$SESSION" >/dev/null
ORCA_CLI_COMMAND="$FAKE_ORCA" ORCA_FAKE_LOG="$FAKE_LOG" \
  bash "$SCRIPT_DIR/pm-orchestrate.sh" retain --worktree "$WT" --session "$SESSION" >/dev/null
ORCA_CLI_COMMAND="$FAKE_ORCA" ORCA_FAKE_LOG="$FAKE_LOG" \
  bash "$SCRIPT_DIR/pm-orchestrate.sh" ack --worktree "$WT" --session "$SESSION" --delivery-id delivery_test >/dev/null
assert_log_contains 'orchestration worker-release --dispatch ctx_test --json'
assert_log_contains 'orchestration worker-retain --dispatch ctx_test --json'
assert_log_contains 'orchestration check --ack delivery_test --json'

echo "=== terminal-managed read: cursor is preserved for alternate-screen TUIs ==="
cat > "$CTX/METADATA.json" <<'JSON'
{"session":{"orca":{"terminal_handle":"term_terminal_managed"}}}
JSON
: > "$FAKE_LOG"
ORCA_CLI_COMMAND="$FAKE_ORCA" ORCA_FAKE_LOG="$FAKE_LOG" \
  bash "$SCRIPT_DIR/pm-orchestrate.sh" read --worktree "$WT" --session "$SESSION" \
  --lines 5000 --cursor 0 >/dev/null
assert_log_contains 'terminal read --terminal term_terminal_managed --limit 5000 --cursor 0 --json'

echo "=== supervised cleanup: close only the exact settled external terminal ==="
clean_repo="$TMP_ROOT/clean-repo"
clean_wt="$TMP_ROOT/clean-worktree"
clean_session="clean-worker"
mkdir -p "$clean_repo"
git -C "$clean_repo" init -q
git -C "$clean_repo" config user.email smoke@example.invalid
git -C "$clean_repo" config user.name "Smoke Test"
printf 'smoke\n' > "$clean_repo/README.md"
printf '.claude/\n' > "$clean_repo/.gitignore"
git -C "$clean_repo" add README.md .gitignore
git -C "$clean_repo" commit -q -m init
git -C "$clean_repo" branch -M main
git -C "$clean_repo" worktree add -q -b feat/clean-worker "$clean_wt" main
mkdir -p "$clean_wt/.claude/agent-sessions/$clean_session"
cat > "$clean_wt/.claude/agent-sessions/$clean_session/METADATA.json" <<'JSON'
{"base_ref":"main","session":{"orca":{"mode":"auto","worktree_id":"repo::clean","terminal_handle":"term_external","supervised":{"dispatch_id":"ctx_external","terminal_ownership":"external"}}}}
JSON
: > "$FAKE_LOG"
ORCA_CLI_COMMAND="$FAKE_ORCA" ORCA_FAKE_LOG="$FAKE_LOG" \
  bash "$SCRIPT_DIR/clean-worktree.sh" --project "$clean_repo" \
  --branch feat/clean-worker --session "$clean_session" --execute >/dev/null
assert_log_contains 'orchestration worker-release --dispatch ctx_external --json'
assert_log_contains 'terminal close --terminal term_external --json'
assert_log_contains 'worktree rm --worktree id:repo::clean --force --json'

echo "=== supervised cleanup: mismatched external terminal fails closed ==="
bad_wt="$TMP_ROOT/bad-clean-worktree"
bad_session="bad-clean-worker"
git -C "$clean_repo" worktree add -q -b feat/bad-clean-worker "$bad_wt" main
mkdir -p "$bad_wt/.claude/agent-sessions/$bad_session"
cat > "$bad_wt/.claude/agent-sessions/$bad_session/METADATA.json" <<'JSON'
{"base_ref":"main","session":{"orca":{"mode":"auto","worktree_id":"repo::bad-clean","terminal_handle":"term_external","supervised":{"dispatch_id":"ctx_external","terminal_ownership":"external"}}}}
JSON
: > "$FAKE_LOG"
if ORCA_CLI_COMMAND="$FAKE_ORCA" ORCA_FAKE_LOG="$FAKE_LOG" ORCA_FAKE_RESOURCE_HANDLE="term_other" \
  bash "$SCRIPT_DIR/clean-worktree.sh" --project "$clean_repo" \
  --branch feat/bad-clean-worker --session "$bad_session" --execute >/dev/null 2>&1; then
  echo "FAIL: mismatched external terminal should block cleanup" >&2
  exit 1
fi
assert_log_not_contains 'terminal close --terminal term_other --json'
test -d "$bad_wt" || { echo "FAIL: blocked cleanup removed the worktree" >&2; exit 1; }

echo "SMOKE_ORCA_CONTROL_PLANE_OK"
