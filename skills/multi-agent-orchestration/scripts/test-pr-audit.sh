#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT
BIN="$TMP_ROOT/bin"; REMOTE="$TMP_ROOT/remote.git"; REPO="$TMP_ROOT/repo"
mkdir -p "$BIN"
git init -q --bare "$REMOTE"
git init -q "$REPO"
git -C "$REPO" config user.name Audit
git -C "$REPO" config user.email audit@example.invalid
printf 'base\n' > "$REPO/file.txt"
git -C "$REPO" add file.txt && git -C "$REPO" commit -qm base
git -C "$REPO" branch -M main
git -C "$REPO" remote add origin "$REMOTE"
git -C "$REPO" push -qu origin main
git -C "$REPO" checkout -qb feat/audit
printf 'worker\n' >> "$REPO/file.txt"
git -C "$REPO" commit -qam worker
HEAD_SHA=$(git -C "$REPO" rev-parse HEAD)
BASE_SHA=$(git -C "$REPO" rev-parse origin/main)
git -C "$REPO" diff "$BASE_SHA" "$HEAD_SHA" > "$TMP_ROOT/diff"

cat > "$BIN/gh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
case "$1 $2" in
  "pr list")
    [ "${AUDIT_LIST_FAIL:-0}" -eq 0 ] || { echo 'failed https://user:super-secret@ghe.example/acme/repo?token=also-secret' >&2; exit 43; }
    cat "$AUDIT_FIXTURE"
    ;;
  "pr diff") [ "${AUDIT_DIFF_FAIL:-0}" -eq 0 ] || exit 41; cat "$AUDIT_DIFF" ;;
  *) exit 42 ;;
esac
SH
chmod +x "$BIN/gh"
export PATH="$BIN:$PATH" AUDIT_DIFF="$TMP_ROOT/diff" AUDIT_FIXTURE="$TMP_ROOT/prs.json"

pass=0; fail=0
ok() { echo "  ✓ $1"; pass=$((pass+1)); }
bad() { echo "  ✗ $1" >&2; fail=$((fail+1)); }
decision() { python3 "$SCRIPT_DIR/pr-audit.py" --repo "$REPO" --base-ref main --head-ref feat/audit --head-sha "$HEAD_SHA" --task-id Task-097 --agent-id agent-a | jq -r '.decision'; }

printf '[]\n' > "$AUDIT_FIXTURE"
[ "$(decision)" = create ] && ok "zero candidates permits create" || bad "zero classification"

printf '[{"number":1,"url":"https://example/pull/1","baseRefName":"main","baseRefOid":"%s","headRefName":"feat/audit","headRefOid":"%s","headRepositoryOwner":{"login":"repository"},"isCrossRepository":false,"title":"Task-097 by agent-a","body":"Task: Task-097\\nAgent: agent-a","reviewDecision":"APPROVED","statusCheckRollup":[]}]\n' "$BASE_SHA" "$HEAD_SHA" > "$AUDIT_FIXTURE"
OUT=$(python3 "$SCRIPT_DIR/pr-audit.py" --repo "$REPO" --base-ref main --head-ref feat/audit --head-sha "$HEAD_SHA" --task-id Task-097 --agent-id agent-a)
[ "$(printf '%s' "$OUT" | jq -r '.decision')" = adopt ] && [ "$(printf '%s' "$OUT" | jq -r '.counts.exact')" = 1 ] && ok "one exact PR is adopted" || bad "exact adoption"
[ "$(printf '%s' "$OUT" | jq -r '.exact[0].reasons[0]')" = base_ref_oid_head_ref_oid_repository_task_agent_match ] \
  && ok "exact reason names every authoritative match" || bad "exact reason is inaccurate"
[ "$(AUDIT_DIFF_FAIL=1 decision)" = ambiguous ] && ok "exact metadata with unknown PR diff remains ambiguous" || bad "exact diff failure was adopted"

printf 'diff --git a/file.txt b/file.txt\n--- a/file.txt\n+++ b/file.txt\n@@ -1 +1 @@\n-base\n+different worker\n' > "$TMP_ROOT/different.diff"
MISMATCH=$(AUDIT_DIFF="$TMP_ROOT/different.diff" python3 "$SCRIPT_DIR/pr-audit.py" --repo "$REPO" --base-ref main --head-ref feat/audit --head-sha "$HEAD_SHA" --task-id Task-097 --agent-id agent-a)
[ "$(printf '%s' "$MISMATCH" | jq -r '.decision')" = ambiguous ] && \
  [ "$(printf '%s' "$MISMATCH" | jq -r '.counts.suspected')" = 1 ] && \
  [ "$(printf '%s' "$MISMATCH" | jq -r '.suspected[0].reasons[]' | grep -c '^pr_diff_mismatch$')" = 1 ] \
  && ok "exact metadata with a different PR diff is suspected" || bad "PR diff mismatch was adopted or reason unreachable"

