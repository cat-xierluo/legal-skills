#!/usr/bin/env bash
# reauthorize 对 dispatched(等待中) worker 的原地重授权支持（Task-081）。
#
# 背景：2026-08-30 FaroPDF 编排实测——worker 卡 escalation 等待（task 仍 dispatched）
# 时跑 reauthorize，worker-start 被 TASK_REUSED 拒绝后直接 exit 2，而新 terminal 已在
# Step 3 创建，旧 terminal 又未关闭 → 双活终端泄漏。
#
# 矩阵（每例独立 fixture）：
#   A. dispatched + 未消费 escalation 消息：先 reply 消费等待，随后走完整链；
#      worker-start 仍被 TASK_REUSED 拒绝（单活 fencing）→ 回滚新终端 + runbook #18
#      manual-recovery 指引，旧终端保留，METADATA 不变
#   B. dispatched 无消息：跳过消费，其余同 A
#   C. failed：既有路径零变化（复位 ready + 重试 + 换终端 + 关旧）
#   D. blocked：同 C
#   E. completed：走既有 task_not_startable 通用路径成功
#   F. 重复调用幂等：成功链与 dispatched 回滚链各连跑两次，活终端数不增长
#   G. terminal create 失败：旧终端保留，无其他终端副作用
#   H. register 其他失败：回滚新终端，旧终端保留
#   I. 旧 runtime 无 task-list：状态探测降级 unknown，行为不比现状差
#
# Task-113 增补（TASK_REUSED 有界区分的 drift/unknown 防线，注册阶段兜底）：
#   K. 复位后重试仍 TASK_REUSED：只重试一次，回滚新终端，旧终端保留
#   L. 预检 failed → 复核翻回 dispatched（漂移=真单活出现）：fail-closed 不复位
#   M. 预检 unknown + TASK_REUSED：fail-closed 不猜测不复位
#
# Task-116 增补（Badminton Lab 实测事故①：旧 Dispatch 已 worker_done/release/ack/
# settled 后，METADATA 残留 dispatch_id 让 reauthorize 把死目标当 live，先合并授权、
# 重写 launch.sh、创建替换终端才回滚。修复：任何 mutation（含 run-use 回绑）前读权威
# Dispatch 状态，只有仍 live（未 released/acked/settled）的目标可继续，其余稳定输出
# REAUTHORIZE_NOT_LIVE 并零副作用）：
#   J.  settled（结算链走完）→ 预门禁拒绝，授权/launch.sh/终端/METADATA 零变化
#   J2. released → 同 J 拒绝
#   N.  已结算目标重复调用 → 零副作用、不累积终端
#   O.  acked（released_retained）→ 同 J 拒绝
#   O2. worker-show 不可达（状态未知）→ fail-closed 零副作用拒绝
#   O3. 已结算目标不带 --allow-cmd 的纯快照刷新 → 同样拒绝
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PM="$SCRIPT_DIR/pm-orchestrate.sh"
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT
DEBUG_RC="${DEBUG_RC:-0}" # 置 1 时打印每次 run_reauth 的 rc 与完整输出（调试用）

pass=0
fail=0
ok() { echo "  ✓ $1"; pass=$((pass + 1)); }
bad() { echo "  ✗ $1" >&2; fail=$((fail + 1)); }
check() { # check <描述> <命令...>（单条命令；组合条件用 if/else + ok/bad）
  local desc="$1"; shift
  if "$@" 2>/dev/null; then ok "$desc"; else bad "$desc"; fi
}
check_not() { # check_not <描述> <命令...>：命令成功即失败
  local desc="$1"; shift
  if "$@" 2>/dev/null; then bad "$desc"; else ok "$desc"; fi
}
# 组合条件断言：if/else + ok/bad，避免 && 在 check 参数外层短路触发 set -e
assert() { if eval "$2"; then ok "$1"; else bad "$1"; fi; }

# ---------- 可编程 fake orca CLI ----------
STATE_ROOT="$TMP_ROOT/state"
mkdir -p "$STATE_ROOT"
FAKE="$TMP_ROOT/fake-orca"
export FAKE_ORCA_LOG="$TMP_ROOT/orca.log"
export FAKE_ORCA_STATE="$STATE_ROOT"
: > "$FAKE_ORCA_LOG"

