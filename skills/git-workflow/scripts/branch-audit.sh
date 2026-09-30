#!/usr/bin/env bash
# 分支冗余只读盘点：对远端与本地分支输出三档候选表（SAFE_DELETE / NEEDS_CONFIRM / KEEP）。
# 本脚本绝不执行任何删除；删除必须按 references/branch-lifecycle-and-cleanup.md
# 展示候选并取得用户确认后，由会话/人工执行。
#
# 用法: branch-audit.sh [base-ref] [remote]
#   base-ref 默认 origin/main；remote 默认 origin
#
# 判定规则（与 references/branch-lifecycle-and-cleanup.md §3 一致）：
#   SAFE_DELETE    PR 已合并（squash/rebase 内容已进 base）或分支已包含于 base
#   NEEDS_CONFIRM  无 PR 且未合并——删=内容真丢，必须逐个问用户
#   KEEP           open PR head / 被任一 worktree 检出 / backup·snapshot 存档命名
#
# 降级：gh 缺失或未认证时按 merge-base+日期判定，并显式标注「PR 状态未核对」；
# squash 合并的分支会漏判为 NEEDS_CONFIRM——宁漏勿错，方向安全。

set -u

BASE_REF="${1:-origin/main}"
REMOTE="${2:-origin}"

command -v git >/dev/null 2>&1 || {
  echo "❌ 缺少依赖: git"
  echo "   macOS: xcode-select --install 或 brew install git"
  exit 1
}

HAS_GH=0
REPO_SLUG=""
MERGED_PRS=""
OPEN_PRS=""
DEGRADE_NOTE=""
if command -v gh >/dev/null 2>&1; then
  HAS_GH=1
  REPO_SLUG=$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null) || REPO_SLUG=""
  if [ -n "$REPO_SLUG" ]; then
    MERGED_PRS=$(gh pr list --repo "$REPO_SLUG" --state merged --limit 200 \
      --json number,headRefName --jq '.[] | "\(.headRefName) #\(.number)"' 2>/dev/null) || MERGED_PRS=""
    OPEN_PRS=$(gh pr list --repo "$REPO_SLUG" --state open --limit 200 \
      --json headRefName --jq '.[].headRefName' 2>/dev/null) || OPEN_PRS=""
  fi
fi
if [ "$HAS_GH" != 1 ] || [ -z "$REPO_SLUG" ]; then
  DEGRADE_NOTE="⚠️ gh 不可用或未认证：PR 状态未核对，squash 合并的分支会漏判为 NEEDS_CONFIRM（宁漏勿错）"
fi

echo "== 分支冗余盘点（只读，不删除） =="
echo "base=$BASE_REF remote=$REMOTE repo=${REPO_SLUG:-未知}"
[ -n "$DEGRADE_NOTE" ] && echo "$DEGRADE_NOTE"
echo

git fetch --prune "$REMOTE" >/dev/null 2>&1 || echo "⚠️ git fetch --prune 失败（离线？），按本地已有引用盘点"

BASE_SHA=$(git rev-parse --verify --quiet "$BASE_REF")
if [ -z "$BASE_SHA" ]; then
  echo "❌ base-ref 不存在: $BASE_REF（先 git fetch，或显式传入，如: branch-audit.sh origin/master）"
  exit 1
fi

BASE_SHORT="${BASE_REF#"$REMOTE"/}"
HEAD_BRANCH=$(git branch --show-current 2>/dev/null)
WT_BRANCHES=$(git worktree list --porcelain 2>/dev/null | sed -n 's/^branch //p' | sed 's|refs/heads/||')

in_set() { # $1=set(换行分隔)  $2=item
  printf '%s\n' "$1" | grep -Fxq -- "$2"
}

merged_pr_of() { # $1=headRefName → 输出 "#n" 或空
  [ -n "$MERGED_PRS" ] || return 0
  printf '%s\n' "$MERGED_PRS" | awk -v x="$1" '$1==x {print $2; exit}'
}

