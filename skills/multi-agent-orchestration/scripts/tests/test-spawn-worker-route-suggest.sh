#!/usr/bin/env bash
# spawn-worker 集成额度感知路由兜底的回归测试（quota-aware routing 集成点 B）。
# 模式沿用 scripts/test-spawn-worker-provider-lease.sh：source helper + 真实
# python3 跑 route_suggest.py（纯标准库零依赖）+ 伪造 personal config/summary
# fixture；对 spawn-worker.sh 主脚本做静态接线断言（source + 调用必须发生在
# acquire_provider_lease 消费 API_PROVIDER 之前）。
set -euo pipefail

REAL_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
SPAWN_WORKER="$REAL_SCRIPT_DIR/spawn-worker.sh"
ROUTE_SUGGEST_HELPER="$REAL_SCRIPT_DIR/spawn-worker-route-suggest.sh"
CASE_ROOT=$(mktemp -d)
trap 'rm -rf "$CASE_ROOT"' EXIT

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

assert_eq() {
  local actual="$1" expected="$2" label="$3"
  if [ "$actual" = "$expected" ]; then
    ok "$label"
  else
    bad "$label (expected=$expected actual=$actual)"
  fi
}

# fixture：三份 personal config（enabled / disabled / summary 失联）+ 一份 fresh
# summary（时间戳动态生成，避免 stale 干扰评分；lane-b 余量低于判停线，
# tier L1 静态序在前也应让位给 lane-a，确保断言的 provider 来自评分）。
python3 - "$CASE_ROOT" <<'PY'
import datetime as dt
import json
import sys

root = sys.argv[1]
now = dt.datetime.now().astimezone()
summary = {
    "schema": "quota-aware-routing.summary.v1",
    "generated_at": now.isoformat(),
    "lanes": {
        "lane-a": {"type": "fuel", "remaining_percent": 80.0,
                   "resets_at": (now + dt.timedelta(minutes=240)).isoformat(),
                   "health": "ok"},
        "lane-b": {"type": "fuel", "remaining_percent": 8.0,
                   "resets_at": (now + dt.timedelta(minutes=240)).isoformat(),
                   "health": "ok"},
    },
}

def qar_config(summary_path):
    return {"quota_aware_routing": {
        "enabled": True,
        "summary_path": summary_path,
        "freshness_minutes": 30,
        "stop_line_percent": 15,
        "urgency_window_minutes": 120,
        "lanes": {
            "lane-a": {"type": "fuel", "providers": ["prov-a1"]},
            "lane-b": {"type": "fuel", "providers": ["prov-b1"]},
        },
        "tier_policy": {
            "L1": ["lane-b", "lane-a"],
            "L2": ["lane-a"],
            "default": "lane-a",
        },
    }}

with open(f"{root}/summary-ok.json", "w", encoding="utf-8") as f:
    json.dump(summary, f)
with open(f"{root}/personal-enabled.json", "w", encoding="utf-8") as f:
    json.dump(qar_config(f"{root}/summary-ok.json"), f)
with open(f"{root}/personal-degraded.json", "w", encoding="utf-8") as f:
    json.dump(qar_config("/nonexistent/qar-summary.json"), f)
disabled = qar_config(f"{root}/summary-ok.json")
disabled["quota_aware_routing"]["enabled"] = False
with open(f"{root}/personal-disabled.json", "w", encoding="utf-8") as f:
    json.dump(disabled, f)
PY

# shellcheck source=spawn-worker-route-suggest.sh
source "$ROUTE_SUGGEST_HELPER"

reset_autofill_case() {
  SCRIPT_DIR="$REAL_SCRIPT_DIR"
  API_PROVIDER=""
  WORKER_BACKEND_CANONICAL="claude-code"
  PERSONAL_CONFIG_FILE="$CASE_ROOT/personal-enabled.json"
  unset ROUTE_SUGGEST_TIER
}

# 场景 1：quota_aware_routing 未启用（enabled=false）→ 不调 route_suggest、
# 不出 marker、API_PROVIDER 保持空；配置文件缺失同样保持空（fail-open）。
# 注意：函数在当前 shell 执行（不用命令替换，否则 API_PROVIDER 的修改留在
# 子 shell 里断言不到），stderr 落文件供 marker 断言。
reset_autofill_case
PERSONAL_CONFIG_FILE="$CASE_ROOT/personal-disabled.json"
route_suggest_autofill_provider 2>"$CASE_ROOT/disabled.err"
assert_eq "$API_PROVIDER" "" "disabled config leaves provider empty"
if grep -Fq 'ROUTE_SUGGEST_AUTO' "$CASE_ROOT/disabled.err"; then
  bad "disabled config emits no marker"
else
  ok "disabled config emits no marker"
fi

