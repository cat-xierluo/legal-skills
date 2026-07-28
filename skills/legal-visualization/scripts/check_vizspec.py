#!/usr/bin/env python3
"""校验 Legal Visualization VizSpec 2.1 的结构与视觉声明。

角色、主题、状态、强调、密度与形状 token 均从
config/visual-role-registry.json 读取，避免文档与校验器各自维护枚举。
脚本只报告问题，不修改 VizSpec 或 draw.io。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = SKILL_ROOT / "config" / "visual-role-registry.json"
NODE_HOST_FIELDS = ("entities", "events", "amounts", "sections")


class VizSpecError(Exception):
    """VizSpec 或注册表无法读取。"""


class MissingDependencyError(VizSpecError):
    """缺少 YAML 解析依赖。"""


def finding(severity: str, code: str, path: str, message: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "path": path, "message": message}


def load_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VizSpecError(f"无法读取视觉注册表 {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise VizSpecError(f"视觉注册表根节点必须是 JSON 对象: {path}")
    required = {"vizspec_version", "roles", "shape_tokens", "themes", "densities", "emphasis", "epistemic_statuses", "relation_statuses"}
    missing = sorted(required - data.keys())
    if missing:
        raise VizSpecError(f"视觉注册表缺少字段: {missing}")
    for field in required - {"vizspec_version"}:
        if not isinstance(data[field], dict) or not data[field]:
            raise VizSpecError(f"视觉注册表字段 {field!r} 必须是非空对象")

    shape_tokens = data["shape_tokens"]
    role_categories: set[str] = set()
    for role_name, role in data["roles"].items():
        if not isinstance(role, dict):
            raise VizSpecError(f"视觉角色 {role_name!r} 必须是对象")
        token = role.get("shape_token")
        category = role.get("category")
        if token not in shape_tokens:
            raise VizSpecError(f"视觉角色 {role_name!r} 引用未声明形状 token: {token!r}")
        if not _nonempty_string(category):
            raise VizSpecError(f"视觉角色 {role_name!r} 缺少非空 category")
        role_categories.add(category)

    for theme_name, theme in data["themes"].items():
        if not isinstance(theme, dict):
            raise VizSpecError(f"主题 {theme_name!r} 必须是对象")
        density = theme.get("default_density")
        if density not in data["densities"]:
            raise VizSpecError(f"主题 {theme_name!r} 引用未声明默认密度: {density!r}")
        categories = theme.get("categories")
        if not isinstance(categories, dict):
            raise VizSpecError(f"主题 {theme_name!r} 缺少 categories 对象")
        missing_categories = sorted(role_categories - categories.keys())
        if missing_categories:
            raise VizSpecError(f"主题 {theme_name!r} 缺少角色类别样式: {missing_categories}")
    return data


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise MissingDependencyError(
            "缺少依赖 PyYAML；请运行: pip install pyyaml"
        ) from exc
    try:
        with path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except OSError as exc:
        raise VizSpecError(f"无法读取 VizSpec {path}: {exc}") from exc
    except yaml.YAMLError as exc:  # type: ignore[attr-defined]
        raise VizSpecError(f"VizSpec YAML 解析失败 {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise VizSpecError(f"VizSpec 根节点必须是 YAML 对象: {path}")
    return data


def _mapping(value: Any, path: str, findings: list[dict]) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        findings.append(finding("error", "type", path, "必须是对象"))
        return {}
    return value


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate(data: dict[str, Any], registry: dict[str, Any] | None = None) -> list[dict]:
    """返回稳定 finding 列表；任一 error 都应让 CLI 非零退出。"""
    registry = registry or load_registry()
    findings: list[dict] = []

    expected_version = str(registry["vizspec_version"])
    actual_version = str(data.get("vizspec_version", ""))
    if actual_version != expected_version:
        findings.append(
            finding(
                "error",
                "vizspec_version",
                "vizspec_version",
                f"必须为 {expected_version!r}，实际为 {actual_version!r}",
            )
        )

    routing = _mapping(data.get("routing"), "routing", findings)
    for key in ("primary_scene", "selection_reason"):
        if not _nonempty_string(routing.get(key)):
            findings.append(
                finding("error", "routing_required", f"routing.{key}", "必须填写非空字符串")
            )

    visual = _mapping(data.get("visual"), "visual", findings)
    themes = registry["themes"]
    densities = registry["densities"]
    theme = visual.get("theme", "client_report")
    density = visual.get("density")
    if theme not in themes:
        findings.append(
            finding("error", "theme", "visual.theme", f"非法主题 {theme!r}；合法值: {sorted(themes)}")
        )
    if density is None and theme in themes:
        density = themes[theme]["default_density"]
    if density not in densities:
        findings.append(
            finding("error", "density", "visual.density", f"非法密度 {density!r}；合法值: {sorted(densities)}")
        )
    if "icons" in visual:
        if not isinstance(visual["icons"], bool):
            findings.append(finding("error", "icons_type", "visual.icons", "必须是布尔值"))
        elif visual["icons"]:
            findings.append(
                finding("error", "icons_disabled", "visual.icons", "正式法律图禁用 emoji/icon 前缀；请设为 false 或删除字段")
            )

    roles = registry["roles"]
    shape_tokens = registry["shape_tokens"]
    emphases = registry["emphasis"]
    epistemic_statuses = registry["epistemic_statuses"]
    node_ids: set[str] = set()

    for host in NODE_HOST_FIELDS:
        items = data.get(host, [])
        if not isinstance(items, list):
            findings.append(finding("error", "type", host, "必须是数组"))
            continue
        for index, item in enumerate(items):
            path = f"{host}[{index}]"
            if not isinstance(item, dict):
                findings.append(finding("error", "type", path, "必须是对象"))
                continue
            node_id = item.get("id")
            if not _nonempty_string(node_id):
                findings.append(finding("error", "node_id", f"{path}.id", "必须填写非空字符串"))
            elif node_id in node_ids:
                findings.append(finding("error", "duplicate_id", f"{path}.id", f"节点 id 重复: {node_id}"))
            else:
                node_ids.add(node_id)

            role = item.get("visual_role")
            if role not in roles:
                findings.append(
                    finding("error", "visual_role", f"{path}.visual_role", f"非法或缺失角色 {role!r}；合法值: {sorted(roles)}")
                )
                continue

            expected_token = roles[role]["shape_token"]
            token = item.get("shape_token", expected_token)
            if token not in shape_tokens:
                findings.append(
                    finding("error", "shape_token", f"{path}.shape_token", f"非法形状 token {token!r}；合法值: {sorted(shape_tokens)}")
                )
            elif token != expected_token:
                findings.append(
                    finding("error", "shape_role_mismatch", f"{path}.shape_token", f"角色 {role!r} 必须使用 {expected_token!r}，不得覆盖为 {token!r}")
                )

            emphasis = item.get("emphasis", "normal")
            if emphasis not in emphases:
                findings.append(
                    finding("error", "emphasis", f"{path}.emphasis", f"非法强调等级 {emphasis!r}；合法值: {sorted(emphases)}")
                )

            status = item.get("epistemic_status", "confirmed")
            if status not in epistemic_statuses:
                findings.append(
                    finding("error", "epistemic_status", f"{path}.epistemic_status", f"非法事实状态 {status!r}；合法值: {sorted(epistemic_statuses)}")
                )

            if item.get("icon") not in (None, ""):
                findings.append(
                    finding("error", "icon_disabled", f"{path}.icon", "正式法律图禁用 emoji/icon 前缀")
                )
            if item.get("style_key") not in (None, ""):
                findings.append(
                    finding("warning", "style_key_deprecated", f"{path}.style_key", "style_key 已弃用；由 visual_role + theme + epistemic_status + emphasis 生成样式")
                )

    relation_statuses = registry["relation_statuses"]
    relation_ids: set[str] = set()
    relations = data.get("relations", [])
    if not isinstance(relations, list):
        findings.append(finding("error", "type", "relations", "必须是数组"))
    else:
        for index, relation in enumerate(relations):
            path = f"relations[{index}]"
            if not isinstance(relation, dict):
                findings.append(finding("error", "type", path, "必须是对象"))
                continue
            relation_id = relation.get("id")
            if not _nonempty_string(relation_id):
                findings.append(finding("error", "relation_id", f"{path}.id", "必须填写非空字符串"))
            elif relation_id in relation_ids or relation_id in node_ids:
                findings.append(finding("error", "duplicate_id", f"{path}.id", f"draw.io id 重复: {relation_id}"))
            else:
                relation_ids.add(relation_id)
            status = relation.get("status")
            if status not in relation_statuses:
                findings.append(
                    finding("error", "relation_status", f"{path}.status", f"非法或缺失关系状态 {status!r}；合法值: {sorted(relation_statuses)}")
                )
            for endpoint in ("source", "target"):
                endpoint_id = relation.get(endpoint)
                if not _nonempty_string(endpoint_id):
                    findings.append(finding("error", "relation_endpoint", f"{path}.{endpoint}", "必须填写节点 id"))
                elif endpoint_id not in node_ids:
                    findings.append(finding("error", "relation_endpoint", f"{path}.{endpoint}", f"引用未声明节点: {endpoint_id}"))

    if not any(item["severity"] == "error" for item in findings):
        findings.append(
            finding("ok", "vizspec", "$", f"VizSpec {expected_version} 声明有效；主题={theme}，密度={density}，节点={len(node_ids)}，关系={len(relation_ids)}")
        )
    return findings


def report_for(path: Path, registry: dict[str, Any]) -> dict[str, Any]:
    try:
        data = load_yaml(path)
        findings = validate(data, registry)
        return {"file": str(path), "ok": not any(item["severity"] == "error" for item in findings), "findings": findings}
    except MissingDependencyError as exc:
        return {"file": str(path), "ok": False, "dependency_missing": True, "error": str(exc)}
    except VizSpecError as exc:
        return {"file": str(path), "ok": False, "error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 Legal Visualization VizSpec 2.1")
    parser.add_argument("paths", nargs="+", help="VizSpec YAML 文件")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY, help="视觉注册表 JSON")
    parser.add_argument("--json", action="store_true", help="输出结构化 JSON")
    args = parser.parse_args()

    try:
        registry = load_registry(args.registry)
    except VizSpecError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2

    reports = [report_for(Path(raw), registry) for raw in args.paths]
    if args.json:
        print(json.dumps({"ok": all(item["ok"] for item in reports), "reports": reports}, ensure_ascii=False, indent=2))
    else:
        for report in reports:
            print(f"\n[{report['file']}]")
            if "error" in report:
                print(f"  ✗ {report['error']}")
                continue
            for item in report["findings"]:
                marker = {"ok": "✓", "warning": "!", "error": "✗"}[item["severity"]]
                print(f"  {marker} {item['path']}: {item['message']}")
    if any(item.get("dependency_missing") for item in reports):
        return 2
    return 0 if all(item["ok"] for item in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
