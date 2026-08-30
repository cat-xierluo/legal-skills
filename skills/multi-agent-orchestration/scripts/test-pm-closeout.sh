#!/usr/bin/env bash
# Deterministic contract tests for pm-closeout.sh. Uses a throwaway local Git
# remote plus fake gh/safe-push/verify executables; never reaches the network.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CLOSEOUT="$SCRIPT_DIR/pm-closeout.sh"
RESOLVER="$SCRIPT_DIR/pm-closeout-resolve.py"
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT

passed=0
failed=0
ok() { echo "  ✓ $1"; passed=$((passed + 1)); }
bad() { echo "  ✗ $1" >&2; failed=$((failed + 1)); }
assert_eq() {
  if [ "$1" = "$2" ]; then ok "$3"; else bad "$3 (expected=$2 actual=$1)"; fi
}

REMOTE="$TMP_ROOT/remote.git"
SEED="$TMP_ROOT/seed"
WT="$TMP_ROOT/worktree"
BIN="$TMP_ROOT/bin"
mkdir -p "$BIN"
git init -q --bare "$REMOTE"
git init -q "$SEED"
git -C "$SEED" config user.name "Closeout Test"
git -C "$SEED" config user.email "closeout@example.invalid"
printf 'base\n' > "$SEED/base.txt"
git -C "$SEED" add base.txt
git -C "$SEED" commit -q -m base
git -C "$SEED" branch -M main
git -C "$SEED" remote add origin "$REMOTE"
git -C "$SEED" push -q -u origin main
git --git-dir="$REMOTE" symbolic-ref HEAD refs/heads/main
git clone -q "$REMOTE" "$WT"
git -C "$WT" config user.name "Closeout Test"
git -C "$WT" config user.email "closeout@example.invalid"
git -C "$WT" checkout -q -b feat/closeout-test
printf 'change\n' > "$WT/change.txt"
git -C "$WT" add change.txt
git -C "$WT" commit -q -m change

SAFE_PUSH="$BIN/safe-push.sh"
cat > "$SAFE_PUSH" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%q ' "$@" >> "${PM_TEST_SAFE_LOG:?}"
printf '\n' >> "$PM_TEST_SAFE_LOG"
SH
chmod +x "$SAFE_PUSH"

VERIFY="$BIN/verify"
cat > "$VERIFY" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$#:$*" >> "${PM_TEST_VERIFY_LOG:?}"
[ "${PM_TEST_VERIFY_ADVANCE_MAIN:-0}" -eq 0 ] || {
  [ -n "${PM_TEST_ADVANCE_REPO:-}" ]
  advance_now=0
  advance_path=main-advanced.txt
  if [ "${PM_TEST_VERIFY_ADVANCE_ALWAYS:-0}" -eq 1 ]; then
    advance_round=$(wc -l < "$PM_TEST_VERIFY_LOG" | tr -d ' ')
    advance_path="main-advanced-$advance_round.txt"
    advance_now=1
  else
    [ -n "${PM_TEST_ADVANCE_MARKER:-}" ]
    [ -e "$PM_TEST_ADVANCE_MARKER" ] || advance_now=1
  fi
  if [ "$advance_now" -eq 1 ]; then
    printf 'main advanced\n' > "$PM_TEST_ADVANCE_REPO/$advance_path"
    git -C "$PM_TEST_ADVANCE_REPO" add "$advance_path"
    git -C "$PM_TEST_ADVANCE_REPO" commit -q -m 'main advances during verify'
    git -C "$PM_TEST_ADVANCE_REPO" push -q origin main
    if [ "${PM_TEST_VERIFY_ADVANCE_ALWAYS:-0}" -eq 0 ]; then
      : > "$PM_TEST_ADVANCE_MARKER"
    fi
  fi
}
[ "${PM_TEST_VERIFY_COMMIT:-0}" -eq 0 ] || git commit -q --allow-empty -m 'verify must not mutate git state'
[ "${PM_TEST_VERIFY_FAIL:-0}" -eq 0 ]
SH
chmod +x "$VERIFY"

