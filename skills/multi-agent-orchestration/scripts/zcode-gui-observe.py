#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-shot read-only observation of a ZCode GUI session binding.

Chains two sibling tools for exactly one (--db, --session-id, --input-id)
request and prints a single fixed-schema JSON observation on stdout:

1. zcode-session-evidence.py (PR250, collector) reads the native ZCode SQLite
   database strictly read-only and emits session evidence metadata.
2. zcode-gui-monitor-adapter.py (PR253, adapter) maps that metadata onto a
   fixed PM monitor state vocabulary.

Hard guarantees:
- One shot only: no polling, no background work, no watch mode, no network,
  no dispatch, no model or Orca invocation. READY_FOR_PM_REVIEW means exactly
  "awaiting PM review"; nothing is ever delivered or accepted.
- Exit-code gate: each dependency's return code is checked before its stdout
  is interpreted. A non-zero dependency exit is always a failed observation —
  legal-looking payloads from a failed dependency never produce OK/READY
  (R1 blocker B1).
- Fixed error-code allowlists: dependency error codes are accepted only when
  they match the published fixed vocabulary of that dependency; anything
  else maps to OBS_COLLECTOR_FAILED / OBS_ADAPTER_FAILED and is never
  echoed verbatim (R1 blocker B2). Summary echo scalars are printable and
  length-capped; out-of-bounds values collapse to the "not observed"
  sentinel instead of being echoed.
- The native database is never opened or written by this wrapper. Only the
  collector touches it, via SQLite URI mode=ro plus PRAGMA query_only.
- Dependencies run as subprocesses of the current interpreter without
  shell=True under a bounded timeout (default 10s, maximum 60s).
- The intermediate collector metadata is written to a private (0600)
  temporary file that is always removed in a finally block; its exact SHA-256
  digest is pinned via --expected-evidence-sha256.
- Output discipline: exactly one JSON object on stdout. Dependency stdout,
  stderr, paths and tracebacks are never echoed; every failure maps to a
  fixed error code. The three flags stay false in every emission.

Dependency resolution order for --collector / --adapter: explicit flag, then
ZCODE_GUI_COLLECTOR / ZCODE_GUI_ADAPTER, then the sibling script next to this
file. At the base of this branch PR250/PR253 are not merged yet, so the
sibling default is normally absent; pass the frozen copies explicitly.

Exit codes: 0 observation complete (state present); 1 observation failed
(fixed JSON with error.code); 2 command-line usage error (argparse).

Standard library only; supports Python 3.9+.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import tempfile

OBSERVER = "zcode-gui-observe"
SCHEMA_VERSION = 1

ENV_COLLECTOR = "ZCODE_GUI_COLLECTOR"
ENV_ADAPTER = "ZCODE_GUI_ADAPTER"
DEFAULT_COLLECTOR_NAME = "zcode-session-evidence.py"
DEFAULT_ADAPTER_NAME = "zcode-gui-monitor-adapter.py"

MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 60
DEFAULT_TIMEOUT_SECONDS = 10

EXIT_OK = 0
EXIT_ERROR = 1

FALSE_FLAGS = {
    "pmAccepted": False,
    "orcaSupervised": False,
    "livenessAuthoritative": False,
}

ADAPTER_STATES = frozenset({
    "INPUT_ACCEPTED",
    "INPUT_FAILED",
    "TURN_UNKNOWN",
    "TURN_RUNNING",
    "TURN_ERROR",
    "TURN_CANCELLED",
    "DELIVERY_PENDING",
    "DELIVERY_ERROR",
    "READY_FOR_PM_REVIEW",
    "EVIDENCE_CONFLICT",
})

