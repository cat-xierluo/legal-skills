#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Targeted black-box tests for zcode-gui-observe.py.

Runs the real CLI entry point via subprocess only. The real-dependency group
drives the frozen PR250 collector and PR253 adapter against synthetic
databases; it is skipped with an explicit notice when neither
ZCODE_GUI_COLLECTOR / ZCODE_GUI_ADAPTER nor the sibling scripts are
available. All other wrapper fault paths are exercised with tiny canned
stubs; dependency implementations are never copied or reimplemented here.

Scratch files live under ZCODE_GUI_OBSERVE_SCRATCH when set (card-private
root), otherwise under the system temporary directory.

Standard library only; supports Python 3.9+.
"""

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OBSERVE = os.path.join(SCRIPT_DIR, "zcode-gui-observe.py")

ENV_COLLECTOR = "ZCODE_GUI_COLLECTOR"
ENV_ADAPTER = "ZCODE_GUI_ADAPTER"
SIBLING_COLLECTOR = os.path.join(SCRIPT_DIR, "zcode-session-evidence.py")
SIBLING_ADAPTER = os.path.join(SCRIPT_DIR, "zcode-gui-monitor-adapter.py")

SCRATCH_ROOT = (
    os.environ.get("ZCODE_GUI_OBSERVE_SCRATCH")
    or os.path.join(tempfile.gettempdir(), "zcode-gui-observe-tests")
)
os.makedirs(SCRATCH_ROOT, exist_ok=True)

SID = "sess-zgo-fixture"
OTHER_SID = "sess-zgo-other"
IID = "input-zgo-1"
OTHER_IID = "input-zgo-other"
PROVIDER = "acme-provider"
MODEL = "model-x"

CANARY = "SECRET-CANARY-zgo-9f1"
FAKE_DB_PATH = "/Users/somebody/Library/Application Support/ZCode/sessions/secret.db"

TEMP_PREFIX = "zcode-gui-observe-"
FALSE_FLAGS = {"pmAccepted": False, "orcaSupervised": False, "livenessAuthoritative": False}


def resolve_real_dependency(env_name, sibling):
    value = os.environ.get(env_name)
    if value and os.path.isfile(value):
        return value
    if os.path.isfile(sibling):
        return sibling
    return None


REAL_COLLECTOR = resolve_real_dependency(ENV_COLLECTOR, SIBLING_COLLECTOR)
REAL_ADAPTER = resolve_real_dependency(ENV_ADAPTER, SIBLING_ADAPTER)
HAVE_REAL_DEPENDENCIES = bool(REAL_COLLECTOR and REAL_ADAPTER)

if not HAVE_REAL_DEPENDENCIES:
    sys.stderr.write(
        "SKIP-GROUP: real frozen dependencies unavailable"
        " (set %s / %s to the frozen PR250/PR253 scripts);"
        " only stub-based wrapper tests will run\n"
        % (ENV_COLLECTOR, ENV_ADAPTER)
    )


def collector_ok_payload(**overrides):
    """Canned collector metadata fixture (schemaVersion 1), not an implementation."""
    payload = {
        "ok": True,
        "schemaVersion": 1,
        "sessionId": SID,
        "inputId": IID,
        "input": {"status": "promoted", "reasonPresent": False, "promotedMessageId": "msg-user-1"},
        "turn": {"found": False, "turnId": None, "status": None},
        "finalAssistant": {
            "found": False, "messageId": None, "completed": False, "errorFree": False,
            "textAvailable": False, "textLength": 0,
            "providerId": "unknown", "modelId": "unknown", "mode": "unknown",
        },
        "completionEvidence": {
            "turnCompleted": False, "finalAssistantCompleted": False,
            "finalAssistantErrorFree": False, "finalTextAvailable": False,
            "complete": False,
        },
        "liveness": {"authoritative": False, "note": "stub fixture"},
    }
    payload.update(overrides)
    return payload


def adapter_ok_payload(**overrides):
    """Canned adapter success fixture, not an implementation."""
    payload = {
        "adapter": "zcode-gui-monitor-adapter",
        "schemaVersion": 1,
        "sessionId": SID,
        "inputId": IID,
        "turnId": None,
        "evidenceSha256": "a" * 64,
        "state": "TURN_UNKNOWN",
        "provider": "unknown",
        "model": "unknown",
        "flags": dict(FALSE_FLAGS),
    }
    payload.update(overrides)
    return payload


class ObserveTestCase(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.mkdtemp(prefix="zgo-case-", dir=SCRATCH_ROOT)
        self.temp_dir = tempfile.gettempdir()
        self.temp_baseline = self.prefixed_temp_count()

    def tearDown(self):
        self.assertEqual(
            self.prefixed_temp_count(), self.temp_baseline,
            "wrapper leaked %s* temporary files" % TEMP_PREFIX,
        )

    def prefixed_temp_count(self):
        try:
            names = os.listdir(self.temp_dir)
        except OSError:
            return 0
        return sum(1 for name in names if name.startswith(TEMP_PREFIX))

    def scratch_path(self, name):
        return os.path.join(self.scratch, name)

    def build_db(self, name, **kwargs):
        """Synthetic native-shaped database for the collector's schema contract."""
        path = self.scratch_path(name)
        conn = sqlite3.connect(path)
        try:
            conn.executescript(
                "CREATE TABLE session_input (id TEXT PRIMARY KEY, session_id TEXT,"
                " status TEXT, status_reason TEXT, promoted_message_id TEXT);"
                "CREATE TABLE turn_usage (session_id TEXT, turn_id TEXT,"
                " user_message_id TEXT, status TEXT, completed_at INTEGER,"
                " error_type TEXT, cancelled_by_user INTEGER);"
                "CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT,"
                " data TEXT, sequence INTEGER);"
                "CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT,"
                " session_id TEXT, data TEXT, sequence INTEGER);"
            )
            conn.execute(
                "INSERT INTO session_input VALUES (?, ?, ?, ?, ?)",
                (IID, SID, kwargs.get("input_status", "promoted"),
                 kwargs.get("status_reason"), "msg-user-1"),
            )
            turn_status = kwargs.get("turn_status")
            if turn_status:
                conn.execute(
                    "INSERT INTO turn_usage VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (SID, "turn-1", "msg-user-1", turn_status, None, None, 0),
                )
            assistant_data = {
                "role": "assistant",
                "parentID": "msg-user-1",
                "time": {"completed": 1727900000},
                "providerId": kwargs.get("provider", PROVIDER),
                "modelId": kwargs.get("model", MODEL),
                "mode": "build",
            }
            if kwargs.get("assistant_error"):
                assistant_data["error"] = "synthetic failure marker"
            conn.execute(
                "INSERT INTO message VALUES (?, ?, ?, ?)",
                ("msg-assistant-1", SID, json.dumps(assistant_data), 2),
            )
            if kwargs.get("has_text", True):
                conn.execute(
                    "INSERT INTO part VALUES (?, ?, ?, ?, ?)",
                    ("part-1", "msg-assistant-1", SID,
                     json.dumps({"type": "text", "text": "work completed"}), 1),
                )
            conn.commit()
        finally:
            conn.close()
        return path

    def write_stub(self, name, payload=None, raw_text=None, sleep_seconds=0, exit_code=0):
        lines = ["#!/usr/bin/env python3", "import json, sys, time"]
        if sleep_seconds:
            lines.append("time.sleep(%d)" % sleep_seconds)
        if payload is not None:
            lines.append("sys.stdout.write(json.dumps(%r) + chr(10))" % (payload,))
        if raw_text is not None:
            lines.append("sys.stdout.write(%r)" % (raw_text,))
        if exit_code:
            lines.append("raise SystemExit(%d)" % exit_code)
        path = self.scratch_path(name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        return path

    def file_sha256(self, path):
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()

    def real_env(self):
        return {ENV_COLLECTOR: REAL_COLLECTOR, ENV_ADAPTER: REAL_ADAPTER}

    def run_observe(self, extra_args, env_overrides=None):
        env = dict(os.environ)
        env.pop(ENV_COLLECTOR, None)
        env.pop(ENV_ADAPTER, None)
        for key, value in (env_overrides or {}).items():
            env[key] = value
        return subprocess.run(
            [sys.executable, OBSERVE] + extra_args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            timeout=120,
        )

    def single_json_line(self, proc):
        text = proc.stdout.decode("utf-8", "replace")
        lines = [line for line in text.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, "wrapper must print exactly one JSON line on stdout")
        return json.loads(lines[0])

    def assert_no_echo(self, proc, *secrets):
        text = proc.stdout.decode("utf-8", "replace")
        for secret in secrets:
            self.assertNotIn(secret, text)

    def assert_ok_payload(self, proc, state):
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        payload = self.single_json_line(proc)
        self.assertEqual(payload["status"], "OK")
        self.assertEqual(payload["state"], state)
        self.assertIsNone(payload["error"])
        self.assertEqual(payload["flags"], FALSE_FLAGS)
        self.assertEqual(payload["sessionId"], SID)
        self.assertEqual(payload["inputId"], IID)
        self.assert_no_echo(proc, CANARY, FAKE_DB_PATH)
        return payload

    def assert_error_payload(self, proc, code, secrets=()):
        self.assertEqual(proc.returncode, 1, proc.stderr.decode("utf-8", "replace"))
        payload = self.single_json_line(proc)
        self.assertEqual(payload["status"], "ERROR")
        self.assertEqual(payload["error"], {"code": code})
        self.assertIsNone(payload["state"])
        self.assertIsNone(payload["summary"])
        self.assertEqual(payload["flags"], FALSE_FLAGS)
        self.assert_no_echo(proc, CANARY, FAKE_DB_PATH, *secrets)
        return payload


@unittest.skipUnless(
    HAVE_REAL_DEPENDENCIES,
    "real frozen dependencies unavailable (set ZCODE_GUI_COLLECTOR / ZCODE_GUI_ADAPTER)",
)
class RealDependencyTests(ObserveTestCase):
    def test_ready_for_pm_review(self):
        db = self.build_db("ready.db", turn_status="completed")
        before = self.file_sha256(db)
        proc = self.run_observe(
            ["--db", db, "--session-id", SID, "--input-id", IID],
            self.real_env(),
        )
        payload = self.assert_ok_payload(proc, "READY_FOR_PM_REVIEW")
        self.assertEqual(
            set(payload),
            {"observer", "schemaVersion", "status", "sessionId", "inputId",
             "state", "summary", "flags", "error"},
        )
        summary = payload["summary"]
        self.assertEqual(
            set(summary),
            {"provider", "model", "turnId", "evidenceSha256",
             "inputStatus", "turnStatus", "finalAssistantFound"},
        )
        self.assertEqual(summary["provider"], PROVIDER)
        self.assertEqual(summary["model"], MODEL)
        self.assertEqual(summary["turnId"], "turn-1")
        self.assertEqual(summary["inputStatus"], "promoted")
        self.assertEqual(summary["turnStatus"], "completed")
        self.assertTrue(summary["finalAssistantFound"])
        self.assertRegex(summary["evidenceSha256"], r"^[0-9a-f]{64}$")
        self.assert_no_echo(proc, db, REAL_COLLECTOR, REAL_ADAPTER)
        self.assertEqual(self.file_sha256(db), before, "native DB must stay unchanged")

    def test_ready_via_flags_expected_identity_and_shas(self):
        db = self.build_db("ready-pinned.db", turn_status="completed")
        proc = self.run_observe(
            [
                "--db", db, "--session-id", SID, "--input-id", IID,
                "--collector", REAL_COLLECTOR, "--adapter", REAL_ADAPTER,
                "--expect-provider", PROVIDER, "--expect-model", MODEL,
                "--collector-sha256", self.file_sha256(REAL_COLLECTOR),
                "--adapter-sha256", self.file_sha256(REAL_ADAPTER),
            ],
            {},
        )
        self.assert_ok_payload(proc, "READY_FOR_PM_REVIEW")

    def test_wrong_session_id(self):
        db = self.build_db("wrong-sid.db", turn_status="completed")
        before = self.file_sha256(db)
        proc = self.run_observe(
            ["--db", db, "--session-id", OTHER_SID, "--input-id", IID],
            self.real_env(),
        )
        self.assert_error_payload(proc, "INPUT_NOT_FOUND", secrets=(db,))
        self.assertEqual(self.file_sha256(db), before)

    def test_wrong_input_id(self):
        db = self.build_db("wrong-iid.db", turn_status="completed")
        proc = self.run_observe(
            ["--db", db, "--session-id", SID, "--input-id", OTHER_IID],
            self.real_env(),
        )
        self.assert_error_payload(proc, "INPUT_NOT_FOUND", secrets=(db,))

    def test_promoted_without_turn_is_unknown(self):
        db = self.build_db("no-turn.db", turn_status=None)
        proc = self.run_observe(
            ["--db", db, "--session-id", SID, "--input-id", IID],
            self.real_env(),
        )
        payload = self.assert_ok_payload(proc, "TURN_UNKNOWN")
        self.assertIsNone(payload["summary"]["turnStatus"])

    def test_turn_running(self):
        db = self.build_db("running.db", turn_status="running")
        proc = self.run_observe(
            ["--db", db, "--session-id", SID, "--input-id", IID],
            self.real_env(),
        )
        payload = self.assert_ok_payload(proc, "TURN_RUNNING")
        self.assertEqual(payload["summary"]["turnStatus"], "running")

    def test_turn_error(self):
        db = self.build_db("turn-error.db", turn_status="error")
        proc = self.run_observe(
            ["--db", db, "--session-id", SID, "--input-id", IID],
            self.real_env(),
        )
        self.assert_ok_payload(proc, "TURN_ERROR")

    def test_turn_cancelled(self):
        db = self.build_db("cancelled.db", turn_status="cancelled")
        proc = self.run_observe(
            ["--db", db, "--session-id", SID, "--input-id", IID],
            self.real_env(),
        )
        self.assert_ok_payload(proc, "TURN_CANCELLED")

    def test_completed_turn_with_final_error_is_delivery_error(self):
        db = self.build_db("final-error.db", turn_status="completed", assistant_error=True)
        proc = self.run_observe(
            ["--db", db, "--session-id", SID, "--input-id", IID],
            self.real_env(),
        )
        self.assert_ok_payload(proc, "DELIVERY_ERROR")

    def test_completed_turn_without_text_is_delivery_pending(self):
        db = self.build_db("pending.db", turn_status="completed", has_text=False)
        proc = self.run_observe(
            ["--db", db, "--session-id", SID, "--input-id", IID],
            self.real_env(),
        )
        self.assert_ok_payload(proc, "DELIVERY_PENDING")

    def test_non_database_file(self):
        db = self.scratch_path("empty.db")
        open(db, "wb").close()
        proc = self.run_observe(
            ["--db", db, "--session-id", SID, "--input-id", IID],
            self.real_env(),
        )
        self.assert_error_payload(proc, "DB_SCHEMA_INVALID", secrets=(db,))

    def test_missing_database(self):
        db = self.scratch_path("absent.db")
        proc = self.run_observe(
            ["--db", db, "--session-id", SID, "--input-id", IID],
            self.real_env(),
        )
        self.assert_error_payload(proc, "DB_NOT_FOUND", secrets=(db,))

    def test_expect_provider_mismatch(self):
        db = self.build_db("provider.db", turn_status="completed")
        proc = self.run_observe(
            ["--db", db, "--session-id", SID, "--input-id", IID,
             "--expect-provider", "someone-else"],
            self.real_env(),
        )
        self.assert_error_payload(proc, "PROVIDER_MISMATCH", secrets=(db,))

    def test_dependency_sha_mismatch(self):
        db = self.build_db("sha.db", turn_status="completed")
        proc = self.run_observe(
            ["--db", db, "--session-id", SID, "--input-id", IID,
             "--collector-sha256", "0" * 64],
            self.real_env(),
        )
        self.assert_error_payload(
            proc, "OBS_DEP_SHA_MISMATCH",
            secrets=(db, self.file_sha256(REAL_COLLECTOR)),
        )

    def test_sensitive_extra_fields_not_leaked(self):
        payload = collector_ok_payload()
        payload["debugEcho"] = CANARY + " " + FAKE_DB_PATH
        stub = self.write_stub("collector-canary.py", payload=payload)
        proc = self.run_observe(
            ["--db", self.scratch_path("unused.db"),
             "--session-id", SID, "--input-id", IID, "--collector", stub],
            {ENV_ADAPTER: REAL_ADAPTER},
        )
        self.assert_ok_payload(proc, "TURN_UNKNOWN")

    def test_dependency_missing_via_env(self):
        db = self.build_db("dep.db")
        missing = self.scratch_path("no-such-collector.py")
        proc = self.run_observe(
            ["--db", db, "--session-id", SID, "--input-id", IID],
            {ENV_COLLECTOR: missing, ENV_ADAPTER: REAL_ADAPTER},
        )
        self.assert_error_payload(proc, "OBS_DEP_MISSING", secrets=(missing, db))


@unittest.skipUnless(
    not os.path.isfile(SIBLING_COLLECTOR) and not os.path.isfile(SIBLING_ADAPTER),
    "sibling dependencies exist; default-missing resolution not applicable",
)
class DefaultSiblingMissingTests(ObserveTestCase):
    def test_default_resolution_reports_missing_dependency(self):
        db = self.build_db("sibling.db")
        proc = self.run_observe(
            ["--db", db, "--session-id", SID, "--input-id", IID], {},
        )
        self.assert_error_payload(proc, "OBS_DEP_MISSING", secrets=(db,))


class StubFaultTests(ObserveTestCase):
    def observe_with_stubs(self, db_name, collector_stub, adapter_stub, extra=()):
        db = self.build_db(db_name)
        return self.run_observe(
            ["--db", db, "--session-id", SID, "--input-id", IID,
             "--collector", collector_stub, "--adapter", adapter_stub] + list(extra),
            {},
        )

    def test_collector_abnormal_stdout(self):
        stub = self.write_stub("collector-garbage.py", raw_text="not json at all " + CANARY + "\n")
        proc = self.observe_with_stubs("bad.db", stub, self.write_stub("a-unused.py"))
        self.assert_error_payload(proc, "OBS_COLLECTOR_BAD_OUTPUT", secrets=(stub,))

    def test_collector_business_error_code_passthrough(self):
        payload = {"ok": False, "error": {"code": "INPUT_NOT_FOUND", "message": "boom " + CANARY}}
        stub = self.write_stub("collector-error.py", payload=payload)
        proc = self.observe_with_stubs("biz.db", stub, self.write_stub("a-unused2.py"))
        self.assert_error_payload(proc, "INPUT_NOT_FOUND", secrets=(stub,))

    def test_collector_business_error_unsafe_code(self):
        payload = {"ok": False, "error": {"code": "bad code with spaces", "message": CANARY}}
        stub = self.write_stub("collector-unsafe.py", payload=payload)
        proc = self.observe_with_stubs("unsafe.db", stub, self.write_stub("a-unused3.py"))
        self.assert_error_payload(
            proc, "OBS_COLLECTOR_FAILED", secrets=("bad code with spaces", stub),
        )

    def test_adapter_abnormal_stdout(self):
        stub_c = self.write_stub("c-ok1.py", payload=collector_ok_payload())
        stub_a = self.write_stub("a-garbage.py", raw_text="]<not json>\n")
        proc = self.observe_with_stubs("adapt-bad.db", stub_c, stub_a)
        self.assert_error_payload(proc, "OBS_ADAPTER_BAD_OUTPUT", secrets=(stub_a,))

    def test_adapter_business_error_passthrough(self):
        payload = {
            "adapter": "stub", "schemaVersion": 1,
            "error": "MODEL_MISMATCH", "flags": dict(FALSE_FLAGS),
        }
        stub_c = self.write_stub("c-ok2.py", payload=collector_ok_payload())
        stub_a = self.write_stub("a-error.py", payload=payload, exit_code=2)
        proc = self.observe_with_stubs("adapt-err.db", stub_c, stub_a)
        self.assert_error_payload(proc, "MODEL_MISMATCH", secrets=(stub_a,))

    def test_adapter_binding_mismatch(self):
        payload = adapter_ok_payload(sessionId=OTHER_SID)
        stub_c = self.write_stub("c-ok3.py", payload=collector_ok_payload())
        stub_a = self.write_stub("a-binding.py", payload=payload)
        proc = self.observe_with_stubs("adapt-bind.db", stub_c, stub_a)
        self.assert_error_payload(proc, "OBS_BINDING_MISMATCH", secrets=(stub_a,))

    def test_adapter_flag_tamper_rejected(self):
        flags = dict(FALSE_FLAGS)
        flags["pmAccepted"] = True
        payload = adapter_ok_payload(flags=flags)
        stub_c = self.write_stub("c-ok4.py", payload=collector_ok_payload())
        stub_a = self.write_stub("a-tamper.py", payload=payload)
        proc = self.observe_with_stubs("adapt-tamper.db", stub_c, stub_a)
        self.assert_error_payload(proc, "OBS_ADAPTER_BAD_OUTPUT", secrets=(stub_a,))

    def test_collector_timeout(self):
        stub = self.write_stub(
            "collector-slow.py", payload=collector_ok_payload(), sleep_seconds=8,
        )
        started = time.time()
        proc = self.observe_with_stubs(
            "slow-c.db", stub, self.write_stub("a-unused4.py"), extra=["--timeout", "1"],
        )
        self.assert_error_payload(proc, "OBS_DEP_TIMEOUT", secrets=(stub,))
        self.assertLess(time.time() - started, 7, "timeout must be enforced promptly")

    def test_adapter_timeout(self):
        stub_c = self.write_stub("c-ok5.py", payload=collector_ok_payload())
        stub_a = self.write_stub(
            "a-slow.py", payload=adapter_ok_payload(), sleep_seconds=8,
        )
        started = time.time()
        proc = self.observe_with_stubs("slow-a.db", stub_c, stub_a, extra=["--timeout", "1"])
        self.assert_error_payload(proc, "OBS_DEP_TIMEOUT", secrets=(stub_a,))
        self.assertLess(time.time() - started, 7, "timeout must be enforced promptly")

    def test_stub_pipeline_ok_with_max_timeout(self):
        stub_c = self.write_stub("c-ok6.py", payload=collector_ok_payload())
        stub_a = self.write_stub("a-ok.py", payload=adapter_ok_payload())
        proc = self.observe_with_stubs(
            "pipeline.db", stub_c, stub_a, extra=["--timeout", "60"],
        )
        payload = self.assert_ok_payload(proc, "TURN_UNKNOWN")
        summary = payload["summary"]
        self.assertEqual(summary["provider"], "unknown")
        self.assertEqual(summary["model"], "unknown")
        self.assertFalse(summary["finalAssistantFound"])
        self.assertRegex(summary["evidenceSha256"], r"^[0-9a-f]{64}$")

    def test_timeout_below_minimum(self):
        db = self.build_db("t0.db")
        proc = self.run_observe(
            ["--db", db, "--session-id", SID, "--input-id", IID, "--timeout", "0"], {},
        )
        self.assert_error_payload(proc, "OBS_INVALID_ARGS", secrets=(db,))

    def test_timeout_above_maximum(self):
        db = self.build_db("t61.db")
        proc = self.run_observe(
            ["--db", db, "--session-id", SID, "--input-id", IID, "--timeout", "61"], {},
        )
        self.assert_error_payload(proc, "OBS_INVALID_ARGS", secrets=(db,))


class ExitCodeGateTests(ObserveTestCase):
    """R1-repair faults: dependency exit codes, code allowlist, echo bounds."""

    def observe_with_stubs(self, db_name, collector_stub, adapter_stub):
        db = self.build_db(db_name)
        return self.run_observe(
            ["--db", db, "--session-id", SID, "--input-id", IID,
             "--collector", collector_stub, "--adapter", adapter_stub],
            {},
        )

    def test_collector_nonzero_exit_with_legal_ok_payload_fails(self):
        stub_c = self.write_stub(
            "c-exit9-legal-ok.py", payload=collector_ok_payload(), exit_code=9,
        )
        stub_a = self.write_stub("a-unused-g1.py", payload=adapter_ok_payload())
        proc = self.observe_with_stubs("gate-c.db", stub_c, stub_a)
        self.assert_error_payload(proc, "OBS_COLLECTOR_FAILED", secrets=(stub_c,))

    def test_adapter_nonzero_exit_with_legal_ready_payload_fails(self):
        stub_c = self.write_stub("c-ok-g2.py", payload=collector_ok_payload())
        stub_a = self.write_stub(
            "a-exit7-legal-ready.py",
            payload=adapter_ok_payload(state="READY_FOR_PM_REVIEW"),
            exit_code=7,
        )
        proc = self.observe_with_stubs("gate-a.db", stub_c, stub_a)
        self.assert_error_payload(proc, "OBS_ADAPTER_FAILED", secrets=(stub_a,))

    def test_collector_synthetic_error_code_not_echoed(self):
        payload = {
            "ok": False,
            "error": {"code": "SYNTHETIC_PRIVATE_CANARY_123", "message": "boom"},
        }
        stub_c = self.write_stub("c-synthetic-code.py", payload=payload, exit_code=1)
        proc = self.observe_with_stubs(
            "gate-syn-c.db", stub_c, self.write_stub("a-unused-g3.py"),
        )
        self.assert_error_payload(
            proc, "OBS_COLLECTOR_FAILED",
            secrets=("SYNTHETIC_PRIVATE_CANARY_123", stub_c),
        )

    def test_adapter_synthetic_error_code_not_echoed(self):
        payload = {
            "adapter": "stub", "schemaVersion": 1,
            "error": "SYNTHETIC_PRIVATE_CANARY_123",
            "flags": dict(FALSE_FLAGS),
        }
        stub_c = self.write_stub("c-ok-g4.py", payload=collector_ok_payload())
        stub_a = self.write_stub("a-synthetic-code.py", payload=payload, exit_code=2)
        proc = self.observe_with_stubs("gate-syn-a.db", stub_c, stub_a)
        self.assert_error_payload(
            proc, "OBS_ADAPTER_FAILED",
            secrets=("SYNTHETIC_PRIVATE_CANARY_123", stub_a),
        )

    def test_allowlisted_dependency_codes_still_surface(self):
        stub_c = self.write_stub(
            "c-allowlisted.py",
            payload={"ok": False, "error": {"code": "INPUT_NOT_FOUND", "message": "boom"}},
            exit_code=1,
        )
        proc = self.observe_with_stubs(
            "gate-allow-c.db", stub_c, self.write_stub("a-unused-g5.py"),
        )
        self.assert_error_payload(proc, "INPUT_NOT_FOUND", secrets=(stub_c,))

        stub_c2 = self.write_stub("c-ok-g6.py", payload=collector_ok_payload())
        stub_a = self.write_stub(
            "a-allowlisted.py",
            payload={"adapter": "stub", "schemaVersion": 1,
                     "error": "MODEL_MISMATCH", "flags": dict(FALSE_FLAGS)},
            exit_code=2,
        )
        proc = self.observe_with_stubs("gate-allow-a.db", stub_c2, stub_a)
        self.assert_error_payload(proc, "MODEL_MISMATCH", secrets=(stub_a,))

    def test_summary_echo_fields_are_bounded(self):
        marker = "ECHO-MARKER-" + "A" * 300
        stub_c = self.write_stub("c-ok-g7.py", payload=collector_ok_payload())
        stub_a = self.write_stub(
            "a-echo-junk.py",
            payload=adapter_ok_payload(provider=marker + "\x01tail", turnId="turn\x02id"),
        )
        proc = self.observe_with_stubs("gate-echo.db", stub_c, stub_a)
        payload = self.assert_ok_payload(proc, "TURN_UNKNOWN")
        self.assertEqual(payload["summary"]["provider"], "unknown")
        self.assertEqual(payload["summary"]["model"], "unknown")
        self.assertIsNone(payload["summary"]["turnId"])
        self.assert_no_echo(proc, "ECHO-MARKER")


if __name__ == "__main__":
    unittest.main(verbosity=2)
