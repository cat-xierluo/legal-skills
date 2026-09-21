#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sub2api 积分 lane 额度 summary 适配器（quota-aware-routing.summary.v1 合并写入方）。

multi-agent-orchestration 的额度预检门（quota_preflight.py）与路由
（route_suggest.py）只消费中立合同文件；谁生产 summary 合同不限定。本脚本
把本机 sub2api 网关的 /ui/api/quota 聚合端点（T35）转成 summary 里的
qwenworkai / lobsterai / autoclaw / codebuddy lane，作为该合同的生产方之一。

网关通道数据源（网关侧已聚合，本脚本只做转发与合并）：
  - qwenworkai：qw 双 app 池（qodercn 专属包 + 千问办公每日 100 当日过期）。
    网关 available_apps() 已内置「最快过期优先」排序（T20/T21）——CLI worker
    派发即吃临期积分，无需 lane 层再排序。
  - lobsterai：积分含 credit_items 逐条 expires_at（每日登录奖励 100 条目
    级临期是高价值信号）。
  - autoclaw：JWT 过期 + 请求统计（积分余量端点未实装，App 内展示为准）。
  - codebuddy：账户池健康（积分余额在聊天响应 credit 字段里顺带观测）。

数据源：--gateway-url 指定网关（默认 http://127.0.0.1:8787）。网关不可达 /
端点异常 → exit 1 不写文件（既有 summary 逐渐过期，消费方按 stale_summary
fail-closed——适配器绝不编造数据放行）。

合并语义（对齐 quota_summary_zcode.py 2026-09-05 决策）：
  - 目标文件已存在且含其他 lane → 只替换本脚本覆盖的 4 条 lane，其余 lane
    原样保留，generated_at 也保留原值：合并方不得替别的生产方"续期"。
  - 文件不存在 / 无其他 lane → generated_at = 本次数据时刻。
  - 写入原子（同目录 tmp + os.replace），并发写不产生半截 JSON。

lane 记录（updated_at/source 为溯源附加键，v1 消费方忽略未知键）：
  {"type": "fuel"|"reservoir",
   "remaining": <金额原样透传>|"remaining_percent": <有 total 时归一>,
   "resets_at" / "expires_at" / "credit_items"（lobster 条目级临期）,
   "health": "ok"|"unavailable"|"error",
   "updated_at": "<本 lane 数据时刻>",
   "source": "sub2api-gateway"}

退出码：0 已写入（stdout 打印合并后的 summary JSON）；
        1 网关不可达 / 数据不可用；
        2 用法或输出路径不可写错误。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.request
from typing import Any

COVERED_LANES = ("qwenworkai", "lobsterai", "autoclaw", "codebuddy")
DEFAULT_GATEWAY = "http://127.0.0.1:8787"


def _now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _fetch_gateway_quota(base_url: str, timeout: float = 10.0) -> dict:
    """拉网关 /ui/api/quota 聚合端点。非 200 / JSON 畸形 / schema 不符 → RuntimeError。"""
    url = base_url.rstrip("/") + "/ui/api/quota"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {url}")
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, dict) or data.get("schema") != "quota-aware-routing.summary.v1":
        raise RuntimeError(f"unexpected schema in {url}: {str(data)[:120]}")
    lanes = data.get("lanes")
    if not isinstance(lanes, dict) or not lanes:
        raise RuntimeError(f"no lanes in {url}")
    return lanes


def _lane_source_entry(lane: dict, now_iso: str) -> dict:
    """网关 lane → summary lane（透传关键字段 + 溯源键）。

    remaining_percent：仅当 total>0 且 remaining 数值有效时归一，钳 [0,100]；
    否则不产出该键（消费方 route_suggest 按 missing 处理，不编造）。
    """
    entry: dict[str, Any] = {"type": lane.get("type", "fuel")}
    remaining = lane.get("remaining")
    total = lane.get("total")
    if isinstance(remaining, (int, float)) and isinstance(total, (int, float)) and total > 0:
        entry["remaining_percent"] = max(0.0, min(100.0, remaining / total * 100.0))
        entry["remaining"] = remaining
        entry["total"] = total
    elif isinstance(remaining, (int, float)):
        entry["remaining"] = remaining
    # qw 聚合 lane 没有 amount 字段，只透传 remaining_total 与 apps 明细
    if lane.get("remaining_total") is not None:
        entry["remaining_total"] = lane["remaining_total"]
    if isinstance(lane.get("apps"), dict):
        entry["apps"] = lane["apps"]
    for k in ("resets_at", "expires_at", "credit_items", "health", "note",
              "jwt_expires_at", "jwt_seconds_left", "account_count", "label"):
        if lane.get(k) is not None:
            entry[k] = lane[k]
    if not lane.get("health"):
        entry["health"] = "ok" if entry.get("remaining_percent", 0) not in (0, None) else "unknown"
    entry["updated_at"] = now_iso
    entry["source"] = "sub2api-gateway"
    return entry


def merge_summary(summary_path: str, new_lanes: dict[str, dict], now_iso: str) -> dict:
    """合并写入：只替换 COVERED_LANES，其余 lane 与 generated_at 原样保留。"""
    existing: dict = {}
    if os.path.exists(summary_path):
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = {}  # 损坏文件视同不存在重写（消费方本来也读不出它）
    lanes: dict = dict(existing.get("lanes") or {})
    for name in COVERED_LANES:
        if name in new_lanes:
            lanes[name] = new_lanes[name]
        else:
            lanes.pop(name, None)  # 网关该通道缺席 → 不保留旧值（避免虚报新鲜）
    out = dict(existing)
    out["schema"] = "quota-aware-routing.summary.v1"
    if not existing.get("lanes"):
        out["generated_at"] = now_iso  # 首次生产：以本次数据为准
    # 已有其他生产方 lane 时保留原 generated_at（不替它们续期）
    out["lanes"] = lanes
    tmp = summary_path + ".tmp"
    os.makedirs(os.path.dirname(summary_path) or ".", exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    os.replace(tmp, summary_path)
    return out


def main_with_args(argv: list[str] | None = None) -> int:
    """可注入 argv 的入口（测试用；生产走 main()）。"""
    ap = argparse.ArgumentParser(description="sub2api 积分 lane 额度 summary 生产方")
    ap.add_argument("--gateway-url", default=DEFAULT_GATEWAY,
                    help=f"sub2api 网关基址（默认 {DEFAULT_GATEWAY}）")
    ap.add_argument("--out", required=True,
                    help="route-summary.json 输出路径（quota-aware-routing.summary.v1）")
    args = ap.parse_args(argv)

    now_iso = _now_iso()
    try:
        gw_lanes = _fetch_gateway_quota(args.gateway_url)
    except Exception as e:
        print(f"sub2api 网关不可达或数据不可用: {e}", file=sys.stderr)
        return 1

    new_lanes = {name: _lane_source_entry(gw_lanes[name], now_iso)
                 for name in COVERED_LANES if name in gw_lanes}
    if not new_lanes:
        print("网关返回无可用 lane", file=sys.stderr)
        return 1

    summary = merge_summary(args.out, new_lanes, now_iso)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


def main() -> int:
    return main_with_args()


if __name__ == "__main__":
    sys.exit(main())
