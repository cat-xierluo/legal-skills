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
#     （空写范围会让 scope guard 整体不安装），全部在任何副作用之前 exit 64；
#   - Task-114 回归：Claude Code 文件编辑工具名为 Update，必须与
#     Edit/Write/NotebookEdit 走同一条 fail-closed 路径——scope-guard.py
#     工具集、spawn 生成的全部 PreToolUse matcher、claude-code 后端的
#     scope-guard hook 接线三处都不能缺 Update；
#   - Task-114-R2B 回归（真实 Claude Code 2.1.237 负探针）：claude backend
#     的 deny JSON 必须带精确 hookEventName="PreToolUse"，否则 Claude 报
#     hook error 后照写不误；非 claude backend 保持既有协议；非 reviewer
#     角色在自身 Session Context 内的控制面写入（STATUS/RESULT）在窄
#     allowlist 下保持可达，父目录/兄弟 session/仓库代码/config/*.local.yaml
#     仍拒绝。
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

# 本测试会在真实 reviewer 会话内运行：外层环境自带 SCOPE_GUARD_ROLE/
# SCOPE_GUARD_SESSION_ROOT/SCOPE_GUARD_REVIEW_REPAIR_GRANT/SCOPE_GUARD_ALLOW。
# `env` 只做增量注入，不清继承变量——不清掉的话 implementer/no-role 案例
# 会被外层 reviewer 角色污染成 deny。每次调用 hook 前先 unset 这五个变量
# （含 WORKER_GUARD_BACKEND：deny 协议按 backend 分叉，必须由案例显式指定），
# 再应用测试案例显式传入的 env，使 reviewer/implementer/no-role 案例互相
# 隔离；只收窄测试夹具，不放宽生产 guard 语义。
SCOPE_GUARD_TEST_ENV_ISOLATION=(
  -u SCOPE_GUARD_ROLE
  -u SCOPE_GUARD_SESSION_ROOT
  -u SCOPE_GUARD_REVIEW_REPAIR_GRANT
  -u SCOPE_GUARD_ALLOW
  -u WORKER_GUARD_BACKEND
)

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
  output=$(cd "$FIXTURE" && env "${SCOPE_GUARD_TEST_ENV_ISOLATION[@]}" PWD="$FIXTURE" "${envs[@]}" python3 "$SCOPE_GUARD" <<<"$1" 2>&1)
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
  output=$(cd "$FIXTURE" && env "${SCOPE_GUARD_TEST_ENV_ISOLATION[@]}" PWD="$FIXTURE" "$env_assignee" python3 "$SCOPE_GUARD" <<<"$stdin_json" 2>&1)
  set -e
  # deny reason 经 json.dumps 输出，非 ASCII 会被转义——用 -F 匹配字面片段
  if printf '%s' "$output" | grep -qF "$expected_sub"; then
    passed=$((passed + 1))
  else
    note_fail "$label" "reason missing '$expected_sub' in: $output"
  fi
}

