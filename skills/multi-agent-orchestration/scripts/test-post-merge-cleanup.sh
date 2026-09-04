#!/usr/bin/env bash
# Deterministic contract tests for post-merge-cleanup.sh: throwaway local Git
# remote plus fake gh/tmux/orca/git executables; never reaches the network.
#
# 覆盖场景（对应任务合同）：
#   1. 即时安全清理：dry-run 计划（Case 1）/ execute 全链路（Case 2）/ supervised
#      released + 存活 tmux 的 release→kill→rm 顺序（Case 3）
#   2. 开放 child PR 阻止删除（Case 4）
#   3. 长期集成/默认分支阻止（Case 5：main、--protected-branch 模式、--base 自身）
#   4. dirty worktree 阻止（Case 6）
#   5. active / release_pending 阻止（Case 7，supervised accounting fail-closed）
#   6. 远端删除失败不冒充完成（Case 8，exit 9 无 DONE）
#   7. dry-run 无副作用（Case 1）
#   8. 执行后机械零残留验证（Case 9：push 谎报成功时的残留捕获）
#   9. 24h 规则保护（Case 10-13、15：无 MERGED 证据 / head 漂移 / metadata 缺失 /
#      tmux 存活未结算 / gh 不可用）
#  10. squash-merge 后 -d 拒绝时的证据背书 -D 升级（Case 14，clean-worktree.sh
#      --force-delete-branch）
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HELPER="$SCRIPT_DIR/post-merge-cleanup.sh"
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT

passed=0
failed=0
ok() { echo "  ✓ $1"; passed=$((passed + 1)); }
bad() { echo "  ✗ $1" >&2; failed=$((failed + 1)); }
assert_eq() {
  if [ "$1" = "$2" ]; then ok "$3"; else bad "$3 (expected=$2 actual=$1)"; fi
}
assert_contains() {
  if grep -qF -- "$1" "$2"; then ok "$3"; else bad "$3 (missing '$1' in $2)"; fi
}
assert_not_contains() {
  if grep -qF -- "$1" "$2"; then bad "$3 (unexpected '$1' in $2)"; else ok "$3"; fi
}
assert_remote_branch_absent() {
  if git --git-dir="$REMOTE" show-ref --verify --quiet "refs/heads/$1"; then bad "remote branch $1 still exists"; else ok "remote branch $1 absent"; fi
}

REAL_GIT=$(command -v git)
world_count=0

build_world() {
  world_count=$((world_count + 1))
  WORLD="$TMP_ROOT/world-$world_count"
  REMOTE="$WORLD/remote.git"
  SEED="$WORLD/seed"
  PROJECT="$WORLD/project"
  BIN="$WORLD/bin"
  OUT="$WORLD/out.log"
  ERR="$WORLD/err.log"
  mkdir -p "$BIN"
  git init -q --bare "$REMOTE"
  git init -q "$SEED"
  git -C "$SEED" config user.name "Cleanup Test"
  git -C "$SEED" config user.email "cleanup@example.invalid"
  printf 'base\n' > "$SEED/base.txt"
  # 与真实 orchestration 仓库一致：session context 不算 dirty。
  printf '.claude/agent-sessions/\n' > "$SEED/.gitignore"
  git -C "$SEED" add .
  git -C "$SEED" commit -q -m base
  git -C "$SEED" branch -M main
  git -C "$SEED" remote add origin "$REMOTE"
  git -C "$SEED" push -q -u origin main
  git --git-dir="$REMOTE" symbolic-ref HEAD refs/heads/main
  git clone -q "$REMOTE" "$PROJECT"
  git -C "$PROJECT" config user.name "Cleanup Test"
  git -C "$PROJECT" config user.email "cleanup@example.invalid"

  : > "$WORLD/gh.log"
  printf '[]\n' > "$WORLD/gh-merged.json"
  printf '[]\n' > "$WORLD/gh-open.json"

  cat > "$BIN/gh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%q ' "$@" >> "${FAKE_GH_LOG:?}"
printf '\n' >> "${FAKE_GH_LOG:?}"
state=""
prev=""
for arg in "$@"; do
  if [ "$prev" = "--state" ]; then state="$arg"; fi
  prev="$arg"
done
case "$state" in
  merged)
    [ "${FAKE_GH_MERGED_FAIL:-0}" -eq 0 ] || { echo 'gh merged list unavailable' >&2; exit 3; }
    cat "${FAKE_GH_MERGED_FILE:?}"
    ;;
  open)
    [ "${FAKE_GH_OPEN_FAIL:-0}" -eq 0 ] || { echo 'gh open list unavailable' >&2; exit 3; }
    cat "${FAKE_GH_OPEN_FILE:?}"
    ;;
  *)
    echo '[]'
    ;;
