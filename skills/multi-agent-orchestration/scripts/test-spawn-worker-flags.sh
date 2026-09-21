#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
FLAGS_HELPER="$SCRIPT_DIR/spawn-worker-flags.sh"
SPAWN_WORKER="$SCRIPT_DIR/spawn-worker.sh"

passed=0
failed=0

ok() {
  printf 'PASS: %s\n' "$1"
  passed=$((passed + 1))
}

bad() {
  printf 'FAIL: %s\n' "$1" >&2
  failed=$((failed + 1))
}

assert_eq() {
  local actual="$1" expected="$2" label="$3"
  if [ "$actual" = "$expected" ]; then
    ok "$label"
  else
    bad "$label (expected=$expected actual=$actual)"
  fi
}

reset_defaults() {
  PROJECT_DIR=""
  BRANCH=""
  WORKTREE=""
  SESSION=""
  BASE_REF="main"
  BRANCH_LIFECYCLE="ephemeral-worker"
  COMMAND=""
  DRY_RUN=0
  WORKER_BACKEND=""
  PM_HARNESS_ASSERTION=""
  RUNTIME_PROFILE=""
  API_PROVIDER=""
  MODEL=""
  PROVIDER_SLOT=""
  ENV_ISOLATION=""
  WAVE_ID=""
  WAVE_WORKER_ID=""
  VERIFY_COMMANDS=()
  VERIFY_COMMAND_SOURCE=""
  REQUIRE_VERIFICATION=0
  VERIFICATION_CONTRACT=""
  VERIFICATION_TASK_ID=""
  PROJECT_CONFIG_FILE=""
  WORKER_TYPE=""
  WITH_SENTINEL=0
  SENTINEL_POLL_INTERVAL=5
  SENTINEL_MAX_WAIT=7200
  KEEP_TMUX_ON_TERMINAL=0
  TRUST_AUTO_OVERRIDE=0
  TRUST_AUTO=1
  PERMISSION_AUTO_OVERRIDE=0
  PERMISSION_AUTO=1
  PERMISSION_AUTO_BG_OVERRIDE=0
  PERMISSION_AUTO_BG=1
  EXTERNAL_IMPORTS_AUTO_OVERRIDE=0
  EXTERNAL_IMPORTS_AUTO=0
  QUOTA_PREFLIGHT_OVERRIDE=0
  QUOTA_PREFLIGHT_OVERRIDE_SOURCE=""
  ADD_DIRS=()
  ALLOW_PATHS=()
  LIGHTWEIGHT_OVERRIDE=0
  LIGHTWEIGHT_MODE=0
  NO_ORCA_MODE=0
  ORCA_SETUP_MODE="skip"
  ORCA_SUPERVISED=0
  TASK_SPEC=""
  TASK_TITLE=""
  ORCA_RUN_ID=""
  ORCA_TASK_ID=""
  ORCA_COORDINATOR_HANDLE=""
  INSTALL_AUTHORIZATION_SOURCE=""
  AUTHORIZED_INSTALL_COMMANDS=()
  ALLOWED_SHELL_COMMANDS=()
  GIT_EXPECTED_NAME=""
  GIT_EXPECTED_EMAIL=""
  GIT_INTEGRATION_BASE=""
  GIT_PUSH_REMOTE="origin"
  ALLOW_PROMPT_ONLY_INSTALL_GUARD=0
  INSTALL_GUARD_DEGRADATION_SOURCE=""
  DEPS_MODE="auto"
}

# shellcheck source=spawn-worker-flags.sh
source "$FLAGS_HELPER"

reset_defaults
parse_spawn_worker_args \
  --project "/tmp/project path" --branch "feat/flags" --worktree "/tmp/worker path" \
  --session "flags-session" --base-ref "origin/main" --command "codex exec" \
  --branch-lifecycle long-lived \
  --worker-backend codex --pm-harness codex --runtime-profile strict \
  --api-provider provider-a --model model-a --provider-slot slot-a \
  --env-isolation isolated --wave-id wave-a --wave-worker-id worker-a \
  --verify-cmd "bash test-a.sh" --verify-cmd "bash test-b.sh" \
  --require-verification --worker-type contract-extension \
  --with-sentinel --sentinel-poll-interval 7 --sentinel-max-wait 90 \
  --keep-tmux-on-terminal --no-trust-auto --trust-auto \
  --no-permission-auto --permission-auto --no-permission-auto-bg \
  --no-external-imports-auto --external-imports-auto \
  --quota-preflight-override "PM 已确认额度恢复，人工授权放行" \
  --add-dir /tmp/a --add-dir "/tmp/b path" \
  --allow-paths "skills/a/**" --allow-paths "skills/b/**" \
  --no-worktree --no-orca-mode --orca-setup-mode skip --orca-supervised \
  --task-spec "full spec" --task-title "short title" \
  --orca-run-id run-a --orca-task-id task-a --orca-coordinator-handle term-pm \
  --allow-install-command "pip install demo" \
  --install-authorization-source "user approval" \
  --allow-shell-command "git status" \
  --deps-mode local \
  --git-expected-name "Expected User" --git-expected-email expected@example.com \
  --git-integration-base origin/main --git-push-remote upstream \
  --allow-prompt-only-install-guard "accepted degradation" --dry-run

