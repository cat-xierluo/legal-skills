#!/usr/bin/env python3
"""Regression tests for ledger_tool.py."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from index_sources import build_index
from ledger_tool import (
    BatchValidationError,
    command_check_chapter,
    command_init,
    command_merge,
    command_plan,
    command_scaffold,
    command_select_images,
    command_status,
)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def expect_error(label: str, operation, expected: str) -> bool:
    try:
        operation()
    except ValueError as exc:
        details = str(exc)
        if isinstance(exc, BatchValidationError):
            details += " " + " ".join(str(item.get("message", "")) for item in exc.errors)
        if expected in details:
            print(f"PASS {label}")
            return True
        print(f"FAIL {label}: {details}")
        return False
    print(f"FAIL {label}: 未失败关闭")
    return False


def main() -> int:
    passed = 0
    total = 33
    with tempfile.TemporaryDirectory(prefix="course-ledger-tool-") as temp:
        root = Path(temp)
        source = root / "source.md"
        source.write_text(
            "操作过程从界面入口触发连续步骤，最终把结果写回文件。\n\n"
            "投影设备切换，不构成课程知识。\n\n"
            "复核环节检查连续编号并确认状态。\n\n"
            "![操作界面](https://example.com/step.png)\n",
            encoding="utf-8",
        )
        course = root / "course"
        course.mkdir()
        index = course / "source-index.json"
        build_index(source, index)
        manifest = course / "course-manifest.json"
        result = command_init(
            argparse.Namespace(
                source_index=index,
                source_root=source,
                manifest=manifest,
                title="测试课程",
                overview_file="00 测试课程 - 总览.md",
            )
        )
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if result["status"] == "PASS" and data["schema_version"] == "1.8" and len(data["images"]) == 1:
            passed += 1
            print("PASS init-scaffold")
        else:
            print(f"FAIL init-scaffold: {result}")

        if expect_error(
            "init-no-overwrite",
            lambda: command_init(
                argparse.Namespace(
                    source_index=index,
                    source_root=source,
                    manifest=manifest,
                    title="测试课程",
                    overview_file="00 测试课程 - 总览.md",
                )
            ),
            "拒绝覆盖",
        ):
            passed += 1

        plan = root / "plan.json"
        write_json(
            plan,
            {
                "chapters": [
                    {
                        "file": "01 可复现操作.md",
                        "title": "可复现操作",
                        "section_headings": ["操作链与结果写回"],
                    }
                ]
            },
        )
        plan_result = command_plan(argparse.Namespace(manifest=manifest, plan=plan))
        if (
            plan_result["chapter_count"] == 1
            and plan_result["section_count"] == 1
            and plan_result["next_batch_content_block_ids"] == ["BLK-00001", "BLK-00002", "BLK-00003"]
        ):
            passed += 1
            print("PASS bounded-plan")
        else:
            print(f"FAIL bounded-plan: {plan_result}")

        oversized_plan = root / "oversized-plan.json"
        write_json(
            oversized_plan,
            {
                "chapters": [
                    {
                        "file": f"{number:02d} 主题{number}.md",
                        "title": f"主题{number}",
                        "section_headings": ["真实素材小节"],
                    }
                    for number in range(1, 10)
                ]
            },
        )
        if expect_error(
            "default-eight-chapter-limit",
            lambda: command_plan(argparse.Namespace(manifest=manifest, plan=oversized_plan, max_chapters=8)),
            "超过当前上限 8",
        ):
            passed += 1

        batch = root / "batch.json"
        write_json(
            batch,
            {
                "materials": [
                    {
                        "type": "操作",
                        "summary": "从界面入口触发连续步骤，并把结果写回文件。",
                        "source_block_ids": ["BLK-00001"],
                        "coverage_terms": ["界面入口", "结果写回"],
                        "disposition": "include",
                        "target_chapter_id": "CH-01",
                        "target_section_heading": "操作链与结果写回",
                    },
                    {
                        "type": "其他",
                        "summary": "投影设备切换。",
                        "source_block_ids": ["BLK-00002"],
                        "disposition": "skip",
                        "skip_code": "device",
                        "skip_reason": "只包含投影设备切换。",
                    },
                ]
            },
        )
        merge_result = command_merge(argparse.Namespace(manifest=manifest, batch=batch, source_root=source))
        current = json.loads(manifest.read_text(encoding="utf-8"))
        if not merge_result["ledger_complete"] and current["chapters"][0]["material_ids"] == ["MAT-001"] and current["materials"][1]["id"] == "MAT-002":
            passed += 1
            print("PASS merge-and-auto-number")
        else:
            print(f"FAIL merge-and-auto-number: {merge_result}")

        early_selection = root / "early-image-selection.json"
        write_json(
            early_selection,
            {"selections": [{"id": "IMG-001", "target_document_id": "CH-01", "reason": "操作界面代表图。"}]},
        )
        if expect_error(
            "reject-image-selection-before-ledger-complete",
            lambda: command_select_images(argparse.Namespace(manifest=manifest, selection=early_selection)),
            "素材账本未完整",
        ):
            passed += 1

        retry_result = command_merge(argparse.Namespace(manifest=manifest, batch=batch, source_root=source))
        retried = json.loads(manifest.read_text(encoding="utf-8"))
        if retry_result["added_material_count"] == 0 and retry_result["duplicate_material_count"] == 2 and len(retried["materials"]) == 2:
            passed += 1
            print("PASS idempotent-batch-retry")
        else:
            print(f"FAIL idempotent-batch-retry: {retry_result}")

        mixed_batch = root / "mixed-retry-and-new.json"
        write_json(
            mixed_batch,
            {
                "materials": [
                    {
                        "type": "操作",
                        "summary": "从界面入口触发连续步骤，并把结果写回文件。",
                        "source_block_ids": ["BLK-00001"],
                        "coverage_terms": ["界面入口", "结果写回"],
                        "disposition": "include",
                        "target_chapter_id": "CH-01",
                        "target_section_heading": "操作链与结果写回",
                    },
                    {
                        "type": "操作",
                        "summary": "复核环节检查连续编号并确认状态。",
                        "source_block_ids": ["BLK-00003"],
                        "coverage_terms": ["复核环节", "连续编号"],
                        "disposition": "include",
                        "target_chapter_id": "CH-01",
                        "target_section_heading": "操作链与结果写回",
                    },
                ]
            },
        )
        mixed_result = command_merge(
            argparse.Namespace(manifest=manifest, batch=mixed_batch, source_root=source)
        )
        mixed_manifest = json.loads(manifest.read_text(encoding="utf-8"))
        if (
            mixed_result["ledger_complete"]
            and mixed_result["added_material_count"] == 1
            and mixed_result["duplicate_material_count"] == 1
            and [item["id"] for item in mixed_manifest["materials"]] == ["MAT-001", "MAT-002", "MAT-003"]
        ):
            passed += 1
            print("PASS mixed-retry-keeps-contiguous-ids")
        else:
            print(f"FAIL mixed-retry-keeps-contiguous-ids: {mixed_result}")

        status = command_status(argparse.Namespace(manifest=manifest, next_batch_size=20))
        if (
            status["remaining_content_block_count"] == 0
            and status["next_batch_content_block_ids"] == []
            and "scaffold chapters" in status["next_action"]
        ):
            passed += 1
            print("PASS checkpoint-status")
        else:
            print(f"FAIL checkpoint-status: {status}")

        stale_manifest = course / "stale-manifest.json"
        stale_data = json.loads(manifest.read_text(encoding="utf-8"))
        stale_data["source_index"]["sha256"] = "0" * 64
        write_json(stale_manifest, stale_data)
        if expect_error(
            "status-rejects-stale-index",
            lambda: command_status(argparse.Namespace(manifest=stale_manifest, next_batch_size=20)),
            "sha256 与真实索引不一致",
        ):
            passed += 1

        conflict = root / "conflict.json"
        write_json(
            conflict,
            {
                "materials": [
                    {
                        "type": "其他",
                        "summary": "错误地跳过操作链。",
                        "source_block_ids": ["BLK-00001"],
                        "disposition": "skip",
                        "skip_code": "no_course_value",
                        "skip_reason": "冲突测试。",
                    }
                ]
            },
        )
        if expect_error(
            "include-skip-conflict",
            lambda: command_merge(argparse.Namespace(manifest=manifest, batch=conflict, source_root=source)),
            "不得同时 include 与 skip",
        ):
            passed += 1

        fragmented_batch = root / "fragmented-batch.json"
        write_json(
            fragmented_batch,
            {
                "materials": [
                    {
                        "type": "观点",
                        "summary": f"把同一操作链拆成第 {number} 个重复碎片。",
                        "source_block_ids": ["BLK-00001"],
                        "coverage_terms": ["界面入口"],
                        "disposition": "include",
                        "target_chapter_id": "CH-01",
                        "target_section_heading": "操作链与结果写回",
                    }
                    for number in range(1, 62)
                ]
            },
        )
        if expect_error(
            "material-count-budget",
            lambda: command_merge(argparse.Namespace(manifest=manifest, batch=fragmented_batch, source_root=source)),
            "超过当前渐进预算",
        ):
            passed += 1

        progressive_root = root / "progressive-budget"
        progressive_root.mkdir()
        progressive_source = progressive_root / "source.md"
        progressive_source.write_text(
            "\n\n".join(
                f"步骤{number:02d}通过独立入口执行，并写回编号{number:02d}结果。"
                for number in range(1, 31)
            )
            + "\n",
            encoding="utf-8",
        )
        progressive_course = progressive_root / "course"
        progressive_course.mkdir()
        progressive_index = progressive_course / "source-index.json"
        build_index(progressive_source, progressive_index)
        progressive_manifest = progressive_course / "course-manifest.json"
        command_init(
            argparse.Namespace(
                source_index=progressive_index,
                source_root=progressive_source,
                manifest=progressive_manifest,
                title="渐进预算测试",
                overview_file="00 渐进预算测试 - 总览.md",
            )
        )
        progressive_plan = progressive_root / "plan.json"
        write_json(
            progressive_plan,
            {
                "chapters": [
                    {
                        "file": "01 渐进预算.md",
                        "title": "渐进预算",
                        "section_headings": ["操作链"],
                    }
                ]
            },
        )
        command_plan(argparse.Namespace(manifest=progressive_manifest, plan=progressive_plan))
        one_block_per_material = progressive_root / "one-block-per-material.json"
        write_json(
            one_block_per_material,
            {
                "materials": [
                    {
                        "type": "操作",
                        "summary": f"步骤{number:02d}通过独立入口执行并写回结果。",
                        "source_block_ids": [f"BLK-{number:05d}"],
                        "coverage_terms": [f"编号{number:02d}"],
                        "disposition": "include",
                        "target_chapter_id": "CH-01",
                        "target_section_heading": "操作链",
                    }
                    for number in range(1, 31)
                ]
            },
        )
        if expect_error(
            "progressive-material-budget-fails-first-fragmented-batch",
            lambda: command_merge(
                argparse.Namespace(
                    manifest=progressive_manifest,
                    batch=one_block_per_material,
                    source_root=progressive_source,
                )
            ),
            "渐进预算 25 项",
        ):
            passed += 1

        contamination_manifest = course / "contamination-manifest.json"
        contamination_data = json.loads(manifest.read_text(encoding="utf-8"))
        contamination_data["materials"] = [contamination_data["materials"][1]]
        contamination_data["chapters"][0]["material_ids"] = []
        contamination_data["chapters"][0]["source_refs"] = []
        write_json(contamination_manifest, contamination_data)
        contamination_batch = root / "contamination-batch.json"
        write_json(
            contamination_batch,
            {
                "materials": [
                    {
                        "type": "观点",
                        "summary": "界面入口与投影设备形成结果写回测试。",
                        "source_block_ids": ["BLK-00001", "BLK-00002"],
                        "coverage_terms": ["界面入口", "投影设备"],
                        "disposition": "include",
                        "target_chapter_id": "CH-01",
                        "target_section_heading": "操作链与结果写回",
                    },
                    {
                        "type": "其他",
                        "summary": "操作链冲突后的合法跳过测试。",
                        "source_block_ids": ["BLK-00001"],
                        "disposition": "skip",
                        "skip_code": "no_course_value",
                        "skip_reason": "用于确认失败项不会污染后续判断。",
                    },
                ]
            },
        )
        try:
            command_merge(
                argparse.Namespace(
                    manifest=contamination_manifest,
                    batch=contamination_batch,
                    source_root=source,
                )
            )
        except BatchValidationError as exc:
            if len(exc.errors) == 1 and exc.errors[0].get("entry_index") == 1:
                passed += 1
                print("PASS rejected-entry-does-not-contaminate-batch")
            else:
                print(f"FAIL rejected-entry-does-not-contaminate-batch: {exc.errors}")
        else:
            print("FAIL rejected-entry-does-not-contaminate-batch: 未失败关闭")

        bad_term = root / "bad-term.json"
        write_json(
            bad_term,
            {
                "materials": [
                    {
                        "type": "观点",
                        "summary": "界面入口形成范式阶梯。",
                        "source_block_ids": ["BLK-00001"],
                        "coverage_terms": ["界面入口", "范式阶梯"],
                        "disposition": "include",
                        "target_chapter_id": "CH-01",
                        "target_section_heading": "操作链与结果写回",
                    }
                ]
            },
        )
        if expect_error(
            "invented-term",
            lambda: command_merge(argparse.Namespace(manifest=manifest, batch=bad_term, source_root=source)),
            "未出现在绑定来源块",
        ):
            passed += 1

        generic_term = root / "generic-term.json"
        write_json(
            generic_term,
            {
                "materials": [
                    {
                        "type": "观点",
                        "summary": "操作过程最终形成结果。",
                        "source_block_ids": ["BLK-00001"],
                        "coverage_terms": ["操作", "过程", "结果"],
                        "disposition": "include",
                        "target_chapter_id": "CH-01",
                        "target_section_heading": "操作链与结果写回",
                    }
                ]
            },
        )
        if expect_error(
            "all-generic-terms",
            lambda: command_merge(argparse.Namespace(manifest=manifest, batch=generic_term, source_root=source)),
            "不能全是",
        ):
            passed += 1

        aggregate = root / "aggregate-errors.json"
        write_json(
            aggregate,
            {
                "materials": [
                    {"type": "非法", "summary": "错误一", "source_block_ids": ["BLK-00001"], "disposition": "skip"},
                    {"type": "观点", "summary": "错误二", "source_block_ids": ["BLK-00001"], "disposition": "unknown"},
                ]
            },
        )
        try:
            command_merge(argparse.Namespace(manifest=manifest, batch=aggregate, source_root=source))
        except BatchValidationError as exc:
            if len(exc.errors) == 2:
                passed += 1
                print("PASS aggregate-batch-errors")
            else:
                print(f"FAIL aggregate-batch-errors: {exc.errors}")
        else:
            print("FAIL aggregate-batch-errors: 未失败关闭")

        selection = root / "image-selection.json"
        write_json(
            selection,
            {
                "selections": [
                    {"id": "IMG-001", "target_document_id": "CH-01", "reason": "操作界面代表图。"}
                ]
            },
        )
        image_result = command_select_images(argparse.Namespace(manifest=manifest, selection=selection))
        selected_manifest = json.loads(manifest.read_text(encoding="utf-8"))
        if (
            image_result["selected_reader_image_count"] == 1
            and selected_manifest["chapters"][0]["image_ids"] == ["IMG-001"]
            and selected_manifest["images"][0]["body_action"] == "insert"
        ):
            passed += 1
            print("PASS select-images")
        else:
            print(f"FAIL select-images: {image_result}")

        rich_unselected_manifest = course / "rich-unselected-manifest.json"
        rich_unselected_data = json.loads(manifest.read_text(encoding="utf-8"))
        rich_unselected_data["images"] = [
            {
                **rich_unselected_data["images"][0],
                "id": f"IMG-{index:03d}",
                "body_action": "asset_only",
                "target_document_id": None,
            }
            for index in range(1, 13)
        ]
        rich_unselected_data["chapters"][0]["image_ids"] = []
        write_json(rich_unselected_manifest, rich_unselected_data)
        if expect_error(
            "scaffold-rejects-missing-required-images",
            lambda: command_scaffold(argparse.Namespace(manifest=rich_unselected_manifest)),
            "代表图未达到最低数量",
        ):
            passed += 1

        empty_section_manifest = course / "empty-section-manifest.json"
        empty_section_data = json.loads(manifest.read_text(encoding="utf-8"))
        empty_section_data["chapters"][0]["section_headings"].append("没有素材的小节")
        write_json(empty_section_manifest, empty_section_data)
        if expect_error(
            "scaffold-rejects-empty-section",
            lambda: command_scaffold(argparse.Namespace(manifest=empty_section_manifest)),
            "没有绑定 include 素材",
        ):
            passed += 1

        scaffold_result = command_scaffold(argparse.Namespace(manifest=manifest))
        chapter_path = course / "01 可复现操作.md"
        chapter_path.write_text(
            "# 可复现操作\n\n"
            "## 操作链与结果写回\n\n"
            "操作过程从界面入口触发连续步骤，并把结果写回文件，形成可以复查的完整操作链。\n\n"
            "复核环节检查连续编号并确认状态，使每一次写回都有明确的核对依据。\n\n"
            "![操作界面](https://example.com/step.png)\n",
            encoding="utf-8",
        )
        chapter_check = command_check_chapter(
            argparse.Namespace(manifest=manifest, document="CH-01")
        )
        if scaffold_result["created"] == ["01 可复现操作.md"] and chapter_check["status"] == "PASS":
            passed += 1
            print("PASS scaffold-and-check-chapter")
        else:
            print(f"FAIL scaffold-and-check-chapter: {scaffold_result} {chapter_check}")

        valid_chapter_text = chapter_path.read_text(encoding="utf-8")
        chapter_path.write_text(valid_chapter_text + "\n# 多余标题\n", encoding="utf-8")
        duplicate_h1_check = command_check_chapter(argparse.Namespace(manifest=manifest, document="CH-01"))
        duplicate_h1_codes = {error.get("code") for error in duplicate_h1_check["errors"]}
        if duplicate_h1_check["status"] == "FAIL" and "H1_MISMATCH" in duplicate_h1_codes:
            passed += 1
            print("PASS duplicate-h1-rejected")
        else:
            print(f"FAIL duplicate-h1-rejected: {duplicate_h1_check}")

        chapter_path.write_text(valid_chapter_text + "\n讲者说这是这样的一个流程。\n", encoding="utf-8")
        tone_check = command_check_chapter(argparse.Namespace(manifest=manifest, document="CH-01"))
        tone_codes = {error.get("code") for error in tone_check["errors"]}
        if tone_check["status"] == "FAIL" and {"SPEAKER_FRAME", "ORAL_FILLER"} <= tone_codes:
            passed += 1
            print("PASS chapter-tone-check")
        else:
            print(f"FAIL chapter-tone-check: {tone_check}")

        chapter_path.write_text(valid_chapter_text + "\n## 正文证据补丁\n\n覆盖足够长度以满足证据。\n", encoding="utf-8")
        audit_patch_check = command_check_chapter(argparse.Namespace(manifest=manifest, document="CH-01"))
        audit_patch_codes = {error.get("code") for error in audit_patch_check["errors"]}
        if audit_patch_check["status"] == "FAIL" and "AUDIT_PATCH_PROSE" in audit_patch_codes:
            passed += 1
            print("PASS chapter-audit-patch-rejected")
        else:
            print(f"FAIL chapter-audit-patch-rejected: {audit_patch_check}")

        repeated_paragraph = (
            "从界面入口开始执行连续步骤，先确认输入文件和目标位置，再逐项检查规则与边界，"
            "随后运行任务并观察中间反馈，出现错误时保留现场信息并修正参数，最后把结果写回文件，"
            "同时核对输出名称、内容完整性和状态记录，确保整个操作链可以被后来者完整复查和稳定复现，"
            "并能够清楚理解每个步骤的输入、动作、结果与限制。"
        )
        chapter_path.write_text(valid_chapter_text + f"\n{repeated_paragraph}\n\n{repeated_paragraph}\n", encoding="utf-8")
        repeated_check = command_check_chapter(argparse.Namespace(manifest=manifest, document="CH-01"))
        repeated_codes = {error.get("code") for error in repeated_check["errors"]}
        if repeated_check["status"] == "FAIL" and "REPEATED_PARAGRAPHS" in repeated_codes:
            passed += 1
            print("PASS chapter-repeated-paragraphs-rejected")
        else:
            print(f"FAIL chapter-repeated-paragraphs-rejected: {repeated_check}")

        authority_root = root / "authority-case"
        authority_root.mkdir()
        authority_source = authority_root / "历史稿.md"
        authority_source.write_text(
            "> 编校说明：本稿不作为现行技术规范，修订口径统一见《当前控制版》“勘误与收束”。\n\n"
            "旧课把这套做法称为 spec coding，并把它当成现行名称。\n\n"
            "历史正文还记录了决策必须落盘，供后续课程保留。\n",
            encoding="utf-8",
        )
        (authority_root / "当前控制版.md").write_text(
            "# 当前控制版\n\n## 勘误与收束\n\n"
            "| 原课堂口径 | 修订后的课程口径 |\n|---|---|\n"
            "| `spec coding` | 使用轻量 Spec-Driven Development。 |\n",
            encoding="utf-8",
        )
        authority_course = authority_root / "course"
        authority_course.mkdir()
        authority_index = authority_course / "source-index.json"
        build_index(authority_source, authority_index)
        authority_manifest = authority_course / "course-manifest.json"
        authority_init = command_init(
            argparse.Namespace(
                source_index=authority_index,
                source_root=authority_source,
                manifest=authority_manifest,
                title="权威课程",
                overview_file="00 权威课程 - 总览.md",
            )
        )
        authority_plan = authority_root / "plan.json"
        write_json(
            authority_plan,
            {
                "chapters": [
                    {"file": "01 历史正文.md", "title": "历史正文", "section_headings": ["当前口径"]}
                ]
            },
        )
        if authority_init["authority_notice_count"] == 1 and authority_init["authority_correction_count"] == 1 and expect_error(
            "authority-plan-must-acknowledge",
            lambda: command_plan(argparse.Namespace(manifest=authority_manifest, plan=authority_plan)),
            "authority_acknowledgements",
        ):
            passed += 1
        write_json(
            authority_plan,
            {
                "authority_acknowledgements": [
                    {"id": "AUTH-001", "action": "apply_control", "controlling_source_ids": ["SRC-002"]}
                ],
                "chapters": [
                    {"file": "01 历史正文.md", "title": "历史正文", "section_headings": ["当前口径"]}
                ],
            },
        )
        if expect_error(
            "authority-plan-must-route-corrections",
            lambda: command_plan(argparse.Namespace(manifest=authority_manifest, plan=authority_plan)),
            "authority_correction_routes",
        ):
            passed += 1
        authority_plan_data = json.loads(authority_plan.read_text(encoding="utf-8"))
        authority_plan_data["authority_correction_routes"] = [
            {
                "id": "COR-001",
                "target_chapter_id": "CH-01",
                "target_section_heading": "当前口径",
                "supersession_status": "blocks_identified",
                "superseded_source_block_ids": ["BLK-00002"],
                "supersession_note": "BLK-00002 明确把旧称当成当前使用名称，应由修订句替代。",
            }
        ]
        write_json(authority_plan, authority_plan_data)
        if expect_error(
            "authority-plan-must-review-candidates",
            lambda: command_plan(argparse.Namespace(manifest=authority_manifest, plan=authority_plan)),
            "candidate_block_reviews",
        ):
            passed += 1
        authority_plan_data["authority_correction_routes"][0]["candidate_block_reviews"] = [
            {
                "source_block_id": "BLK-00002",
                "decision": "superseded",
                "evidence_quote": "旧课把这套做法称为",
                "reason": "该候选块明确把旧称当作当前名称，因此必须整体隔离。",
            }
        ]
        write_json(authority_plan, authority_plan_data)
        authority_plan_result = command_plan(argparse.Namespace(manifest=authority_manifest, plan=authority_plan))
        authority_data = json.loads(authority_manifest.read_text(encoding="utf-8"))
        if (
            authority_plan_result["authority_acknowledged"]
            and authority_plan_result["authority_corrections_routed"]
            and authority_plan_result["authority_candidate_review_queue"][0]["candidates"][0]["source_block_id"] == "BLK-00002"
            and authority_data["source_authority"]["acknowledgements"][0]["action"] == "apply_control"
        ):
            passed += 1
            print("PASS authority-plan-acknowledged-and-routed")
        else:
            print(f"FAIL authority-plan-acknowledged-and-routed: {authority_plan_result}")

        bad_evidence_plan = root / "bad-evidence-plan.json"
        bad_evidence_data = json.loads(authority_plan.read_text(encoding="utf-8"))
        bad_evidence_data["authority_correction_routes"][0]["candidate_block_reviews"][0]["evidence_quote"] = "这段话并不存在于候选预览"
        write_json(bad_evidence_plan, bad_evidence_data)
        fresh_authority_manifest = authority_course / "bad-evidence-manifest.json"
        fresh_authority_manifest.write_text(authority_manifest.read_text(encoding="utf-8"), encoding="utf-8")
        if expect_error(
            "authority-review-evidence-must-match-preview",
            lambda: command_plan(argparse.Namespace(manifest=fresh_authority_manifest, plan=bad_evidence_plan)),
            "evidence_quote 必须逐字来自该候选预览",
        ):
            passed += 1

        low_signal_batch = root / "low-signal-batch.json"
        write_json(
            low_signal_batch,
            {
                "materials": [{
                    "type": "观点",
                    "summary": "口语碎片不应充当正文锚点。",
                    "source_block_ids": ["BLK-00003"],
                    "coverage_terms": ["我觉得"],
                    "disposition": "include",
                    "target_chapter_id": "CH-01",
                    "target_section_heading": "当前口径",
                }]
            },
        )
        if expect_error(
            "coverage-term-rejects-oral-fragment",
            lambda: command_merge(argparse.Namespace(manifest=authority_manifest, batch=low_signal_batch, source_root=authority_source)),
            "口语指代、语气词或截断片段",
        ):
            passed += 1

        authority_batch = authority_root / "batch.json"
        write_json(
            authority_batch,
            {
                "materials": [
                    {
                        "type": "其他",
                        "summary": "旧称已被控制文档替代。",
                        "source_block_ids": ["BLK-00002"],
                        "coverage_terms": [],
                        "disposition": "skip",
                        "target_chapter_id": None,
                        "target_section_heading": None,
                        "skip_code": "authority_superseded",
                        "skip_reason": "该块把旧称作为现行结论，已由 COR-001 的修订口径替代。",
                    },
                    {
                        "type": "观点",
                        "summary": "决策需要落盘以供后续课程复用。",
                        "source_block_ids": ["BLK-00003"],
                        "coverage_terms": ["决策必须落盘"],
                        "disposition": "include",
                        "target_chapter_id": "CH-01",
                        "target_section_heading": "当前口径",
                    }
                ]
            },
        )
        command_merge(argparse.Namespace(manifest=authority_manifest, batch=authority_batch, source_root=authority_source))
        authority_scaffold = command_scaffold(argparse.Namespace(manifest=authority_manifest))
        authority_chapter = authority_course / "01 历史正文.md"
        authority_chapter.write_text(
            authority_chapter.read_text(encoding="utf-8") + "\n历史正文保留决策必须落盘的工程化要求，并按当前规则重新组织。\n",
            encoding="utf-8",
        )
        authority_check = command_check_chapter(argparse.Namespace(manifest=authority_manifest, document="CH-01"))
        authority_text = authority_chapter.read_text(encoding="utf-8")
        if (
            authority_scaffold["created"] == ["01 历史正文.md"]
            and "> **关键规则：** 使用轻量 Spec-Driven Development" in authority_text
            and authority_check["status"] == "PASS"
        ):
            passed += 1
            print("PASS authority-correction-injected")
        else:
            print(f"FAIL authority-correction-injected: {authority_scaffold} {authority_check}")

        authority_chapter.write_text(
            authority_chapter.read_text(encoding="utf-8") + "\nspec coding 是旧称。\n",
            encoding="utf-8",
        )
        deprecated_check = command_check_chapter(argparse.Namespace(manifest=authority_manifest, document="CH-01"))
        deprecated_codes = {item.get("code") for item in deprecated_check["errors"]}
        if deprecated_check["status"] == "FAIL" and "DEPRECATED_AUTHORITY_TERM" in deprecated_codes:
            passed += 1
            print("PASS deprecated-authority-term-rejected")
        else:
            print(f"FAIL deprecated-authority-term-rejected: {deprecated_check}")

    print(f"{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
