#!/usr/bin/env bash
# orca-supervised-register.sh — 把已有 ORCA agent terminal 纳入 ORCA supervised 体系（Task-033）。
#
# 把 spawn-worker 开的 agent terminal（保留 provider env）注册为 ORCA supervised worker：
#   run-create（PM coordinator 绑 Run）→ task-create → worker-start --terminal --worktree
# 注册后 worker 出现在 worker-list，绑定 task + worktree resource，可被 send/reply/inbox + gate 管理。
#
# 前提（实测，references/12 §9 关键发现 4）：
#   - terminal 必须跑 recognized agent（claude/codex/opencode 等）；sleep/shell 被拒
#   - --worktree 必须匹配 terminal 所属 worktree
#
# 用法：
#   orca-supervised-register.sh \
#     --worktree-id "<repoId>::<path>" \
#     --terminal-handle "term_xxx" \
#     --task-spec "<任务描述>" \
#     [--task-title "<标题>"] [--run-id "<run_id>"] [--objective "<目标>"]
#
# 输出（stdout，KV 格式，供 spawn-worker eval）：
#   ORCAREG_RUN_ID=run_xxx
#   ORCAREG_TASK_ID=task_xxx
#   ORCAREG_DISPATCH_ID=ctx_xxx
#
# 退出码：0 成功；64 参数/前提错误；1 ORCA 调用失败。

set -euo pipefail

WORKTREE_ID=""
TERMINAL_HANDLE=""
TASK_SPEC=""
TASK_TITLE=""
RUN_ID=""
OBJECTIVE=""

usage() {
  cat >&2 <<'USAGE'
Usage:
  orca-supervised-register.sh --worktree-id ID --terminal-handle HANDLE --task-spec TEXT [options]

Required:
  --worktree-id ID         ORCA worktree id (format: <repoId>::<path>)
  --terminal-handle HANDLE ORCA terminal handle (term_xxx), must run a recognized agent
  --task-spec TEXT         Task spec / instruction for the supervised task

Optional:
  --task-title TEXT        Task title (default: "spawn-worker supervised worker")
  --run-id ID              Existing Run id (skip run-create; default: create new Run)
  --objective TEXT         Run objective (default: same as task-spec)
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --worktree-id) WORKTREE_ID="$2"; shift 2 ;;
    --terminal-handle) TERMINAL_HANDLE="$2"; shift 2 ;;
    --task-spec) TASK_SPEC="$2"; shift 2 ;;
    --task-title) TASK_TITLE="$2"; shift 2 ;;
    --run-id) RUN_ID="$2"; shift 2 ;;
    --objective) OBJECTIVE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage; exit 64 ;;
  esac
done

[ -n "$WORKTREE_ID" ] || { echo "ERROR: --worktree-id is required" >&2; exit 64; }
[ -n "$TERMINAL_HANDLE" ] || { echo "ERROR: --terminal-handle is required" >&2; exit 64; }
[ -n "$TASK_SPEC" ] || { echo "ERROR: --task-spec is required" >&2; exit 64; }
command -v orca >/dev/null 2>&1 || { echo "ERROR: orca CLI not found" >&2; exit 64; }
command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required" >&2; exit 64; }

[ -n "$TASK_TITLE" ] || TASK_TITLE="spawn-worker supervised worker"
[ -n "$OBJECTIVE" ] || OBJECTIVE="$TASK_SPEC"

# 1. run-create（如果没传 --run-id）
if [ -z "$RUN_ID" ]; then
  RUN_OUT=$(orca orchestration run-create --objective "$OBJECTIVE" --json 2>&1) || {
    echo "ERROR: run-create failed: $RUN_OUT" >&2; exit 1; }
  RUN_ID=$(printf '%s' "$RUN_OUT" | jq -r '.result.run.id // empty')
  [ -n "$RUN_ID" ] || { echo "ERROR: run-create response missing .result.run.id: $RUN_OUT" >&2; exit 1; }
  echo "ORCAREG_RUN_CREATED: $RUN_ID" >&2
fi

# 2. task-create
TASK_OUT=$(orca orchestration task-create --spec "$TASK_SPEC" --task-title "$TASK_TITLE" --run "$RUN_ID" --json 2>&1) || {
  echo "ERROR: task-create failed: $TASK_OUT" >&2; exit 1; }
TASK_ID=$(printf '%s' "$TASK_OUT" | jq -r '.result.task.id // empty')
[ -n "$TASK_ID" ] || { echo "ERROR: task-create response missing .result.task.id: $TASK_OUT" >&2; exit 1; }
echo "ORCAREG_TASK_CREATED: $TASK_ID" >&2

# 3. worker-start --terminal --worktree（把已有 agent terminal 纳入 supervised）
# ORCA runtime 两个已知行为（实测）：
#   (a) terminal 刚 create 时 runtime 注册有延迟，立即 worker-start 偶发 runtime_unavailable
#   (b) worker-start 返回 runtime_unavailable 时，server 端可能已成功建 dispatch（连接断在响应前）
# 所以：单次 worker-start（不 retry——retry 会触发 task_not_startable 把 worker 标 failed），
# 然后靠 worker-list 兜底查 task 的 dispatch（不管 worker-start 返回 ok 与否）。
echo "ORCAREG_WAIT_RUNTIME: sleep 6s 等 ORCA runtime 注册 terminal（worker-start timing）" >&2
sleep 6
WS_OUT=$(orca orchestration worker-start --task "$TASK_ID" --terminal "$TERMINAL_HANDLE" --worktree "id:$WORKTREE_ID" --run "$RUN_ID" --json 2>&1) || true
WS_OK=$(printf '%s' "$WS_OUT" | jq -r '.ok // false' 2>/dev/null)
echo "ORCAREG_WORKER_START: ok=${WS_OK}（false 不一定真失败，查 worker-list 兜底）" >&2
# sleep 让 server 端注册 dispatch（应对 runtime_unavailable 但 server 成功）
sleep 3
# worker-list 兜底查 task 的 dispatch（worker-start runtime_unavailable 时 server 端可能已建）
DISPATCH_ID=""
WORKER_STATE=""
for lookup in 1 2 3; do
  LIST_OUT=$(orca orchestration worker-list --json 2>/dev/null || echo '{}')
  DISPATCH_ID=$(printf '%s' "$LIST_OUT" | jq -r --arg t "$TASK_ID" '.result.workers[]? | select(.taskId==$t) | .dispatchId // empty')
  WORKER_STATE=$(printf '%s' "$LIST_OUT" | jq -r --arg t "$TASK_ID" '.result.workers[]? | select(.taskId==$t) | .workerState // empty')
  [ -n "$DISPATCH_ID" ] && break
  sleep 2
done
if [ -z "$DISPATCH_ID" ]; then
  echo "ERROR: worker-start 失败且 worker-list 无 dispatch: $WS_OUT" >&2; exit 1; fi
echo "ORCAREG_WORKER_REGISTERED: dispatch=$DISPATCH_ID workerState=$WORKER_STATE (worker-start ok=$WS_OK)" >&2

# stdout KV（spawn-worker eval 捕获）
echo "ORCAREG_RUN_ID=$RUN_ID"
echo "ORCAREG_TASK_ID=$TASK_ID"
echo "ORCAREG_DISPATCH_ID=$DISPATCH_ID"
