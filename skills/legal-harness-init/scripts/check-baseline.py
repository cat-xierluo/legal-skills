#!/usr/bin/env python3
"""验证 legal-harness-init 交付报告中的四个可观察硬约束。"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path


CONSTRAINTS = [
    "PRIVACY-MINIMUM-CONTEXT",
    "MANAGED-BLOCK-SAFE-UPSERT",
    "COMPLETION-STATUS-NO-OVERCLAIM",
    "TEAM-LAYER-PRECEDENCE",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def privacy_violations(report: dict) -> list[str]:
    text = str(report.get("config_text", ""))
    patterns = {
        "id_card": r"(?<!\d)[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?![\dXx])",
        "case_number": r"[（(]20\d{2}[）)].{0,40}?号",
        "phone": r"(?<!\d)1[3-9]\d{9}(?!\d)",
        "credential": r"(?i)(?:api[_-]?key|access[_-]?token|secret|password|密码)\s*[:=]\s*[^<{[\s]",
    }
    violations = [name for name, pattern in patterns.items() if re.search(pattern, text)]
    if re.search(
        r"(?:委托人|客户|对方当事人|案号|项目金额|案件标的)\s*[:：]\s*(?!项目代号|见|未写入|待补充|\{|<|\[).+",
        text,
    ):
        violations.append("direct_case_field")
    return sorted(set(violations))


def managed_violations(report: dict) -> tuple[list[str], list[str]]:
    text = str(report.get("config_text", ""))
    starts = re.findall(r"^<!-- legal-harness-init:([a-z0-9-]+):start -->$", text, re.M)
    ends = re.findall(r"^<!-- legal-harness-init:([a-z0-9-]+):end -->$", text, re.M)
    problems: list[str] = []
    if not starts or sorted(starts) != sorted(ends):
        problems.append("unbalanced_markers")
    if len(starts) != len(set(starts)):
        problems.append("duplicate_markers")
    targets = report.get("target_paths", [])
    if not isinstance(targets, list) or len(targets) != len(set(targets)):
        problems.append("duplicate_targets")
    return sorted(problems), sorted(set(starts))


def status_violations(report: dict) -> list[str]:
    status = report.get("status")
    evidence = report.get("session_evidence") or {}
    problems: list[str] = []
    if status not in {"CONFIG_WRITTEN", "INSTRUCTIONS_LOADED", "BEHAVIOR_VERIFIED"}:
        return ["unknown_status"]
    loaded = (
        evidence.get("new_session") is True
        and evidence.get("loaded") is True
        and evidence.get("source_path") in report.get("target_paths", [])
    )
    probes = evidence.get("probes") or {}
    behavior = loaded and all(
        probes.get(key) == "pass"
        for key in ("permission", "confidentiality", "information_gap", "traceability")
    )
    if status == "INSTRUCTIONS_LOADED" and not loaded:
        problems.append("loaded_without_evidence")
    if status == "BEHAVIOR_VERIFIED" and not behavior:
        problems.append("behavior_without_four_probes")
    return problems


def team_violations(report: dict) -> list[str]:
    if report.get("guide_mode") != "team":
        return []
    expected = ["legal_safety", "organization", "project", "individual"]
    return [] if report.get("precedence") == expected else ["wrong_precedence"]


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] != "--input":
        print("用法：check-baseline.py --input <delivery-report.json>", file=sys.stderr)
        return 2
    path = Path(sys.argv[2])
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"无法读取交付报告：{exc}", file=sys.stderr)
        return 2

    privacy = privacy_violations(report)
    managed, block_ids = managed_violations(report)
    status = status_violations(report)
    team = team_violations(report)
    problems = {
        "PRIVACY-MINIMUM-CONTEXT": privacy,
        "MANAGED-BLOCK-SAFE-UPSERT": managed,
        "COMPLETION-STATUS-NO-OVERCLAIM": status,
        "TEAM-LAYER-PRECEDENCE": team,
    }
    passed = [constraint for constraint in CONSTRAINTS if not problems[constraint]]
    artifact_sha = {"delivery-report": sha256(path)}
    if len(passed) == len(CONSTRAINTS):
        payload = {
            "passed_constraint_ids": passed,
            "artifact_sha256": artifact_sha,
            "measurements": {
                constraint: {
                    f"{constraint.lower()}-violations": len(problems[constraint])
                }
                for constraint in CONSTRAINTS
            },
            "observables": {
                "privacy-violation-types": privacy,
                "managed-block-ids": block_ids,
                "completion-status": str(report.get("status", "")),
                "team-precedence": report.get("precedence", []),
            },
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0

    failed = [constraint for constraint in CONSTRAINTS if problems[constraint]]
    payload = {
        "failed_constraint_ids": failed,
        "artifact_sha256": artifact_sha,
        "measurements": {
            constraint: {
                f"{constraint.lower()}-violations": len(problems[constraint])
            }
            for constraint in failed
        },
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
