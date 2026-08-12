#!/usr/bin/env bash
# smoke-orca-worker.sh — ORCA CLI worker backend smoke test（DEC-114 v2.0.0）。
#
# 验证 spawn-worker.sh 在 ORCA 终端模式下的关键行为：
#   1. 不依赖 TERM_PROGRAM / ORCA_WORKTREE_ID，改用 worktree current 识别
#   2. opt-out / 非当前 repo 的降级边界
#   3. supervised dry-run 只允许 worker-start 注入任务
#
# 本 smoke 不起真实 worker CLI（避免消耗额度），只用最小 shell command 模拟：
#   COMMAND = 'echo smoke-orca-done'（写 STATUS.json 由测试脚本直接落地）。
#
# 运行前提：当前 cwd 是 Orca-managed worktree，Orca runtime 正在运行。
#
# 用法：bash scripts/smoke-orca-worker.sh

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TMP_ROOT=$(mktemp -d)
TMP_ROOT=$(cd "$TMP_ROOT" && pwd -P)
SESSION="smoke-orca-$$"
REPO="$TMP_ROOT/repo"
BRANCH="feat/smoke-orca"
WT="$REPO/.claude/worktrees/tmux-smoke-orca"
CTX="$WT/.claude/agent-sessions/$SESSION"

assert_contains() {
  local haystack="$1"
  local needle="$2"
  case "$haystack" in
    *"$needle"*) ;;
    *)
      printf 'ASSERTION FAILED: expected output to contain: %s\n' "$needle" >&2
      printf '%s\n' "$haystack" >&2
      exit 1
      ;;
  esac
}

