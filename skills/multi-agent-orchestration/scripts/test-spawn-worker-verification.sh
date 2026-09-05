#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=spawn-worker-deps.sh
source "$SCRIPT_DIR/spawn-worker-deps.sh"

CASE_ROOT=$(mktemp -d)
trap 'rm -rf "$CASE_ROOT"' EXIT
passed=0
failed=0
ok() { printf 'PASS: %s\n' "$1"; passed=$((passed + 1)); }
bad() { printf 'FAIL: %s\n' "$1" >&2; failed=$((failed + 1)); }

reset_case() {
  PROJECT_DIR="$CASE_ROOT/project"
  mkdir -p "$PROJECT_DIR"
  VERIFY_COMMANDS=()
  VERIFY_COMMAND_SOURCE=""
  REQUIRE_VERIFICATION=0
  VERIFICATION_CONTRACT=""
  VERIFICATION_TASK_ID=""
  PROJECT_CONFIG_FILE=""
  WORKER_TYPE=""
}

write_contract() {
  cat > "$CASE_ROOT/contract.json" <<'JSON'
{"schema_version":"dispatch-value-gate.v2","mode":"converge","pending_acceptance_prs":0,"explore_authorized_by":"","explore_expires_at":"","tasks":[
  {"task_id":"PY-NESTED","status":"READY","kind":"bugfix","value_kind":"implementation","value_identity":"py-nested","problem_target":"nested Python verification authority","consumer":"current wave","decision_or_gate_changed":"worker can verify on first attempt","engineering_assets":["src/example.py"],"doc_assets":[],"verification_commands":["cd 律师IP/motion-composer && python3 -m unittest discover -s tests -v"],"worker_pr_policy":"worker_pr","consume_by":"current wave","expiry":"archive after acceptance","observable_acceptance":"exact command exits zero","starts_external_resources":false,"resource_owner":"none","state_transition":""},
  {"task_id":"MERGE-GATE","status":"READY","kind":"merge-verification","value_kind":"merge_gate","value_identity":"merge-gate","problem_target":"PR #1","consumer":"PM merge decision","decision_or_gate_changed":"accept or reject PR #1","gate_target":{"pr":"#1","head_sha":"1111111111111111111111111111111111111111"},"engineering_assets":[],"doc_assets":[],"verification_commands":[],"worker_pr_policy":"no_worker_pr","consume_by":"current wave","expiry":"archive after decision","observable_acceptance":"pinned merge decision","starts_external_resources":false,"resource_owner":"none","state_transition":""}
]}
JSON
}

echo "Case 1: dispatch contract preserves an exact nested Python command"
reset_case
write_contract
VERIFICATION_CONTRACT="$CASE_ROOT/contract.json"
VERIFICATION_TASK_ID="PY-NESTED"
resolve_verification_commands >/dev/null && validate_verification_commands
exact='cd 律师IP/motion-composer && python3 -m unittest discover -s tests -v'
if [ "${VERIFY_COMMANDS[0]}" = "$exact" ] \
  && [ "$VERIFY_COMMAND_SOURCE" = "dispatch-contract:PY-NESTED" ] \
  && [ "$REQUIRE_VERIFICATION" -eq 1 ]; then
  ok "contract command remains byte-for-byte exact and requires verification"
else
  bad "contract command/source/requirement drifted"
fi

echo "Case 2: explicit nested-project profile is consumed without command rewriting"
reset_case
mkdir -p "$PROJECT_DIR/.claude"
cat > "$PROJECT_DIR/.claude/orchestration.config.json" <<'JSON'
{"schema":"multi-agent-orchestration.project-config.v1","verification":{"required":true,"default":["python3 -m unittest discover -s tests -v"],"by_worker_type":{"motion-composer":["cd 律师IP/motion-composer && python3 -m unittest discover -s tests -v"]}}}
JSON
WORKER_TYPE="motion-composer"
resolve_verification_commands >/dev/null && validate_verification_commands
if [ "${VERIFY_COMMANDS[0]}" = "$exact" ] \
  && [ "$VERIFY_COMMAND_SOURCE" = "project-config:by_worker_type:motion-composer" ]; then
  ok "project profile preserves the complete nested command"
else
  bad "project profile changed or lost the nested command"
fi

echo "Case 3: unknown worker type fails closed"
reset_case
WORKER_TYPE="missing"
if resolve_verification_commands >/dev/null 2>&1; then bad "unknown worker type passed"; else ok "unknown worker type rejected"; fi
rm -f "$PROJECT_DIR/.claude/orchestration.config.json"

echo "Case 4: required empty project profile fails before launch"
reset_case
cat > "$CASE_ROOT/empty-config.json" <<'JSON'
{"schema":"multi-agent-orchestration.project-config.v1","verification":{"required":true,"default":[],"by_worker_type":{}}}
JSON
PROJECT_CONFIG_FILE="$CASE_ROOT/empty-config.json"
if resolve_verification_commands >/dev/null && validate_verification_commands >/dev/null 2>&1; then
  bad "required empty profile passed"
else
  ok "required empty profile rejected"
fi

