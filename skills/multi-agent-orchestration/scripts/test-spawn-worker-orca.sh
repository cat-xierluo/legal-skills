#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ORCA_HELPER="$SCRIPT_DIR/spawn-worker-orca.sh"
CASE_ROOT=$(mktemp -d)
CASE_ROOT=$(cd "$CASE_ROOT" && pwd -P)
FAKE_LOG="$CASE_ROOT/orca.log"
trap 'rm -rf "$CASE_ROOT"' EXIT

PROJECT_REPO="$CASE_ROOT/business repo"
SKILL_REPO="$CASE_ROOT/skills repo"
NON_GIT_PROJECT="$CASE_ROOT/non-git project"
mkdir -p "$PROJECT_REPO/.claude/skills" "$SKILL_REPO/multi-agent-orchestration" "$NON_GIT_PROJECT"
git -C "$PROJECT_REPO" init -q
git -C "$PROJECT_REPO" config user.email "spawn-orca@test.local"
git -C "$PROJECT_REPO" config user.name "spawn-orca-test"
git -C "$PROJECT_REPO" commit -q --allow-empty -m init
git -C "$SKILL_REPO" init -q
git -C "$SKILL_REPO" config user.email "spawn-orca@test.local"
git -C "$SKILL_REPO" config user.name "spawn-orca-test"
git -C "$SKILL_REPO" commit -q --allow-empty -m init
ln -s "$SKILL_REPO/multi-agent-orchestration" "$PROJECT_REPO/.claude/skills/multi-agent-orchestration"
SYMLINK_SKILL_DIR="$PROJECT_REPO/.claude/skills/multi-agent-orchestration"

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

# shellcheck source=spawn-worker-orca.sh
source "$ORCA_HELPER"

reset_orca_case() {
  PROJECT_DIR="$PROJECT_REPO"
  LIGHTWEIGHT_MODE=0
  NO_ORCA_MODE=0
  ORCA_MODE=""
  ORCA_WORKTREE_ID=""
  ORCA_WORKTREE_PATH=""
  ORCA_PROJECT_TOPLEVEL="$PROJECT_REPO"
  ORCA_EXPECTED_REPO_ID="repo-1"
  ORCA_TERMINAL_HANDLE=""
  ORCA_APP_VERSION=""
  ORCA_CAPABILITIES_JSON=""
  ORCA_SUPERVISED=0
  DRY_RUN=0
  RUNTIME_AVAILABLE=1
  CURRENT_MATCH=1
  FAKE_WAIT_FAIL=0
  ORCA_CURRENT_WORKTREE_PATH="$PROJECT_REPO"
  ORCA_CURRENT_WORKTREE_ID="repo-1::current"
  STATUS_JSON='{"result":{"runtime":{"appVersion":"1.4.9","capabilities":["terminal.multiplex.v1","orchestration.contract.v1"]}}}'
  WORKTREE_CREATE_JSON='{"result":{"worktree":{"id":"repo-1::worker"}}}'
  TERMINAL_CREATE_JSON='{"result":{"terminal":{"handle":"term-worker"}}}'
  WORKTREE_RM_FAIL=0
  WORKTREE_RM_REPO=""
  WORKTREE_RM_PATH=""
  CREATE_WORKTREE_REPO=""
  CREATE_WORKTREE_PATH=""
  CREATE_WORKTREE_BRANCH=""
  unset TERM_PROGRAM
  : > "$FAKE_LOG"
}

orca_runtime_init() {
  [ "$RUNTIME_AVAILABLE" -eq 1 ]
}

orca_runtime_current_project() {
  printf 'current %s\n' "$1" >> "$FAKE_LOG"
  [ "$CURRENT_MATCH" -eq 1 ]
}

