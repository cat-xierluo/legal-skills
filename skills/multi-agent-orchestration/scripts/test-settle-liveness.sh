#!/usr/bin/env bash
# test-settle-liveness.sh — settle_liveness_check 单元测试（Task-047 v2，NIT 10）
#
# 用真实 Orca worker-show response fixture（来自 folia Wave-2 测试期间合法 dispatch）
# 覆盖 exited/active/missing-field/--force override/empty 等场景。
# 仅 source 函数定义，不 source 整个 pm-orchestrate.sh（避免 orca-runtime 依赖）。
#
# 用法：bash scripts/test-settle-liveness.sh  # exit 0 全过，1 有失败
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PM="$SCRIPT_DIR/pm-orchestrate.sh"
FIXDIR="$SCRIPT_DIR/tests/fixtures"

# 抽出 settle_liveness_check 函数定义（去掉函数内的 `set -e -o pipefail`，外层已有）
FUNC=$(sed -n '/^settle_liveness_check()/,/^}/p' "$PM" | grep -v 'set -e -o pipefail')
eval "$FUNC"

# subshell 包住让 exit 2 留在子 shell，父 shell 能捕 $?
run() {
  local json="$1" force="$2"
  set +e
  ( eval "settle_liveness_check '$json' $force" )
  local rc=$?
  set -e
  echo "$rc"
}

pass=0; fail=0
check() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    echo "  ✓ $label (rc=$actual)"
    pass=$((pass+1))
  else
    echo "  ✗ $label (expected=$expected, actual=$actual)"
    fail=$((fail+1))
  fi
}

echo "Case 1: exited fixture (observation.status=exited, worker.state=succeeded), no force → expect 0"
check "exited+no-force" 0 "$(run "$(cat "$FIXDIR/worker-show-exited.json")" 0)"

echo "Case 2: active fixture (observation.status=active, worker.state=active), no force → expect 2"
check "active+no-force" 2 "$(run "$(cat "$FIXDIR/worker-show-active.json")" 0)"

echo "Case 3: missing-field fixture (no observation, no worker.state), no force → expect 2 (fail-closed)"
check "missing+no-force" 2 "$(run "$(cat "$FIXDIR/worker-show-missing.json")" 0)"

echo "Case 4: active fixture + --force=1 → expect 0 (override)"
check "active+force" 0 "$(run "$(cat "$FIXDIR/worker-show-active.json")" 1)"

echo "Case 5: empty show_json + --force=1 → expect 0 (override)"
check "empty+force" 0 "$(run "" 1)"

echo "Case 6: empty show_json + no force → expect 2"
check "empty+no-force" 2 "$(run "" 0)"

echo "Case 7: only worker.state (no observation) + no force → expect 2 (fail-closed)"
PARTIAL=$(jq 'del(.observation)' "$FIXDIR/worker-show-exited.json")
check "missing-observation-only" 2 "$(run "$PARTIAL" 0)"

echo ""
echo "Result: $pass pass, $fail fail"
[ "$fail" = "0" ] && exit 0 || exit 1