# assert_deny_protocol <label> <expected_hookEventName|-> <env assignments...> -- <stdin JSON>
# 断言 deny JSON 的协议字段：exit 0 + permissionDecision=deny +
# hookSpecificOutput.hookEventName 精确等于期望值（传 "-" 表示必须缺省，
# 锁定非 claude backend 的既有协议不被扩散）。
assert_deny_protocol() {
  local label="$1" expected_event="$2"
  shift 2
  local envs=()
  while [ "$1" != "--" ]; do
    envs+=("$1")
    shift
  done
  shift
  local output exit_code decision event
  set +e
  output=$(cd "$FIXTURE" && env "${SCOPE_GUARD_TEST_ENV_ISOLATION[@]}" PWD="$FIXTURE" "${envs[@]}" python3 "$SCOPE_GUARD" <<<"$1" 2>&1)
  exit_code=$?
  set -e
  decision=$(printf '%s' "$output" | jq -r '.hookSpecificOutput.permissionDecision // "none"')
  event=$(printf '%s' "$output" | jq -r '.hookSpecificOutput.hookEventName // ""')
  local event_ok=0
  if [ "$expected_event" = "-" ]; then
    [ -z "$event" ] && event_ok=1
  elif [ "$event" = "$expected_event" ]; then
    event_ok=1
  fi
  if [ "$decision" = "deny" ] && [ "$exit_code" -eq 0 ] && [ "$event_ok" -eq 1 ]; then
    passed=$((passed + 1))
  else
    note_fail "$label" "expected deny exit=0 hookEventName='${expected_event}', got exit=$exit_code decision=$decision event='$event' output=$output"
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

# -- Task-114 回归：Claude Code Update 工具走同一条 fail-closed 路径 -------------
# 已实证事故（Badminton Lab bl114-review-glm53flash，Claude Code 2.1.237）：
# 文件编辑工具名为 Update，scope-guard.py 只认 Edit/Write/NotebookEdit，
# reviewer 对 Session Context 外 Makefile 的 Update 写入完全不经过 scope guard，
# Session-Context-only 边界被绕过。Update 必须复用 reviewer 层 + allowlist 全路径。

run_hook "reviewer Update outside session context denied (Makefile)" deny \
  "${ROLE_ENVS[@]}" "SCOPE_GUARD_ALLOW=$ALLOW_ALL" -- \
  "{\"tool_name\":\"Update\",\"tool_input\":{\"file_path\":\"$WORKTREE/Makefile\"}}"

run_hook "reviewer Update own session context allowed" allow \
  "${ROLE_ENVS[@]}" "SCOPE_GUARD_ALLOW=$SESSION_ROOT/**" -- \
  "{\"tool_name\":\"Update\",\"tool_input\":{\"file_path\":\"$SESSION_ROOT/RESULT.md\"}}"

run_hook "reviewer Update cannot create skill config local yaml" deny \
  "${ROLE_ENVS[@]}" "SCOPE_GUARD_ALLOW=$ALLOW_ALL" -- \
  "{\"tool_name\":\"Update\",\"tool_input\":{\"file_path\":\"$SKILL_CONFIG/orchestration-personal.local.yaml\"}}"

run_hook "granted reviewer Update follows allowlist (match)" allow \
  "${ROLE_ENVS[@]}" "SCOPE_GUARD_REVIEW_REPAIR_GRANT=1" "SCOPE_GUARD_ALLOW=$ALLOW_ALL" -- \
  "{\"tool_name\":\"Update\",\"tool_input\":{\"file_path\":\"$WORKTREE/skills/multi-agent-orchestration/SKILL.md\"}}"

run_hook "granted reviewer Update follows allowlist (mismatch)" deny \
  "${ROLE_ENVS[@]}" "SCOPE_GUARD_REVIEW_REPAIR_GRANT=1" "SCOPE_GUARD_ALLOW=docs/**" -- \
  "{\"tool_name\":\"Update\",\"tool_input\":{\"file_path\":\"$WORKTREE/Makefile\"}}"

run_hook "implementer Update allowlist match allows" allow \
  "SCOPE_GUARD_ALLOW=$ALLOW_ALL" -- \
  "{\"tool_name\":\"Update\",\"tool_input\":{\"file_path\":\"$WORKTREE/skills/multi-agent-orchestration/SKILL.md\"}}"

run_hook "implementer Update allowlist mismatch denies" deny \
  "SCOPE_GUARD_ALLOW=docs/**" -- \
  "{\"tool_name\":\"Update\",\"tool_input\":{\"file_path\":\"$WORKTREE/Makefile\"}}"

# -- Task-114-R2B 回归：claude backend deny 协议必须带 PreToolUse 事件名 ---------
# 真实负探针（task114-r2-review-glm53flash，Claude Code 2.1.237）：reviewer 对
# 根 README.md 调 Update，scope-guard 输出 deny JSON 但缺
# hookSpecificOutput.hookEventName="PreToolUse"，Claude 报
# `PreToolUse:Edit hook error` 后仍执行写入。缺字段 = deny 不生效。

assert_deny_protocol "claude-code backend reviewer Edit outside session denies with PreToolUse" "PreToolUse" \
  "${ROLE_ENVS[@]}" "WORKER_GUARD_BACKEND=claude-code" "SCOPE_GUARD_ALLOW=$ALLOW_ALL" -- \
  "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"$WORKTREE/README.md\"}}"

assert_deny_protocol "claude-code backend reviewer Update outside session denies with PreToolUse" "PreToolUse" \
  "${ROLE_ENVS[@]}" "WORKER_GUARD_BACKEND=claude-code" "SCOPE_GUARD_ALLOW=$ALLOW_ALL" -- \
  "{\"tool_name\":\"Update\",\"tool_input\":{\"file_path\":\"$WORKTREE/README.md\"}}"

assert_deny_protocol "claude_code backend reviewer Edit outside session denies with PreToolUse" "PreToolUse" \
  "${ROLE_ENVS[@]}" "WORKER_GUARD_BACKEND=claude_code" "SCOPE_GUARD_ALLOW=$ALLOW_ALL" -- \
  "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"$WORKTREE/README.md\"}}"

assert_deny_protocol "claude backend reviewer Update outside session denies with PreToolUse" "PreToolUse" \
  "${ROLE_ENVS[@]}" "WORKER_GUARD_BACKEND=claude" "SCOPE_GUARD_ALLOW=$ALLOW_ALL" -- \
  "{\"tool_name\":\"Update\",\"tool_input\":{\"file_path\":\"$WORKTREE/README.md\"}}"

# 非 claude backend 保持既有协议：仍给 deny 决策，但不扩散 hookEventName
assert_deny_protocol "codebuddy backend keeps legacy deny protocol (no hookEventName)" "-" \
  "${ROLE_ENVS[@]}" "WORKER_GUARD_BACKEND=codebuddy" "SCOPE_GUARD_ALLOW=$ALLOW_ALL" -- \
  "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"$WORKTREE/README.md\"}}"

# -- Task-114-R2B 回归：implementer 自身 Session Context 控制面保持可达 ---------
# deny 真正生效后，窄 --allow-paths 的 implementer 若不能写
# .claude/agent-sessions/<session>/ 内的 STATUS/RESULT，任务闭环直接断裂。
# 放行严格限定在 SESSION_ROOT 自身目录内；父目录、兄弟 session、仓库代码、
# config/*.local.yaml 一律不放宽。

IMPL_ENVS=("SCOPE_GUARD_ROLE=implementer" "SCOPE_GUARD_SESSION_ROOT=$SESSION_ROOT" "SCOPE_GUARD_ALLOW=skills/**")

run_hook "implementer writes own session STATUS under narrow allowlist" allow \
  "${IMPL_ENVS[@]}" -- \
  "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$SESSION_ROOT/STATUS.json\"}}"

run_hook "implementer Update own session RESULT under narrow allowlist" allow \
  "${IMPL_ENVS[@]}" -- \
  "{\"tool_name\":\"Update\",\"tool_input\":{\"file_path\":\"$SESSION_ROOT/RESULT.md\"}}"

run_hook "implementer cannot write session-root parent directory" deny \
  "${IMPL_ENVS[@]}" -- \
  "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$WORKTREE/.claude/agent-sessions/STATUS.json\"}}"

run_hook "implementer cannot write sibling session" deny \
  "${IMPL_ENVS[@]}" -- \
  "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$WORKTREE/.claude/agent-sessions/rev-2/RESULT.md\"}}"

run_hook "implementer cannot write repo code despite session root" deny \
  "${IMPL_ENVS[@]}" -- \
  "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"$WORKTREE/README.md\"}}"

# config/*.local.yaml 不被 Session Context 放行（carve-out：跳过 session 放行
# 后落入 allowlist 判定；去掉 carve-out 本案例会经 session 放行变 allow）
run_hook "implementer session context allow does not cover config local yaml" deny \
  "${IMPL_ENVS[@]}" -- \
  "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$SESSION_ROOT/config/personal.local.yaml\"}}"

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

# -- Task-114 回归：spawn 生成的 PreToolUse matcher 必须全部包含 Update ----------
# 不能只测 Python helper：matcher 缺 Update 时 hook 根本不会被触发，
# scope-guard.py 改得再对也拦不住。matcher 字符串在 spawn-worker.sh 有多处
# 生成点（dependency install guard × 3 backend + scope guard × 各 backend），
# 必须全部一致包含 Update。
# 结构断言：文件中每一个含 NotebookEdit 的引号 matcher 字面量都必须含 Update。

generated_matchers_include_update() {
  local label="$1" matchers missing
  matchers=$(grep -oE '"[A-Za-z|]+NotebookEdit[A-Za-z|]*"' "$SPAWN_WORKER" | sort -u) || true
  if [ -z "$matchers" ]; then
    note_fail "$label" "spawn-worker.sh 找不到任何文件写入类 matcher 字面量（结构变化需同步更新本测试）"
    return
  fi
  missing=$(printf '%s\n' "$matchers" | grep -vF 'Update' || true)
  if [ -z "$missing" ]; then
    passed=$((passed + 1))
  else
    note_fail "$label" "以下生成的 matcher 缺少 Update: $(printf '%s' "$missing" | tr '\n' ' ')"
  fi
}

generated_matchers_include_update "all generated PreToolUse matchers include Update"

# claude-code 是事故后端（bl114-review-glm53flash）：scope_guard_setup 必须给
# .claude/settings.local.json 安装含 Update 的 scope-guard hook。只注入
# SCOPE_GUARD_* env 而不装 hook，Session Context 约束在该后端完全不生效。
claude_code_scope_guard_wired() {
  local label="$1" body
  body=$(sed -n '/^scope_guard_setup()/,/^}/p' "$SPAWN_WORKER")
  if printf '%s\n' "$body" | grep -qF '.claude/settings.local.json' \
    && printf '%s\n' "$body" | grep -qF 'Edit|Write|NotebookEdit|Update'; then
    passed=$((passed + 1))
  else
    note_fail "$label" "scope_guard_setup 未给 claude-code 安装含 Update 的 scope-guard hook"
  fi
}

claude_code_scope_guard_wired "claude-code backend gets scope-guard hook with Update matcher"

rm -rf "$FIXTURE"
echo "reviewer scope guard tests: $passed passed, $failed failed"
[ "$failed" -eq 0 ]
