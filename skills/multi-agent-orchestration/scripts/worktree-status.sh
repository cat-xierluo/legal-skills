#!/usr/bin/env bash
# worktree-status.sh — read-only status summary for one worker branch/session.

set -euo pipefail

PROJECT_DIR=""
BRANCH=""
SESSION=""

usage() {
  cat >&2 <<'USAGE'
Usage:
  worktree-status.sh --project PATH --branch NAME --session NAME

Reports worktree path, tmux session state, checkpoint status, git dirtiness,
latest commit, and PR URL if available. This script is read-only.
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
    --session)
      SESSION="$2"
      shift 2
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

PROJECT_DIR=$(cd "$PROJECT_DIR" && pwd)

worktree_for_branch() {
  git -C "$PROJECT_DIR" worktree list --porcelain 2>/dev/null | awk -v target="refs/heads/$BRANCH" '
    /^worktree / { wt = substr($0, 10) }
    /^branch / {
      if (substr($0, 8) == target) {
        print wt
        exit
      }
    }
  '
}

WT=$(worktree_for_branch)
if [ -z "$WT" ]; then
  echo "WORKTREE_STATUS: missing branch=$BRANCH"
  exit 2
fi

STATUS_FILE="$WT/.claude/agent-sessions/$SESSION/STATUS.json"
RESULT_FILE="$WT/.claude/agent-sessions/$SESSION/RESULT.md"
PATCH_FILE="$WT/.claude/agent-sessions/$SESSION/PATCH_SUMMARY.md"

current_branch=$(git -C "$WT" branch --show-current 2>/dev/null || echo "")
dirty_count=$(git -C "$WT" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
latest_commit=$(git -C "$WT" log -1 --format="%h %s" 2>/dev/null || echo "none")

echo "WORKTREE_STATUS: branch=$BRANCH worktree=$WT current_branch=${current_branch:-unknown} dirty=$dirty_count"
echo "WORKTREE_COMMIT: $latest_commit"

if command -v tmux >/dev/null 2>&1 && tmux has-session -t "$SESSION" 2>/dev/null; then
  pane_cwd=$(tmux display-message -p -t "$SESSION" '#{pane_current_path}' 2>/dev/null || echo "")
  echo "TMUX_STATUS: alive session=$SESSION cwd=$pane_cwd"
else
  echo "TMUX_STATUS: missing session=$SESSION"
fi

if [ -f "$STATUS_FILE" ]; then
  if command -v jq >/dev/null 2>&1; then
    status=$(jq -r '.status // "unknown"' "$STATUS_FILE" 2>/dev/null || echo "unknown")
    phase=$(jq -r '.phase // ""' "$STATUS_FILE" 2>/dev/null || echo "")
    progress=$(jq -r '.progress // ""' "$STATUS_FILE" 2>/dev/null || echo "")
    updated_at=$(jq -r '.updated_at // ""' "$STATUS_FILE" 2>/dev/null || echo "")
    current_action=$(jq -r '.current_action // ""' "$STATUS_FILE" 2>/dev/null || echo "")
    next_action=$(jq -r '.next_action // ""' "$STATUS_FILE" 2>/dev/null || echo "")
    last_commit_sha=$(jq -r '.git.last_commit_sha // .last_commit_sha // ""' "$STATUS_FILE" 2>/dev/null || echo "")
    last_commit_at=$(jq -r '.git.last_commit_at // ""' "$STATUS_FILE" 2>/dev/null || echo "")
    commits_since_base=$(jq -r '.git.commits_since_base // ""' "$STATUS_FILE" 2>/dev/null || echo "")
    pr_url=$(jq -r '.git.pr_url // .pr_url // ""' "$STATUS_FILE" 2>/dev/null || echo "")
    echo "CHECKPOINT_STATUS: status=${status:-unknown} phase=${phase:-n/a} progress=${progress:-n/a} updated_at=${updated_at:-n/a}"
    echo "CHECKPOINT_ACTION: current=${current_action:-n/a} next=${next_action:-n/a}"
    echo "CHECKPOINT_GIT: commit=${last_commit_sha:-n/a} commit_at=${last_commit_at:-n/a} commits_since_base=${commits_since_base:-n/a} pr=${pr_url:-n/a}"
  else
    echo "CHECKPOINT_STATUS: present jq_missing file=$STATUS_FILE"
  fi
else
  echo "CHECKPOINT_STATUS: missing file=$STATUS_FILE"
fi

[ -f "$RESULT_FILE" ] && echo "CHECKPOINT_RESULT: $RESULT_FILE"
[ -f "$PATCH_FILE" ] && echo "CHECKPOINT_PATCH: $PATCH_FILE"
exit 0
