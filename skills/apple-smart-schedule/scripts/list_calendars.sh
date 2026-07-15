#!/usr/bin/env bash
# apple-smart-schedule / list_calendars.sh
# 列出 macOS「日历」里所有日历名(首次配置 default_calendar 用)。【仅 macOS】
set -euo pipefail
/usr/bin/osascript -e 'tell application "Calendar" to get name of calendars' 2>&1
