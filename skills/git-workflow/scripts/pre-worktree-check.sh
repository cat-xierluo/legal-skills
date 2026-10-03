#!/usr/bin/env bash
# 开 worktree 前 3 查与提 PR 前合并模拟（只读）。
# 把 SKILL.md §2「开 worktree 前的必做 3 查」的判读表机械化：
# 输出 IN_SYNC / AHEAD / BEHIND / DIVERGED 四态判定与对应处理路径，
# 以及 --pre-pr 模式下用 git merge-tree 做的本地合并冲突预检。
#
# 本脚本绝不创建/删除/重置任何分支、worktree 或提交；fetch 只更新
# 远端跟踪引用。AHEAD/BEHIND/DIVERGED 的后续处理（pull/merge/三选一/
# reset）全部由会话/人工按 SKILL.md 判读表执行，脚本只报告不执行。
#
# 用法:
#   pre-worktree-check.sh [base-ref] [remote]        # 开 worktree 前 3 查（默认）
#   pre-worktree-check.sh --pre-pr <branch> [base-ref] [remote]
#                                                     # 提 PR 前本地合并模拟
#   base-ref 默认 main；remote 默认 origin
#
# 判读四态（与 SKILL.md §2 判读表一致）:
#   IN_SYNC   本地 base = 远端 base          → GO
#   AHEAD     本地领先（有未 push 独有提交）  → GO_WITH_NOTE（可以远端 ref 起点开
#              worktree；独有提交按三选一另行处理，禁止 reset 丢弃）
#   BEHIND    本地落后（远端已合，本地没跟）  → FIX_FIRST（先 pull --no-rebase 再开）
#   DIVERGED  双向分叉                       → FIX_FIRST（隔离候选内对账，不重置主源）
#
# --pre-pr 模式（对应 Task「PR mergeable 前置」的真实可行前置点）:
#   PR 创建后的 mergeable 检查无法搬到开 worktree 前（PR 对象尚不存在）；
#   可前置的是「提 PR 前」用 git merge-tree --write-tree 在本地模拟
#   base+head 合并——不创建 PR、不触碰工作区与 index、不耗 GitHub API。
#   干净 → GO；冲突 → NO_GO + 冲突文件清单（按 SKILL.md「base 落后 /
#   冲突处理决策表」三选一处理）。需要 Git 2.38+。
#
# 退出码: 0 = GO / GO_WITH_NOTE；1 = FIX_FIRST / NO_GO（处理后重跑）；
#         2 = 用法或环境错误。

set -u

PRE_PR_BRANCH=""
BASE="main"
REMOTE="origin"

usage() {
  sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}

