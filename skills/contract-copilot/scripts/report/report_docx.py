#!/usr/bin/env python3
"""使用 OOXML 直接生成审查意见书 DOCX。"""

from __future__ import annotations

import html
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from ..docx.pack import pack_document

DOCUMENT_NAMESPACES = (
    'xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" '
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
    'xmlns:o="urn:schemas-microsoft-com:office:office" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
    'xmlns:v="urn:schemas-microsoft-com:vml" '
    'xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:w10="urn:schemas-microsoft-com:office:word" '
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
    'xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml" '
    'xmlns:w16cex="http://schemas.microsoft.com/office/word/2018/wordml/cex" '
    'xmlns:w16cid="http://schemas.microsoft.com/office/word/2016/wordml/cid" '
    'xmlns:w16="http://schemas.microsoft.com/office/word/2018/wordml" '
    'xmlns:w16du="http://schemas.microsoft.com/office/word/2023/wordml/word16du" '
    'xmlns:sl="http://schemas.openxmlformats.org/schemaLibrary/2006/main" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
    'xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
    'xmlns:lc="http://schemas.openxmlformats.org/drawingml/2006/lockedCanvas" '
    'xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram" '
    'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
    'mc:Ignorable="w14 w15 w16se w16cid w16 w16cex w16du wp14"'
)

PRIMARY_COLOR = "1E3A5F"
ACCENT_COLOR = "927F76"
ALT_FILL = "F5F0ED"
BORDER_COLOR = "D9D0CA"

BODY_FONT_EAST_ASIA = "仿宋_GB2312"
BODY_FONT_ASCII = "Times New Roman"
HEADING_FONT_EAST_ASIA = "微软雅黑"
HEADING_FONT_ASCII = "Arial"

CONTENT_TYPES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
  <Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""

ROOT_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""

DOCUMENT_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>
  <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
</Relationships>
"""

APP_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Microsoft Office Word</Application>
</Properties>
"""

STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault>
      <w:rPr>
        <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="仿宋_GB2312" w:cs="Times New Roman"/>
        <w:sz w:val="22"/>
        <w:szCs w:val="22"/>
        <w:lang w:val="en-US" w:eastAsia="zh-CN" w:bidi="ar-SA"/>
      </w:rPr>
    </w:rPrDefault>
    <w:pPrDefault/>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:qFormat/>
  </w:style>
</w:styles>
"""

SETTINGS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w10="urn:schemas-microsoft-com:office:word" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml" mc:Ignorable="w14 w15">
  <w:zoom w:percent="100"/>
</w:settings>
"""

