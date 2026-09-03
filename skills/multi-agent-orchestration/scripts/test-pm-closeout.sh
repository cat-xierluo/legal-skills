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
[ "${PM_TEST_SAFE_LEAK:-0}" -eq 0 ] || { echo 'fatal: https://user:LEAK-ME@example.invalid/repository.git failed' >&2; exit 72; }
[ "${PM_TEST_SAFE_FAIL:-0}" -eq 0 ] || exit 71
if [ "${PM_TEST_SAFE_DO_PUSH:-0}" -eq 1 ]; then
  repo=.; branch=
  while [ $# -gt 0 ]; do
    case "$1" in --repo) repo=$2; shift 2 ;; --branch) branch=$2; shift 2 ;; *) shift ;; esac
  done
  git -C "$repo" push -q origin "$branch"
  if [ -n "${PM_TEST_DIRTY_MAIN_AFTER_PUSH:-}" ]; then
    printf 'post-push drift\n' > "$PM_TEST_DIRTY_MAIN_AFTER_PUSH/post-push-drift.txt"
  fi
fi
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
  elif [ -n "${PM_TEST_VERIFY_ADVANCE_AT_CALL:-}" ]; then
    advance_round=$(wc -l < "$PM_TEST_VERIFY_LOG" | tr -d ' ')
    if [ "$advance_round" = "$PM_TEST_VERIFY_ADVANCE_AT_CALL" ]; then
      advance_path="main-advanced-at-$advance_round.txt"
      advance_now=1
    fi
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
  "pr list")
    if [ "${PM_TEST_GH_MODE:-ok}" = "post-create-audit-fail" ] && grep -qF 'pr create' "$PM_TEST_GH_LOG"; then
      echo 'post-create list unavailable' >&2
      exit 45
    fi
    if [ "${PM_TEST_GH_MODE:-ok}" = "existing" ] || [ "${PM_TEST_GH_MODE:-ok}" = "diff-leak" ] || [ "${PM_TEST_GH_MODE:-ok}" = "check-drift" ] || \
       [ "${PM_TEST_GH_MODE:-ok}" = "duplicate-final" ] || [ "${PM_TEST_GH_MODE:-ok}" = "base-race" ] || \
       [ "${PM_TEST_GH_MODE:-ok}" = "view-fail-after-merge" ] || [ "${PM_TEST_GH_MODE:-ok}" = "close-view-fail" ] || \
       { [ "${PM_TEST_GH_MODE:-ok}" != "create-fail" ] && grep -qF 'pr create' "$PM_TEST_GH_LOG"; }; then
      head_oid=$(git rev-parse HEAD)
      base_oid=$(git rev-parse origin/main)
      row=$(printf '{"number":123,"url":"https://example.invalid/repo/pull/123","baseRefName":"main","baseRefOid":"%s","headRefName":"%s","headRefOid":"%s","headRepositoryOwner":{"login":"repository"},"isCrossRepository":false,"title":"Task-097 by agent-test","body":"Task: Task-097\\nAgent: agent-test","reviewDecision":"APPROVED","statusCheckRollup":[]}' "$base_oid" "$(git branch --show-current)" "$head_oid")
      if { [ "${PM_TEST_GH_MODE:-ok}" = "duplicate-final" ] && [ "$(grep -cF 'pr list' "$PM_TEST_GH_LOG")" -ge 2 ]; } || \
         { [ "${PM_TEST_GH_MODE:-ok}" = "create-suspected" ] && grep -qF 'pr create' "$PM_TEST_GH_LOG"; }; then
        row2=${row/\"number\":123/\"number\":124}; row2=${row2/pull\/123/pull\/124}
        row2=${row2/\"headRefName\":\"$(git branch --show-current)\"/\"headRefName\":\"feat\/same-content-race\"}
        printf '[%s,%s]\n' "$row" "$row2"
      else
        printf '[%s]\n' "$row"
      fi
    else
      echo '[]'
    fi
    ;;
  "pr diff")
    if [ "${PM_TEST_GH_MODE:-ok}" = "diff-leak" ] && \
       [ "$(grep -cF 'pr diff' "$PM_TEST_GH_LOG")" -ge 2 ]; then
      echo 'fatal: https://user:PR-DIFF-LEAK@example.invalid/repository.git?access_token=DIFF-TOKEN failed' >&2
      exit 46
    fi
    base=$(git merge-base HEAD origin/main)
    git diff "$base" HEAD
    ;;
  "pr create")
    [ "${PM_TEST_GH_MODE:-ok}" != "create-fail" ] || { echo "create failed" >&2; exit 41; }
    [ "${PM_TEST_GH_MODE:-ok}" != "race" ] || { echo "a pull request already exists" >&2; exit 41; }
    echo "https://example.invalid/repo/pull/123"
    ;;
  "pr merge")
    [ "${PM_TEST_GH_MODE:-ok}" != "merge-fail" ] || { echo "merge failed" >&2; exit 42; }
    if [ "${PM_TEST_GH_MODE:-ok}" != "view-fail" ] && [ "${PM_TEST_GH_MODE:-ok}" != "view-invalid" ]; then
      main_oid=$(git rev-parse origin/main)
      head_oid=$(git rev-parse HEAD)
      if [ "${PM_TEST_GH_MODE:-ok}" = "base-race" ]; then
        advance_oid=$(printf 'main advanced after final review\n' | git commit-tree "$(git rev-parse "$main_oid^{tree}")" -p "$main_oid")
        git push -q origin "$advance_oid:refs/heads/main"
        main_oid=$advance_oid
      fi
      tree_oid=$(git merge-tree --write-tree "$main_oid" "$head_oid")
      merge_oid=$(printf 'fake squash merge\n' | git commit-tree "$tree_oid" -p "$main_oid")
      git push -q origin "$merge_oid:refs/heads/main"
      printf '%s\n' "$merge_oid" > "${PM_TEST_MERGE_SHA_FILE:?}"
    fi
    ;;
  "pr view")
    if grep -qF 'pr close' "$PM_TEST_GH_LOG"; then
      [ "${PM_TEST_GH_MODE:-ok}" != "close-view-fail" ] || { echo "close state unavailable" >&2; exit 43; }
      echo '{"state":"CLOSED"}'
    elif grep -qF 'pr merge' "$PM_TEST_GH_LOG"; then
      [ "${PM_TEST_GH_MODE:-ok}" != "view-fail" ] && [ "${PM_TEST_GH_MODE:-ok}" != "view-fail-after-merge" ] || { echo "view failed" >&2; exit 43; }
      if [ "${PM_TEST_GH_MODE:-ok}" = "view-invalid" ]; then
        echo '{"state":"MERGED","mergedAt":null,"mergeCommit":null}'
      else
        merge_oid=$(cat "${PM_TEST_MERGE_SHA_FILE:?}")
        printf '{"state":"MERGED","mergedAt":"2026-09-04T00:00:00Z","mergeCommit":{"oid":"%s"}}\n' "$merge_oid"
      fi
    else
      head_oid=$(git rev-parse HEAD)
      base_oid=$(git rev-parse origin/main)
      checks='[]'
      if [ "${PM_TEST_GH_MODE:-ok}" = "check-drift" ] && [ "$(grep -cF 'pr view' "$PM_TEST_GH_LOG")" -ge 2 ]; then
        checks='[{"name":"ci","status":"COMPLETED","conclusion":"NEUTRAL"}]'
      fi
      printf '{"number":123,"url":"https://example.invalid/repo/pull/123","state":"OPEN","baseRefName":"main","baseRefOid":"%s","headRefName":"%s","headRefOid":"%s","statusCheckRollup":%s,"reviewDecision":"APPROVED","mergeable":"MERGEABLE","mergedAt":null,"mergeCommit":null}\n' "$base_oid" "$(git branch --show-current)" "$head_oid" "$checks"
    fi
    ;;
  "pr close") ;;
  "api --hostname")
    if [[ "${4:-}" == */rules/branches/main ]]; then
      case "${PM_TEST_PROTECTION_MODE:-unprotected}" in
        merge-queue) echo '[{"type":"merge_queue"}]' ;;
        rules-404) echo 'HTTP 404' >&2; exit 1 ;;
        *) echo '[]' ;;
      esac
    else
      case "${PM_TEST_PROTECTION_MODE:-unprotected}" in
        unprotected|flip-protection)
          if [ "${PM_TEST_PROTECTION_MODE:-}" = "flip-protection" ] && \
             [ "$(grep -cF '/branches/main' "$PM_TEST_GH_LOG")" -ge 2 ]; then
            echo '{"protected":true}'
          else
            echo '{"protected":false}'
          fi
          ;;
        protected|classic-protected|merge-queue) echo '{"protected":true}' ;;
        404) echo 'HTTP 404' >&2; exit 1 ;;
        malformed) echo '{}' ;;
        *) exit 1 ;;
      esac
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
export PM_TEST_MERGE_SHA_FILE="$TMP_ROOT/merge-sha"
export PM_CLOSEOUT_MODE=remote-pr
export PM_CLOSEOUT_TASK_ID=Task-097
export PM_CLOSEOUT_AGENT_ID=agent-test
: > "$PM_TEST_SAFE_LOG"
: > "$PM_TEST_VERIFY_LOG"
: > "$PM_TEST_GH_LOG"

