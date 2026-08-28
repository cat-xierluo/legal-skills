#!/usr/bin/env bash
set -euo pipefail

REAL_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LAUNCH_HELPER="$REAL_SCRIPT_DIR/spawn-worker-launch.sh"
CASE_ROOT=$(mktemp -d)
FAKE_LOG="$CASE_ROOT/launch.log"
trap 'rm -rf "$CASE_ROOT"' EXIT

passed=0
failed=0

ok() {
  printf 'PASS: %s\n' "$1"
  passed=$((passed + 1))
}

bad() {
  printf 'FAIL: %s\n' "$1" >&2
  failed=$((failed + 1))
}

assert_eq() {
  local actual="$1" expected="$2" label="$3"
  if [ "$actual" = "$expected" ]; then
    ok "$label"
  else
    bad "$label (expected=$expected actual=$actual)"
  fi
}

# shellcheck source=spawn-worker-launch.sh
source "$LAUNCH_HELPER"

reset_launch_case() {
  SCRIPT_DIR="$REAL_SCRIPT_DIR"
  WORKTREE="$CASE_ROOT/worktree"
  SESSION="worker-session"
  COMMAND="codex"
  ORCA_MODE="force_tmux"
  ORCA_WORKTREE_ID="repo-1::worker"
  ORCA_TERMINAL_HANDLE=""
  ORCA_SUPERVISED=0
  ORCA_RUN_ID=""
  ORCA_COORDINATOR_HANDLE=""
  ORCA_TASK_ID=""
  TASK_SPEC="full spec"
  TASK_TITLE="short title"
  ORCA_SUPERVISED_RUN_ID=""
  ORCA_SUPERVISED_COORDINATOR_HANDLE=""
  ORCA_SUPERVISED_TASK_ID=""
  ORCA_SUPERVISED_DISPATCH_ID=""
  DRY_RUN=0
  METADATA_FILE="$CASE_ROOT/metadata.json"
  mkdir -p "$WORKTREE/.claude/agent-sessions/$SESSION"
  : > "$FAKE_LOG"
}

run() {
  printf '%s\n' "$*" >> "$FAKE_LOG"
}

orca_terminal_create_and_send() {
  printf '%s|%s|%s|%s\n' "$1" "$2" "$3" "$4" >> "$FAKE_LOG"
  ORCA_TERMINAL_HANDLE="term-worker"
}

reset_launch_case
launch_worker_session
if grep -Fq 'tmux new-session -d -s worker-session' "$FAKE_LOG"; then
  ok "tmux route keeps exact session launch arguments"
else
  bad "tmux route keeps exact session launch arguments"
fi
assert_eq "$COMMAND" "codex" "single-token command needs no launch wrapper"

reset_launch_case
COMMAND="codebuddy --permission-mode acceptEdits"
launch_worker_session
LAUNCH_SH="$WORKTREE/.claude/agent-sessions/$SESSION/launch.sh"
if [ -x "$LAUNCH_SH" ] && grep -Fq 'exec bash -c' "$LAUNCH_SH"; then
  ok "spaced command is wrapped in an executable launch script"
else
  bad "spaced command is wrapped in an executable launch script"
fi
case "$COMMAND" in
  bash\ *) ok "wrapped command points tmux at launch script" ;;
  *) bad "wrapped command points tmux at launch script" ;;
esac

reset_launch_case
SESSION="dry-run-worker-session"
COMMAND="codebuddy --permission-mode acceptEdits"
DRY_RUN=1
dry_run_plan=$(launch_worker_session)
DRY_SESSION_CONTEXT="$WORKTREE/.claude/agent-sessions/$SESSION"
LAUNCH_SH="$DRY_SESSION_CONTEXT/launch.sh"
if [ ! -e "$DRY_SESSION_CONTEXT" ]; then
  ok "dry-run spaced command does not write Session Context"
else
  bad "dry-run spaced command does not write Session Context"
fi
if printf '%s\n' "$dry_run_plan" | grep -Fq 'SPAWN_WORKER_DRY_RUN_LAUNCH_SH:'; then
  ok "dry-run spaced command reports the planned launch wrapper"
else
  bad "dry-run spaced command reports the planned launch wrapper"
fi

reset_launch_case
ORCA_MODE="auto"
printf '%s\n' '{"session":{"orca":{"terminal_handle":""}}}' > "$METADATA_FILE"
launch_worker_session
if grep -Fq 'repo-1::worker|worker-session|codex|请按你的任务开始工作' "$FAKE_LOG"; then
  ok "Orca terminal-managed route delegates one bootstrap prompt"
