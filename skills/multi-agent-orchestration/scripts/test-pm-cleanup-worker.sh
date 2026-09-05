#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CLEANUP="$SCRIPT_DIR/pm-cleanup-worker.sh"
TMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/pm-cleanup-worker.XXXXXX")
trap 'rm -rf "$TMP_ROOT"' EXIT
pass=0
fail=0

ok() { printf 'PASS: %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf 'FAIL: %s\n' "$1" >&2; fail=$((fail + 1)); }
assert_true() { local name=$1; shift; if "$@"; then ok "$name"; else bad "$name"; fi; }

BIN="$TMP_ROOT/bin"
mkdir -p "$BIN"
cat > "$BIN/gh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
head_oid=${PM_TEST_HEAD_OID:?}
head_ref=${PM_TEST_HEAD_REF:?}
merge_oid=${PM_TEST_MERGE_OID:?}
base_ref=${PM_TEST_BASE_REF:-main}
case ${PM_TEST_GH_MODE:-merged} in
  merged)
    jq -cn --arg base "$base_ref" --arg head "$head_ref" --arg oid "$head_oid" --arg merge "$merge_oid" \
      '{state:"MERGED",mergedAt:"2026-09-05T00:00:00Z",baseRefName:$base,headRefName:$head,headRefOid:$oid,mergeCommit:{oid:$merge}}'
    ;;
  open)
    jq -cn --arg base "$base_ref" --arg head "$head_ref" --arg oid "$head_oid" \
      '{state:"OPEN",mergedAt:null,baseRefName:$base,headRefName:$head,headRefOid:$oid,mergeCommit:null}'
    ;;
  wrong-head)
    jq -cn --arg base "$base_ref" --arg head "$head_ref" --arg merge "$merge_oid" \
      '{state:"MERGED",mergedAt:"2026-09-05T00:00:00Z",baseRefName:$base,headRefName:$head,headRefOid:"0000000000000000000000000000000000000000",mergeCommit:{oid:$merge}}'
    ;;
  unknown)
    jq -cn --arg base "$base_ref" --arg head "$head_ref" --arg oid "$head_oid" \
      '{state:"UNKNOWN",mergedAt:null,baseRefName:$base,headRefName:$head,headRefOid:$oid,mergeCommit:null}'
    ;;
esac
SH
chmod +x "$BIN/gh"
export PATH="$BIN:$PATH"

make_fixture() {
  local name=$1
  ORIGIN="$TMP_ROOT/$name-origin.git"
  PROJECT="$TMP_ROOT/$name-project"
  WORKTREE="$TMP_ROOT/$name-worktree"
  BRANCH="feat/$name"
  SESSION="$name-session"
  git init --bare --initial-branch=main "$ORIGIN" >/dev/null
  git clone -q "$ORIGIN" "$PROJECT"
  git -C "$PROJECT" config user.name Test
  git -C "$PROJECT" config user.email test@example.invalid
  printf 'base\n' > "$PROJECT/base.txt"
  printf '.claude/agent-sessions/\n' > "$PROJECT/.gitignore"
  git -C "$PROJECT" add base.txt .gitignore
  git -C "$PROJECT" commit -qm base
  git -C "$PROJECT" push -q -u origin main
  git -C "$PROJECT" worktree add -q -b "$BRANCH" "$WORKTREE" main
  printf '%s\n' "$name" > "$WORKTREE/$name.txt"
  git -C "$WORKTREE" add "$name.txt"
  git -C "$WORKTREE" commit -qm "$name"
  git -C "$WORKTREE" push -q -u origin "$BRANCH"
  TIP=$(git -C "$WORKTREE" rev-parse HEAD)
  mkdir -p "$WORKTREE/.claude/agent-sessions/$SESSION"
  jq -n --arg project "$PROJECT" --arg worktree "$WORKTREE" --arg branch "$BRANCH" --arg session "$SESSION" \
    '{project:$project,worktree:$worktree,branch:$branch,branch_lifecycle:"ephemeral-worker",base_ref:"origin/main",session:{id:$session},runtime:{provider_lease:{file:""}}}' \
    > "$WORKTREE/.claude/agent-sessions/$SESSION/METADATA.json"
}

run_cleanup() {
  env PM_TEST_HEAD_OID="$TIP" PM_TEST_HEAD_REF="$BRANCH" PM_TEST_MERGE_OID="$DELIVERY_COMMIT" \
    PM_TEST_BASE_REF="${PM_TEST_BASE_REF:-main}" \
    PM_TEST_GH_MODE="${PM_TEST_GH_MODE:-merged}" \
    bash "$CLEANUP" --worktree "$WORKTREE" --branch "$BRANCH" --pr 123 \
      --expected-tip "$TIP" --delivery-mode "$DELIVERY_MODE" \
      --delivery-commit "$DELIVERY_COMMIT" --repository github.com/example/project "$@"
}

