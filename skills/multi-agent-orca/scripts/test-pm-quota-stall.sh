#!/usr/bin/env bash
# shellcheck disable=SC2015  # Test assertions intentionally use concise pass/fail chains.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TARGET="$SCRIPT_DIR/pm-quota-stall.sh"
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

cat > "$FAKE_ORCA" <<'FAKE'
#!/usr/bin/env bash
set -euo pipefail
{
  for arg in "$@"; do printf '%q ' "$arg"; done
  printf '\n'
} >> "$FAKE_ORCA_LOG"
case "$1 $2" in
  "terminal show")
    case "${FAKE_ORCA_SHOW_MODE:-ok}" in
      fail) exit 1 ;;
      nonok) echo '{"ok":false}'; exit 0 ;;
      malformed) echo 'not-json'; exit 0 ;;
      missing) echo '{"ok":true,"result":{}}'; exit 0 ;;
      wrong) echo '{"ok":true,"result":{"terminal":{"handle":"term-other","connected":true,"writable":true}}}' ;;
      disconnected) echo '{"ok":true,"result":{"terminal":{"handle":"term-test","connected":false,"writable":true}}}' ;;
      readonly) echo '{"ok":true,"result":{"terminal":{"handle":"term-test","connected":true,"writable":false}}}' ;;
      *) echo '{"ok":true,"result":{"terminal":{"handle":"term-test","connected":true,"writable":true}}}' ;;
    esac
    ;;
  "terminal send")
    case "${FAKE_ORCA_SEND_MODE:-ok}" in
      fail) exit 1 ;;
      nonok) echo '{"ok":false}'; exit 0 ;;
      malformed) echo 'not-json'; exit 0 ;;
      *) echo '{"ok":true}' ;;
    esac
    ;;
  *) echo '{"ok":true}' ;;
esac
FAKE

cat > "$FAKE_CLAUDE" <<'FAKE'
#!/usr/bin/env bash
set -euo pipefail
{
  for arg in "$@"; do printf '%q ' "$arg"; done
  printf '\n'
} >> "$FAKE_CLAUDE_LOG"
if [ -n "${FAKE_MUTATE_SETTINGS:-}" ] && [ "${FAKE_CLAUDE_MODE:-available}" = available ]; then
  printf '%s\n' '{"changed":true}' > "$FAKE_MUTATE_SETTINGS"
fi
case "${FAKE_CLAUDE_MODE:-available}" in
  available) echo ok ;;
  quota) echo 'HTTP 429: usage limit reached; limit resets at midnight' >&2; exit 1 ;;
  config) echo 'HTTP 400: invalid modelCode, model does not exist' >&2; exit 1 ;;
  auth) echo 'HTTP 401: unauthorized invalid API key' >&2; exit 1 ;;
  network) echo 'network connection refused' >&2; exit 1 ;;
  timeout) sleep 5; echo ok ;;
  mixedauth) echo 'HTTP 401 unauthorized: quota configuration missing' >&2; exit 1 ;;
  mixedconfig) echo 'HTTP 400 bad request: quota configuration missing' >&2; exit 1 ;;
  unknown) echo 'opaque provider failure secret-token-must-not-leak' >&2; exit 1 ;;
  *) echo 'bad fake mode' >&2; exit 2 ;;
esac
FAKE
chmod +x "$FAKE_ORCA" "$FAKE_CLAUDE"
export ORCA_CLI_COMMAND="$FAKE_ORCA"
export CLAUDE_CLI_COMMAND="$FAKE_CLAUDE"
DEFAULT_SETTINGS="$TMP_ROOT/default.settings.json"
printf '%s\n' '{}' > "$DEFAULT_SETTINGS"

OUTPUT=""
STATUS=0
run_pm() {
  : > "$FAKE_ORCA_LOG"
  : > "$FAKE_CLAUDE_LOG"
  set +e
  OUTPUT=$(bash "$TARGET" --terminal term-test --model model-test --probe-timeout-seconds 1 --json --settings "$DEFAULT_SETTINGS" "$@" 2>&1)
  STATUS=$?
  set -e
}

