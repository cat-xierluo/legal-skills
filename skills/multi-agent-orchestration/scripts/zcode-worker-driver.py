#!/usr/bin/env python3
"""zcode worker driver: wrap a long-lived `zcode app-server` session for tmux.

Position in the orchestration stack (see references/09-zcode-cli-worker.md):
the zcode CLI ships no standalone TUI (`@zcode/tui` is not bundled with the
desktop app), so a worker terminal runs THIS driver instead. The driver

  * spawns `zcode app-server` as a child (stdio JSON protocol, bare frames
    `{id, method, params}` — no jsonrpc envelope),
  * auto-answers every `session/requestRuntimePreferences` server request
    (each turn fails with `prompt_failed` unless answered within 15s),
  * forwards plain text typed into the terminal (PM `send`) to `session/send`
    — messages reach the SAME long-lived session, no process restart,
  * renders protocol events as human-readable lines on stdout so existing
    PM inspection (tmux capture-pane / Orca terminal read) works unchanged.

Local commands on stdin (typed like plain text, `/` prefix):
  /status   print session state summary (session/read)
  /stop     stop the running turn (session/stop) — process stays alive
  /compact  compact the session context (session/compact)
  /quit     close the session and exit the driver

Exit codes: 64 = misconfiguration (missing zcode executable / model config),
1 = app-server child died, 0 = clean /quit.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time

PREFS = {
    "nativeSearchEnhancementsEnabled": True,
    "memoryEnabled": False,
    "askUserQuestionAutoResolutionEnabled": True,
}
ZCODE_BUNDLE = "/Applications/ZCode.app/Contents/Resources/glm/zcode.cjs"
# ZCODE_CLI_CONFIG overrides the config path (tests / multi-install machines).
CLI_CONFIG = os.environ.get(
    "ZCODE_CLI_CONFIG",
    os.path.join(os.path.expanduser("~"), ".zcode", "cli", "config.json"),
)

_next_request_id = 0


def request_id() -> int:
    global _next_request_id
    _next_request_id += 1
    return _next_request_id


def fail_config(message: str) -> None:
    print(f"[driver] CONFIG ERROR: {message}", flush=True)
    sys.exit(64)


def resolve_zcode_bin(explicit: str) -> str:
    if explicit:
        if not os.path.exists(explicit):
            fail_config(f"--bin {explicit} does not exist")
        return explicit
    found = shutil.which("zcode")
    if found:
        return found
    if os.path.exists(ZCODE_BUNDLE):
        node = shutil.which("node")
        if node:
            return node  # caller joins ZCODE_BUNDLE as argv[1] below
    fail_config(
        "no zcode executable found (PATH `zcode` or "
        f"{ZCODE_BUNDLE}). Install the ZCode desktop app first."
    )
    raise AssertionError("unreachable")


def check_model_config() -> None:
    """Fail fast instead of launching a worker that cannot talk to a model."""
    if not os.path.exists(CLI_CONFIG):
        fail_config(
            f"{CLI_CONFIG} is missing. Log in via the ZCode desktop app "
            "(BigModel Coding Plan), then mirror the provider entry into the "
            "cli config — see references/09-zcode-cli-worker.md §2."
        )
    try:
        with open(CLI_CONFIG, "r", encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        fail_config(f"cannot read {CLI_CONFIG}: {exc}")
    if not config.get("model") or not config.get("provider"):
        fail_config(
            f"{CLI_CONFIG} lacks `model` / `provider` keys — the headless CLI "
            "cannot reach any model provider without them (see "
            "references/09-zcode-cli-worker.md §2)."
        )


class Driver:
    def __init__(self, proc: subprocess.Popen, session_id: str) -> None:
        self.proc = proc
        self.session_id = session_id
        self.write_lock = threading.Lock()
        self.pending: dict[int, str] = {}  # request id -> short label
        # PM text that arrived before session/create finished; flushed in
        # order as soon as the session id is known (no message loss).
        self.queued_inputs: list[str] = []
        self.queue_lock = threading.Lock()

    def send_line(self, payload: dict) -> None:
        assert self.proc.stdin is not None
        with self.write_lock:
            self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()

    def request(self, method: str, params: dict, label: str) -> int:
        rid = request_id()
        self.pending[rid] = label
        self.send_line({"id": rid, "method": method, "params": params})
        return rid

    # ---- rendering -------------------------------------------------------

    def render(self, frame: dict) -> None:
        method = frame.get("method")
        if method is None:  # response to one of our requests
            rid = frame.get("id")
            label = self.pending.pop(rid, "?") if isinstance(rid, int) else "?"
            if "error" in frame:
                err = frame["error"]
                print(f"[driver] {label} ✗ {err.get('code')}: {err.get('message')}", flush=True)
            else:
                result = frame.get("result", {})
                if label == "create":
                    # Real protocol (ZCode Protocol v1): the id lives at
                    # result.session.sessionId, not at the top level.
                    session = result.get("session")
                    if isinstance(session, dict) and isinstance(
                        session.get("sessionId"), str
                    ):
                        self.session_id = session["sessionId"]
                        print(
                            f"[driver] session ready: {self.session_id}",
                            flush=True,
                        )
                    with self.queue_lock:
                        backlog, self.queued_inputs = self.queued_inputs, []
                    for text in backlog:
                        self.request(
                            "session/send",
                            {"sessionId": self.session_id, "content": text},
                            "send",
                        )
                summary = self.summarize_result(label, result)
                print(f"[driver] {label} ✓ {summary}", flush=True)
            return

        params = frame.get("params") or {}
        if method == "session/requestRuntimePreferences":
            # Answer immediately: every turn fails (prompt_failed) unless the
            # client replies within the 15s server-side window.
            if "id" in frame:
                self.send_line({"id": frame["id"], "result": PREFS})
                print(
                    f"[driver] answered {frame['id']} "
                    f"scope={params.get('scope')}",
                    flush=True,
                )
            return
        if method == "state.updated":
            patch = params.get("patch") or {}
            print(
                f"[session] {patch.get('status', '?')} ({params.get('reason', '—')})",
                flush=True,
            )
            return
        if method == "process/resourceSample":
            return  # too chatty; PM can poll artifacts / sqlite instead
        if method in ("v4/telemetry/event",):
            return
        if method == "computer-use/operation-event":
            op = params.get("operation") or params
            print(f"[tool] {json.dumps(op, ensure_ascii=False)[:160]}", flush=True)
            return
        # Unknown notifications: one compact line each, never drop silently.
        print(f"[notify] {method} {json.dumps(params, ensure_ascii=False)[:120]}", flush=True)

    @staticmethod
    def summarize_result(label: str, result: dict) -> str:
        if label == "send":
            return f"accepted={result.get('accepted')}"
        if label == "read":
            state = result.get("state") or result
            status = state.get("status", "?")
            model = state.get("model") or {}
            if isinstance(model, dict):
                model = model.get("current") or model.get("modelId", "")
            return f"status={status} model={model}"
        return json.dumps(result, ensure_ascii=False)[:120]


def reader_loop(driver: Driver) -> None:
    assert driver.proc.stdout is not None
    for raw in driver.proc.stdout:
        line = raw.strip()
        if not line:
            continue
        try:
            frame = json.loads(line)
        except json.JSONDecodeError:
            print(f"[driver] non-JSON line: {line[:120]}", flush=True)
            continue
        if isinstance(frame, dict):
            driver.render(frame)
    # stdout closed => child is gone
    print("[driver] app-server exited", flush=True)
    os._exit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--cwd", default="", help="session workspace (default: current directory)"
    )
    parser.add_argument("--bin", default="", help="zcode executable override")
    args = parser.parse_args()

    worktree = os.path.abspath(args.cwd or os.getcwd())
    if not os.path.isdir(worktree):
        fail_config(f"--cwd {worktree} is not a directory")
    check_model_config()

    zcode = resolve_zcode_bin(args.bin)
    argv = (
        [zcode, ZCODE_BUNDLE, "app-server"]
        if zcode.endswith("/node") or os.path.basename(zcode) == "node"
        else [zcode, "app-server"]
    )
    print(f"[driver] starting: {' '.join(argv[:1])} app-server (cwd={worktree})", flush=True)
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=worktree,
        )
    except OSError as exc:
        fail_config(f"cannot spawn zcode app-server: {exc}")

    assert proc.stdin is not None and proc.stdout is not None
    driver = Driver(proc, "")

    # Bootstrap: create the session, then keep it fed from stdin.
    driver.request(
        "session/create",
        {
            "workspace": {"workspaceKey": worktree, "workspacePath": worktree},
            "mode": "yolo",
        },
        "create",
    )
    threading.Thread(target=reader_loop, args=(driver,), daemon=True).start()

    for line in sys.stdin:
        text = line.strip()
        if not text:
            continue
        if text == "/quit":
            # Drain: if inputs are still queued, wait (bounded) for the
            # session to come up and flush them before closing.
            deadline = time.monotonic() + 10.0
            while not driver.session_id and time.monotonic() < deadline:
                with driver.queue_lock:
                    still_queued = bool(driver.queued_inputs)
                if not still_queued:
                    break
                time.sleep(0.1)
            if driver.session_id:
                driver.request("session/close", {"sessionId": driver.session_id}, "close")
            print("[driver] bye", flush=True)
            return 0
        if not driver.session_id:
            with driver.queue_lock:
                driver.queued_inputs.append(text)
            print(f"[driver] queued (session starting): {text[:60]}", flush=True)
            continue
        if text == "/status":
            driver.request("session/read", {"sessionId": driver.session_id}, "read")
            continue
        if text == "/stop":
            driver.request("session/stop", {"sessionId": driver.session_id}, "stop")
            continue
        if text == "/compact":
            driver.request("session/compact", {"sessionId": driver.session_id}, "compact")
            continue
        driver.request(
            "session/send",
            {"sessionId": driver.session_id, "content": text},
            "send",
        )

    # stdin closed (tmux pane killed): tear down with the child.
    if driver.session_id:
        driver.request("session/close", {"sessionId": driver.session_id}, "close")
    proc.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
