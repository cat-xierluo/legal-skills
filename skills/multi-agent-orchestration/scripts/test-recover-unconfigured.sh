#!/usr/bin/env bash
# test-recover-unconfigured.sh — recover-unconfigured-worker.sh 四态 stub 测试。
#
# stub orca CLI（fake-orca）以状态文件驱动，覆盖：
#   态1 正常恢复        裸 shell → 注入 launch.sh → TUI 标记出现 → register 重绑
#   态2 幂等二次调用    已恢复（dispatch 绑定 + TUI 在）→ 零副作用 already-healthy
#   态3 terminal 已死   terminal read 失败 → manual-required，零注入零 register
#   态4 METADATA 缺路由段  supervised 段缺失 → manual-required(exit 3)，零 orca 调用
#   态5 TUI 在但未绑    跳过注入只 register（agent_unconfigured 另一半形态）
#   态6 dispatch 探针坏  命令失败/畸形 JSON → manual-required，零 send/worker-start
#   态7 terminal JSON 坏  terminal read 畸形 JSON → manual-required，零 send/worker-start
#   态8 合法空 tail       保持原 unknown → manual-required 语义，零 send/worker-start
# 全程断言：任何路径都不得 terminal create（恢复不产生第二个 terminal）。
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
RECOVER="$SCRIPT_DIR/recover-unconfigured-worker.sh"
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT

pass=0
fail=0
ok() { echo "  ✓ $1"; pass=$((pass + 1)); }
bad() { echo "  ✗ $1" >&2; fail=$((fail + 1)); }

FAKE="$TMP_ROOT/fake-orca"
export FAKE_ORCA_LOG="$TMP_ROOT/orca.log"
STATE_DIR="$TMP_ROOT/state"
mkdir -p "$STATE_DIR"
: > "$FAKE_ORCA_LOG"

cat > "$FAKE" <<'FAKE'
#!/usr/bin/env bash
set -euo pipefail
{
  for arg in "$@"; do printf '%q ' "$arg"; done
  printf '\n'
} >> "$FAKE_ORCA_LOG"
STATE_DIR="${FAKE_ORCA_STATE_DIR:?}"
case "$1 $2" in
  "terminal read")
    st=$(cat "$STATE_DIR/terminal" 2>/dev/null || echo dead)
    case "$st" in
      dead)
        echo '{"ok":false,"error":{"code":"terminal_not_found","message":"terminal is gone"}}' >&2
        exit 1
        ;;
      shell)
        echo '{"ok":true,"result":{"terminal":{"handle":"term-worker","tail":["Last login: Sun Aug 30 20:05:00 on ttys002","worker@mac skill-agent-unconfigured-recovery %"]}}}'
        ;;
      tui)
        echo '{"ok":true,"result":{"terminal":{"handle":"term-worker","tail":["✻ Welcome to Claude Code!","╭──────────────────────────────────╮","│ > _                               │","  1.2M tokens left"]}}}'
        ;;
      malformed)
        printf '{broken-json\n'
        ;;
      invalid-shape)
        echo '{"ok":true,"result":{"terminal":{"tail":"not-an-array"}}}'
        ;;
      *)
        echo '{"ok":true,"result":{"terminal":{"tail":[]}}}'
        ;;
    esac
    ;;
  "terminal send")
    text=""
    while [ "$#" -gt 0 ]; do
      if [ "$1" = "--text" ]; then text="$2"; break; fi
      shift
    done
    # 注入启动命令（bash launch.sh）→ 模拟 agent 拉起，tail 翻成 TUI。
    case "$text" in
      bash\ *) [ "$(cat "$STATE_DIR/terminal" 2>/dev/null)" = "shell" ] && printf 'tui' > "$STATE_DIR/terminal" ;;
    esac
    echo '{"ok":true,"result":{"terminal":{"handle":"term-worker"}}}'
    ;;
  "orchestration dispatch-show")
    d=""
    if [ -f "$STATE_DIR/dispatch" ]; then
      d=$(cat "$STATE_DIR/dispatch")
    fi
    if [ "$d" = "__command_fail__" ]; then
      echo '{"ok":false,"error":{"code":"runtime_unavailable"}}' >&2
      exit 1
    elif [ "$d" = "__malformed__" ]; then
      printf '{broken-json\n'
    elif [ "$d" = "__invalid_shape__" ]; then
      echo '{"ok":true,"result":{"dispatch":[]}}'
    elif [ -n "$d" ]; then
      printf '{"ok":true,"result":{"dispatch":{"id":"%s"}}}\n' "$d"
    else
      echo '{"ok":true,"result":{}}'
    fi
    ;;
  "orchestration worker-start")
    printf 'ctx-recovered' > "$STATE_DIR/dispatch"
    echo '{"ok":true,"result":{"dispatch":{"id":"ctx-recovered"}}}'
    ;;
  *)
    echo '{"ok":true,"result":{}}'
    ;;
