#!/usr/bin/env bash
# Shared, deterministic Task-spec prefix for Orca supervised workers.

orca_supervised_task_spec() {
  local task_spec="$1"
  printf '%s\n\n%s' \
    'SUPERVISED COMPLETION PROTOCOL (MANDATORY): After the business work and verification finish, execute the exact worker_done command from this attempt’s live Orca preamble using its real task/dispatch IDs, then stop new work. A commit, green tests, STATUS=done, heartbeat, or an idle TUI does not complete the Dispatch; do not invent or reuse IDs.' \
    "$task_spec"
}

# Bind the post-worker-start Dispatch identity into the worker's already-running
# hook without persisting the raw dispatch capability. The stable path is known
# before launch and injected into the worker environment; only this hash-bound
# receipt is created after Orca has minted the Dispatch capability.
orchestration_completion_authority_write() {
  local task_id="$1"
  local dispatch_id="$2"
  local terminal_handle="$3"
  local run_id="$4"
  local metadata_file="$5"
  local expected_authority_file="${6:-}"
  local authority_file completion_file show_out
  local actual_task actual_dispatch actual_terminal actual_run capability_hash process_incarnation runtime_id authority_sha
  local created_at receipt_tmp receipt_sha

  ORCAREG_COMPLETION_AUTHORITY_FILE=""
  ORCAREG_COMPLETION_AUTHORITY_SHA256=""

  [ -n "$dispatch_id" ] || {
    echo "ERROR: completion authority requires a bound dispatch" >&2
    return 1
  }
  [ -f "$metadata_file" ] && [ ! -L "$metadata_file" ] || {
    echo "ERROR: completion authority metadata is missing or symlinked: $metadata_file" >&2
    return 1
  }
  authority_file=$(jq -er '.execution_authority.authority_receipt_file | select(type == "string" and length > 0)' \
    "$metadata_file" 2>/dev/null) || {
    echo "ERROR: metadata lacks the PM authority receipt path; completion transport stays closed" >&2
    return 1
  }
  [ -n "$expected_authority_file" ] && [ "$authority_file" = "$expected_authority_file" ] || {
    echo "ERROR: metadata authority path differs from the PM launch binding" >&2
    return 1
  }
  [ -f "$authority_file" ] && [ ! -L "$authority_file" ] || {
    echo "ERROR: PM authority receipt is missing or symlinked: $authority_file" >&2
    return 1
  }
  completion_file="${authority_file%.json}.completion.json"
  [ "$completion_file" != "$authority_file" ] || completion_file="${authority_file}.completion.json"
  authority_sha=$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); from completion_authority import load_authority; print(load_authority(sys.argv[2])[1])' \
    "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" "$authority_file") || return 1

  show_out=$(orca_cli orchestration dispatch-show --task "$task_id" --json 2>&1) || {
    echo "ERROR: dispatch-show failed while binding completion authority" >&2
    return 1
  }
  printf '%s' "$show_out" | jq -e '.ok == true' >/dev/null 2>&1 || return 1
  runtime_id=$(printf '%s' "$show_out" | jq -er '._meta.runtimeId | select(type == "string" and length > 0)' 2>/dev/null) || return 1
  actual_task=$(printf '%s' "$show_out" | jq -er '.result.dispatch.task_id | select(type == "string" and length > 0)' 2>/dev/null) || return 1
  actual_dispatch=$(printf '%s' "$show_out" | jq -er '.result.dispatch.id | select(type == "string" and length > 0)' 2>/dev/null) || return 1
  actual_terminal=$(printf '%s' "$show_out" | jq -er '.result.dispatch.assignee_handle | select(type == "string" and length > 0)' 2>/dev/null) || return 1
  actual_run=$(printf '%s' "$show_out" | jq -er '.result.dispatch.run_id | select(type == "string" and length > 0)' 2>/dev/null) || return 1
  capability_hash=$(printf '%s' "$show_out" | jq -er '.result.dispatch.capability_hash | select(type == "string" and test("^[0-9a-f]{64}$"))' 2>/dev/null) || return 1
  process_incarnation=$(printf '%s' "$show_out" | jq -er '.result.dispatch.process_incarnation | select(type == "string" and length > 0)' 2>/dev/null) || return 1
  if [ "$actual_task" != "$task_id" ] || [ "$actual_dispatch" != "$dispatch_id" ] || \
     [ "$actual_terminal" != "$terminal_handle" ] || [ "$actual_run" != "$run_id" ]; then
    echo "ERROR: dispatch identity drift while binding completion authority" >&2
    return 1
  fi

  mkdir -p "$(dirname "$completion_file")"
  created_at=$(date -u "+%Y-%m-%dT%H:%M:%SZ")
  receipt_tmp=$(mktemp "${completion_file}.tmp.XXXXXX") || return 1
  umask 077
  jq -n \
    --arg schema "multi-agent-orchestration.completion-authority.v1" \
    --arg created_at "$created_at" \
    --arg task "$task_id" \
    --arg dispatch "$dispatch_id" \
    --arg terminal "$terminal_handle" \
    --arg run "$run_id" \
    --arg capability_hash "$capability_hash" \
    --arg process_incarnation "$process_incarnation" \
    --arg runtime_id "$runtime_id" \
    --arg authority_receipt_file "$authority_file" \
    --arg authority_receipt_sha256 "$authority_sha" \
    '{schema:$schema,created_at:$created_at,state:"active",task_id:$task,dispatch_id:$dispatch,
      terminal_handle:$terminal,run_id:$run,capability_hash:$capability_hash,
      process_incarnation:$process_incarnation,runtime_id:$runtime_id,
      authority_receipt_file:$authority_receipt_file,authority_receipt_sha256:$authority_receipt_sha256}' \
    > "$receipt_tmp" || { rm -f "$receipt_tmp"; return 1; }
  chmod 600 "$receipt_tmp"
  if [ -e "$completion_file" ]; then
    if [ -L "$completion_file" ] || [ ! -f "$completion_file" ]; then
      rm -f "$receipt_tmp"
      echo "ERROR: existing completion authority is not a regular file" >&2
      return 1
    fi
    if jq -e --arg task "$task_id" --arg dispatch "$dispatch_id" --arg terminal "$terminal_handle" \
      --arg run "$run_id" --arg capability_hash "$capability_hash" --arg process "$process_incarnation" \
      --arg runtime "$runtime_id" --arg authority "$authority_file" --arg authority_sha "$authority_sha" \
      '.schema == "multi-agent-orchestration.completion-authority.v1" and .state == "active"
       and .task_id == $task and .dispatch_id == $dispatch and .terminal_handle == $terminal
       and .run_id == $run and .capability_hash == $capability_hash and .process_incarnation == $process
       and .runtime_id == $runtime and .authority_receipt_file == $authority and .authority_receipt_sha256 == $authority_sha' \
      "$completion_file" >/dev/null 2>&1; then
      rm -f "$receipt_tmp"
    else
      rm -f "$receipt_tmp"
      echo "ERROR: completion authority already exists with a different Dispatch identity" >&2
      return 1
    fi
  elif ! ln "$receipt_tmp" "$completion_file" 2>/dev/null; then
    rm -f "$receipt_tmp"
    echo "ERROR: could not atomically create completion authority receipt" >&2
    return 1
  else
    rm -f "$receipt_tmp"
  fi

  receipt_sha=$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$completion_file")
  ORCAREG_COMPLETION_AUTHORITY_FILE="$completion_file"
  ORCAREG_COMPLETION_AUTHORITY_SHA256="$receipt_sha"
  echo "ORCAREG_COMPLETION_AUTHORITY: $completion_file sha256=$receipt_sha" >&2
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
      printf 'ORCAREG_DISPATCH_REBIND_RECEIPT: sha256=%s (capability text redacted)\n' \
        "$(printf '%s' "$rebind_out" | python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())')" >&2
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
      local inject_text completion_command
      completion_command=$(printf '%s' "$rebind_out" | python3 -c '
import json, re, sys
raw = sys.stdin.read()
texts = [raw]
try:
    data = json.loads(raw)
    texts = []
    def walk(value):
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, dict):
            for item in value.values(): walk(item)
        elif isinstance(value, list):
            for item in value: walk(item)
    walk(data)