cat > "$FAKE" <<'FAKE'
#!/usr/bin/env bash
set -euo pipefail
{
  for arg in "$@"; do printf '%q ' "$arg"; done
  printf '\n'
} >> "$FAKE_ORCA_LOG"
S="$FAKE_ORCA_STATE"
case "$1 $2" in
  "orchestration run-use")
    echo '{"ok":true,"result":{"run":{"id":"run-r","coordinator_handle":"term-pm"}}}
'
    ;;
  "orchestration task-list")
    if [ -e "$S/task-list-unavailable" ]; then
      echo "ERROR: unknown command: task-list" >&2
      exit 1
    fi
    status=$(cat "$S/task-status" 2>/dev/null) || status="ready"
    # Task-113 漂移注入：task-status-next 存在时，本次返回当前值后一次性轮换进下一
    # 状态（预检 failed → 复核 dispatched 的状态漂移场景）。
    if [ -f "$S/task-status-next" ]; then
      mv "$S/task-status-next" "$S/task-status"
    fi
    printf '{"ok":true,"result":{"tasks":[{"id":"task-1","status":"%s"}]}}\n' "$status"
    ;;
  "orchestration check")
    if [ -f "$S/pending-message.json" ]; then
      cat "$S/pending-message.json"
    else
      echo '{"ok":true,"result":{"count":0,"messages":[]}}'
    fi
    ;;
  "orchestration reply")
    id=""; body=""
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --id) id="$2"; shift 2 ;;
        --body) body="$2"; shift 2 ;;
        *) shift ;;
      esac
    done
    printf '%s\n' "$body" > "$S/last-reply-body.txt"
    printf '%s\n' "$id" > "$S/last-reply-id.txt"
    echo '{"ok":true,"result":{}}'
    ;;
  "orchestration worker-start")
    mode=$(cat "$S/worker-start-result" 2>/dev/null) || mode="ok"
    # task_not_startable 一次性：模拟真实 Orca——task-update 复位 ready 后重试即成功。
    # TASK_REUSED 保持粘滞：活 Dispatch 存续期间重复注册必被单活 fencing 拒绝。
    # task_reused_once（Task-113）：已结算 task 首次注册返回 TASK_REUSED；仅当 PM 已用
    # task-update 复位 ready 后（task-update.count ≥ 1）重试才成功，复位前保持粘滞拒绝
    # ——保证回归验证的是「复位 → 重试」因果链，而非重试本身。
    if [ "$mode" = "task_not_startable" ]; then
      printf 'ok\n' > "$S/worker-start-result"
    elif [ "$mode" = "task_reused_once" ]; then
      if [ -f "$S/task-update.count" ] && [ "$(cat "$S/task-update.count")" -ge 1 ]; then
        mode="ok"
      fi
    fi
    case "$mode" in
      ok)
        echo '{"ok":true,"result":{"dispatch":{"id":"ctx-new-1"}}}
'
        ;;
      task_not_startable|TASK_REUSED)
        printf '{"ok":false,"error":{"code":"%s","message":"%s"}}\n' "$mode" "$mode" >&2
        printf '{"ok":false,"error":{"code":"%s","message":"%s"}}\n' "$mode" "$mode"
        exit 1
        ;;
      *)
        echo '{"ok":false,"error":{"code":"TERMINAL_UNAVAILABLE","message":"boom"}}' >&2
        echo '{"ok":false,"error":{"code":"TERMINAL_UNAVAILABLE","message":"boom"}}'
        exit 1
        ;;
    esac
    ;;
  "orchestration worker-show")
    # Task-116 liveness 预门禁数据源：默认 live dispatch（dispatched + 未 release）；
    # 状态文件把旧 Dispatch 钉进结算链的不同阶段（settled ⊃ released/acked）。
    if [ -e "$S/worker-show-unavailable" ]; then
      echo "ERROR: unknown command: worker-show" >&2
      exit 1
    fi
    if [ -e "$S/dispatch-settled" ]; then
      echo '{"ok":true,"result":{"dispatch":{"id":"ctx-old","status":"settled"},"worker":{"state":"succeeded"},"terminalResource":{"releaseState":"released"}}}'
    elif [ -e "$S/dispatch-acked" ]; then
      echo '{"ok":true,"result":{"dispatch":{"id":"ctx-old","status":"completed"},"worker":{"state":"succeeded"},"terminalResource":{"releaseState":"released_retained"}}}'
    elif [ -e "$S/dispatch-released" ]; then
      echo '{"ok":true,"result":{"dispatch":{"id":"ctx-old","status":"completed"},"worker":{"state":"stopped"},"terminalResource":{"releaseState":"released"}}}'
    else
      echo '{"ok":true,"result":{"dispatch":{"id":"ctx-old","status":"dispatched"},"worker":{"state":"active"},"terminalResource":{"releaseState":"not_requested"}}}'
    fi
    ;;
  "orchestration dispatch-show")
    echo '{"ok":true,"result":{"dispatch":{"id":"ctx-new-1"}}}