while [ $# -gt 0 ]; do
  case "$1" in
    --pre-pr)
      [ $# -ge 2 ] || { echo "❌ --pre-pr 需要分支名参数" >&2; exit 2; }
      PRE_PR_BRANCH="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) break ;;
  esac
done
# 剩余位置参数: [base-ref] [remote]
[ $# -ge 1 ] && BASE="$1"
[ $# -ge 2 ] && REMOTE="$2"
[ $# -ge 3 ] && { echo "❌ 参数过多: $3（最多 [base-ref] [remote] 两个位置参数）" >&2; exit 2; }

command -v git >/dev/null 2>&1 || {
  echo "❌ 缺少依赖: git"
  echo "   macOS: xcode-select --install 或 brew install git"
  exit 2
}

REMOTE_REF="$REMOTE/$BASE"

# ---- 1/3 fetch 远端最新（失败时降级按本地已有引用判定并显式标注） ----
echo "== pre-worktree-check（只读） =="
echo "base=$BASE remote=$REMOTE mode=$([ -n "$PRE_PR_BRANCH" ] && echo "pre-pr($PRE_PR_BRANCH)" || echo worktree-pre)"
echo
DEGRADED=""
if ! git fetch "$REMOTE" >/dev/null 2>&1; then
  DEGRADED="⚠️ git fetch $REMOTE 失败（离线？），以下按本地已有引用判定，可能过期"
  echo "$DEGRADED"
  echo
fi

REMOTE_SHA=$(git rev-parse --verify --quiet "$REMOTE_REF")
if [ -z "$REMOTE_SHA" ]; then
  echo "❌ 远端 base ref 不存在: ${REMOTE_REF}（先 git fetch，或显式传入正确的 base-ref）"
  exit 2
fi

# ---- --pre-pr 模式：merge-tree 本地合并模拟 ----
if [ -n "$PRE_PR_BRANCH" ]; then
  BRANCH_SHA=$(git rev-parse --verify --quiet "$PRE_PR_BRANCH")
  if [ -z "$BRANCH_SHA" ]; then
    echo "❌ 待检分支不存在: $PRE_PR_BRANCH"
    exit 2
  fi
  # git merge-tree --write-tree 需要 Git 2.38+
  gitver=$(git version 2>/dev/null | awk '{print $3}')
  gmajor="${gitver%%.*}"; grest="${gitver#*.}"; gminor="${grest%%.*}"
  if ! { [ "$gmajor" -gt 2 ] || { [ "$gmajor" -eq 2 ] && [ "$gminor" -ge 38 ]; } }; then
    echo "❌ --pre-pr 需要 Git 2.38+（当前 ${gitver}）：merge-tree --write-tree 不可用"
    echo "   旧版等价（触碰工作区，不属于本脚本只读范畴）："
    echo "   git switch -c tmp-merge-test && git merge --no-commit --no-ff $REMOTE_REF; 失败后 git merge --abort"
    exit 2
  fi
  echo "-- 合并模拟: git merge-tree $REMOTE_REF + ${PRE_PR_BRANCH}（不触碰工作区/index）--"
  MT_OUT=$(git merge-tree --write-tree "$REMOTE_REF" "$PRE_PR_BRANCH" 2>&1)
  MT_RC=$?
  if [ "$MT_RC" -eq 0 ]; then
    echo "✅ 判读: GO —— 本地模拟合并干净，无冲突"
    echo "   下一步: 走 safe-push.sh / safe-pr.py create；创建 PR 后仍须跑 PR mergeable 后验（SKILL.md §4）"
    exit 0
  elif [ "$MT_RC" -eq 1 ]; then
    # 输出: <tree OID> / 空行 / 冲突文件清单 / 空行 / informational messages
    CONFLICTS=$(printf '%s\n' "$MT_OUT" | awk 'NF==0{blank++; next} blank==1')
    echo "⛔ 判读: NO_GO —— 本地模拟合并有冲突，创建 PR 前先处理："
    echo
    echo "$CONFLICTS" | sed 's/^/    /'
    echo
    echo "   按 SKILL.md「base 落后 / 冲突处理决策表」三选一（docs 同步文件保留双方 /"
    echo "   实质代码开隔离窄采用候选 / 冲突极少本地按文件解决）。"
    echo "   功能线分支不 rebase/reset；历史已发表分支的重写需单独授权。"
    exit 1
  else
    echo "❌ git merge-tree 失败（exit ${MT_RC}）:"
    printf '%s\n' "$MT_OUT" | sed 's/^/    /'
    exit 2
  fi
fi

# ---- 2/3 & 3/3 默认模式：本地 base vs 远端 base 分叉判定 ----
LOCAL_SHA=$(git rev-parse --verify --quiet "$BASE")
if [ -z "$LOCAL_SHA" ]; then
  echo "ℹ️ 本地分支 $BASE 不存在（未建或已删）：无分叉可判。"
  echo "   以 $REMOTE_REF 为显式起点开 worktree 不受影响："
  echo "   git switch -c <branch> $REMOTE_REF"
  echo "   本地若曾有同名分支，恢复路径见 references/accident-recovery.md。"
  exit 0
fi

MB=$(git merge-base "$BASE" "$REMOTE_REF" 2>/dev/null) || MB=""

LOCAL_SHORT=$(git rev-parse --short "$BASE")
REMOTE_SHORT=$(git rev-parse --short "$REMOTE_REF")
MB_SHORT=$([ -n "$MB" ] && git rev-parse --short "$MB" || echo "无")

echo "-- 2/3 分叉判定 --"
echo "本地 $BASE:      $LOCAL_SHORT"
echo "$REMOTE_REF:  $REMOTE_SHORT"
echo "merge-base:     $MB_SHORT"
echo

echo "-- 3/3 独有 commit 与现场简报 --"
AHEAD_COMMITS=$(git log --oneline "$REMOTE_REF..$BASE" 2>/dev/null)
BEHIND_COMMITS=$(git log --oneline "$BASE..$REMOTE_REF" 2>/dev/null)
AHEAD_N=$(git rev-list --count "$REMOTE_REF..$BASE" 2>/dev/null || echo "?")
BEHIND_N=$(git rev-list --count "$BASE..$REMOTE_REF" 2>/dev/null || echo "?")
DIRTY_N=$(git status --short 2>/dev/null | wc -l | tr -d ' ')
echo "本地独有（$REMOTE_REF..${BASE}）: $AHEAD_N 个"
[ "$AHEAD_N" != "0" ] && printf '%s\n' "$AHEAD_COMMITS" | sed 's/^/    /'
echo "远端已合（$BASE..${REMOTE_REF}）: $BEHIND_N 个"
[ "$BEHIND_N" != "0" ] && printf '%s\n' "$BEHIND_COMMITS" | sed 's/^/    /'
echo "工作区未提交/未跟踪: ${DIRTY_N:-0} 项（与开 worktree 无关，仅现场简报）"
echo

# ---- 判读（与 SKILL.md §2 判读表逐行对应） ----
if [ "$LOCAL_SHA" = "$REMOTE_SHA" ]; then
  STATE="IN_SYNC"
elif [ "$MB" = "$REMOTE_SHA" ]; then
  STATE="AHEAD"
elif [ "$MB" = "$LOCAL_SHA" ]; then
  STATE="BEHIND"
else
  STATE="DIVERGED"
fi

case "$STATE" in
  IN_SYNC)
    echo "✅ 判读: IN_SYNC —— 本地 $BASE 与 $REMOTE_REF 一致"
    echo "   处理: 直接开 worktree：git switch -c <branch> $REMOTE_REF"
    exit 0
    ;;
  AHEAD)
    echo "🟡 判读: AHEAD —— 本地 $BASE 领先 ${REMOTE_REF}（$AHEAD_N 个独有未 push 提交）"
    echo "   处理: 可从 $REMOTE_REF 开 worktree（GO_WITH_NOTE）；独有提交按三选一另行处理:"
    echo "     A. 经 PR 交付（从最新远端目标开隔离短分支窄采用，走 safe-push/safe-pr）"
    echo "     B. merge origin 保留: git merge $REMOTE_REF --no-ff -m \"merge: bring $REMOTE_REF into local $BASE + preserve <描述>\""
    echo "     C. 放弃独有提交 —— git reset --hard 属破坏性，必须用户明确指示（SKILL.md §1）"
    exit 0
    ;;
  BEHIND)
    echo "⛔ 判读: BEHIND —— 本地 $BASE 落后 ${REMOTE_REF}（远端已合 $BEHIND_N 个，本地没跟）"
    echo "   处理: 先 git pull --no-rebase（merge ${REMOTE_REF}）再开 worktree；"
    echo "   禁止基于过期 $BASE 开 worktree 后再补救（PR not mergeable + 决策编号撞车）。"
    exit 1
    ;;
  DIVERGED)
    echo "⛔ 判读: DIVERGED —— 本地与 $REMOTE_REF 双向分叉（本地独有 $AHEAD_N / 远端已合 ${BEHIND_N}）"
    echo "   处理: 保留双方成果，在隔离候选内对账后窄采用；"
    echo "   不 reset 共享主源，不擅自丢弃任一侧（SKILL.md §1 安全协议）。"
    exit 1
    ;;
esac
