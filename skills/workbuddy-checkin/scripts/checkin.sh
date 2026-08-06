#!/bin/bash
# ============================================================
# WorkBuddy 每日积分签到（通用版，可分发）
#
# 流程：读取本地令牌 → 查询签到状态 → 未签到则领取 → 写日志
# 用法：
#   ./checkin.sh                      # 自动探测运行时（Node 优先，Electron 回退）
#   WB_CHECKIN_NODE=<path> ./checkin.sh
#   WB_CHECKIN_ELECTRON=<path> ./checkin.sh
# 定时（示例，每天 09:00）：
#   crontab -e
#   0 9 * * * /path/to/checkin.sh >> /path/to/logs/checkin.log 2>&1
#
# 运行时策略：
#   - 优先用 Node 读取 v5.3.8+ 的新版明文登录态（无需 Electron）。
#   - 新版明文文件缺失时，回退到 Electron + safeStorage 解密旧版 state.vscdb。
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

# ---------- 探测 Node 运行时（v5.3.8+ 新版明文登录态优先用 Node 直读） ----------
find_node() {
  # 1) 显式指定
  if [ -n "${WB_CHECKIN_NODE:-}" ] && [ -x "$WB_CHECKIN_NODE" ]; then
    echo "$WB_CHECKIN_NODE"; return
  fi
  # 2) PATH 上的 node + 常见绝对路径（cron/launchd 的 PATH 可能很精简）
  local cands=(
    "$(command -v node 2>/dev/null)"
    "$HOME/.local/bin/node"
    "/opt/homebrew/bin/node"
    "/usr/local/bin/node"
    "$HOME/.nvm/versions/node"/*/bin/node
  )
  for c in "${cands[@]}"; do
    if [ -n "$c" ] && [ -x "$c" ]; then echo "$c"; return; fi
  done
  echo ""
}

# ---------- 探测 Electron 运行时（仅旧版 state.vscdb 回退分支需要） ----------
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

# ---------- 读取令牌：Node 优先，Electron 回退 ----------
read_token() {
  local out="" node_bin electron_bin
  node_bin="$(find_node)"
  if [ -n "$node_bin" ]; then
    out=$("$node_bin" "$DECRYPT_JS" 2>/dev/null | grep "^DECRYPT_RESULT:" | sed 's/^DECRYPT_RESULT://')
  fi
  if [ -z "$out" ] || [[ "$out" == ERR* ]]; then
    # Node 未产出 token（未装 Node / 崩溃），或 Node 报 ERR（如旧版账户无明文文件、
    # 纯 Node 无法解密 state.vscdb）→ 回退到 Electron 解旧版库
    electron_bin="$(find_electron)"
    if [ -n "$electron_bin" ]; then
      out=$(env -u ELECTRON_RUN_AS_NODE "$electron_bin" "$DECRYPT_JS" 2>/dev/null \
        | grep "^DECRYPT_RESULT:" | sed 's/^DECRYPT_RESULT://')
    fi
  fi
  echo "$out"
}

log() {
  local ts
  ts=$(date '+%Y-%m-%d %H:%M:%S')
  echo "[$ts] $*" | tee -a "$LOG_FILE"
}

# ---------- 可选：随机错峰（避免整点风暴） ----------
# 设置 WB_CHECKIN_JITTER=<正整数秒> 时，脚本在开始前随机等待 0~N 秒
# 须 > 0：RANDOM % 0 会触发除零异常；非数字也会被 `[ -gt 0 ]` 拒绝（静默跳过）
if [ "${WB_CHECKIN_JITTER:-0}" -gt 0 ] 2>/dev/null; then
  jitter=$((RANDOM % WB_CHECKIN_JITTER))
  [ "$jitter" -gt 0 ] && sleep "$jitter"
fi

# ---------- 1. 读取令牌 ----------
TOKEN="$(read_token)"

if [ -z "$TOKEN" ]; then
  log "❌ 未找到 Node 或 Electron 运行时，或运行时未能产出令牌。请安装 Node.js，或设置 WB_CHECKIN_NODE / WB_CHECKIN_ELECTRON 指向可用运行时。"
  exit 1
fi
if [[ "$TOKEN" == ERR* ]]; then
  log "❌ 获取令牌失败（${TOKEN}）。请确认已安装并登录 WorkBuddy 桌面端。"
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

# 注意：today_checked_in 字段在 v5.3.8 实测不可靠（签到成功后仍可能为 false）。
# 此处仅用于「能省一次签到请求就省」的快速短路与 401 探测；真正的幂等兜底
# 放在下方 daily-checkin 的 code=10001 处理。
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
    elif d.get('code') == 10001:
        # 当日已签到：接口幂等拒绝，视为成功
        print('ALREADY today')
    else:
        print(f\"FAIL code={d.get('code')} msg={d.get('msg')}\")
except Exception:
    print('PARSE_ERR')
" 2>/dev/null)

if [[ "$CREDIT" == OK* ]]; then
  log "🎉 签到成功！领取 $CREDIT"
elif [[ "$CREDIT" == ALREADY* ]]; then
  log "✅ 今日已签到，无需重复领取（接口返回已签到）"
elif [ -z "$CREDIT" ]; then
  # 多为缺 python3 导致结果无法解析：服务端可能已成功，不能误报失败
  log "⚠️ 签到请求已提交，但缺少 python3 无法解析结果（请打开 WorkBuddy 确认；安装 python3 可恢复明细）"
else
  log "⚠️ 签到未成功：$CREDIT"
fi