# Fixed allowlists of the published error codes of the frozen dependencies.
# A code outside the respective set maps to OBS_COLLECTOR_FAILED /
# OBS_ADAPTER_FAILED and is never echoed verbatim (R1 blocker B2).
COLLECTOR_ERROR_CODES = frozenset({
    "DB_NOT_FOUND",
    "DB_OPEN_FAILED",
    "DB_SCHEMA_INVALID",
    "READ_ERROR",
    "JSON_MALFORMED",
    "INPUT_NOT_FOUND",
    "INPUT_AMBIGUOUS",
    "TURN_AMBIGUOUS",
    "ASSISTANT_AMBIGUOUS",
    "INTERNAL_ERROR",
})
ADAPTER_ERROR_CODES = frozenset({
    "EVIDENCE_UNREADABLE",
    "EVIDENCE_TOO_LARGE",
    "EVIDENCE_NOT_UTF8",
    "EVIDENCE_NOT_JSON",
    "EVIDENCE_SCHEMA_UNSUPPORTED",
    "EVIDENCE_TYPE_INVALID",
    "EVIDENCE_DIGEST_MISMATCH",
    "BINDING_MISMATCH",
    "PROVIDER_MISMATCH",
    "MODEL_MISMATCH",
})

MAX_ECHO_TEXT_CHARS = 256

ERR_INVALID_ARGS = "OBS_INVALID_ARGS"
ERR_DEP_MISSING = "OBS_DEP_MISSING"
ERR_DEP_SHA_MISMATCH = "OBS_DEP_SHA_MISMATCH"
ERR_DEP_TIMEOUT = "OBS_DEP_TIMEOUT"
ERR_COLLECTOR_FAILED = "OBS_COLLECTOR_FAILED"
ERR_COLLECTOR_BAD_OUTPUT = "OBS_COLLECTOR_BAD_OUTPUT"
ERR_ADAPTER_FAILED = "OBS_ADAPTER_FAILED"
ERR_ADAPTER_BAD_OUTPUT = "OBS_ADAPTER_BAD_OUTPUT"
ERR_BINDING_MISMATCH = "OBS_BINDING_MISMATCH"
ERR_INTERNAL = "OBS_INTERNAL_ERROR"

_HEX64 = re.compile(r"[0-9a-f]{64}")


