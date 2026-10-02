#!/usr/bin/env python3
"""Map ZCode GUI collector metadata (schemaVersion 1) onto fixed PM monitor states.

Read-only cold-snapshot adapter: a single byte read (1 MiB cap), one SHA-256
digest, strict UTF-8/JSON/schema/type/binding/digest validation, then a fixed
state vocabulary. Unknown fields are dropped; output carries binding IDs,
digest, fixed states and constant-false flags only. Never dispatches,
supervises or claims live liveness. Stdlib only, Python 3.9+.
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

    def bool_field(obj, key):
        if key in obj:
            require_type(is_bool(obj[key]))

    input_obj = optional_object("input")
    if "status" in input_obj:
        require_type(is_text(input_obj["status"]))
    turn = optional_object("turn")
    bool_field(turn, "found")
    if "status" in turn:
        require_type(is_text(turn["status"]))
    if "turnId" in turn:
        require_type(is_text(turn["turnId"]))
    final = optional_object("finalAssistant")
    for key in ("found", "completed", "errorFree", "textAvailable"):
        bool_field(final, key)
    for key in ("providerId", "modelId"):
        if key in final:
            require_type(is_text(final[key]))
    completion = optional_object("completionEvidence")
    for key in (
        "complete",
        "turnCompleted",
        "finalAssistantCompleted",
        "finalAssistantErrorFree",
        "finalTextAvailable",
    ):
        bool_field(completion, key)
    return metadata, input_obj, turn, final, completion


def has_conflict(turn, final, completion):
    """Over-claim detection only; missing fields are never a conflict."""
    turn_found = turn.get("found") is True
    turn_status = turn.get("status")
    turn_done = turn_found and turn_status == "completed"
    final_found = final.get("found") is True
    final_completed = final.get("completed") is True
    final_error_free = final.get("errorFree") is True
    final_text = final.get("textAvailable") is True
    final_all_good = final_found and final_completed and final_error_free and final_text
    observed_complete = turn_done and final_all_good

    def over_claims(key, observed):
        return completion.get(key) is True and not observed

    if over_claims("complete", observed_complete):
        return True
    if over_claims("turnCompleted", turn_done):
        return True
    if over_claims("finalAssistantCompleted", final_completed):
        return True
    if over_claims("finalAssistantErrorFree", final_error_free):
        return True
    if over_claims("finalTextAvailable", final_text):
        return True
    if final_found and not turn_found:
        return True
    if turn.get("found") is False and turn_status in TURN_CONCRETE_STATUSES:
        return True
    return False


def map_state(input_obj, turn, final):
    input_status = input_obj.get("status")
    if input_status == "admitted":
        return STATE_INPUT_ACCEPTED
    if input_status == "failed":
        return STATE_INPUT_FAILED
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
        final_completed = final.get("completed") is True
        final_error_free = final.get("errorFree") is True
        final_text = final.get("textAvailable") is True
        if final.get("found") is True and final_completed and final_error_free and final_text:
            return STATE_READY_FOR_PM_REVIEW
        if final.get("found") is True and final.get("errorFree") is False:
            return STATE_DELIVERY_ERROR
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

    if has_conflict(turn, final, completion):
        state = STATE_EVIDENCE_CONFLICT
    else:
        state = map_state(input_obj, turn, final)

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
