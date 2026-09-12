#!/usr/bin/env python3
"""zcode worker driver: wrap a long-lived `zcode app-server` session for tmux.

Position in the orchestration stack (see references/09-zcode-cli-worker.md and
references/24-zcode-driver-safety.md): the zcode CLI ships no standalone TUI
(`@zcode/tui` is not bundled with the desktop app), so a worker terminal runs
THIS driver instead. The driver

  * spawns `zcode app-server` as a child (stdio JSON protocol, bare frames
    `{id, method, params}` — no jsonrpc envelope),
  * auto-answers every `session/requestRuntimePreferences` server request
    (each turn fails with `prompt_failed` unless answered within 15s),
  * forwards plain text typed into the terminal (PM `send`) to `session/send`
    — messages reach the SAME long-lived session, no process restart,
  * renders protocol events as human-readable lines on stdout so existing
    PM inspection (tmux capture-pane / Orca terminal read) works unchanged.

Local commands on stdin (typed like plain text, `/` prefix):
  /status   print session state summary (local projection + session/read)
  /stop     stop the running turn (session/stop) — process stays alive
  /compact  compact the session context (session/compact)
  /quit     close the session and exit the driver
Control commands are NEVER forwarded to the model as session text, including
while the session is still starting up.

== Startup readiness barrier (safety refactor 2026-09-13) ==

The driver only reaches READY after: session/create -> session/setModel (when
--model is given) -> session/read -> EXACT match of the session's actual
{providerId, modelId} against the frozen expected modelRef. Without --model
the expected ref is frozen from the private settings file's `model` field at
startup and verified the same way. Any create/setModel/read error, malformed
response, model mismatch, or bootstrap deadline expiry exits NON-ZERO with
ZERO task messages sent — the queued backlog is dropped (reported), never
flushed, and the driver never falls back to "whatever model the global config
happens to select".

== Private settings isolation (explicit entry, fail-closed) ==

`--settings PATH` (required) is the ONLY accepted configuration entry: a
private per-worker settings file the DISPATCHER provides. The path is passed
to the child CLI via the official `--settings <path>` flag (absolute path —
the official loader resolves relative paths against the child's own cwd).
The driver never reads, writes, or falls back to the shared
`~/.zcode/cli/config.json`, never rewrites the global model on exit, and
never redirects HOME or injects config by environment.

The OFFICIAL ZCode 0.16.5 `app-server` entry REJECTS `--settings`
("Unknown option --settings", exit 1 — PM live receipt 2026-09-13; the flag
documented in `--help` belongs to other entry points). When the child dies
at startup rejecting the isolation flag, the driver prints an explicit
`UNSUPPORTED_CONFIG_ISOLATION` line and exits 68 — it must NOT be deployed as
the default worker entry against that build. Community runtime builds that
actually accept `--settings` for app-server (separate contract) can reuse
this driver unchanged. This flag isolates the USER SETTINGS layer only: it
does not isolate the session DB, the desktop auth storage, or project-level
`.zcode` config files inside the session workspace.

== Permission mode ==

`--mode` maps to the session/create `mode` parameter: build (default, safe —
the server refuses mutating tools without an interactive permission client),
edit, plan, or yolo (unattended; EXPLICIT opt-in only, same risk class as
claude-code bypassPermissions). The driver never auto-approves reverse
permission requests: `interaction/requestPermission` and any other unknown
server->client request gets an identifiable error reply (never a guessed
success payload) so the corresponding work stops instead of hanging.

== Start/Weekend runtime verification headers ==

`interaction/requestProviderRuntimeHeaders` (provider runtime verification,
incl. captcha-retry) is answered via the official fail-closed channel
`{headersApplied: false, errorMessage: ...}`. This driver has NO desktop host
bridge: it cannot apply verification headers, and it never collects, prints,
forwards, or caches captcha/header/ticket material. `headersApplied:false`
makes the server fail the model request loudly instead of proceeding
unverified — an error is NEVER treated as completion.

== Exit codes ==

  0    clean shutdown (/quit with close confirmed, or EOF teardown) — also 0
       when /quit arrives before the session existed (user-initiated abort)
  64   misconfiguration (bad --mode/--settings/--bin/--cwd, unreadable or
       world/group-readable settings file, unusable model ref)
  65   startup not verified (create/setModel/read error, timeout, malformed
       response, or actual model != expected model) — zero task sends
  66   app-server child exited unexpectedly (before or after ready)
  68   UNSUPPORTED_CONFIG_ISOLATION (child rejected the --settings flag)
  70   /quit close was sent but not confirmed within the close timeout
  130  SIGINT (128+2), 143 SIGTERM — bounded child settlement completed

All rendered output goes through emit(): redaction first (token/header/
credential patterns and structured masking), then length bounding. Unknown
notifications print their method name and param KEY names only — never
values, and truncation is never used as a substitute for redaction.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import shlex
import shutil
import signal
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
# Official permission modes (bundle normalizePromptMode, 0.16.5 static read):
# build / edit / plan / yolo. build is the safe headless default; yolo is the
# unattended mode and must be an explicit dispatch decision.
MODES = ("build", "edit", "plan", "yolo")

DEFAULT_BOOTSTRAP_TIMEOUT = 45.0
DEFAULT_CLOSE_TIMEOUT = 5.0
CHILD_TERMINATE_TIMEOUT = 3.0

# Official server->client request method names (bundle static read 0.16.5).
METHOD_RUNTIME_PREFS = "session/requestRuntimePreferences"
METHOD_RUNTIME_HEADERS = "interaction/requestProviderRuntimeHeaders"
# Reverse requests this driver structurally knows about but cannot answer
# (no interactive client / no host bridge). Declined with an identifiable
# error frame — never a guessed success payload, never silence.
KNOWN_UNSUPPORTED_REQUESTS = (
    "interaction/requestPermission",
    "interaction/requestUserInput",
    "interaction/requestOfficialMcpAuthHeaders",
)
# Child output matching this means the child binary rejected the --settings
# isolation flag itself (official 0.16.5 app-server behavior, PM live
# receipt 2026-09-13) — classify as UNSUPPORTED_CONFIG_ISOLATION, not a
# generic child crash.
UNKNOWN_OPTION_SETTINGS_RE = re.compile(
    r"(?i)unknown\s+option[^\n]{0,80}--settings"
    r"|--settings[^\n]{0,80}unknown\s+option"
)

# ---------------------------------------------------------------------------
# Output hygiene: redact first, bound second. Truncation is NEVER a
# substitute for redaction, so every rendered line passes through emit().
# ---------------------------------------------------------------------------

MAX_LINE = 400
ELLIPSIS = "…"
REDACTED = "[REDACTED]"

# Token schemes first so the header pattern cannot orphan the credential.
REDACT_PATTERNS = [
    (re.compile(r"(?i)\b(bearer|basic|token)\s+([A-Za-z0-9._~+/=-]{6,})"),
     r"\1 [REDACTED-TOKEN]"),
    (re.compile(r"\b(sk-[A-Za-z0-9_-]{8,})"), "[REDACTED-TOKEN]"),
    # Header-style assignments: Authorization: ..., "Cookie": ..., including
    # JSON-quoted and Python-repr keys. The \[[^\]]*\] alternative swallows
    # JSON-array values wholesale so no array element can survive.
    (re.compile(
        r"(?i)\b(authorization|proxy-authorization|x-api-key|api-key|"
        r"x-goog-api-key|cookie|set-cookie)\b(['\"]?\s*[:=]\s*)"
        r"(\[[^\]]*\]|\"[^\"]*\"|'[^']*'|[^\s,;}\]]+)"),
     r"\1\2" + REDACTED),
    # Generic secret-ish field names: apiKey: ..., "password": "..." ...
    (re.compile(
        r"(?i)\b(api[_ ]?key|access[_ ]?token|refresh[_ ]?token|token|"
        r"secret|password|passwd|credential)\b(['\"]?\s*[:=]\s*)"
        r"(\"[^\"]{4,}\"|'[^']{4,}'|[A-Za-z0-9._~+/=-]{8,})"),
     r"\1\2" + REDACTED),
]

# Structured-payload masking (single choke point before json.dumps): covers
# shapes text patterns cannot parse (header values serialized as arrays or
# nested objects). Exact key match; header-block keys keep header NAMES with
# every value masked, credential keys mask the whole value.
HEADER_BLOCK_KEYS = re.compile(r"(?i)^(headers|responseheaders|requestheaders)$")
SENSITIVE_PAYLOAD_KEYS = re.compile(
    r"(?i)^(authorization|proxy-authorization|x-api-key|api-key|api_?key|"
    r"cookie|set-cookie|jwt|access[-_]?token|refresh[-_]?token|token|"
    r"secret|password|passwd|credential|x-aliyun-captcha-.*)$"
)


def mask_header_value(value):
    if isinstance(value, str):
        return REDACTED if value else value
    if isinstance(value, list):
        return [mask_header_value(v) for v in value]
    if isinstance(value, dict):
        return {k: mask_header_value(v) for k, v in value.items()}
    return REDACTED


def mask_value(value, key_hint: str = ""):
    """Recursively mask credential material in structured payloads."""
    if HEADER_BLOCK_KEYS.match(key_hint):
        if isinstance(value, dict):
            return {
                k: (REDACTED if SENSITIVE_PAYLOAD_KEYS.match(str(k))
                    else mask_header_value(v))
                for k, v in value.items()
            }
        return REDACTED if value else value
    if SENSITIVE_PAYLOAD_KEYS.match(key_hint):
        return REDACTED
    if isinstance(value, dict):
        return {k: mask_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_value(v) for v in value]
    return value


def redact(text: str) -> str:
    for pattern, replacement in REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def bound(text: str, limit: int = MAX_LINE) -> str:
    return text if len(text) <= limit else text[:limit] + ELLIPSIS


def emit(line: str) -> None:
    """Single exit point for every rendered line: redacted, then bounded."""
    print(redact(bound(line)), flush=True)


def payload_summary(value, limit: int = MAX_LINE) -> str:
    try:
        return json.dumps(mask_value(value), ensure_ascii=False)
    except (TypeError, ValueError):
        return "<unserializable>"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

_next_request_id = 0
_request_id_lock = threading.Lock()


def request_id() -> int:
    global _next_request_id
    with _request_id_lock:
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


def load_private_settings(path: str) -> dict:
    """Validate the explicit private settings entry. Fail closed (64) on:
    missing file, group/world-readable permissions (credential hygiene),
    malformed JSON, or missing `model`/`provider` keys. The driver NEVER
    touches the shared ~/.zcode/cli/config.json as a fallback."""
    if not path:
        fail_config(
            "--settings is required: the driver only runs with an explicit "
            "private per-worker settings file and never falls back to the "
            "shared global config"
        )
    abs_path = os.path.abspath(path)
    if not os.path.isfile(abs_path):
        fail_config(f"--settings {abs_path}: file does not exist")
    perms = os.stat(abs_path).st_mode & 0o777
    if perms & 0o077:
        fail_config(
            f"--settings {abs_path}: permissions {oct(perms)} are "
            "group/world accessible; require 0600 (private credentials)"
        )
    try:
        with open(abs_path, "r", encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        fail_config(f"cannot read private settings {abs_path}: {exc}")
    if not isinstance(config, dict) or not config.get("model") or not config.get("provider"):
        fail_config(
            f"private settings {abs_path} lacks `model` / `provider` keys — "
            "the headless CLI cannot reach any model provider without them"
        )
    return config


def parse_model_ref(model_field: object, source: str) -> dict:
    """`provider/model` config string -> frozen {providerId, modelId}."""
    text = str(model_field or "")
    if "/" not in text:
        fail_config(
            f"{source} `model` field {text!r} has no provider prefix "
            "(expected `providerId/modelId`)"
        )
    provider_id, model_id = text.split("/", 1)
    if not provider_id or not model_id:
        fail_config(f"{source} `model` field {text!r} is malformed")
    return {"providerId": provider_id, "modelId": model_id}


def resolve_model_ref(spec: str, settings: dict) -> dict:
    """`MODEL`, `providerId/modelId` -> setModel modelRef. Bare model ids
    reuse the private settings' provider prefix."""
    if "/" in spec:
        provider_id, model_id = spec.split("/", 1)
    else:
        provider_id = str(settings.get("model", "")).split("/", 1)[0]
        model_id = spec
    if not provider_id or not model_id:
        fail_config(f"cannot build providerId/modelId for --model {spec}")
    return {"providerId": provider_id, "modelId": model_id}


