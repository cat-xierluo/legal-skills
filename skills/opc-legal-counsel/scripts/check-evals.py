#!/usr/bin/env python3
"""Validate opc-legal-counsel eval metadata and optional answer outputs.

Usage:
    python3 scripts/check-evals.py
    python3 scripts/check-evals.py --outputs-dir path/to/answers

When --outputs-dir is provided, answer files should follow:
    <outputs-dir>/<eval_id>.md
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = ROOT / "SKILL.md"
EVALS_PATH = ROOT / "evals" / "evals.json"
ASSERTIONS_PATH = ROOT / "evals" / "assertions.json"

REQUIRED_EVAL_FIELDS = {
    "id",
    "layer",
    "prompt",
    "expected_routing",
    "expected_next_hop",
    "expected_local_overlay",
    "expected_escalation",
    "recommended_assets",
    "expectations",
    "files",
}

ALLOWED_LAYERS = {"foundation", "reinforcement"}
ALLOWED_ROUTING = {
    "governance",
    "contracts",
    "tax",
    "ip",
    "employment",
    "data-compliance",
    "regulatory",
    "disputes",
    "ai-compliance",
    "growth-financing",
}


@dataclass
class CheckResult:
    ok: bool
    message: str


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        raise SystemExit(f"缺少文件: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"JSON 格式错误: {path}:{exc.lineno}:{exc.colno} {exc.msg}")


def normalize(text: str) -> str:
    return text.casefold().replace("\u3000", " ").strip()


def contains(text: str, term: str) -> bool:
    return normalize(term) in normalize(text)


def terms_found(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if contains(text, term)]


def group_label_and_terms(group: Any) -> tuple[str, list[str]]:
    if isinstance(group, dict):
        label = str(group.get("label", "未命名分组"))
        terms = group.get("terms", [])
    else:
        label = " / ".join(str(item) for item in group)
        terms = group
    if not isinstance(terms, list) or not all(isinstance(term, str) for term in terms):
        raise ValueError(f"断言分组格式错误: {group!r}")
    return label, terms


def evaluate_assertion(answer: str, assertion: dict[str, Any]) -> CheckResult:
    assertion_type = assertion.get("type")
    assertion_id = assertion.get("id", "<missing-id>")

    if assertion_type == "contains_any":
        terms = assertion.get("terms", [])
        found = terms_found(answer, terms)
        if found:
            return CheckResult(True, f"{assertion_id}: 命中 {found}")
        return CheckResult(False, f"{assertion_id}: 未命中任一关键词 {terms}")

    if assertion_type == "contains_all":
        terms = assertion.get("terms", [])
        missing = [term for term in terms if not contains(answer, term)]
        if not missing:
            return CheckResult(True, f"{assertion_id}: 全部命中")
        return CheckResult(False, f"{assertion_id}: 缺少 {missing}")

    if assertion_type == "contains_any_per_group":
        missing_groups = []
        for group in assertion.get("groups", []):
            label, terms = group_label_and_terms(group)
            if not terms_found(answer, terms):
                missing_groups.append(f"{label}({terms})")
        if not missing_groups:
            return CheckResult(True, f"{assertion_id}: 所有分组均命中")
        return CheckResult(False, f"{assertion_id}: 未命中分组 {missing_groups}")

    if assertion_type == "not_contains_any":
        terms = assertion.get("terms", [])
        found = terms_found(answer, terms)
        if not found:
            return CheckResult(True, f"{assertion_id}: 未出现禁用表述")
        return CheckResult(False, f"{assertion_id}: 出现禁用表述 {found}")

    return CheckResult(False, f"{assertion_id}: 未支持的断言类型 {assertion_type!r}")


def ensure_relative_paths_exist(case_id: str, paths: list[str], errors: list[str]) -> None:
    for rel_path in paths:
        if not isinstance(rel_path, str):
            errors.append(f"{case_id}: 路径不是字符串: {rel_path!r}")
            continue
        if rel_path == "none":
            continue
        if not (ROOT / rel_path).exists():
            errors.append(f"{case_id}: 路径不存在: {rel_path}")


def validate_version_consistency() -> list[str]:
    """Check that version strings match across SKILL.md, evals.json, assertions.json."""
    import re

    errors: list[str] = []

    skill_text = SKILL_PATH.read_text(encoding="utf-8")
    skill_match = re.search(r'^version:\s*["\']?(\S+?)["\']?\s*$', skill_text, re.MULTILINE)
    skill_version = skill_match.group(1) if skill_match else None

    evals_data = load_json(EVALS_PATH)
    evals_version = evals_data.get("version")

    assertions_data = load_json(ASSERTIONS_PATH)
    assertions_version = assertions_data.get("version")

    if not skill_version:
        errors.append("SKILL.md: 未找到 version 字段")
    if not evals_version:
        errors.append("evals/evals.json: 未找到 version 字段")
    if not assertions_version:
        errors.append("evals/assertions.json: 未找到 version 字段")

    versions = {"SKILL.md": skill_version, "evals.json": evals_version, "assertions.json": assertions_version}
    unique = {v for v in versions.values() if v}
    if len(unique) > 1:
        errors.append(f"版本号不一致: {versions}")

    return errors


def validate_eval_metadata(evals_data: dict[str, Any], assertions_data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    evals = evals_data.get("evals")
    if not isinstance(evals, list):
        return ["evals/evals.json 缺少列表字段 evals"]

    seen_ids: set[str] = set()
    for index, case in enumerate(evals):
        case_id = str(case.get("id", f"<index:{index}>"))
        missing = REQUIRED_EVAL_FIELDS - set(case)
        if missing:
            errors.append(f"{case_id}: 缺少字段 {sorted(missing)}")

        if case_id in seen_ids:
            errors.append(f"{case_id}: id 重复")
        seen_ids.add(case_id)

        if case.get("layer") not in ALLOWED_LAYERS:
            errors.append(f"{case_id}: layer 不合法: {case.get('layer')!r}")

        routing = case.get("expected_routing", [])
        if not isinstance(routing, list) or not routing:
            errors.append(f"{case_id}: expected_routing 应为非空列表")
        else:
            unknown = [item for item in routing if item not in ALLOWED_ROUTING]
            if unknown:
                errors.append(f"{case_id}: 未知领域路由 {unknown}")

        next_hop = case.get("expected_next_hop", [])
        if not isinstance(next_hop, list) or not next_hop:
            errors.append(f"{case_id}: expected_next_hop 应为非空列表")
        else:
            ensure_relative_paths_exist(case_id, next_hop, errors)

        assets = case.get("recommended_assets", [])
        if not isinstance(assets, list):
            errors.append(f"{case_id}: recommended_assets 应为列表")
        else:
            ensure_relative_paths_exist(case_id, assets, errors)

        expectations = case.get("expectations", [])
        if not isinstance(expectations, list) or len(expectations) < 3:
            errors.append(f"{case_id}: expectations 至少应包含 3 条")

    assertion_cases = assertions_data.get("cases", [])
    if not isinstance(assertion_cases, list):
        errors.append("evals/assertions.json 缺少列表字段 cases")
        return errors

    assertion_ids: set[str] = set()
    for case in assertion_cases:
        case_id = case.get("eval_id")
        if case_id not in seen_ids:
            errors.append(f"assertions: eval_id 不存在于 evals.json: {case_id}")
        if case_id in assertion_ids:
            errors.append(f"assertions: eval_id 重复: {case_id}")
        assertion_ids.add(str(case_id))

        assertions = case.get("assertions", [])
        if not isinstance(assertions, list) or not assertions:
            errors.append(f"assertions/{case_id}: assertions 应为非空列表")
            continue
        for assertion in assertions:
            assertion_type = assertion.get("type")
            if assertion_type not in {
                "contains_any",
                "contains_all",
                "contains_any_per_group",
                "not_contains_any",
            }:
                errors.append(f"assertions/{case_id}: 未支持的断言类型 {assertion_type!r}")
            if not assertion.get("id"):
                errors.append(f"assertions/{case_id}: 断言缺少 id")

    return errors


def validate_outputs(outputs_dir: Path, assertions_data: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    total = 0
    passed = 0

    for case in assertions_data.get("cases", []):
        case_id = case["eval_id"]
        answer_path = outputs_dir / f"{case_id}.md"
        if not answer_path.exists():
            failures.append(f"{case_id}: 缺少回答文件 {answer_path}")
            continue

        answer = answer_path.read_text(encoding="utf-8")
        case_passed = 0
        case_total = 0
        for assertion in case.get("assertions", []):
            case_total += 1
            total += 1
            result = evaluate_assertion(answer, assertion)
            if result.ok:
                case_passed += 1
                passed += 1
            else:
                failures.append(f"{case_id}: {result.message}")

        minimum = int(case.get("minimum_passed_assertions", case_total))
        if case_passed < minimum:
            failures.append(
                f"{case_id}: 断言通过数 {case_passed}/{case_total}，低于最低要求 {minimum}"
            )

    print(f"输出断言通过: {passed}/{total}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 opc-legal-counsel 评测样本与可选回答输出")
    parser.add_argument(
        "--outputs-dir",
        type=Path,
        help="可选：包含 <eval_id>.md 回答文件的目录，用于执行文本断言",
    )
    args = parser.parse_args()

    evals_data = load_json(EVALS_PATH)
    assertions_data = load_json(ASSERTIONS_PATH)

    version_errors = validate_version_consistency()
    if version_errors:
        print("版本一致性检查失败:")
        for error in version_errors:
            print(f"- {error}")
        return 1

    print("版本一致性检查通过")

    errors = validate_eval_metadata(evals_data, assertions_data)
    if errors:
        print("元数据检查失败:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("元数据检查通过")
    print(f"评测样本数: {len(evals_data['evals'])}")
    print(f"重点断言样本数: {len(assertions_data['cases'])}")

    if args.outputs_dir:
        output_errors = validate_outputs(args.outputs_dir, assertions_data)
        if output_errors:
            print("输出断言检查失败:")
            for error in output_errors:
                print(f"- {error}")
            return 1
        print("输出断言检查通过")

    return 0


if __name__ == "__main__":
    sys.exit(main())
