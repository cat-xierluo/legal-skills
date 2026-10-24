#!/usr/bin/env python3
"""每日闭环（reconcile / receipt / lease）的离线行为回归。

覆盖：
- 写出反馈卡后 reconcile 立即把对应队列条目置为 judged；
- 没有反馈卡的条目保持未研判（不得标成已处理）；
- 租约互斥、过期接管、只释放自己的租约；
- 回执 judged/silent/failed 区分，silent 需要正向证据；
- 损坏租约/队列不崩溃，而是显式降级。

全部离线：不调用 gh、不访问网络。
运行：python3 -B tests/test_daily_loop.py
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import auto_discover as ad  # noqa: E402
import daily_loop as dl  # noqa: E402

NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)


def capture(func, args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = func(args)
    return code, json.loads(out.getvalue())


def feedback_card(project_id="demo-video", repo="sample/subtitle", repo_id=7,
                  capability="subtitle", recorded_at=NOW, status="rejected",
                  target_revision="t1", repo_revision="r1", evidence_revision="e1"):
    return {
        "scope": "direction",
        "target": {"project_id": project_id, "target_revision": target_revision,
                   "capability_key": capability},
        "signal": {"repo": repo, "repo_id": repo_id, "repo_revision": repo_revision,
                   "evidence_revision": evidence_revision},
        "decision": {"status": status, "reason": "not now"},
        "_recorded_at": recorded_at.isoformat(),
        "_schema": "opportunity-card/1.1",
    }


def queue_entry(candidate_key="k1", project_id="demo-video", repo="sample/subtitle",
                repo_id=7, capability="subtitle", state="shown",
                target_revision="t1", repo_revision="r1", evidence_revision="e1",
                first_seen_at=NOW):
    return {
        "candidate_key": candidate_key, "project_id": project_id, "repo_id": repo_id,
        "repo": repo, "capability_key": capability, "capability_label": "subtitle",
        "scope": "direction", "state": state,
        "first_seen_at": first_seen_at.isoformat(),
        "last_shown_at": first_seen_at.isoformat(), "shown_count": 1,
        "last_target_revision": target_revision, "last_repo_revision": repo_revision,
        "last_evidence_revision": evidence_revision,
    }


class DailyLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / "data"
        self.data.mkdir(parents=True)

    # ---------- reconcile ----------

    def write_queue(self, entries, schema=None):
        value = {"schema_version": schema or ad.QUEUE_SCHEMA,
                 "entries": {entry["candidate_key"]: entry for entry in entries},
                 "cursor": {"round_seq": 1, "last_round_at": NOW.isoformat()}}
        ad.atomic_json(self.data / ad.QUEUE_FILE, value)
        return value

    def write_card(self, card, name="decision.json"):
        ad.atomic_json(self.data / "feedback" / name, card)

    def test_card_makes_queue_entry_judged_on_reconcile(self):
        self.write_queue([queue_entry()])
        self.write_card(feedback_card())
        result, code = ad.reconcile_queue(self.data, now=NOW)
        self.assertEqual(code, 0)
        self.assertEqual(result["newly_judged_count"], 1)
        self.assertEqual(result["newly_judged"][0]["candidate_key"], "k1")
        self.assertEqual(result["newly_judged"][0]["judged_ref"], "decision.json")
        stored = ad.read_json(self.data / ad.QUEUE_FILE)
        self.assertEqual(stored["entries"]["k1"]["state"], "judged")
        self.assertEqual(stored["entries"]["k1"]["judged_ref"], "decision.json")
        self.assertEqual(result["backlog"]["pending_total"], 0)

    def test_entry_without_card_is_not_marked_judged(self):
        self.write_queue([queue_entry()])
        result, code = ad.reconcile_queue(self.data, now=NOW)
        self.assertEqual(code, 0)
        self.assertEqual(result["newly_judged_count"], 0)
        stored = ad.read_json(self.data / ad.QUEUE_FILE)
        self.assertEqual(stored["entries"]["k1"]["state"], "shown")
        self.assertNotIn("judged_ref", stored["entries"]["k1"])
        self.assertEqual(result["backlog"]["pending_total"], 1)

    def test_reconcile_is_idempotent(self):
        self.write_queue([queue_entry()])
        self.write_card(feedback_card())
        ad.reconcile_queue(self.data, now=NOW)
        second, code = ad.reconcile_queue(self.data, now=NOW + timedelta(minutes=5))
        self.assertEqual(code, 0)
        self.assertEqual(second["newly_judged_count"], 0)
        stored = ad.read_json(self.data / ad.QUEUE_FILE)
        self.assertEqual(stored["entries"]["k1"]["state"], "judged")

    def test_stale_revision_does_not_mark_judged(self):
        self.write_queue([queue_entry(evidence_revision="e-new")])
        self.write_card(feedback_card(evidence_revision="e-old"))
        result, _ = ad.reconcile_queue(self.data, now=NOW)
        self.assertEqual(result["newly_judged_count"], 0)
        stored = ad.read_json(self.data / ad.QUEUE_FILE)
        self.assertEqual(stored["entries"]["k1"]["state"], "shown")

    def test_corrupt_queue_degrades_without_crash_or_overwrite(self):
        path = self.data / ad.QUEUE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{broken", encoding="utf-8")
        before = path.read_bytes()
        result, code = ad.reconcile_queue(self.data, now=NOW)
        self.assertEqual(code, 1)
        self.assertTrue(result["degraded"])
        self.assertTrue(result["errors"])
        self.assertEqual(path.read_bytes(), before)
        self.assertTrue(list(path.parent.glob("review-queue.json.corrupt-*")))

    def test_reconcile_cli_exit_code(self):
        self.write_queue([queue_entry()])
        self.write_card(feedback_card())
        run = subprocess.run([sys.executable, "-B", str(SCRIPTS / "auto_discover.py"),
                              "reconcile", "--data-dir", str(self.data)],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0)
        payload = json.loads(run.stdout)
        self.assertEqual(payload["newly_judged_count"], 1)

    def test_reconcile_cli_runs_without_gh_on_path(self):
        self.write_queue([queue_entry()])
        run = subprocess.run([sys.executable, "-B", str(SCRIPTS / "auto_discover.py"),
                              "reconcile", "--data-dir", str(self.data)],
                             capture_output=True, text=True,
                             env={"PATH": "/nonexistent", "HOME": str(self.data)})
        self.assertEqual(run.returncode, 0)
        self.assertIn("newly_judged", json.loads(run.stdout))

    # ---------- lease ----------

    def test_lease_is_mutually_exclusive(self):
        lease, notes = dl.acquire_lease(self.data, "owner-a", run_id="r1",
                                         ttl_seconds=600, now=NOW)
        self.assertEqual(lease["owner"], "owner-a")
        with self.assertRaises(dl.LeaseConflict):
            dl.acquire_lease(self.data, "owner-b", run_id="r2",
                             ttl_seconds=600, now=NOW + timedelta(seconds=10))
        stored = json.loads(dl.lease_path(self.data).read_text(encoding="utf-8"))
        self.assertEqual(stored["owner"], "owner-a")
        self.assertEqual(stored["run_id"], "r1")

    def test_expired_lease_can_be_taken_over(self):
        dl.acquire_lease(self.data, "owner-a", run_id="r1", ttl_seconds=60, now=NOW)
        lease, notes = dl.acquire_lease(self.data, "owner-b", run_id="r2",
                                        ttl_seconds=60, now=NOW + timedelta(seconds=120))
        self.assertEqual(lease["owner"], "owner-b")
        self.assertTrue(any("接管过期租约" in note for note in notes))

    def test_same_owner_can_renew(self):
        dl.acquire_lease(self.data, "owner-a", run_id="r1", ttl_seconds=60, now=NOW)
        lease, notes = dl.acquire_lease(self.data, "owner-a", run_id="r1",
                                        ttl_seconds=60, now=NOW + timedelta(seconds=10))
        self.assertEqual(lease["owner"], "owner-a")
        self.assertTrue(any("续租" in note for note in notes))

    def test_release_only_removes_own_lease(self):
        dl.acquire_lease(self.data, "owner-a", run_id="r1", ttl_seconds=600, now=NOW)
        other = dl.release_lease(self.data, "owner-b")
        self.assertFalse(other["released"])
        self.assertTrue(dl.lease_path(self.data).exists())
        own = dl.release_lease(self.data, "owner-a", run_id="r1")
        self.assertTrue(own["released"])
        self.assertFalse(dl.lease_path(self.data).exists())

    def test_release_refuses_mismatched_run_id(self):
        dl.acquire_lease(self.data, "owner-a", run_id="r1", ttl_seconds=600, now=NOW)
        result = dl.release_lease(self.data, "owner-a", run_id="other")
        self.assertFalse(result["released"])
        self.assertTrue(dl.lease_path(self.data).exists())

    def test_corrupt_lease_degrades_and_is_quarantined(self):
        path = dl.lease_path(self.data)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{broken", encoding="utf-8")
        lease, notes = dl.acquire_lease(self.data, "owner-a", run_id="r1",
                                        ttl_seconds=600, now=NOW)
        self.assertEqual(lease["owner"], "owner-a")
        self.assertTrue(any("损坏租约" in note for note in notes))
        self.assertTrue(list(path.parent.glob("lease.json.corrupt-*")))

    def test_lease_cli_conflict_exit_code_is_one(self):
        dl.acquire_lease(self.data, "owner-a", run_id="r1", ttl_seconds=600)
        run = subprocess.run([sys.executable, "-B", str(SCRIPTS / "auto_discover.py"),
                              "lease", "acquire", "--data-dir", str(self.data),
                              "--owner", "owner-b"],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        payload = json.loads(run.stdout)
        self.assertFalse(payload["acquired"])
        self.assertTrue(payload["conflict"])

    def test_lease_cli_status_and_release(self):
        run = subprocess.run([sys.executable, "-B", str(SCRIPTS / "auto_discover.py"),
                              "lease", "acquire", "--data-dir", str(self.data),
                              "--owner", "owner-a", "--run-id", "r1"],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0)
        run = subprocess.run([sys.executable, "-B", str(SCRIPTS / "auto_discover.py"),
                              "lease", "release", "--data-dir", str(self.data),
                              "--owner", "owner-a", "--run-id", "r1"],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0)
        self.assertTrue(json.loads(run.stdout)["released"])

    # ---------- receipt ----------

    def write_run(self, candidates=0, generated_at=NOW, budget=None):
        directory = self.data / "auto-opportunities" / "runs"
        directory.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": "1.0", "generated_at": generated_at.isoformat(),
                   "status": "ok", "items": [{"x": i} for i in range(candidates)],
                   "coverage": {"watch_coverage": {"request_budget": budget}}}
        path = directory / (generated_at.strftime("%Y%m%dT%H%M%S.%fZ") + ".json")
        ad.atomic_json(path, payload)
        return path

    def test_receipt_judged_when_card_written(self):
        self.write_run(candidates=2, generated_at=NOW)
        self.write_queue([queue_entry()])
        self.write_card(feedback_card(recorded_at=NOW + timedelta(minutes=1)))
        payload, code = ad.build_receipt(self.data, now=NOW + timedelta(minutes=2))
        self.assertEqual(code, 0)
        receipt = payload["receipt"]
        self.assertEqual(receipt["outcome"], "judged")
        self.assertEqual(receipt["cards_written"], 1)
        self.assertEqual(receipt["reconcile"]["newly_judged_count"], 1)
        self.assertEqual(receipt["reconcile"]["judged_total"], 1)
        self.assertEqual(receipt["reconcile"]["cards_now_judged"], 1)
        # 只有拒绝/暂缓类判断 → 不打扰用户
        self.assertFalse(receipt["notification"]["recommended"])

    def test_receipt_silent_requires_positive_evidence(self):
        self.write_run(candidates=0, generated_at=NOW)
        payload, code = ad.build_receipt(self.data, now=NOW + timedelta(minutes=1))
        self.assertEqual(code, 0)
        receipt = payload["receipt"]
        self.assertEqual(receipt["outcome"], "silent")
        self.assertEqual(receipt["evidence"]["candidates"], 0)
        self.assertEqual(receipt["evidence"]["queue_new_pending"], 0)
        self.assertEqual(receipt["evidence"]["queue_new_unjudged"], 0)
        self.assertEqual(receipt["cards_written"], 0)

    def test_receipt_silent_with_only_historical_backlog(self):
        # 历史积压（早于本轮）不阻断静默——相同未恢复问题不每天重报
        self.write_run(candidates=0, generated_at=NOW)
        self.write_queue([queue_entry(first_seen_at=NOW - timedelta(days=3))])
        payload, code = ad.build_receipt(self.data, now=NOW + timedelta(minutes=1))
        self.assertEqual(code, 0)
        receipt = payload["receipt"]
        self.assertEqual(receipt["outcome"], "silent")
        self.assertEqual(receipt["evidence"]["queue_new_unjudged"], 0)
        # 积压仍然披露
        self.assertEqual(receipt["evidence"]["backlog_pending_total"], 1)
        self.assertFalse(receipt["notification"]["recommended"])

    def test_receipt_not_silent_when_new_item_surfaced(self):
        # 本轮新出现的候选（候选数>0）且无卡片 → 失败，不静默
        self.write_run(candidates=1, generated_at=NOW)
        self.write_queue([queue_entry(first_seen_at=NOW)])
        payload, code = ad.build_receipt(self.data, now=NOW + timedelta(minutes=1))
        self.assertEqual(code, 1)
        receipt = payload["receipt"]
        self.assertEqual(receipt["outcome"], "failed")
        self.assertEqual(receipt["facts"]["new_unjudged"], 1)

    def test_receipt_failed_without_run_package(self):
        # 没有准备阶段运行包 → 无法取得"候选数=0"的正向证据 → failed，不得 silent
        payload, code = ad.build_receipt(self.data, now=NOW)
        self.assertEqual(code, 1)
        receipt = payload["receipt"]
        self.assertEqual(receipt["outcome"], "failed")
        self.assertTrue(any("正向证据" in error for error in receipt["errors"]))
        # 历史反馈卡不算作本轮写入
        self.assertEqual(receipt["cards_written"], 0)

    def test_receipt_without_run_package_ignores_old_cards(self):
        # 旧卡片存在但没有本轮运行包 → 卡片不计入本轮；但 reconcile 真实判为
        # judged 时结局仍是 judged，且缺运行包必须留显式警告，不得静默。
        self.write_queue([queue_entry()])
        self.write_card(feedback_card(recorded_at=NOW - timedelta(days=2)))
        payload, code = ad.build_receipt(self.data, now=NOW)
        receipt = payload["receipt"]
        self.assertEqual(receipt["cards_written"], 0)
        self.assertEqual(receipt["outcome"], "judged")
        self.assertEqual(receipt["reconcile"]["newly_judged_count"], 1)
        self.assertTrue(any("运行包" in warning for warning in receipt["warnings"]))

    def test_receipt_notifies_on_actionable_card(self):
        self.write_run(candidates=1, generated_at=NOW)
        self.write_queue([queue_entry()])
        self.write_card(feedback_card(recorded_at=NOW + timedelta(minutes=1),
                                      status="experiment_proposed"))
        payload, code = ad.build_receipt(self.data, now=NOW + timedelta(minutes=2))
        receipt = payload["receipt"]
        self.assertEqual(receipt["outcome"], "judged")
        self.assertTrue(receipt["notification"]["recommended"])

    def test_receipt_silent_rejected_when_candidates_exist(self):
        self.write_run(candidates=3, generated_at=NOW)
        payload, code = ad.build_receipt(self.data, outcome="silent", now=NOW + timedelta(minutes=1))
        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertIn("silent", payload["error"])

    def test_receipt_failed_when_candidates_but_no_cards(self):
        self.write_run(candidates=3, generated_at=NOW)
        payload, code = ad.build_receipt(self.data, now=NOW + timedelta(minutes=1))
        self.assertEqual(code, 1)
        receipt = payload["receipt"]
        self.assertEqual(receipt["outcome"], "failed")
        self.assertTrue(receipt["errors"])
        self.assertTrue(receipt["notification"]["recommended"])

    def test_receipt_failed_when_agent_crashed(self):
        self.write_run(candidates=0, generated_at=NOW)
        payload, code = ad.build_receipt(self.data, errors=["Agent 崩溃：进程退出码 1"],
                                        now=NOW + timedelta(minutes=1))
        self.assertEqual(code, 1)
        receipt = payload["receipt"]
        self.assertEqual(receipt["outcome"], "failed")
        self.assertIn("Agent 崩溃：进程退出码 1", receipt["errors"])

    def test_receipt_records_budget_and_notification(self):
        budget = {"limit": 60, "used": 12, "by_kind": {"refresh": 3}, "exhausted": False}
        self.write_run(candidates=1, generated_at=NOW, budget=budget)
        self.write_queue([queue_entry()])
        self.write_card(feedback_card(recorded_at=NOW + timedelta(minutes=1)))
        payload, code = ad.build_receipt(self.data, now=NOW + timedelta(minutes=2))
        receipt = payload["receipt"]
        self.assertEqual(receipt["request_budget"], budget)
        self.assertIn("notification", receipt)
        self.assertEqual(receipt["facts"]["candidates"], 1)

    def test_receipt_file_is_written_under_runs(self):
        self.write_run(candidates=0, generated_at=NOW)
        args = SimpleNamespace(data_dir=self.data, outcome=None, error=None,
                               notify=None, notify_reason=None)
        code, result = capture(ad.cmd_receipt, args)
        self.assertEqual(code, 0)
        path = Path(result["receipt_path"])
        self.assertTrue(path.exists())
        self.assertIn(".receipt.json", path.name)
        stored = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(stored["outcome"], "silent")

    def test_receipt_cli_failed_exit_code(self):
        self.write_run(candidates=2, generated_at=NOW)
        run = subprocess.run([sys.executable, "-B", str(SCRIPTS / "auto_discover.py"),
                              "receipt", "--data-dir", str(self.data)],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        self.assertEqual(json.loads(run.stdout)["outcome"], "failed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