assert_state() {
  local expected_status=$1 classification=$2 action=$3 label=$4
  if [ "$STATUS" -eq "$expected_status" ] \
    && [[ "$OUTPUT" == *"\"classification\":\"$classification\""* ]] \
    && [[ "$OUTPUT" == *"\"action\":\"$action\""* ]]; then
    ok "$label"
  else
    bad "$label (exit=$STATUS output=$OUTPUT)"
  fi
}

echo "Case 1: available is fail-closed until explicit quota evidence exists"
export FAKE_CLAUDE_MODE=available FAKE_ORCA_SHOW_MODE=ok FAKE_ORCA_SEND_MODE=ok
run_pm
assert_state 11 available fail_closed_unarmed "unarmed availability does not wake"
if ! grep -q '^terminal send ' "$FAKE_ORCA_LOG"; then ok "unarmed availability sends nothing"; else bad "unarmed availability sent terminal input"; fi

echo "Case 2: explicit quota is the only arming classification"
export FAKE_CLAUDE_MODE=quota
run_pm
assert_state 10 quota wait "429/usage limit is classified as quota"
if ! grep -q '^terminal send ' "$FAKE_ORCA_LOG"; then ok "quota state sends nothing"; else bad "quota state sent terminal input"; fi

echo "Case 3: armed quota -> available sends exactly one wake"
export FAKE_CLAUDE_MODE=available
run_pm --armed --wake-text 'resume safely'
assert_state 0 available wake_sent "armed availability sends wake"
[ "$(grep -c '^terminal send ' "$FAKE_ORCA_LOG")" -eq 1 ] && ok "wake is sent exactly once" || bad "wake send count was not one"
grep -q -- '--text resume\\ safely --enter --json' "$FAKE_ORCA_LOG" && ok "wake uses exact terminal send contract" || bad "terminal send arguments were wrong"

echo "Case 4: non-quota failures are classified and never wake"
for spec in 'config:12:config' 'auth:13:auth' 'network:14:network' 'unknown:16:unknown'; do
  IFS=: read -r mode expected code <<< "$spec"
  export FAKE_CLAUDE_MODE=$mode
  run_pm --armed
  assert_state "$expected" "$code" "$( [ "$code" = network ] && echo retry_manually || echo fail_closed )" "$mode failure is distinct from quota"
  if ! grep -q '^terminal send ' "$FAKE_ORCA_LOG"; then ok "$mode failure sends nothing"; else bad "$mode failure sent terminal input"; fi
done
[[ "$OUTPUT" != *secret-token-must-not-leak* ]] && ok "raw provider errors are not emitted" || bad "raw provider error leaked"

echo "Case 5: the portable watchdog reports timeout"
export FAKE_CLAUDE_MODE=timeout
run_pm --armed
assert_state 15 timeout none "probe timeout is distinct"

echo "Case 6: terminal show and send failures are non-zero"
export FAKE_CLAUDE_MODE=available FAKE_ORCA_SHOW_MODE=fail FAKE_ORCA_SEND_MODE=ok
run_pm --armed
assert_state 17 unknown terminal_show_failed "terminal show failure is rejected"
export FAKE_ORCA_SHOW_MODE=nonok
run_pm --armed
assert_state 17 unknown terminal_show_failed "terminal show ok:false is rejected"
export FAKE_ORCA_SHOW_MODE=malformed
run_pm --armed
assert_state 17 unknown terminal_show_failed "terminal show malformed JSON is rejected"
export FAKE_ORCA_SHOW_MODE=missing
run_pm --armed
assert_state 17 unknown terminal_show_failed "terminal show missing identity is rejected"
for show_mode in wrong disconnected readonly; do
  export FAKE_ORCA_SHOW_MODE=$show_mode
  run_pm --armed
  assert_state 17 unknown terminal_show_failed "terminal show $show_mode target is rejected"
done
export FAKE_ORCA_SHOW_MODE=ok FAKE_ORCA_SEND_MODE=fail
run_pm --armed
assert_state 18 available terminal_send_failed "terminal send failure is rejected"
export FAKE_ORCA_SEND_MODE=nonok
run_pm --armed
assert_state 18 available terminal_send_failed "terminal send ok:false is rejected"
export FAKE_ORCA_SEND_MODE=malformed
run_pm --armed
assert_state 18 available terminal_send_failed "terminal send malformed JSON is rejected"