assert_eq "$PROJECT_DIR" "/tmp/project path" "project preserves spaces"
assert_eq "$BRANCH" "feat/flags" "branch parsed"
assert_eq "$BRANCH_LIFECYCLE" "long-lived" "branch lifecycle parsed"
assert_eq "$SESSION" "flags-session" "session parsed"
assert_eq "$WORKER_BACKEND" "codex" "backend parsed"
assert_eq "$WITH_SENTINEL:$KEEP_TMUX_ON_TERMINAL" "1:1" "sentinel booleans parsed"
assert_eq "$TRUST_AUTO:$TRUST_AUTO_OVERRIDE" "1:1" "last trust toggle wins"
assert_eq "$PERMISSION_AUTO:$PERMISSION_AUTO_BG" "1:0" "permission toggles remain independently overridable"
assert_eq "$EXTERNAL_IMPORTS_AUTO:$EXTERNAL_IMPORTS_AUTO_OVERRIDE" "1:1" "external import toggle parsed"
assert_eq "$QUOTA_PREFLIGHT_OVERRIDE:$QUOTA_PREFLIGHT_OVERRIDE_SOURCE" \
  "1:PM 已确认额度恢复，人工授权放行" "quota preflight override requires authorization source"
if grep -Fq -- '--no-claude-code-bare-auto-degrade' "$FLAGS_HELPER"; then
  bad "v2.11.0: --bare auto-degrade opt-out flag is removed"
else
  ok "v2.11.0: --bare auto-degrade opt-out flag is removed"
fi
assert_eq "$LIGHTWEIGHT_MODE:$NO_ORCA_MODE:$ORCA_SUPERVISED" "1:1:1" "transport mode flags parsed"
assert_eq "$ORCA_SETUP_MODE" "skip" "Orca Setup policy parses explicitly"
assert_eq "$ORCA_RUN_ID:$ORCA_TASK_ID:$ORCA_COORDINATOR_HANDLE" "run-a:task-a:term-pm" "Wave receipt identifiers parsed"
assert_eq "$GIT_EXPECTED_NAME:$GIT_EXPECTED_EMAIL:$GIT_INTEGRATION_BASE:$GIT_PUSH_REMOTE" \
  "Expected User:expected@example.com:origin/main:upstream" "safe-push identity fields parsed"
assert_eq "$ALLOW_PROMPT_ONLY_INSTALL_GUARD:$INSTALL_GUARD_DEGRADATION_SOURCE:$DRY_RUN" \
  "1:accepted degradation:1" "degradation receipt and dry-run parsed"
assert_eq "${#VERIFY_COMMANDS[@]}:${VERIFY_COMMANDS[0]}:${VERIFY_COMMANDS[1]}" \
  "2:bash test-a.sh:bash test-b.sh" "repeatable verify commands preserve order"
assert_eq "$REQUIRE_VERIFICATION:$WORKER_TYPE" "1:contract-extension" \
  "verification requirement and worker type parsed"
assert_eq "${#ADD_DIRS[@]}:${ADD_DIRS[1]}" "2:/tmp/b path" "repeatable add-dir preserves spaces"
assert_eq "${#ALLOW_PATHS[@]}:${ALLOW_PATHS[0]}:${ALLOW_PATHS[1]}" \
  "2:skills/a/**:skills/b/**" "repeatable scope globs preserve order"
assert_eq "${#AUTHORIZED_INSTALL_COMMANDS[@]}:${AUTHORIZED_INSTALL_COMMANDS[0]}" \
  "1:pip install demo" "install authorization command parsed"
assert_eq "${#ALLOWED_SHELL_COMMANDS[@]}:${ALLOWED_SHELL_COMMANDS[0]}" \
  "1:git status" "allowed shell command parsed"
assert_eq "$DEPS_MODE" "local" "deps-mode parsed"

set +e
help_output=$( (parse_spawn_worker_args --help) 2>&1 )
help_rc=$?
unknown_output=$( (parse_spawn_worker_args --unknown-flag) 2>&1 )
unknown_rc=$?
set -e

assert_eq "$help_rc" "0" "help exits zero"
if printf '%s' "$help_output" | grep -Fq 'spawn-worker.sh --project PATH'; then
  ok "help text remains available from helper"
else
  bad "help text remains available from helper"
