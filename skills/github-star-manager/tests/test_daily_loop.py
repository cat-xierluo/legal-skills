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
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

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

    def write_run(self, candidates=0, generated_at=NOW, budget=None,
                  quota=None, coverage_cycle=None):
        directory = self.data / "auto-opportunities" / "runs"
        directory.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": "1.0", "generated_at": generated_at.isoformat(),
                   "status": "ok", "items": [{"x": i} for i in range(candidates)],
                   "coverage": {"watch_coverage": {"request_budget": budget}}}
        if quota is not None:
            payload["coverage"]["review_queue"] = {"quota": quota}
        if coverage_cycle is not None:
            payload["coverage"].setdefault("review_queue", {})["coverage_cycle"] = coverage_cycle
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

    def test_receipt_carries_the_round_quota_and_coverage_cycle(self):
        # The receipt has to say where the candidates came from. A round that
        # served the backlog instead of the evidence channel must be visible
        # without re-reading the run package.
        quota = {"backlog_reserve": 2, "backlog_reserved_slots": 2,
                 "evidence_slots": 0, "sources_by_count": {"backlog": 2}}
        cycle = {"never_shown_pending": 100, "backlog_slots_per_round": 2,
                 "estimated_rounds_to_cover": 50, "observed_rounds_per_day": 1.0,
                 "estimated_days_to_cover": 50.0}
        self.write_run(candidates=2, generated_at=NOW,
                       quota=quota, coverage_cycle=cycle)
        self.write_queue([queue_entry()])
        self.write_card(feedback_card(recorded_at=NOW + timedelta(seconds=30)))
        payload, code = ad.build_receipt(self.data, now=NOW + timedelta(minutes=1))
        self.assertEqual(code, 0)
        receipt = payload["receipt"]
        self.assertEqual(receipt["queue_quota"], quota)
        self.assertEqual(receipt["coverage_cycle"], cycle)

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
        # 运行包必须是"本轮"的：cmd_receipt 用真实当前时间判定新鲜度，
        # 固定在 NOW（2026-10-22）的运行包在新鲜度规则下已过期。
        fresh = datetime.now(timezone.utc)
        self.write_run(candidates=0, generated_at=fresh)
        args = SimpleNamespace(data_dir=self.data, outcome=None, error=None,
                               notify=None, notify_reason=None,
                               max_run_age_hours=ad.DEFAULT_MAX_RUN_AGE_HOURS)
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