orca_cli() {
  printf 'cwd=%s %s\n' "$(pwd -P)" "$*" >> "$FAKE_LOG"
  case "$1 $2" in
    "status --json") printf '%s\n' "$STATUS_JSON" ;;
    "worktree create")
      if [ -n "$CREATE_WORKTREE_REPO" ]; then
        git -C "$CREATE_WORKTREE_REPO" worktree add -q -b "$CREATE_WORKTREE_BRANCH" \
          "$CREATE_WORKTREE_PATH" HEAD
      fi
      printf '%s\n' "$WORKTREE_CREATE_JSON"
      ;;
    "worktree rm")
      [ "$WORKTREE_RM_FAIL" -eq 0 ] || return 1
      if [ -n "$WORKTREE_RM_REPO" ] && [ -n "$WORKTREE_RM_PATH" ]; then
        git -C "$WORKTREE_RM_REPO" worktree remove --force "$WORKTREE_RM_PATH"
      fi
      printf '%s\n' '{"result":{"removed":true}}'
      ;;
    "terminal create") printf '%s\n' "$TERMINAL_CREATE_JSON" ;;
    "terminal wait") [ "$FAKE_WAIT_FAIL" -eq 0 ] ;;
    "terminal send") return 0 ;;
    *) return 1 ;;
  esac
}

reset_orca_case
LIGHTWEIGHT_MODE=1
detect_orca_mode >/dev/null
assert_eq "$ORCA_MODE" "force_tmux" "lightweight mode forces tmux before runtime access"
if [ ! -s "$FAKE_LOG" ]; then ok "lightweight gate makes no Orca call"; else bad "lightweight gate makes no Orca call"; fi

reset_orca_case
NO_ORCA_MODE=1
detect_orca_mode >/dev/null
assert_eq "$ORCA_MODE" "force_tmux" "explicit no-Orca flag forces tmux"
if [ ! -s "$FAKE_LOG" ]; then ok "explicit opt-out makes no Orca call"; else bad "explicit opt-out makes no Orca call"; fi

reset_orca_case
RUNTIME_AVAILABLE=0
detect_orca_mode
assert_eq "$ORCA_MODE" "force_tmux" "ordinary shell without runtime falls back to tmux"

reset_orca_case
RUNTIME_AVAILABLE=0
TERM_PROGRAM=Orca
detect_orca_mode
assert_eq "$ORCA_MODE" "missing_orca" "Orca hint without runtime fails loud"

reset_orca_case
CURRENT_MATCH=0
detect_orca_mode
assert_eq "$ORCA_MODE" "force_tmux" "cross-project runtime does not claim Orca mode"

reset_orca_case
detect_orca_mode >/dev/null
assert_eq "$ORCA_MODE:$ORCA_WORKTREE_ID:$ORCA_WORKTREE_PATH:$ORCA_APP_VERSION" \
  "auto:repo-1::current:$PROJECT_REPO:1.4.9" "matching runtime populates Orca identity"
assert_eq "$ORCA_EXPECTED_REPO_ID:$ORCA_PROJECT_TOPLEVEL" \
  "repo-1:$PROJECT_REPO" "matching runtime freezes expected repo identity and project top"
assert_eq "$ORCA_CAPABILITIES_JSON" '["terminal.multiplex.v1","orchestration.contract.v1"]' \
  "runtime capabilities are preserved as compact JSON"

reset_orca_case
STATUS_JSON='{"result":{"runtime":{"capabilities":["terminal.multiplex.v1"]}}}'
detect_orca_mode
assert_eq "$ORCA_MODE" "missing_orca" "missing app version fails loud"

reset_orca_case
STATUS_JSON='{"result":{"runtime":{"appVersion":"1.4.9","capabilities":[]}}}'
detect_orca_mode
assert_eq "$ORCA_MODE" "missing_orca" "missing terminal capability fails loud"

reset_orca_case
DRY_RUN=1
dry_worktree_output=$(orca_worktree_create worker main)
if printf '%s' "$dry_worktree_output" | grep -Fq 'orca worktree create' \
  && printf '%s' "$dry_worktree_output" | grep -Fq 'orca_worktree_id_placeholder'; then
  ok "worktree dry-run prints plan and placeholder"
