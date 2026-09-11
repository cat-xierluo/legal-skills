#!/usr/bin/env python3
"""表级重复表头门禁回归：只校验合同指向的目标表，且严格 fail-closed。"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from lxml import etree

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from fill_template import apply_semantic_table_headers  # noqa: E402
from layout_gate import W, audit_docx, load_policy  # noqa: E402

ANCHOR = "关联民事案件信息表"
POLICY_PATH = SKILL_DIR / "config" / "layout-policy.json"
TEMPLATES = (
    SKILL_DIR / "templates" / "24-侵害发明专利权纠纷-民事起诉状",
    SKILL_DIR / "templates" / "25-侵害外观设计专利权纠纷-民事起诉状",
)


def semantic_policy(anchor: str = ANCHOR, header_rows: int = 3) -> dict:
    return {
        "template_name": "semantic-header-fixture",
        "semantic_table_headers": {
            "enabled": True,
            "contracts": [{"anchor": anchor, "header_rows": header_rows}],
        },
        "require_a4": False,
        "require_table_center": False,
        "require_fixed_table_layout": False,
        "require_row_cant_split": False,
        "require_visible_glyphs": False,
        "require_column_geometry_consistency": False,
        "require_cell_alignment": False,
        "page_numbers": "forbidden",
    }


def _row(table, text: str, marker: bool | str) -> None:
    row = etree.SubElement(table, W + "tr")
    row_properties = etree.SubElement(row, W + "trPr")
    if marker is not False:
        attributes = {} if marker is True else {W + "val": str(marker)}
        etree.SubElement(row_properties, W + "tblHeader", attributes)
    cell = etree.SubElement(row, W + "tc")
    paragraph = etree.SubElement(cell, W + "p")
    run = etree.SubElement(paragraph, W + "r")
    node = etree.SubElement(run, W + "t")
    node.text = text


def fixture_docx(
    root: Path,
    *,
    flags: tuple[bool | str, ...] = (True, True, True, False),
    anchor_row: int = 0,
    duplicate_anchor: bool = False,
) -> Path:
    document = etree.Element(W + "document", nsmap={"w": W[1:-1]})
    body = etree.SubElement(document, W + "body")
    table = etree.SubElement(body, W + "tbl")
    etree.SubElement(table, W + "tblPr")
    grid = etree.SubElement(table, W + "tblGrid")
    etree.SubElement(grid, W + "gridCol", {W + "w": "8000"})
    for index, flag in enumerate(flags):
        text = ANCHOR if index == anchor_row else f"第{index + 1}行"
        if duplicate_anchor and index == len(flags) - 1:
            text = ANCHOR
        _row(table, text, flag)
    etree.SubElement(body, W + "sectPr")

    path = root / "fixture.docx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "word/document.xml",
            etree.tostring(
                document, xml_declaration=True, encoding="UTF-8", standalone=True,
            ),
        )
    return path


def header_issues(path: Path, policy: dict) -> list[dict]:
    return [
        item for item in audit_docx(path, policy)["issues"]
        if item["code"] == "ECG-LAYOUT-HEADER-REPEAT"
    ]


class SemanticHeaderDocxGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ecg-semhdr-gate-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_exact_contract_rows_pass(self):
        self.assertEqual(header_issues(fixture_docx(self.root), semantic_policy()), [])

    def test_missing_second_header_row_is_blocked(self):
        issues = header_issues(
            fixture_docx(self.root, flags=(True, False, True, False)),
            semantic_policy(),
        )
        self.assertEqual([item.get("row") for item in issues], [2])

    def test_explicit_false_marker_is_blocked(self):
        issues = header_issues(
            fixture_docx(self.root, flags=(True, "false", True, False)),
            semantic_policy(),
        )
        self.assertEqual([item.get("row") for item in issues], [2])

    def test_data_row_marked_as_header_is_blocked(self):
        issues = header_issues(
            fixture_docx(self.root, flags=(True, True, True, True)),
            semantic_policy(),
        )
        self.assertEqual([item.get("row") for item in issues], [4])

    def test_anchor_not_in_first_row_is_blocked(self):
        issues = header_issues(
            fixture_docx(self.root, anchor_row=1), semantic_policy(),
        )
        self.assertTrue(any("不在首行" in item["message"] for item in issues))

    def test_duplicate_anchor_is_blocked(self):
        issues = header_issues(
            fixture_docx(self.root, duplicate_anchor=True), semantic_policy(),
        )
        self.assertTrue(any("命中 2 处" in item["message"] for item in issues))

    def test_invalid_contract_is_fail_closed(self):
        policy = semantic_policy()
        policy["semantic_table_headers"]["contracts"][0]["header_rows"] = True
        issues = header_issues(fixture_docx(self.root), policy)
        self.assertTrue(any("必须是正整数" in item["message"] for item in issues))

    def test_real_24_and_25_generated_trees_satisfy_docx_contract(self):
        for template in TEMPLATES:
            with self.subTest(template=template.name):
                tree = self.root / template.name[:2]
                shutil.copytree(template, tree)
                policy = load_policy(POLICY_PATH, template.name)
                stats = apply_semantic_table_headers(tree, policy)
                self.assertEqual(stats["errors"], [])
                path = self.root / f"{template.name[:2]}.docx"
                with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
                    for file in tree.rglob("*"):
                        if file.is_file():
                            archive.write(file, file.relative_to(tree).as_posix())
                self.assertEqual(header_issues(path, policy), [])


if __name__ == "__main__":
    unittest.main()
