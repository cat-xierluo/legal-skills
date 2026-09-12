#!/usr/bin/env bash
# Isolated fake-CLI contract tests; no real Orca/provider processes are started.
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT
export ORCA_CLI_COMMAND="$TMP_ROOT/orca"
unset ORCA_TERMINAL_HANDLE ORCA_CLI_BIN
export IDENTITY_LOG="$TMP_ROOT/calls" IDENTITY_STATE="$TMP_ROOT/count"
export IDENTITY_MODE=match
cat > "$ORCA_CLI_COMMAND" <<'FAKE'
#!/usr/bin/env bash
set -eu
printf '%s\n' "$*" >> "$IDENTITY_LOG"
reject_argv() { echo "FAKE_ORCA_UNSUPPORTED_ARGV: $*" >&2; exit 64; }
validate_flags() {
  local allowed="$1"; shift
  local flag from="" run=""
  while [ "$#" -gt 0 ]; do
    flag="$1"; shift
    case " $allowed " in *" $flag "*) ;; *) reject_argv "$flag" ;; esac
    case "$flag" in --json) ;; *)
      [ "$#" -gt 0 ] || reject_argv "$flag needs a value"
      case "$flag" in --from) from="$1" ;; --run) run="$1" ;; esac
      shift ;;
    esac
  done
  case " $allowed " in *" --from "*) [ "$from" = term-pm ] || reject_argv "wrong --from" ;; esac
  case " $allowed " in *" --run "*) [ "$run" = run-a ] || reject_argv "wrong --run" ;; esac
}
case "$1 $2" in
  'status --json') [ "$#" -eq 2 ] || reject_argv "$*" ;;
  'terminal show') [ "$*" = 'terminal show --terminal term-pm --json' ] || reject_argv "$*" ;;
  'orchestration run-current') [ "$*" = 'orchestration run-current --from term-pm --json' ] || reject_argv "$*" ;;
  'orchestration run-create') validate_flags '--objective --from --json' "${@:3}" ;;
  'orchestration task-create') validate_flags '--spec --task-title --run --from --json' "${@:3}" ;;
  'orchestration worker-start') validate_flags '--task --terminal --worktree --run --from --timeout-ms --json' "${@:3}" ;;
  'orchestration dispatch-show') [ "$*" = 'orchestration dispatch-show --task task-a --json' ] || reject_argv "$*" ;;
  'worktree show') [ "$*" = 'worktree show --worktree id:repo::worker --json' ] || reject_argv "$*" ;;
  *) reject_argv "$*" ;;
esac
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
         if [ "$IDENTITY_MODE" = stale ] || { [ "$IDENTITY_MODE" = drift ] && [ "$n" -gt 1 ]; } ||
            { [ "$IDENTITY_MODE" = wave-drift ] && [ -f "$IDENTITY_STATE.task-created" ]; }; then id=runtime-b; fi
         printf '{"ok":true,"result":{"runtime":{"reachable":true,"runtimeId":"%s"}}}\n' "$id" ;;
    esac ;;
  'terminal show') echo '{"ok":true,"_meta":{"runtimeId":"runtime-a"},"result":{"terminal":{"handle":"term-pm","connected":true,"writable":true,"orphaned":false,"exitCause":null}}}' ;;
  'orchestration run-create'|'orchestration run-current') echo '{"ok":true,"_meta":{"runtimeId":"runtime-a"},"result":{"run":{"id":"run-a","coordinator_handle":"term-pm"}}}' ;;
  'orchestration task-create') touch "$IDENTITY_STATE.task-created"; echo '{"ok":true,"result":{"task":{"id":"task-a"}}}' ;;
  'orchestration worker-start') echo '{"ok":true,"result":{"dispatch":{"id":"dispatch-a"}}}' ;;
  'orchestration dispatch-show') echo '{"ok":true,"result":{"dispatch":{"id":"dispatch-a"}}}' ;;
  'worktree show') echo '{"ok":false,"error":{"code":"selector_not_found"}}'; exit 1 ;;
  *) reject_argv "$*" ;;
esac
FAKE
chmod +x "$ORCA_CLI_COMMAND"
printf '%s\n' '{"objective":"identity test","tasks":[{"key":"a","spec":"test scope"}]}' > "$TMP_ROOT/manifest.json"
pass=0
check() { if "$@"; then pass=$((pass+1)); else echo "FAIL: $*" >&2; exit 1; fi; }
reset_probe() { : > "$IDENTITY_LOG"; printf 0 > "$IDENTITY_STATE"; rm -f "$IDENTITY_STATE.task-created"; }
expect_rc() {
  local expected="$1" actual=0; shift
  "$@" > "$TMP_ROOT/out" 2> "$TMP_ROOT/err" || actual=$?
  check test "$actual" -eq "$expected"
}
for IDENTITY_MODE in invalid missing unreachable none typed cli-fail; do
  export IDENTITY_MODE
  reset_probe
  expect_rc 3 bash "$SCRIPT_DIR/orca-wave-prepare.sh" --from term-pm --manifest "$TMP_ROOT/manifest.json"
  check test "$(wc -l < "$IDENTITY_LOG" | tr -d ' ')" -eq 1
  check grep -q '^ORCA_COORDINATOR_UNVERIFIED: current runtime identity is unavailable' "$TMP_ROOT/err"
done
export IDENTITY_MODE=match
reset_probe
expect_rc 0 bash "$SCRIPT_DIR/orca-wave-prepare.sh" --from term-pm --manifest "$TMP_ROOT/manifest.json" --receipt "$TMP_ROOT/receipt.json"
check jq -e '._meta.runtimeId == "runtime-a"' "$TMP_ROOT/receipt.json"
check grep -qx 'orchestration run-current --from term-pm --json' "$IDENTITY_LOG"
expect_rc 64 bash "$SCRIPT_DIR/orca-wave-prepare.sh" --from term-pm --manifest "$TMP_ROOT/manifest.json" --receipt "$TMP_ROOT/receipt.json"
export IDENTITY_MODE=wave-drift
reset_probe
expect_rc 3 bash "$SCRIPT_DIR/orca-wave-prepare.sh" --from term-pm --manifest "$TMP_ROOT/manifest.json" --receipt "$TMP_ROOT/drift.json"
check test ! -e "$TMP_ROOT/drift.json"
check grep -q ORCA_COORDINATOR_STALE "$TMP_ROOT/err"
check grep -q '^orchestration task-create ' "$IDENTITY_LOG"
check grep -q '^ORCA_WAVE_PARTIAL:' "$TMP_ROOT/err"

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
expect_rc 64 "$ORCA_CLI_COMMAND" orchestration run-current --from term-pm --unknown --json
check grep -q '^FAKE_ORCA_UNSUPPORTED_ARGV:' "$TMP_ROOT/err"
printf 'SUMMARY: pass=%s fail=0\n' "$pass"