else
  bad "worktree dry-run prints plan and placeholder"
fi

reset_orca_case
actual_worktree_id=$(orca_worktree_create worker main)
assert_eq "$actual_worktree_id" "repo-1::worker" "worktree helper returns exact runtime id"

reset_orca_case
WORKTREE_CREATE_JSON='not-json'
invalid_json_rc=0
set +e
orca_worktree_create worker main > "$CASE_ROOT/invalid-json.out" 2> "$CASE_ROOT/invalid-json.err"
invalid_json_rc=$?
set -e
assert_eq "$invalid_json_rc" "64" "malformed create JSON fails closed"
if grep -Fq '返回非法 JSON/合同' "$CASE_ROOT/invalid-json.err" \
  && ! grep -Fq 'worktree rm' "$FAKE_LOG"; then
  ok "malformed create JSON retains unidentifiable resources without guessed cleanup"
else
  bad "malformed create JSON retains unidentifiable resources without guessed cleanup"
fi

reset_orca_case
cd "$SYMLINK_SKILL_DIR"
physical_caller=$(pwd -P)
detect_orca_mode >/dev/null
actual_worktree_id=$(orca_worktree_create worker main)
cd "$SCRIPT_DIR"
assert_eq "$physical_caller" "$SKILL_REPO/multi-agent-orchestration" \
  "symlink fixture starts in the other repository"
if grep -Fq "cwd=$PROJECT_REPO worktree create" "$FAKE_LOG"; then
  ok "worktree create is scoped to the verified PROJECT_DIR top from a symlink skill cwd"
else
  bad "worktree create is scoped to the verified PROJECT_DIR top from a symlink skill cwd"
fi
assert_eq "$actual_worktree_id" "repo-1::worker" "symlink cwd keeps the expected repo id"

reset_orca_case
cd "$PROJECT_REPO"
actual_worktree_id=$(orca_worktree_create worker main)
cd "$SCRIPT_DIR"
if grep -Fq "cwd=$PROJECT_REPO worktree create" "$FAKE_LOG"; then
  ok "same-repository cwd behavior remains unchanged"
else
  bad "same-repository cwd behavior remains unchanged"
fi
assert_eq "$actual_worktree_id" "repo-1::worker" "same-repository create keeps exact id"

# A valid but wrong repoId must fail before terminal/session side effects. The exact
# wrong worktree is removed, but its same-name branch is retained because the helper
# did not observe that repository before create and therefore cannot prove ownership.
WRONG_REPO="$CASE_ROOT/wrong repo"
WRONG_WT="$CASE_ROOT/wrong worker"
mkdir -p "$WRONG_REPO"
git -C "$WRONG_REPO" init -q
git -C "$WRONG_REPO" config user.email "spawn-orca@test.local"
git -C "$WRONG_REPO" config user.name "spawn-orca-test"
git -C "$WRONG_REPO" commit -q --allow-empty -m init
git -C "$WRONG_REPO" worktree add -q -b worker "$WRONG_WT" HEAD
reset_orca_case
WORKTREE_CREATE_JSON=$(jq -cn --arg id "repo-2::$WRONG_WT" --arg path "$WRONG_WT" \
  '{result:{worktree:{id:$id,path:$path}}}')
WORKTREE_RM_REPO="$WRONG_REPO"
WORKTREE_RM_PATH="$WRONG_WT"
mismatch_rc=0
set +e
orca_worktree_create worker main > "$CASE_ROOT/mismatch.out" 2> "$CASE_ROOT/mismatch.err"
mismatch_rc=$?
set -e
assert_eq "$mismatch_rc" "64" "repoId mismatch fails closed"
if [ ! -e "$WRONG_WT" ]; then ok "repoId mismatch removes the exact created worktree"; else bad "repoId mismatch removes the exact created worktree"; fi
if git -C "$WRONG_REPO" show-ref --verify --quiet refs/heads/worker; then
  ok "repoId mismatch retains an unproven same-name branch"
