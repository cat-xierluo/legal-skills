#!/usr/bin/env bash
# harness-backend-policy 回归测试：hermes PM 宿主签名（2.26.0）。
# 覆盖：帧签名匹配（含裸词负例）、canonical 别名、真实 policy 文件的
# 白名单交集与 deny-by-default、本机 Hermes 祖先链实测（可跳过）、
# spawn-worker.sh 静态接线。
set -uo pipefail

REAL_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
POLICY_SH="$REAL_SCRIPT_DIR/harness-backend-policy.sh"
POLICY_JSON="$REAL_SCRIPT_DIR/../config/harness-backend-policy.json"

# shellcheck source=../harness-backend-policy.sh
source "$POLICY_SH"

passed=0
failed=0
skipped=0

ok() { printf 'PASS: %s\n' "$1"; passed=$((passed + 1)); }
bad() { printf 'FAIL: %s\n' "$1" >&2; failed=$((failed + 1)); }
skip() { printf 'SKIP: %s\n' "$1"; skipped=$((skipped + 1)); }

assert_frame() {
  local desc="$1" input="$2" expected="$3"
  local got rc=0
  got=$(pm_harness_candidate_for_frame "$input") || rc=$?
  if [ "$rc" -ne 0 ]; then
    if [ "$expected" = "__none__" ]; then ok "$desc"; else bad "$desc (期望 $expected，helper 返回非零)"; fi
    return
  fi
  if [ "$expected" = "__none__" ]; then
    bad "$desc (期望不识别，实际 [$got])"
  elif [ "$got" = "$expected" ]; then
    ok "$desc"
  else
    bad "$desc (期望 $expected，实际 [$got])"
  fi
}

assert_canonical() {
  local desc="$1" input="$2" expected="$3"
  local got rc=0
  got=$(canonical_harness_backend "$input") || rc=$?
  if [ "$rc" -ne 0 ]; then
    if [ "$expected" = "__none__" ]; then ok "$desc"; else bad "$desc (期望 $expected，canonical 返回非零)"; fi
    return
  fi
  if [ "$expected" = "__none__" ]; then
    bad "$desc (期望拒绝，实际 [$got])"
  elif [ "$got" = "$expected" ]; then
    ok "$desc"
  else
    bad "$desc (期望 $expected，实际 [$got])"
  fi
}

assert_chain() {
  local desc="$1" chain_json="$2" expected="$3"
  local got rc=0
  got=$(allowed_worker_backends_for_chain_json "$chain_json") || rc=$?
  if [ "$rc" -ne 0 ]; then
    if [ "$expected" = "__fail__" ]; then ok "$desc"; else bad "$desc (期望 $expected，交集门返回非零)"; fi
    return
  fi
  if [ "$expected" = "__fail__" ]; then
    bad "$desc (期望 fail-closed，实际放行 [$got])"
  elif [ "$got" = "$expected" ]; then
    ok "$desc"
  else
    bad "$desc (期望 [$expected]，实际 [$got])"
  fi
}

echo '== 1. 帧签名匹配 =='
assert_frame 'Hermes.app bundle 帧' \
  '/users/demo/applications/hermes.app/contents/macos/hermes' 'hermes'
assert_frame '.hermes 安装目录帧' \
  '/users/demo/.hermes/hermes-agent/venv/bin/python' 'hermes'
assert_frame '裸 hermes 词不作签名（负例）' 'hermes' '__none__'
assert_frame '无关 hermes 前缀路径不误命中（负例）' \
  '/opt/tools/hermes-cli/bin/runner' '__none__'
assert_frame 'zcode-cli 帧' '/usr/local/bin/zcode-cli' 'zcode'
assert_frame 'claude 帧' '/usr/local/bin/claude' 'claude-code'
assert_frame 'codex 帧' '/opt/codex/bin/codex' 'codex'
assert_frame 'codebuddy 帧' 'codebuddy' 'codebuddy'
assert_frame 'qoderclicn 帧' 'qoderclicn' 'qoderwork-cn'
assert_frame '普通 bash 帧不识别' 'bash' '__none__'

echo '== 2. canonical_harness_backend =='
assert_canonical 'hermes 别名' 'hermes' 'hermes'
assert_canonical 'claude 归一为 claude-code' 'claude' 'claude-code'
assert_canonical '未知宿主拒绝' 'unknown-agent' '__none__'

echo '== 3. 真实 policy 文件：白名单交集 / deny-by-default =='
[ -f "$POLICY_JSON" ] || { bad "policy 文件缺失: config/harness-backend-policy.json"; }
jq -e 'select(.schema == "multi-agent-orchestration.harness-backend-policy.v1")
      | select(.policy == "deny_by_default")
      | select(.hosts.hermes == ["claude-code", "codex"])' "$POLICY_JSON" >/dev/null 2>&1 \
  && ok 'policy JSON：hermes host 条目与授权面正确' \
  || bad 'policy JSON：schema/policy/hermes 条目校验失败'

assert_chain 'hermes 单层链' '["hermes"]' 'claude-code codex'
assert_chain 'hermes→claude-code 嵌套交集' '["hermes","claude-code"]' 'claude-code codex'
assert_chain 'hermes→zcode 嵌套交集' '["hermes","zcode"]' 'claude-code codex'
assert_chain 'hermes→codebuddy 无交集 fail-closed' '["hermes","codebuddy"]' '__fail__'
assert_chain '未知宿主 fail-closed' '["unknown-host"]' '__fail__'
assert_chain 'zcode 既有授权不回归' '["zcode"]' 'claude-code codex'

echo '== 4. spawn-worker.sh 静态接线 =='
grep -q 'harness-backend-policy.sh' "$REAL_SCRIPT_DIR/spawn-worker.sh" \
  && ok 'spawn-worker.sh 仍 source 策略模块' \
  || bad 'spawn-worker.sh 丢失策略模块 source'
grep -q 'enforce_harness_backend_policy_chain' "$REAL_SCRIPT_DIR/spawn-worker.sh" \
  && ok 'spawn-worker.sh 仍调用门禁链' \
  || bad 'spawn-worker.sh 丢失门禁链调用'

echo '== 5. 本机 Hermes 祖先链实测（非 Hermes 环境自动跳过） =='
frame_out=$(pm_harness_from_process "$PPID" 2>/dev/null) && frame_rc=0 || frame_rc=$?
if [ "$frame_rc" -eq 0 ]; then
  live_host=$(printf '%s\n' "$frame_out" | sed -n '1p')
  live_chain=$(printf '%s\n' "$frame_out" | sed -n '2p')
  if [ "$live_host" = "hermes" ] \
    && printf '%s' "$live_chain" | jq -e 'type == "array" and length > 0 and all(.[]; . == "hermes")' >/dev/null 2>&1; then
    ok "本机祖先链识别为 hermes（chain=${live_chain}）"
  else
    bad "本机祖先链识别异常：host=[$live_host] chain=[$live_chain]"
  fi
elif [ "$frame_rc" -eq 1 ]; then
  skip '当前环境祖先链无可识别宿主（非 Hermes 宿主运行），签名用例已在第 1 节覆盖'
else
  bad "pm_harness_from_process 异常退出码 $frame_rc（预期仅 0/1）"
fi

echo
printf '通过 %d，失败 %d，跳过 %d\n' "$passed" "$failed" "$skipped"
[ "$failed" -eq 0 ]