'
    ;;
  "orchestration task-update")
    echo 1 >> "$S/task-update.count"
    echo '{"ok":true,"result":{}}'
    ;;
  "terminal create")
    if [ -e "$S/terminal-create-fail" ]; then
      echo '{"ok":false,"error":{"code":"TERMINAL_CREATE_FAILED"}}' >&2
      exit 1
    fi
    n=0
    if [ -f "$S/terminal-create.count" ]; then n=$(cat "$S/terminal-create.count"); fi
    n=$((n + 1))
    printf '%s\n' "$n" > "$S/terminal-create.count"
    handle="term-new-$n"
    printf '%s\n' "$handle" >> "$S/terminals.live"
    printf '{"ok":true,"result":{"terminal":{"handle":"%s"}}}\n' "$handle"
    ;;
  "terminal close")
    handle=""
    while [ "$#" -gt 0 ]; do
      case "$1" in --terminal) handle="$2"; shift 2 ;; *) shift ;; esac
    done
    printf '%s\n' "$handle" >> "$S/terminals.closed"
    if [ -f "$S/terminals.live" ]; then
      if grep -v -x "$handle" "$S/terminals.live" > "$S/terminals.live.next"; then
        :
      else
        grep_status=$?
        # grep=1 只表示删除后结果为空；I/O/参数等真实错误不得被测试桩吞掉。
        [ "$grep_status" -eq 1 ] || exit "$grep_status"
        : > "$S/terminals.live.next"
      fi
      mv "$S/terminals.live.next" "$S/terminals.live"
    fi
    echo '{"ok":true,"result":{}}'
    ;;
  "terminal send")
    text=""
    while [ "$#" -gt 0 ]; do
      case "$1" in --text) text="$2"; shift 2 ;; *) shift ;; esac
    done
    printf '%s\n' "$text" > "$S/last-terminal-send.txt"
    echo '{"ok":true,"result":{}}'
    ;;
  *)
    echo '{"ok":true,"result":{}}'
    ;;
esac
FAKE
chmod +x "$FAKE"
export ORCA_CLI_COMMAND="$FAKE"