GH="$BIN/gh"
cat > "$GH" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%q ' "$@" >> "${PM_TEST_GH_LOG:?}"
printf '\n' >> "$PM_TEST_GH_LOG"
case "$1 $2" in
  "pr create")
    [ "${PM_TEST_GH_MODE:-ok}" != "create-fail" ] || { echo "create failed" >&2; exit 41; }
    echo "https://example.invalid/repo/pull/123"
    ;;
  "pr merge")
    [ "${PM_TEST_GH_MODE:-ok}" != "merge-fail" ] || { echo "merge failed" >&2; exit 42; }
    ;;
  "pr view")
    [ "${PM_TEST_GH_MODE:-ok}" != "view-fail" ] || { echo "view failed" >&2; exit 43; }
    if [ "${PM_TEST_GH_MODE:-ok}" = "view-invalid" ]; then
      echo '{"state":null}'
    else
      echo '{"state":"MERGED"}'
    fi
    ;;
  *) echo "unexpected gh call: $*" >&2; exit 44 ;;
esac
SH
chmod +x "$GH"

export PATH="$BIN:$PATH"
export PM_TEST_SAFE_LOG="$TMP_ROOT/safe.log"
export PM_TEST_VERIFY_LOG="$TMP_ROOT/verify.log"
export PM_TEST_GH_LOG="$TMP_ROOT/gh.log"
: > "$PM_TEST_SAFE_LOG"
: > "$PM_TEST_VERIFY_LOG"
: > "$PM_TEST_GH_LOG"

echo "Case 1: legacy shell-string verification is rejected before execution"
set +e
bash "$CLOSEOUT" --worktree "$WT" --title test --safe-push-script "$SAFE_PUSH" \
  --verify 'touch should-not-run' > "$TMP_ROOT/legacy.out" 2>&1
legacy_rc=$?
set -e
assert_eq "$legacy_rc" "64" "legacy --verify is fail-closed"
[ ! -e "$WT/should-not-run" ] && ok "legacy verification text is never evaluated" || bad "legacy verification text was executed"

echo "Case 2: verification command is mandatory"
set +e
bash "$CLOSEOUT" --worktree "$WT" --title test --safe-push-script "$SAFE_PUSH" \
  > "$TMP_ROOT/no-verify.out" 2>&1
no_verify_rc=$?
set -e
assert_eq "$no_verify_rc" "64" "missing verification blocks closeout"

echo "Case 3: argv verification preserves spaces and gh create errors stay visible"
: > "$PM_TEST_VERIFY_LOG"
: > "$PM_TEST_GH_LOG"
set +e
PM_TEST_GH_MODE=create-fail bash "$CLOSEOUT" --worktree "$WT" --title test \
  --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --verify-arg 'arg with spaces' \
  --keep-branch > "$TMP_ROOT/create-fail.out" 2>&1
create_rc=$?
set -e
assert_eq "$create_rc" "5" "gh pr create failure blocks merge"
grep -qF '1:arg with spaces' "$PM_TEST_VERIFY_LOG" && ok "verification runs as an argv array" || bad "verification argv changed"
grep -qF 'create failed' "$TMP_ROOT/create-fail.out" && ok "gh create error is preserved" || bad "gh create error was swallowed"
if grep -qF 'pr merge' "$PM_TEST_GH_LOG"; then bad "merge ran after create failure"; else ok "merge does not run after create failure"; fi

echo "Case 4: gh state read/parse failures do not become success"
for mode in view-fail view-invalid; do
  : > "$PM_TEST_GH_LOG"
  set +e
  PM_TEST_GH_MODE="$mode" bash "$CLOSEOUT" --worktree "$WT" --title test \
    --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
    > "$TMP_ROOT/$mode.out" 2>&1
  rc=$?
  set -e
  assert_eq "$rc" "6" "$mode blocks completion"
done

