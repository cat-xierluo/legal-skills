#!/usr/bin/env bash
# test-blocker-recovery.sh — 验收失败恢复合同的统一回归入口（v2.14.0）。
#
# 汇总三组恢复合同测试，任一失败即非零退出：
#   1. acceptance-recovery.py   单一机械分类合同（internal_recoverable /
#      external_dependency / safety_unknown；修复预算 2 次；表外 fail-closed）
#   2. acceptance-repair-gate.py docs-only 验收修复的极窄价值合同
#      （preflight/postflight 机械拒绝：缺字段、head 漂移、范围外修改、
#      未解决 blocker、重复修复、owner 串行冲突）
#   3. scope-guard.py + spawn-worker.sh reviewer 写范围纪律
#      （默认只写自身 Session Context；config/*.local.yaml 永远拒绝）
#
# 用法：bash skills/multi-agent-orchestration/scripts/test-blocker-recovery.sh
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

overall_failed=0

run_suite() {
  local label="$1"
  shift
  echo "== $label =="
  if "$@"; then
    echo
  else
    echo "SUITE FAILED: $label" >&2
    overall_failed=$((overall_failed + 1))
  fi
}

run_suite "acceptance-recovery classification contract" \
  python3 "$SCRIPT_DIR/test-acceptance-recovery.py"

run_suite "acceptance-repair-gate contract" \
  bash "$SCRIPT_DIR/test-acceptance-repair-gate.sh"

run_suite "reviewer scope guard discipline" \
  bash "$SCRIPT_DIR/test-reviewer-scope-guard.sh"

if [ "$overall_failed" -gt 0 ]; then
  echo "blocker recovery tests: $overall_failed suite(s) failed" >&2
  exit 1
fi
echo "blocker recovery tests: all suites passed"