class Driver:
    """Bootstrap state machine:

    starting -> (create ok) -> applying? -> verifying -> ready
    any failure/timeout -> failed (main loop exits non-zero, zero sends)
    """

    def __init__(
        self,
        proc: subprocess.Popen,
        mode: str,
        model_ref: dict,
        apply_model: bool,
        bootstrap_timeout: float,
    ) -> None:
        self.proc = proc
        self.mode = mode
        # Frozen expected {providerId, modelId}: from --model when given,
        # else from the private settings `model` field. The session's ACTUAL
        # model must match this exactly before any task text is drained.
        self.expected_model = model_ref
        # True only when --model was given: create -> setModel -> read.
        # Without --model: create -> read (verify only, no write).
        self.apply_model = apply_model
        self.bootstrap_timeout = bootstrap_timeout
        self.bootstrap_deadline = time.monotonic() + bootstrap_timeout

        self.write_lock = threading.Lock()
        self.pending_lock = threading.Lock()
        self.pending: dict[int, str] = {}  # request id -> short label

        self.queue_lock = threading.Lock()
        # PM text that arrived before READY; flushed in order ONLY after the
        # model verify barrier passes. On bootstrap failure it is dropped
        # (reported), never sent.
        self.queued_inputs: list[str] = []

        self.state_lock = threading.Lock()
        self.session_id = ""
        self.actual_model = ""

        # Bootstrap coordination (reader thread transitions, main waits).
        self.ready_event = threading.Event()
        self.fail_event = threading.Event()
        self.fail_reason = ""
        self.child_dead = threading.Event()
        self.child_output: list[str] = []  # last raw lines (for classification)
        self.close_acked = threading.Event()
        self.close_timeout = DEFAULT_CLOSE_TIMEOUT

    # ---- protocol plumbing -------------------------------------------------

    def send_line(self, payload: dict) -> None:
        assert self.proc.stdin is not None
        with self.write_lock:
            self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()

    def request(self, method: str, params: dict, label: str) -> int:
        rid = request_id()
        with self.pending_lock:
            self.pending[rid] = label
        self.send_line({"id": rid, "method": method, "params": params})
        return rid

    def bootstrap_fail(self, reason: str) -> None:
        with self.state_lock:
            if self.fail_event.is_set():
                return
            self.fail_reason = reason
        self.fail_event.set()

    def boot_expired(self) -> bool:
        return time.monotonic() > self.bootstrap_deadline

    # ---- bootstrap transitions (reader thread) ------------------------------

    def on_create_result(self, result: dict) -> None:
        session = result.get("session")
        if not (isinstance(session, dict) and isinstance(session.get("sessionId"), str)
                and session["sessionId"]):
            self.bootstrap_fail(
                "create result malformed: no result.session.sessionId "
                f"({payload_summary(result, 120)})"
            )
            return
        with self.state_lock:
            self.session_id = session["sessionId"]
        emit(f"[driver] session created: {self.session_id}")
        if self.apply_model:
            self.request(
                "session/setModel",
                {
                    "sessionId": self.session_id,
                    "model": self.expected_model,
                    # Server default rewrites the persisted last-used model;
                    # the per-worker choice must not leak (PM dual-worker
                    # live check, 2026-08-27).
                    "persistAsWorkspaceLastUsed": False,
                },
                "setModel",
            )
        else:
            # No --model: the settings-selected model must already be the
            # frozen expected ref — verify it instead of writing it.
            self.request("session/read", {"sessionId": self.session_id}, "read")

    def on_setmodel_result(self, result: dict) -> None:
        # Success carries no model echo — the authoritative check is the
        # session/read below.
        self.request("session/read", {"sessionId": self.session_id}, "read")

    def on_read_result(self, result: dict) -> None:
        state = result.get("session")
        model = state.get("model") if isinstance(state, dict) else None
        if not isinstance(model, dict):
            self.bootstrap_fail(
                "read result malformed: no result.session.model "
                f"({payload_summary(result, 120)})"
            )
            return
        actual = {
            "providerId": str(model.get("providerId", "")),
            "modelId": str(model.get("modelId", "")),
        }
        with self.state_lock:
            self.actual_model = f"{actual['providerId']}/{actual['modelId']}"
        if actual != self.expected_model:
            self.bootstrap_fail(
                "model mismatch: session reports "
                f"{actual['providerId']}/{actual['modelId']} but "
                f"{self.expected_model['providerId']}/{self.expected_model['modelId']} "
                "was requested — refusing to send task text on the wrong model"
            )
            return
        # READY: only now may queued PM text reach the model. Inputs that
        # arrive while the backlog drains are picked up here too — ready_event
        # is only set AFTER the queue is empty, so the main loop's direct
        # send path can never strand or reorder queued text.
        with self.queue_lock:
            drained = len(self.queued_inputs)
        while True:
            with self.queue_lock:
                if not self.queued_inputs:
                    break
                text = self.queued_inputs.pop(0)
            self.request(
                "session/send",
                {"sessionId": self.session_id, "content": text},
                "send",
            )
        emit(
            f"[driver] READY model={self.actual_model} verified "
            f"mode={self.mode} drained={drained}"
        )
        self.ready_event.set()

    # ---- rendering -----------------------------------------------------------

    def render(self, frame: dict) -> None:
        method = frame.get("method")
        if method is None:  # response to one of our requests
            self.render_response(frame)
            return

        params = frame.get("params") or {}
        if method == METHOD_RUNTIME_PREFS:
            # Answer immediately: every turn fails (prompt_failed) unless the
            # client replies within the 15s server-side window.
            if "id" in frame:
                self.send_line({"id": frame["id"], "result": PREFS})
                emit(f"[driver] answered runtimePreferences scope={params.get('scope')}")
            return
        if method == METHOD_RUNTIME_HEADERS:
            self.handle_runtime_headers(frame)
            return
        if isinstance(frame.get("id"), (int, str)):
            # Unknown (or known-unsupported) SERVER REQUEST: reply with an
            # identifiable error so the corresponding work stops instead of
            # the server stalling 15s. Never a guessed success payload, and
            # never a silent auto-approval.
            known = method in KNOWN_UNSUPPORTED_REQUESTS
            self.send_line({
                "id": frame["id"],
                "error": {
                    "code": -32601,
                    "message": (
                        "driver does not support "
                        f"{method}: "
                        + (
                            "no interactive permission client attached; "
                            "re-dispatch with an explicit mode decision if "
                            "this work is intended"
                            if known else
                            "unsupported reverse request"
                        )
                    ),
                },
            })
            marker = "NEEDS-AUTHORIZATION" if known else "UNSUPPORTED"
            emit(f"[driver] {marker}: declined server request {method}")
            return
        if method == "state.updated":
            # Whitelisted fields only — a patch can carry arbitrary data.
            patch = params.get("patch") or {}
            if isinstance(patch, dict):
                emit(f"[session] {patch.get('status', '?')} ({params.get('reason', '—')})")
            return
        if method in ("process/resourceSample", "v4/telemetry/event"):
            return  # too chatty; PM polls artifacts / sqlite instead
        if method == "computer-use/operation-event":
            op = params.get("operation") or params
            emit(f"[tool] {payload_summary(op, 160)}")
            return
        # Unknown notifications: method name + param KEY NAMES only. Values
        # are never rendered — bounding a value is not redaction.
        keys = ",".join(sorted(str(k) for k in params.keys())) if isinstance(params, dict) else "?"
        emit(f"[notify] {method} (params redacted; keys: {keys or 'none'})")

    def render_response(self, frame: dict) -> None:
        rid = frame.get("id")
        with self.pending_lock:
            label = self.pending.pop(rid, "?") if isinstance(rid, int) else "?"
        if "error" in frame:
            err = frame["error"] or {}
            emit(f"[driver] {label} ✗ {err.get('code')}: {err.get('message')}")
            if not self.ready_event.is_set():
                self.bootstrap_fail(f"{label} failed: {err.get('code')} {err.get('message')}")
            return
        result = frame.get("result", {})
        if isinstance(result, dict) and label == "create" and not self.ready_event.is_set():
            self.on_create_result(result)
        elif isinstance(result, dict) and label == "setModel" and not self.ready_event.is_set():
            self.on_setmodel_result(result)
        elif isinstance(result, dict) and label == "read" and not self.ready_event.is_set():
            self.on_read_result(result)
        elif label == "close":
            self.close_acked.set()
            emit("[driver] close ✓")
        elif label == "send":
            emit(f"[driver] send ✓ accepted={result.get('accepted') if isinstance(result, dict) else '?'}")
        elif label == "stop":
            emit("[driver] stop ✓")
        elif label == "compact":
            emit("[driver] compact ✓")
        elif label == "read" and self.ready_event.is_set():
            state = result.get("session") if isinstance(result, dict) else {}
            model = state.get("model") or {} if isinstance(state, dict) else {}
            if isinstance(model, dict):
                model = f"{model.get('providerId', '?')}/{model.get('modelId', '?')}"
            emit(f"[driver] read ✓ status={state.get('status', '?') if isinstance(state, dict) else '?'} model={model}")
        else:
            emit(f"[driver] {label} ✓ {payload_summary(result, 120)}")

    def handle_runtime_headers(self, frame: dict) -> None:
        """Official fail-closed channel. This driver has NO host bridge: it
        cannot apply provider runtime verification headers (Start/Weekend
        style runtime verification, captcha retries) and never touches
        header/ticket material. Reply headersApplied:false — the server then
        fails the model request loudly; that error is NOT completion."""
        frame_id = frame.get("id")
        if frame_id is None:
            emit(
                "[driver] NEEDS-AUTHORIZATION: runtime-headers notification "
                "received (no id; cannot even fail-closed-reply) — ignored, "
                "no header material is handled by this driver"
            )
            return
        emit(
            "[driver] NEEDS-AUTHORIZATION: provider runtime verification "
            "requested; this driver has no host bridge and will not "
            "collect, print, or apply header/captcha material"
        )
        self.send_line({
            "id": frame_id,
            "result": {
                "headersApplied": False,
                "errorMessage": (
                    "driver has no provider-runtime-headers host bridge: "
                    "complete verification in the official ZCode desktop "
                    "app, or attach a host-bridge runtime (separate contract)"
                ),
            },
        })

    # ---- projection ----------------------------------------------------------

    def projection(self) -> dict:
        with self.state_lock:
            return {
                "state": (
                    "ready" if self.ready_event.is_set()
                    else "failed" if self.fail_event.is_set()
                    else "starting"
                ),
                "sessionId": self.session_id,
                "mode": self.mode,
                "expectedModel": (
                    f"{self.expected_model['providerId']}/{self.expected_model['modelId']}"
                ),
                "actualModel": self.actual_model,
                "queuedInputs": len(self.queued_inputs),
                "childPid": self.proc.pid,
            }