echo "Case 5: happy path uses one body-file argument and confirms MERGED"
: > "$PM_TEST_GH_LOG"
PM_TEST_GH_MODE=ok bash "$CLOSEOUT" --worktree "$WT" --title test \
  --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/happy.out" 2>&1
grep -qF 'PM_CLOSEOUT_OK: pr=123 branch=feat/closeout-test' "$TMP_ROOT/happy.out" \
  && ok "happy path returns a mechanically extracted PR receipt" \
  || bad "happy path receipt missing"
create_line=$(grep -F 'pr create' "$PM_TEST_GH_LOG" | tail -1)
body_count=$(printf '%s\n' "$create_line" | grep -o -- '--body-file' | wc -l | tr -d ' ')
assert_eq "$body_count" "1" "PR create receives exactly one body-file"

echo "Case 6: resolver stages only declared document conflicts and ignores literal markers elsewhere"
DOC_REPO="$TMP_ROOT/doc-conflict"
git init -q "$DOC_REPO"
git -C "$DOC_REPO" config user.name "Closeout Test"
git -C "$DOC_REPO" config user.email "closeout@example.invalid"
git -C "$DOC_REPO" branch -M main
mkdir -p "$DOC_REPO/docs"
printf 'base\n' > "$DOC_REPO/docs/TASKS.md"
printf 'example: <<<<<<< literal >>>>>>>\n' > "$DOC_REPO/report.txt"
git -C "$DOC_REPO" add .
git -C "$DOC_REPO" commit -q -m base
git -C "$DOC_REPO" checkout -q -b feat/docs
printf 'worker entry\n' > "$DOC_REPO/docs/TASKS.md"
git -C "$DOC_REPO" commit -qam worker
git -C "$DOC_REPO" checkout -q main
printf 'main entry\n' > "$DOC_REPO/docs/TASKS.md"
git -C "$DOC_REPO" commit -qam main
git -C "$DOC_REPO" checkout -q feat/docs
set +e
git -C "$DOC_REPO" merge main >/dev/null 2>&1
doc_merge_rc=$?
set -e
[ "$doc_merge_rc" -ne 0 ] && ok "document fixture creates a real unmerged index" || bad "document fixture did not conflict"
set +e
(cd "$DOC_REPO" && python3 "$RESOLVER") > "$TMP_ROOT/doc-resolve.out" 2>&1
doc_resolve_rc=$?
set -e
assert_eq "$doc_resolve_rc" "0" "declared document conflict resolves and stages cleanly"
[ -z "$(git -C "$DOC_REPO" diff --name-only --diff-filter=U)" ] \
  && ok "resolved document is removed from the unmerged index" \
  || bad "resolved document remains unmerged"
grep -qF 'worker entry' "$DOC_REPO/docs/TASKS.md" \
  && grep -qF 'main entry' "$DOC_REPO/docs/TASKS.md" \
  && ok "document keep-both preserves both entries" \
  || bad "document keep-both lost one side"
grep -qF '<<<<<<< literal' "$DOC_REPO/report.txt" \
  && ok "literal marker outside resolved files is not a false positive" \
  || bad "unrelated literal marker changed"

