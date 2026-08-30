#!/usr/bin/env python3
"""版式门禁最小正反例。

每个反例只改动一条硬约束，用于防止“有 checker 但关键问题仍逃逸”。
"""
from __future__ import annotations

import copy
import importlib.util
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from lxml import etree

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from layout_gate import R, W, audit_docx, audit_pdf  # noqa: E402


POLICY = {
    "template_name": "layout-fixture",
    "page_numbers": "required",
    "page_number_start": 1,
    "require_a4": True,
    "require_table_center": True,
    "require_fixed_table_layout": True,
    "require_row_cant_split": True,
    "forbid_blank_pages": True,
    "center_tolerance_twips": 40,
    "render_center_tolerance_points": 2.5,
    "render_page_number_center_tolerance_points": 18.0,
    "render_a4_tolerance_points": 2.0,
}


def make_document(*, centered: bool = True, grid_ok: bool = True,
                  cant_split: bool = True, long_text: bool = False) -> bytes:
    document = etree.Element(W + "document", nsmap={"w": W[1:-1], "r": R[1:-1]})
    body = etree.SubElement(document, W + "body")
    table = etree.SubElement(body, W + "tbl")
    properties = etree.SubElement(table, W + "tblPr")
    etree.SubElement(properties, W + "tblW", {W + "w": "0", W + "type": "auto"})
    etree.SubElement(properties, W + "jc", {W + "val": "center" if centered else "left"})
    etree.SubElement(properties, W + "tblInd", {W + "w": "0", W + "type": "dxa"})
    etree.SubElement(properties, W + "tblLayout", {W + "type": "fixed"})
    grid = etree.SubElement(table, W + "tblGrid")
    etree.SubElement(grid, W + "gridCol", {W + "w": "2000"})
    etree.SubElement(grid, W + "gridCol", {W + "w": "2000"})
    row = etree.SubElement(table, W + "tr")
    row_properties = etree.SubElement(row, W + "trPr")
    if cant_split:
        etree.SubElement(row_properties, W + "cantSplit")
    for index in range(2):
        cell = etree.SubElement(row, W + "tc")
        cell_properties = etree.SubElement(cell, W + "tcPr")
        width = "1999" if index == 1 and not grid_ok else "2000"
        etree.SubElement(cell_properties, W + "tcW", {W + "w": width, W + "type": "dxa"})
        paragraph = etree.SubElement(cell, W + "p")
        run = etree.SubElement(paragraph, W + "r")
        text = etree.SubElement(run, W + "t")
        text.text = ("这是合法长文本，" * 500) if long_text else f"单元格{index + 1}"
    section = etree.SubElement(body, W + "sectPr")
    etree.SubElement(section, W + "footerReference", {
        W + "type": "default", R + "id": "rIdFooter",
    })
    etree.SubElement(section, W + "pgSz", {W + "w": "11906", W + "h": "16838"})
    etree.SubElement(section, W + "pgMar", {
        W + "top": "400", W + "bottom": "998",
        W + "left": "3953", W + "right": "3953", W + "footer": "720",
    })
    return etree.tostring(document, xml_declaration=True, encoding="UTF-8", standalone=True)


def make_footer(*, hardcoded: bool = False) -> bytes:
    footer = etree.Element(W + "ftr", nsmap={"w": W[1:-1]})
    paragraph = etree.SubElement(footer, W + "p")
    ppr = etree.SubElement(paragraph, W + "pPr")
    etree.SubElement(ppr, W + "jc", {W + "val": "center"})
    run = etree.SubElement(paragraph, W + "r")
    if hardcoded:
        text = etree.SubElement(run, W + "t")
        text.text = "351"
    else:
        etree.SubElement(run, W + "fldChar", {W + "fldCharType": "begin"})
        instruction = etree.SubElement(run, W + "instrText")
        instruction.text = "PAGE"
        etree.SubElement(run, W + "fldChar", {W + "fldCharType": "separate"})
        text = etree.SubElement(run, W + "t")
        text.text = "1"
        etree.SubElement(run, W + "fldChar", {W + "fldCharType": "end"})
    return etree.tostring(footer, xml_declaration=True, encoding="UTF-8", standalone=True)


