#!/bin/bash
# pm-closeout.sh — PM 收口管道：sync-merge→解冲突(安全模式)→门禁→safe-push→PR create/merge(编号机械提取)→验证→清分支
# 用法: pm-closeout.sh --worktree <path> --title <t> --safe-push-script <path>
#       --verify-cmd <executable> [--verify-arg <arg> ...] [--body-file <f>] [--keep-branch]
# 铁律: PR 编号只从 gh pr create 的返回 URL 提取；分支删除只在 state==MERGED 之后。
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SP="${PM_CLOSEOUT_SAFE_PUSH:-}"
GIT_NAME="${EXPECTED_GIT_NAME:-}"; GIT_EMAIL="${EXPECTED_GIT_EMAIL:-}"
WT=""; TITLE=""; BODY_FILE=""; VERIFY_BIN=""; KEEP_BRANCH=0; TMP_BODY=""
WORKER_BASE=""; WORKER_TIP=""; START_MAIN=""; STABLE_MAIN=""; SYNC_STABLE=0
VERIFY_ARGS=()

cleanup_temp() {
  if [ -n "$TMP_BODY" ] && [ -f "$TMP_BODY" ]; then
    rm -f -- "$TMP_BODY"
  fi
}
trap cleanup_temp EXIT

while [ $# -gt 0 ]; do case $1 in
  --worktree) WT="$2"; shift 2 ;;
  --title) TITLE="$2"; shift 2 ;;
  --body-file) BODY_FILE="$2"; shift 2 ;;
  --safe-push-script) SP="$2"; shift 2 ;;
  --verify-cmd) VERIFY_BIN="$2"; shift 2 ;;
  --verify-arg) VERIFY_ARGS+=("$2"); shift 2 ;;
  --verify) echo "PM_CLOSEOUT_USAGE: --verify 字符串已停用；改用 --verify-cmd + --verify-arg，禁止 shell 字符串执行" >&2; exit 64 ;;
  --keep-branch) KEEP_BRANCH=1; shift ;;
  *) echo "PM_CLOSEOUT_USAGE: 未知参数 $1" >&2; exit 64 ;;
esac; done
[ -n "$WT" ] && [ -n "$TITLE" ] || { echo "PM_CLOSEOUT_USAGE: 需要 --worktree 与 --title" >&2; exit 64; }
[ -n "$SP" ] && [ -f "$SP" ] && [ ! -L "$SP" ] || {
  echo "PM_CLOSEOUT_NO_SAFE_PUSH: 需要 --safe-push-script 指向已审查的 git-workflow safe-push.sh（或设置 PM_CLOSEOUT_SAFE_PUSH）" >&2
  exit 7
}
SP="$(cd "$(dirname "$SP")" && pwd -P)/$(basename "$SP")"
[ -n "$VERIFY_BIN" ] || {
  echo "PM_CLOSEOUT_VERIFY_REQUIRED: 需要 --verify-cmd；多步门禁请封装为仓库内可执行脚本" >&2
  exit 64
}
for dependency in git jq gh python3; do
  command -v "$dependency" >/dev/null 2>&1 || {
    echo "PM_CLOSEOUT_DEPENDENCY_MISSING: $dependency" >&2
    exit 64
  }
done
cd "$WT"
BR=$(git branch --show-current)
[ -n "$BR" ] || { echo "PM_CLOSEOUT_DETACHED_HEAD: 必须在具名分支收口" >&2; exit 2; }
[ -n "$GIT_NAME" ] || GIT_NAME=$(git config user.name || true)
[ -n "$GIT_EMAIL" ] || GIT_EMAIL=$(git config user.email || true)
[ -n "$GIT_NAME" ] && [ -n "$GIT_EMAIL" ] || {
  echo "PM_CLOSEOUT_GIT_IDENTITY_REQUIRED: 设置仓库 git user.name/user.email 或 EXPECTED_GIT_NAME/EXPECTED_GIT_EMAIL" >&2
  exit 7
}
echo "PM_CLOSEOUT_BRANCH: $BR"

