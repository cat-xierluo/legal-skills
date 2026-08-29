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
import os
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


def lane_signals(summary: dict[str, Any], lanes_cfg: dict[str, Any],
                 now: dt.datetime, stop_line: float = DEFAULTS["stop_line_percent"],
                 urgency_window_minutes: int = DEFAULTS["urgency_window_minutes"]
                 ) -> dict[str, dict[str, Any]]:
    """逐 lane 计算路由信号。lanes_cfg 是个人配置的 lanes 段；summary lanes
    缺席的 lane 视为 unknown（reservoir→不可用；fuel→不可用，fail-closed）。"""
    summary_lanes = summary.get("lanes", {})
    out: dict[str, dict[str, Any]] = {}
    for name, cfg in lanes_cfg.items():
        rec = summary_lanes.get(name, {})
        lane_type = cfg.get("type", "fuel")
        if lane_type == "reservoir":
            out[name] = {"type": "reservoir",
                         "available": rec.get("health") == "ok",
                         "urgency": "none", "pending_refresh": False,
                         "remaining_percent": None, "resets_in_minutes": None}
            continue
        pct = rec.get("remaining_percent")
        pct_ok = isinstance(pct, (int, float))
        available = rec.get("health", "ok") != "down" and pct_ok and float(pct) > stop_line
        resets = _parse_iso(rec.get("resets_at"))
        countdown_min = None
        urgency = "none"
        pending_refresh = False
        if resets is not None:
            countdown_min = (resets - now).total_seconds() / 60
            if countdown_min < 0:
                pending_refresh = True
            elif countdown_min < urgency_window_minutes and pct_ok and float(pct) > stop_line:
                urgency = "high"
        out[name] = {"type": "fuel", "available": available, "urgency": urgency,
                     "pending_refresh": pending_refresh,
                     "remaining_percent": (float(pct) if pct_ok else None),
                     "resets_in_minutes": countdown_min}
    return out


def _score_and_pick(qar, summary, tier, scene, current, stale):
    signals = lane_signals(summary, qar["lanes"], current,
                           stop_line=qar["stop_line_percent"],
                           urgency_window_minutes=qar["urgency_window_minutes"])

    policy = qar["tier_policy"]
    default_lane = policy.get("default") if isinstance(policy.get("default"), str) else None
    if tier in policy and isinstance(policy[tier], list):
        candidates = [lane for lane in policy[tier] if lane in qar["lanes"]]
    else:
        candidates = [default_lane] if default_lane in qar["lanes"] else []

    scene_match = bool(scene) and scene in (qar.get("reservoir_scenes") or [])
    open_tiers = {lane: (cfg.get("open_tiers") or []) for lane, cfg in qar["lanes"].items()}
    scored: list[tuple[float, int, str]] = []
    for order, lane in enumerate(candidates):
        sig = signals.get(lane)
        if not sig or not sig["available"]:
            continue
        if sig["type"] == "reservoir":
            # 入链两条件：scene 匹配（场景驱动的条件兜底），或 tier 被 lane 的
            # open_tiers 显式开放（能力首选：该 tier 的活本就该这条免费 lane 干，
            # 如 multimodal 链首选积分制视觉模型）。两者语义同为"能薅就薅"。
            if not scene_match and tier not in open_tiers.get(lane, []):
                continue
            score = 1000.0  # 免费额度优先于一切燃料（省已付/主窗口额度）
        elif sig["pending_refresh"]:
            score = -1.0   # 数据属上个窗口，评分不可信 → 排最后，靠静态序兜底
        else:
            score = sig["remaining_percent"] or 0.0
            if sig["urgency"] == "high" and sig["resets_in_minutes"] is not None:
                score += 50.0 * (1.0 - sig["resets_in_minutes"] / qar["urgency_window_minutes"])
        scored.append((score, order, lane))

    evidence = {name: {k: v for k, v in sig.items() if v is not None}
                for name, sig in signals.items()}

    if not scored:
        fallback = default_lane or (candidates[0] if candidates else None)
        return {"status": "all_lanes_stopped",
                "fallback_lane": fallback,
                "reason": "候选 lane 全部不可用，建议回落 default 或任务卡显式 provider",
                "evidence": evidence}

    score, order, lane = max(scored, key=lambda item: (item[0], -item[1]))
    sig = signals[lane]
    providers = qar["lanes"][lane].get("providers") or []
    return {"status": "ok", "tier": tier, "lane": lane,
            "provider": providers[0] if providers else "",
            "urgency": sig["urgency"], "stale": stale, "scene": scene,
            "reason": (f"lane={lane} score={score:.1f} type={sig['type']}"
                       + ("（scene 匹配，薅免费额度）" if sig["type"] == "reservoir" else
                          "（余量/临期加权胜出）")),
            "evidence": evidence}


def _read_json(path: str) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _card_provider(task_card_path: str) -> str | None:
    card = _read_json(task_card_path)
    if not card:
        return None
    value = card.get("provider")
    return str(value).strip() if isinstance(value, str) and value.strip() else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="额度感知路由建议器（输出 JSON）")
    parser.add_argument("--tier", required=True,
                        help="任务档位：L0/L1/L2/multimodal（或自定义，缺省走 default）")
    parser.add_argument("--scene", default=None, help="场景标签（reservoir lane 仅 scene 匹配时入链）")
    parser.add_argument("--task-card-path", default=None, help="任务卡 JSON 路径（显式 provider 直通）")
    parser.add_argument("--config", default=None, help="个人配置 JSON（默认环境变量或 skill config）")
    args = parser.parse_args(argv)

    config_path = (args.config
                   or os.environ.get("MULTI_AGENT_ORCHESTRATION_PERSONAL_CONFIG")
                   or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "..", "config", "orchestration-personal.json"))
    config = _read_json(config_path) or {}

    qar = _merged(config)
    summary = _read_json(qar.get("summary_path", "")) if qar else None

    card_provider = _card_provider(args.task_card_path) if args.task_card_path else None
    decision = build_route_decision(config, summary, args.tier,
                                    scene=args.scene, card_provider=card_provider)
    json.dump(decision, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    # 退出码：ok/locked_by_card/not_configured=0；degraded/all_lanes_stopped=1（调用方自行降级）
    return 0 if decision.get("status") in ("ok", "locked_by_card", "not_configured") else 1


if __name__ == "__main__":
    sys.exit(main())
