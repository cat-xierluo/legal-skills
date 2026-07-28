#!/usr/bin/env python3
"""Legal Visualization VizSpec 声明校验器。

校验 VizSpec YAML 中的 visual_role / theme / icons 字段是否合法，
对照 references/shape-registry.md 的视觉角色总表与主题清单。
脚本只报告问题，不自动改写 VizSpec。

依赖 PyYAML（可选）。未安装时跳过校验并提示，不阻断流程。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

# 合法视觉角色，见 references/shape-registry.md 视觉角色总表
VALID_VISUAL_ROLES = {
    "plaintiff", "defendant", "third_party", "witness", "person",
    "company", "court", "authority", "contract", "legal_doc",
    "evidence", "amount", "risk", "judgment", "procedure", "event",
    "section", "lane",
}

# 主题：本轮已实现 / 预留未实现
IMPLEMENTED_THEMES = {"client_report"}
RESERVED_THEMES = {"court_submit", "lawyer_workpaper"}

# 可能携带 visual_role 的列表字段
ROLE_HOST_FIELDS = ("entities", "amounts", "events", "relations", "sections", "annotations")


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        print(f"warning: 未安装 PyYAML，跳过 VizSpec 校验: {path}", file=sys.stderr)
        return {}
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return data if isinstance(data, dict) else {}


def collect_visual_roles(data: dict[str, Any]) -> list[tuple[str, str]]:
    """返回 (来源路径, visual_role 值) 列表。"""
    found: list[tuple[str, str]] = []
    for key in ROLE_HOST_FIELDS:
        items = data.get(key)
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            if isinstance(item, dict) and "visual_role" in item:
                found.append((f"{key}[{index}]", str(item["visual_role"])))
    return found


def validate(data: dict[str, Any]) -> list[dict]:
    findings: list[dict] = []
    if not data:
        return findings

    visual = data.get("visual")
    visual = visual if isinstance(visual, dict) else {}

    theme = visual.get("theme", data.get("theme"))
    if theme is not None:
        if theme in IMPLEMENTED_THEMES:
            findings.append({"severity": "ok", "message": f"theme 合法且已实现: {theme}"})
        elif theme in RESERVED_THEMES:
            findings.append({"severity": "warning", "message": f"theme {theme} 预留但本轮未实现，将回退 client_report"})
        else:
            findings.append({"severity": "error", "message": f"theme 非法: {theme!r}；合法值: client_report / court_submit / lawyer_workpaper"})

    icons = visual.get("icons", data.get("icons"))
    if icons is True:
        findings.append({"severity": "warning", "message": "icons=true：将渲染 emoji；法律图默认建议 false 以保持严肃"})

    roles = collect_visual_roles(data)
    if not roles:
        findings.append({"severity": "warning", "message": "未声明任何 visual_role；建议按 shape-registry.md 为节点声明语义角色"})
    else:
        illegal = [(src, role) for src, role in roles if role not in VALID_VISUAL_ROLES]
        if illegal:
            for src, role in illegal[:12]:
                findings.append({"severity": "error", "message": f"{src} visual_role 非法: {role!r}；合法值见 shape-registry.md 总表"})
        else:
            findings.append({"severity": "ok", "message": f"{len(roles)} 个节点 visual_role 合法"})

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Legal Visualization VizSpec 声明校验")
    parser.add_argument("paths", nargs="+", help="VizSpec YAML 文件")
    args = parser.parse_args()

    exit_code = 0
    for raw in args.paths:
        path = Path(raw)
        print(f"\n[{path}]")
        data = load_yaml(path)
        if not data:
            continue
        for item in validate(data):
            icon = {"ok": "✓", "warning": "!", "error": "✗"}.get(item["severity"], "?")
            print(f"  {icon} {item['message']}")
        if any(item["severity"] == "error" for item in validate(data)):
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
