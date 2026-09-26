#!/usr/bin/env python3
"""无网络验证原生参数、focused 报告及真实 wrapper 归档透传。"""

import contextlib
import copy
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import query_filter_validator
import research_contract
import yd_search


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def test_native_payloads():
    calls = []

    def post(endpoint, body, use_cache=True):
        calls.append((endpoint, body))
        return {"data": [], "extra": {"fatiao": [], "wenshu": []}}, False, None

    with patch.dict(os.environ, {"YD_STRATEGY": "aggressive"}), \
         patch.object(yd_search, "load_strategy", side_effect=AssertionError("不应读取旧策略")), \
         patch.object(yd_search, "api_post", side_effect=post), \
         patch.object(yd_search, "_archive_write_report", return_value=(None, None)), \
         contextlib.redirect_stdout(io.StringIO()):
        parser = yd_search.build_parser()
        for command in ("search", "case-semantic", "keyword", "case"):
            args = parser.parse_args(["--no-report", command, "测试争点"])
            args.func(args)
        for _, body in calls:
            require(not {"rewrite_flag", "return_num", "top_k"} & body.keys(), "隐式覆盖原生参数")
        require(calls[0][1] == {"query": "测试争点"}, "法条语义默认 payload 漂移")
        require(calls[1][1] == {"query": "测试争点"}, "案例语义默认 payload 漂移")

        for command in ("search", "case-semantic"):
            for flag, expected in (("--rewrite-flag", True), ("--no-rewrite", False)):
                args = parser.parse_args(["--no-report", command, "测试争点", flag, "--return-num", "5"])
                args.func(args)
                require(calls[-1][1] == {"query": "测试争点", "rewrite_flag": expected, "return_num": 5},
                        "显式语义参数未尊重")
        args = parser.parse_args(["--no-report", "case", "测试争点", "--top-k", "7"])
        args.func(args)
        require(calls[-1][1]["top_k"] == 7, "显式 top_k 丢失")
        for command in (["search", "x", "--return-num", "0"],
                        ["case", "x", "--top-k", "-1"],
                        ["search", "x", "--rewrite-flag", "--no-rewrite"]):
            with contextlib.redirect_stderr(io.StringIO()):
                try:
                    parser.parse_args(command)
                except SystemExit as exc:
                    require(exc.code == 2, "参数错误退出码应为2")
                else:
                    raise AssertionError("非法参数未阻断")


def test_nested_archive_and_wrapper(root):
    nested = root / "missing" / "parent" / "archive"
    with patch.object(yd_search, "ARCHIVE_DIR", nested), patch.object(yd_search, "NO_ARCHIVE", False):
        path = yd_search._archive_save("/open/law_vector_search", {"query": "fixture"}, {"data": []})
        require(Path(path).is_file(), "多层目录归档失败")
        cached, _ = yd_search._archive_lookup("/open/law_vector_search", {"query": "fixture"})
        require(cached == {"data": []}, "新归档不能缓存命中")

    # 用只打印指定变量的临时解释器替身走真实 shell wrapper，不请求网络。
    fake_python = root / "python-probe"
    fake_python.write_text(f"#!{sys.executable}\nimport os\nprint(os.environ.get('YD_ARCHIVE_DIR', 'MISSING'))\n", "utf-8")
    fake_python.chmod(0o700)
    env = dict(os.environ, YD_PYTHON=str(fake_python), YD_ARCHIVE_DIR=str(nested))
    result = subprocess.run([str(Path(__file__).with_name("yd-run")), "--help"],
                            env=env, text=True, capture_output=True, check=False)
    require(result.returncode == 0 and result.stdout.strip() == str(nested), "wrapper 未透传 YD_ARCHIVE_DIR")


