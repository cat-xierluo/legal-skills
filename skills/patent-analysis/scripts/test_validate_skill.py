#!/usr/bin/env python3
"""Regression tests for patent-analysis static validation rules."""

from __future__ import annotations

import copy
import unittest

import check_evals
import check_legal_sources
import validate_skill


class ForbiddenPatternTests(unittest.TestCase):
    def test_historical_failures_are_blocked(self) -> None:
        cases = {
            "placeholder_case": "案号：(2020)最高法知民终 " + "X" * 3 + " 号",
            "four_month_reply": "提交答复意见应在" + "四" + "个月内完成",
            "six_month_suit": "收到无效决定后" + "六" + "个月内起诉",
            "six_month_appeal": "不服行政判决应在" + "六" + "个月内上诉",
            "unsupported_percentage": "实用新型案件中无效成功率为 " + "70" + "%",
            "missing_collaborator": "交给 proposal-generator 生成方案",
        }
        for code, text in cases.items():
            with self.subTest(code=code):
                self.assertRegex(text, validate_skill.FORBIDDEN_PATTERNS[code])

    def test_official_title_and_correct_deadlines_are_not_blocked(self) -> None:
        valid = (
            "最高人民法院《关于审理侵犯专利权纠纷案件应用法律若干问题的解释》；"
            "答复期限通常为一个月；无效决定起诉期限为三个月；"
            "行政判决上诉期限为十五日。"
        )
        for code, pattern in validate_skill.FORBIDDEN_PATTERNS.items():
            with self.subTest(code=code):
                self.assertIsNone(pattern.search(valid))

    def test_appended_conflicting_rules_are_blocked(self) -> None:
        conflicts = [
            "即使存在 C 或 B/D，仍可认定全面覆盖。",
            "B-初步支持可以计入已覆盖。",
            "缺少目标法域时仍可继续风险评级。",
        ]
        for conflict in conflicts:
            with self.subTest(conflict=conflict):
                self.assertTrue(validate_skill.forbidden_codes(conflict))


