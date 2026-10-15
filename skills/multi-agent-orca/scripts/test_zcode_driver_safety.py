#!/usr/bin/env python3
"""Fault-injection safety tests for zcode-worker-driver.py.

Every case launches the REAL driver process against a REAL stub app-server
child (no internal-method mocking, no ZCode desktop app, no credentials, no
network). The stub proves the DRIVER contract only — official 0.16.5 config
loading is out of scope (it rejects --settings; see the exit-68 case).

Covers the TASK-2026-09-13-ZCODE-DRIVER-SAFETY acceptance matrix:
  * startup readiness barrier: setModel delayed / error / read-back mismatch /
    no read-back / no create -> exit 65, ZERO session/send of task text
  * early PM text + control commands during bootstrap: queued text drains in
    order only after READY; /status /stop /compact /quit are never forwarded
    to the model as session content
  * explicit private --settings entry: child argv carries it; source files
    stay byte-identical; two concurrent instances never cross-contaminate
  * child crashing / rejecting --settings: exit 66 / 68 + marker line
  * clean /quit (0), close-not-acked (70), EOF teardown (0), SIGINT (130)
  * sensitive-output hygiene: unknown notifications render key names only;
    token/header/credential material is REDACTED (never merely truncated);
    runtime-headers requests fail closed via headersApplied:false; permission
    requests get an identifiable error reply, never a guessed success
"""

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.join(HERE, "zcode-worker-driver.py")

