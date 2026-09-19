#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验涵摄式检索计划，以及可选的 Agent 精选来源清单。"""

import argparse
import sys

import query_filter_validator
import research_contract


def _print_errors(label, errors):
    print(f"✗ {label}存在 {len(errors)} 处合同违规：")
    for item in errors:
        print(f"  {item['path']}: {item['msg']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="校验涵摄式 research plan 与 selected sources")
    parser.add_argument("--plan", required=True, help="research-plan.json 路径")
    parser.add_argument("--selection", help="selected-sources.json 路径；正式报告前必填")
    args = parser.parse_args(argv)

    try:
        plan = research_contract.load_json_object(args.plan, "research plan")
        plan_errors = research_contract.validate_research_plan(plan)
        filter_errors, query_count = query_filter_validator.validate_plan(plan)
        selection_errors = []
        if args.selection:
            selection = research_contract.load_json_object(args.selection, "selected sources")
            selection_errors = research_contract.validate_selected_sources(selection, plan)
    except (research_contract.ContractInputError, query_filter_validator.PlanInputError) as exc:
        print(f"✗ 输入错误：{exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"✗ 校验器初始化/执行失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    failed = False
    if plan_errors:
        failed = True
        _print_errors("research plan", plan_errors)
    if filter_errors:
        failed = True
        query_filter_validator._print_violations(filter_errors, query_count)
    if selection_errors:
        failed = True
        _print_errors("selected sources", selection_errors)
    if failed:
        return 1

    suffix = "；selected sources 已与命题和查询完成交叉校验" if args.selection else ""
    print(f"✓ 合法：涵摄式 research plan（{query_count} 条 query）{suffix}。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
