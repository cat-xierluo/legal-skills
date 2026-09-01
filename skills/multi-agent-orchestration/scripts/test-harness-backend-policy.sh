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

# v2.11.0（P0-④）：zcode 默认不在 claude-code/codex 的 worker backend 白名单
# （配额 lane 独立、人工锁定语义与 Claude/Codex 订阅不同）。显式授权通道 =
# 用户明确编辑 harness-backend-policy.json 把 zcode 加回对应 host（可审计的
# git diff）；canonical 映射保留，策略文件是唯一开关。
for pm in claude-code codex; do
  for worker in claude-code codex codebuddy qoderwork-cn; do
    expect_allow "$pm" "$worker"
  done
  expect_deny "$pm" zcode
done
expect_allow codebuddy codebuddy
expect_allow qoderwork-cn qoderwork-cn

for worker in claude-code codex qoderwork-cn zcode; do expect_deny codebuddy "$worker"; done
for worker in claude-code codex codebuddy zcode; do expect_deny qoderwork-cn "$worker"; done
expect_deny unknown codebuddy
expect_deny codex custom

# Exercise real ancestry detection through executables named as weak harnesses.
ln -s /bin/bash "$TMP_ROOT/codebuddy"
ln -s /bin/bash "$TMP_ROOT/codex"
ln -s /bin/bash "$TMP_ROOT/claude"
ln -s /bin/bash "$TMP_ROOT/qoderclicn"
mkdir -p "$TMP_ROOT/non-orca-project"
if ORCA_CLI_COMMAND=/usr/bin/false "$TMP_ROOT/codebuddy" -c 'bash "$1" --project "$2" --pm-harness codebuddy --worker-backend codebuddy; :' _ \
  "$SCRIPT_DIR/harness-backend-policy.sh" "$TMP_ROOT/non-orca-project" >/dev/null 2>&1; then
  printf 'PASS ancestry allow: codebuddy -> codebuddy\n'
  pass=$((pass + 1))
else
  printf 'FAIL ancestry allow: codebuddy -> codebuddy\n' >&2
  fail=$((fail + 1))
fi
weak_rc=0
ORCA_CLI_COMMAND=/usr/bin/false "$TMP_ROOT/codebuddy" -c 'bash "$1" --project "$2" --pm-harness claude-code --worker-backend codex; rc=$?; :; exit "$rc"' _ \
  "$SCRIPT_DIR/harness-backend-policy.sh" "$TMP_ROOT/non-orca-project" >/dev/null 2>&1 || weak_rc=$?
if [ "$weak_rc" -eq 64 ]; then
  printf 'PASS ancestry deny: codebuddy cannot assert claude-code or dispatch codex\n'
  pass=$((pass + 1))
else
  printf 'FAIL ancestry deny: codebuddy escalation exit=%s\n' "$weak_rc" >&2
  fail=$((fail + 1))
fi
if ORCA_CLI_COMMAND=/usr/bin/false "$TMP_ROOT/qoderclicn" -c 'bash "$1" --project "$2" --pm-harness qoderwork-cn --worker-backend qoderwork-cn; :' _ \
  "$SCRIPT_DIR/harness-backend-policy.sh" "$TMP_ROOT/non-orca-project" >/dev/null 2>&1; then
  printf 'PASS ancestry allow: qoderwork-cn -> qoderwork-cn\n'
  pass=$((pass + 1))
else
  printf 'FAIL ancestry allow: qoderwork-cn -> qoderwork-cn\n' >&2
  fail=$((fail + 1))
fi

# A weak outer Harness cannot regain stronger authority by starting a nested
# strong CLI. The effective permission is the intersection of every ancestor.
nested_rc=0
ORCA_CLI_COMMAND=/usr/bin/false PATH="$TMP_ROOT:$PATH" "$TMP_ROOT/codebuddy" -c '
  codex -c '\''bash "$1" --project "$2" --pm-harness codex --worker-backend claude-code; rc=$?; :; exit "$rc"'\'' _ "$1" "$2"
  rc=$?; :; exit "$rc"
' _ "$SCRIPT_DIR/harness-backend-policy.sh" "$TMP_ROOT/non-orca-project" >/dev/null 2>&1 || nested_rc=$?
if [ "$nested_rc" -eq 64 ]; then
  printf 'PASS ancestry intersection: codebuddy -> codex cannot dispatch claude-code\n'
  pass=$((pass + 1))
