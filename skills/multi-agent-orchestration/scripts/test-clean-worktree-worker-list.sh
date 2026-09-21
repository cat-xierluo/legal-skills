#!/usr/bin/env bash
# Deterministic failure-injection coverage for exact paginated WorkerList cleanup.
# Uses throwaway Git worktrees and a stateful fake Orca CLI; no network or real
# Orca resources are touched.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CLEAN_SCRIPT="$SCRIPT_DIR/clean-worktree.sh"
BASH_BIN=${TEST_BASH_BIN:-bash}
TMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/clean-worker-list.XXXXXX")
trap 'rm -rf "$TMP_ROOT"' EXIT

pass=0
fail=0
ok() { printf 'PASS: %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf 'FAIL: %s\n' "$1" >&2; fail=$((fail + 1)); }

assert_log_contains() {
  local needle=$1 label=$2
  if grep -qF -- "$needle" "$ORCA_LOG"; then ok "$label"; else bad "$label (missing: $needle)"; fi
}

assert_log_not_contains() {
  local needle=$1 label=$2
  if grep -qF -- "$needle" "$ORCA_LOG"; then bad "$label (unexpected: $needle)"; else ok "$label"; fi
}

assert_count() {
  local needle=$1 expected=$2 label=$3 actual
  actual=$(awk -v needle="$needle" 'index($0, needle) { count += 1 } END { print count + 0 }' "$ORCA_LOG")
  if [ "$actual" -eq "$expected" ]; then ok "$label"; else bad "$label (expected=$expected actual=$actual)"; fi
}

FAKE_ORCA="$TMP_ROOT/orca-fake"
cat > "$FAKE_ORCA" <<'FAKE'
#!/usr/bin/env bash
set -euo pipefail

{
  for arg in "$@"; do printf '%q ' "$arg"; done
  printf '\n'
} >> "${FAKE_ORCA_LOG:?}"

mode=${FAKE_ORCA_MODE:?}
run_id=${FAKE_ORCA_RUN_ID:-run-target}
dispatch_id=${FAKE_ORCA_DISPATCH_ID:-dispatch-target}
cursor=""
previous=""
for arg in "$@"; do
  if [ "$previous" = "--cursor" ]; then cursor=$arg; fi
  previous=$arg
done

row() {
  local dispatch=$1 row_run=$2 state=$3 handle=${4:-term-target}
  jq -cn --arg dispatch "$dispatch" --arg run "$row_run" --arg state "$state" --arg handle "$handle" '
    {dispatchId:$dispatch,runId:$run,terminalState:$state,workerState:"succeeded",
     dispatchStatus:"completed",agentTerminalHandle:$handle,
     resource:{ownershipState:"external",retainedReason:"external_terminal",terminalHandle:$handle}}'
}

page() {
  local workers=$1 has_more=$2 next_cursor_json=$3 total=$4 scope_run=${5:-$run_id}
  jq -cn --argjson workers "$workers" --arg scope_run "$scope_run" \
    --argjson more "$has_more" --argjson next "$next_cursor_json" --argjson total "$total" '
    {ok:true,result:{scope:{source:"flag",runId:$scope_run},workers:$workers,
      page:{limit:100,total:$total,hasMore:$more,nextCursor:$next}}}'
}

if [ "$1 $2" = "orchestration worker-list" ]; then
  target=$(row "$dispatch_id" "$run_id" "${FAKE_ORCA_TERMINAL_STATE:-released}" "${FAKE_ORCA_RESOURCE_HANDLE:-term-target}")
  other=$(row dispatch-other "$run_id" released term-other)
  case "$mode" in
    first-page|released|retained-exact|retained-mismatch|retained-show-fail|retained-show-invalid|retained-show-live|retained-show-mismatch)
      page "[$target]" false null 1
      ;;
    active)
      target=$(row "$dispatch_id" "$run_id" active)
      page "[$target]" false null 1
      ;;
    release-pending)
      target=$(row "$dispatch_id" "$run_id" release_pending)
      page "[$target]" false null 1
      ;;
    later-page)
      if [ -z "$cursor" ]; then page "[$other]" true '"cursor-2"' 2; else page "[$target]" false null 2; fi
      ;;
    missing)
      if [ -z "$cursor" ]; then page "[$other]" true '"cursor-2"' 2; else page '[]' false null 2; fi
      ;;
    duplicate-same)
      page "[$target,$target]" false null 2
      ;;
    duplicate-cross)
      if [ -z "$cursor" ]; then page "[$target]" true '"cursor-2"' 2; else page "[$target]" false null 2; fi
      ;;
    has-more-empty)
      page '[]' true '""' 1
      ;;
    has-more-nonstring)
      page '[]' true 7 1
      ;;
    cursor-self)
      page '[]' true '"cursor-self"' 3
      ;;
    cursor-loop)
      case "$cursor" in
        "") page '[]' true '"cursor-a"' 10 ;;
        cursor-a) page '[]' true '"cursor-b"' 10 ;;
        *) page '[]' true '"cursor-a"' 10 ;;
      esac
      ;;
    total-short)
      page "[$target]" false null 2
      ;;
    total-huge)
      page "[$target]" false null 1e20
      ;;
    total-drift)
      if [ -z "$cursor" ]; then page "[$other]" true '"cursor-2"' 2; else page "[$target]" false null 3; fi
      ;;
    worker-run-mismatch)
      target=$(row "$dispatch_id" run-other released)
      page "[$target]" false null 1
      ;;
    dispatch-alias-only)
      target=$(jq -cn --arg dispatch "$dispatch_id" --arg run "$run_id" \
        '{id:$dispatch,runId:$run,terminalState:"released"}')
      page "[$target]" false null 1
      ;;
    page-budget)
      index=${cursor:-0}
      next=$((index + 1))
      page "[$other]" true "\"$next\"" 101
      ;;
    cli-fail)
      exit 23
      ;;
    invalid-json)
      printf '{not-json\n'
      ;;
    ok-false)
      printf '%s\n' '{"ok":false,"result":{"scope":{"source":"flag","runId":"run-target"},"workers":[],"page":{"limit":100,"total":0,"hasMore":false,"nextCursor":null}}}'
      ;;
    missing-page)
      jq -cn --arg run "$run_id" '{ok:true,result:{scope:{source:"flag",runId:$run},workers:[]}}'
      ;;
    scope-mismatch)
      page "[$target]" false null 1 run-other
      ;;
    reclaimable|post-release-unknown)
      if [ -f "${FAKE_ORCA_RELEASED_FILE:?}" ]; then
        if [ "$mode" = reclaimable ]; then state=released; else state=unknown; fi
      else
        state=reclaimable
      fi
      target=$(row "$dispatch_id" "$run_id" "$state")
      page "[$target]" false null 1
      ;;
    *)
      printf 'unexpected fake mode: %s\n' "$mode" >&2
      exit 97
      ;;
  esac
  exit 0
