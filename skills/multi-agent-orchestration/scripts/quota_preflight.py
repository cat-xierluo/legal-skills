#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""spawn-worker 配额预检门（quota preflight gate，fail-closed）。

2026-09 复盘修复（P0-①）：旧语义下 route_suggest 只在「自动补选」时看额度，
显式 --api-provider 直接跳过额度检查；summary 缺失/过期/低于判停线时 spawn
仍然放行（fail-open）。本门在 spawn-worker 的任何 worktree/terminal/lease/
dispatch 副作用之前运行，只要个人配置启用 quota_aware_routing：

  - summary 缺失（--summary-file 与配置 summary_path 均为空）→ missing_summary
  - summary 文件不可读 / 非对象 / 缺 generated_at        → unreadable_summary
  - generated_at 不可解析或超过 freshness_minutes        → stale_summary
  - 显式 provider 不属于任何 lane                        → provider_unknown_lane
  - claude-code 未解析出 provider（自动补选失败）         → no_provider_selected
  - lane 在 summary 缺席 / fuel 缺 remaining_percent /
    resets_at 不可解析                                    → lane_no_signal
  - lane health=down                                     → lane_unhealthy
  - fuel remaining_percent <= stop_line_percent（等于也拒）→ lane_below_stop_line

放行通道只有三条：
  - not_configured：quota_aware_routing 未启用（本门无机械权威，放行并提示）
  - not_applicable：非 claude backend 且未显式 provider（无 lane 概念）
  - ok：provider 命中 lane 且该 lane 余量/健康信号全部通过

绕过通道不在本模块：spawn-worker 侧仅接受显式 --quota-preflight-override
标志 + 非空授权来源，并写入 METADATA / authority receipt；默认不存在人工
锁定直通。summary/config schema 与 route_suggest.py 完全一致
（quota-aware-routing.summary.v1）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from typing import Any

EXIT_ALLOW = 0
EXIT_DENY = 3

SCHEMA_HINT = "quota-aware-routing.summary.v1"

DEFAULTS = {
    "freshness_minutes": 30,
    "stop_line_percent": 15,
}


def _parse_iso(value: Any) -> dt.datetime | None:
    """与 route_suggest.py 相同的解析面：naive 时间按本地时区解释。"""
    if not isinstance(value, str) or not value:
        return None
    try:
        stamp = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.astimezone()
    return stamp


def _now_tz(now: dt.datetime | None) -> dt.datetime:
    current = now or dt.datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.astimezone()
    return current


class Gate:
    """纯决策聚合器：emit() 记录结论，run() 依次走检查链。"""

    def __init__(self, provider: str, backend: str) -> None:
        self.provider = provider
        self.backend = backend
        self.lane: str | None = None
        self.status: str | None = None
        self.reason = ""
        self.pending_refresh = False

    def deny(self, status: str, reason: str) -> dict[str, Any]:
        self.status = status
        self.reason = reason
        payload: dict[str, Any] = {
            "allowed": False,
            "status": status,
            "provider": self.provider,
            "backend": self.backend,
            "reason": reason,
        }
        if self.lane:
            payload["lane"] = self.lane
        return payload

    def allow(self, status: str, reason: str) -> dict[str, Any]:
        self.status = status
        self.reason = reason
        payload: dict[str, Any] = {
            "allowed": True,
            "status": status,
            "provider": self.provider,
            "backend": self.backend,
            "reason": reason,
        }
        if self.lane:
            payload["lane"] = self.lane
        if self.pending_refresh:
            payload["pending_refresh"] = True
        return payload


def _merged_quota_section(config: dict[str, Any]) -> dict[str, Any] | None:
    """未启用 → None（not_configured）；启用但 lanes/tier_policy 结构非法 → {}（config_invalid）。"""
    section = config.get("quota_aware_routing")
    if not isinstance(section, dict) or not section.get("enabled"):
        return None
    merged = {**DEFAULTS, **section}
    if not isinstance(merged.get("lanes"), dict) or not isinstance(merged.get("tier_policy"), dict):
        return {}
    if not isinstance(merged["freshness_minutes"], (int, float)) or merged["freshness_minutes"] < 0:
        return {}
    if not isinstance(merged["stop_line_percent"], (int, float)):
        return {}
    return merged


def _lane_for_provider(qar: dict[str, Any], provider: str) -> str | None:
    for name, cfg in qar["lanes"].items():
        if not isinstance(cfg, dict):
            continue
        providers = cfg.get("providers")
        if isinstance(providers, list) and provider in {str(item) for item in providers}:
            return name
    return None


