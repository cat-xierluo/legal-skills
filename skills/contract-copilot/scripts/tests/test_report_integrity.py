"""报告完整性复核回归测试。

对应 legal-skill-evaluation T-401 的两例 report 完整性缺陷：
- CONTRACT-MICRO-REPORT-FIELD-COLLAPSE：最终报告字段塌缩（14 处待补占位 + 1 处空法律依据）。
- CONTRACT-MICRO-PRODUCER-SELF-SUCCESS：生产器渲染无异常即自报成功（退出码 0），
  未由独立 checker 拦截，导致回归被错误关闭。
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SKILL_ROOT = Path(__file__).resolve().parents[2]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from scripts.report.reporting import (  # noqa: E402
    MAX_MISSING_PLACEHOLDERS,
    check_report_integrity,
)

COLLAPSED_PLAN = {
    "meta": {"contract_name": "脱敏许可合同", "party_role": "中立"},
    "summary": {},
    "findings": [
        {
            "id": "R001",
            "risk_level": "P0",
            "suggestion": "专利号、权利人和权利状态均未填写，应列为签署前置条件。",
            "target_text": "许可标的：____",
            "revised_text": "许可标的：专利号及权利状态待核验",
        }
    ],
}


class ReportIntegrityTests(unittest.TestCase):
    def test_collapsed_report_is_rejected(self) -> None:
        report = "\n".join(["- 字段：未提及/待补充"] * (MAX_MISSING_PLACEHOLDERS + 1))
        result = check_report_integrity(report)
        self.assertFalse(result["passed"])
        self.assertEqual(MAX_MISSING_PLACEHOLDERS + 1, result["missing_placeholder_count"])

    def test_empty_legal_basis_is_rejected(self) -> None:
        result = check_report_integrity("- 法律依据：/\n")
        self.assertFalse(result["passed"])
        self.assertEqual(1, result["empty_legal_basis_count"])

    def test_complete_report_passes(self) -> None:
        report = "- 合同名称：测试合同\n- 法律依据：《民法典》第五百零九条\n"
        result = check_report_integrity(report)
        self.assertTrue(result["passed"])
        self.assertEqual([], result["problems"])

    def test_placeholders_within_threshold_pass(self) -> None:
        report = "\n".join(["- 字段：未提及/待补充"] * MAX_MISSING_PLACEHOLDERS)
        self.assertTrue(check_report_integrity(report)["passed"])

    def _run_cli(self, output_name: str, *extra: str) -> subprocess.CompletedProcess[str]:
        with TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            plan_path.write_text(json.dumps(COLLAPSED_PLAN, ensure_ascii=False), encoding="utf-8")
            return subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.report.reporting",
                    "--plan",
                    str(plan_path),
                    "--output",
                    str(Path(tmp) / output_name),
                    *extra,
                ],
                cwd=SKILL_ROOT,
                capture_output=True,
                text=True,
            )

    def test_producer_does_not_self_report_success(self) -> None:
        """渲染无异常不等于成功：字段塌缩时脚本必须非零退出。"""
        result = self._run_cli("out.md")
        self.assertEqual(1, result.returncode)
        self.assertIn("报告未通过完整性复核", result.stderr)

    def test_skip_flag_allows_placeholder_draft(self) -> None:
        result = self._run_cli("out.md", "--skip-integrity-check")
        self.assertEqual(0, result.returncode)


if __name__ == "__main__":
    unittest.main()