else
  printf 'FAIL ancestry intersection: nested escalation exit=%s\n' "$nested_rc" >&2
  fail=$((fail + 1))
fi

strong_nested_out=""
if strong_nested_out=$(ORCA_CLI_COMMAND=/usr/bin/false PATH="$TMP_ROOT:$PATH" "$TMP_ROOT/claude" -c '
  codex -c '\''bash "$1" --project "$2" --pm-harness codex --worker-backend codebuddy; rc=$?; :; exit "$rc"'\'' _ "$1" "$2"
  rc=$?; :; exit "$rc"
' _ "$SCRIPT_DIR/harness-backend-policy.sh" "$TMP_ROOT/non-orca-project" 2>&1) \
  && printf '%s' "$strong_nested_out" | grep -q 'allowed=claude-code codex codebuddy qoderwork-cn'; then
  printf 'PASS ancestry intersection: strong nested chain keeps the four-backend set\n'
  pass=$((pass + 1))
else
  printf 'FAIL ancestry intersection: strong chain unexpectedly denied: %s\n' "$strong_nested_out" >&2
  fail=$((fail + 1))
fi

blocked_repo="$TMP_ROOT/blocked-repo"
mkdir -p "$blocked_repo"
git -C "$blocked_repo" init -q
git -C "$blocked_repo" -c user.name=Smoke -c user.email=smoke@example.invalid \
  commit --allow-empty -q -m init
blocked_rc=0
ORCA_CLI_COMMAND=/usr/bin/false "$TMP_ROOT/codebuddy" -c '
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


label_mismatch_rc=0
ORCA_CLI_COMMAND=/usr/bin/false PATH="$TMP_ROOT:$PATH" "$TMP_ROOT/codebuddy" -c '
  bash "$1" --project "$2" --branch feat/label-mismatch --session label-mismatch \
    --worker-backend codebuddy --command codex \
    --allow-prompt-only-install-guard "identity mismatch must never degrade" \
    --no-orca-mode --dry-run
' _ "$SCRIPT_DIR/spawn-worker.sh" "$blocked_repo" >/dev/null 2>&1 || label_mismatch_rc=$?
if [ "$label_mismatch_rc" -eq 64 ] \
  && ! git -C "$blocked_repo" show-ref --verify --quiet refs/heads/feat/label-mismatch \
  && [ ! -e "$blocked_repo/.claude/worktrees/tmux-feat-label-mismatch" ]; then
  printf 'PASS backend/command binding: codebuddy label cannot launch codex even with degraded install guard\n'
  pass=$((pass + 1))
else
  printf 'FAIL backend/command binding: mismatch exit=%s branch/worktree may exist\n' "$label_mismatch_rc" >&2
  fail=$((fail + 1))
fi

DETECTED_PM_HARNESS=""
runtime_rc=0
process_probe_rc=0
orca_probe_rc=0
process_probe=$(pm_harness_from_process "$PPID" 2>/dev/null) || process_probe_rc=$?
process_probe_host=$(printf '%s\n' "$process_probe" | sed -n '1p')
orca_probe_host=$(pm_harness_from_orca "" 2>/dev/null) || orca_probe_rc=$?
detect_pm_harness "" 2>/dev/null || runtime_rc=$?
detected="$DETECTED_PM_HARNESS"
if [ "$runtime_rc" -eq 0 ] && [ -n "$detected" ]; then
  printf 'PASS runtime detection: %s\n' "$detected"
  pass=$((pass + 1))
elif [ "$runtime_rc" -eq 64 ] \
  && [ "$process_probe_rc" -eq 0 ] && [ -n "$process_probe_host" ] \
  && [ "$orca_probe_rc" -eq 0 ] && [ -n "$orca_probe_host" ] \
  && [ "$process_probe_host" != "$orca_probe_host" ]; then
  printf 'PASS runtime detection conflict fails closed: process=%s orca=%s\n' \
    "$process_probe_host" "$orca_probe_host"
  pass=$((pass + 1))
else
  printf 'FAIL runtime detection in active Agent session: exit=%s value=%s\n' "$runtime_rc" "$detected" >&2
  fail=$((fail + 1))
fi

printf 'SUMMARY: pass=%d fail=%d\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
