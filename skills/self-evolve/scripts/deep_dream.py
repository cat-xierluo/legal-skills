#!/usr/bin/env python3
"""Optional, explicit LLM analysis for deterministic Dream Sweep clusters.

The daily/index path never imports or invokes this module. This command consumes
only a locally persisted, sanitized cluster packet and fails closed to
``analysis_unavailable`` when the CLI output does not match the schema.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from privacy_gate import (
    sanitize_structured_text,
    sanitize_text,
    validate_text,
    validate_untrusted_source,
    write_review_artifact,
)
from proposal_store import ProposalStore
from self_evolve_paths import REVIEW_INBOX_ROOT, RUNTIME_ROOT, assert_runtime_ready


CLUSTERS_PATH = RUNTIME_ROOT / "dreaming" / "topic-clusters.json"
PACKET_ROOT = RUNTIME_ROOT / "dreaming" / "deep-packets"
STATUS_ROOT = RUNTIME_ROOT / "dreaming" / "deep-status"
DEEP_OUTPUT_ROOT = REVIEW_INBOX_ROOT / "deep-analysis"
INVENTORY_PATH = RUNTIME_ROOT / "skill-inventory.json"
PORTRAITS_PATH = RUNTIME_ROOT / "skill-portraits.json"
SAFE_ID_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
ENHANCED_FIELDS = frozenset(
    ("reusable_bricks", "skeleton_fitness", "extension_points", "triggers")
)
ENHANCED_FIELD_METADATA = "field_metadata"


def finite_budget(value: str, *, maximum: Decimal) -> float:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("budget must be a finite positive number") from exc
    if not parsed.is_finite() or parsed <= 0 or parsed > maximum:
        raise argparse.ArgumentTypeError(
            f"budget must be greater than 0 and no more than {maximum}"
        )
    return float(parsed)


def parse_total_budget(value: str) -> float:
    return finite_budget(value, maximum=Decimal("100.00"))


def parse_per_call_budget(value: str) -> float:
    return finite_budget(value, maximum=Decimal("5.00"))


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, 0o600)
        Path(name).replace(path)
    finally:
        try:
            Path(name).unlink()
        except FileNotFoundError:
            pass


def safe_id(value: str) -> str:
    result = "".join(character if character in SAFE_ID_CHARS else "-" for character in value)
    return result.strip("-")[:80] or "cluster"


def load_clusters(path: Path = CLUSTERS_PATH) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, dict):
        payload = payload.get("clusters", [])
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def _valid_distilled_at(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and value > 0
    )


def current_enhanced_fields(enhanced: Any, content_hash: str) -> dict[str, Any]:
    """Return only enhanced fields explicitly bound to ``content_hash``.

    New portrait stores bind each flat field through ``field_metadata``.  A
    legacy whole-object ``content_hash`` remains readable when explicit; older
    hashless values are retained on disk but intentionally fail closed here.
    """

    if not isinstance(enhanced, dict) or not content_hash:
        return {}
    raw_metadata = enhanced.get(ENHANCED_FIELD_METADATA)
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
    legacy_hash = enhanced.get("content_hash")
    legacy_timestamp = enhanced.get("distilled_at")
    current: dict[str, Any] = {}
    for field in ENHANCED_FIELDS:
        if field not in enhanced:
            continue
        field_metadata = metadata.get(field)
        if isinstance(field_metadata, dict):
            is_current = (
                field_metadata.get("content_hash") == content_hash
                and _valid_distilled_at(field_metadata.get("distilled_at"))
            )
        else:
            is_current = (
                legacy_hash == content_hash
                and _valid_distilled_at(legacy_timestamp)
            )
        if is_current:
            current[field] = enhanced[field]
    return current


def load_skill_catalog(
    inventory_path: Path = INVENTORY_PATH,
    portraits_path: Path = PORTRAITS_PATH,
) -> list[dict[str, Any]]:
    """Load version/content state without exposing source paths to the LLM."""
    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    skills = inventory.get("skills", []) if isinstance(inventory, dict) else []
    try:
        portrait_store = json.loads(portraits_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        portrait_store = {}
    portraits = portrait_store.get("portraits", {}) if isinstance(portrait_store, dict) else {}
    if not isinstance(portraits, dict):
        portraits = {}

    catalog: list[dict[str, Any]] = []
    for skill in skills if isinstance(skills, list) else []:
        if not isinstance(skill, dict) or not skill.get("skill_key") or not skill.get("id"):
            continue
        content_digest = str(skill.get("content_hash") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", content_digest):
            continue
        portrait = portraits.get(str(skill["skill_key"]), {})
        if not isinstance(portrait, dict):
            portrait = {}
        core_is_current = (
            portrait.get("stale") is False
            and portrait.get("content_hash") == skill.get("content_hash")
        )
        current_enhanced = current_enhanced_fields(
            portrait.get("enhanced"), content_digest
        )
        current_portrait = (
            {
                "core": portrait.get("core") if core_is_current else None,
                "enhanced": current_enhanced,
            }
            if core_is_current or current_enhanced
            else {}
        )
        catalog.append(
            {
                "skill_key": str(skill["skill_key"]),
                "id": str(skill["id"]),
                "name": str(skill.get("name") or skill["id"]),
                "version": str(skill.get("version") or "unversioned"),
                "content_hash": content_digest,
                "current_text": json.dumps(
                    {
                        "title": skill.get("title", ""),
                        "description": skill.get("description", ""),
                        "portrait": current_portrait,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            }
        )
    return sorted(catalog, key=lambda item: (item["id"], item["skill_key"]))


def resolve_target(catalog: list[dict[str, Any]], reference: str) -> tuple[dict[str, Any] | None, str]:
    matches = [
        item
        for item in catalog
        if reference in {item.get("skill_key"), item.get("id"), item.get("name")}
    ]
    if not matches:
        return None, "missing"
    if len(matches) != 1:
        return None, "ambiguous"
    return matches[0], "resolved"


def current_state_covers(change_points: list[str], target: dict[str, Any]) -> bool:
    """Conservatively recognize only exact normalized current-state coverage."""
    normalize = lambda value: re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", value).lower()
    haystack = normalize(str(target.get("current_text", "")))
    normalized_points = [normalize(item) for item in change_points]
    return bool(normalized_points) and all(len(item) >= 6 and item in haystack for item in normalized_points)


def _sanitize_packet_value(value: Any) -> Any:
    """Sanitize string leaves without rewriting serialized JSON syntax."""
    if isinstance(value, str):
        source_blockers = validate_untrusted_source(value)
        sanitized, _ = sanitize_text(value)
        residual = validate_text(sanitized)
        if source_blockers or residual:
            raise ValueError("cluster packet failed privacy validation")
        return sanitized
    if isinstance(value, list):
        return [_sanitize_packet_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_packet_value(item) for key, item in value.items()}
    return value


def build_packet(cluster: dict[str, Any]) -> dict[str, Any]:
    """Whitelist fields and sanitize values while preserving JSON structure."""
    sessions = []
    for item in cluster.get("sessions", []):
        if not isinstance(item, dict):
            continue
        sessions.append(
            {
                "source": item.get("source", ""),
                "source_variant": item.get("source_variant", ""),
                "session_id_hash": hashlib.sha256(
                    str(item.get("session_id", "")).encode("utf-8", errors="replace")
                ).hexdigest()[:16],
                "started_at": item.get("started_at", ""),
                "topic_title": item.get("topic_title", ""),
                "session_class": item.get("session_class", ""),
                "work_stage": item.get("work_stage", ""),
            }
        )
    packet = {
        "schema_version": "1.0",
        "cluster_id": cluster.get("cluster_id", ""),
        "title": cluster.get("title", ""),
        "topic_keywords": cluster.get("topic_keywords", []),
        "related_skills": cluster.get("related_skills", []),
        "work_stages": cluster.get("work_stages", []),
        "reasons": cluster.get("reasons", []),
        "cohesion_average": cluster.get("cohesion_average", 0),
        "cohesion_minimum": cluster.get("cohesion_minimum", 0),
        "purity": cluster.get("purity", 0),
        "uncertainty": cluster.get("uncertainty", 1),
        "quality_gate": cluster.get("quality_gate", "observe_only"),
        "evidence": [
            {
                "evidence_id": item.get("evidence_id", ""),
                "source_session_id_hash": item.get("source_session_id_hash", ""),
                "text": item.get("text", ""),
            }
            for item in cluster.get("evidence", [])
            if isinstance(item, dict) and item.get("evidence_id") and item.get("text")
        ],
        "sessions": sessions,
    }
    return _sanitize_packet_value(packet)


def analysis_schema(
    cluster_id: str,
    evidence_ids: list[str],
    target_skill_keys: list[str] | None = None,
) -> dict[str, Any]:
    evidence_array = {
        "type": "array",
        "items": {"type": "string", "enum": evidence_ids},
        "minItems": 1,
        "uniqueItems": True,
    }
    cited_point = {
        "type": "object",
        "additionalProperties": False,
        "required": ["point", "evidence_ids"],
        "properties": {"point": {"type": "string", "minLength": 1}, "evidence_ids": evidence_array},
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "cluster_id",
            "analysis_status",
            "summary",
            "observations",
            "counter_evidence",
            "upgrade_candidates",
            "uncertainties",
        ],
        "properties": {
            "cluster_id": {"const": cluster_id},
            "analysis_status": {"const": "available"},
            "summary": {"type": "string", "minLength": 1},
            "observations": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["claim", "evidence_ids"],
                    "properties": {
                        "claim": {"type": "string", "minLength": 1},
                        "evidence_ids": evidence_array,
                    },
                },
            },
            "counter_evidence": {"type": "array", "minItems": 1, "items": cited_point},
            "upgrade_candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "target_skill",
                        "change_points",
                        "rationale",
                        "evidence_ids",
                        "acceptance_tests",
                    ],
                    "properties": {
                        "target_skill": (
                            {"type": "string", "enum": target_skill_keys}
                            if target_skill_keys
                            else {"type": "string", "minLength": 1}
                        ),
                        "change_points": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string", "minLength": 1},
                        },
                        "rationale": {"type": "string", "minLength": 1},
                        "evidence_ids": evidence_array,
                        "acceptance_tests": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string", "minLength": 1},
                        },
                    },
                },
            },
            "uncertainties": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string", "minLength": 1},
            },
        },
    }


def parse_cli_result(
    stdout: str,
    cluster_id: str,
    allowed_evidence_ids: set[str],
    allowed_target_skill_keys: set[str] | None = None,
) -> dict[str, Any] | None:
    try:
        outer = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    payload: Any = outer
    if isinstance(outer, dict) and isinstance(outer.get("structured_output"), dict):
        payload = outer["structured_output"]
    if isinstance(outer, dict) and isinstance(outer.get("result"), str):
        try:
            payload = json.loads(outer["result"])
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict) or payload.get("cluster_id") != cluster_id:
        return None
    if payload.get("analysis_status") != "available":
        return None
    if not isinstance(payload.get("summary"), str):
        return None
    for key in ("observations", "counter_evidence", "upgrade_candidates", "uncertainties"):
        if not isinstance(payload.get(key), list):
            return None
    if not payload["observations"] or not payload["counter_evidence"] or not payload["uncertainties"]:
        return None
    for observation in payload["observations"]:
        if not isinstance(observation, dict) or not isinstance(observation.get("claim"), str):
            return None
        citations = observation.get("evidence_ids")
        if not isinstance(citations, list) or not citations or not set(citations) <= allowed_evidence_ids:
            return None
    for counterpoint in payload["counter_evidence"]:
        if not isinstance(counterpoint, dict) or not isinstance(counterpoint.get("point"), str):
            return None
        citations = counterpoint.get("evidence_ids")
        if not isinstance(citations, list) or not citations or not set(citations) <= allowed_evidence_ids:
            return None
    for candidate in payload["upgrade_candidates"]:
        if not isinstance(candidate, dict):
            return None
        if not isinstance(candidate.get("target_skill"), str):
            return None
        if allowed_target_skill_keys and candidate["target_skill"] not in allowed_target_skill_keys:
            return None
        if not isinstance(candidate.get("change_points"), list) or not all(
            isinstance(item, str) for item in candidate["change_points"]
        ):
            return None
        citations = candidate.get("evidence_ids")
        tests = candidate.get("acceptance_tests")
        if not isinstance(citations, list) or not citations or not set(citations) <= allowed_evidence_ids:
            return None
        if not isinstance(tests, list) or not tests or not all(isinstance(item, str) and item for item in tests):
            return None
    return payload


def run_claude(
    packet_path: Path,
    claude_bin: str,
    timeout: int,
    *,
    model: str,
    max_budget_usd: float,
) -> tuple[dict[str, Any] | None, str]:
    executable = shutil.which(claude_bin)
    if not executable:
        return None, "claude_cli_missing"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    evidence_ids = [str(item["evidence_id"]) for item in packet.get("evidence", [])]
    if not evidence_ids:
        return None, "packet_has_no_evidence"
    target_skill_keys = [
        str(item["skill_key"])
        for item in packet.get("allowed_target_skills", [])
        if isinstance(item, dict) and item.get("skill_key")
    ]
    schema = analysis_schema(str(packet["cluster_id"]), evidence_ids, target_skill_keys)
    prompt = (
        "只分析随附的脱敏 cluster packet。不要执行工具，不要读取文件，不要把候选描述为已批准。"
        "每条观察、反证和升级候选必须引用 packet 中存在的 evidence_id；每个候选必须给出可执行验收方案。"
        "升级候选的 target_skill 必须逐字使用 allowed_target_skills 中的 skill_key。"
        "必须列出至少一项反证和一项不确定性。只返回 JSON。\nPACKET:\n"
        + json.dumps(packet, ensure_ascii=False)
    )
    command = [
        executable,
        "--print",
        "--output-format",
        "json",
        "--permission-mode",
        "plan",
        "--safe-mode",
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--mcp-config",
        "{}",
        "--tools",
        "",
        "--no-session-persistence",
        "--json-schema",
        json.dumps(schema, ensure_ascii=False, separators=(",", ":")),
        "--model",
        model,
        "--max-budget-usd",
        f"{max(0.01, max_budget_usd):.2f}",
    ]
    try:
        completed = subprocess.run(
            command,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=max(10, timeout),
            check=False,
            env={**os.environ, "SELF_EVOLVE_DEEP_DREAM": "1"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, "claude_cli_failed"
    if completed.returncode != 0:
        return None, "claude_cli_nonzero"
    parsed = parse_cli_result(
        completed.stdout,
        str(packet["cluster_id"]),
        set(evidence_ids),
        set(target_skill_keys) if target_skill_keys else None,
    )
    return (parsed, "") if parsed else (None, "invalid_structured_output")


def render_analysis(payload: dict[str, Any]) -> str:
    lines = [
        f"# Deep Dream 分析：{payload['cluster_id']}",
        "",
        "> 这是机器候选分析，人工决策仍为 `pending`；任何升级都需单独人工接受。",
        "",
        "## 摘要",
        "",
        payload["summary"],
        "",
        "## 观察",
        "",
        *[
            f"- {item['claim']}（证据：{', '.join(item['evidence_ids'])}）"
            for item in payload["observations"]
        ],
        "",
        "## 反证",
        "",
        *[
            f"- {item['point']}（证据：{', '.join(item['evidence_ids'])}）"
            for item in payload["counter_evidence"]
        ],
        "",
        "## 升级候选",
        "",
    ]
    for candidate in payload["upgrade_candidates"]:
        lines.extend(
            [
                f"### {candidate['target_skill']}",
                "",
                *[f"- {point}" for point in candidate["change_points"]],
                f"- 理由：{candidate.get('rationale', '')}",
                f"- 证据：{', '.join(candidate['evidence_ids'])}",
                *[f"- 验收：{item}" for item in candidate["acceptance_tests"]],
                "- 人工决策：`pending`",
                "",
            ]
        )
    lines.extend(["## 不确定性", "", *[f"- {item}" for item in payload["uncertainties"]], ""])
    return "\n".join(lines)


def _read_deep_status(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def persist_deep_attempt(attempt: dict[str, Any], *, success: bool = False) -> dict[str, Any]:
    """Record the latest attempt while retaining the last usable analysis.

    The top-level compatibility view remains the last successful analysis when
    one exists. Transient preview/CLI/privacy failures live in ``last_attempt``
    and therefore cannot erase durable artifact or proposal references.
    """
    cluster_id = str(attempt.get("cluster_id") or "unknown")
    path = STATUS_ROOT / f"{safe_id(cluster_id)}.json"
    previous = _read_deep_status(path)
    previous_success = previous.get("last_success")
    if not isinstance(previous_success, dict) and previous.get("analysis_status") == "available":
        previous_success = {
            key: value
            for key, value in previous.items()
            if key not in {"schema_version", "last_attempt", "last_success"}
        }
    last_success = dict(attempt) if success else (
        dict(previous_success) if isinstance(previous_success, dict) else None
    )
    compatibility_view = last_success or attempt
    durable = {
        **compatibility_view,
        "schema_version": "2.0",
        "cluster_id": cluster_id,
        "last_attempt": dict(attempt),
    }
    if last_success:
        durable["last_success"] = last_success
    atomic_json(path, durable)
    result = dict(attempt)
    result["last_success_available"] = bool(last_success)
    return result


def unavailable(cluster_id: str, reason: str) -> dict[str, Any]:
    attempt = {
        "cluster_id": cluster_id,
        "analysis_status": "analysis_unavailable",
        "reason": reason,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return persist_deep_attempt(attempt)


def prepared(cluster_id: str, packet_path: Path) -> dict[str, Any]:
    attempt = {
        "cluster_id": cluster_id,
        "analysis_status": "prepared",
        "reason": "explicit_execution_required",
        "packet_ref": packet_path.name,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return persist_deep_attempt(attempt)


def process_cluster(cluster: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    cluster_id = str(cluster.get("cluster_id") or "")
    if not cluster_id:
        return unavailable("unknown", "missing_cluster_id")
    if cluster.get("quality_gate") != "deep_eligible":
        return unavailable(cluster_id, "quality_gate_not_deep_eligible")
    catalog = load_skill_catalog()
    if not catalog:
        return unavailable(cluster_id, "skill_inventory_unavailable")
    try:
        packet = build_packet(cluster)
    except ValueError:
        return unavailable(cluster_id, "packet_privacy_blocked")
    try:
        packet["allowed_target_skills"] = [
            {
                "skill_key": sanitize_structured_text(item["skill_key"]),
                "id": sanitize_structured_text(item["id"]),
                "name": sanitize_structured_text(item["name"]),
                "version": sanitize_structured_text(item["version"]),
            }
            for item in catalog
        ]
    except ValueError:
        return unavailable(cluster_id, "skill_inventory_privacy_blocked")
    packet_path = PACKET_ROOT / f"{safe_id(cluster_id)}.json"
    atomic_json(packet_path, packet)
    if not args.execute:
        return prepared(cluster_id, packet_path)
    analysis, reason = run_claude(
        packet_path,
        args.claude_bin,
        args.timeout,
        model=args.model,
        max_budget_usd=getattr(args, "call_budget_usd", args.max_budget_usd),
    )
    if analysis is None:
        return unavailable(cluster_id, reason)
    destination = DEEP_OUTPUT_ROOT / f"{safe_id(cluster_id)}_deep-analysis.md"
    artifact = write_review_artifact(
        destination,
        render_analysis(analysis),
        artifact_id=f"deep-{safe_id(cluster_id)[:70]}",
        source_session_ids=[str(item.get("session_id_hash", "")) for item in packet["sessions"]],
        immutable=True,
    )
    if artifact.get("status") != "published":
        return unavailable(cluster_id, "analysis_privacy_blocked")

    store = ProposalStore()
    proposal_ids: list[str] = []
    artifact_ref = f"review/inbox/{artifact['destination']}"
    proposal_gates: list[dict[str, str]] = []
    for candidate in analysis["upgrade_candidates"]:
        safe_target = sanitize_structured_text(candidate["target_skill"]).strip()
        safe_points = [sanitize_structured_text(item) for item in candidate["change_points"]]
        safe_tests = [sanitize_structured_text(item) for item in candidate["acceptance_tests"]]
        safe_summary = sanitize_structured_text(candidate.get("rationale", ""))
        target, resolution = resolve_target(catalog, safe_target)
        target_version = str(target.get("version")) if target else resolution
        target_content_hash = str(target.get("content_hash", "")) if target else ""
        disposition = (
            "covered"
            if target and current_state_covers(safe_points, target)
            else ("candidate" if target else "filtered")
        )
        if disposition != "candidate":
            proposal_gates.append(
                {
                    "proposal_id": "",
                    "target_resolution": resolution,
                    "machine_disposition": disposition,
                    "target_version": target_version,
                }
            )
            continue
        record, _ = store.upsert(
            target_skill=safe_target,
            target_version=target_version,
            proposal_type="deep_dream_candidate",
            change_points=[
                *safe_points,
                *[f"验收：{item}" for item in safe_tests],
            ],
            summary=safe_summary,
            machine_disposition=disposition,
            source_session_ids=[str(item.get("session_id_hash", "")) for item in packet["sessions"]],
            evidence_ids=candidate["evidence_ids"],
            artifact_paths=[artifact_ref],
            privacy_status="passed",
            artifact_content_sha256=str(artifact["content_sha256"]),
            target_content_sha256=target_content_hash,
            target_resolution=resolution,
        )
        proposal_ids.append(str(record["proposal_id"]))
        proposal_gates.append(
            {
                "proposal_id": str(record["proposal_id"]),
                "target_resolution": resolution,
                "machine_disposition": str(record["machine_disposition"]),
                "target_version": target_version,
            }
        )
    status = {
        "cluster_id": cluster_id,
        "analysis_status": "available",
        "artifact_ref": artifact_ref,
        "proposal_ids": proposal_ids,
        "proposal_gates": proposal_gates,
        "human_decision": "pending",
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return persist_deep_attempt(status, success=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Explicit optional LLM analysis for Dream Sweep clusters")
    parser.add_argument("--clusters", type=Path, default=CLUSTERS_PATH)
    parser.add_argument("--cluster-id", default="")
    parser.add_argument("--max-clusters", "--max-reports", dest="max_clusters", type=int, default=3)
    parser.add_argument("--execute", action="store_true", help="Explicitly allow the optional Claude CLI call")
    parser.add_argument("--claude-bin", default="claude")
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--max-budget-usd", type=parse_total_budget, default=None)
    parser.add_argument(
        "--per-call-budget-usd",
        type=parse_per_call_budget,
        default=0.10,
        help="Per-cluster Claude cap; the invocation-wide --max-budget-usd is never exceeded",
    )
    parser.add_argument("--max-calls", type=int, default=5)
    parser.add_argument("--budget", choices=["low", "medium", "high"], default="low")
    parser.add_argument("--since", default="", help="Compatibility only; clusters are selected from the current index")
    parser.add_argument("--dry-run", action="store_true", help="Prepare packets without invoking Claude")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        assert_runtime_ready()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.dry_run:
        args.execute = False
    if args.max_budget_usd is None:
        args.max_budget_usd = {"low": 0.25, "medium": 0.75, "high": 2.0}[args.budget]
    if args.per_call_budget_usd > args.max_budget_usd:
        print("--per-call-budget-usd cannot exceed --max-budget-usd", file=sys.stderr)
        return 2

    clusters = load_clusters(args.clusters)
    if args.cluster_id:
        clusters = [item for item in clusters if item.get("cluster_id") == args.cluster_id]
    clusters = [item for item in clusters if item.get("quality_gate") == "deep_eligible"]
    # Keep both fan-out and total possible spend bounded. Reserve each call's
    # full cap before invoking it; this is conservative even when Claude spends less.
    max_clusters = max(0, min(args.max_clusters, 10))
    clusters = clusters[:max_clusters]
    total_budget = max(0.0, float(args.max_budget_usd))
    per_call_budget = max(0.01, float(args.per_call_budget_usd))
    max_calls = max(0, min(int(args.max_calls), 10))
    reserved_budget = 0.0
    call_count = 0
    results: list[dict[str, Any]] = []
    for cluster in clusters:
        if args.execute:
            if call_count >= max_calls or reserved_budget + per_call_budget > total_budget + 1e-9:
                results.append(unavailable(str(cluster.get("cluster_id") or "unknown"), "invocation_budget_exhausted"))
                continue
            reserved_budget += per_call_budget
            call_count += 1
            args.call_budget_usd = per_call_budget
        results.append(process_cluster(cluster, args))
    available_count = sum(item.get("analysis_status") == "available" for item in results)
    prepared_count = sum(item.get("analysis_status") == "prepared" for item in results)
    payload = {
        "analysis_layer": "optional_deep",
        "analysis_status": (
            "available" if available_count else ("prepared" if prepared_count else "analysis_unavailable")
        ),
        "reason": (
            ""
            if available_count
            else (
                "explicit_execution_required"
                if prepared_count
                else ("all_analyses_unavailable" if results else "no_deep_eligible_clusters")
            )
        ),
        "available_count": available_count,
        "prepared_count": prepared_count,
        "call_count": call_count,
        "max_calls": max_calls,
        "max_budget_usd": round(total_budget, 2),
        "reserved_budget_usd": round(reserved_budget, 2),
        "results": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else json.dumps(payload, ensure_ascii=False))
    if args.execute and results and available_count == 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