fi

if [ "$1 $2" = "orchestration worker-release" ]; then
  : > "${FAKE_ORCA_RELEASED_FILE:?}"
  jq -cn --arg dispatch "$dispatch_id" '{ok:true,result:{release:{dispatchId:$dispatch}}}'
  exit 0
fi

if [ "$1 $2" = "terminal close" ]; then
  case "$mode" in
    retained-show-fail|retained-show-invalid|retained-show-live|retained-show-mismatch) exit 23 ;;
  esac
  jq -cn --arg terminal "$4" '{ok:true,result:{terminal:{handle:$terminal,connected:false,writable:false}}}'
  exit 0
fi

if [ "$1 $2" = "terminal show" ]; then
  case "$mode" in
    retained-show-fail) exit 24 ;;
    retained-show-invalid) printf '{not-json\n'; exit 0 ;;
    retained-show-live) jq -cn --arg terminal "$4" '{ok:true,result:{terminal:{handle:$terminal,connected:true,writable:true}}}'; exit 0 ;;
    retained-show-mismatch) jq -cn '{ok:true,result:{terminal:{handle:"other",connected:false,writable:false}}}'; exit 0 ;;
  esac
  jq -cn --arg terminal "$4" '{ok:true,result:{terminal:{handle:$terminal,connected:false,writable:false}}}'
  exit 0
