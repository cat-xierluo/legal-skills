#!/usr/bin/env bash
# zcode-worker-driver.py contract tests against a stub app-server.
# No ZCode desktop app, no real credentials, no network — CI-safe.
# Stub proves the DRIVER contract only (argv, readiness barrier, isolation
# entry, control-command routing); it does not simulate official config
# loading — official 0.16.5 app-server rejects --settings (exit 68 case).
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
# Behavior controlled by STUB_MODE:
#   ok         answer create[/setModel]/read/send/close; STUB_MODEL echoes the
#              model the driver set (or the config model when no setModel)
#   mismatch   read answers a DIFFERENT model (read-back verification fault)
#   reject_settings  print "Unknown option --settings" to stderr, exit 1
# The stub logs every received frame plus its own argv into $STUB_LOG.
STUB="$TMP_ROOT/stub-app-server.py"
STUB_LOG="$TMP_ROOT/stub-received.log"
cat > "$STUB" <<PYEOF
#!/usr/bin/env python3
import json, os, sys
log_path = os.environ["STUB_LOG"]
stub_mode = os.environ.get("STUB_MODE", "ok")
stub_model = os.environ.get("STUB_MODEL", "")  # "provider/model" echoed in read

def log(event, payload):
    with open(log_path, "a") as fh:
        fh.write(json.dumps({"event": event, "payload": payload}, ensure_ascii=False) + "\n")

def emit(frame):
    sys.stdout.write(json.dumps(frame) + "\n")
    sys.stdout.flush()

log("argv", sys.argv)

if stub_mode == "reject_settings":
    sys.stderr.write("error: Unknown option --settings\n")
    sys.exit(1)

# Push a server->client request right away; driver must answer in-window.
emit({"id": "server-test", "method": "session/requestRuntimePreferences",
      "params": {"scope": "runtime-materialization"}})
emit({"method": "state.updated",
      "params": {"patch": {"status": "idle"}, "reason": "session_ready"}})

current_model = stub_model or "x/glm"
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    frame = json.loads(line)
    log("received", frame)
    method = frame.get("method")
    if method == "session/create":
        emit({"id": frame["id"], "result": {"session": {"sessionId": "sess_stub_001"}}})
    elif method == "session/setModel":
        if stub_mode != "mismatch":
            model = frame.get("params", {}).get("model", {})
            current_model = f"{model.get('providerId')}/{model.get('modelId')}"
        emit({"id": frame["id"], "result": {}})
    elif method == "session/read":
        provider, _, model_id = ("evil/other" if stub_mode == "mismatch" else current_model).partition("/")
        emit({"id": frame["id"], "result": {"session": {
            "sessionId": "sess_stub_001", "status": "idle",
            "model": {"providerId": provider, "modelId": model_id}}}})
    elif method == "session/send":
        emit({"id": frame["id"], "result": {"accepted": True}})
        emit({"method": "state.updated",
              "params": {"patch": {"status": "running"}, "reason": "prompt_started"}})
    elif method == "session/close":
        emit({"id": frame["id"], "result": {}})
        break
PYEOF
chmod +x "$STUB"

# ---- private settings files (0600, synthetic) ---------------------------------
mk_settings() { # $1=file $2=model
  printf '{"model": "%s", "provider": {"x": {}}}' "$2" > "$1"
  chmod 600 "$1"
}
mk_settings "$TMP_ROOT/good-config.json" "x/glm"
mk_settings "$TMP_ROOT/flash-config.json" "builtin:bigmodel-coding-plan/GLM-5.3-Flash"

# ---- helper: run driver against the stub -------------------------------------
run_driver() { # $1=stdin input, rest = driver args
  local input="$1"; shift
  printf '%s\n' "$input" | \
    STUB_LOG="$STUB_LOG" \
    python3 "$DRIVER" --bin "$STUB" --cwd "$TMP_ROOT" "$@" 2>&1
}

# ---- Case 1: config entry is mandatory and fail-closed ------------------------
out=$(printf '/quit\n' | python3 "$DRIVER" --bin "$STUB" --cwd "$TMP_ROOT" 2>&1) && rc=0 || rc=$?
if [ "$rc" -eq 64 ]; then ok "missing --settings exits 64 (no shared-config fallback)"; else bad "missing --settings rc=$rc: $out"; fi

out=$(printf '/quit\n' | python3 "$DRIVER" --bin "$STUB" --cwd "$TMP_ROOT" --settings "$TMP_ROOT/nope.json" 2>&1) && rc=0 || rc=$?
if [ "$rc" -eq 64 ]; then ok "missing settings file exits 64"; else bad "missing file rc=$rc: $out"; fi

