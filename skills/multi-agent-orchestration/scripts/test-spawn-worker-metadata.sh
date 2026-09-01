#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
METADATA_HELPER="$SCRIPT_DIR/spawn-worker-metadata.sh"
CASE_ROOT=$(mktemp -d)
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

assert_jq() {
  local file="$1" expression="$2" label="$3"
  if jq -e "$expression" "$file" >/dev/null; then
    ok "$label"
  else
    bad "$label"
  fi
}

array_to_json() {
  if [ "$#" -eq 0 ]; then
    printf '[]\n'
  else
    printf '%s\n' "$@" | jq -R . | jq -s .
  fi
}

# shellcheck source=spawn-worker-metadata.sh
source "$METADATA_HELPER"

reset_metadata_case() {
  DRY_RUN=0
  PROJECT_DIR="/repo/project"
  WORKTREE="/repo/project/.claude/worktrees/worker"
  BRANCH="feat/worker"
  BASE_REF="origin/main"
  BASE_SHA="base-sha"
  SESSION="worker-session"
  SESSION_CONTEXT="$WORKTREE/.claude/agent-sessions/$SESSION"
  COMMAND="codex"
  WORKER_BACKEND="codex"
  PM_HARNESS="codex"
  PM_HARNESS_SOURCE="verified_runtime"
  PM_HARNESS_CHAIN_JSON='[{"backend":"codex","source":"process"}]'
  PM_ALLOWED_WORKER_BACKENDS="claude-code codex"
  WORKER_BACKEND_CANONICAL="codex"
  WORKER_COMMAND_SHA256="command-sha"
  RUNTIME_PROFILE="strict"
  API_PROVIDER="provider-a"
  MODEL="model-a"
  PROVIDER_SLOT="slot-a"
  PROVIDER_LEASE_FILE="/repo/common/lease.json"
  PROVIDER_LEASE_ROOT="/repo/common/leases"
  PROVIDER_LEASE_LIMIT="2"
  PROVIDER_LEASE_KEY="provider-a"
  QUOTA_PREFLIGHT_STATUS="ok"
  QUOTA_PREFLIGHT_LANE="primary"
  QUOTA_PREFLIGHT_OVERRIDE=0
  QUOTA_PREFLIGHT_OVERRIDE_SOURCE=""
  ENV_ISOLATION="isolated"
  WAVE_ID="wave-a"
  WAVE_WORKER_ID="worker-a"
  LIGHTWEIGHT_MODE=0
  LIGHTWEIGHT_AUTO=0
  VERIFY_COMMANDS=("bash test-a.sh" "bash test-b.sh")
  ADD_DIRS=("/tmp/a" "/tmp/b path")
  ALLOW_PATHS=("skills/a/**" "skills/b/**")
  INSTALL_GUARD_MODE="hook"
  INSTALL_AUTH_FILE="$SESSION_CONTEXT/INSTALL_AUTHORIZATION.json"
  INSTALL_AUTHORIZATION_SOURCE="user approval"
  INSTALL_GUARD_DEGRADATION_SOURCE=""
  GIT_EXPECTED_NAME="Expected User"
  GIT_EXPECTED_EMAIL="expected@example.com"
  GIT_INTEGRATION_BASE="origin/main"
  SAFE_PUSH_COMMAND="bash safe-push.sh"
  AUTHORITY_RECEIPT_FILE="/repo/common/authority.json"
  AUTHORITY_RECEIPT_SHA256="authority-sha"
  GUARD_ATTESTATION_FILE="/repo/common/attestation.json"
  AUTHORIZED_INSTALL_COMMANDS=("pip install demo")
  EFFECTIVE_ALLOWED_SHELL_COMMANDS=("git status" "git status" "bash test-a.sh")
  ORCA_MODE="auto"
  ORCA_WORKTREE_ID="repo-1::worker"
  ORCA_WORKTREE_PATH="$WORKTREE"
  ORCA_TERMINAL_HANDLE="term-worker"
  ORCA_TUI_READY_METHOD="orca_terminal_wait_tui-idle"
  ORCA_APP_VERSION="1.4.9"
  ORCA_CAPABILITIES_JSON='["terminal.multiplex.v1","orchestration.contract.v1"]'
}

reset_metadata_case
METADATA_FILE="$CASE_ROOT/worktree.json"
write_metadata > "$CASE_ROOT/worktree.out"
assert_jq "$METADATA_FILE" '.schema == "multi-agent-orchestration.worktree-metadata.v1" and .project == "/repo/project"' \
  "schema and project identity are preserved"
assert_jq "$METADATA_FILE" '.isolation == {mode:"worktree", lightweight_auto:0}' \
  "worktree isolation is explicit"
