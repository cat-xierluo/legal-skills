#!/usr/bin/env bash
# spawn-worker.sh — create an isolated worktree and tmux session for one worker.

set -euo pipefail

PROJECT_DIR=""
BRANCH=""
WORKTREE=""
SESSION=""
BASE_REF="main"
COMMAND=""
DRY_RUN=0

usage() {
  cat >&2 <<'USAGE'
Usage:
  spawn-worker.sh --project PATH --branch NAME --session NAME [options]

Options:
  --worktree PATH   Worktree path. Defaults to .claude/worktrees/tmux-{branch}
  --base-ref REF    Base ref for new branches. Default: main
  --command CMD     Command to run in tmux. Default: login shell
  --dry-run         Print actions without changing anything

The script only creates isolation and starts the session. The PM must still send
the Bootstrap-only or Full worker prompt and confirm STATUS.json appears.
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

PROJECT_DIR=$(cd "$PROJECT_DIR" && pwd)
safe_branch=$(printf '%s' "$BRANCH" | tr '/[:space:]' '-' | tr -cd 'A-Za-z0-9._-')
if [ -z "$WORKTREE" ]; then
  WORKTREE=".claude/worktrees/tmux-$safe_branch"
fi
case "$WORKTREE" in
  /*) ;;
  *) WORKTREE="$PROJECT_DIR/$WORKTREE" ;;
esac

SESSION_CONTEXT="$WORKTREE/.claude/agent-sessions/$SESSION"
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
  echo "SPAWN_WORKER_REUSE_WORKTREE: $WORKTREE"
elif [ -d "$WORKTREE" ]; then
  echo "ERROR: worktree path exists but is not registered for branch $BRANCH: $WORKTREE" >&2
  exit 1
elif git -C "$PROJECT_DIR" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  run git -C "$PROJECT_DIR" worktree add "$WORKTREE" "$BRANCH"
else
  run git -C "$PROJECT_DIR" worktree add "$WORKTREE" -b "$BRANCH" "$BASE_REF"
fi

run mkdir -p "$SESSION_CONTEXT"

exclude_file=$(git -C "$WORKTREE" rev-parse --git-path info/exclude)
if [ "$DRY_RUN" -eq 0 ] && ! grep -qxF ".claude/agent-sessions/" "$exclude_file" 2>/dev/null; then
  printf '\n.claude/agent-sessions/\n' >> "$exclude_file"
fi

run tmux new-session -d -s "$SESSION" -c "$WORKTREE" "$COMMAND"

if [ "$DRY_RUN" -eq 0 ]; then
  pane_cwd=$(tmux display-message -p -t "$SESSION" '#{pane_current_path}' 2>/dev/null || echo "")
  current_branch=$(git -C "$WORKTREE" branch --show-current 2>/dev/null || echo "")
  echo "SPAWN_WORKER_SESSION: $SESSION"
  echo "SPAWN_WORKER_WORKTREE: $WORKTREE"
  echo "SPAWN_WORKER_CONTEXT: $SESSION_CONTEXT"
  echo "SPAWN_WORKER_GATE: cwd=$pane_cwd branch=$current_branch expected_cwd=$WORKTREE expected_branch=$BRANCH"
  if [ "$pane_cwd" != "$WORKTREE" ] || [ "$current_branch" != "$BRANCH" ]; then
    echo "SPAWN_WORKER_GATE_FAILED" >&2
    exit 2
  fi
fi

echo "SPAWN_WORKER_NEXT: send worker prompt, then wait for $SESSION_CONTEXT/STATUS.json"
