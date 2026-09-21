#!/usr/bin/env python3
"""出版物页码清理与门禁回归（Task-ECG-007）。

法院发放的 24/25 专利基准件残留出版物页码：430/398 为透明背景竖排图片
（word/media/image1.png，经 rId14 以 a:blip 引用），431/399 为旋转 90 度的
VML 文本框，与页脚 PAGE 域构成双页码。覆盖：
- sanitizer 精确清理（VML 431/399 宿主 run、图片 drawing、关系、点名 media），
  不误删附件标题、注释文字、其他文本框与普通正文数字；
- audit_docx 对 sanitizer 漏跑 fail-closed（文本框标记 / 图片关系+哈希）；
- 普通正文中的 431/年份/金额不得误报；
- audit_pdf 页边孤立文本页码（可提取层覆盖 431/399；栅格 430/398 由
  DOCX 关系门禁覆盖，不做 OCR 假称）。
"""
from __future__ import annotations

import hashlib
import importlib.util
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from lxml import etree

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from fill_template import apply_publication_mark_cleanup  # noqa: E402
from layout_gate import (  # noqa: E402
    W,
    audit_docx,
    audit_pdf,
    load_policy,
)

TEMPLATE_25 = SKILL_DIR / "templates" / "25-侵害外观设计专利权纠纷-民事起诉状"
TEMPLATE_24 = SKILL_DIR / "templates" / "24-侵害发明专利权纠纷-民事起诉状"

_RELS_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rIdFooter" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" '
    'Target="footer1.xml"/>'
    '{image_rel}'
    '</Relationships>'
)

_DOCUMENT_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:v="urn:schemas-microsoft-com:vml" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
    '<w:body>'
    '<w:p><w:r><w:t>原告2026年主张赔偿金额500000元，收案编号第431号。</w:t></w:r></w:p>'
    '{vml_run}'
    '{image_run}'
    '<w:p><w:r><w:t>附件 2</w:t></w:r></w:p>'
    '<w:sectPr>'
    '<w:footerReference w:type="default" r:id="rIdFooter"/>'
    '<w:pgSz w:w="11906" w:h="16838"/>'
    '<w:pgMar w:top="400" w:bottom="998" w:left="1418" w:right="1418" w:footer="720"/>'
    '</w:sectPr>'
    '</w:body></w:document>'
)

_VML_RUN = (
    '<w:r><w:pict>'
    '<v:shape style="width:20pt;height:40pt">'
    '<v:textbox><w:txbxContent>'
    '<w:p><w:r><w:t>{vml_text}</w:t></w:r></w:p>'
    '</w:txbxContent></v:textbox></v:shape></w:pict></w:r>'
)

_IMAGE_RUN = (
    '<w:r><w:drawing><wp:inline>'
    '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
    '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
    '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
    '<a:blip r:embed="{rid}"/>'
    '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>'
)

_FOOTER_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r>'
    '<w:fldChar w:fldCharType="begin"/></w:r>'
    '<w:r><w:instrText>PAGE</w:instrText></w:r>'
    '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
    '<w:r><w:t>1</w:t></w:r>'
    '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
    '</w:p></w:ftr>'
)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_publication_docx(
    directory: Path,
    *,
    vml_text: str | None = "431",
    include_image: bool = False,
    image_hash_match: bool = True,
    image_source: Path | None = None,
) -> Path:
    """构造带出版物页码污染的最小 docx；页脚为正常 PAGE 域。"""
    image_rel = ""
    image_run = ""
    media_bytes = None
    if include_image:
        source = image_source or (TEMPLATE_25 / "word" / "media" / "image1.png")
        media_bytes = source.read_bytes()
        image_rel = (
            '<Relationship Id="rId14" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
            'Target="media/image1.png"/>'
        )
        image_run = _IMAGE_RUN.format(rid="rId14")
    vml_run = _VML_RUN.format(vml_text=vml_text) if vml_text else ""

    path = directory / "publication.docx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "word/document.xml", _DOCUMENT_XML.format(vml_run=vml_run, image_run=image_run)
        )
        archive.writestr(
            "word/_rels/document.xml.rels", _RELS_XML.format(image_rel=image_rel)
        )
        archive.writestr("word/footer1.xml", _FOOTER_XML)
        if media_bytes is not None:
            if not image_hash_match:
                media_bytes = b"tampered-not-the-published-pageno-png"
            archive.writestr("word/media/image1.png", media_bytes)
    return path


