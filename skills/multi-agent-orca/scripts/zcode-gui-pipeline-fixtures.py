#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Synthetic ZCode session SQLite fixtures for the GUI evidence pipeline suite.

Every named case builds a fresh, self-contained synthetic database whose schema
carries the required columns of the read-only collector
(zcode-session-evidence.py). All row content is synthetic; canary tokens and a
decoy session are planted so the integration runner can prove that neither the
collector nor the adapter leaks reasoning/tool/status_reason text, content of
other sessions, or any real user data.

Standard library only; supports Python 3.9+.

CLI:
    python3 zcode-gui-pipeline-fixtures.py --list
    python3 zcode-gui-pipeline-fixtures.py --case admitted_no_turn --out /tmp/case.sqlite
"""

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple

# Synthetic identity constants (never real session data).
FIXTURE_PROVIDER = "prov-fixture"
FIXTURE_MODEL = "model-fixture"
FIXTURE_MODE = "build"
FINAL_TEXT_OK = "Fixture final answer: pipeline verified."

# Plant tokens used by the runner to prove nothing leaks into stdout metadata.
CANARY_STATUS_REASON = "CANARY-STATUS-REASON-7f3a2c"
CANARY_REASONING = "CANARY-REASONING-9d21b4"
CANARY_TOOL = "CANARY-TOOL-5b8e10"
CANARY_DECOY_TEXT = "CANARY-DECOY-TEXT-3c7f96"
ALL_CANARY_TOKENS = (
    CANARY_STATUS_REASON,
    CANARY_REASONING,
    CANARY_TOOL,
    CANARY_DECOY_TEXT,
)

# A second, fully populated synthetic session planted in every database; the
# runner asserts its ids/text never surface in collector or adapter output.
DECOY_SESSION_ID = "sess-decoy-other-session"
DECOY_TURN_ID = "turn-decoy-999"

BASE_SCHEMA = """
CREATE TABLE session_input (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    status TEXT,
    status_reason TEXT,
    promoted_message_id TEXT
);
CREATE TABLE turn_usage (
    session_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    user_message_id TEXT,
    status TEXT,
    completed_at TEXT,
    error_type TEXT,
    cancelled_by_user INTEGER DEFAULT 0
);
CREATE TABLE message (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    data TEXT,
    sequence INTEGER
);
CREATE TABLE part (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    data TEXT,
    sequence INTEGER
);
"""

# Collector requires every table; dropping one must be reported as invalid.
REDUCED_SCHEMA = """
CREATE TABLE session_input (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    status TEXT,
    status_reason TEXT,
    promoted_message_id TEXT
);
CREATE TABLE turn_usage (
    session_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    user_message_id TEXT,
    status TEXT,
    completed_at TEXT,
    error_type TEXT,
    cancelled_by_user INTEGER DEFAULT 0
);
CREATE TABLE message (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    data TEXT,
    sequence INTEGER
);
"""


@dataclass
class CaseSpec:
    """Executable expectation for one collector->adapter combination."""

    name: str
    session_id: str
    description: str = ""
    input_id: str = "input-001"
    # Collector stage expectations.
    collector_input_id: Optional[str] = None
    collector_exit: int = 0
    collector_error: Optional[str] = None
    collector_expect: Dict[str, Any] = field(default_factory=dict)
    # Adapter stage expectations; adapter_exit=None skips the adapter stage.
    adapter_session_id: Optional[str] = None
    adapter_input_id: Optional[str] = None
    adapter_args: Tuple[str, ...] = ()
    adapter_exit: Optional[int] = 0
    adapter_state: Optional[str] = None
    adapter_error: Optional[str] = None
    adapter_expect: Dict[str, Any] = field(default_factory=dict)
    # Extra collector pass with --include-final-text (leak-scan surface).
    include_final_text_pass: bool = False
    # Share the database of another case (binding/digest negative variants).
    reuses_db_of: Optional[str] = None
    # Historical initial-adapter negative control (expected old-defect reject).
    legacy_control: bool = False


BUILDERS: Dict[str, Callable[[sqlite3.Connection, str], None]] = {}


def case_builder(fn):
    """Register build_<name> as the database builder for case <name>."""
    BUILDERS[fn.__name__[len("build_"):]] = fn
    return fn


def _insert_input(conn, sid, iid, status, promoted=None, status_reason=None):
    conn.execute(
        "INSERT INTO session_input (id, session_id, status, status_reason,"
        " promoted_message_id) VALUES (?, ?, ?, ?, ?)",
        (iid, sid, status, status_reason, promoted),
    )


def _insert_turn(conn, sid, turn_id, user_message_id, status,
                 completed_at=None, error_type=None, cancelled_by_user=0):
    conn.execute(
        "INSERT INTO turn_usage (session_id, turn_id, user_message_id, status,"
        " completed_at, error_type, cancelled_by_user) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (sid, turn_id, user_message_id, status, completed_at, error_type,
         cancelled_by_user),
    )


def _insert_message(conn, sid, mid, data, seq):
    raw = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    conn.execute(
        "INSERT INTO message (id, session_id, data, sequence) VALUES (?, ?, ?, ?)",
        (mid, sid, raw, seq),
    )


def _insert_part(conn, sid, mid, pid, data, seq):
    raw = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    conn.execute(
        "INSERT INTO part (id, message_id, session_id, data, sequence)"
        " VALUES (?, ?, ?, ?, ?)",
        (pid, mid, sid, raw, seq),
    )


def _assistant_data(parent, completed=False, error=None, provider=FIXTURE_PROVIDER,
                    model=FIXTURE_MODEL, mode=FIXTURE_MODE):
    data = {"role": "assistant", "parentID": parent}
    if completed:
        data["time"] = {"completed": "2026-10-03T09:00:00Z"}
    if error is not None:
        data["error"] = error
    if provider is not None:
        data["providerId"] = provider
    if model is not None:
        data["modelId"] = model
    if mode is not None:
        data["mode"] = mode
    return data


def _add_user_message(conn, sid, mid="msg-user-001", seq=10):
    _insert_message(conn, sid, mid, {"role": "user", "text": "synthetic user prompt"}, seq)


def _add_assistant(conn, sid, mid, seq, parent="msg-user-001", text=None, parts=(),
                   **kwargs):
    _insert_message(conn, sid, mid, _assistant_data(parent, **kwargs), seq)
    if text is not None:
        _insert_part(conn, sid, mid, mid + "-text", {"type": "text", "text": text}, 10)
    for offset, pdata in enumerate(parts, start=20):
        _insert_part(conn, sid, mid, "%s-part-%d" % (mid, offset), pdata, offset)


def _add_decoy(conn, decoy_text="decoy session final answer text"):
    """Plant a completed second session that must never surface in output."""
    _insert_input(conn, DECOY_SESSION_ID, "input-decoy-1", "promoted", "msg-decoy-user")
    _insert_turn(conn, DECOY_SESSION_ID, DECOY_TURN_ID, "msg-decoy-user", "completed",
                 completed_at="2026-10-03T08:00:00Z")
    _insert_message(conn, DECOY_SESSION_ID, "msg-decoy-user",
                    {"role": "user", "text": "decoy prompt"}, 10)
    _insert_message(conn, DECOY_SESSION_ID, "msg-decoy-asst",
                    _assistant_data("msg-decoy-user", completed=True), 20)
    _insert_part(conn, DECOY_SESSION_ID, "msg-decoy-asst", "msg-decoy-asst-text",
                 {"type": "text", "text": decoy_text}, 10)


def _completed_turn(conn, sid, turn_id="turn-done"):
    _insert_turn(conn, sid, turn_id, "msg-user-001", "completed",
                 completed_at="2026-10-03T09:01:00Z")


def _promoted_input(conn, sid, iid="input-001", status="promoted",
                    promoted="msg-user-001", status_reason=None):
    _insert_input(conn, sid, iid, status, promoted, status_reason)


# ---------------------------------------------------------------------------
# Named case builders. Each builds one independent synthetic database.
# ---------------------------------------------------------------------------


@case_builder
def build_admitted_no_turn(conn, sid):
    _promoted_input(conn, sid, status="admitted", promoted=None)
    _add_user_message(conn, sid)
    _add_decoy(conn)


@case_builder
def build_promoted_no_turn(conn, sid):
    _promoted_input(conn, sid)
    _add_user_message(conn, sid)
    _add_decoy(conn)


@case_builder
def build_turn_running(conn, sid):
    _promoted_input(conn, sid)
    _add_user_message(conn, sid)
    _insert_turn(conn, sid, "turn-running", "msg-user-001", "running")
    _add_assistant(conn, sid, "msg-asst-1", 20, completed=False, parts=[
        {"type": "reasoning", "text": "synthetic in-flight reasoning, no secrets"},
    ])
    _add_decoy(conn)


@case_builder
def build_completed_ready_for_review(conn, sid):
    _promoted_input(conn, sid)
    _add_user_message(conn, sid)
    _completed_turn(conn, sid)
    _add_assistant(conn, sid, "msg-asst-done", 20, completed=True, text=FINAL_TEXT_OK)
    _add_decoy(conn)


@case_builder
def build_completed_latest_error_wins(conn, sid):
    _promoted_input(conn, sid)
    _add_user_message(conn, sid)
    _completed_turn(conn, sid)
    _add_assistant(conn, sid, "msg-asst-early", 10, completed=True,
                   text="earlier successful answer (must be overridden)")
    _add_assistant(conn, sid, "msg-asst-latest", 20, completed=False,
                   error={"code": "synthetic_error", "message": "synthetic failure"},
                   text="partial text before synthetic failure")
    _add_decoy(conn)


@case_builder
def build_turn_cancelled(conn, sid):
    _promoted_input(conn, sid)
    _add_user_message(conn, sid)
    _insert_turn(conn, sid, "turn-cancelled", "msg-user-001", "cancelled",
                 cancelled_by_user=1)
    _add_assistant(conn, sid, "msg-asst-1", 20, completed=False, parts=[
        {"type": "reasoning", "text": "synthetic cancelled-turn reasoning"},
    ])
    _add_decoy(conn)


@case_builder
def build_turn_error(conn, sid):
    _promoted_input(conn, sid)
    _add_user_message(conn, sid)
    _insert_turn(conn, sid, "turn-err", "msg-user-001", "error",
                 error_type="synthetic-provider-error")
    _add_decoy(conn)


@case_builder
def build_provider_missing_unknown_ok(conn, sid):
    _promoted_input(conn, sid)
    _add_user_message(conn, sid)
    _completed_turn(conn, sid)
    _add_assistant(conn, sid, "msg-asst-done", 20, completed=True,
                   provider=None, model=None, text=FINAL_TEXT_OK)
    _add_decoy(conn)


@case_builder
def build_expected_provider_mismatch(conn, sid):
    _promoted_input(conn, sid)
    _add_user_message(conn, sid)
    _completed_turn(conn, sid)
    _add_assistant(conn, sid, "msg-asst-done", 20, completed=True, text=FINAL_TEXT_OK)
    _add_decoy(conn)


@case_builder
def build_collector_input_not_found(conn, sid):
    build_completed_ready_for_review(conn, sid)


@case_builder
def build_adapter_binding_mismatch(conn, sid):
    build_completed_ready_for_review(conn, sid)


@case_builder
def build_multi_turn_ambiguous(conn, sid):
    _promoted_input(conn, sid)
    _add_user_message(conn, sid)
    _insert_turn(conn, sid, "turn-a", "msg-user-001", "completed",
                 completed_at="2026-10-03T09:01:00Z")
    _insert_turn(conn, sid, "turn-b", "msg-user-001", "completed",
                 completed_at="2026-10-03T09:02:00Z")
    _add_assistant(conn, sid, "msg-asst-done", 20, completed=True, text=FINAL_TEXT_OK)
    _add_decoy(conn)


@case_builder
def build_assistant_sequence_ambiguous(conn, sid):
    _promoted_input(conn, sid)
    _add_user_message(conn, sid)
    _completed_turn(conn, sid)
    _add_assistant(conn, sid, "msg-asst-tie-a", 20, completed=True, text=FINAL_TEXT_OK)
    _add_assistant(conn, sid, "msg-asst-tie-b", 20, completed=False,
                   text="tied-sequence sibling (no defensible latest)")
    _add_decoy(conn)


@case_builder
def build_bad_schema_missing_table(conn, sid):
    _insert_input(conn, sid, "input-001", "promoted", "msg-user-001")
    _add_user_message(conn, sid)
    _insert_turn(conn, sid, "turn-done", "msg-user-001", "completed",
                 completed_at="2026-10-03T09:01:00Z")
    _insert_message(conn, sid, "msg-asst-done",
                    _assistant_data("msg-user-001", completed=True), 20)


@case_builder
def build_bad_json_message_data(conn, sid):
    _promoted_input(conn, sid)
    _add_user_message(conn, sid)
    _completed_turn(conn, sid)
    _insert_message(conn, sid, "msg-asst-broken",
                    '{"role": "assistant", "parentID": broken', 20)
    _add_decoy(conn)


@case_builder
def build_canary_containment(conn, sid):
    _promoted_input(conn, sid, status_reason=CANARY_STATUS_REASON)
    _add_user_message(conn, sid)
    _completed_turn(conn, sid)
    _add_assistant(conn, sid, "msg-asst-done", 20, completed=True,
                   text="Fixture final answer with normal content.", parts=[
                       {"type": "reasoning", "text": CANARY_REASONING},
                       {"type": "tool", "tool": "read_file",
                        "state": {"input": CANARY_TOOL, "output": CANARY_TOOL}},
                   ])
    _add_decoy(conn, decoy_text=CANARY_DECOY_TEXT)


@case_builder
def build_digest_mismatch(conn, sid):
    build_completed_ready_for_review(conn, sid)


@case_builder
def build_legacy_nullable_negative_control(conn, sid):
    build_admitted_no_turn(conn, sid)


# ---------------------------------------------------------------------------
# Case registry: executable expectations paired with the builders above.
# ---------------------------------------------------------------------------


def _sid(name):
    return "sess-fix-%s" % name.replace("_", "-")


def _case(name, description, **kwargs):
    kwargs.setdefault("session_id", _sid(name))
    kwargs.setdefault("description", description)
    return CaseSpec(name=name, **kwargs)


def _build_cases():
    cases = {}

    cases["admitted_no_turn"] = _case(
        "admitted_no_turn",
        "admitted input without any turn must map to INPUT_ACCEPTED, never to a"
        " delivery state",
        collector_expect={
            "ok": True,
            "input.status": "admitted",
            "input.reasonPresent": False,
            "input.promotedMessageId": None,
            "turn.found": False,
            "turn.status": None,
            "finalAssistant.found": False,
            "completionEvidence.complete": False,
        },
        adapter_state="INPUT_ACCEPTED",
        adapter_expect={"provider": "unknown", "model": "unknown"},
    )

    cases["promoted_no_turn"] = _case(
        "promoted_no_turn",
        "promoted input whose turn never started stays TURN_UNKNOWN",
        collector_expect={
            "ok": True,
            "input.status": "promoted",
            "turn.found": False,
            "finalAssistant.found": False,
            "completionEvidence.complete": False,
        },
        adapter_state="TURN_UNKNOWN",
    )

    cases["turn_running"] = _case(
        "turn_running",
        "running turn with a partial assistant maps to TURN_RUNNING",
        collector_expect={
            "ok": True,
            "turn.found": True,
            "turn.turnId": "turn-running",
            "turn.status": "running",
            "finalAssistant.found": True,
            "finalAssistant.completed": False,
            "finalAssistant.textAvailable": False,
            "finalAssistant.providerId": FIXTURE_PROVIDER,
            "completionEvidence.turnCompleted": False,
            "completionEvidence.complete": False,
        },
        adapter_state="TURN_RUNNING",
        adapter_expect={"turnId": "turn-running"},
    )

    cases["completed_ready_for_review"] = _case(
        "completed_ready_for_review",
        "completed turn plus a complete error-free assistant reaches"
        " READY_FOR_PM_REVIEW; digest/provider/model expectations hold",
        collector_expect={
            "ok": True,
            "turn.status": "completed",
            "finalAssistant.completed": True,
            "finalAssistant.errorFree": True,
            "finalAssistant.textAvailable": True,
            "finalAssistant.textLength": len(FINAL_TEXT_OK),
            "finalAssistant.providerId": FIXTURE_PROVIDER,
            "finalAssistant.modelId": FIXTURE_MODEL,
            "completionEvidence.complete": True,
        },
        adapter_args=(
            "--expected-evidence-sha256", "{evidence_sha256}",
            "--expected-provider", FIXTURE_PROVIDER,
            "--expected-model", FIXTURE_MODEL,
        ),
        adapter_state="READY_FOR_PM_REVIEW",
    )

    cases["completed_latest_error_wins"] = _case(
        "completed_latest_error_wins",
        "completed turn whose latest assistant errored maps to DELIVERY_ERROR;"
        " the earlier successful assistant must not override it",
        collector_expect={
            "ok": True,
            "finalAssistant.messageId": "msg-asst-latest",
            "finalAssistant.completed": False,
            "finalAssistant.errorFree": False,
            "finalAssistant.textAvailable": True,
            "finalAssistant.textLength": len("partial text before synthetic failure"),
            "completionEvidence.complete": False,
        },
        adapter_state="DELIVERY_ERROR",
    )

    cases["turn_cancelled"] = _case(
        "turn_cancelled",
        "user-cancelled turn maps to TURN_CANCELLED",
        collector_expect={
            "ok": True,
            "turn.status": "cancelled",
            "completionEvidence.turnCompleted": False,
            "completionEvidence.complete": False,
        },
        adapter_state="TURN_CANCELLED",
    )

    cases["turn_error"] = _case(
        "turn_error",
        "errored turn without an assistant maps to TURN_ERROR",
        collector_expect={
            "ok": True,
            "turn.status": "error",
            "finalAssistant.found": False,
            "completionEvidence.complete": False,
        },
        adapter_state="TURN_ERROR",
    )

    cases["provider_missing_unknown_ok"] = _case(
        "provider_missing_unknown_ok",
        "missing provider/model identity stays 'unknown' and must not block the"
        " review gate",
        collector_expect={
            "ok": True,
            "finalAssistant.providerId": "unknown",
            "finalAssistant.modelId": "unknown",
            "completionEvidence.complete": True,
        },
        adapter_state="READY_FOR_PM_REVIEW",
        adapter_expect={"provider": "unknown", "model": "unknown"},
    )

    cases["expected_provider_mismatch"] = _case(
        "expected_provider_mismatch",
        "a wrong expected provider is rejected with PROVIDER_MISMATCH",
        collector_expect={"ok": True, "completionEvidence.complete": True},
        adapter_args=("--expected-provider", "prov-other"),
        adapter_exit=2,
        adapter_error="PROVIDER_MISMATCH",
    )

    cases["collector_input_not_found"] = _case(
        "collector_input_not_found",
        "wrong input binding is rejected by the collector with INPUT_NOT_FOUND",
        collector_input_id="input-does-not-exist",
        collector_exit=1,
        collector_error="INPUT_NOT_FOUND",
        adapter_exit=None,
    )

    cases["adapter_binding_mismatch"] = _case(
        "adapter_binding_mismatch",
        "metadata bound to another session id is rejected with BINDING_MISMATCH",
        collector_expect={"ok": True, "completionEvidence.complete": True},
        adapter_session_id="sess-wrong-binding",
        adapter_exit=2,
        adapter_error="BINDING_MISMATCH",
    )

    cases["multi_turn_ambiguous"] = _case(
        "multi_turn_ambiguous",
        "two turn_usage rows on one promoted message refuse to disambiguate",
        collector_exit=1,
        collector_error="TURN_AMBIGUOUS",
        adapter_exit=None,
    )

    cases["assistant_sequence_ambiguous"] = _case(
        "assistant_sequence_ambiguous",
        "tied maximum assistant sequence refuses to pick a latest message",
        collector_exit=1,
        collector_error="ASSISTANT_AMBIGUOUS",
        adapter_exit=None,
    )

    cases["bad_schema_missing_table"] = _case(
        "bad_schema_missing_table",
        "a database without the part table is reported DB_SCHEMA_INVALID",
        collector_exit=1,
        collector_error="DB_SCHEMA_INVALID",
        adapter_exit=None,
    )

    cases["bad_json_message_data"] = _case(
        "bad_json_message_data",
        "malformed message JSON is reported JSON_MALFORMED, never parsed",
        collector_exit=1,
        collector_error="JSON_MALFORMED",
        adapter_exit=None,
    )

    cases["canary_containment"] = _case(
        "canary_containment",
        "planted canaries in status_reason/reasoning/tool parts and a decoy"
        " session must not surface, with and without --include-final-text",
        collector_expect={
            "ok": True,
            "input.reasonPresent": True,
            "completionEvidence.complete": True,
        },
        adapter_state="READY_FOR_PM_REVIEW",
        include_final_text_pass=True,
    )

    cases["digest_mismatch"] = _case(
        "digest_mismatch",
        "a stale expected digest is rejected with EVIDENCE_DIGEST_MISMATCH",
        collector_expect={"ok": True},
        adapter_args=("--expected-evidence-sha256", "0" * 64),
        adapter_exit=2,
        adapter_error="EVIDENCE_DIGEST_MISMATCH",
    )

    cases["legacy_nullable_negative_control"] = _case(
        "legacy_nullable_negative_control",
        "negative control: the historical initial adapter must reject the"
        " collector-legal null turn scalars (old defect), while the fixed"
        " adapter accepts the same evidence",
        reuses_db_of="admitted_no_turn",
        collector_expect={
            "ok": True,
            "input.status": "admitted",
            "turn.found": False,
            "turn.status": None,
        },
        adapter_state="INPUT_ACCEPTED",
        legacy_control=True,
    )

    return cases


CASES = _build_cases()
CASE_NAMES = tuple(CASES)


def schema_for(name):
    spec = CASES[name]
    if name == "bad_schema_missing_table":
        return REDUCED_SCHEMA
    return BASE_SCHEMA


def build_case(name, db_path):
    """Materialize one named case as an independent SQLite database."""
    if name not in CASES:
        raise KeyError("unknown fixture case: %s" % name)
    spec = CASES[name]
    db_path = os.path.abspath(db_path)
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(schema_for(name))
        BUILDERS[name](conn, spec.session_id)
        conn.commit()
    finally:
        conn.close()
    return spec


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="zcode-gui-pipeline-fixtures",
        description="Build synthetic ZCode session SQLite fixtures (stdlib only).",
    )
    parser.add_argument("--list", action="store_true", help="list named cases")
    parser.add_argument("--case", help="case name to materialize")
    parser.add_argument("--out", help="output SQLite path for --case")
    args = parser.parse_args(argv)

    if args.list:
        for name in CASE_NAMES:
            print("%s: %s" % (name, CASES[name].description))
        return 0
    if args.case:
        if not args.out:
            parser.error("--case requires --out")
        spec = build_case(args.case, args.out)
        print(json.dumps({
            "case": spec.name,
            "database": os.path.abspath(args.out),
            "sessionId": spec.session_id,
            "inputId": spec.input_id,
        }, sort_keys=True))
        return 0
    parser.print_usage()
    return 2


if __name__ == "__main__":
    sys.exit(main())
