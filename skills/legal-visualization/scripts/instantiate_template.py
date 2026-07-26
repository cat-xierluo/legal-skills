#!/usr/bin/env python3
"""只替换 draw.io 模板 value 占位符，并在落盘前运行领域校验。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from validate_drawio import validate_file


PLACEHOLDER = re.compile(r"\{\{([A-Za-z0-9][A-Za-z0-9_.-]{0,127})\}\}")


class TemplateError(Exception):
    pass


def render_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        if any(isinstance(item, (dict, list)) for item in value):
            raise TemplateError("占位符列表只能包含标量")
        return "\n".join(str(item) for item in value)
    if isinstance(value, dict):
        raise TemplateError("占位符值不能是对象")
    return str(value)


def instantiate(template: Path, values: dict[str, Any]) -> tuple[ET.ElementTree, list[str]]:
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    tree = ET.parse(template, parser=parser)
    root = tree.getroot()
    placeholders: set[str] = set()
    invalid_locations: list[str] = []
    for element in root.iter():
        for attribute, raw in element.attrib.items():
            keys = PLACEHOLDER.findall(raw)
            if not keys:
                continue
            if attribute != "value":
                invalid_locations.append(f"{element.tag}.{attribute}")
            placeholders.update(keys)
    if invalid_locations:
        raise TemplateError(f"占位符只能出现在 mxCell value 中: {sorted(set(invalid_locations))}")
    missing = sorted(placeholders - values.keys())
    unused = sorted(values.keys() - placeholders)
    if missing:
        raise TemplateError(f"缺少占位符值: {missing}")
    if unused:
        raise TemplateError(f"提供了模板未使用的字段: {unused}")
    for element in root.iter():
        raw = element.get("value")
        if raw is None:
            continue
        element.set("value", PLACEHOLDER.sub(lambda match: render_value(values[match.group(1)]), raw))
    unresolved = [
        element.get("id")
        for element in root.iter("mxCell")
        if PLACEHOLDER.search(element.get("value") or "")
    ]
    if unresolved:
        raise TemplateError(f"仍有未解析占位符: {unresolved}")
    return tree, sorted(placeholders)


def write_validated(tree: ET.ElementTree, output: Path, force: bool) -> dict:
    if output.exists() and not force:
        raise TemplateError(f"输出已存在，使用 --force 才能覆盖: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb", suffix=".drawio", prefix=".instantiate-", dir=output.parent, delete=False
    )
    temp_path = Path(handle.name)
    handle.close()
    try:
        ET.indent(tree, space="  ")
        tree.write(temp_path, encoding="utf-8", xml_declaration=True)
        validation = validate_file(temp_path)
        if not validation["passed"]:
            raise TemplateError(
                "实例化结果未通过领域校验: "
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
    parser = argparse.ArgumentParser(description="锁定 draw.io 模板几何，只替换 value 占位符")
    parser.add_argument("template", help="含 {{placeholder}} 的 .drawio 模板")
    parser.add_argument("values", help="JSON 对象，键与占位符一致")
    parser.add_argument("output", help="输出 .drawio")
    parser.add_argument("--force", action="store_true", help="允许原子覆盖既有输出")
    parser.add_argument("--json", action="store_true", help="输出结构化报告")
    args = parser.parse_args()

    try:
        values = json.loads(Path(args.values).read_text(encoding="utf-8"))
        if not isinstance(values, dict):
            raise TemplateError("values 文件必须是 JSON 对象")
        tree, placeholders = instantiate(Path(args.template), values)
        validation = write_validated(tree, Path(args.output), args.force)
        report = {
            "ok": True,
            "template": args.template,
            "output": args.output,
            "placeholders": placeholders,
            "validation": validation,
        }
    except (OSError, json.JSONDecodeError, ET.ParseError, TemplateError) as exc:
        report = {"ok": False, "template": args.template, "output": args.output, "error": str(exc)}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report["ok"]:
        print(f"模板实例化完成: {args.output}")
        print(f"领域校验通过，替换字段: {', '.join(report['placeholders'])}")
    else:
        print(f"error: {report['error']}", file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
