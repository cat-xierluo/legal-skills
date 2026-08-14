#!/usr/bin/env bash
# spawn-worker-launch.sh — shared tmux/Orca worker launch boundary.
# This file is sourced after spawn-worker.sh prepares Session Context and guards.

launch_worker_session() {
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
      chmod +x "$LAUNCH_SH"
    fi
    COMMAND="bash $(printf '%q' "$LAUNCH_SH")"
  fi

  if [ "$ORCA_MODE" = "auto" ]; then
    # v2.1（DEC-114）：ORCA 终端模式。orca terminal create 直接调，保留 ORCA_WORKTREE_ID
    # 之外的 COMMAND / provider env / wrapper / launch.sh 全套不变（COMMAND 已被 launch.sh 包好）。
    # 等价于原 tmux new-session -d -s "$SESSION" -c "$WORKTREE" "$COMMAND"。
    # terminal-managed 投普通占位 prompt；supervised 由 worker-start 注入 live preamble + TASK，
    # 此处只创建并等待 terminal，禁止双重投递。
    orca_terminal_create_and_send "$ORCA_WORKTREE_ID" "$SESSION" "$COMMAND" \
      "请按你的任务开始工作。Session 上下文: .claude/agent-sessions/${SESSION}（详细指令将由 PM 后续 orca terminal send 投递）"
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
        printf 'ORCA_RUN: reuse/create Run %q; coordinator=%q; task=%q; worker-start --terminal <handle> --worktree id:<worktree>\n' \
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
          if reg_out=$(bash "$reg_helper" "${reg_args[@]}" 2>&1); then
            # 从 stdout KV 提取（stderr 是日志，reg_out 含两者，grep stdout KV）
            ORCA_SUPERVISED_RUN_ID=$(printf '%s\n' "$reg_out" | sed -n 's/^ORCAREG_RUN_ID=//p')
            ORCA_SUPERVISED_COORDINATOR_HANDLE=$(printf '%s\n' "$reg_out" | sed -n 's/^ORCAREG_COORDINATOR_HANDLE=//p')
            ORCA_SUPERVISED_TASK_ID=$(printf '%s\n' "$reg_out" | sed -n 's/^ORCAREG_TASK_ID=//p')
            ORCA_SUPERVISED_DISPATCH_ID=$(printf '%s\n' "$reg_out" | sed -n 's/^ORCAREG_DISPATCH_ID=//p')
            if [ -n "$ORCA_SUPERVISED_DISPATCH_ID" ] && [ -f "$METADATA_FILE" ]; then
              tmp_meta=$(mktemp)
              jq --arg run "$ORCA_SUPERVISED_RUN_ID" --arg coordinator "$ORCA_SUPERVISED_COORDINATOR_HANDLE" \
                --arg task "$ORCA_SUPERVISED_TASK_ID" --arg disp "$ORCA_SUPERVISED_DISPATCH_ID" \
                '.session.orca.supervised = {run_id: $run, coordinator_handle: $coordinator, task_id: $task, dispatch_id: $disp, contract: "orca.orchestration.contract.v1", completion_authority: "worker_done", terminal_ownership: "external"}' "$METADATA_FILE" > "$tmp_meta" && mv "$tmp_meta" "$METADATA_FILE"
              echo "SPAWN_WORKER_ORCA_SUPERVISED_DONE: dispatch=$ORCA_SUPERVISED_DISPATCH_ID run=$ORCA_SUPERVISED_RUN_ID task=$ORCA_SUPERVISED_TASK_ID" >&2
            fi
          else
            echo "SPAWN_WORKER_ORCA_SUPERVISED_FAILED: helper 退出非 0；保留 terminal 供 PM 检查，但不冒充 supervised worker" >&2
            echo "$reg_out" >&2
            exit 1
          fi
        fi
      fi
    fi
  else
    run tmux new-session -d -s "$SESSION" -c "$WORKTREE" "$COMMAND"
  fi
}
