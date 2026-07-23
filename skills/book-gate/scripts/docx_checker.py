#!/usr/bin/env python3
"""直接检查作者交付的 DOCX 包、正文、脚注、图片覆盖与版心。"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET
import json
import re
import shutil
import subprocess
import tempfile
import zipfile

from gate_models import CheckerOutput, Finding, GateContext, canonical_hash, sha256_file


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_CJK = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
_ASCII_QUOTE_NEAR_CJK_RE = re.compile(
    rf"(?<![A-Za-z])'(?=[{_CJK}])|(?<=[{_CJK}])'(?![A-Za-z])"
)
_MARKDOWN_EMPHASIS_RE = re.compile(r"(?<!\\)(?:\*\*[^*\n]+\*\*|\*[^*\n]+\*|`[^`\n]+`)")
_DIAGRAM_TEXT_RE = re.compile(r"```\s*(?:mermaid|plantuml|puml|dot|graphviz|flowchart)\b", re.I)
_INLINE_SVG_RE = re.compile(r"<svg\b[\s\S]*?</svg>", re.I)
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def package_and_content(ctx: GateContext, requirement: dict) -> CheckerOutput:
    rid = requirement["id"]
    missing = _missing_docx(ctx, rid)
    if missing:
        return CheckerOutput(findings=[missing])
    assert ctx.docx_path is not None
    findings: list[Finding] = []
    required = {"[Content_Types].xml", "word/document.xml", "word/styles.xml"}
    try:
        with zipfile.ZipFile(ctx.docx_path) as archive:
            corrupt = archive.testzip()
            names = set(archive.namelist())
            if corrupt:
                findings.append(Finding(
                    rid, ctx.docx_path.name, 0, "hard", f"DOCX zip 条目损坏：{corrupt}",
                    "重新导出 DOCX。",
                ))
            for name in sorted(required - names):
                findings.append(Finding(
                    rid, ctx.docx_path.name, 0, "hard", f"DOCX 缺少必需部件：{name}",
                    "重新导出完整 OOXML 包。",
                ))
            document_text = _xml_text(archive.read("word/document.xml")) if "word/document.xml" in names else ""
            footnote_text = _xml_text(archive.read("word/footnotes.xml")) if "word/footnotes.xml" in names else ""
    except (zipfile.BadZipFile, OSError, ET.ParseError) as exc:
        return CheckerOutput(findings=[Finding(
            rid, ctx.docx_path.name, 0, "hard", f"DOCX 无法解析：{type(exc).__name__}: {exc}",
            "重新导出并保留原始失败包供回归。",
        )])

    for match in _ASCII_QUOTE_NEAR_CJK_RE.finditer(document_text + "\n" + footnote_text):
        start = max(0, match.start() - 8)
        end = min(len(document_text + "\n" + footnote_text), match.end() + 8)
        findings.append(Finding(
            rid, ctx.docx_path.name, 0, "hard",
            f"DOCX 成品仍含中文语境 ASCII 单引号：{(document_text + chr(10) + footnote_text)[start:end]}",
            "修复转换器或源稿后重新导出；不能只在 Markdown 阶段放行。",
        ))
    for match in _MARKDOWN_EMPHASIS_RE.finditer(footnote_text):
        findings.append(Finding(
            rid, ctx.docx_path.name, 0, "hard",
            f"footnotes.xml 仍显示 Markdown 标记：{match.group(0)[:80]}",
            "把强调/代码标记转换为 Word run 属性，不得把星号或反引号写进 w:t。",
        ))
    if _DIAGRAM_TEXT_RE.search(document_text):
        findings.append(Finding(
            rid, ctx.docx_path.name, 0, "hard", "DOCX 正文仍含图表 DSL 文本。",
            "先把图表转换为 SVG，再重新导出。",
        ))
    return CheckerOutput(
        findings=findings,
        metrics={
            "docx_file": ctx.docx_path.name,
            "docx_sha256": sha256_file(ctx.docx_path),
            "docx_size": ctx.docx_path.stat().st_size,
            "document_text_chars": len(document_text),
            "footnote_text_chars": len(footnote_text),
        },
    )


def image_coverage(ctx: GateContext, requirement: dict) -> CheckerOutput:
    rid = requirement["id"]
    missing = _missing_docx(ctx, rid)
    if missing:
        return CheckerOutput(findings=[missing])
    assert ctx.docx_path is not None
    options = requirement.get("options", {}) or {}
    min_ratio = float(options.get("min_coverage_ratio", 1.0))
    expected = 0
    for path in ctx.scope_files(requirement):
        if path.suffix.lower() != ".md":
            continue
        text = path.read_text(encoding="utf-8")
        expected += len(_INLINE_SVG_RE.findall(text))
        expected += len(_IMAGE_RE.findall(text))
    try:
        with zipfile.ZipFile(ctx.docx_path) as archive:
            document = ET.fromstring(archive.read("word/document.xml"))
            actual = len(document.findall(f".//{{{A_NS}}}blip"))
    except Exception as exc:
        return CheckerOutput(findings=[Finding(
            rid, ctx.docx_path.name, 0, "hard", f"无法统计 DOCX 图片引用：{exc}",
            "先通过 DOCX 包完整性检查。",
        )])
    findings: list[Finding] = []
    required_count = math_ceil(expected * min_ratio)
    if expected <= 0:
        findings.append(Finding(
            rid, "", 0, "hard", "源稿图片期望数为 0，无法证明图片覆盖。",
            "确认 scope 覆盖完整 manuscript，且源稿确实包含图。",
        ))
    elif actual < required_count:
        findings.append(Finding(
            rid, ctx.docx_path.name, 0, "hard",
            f"DOCX 图片引用仅 {actual}，源稿期望 {expected}（最低 {required_count}）。",
            "定位渲染失败/路径断链/静默跳过的图并重新导出。",
            details={"expected": expected, "actual": actual, "minimum": required_count},
        ))
    return CheckerOutput(
        findings=findings,
        metrics={"expected_image_occurrences": expected, "docx_blip_occurrences": actual},
    )


def layout_and_fonts(ctx: GateContext, requirement: dict) -> CheckerOutput:
    rid = requirement["id"]
    missing = _missing_docx(ctx, rid)
    if missing:
        return CheckerOutput(findings=[missing])
    assert ctx.docx_path is not None
    options = requirement.get("options", {}) or {}
    findings: list[Finding] = []
    try:
        with zipfile.ZipFile(ctx.docx_path) as archive:
            document = ET.fromstring(archive.read("word/document.xml"))
            styles = ET.fromstring(archive.read("word/styles.xml"))
    except Exception as exc:
        return CheckerOutput(findings=[Finding(
            rid, ctx.docx_path.name, 0, "hard", f"无法读取布局/字体 XML：{exc}",
            "先通过 DOCX 包完整性检查。",
        )])

    margins = []
    for section in document.findall(f".//{{{W_NS}}}sectPr"):
        margin = section.find(f"{{{W_NS}}}pgMar")
        if margin is None:
            findings.append(Finding(
                rid, ctx.docx_path.name, 0, "hard", "某 section 缺少 w:pgMar。",
                "显式写入全部 section 的页边距。",
            ))
            continue
        values = {
            side: int(margin.get(f"{{{W_NS}}}{side}", "0"))
            for side in ("top", "bottom", "left", "right")
        }
        margins.append(values)
    expected_cm = options.get("expected_margins_cm", {}) or {}
    tolerance_cm = float(options.get("margin_tolerance_cm", 0.05))
    tolerance_twips = _cm_to_twips(tolerance_cm)
    for index, values in enumerate(margins, 1):
        for side, cm in expected_cm.items():
            expected_twips = _cm_to_twips(float(cm))
            if abs(values.get(side, 0) - expected_twips) > tolerance_twips:
                findings.append(Finding(
                    rid, ctx.docx_path.name, 0, "hard",
                    f"section {index} 的 {side} 页边距为 {values.get(side, 0)} twips，期望约 {expected_twips}。",
                    "统一转换 preset 与所有 section 的页边距。",
                ))

    east_asia = set()
    latin = set()
    for fonts in styles.findall(f".//{{{W_NS}}}rFonts"):
        if fonts.get(f"{{{W_NS}}}eastAsia"):
            east_asia.add(fonts.get(f"{{{W_NS}}}eastAsia"))
        for key in ("ascii", "hAnsi"):
            if fonts.get(f"{{{W_NS}}}{key}"):
                latin.add(fonts.get(f"{{{W_NS}}}{key}"))
    required_east = set(options.get("required_east_asia_fonts", []) or [])
    required_latin = set(options.get("required_latin_fonts", []) or [])
    if required_east and not (required_east & east_asia):
        findings.append(Finding(
            rid, ctx.docx_path.name, 0, "hard",
            f"styles.xml 未找到要求的中文字体：{sorted(required_east)}",
            "确认出版 preset 已写入 w:eastAsia。",
            details={"observed": sorted(east_asia)},
        ))
    if required_latin and not (required_latin & latin):
        findings.append(Finding(
            rid, ctx.docx_path.name, 0, "hard",
            f"styles.xml 未找到要求的西文字体：{sorted(required_latin)}",
            "确认出版 preset 已写入 w:ascii/w:hAnsi。",
            details={"observed": sorted(latin)},
        ))
    return CheckerOutput(
        findings=findings,
        metrics={
            "section_count": len(margins),
            "margins_twips": margins,
            "east_asia_fonts": sorted(east_asia),
            "latin_fonts": sorted(latin),
        },
    )


def render_pages(ctx: GateContext, requirement: dict) -> CheckerOutput:
    """把最终 DOCX 对应的 PDF 逐页栅格化，并证明文字层与可见字形都忠实。"""
    rid = requirement["id"]
    missing = _missing_docx(ctx, rid)
    if missing:
        return CheckerOutput(findings=[missing])
    assert ctx.docx_path is not None
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        raise RuntimeError("缺少 pdftoppm（Poppler），无法把 DOCX 分页成品转为 PNG")
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if ctx.rendered_pdf_path is None and not soffice:
        raise RuntimeError(
            "缺少 LibreOffice/soffice，且未提供 Microsoft Word/WPS 导出的 --pdf；"
            "无法验证作者实际看到的分页成品"
        )
    try:
        from PIL import Image, ImageChops, ImageDraw, ImageOps
    except ImportError as exc:
        raise RuntimeError("缺少 Pillow；请运行 python3 -m pip install Pillow") from exc

    options = requirement.get("options", {}) or {}
    dpi = int(options.get("page_dpi", 120))
    min_cjk_ratio = float(options.get("min_cjk_text_ratio", 0.90))
    min_bigram_coverage = float(options.get("min_cjk_bigram_coverage", 0.90))
    min_glyph_coverage = float(options.get("min_cjk_glyph_coverage", 0.98))
    render_dir = ctx.output_dir / f"docx-rendered-{ctx.candidate_sha[:12]}"
    packet_dir = ctx.output_dir / f"docx-packets-{ctx.candidate_sha[:12]}"
    render_dir.mkdir(parents=True, exist_ok=True)
    packet_dir.mkdir(parents=True, exist_ok=True)
    findings: list[Finding] = []
    docx_sha = sha256_file(ctx.docx_path)

    if ctx.rendered_pdf_path is not None:
        if not ctx.rendered_pdf_path.is_file():
            return CheckerOutput(findings=[Finding(
                rid, ctx.rendered_pdf_path.name, 0, "hard", "--pdf 文件不存在。",
                "由 Microsoft Word/WPS 从本次 DOCX 导出 PDF 后重试。",
            )])
        source_pdf = ctx.rendered_pdf_path
        renderer = "external-author-engine"
        warning = ""
        if source_pdf.stat().st_mtime_ns < ctx.docx_path.stat().st_mtime_ns:
            findings.append(Finding(
                rid, source_pdf.name, 0, "hard", "PDF 修改时间早于 DOCX，可能是旧成品。",
                "从当前 DOCX 重新导出 PDF。",
            ))
        pdf_path = render_dir / "author-engine-export.pdf"
        if source_pdf.resolve() != pdf_path.resolve():
            shutil.copy2(source_pdf, pdf_path)
    else:
        with tempfile.TemporaryDirectory(prefix="book-gate-lo-") as profile:
            command = [
                soffice,
                f"-env:UserInstallation={Path(profile).resolve().as_uri()}",
                "--headless",
                "--convert-to", "pdf",
                "--outdir", str(render_dir),
                str(ctx.docx_path),
            ]
            converted = subprocess.run(command, text=True, capture_output=True, check=False)
        pdf_path = render_dir / f"{ctx.docx_path.stem}.pdf"
        renderer = "libreoffice-fallback"
        if converted.returncode != 0 or not pdf_path.is_file():
            return CheckerOutput(findings=[Finding(
                rid, ctx.docx_path.name, 0, "hard",
                f"LibreOffice 转 PDF 失败：{(converted.stderr or converted.stdout)[:500]}",
                "优先用 Microsoft Word/WPS 导出 PDF 并传 --pdf；否则修复 fallback 环境。",
            )])
        warning = (converted.stderr or "").strip()
    warning_lines = [line for line in warning.splitlines() if line.strip()]
    actionable_warnings = [line for line in warning_lines if not _benign_soffice_warning(line)]
    if actionable_warnings:
        findings.append(Finding(
            rid, ctx.docx_path.name, 0, "hard",
            f"LibreOffice 渲染警告：{' | '.join(actionable_warnings)[:500]}",
            "消除渲染警告后重出成品。",
        ))

    prefix = render_dir / "page"
    rasterized = subprocess.run(
        [pdftoppm, "-png", "-r", str(dpi), str(pdf_path), str(prefix)],
        text=True,
        capture_output=True,
        check=False,
    )
    if rasterized.returncode != 0:
        return CheckerOutput(findings=[Finding(
            rid, pdf_path.name, 0, "hard", f"pdftoppm 失败：{rasterized.stderr[:500]}",
            "修复 PDF 后重新分页渲染。",
        )])
    pages = sorted(render_dir.glob("page-*.png"), key=_page_number)
    if not pages:
        return CheckerOutput(findings=[Finding(
            rid, pdf_path.name, 0, "hard", "DOCX 渲染后没有任何页面 PNG。",
            "检查 LibreOffice/PDF 输出。",
        )])

    text_metrics, text_finding = _pdf_text_fidelity(
        ctx.docx_path,
        pdf_path,
        pages,
        min_cjk_ratio,
        min_bigram_coverage,
        min_glyph_coverage,
        rid,
        Image,
    )
    if text_finding:
        findings.append(text_finding)

    page_items: list[dict] = []
    for page_index, page_path in enumerate(pages, 1):
        with Image.open(page_path) as image:
            rgb = image.convert("RGB")
            white = Image.new("RGB", rgb.size, "white")
            content_bbox = ImageChops.difference(rgb, white).getbbox()
            if content_bbox is None:
                findings.append(Finding(
                    rid, ctx.docx_path.name, page_index, "hard", f"第 {page_index} 页完全空白。",
                    "确认是否为意外分页；允许的空白页应在项目规则中显式声明。",
                    f"page-{page_index:04d}",
                ))
            elif min(content_bbox[0], content_bbox[1], rgb.width - content_bbox[2], rgb.height - content_bbox[3]) < 2:
                findings.append(Finding(
                    rid, ctx.docx_path.name, page_index, "hard", f"第 {page_index} 页内容触碰页面边缘，疑似裁切。",
                    "检查页边距、浮动图片和超宽表格。", f"page-{page_index:04d}",
                    {"content_bbox": list(content_bbox), "pixel_size": [rgb.width, rgb.height]},
                ))
            page_items.append({
                "artifact_id": f"page-{page_index:04d}",
                "kind": "docx_page",
                "page": page_index,
                "source_file": ctx.docx_path.name,
                "line": page_index,
                "caption": f"DOCX 第 {page_index} 页",
                "context_before": "",
                "context_after": "",
                "png": page_path.relative_to(ctx.output_dir).as_posix(),
                "png_sha256": sha256_file(page_path),
                "pixel_size": [rgb.width, rgb.height],
                "content_bbox": list(content_bbox) if content_bbox else None,
            })

    manifest = {
        "schema_version": "1.0.0",
        "candidate_sha": ctx.candidate_sha,
        "docx_sha256": docx_sha,
        "pdf_sha256": sha256_file(pdf_path),
        "artifact_count": len(page_items),
        "artifacts": page_items,
    }
    manifest_sha = canonical_hash(manifest)
    manifest["page_manifest_sha"] = manifest_sha
    manifest_path = ctx.output_dir / f"docx-page-manifest-{ctx.candidate_sha[:12]}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    packet_paths = _create_page_packets(
        page_items, ctx.output_dir, packet_dir, Image, ImageDraw, ImageOps,
    )
    return CheckerOutput(
        findings=findings,
        metrics={
            "docx_sha256": docx_sha,
            "pdf": pdf_path.relative_to(ctx.output_dir).as_posix(),
            "pdf_sha256": manifest["pdf_sha256"],
            "renderer": renderer,
            "text_fidelity": text_metrics,
            "page_count": len(page_items),
            "page_manifest": manifest_path.name,
            "page_manifest_sha": manifest_sha,
            "contact_sheets": packet_paths,
            "renderer_warnings": warning_lines,
        },
        artifacts=page_items,
    )


def _missing_docx(ctx: GateContext, rid: str) -> Finding | None:
    if ctx.docx_path is None:
        return Finding(
            rid, "", 0, "hard", "docx/release 阶段缺少 --docx。",
            "传入作者实际查看的最终 DOCX；中间 XML 或单章样本不能替代 release 成品。",
        )
    if not ctx.docx_path.is_file():
        return Finding(
            rid, ctx.docx_path.name, 0, "hard", "--docx 文件不存在。",
            "传入实际导出的 DOCX。",
        )
    return None


def _xml_text(data: bytes) -> str:
    root = ET.fromstring(data)
    return "".join(node.text or "" for node in root.iter() if node.tag == f"{{{W_NS}}}t")


def _cm_to_twips(cm: float) -> int:
    return round(cm / 2.54 * 1440)


def math_ceil(value: float) -> int:
    integer = int(value)
    return integer if integer == value else integer + 1


def _page_number(path: Path) -> int:
    match = re.search(r"(\d+)$", path.stem)
    return int(match.group(1)) if match else 0


def _benign_soffice_warning(line: str) -> bool:
    """隔离 LibreOffice profile 首次创建 fontconfig cache 的固定提示不影响成品。"""
    normalized = line.strip().lower()
    return normalized.startswith("fontconfig warning: no <cachedir>") or normalized.startswith(
        "fontconfig warning: adding <cachedir"
    )


def _pdf_text_fidelity(
    docx_path,
    pdf_path,
    page_pngs,
    min_ratio,
    min_bigram,
    min_glyph,
    rid,
    Image,
):
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        return {}, Finding(
            rid, pdf_path.name, 0, "hard", "缺少 pdftotext，无法证明 PDF 与 DOCX 文本一致。",
            "安装 Poppler，或确保其 pdftotext 在 PATH。",
        )
    with zipfile.ZipFile(docx_path) as archive:
        source = _xml_text(archive.read("word/document.xml"))
        if "word/footnotes.xml" in archive.namelist():
            source += _xml_text(archive.read("word/footnotes.xml"))
    with tempfile.TemporaryDirectory(prefix="book-gate-bbox-") as temp_dir:
        bbox_path = Path(temp_dir) / "bbox.html"
        process = subprocess.run(
            [pdftotext, "-bbox-layout", str(pdf_path), str(bbox_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if process.returncode != 0 or not bbox_path.is_file():
            return {}, Finding(
                rid,
                pdf_path.name,
                0,
                "hard",
                f"pdftotext bbox 失败：{process.stderr.decode('utf-8', 'replace')[:300]}",
                "确认 PDF 完整且文字层可读。",
            )
        try:
            bbox_root = ET.parse(bbox_path).getroot()
        except ET.ParseError as exc:
            return {}, Finding(
                rid, pdf_path.name, 0, "hard", f"PDF 文字 bbox 无法解析：{exc}",
                "重新从当前 DOCX 导出 PDF。",
            )

    namespace = "{http://www.w3.org/1999/xhtml}"
    bbox_pages = bbox_root.findall(f".//{namespace}page")
    rendered_words = ["".join(word.itertext()) for word in bbox_root.findall(f".//{namespace}word")]
    rendered = "".join(rendered_words)
    source_cjk = "".join(re.findall(f"[{_CJK}]", source))
    rendered_cjk = "".join(re.findall(f"[{_CJK}]", rendered))
    length_ratio = len(rendered_cjk) / len(source_cjk) if source_cjk else 0.0
    source_bigrams = {source_cjk[i:i + 2] for i in range(max(0, len(source_cjk) - 1))}
    rendered_bigrams = {rendered_cjk[i:i + 2] for i in range(max(0, len(rendered_cjk) - 1))}
    bigram_coverage = (
        len(source_bigrams & rendered_bigrams) / len(source_bigrams)
        if source_bigrams else 0.0
    )
    sampled_words = 0
    visible_words = 0
    per_page: list[dict] = []
    for page_index, bbox_page in enumerate(bbox_pages):
        if page_index >= len(page_pngs):
            break
        with Image.open(page_pngs[page_index]) as image:
            grayscale = image.convert("L")
            page_width = float(bbox_page.attrib.get("width", 0))
            page_height = float(bbox_page.attrib.get("height", 0))
            page_sampled = 0
            page_visible = 0
            for word in bbox_page.findall(f".//{namespace}word"):
                word_text = "".join(word.itertext())
                cjk_count = len(re.findall(f"[{_CJK}]", word_text))
                # 混排词可能仅由可见的拉丁字符提供墨迹；只抽检纯中文/中文标点词框。
                if cjk_count == 0 or re.search(r"[A-Za-z0-9]", word_text):
                    continue
                page_sampled += 1
                if _word_box_has_ink(grayscale, word, page_width, page_height, cjk_count):
                    page_visible += 1
            sampled_words += page_sampled
            visible_words += page_visible
            if page_sampled:
                per_page.append({
                    "page": page_index + 1,
                    "sampled": page_sampled,
                    "visible": page_visible,
                    "coverage": round(page_visible / page_sampled, 4),
                })
    glyph_coverage = visible_words / sampled_words if sampled_words else 0.0
    metrics = {
        "source_cjk_chars": len(source_cjk),
        "pdf_cjk_chars": len(rendered_cjk),
        "cjk_length_ratio": round(length_ratio, 4),
        "cjk_bigram_coverage": round(bigram_coverage, 4),
        "bbox_page_count": len(bbox_pages),
        "raster_page_count": len(page_pngs),
        "sampled_cjk_words": sampled_words,
        "visible_cjk_words": visible_words,
        "cjk_glyph_coverage": round(glyph_coverage, 4),
        "lowest_cjk_glyph_pages": sorted(per_page, key=lambda item: item["coverage"])[:10],
    }
    if (
        len(bbox_pages) != len(page_pngs)
        or length_ratio < min_ratio
        or bigram_coverage < min_bigram
        or glyph_coverage < min_glyph
    ):
        return metrics, Finding(
            rid, pdf_path.name, 0, "hard",
            "分页渲染不忠实："
            f"中文字符比 {length_ratio:.1%}、中文 bigram 覆盖 {bigram_coverage:.1%}、"
            f"可见中文词框覆盖 {glyph_coverage:.1%}、页数 {len(bbox_pages)}/{len(page_pngs)}。",
            "改用 Microsoft Word/WPS 从当前 DOCX 导出 PDF，或补齐字体；不要审失真的 LibreOffice 替身。",
            details=metrics,
        )
    return metrics, None


def _word_box_has_ink(image, word, page_width: float, page_height: float, cjk_count: int) -> bool:
    """判断 PDF 声称存在的中文词框在栅格页上是否真的画出了字形。"""
    if page_width <= 0 or page_height <= 0:
        return False
    try:
        x0 = max(0, int(float(word.attrib["xMin"]) * image.width / page_width))
        y0 = max(0, int(float(word.attrib["yMin"]) * image.height / page_height))
        x1 = min(image.width, math_ceil(float(word.attrib["xMax"]) * image.width / page_width))
        y1 = min(image.height, math_ceil(float(word.attrib["yMax"]) * image.height / page_height))
    except (KeyError, TypeError, ValueError):
        return False
    if x1 <= x0 or y1 <= y0:
        return False
    histogram = image.crop((x0, y0, x1, y1)).histogram()
    dark_pixels = sum(histogram[:220])
    return dark_pixels >= max(4, cjk_count * 3)


def _create_page_packets(items, output_dir, packet_dir, Image, ImageDraw, ImageOps) -> list[str]:
    paths: list[str] = []
    per_packet = 4
    cell_w, cell_h = 420, 590
    for start in range(0, len(items), per_packet):
        subset = items[start:start + per_packet]
        sheet = Image.new("RGB", (cell_w * 2, cell_h * 2), "#D9D9D9")
        draw = ImageDraw.Draw(sheet)
        for position, item in enumerate(subset):
            column, row = position % 2, position // 2
            x, y = column * cell_w, row * cell_h
            with Image.open(output_dir / item["png"]) as original:
                thumb = ImageOps.contain(original.convert("RGB"), (cell_w - 20, cell_h - 42))
                sheet.paste(thumb, (x + (cell_w - thumb.width) // 2, y + 30))
            draw.text((x + 10, y + 8), f"PAGE {item['page']} / {item['artifact_id']}", fill="black")
        packet = packet_dir / f"packet-{start // per_packet + 1:03d}.png"
        sheet.save(packet, format="PNG", optimize=True)
        paths.append(packet.relative_to(output_dir).as_posix())
    return paths
