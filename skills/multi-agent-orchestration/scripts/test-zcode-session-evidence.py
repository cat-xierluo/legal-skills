#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for zcode-session-evidence.py.

Builds synthetic SQLite fixtures in a temp directory and drives the real CLI
via subprocess; never touches a live ZCode database. Run with:

    python3 skills/multi-agent-orchestration/scripts/test-zcode-session-evidence.py

Standard library only; supports Python 3.9+.
"""

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zcode-session-evidence.py")

SESSION_A = "sess-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SESSION_B = "sess-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
INPUT_OK = "input-0001"
SECRET_PAYLOAD = "TOPSECRET-payload-7f3a"
SECRET_REASONING = "TOPSECRET-reasoning-chain"
SECRET_TOOL_IO = "TOPSECRET-tool-output"

TABLES = {
    "session_input": (
        "CREATE TABLE session_input ("
        " id TEXT, session_id TEXT, kind TEXT, delivery TEXT, payload TEXT,"
        " admitted_sequence INTEGER, promoted_sequence INTEGER, promoted_message_id TEXT,"
        " status TEXT, status_reason TEXT, time_created TEXT, time_updated TEXT);"
    ),
    "turn_usage": (
        "CREATE TABLE turn_usage ("
        " session_id TEXT, turn_id TEXT, trace_id TEXT, user_message_id TEXT, status TEXT,"
        " started_at TEXT, first_model_start_at TEXT, first_token_at TEXT, completed_at TEXT,"
        " duration_ms INTEGER, time_to_first_token_ms INTEGER, model_request_count INTEGER,"
        " model_retry_count INTEGER, tool_call_count INTEGER, tool_error_count INTEGER,"
        " input_tokens INTEGER, output_tokens INTEGER, reasoning_tokens INTEGER,"
        " cache_creation_input_tokens INTEGER, cache_read_input_tokens INTEGER,"
        " computed_total_tokens INTEGER, retryable INTEGER, cancelled_by_user INTEGER,"
        " context_exceeded INTEGER, error_type TEXT, error_code TEXT);"
    ),
    "message": (
        "CREATE TABLE message ("
        " id TEXT, session_id TEXT, time_created TEXT, time_updated TEXT, data TEXT,"
        " sequence INTEGER);"
    ),
    "part": (
        "CREATE TABLE part ("
        " id TEXT, message_id TEXT, session_id TEXT, time_created TEXT, time_updated TEXT,"
        " data TEXT, sequence INTEGER);"
    ),
}


def schema_sql(*names):
    return "\n".join(TABLES[name] for name in names)


FULL_SCHEMA = schema_sql("session_input", "turn_usage", "message", "part")
NO_PART_SCHEMA = schema_sql("session_input", "turn_usage", "message")
MESSAGE_NO_DATA_SCHEMA = "\n".join([
    TABLES["session_input"],
    TABLES["turn_usage"],
    "CREATE TABLE message ("
    " id TEXT, session_id TEXT, time_created TEXT, time_updated TEXT, sequence INTEGER);",
    TABLES["part"],
])


def input_row(sid=SESSION_A, iid=INPUT_OK, status="promoted", promoted="msg-u1",
              payload=SECRET_PAYLOAD, reason=None):
    return (iid, sid, "user", "cli", payload, 1, 2, promoted, status, reason,
            "2026-10-02T00:00:00Z", "2026-10-02T00:00:01Z")


def turn_row(sid=SESSION_A, tid="turn-1", umid="msg-u1", status="completed",
             completed_at="2026-10-02T00:00:05Z", error_type=None, cancelled=0):
    return (sid, tid, "trace-1", umid, status,
            "2026-10-02T00:00:00Z", "2026-10-02T00:00:01Z", "2026-10-02T00:00:02Z",
            completed_at, 4000, 2000, 1, 0, 0, 0, 100, 200, 0, 0, 0, 300,
            0, cancelled, 0, error_type, None)


def message_row(mid, sid=SESSION_A, parent=None, role="assistant", seq=1,
                provider="prov-x", model="model-x", mode="build", completed=True,
                error=None, raw=None):
    if raw is not None:
        return (mid, sid, "t", "t", raw, seq)
    data = {"id": mid, "role": role}
    if parent is not None:
        data["parentID"] = parent
    if provider is not None:
        data["providerId"] = provider
    if model is not None:
        data["modelId"] = model
    if mode is not None:
        data["mode"] = mode
    data["time"] = {"completed": "2026-10-02T00:00:0%dZ" % (seq + 1) if completed else None}
    if error is not None:
        data["error"] = error
    return (mid, sid, "t", "t", json.dumps(data), seq)


def part_row(pid, mid, sid=SESSION_A, ptype="text", text="", seq=0, raw=None):
    if raw is not None:
        return (pid, mid, sid, "t", "t", raw, seq)
    return (pid, mid, sid, "t", "t",
            json.dumps({"id": pid, "type": ptype, "text": text}), seq)


def make_db(path, schema=FULL_SCHEMA, inputs=(), turns=(), messages=(), parts=()):
    conn = sqlite3.connect(path)
    try:
        conn.executescript(schema)
        present = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        # Broken-schema fixtures omit tables or columns; only insert when the
        # target table exists so the CLI (not the builder) reports the defect.
        if "session_input" in present and inputs:
            conn.executemany("INSERT INTO session_input VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", inputs)
        if "turn_usage" in present and turns:
            conn.executemany(
                "INSERT INTO turn_usage VALUES (" + ",".join(["?"] * 26) + ")", turns)
        if "message" in present and messages:
            conn.executemany("INSERT INTO message VALUES (?,?,?,?,?,?)", messages)
        if "part" in present and parts:
            conn.executemany("INSERT INTO part VALUES (?,?,?,?,?,?,?)", parts)
        conn.commit()
    finally:
        conn.close()


def build_completed_db(path):
    make_db(
        path,
        inputs=[input_row()],
        turns=[turn_row()],
        messages=[
            message_row("msg-u1", role="user", seq=0),
            message_row("msg-a1", parent="msg-u1", seq=1),
        ],
        parts=[
            part_row("p1", "msg-a1", text="最终答案文本", seq=0),
            part_row("p2", "msg-a1", ptype="reasoning", text=SECRET_REASONING, seq=1),
            part_row("p3", "msg-a1", ptype="tool", text=SECRET_TOOL_IO, seq=2),
        ],
    )


def run_cli(db, sid, iid, extra=()):
    cmd = [
        sys.executable, SCRIPT,
        "--db", db,
        "--session-id", sid,
        "--input-id", iid,
    ] + list(extra)
    return subprocess.run(cmd, capture_output=True, encoding="utf-8", timeout=60)


def sha256_file(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


class ZcodeSessionEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="zcode-evidence-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def db_path(self, name="fixture.db"):
        return os.path.join(self.tmp, name)

    # ------------------------------------------------------------------
    # Binding and full chain
    # ------------------------------------------------------------------

    def test_completed_full_chain(self):
        db = self.db_path()
        build_completed_db(db)
        proc = run_cli(db, SESSION_A, INPUT_OK)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        body = json.loads(proc.stdout)
        self.assertTrue(body["ok"])
        self.assertEqual(body["input"]["status"], "promoted")
        self.assertEqual(body["input"]["promotedMessageId"], "msg-u1")
        self.assertTrue(body["turn"]["found"])
        self.assertEqual(body["turn"]["turnId"], "turn-1")
        self.assertEqual(body["turn"]["status"], "completed")
        final = body["finalAssistant"]
        self.assertTrue(final["found"])
        self.assertEqual(final["messageId"], "msg-a1")
        self.assertTrue(final["completed"])
        self.assertTrue(final["errorFree"])
        self.assertTrue(final["textAvailable"])
        self.assertEqual(final["textLength"], len("最终答案文本"))
        self.assertEqual(final["providerId"], "prov-x")
        self.assertEqual(final["modelId"], "model-x")
        self.assertEqual(final["mode"], "build")
        self.assertNotIn("text", final)
        self.assertTrue(body["completionEvidence"]["turnCompleted"])
        self.assertTrue(body["completionEvidence"]["complete"])
        self.assertFalse(body["liveness"]["authoritative"])

    def test_foreign_session_binding_rejected(self):
        db = self.db_path()
        build_completed_db(db)
        proc = run_cli(db, SESSION_B, INPUT_OK)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["error"]["code"], "INPUT_NOT_FOUND")

    def test_foreign_input_binding_rejected(self):
        db = self.db_path()
        build_completed_db(db)
        proc = run_cli(db, SESSION_A, "input-belongs-elsewhere")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["error"]["code"], "INPUT_NOT_FOUND")

    def test_ambiguous_turns_rejected(self):
        db = self.db_path()
        make_db(
            db,
            inputs=[input_row()],
            turns=[turn_row(tid="turn-1"), turn_row(tid="turn-2")],
            messages=[
                message_row("msg-u1", role="user", seq=0),
                message_row("msg-a1", parent="msg-u1", seq=1),
            ],
            parts=[part_row("p1", "msg-a1", text="ok")],
        )
        proc = run_cli(db, SESSION_A, INPUT_OK)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["error"]["code"], "TURN_AMBIGUOUS")

    # ------------------------------------------------------------------
    # Input statuses and missing turn
    # ------------------------------------------------------------------

    def test_admitted_input_has_no_turn(self):
        db = self.db_path()
        make_db(db, inputs=[input_row(status="admitted", promoted=None)])
        proc = run_cli(db, SESSION_A, INPUT_OK)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        body = json.loads(proc.stdout)
        self.assertEqual(body["input"]["status"], "admitted")
        self.assertFalse(body["turn"]["found"])
        self.assertFalse(body["finalAssistant"]["found"])
        self.assertFalse(body["completionEvidence"]["complete"])

    def test_failed_input_reported(self):
        db = self.db_path()
        make_db(db, inputs=[input_row(status="failed", promoted=None, reason="gate-rejected")])
        proc = run_cli(db, SESSION_A, INPUT_OK)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        body = json.loads(proc.stdout)
        self.assertEqual(body["input"]["status"], "failed")
        self.assertFalse(body["completionEvidence"]["complete"])

    def test_promoted_without_turn(self):
        db = self.db_path()
        make_db(
            db,
            inputs=[input_row()],
            turns=[],
            messages=[
                message_row("msg-u1", role="user", seq=0),
                message_row("msg-a1", parent="msg-u1", seq=1),
            ],
            parts=[part_row("p1", "msg-a1", text="ok")],
        )
        proc = run_cli(db, SESSION_A, INPUT_OK)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        body = json.loads(proc.stdout)
        self.assertFalse(body["turn"]["found"])
        self.assertFalse(body["completionEvidence"]["turnCompleted"])
        self.assertFalse(body["completionEvidence"]["complete"])

    # ------------------------------------------------------------------
    # Final assistant selection: never shadow the latest by an earlier success
    # ------------------------------------------------------------------

    def test_latest_assistant_error_not_shadowed(self):
        db = self.db_path()
        make_db(
            db,
            inputs=[input_row()],
            turns=[turn_row()],
            messages=[
                message_row("msg-u1", role="user", seq=0),
                message_row("msg-a1", parent="msg-u1", seq=1),
                message_row("msg-a2", parent="msg-u1", seq=2, error={"message": "boom"}),
            ],
            parts=[part_row("p1", "msg-a1", text="earlier success")],
        )
        proc = run_cli(db, SESSION_A, INPUT_OK)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        body = json.loads(proc.stdout)
        final = body["finalAssistant"]
        self.assertEqual(final["messageId"], "msg-a2")
        self.assertFalse(final["errorFree"])
        self.assertFalse(final["textAvailable"])
        self.assertEqual(final["textLength"], 0)
        self.assertFalse(body["completionEvidence"]["complete"])
        self.assertNotIn("earlier success", proc.stdout)

    def test_latest_assistant_incomplete_not_shadowed(self):
        db = self.db_path()
        make_db(
            db,
            inputs=[input_row()],
            turns=[turn_row()],
            messages=[
                message_row("msg-u1", role="user", seq=0),
                message_row("msg-a1", parent="msg-u1", seq=1),
                message_row("msg-a2", parent="msg-u1", seq=2, completed=False),
            ],
            parts=[part_row("p1", "msg-a1", text="earlier success")],
        )
        proc = run_cli(db, SESSION_A, INPUT_OK)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        body = json.loads(proc.stdout)
        final = body["finalAssistant"]
        self.assertEqual(final["messageId"], "msg-a2")
        self.assertFalse(final["completed"])
        self.assertFalse(final["textAvailable"])
        self.assertFalse(body["completionEvidence"]["complete"])

    def test_latest_assistant_without_text(self):
        db = self.db_path()
        make_db(
            db,
            inputs=[input_row()],
            turns=[turn_row()],
            messages=[
                message_row("msg-u1", role="user", seq=0),
                message_row("msg-a1", parent="msg-u1", seq=1),
            ],
            parts=[part_row("p1", "msg-a1", ptype="reasoning", text=SECRET_REASONING)],
        )
        proc = run_cli(db, SESSION_A, INPUT_OK)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        body = json.loads(proc.stdout)
        self.assertFalse(body["finalAssistant"]["textAvailable"])
        self.assertEqual(body["finalAssistant"]["textLength"], 0)
        self.assertFalse(body["completionEvidence"]["complete"])
        self.assertNotIn(SECRET_REASONING, proc.stdout)

    def test_turn_running_is_not_completed(self):
        db = self.db_path()
        make_db(
            db,
            inputs=[input_row()],
            turns=[turn_row(status="running", completed_at=None)],
            messages=[
                message_row("msg-u1", role="user", seq=0),
                message_row("msg-a1", parent="msg-u1", seq=1),
            ],
            parts=[part_row("p1", "msg-a1", text="partial")],
        )
        proc = run_cli(db, SESSION_A, INPUT_OK)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        body = json.loads(proc.stdout)
        self.assertEqual(body["turn"]["status"], "running")
        self.assertFalse(body["completionEvidence"]["turnCompleted"])
        self.assertFalse(body["completionEvidence"]["complete"])

    def test_unknown_turn_status_stays_unknown(self):
        db = self.db_path()
        make_db(db, inputs=[input_row()], turns=[turn_row(status="queued")])
        proc = run_cli(db, SESSION_A, INPUT_OK)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        body = json.loads(proc.stdout)
        self.assertEqual(body["turn"]["status"], "unknown")
        self.assertFalse(body["completionEvidence"]["complete"])

    def test_provider_fields_missing_become_unknown(self):
        db = self.db_path()
        make_db(
            db,
            inputs=[input_row()],
            turns=[turn_row()],
            messages=[
                message_row("msg-u1", role="user", seq=0),
                message_row("msg-a1", parent="msg-u1", seq=1,
                            provider=None, model=None, mode=None),
            ],
            parts=[part_row("p1", "msg-a1", text="done")],
        )
        proc = run_cli(db, SESSION_A, INPUT_OK)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        body = json.loads(proc.stdout)
        final = body["finalAssistant"]
        self.assertEqual(final["providerId"], "unknown")
        self.assertEqual(final["modelId"], "unknown")
        self.assertEqual(final["mode"], "unknown")
        self.assertTrue(body["completionEvidence"]["complete"])

    # ------------------------------------------------------------------
    # Schema and JSON robustness
    # ------------------------------------------------------------------

    def test_missing_table_rejected(self):
        db = self.db_path()
        make_db(db, schema=NO_PART_SCHEMA, inputs=[input_row()], turns=[turn_row()])
        proc = run_cli(db, SESSION_A, INPUT_OK)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["error"]["code"], "DB_SCHEMA_INVALID")

    def test_missing_column_rejected(self):
        db = self.db_path()
        make_db(db, schema=MESSAGE_NO_DATA_SCHEMA, inputs=[input_row()], turns=[turn_row()])
        proc = run_cli(db, SESSION_A, INPUT_OK)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["error"]["code"], "DB_SCHEMA_INVALID")

    def test_malformed_message_json_rejected(self):
        db = self.db_path()
        make_db(
            db,
            inputs=[input_row()],
            turns=[turn_row()],
            messages=[
                message_row("msg-u1", role="user", seq=0),
                message_row("msg-bad", parent="msg-u1", seq=1, raw="{not json"),
            ],
        )
        proc = run_cli(db, SESSION_A, INPUT_OK)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["error"]["code"], "JSON_MALFORMED")

    def test_malformed_part_json_rejected(self):
        db = self.db_path()
        make_db(
            db,
            inputs=[input_row()],
            turns=[turn_row()],
            messages=[
                message_row("msg-u1", role="user", seq=0),
                message_row("msg-a1", parent="msg-u1", seq=1),
            ],
            parts=[part_row("p1", "msg-a1", raw="{oops")],
        )
        proc = run_cli(db, SESSION_A, INPUT_OK)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["error"]["code"], "JSON_MALFORMED")

    # ------------------------------------------------------------------
    # Output surface: text flag, sensitive material, db path
    # ------------------------------------------------------------------

    def test_include_final_text_flag(self):
        db = self.db_path()
        build_completed_db(db)
        proc = run_cli(db, SESSION_A, INPUT_OK, extra=["--include-final-text"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        body = json.loads(proc.stdout)
        self.assertEqual(body["finalAssistant"]["text"], "最终答案文本")
        self.assertNotIn(SECRET_REASONING, proc.stdout)
        self.assertNotIn(SECRET_TOOL_IO, proc.stdout)
        self.assertNotIn(SECRET_PAYLOAD, proc.stdout)

    def test_metadata_only_by_default(self):
        db = self.db_path()
        build_completed_db(db)
        proc = run_cli(db, SESSION_A, INPUT_OK)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        body = json.loads(proc.stdout)
        self.assertNotIn("text", body["finalAssistant"])
        self.assertNotIn(SECRET_REASONING, proc.stdout)
        self.assertNotIn(SECRET_TOOL_IO, proc.stdout)
        self.assertNotIn(SECRET_PAYLOAD, proc.stdout)

    def test_sensitive_material_never_leaked(self):
        db = self.db_path()
        build_completed_db(db)
        for extra in ([], ["--include-final-text"]):
            proc = run_cli(db, SESSION_A, INPUT_OK, extra=extra)
            combined = proc.stdout + proc.stderr
            self.assertNotIn(SECRET_PAYLOAD, combined)
            self.assertNotIn(SECRET_REASONING, combined)
            self.assertNotIn(SECRET_TOOL_IO, combined)
            self.assertNotIn(db, combined)
            self.assertNotIn(os.path.basename(db), combined)

    def test_error_output_withholds_db_path(self):
        db = self.db_path("absent.db")
        proc = run_cli(db, SESSION_A, INPUT_OK)
        self.assertNotEqual(proc.returncode, 0)
        combined = proc.stdout + proc.stderr
        self.assertEqual(json.loads(proc.stdout)["error"]["code"], "DB_NOT_FOUND")
        self.assertNotIn(db, combined)
        self.assertNotIn(os.path.basename(db), combined)

    # ------------------------------------------------------------------
    # Filesystem safety: no db creation, source db untouched
    # ------------------------------------------------------------------

    def test_missing_db_not_created(self):
        db = self.db_path("must-not-appear.db")
        proc = run_cli(db, SESSION_A, INPUT_OK)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["error"]["code"], "DB_NOT_FOUND")
        self.assertFalse(os.path.exists(db))

    def test_source_db_unmodified(self):
        db = self.db_path()
        build_completed_db(db)
        before = sha256_file(db)
        self.assertEqual(run_cli(db, SESSION_A, INPUT_OK).returncode, 0)
        self.assertEqual(run_cli(db, SESSION_A, INPUT_OK, extra=["--include-final-text"]).returncode, 0)
        self.assertNotEqual(run_cli(db, SESSION_B, INPUT_OK).returncode, 0)
        self.assertEqual(before, sha256_file(db))

    # ------------------------------------------------------------------
    # R1 review repairs: F1 status_reason surface, F2 sequence ambiguity
    # ------------------------------------------------------------------

    def test_status_reason_surface_is_boolean_only(self):
        adversarial = "TOPSECRET-REASON-R1 /Users/somebody/secret-dir/file.txt"
        base_msgs = [
            message_row("msg-u1", role="user", seq=0),
            message_row("msg-a1", parent="msg-u1", seq=1),
        ]
        base_parts = [part_row("p1", "msg-a1", text="done")]

        db = self.db_path("reason-adversarial.db")
        make_db(db, inputs=[input_row(reason=adversarial)], turns=[turn_row()],
                messages=base_msgs, parts=base_parts)
        proc = run_cli(db, SESSION_A, INPUT_OK)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        body = json.loads(proc.stdout)
        self.assertTrue(body["input"]["reasonPresent"])
        self.assertNotIn("statusReason", body["input"])
        self.assertNotIn("TOPSECRET-REASON-R1", proc.stdout + proc.stderr)
        self.assertNotIn("secret-dir", proc.stdout + proc.stderr)

        db = self.db_path("reason-absent.db")
        make_db(db, inputs=[input_row(reason=None)], turns=[turn_row()],
                messages=base_msgs, parts=base_parts)
        proc = run_cli(db, SESSION_A, INPUT_OK)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse(json.loads(proc.stdout)["input"]["reasonPresent"])

        db = self.db_path("reason-blank.db")
        make_db(db, inputs=[input_row(reason="   ")], turns=[turn_row()],
                messages=base_msgs, parts=base_parts)
        proc = run_cli(db, SESSION_A, INPUT_OK)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse(json.loads(proc.stdout)["input"]["reasonPresent"])

    def test_assistant_sequence_tie_rejected_both_orders(self):
        # Same maximum sequence: neither an earlier success nor a newer failure
        # may win by row order — both insertion orders are rejected.
        for name, tail in (
            ("tie-success-first", (
                message_row("msg-a1", parent="msg-u1", seq=2),
                message_row("msg-a2", parent="msg-u1", seq=2, error={"message": "boom"}),
            )),
            ("tie-error-first", (
                message_row("msg-a2", parent="msg-u1", seq=2, error={"message": "boom"}),
                message_row("msg-a1", parent="msg-u1", seq=2),
            )),
        ):
            db = self.db_path(name + ".db")
            make_db(
                db,
                inputs=[input_row()],
                turns=[turn_row()],
                messages=[message_row("msg-u1", role="user", seq=0)] + list(tail),
                parts=[part_row("p1", "msg-a1", text="earlier success")],
            )
            proc = run_cli(db, SESSION_A, INPUT_OK)
            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["error"]["code"], "ASSISTANT_AMBIGUOUS")

    def test_assistant_sequence_null_rejected(self):
        for name, tail in (
            ("null-single", (
                message_row("msg-a1", parent="msg-u1", seq=None, completed=False),
            )),
            ("null-all", (
                message_row("msg-a1", parent="msg-u1", seq=None, completed=False),
                message_row("msg-a2", parent="msg-u1", seq=None, completed=False),
            )),
        ):
            db = self.db_path(name + ".db")
            make_db(
                db,
                inputs=[input_row()],
                turns=[turn_row()],
                messages=[message_row("msg-u1", role="user", seq=0)] + list(tail),
                parts=[part_row("p1", "msg-a1", text="ok")],
            )
            proc = run_cli(db, SESSION_A, INPUT_OK)
            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["error"]["code"], "ASSISTANT_AMBIGUOUS")

    def test_assistant_sequence_non_numeric_rejected(self):
        db = self.db_path()
        make_db(
            db,
            inputs=[input_row()],
            turns=[turn_row()],
            messages=[
                message_row("msg-u1", role="user", seq=0),
                ("msg-a1", SESSION_A, "t", "t",
                 json.dumps({"id": "msg-a1", "role": "assistant", "parentID": "msg-u1",
                             "time": {"completed": "2026-10-02T00:00:02Z"}}),
                 "not-a-number"),
            ],
            parts=[part_row("p1", "msg-a1", text="ok")],
        )
        proc = run_cli(db, SESSION_A, INPUT_OK)
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["error"]["code"], "ASSISTANT_AMBIGUOUS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
