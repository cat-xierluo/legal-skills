#!/usr/bin/env bash
# Isolated fake-CLI contract tests; no real Orca/provider processes are started.
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT
export ORCA_CLI_COMMAND="$TMP_ROOT/orca"
export IDENTITY_LOG="$TMP_ROOT/calls" IDENTITY_STATE="$TMP_ROOT/count"
export IDENTITY_MODE=match
cat > "$ORCA_CLI_COMMAND" <<'FAKE'
#!/usr/bin/env bash
set -eu
printf '%s\n' "$*" >> "$IDENTITY_LOG"
case "$1 $2" in
  'status --json')
    n=0; [ ! -f "$IDENTITY_STATE" ] || n=$(cat "$IDENTITY_STATE")
    n=$((n+1)); printf '%s' "$n" > "$IDENTITY_STATE"
    case "$IDENTITY_MODE" in
      invalid) echo invalid ;;
      missing) echo '{"ok":true,"result":{"runtime":{"reachable":true}}}' ;;
      unreachable) echo '{"ok":true,"result":{"runtime":{"reachable":false,"runtimeId":"runtime-a"}}}' ;;
      none) echo '{"ok":true,"result":{"runtime":{"reachable":true,"runtimeId":"none"}}}' ;;
      typed) echo '{"ok":true,"result":{"runtime":{"reachable":true,"runtimeId":42}}}' ;;
      cli-fail) exit 1 ;;
      *) id=runtime-a
         if [ "$IDENTITY_MODE" = stale ] || { [ "$IDENTITY_MODE" = drift ] && [ "$n" -gt 1 ]; }; then id=runtime-b; fi
         printf '{"ok":true,"result":{"runtime":{"reachable":true,"runtimeId":"%s"}}}\n' "$id" ;;
    esac ;;
  'orchestration run-create') echo '{"ok":true,"result":{"run":{"id":"run-a","coordinator_handle":"term-pm"}}}' ;;
  'orchestration task-create') echo '{"ok":true,"result":{"task":{"id":"task-a"}}}' ;;
  'orchestration worker-start') echo '{"ok":true,"result":{"dispatch":{"id":"dispatch-a"}}}' ;;
  *) echo '{"ok":true,"result":{}}' ;;
esac
FAKE
chmod +x "$ORCA_CLI_COMMAND"
printf '%s\n' '{"objective":"identity test","tasks":[{"key":"a","spec":"test scope"}]}' > "$TMP_ROOT/manifest.json"
pass=0
check() { if "$@"; then pass=$((pass+1)); else echo "FAIL: $*" >&2; exit 1; fi; }
reset_probe() { : > "$IDENTITY_LOG"; printf 0 > "$IDENTITY_STATE"; }
expect_rc() {
  local expected="$1" actual=0; shift
  "$@" > "$TMP_ROOT/out" 2> "$TMP_ROOT/err" || actual=$?
  check test "$actual" -eq "$expected"
}
for IDENTITY_MODE in invalid missing unreachable none typed cli-fail; do
  export IDENTITY_MODE
  reset_probe
  expect_rc 3 bash "$SCRIPT_DIR/orca-wave-prepare.sh" --manifest "$TMP_ROOT/manifest.json"
  check test "$(wc -l < "$IDENTITY_LOG" | tr -d ' ')" -eq 1
done
export IDENTITY_MODE=match
reset_probe
expect_rc 0 bash "$SCRIPT_DIR/orca-wave-prepare.sh" --manifest "$TMP_ROOT/manifest.json" --receipt "$TMP_ROOT/receipt.json"
check jq -e '._meta.runtimeId == "runtime-a"' "$TMP_ROOT/receipt.json"
expect_rc 64 bash "$SCRIPT_DIR/orca-wave-prepare.sh" --manifest "$TMP_ROOT/manifest.json" --receipt "$TMP_ROOT/receipt.json"
export IDENTITY_MODE=drift
reset_probe
expect_rc 3 bash "$SCRIPT_DIR/orca-wave-prepare.sh" --manifest "$TMP_ROOT/manifest.json" --receipt "$TMP_ROOT/drift.json"
check test ! -e "$TMP_ROOT/drift.json"
check grep -q SPAWN_COORDINATOR_STALE "$TMP_ROOT/err"

register=(bash "$SCRIPT_DIR/orca-supervised-register.sh" --worktree-id repo::worker --terminal-handle term-worker --run-id run-a --coordinator-handle term-pm --task-id task-a)
export IDENTITY_MODE=stale
reset_probe
expect_rc 3 "${register[@]}" --runtime-id runtime-a
check test "$(wc -l < "$IDENTITY_LOG" | tr -d ' ')" -eq 1
export IDENTITY_MODE=match
reset_probe
expect_rc 0 "${register[@]}" --runtime-id runtime-a
check grep -q '^orchestration worker-start ' "$IDENTITY_LOG"
reset_probe
expect_rc 0 "${register[@]}"
check grep -q SPAWN_COORDINATOR_RUNTIME_UNVERIFIED "$TMP_ROOT/err"
export IDENTITY_MODE=drift
reset_probe
expect_rc 1 "${register[@]}" --runtime-id runtime-a
check grep -q SPAWN_COORDINATOR_STALE "$TMP_ROOT/err"
check test "$(wc -l < "$IDENTITY_LOG" | tr -d ' ')" -eq 2

# Exercise the production launch function at the last pre-terminal boundary.
export IDENTITY_MODE=stale
reset_probe
expect_rc 3 bash -c '
  set -eu
  source "$1/orca-runtime.sh"
  source "$1/spawn-worker-launch.sh"
  COMMAND=claude ORCA_MODE=auto ORCA_EXPECTED_RUNTIME_ID=runtime-a
  orca_terminal_create_and_send() { echo TERMINAL_MUTATION; exit 99; }
  launch_worker_session
' _ "$SCRIPT_DIR"
check test "$(wc -l < "$IDENTITY_LOG" | tr -d ' ')" -eq 1
check grep -q SPAWN_COORDINATOR_STALE "$TMP_ROOT/err"
printf 'SUMMARY: pass=%s fail=0\n' "$pass"
