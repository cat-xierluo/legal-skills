#!/usr/bin/env bash
# 只读候选盘点；不 fetch/prune，不删除。SAFE_DELETE 仍须生命周期/当前 tip/授权复核。
set -u
BASE_REF="${1:-origin/main}"
REMOTE="${2:-origin}"
for key in GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_NAMESPACE; do
  if [ -n "${!key:-}" ]; then echo '拒绝 Git 仓库/索引环境覆盖' >&2; exit 2; fi
done
git_read() { GIT_OPTIONAL_LOCKS=0 git --no-pager -c core.fsmonitor=false -c core.untrackedCache=false "$@"; }
command -v git >/dev/null 2>&1 || { echo '缺少依赖: git' >&2; exit 2; }
BASE_SHA=$(git_read rev-parse --verify "$BASE_REF^{commit}" 2>/dev/null) || { echo 'base-ref 不可读' >&2; exit 2; }
HEAD_BRANCH=$(git_read branch --show-current) || exit 2
WT_INFO=$(git_read worktree list --porcelain) || exit 2
WT_BRANCHES=$(printf '%s\n' "$WT_INFO" | sed -n 's|^branch refs/heads/||p')
in_set() { printf '%s\n' "$1" | grep -Fxq -- "$2"; }
is_archive() { case "$1" in backup/*|*snapshot*|archive/*) return 0;; *) return 1;; esac; }
HAS_GH=0
OPEN_PRS=''
if command -v gh >/dev/null 2>&1; then
  if REPO_SLUG=$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null) && [ -n "$REPO_SLUG" ]; then
    if OPEN_PRS=$(gh pr list --repo "$REPO_SLUG" --state open --limit 201 --json headRefName --jq '.[].headRefName' 2>/dev/null); then
      count=$(printf '%s\n' "$OPEN_PRS" | awk 'NF {n++} END {print n+0}')
      [ "$count" -lt 201 ] && HAS_GH=1
    fi
  fi
fi
printf '== 分支候选盘点（本地只读，无 fetch/prune/删除） ==\nbase=%s remote=%s\n' "$BASE_REF" "$REMOTE"
[ "$HAS_GH" = 1 ] || echo 'PR 查询缺失、失败或截断：保守保留；缓存远端 ref 可能陈旧。'
classify() {
  local ref="$1" short="$2" date="$3" kind="$4" ahead patch count code
  if is_archive "$short" || in_set "$WT_BRANCHES" "$short"; then
    printf 'KEEP          %-55s %s  存档或已检出分支\n' "$short" "$date"; return
  fi
  if [ "$HAS_GH" != 1 ] || in_set "$OPEN_PRS" "$short"; then
    printf 'KEEP          %-55s %s  PR 未核完整或为 open head\n' "$short" "$date"; return
  fi
  if [ "$kind" = remote ]; then
    if git_read show-ref --verify -q "refs/heads/$short"; then
      ahead=$(git_read rev-list --count "$ref..refs/heads/$short" 2>/dev/null) || {
        printf 'KEEP          %s 同名本地增量不可读\n' "$short"; return; }
      if [ "$ahead" -gt 0 ]; then printf 'NEEDS_CONFIRM %s 同名本地分支有未发表成果\n' "$short"; return; fi
    else
      code=$?
      if [ "$code" -ne 1 ]; then printf 'KEEP          %s 同名本地分支查询失败\n' "$short"; return; fi
    fi
  fi
  if git_read merge-base --is-ancestor "$ref" "$BASE_SHA"; then
    printf 'SAFE_DELETE   %-55s %s  当前 tip 已包含于 base，仅为待复核候选\n' "$short" "$date"; return
  else
    code=$?
    if [ "$code" -ne 1 ]; then printf 'KEEP          %s 祖先查询失败\n' "$short"; return; fi
  fi
  if patch=$(git_read cherry "$BASE_SHA" "$ref" 2>/dev/null); then
    count=$(printf '%s\n' "$patch" | awk '/^\+/ {n++} END {print n+0}')
    printf 'NEEDS_CONFIRM %-55s %s  %s 个补丁未匹配；patch-id/历史 MERGED 不证明当前 tip 已交付\n' "$short" "$date" "$count"
  else
    printf 'KEEP          %s 补丁查询失败\n' "$short"
  fi
}
REMOTE_REFS=$(git_read for-each-ref "refs/remotes/$REMOTE/" --format='%(refname)|%(committerdate:short)') || exit 2
while IFS='|' read -r ref date; do
  [ -n "$ref" ] || continue
  short="${ref#"refs/remotes/$REMOTE/"}"
  [ "$short" = HEAD ] && continue
  [ "$ref" = "refs/remotes/$BASE_REF" ] && continue
  classify "$ref" "$short" "$date" remote
done <<< "$REMOTE_REFS"
LOCAL_REFS=$(git_read for-each-ref refs/heads/ --format='%(refname)|%(committerdate:short)') || exit 2
while IFS='|' read -r ref date; do
  [ -n "$ref" ] || continue
  short="${ref#refs/heads/}"
  [ "$short" = "$HEAD_BRANCH" ] && continue
  [ "$short" = "${BASE_REF#"$REMOTE"/}" ] && continue
  classify "$ref" "$short" "$date" local
done <<< "$LOCAL_REFS"
cat <<'NOTICE'

候选不构成删除授权；执行前重新核当前 tip、真实目标、生命周期、归属/占用、全部任务材料与完整 PR 状态。
历史 MERGED、patch-id、日期与祖先关系不能单独授权删除；长期线及未交付成果保留。
删除按 references/branch-lifecycle-and-cleanup.md 的精确 tip/lease 合同；失败保留现场和 CLEANUP_PENDING，不删关联 ref、不绕权限或代理、不盲目重试。
NOTICE
