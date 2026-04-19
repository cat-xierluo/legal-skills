#!/usr/bin/env python3
"""执行归档服务。"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE_DIR = SKILL_ROOT / "archive"


def sanitize_name(value: str, max_len: int = 48) -> str:
    text = re.sub(r"\s+", " ", value.strip())
    text = re.sub(r'[\\/:*?"<>|]+', "_", text)
    text = text.strip(" ._")
    if not text:
        text = "review"
    return text[:max_len]


def ensure_unique_dir(base_dir: Path, folder_name: str) -> Path:
    candidate = base_dir / folder_name
    index = 1
    while candidate.exists():
        candidate = base_dir / f"{folder_name}_{index:02d}"
        index += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def resolve_archive_display_name(
    plan_meta: dict[str, Any],
    output_docx: Path,
) -> str:
    return (
        str(plan_meta.get("contract_name") or "").strip()
        or str(plan_meta.get("title") or "").strip()
        or output_docx.stem
    )


def create_archive_run_dir(
    archive_dir: Path,
    plan_meta: dict[str, Any],
    output_docx: Path,
) -> Path:
    display_name = resolve_archive_display_name(plan_meta, output_docx)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{ts}_{sanitize_name(display_name)}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    return ensure_unique_dir(archive_dir, folder_name)


def _copy_if_needed(source: Path, destination: Path) -> None:
    if source.resolve() == destination.resolve():
        return
    shutil.copy2(source, destination)


def archive_run(
    archive_dir: Path,
    input_docx: Path,
    plan_path: Path,
    output_docx: Path,
    report_path: Path,
    report_docx_path: Path,
    log_path: Path,
    execution_summary: dict[str, Any],
    include_input: bool = True,
    run_dir: Path | None = None,
) -> Path:
    meta = execution_summary.get("plan_meta", {})
    if run_dir is None:
        run_dir = create_archive_run_dir(
            archive_dir=archive_dir,
            plan_meta=meta,
            output_docx=output_docx,
        )

    if include_input:
        _copy_if_needed(input_docx, run_dir / f"input{input_docx.suffix.lower()}")
    _copy_if_needed(plan_path, run_dir / "review-plan.json")
    _copy_if_needed(output_docx, run_dir / output_docx.name)
    _copy_if_needed(report_path, run_dir / report_path.name)
    _copy_if_needed(report_docx_path, run_dir / report_docx_path.name)
    _copy_if_needed(log_path, run_dir / log_path.name)

    manifest = {
        "archived_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "archive_dir": str(run_dir),
        "files": {
            "input_docx": f"input{input_docx.suffix.lower()}" if include_input else None,
            "plan": "review-plan.json",
            "output_docx": output_docx.name,
            "report": report_path.name,
            "report_docx": report_docx_path.name,
            "execution_log": log_path.name,
        },
        "summary": {
            "applied": execution_summary.get("applied", 0),
            "failed": execution_summary.get("failed", 0),
            "skipped": execution_summary.get("skipped", 0),
        },
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return run_dir
