#!/usr/bin/env bash
# read-worker-result.sh — 只读回读下游 M Code/CLI batch worker 的返回内容
#
# 与 upstream-audit 的 read-conclusion.sh 对称：那边回读 Codex 会话结论，
# 这边回读本 skill spawn 出去的 terminal-managed batch worker（mcode exec 等）
# 的最终总结与现场状态。
#
# 判定三态：
#   RUNNING — mcode/batch 进程仍活着（有或无中间输出都算在跑）
#   DONE    — 进程已退且拿到最终总结（终端 message）或 worktree 有 RESULT.md
#   DEAD    — 进程已退且既无终端总结也无 RESULT.md（静默死亡，需 PM 处置）
#
# 用法:
#   read-worker-result.sh --session <session-id> [--worktree PATH] [--tail N]
#     --session   spawn 时的 --session 名（如 iss153-r2），用于定位终端与 Session Context
#     --worktree  worker 的 worktree 路径（缺省时从 orca workspaces 按 session 反查）
#     --tail      终端尾部扫描行数（默认 400；批次越长可加大）
#
# 退出码: 0=RUNNING/DONE；1=DEAD 或定位失败

set -euo pipefail

SESSION="" WT="" TAIL=400
while [ $# -gt 0 ]; do
  case "$1" in
    --session) SESSION="$2"; shift 2;;
    --worktree) WT="$2"; shift 2;;
    --tail) TAIL="$2"; shift 2;;
    *) echo "未知参数: $1" >&2; exit 64;;
  esac
done
[ -n "$SESSION" ] || { echo "用法: $0 --session <session-id> [--worktree PATH] [--tail N]" >&2; exit 64; }

# ── 定位 worktree ──
if [ -z "$WT" ]; then
  WT=$(ls -d "$HOME"/orca/workspaces/*/* 2>/dev/null | while read -r d; do
    [ -d "$d/.claude/agent-sessions/$SESSION" ] && echo "$d" && break
  done)
fi
if [ -z "$WT" ] || [ ! -d "$WT" ]; then
  echo "错误: 找不到 session=$SESSION 的 worktree（试 --worktree 显式指定）" >&2
  exit 1
fi
echo "── worktree: $WT"

# ── 终端定位（orca terminal list 里标题含 session 名的项）──
HANDLE=$(orca terminal list 2>/dev/null | grep -B0 "$SESSION" | grep -oE "term_[a-f0-9-]{36}" | head -1)

# ── batch 进程存活（mcode exec 带 --input - 的进程，且其终端属于本 worktree）──
PROC_ALIVE=0
if pgrep -fl "mcode exec" 2>/dev/null | grep -q "input"; then
  # 粗判：任一 mcode exec 活着还不够，需其命令行/子进程树可关联本 worktree；
  # 无精确映射时以「终端仍有新增输出」兜底（见下方 RUNNING 判定）。
  PROC_ALIVE=1
fi

# ── worktree 现场 ──
echo "── HEAD: $(git -C "$WT" log --oneline -1 2>/dev/null | head -1)"
echo "── 脏文件: $(git -C "$WT" status --short 2>/dev/null | grep -cv '^??' || true)"
[ -f "$WT/RESULT.md" ] && echo "── RESULT.md: 有" || echo "── RESULT.md: 无"

# ── 终端尾部 → 提取最后的 message/总结与最近活动时间 ──
if [ -z "$HANDLE" ]; then
  echo "── 终端: 未找到（可能已关闭——已完成或被结算）"
  LASTMSG=""
  TERM_ALIVE=0
else
  TERM_ALIVE=1
  echo "── 终端: $HANDLE"
  LASTMSG=$(orca terminal read --terminal "$HANDLE" --limit "$TAIL" 2>/dev/null | python3 -c '
import json, sys
last_msg = ""
last_ts = 0
for line in sys.stdin:
    try:
        d = json.loads(line)
    except Exception:
        continue
    it = d.get("item", {})
    t = it.get("type", "")
    ts = d.get("timestampMs", 0)
    if ts > last_ts:
        last_ts = ts
    if t in ("agent_message", "message") and it.get("status") in (None, "completed", ""):
        text = it.get("content") or it.get("text") or ""
        if isinstance(text, list):
            text = "".join(str(c.get("text", "")) for c in text if isinstance(c, dict))
        if str(text).strip():
            last_msg = f"{ts}\t{text}"
print(last_msg)
')
fi

# ── 三态判定 ──
# 启发式：mcode 进程仍活着 → 即便已有 message 也判 RUNNING
#（2026-10-05 实测 154：中途 yield「后台任务会唤醒我」的 message 被误判 DONE）
if [ "$PROC_ALIVE" = "1" ]; then
  echo "═══ 判定: RUNNING（mcode 进程存活；已有输出 ${RECENT:-?} 分钟前）═══"
  [ -n "$LASTMSG" ] && echo "── 最新 message（未确认为最终结论）──" && echo "$LASTMSG" | cut -f2- | head -5
  exit 0
fi
if [ -n "$LASTMSG" ]; then
  echo "═══ 判定: DONE ═══"
  echo "$LASTMSG" | python3 -c '
import sys
line = sys.stdin.read()
ts, _, text = line.partition("\t")
print(f"── 完成时间: {ts}")
print("── 最终总结 ──────────────────────────")
print(text)
'
  exit 0
fi

# 进程在跑或终端近 5 分钟有活动 → RUNNING
NOW_MS=$(python3 -c 'import time; print(int(time.time()*1000))')
RECENT=$(orca terminal read --terminal "$HANDLE" --limit 3 2>/dev/null | python3 -c '
import json, sys, time
now = time.time() * 1000
last = 0
for line in sys.stdin:
    try: last = max(last, json.loads(line).get("timestampMs", 0))
    except Exception: pass
print(f"{(now-last)/60000:.1f}" if last else "-1")
' 2>/dev/null || echo "-1")
if [ "$TERM_ALIVE" = "1" ] && python3 -c "import sys; sys.exit(0 if 0 <= float('''$RECENT''') < 5 else 1)" 2>/dev/null; then
  echo "═══ 判定: RUNNING（终端 ${RECENT} 分钟前仍有输出；mcode 进程存活=${PROC_ALIVE}）═══"
  exit 0
fi

echo "═══ 判定: DEAD（无总结、无 RESULT.md、终端无近期输出；mcode 进程存活=${PROC_ALIVE}）═══"
echo "处置提示：查 orca terminal read --terminal $HANDLE --limit 60 取尾部诊断；"
echo "存活判定存疑时不要直接结算——先核 provider lease 与 worktree 现场。"
exit 1
