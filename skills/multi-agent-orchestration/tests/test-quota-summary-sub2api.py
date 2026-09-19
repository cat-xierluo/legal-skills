#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""quota_summary_sub2api.py 的测试：合并语义 + 临期降级。

运行：python3 tests/test-quota-summary-sub2api.py（或 unittest discover）

测试策略：不起真实网关——mock /ui/api/quota 响应（合同格式来自
gateway.py 实测输出），验证生产方脚本的纯逻辑：
  1. 空目标 → 首次写入 + generated_at = 本次
  2. 既有其他 lane → 只替换本脚本 4 条 lane，其余原样保留
  3. 既有本 lane 旧数据 → 替换且 _old 等附加键清除
  4. 网关不可达 → exit 1 不写文件（fail-closed，绝不编造）
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import quota_summary_sub2api as qsa


MOCK_LANES = {
    "qwenworkai": {
        "type": "fuel", "health": "ok", "remaining_total": 7238.0,
        "accounts": [
            {"app": "qodercn", "remaining": 5138.0, "total": 6000.0,
             "expires_at": "2026-09-14T23:59:59+0800", "exceeded": False},
            {"app": "qwenwork", "remaining": 2100.0, "exceeded": False},
        ],
    },
    "lobsterai": {
        "type": "fuel", "health": "ok", "remaining": 6599.84,
        "total": 6599.84, "expires_at": "2026-09-29T15:02:39+0800",
        "credit_items": [
            {"type": "campaign", "label": "限时登录礼",
             "remaining": 4999.84, "expires_at": "2026-09-29T15:02:39+0800"},
            {"type": "daily", "label": "每日登录奖励",
             "remaining": 100.0, "expires_at": "2026-09-15T00:00:00+0800"},
        ],
    },
    "autoclaw": {"type": "reservoir", "health": "ok"},
    "codebuddy": {"type": "reservoir", "health": "ok", "account_count": 1},
}


def _mock_fetch(good=True):
    """替换 qsa._fetch_gateway_quota：good=True 返回 lanes dict，否则抛 OSError。

    注意：_fetch_gateway_quota 的合同是「已解出 lanes dict」（schema 校验在
    函数内部完成），mock 必须对齐这个边界，不能返回整个响应 envelope。
    """
    def fake(gateway_url, timeout=10.0):
        if not good:
            raise OSError("connection refused")
        return MOCK_LANES
    return fake


class TestMerge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mktemp(suffix=".json")

    def tearDown(self):
        p = Path(self.tmp)
        if p.exists():
            p.unlink()

    def test_first_write_into_empty_target(self):
        """空目标 → 写入 4 条 lane，generated_at 用网关数据时刻。"""
        with mock.patch.object(qsa, "_fetch_gateway_quota", _mock_fetch(True)):
            rc = qsa.main_with_args(["--gateway-url", "http://x", "--out", self.tmp])
        self.assertEqual(rc, 0)
        d = json.loads(Path(self.tmp).read_text("utf-8"))
        self.assertEqual(set(d["lanes"]), set(MOCK_LANES))
        # generated_at = 本地生产时刻（_now_iso，ISO 带时区）；不绑定具体值
        import re as _re
        self.assertRegex(d["generated_at"],
                         _re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$"))
        self.assertEqual(d["lanes"]["qwenworkai"]["remaining_total"], 7238.0)
        # 溯源键存在
        self.assertIn("updated_at", d["lanes"]["qwenworkai"])
        self.assertEqual(d["lanes"]["qwenworkai"]["source"], "sub2api-gateway")

    def test_merge_preserves_other_producer_lanes(self):
        """既有 glm-api/minimax/zcode → 原样保留；generated_at 不续期。"""
        Path(self.tmp).write_text(json.dumps({
            "schema": "quota-aware-routing.summary.v1",
            "generated_at": "2026-09-14T12:00:00+08:00",
            "lanes": {
                "glm-api": {"type": "fuel", "remaining_percent": 55.0},
                "zcode": {"type": "fuel", "remaining_percent": 42.0},
            },
        }), encoding="utf-8")
        with mock.patch.object(qsa, "_fetch_gateway_quota", _mock_fetch(True)):
            rc = qsa.main_with_args(["--gateway-url", "http://x", "--out", self.tmp])
        self.assertEqual(rc, 0)
        d = json.loads(Path(self.tmp).read_text("utf-8"))
        self.assertEqual(d["lanes"]["glm-api"]["remaining_percent"], 55.0)
        self.assertEqual(d["lanes"]["zcode"]["remaining_percent"], 42.0)
        # generated_at 保留原值——不替别的生产方续期
        self.assertEqual(d["generated_at"], "2026-09-14T12:00:00+08:00")

    def test_replaces_own_stale_lane(self):
        """本 lane 旧数据（含 _old 附加键）→ 替换且附加键清除。"""
        Path(self.tmp).write_text(json.dumps({
            "schema": "quota-aware-routing.summary.v1",
            "generated_at": "2026-09-14T12:00:00+08:00",
            "lanes": {
                "qwenworkai": {"type": "fuel", "health": "stale", "_old": True},
                "glm-api": {"type": "fuel", "remaining_percent": 55.0},
            },
        }), encoding="utf-8")
        with mock.patch.object(qsa, "_fetch_gateway_quota", _mock_fetch(True)):
            rc = qsa.main_with_args(["--gateway-url", "http://x", "--out", self.tmp])
        self.assertEqual(rc, 0)
        d = json.loads(Path(self.tmp).read_text("utf-8"))
        qw = d["lanes"]["qwenworkai"]
        self.assertNotIn("_old", qw)
        self.assertEqual(qw["remaining_total"], 7238.0)
        self.assertEqual(d["lanes"]["glm-api"]["remaining_percent"], 55.0)

    def test_gateway_down_fails_closed(self):
        """网关不可达 → exit 1 且不写目标文件（fail-closed）。"""
        existed = Path(self.tmp).exists()
        with mock.patch.object(qsa, "_fetch_gateway_quota", _mock_fetch(False)):
            rc = qsa.main_with_args(["--gateway-url", "http://x", "--out", self.tmp])
        self.assertEqual(rc, 1)
        self.assertEqual(Path(self.tmp).exists(), existed)


if __name__ == "__main__":
    unittest.main()
