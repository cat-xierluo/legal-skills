#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""无网络验证涵摄式检索合同、精选来源门禁和正式报告隔离。"""

import contextlib
import copy
import io
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import query_filter_validator
import research_contract
import yd_search


def _require(condition, message):
    if not condition:
        raise AssertionError(message)


def _valid_plan():
    return {
        "schema_version": "1.0",
        "case_id": "fixture-contract-performance",
        "research_brief": {
            "research_goal": "判断一项非金钱合同义务能否继续履行",
            "party_stance": {"role": "请求履行一方", "claim_or_defense": "请求继续履行"},
            "procedure_stage": "诉前研究",
            "dispute_focus": ["继续履行是否存在法律障碍"],
            "decisive_facts": ["合同已经成立", "相对方尚未完成约定义务"],
            "must_exclude_neighbor_types": ["仅涉及金钱债务且不存在履行障碍的案件"],
        },
        "issues": [
            {
                "id": "I-01",
                "question": "非金钱义务是否可以继续履行",
                "claim_or_defense_basis": "合同履行请求",
                "importance": "decisive",
                "major_premise": {
                    "candidate_rule": "有效合同原则上应履行，但存在法定履行障碍时除外",
                    "applicability": "适用于非金钱义务继续履行请求",
                    "elements": ["合同有效", "义务到期", "具有履行可能性", "不存在法定除外"],
                    "exceptions": ["法律上或事实上不能履行", "履行费用过高"],
                    "legal_consequence": "满足要件时支持履行；命中例外时转向替代责任",
                },
                "element_matrix": [
                    {
                        "id": "E-01",
                        "element": "不存在法定履行障碍",
                        "facts": ["相对方主张标的状态发生变化"],
                        "fact_status": "disputed",
                        "proof_status": "weak",
                        "provisional_subsumption": "uncertain",
                        "opposing_path": "状态变化可能构成不能履行或费用过高",
                        "research_gap": {
                            "id": "G-01",
                            "question": "何种状态变化构成继续履行的法定障碍",
                            "resolution_path": "legal_research",
                            "required_source_types": ["现行法律", "司法解释", "高度对位案例"],
                        },
                    },
                    {
                        "id": "E-02",
                        "element": "标的当前客观状态",
                        "facts": [],
                        "fact_status": "missing",
                        "proof_status": "none",
                        "provisional_subsumption": "uncertain",
                        "opposing_path": "如已无法恢复原状，可能改变责任路径",
                        "research_gap": {
                            "id": "G-02",
                            "question": "标的当前是否仍可履行",
                            "resolution_path": "fact_supplement",
                            "required_source_types": [],
                        },
                    },
                ],
                "provisional_conclusion": "现阶段只能形成附条件结论",
            }
        ],
        "propositions": [
            {
                "id": "P-01",
                "issue_id": "I-01",
                "element_id": "E-01",
                "research_gap_id": "G-01",
                "statement": "未命中法定履行障碍时可以请求继续履行",
                "direction": "support",
                "type": "normative",
                "importance": "decisive",
            },
            {
                "id": "P-02",
                "issue_id": "I-01",
                "element_id": "E-01",
                "research_gap_id": "G-01",
                "statement": "命中不能履行等例外时不支持继续履行",
                "direction": "oppose",
                "type": "reverse",
                "importance": "decisive",
            },
        ],
        "queries": [
            {
                "id": "Q-01",
                "proposition_id": "P-01",
                "research_gap_id": "G-01",
                "interface": "search",
                "routing_rationale": "先发现规范依据",
                "query_field": "自然语言法律问题",
                "query_expression": "非金钱债务继续履行的条件和例外",
                "filters": {"--sxx": "现行有效"},
                "allow_rewrite": True,
                "expected_hit": "现行法律与司法解释",
                "exclusion_criteria": ["金钱债务履行"],
                "fallback_path": "已知规范名称后切 detail 核验",
            },
            {
                "id": "Q-02",
                "proposition_id": "P-02",
                "research_gap_id": "G-01",
                "interface": "case-semantic",
                "routing_rationale": "检索履行障碍事实结构",
                "query_field": "案件事实结构",
                "query_expression": "合同标的状态变化，被请求继续履行，法院判断是否构成履行障碍",
                "filters": {"--wenshu-type": "民事案件"},
                "allow_rewrite": True,
                "expected_hit": "反向裁判规则",
                "exclusion_criteria": ["仅有付款迟延", "未主张继续履行"],
                "fallback_path": "提取裁判用语后切 case 结构化复检",
            },
        ],
    }


