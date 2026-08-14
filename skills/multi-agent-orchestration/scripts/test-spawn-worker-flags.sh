#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
FLAGS_HELPER="$SCRIPT_DIR/spawn-worker-flags.sh"
SPAWN_WORKER="$SCRIPT_DIR/spawn-worker.sh"

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

reset_defaults() {
  PROJECT_DIR=""
  BRANCH=""
  WORKTREE=""
  SESSION=""
  BASE_REF="main"
  COMMAND=""
  DRY_RUN=0
  WORKER_BACKEND=""
  PM_HARNESS_ASSERTION=""
  RUNTIME_PROFILE=""
  API_PROVIDER=""
  MODEL=""
  PROVIDER_SLOT=""
  ENV_ISOLATION=""
  WAVE_ID=""
  WAVE_WORKER_ID=""
  VERIFY_COMMANDS=()
  WITH_SENTINEL=0
  SENTINEL_POLL_INTERVAL=5
  SENTINEL_MAX_WAIT=7200
  KEEP_TMUX_ON_TERMINAL=0
  TRUST_AUTO_OVERRIDE=0
  TRUST_AUTO=1
  PERMISSION_AUTO_OVERRIDE=0
  PERMISSION_AUTO=1
  PERMISSION_AUTO_BG_OVERRIDE=0
  PERMISSION_AUTO_BG=1
  EXTERNAL_IMPORTS_AUTO_OVERRIDE=0
  EXTERNAL_IMPORTS_AUTO=0
  CLAUDE_CODE_BARE_AUTO_DEGRADE=1
  ADD_DIRS=()
  ALLOW_PATHS=()
  LIGHTWEIGHT_OVERRIDE=0
  LIGHTWEIGHT_MODE=0
  NO_ORCA_MODE=0
  ORCA_SUPERVISED=0
  TASK_SPEC=""
  TASK_TITLE=""
  ORCA_RUN_ID=""
  ORCA_TASK_ID=""
  ORCA_COORDINATOR_HANDLE=""
  INSTALL_AUTHORIZATION_SOURCE=""
  AUTHORIZED_INSTALL_COMMANDS=()
  ALLOWED_SHELL_COMMANDS=()
  GIT_EXPECTED_NAME=""
  GIT_EXPECTED_EMAIL=""
  GIT_INTEGRATION_BASE=""
  GIT_PUSH_REMOTE="origin"
  ALLOW_PROMPT_ONLY_INSTALL_GUARD=0
  INSTALL_GUARD_DEGRADATION_SOURCE=""
}

# shellcheck source=spawn-worker-flags.sh
source "$FLAGS_HELPER"

reset_defaults
parse_spawn_worker_args \
  --project "/tmp/project path" --branch "feat/flags" --worktree "/tmp/worker path" \
  --session "flags-session" --base-ref "origin/main" --command "codex exec" \
  --worker-backend codex --pm-harness codex --runtime-profile strict \
  --api-provider provider-a --model model-a --provider-slot slot-a \
  --env-isolation isolated --wave-id wave-a --wave-worker-id worker-a \
  --verify-cmd "bash test-a.sh" --verify-cmd "bash test-b.sh" \
  --with-sentinel --sentinel-poll-interval 7 --sentinel-max-wait 90 \
  --keep-tmux-on-terminal --no-trust-auto --trust-auto \
  --no-permission-auto --permission-auto --no-permission-auto-bg \
  --no-external-imports-auto --external-imports-auto \
  --no-claude-code-bare-auto-degrade \
  --add-dir /tmp/a --add-dir "/tmp/b path" \
  --allow-paths "skills/a/**" --allow-paths "skills/b/**" \
  --no-worktree --no-orca-mode --orca-supervised \
  --task-spec "full spec" --task-title "short title" \
  --orca-run-id run-a --orca-task-id task-a --orca-coordinator-handle term-pm \
  --allow-install-command "pip install demo" \
  --install-authorization-source "user approval" \
  --allow-shell-command "git status" \
  --git-expected-name "Expected User" --git-expected-email expected@example.com \
  --git-integration-base origin/main --git-push-remote upstream \
  --allow-prompt-only-install-guard "accepted degradation" --dry-run