printf '{"model": "x/glm", "provider": {"x": {}}}' > "$TMP_ROOT/loose-config.json"
chmod 644 "$TMP_ROOT/loose-config.json"
out=$(printf '/quit\n' | python3 "$DRIVER" --bin "$STUB" --cwd "$TMP_ROOT" --settings "$TMP_ROOT/loose-config.json" 2>&1) && rc=0 || rc=$?
if [ "$rc" -eq 64 ]; then ok "group/world-readable settings exits 64"; else bad "loose perms rc=$rc: $out"; fi

printf '{"skills": {}}' > "$TMP_ROOT/bad-config.json"; chmod 600 "$TMP_ROOT/bad-config.json"
out=$(printf '/quit\n' | python3 "$DRIVER" --bin "$STUB" --cwd "$TMP_ROOT" --settings "$TMP_ROOT/bad-config.json" 2>&1) && rc=0 || rc=$?
if [ "$rc" -eq 64 ]; then ok "settings without model/provider exits 64"; else bad "bad settings rc=$rc: $out"; fi

out=$(printf '/quit\n' | python3 "$DRIVER" --bin "$STUB" --cwd "$TMP_ROOT" --settings "$TMP_ROOT/good-config.json" --mode bogus 2>&1) && rc=0 || rc=$?
if [ "$rc" -eq 2 ] || [ "$rc" -eq 64 ]; then ok "invalid --mode rejected (rc=$rc)"; else bad "invalid --mode rc=$rc: $out"; fi

