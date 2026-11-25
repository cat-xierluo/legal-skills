#!/usr/bin/env python3
"""radar.py 的离线回归：用合成采集结果覆盖归一化、信号、短名单与校验。"""

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
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import radar  # noqa: E402


def make_raw(keyword: str, mode: str, cards: list[dict]) -> dict:
    return {
        "schema": radar.RAW_SCHEMA,
        "keyword": keyword,
        "mode": mode,
        "collected_at": "2026-11-25T10:00:00+00:00",
        "page_url": "https://www.douyin.com/search/x",
        "rounds": [{"round": 1, "card_count": len(cards), "unique_so_far": len(cards)}],
        "cards": cards,
        "related_searches": ["律师案源获取途径", "律师如何找案源"],
        "card_count": len(cards),
        "truncated": False,
    }


def make_card(
    aweme_id: str,
    nickname: str,
    digg: int,
    age_days: float,
    hashtags: list[str] | None = None,
) -> dict:
    created = datetime.now(timezone.utc) - timedelta(days=age_days)
    return {
        "aweme_id": aweme_id,
        "url": f"https://www.douyin.com/video/{aweme_id}",
        "desc": f"作品 {aweme_id} 的描述 #话题",
        "author": {"nickname": nickname, "uid": "u-" + nickname, "follower_count": 1000},
        "stats": {
            "digg": digg,
            "comment": max(1, digg // 20),
            "share": max(1, digg // 50),
            "collect": max(1, digg // 3),
            "play": 0,
        },
        "duration_s": 120,
        "create_time": int(created.timestamp()),
        "hashtags": hashtags or ["律师", "案源"],
        "is_ads": False,
        "is_slides": False,
        "source": "aweme_info",
    }


class RadarTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.raw_dir = self.workspace / "raw"
        self.raw_dir.mkdir()
        cards = [
            make_card("7000000000000000001", "甲", 50000, 3),
            make_card("7000000000000000002", "甲", 20000, 10),
            make_card("7000000000000000003", "甲", 100, 200),
            make_card("7000000000000000004", "乙", 8000, 5),
            make_card("7000000000000000005", "丙", 3000, 40),
            make_card("7000000000000000006", "丙", 1000, 120),
        ]
        (self.raw_dir / "a.json").write_text(
            json.dumps(make_raw("律师案源", "comprehensive", cards), ensure_ascii=False),
            encoding="utf-8",
        )
        (self.raw_dir / "b.json").write_text(
            json.dumps(
                make_raw("律师案源", "latest", [make_card("7000000000000000007", "丁", 600, 2)]),
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_command(self, *argv: str) -> dict:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = radar.main(list(argv))
        self.assertEqual(code, 0, buffer.getvalue())
        return json.loads(buffer.getvalue())

    def test_normalize_dedupes_and_keeps_unlinked_out(self) -> None:
        payload = self.run_command(
            "normalize",
            "--raw",
            str(self.raw_dir / "*.json"),
            "--workspace",
            str(self.workspace),
        )
        self.assertEqual(payload["observations"], 7)
        self.assertEqual(payload["unlinked_cards"], 0)
        self.assertIn("律师案源", payload["keywords"])
        self.assertEqual(sorted(payload["modes"]), ["comprehensive", "latest"])

        records = radar.load_jsonl(self.workspace / "observations.jsonl")
        self.assertEqual(len(records), 7)
        self.assertEqual(records[0]["stats"]["digg"], 50000)
        self.assertEqual(records[0]["keywords"], ["律师案源"])
        self.assertGreaterEqual(records[0]["age_days"], 2.9)
        meta = json.loads((self.workspace / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["related_searches"][0], "律师案源获取途径")

    def test_normalize_drops_cards_without_id(self) -> None:
        raw = self.raw_dir / "a.json"
        payload = json.loads(raw.read_text(encoding="utf-8"))
        payload["cards"].append({"desc": "无 ID 卡片", "source": "dom_fallback"})
        raw.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        result = self.run_command(
            "normalize",
            "--raw",
            str(raw),
            "--workspace",
            str(self.workspace),
        )
        self.assertEqual(result["observations"], 6)
        self.assertEqual(result["unlinked_cards"], 1)

    def test_rank_writes_signals_and_report(self) -> None:
        self.run_command(
            "normalize",
            "--raw",
            str(self.raw_dir / "*.json"),
            "--workspace",
            str(self.workspace),
        )
        payload = self.run_command("rank", "--workspace", str(self.workspace))
        signals = json.loads((self.workspace / "signals.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["observations"], signals["observations"])
        self.assertEqual(signals["schema"], radar.SIGNALS_SCHEMA)
        self.assertEqual(signals["recency"]["known"], 7)
        self.assertEqual(signals["recency"]["unknown"], 0)
        self.assertEqual(signals["engagement"]["digg"]["max"], 50000)
        self.assertGreaterEqual(len(signals["hashtags"]), 1)
        report = (self.workspace / "candidates.md").read_text(encoding="utf-8")
        for section in ("口径与局限", "概览", "时间分布", "高频话题标签", "选题线索"):
            self.assertIn(section, report)
        self.assertIn("不是平台官方流量数据", report)

    def test_shortlist_caps_author_and_writes_links(self) -> None:
        self.run_command(
            "normalize",
            "--raw",
            str(self.raw_dir / "*.json"),
            "--workspace",
            str(self.workspace),
        )
        self.run_command("rank", "--workspace", str(self.workspace))
        payload = self.run_command(
            "shortlist", "--workspace", str(self.workspace), "--top", "12"
        )
        picked = json.loads((self.workspace / "shortlist.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["selected"], len(picked))
        self.assertEqual(picked[0]["aweme_id"], "7000000000000000001")
        counts: dict[str, int] = {}
        for item in picked:
            counts[item["author"]] = counts.get(item["author"], 0) + 1
        self.assertLessEqual(max(counts.values()), 2)
        links = (self.workspace / "links.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(links), len(picked))

    def test_verify_passes_on_complete_run(self) -> None:
        self.run_command(
            "normalize",
            "--raw",
            str(self.raw_dir / "*.json"),
            "--workspace",
            str(self.workspace),
        )
        self.run_command("rank", "--workspace", str(self.workspace))
        self.run_command("shortlist", "--workspace", str(self.workspace))
        payload = self.run_command("verify", "--workspace", str(self.workspace))
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["shortlist"], payload["links"])

    def test_verify_fails_when_links_drift(self) -> None:
        self.run_command(
            "normalize",
            "--raw",
            str(self.raw_dir / "*.json"),
            "--workspace",
            str(self.workspace),
        )
        self.run_command("rank", "--workspace", str(self.workspace))
        self.run_command("shortlist", "--workspace", str(self.workspace))
        (self.workspace / "links.txt").write_text(
            "https://www.douyin.com/video/1\n", encoding="utf-8"
        )
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = radar.main(["verify", "--workspace", str(self.workspace)])
        self.assertEqual(code, 1)
        self.assertIn("links.txt", buffer.getvalue())

    def test_verify_fails_without_report(self) -> None:
        code = radar.main(["verify", "--workspace", str(self.workspace)])
        self.assertEqual(code, 1)

    def test_driver_placeholders_are_replaced(self) -> None:
        source = radar.build_driver(
            keyword="律师 案源",
            mode="latest",
            rounds=3,
            out_path=self.workspace / "raw" / "x.json",
            page="p1",
            space_id=44,
            finish=False,
            scroll_step=2800,
        )
        self.assertNotIn("__KEYWORD__", source)
        self.assertNotIn("__COLLECTOR__", source)
        self.assertIn('"律师 案源"', source)
        self.assertIn("const SPACE_ID = 44;", source)
        self.assertIn("const SHOULD_FINISH = 0;", source)

    def test_driver_rejects_unknown_mode(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                radar.main(
                    [
                        "driver",
                        "--keyword",
                        "x",
                        "--mode",
                        "nope",
                        "--workspace",
                        str(self.workspace),
                    ]
                )

    def test_slugify_keeps_chinese(self) -> None:
        self.assertEqual(radar.slugify("律师 案源"), "律师-案源")
        self.assertEqual(radar.slugify("   "), "topic")

    def test_download_plan_does_not_touch_network(self) -> None:
        (self.workspace / "links.txt").write_text(
            "https://www.douyin.com/video/7000000000000000001\n", encoding="utf-8"
        )
        payload = self.run_command("download", "--workspace", str(self.workspace))
        self.assertEqual(payload["mode"], "plan")
        self.assertEqual(payload["count"], 1)

    def prepare_full_run(self) -> None:
        self.run_command(
            "normalize",
            "--raw",
            str(self.raw_dir / "*.json"),
            "--workspace",
            str(self.workspace),
        )
        self.run_command("rank", "--workspace", str(self.workspace))
        self.run_command("shortlist", "--workspace", str(self.workspace))

    def test_verify_rejects_swapped_but_well_formed_link(self) -> None:
        self.prepare_full_run()
        shortlist = json.loads(
            (self.workspace / "shortlist.json").read_text(encoding="utf-8")
        )
        links = [item["url"] for item in shortlist]
        links[0] = "https://www.douyin.com/video/7000000000000000099"
        (self.workspace / "links.txt").write_text("\n".join(links) + "\n", encoding="utf-8")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = radar.main(["verify", "--workspace", str(self.workspace)])
        self.assertEqual(code, 1)
        self.assertIn("与短名单不一致", buffer.getvalue())

    def test_download_rejects_non_douyin_link_before_running_tool(self) -> None:
        (self.workspace / "links.txt").write_text(
            "https://example.org/video\n", encoding="utf-8"
        )
        with patch.object(radar.subprocess, "run") as run:
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                code = radar.main(
                    ["download", "--workspace", str(self.workspace), "--execute"]
                )
        self.assertEqual(code, 1)
        run.assert_not_called()

    def test_download_fails_when_tool_exits_zero_without_media(self) -> None:
        (self.workspace / "links.txt").write_text(
            "https://www.douyin.com/video/7000000000000000001\n", encoding="utf-8"
        )
        completed = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(radar.subprocess, "run", return_value=completed):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = radar.main(
                    ["download", "--workspace", str(self.workspace), "--execute"]
                )
        receipt = json.loads(
            (self.workspace / "download_receipt.json").read_text(encoding="utf-8")
        )
        self.assertEqual(code, 1)
        self.assertEqual(receipt["succeeded"], 0)
        self.assertEqual(receipt["failed"], 1)
        self.assertEqual(receipt["verified"], 0)
        self.assertIsNone(receipt["results"][0]["media_path"])

    def test_download_records_media_path_and_passes_double_dash(self) -> None:
        link = "https://www.douyin.com/video/7000000000000000001"
        (self.workspace / "links.txt").write_text(link + "\n", encoding="utf-8")
        target = self.workspace / "downloads"

        def fake_run(command, **kwargs):
            self.assertEqual(command[-2], "--")
            self.assertEqual(command[-1], link)
            target.mkdir(parents=True, exist_ok=True)
            (target / "7000000000000000001.mp4").write_bytes(b"0" * 1024)
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch.object(radar.subprocess, "run", side_effect=fake_run):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = radar.main(
                    ["download", "--workspace", str(self.workspace), "--execute"]
                )
        receipt = json.loads(
            (self.workspace / "download_receipt.json").read_text(encoding="utf-8")
        )
        self.assertEqual(code, 0)
        self.assertEqual(receipt["verified"], 1)
        self.assertTrue(receipt["results"][0]["ok"])
        self.assertTrue(receipt["results"][0]["media_path"].endswith(".mp4"))
        self.assertEqual(receipt["media_bytes"], 1024)

    def test_recency_is_reported_per_mode(self) -> None:
        self.run_command(
            "normalize",
            "--raw",
            str(self.raw_dir / "*.json"),
            "--workspace",
            str(self.workspace),
        )
        self.run_command("rank", "--workspace", str(self.workspace))
        signals = json.loads((self.workspace / "signals.json").read_text(encoding="utf-8"))
        self.assertEqual(set(signals["recency_by_mode"]), {"comprehensive", "latest"})
        merged = signals["recency"]["buckets"]["30d"]["ratio"]
        baseline = signals["recency_by_mode"]["comprehensive"]["buckets"]["30d"]["ratio"]
        self.assertNotEqual(merged, baseline)
        report = (self.workspace / "candidates.md").read_text(encoding="utf-8")
        self.assertIn("分采集模式的时间分布", report)

    def test_topic_lead_uses_comprehensive_baseline(self) -> None:
        signals = {
            "recency": {"buckets": {"30d": {"ratio": 0.6}}},
            "recency_by_mode": {
                "comprehensive": {"buckets": {"30d": {"ratio": 0.1}}},
                "latest": {"buckets": {"30d": {"ratio": 1.0}}},
            },
            "hashtags": [],
            "engagement": {"digg": {"p50": 0}, "collect": {"p50": 0}, "comment": {"p50": 0}},
            "related_searches": [],
        }
        leads = radar.topic_leads(signals)
        self.assertTrue(any("综合排序样本" in lead and "10%" in lead for lead in leads))
        self.assertFalse(any("60%" in lead for lead in leads))

    def test_shortlist_drops_off_topic_work_and_records_terms(self) -> None:
        observations = [
            make_card("7000000000000000001", "甲", 90000, 2),
            make_card("7000000000000000002", "乙", 800, 3),
        ]
        observations[0]["hashtags"] = []
        observations[0]["desc"] = "刑事案件请律师，选本地的还是外地的好？"
        signals = {"keywords": ["律师案源"]}
        picked = radar.select_shortlist(observations, signals, 12, 2)
        self.assertEqual([item["aweme_id"] for item in picked], ["7000000000000000002"])
        self.assertIn("案源", picked[0]["matched_terms"])

    def test_shortlist_exclude_terms_removes_client_facing_work(self) -> None:
        observations = [
            make_card("7000000000000000001", "甲", 90000, 2),
            make_card("7000000000000000002", "乙", 800, 3),
        ]
        observations[0]["desc"] = "律师案源：当事人请律师前必须知道的三件事"
        signals = {"keywords": ["律师案源"]}
        picked = radar.select_shortlist(
            observations, signals, 12, 2, None, ["请律师"]
        )
        self.assertEqual([item["aweme_id"] for item in picked], ["7000000000000000002"])

    def test_expand_terms_keeps_latin_whole(self) -> None:
        self.assertEqual(radar.expand_terms(["AI"], None), ["ai"])
        self.assertEqual(
            radar.expand_terms(["律师案源"], None),
            ["律师案源", "律师", "师案", "案源"],
        )


if __name__ == "__main__":
    unittest.main()
