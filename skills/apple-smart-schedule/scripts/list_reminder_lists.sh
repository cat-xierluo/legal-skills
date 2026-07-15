#!/usr/bin/env bash
# apple-smart-schedule / list_reminder_lists.sh
# 列出「提醒事项」里的清单名(首次配置 default_reminder_list 用)。【仅 macOS】
set -euo pipefail
if command -v remindctl >/dev/null 2>&1; then
  remindctl list 2>&1
else
  /usr/bin/osascript -e 'tell application "Reminders" to get name of lists' 2>&1
fi