class GateTests(unittest.TestCase):
    def test_current_skill_contains_evidence_and_fto_gates(self) -> None:
        skill = (validate_skill.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        fto = (validate_skill.SKILL_DIR / "references" / "05-fto-analysis.md").read_text(encoding="utf-8")
        self.assertEqual([], validate_skill.check_required_rules(skill, fto))

    def test_missing_gate_fails_closed(self) -> None:
        errors = validate_skill.check_required_rules("", "")
        self.assertGreaterEqual(len(errors), 11)

    def test_reversed_fto_gate_fails_closed(self) -> None:
        skill = (validate_skill.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        fto = (validate_skill.SKILL_DIR / "references" / "05-fto-analysis.md").read_text(encoding="utf-8")
        mutated = fto.replace(
            "必须停止风险评级，只输出补充或核验清单",
            "可以继续风险评级，并在结论后补充核验清单",
        )
        self.assertTrue(validate_skill.check_required_rules(skill, mutated))

    def test_missing_mixed_state_priority_fails_closed(self) -> None:
        skill = (validate_skill.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        fto = (validate_skill.SKILL_DIR / "references" / "05-fto-analysis.md").read_text(encoding="utf-8")
        mutated = skill.replace("无论是否同时存在 `B/D`", "在部分情况下")
        self.assertTrue(validate_skill.check_required_rules(mutated, fto))

    def test_visualization_does_not_count_preliminary_evidence(self) -> None:
        visual = (validate_skill.SKILL_DIR / "references" / "10-visualization.md").read_text(encoding="utf-8")
        self.assertIn("`B-初步支持` | 否", visual)
        self.assertIn("是否存在 C？", visual)
        self.assertIn("证据不足：暂不能判断全面覆盖", visual)
        self.assertLess(visual.index("是否存在 C？"), visual.index("是否存在 B 或 D？"))
        self.assertNotIn("推定全部" + "特征覆盖", visual)

    def test_local_release_metadata_is_consistent(self) -> None:
        self.assertEqual([], validate_skill.check_local_release())

    def test_legal_basis_uses_article_matrix_without_urls(self) -> None:
        self.assertEqual([], validate_skill.check_legal_basis())

    def test_legal_basis_url_is_blocked(self) -> None:
        legal = (validate_skill.SKILL_DIR / "references" / "00-legal-basis.md").read_text(encoding="utf-8")
        equivalents = (
            validate_skill.SKILL_DIR / "references" / "08-doctrine-of-equivalents.md"
        ).read_text(encoding="utf-8")
        mutated = equivalents + "\n核验来源：https://example.invalid/court\n"
        self.assertTrue(validate_skill.check_legal_basis(legal, mutated))

    def test_missing_equivalence_limitation_is_blocked(self) -> None:
        legal = (validate_skill.SKILL_DIR / "references" / "00-legal-basis.md").read_text(encoding="utf-8")
        equivalents = (
            validate_skill.SKILL_DIR / "references" / "08-doctrine-of-equivalents.md"
        ).read_text(encoding="utf-8")
        mutated = equivalents.replace("《专利侵权司法解释（一）》第五条", "说明书捐献规则")
        self.assertTrue(validate_skill.check_legal_basis(legal, mutated))

    def test_missing_current_invalidation_rules_are_blocked(self) -> None:
        legal = (validate_skill.SKILL_DIR / "references" / "00-legal-basis.md").read_text(
            encoding="utf-8"
        )
        equivalents = (
            validate_skill.SKILL_DIR / "references" / "08-doctrine-of-equivalents.md"
        ).read_text(encoding="utf-8")
        invalidation = (
            validate_skill.SKILL_DIR / "references" / "09-invalidation-defense.md"
        ).read_text(encoding="utf-8")
        for index, phrase in enumerate([
            "《专利法实施细则》第七十二条",
            "《专利法实施细则》第七十三条",
            "全文替换页",
            "修改对照表",
        ]):
            marker = f"〔已移除无效规则-{index}〕"
            mutated_legal = legal.replace(phrase, marker)
            mutated_invalidation = invalidation.replace(phrase, marker)
            with self.subTest(phrase=phrase):
                self.assertTrue(
                    validate_skill.check_legal_basis(
                        mutated_legal,
                        equivalents,
                        mutated_invalidation,
                    )
                )

    def test_protection_scope_requires_articles_one_through_five_in_its_own_section(self) -> None:
        legal = (validate_skill.SKILL_DIR / "references" / "00-legal-basis.md").read_text(encoding="utf-8")
        equivalents = (
            validate_skill.SKILL_DIR / "references" / "08-doctrine-of-equivalents.md"
        ).read_text(encoding="utf-8")
        for article in ["第一条", "第二条", "第三条", "第四条", "第五条"]:
            phrase = f"《专利侵权司法解释（一）》{article}"
            mutated = legal.replace(phrase, f"〔保护范围已移除{article}〕") + f"\n{phrase}\n"
            with self.subTest(article=article):
                self.assertTrue(validate_skill.check_legal_basis(mutated, equivalents))

    def test_root_readme_download_must_match_or_be_pending(self) -> None:
        prefix = '<tr>\n<td><a href="skills/patent-analysis/"><strong>patent-analysis</strong></a></td>\n'
        suffix = "\n</tr>"
        version = validate_skill.RELEASE_VERSION
        pending = prefix + f"<td>v{version}</td><td>待发布</td>" + suffix
        matching = prefix + f'<td>v{version}</td><td><a href="patent-analysis-{version}.zip">下载</a></td>' + suffix
        mismatched = prefix + f'<td>v{version}</td><td><a href="patent-analysis-1.2.0.zip">下载</a></td>' + suffix
        self.assertEqual([], validate_skill.check_root_readme_release(pending))
        self.assertEqual([], validate_skill.check_root_readme_release(matching))
        self.assertTrue(validate_skill.check_root_readme_release(mismatched))


class LegalSourceRegisterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.register = check_legal_sources.load_register()

    def test_current_register_covers_23_updates_and_ten_scenarios(self) -> None:
        self.assertEqual(
            [],
            check_legal_sources.validate_register(
                self.register,
                expected_skill_version=validate_skill.RELEASE_VERSION,
            ),
        )
        self.assertEqual(23, len(self.register["guide_updates"]))
        self.assertEqual(10, len(self.register["scenario_impacts"]))

    def test_public_url_is_blocked(self) -> None:
        mutated = copy.deepcopy(self.register)
        mutated["official_baseline"]["title"] += " https://example.invalid/source"
        errors = check_legal_sources.validate_register(mutated)
        self.assertTrue(any("禁止 URL" in error for error in errors))

    def test_missing_scenario_is_blocked(self) -> None:
        mutated = copy.deepcopy(self.register)
        mutated["scenario_impacts"] = [
            item for item in mutated["scenario_impacts"] if item["scenario_id"] != 10
        ]
        errors = check_legal_sources.validate_register(mutated)
        self.assertTrue(any("场景1—10" in error for error in errors))

    def test_complex_issue_cannot_degrade_to_one_provision(self) -> None:
        mutated = copy.deepcopy(self.register)
        group = next(
            item for item in mutated["doctrine_groups"] if item["issue_id"] == "equivalence"
        )
        group["provisions"] = group["provisions"][:1]
        errors = check_legal_sources.validate_register(mutated)
        self.assertTrue(any("条款数" in error for error in errors))

    def test_unknown_status_and_invalid_date_are_blocked(self) -> None:
        mutated = copy.deepcopy(self.register)
        mutated["sources"][0]["status"] = "probably-current"
        mutated["guide_updates"][0]["verified_on"] = "2026-02-30"
        errors = check_legal_sources.validate_register(mutated)
        self.assertTrue(any("未知效力状态" in error for error in errors))
        self.assertTrue(any("有效 ISO 日期" in error for error in errors))

    def test_impacted_update_requires_scenario_mapping(self) -> None:
        mutated = copy.deepcopy(self.register)
        update = next(
            item for item in mutated["guide_updates"] if item["impact_status"] == "direct"
        )
        update["scenario_ids"] = []
        errors = check_legal_sources.validate_register(mutated)
        self.assertTrue(any("与影响状态不匹配" in error for error in errors))

    def test_fto_policy_fails_closed_when_baseline_input_is_removed(self) -> None:
        mutated = copy.deepcopy(self.register)
        mutated["fto_update_policy"]["required_inputs"].remove("法律状态基线")
        errors = check_legal_sources.validate_register(mutated)
        self.assertTrue(any("五项FTO输入" in error for error in errors))

    def test_unknown_field_is_blocked(self) -> None:
        mutated = copy.deepcopy(self.register)
        mutated["auto_crawl_endpoint"] = "disabled"
        errors = check_legal_sources.validate_register(mutated)
        self.assertTrue(any("root: 字段不匹配" in error for error in errors))


class EvalContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evals_data, cls.assertions_data = check_evals.load_contract()

    def test_current_ten_scenario_contract_passes(self) -> None:
        self.assertEqual(
            [],
            check_evals.validate_metadata(self.evals_data, self.assertions_data),
        )

    def test_missing_scenario_is_blocked(self) -> None:
        mutated = copy.deepcopy(self.evals_data)
        mutated["evals"] = [case for case in mutated["evals"] if case["id"] != 10]
        errors = check_evals.validate_metadata(mutated, self.assertions_data)
        self.assertTrue(any("场景 1—10" in error for error in errors))

    def test_weak_hard_assertion_policy_is_blocked(self) -> None:
        mutated = copy.deepcopy(self.assertions_data)
        first_case = mutated["cases"][0]
        first_case["assertions"] = [
            assertion
            for assertion in first_case["assertions"]
            if assertion["type"] not in check_evals.NEGATIVE_ASSERTIONS
        ]
        errors = check_evals.validate_metadata(self.evals_data, mutated)
        self.assertTrue(any("hard 禁止性断言" in error for error in errors))

    def test_unknown_assertion_type_is_blocked(self) -> None:
        mutated = copy.deepcopy(self.assertions_data)
        mutated["cases"][0]["assertions"][0]["type"] = "keyword-score"
        errors = check_evals.validate_metadata(self.evals_data, mutated)
        self.assertTrue(any("不支持的 type" in error for error in errors))

    def test_missing_scenario_specific_gate_is_blocked(self) -> None:
        mutated = copy.deepcopy(self.assertions_data)
        case_three = next(case for case in mutated["cases"] if case["eval_id"] == 3)
        case_three["assertions"] = [
            assertion
            for assertion in case_three["assertions"]
            if assertion["id"] != "multi-provision-basis"
        ]
        errors = check_evals.validate_metadata(self.evals_data, mutated)
        self.assertTrue(any("场景关键断言" in error for error in errors))

    @staticmethod
    def _positive_fixture(case: dict) -> str:
        fragments: list[str] = []
        for assertion in case["assertions"]:
            assertion_type = assertion["type"]
            if assertion_type == "contains_all":
                fragments.extend(assertion["terms"])
            elif assertion_type == "contains_any":
                fragments.append(assertion["terms"][0])
            elif assertion_type == "contains_any_per_group":
                fragments.extend(group["terms"][0] for group in assertion["groups"])
        return "。".join(fragments) + "。"

    def test_affirmative_pollution_fails_but_explicit_refusal_passes(self) -> None:
        bad_conclusions = {
            1: "可以直接起诉",
            2: "P-A 范围更大",
            3: "字面侵权成立",
            4: "无效成功率为 70%",
            5: "低风险，可以自由实施",
            6: "删除一个特征即可规避",
            7: "估值为 500 万元",
            8: "等同侵权成立",
            9: "答复期固定为两个月",
            10: "侵权风险高",
        }
        for case in self.assertions_data["cases"]:
            eval_id = case["eval_id"]
            fixture = self._positive_fixture(case)
            with self.subTest(eval_id=eval_id, variant="baseline"):
                self.assertTrue(check_evals.evaluate_case(fixture, case).ok)
            with self.subTest(eval_id=eval_id, variant="polluted"):
                self.assertFalse(
                    check_evals.evaluate_case(
                        fixture + f"综合判断：{bad_conclusions[eval_id]}。",
                        case,
                    ).ok
                )
            with self.subTest(eval_id=eval_id, variant="negated"):
                self.assertTrue(
                    check_evals.evaluate_case(
                        fixture + f"不得认定{bad_conclusions[eval_id]}。",
                        case,
                    ).ok
                )

    def test_product_url_is_allowed_but_legal_source_url_is_blocked(self) -> None:
        case_three = next(case for case in self.assertions_data["cases"] if case["eval_id"] == 3)
        forbidden = next(
            assertion
            for assertion in case_three["assertions"]
            if assertion["id"] == "forbidden-majority-coverage"
        )
        self.assertTrue(
            check_evals.evaluate_assertion(
                "产品证据：https://example.com/product-photo",
                forbidden,
            ).ok
        )
        self.assertFalse(
            check_evals.evaluate_assertion(
                "法律依据：《专利法》第六十四条 https://example.com/legal-source",
                forbidden,
            ).ok
        )
        self.assertFalse(
            check_evals.evaluate_assertion(
                "这是用于说明适用边界和当前核验状态的一段较长前言，法律依据：《专利法》第六十四条\n\n"
                "https://example.com/legal-source",
                forbidden,
            ).ok
        )

    def test_double_negation_is_affirmative_and_long_refusal_is_safe(self) -> None:
        samples = {
            1: ("不得不认定专利有效", "不得在材料和法律状态均未核验且缺少现行文本的情况下认定专利有效"),
            5: ("不能不认为属于低风险", "不能在目标法域、产品版本和实施行为均缺失的情况下作出低风险结论"),
            8: ("不得不认定等同侵权成立", "不得在手段、效果和审查档案原文均未取得且无法逐特征核验的情况下认定等同侵权成立"),
        }
        for eval_id, (double_negative, long_refusal) in samples.items():
            case = next(case for case in self.assertions_data["cases"] if case["eval_id"] == eval_id)
            assertion = next(
                item for item in case["assertions"] if item["type"] == "not_affirm_any"
            )
            with self.subTest(eval_id=eval_id, variant="double-negative"):
                self.assertFalse(check_evals.evaluate_assertion(double_negative, assertion).ok)
            with self.subTest(eval_id=eval_id, variant="long-refusal"):
                self.assertTrue(check_evals.evaluate_assertion(long_refusal, assertion).ok)

    def test_unverified_fixed_deadline_variants_are_blocked(self) -> None:
        case_nine = next(case for case in self.assertions_data["cases"] if case["eval_id"] == 9)
        assertion = next(
            item
            for item in case_nine["assertions"]
            if item["id"] == "forbidden-old-procedure-rules"
        )
        invalid = [
            "答复期限是两个月",
            "应当在两个月内答复",
            "答复截止日：2026-08-31",
            "转送通知的答复期为两个月",
            "截止日期定在2026年8月31日",
        ]
        for text in invalid:
            with self.subTest(text=text, variant="affirmative"):
                self.assertFalse(check_evals.evaluate_assertion(text, assertion).ok)
            with self.subTest(text=text, variant="refusal"):
                self.assertTrue(
                    check_evals.evaluate_assertion(
                        "不得在送达事实尚未核验、通知原件尚未取得且无法复核的情况下写入" + text,
                        assertion,
                    ).ok
                )

    def test_full_legal_titles_satisfy_source_alias_groups(self) -> None:
        answers = {
            3: (
                "《中华人民共和国专利法》第六十四条；"
                "《最高人民法院关于审理侵犯专利权纠纷案件应用法律若干问题的解释》第七条；"
                "《最高人民法院关于审理专利纠纷案件适用法律问题的若干规定》第十三条。"
            ),
            6: (
                "《中华人民共和国专利法》第六十四条；"
                "《最高人民法院关于审理侵犯专利权纠纷案件应用法律若干问题的解释》第七条。"
            ),
        }
        assertion_ids = {3: "multi-provision-basis", 6: "design-around-legal-basis"}
        for eval_id, answer in answers.items():
            case = next(case for case in self.assertions_data["cases"] if case["eval_id"] == eval_id)
            assertion = next(
                item for item in case["assertions"] if item["id"] == assertion_ids[eval_id]
            )
            with self.subTest(eval_id=eval_id):
                self.assertTrue(check_evals.evaluate_assertion(answer, assertion).ok)


if __name__ == "__main__":
    unittest.main(verbosity=2)
