#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only ZCode session evidence collector.

Binds an exact (session_id, session_input.id) pair in an existing ZCode SQLite
database, follows session_input.promoted_message_id ->
turn_usage.user_message_id, and reports turn plus final-assistant completion
evidence as stable JSON.

Guarantees:
- The database is opened with SQLite URI mode=ro plus PRAGMA query_only and a
  single deferred read transaction. The collector never creates or writes the
  native database.
- Reasoning, tool input/output, session_input.payload, session_input free-text
  status_reason, credentials, the full database path and data from any other
  session are never emitted, with or without --include-final-text.
- A cold snapshot is not a real-time liveness authority: missing fields are
  never inferred as idle or completed.

Standard library only; supports Python 3.9+.
"""

import argparse
import json
import os
import sqlite3
import sys
from urllib.parse import quote

SCHEMA_VERSION = 1
EXIT_OK = 0
EXIT_ERROR = 1

KNOWN_INPUT_STATUSES = ("admitted", "promoted", "failed")
KNOWN_TURN_STATUSES = ("running", "completed", "error", "cancelled")

REQUIRED_TABLE_COLUMNS = {
    "session_input": frozenset({
        "id", "session_id", "status", "status_reason", "promoted_message_id",
    }),
    "turn_usage": frozenset({
        "session_id", "turn_id", "user_message_id", "status",
        "completed_at", "error_type", "cancelled_by_user",
    }),
    "message": frozenset({"id", "session_id", "data", "sequence"}),
    "part": frozenset({"id", "message_id", "session_id", "data", "sequence"}),
}


class EvidenceError(Exception):
    """Raised for every expected failure; rendered as a JSON error object."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def emit(payload, exit_code):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    sys.stdout.flush()
    return exit_code


def emit_error(code, message):
    return emit({"ok": False, "error": {"code": code, "message": message}}, EXIT_ERROR)


def open_readonly(db_path):
    if not db_path or not os.path.isfile(db_path):
        raise EvidenceError(
            "DB_NOT_FOUND",
            "database does not exist or is not a regular file; path withheld",
        )
    uri = "file:" + quote(os.path.abspath(db_path)) + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, isolation_level=None)
    except sqlite3.Error:
        raise EvidenceError("DB_OPEN_FAILED", "cannot open database read-only; details withheld")
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only = ON")
        conn.execute("BEGIN")
    except sqlite3.Error:
        conn.close()
        raise EvidenceError("DB_OPEN_FAILED", "cannot prepare the read-only snapshot; details withheld")
    return conn


def verify_schema(conn):
    for table, required in sorted(REQUIRED_TABLE_COLUMNS.items()):
        try:
            rows = conn.execute("PRAGMA table_info(%s)" % table).fetchall()
        except sqlite3.Error:
            raise EvidenceError("READ_ERROR", "cannot inspect the database schema; details withheld")
        if not rows:
            raise EvidenceError("DB_SCHEMA_INVALID", "missing required table: %s" % table)
        present = {row["name"] for row in rows}
        missing = sorted(required - present)
        if missing:
            raise EvidenceError(
                "DB_SCHEMA_INVALID",
                "table %s is missing column(s): %s" % (table, ", ".join(missing)),
            )


def parse_json(raw, kind, row_id):
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        raise EvidenceError("JSON_MALFORMED", "malformed JSON in %s data (id=%s)" % (kind, row_id))


def text_or_unknown(value):
    if value is None:
        return "unknown"
    text = str(value).strip()
    return text if text else "unknown"


def normalize_input_status(status):
    raw = (status or "").strip().lower()
    return raw if raw in KNOWN_INPUT_STATUSES else "unknown"


def normalize_turn_status(status):
    # Only the native turn_usage.status column classifies a turn. Absent or
    # unknown values stay "unknown" and are never promoted to running,
    # completed, error or cancelled from any other field.
    raw = (status or "").strip().lower()
    return raw if raw in KNOWN_TURN_STATUSES else "unknown"


