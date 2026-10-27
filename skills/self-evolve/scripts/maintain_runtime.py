#!/usr/bin/env python3
"""
Inspect and organize Self Evolve runtime files.

The script is conservative by default:
- report mode only reads metadata
- organize mode is dry-run unless --apply is passed
- no deletion or compression is performed
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from self_evolve_paths import RUNTIME_ROOT, assert_runtime_ready


STATE_ROOT = RUNTIME_ROOT
SESSION_SUMMARY_DIR = STATE_ROOT / "session-summaries"


def format_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def iter_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [path for path in root.rglob("*") if path.is_file()]


def count_lines(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as file:
            return sum(1 for _ in file)
    except OSError:
        return 0


def month_from_summary_name(path: Path) -> str:
    match = re.search(r"_(\d{6})_", path.name)
    if match:
        return match.group(1)[:4]
    return "unknown"


def collect_report() -> dict[str, Any]:
    top_dirs = []
    if STATE_ROOT.exists():
        for child in sorted(STATE_ROOT.iterdir(), key=lambda item: item.name):
            if child.is_dir():
                files = iter_files(child)
                size = sum(file_size(path) for path in files)
                top_dirs.append(
                    {
                        "name": child.name,
                        "files": len(files),
                        "bytes": size,
                        "human_size": format_bytes(size),
                    }
                )
            elif child.is_file():
                top_dirs.append(
                    {
                        "name": child.name,
                        "files": 1,
                        "bytes": file_size(child),
                        "human_size": format_bytes(file_size(child)),
                    }
                )

    jsonl_logs = []
    for path in sorted(STATE_ROOT.rglob("*.jsonl")) if STATE_ROOT.exists() else []:
        jsonl_logs.append(
            {
                "path": str(path.relative_to(STATE_ROOT)),
                "bytes": file_size(path),
                "human_size": format_bytes(file_size(path)),
                "lines": count_lines(path),
            }
        )

    flat_summaries = sorted(SESSION_SUMMARY_DIR.glob("*.json")) if SESSION_SUMMARY_DIR.exists() else []
    monthly_summary_dirs = [
        path
        for path in sorted(SESSION_SUMMARY_DIR.iterdir()) if path.is_dir() and re.match(r"^\d{4}$", path.name)
    ] if SESSION_SUMMARY_DIR.exists() else []
    monthly_summary_counts = {
        path.name: len(list(path.glob("*.json")))
        for path in monthly_summary_dirs
    }

    recommendations = []
    if flat_summaries:
        recommendations.append("session-summaries 根目录仍有平铺 JSON，建议按 YYMM 分桶整理。")
    if any(item["bytes"] > 10 * 1024 * 1024 for item in jsonl_logs):
        recommendations.append("存在超过 10MB 的 JSONL 日志，后续应做按月轮转。")
    if not recommendations:
        recommendations.append("当前 runtime 结构正常，暂不需要整理。")

    return {
        "runtime_root": str(STATE_ROOT),
        "total_files": len(iter_files(STATE_ROOT)),
        "total_bytes": sum(file_size(path) for path in iter_files(STATE_ROOT)),
        "top_level": top_dirs,
        "jsonl_logs": jsonl_logs,
        "session_summaries": {
            "flat_files": len(flat_summaries),
            "monthly_dirs": monthly_summary_counts,
        },
        "recommendations": recommendations,
    }


def organize_session_summaries(apply: bool) -> dict[str, Any]:
    SESSION_SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    actions = []
    moved = 0
    conflicts = 0
    flat_files = sorted(SESSION_SUMMARY_DIR.glob("*.json"))

    for source in flat_files:
        month = month_from_summary_name(source)
        target = SESSION_SUMMARY_DIR / month / source.name
        action = {
            "source": str(source.relative_to(STATE_ROOT)),
            "target": str(target.relative_to(STATE_ROOT)),
            "status": "planned",
        }
        if target.exists():
            action["status"] = "conflict_exists"
            conflicts += 1
            actions.append(action)
            continue
        if apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            os.chmod(target, 0o600)
            action["status"] = "moved"
            moved += 1
        actions.append(action)

    return {
        "apply": apply,
        "planned": len(flat_files),
        "moved": moved,
        "conflicts": conflicts,
        "actions": actions[:200],
        "truncated_actions": max(0, len(actions) - 200),
    }


def print_report(report: dict[str, Any]) -> None:
    print("Self Evolve runtime report")
    print(f"- runtime_root: {report['runtime_root']}")
    print(f"- total_files: {report['total_files']}")
    print(f"- total_size: {format_bytes(int(report['total_bytes']))}")
    print("")
    print("Top level:")
    for item in report["top_level"]:
        print(f"- {item['name']}: {item['files']} files, {item['human_size']}")
    print("")
    print("Session summaries:")
    summaries = report["session_summaries"]
    print(f"- flat_files: {summaries['flat_files']}")
    for month, count in summaries["monthly_dirs"].items():
        print(f"- {month}: {count} files")
    print("")
    print("Recommendations:")
    for item in report["recommendations"]:
        print(f"- {item}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect and organize Self Evolve runtime files.")
    parser.add_argument("--report", action="store_true", help="Print runtime size and layout report")
    parser.add_argument("--organize-session-summaries", action="store_true", help="Move flat session summaries into YYMM folders")
    parser.add_argument("--apply", action="store_true", help="Apply organizing actions. Without this flag, organize mode is dry-run")
    parser.add_argument("--json", action="store_true", help="Print JSON result")
    args = parser.parse_args()
    try:
        assert_runtime_ready()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    result: dict[str, Any] = {}
    if args.organize_session_summaries:
        result["organize_session_summaries"] = organize_session_summaries(args.apply)

    if args.report or not result:
        result["report"] = collect_report()

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if "organize_session_summaries" in result:
            organized = result["organize_session_summaries"]
            mode = "apply" if organized["apply"] else "dry-run"
            print(f"Organize session summaries ({mode})")
            print(f"- planned: {organized['planned']}")
            print(f"- moved: {organized['moved']}")
            print(f"- conflicts: {organized['conflicts']}")
            if organized["truncated_actions"]:
                print(f"- hidden actions: {organized['truncated_actions']}")
            print("")
        if "report" in result:
            print_report(result["report"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