# ---------- fixture ----------
# make_fixture <case>: 建独立 git repo+worktree+METADATA+Session Context，
# 并把 fake 状态目录指向本 case；产出全局 WT/SESSION/METADATA/SC/SD。
make_fixture() {
  local case_name="$1" base
  base="$TMP_ROOT/$case_name"
  REPO="$base/repo"
  WT="$base/wt"
  SESSION="w-$case_name"
  SD="$STATE_ROOT/$case_name"
  METADATA="$WT/.claude/agent-sessions/$SESSION/METADATA.json"
  SC="$WT/.claude/agent-sessions/$SESSION"
  mkdir -p "$REPO" "$SD"
  export FAKE_ORCA_STATE="$SD" # fake 的 $S 与本 case 断言目录对齐
  git -C "$REPO" init -q
  printf '%s\n' base > "$REPO/base.txt"
  git -C "$REPO" add base.txt
  GIT_AUTHOR_NAME=T GIT_AUTHOR_EMAIL=t@t.invalid \
    GIT_COMMITTER_NAME=T GIT_COMMITTER_EMAIL=t@t.invalid \
    git -C "$REPO" commit -q -m base
  git -C "$REPO" worktree add -q -b "b-$case_name" "$WT"
  mkdir -p "$SC"
  jq -n --arg project "$REPO" --arg worktree "$WT" --arg session "$SESSION" \
    '{project:$project,worktree:$worktree,session:{id:$session,orca:{worktree_id:"repo::worker",terminal_handle:"term-old",supervised:{run_id:"run-r",coordinator_handle:"term-pm",task_id:"task-1",dispatch_id:"ctx-old"}}},runtime:{provider_lease:{file:""}}}' \
    > "$METADATA"
  printf '{"allowed_shell_commands":["cmd-old"],"version":1}\n' > "$SC/INSTALL_AUTHORIZATION.json"
  local b64
  b64=$(base64 < "$SC/INSTALL_AUTHORIZATION.json" | tr -d '\n')
  {
    printf '#!/usr/bin/env bash\n'
    printf 'WORKER_INSTALL_AUTH_B64=%s\n' "$b64"
    printf 'exec echo worker-launch\n'
  } > "$SC/launch.sh"
  : > "$FAKE_ORCA_LOG"
  rm -f "$SD/terminals.live" "$SD/terminals.closed" "$SD/task-update.count" \
        "$SD/terminal-create.count" "$SD/last-reply-body.txt" "$SD/last-reply-id.txt" \
        "$SD/last-terminal-send.txt" "$SD/terminal-create-fail" "$SD/task-list-unavailable" \
        "$SD/task-status" "$SD/task-status-next" "$SD/worker-start-result" "$SD/pending-message.json" \
        "$SD/dispatch-settled" "$SD/dispatch-released" "$SD/dispatch-acked" \
        "$SD/worker-show-unavailable"
  printf 'term-old\n' > "$SD/terminals.live"
}

log_count() { grep -c "^$1 " "$FAKE_ORCA_LOG" 2>/dev/null || true; }
live_count() { grep -c . "$SD/terminals.live" 2>/dev/null || true; }
live_is_solely() { [ "$(live_count)" = "1" ] && grep -qx "$1" "$SD/terminals.live" 2>/dev/null; }
run_reauth() { # run_reauth <额外参数...>；产出全局 RC/OUT
  RC=0
  OUT=$(bash "$PM" reauthorize --worktree "$WT" --session "$SESSION" "$@" 2>&1) || RC=$?
  if [ "$DEBUG_RC" = "1" ]; then
    printf '  [debug rc=%s]\n' "$RC"
    printf '%s\n' "$OUT" | sed 's/^/    | /'
  fi
}

echo "Case A: dispatched + 未消费 escalation 消息 → reply 消费等待，TASK_REUSED 回滚不泄漏"
make_fixture A
printf 'dispatched\n' > "$SD/task-status"
printf 'TASK_REUSED\n' > "$SD/worker-start-result"
cat > "$SD/pending-message.json" <<'JSON'
{"ok":true,"result":{"count":1,"messages":[{"id":"msg-esc-1","type":"escalation","to":"dispatch:ctx-old","dispatch_id":"ctx-old","body":"cmd-x not allowlisted"}]}}
JSON
run_reauth --allow-cmd "cmd-x" --resume-text "已扩权 cmd-x,从断点继续"
check "退出码非 0(TASK_REUSED 属硬限制,已给指引)" test "$RC" -ne 0
check "输出含 TASK_REUSED 分类标记" grep -q "PM_REAUTHORIZE_REGISTER_TASK_REUSED" <<<"$OUT"
check "输出含 runbook #18 manual-recovery 指引" grep -q "runbook #18" <<<"$OUT"
check "输出含 settle 后重跑选项" grep -q "settle" <<<"$OUT"
check "等待已被 reply 消费(msg-esc-1)" grep -qx "msg-esc-1" "$SD/last-reply-id.txt"
check "reply body 即 --resume-text" grep -qx "已扩权 cmd-x,从断点继续" "$SD/last-reply-body.txt"
check "授权文件仍已合并 cmd-x" grep -q "cmd-x" "$SC/INSTALL_AUTHORIZATION.json"
check "新终端曾被创建" test "$(cat "$SD/terminal-create.count" 2>/dev/null || echo 0)" = "1"
check "新终端已被回滚关闭" grep -qx "term-new-1" "$SD/terminals.closed"
assert "旧终端保留(唯一活终端)" 'live_is_solely term-old'
check "METADATA 仍路由旧终端" test "$(jq -r '.session.orca.terminal_handle' "$METADATA")" = "term-old"
check_not "旧终端未被执行 close" grep -q "^terminal close .* term-old" "$FAKE_ORCA_LOG"