else
  bad "repoId mismatch retains an unproven same-name branch"
fi
if grep -Fq 'expected_repoId=repo-1 actual_repoId=repo-2' "$CASE_ROOT/mismatch.err" \
  && grep -Fq 'rollback=failed_or_partial_resources_retained' "$CASE_ROOT/mismatch.err" \
  && ! grep -Fq 'terminal create' "$FAKE_LOG"; then
  ok "repoId mismatch reports both identities and stops before terminal creation"
else
  bad "repoId mismatch reports both identities and stops before terminal creation"
fi
create_log_line=$(grep -n 'worktree create' "$FAKE_LOG" | head -1 | cut -d: -f1)
remove_log_line=$(grep -n 'worktree rm' "$FAKE_LOG" | head -1 | cut -d: -f1)
if [ -n "$create_log_line" ] && [ -n "$remove_log_line" ] \
  && [ "$create_log_line" -lt "$remove_log_line" ]; then
  ok "repoId mismatch rollback order is create then exact worktree remove"
else
  bad "repoId mismatch rollback order is create then exact worktree remove"
fi

# A malformed id with a path in the expected Git common-dir can be cleaned fully:
# fake create creates the branch after the helper's preexistence snapshot, rollback
# removes the worktree then atomically deletes only that unchanged branch oid.
MALFORMED_WT="$CASE_ROOT/malformed worker"
reset_orca_case
CREATE_WORKTREE_REPO="$PROJECT_REPO"
CREATE_WORKTREE_PATH="$MALFORMED_WT"
CREATE_WORKTREE_BRANCH="worker-malformed"
WORKTREE_RM_REPO="$PROJECT_REPO"
WORKTREE_RM_PATH="$MALFORMED_WT"
WORKTREE_CREATE_JSON=$(jq -cn --arg path "$MALFORMED_WT" \
  '{result:{worktree:{id:"malformed-id",path:$path}}}')
malformed_rc=0
set +e
orca_worktree_create worker-malformed main > "$CASE_ROOT/malformed.out" 2> "$CASE_ROOT/malformed.err"
malformed_rc=$?
set -e
assert_eq "$malformed_rc" "64" "malformed worktree id fails closed"
if [ ! -e "$MALFORMED_WT" ] \
  && ! git -C "$PROJECT_REPO" show-ref --verify --quiet refs/heads/worker-malformed; then
  ok "malformed id rollback removes its exact worktree and provably new branch"
else
  bad "malformed id rollback removes its exact worktree and provably new branch"
fi
if grep -Fq 'actual_repoId=malformed' "$CASE_ROOT/malformed.err"; then
  ok "malformed id error is explicit"
else
  bad "malformed id error is explicit"
fi

# Cleanup failure must retain the worktree/branch and expose rollback status.
FAILED_REPO="$CASE_ROOT/failed cleanup repo"
FAILED_WT="$CASE_ROOT/failed cleanup worker"
mkdir -p "$FAILED_REPO"
git -C "$FAILED_REPO" init -q
git -C "$FAILED_REPO" config user.email "spawn-orca@test.local"
git -C "$FAILED_REPO" config user.name "spawn-orca-test"
git -C "$FAILED_REPO" commit -q --allow-empty -m init
git -C "$FAILED_REPO" worktree add -q -b worker-failed "$FAILED_WT" HEAD
reset_orca_case
WORKTREE_CREATE_JSON=$(jq -cn --arg id "repo-2::$FAILED_WT" --arg path "$FAILED_WT" \
  '{result:{worktree:{id:$id,path:$path}}}')
