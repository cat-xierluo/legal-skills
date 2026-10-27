"""Source-bound public adoption receipts; never apply a proposal or migrate SQLite."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
import unicodedata
from contextlib import contextmanager, closing
from pathlib import Path

import public_workflow as flow
from privacy_gate import read_confined_regular

SCHEMA = "self-evolve-public-adoption-v1"
LEDGER = "adoptions.json"
MAX_LEDGER_BYTES = 16 * 1024 * 1024
TRANSITIONS = {"pending": {"accepted", "rejected", "observe"},
               "observe": {"accepted", "rejected"}, "accepted": {"applied"},
               "applied": {"verified", "failed", "inconclusive"}}
HEX64 = re.compile(r"[0-9a-f]{64}")


def _identifier(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}", value):
        raise ValueError(f"invalid_{label}")
    return value


@contextmanager
def _sources(root):
    """Even SQLite mode=ro can touch WAL/SHM; only connect to a disposable copy."""
    path = root / "ledger.sqlite"
    if not path.is_file() or path.is_symlink():
        raise ValueError("adoption_source_ledger_missing")
    with tempfile.TemporaryDirectory(prefix="self-evolve-adoption-read-") as td:
        for suffix in ("", "-wal", "-shm"):
            source = root / ("ledger.sqlite" + suffix)
            if source.exists():
                if source.is_symlink() or not source.is_file():
                    raise ValueError("invalid_adoption_source_ledger")
                shutil.copy2(source, Path(td) / source.name)
        uri = (Path(td) / "ledger.sqlite").as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            flow._assert_ledger_structure(conn)
            yield conn


def _bound_source(root, conn, analysis_id):
    _identifier(analysis_id, "analysis_id")
    row = conn.execute("SELECT rowid AS source_sequence,* FROM analyses WHERE analysis_id=?", (analysis_id,)).fetchone()
    if not row:
        raise ValueError("unknown_adoption_analysis")
    run_id = row["run_id"]
    if not isinstance(run_id, str) or not re.fullmatch(r"[0-9]{8}T[0-9]{6}-[0-9a-f]{12}", run_id):
        raise ValueError("invalid_adoption_source_run")
    packet = json.loads(read_confined_regular(root, Path("runs") / run_id / "packet.json", label="adoption packet"))
    analysis = json.loads(row["analysis_json"])
    disk_analysis = json.loads(read_confined_regular(root, Path("runs") / run_id / (analysis_id + ".json"), label="adoption analysis"))
    if not isinstance(packet, dict) or not isinstance(analysis, dict) or flow.canonical(analysis) != flow.canonical(disk_analysis):
        raise ValueError("adoption_analysis_hash_mismatch")
    payload = dict(packet)
    packet_digest = payload.pop("packet_digest", None)
    run = conn.execute("SELECT packet_digest FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if (packet.get("schema_version") != flow.PACKET_SCHEMA or packet.get("run_id") != run_id
        or not run or run[0] != packet_digest or row["packet_digest"] != packet_digest
        or flow.digest(payload) != packet_digest or analysis.get("packet_digest") != packet_digest
        or analysis.get("schema_version") != flow.ANALYSIS_SCHEMA):
        raise ValueError("adoption_packet_hash_mismatch")
    evidence = packet.get("evidence")
    proposals = analysis.get("skill_proposals")
    if not isinstance(evidence, list) or not isinstance(proposals, list):
        raise ValueError("invalid_adoption_source")
    by_id = {}
    for item in evidence:
        if not isinstance(item, dict) or not isinstance(item.get("evidence_id"), str) or item["evidence_id"] in by_id:
            raise ValueError("invalid_adoption_source_evidence")
        by_id[item["evidence_id"]] = item
    bindings = []
    seen = set()
    for index, proposal in enumerate(proposals):
        if not isinstance(proposal, dict):
            raise ValueError("invalid_adoption_source_proposal")
        ids = proposal.get("evidence_ids")
        points = proposal.get("change_points")
        if (not isinstance(ids, list) or not ids or any(not isinstance(e, str) or e not in by_id for e in ids)
            or not isinstance(points, list) or not points or any(not isinstance(p, str) or not p.strip() for p in points)
            or proposal.get("action") not in ("create", "reference", "upgrade")
            or not isinstance(proposal.get("target_skill"), str)
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", proposal["target_skill"])):
            raise ValueError("invalid_adoption_source_proposal")
        normalized = sorted({" ".join(unicodedata.normalize("NFKC", p).split()) for p in points})
        proposal_id = "proposal-" + flow.digest([proposal["target_skill"], proposal["action"], normalized])
        revision = flow.digest([proposal, packet_digest, [by_id[e] for e in sorted(set(ids))]])
        if proposal_id in seen:
            raise ValueError("duplicate_adoption_source_proposal")
        seen.add(proposal_id)
        bindings.append({"proposal_index": index, "proposal_id": proposal_id, "revision": revision})
    source = {"analysis_digest": flow.digest(analysis), "packet_digest": packet_digest,
              "run_id": run_id, "source_sequence": row["source_sequence"], "proposals": bindings}
    return source, packet, analysis


def _event_input(value):
    if not isinstance(value, dict):
        raise ValueError("invalid_adoption_event")
    status = value.get("status")
    if not isinstance(status, str) or status not in set().union(*TRANSITIONS.values()):
        raise ValueError("invalid_adoption_status")
    required = {"request_id", "status", "actor", "reason"}
    optional = set()
    if status == "accepted":
        required.add("authorization_ref")
    elif status == "applied":
        required.add("file_scope")
        optional = {"commit_oid", "artifact_sha256"}
    elif status in {"verified", "failed", "inconclusive"}:
        required.update({"applied_event_id", "verification_ref"})
    if not required <= value.keys() or value.keys() - required - optional:
        raise ValueError("invalid_adoption_event_fields")
    request_id = _identifier(value["request_id"], "request_id")
    if flow._text(request_id, "adoption_request_id", max_len=160) != request_id:
        raise ValueError("invalid_adoption_request_id")
    result = {"request_id": request_id, "status": status}
    for field in ("actor", "reason", "authorization_ref", "verification_ref"):
        if field in value:
            result[field] = flow._text(value[field], "adoption_" + field, max_len=2000)
    if status == "applied":
        scope = value["file_scope"]
        if not isinstance(scope, list) or not 1 <= len(scope) <= 100:
            raise ValueError("invalid_adoption_file_scope")
        result["file_scope"] = []
        for path in scope:
            if (not isinstance(path, str) or not path.strip() or len(path) > 500
                or "\\" in path or ":" in path or path.startswith(("/", "~"))
                or any(p in {"", ".", ".."} for p in path.split("/"))):
                raise ValueError("invalid_adoption_file_scope")
            result["file_scope"].append(flow._text(path, "adoption_file_scope", max_len=500))
        for field in ("commit_oid", "artifact_sha256"):
            if field in value:
                pattern = r"[0-9a-f]{40}|[0-9a-f]{64}" if field == "commit_oid" else r"[0-9a-f]{64}"
                if not isinstance(value[field], str) or not re.fullmatch(pattern, value[field]):
                    raise ValueError("invalid_adoption_" + field)
                result[field] = value[field]
        if not any(field in result for field in optional):
            raise ValueError("missing_adoption_artifact_binding")
    if "applied_event_id" in value:
        result["applied_event_id"] = _identifier(value["applied_event_id"], "applied_event_id")
    return result


def _timestamp(value):
    from datetime import datetime
    if not isinstance(value, str):
        raise ValueError("invalid_adoption_timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("invalid_adoption_timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("invalid_adoption_timestamp")
    return value


def _first_imports(conn, packet):
    """Content age comes from all imports, including sources not registered yet."""
    by_id = {e["evidence_id"]: e for e in packet["evidence"]}
    origins = {}
    for row in conn.execute("SELECT rowid,analysis_json FROM analyses WHERE packet_digest=? ORDER BY rowid",
                            (packet["packet_digest"],)):
        history = json.loads(row["analysis_json"])
        if not isinstance(history, dict) or not isinstance(history.get("skill_proposals"), list):
            raise ValueError("invalid_adoption_source_history")
        for proposal in history["skill_proposals"]:
            ids = proposal.get("evidence_ids") if isinstance(proposal, dict) else None
            if not isinstance(ids, list) or not ids or any(not isinstance(e, str) or e not in by_id for e in ids):
                raise ValueError("invalid_adoption_source_history")
            revision = flow.digest([proposal, packet["packet_digest"], [by_id[e] for e in sorted(set(ids))]])
            origins.setdefault(revision, row["rowid"])
    return origins


def _catalog(ledger, imported=None):
    revisions, first_seen, current = {}, {}, {}
    for source in ledger["analyses"].values():
        for binding in source["proposals"]:
            key = (binding["proposal_id"], binding["revision"])
            revisions[key] = binding
            sequence = imported.get(binding["revision"], source["source_sequence"]) if imported is not None else source["source_sequence"]
            first_seen[key] = min(first_seen.get(key, sequence), sequence)
    # A new renderer may create a later analysis row for old proposal content.
    # Repeated source bindings must not promote that old content revision.
    for (proposal_id, revision), sequence in first_seen.items():
        prior = current.get(proposal_id)
        if prior is None or sequence > prior[0]:
            current[proposal_id] = (sequence, revision)
    return revisions, current


def _validate_events(ledger):
    revisions, _ = _catalog(ledger)
    states, requests, applied = {}, set(), {}
    for event in ledger["events"]:
        if not isinstance(event, dict):
            raise ValueError("invalid_adoption_stored_event")
        generated = {"proposal_id", "revision", "event_id", "at", "request_hash"}
        if not generated <= event.keys():
            raise ValueError("invalid_adoption_stored_event")
        data = _event_input({k: v for k, v in event.items() if k not in generated})
        if any(event[k] != v for k, v in data.items()):
            raise ValueError("invalid_adoption_stored_event")
        _timestamp(event["at"])
        _identifier(event["proposal_id"], "proposal_id")
        if not isinstance(event["revision"], str) or not HEX64.fullmatch(event["revision"]):
            raise ValueError("invalid_adoption_revision")
        key = (event["proposal_id"], event["revision"])
        if key not in revisions:
            raise ValueError("unknown_adoption_event_source")
        request_hash = flow.digest([*key, data])
        if event["request_hash"] != request_hash or event["event_id"] != "evt-" + request_hash:
            raise ValueError("adoption_event_hash_mismatch")
        if data["request_id"] in requests:
            raise ValueError("duplicate_adoption_request")
        requests.add(data["request_id"])
        previous = states.get(key, "pending")
        if data["status"] not in TRANSITIONS.get(previous, set()):
            raise ValueError("invalid_adoption_transition")
        if data["status"] in {"verified", "failed", "inconclusive"} and data["applied_event_id"] != applied.get(key):
            raise ValueError("adoption_applied_event_mismatch")
        if data["status"] == "applied":
            applied[key] = event["event_id"]
        states[key] = data["status"]
    return states


def _load(root, conn):
    path = root / LEDGER
    if not path.exists() and not path.is_symlink():
        return {"schema_version": SCHEMA, "updated_at": "1970-01-01T00:00:00+00:00", "analyses": {}, "events": []}, {}
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_LEDGER_BYTES:
        raise ValueError("invalid_adoption_ledger")
    try:
        ledger = json.loads(path.read_bytes())
    except (ValueError, UnicodeError) as exc:
        raise ValueError("invalid_adoption_ledger_json") from exc
    if not isinstance(ledger, dict) or ledger.get("schema_version") != SCHEMA:
        raise ValueError("unsupported_adoption_ledger_schema")
    if (set(ledger) != {"schema_version", "updated_at", "analyses", "events"}
        or not isinstance(ledger["analyses"], dict) or not isinstance(ledger["events"], list)):
        raise ValueError("invalid_adoption_ledger")
    _timestamp(ledger["updated_at"])
    imported, seen_packets = {}, set()
    for analysis_id, stored in ledger["analyses"].items():
        if not isinstance(stored, dict) or "registered_at" not in stored:
            raise ValueError("invalid_adoption_registration")
        _timestamp(stored["registered_at"])
        expected, packet, _ = _bound_source(root, conn, analysis_id)
        if flow.canonical({k: v for k, v in stored.items() if k != "registered_at"}) != flow.canonical(expected):
            raise ValueError("adoption_source_binding_changed")
        if packet["packet_digest"] not in seen_packets:
            imported.update(_first_imports(conn, packet))
            seen_packets.add(packet["packet_digest"])
    _validate_events(ledger)
    return ledger, imported


def _snapshot(ledger, analysis_id):
    states = _validate_events(ledger)
    source = ledger["analyses"].get(analysis_id, {})
    return {"schema_version": SCHEMA, "analysis_id": analysis_id,
            "ledger_digest": flow.digest(ledger), "snapshot_at": ledger["updated_at"],
            "proposals": [{**b, "status": states.get((b["proposal_id"], b["revision"]), "pending"),
                           "events": [copy.deepcopy(e) for e in ledger["events"]
                                      if (e["proposal_id"], e["revision"]) == (b["proposal_id"], b["revision"])]}
                          for b in source.get("proposals", [])]}


def _save(root, ledger):
    # Never commit a ledger that its next reader would reject for size.
    if len(json.dumps(ledger, ensure_ascii=False, indent=2).encode()) + 1 > MAX_LEDGER_BYTES:
        raise ValueError("adoption_ledger_size_budget_exceeded")
    flow.write_json(root / LEDGER, ledger)


def register_proposals(root: Path, analysis_id: str) -> dict:
    with flow.locked(root), _sources(root) as conn:
        ledger, _ = _load(root, conn)
        source, _, _ = _bound_source(root, conn, analysis_id)
        prior = ledger["analyses"].get(analysis_id)
        if prior is None:
            ledger["updated_at"] = flow.now()
            ledger["analyses"][analysis_id] = {**source, "registered_at": ledger["updated_at"]}
            _save(root, ledger)
        return {"status": "proposals_registered", "idempotent": prior is not None,
                **_snapshot(ledger, analysis_id)}


def record_adoption(root: Path, proposal_id: str, revision: str, event: dict) -> dict:
    _identifier(proposal_id, "proposal_id")
    if not isinstance(revision, str) or not HEX64.fullmatch(revision):
        raise ValueError("invalid_adoption_revision")
    data = _event_input(event)
    with flow.locked(root), _sources(root) as conn:
        ledger, imported = _load(root, conn)
        revisions, current = _catalog(ledger, imported)
        key = (proposal_id, revision)
        if key not in revisions:
            raise ValueError("unknown_adoption_proposal_revision")
        if current[proposal_id][1] != revision:
            raise ValueError("stale_adoption_revision")
        request_hash = flow.digest([*key, data])
        for prior in ledger["events"]:
            if prior["request_id"] == data["request_id"]:
                if prior["request_hash"] != request_hash:
                    raise ValueError("adoption_request_conflict")
                return {"status": "adoption_recorded", "idempotent": True, "event": copy.deepcopy(prior)}
        receipt = {**data, "proposal_id": proposal_id, "revision": revision,
                   "event_id": "evt-" + request_hash, "request_hash": request_hash, "at": flow.now()}
        ledger["events"].append(receipt)
        _validate_events(ledger)
        ledger["updated_at"] = receipt["at"]
        _save(root, ledger)
        return {"status": "adoption_recorded", "idempotent": False, "event": receipt}


def adoption_status(root: Path, analysis_id: str | None = None) -> dict:
    with flow.locked(root), _sources(root) as conn:
        ledger, _ = _load(root, conn)
        if analysis_id is not None:
            _bound_source(root, conn, analysis_id)
            return _snapshot(ledger, analysis_id)
        return {"status": "adoption_status", "schema_version": SCHEMA,
                "ledger_digest": flow.digest(ledger), "snapshot_at": ledger["updated_at"],
                "analyses": [_snapshot(ledger, aid) for aid in ledger["analyses"]]}


def render_adoptions(root: Path, analysis_id: str) -> dict:
    with flow.locked(root), _sources(root) as conn:
        ledger, _ = _load(root, conn)
        _, packet, analysis = _bound_source(root, conn, analysis_id)
        snapshot = _snapshot(ledger, analysis_id)
        import public_report
        renderer_hash = hashlib.sha256(Path(public_report.__file__).read_bytes()).hexdigest()
        # Keep the complete binding hash within the report renderer's stem limit.
        stem = "adoptions-" + flow.digest([analysis, renderer_hash, snapshot])
        run_dir = root / "runs" / packet["run_id"]
        pages = flow.publish_report(run_dir, stem, packet, analysis, adoptions=snapshot)
        return {"status": "adoptions_rendered", "analysis_id": analysis_id,
                "report": str(run_dir / (stem + ".html")), "report_pages": pages,
                "adoptions": snapshot}
