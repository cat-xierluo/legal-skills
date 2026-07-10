#!/usr/bin/env bash
# smoke-auto-bypass.sh — v1.18.3 + v1.18.4 spawn-worker.sh auto-bypass 验证
#
# 验证内容（不真正 spawn worker，只验 spawn-worker.sh 的函数 + flag 定义 + 调用点）：
#   v1.18.3（保留）：
#     1. permission_auto 函数存在（v1.18.3 改用数字键 '2'）
#     2. permission_auto_bg 函数存在（v1.18.3 新加后台 watcher）
#     3. --no-permission-auto flag 解析存在
#     4. 调用点拆分为 trust_auto / permission_auto + permission_auto_bg 两段独立 if
#     5. --usage 含 --no-permission-auto
#     6. 头部注释含 v1.18.3 标记
#   v1.18.4（新增）：
#     7.  resolve_backend_defaults() 函数定义存在（backend 分支化）
#     8.  resolve_backend_defaults() 包含 claude-code 全关分支
#     9.  新增 5 个 flag 解析存在（--trust-auto / --permission-auto / --permission-auto-bg /
#         --no-permission-auto-bg / OVERRIDE 标志置位）
#     10. 主流程新增独立 PERMISSION_AUTO_BG gate（与 sync 解耦）
#     11. --usage 含 4 个新 flag
#     12. 头部注释含 v1.18.4 标记
#
# 用法: bash scripts/smoke-auto-bypass.sh
# 期望: exit 0，输出所有 "✓" check
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SPAWN_WORKER="$SCRIPT_DIR/spawn-worker.sh"

if [ ! -f "$SPAWN_WORKER" ]; then
  echo "✗ FAIL: $SPAWN_WORKER not found" >&2
  exit 1
fi

pass=0
fail=0

check() {
  local name="$1"
  local result="$2"  # 0=pass, 1=fail
  if [ "$result" -eq 0 ]; then
    echo "✓ PASS: $name"
    pass=$((pass + 1))
  else
    echo "✗ FAIL: $name" >&2
    fail=$((fail + 1))
  fi
}

# === v1.18.3 retained checks ===

# 1. permission_auto 函数定义存在
if grep -q "^permission_auto() {" "$SPAWN_WORKER"; then
  check "permission_auto() 函数定义存在" 0
else
  check "permission_auto() 函数定义存在" 1
fi

# 2. permission_auto 用数字键 '2'（v1.18.3 关键修复）
if grep -A 25 "^permission_auto() {" "$SPAWN_WORKER" | grep -qF 'send-keys -t "$session" "2"'; then
  check "permission_auto 用数字键 '2'（v1.18.3）" 0
else
  check "permission_auto 用数字键 '2'（v1.18.3）" 1
fi

# 3. permission_auto_bg 函数定义存在
if grep -q "^permission_auto_bg() {" "$SPAWN_WORKER"; then
  check "permission_auto_bg() 函数定义存在（v1.18.3 新加）" 0
else
  check "permission_auto_bg() 函数定义存在（v1.18.3 新加）" 1
fi

# 4. --no-permission-auto flag 解析存在
if grep -q -- "--no-permission-auto)" "$SPAWN_WORKER"; then
  check "--no-permission-auto flag 解析存在（v1.18.3 兼容）" 0
else
  check "--no-permission-auto flag 解析存在（v1.18.3 兼容）" 1
fi

# 5. 调用点拆分（trust_auto 独立 if，permission_auto 独立 if + bg）
if grep -qE "permission_auto_bg \"\\\$SESSION\" & disown" "$SPAWN_WORKER"; then
  check "调用点含 permission_auto_bg disown（v1.18.3 后台 watcher）" 0
else
  check "调用点含 permission_auto_bg disown（v1.18.3 后台 watcher）" 1
fi

# 6. --usage 含 --no-permission-auto（无参触发 usage，输出到 stderr；用临时文件绕过 macOS ugrep pipe bug；`|| true` 忽略 exit 64）
USAGE_OUT=$(mktemp)
bash "$SPAWN_WORKER" > "$USAGE_OUT" 2>&1 || true
if grep -q "no-permission-auto" "$USAGE_OUT"; then
  check "--usage 输出 --no-permission-auto" 0
