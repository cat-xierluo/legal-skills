#!/usr/bin/env python3
"""验证 materials_manifest.json 的四项可机判不变量。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


CONSTRAINT_IDS = (
    "STORAGE-SEPARATION",
    "TRACEABILITY-INTEGRITY",
    "UNCERTAINTY-ROUTING",
    "PROCESSING-CLOSURE",
)
MEASUREMENT_IDS = {
    "STORAGE-SEPARATION": "storage-violation-count",
    "TRACEABILITY-INTEGRITY": "traceability-violation-count",
    "UNCERTAINTY-ROUTING": "uncertainty-violation-count",
    "PROCESSING-CLOSURE": "processing-closure-violation-count",
}
MATERIAL_ID_RE = re.compile(r"^M-\d{6}$")
DISPLAY_CODE_RE = re.compile(r"^[ABCD]\d{3,}$")
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_path(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value.strip().replace("\\", "/").rstrip("/")
    return normalized.casefold()


def _is_within(child: str, parent: str) -> bool:
    return bool(child and parent and (child == parent or child.startswith(parent + "/")))


def _list(value: Any) -> list[dict[str, Any]]:
    return value if isinstance(value, list) and all(isinstance(item, dict) for item in value) else []


def _has_material_payload_key(value: Any) -> bool:
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, child in current.items():
                if str(key).strip().casefold() in MATERIAL_PAYLOAD_KEYS:
                    return True
                stack.append(child)
        elif isinstance(current, list):
            stack.extend(current)
    return False


def validate_manifest(data: Any) -> tuple[dict[str, list[str]], dict[str, Any]]:
    violations = {constraint_id: [] for constraint_id in CONSTRAINT_IDS}
    if not isinstance(data, dict):
        for constraint_id in CONSTRAINT_IDS:
            violations[constraint_id].append("manifest 顶层不是对象")
        return violations, {"material_ids": [], "uncertainty_routes": [], "processing_closures": []}

    materials = _list(data.get("materials"))
    variants = _list(data.get("variants"))
    material_sets = _list(data.get("material_sets"))
    follow_ups = _list(data.get("follow_up_candidates"))
    processing_runs = _list(data.get("processing_runs"))

    archive_dir = _normalized_path(data.get("archive_dir"))
    work_dir = _normalized_path(data.get("work_dir"))
    storage = violations["STORAGE-SEPARATION"]
    if not archive_dir or not work_dir:
        storage.append("archive_dir/work_dir 缺失")
    elif _is_within(archive_dir, work_dir) or _is_within(work_dir, archive_dir):
        storage.append("archive_dir 与 work_dir 相同或互相包含")

    material_paths: list[tuple[str, str, bool]] = []
    for item in materials:
        material_paths.append(
            (
                str(item.get("material_id", "")),
                _normalized_path(item.get("absolute_path")),
                bool(item.get("extracted_from_archive", False)),
            )
        )
    for item in variants:
        material_paths.append(
            (
                str(item.get("variant_id", "")),
                _normalized_path(item.get("file_path")),
                str(item.get("variant_kind", "")) != "original",
            )
        )
    for item in processing_runs:
        output_path = _normalized_path(item.get("output_path"))
        if output_path:
            material_paths.append((str(item.get("run_id", "")), output_path, True))
    for item_id, path, should_be_work in material_paths:
        if path and _is_within(path, archive_dir):
            storage.append(f"真实材料路径进入 archive: {item_id}")
        if path and should_be_work and not _is_within(path, work_dir):
            storage.append(f"处理或解压产物不在 work: {item_id}")

    trace = violations["TRACEABILITY-INTEGRITY"]
    material_ids = [str(item.get("material_id", "")) for item in materials]
    material_id_set = set(material_ids)
    if not materials:
        trace.append("materials 为空或格式错误")
    if len(material_ids) != len(material_id_set):
        trace.append("material_id 重复")
    for material_id in material_ids:
        if not MATERIAL_ID_RE.fullmatch(material_id):
            trace.append(f"material_id 格式错误: {material_id or '<empty>'}")

    display_codes = [str(item.get("display_code", "")) for item in materials]
    if len(display_codes) != len(set(display_codes)):
        trace.append("display_code 重复")
    for display_code in display_codes:
        if not DISPLAY_CODE_RE.fullmatch(display_code):
            trace.append(f"display_code 格式错误: {display_code or '<empty>'}")

    variant_ids = [str(item.get("variant_id", "")) for item in variants]
    variant_id_set = set(variant_ids)
    variant_by_id = {str(item.get("variant_id", "")): item for item in variants if item.get("variant_id")}
    if len(variant_ids) != len(variant_id_set):
        trace.append("variant_id 重复")
    for item in variants:
        if str(item.get("material_id", "")) not in material_id_set:
            trace.append(f"variant 引用不存在的 material_id: {item.get('variant_id', '')}")
    for item in materials:
        material_id = str(item.get("material_id", ""))
        parent_id = item.get("parent_material_id")
        if parent_id and str(parent_id) not in material_id_set:
            trace.append(f"父材料不存在: {material_id}")
        primary_variant = item.get("primary_variant_id")
        if primary_variant and str(primary_variant) not in variant_id_set:
            trace.append(f"primary_variant_id 不存在: {material_id}")
        elif primary_variant and str(variant_by_id[str(primary_variant)].get("material_id", "")) != material_id:
            trace.append(f"primary_variant_id 指向其他材料: {material_id}")
        readable_variant = item.get("primary_readable_variant_id")
        if readable_variant and str(readable_variant) not in variant_id_set:
            trace.append(f"primary_readable_variant_id 不存在: {material_id}")
        elif readable_variant and str(variant_by_id[str(readable_variant)].get("material_id", "")) != material_id:
            trace.append(f"primary_readable_variant_id 指向其他材料: {material_id}")
        if item.get("extracted_from_archive") and (
            not parent_id or not isinstance(item.get("source_chain"), list) or not item.get("source_chain")
        ):
            trace.append(f"解压材料缺父级来源链: {material_id}")
    for item in material_sets:
        for material_id in item.get("material_ids", []) if isinstance(item.get("material_ids"), list) else []:
            if str(material_id) not in material_id_set:
                trace.append(f"材料组引用不存在的 material_id: {material_id}")
    for item in follow_ups:
        if str(item.get("material_id", "")) not in material_id_set:
            trace.append(f"后续候选引用不存在的 material_id: {item.get('candidate_id', '')}")
    candidate_ids = {str(item.get("candidate_id", "")) for item in follow_ups if item.get("candidate_id")}
    run_ids = [str(item.get("run_id", "")) for item in processing_runs]
    if len(run_ids) != len(set(run_ids)):
        trace.append("run_id 重复")
    for item in processing_runs:
        run_id = str(item.get("run_id", ""))
        if not run_id:
            trace.append("processing_run 缺少 run_id")
        if str(item.get("material_id", "")) not in material_id_set:
            trace.append(f"processing_run 引用不存在的 material_id: {run_id}")
        for field in ("input_variant_id", "output_variant_id"):
            value = item.get(field)
            if value and str(value) not in variant_id_set:
                trace.append(f"processing_run.{field} 不存在: {run_id}")
        candidate_id = item.get("candidate_id")
        if candidate_id and str(candidate_id) not in candidate_ids:
            trace.append(f"processing_run.candidate_id 不存在: {run_id}")
    if isinstance(data.get("total_record_count"), int) and data["total_record_count"] != len(materials):
        trace.append("total_record_count 与 materials 数量不一致")

    uncertainty = violations["UNCERTAINTY-ROUTING"]
    routed_ids = {
        str(item.get("material_id", ""))
        for item in follow_ups
        if str(item.get("status", "candidate")) not in {"dismissed", "cancelled"}
    }
    uncertainty_routes: list[str] = []
    for item in materials:
        if str(item.get("lifecycle_status", "active")) == "missing":
            continue
        material_id = str(item.get("material_id", ""))
        readability = str(item.get("readability_status", "unknown"))
        processing_need = str(item.get("processing_need", "none"))
        requires_route = readability in {"", "unknown", "partial", "unreadable", "failed"} or processing_need != "none"
        routed = material_id in routed_ids or bool(item.get("needs_human_review", False))
        if requires_route and not routed:
            uncertainty.append(f"不确定材料缺后续候选或人工复核: {material_id}")
        if requires_route:
            route = "follow-up" if material_id in routed_ids else "human-review" if routed else "missing"
            uncertainty_routes.append(f"{material_id}:{processing_need}:{route}")

    closure = violations["PROCESSING-CLOSURE"]
    material_by_id = {str(item.get("material_id", "")): item for item in materials if item.get("material_id")}
    candidate_by_id = {
        str(item.get("candidate_id", "")): item for item in follow_ups if item.get("candidate_id")
    }
    writeback_runs = [
        item
        for item in processing_runs
        if isinstance(item.get("extra_json"), dict)
        and item["extra_json"].get("writeback_schema_version") == 1
    ]
    writeback_by_candidate: dict[str, list[dict[str, Any]]] = {}
    processing_closures: list[str] = []
    human_review_route_ids = {
        str(item.get("material_id", ""))
        for item in follow_ups
        if item.get("candidate_type") == "human_review"
    }
    for run in writeback_runs:
        run_id = str(run.get("run_id", ""))
        material_id = str(run.get("material_id", ""))
        candidate_id = str(run.get("candidate_id") or run.get("extra_json", {}).get("candidate_id") or "")
        status = str(run.get("status", ""))
        if candidate_id:
            writeback_by_candidate.setdefault(candidate_id, []).append(run)
        material = material_by_id.get(material_id)
        candidate = candidate_by_id.get(candidate_id)
        result_extra = run.get("extra_json", {}).get("result_extra", {})
        if not isinstance(result_extra, dict):
            closure.append(f"回写运行 result_extra 不是对象: {run_id}")
        else:
            extra_size = len(json.dumps(result_extra, ensure_ascii=False, sort_keys=True).encode("utf-8"))
            if extra_size > MAX_RESULT_EXTRA_BYTES or _has_material_payload_key(result_extra):
                closure.append(f"回写运行把材料正文或超大载荷写入元数据: {run_id}")
        if material is None or candidate is None or str(candidate.get("material_id", "")) != material_id:
            closure.append(f"回写运行缺少有效材料或候选关联: {run_id}")
            continue
        if status == "completed":
            output_variant_id = str(run.get("output_variant_id", ""))
            output_variant = variant_by_id.get(output_variant_id)
            if output_variant is None:
                closure.append(f"完成运行缺少输出变体: {run_id}")
                continue
            if str(output_variant.get("material_id", "")) != material_id:
                closure.append(f"完成运行输出变体属于其他材料: {run_id}")
            if str(output_variant.get("processing_status", "")) != "completed":
                closure.append(f"完成运行输出变体未标记 completed: {run_id}")
            if str(output_variant.get("readability_status", "")) not in {"readable", "partial"}:
                closure.append(f"完成运行输出变体不可读: {run_id}")
            if _normalized_path(run.get("output_path")) != _normalized_path(output_variant.get("file_path")):
                closure.append(f"完成运行输出路径与变体不一致: {run_id}")
            if str(material.get("primary_readable_variant_id", "")) != output_variant_id:
                closure.append(f"材料未指向完成运行的主可读变体: {material_id}")
            candidate_status = str(candidate.get("status", ""))
            readability = str(output_variant.get("readability_status", ""))
            if readability == "readable" and candidate_status != "completed":
                closure.append(f"可读结果的候选项未闭合为 completed: {candidate_id}")
            if readability == "readable" and str(material.get("processing_need", "")) != "none":
                closure.append(f"可读结果仍保留待处理动作: {material_id}")
            if readability == "partial" and material_id not in human_review_route_ids:
                closure.append(f"部分可读结果未转人工复核: {material_id}")
            processing_closures.append(f"{material_id}:{candidate_id}:{status}:{output_variant_id}")
        elif status in {"failed", "needs_review"}:
            if not str(run.get("error_message", "")).strip():
                closure.append(f"失败或待复核运行缺少原因: {run_id}")
            if run.get("output_variant_id") or run.get("output_path"):
                closure.append(f"失败或待复核运行错误登记输出: {run_id}")
            if material_id not in human_review_route_ids:
                closure.append(f"失败或待复核运行未转人工复核: {run_id}")
            processing_closures.append(f"{material_id}:{candidate_id}:{status}:human-review")
        else:
            closure.append(f"回写运行状态不受支持: {run_id}")

    for candidate in follow_ups:
        if candidate.get("candidate_type") != "preprocess_material":
            continue
        status = str(candidate.get("status", "candidate"))
        if status not in {"completed", "failed", "needs_review"}:
            continue
        candidate_id = str(candidate.get("candidate_id", ""))
        matching_runs = writeback_by_candidate.get(candidate_id, [])
        if not matching_runs:
            closure.append(f"已闭合候选项缺少回写运行: {candidate_id}")
            continue
        expected_statuses = {"completed"} if status in {"completed", "needs_review"} else {"failed"}
        if status == "needs_review":
            expected_statuses.add("needs_review")
        if not any(str(run.get("status", "")) in expected_statuses for run in matching_runs):
            closure.append(f"候选状态与回写运行不一致: {candidate_id}")

    observables = {
        "material_ids": sorted(material_id_set),
        "uncertainty_routes": sorted(uncertainty_routes),
        "processing_closures": sorted(processing_closures),
    }
    return violations, observables


def main() -> int:
    parser = argparse.ArgumentParser(description="校验法律材料 manifest 的存储、引用、不确定性路由和处理闭环")
    parser.add_argument("--input", required=True, help="materials_manifest.json 路径")
    args = parser.parse_args()
    path = Path(args.input)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        data = None
        parse_error = str(exc)
    else:
        parse_error = ""

    violations, derived = validate_manifest(data)
    if parse_error:
        for constraint_id in CONSTRAINT_IDS:
            violations[constraint_id].append(f"manifest 无法读取: {parse_error}")
    failed = [constraint_id for constraint_id in CONSTRAINT_IDS if violations[constraint_id]]
    artifact_hash = _sha256(path) if path.is_file() else ""
    measurements = {
        constraint_id: {MEASUREMENT_IDS[constraint_id]: len(violations[constraint_id])}
        for constraint_id in (failed or CONSTRAINT_IDS)
    }
    if failed:
        for constraint_id in failed:
            for message in violations[constraint_id]:
                print(f"[{constraint_id}] {message}")
        print(json.dumps({
            "failed_constraint_ids": failed,
            "artifact_sha256": {"materials-manifest": artifact_hash},
            "measurements": measurements,
        }, ensure_ascii=False, sort_keys=True))
        return 3

    print(
        "DOMAIN_VERIFIED "
        "scope=manifest-storage-traceability-uncertainty-processing-closure "
        f"artifact_sha256={artifact_hash}"
    )
    print(json.dumps({
        "passed_constraint_ids": list(CONSTRAINT_IDS),
        "artifact_sha256": {"materials-manifest": artifact_hash},
        "measurements": measurements,
        "observables": {
            "storage-layout": ["archive-metadata-only", "work-real-materials"],
            "material-id-set": derived["material_ids"],
            "uncertainty-route-set": derived["uncertainty_routes"],
            "processing-closure-set": derived["processing_closures"],
        },
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