def test_focused_delivery(root):
    spec = importlib.util.spec_from_file_location("delivery_fixtures", Path(__file__).with_name("verify-research-delivery-contracts.py"))
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    original = fixture._valid_plan()
    plan = {
        "schema_version": "1.1", "mode": "focused", "case_id": original["case_id"],
        "research_brief": {"research_goal": "测试单争点", "dispute_focus": ["履行条件"]},
        "propositions": [{"id": "P-01", "statement": "请求履行的条件", "importance": "decisive"}],
        "queries": [{"id": "Q-01", "proposition_id": "P-01", "interface": "search",
                     "query_expression": "履行条件", "filters": {}}],
    }
    selection = fixture._valid_selection()
    selection["selected_sources"] = selection["selected_sources"][:1]
    require(not research_contract.validate_research_plan(plan), "focused 不应要求矩阵或反向命题")
    require(not query_filter_validator.validate_plan(plan)[0], "focused 查询字段误报")
    require(not research_contract.validate_selected_sources(selection, plan), "focused 精选误报")

    for key, value in (("propositions", []), ("queries", []), ("mode", "unknown"), ("case_id", "")):
        broken = copy.deepcopy(plan)
        broken[key] = value
        require(research_contract.validate_research_plan(broken), f"focused 逃逸未阻断: {key}")
    broken = copy.deepcopy(plan)
    broken["queries"][0]["proposition_id"] = "UNKNOWN"
    require(research_contract.validate_research_plan(broken), "focused 未知命题未阻断")
    broken = copy.deepcopy(plan)
    broken["queries"][0]["filters"] = {"--wenshu-type": "民事案件"}
    require(query_filter_validator.validate_plan(broken)[0], "focused 错字段未阻断")

    plan_path, selection_path = root / "plan.json", root / "selection.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), "utf-8")
    selection_path.write_text(json.dumps(selection, ensure_ascii=False), "utf-8")
    output = root / "focused-report.md"
    args = SimpleNamespace(research_plan=str(plan_path), selection=str(selection_path), include=None,
                           title="离线样本", project="focused", case="测试事实", strategy="一次查询",
                           analysis="测试分析", purpose=None, conclusion="附条件测试结论", risks="测试边界",
                           next_actions="无", output=str(output))
    with patch.object(yd_search, "ARCHIVE_DIR", root / "custom" / "archive"), \
         contextlib.redirect_stdout(io.StringIO()):
        yd_search.cmd_consolidate(args)
        report = output.read_text("utf-8")
        require("### 3.1 规范性法律依据" in report, "focused 来源分组缺失")
        require("涵摄矩阵" not in report and "None" not in report, "focused 空矩阵或占位泄漏")
        require("烟叶购销合同" not in report and "已排除 1 条候选" in report, "噪声污染或排除统计丢失")
        require((root / "custom/archive/focused/research-plan.json").is_file(), "报告忽略自定义归档路径")
        require("不等于实际调用数" in report, "底稿数被误写成调用数")

        for mutation in ({"relevance_label": "LOW"}, {"verification_status": "pending"},
                         {"proposition_ids": ["UNKNOWN"]}):
            bad = copy.deepcopy(selection)
            bad["selected_sources"][0].update(mutation)
            selection_path.write_text(json.dumps(bad), "utf-8")
            args.project = "blocked"
            args.output = str(root / "must-not-exist.md")
            with contextlib.redirect_stderr(io.StringIO()):
                try:
                    yd_search.cmd_consolidate(args)
                except SystemExit as exc:
                    require(exc.code == 1, "违规报告应退出1")
                else:
                    raise AssertionError("focused 绕过精选门禁")
            require(not Path(args.output).exists(), "阻断后仍写报告")
            require(not (root / "custom/archive/blocked").exists(), "阻断后仍写项目包")


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix="yd-lightweight-") as tmp:
        root = Path(tmp)
        test_native_payloads()
        checks.append("native-defaults-explicit-options-invalid-inputs")
        test_nested_archive_and_wrapper(root)
        checks.append("nested-archive-cache-and-real-wrapper-env")
        test_focused_delivery(root)
        checks.append("focused-schema-real-report-and-fail-closed")
    print(json.dumps({"status": "PASS", "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main()
