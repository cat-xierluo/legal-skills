#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "Pillow>=10.0.0",
# ]
# ///

"""私有视频语料的可复跑基线评测；公开汇总不保存路径、原文或标注时间点。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "video-screenshot-benchmark/v1"
WORKSPACE_SCHEMA_VERSION = "video-screenshot-benchmark-workspace/v1"
STATE_SCHEMA_VERSION = "video-screenshot-benchmark-state/v1"
SUMMARY_SCHEMA_VERSION = "video-screenshot-benchmark-summary/v1"
CASE_ID_RE = re.compile(r"^CASE-[0-9]{3}$")
SUPPORTED_CATEGORIES = {
    "xiaohongshu",
    "wechat_chat",
    "product_work",
    "qualification_document",
    "long_scroll",
    "short_video",
    "damaged_video",
}
SUPPORTED_PROFILES = {"visual", "ocr"}
SKILL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_ROOT.parent.parent
EXTRACT_SCRIPT = Path(__file__).resolve().parent / "extract.py"


class BenchmarkError(RuntimeError):
    """可直接展示给用户的基线评测错误。"""


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_bytes(_json_bytes(value))
    temp.replace(path)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _require_private_path(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if _is_within(resolved, REPO_ROOT):
        raise BenchmarkError(
            f"{label} 必须位于 Git 仓库之外，避免真实视频路径或评测产物进入版本库: {resolved}"
        )
    return resolved


def _as_number(value: object, label: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BenchmarkError(f"{label} 必须是数字")
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        raise BenchmarkError(f"{label} 必须是不小于 {minimum:g} 的有限数字")
    return number


def _validate_intervals(items: object, label: str, *, require_id: bool = True) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise BenchmarkError(f"{label} 必须是数组")
    validated: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            raise BenchmarkError(f"{label}[{index}] 必须是对象")
        item_id = str(raw.get("id") or "")
        if require_id and not re.fullmatch(r"[A-Z]+-[0-9]{3}", item_id):
            raise BenchmarkError(f"{label}[{index}].id 必须采用 K-001/T-001/P-001 这类匿名编号")
        if item_id in seen_ids:
            raise BenchmarkError(f"{label} 出现重复 id: {item_id}")
        seen_ids.add(item_id)
        start = _as_number(raw.get("start_seconds"), f"{label}[{index}].start_seconds")
        end = _as_number(raw.get("end_seconds"), f"{label}[{index}].end_seconds")
        if end < start:
            raise BenchmarkError(f"{label}[{index}] 的结束时间不能早于开始时间")
        normalized = {
            "id": item_id,
            "start_seconds": start,
            "end_seconds": end,
        }
        if "max_selected" in raw:
            maximum = raw["max_selected"]
            if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 1:
                raise BenchmarkError(f"{label}[{index}].max_selected 必须是正整数")
            normalized["max_selected"] = maximum
        validated.append(normalized)
    return validated


def _validate_manifest(raw: object, *, check_files: bool) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
        raise BenchmarkError(f"manifest.schema_version 必须是 {SCHEMA_VERSION}")
    acceptance = raw.get("acceptance") or {}
    if not isinstance(acceptance, dict):
        raise BenchmarkError("manifest.acceptance 必须是对象")
    min_categories = acceptance.get("min_distinct_categories", 5)
    if isinstance(min_categories, bool) or not isinstance(min_categories, int) or not 1 <= min_categories <= len(SUPPORTED_CATEGORIES):
        raise BenchmarkError("acceptance.min_distinct_categories 必须是 1—7 的整数")
    required_profiles = acceptance.get("required_profiles", ["visual", "ocr"])
    if not isinstance(required_profiles, list) or not required_profiles:
        raise BenchmarkError("acceptance.required_profiles 必须是非空数组")
    required_profiles = [str(item) for item in required_profiles]
    unknown_profiles = sorted(set(required_profiles) - SUPPORTED_PROFILES)
    if unknown_profiles:
        raise BenchmarkError(f"未知 required_profiles: {', '.join(unknown_profiles)}")

    cases = raw.get("cases")
    if not isinstance(cases, list) or not cases:
        raise BenchmarkError("manifest.cases 必须是非空数组")
    normalized_cases: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    for index, case in enumerate(cases, start=1):
        label = f"cases[{index}]"
        if not isinstance(case, dict):
            raise BenchmarkError(f"{label} 必须是对象")
        case_id = str(case.get("case_id") or "")
        if not CASE_ID_RE.fullmatch(case_id):
            raise BenchmarkError(f"{label}.case_id 必须采用 CASE-001 这类匿名编号")
        if case_id in seen_case_ids:
            raise BenchmarkError(f"重复 case_id: {case_id}")
        seen_case_ids.add(case_id)
        category = str(case.get("category") or "")
        if category not in SUPPORTED_CATEGORIES:
            raise BenchmarkError(f"{label}.category 不受支持: {category}")
        video_path_text = str(case.get("video_path") or "")
        video_path = Path(video_path_text).expanduser()
        if not video_path.is_absolute():
            raise BenchmarkError(f"{label}.video_path 必须是本机绝对路径")
        if check_files and (not video_path.is_file() or video_path.is_symlink()):
            raise BenchmarkError(f"{label}.video_path 不存在、不是普通文件或是符号链接")
        expected_outcome = str(case.get("expected_outcome") or "success")
        if expected_outcome not in {"success", "failure"}:
            raise BenchmarkError(f"{label}.expected_outcome 只能是 success 或 failure")
        annotations = case.get("annotations") or {}
        if not isinstance(annotations, dict):
            raise BenchmarkError(f"{label}.annotations 必须是对象")
        must_keep = _validate_intervals(annotations.get("must_keep", []), f"{label}.annotations.must_keep")
        transitions = _validate_intervals(annotations.get("transitions", []), f"{label}.annotations.transitions")
        page_windows = _validate_intervals(annotations.get("page_windows", []), f"{label}.annotations.page_windows")
        for page_index, item in enumerate(page_windows, start=1):
            if "max_selected" not in item:
                raise BenchmarkError(f"{label}.annotations.page_windows[{page_index}] 缺少 max_selected")
        if expected_outcome == "success" and not must_keep:
            raise BenchmarkError(f"{label} 是成功样本，至少需要一个候选外 must_keep 标注")
        budget = case.get("budget") or {}
        if not isinstance(budget, dict):
            raise BenchmarkError(f"{label}.budget 必须是对象")
        normalized_cases.append(
            {
                "case_id": case_id,
                "category": category,
                "video_path": str(video_path),
                "expected_outcome": expected_outcome,
                "annotations": {
                    "must_keep": must_keep,
                    "transitions": transitions,
                    "page_windows": page_windows,
                },
                "budget": {
                    "max_frames_per_minute": _as_number(
                        budget.get("max_frames_per_minute", 30.0),
                        f"{label}.budget.max_frames_per_minute",
                        minimum=0.01,
                    ),
                    "max_runtime_seconds": _as_number(
                        budget.get("max_runtime_seconds", 1800.0),
                        f"{label}.budget.max_runtime_seconds",
                        minimum=0.01,
                    ),
                },
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "acceptance": {
            "min_distinct_categories": min_categories,
            "required_profiles": required_profiles,
        },
        "cases": normalized_cases,
    }


def _load_manifest(path: Path, *, check_files: bool) -> tuple[dict[str, Any], str]:
    manifest_path = _require_private_path(path, "manifest")
    try:
        payload = manifest_path.read_bytes()
        raw = json.loads(payload)
    except FileNotFoundError as exc:
        raise BenchmarkError(f"manifest 不存在: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise BenchmarkError(f"manifest 不是有效 JSON: {exc}") from exc
    return _validate_manifest(raw, check_files=check_files), _sha256_bytes(payload)


def _profiles(value: str) -> list[str]:
    values = [item.strip() for item in value.split(",") if item.strip()]
    if not values:
        raise argparse.ArgumentTypeError("profiles 不能为空")
    unknown = sorted(set(values) - SUPPORTED_PROFILES)
    if unknown:
        raise argparse.ArgumentTypeError(f"未知 profile: {', '.join(unknown)}")
    return list(dict.fromkeys(values))


def _template() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "acceptance": {
            "min_distinct_categories": 5,
            "required_profiles": ["visual", "ocr"],
        },
        "cases": [
            {
                "case_id": "CASE-001",
                "category": "wechat_chat",
                "video_path": "/ABSOLUTE/LOCAL/PATH/recording.mp4",
                "expected_outcome": "success",
                "annotations": {
                    "must_keep": [
                        {"id": "K-001", "start_seconds": 1.0, "end_seconds": 2.5}
                    ],
                    "transitions": [
                        {"id": "T-001", "start_seconds": 2.6, "end_seconds": 3.1}
                    ],
                    "page_windows": [
                        {
                            "id": "P-001",
                            "start_seconds": 1.0,
                            "end_seconds": 2.5,
                            "max_selected": 1,
                        }
                    ],
                },
                "budget": {
                    "max_frames_per_minute": 30.0,
                    "max_runtime_seconds": 1800.0,
                },
            }
        ],
    }


def _workspace(workspace_arg: Path, manifest_sha256: str) -> Path:
    workspace = _require_private_path(workspace_arg, "workspace")
    if workspace.exists() and workspace.is_symlink():
        raise BenchmarkError("workspace 不能是符号链接")
    workspace.mkdir(parents=True, exist_ok=True)
    marker_path = workspace / "_benchmark_workspace.json"
    allowed = {"_benchmark_workspace.json", "benchmark_state.json", "benchmark_summary.json", "runs"}
    actual = {item.name for item in workspace.iterdir()}
    if marker_path.exists():
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if marker.get("schema_version") != WORKSPACE_SCHEMA_VERSION:
            raise BenchmarkError("workspace 所有权标记版本不受支持")
        if marker.get("manifest_sha256") != manifest_sha256:
            raise BenchmarkError("workspace 已绑定另一份 manifest，请使用新目录")
        unknown = sorted(actual - allowed)
        if unknown:
            raise BenchmarkError(f"workspace 含未知文件，拒绝覆盖: {', '.join(unknown)}")
    elif actual:
        raise BenchmarkError("workspace 非空且缺少本工具所有权标记，拒绝使用")
    else:
        _atomic_write_json(
            marker_path,
            {
                "schema_version": WORKSPACE_SCHEMA_VERSION,
                "manifest_sha256": manifest_sha256,
                "source_paths_stored": False,
            },
        )
    runs_root = workspace / "runs"
    if runs_root.exists() and runs_root.is_symlink():
        raise BenchmarkError("workspace/runs 不能是符号链接")
    runs_root.mkdir(exist_ok=True)
    return workspace


def _empty_state(manifest_sha256: str) -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "manifest_sha256": manifest_sha256,
        "source_paths_stored": False,
        "runs": {},
    }


def _load_state(workspace: Path, manifest_sha256: str) -> dict[str, Any]:
    path = workspace / "benchmark_state.json"
    if not path.exists():
        return _empty_state(manifest_sha256)
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema_version") != STATE_SCHEMA_VERSION or state.get("manifest_sha256") != manifest_sha256:
        raise BenchmarkError("benchmark_state.json 与当前 manifest 不匹配")
    if state.get("source_paths_stored") is not False or not isinstance(state.get("runs"), dict):
        raise BenchmarkError("benchmark_state.json 结构无效")
    return state


def _run_key(case_id: str, profile: str) -> str:
    return f"{case_id}:{profile}"


def _diagnostic(result: subprocess.CompletedProcess[str], case: dict[str, Any], output: Path) -> str:
    text = ((result.stderr or "") + "\n" + (result.stdout or "")).strip()
    for sensitive in (case["video_path"], str(output), str(output.parent), str(output.parents[2])):
        if sensitive:
            text = text.replace(sensitive, "<private-path>")
    return "\n".join(text.splitlines()[-8:])[-1200:]


def _execute_case(case: dict[str, Any], profile: str, output: Path) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.parent.is_symlink():
        raise BenchmarkError("case/profile 输出父目录不能是符号链接")
    command = [
        sys.executable,
        str(EXTRACT_SCRIPT),
        "-i",
        case["video_path"],
        "-o",
        str(output),
        "--no-archive",
    ]
    if profile == "ocr":
        command.append("--ocr-dedup")
    started = time.monotonic()
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    elapsed = round(time.monotonic() - started, 3)
    diagnostic = _diagnostic(result, case, output)
    expected_outcome = case["expected_outcome"]
    if expected_outcome == "failure":
        status = "expected_failure_observed" if result.returncode != 0 else "unexpected_success"
        return {
            "status": status,
            "returncode": result.returncode,
            "runtime_seconds": elapsed,
            "output_relative": str(output.relative_to(output.parents[2])),
            "diagnostic": diagnostic,
        }
    if result.returncode != 0:
        return {
            "status": "failed",
            "returncode": result.returncode,
            "runtime_seconds": elapsed,
            "output_relative": str(output.relative_to(output.parents[2])),
            "diagnostic": diagnostic,
        }
    report_path = output / "_report.json"
    if not report_path.is_file():
        return {
            "status": "failed_missing_report",
            "returncode": result.returncode,
            "runtime_seconds": elapsed,
            "output_relative": str(output.relative_to(output.parents[2])),
            "diagnostic": "抽帧器返回成功但未生成 _report.json",
        }
    report = json.loads(report_path.read_text(encoding="utf-8"))
    actual_mode = ((report.get("options") or {}).get("content_delta_mode"))
    expected_mode = "ocr+visual" if profile == "ocr" else "visual_only"
    if actual_mode != expected_mode:
        return {
            "status": "failed_profile_downgrade",
            "returncode": result.returncode,
            "runtime_seconds": elapsed,
            "output_relative": str(output.relative_to(output.parents[2])),
            "diagnostic": "OCR profile 未实际启用 OCR；请用 --with rapidocr-onnxruntime 运行 benchmark.py",
        }
    return {
        "status": "completed",
        "returncode": result.returncode,
        "runtime_seconds": elapsed,
        "output_relative": str(output.relative_to(output.parents[2])),
    }


def _selected_times(report: dict[str, Any]) -> list[float]:
    frames = report.get("frames")
    if not isinstance(frames, list):
        raise BenchmarkError("_report.json 缺少 frames 数组")
    times: list[float] = []
    for index, frame in enumerate(frames, start=1):
        if not isinstance(frame, dict):
            raise BenchmarkError(f"_report.json frames[{index}] 无效")
        times.append(_as_number(frame.get("capture_time_seconds"), f"frames[{index}].capture_time_seconds"))
    return sorted(times)


def _in_interval(value: float, item: dict[str, Any]) -> bool:
    return item["start_seconds"] <= value <= item["end_seconds"]


def _score_case(case: dict[str, Any], run: dict[str, Any], workspace: Path) -> dict[str, Any]:
    if case["expected_outcome"] == "failure":
        passed = run.get("status") == "expected_failure_observed"
        return {
            "status": "passed" if passed else "failed",
            "expected_failure_observed": passed,
            "runtime_seconds": run.get("runtime_seconds"),
        }
    if run.get("status") != "completed":
        return {"status": str(run.get("status") or "not_run")}
    relative = Path(str(run.get("output_relative") or ""))
    output = (workspace / relative).resolve()
    if not _is_within(output, workspace) or output.is_symlink():
        raise BenchmarkError("benchmark_state.json 的 output_relative 越界或指向符号链接")
    report = json.loads((output / "_report.json").read_text(encoding="utf-8"))
    selected = _selected_times(report)
    duration = _as_number(report.get("duration_seconds"), "_report.json.duration_seconds", minimum=0.001)
    annotations = case["annotations"]
    must_keep = annotations["must_keep"]
    hits = sum(1 for item in must_keep if any(_in_interval(value, item) for value in selected))
    transition_count = sum(
        1 for value in selected if any(_in_interval(value, item) for item in annotations["transitions"])
    )
    duplicate_excess = 0
    for item in annotations["page_windows"]:
        count = sum(1 for value in selected if _in_interval(value, item))
        duplicate_excess += max(0, count - int(item["max_selected"]))
    selected_count = len(selected)
    frames_per_minute = selected_count * 60.0 / duration
    runtime_seconds = float(run.get("runtime_seconds") or 0.0)
    budget = case["budget"]
    return {
        "status": "scored",
        "selected_count": selected_count,
        "duration_seconds": round(duration, 3),
        "must_keep_total": len(must_keep),
        "must_keep_hit": hits,
        "must_keep_recall": round(hits / len(must_keep), 4),
        "transition_leakage_count": transition_count,
        "transition_leakage_rate": round(transition_count / selected_count, 4) if selected_count else 0.0,
        "duplicate_excess_count": duplicate_excess,
        "duplicate_excess_rate": round(duplicate_excess / selected_count, 4) if selected_count else 0.0,
        "frames_per_minute": round(frames_per_minute, 3),
        "runtime_seconds": round(runtime_seconds, 3),
        "budget_pass": (
            frames_per_minute <= budget["max_frames_per_minute"]
            and runtime_seconds <= budget["max_runtime_seconds"]
        ),
    }


def _aggregate(items: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [item for item in items if item.get("status") == "scored"]
    selected = sum(int(item["selected_count"]) for item in scored)
    duration = sum(float(item["duration_seconds"]) for item in scored)
    must_keep_total = sum(int(item["must_keep_total"]) for item in scored)
    must_keep_hit = sum(int(item["must_keep_hit"]) for item in scored)
    transition_count = sum(int(item["transition_leakage_count"]) for item in scored)
    duplicate_excess = sum(int(item["duplicate_excess_count"]) for item in scored)
    return {
        "scored_cases": len(scored),
        "selected_count": selected,
        "duration_seconds": round(duration, 3),
        "must_keep_total": must_keep_total,
        "must_keep_hit": must_keep_hit,
        "must_keep_recall": round(must_keep_hit / must_keep_total, 4) if must_keep_total else None,
        "transition_leakage_rate": round(transition_count / selected, 4) if selected else 0.0,
        "duplicate_excess_rate": round(duplicate_excess / selected, 4) if selected else 0.0,
        "frames_per_minute": round(selected * 60.0 / duration, 3) if duration else 0.0,
        "runtime_seconds": round(sum(float(item["runtime_seconds"]) for item in scored), 3),
        "budget_pass_cases": sum(1 for item in scored if item.get("budget_pass") is True),
    }


def _build_summary(manifest: dict[str, Any], manifest_sha256: str, state: dict[str, Any], workspace: Path) -> dict[str, Any]:
    per_case: list[dict[str, Any]] = []
    profiles = sorted(SUPPORTED_PROFILES)
    for case in manifest["cases"]:
        profile_results: dict[str, Any] = {}
        for profile in profiles:
            run = state["runs"].get(_run_key(case["case_id"], profile), {"status": "not_run"})
            profile_results[profile] = _score_case(case, run, workspace)
        per_case.append(
            {
                "case_id": case["case_id"],
                "category": case["category"],
                "expected_outcome": case["expected_outcome"],
                "profiles": profile_results,
            }
        )
    aggregate = {
        profile: _aggregate([item["profiles"][profile] for item in per_case])
        for profile in profiles
    }
    required_profiles = manifest["acceptance"]["required_profiles"]
    success_cases = [case for case in manifest["cases"] if case["expected_outcome"] == "success"]
    distinct_categories = sorted({case["category"] for case in success_cases})
    incomplete: list[str] = []
    if len(distinct_categories) < manifest["acceptance"]["min_distinct_categories"]:
        incomplete.append("distinct_categories_below_minimum")
    for case in success_cases:
        for profile in required_profiles:
            result = next(item for item in per_case if item["case_id"] == case["case_id"])["profiles"][profile]
            if result.get("status") != "scored":
                incomplete.append(f"{case['case_id']}:{profile}:not_scored")
    damaged = [case for case in manifest["cases"] if case["expected_outcome"] == "failure"]
    for case in damaged:
        for profile in required_profiles:
            result = next(item for item in per_case if item["case_id"] == case["case_id"])["profiles"][profile]
            if result.get("expected_failure_observed") is not True:
                incomplete.append(f"{case['case_id']}:{profile}:failure_contract_not_verified")
    baseline_complete = not incomplete
    comparison: dict[str, Any] = {"status": "not_available"}
    visual = aggregate["visual"]
    ocr = aggregate["ocr"]
    if visual["must_keep_recall"] is not None and ocr["must_keep_recall"] is not None:
        comparison = {
            "status": "available",
            "ocr_minus_visual": {
                "must_keep_recall": round(ocr["must_keep_recall"] - visual["must_keep_recall"], 4),
                "transition_leakage_rate": round(ocr["transition_leakage_rate"] - visual["transition_leakage_rate"], 4),
                "duplicate_excess_rate": round(ocr["duplicate_excess_rate"] - visual["duplicate_excess_rate"], 4),
                "frames_per_minute": round(ocr["frames_per_minute"] - visual["frames_per_minute"], 3),
                "runtime_seconds": round(ocr["runtime_seconds"] - visual["runtime_seconds"], 3),
            },
        }
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "manifest_sha256": manifest_sha256,
        "privacy": {
            "source_paths_stored": False,
            "ocr_text_stored": False,
            "annotation_intervals_stored": False,
            "frame_filenames_stored": False,
        },
        "corpus": {
            "case_count": len(manifest["cases"]),
            "success_case_count": len(success_cases),
            "distinct_categories": distinct_categories,
            "min_distinct_categories": manifest["acceptance"]["min_distinct_categories"],
        },
        "profiles": aggregate,
        "profile_comparison": comparison,
        "cases": per_case,
        "baseline_complete": baseline_complete,
        "real_baseline_status": "verified" if baseline_complete else "not_verified",
        "incomplete_reasons": sorted(set(incomplete)),
        "comparative_evaluation_ready": baseline_complete,
        "accuracy_improvement_claim_allowed": False,
        "claim_note": "本报告只建立固定基线；准确率提升必须由后续候选算法在同一 manifest 上对照证明。",
    }


def _write_summary(manifest: dict[str, Any], manifest_sha256: str, state: dict[str, Any], workspace: Path, output: Path | None) -> dict[str, Any]:
    summary = _build_summary(manifest, manifest_sha256, state, workspace)
    target = output.expanduser().resolve() if output else workspace / "benchmark_summary.json"
    if target.is_symlink():
        raise BenchmarkError("public report 不能是符号链接")
    _atomic_write_json(target, summary)
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="video-screenshot 私有语料基线评测")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="在仓库外生成匿名 manifest 模板")
    init.add_argument("--output", type=Path, required=True)
    validate = sub.add_parser("validate", help="校验 manifest 合同")
    validate.add_argument("--manifest", type=Path, required=True)
    validate.add_argument("--check-files", action="store_true")
    run = sub.add_parser("run", help="运行抽帧并生成脱敏汇总")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--workspace", type=Path, required=True)
    run.add_argument("--profiles", type=_profiles, default=["visual", "ocr"])
    run.add_argument("--public-report", type=Path)
    score = sub.add_parser("score", help="基于已有 workspace 重新计分")
    score.add_argument("--manifest", type=Path, required=True)
    score.add_argument("--workspace", type=Path, required=True)
    score.add_argument("--public-report", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "init":
            output = _require_private_path(args.output, "manifest template")
            if output.exists():
                raise BenchmarkError(f"目标已存在，拒绝覆盖: {output}")
            _atomic_write_json(output, _template())
            print(f"BENCHMARK_TEMPLATE_CREATED {output}")
            return 0
        manifest, manifest_sha256 = _load_manifest(
            args.manifest,
            check_files=args.command == "run" or bool(getattr(args, "check_files", False)),
        )
        if args.command == "validate":
            print(
                f"BENCHMARK_MANIFEST_VALID cases={len(manifest['cases'])} "
                f"sha256={manifest_sha256}"
            )
            return 0
        workspace = _workspace(args.workspace, manifest_sha256)
        state = _load_state(workspace, manifest_sha256)
        if args.command == "run":
            had_failure = False
            for case in manifest["cases"]:
                for profile in args.profiles:
                    output = workspace / "runs" / case["case_id"] / profile
                    run = _execute_case(case, profile, output)
                    state["runs"][_run_key(case["case_id"], profile)] = run
                    _atomic_write_json(workspace / "benchmark_state.json", state)
                    print(f"{case['case_id']} {profile} {run['status']}")
                    if run["status"] not in {"completed", "expected_failure_observed"}:
                        if run.get("diagnostic"):
                            print(str(run["diagnostic"]), file=sys.stderr)
                        had_failure = True
            summary = _write_summary(
                manifest, manifest_sha256, state, workspace, args.public_report
            )
            print(f"BENCHMARK_BASELINE_{summary['real_baseline_status'].upper()}")
            return 2 if had_failure else 0
        summary = _write_summary(manifest, manifest_sha256, state, workspace, args.public_report)
        print(f"BENCHMARK_BASELINE_{summary['real_baseline_status'].upper()}")
        return 0
    except (BenchmarkError, OSError, json.JSONDecodeError) as exc:
        print(f"BENCHMARK_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
