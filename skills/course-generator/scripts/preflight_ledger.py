#!/usr/bin/env python3
"""Fail-fast validation for an in-progress Course Generator material ledger."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from index_sources import build_index_data


MAT_ID_RE = re.compile(r"^MAT-[0-9]{3,}$")
CHAPTER_ID_RE = re.compile(r"^CH-[0-9]{2,}$")
SKIP_CODES = {"derived_duplicate", "meeting", "device", "chatter", "pure_repeat", "no_course_value", "authority_superseded"}
GENERIC_SKIP_CODES = {"pure_repeat", "no_course_value"}
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
MAX_INCLUDE_BLOCKS_PER_MATERIAL = 6
GENERIC_SKIP_RATIO = 0.05
MIN_GENERIC_SKIP_ALLOWANCE = 1200
MIN_MATERIAL_COUNT_BUDGET = 60
MATERIAL_COUNT_BUDGET_RATIO = 0.50


def is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def material_count_budget(content_block_count: int) -> int:
    return max(MIN_MATERIAL_COUNT_BUDGET, math.ceil(content_block_count * MATERIAL_COUNT_BUDGET_RATIO))


def low_signal_coverage_term(value: str) -> bool:
    normalized = re.sub(r"\s+", "", value.strip())
    if not normalized:
        return True
    if LOW_SIGNAL_COVERAGE_RE.search(normalized) or LOW_SIGNAL_COVERAGE_PREFIX_RE.search(normalized):
        return True
    return bool(re.fullmatch(r"[\u4e00-\u9fff]+", normalized) and LOW_SIGNAL_COVERAGE_SUFFIX_RE.search(normalized))


def validate_ledger(
    manifest: Any,
    source_index: Any | None = None,
    raw_block_texts: dict[str, str] | None = None,
) -> list[str]:
    failures: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest 顶层必须是对象"]

    source_authority = manifest.get("source_authority")
    index_authority = source_index.get("authority") if isinstance(source_index, dict) else None
    if not isinstance(source_authority, dict):
        failures.append("manifest.source_authority 必须是对象")
    elif isinstance(index_authority, dict):
        if (
            source_authority.get("mode") != index_authority.get("mode")
            or source_authority.get("notices") != index_authority.get("notices")
            or source_authority.get("corrections") != index_authority.get("corrections")
        ):
            failures.append("manifest.source_authority 必须与 source-index.authority 的模式、声明和修正规则完全一致")
        notices = source_authority.get("notices") if isinstance(source_authority.get("notices"), list) else []
        acknowledgements = source_authority.get("acknowledgements") if isinstance(source_authority.get("acknowledgements"), list) else []
        if len(acknowledgements) != len(notices):
            failures.append("全部来源权威声明必须在 plan 阶段逐项确认")
        for notice, acknowledgement in zip(notices, acknowledgements):
            if not isinstance(acknowledgement, dict) or acknowledgement.get("id") != notice.get("id"):
                failures.append(f"来源权威声明 {notice.get('id')} 的 acknowledgement 缺失或错位")
                continue
            if source_authority.get("mode") == "current":
                if acknowledgement.get("action") != "apply_control" or acknowledgement.get("controlling_source_ids") != notice.get("controlling_source_ids"):
                    failures.append(f"来源权威声明 {notice.get('id')} 未精确确认控制来源")
            elif source_authority.get("mode") == "historical":
                if acknowledgement.get("action") != "historical_disclaimer" or not is_nonempty_string(acknowledgement.get("reader_notice")):
                    failures.append(f"来源权威声明 {notice.get('id')} 的历史模式缺少读者提示")

    materials = manifest.get("materials")
    if not isinstance(materials, list) or not materials:
        return ["materials 必须是非空数组"]

    seen_ids: set[str] = set()
    block_dispositions: dict[str, set[str]] = {}
    invalid_id_samples: list[str] = []
    invalid_id_count = 0
    block_kinds: dict[str, str] = {}
    block_refs: dict[str, str] = {}
    block_char_counts: dict[str, int] = {}
    block_previews: dict[str, str] = {}
    if isinstance(source_index, dict):
        for source in source_index.get("sources") or []:
            if not isinstance(source, dict):
                continue
            for block in source.get("blocks") or []:
                if not isinstance(block, dict) or not is_nonempty_string(block.get("id")):
                    continue
                block_id = block["id"]
                block_kinds[block_id] = str(block.get("kind") or "")
                if is_nonempty_string(block.get("source_ref")):
                    block_refs[block_id] = block["source_ref"]
                if isinstance(block.get("char_count"), int):
                    block_char_counts[block_id] = max(0, block["char_count"])
                if is_nonempty_string(block.get("preview")):
                    block_previews[block_id] = block["preview"]

    content_block_count = sum(1 for kind in block_kinds.values() if kind == "content")
    maximum_materials = material_count_budget(content_block_count)
    if len(materials) > maximum_materials:
        failures.append(
            f"素材共 {len(materials)} 项，超过 {content_block_count} 个 content block 对应的 {maximum_materials} 项预算；"
            "请合并同一观点、连续操作阶段或同一 skip 理由"
        )

    generic_skip_blocks: set[str] = set()
    planned_superseded_blocks: set[str] = set()
    quarantined_superseded_blocks: set[str] = set()
    covered_content_blocks: set[str] = set()
    chapter_sections: dict[str, list[str]] = {}
    section_material_counts: dict[tuple[str, str], int] = {}
    for chapter in manifest.get("chapters") or []:
        if not isinstance(chapter, dict) or not is_nonempty_string(chapter.get("id")):
            continue
        headings = chapter.get("section_headings")
        if not isinstance(headings, list) or not headings or not all(is_nonempty_string(item) for item in headings):
            failures.append(f"{chapter['id']}.section_headings 必须是非空字符串数组")
            continue
        if len(set(headings)) != len(headings):
            failures.append(f"{chapter['id']}.section_headings 不得重复")
        chapter_sections[chapter["id"]] = headings

    if isinstance(source_authority, dict):
        corrections = source_authority.get("corrections") if isinstance(source_authority.get("corrections"), list) else []
        routes = source_authority.get("correction_routes") if isinstance(source_authority.get("correction_routes"), list) else []
        expected_ids = [item.get("id") for item in corrections if isinstance(item, dict)]
        routed_ids = [item.get("id") for item in routes if isinstance(item, dict)]
        if routed_ids != expected_ids:
            failures.append("全部控制文档修正必须按 COR 编号顺序路由到计划 H2")
        correction_catalog = {
            item.get("id"): item
            for item in corrections
            if isinstance(item, dict) and is_nonempty_string(item.get("id"))
        }
        all_candidate_reviews: list[dict[str, Any]] = []
        for route in routes:
            if not isinstance(route, dict):
                failures.append("source_authority.correction_routes 每项必须是对象")
                continue
            chapter_id = route.get("target_chapter_id")
            section_heading = route.get("target_section_heading")
            if chapter_id not in chapter_sections:
                failures.append(f"{route.get('id')} 指向不存在的章节 {chapter_id!r}")
            elif section_heading not in chapter_sections[chapter_id]:
                failures.append(f"{route.get('id')} 指向未声明的小节 {section_heading!r}")
            supersession_status = route.get("supersession_status")
            superseded_ids = route.get("superseded_source_block_ids")
            supersession_note = route.get("supersession_note")
            if supersession_status not in {"blocks_identified", "no_matching_source_block"}:
                failures.append(f"{route.get('id')}.supersession_status 非法")
            if not isinstance(superseded_ids, list) or len(set(superseded_ids)) != len(superseded_ids):
                failures.append(f"{route.get('id')}.superseded_source_block_ids 必须是无重复数组")
                superseded_ids = []
            invalid_superseded = [
                block_id
                for block_id in superseded_ids
                if not is_nonempty_string(block_id) or block_kinds.get(block_id) != "content"
            ]
            if invalid_superseded:
                failures.append(f"{route.get('id')} 含不存在或非 content 的被替代来源块: {', '.join(map(str, invalid_superseded))}")
            planned_superseded_blocks.update(
                block_id for block_id in superseded_ids if is_nonempty_string(block_id) and block_kinds.get(block_id) == "content"
            )
            if supersession_status == "blocks_identified" and not superseded_ids:
                failures.append(f"{route.get('id')} 标记 blocks_identified 时必须列出来源块")
            if supersession_status == "no_matching_source_block" and superseded_ids:
                failures.append(f"{route.get('id')} 标记 no_matching_source_block 时来源块列表必须为空")
            if not is_nonempty_string(supersession_note) or len(supersession_note.strip()) < 12:
                failures.append(f"{route.get('id')}.supersession_note 必须至少 12 字")
            correction = correction_catalog.get(route.get("id"), {})
            expected_candidate_ids = correction.get("superseded_candidate_block_ids") or []
            candidate_reviews = route.get("candidate_block_reviews")
            if not isinstance(candidate_reviews, list):
                failures.append(f"{route.get('id')}.candidate_block_reviews 必须逐项审查全部候选来源块")
                candidate_reviews = []
            reviewed_candidate_ids: list[str] = []
            superseded_candidate_ids: set[str] = set()
            retained_candidate_ids: set[str] = set()
            normalized_review_reasons: list[str] = []
            for review_index, review in enumerate(candidate_reviews, 1):
                if not isinstance(review, dict):
                    failures.append(f"{route.get('id')}.candidate_block_reviews[{review_index}] 必须是对象")
                    continue
                block_id = review.get("source_block_id")
                decision = review.get("decision")
                reason = review.get("reason")
                evidence_quote = review.get("evidence_quote")
                if not is_nonempty_string(block_id) or block_kinds.get(block_id) != "content":
                    failures.append(f"{route.get('id')}.candidate_block_reviews[{review_index}] 引用不存在或非 content 的块")
                else:
                    reviewed_candidate_ids.append(block_id)
                if decision not in {"superseded", "retained_current"}:
                    failures.append(f"{route.get('id')}.candidate_block_reviews[{review_index}].decision 非法")
                elif is_nonempty_string(block_id):
                    if decision == "superseded":
                        superseded_candidate_ids.add(block_id)
                    else:
                        retained_candidate_ids.add(block_id)
                if not is_nonempty_string(reason) or len(reason.strip()) < 12:
                    failures.append(f"{route.get('id')}.candidate_block_reviews[{review_index}].reason 必须至少 12 字")
                else:
                    normalized_review_reasons.append(re.sub(r"\s+", "", reason).casefold())
                if not is_nonempty_string(evidence_quote) or len(evidence_quote.strip()) < 6:
                    failures.append(
                        f"{route.get('id')}.candidate_block_reviews[{review_index}].evidence_quote 必须摘录至少 6 字候选预览原文"
                    )
                elif is_nonempty_string(block_id) and evidence_quote.strip() not in block_previews.get(block_id, ""):
                    failures.append(
                        f"{route.get('id')}.candidate_block_reviews[{review_index}].evidence_quote 必须逐字来自该候选预览"
                    )
                all_candidate_reviews.append(review)
            if reviewed_candidate_ids != expected_candidate_ids:
                failures.append(
                    f"{route.get('id')}.candidate_block_reviews 必须按索引顺序逐项覆盖全部候选块"
                )
            if len(normalized_review_reasons) > 1 and len(set(normalized_review_reasons)) == 1:
                failures.append(f"{route.get('id')}.candidate_block_reviews 不得为全部候选复制同一判断理由")
            if superseded_candidate_ids - set(superseded_ids):
                failures.append(f"{route.get('id')} 判定 superseded 的候选块未进入隔离列表")
            if retained_candidate_ids & set(superseded_ids):
                failures.append(f"{route.get('id')} 判定 retained_current 的候选块被误列入隔离列表")
        if len(all_candidate_reviews) >= 12 and all(
            isinstance(review, dict) and review.get("decision") == "superseded"
            for review in all_candidate_reviews
        ):
            failures.append("候选审查不得把整张高召回矩阵一律判为 superseded；须逐块区分旧结论与相邻主题")

    for index, material in enumerate(materials, 1):
        label = f"materials[{index}]"
        if not isinstance(material, dict):
            failures.append(f"{label} 必须是对象")
            continue

        material_id = material.get("id")
        if not is_nonempty_string(material_id) or not MAT_ID_RE.fullmatch(material_id):
            invalid_id_count += 1
            if len(invalid_id_samples) < 5:
                invalid_id_samples.append(f"{label}={material_id!r}")
        elif material_id in seen_ids:
            failures.append(f"重复素材 ID: {material_id}")
        else:
            seen_ids.add(material_id)

        disposition = material.get("disposition")
        if disposition not in {"include", "skip"}:
            failures.append(f"{material_id or label}.disposition 必须为 include 或 skip")
            disposition = "invalid"

        source_block_ids = material.get("source_block_ids")
        valid_block_ids: list[str] = []
        if not isinstance(source_block_ids, list) or not source_block_ids:
            failures.append(f"{material_id or label}.source_block_ids 必须是非空数组")
        else:
            for block_id in source_block_ids:
                if not is_nonempty_string(block_id):
                    failures.append(f"{material_id or label}.source_block_ids 含空或非字符串值")
                    continue
                valid_block_ids.append(block_id)
                block_dispositions.setdefault(block_id, set()).add(disposition)
                if block_kinds and block_id not in block_kinds:
                    failures.append(f"{material_id or label} 引用了不存在的来源块 {block_id}")
                elif block_kinds and block_kinds.get(block_id) != "content":
                    failures.append(f"{material_id or label} 只能映射 content block，实际为 {block_id}")
                elif block_kinds:
                    covered_content_blocks.add(block_id)

        source_refs = material.get("source_refs")
        if not isinstance(source_refs, list) or not source_refs or not all(is_nonempty_string(value) for value in source_refs):
            failures.append(f"{material_id or label}.source_refs 必须是非空字符串数组")
        elif block_refs and valid_block_ids and all(block_id in block_refs for block_id in valid_block_ids):
            expected_refs: list[str] = []
            for block_id in valid_block_ids:
                source_ref = block_refs[block_id]
                if source_ref not in expected_refs:
                    expected_refs.append(source_ref)
            if source_refs != expected_refs:
                failures.append(f"{material_id or label}.source_refs 与 source_block_ids 的确定性映射不一致；先运行 finalize_manifest.py --phase ledger --write")

        target_chapter_id = material.get("target_chapter_id")
        target_section_heading = material.get("target_section_heading")
        coverage_terms = material.get("coverage_terms")
        summary = material.get("summary")
        if not is_nonempty_string(summary):
            failures.append(f"{material_id or label}.summary 必须是非空字符串")
        if disposition == "include":
            reintroduced = sorted(set(valid_block_ids) & planned_superseded_blocks)
            if reintroduced:
                failures.append(
                    f"{material_id or label} 把已由当前修订替代的来源块重新作为 include: {', '.join(reintroduced)}"
                )
            if len(valid_block_ids) > MAX_INCLUDE_BLOCKS_PER_MATERIAL:
                failures.append(f"{material_id or label} 为 include 时最多绑定 {MAX_INCLUDE_BLOCKS_PER_MATERIAL} 个来源块")
            if not is_nonempty_string(target_chapter_id) or not CHAPTER_ID_RE.fullmatch(target_chapter_id):
                failures.append(f"{material_id or label} 为 include 时必须填写 CH-01 形式的 target_chapter_id")
            elif target_chapter_id not in chapter_sections:
                failures.append(f"{material_id or label} 指向未声明或没有 section_headings 的章节 {target_chapter_id}")
            if not is_nonempty_string(target_section_heading):
                failures.append(f"{material_id or label} 为 include 时必须填写 target_section_heading")
            elif target_section_heading not in chapter_sections.get(str(target_chapter_id), []):
                failures.append(f"{material_id or label}.target_section_heading 未在目标章节声明: {target_section_heading!r}")
            else:
                key = (str(target_chapter_id), target_section_heading)
                section_material_counts[key] = section_material_counts.get(key, 0) + 1
            if not isinstance(coverage_terms, list) or not 1 <= len(coverage_terms) <= 3:
                failures.append(f"{material_id or label} 为 include 时必须预填 1—3 个 coverage_terms")
            elif any(not is_nonempty_string(term) or len(term.strip()) < 2 for term in coverage_terms):
                failures.append(f"{material_id or label}.coverage_terms 每项至少 2 字符")
            else:
                normalized_terms = [term.strip() for term in coverage_terms]
                if len(set(normalized_terms)) != len(normalized_terms):
                    failures.append(f"{material_id or label}.coverage_terms 不得重复")
                if normalized_terms and all(
                    term.casefold() in GENERIC_COVERAGE_TERMS for term in normalized_terms
                ):
                    failures.append(f"{material_id or label}.coverage_terms 不能全是通用词")
                for term in normalized_terms:
                    if low_signal_coverage_term(term):
                        failures.append(
                            f"{material_id or label} 的 coverage term {term!r} 是口语指代、语气词或截断片段"
                        )
                required_term_count = max(1, min(3, math.ceil(len(valid_block_ids) / 3)))
                if len(coverage_terms) < required_term_count:
                    failures.append(f"{material_id or label} 覆盖 {len(valid_block_ids)} 个来源块时至少需要 {required_term_count} 个 coverage_terms")
                if raw_block_texts is not None:
                    bound_text = "\n".join(raw_block_texts.get(block_id, "") for block_id in valid_block_ids)
                    for term in coverage_terms:
                        if is_nonempty_string(term) and term.strip() not in bound_text:
                            failures.append(f"{material_id or label} 的 coverage term {term!r} 未出现在绑定的原始来源块")
        elif disposition == "skip":
            if target_chapter_id is not None:
                failures.append(f"{material_id or label} 为 skip 时 target_chapter_id 必须为 null")
            if target_section_heading is not None:
                failures.append(f"{material_id or label} 为 skip 时 target_section_heading 必须为 null")
            if coverage_terms != []:
                failures.append(f"{material_id or label} 为 skip 时 coverage_terms 必须为空数组")
            if material.get("skip_code") not in SKIP_CODES:
                failures.append(f"{material_id or label} 为 skip 时必须填写受控 skip_code")
            if not is_nonempty_string(material.get("skip_reason")):
                failures.append(f"{material_id or label} 为 skip 时必须填写具体 skip_reason")
            if material.get("skip_code") in GENERIC_SKIP_CODES:
                generic_skip_blocks.update(valid_block_ids)
            if material.get("skip_code") == "authority_superseded":
                unexpected = sorted(set(valid_block_ids) - planned_superseded_blocks)
                if unexpected:
                    failures.append(f"{material_id or label} 把未确认的来源块误标为 authority_superseded: {', '.join(unexpected)}")
                quarantined_superseded_blocks.update(set(valid_block_ids) & planned_superseded_blocks)
            elif set(valid_block_ids) & planned_superseded_blocks:
                failures.append(f"{material_id or label} 的被替代来源块必须使用 skip_code=authority_superseded")

    if invalid_id_count:
        failures.append(
            f"{invalid_id_count} 个素材 ID 未使用 MAT-001 起的统一命名空间"
            f"（例如 {', '.join(invalid_id_samples)}）；skip 也是 disposition，禁止 SKIP-*"
        )

    if seen_ids:
        expected_ids = {f"MAT-{number:03d}" for number in range(1, len(materials) + 1)}
        if seen_ids != expected_ids:
            missing = sorted(expected_ids - seen_ids)
            unexpected = sorted(seen_ids - expected_ids)
            detail: list[str] = []
            if missing:
                detail.append(f"缺少 {', '.join(missing[:8])}")
            if unexpected:
                detail.append(f"越界 {', '.join(unexpected[:8])}")
            failures.append("素材 ID 必须从 MAT-001 连续分配：" + "；".join(detail))

    for block_id, dispositions in sorted(block_dispositions.items()):
        if "include" in dispositions and "skip" in dispositions:
            failures.append(f"{block_id} 不得同时进入 include 与 skip 素材")

    missing_quarantine = sorted(planned_superseded_blocks - quarantined_superseded_blocks)
    if missing_quarantine:
        failures.append(
            "plan 已确认的被替代来源块必须全部进入 authority_superseded skip: "
            + ", ".join(missing_quarantine[:12])
        )

    if block_kinds:
        expected_content_blocks = {
            block_id
            for block_id, kind in block_kinds.items()
            if kind == "content"
        }
        uncovered_blocks = sorted(expected_content_blocks - covered_content_blocks)
        if uncovered_blocks:
            preview = ", ".join(uncovered_blocks[:12])
            suffix = "..." if len(uncovered_blocks) > 12 else ""
            failures.append(f"有 {len(uncovered_blocks)} 个 content block 未登记去向: {preview}{suffix}")

    if block_char_counts:
        total_content_chars = sum(
            block_char_counts.get(block_id, 0)
            for block_id, kind in block_kinds.items()
            if kind == "content"
        )
        generic_skip_chars = sum(block_char_counts.get(block_id, 0) for block_id in generic_skip_blocks)
        allowance = max(MIN_GENERIC_SKIP_ALLOWANCE, math.ceil(total_content_chars * GENERIC_SKIP_RATIO))
        if generic_skip_chars > allowance:
            failures.append(
                f"pure_repeat/no_course_value 共跳过 {generic_skip_chars} 个来源字符，超过 generic skip 预算 {allowance}；"
                "演示过程、操作反馈、错误修正和版本比较应拆为 include 素材"
            )

    for chapter_id, headings in chapter_sections.items():
        for heading in headings:
            if section_material_counts.get((chapter_id, heading), 0) == 0:
                failures.append(f"{chapter_id} 的小节 {heading!r} 没有任何 include 素材")

    return failures


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="在正文生成前预检 course-manifest.json 的素材账本")
    parser.add_argument("manifest", type=Path, help="进行中的 course-manifest.json")
    parser.add_argument("--source-root", type=Path, help="索引时使用的单个来源文件或来源根目录；提供后验证 coverage terms 真实存在于绑定来源块")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False))
        return 2

    source_index_info = manifest.get("source_index") if isinstance(manifest, dict) else None
    source_index_file = source_index_info.get("file") if isinstance(source_index_info, dict) else None
    if not is_nonempty_string(source_index_file):
        print(json.dumps({"status": "ERROR", "error": "manifest.source_index.file 缺失"}, ensure_ascii=False))
        return 2
    source_index_path = (args.manifest.parent / source_index_file).resolve()
    try:
        source_index_path.relative_to(args.manifest.parent.resolve())
        source_index = json.loads(source_index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "ERROR", "error": f"source-index 无法读取: {exc}"}, ensure_ascii=False))
        return 2

    raw_block_texts: dict[str, str] | None = None
    if args.source_root is not None:
        try:
            authority = source_index.get("authority") if isinstance(source_index, dict) else None
            authority_mode = authority.get("mode") if isinstance(authority, dict) else "current"
            rebuilt, raw_block_texts = build_index_data(args.source_root, source_index_path, authority_mode)
            if rebuilt != source_index:
                raise ValueError("source-index 与当前 source-root 的确定性重建结果不一致")
        except (OSError, UnicodeError, ValueError) as exc:
            print(json.dumps({"status": "ERROR", "error": f"source-root 无法重建: {exc}"}, ensure_ascii=False))
            return 2

    failures = validate_ledger(manifest, source_index, raw_block_texts)
    result = {
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
