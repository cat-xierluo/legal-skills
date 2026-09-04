#!/usr/bin/env bash
# post-merge-cleanup.sh — fail-closed post-merge cleanup gate for ONE merged worker branch.
#
# 职责边界（与 git-workflow 分工）：删除资格真值来自 git-workflow 的分支清理规则
# （PR state == MERGED、精确 head 一致、无 stacked child、worktree 干净、非长期集成/
# 默认分支）；本脚本是 multi-agent-orchestration 的生命周期执行者：先经
# clean-worktree.sh 释放 terminal/lease/worktree/本地分支，再删除远端短分支，最后
# 机械验证零残留。任何门禁不确定或失败都输出 deferred-cleanup 理由并保持现场不动。
#
# 即时清理是「已合并且无消费者」的显式例外：只处理显式传入的单个分支，绝不批量
# 扫描；git-workflow 的 <24h 保留规则继续保护没有 MERGED 证据的对象——无 MERGED
# 证据一律 deferred，与分支年龄无关。远端删除失败或残留验证不过以 exit 9 报告，
# 绝不把部分成功冒充为完成。

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=orca-runtime.sh
source "$SCRIPT_DIR/orca-runtime.sh"

PROJECT_DIR=""
BRANCH=""
SESSION=""
WORKTREE=""
BASE_REF="main"
EXECUTE=0
KEEP_REMOTE=0
REPO_SLUG=""
PROTECTED_PATTERNS=()

usage() {
  cat >&2 <<'USAGE'
Usage:
  post-merge-cleanup.sh --project PATH --branch NAME --session NAME [options]

Default is dry-run: every gate is evaluated read-only and the plan is printed.

Options:
  --worktree PATH        Override worktree path if branch lookup is unavailable
  --base REF             Base ref the worker PR merged into (default main)
  --repo SLUG            OWNER/REPO passed to gh; default: gh infers from project remote
  --protected-branch PAT Long-lived/protected branch name or glob; repeatable
  --keep-remote          Do not delete the remote branch
  --execute              Perform the cleanup (still fail-closed on every gate)

Gates (all must hold; the first miss prints POST_MERGE_CLEANUP_DEFERRED and exits 2):
  - branch is not main/master/develop, the --base ref, or a --protected-branch pattern
  - exactly one MERGED PR exists for the branch and its headRefOid equals the local
    branch tip (a moved or unknown head is an identity mismatch, never cleaned)
  - no open PR uses the branch as its base (stacked child consumer)
  - the worktree, when present and registered, is clean
  - the session lifecycle is provably settled: no alive unaccounted tmux session, and
    any supervised dispatch reads released/retained — never active/release_pending

With --execute the deletions run in lifecycle order via clean-worktree.sh
(terminal/lease/worktree/local branch; squash-safe delete escalation only after the
MERGED gate above), then the remote branch, then a mechanical zero-residue
verification. Remote deletion failure or leftover state exits 9 and never reports
success. This script never deletes a remote branch in dry-run and never runs
git reset or git worktree remove --force.
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
    --base)
      BASE_REF="$2"
      shift 2
      ;;
    --repo)
      REPO_SLUG="$2"
      shift 2
      ;;
    --protected-branch)
      PROTECTED_PATTERNS+=("$2")
      shift 2
      ;;
    --keep-remote)
      KEEP_REMOTE=1
      shift
      ;;
    --execute)
      EXECUTE=1
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
[ -n "$BASE_REF" ] || { usage; exit 64; }
for dependency in git jq gh; do
  command -v "$dependency" >/dev/null 2>&1 || { echo "POST_MERGE_CLEANUP_DEPENDENCY_MISSING: $dependency" >&2; exit 64; }
done