make_fixture merged-cleanup
DELIVERY_MODE=remote-pr
DELIVERY_COMMIT=$(git -C "$PROJECT" rev-parse main)

printf 'dirty\n' > "$WORKTREE/dirty.txt"
set +e
run_cleanup --execute > "$TMP_ROOT/dirty.out" 2>&1
dirty_rc=$?
set -e
[ "$dirty_rc" -eq 2 ] && ok "dirty worktree fails closed" || bad "dirty worktree fails closed"
assert_true "dirty refusal preserves worktree" test -d "$WORKTREE"
assert_true "dirty refusal preserves local branch" git -C "$PROJECT" show-ref --verify --quiet "refs/heads/$BRANCH"
assert_true "dirty refusal preserves remote branch" sh -c "test -n \"\$(git -C '$PROJECT' ls-remote --heads origin 'refs/heads/$BRANCH')\""
rm -f "$WORKTREE/dirty.txt"

set +e
PM_TEST_GH_MODE=wrong-head run_cleanup --execute > "$TMP_ROOT/wrong-head.out" 2>&1
wrong_head_rc=$?
set -e
[ "$wrong_head_rc" -eq 2 ] && ok "PR head mismatch fails closed" || bad "PR head mismatch fails closed"
assert_true "PR mismatch preserves worktree" test -d "$WORKTREE"

set +e
PM_TEST_BASE_REF=integration/other run_cleanup --execute > "$TMP_ROOT/wrong-base.out" 2>&1
wrong_base_rc=$?
set -e
[ "$wrong_base_rc" -eq 2 ] && ok "PR base mismatch fails closed" || bad "PR base mismatch fails closed"
assert_true "PR base mismatch preserves worktree" test -d "$WORKTREE"

set +e
run_cleanup --branch-lifecycle long-lived --execute > "$TMP_ROOT/protective-upgrade.out" 2>&1
protective_upgrade_rc=$?
set -e
[ "$protective_upgrade_rc" -eq 11 ] && ok "caller may conservatively upgrade an ephemeral branch to long-lived" || bad "caller may conservatively upgrade an ephemeral branch to long-lived"
assert_true "protective lifecycle upgrade performs no deletion" test -d "$WORKTREE"

metadata_file="$WORKTREE/.claude/agent-sessions/$SESSION/METADATA.json"
metadata_backup=$(mktemp "$TMP_ROOT/metadata.XXXXXX")
cp "$metadata_file" "$metadata_backup"
printf '{invalid\n' > "$metadata_file"
set +e
run_cleanup --execute > "$TMP_ROOT/invalid-metadata.out" 2>&1
invalid_metadata_rc=$?
set -e
[ "$invalid_metadata_rc" -eq 2 ] && ok "invalid metadata fails closed" || bad "invalid metadata fails closed"
assert_true "invalid metadata preserves worktree" test -d "$WORKTREE"
cp "$metadata_backup" "$metadata_file"

original_origin=$(git -C "$PROJECT" remote get-url origin)
git -C "$PROJECT" remote set-url origin "file:///definitely/missing/pm-cleanup-origin.git"
set +e
run_cleanup --execute > "$TMP_ROOT/remote-query.out" 2>&1
remote_query_rc=$?
set -e
[ "$remote_query_rc" -eq 2 ] && ok "remote query failure fails closed" || bad "remote query failure fails closed"
assert_true "remote query failure preserves worktree" test -d "$WORKTREE"
git -C "$PROJECT" remote set-url origin "$original_origin"

run_cleanup > "$TMP_ROOT/dry-run.out"
assert_true "dry-run reports planned cleanup" grep -qF 'PM_CLEANUP_RESULT: DRY_RUN' "$TMP_ROOT/dry-run.out"
assert_true "dry-run keeps worktree" test -d "$WORKTREE"

run_cleanup --execute > "$TMP_ROOT/merged.out"
assert_true "merged delivery reports CLEANED" grep -qF 'PM_CLEANUP_RESULT: CLEANED' "$TMP_ROOT/merged.out"
if [ ! -d "$WORKTREE" ]; then ok "merged cleanup removes worktree"; else bad "merged cleanup removes worktree"; fi
if ! git -C "$PROJECT" show-ref --verify --quiet "refs/heads/$BRANCH"; then ok "merged cleanup deletes exact local branch"; else bad "merged cleanup deletes exact local branch"; fi
if [ -z "$(git -C "$PROJECT" ls-remote --heads origin "refs/heads/$BRANCH")" ]; then ok "merged cleanup deletes exact remote branch"; else bad "merged cleanup deletes exact remote branch"; fi

