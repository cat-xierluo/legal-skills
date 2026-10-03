#!/usr/bin/env bash
# worktree 冗余只读盘点：对 git worktree list 中每个挂载输出死活分类，辅助过期/失效 worktree 清理。
# 本脚本绝不执行任何删除；删除必须按 references/branch-lifecycle-and-cleanup.md §3.4
# 展示候选并取得用户确认后，由会话/人工执行。
#
# 用法: worktree-audit.sh [base-ref]
#   base-ref 默认 origin/main
#
# 判定规则（与 references/branch-lifecycle-and-cleanup.md §3.4 一致）：
#   GONE            目录已不存在（悬空记录）→ git worktree prune 候选
#   KEEP_ACTIVE     有进程 cwd 占用（活跃 PM/agent 会话），绝不列入清理
#   KEEP_DIRTY      有未提交内容 → 人工查看后再定（untracked 可能是无备份的研究材料）
#   KEEP_OPEN_PR    分支是 open PR head 或补丁未进 base → 可删 worktree 保分支（不自动列删）
#   REMOVE_ALL      分支补丁等价已全部在 base，且 PR 已合并/无 PR → worktree+本地分支均为候选
#   SKIP            主工作区 / detached 的工具自管目录（如 eval-harness sources）
#
# 降级：gh 缺失时 PR 状态标注「未核对」；lsof 缺失时进程占用标注「未核对」（一律保守保留）。

set -u

BASE_REF="${1:-origin/main}"

command -v git >/dev/null 2>&1 || {
  echo "❌ 缺少依赖: git"
  echo "   macOS: xcode-select --install 或 brew install git"
  exit 1
}

HAS_GH=0
OPEN_PRS=""
MERGED_PRS=""
if command -v gh >/dev/null 2>&1; then
  REPO_SLUG=$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null) || REPO_SLUG=""
  if [ -n "$REPO_SLUG" ]; then
    HAS_GH=1
    OPEN_PRS=$(gh pr list --repo "$REPO_SLUG" --state open --limit 200 \
      --json headRefName --jq '.[].headRefName' 2>/dev/null) || OPEN_PRS=""
    MERGED_PRS=$(gh pr list --repo "$REPO_SLUG" --state merged --limit 200 \
      --json headRefName --jq '.[].headRefName' 2>/dev/null) || MERGED_PRS=""
  fi
fi

# 进程占用探测：lsof 全量 cwd 记录缓存一次（-F n 输出完整路径，避免列宽截断）
CWD_PATHS=""
HAS_LSOF=0
if command -v lsof >/dev/null 2>&1; then
  HAS_LSOF=1
  CWD_PATHS=$(lsof -w -d cwd -F n 2>/dev/null | sed -n 's/^n//p')
fi

in_set() { printf '%s\n' "$1" | grep -Fxq -- "$2"; }

cwd_occupied() { # $1=worktree 路径 → 输出占用进程数（awk 前缀匹配，防路径空格/正则元字符）
  [ "$HAS_LSOF" = 1 ] || { echo "?"; return; }
  printf '%s\n' "$CWD_PATHS" | awk -v p="$1" 'index($0, p) == 1' | grep -c . || true
}

BASE_SHA=$(git rev-parse --verify --quiet "$BASE_REF")
if [ -z "$BASE_SHA" ]; then
  echo "❌ base-ref 不存在: $BASE_REF（先 git fetch，或显式传入，如: worktree-audit.sh origin/master）"
  exit 1
fi

MAIN_WT=$(git worktree list --porcelain 2>/dev/null | sed -n '1s/^worktree //p')

echo "== worktree 冗余盘点（只读，不删除） =="
echo "base=$BASE_REF repo=${REPO_SLUG:-未知} lsof=$([ "$HAS_LSOF" = 1 ] && echo ok || echo 缺失) gh=$([ "$HAS_GH" = 1 ] && echo ok || echo 缺失)"
echo

