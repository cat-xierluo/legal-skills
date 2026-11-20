#!/usr/bin/env python3
"""Prepare, apply, and verify exact local branch cleanup across repositories."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time


OID = re.compile(r"[0-9a-f]{40}\Z")
BASE_ENV = dict(os.environ, GIT_OPTIONAL_LOCKS="0")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare", help="verify a candidate manifest and build recovery data")
    prepare.add_argument("manifest", type=Path)
    prepare.add_argument("recovery", type=Path)
    prepare.add_argument("--quiet-seconds", type=int, default=24 * 60 * 60)
    prepare.add_argument("--fetch-missing", action="store_true")
    prepare.add_argument("--skip-pr-check", action="store_true")

    apply_command = commands.add_parser("apply", help="delete verified local refs after explicit approval")
    apply_command.add_argument("recovery", type=Path)
    apply_command.add_argument("--approval", type=Path, required=True)
    apply_command.add_argument("--max-age-seconds", type=int, default=60 * 60)
    apply_command.add_argument("--skip-pr-check", action="store_true")

    verify = commands.add_parser("verify", help="verify recovery data and post-delete results")
    verify.add_argument("recovery", type=Path)
    return parser.parse_args()


def run(command, *, allowed=(0,), env=None, data=None, timeout=180, cwd=None):
    result = subprocess.run(command, input=data, capture_output=True, env=env or BASE_ENV, timeout=timeout, cwd=cwd)
    if result.returncode not in allowed:
        message = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(message or f"Command failed: {command}")
    return result


def git(root, *args, allowed=(0,), env=None, data=None):
    return run(["git", "--no-optional-locks", "-C", str(root), *args], allowed=allowed, env=env, data=data)


def git_text(root, *args, allowed=(0,)):
    return git(root, *args, allowed=allowed).stdout.decode().strip()


def digest(path: Path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_json(path: Path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def load_manifest(path: Path):
    manifest = json.loads(path.read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("manifest schema_version must be 1")
    repositories = manifest.get("repositories")
    if not isinstance(repositories, list) or not repositories:
        raise ValueError("manifest repositories must be a non-empty list")
    roots = set()
    validated = []
    required_repository = {"name", "root", "base_ref", "base_oid", "pr_check"}
    for repository in repositories:
        if not required_repository.issubset(repository):
            raise ValueError(f"repository fields missing: {sorted(required_repository - set(repository))}")
        if not repository["base_ref"].startswith("refs/"):
            raise ValueError(f"base_ref must be a full ref for {repository['name']}")
        if repository["pr_check"] == "github" and not repository.get("remote_repo"):
            raise ValueError(f"remote_repo is required for GitHub PR checks in {repository['name']}")
        if not OID.fullmatch(repository["base_oid"]):
            raise ValueError(f"invalid base OID for {repository['name']}")
        if repository["pr_check"] not in {"github", "none"}:
            raise ValueError(f"unsupported pr_check for {repository['name']}")
        root = str(Path(repository["root"]).expanduser())
        if root in roots:
            raise ValueError(f"duplicate repository root: {root}")
        roots.add(root)
        branches = repository.get("branches")
        if not isinstance(branches, list) or not branches:
            raise ValueError(f"no branches for {repository['name']}")
        names = set()
        for branch in branches:
            if not {"branch", "tip", "evidence"}.issubset(branch):
                raise ValueError(f"branch fields missing in {repository['name']}")
            if not OID.fullmatch(branch["tip"]):
                raise ValueError(f"invalid tip OID for {repository['name']}")
            if branch["branch"] in names:
                raise ValueError(f"duplicate branch in {repository['name']}: {branch['branch']}")
            names.add(branch["branch"])
        validated.append(repository | {"root": root, "branches": branches})
    return manifest | {"repositories": validated, "source_sha256": digest(path)}


def common_directory(root):
    return Path(git_text(root, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve(strict=True)


def worktrees(root):
    result = git(root, "worktree", "list", "--porcelain", "-z")
    records = {}
    for section in result.stdout.split(b"\0\0"):
        fields = {}
        for raw in section.strip(b"\0").split(b"\0"):
            if raw:
                key, _, value = raw.decode(errors="surrogateescape").partition(" ")
                fields[key] = value
        if "worktree" in fields:
            records[str(Path(fields["worktree"]).resolve())] = fields
    return records


def protected_branches(root):
    config = git(root, "config", "--get-regexp", r"^branch\..+\.(lifecycle|description|integrationtarget|integration-target|remote|merge)$", allowed=(0, 1))
    settings = defaultdict(dict)
    for line in config.stdout.decode(errors="replace").splitlines():
        key, _, value = line.partition(" ")
        branch, setting = key.removeprefix("branch.").rsplit(".", 1)
        settings[branch][setting] = value
    protected = {"main", "master"}
    for branch, values in settings.items():
        lifecycle = f"{values.get('lifecycle', '')} {values.get('description', '')}".lower()
        if "long-lived" in lifecycle or "long lived" in lifecycle:
            protected.add(branch)
        target = values.get("integrationtarget") or values.get("integration-target")
        if target:
            protected.add(target.removeprefix("refs/heads/").removeprefix("origin/"))
        if values.get("remote") == "." and values.get("merge", "").startswith("refs/heads/"):
            protected.add(values["merge"].removeprefix("refs/heads/"))
    return protected


def reflog_data(common: Path, branch: str):
    path = common / "logs" / "refs" / "heads" / branch
    if not path.exists():
        return None, set(), 0
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"Unexpected reflog for {branch}")
    commits = set()
    latest = 0
    for line in path.read_bytes().splitlines():
        left, _, _ = line.partition(b"\t")
        parts = left.split()
        for oid in parts[:2]:
            value = oid.decode(errors="ignore")
            if OID.fullmatch(value) and int(value, 16):
                commits.add(value)
        if len(parts) >= 2:
            try:
                latest = max(latest, int(parts[-2]))
            except ValueError:
                pass
    state = [path.stat().st_size, path.stat().st_mtime_ns, digest(path)]
    return state, commits, latest


def object_exists(root, oid):
    return git(root, "cat-file", "-e", f"{oid}^{{commit}}", allowed=(0, 1)).returncode == 0


def ancestor(root, descendant, base):
    return git(root, "merge-base", "--is-ancestor", descendant, base, allowed=(0, 1)).returncode == 0


def verify_evidence(root, repository, branch):
    evidence = branch["evidence"]
    kind = evidence.get("kind")
    baseline = evidence.get("baseline_oid")
    if not baseline or not OID.fullmatch(baseline):
        raise RuntimeError(f"Invalid evidence baseline for {branch['branch']}")
    if baseline != repository["base_oid"]:
        raise RuntimeError(f"Evidence baseline mismatch for {branch['branch']}")
    if kind == "ancestor":
        if not ancestor(root, branch["tip"], baseline):
            raise RuntimeError(f"Tip is not an ancestor of the baseline: {branch['branch']}")
    elif kind == "merged-pr":
        if repository["pr_check"] != "github":
            raise RuntimeError(f"Merged PR evidence requires a GitHub repository: {branch['branch']}")
        merge_oid = evidence.get("merge_oid")
        number = evidence.get("pr")
        head_oid = evidence.get("head_oid")
        base_name = evidence.get("base_ref_name")
        if not isinstance(number, int) or not head_oid or head_oid != branch["tip"] or not base_name:
            raise RuntimeError(f"Incomplete merged PR identity for {branch['branch']}")
        if not merge_oid or not OID.fullmatch(merge_oid) or not object_exists(root, merge_oid):
            raise RuntimeError(f"Invalid merge commit for {branch['branch']}")
        result = run(["gh", "pr", "view", "-R", repository["remote_repo"], str(number), "--json",
                      "state,mergedAt,headRefName,headRefOid,baseRefName,mergeCommit"],
                     cwd=root)
        pull = json.loads(result.stdout.decode())
        if (pull.get("state") != "MERGED" or not pull.get("mergedAt")
                or pull.get("headRefName") != branch["branch"]
                or pull.get("headRefOid") != head_oid
                or pull.get("baseRefName") != base_name
                or (pull.get("mergeCommit") or {}).get("oid") != merge_oid):
            raise RuntimeError(f"Merged PR identity mismatch for {branch['branch']}")
        if not ancestor(root, merge_oid, baseline):
            raise RuntimeError(f"Merge commit is not on the baseline: {branch['branch']}")
    elif kind == "cached-remote":
        if not ancestor(root, branch["tip"], baseline):
            raise RuntimeError(f"Tip is not on the cached remote baseline: {branch['branch']}")
    else:
        raise RuntimeError(f"Unsupported evidence kind for {branch['branch']}")


def open_pull_requests(root, repository):
    if repository["pr_check"] != "github":
        return []
    result = run(["gh", "pr", "list", "-R", repository["remote_repo"], "--state", "open",
                  "--limit", "1001", "--json", "headRefName,baseRefName"], cwd=root)
    pulls = json.loads(result.stdout.decode())
    if len(pulls) > 1000:
        raise RuntimeError(f"Open PR query may be truncated for {repository['name']}")
    return pulls


def check_branch(root, common, repository, branch, registers, quiet_seconds):
    name = branch["branch"]
    ref = f"refs/heads/{name}"
    git(root, "check-ref-format", "--branch", name)
    if name in protected_branches(root):
        raise RuntimeError(f"Protected branch: {name}")
    if any(fields.get("branch") == ref for fields in registers.values()):
        raise RuntimeError(f"Branch is checked out: {name}")
    tip = git_text(root, "show-ref", "--verify", "--hash", ref, allowed=(0, 1, 128))
    if tip != branch["tip"]:
        raise RuntimeError(f"Branch tip changed: {name}")
    if git(root, "symbolic-ref", "-q", ref, allowed=(0, 1)).returncode == 0:
        raise RuntimeError(f"Branch ref is symbolic: {name}")
    state, commits, reflog_time = reflog_data(common, name)
    commit_time = int(git_text(root, "show", "-s", "--format=%ct", branch["tip"]))
    if max(reflog_time, commit_time) > time.time() - quiet_seconds:
        raise RuntimeError(f"Branch is active within the quiet window: {name}")
    if os.path.lexists(common / f"{ref}.lock"):
        raise RuntimeError(f"Branch ref is locked: {name}")
    verify_evidence(root, repository, branch)
    return state, commits


def check_base(root, repository):
    current = git_text(root, "rev-parse", "--verify", f"{repository['base_ref']}^{{commit}}", allowed=(0, 1, 128))
    if not OID.fullmatch(current):
        raise RuntimeError(f"Base ref is unavailable: {repository['base_ref']}")
    if current != repository["base_oid"]:
        if not ancestor(root, repository["base_oid"], current):
            raise RuntimeError(f"Base history diverged: {repository['base_ref']}")
    if not object_exists(root, repository["base_oid"]):
        raise RuntimeError(f"Base object is unavailable: {repository['base_oid']}")
    return current


def make_commit_pack(root, folder: Path, commits, baseline, fetch_missing):
    unreachable = {commit for commit in commits if not ancestor(root, commit, baseline)}
    if not unreachable:
        return set()
    pack = folder / "unreachable-commits.pack"
    lines = sorted(unreachable) + ["^" + baseline]
    env = dict(BASE_ENV)
    env["GIT_NO_LAZY_FETCH"] = "0" if fetch_missing else "1"
    with pack.open("wb") as handle:
        result = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(root), "pack-objects", "--stdout", "--revs", "--delta-base-offset"],
            input=("\n".join(lines) + "\n").encode(), stdout=handle, stderr=subprocess.PIPE,
            env=env, timeout=300,
        )
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace").strip())
    index = pack.with_suffix(".idx")
    run(["git", "index-pack", str(pack)])
    run(["git", "verify-pack", "-s", str(index)])
    packed = set()
    for line in run(["git", "show-index"], data=index.read_bytes()).stdout.splitlines():
        fields = line.split()
        if len(fields) >= 2:
            packed.add(fields[1].decode())
    for commit in unreachable - packed:
        if not ancestor(root, commit, baseline):
            raise RuntimeError(f"Recovery pack does not cover commit {commit}")
    return packed


def prepare(args):
    manifest_path = args.manifest.expanduser().resolve(strict=True)
    manifest = load_manifest(manifest_path)
    recovery = args.recovery.expanduser()
    if recovery.exists():
        raise RuntimeError(f"Recovery directory already exists: {recovery}")
    recovery.mkdir(mode=0o700)
    os.chmod(recovery, 0o700)
    prepared = {"prepared_at": time.time(), "source_sha256": manifest["source_sha256"], "repositories": {}}
    retained = []
    try:
        for ordinal, repository in enumerate(manifest["repositories"], 1):
            root = repository["root"]
            folder = recovery / f"repo-{ordinal:02d}"
            folder.mkdir(mode=0o700)
            record = {"name": repository["name"], "root": root, "folder": folder.name, "branches": []}
            pending = repository["branches"]
            try:
                common = common_directory(root)
                registers = worktrees(root)
                base_ref = check_base(root, repository)
                pulls = [] if args.skip_pr_check else open_pull_requests(root, repository)
                pull_names = {pull["headRefName"] for pull in pulls} | {pull["baseRefName"] for pull in pulls}
                histories = set()
                archive = folder / "reflogs.tar.gz"
                with tarfile.open(archive, "w:gz", compresslevel=3) as archive_file:
                    for branch in pending:
                        if branch["branch"] in pull_names:
                            raise RuntimeError(f"Branch participates in an open PR: {branch['branch']}")
                        state, commits = check_branch(root, common, repository, branch, registers, args.quiet_seconds)
                        histories.update(commits | {branch["tip"]})
                        log = common / "logs" / "refs" / "heads" / branch["branch"]
                        if state:
                            archive_file.add(log, arcname=f"logs/refs/heads/{branch['branch']}", recursive=False)
                        record["branches"].append(branch | {"reflog": state})
                typed = set()
                for commit in histories:
                    if object_exists(root, commit):
                        typed.add(commit)
                for branch in record["branches"]:
                    if branch["tip"] not in typed:
                        raise RuntimeError(f"Branch tip object is missing: {branch['branch']}")
                make_commit_pack(root, folder, typed, repository["base_oid"], args.fetch_missing)
                record["base_ref_before"] = base_ref
                record["backup_sha256"] = {path.name: digest(path) for path in folder.iterdir() if path.is_file()}
                prepared["repositories"][root] = record
                print(f"PREPARED {repository['name']} {len(record['branches'])}", flush=True)
            except (RuntimeError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
                completed = {item["branch"] for item in record["branches"]}
                retained.extend({"repository": repository["name"], "branch": item["branch"], "reason": str(error)}
                                for item in pending if item["branch"] not in completed)
                print(f"RETAINED {repository['name']} {error}", flush=True)
        shutil.copyfile(manifest_path, recovery / "manifest.json")
        (recovery / "manifest.sha256").write_text(manifest["source_sha256"] + "\n")
        write_json(recovery / "prepared.json", prepared | {"retained_during_prepare": retained})
        if retained:
            raise RuntimeError(f"{len(retained)} targets were retained during preparation")
    except Exception:
        if not prepared["repositories"]:
            shutil.rmtree(recovery, ignore_errors=True)
        raise


def verify_recovery(recovery: Path, prepared, max_age_seconds=None):
    if not recovery.is_dir():
        raise RuntimeError("Recovery directory is unavailable")
    if digest(recovery / "manifest.json") != prepared["source_sha256"]:
        raise RuntimeError("Manifest digest changed")
    if (recovery / "manifest.sha256").read_text().strip() != prepared["source_sha256"]:
        raise RuntimeError("Manifest digest record changed")
    if max_age_seconds is not None and time.time() - prepared["prepared_at"] > max_age_seconds:
        raise RuntimeError("Prepared evidence is too old")
    for record in prepared["repositories"].values():
        folder = recovery / record["folder"]
        for name, expected in record["backup_sha256"].items():
            if digest(folder / name) != expected:
                raise RuntimeError(f"Recovery checksum changed: {name}")
        index = folder / "unreachable-commits.idx"
        if index.exists():
            run(["git", "verify-pack", "-s", str(index)])


def check_approval(approval: Path, manifest_sha256):
    record = json.loads(approval.read_text())
    if record.get("manifest_sha256") != manifest_sha256:
        raise RuntimeError("Approval does not bind the candidate manifest")
    if not record.get("authorization"):
        raise RuntimeError("Approval has no authorization statement")
    if not record.get("approved_by"):
        raise RuntimeError("Approval has no approver")


def apply_cleanup(args):
    recovery = args.recovery.expanduser().resolve(strict=True)
    prepared = json.loads((recovery / "prepared.json").read_text())
    manifest = json.loads((recovery / "manifest.json").read_text())
    verify_recovery(recovery, prepared, args.max_age_seconds)
    check_approval(args.approval.expanduser().resolve(strict=True), prepared["source_sha256"])
    repository_by_root = {item["root"]: item for item in manifest["repositories"]}
    result = {"completed": [], "retained": prepared.get("retained_during_prepare", [])}
    for root, record in prepared["repositories"].items():
        repository = repository_by_root[root]
        prepared_branches = {item["branch"]: item for item in record["branches"]}
        try:
            common = common_directory(root)
            registers = worktrees(root)
            check_base(root, repository)
            pulls = [] if args.skip_pr_check else open_pull_requests(root, repository)
            pull_names = {pull["headRefName"] for pull in pulls} | {pull["baseRefName"] for pull in pulls}
        except (RuntimeError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
            result["retained"].extend({"repository": record["name"], "branch": item["branch"], "reason": str(error)}
                                      for item in record["branches"])
            continue
        for branch in record["branches"]:
            name = branch["branch"]
            try:
                if name in pull_names:
                    raise RuntimeError(f"Branch participates in an open PR: {name}")
                state, _ = check_branch(root, common, repository, branch, registers, 0)
                if state != prepared_branches[name]["reflog"]:
                    raise RuntimeError(f"Reflog changed after preparation: {name}")
                ref = f"refs/heads/{name}"
                git(root, "update-ref", "--no-deref", "-d", ref, branch["tip"])
                if git(root, "show-ref", "--verify", "--quiet", ref, allowed=(0, 1)).returncode == 0:
                    raise RuntimeError(f"Branch still exists: {name}")
                item = {"repository": record["name"], "root": root, "branch": name, "tip": branch["tip"]}
                result["completed"].append(item)
                with (recovery / "operations.jsonl").open("a") as receipt:
                    receipt.write(json.dumps(item, ensure_ascii=False) + "\n")
            except (RuntimeError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
                result["retained"].append({"repository": record["name"], "branch": name, "reason": str(error)})
        count = sum(item["root"] == root for item in result["completed"])
        print(f"APPLIED {record['name']} {count}/{len(record['branches'])}", flush=True)
    write_json(recovery / "result.json", result)
    if len(result["completed"]) != sum(len(item["branches"]) for item in prepared["repositories"].values()) or result["retained"]:
        raise RuntimeError("Some targets were retained")


def verify_cleanup(args):
    recovery = args.recovery.expanduser().resolve(strict=True)
    prepared = json.loads((recovery / "prepared.json").read_text())
    result = json.loads((recovery / "result.json").read_text())
    operations = [json.loads(line) for line in (recovery / "operations.jsonl").read_text().splitlines()]
    verify_recovery(recovery, prepared)
    if operations != result["completed"] or result["retained"]:
        raise RuntimeError("Result receipt is inconsistent")
    seen = set()
    for operation in operations:
        identity = (operation["root"], operation["branch"], operation["tip"])
        if identity in seen:
            raise RuntimeError(f"Duplicate operation: {operation['branch']}")
        seen.add(identity)
        if git(operation["root"], "show-ref", "--verify", "--quiet", f"refs/heads/{operation['branch']}", allowed=(0, 1)).returncode == 0:
            raise RuntimeError(f"Deleted branch still exists: {operation['branch']}")
    expected = {
        (record["root"], branch["branch"], branch["tip"])
        for record in prepared["repositories"].values() for branch in record["branches"]
    }
    if seen != expected:
        raise RuntimeError("Operations do not cover the prepared set")
    print(f"VERIFIED {len(operations)} local branch deletions")


def main():
    args = parse_args()
    if args.command == "prepare":
        prepare(args)
    elif args.command == "apply":
        apply_cleanup(args)
    else:
        verify_cleanup(args)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