# ---- Case 2: full flow — ready barrier, prefs, send, render --------------------
: > "$STUB_LOG"
out=$(run_driver '创建 hello.txt
/quit' --settings "$TMP_ROOT/good-config.json") && rc=0 || rc=$?

if [ "$rc" -eq 0 ]; then ok "driver exits 0 after /quit"; else bad "driver rc=$rc: $out"; fi

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

# Settings isolation entry: the child argv must carry --settings <private file>
if grep -q "\"--settings\", \".*good-config.json\"" "$STUB_LOG" && \
   ! grep -q '"mode": "yolo"' "$STUB_LOG"; then
  ok "child argv carries --settings; create mode is build (default)"
else
  bad "argv/mode wrong; log head: $(grep '"argv"' "$STUB_LOG" | head -1)"
fi

# Without --model: NO setModel write, but read-back verification required.
if grep -q '"method": "session/setModel"' "$STUB_LOG"; then
  bad "setModel dispatched without --model (must verify, not write)"
else
  ok "no setModel without --model"
fi
if grep -q '"method": "session/read"' "$STUB_LOG" && \
   printf '%s\n' "$out" | grep -q 'READY model=x/glm verified'; then
  ok "read-back verify gates READY even without --model"
else
  bad "read verify missing; output: $out; log: $(cat "$STUB_LOG")"
fi

# Queued early text only drains AFTER ready: send must follow read.
if grep -q '"content": "创建 hello.txt"' "$STUB_LOG"; then
  ok "plain stdin text forwarded as session/send content"
else
  bad "session/send content missing; log: $(cat "$STUB_LOG")"
fi

if printf '%s\n' "$out" | grep -q 'session created: sess_stub_001'; then
  ok "sessionId captured from create response"
else
  bad "sessionId not captured; output: $out"
fi

if printf '%s\n' "$out" | grep -q '\[session\] running (prompt_started)'; then
  ok "state.updated rendered as readable line"
else
  bad "rendered state line missing; output: $out"
fi

# Source settings file must not be modified by the run.
sha_after=$(shasum "$TMP_ROOT/good-config.json" | cut -d' ' -f1)
if [ "$sha_after" = "$(printf '{"model": "x/glm", "provider": {"x": {}}}' | shasum | cut -d' ' -f1)" ]; then
  ok "settings file unchanged after run"
else
  bad "settings file was modified"
fi

# ---- Case 3: --model providerId/modelId — setModel then verify -----------------
: > "$STUB_LOG"
out=$(run_driver $'ping\n/quit' --settings "$TMP_ROOT/good-config.json" \
  --model 'builtin:bigmodel-coding-plan/GLM-5.3-Flash') && rc=0 || rc=$?

if [ "$rc" -eq 0 ]; then ok "driver exits 0 with --model"; else bad "driver rc=$rc: $out"; fi

if grep -q '"method": "session/setModel", "params": {"sessionId": "sess_stub_001", "model": {"providerId": "builtin:bigmodel-coding-plan", "modelId": "GLM-5.3-Flash"}, "persistAsWorkspaceLastUsed": false}' "$STUB_LOG"; then
  ok "setModel dispatched with exact modelRef + persist opt-out"
else
  bad "setModel params wrong; log: $(cat "$STUB_LOG")"
fi

# setModel result must be followed by session/read verification before READY.
if printf '%s\n' "$out" | grep -q 'READY model=builtin:bigmodel-coding-plan/GLM-5.3-Flash verified'; then
  ok "read-back verify confirms requested model before READY"
else
  bad "verified READY line missing; output: $out"
fi

if ! grep -q '"content": "ping"' "$STUB_LOG" || \
   [ "$(grep -n '"method": "session/read"' "$STUB_LOG" | head -1 | cut -d: -f1)" -lt "$(grep -n '"content": "ping"' "$STUB_LOG" | head -1 | cut -d: -f1)" ]; then
  ok "queued ping drained only after the read verify"
else
  bad "ping sent before verify; log: $(cat "$STUB_LOG")"
fi

# ---- Case 4: bare --model — providerId falls back to settings prefix -----------
: > "$STUB_LOG"
out=$(run_driver $'ping\n/quit' --settings "$TMP_ROOT/good-config.json" --model 'GLM-5.3-Flash') && rc=0 || rc=$?
if grep -q '"model": {"providerId": "x", "modelId": "GLM-5.3-Flash"}, "persistAsWorkspaceLastUsed": false' "$STUB_LOG"; then
  ok "bare --model falls back to settings provider prefix"
else
  bad "provider fallback wrong; log: $(cat "$STUB_LOG")"
fi

# ---- Case 5: read-back mismatch — startup fails, zero task sends ---------------
: > "$STUB_LOG"
out=$(printf 'ping\n/quit\n' | STUB_LOG="$STUB_LOG" STUB_MODE=mismatch STUB_MODEL="x/glm" \
  python3 "$DRIVER" --bin "$STUB" --cwd "$TMP_ROOT" --settings "$TMP_ROOT/good-config.json" --bootstrap-timeout 10 2>&1) && rc=0 || rc=$?
if [ "$rc" -eq 65 ]; then ok "model mismatch exits 65"; else bad "mismatch rc=$rc: $out"; fi
if grep -q '"method": "session/send"' "$STUB_LOG"; then
  bad "task text sent despite model mismatch"
else
  ok "zero session/send after model mismatch"
fi
if printf '%s\n' "$out" | grep -q 'STARTUP NOT VERIFIED'; then
  ok "startup failure reason rendered"
else
  bad "failure reason missing; output: $out"
fi

# ---- Case 6: explicit --mode yolo reaches create params -----------------------
: > "$STUB_LOG"
out=$(run_driver '/quit' --settings "$TMP_ROOT/good-config.json" --mode yolo) && rc=0 || rc=$?
if grep -q '"mode": "yolo"' "$STUB_LOG"; then
  ok "explicit --mode yolo forwarded to session/create"
else
  bad "yolo mode missing; log: $(cat "$STUB_LOG")"
fi

# ---- Case 7: official 0.16.5 --settings rejection → 68, zero sends -------------
: > "$STUB_LOG"
out=$(printf 'ping\n/quit\n' | STUB_LOG="$STUB_LOG" STUB_MODE=reject_settings \
  python3 "$DRIVER" --bin "$STUB" --cwd "$TMP_ROOT" --settings "$TMP_ROOT/good-config.json" 2>&1) && rc=0 || rc=$?
if [ "$rc" -eq 68 ]; then ok "settings rejection exits 68 (UNSUPPORTED_CONFIG_ISOLATION)"; else bad "reject rc=$rc: $out"; fi
if printf '%s\n' "$out" | grep -q 'UNSUPPORTED_CONFIG_ISOLATION'; then
  ok "UNSUPPORTED_CONFIG_ISOLATION marker rendered"
else
  bad "marker missing; output: $out"
fi
if grep -q '"method": "session/send"' "$STUB_LOG" || grep -q '"method": "session/create"' "$STUB_LOG"; then
  bad "protocol requests sent to a child that never spoke the protocol"
else
  ok "zero protocol traffic on settings rejection"
fi

# ---- summary ------------------------------------------------------------------
printf 'SUMMARY: pass=%d fail=%d\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