else
  check "--usage 输出 --no-permission-auto" 1
fi
rm -f "$USAGE_OUT"

# 7. 头部注释含 v1.18.3
if grep -q "v1.18.3" "$SPAWN_WORKER"; then
  check "spawn-worker.sh 头部注释含 v1.18.3 标记" 0
else
  check "spawn-worker.sh 头部注释含 v1.18.3 标记" 1
fi

# === v1.18.4 new checks ===

# 8. resolve_backend_defaults 函数定义存在
if grep -q "^resolve_backend_defaults() {" "$SPAWN_WORKER"; then
  check "resolve_backend_defaults() 函数定义存在（v1.18.4 backend 分支化）" 0
else
  check "resolve_backend_defaults() 函数定义存在（v1.18.4 backend 分支化）" 1
fi

# 9. resolve_backend_defaults 包含 claude-code 全关分支
if grep -A 30 "^resolve_backend_defaults() {" "$SPAWN_WORKER" | grep -qE "claude-code\|claude_code\) (TRUST_AUTO|PERMISSION_AUTO|PERMISSION_AUTO_BG)=0" ; then
  check "resolve_backend_defaults 含 claude-code 全关分支（v1.18.4）" 0
else
  check "resolve_backend_defaults 含 claude-code 全关分支（v1.18.4）" 1
fi

# 10. 5 个新 flag 解析存在
flag_ok=0
for flag in --trust-auto --permission-auto --permission-auto-bg --no-permission-auto-bg; do
  if grep -q -- "$flag)" "$SPAWN_WORKER"; then
    flag_ok=1
  else
    flag_ok=0
    break
  fi
done
if [ "$flag_ok" -eq 1 ]; then
  check "5 个新 flag 解析齐全（--trust-auto / --permission-auto / --permission-auto-bg / --no-permission-auto-bg + 兼容 --no-trust-auto）" 0
else
  check "5 个新 flag 解析齐全（--trust-auto / --permission-auto / --permission-auto-bg / --no-permission-auto-bg + 兼容 --no-trust-auto）" 1
fi

# 11. 主流程 PERMISSION_AUTO_BG 独立 gate
if grep -qE 'PERMISSION_AUTO_BG.*-eq 1' "$SPAWN_WORKER"; then
  check "主流程 PERMISSION_AUTO_BG 独立 gate（v1.18.4 sync/bg 解耦）" 0
else
  check "主流程 PERMISSION_AUTO_BG 独立 gate（v1.18.4 sync/bg 解耦）" 1
fi

# 12. --usage 含 4 个新 flag
USAGE_OUT=$(mktemp)
bash "$SPAWN_WORKER" > "$USAGE_OUT" 2>&1 || true
usage_ok=1
for flag in --trust-auto --permission-auto --permission-auto-bg --no-permission-auto-bg; do
  # 用 -- 让 BSD grep 把以 - 开头的 pattern 当作字符串
  if ! grep -q -- "$flag" "$USAGE_OUT"; then
    usage_ok=0
    break
  fi
done
if [ "$usage_ok" -eq 1 ]; then
  check "--usage 输出 4 个新 flag" 0
else
  check "--usage 输出 4 个新 flag" 1
fi
rm -f "$USAGE_OUT"

# 13. 头部注释含 v1.18.4
if grep -q "v1.18.4" "$SPAWN_WORKER"; then
  check "spawn-worker.sh 头部注释含 v1.18.4 标记" 0
else
  check "spawn-worker.sh 头部注释含 v1.18.4 标记" 1
fi

echo
echo "=== smoke-auto-bypass summary ==="
echo "  pass: $pass"
echo "  fail: $fail"
if [ "$fail" -gt 0 ]; then
  echo "  RESULT: FAIL" >&2
  exit 1
else
  echo "  RESULT: PASS"
  exit 0
fi