esac
FAKE
chmod +x "$FAKE"
export ORCA_CLI_COMMAND="$FAKE"
export FAKE_ORCA_STATE_DIR="$STATE_DIR"

reset_state() {
  # $1=terminal 态(shell|tui|dead)，$2=dispatch(空串=未绑)
  printf '%s' "$1" > "$STATE_DIR/terminal"
  printf '%s' "${2:-}" > "$STATE_DIR/dispatch"
  : > "$FAKE_ORCA_LOG"
}

make_fixture() {
  # $1=fixture 名；$2=full|no-supervised。输出 fixture 根路径（stdout）。
  local name="$1" variant="$2" wt session
  wt="$TMP_ROOT/wt-$name"
  session="recover-test"
  mkdir -p "$wt/.claude/agent-sessions/$session"
  printf '#!/bin/bash\n# spawn-worker 自动生成 launch 包装\nexec bash -c "claude --session-token-placeholder"\n' \
    > "$wt/.claude/agent-sessions/$session/launch.sh"
  chmod +x "$wt/.claude/agent-sessions/$session/launch.sh"
  local meta
  meta=$(jq -n --arg project "$TMP_ROOT/repo" --arg worktree "$wt" --arg session "$session" \
    '{project:$project,worktree:$worktree,
      session:{id:$session,orca:{worktree_id:"repo::wt-recover",terminal_handle:"term-worker",
        supervised:{run_id:"run-wave",coordinator_handle:"term-pm",task_id:"task-9",dispatch_id:"",dispatch_bind:"manual-required"}}},
      runtime:{command:"claude --model test"}}')
  if [ "$variant" = "no-supervised" ]; then
    meta=$(printf '%s' "$meta" | jq 'del(.session.orca.supervised)')
  fi
  printf '%s\n' "$meta" > "$wt/.claude/agent-sessions/$session/METADATA.json"
  printf '%s' "$wt"
}

run_recover() {
  # $@ 透传；stdout/stderr 合并落盘，rc 记入 RECOVER_RC
  local out
  set +e
  out=$(bash "$RECOVER" "$@" 2>&1)
  RECOVER_RC=$?
  set -e
  RECOVER_OUT="$out"
}

sends_with_launch() { awk '/^terminal send .*launch\.sh/{count++} END{print count+0}' "$FAKE_ORCA_LOG"; }
terminal_send_count() { awk '/^terminal send/{count++} END{print count+0}' "$FAKE_ORCA_LOG"; }
worker_start_count() { awk '/^orchestration worker-start /{count++} END{print count+0}' "$FAKE_ORCA_LOG"; }
create_count() { awk '/^terminal create/{count++} END{print count+0}' "$FAKE_ORCA_LOG"; }

echo "态0: usage 错误 fail-closed"
run_recover --session only-session
[ "$RECOVER_RC" -eq 64 ] && ok "缺 --worktree 退出 64" || bad "缺 --worktree 应退出 64，实得 $RECOVER_RC"

echo ""
echo "态1: 正常恢复（裸 shell → 注入 → TUI → register 重绑）"
WT1=$(make_fixture case1 full)
reset_state shell ""
run_recover --worktree "$WT1" --session recover-test --poll-interval 0.05 --timeout 5
[ "$RECOVER_RC" -eq 0 ] && ok "恢复退出 0" || bad "态1 应退出 0，实得 ${RECOVER_RC}（输出: ${RECOVER_OUT}）"
printf '%s\n' "$RECOVER_OUT" | grep -q '^RECOVER_STATUS=recovered$' && ok "receipt=RECOVER_STATUS=recovered" || bad "态1 receipt 缺 recovered"
[ "$(sends_with_launch)" -eq 1 ] && ok "注入恰好一次 launch.sh 启动命令" || bad "launch.sh 注入次数=$(sends_with_launch)，应为 1"
[ "$(worker_start_count)" -eq 1 ] && ok "register 恰好一次 worker-start" || bad "worker-start 次数=$(worker_start_count)，应为 1"
[ "$(create_count)" -eq 0 ] && ok "全程零 terminal create" || bad "态1 出现 terminal create"
[ "$(jq -r '.session.orca.supervised.dispatch_id' "$WT1/.claude/agent-sessions/recover-test/METADATA.json")" = "ctx-recovered" ] \
  && ok "METADATA dispatch_id 回写 ctx-recovered" || bad "METADATA dispatch_id 未回写"
