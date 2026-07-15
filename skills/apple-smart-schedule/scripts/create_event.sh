#!/usr/bin/env bash
# apple-smart-schedule / create_event.sh
# 在 macOS「日历」App 创建一个事件，经 iCloud 自动同步到 iPhone/iPad。
# 【仅适用于 macOS】调用 osascript 操作苹果原生日历，不支持 Windows/Android/Linux。
#
# 用法:
#   create_event.sh "<标题>" "<日历名>" "<开始时间>" ["<结束时间>"] ["<地点>"] ["<备注>"]
#   时间接受 ISO 8601 或 "YYYY-MM-DD HH:mm[:ss]"，含或不含时区。
#   未给结束时间 → 默认时长 60 分钟。日历名不存在 → 落到第一个日历(兜底)。
set -euo pipefail

TITLE="${1:?用法: create_event.sh <标题> <日历名> <开始时间> [结束时间] [地点] [备注]}"
CAL="${2:?}"
START="${3:?}"
END="${4:-}"
LOC="${5:-}"
NOTES="${6:-}"

# 用 python3 把开始/结束时间解析成绝对组件，规避 osascript 的 locale 日期解析坑
read -r SY SM SD SH SMI SS EY EM ED EH EMI ES < <(python3 - "$START" "$END" <<'PY'
import sys, re
from datetime import datetime, timedelta
def parse(s):
    s = s.strip().replace("T", " ")
    m = (re.match(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}(?::\d{2})?)", s)
         or re.match(r"(\d{4}-\d{2}-\d{2})", s))
    return datetime.fromisoformat(m.group(0)) if m else datetime.now()
def parts(d): return [d.year, d.month, d.day, d.hour, d.minute, d.second]
sd = parse(sys.argv[1])
e = sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else ""
ed = parse(e) if e else sd + timedelta(minutes=60)
print(*(parts(sd) + parts(ed)))
PY
)

esc() { printf '%s' "$1" | sed 's/"/\\"/g'; }
T_E=$(esc "$TITLE"); C_E=$(esc "$CAL"); L_E=$(esc "$LOC"); N_E=$(esc "$NOTES")

/usr/bin/osascript <<APPLESCRIPT 2>&1
on run
  set eventTitle to "$T_E"
  set calName to "$C_E"
  set locStr to "$L_E"
  set notesStr to "$N_E"

  -- AppleScript 设日期组件要按顺序:先 day=1 再 year/month/day，避免月份溢出
  set startDate to current date
  set day of startDate to 1
  set year of startDate to $SY
  set month of startDate to $SM
  set day of startDate to $SD
  set hours of startDate to $SH
  set minutes of startDate to $SMI
  set seconds of startDate to $SS

  set endDate to current date
  set day of endDate to 1
  set year of endDate to $EY
  set month of endDate to $EM
  set day of endDate to $ED
  set hours of endDate to $EH
  set minutes of endDate to $EMI
  set seconds of endDate to $ES

  tell application "Calendar"
    if exists calendar calName then
      set targetCal to calendar calName
    else
      set targetCal to calendar 1
      log "警告: 找不到日历「" & calName & "」，已落到第一个日历"
    end if
    tell targetCal
      set newEvent to make new event at end of events with properties {summary:eventTitle, start date:startDate, end date:endDate}
      if locStr is not "" then set location of newEvent to locStr
      if notesStr is not "" then set description of newEvent to notesStr
      return id of newEvent
    end tell
  end tell
end run
APPLESCRIPT