def reader_loop(driver: Driver) -> None:
    """Reads child stdout forever. NEVER calls os._exit — child death is an
    event so the main thread performs the bounded settlement + cleanup."""
    assert driver.proc.stdout is not None
    for raw in driver.proc.stdout:
        line = raw.strip()
        if not line:
            continue
        try:
            frame = json.loads(line)
        except json.JSONDecodeError:
            driver.child_output.append(line)
            if len(driver.child_output) > 20:
                del driver.child_output[:-20]
            emit(f"[driver] non-JSON line: {line}")
            continue
        if isinstance(frame, dict):
            driver.render(frame)
    driver.child_dead.set()
    emit("[driver] app-server stdout closed (child exited)")


def classify_child_death(driver: Driver) -> int:
    """Map an unexpected child exit to an exit code. A child that died
    rejecting the --settings flag is UNSUPPORTED_CONFIG_ISOLATION (68), not
    a generic crash."""
    for line in driver.child_output:
        if UNKNOWN_OPTION_SETTINGS_RE.search(line):
            emit(
                "[driver] UNSUPPORTED_CONFIG_ISOLATION: the app-server "
                "binary rejected the --settings isolation flag (official "
                "0.16.5 behavior, PM live receipt 2026-09-13). The driver "
                "will NOT fall back to the shared global config; deploy a "
                "runtime build that supports --settings for app-server."
            )
            return 68
    return 66