[ "$(jq -r '.session.orca.supervised.dispatch_bind' "$WT1/.claude/agent-sessions/recover-test/METADATA.json")" = "ok" ] \
  && ok "METADATA dispatch_bind 回写 ok" || bad "METADATA dispatch_bind 未回写"
[ "$(jq -r '.session.orca.terminal_handle' "$WT1/.claude/agent-sessions/recover-test/METADATA.json")" = "term-worker" ] \
  && ok "terminal_handle 保持不变（未产生第二个 terminal）" || bad "terminal_handle 被改写"

echo ""
echo "态2: 幂等二次调用（已恢复 → 零副作用 already-healthy）"
INJECT_BEFORE=$(sends_with_launch)
START_BEFORE=$(worker_start_count)
run_recover --worktree "$WT1" --session recover-test --poll-interval 0.05 --timeout 5
[ "$RECOVER_RC" -eq 0 ] && ok "二次调用退出 0" || bad "态2 应退出 0，实得 $RECOVER_RC"
printf '%s\n' "$RECOVER_OUT" | grep -q '^RECOVER_STATUS=already-healthy$' && ok "receipt=already-healthy" || bad "态2 receipt 缺 already-healthy"
[ "$(sends_with_launch)" -eq "$INJECT_BEFORE" ] && ok "零新增注入" || bad "二次调用重复注入"
[ "$(worker_start_count)" -eq "$START_BEFORE" ] && ok "零新增 register" || bad "二次调用重复 register"
[ "$(create_count)" -eq 0 ] && ok "全程零 terminal create" || bad "态2 出现 terminal create"

echo ""
echo "态3: terminal 已死（manual-required，零注入零 register 零重建）"
WT3=$(make_fixture case3 full)
reset_state dead ""
run_recover --worktree "$WT3" --session recover-test --poll-interval 0.05 --timeout 5
[ "$RECOVER_RC" -eq 2 ] && ok "退出 2（manual-required）" || bad "态3 应退出 2，实得 $RECOVER_RC"
printf '%s\n' "$RECOVER_OUT" | grep -q 'RECOVER manual-required' && ok "显式输出 manual-required" || bad "态3 缺 manual-required 输出"
printf '%s\n' "$RECOVER_OUT" | grep -q 'terminal list' && ok "manual 步骤含人工指引" || bad "态3 缺人工指引"
[ "$(terminal_send_count)" -eq 0 ] && ok "零 terminal send" || bad "态3 不应注入"
[ "$(worker_start_count)" -eq 0 ] && ok "零 register" || bad "态3 不应 register"
[ "$(create_count)" -eq 0 ] && ok "绝不 terminal create" || bad "态3 出现 terminal create"
[ "$(jq -r '.session.orca.supervised.dispatch_id' "$WT3/.claude/agent-sessions/recover-test/METADATA.json")" = "" ] \
  && ok "METADATA 未被误写" || bad "态3 不应回写 dispatch_id"

echo ""
echo "态4: METADATA 缺 supervised 路由段（manual-required，零 orca 调用）"
WT4=$(make_fixture case4 no-supervised)
reset_state shell ""
run_recover --worktree "$WT4" --session recover-test --poll-interval 0.05 --timeout 5
[ "$RECOVER_RC" -eq 3 ] && ok "退出 3（缺路由段专用码）" || bad "态4 应退出 3，实得 $RECOVER_RC"
printf '%s\n' "$RECOVER_OUT" | grep -q 'RECOVER manual-required' && ok "显式输出 manual-required" || bad "态4 缺 manual-required 输出"
printf '%s\n' "$RECOVER_OUT" | grep -q 'Wave receipt' && ok "指引补齐来源（Wave receipt）" || bad "态4 缺补齐指引"
[ "$(wc -l < "$FAKE_ORCA_LOG" | tr -d ' ')" -eq 0 ] && ok "零 orca 调用" || bad "态4 不应产生任何 orca 调用"

