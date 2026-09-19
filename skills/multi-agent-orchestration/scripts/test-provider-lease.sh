#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT
LEASE="$SCRIPT_DIR/provider-lease.py"
TEST_BIN="$TMP_ROOT/bin"
TMUX_STATE="$TMP_ROOT/tmux-state"
mkdir -p "$TEST_BIN" "$TMUX_STATE"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  "state_root=$(printf '%q' "$TMUX_STATE")" \
  'session=""' \
  'for ((i=1; i<=$#; i++)); do' \
  '  if [ "${!i}" = "-s" ] || [ "${!i}" = "-t" ]; then j=$((i + 1)); session="${!j}"; fi' \
  'done' \
  'case "${1:-}" in' \
  '  new-session) : > "$state_root/$session" ;;' \
  '  has-session) [ -f "$state_root/$session" ] ;;' \
  '  kill-session) rm -f "$state_root/$session" ;;' \
  '  *) exit 1 ;;' \
  'esac' \
  > "$TEST_BIN/tmux"
chmod +x "$TEST_BIN/tmux"
export PATH="$TEST_BIN:$PATH"

first=$(python3 "$LEASE" acquire --root "$TMP_ROOT/leases" --provider provider-a \
  --backend codex --session worker-a --project "$TMP_ROOT/project" --max 1 --owner-pid $$)
first_file=$(printf '%s' "$first" | jq -r '.lease_file')
[ -f "$first_file" ]

if python3 "$LEASE" acquire --root "$TMP_ROOT/leases" --provider provider-a \
  --backend claude-code --session worker-b --project "$TMP_ROOT/project" --max 1 --owner-pid $$ \
  >/dev/null 2>&1; then
  echo "FAIL: provider limit did not block the second lease" >&2
  exit 1
fi
echo "PASS: provider limit blocks the second active lease"

if python3 "$LEASE" acquire --root "$TMP_ROOT/leases" --provider provider-other \
  --backend codex --session worker-a --project "$TMP_ROOT/project" --max 3 --owner-pid $$ \
  >/dev/null 2>&1; then
  echo "FAIL: the same session acquired a second provider lease" >&2
  exit 1
fi
echo "PASS: session identity is unique across the repository lease root"

python3 "$LEASE" finalize --root "$TMP_ROOT/leases" --lease-file "$first_file" --session worker-a \
  --transport tmux --resource-handle lease-test-missing-session >/dev/null
python3 "$LEASE" acquire --root "$TMP_ROOT/leases" --provider provider-a \
  --backend claude-code --session worker-b --project "$TMP_ROOT/project" --max 1 --owner-pid $$ \
  >/dev/null
echo "PASS: stale finalized tmux lease is reclaimed from liveness evidence"

second_file=$(find "$TMP_ROOT/leases" -name '*.json' -type f | head -1)
if python3 "$LEASE" release --root "$TMP_ROOT/leases" --lease-file "$second_file" --session wrong-session --resource-settled >/dev/null 2>&1; then
  echo "FAIL: mismatched session released another worker's lease" >&2
  exit 1
fi
echo "PASS: exact session binding protects lease release"

python3 "$LEASE" release --root "$TMP_ROOT/leases" --lease-file "$second_file" --session worker-b \
  --resource-settled --owner-pid $$ >/dev/null
[ ! -e "$second_file" ]
echo "PASS: exact lease release succeeds"

outside="$TMP_ROOT/outside.json"
printf '%s\n' '{"schema":"multi-agent-orchestration.provider-lease.v1","session":"worker-b"}' > "$outside"
if python3 "$LEASE" release --root "$TMP_ROOT/leases" --lease-file "$outside" --session worker-b --resource-settled >/dev/null 2>&1; then
  echo "FAIL: untrusted lease path escaped the registry root" >&2
  exit 1
fi
[ -f "$outside" ]
echo "PASS: worker-controlled lease paths cannot escape the trusted registry root"

live=$(python3 "$LEASE" acquire --root "$TMP_ROOT/leases" --provider provider-live \
  --backend codex --session live-session --project "$TMP_ROOT/project" --max 1 --owner-pid $$)
live_file=$(printf '%s' "$live" | jq -r '.lease_file')
tmux new-session -d -s provider-lease-live-smoke 'sleep 30'
python3 "$LEASE" finalize --root "$TMP_ROOT/leases" --lease-file "$live_file" \
  --session live-session --transport tmux --resource-handle provider-lease-live-smoke >/dev/null
if python3 "$LEASE" release --root "$TMP_ROOT/leases" --lease-file "$live_file" \
  --session live-session --resource-settled >/dev/null 2>&1; then
  echo "FAIL: live resource was released from quota" >&2
  tmux kill-session -t provider-lease-live-smoke 2>/dev/null || true
  exit 1
fi
tmux kill-session -t provider-lease-live-smoke
python3 "$LEASE" release --root "$TMP_ROOT/leases" --lease-file "$live_file" \
  --session live-session --resource-settled >/dev/null
echo "PASS: active-resource liveness blocks premature quota release"

stale=$(python3 "$LEASE" acquire --root "$TMP_ROOT/leases" --provider provider-b \
  --backend codex --session stale --project "$TMP_ROOT/project" --max 1 --owner-pid 99999999)
stale_file=$(printf '%s' "$stale" | jq -r '.lease_file')
python3 "$LEASE" acquire --root "$TMP_ROOT/leases" --provider provider-b \
  --backend codex --session replacement --project "$TMP_ROOT/project" --max 1 --owner-pid $$ \
  >/dev/null
[ ! -e "$stale_file" ]
echo "PASS: dead provisional lease is reclaimed"

echo "PROVIDER_LEASE_TEST_OK"
