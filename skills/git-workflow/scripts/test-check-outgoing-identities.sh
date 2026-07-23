#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
GATE="$SCRIPT_DIR/check-outgoing-identities.sh"
SAFE_PUSH="$SCRIPT_DIR/safe-push.sh"

pass=0
fail=0

ok() {
  printf 'PASS: %s\n' "$1"
  pass=$((pass + 1))
}

not_ok() {
  printf 'FAIL: %s\n' "$1" >&2
  fail=$((fail + 1))
}

expect_ok() {
  local name="$1"
  shift
  if "$@" >/tmp/git-identity-gate.out 2>/tmp/git-identity-gate.err; then
    ok "$name"
  else
    cat /tmp/git-identity-gate.out /tmp/git-identity-gate.err >&2 || true
    not_ok "$name"
  fi
}

expect_fail_contains() {
  local name="$1"
  local expected="$2"
  shift 2
  if "$@" >/tmp/git-identity-gate.out 2>/tmp/git-identity-gate.err; then
    not_ok "$name (unexpected success)"
    return
  fi
  if grep -qF "$expected" /tmp/git-identity-gate.out /tmp/git-identity-gate.err; then
    ok "$name"
  else
    cat /tmp/git-identity-gate.out /tmp/git-identity-gate.err >&2 || true
    not_ok "$name (missing: $expected)"
  fi
}

commit_as() {
  local repo="$1"
  local author_name="$2"
  local author_email="$3"
  local committer_name="$4"
  local committer_email="$5"
  local message="$6"
  printf '%s\n' "$message" >> "$repo/history.txt"
  git -C "$repo" add history.txt
  GIT_AUTHOR_NAME="$author_name" \
  GIT_AUTHOR_EMAIL="$author_email" \
  GIT_COMMITTER_NAME="$committer_name" \
  GIT_COMMITTER_EMAIL="$committer_email" \
    git -C "$repo" commit -m "$message" >/dev/null
}

tmp_root=$(mktemp -d "${TMPDIR:-/tmp}/git-identity-gate.XXXXXX")
trap 'rm -rf "$tmp_root" /tmp/git-identity-gate.out /tmp/git-identity-gate.err' EXIT

repo="$tmp_root/repo"
remote="$tmp_root/remote.git"
git init --bare "$remote" >/dev/null
git init -b main "$repo" >/dev/null
git -C "$repo" remote add origin "$remote"
commit_as "$repo" "maoking" "secretxierluo@gmail.com" "maoking" "secretxierluo@gmail.com" "base"
git -C "$repo" push -u origin main >/dev/null
git -C "$repo" switch -c feat/test >/dev/null

commit_as "$repo" "maoking" "secretxierluo@gmail.com" "maoking" "secretxierluo@gmail.com" "clean-one"
commit_as "$repo" "maoking" "secretxierluo@gmail.com" "maoking" "secretxierluo@gmail.com" "clean-two"

expect_ok "explicit base scans all clean commits" \
  "$GATE" --repo "$repo" --base origin/main \
  --expected-name maoking --expected-email secretxierluo@gmail.com

git -C "$repo" branch --set-upstream-to=origin/main feat/test >/dev/null
expect_ok "upstream auto-detection" \
  "$GATE" --repo "$repo" \
  --expected-name maoking --expected-email secretxierluo@gmail.com

git -C "$repo" branch --unset-upstream
expect_fail_contains "missing upstream fails closed" "IDENTITY_GATE_BASE_UNKNOWN" \
  "$GATE" --repo "$repo" \
  --expected-name maoking --expected-email secretxierluo@gmail.com

expect_fail_contains "bad explicit base fails closed" "IDENTITY_GATE_BAD_BASE" \
  "$GATE" --repo "$repo" --base refs/heads/does-not-exist \
  --expected-name maoking --expected-email secretxierluo@gmail.com

expect_fail_contains "local commit-ish cannot narrow the audited range" "IDENTITY_GATE_BASE_NOT_REMOTE" \
  "$GATE" --repo "$repo" --base HEAD~1 \
  --expected-name maoking --expected-email secretxierluo@gmail.com

git -C "$repo" reset --hard origin/main >/dev/null
commit_as "$repo" "Polluted Worker" "polluted@example.invalid" "Polluted Worker" "polluted@example.invalid" "polluted-early"
commit_as "$repo" "maoking" "secretxierluo@gmail.com" "maoking" "secretxierluo@gmail.com" "clean-head"
expect_fail_contains "early polluted commit is not hidden by clean HEAD" "IDENTITY_GATE_MISMATCH" \
  "$GATE" --repo "$repo" --base origin/main \
  --expected-name maoking --expected-email secretxierluo@gmail.com

git -C "$repo" push -u origin feat/test >/dev/null
expect_fail_contains "feature upstream cannot hide a previously pushed polluted commit" "IDENTITY_GATE_BASE_AMBIGUOUS" \
  "$GATE" --repo "$repo" \
  --expected-name maoking --expected-email secretxierluo@gmail.com

git -C "$repo" reset --hard origin/main >/dev/null
commit_as "$repo" "maoking" "secretxierluo@gmail.com" "maoking" "wrong-committer@example.invalid" "bad-committer"
expect_fail_contains "committer identity is checked separately" "field=committer_email" \
  "$GATE" --repo "$repo" --base origin/main \
  --expected-name maoking --expected-email secretxierluo@gmail.com

git -C "$repo" reset --hard origin/main >/dev/null
expect_fail_contains "empty outgoing range fails closed" "IDENTITY_GATE_EMPTY_RANGE" \
  "$GATE" --repo "$repo" --base origin/main \
  --expected-name maoking --expected-email secretxierluo@gmail.com

git -C "$repo" switch -C feat/safe origin/main >/dev/null
commit_as "$repo" "maoking" "secretxierluo@gmail.com" "maoking" "secretxierluo@gmail.com" "safe-push-head"
expect_ok "safe-push binds verified HEAD oid to pushed ref" \
  "$SAFE_PUSH" --repo "$repo" --base origin/main --remote origin --branch feat/safe \
  --expected-name maoking --expected-email secretxierluo@gmail.com
if [ "$(git -C "$repo" rev-parse HEAD)" = "$(git --git-dir="$remote" rev-parse refs/heads/feat/safe)" ]; then
  ok "safe-push remote ref equals verified oid"
else
  not_ok "safe-push remote ref equals verified oid"
fi

printf 'SUMMARY: pass=%s fail=%s\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
