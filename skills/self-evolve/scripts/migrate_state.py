#!/usr/bin/env python3
"""Preview or copy legacy in-tree Self Evolve state to the external data root."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from self_evolve_paths import (
    LEGACY_REVIEW_ROOT,
    LEGACY_RUNTIME_ROOT,
    LAYOUT_PATH,
    MIGRATION_MARKER_PATH,
    MIGRATIONS_ROOT,
    PANEL_ROOT,
    REVIEW_ARCHIVE_ROOT,
    RUNTIME_ROOT,
    claim_state_roots,
    is_ignored_state_file,
    state_layout,
    writable_layout_errors,
)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_directory(path: Path) -> None:
    """Persist directory entries before publishing a migration marker."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _mkdir_durable(path: Path) -> None:
    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    for directory in reversed(missing):
        _fsync_directory(directory.parent)


def migration_pairs(legacy_root: Path | None = None) -> list[tuple[Path, Path, str]]:
    legacy_runtime_root = legacy_root / "runtime" if legacy_root else LEGACY_RUNTIME_ROOT
    legacy_review_root = legacy_root / "review" if legacy_root else LEGACY_REVIEW_ROOT
    return [
        (legacy_runtime_root / "panel", PANEL_ROOT, "panel"),
        (legacy_runtime_root, RUNTIME_ROOT, "runtime"),
        (
            legacy_review_root / "output",
            REVIEW_ARCHIVE_ROOT / "legacy-output",
            "review_legacy_output",
        ),
        (legacy_review_root / "archive", REVIEW_ARCHIVE_ROOT, "review_archive"),
        (
            legacy_review_root / "review-log.md",
            REVIEW_ARCHIVE_ROOT / "legacy-review-log.md",
            "review_log",
        ),
    ]


def is_source_placeholder(path: Path, legacy_review_root: Path) -> bool:
    return path == legacy_review_root / "archive" / "README.md"


def build_plan(legacy_root: Path | None = None) -> dict[str, Any]:
    resolved_legacy_root = legacy_root.expanduser().resolve() if legacy_root else None
    legacy_review_root = (
        resolved_legacy_root / "review" if resolved_legacy_root else LEGACY_REVIEW_ROOT
    )
    operations: list[dict[str, Any]] = []
    for source, destination, category in migration_pairs(resolved_legacy_root):
        if source.is_file():
            candidates = [(source, destination)]
        elif source.is_dir():
            candidates = [
                (item, destination / item.relative_to(source))
                for item in source.rglob("*")
                if item.is_file()
                and not is_ignored_state_file(item)
                and not is_source_placeholder(item, legacy_review_root)
                and not (
                    category == "runtime"
                    and item.relative_to(source).parts
                    and item.relative_to(source).parts[0] == "panel"
                )
            ]
        else:
            candidates = []

        for source_file, destination_file in candidates:
            status = "copy"
            if destination_file.exists():
                try:
                    status = "same" if file_hash(source_file) == file_hash(destination_file) else "conflict"
                except OSError:
                    status = "error"
            try:
                source_sha256 = file_hash(source_file)
            except OSError:
                source_sha256 = ""
                status = "error"
            destination_sha256 = ""
            if destination_file.exists():
                try:
                    destination_sha256 = file_hash(destination_file)
                except OSError:
                    status = "error"
            try:
                byte_count = source_file.stat().st_size
            except OSError:
                byte_count = 0
                status = "error"
            operations.append(
                {
                    "category": category,
                    "source": str(source_file),
                    "destination": str(destination_file),
                    "bytes": byte_count,
                    "source_sha256": source_sha256,
                    "destination_sha256": destination_sha256,
                    "status": status,
                }
            )
    plan = {
        "schema_version": "1.0",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "layout": state_layout(),
        "operations": operations,
        "summary": {
            status: sum(1 for item in operations if item["status"] == status)
            for status in ("copy", "same", "conflict", "error")
        },
    }
    if resolved_legacy_root:
        plan["legacy_source_root"] = str(resolved_legacy_root)
    return plan