else
  bad "Orca terminal-managed route delegates one bootstrap prompt"
fi
if jq -e '.session.orca.terminal_handle == "term-worker"' "$METADATA_FILE" >/dev/null; then
  ok "Orca launch patches the exact terminal handle into metadata"
else
  bad "Orca launch patches the exact terminal handle into metadata"
fi

reset_launch_case
ORCA_MODE="auto"
ORCA_SUPERVISED=1
ORCA_RUN_ID="run-wave"
ORCA_COORDINATOR_HANDLE="term-pm"
ORCA_TASK_ID="task-worker"
DRY_RUN=1
supervised_plan=$(launch_worker_session)
if printf '%s' "$supervised_plan" | grep -Fq 'worker-start --terminal <handle>' \
  && printf '%s' "$supervised_plan" | grep -Fq 'run-wave'; then
  ok "supervised dry-run reports receipt reuse and worker-start"
else
  bad "supervised dry-run reports receipt reuse and worker-start"
fi

reset_launch_case
ORCA_MODE="auto"
ORCA_SUPERVISED=1
ORCA_RUN_ID="run-wave"
ORCA_COORDINATOR_HANDLE="term-pm"
ORCA_TASK_ID="task-worker"
SCRIPT_DIR="$CASE_ROOT/register-success"
mkdir -p "$SCRIPT_DIR"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'printf "ORCAREG_RUN_ID=run-wave\n"' \
  'printf "ORCAREG_COORDINATOR_HANDLE=term-pm\n"' \
  'printf "ORCAREG_TASK_ID=task-worker\n"' \
  'printf "ORCAREG_DISPATCH_ID=ctx-worker\n"' \
  'printf "ORCAREG_DISPATCH_BIND=ok\n"' \
  > "$SCRIPT_DIR/orca-supervised-register.sh"
printf '%s\n' '{"session":{"orca":{"terminal_handle":""}}}' > "$METADATA_FILE"
launch_worker_session
assert_eq "$ORCA_SUPERVISED_RUN_ID:$ORCA_SUPERVISED_COORDINATOR_HANDLE:$ORCA_SUPERVISED_TASK_ID:$ORCA_SUPERVISED_DISPATCH_ID" \
  "run-wave:term-pm:task-worker:ctx-worker" "supervised registration exports exact lifecycle ids"
if jq -e '.session.orca.supervised == {run_id:"run-wave",coordinator_handle:"term-pm",task_id:"task-worker",dispatch_id:"ctx-worker",dispatch_bind:"ok",contract:"orca.orchestration.contract.v1",completion_authority:"worker_done",terminal_ownership:"external"}' "$METADATA_FILE" >/dev/null; then
  ok "supervised lifecycle contract is patched into metadata"
else
  bad "supervised lifecycle contract is patched into metadata"
fi

# Task-076：dispatch 绑定 manual-required 不阻断 spawn，METADATA 保留 run/task 供 PM 手动补绑。
reset_launch_case
ORCA_MODE="auto"
ORCA_SUPERVISED=1
ORCA_RUN_ID="run-wave"
ORCA_COORDINATOR_HANDLE="term-pm"
ORCA_TASK_ID="task-worker"
SCRIPT_DIR="$CASE_ROOT/register-manual"
mkdir -p "$SCRIPT_DIR"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'printf "ORCAREG_RUN_ID=run-wave\n"' \
  'printf "ORCAREG_COORDINATOR_HANDLE=term-pm\n"' \
  'printf "ORCAREG_TASK_ID=task-worker\n"' \
  'printf "ORCAREG_DISPATCH_ID=\n"' \
  'printf "ORCAREG_DISPATCH_BIND=manual-required\n"' \
  > "$SCRIPT_DIR/orca-supervised-register.sh"
printf '%s\n' '{"session":{"orca":{"terminal_handle":""}}}' > "$METADATA_FILE"
set +e
manual_out=$(launch_worker_session 2>&1)
manual_rc=$?
set -e
assert_eq "$manual_rc" "0" "manual-required dispatch bind does not block spawn"
if printf '%s\n' "$manual_out" | grep -Fq 'SPAWN_WORKER_DISPATCH_BIND: manual-required'; then
  ok "manual-required prints explicit SPAWN_WORKER_DISPATCH_BIND line"
else
  bad "manual-required prints explicit SPAWN_WORKER_DISPATCH_BIND line"
fi
if printf '%s\n' "$manual_out" | grep -Fq 'return-preamble'; then
  ok "manual-required warning carries the runbook rebind recipe"
