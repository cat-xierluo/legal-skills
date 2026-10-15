#!/usr/bin/env bash
# shellcheck disable=SC2015  # Test assertions intentionally use concise pass/fail chains.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TARGET="$SCRIPT_DIR/night-watch.sh"
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT

pass=0
fail=0
ok() { printf '  ✓ %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  ✗ %s\n' "$1" >&2; fail=$((fail + 1)); }

FAKE_ORCA="$TMP_ROOT/fake-orca"
FAKE_CLAUDE="$TMP_ROOT/fake-claude"
export FAKE_ORCA_LOG="$TMP_ROOT/orca.log"
export FAKE_CLAUDE_LOG="$TMP_ROOT/claude.log"
export FAKE_CLAUDE_STATE="$TMP_ROOT/claude-state"
export FAKE_CLAUDE_SEQUENCE="$TMP_ROOT/claude-sequence"

cat > "$FAKE_ORCA" <<'FAKE'
#!/usr/bin/env bash
set -euo pipefail
{
  for arg in "$@"; do printf '%q ' "$arg"; done
  printf '\n'
} >> "$FAKE_ORCA_LOG"
case "$1 $2" in
  "terminal show")
    [ "${FAKE_ORCA_SHOW_MODE:-ok}" = ok ] || exit 1
    handle=""
    while [ "$#" -gt 0 ]; do
      if [ "$1" = --terminal ]; then handle=$2; break; fi
      shift
    done
    printf '{"ok":true,"result":{"terminal":{"handle":"%s","connected":true,"writable":true}}}\n' "$handle"
    ;;
  "terminal send")
    [ "${FAKE_ORCA_SEND_MODE:-ok}" = ok ] || exit 1
    echo '{"ok":true}'
    ;;
  *) echo '{"ok":true}' ;;
esac
FAKE

cat > "$FAKE_CLAUDE" <<'FAKE'
#!/usr/bin/env bash
set -euo pipefail
count=0
[ -r "$FAKE_CLAUDE_STATE" ] && count=$(sed -n '1p' "$FAKE_CLAUDE_STATE")
count=$((count + 1))
printf '%s\n' "$count" > "$FAKE_CLAUDE_STATE"
mode=$(sed -n "${count}p" "$FAKE_CLAUDE_SEQUENCE")
[ -n "$mode" ] || mode=$(tail -n 1 "$FAKE_CLAUDE_SEQUENCE")
printf '%s\n' "$mode" >> "$FAKE_CLAUDE_LOG"
if [ -n "${FAKE_MUTATE_SETTINGS:-}" ] && [ "$count" -eq 1 ]; then
  printf '%s\n' '{"changed":true}' > "$FAKE_MUTATE_SETTINGS"
fi
case "$mode" in
  available) echo ok ;;
  quota) echo 'HTTP 429: quota exceeded; limit resets later' >&2; exit 1 ;;
  config) echo 'HTTP 400: invalid model' >&2; exit 1 ;;
  auth) echo 'HTTP 401: unauthorized' >&2; exit 1 ;;
  network) echo 'network connection refused' >&2; exit 1 ;;
  unknown) echo 'opaque error' >&2; exit 1 ;;
  *) echo "bad sequence mode: $mode" >&2; exit 2 ;;
esac
FAKE
chmod +x "$FAKE_ORCA" "$FAKE_CLAUDE"
export ORCA_CLI_COMMAND="$FAKE_ORCA"
export CLAUDE_CLI_COMMAND="$FAKE_CLAUDE"
DEFAULT_SETTINGS="$TMP_ROOT/default.settings.json"
printf '%s\n' '{}' > "$DEFAULT_SETTINGS"

OUTPUT=""
STATUS=0
STATE_DIR=""
prepare_case() {
  local name=$1 sequence=$2
  STATE_DIR="$TMP_ROOT/state-$name"
  : > "$FAKE_ORCA_LOG"
  : > "$FAKE_CLAUDE_LOG"
  : > "$FAKE_CLAUDE_STATE"
  # Test sequences contain simple whitespace-delimited state names.
  # shellcheck disable=SC2086
  printf '%s\n' $sequence > "$FAKE_CLAUDE_SEQUENCE"
  export FAKE_ORCA_SHOW_MODE=ok FAKE_ORCA_SEND_MODE=ok
}

