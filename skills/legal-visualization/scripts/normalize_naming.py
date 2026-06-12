#!/usr/bin/env python3
"""normalize_naming.py — Legal Visualization 节点命名偏差检查脚本。

读 VizSpec YAML（可选）与 .drawio XML，对照 references/naming-conventions.md
检查偏差并输出清单。本脚本不修改原文件。

检查项：
1. 程序身份偏差：标签使用"我方/对方/客户"等口语化表达
2. 诉讼请求编号不一致：同一编号在不同字段指代不同对象
3. 证据编号格式不符：未使用"证据 X-Y"格式
4. 状态标签前缀缺失：disputed/asserted/inferred/missing 节点未加前缀

用法：
    python scripts/normalize_naming.py case.drawio
    python scripts/normalize_naming.py case.drawio case.yaml
    python scripts/normalize_naming.py case.drawio --json
"""
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

ORAL_ROLE_TERMS = ("我方", "对方", "客户方", "客户", "当事人一方", "当事人另一方")
CLAIM_ID_PATTERN = re.compile(r"诉讼请求\s*(\d+)")
EVIDENCE_ID_PATTERN = re.compile(r"证据\s*(\d+)\s*[-－]\s*(\d+)")
EVIDENCE_GENERIC_TERMS = (
    "证据目录",
    "证据清单",
    "证据初步梳理",
    "证据梳理",
    "证据矩阵",
    "关键证据",
    "争点-证据矩阵",
    "举证质证",
)
DISPUTE_PREFIXES = ("争议：", "主张：", "推定：", "待补充：")
ROLES = {
    "plaintiff", "defendant", "third_party",
    "appellant", "appellee",
    "retrial_applicant", "retrial_respondent",
    "applicant", "respondent",
    "execution_applicant", "execution_target", "outsider",
    "prosecutor", "criminal_defendant", "private_prosecutor",
    "legal_representative", "agent",
}


def collect_drawio_labels(path: Path) -> list:
    text = path.read_text(encoding="utf-8")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        return [{"error": f"XML 解析失败: {e}"}]
    labels = []
    for cell in root.iter("mxCell"):
        v = cell.get("value") or ""
        if v:
            labels.append({"id": cell.get("id"), "value": v, "vertex": cell.get("vertex") == "1"})
    return labels


def collect_vizspec_claims(path: Path) -> list:
    if yaml is None or not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        return [{"error": f"YAML 解析失败: {e}"}]
    if not isinstance(data, dict):
        return []
    annotations = data.get("annotations", []) or []
    claims = []
    for a in annotations:
        text = a.get("text", "") if isinstance(a, dict) else ""
        m = CLAIM_ID_PATTERN.search(text)
        if m:
            claims.append(m.group(1))
    return claims


def check_oral_roles(labels: list, findings: list) -> None:
    bad = []
    for entry in labels:
        if "error" in entry:
            continue
        v = entry["value"]
        if not entry["vertex"]:
            continue
        for term in ORAL_ROLE_TERMS:
            if term in v:
                bad.append({"id": entry["id"], "value": v, "term": term})
    if bad:
        findings.append(
            {
                "check": "oral_role_terms",
                "severity": "warning",
                "message": f"{len(bad)} 个节点使用口语化身份词",
                "examples": bad[:5],
            }
        )
    else:
        findings.append(
            {
                "check": "oral_role_terms",
                "severity": "ok",
                "message": "未发现口语化身份词",
            }
        )


def check_evidence_format(labels: list, findings: list) -> None:
    bad = []
    for entry in labels:
        if "error" in entry:
            continue
        v = entry["value"]
        if "证据" not in v:
            continue
        if any(term in v for term in EVIDENCE_GENERIC_TERMS):
            continue
        if EVIDENCE_ID_PATTERN.search(v):
            continue
        if v in DISPUTE_PREFIXES or any(v.startswith(p) for p in DISPUTE_PREFIXES):
            continue
        bad.append({"id": entry["id"], "value": v})
    if bad:
        findings.append(
            {
                "check": "evidence_format",
                "severity": "warning",
                "message": f"{len(bad)} 个证据节点未使用 '证据 X-Y' 格式",
                "examples": bad[:5],
            }
        )
    else:
        findings.append(
            {
                "check": "evidence_format",
                "severity": "ok",
                "message": "证据节点均符合 '证据 X-Y' 格式",
            }
        )