echo "Case B: dispatched 无消息 → 跳过消费，其余同 A"
make_fixture B
printf 'dispatched\n' > "$SD/task-status"
printf 'TASK_REUSED\n' > "$SD/worker-start-result"
run_reauth --allow-cmd "cmd-y"
check "退出码非 0" test "$RC" -ne 0
check_not "无 reply 调用" grep -q "^orchestration reply " "$FAKE_ORCA_LOG"
check "输出含无待消费标记" grep -q "PM_REAUTHORIZE_WAIT_NONE" <<<"$OUT"
check "TASK_REUSED 分类标记存在" grep -q "PM_REAUTHORIZE_REGISTER_TASK_REUSED" <<<"$OUT"
check "新终端已回滚" grep -qx "term-new-1" "$SD/terminals.closed"
assert "旧终端保留且唯一" 'live_is_solely term-old'

echo "Case C: failed → 既有路径零变化(复位 ready+重试+换终端+关旧)"
make_fixture C
printf 'failed\n' > "$SD/task-status"
printf 'task_not_startable\n' > "$SD/worker-start-result"
run_reauth --allow-cmd "cmd-c" --resume-text "继续 C"
check "退出码 0" test "$RC" -eq 0
check "worker-start 调用两次(失败+重试)" test "$(log_count 'orchestration worker-start')" = "2"
check "task-update 复位一次" test "$(cat "$SD/task-update.count" 2>/dev/null || echo 0)" = "1"
check "METADATA 改路由新终端" test "$(jq -r '.session.orca.terminal_handle' "$METADATA")" = "term-new-1"
check "METADATA 改路由新 dispatch" test "$(jq -r '.session.orca.supervised.dispatch_id' "$METADATA")" = "ctx-new-1"
check "旧终端已关闭" grep -qx "term-old" "$SD/terminals.closed"
assert "新终端唯一存活" 'live_is_solely term-new-1'
check "resume 文本发到新终端" grep -q "继续 C" "$SD/last-terminal-send.txt"

echo "Case D: blocked → 同 failed"
make_fixture D
printf 'blocked\n' > "$SD/task-status"
printf 'task_not_startable\n' > "$SD/worker-start-result"
run_reauth --allow-cmd "cmd-d"
check "退出码 0" test "$RC" -eq 0
check "worker-start 调用两次" test "$(log_count 'orchestration worker-start')" = "2"
check "task-update 复位一次" test "$(cat "$SD/task-update.count" 2>/dev/null || echo 0)" = "1"
check "METADATA 改路由新终端" test "$(jq -r '.session.orca.terminal_handle' "$METADATA")" = "term-new-1"
check "旧终端已关闭" grep -qx "term-old" "$SD/terminals.closed"

echo "Case E: completed → 既有 task_not_startable 通用路径"
make_fixture E
printf 'completed\n' > "$SD/task-status"
printf 'task_not_startable\n' > "$SD/worker-start-result"
run_reauth --allow-cmd "cmd-e"
check "退出码 0" test "$RC" -eq 0
check "METADATA 改路由新终端" test "$(jq -r '.session.orca.terminal_handle' "$METADATA")" = "term-new-1"
check "旧终端已关闭" grep -qx "term-old" "$SD/terminals.closed"

