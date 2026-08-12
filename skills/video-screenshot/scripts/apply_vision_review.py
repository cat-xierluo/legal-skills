#!/usr/bin/env python3

"""验证视觉审计 JSON，并非破坏性地生成精选帧目录。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any


ALLOWED_DECISIONS = {"keep", "drop", "replace"}
ALLOWED_REASONS = {
    "transition",
    "visual_duplicate",
    "semantic_duplicate",
    "new_evidence",
    "clearer_replacement",
    "other",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="应用多模态截图审计结果并生成精选目录")
    parser.add_argument("-i", "--input", required=True, help="基础抽帧输出目录")
    parser.add_argument("-r", "--review", required=True, help="视觉模型生成的 _vision_review.json")
    parser.add_argument("-m", "--manifest", default=None, help="审计 manifest（默认: <input>/_vision_audit/audit_manifest.json）")
    parser.add_argument("-o", "--output", default=None, help="精选目录（默认: <input>/_curated）")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"缺少{label}: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"{label}不是有效 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label}必须是 JSON 对象")
    return value


def _resolve_source(root: Path, item: dict[str, Any]) -> Path:
    rel = str(item.get("path") or "")
    if not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
        raise ValueError(f"manifest 含非法路径: {rel!r}")
    source = (root / rel).resolve()
    try:
        source.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"manifest 路径越界: {rel}") from exc
    if not source.is_file():
        raise ValueError(f"manifest 图片不存在: {rel}")
    if sha256_file(source) != str(item.get("sha256") or ""):
        raise ValueError(f"manifest 图片哈希不一致: {rel}")
    return source


def _validate_review(review: dict[str, Any], manifest_path: Path, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if review.get("schema_version") != "1.0":
        raise ValueError("视觉审计 schema_version 必须为 1.0")
    if review.get("status") != "completed":
        raise ValueError("视觉审计 status 必须为 completed")
    expected_manifest_sha = sha256_file(manifest_path)
    if review.get("source_manifest_sha256") != expected_manifest_sha:
        raise ValueError("视觉审计未绑定当前 audit_manifest.json")
    known = {str(item["audit_id"]): item for item in manifest.get("images") or []}
    if not known:
        raise ValueError("manifest 没有图片清单")
    decisions = review.get("decisions")
    if not isinstance(decisions, list):
        raise ValueError("视觉审计 decisions 必须是数组")
    result: dict[str, dict[str, Any]] = {}
    for raw in decisions:
        if not isinstance(raw, dict):
            raise ValueError("每条视觉审计决策必须是对象")
        audit_id = str(raw.get("audit_id") or "")
        decision = str(raw.get("decision") or "")
        reason_code = str(raw.get("reason_code") or "")
        reason = str(raw.get("reason") or "").strip()
        confidence = raw.get("confidence")
        if audit_id not in known:
            raise ValueError(f"决策引用 manifest 外图片: {audit_id}")
        if audit_id in result:
            raise ValueError(f"同一图片存在重复决策: {audit_id}")
        if decision not in ALLOWED_DECISIONS:
            raise ValueError(f"非法 decision: {decision}")
        if reason_code not in ALLOWED_REASONS:
            raise ValueError(f"非法 reason_code: {reason_code}")
        if not reason:
            raise ValueError(f"决策缺少可回查理由: {audit_id}")
        if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
            raise ValueError(f"confidence 必须在 0—1: {audit_id}")
        replacement = str(raw.get("replacement_audit_id") or "")
        if decision == "replace":
            if replacement not in known or replacement == audit_id:
                raise ValueError(f"replace 必须引用另一个 manifest 内图片: {audit_id}")
        elif replacement:
            raise ValueError(f"非 replace 决策不得填写 replacement_audit_id: {audit_id}")
        if known[audit_id].get("source") == "drop_candidate" and decision != "keep":
            raise ValueError(f"丢弃候选只允许 keep 补回，其他决策不会产生有效结果: {audit_id}")
        result[audit_id] = dict(raw)
    for audit_id, decision in result.items():
        if decision["decision"] != "replace":
            continue
        replacement = str(decision["replacement_audit_id"])
        replacement_decision = result.get(replacement)
        if replacement_decision and replacement_decision["decision"] != "keep":
            raise ValueError(f"replace 目标同时被 drop/replace，决策相互冲突: {audit_id}")
    return result


def _prepare_output(output: Path) -> None:
    if output.is_symlink():
        raise ValueError("精选目录是符号链接，拒绝跟随并覆盖")
    output.mkdir(parents=True, exist_ok=True)
    unknown = [
        path for path in output.iterdir()
        if path.is_symlink()
        or (path.name != "_curated_report.json" and not re.fullmatch(r"curated_\d{3}_.+\.jpg", path.name))
    ]
    if unknown:
        names = ", ".join(path.name for path in unknown[:5])
        raise ValueError(f"精选目录含非本工具文件，拒绝覆盖: {names}")
    for path in output.glob("curated_*.jpg"):
        path.unlink()
    report = output / "_curated_report.json"
    if report.exists():
        report.unlink()


def _timestamp_label(value: Any) -> str:
    seconds = max(0, int(float(value or 0.0)))
    minutes, sec = divmod(seconds, 60)
    return f"{minutes:02d}m{sec:02d}s"


def main() -> int:
    args = parse_args()
    raw_root = Path(args.input).expanduser()
    if raw_root.is_symlink():
        print("错误: 基础输出目录是符号链接，拒绝跟随", file=sys.stderr)
        return 2
    root = raw_root.resolve()
    raw_manifest = Path(args.manifest).expanduser() if args.manifest else root / "_vision_audit" / "audit_manifest.json"
    raw_review = Path(args.review).expanduser()
    raw_output = Path(args.output).expanduser() if args.output else root / "_curated"
    manifest_path = raw_manifest.resolve()
    review_path = raw_review.resolve()
    output = raw_output.resolve()
    try:
        if raw_manifest.is_symlink() or raw_review.is_symlink() or raw_output.is_symlink():
            raise ValueError("manifest、视觉审计结果或精选目录是符号链接，拒绝跟随")
        report_path = root / "_report.json"
        report = load_json(report_path, "基础报告")
        manifest = load_json(manifest_path, "审计 manifest")
        review = load_json(review_path, "视觉审计结果")
        if manifest.get("schema_version") != "1.0" or manifest.get("status") != "prepared":
            raise ValueError("审计 manifest 的 schema_version/status 无效")
        if manifest.get("source_report_sha256") != sha256_file(report_path):
            raise ValueError("审计 manifest 未绑定当前基础报告")
        decisions = _validate_review(review, manifest_path, manifest)
        manifest_images = manifest.get("images") or []
        if not isinstance(manifest_images, list) or not manifest_images:
            raise ValueError("审计 manifest 没有图片清单")
        audit_images: dict[str, dict[str, Any]] = {}
        manifest_paths: set[str] = set()
        for item in manifest_images:
            if not isinstance(item, dict):
                raise ValueError("审计 manifest 图片项必须是对象")
            audit_id = str(item.get("audit_id") or "")
            rel = str(item.get("path") or "")
            if not audit_id or audit_id in audit_images:
                raise ValueError(f"审计 manifest 含缺失或重复 audit_id: {audit_id!r}")
            if rel in manifest_paths:
                raise ValueError(f"审计 manifest 同一路径出现多个 audit_id: {rel}")
            _resolve_source(root, item)
            audit_images[audit_id] = item
            manifest_paths.add(rel)
        for frame in report.get("frames") or []:
            _resolve_source(root, {
                "path": frame.get("filename"),
                "sha256": frame.get("sha256"),
            })
        by_path = {str(item["path"]): audit_id for audit_id, item in audit_images.items()}

        result_items: list[dict[str, Any]] = []
        included_paths: set[str] = set()
        excluded_by_vision: list[dict[str, Any]] = []
        for frame in report.get("frames") or []:
            rel = str(frame.get("filename") or "")
            audit_id = by_path.get(rel)
            decision = decisions.get(audit_id or "")
            if decision and decision["decision"] == "drop":
                excluded_by_vision.append({
                    "audit_id": audit_id,
                    "source_path": rel,
                    "capture_time_seconds": frame.get("capture_time_seconds"),
                    "sha256": frame.get("sha256"),
                    "decision": decision,
                })
                continue
            selected_item = None
            provenance = "base_keep"
            source_decision = decision
            if decision and decision["decision"] == "replace":
                excluded_by_vision.append({
                    "audit_id": audit_id,
                    "source_path": rel,
                    "capture_time_seconds": frame.get("capture_time_seconds"),
                    "sha256": frame.get("sha256"),
                    "decision": decision,
                })
                selected_item = audit_images[decision["replacement_audit_id"]]
                provenance = "vision_replace"
            else:
                selected_item = {
                    "path": rel,
                    "sha256": frame.get("sha256"),
                    "capture_time_seconds": frame.get("capture_time_seconds"),
                    "source": "kept",
                }
                if decision:
                    provenance = "vision_keep"
            if selected_item["path"] in included_paths:
                if decision and decision["decision"] == "replace":
                    for existing in result_items:
                        if existing["source_path"] == selected_item["path"]:
                            existing["provenance"] = "vision_replace_existing"
                            existing["decision"] = source_decision
                            break
                continue
            source = _resolve_source(root, selected_item)
            included_paths.add(str(selected_item["path"]))
            result_items.append({
                "source": source,
                "source_path": str(selected_item["path"]),
                "capture_time_seconds": selected_item.get("capture_time_seconds"),
                "sha256": str(selected_item.get("sha256") or ""),
                "provenance": provenance,
                "decision": source_decision,
            })

        # manifest 内被丢弃候选可被明确 keep，作为新增证据补入精选集。
        for audit_id, decision in decisions.items():
            item = audit_images[audit_id]
            if item.get("source") != "drop_candidate" or decision["decision"] != "keep":
                continue
            if item["path"] in included_paths:
                continue
            source = _resolve_source(root, item)
            included_paths.add(str(item["path"]))
            result_items.append({
                "source": source,
                "source_path": item["path"],
                "capture_time_seconds": item.get("capture_time_seconds"),
                "sha256": item["sha256"],
                "provenance": "vision_add",
                "decision": decision,
            })

        result_items.sort(key=lambda item: float(item.get("capture_time_seconds") or 0.0))
        if not result_items:
            raise ValueError("审计结果会生成空精选集，拒绝应用")
        _prepare_output(output)
        curated_frames: list[dict[str, Any]] = []
        for index, item in enumerate(result_items, 1):
            filename = f"curated_{index:03d}_{_timestamp_label(item['capture_time_seconds'])}.jpg"
            destination = output / filename
            shutil.copy2(item["source"], destination)
            curated_frames.append({
                "index": index,
                "filename": filename,
                "source_path": item["source_path"],
                "capture_time_seconds": item["capture_time_seconds"],
                "sha256": sha256_file(destination),
                "provenance": item["provenance"],
                "vision_decision": item["decision"],
            })

        curated_report = {
            "schema_version": "1.0",
            "base_report": "../_report.json",
            "base_report_sha256": sha256_file(report_path),
            "audit_manifest": str(manifest_path),
            "audit_manifest_sha256": sha256_file(manifest_path),
            "vision_review": str(review_path),
            "vision_review_sha256": sha256_file(review_path),
            "base_frame_count": len(report.get("frames") or []),
            "curated_frame_count": len(curated_frames),
            "decision_summary": {
                "decision_count": len(decisions),
                "kept": sum(1 for item in decisions.values() if item["decision"] == "keep"),
                "dropped": sum(1 for item in decisions.values() if item["decision"] == "drop"),
                "replaced": sum(1 for item in decisions.values() if item["decision"] == "replace"),
                "added_from_drop_candidates": sum(1 for item in curated_frames if item["provenance"] == "vision_add"),
            },
            "excluded_by_vision": excluded_by_vision,
            "frames": curated_frames,
        }
        report_output = output / "_curated_report.json"
        report_output.write_text(json.dumps(curated_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        actual = sorted(path.name for path in output.glob("curated_*.jpg"))
        expected = sorted(str(item["filename"]) for item in curated_frames)
        if actual != expected:
            raise RuntimeError("精选目录与 _curated_report.json 清单不一致")
        print(f"完成: {output}")
        print(f"  基础帧: {len(report.get('frames') or [])}")
        print(f"  精选帧: {len(curated_frames)}")
        return 0
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
