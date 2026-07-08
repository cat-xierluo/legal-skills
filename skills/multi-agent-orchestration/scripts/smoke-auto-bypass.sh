#!/usr/bin/env bash
# smoke-auto-bypass.sh — v1.18.3 spawn-worker.sh auto-bypass permission 验证
#
# 验证内容（不真正 spawn worker，只验 spawn-worker.sh 的函数 + flag 定义 + 调用点）：
#   1. permission_auto 函数存在（v1.18.3 改用数字键 '2'）
#   2. permission_auto_bg 函数存在（v1.18.3 新加后台 watcher）
#   3. --no-permission-auto flag 解析存在
#   4. 调用点拆分为 trust_auto / permission_auto + permission_auto_bg 两段独立 if
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
  check "--no-permission-auto flag 解析存在（v1.18.3 精细 opt-out）" 0
else
  check "--no-permission-auto flag 解析存在（v1.18.3 精细 opt-out）" 1
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
