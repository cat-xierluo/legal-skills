#!/usr/bin/env python3
"""校验 patent-analysis 十场景评测契约，并可检查外部生成的回答。

示例：
    python3 scripts/check_evals.py
    python3 scripts/check_evals.py --self-test
    python3 scripts/check_evals.py --outputs-dir /path/to/answers
    python3 scripts/check_evals.py --outputs-dir /path/to/answers --case 3

回答文件名由 ``evals/assertions.json`` 的 ``answer_file_pattern`` 决定，
当前约定为 ``01.md`` 至 ``10.md``。

本脚本只验证样本元数据和文本断言，不能证明法律结论正确、法源现行、
跨模型一致或长期稳定。真实法律结论仍须结合正式材料和现行法人工复核。
"""

from __future__ import annotations

import argparse
import copy
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

EXPECTED_SKILL_NAME = "patent-analysis"
EXPECTED_EVAL_IDS = set(range(1, 11))
REQUIRED_EVAL_FIELDS = {
    "id",
    "prompt",
    "expected_output",
    "files",
    "expectations",
}
ALLOWED_ASSERTIONS = {
    "contains_any",
    "contains_all",
    "contains_any_per_group",
    "not_contains_any",
    "not_matches_any",
    "not_affirm_any",
}
POSITIVE_ASSERTIONS = {
    "contains_any",
    "contains_all",
    "contains_any_per_group",
}
NEGATIVE_ASSERTIONS = {"not_contains_any", "not_matches_any", "not_affirm_any"}
ALLOWED_SEVERITIES = {"hard", "soft"}
REQUIRED_ASSERTION_IDS = {
    1: {"required-input-gaps", "summary-stop-boundary", "forbidden-definitive-conclusion"},
    2: {"separate-patent-records", "ranking-stop-boundary", "forbidden-ranking"},
    3: {"selected-claims-and-c-state", "literal-and-equivalent-gates", "equivalence-elements-and-limits", "multi-provision-basis", "forbidden-majority-coverage"},
    4: {"validity-evidence-gaps", "probability-stop-boundary", "forbidden-validity-score"},
    5: {"fto-five-inputs", "fto-stop-gate", "fto-legal-baseline-refresh", "forbidden-fto-clearance"},
    6: {"design-around-input-gate", "coverage-and-equivalence-review", "design-around-legal-basis", "forbidden-safe-harbor"},
    7: {"valuation-required-inputs", "valuation-stop-gate", "forbidden-invented-value"},
    8: {"four-part-equivalence-test", "equivalence-limitations", "equivalence-multi-provision-basis", "forbidden-overall-equivalence"},
    9: {"deadline-verification-gate", "amendment-source-boundary", "invalidation-multi-provision-basis", "amendment-submission-format", "forbidden-old-procedure-rules"},
    10: {"visual-evidence-gates", "no-conclusion-visual", "forbidden-green-conclusion"},
}


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
    """允许测试或其他技能复用检查器时显式切换技能根目录。"""
    global ROOT, SKILL_PATH, EVALS_PATH, ASSERTIONS_PATH
    ROOT = skill_root.resolve()
    SKILL_PATH = ROOT / "SKILL.md"
    EVALS_PATH = ROOT / "evals" / "evals.json"
    ASSERTIONS_PATH = ROOT / "evals" / "assertions.json"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_contract() -> tuple[dict[str, Any], dict[str, Any]]:
    return load_json(EVALS_PATH), load_json(ASSERTIONS_PATH)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold().replace("\u3000", " ")).strip()


def contains(text: str, term: str) -> bool:
    return normalize(term) in normalize(text)


def terms_found(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if contains(text, term)]


SAFE_NEGATION_MARKERS = (
    "不能",
    "不得",
    "不应",
    "不可",
    "无法",
    "尚不能",
    "暂不能",
    "不支持",
    "不构成",
    "不等于",
    "不意味着",
    "不足以",
    "拒绝",
    "禁止",
    "避免",
    "不予",
    "不作",
    "未认定",
    "无从",
    "不要写",
    "不能写",
    "不得写",
    "要求写",
    "要求直接",
    "题设要求",
    "委托人要求",
    "主张",
    "声称",
    "所谓",
)
DOUBLE_NEGATION_MARKERS = ("不得不", "不能不", "不可不", "不会不", "并非不")
CLAUSE_BREAK = re.compile(r"[。；;！？\n]|但是|然而|因此|所以|但|却|仍然|仍")