def _valid_selection():
    return {
        "schema_version": "1.0",
        "case_id": "fixture-contract-performance",
        "selected_sources": [
            {
                "source_id": "S-01",
                "source_type": "law",
                "title": "现行合同履行规范（测试来源）",
                "citation": "测试法源甲·履行条款",
                "proposition_ids": ["P-01"],
                "relevance_label": "HIGH",
                "priority": "core",
                "stance": "support",
                "rule_or_holding": "满足法定条件时可请求继续履行。",
                "applicability": "直接规范本测试争点中的非金钱义务履行请求。",
                "verification_status": "verified",
                "verification_note": "离线测试夹具；验证字段与报告隔离，不验证实体法内容。",
                "validity_status": "current",
                "trace": {
                    "query_ids": ["Q-01"],
                    "source_url": "https://example.invalid/source-a",
                    "archive_ref": "archive/fixture/raw-a.json",
                },
            },
            {
                "source_id": "S-02",
                "source_type": "case",
                "title": "履行障碍反向案例（测试来源）",
                "citation": "（测试）示例案号二",
                "proposition_ids": ["P-02"],
                "relevance_label": "MEDIUM",
                "priority": "supplementary",
                "stance": "oppose",
                "rule_or_holding": "标的客观状态构成法定障碍时不支持继续履行。",
                "applicability": "用于检验相对方提出的履行不能抗辩，不作为规范性法律依据。",
                "verification_status": "verified",
                "verification_note": "离线测试夹具；验证案例与法律依据分组。",
                "validity_status": "not_applicable",
                "trace": {
                    "query_ids": ["Q-02"],
                    "source_url": "",
                    "archive_ref": "archive/fixture/raw-b.json",
                },
            },
        ],
        "unresolved_propositions": [],
        "excluded_candidates": [
            {
                "candidate_id": "R-99",
                "title": "烟叶购销合同暂行办法（测试噪声）",
                "relevance_label": "MISMATCH",
                "reason": "客体、行业和请求权基础均与本争点无关",
                "query_id": "Q-01",
            }
        ],
    }


def _expect_selection_failure(plan, mutator, label):
    selection = _valid_selection()
    mutator(selection)
    _require(research_contract.validate_selected_sources(selection, plan), f"{label} 未被阻断")


def _verify_report_isolation(plan, selection):
    original_root = yd_search.SKILL_ROOT
    original_archive = yd_search.ARCHIVE_DIR
    original_cwd = os.environ.get("YD_USER_CWD")
    try:
        with tempfile.TemporaryDirectory(prefix="yd-delivery-contract-") as tmp:
            root = Path(tmp) / "skill"
            cwd = Path(tmp) / "work"
            archive = root / "archive"
            archive.mkdir(parents=True)
            cwd.mkdir(parents=True)
            yd_search.SKILL_ROOT = root
            yd_search.ARCHIVE_DIR = archive
            os.environ["YD_USER_CWD"] = str(cwd)

            plan_path = cwd / "research-plan.json"
            selection_path = cwd / "selected-sources.json"
            plan_path.write_text(json.dumps(plan, ensure_ascii=False), "utf-8")
            selection_path.write_text(json.dumps(selection, ensure_ascii=False), "utf-8")

            raw_name = "20260830_120000_宽泛检索.md"
            raw_md = cwd / raw_name
            raw_md.write_text(
                "# 原始检索\n\n## 检索结果\n\n"
                "### 烟叶购销合同暂行办法（测试噪声）\n\n"
                "该内容故意放入原始召回，用于验证不会进入正式报告正文。\n\n"
                "## 引用来源\n\n- 测试\n\n积分消耗：10 积分\n",
                "utf-8",
            )
            raw_json = archive / raw_name.replace(".md", ".json")
            raw_json.write_text(
                json.dumps(
                    {
                        "endpoint": "/open/law_vector_search",
                        "timestamp": "2026-08-30T12:00:00",
                        "response": {"noise": "烟叶购销合同暂行办法（测试噪声）"},
                    },
                    ensure_ascii=False,
                ),
                "utf-8",
            )
            output = cwd / "formal-report.md"
            args = SimpleNamespace(
                research_plan=str(plan_path),
                selection=str(selection_path),
                include="宽泛检索",
                title="精选交付门禁离线测试",
                project="fixture-project",
                case="测试案情。",
                strategy="以涵摄缺口生成查询，并由 Agent 逐条复核。",
                analysis="现阶段结论取决于履行障碍事实是否成立。",
                purpose=None,
                conclusion="仅在未命中法定履行障碍时，继续履行请求才有规范基础。",
                risks="标的当前状态尚待补充。",
                next_actions="补充标的状态证据。",
                output=str(output),
            )

            blocked_selection = copy.deepcopy(selection)
            blocked_selection["selected_sources"][0]["relevance_label"] = "LOW"
            blocked_selection_path = cwd / "blocked-selected-sources.json"
            blocked_selection_path.write_text(json.dumps(blocked_selection, ensure_ascii=False), "utf-8")
            blocked_args = copy.copy(args)
            blocked_args.selection = str(blocked_selection_path)
            blocked_args.include = None
            blocked_args.project = "blocked-project"
            blocked_args.output = str(cwd / "must-not-exist.md")
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    yd_search.cmd_consolidate(blocked_args)
            except SystemExit as exc:
                _require(exc.code == 1, "不合格精选清单未以合同违规码 1 阻断")
            else:
                raise AssertionError("不合格精选清单未被 consolidate 阻断")
            _require(not Path(blocked_args.output).exists(), "失败关闭后仍生成正式报告")
            _require(not (archive / "blocked-project").exists(), "失败关闭后仍创建项目包")

            with contextlib.redirect_stdout(io.StringIO()):
                yd_search.cmd_consolidate(args)
            report = output.read_text("utf-8")
            _require("测试法源甲·履行条款" in report, "精选法源未进入正式报告")
            _require("（测试）示例案号二" in report, "精选案例未进入正式报告")
            _require("该内容故意放入原始召回" not in report, "原始召回正文泄漏到正式报告")
            _require("烟叶购销合同暂行办法（测试噪声）" not in report, "已排除候选名称仍污染正式报告")
            _require("已排除 1 条候选" in report, "排除统计未保留审计线索")
            _require("### 6.1 规范性法律依据" in report, "法律依据分组缺失")
            _require("### 6.2 精选司法案例" in report, "案例分组缺失")
            _require(report.index("### 6.1 规范性法律依据") < report.index("### 6.2 精选司法案例"), "法源位阶排序错误")
    finally:
        yd_search.SKILL_ROOT = original_root
        yd_search.ARCHIVE_DIR = original_archive
        if original_cwd is None:
            os.environ.pop("YD_USER_CWD", None)
        else:
            os.environ["YD_USER_CWD"] = original_cwd