echo "Case 7: semantic Makefile collisions fail closed and preserve the unmerged evidence"
MAKE_REPO="$TMP_ROOT/make-conflict"
git init -q "$MAKE_REPO"
git -C "$MAKE_REPO" config user.name "Closeout Test"
git -C "$MAKE_REPO" config user.email "closeout@example.invalid"
git -C "$MAKE_REPO" branch -M main
printf '.PHONY: test\ntest:\n\t@echo base\n' > "$MAKE_REPO/Makefile"
git -C "$MAKE_REPO" add Makefile
git -C "$MAKE_REPO" commit -q -m base
make_base=$(git -C "$MAKE_REPO" rev-parse HEAD)
git -C "$MAKE_REPO" checkout -q -b feat/make
printf '.PHONY: test lint\ntest:\n\t@echo worker\n' > "$MAKE_REPO/Makefile"
git -C "$MAKE_REPO" commit -qam worker
make_worker_tip=$(git -C "$MAKE_REPO" rev-parse HEAD)
git -C "$MAKE_REPO" checkout -q main
printf '.PHONY: test ci\ntest:\n\t@echo main\n' > "$MAKE_REPO/Makefile"
git -C "$MAKE_REPO" commit -qam main
make_main_tip=$(git -C "$MAKE_REPO" rev-parse HEAD)
git -C "$MAKE_REPO" checkout -q feat/make
set +e
git -C "$MAKE_REPO" merge main >/dev/null 2>&1
make_merge_rc=$?
set -e
[ "$make_merge_rc" -ne 0 ] && ok "Makefile fixture creates a real unmerged index" || bad "Makefile fixture did not conflict"
set +e
(cd "$MAKE_REPO" && python3 "$RESOLVER" \
  --worker-base "$make_base" --worker-tip "$make_worker_tip" --main-commit "$make_main_tip") \
  > "$TMP_ROOT/make-resolve.out" 2>&1
make_resolve_rc=$?
set -e
assert_eq "$make_resolve_rc" "3" "a patch that collides with main is refused"
grep -qF 'PM_CLOSEOUT_MAKEFILE_REPLAY_CONFLICT' "$TMP_ROOT/make-resolve.out" \
  && ok "Makefile replay reports the mechanical conflict" \
  || bad "Makefile replay conflict receipt missing"
[ "$(git -C "$MAKE_REPO" diff --name-only --diff-filter=U)" = "Makefile" ] \
  && ok "refused Makefile remains visibly unmerged" \
  || bad "refused Makefile conflict was hidden"

echo "Case 8: replay uses origin/main whole-file base and the frozen multi-commit Makefile range"
REPLAY_REPO="$TMP_ROOT/make-replay"
git init -q "$REPLAY_REPO"
git -C "$REPLAY_REPO" config user.name "Closeout Test"
git -C "$REPLAY_REPO" config user.email "closeout@example.invalid"
git -C "$REPLAY_REPO" branch -M main
mkdir -p "$REPLAY_REPO/docs"
{
  printf 'MODE ?= base\n'
  printf '# stable padding %s\n' 1 2 3 4 5 6 7 8
  printf '.PHONY: test\ntest:\n\t@echo test\n'
} > "$REPLAY_REPO/Makefile"
printf 'base task\n' > "$REPLAY_REPO/docs/TASKS.md"
git -C "$REPLAY_REPO" add .
git -C "$REPLAY_REPO" commit -q -m base
replay_base=$(git -C "$REPLAY_REPO" rev-parse HEAD)
git -C "$REPLAY_REPO" checkout -q -b feat/replay
sed -i.bak 's/MODE ?= base/MODE ?= worker/' "$REPLAY_REPO/Makefile"
rm -f "$REPLAY_REPO/Makefile.bak"
git -C "$REPLAY_REPO" commit -qam 'worker variable block'
printf '\n.PHONY: lint\nlint:\n\t@echo worker-lint\n' >> "$REPLAY_REPO/Makefile"
printf 'worker task\n' > "$REPLAY_REPO/docs/TASKS.md"
git -C "$REPLAY_REPO" commit -qam 'worker target block'
replay_worker_tip=$(git -C "$REPLAY_REPO" rev-parse HEAD)
git -C "$REPLAY_REPO" checkout -q main
printf 'main task\n' > "$REPLAY_REPO/docs/TASKS.md"
git -C "$REPLAY_REPO" commit -qam 'main task update'
replay_main_tip=$(git -C "$REPLAY_REPO" rev-parse HEAD)
git -C "$REPLAY_REPO" checkout -q feat/replay
set +e
git -C "$REPLAY_REPO" merge main >/dev/null 2>&1
replay_merge_rc=$?
set -e
[ "$replay_merge_rc" -ne 0 ] && ok "replay fixture keeps an active MERGE_HEAD" || bad "replay fixture did not conflict"
replay_base_blob=$(git -C "$REPLAY_REPO" rev-parse "$replay_base:Makefile")
replay_worker_blob=$(git -C "$REPLAY_REPO" rev-parse "$replay_worker_tip:Makefile")
replay_main_blob=$(git -C "$REPLAY_REPO" rev-parse "$replay_main_tip:Makefile")
printf '100644 %s 1\tMakefile\n100644 %s 2\tMakefile\n100644 %s 3\tMakefile\n' \
  "$replay_base_blob" "$replay_worker_blob" "$replay_main_blob" \
  | git -C "$REPLAY_REPO" update-index --index-info
