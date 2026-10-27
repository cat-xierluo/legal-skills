#!/usr/bin/env python3
"""Export privacy-gated, cross-session preference evidence for Info Evaluator.

This command is deterministic and never calls a model. It reuses the Dream
Sweep cluster privacy boundary, then emits only the minimum fields required by
the personal-preference bridge contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from deep_dream import CLUSTERS_PATH, atomic_json, build_packet, load_clusters
from privacy_gate import validate_text, validate_untrusted_source
from self_evolve_paths import RUNTIME_ROOT, assert_runtime_ready


SCHEMA_VERSION = "self-evolve-preference-evidence-v1"
DEFAULT_OUTPUT = RUNTIME_ROOT / "preference-bridge" / "evidence-packet.json"
DEFAULT_MAX_CLUSTERS = 20
MAX_EVIDENCE_CHARS = 1200
SHORT_HASH = re.compile(r"^[0-9a-f]{16}$")


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _bridge_cluster(cluster: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    if cluster.get("quality_gate") != "deep_eligible":
        return None, "not_deep_eligible"
    try:
        safe = build_packet(cluster)
    except ValueError:
        return None, "privacy_blocked"

    session_hashes = {
        str(item.get("session_id_hash", ""))
        for item in safe.get("sessions", [])
        if isinstance(item, dict) and SHORT_HASH.fullmatch(str(item.get("session_id_hash", "")))
    }
    if len(session_hashes) < 2:
        return None, "insufficient_sessions"

    evidence: list[dict[str, str]] = []
    evidence_ids: set[str] = set()
    evidence_sessions: set[str] = set()
    for item in safe.get("evidence", []):
        if not isinstance(item, dict):
            continue
        evidence_id = str(item.get("evidence_id", "")).strip()
        source_hash = str(item.get("source_session_id_hash", "")).strip()
        text = str(item.get("text", "")).strip()
        if (
            not evidence_id
            or evidence_id in evidence_ids
            or source_hash not in session_hashes
            or not SHORT_HASH.fullmatch(source_hash)
            or not text
            or len(text) > MAX_EVIDENCE_CHARS
        ):
            continue
        blockers = [*validate_untrusted_source(text), *validate_text(text)]
        if blockers:
            return None, "privacy_blocked"
        evidence.append(
            {
                "evidence_id": evidence_id,
                "source_session_id_hash": source_hash,
                "text": text,
            }
        )
        evidence_ids.add(evidence_id)
        evidence_sessions.add(source_hash)

    if len(evidence) < 2 or len(evidence_sessions) < 2:
        return None, "insufficient_cross_session_evidence"

    source_cluster_id = str(cluster.get("cluster_id", "")).strip()
    if not source_cluster_id:
        return None, "missing_cluster_id"
    cluster_id = "pref-clu-" + hashlib.sha256(
        source_cluster_id.encode("utf-8", errors="replace")
    ).hexdigest()[:20]
    title = str(safe.get("title", "")).strip()
    # Do not re-read untrusted raw cluster metadata after build_packet's privacy gate.
    topic_key = str(title or cluster_id).strip()
    result = {
        "cluster_id": cluster_id,
        "topic_key": topic_key[:120],
        "title": title[:200],
        "session_count": len(session_hashes),
        "source_session_id_hashes": sorted(session_hashes),
        "evidence": evidence,
    }
    return result, None


def build_evidence_packet(
    clusters: list[dict[str, Any]], *, max_clusters: int | None = None
) -> dict[str, Any]:
    exported: list[dict[str, Any]] = []
    skipped: dict[str, int] = {}
    for cluster in clusters:
        item, reason = _bridge_cluster(cluster)
        if item is None:
            reason = reason or "invalid"
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        exported.append(item)
        if max_clusters is not None and len(exported) >= max_clusters:
            break
    exported.sort(key=lambda item: str(item["cluster_id"]))
    packet = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_digest": canonical_digest(exported),
        "clusters": exported,
        "export_summary": {"exported": len(exported), "skipped": skipped},
    }
    verify_evidence_packet(packet)
    return packet


def verify_evidence_packet(packet: Any) -> None:
    if not isinstance(packet, dict) or packet.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid preference evidence schema")
    clusters = packet.get("clusters")
    if not isinstance(clusters, list):
        raise ValueError("clusters must be an array")
    if packet.get("source_digest") != canonical_digest(clusters):
        raise ValueError("source digest mismatch")

    seen_clusters: set[str] = set()
    seen_evidence: set[str] = set()
    for cluster in clusters:
        if not isinstance(cluster, dict):
            raise ValueError("cluster must be an object")
        cluster_id = str(cluster.get("cluster_id", ""))
        if not cluster_id or cluster_id in seen_clusters:
            raise ValueError("cluster ids must be non-empty and unique")
        seen_clusters.add(cluster_id)
        source_hashes = cluster.get("source_session_id_hashes")
        if (
            not isinstance(source_hashes, list)
            or len(set(source_hashes)) < 2
            or any(not SHORT_HASH.fullmatch(str(value)) for value in source_hashes)
        ):
            raise ValueError("cluster requires at least two hashed sessions")
        evidence = cluster.get("evidence")
        if not isinstance(evidence, list) or len(evidence) < 2:
            raise ValueError("cluster requires at least two evidence items")
        evidence_sessions: set[str] = set()
        for item in evidence:
            if not isinstance(item, dict):
                raise ValueError("evidence must be an object")
            evidence_id = str(item.get("evidence_id", ""))
            source_hash = str(item.get("source_session_id_hash", ""))
            text = str(item.get("text", ""))
            if not evidence_id or evidence_id in seen_evidence:
                raise ValueError("evidence ids must be non-empty and globally unique")
            if source_hash not in source_hashes or not SHORT_HASH.fullmatch(source_hash):
                raise ValueError("evidence source hash is invalid")
            blockers = [*validate_untrusted_source(text), *validate_text(text)]
            if not text or len(text) > MAX_EVIDENCE_CHARS or blockers:
                raise ValueError("evidence failed privacy validation")
            seen_evidence.add(evidence_id)
            evidence_sessions.add(source_hash)
        if len(evidence_sessions) < 2:
            raise ValueError("evidence must span at least two sessions")


def load_and_verify(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read evidence packet: {path}") from exc
    verify_evidence_packet(payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导出跨会话脱敏偏好证据包（不调用模型）")
    parser.add_argument("--clusters", type=Path, default=CLUSTERS_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-clusters", type=int, default=DEFAULT_MAX_CLUSTERS)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.max_clusters is not None and args.max_clusters <= 0:
        parser.error("--max-clusters must be greater than 0")

    try:
        if args.verify_only:
            packet = load_and_verify(args.output)
        else:
            assert_runtime_ready()
            packet = build_evidence_packet(
                load_clusters(args.clusters), max_clusters=args.max_clusters
            )
            atomic_json(args.output, packet)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    result = {
        "status": "verified" if args.verify_only else "exported",
        "path": str(args.output),
        "clusters": len(packet["clusters"]),
        "source_digest": packet["source_digest"],
    }
    print(json.dumps(result, ensure_ascii=False) if args.json else result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
