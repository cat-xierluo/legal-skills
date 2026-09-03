#!/usr/bin/env bash
# Full-command regression for pm-orchestrate quota-park (v2.11.0 P0-③)。
# 覆盖：正向停靠、active 反向拒绝、worker-stop 故障、lease 释放故障注入、
# --force 停靠活 worker、参数/模式反向、以及 park 后同 worktree 换 session 交接。
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PM="$SCRIPT_DIR/pm-orchestrate.sh"
LEASE_PY="$SCRIPT_DIR/provider-lease.py"
FIXDIR="$SCRIPT_DIR/tests/fixtures"
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT

pass=0
fail=0

ok() {
  echo "  ✓ $1"
  pass=$((pass + 1))
}

bad() {
  echo "  ✗ $1" >&2
  fail=$((fail + 1))
}

FAKE_ORCA="$TMP_ROOT/fake-orca"
FAKE_ORCA_LOG="$TMP_ROOT/fake-orca.log"
export FAKE_ORCA_LOG

cat > "$FAKE_ORCA" <<'FAKE'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$FAKE_ORCA_LOG"
case "$*" in
  "orchestration run-use"*)
    echo '{"ok":true,"result":{"run":{"id":"run-test","coordinator_handle":"term-pm"}}}'
    ;;
  "orchestration worker-show"*)
    cat "$FAKE_SHOW_JSON"
    ;;
  "orchestration worker-stop"*)
    if [ "${FAKE_STOP_FAIL:-0}" = "1" ]; then
      echo '{"ok":false,"error":"injected stop failure"}' >&2
      exit 1
    fi
    echo '{"ok":true,"result":{"status":"stopped"}}'
    ;;
  "orchestration worker-abandon"*)
    echo '{"ok":true,"result":{"status":"abandoned"}}'
    ;;
  "terminal show"*)
    # provider-lease.py 的 orca_terminal liveness 检查：connected/writable 任一为真
    # 即视为资源仍活（额度必须保留）。
    if [ "${FAKE_TERMINAL_CONNECTED:-0}" = "1" ]; then
      echo '{"ok":true,"result":{"terminal":{"handle":"term-test","connected":true,"writable":true}}}'
    else
      echo '{"ok":true,"result":{"terminal":{"handle":"term-test","connected":false,"writable":false}}}'
    fi
    ;;
  *)
    echo '{"ok":true,"result":{}}'
    ;;
esac
FAKE
chmod +x "$FAKE_ORCA"

new_case() {
  local name="$1"
  CASE_ROOT="$TMP_ROOT/$name"
  REPO="$CASE_ROOT/repo"
  WT="$CASE_ROOT/worker"
  SESSION="park-$name"
  LEASE_ROOT="$REPO/.git/orchestration/provider-leases"
  mkdir -p "$REPO"
  git -C "$REPO" init -q
  printf '%s\n' base > "$REPO/base.txt"
  git -C "$REPO" add base.txt
  GIT_AUTHOR_NAME=Test GIT_AUTHOR_EMAIL=test@example.invalid \
    GIT_COMMITTER_NAME=Test GIT_COMMITTER_EMAIL=test@example.invalid \
    git -C "$REPO" commit -q -m base
  git -C "$REPO" worktree add -q -b "test-$name" "$WT"
  mkdir -p "$WT/.claude/agent-sessions/$SESSION"
  # 真实 provider lease（acquire + finalize 走真代码路径），state=active + orca_terminal
  LEASE_FILE=$(ORCA_CLI_COMMAND="$FAKE_ORCA" python3 "$LEASE_PY" acquire \
    --root "$LEASE_ROOT" --provider anthropic --backend claude-code \
    --session "$SESSION" --project "$REPO" --max 1 --owner-pid $$ | jq -r .lease_file)
  python3 "$LEASE_PY" finalize --root "$LEASE_ROOT" --lease-file "$LEASE_FILE" \
    --session "$SESSION" --transport orca_terminal --resource-handle term-test >/dev/null
  jq -n \
    --arg project "$REPO" \
    --arg worktree "$WT" \
    --arg session "$SESSION" \
    --arg lease_file "$LEASE_FILE" \
    '{project:$project,worktree:$worktree,session:{id:$session,orca:{worktree_id:"repo-test::worker",terminal_handle:"term-test",supervised:{run_id:"run-test",coordinator_handle:"term-pm",task_id:"task-test",dispatch_id:"ctx-test"}}},runtime:{provider_lease:{file:$lease_file}}}' \
    > "$WT/.claude/agent-sessions/$SESSION/METADATA.json"
  # 未提交工作 + checkpoint 文件：park 必须完整保留
  printf '%s\n' "wip for $name" > "$WT/uncommitted.txt"
  AUDIT="$REPO/.git/orchestration/settle-audit.ndjson"
  REASON_VAL="quota stall handoff"
  : > "$FAKE_ORCA_LOG"
}

