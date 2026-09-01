#!/usr/bin/env bash
# test-orca-auto-register.sh — Orca 仓库自动注册（selector_not_found → repo add → 复验）
# 的确定性 mocked 回归测试。不依赖也不改动真实 Orca 状态：CLI 由 ORCA_CLI_COMMAND
# 指向 fake 二进制，按环境变量 + state 文件返回 canned 响应。
#
# 覆盖（2026-09-01 custom-skills 实测事故 + PM 合同）：
#   1. success（未注册 → repo add → 复验 → auto；含 CLI 非零退出仍带错误合同的形态）
#   2. already registered（不调 repo add）
#   3. runtime down（无 JSON / status 不可达，均不注册）
#   4. non-Git（零 CLI 调用）
#   5. wrong error code（非 selector_not_found 不注册）
#   6. repo add failure（fail-closed 回退 tmux，不二次探测）
#   7. post-add path mismatch（复验失败回退 tmux，不进入 Orca 分支）
#   8. --no-orca-mode / DRY_RUN / path_mismatch（永不注册）
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CASE_ROOT=$(mktemp -d)
CASE_ROOT=$(cd "$CASE_ROOT" && pwd -P)
trap 'rm -rf "$CASE_ROOT"' EXIT

command -v git >/dev/null 2>&1 || { echo "SKIP: git is required"; exit 77; }
command -v jq >/dev/null 2>&1 || { echo "SKIP: jq is required"; exit 77; }

PROJECT_REPO="$CASE_ROOT/business repo"
NON_GIT_PROJECT="$CASE_ROOT/non-git project"
mkdir -p "$PROJECT_REPO" "$NON_GIT_PROJECT"
git -C "$PROJECT_REPO" init -q
git -C "$PROJECT_REPO" config user.email "orca-reg@test.local"
git -C "$PROJECT_REPO" config user.name "orca-reg-test"
git -C "$PROJECT_REPO" commit -q --allow-empty -m init

FAKE_ORCA_BIN="$CASE_ROOT/fake-orca"
FAKE_ORCA_STATE="$CASE_ROOT/fake-orca-state"
FAKE_ORCA_LOG="$CASE_ROOT/fake-orca-calls.log"
export FAKE_ORCA_BIN FAKE_ORCA_STATE FAKE_ORCA_LOG

# fake orca CLI：worktree current 由 $FAKE_ORCA_STATE/registered 状态文件翻转；
# 未注册时输出 $FAKE_CURRENT_ERROR_JSON 并按 $FAKE_CURRENT_RC 退出（真实 CLI 的
# 退出码合同未公开，两种形态都必须能被解析）。
cat > "$FAKE_ORCA_BIN" <<'SH'
#!/usr/bin/env bash
state="${FAKE_ORCA_STATE:?}"
printf '%s\n' "$*" >> "${FAKE_ORCA_LOG:?}"
case "$1 $2" in
  "status --json")
    [ "${FAKE_STATUS_FAIL:-0}" = "1" ] && exit 1
    printf '%s\n' '{"result":{"runtime":{"appVersion":"1.4.194","capabilities":["terminal.multiplex.v1","orchestration.contract.v1"]}}}'
    ;;
  "worktree current")
    if [ -f "$state/registered" ]; then
      path="${FAKE_POST_ADD_PATH:-${FAKE_PROJECT_TOP:?}}"
      id="${FAKE_WORKTREE_ID:-repo-1::$path}"
      jq -cn --arg id "$id" --arg path "$path" '{ok:true,result:{worktree:{id:$id,path:$path}}}'
    else
      printf '%s\n' "${FAKE_CURRENT_ERROR_JSON:?}"
      exit "${FAKE_CURRENT_RC:-1}"
    fi
    ;;
  "repo add")
    [ "${FAKE_REPO_ADD_FAIL:-0}" = "1" ] && { echo "ERROR: repo add mutation failed" >&2; exit 1; }
    touch "$state/registered"
    add_json="${FAKE_REPO_ADD_JSON:-}"
    [ -n "$add_json" ] || add_json='{"ok":true,"result":{"repo":{"id":"repo-1"}}}'
    printf '%s\n' "$add_json"
    ;;
  *) exit 1 ;;
esac
SH
chmod +x "$FAKE_ORCA_BIN"

# shellcheck source=orca-runtime.sh
source "$SCRIPT_DIR/orca-runtime.sh"
# shellcheck source=spawn-worker-orca.sh
source "$SCRIPT_DIR/spawn-worker-orca.sh"

command -v orca_runtime_register_current_project >/dev/null 2>&1 \
  || { echo "FAIL: orca-runtime.sh 缺少 orca_runtime_register_current_project"; exit 1; }

