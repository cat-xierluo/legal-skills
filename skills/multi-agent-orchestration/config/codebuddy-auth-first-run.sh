#!/bin/bash
# ============================================================
# codebuddy CLI 首次认证脚本
# 用法：在 Terminal.app 中执行 bash 本文件
# 效果：去 hooks → 启动 hy3 交互模式 → 浏览器授权 → 恢复 hooks
# 日期：2026-07-10（DEC-110 排查后）
# ============================================================

set -e

echo ">>> 1/3 备份 settings.json"
cp ~/.codebuddy/settings.json ~/.codebuddy/settings.json.bak
echo "    已备份到 ~/.codebuddy/settings.json.bak"

echo ">>> 2/3 移除 hooks"
python3 -c "
import json
with open('$HOME/.codebuddy/settings.json') as f:
    d = json.load(f)
d.pop('hooks', None)
with open('$HOME/.codebuddy/settings.json', 'w') as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
print('    hooks 已移除')
"

echo ">>> 3/3 启动 codebuddy + hy3"
echo "    浏览器会弹出授权页面，完成授权后终端出现 > 提示符即成功。"
echo "    按 Ctrl+C 退出后执行：cp ~/.codebuddy/settings.json.bak ~/.codebuddy/settings.json"
echo ""
"/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/bin/codebuddy" --model hy3 -y

echo ""
echo ">>> 恢复 hooks..."
cp ~/.codebuddy/settings.json.bak ~/.codebuddy/settings.json
echo "    hooks 已恢复，认证完成。"
