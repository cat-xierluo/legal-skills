#!/bin/bash
# ============================================================
# WorkBuddy 每日积分签到（通用版，可分发）
#
# 流程：解密本地令牌 → 查询签到状态 → 未签到则领取 → 写日志
# 用法：
#   ./checkin.sh                      # 自动探测 Electron 运行时
#   WB_CHECKIN_ELECTRON=<path> ./checkin.sh
# 定时（示例，每天 09:00）：
#   crontab -e
#   0 9 * * * /path/to/checkin.sh >> /path/to/logs/checkin.log 2>&1
#
# ⚠️ 凭据安全提示：
#   - 本地令牌（accessToken）等同 WorkBuddy 账号密码，仅在本脚本内存中使用，
#     通过管道立即消费，不写入日志、不落地、不回显。
#   - 日志（logs/checkin.log）只记录签到结果（积分/连续天数），不含令牌。
#   - 切勿将日志、脚本输出粘贴分享或提交到任何仓库。
# ============================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DECRYPT_JS="$SCRIPT_DIR/decrypt-token.js"
LOG_DIR="$SCRIPT_DIR/../logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/checkin.log"

# ---------- 探测 Electron 运行时 ----------
find_electron() {
  # 1) 显式指定
  if [ -n "${WB_CHECKIN_ELECTRON:-}" ] && [ -x "$WB_CHECKIN_ELECTRON" ]; then
    echo "$WB_CHECKIN_ELECTRON"; return
  fi
  # 2) 本 skill 常见安装位置（含 Windows/Git Bash 路径，electron.exe）
  local cands=(
    "$HOME/.workbuddy/tools/electron/Electron.app/Contents/MacOS/Electron"
    "$HOME/.workbuddy/tools/electron/electron.exe"
    "$HOME/.workbuddy/skills/workbuddy-checkin/.runtime/electron/Electron.app/Contents/MacOS/Electron"
    "$HOME/.workbuddy/skills/workbuddy-checkin/.runtime/electron/electron.exe"
    "$SCRIPT_DIR/../.runtime/electron/Electron.app/Contents/MacOS/Electron"
    "$SCRIPT_DIR/../.runtime/electron/electron.exe"
    "$(command -v electron 2>/dev/null)"
  )
  for c in "${cands[@]}"; do
    if [ -n "$c" ] && [ -x "$c" ]; then echo "$c"; return; fi
  done
  echo ""
}

log() {
  local ts
  ts=$(date '+%Y-%m-%d %H:%M:%S')
  echo "[$ts] $*" | tee -a "$LOG_FILE"
}

# ---------- 可选：随机错峰（避免整点风暴） ----------
# 设置 WB_CHECKIN_JITTER=<秒> 时，脚本在开始前随机等待 0~N 秒
if [ -n "${WB_CHECKIN_JITTER:-}" ]; then
  jitter=$((RANDOM % WB_CHECKIN_JITTER))
  [ "$jitter" -gt 0 ] && sleep "$jitter"
fi

ELECTRON="$(find_electron)"
if [ -z "$ELECTRON" ]; then
  log "❌ 未找到 Electron 运行时。请先运行 setup.sh 安装，或设置 WB_CHECKIN_ELECTRON 指向 Electron 二进制。"
  exit 1
fi

# ---------- 1. 解密令牌 ----------
TOKEN=$(env -u ELECTRON_RUN_AS_NODE "$ELECTRON" "$DECRYPT_JS" 2>/dev/null \
  | grep "^DECRYPT_RESULT:" | sed 's/^DECRYPT_RESULT://')

if [ -z "$TOKEN" ] || [[ "$TOKEN" == ERR* ]]; then
  log "❌ 获取令牌失败（${TOKEN:-未知原因}）。请确认已安装并登录 WorkBuddy 桌面端。"
  exit 1
fi

API="https://copilot.tencent.com"

# ---------- 2. 查询签到状态 ----------
STATUS=$(curl -s -m 15 -X POST "$API/billing/meter/checkin-status" \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  -H "Authorization: Bearer $TOKEN" -d '{}' 2>/dev/null || echo "")

if [ -z "$STATUS" ]; then
  log "❌ 查询签到状态失败（网络异常）"
  exit 1
fi
if echo "$STATUS" | grep -qi "401\|unauthorized"; then
  log "❌ 令牌已过期（401），请打开 WorkBuddy 桌面端刷新登录态后重试"
  exit 1
fi

CHECKED=$(echo "$STATUS" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('data', {}).get('today_checked_in', False))
except Exception:
    print('unknown')
" 2>/dev/null)

if [ "$CHECKED" = "True" ]; then
  log "✅ 今日已签到，无需重复领取"
  exit 0
fi

# ---------- 3. 执行签到 ----------
RESULT=$(curl -s -m 15 -X POST "$API/billing/meter/daily-checkin" \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  -H "Authorization: Bearer $TOKEN" -d '{}' 2>/dev/null || echo "")

if [ -z "$RESULT" ]; then
  log "❌ 签到请求失败（网络异常）"
  exit 1
fi

CREDIT=$(echo "$RESULT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    if d.get('code') == 0:
        data = d.get('data', {})
        print(f\"OK credit={data.get('credit')} streak_days={data.get('streak_days')}\")
    else:
        print(f\"FAIL code={d.get('code')} msg={d.get('msg')}\")
except Exception:
    print('PARSE_ERR')
" 2>/dev/null)

if [[ "$CREDIT" == OK* ]]; then
  log "🎉 签到成功！领取 $CREDIT"
else
  log "⚠️ 签到未成功：$CREDIT"
fi