fi
if printf '%s' "$help_output" | grep -Fq -- '--deps-mode'; then
  ok "usage documents --deps-mode"
else
  bad "usage documents --deps-mode"
fi
if printf '%s' "$help_output" | grep -Fq -- '--branch-lifecycle'; then
  ok "usage documents branch lifecycle"
else
  bad "usage documents branch lifecycle"
fi
assert_eq "$unknown_rc" "64" "unknown flag keeps exit 64"
if printf '%s' "$unknown_output" | grep -Fq 'Unknown argument: --unknown-flag'; then
  ok "unknown flag keeps diagnostic"
else
  bad "unknown flag keeps diagnostic"
fi

set +e
invalid_deps_output=$( (parse_spawn_worker_args --deps-mode nonsense) 2>&1 )
invalid_deps_rc=$?
invalid_setup_output=$( (parse_spawn_worker_args --orca-setup-mode unsafe) 2>&1 )
invalid_setup_rc=$?
set -e
assert_eq "$invalid_deps_rc" "64" "invalid --deps-mode keeps exit 64"
if printf '%s' "$invalid_deps_output" | grep -Fq 'only accepts auto|symlink|local'; then
  ok "invalid --deps-mode keeps diagnostic"
else
  bad "invalid --deps-mode keeps diagnostic"
fi
assert_eq "$invalid_setup_rc" "64" "invalid --orca-setup-mode keeps exit 64"
if printf '%s' "$invalid_setup_output" | grep -Fq 'only accepts skip|inherit|run'; then
  ok "invalid --orca-setup-mode keeps diagnostic"
else
  bad "invalid --orca-setup-mode keeps diagnostic"
fi

if grep -Fq 'source "$SCRIPT_DIR/spawn-worker-flags.sh"' "$SPAWN_WORKER" \
  && grep -Fq 'parse_spawn_worker_args "$@"' "$SPAWN_WORKER" \
  && ! grep -Fq 'while [[ $# -gt 0 ]]' "$SPAWN_WORKER"; then
  ok "entrypoint delegates parsing without retaining legacy loop"
else
  bad "entrypoint delegates parsing without retaining legacy loop"
fi

# v2.27.1：--base-ref 40-hex sha 在任何 worktree/provider/terminal 副作用之前拒绝。
# 用 --dry-run 复用既有早停机制（run() 与 write_*() 都会跳过），并要求
# PROJECT_DIR 是一个已存在的目录（spawn-worker.sh 第 299 行 cd + pwd 必走）。
hex_proj=$(mktemp -d "${TMPDIR:-/tmp}/spawn-base-ref-hex.XXXXXX")
set +e
hex_out=$(
  bash "$SPAWN_WORKER" \
    --project "$hex_proj" --session "test-base-hex" --branch "feat/base-hex" \
    --base-ref "abcdef1234567890abcdef1234567890abcdef12" \
    --command "true" --worker-backend claude-code --no-worktree --dry-run 2>&1
)
hex_rc=$?
set -e
if [ "$hex_rc" -ne 0 ] && printf '%s' "$hex_out" | grep -Fq 'SPAWN_WORKER_BASE_REF_MUST_BE_REF'; then
  ok "40-hex --base-ref rejected before any side effect"
else
  bad "40-hex --base-ref rejected before any side effect (rc=$hex_rc)"
  printf '%s\n' "$hex_out" >&2
fi
if [ ! -d "$hex_proj/.claude/worktrees" ] && [ ! -d "$hex_proj/.claude/agent-sessions" ]; then
  ok "40-hex rejection did not create worktree or session context"
else
  bad "40-hex rejection must not create worktree or session context (found under $hex_proj/.claude)"
fi
rm -rf "$hex_proj"

# v2.27.3：--base-ref 大写 40-hex 同样在任何 worktree/provider/terminal 副作用
# 之前拒绝（字符类 [0-9a-f]→[0-9a-fA-F]，防止 96A304DF… 绕过）。用法与 v2.27.1
# 40-hex 用例完全镜像，仅把基线值改为大写；断言 rc=64 + 拒绝消息 +
# 无 worktree/METADATA 副作用一并回归。
upper_hex_proj=$(mktemp -d "${TMPDIR:-/tmp}/spawn-base-ref-upper-hex.XXXXXX")
set +e
upper_hex_out=$(
  bash "$SPAWN_WORKER" \
    --project "$upper_hex_proj" --session "test-base-upper-hex" --branch "feat/base-upper-hex" \
    --base-ref "96A304DF1234567890ABCDEF1234567890ABCDEF" \
    --command "true" --worker-backend claude-code --no-worktree --dry-run 2>&1
)
upper_hex_rc=$?
set -e
if [ "$upper_hex_rc" -ne 0 ] && printf '%s' "$upper_hex_out" | grep -Fq 'SPAWN_WORKER_BASE_REF_MUST_BE_REF'; then
  ok "uppercase 40-hex --base-ref rejected before any side effect"
