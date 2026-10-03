#!/usr/bin/env bash
# 身份及隐私门禁绑定 push：核验完整 PR range，只 push 已核验的 immutable OID。

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
  [ "$#" -ge 2 ] || die "SAFE_PUSH_USAGE" "参数不完整"
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
current_branch=$(git --no-replace-objects -C "$REPO" branch --show-current 2>/dev/null) || \
  die "SAFE_PUSH_NOT_REPOSITORY" "无法读取当前分支：$REPO"
[ -n "$current_branch" ] || die "SAFE_PUSH_DETACHED_HEAD" "detached HEAD 不允许 push"
[ -n "$BRANCH" ] || BRANCH="$current_branch"
[ "$BRANCH" = "$current_branch" ] || \
  die "SAFE_PUSH_BRANCH_MISMATCH" "current=$current_branch requested=$BRANCH"
case "$BASE_REF" in
  */*)
    case "$BASE_REF" in
      "$REMOTE"/*) ;;
      *) die "SAFE_PUSH_BASE_REMOTE_MISMATCH" "base=$BASE_REF 必须属于 remote=${REMOTE}（或不写 remote 前缀、留作裸分支名自动规范化为 ${REMOTE}/<branch>）" ;;
    esac
    ;;
  *)
    # 裸分支名（如 --base main）规范化为 "$REMOTE/<branch>"，与白名单
    # spawn-worker 的常见调用一致；后续 base_branch 派生与 fetch 校验沿用
    # 规范化后的值。含 '/' 但前缀不是 $REMOTE 的情形已被上一种 case 拒绝。
    BASE_REF="${REMOTE}/$BASE_REF"
    ;;
esac

base_branch=${BASE_REF#"$REMOTE"/}
git --no-replace-objects -C "$REPO" fetch -- "$REMOTE" "+refs/heads/$base_branch:refs/remotes/$REMOTE/$base_branch" >/dev/null || \
  die "SAFE_PUSH_FETCH_FAILED" "无法刷新 integration base：$BASE_REF"

verified_base=$(git --no-replace-objects -C "$REPO" rev-parse --verify "$BASE_REF^{commit}") || \
  die "SAFE_PUSH_BAD_BASE" "无法解析已刷新的 integration base"
verified_oid=$(git --no-replace-objects -C "$REPO" rev-parse --verify 'HEAD^{commit}') || \
  die "SAFE_PUSH_BAD_HEAD" "无法解析当前 HEAD"
"$SCRIPT_DIR/check-outgoing-identities.sh" \
  --repo "$REPO" --base "$BASE_REF" --head "$verified_oid" --expected-base-oid "$verified_base" \
  --expected-name "$EXPECTED_NAME" --expected-email "$EXPECTED_EMAIL"
python3 "$SCRIPT_DIR/privacy_check.py" --repo "$REPO" range \
  --base-oid "$verified_base" --head-oid "$verified_oid"
[ "$(git --no-replace-objects -C "$REPO" rev-parse --verify "$BASE_REF^{commit}")" = "$verified_base" ] || \
  die "SAFE_PUSH_BASE_CHANGED" "隐私/身份核验期间 integration base 已变化"
[ "$(git --no-replace-objects -C "$REPO" rev-parse --verify 'HEAD^{commit}')" = "$verified_oid" ] || \
  die "SAFE_PUSH_HEAD_CHANGED" "隐私/身份核验期间 HEAD 已变化；拒绝 push"

git --no-replace-objects -C "$REPO" push -- "$REMOTE" "$verified_oid:refs/heads/$BRANCH"
printf 'SAFE_PUSH_OK: remote=%s branch=%s oid=%s base=%s\n' \
  "$REMOTE" "$BRANCH" "$verified_oid" "$BASE_REF"
