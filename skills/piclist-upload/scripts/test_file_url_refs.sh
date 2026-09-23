#!/usr/bin/env bash
# Regression test for file:// / <angle-bracket> image reference support.
# Reproduces the 2026-09-23 Obsidian case: ![alt](<file:///abs/path.jpg>)
# Old behavior: "File not found" for every file:// image (fail_count only,
# no upload). New behavior: recognized, uploaded, replaced with cloud URL.
#
# Usage: bash test_file_url_refs.sh
# Uses a mock PicList server (port 36699) so no real upload happens.

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROCESS_SH="$SCRIPT_DIR/process.sh"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/piclist_fileurl_test.XXXXXX")"
MOCK_PORT=36699

cleanup() {
    [ -n "${MOCK_PID:-}" ] && kill "$MOCK_PID" 2>/dev/null
    rm -rf "$WORK"
}
trap cleanup EXIT

fail=0
ok()   { echo "  ✅ PASS: $1"; }
bad()  { echo "  ❌ FAIL: $1"; fail=$((fail + 1)); }

# ---------- mock PicList server ----------
MOCK_PID=""
start_mock() {
    /usr/bin/python3 - "$MOCK_PORT" <<'PYEOF' &
import http.server, json, sys, threading

port = int(sys.argv[1])
counter = {"n": 0}
lock = threading.Lock()

class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if not self.path.startswith("/upload"):
            self.send_response(404); self.end_headers(); return
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        with lock:
            counter["n"] += 1
            n = counter["n"]
        body = json.dumps({"success": True, "result": [f"https://mock.example.com/u{n}.png"]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        # connectivity probe endpoint
        self.send_response(200); self.end_headers()
    def log_message(self, *a):
        pass

http.server.HTTPServer(("127.0.0.1", port), H).serve_forever()
PYEOF
    MOCK_PID=$!
}

start_mock
# wait for port
i=0
while [ $i -lt 20 ]; do
    if nc -z 127.0.0.1 $MOCK_PORT 2>/dev/null; then break; fi
    if curl -s --noproxy '*' -o /dev/null "http://127.0.0.1:$MOCK_PORT/upload" 2>/dev/null; then break; fi
    sleep 0.5; i=$((i + 1))
done

# ---------- fixtures ----------
IMG="$WORK/pic with space (1).png"
printf 'fake-png-bytes' > "$IMG"
MD="$WORK/obsidian_note.md"
cat > "$MD" <<EOF
# 标题

![活动主视觉](<file://$IMG>)

正文。

![讲台授课](<file://$IMG>)

![已是云端](https://mock.example.com/existing.png)
EOF

# ---------- run process.sh against mock ----------
OUT="$WORK/run.out"
PICLIST_SERVER="http://127.0.0.1:$MOCK_PORT" \
UPLOAD_INTERVAL=0 \
    bash "$PROCESS_SH" --in-place --keep-local "$MD" > "$OUT" 2>&1

echo "--- process.sh output ---"
cat "$OUT"
echo "-------------------------"

# ---------- assertions ----------
CONTENT="$(cat "$MD")"

# 1. exactly 1 upload: second ref to same path is dedup-reused, pre-existing
#    cloud URL skipped -> Uploaded: 1, Skipped: 2, Failed: 0
if grep -q "Uploaded: 1, ⏭️  Skipped: 2, ❌ Failed: 0" "$OUT"; then
    ok "summary Uploaded=1 / Skipped=2 / Failed=0 (dedup reuse works)"
else
    bad "unexpected summary: $(grep -E 'Uploaded:' "$OUT")"
fi

# 2. no File-not-found for the file:// path
if grep -q "File not found" "$OUT"; then
    bad "file:// path reported as File not found (regression)"
else
    ok "no 'File not found' for file:// reference"
fi

# 3. both refs replaced with mock URL
if printf '%s' "$CONTENT" | grep -qF '![活动主视觉](https://mock.example.com/u1.png)'; then
    ok "first file:// ref replaced with cloud URL"
else
    bad "first file:// ref not replaced; md now: $(grep '^![' "$MD")"
fi
if printf '%s' "$CONTENT" | grep -qF '![讲台授课](https://mock.example.com/u1.png)'; then
    ok "second (duplicate) file:// ref reused same URL"
else
    bad "duplicate file:// ref not replaced"
fi

# 4. no residual file:// in md
if printf '%s' "$CONTENT" | grep -q 'file://'; then
    bad "residual file:// reference left in md"
else
    ok "no residual file:// in md"
fi

# 5. local image kept (--keep-local)
if [ -f "$IMG" ]; then
    ok "local image kept (--keep-local)"
else
    bad "local image deleted despite --keep-local"
fi

# 6. existing cloud URL untouched
if printf '%s' "$CONTENT" | grep -qF '![已是云端](https://mock.example.com/existing.png)'; then
    ok "pre-existing cloud URL untouched"
else
    bad "pre-existing cloud URL was modified"
fi

# 7. dry-run also recognizes file:// refs
MD2="$WORK/dry_note.md"
cat > "$MD2" <<EOF
![x](<file://$IMG>)
EOF
OUT2="$WORK/dry.out"
PICLIST_SERVER="http://127.0.0.1:$MOCK_PORT" \
    bash "$PROCESS_SH" --dry-run "$MD2" > "$OUT2" 2>&1
if grep -q "Would upload" "$OUT2"; then
    ok "--dry-run lists file:// ref as upload candidate"
else
    bad "--dry-run did not recognize file:// ref: $(cat "$OUT2")"
fi
if grep -q "File not found" "$OUT2"; then
    bad "--dry-run reports File not found for file:// ref"
else
    ok "--dry-run no File-not-found"
fi

# 8. file://<host>/ volume form (e.g. file://localhost/path) still resolves to
#    local path — worth guarding since we now strip the scheme
IMG2="$WORK/another pic.png"
printf 'fake' > "$IMG2"
MD3="$WORK/vol_note.md"
cat > "$MD3" <<EOF
![vol](<file://localhost$IMG2>)
EOF
OUT3="$WORK/vol.out"
PICLIST_SERVER="http://127.0.0.1:$MOCK_PORT" \
UPLOAD_INTERVAL=0 \
    bash "$PROCESS_SH" --in-place --keep-local "$MD3" > "$OUT3" 2>&1
if grep -q "Uploaded: 1" "$OUT3" && printf '%s' "$(cat "$MD3")" | grep -qF '![vol](https://mock.example.com/u2.png)'; then
    ok "file://localhost/... form resolves and uploads"
else
    bad "file://localhost form failed: $(cat "$OUT3"); md: $(cat "$MD3")"
fi

echo
if [ $fail -eq 0 ]; then
    echo "ALL PASS"
    exit 0
else
    echo "FAILED: $fail assertion(s)"
    exit 1
fi
