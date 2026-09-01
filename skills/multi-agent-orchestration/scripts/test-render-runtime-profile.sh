#!/usr/bin/env bash
# test-render-runtime-profile.sh — renderer hook 契约确定性测试（v2.11.0 P0-② 后续修复）。
#
# 覆盖：
#   1. settings / registry 两路 provider env isolation 默认渲染 hook-capable 命令（无 --bare），
#      wrapper + --setting-sources project,local + --model 契约保留；
#   2. --no-mcp 注入在两路默认路径下保留；
#   3. --claude-bare 显式 opt-in：命令含 --bare，输出上下文标记 degraded/unhooked；
#   4. --claude-bare 错用（非 claude-code / 非 provider 路径 / 关闭 env isolation）fail-closed exit 64；
#   5. 标准 render 输出直接通过 spawn-worker 的 claude hook 检查（无需 PM 字符串 surgery）。
#
# 确定性：不启 tmux、不 spawn worker、不联网；registry/settings 用 config/ 下的 example 文件。
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
RENDERER="$SCRIPT_DIR/render-runtime-profile.sh"
SPAWN_WORKER="$SCRIPT_DIR/spawn-worker.sh"
SETTINGS_EXAMPLE="$SCRIPT_DIR/../config/claude-provider-settings.example.json"
REGISTRY_EXAMPLE="$SCRIPT_DIR/../config/claude-provider-registry.example.json"
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT
PROMPT_FILE="$TMP_ROOT/prompt.md"
printf 'render runtime profile hook contract test\n' > "$PROMPT_FILE"

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

assert_contains() {
  local haystack="$1" needle="$2" label="$3"
  if printf '%s' "$haystack" | grep -Fq -- "$needle"; then
    ok "$label"
  else
    bad "$label (missing: ${needle})"
  fi
}

assert_not_contains() {
  local haystack="$1" needle="$2" label="$3"
  if printf '%s' "$haystack" | grep -Fq -- "$needle"; then
    bad "$label (unexpected: ${needle})"
  else
    ok "$label"
  fi
}

assert_eq() {
  local actual="$1" expected="$2" label="$3"
  if [ "$actual" = "$expected" ]; then
    ok "$label"
  else
    bad "$label (expected=${expected} actual=${actual})"
  fi
}

# 渲染输出按 shell 安全引用（quote_words 的 %q 形态，逗号/空格等会被转义）；
# 断言与 hook 检查前先解码回参数序列，避免对引用转义形态做脆弱断言。
decode_command() {
  local rendered="$1"
  local -a decoded_words=()
  eval "decoded_words=($rendered)"
  local joined="" word first=1
  for word in "${decoded_words[@]}"; do
    if [ "$first" -eq 1 ]; then
      joined="$word"
      first=0
    else
      joined="$joined $word"
    fi
  done
  printf '%s' "$joined"
}

render_command() {
  local rendered
  rendered=$(bash "$RENDERER" "$@" --output command)
  decode_command "$rendered"
}

render_shell_context() {
  # 输出 shell 格式并 eval 到全局（RENDERER 输出本就按 eval 设计，见 smoke-tmux-worker.sh）。
  local shell_out
  shell_out=$(bash "$RENDERER" "$@" --output shell)
  eval "$shell_out"
}

render_prompt_context() {
  bash "$RENDERER" "$@" --output prompt-context
}

SETTINGS_ARGS=(--backend claude-code --settings "$SETTINGS_EXAMPLE" --model glm53)
REGISTRY_ARGS=(--backend claude-code --provider-registry "$REGISTRY_EXAMPLE" --api-provider glm --model glm52)

echo "=== 1. settings / registry 默认渲染 hook-capable 命令（无 --bare） ==="
settings_cmd=$(render_command "${SETTINGS_ARGS[@]}")
assert_contains "$settings_cmd" "claude-provider-env.sh" "settings 默认走 provider env wrapper"
assert_contains "$settings_cmd" "--setting-sources project,local" "settings 默认保留 project,local setting-sources"
assert_contains "$settings_cmd" "--settings" "settings 默认透传 --settings"
assert_not_contains "$settings_cmd" "--bare" "settings 默认无 --bare"

registry_cmd=$(render_command "${REGISTRY_ARGS[@]}")
assert_contains "$registry_cmd" "claude-provider-env.sh" "registry 默认走 provider env wrapper"
assert_contains "$registry_cmd" "--setting-sources project,local" "registry 默认保留 project,local setting-sources"
assert_contains "$registry_cmd" "--api-provider glm" "registry 默认透传 --api-provider"
assert_contains "$registry_cmd" "glm-5.3" "registry 默认解析 model alias"
assert_not_contains "$registry_cmd" "--bare" "registry 默认无 --bare"

render_shell_context "${SETTINGS_ARGS[@]}"
assert_eq "$PROVIDER_ENV_ISOLATION" "settings-env-wrapper(setting-sources=project,local)" \
  "settings 默认 isolation 标签无 degraded 标记"
render_shell_context "${REGISTRY_ARGS[@]}"
assert_eq "$PROVIDER_ENV_ISOLATION" "registry-env-wrapper(provider=glm setting-sources=project,local)" \
  "registry 默认 isolation 标签无 degraded 标记（smoke-tmux-worker 契约）"
registry_ctx=$(render_prompt_context "${REGISTRY_ARGS[@]}")
assert_contains "$registry_ctx" \
  "Env Isolation: registry-env-wrapper(provider=glm setting-sources=project,local)" \
  "registry prompt-context 默认 Env Isolation 行原样"

