#!/usr/bin/env bash
# test-pm-run-bind.sh — full-mock regression for pm-run-bind.sh (BL-162).
#
# 覆盖三路径（mock orca CLI）：
#   Case 1: handle detection miss → 拒绝、未触达 run-use、提示如何在 Orca 终端跑/显式传 --from
#   Case 1: handle detection miss → 拒绝、未触达 run-current、提示如何在 Orca 终端跑/显式传 --from
#   Case 2: successful rebind     → run-use + run-current 都对得上、stdout 输出 run_id / coordinator
#   Case 3: verify mismatch        → run-use 成功但 run-current 报另一 run_id，拒绝并出恢复提示
#   Case 4 (extra): run-use call failure → exit 1、提示勿盲重试
#   Case 5 (extra): terminal-current probe succeeds → 用 orca 上下文探测拿到的 handle
#                                          能正确传进 run-use
#   Case 6 (extra): ORCA_TERMINAL_HANDLE env 优先于 probe
#   Case 7 (extra): run-use 退 0 但 payload ok:false → exit 1
#   Case 8 (extra): run-use OK 但 run-current 不可达 → exit 2
#
# 工具缺失红先证：测试首行检查 pm-run-bind.sh 存在性；缺失时直接退 1。
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BIND="$SCRIPT_DIR/pm-run-bind.sh"
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT

# 红先证：脚本存在性断言。
if [ ! -f "$BIND" ]; then
  echo "FAIL: pm-run-bind.sh missing at $BIND (red-first: this proves the gate works)" >&2
  exit 1
fi

pass=0
fail=0
ok()  { echo "  ✓ $1"; pass=$((pass + 1)); }
bad() { echo "  ✗ $1" >&2; fail=$((fail + 1)); }

# 断言助手：
#   assert_grep <out|log> <pattern> <desc>   — 必须匹配
#   assert_not_grep <out|log> <pattern> <desc> — 必须不匹配
# OUT 来源：BIND 脚本的 stdout+stderr（PM_RUN_BIND_* 行、恢复提示、stdout payload）。
# LOG 来源：fake orca CLI 写入 $FAKE_LOG 的调用日志（用于断言 orca 命令调用形态）。
assert_grep() {
  local source="$1" pat="$2" desc="$3"
  local haystack
  case "$source" in
    out) haystack="$OUT" ;;
    log) haystack=$(cat "$FAKE_LOG" 2>/dev/null || true) ;;
    *)   bad "INTERNAL: assert_grep source=$source"; return ;;
  esac
  if printf '%s\n' "$haystack" | grep -qE -- "$pat"; then
    ok "$desc"
  else
    bad "$desc (source=$source pattern=$pat)"
    echo "    --- FAKE LOG ($FAKE_LOG) ---" >&2
    sed 's/^/    | /' "$FAKE_LOG" 2>/dev/null >&2 || true
    echo "    --- OUT ---" >&2
    sed 's/^/    | /' <<<"$OUT" >&2
  fi
}
assert_not_grep() {
  local source="$1" pat="$2" desc="$3"
  local haystack
  case "$source" in
    out) haystack="$OUT" ;;
    log) haystack=$(cat "$FAKE_LOG" 2>/dev/null || true) ;;
    *)   bad "INTERNAL: assert_not_grep source=$source"; return ;;
  esac
  if printf '%s\n' "$haystack" | grep -qE -- "$pat"; then
    bad "$desc (source=$source should NOT contain: $pat)"
    echo "    --- FAKE LOG ($FAKE_LOG) ---" >&2
    sed 's/^/    | /' "$FAKE_LOG" 2>/dev/null >&2 || true
  else
    ok "$desc"
  fi
}

STATE="$TMP_ROOT/state"
mkdir -p "$STATE"
FAKE="$TMP_ROOT/fake-orca"
FAKE_LOG="$TMP_ROOT/orca.log"
export FAKE_ORCA_LOG="$FAKE_LOG"
export FAKE_ORCA_STATE="$STATE"

