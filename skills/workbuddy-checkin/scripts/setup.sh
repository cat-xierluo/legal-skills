#!/bin/bash
# ============================================================
# WorkBuddy 每日签到 - 环境安装脚本（通用版）
# 检测运行时并验证令牌读取链路是否可用。
#
# v5.3.8+ 新版登录态为明文 JSON，纯 Node 即可读取，无需 Electron。
# 仅当使用旧版 WorkBuddy/CodeBuddy（state.vscdb 加密登录态）时才需要 Electron。
#
# 用法：./setup.sh [--electron <路径或自动下载>]
#   （默认）自动探测：Node 优先；旧版账户缺失 Electron 时提示安装
#   --electron auto   检测已有运行时，缺失则通过 npm 下载
#   --electron <path> 指定已安装的 Electron 二进制（旧版账户用）
# ============================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(dirname "$SCRIPT_DIR")"
RUNTIME_DIR="$SKILL_ROOT/.runtime"
ELECTRON_BIN="$RUNTIME_DIR/electron/Electron.app/Contents/MacOS/Electron"

echo "== WorkBuddy 每日签到 · 环境检查 =="

# ---------- 探测 Node（v5.3.8+ 新版明文登录态优先用 Node 直读）----------
find_node() {
  local cands=(
    "$(command -v node 2>/dev/null)"
    "$HOME/.local/bin/node"
    "/opt/homebrew/bin/node"
    "/usr/local/bin/node"
    "$HOME/.nvm/versions/node"/*/bin/node
  )
  for c in "${cands[@]}"; do
    if [ -n "$c" ] && [ -x "$c" ]; then echo "$c"; return 0; fi
  done
  return 1
}

# ---------- 探测已存在的 Electron（仅旧版 state.vscdb 回退需要）----------
detect_electron() {
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

# ---------- 用 Node 探测新版明文登录态是否可用（不输出 token 内容）----------
probe_token_with_node() {
  local node_bin line
  node_bin="$(find_node)" || return 1
  line=$("$node_bin" "$SCRIPT_DIR/decrypt-token.js" 2>/dev/null | grep "^DECRYPT_RESULT:" | head -1)
  [ -n "$line" ] || return 1
  case "$line" in
    DECRYPT_RESULT:ERR*) return 1;;   # 新版文件缺失/异常 → 走旧版流程
    *) return 0;;
  esac
}

chmod +x "$SCRIPT_DIR/checkin.sh" 2>/dev/null

# ============================================================
# 路径 A：新版明文登录态（v5.3.8+）→ 纯 Node 即可，无需 Electron
# ============================================================
if probe_token_with_node; then
  NODE_BIN="$(find_node)"
  echo "✅ 检测到新版登录态（WorkBuddy v5.3.8+ 明文存储），Node 可直接读取。"
  echo "✅ 令牌读取链路可用（运行时：${NODE_BIN}），无需安装 Electron。"
  echo ""
  echo "== 完成 =="
  echo "运行签到：  $SCRIPT_DIR/checkin.sh"
  echo "设置定时：  每天 09:00 示例 → crontab -e 添加："
  echo "  0 9 * * * $SCRIPT_DIR/checkin.sh >> $SKILL_ROOT/logs/checkin.log 2>&1"
  exit 0
fi

# ============================================================
# 路径 B：旧版 state.vscdb 加密登录态 → 需要 Electron 运行时
# ============================================================
echo "（未检测到新版明文登录态，按旧版 state.vscdb 流程处理，需要 Electron 运行时。）"
echo ""

MODE="${1:-auto}"
ELECTRON=""

# 供应链安全：自动从 npm 下载第三方运行时（约 100MB）默认关闭，需显式开启。
# 推荐手动指定已校验的 Electron：setup.sh --electron /path/to/electron
if [ -z "${WB_CHECKIN_AUTO_INSTALL_ELECTRON:-}" ] && [ "$MODE" = "auto" ]; then
  if ELECTRON="$(detect_electron)"; then
    echo "✅ 已检测到 Electron：$ELECTRON"
  else
    echo "⚠️ 未检测到 Node 可读的新版登录态，也未找到 Electron 运行时。"
    echo "   大多数用户应先确认：已安装 WorkBuddy 桌面端 v5.3.8+ 并登录（新版登录态优先用 Node 读取）。"
    echo "   仅旧版 WorkBuddy/CodeBuddy（state.vscdb）账户才需要 Electron，二选一："
    echo "   1) 手动指定已校验的 Electron：  setup.sh --electron /path/to/electron"
    echo "   2) 确认要从官方 npm 下载（约 100MB），先执行："
    echo "        export WB_CHECKIN_AUTO_INSTALL_ELECTRON=1"
    echo "      再运行本脚本。"
    echo "   （手动放置后也可用环境变量 WB_CHECKIN_ELECTRON=<path> 直接运行 checkin.sh）"
    exit 1
  fi
else
  case "$MODE" in
    auto)
      if ELECTRON="$(detect_electron)"; then
        echo "✅ 已检测到 Electron：$ELECTRON"
      else
        echo "⚠️ 未检测到 Electron 运行时，尝试通过 npm 下载（约 100MB，需要 node/npm）..."
        echo "   ⚠️ 供应链提示：将从官方 npm registry 下载 electron@37 并执行，请确认网络可信。"
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
fi

# ---------- 验证旧版解密链路 ----------
echo "== 验证令牌解密 =="
TOKEN=$(env -u ELECTRON_RUN_AS_NODE "$ELECTRON" "$SCRIPT_DIR/decrypt-token.js" 2>/dev/null \
  | grep "^DECRYPT_RESULT:" | sed 's/^DECRYPT_RESULT://')

if [ -z "$TOKEN" ] || [[ "$TOKEN" == ERR* ]]; then
  echo "❌ 解密失败（${TOKEN:-未知原因}）。请确认：1) 已安装并登录 WorkBuddy 桌面端；2) 旧版账户应用名为 WorkBuddy（老版本 CodeBuddy 设 WB_CHECKIN_APP_NAME=CodeBuddy）；3) 新版 v5.3.8+ 账户应安装 Node.js 用 Node 直读。"
  exit 1
fi

echo "✅ 令牌解密成功（长度 ${#TOKEN}）"
echo ""
echo "== 完成 =="
echo "运行签到：  $SCRIPT_DIR/checkin.sh"
echo "设置定时：  每天 09:00 示例 → crontab -e 添加："
echo "  0 9 * * * $SCRIPT_DIR/checkin.sh >> $SKILL_ROOT/logs/checkin.log 2>&1"
