#!/usr/bin/env bash
# test-remote-dispatch-receipt.sh — 一次性派发回执模块测试。
# 覆盖：issue 原子落盘/字段规范化/TTL 上限；consume 成功/重放/过期/字段不匹配/
# nonce 一次性/consumed 不可逆（chmod 400）；policy disabled fail-closed。
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CASE_ROOT=$(mktemp -d)
trap 'rm -rf "$CASE_ROOT"' EXIT

passed=0
failed=0
ok() { printf 'PASS: %s\n' "$1"; passed=$((passed + 1)); }
bad() { printf 'FAIL: %s\n' "$1" >&2; failed=$((failed + 1)); }
expect_rc() { # expect_rc <expected-rc> <label> — 校验上一条命令的实际 rc
  local expected="$1" label="$2" actual
  actual=$3
  if [ "$actual" -eq "$expected" ]; then ok "$label"; else bad "$label (expect rc=$expected got rc=$actual)"; fi
}

# fixture policy：默认启用；DISABLED 版供开关用例
cat > "$CASE_ROOT/policy-on.json" <<'EOF'
{
  "schema": "multi-agent-orchestration.harness-backend-policy.v1",
  "policy": "deny_by_default",
  "hosts": {"claude-code": ["claude-code", "codex"]},
  "remote_dispatch": {"enabled": true, "max_ttl_seconds": 300}
}
EOF
sed 's/"enabled": true/"enabled": false/' "$CASE_ROOT/policy-on.json" > "$CASE_ROOT/policy-off.json"
export REMOTE_DISPATCH_POLICY_FILE="$CASE_ROOT/policy-on.json"

# shellcheck source=remote-dispatch-receipt.sh
source "$SCRIPT_DIR/remote-dispatch-receipt.sh"

R1="$CASE_ROOT/r1.json"
ISSUE_ARGS=(--file "$R1" --node node-a --pm-harness claude --chain-json '["claude-code"]'
  --worker-backend claude_code --branch node-a/fix-x --session s1)

# 1) issue：别名规范化（claude→claude-code / claude_code→claude-code）+ 原子落盘 600
issue_out=$(remote_receipt_issue "${ISSUE_ARGS[@]}") && rc=$? || rc=$?
expect_rc 0 "issue 成功" "$rc"
receipt_sha=$(printf '%s\n' "$issue_out" | awk '{print $1}')
[ "${#receipt_sha}" -eq 64 ] && ok "issue 输出 sha256" || bad "issue 输出 sha256"
[ "$(stat -f %Lp "$R1")" = "600" ] && ok "回执文件权限 600" || bad "回执文件权限 600"
[ "$(jq -r .pm_harness "$R1")" = "claude-code" ] && ok "pm_harness 规范化" || bad "pm_harness 规范化"
[ "$(jq -r .worker_backend "$R1")" = "claude-code" ] && ok "worker_backend 规范化" || bad "worker_backend 规范化"
[ "$(jq -r .consumed_at_epoch "$R1")" = "null" ] && ok "初始未消费" || bad "初始未消费"

# 2) consume：全字段匹配成功
remote_receipt_consume --file "$R1" --expect-node node-a --expect-worker-backend claude-code \
  --expect-branch node-a/fix-x --expect-session s1 >/dev/null 2>&1 && rc=$? || rc=$?
expect_rc 0 "consume 成功" "$rc"
[ "$(stat -f %Lp "$R1")" = "400" ] && ok "消费后 chmod 400（不可逆）" || bad "消费后 chmod 400"
[ "$(jq -r .consumed_at_epoch "$R1")" != "null" ] && ok "consumed_at_epoch 已写入" || bad "consumed_at_epoch 已写入"

# 3) 重放拒绝（nonce 一次性）
remote_receipt_consume --file "$R1" --expect-node node-a >/dev/null 2>&1 && rc=$? || rc=$?
expect_rc 64 "重放拒绝 REMOTE_RECEIPT_ALREADY_CONSUMED" "$rc"

# 4) 过期拒绝
R2="$CASE_ROOT/r2.json"
remote_receipt_issue --file "$R2" --node node-a --pm-harness claude-code --chain-json '["claude-code"]' \
  --worker-backend claude-code --branch b1 --session s2 >/dev/null
remote_receipt_consume --file "$R2" --now-epoch "$(( $(date +%s) + 99999 ))" >/dev/null 2>&1 && rc=$? || rc=$?
expect_rc 64 "过期拒绝 REMOTE_RECEIPT_EXPIRED" "$rc"

# 5) backend / branch / session 不匹配拒绝
R3="$CASE_ROOT/r3.json"
remote_receipt_issue --file "$R3" --node node-a --pm-harness claude-code --chain-json '["claude-code"]' \
  --worker-backend claude-code --branch b3 --session s3 >/dev/null