esac
SH
  chmod +x "$BIN/gh"

  cat > "$BIN/tmux" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cmd="$1"
shift || true
case "$cmd" in
  has-session)
    if [ "${FAKE_TMUX_ALIVE:-0}" = "1" ] && [ ! -e "${FAKE_TMUX_DEAD:?}" ]; then
      exit 0
    fi
    echo "no server running on /tmp/tmt-test" >&2
    exit 1
    ;;
  kill-session)
    printf '%s\n' "$cmd $*" >> "${FAKE_TMUX_LOG:?}"
    : > "${FAKE_TMUX_DEAD:?}"
    exit 0
    ;;
esac
exit 0
SH
  chmod +x "$BIN/tmux"

  cat > "$BIN/git" <<SH
#!/usr/bin/env bash
set -euo pipefail
# helper 以 git -C <path> push origin --delete 调用，按参数流扫描而非固定下标。
saw_push=0
is_push_delete=0
for arg in "\$@"; do
  if [ "\$saw_push" -eq 1 ] && [ "\$arg" = "--delete" ]; then is_push_delete=1; fi
  if [ "\$arg" = "push" ]; then saw_push=1; fi
done
if [ "\$is_push_delete" -eq 1 ]; then
  printf '%s\n' "\$*" >> "\${FAKE_GIT_LOG:?}"
  case "\${FAKE_GIT_PUSH_DELETE_MODE:-passthrough}" in
    fail) echo 'remote: refusing delete (test injection)' >&2; exit 5 ;;
    lie) echo 'fake push claims success without deleting' ; exit 0 ;;
  esac
fi
exec "$REAL_GIT" "\$@"
SH
  chmod +x "$BIN/git"

  : > "$WORLD/tmux.log"
  rm -f "$WORLD/tmux-dead"
  : > "$WORLD/git.log"
  # 用例间通过函数前缀赋值传递的环境必须清零，避免向后续用例泄漏状态。
  unset FAKE_TMUX_ALIVE FAKE_GIT_PUSH_DELETE_MODE FAKE_ORCA_TERMINAL_STATE \
    FAKE_ORCA_DISPATCH FAKE_GH_MERGED_FAIL FAKE_GH_OPEN_FAIL ORCA_CLI_CMD || true

  cat > "$BIN/orca" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
{
  for arg in "$@"; do printf '%q ' "$arg"; done
  printf '\n'
} >> "${FAKE_ORCA_LOG:?}"
case "$1 $2" in
  "orchestration worker-list")
    printf '{"ok":true,"result":{"workers":[{"dispatch_id":"%s","terminal_state":"%s","worker_state":"succeeded","dispatch_status":"completed"}]}}' \
      "${FAKE_ORCA_DISPATCH:-ctx-1}" "${FAKE_ORCA_TERMINAL_STATE:-released}"
    ;;
  "orchestration worker-release")
    printf '{"ok":true,"result":{"release":{"dispatch_id":"%s"}}}\n' "${FAKE_ORCA_DISPATCH:-ctx-1}"
    ;;
  *)
    echo '{"ok":true,"result":{}}'
    ;;
esac
SH
  chmod +x "$BIN/orca"
  : > "$WORLD/orca.log"
}

