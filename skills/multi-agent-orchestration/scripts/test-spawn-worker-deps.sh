#!/usr/bin/env bash
# Regression tests for Task-045/046 dependency compensation and verify defaults.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=spawn-worker-deps.sh
source "$SCRIPT_DIR/spawn-worker-deps.sh"

TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT
pass=0
fail=0
ok() { echo "  ✓ $1"; pass=$((pass + 1)); }
bad() { echo "  ✗ $1" >&2; fail=$((fail + 1)); }

PROJECT_DIR="$TMP_ROOT/project"
mkdir -p "$PROJECT_DIR/node_modules"
cat > "$PROJECT_DIR/package.json" <<'JSON'
{
  "scripts": {
    "typecheck": "tsc --noEmit",
    "lint": "eslint .",
    "test": "vitest run",
    "build": "vite build",
    "dev": "vite"
  }
}
JSON

echo "Case 1: out-of-tree worker receives an exact node_modules symlink"
WORKTREE="$TMP_ROOT/outside-a"
mkdir -p "$WORKTREE"
ensure_worktree_deps >/dev/null
if [ -L "$WORKTREE/node_modules" ] \
  && [ "$(cd "$WORKTREE/node_modules" && pwd -P)" = "$(cd "$PROJECT_DIR/node_modules" && pwd -P)" ]; then
  ok "out-of-tree symlink points to project dependencies"
else
  bad "out-of-tree symlink is missing or points elsewhere"
fi

echo "Case 2: in-tree worker relies on ancestor resolution without a symlink"
WORKTREE="$PROJECT_DIR/.claude/worktrees/inside"
mkdir -p "$WORKTREE"
ensure_worktree_deps >/dev/null
[ ! -e "$WORKTREE/node_modules" ] && ok "in-tree worktree was not modified" || bad "in-tree worktree received an unnecessary node_modules"

echo "Case 3: existing dependency directory is preserved"
WORKTREE="$TMP_ROOT/outside-existing"
mkdir -p "$WORKTREE/node_modules"
ensure_worktree_deps >/dev/null
[ -d "$WORKTREE/node_modules" ] && [ ! -L "$WORKTREE/node_modules" ] && ok "existing directory preserved" || bad "existing directory was replaced"

echo "Case 4: broken symlink fails loud"
WORKTREE="$TMP_ROOT/outside-broken"
mkdir -p "$WORKTREE"
ln -s "$TMP_ROOT/missing-node-modules" "$WORKTREE/node_modules"
if ensure_worktree_deps >/dev/null 2>&1; then
  bad "broken symlink was accepted"
else
  ok "broken symlink blocks spawn"
fi

echo "Case 5: default verification commands come only from declared scripts"
VERIFY_COMMANDS=()
inject_default_verify_commands >/dev/null
expected=("npm run typecheck" "npm run lint" "npm run test" "npm run build")
if [ "${VERIFY_COMMANDS[*]}" = "${expected[*]}" ]; then
  ok "default verification commands injected deterministically"
else
  bad "unexpected defaults: ${VERIFY_COMMANDS[*]}"
fi

echo "Case 6: explicit PM verification commands are never overwritten"
VERIFY_COMMANDS=("npm run test -- --runInBand")
inject_default_verify_commands >/dev/null
[ "${#VERIFY_COMMANDS[@]}" -eq 1 ] && [ "${VERIFY_COMMANDS[0]}" = "npm run test -- --runInBand" ] \
  && ok "explicit verify command preserved" || bad "explicit verify command was changed"

echo "Case 7: two independent out-of-tree workers can link concurrently"
for worker in concurrent-a concurrent-b; do
  (
    WORKTREE="$TMP_ROOT/$worker"
    mkdir -p "$WORKTREE"
    ensure_worktree_deps >/dev/null
    [ -L "$WORKTREE/node_modules" ]
  ) &
done
wait
if [ -L "$TMP_ROOT/concurrent-a/node_modules" ] && [ -L "$TMP_ROOT/concurrent-b/node_modules" ]; then
  ok "concurrent workers received independent symlinks"
else
  bad "concurrent dependency compensation was incomplete"
fi

echo "Case 8: Makefile-only project gets whitelisted make targets (Wave 2 regression)"
PROJECT_DIR="$TMP_ROOT/make-project"
mkdir -p "$PROJECT_DIR"
cat > "$PROJECT_DIR/Makefile" <<'MK'
PROJECT_DIR := .
RUNTIME_DIR := .runtime
.PHONY: start bootstrap test test-compat test-fixture-browser security-scan validate-skill ci
start:
	python -m badminton_lab serve
test: test-compat
test-compat:
	python tests/run.py
test-fixture-browser:
	bash tests/ci/run_fixture.sh
