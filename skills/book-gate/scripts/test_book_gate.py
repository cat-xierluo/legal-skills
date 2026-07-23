#!/usr/bin/env python3
"""book-gate 故障注入回归：已知坏样本必须被拦下。"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil
import subprocess
import sys
import unittest
import zipfile

import yaml


HERE = Path(__file__).resolve().parent
CLI = HERE / "book-gate.py"
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from docx_checker import _benign_soffice_warning  # noqa: E402


VALID_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">
<rect x="10" y="10" width="80" height="80" fill="#EDF2F7" stroke="#2D3436"/>
<text x="50" y="55" text-anchor="middle" fill="#2D3436">测试</text>
</svg>"""


def requirement(rid, stage, verifier, options=None):
    item = {
        "id": rid,
        "stage": stage,
        "scope": "manuscript/**/*.md",
        "description": rid,
        "verifier": verifier,
        "threshold": 0,
        "blocking": True,
        "needs_human_review": False,
    }
    if options is not None:
        item["options"] = options
    return item


def spec(requirements, stages, include_archive=False, dimensions=None):
    hash_inputs = ["manuscript/**/*.md"]
    if include_archive:
        hash_inputs.append("figures/ai-generated/**/*.svg")
    return {
        "schema_version": "1.0.0",
        "hash_inputs": hash_inputs,
        "require_each_hash_input": True,
        "release": {"required_stages": stages},
        "visual_review": {"dimensions": dimensions or []},
        "requirements": requirements,
    }


class BookGateTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "manuscript").mkdir()
        self.out = self.root / "evidence"

    def tearDown(self):
        self.temp.cleanup()

    def write_chapter(self, text):
        path = self.root / "manuscript" / "ch01.md"
        path.write_text(text, encoding="utf-8")
        return path

    def write_spec(self, data):
        path = self.root / "requirements.yaml"
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return path

    def run_gate_cli(self, stage, req, *extra):
        command = [
            sys.executable, str(CLI), "verify", str(self.root),
            "--requirements", str(req), "--stage", stage, "--out", str(self.out),
            *map(str, extra),
        ]
        return subprocess.run(command, text=True, capture_output=True, check=False)

    def latest_evidence(self, stage):
        files = sorted(self.out.glob(f"evidence-*-{stage}.json"), key=lambda item: item.stat().st_mtime_ns)
        self.assertTrue(files)
        return json.loads(files[-1].read_text(encoding="utf-8"))

    def test_empty_requirements_fail_closed(self):
        self.write_chapter("# 章\n")
        req = self.write_spec({
            "schema_version": "1.0.0",
            "hash_inputs": ["manuscript/**/*.md"],
            "release": {"required_stages": ["source"]},
            "requirements": [],
        })
        result = self.run_gate_cli("source", req)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("空规则集", result.stderr)

    def test_empty_project_cannot_pass(self):
        req = self.write_spec(spec([
            requirement("MD-001", "source", "markdown.no_diagram_dsl"),
        ], ["source"]))
        result = self.run_gate_cli("source", req)
        self.assertEqual(result.returncode, 2)
        self.assertIn("没有匹配任何文件", result.stderr)

    def test_known_markdown_mutations_are_blocking(self):
        self.write_chapter(
            "# 章\n\n```mermaid\nflowchart LR\nA-->B\n```\n\n"
            "这里写'需律师确认'。\n\n" + VALID_SVG + "\n\n**图 1-1：第一张**\n\n"
            + VALID_SVG + "\n\n**图 1-2：第二张**\n"
        )
        req = self.write_spec(spec([
            requirement("MD-001", "source", "markdown.no_diagram_dsl"),
            requirement("MD-002", "source", "markdown.no_ascii_cjk_quote"),
            requirement("MD-003", "source", "markdown.figure_separation"),
        ], ["source"]))
        result = self.run_gate_cli("source", req)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        evidence = self.latest_evidence("source")
        self.assertEqual(evidence["overall"], "BLOCKED")
        self.assertEqual({item["verdict"] for item in evidence["results"]}, {"FAIL"})

    def test_candidate_hash_changes_when_archive_svg_changes(self):
        self.write_chapter("# 章\n\n" + VALID_SVG + "\n\n**图 1-1：测试**\n")
        archive = self.root / "figures" / "ai-generated" / "ch01"
        archive.mkdir(parents=True)
        svg_path = archive / "fig.svg"
        svg_path.write_text(VALID_SVG, encoding="utf-8")
        req = self.write_spec(spec([
            requirement("MD-001", "source", "markdown.no_diagram_dsl"),
        ], ["source"], include_archive=True))
        first = self.run_gate_cli("source", req)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        first_sha = self.latest_evidence("source")["candidate_sha"]
        svg_path.write_text(VALID_SVG.replace("测试", "变更"), encoding="utf-8")
        second = self.run_gate_cli("source", req)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        second_sha = self.latest_evidence("source")["candidate_sha"]
        self.assertNotEqual(first_sha, second_sha)

    @unittest.skipUnless(shutil.which("rsvg-convert"), "需要 rsvg-convert")
    def test_render_manifest_and_independent_review_are_hash_bound(self):
        self.write_chapter("# 章\n\n" + VALID_SVG + "\n\n**图 1-1：测试**\n\n解释正文。\n")
        dimensions = [
            {"id": "text_readable", "allow_na": False},
            {"id": "arrows_correct", "allow_na": True},
        ]
        req = self.write_spec(spec([
            requirement("MD-001", "source", "markdown.no_diagram_dsl"),
            requirement("RENDER-001", "render", "svg.render_and_measure", {
                "render_width": 400,
                "max_padding_ratio": 0.22,
            }),
            requirement("VISUAL-001", "visual", "visual.attestation_complete"),
        ], ["source", "render", "visual"], dimensions=dimensions))
        rendered = self.run_gate_cli("render", req, "--producer-id", "worker-a")
        self.assertEqual(rendered.returncode, 0, rendered.stdout + rendered.stderr)
        template_path = next(self.out.glob("visual-review-*.template.json"))
        review = json.loads(template_path.read_text(encoding="utf-8"))
        review.update({
            "reviewer_id": "reviewer-b",
            "reviewer_session_id": "fresh-session-1",
            "independent": True,
            "reviewed_at": "2026-07-11T00:00:00Z",
        })
        for entry in review["artifacts"]:
            entry["verdict"] = "PASS"
            entry["dimensions"] = {
                "text_readable": {"verdict": "PASS", "note": "清晰"},
                "arrows_correct": {"verdict": "NA", "note": "本图无箭头"},
            }
        review_path = self.root / "review.json"
        review_path.write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
        verified = self.run_gate_cli(
            "visual", req, "--producer-id", "worker-a", "--visual-review", review_path,
        )
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        self.assertEqual(self.latest_evidence("visual")["overall"], "INDEPENDENT_VERIFIED")

        review["reviewer_id"] = "worker-a"
        review_path.write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(self.run_gate_cli(
            "visual", req, "--producer-id", "worker-a", "--visual-review", review_path,
        ).returncode, 1)

    def test_docx_catches_ascii_quote_and_footnote_markdown(self):
        self.write_chapter("# 章\n\n" + VALID_SVG + "\n\n**图 1-1：测试**\n")
        req = self.write_spec(spec([
            requirement("MD-001", "source", "markdown.no_diagram_dsl"),
            requirement("DOCX-001", "docx", "docx.package_and_content"),
            requirement("DOCX-002", "docx", "docx.image_coverage", {"min_coverage_ratio": 1.0}),
            requirement("DOCX-003", "docx", "docx.layout_and_fonts", {
                "expected_margins_cm": {"top": 2.54, "bottom": 2.54, "left": 3.0, "right": 3.0},
                "required_east_asia_fonts": ["仿宋"],
                "required_latin_fonts": ["Times New Roman"],
            }),
        ], ["source", "docx"]))
        docx = self.root / "bad.docx"
        make_docx(docx, "这里写'需律师确认'。", "*模型概览*", image_count=1)
        result = self.run_gate_cli("docx", req, "--docx", docx)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        evidence = self.latest_evidence("docx")
        docx_result = next(item for item in evidence["results"] if item["req_id"] == "DOCX-001")
        self.assertGreaterEqual(docx_result["finding_count"], 2)

    def test_status_marks_evidence_stale_after_source_change(self):
        chapter = self.write_chapter("# 章\n")
        req = self.write_spec(spec([
            requirement("MD-001", "source", "markdown.no_diagram_dsl"),
        ], ["source"]))
        self.assertEqual(self.run_gate_cli("source", req).returncode, 0)
        evidence = next(self.out.glob("evidence-*-source.json"))
        chapter.write_text("# 章\n\n新内容。\n", encoding="utf-8")
        status = subprocess.run([
            sys.executable, str(CLI), "status", str(evidence),
            "--project-root", str(self.root), "--requirements", str(req),
        ], text=True, capture_output=True, check=False)
        self.assertEqual(status.returncode, 1)
        self.assertIn("STALE", status.stdout)

    def test_libreoffice_cache_bootstrap_warning_is_not_a_release_failure(self):
        self.assertTrue(_benign_soffice_warning("Fontconfig warning: no <cachedir> elements found."))
        self.assertTrue(_benign_soffice_warning("Fontconfig warning: adding <cachedir>/tmp/cache</cachedir>"))
        self.assertFalse(_benign_soffice_warning("Warning: font 仿宋 was substituted"))


def make_docx(path: Path, body_text: str, footnote_text: str, image_count: int):
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    blips = "".join(f'<a:blip r:embed="rId{i + 1}"/>' for i in range(image_count))
    document = f'''<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="{w}" xmlns:a="{a}" xmlns:r="{r}"><w:body>
<w:p><w:r><w:t>{body_text}</w:t></w:r></w:p>{blips}
<w:sectPr><w:pgMar w:top="1440" w:bottom="1440" w:left="1701" w:right="1701"/></w:sectPr>
</w:body></w:document>'''
    styles = f'''<?xml version="1.0" encoding="UTF-8"?>
<w:styles xmlns:w="{w}"><w:style w:type="paragraph" w:styleId="Normal">
<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="仿宋"/></w:rPr>
</w:style></w:styles>'''
    footnotes = f'''<?xml version="1.0" encoding="UTF-8"?>
<w:footnotes xmlns:w="{w}"><w:footnote w:id="1"><w:p><w:r><w:t>{footnote_text}</w:t></w:r></w:p></w:footnote></w:footnotes>'''
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", document)
        archive.writestr("word/styles.xml", styles)
        archive.writestr("word/footnotes.xml", footnotes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
