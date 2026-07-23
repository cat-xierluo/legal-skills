#!/usr/bin/env bash
# 身份门禁绑定 push：核验当前 HEAD 的完整 PR range，然后只 push 已核验的 immutable OID。

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO="."
BASE_REF=""
REMOTE="origin"
BRANCH=""
EXPECTED_NAME="${EXPECTED_GIT_NAME:-}"
EXPECTED_EMAIL="${EXPECTED_GIT_EMAIL:-}"

die() {
  local code="$1"
  shift
  printf '%s: %s\n' "$code" "$*" >&2
  exit 1
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --base) BASE_REF="$2"; shift 2 ;;
    --remote) REMOTE="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --expected-name) EXPECTED_NAME="$2"; shift 2 ;;
    --expected-email) EXPECTED_EMAIL="$2"; shift 2 ;;
    *) die "SAFE_PUSH_USAGE" "未知或不完整参数：$1" ;;
  esac
done

[ -n "$BASE_REF" ] || die "SAFE_PUSH_BASE_MISSING" "必须显式提供 PR integration base（例如 origin/main）"
[ -n "$EXPECTED_NAME" ] || die "SAFE_PUSH_IDENTITY_MISSING" "必须提供 expected name"
[ -n "$EXPECTED_EMAIL" ] || die "SAFE_PUSH_IDENTITY_MISSING" "必须提供 expected email"
current_branch=$(git -C "$REPO" branch --show-current 2>/dev/null) || \
  die "SAFE_PUSH_NOT_REPOSITORY" "无法读取当前分支：$REPO"
[ -n "$current_branch" ] || die "SAFE_PUSH_DETACHED_HEAD" "detached HEAD 不允许 push"
[ -n "$BRANCH" ] || BRANCH="$current_branch"
[ "$BRANCH" = "$current_branch" ] || \
  die "SAFE_PUSH_BRANCH_MISMATCH" "current=$current_branch requested=$BRANCH"
case "$BASE_REF" in
  "$REMOTE"/*) ;;
  *) die "SAFE_PUSH_BASE_REMOTE_MISMATCH" "base=$BASE_REF 必须属于 remote=$REMOTE" ;;
esac

base_branch=${BASE_REF#"$REMOTE"/}
git -C "$REPO" fetch -- "$REMOTE" "$base_branch" >/dev/null || \
  die "SAFE_PUSH_FETCH_FAILED" "无法刷新 integration base：$BASE_REF"

verified_oid=$(git -C "$REPO" rev-parse --verify 'HEAD^{commit}') || \
  die "SAFE_PUSH_BAD_HEAD" "无法解析当前 HEAD"
"$SCRIPT_DIR/check-outgoing-identities.sh" \
  --repo "$REPO" --base "$BASE_REF" \
  --expected-name "$EXPECTED_NAME" --expected-email "$EXPECTED_EMAIL"
[ "$(git -C "$REPO" rev-parse --verify 'HEAD^{commit}')" = "$verified_oid" ] || \
  die "SAFE_PUSH_HEAD_CHANGED" "身份核验期间 HEAD 已变化；拒绝 push"

git -C "$REPO" push -- "$REMOTE" "$verified_oid:refs/heads/$BRANCH"
printf 'SAFE_PUSH_OK: remote=%s branch=%s oid=%s base=%s\n' \
  "$REMOTE" "$BRANCH" "$verified_oid" "$BASE_REF"
