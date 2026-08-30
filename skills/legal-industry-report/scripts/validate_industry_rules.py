#!/usr/bin/env python3
"""校验行业规则注册表的结构、唯一性与信源 URL。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

try:
    import yaml
except ImportError as exc:
    print("[error] 缺少 Python 依赖: PyYAML", file=sys.stderr)
    print("请运行: python3 -m pip install -r scripts/requirements.txt", file=sys.stderr)
    raise SystemExit(1) from exc


REQUIRED_PACK_KEYS = {"id", "aliases", "report", "brief", "legal_risk_lenses", "sources"}
REQUIRED_SOURCE_KEYS = {"id", "name", "url", "authority", "use_for", "cadence", "access_notes"}
REQUIRED_REPORT_KEYS = {"required_dimensions", "research_questions", "indicators"}
REQUIRED_BRIEF_KEYS = {"watch_events", "relevance_questions"}
ALLOWED_AUTHORITY = {"official", "statutory-disclosure", "industry-association", "licensed-database"}
ALLOWED_CADENCE = {"daily", "weekly", "monthly", "quarterly", "annual", "event"}


def load_registry(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"无法读取 YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("注册表根节点必须是对象")
    return data


def _nonempty_list(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) and item.strip() for item in value)


def _validate_source(source: object, location: str, findings: list[dict]) -> None:
    if not isinstance(source, dict):
        findings.append({"id": "RULE-SOURCE-TYPE", "location": location, "message": "信源必须是对象"})
        return
    missing = sorted(REQUIRED_SOURCE_KEYS - set(source))
    if missing:
        findings.append({"id": "RULE-SOURCE-KEYS", "location": location, "message": f"缺少字段: {', '.join(missing)}"})
        return
    parsed = urlparse(str(source.get("url", "")))
    if parsed.scheme != "https" or not parsed.hostname or parsed.hostname.endswith(".invalid"):
        findings.append({"id": "RULE-SOURCE-URL", "location": location, "message": "信源必须使用非占位的有效 https URL"})
    if source.get("authority") not in ALLOWED_AUTHORITY:
        findings.append({"id": "RULE-SOURCE-AUTHORITY", "location": location, "message": f"authority 不合法: {source.get('authority')}"})
    if source.get("cadence") not in ALLOWED_CADENCE:
        findings.append({"id": "RULE-SOURCE-CADENCE", "location": location, "message": f"cadence 不合法: {source.get('cadence')}"})
    if not _nonempty_list(source.get("use_for")):
        findings.append({"id": "RULE-SOURCE-USE", "location": location, "message": "use_for 必须是非空字符串数组"})


def validate_registry(data: dict) -> dict:
    findings: list[dict] = []
    if data.get("schema_version") != 1:
        findings.append({"id": "RULE-SCHEMA", "location": "root", "message": "schema_version 必须为 1"})
    common = data.get("common")
    packs = data.get("packs")
    if not isinstance(common, dict):
        findings.append({"id": "RULE-COMMON", "location": "common", "message": "common 必须是对象"})
        common = {}
    if not isinstance(packs, list) or not packs:
        findings.append({"id": "RULE-PACKS", "location": "packs", "message": "packs 必须是非空数组"})
        packs = []

    for key in ("required_dimensions", "research_questions"):
        if not _nonempty_list(common.get(key)):
            findings.append({"id": "RULE-COMMON-FIELD", "location": f"common.{key}", "message": "必须是非空字符串数组"})
    common_sources = common.get("sources")
    if not isinstance(common_sources, list) or not common_sources:
        findings.append({"id": "RULE-COMMON-SOURCES", "location": "common.sources", "message": "必须包含通用信源"})
        common_sources = []

    source_ids: set[str] = set()
    for index, source in enumerate(common_sources):
        _validate_source(source, f"common.sources[{index}]", findings)
        if isinstance(source, dict) and source.get("id"):
            source_ids.add(str(source["id"]))

    pack_ids: set[str] = set()
    aliases: dict[str, str] = {}
    for index, pack in enumerate(packs):
        location = f"packs[{index}]"
        if not isinstance(pack, dict):
            findings.append({"id": "RULE-PACK-TYPE", "location": location, "message": "行业包必须是对象"})
            continue
        missing = sorted(REQUIRED_PACK_KEYS - set(pack))
        if missing:
            findings.append({"id": "RULE-PACK-KEYS", "location": location, "message": f"缺少字段: {', '.join(missing)}"})
            continue
        pack_id = str(pack.get("id", "")).strip()
        if not pack_id or pack_id in pack_ids:
            findings.append({"id": "RULE-PACK-ID", "location": location, "message": f"行业包 id 为空或重复: {pack_id}"})
        pack_ids.add(pack_id)
        if not _nonempty_list(pack.get("aliases")):
            findings.append({"id": "RULE-ALIASES", "location": location, "message": "aliases 必须是非空字符串数组"})
        else:
            for alias in pack["aliases"]:
                normalized = alias.strip().lower()
                if normalized in aliases and aliases[normalized] != pack_id:
                    findings.append({"id": "RULE-ALIAS-DUP", "location": location, "message": f"别名 {alias} 同时属于 {aliases[normalized]} 与 {pack_id}"})
                aliases[normalized] = pack_id
        for branch_name, required in (("report", REQUIRED_REPORT_KEYS), ("brief", REQUIRED_BRIEF_KEYS)):
            branch = pack.get(branch_name)
            if not isinstance(branch, dict):
                findings.append({"id": "RULE-MODE", "location": f"{location}.{branch_name}", "message": "模式配置必须是对象"})
                continue
            for key in required:
                if not _nonempty_list(branch.get(key)):
                    findings.append({"id": "RULE-MODE-FIELD", "location": f"{location}.{branch_name}.{key}", "message": "必须是非空字符串数组"})
        if not _nonempty_list(pack.get("legal_risk_lenses")):
            findings.append({"id": "RULE-RISK", "location": f"{location}.legal_risk_lenses", "message": "必须是非空字符串数组"})
        pack_sources = pack.get("sources")
        if not isinstance(pack_sources, list) or not pack_sources:
            findings.append({"id": "RULE-PACK-SOURCES", "location": f"{location}.sources", "message": "必须至少包含一个行业信源"})
            continue
        local_ids: set[str] = set()
        for source_index, source in enumerate(pack_sources):
            source_location = f"{location}.sources[{source_index}]"
            _validate_source(source, source_location, findings)
            if isinstance(source, dict) and source.get("id"):
                source_id = str(source["id"])
                if source_id in local_ids:
                    findings.append({"id": "RULE-SOURCE-DUP", "location": source_location, "message": f"行业包内信源 id 重复: {source_id}"})
                local_ids.add(source_id)

    return {
        "schema_version": 1,
        "status": "PASS" if not findings else "FAIL",
        "measurements": {
            "pack_count": len(packs),
            "alias_count": len(aliases),
            "common_source_count": len(common_sources),
            "finding_count": len(findings),
        },
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="校验行业规则注册表")
    parser.add_argument("--registry", default=str(Path(__file__).resolve().parent.parent / "references" / "industry-rules.yaml"))
    args = parser.parse_args()
    try:
        result = validate_registry(load_registry(Path(args.registry).resolve()))
    except ValueError as exc:
        result = {"schema_version": 1, "status": "FAIL", "findings": [{"id": "RULE-READ", "location": "root", "message": str(exc)}]}
    for finding in result.get("findings", []):
        print(f"[FAIL] {finding['id']} {finding.get('location', '')}: {finding['message']}", file=sys.stderr)
    if result.get("status") == "PASS":
        print("行业规则注册表校验通过")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