STUB_SOURCE = r'''#!/usr/bin/env python3
"""Configurable stub app-server. Behavior via STUB_MODE:

  ok                 full happy path; read echoes setModel'd / STUB_MODEL model
  slow_create        answer session/create only after STUB_DELAY seconds
  setmodel_error     answer create ok, setModel with a protocol error
  read_error         answer create ok, read with a protocol error
  no_create          never answer create
  no_read            answer create (+setModel), never answer read
  delayed_setmodel   answer setModel only after STUB_DELAY seconds
  mismatch           read answers the model "evil/other"
  crash_after_ready  ok bootstrap, then exit(1) on first session/send
  close_noack        ok bootstrap, never ack session/close
  reject_settings    "Unknown option --settings" on stderr, exit 1
  sensitive          ok path + hostile frames with credential material
  permission         ok path + interaction/requestPermission reverse request
  malicious_settings rewrite the --settings file from our own argv, then ok

Everything received (frames + argv) is appended to STUB_LOG as JSON lines.
"""
import json, os, sys, time

log_path = os.environ["STUB_LOG"]
mode = os.environ.get("STUB_MODE", "ok")
delay = float(os.environ.get("STUB_DELAY", "1.5"))
stub_model = os.environ.get("STUB_MODEL", "")

def log(event, payload):
    with open(log_path, "a") as fh:
        fh.write(json.dumps({"event": event, "payload": payload}, ensure_ascii=False) + "\n")

def emit(frame):
    sys.stdout.write(json.dumps(frame) + "\n")
    sys.stdout.flush()

log("argv", sys.argv)
if mode == "reject_settings":
    sys.stderr.write("error: Unknown option --settings\n")
    sys.exit(1)
if mode == "malicious_settings":
    # Hostile child: rewrite the settings file we were handed via --settings.
    # The driver must not care (it already froze its model ref) and must
    # never echo the file contents; the GLOBAL config is never in play.
    try:
        idx = sys.argv.index("--settings")
        with open(sys.argv[idx + 1], "w") as fh:
            fh.write('{"pwned": true}')
    except (ValueError, OSError, IndexError):
        pass

if mode == "sensitive":
    emit({"method": "weird/notification", "params": {
        "api_key": "sk-stubsecret1234567890",
        "headers": {"set-cookie": ["acw_tc=STUBCOOKIEVALUE", "cdn_sec_tc=X"]}}})
    emit({"id": "rh-1", "method": "interaction/requestProviderRuntimeHeaders",
          "params": {"requestId": "rh-1", "sessionId": "sess_stub_001",
                     "providerId": "builtin:bigmodel-start-plan",
                     "reason": "captcha-retry",
                     "headers": {"x-aliyun-captcha-ticket": "STUBTICKET123456"}}})
    sys.stderr.write("ERROR login refresh failed token=abc123def456ghi789\n")
if mode == "permission":
    emit({"id": "perm-1", "method": "interaction/requestPermission", "params": {
        "tool": "Bash", "command": "rm -rf /", "token": "sk-permsecret123456789"}})

emit({"id": "server-test", "method": "session/requestRuntimePreferences",
      "params": {"scope": "runtime-materialization"}})

current_model = stub_model or "x/glm"
if mode == "slow_create":
    time.sleep(delay)

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    frame = json.loads(line)
    log("received", frame)
    method = frame.get("method")
    if method == "session/create":
        if mode == "no_create":
            continue
        emit({"id": frame["id"], "result": {"session": {"sessionId": "sess_stub_001"}}})
    elif method == "session/setModel":
        if mode == "setmodel_error":
            emit({"id": frame["id"], "error": {"code": -32004, "message": "unknown model"}})
            continue
        if mode == "delayed_setmodel":
            time.sleep(delay)
        if mode != "mismatch":
            model = frame.get("params", {}).get("model", {})
            current_model = f"{model.get('providerId')}/{model.get('modelId')}"
        emit({"id": frame["id"], "result": {}})
    elif method == "session/read":
        if mode == "read_error":
            emit({"id": frame["id"], "error": {"code": -32004, "message": "Session is not active"}})
            continue
        if mode == "no_read":
            continue
        provider, _, model_id = ("evil/other" if mode == "mismatch" else current_model).partition("/")
        emit({"id": frame["id"], "result": {"session": {
            "sessionId": "sess_stub_001", "status": "idle",
            "model": {"providerId": provider, "modelId": model_id}}}})
    elif method == "session/send":
        if mode == "crash_after_ready":
            emit({"id": frame["id"], "result": {"accepted": True}})
            sys.stdout.flush()
            os._exit(1)
        emit({"id": frame["id"], "result": {"accepted": True}})
    elif method == "session/stop":
        emit({"id": frame["id"], "result": {}})
    elif method == "session/compact":
        emit({"id": frame["id"], "result": {}})
    elif method == "session/close":
        if mode != "close_noack":
            emit({"id": frame["id"], "result": {}})
            break
    elif "id" in frame and method is not None:
        # Server-request replies FROM the driver (prefs answer, declines).
        pass
'''

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS: {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name}: {detail}")
        print(f"FAIL: {name} :: {detail}")


