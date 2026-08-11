#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""无网络验证 CLI→payload 与检索计划门禁的已知回归。"""

import contextlib
import io
import json
import sys

import query_filter_validator as validator
import yd_search


def _require(condition, message):
    if not condition:
        raise AssertionError(message)


def _capture_case_payloads():
    calls = []

    def fake_post(endpoint, body, use_cache=True):
        calls.append((endpoint, body))
        if endpoint == "/open/case_vector_search":
            return {"extra": {"wenshu": []}}, False, None
        return {"data": {"lst": []}}, False, None

    original_post = yd_search.api_post
    original_report = yd_search._archive_write_report
    original_footer = yd_search._print_footer
    yd_search.api_post = fake_post
    yd_search._archive_write_report = lambda *args, **kwargs: (None, None)
    yd_search._print_footer = lambda *args, **kwargs: None
    try:
        parser = yd_search.build_parser()
        commands = [
            [
                "--no-report",
                "--no-cwd-report",
                "case",
                "商业秘密",
                "--jarq-start",
                "2025-01-01",
                "--jarq-end",
                "2025-12-31",
            ],
            [
                "--no-report",
                "--no-cwd-report",
                "case-semantic",
                "员工带走客户名单",
                "--jarq-start",
                "2025-01-01",
                "--jarq-end",
                "2025-12-31",
            ],
            [
                "--no-report",
                "--no-cwd-report",
                "case",
                "商业秘密",
                "--authority-only",
                "--jarq-start",
                "2025-01-01",
                "--jarq-end",
                "2025-12-31",
            ],
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            for command in commands:
                args = parser.parse_args(command)
                args.func(args)
    finally:
        yd_search.api_post = original_post
        yd_search._archive_write_report = original_report
        yd_search._print_footer = original_footer
    return calls


def main():
    checks = []
    try:
        calls = _capture_case_payloads()
        _require(len(calls) == 3, "应捕获三个案例检索请求")
        keyword_endpoint, keyword_body = calls[0]
        semantic_endpoint, semantic_body = calls[1]
        authority_endpoint, authority_body = calls[2]
        _require(keyword_endpoint == "/open/rh_ptal_search", "案例关键词接口路由错误")
        _require(semantic_endpoint == "/open/case_vector_search", "案例语义接口路由错误")
        _require(authority_endpoint == "/open/rh_qwal_search", "权威案例关键词接口路由错误")
        _require(keyword_body.get("ja_start") == "2025-01-01", "关键词接口缺 ja_start")
        _require(keyword_body.get("ja_end") == "2025-12-31", "关键词接口缺 ja_end")
        _require("jarq_start" not in keyword_body and "jarq_end" not in keyword_body, "关键词接口泄漏 CLI 日期字段")
        semantic_filter = semantic_body.get("wenshu_filter", {})
        _require(semantic_filter.get("ja_start") == "2025-01-01", "语义接口缺 ja_start")
        _require(semantic_filter.get("ja_end") == "2025-12-31", "语义接口缺 ja_end")
        _require("jarq_start" not in semantic_filter and "jarq_end" not in semantic_filter, "语义接口泄漏 CLI 日期字段")
        _require(authority_body.get("ja_start") == "2025-01-01", "权威案例接口缺 ja_start")
        _require(authority_body.get("ja_end") == "2025-12-31", "权威案例接口缺 ja_end")
        _require("jarq_start" not in authority_body and "jarq_end" not in authority_body, "权威案例接口泄漏 CLI 日期字段")
        checks.append("case-date-payload-mapping")

        _require(len(validator.VALID_FILTERS) == 15, "可规划 API 接口覆盖数不是 15")
        enterprise = {
            "interface": "enterprise-list",
            "filters": {"--type": "writ-list", "--uscc": "test-placeholder"},
        }
        _require(not validator.validate_queries([enterprise], "enterprise"), "企业查询字段未被门禁覆盖")
        checks.append("planned-api-interface-coverage")

        valid = {
            "interface": "case-semantic",
            "filters": {"--wenshu-type": "民事案件", "--jarq-start": "2025-01-01"},
        }
        _require(not validator.validate_queries([valid], "valid"), "合法筛选条件被误报")
        checks.append("valid-query")

        wrong_owner = {"interface": "case", "filters": {"--wenshu-type": "民事案件"}}
        _require(validator.validate_queries([wrong_owner], "wrong-owner"), "错误字段归属未被阻断")
        checks.append("wrong-filter-owner")

        unknown = {"interface": "future-interface", "filters": {}}
        _require(validator.validate_queries([unknown], "unknown"), "未知接口未 fail-closed")
        checks.append("unknown-interface")

        wrong_type = {"interface": "case", "filters": "--ay 商业秘密纠纷"}
        _require(validator.validate_queries([wrong_type], "wrong-type"), "错误 filters 类型未被阻断")
        checks.append("invalid-filter-type")
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc), "checks": checks}, ensure_ascii=False))
        return 1

    print(json.dumps({"status": "PASS", "checks": checks}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