echo "Case 5: malformed config fails closed"
reset_case
printf '{"schema":"wrong","verification":{}}\n' > "$CASE_ROOT/bad-config.json"
PROJECT_CONFIG_FILE="$CASE_ROOT/bad-config.json"
if resolve_verification_commands >/dev/null 2>&1; then bad "malformed config passed"; else ok "malformed config rejected"; fi

echo "Case 6: duplicate exact commands fail closed"
reset_case
VERIFY_COMMANDS=("python3 -m unittest" "python3 -m unittest")
resolve_verification_commands >/dev/null
if validate_verification_commands >/dev/null 2>&1; then bad "duplicate commands passed"; else ok "duplicate commands rejected"; fi

echo "Case 7: install-like verification remains a separate authority"
reset_case
VERIFY_COMMANDS=("pip install pytest")
resolve_verification_commands >/dev/null
if validate_verification_commands >/dev/null 2>&1; then bad "install-like verify passed"; else ok "install-like verify rejected"; fi

echo "Case 8: CLI and contract cannot silently diverge"
reset_case
write_contract
VERIFY_COMMANDS=("python3 -m unittest")
VERIFICATION_CONTRACT="$CASE_ROOT/contract.json"
VERIFICATION_TASK_ID="PY-NESTED"
if resolve_verification_commands >/dev/null 2>&1; then bad "two authorities passed"; else ok "two authorities rejected"; fi

echo "Case 9: root Python unittest discovery is bounded and deterministic"
reset_case
printf '[project]\nname="demo"\n' > "$PROJECT_DIR/pyproject.toml"
mkdir -p "$PROJECT_DIR/tests"
resolve_verification_commands >/dev/null && validate_verification_commands
if [ "${VERIFY_COMMANDS[*]}" = "python3 -m unittest discover -s tests -v" ]; then
  ok "root Python project gets one bounded unittest command"
else
  bad "unexpected Python discovery: ${VERIFY_COMMANDS[*]-}"
fi

echo "Case 10: merge-gate contract may intentionally require no command"
reset_case
write_contract
VERIFICATION_CONTRACT="$CASE_ROOT/contract.json"
VERIFICATION_TASK_ID="MERGE-GATE"
if resolve_verification_commands >/dev/null && validate_verification_commands; then
  ok "explicit merge gate keeps empty verification valid"
else
  bad "merge gate empty verification was rejected"
fi

echo "Case 11: a locally valid task cannot authorize from an invalid whole contract"
reset_case
write_contract
python3 - "$CASE_ROOT/contract.json" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
data["tasks"][1]["consumer"] = ""
with open(path, "w", encoding="utf-8") as stream:
    json.dump(data, stream, ensure_ascii=False)
PY
VERIFICATION_CONTRACT="$CASE_ROOT/contract.json"
VERIFICATION_TASK_ID="PY-NESTED"
if resolve_verification_commands >/dev/null 2>&1; then
  bad "invalid whole contract authorized a selected task"
else
  ok "full dispatch-value preflight rejects invalid sibling task"
fi

echo "Case 12: project config rejects embedded U+0000 before array decoding"
reset_case
mkdir -p "$PROJECT_DIR/.claude"
python3 - "$PROJECT_DIR/.claude/orchestration.config.json" <<'PY'
import json, sys
with open(sys.argv[1], "w", encoding="utf-8") as stream:
    json.dump({
        "schema": "multi-agent-orchestration.project-config.v1",
        "verification": {
            "required": True,
            "default": ["pwd\u0000git status --short"],
            "by_worker_type": {},
        },
    }, stream)
PY
if resolve_verification_commands >"$CASE_ROOT/nul-project.out" 2>&1; then
  bad "project U+0000 command was split into authority"
elif [ "${#VERIFY_COMMANDS[@]}" -eq 0 ] \
  && grep -qF "must not contain U+0000" "$CASE_ROOT/nul-project.out"; then
  ok "project U+0000 command rejected with zero decoded authority"
else
  bad "project U+0000 rejection was not fail-closed"
fi
rm -f "$PROJECT_DIR/.claude/orchestration.config.json"

echo "Case 13: dispatch contract rejects embedded U+0000 before array decoding"
reset_case
write_contract
python3 - "$CASE_ROOT/contract.json" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
data["tasks"][0]["verification_commands"] = ["pwd\u0000git status --short"]
with open(path, "w", encoding="utf-8") as stream:
    json.dump(data, stream, ensure_ascii=False)
PY
VERIFICATION_CONTRACT="$CASE_ROOT/contract.json"
VERIFICATION_TASK_ID="PY-NESTED"
if resolve_verification_commands >"$CASE_ROOT/nul-contract.out" 2>&1; then
  bad "contract U+0000 command was split into authority"
elif [ "${#VERIFY_COMMANDS[@]}" -eq 0 ] \
  && grep -qF "must not contain U+0000" "$CASE_ROOT/nul-contract.out"; then
  ok "contract U+0000 command rejected with zero decoded authority"
else
  bad "contract U+0000 rejection was not fail-closed"
fi

printf 'spawn-worker verification tests: %s passed, %s failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
