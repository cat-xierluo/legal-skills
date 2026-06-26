#!/usr/bin/env bash
# spawn-worker.sh — create an isolated worktree and tmux session for one worker.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

PROJECT_DIR=""
BRANCH=""
WORKTREE=""
SESSION=""
BASE_REF="main"
COMMAND=""
DRY_RUN=0
WORKER_BACKEND=""
RUNTIME_PROFILE=""
API_PROVIDER=""
MODEL=""
PROVIDER_SLOT=""
ENV_ISOLATION=""
WAVE_ID=""
WAVE_WORKER_ID=""
VERIFY_COMMANDS=()
WITH_SENTINEL=0
SENTINEL_POLL_INTERVAL=5
SENTINEL_MAX_WAIT=7200
KEEP_TMUX_ON_TERMINAL=0

usage() {
  cat >&2 <<'USAGE'
Usage:
  spawn-worker.sh --project PATH --branch NAME --session NAME [options]

Options:
  --worktree PATH   Worktree path. Defaults to .claude/worktrees/tmux-{branch}
  --base-ref REF    Base ref for new branches. Default: main
  --command CMD     Command to run in tmux. Default: login shell
  --worker-backend NAME
                   Worker backend, e.g. claude-code, codex, opencode, custom
  --runtime-profile NAME
                   Runtime/settings/profile name used by the worker
  --api-provider NAME
                   API/provider name used by the worker
  --model NAME     Model name used by the worker
  --provider-slot SLOT
                   Provider concurrency slot for this worker
  --env-isolation DESC
                   Provider/env isolation strategy recorded in METADATA.json
  --wave-id ID     Wave ID for this worker
  --wave-worker-id ID
                   Worker ID within the wave
  --verify-cmd CMD Expected verification command; repeat for multiple commands
  --with-sentinel   Print recommended sentinel.sh command (does NOT start sentinel itself)
  --sentinel-poll-interval N
                   Default 5; passed to the recommended sentinel command
  --sentinel-max-wait SECONDS
                   Default 7200; passed to the recommended sentinel command
  --keep-tmux-on-terminal
                   Pass --keep-tmux-on-terminal to the recommended sentinel command
  --dry-run         Print actions without changing anything

The script only creates isolation and starts the session. The PM must still send
the Bootstrap-only or Full worker prompt and confirm STATUS.json appears.
When --with-sentinel is set, spawn-worker.sh outputs the sentinel command but
does NOT start the sentinel itself. The PM must run that command with
run_in_background=true so the harness re-invokes PM on sentinel exit.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT_DIR="$2"
      shift 2
      ;;
    --branch)
      BRANCH="$2"
      shift 2
      ;;
    --worktree)
      WORKTREE="$2"
      shift 2
      ;;
    --session)
      SESSION="$2"
      shift 2
      ;;
    --base-ref)
      BASE_REF="$2"
      shift 2
      ;;
    --command)
      COMMAND="$2"
      shift 2
      ;;
    --worker-backend)
      WORKER_BACKEND="$2"
      shift 2
      ;;
    --runtime-profile)
      RUNTIME_PROFILE="$2"
      shift 2
      ;;
    --api-provider)
      API_PROVIDER="$2"
      shift 2
      ;;
    --model)
      MODEL="$2"
      shift 2
      ;;
    --provider-slot)
      PROVIDER_SLOT="$2"
      shift 2
      ;;
    --env-isolation)
      ENV_ISOLATION="$2"
      shift 2
      ;;
    --wave-id)
      WAVE_ID="$2"
      shift 2
      ;;
    --wave-worker-id)
      WAVE_WORKER_ID="$2"
      shift 2
      ;;
    --verify-cmd)
      VERIFY_COMMANDS+=("$2")
      shift 2
      ;;
    --with-sentinel)
      WITH_SENTINEL=1
      shift
      ;;
    --sentinel-poll-interval)
      SENTINEL_POLL_INTERVAL="$2"
      shift 2
      ;;
    --sentinel-max-wait)
      SENTINEL_MAX_WAIT="$2"
      shift 2
      ;;
    --keep-tmux-on-terminal)
      KEEP_TMUX_ON_TERMINAL=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 64
      ;;
  esac