def _check_lane(gate: Gate, qar: dict[str, Any], summary: dict[str, Any],
                lane: str, stop_line: float) -> dict[str, Any]:
    """逐 lane 校验余量/健康信号；失败直接返回 deny payload。"""
    gate.lane = lane
    lane_cfg = qar["lanes"].get(lane)
    if not isinstance(lane_cfg, dict):
        return gate.deny("config_invalid", f"lane {lane} 配置缺失或非法")
    lane_type = lane_cfg.get("type", "fuel")
    rec = summary.get("lanes", {}).get(lane)
    if not isinstance(rec, dict):
        return gate.deny("lane_no_signal",
                         f"lane {lane} 在 quota summary 中缺席，无余量/健康信号（fail-closed）")
    health = rec.get("health")
    if lane_type == "reservoir":
        if health == "down":
            return gate.deny("lane_unhealthy", f"reservoir lane {lane} health=down（fail-closed）")
        if health != "ok":
            return gate.deny("lane_no_signal",
                             f"reservoir lane {lane} 缺 health=ok 信号（fail-closed）")
        return gate.allow("ok", f"reservoir lane {lane} health=ok")
    # fuel lane
    if health == "down":
        return gate.deny("lane_unhealthy", f"fuel lane {lane} health=down（fail-closed）")
    pct = rec.get("remaining_percent")
    if not isinstance(pct, (int, float)) or isinstance(pct, bool):
        return gate.deny("lane_no_signal",
                         f"fuel lane {lane} 缺 remaining_percent，无余量信号（fail-closed）")
    if float(pct) <= stop_line:
        return gate.deny("lane_below_stop_line",
                         f"fuel lane {lane} remaining={float(pct)}% 低于或触及判停线 "
                         f"{stop_line}%（fail-closed）")
    resets_at = rec.get("resets_at")
    if resets_at is not None:
        resets = _parse_iso(resets_at)
        if resets is None:
            return gate.deny("lane_no_signal",
                             f"fuel lane {lane} resets_at 不可解析（快照局部损坏，fail-closed）")
        if resets <= _now_tz(gate.now):
            gate.pending_refresh = True  # 数据属上个窗口：放行但显式标记待刷新
    return gate.allow("ok", f"fuel lane {lane} remaining={float(pct)}% > 判停线 {stop_line}%")


def run_gate(config: dict[str, Any] | None, summary: dict[str, Any] | None,
             provider: str, backend: str, now: dt.datetime | None = None) -> dict[str, Any]:
    gate = Gate(provider, backend)
    gate.now = now

    qar = _merged_quota_section(config or {})
    if qar is None:
        return gate.allow("not_configured",
                          "quota_aware_routing 未配置或未启用：本门无机械权威，放行")
    if not qar:
        return gate.deny("config_invalid",
                         "quota_aware_routing 已启用但 lanes/tier_policy 结构非法（fail-closed）")

    if not provider:
        if backend == "claude-code":
            return gate.deny("no_provider_selected",
                             "claude-code 未解析出 provider（含自动补选失败），无已验证 lane（fail-closed）")
        return gate.allow("not_applicable",
                          f"backend {backend} 未显式 provider，无 lane 概念（advisory 放行）")

    lane = _lane_for_provider(qar, provider)
    if lane is None:
        return gate.deny("provider_unknown_lane",
                         f"provider {provider} 不属于任何已配置 lane，provider/lane 不匹配（fail-closed）")

    if not isinstance(summary, dict):
        return gate.deny("missing_summary",
                         "quota summary 缺失（--summary-file 与配置 summary_path 均为空）（fail-closed）")
    generated = summary.get("generated_at")
    if not isinstance(generated, str) or not generated:
        return gate.deny("unreadable_summary",
                         "quota summary 缺 generated_at，快照不可读（fail-closed）")
    generated_dt = _parse_iso(generated)
    current = _now_tz(now)
    if generated_dt is None:
        return gate.deny("stale_summary", "quota summary generated_at 不可解析，视为过期（fail-closed）")
    if (current - generated_dt).total_seconds() > float(qar["freshness_minutes"]) * 60:
        return gate.deny("stale_summary",
                         f"quota summary 已过期（超过 freshness_minutes={qar['freshness_minutes']}，"
                         "过期快照的余量不可采信，fail-closed）")
    return _check_lane(gate, qar, summary, lane, float(qar["stop_line_percent"]))


def _read_json(path: str) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="spawn-worker 配额预检门（输出 JSON，fail-closed）")
    parser.add_argument("--config", required=True, help="个人配置 JSON 路径")
    parser.add_argument("--provider", default="", help="已解析的 API provider（可为空）")
    parser.add_argument("--backend", default="", help="canonical worker backend")
    parser.add_argument("--summary-file", default=None,
                        help="显式 quota summary 路径；缺省读配置 quota_aware_routing.summary_path")
    parser.add_argument("--now", default=None, help="ISO8601 当前时刻（可测性注入；缺省取系统时间）")
    args = parser.parse_args(argv)

    config = _read_json(args.config)
    if config is None:
        # 配置不可读 = 无机械权威，与 route_suggest 的 not_configured 语义一致。
        config = {}

    qar_section = config.get("quota_aware_routing")
    summary_path = args.summary_file
    if not summary_path and isinstance(qar_section, dict):
        candidate = qar_section.get("summary_path")
        summary_path = candidate if isinstance(candidate, str) and candidate.strip() else None
    summary = _read_json(summary_path) if summary_path else None

    now = _parse_iso(args.now) if args.now else None
    payload = run_gate(config, summary, args.provider.strip(), args.backend.strip(), now=now)
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return EXIT_ALLOW if payload.get("allowed") else EXIT_DENY


if __name__ == "__main__":
    sys.exit(main())
