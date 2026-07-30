#!/usr/bin/env python3
"""Regression tests for patent-analysis static validation rules."""

from __future__ import annotations

import unittest

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
        pending = prefix + "<td>v2.1.1</td><td>待发布</td>" + suffix
        matching = prefix + '<td>v2.1.1</td><td><a href="patent-analysis-2.1.1.zip">下载</a></td>' + suffix
        mismatched = prefix + '<td>v2.1.1</td><td><a href="patent-analysis-1.2.0.zip">下载</a></td>' + suffix
        self.assertEqual([], validate_skill.check_root_readme_release(pending))
        self.assertEqual([], validate_skill.check_root_readme_release(matching))
        self.assertTrue(validate_skill.check_root_readme_release(mismatched))


if __name__ == "__main__":
    unittest.main(verbosity=2)
