#!/usr/bin/env python3
"""行业规则解析器的正例、失败例与逃逸例。"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

from resolve_industry_rules import resolve
from validate_industry_rules import load_registry, validate_registry


def main() -> int:
    registry = load_registry(Path(__file__).resolve().parent.parent / "references" / "industry-rules.yaml")
    cases: list[tuple[str, bool, str]] = []

    validation = validate_registry(registry)
    cases.append(("注册表正例", validation["status"] == "PASS", validation["status"]))

    report = resolve(registry, "人形机器人制造", "report")
    cases.append(("正式报告命中制造业", report["matched_pack"] == "advanced-manufacturing" and not report["needs_custom_pack"], report["matched_pack"]))

    brief = resolve(registry, "生成式AI", "brief")
    brief_warning = any("白名单" in item for item in brief["warnings"])
    cases.append(("客户简报保留白名单警告", brief["matched_pack"] == "ai-data" and brief_warning, str(brief["warnings"])))

    unknown = resolve(registry, "量子香氛设备", "report")
    cases.append(("未知行业显式回退", unknown["matched_pack"] == "common" and unknown["needs_custom_pack"], str(unknown)))

    broken = copy.deepcopy(registry)
    broken["packs"][0]["sources"][0]["url"] = "http://not-secure.invalid"
    broken_result = validate_registry(broken)
    cases.append(("错误 URL 被阻断", broken_result["status"] == "FAIL" and any(item["id"] == "RULE-SOURCE-URL" for item in broken_result["findings"]), str(broken_result["findings"])))

    failed = False
    for name, ok, evidence in cases:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {evidence}")
        failed = failed or not ok
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