def publication_policy(**overrides) -> dict:
    section = {
        "enabled": True,
        "forbidden_text_marks": ["431"],
        "forbidden_images": [
            {
                "target": "media/image1.png",
                "sha256": sha256_of(TEMPLATE_25 / "word" / "media" / "image1.png"),
            }
        ],
    }
    policy = {
        "template_name": "publication-fixture",
        "page_numbers": "required",
        "publication_mark_cleanup": section,
        # 模拟 load_policy 对模板段的平铺：audit_pdf 读顶层键
        "forbidden_text_marks": list(section["forbidden_text_marks"]),
    }
    policy.update(overrides)
    return policy


class SanitizerTests(unittest.TestCase):
    """sanitizer 精确清理：真模板树复制体上验证删什么、留什么。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ecg-pubmark-sanitize-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _sanitize_copy(self, template_dir: Path, mark: str) -> tuple[Path, dict]:
        tree = self.root / f"tree-{template_dir.name[:2]}"
        shutil.copytree(template_dir, tree)
        policy = load_policy(SKILL_DIR / "config" / "layout-policy.json", template_dir.name)
        stats = apply_publication_mark_cleanup(tree, policy)
        return tree, stats

    def test_25_template_cleanup(self):
        tree, stats = self._sanitize_copy(TEMPLATE_25, "431")
        self.assertEqual(stats["textboxes_removed"], 1)
        self.assertEqual(stats["images_removed"], 1)
        self.assertEqual(stats["relationships_removed"], 1)
        self.assertEqual(stats["media_removed"], 1)
        doc = etree.parse(str(tree / "word" / "document.xml"))
        vml_texts = [
            "".join(t.text or "" for t in tb.iter(f"{W}t")).strip()
            for tb in doc.iter("{urn:schemas-microsoft-com:vml}textbox")
        ]
        self.assertNotIn("431", vml_texts, "431 文本框必须被删除")
        self.assertTrue(
            any(",所" in t for t in vml_texts), "非页码文本框（律师落款区）不得误删"
        )
        text = "".join(t.text or "" for t in doc.iter(f"{W}t"))
        self.assertIn("附件 2", text, "附件标题不得误删")
        self.assertIn("如有关诉讼案件暂未结案", text, "注释文字不得误删")
        self.assertNotIn("431", text, "出版物页码 431 不应残留")
        rels = etree.parse(str(tree / "word" / "_rels" / "document.xml.rels"))
        self.assertEqual(
            [r for r in rels.getroot() if r.get("Id") == "rId14"], [], "rId14 必须删除"
        )
        media = tree / "word" / "media" / "image1.png"
        self.assertFalse(media.exists(), "被点名且哈希一致的 media 必须删除")

    def test_24_template_cleanup(self):
        tree, stats = self._sanitize_copy(TEMPLATE_24, "399")
        self.assertEqual(stats["textboxes_removed"], 1)
        self.assertEqual(stats["images_removed"], 1)
        self.assertEqual(stats["relationships_removed"], 1)
        self.assertEqual(stats["media_removed"], 1)
        doc = etree.parse(str(tree / "word" / "document.xml"))
        text = "".join(t.text or "" for t in doc.iter(f"{W}t"))
        self.assertNotIn("399", text)
        self.assertIn("附件 3", text)
        self.assertIn("如有关诉讼案件暂未结案", text)
        media = tree / "word" / "media" / "image1.png"
        self.assertFalse(media.exists())

    def test_hash_mismatch_blocks_removal(self):
        """策略点名图片的文件哈希与 sha256 不符时不得删除（模板被替换需人工复核）。"""
        tree = self.root / "tree25"
        shutil.copytree(TEMPLATE_25, tree)
        # 篡改 media 内容使哈希与策略不符
        (tree / "word" / "media" / "image1.png").write_bytes(b"tampered")
        policy = load_policy(SKILL_DIR / "config" / "layout-policy.json", TEMPLATE_25.name)
        stats = apply_publication_mark_cleanup(tree, policy)
        self.assertEqual(stats["images_removed"], 0, "哈希不符不得删图片")
        self.assertEqual(stats["relationships_removed"], 0)
        self.assertEqual(stats["media_removed"], 0)
        self.assertTrue(stats["hash_mismatches"], "哈希不符必须记录")

    def test_original_template_tree_untouched(self):
        """sanitizer 只作用于生成流程的临时树，原始 templates 树不被改动。"""
        before = {}
        for template in (TEMPLATE_24, TEMPLATE_25):
            for f in template.rglob("*"):
                if f.is_file():
                    before[str(f)] = f.read_bytes()
        tree, _ = self._sanitize_copy(TEMPLATE_25, "431")
        self.assertTrue(tree.exists())  # 副本被处理
        for rel_path, content in before.items():
            self.assertEqual(
                Path(rel_path).read_bytes(), content, f"原始模板被改动: {rel_path}"
            )


class DocxGateTests(unittest.TestCase):
    """audit_docx 对出版物页码残留 fail-closed；正常正文不误报。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ecg-pubmark-gate-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_vml_mark_with_normal_footer_is_blocked(self):
        """页脚 PAGE 正常但正文 VML 文本框另有 431：必须失败。"""
        docx = make_publication_docx(self.root, vml_text="431")
        report = audit_docx(docx, publication_policy())
        self.assertFalse(report["ok"])
        self.assertIn(
            "ECG-LAYOUT-PUBLICATION-MARK", {i["code"] for i in report["issues"]}
        )

    def test_forbidden_image_relationship_is_blocked(self):
        """禁止图片关系存在（含哈希一致文件）必须失败。"""
        docx = make_publication_docx(
            self.root, vml_text=None, include_image=True, image_hash_match=True
        )
        report = audit_docx(docx, publication_policy())
        self.assertFalse(report["ok"])
        codes = {i["code"] for i in report["issues"]}
        self.assertIn("ECG-LAYOUT-PUBLICATION-MARK", codes)

    def test_image_hash_mismatch_is_blocked_with_precise_error(self):
        """关系命中但文件哈希与策略不符：失败且报精确错误。"""
        docx = make_publication_docx(
            self.root, vml_text=None, include_image=True, image_hash_match=False
        )
        report = audit_docx(docx, publication_policy())
        self.assertFalse(report["ok"])
        messages = " ".join(i["message"] for i in report["issues"])
        self.assertIn("不符", messages)

    def test_plain_body_431_and_amounts_are_not_flagged(self):
        """普通正文中的 431/年份/金额（非图形文本）不得误报；策略关闭不检查。"""
        docx = make_publication_docx(self.root, vml_text=None, include_image=False)
        report = audit_docx(docx, publication_policy())
        self.assertTrue(report["ok"], report["issues"])
        # 策略关闭（enabled=false）时完全不检查
        bare = publication_policy()
        bare["publication_mark_cleanup"] = {"enabled": False}
        dirty = make_publication_docx(self.root, vml_text="431")
        report2 = audit_docx(dirty, bare)
        codes2 = {i["code"] for i in report2["issues"]}
        self.assertNotIn("ECG-LAYOUT-PUBLICATION-MARK", codes2)

    def test_399_mark_blocked_when_policy_says_so(self):
        """策略文本标记可配置：399 同样按策略拦截（24 号场景）。"""
        policy = publication_policy()
        policy["publication_mark_cleanup"]["forbidden_text_marks"] = ["399"]
        docx = make_publication_docx(self.root, vml_text="399")
        report = audit_docx(docx, policy)
        self.assertFalse(report["ok"])


