#!/usr/bin/env bash
# spawn-worker-launch.sh — shared tmux/Orca worker launch boundary.
# This file is sourced after spawn-worker.sh prepares Session Context and guards.

launch_worker_session() {
  DISPATCH_LAUNCH_OUTCOME="planned"
  local minimax_mode="interactive"
  if [ "${WORKER_BACKEND_CANONICAL:-}" = "minimax-code" ]; then
    minimax_mode=$(python3 "$SCRIPT_DIR/minimax-cli-startup.py" --command "$COMMAND" --require-input --supervised "${ORCA_SUPERVISED:-0}" --task-id "${ORCA_TASK_ID:-}") || return 64
    if [ "$minimax_mode" = "batch" ] && { [ "$ORCA_SUPERVISED" -eq 1 ] || [ -n "${ORCA_TASK_ID:-}" ] || [ -n "${ORCA_ZCODE_NATIVE_REQUESTS:-}" ]; }; then
      echo "MINIMAX_BATCH_REQUIRES_TERMINAL_MANAGED: bootstrap cannot receive a second worker-start task" >&2
      return 64
    fi
  fi
  # Launch.sh auto-wrap: COMMAND 含空格时(路径拆词风险,如 qoder BIN
  # /Applications/QoderWork CN.app 含空格),tmux new-session 的 command 解析
  # 会吃掉 %q 反斜杠转义 → env 127(command not found)。
  # 修复(2026-07-05 实测):写 launch.sh(launch.sh 内 `exec bash -c %q` 在 bash
  # 下正确解析转义),tmux 只跑 `bash launch.sh`(无空格),绕过 tmux command 解析。
  # 通用:codebuddy(qoderclicn)/ qoder / 任何含空格路径或特殊字符的 COMMAND 都受益。
  if [[ "$COMMAND" == *' '* ]]; then
    LAUNCH_SH="$WORKTREE/.claude/agent-sessions/$SESSION/launch.sh"
    if [ "$DRY_RUN" -eq 1 ]; then
      printf 'SPAWN_WORKER_DRY_RUN_LAUNCH_SH: path=%q command=%q\n' "$LAUNCH_SH" "$COMMAND"
    else
      mkdir -p "$(dirname "$LAUNCH_SH")"
      printf '#!/bin/bash\n# spawn-worker 自动生成:绕过 tmux command 解析(路径空格/特殊字符)\n# 原始 COMMAND 在 bash -c 下正确解析 %%q 转义(tmux 的 command parser 会吃反斜杠)\nexec bash -c %q\n' "$COMMAND" > "$LAUNCH_SH"
      if [ -n "${BORROW_EXISTING_WORKTREE:-}" ]; then
        # Execute the final borrowed gate inside the frozen bytes, even when the
        # configured Orca bridge is an older installed compatible version.
        local borrowed_helper_sha borrowed_verified_exec
        borrowed_helper_sha=$(python3 -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$SCRIPT_DIR/borrowed-worktree.py") || return 64
        borrowed_verified_exec='import hashlib,os,sys
from pathlib import Path
path,expected=sys.argv[1:3]
try: buffer=Path(path).read_bytes()
except OSError:
 print("BORROWED_HELPER_UNAVAILABLE",file=sys.stderr);raise SystemExit(64)
if hashlib.sha256(buffer).hexdigest()!=expected:
 print("BORROWED_HELPER_CHANGED",file=sys.stderr);raise SystemExit(64)
sys.argv=[path,*sys.argv[3:]]
exec(compile(buffer,path,"exec"),{"__name__":"__main__","__file__":path,"_VERIFIED_FROZEN_LAUNCH_PARENT_PID":os.getppid()})'
        printf -v borrowed_gate 'python3 -c %q %q %q validate --contract %q --project %q --worktree %q --branch %q --session %q --owner-pid %q --orca-bin %q' \
          "$borrowed_verified_exec" "$SCRIPT_DIR/borrowed-worktree.py" "$borrowed_helper_sha" "$BORROW_EXISTING_WORKTREE" "$PROJECT_DIR" "$WORKTREE" "$BRANCH" "$SESSION" "$$" "$ORCA_CLI_BIN"
        printf '#!/bin/bash\n# borrowed-helper-sha256: %s\n%s --terminal "${ORCA_TERMINAL_HANDLE:?}" >/dev/null || exit 64\nexec bash -c %q\n' "$borrowed_helper_sha" "$borrowed_gate" "$COMMAND" > "$LAUNCH_SH"
      fi
      chmod +x "$LAUNCH_SH"
      [ -z "${ORCA_ZCODE_NATIVE_REQUESTS:-}" ] || chmod 700 "$LAUNCH_SH"
    fi
    COMMAND="bash $(printf '%q' "$LAUNCH_SH")"
  fi

  if [ "$ORCA_MODE" = "auto" ]; then
    # Repeat immediately before terminal creation: preparation may take time.
    if [ -n "${ORCA_EXPECTED_RUNTIME_ID:-}" ]; then
      orca_runtime_require_identity "$ORCA_EXPECTED_RUNTIME_ID" || exit $?
    fi
    if [ -n "${ORCA_ZCODE_NATIVE_REQUESTS:-}" ]; then
      if [ "$DRY_RUN" -eq 1 ]; then
        echo "SPAWN_WORKER_DRY_RUN_NATIVE_ZCODE: worker-start --agent zcode; one frozen launch request; native unique task injection"
        return
      fi
      if declare -F spawn_worker_borrowed_recheck >/dev/null; then spawn_worker_borrowed_recheck; fi
      reg_args=(--agent zcode --worktree-id "$ORCA_WORKTREE_ID"
        --metadata-file "$METADATA_FILE" --launch-request-root "$ORCA_ZCODE_NATIVE_REQUESTS"
        --task-spec "$TASK_SPEC" --task-title "${TASK_TITLE:-spawn-worker $SESSION}"
        --authority-receipt "$AUTHORITY_RECEIPT_FILE")
      [ -z "${ORCA_RUN_ID:-}" ] || reg_args+=(--run-id "$ORCA_RUN_ID")
      [ -z "${ORCA_TASK_ID:-}" ] || reg_args+=(--task-id "$ORCA_TASK_ID")
      [ -z "${ORCA_COORDINATOR_HANDLE:-}" ] || reg_args+=(--coordinator-handle "$ORCA_COORDINATOR_HANDLE")
      [ -z "${ORCA_EXPECTED_RUNTIME_ID:-}" ] || reg_args+=(--runtime-id "$ORCA_EXPECTED_RUNTIME_ID")
      if ! reg_out=$(bash "$SCRIPT_DIR/orca-supervised-register.sh" "${reg_args[@]}"); then
        echo "SPAWN_WORKER_NATIVE_ZCODE_FAILED: inspect the exact request/receipt/residualResources; no automatic retry" >&2
        exit 1
      fi
      # Reject duplicate or malformed output fields; never infer an arbitrary handle.
      ORCA_TERMINAL_HANDLE=$(printf '%s\n' "$reg_out" | python3 -c '
import re,sys
lines=[x[len("ORCAREG_TERMINAL_HANDLE="):] for x in sys.stdin.read().splitlines() if x.startswith("ORCAREG_TERMINAL_HANDLE=")]
if len(lines)!=1 or not re.fullmatch(r"[A-Za-z0-9_.:-]+",lines[0]): raise SystemExit(64)
print(lines[0])') || exit 64
      ORCA_SUPERVISED_RUN_ID=$(printf '%s\n' "$reg_out" | sed -n 's/^ORCAREG_RUN_ID=//p')
      ORCA_SUPERVISED_TASK_ID=$(printf '%s\n' "$reg_out" | sed -n 's/^ORCAREG_TASK_ID=//p')
      ORCA_SUPERVISED_DISPATCH_ID=$(printf '%s\n' "$reg_out" | sed -n 's/^ORCAREG_DISPATCH_ID=//p')
      ORCA_SUPERVISED_DISPATCH_BIND=$(printf '%s\n' "$reg_out" | sed -n 's/^ORCAREG_DISPATCH_BIND=//p')
      ORCA_SUPERVISED_COORDINATOR_HANDLE=$(printf '%s\n' "$reg_out" | sed -n 's/^ORCAREG_COORDINATOR_HANDLE=//p')
      DISPATCH_LAUNCH_OUTCOME="supervised_registration_returned"
      echo "SPAWN_WORKER_ORCA_NATIVE_ZCODE_DONE: terminal=$ORCA_TERMINAL_HANDLE dispatch=$ORCA_SUPERVISED_DISPATCH_ID bind=$ORCA_SUPERVISED_DISPATCH_BIND" >&2
      return
    fi
    # Task-077 前置校验（terminal 副作用前 fail-closed）：PM 按 Wave receipt 传了
    # --orca-task-id 但漏 --orca-supervised 时，下方 self-check 分支会接手 dispatch 绑定，
    # 它需要 --orca-run-id（dispatch mutation 的 --run 参数）。残缺组合在创建 terminal
    # 之前报错，避免留下无 dispatch 通道的半活 worker。
    if [ "$ORCA_SUPERVISED" -ne 1 ] && [ -n "$ORCA_TASK_ID" ] && [ -z "$ORCA_RUN_ID" ]; then
      echo "ERROR: --orca-task-id without --orca-supervised requires --orca-run-id (dispatch bind self-check needs the Run; see Task-077 launch-path self-check)" >&2
      exit 64
    fi
    # v2.1（DEC-114）：ORCA 终端模式。orca terminal create 直接调，保留 ORCA_WORKTREE_ID
    # 之外的 COMMAND / provider env / wrapper / launch.sh 全套不变（COMMAND 已被 launch.sh 包好）。
    # 等价于原 tmux new-session -d -s "$SESSION" -c "$WORKTREE" "$COMMAND"。
    # terminal-managed 投普通占位 prompt；supervised 由 worker-start 注入 live preamble + TASK，
    # 此处只创建并等待 terminal，禁止双重投递。
    orca_terminal_create_and_send "$ORCA_WORKTREE_ID" "$SESSION" "$COMMAND" \
      "请按你的任务开始工作。Session 上下文: .claude/agent-sessions/${SESSION}（详细指令将由 PM 后续 orca terminal send 投递）" "$minimax_mode" || return $?
    if [ "$DRY_RUN" -eq 0 ]; then
      DISPATCH_LAUNCH_OUTCOME="terminal_created"
      [ "$minimax_mode" != "batch" ] || DISPATCH_LAUNCH_OUTCOME="batch_launch_returned"
    fi
    # v2.1（DEC-114）：orca_terminal_create_and_send 在 write_metadata 之后跑（设 ORCA_TERMINAL_HANDLE），
    # 补 patch METADATA 的 session.orca.terminal_handle，让 PM 巡检 METADATA 能拿到 handle。
    if [ "$DRY_RUN" -eq 0 ] && [ -n "$ORCA_TERMINAL_HANDLE" ] && [ -f "$METADATA_FILE" ]; then
      tmp_meta=$(mktemp)
      jq --arg handle "$ORCA_TERMINAL_HANDLE" '.session.orca.terminal_handle = $handle' "$METADATA_FILE" > "$tmp_meta" && mv "$tmp_meta" "$METADATA_FILE"
    fi

    # v2.1.1（Task-033）：--orca-supervised 时把 worker terminal 纳入 ORCA supervised 体系。
    # 前提：ORCA 模式 auto + terminal 跑 recognized agent（COMMAND 是 claude/codex 等）。
    # 调 orca-supervised-register.sh（run-create + task-create + worker-start --terminal），
    # 拿 run_id/task_id/dispatch_id patch 进 METADATA。失败时 fail-loud：terminal 保留供精确恢复，
    # 但调用方不能把它误当成已编排 worker。
    if [ "$ORCA_SUPERVISED" -eq 1 ] && [ -n "$ORCA_TERMINAL_HANDLE" ]; then
      if [ "$DRY_RUN" -eq 1 ]; then
        printf 'ORCA_RUN: reuse/create Run %q; coordinator=%q; task=%q; worker-start --terminal <handle> --worktree id:<worktree>; dispatch-bind self-check (Task-076: dispatch-show 核对, 为空时 runbook #18 三步自动补绑)\n' \
          "${ORCA_RUN_ID:-new-wave-run}" "${ORCA_COORDINATOR_HANDLE:-bind-once}" "${ORCA_TASK_ID:-create-from-spec:$TASK_SPEC}"
      else
        reg_helper="$SCRIPT_DIR/orca-supervised-register.sh"
        if [ ! -f "$reg_helper" ]; then
          echo "ERROR: supervised helper missing: $reg_helper" >&2
          exit 1
        else
          echo "SPAWN_WORKER_ORCA_SUPERVISED: registering (worktree=$ORCA_WORKTREE_ID terminal=$ORCA_TERMINAL_HANDLE)" >&2
          reg_args=(
            --worktree-id "$ORCA_WORKTREE_ID"
            --terminal-handle "$ORCA_TERMINAL_HANDLE"
            --task-spec "$TASK_SPEC"
            --task-title "${TASK_TITLE:-spawn-worker $SESSION}"
            --authority-receipt "${AUTHORITY_RECEIPT_FILE:-}"
          )
          if [ -n "$ORCA_RUN_ID" ]; then
            reg_args+=(--run-id "$ORCA_RUN_ID")
          fi
          if [ -n "$ORCA_TASK_ID" ]; then
            reg_args+=(--task-id "$ORCA_TASK_ID")
          fi
          if [ -n "$ORCA_COORDINATOR_HANDLE" ]; then
            reg_args+=(--coordinator-handle "$ORCA_COORDINATOR_HANDLE")
          fi
          if [ -n "${ORCA_EXPECTED_RUNTIME_ID:-}" ]; then
            reg_args+=(--runtime-id "$ORCA_EXPECTED_RUNTIME_ID")
          fi
          if reg_out=$(bash "$reg_helper" "${reg_args[@]}" 2>&1); then
            DISPATCH_LAUNCH_OUTCOME="supervised_registration_returned"
            # 从 stdout KV 提取（stderr 是日志，reg_out 含两者，grep stdout KV）
            ORCA_SUPERVISED_RUN_ID=$(printf '%s\n' "$reg_out" | sed -n 's/^ORCAREG_RUN_ID=//p')
            ORCA_SUPERVISED_COORDINATOR_HANDLE=$(printf '%s\n' "$reg_out" | sed -n 's/^ORCAREG_COORDINATOR_HANDLE=//p')
            ORCA_SUPERVISED_TASK_ID=$(printf '%s\n' "$reg_out" | sed -n 's/^ORCAREG_TASK_ID=//p')
            ORCA_SUPERVISED_DISPATCH_ID=$(printf '%s\n' "$reg_out" | sed -n 's/^ORCAREG_DISPATCH_ID=//p')
            # Task-076：dispatch 绑定自检结果（旧版 helper 无此 KV 时回退 ok，向后兼容）。
            ORCA_SUPERVISED_DISPATCH_BIND=$(printf '%s\n' "$reg_out" | sed -n 's/^ORCAREG_DISPATCH_BIND=//p')
            [ -n "$ORCA_SUPERVISED_DISPATCH_BIND" ] || ORCA_SUPERVISED_DISPATCH_BIND="ok"
            printf 'SPAWN_WORKER_DISPATCH_BIND: %s\n' "$ORCA_SUPERVISED_DISPATCH_BIND" >&2
            if [ "$ORCA_SUPERVISED_DISPATCH_BIND" != "ok" ]; then
              # 不阻断 spawn（terminal/任务注入已生效），但显式告警代替静默缺失。
              echo "WARN: dispatch 绑定自动补绑未完成(manual-required)：worker 已启动且任务已注入，但 worker_done 无通道。PM 按 runbook #18 三步手动补绑：① orca orchestration dispatch --task $ORCA_SUPERVISED_TASK_ID --to $ORCA_TERMINAL_HANDLE --run $ORCA_SUPERVISED_RUN_ID --return-preamble（不带 --inject）② 从 preamble 提取真实 ctx id ③ 单行 terminal send 注入 worker_done/ask 命令形式（必须单行）" >&2
            fi
            # dispatch_id 在 manual-required 时可为空：仍写入 supervised 块（run/task/coordinator
            # 是 PM 手动补绑的输入），pm-orchestrate 对空 dispatch_id 自动按 terminal-managed 路由。
            if [ -f "$METADATA_FILE" ]; then
              tmp_meta=$(mktemp)
              jq --arg run "$ORCA_SUPERVISED_RUN_ID" --arg coordinator "$ORCA_SUPERVISED_COORDINATOR_HANDLE" \
                --arg task "$ORCA_SUPERVISED_TASK_ID" --arg disp "$ORCA_SUPERVISED_DISPATCH_ID" \
                --arg bind "$ORCA_SUPERVISED_DISPATCH_BIND" \
                '.session.orca.supervised = {run_id: $run, coordinator_handle: $coordinator, task_id: $task, dispatch_id: $disp, dispatch_bind: $bind, contract: "orca.orchestration.contract.v1", completion_authority: "worker_done", terminal_ownership: "external"}' "$METADATA_FILE" > "$tmp_meta" && mv "$tmp_meta" "$METADATA_FILE"
              echo "SPAWN_WORKER_ORCA_SUPERVISED_DONE: dispatch=${ORCA_SUPERVISED_DISPATCH_ID:-none} run=$ORCA_SUPERVISED_RUN_ID task=$ORCA_SUPERVISED_TASK_ID bind=$ORCA_SUPERVISED_DISPATCH_BIND" >&2
            fi
          else
            echo "SPAWN_WORKER_ORCA_SUPERVISED_FAILED: helper 退出非 0；保留 terminal 供 PM 检查，但不冒充 supervised worker" >&2
            echo "$reg_out" >&2
            exit 1
          fi
        fi
      fi
    fi

    # Task-077：Wave receipt 派单漏 --orca-supervised 的 dispatch 绑定自检。
    # 2026-08-28 Wave 20 双 worker 实测：orca-wave-prepare 预建 Run/Task 后，PM 按 receipt
    # 传 --orca-run-id/--orca-task-id 但漏 --orca-supervised 时，这些旗标被静默忽略，
    # spawn 走 terminal-managed——Task 停 [ready]、dispatch-show 为空、DISPATCH_BIND 行
    # 不打印，PM 只能手动三步补绑。本分支在 terminal 启动完成后，对已传入的
    # --orca-task-id 执行与 register 路径完全相同的 dispatch-show 自检 + 三步自动补绑
    # （共用 orchestration_dispatch_bind_selfcheck，勿双份漂移），输出同款
    # SPAWN_WORKER_DISPATCH_BIND: ok|manual-required。纯 terminal-managed（无 --orca-task-id）
    # 不涉及 dispatch，保持零变化。
    if [ "$ORCA_SUPERVISED" -ne 1 ] && [ -n "$ORCA_TERMINAL_HANDLE" ] && [ -n "$ORCA_TASK_ID" ]; then
      if [ "$DRY_RUN" -eq 1 ]; then
        printf 'ORCA_RUN: dispatch-bind self-check for pre-created task %q (Task-077: dispatch-show 核对, 为空时 runbook #18 三步自动补绑)\n' \
          "$ORCA_TASK_ID"
      else
        # 函数库按调用时点 source（真链路由 spawn-worker.sh 提供 SCRIPT_DIR；测试直接
        # source 本文件时 SCRIPT_DIR 由用例设置）。纯函数定义，幂等无副作用。
        # shellcheck source=orca-supervised-protocol.sh
        source "$SCRIPT_DIR/orca-supervised-protocol.sh"
        orchestration_dispatch_bind_selfcheck "$ORCA_TASK_ID" "$ORCA_TERMINAL_HANDLE" "$ORCA_RUN_ID" ""
        ORCA_SUPERVISED_RUN_ID="$ORCA_RUN_ID"
        ORCA_SUPERVISED_COORDINATOR_HANDLE="${ORCA_COORDINATOR_HANDLE:-}"
        ORCA_SUPERVISED_TASK_ID="$ORCA_TASK_ID"
        ORCA_SUPERVISED_DISPATCH_ID="$ORCAREG_BIND_DISPATCH_ID"
        ORCA_SUPERVISED_DISPATCH_BIND="$ORCAREG_BIND_STATUS"
        printf 'SPAWN_WORKER_DISPATCH_BIND: %s\n' "$ORCA_SUPERVISED_DISPATCH_BIND" >&2
        if [ "$ORCA_SUPERVISED_DISPATCH_BIND" != "ok" ]; then
          # 与 supervised 分支同款告警：不阻断 spawn（terminal 已启动），显式告警代替静默缺失。
          echo "WARN: dispatch 绑定自动补绑未完成(manual-required)：worker 已启动，但 worker_done 无通道。PM 按 runbook #18 三步手动补绑：① orca orchestration dispatch --task $ORCA_SUPERVISED_TASK_ID --to $ORCA_TERMINAL_HANDLE --run $ORCA_SUPERVISED_RUN_ID --return-preamble（不带 --inject）② 从 preamble 提取真实 ctx id ③ 单行 terminal send 注入 worker_done/ask 命令形式（必须单行）" >&2
        fi
        if [ "$ORCA_SUPERVISED_DISPATCH_BIND" = "ok" ]; then
          orchestration_completion_authority_write \
            "$ORCA_SUPERVISED_TASK_ID" "$ORCA_SUPERVISED_DISPATCH_ID" \
            "$ORCA_TERMINAL_HANDLE" "$ORCA_SUPERVISED_RUN_ID" "$METADATA_FILE" "${AUTHORITY_RECEIPT_FILE:-}" || {
              echo "ERROR: pre-created Task bound, but completion authority receipt could not be created" >&2
              exit 1
            }
        fi
        # METADATA 补 supervised 块（run/task/coordinator/dispatch/bind）：与 supervised
        # 分支同款合同；空 dispatch_id 下 pm-orchestrate 自动按 terminal-managed 路由。
        if [ -f "$METADATA_FILE" ]; then
          tmp_meta=$(mktemp)
          jq --arg run "$ORCA_SUPERVISED_RUN_ID" --arg coordinator "$ORCA_SUPERVISED_COORDINATOR_HANDLE" \
            --arg task "$ORCA_SUPERVISED_TASK_ID" --arg disp "$ORCA_SUPERVISED_DISPATCH_ID" \
            --arg bind "$ORCA_SUPERVISED_DISPATCH_BIND" \
            --arg completion_file "${ORCAREG_COMPLETION_AUTHORITY_FILE:-}" \
            --arg completion_sha "${ORCAREG_COMPLETION_AUTHORITY_SHA256:-}" \
            '.session.orca.supervised = {run_id: $run, coordinator_handle: $coordinator, task_id: $task, dispatch_id: $disp, dispatch_bind: $bind, contract: "orca.orchestration.contract.v1", completion_authority: "worker_done", terminal_ownership: "external"}
             | if $completion_file != "" then
                 .execution_authority.completion_authority_file = $completion_file
                 | .execution_authority.completion_authority_sha256 = $completion_sha
               else . end' "$METADATA_FILE" > "$tmp_meta" && mv "$tmp_meta" "$METADATA_FILE"
          echo "SPAWN_WORKER_ORCA_PRECREATED_TASK_BOUND: dispatch=${ORCA_SUPERVISED_DISPATCH_ID:-none} run=$ORCA_SUPERVISED_RUN_ID task=$ORCA_SUPERVISED_TASK_ID bind=$ORCA_SUPERVISED_DISPATCH_BIND" >&2
        fi
      fi
    fi
  else
    run tmux new-session -d -s "$SESSION" -c "$WORKTREE" "$COMMAND"
    if [ "$DRY_RUN" -eq 0 ]; then
      DISPATCH_LAUNCH_OUTCOME="terminal_created"
      [ "$minimax_mode" != "batch" ] || DISPATCH_LAUNCH_OUTCOME="batch_launch_returned"
    fi
  fi
}
