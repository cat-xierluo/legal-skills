#!/usr/bin/env bash
# spawn-worker-route-suggest.sh — 额度感知路由兜底（quota-aware routing 集成点 B）。
# This file is sourced after spawn-worker.sh resolves the worker backend identity
# and before acquire_provider_lease consumes API_PROVIDER.

# --api-provider 未显式给出且个人配置启用 quota_aware_routing 时，调
# route_suggest.py 按 tier 评分补选 provider。route_suggest 输出
# not_configured/degraded → 保持空（走既有默认链路），不 fail、不静默改道；
# 显式 --api-provider 永远优先（人工锁定 > 动态路由）。tier 由调用方经
# ROUTE_SUGGEST_TIER 环境变量传入（缺省 L1）。全程 fail-open：本函数任何
# 分支都不允许阻断 spawn。
route_suggest_autofill_provider() {
  [ -z "${API_PROVIDER:-}" ] || return 0
  [ "${WORKER_BACKEND_CANONICAL:-}" = "claude-code" ] || return 0
  if python3 - "${PERSONAL_CONFIG_FILE:-}" <<'PY' 2>/dev/null
import json, sys
try:
    cfg = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
qar = cfg.get("quota_aware_routing") or {}
sys.exit(0 if qar.get("enabled") else 1)
PY
  then
    local tier="${ROUTE_SUGGEST_TIER:-L1}"
    local route_suggest_out suggested
    route_suggest_out=$(python3 "$SCRIPT_DIR/route_suggest.py" --tier "$tier" \
      --config "$PERSONAL_CONFIG_FILE" 2>/dev/null) || route_suggest_out=""
    suggested=$(printf '%s' "$route_suggest_out" | python3 -c \
      'import json,sys; d=json.load(sys.stdin); print(d.get("provider","")) if d.get("status")=="ok" else None' 2>/dev/null || true)
    if [ -n "$suggested" ]; then
      API_PROVIDER="$suggested"
      echo "ROUTE_SUGGEST_AUTO provider=$API_PROVIDER tier=$tier" >&2
    fi
  fi
  return 0
}
