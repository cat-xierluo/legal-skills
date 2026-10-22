#!/usr/bin/env python3
"""Offline regression tests for dynamic project and daily opportunity discovery."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SCRIPTS = BASE / "scripts"
sys.path.insert(0, str(SCRIPTS))

import auto_discover as ad  # noqa: E402
import star_tracker  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


def capture(func, *args, **kwargs):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = func(*args, **kwargs)
    try:
        data = json.loads(out.getvalue())
    except ValueError:
        data = None
    return rc, data, err.getvalue()


def write_skill(root: Path, name: str, description: str, task: str | None = None):
    skill = root / "skills" / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# Demo\n", encoding="utf-8")
    if task is not None:
        (skill / "TASKS.md").write_text(task, encoding="utf-8")
    return skill


def init_git(root: Path):
    subprocess.run(("git", "-C", str(root), "init", "-q"), check=True)
    subprocess.run(("git", "-C", str(root), "config", "user.email", "test@example.test"), check=True)
    subprocess.run(("git", "-C", str(root), "config", "user.name", "Test"), check=True)


def commit(root: Path, message: str):
    subprocess.run(("git", "-C", str(root), "add", "."), check=True)
    subprocess.run(("git", "-C", str(root), "commit", "-m", message, "-q"), check=True)


class Args:
    def __init__(self, **kwargs):
        defaults = {
            "project": None, "repo_root": None, "recent_days": 14,
            "update_days": 7, "limit": 50, "show_suppressed": False,
            "write": False,
        }
        defaults.update(kwargs)
        for key, value in defaults.items():
            setattr(self, key, value)


def write_snapshot(path: Path, repos: list, complete=True):
    path.write_text(json.dumps({
        "schema_version": 2,
        "timestamp": "2026-10-22T10:00:00Z",
        "total_count": len(repos),
        "snapshot_meta": {"account_id": "tester", "complete": complete,
                          "completeness": "complete" if complete else "partial"},
        "repos": repos,
    }, ensure_ascii=False), encoding="utf-8")


def repo(full_name, *, starred=None, pushed=None, desc="", topics=None):
    now = datetime.now(timezone.utc)
    return {
        "full_name": full_name,
        "description": desc,
        "language": "Python",
        "topics": topics or [],
        "stargazers_count": 12,
        "starred_at": (now - timedelta(days=starred)).isoformat() if starred is not None else None,
        "pushed_at": (now - timedelta(days=pushed)).isoformat() if pushed is not None else "2000-01-01T00:00:00Z",
        "updated_at": (now - timedelta(days=pushed or 9999)).isoformat(),
    }


print("\n[projects] dynamic local target discovery")
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    write_skill(root, "code-video", "video subtitle timeline rendering")
    invalid = write_skill(root, "no-meta", "missing frontmatter")
    (invalid / "SKILL.md").write_text("# No frontmatter\n", encoding="utf-8")
    rc, data, _ = capture(ad.cmd_projects, Args(repo_root=root))
    check("returns only valid skills", rc == 0 and [x["project_id"] for x in data["items"]] == ["code-video"])
    profile = data["items"][0]
    check("profile has source hash", len(profile["hashes"]) == 1)
    check("profile carries description as need", "video subtitle timeline rendering" in profile["needs"])

print("\n[auto-discover] signals, updates and partial coverage")
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    write_skill(root, "code-video", "video subtitle timeline rendering", "# Tasks\n- TODO subtitle rendering gap\n")
    init_git(root)
    commit(root, "initial")
    output = root / "output"
    output.mkdir()
    star_tracker.StarTracker.CACHE_DIR = output
    star_tracker.StarTracker.CONFIG_DIR = output
    write_snapshot(output / "original_latest.json", [
        repo("demo/subtitle", starred=2, pushed=2, desc="subtitle timeline renderer"),
        repo("demo/video-old", starred=80, pushed=100, desc="video renderer"),
        repo("demo/unknown-time", starred=None, pushed=2, desc="subtitle timeline"),
    ])
    rc, data, err = capture(ad.cmd_auto, Args(repo_root=root))
    names = [(x["project_id"], x["repo"], x["signal"]) for x in data["items"]]
    check("recent star and matched repo returned", ("code-video", "demo/subtitle", "recent_star+recent_upstream_update") in names, str(names))
    check("unknown star time still matches by project terms",
          any(x["repo"] == "demo/unknown-time" and x["signal"] == "recent_upstream_update" for x in data["items"]), str(names))
    check("unmatched old repo omitted", all(x["repo"] != "demo/video-old" for x in data["items"]))
    check("coverage counts projects and repos", data["coverage"]["projects"] == 1 and data["coverage"]["repos"] == 3)

    # Partial snapshot must be visible in envelope and not silently treated as complete.
    write_snapshot(output / "original_latest.json", [repo("demo/subtitle", starred=2, desc="subtitle")], complete=False)
    rc, data, _ = capture(ad.cmd_auto, Args(repo_root=root))
    check("partial snapshot warns", data["status"] == "partial" and any("不完整" in w for w in data["warnings"]))

print("\n[auto-discover] feedback suppression and reopen")
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    write_skill(root, "code-video", "video subtitle timeline rendering")
    output = root / "output"
    output.mkdir()
    star_tracker.StarTracker.CACHE_DIR = output
    star_tracker.StarTracker.CONFIG_DIR = output
    write_snapshot(output / "original_latest.json", [
        repo("demo/subtitle", starred=2, desc="subtitle timeline renderer")
    ])
    feedback = output / "feedback"
    feedback.mkdir()
    card = {
        "target": {"project_id": "code-video"}, "signal": {"repo": "demo/subtitle"},
        "decision": {"status": "experiment_proposed"}, "_recorded_at": "2026-10-21T00:00:00Z",
    }
    (feedback / "code-video__demo__subtitle__x.json").write_text(json.dumps(card), encoding="utf-8")
    rc, data, _ = capture(ad.cmd_auto, Args(repo_root=root))
    check("unchanged proposal suppressed", not data["items"] and data["suppressed"][0]["suppression_reason"] == "already-proposed")

    init_git(root)
    commit(root, "target requirement changed")
    rc, data, _ = capture(ad.cmd_auto, Args(repo_root=root))
    check("target activity reopens candidate", len(data["items"]) == 1 and data["items"][0]["target_recent_commits"] == 1)

print("\n[auto-discover] explicit write and no-snapshot failure")
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    write_skill(root, "code-video", "video subtitle timeline rendering")
    output = root / "output"
    output.mkdir()
    star_tracker.StarTracker.CACHE_DIR = output
    star_tracker.StarTracker.CONFIG_DIR = output
    rc, data, _ = capture(ad.cmd_auto, Args(repo_root=root))
    check("missing snapshot returns non-zero", rc == 1 and "无本地快照" in data["errors"][0])

    write_snapshot(output / "original_latest.json", [repo("demo/subtitle", starred=1, desc="subtitle")])
    rc, data, _ = capture(ad.cmd_auto, Args(repo_root=root, write=True))
    run_path = Path(data["run_path"])
    check("write creates run package", run_path.exists() and run_path.parent == output / "auto-opportunities")
    saved = json.loads(run_path.read_text(encoding="utf-8"))
    check("run package binds target hashes", bool(saved["projects"][0]["hashes"]))

print("\n[auto-discover] deterministic sorting and truncation")
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    write_skill(root, "code-video", "video subtitle timeline rendering")
    output = root / "output"
    output.mkdir()
    star_tracker.StarTracker.CACHE_DIR = output
    star_tracker.StarTracker.CONFIG_DIR = output
    write_snapshot(output / "original_latest.json", [
        repo("demo/old-match", starred=60, desc="subtitle timeline renderer"),
        repo("demo/new-match", starred=1, desc="subtitle timeline renderer"),
    ])
    rc, data, _ = capture(ad.cmd_auto, Args(repo_root=root, limit=1))
    check("truncation visible and recent star first",
          data["items"][0]["repo"] == "demo/new-match" and data["coverage"]["truncated"] is True)

print(f"\n结果: {PASS} 通过 / {FAIL} 失败")
sys.exit(0 if FAIL == 0 else 1)