# 建一个 orchestration worker：worktree + 分支 + 上游 + 可选 METADATA。
make_worker() {
  BRANCH="$1"
  SESSION="$2"
  WT="$WORLD/wt-$SESSION"
  git -C "$PROJECT" worktree add -q -b "$BRANCH" "$WT"
  printf 'worker change\n' > "$WT/worker.txt"
  git -C "$WT" add worker.txt
  git -C "$WT" commit -q -m "worker work"
  git -C "$WT" push -q -u origin "$BRANCH"
  TIP=$(git -C "$PROJECT" rev-parse "refs/heads/$BRANCH")
}

write_metadata() {
  mkdir -p "$WT/.claude/agent-sessions/$SESSION"
  cat > "$WT/.claude/agent-sessions/$SESSION/METADATA.json"
}

set_merged_pr() {
  local oid="$1" number="${2:-27}"
  printf '[{"number":%s,"url":"https://github.invalid/o/r/pull/%s","state":"MERGED","headRefName":"%s","headRefOid":"%s"}]\n' \
    "$number" "$number" "$BRANCH" "$oid" > "$WORLD/gh-merged.json"
}

# run_helper [extra args...] — 每个用例内自选 execute/dry-run；rc 落在 HELPER_RC。
run_helper() {
  set +e
  (
    cd "$PROJECT" && \
    ORCA_CLI_COMMAND="${ORCA_CLI_CMD:-}" \
    FAKE_GH_LOG="$WORLD/gh.log" \
    FAKE_GH_MERGED_FILE="$WORLD/gh-merged.json" \
    FAKE_GH_OPEN_FILE="$WORLD/gh-open.json" \
    FAKE_GH_MERGED_FAIL="${FAKE_GH_MERGED_FAIL:-0}" \
    FAKE_GH_OPEN_FAIL="${FAKE_GH_OPEN_FAIL:-0}" \
    FAKE_TMUX_ALIVE="${FAKE_TMUX_ALIVE:-0}" \
    FAKE_TMUX_LOG="$WORLD/tmux.log" \
    FAKE_TMUX_DEAD="$WORLD/tmux-dead" \
    FAKE_GIT_LOG="$WORLD/git.log" \
    FAKE_GIT_PUSH_DELETE_MODE="${FAKE_GIT_PUSH_DELETE_MODE:-passthrough}" \
    FAKE_ORCA_LOG="$WORLD/orca.log" \
    FAKE_ORCA_TERMINAL_STATE="${FAKE_ORCA_TERMINAL_STATE:-released}" \
    FAKE_ORCA_DISPATCH="${FAKE_ORCA_DISPATCH:-ctx-1}" \
    PATH="$BIN:$PATH" \
    bash "$HELPER" --project "$PROJECT" --branch "$BRANCH" --session "$SESSION" "$@"
  ) > "$OUT" 2> "$ERR"
  HELPER_RC=$?
  set -e
}

echo "Case 1: dry-run plans a safe cleanup with zero side effects"
build_world
make_worker feat/dry-plan worker-a
write_metadata <<JSON
{"session":{"id":"worker-a"},"runtime":{"worker_backend":"codex","provider_lease":{"file":""}}}
JSON
set_merged_pr "$TIP"
run_helper
assert_eq "$HELPER_RC" "0" "dry-run exits 0"
assert_contains "POST_MERGE_CLEANUP_MODE: dry-run" "$OUT" "dry-run announces mode"
assert_contains "POST_MERGE_CLEANUP_MERGED_PR: number=27" "$OUT" "merged PR evidence surfaced"
assert_contains "POST_MERGE_CLEANUP_DRY_RUN_DONE" "$OUT" "dry-run completion marker"
assert_contains "remote_branch=delete" "$OUT" "plan includes remote deletion"
[ -d "$WT" ] && ok "dry-run kept the worktree" || bad "dry-run removed the worktree"
git -C "$PROJECT" show-ref --verify --quiet "refs/heads/$BRANCH" && ok "dry-run kept the local branch" || bad "dry-run deleted the local branch"
git --git-dir="$REMOTE" show-ref --verify --quiet "refs/heads/$BRANCH" && ok "dry-run kept the remote branch" || bad "dry-run deleted the remote branch"
assert_not_contains "CLEAN_WORKTREE_MODE: execute" "$OUT" "dry-run never executes clean-worktree"
assert_not_contains "push origin --delete" "$WORLD/git.log" "dry-run never deletes the remote branch"