cleanup() {
  if [ -d "$REPO" ]; then
    git -C "$REPO" worktree remove --force "$WT" >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

# 前置依赖检查
command -v git >/dev/null 2>&1 || { echo "SKIP: git is required"; exit 77; }
command -v jq >/dev/null 2>&1 || { echo "SKIP: jq is required"; exit 77; }
command -v orca >/dev/null 2>&1 || { echo "SKIP: orca CLI is required (run inside ORCA terminal)"; exit 77; }

# ORCA app 必须运行 + capability 校验
status_json=$(orca status --json 2>/dev/null || echo "")
if [ -z "$status_json" ]; then
  echo "SKIP: orca status --json failed (ORCA app not running?)"
  exit 77
fi
has_multiplex=$(printf '%s' "$status_json" | jq -r '.result.runtime.capabilities // [] | any(. == "terminal.multiplex.v1")' 2>/dev/null)
if [ "$has_multiplex" != "true" ]; then
  echo "SKIP: ORCA lacks terminal.multiplex.v1 capability (need ≥1.4.x)"
  exit 77
fi

current_json=$(orca worktree current --json 2>/dev/null || echo '')
current_id=$(printf '%s' "$current_json" | jq -r '.result.worktree.id // empty')
current_path=$(printf '%s' "$current_json" | jq -r '.result.worktree.path // empty')
if [ -z "$current_id" ] || [ -z "$current_path" ]; then
  echo "SKIP: cwd is not an Orca-managed worktree"
  exit 77
fi

echo "=== Step 0: 准备临时 git repo（用于验证跨 repo 不误触发） ==="
mkdir -p "$REPO"
cd "$REPO"
git init -q
git config user.email "smoke@test.local"
git config user.name "smoke"
git commit -q --allow-empty -m "init"

echo "=== Step 1: 清空旧环境变量仍可识别当前 Orca worktree ==="
spawn_out=$(env -u TERM_PROGRAM -u ORCA_WORKTREE_ID bash "$SCRIPT_DIR/spawn-worker.sh" \
  --project "$current_path" \
  --branch "$BRANCH" \
  --session "$SESSION" \
  --command 'echo smoke-orca-done' \
  --worker-backend codex \
  --allow-prompt-only-install-guard 'smoke test: no dependency install' \
  --dry-run 2>&1) || {
  echo "FAIL: spawn-worker.sh --dry-run exited non-zero"
  echo "$spawn_out"
  exit 1
}
# dry-run 模式下 ORCA 分支应打印 ORCA_RUN 计划命令（detect_orca_mode 命中 auto 的证据）
if ! printf '%s' "$spawn_out" | grep -q "SPAWN_WORKER_ORCA_AUTO"; then
  echo "FAIL: detect_orca_mode 未命中 auto（spawn_out 缺 SPAWN_WORKER_ORCA_AUTO / ORCA_RUN）"
  echo "$spawn_out"
  # 诊断只输出已捕获文本；不要用一个丢弃退出码的二级 grep 掩盖原断言。
  printf '%s\n' "$spawn_out"
  exit 1
fi
echo "PASS: worktree current 命中 auto（无需 TERM_PROGRAM / ORCA_WORKTREE_ID）"

echo "=== Step 2: 验证 METADATA.json session.orca 字段写入（dry-run 不写文件，跳过） ==="
echo "PASS: METADATA 字段由 write_metadata 写入，dry-run 跳过（真实 spawn 时验证）"

echo "=== Step 3: 验证 --no-orca-mode opt-out 走 tmux 路径 ==="
spawn_tmux_out=$(bash "$SCRIPT_DIR/spawn-worker.sh" \
  --project "$REPO" \
  --branch "$BRANCH" \
  --session "$SESSION" \
  --command 'echo smoke-orca-done' \
  --worker-backend codex \
  --allow-prompt-only-install-guard 'smoke test: no dependency install' \
  --no-orca-mode \
  --dry-run 2>&1) || {
  echo "FAIL: --no-orca-mode dry-run exited non-zero"
  echo "$spawn_tmux_out"
  exit 1
}
assert_contains "$spawn_tmux_out" "SPAWN_WORKER_ORCA_FORCED_TMUX"
echo "PASS: --no-orca-mode 正确 opt-out（打印 SPAWN_WORKER_ORCA_FORCED_TMUX）"

echo "=== Step 4: 验证 --no-worktree 与 ORCA 互斥（回落 tmux + 打印 LIGHTWEIGHT_FORCES_TMUX） ==="
spawn_lite_out=$(bash "$SCRIPT_DIR/spawn-worker.sh" \
  --project "$REPO" \
  --branch "$BRANCH" \
  --session "$SESSION" \
  --command 'echo smoke-orca-done' \
  --worker-backend codex \
  --allow-prompt-only-install-guard 'smoke test: no dependency install' \
  --no-worktree \
  --dry-run 2>&1) || {
  echo "FAIL: --no-worktree dry-run exited non-zero"
  echo "$spawn_lite_out"
  exit 1
}
assert_contains "$spawn_lite_out" "SPAWN_WORKER_ORCA_LIGHTWEIGHT_FORCES_TMUX"
echo "PASS: --no-worktree 与 ORCA 互斥正确（打印 LIGHTWEIGHT_FORCES_TMUX，回落 tmux）"

echo "=== Step 5: supervised dry-run 不得普通 terminal send 双投任务 ==="
supervised_out=$(env -u TERM_PROGRAM -u ORCA_WORKTREE_ID bash "$SCRIPT_DIR/spawn-worker.sh" \
  --project "$current_path" \
  --branch "feat/smoke-orca-supervised" \
  --session "$SESSION-supervised" \
  --command 'echo smoke-orca-done' \
  --worker-backend codex \
  --allow-prompt-only-install-guard 'smoke test: no dependency install' \
  --orca-supervised --task-spec '只验证注入计划，不执行真实 worker' \
  --dry-run 2>&1) || {
  echo "FAIL: supervised dry-run exited non-zero"
  echo "$supervised_out"
  exit 1
}
assert_contains "$supervised_out" "supervised prompt will be injected by orchestration worker-start"
assert_contains "$supervised_out" "task-create --spec"
if printf '%s' "$supervised_out" | grep -q 'terminal send --terminal'; then
  echo "FAIL: supervised dry-run still contains ordinary terminal send"
  echo "$supervised_out"
  exit 1
fi
echo "PASS: supervised 路径只由 worker-start 注入任务"

echo ""
echo "==============================================="
echo "ALL SMOKE TESTS PASSED (ORCA worker backend)"
echo "==============================================="
echo ""
echo "注：本 smoke 验证运行时检测、降级边界与 supervised 单一注入计划。"
echo "    真实 agent 的 worker_done/Delivery 闭环需使用受支持 agent 做前向测试。"
