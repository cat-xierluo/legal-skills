#!/usr/bin/env bash
# smoke-tmux-worker.sh — end-to-end smoke test for tmux worker orchestration.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TMP_ROOT=$(mktemp -d)
TMP_ROOT=$(cd "$TMP_ROOT" && pwd -P)
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

deps_out=$("$SCRIPT_DIR/check-dependencies.sh" --backend custom)
assert_contains "$deps_out" "DEPENDENCY_CHECK_OK"

profile_shell=$("$SCRIPT_DIR/render-runtime-profile.sh" \
  --backend custom \
  --runtime-profile smoke-profile \
  --api-provider smoke-provider \
  --model smoke-model \
  --provider-slot smoke-slot-1 \
  --command "printf '%s\n' 'worker-start' 'TOKEN=abc123' 'worker-end'; sleep 60")
eval "$profile_shell"

claude_command=$("$SCRIPT_DIR/render-runtime-profile.sh" \
  --backend claude-code \
  --settings config/minimax-M3.settings.json \
  --model claude-sonnet-4-5 \
  --permission-mode auto \
  --output command)
assert_contains "$claude_command" "claude"
assert_contains "$claude_command" "--settings"

registry_file="$TMP_ROOT/claude-provider-registry.json"
cat > "$registry_file" <<'JSON'
{
  "providers": {
    "smoke-provider": {
      "base_url": "https://smoke.example.com/anthropic",
      "auth_token_env": "SMOKE_PROVIDER_KEY",
      "models": {
        "fast": "smoke-fast-model"
      }
    }
  }
}
JSON
registry_context=$(SMOKE_PROVIDER_KEY=secret "$SCRIPT_DIR/render-runtime-profile.sh" \
  --backend claude-code \
  --provider-registry "$registry_file" \
  --api-provider smoke-provider \
  --model fast \
  --provider-slot smoke-registry-1 \
  --output prompt-context)
assert_contains "$registry_context" "Settings/Profile Path: registry:$registry_file"
assert_contains "$registry_context" "Model: smoke-fast-model (alias: fast)"
assert_contains "$registry_context" "Env Isolation: registry-env-wrapper(provider=smoke-provider setting-sources=project,local)"
assert_contains "$registry_context" "--model smoke-fast-model"
assert_not_contains "$registry_context" "secret"

codex_context=$("$SCRIPT_DIR/render-runtime-profile.sh" \
  --backend codex \
  --runtime-profile codex-default \
  --model gpt-5 \
  --output prompt-context)
assert_contains "$codex_context" "Worker Backend: codex"
assert_contains "$codex_context" "Model: gpt-5"

mkdir -p "$REPO"
git -C "$REPO" init -q
git -C "$REPO" config user.email "smoke@example.invalid"
git -C "$REPO" config user.name "Smoke Test"
printf 'smoke\n' > "$REPO/README.md"
git -C "$REPO" add README.md
git -C "$REPO" commit -q -m "init"
git -C "$REPO" branch -M main

spawn_out=$("$SCRIPT_DIR/spawn-worker.sh" \
  --project "$REPO" \
  --branch "$BRANCH" \
  --worktree "$WT" \
  --session "$SESSION" \
  --base-ref main \
  --command "$WORKER_COMMAND" \
  --worker-backend "$WORKER_BACKEND" \
  --runtime-profile "$RUNTIME_PROFILE" \
  --api-provider "$API_PROVIDER" \
  --model "$MODEL" \
  --provider-slot "$PROVIDER_SLOT" \
  --env-isolation "$PROVIDER_ENV_ISOLATION" \
  --wave-id wave-smoke \
  --wave-worker-id W1 \
  --verify-cmd "npm run typecheck" \
  --verify-cmd "npm test -- --run")
assert_contains "$spawn_out" "SPAWN_WORKER_METADATA: $CTX/METADATA.json"
assert_contains "$spawn_out" "SPAWN_WORKER_GATE:"

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
assert_contains "$status_out" "WORKTREE_METADATA: base=main"
assert_contains "$status_out" "WORKTREE_RUNTIME: backend=custom profile=smoke-profile provider=smoke-provider model=smoke-model slot=smoke-slot-1 env_isolation=inherited-env"
assert_contains "$status_out" "WORKTREE_WAVE: wave=wave-smoke worker=W1"
assert_contains "$status_out" "WORKTREE_VERIFY: npm run typecheck | npm test -- --run"
assert_contains "$status_out" "CHECKPOINT_STATUS: status=done"

clean_out=$("$SCRIPT_DIR/clean-worktree.sh" --project "$REPO" --branch "$BRANCH" --session "$SESSION")
assert_contains "$clean_out" "CLEAN_WORKTREE_MODE: dry-run"
assert_contains "$clean_out" "CLEAN_WORKTREE_METADATA: base=main"
assert_contains "$clean_out" "CLEAN_WORKTREE_DRY_RUN_DONE"

echo "SMOKE_TMUX_WORKER_OK"