echo "Case 2: execute cleans a merged worker and verifies zero residue"
run_helper --execute
assert_eq "$HELPER_RC" "0" "execute exits 0"
assert_contains "CLEAN_WORKTREE_MODE: execute" "$OUT" "lifecycle executed via clean-worktree.sh"
assert_contains "CLEAN_WORKTREE_BRANCH_DELETED: branch=$BRANCH" "$OUT" "local branch deleted"
assert_contains "POST_MERGE_CLEANUP_REMOTE_DELETED: branch=$BRANCH" "$OUT" "remote branch deleted"
assert_contains "POST_MERGE_CLEANUP_RESIDUE_VERIFIED: zero" "$OUT" "residue verification ran"
assert_contains "POST_MERGE_CLEANUP_DONE" "$OUT" "completion marker"
assert_contains "POST_MERGE_CLEANUP_RESULT: CLEANED" "$OUT" "result receipt"
[ ! -d "$WT" ] && ok "worktree directory removed" || bad "worktree directory still present"
git -C "$PROJECT" show-ref --verify --quiet "refs/heads/$BRANCH" && bad "local branch residue" || ok "local branch absent"
assert_remote_branch_absent "$BRANCH"

echo "Case 3: supervised released dispatch is released first, then cleaned"
build_world
make_worker feat/supervised worker-s
write_metadata <<JSON
{"session":{"id":"worker-s","orca":{"worktree_id":"repo::wt1","terminal_handle":"term-x","mode":"orca","supervised":{"dispatch_id":"ctx-1"}}},"runtime":{"worker_backend":"codex","provider_lease":{"file":""}}}
JSON
set_merged_pr "$TIP"
ORCA_CLI_CMD="$BIN/orca" FAKE_TMUX_ALIVE=1 run_helper
assert_eq "$HELPER_RC" "0" "supervised dry-run exits 0"
if grep -q 'orchestration worker-release' "$WORLD/orca.log"; then bad "dry-run released a worker (mutation in dry-run)"; else ok "dry-run never releases the worker"; fi
assert_contains "terminal=released" "$OUT" "released accounting surfaced in dry-run"
: > "$WORLD/orca.log"
: > "$WORLD/tmux.log"
rm -f "$WORLD/tmux-dead"
ORCA_CLI_CMD="$BIN/orca" FAKE_TMUX_ALIVE=1 run_helper --execute
assert_eq "$HELPER_RC" "0" "supervised execute exits 0"
assert_contains "orchestration worker-release" "$WORLD/orca.log" "worker released before filesystem cleanup"
release_line=$(grep -n 'orchestration worker-release' "$WORLD/orca.log" | head -1 | cut -d: -f1)
rm_line=$(grep -n '^worktree rm' "$WORLD/orca.log" | head -1 | cut -d: -f1)
if [ -n "$rm_line" ] && [ "$release_line" -lt "$rm_line" ]; then ok "release happens before worktree rm"; else bad "release ordering broken (release=$release_line rm=$rm_line)"; fi
assert_contains "kill-session" "$WORLD/tmux.log" "tmux session killed after accounting released"
assert_contains "POST_MERGE_CLEANUP_DONE" "$OUT" "supervised cleanup completed"
[ ! -d "$WT" ] && ok "supervised worktree removed" || bad "supervised worktree still present"
assert_remote_branch_absent "$BRANCH"