def sha256(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class Lab:
    """One temp workspace: stub binary + private settings + stub log."""

    def __init__(self, root: str, model: str = "x/glm", name: str = "w") -> None:
        self.root = root
        self.name = name
        self.settings = os.path.join(root, f"settings-{name}.json")
        with open(self.settings, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"model": model, "provider": {model.split("/")[0]: {}}}))
        os.chmod(self.settings, 0o600)
        self.stub = os.path.join(root, f"stub-{name}.py")
        with open(self.stub, "w", encoding="utf-8") as fh:
            fh.write(STUB_SOURCE)
        os.chmod(self.stub, 0o755)
        self.log = os.path.join(root, f"stub-{name}.log")
        open(self.log, "w").close()

    def frames(self, event: str | None = None) -> list[dict]:
        out = []
        with open(self.log, "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event is None or rec.get("event") == event:
                    out.append(rec.get("payload"))
        return out

    def sent_contents(self) -> list[str]:
        return [
            f.get("params", {}).get("content")
            for f in self.frames("received")
            if f.get("method") == "session/send"
        ]


class Run:
    """A live driver process against a Lab stub."""

    def __init__(self, lab: Lab, mode: str, args: list[str], env_extra: dict | None = None,
                 stdin_lines: list[str] | None = None, keep_stdin: bool = False) -> None:
        env = dict(os.environ)
        env["STUB_LOG"] = lab.log
        env["STUB_MODE"] = mode
        if env_extra:
            env.update(env_extra)
        self.proc = subprocess.Popen(
            [sys.executable, DRIVER, "--bin", lab.stub, "--cwd", lab.root,
             "--settings", lab.settings] + args,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=env,
        )
        self.out_lines: list[str] = []
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()
        if stdin_lines:
            for line in stdin_lines:
                self.proc.stdin.write(line + "\n")
            self.proc.stdin.flush()
        if not keep_stdin:
            self.proc.stdin.close()
            self.stdin_closed = True
        else:
            self.stdin_closed = False

    def _pump(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self.out_lines.append(line.rstrip("\n"))

    @property
    def output(self) -> str:
        return "\n".join(self.out_lines)

    def wait(self, timeout: float = 25.0) -> int | None:
        try:
            code = self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None
        self._reader.join(timeout=2.0)
        if not self.stdin_closed:
            try:
                self.proc.stdin.close()
            except OSError:
                pass
        return code

    def sigint(self) -> None:
        self.proc.send_signal(signal.SIGINT)

    def kill(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
            try:
                self.proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                pass
        self._reader.join(timeout=2.0)


def drive(lab: Lab, mode: str, args: list[str], stdin_lines: list[str],
          env_extra: dict | None = None, timeout: float = 25.0, keep_stdin: bool = False):
    """Run a driver to completion; returns (exit_code|None, output)."""
    run = Run(lab, mode, args, env_extra=env_extra, stdin_lines=stdin_lines,
              keep_stdin=keep_stdin)
    code = run.wait(timeout=timeout)
    if code is None:
        run.kill()
    return code, run.output


def main() -> int:
    root = tempfile.mkdtemp(prefix="zcode-driver-safety-")
    try:
        return run_suite(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def run_suite(root: str) -> int:
    fast = ["--bootstrap-timeout", "2", "--close-timeout", "1"]
    roomy = ["--bootstrap-timeout", "10", "--close-timeout", "1"]

    # ---- G1: setModel delayed past the deadline -> 65, zero sends -----------
    lab = Lab(root, name="g1")
    before = sha256(lab.settings)
    code, out = drive(lab, "delayed_setmodel", fast + ["--model", "x/glm"], ["do the task"],
                      env_extra={"STUB_DELAY": "4"}, keep_stdin=True)
    check("g1 delayed setModel exits 65", code == 65, f"code={code} out={out[-400:]}")
    check("g1 zero session/send", lab.sent_contents() == [], f"sent={lab.sent_contents()}")
    check("g1 dropped backlog reported", "dropped 1 queued input" in out, out[-300:])
    check("g1 source settings unchanged", sha256(lab.settings) == before)

    # ---- G2: setModel protocol error -> 65, zero sends -----------------------
    lab = Lab(root, name="g2")
    code, out = drive(lab, "setmodel_error", roomy + ["--model", "x/glm"], ["do the task"], keep_stdin=True)
    check("g2 setModel error exits 65", code == 65, f"code={code} out={out[-400:]}")
    check("g2 zero session/send", lab.sent_contents() == [], f"sent={lab.sent_contents()}")
    check("g2 no READY line", "READY" not in out, out[-300:])

    # ---- G3: read-back model mismatch -> 65, zero sends ----------------------
    lab = Lab(root, name="g3")
    code, out = drive(lab, "mismatch", roomy, ["do the task"], keep_stdin=True)
    check("g3 mismatch exits 65", code == 65, f"code={code} out={out[-400:]}")
    check("g3 zero session/send", lab.sent_contents() == [], f"sent={lab.sent_contents()}")
    check("g3 mismatch reason named", "model mismatch" in out, out[-300:])

    # ---- G4: read never answered -> 65 within the bounded deadline -----------
    lab = Lab(root, name="g4")
    started = time.monotonic()
    code, out = drive(lab, "no_read", fast, ["do the task"], keep_stdin=True)
    elapsed = time.monotonic() - started
    check("g4 no read-back exits 65", code == 65, f"code={code} out={out[-400:]}")
    check("g4 bounded in <6s", elapsed < 6.0, f"elapsed={elapsed:.1f}s")
    check("g4 zero session/send", lab.sent_contents() == [])

    # ---- G5: create never answered -> 65 -------------------------------------
    lab = Lab(root, name="g5")
    code, out = drive(lab, "no_create", fast, ["do the task"], keep_stdin=True)
    check("g5 no create exits 65", code == 65, f"code={code} out={out[-400:]}")
    check("g5 zero session/send", lab.sent_contents() == [])

    # ---- G6: early text + control commands during bootstrap ------------------
    lab = Lab(root, name="g6")
    code, out = drive(lab, "slow_create", roomy,
                      ["first task", "/status", "/stop", "/compact", "second task", "/quit"],
                      env_extra={"STUB_DELAY": "1.2"})
    check("g6 deferred /quit still exits 0", code == 0, f"code={code} out={out[-400:]}")
    check("g6 queued text drained in order",
          lab.sent_contents() == ["first task", "second task"],
          f"sent={lab.sent_contents()}")
    check("g6 control commands never sent to model",
          not any(c in lab.sent_contents() for c in ("/status", "/stop", "/compact", "/quit")),
          f"sent={lab.sent_contents()}")
    check("g6 /status before ready is local-only",
          '"state": "starting"' in out and "/status dropped" not in out, out)
    check("g6 /stop dropped while starting", "/stop dropped: session not ready" in out, out)
    check("g6 READY barrier line", re.search(r"READY model=x/glm verified mode=build drained=2", out) is not None, out)
    create_frames = [f for f in lab.frames("received") if f.get("method") == "session/create"]
    check("g6 default mode is build", create_frames and create_frames[0]["params"].get("mode") == "build",
          f"create={create_frames}")

    # ---- G7: explicit --mode yolo reaches create params ----------------------
    lab = Lab(root, name="g7")
    code, out = drive(lab, "ok", roomy + ["--mode", "yolo"], ["/quit"])
    create_frames = [f for f in lab.frames("received") if f.get("method") == "session/create"]
    check("g7 yolo forwarded",
          code == 0 and bool(create_frames) and create_frames[0]["params"].get("mode") == "yolo",
          f"code={code} create={create_frames}")

    # ---- G8: child argv carries the private --settings path ------------------
    lab = Lab(root, name="g8")
    code, out = drive(lab, "ok", roomy, ["/quit"])
    argvs = lab.frames("argv")
    ok_settings = bool(argvs) and any(
        argvs[0][i] == "--settings" and argvs[0][i + 1] == lab.settings
        for i in range(len(argvs[0]) - 1)
    )
    check("g8 argv includes --settings <private file>", ok_settings, f"argv={argvs}")
    check("g8 no global config path anywhere in argv",
          bool(argvs) and not any(".zcode/cli/config.json" in str(a) for a in argvs[0]), f"argv={argvs}")

    # ---- G9: two concurrent instances, isolated settings ---------------------
    labA = Lab(root, model="alpha/glm-a", name="g9a")
    labB = Lab(root, model="beta/glm-b", name="g9b")
    shaA, shaB = sha256(labA.settings), sha256(labB.settings)
    runA = Run(labA, "ok", roomy + ["--model", "alpha/glm-a"],
               stdin_lines=["task A", "/quit"], keep_stdin=True)
    runB = Run(labB, "ok", roomy + ["--model", "beta/glm-b"],
               stdin_lines=["task B", "/quit"], keep_stdin=True)
    codeA, codeB = runA.wait(), runB.wait()
    outA, outB = runA.output, runB.output
    check("g9 both instances exit 0", codeA == 0 and codeB == 0, f"{codeA}/{codeB}")
    check("g9 A verified its own model", "READY model=alpha/glm-a verified" in outA, outA[-300:])
    check("g9 B verified its own model", "READY model=beta/glm-b verified" in outB, outB[-300:])
    check("g9 A only sent A's task", labA.sent_contents() == ["task A"], f"{labA.sent_contents()}")
    check("g9 B only sent B's task", labB.sent_contents() == ["task B"], f"{labB.sent_contents()}")
    check("g9 settings sources unchanged",
          sha256(labA.settings) == shaA and sha256(labB.settings) == shaB)

    # ---- G10: malicious child rewrites ITS OWN settings file -----------------
    lab = Lab(root, name="g10")
    code, out = drive(lab, "malicious_settings", roomy, ["ping", "/quit"])
    with open(lab.settings, "r", encoding="utf-8") as fh:
        after = fh.read()
    check("g10 child rewrote the private settings (writes redirected there)",
          code == 0 and "pwned" in after, f"code={code} content={after!r}")
    check("g10 driver never echoes settings contents", '"provider"' not in out, out)

    # ---- G11: official-style --settings rejection -> 68 ----------------------
    lab = Lab(root, name="g11")
    code, out = drive(lab, "reject_settings", roomy, ["ping"], keep_stdin=True)
    check("g11 rejection exits 68", code == 68, f"code={code} out={out[-400:]}")
    check("g11 UNSUPPORTED_CONFIG_ISOLATION marker", "UNSUPPORTED_CONFIG_ISOLATION" in out, out[-300:])
    check("g11 zero protocol traffic", lab.frames("received") == [], f"{lab.frames('received')}")

    # ---- G12: child crash after ready -> 66 ----------------------------------
    lab = Lab(root, name="g12")
    code, out = drive(lab, "crash_after_ready", roomy, ["task"], keep_stdin=True)
    check("g12 crash exits 66", code == 66, f"code={code} out={out[-400:]}")

    # ---- G13: clean /quit -> 0 with close acked ------------------------------
    lab = Lab(root, name="g13")
    code, out = drive(lab, "ok", roomy, ["hello", "/quit"], keep_stdin=True)
    closes = [f for f in lab.frames("received") if f.get("method") == "session/close"]
    check("g13 clean quit exits 0", code == 0, f"code={code} out={out[-400:]}")
    check("g13 close dispatched once", len(closes) == 1, f"closes={closes}")

    # ---- G14: close never acked -> 70 ----------------------------------------
    lab = Lab(root, name="g14")
    started = time.monotonic()
    code, out = drive(lab, "close_noack", roomy, ["/quit"], keep_stdin=True, timeout=20)
    elapsed = time.monotonic() - started
    check("g14 unacked close exits 70", code == 70, f"code={code} out={out[-400:]}")
    check("g14 bounded settlement <15s", elapsed < 15.0, f"elapsed={elapsed:.1f}s")

    # ---- G15: EOF teardown -> 0 ----------------------------------------------
    lab = Lab(root, name="g15")
    run = Run(lab, "ok", roomy, stdin_lines=None, keep_stdin=True)
    time.sleep(0.3)  # let the spawn happen
    run.proc.stdin.close()
    code = run.wait(timeout=15)
    check("g15 EOF teardown exits 0", code == 0, f"code={code} out={run.output[-300:]}")

    # ---- G16: SIGINT -> 130, bounded, child settled --------------------------
    lab = Lab(root, name="g16")
    run = Run(lab, "ok", roomy, stdin_lines=None, keep_stdin=True)
    time.sleep(1.5)  # reach READY
    run.sigint()
    code = run.wait(timeout=10)
    check("g16 SIGINT exits 130", code == 130, f"code={code} out={run.output[-300:]}")
    check("g16 bounded SIGINT settlement <8s", code is not None, "timed out")
    time.sleep(1.0)  # let the orphaned stub notice its stdin closed and exit
    stub_alive = subprocess.run(["pgrep", "-f", f"stub-{lab.name}.py"], capture_output=True)
    check("g16 stub child gone", stub_alive.returncode != 0, f"pgrep out={stub_alive.stdout!r}")

    # ---- G17: sensitive material redaction, never truncated-only -------------
    lab = Lab(root, name="g17")
    code, out = drive(lab, "sensitive", roomy, ["hello", "/quit"])
    secrets = ["sk-stubsecret1234567890", "STUBCOOKIEVALUE", "STUBTICKET123456",
               "abc123def456ghi789", "acw_tc"]
    check("g17 no raw secret in output", not any(s in out for s in secrets),
          "\n".join(l for l in out.splitlines() if any(s in l for s in secrets)))
    check("g17 redaction markers present", "[REDACTED" in out, out)
    check("g17 unknown notification shows key names only",
          "weird/notification" in out and "api_key" in out and "headers" in out, out)
    rh_replies = [f for f in lab.frames("received")
                  if isinstance(f, dict) and f.get("id") == "rh-1"]
    check("g17 runtime-headers fail-closed reply",
          rh_replies and rh_replies[0].get("result", {}).get("headersApplied") is False,
          f"replies={rh_replies}")
    check("g17 NEEDS-AUTHORIZATION surfaced", "NEEDS-AUTHORIZATION" in out, out)
    check("g17 exits 0 despite hostile frames", code == 0, f"code={code}")

    # ---- G18: permission reverse request declined, no hang -------------------
    lab = Lab(root, name="g18")
    code, out = drive(lab, "permission", roomy, ["hello", "/quit"], timeout=20)
    check("g18 completes (no hang), exits 0", code == 0, f"code={code} out={out[-300:]}")
    check("g18 permission secret redacted", "sk-permsecret123456789" not in out, out)
    declines = [f for f in lab.frames("received")
                if isinstance(f, dict) and f.get("id") == "perm-1"]
    check("g18 identifiable error reply sent",
          declines and declines[0].get("error", {}).get("code") == -32601
          and "does not support" in declines[0].get("error", {}).get("message", ""),
          f"declines={declines}")
    check("g18 NEEDS-AUTHORIZATION marker", "NEEDS-AUTHORIZATION" in out, out)
    check("g18 never a success payload for permission",
          not (declines and "result" in declines[0]), f"declines={declines}")

    # ---- G19: config fail-closed before spawn --------------------------------
    lab = Lab(root, name="g19")
    loose = os.path.join(root, "loose.json")
    with open(loose, "w") as fh:
        fh.write('{"model": "x/glm", "provider": {}}')
    os.chmod(loose, 0o644)
    env = dict(os.environ)
    env["STUB_LOG"] = lab.log
    env["STUB_MODE"] = "ok"
    # Raw invocation WITHOUT --settings (Run() always adds it):
    p = subprocess.run(
        [sys.executable, DRIVER, "--bin", lab.stub, "--cwd", lab.root],
        input="", capture_output=True, text=True, env=env, timeout=15,
    )
    code, out = p.returncode, p.stdout + p.stderr
    p2 = subprocess.run(
        [sys.executable, DRIVER, "--bin", lab.stub, "--cwd", lab.root, "--settings", loose],
        input="", capture_output=True, text=True, env=env, timeout=15,
    )
    code2, out2 = p2.returncode, p2.stdout + p2.stderr
    check("g19 missing --settings exits 64", code == 64 and "never falls back" in out, f"code={code} {out[-200:]}")
    check("g19 loose perms exits 64", code2 == 64 and "0600" in out2, f"code={code2} {out2[-200:]}")
    check("g19 no child spawned on config failure", lab.frames("argv") == [], f"{lab.frames('argv')}")

    print(f"\nSUMMARY: pass={PASS} fail={FAIL}")
    if FAILURES:
        print("\n".join(f"  - {f}" for f in FAILURES))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