fi

printf '%s\n' '{"ok":true,"result":{}}'
FAKE
chmod +x "$FAKE_ORCA"

FAKE_BIN="$TMP_ROOT/fake-bin"
mkdir -p "$FAKE_BIN"
cat > "$FAKE_BIN/tmux" <<'FAKE'
#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  has-session)
    [ "${FAKE_TMUX_ACTIVE:-0}" = "1" ]
    ;;
  kill-session)
    printf 'tmux kill-session %s\n' "$*" >> "${FAKE_ORCA_LOG:?}"
    ;;
  *)
    exit 2
    ;;
esac
FAKE
chmod +x "$FAKE_BIN/tmux"

case_index=0
make_fixture() {
  local label=$1 include_run=${2:-1}
  case_index=$((case_index + 1))
  CASE_ROOT="$TMP_ROOT/case-$case_index-$label"
  PROJECT="$CASE_ROOT/project"
  WORKTREE="$CASE_ROOT/worktree"
  BRANCH="feat/$label-$case_index"
  SESSION="session-$label-$case_index"
  ORCA_LOG="$CASE_ROOT/orca.log"
  RELEASED_FILE="$CASE_ROOT/released"
  OUT="$CASE_ROOT/out.log"
  ERR="$CASE_ROOT/err.log"
  mkdir -p "$PROJECT"
  git -C "$PROJECT" init -q
  git -C "$PROJECT" config user.name Test
  git -C "$PROJECT" config user.email test@example.invalid
  printf 'base\n' > "$PROJECT/base.txt"
  printf '.claude/agent-sessions/\n' > "$PROJECT/.gitignore"
  git -C "$PROJECT" add base.txt .gitignore
  git -C "$PROJECT" commit -qm base
  git -C "$PROJECT" branch -M main
  git -C "$PROJECT" worktree add -q -b "$BRANCH" "$WORKTREE" main
  mkdir -p "$WORKTREE/.claude/agent-sessions/$SESSION"
  if [ "$include_run" -eq 1 ]; then
    jq -n --arg session "$SESSION" '
      {base_ref:"main",session:{id:$session,orca:{mode:"orca",worktree_id:"repo::worker",
       terminal_handle:"term-target",supervised:{run_id:"run-target",dispatch_id:"dispatch-target",
       terminal_ownership:"external"}}},runtime:{provider_lease:{file:""}}}' \
      > "$WORKTREE/.claude/agent-sessions/$SESSION/METADATA.json"
  else
    jq -n --arg session "$SESSION" '
      {base_ref:"main",session:{id:$session,orca:{mode:"orca",worktree_id:"repo::worker",
       terminal_handle:"term-target",supervised:{dispatch_id:"dispatch-target",
       terminal_ownership:"external"}}},runtime:{provider_lease:{file:""}}}' \
      > "$WORKTREE/.claude/agent-sessions/$SESSION/METADATA.json"
  fi
  : > "$ORCA_LOG"
}

run_cleanup() {
  local mode=$1 state=${2:-released} handle=${3:-term-target} tmux_active=${4:-0} keep_worktree=${5:-0}
  local -a clean_args=(--project "$PROJECT" --worktree "$WORKTREE" --branch "$BRANCH" --session "$SESSION" --execute)
  [ "$keep_worktree" -eq 0 ] || clean_args+=(--keep-worktree)
  set +e
  PATH="$FAKE_BIN:$PATH" ORCA_CLI_COMMAND="$FAKE_ORCA" FAKE_ORCA_LOG="$ORCA_LOG" FAKE_ORCA_MODE="$mode" \
    FAKE_ORCA_RUN_ID=run-target FAKE_ORCA_DISPATCH_ID=dispatch-target \
    FAKE_ORCA_TERMINAL_STATE="$state" FAKE_ORCA_RESOURCE_HANDLE="$handle" \
    FAKE_ORCA_RELEASED_FILE="$RELEASED_FILE" FAKE_TMUX_ACTIVE="$tmux_active" \
    "$BASH_BIN" "$CLEAN_SCRIPT" "${clean_args[@]}" > "$OUT" 2> "$ERR"
  CLEAN_RC=$?
  set -e
}

