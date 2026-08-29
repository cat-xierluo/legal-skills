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


if __name__ == "__main__":
    unittest.main()
