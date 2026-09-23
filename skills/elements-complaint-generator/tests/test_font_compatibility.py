#!/usr/bin/env python3
"""中文字体兼容回归（09-sample 真实故障复现）。

故障链：官方模板 rFonts 全部指向 方正书宋_GBK/方正大标宋_GBK 等商业字体，
fontTable 中 方正书宋_GBK 的 altName=Arial Unicode MS。在缺少这些精确字体名
的 LibreOffice+fontconfig 环境（如部分 Linux/无方正字体的 mac），Arial Unicode MS
同样缺失，fontconfig 把陌生家族名连锁模糊错配到无中文字形的拉丁字体
（基线验证环境实测 Verdana），09-sample 六页大量中文标签/姓名渲染为空白，
字形存活率 0.979、缺失 53 个去重字符。

修复：fill_template.apply_font_compatibility 按 config/layout-policy.json 的
font_compatibility 段，把最终 OOXML 中 rFonts 的 eastAsia 引用重写为通用
中文字体名（ascii/hAnsi/cs 同步改写，字号、加粗等其余属性一律不动，
标题/正文/落款的字号与段落层级保留），并把同一替代名写入 fontTable altName。

本文件在声明层机械复现并拦截该故障：产物不得再携带
“eastAsia=方正*_GBK + altName=Arial Unicode MS”这一触发组合。
渲染层的最终裁决（存活率 ≥ 0.995）由 run_e2e.sh 的真实 PDF 渲染阶段兜底。
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from lxml import etree

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from fill_template import apply_font_compatibility  # noqa: E402
from layout_gate import _find_soffice, _renderer_kind, _soffice_version  # noqa: E402

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

SAMPLE_TEMPLATE = SKILL_DIR / "templates" / "09-民间借贷纠纷-民事起诉状"


def load_policy() -> dict:
    """与 layout_gate.load_policy 同口径：defaults 平铺 + 模板覆写。"""
    raw = json.loads(
        (SKILL_DIR / "config" / "layout-policy.json").read_text(encoding="utf-8")
    )
    policy = dict(raw.get("defaults") or {})
    policy.update((raw.get("templates") or {}).get("09-民间借贷纠纷-民事起诉状", {}))
    return policy


def read_docx_part(docx: Path, name: str):
    with zipfile.ZipFile(docx) as archive:
        return etree.fromstring(archive.read(name))


def unpack_template(root: Path) -> Path:
    """把真实 09 模板树复制为可编辑副本（绝不污染源码树）。"""
    tree = root / "tree"
    shutil.copytree(SAMPLE_TEMPLATE, tree)
    return tree


def pack_tree(tree_dir: Path, out_docx: Path) -> Path:
    import pack_docx

    pack_docx.pack_tree(tree_dir, out_docx)
    return out_docx


class OriginalTemplateCarriesMismatchTrigger(unittest.TestCase):
    """故障前提确认：原始模板确实携带会触发错配的字体声明组合。"""

    def test_original_font_table_has_unicode_ms_altname(self):
        font_table = etree.parse(str(SAMPLE_TEMPLATE / "word" / "fontTable.xml"))
        aliases = {
            font.get(f"{W}name"): (
                font.find(f"{W}altName").get(f"{W}val")
                if font.find(f"{W}altName") is not None else None
            )
            for font in font_table.iter(f"{W}font")
        }
        # 09 基线故障的声明级根因：书宋 altName 指向多数渲染环境不存在的字体
        self.assertEqual(aliases.get("方正书宋_GBK"), "Arial Unicode MS")

    def test_original_styles_reference_fangzheng_body_font(self):
        styles = etree.parse(str(SAMPLE_TEMPLATE / "word" / "styles.xml"))
        east_asia = {
            rf.get(f"{W}eastAsia") for rf in styles.iter(f"{W}rFonts")
            if rf.get(f"{W}eastAsia")
        }
        self.assertIn("方正书宋_GBK", east_asia)


def all_candidates(policy: dict) -> set[str]:
    """策略中全部候选名的并集（替代结果必须出自该集合）。"""
    names: set[str] = set()
    for value in policy["font_compatibility"]["cjk_replacements"].values():
        names.update(value if isinstance(value, list) else [value])
    return names


def candidates_of(policy: dict, font: str) -> set[str]:
    """某个原字体的候选链。"""
    value = policy["font_compatibility"]["cjk_replacements"][font]
    return set(value if isinstance(value, list) else [value])


class FontCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ecg-font-compat-")
        self.root = Path(self.temp.name)
        self.policy = load_policy()

    def tearDown(self):
        self.temp.cleanup()

    def test_real_template_rewrites_cjk_references(self):
        """真实 09 模板：eastAsia 全部替换为策略替代名，ascii/字号/加粗不动。"""
        tree = unpack_template(self.root)
        before = etree.parse(str(tree / "word" / "document.xml"))
        sizes_before = sorted(
            el.get(f"{W}val") for el in before.iter(f"{W}sz") if el.get(f"{W}val")
        )
        bold_before = sum(1 for _ in before.iter(f"{W}b"))

        stats = apply_font_compatibility(tree, self.policy)

        self.assertGreater(stats["attribute_count"], 0, "真实模板必须产生替代")
        replacements = self.policy["font_compatibility"]["cjk_replacements"]

        after = etree.parse(str(tree / "word" / "document.xml"))
        east_asia = {
            rf.get(f"{W}eastAsia") for rf in after.iter(f"{W}rFonts")
            if rf.get(f"{W}eastAsia")
        }
        # 只剩替代名（且都来自策略候选），不再有任何方正 *_GBK CJK 引用
        self.assertTrue(east_asia, "替代后 eastAsia 不应为空")
        self.assertTrue(east_asia.issubset(all_candidates(self.policy)))
        self.assertFalse(
            any(name in replacements for name in east_asia),
            f"方正字体 CJK 引用未被替换: {east_asia}",
        )

        # 四槽（eastAsia/ascii/hAnsi/cs）都不得残留被替换旧名：ascii/hAnsi 残留
        # 方正旧名时，LibreOffice 对继承样式/中西混排 run 仍会错配 Verdana。
        for slot in ("eastAsia", "ascii", "hAnsi", "cs"):
            values = {
                rf.get(f"{W}{slot}") for rf in after.iter(f"{W}rFonts")
                if rf.get(f"{W}{slot}")
            }
            residue = values & set(replacements)
            self.assertFalse(residue, f"{slot} 槽仍残留被替换旧名: {residue}")

        # 字号/加粗等非字体名属性一律不动
        sizes_after = sorted(
            el.get(f"{W}val") for el in after.iter(f"{W}sz") if el.get(f"{W}val")
        )
        self.assertEqual(sizes_before, sizes_after)
        bold_after = sum(1 for _ in after.iter(f"{W}b"))
        self.assertEqual(bold_before, bold_after)

        # 已证明会让 LibreOffice 漂移的名字不得再次成为候选；标题/正文/
        # 落款的层级由上面的字号、加粗和段落样式不变断言保障。
        unstable = {"STZhongsong", "Kaiti SC"}
        for font, names in replacements.items():
            self.assertFalse(
                set(names) & unstable,
                f"{font} 候选链仍含不稳定字体: {set(names) & unstable}",
            )

    def test_font_table_altname_follows_policy(self):
        """fontTable：被替代字体的 altName 更新为策略替代名；未列名字体不动。"""
        tree = unpack_template(self.root)
        stats = apply_font_compatibility(tree, self.policy)

        font_table = etree.parse(str(tree / "word" / "fontTable.xml"))
        replacements = self.policy["font_compatibility"]["cjk_replacements"]
        candidates = all_candidates(self.policy)
        for font in font_table.iter(f"{W}font"):
            name = font.get(f"{W}name")
            alt = font.find(f"{W}altName")
            if name in replacements:
                self.assertIsNotNone(alt, f"{name} 缺少 altName")
                self.assertIn(
                    alt.get(f"{W}val"), replacements[name],
                    f"{name} 的 altName 不在其候选链内",
                )
            elif alt is not None:
                # 未参与替代的字体（如 Calibri→DejaVu Sans）保持原 altName 声明
                self.assertNotIn(name, stats["fonts"])
                self.assertNotIn(alt.get(f"{W}val"), candidates - {alt.get(f"{W}val")})
        # altName 只更新 fontTable 中实际存在的被映射字体条目，不超过映射表大小
        self.assertLessEqual(stats["altname_count"], len(replacements))
        self.assertGreater(stats["altname_count"], 0, "09 fontTable 含方正条目，必须更新")

    def test_styles_part_is_rewritten(self):
        """styles.xml 的默认字体（书宋）同样必须被替换，否则正文继承仍错配。"""
        tree = unpack_template(self.root)
        apply_font_compatibility(tree, self.policy)
        styles = etree.parse(str(tree / "word" / "styles.xml"))
        east_asia = {
            rf.get(f"{W}eastAsia") for rf in styles.iter(f"{W}rFonts")
            if rf.get(f"{W}eastAsia")
        }
        self.assertNotIn("方正书宋_GBK", east_asia)
        self.assertTrue(
            east_asia & all_candidates(self.policy),
            f"styles 默认字体未被替换为候选链内字体: {east_asia}",
        )

    def test_disabled_policy_leaves_tree_untouched(self):
        """策略开关关闭（enabled=false）时不做任何改写。"""
        tree = unpack_template(self.root)
        before = (tree / "word" / "document.xml").read_bytes()
        policy = {**self.policy, "font_compatibility": {"enabled": False}}
        stats = apply_font_compatibility(tree, policy)
        self.assertEqual(stats["attribute_count"], 0)
        self.assertEqual(stats["altname_count"], 0)
        self.assertEqual(before, (tree / "word" / "document.xml").read_bytes())

    def test_missing_policy_section_leaves_tree_untouched(self):
        """policy 无 font_compatibility 段（旧版 config）时安全跳过。"""
        tree = unpack_template(self.root)
        before = (tree / "word" / "document.xml").read_bytes()
        stats = apply_font_compatibility(tree, {"template_name": "x"})
        self.assertEqual(stats["attribute_count"], 0)
        self.assertEqual(before, (tree / "word" / "document.xml").read_bytes())

    def test_packed_docx_carries_no_mismatch_trigger(self):
        """产物级回归：打包后 docx 四槽都不再携带触发错配的声明组合。"""
        tree = unpack_template(self.root)
        apply_font_compatibility(tree, self.policy)
        docx = pack_tree(tree, self.root / "candidate.docx")

        replacements = self.policy["font_compatibility"]["cjk_replacements"]
        for part in ("word/document.xml", "word/styles.xml"):
            xml = read_docx_part(docx, part)
            for slot in ("eastAsia", "ascii", "hAnsi", "cs"):
                values = {
                    rf.get(f"{W}{slot}") for rf in xml.iter(f"{W}rFonts")
                    if rf.get(f"{W}{slot}")
                }
                self.assertFalse(
                    values & set(replacements),
                    f"{part} 的 {slot} 槽仍引用方正 CJK 字体: {values & set(replacements)}",
                )

    def test_chosen_candidates_have_cjk_coverage_via_fc_match(self):
        """候选验证：每个被选定的替代字体名经 fc-match 解析后 lang 必须覆盖
        中文。裸名「黑体」「楷体」在本机 fontconfig 会错配 Verdana（无 zh 覆盖，
        09-sample 字形存活率 0.979 的根因），此类名字不得成为替代结果。"""
        import subprocess

        fc_match = shutil.which("fc-match")
        if fc_match is None:
            self.skipTest("本机无 fc-match，无法做字体覆盖验证")

        def has_cjk(name: str) -> bool:
            proc = subprocess.run(
                [fc_match, "-f", "%{file}|%{lang}", "--", name],
                capture_output=True, text=True, timeout=15, check=False,
            )
            fields = proc.stdout.strip().split("|")
            return any(
                lang == "zh" or lang.startswith("zh-") for lang in fields[1:]
            ) and proc.returncode == 0

        for font, names in self.policy["font_compatibility"]["cjk_replacements"].items():
            self.assertTrue(
                any(has_cjk(name) for name in names),
                f"{font} 的候选链 {names} 中没有任何名字有中文覆盖",
            )

    def test_unresolvable_candidates_fail_closed(self):
        """fail-closed：候选链全部无法解析出中文覆盖字体时必须阻断生成，
        宁可不出文书也不产出渲染丢字的不可读产物。"""
        tree = unpack_template(self.root)
        before = (tree / "word" / "document.xml").read_bytes()
        policy = {
            **self.policy,
            "font_compatibility": {
                "enabled": True,
                "cjk_replacements": {"方正书宋_GBK": ["NoSuchZhFont-A", "NoSuchZhFont-B"]},
            },
        }
        stats = apply_font_compatibility(tree, policy)
        if shutil.which("fc-match") is None:
            self.skipTest("本机无 fc-match，走未验证分支而非 fail-closed")
        self.assertFalse(stats["ok"], "不存在的候选字体必须 fail-closed")
        self.assertEqual(stats["unresolved"], ["方正书宋_GBK"])
        self.assertEqual(
            before, (tree / "word" / "document.xml").read_bytes(),
            "fail-closed 时不得改写模板树",
        )

    def test_patent_template_simplified_variant_is_rewritten(self):
        """回归（25-专利模板真实故障复现）：25 模板正文使用映射外变体
        「方正书宋简体」，fc-match 解析为 Verdana（无中文覆盖），真实渲染
        存活率 0.990、缺 36 字。变体必须被收编进宋体候选链。"""
        patent_dir = SKILL_DIR / "templates" / "25-侵害外观设计专利权纠纷-民事起诉状"
        tree = self.root / "tree25"
        shutil.copytree(patent_dir, tree)
        stats = apply_font_compatibility(tree, self.policy)

        self.assertTrue(stats["ok"], stats)
        after = etree.parse(str(tree / "word" / "document.xml"))
        east_asia = {
            rf.get(f"{W}eastAsia") for rf in after.iter(f"{W}rFonts")
            if rf.get(f"{W}eastAsia")
        }
        self.assertNotIn("方正书宋简体", east_asia)
        # 四槽都不得残留任何被映射旧名（含 方正书宋简体 变体）
        replacements = self.policy["font_compatibility"]["cjk_replacements"]
        for slot in ("eastAsia", "ascii", "hAnsi", "cs"):
            values = {
                rf.get(f"{W}{slot}") for rf in after.iter(f"{W}rFonts")
                if rf.get(f"{W}{slot}")
            }
            residue = values & set(replacements)
            self.assertFalse(residue, f"25 模板 {slot} 槽仍残留被替换旧名: {residue}")
        # 中文字体槽不得残留任何陌生名；Times New Roman/Arial 属 eastAsia 槽里的
        # 西文字体声明（模板原有），不在中文替代管辖范围，由渲染存活率裁决。
        unexpected = east_asia - all_candidates(self.policy) - {"Times New Roman", "Arial"}
        self.assertFalse(
            unexpected,
            f"仍有映射外的中文字体名: {unexpected}",
        )
        # fontTable 的变体条目同样获得候选链内的 altName
        font_table = etree.parse(str(tree / "word" / "fontTable.xml"))
        for font in font_table.iter(f"{W}font"):
            name = font.get(f"{W}name")
            alt = font.find(f"{W}altName")
            if name == "方正书宋简体":
                self.assertIsNotNone(alt)
                self.assertIn(alt.get(f"{W}val"), candidates_of(self.policy, "方正书宋简体"))

    def test_case_47_unstable_mapped_font_names_are_rewritten(self):
        """回归：47 模板映射出的 STZhongsong/Kaiti SC 在同一 LibreOffice
        中连续渲染会漂移到不同实际字体并造成 3/4 页波动；四槽必须统一归一。"""
        case_dir = SKILL_DIR / "templates" / "47-国有土地上房屋征收决定-行政起诉状"
        tree = self.root / "tree47"
        shutil.copytree(case_dir, tree)

        before = etree.parse(str(tree / "word" / "document.xml"))
        unstable = {"STZhongsong", "Kaiti SC"}
        before_names = {
            rf.get(f"{W}{slot}")
            for rf in before.iter(f"{W}rFonts")
            for slot in ("eastAsia", "ascii", "hAnsi", "cs")
            if rf.get(f"{W}{slot}")
        }
        source_fonts = {"方正大标宋_GBK", "方正小标宋_GBK", "方正楷体_GBK"}
        self.assertTrue(before_names & source_fonts, "47 模板应保留故障前提")

        stats = apply_font_compatibility(tree, self.policy)
        self.assertTrue(stats["ok"], stats)
        after = etree.parse(str(tree / "word" / "document.xml"))
        for slot in ("eastAsia", "ascii", "hAnsi", "cs"):
            values = {
                rf.get(f"{W}{slot}")
                for rf in after.iter(f"{W}rFonts")
                if rf.get(f"{W}{slot}")
            }
            self.assertFalse(
                values & unstable,
                f"47 模板 {slot} 槽仍残留不稳定字体: {values & unstable}",
            )

    def test_no_cjk_fallback_names_are_not_used(self):
        """回归：曾被 fc-match 错配 Verdana 的裸名不得再作为唯一候选进入策略。"""
        raw = self.policy["font_compatibility"]["cjk_replacements"]
        for font, names in raw.items():
            name_list = names if isinstance(names, list) else [names]
            self.assertGreaterEqual(
                len(name_list), 2,
                f"{font} 只配置了单名 {name_list}：裸名错配 Verdana 时无回退候选",
            )


@unittest.skipUnless(
    _find_soffice() is not None
    and _renderer_kind(_soffice_version(_find_soffice() or "")) == "official",
    "需要正式版 LibreOffice/soffice 做真实渲染（开发构建不暴露系统中文字体）",
)
class RenderedGlyphSurvivalTests(unittest.TestCase):
    """字形真实可见性证明：只有名称改写不足为凭，必须真实渲染并比对存活率。

    验收对象是真实交付路径的生成件（fill_template 完整生成：删未用节、
    归一表格、修分页），而非“裸模板仅字体兼容后直接打包”——裸模板含有
    不进入交付物的可选节/复杂对象，渲染缺字不代表交付物缺字。
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ecg-font-render-")
        self.root = Path(self.temp.name)
        self.policy = load_policy()

    def tearDown(self):
        self.temp.cleanup()

    def assert_generated_docx_rendered_survival(
        self, case_type: str, fixture: str, tag: str
    ):
        """真实生成 → LibreOffice 渲染 → 存活率/方框字/视觉空字形三重裁决心检。"""
        import subprocess

        from layout_gate import audit_pdf, audit_text_survival, render_docx

        docx = self.root / f"{tag}-generated.docx"
        proc = subprocess.run(
            [
                sys.executable, "-B", str(SKILL_DIR / "scripts" / "fill_template.py"),
                "--case-type", case_type,
                "--elements", str(SKILL_DIR / "tests" / "fixtures" / fixture),
                "--output", str(docx),
                "--layout-check", "docx",
            ],
            capture_output=True, text=True, timeout=180,
        )
        self.assertEqual(
            proc.returncode, 0,
            f"{tag} 生成失败：{proc.stdout[-500:]}{proc.stderr[-500:]}",
        )
        pdf, work = render_docx(docx)
        try:
            # 1) 文本层存活率 ≥ 阈值（基线故障：09 为 0.979、25 为 0.990）
            survival = audit_text_survival(docx, pdf, self.policy)
            self.assertTrue(survival["ok"], survival["issues"])
            ratio = survival["measurements"]["glyph_survival_ratio"]
            threshold = float(self.policy.get("min_glyph_survival_ratio", 0.995))
            self.assertGreaterEqual(
                ratio, threshold,
                f"{tag}：中文字形存活率 {ratio} 低于阈值 {threshold}",
            )
            # 2) gate 层无方框字判定
            rendered = audit_pdf(pdf, self.policy)
            glyph_issues = [
                i for i in rendered["issues"] if i["code"] == "ECG-LAYOUT-GLYPH"
            ]
            self.assertFalse(glyph_issues, f"渲染出现方框字: {glyph_issues}")

            # 3) 视觉级检查：PDF 文本层可提取不代表字形可见（LibreOffice 缺字形
            #    时输出 glyph 0 空字形但保留 ToUnicode，存活率被高估）。统计
            #    CJK 字符落在 0 号空字形上的比例，超过 5% 即判定视觉性丢字。
            import fitz

            cjk_total = notdef_cjk = 0
            pdf_doc = fitz.open(pdf)
            try:
                for page in pdf_doc:
                    for span in page.get_texttrace():
                        for uni, glyph, _origin, _bbox in span.get("chars", []):
                            if not (0x2E80 <= uni <= 0x9FFF or 0xFF00 <= uni <= 0xFFEF):
                                continue
                            cjk_total += 1
                            if glyph == 0:
                                notdef_cjk += 1
            finally:
                pdf_doc.close()
            notdef_ratio = notdef_cjk / cjk_total if cjk_total else 0.0
            self.assertLess(
                notdef_ratio, 0.05,
                f"{tag}：CJK 字符 {notdef_cjk}/{cjk_total} 渲染为 0 号空字形"
                f"（比例 {notdef_ratio:.1%}），视觉性丢字未修复",
            )
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_09_generated_sample_renders_chinese_survives(self):
        """基线故障 09-sample：存活率 0.979、缺 53 字（Verdana 错配）。"""
        self.assert_generated_docx_rendered_survival(
            "09-private-lending", "09-private-lending-sample.json", "09"
        )

    def test_25_generated_sample_renders_chinese_survives(self):
        """回归（真实 E2E 故障）：25 专利模板的映射外变体「方正书宋简体」
        曾致存活率 0.990、缺 36 字；收编进候选链后生成件必须达标。"""
        self.assert_generated_docx_rendered_survival(
            "25-design-patent", "25-design-patent-sample.json", "25"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
