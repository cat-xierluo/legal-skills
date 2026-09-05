#!/usr/bin/env bash
# pm-cleanup-worker.sh — delivery-bound cleanup for one accepted worker.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORKTREE=""
PROJECT=""
BRANCH=""
SESSION=""
PR_NUMBER=""
EXPECTED_TIP=""
DELIVERY_MODE=""
DELIVERY_COMMIT=""
BRANCH_LIFECYCLE=""
INTEGRATION_TARGET=""
REMOTE="origin"
REPOSITORY=""
EXECUTE=0
CLEAN_SCRIPT="${PM_CLEANUP_CLEAN_WORKTREE_SCRIPT:-$SCRIPT_DIR/clean-worktree.sh}"

usage() {
  cat >&2 <<'USAGE'
Usage:
  pm-cleanup-worker.sh --worktree PATH --branch NAME --pr NUMBER \
    --expected-tip SHA --delivery-mode remote-pr|local-after-pr \
    --delivery-commit SHA [options]

Default is dry-run.  --execute authorizes deletion of the exact delivery-bound
remote branch, worker worktree and local branch.  Unknown identity, dirty state,
active lifecycle state or delivery mismatch fails closed.

Options:
  --project PATH       Main checkout; otherwise read the unique worker metadata
  --session NAME       Worker session; otherwise read the unique worker metadata
  --branch-lifecycle KIND
                       ephemeral-worker or long-lived; otherwise read metadata,
                       then default to ephemeral-worker for legacy workers
  --integration-target NAME
                       PR base branch; otherwise derive from metadata base_ref,
                       then default to main
  --remote NAME        Git remote (default: origin)
  --repository SLUG    GitHub repository identity (HOST/OWNER/REPO)
  --execute            Perform the verified cleanup
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --worktree) WORKTREE="$2"; shift 2 ;;
    --project) PROJECT="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --session) SESSION="$2"; shift 2 ;;
    --pr) PR_NUMBER="$2"; shift 2 ;;
    --expected-tip) EXPECTED_TIP="$2"; shift 2 ;;
    --delivery-mode) DELIVERY_MODE="$2"; shift 2 ;;
    --delivery-commit) DELIVERY_COMMIT="$2"; shift 2 ;;
    --branch-lifecycle) BRANCH_LIFECYCLE="$2"; shift 2 ;;
    --integration-target) INTEGRATION_TARGET="$2"; shift 2 ;;
    --remote) REMOTE="$2"; shift 2 ;;
    --repository) REPOSITORY="$2"; shift 2 ;;
    --execute) EXECUTE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "PM_CLEANUP_USAGE: unknown argument $1" >&2; usage; exit 64 ;;
  esac
done

for dependency in git jq gh; do
  command -v "$dependency" >/dev/null 2>&1 || {
    echo "PM_CLEANUP_DEPENDENCY_MISSING: $dependency" >&2
    exit 64
  }
done
[ -n "$WORKTREE" ] && [ -n "$BRANCH" ] && [ -n "$PR_NUMBER" ] && \
  [ -n "$EXPECTED_TIP" ] && [ -n "$DELIVERY_MODE" ] && [ -n "$DELIVERY_COMMIT" ] || {
    usage
    exit 64
  }
case "$DELIVERY_MODE" in remote-pr|local-after-pr) ;; *) usage; exit 64 ;; esac
[[ "$PR_NUMBER" =~ ^[1-9][0-9]*$ ]] || { echo "PM_CLEANUP_PR_INVALID" >&2; exit 64; }
[[ "$EXPECTED_TIP" =~ ^[0-9a-fA-F]{40}$ ]] || { echo "PM_CLEANUP_TIP_INVALID" >&2; exit 64; }
[[ "$DELIVERY_COMMIT" =~ ^[0-9a-fA-F]{40}$ ]] || { echo "PM_CLEANUP_DELIVERY_COMMIT_INVALID" >&2; exit 64; }
git check-ref-format --branch "$BRANCH" >/dev/null 2>&1 || { echo "PM_CLEANUP_BRANCH_INVALID: $BRANCH" >&2; exit 64; }