echo "Case F: 重复调用幂等——成功链与 dispatched 回滚链活终端数不增长"
make_fixture F
printf 'failed\n' > "$SD/task-status"
printf 'task_not_startable\n' > "$SD/worker-start-result"
run_reauth --allow-cmd "cmd-f1"
check "第一次成功" test "$RC" -eq 0
run_reauth --allow-cmd "cmd-f2"
check "第二次成功" test "$RC" -eq 0
assert "两次后唯一活终端是最新终端" 'live_is_solely term-new-2'
check "term-old 已关" grep -qx "term-old" "$SD/terminals.closed"
check "term-new-1 已关" grep -qx "term-new-1" "$SD/terminals.closed"
check "METADATA 指向 term-new-2" test "$(jq -r '.session.orca.terminal_handle' "$METADATA")" = "term-new-2"
make_fixture F2
printf 'dispatched\n' > "$SD/task-status"
printf 'TASK_REUSED\n' > "$SD/worker-start-result"
run_reauth --allow-cmd "cmd-f3"
run_reauth --allow-cmd "cmd-f4"
assert "dispatched 连跑两次仍只剩旧终端一个活终端" 'live_is_solely term-old'
check "第一次新终端已回滚" grep -qx "term-new-1" "$SD/terminals.closed"
check "第二次新终端已回滚" grep -qx "term-new-2" "$SD/terminals.closed"

echo "Case G: terminal create 失败 → 旧终端保留，无其他终端副作用"
make_fixture G
printf 'dispatched\n' > "$SD/task-status"
printf 'TASK_REUSED\n' > "$SD/worker-start-result"
touch "$SD/terminal-create-fail"
run_reauth --allow-cmd "cmd-g"
check "退出码非 0" test "$RC" -ne 0
check "无 worker-start 调用" test "$(log_count 'orchestration worker-start')" = "0"
assert "旧终端保留且唯一" 'live_is_solely term-old'
check "METADATA 未变" test "$(jq -r '.session.orca.terminal_handle' "$METADATA")" = "term-old"

echo "Case H: register 其他失败 → 回滚新终端，旧终端保留"
make_fixture H
printf 'ready\n' > "$SD/task-status"
printf 'other-failure\n' > "$SD/worker-start-result"
run_reauth --allow-cmd "cmd-h"
check "退出码非 0" test "$RC" -ne 0
check "新终端已回滚关闭" grep -qx "term-new-1" "$SD/terminals.closed"
assert "旧终端保留且唯一" 'live_is_solely term-old'
check "METADATA 未变" test "$(jq -r '.session.orca.terminal_handle' "$METADATA")" = "term-old"

echo "Case I: 旧 runtime 无 task-list → 状态探测降级，不比现状差"
make_fixture I
printf 'dispatched\n' > "$SD/task-status"
printf 'TASK_REUSED\n' > "$SD/worker-start-result"
touch "$SD/task-list-unavailable"
run_reauth --allow-cmd "cmd-i"
check "退出码非 0" test "$RC" -ne 0
check "TASK_REUSED 仍给出 manual-recovery 而非裸错误" grep -q "PM_REAUTHORIZE_MANUAL_RECOVERY" <<<"$OUT"
check "新终端已回滚" grep -qx "term-new-1" "$SD/terminals.closed"
assert "旧终端保留且唯一" 'live_is_solely term-old'

echo "Case J (Task-116): worker_done 结算后（release+ack+settled）→ 预门禁 REAUTHORIZE_NOT_LIVE 零副作用拒绝"
make_fixture J
printf 'failed\n' > "$SD/task-status"
printf 'task_reused_once\n' > "$SD/worker-start-result"
touch "$SD/dispatch-settled"
cp "$SC/INSTALL_AUTHORIZATION.json" "$TMP_ROOT/J-auth-before.json"
cp "$SC/launch.sh" "$TMP_ROOT/J-launch-before.sh"
cp "$METADATA" "$TMP_ROOT/J-metadata-before.json"
run_reauth --allow-cmd "cmd-j" --resume-text "结算残留已复位,从断点继续"
check "退出码非 0（已结算目标不再经由 reauthorize 复活）" test "$RC" -ne 0
check "输出含稳定机器码 REAUTHORIZE_NOT_LIVE" grep -q "REAUTHORIZE_NOT_LIVE" <<<"$OUT"
check_not "零授权合并：--allow-cmd 未写入授权文件" grep -q "cmd-j" "$SC/INSTALL_AUTHORIZATION.json"
check "launch.sh B64 未被改写" cmp -s "$TMP_ROOT/J-launch-before.sh" "$SC/launch.sh"
check_not "零新终端创建" test "$(cat "$SD/terminal-create.count" 2>/dev/null || echo 0)" != "0"
check_not "零 worker-start 调用" grep -q "^orchestration worker-start" "$FAKE_ORCA_LOG"
check_not "零 task-update 复位" grep -q "^orchestration task-update" "$FAKE_ORCA_LOG"
check_not "零 reply 消费" grep -q "^orchestration reply " "$FAKE_ORCA_LOG"
check_not "零 run-use 回绑" grep -q "^orchestration run-use" "$FAKE_ORCA_LOG"
check "METADATA 未变（仍路由旧终端）" cmp -s "$TMP_ROOT/J-metadata-before.json" "$METADATA"
assert "旧终端保留且唯一（零终端副作用）" 'live_is_solely term-old'

