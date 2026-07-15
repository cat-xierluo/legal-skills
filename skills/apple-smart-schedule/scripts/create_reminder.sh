#!/usr/bin/env bash
# apple-smart-schedule / create_reminder.sh
# 在 macOS「提醒事项」App 创建一条带截止时间的提醒，经 iCloud 同步到 iPhone/iPad。
# 【仅适用于 macOS】优先 remindctl(可查/改/删)，未安装则降级 osascript(仅创建)。
#
# 用法:
#   create_reminder.sh "<标题>" "<清单名>" "<截止时间>" ["<备注>"]
#   截止时间接受 ISO 8601 或 "YYYY-MM-DD HH:mm"。
set -euo pipefail

TITLE="${1:?用法: create_reminder.sh <标题> <清单名> <截止时间> [备注]}"
LIST="${2:?}"
DUE="${3:?}"
NOTES="${4:-}"

# remindctl --due 需要 "YYYY-MM-DD HH:mm"
DUE_RC=$(python3 - "$DUE" <<'PY'
import sys, re
s = sys.argv[1].strip().replace("T", " ")
m = re.match(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})", s)
if m:
    print(f"{m.group(1)} {m.group(2)}")
else:
    m2 = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    print(f"{m2.group(1)} 09:00" if m2 else s)
PY
)

if command -v remindctl >/dev/null 2>&1; then
  if [ -n "$LIST" ]; then
    remindctl add --title "$TITLE" --list "$LIST" --due "$DUE_RC" 2>&1
  else
    remindctl add --title "$TITLE" --due "$DUE_RC" 2>&1
  fi
  echo "[remindctl] 已创建提醒: $TITLE @ $DUE_RC"
else
  # 降级 osascript
  read -r RY RM RD RH RMI RS < <(python3 - "$DUE" <<'PY'
import sys, re
s = sys.argv[1].strip().replace("T", " ")
m = re.match(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})", s)
if m:
    print(*m.groups(), "0")
else:
    m2 = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    print(*m2.groups(), "09", "00", "0")
PY
)
  esc() { printf '%s' "$1" | sed 's/"/\\"/g'; }
  T_E=$(esc "$TITLE"); L_E=$(esc "$LIST")
  /usr/bin/osascript <<APPLESCRIPT 2>&1
on run
  set t to "$T_E"
  set lName to "$L_E"
  set d to current date
  set day of d to 1
  set year of d to $RY
  set month of d to $RM
  set day of d to $RD
  set hours of d to $RH
  set minutes of d to $RMI
  set seconds of d to $RS
  tell application "Reminders"
    if lName is "" or not (exists list lName) then
      set targetList to default list
    else
      set targetList to list lName
    end if
    set r to make new reminder in targetList with properties {name:t, due date:d, remind me date:d}
    return id of r
  end tell
end run
APPLESCRIPT
  echo "[osascript 降级] 已创建提醒: ${TITLE}（未装 remindctl；如需查改删可 brew install steipete/tap/remindctl）"
fi
