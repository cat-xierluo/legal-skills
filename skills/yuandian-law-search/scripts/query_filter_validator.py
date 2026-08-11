#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检索计划 query 的 interface×filter 契约校验。"""

import argparse
import json
import sys
from pathlib import Path

import yd_search


PLANNED_API_INTERFACES = {
    "search",
    "keyword",
    "detail",
    "case",
    "case-semantic",
    "case-detail",
    "regulation",
    "regulation-detail",
    "enterprise",
    "enterprise-detail",
    "enterprise-search",
    "enterprise-base",
    "enterprise-summary",
    "enterprise-list",
    "hall-detect",
}


class PlanInputError(ValueError):
    """检索计划不是可校验的 JSON/对象结构。"""


def _load_valid_filters():
    """从实际 CLI parser 读取研究查询接口字段；失败时拒绝继续校验。"""
    parser = yd_search.build_parser()
    discovered = {}
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for name, subparser in action.choices.items():
            fields = set()
            for sub_action in subparser._actions:
                for option in sub_action.option_strings:
                    if option not in ("-h", "--help"):
                        fields.add(option.lstrip("-"))
            discovered[name] = fields

    missing = PLANNED_API_INTERFACES - discovered.keys()
    if missing:
        raise RuntimeError(f"yd_search parser 缺少可规划 API 接口: {sorted(missing)}")
    return {name: discovered[name] for name in sorted(PLANNED_API_INTERFACES)}


INITIALIZATION_ERROR = None
try:
    VALID_FILTERS = _load_valid_filters()
except Exception as exc:  # CLI 在 main 中统一转为退出码 2
    VALID_FILTERS = {}
    INITIALIZATION_ERROR = exc
FIELD_OWNERS = {}
for _interface, _fields in VALID_FILTERS.items():
    for _field in _fields:
        FIELD_OWNERS.setdefault(_field, []).append(_interface)


def _normalize(key):
    key = key.strip()
    while key.startswith("-"):
        key = key[1:]
    return key


def _violation(case_id, query_id, interface, field, message):
    return {
        "case_id": case_id,
        "query_id": query_id,
        "interface": interface,
        "field": field,
        "msg": message,
    }


def validate_queries(queries, case_id="?"):
    """校验一组 query；未知接口、错误类型和非法字段均 fail-closed。"""
    if INITIALIZATION_ERROR is not None:
        raise RuntimeError(f"无法从 yd_search 初始化字段表: {INITIALIZATION_ERROR}")
    if not isinstance(queries, list):
        return [_violation(case_id, "?", "(未知)", "queries", "queries 必须是数组")]

    violations = []
    for index, query in enumerate(queries):
        if not isinstance(query, dict):
            violations.append(
                _violation(case_id, f"#{index}", "(未知)", None, "query 必须是 JSON 对象")
            )
            continue

        query_id = query.get("id") or f"#{index}"
        raw_interface = query.get("interface")
        interface = raw_interface.strip() if isinstance(raw_interface, str) else ""
        if interface not in VALID_FILTERS:
            violations.append(
                _violation(
                    case_id,
                    query_id,
                    interface or "(空/非字符串)",
                    None,
                    f"未知/缺失 interface；可用值: {sorted(VALID_FILTERS)}",
                )
            )
            continue

        filters = query.get("filters")
        if filters is None:
            filters = {}
        if not isinstance(filters, dict):
            violations.append(
                _violation(case_id, query_id, interface, "filters", "filters 必须是 JSON 对象")
            )
            continue

        legal = VALID_FILTERS[interface]
        for raw_key in filters:
            if not isinstance(raw_key, str):
                violations.append(
                    _violation(case_id, query_id, interface, repr(raw_key), "filter 名必须是字符串")
                )
                continue
            key = _normalize(raw_key)
            if key in legal:
                continue
            owners = FIELD_OWNERS.get(key, [])
            hint = f"（属 {owners[0]}）" if len(owners) == 1 else (
                f"（属 {owners}）" if owners else "（未知字段；请使用 CLI 的连字符参数名）"
            )
            violations.append(
                _violation(
                    case_id,
                    query_id,
                    interface,
                    raw_key,
                    f"--{key} 不被 {interface} 支持{hint}",
                )
            )
    return violations


def _extract_cases(plan):
    if isinstance(plan, list):
        return [(f"#{index}", case) for index, case in enumerate(plan)]
    if not isinstance(plan, dict):
        raise PlanInputError("顶层必须是 JSON 对象或数组")
    if "queries" in plan:
        return [(plan.get("case_id", "?"), plan)]

    cases = plan.get("cases", plan.get("results"))
    if not isinstance(cases, list):
        raise PlanInputError("顶层对象必须包含 queries，或包含 cases/results 数组")
    return [(f"#{index}", case) for index, case in enumerate(cases)]


def validate_plan(plan):
    violations = []
    query_count = 0
    for fallback_id, case in _extract_cases(plan):
        if not isinstance(case, dict):
            violations.append(
                _violation(fallback_id, "?", "(未知)", None, "case 必须是 JSON 对象")
            )
            continue
        case_id = case.get("case_id", fallback_id)
        queries = case.get("queries")
        if isinstance(queries, list):
            query_count += len(queries)
        violations.extend(validate_queries(queries, case_id))
    return violations, query_count


def validate_plan_file(path):
    try:
        plan = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise PlanInputError(f"无法读取计划文件: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PlanInputError(f"计划文件不是合法 JSON: {exc}") from exc
    return validate_plan(plan)


def _print_violations(violations, query_count):
    cases_hit = sorted({str(item["case_id"]) for item in violations})
    print(f"✗ {len(violations)} 处 query 契约违规（涉及 {len(cases_hit)} 个 case / {query_count} 条 query）：")
    for item in violations:
        field = f" field={item['field']}" if item["field"] is not None else ""
        print(
            f"  [{item['case_id']}] Q{item['query_id']} "
            f"interface={item['interface']}{field}: {item['msg']}"
        )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="校验 research-plan 的 interface×filter 合法性（默认 fail-closed）"
    )
    parser.add_argument("plan", nargs="?", help="research-plan.json 路径")
    parser.add_argument("--query", help="单条 query JSON")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="兼容旧调用；当前版本默认即严格拒绝未知接口",
    )
    args = parser.parse_args(argv)

    try:
        if args.query:
            try:
                query = json.loads(args.query)
            except json.JSONDecodeError as exc:
                raise PlanInputError(f"--query 不是合法 JSON: {exc}") from exc
            violations = validate_queries([query], "(单条)")
            query_count = 1
        elif args.plan:
            violations, query_count = validate_plan_file(args.plan)
        else:
            parser.error("需要 plan 路径或 --query")
    except PlanInputError as exc:
        print(f"✗ 输入错误：{exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"✗ 校验器初始化/执行失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if violations:
        _print_violations(violations, query_count)
        print("\n参考: references/07-research-middleware.md §9.1。")
        return 1

    print(
        f"✓ 合法：{query_count} 条 query 的 interface×filter 全部匹配 "
        f"yd_search.build_parser（{len(VALID_FILTERS)} 个可规划 API 接口）。"
    )
    return 0