def main():
    checks = []
    try:
        plan = _valid_plan()
        selection = _valid_selection()
        _require(not research_contract.validate_research_plan(plan), "合法 research plan 被误报")
        filter_errors, _ = query_filter_validator.validate_plan(plan)
        _require(not filter_errors, "合法 query filter 被误报")
        _require(not research_contract.validate_selected_sources(selection, plan), "合法精选清单被误报")
        checks.append("valid-contract")

        _expect_selection_failure(plan, lambda data: data.update(selected_sources=[]), "空精选清单")
        _expect_selection_failure(plan, lambda data: data["selected_sources"][0].update(relevance_label="LOW"), "LOW 来源")
        _expect_selection_failure(
            plan,
            lambda data: data["selected_sources"][0].update(relevance_label="MEDIUM"),
            "MEDIUM 核心依据",
        )
        _expect_selection_failure(plan, lambda data: data["selected_sources"][0].update(verification_status="pending"), "未核验来源")
        _expect_selection_failure(plan, lambda data: data["selected_sources"][0].update(proposition_ids=["P-UNKNOWN"]), "未知命题")
        _expect_selection_failure(
            plan,
            lambda data: data["selected_sources"].append(copy.deepcopy(data["selected_sources"][0])),
            "重复来源",
        )
        _expect_selection_failure(
            plan,
            lambda data: data.update(
                selected_sources=[
                    {
                        **copy.deepcopy(data["selected_sources"][0]),
                        "source_id": f"S-{index:02d}",
                        "citation": f"测试引用 {index}",
                    }
                    for index in range(1, research_contract.MAX_SELECTED_SOURCES + 2)
                ]
            ),
            "正文来源超过阅读预算",
        )
        checks.append("selection-fault-injection")

        bad_plan = copy.deepcopy(plan)
        bad_plan["queries"][0]["research_gap_id"] = "G-02"
        _require(research_contract.validate_research_plan(bad_plan), "事实补充缺口被错误转成查询而未阻断")
        checks.append("gap-routing-fault-injection")

        _verify_report_isolation(plan, selection)
        checks.append("consolidate-fail-closed")
        checks.append("raw-recall-report-isolation")
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc), "checks": checks}, ensure_ascii=False))
        return 1

    print(json.dumps({"status": "PASS", "checks": checks}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
