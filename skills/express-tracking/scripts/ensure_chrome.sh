#!/bin/bash
# express-tracking · 专属 Chrome 工位管理（幂等）
# 已跑（CDP 9222 活着）→ 直接复用（保留登录态/验证标记，绝不重启）
# 未跑 → 以持久 profile 启动（cookie 落盘，重启不丢）
set -u
PROFILE="$HOME/.cache/express-tracking/chrome-profile"
PORT=9222

if curl -s --max-time 2 "http://127.0.0.1:${PORT}/json/version" | grep -q "Browser"; then
  echo "CDP_ALREADY_RUNNING (port ${PORT}，复用现有会话)"
  exit 0
fi

mkdir -p "$PROFILE"
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --user-data-dir="$PROFILE" \
  --remote-debugging-port=${PORT} \
  --no-first-run --no-default-browser-check \
  --disable-blink-features=AutomationControlled \
  "https://www.11183.com.cn/query_express_delivery" \
  > /dev/null 2>&1 &

for i in $(seq 1 20); do
  sleep 1
  if curl -s --max-time 2 "http://127.0.0.1:${PORT}/json/version" | grep -q "Browser"; then
    echo "CDP_LAUNCHED (port ${PORT}, profile: $PROFILE)"
    exit 0
  fi
done
echo "CDP_LAUNCH_FAILED" >&2
exit 1
