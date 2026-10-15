#!/usr/bin/env python3
"""Map ZCode GUI collector metadata (schemaVersion 1) onto fixed PM monitor states.

Read-only cold-snapshot adapter: a single byte read (1 MiB cap), one SHA-256
digest, strict UTF-8/JSON/schema/type/binding/digest validation, then a fixed
state vocabulary. Collector-legal nullable scalars (turn.status/turnId null
when no turn exists) are accepted as "missing"; unknown fields are dropped.
completionEvidence is checked for consistency in BOTH directions against the
observed turn/final booleans, and READY_FOR_PM_REVIEW additionally requires a
promoted input plus an explicit complete=true. Conflicting input/turn/final
observations and fabricated completion collapse to EVIDENCE_CONFLICT. Output
carries binding IDs, digest, fixed states and constant-false flags only.
Never dispatches, supervises or claims live liveness. Stdlib only, 3.9+.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import stat
import sys

ADAPTER = "zcode-gui-monitor-adapter"
SCHEMA_VERSION = 1
MAX_EVIDENCE_BYTES = 1024 * 1024

STATE_INPUT_ACCEPTED = "INPUT_ACCEPTED"
STATE_INPUT_FAILED = "INPUT_FAILED"
STATE_TURN_UNKNOWN = "TURN_UNKNOWN"
STATE_TURN_RUNNING = "TURN_RUNNING"
STATE_TURN_ERROR = "TURN_ERROR"
STATE_TURN_CANCELLED = "TURN_CANCELLED"
STATE_DELIVERY_PENDING = "DELIVERY_PENDING"
STATE_DELIVERY_ERROR = "DELIVERY_ERROR"
STATE_READY_FOR_PM_REVIEW = "READY_FOR_PM_REVIEW"
STATE_EVIDENCE_CONFLICT = "EVIDENCE_CONFLICT"

ERR_EVIDENCE_UNREADABLE = "EVIDENCE_UNREADABLE"
ERR_EVIDENCE_TOO_LARGE = "EVIDENCE_TOO_LARGE"
ERR_EVIDENCE_NOT_UTF8 = "EVIDENCE_NOT_UTF8"
ERR_EVIDENCE_NOT_JSON = "EVIDENCE_NOT_JSON"
ERR_EVIDENCE_SCHEMA_UNSUPPORTED = "EVIDENCE_SCHEMA_UNSUPPORTED"
ERR_EVIDENCE_TYPE_INVALID = "EVIDENCE_TYPE_INVALID"
ERR_EVIDENCE_DIGEST_MISMATCH = "EVIDENCE_DIGEST_MISMATCH"
ERR_BINDING_MISMATCH = "BINDING_MISMATCH"
ERR_PROVIDER_MISMATCH = "PROVIDER_MISMATCH"
ERR_MODEL_MISMATCH = "MODEL_MISMATCH"

TURN_CONCRETE_STATUSES = ("running", "completed", "error", "cancelled")

FALSE_FLAGS = {
    "pmAccepted": False,
    "orcaSupervised": False,
    "livenessAuthoritative": False,
}


class Rejected(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def emit(payload):
    sys.stdout.write(json.dumps(payload, sort_keys=True, ensure_ascii=True) + "\n")


def fail(code):
    emit(
        {
            "adapter": ADAPTER,
            "schemaVersion": SCHEMA_VERSION,
            "error": code,
            "flags": dict(FALSE_FLAGS),
        }
    )
    raise SystemExit(2)


def is_bool(value):
    return isinstance(value, bool)


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def is_text(value):
    return isinstance(value, str)


def read_evidence(path):
    # One open, one read; a missing file is never created or written.
    try:
        with open(path, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise Rejected(ERR_EVIDENCE_UNREADABLE)
            if info.st_size > MAX_EVIDENCE_BYTES:
                raise Rejected(ERR_EVIDENCE_TOO_LARGE)
            raw = handle.read(MAX_EVIDENCE_BYTES + 1)
    except OSError:
        raise Rejected(ERR_EVIDENCE_UNREADABLE)
    if len(raw) > MAX_EVIDENCE_BYTES:
        raise Rejected(ERR_EVIDENCE_TOO_LARGE)
    return raw


def require_type(condition):
    if not condition:
        raise Rejected(ERR_EVIDENCE_TYPE_INVALID)


def parse_metadata(raw):
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise Rejected(ERR_EVIDENCE_NOT_UTF8)
    try:
        metadata = json.loads(text)
    except json.JSONDecodeError:
        raise Rejected(ERR_EVIDENCE_NOT_JSON)

    require_type(isinstance(metadata, dict))
    if not (is_int(metadata.get("schemaVersion")) and metadata["schemaVersion"] == SCHEMA_VERSION):
        raise Rejected(ERR_EVIDENCE_SCHEMA_UNSUPPORTED)
    require_type(is_text(metadata.get("sessionId")) and metadata["sessionId"] != "")
    require_type(is_text(metadata.get("inputId")) and metadata["inputId"] != "")

    def optional_object(key):
        value = metadata.get(key)
        if value is None:
            return {}
        require_type(isinstance(value, dict))
        return value

    def nullable_bool(obj, key):
        # Collector-legal null means "not observed"; only wrong non-null
        # types are rejected.
        if obj.get(key) is not None:
            require_type(is_bool(obj[key]))

    def nullable_text(obj, key):
        if obj.get(key) is not None:
            require_type(is_text(obj[key]))

    input_obj = optional_object("input")
    nullable_text(input_obj, "status")
    turn = optional_object("turn")
    nullable_bool(turn, "found")
    nullable_text(turn, "status")
    nullable_text(turn, "turnId")
    final = optional_object("finalAssistant")
    for key in ("found", "completed", "errorFree", "textAvailable"):
        nullable_bool(final, key)
    for key in ("providerId", "modelId"):
        nullable_text(final, key)
    completion = optional_object("completionEvidence")
    for key in (
        "complete",
        "turnCompleted",
        "finalAssistantCompleted",
        "finalAssistantErrorFree",
        "finalTextAvailable",
    ):
        nullable_bool(completion, key)
    return metadata, input_obj, turn, final, completion


def final_all_good(final):
    return (
        final.get("found") is True
        and final.get("completed") is True
        and final.get("errorFree") is True
        and final.get("textAvailable") is True
    )


def has_conflict(input_obj, turn, final, completion):
    """Bidirectional mismatch between stated and observed booleans.

    A key that is present (non-null) on both sides must agree in either
    direction; missing/null keys stay unknown and are never a conflict.
    """
    turn_found = turn.get("found") is True
    turn_status = turn.get("status")
    turn_done = turn_found and turn_status == "completed"
    final_good = final_all_good(final)
    observed_complete = turn_done and final_good

    # completionEvidence vs observation, both directions.
    stated_complete = completion.get("complete")
    if is_bool(stated_complete) and stated_complete is not observed_complete:
        return True
    stated_turn_done = completion.get("turnCompleted")
    if is_bool(stated_turn_done) and stated_turn_done is not turn_done:
        return True
    for ce_key, final_key in (
        ("finalAssistantCompleted", "completed"),
        ("finalAssistantErrorFree", "errorFree"),
        ("finalTextAvailable", "textAvailable"),
    ):
        stated = completion.get(ce_key)
        if is_bool(stated) and stated is not (final.get(final_key) is True):
            return True

    # finalAssistant cannot be not-found while claiming concrete booleans.
    if final.get("found") is False and any(
        final.get(key) is True for key in ("completed", "errorFree", "textAvailable")
    ):
        return True

    # turn cannot be absent while claiming a concrete status.
    if turn.get("found") is False and turn_status in TURN_CONCRETE_STATUSES:
        return True

    # A non-promoted input contradicts any concrete turn or final assistant.
    input_status = input_obj.get("status")
    if input_status in ("admitted", "failed") and (turn_found or final.get("found") is True):
        return True
    return False


def map_state(input_obj, turn, final, completion):
    input_status = input_obj.get("status")
    if input_status == "admitted":
        return STATE_INPUT_ACCEPTED
    if input_status == "failed":
        return STATE_INPUT_FAILED
    # Only a proven promoted input may reach the delivery gate; missing,
    # null or unknown statuses keep the whole snapshot TURN_UNKNOWN.
    if input_status != "promoted":
        return STATE_TURN_UNKNOWN
    if turn.get("found") is not True:
        return STATE_TURN_UNKNOWN
    turn_status = turn.get("status")
    if turn_status == "running":
        return STATE_TURN_RUNNING
    if turn_status == "error":
        return STATE_TURN_ERROR
    if turn_status == "cancelled":
        return STATE_TURN_CANCELLED
    if turn_status == "completed":
        if final.get("found") is True and final.get("errorFree") is False:
            return STATE_DELIVERY_ERROR
        # The review gate needs every observed boolean plus an explicit,
        # non-contradicted complete=true; missing pieces stay pending.
        if final_all_good(final) and completion.get("complete") is True:
            return STATE_READY_FOR_PM_REVIEW
        return STATE_DELIVERY_PENDING
    return STATE_TURN_UNKNOWN


def observed_identity(final, key):
    value = final.get(key)
    if is_text(value) and value:
        return value
    return "unknown"


def build_parser():
    parser = argparse.ArgumentParser(
        prog=ADAPTER,
        description="Read-only ZCode GUI evidence to fixed PM monitor state (cold snapshot).",
    )
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--input-id", required=True)
    parser.add_argument("--expected-evidence-sha256", default=None)
    parser.add_argument("--expected-provider", default=None)
    parser.add_argument("--expected-model", default=None)
    return parser


def main(argv):
    args = build_parser().parse_args(argv)

    expected_digest = args.expected_evidence_sha256
    if expected_digest is not None:
        expected_digest = expected_digest.strip().lower()
        if len(expected_digest) != 64 or any(c not in "0123456789abcdef" for c in expected_digest):
            fail(ERR_EVIDENCE_DIGEST_MISMATCH)

    try:
        raw = read_evidence(args.evidence)
    except Rejected as rejected:
        fail(rejected.code)

    digest = hashlib.sha256(raw).hexdigest()
    if expected_digest is not None and not hmac.compare_digest(digest, expected_digest):
        fail(ERR_EVIDENCE_DIGEST_MISMATCH)

    try:
        metadata, input_obj, turn, final, completion = parse_metadata(raw)
    except Rejected as rejected:
        fail(rejected.code)

    if metadata["sessionId"] != args.session_id or metadata["inputId"] != args.input_id:
        fail(ERR_BINDING_MISMATCH)

    provider = observed_identity(final, "providerId")
    model = observed_identity(final, "modelId")
    if args.expected_provider is not None and provider != args.expected_provider:
        fail(ERR_PROVIDER_MISMATCH)
    if args.expected_model is not None and model != args.expected_model:
        fail(ERR_MODEL_MISMATCH)

    if has_conflict(input_obj, turn, final, completion):
        state = STATE_EVIDENCE_CONFLICT
    else:
        state = map_state(input_obj, turn, final, completion)

    turn_id = turn.get("turnId")
    emit(
        {
            "adapter": ADAPTER,
            "schemaVersion": SCHEMA_VERSION,
            "sessionId": metadata["sessionId"],
            "inputId": metadata["inputId"],
            "turnId": turn_id if is_text(turn_id) and turn_id else None,
            "evidenceSha256": digest,
            "state": state,
            "provider": provider,
            "model": model,
            "flags": dict(FALSE_FLAGS),
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
