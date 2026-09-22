#!/usr/bin/env python3
"""版式门禁终稿级正反例。

每个反例只改动一条硬约束，用于防止“有 checker 但关键问题仍逃逸”。
渲染层用例用 PyMuPDF 构造带真实几何/字形信息的 PDF，
避免把验证降级成“只看 XML 标志是否存在”。
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

from layout_gate import (  # noqa: E402
    R,
    W,
    _find_soffice,
    _notdef_glyphs,
    _renderer_kind,
    _soffice_version,
    audit_docx,
    audit_pdf,
    audit_text_survival,
    check,
)


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

# 声明类检查（tblHeader/显式 vAlign/jc）默认关闭，仅显式启用时验证。
DECLARATION_POLICY = {
    **POLICY,
    "require_repeated_table_header_declaration": True,
    "require_cell_alignment_declaration": True,
}

_RELS_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rIdFooter" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" '
    'Target="footer1.xml"/>'
    '</Relationships>'
)

# U+0378 是未分配码位，任何字体都没有对应字形，TextWriter 会落 .notdef。
_NOTDEF_SAMPLE = "缺͸字"


def make_document(*, centered: bool = True, grid_ok: bool = True,
                  cant_split: bool = True, cant_split_value: str | None = None,
                  long_text: bool = False,
                  header_repeat: bool = True, valign_ok: bool = True,
                  jc_ok: bool = True, suspect_char: str | None = None,
                  single_row: bool = False,
                  grid: tuple[int, ...] = (2000, 2000),
                  margins: tuple[int, int] = (3953, 3953),
                  continuation_grid: tuple[int, ...] | None = None) -> bytes:
    """构造一份默认满足全部终稿约束的 document.xml；每个参数都可注入单一缺陷。"""
    document = etree.Element(W + "document", nsmap={"w": W[1:-1], "r": R[1:-1]})
    body = etree.SubElement(document, W + "body")

    def build_cell(row, width: int, text: str, alignment: str) -> None:
        cell = etree.SubElement(row, W + "tc")
        cell_properties = etree.SubElement(cell, W + "tcPr")
        etree.SubElement(cell_properties, W + "tcW", {W + "w": str(width), W + "type": "dxa"})
        if valign_ok:
            etree.SubElement(cell_properties, W + "vAlign", {W + "val": "center"})
        paragraph = etree.SubElement(cell, W + "p")
        if jc_ok:
            paragraph_properties = etree.SubElement(paragraph, W + "pPr")
            etree.SubElement(paragraph_properties, W + "jc", {W + "val": alignment})
        run = etree.SubElement(paragraph, W + "r")
        value = etree.SubElement(run, W + "t")
        value.text = text

    def build_row(table, widths: tuple[int, ...], *, header: bool) -> None:
        row = etree.SubElement(table, W + "tr")
        row_properties = etree.SubElement(row, W + "trPr")
        if cant_split:
            attributes = {W + "val": cant_split_value} if cant_split_value else {}
            etree.SubElement(row_properties, W + "cantSplit", attributes)
        if header and header_repeat:
            etree.SubElement(row_properties, W + "tblHeader")
        for index, width in enumerate(widths):
            if header:
                build_cell(row, width, f"表头{index + 1}", "center")
                continue
            text = ("这是合法长文本，" * 500) if long_text else f"单元格{index + 1}"
            if index == len(widths) - 1 and suspect_char:
                text += suspect_char
            actual_width = width if (grid_ok or index < len(widths) - 1) else width - 1
            build_cell(row, actual_width, text, "left")

    def build_table(widths: tuple[int, ...]) -> None:
        table = etree.SubElement(body, W + "tbl")
        properties = etree.SubElement(table, W + "tblPr")
        etree.SubElement(properties, W + "tblW", {W + "w": "0", W + "type": "auto"})
        etree.SubElement(properties, W + "jc", {W + "val": "center" if centered else "left"})
        etree.SubElement(properties, W + "tblInd", {W + "w": "0", W + "type": "dxa"})
        etree.SubElement(properties, W + "tblLayout", {W + "type": "fixed"})
        grid_element = etree.SubElement(table, W + "tblGrid")
        for width in widths:
            etree.SubElement(grid_element, W + "gridCol", {W + "w": str(width)})
        if not single_row:
            build_row(table, widths, header=True)
        build_row(table, widths, header=False)

    build_table(tuple(grid))
    if continuation_grid is not None:
        # 紧邻上一表、中间无段落：模拟同一逻辑表被拆成两张物理表续接。
        build_table(tuple(continuation_grid))

    section = etree.SubElement(body, W + "sectPr")
    etree.SubElement(section, W + "footerReference", {
        W + "type": "default", R + "id": "rIdFooter",
    })
    etree.SubElement(section, W + "pgSz", {W + "w": "11906", W + "h": "16838"})
    etree.SubElement(section, W + "pgMar", {
        W + "top": "400", W + "bottom": "998",
        W + "left": str(margins[0]), W + "right": str(margins[1]), W + "footer": "720",
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
               cant_split: bool = True, cant_split_value: str | None = None,
               long_text: bool = False,
               hardcoded_page: bool = False, header_repeat: bool = True,
               valign_ok: bool = True, jc_ok: bool = True,
               suspect_char: str | None = None, single_row: bool = False,
               grid: tuple[int, ...] = (2000, 2000),
               margins: tuple[int, int] = (3953, 3953),
               continuation_grid: tuple[int, ...] | None = None) -> Path:
    path = directory / "fixture.docx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", make_document(
            centered=centered, grid_ok=grid_ok,
            cant_split=cant_split, cant_split_value=cant_split_value,
            long_text=long_text,
            header_repeat=header_repeat, valign_ok=valign_ok, jc_ok=jc_ok,
            suspect_char=suspect_char, single_row=single_row,
            grid=grid, margins=margins, continuation_grid=continuation_grid,
        ))
        archive.writestr("word/footer1.xml", make_footer(hardcoded=hardcoded_page))
        archive.writestr("word/_rels/document.xml.rels", _RELS_XML)
    return path


def write_opc_docx(directory: Path, **kwargs) -> Path:
    """带 [Content_Types].xml 的最小合法 OPC 包，可直接被 LibreOffice 打开渲染。"""
    path = directory / "fixture-opc.docx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" '
            'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/footer1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
            '</Types>',
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rIdDoc" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/>'
            '</Relationships>',
        )
        archive.writestr("word/document.xml", make_document(**kwargs))
        archive.writestr("word/footer1.xml", make_footer())
        archive.writestr("word/_rels/document.xml.rels", _RELS_XML)
    return path


class DocxLayoutGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ecg-layout-test-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def assert_fails(self, path: Path, code: str, policy: dict | None = None):
        report = audit_docx(path, copy.deepcopy(policy or POLICY))
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

    def test_oversized_long_row_may_split_naturally(self):
        """超过整页容量的长事实行允许自然跨页；对它强制 cantSplit 会让
        LibreOffice 在忽略约束时出现不稳定的整行推页。"""
        report = audit_docx(
            write_docx(
                self.root, cant_split=True, cant_split_value="0",
                long_text=True, single_row=True,
            ),
            copy.deepcopy(POLICY),
        )
        self.assertNotIn(
            "ECG-LAYOUT-ROW-BREAK", {item["code"] for item in report["issues"]},
        )
        self.assertTrue(report["ok"], report["issues"])

    def test_hardcoded_page_number_is_blocked(self):
        self.assert_fails(write_docx(self.root, hardcoded_page=True), "ECG-LAYOUT-PAGINATION")

    def test_final_draft_fixture_passes_all_final_checks(self):
        """默认夹具满足全部终稿约束；新增检查不会误伤合规产物。"""
        report = audit_docx(write_docx(self.root), copy.deepcopy(POLICY))
        self.assertTrue(report["ok"], report["issues"])

    def test_replacement_char_in_source_is_blocked(self):
        self.assert_fails(write_docx(self.root, suspect_char="�"), "ECG-LAYOUT-GLYPH")

    def test_private_use_char_in_source_is_blocked(self):
        self.assert_fails(write_docx(self.root, suspect_char=""), "ECG-LAYOUT-GLYPH")

    def test_checkbox_square_is_legitimate_content(self):
        """官方模板用 □ 做复选框（如“男□ 女□”），不得按方框字误报。"""
        report = audit_docx(write_docx(self.root, suspect_char="□"), copy.deepcopy(POLICY))
        self.assertTrue(report["ok"], report["issues"])

    def test_multi_row_table_without_header_declaration_passes_by_default(self):
        """不会跨页的多行表正例：默认策略不因缺 tblHeader 声明而阻断，
        实际跨页表头由渲染层检查兜底。"""
        report = audit_docx(
            write_docx(self.root, header_repeat=False), copy.deepcopy(POLICY),
        )
        self.assertTrue(report["ok"], report["issues"])

    def test_first_row_without_repeated_header_is_blocked_when_declared(self):
        """声明类检查显式启用时仍可拦截缺失的 tblHeader。"""
        self.assert_fails(
            write_docx(self.root, header_repeat=False),
            "ECG-LAYOUT-HEADER-REPEAT",
            policy=DECLARATION_POLICY,
        )

    def test_single_row_table_needs_no_repeated_header(self):
        """单行表不存在跨页续接，不要求 tblHeader。"""
        report = audit_docx(write_docx(self.root, single_row=True), copy.deepcopy(POLICY))
        self.assertTrue(report["ok"], report["issues"])

    def test_repeat_header_declaration_is_measured(self):
        """tblHeader 声明必须被测量：渲染级表头比对的前提来自该计数。"""
        declared = audit_docx(write_docx(self.root), copy.deepcopy(POLICY))
        self.assertEqual(declared["measurements"]["tables_with_repeat_header"], 1)
        undeclared = audit_docx(
            write_docx(self.root, header_repeat=False), copy.deepcopy(POLICY),
        )
        self.assertEqual(undeclared["measurements"]["tables_with_repeat_header"], 0)

    def test_inherited_alignment_table_passes_by_default(self):
        """继承默认对齐的合法表正例：单元格无 vAlign、段落无显式 jc，
        默认策略不视为版式错误（实际对齐由渲染层检查兜底）。"""
        report = audit_docx(
            write_docx(self.root, valign_ok=False, jc_ok=False), copy.deepcopy(POLICY),
        )
        self.assertTrue(report["ok"], report["issues"])

    def test_cell_without_valign_is_blocked_when_declared(self):
        self.assert_fails(
            write_docx(self.root, valign_ok=False),
            "ECG-LAYOUT-CELL-ALIGN",
            policy=DECLARATION_POLICY,
        )

    def test_cell_paragraph_without_explicit_jc_is_blocked_when_declared(self):
        self.assert_fails(
            write_docx(self.root, jc_ok=False),
            "ECG-LAYOUT-CELL-ALIGN",
            policy=DECLARATION_POLICY,
        )

    def test_adjacent_tables_with_drifted_grid_are_blocked(self):
        """紧邻续接表网格漂移意味着跨页列几何对不上。"""
        self.assert_fails(
            write_docx(self.root, continuation_grid=(1900, 2100)),
            "ECG-LAYOUT-COLUMN-GRID",
        )

    def test_adjacent_tables_with_identical_grid_pass(self):
        report = audit_docx(
            write_docx(self.root, continuation_grid=(2000, 2000)), copy.deepcopy(POLICY),
        )
        self.assertTrue(report["ok"], report["issues"])

    def test_check_docx_mode_reports_docx_verified(self):
        """check() 接口保持兼容，且新约束 ID 进入 passed_constraint_ids。"""
        report = check(write_docx(self.root), copy.deepcopy(POLICY), rendered=False)
        self.assertTrue(report["ok"], report["issues"])
        self.assertEqual(report["status"], "DOCX_VERIFIED")
        for constraint in ("ECG-LAYOUT-GLYPH", "ECG-LAYOUT-COLUMN-GRID",
                           "ECG-LAYOUT-CELL-ALIGN", "ECG-LAYOUT-HEADER-REPEAT"):
            self.assertIn(constraint, report["passed_constraint_ids"])


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

    def build_table_pdf(self, specs: list[dict]) -> Path:
        """按页规格画带框线表格：columns 为竖线 x，row_lines 为横线 y，texts 为 (x, y, 文字)。"""
        import fitz
        path = self.root / "fixture-table.pdf"
        document = fitz.open()
        for index, spec in enumerate(specs, 1):
            landscape = spec.get("landscape", False)
            width, height = (841.89, 595.28) if landscape else (595.28, 841.89)
            page = document.new_page(width=width, height=height)
            columns = spec["columns"]
            row_lines = spec.get("row_lines", [100.0, 140.0, 180.0])
            top, bottom = row_lines[0], row_lines[-1]
            for y in row_lines:
                page.draw_line(fitz.Point(columns[0], y), fitz.Point(columns[-1], y), width=0.8)
            for x in columns:
                page.draw_line(fitz.Point(x, top), fitz.Point(x, bottom), width=0.8)
            for x, y0, y1 in spec.get("partial_verticals", []):
                page.draw_line(fitz.Point(x, y0), fitz.Point(x, y1), width=0.8)
            for x, y, text in spec.get("texts", []):
                page.insert_text((x, y), text, fontname="china-s", fontsize=10)
            for extra in spec.get("extra_bands", []):
                extra_columns = extra["columns"]
                extra_rows = extra.get("row_lines", [300.0, 340.0, 380.0])
                for y in extra_rows:
                    page.draw_line(
                        fitz.Point(extra_columns[0], y), fitz.Point(extra_columns[-1], y), width=0.8,
                    )
                for x in extra_columns:
                    page.draw_line(
                        fitz.Point(x, extra_rows[0]), fitz.Point(x, extra_rows[-1]), width=0.8,
                    )
                for x, y, text in extra.get("texts", []):
                    page.insert_text((x, y), text, fontname="china-s", fontsize=10)
            writer_text = spec.get("writer_text")
            if writer_text:
                writer = fitz.TextWriter(page.rect)
                writer.append(
                    (writer_text[0], writer_text[1]), writer_text[2],
                    font=fitz.Font("china-s"), fontsize=12,
                )
                writer.write_text(page)
            if spec.get("page_number", True):
                page.insert_textbox(
                    fitz.Rect(width / 2 - 17.5, height - 57, width / 2 + 17.5, height - 27),
                    spec.get("page_number_text", str(index)), fontsize=10, align=1,
                )
        document.save(path)
        document.close()
        return path

    # ---- 既有渲染层回归 ----

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

    # ---- 表格整体水平居中 ----

    def test_rendered_center_offset_per_table_band(self):
        """居中按每个表格带各自的列边界逐表复核；每页独立。"""
        first = {"columns": [64.0, 297.64, 531.28], "row_lines": [100.0, 140.0, 180.0],
                 "texts": [(80, 130, "项目"), (320, 130, "内容")]}
        shifted = {"columns": [76.0, 309.64, 543.28], "row_lines": [100.0, 140.0, 180.0],
                   "texts": [(92, 130, "附件"), (332, 130, "说明")]}
        report = audit_pdf(self.build_table_pdf([first, shifted]), copy.deepcopy(POLICY))
        issues = {item["code"]: item for item in report["issues"]}
        self.assertIn("ECG-LAYOUT-CENTER", issues)
        self.assertEqual(issues["ECG-LAYOUT-CENTER"].get("page"), 2)

    def test_rendered_two_offset_tables_are_flagged_individually(self):
        """反例：同一页两个偏移表一左一右，合并包围盒中心恰为零，
        逐表检查必须各自拦下，不能互相抵消。"""
        left_table = {
            "columns": [40.0, 180.0, 320.0],  # 中心 180，左偏 117.64 pt
            "row_lines": [100.0, 140.0, 180.0],
            "texts": [(48, 130, "甲"), (188, 130, "乙")],
        }
        right_table = {
            "columns": [275.28, 415.28, 555.28],  # 中心 415.28，右偏 117.64 pt
            "row_lines": [300.0, 340.0, 380.0],
            "texts": [(283, 330, "丙"), (423, 330, "丁")],
        }
        page = {**left_table, "extra_bands": [right_table]}
        report = audit_pdf(self.build_table_pdf([page]), copy.deepcopy(POLICY))
        center_issues = [item for item in report["issues"] if item["code"] == "ECG-LAYOUT-CENTER"]
        self.assertEqual(len(center_issues), 2, report["issues"])
        self.assertEqual({item.get("page") for item in center_issues}, {1})

    # ---- 跨页列几何一致 ----

    def bottom_reaching_page(self) -> dict:
        """首页：表格一直排到页底（触底带），是跨页续接的必要前提。"""
        return {
            "columns": [64.0, 297.64, 531.28],
            "row_lines": [100.0 + 40.0 * step for step in range(18)],  # 100..780 触底
            "texts": [(80, 130, "项目"), (320, 130, "内容"), (80, 170, "张三"),
                      (320, 170, "出借人"), (80, 210, "李四"), (320, 210, "借款人")],
        }

    def test_rendered_two_page_table_with_same_columns_passes(self):
        header = [(80, 130, "项目"), (320, 130, "内容")]
        page_two = {
            "columns": [64.0, 297.64, 531.28],
            "row_lines": [100.0, 140.0, 180.0, 220.0],
            "texts": header + [(80, 170, "王五"), (320, 170, "担保人")],
        }
        report = audit_pdf(
            self.build_table_pdf([self.bottom_reaching_page(), page_two]),
            copy.deepcopy(POLICY),
        )
        self.assertTrue(report["ok"], report["issues"])

    def test_rendered_internal_gridspan_change_is_left_to_docx_gate(self):
        """PDF 无法区分内部列漂移与合法 gridSpan 子集，不能据此误报。"""
        header = [(80, 130, "项目"), (320, 130, "内容")]
        page_two = {
            "columns": [64.0, 280.0, 531.28],  # 中列漂移 17.6 pt
            "row_lines": [100.0, 140.0, 180.0, 220.0],
            "texts": header + [(80, 170, "王五"), (320, 170, "担保人")],
        }
        report = audit_pdf(
            self.build_table_pdf([self.bottom_reaching_page(), page_two]),
            copy.deepcopy(POLICY),
        )
        self.assertNotIn(
            "ECG-LAYOUT-COLUMN-GRID", {item["code"] for item in report["issues"]},
        )
        self.assertTrue(report["ok"], report["issues"])

    def test_rendered_second_table_on_continuation_page_is_not_compared(self):
        """同一页并存“续接表 + 列位不同的新表”：只比对首个（页顶）带，新表不误报。"""
        page_two = {
            "columns": [64.0, 297.64, 531.28],
            "row_lines": [100.0, 140.0, 180.0, 220.0],
            "texts": [(80, 130, "项目"), (320, 130, "内容"), (80, 170, "王五"), (320, 170, "担保人")],
            "extra_bands": [{
                "columns": [80.0, 300.0, 520.0],  # 下方新表列位不同，不参与续接比对
                "row_lines": [300.0, 340.0, 380.0],
                "texts": [(96, 330, "标的"), (320, 330, "金额")],
            }],
        }
        report = audit_pdf(
            self.build_table_pdf([self.bottom_reaching_page(), page_two]),
            copy.deepcopy(POLICY),
        )
        self.assertNotIn(
            "ECG-LAYOUT-COLUMN-GRID", {item["code"] for item in report["issues"]},
        )
        self.assertTrue(report["ok"], report["issues"])

    def test_rendered_continuation_requires_table_at_page_top(self):
        """上一页触底但本页首个表格带不从页顶开始：视为无关新表，不比对。"""
        page_two = {
            "columns": [80.0, 300.0, 520.0],
            "row_lines": [300.0, 340.0, 380.0],
            "texts": [(96, 330, "标的"), (320, 330, "金额")],
        }
        report = audit_pdf(
            self.build_table_pdf([self.bottom_reaching_page(), page_two]),
            copy.deepcopy(POLICY),
        )
        self.assertNotIn(
            "ECG-LAYOUT-COLUMN-GRID", {item["code"] for item in report["issues"]},
        )
        self.assertTrue(report["ok"], report["issues"])

    def test_rendered_new_table_after_finished_table_is_not_flagged(self):
        """上一页表格未触底即已结束，下一页是新表：列位不同不算漂移。"""
        page_one = {
            "columns": [64.0, 297.64, 531.28],
            "row_lines": [100.0, 140.0, 180.0],
            "texts": [(80, 130, "项目"), (320, 130, "内容"), (80, 170, "张三"), (320, 170, "出借人")],
        }
        page_two = {
            "columns": [80.0, 300.0, 520.0],
            "row_lines": [100.0, 140.0, 180.0],
            "texts": [(96, 130, "标的"), (320, 130, "金额")],
        }
        report = audit_pdf(self.build_table_pdf([page_one, page_two]), copy.deepcopy(POLICY))
        self.assertNotIn(
            "ECG-LAYOUT-COLUMN-GRID", {item["code"] for item in report["issues"]},
        )
        self.assertTrue(report["ok"], report["issues"])

    def test_rendered_new_table_at_page_top_is_not_mistaken_for_continuation(self):
        """09-sample 波动回归：上一表恰好在页底结束，下一张表恰好从页顶
        开始且外框相同，但内部列位和顶部文本都不同；缺少身份连续证据时
        不得把新表误报成续表列漂移。"""
        page_two = {
            "columns": [64.0, 177.5, 531.28],
            "row_lines": [100.0, 140.0, 180.0, 220.0],
            "texts": [
                (80, 130, "是否了解调解"), (200, 130, "了解"),
                (80, 170, "是否考虑调解"), (200, 170, "是"),
            ],
        }
        report = audit_pdf(
            self.build_table_pdf([self.bottom_reaching_page(), page_two]),
            copy.deepcopy(POLICY),
        )
        self.assertNotIn(
            "ECG-LAYOUT-COLUMN-GRID", {item["code"] for item in report["issues"]},
        )
        self.assertTrue(report["ok"], report["issues"])

    def test_rendered_landscape_annex_with_other_columns_is_not_flagged(self):
        """横版附件节与纵版主表列位天然不同，方向过滤后不得误报。"""
        annex = {
            "landscape": True,
            "columns": [64.0, 400.0, 780.0],
            "row_lines": [100.0, 140.0, 180.0],
            "texts": [(80, 130, "证据"), (420, 130, "证明内容")],
        }
        report = audit_pdf(
            self.build_table_pdf([self.bottom_reaching_page(), annex]),
            copy.deepcopy(POLICY),
        )
        self.assertTrue(report["ok"], report["issues"])

    def test_rendered_continuation_signature_ignores_deep_segments(self):
        """回归（09-sample 第4→5页真实误报复现）：续接带列位完全对齐，但带内
        一条起点远低于带顶的竖线（09-sample 中 x=177.5，来自后续相邻表格）
        把全带签名污染成 [64.1,177.5,183.3,531.3]，旧逻辑按列漂移误报。
        签名只统计从带顶开始的竖线段后，该形态必须通过。"""
        page_one = {
            "columns": [64.1, 183.3, 531.3],
            "row_lines": [100.0 + 40.0 * step for step in range(18)],  # 100..780 触底
            "texts": [(80, 130, "项目"), (200, 130, "内容"), (80, 170, "张三"),
                      (200, 170, "出借人"), (80, 210, "李四"), (200, 210, "借款人")],
        }
        page_two = {
            # 左右边框长线（64.1/531.3）贯穿全带；续表列边界 183.3 只在顶部行存在；
            # 177.5 是相邻表格竖线，从带顶下方 y=180 才开始（距带顶 80 pt）。
            "columns": [64.1, 531.3],
            "row_lines": [100.0 + 40.0 * step for step in range(18)],  # 100..780
            "partial_verticals": [(183.3, 100.0, 140.0), (177.5, 180.0, 780.0)],
            "texts": [(80, 130, "项目"), (200, 130, "内容"), (80, 170, "王五"), (200, 170, "担保人")],
        }
        report = audit_pdf(
            self.build_table_pdf([page_one, page_two]),
            copy.deepcopy(POLICY),
        )
        self.assertNotIn(
            "ECG-LAYOUT-COLUMN-GRID", {item["code"] for item in report["issues"]},
        )
        self.assertTrue(report["ok"], report["issues"])

    def test_rendered_continuation_with_merged_first_row_passes(self):
        """续页首行为合并单元格：某列边界仅带顶缺失、带下方仍存在，属合法形态。"""
        page_two = {
            "columns": [64.0, 531.28],
            "row_lines": [100.0 + 40.0 * step for step in range(18)],  # 100..780
            "partial_verticals": [(297.64, 180.0, 780.0)],
            "texts": [(80, 130, "项目"), (320, 130, "内容"), (80, 170, "王五"), (320, 170, "担保人")],
        }
        report = audit_pdf(
            self.build_table_pdf([self.bottom_reaching_page(), page_two]),
            copy.deepcopy(POLICY),
        )
        self.assertNotIn(
            "ECG-LAYOUT-COLUMN-GRID", {item["code"] for item in report["issues"]},
        )
        self.assertTrue(report["ok"], report["issues"])

    def test_rendered_refined_row_grid_at_continuation_top_passes(self):
        """上一页为合并行、续页恢复内部网格：只新增列而未移动列，属合法 gridSpan。"""
        page_two = {
            "columns": [64.0, 297.64, 400.0, 531.28],  # 400.0 为带顶新增列
            "row_lines": [100.0, 140.0, 180.0, 220.0],
            "texts": [(80, 130, "项目"), (320, 130, "内容"), (80, 170, "王五"), (320, 170, "担保人")],
        }
        report = audit_pdf(
            self.build_table_pdf([self.bottom_reaching_page(), page_two]),
            copy.deepcopy(POLICY),
        )
        self.assertNotIn(
            "ECG-LAYOUT-COLUMN-GRID", {item["code"] for item in report["issues"]},
        )
        self.assertTrue(report["ok"], report["issues"])

    def test_rendered_24_split_row_refinement_passes(self):
        """24 专利长文本第8→9页：三列合并行续到四列明细行，不是列位漂移。"""
        page_one = {
            "columns": [64.1, 177.5, 531.3],
            "row_lines": [100.0 + 40.0 * step for step in range(18)],
            "texts": [(80, 130, "责任承担"), (200, 130, "停止侵害")],
        }
        page_two = {
            "columns": [64.1, 177.5, 328.2, 531.3],
            "row_lines": [100.0, 140.0, 180.0, 220.0],
            "texts": [(80, 130, "赔偿责任"), (200, 130, "补偿性赔偿")],
        }
        report = audit_pdf(
            self.build_table_pdf([page_one, page_two]),
            copy.deepcopy(POLICY),
        )
        self.assertNotIn(
            "ECG-LAYOUT-COLUMN-GRID", {item["code"] for item in report["issues"]},
        )
        self.assertTrue(report["ok"], report["issues"])

    def test_rendered_outer_table_boundary_drift_is_blocked(self):
        """真漂移反例：跨页后的表格整体右移，左右外边界必须拦截。"""
        page_two = {
            "columns": [84.0, 317.64, 551.28],
            "row_lines": [100.0, 140.0, 180.0, 220.0],
            "texts": [(100, 130, "项目"), (340, 130, "内容"), (100, 170, "王五"), (340, 170, "担保人")],
        }
        report = audit_pdf(
            self.build_table_pdf([self.bottom_reaching_page(), page_two]),
            copy.deepcopy(POLICY),
        )
        self.assertIn("ECG-LAYOUT-COLUMN-GRID", {item["code"] for item in report["issues"]})

    def test_rendered_alternate_gridspan_subset_passes(self):
        """合法近似：相邻行可显示不同内部网格子集，外边界未变化。"""
        page_two = {
            "columns": [64.0, 400.0, 531.28],
            "row_lines": [100.0, 140.0, 180.0, 220.0],
            "texts": [(80, 130, "项目"), (420, 130, "内容"), (80, 170, "王五")],
        }
        report = audit_pdf(
            self.build_table_pdf([self.bottom_reaching_page(), page_two]),
            copy.deepcopy(POLICY),
        )
        self.assertNotIn(
            "ECG-LAYOUT-COLUMN-GRID", {item["code"] for item in report["issues"]},
        )
        self.assertTrue(report["ok"], report["issues"])

    def test_rendered_full_row_merged_continuation_passes(self):
        """回归（24-专利模板第6→7页真实误报复现）：续页为合法整行合并，
        上一页列边界（177.5/328.2）在续页带内完全不出现、只剩左右边框，
        带顶无新 x，不得按列漂移误报。"""
        page_one = {
            "columns": [64.1, 177.5, 328.2, 531.3],
            "row_lines": [100.0 + 40.0 * step for step in range(18)],  # 100..780 触底
            "texts": [(80, 130, "项目"), (200, 130, "内容"), (80, 170, "张三"),
                      (200, 170, "出借人"), (80, 210, "李四"), (200, 210, "借款人")],
        }
        page_two = {
            # 整行合并：只有左右边框；深起点的 300.0 来自下方相邻表格，
            # 不在带顶，不构成新列。
            "columns": [64.1, 531.3],
            "row_lines": [100.0 + 40.0 * step for step in range(18)],
            "partial_verticals": [(300.0, 300.0, 780.0)],
            "texts": [(80, 130, "项目"), (200, 130, "内容"), (80, 170, "王五"), (200, 170, "担保人")],
        }
        report = audit_pdf(
            self.build_table_pdf([page_one, page_two]),
            copy.deepcopy(POLICY),
        )
        self.assertNotIn(
            "ECG-LAYOUT-COLUMN-GRID", {item["code"] for item in report["issues"]},
        )
        self.assertTrue(report["ok"], report["issues"])

    # ---- 跨页重复表头 ----

    def test_rendered_missing_repeated_header_is_blocked(self):
        semantic_policy = {
            **copy.deepcopy(POLICY),
            "semantic_table_headers": {
                "enabled": True,
                "contracts": [{"anchor": "项目", "header_rows": 1}],
            },
        }
        page_two = {
            "columns": [64.0, 297.64, 531.28],
            "row_lines": [100.0, 140.0, 180.0, 220.0],
            "texts": [(80, 130, "王五"), (320, 130, "担保人"), (80, 170, "赵六"), (320, 170, "保证人")],
        }
        report = audit_pdf(
            self.build_table_pdf([self.bottom_reaching_page(), page_two]),
            semantic_policy,
        )
        self.assertIn("ECG-LAYOUT-HEADER-REPEAT", {item["code"] for item in report["issues"]})

    def test_rendered_header_repeat_is_scoped_to_semantic_contract(self):
        """回归（09-sample 真实误报复现）：无表级合同的普通跨页表不检查
        重复表头；同一 PDF 只有在锚点合同明确指向该表时才拦截。"""
        page_two = {
            "columns": [64.0, 297.64, 531.28],
            "row_lines": [100.0, 140.0, 180.0, 220.0],
            "texts": [(80, 130, "王五"), (320, 130, "担保人"), (80, 170, "赵六"), (320, 170, "保证人")],
        }
        pdf = self.build_table_pdf([self.bottom_reaching_page(), page_two])
        unscoped = audit_pdf(pdf, copy.deepcopy(POLICY))
        self.assertNotIn(
            "ECG-LAYOUT-HEADER-REPEAT", {item["code"] for item in unscoped["issues"]},
        )
        scoped_policy = {
            **copy.deepcopy(POLICY),
            "semantic_table_headers": {
                "enabled": True,
                "contracts": [{"anchor": "项目", "header_rows": 1}],
            },
        }
        scoped = audit_pdf(pdf, scoped_policy)
        self.assertIn(
            "ECG-LAYOUT-HEADER-REPEAT", {item["code"] for item in scoped["issues"]},
        )

    # ---- 单元格与段落对齐 ----

    def test_rendered_cell_text_crossing_column_border_is_blocked(self):
        spec = {
            "columns": [64.0, 297.64, 531.28],
            "row_lines": [100.0, 140.0, 180.0],
            "texts": [(80, 130, "项目"), (320, 130, "内容"), (250, 165, "借款合同纠纷")],
        }
        report = audit_pdf(self.build_table_pdf([spec]), copy.deepcopy(POLICY))
        self.assertIn("ECG-LAYOUT-CELL-ALIGN", {item["code"] for item in report["issues"]})

    def test_rendered_merged_cell_text_is_not_flagged(self):
        """合并单元格所在行没有竖线：文字覆盖该列位不算越界。"""
        spec = {
            "columns": [64.0, 531.28],
            "row_lines": [100.0, 140.0, 180.0],
            "partial_verticals": [(297.64, 100.0, 140.0)],
            "texts": [(80, 130, "项目"), (320, 130, "内容"), (250, 165, "合并单元格长文本")],
        }
        report = audit_pdf(self.build_table_pdf([spec]), copy.deepcopy(POLICY))
        self.assertNotIn(
            "ECG-LAYOUT-CELL-ALIGN", {item["code"] for item in report["issues"]},
        )
        self.assertTrue(report["ok"], report["issues"])

    def test_rendered_adjacent_row_border_touch_is_not_text_crossing(self):
        """32/33 第三人意见书波动回归：上一行竖线终点与下一合并行文字
        包围盒只因小数取整轻触，不代表竖线真实贯穿文字所在行。"""
        spec = {
            "columns": [64.0, 531.28],
            "row_lines": [100.0, 140.0, 180.0, 220.0],
            "partial_verticals": [(177.5, 100.0, 140.0)],
            "texts": [(120, 150, "指导性案例、人民法院案例库案例等情况")],
        }
        report = audit_pdf(self.build_table_pdf([spec]), copy.deepcopy(POLICY))
        self.assertNotIn(
            "ECG-LAYOUT-CELL-ALIGN", {item["code"] for item in report["issues"]},
        )
        self.assertTrue(report["ok"], report["issues"])

    def test_rendered_adjacent_zero_padding_cells_are_not_merged_as_crossing(self):
        """左右单元格文字紧贴列线时，PyMuPDF words 会把两侧文字拼接；
        span 级几何仍应识别为两个单元格，而不是越界。"""
        spec = {
            "columns": [64.0, 177.5, 531.28],
            "row_lines": [100.0, 140.0, 180.0],
            "texts": [(133.5, 130, "违约责任")],
            # TextWriter 单独绘制右单元格，保留与左侧不同的 PDF span。
            "writer_text": (177.85, 130, "压力明细长文本"),
        }
        report = audit_pdf(self.build_table_pdf([spec]), copy.deepcopy(POLICY))
        self.assertNotIn(
            "ECG-LAYOUT-CELL-ALIGN", {item["code"] for item in report["issues"]},
        )
        self.assertTrue(report["ok"], report["issues"])

    # ---- 缺字/方框字可见性 ----

    def test_rendered_notdef_glyph_is_blocked(self):
        """TextWriter 强排未分配码位 → 渲染落 .notdef 字形，必须被拦截。"""
        spec = {
            "columns": [64.0, 297.64, 531.28],
            "row_lines": [100.0, 140.0, 180.0],
            "texts": [(80, 130, "项目"), (320, 130, "内容")],
            "writer_text": (80, 250, _NOTDEF_SAMPLE),
        }
        report = audit_pdf(self.build_table_pdf([spec]), copy.deepcopy(POLICY))
        self.assertIn("ECG-LAYOUT-GLYPH", {item["code"] for item in report["issues"]})

    def test_notdef_helper_ignores_space_and_real_glyphs(self):
        class FakePage:
            def get_texttrace(self):
                return [{
                    "font": "FakeFont",
                    "chars": [
                        (0xE000, 0, (0, 0), (0, 0, 1, 1)),   # 私用区 → .notdef 方框字
                        (0x20, 0, (0, 0), (0, 0, 1, 1)),     # 空格的 0 号字形属正常
                        (0x5929, 7, (0, 0), (0, 0, 1, 1)),   # 天 → 真实字形
                    ],
                }]

        self.assertEqual(_notdef_glyphs(FakePage()), [("", "FakeFont")])

    def test_notdef_in_non_embedded_font_is_refuted(self):
        """回归：LibreOffice 默认字体（LinuxLibertineG）以未内嵌资源出现时，
        其 0 号字形会被阅读器回退渲染，不得按方框字误报（真实 E2E 假阳性复现）。"""
        class FakePage:
            def get_texttrace(self):
                return [{
                    "font": "LinuxLibertineG",
                    "chars": [
                        (0x8868, 0, (72, 100), (72, 92, 82, 110)),   # 表 → 0 号字形
                        (0x5934, 1, (82, 100), (82, 92, 92, 110)),   # 头 → 真实字形
                    ],
                }]

            def get_fonts(self):
                # ext 为 n/a：字体未内嵌，阅读器按规范做本地回退
                return [(5, "n/a", "Type0", "LinuxLibertineG", "F1", "Identity-H")]

        self.assertEqual(_notdef_glyphs(FakePage()), [])

    def test_notdef_in_embedded_font_is_blocked(self):
        """内嵌字体里无字体覆盖码位（私用区）的 .notdef 仍必须拦截。"""
        class FakePage:
            def get_texttrace(self):
                return [{
                    "font": "BAAAAA+NotoSansCJK",
                    "chars": [(0xE001, 0, (72, 100), (72, 92, 82, 110))],
                }]

            def get_fonts(self):
                return [(5, "ttf", "Type0", "BAAAAA+NotoSansCJK", "F1", "Identity-H")]

        self.assertEqual(_notdef_glyphs(FakePage()), [("", "BAAAAA+NotoSansCJK")])

    def test_notdef_of_assigned_codepoint_in_embedded_font_is_refuted(self):
        """回归（真实 E2E 假阳性根因）：常用已分配码位（表 U+8868）即使命中
        0 号字形，阅读器也会按码位回退渲染，不呈现方框，不得误报。"""
        class FakePage:
            def get_texttrace(self):
                return [{
                    "font": "BAAAAA+NotoSansCJK",
                    "chars": [(0x8868, 0, (72, 100), (72, 92, 82, 110))],  # 表
                }]

            def get_fonts(self):
                return [(5, "ttf", "Type0", "BAAAAA+NotoSansCJK", "F1", "Identity-H")]

        self.assertEqual(_notdef_glyphs(FakePage()), [])

    def test_notdef_corroborated_by_real_glyph_elsewhere_is_refuted(self):
        """回归：同一字符在同页其他 span 已用非 0 字形渲染 → 可见，
        0 号字形只是字体归属伪影，不得误报。"""
        class FakePage:
            def get_texttrace(self):
                return [
                    {
                        "font": "BAAAAA+NotoSansCJK",
                        "chars": [(0x8868, 0, (72, 100), (72, 92, 82, 110))],
                    },
                    {
                        "font": "CCCCCC+NotoSansCJK",
                        "chars": [(0x8868, 1234, (72, 120), (72, 112, 82, 130))],
                    },
                ]

            def get_fonts(self):
                return [
                    (5, "ttf", "Type0", "BAAAAA+NotoSansCJK", "F1", "Identity-H"),
                    (6, "ttf", "Type0", "CCCCCC+NotoSansCJK", "F2", "Identity-H"),
                ]

        self.assertEqual(_notdef_glyphs(FakePage()), [])


@unittest.skipUnless(importlib.util.find_spec("fitz"), "需要 PyMuPDF")
class TextSurvivalTests(unittest.TestCase):
    """缺字比对：源 DOCX 的中文字符必须在渲染 PDF 中存活。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ecg-layout-survival-test-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make_rendered_pdf(self, lines: list[str]) -> Path:
        import fitz
        path = self.root / "survival.pdf"
        document = fitz.open()
        page = document.new_page(width=595.28, height=841.89)
        y = 100.0
        for line in lines:
            page.insert_text((72, y), line, fontname="china-s", fontsize=11)
            y += 20
        document.save(path)
        document.close()
        return path

    def test_complete_render_passes(self):
        docx = write_docx(self.root)
        pdf = self.make_rendered_pdf(["表头1 表头2", "单元格1 单元格2"])
        report = audit_text_survival(docx, pdf, copy.deepcopy(POLICY))
        self.assertTrue(report["ok"], report["issues"])
        self.assertEqual(report["measurements"]["glyph_survival_ratio"], 1.0)

    def test_dropped_source_text_is_blocked(self):
        docx = write_docx(self.root)
        pdf = self.make_rendered_pdf(["表头1"])
        report = audit_text_survival(docx, pdf, copy.deepcopy(POLICY))
        self.assertFalse(report["ok"])
        self.assertIn("ECG-LAYOUT-GLYPH", {item["code"] for item in report["issues"]})


@unittest.skipUnless(
    _find_soffice() is not None
    and _renderer_kind(_soffice_version(_find_soffice() or "")) == "official",
    "需要正式版 LibreOffice/soffice 做真实渲染（开发构建不暴露系统中文字体）",
)
class LibreOfficeEndToEndTests(unittest.TestCase):
    """真实 LibreOffice 渲染链路：合规终稿必须全绿（DOMAIN_VERIFIED）。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ecg-layout-e2e-test-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_compliant_final_docx_passes_full_render_gate(self):
        path = write_opc_docx(self.root, grid=(3504, 3504), margins=(2449, 2449))
        report = check(path, copy.deepcopy(POLICY), rendered=True)
        self.assertTrue(report["ok"], report["issues"])
        self.assertEqual(report["status"], "DOMAIN_VERIFIED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
