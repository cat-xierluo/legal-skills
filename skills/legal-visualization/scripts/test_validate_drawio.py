#!/usr/bin/env python3
"""validate_drawio.py 的领域回归。"""

from __future__ import annotations

import sys
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from validate_drawio import validate_file  # noqa: E402


class ValidateDrawioTest(unittest.TestCase):
    def fixture(self, name: str) -> Path:
        return SKILL_ROOT / "assets" / "stability" / name

    def finding_ids(self, report: dict, severity: str) -> set[str]:
        return {
            item["check"]
            for item in report["findings"]
            if item["severity"] == severity
        }

    def test_minimal_geometry_overlap_is_blocked(self) -> None:
        report = validate_file(self.fixture("geometry-overlap.drawio"))
        self.assertFalse(report["passed"])
        self.assertIn("geometry_overlap", self.finding_ids(report, "error"))

    def test_text_overflow_is_blocked(self) -> None:
        report = validate_file(self.fixture("text-overflow.drawio"))
        self.assertFalse(report["passed"])
        self.assertIn("text_fit", self.finding_ids(report, "error"))

    def test_long_edge_label_is_blocked(self) -> None:
        report = validate_file(self.fixture("edge-label-overflow.drawio"))
        self.assertFalse(report["passed"])
        self.assertIn("edge_label_risk", self.finding_ids(report, "error"))

    def test_legal_container_and_touching_boundary_pass(self) -> None:
        report = validate_file(self.fixture("legal-container-near-miss.drawio"))
        self.assertTrue(report["passed"], report)
        self.assertNotIn("geometry_overlap", self.finding_ids(report, "error"))
        self.assertNotIn("parent_relationships", self.finding_ids(report, "error"))

    def test_all_published_templates_have_no_hard_geometry_error(self) -> None:
        templates = sorted((SKILL_ROOT / "templates").rglob("*.drawio"))
        self.assertGreaterEqual(len(templates), 18)
        failures = {
            str(path.relative_to(SKILL_ROOT)): validate_file(path)
            for path in templates
            if not validate_file(path)["passed"]
        }
        self.assertEqual(failures, {})

    def test_export_is_blocked_before_copying_invalid_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "export_drawio.py"),
                    str(self.fixture("geometry-overlap.drawio")),
                    "--format",
                    "png",
                    "--output-dir",
                    directory,
                    "--json",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("未通过领域校验", result.stdout)
            created = {path.name for path in Path(directory).iterdir()}
            self.assertEqual(created, {"export-report.json"})


if __name__ == "__main__":
    unittest.main()
