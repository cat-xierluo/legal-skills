#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LEASE_HELPER="$SCRIPT_DIR/spawn-worker-provider-lease.sh"
CASE_ROOT=$(mktemp -d)
FAKE_LOG="$CASE_ROOT/provider.log"
CONFIG_FILE="$CASE_ROOT/orchestration-personal.json"
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

# shellcheck source=spawn-worker-provider-lease.sh
source "$LEASE_HELPER"

reset_lease_case() {
  PERSONAL_CONFIG_FILE="$CASE_ROOT/missing.json"
  WORKER_BACKEND_CANONICAL="codex"
  API_PROVIDER="provider-a"
  PROVIDER_LEASE_FILE=""
  PROVIDER_LEASE_ROOT=""
  PROVIDER_LEASE_LIMIT=""
  PROVIDER_LEASE_KEY=""
  PROVIDER_LEASE_ACQUIRED=0
  PROJECT_DIR="/repo/project"
  SESSION="worker-session"
  DRY_RUN=0
  ORCA_MODE="force_tmux"
  ORCA_TERMINAL_HANDLE=""
  ORCA_CLI_BIN="/opt/orca"
  FAKE_ACQUIRE_MODE="success"
  FAKE_FINALIZE_FAIL=0
  : > "$FAKE_LOG"
}

provider_lease_root_for_project() {
  printf '/repo/common/provider-leases\n'
}

orca_runtime_init() {
  return 0
}

python3() {
  printf '%s\n' "$*" >> "$FAKE_LOG"
  case "${2:-}" in
    acquire)
      case "$FAKE_ACQUIRE_MODE" in
        success) printf '{"lease_file":"/repo/common/provider-leases/lease.json"}\n' ;;
        missing) printf '{}\n' ;;
        deny) return 1 ;;
      esac
      ;;
    finalize)
      [ "$FAKE_FINALIZE_FAIL" -eq 0 ]
      ;;
    release)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

reset_lease_case
advisory_output=$(acquire_provider_lease)
if printf '%s' "$advisory_output" | grep -Fq 'limit=advisory_unconfigured'; then
  ok "missing personal config remains advisory"
else
  bad "missing personal config remains advisory"
fi
assert_eq "$PROVIDER_LEASE_ACQUIRED" "0" "advisory path acquires no lease"
if [ ! -s "$FAKE_LOG" ]; then ok "advisory path makes no mutation"; else bad "advisory path makes no mutation"; fi

printf '%s\n' '{"concurrency":{"max_per_provider":3,"per_backend":{"codex":2}}}' > "$CONFIG_FILE"
reset_lease_case
PERSONAL_CONFIG_FILE="$CONFIG_FILE"
resolve_provider_lease_limit
assert_eq "$PROVIDER_LEASE_LIMIT:$PROVIDER_LEASE_KEY" "2:provider-a" \
  "backend-specific limit overrides provider default"

reset_lease_case
PERSONAL_CONFIG_FILE="$CONFIG_FILE"
DRY_RUN=1
dry_output=$(acquire_provider_lease)
if printf '%s' "$dry_output" | grep -Fq 'state=dry-run-no-acquire'; then
  ok "dry-run reports configured lease without acquiring"
else
  bad "dry-run reports configured lease without acquiring"
fi
if [ ! -s "$FAKE_LOG" ]; then ok "dry-run makes no lease mutation"; else bad "dry-run makes no lease mutation"; fi

reset_lease_case
PERSONAL_CONFIG_FILE="$CONFIG_FILE"
acquire_provider_lease > "$CASE_ROOT/acquire.out"
assert_eq "$PROVIDER_LEASE_ACQUIRED:$PROVIDER_LEASE_FILE:$PROVIDER_LEASE_ROOT" \
  "1:/repo/common/provider-leases/lease.json:/repo/common/provider-leases" \
  "successful acquire records provisional lease identity"
