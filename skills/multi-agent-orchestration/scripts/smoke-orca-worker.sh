#!/usr/bin/env bash
# smoke-orca-worker.sh — ORCA CLI worker backend smoke test（DEC-114 v2.0.0）。
#
# 验证 spawn-worker.sh 在 ORCA 终端模式下的关键行为：
#   1. 不依赖 TERM_PROGRAM / ORCA_WORKTREE_ID，改用 worktree current 识别
#   2. opt-out / 非当前 repo 的降级边界
#   3. supervised dry-run 缺少/错误 sender 时在资源计划前拒绝
#
# 本 smoke 不起真实 worker CLI（避免消耗额度），但命令仍使用 `codex`
# 令牌通过 backend/command 身份门禁；只读 CLI 代理额外阻断一切 mutation。
# 正向 single-worker 注入/Wave reuse 由 test-spawn-worker-orca.sh 隔离验证。
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

# 真 CLI 只读代理，不伪造 runtime/terminal/Run 回执；任何非白名单调用都不能落到真实 Orca。
export SMOKE_REAL_ORCA_BIN="$(command -v orca)"
export SMOKE_ORCA_LOG="$TMP_ROOT/orca-readonly.log"
export ORCA_CLI_COMMAND="$TMP_ROOT/orca-readonly"
unset ORCA_CLI_BIN
cat > "$ORCA_CLI_COMMAND" <<'READONLY'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$SMOKE_ORCA_LOG"
case "$*" in
  'status --json'|'worktree current --json'|'worktree ps --limit 100 --json') ;;
  *)
    if [ "$#" -ne 5 ] || [ "$1 $2 $3" != 'terminal show --terminal' ] || [ "$5" != --json ]; then
      echo READONLY_GUARD_BLOCKED >> "$SMOKE_ORCA_LOG"
      echo "READONLY_GUARD_BLOCKED: $*" >&2
      exit 95
    fi ;;
esac
exec "$SMOKE_REAL_ORCA_BIN" "$@"
READONLY
chmod +x "$ORCA_CLI_COMMAND"
# 本 smoke 只检查 runtime/身份边界；显式关闭内存/个人配额前门，确保抵达目标分支。
export SPAWN_WORKER_MEM_BUDGET_BYTES=0
export MULTI_AGENT_ORCHESTRATION_PERSONAL_CONFIG="$TMP_ROOT/personal-quota-disabled.json"
printf '%s\n' '{"quota_aware_routing":{"enabled":false}}' > "$MULTI_AGENT_ORCHESTRATION_PERSONAL_CONFIG"

# ORCA app 必须运行 + capability 校验
status_json=$("$ORCA_CLI_COMMAND" status --json 2>/dev/null || echo "")
if [ -z "$status_json" ]; then
  echo "SKIP: orca status --json failed (ORCA app not running?)"
  exit 77
fi
has_multiplex=$(printf '%s' "$status_json" | jq -r '.result.runtime.capabilities // [] | any(. == "terminal.multiplex.v1")' 2>/dev/null)
if [ "$has_multiplex" != "true" ]; then
  echo "SKIP: ORCA lacks terminal.multiplex.v1 capability (need ≥1.4.x)"
  exit 77
fi

current_json=$("$ORCA_CLI_COMMAND" worktree current --json 2>/dev/null || echo '')
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
  --command 'codex' \
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
echo "NOT_VERIFIED: 本只读 smoke 不验证 METADATA 写入；由隔离 spawn/metadata 套件负责"