passed=0
failed=0
ok()  { printf 'PASS: %s\n' "$1"; passed=$((passed + 1)); }
bad() { printf 'FAIL: %s\n' "$1" >&2; failed=$((failed + 1)); }
assert_eq() {
  local actual="$1" expected="$2" label="$3"
  if [ "$actual" = "$expected" ]; then ok "$label"; else bad "$label (expected=$expected actual=$actual)"; fi
}
assert_log_has() { grep -Fq -- "$1" "$FAKE_ORCA_LOG" && ok "$2" || bad "$2"; }
assert_log_lacks() { grep -Fq -- "$1" "$FAKE_ORCA_LOG" && bad "$2" || ok "$2"; }
assert_err_has()  { grep -Fq -- "$1" "$ERR_FILE" && ok "$2" || bad "$2"; }
assert_err_lacks() { grep -Fq -- "$1" "$ERR_FILE" && bad "$2" || ok "$2"; }

ERR_FILE="$CASE_ROOT/detect.err"
SELECTOR_JSON=$(jq -cn '{ok:false,error:{code:"selector_not_found"}}')
OTHER_CODE_JSON=$(jq -cn '{ok:false,error:{code:"runtime_unavailable"}}')

reset_case() {
  rm -rf "$FAKE_ORCA_STATE"; mkdir -p "$FAKE_ORCA_STATE"
  : > "$FAKE_ORCA_LOG"; : > "$ERR_FILE"
  PROJECT_DIR="$PROJECT_REPO"
  LIGHTWEIGHT_MODE=0
  NO_ORCA_MODE=0
  DRY_RUN=0
  ORCA_SUPERVISED=0
  ORCA_MODE=""
  ORCA_WORKTREE_ID=""
  ORCA_WORKTREE_PATH=""
  ORCA_PROJECT_TOPLEVEL=""
  ORCA_EXPECTED_REPO_ID=""
  ORCA_APP_VERSION=""
  ORCA_CAPABILITIES_JSON=""
  ORCA_CURRENT_WORKTREE_JSON=""
  ORCA_CURRENT_WORKTREE_ID=""
  ORCA_CURRENT_WORKTREE_PATH=""
  ORCA_WORKTREE_CURRENT_ERROR=""
  ORCA_CLI_BIN=""
  ORCA_CLI_COMMAND="$FAKE_ORCA_BIN"
  unset TERM_PROGRAM || true
  export FAKE_PROJECT_TOP="$PROJECT_REPO"
  export FAKE_CURRENT_ERROR_JSON="$SELECTOR_JSON"
  export FAKE_CURRENT_RC=1
  export FAKE_STATUS_FAIL=0
  export FAKE_REPO_ADD_FAIL=0
  export FAKE_REPO_ADD_JSON='{"ok":true,"result":{"repo":{"id":"repo-1"}}}'
  export FAKE_POST_ADD_PATH="$PROJECT_REPO"
  export FAKE_WORKTREE_ID="repo-1::$PROJECT_REPO"
}

run_detect() { detect_orca_mode >/dev/null 2> "$ERR_FILE" || true; }
current_call_count() { grep -c '^worktree current --json$' "$FAKE_ORCA_LOG" || true; }

# --- 1a. success：未注册（错误合同 + CLI 非零退出）→ repo add → 复验 → auto ---
reset_case
run_detect
assert_eq "$ORCA_MODE" "auto" "success(rc=1): unregistered repo auto-registers into Orca mode"
assert_eq "$ORCA_WORKTREE_PATH" "$PROJECT_REPO" "success(rc=1): verified toplevel becomes ORCA_WORKTREE_PATH"
assert_eq "$ORCA_EXPECTED_REPO_ID" "repo-1" "success(rc=1): repo identity frozen from re-verified worktree id"
assert_eq "$ORCA_APP_VERSION" "1.4.194" "success(rc=1): status capability gate still runs after registration"
assert_log_has "repo add --path $PROJECT_REPO --json" "success(rc=1): repo add targets the exact canonical Git top"
assert_err_has "SPAWN_WORKER_ORCA_AUTO_REGISTER:" "success(rc=1): registration announces the mutation before it happens"
assert_err_has "SPAWN_WORKER_ORCA_AUTO:" "success(rc=1): auto mode confirmed after re-verification"
assert_eq "$(current_call_count)" "2" "success(rc=1): worktree current probed before and after repo add"
cur1=$(grep -n '^worktree current --json$' "$FAKE_ORCA_LOG" | head -1 | cut -d: -f1)
add=$(grep -n '^repo add' "$FAKE_ORCA_LOG" | head -1 | cut -d: -f1)
if [ -n "$cur1" ] && [ -n "$add" ] && [ "$cur1" -lt "$add" ]; then
  ok "success(rc=1): probe precedes repo add (no blind mutation)"
else
  bad "success(rc=1): probe precedes repo add (no blind mutation)"
fi

# --- 1b. success（rc=0 + ok:false 合同）：错误码仍可解析，注册复验成功 ---
reset_case
export FAKE_CURRENT_RC=0
run_detect
assert_eq "$ORCA_MODE" "auto" "success(rc=0): zero-exit error contract still registers and verifies"
assert_log_has "repo add --path $PROJECT_REPO --json" "success(rc=0): repo add invoked exactly for this repo"