echo "Case 4: an open stacked child PR blocks deletion"
build_world
make_worker feat/stacked-base worker-c
write_metadata <<JSON
{"session":{"id":"worker-c"},"runtime":{"provider_lease":{"file":""}}}
JSON
set_merged_pr "$TIP"
printf '[{"number":31,"url":"https://github.invalid/o/r/pull/31","state":"OPEN","headRefName":"feat/stacked-child","headRefOid":"%s"}]\n' "$TIP" > "$WORLD/gh-open.json"
run_helper --execute
assert_eq "$HELPER_RC" "2" "open child PR defers cleanup"
assert_contains "POST_MERGE_CLEANUP_DEFERRED: reason=open_child_pr" "$ERR" "child PR deferred reason"
[ -d "$WT" ] && ok "worktree untouched by deferred cleanup" || bad "worktree removed despite child PR"
git -C "$PROJECT" show-ref --verify --quiet "refs/heads/$BRANCH" && ok "local branch kept" || bad "local branch deleted despite child PR"
git --git-dir="$REMOTE" show-ref --verify --quiet "refs/heads/$BRANCH" && ok "remote branch kept" || bad "remote branch deleted despite child PR"

echo "Case 5: default and long-lived integration branches are never deleted"
build_world
BRANCH=main
SESSION=worker-m
run_helper --execute
assert_eq "$HELPER_RC" "2" "main branch defers cleanup"
assert_contains "reason=protected_branch" "$ERR" "main protected reason"
git -C "$PROJECT" show-ref --verify --quiet refs/heads/main && ok "main survived" || bad "main deleted"

build_world
make_worker bl-main worker-l
set_merged_pr "$TIP"
run_helper --execute --protected-branch 'bl-*'
assert_eq "$HELPER_RC" "2" "pattern-protected long-lived branch defers cleanup"
assert_contains "matches protected pattern=bl-*" "$ERR" "protected pattern surfaced"

build_world
make_worker feat/self worker-b2
set_merged_pr "$TIP"
run_helper --execute --base feat/self
assert_eq "$HELPER_RC" "2" "branch equal to base ref defers cleanup"
assert_contains "reason=protected_branch" "$ERR" "base-ref protected reason"

echo "Case 6: a dirty worktree blocks cleanup and keeps every artifact"
build_world
make_worker feat/dirty worker-d
write_metadata <<JSON
{"session":{"id":"worker-d"},"runtime":{"provider_lease":{"file":""}}}
JSON
set_merged_pr "$TIP"
printf 'uncommitted\n' > "$WT/worker.txt"
run_helper --execute
assert_eq "$HELPER_RC" "2" "dirty worktree defers cleanup"
assert_contains "reason=dirty_worktree" "$ERR" "dirty deferred reason"
[ -d "$WT" ] && ok "dirty worktree kept" || bad "dirty worktree removed"
[ "$(git -C "$WT" status --porcelain | wc -l | tr -d ' ')" != "0" ] && ok "uncommitted work preserved" || bad "uncommitted work lost"
git --git-dir="$REMOTE" show-ref --verify --quiet "refs/heads/$BRANCH" && ok "remote branch kept for dirty case" || bad "remote branch deleted for dirty case"

echo "Case 7: active and release_pending accounting refuse filesystem cleanup"
build_world
make_worker feat/active worker-p
write_metadata <<JSON
{"session":{"id":"worker-p","orca":{"worktree_id":"repo::wt2","terminal_handle":"term-y","supervised":{"dispatch_id":"ctx-1"}}},"runtime":{"provider_lease":{"file":""}}}
JSON
set_merged_pr "$TIP"
ORCA_CLI_CMD="$BIN/orca" FAKE_ORCA_TERMINAL_STATE=active run_helper --execute
assert_eq "$HELPER_RC" "2" "active terminal accounting defers cleanup"
assert_contains "reason=terminal_accounting_active" "$ERR" "active deferred reason"
if grep -q 'orchestration worker-release' "$WORLD/orca.log"; then bad "active worker was released"; else ok "active worker not released"; fi
[ -d "$WT" ] && ok "active worker worktree kept" || bad "active worker worktree removed"

