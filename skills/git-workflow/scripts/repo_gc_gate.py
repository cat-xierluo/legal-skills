#!/usr/bin/env python3
"""Fail-closed gate for repository GC after exact branch cleanup."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


OID = re.compile(r"[0-9a-f]{40}\Z")
RESOLVE_UNDO = re.compile(r"invalid sha1 pointer in resolve-undo of \S*\.git/worktrees/\S+/index")
BASE_ENV = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    audit = commands.add_parser("audit", help="write a read-only GC baseline")
    audit.add_argument("repository", type=Path)
    audit.add_argument("--output", type=Path, required=True)

    gc = commands.add_parser("gc", help="run GC after baseline and approval checks")
    gc.add_argument("repository", type=Path)
    gc.add_argument("--baseline", type=Path, required=True)
    gc.add_argument("--approval", type=Path, required=True)
    gc.add_argument("--receipt", type=Path, required=True)
    gc.add_argument("--max-age-seconds", type=int, default=24 * 60 * 60)

    verify = commands.add_parser("verify", help="verify a completed GC receipt")
    verify.add_argument("repository", type=Path)
    verify.add_argument("--baseline", type=Path, required=True)
    verify.add_argument("--receipt", type=Path, required=True)

    release = commands.add_parser("release", help="verify and release a multi-repo recovery directory")
    release.add_argument("recovery", type=Path)
    release.add_argument("--approval", type=Path, required=True)
    release.add_argument("--receipt", type=Path, required=True)
    return parser.parse_args()


def run(command, *, allowed=(0,), timeout=600, env=None):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=env or os.environ)
    if result.returncode not in allowed:
        message = (result.stderr + result.stdout).strip()
        raise RuntimeError(message or f"Command failed: {command}")
    return result


def git(root: Path, *args, allowed=(0,), timeout=600):
    return run(["git", "--no-optional-locks", "-C", str(root), *args], allowed=allowed, timeout=timeout, env=BASE_ENV)


def git_text(root: Path, *args, timeout=600):
    return git(root, *args, timeout=timeout).stdout.strip()


def digest(path: Path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def tree_size(path: Path):
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file() and not item.is_symlink():
                total += item.stat().st_blocks * 512
        except FileNotFoundError:
            continue
    return total


def write_json(path: Path, value):
    if path.exists():
        raise RuntimeError(f"Output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def repository_identity(root: Path):
    root = root.expanduser().resolve(strict=True)
    common = Path(git_text(root, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve(strict=True)
    head = git_text(root, "rev-parse", "HEAD")
    branch = git_text(root, "branch", "--show-current")
    if not OID.fullmatch(head):
        raise RuntimeError(f"Invalid HEAD: {head}")
    return root, common, head, branch


def refs_snapshot(root: Path):
    output = git_text(root, "for-each-ref", "--format=%(refname) %(objectname)")
    refs = []
    for line in output.splitlines():
        name, _, oid = line.partition(" ")
        if not name or not OID.fullmatch(oid):
            raise RuntimeError(f"Invalid ref snapshot line: {line}")
        refs.append({"ref": name, "oid": oid})
    return refs


def worktree_snapshot(root: Path):
    output = git(root, "worktree", "list", "--porcelain").stdout
    worktrees = []
    current = {}
    for line in output.splitlines() + [""]:
        if not line:
            if current:
                worktrees.append(dict(sorted(current.items())))
                current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value
    return worktrees


def count_objects(root: Path):
    result = git(root, "count-objects", "-v")
    values = {}
    for line in result.stdout.splitlines():
        key, _, value = line.partition(": ")
        if key and value:
            values[key] = value
    return values


def pack_files(common: Path):
    files = []
    for path in sorted((common / "objects" / "pack").glob("*")):
        if path.is_file():
            files.append({"name": path.name, "size": path.stat().st_size})
    return files


def classify_fsck(output: str):
    fatal = []
    index_warnings = []
    garbage = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if RESOLVE_UNDO.search(stripped):
            index_warnings.append(stripped)
        elif stripped.startswith(("missing ", "broken ", "error:", "fatal:", "bad object")):
            fatal.append(stripped)
        elif stripped.startswith(("bad sha1 file:", "garbage found:")):
            garbage.append(stripped)
    return {"fatal": fatal, "index_warnings": sorted(set(index_warnings)), "garbage": sorted(set(garbage))}


def fsck(root: Path):
    result = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(root), "fsck", "--no-progress", "--no-dangling"],
        capture_output=True, text=True, timeout=600, env=BASE_ENV,
    )
    classified = classify_fsck(result.stderr + "\n" + result.stdout)
    if result.returncode != 0 and classified["fatal"]:
        raise RuntimeError("fsck fatal findings: " + "\n".join(classified["fatal"][:10]))
    if result.returncode != 0:
        raise RuntimeError(f"fsck failed with exit {result.returncode}")
    return classified


def sync_and_temporary_files(common: Path):
    conflicts = []
    temporary_packs = []
    for path in common.rglob("*NSConflict*"):
        if path.is_file():
            conflicts.append({"path": str(path.relative_to(common)), "size": path.stat().st_size})
    for path in (common / "objects" / "pack").glob("tmp_*"):
        if path.is_file():
            temporary_packs.append({"path": str(path.relative_to(common)), "size": path.stat().st_size})
    return sorted(conflicts, key=lambda item: item["path"]), sorted(temporary_packs, key=lambda item: item["path"])


def lock_files(common: Path):
    locks = []
    for path in common.rglob("*.lock"):
        if path.is_file():
            locks.append(str(path.relative_to(common)))
    return sorted(locks)


def traverse_all_objects(root: Path):
    git(root, "rev-list", "--objects", "--all", timeout=900)


def make_baseline(root: Path):
    root, common, head, branch = repository_identity(root)
    classified = fsck(root)
    traverse_all_objects(root)
    conflicts, temporary_packs = sync_and_temporary_files(common)
    return {
        "schema_version": 1,
        "created_at": time.time(),
        "repository": {
            "root": str(root), "common": str(common), "head": head, "branch": branch,
        },
        "head": head,
        "branch": branch,
        "refs": refs_snapshot(root),
        "worktrees": worktree_snapshot(root),
        "count_objects": count_objects(root),
        "pack_files": pack_files(common),
        "git_size_bytes": tree_size(common),
        "fsck": classified,
        "sync_conflicts": conflicts,
        "temporary_packs": temporary_packs,
        "locks": lock_files(common),
    }


def current_identity_fields(root: Path, baseline):
    expected_root = Path(baseline["repository"]["root"])
    root, common, head, branch = repository_identity(root)
    if root != expected_root or str(common) != baseline["repository"]["common"]:
        raise RuntimeError("Repository or common Git directory changed")
    return {
        "head": head,
        "branch": branch,
        "refs": refs_snapshot(root),
        "worktrees": worktree_snapshot(root),
    }


def assert_unchanged(baseline, current):
    for field in ("head", "branch", "refs", "worktrees"):
        if baseline.get(field) != current.get(field):
            raise RuntimeError(f"Baseline drift: {field}")


def assert_gc_approval(approval: Path, baseline_path: Path, baseline):
    record = json.loads(approval.read_text())
    if record.get("action") != "git-gc":
        raise RuntimeError("Approval action is not git-gc")
    if record.get("baseline_sha256") != digest(baseline_path):
        raise RuntimeError("Approval is not bound to the baseline")
    if record.get("accepted_fsck_warnings") != baseline["fsck"]["index_warnings"]:
        raise RuntimeError("Approval does not exactly acknowledge index warnings")
    if not record.get("approved_by") or not record.get("authorization"):
        raise RuntimeError("Approval lacks approver or authorization")
    recovery_paths = record.get("cleanup_recovery_paths")
    if not isinstance(recovery_paths, list) or not recovery_paths:
        raise RuntimeError("GC approval does not bind a verified cleanup recovery")
    prepared_roots = set()
    for value in recovery_paths:
        recovery = Path(str(value)).expanduser().resolve(strict=True)
        prepared = verify_multi_repo_recovery(recovery)
        prepared_roots.update(prepared["repositories"])
    if baseline["repository"]["root"] not in prepared_roots:
        raise RuntimeError("Bound cleanup recoveries do not cover this repository")


def check_pre_gc(root: Path, baseline_path: Path, baseline, max_age_seconds):
    if baseline.get("schema_version") != 1:
        raise RuntimeError("Unsupported baseline schema")
    if time.time() - baseline["created_at"] > max_age_seconds:
        raise RuntimeError("Baseline is too old")
    current = current_identity_fields(root, baseline)
    assert_unchanged(baseline, current)
    if baseline["locks"] or lock_files(Path(baseline["repository"]["common"])):
        raise RuntimeError("Git lock files are present")
    classified = fsck(root)
    if classified["fatal"] or classified["index_warnings"] != baseline["fsck"]["index_warnings"]:
        raise RuntimeError("fsck result changed after baseline")
    traverse_all_objects(root)
    return current


def gc_receipt(root: Path, baseline_path: Path, baseline, current, before_bytes):
    common = Path(baseline["repository"]["common"])
    return {
        "schema_version": 1,
        "completed_at": time.time(),
        "repository": baseline["repository"],
        "baseline_path": str(baseline_path),
        "baseline_sha256": digest(baseline_path),
        "baseline_head": baseline["head"],
        "baseline_refs": baseline["refs"],
        "baseline_worktrees": baseline["worktrees"],
        "command": ["git", "gc", "--prune=now", "--quiet"],
        "pre_git_size_bytes": before_bytes,
        "post_git_size_bytes": tree_size(common),
        "git_freed_bytes": before_bytes - tree_size(common),
        "count_objects_before": baseline["count_objects"],
        "count_objects_after": count_objects(root),
        "pack_files_after": pack_files(common),
        "fsck_after": fsck(root),
        "identity_after": current,
    }


def verify_gc(root: Path, baseline_path: Path, receipt_path: Path):
    baseline = json.loads(baseline_path.read_text())
    receipt = json.loads(receipt_path.read_text())
    if baseline.get("schema_version") != 1 or receipt.get("schema_version") != 1:
        raise RuntimeError("Unsupported baseline or receipt schema")
    current = current_identity_fields(root, baseline)
    expected = {"head": receipt["baseline_head"], "branch": baseline["branch"], "refs": receipt["baseline_refs"], "worktrees": receipt["baseline_worktrees"]}
    assert_unchanged(expected, current)
    classified = fsck(root)
    if classified["fatal"]:
        raise RuntimeError("fsck fatal findings after GC")
    traverse_all_objects(root)
    return receipt


def verify_multi_repo_recovery(recovery: Path):
    prepared = json.loads((recovery / "prepared.json").read_text())
    result = json.loads((recovery / "result.json").read_text())
    operations = [json.loads(line) for line in (recovery / "operations.jsonl").read_text().splitlines()]
    manifest = json.loads((recovery / "manifest.json").read_text())
    if prepared.get("source_sha256") != digest(recovery / "manifest.json"):
        raise RuntimeError("Recovery manifest checksum changed")
    if prepared.get("source_sha256") != (recovery / "manifest.sha256").read_text().strip():
        raise RuntimeError("Recovery manifest checksum record changed")
    for record in prepared["repositories"].values():
        folder = recovery / record["folder"]
        for name, expected in record["backup_sha256"].items():
            if digest(folder / name) != expected:
                raise RuntimeError(f"Recovery checksum changed: {name}")
        index = folder / "unreachable-commits.idx"
        if index.exists():
            run(["git", "verify-pack", "-s", str(index)])
    if result.get("retained"):
        raise RuntimeError("Recovery still has retained cleanup objects")
    if operations != result.get("completed"):
        raise RuntimeError("Recovery operations and result differ")
    expected = {
        (record["root"], branch["branch"], branch["tip"])
        for record in prepared["repositories"].values() for branch in record["branches"]
    }
    actual = {(item["root"], item["branch"], item["tip"]) for item in operations}
    if actual != expected:
        raise RuntimeError("Recovery operations do not cover prepared branches")
    for operation in operations:
        root = Path(operation["root"])
        ref = f"refs/heads/{operation['branch']}"
        if git(root, "show-ref", "--verify", "--quiet", ref, allowed=(0, 1), timeout=60).returncode == 0:
            raise RuntimeError(f"Deleted branch still exists: {operation['branch']}")
    return prepared


def assert_release_approval(approval: Path, recovery: Path, prepared):
    record = json.loads(approval.read_text())
    if record.get("action") != "release-recovery":
        raise RuntimeError("Approval action is not release-recovery")
    if record.get("recovery_path") != str(recovery.resolve()):
        raise RuntimeError("Approval is not bound to the recovery path")
    if record.get("prepared_sha256") != digest(recovery / "prepared.json"):
        raise RuntimeError("Approval is not bound to prepared.json")
    receipts = record.get("gc_receipts")
    if not isinstance(receipts, dict) or not receipts:
        raise RuntimeError("Approval does not bind GC receipts")
    expected_roots = set(prepared["repositories"])
    if set(receipts) != expected_roots:
        raise RuntimeError("Approval GC receipts do not cover recovery repositories")
    for root, value in receipts.items():
        receipt_path = Path(str(value)).expanduser().resolve(strict=True)
        receipt = json.loads(receipt_path.read_text())
        if receipt.get("schema_version") != 1 or receipt.get("repository", {}).get("root") != root:
            raise RuntimeError(f"Invalid GC receipt for {root}")
        baseline_path = Path(str(receipt.get("baseline_path", ""))).expanduser()
        if not baseline_path.is_file() or receipt.get("baseline_sha256") != digest(baseline_path):
            raise RuntimeError(f"GC receipt baseline is invalid for {root}")
        if receipt.get("fsck_after", {}).get("fatal"):
            raise RuntimeError(f"GC receipt has fatal findings for {root}")
    if not record.get("approved_by") or not record.get("authorization"):
        raise RuntimeError("Approval lacks approver or authorization")


def audit_command(args):
    output = args.output.expanduser().resolve()
    repository = args.repository.expanduser().resolve(strict=True)
    if output.is_relative_to(repository):
        raise RuntimeError("GC baseline must be written outside the repository")
    baseline = make_baseline(args.repository)
    if baseline["fsck"]["fatal"]:
        raise RuntimeError("Baseline has fatal fsck findings")
    common = Path(baseline["repository"]["common"])
    protected = [repository, common] + [Path(item["worktree"]) for item in baseline["worktrees"] if item.get("worktree")]
    if any(output.is_relative_to(path.resolve()) for path in protected):
        raise RuntimeError("GC baseline must be written outside all registered worktrees")
    write_json(output, baseline)
    print(f"AUDITED {baseline['repository']['root']} baseline={output}")


def gc_command(args):
    root = Path(args.repository).expanduser().resolve(strict=True)
    baseline_path = args.baseline.expanduser().resolve(strict=True)
    receipt_path = args.receipt.expanduser().resolve()
    if receipt_path.exists():
        raise RuntimeError(f"Receipt already exists: {receipt_path}")
    baseline = json.loads(baseline_path.read_text())
    assert_gc_approval(args.approval.expanduser().resolve(strict=True), baseline_path, baseline)
    check_pre_gc(root, baseline_path, baseline, args.max_age_seconds)
    before_bytes = tree_size(Path(baseline["repository"]["common"]))
    git(root, "gc", "--prune=now", "--quiet", timeout=1800)
    current = current_identity_fields(root, baseline)
    assert_unchanged(baseline, current)
    receipt = gc_receipt(root, baseline_path, baseline, current, before_bytes)
    if receipt["fsck_after"]["fatal"]:
        raise RuntimeError("GC produced fatal fsck findings")
    traverse_all_objects(root)
    write_json(receipt_path, receipt)
    print(f"GC_OK freed_bytes={receipt['git_freed_bytes']} receipt={receipt_path}")


def verify_command(args):
    root = Path(args.repository).expanduser().resolve(strict=True)
    receipt = verify_gc(root, args.baseline.expanduser().resolve(strict=True), args.receipt.expanduser().resolve(strict=True))
    print(f"GC_VERIFIED {receipt['repository']['root']}")


def release_command(args):
    recovery = args.recovery.expanduser().resolve(strict=True)
    receipt_path = args.receipt.expanduser().resolve()
    if receipt_path.exists():
        raise RuntimeError(f"Receipt already exists: {receipt_path}")
    prepared = verify_multi_repo_recovery(recovery)
    assert_release_approval(args.approval.expanduser().resolve(strict=True), recovery, prepared)
    receipt = {
        "schema_version": 1,
        "released_at": time.time(),
        "recovery_path": str(recovery),
        "prepared_sha256": digest(recovery / "prepared.json"),
        "repository_count": len(prepared["repositories"]),
        "operation_count": len(json.loads((recovery / "result.json").read_text())["completed"]),
    }
    temporary = recovery.with_name(recovery.name + ".release-tmp")
    if temporary.exists():
        raise RuntimeError("Temporary release path already exists")
    recovery.rename(temporary)
    shutil.rmtree(temporary)
    if recovery.exists() or temporary.exists():
        raise RuntimeError("Recovery release was incomplete")
    write_json(receipt_path, receipt)
    print(f"RECOVERY_RELEASED {receipt['operation_count']} operations receipt={receipt_path}")


def main():
    args = parse_args()
    if args.command == "audit":
        audit_command(args)
    elif args.command == "gc":
        gc_command(args)
    elif args.command == "verify":
        verify_command(args)
    else:
        release_command(args)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