NUMBERING_XML = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="0">
    <w:multiLevelType w:val="hybridMultilevel"/>
    <w:lvl w:ilvl="0">
      <w:start w:val="1"/>
      <w:numFmt w:val="bullet"/>
      <w:lvlText w:val="•"/>
      <w:lvlJc w:val="left"/>
      <w:pPr><w:ind w:left="360" w:hanging="220"/></w:pPr>
      <w:rPr><w:rFonts w:ascii="{BODY_FONT_ASCII}" w:hAnsi="{BODY_FONT_ASCII}" w:eastAsia="{BODY_FONT_EAST_ASIA}" w:cs="{BODY_FONT_ASCII}"/></w:rPr>
    </w:lvl>
    <w:lvl w:ilvl="1">
      <w:start w:val="1"/>
      <w:numFmt w:val="bullet"/>
      <w:lvlText w:val="◦"/>
      <w:lvlJc w:val="left"/>
      <w:pPr><w:ind w:left="600" w:hanging="220"/></w:pPr>
      <w:rPr><w:rFonts w:ascii="{BODY_FONT_ASCII}" w:hAnsi="{BODY_FONT_ASCII}" w:eastAsia="{BODY_FONT_EAST_ASIA}" w:cs="{BODY_FONT_ASCII}"/></w:rPr>
    </w:lvl>
    <w:lvl w:ilvl="2">
      <w:start w:val="1"/>
      <w:numFmt w:val="bullet"/>
      <w:lvlText w:val="▪"/>
      <w:lvlJc w:val="left"/>
      <w:pPr><w:ind w:left="840" w:hanging="220"/></w:pPr>
      <w:rPr><w:rFonts w:ascii="{BODY_FONT_ASCII}" w:hAnsi="{BODY_FONT_ASCII}" w:eastAsia="{BODY_FONT_EAST_ASIA}" w:cs="{BODY_FONT_ASCII}"/></w:rPr>
    </w:lvl>
  </w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
  <w:abstractNum w:abstractNumId="1">
    <w:multiLevelType w:val="multilevel"/>
    <w:lvl w:ilvl="0">
      <w:start w:val="1"/>
      <w:numFmt w:val="decimal"/>
      <w:lvlText w:val="%1."/>
      <w:lvlJc w:val="left"/>
      <w:pPr><w:ind w:left="360" w:hanging="220"/></w:pPr>
    </w:lvl>
    <w:lvl w:ilvl="1">
      <w:start w:val="1"/>
      <w:numFmt w:val="decimal"/>
      <w:lvlText w:val="%1.%2."/>
      <w:lvlJc w:val="left"/>
      <w:pPr><w:ind w:left="600" w:hanging="220"/></w:pPr>
    </w:lvl>
    <w:lvl w:ilvl="2">
      <w:start w:val="1"/>
      <w:numFmt w:val="decimal"/>
      <w:lvlText w:val="%1.%2.%3."/>
      <w:lvlJc w:val="left"/>
      <w:pPr><w:ind w:left="840" w:hanging="220"/></w:pPr>
    </w:lvl>
  </w:abstractNum>
  <w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>
</w:numbering>
"""


def _normalize_timestamp(value: str | None = None) -> tuple[str, str]:
    local_timezone = datetime.now().astimezone().tzinfo or timezone.utc
    if value:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M")
        except ValueError:
            parsed = datetime.now().astimezone(local_timezone)
    else:
        parsed = datetime.now().astimezone(local_timezone)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=local_timezone)
    utc_value = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%d %H:%M"), utc_value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _core_xml(title: str, author: str, timestamp_utc: str) -> str:
    title_escaped = html.escape(title, quote=False)
    author_escaped = html.escape(author, quote=False)
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{title_escaped}</dc:title>
  <dc:creator>{author_escaped}</dc:creator>
  <cp:lastModifiedBy>{author_escaped}</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{timestamp_utc}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{timestamp_utc}</dcterms:modified>
</cp:coreProperties>
"""


def _font_props(font_family: str = "body") -> tuple[str, str]:
    if font_family == "heading":
        return HEADING_FONT_EAST_ASIA, HEADING_FONT_ASCII
    return BODY_FONT_EAST_ASIA, BODY_FONT_ASCII


