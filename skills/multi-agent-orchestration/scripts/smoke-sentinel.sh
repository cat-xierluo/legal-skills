#!/usr/bin/env bash
# smoke-sentinel.sh — end-to-end smoke test for the sentinel pattern.
#
# Two scenarios:
#   (1) done path: STATUS.json transitions running -> done, sentinel exits 0
#                   and kills the worker's tmux session.
#   (2) timeout path: STATUS.json never reaches terminal, sentinel hits
#                     --max-wait and exits 124.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TMP_ROOT=$(mktemp -d)
TMP_ROOT=$(cd "$TMP_ROOT" && pwd -P)
SESSION_DONE="smoke-sentinel-done-$$"
SESSION_TIMEOUT="smoke-sentinel-timeout-$$"

cleanup() {
  tmux kill-session -t "$SESSION_DONE" 2>/dev/null || true
  tmux kill-session -t "$SESSION_TIMEOUT" 2>/dev/null || true
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

assert_contains() {
  local haystack="$1"
  local needle="$2"
  case "$haystack" in
    *"$needle"*) ;;
    *)
      printf 'ASSERTION FAILED: expected output to contain: %s\n' "$needle" >&2
      printf '%s\n' "$haystack" >&2
      exit 1
      ;;
  esac
}

assert_not_contains() {
  local haystack="$1"
  local needle="$2"
  case "$haystack" in
    *"$needle"*)
      printf 'ASSERTION FAILED: expected output NOT to contain: %s\n' "$needle" >&2
      printf '%s\n' "$haystack" >&2
      exit 1
      ;;
    *) ;;
  esac
}

command -v jq >/dev/null 2>&1 || { echo "SKIP: jq is required"; exit 77; }
command -v tmux >/dev/null 2>&1 || { echo "SKIP: tmux is required"; exit 77; }

CTX_DONE="$TMP_ROOT/done/.claude/agent-sessions/$SESSION_DONE"
CTX_TIMEOUT="$TMP_ROOT/timeout/.claude/agent-sessions/$SESSION_TIMEOUT"
STATUS_DONE="$CTX_DONE/STATUS.json"
STATUS_TIMEOUT="$CTX_TIMEOUT/STATUS.json"
LOG_DONE="$CTX_DONE/SENTINEL_OUT.log"
LOG_TIMEOUT="$CTX_TIMEOUT/SENTINEL_OUT.log"

mkdir -p "$CTX_DONE" "$CTX_TIMEOUT"

# ---------- Scenario 1: done path ----------
echo "SMOKE_SENTINEL_CASE: done"
tmux new-session -d -s "$SESSION_DONE" -x 200 -y 50 "printf 'TOKEN=should-not-leak\\nSECRET=should-not-leak\\nworker thinking...\\n'; sleep 60" >/dev/null
sleep 0.3
if ! tmux has-session -t "$SESSION_DONE" 2>/dev/null; then
  echo "SKIP: tmux session could not be created"; exit 77
fi

cat > "$STATUS_DONE" <<JSON
{
  "status": "running",
  "phase": "smoke",
  "updated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "branch": "smoke/sentinel-done",
  "worktree": "$TMP_ROOT/done",
  "session_id": "$SESSION_DONE",
  "session_context": "$CTX_DONE"
}
JSON

# Run sentinel in the background; capture its exit code via wait.
bash "$SCRIPT_DIR/sentinel.sh" \
  --status-file "$STATUS_DONE" \
  --tmux-session "$SESSION_DONE" \
  --poll-interval 1 \
  --max-wait 30 \
  --pane-tail-lines 20 >/dev/null 2>&1 &
SENTINEL_DONE_PID=$!

# Give the sentinel a moment to start, then flip STATUS to done.
sleep 2
cat > "$STATUS_DONE" <<JSON
{
  "status": "done",
  "phase": "smoke-complete",
  "updated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "branch": "smoke/sentinel-done",
  "worktree": "$TMP_ROOT/done",
  "session_id": "$SESSION_DONE",
  "session_context": "$CTX_DONE"
}
JSON

# Wait for the sentinel to exit (max 15s).
DONE_EXIT=0
wait "$SENTINEL_DONE_PID" || DONE_EXIT=$?

# Validate
LOG_DONE_CONTENT=$(cat "$LOG_DONE" 2>/dev/null || echo "(no log)")
assert_contains "$LOG_DONE_CONTENT" "SENTINEL_START: status=$STATUS_DONE"
assert_contains "$LOG_DONE_CONTENT" "SENTINEL_TERMINAL: status=done"
assert_contains "$LOG_DONE_CONTENT" "SENTINEL_TMUX_KILLED: session=$SESSION_DONE"
assert_contains "$LOG_DONE_CONTENT" "SENTINEL_PANE_TAIL: session=$SESSION_DONE"
assert_not_contains "$LOG_DONE_CONTENT" "TOKEN=should-not-leak"
assert_not_contains "$LOG_DONE_CONTENT" "SECRET=should-not-leak"

if [ "$DONE_EXIT" -ne 0 ]; then
  printf 'ASSERTION FAILED: sentinel done path expected exit 0, got %d\n' "$DONE_EXIT" >&2
  exit 1
fi

if tmux has-session -t "$SESSION_DONE" 2>/dev/null; then
  echo "ASSERTION FAILED: tmux session still alive after sentinel terminal: $SESSION_DONE" >&2
  exit 1
fi

# ---------- Scenario 2: timeout path ----------
echo "SMOKE_SENTINEL_CASE: timeout"

# No tmux session needed; sentinel will skip pane capture and tmux kill on
# timeout if the session is absent. We do create one to verify the sentinel
# handles "tmux already gone" gracefully at the timeout boundary.
cat > "$STATUS_TIMEOUT" <<JSON
{
  "status": "running",
  "phase": "smoke-stuck",
  "updated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "branch": "smoke/sentinel-timeout",
  "worktree": "$TMP_ROOT/timeout",
  "session_id": "$SESSION_TIMEOUT",
  "session_context": "$CTX_TIMEOUT"
}
JSON

bash "$SCRIPT_DIR/sentinel.sh" \
  --status-file "$STATUS_TIMEOUT" \
  --tmux-session "$SESSION_TIMEOUT" \
  --poll-interval 1 \
  --max-wait 4 >/dev/null 2>&1 &
SENTINEL_TIMEOUT_PID=$!

TIMEOUT_EXIT=0
wait "$SENTINEL_TIMEOUT_PID" || TIMEOUT_EXIT=$?

LOG_TIMEOUT_CONTENT=$(cat "$LOG_TIMEOUT" 2>/dev/null || echo "(no log)")
assert_contains "$LOG_TIMEOUT_CONTENT" "SENTINEL_START: status=$STATUS_TIMEOUT"
assert_contains "$LOG_TIMEOUT_CONTENT" "SENTINEL_TIMEOUT:"

if [ "$TIMEOUT_EXIT" -ne 124 ]; then
  printf 'ASSERTION FAILED: sentinel timeout path expected exit 124, got %d\n' "$TIMEOUT_EXIT" >&2
  exit 1
fi

# Validate usage path
USAGE_OUT=$(bash "$SCRIPT_DIR/sentinel.sh" 2>&1 || true)
assert_contains "$USAGE_OUT" "Usage:"

USAGE_OUT2=$(bash "$SCRIPT_DIR/sentinel.sh" --bogus 2>&1 || true)
assert_contains "$USAGE_OUT2" "Unknown argument: --bogus"

echo "SMOKE_SENTINEL_OK"
