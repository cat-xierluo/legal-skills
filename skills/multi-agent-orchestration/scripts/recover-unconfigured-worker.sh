#!/usr/bin/env bash
# recover-unconfigured-worker.sh — spawn 后 agent_unconfigured 的 PM 侧一键恢复。
#
# 背景（2026-08-30 FaroPDF/legal-skills 编排 5+ 次复现，概率约 20%）：spawn 的
# terminal 已创建，但里面 agent TUI 未起（Orca 报 agent_unconfigured / no
# recognized agent 家族），worker-start 失败 → Task 停 [ready]、dispatch 未绑、
# worker_done 无通道。现行恢复 = PM 手工三步：读 METADATA runtime.command →
# orca terminal send 重注入 → register --reset-failed。本脚本把三步自动化。
#
# 恢复时序：
#   ① 读 Session Context METADATA（runtime.command / terminal_handle /
#      supervised 路由段），缺路由段 → manual-required（exit 3）
#   ② 幂等门：dispatch-show 已绑 + 终端 TUI 特征在 → already-healthy（exit 0，
#      零副作用）；dispatch 已绑但无 TUI → manual-required（不盲注入，防双跑）
#   ③ 终端活性：orca terminal read 失败 → manual-required（exit 2，不重试、
#      绝不 terminal create —— 恢复不产生第二个 terminal）
#   ④ TUI 存在判定：orca worker-show 对 external terminal 不提供 agent 识别
#      接口，改用 terminal read 的 tail 特征（RECOVER_TUI_DETECT）：
#      - tui     tail 命中强 TUI 标记（Claude Code 横幅/输入框/tokens left 等）
#      - shell   无 TUI 标记且末行是裸 shell 提示符（$ % > # 结尾）
#      - unknown 两者皆非（trust dialog/空 tail/杂乱输出）→ manual-required
#   ⑤ shell 态注入启动命令：优先 `bash <SESSION_CONTEXT>/launch.sh`
#      （spawn 的 provider env/wrapper 全在这，METADATA.runtime.command 是
#      launch 包装前的原始命令），否则注入 runtime.command 原文；单行 --enter
#   ⑥ 轮询 terminal read 直到 TUI 标记出现（超时 → manual-required，不静默重试）
#   ⑦ TUI 起来后按 Task-092 基建走 orca-supervised-register.sh（带
#      --reset-failed 复位被翻成 failed 的 Task）重绑 worker-start
#   ⑧ register 成功后把 dispatch_id/dispatch_bind 回写 METADATA supervised 段
#      （与 spawn-worker-launch.sh 同款合同）；terminal_handle 不变
#
# 幂等保证：已恢复（dispatch 绑定 + TUI 在）→ exit 0 零副作用；TUI 已在但
# dispatch 未绑 → 跳过注入只 register 一次；任何失败路径都不 terminal create、
# 不重复 register。
#
# 退出码：0 已恢复/本就健康；2 manual-required（terminal 已死/状态不明/TUI 未
# 起来/register 失败/bind 缺失）；3 manual-required（METADATA 缺路由段/合同破坏）；
# 64 usage。
# stdout 只有 PM 可 grep 的 KV receipt（RECOVER_*），人类可读流程走 stderr。

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=orca-runtime.sh
source "$SCRIPT_DIR/orca-runtime.sh"

WORKTREE=""
SESSION=""
TIMEOUT_SEC=60
POLL_INTERVAL=3
TAIL_LINES=50