except json.JSONDecodeError:
    pass
for text in texts:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if "orca orchestration send" not in line:
            continue
        parts = [line.strip()]
        while parts[-1].endswith("\\") and index + len(parts) < len(lines):
            parts.append(lines[index + len(parts)].strip())
        command = re.sub(r"\\\s*$", "", parts[0])
        for part in parts[1:]:
            command += " " + re.sub(r"\\\s*$", "", part)
        if "--type worker_done" in command and "--dispatch-capability" in command:
            print(command)
            raise SystemExit(0)
raise SystemExit(1)
' 2>/dev/null) || completion_command=""
      if [ -z "$completion_command" ]; then
        dispatch_bind="manual-required"
        echo "WARN: dispatch 已补绑($dispatch_id)但未能从 live preamble 提取原生 worker_done；拒绝注入无 capability 的伪命令" >&2
        ORCAREG_BIND_DISPATCH_ID="$dispatch_id"
        ORCAREG_BIND_STATUS="$dispatch_bind"
        return 0
      fi
      printf -v inject_text \
        '[dispatch-bind 自动补绑] task_id=%s dispatch_id=%s。完成时原样执行且只执行一次以下命令（首次权限拒绝后立即停止，不得改写或包装）: %s。其余仍按已注入任务执行。' \
        "$task_id" "$dispatch_id" "$completion_command"
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