# 1) 未提交改动检查(fail-closed)
if [ -n "$(git status --porcelain)" ]; then echo "PM_CLOSEOUT_DIRTY: 工作树有未提交改动,先处理" >&2; exit 2; fi

# 2) 冻结 worker 贡献范围；每次 main 前移后都重新合并并重跑门禁。
git fetch origin --quiet
WORKER_TIP=$(git rev-parse --verify 'HEAD^{commit}')
START_MAIN=$(git rev-parse --verify 'origin/main^{commit}')
WORKER_BASE=$(git merge-base "$WORKER_TIP" "$START_MAIN")
[ -n "$WORKER_BASE" ] && git merge-base --is-ancestor "$WORKER_BASE" "$WORKER_TIP" || {
  echo "PM_CLOSEOUT_WORKER_RANGE_INVALID: base=$WORKER_BASE tip=$WORKER_TIP main=$START_MAIN" >&2
  exit 3
}
echo "PM_CLOSEOUT_WORKER_RANGE: base=$WORKER_BASE tip=$WORKER_TIP start_main=$START_MAIN"

resolve_conflicts() {
  local message=$1
  local main_commit=$2
  python3 "$SKILL_DIR/scripts/pm-closeout-resolve.py" \
    --worker-base "$WORKER_BASE" --worker-tip "$WORKER_TIP" \
    --main-commit "$main_commit"
  git commit -m "$message" --quiet
}

# 最多 3 轮：每次合并后都必须重新验证；持续前移则失败关闭。
for sync_attempt in 1 2 3; do
  git fetch origin --quiet
  candidate_main=$(git rev-parse --verify 'origin/main^{commit}')
  if ! git merge-base --is-ancestor "$START_MAIN" "$candidate_main"; then
    echo "PM_CLOSEOUT_MAIN_HISTORY_REWRITTEN: start=$START_MAIN current=$candidate_main" >&2
    exit 3
  fi
  if ! git merge-base --is-ancestor "$candidate_main" HEAD 2>/dev/null; then
    if ! git merge "$candidate_main" -m "sync-merge origin/main (pm-closeout round $sync_attempt)" 2>/dev/null; then
      resolve_conflicts "sync-merge origin/main (round $sync_attempt, resolved)" "$candidate_main"
    fi
  fi

  # 3) 门禁（必需；参数数组执行，不经 shell/eval）
  verify_head=$(git rev-parse --verify 'HEAD^{commit}')
  verify_branch=$(git branch --show-current)
  echo "PM_CLOSEOUT_VERIFY: round=$sync_attempt $VERIFY_BIN (${#VERIFY_ARGS[@]} args)"
  if ! "$VERIFY_BIN" "${VERIFY_ARGS[@]}"; then
    echo "PM_CLOSEOUT_VERIFY_FAILED" >&2
    exit 4
  fi
  if [ -n "$(git status --porcelain)" ]; then
    echo "PM_CLOSEOUT_VERIFY_DIRTY: 门禁后工作树不干净" >&2
    exit 4
  fi
  after_verify_head=$(git rev-parse --verify 'HEAD^{commit}')
  after_verify_branch=$(git branch --show-current)
  if [ "$after_verify_head" != "$verify_head" ] || \
     [ "$after_verify_branch" != "$verify_branch" ] || \
     [ "$after_verify_branch" != "$BR" ]; then
    echo "PM_CLOSEOUT_VERIFY_GIT_STATE_CHANGED: before=$verify_head/$verify_branch after=$after_verify_head/$after_verify_branch" >&2
    exit 4
  fi
  if ! git merge-base --is-ancestor "$candidate_main" HEAD; then
    echo "PM_CLOSEOUT_VERIFY_BASE_LOST: candidate_main=$candidate_main head=$after_verify_head" >&2
    exit 4
  fi
  git_dir=$(git rev-parse --git-dir)
  for operation_marker in MERGE_HEAD CHERRY_PICK_HEAD REBASE_HEAD REVERT_HEAD; do
    if [ -e "$git_dir/$operation_marker" ]; then
      echo "PM_CLOSEOUT_VERIFY_OPERATION_IN_PROGRESS: $operation_marker" >&2
      exit 4
    fi
  done

  git fetch origin --quiet
  observed_main=$(git rev-parse --verify 'origin/main^{commit}')
  if ! git merge-base --is-ancestor "$START_MAIN" "$observed_main"; then
    echo "PM_CLOSEOUT_MAIN_HISTORY_REWRITTEN: start=$START_MAIN current=$observed_main" >&2
    exit 3
  fi
  if [ "$observed_main" = "$candidate_main" ]; then
    STABLE_MAIN="$candidate_main"
    SYNC_STABLE=1
    break
  fi
  echo "PM_CLOSEOUT_MAIN_ADVANCED: round=$sync_attempt before=$candidate_main after=$observed_main"
