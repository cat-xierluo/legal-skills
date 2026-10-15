#!/usr/bin/env zsh
# night-revive-timer.sh —— 多终端守夜复活 v2(2026-08-28 守夜实战沉淀,Task-080)
#
# 用途:已知恢复时间(同账号 429 限流恢复等)时,脱开 PM/Orca 进程树,
#     在 wall-clock 时间点逐终端键盘注入复活文本(worker 先,PM 后),
#     把额度风暴后集体死 turn 的 worker 与 PM 拉回 ready。
#
# 与 night-watch.sh 的差别:
#   night-watch.sh 是有界探测+只对 PM terminal 一次唤醒(查 quota→available 状态机)。
#   night-revive-timer.sh 是定时一次性脚本:已知"何时恢复",先逐 worker 键盘注入复活文本
#   (turn 不会自愈,必须人或外部注入唤醒),间隔数秒后再向 PM 注入"核活+收口"指令。
#   零探测、零死窗消耗、最经济。
#
# 形态:nohup caffeinate -dis 包裹(脱离 PM/Orca 进程树——2026-08-28 实证 App Nap 屏灭会
#     冻结整树,与合盖无关;挂在 Orca/Electron 内的脚本屏灭即冻,守夜=0 唤醒)。
#
# 历史来源:~/BadmintonLab/ops/night-wake-20260829.sh(v1 只叫醒 PM,
#     漏了死 turn worker;v2 由用户 2026-08-28 22:02 要求补 worker 复活段)。
# 本脚本是该 v2 实战形态的参数化模板,落到 skill 自有目录以便跨项目复用。
#
# --- 关键不变量(违反即布防失败) ---
# 1. 所有必选参数(--pm-terminal/--workers-file/--revive-at/--wake-at/--revive-text/
#    --wake-text/--log)缺一即 fail-closed,不读默认值(防止误触)。
# 2. 时间格式严格 "YYYY-MM-DD HH:MM:SS";macOS date -j -f 解析;Linux 应改 gdate。
# 3. workers-file 一行一个 "handle<TAB>label"(label 用作日志 tag 与 orca terminal send
#    的可读标识);空文件、空行、注释行(#)允许;其它格式行 fail-closed。
# 4. caffeinate -dis:macOS 自带;不在 macOS 上本脚本无意义,直接 fail-closed。
# 5. 布防后必须立即做通道自测(向 PM 自身终端注入一行自测文本+向任一 worker 终端
#    注入探针;两条都确认送达才算布防完成——SKILL §4.6 守夜段,2026-08-28 双验)。
# 6. worker 429 死 turn 不会自愈:即使额度恢复,TUI 停 ready 不再消费 send;
#    必须 `orca terminal send --text ... --enter` 键盘注入唤醒。
#    `pm-orchestrate send` 投递 Dispatch inbox `ok:true` ≠ 被消费。
#
# 用法:
#   night-revive-timer.sh \
#     --pm-terminal term_xxx \
#     --workers-file /tmp/workers.tsv \
#     --revive-at  "2026-08-29 02:52:00" \
#     --wake-at    "2026-08-29 02:55:00" \
#     --revive-text "额度已恢复。请从断点继续..." \
#     --wake-text   "[守夜唤醒0255] ..." \
#     --log         ~/BadmintonLab/ops/night-wake.log
#   # 然后立即做通道自测(向 PM + 任一 worker 各注入一行/探针,确认送达)。

emulate -L zsh
set -euo pipefail

# ---------- 参数解析(fail-closed) ----------

usage() {
  cat <<'USAGE'
Usage: night-revive-timer.sh [options]

Required options:
  --pm-terminal HANDLE         PM Orca 终端 handle(已知恢复时间后注入收口指令的目标)
  --workers-file PATH          worker 清单文件,每行 "handle<TAB>label",
                               空行/# 注释行允许;其它格式 fail-closed
  --revive-at "YYYY-MM-DD HH:MM:SS"   复活六 worker 的 wall-clock 时间点
  --wake-at   "YYYY-MM-DD HH:MM:SS"   注入 PM 的 wall-clock 时间点(revive 之后)
  --revive-text TEXT           注入每个 worker 终端的复活文本(单行)
  --wake-text TEXT             注入 PM 终端的收口+核活指令(可多行;压成单行)
  --log PATH                   守夜日志路径(可追加;同一文件可与 PM 共享)

Other options:
  --revive-interval N          worker 顺序注入间隔秒数(默认 4)
  --repeat N                   打摆 lane 周期性复活间隔(秒)。>0 时启用周期性复活,
                               必须同时给 --until;每 N 秒重注一轮 worker,直至 UNTIL_AT
                               (默认 0 = 单发,不循环)
  --until "YYYY-MM-DD HH:MM:SS" 周期性复活的停止时间;必须与 --repeat 同时给,
                               必须早于 --wake-at,晚于 --revive-at
  --_armed                     内部旗标:caffeinate 子壳二次启动时携带,
                               表示跳过布防段直接进入 wall-clock 注入
  -h | --help                  显示本帮助并退出

Exit codes:
   0  正常布防完成(前端入口)/ caffeinate 子壳全部注入完成(armed 入口)
  64  用法错误/缺参数/格式校验失败
  70  workers-file 解析失败
  71  caffeinate 不可用(非 macOS 或 PATH 缺)
  72  wall-clock 时间格式不可解析(macOS date -j -f 拒绝)
 130  被信号中断(SIGINT/SIGTERM/HUP)
USAGE
}

