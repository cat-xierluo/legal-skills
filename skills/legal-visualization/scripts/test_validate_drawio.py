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

    def test_shape_policy_passes_on_rectangles(self) -> None:
        shapes = [
            "rounded=1;whiteSpace=wrap;fillColor=#E3F2FD;strokeColor=#1f77b4;",
            "rounded=1;whiteSpace=wrap;fillColor=#E3F2FD;strokeColor=#1f77b4;",
            "rounded=1;whiteSpace=wrap;fillColor=#FFF3E0;strokeColor=#FF8C00;",
            "rounded=1;whiteSpace=wrap;fillColor=#F5F5F5;strokeColor=#9E9E9E;",
            "rhombus;whiteSpace=wrap;fillColor=#FFF3E0;strokeColor=#FF8C00;",
            "rounded=1;whiteSpace=wrap;fillColor=#FFFDE7;strokeColor=#F9A825;",
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".drawio", delete=False, encoding="utf-8") as handle:
            handle.write('<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>')
            for index, shape in enumerate(shapes):
                role = ' visualRole="decision"' if "rhombus" in shape else ""
                handle.write(
                    f'<mxCell id="n{index}" value="节点{index}" style="{shape}" '
                    f'vertex="1" parent="1"{role}><mxGeometry x="{60 + index * 140}" y="80" width="120" height="70" as="geometry"/></mxCell>'
                )
            handle.write('</root></mxGraphModel>')
            path = Path(handle.name)
        try:
            report = validate_file(path)
            self.assertTrue(report["passed"], report)
            self.assertNotIn("shape_policy", self.finding_ids(report, "warning"))
        finally:
            path.unlink(missing_ok=True)

    def test_shape_policy_warns_on_exotic_shapes(self) -> None:
        shapes = [
            "rounded=1;whiteSpace=wrap;fillColor=#E3F2FD;strokeColor=#1f77b4;",
            "ellipse;whiteSpace=wrap;fillColor=#E3F2FD;strokeColor=#1f77b4;",
            "shape=cylinder3;whiteSpace=wrap;fillColor=#FFF3E0;strokeColor=#FF8C00;size=12;",
            "shape=document;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#1f77b4;",
            "hexagon;whiteSpace=wrap;fillColor=#FFF8E1;strokeColor=#F9A825;",
            "rounded=1;whiteSpace=wrap;fillColor=#F5F5F5;strokeColor=#9E9E9E;",
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
            self.assertTrue(report["passed"], "非限定形状仅为 warning，不应阻断导出")
            self.assertIn("shape_policy", self.finding_ids(report, "warning"))
        finally:
            path.unlink(missing_ok=True)

    def test_shape_policy_warns_on_unregistered_diamond(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".drawio", delete=False, encoding="utf-8") as handle:
            handle.write(
                '<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
                '<mxCell id="n1" value="普通主体" style="rhombus;whiteSpace=wrap;" '
                'vertex="1" parent="1"><mxGeometry x="60" y="80" width="160" height="80" as="geometry"/></mxCell>'
                '</root></mxGraphModel>'
            )
            path = Path(handle.name)
        try:
            report = validate_file(path)
            self.assertTrue(report["passed"], report)
            self.assertIn("shape_policy", self.finding_ids(report, "warning"))
        finally:
            path.unlink(missing_ok=True)

    def test_edge_label_overlap_with_text_block_is_warned(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".drawio", delete=False, encoding="utf-8") as handle:
            handle.write(
                '<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
                '<mxCell id="a" value="上方节点" style="rounded=1;whiteSpace=wrap;" vertex="1" parent="1">'
                '<mxGeometry x="200" y="40" width="160" height="60" as="geometry"/></mxCell>'
                '<mxCell id="b" value="下方节点" style="rounded=1;whiteSpace=wrap;" vertex="1" parent="1">'
                '<mxGeometry x="200" y="240" width="160" height="60" as="geometry"/></mxCell>'
                '<mxCell id="middle-label" value="栏目标题" style="text;fontSize=12;" vertex="1" parent="1">'
                '<mxGeometry x="220" y="160" width="120" height="22" as="geometry"/></mxCell>'
                '<mxCell id="e1" value="合同关系" style="endArrow=classic;fontSize=12;" edge="1" source="b" target="a" parent="1">'
                '<mxGeometry relative="1" as="geometry"/></mxCell>'
                '</root></mxGraphModel>'
            )
            path = Path(handle.name)
        try:
            report = validate_file(path)
            self.assertTrue(report["passed"], report)
            self.assertIn("edge_label_overlap", self.finding_ids(report, "warning"))
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