run_watch() {
  set +e
  OUTPUT=$(bash "$TARGET" --terminal term-test --model model-test \
    --interval-seconds 1 --max-seconds 4 --probe-timeout-seconds 1 \
    --state-dir "$STATE_DIR" --settings "$DEFAULT_SETTINGS" "$@" 2>&1)
  STATUS=$?
  set -e
}

echo "Case 1: explicit quota -> available is the only wake path"
prepare_case recover 'quota available'
run_watch
[ "$STATUS" -eq 0 ] && ok "quota recovery watcher succeeds" || bad "quota recovery exit was $STATUS ($OUTPUT)"
[ "$(grep -c '^terminal send ' "$FAKE_ORCA_LOG")" -eq 1 ] && ok "recovery injects exactly one wake" || bad "recovery wake count was not one"
[ "$(wc -l < "$FAKE_CLAUDE_LOG" | tr -d ' ')" -eq 2 ] && ok "recovery used the expected two probes" || bad "recovery probe count was wrong"

echo "Case 2: initial availability fails closed without continued consumption"
prepare_case initially-available 'available available'
run_watch
[ "$STATUS" -eq 11 ] && ok "initial availability is rejected" || bad "initial availability exit was $STATUS ($OUTPUT)"
[ "$(wc -l < "$FAKE_CLAUDE_LOG" | tr -d ' ')" -eq 1 ] && ok "initial availability performs only one probe" || bad "initial availability kept probing"
if ! grep -q '^terminal send ' "$FAKE_ORCA_LOG"; then ok "initial availability sends nothing"; else bad "initial availability sent terminal input"; fi

echo "Case 3: non-quota failures stop immediately"
for spec in 'config:12' 'auth:13' 'network:14' 'unknown:16'; do
  IFS=: read -r mode expected <<< "$spec"
  prepare_case "$mode" "$mode"
  run_watch
  [ "$STATUS" -eq "$expected" ] && ok "$mode propagates exit $expected" || bad "$mode exit was $STATUS ($OUTPUT)"
  if ! grep -q '^terminal send ' "$FAKE_ORCA_LOG"; then ok "$mode sends nothing"; else bad "$mode sent terminal input"; fi
done

echo "Case 4: bounded wait stops at deadline without a false wake"
prepare_case deadline 'quota quota quota'
run_watch --max-seconds 1
[ "$STATUS" -eq 2 ] && ok "quota wait reaches bounded timeout" || bad "deadline exit was $STATUS ($OUTPUT)"
if ! grep -q '^terminal send ' "$FAKE_ORCA_LOG"; then ok "deadline sends no false recovery wake"; else bad "deadline sent terminal input"; fi

prepare_case settings-drift 'quota available'
settings="$TMP_ROOT/night.settings.json"
printf '%s\n' '{}' > "$settings"
export FAKE_MUTATE_SETTINGS="$settings"
run_watch --settings "$settings"
unset FAKE_MUTATE_SETTINGS
[ "$STATUS" -eq 12 ] && ok "settings drift stops an armed watcher" || bad "settings drift exit was $STATUS ($OUTPUT)"
if ! grep -q '^terminal send ' "$FAKE_ORCA_LOG"; then ok "settings drift sends no wake"; else bad "settings drift sent terminal input"; fi

echo "Case 5: terminal failures are propagated"
prepare_case show-fail 'quota'
export FAKE_ORCA_SHOW_MODE=fail
run_watch
[ "$STATUS" -eq 17 ] && ok "terminal show failure is non-zero" || bad "show failure exit was $STATUS ($OUTPUT)"
prepare_case send-fail 'quota available'
export FAKE_ORCA_SEND_MODE=fail
run_watch
[ "$STATUS" -eq 18 ] && ok "terminal send failure is non-zero" || bad "send failure exit was $STATUS ($OUTPUT)"

echo "Case 6: lock acquisition is atomic per terminal"
prepare_case lock 'quota quota quota'
set +e
bash "$TARGET" --terminal term-test --model model-test \
  --interval-seconds 2 --max-seconds 4 --probe-timeout-seconds 1 \
  --state-dir "$STATE_DIR" --settings "$DEFAULT_SETTINGS" >"$TMP_ROOT/first-watch.out" 2>&1 &