# --- 2. already registered：worktree current 直接命中，repo add 永不调用 ---
reset_case
touch "$FAKE_ORCA_STATE/registered"
run_detect
assert_eq "$ORCA_MODE" "auto" "already-registered: current Orca behavior preserved"
assert_log_lacks "repo add" "already-registered: repo add is never called for a known repo"

# --- 3a. runtime down（无 JSON 输出）：不注册，静默回退 tmux ---
reset_case
export FAKE_CURRENT_ERROR_JSON="" FAKE_CURRENT_RC=1
run_detect
assert_eq "$ORCA_MODE" "force_tmux" "runtime-down(no json): falls back to tmux"
assert_log_lacks "repo add" "runtime-down(no json): no mutation without a structured error code"
assert_eq "$(current_call_count)" "1" "runtime-down(no json): single probe only"

# --- 3b. runtime down（selector 错误但 status 不可达）：跳过注册并给出诊断 ---
reset_case
export FAKE_STATUS_FAIL=1
run_detect
assert_eq "$ORCA_MODE" "force_tmux" "runtime-down(status): falls back to tmux"
assert_log_lacks "repo add" "runtime-down(status): unreachable runtime never mutates Orca state"
assert_err_has "SPAWN_WORKER_ORCA_AUTO_REGISTER_SKIPPED" "runtime-down(status): skip reason is reported"
assert_err_lacks "SPAWN_WORKER_ORCA_AUTO:" "runtime-down(status): never pretends Orca management succeeded"

# --- 4. non-Git：零 CLI 调用，回退 tmux ---
reset_case
PROJECT_DIR="$NON_GIT_PROJECT"
run_detect
assert_eq "$ORCA_MODE" "force_tmux" "non-Git: falls back to tmux"
if [ -s "$FAKE_ORCA_LOG" ]; then bad "non-Git: zero Orca CLI calls"; else ok "non-Git: zero Orca CLI calls"; fi

# --- 5. wrong error code：非 selector_not_found 一律不注册 ---
reset_case
export FAKE_CURRENT_ERROR_JSON="$OTHER_CODE_JSON"
run_detect
assert_eq "$ORCA_MODE" "force_tmux" "wrong-code: other structured errors fall back to tmux"
assert_log_lacks "repo add" "wrong-code: repo add restricted to selector_not_found"
assert_eq "$(current_call_count)" "1" "wrong-code: single probe only"

# --- 6. repo add failure：fail-closed，不二次探测，不进入 Orca 分支 ---
reset_case
export FAKE_REPO_ADD_FAIL=1
run_detect
assert_eq "$ORCA_MODE" "force_tmux" "repo-add-failure: falls back to tmux before any side effect"
assert_log_has "repo add" "repo-add-failure: registration was attempted exactly once"
assert_eq "$(current_call_count)" "1" "repo-add-failure: no re-probe after failed add"
assert_err_has "orca repo add 失败" "repo-add-failure: failure diagnostic is explicit"
assert_err_lacks "SPAWN_WORKER_ORCA_AUTO:" "repo-add-failure: never claims Orca mode"

# --- 7. post-add path mismatch：复验失败，fail-closed 回退 tmux ---
reset_case
export FAKE_POST_ADD_PATH="$CASE_ROOT/other place"
run_detect
assert_eq "$ORCA_MODE" "force_tmux" "post-add-mismatch: exact path re-verification gates Orca mode"
assert_eq "$(current_call_count)" "2" "post-add-mismatch: re-probe ran after repo add"
assert_err_has "复验失败" "post-add-mismatch: re-verification failure is reported"
assert_err_lacks "SPAWN_WORKER_ORCA_AUTO:" "post-add-mismatch: never claims Orca mode"

# --- 8a. --no-orca-mode：显式 opt-out，零 CLI 调用 ---
reset_case
NO_ORCA_MODE=1
run_detect
assert_eq "$ORCA_MODE" "force_tmux" "no-orca-mode: explicit opt-out preserved"
if [ -s "$FAKE_ORCA_LOG" ]; then bad "no-orca-mode: zero Orca CLI calls"; else ok "no-orca-mode: zero Orca CLI calls"; fi

# --- 8b. DRY_RUN：只打印注册计划，不执行 mutation，fail-closed 回退 tmux ---
reset_case
DRY_RUN=1
run_detect
assert_eq "$ORCA_MODE" "force_tmux" "dry-run: no mutation without verification, falls back to tmux"
assert_log_lacks "repo add" "dry-run: repo add is never executed"
assert_err_has "ORCA_RUN: orca repo add --path" "dry-run: registration plan is printed instead"

# --- 8c. path_mismatch（已注册到别的路径）：绝不触发注册 ---
reset_case
touch "$FAKE_ORCA_STATE/registered"
export FAKE_POST_ADD_PATH="$CASE_ROOT/other place"
run_detect
assert_eq "$ORCA_MODE" "force_tmux" "path-mismatch: cross-project mismatch stays tmux"
assert_log_lacks "repo add" "path-mismatch: mismatch never triggers registration"

printf 'orca auto-register tests: %s passed, %s failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
