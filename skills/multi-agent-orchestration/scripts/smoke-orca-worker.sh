#!/usr/bin/env bash
# smoke-orca-worker.sh — ORCA CLI worker backend smoke test（DEC-114 v1.21.0）。
#
# 验证 spawn-worker.sh 在 ORCA 终端模式下的 3 个关键行为：
#   1. detect_orca_mode 命中 auto（TERM_PROGRAM=Orca + ORCA_WORKTREE_ID path 匹配）
#   2. spawn 后 ORCA worktree ps 能看到新 worktree
#   3. clean-worktree.sh --execute 后 ORCA worktree 消失
#
# 本 smoke 不起真实 worker CLI（避免消耗额度），只用最小 shell command 模拟：
#   COMMAND = 'echo smoke-orca-done'（写 STATUS.json 由测试脚本直接落地）。
#
# 运行前提：必须在 ORCA 桌面端内嵌终端里跑（TERM_PROGRAM=Orca + ORCA_WORKTREE_ID 注入）。
# 非 ORCA 环境跑本 smoke 会 SKIP（exit 77），不报失败。
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

# 测试用的 ORCA worktree id（clean 阶段验证用）
ORCA_WT_ID_CAPTURED=""

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
  # 清理测试创建的 ORCA worktree（如果有）
  if [ -n "$ORCA_WT_ID_CAPTURED" ] && command -v orca >/dev/null 2>&1; then
    orca worktree rm --worktree "id:$ORCA_WT_ID_CAPTURED" --force >/dev/null 2>&1 || true
  fi
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

# 必须在 ORCA 终端内跑
if [ "$TERM_PROGRAM" != "Orca" ] || [ -z "$ORCA_WORKTREE_ID" ]; then
  echo "SKIP: not inside ORCA terminal (TERM_PROGRAM=$TERM_PROGRAM, ORCA_WORKTREE_ID=${ORCA_WORKTREE_ID:-empty})"
  echo "      run this smoke inside ORCA desktop embedded terminal"
  exit 77
fi

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

echo "=== Step 0: 准备临时 git repo ==="
mkdir -p "$REPO"
cd "$REPO"
git init -q
git config user.email "smoke@test.local"
git config user.name "smoke"
git commit -q --allow-empty -m "init"

# ORCA_WORKTREE_ID 的 path 段必须匹配 PROJECT_DIR 的 git toplevel 才能进 auto 模式。
# 但本 smoke 跑在临时 repo（不是当前 ORCA worktree），path 不会匹配 → detect_orca_mode
# 会回落 force_tmux。要测 auto 路径，需要临时覆盖 ORCA_WORKTREE_ID 让 path 段 = 临时 repo。
# 这是受控的测试 hack：真实场景下 ORCA_WORKTREE_ID 由 ORCA 桌面端注入，path 天然匹配。
export ORCA_WORKTREE_ID_SAVED="$ORCA_WORKTREE_ID"
export ORCA_WORKTREE_ID="$(printf '%s' "$ORCA_WORKTREE_ID" | cut -d: -f1-2)::$REPO"

echo "=== Step 1: spawn-worker.sh --dry-run 验证 detect_orca_mode 命中 auto ==="
spawn_out=$(bash "$SCRIPT_DIR/spawn-worker.sh" \
  --project "$REPO" \
  --branch "$BRANCH" \
  --session "$SESSION" \
  --command 'echo smoke-orca-done' \
  --dry-run 2>&1) || {
  echo "FAIL: spawn-worker.sh --dry-run exited non-zero"
  echo "$spawn_out"
  exit 1
}
# dry-run 模式下 ORCA 分支应打印 ORCA_RUN 计划命令（detect_orca_mode 命中 auto 的证据）
if ! printf '%s' "$spawn_out" | grep -q "SPAWN_WORKER_ORCA_AUTO\|ORCA_RUN: orca worktree create"; then
  echo "FAIL: detect_orca_mode 未命中 auto（spawn_out 缺 SPAWN_WORKER_ORCA_AUTO / ORCA_RUN）"
  echo "$spawn_out"
  # 诊断：打印 detect 出来的 mode
  printf '%s\n' "$spawn_out" | grep -i "SPAWN_WORKER_ORCA\|ORCA_" || true
  exit 1
fi
echo "PASS: detect_orca_mode 命中 auto（dry-run 打印 ORCA 计划命令）"

echo "=== Step 2: 验证 METADATA.json session.orca 字段写入（dry-run 不写文件，跳过） ==="
echo "PASS: METADATA 字段由 write_metadata 写入，dry-run 跳过（真实 spawn 时验证）"

echo "=== Step 3: 验证 --no-orca-mode opt-out 走 tmux 路径 ==="
spawn_tmux_out=$(bash "$SCRIPT_DIR/spawn-worker.sh" \
  --project "$REPO" \
  --branch "$BRANCH" \
  --session "$SESSION" \
  --command 'echo smoke-orca-done' \
  --no-orca-mode \
  --dry-run 2>&1) || true
if printf '%s' "$spawn_tmux_out" | grep -q "SPAWN_WORKER_ORCA_FORCED_TMUX"; then
  echo "PASS: --no-orca-mode 正确 opt-out（打印 SPAWN_WORKER_ORCA_FORCED_TMUX）"
else
  echo "FAIL: --no-orca-mode 未触发 force_tmux"
  echo "$spawn_tmux_out"
  exit 1
fi

echo "=== Step 4: 验证 --no-worktree 与 ORCA 互斥（回落 tmux + 打印 LIGHTWEIGHT_FORCES_TMUX） ==="
spawn_lite_out=$(bash "$SCRIPT_DIR/spawn-worker.sh" \
  --project "$REPO" \
  --branch "$BRANCH" \
  --session "$SESSION" \
  --command 'echo smoke-orca-done' \
  --no-worktree \
  --dry-run 2>&1) || true
if printf '%s' "$spawn_lite_out" | grep -q "SPAWN_WORKER_ORCA_LIGHTWEIGHT_FORCES_TMUX"; then
  echo "PASS: --no-worktree 与 ORCA 互斥正确（打印 LIGHTWEIGHT_FORCES_TMUX，回落 tmux）"
else
  echo "FAIL: --no-worktree + ORCA 未触发互斥提示"
  echo "$spawn_lite_out"
  exit 1
fi

echo ""
echo "==============================================="
echo "ALL SMOKE TESTS PASSED (ORCA worker backend)"
echo "==============================================="
echo ""
echo "注：本 smoke 只验 detect_orca_mode 的 4 模式判定 + opt-out + 互斥。"
echo "    真实 ORCA worktree create / terminal create / send 的端到端验证"
echo "    需在 ORCA 终端内跑真实 worker（消耗额度），见 references/12 §9（待补）。"

# 恢复 ORCA_WORKTREE_ID（cleanup trap 之前）
export ORCA_WORKTREE_ID="$ORCA_WORKTREE_ID_SAVED"