echo "Case J2 (Task-116): released（release 已做、settled 未完成）同 J 拒绝"
make_fixture J2
printf 'failed\n' > "$SD/task-status"
printf 'task_reused_once\n' > "$SD/worker-start-result"
touch "$SD/dispatch-released"
run_reauth --allow-cmd "cmd-j2"
check "退出码非 0" test "$RC" -ne 0
check "输出含 REAUTHORIZE_NOT_LIVE" grep -q "REAUTHORIZE_NOT_LIVE" <<<"$OUT"
check_not "零新终端创建" test "$(cat "$SD/terminal-create.count" 2>/dev/null || echo 0)" != "0"
check_not "零 worker-start 调用" grep -q "^orchestration worker-start" "$FAKE_ORCA_LOG"
assert "旧终端保留且唯一" 'live_is_solely term-old'
check "METADATA 仍路由旧终端" test "$(jq -r '.session.orca.terminal_handle' "$METADATA")" = "term-old"

echo "Case K (Task-113): 复位后重试仍 TASK_REUSED → 只重试一次,回滚新终端 fail-closed"
make_fixture K
printf 'failed\n' > "$SD/task-status"
printf 'TASK_REUSED\n' > "$SD/worker-start-result"
run_reauth --allow-cmd "cmd-k"
check "退出码非 0" test "$RC" -ne 0
check "worker-start 恰好两次(有界单次重试)" test "$(log_count 'orchestration worker-start')" = "2"
check "task-update 恰好一次" test "$(cat "$SD/task-update.count" 2>/dev/null || echo 0)" = "1"
check "新终端已回滚关闭" grep -qx "term-new-1" "$SD/terminals.closed"
assert "旧终端保留且唯一(不累积终端)" 'live_is_solely term-old'
check "METADATA 未变" test "$(jq -r '.session.orca.terminal_handle' "$METADATA")" = "term-old"

echo "Case L (Task-113): 预检 failed → 复核翻回 dispatched(漂移=真单活) → fail-closed 不复位"
make_fixture L
printf 'failed\n' > "$SD/task-status"
printf 'dispatched\n' > "$SD/task-status-next"
printf 'TASK_REUSED\n' > "$SD/worker-start-result"
run_reauth --allow-cmd "cmd-l"
check "退出码非 0" test "$RC" -ne 0
check "task-list 恰好两次(预检+复核)" test "$(log_count 'orchestration task-list')" = "2"
check_not "漂移时不得复位 task" grep -q "^orchestration task-update" "$FAKE_ORCA_LOG"
check "输出含漂移 fail-closed 标记" grep -q "PM_REAUTHORIZE_TASK_STATE_DRIFT" <<<"$OUT"
check "新终端已回滚关闭" grep -qx "term-new-1" "$SD/terminals.closed"
assert "旧终端保留且唯一" 'live_is_solely term-old'
check "METADATA 未变" test "$(jq -r '.session.orca.terminal_handle' "$METADATA")" = "term-old"

echo "Case M (Task-113): 预检 unknown + TASK_REUSED → fail-closed 不猜测不复位"
make_fixture M
printf 'TASK_REUSED\n' > "$SD/worker-start-result"
touch "$SD/task-list-unavailable"
run_reauth --allow-cmd "cmd-m"
check "退出码非 0" test "$RC" -ne 0
check_not "unknown 不得复位 task" grep -q "^orchestration task-update" "$FAKE_ORCA_LOG"
check "TASK_REUSED 分类标记仍在" grep -q "PM_REAUTHORIZE_REGISTER_TASK_REUSED" <<<"$OUT"
check "manual-recovery 指引仍在" grep -q "PM_REAUTHORIZE_MANUAL_RECOVERY" <<<"$OUT"
check "新终端已回滚关闭" grep -qx "term-new-1" "$SD/terminals.closed"
assert "旧终端保留且唯一" 'live_is_solely term-old'

