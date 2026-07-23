#!/usr/bin/env bash
# 只读门禁：核验 push 前完整 outgoing range 内每个 commit 的 author 与 committer。

set -euo pipefail

REPO="."
BASE_REF=""
HEAD_REF="HEAD"
EXPECTED_NAME="${EXPECTED_GIT_NAME:-}"
EXPECTED_EMAIL="${EXPECTED_GIT_EMAIL:-}"

usage() {
  cat >&2 <<'USAGE'
用法：
  check-outgoing-identities.sh [--repo PATH] [--base REF] [--head REF]
    --expected-name NAME --expected-email EMAIL

默认仅在当前分支 upstream 指向不同名称的远端分支时推导 base；
若 upstream 是当前 feature branch 自身（例如 origin/feat/x），必须显式传 PR base。
显式 base 也必须是远端跟踪引用（例如 origin/main），不接受 HEAD~1 或本地分支。
门禁只读，不修改 Git 配置、refs、工作树或提交。

环境变量备用入口：EXPECTED_GIT_NAME、EXPECTED_GIT_EMAIL。
USAGE
}

die() {
  local code="$1"
  shift
  printf '%s: %s\n' "$code" "$*" >&2
  exit 1
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo)
      [ "$#" -ge 2 ] || die "IDENTITY_GATE_USAGE" "--repo 缺少参数"
      REPO="$2"
      shift 2
      ;;
    --base)
      [ "$#" -ge 2 ] || die "IDENTITY_GATE_USAGE" "--base 缺少参数"
      BASE_REF="$2"
      shift 2
      ;;
    --head)
      [ "$#" -ge 2 ] || die "IDENTITY_GATE_USAGE" "--head 缺少参数"
      HEAD_REF="$2"
      shift 2
      ;;
    --expected-name)
      [ "$#" -ge 2 ] || die "IDENTITY_GATE_USAGE" "--expected-name 缺少参数"
      EXPECTED_NAME="$2"
      shift 2
      ;;
    --expected-email)
      [ "$#" -ge 2 ] || die "IDENTITY_GATE_USAGE" "--expected-email 缺少参数"
      EXPECTED_EMAIL="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      die "IDENTITY_GATE_USAGE" "未知参数：$1"
      ;;
  esac
done

[ -n "$EXPECTED_NAME" ] || die "IDENTITY_GATE_EXPECTATION_MISSING" "必须提供 expected name"
[ -n "$EXPECTED_EMAIL" ] || die "IDENTITY_GATE_EXPECTATION_MISSING" "必须提供 expected email"
[ "$HEAD_REF" = "HEAD" ] || \
  die "IDENTITY_GATE_HEAD_NOT_CURRENT" "身份门禁只能核验当前 worktree HEAD；拒绝用其他干净 ref 代替待 push HEAD"
case "$EXPECTED_NAME" in
  *$'\n'*|*$'\r'*|*$'\t'*) die "IDENTITY_GATE_EXPECTATION_INVALID" "expected name 含控制字符" ;;
esac
case "$EXPECTED_EMAIL" in
  *$'\n'*|*$'\r'*|*$'\t'*|*' '*) die "IDENTITY_GATE_EXPECTATION_INVALID" "expected email 含空白或控制字符" ;;
  *@*) ;;
  *) die "IDENTITY_GATE_EXPECTATION_INVALID" "expected email 格式异常" ;;
esac

[ -d "$REPO" ] || die "IDENTITY_GATE_NOT_REPOSITORY" "目录不存在：$REPO"
git -C "$REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1 || \
  die "IDENTITY_GATE_NOT_REPOSITORY" "不是 Git worktree：$REPO"

branch_ref=$(git -C "$REPO" symbolic-ref -q HEAD 2>/dev/null) || \
  die "IDENTITY_GATE_BASE_UNKNOWN" "detached HEAD 无法确认 PR 分支与 base；请在分支 worktree 中运行"
