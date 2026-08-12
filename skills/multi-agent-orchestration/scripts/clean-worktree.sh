#!/usr/bin/env bash
# clean-worktree.sh — safe cleanup for one worker tmux session and worktree.

set -euo pipefail

PROJECT_DIR=""
BRANCH=""
SESSION=""
WORKTREE=""
EXECUTE=0
KEEP_SESSION=0
KEEP_WORKTREE=0
DELETE_BRANCH=0
FORCE_DIRTY=0

usage() {
  cat >&2 <<'USAGE'
Usage:
  clean-worktree.sh --project PATH --branch NAME --session NAME [options]

Default is dry-run. It prints planned cleanup and makes no changes.

Options:
  --worktree PATH        Override worktree path if branch lookup is unavailable
  --execute             Actually kill tmux/remove worktree
  --keep-session        Do not kill tmux session
  --keep-worktree       Do not remove git worktree
  --delete-branch       Delete local branch after worktree removal
  --force-remove-dirty  Allow removing a dirty worktree

This script never deletes a remote branch and never runs git reset.
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
    --worktree)
      WORKTREE="$2"
      shift 2
      ;;
    --execute)
      EXECUTE=1
      shift
      ;;
    --keep-session)
      KEEP_SESSION=1
      shift
      ;;
    --keep-worktree)
      KEEP_WORKTREE=1
      shift
      ;;
    --delete-branch)
      DELETE_BRANCH=1
      shift
      ;;
    --force-remove-dirty)
      FORCE_DIRTY=1
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

