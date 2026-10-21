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
                      "live metadata is not an atomic filesystem snapshot; clones not deduplicated",
                      "hardlinks are deduplicated within each scanned root only; the same "
                      "inode counted under two separate roots appears in both"]}


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


def default_fathom_dbs():
    # Standard macOS application support location plus the documented env override.
    # A bounded search for "fathom" directories also finds project-local copies
    # (for example <vendor>/fathom/data/fathom.db) without assuming a machine layout.
    candidates = []
    env_db = os.environ.get("FATHOM_DB")
    if env_db:
        candidates.append(Path(env_db).expanduser())
    home = os.environ.get("HOME") or str(Path.home())
    home_path = Path(os.path.realpath(home))
    support = home_path / "Library/Application Support"
    if support.is_dir():
        standard = support / "Fathom/data/fathom.db"
        if standard.is_file():
            candidates.append(standard)
        for directory in bounded_find(support, "fathom", max_depth=4, max_entries=20000):
            candidates.append(directory / "data/fathom.db")
    else:
        candidates.extend(bounded_find(home_path, "fathom.db", max_depth=6, max_entries=20000,
                                       kind="file"))
    return candidates


def bounded_find(root, name, max_depth, max_entries, kind="directory"):
    found = []
    seen = 0
    stack = [(root, 0)]
    while stack and seen < max_entries:
        current, depth = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            seen += 1
            if seen > max_entries:
                break
            matches = (entry.is_dir(follow_symlinks=False) if kind == "directory"
                       else entry.is_file(follow_symlinks=False))
            if entry.name == name and matches:
                found.append(Path(entry.path))
            elif depth < max_depth and entry.is_dir(follow_symlinks=False):
                stack.append((Path(entry.path), depth + 1))
    return found


def open_fathom(path):
    # No application connection: Fathom's connect() can perform schema/index writes.
    path = Path(path).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError("database must be an existing file")
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
        tables = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        snapshots = [dict(r) for r in conn.execute("SELECT * FROM snapshots ORDER BY created_at,id")]
        volume_stats = []
        if "volume_stats" in tables and {"snapshot_id", "total_bytes", "free_bytes"} <= {
                r["name"] for r in conn.execute("PRAGMA table_info(volume_stats)")}:
            volume_stats = [dict(r) for r in conn.execute(
                "SELECT * FROM volume_stats ORDER BY snapshot_id")]
        capacity = []
        if "container_capacity_samples" in tables and {
                "container_id", "total_bytes", "free_bytes", "sampled_at"} <= {
                r["name"] for r in conn.execute("PRAGMA table_info(container_capacity_samples)")}:
            capacity = [dict(r) for r in conn.execute(
                "SELECT * FROM container_capacity_samples ORDER BY sampled_at,id")]
        return {"path": str(path), "schema_version": version, "snapshots": snapshots,
                "volume_stats": volume_stats, "capacity_samples": capacity}
    except Exception:
        conn.close()
        raise


def fathom_payload(db):
    return {"schema": SCHEMA, "kind": "fathom-list", "db": db["path"],
            "db_schema": db["schema_version"], "snapshots": db["snapshots"],
            "volume_stats": db["volume_stats"], "capacity_samples": db["capacity_samples"]}


def dataset_key(row):
    return tuple(row[k] for k in ("root", "min_kb", "exclude_names", "metric_version", "plan_id"))


def snapshot_time(row):
    """Return the snapshot timestamp, or None when the stored value is unusable."""
    try:
        return datetime.fromisoformat(row["created_at"]).timestamp()
    except (TypeError, ValueError):
        return None


def choose_history_pair(db, focus, days):
    eligible = [r for r in db["snapshots"] if inside(focus, r["root"])]
    groups = {}
    for row in eligible:
        if any(row[k] is None for k in ("root", "min_kb", "exclude_names", "metric_version", "plan_id")):
            continue
        groups.setdefault(dataset_key(row), []).append(row)
    choices = []
    corrupt_groups = []
    for rows in groups.values():
        rows.sort(key=lambda r: (r["created_at"], r["id"]))
        if len(rows) < 2:
            continue
        timed = [(r, snapshot_time(r)) for r in rows]
        usable = [(r, t) for r, t in timed if t is not None]
        if not usable:
            # Every timestamp in this dataset is unparsable: the history is damaged,
            # not absent. Never let that degrade into a silent "no history".
            corrupt_groups.append({"dataset": list(dataset_key(rows[0])),
                                   "snapshot_count": len(rows),
                                   "invalid_timestamps": len(rows)})
            continue
        after, after_at = usable[-1]
        target = after_at - days * 86400
        prior = [(r, t) for r, t in usable[:-1] if t <= target]
        before = prior[-1][0] if prior else usable[0][0]
        choices.append((after["created_at"], len(rows), before, after))
    if choices:
        _, _, before, after = max(choices, key=lambda item: (item[0], item[1]))
        return {"before": before, "after": after, "corrupt_datasets": corrupt_groups}
    return {"before": None, "after": None, "corrupt_datasets": corrupt_groups}