set +e
(cd "$REPLAY_REPO" && python3 "$RESOLVER" \
  --worker-base "$replay_base" --worker-tip "$replay_worker_tip" --main-commit "$replay_main_tip") \
  > "$TMP_ROOT/make-replay.out" 2>&1
replay_rc=$?
set -e
if [ "$replay_rc" -ne 0 ]; then
  sed -n '1,120p' "$TMP_ROOT/make-replay.out" >&2
fi
assert_eq "$replay_rc" "0" "frozen multi-commit Makefile patch replays cleanly"
grep -qF 'PM_CLOSEOUT_MAKEFILE_REPLAYED_PENDING_VERIFY' "$TMP_ROOT/make-replay.out" \
  && ok "successful replay is explicitly pending verification" \
  || bad "successful replay receipt missing"
[ -z "$(git -C "$REPLAY_REPO" diff --name-only --diff-filter=U)" ] \
  && grep -qF 'MODE ?= worker' "$REPLAY_REPO/Makefile" \
  && grep -qF 'worker-lint' "$REPLAY_REPO/Makefile" \
  && ok "replay preserves both worker Makefile commits on the main blob" \
  || bad "multi-commit Makefile replay lost content or stayed unmerged"

echo "Case 9: main advancing during verify forces a new sync and a second verification"
ADV_REMOTE="$TMP_ROOT/advance-remote.git"
ADV_SEED="$TMP_ROOT/advance-seed"
ADV_WT="$TMP_ROOT/advance-worktree"
git init -q --bare "$ADV_REMOTE"
git init -q "$ADV_SEED"
git -C "$ADV_SEED" config user.name "Closeout Test"
git -C "$ADV_SEED" config user.email "closeout@example.invalid"
{
  printf 'MODE ?= base\n'
  printf '# stable padding %s\n' 1 2 3 4 5 6 7 8
  printf '.PHONY: test\ntest:\n\t@echo test\n'
} > "$ADV_SEED/Makefile"
git -C "$ADV_SEED" add Makefile
git -C "$ADV_SEED" commit -q -m base
git -C "$ADV_SEED" branch -M main
git -C "$ADV_SEED" remote add origin "$ADV_REMOTE"
git -C "$ADV_SEED" push -q -u origin main
git --git-dir="$ADV_REMOTE" symbolic-ref HEAD refs/heads/main
git clone -q "$ADV_REMOTE" "$ADV_WT"
git -C "$ADV_WT" config user.name "Closeout Test"
git -C "$ADV_WT" config user.email "closeout@example.invalid"
git -C "$ADV_WT" checkout -q -b feat/advance-main
sed -i.bak 's/MODE ?= base/MODE ?= worker/' "$ADV_WT/Makefile"
rm -f "$ADV_WT/Makefile.bak"
git -C "$ADV_WT" commit -qam 'worker variable block'
printf '\n.PHONY: lint\nlint:\n\t@echo worker-lint\n' >> "$ADV_WT/Makefile"
git -C "$ADV_WT" commit -qam 'worker target block'
: > "$PM_TEST_VERIFY_LOG"
: > "$PM_TEST_SAFE_LOG"
: > "$PM_TEST_GH_LOG"
set +e
PM_TEST_VERIFY_ADVANCE_MAIN=1 \
PM_TEST_ADVANCE_REPO="$ADV_SEED" \
PM_TEST_ADVANCE_MARKER="$TMP_ROOT/advance.marker" \
PM_TEST_GH_MODE=ok bash "$CLOSEOUT" --worktree "$ADV_WT" --title test \
  --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/advance.out" 2>&1