class ObservationError(Exception):
    """Carries a fixed error code; rendered without any incident detail."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def emit(payload):
    sys.stdout.write(json.dumps(payload, sort_keys=True, ensure_ascii=True) + "\n")
    sys.stdout.flush()


def error_payload(session_id, input_id, code):
    return {
        "observer": OBSERVER,
        "schemaVersion": SCHEMA_VERSION,
        "status": "ERROR",
        "sessionId": session_id,
        "inputId": input_id,
        "state": None,
        "summary": None,
        "flags": dict(FALSE_FLAGS),
        "error": {"code": code},
    }


def allowlisted_code(value, allowlist):
    if isinstance(value, str) and value in allowlist:
        return value
    return None


def bounded_text(value, fallback):
    """Echo-bound a dependency-provided scalar (printable, length-capped)."""
    if not isinstance(value, str) or not value or len(value) > MAX_ECHO_TEXT_CHARS:
        return fallback
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        return fallback
    return value


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def resolve_dependency(explicit, env_name, sibling):
    candidate = explicit
    if not candidate:
        env_value = os.environ.get(env_name)
        if env_value and env_value.strip():
            candidate = env_value
    if not candidate:
        candidate = sibling
    if not candidate or not os.path.isfile(candidate):
        raise ObservationError(ERR_DEP_MISSING)
    return candidate


def sha256_file(path):
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
    except OSError:
        raise ObservationError(ERR_DEP_MISSING)
    return digest.hexdigest()


def check_dependency_sha(path, expected):
    expected_norm = expected.strip().lower()
    if (
        len(expected_norm) != 64
        or not _HEX64.fullmatch(expected_norm)
        or not hmac.compare_digest(sha256_file(path), expected_norm)
    ):
        raise ObservationError(ERR_DEP_SHA_MISMATCH)


def run_dependency(argv, timeout):
    try:
        return subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise ObservationError(ERR_DEP_TIMEOUT)
    except OSError:
        raise ObservationError(ERR_DEP_MISSING)


def load_json_object(raw):
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def collector_failure_code(meta):
    """Allowlisted business code from a collector error payload, else fixed."""
    if meta is not None and meta.get("ok") is not True:
        err = meta.get("error")
        code = err.get("code") if isinstance(err, dict) else None
        return allowlisted_code(code, COLLECTOR_ERROR_CODES) or ERR_COLLECTOR_FAILED
    return ERR_COLLECTOR_FAILED


def run_collector_stage(collector, args):
    proc = run_dependency(
        [
            sys.executable, collector,
            "--db", args.db,
            "--session-id", args.session_id,
            "--input-id", args.input_id,
        ],
        args.timeout,
    )
    meta = load_json_object(proc.stdout)
    # Exit-code gate (R1 blocker B1): a failed dependency is a failed
    # observation regardless of how legal its stdout looks; partial output
    # is never promoted to a success path.
    if proc.returncode != 0:
        raise ObservationError(collector_failure_code(meta))
    if meta is None:
        raise ObservationError(ERR_COLLECTOR_BAD_OUTPUT)
    if meta.get("ok") is not True:
        raise ObservationError(collector_failure_code(meta))
    if not (is_int(meta.get("schemaVersion")) and meta["schemaVersion"] == SCHEMA_VERSION):
        raise ObservationError(ERR_COLLECTOR_BAD_OUTPUT)
    if meta.get("sessionId") != args.session_id or meta.get("inputId") != args.input_id:
        raise ObservationError(ERR_COLLECTOR_BAD_OUTPUT)
    for key in ("input", "turn", "finalAssistant"):
        if not isinstance(meta.get(key), dict):
            raise ObservationError(ERR_COLLECTOR_BAD_OUTPUT)
    return meta, proc.stdout


def run_adapter_stage(adapter, args, raw_evidence):
    digest = hashlib.sha256(raw_evidence).hexdigest()
    handle, evidence_path = tempfile.mkstemp(prefix="zcode-gui-observe-", suffix=".json")
    try:
        with os.fdopen(handle, "wb") as evidence_file:
            evidence_file.write(raw_evidence)
        argv = [
            sys.executable, adapter,
            "--evidence", evidence_path,
            "--session-id", args.session_id,
            "--input-id", args.input_id,
            "--expected-evidence-sha256", digest,
        ]
        if args.expect_provider:
            argv += ["--expected-provider", args.expect_provider]
        if args.expect_model:
            argv += ["--expected-model", args.expect_model]
        proc = run_dependency(argv, args.timeout)
    finally:
        try:
            os.unlink(evidence_path)
        except OSError:
            pass

    data = load_json_object(proc.stdout)
    # Exit-code gate (R1 blocker B1): a failed adapter never yields OK/READY,
    # even when its stdout looks like a legal success payload.
    if proc.returncode != 0:
        code = data.get("error") if data is not None else None
        raise ObservationError(allowlisted_code(code, ADAPTER_ERROR_CODES) or ERR_ADAPTER_FAILED)
    if data is None:
        raise ObservationError(ERR_ADAPTER_BAD_OUTPUT)
    if "error" in data:
        raise ObservationError(allowlisted_code(data.get("error"), ADAPTER_ERROR_CODES) or ERR_ADAPTER_FAILED)
    if not (is_int(data.get("schemaVersion")) and data["schemaVersion"] == SCHEMA_VERSION):
        raise ObservationError(ERR_ADAPTER_BAD_OUTPUT)
    if data.get("sessionId") != args.session_id or data.get("inputId") != args.input_id:
        raise ObservationError(ERR_BINDING_MISMATCH)
    state = data.get("state")
    if not (isinstance(state, str) and state in ADAPTER_STATES):
        raise ObservationError(ERR_ADAPTER_BAD_OUTPUT)
    provider = data.get("provider")
    model = data.get("model")
    if not isinstance(provider, str) or not isinstance(model, str):
        raise ObservationError(ERR_ADAPTER_BAD_OUTPUT)
    flags = data.get("flags")
    if flags is not None:
        if not isinstance(flags, dict):
            raise ObservationError(ERR_ADAPTER_BAD_OUTPUT)
        for key in FALSE_FLAGS:
            if key in flags and flags[key] is not False:
                raise ObservationError(ERR_ADAPTER_BAD_OUTPUT)
    turn_id = data.get("turnId")
    if not (turn_id is None or isinstance(turn_id, str)):
        raise ObservationError(ERR_ADAPTER_BAD_OUTPUT)
    return data, digest


def observe(args):
    if not (MIN_TIMEOUT_SECONDS <= args.timeout <= MAX_TIMEOUT_SECONDS):
        raise ObservationError(ERR_INVALID_ARGS)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    collector = resolve_dependency(
        args.collector, ENV_COLLECTOR,
        os.path.join(script_dir, DEFAULT_COLLECTOR_NAME),
    )
    adapter = resolve_dependency(
        args.adapter, ENV_ADAPTER,
        os.path.join(script_dir, DEFAULT_ADAPTER_NAME),
    )
    if args.collector_sha256 is not None:
        check_dependency_sha(collector, args.collector_sha256)
    if args.adapter_sha256 is not None:
        check_dependency_sha(adapter, args.adapter_sha256)

    meta, raw_evidence = run_collector_stage(collector, args)
    result, digest = run_adapter_stage(adapter, args, raw_evidence)

    input_obj = meta["input"]
    turn_obj = meta["turn"]
    final_obj = meta["finalAssistant"]
    summary = {
        "provider": bounded_text(result["provider"], "unknown"),
        "model": bounded_text(result["model"], "unknown"),
        "turnId": bounded_text(result.get("turnId"), None),
        "evidenceSha256": digest,
        "inputStatus": bounded_text(input_obj.get("status"), None),
        "turnStatus": bounded_text(turn_obj.get("status"), None),
        "finalAssistantFound": final_obj.get("found") is True,
    }
    return {
        "observer": OBSERVER,
        "schemaVersion": SCHEMA_VERSION,
        "status": "OK",
        "sessionId": args.session_id,
        "inputId": args.input_id,
        "state": result["state"],
        "summary": summary,
        "flags": dict(FALSE_FLAGS),
        "error": None,
    }


def build_parser():
    parser = argparse.ArgumentParser(
        prog=OBSERVER,
        description=(
            "One-shot read-only collector->adapter observation of a ZCode GUI"
            " session binding; prints a single fixed-schema JSON object."
        ),
    )
    parser.add_argument(
        "--db", required=True,
        help="path to an existing ZCode SQLite database (never created or written)",
    )
    parser.add_argument("--session-id", required=True, help="exact session id to bind")
    parser.add_argument("--input-id", required=True, help="exact session_input id to bind")
    parser.add_argument(
        "--collector", default=None,
        help="collector script (default: sibling %s, override: %s)"
             % (DEFAULT_COLLECTOR_NAME, ENV_COLLECTOR),
    )
    parser.add_argument(
        "--adapter", default=None,
        help="adapter script (default: sibling %s, override: %s)"
             % (DEFAULT_ADAPTER_NAME, ENV_ADAPTER),
    )
    parser.add_argument(
        "--expect-provider", default=None,
        help="fail with PROVIDER_MISMATCH unless the observed provider matches",
    )
    parser.add_argument(
        "--expect-model", default=None,
        help="fail with MODEL_MISMATCH unless the observed model matches",
    )
    parser.add_argument(
        "--collector-sha256", default=None,
        help="require this SHA-256 for the collector script",
    )
    parser.add_argument(
        "--adapter-sha256", default=None,
        help="require this SHA-256 for the adapter script",
    )
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS,
        help="per-dependency subprocess timeout in seconds (%d-%d, default %d)"
             % (MIN_TIMEOUT_SECONDS, MAX_TIMEOUT_SECONDS, DEFAULT_TIMEOUT_SECONDS),
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        payload = observe(args)
    except ObservationError as exc:
        emit(error_payload(args.session_id, args.input_id, exc.code))
        return EXIT_ERROR
    emit(payload)
    return EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BrokenPipeError:
        sys.exit(EXIT_ERROR)
    except KeyboardInterrupt:
        sys.exit(EXIT_ERROR)
    except Exception:
        # Never leak tracebacks: they can contain paths or session data.
        try:
            emit(error_payload(None, None, ERR_INTERNAL))
        except Exception:
            pass
        sys.exit(EXIT_ERROR)
