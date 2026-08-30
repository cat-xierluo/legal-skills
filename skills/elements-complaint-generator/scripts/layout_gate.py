#!/usr/bin/env python3
"""要素式诉状 DOCX/PDF 版式门禁。

该脚本是生成器之外的独立验证器，不修改被检文件。
它同时检查最终 DOCX 的 OOXML 不变量，以及 LibreOffice 实际渲染后 PDF 的页面几何。

依赖：
- DOCX 检查：lxml
- 真实渲染检查：LibreOffice（soffice）+ PyMuPDF（fitz）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

try:
    from lxml import etree
except ImportError:
    print("❌ 缺少依赖: lxml", file=sys.stderr)
    print("   请运行: pip install lxml", file=sys.stderr)
    raise SystemExit(2)


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{%s}" % W_NS
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
R = "{%s}" % R_NS
CONSTRAINT_IDS = (
    "ECG-LAYOUT-A4",
    "ECG-LAYOUT-CENTER",
    "ECG-LAYOUT-GRID",
    "ECG-LAYOUT-ROW-BREAK",
    "ECG-LAYOUT-PAGINATION",
    "ECG-LAYOUT-NO-BLANK-PAGE",
)


def _issue(code: str, message: str, *, stage: str, **context: Any) -> dict[str, Any]:
    item: dict[str, Any] = {"code": code, "stage": stage, "message": message}
    item.update(context)
    return item


def _int_attr(element, name: str, default: int = 0) -> int:
    if element is None:
        return default
    try:
        return int(element.get(W + name, str(default)))
    except (TypeError, ValueError):
        return default


def load_policy(policy_path: Path, template_name: str) -> dict[str, Any]:
    raw = json.loads(policy_path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1:
        raise ValueError(f"不支持的 layout policy schema: {raw.get('schema_version')!r}")
    policy = dict(raw.get("defaults") or {})
    policy.update((raw.get("templates") or {}).get(template_name, {}))
    policy["template_name"] = template_name
    return policy


def _section_ranges(body) -> list[tuple[int, int, Any]]:
    """返回 (start, end, sectPr)。sectPr 对应其前方的节。"""
    ranges: list[tuple[int, int, Any]] = []
    start = 0
    children = list(body)
    for index, child in enumerate(children):
        if child.tag != W + "p":
            continue
        sect = child.find("./" + W + "pPr/" + W + "sectPr")
        if sect is not None:
            ranges.append((start, index + 1, sect))
            start = index + 1
    body_sect = body.find("./" + W + "sectPr")
    if body_sect is not None:
        ranges.append((start, len(children), body_sect))
    return ranges


def _table_grid(table) -> list[int]:
    return [_int_attr(col, "w") for col in table.findall("./" + W + "tblGrid/" + W + "gridCol")]


def _page_geometry(sect) -> tuple[int, int, int, int]:
    size = sect.find("./" + W + "pgSz")
    margin = sect.find("./" + W + "pgMar")
    return (
        _int_attr(size, "w"),
        _int_attr(size, "h"),
        _int_attr(margin, "left"),
        _int_attr(margin, "right"),
    )


def _footer_facts(xml_bytes: bytes) -> tuple[int, int]:
    root = etree.fromstring(xml_bytes)
    instructions = " ".join((node.text or "") for node in root.iter(W + "instrText"))
    for field in root.iter(W + "fldSimple"):
        instructions += " " + (field.get(W + "instr") or "")
    page_fields = len(re.findall(r"\bPAGE\b", instructions, flags=re.IGNORECASE))
    hardcoded = 0
    for paragraph in root.iter(W + "p"):
        text = "".join(node.text or "" for node in paragraph.iter(W + "t")).strip()
        paragraph_instructions = " ".join(
            (node.text or "") for node in paragraph.iter(W + "instrText")
        )
        paragraph_instructions += " " + " ".join(
            (field.get(W + "instr") or "") for field in paragraph.iter(W + "fldSimple")
        )
        if text.isdigit() and not re.search(r"\bPAGE\b", paragraph_instructions, flags=re.IGNORECASE):
            hardcoded += 1
    return page_fields, hardcoded


def audit_docx(docx_path: Path, policy: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    measurements = {
        "sections": 0,
        "tables": 0,
        "rows": 0,
        "page_fields": 0,
        "hardcoded_page_numbers": 0,
        "footer_references": 0,
        "page_restarts": 0,
    }
    try:
        with zipfile.ZipFile(docx_path) as archive:
            document = etree.fromstring(archive.read("word/document.xml"))
            footer_facts: dict[str, tuple[int, int]] = {}
            footer_names = sorted(
                name for name in archive.namelist()
                if re.fullmatch(r"word/footer\d*\.xml", name)
            )
            for name in footer_names:
                page_fields, hardcoded = _footer_facts(archive.read(name))
                footer_facts[name] = (page_fields, hardcoded)
                measurements["page_fields"] += page_fields
                measurements["hardcoded_page_numbers"] += hardcoded
            relationship_targets: dict[str, str] = {}
            try:
                relationships = etree.fromstring(
                    archive.read("word/_rels/document.xml.rels")
                )
                for relationship in relationships:
                    if not (relationship.get("Type") or "").endswith("/footer"):
                        continue
                    target = (relationship.get("Target") or "").lstrip("/")
                    if not target.startswith("word/"):
                        target = "word/" + target
                    relationship_targets[relationship.get("Id") or ""] = target
            except KeyError:
                relationships = None
    except (OSError, KeyError, zipfile.BadZipFile, etree.XMLSyntaxError) as exc:
        return {
            "ok": False,
            "stage": "docx",
            "issues": [_issue("ECG-DOCX-INVALID", f"DOCX 不可解包或 XML 无效: {exc}", stage="docx")],
            "measurements": measurements,
        }

    body = document.find("./" + W + "body")
    if body is None:
        issues.append(_issue("ECG-DOCX-NO-BODY", "document.xml 缺少 w:body", stage="docx"))
        return {"ok": False, "stage": "docx", "issues": issues, "measurements": measurements}

    ranges = _section_ranges(body)
    measurements["sections"] = len(ranges)
    if not ranges:
        issues.append(_issue("ECG-LAYOUT-A4", "文档缺少节属性 sectPr", stage="docx"))

    all_tables = document.findall(".//" + W + "tbl")
    table_number = {id(table): index for index, table in enumerate(all_tables, 1)}
    measurements["tables"] = len(all_tables)

    for section_index, (start, end, sect) in enumerate(ranges, 1):
        page_width, page_height, left, right = _page_geometry(sect)
        if policy.get("require_a4", True):
            portrait = abs(page_width - 11906) <= 120 and abs(page_height - 16838) <= 120
            landscape = abs(page_width - 16838) <= 120 and abs(page_height - 11906) <= 120
            if not (portrait or landscape):
                issues.append(_issue(
                    "ECG-LAYOUT-A4",
                    f"第 {section_index} 节页面尺寸不是 A4: {page_width}×{page_height} twips",
                    stage="docx", section=section_index,
                ))
        if policy.get("require_table_center", True) and abs(left - right) > int(policy.get("center_tolerance_twips", 40)):
            issues.append(_issue(
                "ECG-LAYOUT-CENTER",
                f"第 {section_index} 节左右页边距不对称: {left}/{right} twips",
                stage="docx", section=section_index,
            ))

        section_tables = []
        for child in list(body)[start:end]:
            if child.tag == W + "tbl":
                section_tables.append(child)
            section_tables.extend(child.findall(".//" + W + "tbl"))

        usable = page_width - left - right
        for table in section_tables:
            number = table_number.get(id(table), 0)
            grid = _table_grid(table)
            grid_width = sum(grid)
            if not grid or any(width <= 0 for width in grid):
                issues.append(_issue(
                    "ECG-LAYOUT-GRID", f"表 {number} 缺少有效 tblGrid", stage="docx", table=number,
                ))
                continue
            if grid_width > usable:
                issues.append(_issue(
                    "ECG-LAYOUT-GRID",
                    f"表 {number} 宽 {grid_width} twips 超出第 {section_index} 节可用宽 {usable} twips",
                    stage="docx", section=section_index, table=number,
                ))

            properties = table.find("./" + W + "tblPr")
            justification = properties.find("./" + W + "jc") if properties is not None else None
            indent = properties.find("./" + W + "tblInd") if properties is not None else None
            layout = properties.find("./" + W + "tblLayout") if properties is not None else None
            if policy.get("require_table_center", True):
                if justification is None or justification.get(W + "val") != "center":
                    issues.append(_issue(
                        "ECG-LAYOUT-CENTER", f"表 {number} 未显式设为居中", stage="docx", table=number,
                    ))
                if indent is not None and _int_attr(indent, "w") != 0:
                    issues.append(_issue(
                        "ECG-LAYOUT-CENTER", f"表 {number} 仍有非零缩进", stage="docx", table=number,
                    ))
            if policy.get("require_fixed_table_layout", True):
                if layout is None or layout.get(W + "type") != "fixed":
                    issues.append(_issue(
                        "ECG-LAYOUT-GRID", f"表 {number} 未使用 fixed 列布局", stage="docx", table=number,
                    ))

            for row_index, row in enumerate(table.findall("./" + W + "tr"), 1):
                measurements["rows"] += 1
                row_properties = row.find("./" + W + "trPr")
                cant_split = row_properties.find("./" + W + "cantSplit") if row_properties is not None else None
                if policy.get("require_row_cant_split", True) and cant_split is None:
                    issues.append(_issue(
                        "ECG-LAYOUT-ROW-BREAK",
                        f"表 {number} 第 {row_index} 行未禁止非必要的跨页拆行",
                        stage="docx", table=number, row=row_index,
                    ))

                position = 0
                row_width = 0
                for cell_index, cell in enumerate(row.findall("./" + W + "tc"), 1):
                    cell_properties = cell.find("./" + W + "tcPr")
                    width_element = cell_properties.find("./" + W + "tcW") if cell_properties is not None else None
                    span_element = cell_properties.find("./" + W + "gridSpan") if cell_properties is not None else None
                    span = max(1, _int_attr(span_element, "val", 1))
                    cell_width = _int_attr(width_element, "w")
                    expected = sum(grid[position:position + span])
                    if width_element is None or width_element.get(W + "type", "dxa") != "dxa" or cell_width != expected:
                        issues.append(_issue(
                            "ECG-LAYOUT-GRID",
                            f"表 {number} 第 {row_index} 行第 {cell_index} 格宽 {cell_width} 与网格宽 {expected} 不一致",
                            stage="docx", table=number, row=row_index, cell=cell_index,
                        ))
                    row_width += cell_width
                    position += span
                if row_width != grid_width or position != len(grid):
                    issues.append(_issue(
                        "ECG-LAYOUT-GRID",
                        f"表 {number} 第 {row_index} 行宽/列数不守恒: {row_width}/{position}，表网格 {grid_width}/{len(grid)}",
                        stage="docx", table=number, row=row_index,
                    ))

        if policy.get("page_numbers", "required") == "required":
            default_footer = next(
                (
                    ref for ref in sect.findall("./" + W + "footerReference")
                    if ref.get(W + "type") == "default"
                ),
                None,
            )
            if default_footer is None:
                issues.append(_issue(
                    "ECG-LAYOUT-PAGINATION",
                    f"第 {section_index} 节没有显式默认页脚引用",
                    stage="docx", section=section_index,
                ))
            else:
                measurements["footer_references"] += 1
                relationship_id = default_footer.get(R + "id") or ""
                target = relationship_targets.get(relationship_id)
                if not target or target not in footer_facts:
                    issues.append(_issue(
                        "ECG-LAYOUT-PAGINATION",
                        f"第 {section_index} 节页脚关系 {relationship_id or '（缺失）'} 无效",
                        stage="docx", section=section_index,
                    ))
                elif footer_facts[target][0] == 0:
                    issues.append(_issue(
                        "ECG-LAYOUT-PAGINATION",
                        f"第 {section_index} 节所引用页脚没有 PAGE 域",
                        stage="docx", section=section_index,
                    ))

            numbering = sect.find("./" + W + "pgNumType")
            restart = _int_attr(numbering, "start", 0)
            if section_index == 1 and restart not in (0, int(policy.get("page_number_start", 1))):
                issues.append(_issue(
                    "ECG-LAYOUT-PAGINATION",
                    f"首节页码从 {restart} 开始，不是策略要求的 {policy.get('page_number_start', 1)}",
                    stage="docx", section=section_index,
                ))
            elif section_index > 1 and restart:
                measurements["page_restarts"] += 1
                issues.append(_issue(
                    "ECG-LAYOUT-PAGINATION",
                    f"第 {section_index} 节将页码重置为 {restart}",
                    stage="docx", section=section_index,
                ))

    page_policy = policy.get("page_numbers", "required")
    page_fields = measurements["page_fields"]
    hardcoded = measurements["hardcoded_page_numbers"]
    if hardcoded:
        issues.append(_issue(
            "ECG-LAYOUT-PAGINATION", f"页脚仍有 {hardcoded} 个硬编码页码", stage="docx",
        ))
    if page_policy == "required" and page_fields == 0:
        issues.append(_issue("ECG-LAYOUT-PAGINATION", "策略要求页码，但页脚没有 PAGE 域", stage="docx"))
    if page_policy == "forbidden" and page_fields:
        issues.append(_issue("ECG-LAYOUT-PAGINATION", "该法院基准件不带页码，但产物含 PAGE 域", stage="docx"))

    return {"ok": not issues, "stage": "docx", "issues": issues, "measurements": measurements}


def _find_soffice(explicit: Path | None = None) -> str | None:
    if explicit:
        return str(explicit) if explicit.exists() else None
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    mac = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    return str(mac) if mac.exists() else None


def render_docx(docx_path: Path, *, soffice: Path | None = None) -> tuple[Path, Path]:
    executable = _find_soffice(soffice)
    if not executable:
        raise RuntimeError(
            "缺少 LibreOffice/soffice，无法做真实渲染验证。"
            "macOS 可运行 brew install --cask libreoffice"
        )
    work = Path(tempfile.mkdtemp(prefix="ecg-layout-render-"))
    source = work / "candidate.docx"
    shutil.copy2(docx_path, source)
    proc = subprocess.run(
        [executable, "--headless", "--convert-to", "pdf", "--outdir", str(work), str(source)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    pdf = work / "candidate.pdf"
    if proc.returncode != 0 or not pdf.exists() or pdf.stat().st_size == 0:
        shutil.rmtree(work, ignore_errors=True)
        detail = (proc.stderr or proc.stdout or "").strip()[-500:]
        raise RuntimeError(f"LibreOffice 渲染失败（exit={proc.returncode}）: {detail}")
    return pdf, work


def _wide_horizontal_lines(page) -> list[tuple[float, float, float]]:
    lines: list[tuple[float, float, float]] = []
    minimum = page.rect.width * 0.45
    for drawing in page.get_drawings():
        for item in drawing.get("items", []):
            if item[0] == "l":
                start, end = item[1], item[2]
                if abs(start.y - end.y) <= 0.8 and abs(end.x - start.x) >= minimum:
                    lines.append((min(start.x, end.x), max(start.x, end.x), (start.y + end.y) / 2))
            elif item[0] == "re":
                rect = item[1]
                if rect.width >= minimum:
                    lines.append((rect.x0, rect.x1, rect.y0))
                    lines.append((rect.x0, rect.x1, rect.y1))
    return lines


def audit_pdf(pdf_path: Path, policy: dict[str, Any]) -> dict[str, Any]:
    try:
        import fitz
    except ImportError:
        return {
            "ok": False,
            "stage": "rendered",
            "issues": [_issue(
                "ECG-RENDER-DEPENDENCY",
                "缺少 PyMuPDF，无法检查渲染后表格几何。请运行: pip install pymupdf",
                stage="rendered",
            )],
            "measurements": {},
        }

    issues: list[dict[str, Any]] = []
    page_summaries: list[dict[str, Any]] = []
    document = fitz.open(pdf_path)
    a4_tolerance = float(policy.get("render_a4_tolerance_points", 2.0))
    center_tolerance = float(policy.get("render_center_tolerance_points", 2.5))
    page_number_tolerance = float(policy.get("render_page_number_center_tolerance_points", 18.0))
    page_policy = policy.get("page_numbers", "required")
    start = int(policy.get("page_number_start", 1))

    for page_index, page in enumerate(document, 1):
        width, height = page.rect.width, page.rect.height
        portrait = abs(width - 595.28) <= a4_tolerance and abs(height - 841.89) <= a4_tolerance
        landscape = abs(width - 841.89) <= a4_tolerance and abs(height - 595.28) <= a4_tolerance
        if policy.get("require_a4", True) and not (portrait or landscape):
            issues.append(_issue(
                "ECG-LAYOUT-A4", f"第 {page_index} 页渲染尺寸不是 A4: {width:.2f}×{height:.2f} pt",
                stage="rendered", page=page_index,
            ))

        words = page.get_text("words")
        drawings = page.get_drawings()
        # “只有页码”的页面在文本层并不为空，但对用户而言仍是空白页。
        # 先剔除页脚区纯数字，再判断是否还有正文文字或图形。
        substantive_words = [
            word for word in words
            if not (word[1] >= height - 70 and str(word[4]).strip().isdigit())
        ]
        is_blank = not substantive_words and not drawings
        if policy.get("forbid_blank_pages", True) and is_blank:
            issues.append(_issue(
                "ECG-LAYOUT-NO-BLANK-PAGE", f"第 {page_index} 页是空白页", stage="rendered", page=page_index,
            ))

        wide_lines = _wide_horizontal_lines(page)
        dominant = max(wide_lines, key=lambda item: item[1] - item[0], default=None)
        center_offset = None
        if dominant is not None:
            center_offset = (dominant[0] + dominant[1]) / 2 - width / 2
            if policy.get("require_table_center", True) and abs(center_offset) > center_tolerance:
                issues.append(_issue(
                    "ECG-LAYOUT-CENTER",
                    f"第 {page_index} 页表格中心偏移 {center_offset:.2f} pt（容差 {center_tolerance:.2f} pt）",
                    stage="rendered", page=page_index,
                ))

        footer_words = []
        for word in words:
            x0, y0, x1, y1, value = word[:5]
            if y0 >= height - 70 and str(value).strip().isdigit():
                footer_words.append((str(value).strip(), x0, x1))
        expected = str(start + page_index - 1)
        if page_policy == "required":
            matches = [item for item in footer_words if item[0] == expected]
            if not matches:
                issues.append(_issue(
                    "ECG-LAYOUT-PAGINATION",
                    f"第 {page_index} 页页脚缺少连续页码 {expected}",
                    stage="rendered", page=page_index,
                ))
            else:
                value, x0, x1 = matches[0]
                offset = (x0 + x1) / 2 - width / 2
                if abs(offset) > page_number_tolerance:
                    issues.append(_issue(
                        "ECG-LAYOUT-PAGINATION",
                        f"第 {page_index} 页页码未居中，偏移 {offset:.2f} pt",
                        stage="rendered", page=page_index,
                    ))
        elif page_policy == "forbidden" and footer_words:
            issues.append(_issue(
                "ECG-LAYOUT-PAGINATION",
                f"第 {page_index} 页不应带页码，但页脚发现数字 {footer_words[0][0]!r}",
                stage="rendered", page=page_index,
            ))

        page_summaries.append({
            "page": page_index,
            "width_points": round(width, 3),
            "height_points": round(height, 3),
            "table_center_offset_points": round(center_offset, 3) if center_offset is not None else None,
            "footer_numbers": [item[0] for item in footer_words],
            "blank": is_blank,
        })
    document.close()
    return {
        "ok": not issues,
        "stage": "rendered",
        "issues": issues,
        "measurements": {"pages": len(page_summaries), "page_summaries": page_summaries},
    }


def check(docx_path: Path, policy: dict[str, Any], *, rendered: bool, soffice: Path | None = None) -> dict[str, Any]:
    static = audit_docx(docx_path, policy)
    reports = [static]
    render_work: Path | None = None
    if static["ok"] and rendered:
        try:
            pdf, render_work = render_docx(docx_path, soffice=soffice)
            reports.append(audit_pdf(pdf, policy))
        except Exception as exc:
            reports.append({
                "ok": False,
                "stage": "rendered",
                "issues": [_issue("ECG-RENDER-FAILED", str(exc), stage="rendered")],
                "measurements": {},
            })
        finally:
            if render_work is not None:
                shutil.rmtree(render_work, ignore_errors=True)
    issues = [item for report in reports for item in report.get("issues", [])]
    digest = hashlib.sha256(docx_path.read_bytes()).hexdigest()
    return {
        "schema_version": 1,
        "status": "DOMAIN_VERIFIED" if not issues and rendered else ("DOCX_VERIFIED" if not issues else "FAIL"),
        "ok": not issues,
        "artifact": str(docx_path),
        "artifact_sha256": digest,
        "template_name": policy.get("template_name"),
        "mode": "rendered" if rendered else "docx",
        "passed_constraint_ids": list(CONSTRAINT_IDS) if not issues else [],
        "failed_constraint_ids": sorted({item["code"] for item in issues if item["code"].startswith("ECG-LAYOUT-")}),
        "issues": issues,
        "reports": reports,
    }


def main() -> int:
    skill_dir = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docx", type=Path, required=True)
    parser.add_argument("--template-name", required=True)
    parser.add_argument("--policy", type=Path, default=skill_dir / "config/layout-policy.json")
    parser.add_argument("--mode", choices=("docx", "rendered"), default="rendered")
    parser.add_argument("--soffice", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not args.docx.is_file():
        print(f"[layout-gate] 文件不存在: {args.docx}", file=sys.stderr)
        return 2
    try:
        policy = load_policy(args.policy, args.template_name)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[layout-gate] 策略读取失败: {exc}", file=sys.stderr)
        return 2

    report = check(args.docx, policy, rendered=args.mode == "rendered", soffice=args.soffice)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"[layout-gate] {report['status']} mode={report['mode']} sha256={report['artifact_sha256'][:12]}")
        for item in report["issues"]:
            print(f"  - {item['code']}: {item['message']}")
    return 0 if report["ok"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