else
  bad "uppercase 40-hex --base-ref rejected before any side effect (rc=$upper_hex_rc)"
  printf '%s\n' "$upper_hex_out" >&2
fi
if [ ! -d "$upper_hex_proj/.claude/worktrees" ] && [ ! -d "$upper_hex_proj/.claude/agent-sessions" ]; then
  ok "uppercase 40-hex rejection did not create worktree or session context"
else
  bad "uppercase 40-hex rejection must not create worktree or session context (found under $upper_hex_proj/.claude)"
fi
rm -rf "$upper_hex_proj"

# v2.27.3：大小写混合 40-hex 同样拒绝（防御性，断言正则严格区分大小写——
# 单纯改大小写不绕开；真实上游通常给出统一小写但不能依赖）。
mixed_hex_proj=$(mktemp -d "${TMPDIR:-/tmp}/spawn-base-ref-mixed-hex.XXXXXX")
set +e
mixed_hex_out=$(
  bash "$SPAWN_WORKER" \
    --project "$mixed_hex_proj" --session "test-base-mixed-hex" --branch "feat/base-mixed-hex" \
    --base-ref "AbCdEf1234567890aBcDeF1234567890AbCdEf12" \
    --command "true" --worker-backend claude-code --no-worktree --dry-run 2>&1
)
mixed_hex_rc=$?
set -e
if [ "$mixed_hex_rc" -ne 0 ] && printf '%s' "$mixed_hex_out" | grep -Fq 'SPAWN_WORKER_BASE_REF_MUST_BE_REF'; then
  ok "mixed-case 40-hex --base-ref rejected before any side effect"
else
  bad "mixed-case 40-hex --base-ref rejected before any side effect (rc=$mixed_hex_rc)"
  printf '%s\n' "$mixed_hex_out" >&2
fi
rm -rf "$mixed_hex_proj"

# v2.27.3：大写 hex 形态的分支名若真实存在（refs/heads/<v> 大小写敏感），
# 仍应放行——show-ref/--verify 是精确路径匹配，新建 DEADBEEF2 这样的分支
# 不应被守卫误伤。建在临时 fixture 仓库里，跑完即抛。
deadbeef_proj=$(mktemp -d "${TMPDIR:-/tmp}/spawn-base-ref-deadbeef.XXXXXX")
git -C "$deadbeef_proj" init -q -b main
git -C "$deadbeef_proj" -c user.name=test -c user.email=test@example.com commit --allow-empty -q -m seed
git -C "$deadbeef_proj" checkout -q -b DEADBEEF2
deadbeef_branch=$(git -C "$deadbeef_proj" rev-parse --verify DEADBEEF2)
set +e
deadbeef_out=$(
  bash "$SPAWN_WORKER" \
    --project "$deadbeef_proj" --session "test-base-deadbeef" --branch "feat/base-deadbeef" \
    --base-ref "DEADBEEF2" \
    --command "true" --worker-backend claude-code --no-worktree --dry-run 2>&1
)
deadbeef_rc=$?
set -e
if printf '%s' "$deadbeef_out" | grep -Fq 'SPAWN_WORKER_BASE_REF_MUST_BE_REF'; then
  bad "uppercase-hex real branch DEADBEEF2 must not trigger BASE_REF_MUST_BE_REF (rc=$deadbeef_rc)"
  printf '%s\n' "$deadbeef_out" >&2
else
  ok "uppercase-hex real branch DEADBEEF2 proceeds past base-ref gate"
fi
rm -rf "$deadbeef_proj"

# v2.27.1：--base-ref main 正常进入后续（不触发 BASE_REF_MUST_BE_REF 拒绝）。
# 这里只断言我们的拒绝消息没有出现，不强求 0 退出——后续步骤在临时空目录
# 下可能因 harness/lease 等真实副作用前的检测而以非零退出，但本任务不关心。
main_proj=$(mktemp -d "${TMPDIR:-/tmp}/spawn-base-ref-main.XXXXXX")
set +e
main_out=$(
  bash "$SPAWN_WORKER" \
    --project "$main_proj" --session "test-base-main" --branch "feat/base-main" \
    --base-ref "main" \
    --command "true" --worker-backend claude-code --no-worktree --dry-run 2>&1
)
main_rc=$?
set -e
if printf '%s' "$main_out" | grep -Fq 'SPAWN_WORKER_BASE_REF_MUST_BE_REF'; then
  bad "--base-ref main must not trigger BASE_REF_MUST_BE_REF (rc=$main_rc)"
  printf '%s\n' "$main_out" >&2
else
  ok "--base-ref main proceeds past base-ref gate"
fi
rm -rf "$main_proj"

printf 'spawn-worker flags tests: %s passed, %s failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
