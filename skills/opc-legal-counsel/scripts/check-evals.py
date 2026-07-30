#!/usr/bin/env python3
"""校验 opc-legal-counsel 评测契约，并可检查外部生成的回答。

示例：
    python3 scripts/check-evals.py
    python3 scripts/check-evals.py --self-test
    python3 scripts/check-evals.py --outputs-dir /path/to/answers
    python3 scripts/check-evals.py --outputs-dir /path/to/answers --case fault-01-retrieval-unavailable

回答文件约定：<outputs-dir>/<eval_id>.md

本脚本只验证元数据和文本契约，不能证明法律结论正确、来源真实或
回答在真实 Agent 运行中稳定。法律正确性仍需人工审阅与权威来源核验。
"""

from __future__ import annotations

import argparse
import json
import re
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
    "expected_domains",
    "expected_references",
    "retrieval_requirement",
    "expected_retrieval_scope",
    "expected_escalation",
    "business_expectations",
    "hard_failures",
    "files",
}
ALLOWED_LAYERS = {"business-judgment", "retrieval-orchestration", "fail-closed"}
ALLOWED_DOMAINS = {
    "governance",
    "contracts",
    "tax",
    "ai-compliance",
    "data-compliance",
    "ip",
    "employment",
    "regulatory",
    "disputes",
    "growth-financing",
}
ALLOWED_RETRIEVAL = {"required", "conditional", "not-required"}
ALLOWED_ASSERTIONS = {
    "contains_any",
    "contains_all",
    "contains_any_per_group",
    "not_contains_any",
}
ALLOWED_SEVERITIES = {"hard", "soft"}


@dataclass
class AssertionResult:
    ok: bool
    message: str


@dataclass
class CaseResult:
    ok: bool
    hard_passed: int
    hard_total: int
    soft_passed: int
    soft_total: int
    errors: list[str]
    warnings: list[str]


