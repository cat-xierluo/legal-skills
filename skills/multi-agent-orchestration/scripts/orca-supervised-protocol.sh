#!/usr/bin/env bash
# Shared, deterministic Task-spec prefix for Orca supervised workers.

orca_supervised_task_spec() {
  local task_spec="$1"
  printf '%s\n\n%s' \
    'SUPERVISED COMPLETION PROTOCOL (MANDATORY): After the business work and verification finish, execute the exact worker_done command from this attempt’s live Orca preamble using its real task/dispatch IDs, then stop new work. A commit, green tests, STATUS=done, heartbeat, or an idle TUI does not complete the Dispatch; do not invent or reuse IDs.' \
    "$task_spec"
}

# Task-106/Task-107（旧发布别名 Task-076/077-Dispatch）：worker 启动后的 Dispatch 绑定自检与三步自动补绑（register/launch 共用实现）。
#
# 2026-08-27 三波实战（badminton-lab Wave17/18/19）：worker-start 成功拉起 TUI 并注入
# 任务，但 Orca 不识别终端内 agent（agent_unconfigured / no recognized agent 家族）导致
# Dispatch 未绑——Task 停 [ready]、dispatch-show --task 为空、worker_done 无通道。
# 2026-08-28 Wave 20 又暴露第二形态：orca-wave-prepare 预建 Run/Task 后 PM 按 receipt 传
# 三件套但漏 --orca-supervised 时，spawn 走 terminal-managed，worker-start 根本不发生，
# dispatch 同样不绑（Task-107 根因）。两条路径都必须经本函数收尾自检，禁止各自复制
# 一份实现（漂移即回归）。
#
# 输入参数：
#   $1 task_id         已存在的 Orca Task id
#   $2 terminal_handle worker 终端 handle（term_xxx）
#   $3 run_id          Task 所属 Run id（dispatch mutation 需要）
#   $4 start_out       worker-start 的输出（launch 直启路径没有 worker-start 时传空串）
# 依赖：orca_cli（orca-runtime.sh 提供）、jq。
# 输出（全局变量，调用方读取）：
#   ORCAREG_BIND_DISPATCH_ID  绑定成功的 ctx id；自动补绑失败时为空串
#   ORCAREG_BIND_STATUS       ok | manual-required
# 诊断日志全部走 stderr（ORCAREG_ 前缀，与 register 历史输出合同一致）。
# manual-required 不以非零返回阻断调用方：terminal/任务注入已生效，阻断只会制造半活
# worker；由调用方显式告警并输出 SPAWN_WORKER_DISPATCH_BIND 行。
orchestration_dispatch_bind_selfcheck() {
  local task_id="$1"
  local terminal_handle="$2"
  local run_id="$3"
  local start_out="${4:-}"
  local dispatch_bind="ok"
  local dispatch_id=""
  local receipt_id show_out show_id
  receipt_id=$(printf '%s' "$start_out" | jq -r '
    .result.dispatch.id
    // .result.worker.dispatch.id
    // .result.dispatchId
    // .result.worker.dispatchId
    // empty' 2>/dev/null || true)
  # 主动只读核对（旧 runtime 缺 dispatch-show 子命令时容错为空，不阻断）。
  show_out=$(orca_cli orchestration dispatch-show --task "$task_id" --json 2>&1) || show_out=""
  show_id=$(printf '%s' "$show_out" | jq -r '
    .result.dispatch.id
    // .result.dispatch.dispatchId
    // .result.dispatchId
    // empty' 2>/dev/null || true)
  if [ -n "$show_id" ]; then
    dispatch_id="$show_id"
    if [ -n "$receipt_id" ] && [ "$receipt_id" != "$show_id" ]; then
      echo "WARN: worker-start receipt dispatch ($receipt_id) differs from dispatch-show ($show_id); using dispatch-show as canonical" >&2
    fi
  elif [ -n "$receipt_id" ]; then
    dispatch_id="$receipt_id"
    echo "ORCAREG_DISPATCH_SHOW_EMPTY: dispatch-show 未回显 id，按 worker-start mutation receipt 采信: $receipt_id" >&2
  else
    # 绑定缺失：按 runbook #18 自动补绑三步。
    # ① dispatch 无 --inject 建绑定并返回 preamble（agent 不被识别时 --inject 会直接报错）
    # ② 从响应/preamble 提取真实 ctx id ③ 单行 terminal send 注入 worker_done/ask 命令形式
    echo "ORCAREG_DISPATCH_MISSING: worker 启动完成但 dispatch 绑定缺失（receipt 与 dispatch-show 均为空）；执行 runbook #18 三步自动补绑" >&2
    local rebind_out rebind_id rebind_unique verify_out verify_id
    rebind_out=""
    rebind_out=$(orca_cli orchestration dispatch --task "$task_id" --to "$terminal_handle" \
      --run "$run_id" --return-preamble 2>&1) || rebind_out=""
    if [ -n "$rebind_out" ]; then
      printf 'ORCAREG_DISPATCH_REBIND_RECEIPT: %s\n' "$rebind_out" >&2
    fi
    rebind_id=$(printf '%s' "$rebind_out" | jq -r '
      .result.dispatch.id
      // .result.dispatch.dispatchId
      // .result.dispatchId
      // .result.worker.dispatch.id
      // empty' 2>/dev/null || true)
    if [ -z "$rebind_id" ]; then
      # 响应可能不是 JSON（--return-preamble 文本形态）：从 preamble 提取 ctx id；
      # 出现多个不同 ctx id 时视为歧义，宁拒不猜（PM 手动裁定）。
      rebind_id=$(printf '%s' "$rebind_out" | grep -oE 'ctx_[A-Za-z0-9_-]+' | sort -u | sed -n '1p' || true)
      rebind_unique=$(printf '%s' "$rebind_out" | grep -oE 'ctx_[A-Za-z0-9_-]+' | sort -u | wc -l | tr -d ' ' || true)
      if [ "${rebind_unique:-0}" -gt 1 ]; then
        echo "WARN: 补绑响应含 ${rebind_unique} 个不同 ctx id，拒绝猜测" >&2
        rebind_id=""
      fi
    fi
    verify_out=$(orca_cli orchestration dispatch-show --task "$task_id" --json 2>&1) || verify_out=""
    verify_id=$(printf '%s' "$verify_out" | jq -r '
      .result.dispatch.id
      // .result.dispatch.dispatchId
      // .result.dispatchId
      // empty' 2>/dev/null || true)
    if [ -n "$verify_id" ]; then
      dispatch_id="$verify_id"
    elif [ -n "$rebind_id" ]; then
      dispatch_id="$rebind_id"
      echo "ORCAREG_DISPATCH_BIND_BY_RECEIPT: dispatch-show 二次核对仍未回显，按补绑响应采信: $rebind_id" >&2
    else
      dispatch_id=""
    fi
    if [ -n "$dispatch_id" ]; then
      # 第三步：单行注入 worker_done/ask 精确命令形式。
      # 必须单行：多行文本会在 TUI 里被提前回车逐行提交。
      local inject_text
      printf -v inject_text \
        '[dispatch-bind 自动补绑] task_id=%s dispatch_id=%s。完成时精确执行一次: orca orchestration send --from %s --type worker_done --subject "worker 完成" --body "三句内摘要" --task-id %s --dispatch-id %s --outcome succeeded --files-modified "改动文件路径列表"。阻塞时: orca orchestration ask --from %s --question "阻塞问题" --timeout-ms 600000。其余仍按已注入任务执行。' \
        "$task_id" "$dispatch_id" "$terminal_handle" "$task_id" "$dispatch_id" "$terminal_handle"
      if orca_cli terminal send --terminal "$terminal_handle" --text "$inject_text" --enter --json >/dev/null 2>&1; then
        echo "ORCAREG_DISPATCH_INJECTED: 已向 $terminal_handle 单行注入 worker_done/ask 命令形式" >&2
      else
        dispatch_bind="manual-required"
        echo "WARN: dispatch 已补绑($dispatch_id)但命令形式注入失败；PM 需手动单行 terminal send 注入 worker_done 命令形式" >&2
      fi
    else
      dispatch_bind="manual-required"
      echo "WARN: 自动补绑失败（dispatch mutation 无 id 且 dispatch-show 复核为空）。spawn 不阻断，但 worker_done 无通道。PM 手动三步补绑: ① orca orchestration dispatch --task $task_id --to $terminal_handle --run $run_id --return-preamble（不带 --inject，agent 不被识别时 --inject 会直接报错） ② 从返回 preamble 提取真实 ctx id ③ orca terminal send --terminal $terminal_handle --text \"<单行 worker_done/ask 命令形式>\" --enter（必须单行）。" >&2
    fi
  fi
  ORCAREG_BIND_DISPATCH_ID="$dispatch_id"
  ORCAREG_BIND_STATUS="$dispatch_bind"
}