usage() {
  cat >&2 <<'USAGE'
Usage:
  recover-unconfigured-worker.sh --worktree PATH --session NAME [options]

  PM 侧恢复一个 spawn 后 agent TUI 未起（agent_unconfigured 家族）的
  supervised worker：重注入启动命令 → 等 TUI → register --reset-failed 重绑。

Required:
  --worktree PATH        Worker worktree 路径
  --session NAME         spawn-worker session id

Optional:
  --timeout SEC          注入后等待 TUI 标记出现的超时（默认 60）
  --poll-interval SEC    TUI 轮询间隔（默认 3；测试可调小）
  --tail-lines N         terminal read 的 tail 行数（默认 50）

Exit codes:
  0   recovered / already-healthy
  2   manual-required（terminal 已死、状态不明、TUI 未起来、register 失败）
  3   manual-required（METADATA 缺 supervised 路由段或合同字段破坏）
  64  usage
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --worktree) WORKTREE="$2"; shift 2 ;;
    --session) SESSION="$2"; shift 2 ;;
    --timeout) TIMEOUT_SEC="$2"; shift 2 ;;
    --poll-interval) POLL_INTERVAL="$2"; shift 2 ;;
    --tail-lines) TAIL_LINES="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: 未知参数: $1" >&2; usage; exit 64 ;;
  esac
done

[ -n "$WORKTREE" ] || { echo "ERROR: --worktree 必填" >&2; exit 64; }
[ -n "$SESSION" ] || { echo "ERROR: --session 必填" >&2; exit 64; }
[[ "$TIMEOUT_SEC" =~ ^[0-9]+$ ]] && [ "$TIMEOUT_SEC" -gt 0 ] || { echo "ERROR: --timeout 须为正整数" >&2; exit 64; }
[[ "$POLL_INTERVAL" =~ ^[0-9]+([.][0-9]+)?$ ]] || { echo "ERROR: --poll-interval 须为数字" >&2; exit 64; }
[[ "$TAIL_LINES" =~ ^[0-9]+$ ]] && [ "$TAIL_LINES" -gt 0 ] || { echo "ERROR: --tail-lines 须为正整数" >&2; exit 64; }
command -v jq >/dev/null 2>&1 || { echo "ERROR: 需要 jq" >&2; exit 64; }

# TUI 强标记：只在 agent TUI 真正渲染后出现，不会出现在注入命令的回显里。
# 覆盖 claude-code（横幅/输入框/token 计数/快捷键提示）与 codex（横幅）家族；
# CodeBuddy/QoderWork 横幅措辞未实证，命中不了会落 unknown → manual-required
# （fail-closed 方向，见 RESULT 误判风险披露）。
TUI_MARKER_RE='claude code|welcome to claude|tokens left|esc to interrupt|for shortcuts|openai codex|✻|╭|╰|▌'
TUI_DETECT_METHOD='terminal-read-tail-heuristic'

SESSION_CONTEXT="$WORKTREE/.claude/agent-sessions/$SESSION"
METADATA="$SESSION_CONTEXT/METADATA.json"

emit_receipt() {
  # $1=status $2=dispatch(可空) ；TERMINAL/TASK 全局已知
  printf 'RECOVER_STATUS=%s\n' "$1"
  printf 'RECOVER_REASON=%s\n' "${RECOVER_REASON:-none}"
  printf 'RECOVER_TERMINAL=%s\n' "${TERMINAL_HANDLE:-}"
  printf 'RECOVER_DISPATCH=%s\n' "${2:-}"
  printf 'RECOVER_TASK=%s\n' "${TASK_ID:-}"
  printf 'RECOVER_TUI_DETECT=%s\n' "$TUI_DETECT_METHOD"
}

manual_required() {
  # $1=exit_code $2=reason $3=manual steps（多行文本）
  # $4=dispatch（可空） $5=稳定 receipt reason code（可空）
  local code="$1" reason="$2" steps="$3" disp="${4:-}"
  RECOVER_REASON="${5:-manual-required}"
  echo "RECOVER manual-required: $reason" >&2
  printf 'RECOVER_MANUAL_STEPS:\n%s\n' "$steps" >&2
  emit_receipt manual-required "$disp"
  exit "$code"
}

# ---------- ① METADATA 合同 ----------

[ -f "$METADATA" ] || {
  manual_required 3 "METADATA 不存在: ${METADATA}（Session Context 被删或路径错误；核对 --worktree/--session）" \
    "人工核对 worktree 与 session 名；若 Session Context 已被清理，该 worker 只能重派。"
}

