#!/usr/bin/env bash
# test-reviewer-scope-guard.sh — reviewer 角色写范围纪律的离线回归（v2.14.0）。
#
# 覆盖：
#   - scope-guard.py reviewer 层：默认只写自身 Session Context；
#     config/*.local.yaml（安装 Skill 的本地运行配置）永远不可写
#     （即便任务合同授予了被审分支修复权）；
#   - 非 reviewer 角色完全保持既有 allowlist 行为（向后兼容）；
#   - spawn-worker.sh 角色校验 fail-closed：坏角色、缺授权的 grant、
#     reviewer 无授权却带 --allow-paths、reviewer 带授权但空 --allow-paths
#     （空写范围会让 scope guard 整体不安装），全部在任何副作用之前 exit 64。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCOPE_GUARD="$SCRIPT_DIR/scope-guard.py"
SPAWN_WORKER="$SCRIPT_DIR/spawn-worker.sh"

passed=0
failed=0

note_fail() {
  failed=$((failed + 1))
  echo "FAIL $1: $2"
}

# run_hook <label> <expected: allow|deny> <env assignments...> -- <stdin JSON>
# hook 子进程以临时 git fixture 为 cwd/PWD：scope-guard 的 allowlist 相对
# 匹配依赖 `git rev-parse --show-toplevel` 解析出的 worktree root。
run_hook() {
  local label="$1" expected="$2"
  shift 2
  local envs=()
  while [ "$1" != "--" ]; do
    envs+=("$1")
    shift
  done
  shift
  local output exit_code decision
  set +e
  output=$(cd "$FIXTURE" && env PWD="$FIXTURE" "${envs[@]}" python3 "$SCOPE_GUARD" <<<"$1" 2>&1)
  exit_code=$?
  set -e
  if [ -z "$output" ]; then
    decision="allow"
  else
    decision=$(printf '%s' "$output" | jq -r '.hookSpecificOutput.permissionDecision // "unknown"')
  fi
  if [ "$decision" = "$expected" ] && [ "$exit_code" -eq 0 ]; then
    passed=$((passed + 1))
  else
    note_fail "$label" "expected=$expected exit=$exit_code decision=$decision output=$output"
  fi
}

deny_reason() {
  local label="$1" expected_sub="$2" env_assignee="$3" stdin_json="$4"
  local output
  set +e
  output=$(cd "$FIXTURE" && env PWD="$FIXTURE" "$env_assignee" python3 "$SCOPE_GUARD" <<<"$stdin_json" 2>&1)
  set -e
  # deny reason 经 json.dumps 输出，非 ASCII 会被转义——用 -F 匹配字面片段
  if printf '%s' "$output" | grep -qF "$expected_sub"; then
    passed=$((passed + 1))
  else
    note_fail "$label" "reason missing '$expected_sub' in: $output"
  fi
}

FIXTURE="$(mktemp -d /tmp/mao-reviewer-fixture.XXXXXX)"
# macOS /tmp 是 /private/tmp 的 symlink：scope-guard 的 allowlist 前缀剥离
# 用 git 返回的物理路径，测试路径必须与之一致（pwd -P 归一）。
FIXTURE="$(cd "$FIXTURE" && pwd -P)"
git -C "$FIXTURE" init -q
WORKTREE="$FIXTURE"
SESSION_ROOT="$WORKTREE/.claude/agent-sessions/rev-1"
SKILL_CONFIG="$WORKTREE/skills/multi-agent-orchestration/config"
ALLOW_ALL="skills/multi-agent-orchestration/**"

ROLE_ENVS=("SCOPE_GUARD_ROLE=reviewer" "SCOPE_GUARD_SESSION_ROOT=$SESSION_ROOT")

# -- reviewer 默认（无修复授权）：只写自身 Session Context ----------------------

run_hook "reviewer writes own session context" allow \
  "${ROLE_ENVS[@]}" "SCOPE_GUARD_ALLOW=$SESSION_ROOT/**" -- \
  "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$SESSION_ROOT/RESULT.md\"}}"

run_hook "reviewer cannot write outside session context" deny \
  "${ROLE_ENVS[@]}" "SCOPE_GUARD_ALLOW=$ALLOW_ALL" -- \
  "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"$WORKTREE/skills/multi-agent-orchestration/SKILL.md\"}}"

# 回归（要求 5）：reviewer 不得在安装 Skill 的 config/ 下创建 *.local.yaml
run_hook "reviewer cannot create skill config *.local.yaml" deny \
  "${ROLE_ENVS[@]}" "SCOPE_GUARD_ALLOW=$ALLOW_ALL" -- \
  "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$SKILL_CONFIG/orchestration-personal.local.yaml\"}}"

run_hook "reviewer cannot create nested config local yaml" deny \
  "${ROLE_ENVS[@]}" "SCOPE_GUARD_ALLOW=$ALLOW_ALL" -- \
  "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$WORKTREE/config/nested/deep.local.yaml\"}}"

deny_reason "config local yaml deny reason names the rule" "reviewer role: config/*.local.yaml" \
  "SCOPE_GUARD_ROLE=reviewer" \
  "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$SKILL_CONFIG/x.local.yaml\"}}"

# -- reviewer 带修复授权：allowlist 生效，config/*.local.yaml 仍然硬拒绝 --------