export FAKE_ORCA_SEND_MODE=ok FAKE_ORCA_SHOW_MODE=ok FAKE_CLAUDE_MODE=mixedauth
run_pm --armed
assert_state 13 auth fail_closed "mixed auth/quota text cannot arm quota"
export FAKE_CLAUDE_MODE=mixedconfig
run_pm --armed
assert_state 12 config fail_closed "mixed config/quota text cannot arm quota"

echo "Case 7: probe command is side-effect constrained"
export FAKE_ORCA_SEND_MODE=ok FAKE_CLAUDE_MODE=quota
settings="$TMP_ROOT/provider.settings.json"
printf '%s\n' '{}' > "$settings"
run_pm --settings "$settings" --setting-sources user
if grep -q -- "--tools ''" "$FAKE_CLAUDE_LOG" \
  && grep -q -- '--disable-slash-commands' "$FAKE_CLAUDE_LOG" \
  && grep -q -- '--strict-mcp-config' "$FAKE_CLAUDE_LOG" \
  && grep -q -- '--no-session-persistence' "$FAKE_CLAUDE_LOG" \
  && grep -q -- "--settings $settings" "$FAKE_CLAUDE_LOG"; then
  ok "probe disables tools/skills/session and preserves provider settings"
else
  bad "probe safety/provider arguments are incomplete"
fi

settings_sha256=$(python3 - "$settings" <<'PY'
import hashlib
import sys
print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())
PY
)
export FAKE_CLAUDE_MODE=available FAKE_MUTATE_SETTINGS="$settings"
run_pm --armed --settings "$settings" --settings-sha256 "$settings_sha256"
assert_state 12 config settings_identity_changed "settings drift before wake fails closed"
if ! grep -q '^terminal send ' "$FAKE_ORCA_LOG"; then ok "settings drift sends nothing"; else bad "settings drift sent terminal input"; fi
unset FAKE_MUTATE_SETTINGS
printf '%s\n' '{}' > "$settings"
run_pm --armed --settings "$settings" --settings-sha256 "$(printf '0%.0s' {1..64})"
assert_state 12 config settings_identity_changed "initial settings fingerprint mismatch fails closed"

echo "Case 8: invalid input and missing dependency fail before mutation"
set +e
bash "$TARGET" --terminal '../bad' --model model-test >/dev/null 2>&1
invalid_status=$?
bash "$TARGET" --terminal >/dev/null 2>&1
missing_value_status=$?
CLAUDE_CLI_COMMAND="$TMP_ROOT/missing" bash "$TARGET" --terminal term-test --model model-test >/dev/null 2>&1
dependency_status=$?
PYTHON_CLI_COMMAND="$TMP_ROOT/missing" bash "$TARGET" --terminal term-test --model model-test >/dev/null 2>&1
python_dependency_status=$?
bash "$TARGET" --terminal term-test --model model-test --armed >/dev/null 2>&1
armed_without_settings_status=$?
bash "$TARGET" --terminal term-test --model model-test --armed --settings "$DEFAULT_SETTINGS" --setting-sources user >/dev/null 2>&1
armed_with_sources_status=$?
set -e
[ "$invalid_status" -eq 64 ] && ok "invalid terminal handle is rejected" || bad "invalid handle exit was $invalid_status"
[ "$missing_value_status" -eq 64 ] && ok "missing option value is rejected cleanly" || bad "missing value exit was $missing_value_status"
[ "$dependency_status" -eq 64 ] && ok "missing Claude CLI is rejected" || bad "missing Claude CLI exit was $dependency_status"
[ "$python_dependency_status" -eq 64 ] && ok "missing Python runtime is rejected" || bad "missing Python runtime exit was $python_dependency_status"
[ "$armed_without_settings_status" -eq 64 ] && ok "armed wake requires explicit settings authority" || bad "armed wake without settings exit was $armed_without_settings_status"
[ "$armed_with_sources_status" -eq 64 ] && ok "armed wake rejects mutable setting sources" || bad "armed wake with setting sources exit was $armed_with_sources_status"

echo
echo "Result: $pass pass, $fail fail"
[ "$fail" -eq 0 ]
