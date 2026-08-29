#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""route_suggest 决策逻辑单测。运行：python3 -m unittest discover -s scripts/tests -p 'test_route_suggest.py' -v"""
import datetime as dt
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import route_suggest as rs  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures")


def load_fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


def freshify(summary, now, resets_in_minutes=240):
    """把 fixture 占位时间替换成相对 now 的真实时间。"""
    summary["generated_at"] = now.isoformat()
    for rec in summary.get("lanes", {}).values():
        if rec.get("resets_at"):
            rec["resets_at"] = (now + dt.timedelta(minutes=resets_in_minutes)).isoformat()
    return summary


BASE_CONFIG = {
    "quota_aware_routing": {
        "enabled": True,
        "summary_path": "/nonexistent/ignored-in-unit-tests.json",
        "freshness_minutes": 30,
        "stop_line_percent": 15,
        "urgency_window_minutes": 120,
        "lanes": {
            "lane-a": {"type": "fuel", "providers": ["prov-a1"]},
            "lane-b": {"type": "fuel", "providers": ["prov-b1"]},
            "lane-r": {"type": "reservoir", "providers": ["prov-r1"], "concurrency_cap": 1},
        },
        "tier_policy": {
            "L2": ["lane-a"],
            "L1": ["lane-b", "lane-a", "lane-r"],
            "L0": ["lane-b", "lane-a", "lane-r"],
            "multimodal": ["lane-r", "lane-a"],
            "default": "lane-a",
        },
        "reservoir_scenes": ["overnight_batch"],
    }
}

NOW = dt.datetime(2026, 8, 29, 12, 0, 0, tzinfo=dt.timezone(dt.timedelta(hours=8)))


class TestBasePaths(unittest.TestCase):
    def test_not_configured_when_section_missing(self):
        out = rs.build_route_decision({"main_force": {}}, None, "L0", now=NOW)
        self.assertEqual(out["status"], "not_configured")

    def test_not_configured_when_disabled(self):
        cfg = {"quota_aware_routing": {**BASE_CONFIG["quota_aware_routing"], "enabled": False}}
        out = rs.build_route_decision(cfg, None, "L0", now=NOW)
        self.assertEqual(out["status"], "not_configured")

    def test_degraded_when_summary_none(self):
        out = rs.build_route_decision(BASE_CONFIG, None, "L0", now=NOW)
        self.assertEqual(out["status"], "degraded")

    def test_locked_by_card_wins(self):
        summary = freshify(load_fixture("quota-summary-normal.json"), NOW)
        out = rs.build_route_decision(BASE_CONFIG, summary, "L0",
                                      card_provider="prov-manual", now=NOW)
        self.assertEqual(out["status"], "locked_by_card")
        self.assertEqual(out["provider"], "prov-manual")


class TestLaneSignals(unittest.TestCase):
    def test_lane_signals_basic(self):
        summary = freshify(load_fixture("quota-summary-normal.json"), NOW)
        lanes_cfg = BASE_CONFIG["quota_aware_routing"]["lanes"]
        signals = rs.lane_signals(summary, lanes_cfg, NOW)
        # lane-a: fuel 80% 余量、4h 后重置 → available，无 urgency，无 pending_refresh
        self.assertTrue(signals["lane-a"]["available"])
        self.assertNotEqual(signals["lane-a"]["urgency"], "high")
        self.assertFalse(signals["lane-a"]["pending_refresh"])
        # lane-b: fuel 10% < 判停线 15% → 不可用
        self.assertFalse(signals["lane-b"]["available"])
        # lane-r: reservoir health ok → available
        self.assertTrue(signals["lane-r"]["available"])

    def test_urgency_when_reset_imminent_and_quota_left(self):
        summary = freshify(load_fixture("quota-summary-normal.json"), NOW, resets_in_minutes=74)
        lanes_cfg = BASE_CONFIG["quota_aware_routing"]["lanes"]
        signals = rs.lane_signals(summary, lanes_cfg, NOW)
        self.assertEqual(signals["lane-a"]["urgency"], "high")   # 74min < 120min 窗口
        self.assertEqual(signals["lane-b"]["urgency"], "none")   # 余量低于判停线，不冲

    def test_pending_refresh_when_reset_already_passed(self):
        summary = freshify(load_fixture("quota-summary-normal.json"), NOW, resets_in_minutes=-5)
        lanes_cfg = BASE_CONFIG["quota_aware_routing"]["lanes"]
        signals = rs.lane_signals(summary, lanes_cfg, NOW)
        self.assertTrue(signals["lane-a"]["pending_refresh"])    # resets_at 已过 → 数据是上个窗口的
        self.assertTrue(signals["lane-a"]["available"])          # 保守视为可用（可能已满血）