PROJECT_DIR=$(cd "$PROJECT_DIR" && pwd -P)
case "$WORKTREE" in
  "") ;;
  /*) ;;
  *) WORKTREE="$PROJECT_DIR/$WORKTREE" ;;
esac

defer() {
  echo "POST_MERGE_CLEANUP_DEFERRED: reason=$1${2:+ detail=$2}" >&2
  exit 2
}

# exact-match against `git worktree list --porcelain` output (no substring hits).
worktree_listed() {
  [ -n "$1" ] || return 1
  git -C "$PROJECT_DIR" worktree list --porcelain 2>/dev/null | \
    awk -v wt="$1" '/^worktree / { if (substr($0, 10) == wt) { found = 1 } } END { exit !found }'
}

gh_pr_list() {
  local state="$1"
  shift
  if [ -n "$REPO_SLUG" ]; then
    (cd "$PROJECT_DIR" && gh pr list --state "$state" "$@" --repo "$REPO_SLUG" \
      --json number,url,state,headRefName,headRefOid --limit 50 2>/dev/null)
  else
    (cd "$PROJECT_DIR" && gh pr list --state "$state" "$@" \
      --json number,url,state,headRefName,headRefOid --limit 50 2>/dev/null)
  fi
}

echo "POST_MERGE_CLEANUP_MODE: $([ "$EXECUTE" -eq 1 ] && echo execute || echo dry-run)"
echo "POST_MERGE_CLEANUP_TARGET: branch=$BRANCH session=$SESSION base=$BASE_REF worktree=${WORKTREE:-auto}"

# ---- Gate 1: 删除资格真值（git-workflow）——默认/长期集成分支永不删除 -------------
case "$BRANCH" in
  main|master|develop|"$BASE_REF")
    defer "protected_branch" "branch=$BRANCH is a default/integration trunk"
    ;;
esac
if [ "${#PROTECTED_PATTERNS[@]}" -gt 0 ]; then
  for pattern in "${PROTECTED_PATTERNS[@]}"; do
    # shellcheck disable=SC2254  # pattern matching on purpose
    case "$BRANCH" in
      $pattern) defer "protected_branch" "branch=$BRANCH matches protected pattern=$pattern" ;;
    esac
  done
fi
echo "POST_MERGE_CLEANUP_PROTECTED: clear branch=$BRANCH"

# ---- Gate 2: MERGED 证据 + 精确 head 一致（squash/rebase merge 的唯一权威证据）----
BRANCH_TIP=$(git -C "$PROJECT_DIR" rev-parse --verify --quiet "refs/heads/$BRANCH" 2>/dev/null || true)
[ -n "$BRANCH_TIP" ] || defer "branch_missing_local" "refs/heads/$BRANCH is not resolvable; remote-only residue needs manual review"
echo "POST_MERGE_CLEANUP_BRANCH_TIP: $BRANCH_TIP"

set +e
MERGED_JSON=$(gh_pr_list merged --head "$BRANCH")
GH_MERGED_RC=$?
set -e
[ "$GH_MERGED_RC" -eq 0 ] || defer "pr_evidence_unavailable" "gh pr list --state merged exited $GH_MERGED_RC"
printf '%s' "$MERGED_JSON" | jq -e 'type == "array"' >/dev/null 2>&1 || \
  defer "pr_evidence_unavailable" "gh pr list --state merged did not return a JSON array"

MERGED_FOR_BRANCH=$(printf '%s' "$MERGED_JSON" | jq -c --arg br "$BRANCH" \
  '[.[] | select(.state == "MERGED" and .headRefName == $br)]')
MERGED_COUNT=$(printf '%s' "$MERGED_FOR_BRANCH" | jq 'length')
if [ "$MERGED_COUNT" -eq 0 ]; then
  defer "no_merged_pr_evidence" "no MERGED PR for head=$BRANCH; <24h and unknown branches stay protected"
fi
MERGED_AT_TIP=$(printf '%s' "$MERGED_FOR_BRANCH" | jq -c --arg tip "$BRANCH_TIP" '[.[] | select(.headRefOid == $tip)]')
TIP_COUNT=$(printf '%s' "$MERGED_AT_TIP" | jq 'length')
if [ "$TIP_COUNT" -ne 1 ]; then
  pr_head_oids=$(printf '%s' "$MERGED_FOR_BRANCH" | jq -c '[.[].headRefOid]')
  defer "head_mismatch" "merged_pr_oids=$pr_head_oids local_tip=$BRANCH_TIP; branch identity is uncertain after merge"
fi
PR_NUMBER=$(printf '%s' "$MERGED_AT_TIP" | jq -r '.[0].number | tostring')
PR_URL=$(printf '%s' "$MERGED_AT_TIP" | jq -r '.[0].url // ""')
echo "POST_MERGE_CLEANUP_MERGED_PR: number=$PR_NUMBER url=$PR_URL head=$BRANCH_TIP"

# ---- Gate 3: 无 stacked child 消费者（开放 PR 以该分支为 base）--------------------
set +e
CHILD_JSON=$(gh_pr_list open --base "$BRANCH")
GH_CHILD_RC=$?
set -e
[ "$GH_CHILD_RC" -eq 0 ] || defer "child_pr_query_unavailable" "gh pr list --state open --base exited $GH_CHILD_RC"
printf '%s' "$CHILD_JSON" | jq -e 'type == "array"' >/dev/null 2>&1 || \
  defer "child_pr_query_unavailable" "gh pr list --state open did not return a JSON array"
CHILD_COUNT=$(printf '%s' "$CHILD_JSON" | jq 'length')
[ "$CHILD_COUNT" -eq 0 ] || \
  defer "open_child_pr" "children=$(printf '%s' "$CHILD_JSON" | jq -c '[.[].number]') use $BRANCH as base"
echo "POST_MERGE_CLEANUP_CHILD_PRS: zero"

# ---- Gate 4: worktree 干净（未提交工作永不清）------------------------------------
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

WORKTREE_LISTED=0
WORKTREE_PRESENT=0
if worktree_listed "$WORKTREE"; then
  WORKTREE_LISTED=1
fi
if [ -n "$WORKTREE" ] && [ -d "$WORKTREE" ]; then
  WORKTREE_PRESENT=1
fi
if [ "$WORKTREE_LISTED" -eq 1 ] && [ "$WORKTREE_PRESENT" -eq 0 ]; then
  defer "worktree_stale_registration" "worktree=$WORKTREE is registered but missing on disk; run git worktree prune manually first"
fi
if [ "$WORKTREE_PRESENT" -eq 1 ]; then
  [ "$WORKTREE" != "$PROJECT_DIR" ] || defer "worktree_is_project_dir" "refusing to treat the project directory as a worker worktree"
  dirty_count=$(git -C "$WORKTREE" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
  [ "$dirty_count" = "0" ] || defer "dirty_worktree" "worktree=$WORKTREE has $dirty_count uncommitted changes"
  echo "POST_MERGE_CLEANUP_WORKTREE: present path=$WORKTREE dirty=0"
else
  echo "POST_MERGE_CLEANUP_WORKTREE: missing path=${WORKTREE:-unresolved}"
fi

# ---- Gate 5: session 生命周期可证结算（active/release_pending 一律拒绝）----------
METADATA_FILE=""
DISPATCH_ID=""
if [ "$WORKTREE_PRESENT" -eq 1 ]; then
  METADATA_FILE="$WORKTREE/.claude/agent-sessions/$SESSION/METADATA.json"
  [ -f "$METADATA_FILE" ] || defer "session_metadata_missing" "file=$METADATA_FILE; orchestration workers always carry METADATA"
  jq -e 'type == "object"' "$METADATA_FILE" >/dev/null 2>&1 || \
    defer "session_metadata_invalid" "file=$METADATA_FILE; retain for recovery"
  DISPATCH_ID=$(jq -r '.session.orca.supervised.dispatch_id // ""' "$METADATA_FILE" 2>/dev/null || echo "")
fi

TMUX_ALIVE=0
if command -v tmux >/dev/null 2>&1 && tmux has-session -t "$SESSION" 2>/dev/null; then
  TMUX_ALIVE=1
fi
if [ "$TMUX_ALIVE" -eq 1 ] && [ -z "$DISPATCH_ID" ]; then
  defer "tmux_session_alive_unaccounted" "session=$SESSION is alive without supervised dispatch to prove settlement"
fi

TERMINAL_STATE="no-dispatch"
if [ -n "$DISPATCH_ID" ]; then
  if orca_runtime_init >/dev/null 2>&1; then
    worker_json=$(orca_cli orchestration worker-list --json 2>/dev/null || echo '{}')
    worker_row=$(printf '%s' "$worker_json" | jq -c --arg disp "$DISPATCH_ID" '
      [(.result.workers // [])[]? | select((.dispatch_id // .dispatchId // .id) == $disp)][0] // {}' 2>/dev/null || echo '{}')
    TERMINAL_STATE=$(printf '%s' "$worker_row" | jq -r '.terminal_state // .terminalState // .accounting_state // .accountingState // "unknown"' 2>/dev/null || echo "unknown")
    [ -n "$TERMINAL_STATE" ] || TERMINAL_STATE="unknown"
    case "$TERMINAL_STATE" in
      released|retained)
        # retained 的 external 所有权证明由 clean-worktree.sh 在 execute 时权威复核。
        ;;
      active|reclaimable|release_pending|release_unknown)
        defer "terminal_accounting_$TERMINAL_STATE" "dispatch=$DISPATCH_ID; settle the worker first"
        ;;
      *)
        defer "terminal_accounting_unknown" "dispatch=$DISPATCH_ID state=$TERMINAL_STATE; recover exact worker-release first"
        ;;
    esac
  else
    defer "orca_cli_unavailable" "dispatch=$DISPATCH_ID cannot be accounted; lifecycle unknown"
  fi
fi
echo "POST_MERGE_CLEANUP_LIFECYCLE: dispatch=${DISPATCH_ID:-none} terminal=$TERMINAL_STATE tmux=$([ "$TMUX_ALIVE" -eq 1 ] && echo alive || echo absent)"

# ---- 远端分支现状（只读）；任何模式都要求可验证，否则拒绝继续 --------------------
set +e
LS_REMOTE_OUT=$(git -C "$PROJECT_DIR" ls-remote --heads origin "refs/heads/$BRANCH" 2>/dev/null)
LS_RC=$?
set -e
if [ "$LS_RC" -ne 0 ]; then
  # 发生在任何 mutation 之前：这是可恢复的拒绝，不是 outcome-unknown。
  defer "remote_state_unverifiable" "git ls-remote origin exited $LS_RC; refusing an unverifiable cleanup"
fi
if [ -n "$LS_REMOTE_OUT" ]; then
  REMOTE_STATE="present"
else
  REMOTE_STATE="absent"
fi
echo "POST_MERGE_CLEANUP_REMOTE_STATE: branch=$BRANCH state=$REMOTE_STATE"

# ---- 执行：生命周期顺序 = release/terminal/lease → worktree/本地分支 → 远端 → 残留 --
if [ "$EXECUTE" -eq 1 ]; then
  # 删除前的最后身份复核：门禁通过后分支不得再移动。
  now_tip=$(git -C "$PROJECT_DIR" rev-parse --verify --quiet "refs/heads/$BRANCH" 2>/dev/null || true)
  [ "$now_tip" = "$BRANCH_TIP" ] || defer "head_mismatch" "branch advanced during cleanup: expected=$BRANCH_TIP actual=${now_tip:-missing}"

  CW_ARGS=(--project "$PROJECT_DIR" --branch "$BRANCH" --session "$SESSION" --execute --delete-branch --force-delete-branch)
  if [ -n "$WORKTREE" ]; then
    CW_ARGS+=(--worktree "$WORKTREE")
  fi
  set +e
  bash "$SCRIPT_DIR/clean-worktree.sh" "${CW_ARGS[@]}"
  CW_RC=$?
  set -e
  if [ "$CW_RC" -ne 0 ]; then
    echo "POST_MERGE_CLEANUP_DEFERRED: reason=clean_worktree_refused detail=clean-worktree.sh exit=$CW_RC" >&2
    exit 2
  fi

  REMOTE_OUTCOME="$REMOTE_STATE"
  if [ "$KEEP_REMOTE" -eq 1 ]; then
    echo "POST_MERGE_CLEANUP_REMOTE: kept branch=$BRANCH"
    REMOTE_OUTCOME="kept"
  elif [ "$REMOTE_STATE" = "present" ]; then
    set +e
    git -C "$PROJECT_DIR" push origin --delete "refs/heads/$BRANCH"
    PUSH_RC=$?
    set -e
    if [ "$PUSH_RC" -ne 0 ]; then
      # 与 clean-worktree.sh 的 terminal close race 同理：push 报错但远端实际已删
      # （并发清理 / GitHub auto-delete）时，用 follow-up ls-remote 证明后幂等放行。
      set +e
      LS_RACE=$(git -C "$PROJECT_DIR" ls-remote --heads origin "refs/heads/$BRANCH" 2>/dev/null)
      LS_RACE_RC=$?
      set -e
      if [ "$LS_RACE_RC" -eq 0 ] && [ -z "$LS_RACE" ]; then
        echo "POST_MERGE_CLEANUP_REMOTE_ALREADY_ABSENT: branch=$BRANCH reason=delete_race_verified"
        REMOTE_OUTCOME="absent"
      else
        echo "POST_MERGE_CLEANUP_REMOTE_DELETE_FAILED: branch=$BRANCH detail=local cleanup already applied; inspect remote state before retrying" >&2
        exit 9
      fi
    else
      echo "POST_MERGE_CLEANUP_REMOTE_DELETED: branch=$BRANCH"
      REMOTE_OUTCOME="deleted"
    fi
  else
    echo "POST_MERGE_CLEANUP_REMOTE_ALREADY_ABSENT: branch=$BRANCH"
    REMOTE_OUTCOME="absent"
  fi

  # ---- 机械零残留验证：任何残留都否定完成 --------------------------------------
  residue=0
  if git -C "$PROJECT_DIR" show-ref --verify --quiet "refs/heads/$BRANCH"; then
    echo "POST_MERGE_CLEANUP_RESIDUE: kind=local_branch branch=$BRANCH" >&2
    residue=1
  fi
  if [ "$WORKTREE_LISTED" -eq 1 ] && worktree_listed "$WORKTREE"; then
    echo "POST_MERGE_CLEANUP_RESIDUE: kind=worktree_registration path=$WORKTREE" >&2
    residue=1
  fi
  if [ "$WORKTREE_PRESENT" -eq 1 ] && [ -e "$WORKTREE" ]; then
    echo "POST_MERGE_CLEANUP_RESIDUE: kind=worktree_dir path=$WORKTREE" >&2
    residue=1
  fi
  if command -v tmux >/dev/null 2>&1 && tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "POST_MERGE_CLEANUP_RESIDUE: kind=tmux_session session=$SESSION" >&2
    residue=1
  fi
  if [ "$KEEP_REMOTE" -eq 0 ]; then
    set +e
    LS_AFTER=$(git -C "$PROJECT_DIR" ls-remote --heads origin "refs/heads/$BRANCH" 2>/dev/null)
    LS_AFTER_RC=$?
    set -e
    if [ "$LS_AFTER_RC" -ne 0 ]; then
      echo "POST_MERGE_CLEANUP_RESIDUE_UNVERIFIED: kind=remote_branch reason=ls_remote_failed exit=$LS_AFTER_RC" >&2
      exit 9
    fi
    if [ -n "$LS_AFTER" ]; then
      echo "POST_MERGE_CLEANUP_RESIDUE: kind=remote_branch branch=$BRANCH still visible on origin" >&2
      residue=1
    fi
  fi
  if [ "$residue" -ne 0 ]; then
    echo "POST_MERGE_CLEANUP_RESIDUE_DETECTED: cleanup is incomplete; do not report this branch as settled" >&2
    exit 9
  fi
  echo "POST_MERGE_CLEANUP_RESIDUE_VERIFIED: zero"
  echo "POST_MERGE_CLEANUP_DONE"
  echo "POST_MERGE_CLEANUP_RESULT: CLEANED pr=$PR_NUMBER branch=$BRANCH worktree=$([ "$WORKTREE_PRESENT" -eq 1 ] && echo removed || echo absent) local_branch=deleted remote_branch=$REMOTE_OUTCOME residue=zero"
  exit 0
fi

# ---- dry-run：输出计划，零副作用 --------------------------------------------------
if [ "$KEEP_REMOTE" -eq 1 ]; then
  REMOTE_PLAN="keep"
elif [ "$REMOTE_STATE" = "present" ]; then
  REMOTE_PLAN="delete"
else
  REMOTE_PLAN="already-absent"
fi
echo "POST_MERGE_CLEANUP_PLAN: clean-worktree.sh --execute --delete-branch (terminal/lease → worktree → local branch) then remote branch $REMOTE_PLAN then zero-residue verification"
echo "POST_MERGE_CLEANUP_DRY_RUN_DONE"
echo "POST_MERGE_CLEANUP_RESULT: PLAN pr=$PR_NUMBER branch=$BRANCH worktree=$([ "$WORKTREE_PRESENT" -eq 1 ] && echo remove || echo absent) local_branch=delete remote_branch=$REMOTE_PLAN residue=verify-after-execute"
exit 0