echo ""
echo "态5: TUI 已在但 dispatch 未绑（跳过注入，只 register）"
WT5=$(make_fixture case5 full)
reset_state tui ""
run_recover --worktree "$WT5" --session recover-test --poll-interval 0.05 --timeout 5
[ "$RECOVER_RC" -eq 0 ] && ok "恢复退出 0" || bad "态5 应退出 0，实得 ${RECOVER_RC}（输出: ${RECOVER_OUT}）"
printf '%s\n' "$RECOVER_OUT" | grep -q '^RECOVER_STATUS=recovered$' && ok "receipt=recovered" || bad "态5 receipt 缺 recovered"
[ "$(sends_with_launch)" -eq 0 ] && ok "零注入（TUI 已在）" || bad "态5 不应注入，实注入 $(sends_with_launch) 次"
[ "$(worker_start_count)" -eq 1 ] && ok "恰好一次 worker-start 重绑" || bad "态5 worker-start 次数=$(worker_start_count)，应为 1"
[ "$(create_count)" -eq 0 ] && ok "全程零 terminal create" || bad "态5 出现 terminal create"

echo ""
echo "态6: dispatch-show 失败/畸形 JSON（manual-required，零 send 零 worker-start）"
WT6=$(make_fixture case6 full)
for dispatch_fault in __command_fail__ __malformed__ __invalid_shape__; do
  reset_state shell "$dispatch_fault"
  run_recover --worktree "$WT6" --session recover-test --poll-interval 0.05 --timeout 5
  [ "$RECOVER_RC" -eq 2 ] && ok "dispatch fault=${dispatch_fault} 退出 2" || bad "dispatch fault=${dispatch_fault} 应退出 2，实得 $RECOVER_RC"
  if [ "$dispatch_fault" = "__command_fail__" ]; then
    expected_reason="dispatch-read-failed"
  else
    expected_reason="dispatch-probe-invalid"
  fi
  printf '%s\n' "$RECOVER_OUT" | grep -q "^RECOVER_REASON=${expected_reason}$" \
    && ok "receipt 明确 ${expected_reason}" || bad "dispatch fault=${dispatch_fault} receipt reason 错误"
  [ "$(terminal_send_count)" -eq 0 ] && ok "dispatch fault=${dispatch_fault} 零 terminal send" || bad "dispatch fault=${dispatch_fault} 不应 send"
  [ "$(worker_start_count)" -eq 0 ] && ok "dispatch fault=${dispatch_fault} 零 worker-start" || bad "dispatch fault=${dispatch_fault} 不应 worker-start"
done

echo ""
echo "态7: terminal read 畸形 JSON/结构（manual-required，零 send 零 worker-start）"
WT7=$(make_fixture case7 full)
for terminal_fault in malformed invalid-shape; do
  reset_state "$terminal_fault" ""
  run_recover --worktree "$WT7" --session recover-test --poll-interval 0.05 --timeout 5
  [ "$RECOVER_RC" -eq 2 ] && ok "terminal fault=${terminal_fault} 退出 2" || bad "terminal fault=${terminal_fault} 应退出 2，实得 $RECOVER_RC"
  printf '%s\n' "$RECOVER_OUT" | grep -q '^RECOVER_REASON=terminal-probe-invalid$' \
    && ok "terminal fault=${terminal_fault} receipt 明确非法探针" || bad "terminal fault=${terminal_fault} receipt reason 错误"
  [ "$(terminal_send_count)" -eq 0 ] && ok "terminal fault=${terminal_fault} 零 terminal send" || bad "terminal fault=${terminal_fault} 不应 send"
  [ "$(worker_start_count)" -eq 0 ] && ok "terminal fault=${terminal_fault} 零 worker-start" || bad "terminal fault=${terminal_fault} 不应 worker-start"
  [ "$(create_count)" -eq 0 ] && ok "terminal fault=${terminal_fault} 零 terminal create" || bad "terminal fault=${terminal_fault} 不应 create"
done

echo ""
echo "态8: 合法空 tail 保持 unknown/manual-required 原语义"
WT8=$(make_fixture case8 full)
reset_state empty ""
run_recover --worktree "$WT8" --session recover-test --poll-interval 0.05 --timeout 5
[ "$RECOVER_RC" -eq 2 ] && ok "合法空 tail 退出 2" || bad "态8 应退出 2，实得 $RECOVER_RC"
printf '%s\n' "$RECOVER_OUT" | grep -q 'TUI_STATE=unknown\|无法安全判定' \
  && ok "合法空 tail 仍归类 unknown" || bad "态8 未保持 unknown 语义"
[ "$(terminal_send_count)" -eq 0 ] && ok "合法空 tail 零 terminal send" || bad "态8 不应 send"
[ "$(worker_start_count)" -eq 0 ] && ok "合法空 tail 零 worker-start" || bad "态8 不应 worker-start"

echo ""
echo "Result: $pass pass, $fail fail"
[ "$fail" -eq 0 ]