# 可编程 fake orca CLI。每条 case 通过 state 文件调整行为。
cat > "$FAKE" <<'FAKE'
#!/usr/bin/env bash
set -euo pipefail
{
  for arg in "$@"; do printf '%q ' "$arg"; done
  printf '\n'
} >> "$FAKE_ORCA_LOG"
S="$FAKE_ORCA_STATE"
case "$1 $2" in
  # ---------- handle probe (orca terminal current) ----------
  "terminal current")
    if [ -e "$S/terminal-current-fail" ]; then
      echo '{"ok":false,"error":{"code":"selector_not_found"}}' >&2
      exit 1
    fi
    if [ -e "$S/terminal-current-empty" ]; then
      echo '{"ok":true,"result":{"terminal":{}}}'  # 无 handle
      exit 0
    fi
    handle=$(cat "$S/terminal-current-handle" 2>/dev/null) || handle="term-from-probe"
    printf '{"ok":true,"result":{"terminal":{"handle":"%s"}}}\n' "$handle"
    ;;
  # ---------- 核心 run-use ----------
  "orchestration run-use")
    if [ -e "$S/run-use-fail" ]; then
      echo '{"ok":false,"error":{"code":"RUN_NOT_FOUND","message":"injected"}}' >&2
      echo '{"ok":false,"error":{"code":"RUN_NOT_FOUND","message":"injected"}}'
      exit 1
    fi
    if [ -e "$S/run-use-notok" ]; then
      echo '{"ok":false,"error":{"code":"RUN_LOCKED","message":"locked"}}'
      exit 0
    fi
    echo '{"ok":true,"result":{"run":{"id":"run-x","coordinator_handle":"term-pm"}}}'
    ;;
  # ---------- 校验：run-current ----------
  "orchestration run-current")
    if [ -e "$S/run-current-unavailable" ]; then
      echo '{"ok":false,"error":{"code":"INTERNAL","message":"unavailable"}}' >&2
      exit 1
    fi
    if [ -e "$S/run-current-mismatch" ]; then
      echo '{"ok":true,"result":{"run":{"id":"run-stale","coordinator_handle":"term-old"}}}'
    else
      echo '{"ok":true,"result":{"run":{"id":"run-x","coordinator_handle":"term-pm"}}}'
    fi
    ;;
  *)
    echo '{"ok":true,"result":{}}'
    ;;
esac
FAKE
chmod +x "$FAKE"