@unittest.skipUnless(importlib.util.find_spec("fitz"), "需要 PyMuPDF")
class PdfGateTests(unittest.TestCase):
    """渲染层页边孤立文本页码检查（可提取层；栅格由 DOCX 关系门禁覆盖）。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ecg-pubmark-pdf-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make_pdf(self, marks: list[tuple[str, float, float]]) -> Path:
        import fitz

        path = self.root / "pubmark.pdf"
        document = fitz.open()
        page = document.new_page(width=595.28, height=841.89)
        for text, x, y in marks:
            page.insert_text((x, y), text, fontname="china-s", fontsize=10)
        # 正常底部页码
        page.insert_text((293, 790), "8", fontname="helv", fontsize=10)
        document.save(path)
        document.close()
        return path

    def test_left_edge_mark_is_blocked(self):
        pdf = self.make_pdf([("431", 30.0, 300.0)])
        report = audit_pdf(pdf, publication_policy())
        self.assertFalse(report["ok"])
        self.assertIn(
            "ECG-LAYOUT-PUBLICATION-MARK", {i["code"] for i in report["issues"]}
        )

    def test_no_policy_marks_no_publication_issues(self):
        pdf = self.make_pdf([("431", 30.0, 300.0)])
        policy = publication_policy()
        policy["forbidden_text_marks"] = []
        report = audit_pdf(pdf, policy)
        self.assertNotIn(
            "ECG-LAYOUT-PUBLICATION-MARK", {i["code"] for i in report["issues"]}
        )

    def test_center_body_number_is_not_flagged(self):
        """页面中部（非页边带）的相同数字不按出版物页码处理。"""
        pdf = self.make_pdf([("431", 250.0, 300.0)])
        report = audit_pdf(pdf, publication_policy())
        self.assertNotIn(
            "ECG-LAYOUT-PUBLICATION-MARK", {i["code"] for i in report["issues"]}
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