else
  bad "manual-required warning carries the runbook rebind recipe"
fi
if jq -e '.session.orca.supervised.dispatch_id == "" and .session.orca.supervised.dispatch_bind == "manual-required" and .session.orca.supervised.task_id == "task-worker"' "$METADATA_FILE" >/dev/null; then
  ok "manual-required metadata keeps run/task ids with empty dispatch"
else
  bad "manual-required metadata keeps run/task ids with empty dispatch"
fi

reset_launch_case
ORCA_MODE="auto"
ORCA_SUPERVISED=1
SCRIPT_DIR="$CASE_ROOT/register-missing"
mkdir -p "$SCRIPT_DIR"
set +e
( launch_worker_session ) >/dev/null 2>&1
missing_helper_rc=$?
set -e
assert_eq "$missing_helper_rc" "1" "missing supervised helper fails loud after terminal creation"

# --- Task-077：Wave receipt 派单漏 --orca-supervised 的 launch 路径 dispatch 自检 ---
# 场景（2026-08-28 Wave 20 双 worker 实测形态）：orca-wave-prepare 预建 Run/Task 后 PM
# 传 --orca-run-id/--orca-task-id 但漏 --orca-supervised。launch 路径 terminal 启动完成后
# 必须执行与 register 路径共用的 dispatch-show 自检 + 三步自动补绑，输出同款
# SPAWN_WORKER_DISPATCH_BIND 行。orca_cli 以函数 stub 驱动（真协议函数来自
# orca-supervised-protocol.sh，由 launch_worker_session 的 Task-077 分支按调用时点 source）。
# 注意：公共函数在 `$(...)` 命令替换子 shell 里调用 orca_cli，stub 内的变量写入不会
# 回到父 shell——跨调用状态必须走文件（FAKE_LOG/T77_SENDS），断言一律 grep 文件。
T77_SENDS="$CASE_ROOT/t77-sends.log"
T77_STATE=""
orca_cli() {
  printf '%s\n' "$*" >> "$FAKE_LOG"
  case "$1 $2" in
    "orchestration dispatch-show")
      case "$T77_STATE" in
        healthy) printf '%s\n' '{"result":{"dispatch":{"id":"ctx-healthy"}}}' ;;
        *) printf '%s\n' '{"result":{}}' ;;
      esac ;;
    "orchestration dispatch")
      [ "$T77_STATE" != "dispatch-fails" ] || { echo "ERROR: dispatch mutation failed" >&2; return 1; }
      printf '%s\n' '{"result":{"dispatch":{"id":"ctx-auto"},"preamble":"live preamble dispatch_id=ctx-auto"}}' ;;
    "terminal send")
      [ "$T77_STATE" != "inject-fails" ] || { echo "ERROR: terminal send failed" >&2; return 1; }
      printf '%s\n' "$*" >> "$T77_SENDS"
      printf '%s\n' '{"result":{"ok":true}}' ;;
    *) return 1 ;;
  esac
}

# Task-077 用例 1（健康路径）：dispatch-show 已回显 id → bind ok，不触发补绑 mutation。
reset_launch_case
ORCA_MODE="auto"
T77_STATE="healthy"
ORCA_RUN_ID="run-wave"
ORCA_COORDINATOR_HANDLE="term-pm"
ORCA_TASK_ID="task-worker"
printf '%s\n' '{"session":{"orca":{"terminal_handle":""}}}' > "$METADATA_FILE"
set +e
t77_healthy_out=$(launch_worker_session 2>&1)
t77_healthy_rc=$?
set -e
assert_eq "$t77_healthy_rc" "0" "Task-077 healthy pre-created task exits 0"
if printf '%s\n' "$t77_healthy_out" | grep -Fq 'SPAWN_WORKER_DISPATCH_BIND: ok'; then
  ok "Task-077 healthy path prints SPAWN_WORKER_DISPATCH_BIND ok"
else
  bad "Task-077 healthy path prints SPAWN_WORKER_DISPATCH_BIND ok"
fi
if grep -Fq -- '--return-preamble' "$FAKE_LOG"; then
  bad "Task-077 healthy path must not trigger rebind mutation"
else
  ok "Task-077 healthy path must not trigger rebind mutation"
fi
if grep -Fq 'orchestration dispatch-show --task task-worker' "$FAKE_LOG"; then
  ok "Task-077 launch path actively calls dispatch-show after terminal start"
else
  bad "Task-077 launch path actively calls dispatch-show after terminal start"
