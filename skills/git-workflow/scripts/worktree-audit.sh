#!/usr/bin/env bash
# 只读候选盘点；不 prune/remove/删分支。实际登记/材料详细审计使用 sparse-worktree-audit.py。
set -u
BASE_REF="${1:-origin/main}"
for key in GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_NAMESPACE; do
  if [ -n "${!key:-}" ]; then echo '拒绝 Git 仓库/索引环境覆盖' >&2; exit 2; fi
done
git_read() { GIT_OPTIONAL_LOCKS=0 git --no-pager -c core.fsmonitor=false -c core.untrackedCache=false "$@"; }
command -v git >/dev/null 2>&1 || { echo '缺少依赖: git' >&2; exit 2; }
BASE_SHA=$(git_read rev-parse --verify "$BASE_REF^{commit}" 2>/dev/null) || { echo 'base-ref 不可读' >&2; exit 2; }
COMMON=$(git_read rev-parse --path-format=absolute --git-common-dir) || exit 2
INFO=$(git_read worktree list --porcelain) || exit 2
MAIN_WT=$(printf '%s\n' "$INFO" | sed -n '1s/^worktree //p')
HAS_GH=0; OPEN_PRS=''
if command -v gh >/dev/null 2>&1; then
  if SLUG=$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null) && [ -n "$SLUG" ]; then
    if OPEN_PRS=$(gh pr list --repo "$SLUG" --state open --limit 201 --json headRefName --jq '.[].headRefName' 2>/dev/null); then
      count=$(printf '%s\n' "$OPEN_PRS" | awk 'NF {n++} END {print n+0}')
      [ "$count" -lt 201 ] && HAS_GH=1
    fi
  fi
fi
HAS_LSOF=0; CWD_PATHS=''
if command -v lsof >/dev/null 2>&1; then
  if CWD_RAW=$(lsof -w -d cwd -F n 2>/dev/null); then
    CWD_PATHS=$(printf '%s\n' "$CWD_RAW" | sed -n 's/^n//p'); HAS_LSOF=1
  fi
fi
printf '== worktree 候选盘点（只读，不删除） ==\nbase=%s\n' "$BASE_REF"
WT=''; REG_HEAD=''
while IFS= read -r line; do
  case "$line" in
    worktree\ *) WT="${line#worktree }";;
    HEAD\ *) REG_HEAD="${line#HEAD }";;
    branch\ *|detached*)
      BR="${line#branch refs/heads/}"; [ "$line" = detached ] && BR=DETACHED
      [ -d "$WT" ] || { printf 'GONE          %s 登记缺目录，保留待核，不自动 prune\n' "$WT"; continue; }
      [ "$WT" = "$MAIN_WT" ] && { printf 'SKIP          %s 主工作区\n' "$WT"; continue; }
      if [ "$HAS_LSOF" != 1 ]; then printf 'KEEP_UNKNOWN  %s 占用未核\n' "$WT"; continue; fi
      occ=$(printf '%s\n' "$CWD_PATHS" | awk -v p="$WT" '$0==p || index($0,p"/")==1 {n++} END {print n+0}')
      [ "$occ" -gt 0 ] && { printf 'KEEP_ACTIVE   %s cwd 占用\n' "$WT"; continue; }
      [ "$BR" = DETACHED ] && { printf 'KEEP_UNKNOWN  %s detached 归属待核\n' "$WT"; continue; }
      if ! root=$(git_read -C "$WT" rev-parse --show-toplevel) || [ "$root" != "$WT" ]; then printf 'KEEP_UNKNOWN %s 实际根与登记不符\n' "$WT"; continue; fi
      if ! actual_common=$(git_read -C "$WT" rev-parse --path-format=absolute --git-common-dir) || [ "$actual_common" != "$COMMON" ]; then printf 'KEEP_UNKNOWN %s 仓库身份与登记不符\n' "$WT"; continue; fi
      if ! tip=$(git_read -C "$WT" rev-parse HEAD) || [ "$tip" != "$REG_HEAD" ]; then printf 'KEEP_UNKNOWN %s HEAD 已漂移\n' "$WT"; continue; fi
      if ! actual=$(git_read -C "$WT" symbolic-ref -q HEAD); then printf 'KEEP_UNKNOWN %s 分支不可读\n' "$WT"; continue; fi
      [ "$actual" = "refs/heads/$BR" ] || { printf 'KEEP_UNKNOWN %s 登记身份变化\n' "$WT"; continue; }
      # 该旧格式审计保守跳过配置了外部过滤器的树；精确属性判定由 sparse-worktree-audit.py 维护。
      if filters=$(git_read -C "$WT" config --name-only --get-regexp '^filter\..*\.(clean|process)$'); then
        printf 'KEEP_UNKNOWN  %s 外部过滤器配置，材料未验\n' "$WT"; continue
      else
        code=$?; [ "$code" = 1 ] || { printf 'KEEP_UNKNOWN %s 配置不可读\n' "$WT"; continue; }
      fi
      if ! dirty=$(git_read -C "$WT" status --porcelain --untracked-files=all); then printf 'KEEP_UNKNOWN %s status 不可读\n' "$WT"; continue; fi
      if ! ignored=$(git_read -C "$WT" ls-files --others --ignored --exclude-standard); then printf 'KEEP_UNKNOWN %s 本地材料不可读\n' "$WT"; continue; fi
      if [ -n "$dirty" ] || [ -n "$ignored" ]; then printf 'KEEP_DIRTY    %s dirty/untracked/ignored 材料待保护\n' "$WT"; continue; fi
      if [ "$HAS_GH" != 1 ] || printf '%s\n' "$OPEN_PRS" | grep -Fxq -- "$BR"; then printf 'KEEP_OPEN_PR  %s PR 未核完整或为 open head\n' "$WT"; continue; fi
      if git_read merge-base --is-ancestor "$actual" "$BASE_SHA"; then
        printf 'REMOVE_ALL    %s 当前 tip 在 base，仅为生命周期/owner 待复核候选\n' "$WT"
      else
        printf 'KEEP_OPEN_PR  %s 当前 tip 未证明已交付；不按 patch-id/历史 MERGED 判死\n' "$WT"
      fi;;
  esac
done <<< "$INFO"
cat <<'NOTICE'

本表只是候选，cwd 无命中不证明无 writer/Session。删除前核生命周期、精确 tip、全部本地材料备份及具名授权。
主源、长期线、活跃/未知归属和未交付成果保留；分支存在不代表 ignored/untracked/Session 已备份。
prune 是独立登记写操作，不自动执行；ordinary remove 失败即保留现场，不继续删除关联 ref，不强删、不绕权限。
记录 CLEANUP_PENDING 或 RETAINED_WITH_REASON；已交付的 push/merge 不重放。详细合同见 references/branch-lifecycle-and-cleanup.md。
NOTICE
