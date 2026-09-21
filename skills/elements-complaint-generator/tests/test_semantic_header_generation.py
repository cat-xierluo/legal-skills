#!/usr/bin/env python3
"""表级表头合同（semantic_table_headers）生成回归。

24/25 专利基准件的「关联民事案件信息表」横跨多页，表头由三行构成
（表题行/专利信息行/栏目标题行）；Word/LibreOffice 仅在自首行起连续各行
都声明 tblHeader 时才在续页重复整块表头。覆盖：
- 合同配置装载：24/25 有合同（anchor/header_rows=3），09 无合同；
- 正向：真模板树复制体上为首部连续 3 行补写 w:tblHeader，数据行不受影响，
  trPr 子元素顺序符合 CT_TrPr schema，重复执行幂等；
- 反向 fail-closed：找不到锚点、重复命中、锚点不在首行、行数不足、
  锚点落在表格外段落，均报错且不写任何行；
- 无合同模板（09）零改动，原始 templates 树绝不改动。
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from lxml import etree

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from fill_template import apply_semantic_table_headers  # noqa: E402
from layout_gate import W, load_policy  # noqa: E402

TEMPLATE_24 = SKILL_DIR / "templates" / "24-侵害发明专利权纠纷-民事起诉状"
TEMPLATE_25 = SKILL_DIR / "templates" / "25-侵害外观设计专利权纠纷-民事起诉状"
TEMPLATE_09 = SKILL_DIR / "templates" / "09-民间借贷纠纷-民事起诉状"
POLICY_PATH = SKILL_DIR / "config" / "layout-policy.json"
ANCHOR = "关联民事案件信息表"

_DOCUMENT_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:body>{tables}{trailing_paragraph}'
    '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>'
    '</w:body></w:document>'
)


def _paragraph(text: str) -> str:
    return f'<w:p><w:r><w:t>{text}</w:t></w:r></w:p>'


def _table(row_texts: list[str], *, first_row_trpr: str = "") -> str:
    rows = []
    for index, text in enumerate(row_texts):
        trpr = first_row_trpr if index == 0 else ""
        rows.append(
            f'<w:tr>{trpr}<w:tc><w:tcPr/><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:tc></w:tr>'
        )
    return f'<w:tbl><w:tblPr/><w:tblGrid><w:gridCol w:w="8000"/></w:tblGrid>{"".join(rows)}</w:tbl>'


def make_document(directory: Path, *, tables: list[str], trailing_paragraph: str = "") -> Path:
    """构造最小 OOXML 树：apply_semantic_table_headers 只依赖 word/document.xml。"""
    tree = directory / "tree"
    (tree / "word").mkdir(parents=True)
    (tree / "word" / "document.xml").write_text(
        _DOCUMENT_XML.format(
            tables="".join(tables),
            trailing_paragraph=(
                _paragraph(trailing_paragraph) if trailing_paragraph else ""
            ),
        ),
        encoding="utf-8",
    )
    return tree


def header_policy(**overrides) -> dict:
    policy = {
        "template_name": "fixture",
        "semantic_table_headers": {
            "enabled": True,
            "contracts": [{"anchor": ANCHOR, "header_rows": 3}],
        },
    }
    policy.update(overrides)
    return policy


def _tbl_header_flags(tree: Path) -> list[list[bool]]:
    """按表返回各行 tblHeader 声明状态（用于断言首部连续行）。"""
    doc = etree.parse(str(tree / "word" / "document.xml"))
    flags = []
    for tbl in doc.iter(f"{W}tbl"):
        flags.append([
            row.find(f"./{W}trPr/{W}tblHeader") is not None
            for row in tbl.findall(f"./{W}tr")
        ])
    return flags


class PolicyWiringTests(unittest.TestCase):
    """config 合同装载：24/25 有合同，09 无合同。"""

    def test_24_and_25_have_contract(self):
        for name in (TEMPLATE_24.name, TEMPLATE_25.name):
            policy = load_policy(POLICY_PATH, name)
            section = policy.get("semantic_table_headers") or {}
            self.assertTrue(section.get("enabled"), name)
            self.assertEqual(
                section.get("contracts"),
                [{"anchor": ANCHOR, "header_rows": 3}],
                name,
            )

    def test_09_has_no_contract(self):
        for name in (TEMPLATE_09.name, "09-民间借贷纠纷-民事答辩状"):
            policy = load_policy(POLICY_PATH, name)
            self.assertIsNone(
                policy.get("semantic_table_headers"),
                f"{name} 不应配置表级表头合同",
            )


class RealTemplateTests(unittest.TestCase):
    """正向：真模板树复制体上按合同补写首部连续 3 行。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ecg-semhdr-real-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _apply_on_copy(self, template_dir: Path) -> tuple[Path, dict]:
        tree = self.root / f"tree-{template_dir.name[:2]}"
        shutil.copytree(template_dir, tree)
        policy = load_policy(POLICY_PATH, template_dir.name)
        stats = apply_semantic_table_headers(tree, policy)
        return tree, stats

    def test_anchor_table_first_three_rows_marked(self):
        for template in (TEMPLATE_24, TEMPLATE_25):
            with self.subTest(template=template.name):
                tree, stats = self._apply_on_copy(template)
                self.assertEqual(stats["errors"], [])
                self.assertEqual(stats["contracts_applied"], 1)
                self.assertEqual(stats["rows_marked"], 3)
                doc = etree.parse(str(tree / "word" / "document.xml"))
                target = None
                for tbl in doc.iter(f"{W}tbl"):
                    rows = tbl.findall(f"./{W}tr")
                    texts = [
                        "".join(t.text or "" for t in r.iter(f"{W}t"))
                        for r in rows
                    ]
                    if any(ANCHOR in t for t in texts):
                        target = (rows, texts)
                        break
                self.assertIsNotNone(target, "目标表必须存在")
                rows, texts = target
                self.assertIn(ANCHOR, texts[0], "锚点必须落在目标表首行")
                flags = [
                    r.find(f"./{W}trPr/{W}tblHeader") is not None for r in rows
                ]
                self.assertEqual(
                    flags, [True, True, True, False, False, False, False, False],
                    "仅首部连续 3 行声明 tblHeader，数据行不受影响",
                )

    def test_trpr_child_order_remains_schema_valid(self):
        """tblHeader 必须位于 cantSplit/trHeight 之后（CT_TrPr schema 顺序）。"""
        tree, _ = self._apply_on_copy(TEMPLATE_25)
        doc = etree.parse(str(tree / "word" / "document.xml"))
        for tbl in doc.iter(f"{W}tbl"):
            for row in tbl.findall(f"./{W}tr"):
                trpr = row.find(f"./{W}trPr")
                if trpr is None or trpr.find(f"./{W}tblHeader") is None:
                    continue
                names = [child.tag.split("}")[1] for child in trpr]
                self.assertLess(
                    names.index("tblHeader"),
                    min(
                        (names.index(n) for n in ("tblCellSpacing", "jc", "hidden") if n in names),
                        default=len(names),
                    ),
                    f"trPr 子元素顺序违反 schema: {names}",
                )

    def test_apply_is_idempotent(self):
        tree, first = self._apply_on_copy(TEMPLATE_25)
        self.assertEqual(first["rows_marked"], 3)
        before = (tree / "word" / "document.xml").read_bytes()
        policy = load_policy(POLICY_PATH, TEMPLATE_25.name)
        second = apply_semantic_table_headers(tree, policy)
        self.assertEqual(second["errors"], [])
        self.assertEqual(second["rows_marked"], 0, "已声明的行不得重复写入")
        self.assertEqual(
            (tree / "word" / "document.xml").read_bytes(),
            before,
            "幂等重跑不得改写 document.xml",
        )

    def test_original_template_tree_untouched(self):
        before = {}
        for template in (TEMPLATE_24, TEMPLATE_25, TEMPLATE_09):
            for f in template.rglob("*"):
                if f.is_file():
                    before[str(f)] = f.read_bytes()
        self._apply_on_copy(TEMPLATE_25)
        for rel_path, content in before.items():
            self.assertEqual(
                Path(rel_path).read_bytes(), content, f"原始模板被改动: {rel_path}"
            )