fi
if jq -e '.session.orca.supervised.dispatch_id == "ctx-healthy" and .session.orca.supervised.dispatch_bind == "ok" and .session.orca.supervised.task_id == "task-worker"' "$METADATA_FILE" >/dev/null; then
  ok "Task-077 healthy path patches the supervised contract into metadata"
else
  bad "Task-077 healthy path patches the supervised contract into metadata"
fi

# Task-077 用例 2（dispatch-missing 分支）：receipt 与 dispatch-show 均空 → 三步自动补绑成功。
reset_launch_case
ORCA_MODE="auto"
T77_STATE="missing"
: > "$T77_SENDS"
ORCA_RUN_ID="run-wave"
ORCA_COORDINATOR_HANDLE="term-pm"
ORCA_TASK_ID="task-worker"
printf '%s\n' '{"session":{"orca":{"terminal_handle":""}}}' > "$METADATA_FILE"
set +e
t77_rebind_out=$(launch_worker_session 2>&1)
t77_rebind_rc=$?
set -e
assert_eq "$t77_rebind_rc" "0" "Task-077 auto rebind on launch path exits 0"
if printf '%s\n' "$t77_rebind_out" | grep -Fq 'SPAWN_WORKER_DISPATCH_BIND: ok'; then
  ok "Task-077 auto rebind reports bind ok"
else
  bad "Task-077 auto rebind reports bind ok"
fi
t77_mutation_call=$(grep -F -- 'orchestration dispatch --task task-worker --to term-worker --run run-wave' "$FAKE_LOG" | head -1)
if [ -n "$t77_mutation_call" ]; then
  ok "Task-077 rebind dispatch mutation targets the exact pre-created task"
else
  bad "Task-077 rebind dispatch mutation targets the exact pre-created task"
fi
if printf '%s' "$t77_mutation_call" | grep -Fq -- '--inject'; then
  bad "Task-077 rebind must not pass --inject (agent-unrecognized runbook rule)"
else
  ok "Task-077 rebind must not pass --inject (agent-unrecognized runbook rule)"
fi
if printf '%s\n' "$t77_rebind_out" | grep -Fq 'SPAWN_WORKER_ORCA_PRECREATED_TASK_BOUND: dispatch=ctx-auto'; then
  ok "Task-077 rebind exports the recovered dispatch id"
else
  bad "Task-077 rebind exports the recovered dispatch id"
fi
t77_send_lines=$(wc -l < "$T77_SENDS" | tr -d ' ')
assert_eq "$t77_send_lines" "1" "Task-077 rebind injects exactly one single-line send"
if grep -Fq 'ctx-auto' "$T77_SENDS" && grep -Fq -- '--type worker_done' "$T77_SENDS" \
  && grep -Fq -- '--task-id task-worker' "$T77_SENDS" && grep -Fq -- '--from term-worker' "$T77_SENDS" \
  && grep -Fq -- 'orchestration ask' "$T77_SENDS"; then
  ok "Task-077 injected line carries dispatch id and worker_done/ask command forms"
else
  bad "Task-077 injected line carries dispatch id and worker_done/ask command forms"
fi
if jq -e '.session.orca.supervised == {run_id:"run-wave",coordinator_handle:"term-pm",task_id:"task-worker",dispatch_id:"ctx-auto",dispatch_bind:"ok",contract:"orca.orchestration.contract.v1",completion_authority:"worker_done",terminal_ownership:"external"}' "$METADATA_FILE" >/dev/null; then
  ok "Task-077 rebind patches the full supervised lifecycle contract into metadata"
else
  bad "Task-077 rebind patches the full supervised lifecycle contract into metadata"
fi

# Task-077 用例 3（补绑 mutation 失败）：manual-required + 显式告警 + 不阻断（exit 0）。
reset_launch_case
ORCA_MODE="auto"
T77_STATE="dispatch-fails"
: > "$T77_SENDS"
ORCA_RUN_ID="run-wave"
ORCA_COORDINATOR_HANDLE="term-pm"
ORCA_TASK_ID="task-worker"
printf '%s\n' '{"session":{"orca":{"terminal_handle":""}}}' > "$METADATA_FILE"
set +e
t77_manual_out=$(launch_worker_session 2>&1)
t77_manual_rc=$?
set -e
assert_eq "$t77_manual_rc" "0" "Task-077 failed rebind does not block spawn (exit 0)"
if printf '%s\n' "$t77_manual_out" | grep -Fq 'SPAWN_WORKER_DISPATCH_BIND: manual-required'; then
  ok "Task-077 failed rebind prints explicit manual-required line"
else
  bad "Task-077 failed rebind prints explicit manual-required line"
