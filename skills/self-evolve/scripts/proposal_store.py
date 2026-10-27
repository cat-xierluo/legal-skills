#!/usr/bin/env python3
"""Append-audited proposal lifecycle for Self Evolve.

Machine records and human/lifecycle events are stored separately. A projected
proposal is assembled on read so automated upserts cannot overwrite a human
decision.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import re
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows is not a supported runtime today.
    fcntl = None  # type: ignore[assignment]

from self_evolve_paths import (
    PROPOSALS_ROOT,
    REVIEW_ARCHIVE_ROOT,
    REVIEW_INBOX_ROOT,
    assert_external_write_path,
    assert_runtime_ready,
)
from privacy_gate import publish_immutable_bytes, read_confined_regular, sanitize_structured_text


SCHEMA_VERSION = "1.4"
MACHINE_DISPOSITIONS = {"filtered", "candidate", "duplicate", "covered", "recommended"}
HUMAN_DECISIONS = {"pending", "accepted", "partially_accepted", "rejected", "observe"}
OUTCOMES = {"pending", "verified", "failed", "inconclusive"}
PRIVACY_STATUSES = {"not_required", "pending", "passed", "quarantined"}
SAFE_ID = re.compile(r"^prp-[0-9a-f]{16}$")
SAFE_EVENT_ID = re.compile(r"^evt-[0-9a-f]{16}$")


class ProposalStoreCorruptionError(ValueError):
    """Raised when durable proposal state cannot be interpreted safely."""


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def normalize_change_points(items: Iterable[str]) -> list[str]:
    normalized: set[str] = set()
    for item in items:
        value = re.sub(r"\s+", " ", str(item)).strip().lower()
        if value:
            normalized.add(value)
    return sorted(normalized)


def proposal_fingerprint(target_skill: str, proposal_type: str, change_points: Iterable[str]) -> str:
    payload = {
        "target_skill": target_skill.strip().lower(),
        "proposal_type": proposal_type.strip().lower(),
        "change_points": normalize_change_points(change_points),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def proposal_id(fingerprint: str) -> str:
    return "prp-" + fingerprint[:16]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def revision_hash(
    *,
    target_version: str,
    change_points: Iterable[str],
    evidence_ids: Iterable[str],
    artifact_paths: Iterable[str],
    artifact_content_sha256: str,
    target_content_sha256: str = "",
    target_resolution: str = "unknown",
) -> str:
    payload = {
        "target_version": target_version,
        "change_points": normalize_change_points(change_points),
        "evidence_ids": sorted(set(evidence_ids)),
        "artifact_paths": normalize_artifact_paths(artifact_paths),
        "artifact_content_sha256": artifact_content_sha256,
        "target_content_sha256": target_content_sha256,
        "target_resolution": target_resolution,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_artifact_paths(paths: Iterable[str]) -> list[str]:
    output: set[str] = set()
    for raw in paths:
        value = str(raw).strip().replace("\\", "/")
        path = Path(value)
        if not value:
            continue
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("artifact paths must be logical relative paths")
        output.add(value)
    return sorted(output)


def normalize_source_session_ids(items: Iterable[str]) -> list[str]:
    """Persist only stable hashes, never raw provider session identifiers."""
    output: set[str] = set()
    for raw in items:
        value = str(raw).strip()
        if not value:
            continue
        if re.fullmatch(r"[0-9a-f]{16}", value):
            output.add(value)
        else:
            output.add(hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:16])
    return sorted(output)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary).replace(path)
    finally:
        try:
            Path(temporary).unlink()
        except FileNotFoundError:
            pass


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _read_regular_nofollow(root: Path, relative: Path, *, label: str) -> bytes:
    """Read a confined regular file through directory descriptors."""
    return read_confined_regular(root, relative, label=label)


class ProposalStore:
    def __init__(
        self,
        root: Path = PROPOSALS_ROOT,
        *,
        review_inbox_root: Path = REVIEW_INBOX_ROOT,
        review_archive_root: Path = REVIEW_ARCHIVE_ROOT,
    ) -> None:
        self.root = root.expanduser()
        self.review_inbox_root = review_inbox_root.expanduser()
        self.review_archive_root = review_archive_root.expanduser()
        self.artifact_snapshot_root = self.review_archive_root / "proposal-artifacts"
        self.machine_dir = self.root / "machine"
        self.events_dir = self.root / "events"
        self.audit_path = self.root / "audit.jsonl"
        self.lock_path = self.root / ".proposal-store.lock"

    @contextmanager
    def _exclusive(self) -> Any:
        self.root.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as handle:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _check_id(self, item_id: str) -> None:
        if not SAFE_ID.fullmatch(item_id):
            raise ValueError("invalid proposal_id")

    def _machine_path(self, item_id: str) -> Path:
        self._check_id(item_id)
        return self.machine_dir / f"{item_id}.json"

    def _events_path(self, item_id: str) -> Path:
        self._check_id(item_id)
        return self.events_dir / f"{item_id}.jsonl"

    def _verify_current_artifact(self, machine: dict[str, Any]) -> tuple[str, bytes]:
        """Read one current Inbox artifact without following symlinks."""
        paths = normalize_artifact_paths(machine.get("artifact_paths", []))
        if len(paths) != 1:
            raise ValueError("proposal requires exactly one current Review Inbox artifact")
        logical = Path(paths[0])
        if logical.parts[:2] != ("review", "inbox") or len(logical.parts) < 3:
            raise ValueError("proposal artifact must use a review/inbox logical path")

        relative = Path(*logical.parts[2:])
        content = _read_regular_nofollow(
            self.review_inbox_root,
            relative,
            label="Review Inbox artifact",
        )
        expected = str(machine.get("artifact_content_sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", expected) or hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("Review Inbox artifact content hash changed; refresh before deciding")
        return logical.as_posix(), content

    def _snapshot_artifact(
        self,
        item_id: str,
        revision: str,
        logical_path: str,
        content: bytes,
    ) -> str:
        """Publish verified bytes into a no-clobber, revision-bound archive."""
        self._check_id(item_id)
        if not re.fullmatch(r"[0-9a-f]{64}", revision):
            raise ValueError("invalid proposal revision")
        digest = hashlib.sha256(content).hexdigest()
        suffix = Path(logical_path).suffix
        if not re.fullmatch(r"\.[A-Za-z0-9]{1,10}", suffix):
            suffix = ".artifact"
        relative = Path("proposal-artifacts") / item_id / revision / f"{digest}{suffix}"
        try:
            publish_immutable_bytes(self.review_archive_root, relative, content)
        except ValueError as exc:
            raise ProposalStoreCorruptionError(
                "proposal artifact snapshot cannot be published safely"
            ) from exc
        return (Path("review") / "archive" / relative).as_posix()

    def _verify_decision_snapshot(self, current: dict[str, Any]) -> None:
        logical = Path(str(current.get("decision_artifact_snapshot", "")))
        if logical.parts[:2] != ("review", "archive") or len(logical.parts) < 3:
            raise ValueError(
                "accepted decision has no immutable artifact snapshot; create a new revision and review again"
            )
        content = _read_regular_nofollow(
            self.review_archive_root,
            Path(*logical.parts[2:]),
            label="proposal artifact snapshot",
        )
        expected = str(current.get("artifact_content_sha256", ""))
        if hashlib.sha256(content).hexdigest() != expected:
            raise ProposalStoreCorruptionError("proposal artifact snapshot content hash mismatch")

    def load_machine(self, item_id: str) -> dict[str, Any] | None:
        path = self._machine_path(item_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProposalStoreCorruptionError(
                f"corrupt machine record for {item_id}; repair before retrying"
            ) from exc
        if not isinstance(payload, dict):
            raise ProposalStoreCorruptionError(
                f"corrupt machine record for {item_id}; expected a JSON object"
            )
        return payload

    def events(self, item_id: str) -> list[dict[str, Any]]:
        path = self._events_path(item_id)
        if not path.exists():
            return []
        raw = path.read_text(encoding="utf-8")
        if not raw or not raw.endswith("\n"):
            raise ProposalStoreCorruptionError(
                f"corrupt event log for {item_id}; incomplete final event"
            )
        output: list[dict[str, Any]] = []
        seen_event_ids: set[str] = set()
        for line_number, line in enumerate(raw.splitlines(), start=1):
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ProposalStoreCorruptionError(
                    f"corrupt event log for {item_id} at line {line_number}"
                ) from exc
            if not isinstance(item, dict):
                raise ProposalStoreCorruptionError(
                    f"corrupt event log for {item_id} at line {line_number}; expected a JSON object"
                )
            event_id = str(item.get("event_id", ""))
            if not SAFE_EVENT_ID.fullmatch(event_id) or event_id in seen_event_ids:
                raise ProposalStoreCorruptionError(
                    f"corrupt event log for {item_id} at line {line_number}; invalid or duplicate event_id"
                )
            if item.get("proposal_id") != item_id:
                raise ProposalStoreCorruptionError(
                    f"corrupt event log for {item_id} at line {line_number}; proposal_id mismatch"
                )
            seen_event_ids.add(event_id)
            output.append(item)
        return output

    def project(self, machine: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
        record = dict(machine)
        record_revision = str(record.get("revision_hash", ""))
        artifact_hash = str(record.get("artifact_content_sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", record_revision):
            raise ProposalStoreCorruptionError(
                f"machine record for {record.get('proposal_id', 'proposal')} has no valid revision hash"
            )
        if artifact_hash and not re.fullmatch(r"[0-9a-f]{64}", artifact_hash):
            raise ProposalStoreCorruptionError(
                f"machine record for {record.get('proposal_id', 'proposal')} has an invalid artifact hash"
            )
        record.update(
            {
                "human_decision": "pending",
                "decision_reason": "",
                "partial_items": [],
                "reviewer": "",
                "decision_event_id": "",
                "decision_artifact_path": "",
                "decision_artifact_snapshot": "",
                "applied_commit": "",
                "applied_at": "",
                "verified_at": "",
                "outcome": "pending",
                "outcome_reason": "",
                "decision_revision_hash": "",
                "previous_human_decision": "",
            }
        )
        active_event_kinds: set[str] = set()
        for event in events:
            kind = event.get("kind")
            if kind == "human_decision":
                event_revision = str(event.get("revision_hash", ""))
                if event_revision != record.get("revision_hash"):
                    # Legacy events without a revision remain visible as history but
                    # can never become the active decision for a mutable proposal.
                    if event.get("decision"):
                        record["previous_human_decision"] = event.get("decision", "")
                    continue
                if kind in active_event_kinds:
                    raise ProposalStoreCorruptionError(
                        f"conflicting human decisions for {record.get('proposal_id', 'proposal')} revision"
                    )
                if event.get("artifact_content_sha256") != record.get("artifact_content_sha256"):
                    raise ProposalStoreCorruptionError(
                        f"human decision artifact hash mismatch for {record.get('proposal_id', 'proposal')}"
                    )
                if event.get("decision") not in HUMAN_DECISIONS - {"pending"}:
                    raise ProposalStoreCorruptionError(
                        f"invalid human decision event for {record.get('proposal_id', 'proposal')}"
                    )
                event_artifact_path = str(event.get("artifact_path", ""))
                current_paths = normalize_artifact_paths(record.get("artifact_paths", []))
                if event_artifact_path and event_artifact_path not in current_paths:
                    raise ProposalStoreCorruptionError(
                        f"human decision artifact path mismatch for {record.get('proposal_id', 'proposal')}"
                    )
                event_snapshot = str(event.get("artifact_snapshot", ""))
                if event_snapshot:
                    snapshot_path = Path(event_snapshot)
                    if snapshot_path.parts[:3] != (
                        "review",
                        "archive",
                        "proposal-artifacts",
                    ) or ".." in snapshot_path.parts or len(snapshot_path.parts) != 6:
                        raise ProposalStoreCorruptionError(
                            f"invalid human decision artifact snapshot for {record.get('proposal_id', 'proposal')}"
                        )
                    snapshot_name = Path(snapshot_path.parts[5])
                    if (
                        snapshot_path.parts[3] != str(record.get("proposal_id", ""))
                        or snapshot_path.parts[4] != event_revision
                        or snapshot_name.stem != str(record.get("artifact_content_sha256", ""))
                    ):
                        raise ProposalStoreCorruptionError(
                            f"human decision artifact snapshot binding mismatch for {record.get('proposal_id', 'proposal')}"
                        )
                    if event_artifact_path not in current_paths or len(current_paths) != 1:
                        raise ProposalStoreCorruptionError(
                            f"human decision artifact path binding mismatch for {record.get('proposal_id', 'proposal')}"
                        )
                active_event_kinds.add(kind)
                record.update(
                    {
                        "human_decision": event.get("decision", "pending"),
                        "decision_reason": event.get("reason", ""),
                        "partial_items": event.get("partial_items", []),
                        "reviewer": event.get("actor", ""),
                        "decision_event_id": event.get("event_id", ""),
                        "decision_revision_hash": event_revision,
                        "decision_artifact_path": event_artifact_path,
                        "decision_artifact_snapshot": event_snapshot,
                    }
                )
            elif kind == "applied":
                if str(event.get("revision_hash", "")) != record.get("revision_hash"):
                    continue
                if kind in active_event_kinds:
                    raise ProposalStoreCorruptionError(
                        f"conflicting applied events for {record.get('proposal_id', 'proposal')} revision"
                    )
                if record.get("human_decision") not in {"accepted", "partially_accepted"}:
                    raise ProposalStoreCorruptionError(
                        f"applied event has no accepted decision for {record.get('proposal_id', 'proposal')}"
                    )
                if not re.fullmatch(r"[0-9a-fA-F]{7,64}", str(event.get("commit", ""))):
                    raise ProposalStoreCorruptionError(
                        f"applied event has invalid commit for {record.get('proposal_id', 'proposal')}"
                    )
                if (
                    "artifact_content_sha256" in event
                    and event.get("artifact_content_sha256") != record.get("artifact_content_sha256")
                ):
                    raise ProposalStoreCorruptionError(
                        f"applied event artifact hash mismatch for {record.get('proposal_id', 'proposal')}"
                    )
                if (
                    "artifact_snapshot" in event
                    and event.get("artifact_snapshot") != record.get("decision_artifact_snapshot")
                ):
                    raise ProposalStoreCorruptionError(
                        f"applied event artifact snapshot mismatch for {record.get('proposal_id', 'proposal')}"
                    )
                active_event_kinds.add(kind)
                record.update(
                    {"applied_commit": event.get("commit", ""), "applied_at": event.get("timestamp", "")}
                )
            elif kind == "verified":
                if str(event.get("revision_hash", "")) != record.get("revision_hash"):
                    continue
                if kind in active_event_kinds:
                    raise ProposalStoreCorruptionError(
                        f"conflicting verified events for {record.get('proposal_id', 'proposal')} revision"
                    )
                if "applied" not in active_event_kinds:
                    raise ProposalStoreCorruptionError(
                        f"verified event has no applied event for {record.get('proposal_id', 'proposal')}"
                    )
                if event.get("applied_commit") != record.get("applied_commit"):
                    raise ProposalStoreCorruptionError(
                        f"verified event commit mismatch for {record.get('proposal_id', 'proposal')}"
                    )
                if event.get("outcome") not in OUTCOMES - {"pending"}:
                    raise ProposalStoreCorruptionError(
                        f"invalid verified outcome for {record.get('proposal_id', 'proposal')}"
                    )
                active_event_kinds.add(kind)
                record.update(
                    {
                        "outcome": event.get("outcome", "pending"),
                        "outcome_reason": event.get("reason", ""),
                        "verified_at": event.get("timestamp", ""),
                    }
                )
            else:
                raise ProposalStoreCorruptionError(
                    f"unknown event kind for {record.get('proposal_id', 'proposal')}"
                )
        record["events_count"] = len(events)
        return record

    def load(self, item_id: str) -> dict[str, Any] | None:
        machine = self.load_machine(item_id)
        return self.project(machine, self.events(item_id)) if machine else None

    def list(self) -> list[dict[str, Any]]:
        if not self.machine_dir.exists():
            return []
        output = []
        for path in sorted(self.machine_dir.glob("prp-*.json")):
            item_id = path.stem
            record = self.load(item_id)
            if record:
                output.append(record)
        return sorted(output, key=lambda item: str(item.get("updated_at", "")), reverse=True)

    def _audit(self, item_id: str, action: str, actor: str, fields: dict[str, Any]) -> None:
        safe_fields = {
            key: value
            for key, value in fields.items()
            if key
            in {
                "event_id",
                "kind",
                "decision",
                "outcome",
                "commit",
                "machine_disposition",
                "privacy_status",
                "artifact_content_sha256",
                "artifact_path",
                "artifact_snapshot",
                "revision_hash",
            }
        }
        _append_jsonl(
            self.audit_path,
            {"timestamp": now(), "proposal_id": item_id, "action": action, "actor": actor, **safe_fields},
        )

    def upsert(
        self,
        *,
        target_skill: str,
        target_version: str,
        proposal_type: str,
        change_points: Iterable[str],
        summary: str,
        machine_disposition: str,
        source_session_ids: Iterable[str] = (),
        evidence_ids: Iterable[str] = (),
        artifact_paths: Iterable[str] = (),
        privacy_status: str = "pending",
        artifact_content_sha256: str = "",
        target_content_sha256: str = "",
        target_resolution: str = "unknown",
        actor: str = "self-evolve",
    ) -> tuple[dict[str, Any], bool]:
        if machine_disposition not in MACHINE_DISPOSITIONS:
            raise ValueError("invalid machine_disposition")
        if privacy_status not in PRIVACY_STATUSES:
            raise ValueError("invalid privacy_status")
        if privacy_status == "passed" and not re.fullmatch(r"[0-9a-f]{64}", artifact_content_sha256):
            raise ValueError("passed privacy status requires artifact content hash")
        if target_content_sha256 and not re.fullmatch(r"[0-9a-f]{64}", target_content_sha256):
            raise ValueError("target content hash must be sha256")
        if target_resolution not in {"resolved", "missing", "ambiguous", "unknown"}:
            raise ValueError("invalid target_resolution")

        target_skill = sanitize_structured_text(target_skill).strip()
        target_version = sanitize_structured_text(target_version).strip()
        proposal_type = sanitize_structured_text(proposal_type).strip()
        summary = sanitize_structured_text(summary)
        points = normalize_change_points(sanitize_structured_text(item) for item in change_points)
        artifact_list = normalize_artifact_paths(artifact_paths)
        safe_source_ids = normalize_source_session_ids(source_session_ids)
        fingerprint = proposal_fingerprint(target_skill, proposal_type, points)
        item_id = proposal_id(fingerprint)
        with self._exclusive():
            previous = self.load_machine(item_id)
            existing_events = self.events(item_id)
            if previous is None and existing_events:
                raise ProposalStoreCorruptionError(
                    f"orphan event log for {item_id}; repair before retrying"
                )
            created = previous is None
            timestamp = now()
            combined_evidence = sorted(set((previous or {}).get("evidence_ids", [])) | set(evidence_ids))
            current_revision = revision_hash(
                target_version=target_version,
                change_points=points,
                evidence_ids=combined_evidence,
                artifact_paths=artifact_list,
                artifact_content_sha256=artifact_content_sha256,
                target_content_sha256=target_content_sha256,
                target_resolution=target_resolution,
            )
            effective_disposition = machine_disposition
            if previous and previous.get("revision_hash") == current_revision:
                projected = self.project(previous, existing_events)
                human = projected.get("human_decision")
                if projected.get("outcome") == "verified":
                    effective_disposition = "covered"
                elif human in {"rejected", "accepted", "partially_accepted"}:
                    effective_disposition = "duplicate"
                elif human == "observe":
                    effective_disposition = "candidate"

            machine = dict(previous or {})
            machine.update(
                {
                "schema_version": SCHEMA_VERSION,
                "proposal_id": item_id,
                "proposal_fingerprint": fingerprint,
                "target_skill": target_skill,
                "target_version": target_version,
                "proposal_type": proposal_type,
                "change_points": points,
                "summary": summary,
                "source_session_ids": sorted(set(machine.get("source_session_ids", [])) | set(safe_source_ids)),
                "evidence_ids": combined_evidence,
                # Bind only the current revision. Historical paths remain in
                # append-only lifecycle events rather than accumulating
                # into an ambiguous acceptance target.
                "artifact_paths": artifact_list,
                "machine_disposition": effective_disposition,
                "privacy_status": privacy_status,
                "artifact_content_sha256": artifact_content_sha256,
                "target_content_sha256": target_content_sha256,
                "target_resolution": target_resolution,
                "revision_hash": current_revision,
                "supersedes": machine.get("supersedes", []),
                "superseded_by": machine.get("superseded_by", ""),
                "created_at": machine.get("created_at", timestamp),
                "updated_at": timestamp,
                }
            )
            _atomic_json(self._machine_path(item_id), machine)
            self._audit(
                item_id,
                "machine_created" if created else "machine_updated",
                actor,
                {
                    "machine_disposition": effective_disposition,
                    "privacy_status": privacy_status,
                    "artifact_content_sha256": artifact_content_sha256,
                },
            )
            return self.project(machine, existing_events), created

    def _append_event_unlocked(self, item_id: str, event: dict[str, Any]) -> dict[str, Any]:
        if self.load_machine(item_id) is None:
            raise KeyError(item_id)
        # Never append past a torn/corrupt line: doing so could hide an earlier
        # terminal event and make a retry look like the first decision.
        self.events(item_id)
        event = {
            "event_id": "evt-" + uuid.uuid4().hex[:16],
            "proposal_id": item_id,
            "timestamp": now(),
            **event,
        }
        _append_jsonl(self._events_path(item_id), event)
        self._audit(item_id, str(event["kind"]), str(event.get("actor", "")), event)
        projected = self.load(item_id)
        if projected is None:
            raise KeyError(item_id)
        return projected

    def _append_event(self, item_id: str, event: dict[str, Any]) -> dict[str, Any]:
        with self._exclusive():
            return self._append_event_unlocked(item_id, event)

    def decide(
        self,
        item_id: str,
        *,
        decision: str,
        reason: str,
        reviewer: str,
        partial_items: Iterable[str] = (),
        expected_revision_hash: str,
        expected_artifact_sha256: str,
    ) -> dict[str, Any]:
        if decision not in HUMAN_DECISIONS - {"pending"}:
            raise ValueError("invalid human_decision")
        reviewer = reviewer.strip()
        if not reviewer or reviewer.lower() in {"machine", "headless", "self-evolve"}:
            raise ValueError("reviewer must identify an authorized human interaction")
        items = [str(item).strip() for item in partial_items if str(item).strip()]
        if decision == "partially_accepted" and not items:
            raise ValueError("partial_items are required")
        if decision in {"rejected", "partially_accepted"} and not reason.strip():
            raise ValueError("decision reason is required")
        with self._exclusive():
            machine = self.load_machine(item_id)
            if machine is None:
                raise KeyError(item_id)
            current = self.project(machine, self.events(item_id))
            current_revision = str(machine.get("revision_hash", ""))
            artifact_hash = str(machine.get("artifact_content_sha256", ""))
            if expected_revision_hash != current_revision:
                raise ValueError("proposal revision changed; refresh before deciding")
            if expected_artifact_sha256 != artifact_hash:
                raise ValueError("artifact hash changed; refresh before deciding")
            if current.get("human_decision") != "pending":
                same = (
                    current.get("human_decision") == decision
                    and current.get("decision_reason", "") == reason.strip()
                    and current.get("partial_items", []) == items
                )
                if same:
                    if decision in {"accepted", "partially_accepted"}:
                        self._verify_decision_snapshot(current)
                    return current
                raise ValueError("human decision is already terminal")
            if decision in {"accepted", "partially_accepted"}:
                if current.get("target_resolution") != "resolved":
                    raise ValueError("acceptance requires a uniquely resolved inventory target")
                if not re.fullmatch(r"[0-9a-f]{64}", str(current.get("target_content_sha256", ""))):
                    raise ValueError("acceptance requires a resolved target content hash")
                if current.get("privacy_status") != "passed" or not artifact_hash:
                    raise ValueError("acceptance requires a privacy-passed artifact hash")
                artifact_path, artifact_content = self._verify_current_artifact(machine)
                artifact_snapshot = self._snapshot_artifact(
                    item_id,
                    current_revision,
                    artifact_path,
                    artifact_content,
                )
            else:
                artifact_paths = normalize_artifact_paths(machine.get("artifact_paths", []))
                artifact_path = artifact_paths[0] if len(artifact_paths) == 1 else ""
                artifact_snapshot = ""
            return self._append_event_unlocked(
                item_id,
                {
                "kind": "human_decision",
                "actor": reviewer,
                "decision": decision,
                "reason": reason.strip(),
                "partial_items": items,
                "revision_hash": current.get("revision_hash", ""),
                "artifact_content_sha256": current.get("artifact_content_sha256", ""),
                "artifact_path": artifact_path,
                "artifact_snapshot": artifact_snapshot,
                },
            )

    def mark_applied(
        self,
        item_id: str,
        *,
        commit: str,
        actor: str,
        expected_revision_hash: str,
    ) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9a-fA-F]{7,64}", commit.strip()):
            raise ValueError("applied commit must be a git object id")
        if not actor.strip():
            raise ValueError("actor is required")
        with self._exclusive():
            machine = self.load_machine(item_id)
            if machine is None:
                raise KeyError(item_id)
            current = self.project(machine, self.events(item_id))
            if expected_revision_hash != machine.get("revision_hash"):
                raise ValueError("proposal revision changed; refresh before marking applied")
            if current.get("human_decision") not in {"accepted", "partially_accepted"}:
                raise ValueError("only accepted proposals can be marked applied")
            if current.get("target_resolution") != "resolved":
                raise ValueError("application requires a uniquely resolved inventory target")
            if not re.fullmatch(r"[0-9a-f]{64}", str(current.get("target_content_sha256", ""))):
                raise ValueError("application requires a resolved target content hash")
            self._verify_decision_snapshot(current)
            if current.get("applied_commit"):
                raise ValueError("proposal is already marked applied")
            return self._append_event_unlocked(
                item_id,
                {
                    "kind": "applied",
                    "actor": actor.strip(),
                    "commit": commit.strip(),
                    "revision_hash": current.get("revision_hash", ""),
                    "artifact_content_sha256": current.get("artifact_content_sha256", ""),
                    "artifact_path": current.get("decision_artifact_path", ""),
                    "artifact_snapshot": current.get("decision_artifact_snapshot", ""),
                },
            )

    def verify(
        self,
        item_id: str,
        *,
        outcome: str,
        reason: str,
        actor: str,
        expected_revision_hash: str,
        expected_applied_commit: str,
    ) -> dict[str, Any]:
        if outcome not in OUTCOMES - {"pending"}:
            raise ValueError("invalid outcome")
        if outcome == "failed" and not reason.strip():
            raise ValueError("failure reason is required")
        if not actor.strip():
            raise ValueError("actor is required")
        with self._exclusive():
            machine = self.load_machine(item_id)
            if machine is None:
                raise KeyError(item_id)
            current = self.project(machine, self.events(item_id))
            if expected_revision_hash != machine.get("revision_hash"):
                raise ValueError("proposal revision changed; refresh before verifying")
            if not current.get("applied_commit"):
                raise ValueError("verification requires an applied commit")
            if expected_applied_commit != current.get("applied_commit"):
                raise ValueError("applied commit changed; refresh before verifying")
            if current.get("outcome") != "pending":
                raise ValueError("verification outcome is already terminal")
            return self._append_event_unlocked(
                item_id,
                {
                    "kind": "verified",
                    "actor": actor.strip(),
                    "outcome": outcome,
                    "reason": reason.strip(),
                    "revision_hash": current.get("revision_hash", ""),
                    "applied_commit": current.get("applied_commit", ""),
                },
            )

    def metrics(self) -> dict[str, Any]:
        records = self.list()
        counts = lambda values, key: {value: sum(1 for item in records if item.get(key) == value) for value in values}
        human = counts(HUMAN_DECISIONS, "human_decision")
        decided = len(records) - human.get("pending", 0)
        accepted = human.get("accepted", 0) + human.get("partially_accepted", 0)
        return {
            "total": len(records),
            "machine_disposition": counts(MACHINE_DISPOSITIONS, "machine_disposition"),
            "human_decision": human,
            "outcome": counts(OUTCOMES, "outcome"),
            "human_acceptance_rate": round(accepted / decided, 4) if decided else None,
            "applied": sum(1 for item in records if item.get("applied_commit")),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage Self Evolve proposals.")
    parser.add_argument("--root", type=Path, default=PROPOSALS_ROOT)
    parser.add_argument("--review-inbox-root", type=Path, default=REVIEW_INBOX_ROOT)
    parser.add_argument("--review-archive-root", type=Path, default=REVIEW_ARCHIVE_ROOT)
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    sub.add_parser("metrics")

    decide = sub.add_parser("decide")
    decide.add_argument("proposal_id")
    decide.add_argument("--decision", required=True, choices=sorted(HUMAN_DECISIONS - {"pending"}))
    decide.add_argument("--reason", default="")
    decide.add_argument("--reviewer", required=True)
    decide.add_argument("--partial-item", action="append", default=[])
    decide.add_argument("--revision-hash", required=True)
    decide.add_argument("--artifact-sha256", required=True)

    applied = sub.add_parser("applied")
    applied.add_argument("proposal_id")
    applied.add_argument("--commit", required=True)
    applied.add_argument("--actor", required=True)
    applied.add_argument("--revision-hash", required=True)

    verify = sub.add_parser("verify")
    verify.add_argument("proposal_id")
    verify.add_argument("--outcome", required=True, choices=sorted(OUTCOMES - {"pending"}))
    verify.add_argument("--reason", default="")
    verify.add_argument("--actor", required=True)
    verify.add_argument("--revision-hash", required=True)
    verify.add_argument("--applied-commit", required=True)

    args = parser.parse_args()
    if args.command in {"decide", "applied", "verify"}:
        try:
            assert_runtime_ready()
            args.root = assert_external_write_path(args.root, label="proposal_root")
            args.review_inbox_root = assert_external_write_path(
                args.review_inbox_root,
                label="review_inbox_root",
            )
            args.review_archive_root = assert_external_write_path(
                args.review_archive_root,
                label="review_archive_root",
            )
        except ValueError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
            return 2
    store = ProposalStore(
        args.root,
        review_inbox_root=args.review_inbox_root,
        review_archive_root=args.review_archive_root,
    )
    try:
        if args.command == "list":
            payload: Any = store.list()
        elif args.command == "metrics":
            payload = store.metrics()
        elif args.command == "decide":
            payload = store.decide(
                args.proposal_id,
                decision=args.decision,
                reason=args.reason,
                reviewer=args.reviewer,
                partial_items=args.partial_item,
                expected_revision_hash=args.revision_hash,
                expected_artifact_sha256=args.artifact_sha256,
            )
        elif args.command == "applied":
            payload = store.mark_applied(
                args.proposal_id,
                commit=args.commit,
                actor=args.actor,
                expected_revision_hash=args.revision_hash,
            )
        else:
            payload = store.verify(
                args.proposal_id,
                outcome=args.outcome,
                reason=args.reason,
                actor=args.actor,
                expected_revision_hash=args.revision_hash,
                expected_applied_commit=args.applied_commit,
            )
    except (ValueError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