PM_TERMINAL=""
WORKERS_FILE=""
REVIVE_AT=""
WAKE_AT=""
REVIVE_TEXT=""
WAKE_TEXT=""
LOG_FILE=""
REVIVE_INTERVAL=4
REPEAT_INTERVAL=0
UNTIL_AT=""
ARMED=0

# fail-closed 收集器:每解析一项就 set;最后留空即报错
missing=()

while [ $# -gt 0 ]; do
  case "$1" in
    --pm-terminal)
      [ $# -ge 2 ] || { echo "ERROR: --pm-terminal 需要值" >&2; exit 64; }
      PM_TERMINAL="$2"; shift 2 ;;
    --workers-file)
      [ $# -ge 2 ] || { echo "ERROR: --workers-file 需要值" >&2; exit 64; }
      WORKERS_FILE="$2"; shift 2 ;;
    --revive-at)
      [ $# -ge 2 ] || { echo "ERROR: --revive-at 需要值" >&2; exit 64; }
      REVIVE_AT="$2"; shift 2 ;;
    --wake-at)
      [ $# -ge 2 ] || { echo "ERROR: --wake-at 需要值" >&2; exit 64; }
      WAKE_AT="$2"; shift 2 ;;
    --revive-text)
      [ $# -ge 2 ] || { echo "ERROR: --revive-text 需要值" >&2; exit 64; }
      REVIVE_TEXT="$2"; shift 2 ;;
    --wake-text)
      [ $# -ge 2 ] || { echo "ERROR: --wake-text 需要值" >&2; exit 64; }
      WAKE_TEXT="$2"; shift 2 ;;
    --log)
      [ $# -ge 2 ] || { echo "ERROR: --log 需要值" >&2; exit 64; }
      LOG_FILE="$2"; shift 2 ;;
    --revive-interval)
      [ $# -ge 2 ] || { echo "ERROR: --revive-interval 需要值" >&2; exit 64; }
      REVIVE_INTERVAL="$2"; shift 2 ;;
    --repeat)
      [ $# -ge 2 ] || { echo "ERROR: --repeat 需要值" >&2; exit 64; }
      REPEAT_INTERVAL="$2"; shift 2 ;;
    --until)
      [ $# -ge 2 ] || { echo "ERROR: --until 需要值" >&2; exit 64; }
      UNTIL_AT="$2"; shift 2 ;;
    --_armed) ARMED=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: 未知参数 $1" >&2; usage >&2; exit 64 ;;
  esac
done