def capacity_deltas(samples, before_time, after_time):
    rows = []
    before_at = datetime.fromisoformat(before_time).timestamp()
    after_at = datetime.fromisoformat(after_time).timestamp()
    ids = sorted({r["container_id"] for r in samples if r.get("container_id")})
    for container_id in ids:
        series = sorted((r for r in samples if r.get("container_id") == container_id),
                        key=lambda r: (r["sampled_at"], r.get("id", 0)))
        if not series:
            continue
        # Fathom records capacity after the directory scan in the same round.
        # Pick the nearest sample on each side, then disclose its time distance.
        a = min(series, key=lambda r: abs(datetime.fromisoformat(r["sampled_at"]).timestamp() - before_at))
        b = min(series, key=lambda r: abs(datetime.fromisoformat(r["sampled_at"]).timestamp() - after_at))
        row = {"container_id": container_id, "before": a, "after": b,
               "before_distance_seconds": round(
                   datetime.fromisoformat(a["sampled_at"]).timestamp() - before_at, 3),
               "after_distance_seconds": round(
                   datetime.fromisoformat(b["sampled_at"]).timestamp() - after_at, 3),
               "total_bytes_delta": b["total_bytes"] - a["total_bytes"]}
        if a.get("free_bytes") is not None and b.get("free_bytes") is not None:
            row["free_bytes_delta"] = b["free_bytes"] - a["free_bytes"]
        rows.append(row)
    return rows


def discover_fathom(explicit, focus, days):
    candidates = list(explicit or [])
    if not candidates:
        candidates = default_fathom_dbs()
    reports = []
    usable = []
    corrupt = []
    seen = set()
    for candidate in candidates:
        candidate = candidate.resolve(strict=False)
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            db = open_fathom(candidate)
        except (OSError, ValueError, sqlite3.Error) as exc:
            reports.append({"path": str(candidate), "status": "unavailable", "reason": str(exc)})
            continue
        pair = choose_history_pair(db, focus, days)
        corrupt_datasets = pair["corrupt_datasets"]
        if pair["before"] is not None:
            reports.append({"path": db["path"], "status": "usable",
                            "snapshot_count": len(db["snapshots"])})
            usable.append((db, pair))
            continue
        if corrupt_datasets:
            # A damaged dataset is not the same as an absent one; keep it visible
            # and fail closed instead of silently degrading to "no history".
            reports.append({"path": db["path"], "status": "corrupt_history",
                            "snapshot_count": len(db["snapshots"]),
                            "corrupt_datasets": corrupt_datasets})
            corrupt.append((db, corrupt_datasets))
            continue
        reports.append({"path": db["path"], "status": "no_comparable_focus_pair",
                        "snapshot_count": len(db["snapshots"])})
    if not usable:
        return {"selected": None, "discovered_dbs": reports, "corrupt": corrupt}
    # Prefer the newest usable after snapshot; explicit databases are still ranked by evidence.
    db, pair = max(usable, key=lambda item: item[1]["after"]["created_at"])
    return {"selected": {"db": db, "before": pair["before"], "after": pair["after"]},
            "discovered_dbs": reports, "corrupt": corrupt}


