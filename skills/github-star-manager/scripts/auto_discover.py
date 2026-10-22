#!/usr/bin/env python3
"""Daily opportunity discovery for local skills and starred repositories.

The command is deliberately deterministic and offline: it reads the local
snapshot, local skill documents and recorded feedback, then emits candidates
for an Agent/proactive scheduler to investigate. It never mutates target
skills or executes upstream code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))
from opportunity import existing_decisions  # noqa: E402
from star_query import emit, envelope, parse_dt  # noqa: E402
from star_tracker import StarTracker  # noqa: E402


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sha256_file(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def parse_frontmatter(text: str) -> Tuple[str, Optional[dict]]:
    if not text.startswith("---"):
        return "", None
    lines = text.splitlines()
    try:
        end = next(i for i in range(2, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return "", None

    # Avoid requiring PyYAML for this read-only path. The fields used here are
    # scalar frontmatter values emitted by this repository.
    metadata: Dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line or line.startswith((" ", "\t")):
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")
    return "\n".join(lines[end + 1:]), metadata


def task_lines(text: str) -> List[str]:
    # Task queues contain routine instructions as well as real goals. Use only
    # explicit goal/gap lines here; richer extraction remains an Agent decision.
    wanted = ("ready", "in_progress", "缺口", "目标")
    return [line.strip(" -#[]\t") for line in text.splitlines()
            if line.strip().startswith(("-", "#")) and any(w in line.lower() for w in wanted)][:20]


def git_activity(skill_dir: Path) -> dict:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    def run(*args: str) -> List[str]:
        try:
            proc = subprocess.run(
                ("git", "-C", str(skill_dir), *args), capture_output=True,
                text=True, timeout=3, env=env, check=False)
            return proc.stdout.splitlines() if proc.returncode == 0 else []
        except (OSError, subprocess.TimeoutExpired):
            return []

    subjects = run("log", "--since=30.days.ago", "--pretty=%s")
    files = run("log", "--since=30.days.ago", "--name-only", "--pretty=")
    return {
        "recent_commits": len(subjects),
        "recent_subjects": subjects[:10],
        "recent_paths": sorted({x for x in files if x})[:30],
    }


@dataclass
class ProjectTarget:
    project_id: str
    skill_path: Path
    skill_file: Path
    task_file: Optional[Path]
    description: str
    tasks: List[str]
    source_hashes: Dict[str, str]
    recent_commits: int
    recent_subjects: List[str]
    recent_paths: List[str]
    discovery_source: str

    def as_profile(self) -> dict:
        return {
            "project_id": self.project_id,
            "origin": "dynamic-skill-scan/1",
            "description": self.description,
            "needs": [self.description] + self.tasks[:5],
            "constraints": [
                "候选只是待研判信号；必须先核对目标 Skill 当前实现与上游证据",
                "允许结论为已有等价能力或不适用",
            ],
            "tasks": self.tasks,
            "source_ref": [str(self.skill_file), *([str(self.task_file)] if self.task_file else [])],
            "hashes": self.source_hashes,
            "activity": {
                "recent_commits": self.recent_commits,
                "recent_subjects": self.recent_subjects,
                "recent_paths": self.recent_paths,
            },
        }


def discover_projects(repo_root: Optional[Path] = None, project_id: Optional[str] = None) -> List[ProjectTarget]:
    root = (repo_root or Path(__file__).resolve().parents[3]).resolve()
    out: List[ProjectTarget] = []
    for skill_file in sorted((root / "skills").glob("*/SKILL.md")):
        ident = skill_file.parent.name
        if project_id and ident != project_id:
            continue
        try:
            text = skill_file.read_text(encoding="utf-8")
        except OSError:
            continue
        _body, meta = parse_frontmatter(text)
        if not meta or not meta.get("name") or not meta.get("description"):
            continue

        task_file = skill_file.parent / "TASKS.md"
        tasks: List[str] = []
        hashes: Dict[str, str] = {}
        if task_file.exists():
            try:
                task_text = task_file.read_text(encoding="utf-8")
                tasks = task_lines(task_text)
                digest = sha256_file(task_file)
                if digest:
                    hashes[str(task_file)] = digest
            except OSError:
                task_file = None
        digest = sha256_file(skill_file)
        if digest:
            hashes[str(skill_file)] = digest
        activity = git_activity(skill_file.parent)
        out.append(ProjectTarget(
            project_id=ident,
            skill_path=skill_file.parent,
            skill_file=skill_file,
            task_file=task_file if task_file and task_file.exists() else None,
            description=meta.get("description", ""),
            tasks=tasks,
            source_hashes=hashes,
            recent_commits=activity["recent_commits"],
            recent_subjects=activity["recent_subjects"],
            recent_paths=activity["recent_paths"],
            discovery_source="skills/*/SKILL.md + TASKS.md + git activity",
        ))
    return out


def query_terms(target: ProjectTarget) -> List[str]:
    stop = {"and", "for", "the", "with", "使用", "支持", "以及", "用于", "需要", "用户"}
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", target.description)
    return list(dict.fromkeys(w.lower() for w in words if w.lower() not in stop))[:12]


def match_repo(repo: dict, terms: Iterable[str]) -> List[str]:
    haystack = " ".join(filter(None, [
        repo.get("description") or "", repo.get("language") or "",
        " ".join(repo.get("topics") or []), repo.get("full_name") or "",
    ])).lower()
    return [term for term in terms if term and term in haystack]


def feedback_state(project_id: str, repo: str) -> dict:
    prior = existing_decisions(project_id, repo)
    decisions = [((x.get("decision") or {}).get("status"), x.get("_recorded_at")) for x in prior]
    rejected = [x for x in decisions if x[0] == "rejected"]
    open_proposed = [x for x in decisions if x[0] in ("researched", "experiment_proposed")]
    return {
        "records": len(prior),
        "last_decision": decisions[-1][0] if decisions else None,
        "last_recorded_at": decisions[-1][1] if decisions else None,
        "suppressed": bool(rejected or open_proposed),
        "suppression_reason": (
            "rejected" if rejected else
            "already-proposed" if open_proposed else
            None
        ),
    }


def target_changed(target: ProjectTarget) -> bool:
    return target.recent_commits > 0


def candidate_repo(repo: dict, target: ProjectTarget, reason: str, matched: List[str]) -> dict:
    return {
        "project_id": target.project_id,
        "repo": repo.get("full_name"),
        "signal": reason,
        "matched_terms": matched,
        "starred_at": repo.get("starred_at"),
        "pushed_at": repo.get("pushed_at"),
        "updated_at": repo.get("updated_at"),
        "snapshot_revision": {
            str(target.skill_file): target.source_hashes.get(str(target.skill_file)),
            **({str(target.task_file): target.source_hashes[str(target.task_file)]}
               if target.task_file and str(target.task_file) in target.source_hashes else {}),
        },
        "target_recent_commits": target.recent_commits,
        "target_recent_subjects": target.recent_subjects,
        "target_needs_sample": target.as_profile()["needs"][:6],
        "next_action": "核对目标 Skill 当前实现与仓库 README/代码证据，产出 opportunity.py 机会卡",
    }


def load_snapshot() -> Optional[dict]:
    tracker = StarTracker.__new__(StarTracker)
    tracker.CACHE_DIR = StarTracker.CACHE_DIR
    return StarTracker.load_latest(tracker)


def cmd_projects(args) -> int:
    targets = discover_projects(args.repo_root, args.project)
    items = [target.as_profile() for target in targets]
    return emit(envelope(items, coverage={
        "projects": len(items),
        "repo_root": str((args.repo_root or Path(__file__).resolve().parents[3]).resolve()),
    }))


def cmd_auto(args) -> int:
    snap = load_snapshot()
    if not snap:
        return emit(envelope([], errors=["无本地快照，请先运行 --init"]), 1)

    targets = discover_projects(args.repo_root, args.project)
    if args.project and not targets:
        return emit(envelope([], errors=[f"未发现项目 {args.project} 的 SKILL.md"]), 1)

    now = utcnow()
    recent_cutoff = now - timedelta(days=args.recent_days)
    update_cutoff = now - timedelta(days=args.update_days)
    warnings: List[str] = []
    if snap.get("snapshot_meta", {}).get("complete") is not True:
        warnings.append("快照不完整，自动机会可能遗漏")

    candidates = []
    seen = set()
    suppressed = []
    for target in targets:
        terms = query_terms(target)
        for repo in snap.get("repos", []):
            matched = match_repo(repo, terms)
            starred = parse_dt(repo.get("starred_at"))
            pushed = parse_dt(repo.get("pushed_at"))
            reasons = []
            if starred and starred >= recent_cutoff and matched:
                reasons.append("recent_star")
            if pushed and pushed >= update_cutoff and matched:
                reasons.append("recent_upstream_update")
            # A single generic word (e.g. "video") causes many false positives.
            # Ordinary project matches require two distinct target terms.
            if not matched or (not reasons and len(matched) < 2):
                continue
            key = (target.project_id, repo.get("full_name"))
            if key in seen:
                continue
            state = feedback_state(target.project_id, repo.get("full_name"))
            # Suppress an unchanged proposal unless the target changed materially.
            if state["suppressed"] and not (target_changed(target) or args.show_suppressed):
                suppressed.append({"project_id": target.project_id, "repo": repo.get("full_name"), **state})
                continue
            seen.add(key)
            candidates.append(candidate_repo(
                repo, target, "+".join(reasons) if reasons else "project_match",
                matched,
            ))

    candidates.sort(key=lambda x: (
        0 if "recent_star" in x["signal"] else 1,
        0 if "recent_upstream_update" in x["signal"] else 1,
        -len(x["matched_terms"]),
        -(parse_dt(x.get("starred_at")) or datetime.min.replace(tzinfo=timezone.utc)).timestamp(),
    ))
    truncated = len(candidates) > args.limit
    candidates = candidates[:args.limit]

    generated_at = now.isoformat()
    run = {
        "schema_version": "auto-opportunity-run/1",
        "generated_at": generated_at,
        "snapshot_id": snap.get("timestamp"),
        "snapshot_complete": snap.get("snapshot_meta", {}).get("complete"),
        "projects": [
            {"project_id": t.project_id, "source_ref": t.as_profile()["source_ref"],
             "hashes": t.source_hashes, "recent_commits": t.recent_commits}
            for t in targets
        ],
        "candidates": candidates,
        "suppressed": suppressed,
        "coverage": {
            "repos": len(snap.get("repos", [])),
            "projects": len(targets),
            "recent_days": args.recent_days,
            "update_days": args.update_days,
            "matched": len(candidates) + len(suppressed),
            "returned": len(candidates),
            "suppressed": len(suppressed),
            "truncated": truncated,
        },
    }
    if args.write:
        out_dir = StarTracker.CACHE_DIR / "auto-opportunities"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = now.strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"{stamp}.json"
        seq = 0
        while out_path.exists():
            seq += 1
            out_path = out_dir / f"{stamp}_{seq}.json"
        out_path.write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        out_path = None

    result = envelope(candidates, snapshot=snap, coverage=run["coverage"], warnings=warnings, extra={
        "projects": run["projects"],
        "suppressed": suppressed,
        "run_path": str(out_path) if out_path else None,
        "usage_note": "结果是待研判候选，不是适用性结论；须核对目标实现与上游证据后用 opportunity.py record。",
    })
    return emit(result)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="自动发现本地 Skill 与 GitHub Star 的潜在机会（只读；--write 才落盘运行包）")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("projects", help="动态发现本地 Skill 项目目标")
    p.add_argument("--project", help="只返回指定项目")
    p.add_argument("--repo-root", type=Path, help="monorepo 根（默认按脚本位置推导）")
    p.set_defaults(func=cmd_projects)

    p = sub.add_parser("auto-discover", help="产出每日机会候选队列")
    p.add_argument("--project", help="只分析指定项目")
    p.add_argument("--recent-days", type=int, default=14, help="新 Star 窗口（默认 14 天）")
    p.add_argument("--update-days", type=int, default=7, help="上游 pushed_at 窗口（默认 7 天）")
    p.add_argument("--limit", type=int, default=50, help="返回候选上限（默认 50）")
    p.add_argument("--show-suppressed", action="store_true", help="包含已拒绝/已提议候选")
    p.add_argument("--repo-root", type=Path, help="monorepo 根（默认按脚本位置推导）")
    p.add_argument("--write", action="store_true", help="写入 output/auto-opportunities/（唯一本地写）")
    p.set_defaults(func=cmd_auto)

    args = parser.parse_args()
    try:
        return args.func(args)
    except BrokenPipeError:
        return 0
    except Exception as exc:
        print(f"自动发现失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return emit(envelope([], errors=[f"{type(exc).__name__}: {exc}"]), 1)


if __name__ == "__main__":
    sys.exit(main())
