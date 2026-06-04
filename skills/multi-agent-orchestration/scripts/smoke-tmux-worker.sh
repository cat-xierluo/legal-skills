#!/usr/bin/env bash
# smoke-tmux-worker.sh — end-to-end smoke test for tmux worker orchestration.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TMP_ROOT=$(mktemp -d)
SESSION="smoke-worker-$$"
REPO="$TMP_ROOT/repo"
BRANCH="feat/smoke-worker"
WT="$REPO/.claude/worktrees/tmux-smoke-worker"
CTX="$WT/.claude/agent-sessions/$SESSION"
STATUS_FILE="$CTX/STATUS.json"

cleanup() {
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  if [ -d "$REPO" ]; then
    git -C "$REPO" worktree remove --force "$WT" >/dev/null 2>&1 || true
  fi
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
      printf 'ASSERTION FAILED: expected output not to contain: %s\n' "$needle" >&2
      printf '%s\n' "$haystack" >&2
      exit 1
      ;;
    *) ;;
  esac
}

command -v git >/dev/null 2>&1 || { echo "SKIP: git is required"; exit 77; }
command -v jq >/dev/null 2>&1 || { echo "SKIP: jq is required"; exit 77; }
command -v tmux >/dev/null 2>&1 || { echo "SKIP: tmux is required"; exit 77; }

mkdir -p "$REPO"
git -C "$REPO" init -q
git -C "$REPO" config user.email "smoke@example.invalid"
git -C "$REPO" config user.name "Smoke Test"
printf 'smoke\n' > "$REPO/README.md"
git -C "$REPO" add README.md
git -C "$REPO" commit -q -m "init"
git -C "$REPO" branch -M main
git -C "$REPO" worktree add -q "$WT" -b "$BRANCH" main

mkdir -p "$CTX"
now=$(date -u "+%Y-%m-%dT%H:%M:%SZ")
cat > "$STATUS_FILE" <<JSON
{
  "status": "running",
  "phase": "bootstrap",
  "progress": "1/3",
  "updated_at": "$now",
  "heartbeat_interval_seconds": 300,
  "branch": "$BRANCH",
  "worktree": "$WT",
  "session_id": "$SESSION",
  "session_context": "$CTX",
  "current_action": "smoke running",
  "next_action": "finish smoke",
  "orchestration_gate": {
    "required": true,
    "session_verified": true,
    "cwd_matches_worktree": true,
    "branch_matches_expected": true,
    "worktree_isolated": true,
    "degraded": false,
    "degrade_reason": "",
    "escape_attempted": false
  },
  "git": {
    "base_ref": "main",
    "head_ref": "$BRANCH",
    "last_commit_sha": "",
    "pr_url": ""
  },
  "tests": [],
  "needs_input": false,
  "pm_action_required": false,
  "issues": []
}
JSON

tmux new-session -d -s "$SESSION" -c "$WT" "printf '%s\n' 'worker-start' 'TOKEN=abc123' 'worker-end'; sleep 60"
sleep 0.5

monitor_out=$("$SCRIPT_DIR/pm-monitor.sh" \
  --project "$REPO" \
  --base-ref main \
  --commit-stale-threshold 1 \
  --once \
  --branch "$BRANCH:$SESSION")
assert_contains "$monitor_out" "BRANCH_NOT_PUSHED: $BRANCH"
assert_contains "$monitor_out" "CHECKPOINT_STATUS: $SESSION running bootstrap"
assert_contains "$monitor_out" "WORKER_STALE_NO_COMMIT: $SESSION"

cat > "$STATUS_FILE" <<JSON
{
  "status": "done",
  "phase": "complete",
  "progress": "3/3",
  "updated_at": "$now",
  "branch": "$BRANCH",
  "worktree": "$WT",
  "session_id": "$SESSION",
  "session_context": "$CTX",
  "current_action": "smoke done",
  "next_action": "none",
  "orchestration_gate": {
    "required": true,
    "session_verified": true,
    "cwd_matches_worktree": true,
    "branch_matches_expected": true,
    "worktree_isolated": true,
    "degraded": false,
    "degrade_reason": "",
    "escape_attempted": false
  },
  "git": {
    "base_ref": "main",
    "head_ref": "$BRANCH",
    "last_commit_sha": "",
    "pr_url": ""
  },
  "tests": [],
  "needs_input": false,
  "pm_action_required": false,
  "issues": []
}
JSON
printf 'Smoke result\nSECRET=should-not-leak\n' > "$CTX/RESULT.md"

wait_out=$("$SCRIPT_DIR/wait-worker.sh" \
  --session-context "$CTX" \
  --tmux-session "$SESSION" \
  --include-pane-on terminal \
  --once)
assert_contains "$wait_out" "WAIT_WORKER_DONE: $STATUS_FILE"
assert_contains "$wait_out" "WAIT_WORKER_TMUX_TAIL: reason=terminal"
assert_contains "$wait_out" "[redacted sensitive line]"
assert_not_contains "$wait_out" "TOKEN=abc123"
assert_not_contains "$wait_out" "SECRET=should-not-leak"

status_out=$("$SCRIPT_DIR/worktree-status.sh" --project "$REPO" --branch "$BRANCH" --session "$SESSION")
assert_contains "$status_out" "WORKTREE_STATUS: branch=$BRANCH"
assert_contains "$status_out" "CHECKPOINT_STATUS: status=done"

clean_out=$("$SCRIPT_DIR/clean-worktree.sh" --project "$REPO" --branch "$BRANCH" --session "$SESSION")
assert_contains "$clean_out" "CLEAN_WORKTREE_MODE: dry-run"
assert_contains "$clean_out" "CLEAN_WORKTREE_DRY_RUN_DONE"

echo "SMOKE_TMUX_WORKER_OK"