run_park() {
  local extra_args=()
  [ -z "${1:-}" ] || extra_args+=("$1")
  set +e
  ORCA_CLI_COMMAND="$FAKE_ORCA" FAKE_SHOW_JSON="${FAKE_SHOW_JSON_FILE:-$FIXDIR/worker-show-exited.json}" \
    bash "$PM" quota-park --worktree "$WT" --session "$SESSION" --reason "${REASON_VAL-}" ${extra_args[@]+"${extra_args[@]}"} \
    > "$CASE_ROOT/output.log" 2>&1
  PARK_RC=$?
  set -e
}

metadata_is() {
  [ -f "$WT/.claude/agent-sessions/$SESSION/METADATA.json" ]
}

echo "Case 1: dead worker parks cleanly and releases the provider lease"
new_case positive
FAKE_SHOW_JSON_FILE="$FIXDIR/worker-show-exited.json" run_park
[ "$PARK_RC" -eq 0 ] && ok "park returns 0" || bad "park expected rc=0, got $PARK_RC"
grep -q 'orchestration worker-stop' "$FAKE_ORCA_LOG" && ok "worker-stop fenced the old dispatch" || bad "worker-stop missing"
[ ! -e "$LEASE_FILE" ] && ok "provider lease released" || bad "provider lease still present"
metadata_is && ok "METADATA (session checkpoint) preserved" || bad "METADATA missing after park"
[ -f "$WT/uncommitted.txt" ] && ok "uncommitted worktree change preserved" || bad "uncommitted change lost"
jq -e '.recovery.quota_park.dispatch_id == "ctx-test" and (.recovery.quota_park.parked_at | length > 0) and (.recovery.quota_park.provider_lease_file | length > 0)' \
  "$WT/.claude/agent-sessions/$SESSION/METADATA.json" >/dev/null \
  && ok "quota_park marker written with dispatch + parked_at" || bad "quota_park marker missing/incomplete"
jq -e 'select(.event == "quota_park_parked")' "$AUDIT" >/dev/null && ok "final park audit persisted" || bad "park audit missing"

echo "Case 2: active worker is refused before any lifecycle mutation (no double-active)"
new_case active-refused
FAKE_SHOW_JSON_FILE="$FIXDIR/worker-show-active.json" run_park
[ "$PARK_RC" -eq 2 ] && ok "active worker returns 2" || bad "active expected rc=2, got $PARK_RC"
if grep -q 'worker-stop' "$FAKE_ORCA_LOG"; then
  bad "active path reached worker-stop"
else
  ok "active path made no lifecycle mutation"
fi
[ -e "$LEASE_FILE" ] && ok "provider lease retained for active worker" || bad "lease released while worker active (double-active)"
jq -e '.recovery.quota_park == null' "$WT/.claude/agent-sessions/$SESSION/METADATA.json" >/dev/null \
  && ok "no marker written on refusal" || bad "marker written on refusal"

echo "Case 3: worker-stop failure keeps the lease and writes no marker"
new_case stop-fail
FAKE_STOP_FAIL=1 run_park
[ "$PARK_RC" -eq 2 ] && ok "stop failure returns 2" || bad "stop failure expected rc=2, got $PARK_RC"
grep -q 'orchestration worker-abandon' "$FAKE_ORCA_LOG" && ok "fallback abandon attempted" || bad "fallback abandon missing"
[ -e "$LEASE_FILE" ] && ok "provider lease retained after stop failure" || bad "lease released after stop failure"
jq -e '.recovery.quota_park == null' "$WT/.claude/agent-sessions/$SESSION/METADATA.json" >/dev/null \
  && ok "no marker after stop failure" || bad "marker written after stop failure"
