#!/usr/bin/env python3
"""Build a Course Generator manifest incrementally without model-written glue code."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from finalize_manifest import reconcile_manifest
from index_sources import build_index_data


MATERIAL_TYPES = {"案例", "操作", "观点", "金句", "踩坑", "取舍", "疑问", "其他"}
SKIP_CODES = {"derived_duplicate", "meeting", "device", "chatter", "pure_repeat", "no_course_value", "authority_superseded"}
CHAPTER_RE = re.compile(r"^CH-[0-9]{2,3}$")
BLOCK_RE = re.compile(r"^BLK-[0-9]{5,}$")
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
IMAGE_RE = re.compile(r"!\[[^\]\n]*\]\((?:[^()\\\n]|\\.|\([^()\n]*\))*\)")
SPEAKER_TERM_RE = re.compile(r"讲者|主讲人|讲师(?!资格)")
SOURCE_FRAME_RE = re.compile(
    r"现场演示|课程现场|现场问答|本次分享中|根据原文|原文中|主讲人提到"
    r"|(?:课程|本次|上述|后续|前面)演示|演示(?:中|里|开始时|一开始|过程(?:中)?|环节)|给大家演示"
    r"|来自[^\n。]{0,24}(?:现场|讲课|课程)?实录|现场实录|这一轮体验里|把这一节与前面|整门课程到这里|回过头看"
)
FILLER_RE = re.compile(
    r"这样的一个|也而且|这个那个|的话就是说|比如说|就是说|我们我们|你我|他这个里面|什么什么"
    r"|我觉得|我有问题|你指的|还是不够|好像有|玩一玩"
)
AUDIT_PATCH_RE = re.compile(
    r"正文证据补丁|证据补丁|原文痕迹|覆盖足够长度以满足证据|面向门禁|生成过程术语"
    r"|\b(?:SRC|BLK|MAT|IMG)-(?:[0-9]{3,}|x{3,})\b",
    re.IGNORECASE,
)
ASCII_CJK_PUNCT_RE = re.compile(r"(?<=[\u3400-\u9fff])[,;:!?](?=[\u3400-\u9fffA-Za-z0-9\"“])")
GENERIC_COVERAGE_TERMS = {
    "ai", "agent", "skill", "word", "markdown", "内容", "结果", "过程", "任务", "工作",
    "方法", "材料", "操作", "课程", "生成", "进行", "这个", "可以",
}
LOW_SIGNAL_COVERAGE_RE = re.compile(
    r"(?:比如说|就是说|我觉得|我有问题|你像|我们做一个|做一个新|前面说|好像有|挺好(?:的)?|玩一玩|还是不够|你指的|除了[^，。；]{0,12}这些)"
)
LOW_SIGNAL_COVERAGE_PREFIX_RE = re.compile(
    r"^(?:我|你|他|她|我们|你们|他们|们)(?:有|觉|认|说|提|像|指|做|要|就|是|的|前|这|那)"
)
LOW_SIGNAL_COVERAGE_SUFFIX_RE = re.compile(r"(?:了|的|呢|吧|啊|哦|嘛)$")
DEFAULT_NEXT_BATCH_SIZE = 30
MAX_NEXT_BATCH_SIZE = 40
RICH_SOURCE_IMAGE_THRESHOLD = 12
SOURCE_IMAGES_PER_REQUIRED_READER_IMAGE = 20
CHAPTER_READER_DEPTH_RATIO = 0.40
MAX_CHAPTER_READER_EXPANSION_RATIO = 2.50
MAX_CHAPTER_READER_EXPANSION_FLOOR = 1400
MIN_MATERIAL_COUNT_BUDGET = 60
MATERIAL_COUNT_BUDGET_RATIO = 0.50


class BatchValidationError(ValueError):
    """Report every independently detectable batch error in one retry."""

    def __init__(self, errors: list[dict[str, Any]]):
        super().__init__(f"批次含 {len(errors)} 个校验错误")
        self.errors = errors


def material_count_budget(content_block_count: int) -> int:
    """Cap ledger fragmentation while leaving headroom for short sources."""
    return max(MIN_MATERIAL_COUNT_BUDGET, math.ceil(content_block_count * MATERIAL_COUNT_BUDGET_RATIO))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def rebuild_sources(
    source_root: Path,
    output_hint: Path,
    authority_mode: str = "current",
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, Any]]:
    payload, block_texts = build_index_data(source_root, output_hint, authority_mode)
    return payload["sources"], block_texts, payload["authority"]


def load_bound_index(index_path: Path, source_root: Path) -> tuple[dict[str, Any], dict[str, str]]:
    source_index = read_json(index_path)
    if not isinstance(source_index, dict) or source_index.get("schema_version") != "1.4":
        raise ValueError("source-index.schema_version 必须为 1.4")
    authority = source_index.get("authority")
    authority_mode = authority.get("mode") if isinstance(authority, dict) else None
    rebuilt_sources, block_texts, rebuilt_authority = rebuild_sources(source_root, index_path, authority_mode)
    if source_index.get("sources") != rebuilt_sources:
        raise ValueError("source-index 与当前 source-root 的确定性重建结果不一致")
    if authority != rebuilt_authority:
        raise ValueError("source-index.authority 与当前 source-root 的确定性重建结果不一致")
    return source_index, block_texts


def load_manifest_index(manifest_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    source_meta = manifest.get("source_index")
    if not isinstance(source_meta, dict) or not isinstance(source_meta.get("file"), str):
        raise ValueError("manifest.source_index.file 缺失或非法")
    index_path = (manifest_path.parent / source_meta["file"]).resolve()
    try:
        index_path.relative_to(manifest_path.parent)
    except ValueError as exc:
        raise ValueError("manifest.source_index.file 必须位于课程目录内") from exc
    if not index_path.is_file():
        raise ValueError(f"source-index 不存在: {index_path}")
    actual_sha256 = hashlib.sha256(index_path.read_bytes()).hexdigest()
    if source_meta.get("sha256") != actual_sha256:
        raise ValueError("manifest.source_index.sha256 与真实索引不一致")
    source_index = read_json(index_path)
    if not isinstance(source_index, dict) or source_index.get("schema_version") != "1.4":
        raise ValueError("source-index.schema_version 必须为 1.4")
    return source_index


def block_catalog(source_index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        block["id"]: block
        for source in source_index.get("sources") or []
        for block in source.get("blocks") or []
        if isinstance(block, dict) and isinstance(block.get("id"), str)
    }


def minimum_reader_image_count(manifest: dict[str, Any]) -> int:
    image_count = len(manifest.get("images") or [])
    if image_count < RICH_SOURCE_IMAGE_THRESHOLD:
        return 0
    document_count = 1 + len(manifest.get("chapters") or [])
    return min(document_count, math.ceil(image_count / SOURCE_IMAGES_PER_REQUIRED_READER_IMAGE))


def manifest_status(
    manifest: dict[str, Any],
    source_index: dict[str, Any],
    *,
    next_batch_size: int = DEFAULT_NEXT_BATCH_SIZE,
) -> dict[str, Any]:
    content_ids = {
        block["id"]
        for block in block_catalog(source_index).values()
        if block.get("kind") == "content"
    }
    covered = {
        block_id
        for material in manifest.get("materials") or []
        if isinstance(material, dict)
        for block_id in material.get("source_block_ids") or []
        if isinstance(block_id, str)
    }
    remaining = sorted(content_ids - covered)
    chapter_count = len(manifest.get("chapters") or [])
    section_count = sum(len(chapter.get("section_headings") or []) for chapter in manifest.get("chapters") or [] if isinstance(chapter, dict))
    selected_reader_images = sum(
        1
        for image in manifest.get("images") or []
        if isinstance(image, dict) and image.get("body_action") == "insert"
    )
    minimum_reader_images = minimum_reader_image_count(manifest)
    authority = manifest.get("source_authority") if isinstance(manifest.get("source_authority"), dict) else {}
    authority_notices = authority.get("notices") if isinstance(authority.get("notices"), list) else []
    authority_acknowledgements = authority.get("acknowledgements") if isinstance(authority.get("acknowledgements"), list) else []
    authority_corrections = authority.get("corrections") if isinstance(authority.get("corrections"), list) else []
    correction_routes = authority.get("correction_routes") if isinstance(authority.get("correction_routes"), list) else []
    source_blocks = block_catalog(source_index)
    authority_candidate_review_queue = [
        {
            "correction_id": correction.get("id"),
            "original_text": correction.get("original_text"),
            "revised_text": correction.get("revised_text"),
            "candidates": [
                {
                    "source_block_id": block_id,
                    "source_ref": source_blocks.get(block_id, {}).get("source_ref"),
                    "preview": source_blocks.get(block_id, {}).get("preview"),
                }
                for block_id in correction.get("superseded_candidate_block_ids") or []
            ],
        }
        for correction in authority_corrections
        if isinstance(correction, dict)
    ]
    authority_acknowledged = (
        [item.get("id") for item in authority_acknowledgements if isinstance(item, dict)]
        == [item.get("id") for item in authority_notices if isinstance(item, dict)]
    )
    authority_corrections_routed = (
        [item.get("id") for item in correction_routes if isinstance(item, dict)]
        == [item.get("id") for item in authority_corrections if isinstance(item, dict)]
    )
    if authority_notices and (not authority_acknowledged or not authority_corrections_routed):
        next_action = "read authority corrections and route every correction to one planned H2"
    elif chapter_count == 0:
        next_action = "run plan before merging materials"
    elif remaining:
        next_action = "merge exactly next_batch_content_block_ids; do not recompute remaining IDs"
    elif selected_reader_images < minimum_reader_images:
        next_action = "run ledger finalizer and preflight, then select representative images before writing"
    else:
        next_action = "run ledger finalizer and preflight, scaffold chapters, then write one chapter at a time"
    return {
        "content_block_count": len(content_ids),
        "maximum_material_count": material_count_budget(len(content_ids)),
        "covered_content_block_count": len(content_ids & covered),
        "remaining_content_block_count": len(remaining),
        "remaining_content_block_ids": remaining[:40],
        "next_batch_size": next_batch_size,
        "next_batch_content_block_ids": remaining[:next_batch_size],
        "material_count": len(manifest.get("materials") or []),
        "chapter_count": chapter_count,
        "section_count": section_count,
        "source_image_count": len(manifest.get("images") or []),
        "selected_reader_image_count": selected_reader_images,
        "minimum_reader_image_count": minimum_reader_images,
        "authority_mode": authority.get("mode", "current"),
        "authority_notice_count": len(authority_notices),
        "authority_acknowledged": authority_acknowledged,
        "authority_notices": authority_notices,
        "authority_correction_count": len(authority_corrections),
        "authority_corrections_routed": authority_corrections_routed,
        "authority_corrections": authority_corrections,
        "authority_candidate_review_queue": authority_candidate_review_queue,
        "ledger_complete": bool(content_ids) and not remaining and chapter_count > 0 and section_count > 0,
        "next_action": next_action,
    }


def command_init(args: argparse.Namespace) -> dict[str, Any]:
    index_path = args.source_index.expanduser().resolve()
    manifest_path = args.manifest.expanduser().resolve()
    if manifest_path.exists():
        raise ValueError(f"manifest 已存在，拒绝覆盖: {manifest_path}")
    try:
        index_relative = index_path.relative_to(manifest_path.parent).as_posix()
    except ValueError as exc:
        raise ValueError("source-index 必须位于课程目录内") from exc
    source_index, block_texts = load_bound_index(index_path, args.source_root)
    images: list[dict[str, Any]] = []
    for block in block_catalog(source_index).values():
        if block.get("kind") != "image":
            continue
        image_id = f"IMG-{len(images) + 1:03d}"
        images.append(
            {
                "id": image_id,
                "source_ref": block["source_ref"],
                "original_markdown": block_texts[block["id"]],
                "body_action": "asset_only",
                "target_document_id": None,
                "reason": "尚未筛选正文代表图。",
            }
        )
    manifest = {
        "schema_version": "1.8",
        "generator_version": "2.10.0",
        "course": {"title": args.title},
        "sources": [{"id": source["id"], "path": source["path"]} for source in source_index["sources"]],
        "source_index": {"file": index_relative, "sha256": hashlib.sha256(index_path.read_bytes()).hexdigest()},
        "source_authority": {
            "mode": source_index["authority"]["mode"],
            "notices": source_index["authority"]["notices"],
            "corrections": source_index["authority"]["corrections"],
            "acknowledgements": [],
            "correction_routes": [],
        },
        "overview": {"file": args.overview_file, "image_ids": []},
        "chapters": [],
        "materials": [],
        "images": images,
    }
    write_json_atomic(manifest_path, manifest)
    return {"status": "PASS", "action": "init", "manifest": str(manifest_path), **manifest_status(manifest, source_index)}


def command_plan(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = args.manifest.expanduser().resolve()
    manifest = read_json(manifest_path)
    source_index = load_manifest_index(manifest_path, manifest)
    source_block_catalog = block_catalog(source_index)
    if manifest.get("materials"):
        raise ValueError("materials 非空后不得重建章节计划；请在合并素材前完成 plan")
    plan = read_json(args.plan.expanduser().resolve())
    authority = manifest.get("source_authority") if isinstance(manifest.get("source_authority"), dict) else {}
    notices = authority.get("notices") if isinstance(authority.get("notices"), list) else []
    raw_acknowledgements = plan.get("authority_acknowledgements") if isinstance(plan, dict) else None
    if notices:
        if not isinstance(raw_acknowledgements, list) or len(raw_acknowledgements) != len(notices):
            raise ValueError("plan.authority_acknowledgements 必须逐项确认全部来源权威声明")
        acknowledgements: list[dict[str, Any]] = []
        for notice, raw in zip(notices, raw_acknowledgements):
            if not isinstance(raw, dict) or raw.get("id") != notice.get("id"):
                raise ValueError(f"authority acknowledgement 必须按顺序确认 {notice.get('id')}")
            expected_controls = notice.get("controlling_source_ids") or []
            mode = authority.get("mode")
            if mode == "current":
                if raw.get("action") != "apply_control" or raw.get("controlling_source_ids") != expected_controls:
                    raise ValueError(
                        f"{notice.get('id')} 必须使用 action=apply_control 并精确确认 controlling_source_ids={expected_controls!r}"
                    )
                if not expected_controls:
                    raise ValueError(f"{notice.get('id')} current 模式缺少已解析控制来源")
                acknowledgements.append(
                    {
                        "id": notice["id"],
                        "action": "apply_control",
                        "controlling_source_ids": expected_controls,
                        "reader_notice": None,
                    }
                )
            elif mode == "historical":
                reader_notice = raw.get("reader_notice")
                if raw.get("action") != "historical_disclaimer" or not isinstance(reader_notice, str) or len(reader_notice.strip()) < 12:
                    raise ValueError(
                        f"{notice.get('id')} historical 模式必须使用 action=historical_disclaimer 并提供至少 12 字 reader_notice"
                    )
                acknowledgements.append(
                    {
                        "id": notice["id"],
                        "action": "historical_disclaimer",
                        "controlling_source_ids": [],
                        "reader_notice": reader_notice.strip(),
                    }
                )
            else:
                raise ValueError(f"未知 source_authority.mode: {mode!r}")
        manifest["source_authority"]["acknowledgements"] = acknowledgements
    elif raw_acknowledgements not in (None, []):
        raise ValueError("来源没有权威声明时不得虚构 authority_acknowledgements")
    chapters = plan.get("chapters") if isinstance(plan, dict) else None
    if not isinstance(chapters, list) or not chapters:
        raise ValueError("plan.chapters 必须是非空数组")
    max_chapters = getattr(args, "max_chapters", 8)
    if not isinstance(max_chapters, int) or max_chapters < 1:
        raise ValueError("max_chapters 必须为正整数")
    if len(chapters) > max_chapters:
        raise ValueError(
            f"plan 含 {len(chapters)} 章，超过当前上限 {max_chapters}；"
            "先合并结构性薄章，只有用户明确要求超过 8 章时才读取高级覆盖说明"
        )
    records: list[dict[str, Any]] = []
    seen_files: set[str] = set()
    for index, raw in enumerate(chapters, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"plan.chapters[{index}] 必须是对象")
        file_name = raw.get("file")
        title = raw.get("title")
        headings = raw.get("section_headings")
        if not isinstance(file_name, str) or not re.fullmatch(r"[0-9]{2}[ _-].+\.md", file_name):
            raise ValueError(f"plan.chapters[{index}].file 必须是两位编号 Markdown 文件")
        if file_name in seen_files:
            raise ValueError(f"重复章节文件: {file_name}")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"plan.chapters[{index}].title 必须非空")
        if not isinstance(headings, list) or not headings or not all(isinstance(item, str) and item.strip() for item in headings):
            raise ValueError(f"plan.chapters[{index}].section_headings 必须是非空字符串数组")
        normalized = [item.strip() for item in headings]
        if len(set(normalized)) != len(normalized):
            raise ValueError(f"plan.chapters[{index}].section_headings 不得重复")
        seen_files.add(file_name)
        records.append(
            {
                "id": f"CH-{index:02d}",
                "file": file_name,
                "title": title.strip(),
                "section_headings": normalized,
                "source_refs": [],
                "material_ids": [],
                "image_ids": [],
            }
        )
    manifest["chapters"] = records
    corrections = authority.get("corrections") if isinstance(authority.get("corrections"), list) else []
    raw_routes = plan.get("authority_correction_routes") if isinstance(plan, dict) else None
    if corrections:
        if not isinstance(raw_routes, list) or len(raw_routes) != len(corrections):
            raise ValueError("plan.authority_correction_routes 必须逐项路由全部控制文档修正")
        chapter_catalog = {chapter["id"]: chapter for chapter in records}
        routes: list[dict[str, Any]] = []
        all_candidate_reviews: list[dict[str, str]] = []
        for correction, raw in zip(corrections, raw_routes):
            correction_id = correction.get("id")
            if not isinstance(raw, dict) or raw.get("id") != correction_id:
                raise ValueError(f"authority correction route 必须按顺序确认 {correction_id}")
            chapter_id = raw.get("target_chapter_id")
            section_heading = raw.get("target_section_heading")
            chapter = chapter_catalog.get(chapter_id)
            if chapter is None:
                raise ValueError(f"{correction_id} 指向不存在的章节 {chapter_id!r}")
            if not isinstance(section_heading, str) or section_heading not in chapter["section_headings"]:
                raise ValueError(f"{correction_id} 指向未声明的小节 {section_heading!r}")
            supersession_status = raw.get("supersession_status")
            superseded_ids = raw.get("superseded_source_block_ids")
            supersession_note = raw.get("supersession_note")
            raw_candidate_reviews = raw.get("candidate_block_reviews")
            expected_candidate_ids = correction.get("superseded_candidate_block_ids") or []
            if supersession_status not in {"blocks_identified", "no_matching_source_block"}:
                raise ValueError(
                    f"{correction_id}.supersession_status 必须为 blocks_identified 或 no_matching_source_block"
                )
            if (
                not isinstance(superseded_ids, list)
                or not all(isinstance(item, str) and BLOCK_RE.fullmatch(item) for item in superseded_ids)
                or len(set(superseded_ids)) != len(superseded_ids)
            ):
                raise ValueError(f"{correction_id}.superseded_source_block_ids 必须是无重复 BLK-xxxxx 数组")
            for block_id in superseded_ids:
                block = source_block_catalog.get(block_id)
                if not block or block.get("kind") != "content":
                    raise ValueError(f"{correction_id} 只能把普通 content block 标记为被修订替代: {block_id}")
            if supersession_status == "blocks_identified" and not superseded_ids:
                raise ValueError(f"{correction_id} 标记 blocks_identified 时必须列出被替代来源块")
            if supersession_status == "no_matching_source_block" and superseded_ids:
                raise ValueError(f"{correction_id} 标记 no_matching_source_block 时来源块列表必须为空")
            if not isinstance(supersession_note, str) or len(supersession_note.strip()) < 12:
                raise ValueError(f"{correction_id}.supersession_note 必须写明检索与判断依据，至少 12 字")
            if not isinstance(raw_candidate_reviews, list):
                raise ValueError(f"{correction_id}.candidate_block_reviews 必须逐项审查全部候选来源块")
            candidate_reviews: list[dict[str, str]] = []
            reviewed_candidate_ids: list[str] = []
            normalized_review_reasons: list[str] = []
            for review_index, review in enumerate(raw_candidate_reviews, 1):
                if not isinstance(review, dict):
                    raise ValueError(f"{correction_id}.candidate_block_reviews[{review_index}] 必须是对象")
                block_id = review.get("source_block_id")
                decision = review.get("decision")
                reason = review.get("reason")
                evidence_quote = review.get("evidence_quote")
                if not isinstance(block_id, str) or not BLOCK_RE.fullmatch(block_id):
                    raise ValueError(f"{correction_id}.candidate_block_reviews[{review_index}].source_block_id 非法")
                if decision not in {"superseded", "retained_current"}:
                    raise ValueError(
                        f"{correction_id}.candidate_block_reviews[{review_index}].decision 必须为 superseded 或 retained_current"
                    )
                if not isinstance(reason, str) or len(reason.strip()) < 12:
                    raise ValueError(f"{correction_id}.candidate_block_reviews[{review_index}].reason 必须至少 12 字")
                candidate_preview = str(source_block_catalog.get(block_id, {}).get("preview") or "")
                if not isinstance(evidence_quote, str) or len(evidence_quote.strip()) < 6:
                    raise ValueError(
                        f"{correction_id}.candidate_block_reviews[{review_index}].evidence_quote 必须摘录至少 6 字候选预览原文"
                    )
                if evidence_quote.strip() not in candidate_preview:
                    raise ValueError(
                        f"{correction_id}.candidate_block_reviews[{review_index}].evidence_quote 必须逐字来自该候选预览"
                    )
                reviewed_candidate_ids.append(block_id)
                normalized_review_reasons.append(re.sub(r"\s+", "", reason).casefold())
                candidate_reviews.append(
                    {
                        "source_block_id": block_id,
                        "decision": decision,
                        "evidence_quote": evidence_quote.strip(),
                        "reason": reason.strip(),
                    }
                )
            if reviewed_candidate_ids != expected_candidate_ids:
                raise ValueError(
                    f"{correction_id}.candidate_block_reviews 必须按索引顺序逐项覆盖候选块；"
                    f"期望 {expected_candidate_ids!r}，实际 {reviewed_candidate_ids!r}"
                )
            if len(normalized_review_reasons) > 1 and len(set(normalized_review_reasons)) == 1:
                raise ValueError(f"{correction_id}.candidate_block_reviews 不得为全部候选复制同一判断理由")
            superseded_candidate_ids = {
                review["source_block_id"]
                for review in candidate_reviews
                if review["decision"] == "superseded"
            }
            retained_candidate_ids = {
                review["source_block_id"]
                for review in candidate_reviews
                if review["decision"] == "retained_current"
            }
            if superseded_candidate_ids - set(superseded_ids):
                raise ValueError(
                    f"{correction_id} 判定 superseded 的候选块必须进入 superseded_source_block_ids: "
                    f"{sorted(superseded_candidate_ids - set(superseded_ids))!r}"
                )
            if retained_candidate_ids & set(superseded_ids):
                raise ValueError(
                    f"{correction_id} 判定 retained_current 的候选块不得进入 superseded_source_block_ids: "
                    f"{sorted(retained_candidate_ids & set(superseded_ids))!r}"
                )
            routes.append(
                {
                    "id": correction_id,
                    "target_chapter_id": chapter_id,
                    "target_section_heading": section_heading,
                    "supersession_status": supersession_status,
                    "superseded_source_block_ids": superseded_ids,
                    "supersession_note": supersession_note.strip(),
                    "candidate_block_reviews": candidate_reviews,
                }
            )
            all_candidate_reviews.extend(candidate_reviews)
        if len(all_candidate_reviews) >= 12 and all(
            review["decision"] == "superseded" for review in all_candidate_reviews
        ):
            raise ValueError("候选审查不得把整张高召回矩阵一律判为 superseded；须逐块区分旧结论与相邻主题")
        manifest["source_authority"]["correction_routes"] = routes
    elif raw_routes not in (None, []):
        raise ValueError("来源没有结构化修正表时不得虚构 authority_correction_routes")
    if isinstance(plan.get("course_title"), str) and plan["course_title"].strip():
        manifest["course"]["title"] = plan["course_title"].strip()
    if isinstance(plan.get("overview_file"), str) and plan["overview_file"].strip():
        manifest["overview"]["file"] = plan["overview_file"].strip()
    write_json_atomic(manifest_path, manifest)
    return {"status": "PASS", "action": "plan", **manifest_status(manifest, source_index)}


def coverage_term_candidates(text: str, limit: int = 12) -> list[str]:
    """Return deterministic exact-source anchors to reduce weak-model retry loops."""
    patterns = (
        re.compile(r"`([^`\n]{2,40})`"),
        re.compile(r"\b[A-Za-z][A-Za-z0-9_.+/#-]{1,39}\b"),
        re.compile(r"\d+(?:\.\d+)?(?:%|％|亿元|万元|元|年|月|日|次|条|页|个|分钟|秒|GB|MB|K)?"),
        re.compile(r"[\u4e00-\u9fff]{2,12}"),
    )
    candidates: list[str] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            value = (match.group(1) if match.lastindex else match.group(0)).strip()
            if (
                len(value) < 2
                or value.casefold() in GENERIC_COVERAGE_TERMS
                or low_signal_coverage_term(value)
                or value in candidates
            ):
                continue
            candidates.append(value)
            if len(candidates) >= limit:
                return candidates
    return candidates


def low_signal_coverage_term(value: str) -> bool:
    """Reject transcript fragments that make weak models write audit-shaped prose."""
    normalized = re.sub(r"\s+", "", value.strip())
    if not normalized:
        return True
    if LOW_SIGNAL_COVERAGE_RE.search(normalized) or LOW_SIGNAL_COVERAGE_PREFIX_RE.search(normalized):
        return True
    return bool(re.fullmatch(r"[\u4e00-\u9fff]+", normalized) and LOW_SIGNAL_COVERAGE_SUFFIX_RE.search(normalized))


def authority_superseded_blocks(manifest: dict[str, Any]) -> set[str]:
    authority = manifest.get("source_authority") if isinstance(manifest.get("source_authority"), dict) else {}
    return {
        block_id
        for route in authority.get("correction_routes") or []
        if isinstance(route, dict)
        for block_id in route.get("superseded_source_block_ids") or []
        if isinstance(block_id, str)
    }


def normalize_batch_entry(
    raw: Any,
    ordinal: int,
    manifest: dict[str, Any],
    catalog: dict[str, dict[str, Any]],
    block_texts: dict[str, str],
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("batch.materials 每项必须是对象")
    disposition = raw.get("disposition")
    if disposition not in {"include", "skip"}:
        raise ValueError("disposition 必须为 include 或 skip")
    material_type = raw.get("type")
    if material_type not in MATERIAL_TYPES:
        raise ValueError(f"非法素材类型: {material_type!r}")
    summary = raw.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("summary 必须非空")
    block_ids = raw.get("source_block_ids")
    if not isinstance(block_ids, list) or not block_ids or not all(isinstance(item, str) and BLOCK_RE.fullmatch(item) for item in block_ids):
        raise ValueError("source_block_ids 必须是非空 BLK-xxxxx 数组")
    if len(set(block_ids)) != len(block_ids):
        raise ValueError("单个素材的 source_block_ids 不得重复")
    blocks = []
    for block_id in block_ids:
        block = catalog.get(block_id)
        if not block or block.get("kind") != "content":
            raise ValueError(f"素材只能引用存在的 content block: {block_id}")
        blocks.append(block)
    superseded_blocks = authority_superseded_blocks(manifest)
    bound_superseded = sorted(set(block_ids) & superseded_blocks)
    source_refs: list[str] = []
    for block in blocks:
        if block["source_ref"] not in source_refs:
            source_refs.append(block["source_ref"])
    record: dict[str, Any] = {
        "id": f"MAT-{ordinal:03d}",
        "type": material_type,
        "summary": summary.strip(),
        "source_refs": source_refs,
        "source_block_ids": block_ids,
        "coverage_terms": [],
        "disposition": disposition,
        "target_chapter_id": None,
        "target_section_heading": None,
        "reader_evidence": None,
    }
    if disposition == "include":
        if bound_superseded:
            raise ValueError(
                f"被当前修订替代的来源块只能使用 skip_code=authority_superseded: {', '.join(bound_superseded)}"
            )
        if len(block_ids) > 6:
            raise ValueError("include 素材最多绑定 6 个来源块")
        terms = raw.get("coverage_terms")
        bound_text = "\n".join(block_texts[block_id] for block_id in block_ids)
        suggestions = coverage_term_candidates(bound_text)
        if not isinstance(terms, list) or not 1 <= len(terms) <= 3 or not all(isinstance(item, str) and len(item.strip()) >= 2 for item in terms):
            raise ValueError(f"include 素材必须提供 1—3 个 coverage_terms；可直接选用来源候选 {suggestions!r}")
        normalized_terms = [item.strip() for item in terms]
        if len(set(normalized_terms)) != len(normalized_terms):
            raise ValueError("coverage_terms 不得重复")
        required_term_count = max(1, min(3, math.ceil(len(block_ids) / 3)))
        if len(normalized_terms) < required_term_count:
            raise ValueError(
                f"覆盖 {len(block_ids)} 个来源块时至少需要 {required_term_count} 个具体 coverage_terms"
            )
        if all(term.casefold() in GENERIC_COVERAGE_TERMS for term in normalized_terms):
            raise ValueError("coverage_terms 不能全是 AI/Agent/Skill 等通用词")
        for term in normalized_terms:
            if low_signal_coverage_term(term):
                raise ValueError(
                    f"coverage term 是口语指代、语气词或截断片段: {term!r}；请选择步骤、结果、数字、限制或专名"
                )
            if term not in bound_text:
                raise ValueError(f"coverage term 未出现在绑定来源块: {term!r}；可直接选用来源候选 {suggestions!r}")
        chapter_id = raw.get("target_chapter_id")
        section_heading = raw.get("target_section_heading")
        chapters = {chapter.get("id"): chapter for chapter in manifest.get("chapters") or [] if isinstance(chapter, dict)}
        chapter = chapters.get(chapter_id)
        if not CHAPTER_RE.fullmatch(str(chapter_id)) or chapter is None:
            raise ValueError(f"目标章节不存在: {chapter_id!r}")
        if not isinstance(section_heading, str) or section_heading not in chapter.get("section_headings", []):
            raise ValueError(f"目标小节未在 {chapter_id} 声明: {section_heading!r}")
        record["coverage_terms"] = normalized_terms
        record["target_chapter_id"] = chapter_id
        record["target_section_heading"] = section_heading
    else:
        skip_code = raw.get("skip_code")
        skip_reason = raw.get("skip_reason")
        if skip_code not in SKIP_CODES or not isinstance(skip_reason, str) or not skip_reason.strip():
            raise ValueError("skip 素材必须提供受控 skip_code 与具体 skip_reason")
        if bound_superseded and skip_code != "authority_superseded":
            raise ValueError(
                f"被当前修订替代的来源块必须使用 skip_code=authority_superseded: {', '.join(bound_superseded)}"
            )
        if skip_code == "authority_superseded" and set(block_ids) - superseded_blocks:
            raise ValueError("authority_superseded 只能用于 plan 已确认被当前修订替代的来源块")
        record["skip_code"] = skip_code
        record["skip_reason"] = skip_reason.strip()
    return record


def material_signature(material: dict[str, Any]) -> str:
    stable = {
        "type": material.get("type"),
        "summary": material.get("summary"),
        "source_block_ids": material.get("source_block_ids"),
        "coverage_terms": material.get("coverage_terms"),
        "disposition": material.get("disposition"),
        "target_chapter_id": material.get("target_chapter_id"),
        "target_section_heading": material.get("target_section_heading"),
        "skip_code": material.get("skip_code"),
        "skip_reason": material.get("skip_reason"),
    }
    return json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def command_merge(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = args.manifest.expanduser().resolve()
    manifest = read_json(manifest_path)
    if not manifest.get("chapters"):
        raise ValueError("请先运行 plan 建立章节与小节计划")
    load_manifest_index(manifest_path, manifest)
    index_path = (manifest_path.parent / manifest["source_index"]["file"]).resolve()
    source_index, block_texts = load_bound_index(index_path, args.source_root)
    batch = read_json(args.batch.expanduser().resolve())
    entries = batch.get("materials") if isinstance(batch, dict) else batch
    if not isinstance(entries, list) or not entries:
        raise ValueError("batch 必须是非空数组，或包含非空 materials 数组")
    catalog = block_catalog(source_index)
    existing = [item for item in manifest.get("materials") or [] if isinstance(item, dict)]
    known_signatures = {material_signature(material) for material in existing}
    existing_dispositions: dict[str, set[str]] = {}
    for material in existing:
        for block_id in material.get("source_block_ids") or []:
            existing_dispositions.setdefault(block_id, set()).add(str(material.get("disposition")))
    normalized_entries: list[tuple[int, dict[str, Any]]] = []
    validation_errors: list[dict[str, Any]] = []
    for entry_index, raw in enumerate(entries, 1):
        try:
            record = normalize_batch_entry(raw, 1, manifest, catalog, block_texts)
        except (ValueError, KeyError) as exc:
            validation_errors.append({"entry_index": entry_index, "message": str(exc)})
            continue
        normalized_entries.append((entry_index, record))
    if validation_errors:
        raise BatchValidationError(validation_errors)

    additions: list[dict[str, Any]] = []
    duplicate_count = 0
    for entry_index, record in normalized_entries:
        signature = material_signature(record)
        if signature in known_signatures:
            duplicate_count += 1
            continue
        conflicting_blocks: list[str] = []
        for block_id in record["source_block_ids"]:
            dispositions = existing_dispositions.get(block_id, set())
            if dispositions and record["disposition"] not in dispositions:
                conflicting_blocks.append(block_id)
        if conflicting_blocks:
            validation_errors.append(
                {
                    "entry_index": entry_index,
                    "message": f"{', '.join(conflicting_blocks)} 不得同时 include 与 skip",
                }
            )
            continue
        record["id"] = f"MAT-{len(existing) + len(additions) + 1:03d}"
        additions.append(record)
        known_signatures.add(signature)
        for block_id in record["source_block_ids"]:
            existing_dispositions.setdefault(block_id, set()).add(record["disposition"])
    if validation_errors:
        raise BatchValidationError(validation_errors)
    maximum_materials = material_count_budget(sum(1 for block in catalog.values() if block.get("kind") == "content"))
    if len(existing) + len(additions) > maximum_materials:
        raise BatchValidationError(
            [
                {
                    "entry_index": 0,
                    "message": (
                        f"合并后将有 {len(existing) + len(additions)} 项素材，超过 {maximum_materials} 项预算；"
                        "请合并同一观点、连续操作阶段或同一 skip 理由，不要按发言片段或微步骤逐块建素材"
                    ),
                }
            ]
        )
    manifest["materials"] = existing + additions
    write_json_atomic(manifest_path, manifest)
    reconcile = reconcile_manifest(manifest_path, write=True, phase="ledger")
    current = read_json(manifest_path)
    return {
        "status": "PASS",
        "action": "merge",
        "added_material_count": len(additions),
        "duplicate_material_count": duplicate_count,
        "ledger_reconcile_unresolved_count": reconcile["unresolved_count"],
        **manifest_status(current, source_index),
    }


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = args.manifest.expanduser().resolve()
    manifest = read_json(manifest_path)
    source_index = load_manifest_index(manifest_path, manifest)
    next_batch_size = getattr(args, "next_batch_size", DEFAULT_NEXT_BATCH_SIZE)
    if not 1 <= next_batch_size <= MAX_NEXT_BATCH_SIZE:
        raise ValueError(f"next-batch-size 必须在 1—{MAX_NEXT_BATCH_SIZE} 之间")
    return {
        "status": "PASS",
        "action": "status",
        **manifest_status(manifest, source_index, next_batch_size=next_batch_size),
    }


def command_select_images(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = args.manifest.expanduser().resolve()
    manifest = read_json(manifest_path)
    source_index = load_manifest_index(manifest_path, manifest)
    status = manifest_status(manifest, source_index)
    if not status["ledger_complete"]:
        raise ValueError("素材账本未完整，不得提前选择正文图片")
    payload = read_json(args.selection.expanduser().resolve())
    selections = payload.get("selections") if isinstance(payload, dict) else payload
    if not isinstance(selections, list):
        raise ValueError("图片选择必须是数组，或包含 selections 数组")
    image_records = {
        image.get("id"): image
        for image in manifest.get("images") or []
        if isinstance(image, dict) and isinstance(image.get("id"), str)
    }
    valid_targets = {"OVERVIEW"} | {
        chapter.get("id")
        for chapter in manifest.get("chapters") or []
        if isinstance(chapter, dict) and isinstance(chapter.get("id"), str)
    }
    normalized: dict[str, dict[str, str]] = {}
    errors: list[dict[str, Any]] = []
    for entry_index, raw in enumerate(selections, 1):
        if not isinstance(raw, dict):
            errors.append({"entry_index": entry_index, "message": "图片选择项必须是对象"})
            continue
        image_id = raw.get("id")
        target = raw.get("target_document_id")
        reason = raw.get("reason")
        if image_id not in image_records:
            errors.append({"entry_index": entry_index, "message": f"图片不存在: {image_id!r}"})
        elif image_id in normalized:
            errors.append({"entry_index": entry_index, "message": f"图片重复选择: {image_id}"})
        elif target not in valid_targets:
            errors.append({"entry_index": entry_index, "message": f"目标文档不存在: {target!r}"})
        elif not isinstance(reason, str) or not reason.strip():
            errors.append({"entry_index": entry_index, "message": "reason 必须具体且非空"})
        else:
            normalized[image_id] = {"target_document_id": target, "reason": reason.strip()}
    minimum = minimum_reader_image_count(manifest)
    if len(normalized) < minimum:
        errors.append(
            {
                "entry_index": None,
                "message": f"来源图片要求至少选择 {minimum} 张正文代表图，实际 {len(normalized)} 张",
            }
        )
    if errors:
        raise BatchValidationError(errors)

    manifest["overview"]["image_ids"] = []
    chapter_records = {
        chapter["id"]: chapter
        for chapter in manifest.get("chapters") or []
        if isinstance(chapter, dict) and isinstance(chapter.get("id"), str)
    }
    for chapter in chapter_records.values():
        chapter["image_ids"] = []
    for image in manifest.get("images") or []:
        image_id = image.get("id") if isinstance(image, dict) else None
        selection = normalized.get(image_id)
        if selection is None:
            image["body_action"] = "asset_only"
            image["target_document_id"] = None
            image["reason"] = "未被选为正文代表图，保留在资产账本。"
            continue
        target = selection["target_document_id"]
        image["body_action"] = "insert"
        image["target_document_id"] = target
        image["reason"] = selection["reason"]
        if target == "OVERVIEW":
            manifest["overview"]["image_ids"].append(image_id)
        else:
            chapter_records[target]["image_ids"].append(image_id)
    write_json_atomic(manifest_path, manifest)
    return {
        "status": "PASS",
        "action": "select-images",
        "selected_reader_image_count": len(normalized),
        **manifest_status(manifest, source_index),
    }


def command_scaffold(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = args.manifest.expanduser().resolve()
    manifest = read_json(manifest_path)
    source_index = load_manifest_index(manifest_path, manifest)
    status = manifest_status(manifest, source_index)
    if not status["ledger_complete"]:
        raise ValueError("素材账本未完整，不得提前生成章节脚手架")
    if status["selected_reader_image_count"] < status["minimum_reader_image_count"]:
        raise ValueError("正文代表图未达到最低数量，不得提前生成章节脚手架")
    included_targets = {
        (material.get("target_chapter_id"), material.get("target_section_heading"))
        for material in manifest.get("materials") or []
        if isinstance(material, dict) and material.get("disposition") == "include"
    }
    empty_sections = [
        f"{chapter.get('id')}::{heading}"
        for chapter in manifest.get("chapters") or []
        if isinstance(chapter, dict)
        for heading in chapter.get("section_headings") or []
        if (chapter.get("id"), heading) not in included_targets
    ]
    if empty_sections:
        raise ValueError(f"以下 H2 没有绑定 include 素材，拒绝生成空架构: {', '.join(empty_sections)}")
    created: list[str] = []
    existing: list[str] = []
    authority = manifest.get("source_authority") if isinstance(manifest.get("source_authority"), dict) else {}
    correction_catalog = {
        item.get("id"): item
        for item in authority.get("corrections") or []
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    required_by_section: dict[tuple[str, str], list[str]] = {}
    for route in authority.get("correction_routes") or []:
        if not isinstance(route, dict):
            continue
        correction = correction_catalog.get(route.get("id"))
        if correction and isinstance(correction.get("revised_text"), str):
            required_by_section.setdefault(
                (str(route.get("target_chapter_id")), str(route.get("target_section_heading"))),
                [],
            ).append(correction["revised_text"])
    for chapter in manifest.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        file_name = chapter.get("file")
        title = chapter.get("title")
        headings = chapter.get("section_headings")
        if not isinstance(file_name, str) or not isinstance(title, str) or not isinstance(headings, list):
            raise ValueError("manifest 章节计划不完整，无法生成脚手架")
        path = manifest_path.parent / file_name
        if path.exists():
            text = path.read_text(encoding="utf-8")
            actual_h1 = H1_RE.findall(text)
            actual_h2 = H2_RE.findall(text)
            if actual_h1 != [title] or actual_h2 != headings:
                raise ValueError(f"既有章节标题与 manifest 不一致，拒绝覆盖: {file_name}")
            missing_corrections = [
                required
                for heading in headings
                for required in required_by_section.get((chapter["id"], heading), [])
                if required not in text
            ]
            if missing_corrections:
                raise ValueError(f"既有章节缺少工具注入的权威修正句，拒绝静默改写: {file_name}")
            existing.append(file_name)
            continue
        section_parts: list[str] = []
        for heading in headings:
            required_texts = required_by_section.get((chapter["id"], heading), [])
            section = f"## {heading}\n"
            if required_texts:
                section += "\n" + "\n\n".join(f"> **关键规则：** {text}" for text in required_texts) + "\n"
            section_parts.append(section)
        body = f"# {title}\n\n" + "\n\n".join(section_parts)
        write_text_atomic(path, body.rstrip() + "\n")
        created.append(file_name)
    return {"status": "PASS", "action": "scaffold", "created": created, "existing": existing}


def h2_sections(text: str) -> tuple[list[str], dict[str, str]]:
    matches = list(H2_RE.finditer(text))
    headings = [match.group(1).strip() for match in matches]
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[headings[index]] = text[match.end():end]
    return headings, sections


def pattern_hits(text: str, pattern: re.Pattern[str], limit: int = 8) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for match in pattern.finditer(text):
        hits.append({"line": text.count("\n", 0, match.start()) + 1, "text": match.group(0)})
        if len(hits) >= limit:
            break
    return hits


def style_prose(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`[^`\n]+`", "", text)
    return IMAGE_RE.sub("", text)


def repeated_paragraph_pairs(text: str) -> list[tuple[int, int, float]]:
    paragraphs: list[str] = []
    for raw in re.split(r"\n\s*\n", style_prose(text)):
        value = raw.strip()
        if not value or value.startswith(("#", ">", "|", "![")):
            continue
        normalized = re.sub(r"[^\w\u3400-\u9fff]+", "", value.casefold())
        if len(normalized) >= 120:
            paragraphs.append(normalized)
    grams = [{value[index : index + 5] for index in range(len(value) - 4)} for value in paragraphs]
    pairs: list[tuple[int, int, float]] = []
    for left in range(len(grams)):
        for right in range(left + 1, len(grams)):
            overlap = len(grams[left] & grams[right])
            denominator = min(len(grams[left]), len(grams[right]))
            ratio = overlap / denominator if denominator else 0.0
            if overlap >= 60 and ratio >= 0.40:
                pairs.append((left + 1, right + 1, ratio))
    return pairs


def command_check_chapter(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = args.manifest.expanduser().resolve()
    manifest = read_json(manifest_path)
    chapter = next(
        (
            item
            for item in manifest.get("chapters") or []
            if isinstance(item, dict) and item.get("id") == args.document
        ),
        None,
    )
    if chapter is None:
        raise ValueError(f"章节不存在: {args.document}")
    path = manifest_path.parent / chapter["file"]
    if not path.is_file():
        return {
            "status": "FAIL",
            "action": "check-chapter",
            "document": args.document,
            "errors": [{"code": "MISSING_FILE", "message": f"章节文件不存在: {chapter['file']}"}],
        }
    text = path.read_text(encoding="utf-8")
    errors: list[dict[str, Any]] = []
    h1_values = H1_RE.findall(text)
    headings, sections = h2_sections(text)
    if h1_values != [chapter["title"]]:
        errors.append({"code": "H1_MISMATCH", "message": f"H1 必须精确等于 {chapter['title']!r}"})
    if headings != chapter.get("section_headings"):
        errors.append(
            {
                "code": "H2_MISMATCH",
                "message": "H2 的文字、数量和顺序必须与 manifest 完全一致",
                "actual": headings,
                "expected": chapter.get("section_headings"),
            }
        )
    included_materials = [
        material
        for material in manifest.get("materials") or []
        if isinstance(material, dict)
        and material.get("disposition") == "include"
        and material.get("target_chapter_id") == args.document
    ]
    if not included_materials:
        errors.append({"code": "NO_INCLUDED_MATERIAL", "message": "本章没有绑定 include 素材"})
    authority = manifest.get("source_authority") if isinstance(manifest.get("source_authority"), dict) else {}
    correction_catalog = {
        item.get("id"): item
        for item in authority.get("corrections") or []
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    for route in authority.get("correction_routes") or []:
        if not isinstance(route, dict) or route.get("target_chapter_id") != args.document:
            continue
        correction = correction_catalog.get(route.get("id"))
        section_heading = route.get("target_section_heading")
        revised_text = correction.get("revised_text") if isinstance(correction, dict) else None
        if not isinstance(revised_text, str) or revised_text not in sections.get(str(section_heading), ""):
            errors.append(
                {
                    "code": "AUTHORITY_CORRECTION_MISSING",
                    "correction_id": route.get("id"),
                    "section": section_heading,
                }
            )
    folded_text = text.casefold()
    for correction in correction_catalog.values():
        for term in correction.get("deprecated_terms") or []:
            if isinstance(term, str) and term.casefold() in folded_text:
                errors.append(
                    {
                        "code": "DEPRECATED_AUTHORITY_TERM",
                        "correction_id": correction.get("id"),
                        "term": term,
                    }
                )
    for material in included_materials:
        section = material.get("target_section_heading")
        section_text = sections.get(str(section), "")
        missing_terms = [term for term in material.get("coverage_terms") or [] if term not in section_text]
        if missing_terms:
            errors.append(
                {
                    "code": "MISSING_COVERAGE_TERMS",
                    "material_id": material.get("id"),
                    "section": section,
                    "missing_terms": missing_terms,
                }
            )
    image_records = {
        image.get("id"): image
        for image in manifest.get("images") or []
        if isinstance(image, dict)
    }
    expected_images = [
        image_records[image_id]["original_markdown"]
        for image_id in chapter.get("image_ids") or []
        if image_id in image_records
    ]
    actual_images = IMAGE_RE.findall(text)
    if actual_images != expected_images:
        errors.append(
            {
                "code": "IMAGE_SEQUENCE_MISMATCH",
                "message": "正文图片必须与 manifest 本章 image_ids 的原始 Markdown 序列完全一致",
                "actual_count": len(actual_images),
                "expected_count": len(expected_images),
            }
        )
    for code, pattern in (
        ("SPEAKER_FRAME", SPEAKER_TERM_RE),
        ("SOURCE_FRAME", SOURCE_FRAME_RE),
        ("ORAL_FILLER", FILLER_RE),
        ("AUDIT_PATCH_PROSE", AUDIT_PATCH_RE),
    ):
        hits = pattern_hits(text, pattern)
        if hits:
            errors.append({"code": code, "hits": hits})
    prose_for_style = style_prose(text)
    ascii_punctuation = ASCII_CJK_PUNCT_RE.findall(prose_for_style)
    if len(ascii_punctuation) >= 4:
        errors.append({"code": "ASCII_CJK_PUNCTUATION", "count": len(ascii_punctuation)})
    if prose_for_style.count('"') % 2 or prose_for_style.count("“") != prose_for_style.count("”"):
        errors.append({"code": "UNBALANCED_QUOTES"})
    repeated_pairs = repeated_paragraph_pairs(text)
    if repeated_pairs:
        errors.append(
            {
                "code": "REPEATED_PARAGRAPHS",
                "pairs": [
                    {"left": left, "right": right, "overlap_ratio": round(ratio, 3)}
                    for left, right, ratio in repeated_pairs[:4]
                ],
            }
        )
    source_index = load_manifest_index(manifest_path, manifest)
    catalog = block_catalog(source_index)
    included_blocks = {
        block_id
        for material in manifest.get("materials") or []
        if isinstance(material, dict)
        and material.get("disposition") == "include"
        and material.get("target_chapter_id") == args.document
        for block_id in material.get("source_block_ids") or []
    }
    source_chars = sum(int(catalog.get(block_id, {}).get("char_count") or 0) for block_id in included_blocks)
    visible = IMAGE_RE.sub("", text)
    visible = re.sub(r"[#>*_`~|\\\s]", "", visible)
    required_chars = math.ceil(source_chars * CHAPTER_READER_DEPTH_RATIO)
    if source_chars and len(visible) < required_chars:
        errors.append(
            {
                "code": "READER_DEPTH",
                "reader_prose_chars": len(visible),
                "required_reader_prose_chars": required_chars,
            }
        )
    maximum_chars = max(
        MAX_CHAPTER_READER_EXPANSION_FLOOR,
        math.ceil(source_chars * MAX_CHAPTER_READER_EXPANSION_RATIO),
    )
    if source_chars and len(visible) > maximum_chars:
        errors.append(
            {
                "code": "READER_OVEREXPANSION",
                "reader_prose_chars": len(visible),
                "maximum_reader_prose_chars": maximum_chars,
            }
        )
    return {
        "status": "FAIL" if errors else "PASS",
        "action": "check-chapter",
        "document": args.document,
        "error_count": len(errors),
        "errors": errors,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Course Generator 增量素材账本工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="从冻结来源索引创建 manifest 脚手架")
    init_parser.add_argument("--source-index", type=Path, required=True)
    init_parser.add_argument("--source-root", type=Path, required=True)
    init_parser.add_argument("--manifest", type=Path, required=True)
    init_parser.add_argument("--title", required=True)
    init_parser.add_argument("--overview-file", required=True)

    plan_parser = subparsers.add_parser("plan", help="写入章节与小节计划")
    plan_parser.add_argument("manifest", type=Path)
    plan_parser.add_argument("plan", type=Path)
    plan_parser.add_argument("--max-chapters", type=int, default=8, help="章节上限，默认 8；高级授权模式参数")

    merge_parser = subparsers.add_parser("merge", help="校验并增量合并一批素材")
    merge_parser.add_argument("manifest", type=Path)
    merge_parser.add_argument("batch", type=Path)
    merge_parser.add_argument("--source-root", type=Path, required=True)

    status_parser = subparsers.add_parser("status", help="报告剩余来源块与下一步")
    status_parser.add_argument("manifest", type=Path)
    status_parser.add_argument(
        "--next-batch-size",
        type=int,
        default=DEFAULT_NEXT_BATCH_SIZE,
        help=f"精确返回下一批 ID，默认 {DEFAULT_NEXT_BATCH_SIZE}，最大 {MAX_NEXT_BATCH_SIZE}",
    )

    images_parser = subparsers.add_parser("select-images", help="用短选择清单同步正文图片映射")
    images_parser.add_argument("manifest", type=Path)
    images_parser.add_argument("selection", type=Path)

    scaffold_parser = subparsers.add_parser("scaffold", help="按 manifest 精确创建章节 H1/H2 脚手架")
    scaffold_parser.add_argument("manifest", type=Path)

    check_parser = subparsers.add_parser("check-chapter", help="在写下一章前检查单章结构、覆盖、图片、文风与深度")
    check_parser.add_argument("manifest", type=Path)
    check_parser.add_argument("--document", required=True, help="要检查的 CH-xx")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = {
            "init": command_init,
            "plan": command_plan,
            "merge": command_merge,
            "status": command_status,
            "select-images": command_select_images,
            "scaffold": command_scaffold,
            "check-chapter": command_check_chapter,
        }[args.command](args)
    except BatchValidationError as exc:
        print(
            json.dumps(
                {"status": "ERROR", "error": str(exc), "error_count": len(exc.errors), "errors": exc.errors},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    except (OSError, UnicodeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 1 if result.get("status") == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
