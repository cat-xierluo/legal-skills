#!/usr/bin/env python3
"""要素式诉状 DOCX/PDF 终稿版式门禁。

该脚本是生成器之外的独立验证器，不修改被检文件。
它同时检查最终 DOCX 的 OOXML 不变量，以及 LibreOffice 实际渲染后 PDF 的页面几何。

终稿级检查覆盖：
- 缺字/方框字可见性：源文本中的替换符/私用区/未分配码点，渲染层 .notdef 字形
  （仅在内嵌字体且同页无真实字形佐证时判定；未内嵌字体由阅读器回退，不误判），
  以及“源文本中文字符在渲染 PDF 中存活率”比对（官方模板的 □ 复选框属合法内容，不误报）。
- 表格整体水平居中：DOCX 层显式居中 + 对称边距；渲染层按每个表格带各自的
  列边界逐表复核，无竖线带页面退回宽横线并集整页复核。
- 跨页列几何一致：渲染层逐页分带提取竖线列位签名，前一页表格触底续页时
  列位必须一致；DOCX 层要求紧邻表格（跨页续接的物理拆表）网格完全一致。
- 单元格与段落对齐：渲染层要求单元格文字不跨越本行实际存在的列边界
  （兼容合法合并单元格）；“显式 vAlign/jc 声明”属可选严格项，默认关闭
  （缺少显式 OOXML 属性不等于实际版式错误），由 *_declaration 开关按模板启用。
- 跨页重复表头：按模板 policy 的语义锚点精确定位目标表，DOCX 层验证约定的
  首部连续行均声明 tblHeader，渲染层验证该锚点确实出现在每个续页表格顶部；
  未配置合同的普通表格不参与重复表头检查。

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
import unicodedata
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
    "ECG-LAYOUT-GLYPH",
    "ECG-LAYOUT-COLUMN-GRID",
    "ECG-LAYOUT-CELL-ALIGN",
    "ECG-LAYOUT-HEADER-REPEAT",
    "ECG-LAYOUT-PUBLICATION-MARK",
)

# 段落/单元格对齐允许的显式取值（ST_Jc / ST_VerticalJc 的常规子集）。
VALID_PARAGRAPH_JC = {"left", "start", "center", "right", "end", "both", "distribute"}
VALID_CELL_VALIGN = {"top", "center", "bottom"}


def _suspicious_glyph_chars(text: str) -> list[str]:
    """返回疑似“缺字/方框字”的字符：替换符、私用区、未分配码点。

    官方模板大量使用 □（U+25A1）作复选框（如“男□ 女□”），属合法内容，
    不在怀疑之列；这里只抓取任何正常字体都不该出现的码位。
    """
    suspects: list[str] = []
    for char in text:
        if char == "�":
            suspects.append(char)
            continue
        if unicodedata.category(char) in ("Co", "Cn"):
            suspects.append(char)
    return suspects


def _is_cjk_char(char: str) -> bool:
    """是否参与缺字比对的中日韩字符（含中文标点与全角形式）。"""
    codepoint = ord(char)
    return (
        0x3000 <= codepoint <= 0x303F
        or 0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xFF00 <= codepoint <= 0xFFEF
    )


def _cjk_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for char in text:
        if _is_cjk_char(char):
            counts[char] = counts.get(char, 0) + 1
    return counts


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


def _normalize_text(text: str) -> str:
    """移除排版空白，供 OOXML/PDF 两层稳定匹配语义锚点。"""
    return "".join(str(text or "").split())


def _semantic_header_contracts(
    policy: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """解析并校验表级重复表头合同；非法配置必须 fail-closed。"""
    section = policy.get("semantic_table_headers")
    if section is None:
        return [], []
    if not isinstance(section, dict):
        return [], ["semantic_table_headers 必须是对象"]
    if not section.get("enabled", True):
        return [], []
    raw_contracts = section.get("contracts")
    if not isinstance(raw_contracts, list) or not raw_contracts:
        return [], ["semantic_table_headers 已启用但 contracts 不是非空数组"]

    contracts: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_contracts, 1):
        if not isinstance(raw, dict):
            errors.append(f"第 {index} 个表级合同必须是对象")
            continue
        anchor = str(raw.get("anchor") or "").strip()
        header_rows = raw.get("header_rows")
        if not anchor:
            errors.append(f"第 {index} 个表级合同缺少 anchor")
            continue
        if isinstance(header_rows, bool) or not isinstance(header_rows, int) or header_rows < 1:
            errors.append(
                f"表级合同 {anchor!r} 的 header_rows 必须是正整数，实际为 {header_rows!r}"
            )
            continue
        normalized = _normalize_text(anchor)
        if normalized in seen:
            errors.append(f"表级合同锚点 {anchor!r} 重复配置")
            continue
        seen.add(normalized)
        contracts.append({
            "anchor": anchor,
            "normalized_anchor": normalized,
            "header_rows": header_rows,
        })
    return contracts, errors


def _on_off_enabled(element) -> bool:
    """解析 OOXML on/off 属性；无 val 与 true/1/on 均视为启用。"""
    if element is None:
        return False
    return str(element.get(W + "val", "true")).strip().lower() not in {
        "false", "0", "off", "no",
    }


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
        "semantic_header_contracts": 0,
        "semantic_header_tables": 0,
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
            relationship_types: dict[str, str] = {}
            try:
                relationships = etree.fromstring(
                    archive.read("word/_rels/document.xml.rels")
                )
                for relationship in relationships:
                    rel_type = relationship.get("Type") or ""
                    target = (relationship.get("Target") or "").lstrip("/")
                    if not target.startswith("word/"):
                        target = "word/" + target
                    relationship_targets[relationship.get("Id") or ""] = target
                    relationship_types[relationship.get("Id") or ""] = rel_type
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
    # 保留全局计数作为诊断信息，但绝不再把它当成渲染层的放行开关；重复表头
    # 是否必需、目标表是哪一张，统一由 semantic_table_headers 合同决定。
    measurements["tables_with_repeat_header"] = 0
    for table in all_tables:
        if len(table.findall("./" + W + "tr")) < 2:
            continue
        first_row_properties = table.find("./" + W + "tr/" + W + "trPr")
        if (first_row_properties is not None
                and first_row_properties.find("./" + W + "tblHeader") is not None):
            measurements["tables_with_repeat_header"] += 1

    semantic_contracts, semantic_errors = _semantic_header_contracts(policy)
    measurements["semantic_header_contracts"] = len(semantic_contracts)
    for message in semantic_errors:
        issues.append(_issue(
            "ECG-LAYOUT-HEADER-REPEAT",
            f"表级重复表头合同配置无效：{message}",
            stage="docx",
        ))

    # 表级合同是生成与门禁共享的不变量：锚点必须在全文唯一命中、位于目标表
    # 首行，且恰好前 header_rows 行声明 tblHeader。这样既不会被其他表的声明
    # 误放行，也能发现生成后 OOXML 被二次编辑或合同/模板发生漂移。
    for contract in semantic_contracts:
        anchor = contract["anchor"]
        hits: list[tuple[Any, Any]] = []
        for paragraph in document.iter(W + "p"):
            text = "".join(node.text or "" for node in paragraph.iter(W + "t"))
            if anchor not in text:
                continue
            node = paragraph.getparent()
            row = table = None
            while node is not None:
                if row is None and node.tag == W + "tr":
                    row = node
                elif table is None and node.tag == W + "tbl":
                    table = node
                    break
                node = node.getparent()
            hits.append((row, table))

        if len(hits) != 1:
            detail = "未命中" if not hits else f"命中 {len(hits)} 处"
            issues.append(_issue(
                "ECG-LAYOUT-HEADER-REPEAT",
                f"表级合同锚点 {anchor!r} {detail}，无法唯一定位目标表",
                stage="docx", anchor=anchor,
            ))
            continue
        row, table = hits[0]
        if row is None or table is None:
            issues.append(_issue(
                "ECG-LAYOUT-HEADER-REPEAT",
                f"表级合同锚点 {anchor!r} 位于表格外，无法定位目标表",
                stage="docx", anchor=anchor,
            ))
            continue
        rows = table.findall("./" + W + "tr")
        number = table_number.get(id(table), 0)
        if not rows or rows[0] is not row:
            position = rows.index(row) + 1 if row in rows else "?"
            issues.append(_issue(
                "ECG-LAYOUT-HEADER-REPEAT",
                f"表级合同锚点 {anchor!r} 位于表 {number} 第 {position} 行，不在首行",
                stage="docx", anchor=anchor, table=number,
            ))
            continue
        required = contract["header_rows"]
        if len(rows) < required:
            issues.append(_issue(
                "ECG-LAYOUT-HEADER-REPEAT",
                f"表 {number} 共 {len(rows)} 行，不足合同 {anchor!r} 要求的 {required} 行表头",
                stage="docx", anchor=anchor, table=number,
            ))
            continue
        measurements["semantic_header_tables"] += 1
        for row_index, target_row in enumerate(rows, 1):
            marker = target_row.find("./" + W + "trPr/" + W + "tblHeader")
            enabled = _on_off_enabled(marker)
            should_repeat = row_index <= required
            if should_repeat and not enabled:
                issues.append(_issue(
                    "ECG-LAYOUT-HEADER-REPEAT",
                    f"表 {number} 的语义表头第 {row_index}/{required} 行未启用 tblHeader",
                    stage="docx", anchor=anchor, table=number, row=row_index,
                ))
            elif not should_repeat and enabled:
                issues.append(_issue(
                    "ECG-LAYOUT-HEADER-REPEAT",
                    f"表 {number} 第 {row_index} 行是数据行，却仍启用 tblHeader",
                    stage="docx", anchor=anchor, table=number, row=row_index,
                ))

    if policy.get("require_visible_glyphs", True):
        body_text = "".join(node.text or "" for node in document.iter(W + "t"))
        suspects = _suspicious_glyph_chars(body_text)
        measurements["glyph_suspects"] = len(suspects)
        if suspects:
            issues.append(_issue(
                "ECG-LAYOUT-GLYPH",
                f"正文含 {len(suspects)} 个疑似缺字/方框字符（替换符/私用区/未分配码点）: "
                f"{''.join(sorted(set(suspects)))!r}",
                stage="docx",
            ))

    # 出版物页码残留（如 25-专利基准件的 430 竖排图片 / 431 旋转文本框）：
    # sanitizer 漏跑时在此 fail-closed。文本标记只查图形对象（VML 文本框/
    # txbxContent）内“整块文本恰为标记”的情况，普通正文的数字（案号/年份/
    # 金额/表格序号）不在此列；图片关系按策略 Target+sha256 精确点名，
    # 关系存在即违例（哈希与策略不符时单独提示需人工复核策略）。
    publication = policy.get("publication_mark_cleanup") or {}
    if publication.get("enabled"):
        for mark in (publication.get("forbidden_text_marks") or []):
            mark = str(mark)
            for box_tag in ("{urn:schemas-microsoft-com:vml}textbox", f"{W}txbxContent"):
                for box in document.iter(box_tag):
                    text = "".join(t.text or "" for t in box.iter(f"{W}t")).strip()
                    if text == mark:
                        issues.append(_issue(
                            "ECG-LAYOUT-PUBLICATION-MARK",
                            f"正文图形文本框残留出版物页码 {mark!r}，与页脚 PAGE 域构成双页码",
                            stage="docx",
                        ))
        for rule in (publication.get("forbidden_images") or []):
            target = str(rule.get("target") or "").strip().lstrip("/")
            expected_hash = str(rule.get("sha256") or "").lower()
            if not target:
                continue
            for rel_id, rel_target in relationship_targets.items():
                rel_clean = rel_target.lstrip("/")
                if not (rel_clean == target or rel_clean.endswith("/" + target)):
                    continue
                if expected_hash:
                    zip_name = rel_target if rel_target.startswith("word/") else "word/" + rel_target
                    actual_hash = ""
                    try:
                        with zipfile.ZipFile(docx_path) as archive:
                            actual_hash = hashlib.sha256(archive.read(zip_name)).hexdigest()
                    except (OSError, KeyError, zipfile.BadZipFile):
                        actual_hash = ""
                    if actual_hash and actual_hash != expected_hash:
                        issues.append(_issue(
                            "ECG-LAYOUT-PUBLICATION-MARK",
                            f"文档关系 {rel_id or '?'} 仍引用禁止的出版物页码图片 {target!r}"
                            f"（文件哈希 {actual_hash[:12]}… 与策略 {expected_hash[:12]}… 不符，"
                            "模板图片已被替换，请人工复核策略）",
                            stage="docx",
                        ))
                        continue
                issues.append(_issue(
                    "ECG-LAYOUT-PUBLICATION-MARK",
                    f"文档关系 {rel_id or '?'} 仍引用禁止的出版物页码图片 {target!r}",
                    stage="docx",
                ))

    # tblHeader/显式对齐属于“声明类”检查：缺少显式 OOXML 属性不等于实际版式
    # 错误（Word 默认行为同样合法），故默认关闭；实际版式由渲染层检查兜底。
    # 需要更严格的逐模板要求时，可通过 policy 的 *_declaration 开关显式启用。
    if policy.get("require_repeated_table_header_declaration", False):
        for table in all_tables:
            rows = table.findall("./" + W + "tr")
            if len(rows) < 2:
                continue
            row_properties = rows[0].find("./" + W + "trPr")
            has_header = (
                row_properties is not None
                and row_properties.find("./" + W + "tblHeader") is not None
            )
            if not has_header:
                issues.append(_issue(
                    "ECG-LAYOUT-HEADER-REPEAT",
                    f"表 {table_number.get(id(table), 0)} 为多行表，但首行未设置跨页重复表头（tblHeader）",
                    stage="docx", table=table_number.get(id(table), 0),
                ))

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
        previous_body_table = None
        for child in list(body)[start:end]:
            if child.tag == W + "tbl":
                section_tables.append(child)
                section_tables.extend(child.findall(".//" + W + "tbl"))
                # 紧邻表格通常是同一逻辑表跨页被拆成两张物理表；网格漂移会让
                # 续页列几何与首页对不上。网格完全一致才视为合法续接。
                if (previous_body_table is not None
                        and policy.get("require_column_geometry_consistency", True)):
                    previous_grid = _table_grid(previous_body_table)
                    current_grid = _table_grid(child)
                    if (previous_grid and current_grid and previous_grid != current_grid
                            and (len(previous_grid) == len(current_grid)
                                 or sum(previous_grid) == sum(current_grid))):
                        issues.append(_issue(
                            "ECG-LAYOUT-COLUMN-GRID",
                            f"第 {section_index} 节紧邻续接表网格不一致: "
                            f"{previous_grid} → {current_grid}",
                            stage="docx", section=section_index,
                        ))
                previous_body_table = child
            else:
                previous_body_table = None
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
                row_text = "".join(node.text or "" for node in row.iter(W + "t"))
                long_row_threshold = int(policy.get("long_row_split_min_chars", 300))
                explicitly_splittable = (
                    cant_split is not None
                    and (cant_split.get(W + "val") or "").lower()
                    in {"0", "false", "off", "no"}
                )
                if (policy.get("require_row_cant_split", True)
                        and (
                            cant_split is None
                            or (explicitly_splittable and len(row_text) < long_row_threshold)
                        )):
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
                    if policy.get("require_cell_alignment_declaration", False):
                        vertical = (
                            cell_properties.find("./" + W + "vAlign")
                            if cell_properties is not None else None
                        )
                        if vertical is None or vertical.get(W + "val") not in VALID_CELL_VALIGN:
                            issues.append(_issue(
                                "ECG-LAYOUT-CELL-ALIGN",
                                f"表 {number} 第 {row_index} 行第 {cell_index} 格未显式设置垂直对齐（vAlign）",
                                stage="docx", table=number, row=row_index, cell=cell_index,
                            ))
                        for paragraph in cell.findall("./" + W + "p"):
                            paragraph_text = "".join(
                                node.text or "" for node in paragraph.iter(W + "t")
                            ).strip()
                            if not paragraph_text:
                                continue
                            paragraph_properties = paragraph.find("./" + W + "pPr")
                            paragraph_jc = (
                                paragraph_properties.find("./" + W + "jc")
                                if paragraph_properties is not None else None
                            )
                            if (paragraph_jc is None
                                    or paragraph_jc.get(W + "val") not in VALID_PARAGRAPH_JC):
                                issues.append(_issue(
                                    "ECG-LAYOUT-CELL-ALIGN",
                                    f"表 {number} 第 {row_index} 行第 {cell_index} 格有文字段落未显式设置对齐方式（jc）",
                                    stage="docx", table=number, row=row_index, cell=cell_index,
                                ))
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


_RENDERER_VERSION_CACHE: dict[str, str] = {}


def _soffice_version(path: str) -> str:
    """缓存化地探测 soffice 的 --version 输出（如 'LibreOffice 25.8.4.2 ...'）。"""
    if path not in _RENDERER_VERSION_CACHE:
        try:
            proc = subprocess.run(
                [path, "--version"], capture_output=True, text=True, timeout=10, check=False,
            )
            first = (proc.stdout or "").strip().splitlines()
            _RENDERER_VERSION_CACHE[path] = first[0].strip() if first else ""
        except (OSError, subprocess.SubprocessError):
            _RENDERER_VERSION_CACHE[path] = ""
    return _RENDERER_VERSION_CACHE[path]


def _renderer_kind(version: str) -> str:
    """official=正式版；development=LibreOfficeDev/alpha 等 headless 开发构建。

    开发构建（如 Codex runtime 的 LibreOfficeDev 26.8 alpha）不暴露 macOS
    系统字体，渲染不出可靠中文视觉结果，只能作为正式版缺失时的最后回退，
    且此时 rendered 门禁会因真实缺字按 fail-closed 拦截。
    """
    if not version:
        return "unknown"
    lowered = version.lower()
    if "dev" in lowered or "alpha" in lowered or "beta" in lowered or "rc" in lowered:
        return "development"
    return "official"


def _candidate_soffice_paths() -> list[str]:
    """枚举候选 soffice（不写死任何版本号）；候选按发现顺序去重。"""
    candidates: list[str] = []
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        candidates.append(found)
    for app_dir in Path("/Applications").glob("LibreOffice*.app"):
        candidates.append(str(app_dir / "Contents" / "MacOS" / "soffice"))
    for cask_root in (Path("/opt/homebrew/Caskroom"), Path("/usr/local/Caskroom")):
        for cask_dir in sorted(cask_root.glob("libreoffice/*/LibreOffice.app")):
            candidates.append(str(cask_dir / "Contents" / "MacOS" / "soffice"))
    seen: set[str] = set()
    unique: list[str] = []
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        if Path(path).exists():
            unique.append(path)
    return unique


def _find_soffice(explicit: Path | None = None) -> str | None:
    """选择渲染器：显式 --soffice 优先；否则正式版 LibreOffice 优先，
    LibreOfficeDev/alpha 等开发构建只在正式版不存在时兜底。"""
    if explicit:
        return str(explicit) if explicit.exists() else None
    candidates = _candidate_soffice_paths()
    official = [c for c in candidates if _renderer_kind(_soffice_version(c)) == "official"]
    return (official or candidates or [None])[0]


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
    # 每次渲染用独立的 UserInstallation profile（由 LibreOffice 自行创建，
    # 不预创建），避免多进程并发渲染时抢同一个全局单实例锁导致
    # “渲染失败（exit=0）”的假失败。
    profile = work / "profile"
    proc = subprocess.run(
        [
            executable, "--headless",
            f"-env:UserInstallation={profile.as_uri()}",
            "--convert-to", "pdf", "--outdir", str(work), str(source),
        ],
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


def _vertical_segments(page, min_length: float) -> list[tuple[float, float, float]]:
    """提取页面上近似竖直的线段，返回 (x, y0, y1)，用于重建表格列几何。"""
    segments: list[tuple[float, float, float]] = []
    for drawing in page.get_drawings():
        for item in drawing.get("items", []):
            if item[0] == "l":
                start, end = item[1], item[2]
                if abs(start.x - end.x) <= 0.8 and abs(end.y - start.y) >= min_length:
                    segments.append((start.x, min(start.y, end.y), max(start.y, end.y)))
            elif item[0] == "re":
                rect = item[1]
                if rect.height >= min_length:
                    segments.append((rect.x0, rect.y0, rect.y1))
                    segments.append((rect.x1, rect.y0, rect.y1))
    return segments


def _cluster_positions(values: list[float], tolerance: float) -> list[float]:
    """把相近的坐标聚成簇，返回簇中心（升序）。"""
    clusters: list[list[float]] = []
    for value in sorted(values):
        if clusters and value - clusters[-1][-1] <= tolerance:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [sum(cluster) / len(cluster) for cluster in clusters]


def _font_key(name: str) -> str:
    """字体名归一化：去子集前缀 ABCDEF+、去空白/连字符/下划线，统一小写。"""
    cleaned = re.sub(r"^[A-Z]{6}\+", "", str(name or ""))
    return re.sub(r"[\s\-_]+", "", cleaned).lower()


def _embedded_font_keys(page) -> set[str] | None:
    """返回页面已内嵌字体的规范化名称集合；无法判定时返回 None（按内嵌处理，不豁免）。"""
    try:
        fonts = page.get_fonts()
    except Exception:
        return None
    embedded: set[str] = set()
    for item in fonts:
        ext = item[1] if len(item) > 1 else "n/a"
        basefont = item[3] if len(item) > 3 else ""
        if ext and ext != "n/a":
            embedded.add(_font_key(basefont))
    return embedded


def _font_matches_embedded(key: str, embedded: set[str]) -> bool:
    if not key:
        return False
    if key in embedded:
        return True
    # 内嵌子集常带命名差异（前缀/连字符），做双向包含匹配。
    return any(key in item or item in key for item in embedded if item)


def _is_fallback_recoverable(symbol: str) -> bool:
    """已正常分配的码位即使个别字体缺字形，PDF 阅读器（Adobe/Preview/MuPDF）
    都会按码位回退到有该字形的字体，不会在纸面呈现方框；能呈现成方框字的
    是无任何字体覆盖的码位（替换符/未分配/私用区/控制与代理区）。
    """
    if symbol == "�":
        return False
    return unicodedata.category(symbol) not in ("Cc", "Cn", "Co", "Cs")


def _notdef_glyphs(page) -> list[tuple[str, str]]:
    """返回真正缺字形（.notdef 且无法回退补救）的字符及其字体。

    glyph id 0 单独出现并不等于方框字，按三类可解释的证据豁免：
    - 码位已正常分配：阅读器按码位回退渲染，不呈现方框（见 _is_fallback_recoverable）；
    - 字体未内嵌（get_fonts ext 为 n/a）：阅读器用本地字体回退渲染缺字，
      LibreOffice 默认字体（如 LinuxLibertineG）常以未内嵌资源出现；
    - 同一字符在同页其他 span 已用非 0 字形渲染：字符可见，0 号字形只是
      字体归属伪影。
    内嵌字体中无字体覆盖码位（未分配/私用区/替换符）的 .notdef 仍照常拦截
    （TextWriter 未分配码位回归覆盖），配合存活率比对，真实方框字不会漏检。
    """
    trace = getattr(page, "get_texttrace", None)
    if trace is None:
        return []
    try:
        spans = trace()
    except Exception:
        return []
    embedded = _embedded_font_keys(page)
    rendered_unicodes = {
        int(char[0])
        for span in spans
        for char in span.get("chars", [])
        if int(char[1]) != 0
    }
    defects: list[tuple[str, str]] = []
    for span in spans:
        font = str(span.get("font") or "未知字体")
        font_is_embedded = embedded is None or _font_matches_embedded(
            _font_key(font), embedded
        )
        for char in span.get("chars", []):
            codepoint = int(char[0])
            symbol = chr(codepoint)
            if int(char[1]) != 0 or symbol.isspace():
                continue
            if _is_fallback_recoverable(symbol):
                continue  # 码位已分配：阅读器按码位回退，不会呈现方框
            if not font_is_embedded:
                continue  # 未内嵌字体：阅读器会回退渲染，不按方框字处理
            if codepoint in rendered_unicodes:
                continue  # 同页已有真实字形渲染：字符可见
            defects.append((symbol, font))
    return defects


def _table_bands(page, min_length: float, tolerance: float) -> list[dict[str, Any]]:
    """把页面竖线按 y 连续性聚成若干“表格带”，返回每带的列几何。

    同一页可能并排/上下有多个表格（官方模板常见），必须先分带，
    跨页列几何比对和单元格越界检查才能落到正确的表格上。
    """
    segments = _vertical_segments(page, min_length)
    if not segments:
        return []
    segments.sort(key=lambda segment: (segment[1], segment[0]))
    groups: list[list[tuple[float, float, float]]] = []
    for segment in segments:
        for group in groups:
            top = min(item[1] for item in group)
            bottom = max(item[2] for item in group)
            if segment[1] <= bottom + 4.0 and segment[2] >= top - 4.0:
                group.append(segment)
                break
        else:
            groups.append([segment])
    bands: list[dict[str, Any]] = []
    for group in groups:
        columns = _cluster_positions([item[0] for item in group], tolerance)
        if len(columns) < 3:
            continue
        bands.append({
            "columns": columns,
            "y0": min(item[1] for item in group),
            "y1": max(item[2] for item in group),
            "segments": group,
        })
    bands.sort(key=lambda band: band["y0"])
    return bands


def _table_top_line(page, geometry: dict[str, Any]) -> str:
    """提取表格区域内最顶部一行文字（规范化空白后返回），用于跨页表头比对。"""
    columns = geometry["columns"]
    x_low, x_high = columns[0] - 6.0, columns[-1] + 6.0
    y_low, y_high = geometry["y0"] - 6.0, geometry["y1"] + 6.0
    candidates = [
        word for word in page.get_text("words")
        if x_low <= word[0] and word[2] <= x_high and y_low <= word[1] and word[3] <= y_high
    ]
    if not candidates:
        return ""
    candidates.sort(key=lambda word: word[1])
    line_y = candidates[0][1]
    line = sorted(
        (word for word in candidates if word[1] <= line_y + 3.0),
        key=lambda word: word[0],
    )
    return "".join(str(word[4]) for word in line)


def _table_band_text(page, geometry: dict[str, Any]) -> str:
    """提取整个表格带文字，用于把语义锚点绑定到跨页候选带。"""
    columns = geometry["columns"]
    x_low, x_high = columns[0] - 6.0, columns[-1] + 6.0
    y_low, y_high = geometry["y0"] - 6.0, geometry["y1"] + 6.0
    words = [
        word for word in page.get_text("words")
        if x_low <= word[0] and word[2] <= x_high and y_low <= word[1] and word[3] <= y_high
    ]
    words.sort(key=lambda word: (round(word[1] / 3.0), word[0]))
    return "".join(str(word[4]) for word in words)


def _cell_crossings(page, geometry: dict[str, Any], tolerance: float) -> list[tuple[str, float]]:
    """找出跨越本行实际存在列边界的单元格文字。

    只有当该列位上确实存在覆盖文字所在行高的竖线时才判定越界，
    因此合法的合并单元格（该行该列位没有竖线）不会误报。
    """
    columns = geometry["columns"]
    segments = geometry["segments"]
    x_low, x_high = columns[0] - 4.0, columns[-1] + 4.0
    y_low, y_high = geometry["y0"] - 4.0, geometry["y1"] + 4.0
    crossings: list[tuple[str, float]] = []
    seen_rows: set[tuple[int, float]] = set()
    # ``get_text('words')`` 会在零内边距表格中把左单元格末字和右单元格
    # 首字拼成同一个“词”，从而制造跨列假阳性。rawdict 的 span 保留两侧
    # 独立绘制边界；用去除首尾空白后的真实字符包围盒判断视觉越线。
    raw = page.get_text("rawdict")
    for block in raw.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                chars = [char for char in span.get("chars", []) if not char.get("c", "").isspace()]
                if not chars:
                    continue
                x0 = min(char["bbox"][0] for char in chars)
                y0 = min(char["bbox"][1] for char in chars)
                x1 = max(char["bbox"][2] for char in chars)
                y1 = max(char["bbox"][3] for char in chars)
                text = "".join(char.get("c", "") for char in chars)[:80]
                if x0 < x_low or x1 > x_high or y0 < y_low or y1 > y_high:
                    continue
                for boundary in columns[1:-1]:
                    if not (x0 < boundary - tolerance and x1 > boundary + tolerance):
                        continue
                    if not any(
                        abs(segment[0] - boundary) <= 2.5
                        and (
                            min(segment[2], y1) - max(segment[1], y0)
                            >= max(1.5, min((y1 - y0) * 0.25, 4.0))
                        )
                        for segment in segments
                    ):
                        # 该列位在本行没有贯穿文字高度的竖线（合法合并单元格），
                        # 或竖线只在相邻行边界与 PDF 字形包围盒轻微相交；后者在
                        # LibreOffice/PyMuPDF 的小数坐标取整中会波动，不能算越界。
                        continue
                    key = (round(y0 / 4), boundary)
                    if key not in seen_rows:
                        seen_rows.add(key)
                        crossings.append((text, boundary))
                    break
    return crossings


def audit_pdf(
    pdf_path: Path,
    policy: dict[str, Any],
    *,
    docx_declares_repeat_header: bool | None = None,
) -> dict[str, Any]:
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
    column_tolerance = float(policy.get("column_alignment_tolerance_points", 1.5))
    cross_tolerance = float(policy.get("render_cell_cross_tolerance_points", 1.0))
    min_segment = float(policy.get("render_column_min_segment_points", 6.0))
    bottom_zone = float(policy.get("render_table_bottom_zone_points", 90.0))
    continuation_top = float(policy.get("render_continuation_top_points", 160.0))
    band_top_tolerance = float(policy.get("render_continuation_band_top_tolerance_points", 24.0))
    page_policy = policy.get("page_numbers", "required")
    start = int(policy.get("page_number_start", 1))
    check_columns = policy.get("require_column_geometry_consistency", True)
    check_alignment = policy.get("require_cell_alignment", True)
    check_header = policy.get("require_repeated_table_header", True)
    check_glyphs = policy.get("require_visible_glyphs", True)
    # 出版物页码文本标记（如 25-专利的 431）：页脚页码区之外的页边孤立文本
    # 命中即违例。栅格图片页码（430）不在可提取文本层，由 DOCX 关系门禁覆盖。
    forbidden_marks = [str(m) for m in (policy.get("forbidden_text_marks") or [])]
    semantic_contracts, semantic_errors = _semantic_header_contracts(policy)
    # 参数仅为兼容旧调用方保留。全局布尔值无法表达“哪一张表、几行表头”，
    # 不再参与判定；DOCX 静态门禁和 PDF 渲染门禁都以同一表级合同为准。
    _ = docx_declares_repeat_header
    for message in semantic_errors:
        issues.append(_issue(
            "ECG-LAYOUT-HEADER-REPEAT",
            f"表级重复表头合同配置无效：{message}",
            stage="rendered",
        ))

    previous: dict[str, Any] | None = None
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

        # 表格列几何：竖线按 y 连续性分带，每带独立成一张有框线表格。
        bands = _table_bands(page, min_segment, column_tolerance)
        for band in bands:
            band["reaches_bottom"] = band["y1"] >= height - bottom_zone

        # 整表水平居中：按每个表格带各自的列边界逐表复核——同页一左一右
        # 两个偏移表的合并包围盒中心可能恰好为零，合并检查会互相抵消。
        # 页面没有竖线带（无框线表格）时，退回用宽横线并集做整页复核。
        center_offset = None
        if bands:
            if policy.get("require_table_center", True):
                for band in bands:
                    left_edge, right_edge = band["columns"][0], band["columns"][-1]
                    offset = (left_edge + right_edge) / 2 - width / 2
                    band["center_offset"] = offset
                    if abs(offset) > center_tolerance:
                        issues.append(_issue(
                            "ECG-LAYOUT-CENTER",
                            f"第 {page_index} 页表格（x≈{left_edge:.0f}–{right_edge:.0f}）"
                            f"中心偏移 {offset:.2f} pt（容差 {center_tolerance:.2f} pt）",
                            stage="rendered", page=page_index,
                        ))
        elif wide_lines:
            left_edge = min(line[0] for line in wide_lines)
            right_edge = max(line[1] for line in wide_lines)
            center_offset = (left_edge + right_edge) / 2 - width / 2
            if policy.get("require_table_center", True) and abs(center_offset) > center_tolerance:
                issues.append(_issue(
                    "ECG-LAYOUT-CENTER",
                    f"第 {page_index} 页表格中心偏移 {center_offset:.2f} pt（容差 {center_tolerance:.2f} pt）",
                    stage="rendered", page=page_index,
                ))

        if check_glyphs:
            for symbol, font in _notdef_glyphs(page):
                issues.append(_issue(
                    "ECG-LAYOUT-GLYPH",
                    f"第 {page_index} 页字符 {symbol!r} 在字体 {font} 中缺字形（渲染为方框/空白）",
                    stage="rendered", page=page_index,
                ))
            suspects = _suspicious_glyph_chars(page.get_text())
            if suspects:
                issues.append(_issue(
                    "ECG-LAYOUT-GLYPH",
                    f"第 {page_index} 页渲染文本含 {len(suspects)} 个疑似缺字/方框字符: "
                    f"{''.join(sorted(set(suspects)))!r}",
                    stage="rendered", page=page_index,
                ))

        if check_alignment:
            for band in bands:
                for text, boundary in _cell_crossings(page, band, cross_tolerance):
                    issues.append(_issue(
                        "ECG-LAYOUT-CELL-ALIGN",
                        f"第 {page_index} 页单元格文字 {text!r} 跨过列边界 x≈{boundary:.1f} pt",
                        stage="rendered", page=page_index,
                    ))

        if forbidden_marks:
            edge_band = width * 0.2
            seen_marks: set[tuple[str, int]] = set()
            for word in words:
                value = str(word[4]).strip()
                if value not in forbidden_marks:
                    continue
                if not (word[0] < edge_band or word[2] > width - edge_band):
                    continue  # 页边带之外的正/表格数字不属出版物页码
                if word[1] >= height - 70:
                    continue  # 页脚区数字由页码检查负责
                key = (value, round(word[1] / 10))
                if key in seen_marks:
                    continue
                seen_marks.add(key)
                issues.append(_issue(
                    "ECG-LAYOUT-PUBLICATION-MARK",
                    f"第 {page_index} 页页边出现孤立出版物页码文本 {value!r}"
                    f"（x≈{word[0]:.0f}–{word[2]:.0f}）",
                    stage="rendered", page=page_index,
                ))

        # 跨页一致性：续接形态本身不依赖列检查开关。列位漂移只在启用对应
        # 约束时检查；表头则仅对上一页已由语义锚点绑定的目标表检查。
        continuation: dict[str, Any] | None = None
        previous_bottom = previous["bottom_band"] if previous else None
        active_anchors = previous.get("semantic_anchors", []) if previous else []
        if (previous_bottom is not None and bands
                and abs(previous["page_width"] - width) <= a4_tolerance
                and bands[0]["y0"] <= continuation_top):
            first = bands[0]
            continuation = first
            # 列位签名只统计“从本带顶部就开始”的竖线段：页面顶部实际续接的
            # 是上一页触底表格的延续部分，而同表后段的合法网格变化（合并行）
            # 或下方相邻表格的竖线（起点远低于带顶，如节间空档后的新表）不得
            # 混入签名，否则会把对齐良好的续表误报成列漂移。
            top_columns = _cluster_positions(
                [segment[0] for segment in first["segments"]
                 if segment[1] <= first["y0"] + band_top_tolerance],
                column_tolerance,
            )
            previous_columns = previous_bottom["columns"]

            def _has_column(values: list[float], x: float) -> bool:
                return any(abs(value - x) <= column_tolerance for value in values)

            # “上一表恰好在页底结束 + 下一张不同表恰好从页顶开始”与续表在外框
            # 几何上不可区分。只有存在表格身份连续证据时才判列漂移：已绑定语义
            # 锚点、顶部文本相同（重复表头），或至少一个内部列位保持不变。
            # 单一 OOXML 表自身网格与物理拆表的网格漂移仍由 DOCX 层兜底。
            previous_interior = previous_columns[1:-1]
            current_interior = top_columns[1:-1]
            interior_continuity = any(
                _has_column(previous_interior, x) for x in current_interior
            )
            current_top_line = _normalize_text(_table_top_line(page, first))
            previous_top_line = previous.get("bottom_band_top_line", "")
            same_top_line = bool(
                current_top_line and previous_top_line
                and current_top_line == previous_top_line
            )
            identity_confident = bool(
                active_anchors or interior_continuity or same_top_line
            )

            # 同一 tblGrid 的不同行可用不同 gridSpan 子集：内部边界既可能
            # 纯新增/消失，也可能合法地由一个位置换到另一个位置。PDF 几何
            # 无法区分这种行级合并与真实内部列漂移，故这里只硬判不会被
            # gridSpan 改变的表格左右外边界；内部网格守恒交给 DOCX 层的
            # tblGrid/tcW/gridSpan 检查。
            drifted = (
                not _has_column([previous_columns[0]], top_columns[0])
                or not _has_column([previous_columns[-1]], top_columns[-1])
            )
            if check_columns and identity_confident and drifted:
                issues.append(_issue(
                    "ECG-LAYOUT-COLUMN-GRID",
                    f"表格跨页后第 {previous['page']}→{page_index} 页列几何不一致: "
                    f"{[round(value, 1) for value in previous_columns]} → "
                    f"{[round(value, 1) for value in top_columns]}",
                    stage="rendered", page=page_index,
                ))
        if continuation is not None and check_header and active_anchors:
            actual_top = _table_top_line(page, continuation)
            normalized_top = _normalize_text(actual_top)
            for anchor in active_anchors:
                if anchor["normalized_anchor"] not in normalized_top:
                    issues.append(_issue(
                        "ECG-LAYOUT-HEADER-REPEAT",
                        f"语义表格 {anchor['anchor']!r} 跨页续接后，第 {page_index} 页"
                        f"顶部行 {actual_top!r} 未重复表题锚点",
                        stage="rendered", page=page_index, anchor=anchor["anchor"],
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
            "table_bands": [
                {
                    "column_x_positions": [round(value, 2) for value in band["columns"]],
                    "y0": round(band["y0"], 2),
                    "y1": round(band["y1"], 2),
                    "reaches_page_bottom": band["reaches_bottom"],
                    "center_offset_points": (
                        round(band["center_offset"], 3)
                        if "center_offset" in band else None
                    ),
                }
                for band in bands
            ],
            "footer_numbers": [item[0] for item in footer_words],
            "blank": is_blank,
        })
        # 触底带最多取一个：多个触底带说明页面结构异常，宁可不比对也不误报。
        bottom_bands = [band for band in bands if band["reaches_bottom"]]
        bottom_band = bottom_bands[0] if len(bottom_bands) == 1 else None
        semantic_anchors: list[dict[str, Any]] = []
        if bottom_band is not None:
            normalized_band = _normalize_text(_table_band_text(page, bottom_band))
            semantic_anchors = [
                contract for contract in semantic_contracts
                if contract["normalized_anchor"] in normalized_band
            ]
            # 续页可能只有重复表头/数据，若锚点因渲染缺陷未出现，仍须把上一页
            # 绑定关系传到下一续页，避免只拦第一处而漏掉更后面的续页。
            if continuation is bottom_band and active_anchors:
                known = {item["normalized_anchor"] for item in semantic_anchors}
                semantic_anchors.extend(
                    item for item in active_anchors
                    if item["normalized_anchor"] not in known
                )
        previous = {
            "page": page_index,
            "page_width": width,
            "bottom_band": bottom_band,
            "bottom_band_top_line": (
                _normalize_text(_table_top_line(page, bottom_band))
                if bottom_band else ""
            ),
            "semantic_anchors": semantic_anchors,
        }
    document.close()
    return {
        "ok": not issues,
        "stage": "rendered",
        "issues": issues,
        "measurements": {"pages": len(page_summaries), "page_summaries": page_summaries},
    }


def audit_text_survival(docx_path: Path, pdf_path: Path, policy: dict[str, Any]) -> dict[str, Any]:
    """比对源 DOCX 与渲染 PDF 的中文字符数量，机械验证“缺字”。

    方框字形（.notdef）有时仍能提取出原字符，反过来字体缺字也可能整段渲染为空；
    逐字符计数比对可以从内容侧兜住这两类逃逸。只比对中日韩字符，
    避免拉丁连字/空格规则差异造成噪音；表头在续页重复属合法复制，不影响“只多不少”方向。
    """
    try:
        import fitz
    except ImportError:
        return {
            "ok": False,
            "stage": "rendered",
            "issues": [_issue(
                "ECG-RENDER-DEPENDENCY",
                "缺少 PyMuPDF，无法比对渲染后文本是否缺字。请运行: pip install pymupdf",
                stage="rendered",
            )],
            "measurements": {},
        }
    try:
        with zipfile.ZipFile(docx_path) as archive:
            document = etree.fromstring(archive.read("word/document.xml"))
    except (OSError, KeyError, zipfile.BadZipFile, etree.XMLSyntaxError) as exc:
        return {
            "ok": False,
            "stage": "rendered",
            "issues": [_issue("ECG-LAYOUT-GLYPH", f"缺字比对无法读取源 DOCX: {exc}", stage="rendered")],
            "measurements": {},
        }
    source_text = "".join(node.text or "" for node in document.iter(W + "t"))
    rendered_text: list[str] = []
    pdf_document = fitz.open(pdf_path)
    try:
        for page in pdf_document:
            rendered_text.append(page.get_text())
    finally:
        pdf_document.close()

    source_counts = _cjk_counts(source_text)
    rendered_counts = _cjk_counts("".join(rendered_text))
    total = sum(source_counts.values())
    if total == 0:
        return {
            "ok": True, "stage": "rendered", "issues": [],
            "measurements": {"glyph_survival_ratio": 1.0, "missing_glyph_chars": 0},
        }
    deficits = {
        char: count - rendered_counts.get(char, 0)
        for char, count in source_counts.items()
    }
    deficits = {char: deficit for char, deficit in deficits.items() if deficit > 0}
    missing_total = sum(deficits.values())
    ratio = (total - missing_total) / total
    threshold = float(policy.get("min_glyph_survival_ratio", 0.995))
    issues: list[dict[str, Any]] = []
    if ratio < threshold:
        sample = "".join(sorted(deficits)[:12])
        issues.append(_issue(
            "ECG-LAYOUT-GLYPH",
            f"渲染后中文字符存活率 {ratio:.3f} 低于阈值 {threshold:.3f}，"
            f"共缺失 {missing_total} 字（如 {sample!r}）",
            stage="rendered",
        ))
    return {
        "ok": not issues,
        "stage": "rendered",
        "issues": issues,
        "measurements": {
            "glyph_survival_ratio": round(ratio, 4),
            "missing_glyph_chars": missing_total,
        },
    }


def check(docx_path: Path, policy: dict[str, Any], *, rendered: bool, soffice: Path | None = None) -> dict[str, Any]:
    static = audit_docx(docx_path, policy)
    reports = [static]
    render_work: Path | None = None
    selected_renderer: str | None = None
    if static["ok"] and rendered:
        selected_renderer = _find_soffice(soffice)
        try:
            if not selected_renderer:
                raise RuntimeError(
                    "缺少 LibreOffice/soffice，无法做真实渲染验证。"
                    "macOS 可运行 brew install --cask libreoffice"
                )
            version = _soffice_version(selected_renderer)
            if _renderer_kind(version) != "official":
                # fail-closed：headless 开发构建（LibreOfficeDev/alpha）不暴露
                # 系统中文字体，简单文档可能“缺字不明显”而误判通过，因此
                # 开发构建/未知版本一律不得作为 rendered 验收的渲染器。
                raise RuntimeError(
                    f"渲染器为开发构建或未知版本（{version or '未知'}），"
                    "不能作为中文视觉验收依据（fail-closed）："
                    f"{selected_renderer}。请安装正式版 LibreOffice。"
                )
            # 资格检查与实际执行必须同一路径：未显式指定 --soffice 时，
            # 把选址结果传给 render_docx，避免二次选址偏离。
            render_soffice = soffice if soffice is not None else Path(selected_renderer)
            pdf, render_work = render_docx(docx_path, soffice=render_soffice)
            reports.append(audit_pdf(pdf, policy))
            reports.append(audit_text_survival(docx_path, pdf, policy))
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
    renderer: dict[str, str] | None = None
    if rendered:
        renderer_path = selected_renderer or _find_soffice(soffice)
        if renderer_path:
            version = _soffice_version(renderer_path)
            renderer = {
                "path": renderer_path,
                "version": version,
                "kind": _renderer_kind(version),
            }
    return {
        "schema_version": 1,
        "status": "DOMAIN_VERIFIED" if not issues and rendered else ("DOCX_VERIFIED" if not issues else "FAIL"),
        "ok": not issues,
        "artifact": str(docx_path),
        "artifact_sha256": digest,
        "template_name": policy.get("template_name"),
        "mode": "rendered" if rendered else "docx",
        "renderer": renderer,
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