make_fixture feature-integration
git -C "$PROJECT" branch integration/feature main
git -C "$PROJECT" push -q origin integration/feature
metadata_file="$WORKTREE/.claude/agent-sessions/$SESSION/METADATA.json"
jq '.base_ref = "origin/integration/feature"' "$metadata_file" > "$metadata_file.tmp"
mv "$metadata_file.tmp" "$metadata_file"
DELIVERY_MODE=remote-pr
DELIVERY_COMMIT=$(git -C "$PROJECT" rev-parse integration/feature)
PM_TEST_BASE_REF=integration/feature run_cleanup --integration-target integration/feature --execute > "$TMP_ROOT/feature-target.out"
assert_true "ephemeral head merged into long-lived target is cleaned" grep -qF 'PM_CLEANUP_RESULT: CLEANED' "$TMP_ROOT/feature-target.out"
assert_true "long-lived integration target remains local" git -C "$PROJECT" show-ref --verify --quiet refs/heads/integration/feature
assert_true "long-lived integration target remains remote" sh -c "test -n \"\$(git -C '$PROJECT' ls-remote --heads origin refs/heads/integration/feature)\""

make_fixture retained-line
metadata_file="$WORKTREE/.claude/agent-sessions/$SESSION/METADATA.json"
jq '.branch_lifecycle = "long-lived"' "$metadata_file" > "$metadata_file.tmp"
mv "$metadata_file.tmp" "$metadata_file"
DELIVERY_MODE=remote-pr
DELIVERY_COMMIT=$(git -C "$PROJECT" rev-parse main)
set +e
run_cleanup --execute > "$TMP_ROOT/long-lived.out" 2>&1
long_lived_rc=$?
set -e
[ "$long_lived_rc" -eq 11 ] && ok "long-lived source reports RETAINED_WITH_REASON" || bad "long-lived source reports RETAINED_WITH_REASON"
assert_true "long-lived reason is explicit" grep -qF 'reason=long-lived-branch' "$TMP_ROOT/long-lived.out"
assert_true "long-lived worktree is retained" test -d "$WORKTREE"
assert_true "long-lived local branch is retained" git -C "$PROJECT" show-ref --verify --quiet "refs/heads/$BRANCH"
assert_true "long-lived remote branch is retained" sh -c "test -n \"\$(git -C '$PROJECT' ls-remote --heads origin 'refs/heads/$BRANCH')\""

set +e
run_cleanup --branch-lifecycle ephemeral-worker --execute > "$TMP_ROOT/lifecycle-mismatch.out" 2>&1
lifecycle_mismatch_rc=$?
set -e
[ "$lifecycle_mismatch_rc" -eq 2 ] && ok "caller cannot downgrade long-lived metadata" || bad "caller cannot downgrade long-lived metadata"
assert_true "lifecycle mismatch still retains worktree" test -d "$WORKTREE"

make_fixture local-open
DELIVERY_MODE=local-after-pr
git -C "$PROJECT" merge --squash "$BRANCH" >/dev/null
git -C "$PROJECT" commit -qm 'integrate local-open'
git -C "$PROJECT" push -q origin main
DELIVERY_COMMIT=$(git -C "$PROJECT" rev-parse main)
set +e
PM_TEST_GH_MODE=unknown run_cleanup --execute > "$TMP_ROOT/unknown-state.out" 2>&1
unknown_state_rc=$?
set -e
[ "$unknown_state_rc" -eq 2 ] && ok "unknown PR state fails closed" || bad "unknown PR state fails closed"
assert_true "unknown PR state preserves worktree" test -d "$WORKTREE"
set +e
PM_TEST_GH_MODE=open run_cleanup --execute > "$TMP_ROOT/open.out" 2>&1
open_rc=$?
set -e
[ "$open_rc" -eq 11 ] && ok "open PR produces RETAINED_WITH_REASON" || bad "open PR produces RETAINED_WITH_REASON"
assert_true "open PR retention is explicit" grep -qF 'PM_CLEANUP_RESULT: RETAINED_WITH_REASON' "$TMP_ROOT/open.out"
if [ ! -d "$WORKTREE" ]; then ok "open PR still reclaims local worktree"; else bad "open PR still reclaims local worktree"; fi
if ! git -C "$PROJECT" show-ref --verify --quiet "refs/heads/$BRANCH"; then ok "open PR still reclaims local branch"; else bad "open PR still reclaims local branch"; fi
if [ -n "$(git -C "$PROJECT" ls-remote --heads origin "refs/heads/$BRANCH")" ]; then ok "open PR retains remote branch"; else bad "open PR retains remote branch"; fi

printf 'pm-cleanup-worker tests: %s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
