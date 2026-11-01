#!/usr/bin/env python3
"""验证 legal-harness-init 交付报告中的五个可观察硬约束。"""

from __future__ import annotations

import argparse
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
    "INIT-ENVIRONMENT-RECORD-ON-WRITE",
]

TRUSTED_COLLECTORS: set[str] = set()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def privacy_violations(report: dict) -> list[str]:
    text = str(report.get("config_text", ""))
    patterns = {
        "id_card": r"(?<!\d)[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?![\dXx])",
        "case_number": r"[（(]20\d{2}[）)].{0,40}?号",
        "phone": r"(?<!\d)1[3-9]\d{9}(?!\d)",
        "email": r"[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}",
        "credential": r"(?i)(?:api[_-]?key|access[_-]?token|secret|password|密码)\s*[:=]\s*[^<{[\s]",
    }
    violations = [name for name, pattern in patterns.items() if re.search(pattern, text)]
    if re.search(
        r"(?:委托人|客户|对方当事人|案号|项目金额|案件标的)\s*[:：]\s*(?!项目代号|见|未写入|待补充|\{|<|\[).+",
        text,
    ):
        violations.append("direct_case_field")
    return sorted(set(violations))


def marker_violations(text: str) -> tuple[list[str], list[str]]:
    problems, starts, open_id = [], [], ""
    for line in text.splitlines():
        match = re.fullmatch(r"<!-- legal-harness-init:([a-z0-9-]+):(start|end) -->", line)
        if not match:
            if "legal-harness-init:" in line:
                problems.append("malformed_markers")
            continue
        block_id, kind = match.groups()
        if kind == "start":
            if open_id:
                problems.append("nested_or_crossed_markers")
            if block_id in starts:
                problems.append("duplicate_markers")
            starts.append(block_id)
            open_id = block_id
        elif open_id != block_id:
            problems.append("nested_or_crossed_markers")
            open_id = ""
        else:
            open_id = ""
    if open_id or not starts:
        problems.append("unbalanced_markers")
    return sorted(set(problems)), sorted(set(starts))