git worktree list --porcelain |
while IFS= read -r line; do
  case "$line" in
    worktree\ *) WT="${line#worktree }" ;;
    branch\ *)
      BR="${line#branch refs/heads/}"
      [ -d "$WT" ] || { printf 'GONE          %s\n' "$WT"; continue; }
      [ "$WT" = "$MAIN_WT" ] && { printf 'SKIP          %-70s 主工作区\n' "$WT"; continue; }
      occ=$(cwd_occupied "$WT")
      [ "$occ" != "?" ] && [ "$occ" -gt 0 ] 2>/dev/null && {
        printf 'KEEP_ACTIVE   %-70s [%s] %s 个进程占用\n' "$WT" "$BR" "$occ"; continue; }
      dirty=$(git -C "$WT" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
      [ "${dirty:-0}" -gt 0 ] 2>/dev/null && {
        printf 'KEEP_DIRTY    %-70s [%s] %s 个未提交项\n' "$WT" "$BR" "$dirty"; continue; }
      if [ -n "$BASE_SHA" ]; then
        new=$(git cherry "$BASE_SHA" "$BR" 2>/dev/null | grep -c '^+')
        if [ "${new:-1}" -eq 0 ] 2>/dev/null; then
          if in_set "$OPEN_PRS" "$BR"; then
            printf 'REMOVE_ALL*   %-70s [%s] 补丁已全在 base，但为 open PR head——删前先核对 PR\n' "$WT" "$BR"
          elif in_set "$MERGED_PRS" "$BR"; then
            printf 'REMOVE_ALL    %-70s [%s] PR 已合并且补丁在 base\n' "$WT" "$BR"
          else
            printf 'REMOVE_ALL    %-70s [%s] 补丁等价已全在 %s（patch-id 0）\n' "$WT" "$BR" "$BASE_REF"
          fi
        else
          printf 'KEEP_OPEN_PR  %-70s [%s] %s 个补丁未进 base（open PR/待交付），可仅删 worktree 保分支\n' "$WT" "$BR" "$new"
        fi
      else
        printf 'KEEP_OPEN_PR  %-70s [%s] 补丁状态未知（保守保留）\n' "$WT" "$BR"
      fi
      ;;
    detached*)
      [ -d "$WT" ] || { printf 'GONE          %s\n' "$WT"; continue; }
      [ "$WT" = "$MAIN_WT" ] && continue
      occ=$(cwd_occupied "$WT")
      if [ "$occ" != "?" ] && [ "$occ" -gt 0 ] 2>/dev/null; then
        printf 'KEEP_ACTIVE   %-70s [detached] %s 个进程占用\n' "$WT" "$occ"
      else
        printf 'KEEP_DIRTY*   %-70s [detached] 无分支挂载——确认非工具自管目录后人工定夺\n' "$WT"
      fi
      ;;
  esac
done

cat <<'EOF'

---- 执行须知（删除前必读） ----
1. 本表只是「候选」：批量删除前必须展示给用户并取得确认（红线，见 references §5）。
2. KEEP_ACTIVE 是硬保护：lsof 检出进程 cwd 占用的 worktree 属于活跃会话，绝不删除；
   lsof 缺失时占用显示 "?"，一律保守保留。
3. KEEP_DIRTY 中的 untracked 文件可能是无备份的研究材料（实战：R15 研究脚本只存在于
   worktree 未提交区）——删除前先确认正式版已入库，必要时拷出归档。
4. REMOVE_ALL 同时覆盖 worktree 与本地分支；KEEP_OPEN_PR 只可「删 worktree 保分支」
   （内容仍在分支/远端）。带 * 的行有附加条件，删前逐条核对。
5. detached worktree 先确认不是其他工具自管目录（评测/harness 类 sources 目录等）再处置。
6. 删除顺序：先 git worktree prune 清悬空记录，再逐个 remove（dirty 需 --force，须用户
   确认放弃未提交内容）；本地分支删除前对每条重跑 git cherry 校验。
7. 执行中可能遇到目录权限拒绝（实战：orca 工作区 Permission denied）——权限失败
   不继续删该 worktree 的关联分支，整项保留并按 CLEANUP_PENDING 如实报告；空壳目录
   由用户自行处置（如需提权删除须用户亲手执行，Agent 不代跑），勿反复重试。
EOF