echo "=== Step 3: 验证 --no-orca-mode opt-out 走 tmux 路径 ==="
spawn_tmux_out=$(bash "$SCRIPT_DIR/spawn-worker.sh" \
  --project "$REPO" \
  --branch "$BRANCH" \
  --session "$SESSION" \
  --command 'codex' \
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
  --command 'codex' \
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

echo "=== Step 5: 无 sender 的 supervised dry-run 在资源计划前拒绝 ==="
supervised_rc=0
supervised_out=$(env -u TERM_PROGRAM -u ORCA_WORKTREE_ID -u ORCA_TERMINAL_HANDLE bash "$SCRIPT_DIR/spawn-worker.sh" \
  --project "$current_path" \
  --branch "feat/smoke-orca-supervised" \
  --session "$SESSION-supervised" \
  --command 'codex' \
  --worker-backend codex \
  --allow-prompt-only-install-guard 'smoke test: no dependency install' \
  --orca-supervised --task-spec '只验证 sender 拒绝，不执行真实 worker' \
  --dry-run 2>&1) || supervised_rc=$?
if [ "$supervised_rc" -ne 3 ]; then
  echo "FAIL: missing sender expected exit 3, got $supervised_rc"
  echo "$supervised_out"
  exit 1
fi
assert_contains "$supervised_out" "ORCA_COORDINATOR_MISSING: provide --from / --orca-coordinator-handle"
if printf '%s' "$supervised_out" | grep -Eq 'ORCA_RUN:.*(worktree create|terminal create|worker-start)'; then
  echo "FAIL: missing sender reached worker resource plan"
  exit 1
fi
echo "PASS: 缺 sender 精确拒绝，未到 worker 资源计划"

echo "=== Step 6: 虚构 sender 不能冒充有效 Wave receipt ==="
wave_rc=0
invalid_sender="term-smoke-pm-$SESSION"
wave_out=$(env -u TERM_PROGRAM -u ORCA_WORKTREE_ID -u ORCA_TERMINAL_HANDLE bash "$SCRIPT_DIR/spawn-worker.sh" \
  --project "$current_path" \
  --branch "feat/smoke-orca-wave" \
  --session "$SESSION-wave" \
  --command 'codex' \
  --worker-backend codex \
  --allow-prompt-only-install-guard 'smoke test: no dependency install' \
  --orca-supervised --orca-run-id run-smoke --orca-task-id task-smoke \
  --orca-coordinator-handle "$invalid_sender" \
  --dry-run 2>&1) || wave_rc=$?
if [ "$wave_rc" -ne 3 ]; then
  echo "FAIL: invalid sender expected exit 3, got $wave_rc"
  echo "$wave_out"
  exit 1
fi
assert_contains "$wave_out" "ORCA_COORDINATOR_UNVERIFIED: terminal show failed for the selected sender"
grep -qx "terminal show --terminal $invalid_sender --json" "$SMOKE_ORCA_LOG" || {
  echo "FAIL: invalid sender did not reach the exact readonly terminal probe"; exit 1;
}
if printf '%s' "$wave_out" | grep -Eq 'ORCA_RUN:.*(worktree create|terminal create|worker-start)'; then
  echo "FAIL: invalid sender reached worker resource plan"; exit 1
fi
if grep -Eq 'READONLY_GUARD_BLOCKED|^(repo add|worktree create|terminal create|orchestration )' "$SMOKE_ORCA_LOG"; then
  echo "FAIL: smoke attempted a non-readonly Orca call"; exit 1
fi
for suffix in supervised wave; do
  [ ! -e "$current_path/.claude/agent-sessions/$SESSION-$suffix" ] || {
    echo "FAIL: refused sender created a Session Context"; exit 1;
  }
done
echo "PASS: 精确只读探测拒绝错误 sender；零 Orca mutation / Session Context"
printf 'SMOKE_SENDER_REFUSAL: missing_exit=%s invalid_exit=%s\n' "$supervised_rc" "$wave_rc"
printf '%s\n' "$supervised_out" "$wave_out" | sed -n '/^ORCA_COORDINATOR_/p'
echo "SMOKE_ACTUAL_READONLY_ARGV (count + exact argv):"
sort "$SMOKE_ORCA_LOG" | uniq -c

echo ""
echo "==============================================="
echo "ALL SMOKE TESTS PASSED (ORCA worker backend)"
echo "==============================================="
echo ""
echo "注：本 smoke 验证运行时检测、降级边界与 sender 拒绝；未创建真实 Run/worker/provider。"
echo "    正向单一注入与 Wave reuse 由隔离 test-spawn-worker-orca.sh 负责。"
echo "    真实 agent 的 worker_done/Delivery 闭环需使用受支持 agent 做前向测试。"
