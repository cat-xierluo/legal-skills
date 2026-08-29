#!/usr/bin/env python3
"""scan_consistency.py 的最小 fixture 自测。

覆盖两类样本（T263 任务书口径）：
- 一个合规 SVG → 0 finding；
- 一个故意违规 SVG → 命中各规则（SYNTAX/MARKER/PADDING/ARROW/IDENTITY）。
另有 sidecar 同步（SIDECAR-01/02）与跨图重复 ID（IDENTITY-02）的最小书树用例。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from scan_consistency import (  # noqa: E402
    SvgScanResult,
    discover_canonical,
    scan_file,
    scan_svg,
)

# 合规样本：viewBox 0 0 720 128（H=内容底 88+40）、显式 width/height、唯一 figure-id、
# 单 arrow marker（userSpaceOnUse+orient=auto）、箭头落点=目标框边−4px、四周边距=40px、
# 无 <style>/style=/font-family/背景矩形。
COMPLIANT_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 128" width="720" height="128" data-figure-id="fig-ch99-s1-01">
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="10" markerHeight="10" orient="auto" markerUnits="userSpaceOnUse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#2D3436"/>
    </marker>
  </defs>
  <rect x="40" y="40" width="140" height="48" rx="6" fill="#D6E4F0" stroke="#2D3436" stroke-width="2"/>
  <text x="110" y="69" text-anchor="middle" font-size="18" fill="#2D3436">识别场景</text>
  <rect x="540" y="40" width="140" height="48" rx="6" fill="#C5D9E8" stroke="#2D3436" stroke-width="2"/>
  <text x="610" y="69" text-anchor="middle" font-size="18" fill="#2D3436">梳理流程</text>
  <line x1="184" y1="64" x2="536" y2="64" stroke="#2D3436" stroke-width="2" marker-end="url(#arrow)"/>
</svg>'''

# 违规样本：逐条命中 SYNTAX-01..05 / MARKER-01..03 / PADDING-01 / ARROW-01..03 / IDENTITY-01。
VIOLATING_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 400" width="700" height="390">
  <style>.a { fill: red; }</style>
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="10" markerHeight="10">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#2D3436"/>
    </marker>
    <marker id="arrV" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="10" markerHeight="10" orient="auto" markerUnits="userSpaceOnUse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#2D3436"/>
    </marker>
  </defs>
  <rect x="0" y="0" width="720" height="400" fill="#FFFFFF"/>
  <rect x="10" y="330" width="140" height="48" rx="6" fill="#D6E4F0" stroke="#2D3436" stroke-width="2"/>
  <text x="80" y="360" text-anchor="middle" font-size="18" font-family="PingFang SC" fill="#2D3436">左贴边</text>
  <rect x="300" y="330" width="140" height="48" rx="6" fill="#D6E4F0" stroke="#2D3436" stroke-width="2"/>
  <text x="370" y="360" text-anchor="middle" font-size="18" fill="#2D3436">目标框</text>
  <line x1="200" y1="354" x2="340" y2="354" stroke="#2D3436" stroke-width="2" marker-end="url(#arrow)"/>
  <line x1="480" y1="354" x2="650" y2="354" stroke="#2D3436" stroke-width="2" marker-end="url(#arrV)"/>
  <line x1="480" y1="100" x2="650" y2="100" stroke="#2D3436" stroke-width="2" marker-end="url(#missing)"/>
  <line x1="40" y1="100" x2="640" y2="100" stroke="#718096" stroke-width="1.8" marker-end="url(#arrow)" data-arrow-role="axis" data-arrow-note=""/>
  <rect x="500" y="150" width="100" height="40" style="fill:#F00" fill="#EDF2F7"/>
</svg>'''


def rule_ids(result: SvgScanResult) -> set[str]:
    return {f.rule_id for f in result.findings}


class ScanSvgFixtureTest(unittest.TestCase):
    def test_compliant_svg_zero_findings(self) -> None:
        ctx = SvgScanResult(file='fixture.md', svg_index=0)
        scan_svg(COMPLIANT_SVG, ctx, padding=40, arrow_gap=8)
        self.assertEqual(ctx.findings, [])

    def test_violating_svg_hits_each_rule_family(self) -> None:
        ctx = SvgScanResult(file='fixture.md', svg_index=0)
        scan_svg(VIOLATING_SVG, ctx, padding=40, arrow_gap=8)
        got = rule_ids(ctx)
        expected = {
            'SYNTAX-01',  # <style> 块
            'SYNTAX-02',  # style= 属性
            'SYNTAX-03',  # font-family
            'SYNTAX-04',  # 720×400 白底矩形
            'SYNTAX-05',  # width=700/height=390 与 viewBox 720×400 不一致
            'MARKER-01',  # arrV 多 marker
            'MARKER-02',  # arrow 缺 markerUnits/orient
            'MARKER-03',  # url(#missing) 悬空引用
            'PADDING-01',  # 左 10px / 底 22px < 40px
            'ARROW-01',   # 尖端 (340,354) 穿入目标框
            'ARROW-02',   # 悬空箭头（含 url(#missing) 与无 note 的轴线）
            'ARROW-03',   # data-arrow-role=axis 但 note 为空
            'IDENTITY-01',  # 缺 data-figure-id
        }
        self.assertEqual(got, expected, f'实际命中 {sorted(got)}')

    def test_xml_parse_error(self) -> None:
        ctx = SvgScanResult(file='fixture.md', svg_index=0)
        scan_svg('<svg><rect></svg>', ctx, padding=40, arrow_gap=8)
        self.assertEqual(rule_ids(ctx), {'XML-01'})


class ScanFileSidecarTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ms = self.root / 'manuscript'
        self.ms.mkdir()
        self.md = self.ms / 'ch99-测试图.md'
        self.md.write_text(
            COMPLIANT_SVG + '\n\n**图 99-1：测试图**\n', encoding='utf-8')
        self.sidecar_dir = self.ms / 'ch99-测试图_images'

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _scan(self) -> object:
        return scan_file(self.md, self.root, padding=40, arrow_gap=8, id_registry={})

    def test_matching_sidecar_no_findings(self) -> None:
        self.sidecar_dir.mkdir()
        (self.sidecar_dir / 'ch99-测试图-svg-0.svg').write_text(
            COMPLIANT_SVG, encoding='utf-8')
        fs = self._scan()
        self.assertEqual(fs.sidecar_findings, [])
        self.assertEqual(fs.svg_count, 1)
        self.assertEqual(fs.results[0].findings, [])

    def test_trailing_whitespace_sidecar_reported(self) -> None:
        # T261 口径:sidecar 与 canonical 逐字节相同;仅尾随空白差异也须报 SIDECAR-01
        self.sidecar_dir.mkdir()
        (self.sidecar_dir / 'ch99-测试图-svg-0.svg').write_text(
            COMPLIANT_SVG + '\n', encoding='utf-8')
        fs = self._scan()
        self.assertEqual([f.rule_id for f in fs.sidecar_findings], ['SIDECAR-01'])

    def test_mismatched_sidecar_reported(self) -> None:
        self.sidecar_dir.mkdir()
        (self.sidecar_dir / 'ch99-测试图-svg-0.svg').write_text(
            COMPLIANT_SVG.replace('识别场景', '已被改动'), encoding='utf-8')
        fs = self._scan()
        self.assertEqual([f.rule_id for f in fs.sidecar_findings], ['SIDECAR-01'])
        self.assertIn('实质差异', fs.sidecar_findings[0].message)

    def test_missing_sidecar_file_reported(self) -> None:
        self.sidecar_dir.mkdir()
        fs = self._scan()
        self.assertEqual([f.rule_id for f in fs.sidecar_findings], ['SIDECAR-02'])

    def test_no_sidecar_dir_is_note_only(self) -> None:
        fs = self._scan()
        self.assertEqual(fs.sidecar_findings, [])
        self.assertTrue(any('无 sidecar 目录' in n for n in fs.sidecar_notes))

    def test_duplicate_figure_id_across_svgs(self) -> None:
        # 两张同 id 的合规 SVG：第二张应报 IDENTITY-02（跨图重复）
        self.md.write_text(
            COMPLIANT_SVG + '\n\n**图 99-1：第一张**\n\n' + COMPLIANT_SVG + '\n\n**图 99-2：第二张**\n',
            encoding='utf-8')
        fs = self._scan()
        second = fs.results[1]
        self.assertIn('IDENTITY-02', rule_ids(second))
        self.assertNotIn('IDENTITY-02', rule_ids(fs.results[0]))

    def test_discover_canonical_ignores_images_dirs(self) -> None:
        self.sidecar_dir.mkdir()
        (self.sidecar_dir / 'ch99-测试图-svg-0.svg').write_text(COMPLIANT_SVG, encoding='utf-8')
        self.assertEqual(discover_canonical(self.root), [self.md])


if __name__ == '__main__':
    unittest.main()


class ExemptionLedgerTest(unittest.TestCase):
    """--exemptions 逐项豁免台账（v1.9.1）：命中不计 findings，未命中报警，坏台账 fail-closed。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ms = self.root / 'manuscript'
        self.ms.mkdir()
        self.md = self.ms / 'ch99-测试图.md'
        # sidecar 不一致场景：canonical 无尾换行、sidecar 有 → SIDECAR-01
        self.md.write_text(COMPLIANT_SVG + '\n\n**图 99-1：测试图**\n', encoding='utf-8')
        self.sidecar_dir = self.ms / 'ch99-测试图_images'
        self.sidecar_dir.mkdir()
        (self.sidecar_dir / 'ch99-测试图-svg-0.svg').write_text(
            COMPLIANT_SVG.replace('识别场景', '已被改动'), encoding='utf-8')

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _ledger(self, root: Path, items: list) -> Path:
        import json
        p = root / 'exemptions.json'
        p.write_text(json.dumps({'schema_version': 1, 'items': items}, ensure_ascii=False), encoding='utf-8')
        return p

    def test_exempted_finding_removed_and_used_key_reported(self) -> None:
        from scan_consistency import apply_exemptions, load_exemptions
        ledger = self._ledger(self.root, [
            {'file': 'manuscript/ch99-测试图.md', 'svg_index': 0, 'rule_id': 'SIDECAR-01',
             'reason': '作者裁决接受(2026-08-29)', 'adjudicated': '2026-08-29'}])
        table = load_exemptions(ledger)
        self.assertEqual(len(table), 1)
        fs = [scan_file(self.md, self.root, padding=40, arrow_gap=8, id_registry={})]
        self.assertEqual([f.rule_id for f in fs[0].sidecar_findings], ['SIDECAR-01'])
        used = apply_exemptions(fs, table)
        self.assertEqual(used, {('manuscript/ch99-测试图.md', 0, 'SIDECAR-01')})
        self.assertEqual(fs[0].sidecar_findings, [])

    def test_non_matching_entry_keeps_finding_and_marks_unused(self) -> None:
        from scan_consistency import apply_exemptions, load_exemptions
        ledger = self._ledger(self.root, [
            {'file': 'manuscript/ch99-测试图.md', 'svg_index': 3, 'rule_id': 'SIDECAR-01'}])
        table = load_exemptions(ledger)
        fs = [scan_file(self.md, self.root, padding=40, arrow_gap=8, id_registry={})]
        used = apply_exemptions(fs, table)
        self.assertEqual(used, set())                     # 未命中 → 台账漂移信号
        self.assertEqual([f.rule_id for f in fs[0].sidecar_findings], ['SIDECAR-01'])

    def test_bad_schema_or_unknown_rule_fail_closed(self) -> None:
        from scan_consistency import load_exemptions
        bad = self.root / 'bad.json'
        bad.write_text('{"schema_version": 2, "items": []}', encoding='utf-8')
        with self.assertRaises(SystemExit):
            load_exemptions(bad)
        unknown = self._ledger(self.root, [
            {'file': 'x.md', 'svg_index': 0, 'rule_id': 'NOPE-99'}])
        with self.assertRaises(SystemExit):
            load_exemptions(unknown)