advance_rc=$?
set -e
if [ "$advance_rc" -ne 0 ]; then
  sed -n '1,160p' "$TMP_ROOT/advance.out" >&2
fi
assert_eq "$advance_rc" "0" "main-advance closeout completes"
verify_rounds=$(wc -l < "$PM_TEST_VERIFY_LOG" | tr -d ' ')
assert_eq "$verify_rounds" "2" "main movement forces verification to run again"
grep -qF 'PM_CLOSEOUT_MAIN_ADVANCED: round=1' "$TMP_ROOT/advance.out" \
  && ok "pre-push refresh observes the moving main" \
  || bad "main-advance receipt missing"
grep -qF 'MODE ?= worker' "$ADV_WT/Makefile" \
  && grep -qF 'worker-lint' "$ADV_WT/Makefile" \
  && grep -qF 'main advanced' "$ADV_WT/main-advanced.txt" \
  && ok "second sync preserves worker content and the newly advanced main" \
  || bad "main refresh lost worker or main content"
git -C "$ADV_WT" merge-base --is-ancestor origin/main HEAD \
  && ok "stable origin/main is an ancestor before safe-push" \
  || bad "closeout pushed from a stale main baseline"

echo "Case 10: continuously moving main exhausts the bounded loop before push or PR"
: > "$PM_TEST_VERIFY_LOG"
: > "$PM_TEST_SAFE_LOG"
: > "$PM_TEST_GH_LOG"
set +e
PM_TEST_VERIFY_ADVANCE_MAIN=1 \
PM_TEST_VERIFY_ADVANCE_ALWAYS=1 \
PM_TEST_ADVANCE_REPO="$ADV_SEED" \
PM_TEST_GH_MODE=ok bash "$CLOSEOUT" --worktree "$ADV_WT" --title test \
  --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/advance-always.out" 2>&1
advance_always_rc=$?
set -e
assert_eq "$advance_always_rc" "3" "continuous main movement fails closed"
advance_always_rounds=$(wc -l < "$PM_TEST_VERIFY_LOG" | tr -d ' ')
assert_eq "$advance_always_rounds" "3" "moving-main loop is bounded to three verification rounds"
grep -qF 'PM_CLOSEOUT_MAIN_MOVED_TOO_MANY_TIMES' "$TMP_ROOT/advance-always.out" \
  && ok "bounded-loop exhaustion has an explicit receipt" \
  || bad "bounded-loop exhaustion receipt missing"
[ ! -s "$PM_TEST_SAFE_LOG" ] && [ ! -s "$PM_TEST_GH_LOG" ] \
  && ok "safe-push and PR mutations never run after loop exhaustion" \
  || bad "external mutation ran after moving-main exhaustion"

echo "Case 11: a clean verify-side commit is detected as a forbidden Git state mutation"
: > "$PM_TEST_SAFE_LOG"
: > "$PM_TEST_GH_LOG"
set +e
PM_TEST_VERIFY_COMMIT=1 PM_TEST_GH_MODE=ok bash "$CLOSEOUT" \
  --worktree "$WT" --title test --safe-push-script "$SAFE_PUSH" \
  --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/verify-commit.out" 2>&1
verify_commit_rc=$?
set -e
assert_eq "$verify_commit_rc" "4" "clean verify-side commit fails closed"
grep -qF 'PM_CLOSEOUT_VERIFY_GIT_STATE_CHANGED' "$TMP_ROOT/verify-commit.out" \
  && ok "clean Git mutation has an explicit receipt" \
  || bad "clean Git mutation receipt missing"
[ ! -s "$PM_TEST_SAFE_LOG" ] && [ ! -s "$PM_TEST_GH_LOG" ] \
  && ok "no push or PR mutation follows a verify-side commit" \
  || bad "external mutation ran after verify changed HEAD"

printf 'pm-closeout tests: %s passed, %s failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
