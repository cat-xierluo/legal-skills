#!/usr/bin/env python3
"""把 VizSpec 2.1 的视觉角色编译进既有 draw.io，严格保持几何不变。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from check_vizspec import (
    DEFAULT_REGISTRY,
    MissingDependencyError,
    VizSpecError,
    load_registry,
    load_yaml,
    validate,
)
from validate_drawio import parse_style, validate_file


NODE_HOST_FIELDS = ("entities", "events", "amounts", "sections")
BARE_STYLE_KEYS = {"rhombus", "ellipse", "hexagon", "text", "swimlane", "group"}
SHAPE_STYLE_KEYS = {
    "shape",
    "rhombus",
    "ellipse",
    "hexagon",
    "doubleEllipse",
    "triangle",
    "actor",
    "rounded",
    "arcSize",
}


class CompileError(Exception):
    """VizSpec 无法安全应用到 draw.io。"""


def serialize_style(style: dict[str, str]) -> str:
    parts: list[str] = []
    for key, value in style.items():
        if key in BARE_STYLE_KEYS and value == "1":
            parts.append(key)
        else:
            parts.append(f"{key}={value}")
    return ";".join(parts) + (";" if parts else "")


def geometry_snapshot(root: ET.Element) -> dict[str, str]:
    result: dict[str, str] = {}
    for cell in root.iter("mxCell"):
        cell_id = cell.get("id")
        geometry = cell.find("mxGeometry")
        if cell_id and geometry is not None:
            result[cell_id] = ET.tostring(geometry, encoding="unicode")
    return result


def graph_cells(root: ET.Element) -> dict[str, ET.Element]:
    return {
        cell.get("id", ""): cell
        for cell in root.iter("mxCell")
        if cell.get("id")
    }


def node_declarations(spec: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for host in NODE_HOST_FIELDS:
        for item in spec.get(host, []):
            result.append(item)
    return result


def clear_shape(style: dict[str, str]) -> None:
    for key in SHAPE_STYLE_KEYS:
        style.pop(key, None)


def apply_shape(style: dict[str, str], token: str, registry: dict[str, Any]) -> None:
    definition = registry["shape_tokens"][token]
    if definition.get("preserve_container_shape"):
        return
    clear_shape(style)
    style.update({str(key): str(value) for key, value in definition["style"].items()})


def reset_status_style(style: dict[str, str]) -> None:
    style.pop("dashed", None)
    style.pop("dashPattern", None)


def compile_tree(
    tree: ET.ElementTree,
    spec: dict[str, Any],
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = registry or load_registry()
    spec_findings = validate(spec, registry)
    errors = [item for item in spec_findings if item["severity"] == "error"]
    if errors:
        raise CompileError(
            "VizSpec 校验失败: "
            + "; ".join(f"{item['path']} {item['message']}" for item in errors[:12])
        )

    root = tree.getroot()
    before_geometry = geometry_snapshot(root)
    cells = graph_cells(root)
    visual = spec.get("visual") or {}
    theme_name = visual.get("theme", "client_report")
    theme = registry["themes"][theme_name]
    density_name = visual.get("density") or theme["default_density"]
    density_style = registry["densities"][density_name]
    changes: list[dict[str, str]] = []

    for declaration in node_declarations(spec):
        node_id = declaration["id"]
        cell = cells.get(node_id)
        if cell is None:
            raise CompileError(f"draw.io 缺少 VizSpec 节点 id: {node_id}")
        if cell.get("vertex") != "1":
            raise CompileError(f"VizSpec 节点不是 draw.io vertex: {node_id}")

        role_name = declaration["visual_role"]
        role = registry["roles"][role_name]
        token = declaration.get("shape_token", role["shape_token"])
        emphasis_name = declaration.get("emphasis", "normal")
        status_name = declaration.get("epistemic_status", "confirmed")
        style = parse_style(cell.get("style"))

        apply_shape(style, token, registry)
        category = role["category"]
        style.update({str(key): str(value) for key, value in theme["categories"][category].items()})
        style.update({str(key): str(value) for key, value in density_style.items()})
        reset_status_style(style)
        style.update(
            {
                str(key): str(value)
                for key, value in registry["epistemic_statuses"][status_name].items()
            }
        )
        style.update(
            {str(key): str(value) for key, value in registry["emphasis"][emphasis_name].items()}
        )
        cell.set("style", serialize_style(style))
        cell.set("visualRole", role_name)
        cell.set("epistemicStatus", status_name)
        cell.set("visualEmphasis", emphasis_name)
        cell.set("visualTheme", theme_name)
        changes.append(
            {
                "id": node_id,
                "kind": "node",
                "role": role_name,
                "status": status_name,
                "emphasis": emphasis_name,
                "shape_token": token,
            }
        )

    for relation in spec.get("relations", []):
        relation_id = relation["id"]
        cell = cells.get(relation_id)
        if cell is None:
            raise CompileError(f"draw.io 缺少 VizSpec 关系 id: {relation_id}")
        if cell.get("edge") != "1":
            raise CompileError(f"VizSpec 关系不是 draw.io edge: {relation_id}")
        status_name = relation["status"]
        style = parse_style(cell.get("style"))
        reset_status_style(style)
        style.update(
            {
                str(key): str(value)
                for key, value in registry["relation_statuses"][status_name].items()
            }
        )
        cell.set("style", serialize_style(style))
        cell.set("relationStatus", status_name)
        cell.set("visualTheme", theme_name)
        changes.append(
            {"id": relation_id, "kind": "relation", "status": status_name}
        )

    after_geometry = geometry_snapshot(root)
    if before_geometry != after_geometry:
        raise CompileError("样式编译器改变了 mxGeometry；已阻断输出")
    return {
        "theme": theme_name,
        "density": density_name,
        "geometry_preserved": True,
        "changes": changes,
        "vizspec_findings": spec_findings,
    }


def write_validated(
    tree: ET.ElementTree,
    output: Path,
    force: bool,
) -> dict[str, Any]:
    if output.exists() and not force:
        raise CompileError(f"输出已存在，使用 --force 才能覆盖: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb", suffix=".drawio", prefix=".visual-role-", dir=output.parent, delete=False
    )
    temp_path = Path(handle.name)
    handle.close()
    try:
        tree.write(temp_path, encoding="utf-8", xml_declaration=True)
        validation = validate_file(temp_path)
        if not validation["passed"]:
            raise CompileError(
                "样式编译结果未通过领域校验: "
                + "; ".join(
                    item["message"]
                    for item in validation["findings"]
                    if item["severity"] == "error"
                )
            )
        os.replace(temp_path, output)
        validation["file"] = str(output)
        return validation
    finally:
        temp_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="把 VizSpec 视觉角色编译进 draw.io，只改样式、不改几何"
    )
    parser.add_argument("source", help="输入 .drawio")
    parser.add_argument("spec", help="VizSpec 2.1 YAML")
    parser.add_argument("output", help="输出 .drawio")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY, help="视觉注册表 JSON")
    parser.add_argument("--force", action="store_true", help="允许原子覆盖既有输出")
    parser.add_argument("--json", action="store_true", help="输出结构化报告")
    args = parser.parse_args()

    try:
        registry = load_registry(args.registry)
        spec = load_yaml(Path(args.spec))
        parser_xml = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
        tree = ET.parse(args.source, parser=parser_xml)
        compilation = compile_tree(tree, spec, registry)
        validation = write_validated(tree, Path(args.output), args.force)
        report: dict[str, Any] = {
            "ok": True,
            "source": args.source,
            "spec": args.spec,
            "output": args.output,
            "compilation": compilation,
            "validation": validation,
        }
        exit_code = 0
    except MissingDependencyError as exc:
        report = {"ok": False, "dependency_missing": True, "error": str(exc)}
        exit_code = 2
    except (OSError, ET.ParseError, VizSpecError, CompileError) as exc:
        report = {"ok": False, "error": str(exc)}
        exit_code = 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report["ok"]:
        print(f"样式编译完成: {args.output}")
        print("mxGeometry 未改变，领域校验通过")
    else:
        print(f"error: {report['error']}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