# ARMED 入口只做 wall-clock 注入;其它校验已在首次启动时跑过
if (( ARMED )); then
  # 仅校验 caffeinate 子壳再次启动时仍能解析时间与读 workers-file
  [ -r "$WORKERS_FILE" ] || { echo "ERROR(armed): workers-file 不可读" >&2; exit 70; }
  parse_epoch() {
    date -j -f "%Y-%m-%d %H:%M:%S" "$1" +%s 2>/dev/null || {
      echo "ERROR(armed): 时间 '$1' 不能被 date -j -f 解析" >&2
      exit 72
    }
  }
  REVIVE_EPOCH=$(parse_epoch "$REVIVE_AT")
  WAKE_EPOCH=$(parse_epoch "$WAKE_AT")

  # 解析 workers-file
  typeset -a A_HANDLES A_LABELS
  while IFS=$'\t' read -r handle label || [ -n "$handle" ]; do
    [[ -z "$handle" || "$handle" == \#* ]] && continue
    [[ "$handle" =~ ^[A-Za-z0-9._:-]+$ ]] || {
      echo "ERROR(armed): workers-file 行 '$handle\t$label' 的 handle 不合法" >&2
      exit 70
    }
    A_HANDLES+=("$handle")
    A_LABELS+=("${label:-$handle}")
  done < "$WORKERS_FILE"

  log() { echo "[$(date '+%F %T')] $*" >> "$LOG_FILE"; }
  send() {
    orca terminal send --terminal "$1" --text "$2" --enter >> "$LOG_FILE" 2>&1
    local rc=$?
    log "sent -> $3 ($1) exit=$rc"
    return $rc
  }
  wait_until() {
    local target_epoch now
    target_epoch=$(parse_epoch "$1")
    now=$(date +%s)
    if (( target_epoch <= now )); then
      log "WARN: target $1 already past"
      return 0
    fi
    sleep $(( target_epoch - now ))
  }

  log "--- armed shell entered; waiting for ${REVIVE_AT} ---"

  # ---- worker 复活段(首次) ----
  wait_until "$REVIVE_AT"
  log "--- worker revival pass: ${#A_HANDLES[@]} terminal(s) ---"
  for i in 1..${#A_HANDLES[@]}; do
    handle="${A_HANDLES[$i]}"
    label="${A_LABELS[$i]}"
    send "$handle" "$REVIVE_TEXT" "$label" || true
    if (( i < ${#A_HANDLES[@]} )); then
      sleep "$REVIVE_INTERVAL"
    fi
  done
  log "--- worker revival pass done ---"

  # ---- 周期性复活段(打摆 lane)— 仅当 --repeat > 0 且 --until 给定时启用 ----
  if (( REPEAT_INTERVAL > 0 )); then
    until_epoch=$(parse_epoch "$UNTIL_AT")
    log "--- periodic revival loop: every ${REPEAT_INTERVAL}s until ${UNTIL_AT} ---"
    while :; do
      now=$(date +%s)
      if (( now >= until_epoch )); then
        log "--- until time reached, exit periodic loop ---"
        break
      fi
      log "--- periodic revival pass ---"
      for i in 1..${#A_HANDLES[@]}; do
        handle="${A_HANDLES[$i]}"
        label="${A_LABELS[$i]}"
        send "$handle" "$REVIVE_TEXT" "$label" || true
        if (( i < ${#A_HANDLES[@]} )); then
          sleep "$REVIVE_INTERVAL"
        fi
      done
      log "--- periodic revival pass done ---"

      now=$(date +%s)
      remaining=$(( until_epoch - now ))
      sleep_for=$REPEAT_INTERVAL
      [ "$sleep_for" -le "$remaining" ] || sleep_for=$remaining
      if (( sleep_for <= 0 )); then
        break
      fi
      sleep "$sleep_for"
    done
    log "--- periodic revival loop done ---"
  fi

  # ---- PM 唤醒段 ----
  wait_until "$WAKE_AT"
  send "$PM_TERMINAL" "$WAKE_TEXT" "PM" || true
  log "=== night-revive v2 complete ==="
  exit 0
fi

# ===== 首次入口:必选参数校验 + caffeinate 布防 =====

[ -n "$PM_TERMINAL"  ] || missing+=("--pm-terminal")
[ -n "$WORKERS_FILE"  ] || missing+=("--workers-file")
[ -n "$REVIVE_AT"     ] || missing+=("--revive-at")
[ -n "$WAKE_AT"       ] || missing+=("--wake-at")
[ -n "$REVIVE_TEXT"   ] || missing+=("--revive-text")
[ -n "$WAKE_TEXT"     ] || missing+=("--wake-text")
[ -n "$LOG_FILE"      ] || missing+=("--log")

if [ ${#missing[@]} -gt 0 ]; then
  echo "ERROR: 缺必选参数:${(j:,:)missing}" >&2
  usage >&2
  exit 64
fi

# terminal handle:简单白名单(term_/ctx_/任意 [A-Za-z0-9._:-]+)
[[ "$PM_TERMINAL" =~ ^[A-Za-z0-9._:-]+$ ]] || {
  echo "ERROR: --pm-terminal '$PM_TERMINAL' 不合法(只允许 [A-Za-z0-9._:-])" >&2
  exit 64
}

# workers-file 必须存在、可读
[ -r "$WORKERS_FILE" ] || {
  echo "ERROR: --workers-file '$WORKERS_FILE' 不存在或不可读" >&2
  exit 70
}

# 时间格式严格 "YYYY-MM-DD HH:MM:SS";先用 macOS date -j -f 解析,失败即 fail-closed。
parse_epoch() {
  local ts="$1"
  date -j -f "%Y-%m-%d %H:%M:%S" "$ts" +%s 2>/dev/null || {
    echo "ERROR: 时间 '$ts' 不能被 'date -j -f %Y-%m-%d %H:%M:%S' 解析" >&2
    echo "       请用 macOS,或安装 coreutils 后改用 gdate -d" >&2
    exit 72
  }
}
REVIVE_EPOCH=$(parse_epoch "$REVIVE_AT")
WAKE_EPOCH=$(parse_epoch "$WAKE_AT")

[ "$REVIVE_EPOCH" -lt "$WAKE_EPOCH" ] || {
  echo "ERROR: --revive-at ($REVIVE_AT) 必须早于 --wake-at ($WAKE_AT)" >&2
  exit 64
}

# --repeat / --until 成对校验(打摆 lane 周期性复活)
if [ -n "$REPEAT_INTERVAL" ] && [ "$REPEAT_INTERVAL" != "0" ]; then
  # --repeat 已给
  [ -n "$UNTIL_AT" ] || {
    echo "ERROR: --repeat 已给(${REPEAT_INTERVAL}s),但缺 --until(--repeat 必须与 --until 成对)" >&2
    exit 64
  }
  # --repeat 必须为正整数
  [[ "$REPEAT_INTERVAL" =~ ^[1-9][0-9]*$ ]] || {
    echo "ERROR: --repeat '$REPEAT_INTERVAL' 不是正整数" >&2
    exit 64
  }
  UNTIL_EPOCH=$(parse_epoch "$UNTIL_AT")
  [ "$REVIVE_EPOCH" -lt "$UNTIL_EPOCH" ] || {
    echo "ERROR: --until ($UNTIL_AT) 必须晚于 --revive-at ($REVIVE_AT)" >&2
    exit 64
  }
  [ "$UNTIL_EPOCH" -lt "$WAKE_EPOCH" ] || {
    echo "ERROR: --until ($UNTIL_AT) 必须早于 --wake-at ($WAKE_AT)" >&2
    exit 64
  }
elif [ -n "$UNTIL_AT" ]; then
  # --until 已给但 --repeat 未给
  echo "ERROR: --until 已给(${UNTIL_AT}),但缺 --repeat(--until 必须与 --repeat 成对)" >&2
  exit 64
fi

# caffeinate 守卫
command -v caffeinate >/dev/null 2>&1 || {
  echo "ERROR: caffeinate 不可用——本脚本仅在 macOS 运行" >&2
  echo "       Linux 用 systemd-inhibit 或 loginctl 替代 -dis 的 App Nap/屏灭守护" >&2
  exit 71
}

# 日志目录兜底
LOG_DIR=$(dirname -- "$LOG_FILE")
[ -d "$LOG_DIR" ] || mkdir -p "$LOG_DIR" || {
  echo "ERROR: 日志目录 '$LOG_DIR' 无法创建" >&2
  exit 64
}

# 日志函数(首次入口与 armed 子壳共用)
log() { echo "[$(date '+%F %T')] $*" >> "$LOG_FILE"; }

# ---------- caffeinate -dis 布防 ----------
#
# -d:阻止系统休眠(display sleep prevention)
# -i:阻止系统空闲休眠
# -s:阻止系统完全休眠(AC 切断后)
# nohup:脱离父进程(PM/Orca 关闭/屏灭后仍存活)
# &:后台运行(本脚本立即返回,布防即结束;后续注入由 caffeinate 子壳按 wall-clock 执行)
#
# 教训:2026-08-28 实证,任何守夜装置不得只活在 Orca/Electron 进程树内——
# App Nap 屏灭冻结整进程树,与合盖无关,守夜=0 唤醒。
# caffeinate -dis 是 macOS 上保证脚本运行到时间点的最简手段。

log "=== night-revive v2 armed: revive@${REVIVE_AT} wake@${WAKE_AT} workers-file=${WORKERS_FILE} pm=${PM_TERMINAL} ==="

CAFFEINATE_BIN=$(command -v caffeinate)
CAFFEINATE_ARGS=(
  --pm-terminal "$PM_TERMINAL"
  --workers-file "$WORKERS_FILE"
  --revive-at "$REVIVE_AT"
  --wake-at "$WAKE_AT"
  --revive-text "$REVIVE_TEXT"
  --wake-text "$WAKE_TEXT"
  --log "$LOG_FILE"
  --revive-interval "$REVIVE_INTERVAL"
  --repeat "$REPEAT_INTERVAL"
  --until "$UNTIL_AT"
  --_armed
)
nohup "$CAFFEINATE_BIN" -dis "$0" "${CAFFEINATE_ARGS[@]}" >> "$LOG_FILE" 2>&1 &

ARMED_PID=$!
log "armed pid=${ARMED_PID}; caffeinate -dis detached;布防完成;立刻做通道自测(详见 SKILL §4.6)"

# 布防立即返回(前端脚本不等 wall-clock);前端必须:
#  1. 向 PM 自身注入一行自测文本(确认 PM 通道可达)
#  2. 向任一 worker 注入探针(确认 worker 通道可达)
#  两条都确认送达 = 布防完成;任一失败必须立即 abort/重发。
exit 0