#!/usr/bin/env bash
# zcode-worker-driver.py contract tests against a stub app-server.
# No ZCode desktop app, no real credentials, no network — CI-safe.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
DRIVER="$SCRIPT_DIR/zcode-worker-driver.py"
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT

pass=0
fail=0
ok() { printf 'PASS: %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf 'FAIL: %s\n' "$1" >&2; fail=$((fail + 1)); }

# ---- stub app-server: speaks the bare-frame protocol -------------------------
# Behavior: answers session/create + session/send, pushes one runtime
# preferences request, emits a state.updated notification, records what it
# received into $STUB_LOG for assertions.
STUB="$TMP_ROOT/stub-app-server.py"
STUB_LOG="$TMP_ROOT/stub-received.log"
cat > "$STUB" <<PYEOF
#!/usr/bin/env python3
import json, os, sys, threading
log_path = os.environ["STUB_LOG"]

def log(event, payload):
    with open(log_path, "a") as fh:
        fh.write(json.dumps({"event": event, "payload": payload}, ensure_ascii=False) + "\n")

def emit(frame):
    sys.stdout.write(json.dumps(frame) + "\n")
    sys.stdout.flush()

# Push a server->client request right away; driver must answer in-window.
emit({"id": "server-test", "method": "session/requestRuntimePreferences",
      "params": {"scope": "runtime-materialization"}})
emit({"method": "state.updated",
      "params": {"patch": {"status": "idle"}, "reason": "session_ready"}})

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    frame = json.loads(line)
    log("received", frame)
    if frame.get("method") == "session/create":
        # Real protocol shape: sessionId nested under result.session.
        emit({"id": frame["id"], "result": {"session": {"sessionId": "sess_stub_001"}}})
    elif frame.get("method") == "session/setModel":
        emit({"id": frame["id"], "result": {}})
    elif frame.get("method") == "session/send":
        emit({"id": frame["id"], "result": {"accepted": True}})
        emit({"method": "state.updated",
              "params": {"patch": {"status": "running"}, "reason": "prompt_started"}})
    elif frame.get("method") == "session/close":
        emit({"id": frame["id"], "result": {}})
        break
PYEOF
chmod +x "$STUB"

# ---- helper: run driver against the stub -------------------------------------
run_driver() {
  local input="$1" cfg="$2"
  shift 2
  printf '%s\n' "$input" | \
    STUB_LOG="$STUB_LOG" \
    ZCODE_CLI_CONFIG="$cfg" \
    python3 "$DRIVER" --bin "$STUB" --cwd "$TMP_ROOT" "$@" 2>&1
}

# ---- Case 1: missing/invalid model config fails fast (exit 64) ---------------
out=$(printf '/quit\n' | ZCODE_CLI_CONFIG="$TMP_ROOT/nope.json" \
  python3 "$DRIVER" --bin "$STUB" --cwd "$TMP_ROOT" 2>&1) && rc=0 || rc=$?
if [ "$rc" -eq 64 ]; then ok "missing config exits 64"; else bad "missing config rc=$rc: $out"; fi

echo '{"model": "x/glm", "provider": {"x": {}}}' > "$TMP_ROOT/good-config.json"
echo '{"skills": {}}' > "$TMP_ROOT/bad-config.json"
out=$(printf '/quit\n' | ZCODE_CLI_CONFIG="$TMP_ROOT/bad-config.json" \
  python3 "$DRIVER" --bin "$STUB" --cwd "$TMP_ROOT" 2>&1) && rc=0 || rc=$?
if [ "$rc" -eq 64 ]; then ok "config without model/provider exits 64"; else bad "bad config rc=$rc: $out"; fi

# ---- Case 2: full flow — prefs answered, send forwarded, render visible -------
: > "$STUB_LOG"
out=$(run_driver '创建 hello.txt
/quit' "$TMP_ROOT/good-config.json") && rc=0 || rc=$?

if [ "$rc" -eq 0 ]; then ok "driver exits 0 after /quit"; else bad "driver rc=$rc"; fi

if grep -q '"id": "server-test", "result"' "$STUB_LOG"; then
  ok "runtimePreferences auto-answered"
else
  bad "runtimePreferences answer missing; stub log: $(cat "$STUB_LOG")"
fi

if grep -q '"method": "session/create"' "$STUB_LOG"; then
  ok "session/create dispatched"
else
  bad "session/create missing"
fi

if grep -q '"content": "创建 hello.txt"' "$STUB_LOG"; then
  ok "plain stdin text forwarded as session/send content"
else
  bad "session/send content missing; log: $(cat "$STUB_LOG")"
fi

if printf '%s\n' "$out" | grep -q 'session ready: sess_stub_001'; then
  ok "sessionId captured from create response"
else
  bad "sessionId not captured; output: $out"
fi

if printf '%s\n' "$out" | grep -q '\[session\] running (prompt_started)'; then
  ok "state.updated rendered as readable line"
else
  bad "rendered state line missing; output: $out"
fi

if grep -q '"method": "session/setModel"' "$STUB_LOG"; then
  bad "setModel dispatched without --model (must keep global model)"
else
  ok "no setModel without --model"
fi

# ---- Case 3: --model providerId/modelId — setModel dispatched with exact ref ----
: > "$STUB_LOG"
out=$(run_driver $'ping\n/quit' "$TMP_ROOT/good-config.json" \
  --model 'builtin:bigmodel-coding-plan/GLM-5.3-Flash') && rc=0 || rc=$?

if [ "$rc" -eq 0 ]; then ok "driver exits 0 with --model"; else bad "driver rc=$rc"; fi

if grep -q '"method": "session/setModel", "params": {"sessionId": "sess_stub_001", "model": {"providerId": "builtin:bigmodel-coding-plan", "modelId": "GLM-5.3-Flash"}, "persistAsWorkspaceLastUsed": false}' "$STUB_LOG"; then
  ok "setModel dispatched with exact modelRef"
else
  bad "setModel params wrong; log: $(cat "$STUB_LOG")"
fi

if printf '%s\n' "$out" | grep -q '\[driver\] setModel ✓ per-worker model applied'; then
  ok "setModel success rendered"
else
  bad "setModel success line missing; output: $out"
fi

# ---- Case 4: bare --model (no provider) — providerId falls back to config ----
: > "$STUB_LOG"
out=$(run_driver $'ping\n/quit' "$TMP_ROOT/good-config.json" --model 'GLM-5.3-Flash') && rc=0 || rc=$?
if grep -q '"model": {"providerId": "x", "modelId": "GLM-5.3-Flash"}, "persistAsWorkspaceLastUsed": false' "$STUB_LOG"; then
  ok "bare --model falls back to config provider prefix"
else
  bad "provider fallback wrong; log: $(cat "$STUB_LOG")"
fi

# ---- summary ------------------------------------------------------------------
printf 'SUMMARY: pass=%d fail=%d\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