def configuration_artifacts(report: dict, report_path: Path, explicit: list[str]):
    targets = report.get("target_paths")
    if (not isinstance(targets, list) or not targets
            or not all(isinstance(x, str) and x for x in targets)
            or len(targets) != len(set(targets))):
        return ["invalid_target_paths"], [], []
    artifacts = report.get("config_artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != len(targets):
        return ["missing_or_mismatched_config_artifacts"], [], []
    if explicit and len(explicit) != len(targets):
        return ["explicit_config_count_mismatch"], [], []
    base, texts, hashes, mapped, problems = report_path.parent.resolve(), [], [], [], []
    for i, item in enumerate(artifacts):
        if (not isinstance(item, dict) or not isinstance(item.get("path"), str)
                or item.get("target") not in targets):
            problems.append("invalid_config_artifact")
            continue
        mapped.append(item["target"])
        raw = Path(explicit[i]) if explicit else base / item["path"]
        artifact = raw.resolve()
        try:
            if not explicit:
                artifact.relative_to(base)
            if raw.is_symlink() or not artifact.is_file():
                raise ValueError("not a regular artifact")
            text = artifact.read_text(encoding="utf-8")
            texts.append(text)
            hashes.append(sha256(artifact))
        except (OSError, UnicodeError, ValueError):
            problems.append("missing_or_unsafe_config_artifact")
    if sorted(mapped) != sorted(targets):
        problems.append("artifact_target_mapping_mismatch")
    if not problems and report.get("config_text") != "\n".join(texts):
        problems.append("config_text_does_not_match_artifacts")
    return problems, texts, hashes


def status_violations(report: dict, hashes: list[str]) -> list[str]:
    status = report.get("status")
    evidence = report.get("session_evidence") or {}
    problems: list[str] = []
    if not isinstance(status, str) or status not in {
        "CONFIG_WRITTEN",
        "INSTRUCTIONS_DECLARED",
        "BEHAVIOR_DECLARED",
        "BEHAVIOR_VERIFIED",
    }:
        return ["unknown_status"]
    loaded = (
        evidence.get("new_session") is True
        and evidence.get("loaded") is True
        and evidence.get("source_path") in report.get("target_paths", [])
        and len(hashes) == 1
        and evidence.get("config_sha256") == hashes[0]
    )
    probes = evidence.get("probes") or {}
    behavior = loaded and all(
        probes.get(key) == "pass"
        for key in ("permission", "confidentiality", "information_gap", "traceability")
    )
    if status == "INSTRUCTIONS_DECLARED" and not loaded:
        problems.append("loaded_without_evidence")
    if status == "BEHAVIOR_DECLARED" and not behavior:
        problems.append("behavior_without_four_probes")
    if status == "BEHAVIOR_VERIFIED":
        collector = str(evidence.get("collector") or "")
        if collector not in TRUSTED_COLLECTORS:
            problems.append("behavior_verified_without_trusted_collector")
        if not behavior:
            problems.append("behavior_without_four_probes")
    return problems


def team_violations(report: dict) -> list[str]:
    if report.get("guide_mode") != "team":
        return []
    expected = ["legal_safety", "organization", "project", "individual"]
    return [] if report.get("precedence") == expected else ["wrong_precedence"]


def init_environment_violations(report: dict, texts: list[str], hashes: list[str]):
    init = report.get("init_environment")
    if not isinstance(init, dict) or init.get("recorded") is not True:
        return ["init_environment_not_recorded"]
    # Evidence is bound to the same final configuration artifacts, never a separate file.
    if not hashes or init.get("config_sha256") != hashes:
        return ["init_environment_config_hash_mismatch"]
    for text in texts:
        block = re.search(
            r"(?ms)^<!-- legal-harness-init:init-environment:start -->\n(.*?)"
            r"^<!-- legal-harness-init:init-environment:end -->$", text,
        )
        if not block:
            return ["init_environment_block_missing"]
        rows = []
        for line in block[1].splitlines():
            if not line.startswith("|"):
                continue
            cells = re.split(r"(?<!\\)\|", line)[1:-1]
            cells = [x.strip() for x in cells]
            if cells and re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", cells[0]):
                rows.append(cells)
        if not rows or any(
            len(cells) != 7 or not all(cells) or cells[4] != "legal-harness-init"
            or cells[6].split(" · ")[0] not in {"init", "update", "append"}
            for cells in rows
        ):
            return ["init_environment_row_missing_or_invalid"]
        body = re.sub(
            r"(?ms)^<!-- legal-harness-init:init-environment:start -->\n.*?"
            r"^<!-- legal-harness-init:init-environment:end -->$\n?",
            "",
            text,
        )
        body_lines = body.splitlines()
        nonempty = [i for i, line in enumerate(body_lines) if line.strip()]
        if not nonempty:
            return ["init_environment_body_empty"]
        expected_digest = hashlib.sha256(
            ("\n".join(body_lines[: nonempty[-1] + 1]) + "\n").encode("utf-8")
        ).hexdigest()
        if not any(
            f"config-sha256={expected_digest}" in cells[6] for cells in rows
        ):
            return ["init_environment_stale_for_current_configuration"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--config", action="append", default=[])
    args = parser.parse_args()
    path = args.input
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"无法读取交付报告：{exc}", file=sys.stderr)
        return 2

    if not isinstance(report, dict):
        print(json.dumps({"error": "report must be an object"}))
        return 2
    if (not isinstance(report.get("session_evidence", {}), dict)
            or not isinstance(report.get("session_evidence", {}).get("probes", {}), dict)):
        print(json.dumps({"error": "session_evidence/probes must be objects"}))
        return 2
    managed, texts, hashes = configuration_artifacts(report, path, args.config)
    block_ids = []
    for text in texts:
        issues, ids = marker_violations(text)
        managed.extend(issues)
        block_ids.extend(ids)
    actual = dict(report, config_text="\n".join(texts))
    privacy = privacy_violations(actual)
    status = status_violations(report, hashes)
    team = team_violations(report)
    init = init_environment_violations(report, texts, hashes)
    problems = {
        "PRIVACY-MINIMUM-CONTEXT": privacy,
        "MANAGED-BLOCK-SAFE-UPSERT": managed,
        "COMPLETION-STATUS-NO-OVERCLAIM": status,
        "TEAM-LAYER-PRECEDENCE": team,
        "INIT-ENVIRONMENT-RECORD-ON-WRITE": init,
    }
    passed = [constraint for constraint in CONSTRAINTS if not problems[constraint]]
    artifact_sha = {"delivery-report": sha256(path)}
    if len(hashes) == 1:
        artifact_sha["configuration"] = hashes[0]
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
                "init-environment-recorded": bool(
                    isinstance(report.get("init_environment"), dict)
                    and report["init_environment"].get("recorded") is True
                ),
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
