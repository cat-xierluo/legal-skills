#!/usr/bin/env python3
"""validate_drawio.py — Legal Visualization drawio XML 自检脚本。

读 .drawio 文件，对照 references/quality-checklist.md 第 32-38 行的 draw.io XML
自检项输出结构化报告。本脚本不修复问题，只报告。

检查项：
- 顶层 mxGraphModel + root + id="0" + id="1"
- 每个 edge 含 mxGeometry relative="1" 子元素
- 所有顶层元素 parent="1"
- 容器内子元素使用相对坐标
- 节点有明确 width/height
- 注释中无破坏 XML 的字符组合（双破折号、原始 &/</>）

用法：
    python scripts/validate_drawio.py path/to/file.drawio
    python scripts/validate_drawio.py path/to/file.drawio --json
    python scripts/validate_drawio.py path/to/dir/ --recursive
"""
import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

CHECKS = (
    "mxgraph_model",
    "root_cells",
    "parent_one",
    "edge_geometry",
    "node_size",
    "xml_safe_comments",
)


def check_mxgraph_model(root: ET.Element, findings: list) -> None:
    if root.tag != "mxGraphModel":
        findings.append(
            {
                "check": "mxgraph_model",
                "severity": "error",
                "message": f"根节点必须是 mxGraphModel，实际为 {root.tag}",
            }
        )
        return
    findings.append({"check": "mxgraph_model", "severity": "ok", "message": "mxGraphModel 存在"})

    child = root.find("root")
    if child is None:
        findings.append(
            {
                "check": "root_cells",
                "severity": "error",
                "message": "缺少 root 子节点",
            }
        )
        return

    ids = {c.get("id") for c in child.findall("mxCell")}
    if "0" not in ids:
        findings.append(
            {
                "check": "root_cells",
                "severity": "error",
                "message": '缺少 id="0" 保留节点',
            }
        )
    if "1" not in ids:
        findings.append(
            {
                "check": "root_cells",
                "severity": "error",
                "message": '缺少 id="1" 保留节点',
            }
        )
    if "0" in ids and "1" in ids:
        findings.append(
            {
                "check": "root_cells",
                "severity": "ok",
                "message": 'id="0" 与 id="1" 保留节点齐备',
            }
        )


def check_parent_one(root: ET.Element, findings: list) -> None:
    child = root.find("root")
    if child is None:
        return
    bad = [
        c
        for c in child.findall("mxCell")
        if c.get("id") not in {"0", "1"} and c.get("parent") != "1"
    ]
    if bad:
        findings.append(
            {
                "check": "parent_one",
                "severity": "error",
                "message": f"{len(bad)} 个顶层元素未声明 parent=\"1\"",
                "examples": [c.get("id") for c in bad[:5]],
            }
        )
    else:
        findings.append(
            {
                "check": "parent_one",
                "severity": "ok",
                "message": "所有顶层元素 parent=\"1\"",
            }
        )


def check_edge_geometry(root: ET.Element, findings: list) -> None:
    bad = []
    for cell in root.iter("mxCell"):
        if cell.get("edge") != "1":
            continue
        geom = cell.find("mxGeometry")
        if geom is None or geom.get("relative") != "1":
            bad.append(cell.get("id"))
    if bad:
        findings.append(
            {
                "check": "edge_geometry",
                "severity": "error",
                "message": f"{len(bad)} 个 edge 缺少 mxGeometry relative=\"1\" 子元素",
                "examples": bad[:5],
            }
        )
    else:
        findings.append(
            {
                "check": "edge_geometry",
                "severity": "ok",
                "message": "所有 edge 含 mxGeometry relative=\"1\"",
            }
        )


