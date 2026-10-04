#!/usr/bin/env bash
# 在独立临时 Git 仓核验恢复说明；不修改调用者仓库，不联网。
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
DOC="${ACCIDENT_RECOVERY_DOC:-$SCRIPT_DIR/../references/accident-recovery.md}"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
export GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.com
export GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.com
pass=0 fail=0
check() {
  local label="$1"; shift
  if "$@"; then
    printf 'PASS: %s\n' "$label"; pass=$((pass + 1))
  else
    printf 'FAIL: %s\n' "$label" >&2; fail=$((fail + 1))
  fi
}
not_contains() { ! grep -qF -- "$1" "$DOC"; }
check "文档不依赖已删除分支自身reflog" not_contains '在删除后仍可读'
check "文档不把全部未提交内容判为不可恢复" not_contains 'Git 层面无法恢复'

REPO="$WORK/repo"
git init -q -b main "$REPO"
git -C "$REPO" commit -q --allow-empty -m baseline
git -C "$REPO" switch -q -c accident
git -C "$REPO" commit -q --allow-empty -m recovery-marker
expected_tip=$(git -C "$REPO" rev-parse HEAD)
git -C "$REPO" switch -q main
main_tip=$(git -C "$REPO" rev-parse HEAD)
git -C "$REPO" branch -D accident >/dev/null
rc=0; git -C "$REPO" reflog exists refs/heads/accident || rc=$?
check "删分支同时删除该分支reflog" test "$rc" -eq 1
recovered_tip=$(git -C "$REPO" reflog show HEAD --format=%H --grep-reflog='commit: recovery-marker' -1)
git -C "$REPO" branch recovered "$recovered_tip"
check "HEAD reflog定位后可新建分支恢复" test "$(git -C "$REPO" rev-parse recovered)" = "$expected_tip"
check "恢复不移动现有main" test "$(git -C "$REPO" rev-parse main)" = "$main_tip"

# 从未检出的分支：HEAD reflog没有记录，转对象库定位。
tree=$(git -C "$REPO" rev-parse 'HEAD^{tree}')
unseen=$(printf 'never-checked-out\n' | git -C "$REPO" commit-tree "$tree" -p HEAD)
git -C "$REPO" branch unseen "$unseen"
git -C "$REPO" branch -D unseen >/dev/null
candidate=""
while IFS= read -r oid; do
  if [ "$(git -C "$REPO" log -1 --format=%s "$oid")" = 'never-checked-out' ]; then candidate="$oid"; fi
done < <(git -C "$REPO" fsck --no-reflogs --unreachable 2>/dev/null | awk '$2=="commit" {print $3}')
check "未检出分支可用fsck核内容定位" test "$candidate" = "$unseen"
git -C "$REPO" branch recovered-unseen "$candidate"

printf 'STAGED_RECOVERY_PAYLOAD\n' > "$REPO/lost.txt"
git -C "$REPO" add lost.txt
printf 'LATER_UNSTAGED_PAYLOAD\n' > "$REPO/lost.txt"
git -C "$REPO" reset --hard HEAD >/dev/null
check "reset后未提交文件已消失" test ! -e "$REPO/lost.txt"
staged_found=0 later_found=0
while IFS= read -r oid; do
  content=$(git -C "$REPO" cat-file -p "$oid")
  [ "$content" != STAGED_RECOVERY_PAYLOAD ] || staged_found=1
  [ "$content" != LATER_UNSTAGED_PAYLOAD ] || later_found=1
done < <(git -C "$REPO" fsck --no-reflogs --unreachable 2>/dev/null | awk '$2=="blob" {print $3}')
check "fsck+cat-file找回曾暂存的字节" test "$staged_found" -eq 1
check "暂存后更晚编辑没有被误称找回" test "$later_found" -eq 0
printf '\n== 事故恢复回归：%s passed, %s failed ==\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