def collect(conn, session_id, input_id, include_final_text):
    verify_schema(conn)

    try:
        binding = conn.execute(
            "SELECT id, session_id, status, status_reason, promoted_message_id"
            " FROM session_input WHERE id = ? AND session_id = ?",
            (input_id, session_id),
        ).fetchall()
    except sqlite3.Error:
        raise EvidenceError("READ_ERROR", "cannot read session_input; details withheld")
    if not binding:
        raise EvidenceError(
            "INPUT_NOT_FOUND",
            "no session_input row matches the given (session_id, input_id) binding",
        )
    if len(binding) > 1:
        raise EvidenceError(
            "INPUT_AMBIGUOUS",
            "multiple session_input rows match the binding; refusing to disambiguate",
        )
    bound = binding[0]

    result = {
        "ok": True,
        "schemaVersion": SCHEMA_VERSION,
        "sessionId": session_id,
        "inputId": input_id,
        "input": {
            "status": normalize_input_status(bound["status"]),
            # status_reason is native free text and may embed paths or
            # credentials, so only its presence is reported, never its content.
            "reasonPresent": bool(
                bound["status_reason"] is not None and str(bound["status_reason"]).strip()
            ),
            "promotedMessageId": bound["promoted_message_id"],
        },
        "turn": {"found": False, "turnId": None, "status": None},
        "finalAssistant": {
            "found": False,
            "messageId": None,
            "completed": False,
            "errorFree": False,
            "textAvailable": False,
            "textLength": 0,
            "providerId": "unknown",
            "modelId": "unknown",
            "mode": "unknown",
        },
        "completionEvidence": {
            "turnCompleted": False,
            "finalAssistantCompleted": False,
            "finalAssistantErrorFree": False,
            "finalTextAvailable": False,
            "complete": False,
        },
        "liveness": {
            "authoritative": False,
            "note": "Cold read-only snapshot; missing fields are never inferred as idle or completed.",
        },
    }

    promoted = bound["promoted_message_id"]

    turn_id = None
    turn_status = None
    if promoted:
        try:
            turns = conn.execute(
                "SELECT turn_id, status FROM turn_usage"
                " WHERE session_id = ? AND user_message_id = ?",
                (session_id, promoted),
            ).fetchall()
        except sqlite3.Error:
            raise EvidenceError("READ_ERROR", "cannot read turn_usage; details withheld")
        if len(turns) > 1:
            raise EvidenceError(
                "TURN_AMBIGUOUS",
                "multiple turn_usage rows reference the promoted message; refusing to disambiguate",
            )
        if len(turns) == 1:
            turn_id = turns[0]["turn_id"]
            turn_status = normalize_turn_status(turns[0]["status"])
            result["turn"] = {"found": True, "turnId": turn_id, "status": turn_status}

    candidates = []
    if promoted:
        try:
            messages = conn.execute(
                "SELECT id, data, sequence FROM message WHERE session_id = ? ORDER BY sequence",
                (session_id,),
            ).fetchall()
        except sqlite3.Error:
            raise EvidenceError("READ_ERROR", "cannot read message; details withheld")
        for row in messages:
            data = parse_json(row["data"], "message", row["id"])
            if not isinstance(data, dict):
                continue
            if str(data.get("role", "")).strip().lower() != "assistant":
                continue
            parent = data.get("parentID", data.get("parentId"))
            if parent != promoted:
                continue
            candidates.append((row, data))

    sequences = []
    for row, _data in candidates:
        seq = row["sequence"]
        # Without a unique numeric sequence there is no defensible "latest";
        # ties, NULL or non-numeric values must never be resolved by row order.
        if seq is None or isinstance(seq, bool) or not isinstance(seq, (int, float)):
            raise EvidenceError(
                "ASSISTANT_AMBIGUOUS",
                "assistant candidates for the promoted message have a missing or"
                " non-numeric sequence; refusing to pick one arbitrarily",
            )
        sequences.append(seq)
    if len(candidates) > 1:
        top = max(sequences)
        if sequences.count(top) > 1:
            raise EvidenceError(
                "ASSISTANT_AMBIGUOUS",
                "multiple assistant messages share the maximum sequence for the"
                " promoted message; refusing to pick one arbitrarily",
            )

    assistant = candidates[-1][0] if candidates else None
    assistant_data = candidates[-1][1] if candidates else None

    final_text = ""
    if assistant is not None:
        time_obj = assistant_data.get("time")
        completed = bool(isinstance(time_obj, dict) and time_obj.get("completed"))
        error_free = not assistant_data.get("error")
        try:
            parts = conn.execute(
                "SELECT id, data, sequence FROM part"
                " WHERE session_id = ? AND message_id = ? ORDER BY sequence",
                (session_id, assistant["id"]),
            ).fetchall()
        except sqlite3.Error:
            raise EvidenceError("READ_ERROR", "cannot read part; details withheld")
        chunks = []
        for prow in parts:
            pdata = parse_json(prow["data"], "part", prow["id"])
            if not isinstance(pdata, dict):
                continue
            if str(pdata.get("type", "")).strip().lower() != "text":
                continue  # reasoning/tool/... parts stay unread and unemitted
            text = pdata.get("text")
            if isinstance(text, str) and text:
                chunks.append(text)
        final_text = "\n".join(chunks)
        has_text = bool(final_text.strip())
        result["finalAssistant"] = {
            "found": True,
            "messageId": assistant["id"],
            "completed": completed,
            "errorFree": error_free,
            "textAvailable": has_text,
            "textLength": len(final_text),
            "providerId": text_or_unknown(assistant_data.get("providerId", assistant_data.get("providerID"))),
            "modelId": text_or_unknown(assistant_data.get("modelId", assistant_data.get("modelID"))),
            "mode": text_or_unknown(assistant_data.get("mode")),
        }
        if include_final_text:
            result["finalAssistant"]["text"] = final_text if has_text else None

    evidence = result["completionEvidence"]
    evidence["turnCompleted"] = turn_status == "completed"
    evidence["finalAssistantCompleted"] = result["finalAssistant"]["completed"]
    evidence["finalAssistantErrorFree"] = result["finalAssistant"]["errorFree"]
    evidence["finalTextAvailable"] = result["finalAssistant"]["textAvailable"]
    evidence["complete"] = bool(
        result["turn"]["found"]
        and evidence["turnCompleted"]
        and result["finalAssistant"]["found"]
        and evidence["finalAssistantCompleted"]
        and evidence["finalAssistantErrorFree"]
        and evidence["finalTextAvailable"]
    )
    return result


def build_parser():
    parser = argparse.ArgumentParser(
        prog="zcode-session-evidence",
        description="Read-only ZCode session evidence collector emitting stable JSON.",
    )
    parser.add_argument(
        "--db", required=True,
        help="path to an existing ZCode SQLite database (opened read-only; never created)",
    )
    parser.add_argument("--session-id", required=True, help="exact session id to bind")
    parser.add_argument("--input-id", required=True, help="exact session_input id to bind")
    parser.add_argument(
        "--include-final-text", action="store_true",
        help="include the final assistant text (metadata-only by default)",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    conn = None
    try:
        conn = open_readonly(args.db)
    except EvidenceError as exc:
        return emit_error(exc.code, exc.message)
    try:
        return emit(collect(conn, args.session_id, args.input_id, args.include_final_text), EXIT_OK)
    except EvidenceError as exc:
        return emit_error(exc.code, exc.message)
    except sqlite3.Error:
        return emit_error("READ_ERROR", "database read failed; details withheld")
    finally:
        if conn is not None:
            conn.close()


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
            emit_error("INTERNAL_ERROR", "unexpected internal error; details withheld")
        except Exception:
            pass
        sys.exit(EXIT_ERROR)