echo "=== 2. --no-mcp 注入保留 ==="
settings_no_mcp_cmd=$(render_command "${SETTINGS_ARGS[@]}" --no-mcp)
assert_contains "$settings_no_mcp_cmd" "strict-mcp-config" "settings + --no-mcp 注入 strict-mcp-config"
assert_contains "$settings_no_mcp_cmd" '--mcp-config {"mcpServers":{}}' "settings + --no-mcp 注入空 MCP config"
assert_not_contains "$settings_no_mcp_cmd" "--bare" "settings + --no-mcp 仍默认无 --bare"
registry_no_mcp_cmd=$(render_command "${REGISTRY_ARGS[@]}" --no-mcp)
assert_contains "$registry_no_mcp_cmd" "strict-mcp-config" "registry + --no-mcp 注入 strict-mcp-config"
assert_contains "$registry_no_mcp_cmd" '--mcp-config {"mcpServers":{}}' "registry + --no-mcp 注入空 MCP config"
assert_not_contains "$registry_no_mcp_cmd" "--bare" "registry + --no-mcp 仍默认无 --bare"

echo "=== 3. --claude-bare 显式 opt-in ==="
settings_bare_cmd=$(render_command "${SETTINGS_ARGS[@]}" --claude-bare)
assert_contains "$settings_bare_cmd" "--bare" "settings + --claude-bare 命令含 --bare"
render_shell_context "${SETTINGS_ARGS[@]}" --claude-bare
assert_eq "$PROVIDER_ENV_ISOLATION" \
  "settings-env-wrapper(setting-sources=project,local)+bare(degraded/unhooked)" \
  "settings bare opt-in 标记 degraded/unhooked"
registry_bare_cmd=$(render_command "${REGISTRY_ARGS[@]}" --claude-bare)
assert_contains "$registry_bare_cmd" "--bare" "registry + --claude-bare 命令含 --bare"
registry_bare_ctx=$(render_prompt_context "${REGISTRY_ARGS[@]}" --claude-bare)
assert_contains "$registry_bare_ctx" \
  "Env Isolation: registry-env-wrapper(provider=glm setting-sources=project,local)+bare(degraded/unhooked)" \
  "registry bare opt-in prompt-context 标记 degraded/unhooked"

echo "=== 4. --claude-bare 错用 fail-closed ==="
set +e
misuse_oauth_out=$(bash "$RENDERER" --backend claude-oauth --claude-bare 2>&1)
misuse_oauth_rc=$?
misuse_nosettings_out=$(bash "$RENDERER" --backend claude-code --claude-bare 2>&1)
misuse_nosettings_rc=$?
misuse_noisolation_out=$(bash "$RENDERER" "${SETTINGS_ARGS[@]}" --no-provider-env-isolation --claude-bare 2>&1)
misuse_noisolation_rc=$?
set -e
assert_eq "$misuse_oauth_rc" "64" "--claude-bare 拒绝 claude-oauth backend"
assert_eq "$misuse_nosettings_rc" "64" "--claude-bare 拒绝无 settings/registry 的 claude-code"
assert_eq "$misuse_noisolation_rc" "64" "--claude-bare 拒绝关闭 provider env isolation"
assert_contains "$misuse_oauth_out$misuse_nosettings_out$misuse_noisolation_out" \
  "--claude-bare only applies to claude-code provider workers" "错用报错保留诊断文本"

echo "=== 5. 标准 render 输出直接过 spawn-worker hook 检查（无 PM 字符串 surgery） ==="
# 从 spawn-worker.sh 机械提取真实检查函数（fail-closed 契约来源），避免测试内复刻逻辑漂移。
hook_fn_source=$(sed -n '/^claude_hook_disable_reason() {$/,/^}$/p' "$SPAWN_WORKER")
if [ -n "$hook_fn_source" ]; then
  ok "spawn-worker hook 检查函数提取成功"
  eval "$hook_fn_source"
  for label_cmd in \
    "settings interactive:$settings_cmd" \
    "settings batch:$(render_command "${SETTINGS_ARGS[@]}" --mode batch --prompt-file "$PROMPT_FILE")" \
    "registry interactive:$registry_cmd" \
    "registry batch:$(render_command "${REGISTRY_ARGS[@]}" --mode batch --prompt-file "$PROMPT_FILE")" \
    "settings no-mcp:$settings_no_mcp_cmd"; do
    case_name=${label_cmd%%:*}
    COMMAND=${label_cmd#*:}
    hook_reason=$(claude_hook_disable_reason) && hook_blocked=1 || hook_blocked=0
    if [ "$hook_blocked" -eq 0 ] && [ -z "$hook_reason" ]; then
      ok "${case_name} 标准 render 通过 spawn-worker hook 检查"
    else
      bad "${case_name} 标准 render 被 spawn-worker hook 检查拒绝, reason=${hook_reason}"
    fi
  done
  # 反向校验：bare opt-in 渲染必须仍被同一检查拦下（spawn-worker 侧还需显式授权）。
  COMMAND=$settings_bare_cmd
  bare_reason=$(claude_hook_disable_reason) && bare_blocked=1 || bare_blocked=0
  if [ "$bare_blocked" -eq 1 ] && printf '%s' "$bare_reason" | grep -Fq -- '--bare'; then
    ok "bare opt-in 渲染仍被 spawn-worker hook 检查拦截, reason 提及 --bare"
  else
    bad "bare opt-in 渲染未被 spawn-worker hook 检查拦截, blocked=${bare_blocked} reason=${bare_reason}"
  fi
else
  bad "spawn-worker hook 检查函数提取失败, claude_hook_disable_reason 函数边界变化"
fi

printf 'SUMMARY: pass=%d fail=%d\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