def write_docx(directory: Path, *, centered: bool = True, grid_ok: bool = True,
               cant_split: bool = True, long_text: bool = False,
               hardcoded_page: bool = False) -> Path:
    path = directory / "fixture.docx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", make_document(
            centered=centered, grid_ok=grid_ok,
            cant_split=cant_split, long_text=long_text,
        ))
        archive.writestr("word/footer1.xml", make_footer(hardcoded=hardcoded_page))
        archive.writestr(
            "word/_rels/document.xml.rels",
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rIdFooter" '
            b'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" '
            b'Target="footer1.xml"/>'
            b'</Relationships>',
        )
    return path


class DocxLayoutGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ecg-layout-test-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def assert_fails(self, path: Path, code: str):
        report = audit_docx(path, copy.deepcopy(POLICY))
        self.assertFalse(report["ok"])
        self.assertIn(code, {item["code"] for item in report["issues"]})

    def test_legal_long_text_near_miss_passes(self):
        """合法长文本仍保留 cantSplit；静态门禁不把自然换页误报为错误。"""
        report = audit_docx(write_docx(self.root, long_text=True), copy.deepcopy(POLICY))
        self.assertTrue(report["ok"], report["issues"])

    def test_table_left_offset_is_blocked(self):
        self.assert_fails(write_docx(self.root, centered=False), "ECG-LAYOUT-CENTER")

    def test_cell_grid_mismatch_is_blocked(self):
        self.assert_fails(write_docx(self.root, grid_ok=False), "ECG-LAYOUT-GRID")

    def test_splittable_row_is_blocked(self):
        self.assert_fails(write_docx(self.root, cant_split=False), "ECG-LAYOUT-ROW-BREAK")

    def test_hardcoded_page_number_is_blocked(self):
        self.assert_fails(write_docx(self.root, hardcoded_page=True), "ECG-LAYOUT-PAGINATION")


@unittest.skipUnless(importlib.util.find_spec("fitz"), "需要 PyMuPDF")
class RenderedLayoutGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ecg-layout-pdf-test-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make_pdf(self, *, table_offset: float = 0.0, page_number: bool = True,
                 blank: bool = False, page_values: tuple[str, ...] = ("1",)) -> Path:
        import fitz
        path = self.root / "fixture.pdf"
        document = fitz.open()
        for value in page_values:
            page = document.new_page(width=595.28, height=841.89)
            if not blank:
                left, right = 64.0 + table_offset, 531.28 + table_offset
                page.draw_rect(fitz.Rect(left, 100, right, 300), width=0.8)
                page.insert_text((80, 140), "layout fixture", fontsize=10)
            if page_number:
                page.insert_textbox(
                    fitz.Rect(280, 785, 315, 815), value, fontsize=10, align=1
                )
        document.save(path)
        document.close()
        return path

    def test_rendered_centered_page_passes(self):
        report = audit_pdf(self.make_pdf(), copy.deepcopy(POLICY))
        self.assertTrue(report["ok"], report["issues"])

    def test_rendered_offset_table_is_blocked(self):
        report = audit_pdf(self.make_pdf(table_offset=12), copy.deepcopy(POLICY))
        self.assertIn("ECG-LAYOUT-CENTER", {item["code"] for item in report["issues"]})

    def test_rendered_missing_page_number_is_blocked(self):
        report = audit_pdf(self.make_pdf(page_number=False), copy.deepcopy(POLICY))
        self.assertIn("ECG-LAYOUT-PAGINATION", {item["code"] for item in report["issues"]})

    def test_rendered_page_number_restart_is_blocked(self):
        report = audit_pdf(
            self.make_pdf(page_values=("1", "1")), copy.deepcopy(POLICY)
        )
        self.assertIn("ECG-LAYOUT-PAGINATION", {item["code"] for item in report["issues"]})

    def test_rendered_blank_page_is_blocked(self):
        report = audit_pdf(self.make_pdf(blank=True), copy.deepcopy(POLICY))
        codes = {item["code"] for item in report["issues"]}
        self.assertIn("ECG-LAYOUT-NO-BLANK-PAGE", codes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
