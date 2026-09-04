#!/usr/bin/env bash
# apple-smart-schedule / find_event.sh
# 在 macOS「日历」按日期窗口(+可选标题关键词)查询已有事件,供创建前查重/更新前定位。
# 【仅适用于 macOS】配合 update_event.sh:先 find 找到已有事件,再 update,避免重复新建。
#
# 用法:
#   find_event.sh "<日历名|ALL>" "<起始日期>" ["<结束日期>"] ["<标题关键词>"]
#   日期接受 "YYYY-MM-DD" 或含时分的 ISO;结束缺省 = 起始次日 00:00(单日窗口)。
#   日历名传 ALL 时遍历所有日历(含共享/订阅日历),每行输出带日历名。
#   输出每行: uid<TAB>日历<TAB>开始<TAB>结束<TAB>标题<TAB>地点<TAB>备注(截断120字,换行换空格)
#   无匹配 → 空输出;日历不存在 → 空输出+stderr 警告,退出码 0(查重语义下"没有"不算错)。
set -euo pipefail

CAL="${1:?用法: find_event.sh <日历名|ALL> <起始日期> [结束日期] [标题关键词]}"
START="${2:?}"
END="${3:-}"
KW="${4:-}"

# 用 python3 把窗口起止解析成绝对组件,规避 osascript 的 locale 日期解析坑
read -r SY SM SD SH SMI SS EY EM ED EH EMI ES < <(python3 - "$START" "$END" <<'PY'
import sys, re
from datetime import datetime, timedelta
def parse(s):
    s = s.strip().replace("T", " ")
    m = re.match(r"(\d{4}-\d{2}-\d{2})(?:[ T](\d{1,2}:\d{2}))?", s)
    if not m:
        raise SystemExit(f"无法解析日期: {s}")
    return datetime.fromisoformat(f"{m.group(1)} {(m.group(2) or '00:00')}")
def parts(d): return [d.year, d.month, d.day, d.hour, d.minute, d.second]
sd = parse(sys.argv[1])
e = sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else ""
ed = parse(e) if e else sd + timedelta(days=1)
if ed <= sd:
    ed = sd + timedelta(days=1)
print(*(parts(sd) + parts(ed)))
PY
)

esc() { printf '%s' "$1" | sed 's/"/\\"/g'; }
C_E=$(esc "$CAL"); K_E=$(esc "$KW")

/usr/bin/osascript <<APPLESCRIPT 2>&1
on run
  set calName to "$C_E"
  set kw to "$K_E"

  -- AppleScript 设日期组件要按顺序:先 day=1 再 year/month/day，避免月份溢出
  set winStart to current date
  set day of winStart to 1
  set year of winStart to $SY
  set month of winStart to $SM
  set day of winStart to $SD
  set hours of winStart to $SH
  set minutes of winStart to $SMI
  set seconds of winStart to $SS

  set winEnd to current date
  set day of winEnd to 1
  set year of winEnd to $EY
  set month of winEnd to $EM
  set day of winEnd to $ED
  set hours of winEnd to $EH
  set minutes of winEnd to $EMI
  set seconds of winEnd to $ES

  tell application "Calendar"
    set calList to {}
    if calName is "ALL" then
      set calList to every calendar
    else
      try
        set calList to {(first calendar whose name is calName)}
      on error
        log "警告: 找不到日历「" & calName & "」"
        return ""
      end try
    end if

    set outLines to {}
    repeat with c in calList
      if kw is "" then
        set evs to (every event of c whose start date ≥ winStart and start date < winEnd)
      else
        set evs to (every event of c whose start date ≥ winStart and start date < winEnd and summary contains kw)
      end if
      repeat with ev in evs
        set evStart to my fmtDate(start date of ev)
        set evEnd to my fmtDate(end date of ev)
        set evTitle to my repNL(summary of ev)
        set evLoc to my repNL(location of ev)
        set evNotes to my repNL(description of ev)
        if (length of evNotes) > 120 then set evNotes to (text 1 thru 120 of evNotes) & "…"
        set end of outLines to (uid of ev as text) & tab & (name of c) & tab & evStart & tab & evEnd & tab & evTitle & tab & evLoc & tab & evNotes
      end repeat
    end repeat
    set {od, my text item delimiters} to {my text item delimiters, {linefeed}}
    set out to outLines as text
    set my text item delimiters to od
    return out
  end tell
end run

on fmtDate(d)
  set mo to text -2 thru -1 of ("0" & (month of d as integer))
  set da to text -2 thru -1 of ("0" & (day of d as integer))
  set h to text -2 thru -1 of ("0" & (hours of d as integer))
  set mi to text -2 thru -1 of ("0" & (minutes of d as integer))
  return (year of d as text) & "-" & mo & "-" & da & " " & h & ":" & mi
end fmtDate

on repNL(t)
  if t is missing value then return ""
  set t to my repAll(t, return, " ")
  return my repAll(t, linefeed, " ")
end repNL

on repAll(t, a, b)
  set {od, my text item delimiters} to {my text item delimiters, {a}}
  set lst to every text item of t
  set my text item delimiters to {b}
  set r to lst as text
  set my text item delimiters to od
  return r
end repAll
APPLESCRIPT