class FailClosedTests(unittest.TestCase):
    """反向：定位失败一律报错，不做部分写入。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ecg-semhdr-fail-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _apply(self, tree: Path, policy: dict | None = None) -> dict:
        return apply_semantic_table_headers(tree, policy or header_policy())

    def test_anchor_missing_is_blocked(self):
        tree = make_document(
            self.root, tables=[_table(["其他表格", "数据行", "数据行", "数据行"])]
        )
        before = (tree / "word" / "document.xml").read_bytes()
        stats = self._apply(tree)
        self.assertEqual(len(stats["errors"]), 1)
        self.assertIn("未命中", stats["errors"][0])
        self.assertEqual(stats["rows_marked"], 0)
        self.assertEqual((tree / "word" / "document.xml").read_bytes(), before)

    def test_duplicate_hits_are_blocked(self):
        tree = make_document(
            self.root,
            tables=[
                _table([ANCHOR, "数据行", "数据行", "数据行"]),
                _table([ANCHOR, "数据行", "数据行", "数据行"]),
            ],
        )
        before = (tree / "word" / "document.xml").read_bytes()
        stats = self._apply(tree)
        self.assertEqual(len(stats["errors"]), 1)
        self.assertIn("重复命中", stats["errors"][0])
        self.assertEqual(stats["rows_marked"], 0)
        self.assertEqual(_tbl_header_flags(tree), [[False] * 4, [False] * 4])
        self.assertEqual((tree / "word" / "document.xml").read_bytes(), before)

    def test_anchor_not_in_first_row_is_blocked(self):
        tree = make_document(
            self.root,
            tables=[_table(["说明行", ANCHOR, "数据行", "数据行", "数据行"])],
        )
        before = (tree / "word" / "document.xml").read_bytes()
        stats = self._apply(tree)
        self.assertEqual(len(stats["errors"]), 1)
        self.assertIn("不在首行", stats["errors"][0])
        self.assertEqual(_tbl_header_flags(tree), [[False] * 5])
        self.assertEqual((tree / "word" / "document.xml").read_bytes(), before)

    def test_insufficient_rows_are_blocked(self):
        tree = make_document(
            self.root, tables=[_table([ANCHOR, "数据行"])]
        )
        before = (tree / "word" / "document.xml").read_bytes()
        stats = self._apply(tree)
        self.assertEqual(len(stats["errors"]), 1)
        self.assertIn("不足", stats["errors"][0])
        self.assertEqual(_tbl_header_flags(tree), [[False] * 2])
        self.assertEqual((tree / "word" / "document.xml").read_bytes(), before)

    def test_anchor_outside_table_is_blocked(self):
        tree = make_document(self.root, tables=[], trailing_paragraph=ANCHOR)
        stats = self._apply(tree)
        self.assertEqual(len(stats["errors"]), 1)
        self.assertIn("表格外", stats["errors"][0])
        self.assertEqual(stats["rows_marked"], 0)

    def test_exact_three_rows_satisfy_contract(self):
        """恰好 header_rows 行视为行数充足（边界正向）。"""
        tree = make_document(
            self.root, tables=[_table([ANCHOR, "栏目标题", "数据行"])]
        )
        stats = self._apply(tree)
        self.assertEqual(stats["errors"], [])
        self.assertEqual(stats["rows_marked"], 3)
        self.assertEqual(_tbl_header_flags(tree), [[True, True, True]])

    def test_no_contract_is_noop(self):
        """无合同（09 场景）：文档零改动。"""
        tree = make_document(
            self.root, tables=[_table([ANCHOR, "数据行", "数据行", "数据行"])]
        )
        before = (tree / "word" / "document.xml").read_bytes()
        stats = self._apply(tree, policy={"template_name": "fixture-09"})
        self.assertEqual(stats, {"contracts_applied": 0, "rows_marked": 0, "errors": []})
        self.assertEqual((tree / "word" / "document.xml").read_bytes(), before)

    def test_disabled_contract_is_noop(self):
        tree = make_document(
            self.root, tables=[_table([ANCHOR, "数据行", "数据行", "数据行"])]
        )
        before = (tree / "word" / "document.xml").read_bytes()
        policy = header_policy()
        policy["semantic_table_headers"]["enabled"] = False
        stats = self._apply(tree, policy=policy)
        self.assertEqual(stats["rows_marked"], 0)
        self.assertEqual((tree / "word" / "document.xml").read_bytes(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