build_world
make_worker feat/pending worker-q
write_metadata <<JSON
{"session":{"id":"worker-q","orca":{"worktree_id":"repo::wt3","terminal_handle":"term-z","supervised":{"dispatch_id":"ctx-2"}}},"runtime":{"provider_lease":{"file":""}}}
JSON
set_merged_pr "$TIP"
ORCA_CLI_CMD="$BIN/orca" FAKE_ORCA_DISPATCH=ctx-2 FAKE_ORCA_TERMINAL_STATE=release_pending run_helper --execute
assert_eq "$HELPER_RC" "2" "release_pending accounting defers cleanup"
assert_contains "reason=terminal_accounting_release_pending" "$ERR" "release_pending deferred reason"
[ -d "$WT" ] && ok "release_pending worktree kept" || bad "release_pending worktree removed"

echo "Case 8: a failed remote deletion is never reported as completion"
build_world
make_worker feat/pushfail worker-f
write_metadata <<JSON
{"session":{"id":"worker-f"},"runtime":{"provider_lease":{"file":""}}}
JSON
set_merged_pr "$TIP"
FAKE_GIT_PUSH_DELETE_MODE=fail run_helper --execute
assert_eq "$HELPER_RC" "9" "remote delete failure exits 9"
assert_contains "POST_MERGE_CLEANUP_REMOTE_DELETE_FAILED" "$ERR" "remote failure surfaced"
assert_not_contains "POST_MERGE_CLEANUP_DONE" "$OUT" "no completion marker after remote failure"
git -C "$PROJECT" show-ref --verify --quiet "refs/heads/$BRANCH" && bad "local branch unexpectedly kept" || ok "local branch deletion acknowledged as partial state"
git --git-dir="$REMOTE" show-ref --verify --quiet "refs/heads/$BRANCH" && ok "remote branch still present after failed delete" || bad "remote branch vanished without success receipt"

echo "Case 9: residue verification catches a push that lies about deletion"
build_world
make_worker feat/liar worker-r
write_metadata <<JSON
{"session":{"id":"worker-r"},"runtime":{"provider_lease":{"file":""}}}
JSON
set_merged_pr "$TIP"
FAKE_GIT_PUSH_DELETE_MODE=lie run_helper --execute
assert_eq "$HELPER_RC" "9" "lying push is caught by residue verification"
assert_contains "POST_MERGE_CLEANUP_RESIDUE: kind=remote_branch" "$ERR" "remote residue reported"
assert_not_contains "POST_MERGE_CLEANUP_DONE" "$OUT" "no completion marker with residue"
git --git-dir="$REMOTE" show-ref --verify --quiet "refs/heads/$BRANCH" && ok "remote branch honestly still present" || bad "remote branch state changed under lie mode"

echo "Case 10: no MERGED evidence keeps the branch (24h rule protection)"
build_world
make_worker feat/fresh worker-n
write_metadata <<JSON
{"session":{"id":"worker-n"},"runtime":{"provider_lease":{"file":""}}}
JSON
run_helper --execute
assert_eq "$HELPER_RC" "2" "missing MERGED evidence defers cleanup"
assert_contains "reason=no_merged_pr_evidence" "$ERR" "no-evidence deferred reason"
git --git-dir="$REMOTE" show-ref --verify --quiet "refs/heads/$BRANCH" && ok "unmerged young branch kept" || bad "unmerged young branch deleted"

echo "Case 11: a branch tip that drifted from the merged PR head is never cleaned"
build_world
make_worker feat/drifted worker-h
write_metadata <<JSON
{"session":{"id":"worker-h"},"runtime":{"provider_lease":{"file":""}}}
JSON
set_merged_pr "0000000000000000000000000000000000000000"
run_helper --execute
assert_eq "$HELPER_RC" "2" "head mismatch defers cleanup"
assert_contains "reason=head_mismatch" "$ERR" "head mismatch deferred reason"
git -C "$PROJECT" show-ref --verify --quiet "refs/heads/$BRANCH" && ok "drifted branch kept" || bad "drifted branch deleted"

