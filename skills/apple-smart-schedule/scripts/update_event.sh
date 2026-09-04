#!/usr/bin/env bash
# apple-smart-schedule / update_event.sh
# 修改 macOS「日历」App 中**已有**的事件 —— create_event.sh 只能新建，改已有的用它。
# 经 iCloud 自动同步到 iPhone/iPad。【仅 macOS】
#
# 用法:
#   update_event.sh "<UID 或 标题关键词>" ["<新标题>"] ["<开始>"] ["<结束>"] ["<地点>"] ["<备注>"]
#
#   · 第 2–6 个参数传 "-" 表示「不改这一项」
#   · 开始/结束可只改其一，另一个填 "-"
#   · 第 1 个参数形如 UUID 时按 UID 精确匹配，否则按标题包含匹配
#   · 标题匹配到多个事件时**拒绝修改**并返回候选清单（防止误改同名事件）
#   · 时间接受 ISO 8601 或 "YYYY-MM-DD HH:mm[:ss]"
#
# 搜索窗口（性能关键：不加窗口会全量遍历日历，事件多时极慢）：
#   默认只在 [今天-7天, 今天+400天] 内查找，可用环境变量覆盖：
#     BACK_DAYS=30 AHEAD_DAYS=800 update_event.sh "关键词" ...
#
# 返回: OK_UPDATED <标题> <开始> → <结束> | NOT_FOUND | MULTI_MATCH:<数量> + 候选清单
set -euo pipefail

KEY="${1:?用法: update_event.sh <UID或标题关键词> [新标题] [开始] [结束] [地点] [备注]}"
TITLE="${2:-}"; START="${3:-}"; END="${4:-}"; LOC="${5:-}"; NOTES="${6:-}"
BACK_DAYS="${BACK_DAYS:-7}"; AHEAD_DAYS="${AHEAD_DAYS:-400}"

# 是否修改该项（空或 "-" 表示不改）
START_SET=1; END_SET=1; TITLE_SET=1; LOC_SET=1; NOTES_SET=1
[ -z "$START" ] || [ "$START" = "-" ] && START_SET=0 || true
[ -z "$END" ]   || [ "$END"   = "-" ] && END_SET=0   || true
[ -z "$TITLE" ] || [ "$TITLE" = "-" ] && TITLE_SET=0 || true
[ -z "$LOC" ]   || [ "$LOC"   = "-" ] && LOC_SET=0   || true
[ -z "$NOTES" ] || [ "$NOTES" = "-" ] && NOTES_SET=0 || true

# 定位模式：UUID 格式 → uid；否则 → title
if printf '%s' "$KEY" | grep -Eq '^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$'; then
  MODE="uid"
else
  MODE="title"
fi

read -r SY SM SD SH SMI SS EY EM ED EH EMI ES D1Y D1M D1D D2Y D2M D2D < <(python3 - "$START" "$END" "$BACK_DAYS" "$AHEAD_DAYS" <<'PYEOF'
import sys, re
from datetime import datetime, timedelta
def parse(s):
    s = (s or "").strip().replace("T", " ")
    m = (re.match(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}(?::\d{2})?)", s)
         or re.match(r"(\d{4}-\d{2}-\d{2})", s))
    return datetime.fromisoformat(m.group(0)) if m else None
def parts(d):
    return [d.year, d.month, d.day, d.hour, d.minute, d.second] if d else [0]*6
sd = parse(sys.argv[1]) if len(sys.argv) > 1 else None
ed = parse(sys.argv[2]) if len(sys.argv) > 2 else None
back, ahead = int(sys.argv[3]), int(sys.argv[4])
now = datetime.now()
d1, d2 = now - timedelta(days=back), now + timedelta(days=ahead)
print(*(parts(sd) + parts(ed) + [d1.year, d1.month, d1.day, d2.year, d2.month, d2.day]))
PYEOF
)

# 转义双引号;换行只在行间转成 " & linefeed & " 拼接(字面量不能含裸换行;单行/末行不加,否则等值匹配会带上换行符)
esc() {
  local s="${1//\"/\\\"}" out="" line
  while IFS= read -r line; do
    [ -n "$out" ] && out+='" & linefeed & "'
    out+="$line"
  done <<< "$s"
  printf '%s' "$out"
}
K_E=$(esc "$KEY"); T_E=$(esc "$TITLE"); L_E=$(esc "$LOC"); N_E=$(esc "$NOTES")

/usr/bin/osascript <<APPLESCRIPT 2>&1
on run
  set keyStr to "$K_E"
  set titleStr to "$T_E"
  set locStr to "$L_E"
  set notesStr to "$N_E"
  set modeStr to "$MODE"
  set titleSet to $TITLE_SET
  set startSet to $START_SET
  set endSet to $END_SET
  set locSet to $LOC_SET
  set notesSet to $NOTES_SET

  -- 搜索窗口：不加窗口会全量遍历日历，事件多时慢到不可用
  set d1 to current date
  set day of d1 to 1
  set year of d1 to $D1Y
  set month of d1 to $D1M
  set day of d1 to $D1D
  set hours of d1 to 0
  set minutes of d1 to 0
  set seconds of d1 to 0

  set d2 to current date
  set day of d2 to 1
  set year of d2 to $D2Y
  set month of d2 to $D2M
  set day of d2 to $D2D
  set hours of d2 to 23
  set minutes of d2 to 59
  set seconds of d2 to 59

  set matchEvents to {}

  tell application "Calendar"
    repeat with c in calendars
      try
        if modeStr is "uid" then
          set evs to (every event of c whose uid is keyStr and start date is greater than or equal to d1 and start date is less than or equal to d2)
        else
          set evs to (every event of c whose summary contains keyStr and start date is greater than or equal to d1 and start date is less than or equal to d2)
        end if
        repeat with e in evs
          set end of matchEvents to e
        end repeat
      end try
    end repeat

    if (count of matchEvents) is 0 then return "NOT_FOUND"

    if (count of matchEvents) > 1 then
      set msg to "MULTI_MATCH:" & (count of matchEvents) & " 个事件匹配「" & keyStr & "」，已拒绝修改。请用 UID 精确指定，候选："
      repeat with e in matchEvents
        set msg to msg & linefeed & "  - " & (summary of e) & "  " & ((start date of e) as string) & "  UID=" & (uid of e)
      end repeat
      return msg
    end if

    set e to item 1 of matchEvents

    -- ⚠️ 组件顺序：先 day=1，再 year/month/day，最后 hours/minutes/seconds（避免月份溢出）
    -- ⚠️ 禁止用减法跨天：要「9 日 17:00」就直接设 day=9, hours=17；
    --    写成 day=9, hours=0 再减 7 小时会跨天回退成 8 日 17:00，把两天行程压进一天。
    if startSet is 1 then
      set sd to current date
      set day of sd to 1
      set year of sd to $SY
      set month of sd to $SM
      set day of sd to $SD
      set hours of sd to $SH
      set minutes of sd to $SMI
      set seconds of sd to $SS
      set start date of e to sd
    end if

    if endSet is 1 then
      set ed to current date
      set day of ed to 1
      set year of ed to $EY
      set month of ed to $EM
      set day of ed to $ED
      set hours of ed to $EH
      set minutes of ed to $EMI
      set seconds of ed to $ES
      set end date of e to ed
    end if

    if titleSet is 1 then set summary of e to titleStr
    if locSet   is 1 then set location of e to locStr
    if notesSet is 1 then set description of e to notesStr

    return "OK_UPDATED " & (summary of e) & "  " & ((start date of e) as string) & "  →  " & ((end date of e) as string)
  end tell
end run
APPLESCRIPT
