#!/usr/bin/env python3
"""校验 patent-analysis 的无网址、多条款法源登记表。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parents[1]
REGISTER_PATH = SKILL_DIR / "config" / "legal-source-register.json"

EXPECTED_TOP_LEVEL_KEYS = {
    "schema_version",
    "skill_name",
    "skill_version",
    "jurisdiction",
    "baseline_id",
    "verified_on",
    "public_url_policy",
    "official_baseline",
    "sources",
    "doctrine_groups",
    "guide_updates",
    "scenario_impacts",
    "fto_update_policy",
}
EXPECTED_SCENARIOS = set(range(1, 11))
EXPECTED_GUIDE_ORDINALS = set(range(1, 24))
REQUIRED_DOCTRINE_GROUPS = {
    "protection-scope": 2,
    "literal-coverage": 2,
    "equivalence": 2,
    "validity-2026": 2,
    "invalidation-procedure": 2,
    "fto-currentness": 4,
    "valuation-currentness": 2,
}
ALLOWED_SOURCE_KINDS = {
    "law",
    "administrative_regulation",
    "judicial_interpretation",
    "examination_guideline",
}
ALLOWED_SOURCE_STATUSES = {"current"}
ALLOWED_UPDATE_STATUSES = {"direct", "conditional", "out_of_scope"}
ALLOWED_SCENARIO_STATUSES = {"affected", "conditional", "not_affected"}
URL_PATTERN = re.compile(r"(?:https?://|www\.)", flags=re.IGNORECASE)
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
UPDATE_ID_PATTERN = re.compile(r"^G2026-(\d{2})$")


def load_register(path: Path = REGISTER_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("法源登记表根节点必须为对象")
    return data


def valid_iso_date(value: Any) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def require_exact_keys(
    value: Any,
    expected: set[str],
    path: str,
    errors: list[str],
) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{path}: 必须为对象")
        return False
    actual = set(value)
    if actual != expected:
        errors.append(
            f"{path}: 字段不匹配 missing={sorted(expected - actual)} "
            f"extra={sorted(actual - expected)}"
        )
        return False
    return True


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def integer_list(value: Any, allowed: set[int], *, nonempty: bool) -> bool:
    return (
        isinstance(value, list)
        and (bool(value) or not nonempty)
        and len(value) == len(set(value))
        and all(isinstance(item, int) and not isinstance(item, bool) and item in allowed for item in value)
    )


def string_list(value: Any, *, nonempty: bool = True) -> bool:
    return (
        isinstance(value, list)
        and (bool(value) or not nonempty)
        and len(value) == len(set(value))
        and all(nonempty_string(item) for item in value)
    )


def validate_register(
    data: dict[str, Any],
    *,
    expected_skill_version: str | None = None,
) -> list[str]:
    errors: list[str] = []
    if set(data) != EXPECTED_TOP_LEVEL_KEYS:
        errors.append(
            "root: 字段不匹配 "
            f"missing={sorted(EXPECTED_TOP_LEVEL_KEYS - set(data))} "
            f"extra={sorted(set(data) - EXPECTED_TOP_LEVEL_KEYS)}"
        )

    serialized = json.dumps(data, ensure_ascii=False)
    if URL_PATTERN.search(serialized):
        errors.append("root: 公开法源登记表禁止 URL")

    if data.get("schema_version") != 1:
        errors.append("root.schema_version: 必须为 1")
    if data.get("skill_name") != "patent-analysis":
        errors.append("root.skill_name: 必须为 patent-analysis")
    version = data.get("skill_version")
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        errors.append("root.skill_version: 必须为 x.y.z")
    if expected_skill_version is not None and version != expected_skill_version:
        errors.append(
            f"root.skill_version: {version!r} 与发布版本 {expected_skill_version!r} 不一致"
        )
    if data.get("jurisdiction") != "中国":
        errors.append("root.jurisdiction: 必须为中国")
    if not nonempty_string(data.get("baseline_id")):
        errors.append("root.baseline_id: 必须为非空字符串")
    if not valid_iso_date(data.get("verified_on")):
        errors.append("root.verified_on: 必须为有效 ISO 日期")
    if data.get("public_url_policy") != "forbidden":
        errors.append("root.public_url_policy: 必须为 forbidden")

    baseline = data.get("official_baseline")
    if require_exact_keys(
        baseline,
        {"title", "issuing_authority", "order_no", "issued_on", "effective_from"},
        "official_baseline",
        errors,
    ):
        for field in ("title", "issuing_authority", "order_no"):
            if not nonempty_string(baseline[field]):
                errors.append(f"official_baseline.{field}: 必须为非空字符串")
        if baseline["order_no"] != "国家知识产权局令第八十四号":
            errors.append("official_baseline.order_no: 未锁定第八十四号令")
        if not valid_iso_date(baseline["issued_on"]):
            errors.append("official_baseline.issued_on: 必须为有效 ISO 日期")
        if baseline["effective_from"] != "2026-01-01":
            errors.append("official_baseline.effective_from: 必须为 2026-01-01")

    sources = data.get("sources")
    source_ids: set[str] = set()
    if not isinstance(sources, list) or not sources:
        errors.append("sources: 必须为非空列表")
        sources = []
    source_keys = {
        "source_id",
        "short_title",
        "full_title",
        "issuing_authority",
        "kind",
        "status",
        "effective_from",
    }
    for index, source in enumerate(sources):
        path = f"sources[{index}]"
        if not require_exact_keys(source, source_keys, path, errors):
            continue
        source_id = source["source_id"]
        if not nonempty_string(source_id):
            errors.append(f"{path}.source_id: 必须为非空字符串")
        elif source_id in source_ids:
            errors.append(f"{path}.source_id: 重复 {source_id}")
        else:
            source_ids.add(source_id)
        for field in ("short_title", "full_title", "issuing_authority"):
            if not nonempty_string(source[field]):
                errors.append(f"{path}.{field}: 必须为非空字符串")
        if source["kind"] not in ALLOWED_SOURCE_KINDS:
            errors.append(f"{path}.kind: 未知类型 {source['kind']!r}")
        if source["status"] not in ALLOWED_SOURCE_STATUSES:
            errors.append(f"{path}.status: 未知效力状态 {source['status']!r}")
        if not valid_iso_date(source["effective_from"]):
            errors.append(f"{path}.effective_from: 必须为有效 ISO 日期")

    groups = data.get("doctrine_groups")
    group_ids: set[str] = set()
    group_map: dict[str, dict[str, Any]] = {}
    if not isinstance(groups, list) or not groups:
        errors.append("doctrine_groups: 必须为非空列表")
        groups = []
    group_keys = {
        "issue_id",
        "title",
        "min_provisions",
        "affected_scenarios",
        "provisions",
    }
    provision_keys = {"source_id", "citation"}
    for index, group in enumerate(groups):
        path = f"doctrine_groups[{index}]"
        if not require_exact_keys(group, group_keys, path, errors):
            continue
        issue_id = group["issue_id"]
        if not nonempty_string(issue_id):
            errors.append(f"{path}.issue_id: 必须为非空字符串")
            continue
        if issue_id in group_ids:
            errors.append(f"{path}.issue_id: 重复 {issue_id}")
        group_ids.add(issue_id)
        group_map[issue_id] = group
        if not nonempty_string(group["title"]):
            errors.append(f"{path}.title: 必须为非空字符串")
        minimum = group["min_provisions"]
        if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 2:
            errors.append(f"{path}.min_provisions: 复合问题至少为 2")
        if not integer_list(group["affected_scenarios"], EXPECTED_SCENARIOS, nonempty=True):
            errors.append(f"{path}.affected_scenarios: 必须为不重复的场景 1—10 列表")
        provisions = group["provisions"]
        if not isinstance(provisions, list) or not provisions:
            errors.append(f"{path}.provisions: 必须为非空列表")
            continue
        pairs: set[tuple[str, str]] = set()
        for provision_index, provision in enumerate(provisions):
            provision_path = f"{path}.provisions[{provision_index}]"
            if not require_exact_keys(provision, provision_keys, provision_path, errors):
                continue
            source_id = provision["source_id"]
            citation = provision["citation"]
            if source_id not in source_ids:
                errors.append(f"{provision_path}.source_id: 未登记法源 {source_id!r}")
            if not nonempty_string(citation) or not re.search(r"第.+(?:条|节)", citation):
                errors.append(f"{provision_path}.citation: 必须包含具体条款或节号")
            pair = (source_id, citation)
            if pair in pairs:
                errors.append(f"{provision_path}: 重复条款 {pair}")
            pairs.add(pair)
        if isinstance(minimum, int) and len(pairs) < minimum:
            errors.append(f"{path}: 条款数 {len(pairs)} 少于声明的 {minimum}")

    for issue_id, minimum in REQUIRED_DOCTRINE_GROUPS.items():
        group = group_map.get(issue_id)
        if group is None:
            errors.append(f"doctrine_groups: 缺少必需条款组 {issue_id}")
        elif group.get("min_provisions", 0) < minimum:
            errors.append(f"doctrine_groups.{issue_id}: min_provisions 至少为 {minimum}")

    guide_updates = data.get("guide_updates")
    update_ids: set[str] = set()
    update_ordinals: set[int] = set()
    linked_update_ids: set[str] = set()
    update_map: dict[str, dict[str, Any]] = {}
    if not isinstance(guide_updates, list):
        errors.append("guide_updates: 必须为列表")
        guide_updates = []
    update_keys = {
        "update_id",
        "ordinal",
        "guide_section",
        "title",
        "effective_from",
        "verified_on",
        "impact_status",
        "scenario_ids",
        "rationale",
    }
    for index, update in enumerate(guide_updates):
        path = f"guide_updates[{index}]"
        if not require_exact_keys(update, update_keys, path, errors):
            continue
        update_id = update["update_id"]
        ordinal = update["ordinal"]
        match = UPDATE_ID_PATTERN.fullmatch(update_id) if isinstance(update_id, str) else None
        if not match:
            errors.append(f"{path}.update_id: 格式必须为 G2026-NN")
        elif int(match.group(1)) != ordinal:
            errors.append(f"{path}: update_id 与 ordinal 不一致")
        if update_id in update_ids:
            errors.append(f"{path}.update_id: 重复 {update_id}")
        update_ids.add(update_id)
        if not isinstance(ordinal, int) or isinstance(ordinal, bool):
            errors.append(f"{path}.ordinal: 必须为整数")
        elif ordinal in update_ordinals:
            errors.append(f"{path}.ordinal: 重复 {ordinal}")
        else:
            update_ordinals.add(ordinal)
        update_map[update_id] = update
        for field in ("guide_section", "title", "rationale"):
            if not nonempty_string(update[field]):
                errors.append(f"{path}.{field}: 必须为非空字符串")
        if update["effective_from"] != "2026-01-01":
            errors.append(f"{path}.effective_from: 必须为 2026-01-01")
        if not valid_iso_date(update["verified_on"]):
            errors.append(f"{path}.verified_on: 必须为有效 ISO 日期")
        if update["verified_on"] != data.get("verified_on"):
            errors.append(f"{path}.verified_on: 与登记表核验日期不一致")
        status = update["impact_status"]
        scenarios = update["scenario_ids"]
        if status not in ALLOWED_UPDATE_STATUSES:
            errors.append(f"{path}.impact_status: 未知状态 {status!r}")
        if not integer_list(
            scenarios,
            EXPECTED_SCENARIOS,
            nonempty=status in {"direct", "conditional"},
        ):
            errors.append(f"{path}.scenario_ids: 与影响状态不匹配或包含非法场景")
        if status == "out_of_scope" and scenarios:
            errors.append(f"{path}.scenario_ids: out_of_scope 必须为空")

    if update_ordinals != EXPECTED_GUIDE_ORDINALS:
        errors.append(
            "guide_updates: 必须完整覆盖第84号令23项修改；"
            f"缺少={sorted(EXPECTED_GUIDE_ORDINALS - update_ordinals)} "
            f"多余={sorted(update_ordinals - EXPECTED_GUIDE_ORDINALS)}"
        )

    impacts = data.get("scenario_impacts")
    scenario_ids: set[int] = set()
    if not isinstance(impacts, list):
        errors.append("scenario_impacts: 必须为列表")
        impacts = []
    impact_keys = {
        "scenario_id",
        "title",
        "status",
        "guide_update_ids",
        "doctrine_group_ids",
        "rationale",
    }
    for index, impact in enumerate(impacts):
        path = f"scenario_impacts[{index}]"
        if not require_exact_keys(impact, impact_keys, path, errors):
            continue
        scenario_id = impact["scenario_id"]
        if scenario_id not in EXPECTED_SCENARIOS:
            errors.append(f"{path}.scenario_id: 必须为 1—10")
        elif scenario_id in scenario_ids:
            errors.append(f"{path}.scenario_id: 重复 {scenario_id}")
        else:
            scenario_ids.add(scenario_id)
        if not nonempty_string(impact["title"]) or not nonempty_string(impact["rationale"]):
            errors.append(f"{path}: title 与 rationale 必须为非空字符串")
        status = impact["status"]
        if status not in ALLOWED_SCENARIO_STATUSES:
            errors.append(f"{path}.status: 未知状态 {status!r}")
        update_links = impact["guide_update_ids"]
        if not string_list(update_links, nonempty=status != "not_affected"):
            errors.append(f"{path}.guide_update_ids: 必须为不重复字符串列表")
        else:
            unknown = set(update_links) - update_ids
            if unknown:
                errors.append(f"{path}.guide_update_ids: 未知修改项 {sorted(unknown)}")
            linked_update_ids.update(update_links)
        doctrine_links = impact["doctrine_group_ids"]
        if not string_list(doctrine_links):
            errors.append(f"{path}.doctrine_group_ids: 必须为非空不重复字符串列表")
        else:
            unknown = set(doctrine_links) - group_ids
            if unknown:
                errors.append(f"{path}.doctrine_group_ids: 未知条款组 {sorted(unknown)}")

    if scenario_ids != EXPECTED_SCENARIOS:
        errors.append(
            "scenario_impacts: 必须且只能覆盖场景1—10；"
            f"缺少={sorted(EXPECTED_SCENARIOS - scenario_ids)}"
        )
    expected_linked = {
        update_id
        for update_id, update in update_map.items()
        if update.get("impact_status") in {"direct", "conditional"}
    }
    if linked_update_ids != expected_linked:
        errors.append(
            "scenario_impacts: 修改项链接不完整；"
            f"缺少={sorted(expected_linked - linked_update_ids)} "
            f"多余={sorted(linked_update_ids - expected_linked)}"
        )

    policy = data.get("fto_update_policy")
    policy_keys = {
        "scenario_id",
        "required_inputs",
        "baseline_checks",
        "refresh_triggers",
        "stale_action",
    }
    if require_exact_keys(policy, policy_keys, "fto_update_policy", errors):
        if policy["scenario_id"] != 5:
            errors.append("fto_update_policy.scenario_id: 必须为 5")
        expected_inputs = {"目标法域", "产品版本", "实施行为", "检索截止日", "法律状态基线"}
        if not string_list(policy["required_inputs"]) or set(policy["required_inputs"]) != expected_inputs:
            errors.append("fto_update_policy.required_inputs: 必须精确覆盖五项FTO输入")
        required_checks = {"法源效力状态", "指南施行版本", "司法解释修订状态", "目标法域有效权利要求版本", "法律状态查询日"}
        if not string_list(policy["baseline_checks"]) or not required_checks.issubset(policy["baseline_checks"]):
            errors.append("fto_update_policy.baseline_checks: 缺少法源和权利状态检查")
        if not string_list(policy["refresh_triggers"]) or len(policy["refresh_triggers"]) < 4:
            errors.append("fto_update_policy.refresh_triggers: 至少需要四类刷新触发条件")
        if policy["stale_action"] != "停止风险评级，只输出补充或核验清单":
            errors.append("fto_update_policy.stale_action: 必须失败关闭")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 patent-analysis 法源登记表")
    parser.add_argument("path", nargs="?", type=Path, default=REGISTER_PATH)
    parser.add_argument("--expected-version")
    args = parser.parse_args()
    try:
        data = load_register(args.path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 1
    errors = validate_register(data, expected_skill_version=args.expected_version)
    print(
        json.dumps(
            {
                "status": "PASS" if not errors else "FAIL",
                "sources": len(data.get("sources", [])),
                "doctrine_groups": len(data.get("doctrine_groups", [])),
                "guide_updates": len(data.get("guide_updates", [])),
                "scenario_impacts": len(data.get("scenario_impacts", [])),
                "errors": errors,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