WRONG_SHA=$(printf 'f%.0s' {1..40})
printf '[{"number":2,"url":"https://example/pull/2","baseRefName":"main","baseRefOid":"%s","headRefName":"feat/audit","headRefOid":"%s","headRepositoryOwner":{"login":"repository"},"isCrossRepository":false,"title":"Task-097 by agent-a","body":"Task: Task-097\\nAgent: agent-a","reviewDecision":"APPROVED","statusCheckRollup":[]}]\n' "$BASE_SHA" "$WRONG_SHA" > "$AUDIT_FIXTURE"
[ "$(decision)" = ambiguous ] && ok "same head with different SHA is ambiguous" || bad "same-head SHA mismatch"

printf '[{"number":3,"url":"https://example/pull/3","baseRefName":"main","baseRefOid":"%s","headRefName":"feat/other","headRefOid":"%s","headRepositoryOwner":{"login":"repository"},"isCrossRepository":false,"title":"other","body":"other","reviewDecision":"APPROVED","statusCheckRollup":[]}]\n' "$BASE_SHA" "$WRONG_SHA" > "$AUDIT_FIXTURE"
[ "$(AUDIT_DIFF_FAIL=1 decision)" = ambiguous ] && ok "unknown PR diff fails closed" || bad "diff unknown classification"

printf '[{"number":4,"url":"https://example/pull/4","baseRefName":"main","baseRefOid":"%s","headRefName":"feat/audit","headRefOid":"%s","headRepositoryOwner":{"login":"repository"},"isCrossRepository":false,"title":"Task-97 by agent-a","body":"Task: Task-97\\nAgent: agent-a","reviewDecision":"APPROVED","statusCheckRollup":[]}]\n' "$BASE_SHA" "$HEAD_SHA" > "$AUDIT_FIXTURE"
[ "$(python3 "$SCRIPT_DIR/pr-audit.py" --repo "$REPO" --base-ref main --head-ref feat/audit --head-sha "$HEAD_SHA" --task-id Task-9 --agent-id agent-a | jq -r '.decision')" = ambiguous ] && ok "ownership uses token boundaries" || bad "ownership substring collision"

printf '[{"number":41,"url":"https://example/pull/41","baseRefName":"main","baseRefOid":"%s","headRefName":"feat/audit","headRefOid":"%s","headRepositoryOwner":{"login":"repository"},"isCrossRepository":false,"title":"lookalike trailers","body":"Task: Task-097-old\\nAgent: agent-a-copy","reviewDecision":"APPROVED","statusCheckRollup":[]}]\n' "$BASE_SHA" "$HEAD_SHA" > "$AUDIT_FIXTURE"
[ "$(decision)" = ambiguous ] && ok "Task/Agent trailers require exact independent values" || bad "trailer prefix collision"

printf '[{"number":42,"url":"https://example/pull/42","baseRefName":"main","baseRefOid":"%s","headRefName":"feat/audit","headRefOid":"%s","headRepositoryOwner":{"login":"fork-owner"},"isCrossRepository":true,"title":"same refs from fork","body":"Task: Task-097\\nAgent: agent-a","reviewDecision":"APPROVED","statusCheckRollup":[]}]\n' "$BASE_SHA" "$HEAD_SHA" > "$AUDIT_FIXTURE"
[ "$(decision)" = ambiguous ] && ok "fork/cross-repository head cannot be exact" || bad "repository ownership was ignored"

printf '[{"number":43,"url":"https://example/pull/43","baseRefName":"main","baseRefOid":"%s","headRefName":"feat/same-content","headRefOid":"%s","headRepositoryOwner":{"login":"repository"},"isCrossRepository":false,"title":"other branch","body":"other","reviewDecision":"APPROVED","statusCheckRollup":[]}]\n' "$BASE_SHA" "$WRONG_SHA" > "$AUDIT_FIXTURE"
SAME_CONTENT=$(python3 "$SCRIPT_DIR/pr-audit.py" --repo "$REPO" --base-ref main --head-ref feat/audit --head-sha "$HEAD_SHA" --task-id Task-097 --agent-id agent-a)
[ "$(printf '%s' "$SAME_CONTENT" | jq -r '.decision')" = ambiguous ] && \
  [ "$(printf '%s' "$SAME_CONTENT" | jq -r '.suspected[0].reasons[]' | grep -c same_content_different_head)" = 1 ] \
  && ok "same content on a different branch is suspected" || bad "same-content branch was missed"

printf '[{"number":5,"url":"https://example/pull/5","baseRefName":"main","baseRefOid":"%s","headRefName":"feat/audit","headRefOid":"%s","headRepositoryOwner":{"login":"repository"},"isCrossRepository":false,"title":"Task-097 by agent-a","body":"Task: Task-097\\nAgent: agent-a","reviewDecision":"APPROVED","statusCheckRollup":[]},{"number":6,"url":"https://example/pull/6","baseRefName":"main","baseRefOid":"%s","headRefName":"feat/audit","headRefOid":"%s","headRepositoryOwner":{"login":"repository"},"isCrossRepository":false,"title":"Task-097 by agent-a","body":"Task: Task-097\\nAgent: agent-a","reviewDecision":"APPROVED","statusCheckRollup":[]}]\n' "$BASE_SHA" "$HEAD_SHA" "$BASE_SHA" "$HEAD_SHA" > "$AUDIT_FIXTURE"
[ "$(decision)" = ambiguous ] && ok "multiple exact PRs are ambiguous" || bad "multiple exact classification"

