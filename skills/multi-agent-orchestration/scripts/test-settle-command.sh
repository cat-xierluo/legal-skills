#!/usr/bin/env bash
# Full-command regression for pm-orchestrate settle (Task-047R).
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PM="$SCRIPT_DIR/pm-orchestrate.sh"
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
  "worktree rm"*)
    echo '{"ok":true,"result":{"removed":true}}'
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
  OTHER_WT="$CASE_ROOT/worker-other"
  SESSION="settle-$name"
  mkdir -p "$REPO"
  git -C "$REPO" init -q
  printf '%s\n' base > "$REPO/base.txt"
  git -C "$REPO" add base.txt
  GIT_AUTHOR_NAME=Test GIT_AUTHOR_EMAIL=test@example.invalid \
    GIT_COMMITTER_NAME=Test GIT_COMMITTER_EMAIL=test@example.invalid \
    git -C "$REPO" commit -q -m base
  git -C "$REPO" worktree add -q -b "test-$name" "$WT"
  git -C "$REPO" worktree add -q -b "test-$name-other" "$OTHER_WT"
  mkdir -p "$WT/.claude/agent-sessions/$SESSION"
  jq -n \
    --arg project "$REPO" \
    --arg worktree "$WT" \
    --arg session "$SESSION" \
    '{project:$project,worktree:$worktree,session:{id:$session,orca:{worktree_id:"repo-test::worker",terminal_handle:"term-test",supervised:{run_id:"run-test",coordinator_handle:"term-pm",task_id:"task-test",dispatch_id:"ctx-test"}}},runtime:{provider_lease:{file:""}}}' \
    > "$WT/.claude/agent-sessions/$SESSION/METADATA.json"
  : > "$FAKE_ORCA_LOG"
}

run_settle() {
  local extra_args=()
  [ -z "${4:-}" ] || extra_args+=("$4")
  set +e
  ORCA_CLI_COMMAND="$FAKE_ORCA" FAKE_SHOW_JSON="$1" FAKE_STOP_FAIL="${2:-0}" \
    bash "$PM" settle --worktree "$WT" --session "$SESSION" --reason "$3" "${extra_args[@]}" \
    > "$CASE_ROOT/output.log" 2>&1
  SETTLE_RC=$?
  set -e
}

echo "Case 1: active worker is refused before lifecycle mutation"
new_case active
run_settle "$FIXDIR/worker-show-active.json" 0 "active must stay"
[ "$SETTLE_RC" -eq 2 ] && ok "active returns 2" || bad "active expected rc=2, got $SETTLE_RC"
if grep -q 'worker-stop\|worker-abandon\|worktree rm' "$FAKE_ORCA_LOG"; then
  bad "active path reached mutation"
else
  ok "active path made no lifecycle mutation"
fi

echo "Case 2: unknown states fail closed"
new_case unknown
UNKNOWN_JSON="$CASE_ROOT/unknown.json"
jq '.result.observation.status="future_idle" | .result.worker.state="future_ready"' \
  "$FIXDIR/worker-show-exited.json" > "$UNKNOWN_JSON"
run_settle "$UNKNOWN_JSON" 0 "unknown must stay"
[ "$SETTLE_RC" -eq 2 ] && ok "unknown state returns 2" || bad "unknown expected rc=2, got $SETTLE_RC"

echo "Case 3: worker-stop failure fences uncertainty but blocks destroy"
new_case stop-failure
run_settle "$FIXDIR/worker-show-exited.json" 1 "stop failure retained" --destroy
[ "$SETTLE_RC" -eq 2 ] && ok "stop failure returns 2" || bad "stop failure expected rc=2, got $SETTLE_RC"
[ -d "$WT" ] && ok "worktree retained after stop failure" || bad "worktree was deleted after stop failure"
grep -q 'orchestration worker-abandon' "$FAKE_ORCA_LOG" && ok "fallback abandon attempted" || bad "fallback abandon missing"
if grep -q '^worktree rm' "$FAKE_ORCA_LOG"; then
  bad "destroy continued after stop failure"
else
  ok "destroy blocked after stop failure"
fi

echo "Case 4: destroy removes only the exact worktree and preserves audit"
new_case destroy
run_settle "$FIXDIR/worker-show-exited.json" 0 "destroy integration" --destroy
[ "$SETTLE_RC" -eq 0 ] && ok "destroy returns 0" || bad "destroy expected rc=0, got $SETTLE_RC"
[ ! -e "$WT" ] && ok "target worktree removed" || bad "target worktree still exists"
[ -d "$OTHER_WT" ] && ok "sibling worktree retained" || bad "sibling worktree was removed"
if git -C "$REPO" worktree list --porcelain | awk -v target="$WT" '
    /^worktree / { path=$0; sub(/^worktree /, "", path); if (path == target) found=1 }
    END { exit(found ? 0 : 1) }
  '; then
  bad "target worktree registration remains"
else
  ok "target worktree registration removed"
fi
AUDIT="$REPO/.git/orchestration/settle-audit.ndjson"
if [ -f "$AUDIT" ] && jq -e 'select(.event == "destroyed" and .reason == "destroy integration")' "$AUDIT" >/dev/null; then
  ok "audit survives Session Context deletion"
else
  bad "persistent destroyed audit missing"
fi

echo "Case 5: missing METADATA.project blocks repository mutation"
new_case missing-project
jq 'del(.project)' "$WT/.claude/agent-sessions/$SESSION/METADATA.json" > "$CASE_ROOT/meta.json"
mv "$CASE_ROOT/meta.json" "$WT/.claude/agent-sessions/$SESSION/METADATA.json"
run_settle "$FIXDIR/worker-show-exited.json" 0 "missing project"
[ "$SETTLE_RC" -eq 2 ] && ok "missing project returns 2" || bad "missing project expected rc=2, got $SETTLE_RC"
[ ! -s "$FAKE_ORCA_LOG" ] && ok "missing project made no Orca call" || bad "missing project reached Orca"

echo ""
echo "Result: $pass pass, $fail fail"
[ "$fail" -eq 0 ]