remote_receipt_consume --file "$R3" --expect-worker-backend codex >/dev/null 2>&1 && rc=$? || rc=$?
expect_rc 64 "backend 不匹配拒绝" "$rc"
remote_receipt_consume --file "$R3" --expect-branch other >/dev/null 2>&1 && rc=$? || rc=$?
expect_rc 64 "branch 不匹配拒绝" "$rc"
remote_receipt_consume --file "$R3" --expect-session other >/dev/null 2>&1 && rc=$? || rc=$?
expect_rc 64 "session 不匹配拒绝" "$rc"
# 未消费的回执在拒绝后仍可被正确 consume（拒绝不改文件）
remote_receipt_consume --file "$R3" --expect-node node-a --expect-worker-backend claude-code \
  --expect-branch b3 --expect-session s3 >/dev/null 2>&1 && rc=$? || rc=$?
expect_rc 0 "拒绝不改文件：正确 consume 仍成功" "$rc"

# 6) TTL 超 policy 上限拒绝
remote_receipt_issue --file "$CASE_ROOT/r4.json" --node node-a --pm-harness claude-code \
  --chain-json '["claude-code"]' --worker-backend claude-code --branch b4 --session s4 \
  --ttl-seconds 99999 >/dev/null 2>&1 && rc=$? || rc=$?
expect_rc 64 "TTL 超 max_ttl_seconds 拒绝" "$rc"

# 7) 缺参 / 非法 chain / 未知 harness
remote_receipt_issue --file "$CASE_ROOT/r5.json" --node node-a >/dev/null 2>&1 && rc=$? || rc=$?
expect_rc 64 "缺参拒绝" "$rc"
remote_receipt_issue --file "$CASE_ROOT/r5.json" --node node-a --pm-harness claude-code \
  --chain-json '[]' --worker-backend claude-code --branch b --session s >/dev/null 2>&1 && rc=$? || rc=$?
expect_rc 64 "空 chain 拒绝" "$rc"
remote_receipt_issue --file "$CASE_ROOT/r5.json" --node node-a --pm-harness not-a-harness \
  --chain-json '["claude-code"]' --worker-backend claude-code --branch b --session s >/dev/null 2>&1 && rc=$? || rc=$?
expect_rc 64 "未知 harness 拒绝" "$rc"

# 8) 畸形 JSON / 文件缺失
echo "not json" > "$CASE_ROOT/malformed.json"
remote_receipt_consume --file "$CASE_ROOT/malformed.json" >/dev/null 2>&1 && rc=$? || rc=$?
expect_rc 64 "畸形 JSON 拒绝" "$rc"
remote_receipt_consume --file "$CASE_ROOT/nope.json" >/dev/null 2>&1 && rc=$? || rc=$?
expect_rc 64 "文件缺失拒绝" "$rc"

# 9) policy disabled → issue/consume 双侧 fail-closed
export REMOTE_DISPATCH_POLICY_FILE="$CASE_ROOT/policy-off.json"
remote_receipt_issue --file "$CASE_ROOT/r6.json" --node node-a --pm-harness claude-code \
  --chain-json '["claude-code"]' --worker-backend claude-code --branch b6 --session s6 \
  >/dev/null 2>&1 && rc=$? || rc=$?
expect_rc 64 "policy disabled：issue 拒绝" "$rc"
export REMOTE_DISPATCH_POLICY_FILE="$CASE_ROOT/policy-on.json"
remote_receipt_issue --file "$CASE_ROOT/r6.json" --node node-a --pm-harness claude-code \
  --chain-json '["claude-code"]' --worker-backend claude-code --branch b6 --session s6 >/dev/null
export REMOTE_DISPATCH_POLICY_FILE="$CASE_ROOT/policy-off.json"
remote_receipt_consume --file "$CASE_ROOT/r6.json" >/dev/null 2>&1 && rc=$? || rc=$?
expect_rc 64 "policy disabled：consume 拒绝" "$rc"
export REMOTE_DISPATCH_POLICY_FILE="$CASE_ROOT/policy-on.json"

# 10) consume 输出全局变量（spawn-worker.sh 集成点依赖）
R7="$CASE_ROOT/r7.json"
remote_receipt_issue --file "$R7" --node node-b --pm-harness claude-code --chain-json '["claude-code"]' \
  --worker-backend claude-code --branch b7 --session s7 >/dev/null
remote_receipt_consume --file "$R7" --expect-node node-b >/dev/null 2>&1
[ "$REMOTE_DISPATCH_RECEIPT_PM_HARNESS" = "claude-code" ] && ok "consume 设置 PM_HARNESS" || bad "consume 设置 PM_HARNESS"
[ "$REMOTE_DISPATCH_RECEIPT_NODE" = "node-b" ] && ok "consume 设置 NODE" || bad "consume 设置 NODE"
[ "$REMOTE_DISPATCH_RECEIPT_PM_HARNESS_CHAIN_JSON" = '["claude-code"]' ] && ok "consume 设置 CHAIN_JSON" || bad "consume 设置 CHAIN_JSON"
[ "${#REMOTE_DISPATCH_RECEIPT_SHA256}" -eq 64 ] && ok "consume 设置 SHA256" || bad "consume 设置 SHA256"

printf '\n远程派发回执测试：%d passed, %d failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