done
[ "$SYNC_STABLE" -eq 1 ] || {
  echo "PM_CLOSEOUT_MAIN_MOVED_TOO_MANY_TIMES: max_rounds=3" >&2
  exit 3
}
echo "PM_CLOSEOUT_MAIN_STABLE: $STABLE_MAIN"

# 4) safe-push
"$SP" --repo . --base origin/main --branch "$BR" --expected-name "$GIT_NAME" --expected-email "$GIT_EMAIL" >/dev/null
echo "PM_CLOSEOUT_PUSHED: $BR"

# 5) PR create → 从 URL 机械提取编号
if [ -z "$BODY_FILE" ]; then
  TMP_BODY=$(mktemp "${TMPDIR:-/tmp}/pm-closeout-body.XXXXXX")
  printf '%s

%s
' "$TITLE" "- 管道自动收口（未提供 body-file）：验证证据见分支提交与门禁日志。" > "$TMP_BODY"
  BODY_FILE="$TMP_BODY"
fi
CREATE_ARGS=(--base main --head "$BR" --title "$TITLE" --body-file "$BODY_FILE")
if ! CREATE_OUT=$(gh pr create "${CREATE_ARGS[@]}" 2>&1); then
  echo "PM_CLOSEOUT_PR_CREATE_FAILED: $CREATE_OUT" >&2
  exit 5
fi
URL=$(printf '%s\n' "$CREATE_OUT" | tail -1)
PR_N=$(printf '%s\n' "$URL" | sed -nE 's#^.*/pull/([0-9]+).*$#\1#p')
[ -n "$PR_N" ] || { echo "PM_CLOSEOUT_PR_CREATE_INVALID_RECEIPT: $CREATE_OUT" >&2; exit 5; }
echo "PM_CLOSEOUT_PR: #$PR_N ($URL)"

# 6) merge(用提取的编号) + 状态验证
if ! MERGE_OUT=$(gh pr merge "$PR_N" --squash --subject "$TITLE (#$PR_N)" 2>&1); then
  echo "PM_CLOSEOUT_MERGE_FAILED: #$PR_N $MERGE_OUT" >&2
  exit 6
fi
if ! STATE_OUT=$(gh pr view "$PR_N" --json state 2>&1); then
  echo "PM_CLOSEOUT_MERGE_STATE_READ_FAILED: #$PR_N $STATE_OUT" >&2
  exit 6
fi
if ! STATE=$(printf '%s\n' "$STATE_OUT" | jq -er '.state | select(type == "string")'); then
  echo "PM_CLOSEOUT_MERGE_STATE_INVALID: #$PR_N $STATE_OUT" >&2
  exit 6
fi
[ "$STATE" = "MERGED" ] || { echo "PM_CLOSEOUT_MERGE_UNCONFIRMED: #$PR_N state=$STATE" >&2; exit 6; }
echo "PM_CLOSEOUT_MERGED: #$PR_N"

# 7) 分支清理(仅在 MERGED 确认后)
if [ "$KEEP_BRANCH" -eq 0 ]; then
  if git push origin --delete "$BR" --quiet 2>/dev/null; then
    echo "PM_CLOSEOUT_BRANCH_DELETED: $BR"
  else
    echo "PM_CLOSEOUT_BRANCH_DELETE_WARNING: PR 已合并，但远端分支删除失败，请人工复核 $BR" >&2
  fi
fi
echo "PM_CLOSEOUT_OK: pr=$PR_N branch=$BR"