def apply_plan(plan: dict[str, Any]) -> dict[str, Any]:
    copied = 0
    for operation in plan.get("operations", []):
        if operation.get("status") != "copy":
            continue
        source = Path(str(operation["source"]))
        destination = Path(str(operation["destination"]))
        destination_created = False
        try:
            if file_hash(source) != operation.get("source_sha256"):
                operation["status"] = "error"
                operation["error"] = "source changed after preview"
                continue
            _mkdir_durable(destination.parent)
            descriptor = os.open(
                destination,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
            destination_created = True
            with os.fdopen(descriptor, "wb") as destination_handle, source.open("rb") as source_handle:
                shutil.copyfileobj(source_handle, destination_handle, length=1024 * 1024)
                destination_handle.flush()
                os.fsync(destination_handle.fileno())
            os.chmod(destination, 0o600)
            _fsync_directory(destination.parent)
        except FileExistsError:
            operation["status"] = "conflict"
            operation["error"] = "destination appeared after preview"
            continue
        except OSError as exc:
            if destination_created:
                destination.unlink(missing_ok=True)
                _fsync_directory(destination.parent)
            operation["status"] = "error"
            operation["error"] = f"copy failed: {type(exc).__name__}"
            continue
        try:
            source_verified = file_hash(source) == operation.get("source_sha256")
            destination_verified = file_hash(destination) == operation.get("source_sha256")
        except OSError:
            source_verified = False
            destination_verified = False
        if not source_verified or not destination_verified:
            destination.unlink(missing_ok=True)
            _fsync_directory(destination.parent)
            operation["status"] = "error"
            operation["error"] = "copy verification failed"
            continue
        operation["status"] = "copied"
        operation["destination_sha256"] = operation.get("source_sha256", "")
        copied += 1
    plan["applied_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    plan["copied"] = copied
    statuses = {"copied", "same", "conflict", "error"}
    plan["summary"] = {
        status: sum(1 for item in plan.get("operations", []) if item.get("status") == status)
        for status in statuses
    }
    return plan


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    _mkdir_durable(path.parent)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary).replace(path)
        os.chmod(path, 0o600)
        _fsync_directory(path.parent)
    finally:
        try:
            Path(temporary).unlink()
        except FileNotFoundError:
            pass


def write_manifest(plan: dict[str, Any]) -> Path:
    _mkdir_durable(MIGRATIONS_ROOT)
    os.chmod(MIGRATIONS_ROOT, 0o700)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = MIGRATIONS_ROOT / f"legacy-state-{stamp}-{os.getpid()}-{time.time_ns()}.json"
    atomic_json(path, plan)
    return path


def write_completion_markers(plan: dict[str, Any], manifest: Path) -> bool:
    errors = [
        item
        for item in plan.get("operations", [])
        if item.get("status") in {"conflict", "error"}
    ]
    if errors:
        return False
    completed_at = time.strftime("%Y-%m-%d %H:%M:%S")
    atomic_json(
        LAYOUT_PATH,
        {
            "schema_version": "2.0",
            "created_at": completed_at,
            "layout": state_layout(include_skill_root=False),
        },
    )
    atomic_json(
        MIGRATION_MARKER_PATH,
        {
            "schema_version": "1.1",
            "completed_at": completed_at,
            "manifest": manifest.name,
            "manifest_sha256": file_hash(manifest),
            "copied": plan.get("copied", 0),
            "source_files_preserved": True,
        },
    )
    return True


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="Migrate legacy Self Evolve state by copying files.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview only (default)")
    mode.add_argument("--apply", action="store_true", help="Copy non-conflicting files")
    parser.add_argument(
        "--legacy-root",
        type=Path,
        help="Old self-evolve Skill root (for migration after switching worktrees/versions)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    layout_errors = writable_layout_errors()
    if args.apply and layout_errors:
        payload = {"mode": "apply", "completed": False, "errors": layout_errors}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else json.dumps(payload, ensure_ascii=False))
        return 2
    legacy_root = args.legacy_root.expanduser().resolve() if args.legacy_root else None
    if legacy_root and not legacy_root.is_dir():
        payload = {
            "mode": "apply" if args.apply else "dry-run",
            "completed": False,
            "errors": [f"legacy root is not a directory: {legacy_root}"],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else json.dumps(payload, ensure_ascii=False))
        return 2
    if args.apply:
        try:
            claim_state_roots()
        except (OSError, ValueError) as exc:
            payload = {"mode": "apply", "completed": False, "errors": [str(exc)]}
            print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else json.dumps(payload, ensure_ascii=False))
            return 2
    plan = build_plan(legacy_root)
    if args.apply:
        plan = apply_plan(plan)
        manifest = write_manifest(plan)
        completed = write_completion_markers(plan, manifest)
        plan["manifest"] = str(manifest)
        plan["completed"] = completed
    plan["mode"] = "apply" if args.apply else "dry-run"
    print(json.dumps(plan, ensure_ascii=False, indent=2) if args.json else json.dumps(plan["summary"], ensure_ascii=False))
    return 2 if plan["summary"].get("conflict") or plan["summary"].get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