WORKTREE_RM_FAIL=1
cleanup_fail_rc=0
set +e
orca_worktree_create worker-failed main > "$CASE_ROOT/cleanup-fail.out" 2> "$CASE_ROOT/cleanup-fail.err"
cleanup_fail_rc=$?
set -e
assert_eq "$cleanup_fail_rc" "64" "cleanup failure keeps the spawn failure closed"
if [ -d "$FAILED_WT" ] && git -C "$FAILED_REPO" show-ref --verify --quiet refs/heads/worker-failed; then
  ok "cleanup failure retains worktree and branch for manual recovery"
else
  bad "cleanup failure retains worktree and branch for manual recovery"
fi
if grep -Fq 'rollback=failed_or_partial_resources_retained' "$CASE_ROOT/cleanup-fail.err" \
  && grep -Fq '资源保留' "$CASE_ROOT/cleanup-fail.err"; then
  ok "cleanup failure reports retained resources"
else
  bad "cleanup failure reports retained resources"
fi

reset_orca_case
PROJECT_DIR="$NON_GIT_PROJECT"
LIGHTWEIGHT_MODE=1
cd "$NON_GIT_PROJECT"
lightweight_pwd_before=$(pwd -P)
detect_orca_mode >/dev/null
lightweight_pwd_after=$(pwd -P)
cd "$SCRIPT_DIR"
assert_eq "$ORCA_MODE" "force_tmux" "non-Git lightweight still forces tmux"
assert_eq "$lightweight_pwd_after" "$lightweight_pwd_before" "non-Git lightweight does not change cwd"
if [ ! -s "$FAKE_LOG" ]; then ok "non-Git lightweight makes no Orca call"; else bad "non-Git lightweight makes no Orca call"; fi

reset_orca_case
DRY_RUN=1
orca_terminal_create_and_send 'repo-1::worker' worker 'codex' 'start task' > "$CASE_ROOT/terminal-dry.txt"
assert_eq "$ORCA_TERMINAL_HANDLE" "orca_terminal_handle_placeholder" "terminal dry-run sets placeholder handle"
if grep -Fq 'orca terminal send' "$CASE_ROOT/terminal-dry.txt"; then
  ok "terminal-managed dry-run includes ordinary prompt"
else
  bad "terminal-managed dry-run includes ordinary prompt"
fi

reset_orca_case
DRY_RUN=1
ORCA_SUPERVISED=1
orca_terminal_create_and_send 'repo-1::worker' worker 'codex' 'must not send' > "$CASE_ROOT/terminal-supervised.txt"
if grep -Fq 'worker-start' "$CASE_ROOT/terminal-supervised.txt" \
  && ! grep -Fq 'orca terminal send' "$CASE_ROOT/terminal-supervised.txt"; then
  ok "supervised dry-run keeps worker-start as the only injector"
else
  bad "supervised dry-run keeps worker-start as the only injector"
fi

reset_orca_case
FAKE_WAIT_FAIL=1
orca_terminal_create_and_send 'repo-1::worker' worker 'codex' 'start task'
assert_eq "$ORCA_TERMINAL_HANDLE" "term-worker" "terminal helper records exact handle"
if grep -Fq 'terminal create' "$FAKE_LOG" && grep -Fq 'terminal wait' "$FAKE_LOG" \
  && grep -Fq 'terminal send' "$FAKE_LOG"; then
  ok "tui-idle timeout remains non-blocking before prompt send"
else
  bad "tui-idle timeout remains non-blocking before prompt send"
fi

if grep -Fq 'source "$SCRIPT_DIR/spawn-worker-orca.sh"' "$SCRIPT_DIR/spawn-worker.sh" \
  && ! grep -q '^detect_orca_mode() {' "$SCRIPT_DIR/spawn-worker.sh"; then
  ok "entrypoint delegates Orca helpers without retaining definitions"
else
  bad "entrypoint delegates Orca helpers without retaining definitions"
fi

printf 'spawn-worker Orca helper tests: %s passed, %s failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
