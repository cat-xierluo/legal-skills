#!/usr/bin/env python3
"""Regression tests for finalize_manifest.py."""

from __future__ import annotations

import copy
import json
import stat
import tempfile
from pathlib import Path

from finalize_manifest import reconcile_manifest


PARAGRAPH_ONE = (
    "从界面入口开始，任务依次完成文件选择、规则确认、连续执行和结果写回。"
    "过程中保留错误提示与修正过程，并记录每一步的输入条件和输出位置，"
    "使相同输入可以按原步骤再次复现并核对最终文件。"
)
PARAGRAPH_TWO = (
    "第二次运行继续使用界面入口，但将规则确认调整为逐项核对。"
    "结果写回后再比较前后差异，并记录输入条件、执行顺序和修正结果，"
    "形成另一组可以独立定位且足以复现的正文证据。"
)
PARAGRAPH_THREE = (
    "工程化判断的重点不是表面完成，而是让每次修改留下记录，并让最终结果能够被重新检查。"
)
IMAGE_ONE = "![关键界面](https://example.com/step.png)"
IMAGE_TWO = "![重复页面](https://example.com/other.png)"


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def source_index() -> dict:
    return {
        "schema_version": "1.4",
        "authority": {"mode": "current", "notices": [], "corrections": []},
        "sources": [
            {
                "id": "SRC-001",
                "path": "source.md",
                "sha256": "a" * 64,
                "blocks": [
                    {"id": "BLK-00001", "source_ref": "SRC-001#L0001-L0002", "kind": "content", "char_count": 80, "sha256": "b" * 64, "preview": "操作来源"},
                    {"id": "BLK-00002", "source_ref": "SRC-001#L0003-L0004", "kind": "content", "char_count": 60, "sha256": "c" * 64, "preview": "判断来源"},
                ],
            }
        ],
    }


def manifest() -> dict:
    return {
        "schema_version": "1.8",
        "generator_version": "2.10.1",
        "course": {"title": "测试课程"},
        "sources": [{"id": "SRC-001", "path": "source.md"}],
        "source_index": {"file": "source-index.json", "sha256": "d" * 64},
        "source_authority": {
            "mode": "current",
            "notices": [],
            "corrections": [],
            "acknowledgements": [],
            "correction_routes": [],
        },
        "overview": {"file": "00 测试课程 - 总览.md", "image_ids": ["IMG-002"]},
        "chapters": [
            {
                "id": "CH-01",
                "file": "01 第一章.md",
                "title": "第一章",
                "section_headings": ["操作证据", "第二次运行", "工程化判断"],
                "source_refs": ["SRC-001#L0001-L0004"],
                "material_ids": ["MAT-001", "MAT-002", "MAT-003"],
                "image_ids": [],
            }
        ],
        "materials": [
            {
                "id": "MAT-001",
                "type": "操作",
                "summary": "界面入口、结果写回与修正过程",
                "source_refs": ["SRC-999#L0001"],
                "source_block_ids": ["BLK-00001"],
                "coverage_terms": ["界面入口", "结果写回"],
                "disposition": "include",
                "target_chapter_id": "CH-01",
                "target_section_heading": "第二次运行",
                "reader_evidence": {"quotes": ["这是一段错误而且不在正文里的旧证据。"]},
            },
            {
                "id": "MAT-002",
                "type": "操作",
                "summary": "界面入口与结果写回的第二次运行",
                "source_refs": [],
                "source_block_ids": ["BLK-00001"],
                "coverage_terms": ["界面入口", "结果写回"],
                "disposition": "include",
                "target_chapter_id": "CH-01",
                "target_section_heading": "操作证据",
                "reader_evidence": None,
            },
            {
                "id": "MAT-003",
                "type": "观点",
                "summary": "修改记录与最终结果",
                "source_refs": [],
                "source_block_ids": ["BLK-00002"],
                "coverage_terms": ["修改", "最终结果"],
                "disposition": "include",
                "target_chapter_id": "CH-01",
                "target_section_heading": "工程化判断",
                "reader_evidence": None,
            },
        ],
        "images": [
            {"id": "IMG-001", "source_ref": "SRC-001#L0005", "original_markdown": IMAGE_ONE, "body_action": "asset_only", "target_document_id": None, "reason": "旧分配"},
            {"id": "IMG-002", "source_ref": "SRC-001#L0006", "original_markdown": IMAGE_TWO, "body_action": "insert", "target_document_id": "OVERVIEW"},
        ],
    }