if grep -Fq 'acquire --root /repo/common/provider-leases' "$FAKE_LOG" \
  && grep -Fq -- '--orca-cli /opt/orca' "$FAKE_LOG"; then
  ok "acquire binds trusted root and current Orca CLI"
else
  bad "acquire binds trusted root and current Orca CLI"
fi

set +e
( reset_lease_case; PERSONAL_CONFIG_FILE="$CONFIG_FILE"; FAKE_ACQUIRE_MODE=deny; acquire_provider_lease ) >/dev/null 2>&1
deny_rc=$?
( reset_lease_case; PERSONAL_CONFIG_FILE="$CONFIG_FILE"; FAKE_ACQUIRE_MODE=missing; acquire_provider_lease ) >/dev/null 2>&1
missing_rc=$?
set -e
assert_eq "$deny_rc" "75" "provider denial keeps temporary-failure exit code"
assert_eq "$missing_rc" "64" "malformed acquire response fails closed"

reset_lease_case
PROVIDER_LEASE_ACQUIRED=1
PROVIDER_LEASE_FILE="/repo/common/provider-leases/lease.json"
PROVIDER_LEASE_ROOT="/repo/common/provider-leases"
PROVIDER_LEASE_KEY="provider-a"
ORCA_MODE="auto"
ORCA_TERMINAL_HANDLE="term-worker"
finalize_provider_lease > "$CASE_ROOT/finalize-orca.out"
assert_eq "$PROVIDER_LEASE_ACQUIRED" "0" "successful finalize disables provisional cleanup"
if grep -Fq -- '--transport orca_terminal --resource-handle term-worker' "$FAKE_LOG"; then
  ok "Orca finalize binds the exact terminal handle"
else
  bad "Orca finalize binds the exact terminal handle"
fi

reset_lease_case
PROVIDER_LEASE_ACQUIRED=1
PROVIDER_LEASE_FILE="/repo/common/provider-leases/lease.json"
PROVIDER_LEASE_ROOT="/repo/common/provider-leases"
PROVIDER_LEASE_KEY="provider-a"
finalize_provider_lease > "$CASE_ROOT/finalize-tmux.out"
if grep -Fq -- '--transport tmux --resource-handle worker-session' "$FAKE_LOG"; then
  ok "tmux finalize binds the exact session"
else
  bad "tmux finalize binds the exact session"
fi

set +e
( reset_lease_case; PROVIDER_LEASE_ACQUIRED=1; PROVIDER_LEASE_FILE="/repo/common/provider-leases/lease.json"; PROVIDER_LEASE_ROOT="/repo/common/provider-leases"; FAKE_FINALIZE_FAIL=1; finalize_provider_lease ) >/dev/null 2>&1
finalize_rc=$?
set -e
assert_eq "$finalize_rc" "75" "finalize failure keeps temporary-failure exit code"

reset_lease_case
set +e
( PROVIDER_LEASE_ACQUIRED=1; PROVIDER_LEASE_FILE="/repo/common/provider-leases/lease.json"; PROVIDER_LEASE_ROOT="/repo/common/provider-leases"; false; release_provisional_provider_lease )
release_rc=$?
set -e
assert_eq "$release_rc" "1" "provisional cleanup preserves original exit code"
if grep -Fq 'release --root /repo/common/provider-leases' "$FAKE_LOG"; then
  ok "provisional cleanup releases only the recorded lease"
else
  bad "provisional cleanup releases only the recorded lease"
fi

if grep -Fq 'source "$SCRIPT_DIR/spawn-worker-provider-lease.sh"' "$SCRIPT_DIR/spawn-worker.sh" \
  && ! grep -q '^acquire_provider_lease() {' "$SCRIPT_DIR/spawn-worker.sh"; then
  ok "entrypoint delegates provider lease lifecycle"
else
  bad "entrypoint delegates provider lease lifecycle"
fi

printf 'spawn-worker provider lease tests: %s passed, %s failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
