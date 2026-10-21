#!/usr/bin/env python3
"""Bounded metadata-only disk diagnosis. No cleanup or application imports."""
import argparse
from datetime import datetime, timezone
import heapq
import json
import math
import os
from pathlib import Path
import sqlite3
import stat
import sys
import time

SCHEMA = "disk-insight/1"


def absolute(value):
    return os.path.abspath(os.path.expanduser(value))


def inside(path, root):
    return path == root or path.startswith(root.rstrip("/") + "/")


def emit(payload, output):
    # Only caller-selected new files; no implicit state, overwrite or symlink following.
    target = Path(output).expanduser()
    if not target.parent.is_dir():
        raise ValueError("output parent must already exist")
    data = (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
    print(json.dumps({"output": str(target.absolute()), "schema": payload["schema"],
                      "kind": payload["kind"]}, ensure_ascii=False))


def positive(value):
    n = int(value)
    if n <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return n


def seconds_value(value):
    n = float(value)
    if not math.isfinite(n) or n <= 0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return n


def scan(args):
    roots = sorted(set(absolute(p) for p in args.root))
    for i, root in enumerate(roots):
        if os.path.realpath(root) != root:
            raise ValueError("root contains a symbolic link; choose its real path explicitly")
        if any(inside(root, old) for old in roots[:i]):
            raise ValueError("overlapping roots; scan disjoint roots")
    start = time.monotonic()
    deadline = start + args.seconds
    now = time.time()
    cutoff = now - args.days * 86400
    count = 0
    exhausted = False
    results = []
    excludes = sorted(set(args.exclude_name or []))
    for root in roots:
        rows = {}
        seen = set()
        errors = []
        error_count = 0
        mount_count = 0
        big = []
        partial = False
        root_entries = 0

        def error(path, reason):
            nonlocal error_count, partial
            error_count += 1
            partial = True
            if len(errors) < 20:
                errors.append({"path": path, "reason": reason})

        def add(path, st):
            nonlocal root_entries
            root_entries += 1
            if stat.S_ISREG(st.st_mode) and st.st_nlink > 1:
                key = (st.st_dev, st.st_ino)
                if key in seen:
                    return
                seen.add(key)
            allocated = st.st_blocks * 512
            logical = st.st_size if stat.S_ISREG(st.st_mode) else 0
            modified = stat.S_ISREG(st.st_mode) and st.st_mtime >= cutoff
            parent = path if stat.S_ISDIR(st.st_mode) else os.path.dirname(path)
            while inside(parent, root):
                depth = len(Path(parent).relative_to(root).parts)
                if depth <= args.depth:
                    row = rows.setdefault(parent, {"path": parent, "allocated_bytes": 0,
                                                  "logical_bytes": 0, "recent_modified_logical_bytes": 0})
                    row["allocated_bytes"] += allocated
                    row["logical_bytes"] += logical
                    row["recent_modified_logical_bytes"] += logical if modified else 0
                if parent == root:
                    break
                parent = os.path.dirname(parent)
            if stat.S_ISREG(st.st_mode) and logical >= args.min_file_mib * 1048576:
                item = (logical, path, allocated, st.st_mtime)
                if len(big) < args.top:
                    heapq.heappush(big, item)
                elif item > big[0]:
                    heapq.heapreplace(big, item)

        try:
            st = os.lstat(root)
            if not stat.S_ISDIR(st.st_mode):
                raise ValueError("root must be a directory: " + root)
        except OSError as exc:
            results.append({"root": root, "status": "unavailable", "reason": type(exc).__name__,
                            "rows": [], "large_files": []})
            continue
        if exhausted or count >= args.max_entries or time.monotonic() >= deadline:
            exhausted = True
            results.append({"root": root, "status": "unavailable", "reason": "budget",
                            "rows": [], "large_files": []})
            continue
        count += 1
        add(root, st)
        device = st.st_dev
        stack = []

        def enter(path):
            try:
                stack.append(os.scandir(path))
            except OSError as exc:
                error(path, type(exc).__name__)

        enter(root)
        try:
            while stack:
                if count >= args.max_entries or time.monotonic() >= deadline:
                    exhausted = True
                    partial = True
                    break
                try:
                    entry = next(stack[-1])
                except StopIteration:
                    stack.pop().close()
                    continue
                except OSError as exc:
                    error(root, type(exc).__name__)
                    stack.pop().close()
                    continue
                count += 1
                if entry.name in excludes:
                    continue
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError as exc:
                    error(entry.path, type(exc).__name__)
                    continue
                if info.st_dev != device:
                    mount_count += 1
                    continue
                add(entry.path, info)
                if stat.S_ISDIR(info.st_mode):
                    enter(entry.path)
        finally:
            for iterator in stack:
                iterator.close()
        results.append({"root": root, "status": "partial" if partial else "complete",
                        "budget_exhausted": exhausted, "entries_seen": root_entries,
                        "error_count": error_count, "errors": errors,
                        "excluded_mounts": mount_count,
                        "rows": sorted(rows.values(), key=lambda x: -x["allocated_bytes"]),
                        "large_files": [{"path": p, "logical_bytes": n, "allocated_bytes": a,
                                         "mtime_utc": datetime.fromtimestamp(t, timezone.utc).isoformat()}
                                        for n, p, a, t in sorted(big, reverse=True)]})
    return {"schema": SCHEMA, "kind": "scan", "created_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(time.monotonic() - start, 3), "entries_seen": count,
            "policy": {"roots": roots, "depth": args.depth, "exclude_names": excludes,
                       "metric": "st_blocks*512; hardlinks dedup within each root",
                       "follow_symlinks": False, "one_device_per_root": True},
            "budgets": {"seconds": args.seconds, "max_entries": args.max_entries},
            "recent_modified_days": args.days, "results": results,
            "notes": ["rows are cumulative; do not sum parents and children",
                      "mtime is a clue, not growth; bytes are not reclaimable space",
                      "live metadata is not an atomic filesystem snapshot; clones not deduplicated"]}


def compare(args):
    with open(args.before, encoding="utf-8") as f:
        a = json.load(f)
    with open(args.after, encoding="utf-8") as f:
        b = json.load(f)
    if any(x.get("schema") != SCHEMA or x.get("kind") != "scan" for x in (a, b)):
        raise ValueError("unsupported scan schema/kind")
    if not a.get("policy") or a["policy"] != b.get("policy"):
        raise ValueError("incomparable scan policies")
    if datetime.fromisoformat(a["created_at"]) >= datetime.fromisoformat(b["created_at"]):
        raise ValueError("before must precede after")
    if any(r.get("status") != "complete" or r.get("excluded_mounts") for x in (a, b) for r in x["results"]):
        raise ValueError("partial/unavailable or mount-excluded scan: no full comparison")
    maps = [{r["path"]: r["allocated_bytes"] for root in x["results"] for r in root["rows"]} for x in (a, b)]
    return {"schema": SCHEMA, "kind": "scan-diff", "before": a["created_at"], "after": b["created_at"],
            "policy": a["policy"], "rows": diff_rows(*maps),
            "notes": ["cumulative rows overlap; missing means not recorded, not zero or deletion"]}


def diff_rows(a, b):
    rows = []
    for path in sorted(a.keys() | b.keys()):
        av, bv = a.get(path), b.get(path)
        rows.append({"path": path, "before_bytes": av, "after_bytes": bv,
                     "delta_bytes": bv - av if av is not None and bv is not None else None,
                     "status": "both_recorded" if av is not None and bv is not None
                     else "not_recorded_before" if av is None else "not_recorded_after"})
    return sorted(rows, key=lambda x: -(x["delta_bytes"] or 0))


def fathom(args):
    path = Path(args.db).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError("database must be an existing file")
    # No application connection: Fathom's connect() can perform schema/index writes.
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version != 9:
            raise ValueError("unsupported Fathom schema (expected user_version=9)")
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(snapshots)")}
        needed = {"id", "created_at", "root", "min_kb", "exclude_names", "metric_version",
                  "plan_id", "collection_status", "denied_count", "vanished_count"}
        if not needed <= cols:
            raise ValueError("unsupported Fathom snapshot columns")
        snapshots = [dict(r) for r in conn.execute("SELECT * FROM snapshots ORDER BY created_at,id")]
        if args.command == "fathom-list":
            return {"schema": SCHEMA, "kind": "fathom-list", "db": str(path),
                    "db_schema": version, "snapshots": snapshots}
        by_id = {r["id"]: r for r in snapshots}
        if args.before not in by_id or args.after not in by_id:
            raise ValueError("snapshot ID not found; run fathom-list")
        a, b = by_id[args.before], by_id[args.after]
        keys = ("root", "min_kb", "exclude_names", "metric_version", "plan_id")
        if any(a[k] is None or b[k] is None or a[k] != b[k] for k in keys):
            raise ValueError("incomparable or unknown Fathom dataset metadata")
        if datetime.fromisoformat(a["created_at"]) >= datetime.fromisoformat(b["created_at"]):
            raise ValueError("before must precede after")
        focus = absolute(args.focus)
        if not inside(focus, a["root"]):
            raise ValueError("focus outside snapshot root")
        maps = []
        for snapshot in (a, b):
            found = {}
            prefix = focus.rstrip("/") + "/"
            # Literal prefix; no LIKE wildcards from directory names.
            for row in conn.execute("SELECT path,size_kb FROM entries WHERE snapshot_id=? AND "
                                    "(path=? OR substr(path,1,?)=?)",
                                    (snapshot["id"], focus, len(prefix), prefix)):
                if len(Path(row["path"]).relative_to(focus).parts) <= args.depth:
                    found[row["path"]] = row["size_kb"] * 1024
            maps.append(found)
        return {"schema": SCHEMA, "kind": "fathom-diff", "db": str(path), "db_schema": version,
                "before": a, "after": b, "focus": focus, "depth": args.depth,
                "rows": diff_rows(*maps), "notes": ["partial quality applies to recorded deltas",
                "cumulative rows overlap; do not sum; missing does not mean deletion",
                "historical allocated bytes are not reclaimable bytes"]}
    finally:
        conn.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("scan", help="metadata-only, bounded, no symlink traversal")
    s.add_argument("--root", action="append", required=True)
    s.add_argument("--depth", type=positive, default=2)
    s.add_argument("--seconds", type=seconds_value, default=45)
    s.add_argument("--max-entries", type=positive, default=200000)
    s.add_argument("--days", type=positive, default=7)
    s.add_argument("--min-file-mib", type=positive, default=100)
    s.add_argument("--top", type=positive, default=30)
    s.add_argument("--exclude-name", action="append", help="exact entry name, applies recursively")
    c = sub.add_parser("compare", help="compare complete scans of identical policy")
    c.add_argument("--before", required=True)
    c.add_argument("--after", required=True)
    for command in ("fathom-list", "fathom-diff"):
        f = sub.add_parser(command, help="query existing Fathom database in read-only mode")
        f.add_argument("--db", required=True)
        if command == "fathom-diff":
            f.add_argument("--before", required=True, type=positive)
            f.add_argument("--after", required=True, type=positive)
            f.add_argument("--focus", required=True)
            f.add_argument("--depth", type=positive, default=1)
    for parser in (s, c, *[sub.choices[k] for k in ("fathom-list", "fathom-diff")]):
        parser.add_argument("--output", required=True, help="new JSON file, parent must exist")
    args = p.parse_args()
    try:
        out = Path(args.output).expanduser()
        if os.path.lexists(out):
            raise ValueError("output exists; refusing overwrite")
        if args.command == "scan" and any(inside(absolute(args.output), absolute(r)) for r in args.root):
            raise ValueError("output must be outside all scanned roots")
        result = scan(args) if args.command == "scan" else compare(args) if args.command == "compare" else fathom(args)
        emit(result, args.output)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        print("disk-insight: " + str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