echo "Case N (Task-116): 已结算目标重复调用 reauthorize 零副作用、不累积终端"
make_fixture N
printf 'failed\n' > "$SD/task-status"
printf 'task_reused_once\n' > "$SD/worker-start-result"
touch "$SD/dispatch-settled"
run_reauth --allow-cmd "cmd-n1"
check "第一次拒绝" test "$RC" -ne 0
run_reauth --allow-cmd "cmd-n2"
check "第二次拒绝" test "$RC" -ne 0
check "两次调用零新终端创建" test "$(cat "$SD/terminal-create.count" 2>/dev/null || echo 0)" = "0"
assert "旧终端保留且唯一（活终端数不增长）" 'live_is_solely term-old'
check_not "零 worker-start 调用" grep -q "^orchestration worker-start" "$FAKE_ORCA_LOG"
check "METADATA 仍路由旧终端" test "$(jq -r '.session.orca.terminal_handle' "$METADATA")" = "term-old"

echo "Case O (Task-116): acked（released_retained）同属结算链 → 拒绝"
make_fixture O
printf 'failed\n' > "$SD/task-status"
printf 'task_reused_once\n' > "$SD/worker-start-result"
touch "$SD/dispatch-acked"
run_reauth --allow-cmd "cmd-o"
check "退出码非 0" test "$RC" -ne 0
check "输出含 REAUTHORIZE_NOT_LIVE" grep -q "REAUTHORIZE_NOT_LIVE" <<<"$OUT"
check_not "零新终端创建" test "$(cat "$SD/terminal-create.count" 2>/dev/null || echo 0)" != "0"
assert "旧终端保留且唯一" 'live_is_solely term-old'

echo "Case O2 (Task-116): worker-show 不可达（状态未知）→ fail-closed 零副作用拒绝"
make_fixture O2
printf 'dispatched\n' > "$SD/task-status"
printf 'TASK_REUSED\n' > "$SD/worker-start-result"
touch "$SD/worker-show-unavailable"
run_reauth --allow-cmd "cmd-o2"
check "退出码非 0（未知状态不得带副作用推进）" test "$RC" -ne 0
check "输出含 REAUTHORIZE_NOT_LIVE" grep -q "REAUTHORIZE_NOT_LIVE" <<<"$OUT"
check_not "零授权合并" grep -q "cmd-o2" "$SC/INSTALL_AUTHORIZATION.json"
check_not "零新终端创建" test "$(cat "$SD/terminal-create.count" 2>/dev/null || echo 0)" != "0"
check_not "零 worker-start 调用" grep -q "^orchestration worker-start" "$FAKE_ORCA_LOG"
assert "旧终端保留且唯一" 'live_is_solely term-old'
check "METADATA 仍路由旧终端" test "$(jq -r '.session.orca.terminal_handle' "$METADATA")" = "term-old"

echo "Case O3 (Task-116): 已结算目标不带 --allow-cmd 的纯快照刷新请求同样拒绝"
make_fixture O3
printf 'failed\n' > "$SD/task-status"
touch "$SD/dispatch-settled"
cp "$SC/launch.sh" "$TMP_ROOT/O3-launch-before.sh"
run_reauth
check "退出码非 0" test "$RC" -ne 0
check "输出含 REAUTHORIZE_NOT_LIVE" grep -q "REAUTHORIZE_NOT_LIVE" <<<"$OUT"
check "launch.sh 未被改写" cmp -s "$TMP_ROOT/O3-launch-before.sh" "$SC/launch.sh"
check_not "零新终端创建" test "$(cat "$SD/terminal-create.count" 2>/dev/null || echo 0)" != "0"
assert "旧终端保留且唯一" 'live_is_solely term-old'

echo ""
echo "Result: $pass pass, $fail fail"
[ "$fail" -eq 0 ]
