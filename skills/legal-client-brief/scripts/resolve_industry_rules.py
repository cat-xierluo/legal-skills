#!/usr/bin/env python3
"""将行业名称解析为 report 或 brief 研究计划。"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

from validate_industry_rules import load_registry, validate_registry


SKILL_DIR = Path(__file__).resolve().parent.parent


def _merge_registry(base: dict, overlay: dict) -> dict:
    merged = copy.deepcopy(base)
    by_id = {pack["id"]: index for index, pack in enumerate(merged.get("packs", [])) if isinstance(pack, dict) and pack.get("id")}
    for pack in overlay.get("packs", []):
        if not isinstance(pack, dict) or not pack.get("id"):
            continue
        if pack["id"] in by_id:
            merged["packs"][by_id[pack["id"]]] = copy.deepcopy(pack)
        else:
            merged.setdefault("packs", []).append(copy.deepcopy(pack))
    return merged


def _score(industry: str, alias: str) -> int:
    query = industry.strip().lower()
    candidate = alias.strip().lower()
    if query == candidate:
        return 1000 + len(candidate)
    if candidate in query:
        return 600 + len(candidate)
    if query in candidate and len(query) >= 2:
        return 300 + len(query)
    return 0


def resolve(data: dict, industry: str, mode: str) -> dict:
    matches: list[tuple[int, dict, str]] = []
    for pack in data.get("packs", []):
        for alias in pack.get("aliases", []):
            score = _score(industry, alias)
            if score:
                matches.append((score, pack, alias))
    matches.sort(key=lambda item: (-item[0], item[1]["id"], item[2]))
    selected = matches[0][1] if matches else None
    common = data["common"]

    source_map: dict[str, dict] = {}
    for source in common.get("sources", []) + (selected.get("sources", []) if selected else []):
        source_map[source["id"]] = source

    if mode == "report":
        mode_plan = {
            "required_dimensions": list(dict.fromkeys(common.get("required_dimensions", []) + (selected.get("report", {}).get("required_dimensions", []) if selected else []))),
            "research_questions": common.get("research_questions", []) + (selected.get("report", {}).get("research_questions", []) if selected else []),
            "indicators": selected.get("report", {}).get("indicators", []) if selected else [],
        }
    else:
        mode_plan = {
            "watch_events": selected.get("brief", {}).get("watch_events", []) if selected else ["政策、监管、标准、执法、判例和重大经营事件"],
            "relevance_questions": selected.get("brief", {}).get("relevance_questions", []) if selected else ["是否改变客户的权利义务、业务流程或风险暴露", "是否形成近期可执行动作"],
        }

    runner_up = []
    seen = {selected["id"]} if selected else set()
    for score, pack, alias in matches[1:]:
        if pack["id"] not in seen:
            runner_up.append({"pack_id": pack["id"], "matched_alias": alias, "score": score})
            seen.add(pack["id"])
        if len(runner_up) == 3:
            break

    return {
        "schema_version": 1,
        "industry_query": industry,
        "mode": mode,
        "matched_pack": selected["id"] if selected else "common",
        "matched_alias": matches[0][2] if matches else None,
        "needs_custom_pack": selected is None,
        "alternative_matches": runner_up,
        "plan": mode_plan,
        "legal_risk_lenses": selected.get("legal_risk_lenses", []) if selected else [],
        "candidate_sources": list(source_map.values()),
        "freshness_rules": common.get("freshness_rules", {}),
        "warnings": (["未命中细分行业包；当前仅提供通用研究路线，正式研究前应补充行业规则。"] if selected is None else []) + (["legal-client-brief 不得直接采用候选信源；每个域名仍须通过本地白名单。"] if mode == "brief" else []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="解析行业规则并输出研究计划 JSON")
    parser.add_argument("--industry", required=True)
    parser.add_argument("--mode", choices=("report", "brief"), required=True)
    parser.add_argument("--registry", default=str(SKILL_DIR / "references" / "industry-rules.yaml"))
    parser.add_argument("--overlay", help="可选本地行业规则补充")
    parser.add_argument("--output", help="输出 JSON；省略则打印到 stdout")
    args = parser.parse_args()

    try:
        data = load_registry(Path(args.registry).resolve())
        if args.overlay:
            data = _merge_registry(data, load_registry(Path(args.overlay).resolve()))
        validation = validate_registry(data)
        if validation["status"] != "PASS":
            print(json.dumps(validation, ensure_ascii=False, indent=2), file=sys.stderr)
            return 1
        result = resolve(data, args.industry, args.mode)
    except ValueError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        target = Path(args.output).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
        print(f"研究计划已写入: {target}")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