fi
if printf '%s\n' "$t77_manual_out" | grep -Fq 'return-preamble'; then
  ok "Task-077 manual-required warning carries the runbook rebind recipe"
else
  bad "Task-077 manual-required warning carries the runbook rebind recipe"
fi
if [ -s "$T77_SENDS" ]; then
  bad "Task-077 failed rebind must not inject protocol line"
else
  ok "Task-077 failed rebind must not inject protocol line"
fi
if jq -e '.session.orca.supervised.dispatch_id == "" and .session.orca.supervised.dispatch_bind == "manual-required" and .session.orca.supervised.task_id == "task-worker"' "$METADATA_FILE" >/dev/null; then
  ok "Task-077 manual-required metadata keeps run/task ids with empty dispatch"
else
  bad "Task-077 manual-required metadata keeps run/task ids with empty dispatch"
fi

# Task-077 用例 4（残缺组合 fail-closed）：--orca-task-id 漏 --orca-supervised 且缺
# --orca-run-id 时，必须在任何 terminal 副作用之前失败关闭。
reset_launch_case
ORCA_MODE="auto"
: > "$FAKE_LOG"
ORCA_TASK_ID="task-worker"
set +e
t77_incomplete_out=$(launch_worker_session 2>&1)
t77_incomplete_rc=$?
set -e
assert_eq "$t77_incomplete_rc" "64" "Task-077 incomplete receipt combo fails closed with exit 64"
if [ -s "$FAKE_LOG" ]; then
  bad "Task-077 incomplete combo must fail before any terminal side effect"
else
  ok "Task-077 incomplete combo must fail before any terminal side effect"
fi

# Task-077 用例 5（纯 terminal-managed 回归保护）：无 --orca-task-id 时不做任何
# dispatch 自检调用，行为与 Task-077 之前完全一致。
reset_launch_case
ORCA_MODE="auto"
: > "$FAKE_LOG"
printf '%s\n' '{"session":{"orca":{"terminal_handle":""}}}' > "$METADATA_FILE"
launch_worker_session >/dev/null 2>&1
if grep -Fq 'dispatch-show' "$FAKE_LOG"; then
  bad "Task-077 plain terminal-managed spawn must not call dispatch-show"
else
  ok "Task-077 plain terminal-managed spawn must not call dispatch-show"
fi
if jq -e 'has("supervised")' <(jq '.session.orca' "$METADATA_FILE") >/dev/null 2>&1; then
  bad "Task-077 plain terminal-managed spawn writes no supervised block"
else
  ok "Task-077 plain terminal-managed spawn writes no supervised block"
fi

E2E_PROJECT="$CASE_ROOT/dry-run-project"
E2E_BIN="$CASE_ROOT/dry-run-bin"
E2E_SESSION="dry-run-e2e"
mkdir -p "$E2E_PROJECT" "$E2E_BIN"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'if [ "${1:-}" = "has-session" ]; then exit 1; fi' \
  'exit 0' \
  > "$E2E_BIN/tmux"
chmod +x "$E2E_BIN/tmux"
set +e
e2e_output=$(PATH="$E2E_BIN:$PATH" bash "$REAL_SCRIPT_DIR/spawn-worker.sh" \
  --project "$E2E_PROJECT" \
  --no-worktree \
  --no-orca-mode \
  --session "$E2E_SESSION" \
  --worker-backend codebuddy \
  --command 'codebuddy --permission-mode acceptEdits' \
  --dry-run 2>&1)
e2e_rc=$?
set -e
assert_eq "$e2e_rc" "0" "entrypoint accepts a dry-run spaced command"
if [ ! -e "$E2E_PROJECT/.claude/agent-sessions/$E2E_SESSION" ]; then
  ok "entrypoint dry-run leaves Session Context absent"
else
  bad "entrypoint dry-run leaves Session Context absent"
fi
if printf '%s\n' "$e2e_output" | grep -Fq 'SPAWN_WORKER_DRY_RUN_LAUNCH_SH:'; then
  ok "entrypoint dry-run exposes the planned wrapper"
else
  bad "entrypoint dry-run exposes the planned wrapper"
fi

if grep -Fq 'source "$SCRIPT_DIR/spawn-worker-launch.sh"' "$REAL_SCRIPT_DIR/spawn-worker.sh" \
  && ! grep -q '^launch_worker_session() {' "$REAL_SCRIPT_DIR/spawn-worker.sh"; then
  ok "entrypoint delegates the shared launch boundary"
else
  bad "entrypoint delegates the shared launch boundary"
fi

printf 'spawn-worker launch tests: %s passed, %s failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