assert_jq "$METADATA_FILE" '.runtime.harness_authority.pm_harness == "codex" and .runtime.harness_authority.allowed_worker_backends == ["claude-code","codex"]' \
  "Harness authority remains structured"
assert_jq "$METADATA_FILE" '.runtime.provider_lease.max_concurrency == 2 and .runtime.provider_lease.provider == "provider-a"' \
  "provider lease limit remains numeric"
assert_jq "$METADATA_FILE" '.runtime.quota_preflight == {status:"ok",lane:"primary",override_used:0,override_authorization_source:""}' \
  "quota preflight evidence is initialized and structurally asserted"
assert_jq "$METADATA_FILE" '.verification.commands == ["bash test-a.sh","bash test-b.sh"] and .add_dirs[1] == "/tmp/b path" and .allow_paths[0] == "skills/a/**"' \
  "repeatable arrays preserve order and spaces"
assert_jq "$METADATA_FILE" '.execution_authority.allowed_shell_commands | length == 2' \
  "allowed Shell commands remain unique"
assert_jq "$METADATA_FILE" '.execution_authority.enforcement_source == "pretool_hook_settings_wired_process_snapshot_runtime_unproven" and .execution_authority.worker_mirror_authoritative == false' \
  "hook mode does not overclaim runtime attestation"
assert_jq "$METADATA_FILE" '.execution_authority.git_identity.raw_git_push_allowed == false and .execution_authority.git_identity.commit_environment_bound == true' \
  "Git identity metadata remains fail-closed"
assert_jq "$METADATA_FILE" '.session.orca.terminal_handle == "term-worker" and .session.orca.capabilities[1] == "orchestration.contract.v1"' \
  "Orca session identity remains structured"
assert_jq "$METADATA_FILE" '.pr == {number:null,url:"",state:""}' \
  "PR placeholder contract is preserved"

reset_metadata_case
METADATA_FILE="$CASE_ROOT/lightweight.json"
SESSION_CONTEXT="/repo/project/.claude/agent-sessions/lightweight"
LIGHTWEIGHT_MODE=1
LIGHTWEIGHT_AUTO=1
INSTALL_GUARD_MODE="prompt_only_degraded"
PROVIDER_LEASE_LIMIT=""
GIT_EXPECTED_NAME=""
GIT_EXPECTED_EMAIL=""
VERIFY_COMMANDS=()
ADD_DIRS=()
ALLOW_PATHS=()
AUTHORIZED_INSTALL_COMMANDS=()
EFFECTIVE_ALLOWED_SHELL_COMMANDS=()
ORCA_MODE="force_tmux"
ORCA_WORKTREE_ID=""
ORCA_WORKTREE_PATH=""
ORCA_TERMINAL_HANDLE=""
ORCA_APP_VERSION=""
ORCA_CAPABILITIES_JSON='[]'
write_metadata > "$CASE_ROOT/lightweight.out"
assert_jq "$METADATA_FILE" '.isolation == {mode:"lightweight", lightweight_auto:1}' \
  "lightweight isolation and auto-detection are recorded"
assert_jq "$METADATA_FILE" '.runtime.provider_lease.max_concurrency == null' \
  "unconfigured provider limit remains null"
assert_jq "$METADATA_FILE" '.execution_authority.enforcement_source == "prompt_only_no_mechanical_enforcement" and .execution_authority.git_identity.commit_environment_bound == false' \
  "degraded guard and unbound Git identity remain explicit"
assert_jq "$METADATA_FILE" '.verification.commands == [] and .session.orca.mode == "force_tmux"' \
  "empty verification and tmux fallback remain valid"

reset_metadata_case
METADATA_FILE="$CASE_ROOT/dry-run.json"
DRY_RUN=1
write_metadata > "$CASE_ROOT/dry-run.out"
if [ ! -e "$METADATA_FILE" ] && grep -Fq "SPAWN_WORKER_METADATA: $METADATA_FILE" "$CASE_ROOT/dry-run.out"; then
  ok "dry-run reports target without writing metadata"
else
  bad "dry-run reports target without writing metadata"
fi

if grep -Fq 'source "$SCRIPT_DIR/spawn-worker-metadata.sh"' "$SCRIPT_DIR/spawn-worker.sh" \
  && ! grep -q '^write_metadata() {' "$SCRIPT_DIR/spawn-worker.sh"; then
  ok "entrypoint delegates metadata writing without retaining definition"
else
  bad "entrypoint delegates metadata writing without retaining definition"
fi

printf 'spawn-worker metadata tests: %s passed, %s failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