assert_failed_before_mutation() {
  local label=$1
  if [ "$CLEAN_RC" -eq 2 ]; then ok "$label exits 2"; else bad "$label exits 2 (actual=$CLEAN_RC)"; fi
  assert_log_not_contains 'orchestration worker-release' "$label performs no worker-release"
  assert_log_not_contains 'terminal close' "$label performs no terminal close"
  assert_log_not_contains 'tmux kill-session' "$label performs no tmux session kill"
  assert_log_not_contains 'worktree rm' "$label performs no Orca worktree rm"
  if [ -d "$WORKTREE" ]; then ok "$label preserves worktree"; else bad "$label preserves worktree"; fi
  if git -C "$PROJECT" show-ref --verify --quiet "refs/heads/$BRANCH"; then ok "$label preserves local branch"; else bad "$label preserves local branch"; fi
}

run_preflight_refusal() {
  local mode=$1 label=$2 include_run=${3:-1}
  make_fixture "$label" "$include_run"
  run_cleanup "$mode"
  assert_failed_before_mutation "$label"
}

echo '=== exact pagination positive paths ==='
make_fixture first-page
run_cleanup first-page
if [ "$CLEAN_RC" -eq 0 ]; then ok 'first-page exact row cleans successfully'; else bad "first-page exact row cleans successfully (rc=$CLEAN_RC)"; fi
assert_log_contains 'orchestration worker-list --run run-target --limit 100 --json' 'first-page query binds run and page limit'
assert_log_not_contains 'orchestration worker-release' 'already released row is not released again'
assert_log_contains 'worktree rm --worktree id:repo::worker --force --json' 'released row permits Orca worktree removal'
if [ ! -d "$WORKTREE" ]; then ok 'released row permits Git worktree removal'; else bad 'released row permits Git worktree removal'; fi

make_fixture later-page
run_cleanup later-page
if [ "$CLEAN_RC" -eq 0 ]; then ok 'later-page exact row cleans successfully'; else bad "later-page exact row cleans successfully (rc=$CLEAN_RC)"; fi
assert_log_contains 'orchestration worker-list --run run-target --limit 100 --cursor cursor-2 --json' 'pagination follows opaque nextCursor'
assert_count 'orchestration worker-list' 2 'later-page query reads both pages'

echo '=== malformed, ambiguous and missing WorkerList paths fail before mutation ==='
run_preflight_refusal missing missing-row
run_preflight_refusal duplicate-same duplicate-same-page
run_preflight_refusal duplicate-cross duplicate-cross-page
run_preflight_refusal has-more-empty has-more-empty-cursor
run_preflight_refusal has-more-nonstring has-more-nonstring-cursor
run_preflight_refusal cursor-self cursor-self-loop
run_preflight_refusal cursor-loop cursor-multi-page-loop
run_preflight_refusal cli-fail cli-failure
run_preflight_refusal invalid-json invalid-json
run_preflight_refusal ok-false ok-false
run_preflight_refusal missing-page missing-page
run_preflight_refusal scope-mismatch scope-mismatch
run_preflight_refusal total-short total-short
run_preflight_refusal total-huge total-huge
run_preflight_refusal total-drift total-drift
run_preflight_refusal worker-run-mismatch worker-run-mismatch
run_preflight_refusal dispatch-alias-only dispatch-alias-only
run_preflight_refusal page-budget page-budget
run_preflight_refusal first-page missing-run-id 0
assert_log_not_contains 'orchestration worker-list' 'missing run_id refuses before WorkerList query'