echo "Case 12: a worktree without session METADATA has uncertain identity"
build_world
make_worker feat/nometa worker-x
set_merged_pr "$TIP"
run_helper --execute
assert_eq "$HELPER_RC" "2" "missing METADATA defers cleanup"
assert_contains "reason=session_metadata_missing" "$ERR" "metadata deferred reason"
[ -d "$WT" ] && ok "worktree kept without METADATA" || bad "worktree removed without METADATA"

echo "Case 13: an alive tmux session without supervised dispatch blocks cleanup"
build_world
make_worker feat/livetmux worker-t
write_metadata <<JSON
{"session":{"id":"worker-t"},"runtime":{"provider_lease":{"file":""}}}
JSON
set_merged_pr "$TIP"
FAKE_TMUX_ALIVE=1 run_helper --execute
assert_eq "$HELPER_RC" "2" "alive unaccounted tmux session defers cleanup"
assert_contains "reason=tmux_session_alive_unaccounted" "$ERR" "tmux deferred reason"
assert_not_contains "CLEAN_WORKTREE_MODE: execute" "$OUT" "clean-worktree never executed behind tmux gate"
[ -d "$WT" ] && ok "worktree kept behind tmux gate" || bad "worktree removed behind tmux gate"

echo "Case 14: squash-merged branches escalate from refused -d to evidence-backed -D"
build_world
BRANCH=feat/squashed
SESSION=worker-sq
git -C "$PROJECT" checkout -q -b "$BRANCH"
printf 'squash content\n' > "$PROJECT/worker.txt"
git -C "$PROJECT" add worker.txt
git -C "$PROJECT" commit -q -m "worker work"
git -C "$PROJECT" push -q -u origin "$BRANCH"
TIP=$(git -C "$PROJECT" rev-parse "refs/heads/$BRANCH")
git -C "$PROJECT" push -q origin --delete "$BRANCH"
git -C "$PROJECT" fetch -q --prune origin
git -C "$PROJECT" checkout -q main
printf 'squash content\n' > "$PROJECT/worker.txt"
git -C "$PROJECT" add worker.txt
git -C "$PROJECT" commit -q -m "worker work (#27)"
git -C "$PROJECT" push -q origin main
set_merged_pr "$TIP"
WT=""
run_helper --execute
assert_eq "$HELPER_RC" "0" "squash-merged branch cleanup exits 0"
assert_contains "CLEAN_WORKTREE_BRANCH_FORCE_DELETED" "$OUT" "evidence-backed -D escalation recorded"
assert_contains "POST_MERGE_CLEANUP_REMOTE_ALREADY_ABSENT: branch=$BRANCH" "$OUT" "absent remote handled idempotently"
assert_contains "POST_MERGE_CLEANUP_DONE" "$OUT" "squash cleanup completed"
git -C "$PROJECT" show-ref --verify --quiet "refs/heads/$BRANCH" && bad "squashed branch residue" || ok "squashed branch deleted"

echo "Case 15: gh evidence failures fail closed on both queries"
build_world
make_worker feat/ghfail worker-g
write_metadata <<JSON
{"session":{"id":"worker-g"},"runtime":{"provider_lease":{"file":""}}}
JSON
FAKE_GH_MERGED_FAIL=1 run_helper --execute
assert_eq "$HELPER_RC" "2" "merged-query failure defers cleanup"
assert_contains "reason=pr_evidence_unavailable" "$ERR" "merged-query deferred reason"
set_merged_pr "$TIP"
FAKE_GH_OPEN_FAIL=1 run_helper --execute
assert_eq "$HELPER_RC" "2" "open-query failure defers cleanup"
assert_contains "reason=child_pr_query_unavailable" "$ERR" "open-query deferred reason"
git -C "$PROJECT" show-ref --verify --quiet "refs/heads/$BRANCH" && ok "branch kept through gh failures" || bad "branch deleted through gh failures"

echo "Case 16: usage errors exit 64"
build_world
make_worker feat/usage worker-u
set_merged_pr "$TIP"
run_helper --nonsense
assert_eq "$HELPER_RC" "64" "unknown argument exits 64"

echo ""
echo "post-merge-cleanup tests: $passed passed, $failed failed"
[ "$failed" -eq 0 ]
