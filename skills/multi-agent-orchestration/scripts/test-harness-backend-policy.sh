#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT
# shellcheck source=harness-backend-policy.sh
source "$SCRIPT_DIR/harness-backend-policy.sh"

pass=0
fail=0

expect_allow() {
  local pm="$1" worker="$2"
  if enforce_harness_backend_policy "$pm" "$worker"; then
    printf 'PASS allow: %s -> %s\n' "$pm" "$worker"
    pass=$((pass + 1))
  else
    printf 'FAIL expected allow: %s -> %s\n' "$pm" "$worker" >&2
    fail=$((fail + 1))
  fi
}

expect_deny() {
  local pm="$1" worker="$2"
  if enforce_harness_backend_policy "$pm" "$worker" >/dev/null 2>&1; then
    printf 'FAIL expected deny: %s -> %s\n' "$pm" "$worker" >&2
    fail=$((fail + 1))
  else
    printf 'PASS deny: %s -> %s\n' "$pm" "$worker"
    pass=$((pass + 1))
  fi
}

for pm in claude-code codex; do
  for worker in claude-code codex codebuddy qoderwork-cn; do
    expect_allow "$pm" "$worker"
  done
done
expect_allow codebuddy codebuddy
expect_allow qoderwork-cn qoderwork-cn

for worker in claude-code codex qoderwork-cn; do expect_deny codebuddy "$worker"; done
for worker in claude-code codex codebuddy; do expect_deny qoderwork-cn "$worker"; done
expect_deny unknown codebuddy
expect_deny codex custom

# Exercise real ancestry detection through executables named as weak harnesses.
ln -s /bin/bash "$TMP_ROOT/codebuddy"
ln -s /bin/bash "$TMP_ROOT/qoderclicn"
mkdir -p "$TMP_ROOT/non-orca-project"
if "$TMP_ROOT/codebuddy" -c 'bash "$1" --project "$2" --pm-harness codebuddy --worker-backend codebuddy; :' _ \
  "$SCRIPT_DIR/harness-backend-policy.sh" "$TMP_ROOT/non-orca-project" >/dev/null 2>&1; then
  printf 'PASS ancestry allow: codebuddy -> codebuddy\n'
  pass=$((pass + 1))
else
  printf 'FAIL ancestry allow: codebuddy -> codebuddy\n' >&2
  fail=$((fail + 1))
fi
weak_rc=0
"$TMP_ROOT/codebuddy" -c 'bash "$1" --project "$2" --pm-harness claude-code --worker-backend codex; rc=$?; :; exit "$rc"' _ \
  "$SCRIPT_DIR/harness-backend-policy.sh" "$TMP_ROOT/non-orca-project" >/dev/null 2>&1 || weak_rc=$?
if [ "$weak_rc" -eq 64 ]; then
  printf 'PASS ancestry deny: codebuddy cannot assert claude-code or dispatch codex\n'
  pass=$((pass + 1))
else
  printf 'FAIL ancestry deny: codebuddy escalation exit=%s\n' "$weak_rc" >&2
  fail=$((fail + 1))
fi
if "$TMP_ROOT/qoderclicn" -c 'bash "$1" --project "$2" --pm-harness qoderwork-cn --worker-backend qoderwork-cn; :' _ \
  "$SCRIPT_DIR/harness-backend-policy.sh" "$TMP_ROOT/non-orca-project" >/dev/null 2>&1; then
  printf 'PASS ancestry allow: qoderwork-cn -> qoderwork-cn\n'
  pass=$((pass + 1))
else
  printf 'FAIL ancestry allow: qoderwork-cn -> qoderwork-cn\n' >&2
  fail=$((fail + 1))
fi

blocked_repo="$TMP_ROOT/blocked-repo"
mkdir -p "$blocked_repo"
git -C "$blocked_repo" init -q
git -C "$blocked_repo" -c user.name=Smoke -c user.email=smoke@example.invalid \
  commit --allow-empty -q -m init
blocked_rc=0
"$TMP_ROOT/codebuddy" -c '
  bash "$1" --project "$2" --branch feat/blocked-escalation --session blocked-escalation \
    --worker-backend codex --command "sleep 1" \
    --allow-prompt-only-install-guard "policy fault injection" --no-orca-mode
  rc=$?; :; exit "$rc"
' _ "$SCRIPT_DIR/spawn-worker.sh" "$blocked_repo" >/dev/null 2>&1 || blocked_rc=$?
if [ "$blocked_rc" -eq 64 ] \
  && ! git -C "$blocked_repo" show-ref --verify --quiet refs/heads/feat/blocked-escalation \
  && [ ! -e "$blocked_repo/.claude/worktrees/tmux-feat-blocked-escalation" ]; then
  printf 'PASS spawn side-effect gate: weak harness escalation stops before branch/worktree creation\n'
  pass=$((pass + 1))
else
  printf 'FAIL spawn side-effect gate: exit=%s branch/worktree may exist\n' "$blocked_rc" >&2
  fail=$((fail + 1))
fi

DETECTED_PM_HARNESS=""
runtime_rc=0
detect_pm_harness "" 2>/dev/null || runtime_rc=$?
detected="$DETECTED_PM_HARNESS"
if [ "$runtime_rc" -eq 0 ] && [ -n "$detected" ]; then
  printf 'PASS runtime detection: %s\n' "$detected"
  pass=$((pass + 1))
else
  printf 'FAIL runtime detection in active Agent session: exit=%s value=%s\n' "$runtime_rc" "$detected" >&2
  fail=$((fail + 1))
fi

printf 'SUMMARY: pass=%d fail=%d\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