def configure_paths(skill_root: Path) -> None:
    global ROOT, SKILL_PATH, EVALS_PATH, ASSERTIONS_PATH
    ROOT = skill_root.resolve()
    SKILL_PATH = ROOT / "SKILL.md"
    EVALS_PATH = ROOT / "evals" / "evals.json"
    ASSERTIONS_PATH = ROOT / "evals" / "assertions.json"


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        raise SystemExit(f"缺少文件: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"JSON 格式错误: {path}:{exc.lineno}:{exc.colno} {exc.msg}")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold().replace("\u3000", " ")).strip()


def contains(text: str, term: str) -> bool:
    return normalize(term) in normalize(text)


def terms_found(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if contains(text, term)]


def string_list(value: Any, *, nonempty: bool = True) -> bool:
    return (
        isinstance(value, list)
        and (bool(value) or not nonempty)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def ensure_paths_exist(case_id: str, paths: Any, errors: list[str]) -> None:
    if not string_list(paths, nonempty=False):
        errors.append(f"{case_id}: 路径字段应为字符串列表")
        return
    for relative in paths:
        candidate = ROOT / relative
        if not candidate.exists():
            errors.append(f"{case_id}: 路径不存在: {relative}")


def extract_skill_version() -> str | None:
    try:
        text = SKILL_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    match = re.search(r'^version:\s*["\']?([^"\'\s]+)["\']?\s*$', text, re.MULTILINE)
    return match.group(1) if match else None


def validate_version_consistency(evals_data: dict[str, Any], assertions_data: dict[str, Any]) -> list[str]:
    versions = {
        "SKILL.md": extract_skill_version(),
        "evals.json": evals_data.get("version"),
        "assertions.json": assertions_data.get("version"),
    }
    errors = [f"{name}: 缺少 version" for name, version in versions.items() if not version]
    if len({version for version in versions.values() if version}) > 1:
        errors.append(f"版本号不一致: {versions}")
    return errors


def validate_assertion_schema(assertion: Any, prefix: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(assertion, dict):
        return [f"{prefix}: 断言应为对象"]

    assertion_id = assertion.get("id")
    assertion_type = assertion.get("type")
    severity = assertion.get("severity")
    if not isinstance(assertion_id, str) or not assertion_id.strip():
        errors.append(f"{prefix}: 缺少非空 id")
    if assertion_type not in ALLOWED_ASSERTIONS:
        errors.append(f"{prefix}/{assertion_id}: 不支持的 type {assertion_type!r}")
    if severity not in ALLOWED_SEVERITIES:
        errors.append(f"{prefix}/{assertion_id}: severity 必须为 hard 或 soft")

    if assertion_type == "contains_any_per_group":
        groups = assertion.get("groups")
        if not isinstance(groups, list) or not groups:
            errors.append(f"{prefix}/{assertion_id}: groups 必须为非空列表")
        else:
            for index, group in enumerate(groups):
                if not isinstance(group, dict):
                    errors.append(f"{prefix}/{assertion_id}/group-{index}: 应为对象")
                    continue
                if not isinstance(group.get("label"), str) or not group["label"].strip():
                    errors.append(f"{prefix}/{assertion_id}/group-{index}: 缺少 label")
                if not string_list(group.get("terms")):
                    errors.append(f"{prefix}/{assertion_id}/group-{index}: terms 必须为非空字符串列表")
    elif assertion_type in {"contains_any", "contains_all", "not_contains_any"}:
        if not string_list(assertion.get("terms")):
            errors.append(f"{prefix}/{assertion_id}: terms 必须为非空字符串列表")
    return errors


def validate_metadata(evals_data: dict[str, Any], assertions_data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    evals = evals_data.get("evals")
    if not isinstance(evals, list) or not evals:
        return ["evals/evals.json: evals 必须为非空列表"]

    eval_ids: set[str] = set()
    for index, case in enumerate(evals):
        if not isinstance(case, dict):
            errors.append(f"evals/{index}: 应为对象")
            continue
        case_id = str(case.get("id", f"<index:{index}>"))
        missing = REQUIRED_EVAL_FIELDS - set(case)
        if missing:
            errors.append(f"{case_id}: 缺少字段 {sorted(missing)}")
        if case_id in eval_ids:
            errors.append(f"{case_id}: id 重复")
        eval_ids.add(case_id)

        if case.get("layer") not in ALLOWED_LAYERS:
            errors.append(f"{case_id}: layer 不合法: {case.get('layer')!r}")
        if case.get("retrieval_requirement") not in ALLOWED_RETRIEVAL:
            errors.append(f"{case_id}: retrieval_requirement 不合法")

        domains = case.get("expected_domains")
        if not string_list(domains):
            errors.append(f"{case_id}: expected_domains 应为非空字符串列表")
        else:
            unknown = [domain for domain in domains if domain not in ALLOWED_DOMAINS]
            if unknown:
                errors.append(f"{case_id}: 未知领域 {unknown}")

        for field in ("expected_retrieval_scope", "business_expectations", "hard_failures"):
            if not string_list(case.get(field)):
                errors.append(f"{case_id}: {field} 应为非空字符串列表")
        ensure_paths_exist(case_id, case.get("expected_references"), errors)
        ensure_paths_exist(case_id, case.get("files"), errors)

    assertion_cases = assertions_data.get("cases")
    if not isinstance(assertion_cases, list) or not assertion_cases:
        errors.append("evals/assertions.json: cases 必须为非空列表")
        return errors

    seen_cases: set[str] = set()
    for index, case in enumerate(assertion_cases):
        if not isinstance(case, dict):
            errors.append(f"assertions/{index}: 应为对象")
            continue
        case_id = str(case.get("eval_id", f"<index:{index}>"))
        if case_id not in eval_ids:
            errors.append(f"assertions/{case_id}: eval_id 不存在于 evals.json")
        if case_id in seen_cases:
            errors.append(f"assertions/{case_id}: eval_id 重复")
        seen_cases.add(case_id)

        assertions = case.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            errors.append(f"assertions/{case_id}: assertions 必须为非空列表")
            continue
        assertion_ids: set[str] = set()
        for assertion in assertions:
            errors.extend(validate_assertion_schema(assertion, f"assertions/{case_id}"))
            if isinstance(assertion, dict):
                assertion_id = str(assertion.get("id"))
                if assertion_id in assertion_ids:
                    errors.append(f"assertions/{case_id}: 断言 id 重复: {assertion_id}")
                assertion_ids.add(assertion_id)

        soft_count = sum(
            1 for assertion in assertions
            if isinstance(assertion, dict) and assertion.get("severity") == "soft"
        )
        minimum = case.get("soft_minimum", soft_count)
        if not isinstance(minimum, int) or isinstance(minimum, bool) or not 0 <= minimum <= soft_count:
            errors.append(
                f"assertions/{case_id}: soft_minimum 应为 0 至 {soft_count} 的整数，实际为 {minimum!r}"
            )
    return errors


def evaluate_assertion(answer: str, assertion: dict[str, Any]) -> AssertionResult:
    assertion_id = assertion["id"]
    assertion_type = assertion["type"]
    if assertion_type == "contains_any":
        found = terms_found(answer, assertion["terms"])
        return AssertionResult(bool(found), f"{assertion_id}: 命中 {found}" if found else f"{assertion_id}: 未命中任一关键词")
    if assertion_type == "contains_all":
        missing = [term for term in assertion["terms"] if not contains(answer, term)]
        return AssertionResult(not missing, f"{assertion_id}: 全部命中" if not missing else f"{assertion_id}: 缺少 {missing}")
    if assertion_type == "not_contains_any":
        found = terms_found(answer, assertion["terms"])
        return AssertionResult(not found, f"{assertion_id}: 未出现禁用表述" if not found else f"{assertion_id}: 出现禁用表述 {found}")

    missing_groups: list[str] = []
    for group in assertion["groups"]:
        if not terms_found(answer, group["terms"]):
            missing_groups.append(group["label"])
    return AssertionResult(
        not missing_groups,
        f"{assertion_id}: 所有分组均命中" if not missing_groups else f"{assertion_id}: 未命中分组 {missing_groups}",
    )


def evaluate_case(answer: str, case: dict[str, Any]) -> CaseResult:
    errors: list[str] = []
    warnings: list[str] = []
    hard_passed = hard_total = soft_passed = soft_total = 0

    for assertion in case["assertions"]:
        result = evaluate_assertion(answer, assertion)
        if assertion["severity"] == "hard":
            hard_total += 1
            if result.ok:
                hard_passed += 1
            else:
                errors.append(result.message)
        else:
            soft_total += 1
            if result.ok:
                soft_passed += 1
            else:
                warnings.append(result.message)

    minimum = case.get("soft_minimum", soft_total)
    if soft_passed < minimum:
        errors.append(f"soft 断言通过 {soft_passed}/{soft_total}，低于最低要求 {minimum}")
    ok = hard_passed == hard_total and soft_passed >= minimum
    return CaseResult(ok, hard_passed, hard_total, soft_passed, soft_total, errors, warnings)


def validate_outputs(outputs_dir: Path, assertions_data: dict[str, Any], only_case: str | None) -> list[str]:
    failures: list[str] = []
    selected = [
        case for case in assertions_data["cases"]
        if only_case is None or case["eval_id"] == only_case
    ]
    if only_case and not selected:
        return [f"未找到断言样本: {only_case}"]

    for case in selected:
        case_id = case["eval_id"]
        answer_path = outputs_dir / f"{case_id}.md"
        if not answer_path.exists():
            failures.append(f"{case_id}: 缺少回答文件 {answer_path}")
            continue
        result = evaluate_case(answer_path.read_text(encoding="utf-8"), case)
        print(
            f"{case_id}: hard {result.hard_passed}/{result.hard_total}; "
            f"soft {result.soft_passed}/{result.soft_total}; {'通过' if result.ok else '失败'}"
        )
        for warning in result.warnings:
            print(f"  提示: {warning}")
        failures.extend(f"{case_id}: {error}" for error in result.errors)
    return failures


def run_self_test() -> list[str]:
    errors: list[str] = []
    test_case = {
        "soft_minimum": 1,
        "assertions": [
            {"id": "state", "severity": "hard", "type": "contains_all", "terms": ["RETRIEVAL_UNAVAILABLE"]},
            {"id": "actions", "severity": "hard", "type": "contains_any_per_group", "groups": [{"label": "事实", "terms": ["待核事实"]}, {"label": "渠道", "terms": ["官方渠道"]}]},
            {"id": "forbidden", "severity": "hard", "type": "not_contains_any", "terms": ["最新税率为"]},
            {"id": "fallback", "severity": "soft", "type": "contains_any", "terms": ["主体选择"]},
        ],
    }

    valid = evaluate_case(
        "状态：RETRIEVAL_UNAVAILABLE。先整理待核事实并走官方渠道；当前只提供主体选择框架。",
        test_case,
    )
    if not valid.ok:
        errors.append(f"正例应通过但失败: {valid.errors}")

    poisoned = evaluate_case(
        "状态：RETRIEVAL_UNAVAILABLE。已整理待核事实并走官方渠道，主体选择如下；最新税率为某数值。",
        test_case,
    )
    if poisoned.ok or not any("forbidden" in item for item in poisoned.errors):
        errors.append("故障注入失败：禁用表述被其他正向命中项抵消")

    missing_state = evaluate_case("先整理待核事实并走官方渠道，说明主体选择。", test_case)
    if missing_state.ok:
        errors.append("故障注入失败：缺少依据状态仍被判定通过")

    malformed = {"id": "bad", "severity": "hard", "type": "contains_any", "terms": []}
    if not validate_assertion_schema(malformed, "self-test"):
        errors.append("结构故障注入失败：空 terms 未被拒绝")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 opc-legal-counsel 评测契约与可选回答输出")
    parser.add_argument("skill_root", nargs="?", type=Path, default=ROOT, help="技能根目录")
    parser.add_argument("--outputs-dir", type=Path, help="包含 <eval_id>.md 回答文件的目录")
    parser.add_argument("--case", help="只检查指定 eval_id；需配合 --outputs-dir")
    parser.add_argument("--self-test", action="store_true", help="运行检查器自身的正例与故障注入测试")
    args = parser.parse_args()
    configure_paths(args.skill_root)

    evals_data = load_json(EVALS_PATH)
    assertions_data = load_json(ASSERTIONS_PATH)
    errors = validate_version_consistency(evals_data, assertions_data)
    errors.extend(validate_metadata(evals_data, assertions_data))
    if errors:
        print("评测契约检查失败:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("版本与元数据检查通过")
    print(f"评测样本数: {len(evals_data['evals'])}")
    print(f"断言样本数: {len(assertions_data['cases'])}")

    if args.self_test:
        self_test_errors = run_self_test()
        if self_test_errors:
            print("检查器自测失败:")
            for error in self_test_errors:
                print(f"- {error}")
            return 1
        print("检查器自测通过：正例、禁用表述故障、缺失状态和畸形断言均按预期处理")

    if args.case and not args.outputs_dir:
        print("参数错误: --case 需配合 --outputs-dir")
        return 2
    if args.outputs_dir:
        output_errors = validate_outputs(args.outputs_dir, assertions_data, args.case)
        if output_errors:
            print("输出断言检查失败:")
            for error in output_errors:
                print(f"- {error}")
            return 1
        print("输出断言检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