python3 - "$AUDIT_FIXTURE" <<'PY'
import json,sys
rows=[]
for number in range(1,102):
    rows.append({"number":number,"url":f"https://example/pull/{number}",
      "baseRefName":"other","baseRefOid":"0"*40,"headRefName":f"feat/other-{number}",
      "headRefOid":"f"*40,"headRepositoryOwner":{"login":"repository"},
      "isCrossRepository":False,"title":"other","body":"other",
      "reviewDecision":"APPROVED","statusCheckRollup":[]})
with open(sys.argv[1],"w",encoding="utf-8") as f: json.dump(rows,f)
PY
TRUNCATED=$(python3 "$SCRIPT_DIR/pr-audit.py" --repo "$REPO" --base-ref main --head-ref feat/audit --head-sha "$HEAD_SHA")
[ "$(printf '%s' "$TRUNCATED" | jq -r '.decision')" = ambiguous ] && \
  [ "$(printf '%s' "$TRUNCATED" | jq -r '.candidate_set_truncated')" = true ] \
  && ok "101-row candidate page fails closed as truncated" || bad "truncation permitted create"

REMOTE_FORMS=$(python3 - "$SCRIPT_DIR/pr-audit.py" <<'PY'
import importlib.util,sys
spec=importlib.util.spec_from_file_location("pr_audit",sys.argv[1]); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
for url in ("https://user:secret@ghe.example/acme/repo.git", "git@ghe.example:acme/repo.git", "ssh://git@ghe.example/acme/repo.git"):
    print(mod.canonical_remote(url))
PY
)
[ "$REMOTE_FORMS" = $'ghe.example/acme/repo\nghe.example/acme/repo\nghe.example/acme/repo' ] \
  && ok "HTTPS credentials, SCP SSH and ssh:// canonicalize without userinfo" || bad "GHE remote canonicalization"

printf '[]\n' > "$AUDIT_FIXTURE"
set +e
AUDIT_LIST_FAIL=1 python3 "$SCRIPT_DIR/pr-audit.py" --repo "$REPO" --base-ref main --head-ref feat/audit --head-sha "$HEAD_SHA" \
  > "$TMP_ROOT/fail.stdout" 2> "$TMP_ROOT/fail.stderr"
command_fail_rc=$?
set -e
[ "$command_fail_rc" -eq 2 ] && [ ! -s "$TMP_ROOT/fail.stdout" ] && \
  grep -q 'PR_AUDIT_ERROR: command_failed command=gh pr list exit=43' "$TMP_ROOT/fail.stderr" && \
  ! grep -Eq 'super-secret|also-secret|Traceback' "$TMP_ROOT/fail.stderr" \
  && ok "command failure is stable, stderr-only and credential-redacted" || bad "command failure leaked or traced back"

ONLY_GIT="$TMP_ROOT/only-git"; mkdir -p "$ONLY_GIT"
ln -s "$(command -v git)" "$ONLY_GIT/git"
PYTHON_BIN=$(command -v python3)
set +e
PATH="$ONLY_GIT" "$PYTHON_BIN" "$SCRIPT_DIR/pr-audit.py" --repo "$REPO" --base-ref main --head-ref feat/audit --head-sha "$HEAD_SHA" \
  > "$TMP_ROOT/missing.stdout" 2> "$TMP_ROOT/missing.stderr"
missing_rc=$?
set -e
[ "$missing_rc" -eq 2 ] && [ ! -s "$TMP_ROOT/missing.stdout" ] && \
  grep -qx 'PR_AUDIT_ERROR: dependency_missing command=gh' "$TMP_ROOT/missing.stderr" && \
  ! grep -q Traceback "$TMP_ROOT/missing.stderr" \
  && ok "missing gh dependency has a stable no-traceback error" || bad "missing dependency error contract"

STDERR="$TMP_ROOT/orchestrate.err"
JSON=$(bash "$SCRIPT_DIR/pm-orchestrate.sh" pr-audit --worktree "$REPO" --base-ref main --head-ref feat/audit --head-sha "$HEAD_SHA" --task-id Task-097 --agent-id agent-a 2>"$STDERR")
printf '%s' "$JSON" | jq -e '.schema_version=="pr-audit.v1"' >/dev/null && ok "pm-orchestrate stdout is one JSON document" || bad "pm-orchestrate JSON stdout"
grep -q '^PM_ORCHESTRATE_PR_AUDIT:' "$STDERR" && ok "pm-orchestrate receipt is stderr-only" || bad "pm-orchestrate receipt channel"

printf 'pr-audit tests: %s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
