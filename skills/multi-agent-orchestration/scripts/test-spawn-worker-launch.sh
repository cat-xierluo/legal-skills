#!/usr/bin/env bash
set -euo pipefail

REAL_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LAUNCH_HELPER="$REAL_SCRIPT_DIR/spawn-worker-launch.sh"
CASE_ROOT=$(mktemp -d)
FAKE_LOG="$CASE_ROOT/launch.log"
trap 'rm -rf "$CASE_ROOT"' EXIT

passed=0
failed=0

ok() {
  printf 'PASS: %s\n' "$1"
  passed=$((passed + 1))
}

bad() {
  printf 'FAIL: %s\n' "$1" >&2
  failed=$((failed + 1))
}

assert_eq() {
  local actual="$1" expected="$2" label="$3"
  if [ "$actual" = "$expected" ]; then
    ok "$label"
  else
    bad "$label (expected=$expected actual=$actual)"
  fi
}

# shellcheck source=spawn-worker-launch.sh
source "$LAUNCH_HELPER"

reset_launch_case() {
  SCRIPT_DIR="$REAL_SCRIPT_DIR"
  WORKTREE="$CASE_ROOT/worktree"
  SESSION="worker-session"
  COMMAND="codex"
  ORCA_MODE="force_tmux"
  ORCA_WORKTREE_ID="repo-1::worker"
  ORCA_TERMINAL_HANDLE=""
  ORCA_SUPERVISED=0
  ORCA_RUN_ID=""
  ORCA_COORDINATOR_HANDLE=""
  ORCA_TASK_ID=""
  TASK_SPEC="full spec"
  TASK_TITLE="short title"
  ORCA_SUPERVISED_RUN_ID=""
  ORCA_SUPERVISED_COORDINATOR_HANDLE=""
  ORCA_SUPERVISED_TASK_ID=""
  ORCA_SUPERVISED_DISPATCH_ID=""
  DRY_RUN=0
  METADATA_FILE="$CASE_ROOT/metadata.json"
  mkdir -p "$WORKTREE/.claude/agent-sessions/$SESSION"
  : > "$FAKE_LOG"
}

run() {
  printf '%s\n' "$*" >> "$FAKE_LOG"
}

orca_terminal_create_and_send() {
  printf '%s|%s|%s|%s\n' "$1" "$2" "$3" "$4" >> "$FAKE_LOG"
  ORCA_TERMINAL_HANDLE="term-worker"
}

reset_launch_case
launch_worker_session
if grep -Fq 'tmux new-session -d -s worker-session' "$FAKE_LOG"; then
  ok "tmux route keeps exact session launch arguments"
else
  bad "tmux route keeps exact session launch arguments"
fi
assert_eq "$COMMAND" "codex" "single-token command needs no launch wrapper"

reset_launch_case
COMMAND="codebuddy --permission-mode acceptEdits"
launch_worker_session
LAUNCH_SH="$WORKTREE/.claude/agent-sessions/$SESSION/launch.sh"
if [ -x "$LAUNCH_SH" ] && grep -Fq 'exec bash -c' "$LAUNCH_SH"; then
  ok "spaced command is wrapped in an executable launch script"
else
  bad "spaced command is wrapped in an executable launch script"
fi
case "$COMMAND" in
  bash\ *) ok "wrapped command points tmux at launch script" ;;
  *) bad "wrapped command points tmux at launch script" ;;
esac

reset_launch_case
SESSION="dry-run-worker-session"
COMMAND="codebuddy --permission-mode acceptEdits"
DRY_RUN=1
dry_run_plan=$(launch_worker_session)
DRY_SESSION_CONTEXT="$WORKTREE/.claude/agent-sessions/$SESSION"
LAUNCH_SH="$DRY_SESSION_CONTEXT/launch.sh"
if [ ! -e "$DRY_SESSION_CONTEXT" ]; then
  ok "dry-run spaced command does not write Session Context"
else
  bad "dry-run spaced command does not write Session Context"
fi
if printf '%s\n' "$dry_run_plan" | grep -Fq 'SPAWN_WORKER_DRY_RUN_LAUNCH_SH:'; then
  ok "dry-run spaced command reports the planned launch wrapper"
else
  bad "dry-run spaced command reports the planned launch wrapper"
fi

reset_launch_case
ORCA_MODE="auto"
printf '%s\n' '{"session":{"orca":{"terminal_handle":""}}}' > "$METADATA_FILE"
launch_worker_session
if grep -Fq 'repo-1::worker|worker-session|codex|请按你的任务开始工作' "$FAKE_LOG"; then
  ok "Orca terminal-managed route delegates one bootstrap prompt"
else
  bad "Orca terminal-managed route delegates one bootstrap prompt"
fi
if jq -e '.session.orca.terminal_handle == "term-worker"' "$METADATA_FILE" >/dev/null; then
  ok "Orca launch patches the exact terminal handle into metadata"
