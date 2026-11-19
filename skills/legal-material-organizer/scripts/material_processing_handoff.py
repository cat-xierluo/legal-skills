#!/usr/bin/env python3
"""导出工具中立的材料处理任务，并把外部处理结果安全回写 manifest。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
ACTIVE_CANDIDATE_STATUSES = {"candidate", "pending", "retry", "in_progress"}
RESULT_STATUSES = {"completed", "failed", "needs_review"}
READABLE_STATUSES = {"readable", "partial"}
VARIANT_KINDS = {
    "ocr_markdown",
    "audio_transcript",
    "visual_summary",
    "clean_markdown",
    "word_export",
    "other",
}
CAPABILITIES = {
    "ocr",
    "asr",
    "visual_understanding",
    "text_extract",
    "web_capture",
    "clean_markdown",
    "other",
}
CAPABILITIES_BY_NEED = {
    "need_ocr_or_visual": ["text_extract", "ocr", "visual_understanding"],
    "need_asr": ["asr", "visual_understanding"],
    "need_text_extract": ["text_extract"],
    "need_web_capture": ["web_capture"],
    "need_review": ["other"],
}
HANDOFF_PROCESSING_NEEDS = set(CAPABILITIES_BY_NEED)
MATERIAL_ID_RE = re.compile(r"^M-\d{6}$")
ALLOWED_RESULT_KEYS = {
    "schema_version",
    "material_id",
    "candidate_id",
    "status",
    "capability",
    "producer",
    "output_path",
    "variant_kind",
    "readability_status",
    "text_quality",
    "started_at",
    "completed_at",
    "error_message",
    "extra_json",
}
MATERIAL_PAYLOAD_KEYS = {
    "body",
    "content",
    "full_text",
    "markdown",
    "ocr_text",
    "raw_text",
    "transcript",
}
MAX_RESULT_EXTRA_BYTES = 8 * 1024


class HandoffError(ValueError):
    """表示输入合同或写入边界不满足。"""


def iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_digest(parts: list[str]) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink():
        raise HandoffError(f"{label} 不得是符号链接: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise HandoffError(f"无法读取{label}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise HandoffError(f"{label}不是有效 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise HandoffError(f"{label}顶层必须是对象")
    return value


def list_of_objects(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise HandoffError(f"manifest.{label} 必须是对象数组")
    return value


def is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def resolve_output_path(raw_path: Any, work_dir: Path) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise HandoffError("completed 结果必须提供 output_path")
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = work_dir / candidate
    if candidate.is_symlink():
        raise HandoffError("output_path 不得是符号链接")
    resolved = candidate.resolve()
    if not is_within(resolved, work_dir):
        raise HandoffError("output_path 必须位于 manifest.work_dir 内")
    if not resolved.is_file():
        raise HandoffError("output_path 必须指向已存在的普通文件")
    return resolved


def manifest_collections(data: dict[str, Any]) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    return (
        list_of_objects(data.get("materials"), "materials"),
        list_of_objects(data.get("variants"), "variants"),
        list_of_objects(data.get("processing_runs"), "processing_runs"),
        list_of_objects(data.get("follow_up_candidates"), "follow_up_candidates"),
    )


def indexed(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        item_id = str(item.get(key, ""))
        if not item_id or item_id in result:
            raise HandoffError(f"manifest.{key} 缺失或重复: {item_id or '<empty>'}")
        result[item_id] = item
    return result


def export_tasks(manifest_path: Path) -> dict[str, Any]:
    data = read_json_object(manifest_path, "manifest")
    materials, variants, _runs, candidates = manifest_collections(data)
    material_by_id = indexed(materials, "material_id")
    variant_by_id = indexed(variants, "variant_id")
    tasks: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: str(item.get("candidate_id", ""))):
        if candidate.get("candidate_type") != "preprocess_material":
            continue
        if str(candidate.get("status", "candidate")) not in ACTIVE_CANDIDATE_STATUSES:
            continue
        material_id = str(candidate.get("material_id", ""))
        material = material_by_id.get(material_id)
        if not material or str(material.get("lifecycle_status", "active")) == "missing":
            continue
        input_variant_id = str(material.get("primary_variant_id", ""))
        input_variant = variant_by_id.get(input_variant_id)
        input_path = str(input_variant.get("file_path", "")) if input_variant else str(material.get("absolute_path", ""))
        processing_need = str(material.get("processing_need") or candidate.get("reason") or "need_review")
        if processing_need not in HANDOFF_PROCESSING_NEEDS:
            continue
        tasks.append(
            {
                "candidate_id": str(candidate.get("candidate_id", "")),
                "material_id": material_id,
                "display_code": str(material.get("display_code", "")),
                "input_variant_id": input_variant_id or None,
                "input_path": input_path,
                "processing_need": processing_need,
                "acceptable_capabilities": CAPABILITIES_BY_NEED.get(processing_need, ["other"]),
                "result_contract": {
                    "schema_version": SCHEMA_VERSION,
                    "required_common": ["material_id", "candidate_id", "status", "capability", "producer"],
                    "required_when_completed": ["output_path", "variant_kind", "readability_status"],
                    "required_when_not_completed": ["error_message"],
                },
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "manifest_path": str(manifest_path.resolve()),
        "work_dir": str(data.get("work_dir", "")),
        "task_count": len(tasks),
        "tasks": tasks,
    }


def require_string(result: dict[str, Any], key: str) -> str:
    value = result.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HandoffError(f"result.{key} 必须是非空字符串")
    return value.strip()


def validate_result_extra(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise HandoffError("result.extra_json 必须是对象")
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    if len(encoded) > MAX_RESULT_EXTRA_BYTES:
        raise HandoffError("result.extra_json 过大；材料正文必须留在 work_dir 文件中")
    stack: list[Any] = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, child in current.items():
                if str(key).strip().casefold() in MATERIAL_PAYLOAD_KEYS:
                    raise HandoffError(f"result.extra_json 不得包含材料正文键: {key}")
                stack.append(child)
        elif isinstance(current, list):
            stack.extend(current)
    return value


def add_review_reason(material: dict[str, Any], reason: str) -> None:
    current = material.get("review_reasons")
    reasons = list(current) if isinstance(current, list) else []
    if reason not in reasons:
        reasons.append(reason)
    material["review_reasons"] = reasons
    material["needs_human_review"] = True


def upsert_human_review_candidate(
    candidates: list[dict[str, Any]], material: dict[str, Any], reason: str, run_id: str
) -> None:
    material_id = str(material["material_id"])
    candidate_id = f"follow_{material_id.replace('-', '_')}_human_review"
    existing = next((item for item in candidates if item.get("candidate_id") == candidate_id), None)
    payload = {
        "candidate_id": candidate_id,
        "material_id": material_id,
        "display_code": str(material.get("display_code", "")),
        "candidate_type": "human_review",
        "title": f"{material.get('display_code') or material_id} 需要人工复核",
        "suggested_action": "人工确认处理失败原因、结果完整性或是否改用其他可用能力",
        "priority": "P2",
        "status": "candidate",
        "reason": reason,
        "extra_json": {"source_run_id": run_id},
    }
    if existing is None:
        candidates.append(payload)
    else:
        payload["extra_json"] = {
            **(existing.get("extra_json") if isinstance(existing.get("extra_json"), dict) else {}),
            "source_run_id": run_id,
        }
        existing.update(payload)


def validate_result_shape(result: dict[str, Any]) -> tuple[str, str, str, str, str]:
    unknown_keys = sorted(set(result) - ALLOWED_RESULT_KEYS)
    if unknown_keys:
        raise HandoffError(f"result 包含未定义字段: {', '.join(unknown_keys)}")
    if result.get("schema_version") != SCHEMA_VERSION:
        raise HandoffError(f"result.schema_version 必须为 {SCHEMA_VERSION}")
    material_id = require_string(result, "material_id")
    if not MATERIAL_ID_RE.fullmatch(material_id):
        raise HandoffError("result.material_id 格式错误")
    candidate_id = require_string(result, "candidate_id")
    status = require_string(result, "status")
    capability = require_string(result, "capability")
    producer = require_string(result, "producer")
    if status not in RESULT_STATUSES:
        raise HandoffError(f"result.status 必须是 {sorted(RESULT_STATUSES)} 之一")
    if capability not in CAPABILITIES:
        raise HandoffError(f"result.capability 必须是 {sorted(CAPABILITIES)} 之一")
    if len(producer) > 200:
        raise HandoffError("result.producer 过长")
    validate_result_extra(result.get("extra_json"))
    text_quality = result.get("text_quality")
    if text_quality is not None and not isinstance(text_quality, (str, int, float)):
        raise HandoffError("result.text_quality 只能是字符串或数值")
    if status != "completed":
        error_message = require_string(result, "error_message")
        if len(error_message) > 2000:
            raise HandoffError("result.error_message 过长")
        if result.get("output_path") or result.get("variant_kind"):
            raise HandoffError("非 completed 结果不得登记 output_path 或 variant_kind")
    return material_id, candidate_id, status, capability, producer


def apply_result(data: dict[str, Any], result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    material_id, candidate_id, status, capability, producer = validate_result_shape(result)
    updated = deepcopy(data)
    materials, variants, runs, candidates = manifest_collections(updated)
    material_by_id = indexed(materials, "material_id")
    variant_by_id = indexed(variants, "variant_id")
    run_by_id = indexed(runs, "run_id")
    candidate_by_id = indexed(candidates, "candidate_id")
    material = material_by_id.get(material_id)
    candidate = candidate_by_id.get(candidate_id)
    if material is None:
        raise HandoffError(f"material_id 不存在: {material_id}")
    if candidate is None or candidate.get("candidate_type") != "preprocess_material":
        raise HandoffError(f"candidate_id 不是有效预处理候选: {candidate_id}")
    if str(candidate.get("material_id", "")) != material_id:
        raise HandoffError("candidate_id 与 material_id 不匹配")
    if str(material.get("lifecycle_status", "active")) == "missing":
        raise HandoffError("不能为 missing 材料回写处理结果")

    work_raw = updated.get("work_dir")
    if not isinstance(work_raw, str) or not work_raw.strip():
        raise HandoffError("manifest.work_dir 缺失")
    work_dir = Path(work_raw).expanduser().resolve()
    input_variant_id = str(material.get("primary_variant_id", "")) or None
    started_at = str(result.get("started_at") or iso_now())
    completed_at = str(result.get("completed_at") or iso_now())

    output_path: Path | None = None
    output_hash = ""
    variant_id: str | None = None
    readability_status: str | None = None
    variant_kind: str | None = None
    if status == "completed":
        variant_kind = require_string(result, "variant_kind")
        readability_status = require_string(result, "readability_status")
        if variant_kind not in VARIANT_KINDS:
            raise HandoffError(f"result.variant_kind 必须是 {sorted(VARIANT_KINDS)} 之一")
        if readability_status not in READABLE_STATUSES:
            raise HandoffError("completed 结果的 readability_status 必须是 readable 或 partial")
        output_path = resolve_output_path(result.get("output_path"), work_dir)
        output_hash = sha256_file(output_path)
        variant_id = f"variant_{material_id.replace('-', '_')}_{variant_kind}_{output_hash[:12]}"

    error_message = str(result.get("error_message") or "")
    run_id = "run_{}_{}_{}".format(
        material_id.replace("-", "_"),
        capability,
        stable_digest(
            [material_id, candidate_id, status, capability, producer, str(output_path or ""), output_hash, error_message]
        ),
    )
    if run_id in run_by_id:
        return updated, {
            "changed": False,
            "run_id": run_id,
            "variant_id": run_by_id[run_id].get("output_variant_id"),
            "status": status,
        }
    if str(candidate.get("status", "candidate")) == "completed":
        raise HandoffError("候选项已完成；如需重新处理，请先建立新的候选项")

    run_status = "completed" if status == "completed" else status
    run = {
        "run_id": run_id,
        "material_id": material_id,
        "candidate_id": candidate_id,
        "input_variant_id": input_variant_id,
        "output_variant_id": variant_id,
        "run_type": capability,
        "status": run_status,
        "producer": producer,
        "reason": str(candidate.get("reason") or material.get("processing_need") or "外部处理结果回写"),
        "input_path": str(material.get("absolute_path") or "") or None,
        "output_path": str(output_path) if output_path else None,
        "error_message": error_message or None,
        "started_at": started_at,
        "completed_at": completed_at,
        "extra_json": {
            "writeback_schema_version": SCHEMA_VERSION,
            "candidate_id": candidate_id,
            "result_extra": result.get("extra_json") if isinstance(result.get("extra_json"), dict) else {},
        },
    }
    runs.append(run)

    if status == "completed" and output_path and variant_id and variant_kind and readability_status:
        existing_variant = variant_by_id.get(variant_id)
        variant = {
            "variant_id": variant_id,
            "material_id": material_id,
            "parent_variant_id": input_variant_id,
            "variant_kind": variant_kind,
            "file_path": str(output_path),
            "display_path": None,
            "file_hash": output_hash,
            "generator": producer,
            "readability_status": readability_status,
            "processing_status": "completed",
            "text_quality": result.get("text_quality"),
            "asset_status": "available",
            "is_primary": False,
            "is_primary_readable": True,
            "created_at": completed_at,
            "extra_json": {"source_run_id": run_id},
        }
        if existing_variant and any(
            existing_variant.get(key) != variant.get(key) for key in ("material_id", "file_path", "file_hash")
        ):
            raise HandoffError(f"variant_id 冲突: {variant_id}")
        for item in variants:
            if item.get("material_id") == material_id:
                item["is_primary_readable"] = False
        if existing_variant:
            existing_variant.update(variant)
        else:
            variants.append(variant)
        material["primary_readable_variant_id"] = variant_id
        material["readability_status"] = readability_status
        material["content_status"] = "completed"
        candidate["extra_json"] = {
            **(candidate.get("extra_json") if isinstance(candidate.get("extra_json"), dict) else {}),
            "last_run_id": run_id,
            "output_variant_id": variant_id,
        }
        if readability_status == "readable":
            material["processing_need"] = "none"
            candidate["status"] = "completed"
        else:
            review_reason = "处理结果仅部分可读，需人工复核完整性"
            material["processing_need"] = "need_review"
            add_review_reason(material, review_reason)
            candidate["status"] = "needs_review"
            upsert_human_review_candidate(candidates, material, review_reason, run_id)
    else:
        prefix = "处理失败" if status == "failed" else "处理结果需人工复核"
        review_reason = f"{prefix}：{error_message}"
        candidate["status"] = status
        candidate["extra_json"] = {
            **(candidate.get("extra_json") if isinstance(candidate.get("extra_json"), dict) else {}),
            "last_run_id": run_id,
        }
        if not material.get("primary_readable_variant_id"):
            material["readability_status"] = "failed" if status == "failed" else "unknown"
        material["content_status"] = "failed" if status == "failed" else "needs_review"
        add_review_reason(material, review_reason)
        upsert_human_review_candidate(candidates, material, review_reason, run_id)

    updated["processing_updated_at"] = completed_at
    return updated, {"changed": True, "run_id": run_id, "variant_id": variant_id, "status": status}


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    if path.is_symlink():
        raise HandoffError("manifest 不得是符号链接")
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description="导出材料处理任务或回写外部处理结果")
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export", help="向标准输出导出待处理任务 JSON")
    export_parser.add_argument("--manifest", required=True, help="materials_manifest.json 路径")
    record_parser = subparsers.add_parser("record", help="验证结果 JSON 并原子回写 manifest")
    record_parser.add_argument("--manifest", required=True, help="materials_manifest.json 路径")
    record_parser.add_argument("--result", required=True, help="处理结果 JSON 路径")
    args = parser.parse_args()

    try:
        manifest_path = Path(args.manifest).expanduser()
        if args.command == "export":
            print(json.dumps(export_tasks(manifest_path), ensure_ascii=False, sort_keys=True))
            return 0
        result = read_json_object(Path(args.result).expanduser(), "result")
        manifest = read_json_object(manifest_path, "manifest")
        updated, receipt = apply_result(manifest, result)
        if receipt["changed"]:
            atomic_write_json(manifest_path, updated)
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
        return 0
    except HandoffError as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