PROJECT_DIR=$(cd "$PROJECT_DIR" && pwd -P)
case "$WORKTREE" in
  "") ;;
  /*) ;;
  *) WORKTREE="$PROJECT_DIR/$WORKTREE" ;;
esac

if [ -z "$WORKTREE" ]; then
  WORKTREE=$(git -C "$PROJECT_DIR" worktree list --porcelain 2>/dev/null | awk -v target="refs/heads/$BRANCH" '
    /^worktree / { wt = substr($0, 10) }
    /^branch / {
      if (substr($0, 8) == target) {
        print wt
        exit
      }
    }
  ')
fi

run() {
  printf 'CLEAN_WORKTREE_RUN: %s\n' "$*"
  [ "$EXECUTE" -eq 1 ] || return 0
  "$@"
}

echo "CLEAN_WORKTREE_MODE: $([ "$EXECUTE" -eq 1 ] && echo execute || echo dry-run)"
echo "CLEAN_WORKTREE_TARGET: branch=$BRANCH session=$SESSION worktree=${WORKTREE:-missing}"

if [ -n "$WORKTREE" ] && [ -f "$WORKTREE/.claude/agent-sessions/$SESSION/METADATA.json" ]; then
  metadata_file="$WORKTREE/.claude/agent-sessions/$SESSION/METADATA.json"
  if command -v jq >/dev/null 2>&1; then
    metadata_base_ref=$(jq -r '.base_ref // ""' "$metadata_file" 2>/dev/null || echo "")
    metadata_created_at=$(jq -r '.created_at // ""' "$metadata_file" 2>/dev/null || echo "")
    metadata_backend=$(jq -r '.runtime.worker_backend // ""' "$metadata_file" 2>/dev/null || echo "")
    metadata_profile=$(jq -r '.runtime.runtime_profile // ""' "$metadata_file" 2>/dev/null || echo "")
    metadata_env_isolation=$(jq -r '.runtime.env_isolation // ""' "$metadata_file" 2>/dev/null || echo "")
    metadata_pr=$(jq -r '.pr.url // ""' "$metadata_file" 2>/dev/null || echo "")
    # v2.1（DEC-114）：读 ORCA worktree_id，用于后续 orca worktree rm 同步清理。
    metadata_orca_worktree_id=$(jq -r '.session.orca.worktree_id // ""' "$metadata_file" 2>/dev/null || echo "")
    metadata_orca_mode=$(jq -r '.session.orca.mode // ""' "$metadata_file" 2>/dev/null || echo "")
    # v2.1.1（Task-033）：读 ORCA supervised dispatch_id，清理时 worker-stop（释放 supervised worker）。
    metadata_orca_dispatch_id=$(jq -r '.session.orca.supervised.dispatch_id // ""' "$metadata_file" 2>/dev/null || echo "")
    echo "CLEAN_WORKTREE_METADATA: base=${metadata_base_ref:-n/a} created_at=${metadata_created_at:-n/a} backend=${metadata_backend:-n/a} profile=${metadata_profile:-n/a} env_isolation=${metadata_env_isolation:-n/a} pr=${metadata_pr:-n/a} orca_mode=${metadata_orca_mode:-n/a}"
  else
    echo "CLEAN_WORKTREE_METADATA: present jq_missing file=$metadata_file"
  fi
else
  echo "CLEAN_WORKTREE_METADATA: missing"
fi

if [ "$KEEP_SESSION" -eq 0 ]; then
  if command -v tmux >/dev/null 2>&1 && tmux has-session -t "$SESSION" 2>/dev/null; then
    run tmux kill-session -t "$SESSION"
  else
    echo "CLEAN_WORKTREE_SESSION: missing session=$SESSION"
  fi
else
  echo "CLEAN_WORKTREE_SESSION: kept session=$SESSION"
fi

# v2.1.1（Task-033）：ORCA supervised worker 清理。有 dispatch_id 时先 worker-stop（释放 supervised worker），
# 再 worktree rm。用 run() 包装保持 dry-run 友好；无 dispatch_id（非 supervised）/ ORCA 不可用时跳过。
if [ -n "${metadata_orca_dispatch_id:-}" ] && [ "$KEEP_WORKTREE" -eq 0 ]; then
  if command -v orca >/dev/null 2>&1; then
    run orca orchestration worker-stop --dispatch "$metadata_orca_dispatch_id"
  else
    echo "CLEAN_WORKTREE_ORCA_SUPERVISED: orca CLI not found, skip worker-stop (dispatch=$metadata_orca_dispatch_id)"
  fi
fi

# v2.1（DEC-114）：ORCA 模式下额外清理 ORCA 跟踪的 worktree（tmux 路径不会自动同步）。
# 用 run() 包装保持 dry-run 友好；ORCA 不可用 / 无 worktree_id 时跳过（不阻塞 git 清理）。
if [ -n "${metadata_orca_worktree_id:-}" ] && [ "$KEEP_WORKTREE" -eq 0 ]; then
  if command -v orca >/dev/null 2>&1; then
    run orca worktree rm --worktree "id:$metadata_orca_worktree_id" --force
  else
    echo "CLEAN_WORKTREE_ORCA: orca CLI not found, skip ORCA worktree rm (worktree_id=$metadata_orca_worktree_id)"
  fi
fi

if [ "$KEEP_WORKTREE" -eq 0 ]; then
  if [ -n "$WORKTREE" ] && [ -d "$WORKTREE" ]; then
    dirty_count=$(git -C "$WORKTREE" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
    echo "CLEAN_WORKTREE_DIRTY: $dirty_count"
    if [ "$dirty_count" != "0" ] && [ "$FORCE_DIRTY" -eq 0 ]; then
      echo "CLEAN_WORKTREE_REFUSED: dirty worktree; rerun with --force-remove-dirty after review" >&2
      [ "$EXECUTE" -eq 1 ] && exit 2
    elif [ "$FORCE_DIRTY" -eq 1 ]; then
      run git -C "$PROJECT_DIR" worktree remove --force "$WORKTREE"
    else
      run git -C "$PROJECT_DIR" worktree remove "$WORKTREE"
    fi
  else
    echo "CLEAN_WORKTREE_WORKTREE: missing"
  fi
else
  echo "CLEAN_WORKTREE_WORKTREE: kept"
fi

if [ "$DELETE_BRANCH" -eq 1 ]; then
  if git -C "$PROJECT_DIR" show-ref --verify --quiet "refs/heads/$BRANCH"; then
    run git -C "$PROJECT_DIR" branch -d "$BRANCH"
  else
    echo "CLEAN_WORKTREE_BRANCH: missing branch=$BRANCH"
  fi
else
  echo "CLEAN_WORKTREE_BRANCH: kept branch=$BRANCH"
fi

[ "$EXECUTE" -eq 1 ] && echo "CLEAN_WORKTREE_DONE" || echo "CLEAN_WORKTREE_DRY_RUN_DONE"