def prepare(root: Path, data: dict | None = None) -> Path:
    write_json(root / "source-index.json", source_index())
    (root / "00 测试课程 - 总览.md").write_text("# 总览\n\n本课程用于测试确定性收口。\n", encoding="utf-8")
    (root / "01 第一章.md").write_text(
        f"# 第一章\n\n## 操作证据\n\n{PARAGRAPH_ONE}\n\n{IMAGE_ONE}\n\n## 第二次运行\n\n{PARAGRAPH_TWO}\n\n## 工程化判断\n\n{PARAGRAPH_THREE}\n",
        encoding="utf-8",
    )
    manifest_path = root / "course-manifest.json"
    write_json(manifest_path, data or manifest())
    return manifest_path


def main() -> int:
    passed = 0
    total = 8
    with tempfile.TemporaryDirectory(prefix="course-finalize-") as temp:
        root = Path(temp)
        manifest_path = prepare(root)
        original_mode = stat.S_IMODE(manifest_path.stat().st_mode)
        ledger = reconcile_manifest(manifest_path, write=True, phase="ledger")
        ledger_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if ledger["status"] == "PASS" and ledger_data["materials"][0]["source_refs"] == ["SRC-001#L0001-L0002"] and ledger_data["materials"][0]["reader_evidence"]["quotes"] == ["这是一段错误而且不在正文里的旧证据。"]:
            passed += 1
            print("PASS ledger-phase-only")
        else:
            print(f"FAIL ledger-phase-only: {ledger}")

        if stat.S_IMODE(manifest_path.stat().st_mode) == original_mode:
            passed += 1
            print("PASS atomic-write-preserves-mode")
        else:
            print("FAIL atomic-write-preserves-mode")

        before = manifest_path.read_bytes()
        preview = reconcile_manifest(manifest_path, write=False)
        if preview["status"] == "PASS" and manifest_path.read_bytes() == before:
            passed += 1
            print("PASS dry-run-does-not-write")
        else:
            print(f"FAIL dry-run-does-not-write: {preview}")

        applied = reconcile_manifest(manifest_path, write=True)
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        material_one = data["materials"][0]
        material_two = data["materials"][1]
        signatures = {
            "\u241e".join(material_one["reader_evidence"]["quotes"]),
            "\u241e".join(material_two["reader_evidence"]["quotes"]),
        }
        if applied["status"] == "PASS" and material_one["source_refs"] == ["SRC-001#L0001-L0002"] and len(signatures) == 2:
            passed += 1
            print("PASS evidence-and-source-refs")
        else:
            print(f"FAIL evidence-and-source-refs: {applied}")

        if data["chapters"][0]["image_ids"] == ["IMG-001"] and data["images"][0]["body_action"] == "insert" and data["images"][1]["body_action"] == "asset_only":
            passed += 1
            print("PASS image-reconciliation")
        else:
            print("FAIL image-reconciliation")

        first_bytes = manifest_path.read_bytes()
        second = reconcile_manifest(manifest_path, write=True)
        if second["status"] == "PASS" and not second["written"] and manifest_path.read_bytes() == first_bytes:
            passed += 1
            print("PASS idempotent")
        else:
            print(f"FAIL idempotent: {second}")

    with tempfile.TemporaryDirectory(prefix="course-finalize-gap-") as temp:
        root = Path(temp)
        broken = copy.deepcopy(manifest())
        broken["materials"][2]["coverage_terms"] = ["不存在", "最终结果"]
        broken["materials"][2]["summary"] = "不存在与最终结果"
        manifest_path = prepare(root, broken)
        result = reconcile_manifest(manifest_path, write=True)
        current = json.loads(manifest_path.read_text(encoding="utf-8"))
        if result["status"] == "FAIL" and any(item.get("id") == "MAT-003" for item in result["unresolved"]) and current["materials"][2]["reader_evidence"] is None:
            passed += 1
            print("PASS unresolved-does-not-fabricate")
        else:
            print(f"FAIL unresolved-does-not-fabricate: {result}")

    with tempfile.TemporaryDirectory(prefix="course-finalize-missing-reader-") as temp:
        root = Path(temp)
        missing_reader_manifest = manifest()
        missing_reader_manifest["chapters"][0]["image_ids"] = ["IMG-001"]
        missing_reader_manifest["images"][0]["body_action"] = "insert"
        missing_reader_manifest["images"][0]["target_document_id"] = "CH-01"
        manifest_path = prepare(root, missing_reader_manifest)
        (root / "01 第一章.md").unlink()
        result = reconcile_manifest(manifest_path, write=True)
        current = json.loads(manifest_path.read_text(encoding="utf-8"))
        chapter_images = current["chapters"][0]["image_ids"]
        image_record = current["images"][0]
        if result["status"] == "FAIL" and chapter_images == ["IMG-001"] and image_record["body_action"] == "insert" and image_record["target_document_id"] == "CH-01":
            passed += 1
            print("PASS unreadable-reader-preserves-image-state")
        else:
            print(f"FAIL unreadable-reader-preserves-image-state: {result}")

    print(f"{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
