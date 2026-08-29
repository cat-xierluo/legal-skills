#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""额度感知路由建议器（quota-aware routing suggester）。

机制（零具体模型名，全部来自个人配置；设计文档见仓库 docs/plans/）：
  输入 --tier/--scene/--task-card-path，读个人配置 quota_aware_routing 段
  + 一个中立 schema 的余量 JSON 文件，输出推荐 provider + urgency + 证据。

契约 schema（quota-aware-routing.summary.v1，产出方不限，公开侧不感知）：
  {"schema": "quota-aware-routing.summary.v1",
   "generated_at": "<ISO8601>",
   "lanes": {"<lane>": {"type": "fuel|reservoir",
                        "remaining_percent": <float>?,   # fuel 型余量百分比
                        "resets_at": "<ISO8601>"?,       # fuel 型窗口重置时刻
                        "health": "ok|down"}}}           # reservoir 型健康信号

降级链（fail-closed，不静默换 lane）：
  未配置段 → not_configured → 调用方走任务卡显式 provider / 静态 task_routing
  summary 读不到 → degraded → 同上
  数据过期 → 仍推荐但标 stale
  resets_at 已过 → 该 lane 标 pending_refresh，评分降为静态序
  燃料 lane 全判停 → all_lanes_stopped → 落 tier_policy.default 保底
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from typing import Any

SCHEMA_ID = "quota-aware-routing.summary.v1"

DEFAULTS = {
    "enabled": False,
    "freshness_minutes": 30,
    "stop_line_percent": 15,
    "urgency_window_minutes": 120,
}


def _now_tz(now: dt.datetime | None) -> dt.datetime:
    current = now or dt.datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.astimezone()
    return current


def _parse_iso(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        stamp = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.astimezone()
    return stamp


def _merged(cfg: dict[str, Any]) -> dict[str, Any]:
    """quota_aware_routing 段 + 默认值合并。返回空 dict 表示未启用。"""
    section = cfg.get("quota_aware_routing")
    if not isinstance(section, dict) or not section.get("enabled"):
        return {}
    merged = {**DEFAULTS, **section}
    if not isinstance(merged.get("lanes"), dict) or not isinstance(merged.get("tier_policy"), dict):
        return {}
    return merged


def build_route_decision(
    config: dict[str, Any] | None,
    summary: dict[str, Any] | None,
    tier: str,
    scene: str | None = None,
    card_provider: str | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """纯决策函数（可测）。不发 IO、不访问网络。"""
    qar = _merged(config or {})
    if not qar:
        return {"status": "not_configured",
                "reason": "quota_aware_routing 未配置或未启用"}

    if card_provider and str(card_provider).strip():
        return {"status": "locked_by_card",
                "provider": str(card_provider).strip(),
                "reason": "任务卡显式指定 provider，尊重人工锁定"}

    if not isinstance(summary, dict) or not summary.get("lanes"):
        return {"status": "degraded",
                "reason": "summary 缺失或无可读 lanes，走任务卡显式 provider 或静态 task_routing"}

    current = _now_tz(now)
    generated = _parse_iso(summary.get("generated_at"))
    stale = generated is None or (current - generated).total_seconds() > qar["freshness_minutes"] * 60

    return _score_and_pick(qar, summary, tier, scene, current, stale)


def _score_and_pick(qar, summary, tier, scene, current, stale):
    raise NotImplementedError("Task 2/3 实现")


def main(argv: list[str] | None = None) -> int:
    raise NotImplementedError("Task 4 实现")


if __name__ == "__main__":
    sys.exit(main())