echo '=== lifecycle states and post-release recheck ==='
make_fixture active-state
run_cleanup active released term-target 1
assert_failed_before_mutation active-state
make_fixture active-keep-worktree
run_cleanup active released term-target 1 1
assert_failed_before_mutation active-keep-worktree
run_preflight_refusal release-pending release-pending-state

make_fixture reclaimable
run_cleanup reclaimable
if [ "$CLEAN_RC" -eq 0 ]; then ok 'reclaimable row releases then cleans'; else bad "reclaimable row releases then cleans (rc=$CLEAN_RC)"; fi
assert_count 'orchestration worker-release' 1 'reclaimable row releases exactly once'
assert_count 'orchestration worker-list' 2 'reclaimable row is re-read after release'
assert_log_contains 'worktree rm --worktree id:repo::worker --force --json' 'released recheck permits worktree removal'
if [ ! -d "$WORKTREE" ]; then ok 'reclaimable success removes worktree'; else bad 'reclaimable success removes worktree'; fi

make_fixture retained-exact
run_cleanup retained-exact retained term-target
if [ "$CLEAN_RC" -eq 0 ]; then ok 'exact retained external terminal cleans successfully'; else bad "exact retained external terminal cleans successfully (rc=$CLEAN_RC)"; fi
assert_log_not_contains 'orchestration worker-release' 'retained terminal is not worker-released'
assert_log_contains 'terminal close --terminal term-target --json' 'retained cleanup closes exact metadata-bound terminal'
assert_log_contains 'worktree rm --worktree id:repo::worker --force --json' 'exact retained terminal permits worktree removal'

make_fixture retained-mismatch
run_cleanup retained-mismatch retained term-other
assert_failed_before_mutation retained-terminal-mismatch

for show_mode in retained-show-fail retained-show-invalid retained-show-live retained-show-mismatch; do
  make_fixture "$show_mode"
  run_cleanup "$show_mode" retained term-target 1
  if [ "$CLEAN_RC" -eq 2 ]; then ok "$show_mode exits 2"; else bad "$show_mode exits 2 (actual=$CLEAN_RC)"; fi
  assert_log_contains 'terminal close --terminal term-target --json' "$show_mode attempts only the exact terminal close"
  assert_log_contains 'terminal show --terminal term-target --json' "$show_mode performs authoritative disconnect readback"
  assert_log_not_contains 'tmux kill-session' "$show_mode does not kill tmux after unverifiable disconnect"
  assert_log_not_contains 'worktree rm' "$show_mode performs no worktree removal"
  if [ -d "$WORKTREE" ]; then ok "$show_mode preserves worktree"; else bad "$show_mode preserves worktree"; fi
done

make_fixture post-release-unknown
run_cleanup post-release-unknown
if [ "$CLEAN_RC" -eq 2 ]; then ok 'post-release unknown state exits 2'; else bad "post-release unknown state exits 2 (actual=$CLEAN_RC)"; fi
assert_count 'orchestration worker-release' 1 'post-release unknown records the one authorized release'
assert_count 'orchestration worker-list' 2 'post-release unknown performs authoritative recheck'
assert_log_not_contains 'terminal close' 'post-release unknown performs no direct terminal close'
assert_log_not_contains 'tmux kill-session' 'post-release unknown performs no tmux session kill'
assert_log_not_contains 'worktree rm' 'post-release unknown performs no worktree removal'
if [ -d "$WORKTREE" ]; then ok 'post-release unknown preserves worktree'; else bad 'post-release unknown preserves worktree'; fi
if git -C "$PROJECT" show-ref --verify --quiet "refs/heads/$BRANCH"; then ok 'post-release unknown preserves local branch'; else bad 'post-release unknown preserves local branch'; fi

printf 'clean-worktree WorkerList tests: %s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
