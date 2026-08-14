#!/usr/bin/env bash
# test-settle-liveness.sh — settle_liveness_check 单元测试（Task-047R）
#
# 用真实 Orca worker-show **完整包装** response fixture（含 _meta/id/ok/result）
# 覆盖 completed(active→missing GC)/active/missing-field/--force override/empty 场景。
# 仅 source 函数定义，不 source 整个 pm-orchestrate.sh（避免 orca-runtime 依赖）。
#
# v2 修复（PR #86 review B1）：fixture 是完整包装（非预解包），jq 路径用 .result.*。
# gate 逻辑：仅允许 observation=missing|exited 且 worker=succeeded|failed|stopped；
# 任一未知/缺失状态保守拒绝。
#
# 用法：bash scripts/test-settle-liveness.sh  # exit 0 全过，1 有失败
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PM="$SCRIPT_DIR/pm-orchestrate.sh"
FIXDIR="$SCRIPT_DIR/tests/fixtures"

# 抽出 settle_liveness_check 函数定义（去掉函数内的 set 行，外层已有 set -euo pipefail）
FUNC=$(sed -n '/^settle_liveness_check()/,/^}/p' "$PM" | grep -v 'set -e -o pipefail')
eval "$FUNC"

# subshell 包住让 exit 2 留在子 shell，父 shell 能捕 $?（set -e 兼容）
run() {
  local json="$1" force="$2"
  set +e
  ( SETTLE_TEST_JSON="$json" bash -c '
      # 子 shell 重新 eval 函数（避免 eval 单引号 JSON 脆弱，用 env var 传）
      '"$(declare -f settle_liveness_check)"'
      settle_liveness_check "$SETTLE_TEST_JSON" "'"$force"'"
    ' )
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

echo "Case 1: completed fixture (obs=missing GC, state=succeeded), no force → expect 0 (死, 可 settle)"
check "completed+no-force" 0 "$(run "$(cat "$FIXDIR/worker-show-exited.json")" 0)"

echo "Case 2: active fixture (obs=active, state=active), no force → expect 2 (活, REFUSED)"
check "active+no-force" 2 "$(run "$(cat "$FIXDIR/worker-show-active.json")" 0)"

echo "Case 3: missing-field fixture (双 ABSENT), no force → expect 2 (fail-closed)"
check "missing+no-force" 2 "$(run "$(cat "$FIXDIR/worker-show-missing.json")" 0)"

echo "Case 4: active fixture + --force=1 → expect 0 (override)"
check "active+force" 0 "$(run "$(cat "$FIXDIR/worker-show-active.json")" 1)"

echo "Case 5: empty show_json + --force=1 → expect 0 (override)"
check "empty+force" 0 "$(run "" 1)"

echo "Case 6: empty show_json + no force → expect 2"
check "empty+no-force" 2 "$(run "" 0)"

echo "Case 7: missing observation only (worker.state=succeeded), no force → expect 2 (schema 不完整)"
PARTIAL=$(jq 'del(.result.observation)' "$FIXDIR/worker-show-exited.json")
check "missing-observation-only" 2 "$(run "$PARTIAL" 0)"

echo "Case 8: 双 ABSENT + --force=1 → expect 0 (override)"
check "both-absent+force" 0 "$(run "$(cat "$FIXDIR/worker-show-missing.json")" 1)"

echo "Case 9: 验证 fixture 是完整包装（顶层有 _meta/id/ok/result，B1 防回归）"
TOPKEYS=$(jq -r 'keys | join(",")' "$FIXDIR/worker-show-exited.json")
if echo "$TOPKEYS" | grep -q 'result'; then
  echo "  ✓ fixture 含 .result 包装 (keys: $TOPKEYS)"
  pass=$((pass+1))
else
  echo "  ✗ fixture 缺 .result 包装（B1 回归！）keys: $TOPKEYS"
  fail=$((fail+1))
fi

echo "Case 10: 未知 future state 不得因不在 denylist 而放行"
UNKNOWN=$(jq '.result.observation.status = "idle_unknown" | .result.worker.state = "ready_unknown"' "$FIXDIR/worker-show-exited.json")
check "unknown-state+no-force" 2 "$(run "$UNKNOWN" 0)"

echo ""
echo "Result: $pass pass, $fail fail"
[ "$fail" = "0" ] && exit 0 || exit 1
