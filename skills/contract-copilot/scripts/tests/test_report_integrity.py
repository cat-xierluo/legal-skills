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
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

SKILL_ROOT = Path(__file__).resolve().parents[2]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from scripts.report.integrity import (  # noqa: E402
    MAX_MISSING_PLACEHOLDERS,
    check_delivery_integrity,
    check_plan_integrity,
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
        report = "## 四、详细审查意见\n\n### 1. 测试风险\n\n- 风险概述：测试\n\n## 五、声明\n"
        result = check_report_integrity(report)
        self.assertFalse(result["passed"])
        self.assertEqual(1, result["empty_legal_basis_count"])

    def test_plan_finding_without_legal_basis_is_rejected(self) -> None:
        result = check_plan_integrity(COLLAPSED_PLAN)
        self.assertFalse(result["passed"])
        self.assertEqual(["R001"], result["missing_legal_basis_ids"])

    def test_legal_basis_placeholder_is_rejected(self) -> None:
        plan = json.loads(json.dumps(COLLAPSED_PLAN))
        plan["findings"][0]["legal_basis"] = "待补充"
        report = (
            "## 四、详细审查意见\n\n### 1. 测试风险\n\n"
            "- 法律依据：待补充\n\n## 五、声明\n"
        )
        result = check_delivery_integrity(plan, report)
        self.assertFalse(result["passed"])
        self.assertEqual(["R001"], result["plan"]["missing_legal_basis_ids"])
        self.assertEqual(1, result["report"]["empty_legal_basis_count"])

    def test_delivery_requires_plan_and_rendered_report_to_agree(self) -> None:
        report = (
            "## 四、详细审查意见\n\n### 1. 测试风险\n\n"
            "- 法律依据：《民法典》第五百零九条\n\n## 五、声明\n"
        )
        result = check_delivery_integrity(COLLAPSED_PLAN, report)
        self.assertFalse(result["passed"])
        self.assertIn("R001", result["plan"]["missing_legal_basis_ids"])

    def test_complete_report_passes(self) -> None:
        report = "- 合同名称：测试合同\n- 法律依据：《民法典》第五百零九条\n"
        result = check_report_integrity(report)
        self.assertTrue(result["passed"])
        self.assertEqual([], result["problems"])

    def test_placeholders_within_threshold_pass(self) -> None:
        report = "\n".join(["- 字段：未提及/待补充"] * MAX_MISSING_PLACEHOLDERS)
        self.assertTrue(check_report_integrity(report)["passed"])

    def _run_cli(self, output_name: str, *extra: str) -> tuple[subprocess.CompletedProcess[str], bool, str]:
        with TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            output_path = Path(tmp) / output_name
            plan_path.write_text(json.dumps(COLLAPSED_PLAN, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.report.reporting",
                    "--plan",
                    str(plan_path),
                    "--output",
                    str(output_path),
                    *extra,
                ],
                cwd=SKILL_ROOT,
                capture_output=True,
                text=True,
            )
            return result, output_path.exists(), (
                output_path.read_text(encoding="utf-8") if output_path.exists() else ""
            )

    def test_producer_does_not_self_report_success(self) -> None:
        """渲染无异常不等于成功：字段塌缩时脚本必须非零退出。"""
        result, exists, _ = self._run_cli("out.md")
        self.assertEqual(1, result.returncode)
        self.assertIn("报告未通过完整性复核", result.stderr)
        self.assertFalse(exists, "失败时不得留下可误交付的报告")

    def test_skip_flag_allows_placeholder_draft(self) -> None:
        result, exists, content = self._run_cli(
            "out.md", "--skip-integrity-check", "--draft-authorization", "user-confirmed-20260811"
        )
        self.assertEqual(0, result.returncode)
        self.assertTrue(exists)
        self.assertIn("草稿（已跳过完整性复核）", content)

    def test_skip_flag_requires_recorded_authorization(self) -> None:
        result, exists, _ = self._run_cli("out.md", "--skip-integrity-check")
        self.assertEqual(2, result.returncode)
        self.assertFalse(exists)

    @staticmethod
    def _write_minimal_docx(path: Path) -> None:
        files = {
            "[Content_Types].xml": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Override PartName="/word/document.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                '<Override PartName="/word/settings.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
                "</Types>"
            ),
            "word/_rels/document.xml.rels": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
            ),
            "word/settings.xml": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'
            ),
            "word/document.xml": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>测试合同</w:t></w:r></w:p></w:body></w:document>"
            ),
        }
        with zipfile.ZipFile(path, "w") as archive:
            for relative_path, content in files.items():
                archive.writestr(relative_path, content)

    def test_default_apply_entry_blocks_before_creating_formal_deliverables(self) -> None:
        """默认 DOCX 交付路径必须在写入任何正式产物前阻断塌缩报告。"""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_docx = root / "input.docx"
            plan_path = root / "plan.json"
            output_docx = root / "revised.docx"
            report_path = root / "report.md"
            report_docx = root / "report.docx"
            log_path = root / "execution.json"
            self._write_minimal_docx(input_docx)
            plan_path.write_text(
                json.dumps({"meta": {"contract_name": "测试合同"}, "summary": {}, "findings": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.review.apply_review_plan",
                    "--input", str(input_docx),
                    "--plan", str(plan_path),
                    "--output", str(output_docx),
                    "--report", str(report_path),
                    "--report-docx", str(report_docx),
                    "--log", str(log_path),
                    "--author", "测试律师",
                    "--organization", "测试机构",
                    "--party-role", "中立",
                    "--no-archive",
                    "--no-validate",
                ],
                cwd=SKILL_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(1, result.returncode, result.stderr)
            self.assertIn("报告未通过完整性复核", result.stderr)
            self.assertFalse(output_docx.exists())
            self.assertFalse(report_path.exists())
            self.assertFalse(report_docx.exists())
            self.assertFalse(log_path.exists())


if __name__ == "__main__":
    unittest.main()
