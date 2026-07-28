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

    def test_shape_diversity_warns_on_uniform_rectangles(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".drawio", delete=False, encoding="utf-8") as handle:
            handle.write('<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>')
            for index in range(6):
                handle.write(
                    f'<mxCell id="n{index}" value="节点{index}" '
                    f'style="rounded=1;whiteSpace=wrap;fillColor=#E3F2FD;strokeColor=#1f77b4;" '
                    f'vertex="1" parent="1"><mxGeometry x="{60 + index * 130}" y="80" width="110" height="60" as="geometry"/></mxCell>'
                )
            handle.write('</root></mxGraphModel>')
            path = Path(handle.name)
        try:
            report = validate_file(path)
            self.assertTrue(report["passed"], "形状单一仅为 warning，不应阻断导出")
            self.assertIn("shape_diversity", self.finding_ids(report, "warning"))
        finally:
            path.unlink(missing_ok=True)

    def test_shape_diversity_ok_on_mixed_shapes(self) -> None:
        shapes = [
            "rounded=1;whiteSpace=wrap;fillColor=#E3F2FD;strokeColor=#1f77b4;",
            "ellipse;whiteSpace=wrap;fillColor=#E3F2FD;strokeColor=#1f77b4;",
            "hexagon;whiteSpace=wrap;fillColor=#FFF8E1;strokeColor=#F9A825;",
            "rhombus;whiteSpace=wrap;fillColor=#FDECEA;strokeColor=#C0392B;",
            "shape=document;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#1f77b4;",
            "shape=parallelogram;whiteSpace=wrap;fillColor=#E8F5E9;strokeColor=#43A047;",
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".drawio", delete=False, encoding="utf-8") as handle:
            handle.write('<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>')
            for index, shape in enumerate(shapes):
                handle.write(
                    f'<mxCell id="n{index}" value="节点{index}" style="{shape}" '
                    f'vertex="1" parent="1"><mxGeometry x="{60 + index * 140}" y="80" width="120" height="70" as="geometry"/></mxCell>'
                )
            handle.write('</root></mxGraphModel>')
            path = Path(handle.name)
        try:
            report = validate_file(path)
            self.assertTrue(report["passed"], report)
            self.assertNotIn("shape_diversity", self.finding_ids(report, "warning"))
        finally:
            path.unlink(missing_ok=True)

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