TERMINAL_HANDLE=$(jq -r '.session.orca.terminal_handle // empty' "$METADATA")
WORKTREE_ID=$(jq -r '.session.orca.worktree_id // empty' "$METADATA")
RUNTIME_COMMAND=$(jq -r '.runtime.command // empty' "$METADATA")
RUN_ID=$(jq -r '.session.orca.supervised.run_id // empty' "$METADATA")
TASK_ID=$(jq -r '.session.orca.supervised.task_id // empty' "$METADATA")
COORDINATOR_HANDLE=$(jq -r '.session.orca.supervised.coordinator_handle // empty' "$METADATA")
PREV_DISPATCH=$(jq -r '.session.orca.supervised.dispatch_id // empty' "$METADATA")

[ -n "$TERMINAL_HANDLE" ] && [ -n "$WORKTREE_ID" ] && [ -n "$RUNTIME_COMMAND" ] || {
  manual_required 3 "METADATA 缺合同字段（terminal_handle/worktree_id/runtime.command 任一为空），spawn 合同破坏，无法自动恢复" \
    "人工核对 ${METADATA}；字段确实缺失时该 session 只能重新 spawn。"
}
[ -n "$RUN_ID" ] && [ -n "$TASK_ID" ] && [ -n "$COORDINATOR_HANDLE" ] || {
  manual_required 3 "METADATA 缺 supervised 路由段（run_id/task_id/coordinator_handle 任一为空），register 无从重绑" \
    "PM 从 Wave receipt 补齐三件套后重跑本命令：jq 写入 .session.orca.supervised.{run_id,task_id,coordinator_handle}；receipt 在 orca-wave-prepare.sh --receipt 输出。"
}

orca_runtime_init

# ---------- ② 幂等门：dispatch 是否已绑 ----------

