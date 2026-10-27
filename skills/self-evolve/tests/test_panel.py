from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import panel
import render_panel
from proposal_store import ProposalStore, ProposalStoreCorruptionError


DEFAULT_ORIGIN = object()
TEST_ACCESS_TOKEN = "-".join(("test", "access", "token", "1234567890"))
TEST_SESSION_TOKEN = "-".join(("test", "session", "token", "123456789"))


def safe_panel_data() -> dict:
    return {
        "generated_at": "2026-07-18 12:00:00",
        "skill": {"name": "self-evolve", "version": "0.7.0", "mode": "cron-only"},
        "legacy_hook": {"status": "healthy", "status_label": "Cron-only 正常", "residue_count": 0, "entries": []},
        "scheduler": {"schema_version": "2.0", "config_label": "config/scheduled_tasks.yaml", "config_error": "", "tasks": [], "runs": []},
        "proposals": [],
        "inventory": {"count": 0, "generated_at": "", "schema_version": "2.0"},
        "clusters": {"count": 0, "generated_at": "", "quality": {}},
        "metrics": {"proposal_total": 0, "proposal_pending": 0, "inventory_count": 0, "cluster_count": 0, "task_count": 0},
    }


class PanelRenderTests(unittest.TestCase):
    def test_static_html_contains_no_private_paths_or_file_uri(self) -> None:
        data = safe_panel_data()
        data["proposals"] = [
            {
                "proposal_id": "prp-0123456789abcdef",
                "target_skill": "demo",
                "proposal_type": "upgrade",
                "summary": "safe",
                "change_points": [],
                "machine_disposition": "recommended",
                "privacy_status": "passed",
                "human_decision": "pending",
                "artifact_content_sha256": "0" * 64,
                "decision_reason": "",
                "updated_at": "",
            }
        ]
        html = render_panel.render_html(data, server_mode=False)
        self.assertNotIn("/Users/", html)
        self.assertNotIn("file://", html)
        self.assertNotIn("transcript_path", html)
        self.assertIn("Cron-only", html)
        self.assertNotIn("onclick", html.lower())
        self.assertIn("addEventListener", html)

    def test_legacy_hook_status_uses_shared_inspector_for_top_level_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            settings = Path(temporary) / "settings.json"
            settings.write_text(
                json.dumps(
                    {
                        "hooks": {
                            "SessionEnd": [
                                {
                                    "type": "command",
                                    "command": "python3 /tmp/self-evolve/scripts/sediment_guard.py",
                                },
                                {
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "command": "python3 /tmp/skill-evolve/scripts/sediment_guard.py",
                                        }
                                    ]
                                },
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            status = render_panel.collect_legacy_hook_status(settings)
        self.assertEqual(status["status"], "warning")
        self.assertEqual(status["residue_count"], 2)
        self.assertEqual(
            {(item["group_index"], item["hook_index"]) for item in status["entries"]},
            {(0, None), (1, 0)},
        )

    def test_safe_text_blocks_bearer_jwt_and_redacts_mounted_volume_paths(self) -> None:
        bearer = "Bearer " + "opaque-" + ("a" * 24)
        jwt = ".".join(("eyJ" + ("a" * 12), "eyJ" + ("b" * 12), "c" * 16))
        mounted_path = "/Volumes/CaseDrive/private/client.jsonl"

        self.assertEqual("<content-quarantined>", render_panel.safe_text(bearer))
        self.assertEqual("<content-quarantined>", render_panel.safe_text(jwt))
        sanitized = render_panel.safe_text(f"failed at {mounted_path}")
        self.assertNotIn(mounted_path, sanitized)
        self.assertIn("<private-path>", sanitized)


class PanelAuthorityTests(unittest.TestCase):
    def test_loopback_authority_supports_ipv4_and_bracketed_ipv6(self) -> None:
        self.assertEqual(panel.parse_loopback_authority("127.0.0.1:8765"), ("127.0.0.1", 8765))
        self.assertEqual(panel.parse_loopback_authority("[::1]:8765"), ("::1", 8765))
        self.assertTrue(panel.same_origin_loopback("http://[::1]:8765", ("::1", 8765)))

    def test_loopback_authority_rejects_names_non_loopback_and_missing_port(self) -> None:
        self.assertIsNone(panel.parse_loopback_authority("localhost:8765"))
        self.assertIsNone(panel.parse_loopback_authority("attacker.example:8765"))
        self.assertIsNone(panel.parse_loopback_authority("127.0.0.1"))
        self.assertFalse(panel.same_origin_loopback("https://127.0.0.1:8765", ("127.0.0.1", 8765)))


class PanelHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        inbox = root / "review" / "inbox"
        self.store = ProposalStore(
            root / "proposals",
            review_inbox_root=inbox,
            review_archive_root=root / "review" / "archive",
        )
        self.digest = hashlib.sha256(b"artifact").hexdigest()
        self.target_digest = hashlib.sha256(b"target skill").hexdigest()
        inbox.mkdir(parents=True)
        (inbox / "demo.md").write_bytes(b"artifact")
        self.record, _ = self.store.upsert(
            target_skill="demo",
            target_version="1.0.0",
            proposal_type="upgrade",
            change_points=["validation"],
            summary="safe",
            machine_disposition="recommended",
            evidence_ids=["ev-1"],
            artifact_paths=["review/inbox/demo.md"],
            privacy_status="passed",
            artifact_content_sha256=self.digest,
            target_content_sha256=self.target_digest,
            target_resolution="resolved",
        )
        self.data_patch = mock.patch.object(panel.render_panel, "build_panel_data", return_value=safe_panel_data())
        self.build_data_mock = self.data_patch.start()
        self.server = panel.PanelServer(
            ("127.0.0.1", 0),
            nonce="test-nonce",
            access_token=TEST_ACCESS_TOKEN,
            session_token=TEST_SESSION_TOKEN,
            limit=20,
            verbose=False,
            store=self.store,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.authority = f"127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.data_patch.stop()
        self.temp.cleanup()

    def request(self, request: urllib.request.Request) -> tuple[int, bytes, object]:
        opener = urllib.request.build_opener()
        try:
            with opener.open(request, timeout=3) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as exc:
            body = exc.read()
            headers = exc.headers
            status = exc.code
            exc.close()
            return status, body, headers

    def get(
        self,
        path: str,
        *,
        host: str | None = None,
        authenticated: bool = True,
        cookie_only: bool = False,
    ) -> tuple[int, bytes, object]:
        headers = {"Host": host} if host is not None else {}
        if authenticated:
            headers["Authorization"] = "Bearer " + TEST_SESSION_TOKEN
        if cookie_only:
            headers["Cookie"] = "self_evolve_session=" + TEST_SESSION_TOKEN
        return self.request(urllib.request.Request(self.base + path, headers=headers, method="GET"))

    def post(
        self,
        path: str,
        payload: dict,
        nonce: str = "test-nonce",
        *,
        host: str | None = None,
        origin: str | None | object = DEFAULT_ORIGIN,
        authenticated: bool = True,
    ) -> tuple[int, dict]:
        headers = {"Content-Type": "application/json", "X-Self-Evolve-Nonce": nonce}
        if authenticated:
            headers["Authorization"] = "Bearer " + TEST_SESSION_TOKEN
        if host is not None:
            headers["Host"] = host
        if origin is DEFAULT_ORIGIN:
            headers["Origin"] = self.base
        elif origin is not None:
            headers["Origin"] = str(origin)
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        status, body, _ = self.request(request)
        return status, json.loads(body)

    def test_server_html_uses_csp_nonce_and_has_no_inline_handlers(self) -> None:
        status, body, headers = self.get("/")
        html = body.decode("utf-8")
        csp = headers.get("Content-Security-Policy", "")
        self.assertEqual(status, 200)
        self.assertNotIn("script-src 'unsafe-inline'", csp)
        self.assertIn("script-src-attr 'none'", csp)
        match = re.search(r"script-src 'nonce-([^']+)'", csp)
        self.assertIsNotNone(match)
        self.assertIn(f'<script nonce="{match.group(1)}">', html)
        self.assertNotIn("onclick", html.lower())
        self.assertIn("sessionStorage", html)
        self.assertIn("Authorization", html)
        self.assertNotIn("test-nonce", html)
        self.assertNotIn("test-session-token", html)
        self.build_data_mock.assert_not_called()

    def test_anonymous_reads_and_writes_are_rejected_before_data_access(self) -> None:
        self.build_data_mock.reset_mock()
        status, body, headers = self.get("/", authenticated=False)
        self.assertEqual(200, status)
        self.assertNotIn("test-nonce", body.decode("utf-8"))
        self.assertNotIn("test-session-token", body.decode("utf-8"))
        self.assertNotIn("Set-Cookie", headers)
        self.build_data_mock.assert_not_called()

        status, body, headers = self.get("/api/proposals", authenticated=False)
        self.assertEqual(401, status)
        self.assertEqual("authentication_required", json.loads(body)["error"])
        self.assertNotIn("test-nonce", body.decode("utf-8"))
        self.assertNotIn("Set-Cookie", headers)
        self.build_data_mock.assert_not_called()

        status, body, _ = self.get("/api/proposals", authenticated=False, cookie_only=True)
        self.assertEqual(401, status)
        self.assertEqual("authentication_required", json.loads(body)["error"])

        status, payload = self.post(
            f"/api/proposals/{self.record['proposal_id']}/decision",
            {
                "decision": "accepted",
                "revision_hash": self.record["revision_hash"],
                "artifact_sha256": self.digest,
            },
            authenticated=False,
        )
        self.assertEqual(401, status)
        self.assertEqual("authentication_required", payload["error"])
        self.assertEqual("pending", self.store.load(self.record["proposal_id"])["human_decision"])

    def test_one_time_fragment_token_returns_explicit_session_bearer(self) -> None:
        status, payload = self.post(
            "/auth",
            {"token": TEST_ACCESS_TOKEN},
            authenticated=False,
            origin="http://attacker.example:8765",
        )
        self.assertEqual(403, status)
        self.assertEqual("invalid_origin", payload["error"])

        status, payload = self.post(
            "/auth",
            {"token": "wrong"},
            authenticated=False,
        )
        self.assertEqual(403, status)
        self.assertEqual("invalid_access_token", payload["error"])

        status, payload = self.post(
            "/auth",
            {"token": TEST_ACCESS_TOKEN},
            authenticated=False,
        )
        self.assertEqual(200, status)
        self.assertTrue(payload["ok"])
        self.assertEqual(TEST_SESSION_TOKEN, payload["session_token"])

        status, payload = self.post(
            "/auth",
            {"token": TEST_ACCESS_TOKEN},
            authenticated=False,
        )
        self.assertEqual(403, status)
        self.assertEqual("invalid_access_token", payload["error"])

    def test_get_and_post_reject_malicious_host_without_nonce_leak(self) -> None:
        self.build_data_mock.reset_mock()
        malicious_host = f"attacker.example:{self.server.server_address[1]}"
        status, body, headers = self.get("/", host=malicious_host)
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"], "invalid_host")
        self.assertNotIn(b"test-nonce", body)
        self.assertNotIn("test-nonce", str(headers))
        self.assertNotIn("Content-Security-Policy", headers)
        self.build_data_mock.assert_not_called()

        status, payload = self.post(
            f"/api/proposals/{self.record['proposal_id']}/decision",
            {
                "decision": "accepted",
                "revision_hash": self.record["revision_hash"],
                "artifact_sha256": self.digest,
            },
            host=malicious_host,
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "invalid_host")
        self.assertNotIn("test-nonce", json.dumps(payload))
        self.assertEqual(self.store.load(self.record["proposal_id"])["human_decision"], "pending")

    def test_post_rejects_cross_origin_and_missing_origin_without_nonce_leak(self) -> None:
        path = f"/api/proposals/{self.record['proposal_id']}/decision"
        decision = {
            "decision": "accepted",
            "revision_hash": self.record["revision_hash"],
            "artifact_sha256": self.digest,
        }
        status, payload = self.post(path, decision, origin="http://attacker.example:8765")
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "invalid_origin")
        self.assertNotIn("test-nonce", json.dumps(payload))

        status, payload = self.post(path, decision, origin=None)
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "invalid_origin")
        self.assertNotIn("test-nonce", json.dumps(payload))
        self.assertEqual(self.store.load(self.record["proposal_id"])["human_decision"], "pending")

    def test_nonce_unknown_id_and_accept_persist(self) -> None:
        path = f"/api/proposals/{self.record['proposal_id']}/decision"
        decision = {
            "decision": "accepted",
            "revision_hash": self.record["revision_hash"],
            "artifact_sha256": self.digest,
        }
        status, payload = self.post(path, decision, nonce="wrong")
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "invalid_nonce")

        status, payload = self.post(path, decision)
        self.assertEqual(status, 200)
        self.assertEqual(payload["human_decision"], "accepted")
        self.assertEqual(self.store.load(self.record["proposal_id"])["human_decision"], "accepted")

        status, _ = self.post(
            "/api/proposals/prp-ffffffffffffffff/decision",
            {
                "decision": "observe",
                "revision_hash": "0" * 64,
                "artifact_sha256": "0" * 64,
            },
        )
        self.assertEqual(status, 404)

    def test_missing_or_stale_revision_and_artifact_fail_closed(self) -> None:
        path = f"/api/proposals/{self.record['proposal_id']}/decision"
        status, payload = self.post(
            path,
            {"decision": "observe", "artifact_sha256": self.digest},
        )
        self.assertEqual(status, 409)

        status, payload = self.post(
            path,
            {
                "decision": "observe",
                "revision_hash": "0" * 64,
                "artifact_sha256": self.digest,
            },
        )
        self.assertEqual(status, 409)

        status, payload = self.post(
            path,
            {
                "decision": "observe",
                "revision_hash": self.record["revision_hash"],
                "artifact_sha256": "0" * 64,
            },
        )
        self.assertEqual(status, 409)
        self.assertEqual(self.store.load(self.record["proposal_id"])["human_decision"], "pending")

    def test_corrupt_proposal_log_is_reported_as_server_failure(self) -> None:
        self.store.events_dir.mkdir(parents=True, exist_ok=True)
        (self.store.events_dir / f"{self.record['proposal_id']}.jsonl").write_text(
            "{incomplete",
            encoding="utf-8",
        )
        status, payload = self.post(
            f"/api/proposals/{self.record['proposal_id']}/decision",
            {
                "decision": "observe",
                "revision_hash": self.record["revision_hash"],
                "artifact_sha256": self.digest,
            },
        )
        self.assertEqual(status, 500)
        self.assertEqual(payload["error"], "proposal_store_corrupt")
        self.assertNotIn("test-nonce", json.dumps(payload))

    def test_get_reports_corrupt_proposal_store_without_dropping_connection(self) -> None:
        self.build_data_mock.side_effect = ProposalStoreCorruptionError("private detail")
        status, body, _ = self.get("/api/proposals")
        payload = json.loads(body)
        self.assertEqual(status, 500)
        self.assertEqual(payload["error"], "proposal_store_corrupt")
        self.assertNotIn("private detail", json.dumps(payload))
        self.assertNotIn("test-nonce", json.dumps(payload))

    def test_task_execution_endpoint_does_not_exist(self) -> None:
        status, payload = self.post("/api/tasks/external/run-now", {})
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"], "not_found")


if __name__ == "__main__":
    unittest.main()