class ReviewFixRegressionTests(unittest.TestCase):
    """PR #341 独立审查 5 项缺陷的回归覆盖（P1-1/P1-2/P1-3/P2-1/P2-2）。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / "data"
        self.data.mkdir(parents=True)

    def write_run(self, candidates=0, generated_at=None, budget=None, items=None):
        generated_at = generated_at or datetime.now(timezone.utc)
        directory = self.data / "auto-opportunities" / "runs"
        directory.mkdir(parents=True, exist_ok=True)
        rows = items if items is not None else [{"x": i} for i in range(candidates)]
        payload = {"schema_version": "1.0", "generated_at": generated_at.isoformat(),
                   "status": "ok", "items": rows,
                   "coverage": {"watch_coverage": {"request_budget": budget}}}
        path = directory / (generated_at.strftime("%Y%m%dT%H%M%S.%fZ") + ".json")
        ad.atomic_json(path, payload)
        return path

    def write_queue(self, entries):
        value = {"schema_version": ad.QUEUE_SCHEMA,
                 "entries": {entry["candidate_key"]: entry for entry in entries},
                 "cursor": {"round_seq": 1, "last_round_at": NOW.isoformat()}}
        ad.atomic_json(self.data / ad.QUEUE_FILE, value)
        return value

    def write_card(self, card, name="decision.json"):
        ad.atomic_json(self.data / "feedback" / name, card)

    def card(self, recorded_at=None, status="rejected"):
        recorded_at = recorded_at or datetime.now(timezone.utc)
        return {
            "scope": "direction",
            "target": {"project_id": "demo-video", "target_revision": "t1",
                       "capability_key": "subtitle"},
            "signal": {"repo": "sample/subtitle", "repo_id": 7,
                       "repo_revision": "r1", "evidence_revision": "e1"},
            "decision": {"status": status, "reason": "not now"},
            "_recorded_at": recorded_at.isoformat(),
            "_schema": "opportunity-card/1.1",
        }

    def entry(self, state="shown", first_seen_at=None):
        first_seen_at = first_seen_at or datetime.now(timezone.utc)
        return {
            "candidate_key": "k1", "project_id": "demo-video", "repo_id": 7,
            "repo": "sample/subtitle", "capability_key": "subtitle",
            "capability_label": "subtitle", "scope": "direction", "state": state,
            "first_seen_at": first_seen_at.isoformat(),
            "last_shown_at": first_seen_at.isoformat(), "shown_count": 1,
            "last_target_revision": "t1", "last_repo_revision": "r1",
            "last_evidence_revision": "e1",
        }

    # ---------- P1-1：--outcome auto 必须可用（不是 argparse 退出码 2）----------

    def test_p1_1_receipt_cli_accepts_outcome_auto(self):
        run = subprocess.run([sys.executable, "-B", str(SCRIPTS / "auto_discover.py"),
                              "receipt", "--data-dir", str(self.data),
                              "--outcome", "auto"],
                             capture_output=True, text=True)
        # 不得是 argparse 的 invalid choice（退出码 2）
        self.assertNotEqual(run.returncode, 2, run.stderr)
        payload = json.loads(run.stdout)
        self.assertEqual(payload["requested_outcome"], "auto")
        # 没有准备阶段运行包 → 事实不支持任何结论 → failed（退出码 1）
        self.assertEqual(payload["outcome"], "failed")
        self.assertEqual(run.returncode, 1)

    def test_p1_1_receipt_cli_without_outcome_matches_auto(self):
        self.write_run(candidates=0)
        args = [sys.executable, "-B", str(SCRIPTS / "auto_discover.py"),
                "receipt", "--data-dir", str(self.data)]
        plain = subprocess.run(args, capture_output=True, text=True)
        auto = subprocess.run(args + ["--outcome", "auto"], capture_output=True, text=True)
        self.assertEqual(plain.returncode, 0)
        self.assertEqual(auto.returncode, 0)
        self.assertEqual(json.loads(plain.stdout)["outcome"],
                         json.loads(auto.stdout)["outcome"])
        self.assertEqual(json.loads(auto.stdout)["outcome"], "silent")

    def test_p1_1_receipt_outcome_auto_is_documented_behaviour(self):
        # auto 与不传等价：显式 judged 仍须有证据，auto 走事实判定
        self.write_run(candidates=0)
        payload, code = ad.build_receipt(self.data, outcome=None, requested="auto",
                                         now=datetime.now(timezone.utc))
        self.assertEqual(code, 0)
        self.assertEqual(payload["receipt"]["outcome"], "silent")

    # ---------- P1-2：显式 judged 也必须过事实校验 ----------

    def test_p1_2_explicit_judged_without_evidence_is_downgraded(self):
        # 复现 A：空数据目录 + receipt --outcome judged
        run = subprocess.run([sys.executable, "-B", str(SCRIPTS / "auto_discover.py"),
                              "receipt", "--data-dir", str(self.data),
                              "--outcome", "judged"],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        payload = json.loads(run.stdout)
        self.assertEqual(payload["outcome"], "failed")
        self.assertEqual(payload["facts"]["cards_written"], 0)
        self.assertEqual(payload["facts"]["newly_judged"], 0)
        self.assertTrue(payload["errors"])
        # 不得写出与事实矛盾的 statement
        self.assertNotIn("写出反馈卡并完成对账",
                         payload["evidence"]["statement"])

    def test_p1_2_explicit_judged_with_corrupt_queue_is_downgraded(self):
        # 复现 B：损坏的研判队列 + receipt --outcome judged
        path = self.data / ad.QUEUE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{broken", encoding="utf-8")
        run = subprocess.run([sys.executable, "-B", str(SCRIPTS / "auto_discover.py"),
                              "receipt", "--data-dir", str(self.data),
                              "--outcome", "judged"],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        payload = json.loads(run.stdout)
        self.assertEqual(payload["outcome"], "failed")
        self.assertEqual(payload["facts"]["queue_state"], "degraded")
        self.assertTrue(any("队列" in error for error in payload["errors"]))

    def test_p1_2_explicit_judged_with_real_evidence_is_kept(self):
        self.write_run(candidates=1)
        self.write_queue([self.entry()])
        self.write_card(self.card())
        run = subprocess.run([sys.executable, "-B", str(SCRIPTS / "auto_discover.py"),
                              "receipt", "--data-dir", str(self.data),
                              "--outcome", "judged"],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0)
        payload = json.loads(run.stdout)
        self.assertEqual(payload["outcome"], "judged")
        self.assertEqual(payload["facts"]["cards_written"], 1)

    def test_p1_2_explicit_failed_is_preserved(self):
        # Agent 主动报错是合法意图，显式 failed 必须保留
        self.write_run(candidates=0)
        run = subprocess.run([sys.executable, "-B", str(SCRIPTS / "auto_discover.py"),
                              "receipt", "--data-dir", str(self.data),
                              "--outcome", "failed", "--error", "Agent 崩溃"],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        payload = json.loads(run.stdout)
        self.assertEqual(payload["outcome"], "failed")
        self.assertIn("Agent 崩溃", payload["errors"])

    def test_p1_2_explicit_silent_still_requires_positive_evidence(self):
        self.write_run(candidates=3)
        run = subprocess.run([sys.executable, "-B", str(SCRIPTS / "auto_discover.py"),
                              "receipt", "--data-dir", str(self.data),
                              "--outcome", "silent"],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        payload = json.loads(run.stdout)
        self.assertFalse(payload["ok"])
        self.assertIn("silent", payload["error"])

    # ---------- P1-3：运行包新鲜度 ----------

    def test_p1_3_stale_run_package_is_not_silent(self):
        # 复现：昨天（或任意旧日期）的运行包 + 今天跑 receipt
        old = datetime.now(timezone.utc) - timedelta(days=2)
        self.write_run(candidates=1, generated_at=old)
        self.write_queue([self.entry(first_seen_at=old)])
        self.write_card(self.card(recorded_at=old), name="old.json")
        run = subprocess.run([sys.executable, "-B", str(SCRIPTS / "auto_discover.py"),
                              "receipt", "--data-dir", str(self.data)],
                             capture_output=True, text=True)
        payload = json.loads(run.stdout)
        # 长时间停机不得被记成"本轮无变化"的零警告静默成功
        self.assertNotEqual(payload["outcome"], "silent")
        self.assertTrue(payload["warnings"])
        self.assertTrue(payload["facts"]["stale_run"])
        # 旧运行包之后的卡片不计入本轮
        self.assertEqual(payload["facts"]["cards_written"], 0)
        self.assertEqual(payload["facts"]["candidates"], 0)

    def test_p1_3_stale_run_package_with_no_judged_evidence_fails(self):
        # 过期运行包 + 无任何研判证据 → failed（不得静默）
        old = datetime.now(timezone.utc) - timedelta(days=2)
        self.write_run(candidates=0, generated_at=old)
        run = subprocess.run([sys.executable, "-B", str(SCRIPTS / "auto_discover.py"),
                              "receipt", "--data-dir", str(self.data)],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        payload = json.loads(run.stdout)
        self.assertEqual(payload["outcome"], "failed")
        self.assertTrue(payload["errors"])
        self.assertTrue(any("过期" in warning for warning in payload["warnings"]))

    def test_p1_3_stale_run_package_not_counted_as_candidates(self):
        old = datetime.now(timezone.utc) - timedelta(hours=30)
        self.write_run(candidates=5, generated_at=old)
        payload, code = ad.build_receipt(self.data, now=datetime.now(timezone.utc))
        self.assertEqual(code, 1)
        receipt = payload["receipt"]
        self.assertEqual(receipt["facts"]["candidates"], 0)
        self.assertTrue(receipt["facts"]["stale_run"])
        self.assertEqual(receipt["outcome"], "failed")

    def test_p1_3_max_run_age_hours_override(self):
        # 阈值可覆盖：把阈值调大后旧运行包重新有效
        old = datetime.now(timezone.utc) - timedelta(hours=30)
        self.write_run(candidates=0, generated_at=old)
        payload, code = ad.build_receipt(self.data, max_run_age_hours=48,
                                         now=datetime.now(timezone.utc))
        self.assertEqual(code, 0)
        self.assertEqual(payload["receipt"]["outcome"], "silent")
        self.assertFalse(payload["receipt"]["facts"]["stale_run"])

    def test_p1_3_fresh_run_package_still_allows_silent(self):
        self.write_run(candidates=0)
        payload, code = ad.build_receipt(self.data, now=datetime.now(timezone.utc))
        self.assertEqual(code, 0)
        self.assertEqual(payload["receipt"]["outcome"], "silent")
        self.assertFalse(payload["receipt"]["facts"]["stale_run"])

    # ---------- P2-1：隔离失败不得销毁原始损坏内容 ----------

    def test_p2_1_quarantine_failure_preserves_original_content(self):
        path = dl.lease_path(self.data)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{broken original", encoding="utf-8")
        before = path.read_bytes()
        with mock.patch.object(dl, "_quarantine", return_value=None):
            with self.assertRaises(dl.LeaseError) as caught:
                dl.acquire_lease(self.data, "owner-a", run_id="r1")
        self.assertIn("隔离失败", str(caught.exception))
        # 原始损坏内容必须一字未改
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(path.read_text(encoding="utf-8"), "{broken original")

    def test_p2_1_quarantine_failure_via_cli_reports_error(self):
        path = dl.lease_path(self.data)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{broken original", encoding="utf-8")
        before = path.read_bytes()
        script = ("import sys, runpy\n"
                  "sys.path.insert(0, %r)\n"
                  "import daily_loop as dl\n"
                  "dl._quarantine = lambda path: None\n"
                  "sys.argv = ['auto_discover.py', 'lease', 'acquire', "
                  "'--data-dir', %r, '--owner', 'owner-a']\n"
                  "runpy.run_path(%r, run_name='__main__')\n")
        run = subprocess.run([sys.executable, "-B", "-c",
                              script % (str(SCRIPTS), str(self.data),
                                        str(SCRIPTS / "auto_discover.py"))],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        payload = json.loads(run.stdout)
        self.assertFalse(payload["acquired"])
        self.assertTrue(payload["error"])
        self.assertEqual(path.read_bytes(), before)

    def test_p2_1_successful_quarantine_still_preserves_content(self):
        path = dl.lease_path(self.data)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{broken original", encoding="utf-8")
        lease, notes = dl.acquire_lease(self.data, "owner-a", run_id="r1")
        self.assertEqual(lease["owner"], "owner-a")
        self.assertTrue(any("隔离" in note for note in notes))
        backups = list(path.parent.glob("lease.json.corrupt-*"))
        self.assertTrue(backups)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "{broken original")

    # ---------- P2-2：同 owner 续租保留 run_id ----------

    def test_p2_2_same_owner_renew_keeps_run_id(self):
        lease, _ = dl.acquire_lease(self.data, "owner-a", run_id="r1",
                                     ttl_seconds=600)
        self.assertEqual(lease["run_id"], "r1")
        renewed, notes = dl.acquire_lease(self.data, "owner-a")
        self.assertEqual(renewed["run_id"], "r1")
        self.assertTrue(any("保留原运行 ID" in note for note in notes))
        # 原 run_id 仍可用于释放
        released = dl.release_lease(self.data, "owner-a", run_id="r1")
        self.assertTrue(released["released"])
        self.assertFalse(dl.lease_path(self.data).exists())

    def test_p2_2_explicit_new_run_id_switches_and_is_documented(self):
        dl.acquire_lease(self.data, "owner-a", run_id="r1", ttl_seconds=600)
        renewed, notes = dl.acquire_lease(self.data, "owner-a", run_id="r2")
        self.assertEqual(renewed["run_id"], "r2")
        self.assertTrue(any("运行 ID 切换" in note for note in notes))

    def test_p2_2_takeover_of_expired_lease_gets_new_run_id(self):
        now = datetime.now(timezone.utc)
        dl.acquire_lease(self.data, "owner-a", run_id="r1", ttl_seconds=60, now=now)
        lease, _ = dl.acquire_lease(self.data, "owner-b", ttl_seconds=600,
                                     now=now + timedelta(seconds=120))
        self.assertNotEqual(lease["run_id"], "r1")
        self.assertEqual(lease["owner"], "owner-b")

    def test_p2_2_cli_renew_keeps_run_id(self):
        acquire = subprocess.run([sys.executable, "-B", str(SCRIPTS / "auto_discover.py"),
                                  "lease", "acquire", "--data-dir", str(self.data),
                                  "--owner", "owner-a", "--run-id", "r1"],
                                 capture_output=True, text=True)
        self.assertEqual(acquire.returncode, 0)
        renew = subprocess.run([sys.executable, "-B", str(SCRIPTS / "auto_discover.py"),
                                "lease", "acquire", "--data-dir", str(self.data),
                                "--owner", "owner-a"],
                               capture_output=True, text=True)
        self.assertEqual(renew.returncode, 0)
        self.assertEqual(json.loads(renew.stdout)["lease"]["run_id"], "r1")
        release = subprocess.run([sys.executable, "-B", str(SCRIPTS / "auto_discover.py"),
                                  "lease", "release", "--data-dir", str(self.data),
                                  "--owner", "owner-a", "--run-id", "r1"],
                                 capture_output=True, text=True)
        self.assertEqual(release.returncode, 0)
        self.assertTrue(json.loads(release.stdout)["released"])


class UnreadableRunPackageRegressionTests(unittest.TestCase):
    """运行包不可读/格式异常时的回执判定回归（PR #341 第二轮 F1）。

    缺陷：不可读或格式异常的运行包会提前 return，跳过新鲜度判定，于是
    stale_run 恒为 False、run_age_hours 恒为 None；候选数按 0 计使
    outcome 落进 silent 分支——长时间停机 + 运行包损坏变成零警告静默成功。
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / "data"
        self.data.mkdir(parents=True)
        self.runs = self.data / "auto-opportunities" / "runs"
        self.runs.mkdir(parents=True)

    def write_broken_run(self, content="{broken", age_hours=None, name=None):
        """写一个内容损坏或格式异常的运行包，可选回拨 mtime。"""
        name = name or "20260101T000000.000000Z.json"
        path = self.runs / name
        path.write_text(content, encoding="utf-8")
        if age_hours is not None:
            stamp = time.time() - age_hours * 3600
            os.utime(path, (stamp, stamp))
        return path

    def write_queue(self, entries):
        value = {"schema_version": ad.QUEUE_SCHEMA,
                 "entries": {entry["candidate_key"]: entry for entry in entries},
                 "cursor": {"round_seq": 1, "last_round_at": NOW.isoformat()}}
        ad.atomic_json(self.data / ad.QUEUE_FILE, value)
        return value

    def entry(self, state="shown", first_seen_at=None):
        first_seen_at = first_seen_at or datetime.now(timezone.utc)
        return {
            "candidate_key": "k1", "project_id": "demo-video", "repo_id": 7,
            "repo": "sample/subtitle", "capability_key": "subtitle",
            "capability_label": "subtitle", "scope": "direction", "state": state,
            "first_seen_at": first_seen_at.isoformat(),
            "last_shown_at": first_seen_at.isoformat(), "shown_count": 1,
            "last_target_revision": "t1", "last_repo_revision": "r1",
            "last_evidence_revision": "e1",
        }

    def write_valid_run(self, candidates=0, generated_at=None):
        generated_at = generated_at or datetime.now(timezone.utc)
        payload = {"schema_version": "1.0", "generated_at": generated_at.isoformat(),
                   "status": "ok", "items": [{"x": i} for i in range(candidates)]}
        path = self.runs / (generated_at.strftime("%Y%m%dT%H%M%S.%fZ") + ".json")
        ad.atomic_json(path, payload)
        return path

    # ---------- F1-1：损坏运行包不得静默成功 ----------

    def test_f1_corrupt_run_package_is_not_silent(self):
        self.write_broken_run(age_hours=72)
        run = subprocess.run([sys.executable, "-B", str(SCRIPTS / "auto_discover.py"),
                              "receipt", "--data-dir", str(self.data)],
                             capture_output=True, text=True)
        payload = json.loads(run.stdout)
        # 长时间停机 + 运行包损坏不得记成静默成功
        self.assertNotEqual(payload["outcome"], "silent")
        self.assertEqual(payload["outcome"], "failed")
        self.assertEqual(run.returncode, 1)
        # 必须有显式警告，不能是零警告
        self.assertTrue(payload["warnings"])
        self.assertTrue(any("运行包不可读" in w for w in payload["warnings"]))
        self.assertTrue(payload["errors"])

    def test_f1_corrupt_run_package_freshness_is_still_checked(self):
        # 新鲜度判定必须在可读性检查之前生效：mtime 可读，损坏也要判过期
        self.write_broken_run(age_hours=72)
        payload, code = ad.build_receipt(self.data, now=datetime.now(timezone.utc))
        receipt = payload["receipt"]
        self.assertEqual(code, 1)
        self.assertTrue(receipt["facts"]["stale_run"])
        self.assertIsNotNone(receipt["facts"]["run_age_hours"])
        self.assertGreater(receipt["facts"]["run_age_hours"], 24)

    def test_f1_corrupt_run_package_fresh_is_still_failed(self):
        # 运行包本身新鲜（mtime 在阈值内）但内容损坏 → 仍不得 silent
        self.write_broken_run(age_hours=1)
        payload, code = ad.build_receipt(self.data, now=datetime.now(timezone.utc))
        receipt = payload["receipt"]
        self.assertEqual(code, 1)
        self.assertEqual(receipt["outcome"], "failed")
        self.assertFalse(receipt["facts"]["stale_run"])
        self.assertTrue(receipt["facts"]["run_invalid"])
        self.assertTrue(receipt["warnings"])

    def test_f1_malformed_but_parseable_run_package_is_not_silent(self):
        # 格式异常但可解析（顶层不是 dict）→ 同上
        self.write_broken_run(content="[1, 2, 3]", age_hours=72)
        payload, code = ad.build_receipt(self.data, now=datetime.now(timezone.utc))
        receipt = payload["receipt"]
        self.assertEqual(code, 1)
        self.assertEqual(receipt["outcome"], "failed")
        self.assertTrue(receipt["facts"]["run_invalid"])
        self.assertTrue(any("格式异常" in w for w in receipt["warnings"]))
        self.assertTrue(receipt["errors"])

    def test_f1_corrupt_run_package_with_new_pending_entry_is_not_silent(self):
        # 损坏运行包 + 队列有本轮新增未研判条目 → 不得静默成功
        self.write_broken_run(age_hours=1)
        self.write_queue([self.entry(first_seen_at=datetime.now(timezone.utc))])
        payload, code = ad.build_receipt(self.data, now=datetime.now(timezone.utc))
        receipt = payload["receipt"]
        self.assertEqual(code, 1)
        self.assertNotEqual(receipt["outcome"], "silent")
        self.assertEqual(receipt["outcome"], "failed")
        self.assertTrue(receipt["errors"])

    def test_f1_corrupt_run_package_keeps_new_unjudged_counted(self):
        # 不可读运行包的"本轮边界"回退到文件 mtime：本轮新增未研判条目仍被计入，
        # 不能因为 run_at=None 就被排除在统计之外。
        self.write_broken_run(age_hours=1)
        self.write_queue([self.entry(first_seen_at=datetime.now(timezone.utc))])
        payload, code = ad.build_receipt(self.data, now=datetime.now(timezone.utc))
        receipt = payload["receipt"]
        self.assertTrue(receipt["facts"]["run_boundary_known"])
        self.assertEqual(receipt["facts"]["run_boundary_source"], "file_mtime")
        self.assertEqual(receipt["facts"]["new_unjudged"], 1)
        self.assertEqual(receipt["facts"]["new_pending"], 1)

    def test_f1_corrupt_run_package_boundary_failure_is_disclosed(self):
        # 边界确实不可判定（mtime 不可读）时显式披露，不假装边界有效
        self.write_broken_run(age_hours=1)
        with mock.patch.object(ad.daily_loop, "run_age_hours", return_value=None), \
                mock.patch.object(ad, "_file_mtime_iso", return_value=None):
            payload, code = ad.build_receipt(self.data, now=datetime.now(timezone.utc))
        receipt = payload["receipt"]
        self.assertEqual(code, 1)
        self.assertEqual(receipt["outcome"], "failed")
        self.assertFalse(receipt["facts"]["run_boundary_known"])
        self.assertTrue(any("边界不可判定" in w for w in receipt["warnings"]))

    def test_f1_explicit_silent_with_corrupt_run_package_is_rejected(self):
        # 显式 silent 也必须被事实校验拒绝
        self.write_broken_run(age_hours=1)
        run = subprocess.run([sys.executable, "-B", str(SCRIPTS / "auto_discover.py"),
                              "receipt", "--data-dir", str(self.data),
                              "--outcome", "silent"],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        payload = json.loads(run.stdout)
        self.assertFalse(payload["ok"])
        self.assertIn("silent", payload["error"])

    def test_f1_corrupt_run_package_candidates_counted_as_zero(self):
        self.write_broken_run(age_hours=1)
        payload, code = ad.build_receipt(self.data, now=datetime.now(timezone.utc))
        receipt = payload["receipt"]
        self.assertEqual(receipt["facts"]["candidates"], 0)
        self.assertEqual(receipt["cards_written"], 0)

    # ---------- 已验证通过的行为不得被矫枉过正 ----------

    def test_f1_valid_fresh_run_package_still_allows_silent(self):
        self.write_valid_run(candidates=0)
        payload, code = ad.build_receipt(self.data, now=datetime.now(timezone.utc))
        receipt = payload["receipt"]
        self.assertEqual(code, 0)
        self.assertEqual(receipt["outcome"], "silent")
        self.assertFalse(receipt["facts"]["stale_run"])
        self.assertFalse(receipt["facts"]["run_invalid"])
        self.assertTrue(receipt["facts"]["run_boundary_known"])
        self.assertEqual(receipt["facts"]["run_boundary_source"], "generated_at")

    def test_f1_valid_stale_run_package_still_fails(self):
        old = datetime.now(timezone.utc) - timedelta(hours=30)
        self.write_valid_run(candidates=0, generated_at=old)
        payload, code = ad.build_receipt(self.data, now=datetime.now(timezone.utc))
        receipt = payload["receipt"]
        self.assertEqual(code, 1)
        self.assertEqual(receipt["outcome"], "failed")
        self.assertTrue(receipt["facts"]["stale_run"])

    def test_f1_missing_run_package_still_fails(self):
        payload, code = ad.build_receipt(self.data, now=datetime.now(timezone.utc))
        receipt = payload["receipt"]
        self.assertEqual(code, 1)
        self.assertEqual(receipt["outcome"], "failed")
        self.assertFalse(receipt["facts"]["run_found"])
        self.assertTrue(any("运行包" in w for w in receipt["warnings"]))

    def test_f1_max_run_age_hours_override_still_works(self):
        # 阈值可覆盖：把阈值调大后旧的（可读）运行包重新有效
        old = datetime.now(timezone.utc) - timedelta(hours=30)
        self.write_valid_run(candidates=0, generated_at=old)
        payload, code = ad.build_receipt(self.data, max_run_age_hours=48,
                                         now=datetime.now(timezone.utc))
        receipt = payload["receipt"]
        self.assertEqual(code, 0)
        self.assertEqual(receipt["outcome"], "silent")
        self.assertFalse(receipt["facts"]["stale_run"])


class ReceiptPreparationContractTests(unittest.TestCase):
    """Malformed preparation is not positive evidence of zero candidates."""

    def check_run(self, value, outcome=None):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            run = data / "auto-opportunities/runs/preparation.json"
            run.parent.mkdir(parents=True)
            run.write_text(json.dumps(value), encoding="utf-8")
            return ad.build_receipt(data, outcome=outcome)

    def test_missing_or_non_list_items_cannot_be_silent(self):
        for value in ({}, {"items": None}, {"items": {}}, {"items": ""}):
            with self.subTest(value=value):
                result, code = self.check_run(value)
                self.assertEqual(code, 1)
                self.assertEqual(result["receipt"]["outcome"], "failed")
                self.assertTrue(result["receipt"]["facts"]["run_invalid"])

    def test_non_object_candidate_cannot_be_zero_or_valid_evidence(self):
        result, code = self.check_run({"items": [None]})
        self.assertEqual(code, 1)
        self.assertTrue(result["receipt"]["facts"]["run_invalid"])

    def test_malformed_coverage_is_controlled_failure(self):
        for coverage in ([], ["bad"], "bad", {"watch_coverage": []},
                         {"watch_coverage": ["bad"]}):
            with self.subTest(coverage=coverage):
                result, code = self.check_run({"items": [], "coverage": coverage})
                self.assertEqual(code, 1)
                self.assertEqual(result["receipt"]["outcome"], "failed")

    def test_explicit_silent_rejects_invalid_run(self):
        result, code = self.check_run({}, outcome="silent")
        self.assertEqual(code, 1)
        self.assertFalse(result["ok"])

    def test_preparation_errors_survive_receipt(self):
        result, code = self.check_run({"items": [], "status": "partial",
                                       "errors": ["synthetic preparation failed"]})
        self.assertEqual(code, 1)
        self.assertEqual(result["receipt"]["outcome"], "failed")
        self.assertTrue(any("synthetic preparation failed" in error
                            for error in result["receipt"]["errors"]))

    def test_invalid_status_and_error_container_fail_closed(self):
        for fields in ({"status": "error"}, {"status": []},
                       {"errors": "failed"}, {"errors": [None]}):
            with self.subTest(fields=fields):
                result, code = self.check_run({"items": [], **fields})
                self.assertEqual(code, 1)
                self.assertTrue(result["receipt"]["facts"]["run_invalid"])

    def test_legacy_minimal_items_list_keeps_mtime_fallback(self):
        result, code = self.check_run({"items": []})
        self.assertEqual(code, 0)
        self.assertEqual(result["receipt"]["outcome"], "silent")
        self.assertEqual(result["receipt"]["facts"]["run_boundary_source"], "file_mtime")

    def test_unparseable_timestamp_keeps_documented_mtime_fallback(self):
        for timestamp in ("not-a-date", ["bad"], {"bad": True}):
            with self.subTest(timestamp=timestamp):
                result, code = self.check_run({"items": [], "generated_at": timestamp})
                self.assertEqual(code, 0)
                self.assertEqual(result["receipt"]["facts"]["run_boundary_source"], "file_mtime")

    def test_cli_persists_failed_receipt_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / "auto-opportunities/runs/preparation.json"
            run.parent.mkdir(parents=True)
            run.write_text(json.dumps({"items": [], "coverage": ["bad"]}))
            completed = subprocess.run(
                [sys.executable, str(SCRIPTS / "auto_discover.py"), "receipt",
                 "--data-dir", directory, "--outcome", "auto"],
                capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 1)
            self.assertNotIn("Traceback", completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual(result["outcome"], "failed")
            stored = json.loads(Path(result["receipt_path"]).read_text())
            self.assertEqual(stored["outcome"], "failed")

    def test_partial_with_warning_only_keeps_valid_empty_result(self):
        result, code = self.check_run({"items": [], "status": "partial",
                                      "warnings": ["bounded coverage"], "errors": []})
        self.assertEqual(code, 0)
        self.assertEqual(result["receipt"]["outcome"], "silent")


if __name__ == "__main__":
    unittest.main(verbosity=2)
