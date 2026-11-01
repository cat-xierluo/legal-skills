#!/usr/bin/env python3
"""Save dirty working files and index state outside a repository; never restore it."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import uuid

ROUTING = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")


def git(repo, *args):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    return subprocess.check_output(["git", "-C", str(repo), *args], env=env)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=True, indent=2) + "\n").encode()


def read_state(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {"kind": "absent"}
    mode = stat.S_IMODE(info.st_mode)
    if stat.S_ISLNK(info.st_mode):
        return {"kind": "symlink", "target": os.readlink(path)}
    if stat.S_ISREG(info.st_mode):
        data = path.read_bytes()
        return {"kind": "file", "sha256": sha(data), "size": len(data), "mode": mode}
    if stat.S_ISDIR(info.st_mode):
        if (path / ".git").exists():
            # A submodule keeps its own repository; never copy or follow it here.
            return {"kind": "submodule", "mode": mode}
        return {"kind": "directory", "mode": mode}
    raise ValueError("unsupported special file: " + str(path))


def safe_path(root, relative):
    p = Path(relative)
    if not relative or p.is_absolute() or any(x in ("..", ".git") for x in p.parts):
        raise ValueError("unsafe relative path: " + repr(relative))
    full = root / p
    # A leaf symlink is copied as a link. Parent symlinks are never traversed.
    for parent in p.parents:
        if (root / parent).is_symlink():
            raise ValueError("path crosses symlink: " + repr(relative))
    return full


def status_entries(raw):
    fields = raw.split(b"\0")
    result = []
    i = 0
    while i < len(fields) and fields[i]:
        field = fields[i]
        i += 1
        code, path = field[:2].decode("ascii"), os.fsdecode(field[3:])
        entry = {"code": code, "path": path}
        if "R" in code or "C" in code:
            entry["old_path"] = os.fsdecode(fields[i])
            i += 1
        result.append(entry)
    return result


def collect(repo, entries, include_ignored):
    names = {e["path"] for e in entries}
    names.update(e["old_path"] for e in entries if "old_path" in e)
    if include_ignored:
        names.update(os.fsdecode(p) for p in git(
            repo, "ls-files", "--others", "--ignored", "--exclude-standard", "-z"
        ).split(b"\0") if p)
    states = {}

    def visit(name):
        if name in states:
            return
        path = safe_path(repo, name)
        value = read_state(path)
        states[name] = value
        if value["kind"] == "directory":
            for child in sorted(path.iterdir()):
                visit(child.relative_to(repo).as_posix())
        elif value["kind"] == "submodule":
            states[name] = {"kind": "submodule", "mode": value["mode"]}

    for name in sorted(names):
        visit(name)
    return states


def capture_git(repo):
    head = git(repo, "rev-parse", "HEAD").strip().decode()
    branch = git(repo, "symbolic-ref", "--quiet", "HEAD").strip().decode()
    index = Path(os.fsdecode(git(repo, "rev-parse", "--git-path", "index").strip()))
    if not index.is_absolute():
        index = repo / index
    raw_index = index.read_bytes()
    staged = git(repo, "ls-files", "--stage", "-z")
    status = git(repo, "status", "--porcelain=v1", "-z", "-uall")
    return {"head": head, "branch": branch, "index": raw_index,
            "index_entries": staged, "status": status}


def snapshot(repo, safety_root, label, include_ignored=False):
    if any(os.environ.get(k) for k in ROUTING):
        raise ValueError("unset Git routing environment before snapshot")
    repo = Path(repo).expanduser().resolve()
    top = Path(os.fsdecode(git(repo, "rev-parse", "--show-toplevel").strip())).resolve()
    if repo != top:
        raise ValueError("--repo must identify the repository root")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", label):
        raise ValueError("label must be a short filename component")
    safety = Path(safety_root).expanduser().resolve()
    if safety == repo or repo in safety.parents:
        raise ValueError("snapshot destination must be outside the repository")
    before = capture_git(repo)
    entries = status_entries(before["status"])
    states = collect(repo, entries, include_ignored)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = safety / repo.name / (stamp + "-" + label + "-" + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, mode=0o700)
    out.chmod(0o700)
    inventory = {}
    skipped = []

    def save(relative, data):
        target = safe_path(out, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(0o600)
        inventory[relative] = sha(data)

    try:
        save("index.bin", before["index"])
        save("index-entries.z", before["index_entries"])
        save("status.z", before["status"])
        save("status.json", encode(entries))
        # Preserve index blobs for staged, renamed, added and unmerged paths.
        changed_index = {e["path"] for e in entries if e["code"][0] not in (" ", "?")}
        staged_objects = []
        for line in before["index_entries"].split(b"\0"):
            if not line:
                continue
            header, raw_path = line.split(b"\t", 1)
            mode, oid, stage = header.decode().split()
            name = os.fsdecode(raw_path)
            if name not in changed_index:
                continue
            if mode == "160000":
                # A submodule's inner state lives in another repository; only the
                # gitlink is recorded here. Snapshot it separately, never fail silently.
                skipped.append({"path": name, "reason": "dirty submodule; snapshot the submodule repository separately",
                                 "oid": oid, "stage": stage})
                continue
            data = git(repo, "cat-file", "blob", oid)
            blob_path = "index-blobs/" + oid
            if blob_path not in inventory:
                save(blob_path, data)
            staged_objects.append({"path": name, "mode": mode, "stage": stage,
                                   "oid": oid, "file": blob_path})
        save("staged-objects.json", encode(staged_objects))
        save("skipped.json", encode(skipped))
        for name, expected in sorted(states.items()):
            source = safe_path(repo, name)
            destination = safe_path(out / "working-tree", name)
            if read_state(source) != expected:
                raise ValueError("source drift before copying: " + repr(name))
            if expected["kind"] == "file":
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination, follow_symlinks=False)
            elif expected["kind"] == "symlink":
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.symlink_to(expected["target"])
            elif expected["kind"] == "directory":
                destination.mkdir(parents=True, exist_ok=True)
                destination.chmod(expected["mode"])
            elif expected["kind"] == "submodule":
                skipped.append({"path": name, "reason": "submodule working tree; snapshot the submodule repository separately",
                                 "mode": expected["mode"]})
                continue
            if expected["kind"] != "submodule" and read_state(destination) != expected:
                raise ValueError("copy mismatch: " + repr(name))
        # Catch changes during copying, including same-status text edits.
        if capture_git(repo) != before or collect(repo, entries, include_ignored) != states:
            raise ValueError("repository drift during snapshot; retry after writers yield")
        save("states.json", encode(states))
        meta = {"schema": "git-workflow/main-snapshot/v1", "complete": True,
                "skipped": skipped,
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "repo": str(repo), "head": before["head"], "branch": before["branch"],
                "label": label, "include_ignored": include_ignored,
                "entries": len(entries), "working_paths": len(states),
                "staged_blobs": len(staged_objects), "files": inventory}
        (out / "snapshot.json").write_bytes(encode(meta))
        checked = verify(out)
        if checked["status"] != "PASS":
            raise ValueError("new snapshot failed self-verification: " + repr(checked))
        return {**checked, "head": meta["head"], "entries": len(entries),
                "working_paths": len(states), "staged_blobs": len(staged_objects),
                "skipped": skipped}
    except Exception as error:
        (out / "INCOMPLETE.json").write_bytes(encode({"complete": False, "error": str(error)}))
        raise


def verify(snapshot_dir):
    root = Path(snapshot_dir).expanduser().resolve()
    meta = json.loads((root / "snapshot.json").read_bytes())
    problems = []
    if meta.get("schema") != "git-workflow/main-snapshot/v1" or meta.get("complete") is not True:
        problems.append("invalid or incomplete snapshot")
    if (root / "INCOMPLETE.json").exists():
        problems.append("incomplete marker present")
    required = {"index.bin", "index-entries.z", "status.z", "status.json", "states.json",
                "staged-objects.json", "skipped.json"}
    if not required <= set(meta.get("files", {})):
        problems.append("missing required metadata files")
    for name, expected in meta.get("files", {}).items():
        path = safe_path(root, name)
        if not path.is_file() or path.is_symlink() or sha(path.read_bytes()) != expected:
            problems.append("metadata/blob mismatch: " + name)
    if not problems:
        states = json.loads((root / "states.json").read_bytes())
        for name, expected in states.items():
            if expected["kind"] == "submodule":
                continue
            if read_state(safe_path(root / "working-tree", name)) != expected:
                problems.append("working path mismatch: " + repr(name))
        for entry in json.loads((root / "staged-objects.json").read_bytes()):
            path = safe_path(root, entry["file"])
            if entry["file"] not in meta["files"] or sha(path.read_bytes()) != meta["files"][entry["file"]]:
                problems.append("missing staged object: " + repr(entry["path"]))
    return {"status": "FAIL" if problems else "PASS", "snapshot_dir": str(root),
            "problems": problems,
            "skipped": meta.get("skipped", []),
            "scope": "verifies snapshot internal consistency and byte integrity only; "
                     "it does not prove the snapshot equals the pre-incident repository state"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--repo")
    operation.add_argument("--verify", metavar="SNAPSHOT_DIR")
    parser.add_argument("--label", default="pre-main-adoption")
    parser.add_argument("--safety-root", help="required for creation; outside repo")
    parser.add_argument("--include-ignored", action="store_true",
                        help="copy ignored paths too; preflight size/privacy first")
    args = parser.parse_args()
    if args.repo and not args.safety_root:
        parser.error("--safety-root is required with --repo")
    try:
        result = verify(args.verify) if args.verify else snapshot(
            args.repo, args.safety_root, args.label, args.include_ignored)
    except (OSError, ValueError, subprocess.SubprocessError, KeyError, TypeError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=True), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
