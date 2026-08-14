#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ORCA_HELPER="$SCRIPT_DIR/spawn-worker-orca.sh"
CASE_ROOT=$(mktemp -d)
FAKE_LOG="$CASE_ROOT/orca.log"
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

# shellcheck source=spawn-worker-orca.sh
source "$ORCA_HELPER"

reset_orca_case() {
  PROJECT_DIR="/repo/project"
  LIGHTWEIGHT_MODE=0
  NO_ORCA_MODE=0
  ORCA_MODE=""
  ORCA_WORKTREE_ID=""
  ORCA_WORKTREE_PATH=""
  ORCA_TERMINAL_HANDLE=""
  ORCA_APP_VERSION=""
  ORCA_CAPABILITIES_JSON=""
  ORCA_SUPERVISED=0
  DRY_RUN=0
  RUNTIME_AVAILABLE=1
  CURRENT_MATCH=1
  FAKE_WAIT_FAIL=0
  ORCA_CURRENT_WORKTREE_PATH="/repo/project"
  ORCA_CURRENT_WORKTREE_ID="repo-1::current"
  STATUS_JSON='{"result":{"runtime":{"appVersion":"1.4.9","capabilities":["terminal.multiplex.v1","orchestration.contract.v1"]}}}'
  WORKTREE_CREATE_JSON='{"result":{"worktree":{"id":"repo-1::worker"}}}'
  TERMINAL_CREATE_JSON='{"result":{"terminal":{"handle":"term-worker"}}}'
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
  printf '%s\n' "$*" >> "$FAKE_LOG"
  case "$1 $2" in
    "status --json") printf '%s\n' "$STATUS_JSON" ;;
    "worktree create") printf '%s\n' "$WORKTREE_CREATE_JSON" ;;
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
  "auto:repo-1::current:/repo/project:1.4.9" "matching runtime populates Orca identity"
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