# ---------- 工具函数 ----------
reset_state() {
  rm -f "$STATE"/* 2>/dev/null || true
  : > "$FAKE_LOG"
}
run_bind() {
  # run_bind <额外参数...>；产出全局 RC/OUT
  RC=0
  OUT=$(ORCA_CLI_COMMAND="$FAKE" bash "$BIND" "$@" 2>&1) || RC=$?
}
assert_rc() {
  local want="$1" desc="$2"
  if [ "$RC" = "$want" ]; then ok "$desc (rc=$RC)"; else bad "$desc (expected rc=$want got $RC)"; fi
}

# ============================== Case 1 ==============================
echo "Case 1: handle detection fails — no --from, env unset, terminal-current empty → exit 64, no Orca call"
reset_state
touch "$STATE/terminal-current-empty"
unset ORCA_TERMINAL_HANDLE
run_bind run-x
assert_rc 64 "missing handle exits 64"
assert_grep    out "cannot determine sending terminal handle" "handle-miss error line"
assert_grep    out "RECOVERY"                                "recovery hint printed"
assert_grep    out "Orca terminal"                            "hint mentions Orca terminal"
assert_grep    out "pm-run-bind.sh <run_id> --from <handle>"  "hint suggests explicit --from"
assert_grep    out "Do NOT retry blindly"                     "hint warns against blind retry"
assert_not_grep log "orchestration run-use "                  "no run-use call made"
assert_not_grep log "orchestration run-current"               "no run-current call made"

# ============================== Case 2 ==============================
echo "Case 2: successful rebind via --from → exit 0, stdout echoes run_id + coordinator"
reset_state
run_bind run-x --from term-pm
assert_rc 0 "successful rebind exits 0"
assert_grep    out "PM_RUN_BIND_START"                        "start diagnostic line"
assert_grep    out "PM_RUN_BIND_USED"                         "post run-use diagnostic line"
assert_grep    out "PM_RUN_BIND_VERIFIED"                     "post verify diagnostic line"
assert_grep    out "^run_id=run-x"                            "stdout has run_id=run-x"
assert_grep    out "^coordinator=term-pm"                     "stdout has coordinator=term-pm"
assert_grep    log "orchestration run-use .* run-x .* term-pm" "run-use called with --id run-x --from term-pm"
assert_grep    log "orchestration run-current"                "run-current called for verification"
assert_grep    log "run-current --from term-pm"           "run-current verifies with --from (F1 cross-terminal)"

# ============================== Case 3 ==============================
echo "Case 3: verify mismatch — run-use OK but run-current returns stale run_id → exit 2, recovery printed"
reset_state
touch "$STATE/run-current-mismatch"
run_bind run-x --from term-pm
assert_rc 2 "verify mismatch exits 2"
assert_grep    out "PM_RUN_BIND_USED"                         "run-use still marked succeeded (script doesn't lie)"
assert_grep    out "verify mismatch"                          "mismatch error line"
assert_grep    out "run-stale"                                "recovery hint surfaces actual current run_id"
assert_grep    out "term-old"                                 "recovery hint surfaces actual current coordinator"
assert_grep    out "Do NOT retry blindly"                     "recovery warns against blind retry"
assert_grep    out "pm-run-bind.sh run-x --from"              "recovery suggests re-bind with explicit handle"

# ============================== Case 4 ==============================
echo "Case 4: run-use call failure (rc != 0) → exit 1, recovery printed, no verify call"
reset_state
touch "$STATE/run-use-fail"
run_bind run-x --from term-pm
assert_rc 1 "run-use failure exits 1"
assert_grep    out "run-use failed"                           "run-use failure error line"
assert_grep    out "Do NOT retry blindly"                     "recovery warns against blind retry"
assert_not_grep log "orchestration run-current"               "verify not attempted after run-use failure"
assert_grep    out "RUN_NOT_FOUND"                            "raw error code surfaced for diagnosis"

# ============================== Case 5 ==============================
echo "Case 5: orca terminal-current probe → handle picked up automatically, no --from needed"
reset_state
printf 'term-from-probe\n' > "$STATE/terminal-current-handle"
unset ORCA_TERMINAL_HANDLE
run_bind run-x
assert_rc 0 "probe-detected handle succeeds"
assert_grep    log "^terminal current "                       "terminal-current probe invoked"
assert_grep    log "orchestration run-use .* run-x .* term-from-probe" "run-use uses probed handle"
assert_grep    out "^coordinator=term-pm"                     "stdout echoes coordinator from verify"

# ============================== Case 6 ==============================
echo "Case 6: ORCA_TERMINAL_HANDLE takes priority over probe — both available"
reset_state
printf 'term-from-probe\n' > "$STATE/terminal-current-handle"
export ORCA_TERMINAL_HANDLE="term-from-env"
run_bind run-x
assert_rc 0 "env var handle succeeds"
assert_grep    log "orchestration run-use .* run-x .* term-from-env" "run-use uses env var handle (not probe)"
unset ORCA_TERMINAL_HANDLE

# ============================== Case 7 ==============================
echo "Case 7: run-use exits 0 but payload has ok:false → exit 1, recovery printed"
reset_state
touch "$STATE/run-use-notok"
run_bind run-x --from term-pm
assert_rc 1 "not-ok payload exits 1"
assert_grep    out "not-ok payload"                           "not-ok payload error line"
assert_grep    out "RUN_LOCKED"                               "raw error code surfaced"
assert_not_grep log "orchestration run-current"               "verify not attempted after not-ok payload"

# ============================== Case 8 ==============================
echo "Case 8: run-use succeeds, run-current unreachable → exit 2, recovery printed"
reset_state
touch "$STATE/run-current-unavailable"
run_bind run-x --from term-pm
assert_rc 2 "run-current unreachable exits 2"
assert_grep    out "PM_RUN_BIND_USED"                         "run-use succeeded (verified before probe)"
assert_grep    out "run-current verification call failed"     "verify-failure error line"
assert_grep    out "binding status unknown"                   "hint flags binding as unknown"

echo ""
echo "Result: $pass pass, $fail fail"
[ "$fail" -eq 0 ]