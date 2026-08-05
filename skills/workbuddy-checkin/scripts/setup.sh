#!/bin/bash
# ============================================================
# WorkBuddy 每日签到 - 环境安装脚本（通用版）
# 自动检测/安装 Electron 运行时，并验证令牌解密链路是否可用。
#
# 用法：./setup.sh [--electron <路径或自动下载>]
#   --electron auto   （默认）检测已有运行时，缺失则通过 npm 下载
#   --electron <path> 指定已安装的 Electron 二进制
# ============================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(dirname "$SCRIPT_DIR")"
RUNTIME_DIR="$SKILL_ROOT/.runtime"
ELECTRON_BIN="$RUNTIME_DIR/electron/Electron.app/Contents/MacOS/Electron"

echo "== WorkBuddy 每日签到 · 环境检查 =="

# ---------- 检测已存在的 Electron ----------
detect() {
  local cands=(
    "$HOME/.workbuddy/tools/electron/Electron.app/Contents/MacOS/Electron"
    "$ELECTRON_BIN"
    "$(command -v electron 2>/dev/null)"
  )
  for c in "${cands[@]}"; do
    if [ -n "$c" ] && [ -x "$c" ]; then echo "$c"; return 0; fi
  done
  return 1
}

MODE="${1:-auto}"
ELECTRON=""

case "$MODE" in
  auto)
    if ELECTRON="$(detect)"; then
      echo "✅ 已检测到 Electron：$ELECTRON"
    else
      echo "⚠️ 未检测到 Electron 运行时，尝试通过 npm 下载（约 100MB，需要 node/npm）..."
      command -v npm >/dev/null 2>&1 || { echo "❌ 未找到 npm，请先安装 Node.js，或手动放置 Electron 后重试"; exit 1; }
      mkdir -p "$RUNTIME_DIR"
      cd "$RUNTIME_DIR"
      npm init -y >/dev/null 2>&1
      npm install electron@37 >/dev/null 2>&1 || { echo "❌ Electron 下载失败（网络/代理问题），请手动安装"; exit 1; }
      mv node_modules/electron/dist "$RUNTIME_DIR/electron"
      rm -rf node_modules package.json package-lock.json
      ELECTRON="$ELECTRON_BIN"
      echo "✅ Electron 安装完成：$ELECTRON"
    fi
    ;;
  --electron)
    ELECTRON="$2"
    [ -x "$ELECTRON" ] || { echo "❌ 指定的 Electron 不存在：$ELECTRON"; exit 1; }
    echo "✅ 使用指定 Electron：$ELECTRON"
    ;;
  *)
    echo "用法：$0 [--electron <path>]"; exit 1;;
esac

# ---------- 验证解密链路 ----------
chmod +x "$SCRIPT_DIR/checkin.sh" 2>/dev/null
echo "== 验证令牌解密 =="
TOKEN=$(env -u ELECTRON_RUN_AS_NODE "$ELECTRON" "$SCRIPT_DIR/decrypt-token.js" 2>/dev/null \
  | grep "^DECRYPT_RESULT:" | sed 's/^DECRYPT_RESULT://')

if [ -z "$TOKEN" ] || [[ "$TOKEN" == ERR* ]]; then
  echo "❌ 解密失败（${TOKEN:-未知原因}）。请确认：1) 已安装并登录 WorkBuddy 桌面端；2) 应用名是 WorkBuddy（老版本 CodeBuddy 会自动兼容）。"
  exit 1
fi

echo "✅ 令牌解密成功（长度 ${#TOKEN}）"
echo ""
echo "== 完成 =="
echo "运行签到：  $SCRIPT_DIR/checkin.sh"
echo "设置定时：  每天 09:00 示例 → crontab -e 添加："
echo "  0 9 * * * $SCRIPT_DIR/checkin.sh >> $SKILL_ROOT/logs/checkin.log 2>&1"