def is_safe_negative_context(prefix: str) -> bool:
    clause = CLAUSE_BREAK.split(prefix)[-1]
    if any(marker in clause for marker in DOUBLE_NEGATION_MARKERS):
        return False
    return any(marker in clause for marker in SAFE_NEGATION_MARKERS)


def affirmative_terms_found(text: str, terms: list[str]) -> list[str]:
    """查找未被否定、引用请求或对方主张限定的禁用结论。

    仅在禁用词所在的当前分句检查语境；“不能确定，但总体低风险”会在
    “但”后重新开始判断，因此仍被识别为肯定结论。
    """
    found: list[str] = []
    for line in text.splitlines():
        lowered = line.casefold()
        for term in terms:
            lowered_term = term.casefold()
            start = 0
            while True:
                index = lowered.find(lowered_term, start)
                if index < 0:
                    break
                prefix = line[:index]
                if not is_safe_negative_context(prefix):
                    found.append(term)
                    break
                start = index + max(1, len(term))
    return found


def affirmative_patterns_found(text: str, patterns: list[str]) -> list[str]:
    found: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            if not is_safe_negative_context(text[: match.start()]):
                found.append(pattern)
                break
    return found


def string_list(value: Any, *, nonempty: bool = True) -> bool:
    return (
        isinstance(value, list)
        and (bool(value) or not nonempty)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def integer_at_least(value: Any, minimum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def extract_skill_version() -> str | None:
    try:
        text = SKILL_PATH.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r'^version:\s*["\']?([^"\'\s]+)["\']?\s*$', text, re.MULTILINE)
    return match.group(1) if match else None


def validate_version_and_name(
    evals_data: dict[str, Any], assertions_data: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    for name, data in (("evals.json", evals_data), ("assertions.json", assertions_data)):
        if data.get("skill_name") != EXPECTED_SKILL_NAME:
            errors.append(
                f"{name}: skill_name={data.get('skill_name')!r}，应为 {EXPECTED_SKILL_NAME!r}"
            )

    versions = {
        "SKILL.md": extract_skill_version(),
        "evals.json": evals_data.get("version"),
        "assertions.json": assertions_data.get("version"),
    }
    errors.extend(f"{name}: 缺少 version" for name, version in versions.items() if not version)
    if len({version for version in versions.values() if version}) > 1:
        errors.append(f"版本号不一致: {versions}")
    return errors


def ensure_paths_exist(eval_id: int, paths: Any, errors: list[str]) -> None:
    if not string_list(paths, nonempty=False):
        errors.append(f"eval-{eval_id}: files 应为字符串列表")
        return
    for relative in paths:
        candidate = (ROOT / relative).resolve()
        try:
            candidate.relative_to(ROOT)
        except ValueError:
            errors.append(f"eval-{eval_id}: files 不得指向技能目录之外: {relative}")
            continue
        if not candidate.is_file():
            errors.append(f"eval-{eval_id}: 输入文件不存在: {relative}")


def validate_assertion_schema(assertion: Any, prefix: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(assertion, dict):
        return [f"{prefix}: 断言应为对象"]

    assertion_id = assertion.get("id")
    assertion_type = assertion.get("type")
    severity = assertion.get("severity")
    if not isinstance(assertion_id, str) or not assertion_id.strip():
        errors.append(f"{prefix}: 缺少非空 id")
    if not isinstance(assertion.get("description"), str) or not assertion["description"].strip():
        errors.append(f"{prefix}/{assertion_id}: 缺少非空 description")
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
                    errors.append(
                        f"{prefix}/{assertion_id}/group-{index}: terms 必须为非空字符串列表"
                    )
    elif assertion_type in {"contains_any", "contains_all", "not_contains_any"}:
        if not string_list(assertion.get("terms")):
            errors.append(f"{prefix}/{assertion_id}: terms 必须为非空字符串列表")
    elif assertion_type == "not_affirm_any":
        if not string_list(assertion.get("terms")):
            errors.append(f"{prefix}/{assertion_id}: terms 必须为非空字符串列表")
        patterns = assertion.get("patterns", [])
        if not string_list(patterns, nonempty=False):
            errors.append(f"{prefix}/{assertion_id}: patterns 应为字符串列表")
        else:
            for pattern in patterns:
                try:
                    re.compile(pattern)
                except re.error as exc:
                    errors.append(f"{prefix}/{assertion_id}: 非法正则 {pattern!r}: {exc}")
        affirmative_patterns = assertion.get("affirmative_patterns", [])
        if not string_list(affirmative_patterns, nonempty=False):
            errors.append(f"{prefix}/{assertion_id}: affirmative_patterns 应为字符串列表")
        else:
            for pattern in affirmative_patterns:
                try:
                    re.compile(pattern)
                except re.error as exc:
                    errors.append(
                        f"{prefix}/{assertion_id}: 非法 affirmative_pattern {pattern!r}: {exc}"
                    )
    elif assertion_type == "not_matches_any":
        patterns = assertion.get("patterns")
        if not string_list(patterns):
            errors.append(f"{prefix}/{assertion_id}: patterns 必须为非空字符串列表")
        else:
            for pattern in patterns:
                try:
                    re.compile(pattern)
                except re.error as exc:
                    errors.append(f"{prefix}/{assertion_id}: 非法正则 {pattern!r}: {exc}")
    return errors


def validate_policy(assertions_data: dict[str, Any]) -> tuple[dict[str, int], list[str]]:
    policy = assertions_data.get("policy")
    if not isinstance(policy, dict):
        return {}, ["assertions.json: policy 应为对象"]

    keys = {
        "minimum_hard_positive": 2,
        "minimum_hard_negative": 1,
        "minimum_soft": 1,
    }
    errors: list[str] = []
    values: dict[str, int] = {}
    for key, floor in keys.items():
        value = policy.get(key)
        if not integer_at_least(value, floor):
            errors.append(f"assertions.json: policy.{key} 应为不小于 {floor} 的整数")
        else:
            values[key] = value
    if not isinstance(policy.get("hard_failure_rule"), str) or not policy["hard_failure_rule"].strip():
        errors.append("assertions.json: policy.hard_failure_rule 应为非空字符串")
    return values, errors


def validate_metadata(
    evals_data: dict[str, Any], assertions_data: dict[str, Any]
) -> list[str]:
    errors = validate_version_and_name(evals_data, assertions_data)
    policy, policy_errors = validate_policy(assertions_data)
    errors.extend(policy_errors)

    evals = evals_data.get("evals")
    if not isinstance(evals, list):
        return errors + ["evals.json: evals 必须为列表"]

    eval_ids: list[int] = []
    for index, case in enumerate(evals):
        if not isinstance(case, dict):
            errors.append(f"evals/{index}: 应为对象")
            continue
        eval_id = case.get("id")
        if not isinstance(eval_id, int) or isinstance(eval_id, bool):
            errors.append(f"evals/{index}: id 必须为整数")
            continue
        eval_ids.append(eval_id)
        missing = REQUIRED_EVAL_FIELDS - set(case)
        if missing:
            errors.append(f"eval-{eval_id}: 缺少字段 {sorted(missing)}")
        for field in ("prompt", "expected_output"):
            if not isinstance(case.get(field), str) or not case[field].strip():
                errors.append(f"eval-{eval_id}: {field} 应为非空字符串")
        expectations = case.get("expectations")
        if not string_list(expectations) or len(expectations) < 3:
            errors.append(f"eval-{eval_id}: expectations 至少包含 3 条可核验陈述")
        ensure_paths_exist(eval_id, case.get("files"), errors)

    eval_id_set = set(eval_ids)
    if len(eval_ids) != len(eval_id_set):
        errors.append("evals.json: id 存在重复")
    if eval_id_set != EXPECTED_EVAL_IDS:
        errors.append(
            "evals.json: 必须且只能覆盖场景 1—10；"
            f"缺少={sorted(EXPECTED_EVAL_IDS - eval_id_set)}，"
            f"多余={sorted(eval_id_set - EXPECTED_EVAL_IDS)}"
        )

    answer_pattern = assertions_data.get("answer_file_pattern")
    if answer_pattern != "{eval_id:02d}.md":
        errors.append(
            "assertions.json: answer_file_pattern 必须为 '{eval_id:02d}.md'"
        )

    assertion_cases = assertions_data.get("cases")
    if not isinstance(assertion_cases, list):
        return errors + ["assertions.json: cases 必须为列表"]

    seen_cases: set[int] = set()
    for index, case in enumerate(assertion_cases):
        if not isinstance(case, dict):
            errors.append(f"assertions/{index}: 应为对象")
            continue
        eval_id = case.get("eval_id")
        if not isinstance(eval_id, int) or isinstance(eval_id, bool):
            errors.append(f"assertions/{index}: eval_id 必须为整数")
            continue
        if eval_id not in EXPECTED_EVAL_IDS:
            errors.append(f"assertions/{eval_id}: eval_id 不属于场景 1—10")
        if eval_id in seen_cases:
            errors.append(f"assertions/{eval_id}: eval_id 重复")
        seen_cases.add(eval_id)

        assertions = case.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            errors.append(f"assertions/{eval_id}: assertions 必须为非空列表")
            continue

        assertion_ids: set[str] = set()
        hard_positive = hard_negative = soft_count = 0
        for assertion in assertions:
            errors.extend(validate_assertion_schema(assertion, f"assertions/{eval_id}"))
            if not isinstance(assertion, dict):
                continue
            assertion_id = assertion.get("id")
            if isinstance(assertion_id, str):
                if assertion_id in assertion_ids:
                    errors.append(f"assertions/{eval_id}: 断言 id 重复: {assertion_id}")
                assertion_ids.add(assertion_id)
            if assertion.get("severity") == "hard":
                if assertion.get("type") in POSITIVE_ASSERTIONS:
                    hard_positive += 1
                elif assertion.get("type") in NEGATIVE_ASSERTIONS:
                    hard_negative += 1
            elif assertion.get("severity") == "soft":
                soft_count += 1

        required_ids = REQUIRED_ASSERTION_IDS.get(eval_id, set())
        missing_ids = required_ids - assertion_ids
        if missing_ids:
            errors.append(f"assertions/{eval_id}: 缺少场景关键断言 {sorted(missing_ids)}")

        if policy:
            if hard_positive < policy["minimum_hard_positive"]:
                errors.append(
                    f"assertions/{eval_id}: hard 正向断言仅 {hard_positive} 条，"
                    f"至少需要 {policy['minimum_hard_positive']} 条"
                )
            if hard_negative < policy["minimum_hard_negative"]:
                errors.append(
                    f"assertions/{eval_id}: hard 禁止性断言仅 {hard_negative} 条，"
                    f"至少需要 {policy['minimum_hard_negative']} 条"
                )
            if soft_count < policy["minimum_soft"]:
                errors.append(
                    f"assertions/{eval_id}: soft 断言仅 {soft_count} 条，"
                    f"至少需要 {policy['minimum_soft']} 条"
                )

        minimum = case.get("soft_minimum")
        if not integer_at_least(minimum, 1) or minimum > soft_count:
            errors.append(
                f"assertions/{eval_id}: soft_minimum 应为 1 至 {soft_count} 的整数，"
                f"实际为 {minimum!r}"
            )

    if seen_cases != EXPECTED_EVAL_IDS:
        errors.append(
            "assertions.json: 必须且只能为场景 1—10 各提供一个断言集；"
            f"缺少={sorted(EXPECTED_EVAL_IDS - seen_cases)}，"
            f"多余={sorted(seen_cases - EXPECTED_EVAL_IDS)}"
        )
    if seen_cases != eval_id_set:
        errors.append("evals.json 与 assertions.json 的场景 ID 不一致")
    return errors


def validate_contract() -> list[str]:
    """返回完整契约错误列表，供静态验证器和单元测试复用。"""
    try:
        evals_data, assertions_data = load_contract()
    except FileNotFoundError as exc:
        return [f"缺少文件: {exc.filename}"]
    except json.JSONDecodeError as exc:
        return [f"JSON 格式错误: {exc.doc!r} at {exc.lineno}:{exc.colno} {exc.msg}"]
    except OSError as exc:
        return [f"读取评测契约失败: {exc}"]
    if not isinstance(evals_data, dict) or not isinstance(assertions_data, dict):
        return ["evals.json 与 assertions.json 的根节点必须为对象"]
    return validate_metadata(evals_data, assertions_data)


def evaluate_assertion(answer: str, assertion: dict[str, Any]) -> AssertionResult:
    assertion_id = assertion["id"]
    assertion_type = assertion["type"]
    if assertion_type == "contains_any":
        found = terms_found(answer, assertion["terms"])
        message = f"{assertion_id}: 命中 {found}" if found else f"{assertion_id}: 未命中任一关键词"
        return AssertionResult(bool(found), message)
    if assertion_type == "contains_all":
        missing = [term for term in assertion["terms"] if not contains(answer, term)]
        message = f"{assertion_id}: 全部命中" if not missing else f"{assertion_id}: 缺少 {missing}"
        return AssertionResult(not missing, message)
    if assertion_type == "not_contains_any":
        found = terms_found(answer, assertion["terms"])
        message = f"{assertion_id}: 未出现禁用表述" if not found else f"{assertion_id}: 出现禁用表述 {found}"
        return AssertionResult(not found, message)
    if assertion_type == "not_matches_any":
        found = [pattern for pattern in assertion["patterns"] if re.search(pattern, answer)]
        message = f"{assertion_id}: 未命中禁用模式" if not found else f"{assertion_id}: 命中禁用模式 {found}"
        return AssertionResult(not found, message)
    if assertion_type == "not_affirm_any":
        found_terms = affirmative_terms_found(answer, assertion["terms"])
        found_affirmative_patterns = affirmative_patterns_found(
            answer, assertion.get("affirmative_patterns", [])
        )
        found_patterns = [
            pattern for pattern in assertion.get("patterns", []) if re.search(pattern, answer)
        ]
        ok = not found_terms and not found_affirmative_patterns and not found_patterns
        message = (
            f"{assertion_id}: 未出现肯定性禁用结论或禁用模式"
            if ok
            else (
                f"{assertion_id}: 肯定性禁用结论={found_terms}，"
                f"肯定性禁用模式={found_affirmative_patterns}，禁用模式={found_patterns}"
            )
        )
        return AssertionResult(ok, message)

    missing_groups = [
        group["label"]
        for group in assertion["groups"]
        if not terms_found(answer, group["terms"])
    ]
    message = (
        f"{assertion_id}: 所有分组均命中"
        if not missing_groups
        else f"{assertion_id}: 未命中分组 {missing_groups}"
    )
    return AssertionResult(not missing_groups, message)


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

    minimum = case["soft_minimum"]
    if soft_passed < minimum:
        errors.append(f"soft 断言通过 {soft_passed}/{soft_total}，低于最低要求 {minimum}")
    ok = hard_passed == hard_total and soft_passed >= minimum
    return CaseResult(ok, hard_passed, hard_total, soft_passed, soft_total, errors, warnings)


def answer_filename(eval_id: int, pattern: str) -> str:
    return pattern.format(eval_id=eval_id)


def validate_outputs(
    outputs_dir: Path,
    assertions_data: dict[str, Any],
    only_case: int | None,
) -> list[str]:
    failures: list[str] = []
    selected = [
        case
        for case in assertions_data["cases"]
        if only_case is None or case["eval_id"] == only_case
    ]
    if only_case is not None and not selected:
        return [f"未找到断言样本: {only_case}"]

    pattern = assertions_data["answer_file_pattern"]
    for case in selected:
        eval_id = case["eval_id"]
        answer_path = outputs_dir / answer_filename(eval_id, pattern)
        if not answer_path.is_file():
            failures.append(f"eval-{eval_id}: 缺少回答文件 {answer_path}")
            continue
        answer = answer_path.read_text(encoding="utf-8")
        result = evaluate_case(answer, case)
        print(
            f"eval-{eval_id}: hard {result.hard_passed}/{result.hard_total}; "
            f"soft {result.soft_passed}/{result.soft_total}; {'通过' if result.ok else '失败'}"
        )
        for warning in result.warnings:
            print(f"  提示: {warning}")
        failures.extend(f"eval-{eval_id}: {error}" for error in result.errors)
    return failures


def run_self_test(
    evals_data: dict[str, Any], assertions_data: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    test_case = {
        "soft_minimum": 1,
        "assertions": [
            {
                "id": "inputs",
                "description": "输入",
                "severity": "hard",
                "type": "contains_all",
                "terms": ["目标法域", "法律状态"],
            },
            {
                "id": "stop",
                "description": "停止",
                "severity": "hard",
                "type": "contains_any",
                "terms": ["停止风险评级"],
            },
            {
                "id": "forbidden",
                "description": "禁用",
                "severity": "hard",
                "type": "not_affirm_any",
                "terms": ["低风险"],
                "patterns": [],
            },
            {
                "id": "plan",
                "description": "计划",
                "severity": "soft",
                "type": "contains_any",
                "terms": ["补充清单"],
            },
        ],
    }

    valid = evaluate_case(
        "目标法域和法律状态缺失，停止风险评级。以下为补充清单。",
        test_case,
    )
    if not valid.ok:
        errors.append(f"正例应通过但失败: {valid.errors}")

    poisoned = evaluate_case(
        "目标法域和法律状态缺失，停止风险评级。以下为补充清单。\n结论：低风险",
        test_case,
    )
    if poisoned.ok or not any("forbidden" in item for item in poisoned.errors):
        errors.append("故障注入失败：错误结论被正向关键词抵消")

    negated = evaluate_case(
        "目标法域和法律状态缺失，停止风险评级。以下为补充清单。不能据此认定低风险。",
        test_case,
    )
    if not negated.ok:
        errors.append(f"否定句不应被误杀: {negated.errors}")

    adversative = evaluate_case(
        "目标法域和法律状态缺失，停止风险评级。以下为补充清单。"
        "虽然证据不足，但总体低风险。",
        test_case,
    )
    if adversative.ok:
        errors.append("故障注入失败：转折后的错误结论未被识别")

    double_negative = evaluate_case(
        "目标法域和法律状态缺失，停止风险评级。以下为补充清单。不得不认定低风险。",
        test_case,
    )
    if double_negative.ok:
        errors.append("故障注入失败：双重否定的肯定结论未被识别")

    missing_gate = evaluate_case("目标法域和法律状态缺失。以下为补充清单。", test_case)
    if missing_gate.ok:
        errors.append("故障注入失败：缺少停止门禁仍被判定通过")

    malformed = {
        "id": "bad",
        "description": "非法类型",
        "severity": "hard",
        "type": "unknown",
    }
    if not validate_assertion_schema(malformed, "self-test"):
        errors.append("结构故障注入失败：未知断言类型未被拒绝")

    missing_scenario = copy.deepcopy(evals_data)
    missing_scenario["evals"] = missing_scenario["evals"][:-1]
    if not any("场景 1—10" in item for item in validate_metadata(missing_scenario, assertions_data)):
        errors.append("契约故障注入失败：删除场景 10 未被拒绝")

    weak_assertions = copy.deepcopy(assertions_data)
    first_case = weak_assertions["cases"][0]
    first_case["assertions"] = [
        assertion
        for assertion in first_case["assertions"]
        if assertion["type"] not in NEGATIVE_ASSERTIONS
    ]
    if not any("hard 禁止性断言" in item for item in validate_metadata(evals_data, weak_assertions)):
        errors.append("契约故障注入失败：删除 hard 禁止性断言未被拒绝")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 patent-analysis 十场景评测契约")
    parser.add_argument("skill_root", nargs="?", type=Path, default=ROOT, help="技能根目录")
    parser.add_argument("--outputs-dir", type=Path, help="包含 01.md 至 10.md 的回答目录")
    parser.add_argument("--case", type=int, choices=range(1, 11), help="只检查指定场景")
    parser.add_argument("--self-test", action="store_true", help="运行正例和故障注入自测")
    args = parser.parse_args()
    configure_paths(args.skill_root)

    try:
        evals_data, assertions_data = load_contract()
    except FileNotFoundError as exc:
        print(f"缺少文件: {exc.filename}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"JSON 格式错误: {exc.lineno}:{exc.colno} {exc.msg}")
        return 1
    except OSError as exc:
        print(f"读取评测契约失败: {exc}")
        return 1

    errors = validate_metadata(evals_data, assertions_data)
    if errors:
        print("评测契约检查失败:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("版本、十场景覆盖和断言策略检查通过")
    print(f"评测样本数: {len(evals_data['evals'])}")
    print(f"断言样本数: {len(assertions_data['cases'])}")

    if args.self_test:
        self_test_errors = run_self_test(evals_data, assertions_data)
        if self_test_errors:
            print("检查器自测失败:")
            for error in self_test_errors:
                print(f"- {error}")
            return 1
        print(
            "检查器自测通过：正例、错误结论、否定/转折/双重否定、缺失门禁、"
            "未知类型、缺场景和弱断言均按预期处理"
        )

    if args.case is not None and args.outputs_dir is None:
        print("参数错误: --case 需配合 --outputs-dir")
        return 2
    if args.outputs_dir is not None:
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