def check_dispute_prefix(labels: list, findings: list) -> None:
    suspicious = []
    keywords = ("争议", "待证", "推定", "待补充", "待核", "一方主张")
    for entry in labels:
        if "error" in entry:
            continue
        v = entry["value"]
        if not entry["vertex"]:
            continue
        if not any(kw in v for kw in keywords):
            continue
        if any(v.startswith(p) for p in DISPUTE_PREFIXES):
            continue
        suspicious.append({"id": entry["id"], "value": v})
    if suspicious:
        findings.append(
            {
                "check": "dispute_prefix",
                "severity": "info",
                "message": f"{len(suspicious)} 个争议/待证节点未加状态前缀",
                "examples": suspicious[:5],
                "expected_prefixes": list(DISPUTE_PREFIXES),
            }
        )
    else:
        findings.append(
            {
                "check": "dispute_prefix",
                "severity": "ok",
                "message": "争议/待证节点已加状态前缀",
            }
        )


def check_claim_consistency(labels: list, claim_ids: list, findings: list) -> None:
    label_ids = set()
    for entry in labels:
        if "error" in entry:
            continue
        v = entry["value"]
        m = CLAIM_ID_PATTERN.search(v)
        if m:
            label_ids.add(m.group(1))
    spec_ids = set(claim_ids)
    missing_in_spec = label_ids - spec_ids
    missing_in_drawio = spec_ids - label_ids
    if missing_in_spec or missing_in_drawio:
        findings.append(
            {
                "check": "claim_consistency",
                "severity": "warning",
                "message": "诉讼请求编号在 VizSpec 与 drawio 间不一致",
                "missing_in_vizspec": sorted(missing_in_spec),
                "missing_in_drawio": sorted(missing_in_drawio),
            }
        )
    else:
        findings.append(
            {
                "check": "claim_consistency",
                "severity": "ok",
                "message": "诉讼请求编号在 VizSpec 与 drawio 间一致",
            }
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Legal Visualization 节点命名偏差检查",
    )
    parser.add_argument("drawio", help=".drawio 源文件")
    parser.add_argument("vizspec", nargs="?", default=None, help="VizSpec YAML（可选）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 到 stdout")
    args = parser.parse_args()

    drawio_path = Path(args.drawio)
    if not drawio_path.exists():
        print(f"error: {drawio_path} 不存在", file=sys.stderr)
        return 2

    labels = collect_drawio_labels(drawio_path)
    vizspec_path = Path(args.vizspec) if args.vizspec else None
    claim_ids = collect_vizspec_claims(vizspec_path) if vizspec_path else []

    findings: list = []
    check_oral_roles(labels, findings)
    check_evidence_format(labels, findings)
    check_dispute_prefix(labels, findings)
    if vizspec_path and yaml is not None:
        check_claim_consistency(labels, claim_ids, findings)
    elif vizspec_path and yaml is None:
        findings.append(
            {
                "check": "yaml_dependency",
                "severity": "warning",
                "message": "未安装 PyYAML，跳过 VizSpec 一致性检查；pip install pyyaml",
            }
        )

    bad = [f for f in findings if f["severity"] in ("error", "warning")]
    report = {
        "file": str(drawio_path),
        "vizspec": str(vizspec_path) if vizspec_path else None,
        "passed": not bad,
        "findings": findings,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if report["passed"] else "FAIL"
        print(f"\n[{status}] {report['file']}")
        if report["vizspec"]:
            print(f"  VizSpec: {report['vizspec']}")
        for f in findings:
            icon = {"ok": "✓", "info": "i", "warning": "!", "error": "✗"}.get(
                f["severity"], "?"
            )
            print(f"  {icon} [{f['check']}] {f['message']}")
            if "examples" in f and f["examples"]:
                for ex in f["examples"][:3]:
                    print(f"      - {ex}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