def _run_xml(
    text: str,
    *,
    bold: bool = False,
    size: int | None = None,
    color: str | None = None,
    font_family: str = "body",
) -> str:
    escaped = html.escape(text, quote=False)
    east_asia, ascii_font = _font_props(font_family)
    rpr_parts = [
        f'<w:rFonts w:ascii="{ascii_font}" w:hAnsi="{ascii_font}" '
        f'w:eastAsia="{east_asia}" w:cs="{ascii_font}"/>'
    ]
    if bold:
        rpr_parts.append("<w:b/>")
    if color:
        rpr_parts.append(f'<w:color w:val="{color}"/>')
    if size is not None:
        rpr_parts.append(f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>')
    rpr_xml = f"<w:rPr>{''.join(rpr_parts)}</w:rPr>"
    return f'<w:r>{rpr_xml}<w:t xml:space="preserve">{escaped}</w:t></w:r>'


def _field_run_xml(instruction: str, fallback_text: str, *, size: int = 21) -> str:
    east_asia, ascii_font = _font_props("body")
    run_props = (
        "<w:rPr>"
        f'<w:rFonts w:ascii="{ascii_font}" w:hAnsi="{ascii_font}" '
        f'w:eastAsia="{east_asia}" w:cs="{ascii_font}"/>'
        f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
        "</w:rPr>"
    )
    return (
        f'<w:r>{run_props}<w:fldChar w:fldCharType="begin"/></w:r>'
        f'<w:r>{run_props}<w:instrText xml:space="preserve"> {instruction} </w:instrText></w:r>'
        f'<w:r>{run_props}<w:fldChar w:fldCharType="separate"/></w:r>'
        f'<w:r>{run_props}<w:t>{html.escape(fallback_text, quote=False)}</w:t></w:r>'
        f'<w:r>{run_props}<w:fldChar w:fldCharType="end"/></w:r>'
    )


def _runs_xml(parts: Iterable[dict[str, object]]) -> str:
    return "".join(
        _run_xml(
            str(part.get("text") or ""),
            bold=bool(part.get("bold")),
            size=int(part["size"]) if part.get("size") is not None else None,
            color=str(part["color"]) if part.get("color") is not None else None,
            font_family=str(part.get("font_family") or "body"),
        )
        for part in parts
    )


def _split_label_value(text: str) -> tuple[str | None, str]:
    for separator in ("：", ":"):
        if separator in text:
            label, value = text.split(separator, 1)
            return f"{label}{separator}", value.lstrip()
    return None, text


def _label_value_runs(
    text: str,
    *,
    label_color: str = ACCENT_COLOR,
) -> str:
    parts: list[dict[str, object]] = []
    label, value = _split_label_value(text)
    if label is not None:
        parts.append(
            {
                "text": label,
                "bold": True,
                "size": 22,
                "color": label_color,
                "font_family": "heading",
            }
        )
        if value:
            parts.append(
                {
                    "text": value,
                    "size": 22,
                    "color": "000000",
                    "font_family": "body",
                }
            )
    else:
        parts.append(
            {
                "text": text,
                "size": 22,
                "color": "000000",
                "font_family": "body",
            }
        )
    return _runs_xml(parts)


def _paragraph_xml(
    text: str = "",
    *,
    kind: str = "body",
    level: int = 0,
    runs_xml: str | None = None,
) -> str:
    if kind == "blank":
        return '<w:p><w:pPr><w:spacing w:after="30"/></w:pPr></w:p>'
    if kind == "table_gap":
        return '<w:p><w:pPr><w:spacing w:after="20"/></w:pPr></w:p>'

    before = 0
    after = 60
    line = 300
    indent_xml = '<w:ind w:firstLine="360"/>'
    jc_xml = '<w:jc w:val="both"/>'
    shd_xml = ""
    border_xml = ""
    keep_next_xml = ""
    numpr_xml = ""

    if kind == "title":
        before = 120
        after = 160
        indent_xml = ""
        jc_xml = '<w:jc w:val="center"/>'
        line = 280
        runs_xml = runs_xml or _run_xml(
            text,
            bold=True,
            size=32,
            color=PRIMARY_COLOR,
            font_family="heading",
        )
    elif kind == "section":
        before = 160
        after = 70
        indent_xml = ""
        jc_xml = '<w:jc w:val="left"/>'
        shd_xml = f'<w:shd w:val="clear" w:color="auto" w:fill="{PRIMARY_COLOR}"/>'
        keep_next_xml = "<w:keepNext/>"
        runs_xml = runs_xml or _run_xml(
            text,
            bold=True,
            size=26,
            color="FFFFFF",
            font_family="heading",
        )
    elif kind == "subsection":
        before = 100
        after = 40
        indent_xml = ""
        jc_xml = '<w:jc w:val="left"/>'
        border_xml = (
            "<w:pBdr>"
            f'<w:left w:val="single" w:sz="10" w:space="6" w:color="{ACCENT_COLOR}"/>'
            "</w:pBdr>"
        )
        runs_xml = runs_xml or _run_xml(
            text,
            bold=True,
            size=22,
            color=PRIMARY_COLOR,
            font_family="heading",
        )
    elif kind == "meta":
        after = 16
        line = 280
        indent_xml = '<w:ind w:left="240" w:right="240"/>'
        jc_xml = '<w:jc w:val="left"/>'
        shd_xml = f'<w:shd w:val="clear" w:color="auto" w:fill="{ALT_FILL}"/>'
        border_xml = (
            "<w:pBdr>"
            f'<w:left w:val="single" w:sz="16" w:space="10" w:color="{ACCENT_COLOR}"/>'
            "</w:pBdr>"
        )
        runs_xml = runs_xml or _label_value_runs(text)
    elif kind == "list":
        after = 18
        line = 280
        indent_xml = ""
        jc_xml = '<w:jc w:val="left"/>'
        numpr_xml = (
            "<w:numPr>"
            f'<w:ilvl w:val="{min(max(level, 0), 2)}"/>'
            '<w:numId w:val="1"/>'
            "</w:numPr>"
        )
        runs_xml = runs_xml or _label_value_runs(text)
    elif kind == "numbered":
        after = 18
        line = 280
        indent_xml = ""
        jc_xml = '<w:jc w:val="left"/>'
        numpr_xml = (
            "<w:numPr>"
            f'<w:ilvl w:val="{min(max(level, 0), 2)}"/>'
            '<w:numId w:val="2"/>'
            "</w:numPr>"
        )
        runs_xml = runs_xml or _run_xml(
            text,
            size=22,
            color="000000",
            font_family="body",
        )
    else:
        runs_xml = runs_xml or _run_xml(
            text,
            size=22,
            color="000000",
            font_family="body",
        )

    ppr_xml = (
        "<w:pPr>"
        f"{numpr_xml}"
        f'<w:spacing w:before="{before}" w:after="{after}" w:line="{line}" w:lineRule="auto"/>'
        f"{jc_xml}{indent_xml}{shd_xml}{border_xml}{keep_next_xml}"
        "</w:pPr>"
    )
    return f"<w:p>{ppr_xml}{runs_xml}</w:p>"


def _table_paragraph_xml(
    text: str,
    *,
    role: str = "value",
    fill: str | None = None,
) -> str:
    if role == "header":
        runs_xml = _run_xml(
            text,
            bold=True,
            size=22,
            color="FFFFFF",
            font_family="heading",
        )
        jc_xml = '<w:jc w:val="left"/>'
    elif role == "label":
        runs_xml = _run_xml(
            text,
            bold=True,
            size=20,
            color=PRIMARY_COLOR,
            font_family="heading",
        )
        jc_xml = '<w:jc w:val="left"/>'
    else:
        runs_xml = _run_xml(
            text,
            size=20,
            color="000000",
            font_family="body",
        )
        jc_xml = '<w:jc w:val="left"/>'

    shd_xml = ""
    if fill:
        shd_xml = f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>'

    return (
        "<w:p>"
        "<w:pPr>"
        '<w:spacing w:before="0" w:after="0" w:line="260" w:lineRule="auto"/>'
        f"{jc_xml}{shd_xml}"
        "</w:pPr>"
        f"{runs_xml}"
        "</w:p>"
    )


def _table_cell_xml(
    text: str,
    *,
    width: int,
    fill: str | None = None,
    grid_span: int | None = None,
    role: str = "value",
) -> str:
    grid_span_xml = f'<w:gridSpan w:val="{grid_span}"/>' if grid_span else ""
    shd_xml = f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>' if fill else ""
    paragraph_xml = _table_paragraph_xml(text, role=role, fill=fill)
    return (
        "<w:tc>"
        "<w:tcPr>"
        f'<w:tcW w:w="{width}" w:type="dxa"/>'
        f"{grid_span_xml}"
        f"{shd_xml}"
        '<w:vAlign w:val="center"/>'
        "</w:tcPr>"
        f"{paragraph_xml}"
        "</w:tc>"
    )


def _finding_table_xml(title: str, rows: list[str]) -> str:
    total_width = 9360
    label_width = 1800
    value_width = total_width - label_width
    table_rows = [
        "<w:tr>"
        f"{_table_cell_xml(title, width=total_width, fill=PRIMARY_COLOR, grid_span=2, role='header')}"
        "</w:tr>"
    ]

    for raw_row in rows:
        label, value = _split_label_value(raw_row)
        if label is None:
            label_text = "说明"
            value_text = raw_row
        else:
            label_text = label.rstrip("：:")
            value_text = value or "未提及/待补充"
        table_rows.append(
            "<w:tr>"
            f"{_table_cell_xml(label_text, width=label_width, fill=ALT_FILL, role='label')}"
            f"{_table_cell_xml(value_text, width=value_width, role='value')}"
            "</w:tr>"
        )

    return (
        "<w:tbl>"
        "<w:tblPr>"
        f'<w:tblW w:w="{total_width}" w:type="dxa"/>'
        '<w:jc w:val="center"/>'
        "<w:tblBorders>"
        f'<w:top w:val="single" w:sz="8" w:space="0" w:color="{BORDER_COLOR}"/>'
        f'<w:left w:val="single" w:sz="8" w:space="0" w:color="{BORDER_COLOR}"/>'
        f'<w:bottom w:val="single" w:sz="8" w:space="0" w:color="{BORDER_COLOR}"/>'
        f'<w:right w:val="single" w:sz="8" w:space="0" w:color="{BORDER_COLOR}"/>'
        f'<w:insideH w:val="single" w:sz="6" w:space="0" w:color="{BORDER_COLOR}"/>'
        f'<w:insideV w:val="single" w:sz="6" w:space="0" w:color="{BORDER_COLOR}"/>'
        "</w:tblBorders>"
        "<w:tblCellMar>"
        '<w:top w:w="0" w:type="dxa"/>'
        '<w:left w:w="90" w:type="dxa"/>'
        '<w:bottom w:w="0" w:type="dxa"/>'
        '<w:right w:w="90" w:type="dxa"/>'
        "</w:tblCellMar>"
        "</w:tblPr>"
        f'<w:tblGrid><w:gridCol w:w="{label_width}"/><w:gridCol w:w="{value_width}"/></w:tblGrid>'
        f"{''.join(table_rows)}"
        "</w:tbl>"
    )


def _strip_numbering_prefix(text: str) -> str:
    return re.sub(r"^\s*\d+\.\s*", "", text).strip()


def _collect_finding_rows(lines: list[str], start_index: int) -> tuple[list[str], int]:
    rows: list[str] = []
    index = start_index
    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        if not stripped:
            index += 1
            continue
        if stripped.startswith("### ") or stripped.startswith("## "):
            break
        if re.match(r"^\s*-\s", raw_line):
            rows.append(re.sub(r"^\s*-\s", "", raw_line).strip())
        else:
            rows.append(stripped)
        index += 1
    return rows, index


def _markdown_to_paragraphs(markdown_content: str) -> str:
    paragraphs = []
    lines = markdown_content.splitlines()
    section_title = ""
    in_cover_meta = False
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        line = raw_line.rstrip()
        stripped = line.strip()
        if not line:
            if not in_cover_meta:
                paragraphs.append(_paragraph_xml("", kind="blank"))
            index += 1
            continue
        if stripped.startswith("# "):
            in_cover_meta = True
            paragraphs.append(_paragraph_xml(stripped[2:], kind="title"))
            index += 1
            continue
        if stripped.startswith("## "):
            in_cover_meta = False
            section_title = stripped[3:]
            paragraphs.append(_paragraph_xml(stripped[3:], kind="section"))
            index += 1
            continue
        if section_title in {"三、具体审查意见", "四、详细审查意见"} and stripped.startswith("### "):
            in_cover_meta = False
            rows, next_index = _collect_finding_rows(lines, index + 1)
            paragraphs.append(_finding_table_xml(stripped[4:], rows))
            paragraphs.append(_paragraph_xml("", kind="table_gap"))
            index = next_index
            continue
        if stripped.startswith("### "):
            in_cover_meta = False
            paragraphs.append(_paragraph_xml(stripped[4:], kind="subsection"))
            index += 1
            continue
        if in_cover_meta and stripped.startswith("- "):
            paragraphs.append(_paragraph_xml(stripped[2:], kind="meta"))
            index += 1
            continue
        if re.match(r"^\s*-\s", raw_line):
            level = (len(raw_line) - len(raw_line.lstrip(" "))) // 2
            content = re.sub(r"^\s*-\s", "", raw_line).strip()
            paragraphs.append(_paragraph_xml(content, kind="list", level=level))
            index += 1
            continue
        if re.match(r"^\s*\d+\.\s", raw_line):
            level = (len(raw_line) - len(raw_line.lstrip(" "))) // 2
            paragraphs.append(
                _paragraph_xml(_strip_numbering_prefix(stripped), kind="numbered", level=level)
            )
            index += 1
            continue
        in_cover_meta = False
        paragraphs.append(_paragraph_xml(stripped, kind="body"))
        index += 1
    return "".join(paragraphs)


def _footer_xml() -> str:
    line_run = _run_xml(
        "────────────",
        size=21,
        color=BORDER_COLOR,
        font_family="body",
    )
    separator_run = _run_xml(
        " / ",
        size=21,
        color=ACCENT_COLOR,
        font_family="heading",
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<w:p>"
        "<w:pPr>"
        '<w:spacing w:before="0" w:after="0"/>'
        '<w:jc w:val="center"/>'
        "</w:pPr>"
        f"{line_run}"
        f"{_field_run_xml('PAGE', '1')}"
        f"{separator_run}"
        f"{_field_run_xml('NUMPAGES', '1')}"
        f"{line_run}"
        "</w:p>"
        "</w:ftr>"
    )


def _document_xml(markdown_content: str) -> str:
    body_xml = _markdown_to_paragraphs(markdown_content)
    sect_pr = (
        '<w:sectPr>'
        '<w:footerReference w:type="default" r:id="rId3"/>'
        '<w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
        'w:header="720" w:footer="720" w:gutter="0"/>'
        '<w:pgNumType w:start="1"/>'
        '<w:cols w:space="720"/>'
        '<w:docGrid w:linePitch="360"/>'
        "</w:sectPr>"
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f"<w:document {DOCUMENT_NAMESPACES}>"
        f"<w:body>{body_xml}{sect_pr}</w:body>"
        "</w:document>"
    )


def write_review_report_docx(
    markdown_content: str,
    output_path: str | Path,
    *,
    title: str = "合同审查意见书",
    author: str = "合同审查助手",
    generated_at: str | None = None,
    validate: bool = True,
) -> Path:
    _, timestamp_utc = _normalize_timestamp(generated_at)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    files = {
        "[Content_Types].xml": CONTENT_TYPES_XML,
        "_rels/.rels": ROOT_RELS_XML,
        "docProps/core.xml": _core_xml(title=title, author=author, timestamp_utc=timestamp_utc),
        "docProps/app.xml": APP_XML,
        "word/document.xml": _document_xml(markdown_content),
        "word/_rels/document.xml.rels": DOCUMENT_RELS_XML,
        "word/styles.xml": STYLES_XML,
        "word/settings.xml": SETTINGS_XML,
        "word/numbering.xml": NUMBERING_XML,
        "word/footer1.xml": _footer_xml(),
    }

    with tempfile.TemporaryDirectory(prefix="review-report-docx-") as temp_dir:
        unpacked_dir = Path(temp_dir) / "unpacked"
        for relative_path, content in files.items():
            target = unpacked_dir / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        packed = pack_document(unpacked_dir, output, validate=validate)
        if not packed:
            raise ValueError("审查报告 DOCX 打包失败")

    return output
