"""Business delivery bindings, bounded file observations and review structure.

Source references are declarations. Reviewer records are attestations; neither
a digest nor this mechanical gate proves the business content is true.
"""
from __future__ import annotations

import codecs
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any

MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_ARTIFACTS = 32
MAX_SOURCES = 128
MAX_CRITERIA = 128
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
PLACEHOLDERS = {"", "tbd", "todo", "unknown", "n/a", "na", "-", "*", "**", "none"}
PURPOSES = {"research_report", "design_document", "legal_document", "business_report"}
MEDIA = {"text/plain": "text", "text/markdown": "text", "text/html": "text",
         "application/pdf": "binary", "image/png": "binary", "image/jpeg": "binary",
         "application/octet-stream": "binary"}
OFFICE = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
MEDIA.update({mime: "binary" for mime in OFFICE})


class ArtifactError(ValueError):
    pass


def missing(value: Any) -> bool:
    return (not isinstance(value, str) or value.strip().casefold() in PLACEHOLDERS
            or "\x00" in value or value.strip().startswith("{{"))


def digest_json(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def exact_path(value: Any) -> bool:
    if not isinstance(value, str) or missing(value) or value != value.strip():
        return False
    if any(ord(c) < 32 for c in value) or any(c in value for c in "\\*?[]"):
        return False
    path = PurePosixPath(value)
    return (not path.is_absolute() and str(path) == value
            and all(part not in {".", ".."} for part in value.split("/")))


def validate_task(task: dict[str, Any], prefix: str = "task") -> list[str]:
    errors: list[str] = []
    for field in ("task_id", "value_identity"):
        if missing(task.get(field)):
            errors.append(f"{prefix}.{field} is required for stable business identity")
    block = task.get("business_artifact")
    if not isinstance(block, dict):
        return [f"{prefix}.business_artifact must be an object"]
    if not isinstance(block.get("purpose_type"), str) or block["purpose_type"] not in PURPOSES:
        errors.append(f"{prefix}.business_artifact.purpose_type must name a business delivery, not maintenance")
    for field in ("purpose", "request_ref"):
        if missing(block.get(field)):
            errors.append(f"{prefix}.business_artifact.{field} is required")
    if task.get("engineering_assets") or task.get("doc_assets"):
        errors.append(f"{prefix}.business_artifact uses exact artifacts, not engineering_assets/doc_assets")
    if task.get("gate_target") is not None:
        errors.append(f"{prefix}.business_artifact must not impersonate a merge_gate")
    mode = block.get("acceptance_mode")
    if not isinstance(mode, str) or mode not in {"content_review", "verifier"}:
        errors.append(f"{prefix}.business_artifact.acceptance_mode must be content_review or verifier")
    commands = task.get("verification_commands")
    if not isinstance(commands, list):
        errors.append(f"{prefix}.verification_commands must be an explicit array")
    elif mode == "content_review" and commands:
        errors.append(f"{prefix}.content_review requires an empty verification_commands array")
    elif mode == "verifier" and not commands:
        errors.append(f"{prefix}.verifier requires existing verification_commands")
    if isinstance(commands, list):
        if any(missing(c) or c != c.strip() or "\n" in c or "\r" in c for c in commands):
            errors.append(f"{prefix}.verification_commands must be exact single-line commands")
        if all(isinstance(c, str) for c in commands) and len(set(commands)) != len(commands):
            errors.append(f"{prefix}.verification_commands must be unique")
    sources = block.get("sources")
    source_ids: set[str] = set()
    if not isinstance(sources, list) or not 1 <= len(sources) <= MAX_SOURCES:
        errors.append(f"{prefix}.sources must contain 1..{MAX_SOURCES} named source declarations")
        sources = []
    for entry in sources:
        if not isinstance(entry, dict):
            errors.append(f"{prefix}.source must be an object")
            continue
        identity = entry.get("source_id")
        if missing(identity) or not ID_RE.fullmatch(identity) or identity in source_ids:
            errors.append(f"{prefix}.source_id must be a unique canonical identifier")
        else:
            source_ids.add(identity)
        if missing(entry.get("reference")):
            errors.append(f"{prefix}.source reference is required")
    artifacts = block.get("artifacts")
    paths: set[str] = set()
    if not isinstance(artifacts, list) or not 1 <= len(artifacts) <= MAX_ARTIFACTS:
        errors.append(f"{prefix}.artifacts must contain 1..{MAX_ARTIFACTS} exact file paths")
        artifacts = []
    for entry in artifacts:
        if not isinstance(entry, dict):
            errors.append(f"{prefix}.artifact must be an object")
            continue
        path = entry.get("path")
        if not exact_path(path) or path in paths:
            errors.append(f"{prefix}.artifact path must be unique, canonical and relative without traversal")
        else:
            paths.add(path)
        if not isinstance(entry.get("media_type"), str) or entry["media_type"] not in MEDIA or entry.get("modality") != MEDIA[entry["media_type"]]:
            errors.append(f"{prefix}.artifact modality/media_type is unsupported or mismatched")
    criteria = block.get("acceptance_criteria")
    criterion_ids: set[str] = set()
    covered_paths: set[str] = set()
    covered_sources: set[str] = set()
    if not isinstance(criteria, list) or not 1 <= len(criteria) <= MAX_CRITERIA:
        errors.append(f"{prefix}.acceptance_criteria must contain 1..{MAX_CRITERIA} standards")
        criteria = []
    for entry in criteria:
        if not isinstance(entry, dict):
            errors.append(f"{prefix}.criterion must be an object")
            continue
        identity = entry.get("criterion_id")
        if missing(identity) or not ID_RE.fullmatch(identity) or identity in criterion_ids:
            errors.append(f"{prefix}.criterion_id must be a unique canonical identifier")
        else:
            criterion_ids.add(identity)
        if missing(entry.get("standard")):
            errors.append(f"{prefix}.criterion standard is required")
        for field, allowed, covered in (("artifact_paths", paths, covered_paths), ("source_ids", source_ids, covered_sources)):
            values = entry.get(field)
            if (not isinstance(values, list) or not values or any(not isinstance(v, str) for v in values)
                    or len(set(values)) != len(values) or not set(values).issubset(allowed)):
                errors.append(f"{prefix}.criterion {field} must bind unique declared entries")
            else:
                covered.update(values)
    if covered_paths != paths or covered_sources != source_ids:
        errors.append(f"{prefix}.criteria must cover every declared artifact and source")
    return errors


def _signature(entry: os.stat_result) -> tuple[int, ...]:
    return (entry.st_dev, entry.st_ino, entry.st_size, entry.st_mtime_ns, entry.st_ctime_ns)


def _canonical_root(root: Path) -> Path:
    if not root.is_absolute() or str(root) != str(root.resolve(strict=True)):
        raise ArtifactError("artifact root must be an existing canonical absolute directory")
    # resolve equality alone misses a final symlink to itself or aliased paths.
    for path in (root, *root.parents):
        if stat.S_ISLNK(path.lstat().st_mode):
            raise ArtifactError("artifact root must not contain symlink components")
    if not root.is_dir():
        raise ArtifactError("artifact root must be a directory")
    return root


def _observe(root: Path, artifact: dict[str, Any]) -> dict[str, Any]:
    path = root / artifact["path"]
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors: list[int] = []
    chain: list[tuple[Path, tuple[int, ...]]] = []
    try:
        descriptor = os.open(root, directory_flags)
        descriptors.append(descriptor)
        chain.append((root, _signature(os.fstat(descriptor))))
        parent = root
        parts = PurePosixPath(artifact["path"]).parts
        for part in parts[:-1]:
            descriptor = os.open(part, directory_flags, dir_fd=descriptor)
            descriptors.append(descriptor)
            parent = parent / part
            chain.append((parent, _signature(os.fstat(descriptor))))
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        descriptors.append(file_fd)
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_FILE_BYTES:
            raise ArtifactError("artifact must be a nonempty regular file within 64 MiB")
        digest = hashlib.sha256()
        total = 0
        prefix = b""
        decoder = codecs.getincrementaldecoder("utf-8")() if artifact["modality"] == "text" else None
        substantive = False
        while True:
            block = os.read(file_fd, 128 * 1024)
            if not block:
                break
            total += len(block)
            if total > MAX_FILE_BYTES:
                raise ArtifactError("artifact exceeded bounded read size")
            digest.update(block)
            prefix = (prefix + block[:16])[:16]
            if decoder is not None:
                text = decoder.decode(block)
                if "\x00" in text:
                    raise ArtifactError("text artifact contains binary NUL")
                substantive = substantive or bool(text.strip())
        if decoder is not None:
            substantive = substantive or bool(decoder.decode(b"", final=True).strip())
            if not substantive:
                raise ArtifactError("text artifact is empty or whitespace only")
        signatures = {"application/pdf": b"%PDF-", "image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff"}
        magic = signatures.get(artifact["media_type"])
        if magic is not None and not prefix.startswith(magic):
            raise ArtifactError("artifact bytes do not match declared media_type")
        if artifact["media_type"] in OFFICE and not prefix.startswith(b"PK\x03\x04"):
            raise ArtifactError("Office artifact must have a ZIP-based container signature")
        if total != before.st_size or _signature(os.fstat(file_fd)) != _signature(before):
            raise ArtifactError("artifact changed while reading")
        if _signature(path.lstat()) != _signature(before):
            raise ArtifactError("artifact path changed while reading")
        for directory, expected in chain:
            if _signature(directory.lstat()) != expected:
                raise ArtifactError("artifact directory changed while reading")
        return {**artifact, "sha256": digest.hexdigest(), "bytes": total}
    except (OSError, UnicodeError, RuntimeError) as exc:
        raise ArtifactError("artifact cannot be safely read or does not match declared modality") from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def observe_delivery(task: dict[str, Any], root: Path) -> dict[str, Any]:
    errors = validate_task(task)
    if errors:
        raise ArtifactError("; ".join(errors))
    try:
        root = _canonical_root(root)
        before = {artifact["path"]: _signature((root / artifact["path"]).lstat())
                  for artifact in task["business_artifact"]["artifacts"]}
        artifacts = [_observe(root, artifact) for artifact in task["business_artifact"]["artifacts"]]
        _canonical_root(root)
        if any(_signature((root / path).lstat()) != signature for path, signature in before.items()):
            raise ArtifactError("business artifacts changed during delivery observation")
    except (OSError, RuntimeError) as exc:
        raise ArtifactError("artifact root is unavailable or noncanonical") from exc
    body = {"task_id": task["task_id"], "value_identity": task["value_identity"], "artifact_root": str(root),
            "contract_sha256": digest_json(task),
            "sources_sha256": digest_json(task["business_artifact"]["sources"]), "artifacts": artifacts}
    return {**body, "identity": "artifact-sha256:" + digest_json(body)}


def validate_evidence(task: dict[str, Any], evidence: Any, observed: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(evidence, dict):
        return ["business evidence must be an object"]
    if digest_json(evidence.get("delivery")) != digest_json(observed):
        errors.append("business delivery manifest/identity does not match actual artifacts and source/contract bindings")
    implementation = evidence.get("implementation")
    review = evidence.get("content_review")
    if not isinstance(implementation, dict) or not isinstance(review, dict) or not isinstance(review.get("reviewer"), dict):
        return errors + ["business evidence requires implementation and independent content_review.reviewer"]
    reviewer = review["reviewer"]
    for field in ("dispatch_id", "session_id", "author_id"):
        if missing(implementation.get(field)) or missing(reviewer.get(field)):
            errors.append(f"business implementation/reviewer {field} must be named")
        elif " ".join(implementation[field].casefold().split()) == " ".join(reviewer[field].casefold().split()):
            errors.append(f"business self-review: distinct {field} required")
    if review.get("verdict") != "ACCEPT" or review.get("delivery_identity") != observed["identity"]:
        errors.append("business reviewer must ACCEPT the exact observed delivery identity")
    if review.get("sources_sha256") != observed["sources_sha256"]:
        errors.append("business reviewer source binding mismatch")
    wanted = task["business_artifact"]["acceptance_criteria"]
    records = review.get("criteria")
    if (not isinstance(records, list) or len(records) != len(wanted)
            or any(not isinstance(r, dict) for r in records)):
        errors.append("business review requires one evidence record per criterion")
    else:
        by_id = {r.get("criterion_id"): r for r in records if isinstance(r.get("criterion_id"), str)}
        if len(by_id) != len(records) or set(by_id) != {c["criterion_id"] for c in wanted}:
            errors.append("business review criterion identities are duplicate, missing or extra")
        for criterion in wanted:
            record = by_id.get(criterion["criterion_id"], {})
            if (record.get("verdict") != "PASS" or missing(record.get("evidence"))
                    or record.get("artifact_paths") != criterion["artifact_paths"]
                    or record.get("source_ids") != criterion["source_ids"]):
                errors.append("business review criterion must PASS with exact artifact/source IDs and concrete evidence")
    checks = review.get("source_checks")
    sources = task["business_artifact"]["sources"]
    if (not isinstance(checks, list) or len(checks) != len(sources)
            or any(not isinstance(r, dict) or missing(r.get("evidence")) or not isinstance(r.get("source_id"), str) for r in checks)
            or {r["source_id"] for r in checks} != {s["source_id"] for s in sources}):
        errors.append("business review requires exactly one named source check with evidence per source")
    commands = task["verification_commands"]
    executed = evidence.get("executed", [])
    if not isinstance(executed, list) or len(executed) != len(commands):
        errors.append("business executed verifiers must match declared commands exactly")
    else:
        recorded: set[str] = set()
        for entry in executed:
            if (not isinstance(entry, dict) or entry.get("command") not in commands
                    or entry.get("command") in recorded or type(entry.get("exit_code")) is not int or entry["exit_code"] != 0):
                errors.append("business verification command is missing, duplicate, extra or failed")
            elif isinstance(entry.get("command"), str):
                recorded.add(entry["command"])
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Read actual business artifacts and emit a draft manifest, never an acceptance verdict")
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--artifact-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.spec.is_symlink() or not args.spec.is_file():
            raise ArtifactError("spec must be a regular non-symlink file")
        with args.spec.open("rb") as stream:
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ArtifactError("spec exceeds 1 MiB")
        data = json.loads(raw)
        gate_spec = importlib.util.spec_from_file_location("business_dispatch_observation", Path(__file__).with_name("dispatch-value-gate.py"))
        gate = importlib.util.module_from_spec(gate_spec)
        gate_spec.loader.exec_module(gate)
        errors = gate.validate(data, datetime.now(timezone.utc))
        if errors:
            raise ArtifactError("; ".join(errors))
        selected = [task for task in data["tasks"] if task["task_id"] == args.task_id]
        if len(selected) != 1 or selected[0].get("value_kind") != "business_artifact":
            raise ArtifactError("task must uniquely select a business_artifact contract")
        delivery = observe_delivery(selected[0], args.artifact_root)
        print(json.dumps({"ok": True, "status": "observed_draft", "accepted": False, "delivery": delivery}, ensure_ascii=False))
        return 0
    except (ArtifactError, OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"ok": False, "status": "unverified", "accepted": False, "errors": [str(exc)]}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