build/app.js:
	echo fake
security-scan:
	python tests/ci/security_scan.py
ci: test validate-skill security-scan
MK
VERIFY_COMMANDS=()
inject_default_verify_commands >/dev/null
expected_make=("make ci" "make test" "make test-compat" "make test-fixture-browser")
if [ "${VERIFY_COMMANDS[*]}" = "${expected_make[*]}" ]; then
  ok "Makefile targets injected in sorted order, non-whitelisted excluded"
else
  bad "unexpected Makefile defaults: ${VERIFY_COMMANDS[*]}"
fi

echo "Case 9: Makefile fallback kicks in when package.json declares no verify scripts"
PROJECT_DIR="$TMP_ROOT/mixed-project"
mkdir -p "$PROJECT_DIR"
printf '{"scripts": {"dev": "vite"}}\n' > "$PROJECT_DIR/package.json"
printf '.PHONY: test lint\ntest:\n\ttrue\nlint:\n\ttrue\n' > "$PROJECT_DIR/Makefile"
VERIFY_COMMANDS=()
inject_default_verify_commands >/dev/null
expected_mixed=("make lint" "make test")
if [ "${VERIFY_COMMANDS[*]}" = "${expected_mixed[*]}" ]; then
  ok "Makefile fallback used when npm scripts yield nothing"
else
  bad "unexpected mixed defaults: ${VERIFY_COMMANDS[*]}"
fi

echo "Case 10: npm-first project with Makefile present does not double-inject"
PROJECT_DIR="$TMP_ROOT/npm-project"
mkdir -p "$PROJECT_DIR"
printf '{"scripts": {"test": "vitest run", "lint": "eslint ."}}\n' > "$PROJECT_DIR/package.json"
printf '.PHONY: test ci\ntest:\n\tnpm test\nci:\n\tnpm test\n' > "$PROJECT_DIR/Makefile"
VERIFY_COMMANDS=()
inject_default_verify_commands >/dev/null
expected_npm=("npm run lint" "npm run test")
if [ "${VERIFY_COMMANDS[*]}" = "${expected_npm[*]}" ]; then
  ok "npm scripts stay primary when both manifests exist"
else
  bad "unexpected npm-first defaults: ${VERIFY_COMMANDS[*]}"
fi

echo "Case 11: --python-runtime-symlink links a validated runtime (Task-061)"
PROJECT_DIR="$TMP_ROOT/py-project"
mkdir -p "$PROJECT_DIR"
printf 'print("ok")\n' > "$PROJECT_DIR/app.py"
printf 'requests>=2.0\n' > "$PROJECT_DIR/requirements.txt"
mkdir -p "$TMP_ROOT/shared-runtime/venv/bin"
printf '#!/bin/sh\n' > "$TMP_ROOT/shared-runtime/venv/bin/python"
chmod +x "$TMP_ROOT/shared-runtime/venv/bin/python"
WORKTREE="$TMP_ROOT/py-worktree"
mkdir -p "$WORKTREE"
PYTHON_RUNTIME_SYMLINK="$TMP_ROOT/shared-runtime"
ensure_worktree_deps >/dev/null
if [ -L "$WORKTREE/.runtime" ] && [ "$(readlink "$WORKTREE/.runtime")" = "$TMP_ROOT/shared-runtime" ]; then
  ok "runtime symlink created after interpreter validation"
else
  bad "runtime symlink missing or mispointed"
fi

echo "Case 12: 0-byte placeholder interpreter refuses spawn (Wave 1 fake-venv lesson)"
WORKTREE="$TMP_ROOT/py-worktree-bad"
mkdir -p "$WORKTREE"
mkdir -p "$TMP_ROOT/bad-runtime/venv/bin"
: > "$TMP_ROOT/bad-runtime/venv/bin/python"
PYTHON_RUNTIME_SYMLINK="$TMP_ROOT/bad-runtime"
if ensure_worktree_deps >/dev/null 2>&1; then
  bad "0-byte placeholder interpreter was accepted"
else
  ok "0-byte placeholder interpreter blocks spawn"
fi

echo "Case 13: existing worktree .runtime is never touched"
WORKTREE="$TMP_ROOT/py-worktree-exists"
mkdir -p "$WORKTREE/.runtime/models"
PYTHON_RUNTIME_SYMLINK="$TMP_ROOT/shared-runtime"
ensure_worktree_deps >/dev/null
if [ -d "$WORKTREE/.runtime" ] && [ ! -L "$WORKTREE/.runtime" ]; then
  ok "existing .runtime directory preserved"
else
  bad "existing .runtime was replaced"
fi

echo ""
echo "Result: $pass pass, $fail fail"
[ "$fail" -eq 0 ]