class TestScoring(unittest.TestCase):
    def normal(self, **kw):
        summary = freshify(load_fixture("quota-summary-normal.json"), NOW,
                           resets_in_minutes=kw.pop("resets_in_minutes", 240))
        return rs.build_route_decision(BASE_CONFIG, summary, kw.pop("tier", "L0"), now=NOW, **kw)

    def test_high_quota_lane_wins_L0(self):
        # 额度经济化核心场景：余量 80% 的 lane-b... 注意 fixture 中 lane-a=80/lane-b=10，
        # tier_policy L0=[lane-b, lane-a, lane-r] 静态序 lane-b 在前，但评分按余量应选 lane-a
        out = self.normal()
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["lane"], "lane-a")
        self.assertEqual(out["provider"], "prov-a1")
        self.assertIn("evidence", out)

    def test_stopped_lane_yields_to_next(self):
        # lane-a 判停（10%）→ L0 让位：修改 fixture 使 lane-a=8%，lane-b=80%
        summary = freshify(load_fixture("quota-summary-normal.json"), NOW)
        summary["lanes"]["lane-a"]["remaining_percent"] = 8.0
        summary["lanes"]["lane-b"]["remaining_percent"] = 80.0
        out = rs.build_route_decision(BASE_CONFIG, summary, "L0", now=NOW)
        self.assertEqual(out["lane"], "lane-b")

    def test_urgency_boost_prefers_imminent_lane(self):
        # lane-a 80%/4h、lane-b 80%/74min → 临期加权让 lane-b 胜出（尽管静态序 lane-b 靠后）
        summary = freshify(load_fixture("quota-summary-normal.json"), NOW)
        summary["lanes"]["lane-b"]["remaining_percent"] = 80.0
        summary["lanes"]["lane-a"]["resets_at"] = (NOW + dt.timedelta(minutes=240)).isoformat()
        summary["lanes"]["lane-b"]["resets_at"] = (NOW + dt.timedelta(minutes=74)).isoformat()
        out = rs.build_route_decision(BASE_CONFIG, summary, "L0", now=NOW)
        self.assertEqual(out["lane"], "lane-b")
        self.assertEqual(out["urgency"], "high")

    def test_reservoir_only_when_scene_matches(self):
        # scene 不匹配 → reservoir lane 不入链（L0 静态序里 lane-r 存在但不选它）
        out = self.normal()  # 无 scene
        self.assertNotEqual(out["lane"], "lane-r")
        # scene 匹配 overnight_batch → reservoir 优先（省燃料）
        out2 = self.normal(scene="overnight_batch")
        self.assertEqual(out2["lane"], "lane-r")
        self.assertEqual(out2["provider"], "prov-r1")

    def test_all_fuel_stopped_falls_to_default(self):
        summary = freshify(load_fixture("quota-summary-normal.json"), NOW)
        summary["lanes"]["lane-a"]["remaining_percent"] = 5.0
        summary["lanes"]["lane-b"]["remaining_percent"] = 5.0
        summary["lanes"]["lane-r"]["health"] = "down"
        out = rs.build_route_decision(BASE_CONFIG, summary, "L0", now=NOW)
        self.assertEqual(out["status"], "all_lanes_stopped")
        self.assertEqual(out["fallback_lane"], "lane-a")  # tier_policy.default


if __name__ == "__main__":
    unittest.main()


class TestReservoirOpenTiers(unittest.TestCase):
    """open_tiers：reservoir lane 对显式开放的 tier 无条件入链（能力首选场景）。"""

    def _config(self):
        import copy
        cfg = copy.deepcopy(BASE_CONFIG)
        cfg["quota_aware_routing"]["lanes"]["lane-r"]["open_tiers"] = ["multimodal"]
        return cfg

    def test_open_tier_reservoir_wins_without_scene(self):
        # multimodal 链中 reservoir 被显式开放 → 无 scene 也应胜过 fuel（能力首选吃积分）
        summary = freshify(load_fixture("quota-summary-normal.json"), NOW)
        out = rs.build_route_decision(self._config(), summary, "multimodal", now=NOW)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["lane"], "lane-r")
        self.assertEqual(out["provider"], "prov-r1")

    def test_non_open_tier_still_scene_gated(self):
        # L0 未开放 → 无 scene 仍不入链（不抢主链流量，定稿语义不变）
        summary = freshify(load_fixture("quota-summary-normal.json"), NOW)
        out = rs.build_route_decision(self._config(), summary, "L0", now=NOW)
        self.assertNotEqual(out["lane"], "lane-r")
