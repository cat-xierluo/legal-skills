#!/usr/bin/env python3
"""Offline evidence binding for Agent-authored semantic reuse proposals.

Reads only the supplied JSON and target SKILL.md; never executes upstream text.
The result is admissibility for an experiment, not semantic proof or adoption.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

PACKET_SCHEMA = "reuse-input/1"
REPORT_SCHEMA = "reuse-assessment/1"
RULES_VERSION = "1"
CHECKS = ("delivery", "authority", "unit", "runtime", "license_code",
          "license_assets", "license_service", "local_gap", "mechanism")
CATEGORIES = {"capability_package", "backend_candidate", "method_only",
              "not_applicable", "needs_evidence"}
TRANSFERS = {"rule_only", "code", "asset", "interface"}
MAX_BYTES = 1_500_000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(value):
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")).encode())


def read_json(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("JSON exceeds input budget")
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError("JSON exceeds input budget")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object")
    return value


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing text: {label}")
    return value


def source(key, side, body, anchor):
    return {"id": key, "side": side, "text": body,
            "sha256": sha(body.encode()), "anchor": anchor}


def binding(candidate, local):
    if not isinstance(candidate, dict):
        raise ValueError("candidate must be object")
    for name in ("candidate_key", "project_id", "repo"):
        text(candidate.get(name), name)
    capability = candidate.get("capability") or {}
    if not isinstance(capability, dict):
        raise ValueError("candidate.capability must be object")
    return {**{k: candidate.get(k) for k in
               ("candidate_key", "project_id", "repo", "repo_id", "repo_revision",
                "evidence_revision", "target_revision")},
            "capability_key": capability.get("key"),
            "skill_path": candidate.get("skill_path"),
            "skill_sha256": local["sha256"]}


def prepare(candidate, skill_path):
    directory = Path(skill_path).expanduser().resolve()
    if directory.name == "SKILL.md":
        directory = directory.parent
    expected = candidate.get("skill_path")
    if not expected or Path(expected).expanduser().resolve() != directory:
        raise ValueError("skill_path differs from dynamic candidate target")
    if (directory / "SKILL.md").stat().st_size > MAX_BYTES:
        raise ValueError("SKILL.md exceeds input budget")
    raw = (directory / "SKILL.md").read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError("SKILL.md exceeds input budget")
    local = source("local-skill", "local", raw.decode("utf-8"), str(directory / "SKILL.md"))
    # Hash original bytes as well; UTF-8 decoding preserves newline bytes here.
    sources = [local]
    summary = candidate.get("evidence_summary") or {}
    if not isinstance(summary, dict):
        raise ValueError("evidence_summary must be object")
    for section in ("readme", "release", "commits"):
        body = summary.get(section)
        if body:
            text(body, section)
            sources.append(source("upstream-" + section, "upstream", body, {
                "repo": candidate["repo"], "section": section,
                "carried_source": summary.get("source"),
                "observed": summary.get("observed"),
                "probe": summary.get("probe"),
                "this_run_observation": ("unknown" if summary.get("source") != "this_run"
                                         or summary.get("probe") == "cheap" and section != "release"
                                         else "consult per-field observed metadata; not independently verified"),
                "freshness": "carried text; fetched_at is not per-field observation proof",
                "revision": candidate.get("evidence_revision"),
                "blob_sha": summary.get("readme_blob_sha") if section == "readme" else None,
                "head_sha": summary.get("head_sha"),
                "release_url": summary.get("release_url"),
                "truncated": summary.get(section + "_truncated", False),
            }))
    packet = {"schema": PACKET_SCHEMA, "candidate": candidate,
              "binding": binding(candidate, local), "sources": sources}
    packet["packet_sha256"] = digest(packet)
    return packet


def validate_packet(packet):
    if not isinstance(packet, dict):
        raise ValueError("Input packet must be object")
    if packet.get("schema") != PACKET_SCHEMA:
        raise ValueError("Unsupported input schema")
    if packet.get("packet_sha256") != digest({k: v for k, v in packet.items() if k != "packet_sha256"}):
        raise ValueError("Input packet hash mismatch")
    sources = packet.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("Missing sources")
    indexed = {}
    for row in sources:
        if not isinstance(row, dict) or row.get("side") not in {"local", "upstream"}:
            raise ValueError("Invalid source")
        key = text(row.get("id"), "source.id")
        if key in indexed or row.get("sha256") != sha(text(row.get("text"), key).encode()):
            raise ValueError("Duplicate source or source hash mismatch")
        indexed[key] = row
    local = indexed.get("local-skill")
    if not local or local["side"] != "local":
        raise ValueError("Missing local SKILL source")
    candidate = packet["candidate"]
    if not isinstance(candidate, dict):
        raise ValueError("candidate must be object")
    summary = candidate.get("evidence_summary") or {}
    if not isinstance(summary, dict):
        raise ValueError("evidence_summary must be object")
    expected_ids = {"local-skill"}
    for section in ("readme", "release", "commits"):
        if summary.get(section):
            expected_ids.add("upstream-" + section)
            row = indexed.get("upstream-" + section, {})
            if row.get("side") != "upstream" or row.get("text") != summary[section]:
                raise ValueError("Source differs from carried candidate evidence")
    if set(indexed) != expected_ids:
        raise ValueError("Sources differ from carried candidate evidence")
    if packet.get("binding") != binding(candidate, local):
        raise ValueError("Input binding mismatch")
    return indexed


def evaluate(packet, review):
    sources = validate_packet(packet)
    if not isinstance(review, dict):
        raise ValueError("Review must be object")
    if review.get("packet_sha256") != packet["packet_sha256"] or review.get("binding") != packet["binding"]:
        raise ValueError("Review belongs to another candidate/input revision")
    items = review.get("proposals")
    if not isinstance(items, list) or not items:
        raise ValueError("proposals must be nonempty list")
    results, ids = [], set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("proposal must be object")
        key = text(item.get("id"), "proposal.id")
        if key in ids:
            raise ValueError("Duplicate proposal id")
        ids.add(key)
        requested = item.get("category")
        if requested not in CATEGORIES:
            raise ValueError("Invalid proposal category")
        checks = item.get("checks", {})
        if not isinstance(checks, dict) or set(checks) - set(CHECKS):
            raise ValueError("Invalid checks")
        outcomes, sides = {}, {}
        for name in CHECKS:
            check = checks.get(name, {"status": "unknown"})
            if not isinstance(check, dict) or check.get("status") not in {"pass", "fail", "unknown"}:
                raise ValueError(f"Invalid check: {name}")
            outcome = check["status"]
            sides[name] = set()
            if outcome != "unknown":
                text(check.get("claim"), name + ".claim")
                refs = check.get("refs")
                if not isinstance(refs, list) or not refs:
                    raise ValueError(f"{name}: pass/fail requires source excerpts")
                for ref in refs:
                    if not isinstance(ref, dict) or ref.get("source") not in sources:
                        raise ValueError(f"{name}: unknown source")
                    row = sources[ref["source"]]
                    excerpt = text(ref.get("excerpt"), name + ".excerpt")
                    if ref.get("sha256") != row["sha256"] or excerpt not in row["text"]:
                        raise ValueError(f"{name}: source hash/excerpt mismatch")
                    sides[name].add(row["side"])
            outcomes[name] = outcome
        needed = []
        required_sides = {}
        if requested in {"capability_package", "backend_candidate"}:
            needed = list(CHECKS[:-1])
            required_sides = {name: {"local", "upstream"} for name in
                              ("delivery", "authority", "unit", "runtime")}
            required_sides.update({name: {"upstream"} for name in
                                   ("license_code", "license_assets", "license_service")})
            required_sides["local_gap"] = {"local"}
        elif requested == "method_only":
            text(item.get("mechanism"), "mechanism")
            transfer = item.get("transfer_type")
            if transfer not in TRANSFERS:
                raise ValueError("method_only needs transfer_type")
            needed = ["mechanism", "local_gap"]
            required_sides = {"mechanism": {"upstream"}, "local_gap": {"local"}}
            license_check = {"code": "license_code", "asset": "license_assets", "interface": "license_service"}.get(transfer)
            if license_check:
                needed.append(license_check)
                required_sides[license_check] = {"upstream"}
        blockers = [name for name in needed if outcomes[name] != "pass" or
                    not required_sides.get(name, set()).issubset(sides[name])]
        missing = [name for name in needed if outcomes[name] == "unknown" or
                   not required_sides.get(name, set()).issubset(sides[name])]
        # Unknown revisions never become a positive claim or a rejection.
        revisions_known = all(isinstance(packet["binding"].get(k), str) and packet["binding"][k].strip()
                              for k in ("repo_revision", "evidence_revision", "target_revision"))
        if not revisions_known:
            blockers.append("binding_revisions")
            missing.append("binding_revisions")
        category = requested
        if requested == "not_applicable":
            # A counterexample is limited to this proposal and bound capability.
            counterexamples = [name for name in CHECKS if outcomes[name] == "fail" and sides[name] == {"local", "upstream"}]
            if not counterexamples:
                blockers.append("counterexample")
                missing.append("counterexample")
        if blockers:
            category = "needs_evidence"
        if category == "needs_evidence" and not missing:
            missing = [name for name in CHECKS if outcomes[name] == "unknown"]
        results.append({"id": key, "requested_category": requested, "category": category,
                        "checks": outcomes, "blockers": blockers, "next_evidence": missing,
                        "max_decision_status": ("rejected" if category == "not_applicable" else
                                                "deferred" if category == "needs_evidence" else "experiment_proposed")})
    return {"rules_version": RULES_VERSION, "binding": packet["binding"], "proposals": results}


def make_report(packet, review):
    return {"schema": REPORT_SCHEMA, "packet": packet, "review": review,
            "result": evaluate(packet, review)}


def validate_report(report):
    if not isinstance(report, dict) or report.get("schema") != REPORT_SCHEMA:
        raise ValueError("Unsupported report schema")
    expected = evaluate(report["packet"], report["review"])
    if report.get("result") != expected:
        raise ValueError("Report result differs from recomputed rules")
    return expected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    mode = prep.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run")
    mode.add_argument("--candidate")
    prep.add_argument("--candidate-key")
    prep.add_argument("--skill-path", required=True)
    prep.add_argument("--output", required=True)
    ev = sub.add_parser("evaluate")
    ev.add_argument("--packet", required=True)
    ev.add_argument("--review", required=True)
    ev.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            if args.run:
                run = read_json(args.run)
                rows = run.get("items")
                if not args.candidate_key or not isinstance(rows, list):
                    raise ValueError("--run requires candidate-key and items list")
                rows = [row for row in rows if isinstance(row, dict) and row.get("candidate_key") == args.candidate_key]
                if len(rows) != 1:
                    raise ValueError("candidate_key must identify exactly one item")
                candidate = rows[0]
            else:
                candidate = read_json(args.candidate)
            value = prepare(candidate, args.skill_path)
        else:
            value = make_report(read_json(args.packet), read_json(args.review))
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(output), "sha256": sha(output.read_bytes())}))
        return 0
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