def terminate_child(proc: subprocess.Popen) -> None:
    """Precise-handle bounded teardown: SIGTERM, wait, SIGKILL, wait. Never
    kills by process name or pattern."""
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
    except OSError:
        pass
    try:
        proc.wait(timeout=CHILD_TERMINATE_TIMEOUT)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        proc.kill()
    except OSError:
        pass
    try:
        proc.wait(timeout=CHILD_TERMINATE_TIMEOUT)
    except subprocess.TimeoutExpired:
        emit(f"[driver] WARNING: child pid {proc.pid} did not exit after SIGKILL")


def shutdown(driver: Driver, requested: bool) -> int | None:
    """Bounded close settlement. Returns an exit code when the caller should
    exit with it, or None when settlement must be classified by the caller
    (child death / bootstrap failure already have codes)."""
    if requested and driver.session_id and not driver.child_dead.is_set():
        driver.request("session/close", {"sessionId": driver.session_id}, "close")
        deadline = time.monotonic() + driver.close_timeout
        while time.monotonic() < deadline:
            if driver.close_acked.is_set() or driver.child_dead.is_set():
                break
            time.sleep(0.05)
        terminate_child(driver.proc)
        if not driver.close_acked.is_set() and not driver.child_dead.is_set():
            # child_dead unset and no ack: close unconfirmed.
            emit("[driver] close NOT confirmed within timeout")
            return 70
        return None
    terminate_child(driver.proc)
    return None