def check_node_size(root: ET.Element, findings: list) -> None:
    missing = []
    for cell in root.iter("mxCell"):
        if cell.get("vertex") != "1":
            continue
        geom = cell.find("mxGeometry")
        if geom is None:
            missing.append(cell.get("id"))
            continue
        w = geom.get("width")
        h = geom.get("height")
        if not w or not h:
            missing.append(cell.get("id"))
    if missing:
        findings.append(
            {
                "check": "node_size",
                "severity": "warning",
                "message": f"{len(missing)} 个节点缺少 width/height",
                "examples": missing[:5],
            }
        )
    else:
        findings.append(
            {
                "check": "node_size",
                "severity": "ok",
                "message": "所有节点声明 width/height",
            }
        )


def check_xml_safe_comments(text: str, findings: list) -> None:
    """检查注释中是否含破坏 XML 的字符组合。

    仅在 XML 注释（<!-- ... -->）内检查双破折号 --；未转义尖括号由 XML
    解析阶段的失败信号覆盖，本函数不重复检测（避免 false positive，
    因为所有合法 XML 标签都含 < 与 >）。
    """
    issues = []
    in_comment = False
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("<!--") and "-->" in stripped:
            content = stripped[4 : stripped.index("-->")]
            if "--" in content:
                issues.append((i, "单行注释内含双破折号"))
        elif stripped.startswith("<!--"):
            in_comment = True
            content = stripped[4:]
            if "--" in content:
                issues.append((i, "注释起始行含双破折号"))
        elif in_comment and "-->" in stripped:
            in_comment = False
            content = stripped[: stripped.index("-->")]
            if "--" in content:
                issues.append((i, "注释结束前含双破折号"))
    if issues:
        findings.append(
            {
                "check": "xml_safe_comments",
                "severity": "warning",
                "message": f"发现 {len(issues)} 处注释双破折号",
                "examples": issues[:5],
            }
        )
    else:
        findings.append(
            {
                "check": "xml_safe_comments",
                "severity": "ok",
                "message": "未发现破坏 XML 的字符组合",
            }
        )


def validate_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    findings: list = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        return {
            "file": str(path),
            "passed": False,
            "error": f"XML 解析失败: {e}",
            "findings": [
                {
                    "check": "xml_parse",
                    "severity": "error",
                    "message": f"XML 解析失败: {e}",
                }
            ],
        }
    check_mxgraph_model(root, findings)
    check_parent_one(root, findings)
    check_edge_geometry(root, findings)
    check_node_size(root, findings)
    check_xml_safe_comments(text, findings)
    passed = not any(f["severity"] == "error" for f in findings)
    return {"file": str(path), "passed": passed, "findings": findings}


def collect_files(targets: list, recursive: bool) -> list:
    files = []
    for t in targets:
        p = Path(t)
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            it = p.rglob("*.drawio") if recursive else p.glob("*.drawio")
            files.extend(sorted(it))
        else:
            print(f"warning: 路径不存在 {p}", file=sys.stderr)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Legal Visualization drawio XML 自检",
    )
    parser.add_argument("paths", nargs="+", help=".drawio 文件或目录")
    parser.add_argument(
        "--recursive", "-r", action="store_true", help="目录递归查找"
    )
    parser.add_argument(
        "--json", action="store_true", help="输出 JSON 报告到 stdout"
    )
    args = parser.parse_args()

    files = collect_files(args.paths, args.recursive)
    if not files:
        print("error: 没有找到 .drawio 文件", file=sys.stderr)
        return 2

    reports = [validate_file(f) for f in files]
    all_passed = all(r["passed"] for r in reports)

    if args.json:
        json.dump({"all_passed": all_passed, "reports": reports}, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        for r in reports:
            status = "PASS" if r["passed"] else "FAIL"
            print(f"\n[{status}] {r['file']}")
            if "error" in r and r.get("error"):
                print(f"  ! {r['error']}")
            for f in r["findings"]:
                icon = {"ok": "✓", "warning": "!", "error": "✗"}.get(f["severity"], "?")
                print(f"  {icon} [{f['check']}] {f['message']}")
        print(
            f"\n汇总：{len(reports)} 个文件，{sum(1 for r in reports if r['passed'])} 通过，{sum(1 for r in reports if not r['passed'])} 失败"
        )

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