branch_name=${branch_ref#refs/heads/}

if [ -z "$BASE_REF" ]; then
  [ "$HEAD_REF" = "HEAD" ] || \
    die "IDENTITY_GATE_BASE_UNKNOWN" "--head 非 HEAD 时必须显式提供 --base"
  BASE_REF=$(git -C "$REPO" for-each-ref --format='%(upstream:short)' "$branch_ref") || \
    die "IDENTITY_GATE_GIT_ERROR" "读取 upstream 失败"
  [ -n "$BASE_REF" ] || \
    die "IDENTITY_GATE_BASE_UNKNOWN" "当前分支没有 upstream；请显式提供 --base"
  upstream_merge_ref=$(git -C "$REPO" for-each-ref --format='%(upstream:remoteref)' "$branch_ref") || \
    die "IDENTITY_GATE_GIT_ERROR" "读取 upstream remote ref 失败"
  [ "$upstream_merge_ref" != "refs/heads/$branch_name" ] || \
    die "IDENTITY_GATE_BASE_AMBIGUOUS" \
      "upstream=$BASE_REF 是当前分支自身，可能隐藏已 push 的早期污染；请显式传 PR base（例如 origin/main）"
fi

BASE_FULL_REF=$(git -C "$REPO" rev-parse --symbolic-full-name "$BASE_REF" 2>/dev/null) || \
  die "IDENTITY_GATE_BAD_BASE" "无法解析 base：$BASE_REF"
case "$BASE_FULL_REF" in
  refs/remotes/*) ;;
  *) die "IDENTITY_GATE_BASE_NOT_REMOTE" \
       "base 必须是远端跟踪引用，拒绝可任意缩窄范围的本地 commit-ish：$BASE_REF" ;;
esac

BASE_SHA=$(git -C "$REPO" rev-parse --verify "$BASE_FULL_REF^{commit}" 2>/dev/null) || \
  die "IDENTITY_GATE_BAD_BASE" "无法解析 base：$BASE_REF"
HEAD_SHA=$(git -C "$REPO" rev-parse --verify "$HEAD_REF^{commit}" 2>/dev/null) || \
  die "IDENTITY_GATE_BAD_HEAD" "无法解析 head：$HEAD_REF"

git -C "$REPO" merge-base --is-ancestor "$BASE_SHA" "$HEAD_SHA" >/dev/null 2>&1 || \
  die "IDENTITY_GATE_NON_ANCESTOR_BASE" "base 不是 head 的祖先，outgoing range 不可靠：$BASE_REF..$HEAD_REF"

commit_list=$(git -C "$REPO" rev-list --reverse "$BASE_SHA..$HEAD_SHA") || \
  die "IDENTITY_GATE_GIT_ERROR" "无法枚举 outgoing range：$BASE_REF..$HEAD_REF"
[ -n "$commit_list" ] || \
  die "IDENTITY_GATE_EMPTY_RANGE" "outgoing range 为空：$BASE_REF..$HEAD_REF"

count=0
while IFS= read -r sha; do
  [ -n "$sha" ] || die "IDENTITY_GATE_BAD_COMMIT" "outgoing range 出现空 commit id"
  case "$sha" in
    *[!0-9a-fA-F]*) die "IDENTITY_GATE_BAD_COMMIT" "commit id 异常：$sha" ;;
  esac
  [ "${#sha}" -ge 40 ] || die "IDENTITY_GATE_BAD_COMMIT" "commit id 过短：$sha"

  author_name=$(git -C "$REPO" show -s --format='%an' "$sha") || \
    die "IDENTITY_GATE_GIT_ERROR" "读取 author_name 失败：$sha"
  author_email=$(git -C "$REPO" show -s --format='%ae' "$sha") || \
    die "IDENTITY_GATE_GIT_ERROR" "读取 author_email 失败：$sha"
  committer_name=$(git -C "$REPO" show -s --format='%cn' "$sha") || \
    die "IDENTITY_GATE_GIT_ERROR" "读取 committer_name 失败：$sha"
  committer_email=$(git -C "$REPO" show -s --format='%ce' "$sha") || \
    die "IDENTITY_GATE_GIT_ERROR" "读取 committer_email 失败：$sha"

  [ -n "$author_name" ] || die "IDENTITY_GATE_EMPTY_IDENTITY" "sha=$sha field=author_name"
  [ -n "$author_email" ] || die "IDENTITY_GATE_EMPTY_IDENTITY" "sha=$sha field=author_email"
  [ -n "$committer_name" ] || die "IDENTITY_GATE_EMPTY_IDENTITY" "sha=$sha field=committer_name"
  [ -n "$committer_email" ] || die "IDENTITY_GATE_EMPTY_IDENTITY" "sha=$sha field=committer_email"

  [ "$author_name" = "$EXPECTED_NAME" ] || \
    die "IDENTITY_GATE_MISMATCH" "sha=$sha field=author_name actual=$author_name expected=$EXPECTED_NAME"
  [ "$author_email" = "$EXPECTED_EMAIL" ] || \
    die "IDENTITY_GATE_MISMATCH" "sha=$sha field=author_email actual=$author_email expected=$EXPECTED_EMAIL"
  [ "$committer_name" = "$EXPECTED_NAME" ] || \
    die "IDENTITY_GATE_MISMATCH" "sha=$sha field=committer_name actual=$committer_name expected=$EXPECTED_NAME"
  [ "$committer_email" = "$EXPECTED_EMAIL" ] || \
    die "IDENTITY_GATE_MISMATCH" "sha=$sha field=committer_email actual=$committer_email expected=$EXPECTED_EMAIL"

  count=$((count + 1))
  printf 'IDENTITY_GATE_COMMIT_OK: %s\n' "$sha"
done <<EOF
$commit_list
EOF

printf 'IDENTITY_GATE_OK: base=%s head=%s commits=%s expected_name=%s expected_email=%s\n' \
  "$BASE_SHA" "$HEAD_SHA" "$count" "$EXPECTED_NAME" "$EXPECTED_EMAIL"