def input_pump(stdin, lines: "queue.Queue[str | None]") -> None:
    """Feeds stdin lines into a queue so the main loop can also watch
    events with bounded latency. EOF pushes None."""
    try:
        for line in stdin:
            lines.put(line)
    except (OSError, ValueError):
        pass
    finally:
        lines.put(None)


def do_quit(driver: Driver) -> int:
    """Clean /quit settlement: bounded close, exit 0 only when the close is
    confirmed (or no session ever existed)."""
    emit("[driver] /quit: closing session")
    result = shutdown(driver, requested=True)
    if result is None:
        result = 0 if (driver.close_acked.is_set() or not driver.session_id) else 70
    emit("[driver] bye")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--cwd", default="", help="session workspace (default: current directory)"
    )
    parser.add_argument("--bin", default="", help="zcode executable override")
    parser.add_argument(
        "--settings",
        default="",
        help="REQUIRED: private per-worker settings file, passed to the CLI "
        "via the official --settings flag (absolute path recommended; never "
        "the shared ~/.zcode/cli/config.json)",
    )
    parser.add_argument(
        "--mode",
        default="build",
        choices=list(MODES),
        help="session permission mode (default: build — safe; yolo is an "
        "explicit unattended opt-in)",
    )
    parser.add_argument(
        "--model",
        default="",
        help="per-worker model, e.g. GLM-5.3-Flash or providerId/modelId "
        "(default: the `model` field of the private settings file)",
    )
    parser.add_argument(
        "--bootstrap-timeout",
        type=float,
        default=DEFAULT_BOOTSTRAP_TIMEOUT,
        help=f"seconds to reach READY or fail (default {DEFAULT_BOOTSTRAP_TIMEOUT:g})",
    )
    parser.add_argument(
        "--close-timeout",
        type=float,
        default=DEFAULT_CLOSE_TIMEOUT,
        help=f"seconds to wait for session/close ack on /quit (default {DEFAULT_CLOSE_TIMEOUT:g})",
    )
    args = parser.parse_args()
    if not args.bootstrap_timeout > 0:
        fail_config("--bootstrap-timeout must be > 0")

    worktree = os.path.abspath(args.cwd or os.getcwd())
    if not os.path.isdir(worktree):
        fail_config(f"--cwd {worktree} is not a directory")
    settings = load_private_settings(args.settings)
    settings_path = os.path.abspath(args.settings)
    if args.model:
        model_ref = resolve_model_ref(args.model, settings)
        emit(f"[driver] per-worker model: {model_ref['providerId']}/{model_ref['modelId']}")
    else:
        model_ref = parse_model_ref(settings.get("model"), "--settings")
        emit(
            "[driver] frozen session model from settings: "
            f"{model_ref['providerId']}/{model_ref['modelId']}"
        )

    zcode = resolve_zcode_bin(args.bin)
    argv = (
        [zcode, ZCODE_BUNDLE, "app-server"]
        if zcode.endswith("/node") or os.path.basename(zcode) == "node"
        else [zcode, "app-server"]
    )
    argv += ["--settings", settings_path]
    emit(
        f"[driver] starting: {shlex.quote(argv[0])} app-server "
        f"--settings {settings_path} (cwd={worktree}, mode={args.mode})"
    )
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
    driver = Driver(
        proc, args.mode, model_ref, bool(args.model), args.bootstrap_timeout
    )
    driver.close_timeout = max(0.1, args.close_timeout)

    # Bootstrap: create -> setModel -> read -> verify -> READY -> drain.
    driver.request(
        "session/create",
        {
            "workspace": {"workspaceKey": worktree, "workspacePath": worktree},
            "mode": args.mode,
        },
        "create",
    )
    threading.Thread(target=reader_loop, args=(driver,), daemon=True).start()

    lines: "queue.Queue[str | None]" = queue.Queue()
    threading.Thread(target=input_pump, args=(sys.stdin, lines), daemon=True).start()

    sigint_code: list[int] = []

    def on_signal(signum, _frame) -> None:
        sigint_code.append(128 + signum)
        # Wake the main loop (it polls at 0.2s; this just accelerates it).

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    exit_code: int | None = None
    quit_requested = False  # /quit during bootstrap: conclude first, then close
    eof_pending = False  # EOF with undrained interest: same deferral
    while True:
        if sigint_code:
            emit(f"[driver] signal {sigint_code[0] - 128} received: bounded shutdown")
            shutdown(driver, requested=True)
            exit_code = sigint_code[0]
            break
        if driver.fail_event.is_set():
            with driver.queue_lock:
                dropped = list(driver.queued_inputs)
                driver.queued_inputs = []
            if dropped:
                emit(
                    f"[driver] dropped {len(dropped)} queued input(s) — "
                    "startup failed, nothing was sent to the model"
                )
            shutdown(driver, requested=False)
            exit_code = 65
            emit(f"[driver] STARTUP NOT VERIFIED: {driver.fail_reason}")
            break
        if driver.child_dead.is_set():
            code = classify_child_death(driver)
            shutdown(driver, requested=False)
            exit_code = code
            break
        if not driver.ready_event.is_set() and driver.boot_expired():
            driver.bootstrap_fail(
                f"bootstrap deadline ({args.bootstrap_timeout:g}s) expired "
                "before the session model was verified"
            )
            continue
        if (quit_requested or eof_pending) and driver.ready_event.is_set():
            # Bootstrap concluded READY after /quit or EOF arrived: the drain
            # happened (queued text was flushed by the reader), now close.
            exit_code = do_quit(driver)
            break
        try:
            item = lines.get(timeout=0.2)
        except queue.Empty:
            continue
        if item is None:  # EOF (tmux pane killed)
            with driver.queue_lock:
                undrained = quit_requested or bool(driver.queued_inputs)
            if undrained and not driver.fail_event.is_set() and not driver.child_dead.is_set():
                # Text is still queued behind the verify barrier (or /quit is
                # deferred): tearing down now would silently lose the drain.
                # Defer bounded by the bootstrap deadline; failure/child-death
                # paths above keep priority.
                eof_pending = True
                emit("[driver] stdin EOF: startup still verifying; teardown deferred (bounded)")
                continue
            emit("[driver] stdin EOF: closing")
            shutdown(driver, requested=True)
            exit_code = 0
            break
        text = item.strip()
        if not text:
            continue
        # Control commands are handled BEFORE any queueing and are never
        # forwarded to the model — including during startup.
        if text == "/quit":
            if driver.ready_event.is_set():
                exit_code = do_quit(driver)
                break
            # Startup still in flight: wait (bounded by the bootstrap
            # deadline) for it to conclude, so an in-flight drain is not
            # silently lost. Failure/child-death paths above keep priority.
            quit_requested = True
            emit("[driver] /quit deferred: startup still verifying (bounded)")
            continue
        if text == "/status":
            print("[status] " + redact(json.dumps(driver.projection(), ensure_ascii=False)), flush=True)
            if driver.ready_event.is_set() and driver.session_id:
                driver.request("session/read", {"sessionId": driver.session_id}, "read")
            continue
        if text == "/stop":
            if driver.ready_event.is_set() and driver.session_id:
                driver.request("session/stop", {"sessionId": driver.session_id}, "stop")
            else:
                emit("[driver] /stop dropped: session not ready (nothing to stop)")
            continue
        if text == "/compact":
            if driver.ready_event.is_set() and driver.session_id:
                driver.request("session/compact", {"sessionId": driver.session_id}, "compact")
            else:
                emit("[driver] /compact dropped: session not ready")
            continue
        if not driver.ready_event.is_set():
            with driver.queue_lock:
                driver.queued_inputs.append(text)
            emit(f"[driver] queued (session starting): {text[:60]}")
            continue
        driver.request(
            "session/send",
            {"sessionId": driver.session_id, "content": text},
            "send",
        )

    emit(f"[driver] exit {exit_code}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