first_pid=$!
set -e
for _ in 1 2 3 4 5 6 7 8 9 10; do
  [ -d "$STATE_DIR/lock.term-test" ] && break
  sleep 0.1
done
set +e
bash "$TARGET" --terminal term-test --model model-test \
  --interval-seconds 1 --max-seconds 1 --probe-timeout-seconds 1 \
  --state-dir "$STATE_DIR" --settings "$DEFAULT_SETTINGS" >/dev/null 2>&1
duplicate_status=$?
bash "$TARGET" --terminal term-other --model model-test \
  --interval-seconds 1 --max-seconds 1 --probe-timeout-seconds 1 \
  --state-dir "$STATE_DIR" --settings "$DEFAULT_SETTINGS" >/dev/null 2>&1
different_terminal_status=$?
kill "$first_pid" 2>/dev/null
wait "$first_pid" 2>/dev/null
set -e
[ "$duplicate_status" -eq 73 ] && ok "duplicate watcher for one terminal is rejected" || bad "duplicate watcher exit was $duplicate_status"
[ "$different_terminal_status" -ne 73 ] && ok "different terminals do not share one global lock" || bad "different terminal was blocked by the first lock"
[ ! -d "$STATE_DIR/lock.term-test" ] && ok "signal cleanup releases owned lock" || bad "owned lock remained after signal"

prepare_case stale-lock 'available'
mkdir -p "$STATE_DIR/lock.term-test"
printf '%s\n' 99999999 > "$STATE_DIR/lock.term-test/pid"
run_watch
[ "$STATUS" -eq 11 ] && ok "dead-pid stale lock is reclaimed before probing" || bad "stale lock was not reclaimed ($STATUS: $OUTPUT)"
[ ! -d "$STATE_DIR/lock.term-test" ] && ok "reclaimed stale lock is cleaned on exit" || bad "reclaimed stale lock remained"

echo "Case 7: parameter and state-directory validation fail before launch"
prepare_case validation 'quota'
set +e
bash "$TARGET" --terminal '../bad' --model model-test --state-dir "$STATE_DIR" >/dev/null 2>&1
bad_handle_status=$?
bash "$TARGET" --terminal >/dev/null 2>&1
missing_value_status=$?
bash "$TARGET" --terminal term-test --model model-test --interval-seconds 0 --state-dir "$STATE_DIR" >/dev/null 2>&1
bad_interval_status=$?
ln -s "$TMP_ROOT" "$TMP_ROOT/state-link"
bash "$TARGET" --terminal term-test --model model-test --state-dir "$TMP_ROOT/state-link" >/dev/null 2>&1
symlink_status=$?
bash "$TARGET" --terminal term-test --model model-test --state-dir "$STATE_DIR" >/dev/null 2>&1
missing_settings_status=$?
bash "$TARGET" --terminal term-test --model model-test --state-dir "$STATE_DIR" --settings "$DEFAULT_SETTINGS" --setting-sources user >/dev/null 2>&1
setting_sources_status=$?
set -e
[ "$bad_handle_status" -eq 64 ] && ok "invalid terminal handle is rejected" || bad "bad handle exit was $bad_handle_status"
[ "$missing_value_status" -eq 64 ] && ok "missing option value is rejected cleanly" || bad "missing value exit was $missing_value_status"
[ "$bad_interval_status" -eq 64 ] && ok "zero interval is rejected" || bad "zero interval exit was $bad_interval_status"
[ "$symlink_status" -eq 64 ] && ok "symlink state directory is rejected" || bad "symlink state-dir exit was $symlink_status"
[ "$missing_settings_status" -eq 64 ] && ok "watcher requires explicit settings authority" || bad "watcher without settings exit was $missing_settings_status"
[ "$setting_sources_status" -eq 64 ] && ok "watcher rejects mutable setting sources" || bad "watcher with setting sources exit was $setting_sources_status"

echo
echo "Result: $pass pass, $fail fail"
[ "$fail" -eq 0 ]