def history(args):
    focus = absolute(args.focus)
    explicit = [Path(p).expanduser() for p in (args.db or [])]
    if args.db_dir:
        root = Path(args.db_dir).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError("--db-dir must be an existing directory")
        explicit.extend(bounded_find(root, "fathom.db", max_depth=6, max_entries=20000,
                                     kind="file"))
    discovery = discover_fathom(explicit, focus, args.days)
    selected = discovery["selected"]
    corrupt = discovery["corrupt"]
    if selected is None:
        if corrupt:
            # Damaged history must not pass as "no history"; fail closed and name the
            # damaged datasets so the caller can fall back to an explicit scan.
            detail = [{"path": db["path"], "corrupt_datasets": datasets}
                       for db, datasets in corrupt]
            raise ValueError("corrupt history: unusable snapshot timestamps in "
                             + "; ".join(item["path"] for item in detail))
        return {"schema": SCHEMA, "kind": "history-summary", "status": "no_history",
                "focus": focus, "requested_days": args.days,
                "discovered_dbs": discovery["discovered_dbs"],
                "notes": ["no comparable read-only history; perform bounded independent scans"]}
    db = selected["db"]
    before, after = selected["before"], selected["after"]
    if args.before is not None or args.after is not None:
        by_id = {r["id"]: r for r in db["snapshots"]}
        try:
            before = by_id[args.before] if args.before is not None else before
            after = by_id[args.after] if args.after is not None else after
        except KeyError as exc:
            raise ValueError("snapshot ID not found in selected database") from exc
        if dataset_key(before) != dataset_key(after):
            raise ValueError("selected snapshots use incomparable datasets")
        if datetime.fromisoformat(before["created_at"]) >= datetime.fromisoformat(after["created_at"]):
            raise ValueError("before must precede after")
    maps = []
    conn = sqlite3.connect(Path(db["path"]).as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        prefix = focus.rstrip("/") + "/"
        for snapshot in (before, after):
            found = {}
            for row in conn.execute("SELECT path,size_kb FROM entries WHERE snapshot_id=? AND "
                                    "(path=? OR substr(path,1,?)=?)",
                                    (snapshot["id"], focus, len(prefix), prefix)):
                if len(Path(row["path"]).relative_to(focus).parts) <= args.depth:
                    found[row["path"]] = row["size_kb"] * 1024
            maps.append(found)
    finally:
        conn.close()
    stats = {r["snapshot_id"]: r for r in db["volume_stats"]}
    notes = ["directory rows and physical capacity deltas are separate metrics",
             "APFS clone/shared blocks prevent converting directory bytes to reclaimable space",
             "use the actual interval shown here when no snapshot covers the requested window"]
    if corrupt:
        notes.append("other candidate databases contain unusable snapshot timestamps "
                     "and were reported as corrupt_history")
    return {"schema": SCHEMA, "kind": "history-summary", "status": "history_found",
            "db": db["path"], "db_schema": db["schema_version"], "focus": focus,
            "requested_days": args.days, "actual_days": (
                datetime.fromisoformat(after["created_at"]).timestamp()
                - datetime.fromisoformat(before["created_at"]).timestamp()) / 86400,
            "before": before, "after": after,
            "volume_stats": {"before": stats.get(before["id"]), "after": stats.get(after["id"])},
            "capacity_deltas": capacity_deltas(db["capacity_samples"], before["created_at"],
                                               after["created_at"]),
            "rows": diff_rows(*maps),
            "discovered_dbs": discovery["discovered_dbs"],
            "notes": notes}


def fathom(args):
    db = open_fathom(args.db)
    if args.command == "fathom-list":
        return fathom_payload(db)
    by_id = {r["id"]: r for r in db["snapshots"]}
    if args.before not in by_id or args.after not in by_id:
        raise ValueError("snapshot ID not found; run fathom-list")
    a, b = by_id[args.before], by_id[args.after]
    if dataset_key(a) != dataset_key(b) or any(v is None for v in dataset_key(a)):
        raise ValueError("incomparable or unknown Fathom dataset metadata")
    if datetime.fromisoformat(a["created_at"]) >= datetime.fromisoformat(b["created_at"]):
        raise ValueError("before must precede after")
    focus = absolute(args.focus)
    if not inside(focus, a["root"]):
        raise ValueError("focus outside snapshot root")
    maps = []
    conn = sqlite3.connect(Path(db["path"]).as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        prefix = focus.rstrip("/") + "/"
        for snapshot in (a, b):
            found = {}
            # Literal prefix; no LIKE wildcards from directory names.
            for row in conn.execute("SELECT path,size_kb FROM entries WHERE snapshot_id=? AND "
                                    "(path=? OR substr(path,1,?)=?)",
                                    (snapshot["id"], focus, len(prefix), prefix)):
                if len(Path(row["path"]).relative_to(focus).parts) <= args.depth:
                    found[row["path"]] = row["size_kb"] * 1024
            maps.append(found)
    finally:
        conn.close()
    return {"schema": SCHEMA, "kind": "fathom-diff", "db": db["path"], "db_schema": db["schema_version"],
            "before": a, "after": b, "focus": focus, "depth": args.depth,
            "rows": diff_rows(*maps), "notes": ["partial quality applies to recorded deltas",
            "cumulative rows overlap; do not sum; missing does not mean deletion",
            "historical allocated bytes are not reclaimable bytes"]}


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
    h = sub.add_parser("history", help="discover and summarize comparable local history first")
    h.add_argument("--db", action="append", help="explicit candidate; omit to auto-discover Fathom DBs")
    h.add_argument("--db-dir", help="also discover fathom.db files under this existing directory")
    h.add_argument("--before", type=positive)
    h.add_argument("--after", type=positive)
    h.add_argument("--focus", default="~")
    h.add_argument("--depth", type=positive, default=2)
    h.add_argument("--days", type=positive, default=7)
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
    for parser in (s, c, h, *[sub.choices[k] for k in ("fathom-list", "fathom-diff")]):
        parser.add_argument("--output", required=True, help="new JSON file, parent must exist")
    args = p.parse_args()
    try:
        out = Path(args.output).expanduser()
        if os.path.lexists(out):
            raise ValueError("output exists; refusing overwrite")
        if args.command == "scan" and any(inside(absolute(args.output), absolute(r)) for r in args.root):
            raise ValueError("output must be outside all scanned roots")
        result = (scan(args) if args.command == "scan" else compare(args) if args.command == "compare"
                  else history(args) if args.command == "history" else fathom(args))
        emit(result, args.output)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        print("disk-insight: " + str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