authority_for() {
  local repo=$1 operation=$2 pr_number=${3:-none} remote_url leaf remote_id branch sha
  remote_url=$(git -C "$repo" remote get-url origin)
  leaf=${remote_url##*/}; leaf=${leaf%.git}
  remote_id="local/repository/$leaf"
  branch=$(git -C "$repo" branch --show-current)
  sha=$(git -C "$repo" rev-parse HEAD)
  printf 'operation=%s;repo=%s;pr=%s;head=%s;sha=%s' "$operation" "$remote_id" "$pr_number" "$branch" "$sha"
}

candidate_authority_for() {
  local repo=$1 operation=$2 pr_number=$3 title=$4 remote_url leaf remote_id branch sha base tree candidate date
  remote_url=$(git -C "$repo" remote get-url origin)
  leaf=${remote_url##*/}; leaf=${leaf%.git}
  remote_id="local/repository/$leaf"
  branch=$(git -C "$repo" branch --show-current)
  sha=$(git -C "$repo" rev-parse HEAD)
  base=$(git -C "$repo" rev-parse origin/main)
  tree=$(git -C "$repo" merge-tree --write-tree "$base" "$sha")
  date=$(git -C "$repo" show -s --format=%aI "$sha")
  candidate=$(GIT_AUTHOR_DATE="$date" GIT_COMMITTER_DATE="$date" \
    git -C "$repo" -c user.name="$(git -C "$repo" config user.name)" \
      -c user.email="$(git -C "$repo" config user.email)" \
      commit-tree "$tree" -p "$base" -m "$title (#$pr_number)")
  printf 'operation=%s;repo=%s;pr=%s;head=%s;sha=%s;base=%s;candidate=%s;tree=%s' \
    "$operation" "$remote_id" "$pr_number" "$branch" "$sha" "$base" "$candidate" "$tree"
}

INITIAL_ARGS=(
  --integration-path change.txt
  --authorize-branch-push "$(authority_for "$WT" branch-push)"
  --authorize-pr-create "$(authority_for "$WT" pr-create)"
  --authorize-remote-merge "$(authority_for "$WT" remote-merge 123)"
  --authorize-remote-candidate "$(candidate_authority_for "$WT" remote-merge-candidate 123 test)"
  --authorize-main-push "$(authority_for "$WT" main-push 123)"
  --authorize-main-candidate "$(candidate_authority_for "$WT" main-push-candidate 123 test)"
  --authorize-pr-close "$(authority_for "$WT" pr-close 123)"
)
INITIAL_MAIN_SHA=$(git -C "$WT" rev-parse origin/main)

echo "Case 1: legacy shell-string verification is rejected before execution"
set +e
bash "$CLOSEOUT" --worktree "$WT" --title test --safe-push-script "$SAFE_PUSH" \
  "${INITIAL_ARGS[@]}" --verify 'touch should-not-run' > "$TMP_ROOT/legacy.out" 2>&1
legacy_rc=$?
set -e
assert_eq "$legacy_rc" "64" "legacy --verify is fail-closed"
[ ! -e "$WT/should-not-run" ] && ok "legacy verification text is never evaluated" || bad "legacy verification text was executed"

echo "Case 2: verification command is mandatory"
set +e
bash "$CLOSEOUT" --worktree "$WT" --title test --safe-push-script "$SAFE_PUSH" \
  "${INITIAL_ARGS[@]}" > "$TMP_ROOT/no-verify.out" 2>&1
no_verify_rc=$?
set -e
assert_eq "$no_verify_rc" "64" "missing verification blocks closeout"

echo "Case 3: argv verification preserves spaces and gh create errors stay visible"
: > "$PM_TEST_VERIFY_LOG"
: > "$PM_TEST_GH_LOG"
set +e
PM_TEST_GH_MODE=create-fail bash "$CLOSEOUT" --worktree "$WT" --title test \
  --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --verify-arg 'arg with spaces' \
  "${INITIAL_ARGS[@]}" --keep-branch > "$TMP_ROOT/create-fail.out" 2>&1
create_rc=$?
set -e
assert_eq "$create_rc" "9" "gh pr create failure becomes an explicit outcome-unknown state"
grep -qF '1:arg with spaces' "$PM_TEST_VERIFY_LOG" && ok "verification runs as an argv array" || bad "verification argv changed"
grep -qF 'create failed' "$TMP_ROOT/create-fail.out" && ok "gh create error is preserved" || bad "gh create error was swallowed"
if grep -qF 'pr merge' "$PM_TEST_GH_LOG"; then bad "merge ran after create failure"; else ok "merge does not run after create failure"; fi

echo "Case 4: gh state read/parse failures do not become success"
for mode in view-fail view-invalid; do
  : > "$PM_TEST_GH_LOG"
  set +e
  PM_TEST_GH_MODE="$mode" bash "$CLOSEOUT" --worktree "$WT" --title test \
    --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
    "${INITIAL_ARGS[@]}" > "$TMP_ROOT/$mode.out" 2>&1
  rc=$?
  set -e
  assert_eq "$rc" "9" "$mode blocks success with outcome unknown"
done

echo "Case 5: happy path uses one body-file argument and confirms MERGED"
: > "$PM_TEST_GH_LOG"
PM_TEST_GH_MODE=ok bash "$CLOSEOUT" --worktree "$WT" --title test \
  --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  "${INITIAL_ARGS[@]}" > "$TMP_ROOT/happy.out" 2>&1
grep -qF 'PM_CLOSEOUT_RESULT: REMOTE_PR pr=123' "$TMP_ROOT/happy.out" \
  && ok "happy path returns a mechanically extracted PR receipt" \
  || bad "happy path receipt missing"
create_line=$(grep -F 'pr create' "$PM_TEST_GH_LOG" | tail -1)
body_count=$(printf '%s\n' "$create_line" | grep -o -- '--body-file' | wc -l | tr -d ' ')
assert_eq "$body_count" "1" "PR create receives exactly one body-file"
git --git-dir="$REMOTE" update-ref refs/heads/main "$INITIAL_MAIN_SHA"
git -C "$WT" fetch -q origin main

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
ADV_ARGS=(
  --integration-path Makefile
  --authorize-branch-push "$(authority_for "$ADV_WT" branch-push)"
  --authorize-pr-create "$(authority_for "$ADV_WT" pr-create)"
  --authorize-remote-merge "$(authority_for "$ADV_WT" remote-merge 123)"
)
: > "$PM_TEST_VERIFY_LOG"
: > "$PM_TEST_SAFE_LOG"
: > "$PM_TEST_GH_LOG"
set +e
PM_TEST_VERIFY_ADVANCE_MAIN=1 \
PM_TEST_ADVANCE_REPO="$ADV_SEED" \
PM_TEST_ADVANCE_MARKER="$TMP_ROOT/advance.marker" \
PM_TEST_GH_MODE=ok bash "$CLOSEOUT" --worktree "$ADV_WT" --title test \
  --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  "${ADV_ARGS[@]}" > "$TMP_ROOT/advance.out" 2>&1
advance_rc=$?
set -e
assert_eq "$advance_rc" "8" "main movement invalidates the pre-candidate authorization"
ADV_CANDIDATE_AUTH=$(sed -n 's/^PM_CLOSEOUT_CANDIDATE_AUTHORIZATION_REQUIRED: operation=remote-merge-candidate expected=//p' "$TMP_ROOT/advance.out" | tail -1)
[ -n "$ADV_CANDIDATE_AUTH" ] && ok "main-advance emits a candidate-bound authorization challenge" || bad "candidate challenge missing"
set +e
PM_TEST_GH_MODE=ok bash "$CLOSEOUT" --worktree "$ADV_WT" --title test \
  --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  "${ADV_ARGS[@]}" --authorize-remote-candidate "$ADV_CANDIDATE_AUTH" \
  > "$TMP_ROOT/advance-retry.out" 2>&1
advance_retry_rc=$?
set -e
if [ "$advance_retry_rc" -ne 0 ]; then
  sed -n '1,160p' "$TMP_ROOT/advance-retry.out" >&2
fi
assert_eq "$advance_retry_rc" "0" "candidate-bound reauthorization completes main-advance closeout"
if [ "$advance_rc" -ne 8 ]; then
  sed -n '1,160p' "$TMP_ROOT/advance.out" >&2
fi
verify_rounds=$(wc -l < "$PM_TEST_VERIFY_LOG" | tr -d ' ')
assert_eq "$verify_rounds" "4" "main movement plus reauthorization reruns worker and candidate verification"
grep -qF 'PM_CLOSEOUT_CANDIDATE_VERIFIED: pr=123' "$TMP_ROOT/advance.out" \
  && ok "PR-first candidate verification emits a stable receipt" \
  || bad "candidate verification receipt missing"
grep -qF 'MODE ?= worker' "$ADV_WT/Makefile" \
  && grep -qF 'worker-lint' "$ADV_WT/Makefile" \
  && git -C "$ADV_WT" show origin/main:main-advanced.txt | grep -qF 'main advanced' \
  && [ ! -e "$ADV_WT/main-advanced.txt" ] \
  && ok "PR-first keeps worker head immutable while candidate consumes fresh main" \
  || bad "worker head or refreshed main evidence changed unexpectedly"
[ "$(git -C "$ADV_WT" branch --show-current)" = 'feat/advance-main' ] \
  && ok "candidate verification never checks out or mutates main in the worker tree" \
  || bad "worker branch changed during candidate verification"
ADV_MAIN_AFTER_VERIFY=$(git -C "$ADV_WT" rev-parse 'origin/main^1')
git --git-dir="$ADV_REMOTE" update-ref refs/heads/main "$ADV_MAIN_AFTER_VERIFY"
git -C "$ADV_WT" fetch -q origin main

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
  "${ADV_ARGS[@]}" > "$TMP_ROOT/advance-always.out" 2>&1
advance_always_rc=$?
set -e
assert_eq "$advance_always_rc" "3" "continuous main movement fails closed"
advance_always_rounds=$(wc -l < "$PM_TEST_VERIFY_LOG" | tr -d ' ')
assert_eq "$advance_always_rounds" "4" "one worker verify plus three candidate rounds bounds moving-main verification"
grep -qF 'PM_CLOSEOUT_MAIN_MOVED_TOO_MANY_TIMES' "$TMP_ROOT/advance-always.out" \
  && ok "bounded-loop exhaustion has an explicit receipt" \
  || bad "bounded-loop exhaustion receipt missing"
if grep -qF 'pr merge' "$PM_TEST_GH_LOG"; then
  bad "merge ran after moving-main exhaustion"
else
  ok "moving-main exhaustion performs no merge or main integration mutation"
fi

echo "Case 11: a clean verify-side commit is detected as a forbidden Git state mutation"
: > "$PM_TEST_SAFE_LOG"
: > "$PM_TEST_GH_LOG"
set +e
PM_TEST_VERIFY_COMMIT=1 PM_TEST_GH_MODE=ok bash "$CLOSEOUT" \
  --worktree "$WT" --title test --safe-push-script "$SAFE_PUSH" \
  --verify-cmd "$VERIFY" "${INITIAL_ARGS[@]}" --keep-branch \
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

echo "Case 12: create race re-audits and adopts the unique worker PR without a second create"
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=race PM_CLOSEOUT_MODE=remote-pr bash "$CLOSEOUT" \
  --worktree "$WT" --title test --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" \
  --integration-path change.txt \
  --authorize-branch-push "$(authority_for "$WT" branch-push)" \
  --authorize-pr-create "$(authority_for "$WT" pr-create)" \
  --keep-branch > "$TMP_ROOT/race.out" 2>&1
race_rc=$?
set -e
assert_eq "$race_rc" "8" "concurrent create adopts uniquely then stops without merge authority"
grep -qF 'PM_CLOSEOUT_PR_ADOPTED_AFTER_CREATE_RACE: #123' "$TMP_ROOT/race.out" \
  && ok "create race adopts the unique exact PR" || bad "create-race adoption receipt missing"
assert_eq "$(grep -cF 'pr create' "$PM_TEST_GH_LOG")" "1" "create race performs exactly one create attempt"
if grep -qF 'pr merge' "$PM_TEST_GH_LOG"; then bad "race path merged unexpectedly"; else ok "race path creates no duplicate or merge"; fi

echo "Case 13: dirty main worktree degrades locally with zero main mutation"
MAIN_WT="$TMP_ROOT/main-worktree"
git -C "$WT" branch -f main origin/main
git -C "$WT" worktree add -q "$MAIN_WT" main
main_before=$(git -C "$MAIN_WT" rev-parse HEAD)
printf 'dirty\n' > "$MAIN_WT/uncommitted.txt"
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=existing PM_CLOSEOUT_MODE=local-after-pr bash "$CLOSEOUT" \
  --worktree "$WT" --main-worktree "$MAIN_WT" --integration-path change.txt \
  --authorize-main-push "$(authority_for "$WT" main-push 123)" \
  --title test --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/dirty-main.out" 2>&1
dirty_main_rc=$?
set -e
assert_eq "$dirty_main_rc" "8" "dirty main is a non-success validate-only downgrade"
grep -qF 'reason=main-worktree-dirty' "$TMP_ROOT/dirty-main.out" \
  && ok "dirty main yields validate-only" || bad "dirty-main reason missing"
assert_eq "$(git -C "$MAIN_WT" rev-parse HEAD)" "$main_before" "dirty main HEAD is not mutated"
if grep -qF 'pr merge' "$PM_TEST_GH_LOG"; then bad "dirty main triggered merge"; else ok "dirty main performs no merge"; fi
rm -f "$MAIN_WT/uncommitted.txt"

echo "Case 14: checks drift after candidate verification leaves main unchanged"
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=check-drift PM_CLOSEOUT_MODE=local-after-pr bash "$CLOSEOUT" \
  --worktree "$WT" --main-worktree "$MAIN_WT" --integration-path change.txt \
  --authorize-main-push "$(authority_for "$WT" main-push 123)" \
  --title test --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/check-drift.out" 2>&1
drift_rc=$?
set -e
assert_eq "$drift_rc" "5" "checks drift fails closed"
grep -qF 'PM_CLOSEOUT_REVIEW_DRIFT' "$TMP_ROOT/check-drift.out" \
  && ok "checks drift emits re-review receipt" || bad "checks drift receipt missing"
assert_eq "$(git -C "$MAIN_WT" rev-parse HEAD)" "$main_before" "checks drift performs zero main mutation"

echo "Case 15: local-after-pr commits (#PR), safe-pushes main and closes only with authority"
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
PM_TEST_GH_MODE=existing PM_TEST_SAFE_DO_PUSH=1 PM_CLOSEOUT_MODE=local-after-pr bash "$CLOSEOUT" \
  --worktree "$WT" --main-worktree "$MAIN_WT" --integration-path change.txt \
  --authorize-main-push "$(authority_for "$WT" main-push 123)" \
  --authorize-main-candidate "$(candidate_authority_for "$WT" main-push-candidate 123 'local integration')" \
  --authorize-pr-close "$(authority_for "$WT" pr-close 123)" \
  --title 'local integration' --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/local-success.out" 2>&1
grep -qF 'PM_CLOSEOUT_RESULT: LOCAL_AFTER_PR pr=123' "$TMP_ROOT/local-success.out" \
  && ok "local-after-pr reaches the explicit result" || bad "local result missing"
grep -qF '(#123)' < <(git -C "$MAIN_WT" log -1 --pretty=%s) \
  && ok "local integration subject is bound to PR number" || bad "local subject lacks PR number"
assert_eq "$(git -C "$MAIN_WT" rev-parse HEAD)" "$(git -C "$MAIN_WT" rev-parse origin/main)" "local main push is confirmed"
grep -qF 'pr close' "$PM_TEST_GH_LOG" && ok "authorized local integration closes with commit receipt" || bad "authorized close missing"

echo "Case 16: main movement during candidate causes PR refreeze and candidate re-verification"
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=existing PM_CLOSEOUT_MODE=remote-pr \
  PM_TEST_VERIFY_ADVANCE_MAIN=1 PM_TEST_VERIFY_ADVANCE_AT_CALL=2 \
  PM_TEST_ADVANCE_REPO="$ADV_SEED" PM_TEST_ADVANCE_MARKER="$TMP_ROOT/unused-at-call.marker" \
  bash "$CLOSEOUT" --worktree "$ADV_WT" --title test --safe-push-script "$SAFE_PUSH" \
  --verify-cmd "$VERIFY" "${ADV_ARGS[@]}" --keep-branch > "$TMP_ROOT/main-refreeze.out" 2>&1
refreeze_rc=$?
set -e
assert_eq "$refreeze_rc" "8" "candidate-time main movement requires a new candidate-bound authorization"
REFREEZE_AUTH=$(sed -n 's/^PM_CLOSEOUT_CANDIDATE_AUTHORIZATION_REQUIRED: operation=remote-merge-candidate expected=//p' "$TMP_ROOT/main-refreeze.out" | tail -1)
[ -n "$REFREEZE_AUTH" ] && ok "refrozen candidate emits a new authorization challenge" || bad "refrozen challenge missing"
set +e
PM_TEST_GH_MODE=existing PM_CLOSEOUT_MODE=remote-pr bash "$CLOSEOUT" \
  --worktree "$ADV_WT" --title test --safe-push-script "$SAFE_PUSH" \
  --verify-cmd "$VERIFY" "${ADV_ARGS[@]}" --authorize-remote-candidate "$REFREEZE_AUTH" \
  --keep-branch > "$TMP_ROOT/main-refreeze-retry.out" 2>&1
refreeze_retry_rc=$?
set -e
assert_eq "$refreeze_retry_rc" "0" "refrozen candidate succeeds after exact reauthorization"
grep -qF 'PM_CLOSEOUT_REVIEW_REFROZEN:' "$TMP_ROOT/main-refreeze.out" \
  && ok "main movement refreezes base/diff/checks facts" || bad "PR refreeze receipt missing"
assert_eq "$(wc -l < "$PM_TEST_VERIFY_LOG" | tr -d ' ')" "5" "refreeze plus authorized retry reverify every candidate"

make_same_file_fixture() {
  local name=$1 main_mode=$2
  FX_REMOTE="$TMP_ROOT/$name-remote.git"
  FX_REPO="$TMP_ROOT/$name-worker"
  FX_MAIN="$TMP_ROOT/$name-main"
  git init -q --bare "$FX_REMOTE"
  git init -q "$FX_REPO"
  git -C "$FX_REPO" config user.name "Closeout Test"
  git -C "$FX_REPO" config user.email "closeout@example.invalid"
  printf 'worker=base\nstable=keep\nmain=base\n' > "$FX_REPO/shared.txt"
  git -C "$FX_REPO" add shared.txt
  git -C "$FX_REPO" commit -qm base
  git -C "$FX_REPO" branch -M main
  git -C "$FX_REPO" remote add origin "$FX_REMOTE"
  git -C "$FX_REPO" push -qu origin main
  git --git-dir="$FX_REMOTE" symbolic-ref HEAD refs/heads/main
  git -C "$FX_REPO" checkout -qb "feat/$name"
  sed -i.bak 's/worker=base/worker=feature/' "$FX_REPO/shared.txt"; rm -f "$FX_REPO/shared.txt.bak"
  git -C "$FX_REPO" commit -qam worker
  git -C "$FX_REPO" worktree add -q "$FX_MAIN" main
  if [ "$main_mode" = conflict ]; then
    sed -i.bak 's/worker=base/worker=main/' "$FX_MAIN/shared.txt"
  else
    sed -i.bak 's/main=base/main=fresh/' "$FX_MAIN/shared.txt"
  fi
  rm -f "$FX_MAIN/shared.txt.bak"
  git -C "$FX_MAIN" commit -qam 'main advances same file'
  git -C "$FX_MAIN" push -q origin main
  git -C "$FX_REPO" fetch -q origin main
}

echo "Case 17: validate-only with zero PR performs no push or create"
make_same_file_fixture validate-zero preserve
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
PM_TEST_GH_MODE=no-pr PM_CLOSEOUT_MODE=validate-only bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --title test --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/validate-zero.out" 2>&1
grep -qF 'VALIDATE_ONLY pr=none' "$TMP_ROOT/validate-zero.out" \
  && ok "zero-PR validate-only emits an explicit result" || bad "validate-only zero result missing"
[ ! -s "$PM_TEST_SAFE_LOG" ] && ! grep -qF 'pr create' "$PM_TEST_GH_LOG" \
  && ok "validate-only performs zero external mutation" || bad "validate-only mutated remote state"

echo "Case 18: a worker-created exact PR is adopted before any branch push"
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
PM_TEST_GH_MODE=existing PM_CLOSEOUT_MODE=validate-only bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --title test --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/adopt-no-push.out" 2>&1
grep -qF 'PM_CLOSEOUT_PR_ADOPTED: #123' "$TMP_ROOT/adopt-no-push.out" \
  && ok "worker-created PR is adopted" || bad "worker PR adoption missing"
[ ! -s "$PM_TEST_SAFE_LOG" ] && ! grep -qF 'pr create' "$PM_TEST_GH_LOG" \
  && ok "adoption performs zero branch push and zero create" || bad "adoption mutated branch or PR set"

echo "Case 19: three-way candidate preserves a fresh main edit in the same file"
PRESERVE_MAIN_BEFORE=$(git -C "$FX_MAIN" rev-parse HEAD)
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=existing PM_TEST_SAFE_DO_PUSH=1 PM_CLOSEOUT_MODE=local-after-pr bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --main-worktree "$FX_MAIN" --integration-path shared.txt \
  --authorize-main-push "$(authority_for "$FX_REPO" main-push 123)" \
  --authorize-main-candidate "$(candidate_authority_for "$FX_REPO" main-push-candidate 123 preserve)" \
  --title preserve --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/preserve.out" 2>&1
preserve_rc=$?
set -e
assert_eq "$preserve_rc" "0" "non-overlapping same-file edits integrate"
grep -q '^worker=feature$' "$FX_MAIN/shared.txt" && grep -q '^main=fresh$' "$FX_MAIN/shared.txt" \
  && ok "three-way patch preserves worker and fresh-main content" || bad "same-file integration lost content"
[ "$(git -C "$FX_MAIN" rev-parse HEAD)" = "$(git -C "$FX_MAIN" rev-parse origin/main)" ] \
  && [ "$(git -C "$FX_MAIN" rev-parse HEAD)" != "$PRESERVE_MAIN_BEFORE" ] \
  && ok "verified candidate is pushed then fast-forwarded locally" || bad "local/remote main did not converge"

echo "Case 20: same-line conflict fails before remote or local main mutation"
make_same_file_fixture conflict conflict
CONFLICT_MAIN_BEFORE=$(git -C "$FX_MAIN" rev-parse HEAD)
CONFLICT_REMOTE_BEFORE=$(git -C "$FX_REPO" rev-parse origin/main)
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=existing PM_CLOSEOUT_MODE=local-after-pr bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --main-worktree "$FX_MAIN" --integration-path shared.txt \
  --authorize-main-push "$(authority_for "$FX_REPO" main-push 123)" \
  --title conflict --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/conflict.out" 2>&1
conflict_rc=$?
set -e
assert_eq "$conflict_rc" "8" "same-line conflict becomes non-success validate-only"
assert_eq "$(git -C "$FX_MAIN" rev-parse HEAD)" "$CONFLICT_MAIN_BEFORE" "conflict leaves local main unchanged"
git -C "$FX_REPO" fetch -q origin main
assert_eq "$(git -C "$FX_REPO" rev-parse origin/main)" "$CONFLICT_REMOTE_BEFORE" "conflict leaves remote main unchanged"

echo "Case 21: unknown protection cannot be overridden into a local push"
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=existing PM_TEST_PROTECTION_MODE=404 PM_CLOSEOUT_MODE=local-after-pr bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --main-worktree "$FX_MAIN" --integration-path shared.txt \
  --authorize-main-push "$(authority_for "$FX_REPO" main-push 123)" \
  --title protection --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/protection-unknown.out" 2>&1
protection_unknown_rc=$?
set -e
assert_eq "$protection_unknown_rc" "8" "404 protection evidence degrades to non-success validate-only"
if grep -qF 'branch main' "$PM_TEST_SAFE_LOG" || grep -qF 'pr merge' "$PM_TEST_GH_LOG"; then
  bad "unknown protection triggered a main mutation"
else
  ok "unknown protection performs zero main push/merge"
fi

echo "Case 22: safe-push failure leaves the real main worktree unchanged"
make_same_file_fixture push-fail preserve
PUSH_FAIL_MAIN_BEFORE=$(git -C "$FX_MAIN" rev-parse HEAD)
PUSH_FAIL_REMOTE_BEFORE=$(git -C "$FX_REPO" rev-parse origin/main)
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=existing PM_TEST_SAFE_FAIL=1 PM_CLOSEOUT_MODE=local-after-pr bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --main-worktree "$FX_MAIN" --integration-path shared.txt \
  --authorize-main-push "$(authority_for "$FX_REPO" main-push 123)" \
  --authorize-main-candidate "$(candidate_authority_for "$FX_REPO" main-push-candidate 123 push-fail)" \
  --title push-fail --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/push-fail.out" 2>&1
push_fail_rc=$?
set -e
assert_eq "$push_fail_rc" "71" "safe-push error propagates"
assert_eq "$(git -C "$FX_MAIN" rev-parse HEAD)" "$PUSH_FAIL_MAIN_BEFORE" "safe-push failure leaves local main unchanged"
git -C "$FX_REPO" fetch -q origin main
assert_eq "$(git -C "$FX_REPO" rev-parse origin/main)" "$PUSH_FAIL_REMOTE_BEFORE" "safe-push failure leaves remote main unchanged"

echo "Case 23: final duplicate PR set blocks merge after candidate verification"
make_same_file_fixture duplicate-final preserve
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=duplicate-final PM_CLOSEOUT_MODE=remote-pr bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --integration-path shared.txt \
  --authorize-remote-merge "$(authority_for "$FX_REPO" remote-merge 123)" \
  --authorize-remote-candidate "$(candidate_authority_for "$FX_REPO" remote-merge-candidate 123 duplicate)" \
  --title duplicate --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/duplicate-final.out" 2>&1
duplicate_final_rc=$?
set -e
assert_eq "$duplicate_final_rc" "5" "final duplicate set fails closed"
if grep -qF 'pr merge' "$PM_TEST_GH_LOG"; then bad "merge ran after final PR-set drift"; else ok "PR-set drift performs zero merge"; fi

echo "Case 24: remote merge requires an explicit integration scope"
set +e
PM_TEST_GH_MODE=existing PM_CLOSEOUT_MODE=remote-pr bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --authorize-remote-merge "$(authority_for "$FX_REPO" remote-merge 123)" \
  --title scope --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/remote-no-scope.out" 2>&1
remote_no_scope_rc=$?
set -e
assert_eq "$remote_no_scope_rc" "64" "remote-pr refuses an undeclared whole-PR scope"

echo "Case 25: scope violations and pathspec magic fail before mutation"
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=existing PM_CLOSEOUT_MODE=remote-pr bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --integration-path unrelated.txt \
  --authorize-remote-merge "$(authority_for "$FX_REPO" remote-merge 123)" \
  --title scope --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/scope-violation.out" 2>&1
scope_violation_rc=$?
PM_TEST_GH_MODE=existing PM_CLOSEOUT_MODE=remote-pr bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --integration-path ':(glob)**' \
  --authorize-remote-merge "$(authority_for "$FX_REPO" remote-merge 123)" \
  --title scope --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/pathspec-magic.out" 2>&1
pathspec_magic_rc=$?
set -e
assert_eq "$scope_violation_rc" "3" "out-of-scope worker paths are rejected"
assert_eq "$pathspec_magic_rc" "2" "pathspec magic is rejected"
[ ! -s "$PM_TEST_SAFE_LOG" ] && ! grep -qF 'pr merge' "$PM_TEST_GH_LOG" \
  && ok "scope failures perform zero push/merge" || bad "scope failure mutated remote state"

echo "Case 26: positive protection evidence routes local preference to remote merge"
make_same_file_fixture protected-route preserve
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
PM_TEST_GH_MODE=existing PM_TEST_PROTECTION_MODE=protected PM_CLOSEOUT_MODE=local-after-pr bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --integration-path shared.txt \
  --authorize-remote-merge "$(authority_for "$FX_REPO" remote-merge 123)" \
  --authorize-remote-candidate "$(candidate_authority_for "$FX_REPO" remote-merge-candidate 123 protected)" \
  --title protected --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/protected-route.out" 2>&1
grep -qF 'effective=remote-pr protection=protected reason=protected-main' "$TMP_ROOT/protected-route.out" \
  && grep -qF 'PM_CLOSEOUT_RESULT: REMOTE_PR' "$TMP_ROOT/protected-route.out" \
  && ok "protected main uses the GitHub merge path" || bad "protected main routing failed"

echo "Case 27: a main worktree from another Git common dir is rejected"
make_same_file_fixture wrong-main-a preserve
WRONG_WORKER=$FX_REPO; WRONG_MAIN_EXPECTED=$FX_MAIN
make_same_file_fixture wrong-main-b preserve
OTHER_MAIN=$FX_MAIN
WRONG_MAIN_BEFORE=$(git -C "$WRONG_MAIN_EXPECTED" rev-parse HEAD)
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=existing PM_CLOSEOUT_MODE=local-after-pr bash "$CLOSEOUT" \
  --worktree "$WRONG_WORKER" --main-worktree "$OTHER_MAIN" --integration-path shared.txt \
  --authorize-main-push "$(authority_for "$WRONG_WORKER" main-push 123)" \
  --title wrong-main --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/wrong-main.out" 2>&1
wrong_main_rc=$?
set -e
assert_eq "$wrong_main_rc" "8" "wrong-repository main becomes non-success validate-only"
assert_eq "$(git -C "$WRONG_MAIN_EXPECTED" rev-parse HEAD)" "$WRONG_MAIN_BEFORE" "wrong-main rejection leaves intended main unchanged"

echo "Case 28: a clean main with an in-progress Git operation is rejected"
WRONG_MAIN_GIT_DIR=$(git -C "$WRONG_MAIN_EXPECTED" rev-parse --absolute-git-dir)
printf '%s\n' "$WRONG_MAIN_BEFORE" > "$WRONG_MAIN_GIT_DIR/MERGE_HEAD"
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=existing PM_CLOSEOUT_MODE=local-after-pr bash "$CLOSEOUT" \
  --worktree "$WRONG_WORKER" --main-worktree "$WRONG_MAIN_EXPECTED" --integration-path shared.txt \
  --authorize-main-push "$(authority_for "$WRONG_WORKER" main-push 123)" \
  --title operation --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/main-operation.out" 2>&1
main_operation_rc=$?
set -e
rm -f "$WRONG_MAIN_GIT_DIR/MERGE_HEAD"
assert_eq "$main_operation_rc" "8" "clean main with MERGE_HEAD is rejected"
assert_eq "$(git -C "$WRONG_MAIN_EXPECTED" rev-parse HEAD)" "$WRONG_MAIN_BEFORE" "operation-in-progress rejection leaves main unchanged"

echo "Case 29: branch protected metadata covers classic protection and routes remotely"
make_same_file_fixture classic-protection preserve
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
PM_TEST_GH_MODE=existing PM_TEST_PROTECTION_MODE=classic-protected PM_CLOSEOUT_MODE=local-after-pr bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --integration-path shared.txt \
  --authorize-remote-merge "$(authority_for "$FX_REPO" remote-merge 123)" \
  --authorize-remote-candidate "$(candidate_authority_for "$FX_REPO" remote-merge-candidate 123 classic)" \
  --title classic --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/classic-protection.out" 2>&1
grep -qF 'effective=remote-pr protection=protected' "$TMP_ROOT/classic-protection.out" \
  && grep -qF 'repos/repository/classic-protection-remote/branches/main' "$PM_TEST_GH_LOG" \
  && ok "classic/ruleset protection uses typed branch metadata" \
  || bad "classic protection was not routed remotely"

echo "Case 30: a base race after final review cannot be reported as a verified remote merge"
make_same_file_fixture base-race preserve
BASE_RACE_BEFORE=$(git -C "$FX_REPO" rev-parse origin/main)
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=base-race PM_CLOSEOUT_MODE=remote-pr bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --integration-path shared.txt \
  --authorize-remote-merge "$(authority_for "$FX_REPO" remote-merge 123)" \
  --authorize-remote-candidate "$(candidate_authority_for "$FX_REPO" remote-merge-candidate 123 base-race)" \
  --title base-race --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/base-race.out" 2>&1
base_race_rc=$?
set -e
assert_eq "$base_race_rc" "9" "base race becomes merged-review-required, never REMOTE_PR success"
grep -qF 'REMOTE_MERGED_REVIEW_REQUIRED' "$TMP_ROOT/base-race.out" \
  && ok "base race reports the expected and actual merge parent/tree" \
  || bad "base race recovery receipt missing"
git -C "$FX_REPO" fetch -q origin main
[ "$(git -C "$FX_REPO" rev-parse origin/main)" != "$BASE_RACE_BEFORE" ] \
  && ok "post-commit uncertainty is explicitly distinguished from a zero-mutation failure" \
  || bad "base-race fixture did not mutate remote main"

echo "Case 31: a lost merge receipt after remote commit is outcome-unknown"
make_same_file_fixture merge-receipt-loss preserve
RECEIPT_MAIN_BEFORE=$(git -C "$FX_REPO" rev-parse origin/main)
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=view-fail-after-merge PM_CLOSEOUT_MODE=remote-pr bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --integration-path shared.txt \
  --authorize-remote-merge "$(authority_for "$FX_REPO" remote-merge 123)" \
  --authorize-remote-candidate "$(candidate_authority_for "$FX_REPO" remote-merge-candidate 123 receipt-loss)" \
  --title receipt-loss --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/merge-receipt-loss.out" 2>&1
receipt_loss_rc=$?
set -e
assert_eq "$receipt_loss_rc" "9" "lost post-merge receipt is not misclassified as an ordinary failure"
grep -qF 'REMOTE_MERGE_OUTCOME_UNKNOWN' "$TMP_ROOT/merge-receipt-loss.out" \
  && ok "lost merge receipt emits a reconciliation state" || bad "outcome-unknown receipt missing"
git -C "$FX_REPO" fetch -q origin main
[ "$(git -C "$FX_REPO" rev-parse origin/main)" != "$RECEIPT_MAIN_BEFORE" ] \
  && ok "receipt-loss fixture proves main may already be changed" || bad "receipt-loss fixture did not mutate main"

echo "Case 32: remote main success followed by local drift becomes LOCAL_PENDING"
make_same_file_fixture local-pending preserve
LOCAL_PENDING_BEFORE=$(git -C "$FX_MAIN" rev-parse HEAD)
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=existing PM_TEST_SAFE_DO_PUSH=1 PM_TEST_DIRTY_MAIN_AFTER_PUSH="$FX_MAIN" \
  PM_CLOSEOUT_MODE=local-after-pr bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --main-worktree "$FX_MAIN" --integration-path shared.txt \
  --authorize-main-push "$(authority_for "$FX_REPO" main-push 123)" \
  --authorize-main-candidate "$(candidate_authority_for "$FX_REPO" main-push-candidate 123 local-pending)" \
  --title local-pending --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/local-pending.out" 2>&1
local_pending_rc=$?
set -e
assert_eq "$local_pending_rc" "9" "post-push local drift becomes a recoverable local-pending state"
grep -qF 'REMOTE_MAIN_APPLIED_LOCAL_PENDING' "$TMP_ROOT/local-pending.out" \
  && ok "local pending receipt names the confirmed remote commit" || bad "local pending receipt missing"
assert_eq "$(git -C "$FX_MAIN" rev-parse HEAD)" "$LOCAL_PENDING_BEFORE" "local pending does not rewrite the drifted main worktree"
rm -f "$FX_MAIN/post-push-drift.txt"

echo "Case 33: caller-supplied ownership trailers are rejected before push/create"
make_same_file_fixture body-trailer preserve
BODY_WITH_TRAILER="$TMP_ROOT/body-with-trailer.md"
printf 'Summary\n\ntask: Task-097\nagent: agent-test\n' > "$BODY_WITH_TRAILER"
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=ok PM_CLOSEOUT_MODE=remote-pr bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --integration-path shared.txt --body-file "$BODY_WITH_TRAILER" \
  --authorize-branch-push "$(authority_for "$FX_REPO" branch-push)" \
  --authorize-pr-create "$(authority_for "$FX_REPO" pr-create)" \
  --title body --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/body-trailer.out" 2>&1
body_trailer_rc=$?
set -e
assert_eq "$body_trailer_rc" "64" "reserved Task/Agent trailers fail pre-mutation"
[ ! -s "$PM_TEST_SAFE_LOG" ] && ! grep -qF 'pr create' "$PM_TEST_GH_LOG" \
  && ok "invalid body performs zero push/create" || bad "invalid body caused a mutation"

echo "Case 34: post-create same-content race is a named created-review state"
make_same_file_fixture create-suspected preserve
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=create-suspected PM_CLOSEOUT_MODE=remote-pr bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --integration-path shared.txt \
  --authorize-branch-push "$(authority_for "$FX_REPO" branch-push)" \
  --authorize-pr-create "$(authority_for "$FX_REPO" pr-create)" \
  --title create-race --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/create-suspected.out" 2>&1
create_suspected_rc=$?
set -e
assert_eq "$create_suspected_rc" "9" "post-create suspected PR is not collapsed into ordinary failure"
grep -qF 'PR_CREATED_REVIEW_REQUIRED pr=123' "$TMP_ROOT/create-suspected.out" \
  && ok "created PR receipt is preserved for manual reconciliation" || bad "created-review receipt missing"
assert_eq "$(grep -cF 'pr create' "$PM_TEST_GH_LOG")" "1" "race path creates at most one PR in this invocation"

echo "Case 35: clean worktree with rebase directory is rejected"
make_same_file_fixture rebase-marker preserve
REBASE_GIT_DIR=$(git -C "$FX_MAIN" rev-parse --absolute-git-dir)
mkdir -p "$REBASE_GIT_DIR/rebase-merge"
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=existing PM_CLOSEOUT_MODE=local-after-pr bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --main-worktree "$FX_MAIN" --integration-path shared.txt \
  --authorize-main-push "$(authority_for "$FX_REPO" main-push 123)" \
  --title rebase-marker --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/rebase-marker.out" 2>&1
rebase_marker_rc=$?
set -e
rmdir "$REBASE_GIT_DIR/rebase-merge"
assert_eq "$rebase_marker_rc" "8" "clean main with rebase-merge state is rejected"

echo "Case 36: closeout Git errors redact credentials"
make_same_file_fixture fetch-redaction preserve
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=ok PM_TEST_SAFE_LEAK=1 PM_CLOSEOUT_MODE=remote-pr bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --integration-path shared.txt \
  --authorize-branch-push "$(authority_for "$FX_REPO" branch-push)" \
  --authorize-pr-create "$(authority_for "$FX_REPO" pr-create)" \
  --title redact --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/fetch-redaction.out" 2>&1
fetch_redaction_rc=$?
set -e
[ "$fetch_redaction_rc" -ne 0 ] && ok "safe-push failure is surfaced" || bad "redaction fixture unexpectedly succeeded"
! grep -qF 'LEAK-ME' "$TMP_ROOT/fetch-redaction.out" && grep -qF '***@example.invalid' "$TMP_ROOT/fetch-redaction.out" \
  && ok "closeout redacts remote credentials from Git stderr" || bad "credential redaction failed"

make_same_file_fixture pr-diff-redaction preserve
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=diff-leak PM_CLOSEOUT_MODE=remote-pr bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --integration-path shared.txt \
  --authorize-remote-merge "$(authority_for "$FX_REPO" remote-merge 123)" \
  --title redact-diff --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/pr-diff-redaction.out" 2>&1
pr_diff_redaction_rc=$?
set -e
[ "$pr_diff_redaction_rc" -ne 0 ] && ok "PR diff failure is surfaced" || bad "PR diff redaction fixture unexpectedly succeeded"
! grep -qE 'PR-DIFF-LEAK|DIFF-TOKEN' "$TMP_ROOT/pr-diff-redaction.out" && grep -qF '***@example.invalid' "$TMP_ROOT/pr-diff-redaction.out" \
  && ok "closeout redacts credentials from PR diff stderr" || bad "PR diff credential redaction failed"

echo "Case 37: lost PR-close receipt preserves delivered main as an outcome-unknown state"
make_same_file_fixture close-receipt-loss preserve
CLOSE_MAIN_BEFORE=$(git -C "$FX_MAIN" rev-parse HEAD)
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=close-view-fail PM_TEST_SAFE_DO_PUSH=1 PM_CLOSEOUT_MODE=local-after-pr bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --main-worktree "$FX_MAIN" --integration-path shared.txt \
  --authorize-main-push "$(authority_for "$FX_REPO" main-push 123)" \
  --authorize-main-candidate "$(candidate_authority_for "$FX_REPO" main-push-candidate 123 close-receipt)" \
  --authorize-pr-close "$(authority_for "$FX_REPO" pr-close 123)" \
  --title close-receipt --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/close-receipt-loss.out" 2>&1
close_receipt_rc=$?
set -e
assert_eq "$close_receipt_rc" "9" "lost close receipt is not reported as a zero-mutation failure"
grep -qF 'LOCAL_AFTER_PR_CLOSE_OUTCOME_UNKNOWN' "$TMP_ROOT/close-receipt-loss.out" \
  && ok "close outcome-unknown receipt retains PR and main identities" || bad "close outcome receipt missing"
[ "$(git -C "$FX_MAIN" rev-parse HEAD)" != "$CLOSE_MAIN_BEFORE" ] \
  && [ "$(git -C "$FX_MAIN" rev-parse HEAD)" = "$(git -C "$FX_MAIN" rev-parse origin/main)" ] \
  && ok "close receipt loss keeps the confirmed local/remote main delivery" \
  || bad "main delivery was not preserved before close receipt loss"

echo "Case 38: post-create audit failure preserves an outcome-unknown receipt"
make_same_file_fixture post-create-audit preserve
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=post-create-audit-fail PM_CLOSEOUT_MODE=remote-pr bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --integration-path shared.txt \
  --authorize-branch-push "$(authority_for "$FX_REPO" branch-push)" \
  --authorize-pr-create "$(authority_for "$FX_REPO" pr-create)" \
  --title post-create-audit --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/post-create-audit.out" 2>&1
post_create_audit_rc=$?
set -e
assert_eq "$post_create_audit_rc" "9" "post-create audit failure is outcome-unknown, not zero-mutation failure"
grep -qF 'PR_CREATE_OUTCOME_UNKNOWN' "$TMP_ROOT/post-create-audit.out" \
  && ok "post-create audit failure retains a reconciliation state" || bad "post-create audit state missing"
assert_eq "$(grep -cF 'pr create' "$PM_TEST_GH_LOG")" "1" "post-create audit failure never retries create"

echo "Case 39: native merge queue is left to Task-070"
make_same_file_fixture merge-queue preserve
MERGE_QUEUE_MAIN_BEFORE=$(git -C "$FX_REPO" rev-parse origin/main)
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=existing PM_TEST_PROTECTION_MODE=merge-queue PM_CLOSEOUT_MODE=local-after-pr bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --integration-path shared.txt \
  --authorize-main-push "$(authority_for "$FX_REPO" main-push 123)" \
  --authorize-remote-merge "$(authority_for "$FX_REPO" remote-merge 123)" \
  --authorize-remote-candidate "$(candidate_authority_for "$FX_REPO" remote-merge-candidate 123 queue)" \
  --title queue --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/merge-queue.out" 2>&1
merge_queue_rc=$?
set -e
assert_eq "$merge_queue_rc" "8" "merge queue rule degrades to validate-only"
grep -qF 'merge-queue-present-task-070-required' "$TMP_ROOT/merge-queue.out" \
  && ! grep -qF 'pr merge' "$PM_TEST_GH_LOG" \
  && ok "Task-097 never enqueues an asynchronous merge" || bad "merge queue boundary failed"
git -C "$FX_REPO" fetch -q origin main
assert_eq "$(git -C "$FX_REPO" rev-parse origin/main)" "$MERGE_QUEUE_MAIN_BEFORE" "merge queue path leaves main unchanged"

echo "Case 40: protection is rechecked immediately before local main push"
make_same_file_fixture protection-flip preserve
PROTECTION_FLIP_MAIN_BEFORE=$(git -C "$FX_REPO" rev-parse origin/main)
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=existing PM_TEST_PROTECTION_MODE=flip-protection PM_CLOSEOUT_MODE=local-after-pr bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --main-worktree "$FX_MAIN" --integration-path shared.txt \
  --authorize-main-push "$(authority_for "$FX_REPO" main-push 123)" \
  --authorize-main-candidate "$(candidate_authority_for "$FX_REPO" main-push-candidate 123 protection-flip)" \
  --title protection-flip --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/protection-flip.out" 2>&1
protection_flip_rc=$?
set -e
assert_eq "$protection_flip_rc" "8" "protection flip blocks local push after candidate verification"
grep -qF 'reason=main-protection-drift-protected' "$TMP_ROOT/protection-flip.out" \
  && [ ! -s "$PM_TEST_SAFE_LOG" ] \
  && ok "final protection gate performs zero main push" || bad "final protection recheck failed"
git -C "$FX_REPO" fetch -q origin main
assert_eq "$(git -C "$FX_REPO" rev-parse origin/main)" "$PROTECTION_FLIP_MAIN_BEFORE" "protection flip leaves remote main unchanged"

echo "Case 41: stale REBASE_HEAD alone is not an active rebase"
make_same_file_fixture stale-rebase-head preserve
STALE_REBASE_GIT_DIR=$(git -C "$FX_MAIN" rev-parse --absolute-git-dir)
git -C "$FX_REPO" rev-parse HEAD > "$STALE_REBASE_GIT_DIR/REBASE_HEAD"
: > "$PM_TEST_SAFE_LOG"; : > "$PM_TEST_GH_LOG"; : > "$PM_TEST_VERIFY_LOG"
set +e
PM_TEST_GH_MODE=existing PM_CLOSEOUT_MODE=local-after-pr bash "$CLOSEOUT" \
  --worktree "$FX_REPO" --main-worktree "$FX_MAIN" --integration-path shared.txt \
  --authorize-main-push "$(authority_for "$FX_REPO" main-push 123)" \
  --title stale-rebase-head --safe-push-script "$SAFE_PUSH" --verify-cmd "$VERIFY" --keep-branch \
  > "$TMP_ROOT/stale-rebase-head.out" 2>&1
stale_rebase_head_rc=$?
set -e
rm -f "$STALE_REBASE_GIT_DIR/REBASE_HEAD"
assert_eq "$stale_rebase_head_rc" "8" "stale REBASE_HEAD reaches the later candidate authorization gate"
grep -qF 'PM_CLOSEOUT_CANDIDATE_VERIFIED:' "$TMP_ROOT/stale-rebase-head.out" && \
  ! grep -qF 'main-worktree-operation-in-progress-REBASE_HEAD' "$TMP_ROOT/stale-rebase-head.out" \
  && ok "stale REBASE_HEAD is ignored while active rebase directories remain guarded" \
  || bad "stale REBASE_HEAD was mistaken for an active rebase"

printf 'pm-closeout tests: %s passed, %s failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