is_archive_name() { # backup/snapshot 类存档命名 → 存档分支默认保留
  case "$1" in
    backup/*|*snapshot*|archive/*) return 0 ;;
    *) return 1 ;;
  esac
}

echo "---- 远端分支（$REMOTE/*，除 base） ----"
git for-each-ref "refs/remotes/$REMOTE" --format='%(refname:short)|%(committerdate:short)' |
while IFS='|' read -r full date; do
  short="${full#"$REMOTE"/}"
  case "$full" in "$REMOTE"/*) ;; *) continue ;; esac  # 跳过裸 remote ref（refs/remotes/origin 本身）
  [ "$short" = "HEAD" ] && continue
  [ "$full" = "$BASE_REF" ] && continue
  if in_set "$OPEN_PRS" "$short"; then
    printf 'KEEP          %-55s %s  open PR head\n' "$short" "$date"; continue
  fi
  pr=$(merged_pr_of "$short")
  # 方向性保护：本地同名分支若有未推送提交，说明分支被复用，远端 ref 不可列为删除候选
  if git show-ref --verify -q "refs/heads/$short" 2>/dev/null; then
    a=$(git rev-list --count "$full..refs/heads/$short" 2>/dev/null || echo 0)
    if [ "${a:-0}" -gt 0 ] 2>/dev/null; then
      printf 'NEEDS_CONFIRM %-55s %s  本地同名分支有 %s 个未推送提交（分支被复用）\n' "$short" "$date" "$a"
      continue
    fi
  fi
  if [ -n "$pr" ]; then
    printf 'SAFE_DELETE   %-55s %s  PR %s 已合并（内容已进 base）\n' "$short" "$date" "$pr"
  elif git merge-base --is-ancestor "$full" "$BASE_SHA" 2>/dev/null; then
    printf 'SAFE_DELETE   %-55s %s  已包含于 %s\n' "$short" "$date" "$BASE_REF"
  elif is_archive_name "$short"; then
    printf 'KEEP          %-55s %s  存档分支\n' "$short" "$date"
  else
    n=$(git rev-list --count "$BASE_SHA..$full" 2>/dev/null || echo '?')
    printf 'NEEDS_CONFIRM %-55s %s  无 PR 未合并（%s commits，删=内容丢失）\n' "$short" "$date" "$n"
  fi
done

echo
echo "---- 本地分支（refs/heads/*，除当前 HEAD） ----"
git for-each-ref refs/heads --format='%(refname:short)|%(committerdate:short)' |
while IFS='|' read -r short date; do
  [ "$short" = "$HEAD_BRANCH" ] && continue
  [ "$short" = "$BASE_SHORT" ] && continue  # 永不把 base 的本地分支（如 main）列为候选
  if in_set "$WT_BRANCHES" "$short"; then
    printf 'KEEP          %-55s %s  被 worktree 检出\n' "$short" "$date"; continue
  fi
  if git merge-base --is-ancestor "$short" "$BASE_SHA" 2>/dev/null; then
    printf 'SAFE_DELETE   %-55s %s  已包含于 %s\n' "$short" "$date" "$BASE_REF"
  elif is_archive_name "$short"; then
    printf 'KEEP          %-55s %s  存档分支\n' "$short" "$date"
  else
    n=$(git rev-list --count "$BASE_SHA..$short" 2>/dev/null || echo '?')
    printf 'NEEDS_CONFIRM %-55s %s  未合并（%s commits）\n' "$short" "$date" "$n"
  fi
done

cat <<'EOF'

---- 执行须知（删除前必读） ----
1. SAFE_DELETE 也只是「候选」：批量删除前必须把候选表展示给用户并取得确认（红线，见 references §5）。
2. 确认到执行之间并行会话可能新开/推送分支：执行删除前重跑 open PR head 核对（gh pr list --state open）。
3. git push origin --delete b1 b2 ... 遇任一 ref 已不存在会整批失败：先 git fetch --prune，再对仍存在的名单补删。
4. 代理环境 push 被全局 http.proxy 干扰时：git -c http.proxy= -c https.proxy= push ...
5. 删除远端 ref 不影响本地分支与 worktree 检出；本地分支删除前对每条重跑 merge-base 校验。
EOF
