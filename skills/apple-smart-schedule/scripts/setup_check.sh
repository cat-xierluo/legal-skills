#!/usr/bin/env bash
# apple-smart-schedule / setup_check.sh
# 首次使用自检:依赖、权限、日历/清单名。【仅 macOS】
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== apple-smart-schedule 环境自检（仅 macOS）==="
echo
echo "[依赖]"
echo "  osascript : $(command -v osascript || echo 缺失)"
if command -v remindctl >/dev/null 2>&1; then
  echo "  remindctl : $(command -v remindctl) ✓（推荐，提醒可查/改/删）"
else
  echo "  remindctl : 未安装 → 将用 osascript 降级（提醒仅可创建）"
  echo "              如需更全: brew install steipete/tap/remindctl"
fi
echo "  python3   : $(command -v python3 || echo 缺失)"
echo
echo "[日历名] → 用于 config.json 的 default_calendar"
echo "  (首次会弹「xxx 想控制 日历」对话框，点「好」即可)"
bash "$DIR/list_calendars.sh" 2>&1 || echo "  ⚠ 读取失败:点弹窗「好」后重跑本脚本;若曾拒绝,去 系统设置>隐私与安全>自动化 打开开关"
echo
echo "[提醒清单名] → 用于 config.json 的 default_reminder_list"
echo "  (首次会弹「xxx 想控制 提醒事项」对话框，点「好」即可)"
bash "$DIR/list_reminder_lists.sh" 2>&1 || echo "  ⚠ 读取失败:点弹窗「好」后重跑本脚本;若曾拒绝,去 自动化 设置打开开关"
echo
echo "[平台] 本 skill 仅在 macOS 运行;建好的日历/提醒经 iCloud 自动同步到 iPhone/iPad。"
echo "[授权] 每换一个终端 App 首次用,会再弹一次授权窗——正常现象,点「好」即可(授权按终端分别记录)。"