reset_autofill_case
PERSONAL_CONFIG_FILE="$CASE_ROOT/missing-config.json"
route_suggest_autofill_provider 2>"$CASE_ROOT/missing.err"
assert_eq "$API_PROVIDER" "" "missing config leaves provider empty"
if grep -Fq 'ROUTE_SUGGEST_AUTO' "$CASE_ROOT/missing.err"; then
  bad "missing config emits no marker"
else
  ok "missing config emits no marker"
fi

# 场景 2：enabled + summary 可读 + 未显式 --api-provider → 自动补 provider，
# stderr 出 ROUTE_SUGGEST_AUTO marker；ROUTE_SUGGEST_TIER 环境变量覆盖缺省 L1。
reset_autofill_case
route_suggest_autofill_provider 2>"$CASE_ROOT/auto.err"
assert_eq "$API_PROVIDER" "prov-a1" "enabled config autofills scored provider"
if grep -Fq 'ROUTE_SUGGEST_AUTO provider=prov-a1 tier=L1' "$CASE_ROOT/auto.err"; then
  ok "autofill marker carries provider and default tier"
else
  bad "autofill marker carries provider and default tier ($(cat "$CASE_ROOT/auto.err"))"
fi

reset_autofill_case
export ROUTE_SUGGEST_TIER="L2"
route_suggest_autofill_provider 2>"$CASE_ROOT/tier.err"
if grep -Fq 'ROUTE_SUGGEST_AUTO provider=prov-a1 tier=L2' "$CASE_ROOT/tier.err"; then
  ok "autofill marker honors ROUTE_SUGGEST_TIER override"
else
  bad "autofill marker honors ROUTE_SUGGEST_TIER override ($(cat "$CASE_ROOT/tier.err"))"
fi
unset ROUTE_SUGGEST_TIER

# 场景 3：route_suggest 退出码非 0（degraded：summary 失联）→ 不改道、不 fail。
reset_autofill_case
PERSONAL_CONFIG_FILE="$CASE_ROOT/personal-degraded.json"
set +e
route_suggest_autofill_provider 2>"$CASE_ROOT/degraded.err"
degraded_rc=$?
set -e
assert_eq "$degraded_rc" "0" "degraded route_suggest stays fail-open"
assert_eq "$API_PROVIDER" "" "degraded route_suggest keeps provider empty"
if grep -Fq 'ROUTE_SUGGEST_AUTO' "$CASE_ROOT/degraded.err"; then
  bad "degraded route_suggest emits no marker"
else
  ok "degraded route_suggest emits no marker"
fi

# 场景 4：显式 --api-provider（API_PROVIDER 已非空）→ 跳过 route_suggest，
# 人工锁定优先，provider 不被覆盖。
reset_autofill_case
API_PROVIDER="prov-manual"
route_suggest_autofill_provider 2>"$CASE_ROOT/locked.err"
assert_eq "$API_PROVIDER" "prov-manual" "explicit provider is never overridden"
if grep -Fq 'ROUTE_SUGGEST_AUTO' "$CASE_ROOT/locked.err"; then
  bad "explicit provider emits no marker"
else
  ok "explicit provider emits no marker"
fi

# 场景 5：非 claude-code backend（provider 隔离仅 claude-code 有效）→ 跳过。
reset_autofill_case
WORKER_BACKEND_CANONICAL="codex"
route_suggest_autofill_provider 2>"$CASE_ROOT/backend.err"
assert_eq "$API_PROVIDER" "" "non-claude-code backend skips autofill"
if grep -Fq 'ROUTE_SUGGEST_AUTO' "$CASE_ROOT/backend.err"; then
  bad "non-claude-code backend emits no marker"
else
  ok "non-claude-code backend emits no marker"
fi

# 静态接线断言：主脚本必须 source helper、在 acquire_provider_lease 消费
# API_PROVIDER 之前调用 autofill（否则 lease key 与 runtime profile 用不到补选值）。
if grep -Fq 'source "$SCRIPT_DIR/spawn-worker-route-suggest.sh"' "$SPAWN_WORKER" \
  && grep -Eq '^route_suggest_autofill_provider$' "$SPAWN_WORKER"; then
  ok "entrypoint sources and invokes route suggest helper"
else
  bad "entrypoint sources and invokes route suggest helper"
fi
autofill_line=$(grep -En '^route_suggest_autofill_provider$' "$SPAWN_WORKER" | head -1 | cut -d: -f1)
lease_line=$(grep -En '^acquire_provider_lease$' "$SPAWN_WORKER" | head -1 | cut -d: -f1)
if [ -n "$autofill_line" ] && [ -n "$lease_line" ] && [ "$autofill_line" -lt "$lease_line" ]; then
  ok "autofill runs before provider lease consumes API_PROVIDER"
else
  bad "autofill runs before provider lease consumes API_PROVIDER (autofill=$autofill_line lease=$lease_line)"
fi

printf 'spawn-worker route-suggest tests: %s passed, %s failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