run_hook "granted reviewer writes allowlisted doc" allow \
  "${ROLE_ENVS[@]}" "SCOPE_GUARD_REVIEW_REPAIR_GRANT=1" "SCOPE_GUARD_ALLOW=$ALLOW_ALL" -- \
  "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"$WORKTREE/skills/multi-agent-orchestration/SKILL.md\"}}"

run_hook "granted reviewer still cannot write config local yaml" deny \
  "${ROLE_ENVS[@]}" "SCOPE_GUARD_REVIEW_REPAIR_GRANT=1" "SCOPE_GUARD_ALLOW=$ALLOW_ALL" -- \
  "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$SKILL_CONFIG/orchestration-personal.local.yaml\"}}"

run_hook "granted reviewer still cannot write outside allowlist" deny \
  "${ROLE_ENVS[@]}" "SCOPE_GUARD_REVIEW_REPAIR_GRANT=1" "SCOPE_GUARD_ALLOW=docs/**" -- \
  "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$WORKTREE/skills/other/secret.md\"}}"

# -- 非 reviewer：既有行为完全不变（向后兼容） ----------------------------------

run_hook "implementer allowlist match allows" allow \
  "SCOPE_GUARD_ALLOW=$ALLOW_ALL" -- \
  "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$WORKTREE/skills/multi-agent-orchestration/SKILL.md\"}}"

run_hook "implementer allowlist mismatch denies" deny \
  "SCOPE_GUARD_ALLOW=docs/**" -- \
  "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$WORKTREE/skills/other/secret.md\"}}"

run_hook "no allow env stays a no-op" allow \
  "SCOPE_GUARD_ALLOW=" -- \
  "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$SKILL_CONFIG/anything.local.yaml\"}}"

run_hook "config local yaml outside config dir is not hard-denied" allow \
  "${ROLE_ENVS[@]}" "SCOPE_GUARD_REVIEW_REPAIR_GRANT=1" "SCOPE_GUARD_ALLOW=docs/**" -- \
  "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$WORKTREE/docs/notes.local.yaml\"}}"

# -- spawn-worker.sh 角色校验（任何副作用之前 fail-closed） ----------------------

spawn_expect_rejected() {
  local label="$1"
  shift
  local output exit_code
  set +e
  output=$(bash "$SPAWN_WORKER" --project /tmp/mao-nonexistent-project --session rev-1 "$@" 2>&1)
  exit_code=$?
  set -e
  if [ "$exit_code" -eq 64 ]; then
    passed=$((passed + 1))
  else
    note_fail "$label" "expected exit 64, got $exit_code: $output"
  fi
}

spawn_expect_rejected "invalid role rejected" --role admin
spawn_expect_rejected "repair grant requires reviewer role" --role implementer --review-repair-grant "task-contract-1"
spawn_expect_rejected "reviewer without grant cannot take allow-paths" --role reviewer --allow-paths 'skills/**'
spawn_expect_rejected "reviewer without grant cannot take allow-paths (second)" --role reviewer --allow-paths 'docs/**' --allow-paths 'README.md'

# R1 回归：reviewer 带修复授权却完全不带 --allow-paths。空 ALLOW_PATHS 会让
# scope_guard_setup 整体跳过（无 SCOPE_GUARD_* env、无 PreToolUse hook），
# Session Context 约束与 config/*.local.yaml 永久拒绝在该次 spawn 全部失守。
# 必须命中空 allow-paths 专用错误、在任何副作用之前 exit 64——用
# SPAWN_WORKER_HARNESS_POLICY（角色校验后第一个阶段标记）未出现证明提前退出。
spawn_grant_empty_allowpaths_rejected() {
  local label="$1"
  shift
  local output exit_code
  set +e
  output=$(bash "$SPAWN_WORKER" --project /tmp/mao-nonexistent-project --session rev-1 "$@" 2>&1)
  exit_code=$?
  set -e
  if [ "$exit_code" -eq 64 ] \
    && printf '%s' "$output" | grep -qF "requires explicit --allow-paths" \
    && ! printf '%s' "$output" | grep -q "SPAWN_WORKER_HARNESS_POLICY"; then
    passed=$((passed + 1))
  else
    note_fail "$label" "expected exit 64 with empty-allow-paths gate before side effects, got exit=$exit_code: $output"
  fi
}

spawn_grant_empty_allowpaths_rejected "granted reviewer without allow-paths rejected before side effects" \
  --role reviewer --review-repair-grant "task-contract-1"

spawn_expect_ok() {
  local label="$1"
  shift
  local output exit_code
  set +e
  output=$(bash "$SPAWN_WORKER" --project /tmp/mao-nonexistent-project --session rev-1 "$@" 2>&1)
  exit_code=$?
  set -e
  # 角色校验通过后才会因假 project 缺 git 等继续失败——但绝不应当再报角色错误
  if printf '%s' "$output" | grep -q "ERROR: --role\|ERROR: --review-repair-grant\|reviewer without .*grant may only"; then
    note_fail "$label" "role gate fired unexpectedly: $output"
  else
    passed=$((passed + 1))
  fi
}

spawn_expect_ok "implementer default passes role gate" --allow-paths 'skills/**'
spawn_expect_ok "reviewer without allow-paths passes role gate" --role reviewer
spawn_expect_ok "reviewer with grant and allow-paths passes role gate" --role reviewer --review-repair-grant "task-contract-1" --allow-paths 'skills/**'

rm -rf "$FIXTURE"
echo "reviewer scope guard tests: $passed passed, $failed failed"
[ "$failed" -eq 0 ]
