#!/usr/bin/env python3
"""fill_template 输出完整性回归：批处理旗标透传、原子发布、失败不发布。

覆盖四条要求：
1. 批处理模式把 --templates-dir / --verify-residual 完整透传给单件渲染；
2. 未知/错位业务字段路径默认拒绝，路径级 Schema 防层级错位（详见
   test_fail_closed.py）；
3. 失败不发布、不覆盖已有产物；
4. 成功时经输出同目录临时文件原子替换，不留临时残片。
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPT = SKILL_DIR / "scripts/fill_template.py"
SAMPLE = SKILL_DIR / "tests/fixtures/09-private-lending-sample.json"
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import fill_template as _ft


def _run(*cli: str, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *cli],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _write_batch_input(batch_dir: Path) -> Path:
    """批处理入口要求 *-elements.json 命名且文件内含 case_type。"""
    raw = json.loads(SAMPLE.read_text(encoding="utf-8"))
    path = batch_dir / "09-a-elements.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


def _assert_valid_docx(self, path: Path):
    self.assertTrue(path.exists(), f"缺少产物 {path}")
    self.assertTrue(zipfile.is_zipfile(path), f"产物不是合法 zip/docx: {path}")
    with zipfile.ZipFile(path) as archive:
        self.assertIn("word/document.xml", archive.namelist())


class AtomicPublishTests(unittest.TestCase):
    def test_success_atomically_replaces_existing_output(self):
        """成功渲染：已有输出被合法 docx 原子替换，目录无临时文件残片。"""
        sentinel = b"stale-previous-output\n"
        with tempfile.TemporaryDirectory(prefix="ecg-atomic-") as directory:
            work = Path(directory)
            output = work / "out.docx"
            output.write_bytes(sentinel)
            result = _run(
                "--case-type", "09-private-lending",
                "--elements", str(SAMPLE),
                "--output", str(output),
                "--layout-check", "docx",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotEqual(output.read_bytes(), sentinel)
            _assert_valid_docx(self, output)
            # 原子替换后输出目录只应有正式产物本身（无 .publish/.tmp 残片）
            self.assertEqual([p.name for p in work.iterdir()], ["out.docx"])

    def test_existing_legal_call_remains_compatible(self):
        """既有合法调用保持兼容：默认旗标单件渲染 + md 抽取回路均可发布。"""
        with tempfile.TemporaryDirectory(prefix="ecg-compat-") as directory:
            work = Path(directory)
            output = work / "plain.docx"
            result = _run(
                "--case-type", "09-private-lending",
                "--elements", str(SAMPLE),
                "--output", str(output),
                "--layout-check", "docx",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            _assert_valid_docx(self, output)
            # extract_from_markdown → fill_template 抽取回路（09/05 两案由）
            for ct, md in (
                ("09-private-lending", "09-private-lending-complaint.md"),
                ("05-divorce", "05-divorce-complaint.md"),
            ):
                elements = work / f"{ct}-e2e-elements.json"
                extracted = subprocess.run(
                    [
                        sys.executable, "-B",
                        str(SKILL_DIR / "scripts/extract_from_markdown.py"),
                        "--case-type", ct,
                        "--input", str(SKILL_DIR / "tests/fixtures" / md),
                        "--output", str(elements),
                    ],
                    capture_output=True, text=True, timeout=60, check=False,
                )
                self.assertEqual(extracted.returncode, 0, extracted.stderr)
                render = _run(
                    "--case-type", ct,
                    "--elements", str(elements),
                    "--output", str(work / f"{ct}-e2e.docx"),
                    "--layout-check", "docx",
                )
                self.assertEqual(render.returncode, 0, render.stdout + render.stderr)


class AttachmentPaginationTests(unittest.TestCase):
    def test_25_keeps_official_attachment_section_without_extra_break(self):
        """25 号正文自然铺满页时，删除附件前 next-page 节再补硬分页会额外
        制造空白页；应保留官方节边界，且不再给附件标题叠加分页。"""
        template = SKILL_DIR / "templates/25-侵害外观设计专利权纠纷-民事起诉状"
        parts = _ft.load_text_parts(template)
        first = _ft.merge_sections_and_normalize(parts)
        self.assertEqual(first["page_breaks_added"], 0)

        namespace = "{%s}" % _ft.W_NS
        document = parts["word/document.xml"].getroot()
        attachment = None
        for paragraph in document.iter(namespace + "p"):
            text = "".join(node.text or "" for node in paragraph.iter(namespace + "t")).strip()
            if text == "附件 1":
                attachment = paragraph
                break
        self.assertIsNotNone(attachment)
        self.assertIsNone(attachment.find(f"./{namespace}pPr/{namespace}pageBreakBefore"))
        self.assertIsNone(
            attachment.find(f".//{namespace}br[@{namespace}type='page']")
        )

        body = document.find(namespace + "body")
        children = list(body)
        attachment_index = children.index(attachment)
        previous_section = None
        for previous in reversed(children[:attachment_index]):
            previous_section = previous.find(f".//{namespace}sectPr")
            if previous_section is not None:
                break
            text = "".join(node.text or "" for node in previous.iter(namespace + "t")).strip()
            self.assertFalse(text, "附件标题前只允许跨过空段落查找节边界")
        self.assertIsNotNone(previous_section, "官方附件前 next-page 节必须保留")

        second = _ft.merge_sections_and_normalize(parts)
        self.assertEqual(second["page_breaks_added"], 0)

    def test_61_removes_trailing_same_orientation_book_section(self):
        """61 号模板的独立空段落 next-page 分节在前表恰好铺满时会独占
        一页；应移除冗余同方向书册节，并让后续表格按实际剩余空间自然续排。"""
        template = (
            SKILL_DIR
            / "templates/61-暂时解除乘坐飞机、高铁限制措施申请-暂时解除乘坐飞机、高铁限制措施申请书"
        )
        parts = _ft.load_text_parts(template)
        first = _ft.merge_sections_and_normalize(parts)
        self.assertEqual(first["sections_removed"], 1)
        self.assertEqual(first["page_breaks_added"], 0)

        namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        body = parts["word/document.xml"].getroot().find(f"{namespace}body")
        self.assertIsNotNone(body)
        paragraph_sections = body.findall(f"./{namespace}p/{namespace}pPr/{namespace}sectPr")
        self.assertEqual(paragraph_sections, [])
        page_break_before = body.findall(
            f"./{namespace}p/{namespace}pPr/{namespace}pageBreakBefore"
        )
        self.assertEqual(page_break_before, [])

        second = _ft.merge_sections_and_normalize(parts)
        self.assertEqual(second["sections_removed"], 0)
        self.assertEqual(second["page_breaks_added"], 0)

    def test_62_removes_only_semantically_empty_trailing_paragraphs(self):
        """删除末尾同方向节后，不得让空承载段落溢出成只含页码的尾页。"""
        template = SKILL_DIR / "templates/62-参与分配申请书-参与分配申请"
        parts = _ft.load_text_parts(template)
        first = _ft.merge_sections_and_normalize(parts)
        self.assertEqual(first["sections_removed"], 3)
        self.assertEqual(first["trailing_empty_paragraphs_removed"], 2)

        namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        body = parts["word/document.xml"].getroot().find(f"{namespace}body")
        self.assertIsNotNone(body)
        self.assertEqual(body[-1].tag, f"{namespace}sectPr")
        tail_text = "".join(
            node.text or "" for node in body[-2].iter(f"{namespace}t")
        ).strip()
        self.assertTrue(tail_text)

        second = _ft.merge_sections_and_normalize(parts)
        self.assertEqual(second["trailing_empty_paragraphs_removed"], 0)

    def test_28_promotes_terminal_attachment_section_without_blank_tail(self):
        """28 号附件后的空分节不得产生只有页码的末页；附件节属性应提升
        为最终 body 节属性，避免删除后改变附件页边距和页脚。"""
        template = SKILL_DIR / "templates/28-技术合同纠纷-民事起诉状"
        parts = _ft.load_text_parts(template)
        namespace = "{%s}" % _ft.W_NS
        original_body = parts["word/document.xml"].getroot().find(f"{namespace}body")
        terminal_paragraph = next(
            paragraph for paragraph in reversed(original_body.findall(f"./{namespace}p"))
            if paragraph.find(f"./{namespace}pPr/{namespace}sectPr") is not None
        )
        original_terminal_section = terminal_paragraph.find(
            f"./{namespace}pPr/{namespace}sectPr"
        )
        first = _ft.merge_sections_and_normalize(parts)

        body = parts["word/document.xml"].getroot().find(f"{namespace}body")
        self.assertIsNotNone(body)
        self.assertEqual(body[-1].tag, f"{namespace}sectPr")
        def section_signature(section):
            return [
                (
                    _ft.etree.QName(node).localname,
                    sorted(
                        (_ft.etree.QName(name).localname, value)
                        for name, value in node.attrib.items()
                    ),
                )
                for node in section.iter()
            ]
        self.assertEqual(
            section_signature(body[-1]), section_signature(original_terminal_section)
        )
        self.assertIsNone(body[-2].find(f"./{namespace}pPr/{namespace}sectPr"))
        self.assertGreaterEqual(first["trailing_empty_paragraphs_removed"], 1)

        second = _ft.merge_sections_and_normalize(parts)
        self.assertEqual(second["trailing_empty_paragraphs_removed"], 0)

    def test_terminal_section_with_bookmark_is_not_promoted_or_deleted(self):
        template = SKILL_DIR / "templates/28-技术合同纠纷-民事起诉状"
        parts = _ft.load_text_parts(template)
        namespace = "{%s}" % _ft.W_NS
        body = parts["word/document.xml"].getroot().find(f"{namespace}body")
        terminal_paragraph = next(
            paragraph for paragraph in reversed(body.findall(f"./{namespace}p"))
            if paragraph.find(f"./{namespace}pPr/{namespace}sectPr") is not None
        )
        bookmark = _ft.etree.Element(f"{namespace}bookmarkStart")
        bookmark.set(f"{namespace}id", "999")
        bookmark.set(f"{namespace}name", "terminal-marker")
        terminal_paragraph.append(bookmark)

        stats = _ft.merge_sections_and_normalize(parts)

        self.assertIsNotNone(
            body.find(f".//{namespace}bookmarkStart[@{namespace}name='terminal-marker']")
        )
        self.assertIsNotNone(
            terminal_paragraph.find(f"./{namespace}pPr/{namespace}sectPr")
        )
        # 末尾另一个纯空段仍可清理，但带书签的分节段本身必须保留。
        self.assertGreaterEqual(stats["trailing_empty_paragraphs_removed"], 1)


class LongTextCapacityTests(unittest.TestCase):
    def test_long_replacement_removes_only_direct_right_indent(self):
        namespace = "{%s}" % _ft.W_NS
        paragraph = _ft.etree.fromstring(
            f'<w:p xmlns:w="{_ft.W_NS}"><w:pPr><w:ind w:left="83" '
            f'w:right="5554" w:rightChars="400"/></w:pPr><w:r><w:t>具体赔偿请求：</w:t>'
            f'</w:r></w:p>'
        )
        doc = _ft.DocParts({"word/document.xml": _ft.etree.ElementTree(paragraph)})
        rule = _ft.make_text_replace_rule("请求", "具体赔偿请求：")
        self.assertTrue(rule(doc, {"请求": "长" * 100}))
        indent = paragraph.find(f"./{namespace}pPr/{namespace}ind")
        self.assertEqual(indent.get(f"{namespace}left"), "83")
        self.assertIsNone(indent.get(f"{namespace}right"))
        self.assertIsNone(indent.get(f"{namespace}rightChars"))

    def test_short_replacement_preserves_template_right_indent(self):
        namespace = "{%s}" % _ft.W_NS
        paragraph = _ft.etree.fromstring(
            f'<w:p xmlns:w="{_ft.W_NS}"><w:pPr><w:ind w:right="5554"/></w:pPr>'
            f'<w:r><w:t>金额：</w:t></w:r></w:p>'
        )
        doc = _ft.DocParts({"word/document.xml": _ft.etree.ElementTree(paragraph)})
        rule = _ft.make_text_replace_rule("金额", "金额：")
        self.assertTrue(rule(doc, {"金额": "100元"}))
        indent = paragraph.find(f"./{namespace}pPr/{namespace}ind")
        self.assertEqual(indent.get(f"{namespace}right"), "5554")

    def test_long_fill_removes_direct_right_indent(self):
        namespace = "{%s}" % _ft.W_NS
        paragraph = _ft.etree.fromstring(
            f'<w:p xmlns:w="{_ft.W_NS}"><w:pPr><w:ind w:right="5554"/>'
            f'</w:pPr><w:r><w:t>事实：</w:t></w:r><w:r><w:t>    </w:t></w:r>'
            f'<w:r><w:t>证据：</w:t></w:r></w:p>'
        )
        doc = _ft.DocParts({"word/document.xml": _ft.etree.ElementTree(paragraph)})
        rule = _ft.make_text_fill_rule("事实", "事实：", "证据：")
        self.assertTrue(rule(doc, {"事实": "长" * 100}))
        indent = paragraph.find(f"./{namespace}pPr/{namespace}ind")
        self.assertIsNone(indent.get(f"{namespace}right"))

    def test_long_row_threshold_comes_from_policy(self):
        namespace = "{%s}" % _ft.W_NS
        document = _ft.etree.fromstring(
            f'<w:document xmlns:w="{_ft.W_NS}"><w:body><w:tbl><w:tr><w:trPr>'
            f'<w:cantSplit/></w:trPr><w:tc><w:p><w:r><w:t>{"长" * 12}</w:t>'
            f'</w:r></w:p></w:tc></w:tr><w:tblPr/><w:tblGrid><w:gridCol w:w="100"/>'
            f'</w:tblGrid></w:tbl><w:sectPr/></w:body></w:document>'
        )
        paragraph = _ft.Para(document.find(f".//{namespace}p"))
        _ft._mark_row_splittable(paragraph)
        parts = {"word/document.xml": _ft.etree.ElementTree(document)}
        stats = _ft.merge_sections_and_normalize(
            parts, {"long_row_split_min_chars": 10}
        )
        self.assertEqual(stats["long_rows_split_enabled"], 1)
        cant_split = document.find(f".//{namespace}cantSplit")
        self.assertIsNotNone(cant_split)
        self.assertEqual(cant_split.get(f"{namespace}val"), "0")


class BatchPassThroughTests(unittest.TestCase):
    def test_batch_passes_templates_dir_through(self):
        """--templates-dir 必须透传：伪目录应导致单件渲染失败而非静默用默认值。"""
        with tempfile.TemporaryDirectory(prefix="ecg-batch-") as directory:
            work = Path(directory)
            batch_dir = work / "batch"
            batch_dir.mkdir()
            _write_batch_input(batch_dir)
            out_dir = work / "out"
            result = _run(
                "--batch", str(batch_dir),
                "--output", str(out_dir),
                "--templates-dir", "/nonexistent-ecg-templates-xyz",
                "--layout-check", "docx",
            )
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("模板树不存在", result.stdout + result.stderr)
            self.assertFalse(any(out_dir.glob("*")), "失败批次不得发布任何产物")

    def test_batch_passes_verify_residual_through(self):
        """--verify-residual 必须透传：命中残留串应阻断整批；无害串应放行。"""
        with tempfile.TemporaryDirectory(prefix="ecg-batch-") as directory:
            work = Path(directory)
            batch_dir = work / "batch"
            batch_dir.mkdir()
            _write_batch_input(batch_dir)
            blocked_dir = work / "blocked"
            blocked = _run(
                "--batch", str(batch_dir),
                "--output", str(blocked_dir),
                "--verify-residual", "民事起诉状",
                "--layout-check", "docx",
            )
            self.assertNotEqual(blocked.returncode, 0, blocked.stdout + blocked.stderr)
            self.assertIn("旧串仍存在", blocked.stdout + blocked.stderr)
            self.assertFalse(any(blocked_dir.glob("*")), "残留校验失败不得发布产物")
            # 无害残留串 + 非默认模板目录（软链）→ 全批通过
            good_dir = work / "good"
            linked_templates = work / "linked-templates"
            linked_templates.symlink_to(SKILL_DIR / "templates", target_is_directory=True)
            good = _run(
                "--batch", str(batch_dir),
                "--output", str(good_dir),
                "--templates-dir", str(linked_templates),
                "--verify-residual", "绝不存在的残留串ECG",
                "--layout-check", "docx",
            )
            self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
            published = list(good_dir.glob("*-要素式起诉状.docx"))
            self.assertEqual(len(published), 1)
            _assert_valid_docx(self, published[0])

    def test_batch_failure_preserves_existing_output(self):
        """批内失败：已有同名正式产物不被覆盖、不留临时文件。"""
        sentinel = b"existing-user-output\n"
        with tempfile.TemporaryDirectory(prefix="ecg-batch-") as directory:
            work = Path(directory)
            batch_dir = work / "batch"
            batch_dir.mkdir()
            _write_batch_input(batch_dir)
            out_dir = work / "out"
            out_dir.mkdir()
            output = out_dir / "09-a-要素式起诉状.docx"
            output.write_bytes(sentinel)
            result = _run(
                "--batch", str(batch_dir),
                "--output", str(out_dir),
                "--verify-residual", "民事起诉状",
                "--layout-check", "docx",
            )
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(output.read_bytes(), sentinel)
            self.assertEqual([p.name for p in out_dir.iterdir()], [output.name])


class SchemaGateTests(unittest.TestCase):
    """路径级 Schema（find_unknown_fields）单元回归：层级精确、空值语义、自由容器。"""

    def test_free_form_containers_and_legal_list_paths_accepted(self):
        """勾选/填空/标签自由锚与合法列表路径不得误报。"""
        elements = {
            "勾选": {"全新锚文本□": "全新选项", "另一个锚": ["选项一", "选项二"]},
            "填空": {"9. 全新编号标题": "内容", "3. 医疗费": "5000 元"},
            "标签": {"全新唯一标签": "值"},
            "当事人": {
                "原告": {"姓名": "张三", "名称": "某公司", "统一社会信用代码": "9111X"},
                "委托诉讼代理人": [
                    {"姓名": "李律师", "单位": "某律所", "特别授权": True},
                    {"姓名": "王律师", "联系电话": "123"},
                ],
            },
            "对纠纷解决方式的意愿": {
                "是否了解调解": "了解",
                "是否了解先行调解好处": ["了解"] * 5,
                "是否考虑先行调解": "是",
            },
        }
        self.assertEqual(_ft.find_unknown_fields(elements), [])

    def test_misplaced_and_unknown_paths_rejected(self):
        """同名字段错层级、未知路径（含嵌套未知分组）必须整路径报出。"""
        self.assertEqual(
            _ft.find_unknown_fields({"诉讼请求": {"姓名": "张三"}}),
            ["诉讼请求.姓名"],
        )
        self.assertEqual(
            _ft.find_unknown_fields({"当事人": {"原告X": {"姓名": "张三"}}}),
            ["当事人.原告X.姓名"],
        )
        self.assertEqual(
            _ft.find_unknown_fields({"当事人": {"原告": {"工作单位": {"名称": "某公司"}}}}),
            ["当事人.原告.工作单位.名称"],
        )

    def test_falsy_unknown_rejected_and_empty_accepted(self):
        """仅 None/空字符串/空容器按空值放行；未知 false/0 不得逃逸。"""
        self.assertEqual(
            _ft.find_unknown_fields({"诉讼请求": {"神秘开关": False}}),
            ["诉讼请求.神秘开关"],
        )
        self.assertEqual(
            _ft.find_unknown_fields({"诉讼请求": {"神秘计数": 0}}),
            ["诉讼请求.神秘计数"],
        )
        self.assertEqual(
            _ft.find_unknown_fields({
                "诉讼请求": {"其他请求": "", "明细": None, "神秘组": {}, "神秘列表": []},
                "当事人": {"原告": {"职务": ""}},
            }),
            [],
        )
        # 合法路径上的 false 不误报
        self.assertEqual(
            _ft.find_unknown_fields({"诉讼请求": {"是否主张诉讼费用": False}}),
            [],
        )

    def test_schema_covers_all_fixtures(self):
        """漂移守卫：bundled fixtures 的全部业务叶路径必须被 Schema 覆盖。

        新增样例字段而未登记 KNOWN_PATH_PATTERNS 时，本用例失败以提示同步。
        """
        fixtures_dir = SKILL_DIR / "tests/fixtures"
        for fixture in sorted(fixtures_dir.glob("*.json")):
            raw = json.loads(fixture.read_text(encoding="utf-8"))
            elements = raw.get("elements") if isinstance(raw.get("elements"), dict) else raw
            self.assertEqual(
                _ft.find_unknown_fields(elements),
                [],
                f"{fixture.name} 存在未登记路径 Schema 的业务字段",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