dispatch_bound_id() {
  local show_out show_id
  show_out=$(orca_cli orchestration dispatch-show --task "$TASK_ID" --json 2>&1) || return 10
  show_id=$(printf '%s' "$show_out" | jq -er '
    if type != "object" or .ok != true or (.result | type) != "object" then
      error("invalid dispatch-show envelope")
    elif (.result.dispatch != null and (.result.dispatch | type) != "object") then
      error("invalid dispatch object")
    elif (.result.dispatchId != null and (.result.dispatchId | type) != "string") then
      error("invalid top-level dispatch id")
    else
      ([.result.dispatch.id?, .result.dispatch.dispatchId?, .result.dispatchId?]
       | map(select(. != null))) as $ids
      | if ($ids | any(.[]; type != "string" or length == 0)) then
          error("invalid dispatch id")
        elif (.result.dispatch != null and ($ids | length) == 0) then
          error("dispatch object omitted its id")
        elif ($ids | unique | length) > 1 then
          error("conflicting dispatch ids")
        elif ($ids | length) == 0 then ""
        else $ids[0]
        end
    end' 2>/dev/null) || return 11
  printf '%s' "$show_id"
}

# ---------- ③/④ 终端读取与 TUI 判定 ----------

read_terminal_tail() {
  # 成功输出 tail 文本（多行）；terminal read 本身失败（rc!=0）返回非零。
  # 合法空 tail 输出空文本；非法 JSON/结构返回 11，绝不折叠成 unknown 继续。
  local out tail_text
  out=$(orca_cli terminal read --terminal "$TERMINAL_HANDLE" --limit "$TAIL_LINES" --json 2>&1) || return 10
  tail_text=$(printf '%s' "$out" | jq -er '
    if type != "object" or .ok != true or (.result | type) != "object" then
      error("invalid terminal-read envelope")
    elif (.result.terminal != null and (.result.terminal | type) != "object") then
      error("invalid terminal object")
    else
      (if ((.result.terminal | type) == "object" and (.result.terminal | has("tail"))) then
         .result.terminal.tail
       elif (.result | has("tail")) then .result.tail
       else null
       end) as $candidate
      | if $candidate == null then []
        elif ($candidate | type) != "array" then error("terminal tail is not an array")
        else $candidate
        end as $tail
      | if ($tail | any(.[]; type != "string")) then error("terminal tail contains non-string values")
        else ($tail | join("\n"))
        end
    end' 2>/dev/null) || return 11
  printf '%s' "$tail_text"
}

detect_tui_state() {
  # stdin=tail 文本；stdout: tui|shell|unknown
  local tail_text last_line
  tail_text=$(cat)
  [ -n "$(printf '%s' "$tail_text" | tr -d '[:space:]')" ] || { echo unknown; return; }
  if printf '%s' "$tail_text" | grep -qiE "$TUI_MARKER_RE"; then
    echo tui
    return
  fi
  last_line=$(printf '%s\n' "$tail_text" | sed '/^[[:space:]]*$/d' | tail -n 1)
  if printf '%s' "$last_line" | grep -qE '[%$>#❯][[:space:]]*$'; then
    echo shell
    return
  fi
  echo unknown
}

if BOUND_DISPATCH=$(dispatch_bound_id); then
  :
else
  dispatch_probe_rc=$?
  if [ "$dispatch_probe_rc" -eq 11 ]; then
    manual_required 2 "dispatch-show 返回非法 JSON/结构，无法证明 Task ${TASK_ID} 是否已绑定；禁止继续读取后注入或 register" \
      "人工步骤：① orca orchestration dispatch-show --task $TASK_ID --json 检查原始响应；② 修复 Orca runtime/版本契约后重跑。本次未执行 terminal send 或 worker-start。" \
      "" "dispatch-probe-invalid"
  fi
  manual_required 2 "dispatch-show 命令失败，无法证明 Task ${TASK_ID} 是否已绑定；禁止把失败折叠成未绑定继续恢复" \
    "人工步骤：① orca orchestration dispatch-show --task $TASK_ID --json 核对 runtime、Task 和权限；② 命令恢复成功后重跑。本次未执行 terminal send 或 worker-start。" \
    "" "dispatch-read-failed"
fi

TAIL_TEXT=""
if TAIL_TEXT=$(read_terminal_tail); then
  :
else
  terminal_probe_rc=$?
  if [ "$terminal_probe_rc" -eq 11 ]; then
    manual_required 2 "terminal read 返回非法 JSON/结构：无法安全判定 terminal ${TERMINAL_HANDLE} 的 TUI 状态" \
      "人工步骤：① orca terminal read --terminal $TERMINAL_HANDLE --limit $TAIL_LINES --json 检查原始响应；② 修复 Orca runtime/版本契约后重跑。本次未执行 terminal send 或 worker-start。" \
      "" "terminal-probe-invalid"
  fi
  # 不可恢复场景之一：terminal 已死/不可读。不重试、不重建，显式交还 PM。
  manual_required 2 "terminal read 失败：terminal $TERMINAL_HANDLE 已死或不可读（Orca runtime 未识别该句柄）" \
    "人工步骤：① orca terminal list --json 核对该句柄是否仍存在；② 已消失则该 terminal 无法复活，改走 spawn-worker.sh 重派或 pm-orchestrate.sh settle 清尾；③ 本脚本绝不自动创建第二个 terminal。" \
    "" "terminal-read-failed"
fi
TUI_STATE=$(printf '%s' "$TAIL_TEXT" | detect_tui_state)
echo "RECOVER: 终端 ${TERMINAL_HANDLE} 读取成功，TUI 判定=${TUI_STATE}（方法=${TUI_DETECT_METHOD}，强标记或裸 shell 提示符特征）" >&2

if [ -n "$BOUND_DISPATCH" ]; then
  if [ "$TUI_STATE" = "tui" ]; then
    echo "RECOVER: dispatch $BOUND_DISPATCH 已绑定且 TUI 特征在——worker 健康，幂等跳过（零副作用）" >&2
    emit_receipt already-healthy "$BOUND_DISPATCH"
    exit 0
  fi
  # dispatch 已绑但终端无 TUI：可能是 agent 退出后 shell 暴露。注入会与既有
  # dispatch 双跑任务，fail-closed 交 PM 裁定（settle 或人工核对）。
  manual_required 2 "dispatch ${BOUND_DISPATCH} 已绑定但终端无 TUI 特征（TUI_STATE=${TUI_STATE}）：盲注入可能与在途 worker 双跑" \
    "人工步骤：① orca orchestration worker-show --dispatch $BOUND_DISPATCH --json 核对 worker 状态；② 已死走 pm-orchestrate.sh settle --worktree <WT> --session <S> --reason '...' 收尾后重派；③ 存活则无需恢复。"
fi

if [ "$TUI_STATE" = "unknown" ]; then
  manual_required 2 "终端 tail 既无 TUI 强标记也无裸 shell 提示符（可能是 trust dialog/空输出/中间态），无法安全判定" \
    "人工步骤：① orca terminal read --terminal $TERMINAL_HANDLE --limit 50 --json 看真实 tail；② 是 CodeBuddy/Qoder trust dialog 则人工答复后重跑本命令；③ 其他中间态稍候重跑；持续 unknown 则人工注入。"
fi

# ---------- ⑤/⑥ 注入 + 等 TUI（仅 shell 态） ----------

if [ "$TUI_STATE" = "shell" ]; then
  LAUNCH_SH="$SESSION_CONTEXT/launch.sh"
  if [ -f "$LAUNCH_SH" ]; then
    INJECT_CMD="bash $LAUNCH_SH"
  else
    INJECT_CMD="$RUNTIME_COMMAND"
  fi
  echo "RECOVER: 裸 shell 确认，注入启动命令（单行）: $INJECT_CMD" >&2
  if ! orca_cli terminal send --terminal "$TERMINAL_HANDLE" --text "$INJECT_CMD" --enter --json >/dev/null 2>&1; then
    manual_required 2 "terminal send 注入失败：terminal $TERMINAL_HANDLE 可读但不可写" \
    "人工步骤：① orca terminal send --terminal $TERMINAL_HANDLE --text \"$INJECT_CMD\" --enter 手工注入；② 成功后重跑本命令完成 register。"
  fi
  echo "RECOVER: 已注入，轮询 TUI 标记（间隔 ${POLL_INTERVAL}s 超时 ${TIMEOUT_SEC}s）" >&2
  deadline=$(( SECONDS + TIMEOUT_SEC ))
  while :; do
    sleep "$POLL_INTERVAL"
    if TAIL_TEXT=$(read_terminal_tail); then
      :
    else
      terminal_probe_rc=$?
      if [ "$terminal_probe_rc" -eq 11 ]; then
        manual_required 2 "等待 TUI 期间 terminal read 返回非法 JSON/结构：停止恢复，不执行 worker-start" \
        "人工步骤：① orca terminal read --terminal $TERMINAL_HANDLE --limit $TAIL_LINES --json 检查原始响应；② 修复响应契约后人工核对已注入进程，再决定重跑或收尾。" \
        "" "terminal-probe-invalid"
      fi
      manual_required 2 "等待 TUI 期间 terminal read 失败：terminal $TERMINAL_HANDLE 在注入后死亡" \
      "人工步骤：① 注入命令可能立即崩溃，orca terminal read 看退出信息；② 核对 $LAUNCH_SH 与 runtime.command 可执行性后人工重试。" \
      "" "terminal-read-failed"
    fi
    TUI_STATE=$(printf '%s' "$TAIL_TEXT" | detect_tui_state)
    if [ "$TUI_STATE" = "tui" ]; then
      echo "RECOVER: TUI 标记已出现（${SECONDS}s 内），进入 register" >&2
      break
    fi
    if [ "$SECONDS" -ge "$deadline" ]; then
      manual_required 2 "启动命令已注入但 TUI 标记 ${TIMEOUT_SEC}s 内未出现（最后判定=${TUI_STATE}）：命令可能启动失败，不静默重试" \
      "人工步骤：① orca terminal read --terminal $TERMINAL_HANDLE --limit 50 --json 查看报错；② 修复后人工注入并跑 orca-supervised-register.sh --worktree-id $WORKTREE_ID --terminal-handle $TERMINAL_HANDLE --run-id $RUN_ID --task-id $TASK_ID --coordinator-handle $COORDINATOR_HANDLE --reset-failed。"
    fi
  done
else
  echo "RECOVER: TUI 已在而 dispatch 未绑（agent_unconfigured 的另一半形态），跳过注入直接 register" >&2
fi

# ---------- ⑦ register 重绑（Task-092 基建，--reset-failed） ----------

REGISTER="$SCRIPT_DIR/orca-supervised-register.sh"
[ -f "$REGISTER" ] || {
  manual_required 2 "orca-supervised-register.sh 缺失: $REGISTER" \
  "人工核对 skill 安装完整性。"
}
echo "RECOVER: register 重绑 task=${TASK_ID} run=${RUN_ID} terminal=${TERMINAL_HANDLE}（--reset-failed）" >&2
if ! REGISTER_OUT=$(bash "$REGISTER" \
    --worktree-id "$WORKTREE_ID" \
    --terminal-handle "$TERMINAL_HANDLE" \
    --run-id "$RUN_ID" \
    --task-id "$TASK_ID" \
    --coordinator-handle "$COORDINATOR_HANDLE" \
    --reset-failed 2>&1); then
  printf 'RECOVER: register 输出:\n%s\n' "$REGISTER_OUT" >&2
  manual_required 2 "register 重绑失败（详见上方输出；coordinator 过期会被 fencing 拒绝）" \
    "人工步骤：① 若报 consumer fencing/coordinator 相关错误，先 orca orchestration run-use --id $RUN_ID --json 重绑当前 PM 终端，把返回的 coordinator_handle 写回 METADATA 后重跑本命令；② 其他错误按 register 输出核对 Task/Run 状态。"
fi
NEW_DISPATCH=$(printf '%s\n' "$REGISTER_OUT" | sed -n 's/^ORCAREG_DISPATCH_ID=//p' | tail -1)
BIND_STATUS=$(printf '%s\n' "$REGISTER_OUT" | sed -n 's/^ORCAREG_DISPATCH_BIND=//p' | tail -1)
[ -n "$BIND_STATUS" ] || BIND_STATUS="ok"
printf 'RECOVER: register 完成 dispatch=%s bind=%s\n' "${NEW_DISPATCH:-none}" "$BIND_STATUS" >&2

# ---------- ⑧ METADATA 路由段回写（与 spawn-worker-launch.sh 同款合同） ----------

tmp_meta=$(mktemp)
if jq --arg disp "$NEW_DISPATCH" --arg bind "$BIND_STATUS" \
    '.session.orca.supervised.dispatch_id = $disp | .session.orca.supervised.dispatch_bind = $bind' \
    "$METADATA" > "$tmp_meta" && mv "$tmp_meta" "$METADATA"; then
  echo "RECOVER: METADATA supervised 路由段已回写 dispatch=${NEW_DISPATCH:-none} bind=${BIND_STATUS}（terminal_handle 不变，未创建新 terminal）" >&2
else
  rm -f "$tmp_meta"
  echo "WARN: METADATA 回写失败（恢复本身已生效，PM 巡检时注意 METADATA dispatch_id 陈旧）" >&2
fi

if [ "$BIND_STATUS" != "ok" ]; then
  manual_required 2 "worker-start 已完成（preamble+TASK 已注入）但 dispatch 绑定缺失（bind=${BIND_STATUS}），worker_done 无通道" \
    "PM 手动三步补绑（runbook #18）：① orca orchestration dispatch --task $TASK_ID --to $TERMINAL_HANDLE --run $RUN_ID --return-preamble（不带 --inject）；② 从 preamble 提取真实 ctx id；③ orca terminal send --terminal $TERMINAL_HANDLE --text '<单行 worker_done 命令形式>' --enter（必须单行）。" \
    "$NEW_DISPATCH"
fi

emit_receipt recovered "$NEW_DISPATCH"
exit 0
