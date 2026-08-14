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

echo ""
echo "Result: $pass pass, $fail fail"
[ "$fail" -eq 0 ]