WORKTREE=$(cd "$WORKTREE" && pwd -P) || { echo "PM_CLEANUP_WORKTREE_MISSING" >&2; exit 2; }
git -C "$WORKTREE" rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  echo "PM_CLEANUP_NOT_GIT_WORKTREE: $WORKTREE" >&2
  exit 2
}

# Resolve the exact session/project from worker metadata when the caller does not
# provide them.  Multiple matching sessions are ambiguous and therefore retained.
metadata_matches=()
if [ -d "$WORKTREE/.claude/agent-sessions" ]; then
  for metadata in "$WORKTREE"/.claude/agent-sessions/*/METADATA.json; do
    [ -f "$metadata" ] || continue
    jq -e 'type == "object"' "$metadata" >/dev/null 2>&1 || {
      echo "PM_CLEANUP_METADATA_INVALID: $metadata" >&2
      exit 2
    }
    metadata_branch=$(jq -r '.branch // empty' "$metadata")
    metadata_worktree=$(jq -r '.worktree // empty' "$metadata")
    [ "$metadata_branch" = "$BRANCH" ] || continue
    [ -n "$metadata_worktree" ] || continue
    metadata_worktree_real=$(cd "$metadata_worktree" 2>/dev/null && pwd -P || true)
    [ "$metadata_worktree_real" = "$WORKTREE" ] || continue
    metadata_matches+=("$metadata")
  done
fi
if [ -z "$PROJECT" ] || [ -z "$SESSION" ]; then
  [ "${#metadata_matches[@]}" -eq 1 ] || {
    echo "PM_CLEANUP_METADATA_AMBIGUOUS: matches=${#metadata_matches[@]} project=${PROJECT:-missing} session=${SESSION:-missing}" >&2
    exit 2
  }
  [ -n "$PROJECT" ] || PROJECT=$(jq -r '.project // empty' "${metadata_matches[0]}")
  [ -n "$SESSION" ] || SESSION=$(jq -r '.session.id // empty' "${metadata_matches[0]}")
fi
[ -n "$PROJECT" ] && [ -n "$SESSION" ] || { echo "PM_CLEANUP_IDENTITY_MISSING" >&2; exit 2; }

# Lifecycle and PR base are persisted at spawn time so cleanup does not depend
# on the PM remembering which branches are disposable.  An explicit long-lived
# value may conservatively upgrade legacy/ephemeral metadata, but a persisted
# long-lived value can never be downgraded by the cleanup caller.
metadata_lifecycle=""
metadata_base_ref=""
if [ "${#metadata_matches[@]}" -eq 1 ]; then
  metadata_lifecycle=$(jq -r '.branch_lifecycle // empty' "${metadata_matches[0]}")
  metadata_base_ref=$(jq -r '.base_ref // empty' "${metadata_matches[0]}")
fi
case "$metadata_lifecycle" in ""|ephemeral-worker|long-lived) ;; *) echo "PM_CLEANUP_METADATA_LIFECYCLE_INVALID: $metadata_lifecycle" >&2; exit 2 ;; esac
if [ "$metadata_lifecycle" = "long-lived" ] && [ "$BRANCH_LIFECYCLE" = "ephemeral-worker" ]; then
  echo "PM_CLEANUP_LIFECYCLE_MISMATCH: argument=$BRANCH_LIFECYCLE metadata=$metadata_lifecycle" >&2
  exit 2
fi
[ -n "$BRANCH_LIFECYCLE" ] || BRANCH_LIFECYCLE=${metadata_lifecycle:-ephemeral-worker}
case "$BRANCH_LIFECYCLE" in ephemeral-worker|long-lived) ;; *) echo "PM_CLEANUP_LIFECYCLE_INVALID: $BRANCH_LIFECYCLE" >&2; exit 64 ;; esac

normalize_target() {
  local value=$1
  value=${value#refs/remotes/}
  value=${value#refs/heads/}
  case "$value" in "$REMOTE"/*) value=${value#"$REMOTE"/} ;; esac
  git check-ref-format --branch "$value" >/dev/null 2>&1 || return 1
  printf '%s\n' "$value"
}
metadata_target=""
if [ -n "$metadata_base_ref" ]; then
  metadata_target=$(normalize_target "$metadata_base_ref") || {
    echo "PM_CLEANUP_METADATA_BASE_INVALID: $metadata_base_ref" >&2
    exit 2
  }
fi
if [ -n "$INTEGRATION_TARGET" ]; then
  INTEGRATION_TARGET=$(normalize_target "$INTEGRATION_TARGET") || { echo "PM_CLEANUP_INTEGRATION_TARGET_INVALID" >&2; exit 64; }
fi
if [ -n "$INTEGRATION_TARGET" ] && [ -n "$metadata_target" ] && [ "$INTEGRATION_TARGET" != "$metadata_target" ]; then
  echo "PM_CLEANUP_INTEGRATION_TARGET_MISMATCH: argument=$INTEGRATION_TARGET metadata=$metadata_target" >&2
  exit 2
fi
[ -n "$INTEGRATION_TARGET" ] || INTEGRATION_TARGET=${metadata_target:-main}

PROJECT=$(cd "$PROJECT" && pwd -P) || { echo "PM_CLEANUP_PROJECT_MISSING" >&2; exit 2; }

project_common=$(git -C "$PROJECT" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)
worker_common=$(git -C "$WORKTREE" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)
[ -n "$project_common" ] && [ "$project_common" = "$worker_common" ] || {
  echo "PM_CLEANUP_REPOSITORY_MISMATCH" >&2
  exit 2
}
[ "$(git -C "$WORKTREE" branch --show-current)" = "$BRANCH" ] || {
  echo "PM_CLEANUP_BRANCH_MISMATCH" >&2
  exit 2
}
actual_tip=$(git -C "$WORKTREE" rev-parse 'HEAD^{commit}')
[ "$actual_tip" = "$EXPECTED_TIP" ] || {
  echo "PM_CLEANUP_TIP_MISMATCH: expected=$EXPECTED_TIP actual=$actual_tip" >&2
  exit 2
}
[ -z "$(git -C "$WORKTREE" status --porcelain)" ] || {
  echo "PM_CLEANUP_DIRTY: retain worktree and branches" >&2
  exit 2
}

# Long-lived feature/integration baselines are not worker cleanup targets.  The
# default branch names remain protected even if legacy metadata is missing.
case "$BRANCH" in main|master|trunk) BRANCH_LIFECYCLE="long-lived" ;; esac
if [ "$BRANCH" = "$INTEGRATION_TARGET" ]; then
  BRANCH_LIFECYCLE="long-lived"
fi
if [ "$BRANCH_LIFECYCLE" = "long-lived" ]; then
  echo "PM_CLEANUP_MODE: $([ "$EXECUTE" -eq 1 ] && echo execute || echo dry-run)"
  echo "PM_CLEANUP_TARGET: branch=$BRANCH tip=$EXPECTED_TIP worktree=$WORKTREE session=$SESSION lifecycle=$BRANCH_LIFECYCLE integration_target=$INTEGRATION_TARGET"
  echo "PM_CLEANUP_RESULT: RETAINED_WITH_REASON remote=retained worktree=retained local=retained reason=long-lived-branch"
  exit 11
fi

remote_url=$(git -C "$PROJECT" remote get-url "$REMOTE" 2>/dev/null || true)
[ -n "$remote_url" ] || { echo "PM_CLEANUP_REMOTE_MISSING: $REMOTE" >&2; exit 2; }
repo_slug="$REPOSITORY"
if [ -z "$repo_slug" ]; then
  repo_slug=$(printf '%s' "$remote_url" | sed -nE \
    's#^(https?://|ssh://git@|git@)([^/:]+)[:/]([^/]+/[^/]+?)(\.git)?$#\2/\3#p')
  repo_slug=${repo_slug%.git}
fi
[[ "$repo_slug" =~ ^[^/[:space:]]+/[^/[:space:]]+/[^/[:space:]]+$ ]] || repo_slug=""
[ -n "$repo_slug" ] || { echo "PM_CLEANUP_REMOTE_IDENTITY_UNKNOWN" >&2; exit 2; }

pr_json=$(gh pr view "$PR_NUMBER" --repo "$repo_slug" \
  --json state,mergedAt,baseRefName,headRefName,headRefOid,mergeCommit 2>/dev/null) || {
    echo "PM_CLEANUP_PR_FACTS_UNKNOWN" >&2
    exit 2
  }
pr_head=$(printf '%s' "$pr_json" | jq -r '.headRefName // empty')
pr_head_oid=$(printf '%s' "$pr_json" | jq -r '.headRefOid // empty')
pr_base=$(printf '%s' "$pr_json" | jq -r '.baseRefName // empty')
pr_state=$(printf '%s' "$pr_json" | jq -r '.state // empty')
[ "$pr_head" = "$BRANCH" ] && [ "$pr_head_oid" = "$EXPECTED_TIP" ] || {
  echo "PM_CLEANUP_PR_HEAD_MISMATCH: branch=$pr_head head=$pr_head_oid" >&2
  exit 2
}
[ "$pr_base" = "$INTEGRATION_TARGET" ] || {
  echo "PM_CLEANUP_PR_BASE_MISMATCH: expected=$INTEGRATION_TARGET actual=${pr_base:-missing}" >&2
  exit 2
}
if [ "$DELIVERY_MODE" = "remote-pr" ]; then
  pr_merged_at=$(printf '%s' "$pr_json" | jq -r '.mergedAt // empty')
  pr_merge_commit=$(printf '%s' "$pr_json" | jq -r '.mergeCommit.oid // empty')
  [ "$pr_state" = "MERGED" ] && [ -n "$pr_merged_at" ] && \
    [ "$pr_merge_commit" = "$DELIVERY_COMMIT" ] || {
      echo "PM_CLEANUP_DELIVERY_NOT_PROVEN: mode=remote-pr state=$pr_state merge=$pr_merge_commit" >&2
      exit 2
    }
else
  case "$pr_state" in
    OPEN|CLOSED|MERGED) ;;
    *)
      echo "PM_CLEANUP_PR_STATE_UNKNOWN: state=${pr_state:-missing}" >&2
      exit 2
      ;;
  esac
  git -C "$PROJECT" fetch "$REMOTE" "$INTEGRATION_TARGET" --quiet || {
    echo "PM_CLEANUP_DELIVERY_FETCH_FAILED" >&2
    exit 2
  }
  git -C "$PROJECT" cat-file -e "$DELIVERY_COMMIT^{commit}" 2>/dev/null && \
    git -C "$PROJECT" merge-base --is-ancestor "$DELIVERY_COMMIT" "$REMOTE/$INTEGRATION_TARGET" || {
      echo "PM_CLEANUP_DELIVERY_NOT_PROVEN: mode=local-after-pr commit=$DELIVERY_COMMIT" >&2
      exit 2
    }
fi

echo "PM_CLEANUP_MODE: $([ "$EXECUTE" -eq 1 ] && echo execute || echo dry-run)"
echo "PM_CLEANUP_TARGET: repo=$repo_slug pr=$PR_NUMBER branch=$BRANCH tip=$EXPECTED_TIP worktree=$WORKTREE session=$SESSION lifecycle=$BRANCH_LIFECYCLE integration_target=$INTEGRATION_TARGET"

query_remote_branch() {
  set +e
  remote_query_output=$(git -C "$PROJECT" ls-remote --heads "$REMOTE" "refs/heads/$BRANCH" 2>/dev/null)
  remote_query_rc=$?
  set -e
  if [ "$remote_query_rc" -ne 0 ]; then
    echo "PM_CLEANUP_REMOTE_QUERY_FAILED: remote=$REMOTE branch=$BRANCH" >&2
    return 1
  fi
  return 0
}

remote_state="absent"
query_remote_branch || exit 2
remote_row=$remote_query_output
if [ -n "$remote_row" ]; then
  remote_tip=${remote_row%%[[:space:]]*}
  [ "$remote_tip" = "$EXPECTED_TIP" ] || {
    echo "PM_CLEANUP_REMOTE_TIP_MISMATCH: expected=$EXPECTED_TIP actual=$remote_tip" >&2
    exit 2
  }
  if [ "$DELIVERY_MODE" = "local-after-pr" ] && [ "$pr_state" = "OPEN" ]; then
    # Local integration may intentionally leave the PR open when close authority
    # is absent.  Local ephemeral resources can still be reclaimed, but deleting
    # the remote head would mutate that live PR unexpectedly.
    remote_state="retained-open-pr"
  else
    remote_state="planned-delete"
  fi
  if [ "$EXECUTE" -eq 1 ] && [ "$remote_state" = "planned-delete" ]; then
    push_rc=0
    git -C "$PROJECT" push "$REMOTE" --delete "$BRANCH" >/dev/null 2>&1 || push_rc=$?
    if query_remote_branch && [ -z "$remote_query_output" ]; then
      remote_state="deleted"
    else
      remote_state="pending"
      echo "PM_CLEANUP_REMOTE_DELETE_PENDING: branch=$BRANCH push_rc=$push_rc" >&2
    fi
  fi
fi

clean_args=(--project "$PROJECT" --branch "$BRANCH" --session "$SESSION" --worktree "$WORKTREE")
[ "$EXECUTE" -eq 0 ] || clean_args+=(--execute)
if ! bash "$CLEAN_SCRIPT" "${clean_args[@]}"; then
  echo "PM_CLEANUP_RESULT: CLEANUP_PENDING remote=$remote_state worktree=retained local=retained reason=clean-worktree-refused" >&2
  exit 2
fi
if [ "$EXECUTE" -eq 0 ]; then
  echo "PM_CLEANUP_RESULT: DRY_RUN remote=$remote_state worktree=planned-remove local=planned-delete"
  exit 0
fi

if [ -d "$WORKTREE" ]; then
  echo "PM_CLEANUP_RESULT: CLEANUP_PENDING remote=$remote_state worktree=present local=retained reason=worktree-still-present" >&2
  exit 2
fi
if git -C "$PROJECT" worktree list --porcelain | grep -Fxq "branch refs/heads/$BRANCH"; then
  echo "PM_CLEANUP_RESULT: CLEANUP_PENDING remote=$remote_state worktree=registered local=retained reason=branch-still-checked-out" >&2
  exit 2
fi
if git -C "$PROJECT" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  local_tip=$(git -C "$PROJECT" rev-parse "refs/heads/$BRANCH^{commit}")
  [ "$local_tip" = "$EXPECTED_TIP" ] || {
    echo "PM_CLEANUP_RESULT: CLEANUP_PENDING remote=$remote_state worktree=removed local=retained reason=local-tip-drift" >&2
    exit 2
  }
  git -C "$PROJECT" update-ref -d "refs/heads/$BRANCH" "$EXPECTED_TIP"
fi
if git -C "$PROJECT" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  echo "PM_CLEANUP_RESULT: CLEANUP_PENDING remote=$remote_state worktree=removed local=present reason=local-delete-failed" >&2
  exit 2
fi

if [ "$remote_state" = "pending" ]; then
  echo "PM_CLEANUP_RESULT: CLEANUP_PENDING remote=pending worktree=removed local=deleted reason=remote-delete-failed" >&2
  exit 10
fi
if [ "$remote_state" = "retained-open-pr" ]; then
  echo "PM_CLEANUP_RESULT: RETAINED_WITH_REASON remote=retained-open-pr worktree=removed local=deleted reason=pr-still-open"
  exit 11
fi
echo "PM_CLEANUP_RESULT: CLEANED remote=$remote_state worktree=removed local=deleted"
