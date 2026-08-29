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

# v2.9.4：自动补选的 provider 必须同时注入运行 env。spawn-worker 的设计里
# provider env 注入本是 PM 职责（eval render-runtime-profile 生成 --command），
# 自动补选路径没有这层——补选后裸 claude 继承用户全局默认 provider，与 lease
# 计数的 lane 不一致（2026-08-29 实测：补选 minimax-M3 但裸 claude 走全局
# 配置，MiniMax 后端报 400 modelCode 不存在）。修复：命令为 backend 默认值
# （用户未显式 --command）时，用 claude-provider-env.sh 包装注入
# config/$API_PROVIDER.settings.json 的 env + --model。settings 缺失或 model
# 解析失败保持裸命令（fail-open，行为回到修复前，不阻断 spawn）。
route_suggest_wrap_command() {
  [ -n "${API_PROVIDER:-}" ] || return 0
  [ "${COMMAND_WAS_DEFAULT:-0}" = "1" ] || return 0
  [ "${WORKER_BACKEND_CANONICAL:-}" = "claude-code" ] || return 0
  local wrapper="$SCRIPT_DIR/claude-provider-env.sh"
  local settings="$SCRIPT_DIR/../config/$API_PROVIDER.settings.json"
  [ -f "$wrapper" ] && [ -f "$settings" ] || return 0
  local model
  model=$(python3 - "$settings" <<'PY' 2>/dev/null
import json, sys
try:
    cfg = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
print((cfg.get("env") or {}).get("ANTHROPIC_MODEL", ""))
PY
) || model=""
  [ -n "$model" ] || return 0
  COMMAND="bash '$wrapper' --settings '$settings' --model '$model' -- $COMMAND --permission-mode auto"
  echo "ROUTE_SUGGEST_ENV: provider=${API_PROVIDER} settings=${API_PROVIDER}.settings.json model=${model}（默认命令自动包装 provider env）" >&2
  return 0
}