done

[ -n "$PROJECT_DIR" ] || { usage; exit 64; }
[ -n "$BRANCH" ] || { usage; exit 64; }
[ -n "$SESSION" ] || { usage; exit 64; }
command -v git >/dev/null 2>&1 || { echo "ERROR: git is required" >&2; exit 64; }
command -v tmux >/dev/null 2>&1 || { echo "ERROR: tmux is required" >&2; exit 64; }
command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required" >&2; exit 64; }

PROJECT_DIR=$(cd "$PROJECT_DIR" && pwd -P)
safe_branch=$(printf '%s' "$BRANCH" | tr '/[:space:]' '-' | tr -cd 'A-Za-z0-9._-')
if [ -z "$WORKTREE" ]; then
  WORKTREE=".claude/worktrees/tmux-$safe_branch"
fi
case "$WORKTREE" in
  /*) ;;
  *) WORKTREE="$PROJECT_DIR/$WORKTREE" ;;
esac

SESSION_CONTEXT="$WORKTREE/.claude/agent-sessions/$SESSION"
METADATA_FILE="$SESSION_CONTEXT/METADATA.json"
[ -n "$COMMAND" ] || COMMAND="${SHELL:-/bin/bash} -l"

run() {
  printf 'SPAWN_WORKER_RUN: %s\n' "$*"
  [ "$DRY_RUN" -eq 1 ] || "$@"
}

if ! git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: --project is not a git work tree: $PROJECT_DIR" >&2
  exit 64
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "ERROR: tmux session already exists: $SESSION" >&2
  exit 1
fi

if ! git -C "$PROJECT_DIR" rev-parse --verify --quiet "$BASE_REF^{commit}" >/dev/null; then
  echo "ERROR: base ref not found: $BASE_REF" >&2
  exit 1
fi
BASE_SHA=$(git -C "$PROJECT_DIR" rev-parse "$BASE_REF^{commit}")

existing_wt=$(git -C "$PROJECT_DIR" worktree list --porcelain | awk -v target="refs/heads/$BRANCH" '
  /^worktree / { wt = substr($0, 10) }
  /^branch / {
    if (substr($0, 8) == target) {
      print wt
      exit
    }
  }
')

if [ -n "$existing_wt" ]; then
  WORKTREE="$existing_wt"
  SESSION_CONTEXT="$WORKTREE/.claude/agent-sessions/$SESSION"
  METADATA_FILE="$SESSION_CONTEXT/METADATA.json"
  echo "SPAWN_WORKER_REUSE_WORKTREE: $WORKTREE"
elif [ -d "$WORKTREE" ]; then
  echo "ERROR: worktree path exists but is not registered for branch $BRANCH: $WORKTREE" >&2
  exit 1
elif git -C "$PROJECT_DIR" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  run git -C "$PROJECT_DIR" worktree add "$WORKTREE" "$BRANCH"
else
  run git -C "$PROJECT_DIR" worktree add "$WORKTREE" -b "$BRANCH" "$BASE_REF"
fi

if [ "$DRY_RUN" -eq 0 ]; then
  WORKTREE=$(cd "$WORKTREE" && pwd -P)
  SESSION_CONTEXT="$WORKTREE/.claude/agent-sessions/$SESSION"
  METADATA_FILE="$SESSION_CONTEXT/METADATA.json"
fi

run mkdir -p "$SESSION_CONTEXT"

write_metadata() {
  created_at=$(date -u "+%Y-%m-%dT%H:%M:%SZ")
  if [ "${#VERIFY_COMMANDS[@]}" -gt 0 ]; then
    verify_json=$(printf '%s\n' "${VERIFY_COMMANDS[@]}" | jq -R . | jq -s .)
  else
    verify_json="[]"
  fi

  echo "SPAWN_WORKER_METADATA: $METADATA_FILE"
  if [ "$DRY_RUN" -eq 1 ]; then
    return 0
  fi

  jq -n \
    --arg schema "multi-agent-orchestration.worktree-metadata.v1" \
    --arg created_at "$created_at" \
    --arg project "$PROJECT_DIR" \
    --arg worktree "$WORKTREE" \
    --arg branch "$BRANCH" \
    --arg base_ref "$BASE_REF" \
    --arg base_sha "$BASE_SHA" \
    --arg session "$SESSION" \
    --arg session_context "$SESSION_CONTEXT" \
    --arg command "$COMMAND" \
    --arg worker_backend "$WORKER_BACKEND" \
    --arg runtime_profile "$RUNTIME_PROFILE" \
    --arg api_provider "$API_PROVIDER" \
    --arg model "$MODEL" \
    --arg provider_slot "$PROVIDER_SLOT" \
    --arg env_isolation "$ENV_ISOLATION" \
    --arg wave_id "$WAVE_ID" \
    --arg wave_worker_id "$WAVE_WORKER_ID" \
    --argjson verification_commands "$verify_json" \
    '{
      schema: $schema,
      created_at: $created_at,
      project: $project,
      worktree: $worktree,
      branch: $branch,
      base_ref: $base_ref,
      base_sha: $base_sha,
      session: {
        id: $session,
        context: $session_context
      },
      runtime: {
        worker_backend: $worker_backend,
        runtime_profile: $runtime_profile,
        api_provider: $api_provider,
        model: $model,
        provider_slot: $provider_slot,
        env_isolation: $env_isolation,
        command: $command
      },
      wave: {
        id: $wave_id,
        worker_id: $wave_worker_id
      },
      verification: {
        commands: $verification_commands
      },
      pr: {
        number: null,
        url: "",
        state: ""
      }
    }' > "$METADATA_FILE"
}

write_metadata

exclude_file=$(git -C "$WORKTREE" rev-parse --git-path info/exclude)
if [ "$DRY_RUN" -eq 0 ] && ! grep -qxF ".claude/agent-sessions/" "$exclude_file" 2>/dev/null; then
  printf '\n.claude/agent-sessions/\n' >> "$exclude_file"
fi

run tmux new-session -d -s "$SESSION" -c "$WORKTREE" "$COMMAND"

if [ "$DRY_RUN" -eq 0 ]; then
  pane_cwd=$(tmux display-message -p -t "$SESSION" '#{pane_current_path}' 2>/dev/null || echo "")
  pane_cwd_physical="$pane_cwd"
  if [ -n "$pane_cwd" ] && [ -d "$pane_cwd" ]; then
    pane_cwd_physical=$(cd "$pane_cwd" && pwd -P)
  fi
  current_branch=$(git -C "$WORKTREE" branch --show-current 2>/dev/null || echo "")
  echo "SPAWN_WORKER_SESSION: $SESSION"
  echo "SPAWN_WORKER_WORKTREE: $WORKTREE"
  echo "SPAWN_WORKER_CONTEXT: $SESSION_CONTEXT"
  echo "SPAWN_WORKER_GATE: cwd=$pane_cwd_physical branch=$current_branch expected_cwd=$WORKTREE expected_branch=$BRANCH"
  if [ "$pane_cwd_physical" != "$WORKTREE" ] || [ "$current_branch" != "$BRANCH" ]; then
    echo "SPAWN_WORKER_GATE_FAILED" >&2
    exit 2
  fi
fi

echo "SPAWN_WORKER_NEXT: send worker prompt, then wait for $SESSION_CONTEXT/STATUS.json"

if [ "$WITH_SENTINEL" -eq 1 ] && [ "$DRY_RUN" -eq 0 ]; then
  SENTINEL_SCRIPT="$SCRIPT_DIR/sentinel.sh"
  SENTINEL_CMD="bash $SENTINEL_SCRIPT --status-file $SESSION_CONTEXT/STATUS.json --tmux-session $SESSION --poll-interval $SENTINEL_POLL_INTERVAL --max-wait $SENTINEL_MAX_WAIT"
  if [ "$KEEP_TMUX_ON_TERMINAL" -eq 1 ]; then
    SENTINEL_CMD="$SENTINEL_CMD --keep-tmux-on-terminal"
  fi
  echo "SPAWN_WORKER_SENTINEL_CMD: $SENTINEL_CMD"
  echo "SPAWN_WORKER_RECOMMENDED_NEXT: run the above command with Bash run_in_background=true (NOT from inside spawn-worker). Sentinel exit triggers harness task-notification and wakes PM."
fi