else
  bad "Orca launch patches the exact terminal handle into metadata"
fi

reset_launch_case
ORCA_MODE="auto"
ORCA_SUPERVISED=1
ORCA_RUN_ID="run-wave"
ORCA_COORDINATOR_HANDLE="term-pm"
ORCA_TASK_ID="task-worker"
DRY_RUN=1
supervised_plan=$(launch_worker_session)
if printf '%s' "$supervised_plan" | grep -Fq 'worker-start --terminal <handle>' \
  && printf '%s' "$supervised_plan" | grep -Fq 'run-wave'; then
  ok "supervised dry-run reports receipt reuse and worker-start"
else
  bad "supervised dry-run reports receipt reuse and worker-start"
fi

reset_launch_case
ORCA_MODE="auto"
ORCA_SUPERVISED=1
ORCA_RUN_ID="run-wave"
ORCA_COORDINATOR_HANDLE="term-pm"
ORCA_TASK_ID="task-worker"
SCRIPT_DIR="$CASE_ROOT/register-success"
mkdir -p "$SCRIPT_DIR"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'printf "ORCAREG_RUN_ID=run-wave\n"' \
  'printf "ORCAREG_COORDINATOR_HANDLE=term-pm\n"' \
  'printf "ORCAREG_TASK_ID=task-worker\n"' \
  'printf "ORCAREG_DISPATCH_ID=ctx-worker\n"' \
  > "$SCRIPT_DIR/orca-supervised-register.sh"
printf '%s\n' '{"session":{"orca":{"terminal_handle":""}}}' > "$METADATA_FILE"
launch_worker_session
assert_eq "$ORCA_SUPERVISED_RUN_ID:$ORCA_SUPERVISED_COORDINATOR_HANDLE:$ORCA_SUPERVISED_TASK_ID:$ORCA_SUPERVISED_DISPATCH_ID" \
  "run-wave:term-pm:task-worker:ctx-worker" "supervised registration exports exact lifecycle ids"
if jq -e '.session.orca.supervised == {run_id:"run-wave",coordinator_handle:"term-pm",task_id:"task-worker",dispatch_id:"ctx-worker",contract:"orca.orchestration.contract.v1",completion_authority:"worker_done",terminal_ownership:"external"}' "$METADATA_FILE" >/dev/null; then
  ok "supervised lifecycle contract is patched into metadata"
else
  bad "supervised lifecycle contract is patched into metadata"
fi

reset_launch_case
ORCA_MODE="auto"
ORCA_SUPERVISED=1
SCRIPT_DIR="$CASE_ROOT/register-missing"
mkdir -p "$SCRIPT_DIR"
set +e
( launch_worker_session ) >/dev/null 2>&1
missing_helper_rc=$?
set -e
assert_eq "$missing_helper_rc" "1" "missing supervised helper fails loud after terminal creation"

E2E_PROJECT="$CASE_ROOT/dry-run-project"
E2E_BIN="$CASE_ROOT/dry-run-bin"
E2E_SESSION="dry-run-e2e"
mkdir -p "$E2E_PROJECT" "$E2E_BIN"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'if [ "${1:-}" = "has-session" ]; then exit 1; fi' \
  'exit 0' \
  > "$E2E_BIN/tmux"
chmod +x "$E2E_BIN/tmux"
set +e
e2e_output=$(PATH="$E2E_BIN:$PATH" bash "$REAL_SCRIPT_DIR/spawn-worker.sh" \
  --project "$E2E_PROJECT" \
  --no-worktree \
  --no-orca-mode \
  --session "$E2E_SESSION" \
  --worker-backend codebuddy \
  --command 'codebuddy --permission-mode acceptEdits' \
  --dry-run 2>&1)
e2e_rc=$?
set -e
assert_eq "$e2e_rc" "0" "entrypoint accepts a dry-run spaced command"
if [ ! -e "$E2E_PROJECT/.claude/agent-sessions/$E2E_SESSION" ]; then
  ok "entrypoint dry-run leaves Session Context absent"
else
  bad "entrypoint dry-run leaves Session Context absent"
fi
if printf '%s\n' "$e2e_output" | grep -Fq 'SPAWN_WORKER_DRY_RUN_LAUNCH_SH:'; then
  ok "entrypoint dry-run exposes the planned wrapper"
else
  bad "entrypoint dry-run exposes the planned wrapper"
fi

if grep -Fq 'source "$SCRIPT_DIR/spawn-worker-launch.sh"' "$REAL_SCRIPT_DIR/spawn-worker.sh" \
  && ! grep -q '^launch_worker_session() {' "$REAL_SCRIPT_DIR/spawn-worker.sh"; then
  ok "entrypoint delegates the shared launch boundary"
else
  bad "entrypoint delegates the shared launch boundary"
fi

printf 'spawn-worker launch tests: %s passed, %s failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
