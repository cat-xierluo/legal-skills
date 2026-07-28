#!/usr/bin/env python3
"""apply_visual_roles.py 的样式编译与几何守恒回归。"""

from __future__ import annotations

import copy
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from apply_visual_roles import (  # noqa: E402
    CompileError,
    compile_tree,
    geometry_snapshot,
    write_validated,
)
from validate_drawio import parse_style  # noqa: E402


DRAWIO = """<mxGraphModel><root>
<mxCell id="0"/><mxCell id="1" parent="0"/>
<mxCell id="a" value="原告" style="rounded=1;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#000000;" vertex="1" parent="1"><mxGeometry x="40" y="40" width="160" height="60" as="geometry"/></mxCell>
<mxCell id="b" value="被告" style="rounded=1;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#000000;" vertex="1" parent="1"><mxGeometry x="300" y="40" width="160" height="60" as="geometry"/></mxCell>
<mxCell id="e1" value="关系" style="edgeStyle=orthogonalEdgeStyle;strokeColor=#000000;" edge="1" parent="1" source="a" target="b"><mxGeometry relative="1" as="geometry"/></mxCell>
</root></mxGraphModel>"""


def make_tree() -> ET.ElementTree:
    return ET.ElementTree(ET.fromstring(DRAWIO))


def make_spec(theme: str = "client_report") -> dict:
    return {
        "vizspec_version": "2.1",
        "routing": {
            "primary_scene": "multi-party-relation",
            "selection_reason": "验证视觉角色编译",
        },
        "visual": {"theme": theme, "density": "normal"},
        "entities": [
            {
                "id": "a",
                "visual_role": "plaintiff",
                "epistemic_status": "confirmed",
                "emphasis": "normal",
            },
            {
                "id": "b",
                "visual_role": "defendant",
                "epistemic_status": "disputed",
                "emphasis": "high",
            },
        ],
        "relations": [
            {"id": "e1", "source": "a", "target": "b", "status": "inferred"}
        ],
    }


def cell(tree: ET.ElementTree, cell_id: str) -> ET.Element:
    found = tree.getroot().find(f".//mxCell[@id='{cell_id}']")
    assert found is not None
    return found


class ApplyVisualRolesTest(unittest.TestCase):
    def test_compiler_changes_style_and_metadata_but_not_geometry(self) -> None:
        tree = make_tree()
        before = geometry_snapshot(tree.getroot())
        report = compile_tree(tree, make_spec())
        after = geometry_snapshot(tree.getroot())

        self.assertEqual(before, after)
        self.assertTrue(report["geometry_preserved"])
        plaintiff_style = parse_style(cell(tree, "a").get("style"))
        defendant_style = parse_style(cell(tree, "b").get("style"))
        edge_style = parse_style(cell(tree, "e1").get("style"))
        self.assertNotEqual(plaintiff_style["fillColor"], "#FFFFFF")
        self.assertNotEqual(defendant_style["fillColor"], "#FFFFFF")
        self.assertNotEqual(plaintiff_style["strokeWidth"], defendant_style["strokeWidth"])
        self.assertNotEqual(defendant_style.get("dashed"), "0")
        self.assertEqual(edge_style.get("dashed"), "1")
        self.assertEqual(cell(tree, "a").get("visualRole"), "plaintiff")
        self.assertEqual(cell(tree, "b").get("epistemicStatus"), "disputed")

    def test_defendant_role_does_not_implicitly_mean_disputed(self) -> None:
        tree = make_tree()
        spec = make_spec()
        spec["entities"][1]["epistemic_status"] = "confirmed"
        spec["entities"][1]["emphasis"] = "normal"
        compile_tree(tree, spec)
        style = parse_style(cell(tree, "b").get("style"))
        self.assertNotEqual(style.get("dashed"), "1")
        self.assertEqual(style.get("strokeWidth"), "2")

    def test_three_themes_generate_distinct_styles(self) -> None:
        signatures: set[tuple[str | None, ...]] = set()
        for theme in ("client_report", "court_submit", "lawyer_workpaper"):
            tree = make_tree()
            compile_tree(tree, make_spec(theme))
            style = parse_style(cell(tree, "a").get("style"))
            signatures.add(
                (
                    style.get("fillColor"),
                    style.get("strokeColor"),
                    style.get("fontColor"),
                    style.get("fontSize"),
                )
            )
        self.assertEqual(len(signatures), 3)

    def test_decision_role_uses_diamond_without_geometry_change(self) -> None:
        tree = make_tree()
        spec = make_spec()
        spec["entities"][0]["visual_role"] = "decision"
        before = copy.deepcopy(geometry_snapshot(tree.getroot()))
        compile_tree(tree, spec)
        style = parse_style(cell(tree, "a").get("style"))
        self.assertIn("rhombus", style)
        self.assertEqual(before, geometry_snapshot(tree.getroot()))

    def test_missing_drawio_node_is_blocking_error(self) -> None:
        tree = make_tree()
        spec = make_spec()
        spec["entities"][0]["id"] = "absent"
        spec["relations"][0]["source"] = "absent"
        with self.assertRaisesRegex(CompileError, "absent"):
            compile_tree(tree, spec)

    def test_geometry_is_preserved_after_atomic_disk_write(self) -> None:
        tree = make_tree()
        before = geometry_snapshot(tree.getroot())
        compile_tree(tree, make_spec())
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "styled.drawio"
            write_validated(tree, output, force=False)
            written = ET.parse(output)
        self.assertEqual(before, geometry_snapshot(written.getroot()))


if __name__ == "__main__":
    unittest.main()
