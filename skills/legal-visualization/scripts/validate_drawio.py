#!/usr/bin/env python3
"""Legal Visualization draw.io 领域校验器。

校验 XML 结构、父子容器、节点几何碰撞、文本适配和长连线标签风险。
脚本只报告问题，不自动移动节点或改写文字。
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


CHECKS = (
    "mxgraph_model",
    "root_cells",
    "parent_relationships",
    "edge_geometry",
    "node_size",
    "geometry_overlap",
    "shape_diversity",
    "text_fit",
    "edge_label_risk",
    "xml_safe_comments",
)

CONTAINER_STYLE_KEYS = {"swimlane", "group"}
EDGE_LABEL_WARNING_UNITS = 8.0
EDGE_LABEL_ERROR_UNITS = 14.0
TAG_RE = re.compile(r"<[^>]+>")


def finding(check: str, severity: str, message: str, **extra: Any) -> dict:
    return {"check": check, "severity": severity, "message": message, **extra}


def parse_style(raw: str | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in (raw or "").split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            key, value = part.split("=", 1)
            result[key] = value
        else:
            result[part] = "1"
    return result


def number(raw: str | None, default: float = 0.0) -> float:
    try:
        return float(raw) if raw is not None else default
    except ValueError:
        return default


def graph_cells(root: ET.Element) -> tuple[ET.Element | None, dict[str, ET.Element]]:
    graph_root = root.find("root")
    if graph_root is None:
        return None, {}
    cells = {
        cell.get("id", ""): cell
        for cell in graph_root.findall("mxCell")
        if cell.get("id")
    }
    return graph_root, cells


def is_container(cell: ET.Element) -> bool:
    style = parse_style(cell.get("style"))
    return bool(CONTAINER_STYLE_KEYS.intersection(style)) or style.get("container") == "1"


def check_mxgraph_model(root: ET.Element, findings: list[dict]) -> None:
    if root.tag != "mxGraphModel":
        findings.append(finding("mxgraph_model", "error", f"根节点必须是 mxGraphModel，实际为 {root.tag}"))
        return
    findings.append(finding("mxgraph_model", "ok", "mxGraphModel 存在"))

    graph_root, cells = graph_cells(root)
    if graph_root is None:
        findings.append(finding("root_cells", "error", "缺少 root 子节点"))
        return
    missing = [cell_id for cell_id in ("0", "1") if cell_id not in cells]
    if missing:
        findings.append(finding("root_cells", "error", f"缺少保留节点: {missing}"))
    else:
        findings.append(finding("root_cells", "ok", 'id="0" 与 id="1" 保留节点齐备'))


def check_parent_relationships(root: ET.Element, findings: list[dict]) -> None:
    _, cells = graph_cells(root)
    issues: list[dict] = []
    for cell_id, cell in cells.items():
        if cell_id == "0":
            continue
        parent_id = cell.get("parent")
        if cell_id == "1":
            if parent_id != "0":
                issues.append({"id": cell_id, "reason": '保留节点 id="1" 必须 parent="0"'})
            continue
        if not parent_id or parent_id not in cells:
            issues.append({"id": cell_id, "reason": f"parent 不存在: {parent_id!r}"})
            continue
        if parent_id in {"0", "1"} or cell.get("vertex") != "1":
            continue
        parent = cells[parent_id]
        if parent.get("vertex") != "1":
            issues.append({"id": cell_id, "reason": f"父节点 {parent_id} 不是 vertex 容器"})
            continue
        geom = cell.find("mxGeometry")
        parent_geom = parent.find("mxGeometry")
        if geom is None or parent_geom is None:
            continue
        x = number(geom.get("x"))
        y = number(geom.get("y"))
        width = number(geom.get("width"))
        height = number(geom.get("height"))
        parent_width = number(parent_geom.get("width"))
        parent_height = number(parent_geom.get("height"))
        if x < 0 or y < 0 or x + width > parent_width + 0.01 or y + height > parent_height + 0.01:
            issues.append(
                {
                    "id": cell_id,
                    "reason": f"相对坐标超出父容器 {parent_id}",
                    "geometry": [x, y, width, height],
                    "parent_size": [parent_width, parent_height],
                }
            )
    if issues:
        findings.append(finding("parent_relationships", "error", f"{len(issues)} 个 parent/相对坐标问题", examples=issues[:8]))
    else:
        findings.append(finding("parent_relationships", "ok", "parent 引用与容器相对坐标有效"))


def check_edge_geometry(root: ET.Element, findings: list[dict]) -> None:
    bad: list[str | None] = []
    for cell in root.iter("mxCell"):
        if cell.get("edge") != "1":
            continue
        geom = cell.find("mxGeometry")
        if geom is None or geom.get("relative") != "1":
            bad.append(cell.get("id"))
    if bad:
        findings.append(finding("edge_geometry", "error", f"{len(bad)} 个 edge 缺少 mxGeometry relative=\"1\"", examples=bad[:8]))
    else:
        findings.append(finding("edge_geometry", "ok", "所有 edge 含 mxGeometry relative=\"1\""))


def check_node_size(root: ET.Element, findings: list[dict]) -> None:
    missing: list[str | None] = []
    for cell in root.iter("mxCell"):
        if cell.get("vertex") != "1":
            continue
        geom = cell.find("mxGeometry")
        if geom is None or number(geom.get("width")) <= 0 or number(geom.get("height")) <= 0:
            missing.append(cell.get("id"))
    if missing:
        findings.append(finding("node_size", "error", f"{len(missing)} 个节点缺少有效 width/height", examples=missing[:8]))
    else:
        findings.append(finding("node_size", "ok", "所有节点声明有效 width/height"))


def vertex_records(root: ET.Element) -> tuple[list[dict], dict[str, ET.Element]]:
    _, cells = graph_cells(root)
    origins: dict[str, tuple[float, float]] = {}

    def absolute_origin(cell_id: str, stack: tuple[str, ...] = ()) -> tuple[float, float]:
        if cell_id in origins:
            return origins[cell_id]
        if cell_id in stack:
            return 0.0, 0.0
        cell = cells[cell_id]
        geom = cell.find("mxGeometry")
        x = number(geom.get("x")) if geom is not None else 0.0
        y = number(geom.get("y")) if geom is not None else 0.0
        parent_id = cell.get("parent")
        if parent_id and parent_id not in {"0", "1"} and parent_id in cells:
            px, py = absolute_origin(parent_id, stack + (cell_id,))
            x += px
            y += py
        origins[cell_id] = (x, y)
        return x, y

    records: list[dict] = []
    for cell_id, cell in cells.items():
        if cell.get("vertex") != "1":
            continue
        geom = cell.find("mxGeometry")
        if geom is None:
            continue
        width = number(geom.get("width"))
        height = number(geom.get("height"))
        if width <= 0 or height <= 0:
            continue
        x, y = absolute_origin(cell_id)
        records.append(
            {
                "id": cell_id,
                "cell": cell,
                "parent": cell.get("parent"),
                "container": is_container(cell),
                "bbox": (x, y, width, height),
            }
        )
    return records, cells


def is_ancestor(ancestor_id: str, child_id: str, cells: dict[str, ET.Element]) -> bool:
    seen: set[str] = set()
    current = cells.get(child_id)
    while current is not None:
        parent_id = current.get("parent")
        if not parent_id or parent_id in seen:
            return False
        if parent_id == ancestor_id:
            return True
        seen.add(parent_id)
        current = cells.get(parent_id)
    return False


def contains(outer: tuple[float, float, float, float], inner: tuple[float, float, float, float]) -> bool:
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    return ix >= ox - 0.01 and iy >= oy - 0.01 and ix + iw <= ox + ow + 0.01 and iy + ih <= oy + oh + 0.01


def check_geometry_overlap(root: ET.Element, findings: list[dict]) -> None:
    records, cells = vertex_records(root)
    overlaps: list[dict] = []
    for index, left in enumerate(records):
        lx, ly, lw, lh = left["bbox"]
        for right in records[index + 1 :]:
            if is_ancestor(left["id"], right["id"], cells) or is_ancestor(right["id"], left["id"], cells):
                continue
            rx, ry, rw, rh = right["bbox"]
            intersection_width = min(lx + lw, rx + rw) - max(lx, rx)
            intersection_height = min(ly + lh, ry + rh) - max(ly, ry)
            if intersection_width <= 0.01 or intersection_height <= 0.01:
                continue
            if left["container"] and contains(left["bbox"], right["bbox"]):
                continue
            if right["container"] and contains(right["bbox"], left["bbox"]):
                continue
            overlaps.append(
                {
                    "left": left["id"],
                    "right": right["id"],
                    "intersection": [round(intersection_width, 2), round(intersection_height, 2)],
                }
            )
    if overlaps:
        findings.append(finding("geometry_overlap", "error", f"发现 {len(overlaps)} 对非容器节点发生正面积重叠", examples=overlaps[:12]))
    else:
        findings.append(finding("geometry_overlap", "ok", "未发现非容器节点正面积重叠"))


def base_shape(style: dict[str, str]) -> str:
    """从解析后的 style 字典提取基础形状 token，用于形状多样性统计。"""
    shape_attr = style.get("shape")
    if shape_attr:
        return shape_attr
    for key in ("doubleEllipse", "rhombus", "ellipse", "hexagon", "triangle", "actor"):
        if style.get(key) == "1":
            return key
    if style.get("rounded") == "1":
        return "capsule" if style.get("arcSize") == "50" else "rounded_rect"
    if style.get("text") == "1":
        return "text"
    return "rect"


def check_shape_diversity(root: ET.Element, findings: list[dict]) -> None:
    """统计非容器、非文本节点的基础形状分布，单一形状占比过高时告警（warning，不阻断）。

    直接量化"全方框"问题：若节点数 ≥ 5 且主导形状占比 > 80%，提示按
    shape-registry.md 用不同几何形状区分法律语义。标题、注释、图例等
    纯文本节点不计入，与 0.7.0 审查口径（非文本节点）保持一致。
    """
    counts: dict[str, int] = {}
    for cell in root.iter("mxCell"):
        if cell.get("vertex") != "1" or is_container(cell):
            continue
        shape = base_shape(parse_style(cell.get("style")))
        if shape == "text":
            continue  # 标题/注释/图例等纯文本节点不计入图形形状统计
        counts[shape] = counts.get(shape, 0) + 1
    total = sum(counts.values())
    if total < 5:
        findings.append(finding("shape_diversity", "ok", f"非容器节点 {total} 个 < 5，跳过形状多样性检查"))
        return
    dominant, dominant_count = max(counts.items(), key=lambda item: item[1])
    ratio = dominant_count / total
    detail = {
        "total": total,
        "dominant_shape": dominant,
        "dominant_count": dominant_count,
        "ratio": round(ratio, 3),
        "shape_counts": counts,
    }
    if ratio > 0.8:
        findings.append(
            finding(
                "shape_diversity",
                "warning",
                f"形状过于单一：{dominant} 占 {round(ratio * 100)}%（{dominant_count}/{total}），建议按 references/shape-registry.md 用不同形状区分法律语义",
                **detail,
            )
        )
    else:
        findings.append(finding("shape_diversity", "ok", f"形状分布合理，主导形状 {dominant} 占 {round(ratio * 100)}%", **detail))


def plain_text(value: str | None) -> str:
    raw = html.unescape(value or "")
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = TAG_RE.sub("", raw)
    return raw.replace("\r\n", "\n").replace("\r", "\n").strip()


def glyph_units(text: str) -> float:
    units = 0.0
    for char in text:
        if char == "\t":
            units += 2.0
        elif char.isspace():
            units += 0.35
        elif unicodedata.east_asian_width(char) in {"W", "F"}:
            units += 1.0
        elif unicodedata.category(char).startswith("P"):
            units += 0.5
        else:
            units += 0.56
    return units


def check_text_fit(root: ET.Element, findings: list[dict]) -> None:
    errors: list[dict] = []
    warnings: list[dict] = []
    for cell in root.iter("mxCell"):
        if cell.get("vertex") != "1" or is_container(cell):
            continue
        text = plain_text(cell.get("value"))
        if not text:
            continue
        geom = cell.find("mxGeometry")
        if geom is None:
            continue
        width = number(geom.get("width"))
        height = number(geom.get("height"))
        style = parse_style(cell.get("style"))
        font_size = max(number(style.get("fontSize"), 12.0), 1.0)
        spacing = number(style.get("spacing"), 0.0)
        horizontal_padding = 8.0 + 2 * spacing + number(style.get("spacingLeft")) + number(style.get("spacingRight"))
        vertical_padding = 8.0 + 2 * spacing + number(style.get("spacingTop")) + number(style.get("spacingBottom"))
        available_width = max(width - horizontal_padding, 1.0)
        lines = text.split("\n") or [""]
        line_widths = [glyph_units(line) * font_size for line in lines]
        wrap = style.get("whiteSpace") == "wrap"
        if wrap:
            visual_lines = sum(max(1, math.ceil(line_width / available_width)) for line_width in line_widths)
            required_height = visual_lines * font_size * 1.2 + vertical_padding
            ratio = required_height / max(height, 1.0)
            detail = {
                "id": cell.get("id"),
                "required_height": round(required_height, 2),
                "height": height,
                "estimated_lines": visual_lines,
            }
            if ratio > 1.25:
                errors.append(detail)
            elif ratio > 1.0:
                warnings.append(detail)
        else:
            required_width = max(line_widths, default=0.0) + horizontal_padding
            ratio = required_width / max(width, 1.0)
            detail = {
                "id": cell.get("id"),
                "required_width": round(required_width, 2),
                "width": width,
            }
            if ratio > 1.15:
                errors.append(detail)
            elif ratio > 1.0:
                warnings.append(detail)
    if errors:
        findings.append(finding("text_fit", "error", f"{len(errors)} 个节点存在确定性文本溢出风险", examples=errors[:12]))
    elif warnings:
        findings.append(finding("text_fit", "warning", f"{len(warnings)} 个节点接近文本容量上限", examples=warnings[:12]))
    else:
        findings.append(finding("text_fit", "ok", "未发现节点文本宽高溢出风险"))


def check_edge_label_risk(root: ET.Element, findings: list[dict]) -> None:
    errors: list[dict] = []
    warnings: list[dict] = []
    for cell in root.iter("mxCell"):
        if cell.get("edge") != "1":
            continue
        text = plain_text(cell.get("value"))
        if not text:
            continue
        units = glyph_units(text)
        detail = {"id": cell.get("id"), "label": text, "display_units": round(units, 2)}
        if units > EDGE_LABEL_ERROR_UNITS:
            errors.append(detail)
        elif units > EDGE_LABEL_WARNING_UNITS:
            warnings.append(detail)
    if errors:
        findings.append(finding("edge_label_risk", "error", f"{len(errors)} 个连线标签过长，必须移到独立文本节点、侧栏或图例", examples=errors[:12]))
    elif warnings:
        findings.append(finding("edge_label_risk", "warning", f"{len(warnings)} 个连线标签较长，需检查是否压住箭头或节点", examples=warnings[:12]))
    else:
        findings.append(finding("edge_label_risk", "ok", "未发现长连线标签风险"))


def check_xml_safe_comments(text: str, findings: list[dict]) -> None:
    issues: list[tuple[int, str]] = []
    in_comment = False
    for line_number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("<!--") and "-->" in stripped:
            content = stripped[4 : stripped.index("-->")]
            if "--" in content:
                issues.append((line_number, "单行注释内含双破折号"))
        elif stripped.startswith("<!--"):
            in_comment = True
            if "--" in stripped[4:]:
                issues.append((line_number, "注释起始行含双破折号"))
        elif in_comment and "-->" in stripped:
            in_comment = False
            if "--" in stripped[: stripped.index("-->")]:
                issues.append((line_number, "注释结束前含双破折号"))
    if issues:
        findings.append(finding("xml_safe_comments", "warning", f"发现 {len(issues)} 处注释双破折号", examples=issues[:8]))
    else:
        findings.append(finding("xml_safe_comments", "ok", "未发现破坏 XML 的注释字符组合"))


def validate_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    findings: list[dict] = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return {
            "file": str(path),
            "passed": False,
            "error": f"XML 解析失败: {exc}",
            "findings": [finding("xml_parse", "error", f"XML 解析失败: {exc}")],
        }
    check_mxgraph_model(root, findings)
    if root.tag == "mxGraphModel":
        check_parent_relationships(root, findings)
        check_edge_geometry(root, findings)
        check_node_size(root, findings)
        check_geometry_overlap(root, findings)
        check_shape_diversity(root, findings)
        check_text_fit(root, findings)
        check_edge_label_risk(root, findings)
        check_xml_safe_comments(text, findings)
    passed = not any(item["severity"] == "error" for item in findings)
    return {"file": str(path), "passed": passed, "findings": findings}


def collect_files(targets: list[str], recursive: bool) -> list[Path]:
    files: list[Path] = []
    for target in targets:
        path = Path(target)
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            iterator = path.rglob("*.drawio") if recursive else path.glob("*.drawio")
            files.extend(sorted(iterator))
        else:
            print(f"warning: 路径不存在 {path}", file=sys.stderr)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Legal Visualization draw.io 领域校验")
    parser.add_argument("paths", nargs="+", help=".drawio 文件或目录")
    parser.add_argument("--recursive", "-r", action="store_true", help="目录递归查找")
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    args = parser.parse_args()

    files = collect_files(args.paths, args.recursive)
    if not files:
        print("error: 没有找到 .drawio 文件", file=sys.stderr)
        return 2
    reports = [validate_file(path) for path in files]
    all_passed = all(report["passed"] for report in reports)
    if args.json:
        json.dump({"all_passed": all_passed, "reports": reports}, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        for report in reports:
            print(f"\n[{'PASS' if report['passed'] else 'FAIL'}] {report['file']}")
            for item in report["findings"]:
                icon = {"ok": "✓", "warning": "!", "error": "✗"}.get(item["severity"], "?")
                print(f"  {icon} [{item['check']}] {item['message']}")
        print(f"\n汇总：{len(reports)} 个文件，{sum(report['passed'] for report in reports)} 通过，{sum(not report['passed'] for report in reports)} 失败")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