jq -e 'select(.event == "quota_park_stop_failed")' "$AUDIT" >/dev/null && ok "stop-failure audit persisted" || bad "stop-failure audit missing"

echo "Case 4: lease-release fault injection aborts before the marker (quota stays held)"
new_case lease-fail
FAKE_TERMINAL_CONNECTED=1 run_park
[ "$PARK_RC" -eq 2 ] && ok "lease-release failure returns 2" || bad "lease failure expected rc=2, got $PARK_RC"
[ -e "$LEASE_FILE" ] && ok "provider lease retained on release failure" || bad "lease vanished on release failure"
jq -e '.recovery.quota_park == null' "$WT/.claude/agent-sessions/$SESSION/METADATA.json" >/dev/null \
  && ok "no marker after lease failure (restart not authorized)" || bad "marker written after lease failure"
jq -e 'select(.event == "quota_park_lease_release_failed")' "$AUDIT" >/dev/null && ok "lease-failure audit persisted" || bad "lease-failure audit missing"

echo "Case 5: --force parks an actively-stuck worker after manual verification"
new_case force-active
FAKE_SHOW_JSON_FILE="$FIXDIR/worker-show-active.json" run_park --force
[ "$PARK_RC" -eq 0 ] && ok "forced park of active worker returns 0" || bad "forced park expected rc=0, got $PARK_RC"
[ ! -e "$LEASE_FILE" ] && ok "provider lease released after forced park" || bad "lease not released after forced park"
jq -e '.recovery.quota_park.dispatch_id == "ctx-test"' "$WT/.claude/agent-sessions/$SESSION/METADATA.json" >/dev/null \
  && ok "marker written after forced park" || bad "marker missing after forced park"

echo "Case 6: missing --reason is refused before any mutation"
new_case no-reason
REASON_VAL="" run_park
[ "$PARK_RC" -eq 64 ] && ok "missing --reason returns 64" || bad "missing reason expected rc=64, got $PARK_RC"
[ ! -s "$FAKE_ORCA_LOG" ] && ok "missing --reason made no Orca call" || bad "missing reason reached Orca"

echo "Case 7: non-supervised (tmux) worker is refused (no dispatch fencing, no park)"
new_case tmux-mode
jq '.session.orca.supervised = null | .session.orca.terminal_handle = null' \
  "$WT/.claude/agent-sessions/$SESSION/METADATA.json" > "$CASE_ROOT/meta.json"
mv "$CASE_ROOT/meta.json" "$WT/.claude/agent-sessions/$SESSION/METADATA.json"
run_park
[ "$PARK_RC" -eq 64 ] && ok "tmux-mode worker returns 64" || bad "tmux-mode expected rc=64, got $PARK_RC"
[ ! -s "$FAKE_ORCA_LOG" ] && ok "tmux-mode made no Orca call" || bad "tmux-mode reached Orca"
[ -e "$LEASE_FILE" ] && ok "tmux-mode lease untouched" || bad "tmux-mode lease released"

echo "Case 8: handoff — after park, a NEW session can acquire the same provider again"
new_case handoff
run_park
[ "$PARK_RC" -eq 0 ] && ok "park before handoff returns 0" || bad "park before handoff expected rc=0, got $PARK_RC"
set +e
HANDOFF_OUT=$(python3 "$LEASE_PY" acquire \
  --root "$LEASE_ROOT" --provider anthropic --backend claude-code \
  --session "$SESSION-restart" --project "$REPO" --max 1 --owner-pid $$ 2>&1)
HANDOFF_RC=$?
set -e
[ "$HANDOFF_RC" -eq 0 ] && ok "new session acquires the released provider slot" || bad "new session acquire failed rc=$HANDOFF_RC: $HANDOFF_OUT"
HANDOFF_LEASE=$(printf '%s' "$HANDOFF_OUT" | jq -r .lease_file)
[ -f "$HANDOFF_LEASE" ] && ok "acquire created the new session lease file" || bad "acquire lease file missing: $HANDOFF_LEASE"

echo ""
echo "Result: $pass pass, $fail fail"
[ "$fail" -eq 0 ]