assert_eq "$PROJECT_DIR" "/tmp/project path" "project preserves spaces"
assert_eq "$BRANCH" "feat/flags" "branch parsed"
assert_eq "$SESSION" "flags-session" "session parsed"
assert_eq "$WORKER_BACKEND" "codex" "backend parsed"
assert_eq "$WITH_SENTINEL:$KEEP_TMUX_ON_TERMINAL" "1:1" "sentinel booleans parsed"
assert_eq "$TRUST_AUTO:$TRUST_AUTO_OVERRIDE" "1:1" "last trust toggle wins"
assert_eq "$PERMISSION_AUTO:$PERMISSION_AUTO_BG" "1:0" "permission toggles remain independently overridable"
assert_eq "$EXTERNAL_IMPORTS_AUTO:$EXTERNAL_IMPORTS_AUTO_OVERRIDE" "1:1" "external import toggle parsed"
assert_eq "$CLAUDE_CODE_BARE_AUTO_DEGRADE" "0" "bare degradation opt-out parsed"
assert_eq "$LIGHTWEIGHT_MODE:$NO_ORCA_MODE:$ORCA_SUPERVISED" "1:1:1" "transport mode flags parsed"
assert_eq "$ORCA_RUN_ID:$ORCA_TASK_ID:$ORCA_COORDINATOR_HANDLE" "run-a:task-a:term-pm" "Wave receipt identifiers parsed"
assert_eq "$GIT_EXPECTED_NAME:$GIT_EXPECTED_EMAIL:$GIT_INTEGRATION_BASE:$GIT_PUSH_REMOTE" \
  "Expected User:expected@example.com:origin/main:upstream" "safe-push identity fields parsed"
assert_eq "$ALLOW_PROMPT_ONLY_INSTALL_GUARD:$INSTALL_GUARD_DEGRADATION_SOURCE:$DRY_RUN" \
  "1:accepted degradation:1" "degradation receipt and dry-run parsed"
assert_eq "${#VERIFY_COMMANDS[@]}:${VERIFY_COMMANDS[0]}:${VERIFY_COMMANDS[1]}" \
  "2:bash test-a.sh:bash test-b.sh" "repeatable verify commands preserve order"
assert_eq "${#ADD_DIRS[@]}:${ADD_DIRS[1]}" "2:/tmp/b path" "repeatable add-dir preserves spaces"
assert_eq "${#ALLOW_PATHS[@]}:${ALLOW_PATHS[0]}:${ALLOW_PATHS[1]}" \
  "2:skills/a/**:skills/b/**" "repeatable scope globs preserve order"
assert_eq "${#AUTHORIZED_INSTALL_COMMANDS[@]}:${AUTHORIZED_INSTALL_COMMANDS[0]}" \
  "1:pip install demo" "install authorization command parsed"
assert_eq "${#ALLOWED_SHELL_COMMANDS[@]}:${ALLOWED_SHELL_COMMANDS[0]}" \
  "1:git status" "allowed shell command parsed"

set +e
help_output=$( (parse_spawn_worker_args --help) 2>&1 )
help_rc=$?
unknown_output=$( (parse_spawn_worker_args --unknown-flag) 2>&1 )
unknown_rc=$?
set -e

assert_eq "$help_rc" "0" "help exits zero"
if printf '%s' "$help_output" | grep -Fq 'spawn-worker.sh --project PATH'; then
  ok "help text remains available from helper"
else
  bad "help text remains available from helper"
fi
assert_eq "$unknown_rc" "64" "unknown flag keeps exit 64"
if printf '%s' "$unknown_output" | grep -Fq 'Unknown argument: --unknown-flag'; then
  ok "unknown flag keeps diagnostic"
else
  bad "unknown flag keeps diagnostic"
fi

if grep -Fq 'source "$SCRIPT_DIR/spawn-worker-flags.sh"' "$SPAWN_WORKER" \
  && grep -Fq 'parse_spawn_worker_args "$@"' "$SPAWN_WORKER" \
  && ! grep -Fq 'while [[ $# -gt 0 ]]' "$SPAWN_WORKER"; then
  ok "entrypoint delegates parsing without retaining legacy loop"
else
  bad "entrypoint delegates parsing without retaining legacy loop"
fi

printf 'spawn-worker flags tests: %s passed, %s failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
