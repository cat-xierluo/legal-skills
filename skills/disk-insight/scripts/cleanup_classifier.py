#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把磁盘扫描结果分成「哪里膨胀」和「哪里可以清」两张清单。

只读消费已有的扫描 JSON 与差分 JSON，不做任何额外扫描。分类规则来自
cleanup_policy.json，按顺序命中，第一条匹配生效；未命中的路径归为
unclassified，不推断可清理性。

同时给出两份口径，二者不可混用：
- growth：本轮可比窗口的增量，回答「哪里在膨胀」
- occupancy：当前占用的存量，回答「哪里堆着可清理的东西」
只看增量会漏掉早就堆积、本轮没有变化的可清理内容。
"""

import argparse
import json
import re
from pathlib import Path

GIB = 1024 ** 3
SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_POLICY = SKILL_DIR / "references" / "cleanup_policy.json"


def load_policy(policy_path=DEFAULT_POLICY):
    policy = json.loads(Path(policy_path).read_text())
    compiled = [(re.compile(rule["match"]), rule) for rule in policy["rules"]]
    return policy, compiled


def classify(path, compiled):
    for pattern, rule in compiled:
        if pattern.search(path):
            return rule
    return {"id": "unknown", "class": "unclassified", "reclaimable": False,
            "risk": "unknown", "reason": "未归类路径，需人工判断。", "recovery": "不适用"}


def _deepest_only(paths):
    """同一目标内只保留最深的路径。

    父路径的体积已包含在其子目录里，两者相加会重复计数；保留最深的一层
    才能得到该目标内不重叠的实际占用。
    """
    keep = []
    # 层级越深路径段越多，先处理最深的，好让父路径被子路径覆盖。
    for candidate in sorted(set(paths), key=lambda p: (p.count("/"), len(p)), reverse=True):
        # candidate 若是已保留路径的祖先，其体积已包含在子路径里，丢弃。
        if any(other.startswith(candidate.rstrip("/") + "/") for other in keep):
            continue
        keep.append(candidate)
    return set(keep)


def _iter_comparable_growth(comparisons):
    for diff in comparisons or []:
        if diff.get("status") != "COMPARABLE":
            continue
        for row in diff.get("top_growth") or []:
            if row.get("delta_bytes"):
                yield diff.get("id"), row


def growth_view(report, compiled, min_bytes, max_listed):
    entries = []
    for target_id, row in _iter_comparable_growth(report.get("comparisons")):
        rule = classify(row["path"], compiled)
        entries.append({
            "target": target_id,
            "path": row["path"],
            "delta_bytes": row["delta_bytes"],
            "before_bytes": row.get("before_bytes"),
            "after_bytes": row.get("after_bytes"),
            "class": rule["class"],
            "reclaimable": bool(rule.get("reclaimable")),
            "risk": rule.get("risk"),
            "reason": rule.get("reason"),
            "recovery": rule.get("recovery"),
        })
    entries.sort(key=lambda item: item["delta_bytes"], reverse=True)
    return entries[:max_listed]


def occupancy_view(report, compiled, min_bytes, max_listed):
    """按当前占用统计各类别体积：回答「哪里堆着可清理的东西」。"""
    buckets = {}
    for measurement in report.get("measurements", []):
        snapshot = measurement.get("snapshot")
        if not snapshot or not Path(snapshot).is_file():
            continue
        try:
            data = json.loads(Path(snapshot).read_text())
        except Exception:
            continue
        for result in data.get("results") or []:
            if result.get("status") != "complete":
                continue
            rows = [r for r in (result.get("rows") or []) if r.get("path")]
            if not rows:
                continue
            keep = _deepest_only([r["path"] for r in rows])
            for row in rows:
                if row["path"] not in keep:
                    continue
                size = row.get("allocated_bytes") or 0
                if size < min_bytes:
                    continue
                rule = classify(row["path"], compiled)
                bucket = buckets.setdefault(rule["class"], {
                    "class": rule["class"],
                    "reclaimable": bool(rule.get("reclaimable")),
                    "risk": rule.get("risk"),
                    "reason": rule.get("reason"),
                    "recovery": rule.get("recovery"),
                    "total_bytes": 0,
                    "paths": [],
                })
                bucket["total_bytes"] += size
                bucket["paths"].append({"path": row["path"], "target": measurement.get("id"),
                                        "allocated_bytes": size})
    ordered = sorted(buckets.values(), key=lambda b: b["total_bytes"], reverse=True)
    for bucket in ordered:
        bucket["paths"].sort(key=lambda item: item["allocated_bytes"], reverse=True)
        bucket["paths"] = bucket["paths"][:max_listed]
    return ordered


def analyze(report, policy_path=DEFAULT_POLICY):
    policy, compiled = load_policy(policy_path)
    limits = policy["reporting"]
    min_bytes = limits["min_gib"] * GIB
    max_listed = limits["max_listed"]

    occupancy = occupancy_view(report, compiled, min_bytes, max_listed)
    growth = growth_view(report, compiled, min_bytes, max_listed)
    reclaimable = [b for b in occupancy if b["reclaimable"]]
    keep = [b for b in occupancy if not b["reclaimable"]]
    available = None
    if report.get("capacity_after"):
        available = round(report["capacity_after"]["available_bytes"] / GIB, 3)
    delta = None
    if report.get("capacity_delta_from_previous_bytes") is not None:
        delta = round(report["capacity_delta_from_previous_bytes"] / GIB, 3)
    return {
        "schema": "disk-insight/cleanup-analysis/1",
        "available_gib": available,
        "capacity_delta_gib": delta,
        "growth_ranking": growth,
        "occupancy_ranking": occupancy,
        "reclaimable_occupancy_gib": round(sum(b["total_bytes"] for b in reclaimable) / GIB, 3),
        "keep_occupancy_gib": round(sum(b["total_bytes"] for b in keep) / GIB, 3),
        "notes": [
            "growth 回答「哪里在膨胀」，occupancy 回答「哪里堆着可清理的东西」，两者不可混用。",
            "父路径与子路径不叠加；同一目标内只计最深路径。",
            "APFS clone 与共享 extent 会让目录体积远大于真实物理占用，清除前用 df 前后差值实测。",
            "reclaimable_occupancy 是理论上限，不是承诺可释放的空间。",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True, help="disk_probe 或监控生成的 report.json")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--out", "--output", dest="out", type=Path,
                        help="输出 JSON 路径（--out 与 --output 等价）")
    args = parser.parse_args()
    result = analyze(json.loads(args.report.read_text()), args.policy)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
