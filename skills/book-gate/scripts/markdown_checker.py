#!/usr/bin/env python3
"""Markdown 源稿的可判定出版门禁。"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote
import re

from gate_models import CheckerOutput, Finding, GateContext


_DIAGRAM_FENCE_RE = re.compile(
    r"^\s*```\s*(mermaid|plantuml|puml|dot|graphviz|flowchart|"
    r"sequenceDiagram|classDiagram|erDiagram|stateDiagram|gantt|pie|"
    r"gitGraph|journey)\b",
    re.IGNORECASE,
)
_CJK = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
_ASCII_QUOTE_NEAR_CJK_RE = re.compile(
    rf"(?<![A-Za-z])'(?=[{_CJK}])|(?<=[{_CJK}])'(?![A-Za-z])"
)
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_NOTE_REF_RE = re.compile(r"\[\^([^\]]+)\]")
_NOTE_DEF_RE = re.compile(r"^\s*\[\^([^\]]+)\]:")


def _markdown_files(ctx: GateContext, requirement: dict) -> list[Path]:
    return [p for p in ctx.scope_files(requirement) if p.suffix.lower() == ".md"]


def _strip_inline_code(line: str) -> str:
    return re.sub(r"`[^`]*`", "", line)


def no_diagram_dsl(ctx: GateContext, requirement: dict) -> CheckerOutput:
    findings: list[Finding] = []
    rid = requirement["id"]
    for path in _markdown_files(ctx, requirement):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = _DIAGRAM_FENCE_RE.match(line)
            if match:
                findings.append(Finding(
                    rid,
                    ctx.rel(path),
                    number,
                    "hard",
                    f"发现非 SVG 图表 DSL：{match.group(1)}",
                    "把结构图重画为内联 SVG；目录树等文本示例不要使用图表 DSL 围栏。",
                ))
    return CheckerOutput(findings=findings)


def no_ascii_cjk_quote(ctx: GateContext, requirement: dict) -> CheckerOutput:
    findings: list[Finding] = []
    rid = requirement["id"]
    for path in _markdown_files(ctx, requirement):
        in_fence = False
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            clean = _strip_inline_code(line)
            for match in _ASCII_QUOTE_NEAR_CJK_RE.finditer(clean):
                start = max(0, match.start() - 6)
                end = min(len(clean), match.end() + 6)
                findings.append(Finding(
                    rid,
                    ctx.rel(path),
                    number,
                    "hard",
                    f"中文语境仍含 ASCII 单引号：{clean[start:end]}",
                    "源稿直接使用中文单引号‘’；不要依赖转换器猜测。",
                ))
    return CheckerOutput(findings=findings)


def figure_separation(ctx: GateContext, requirement: dict) -> CheckerOutput:
    """禁止两张图只隔图注而无正文承接。"""
    findings: list[Finding] = []
    rid = requirement["id"]
    for path in _markdown_files(ctx, requirement):
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            is_svg_end = "</svg>" in line
            is_image = bool(_IMAGE_RE.search(line))
            if not (is_svg_end or is_image):
                continue
            cursor = index + 1
            while cursor < len(lines) and not lines[cursor].strip():
                cursor += 1
            if cursor < len(lines) and _looks_like_caption(lines[cursor]):
                cursor += 1
                while cursor < len(lines) and not lines[cursor].strip():
                    cursor += 1
            if cursor < len(lines) and _looks_like_figure_start(lines[cursor]):
                findings.append(Finding(
                    rid,
                    ctx.rel(path),
                    cursor + 1,
                    "hard",
                    "两张图直接相邻，中间只有空行或图注，没有正文承接。",
                    "在两图之间补充解释前图结论并引出后图的正文；若内容重复则合并或删除。",
                ))
    return CheckerOutput(findings=findings)


def _looks_like_caption(line: str) -> bool:
    text = line.strip().replace("*", "").replace("_", "")
    return bool(re.match(r"^(?:图|表)\s*[0-9一二三四五六七八九十]", text))


def _looks_like_figure_start(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("<svg") or bool(_IMAGE_RE.search(stripped))


def image_targets_exist(ctx: GateContext, requirement: dict) -> CheckerOutput:
    findings: list[Finding] = []
    rid = requirement["id"]
    for path in _markdown_files(ctx, requirement):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in _IMAGE_RE.finditer(line):
                raw = match.group(1).strip().split(maxsplit=1)[0].strip("<>")
                if raw.startswith(("http://", "https://", "data:")):
                    continue
                raw = unquote(raw.split("#", 1)[0])
                if not raw:
                    continue
                candidates = [(path.parent / raw).resolve(), (ctx.project_root / raw).resolve()]
                if not any(target.exists() for target in candidates):
                    findings.append(Finding(
                        rid,
                        ctx.rel(path),
                        number,
                        "hard",
                        f"图片引用不存在：{raw}",
                        "修正相对路径或补齐出版候选图片；不得在转换时静默跳过。",
                    ))
    return CheckerOutput(findings=findings)


def footnote_references_resolve(ctx: GateContext, requirement: dict) -> CheckerOutput:
    findings: list[Finding] = []
    rid = requirement["id"]
    for path in _markdown_files(ctx, requirement):
        text = path.read_text(encoding="utf-8")
        definitions: dict[str, int] = {}
        refs: list[tuple[str, int]] = []
        for number, line in enumerate(text.splitlines(), 1):
            definition = _NOTE_DEF_RE.match(line)
            if definition:
                key = definition.group(1)
                if key in definitions:
                    findings.append(Finding(
                        rid, ctx.rel(path), number, "hard",
                        f"脚注定义重复：{key}",
                        "同一脚注 id 只保留一个定义。",
                    ))
                definitions[key] = number
                continue
            refs.extend((match.group(1), number) for match in _NOTE_REF_RE.finditer(line))
        for key, number in refs:
            if key not in definitions:
                findings.append(Finding(
                    rid, ctx.rel(path), number, "hard",
                    f"脚注引用没有定义：{key}",
                    "补齐 [^id]: 定义或删除悬空引用。",
                ))
    return CheckerOutput(findings=findings)
