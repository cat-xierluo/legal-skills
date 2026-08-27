#!/usr/bin/env python3
"""Fault-injection regression suite for verify_course.py."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

from index_sources import build_index
from verify_course import verify_course


SCRIPT_DIR = Path(__file__).resolve().parent
VERIFIER = SCRIPT_DIR / "verify_course.py"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_fixture(root: Path) -> None:
    overview_name = "00 示例课程 - 总览.md"
    chapter_name = "01 第一 章（文件名含空格）.md"
    overview_image = "![方法框架](https://example.com/framework.png)"
    image_2 = "![操作界面](https://example.com/step-1.png)"
    image_3 = "![结果页面](https://example.com/step-2.png)"
    image_4 = "![会务页](https://example.com/test.png)"
    root.mkdir(parents=True)
    source_root = root.parent / "sources"
    source_root.mkdir(exist_ok=True)
    source_path = source_root / "转录稿.md"
    source_path.write_text(
        "完整操作链包含界面入口、连续步骤与 Agent 返回结果\n\n"
        + "\n\n".join([overview_image, image_2, image_3, image_4])
        + "\n",
        encoding="utf-8",
    )
    (root / overview_name).write_text(f"# 示例课程 - 总览\n\n讲师资格的判断属于正常课程内容，不是来源指代。\n\n{overview_image}\n", encoding="utf-8")
    evidence_quote_1 = "一次完整操作链从界面入口开始，连续说明每一步动作、必要前置条件、Agent 返回结果与途中修正，使读者能够独立复现，而不是只看到一句没有过程的结论。"
    evidence_quote_2 = "完成执行后还要检查结果写回位置与关键字段，确认错误已经修正、最终文件可以直接使用。"
    evidence_quote = evidence_quote_1 + evidence_quote_2
    (root / chapter_name).write_text(f"# 第一章\n\n{evidence_quote}\n\n{image_2}\n\n操作继续推进。\n\n{image_3}\n", encoding="utf-8")
    (root / "98 图片资产表.md").write_text("# 图片资产表\n\n共三张。\n", encoding="utf-8")
    (root / "99 课程大纲.md").write_text("# 课程大纲\n\n第一章。\n", encoding="utf-8")
    source_index_path = root / "source-index.json"
    build_index(source_path, source_index_path)
    source_index = json.loads(source_index_path.read_text(encoding="utf-8"))
    source_image_blocks = [
        block
        for block in source_index["sources"][0]["blocks"]
        if block["kind"] == "image"
    ]
    manifest = {
        "schema_version": "1.2",
        "generator_version": "2.9.4",
        "course": {"title": "示例课程"},
        "sources": [{"id": "SRC-001", "path": "转录稿.md"}],
        "source_index": {"file": "source-index.json", "sha256": sha256_file(source_index_path)},
        "overview": {"file": overview_name, "image_ids": ["IMG-001"]},
        "chapters": [{"id": "CH-01", "file": chapter_name, "title": "第一章", "source_refs": ["SRC-001#00:00-10:00"], "material_ids": ["MAT-001"], "image_ids": ["IMG-002", "IMG-003"]}],
        "materials": [{
            "id": "MAT-001",
            "type": "操作",
            "summary": "完整操作链包含界面入口与 Agent 返回结果",
            "source_refs": ["SRC-001#L0001-L0001"],
            "source_block_ids": ["BLK-00001"],
            "coverage_terms": ["界面入口", "Agent 返回结果"],
            "disposition": "include",
            "target_chapter_id": "CH-01",
            "reader_evidence": {"quotes": [evidence_quote_1, evidence_quote_2]}
        }],
        "images": [
            {"id": "IMG-001", "source_ref": source_image_blocks[0]["source_ref"], "original_markdown": overview_image, "body_action": "insert", "target_document_id": "OVERVIEW"},
            {"id": "IMG-002", "source_ref": source_image_blocks[1]["source_ref"], "original_markdown": image_2, "body_action": "insert", "target_document_id": "CH-01"},
            {"id": "IMG-003", "source_ref": source_image_blocks[2]["source_ref"], "original_markdown": image_3, "body_action": "insert", "target_document_id": "CH-01"},
            {"id": "IMG-004", "source_ref": source_image_blocks[3]["source_ref"], "original_markdown": image_4, "body_action": "asset_only", "target_document_id": None, "reason": "会务测试"}
        ],
        "audit_files": {"outline": "99 课程大纲.md", "image_assets": "98 图片资产表.md"}
    }
    (root / "course-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rewrite_source_images(root: Path, markdowns: list[str]) -> list[dict]:
    source_path = root.parent / "sources" / "转录稿.md"
    source_path.write_text(
        "完整操作链包含界面入口、连续步骤与 Agent 返回结果\n\n" + "\n\n".join(markdowns) + "\n",
        encoding="utf-8",
    )
    index_path = root / "source-index.json"
    build_index(source_path, index_path)
    source_index = json.loads(index_path.read_text(encoding="utf-8"))
    manifest_path = root / "course-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_index"]["sha256"] = sha256_file(index_path)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return [
        block
        for block in source_index["sources"][0]["blocks"]
        if block["kind"] == "image"
    ]


def strip_reader_images(root: Path) -> None:
    for path in [root / "00 示例课程 - 总览.md", root / "01 第一 章（文件名含空格）.md"]:
        text = path.read_text(encoding="utf-8")
        path.write_text(re.sub(r"!\[[^\]\n]*\]\([^\n)]*\)\s*", "", text), encoding="utf-8")


def run_verifier(root: Path) -> tuple[int, dict]:
    completed = subprocess.run(
        [sys.executable, str(VERIFIER), str(root), "--source-root", str(root.parent / "sources")],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise AssertionError(f"验收器无 stdout，stderr={completed.stderr!r}")
    try:
        result = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise AssertionError(f"stdout 最后一行不是 JSON: {lines[-1]!r}") from exc
    return completed.returncode, result


def mutate_missing_manifest(root: Path) -> None:
    (root / "course-manifest.json").unlink()


def mutate_empty_manifest(root: Path) -> None:
    (root / "course-manifest.json").write_text("{}\n", encoding="utf-8")


def mutate_missing_source_index(root: Path) -> None:
    (root / "source-index.json").unlink()


def mutate_source_index_hash(root: Path) -> None:
    with (root / "source-index.json").open("a", encoding="utf-8") as handle:
        handle.write(" ")


def mutate_source_index_not_deterministic(root: Path) -> None:
    index_path = root / "source-index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["sources"][0]["blocks"][0]["preview"] = "人工伪造但结构合法的预览"
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path = root / "course-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_index"]["sha256"] = sha256_file(index_path)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutate_uncovered_source_block(root: Path) -> None:
    index_path = root / "source-index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["sources"][0]["blocks"].append({
        "id": "BLK-00002",
        "source_ref": "SRC-001#L0002-L0002",
        "kind": "content",
        "char_count": 8,
        "sha256": "2" * 64,
        "preview": "遗漏的实质段落"
    })
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path = root / "course-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_index"]["sha256"] = sha256_file(index_path)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutate_unknown_source_block(root: Path) -> None:
    path = root / "course-manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["materials"][0]["source_block_ids"] = ["BLK-99999"]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutate_missing_reader_evidence(root: Path) -> None:
    path = root / "course-manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["materials"][0]["reader_evidence"] = None
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutate_short_reader_evidence(root: Path) -> None:
    path = root / "course-manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["materials"][0]["reader_evidence"] = {"quotes": ["界面入口和连续步骤需要完整说明。"]}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutate_missing_reader_quote(root: Path) -> None:
    path = root / "course-manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["materials"][0]["reader_evidence"]["quotes"] = ["这是一段长度足够但没有实际出现在目标章节中的虚构证据摘录，它不能证明真实正文已经承载对应的操作素材与连续步骤。"]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutate_reader_term_missing(root: Path) -> None:
    path = root / "course-manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["materials"][0]["coverage_terms"] = ["界面入口", "不存在的覆盖词"]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutate_term_absent_from_summary(root: Path) -> None:
    path = root / "course-manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["materials"][0]["coverage_terms"] = ["界面入口", "必要前置条件"]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutate_single_coverage_term(root: Path) -> None:
    path = root / "course-manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["materials"][0]["coverage_terms"] = ["界面入口"]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutate_generic_coverage_terms(root: Path) -> None:
    path = root / "course-manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["materials"][0]["summary"] = "Agent 生成结果"
    data["materials"][0]["coverage_terms"] = ["Agent", "结果"]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutate_thin_reader_depth(root: Path) -> None:
    source_path = root.parent / "sources" / "转录稿.md"
    source_path.write_text(
        "完整操作链包含界面入口、文件选择、规则确认、前置条件、逐步执行、Agent 返回结果、错误发现、修正过程、结果写回与复核。" * 40 + "\n",
        encoding="utf-8",
    )
    index_path = root / "source-index.json"
    build_index(source_path, index_path)
    manifest_path = root / "course-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_index"]["sha256"] = sha256_file(index_path)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutate_overmerged_material(root: Path) -> None:
    source_path = root.parent / "sources" / "转录稿.md"
    source_path.write_text(
        "\n\n".join([
            "从界面入口选择工作目录。",
            "确认输入文件与必要前置条件。",
            "向 Agent 下达第一步执行指令。",
            "检查 Agent 返回结果是否完整。",
            "发现字段遗漏并定位错误原因。",
            "修改规则后重新执行任务。",
            "把最终结果写回文件并完成复核。",
        ]) + "\n",
        encoding="utf-8",
    )
    index_path = root / "source-index.json"
    build_index(source_path, index_path)
    source_index = json.loads(index_path.read_text(encoding="utf-8"))
    content_ids = [
        block["id"]
        for block in source_index["sources"][0]["blocks"]
        if block["kind"] == "content"
    ]
    manifest_path = root / "course-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_index"]["sha256"] = sha256_file(index_path)
    manifest["materials"][0]["source_block_ids"] = content_ids
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutate_image_overload(root: Path) -> None:
    path = root / "course-manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    existing_markdowns = [item["original_markdown"] for item in data["images"]]
    extra_images = [
        ("IMG-005", "![补充界面一](https://example.com/extra-1.png)"),
        ("IMG-006", "![补充界面二](https://example.com/extra-2.png)"),
    ]
    source_image_blocks = rewrite_source_images(
        root,
        existing_markdowns + [markdown for _, markdown in extra_images],
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    for index, image in enumerate(data["images"]):
        image["source_ref"] = source_image_blocks[index]["source_ref"]
    data["chapters"][0]["image_ids"].extend(image_id for image_id, _ in extra_images)
    for offset, (image_id, markdown) in enumerate(extra_images, len(data["images"])):
        data["images"].append({
            "id": image_id,
            "source_ref": source_image_blocks[offset]["source_ref"],
            "original_markdown": markdown,
            "body_action": "insert",
            "target_document_id": "CH-01",
        })
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    chapter_path = root / "01 第一 章（文件名含空格）.md"
    with chapter_path.open("a", encoding="utf-8") as handle:
        for _, markdown in extra_images:
            handle.write(f"\n{markdown}\n")


def mutate_source_traversal(root: Path) -> None:
    path = root / "course-manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["sources"][0]["path"] = "../../private/secret.md"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutate_empty_chapter(root: Path) -> None:
    (root / "01 第一 章（文件名含空格）.md").write_text("", encoding="utf-8")


def mutate_missing_image(root: Path) -> None:
    path = root / "01 第一 章（文件名含空格）.md"
    path.write_text(path.read_text(encoding="utf-8").replace("\n\n![结果页面](https://example.com/step-2.png)", ""), encoding="utf-8")


def mutate_wrong_order(root: Path) -> None:
    path = root / "01 第一 章（文件名含空格）.md"
    text = path.read_text(encoding="utf-8")
    image_2 = "![操作界面](https://example.com/step-1.png)"
    image_3 = "![结果页面](https://example.com/step-2.png)"
    path.write_text(text.replace(image_2, "__TMP__").replace(image_3, image_2).replace("__TMP__", image_3), encoding="utf-8")


def mutate_undeclared_image(root: Path) -> None:
    with (root / "01 第一 章（文件名含空格）.md").open("a", encoding="utf-8") as handle:
        handle.write("\n![额外图片](https://example.com/extra.png)\n")


def mutate_material_link(root: Path) -> None:
    path = root / "course-manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["chapters"][0]["material_ids"] = []
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutate_non_contiguous_material_id(root: Path) -> None:
    path = root / "course-manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["materials"][0]["id"] = "MAT-002"
    data["chapters"][0]["material_ids"] = ["MAT-002"]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutate_speaker_actor(root: Path) -> None:
    with (root / "01 第一 章（文件名含空格）.md").open("a", encoding="utf-8") as handle:
        handle.write("\n讲师强调这一步最重要。\n")


def mutate_visible_trace(root: Path) -> None:
    with (root / "01 第一 章（文件名含空格）.md").open("a", encoding="utf-8") as handle:
        handle.write("\n> 原文区间：SRC-001#03:20-06:10\n")


def mutate_asset_only_inserted(root: Path) -> None:
    with (root / "01 第一 章（文件名含空格）.md").open("a", encoding="utf-8") as handle:
        handle.write("\n![会务页](https://example.com/test.png)\n")


def mutate_omitted_source_image(root: Path) -> None:
    path = root / "course-manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["images"] = [item for item in data["images"] if item["id"] != "IMG-004"]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutate_low_image_zero_insert(root: Path) -> None:
    path = root / "course-manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["overview"]["image_ids"] = []
    data["chapters"][0]["image_ids"] = []
    for image in data["images"]:
        image["body_action"] = "asset_only"
        image["target_document_id"] = None
        image["reason"] = "少量低价值测试图片，不进入正文"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    strip_reader_images(root)


def mutate_rich_source_zero_insert(root: Path) -> None:
    path = root / "course-manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    markdowns = [
        f"![课程截图 {index}](https://example.com/rich-{index}.png)"
        for index in range(1, 13)
    ]
    source_image_blocks = rewrite_source_images(root, markdowns)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["overview"]["image_ids"] = []
    data["chapters"][0]["image_ids"] = []
    data["images"] = [
        {
            "id": f"IMG-{index:03d}",
            "source_ref": source_image_blocks[index - 1]["source_ref"],
            "original_markdown": markdown,
            "body_action": "asset_only",
            "target_document_id": None,
            "reason": "全部降级为附件",
        }
        for index, markdown in enumerate(markdowns, 1)
    ]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    strip_reader_images(root)


def mutate_extra_chapter(root: Path) -> None:
    (root / "02 未声明章节.md").write_text("# 未声明章节\n", encoding="utf-8")


def mutate_whole_source_omitted(root: Path) -> None:
    (root.parent / "sources" / "补充材料.md").write_text("这是一份被整个漏掉的补充来源文件。\n", encoding="utf-8")


def mutate_invented_source_term(root: Path) -> None:
    manifest_path = root / "course-manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["materials"][0]["summary"] = "完整操作链包含界面入口与范式阶梯"
    data["materials"][0]["coverage_terms"] = ["界面入口", "范式阶梯"]
    original = data["materials"][0]["reader_evidence"]["quotes"][0]
    replacement = original.replace("连续说明", "按范式阶梯连续说明")
    data["materials"][0]["reader_evidence"]["quotes"][0] = replacement
    chapter_path = root / "01 第一 章（文件名含空格）.md"
    chapter_path.write_text(
        chapter_path.read_text(encoding="utf-8").replace(original, replacement),
        encoding="utf-8",
    )
    manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutate_invented_acronym_expansion(root: Path) -> None:
    with (root / "01 第一 章（文件名含空格）.md").open("a", encoding="utf-8") as handle:
        handle.write("\nRCP（Record of Completion / 修订记录）用于保存修改过程。\n")


def mutate_too_many_chapters(root: Path) -> None:
    manifest_path = root / "course-manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    for number in range(2, 10):
        chapter_id = f"CH-{number:02d}"
        file_name = f"{number:02d} 补充主题{number}.md"
        (root / file_name).write_text(f"# 补充主题{number}\n\n这是按需合并前的补充内容。\n", encoding="utf-8")
        data["chapters"].append({
            "id": chapter_id,
            "file": file_name,
            "title": f"补充主题{number}",
            "source_refs": ["SRC-001#L0001-L0001"],
            "material_ids": [],
            "image_ids": [],
        })
    manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutate_placeholder_filename(root: Path) -> None:
    old_path = root / "00 示例课程 - 总览.md"
    new_name = "00 [课程名称] - 总览.md"
    old_path.rename(root / new_name)
    manifest_path = root / "course-manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["overview"]["file"] = new_name
    manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


CASES: dict[str, tuple[str, Callable[[Path], None] | None, int, str | None]] = {
    "valid": ("合法近似正例与带空格文件名", None, 0, None),
    "valid-low-image-zero": ("少量低价值来源图允许不进入正文", mutate_low_image_zero_insert, 0, None),
    "missing-manifest": ("缺少 manifest", mutate_missing_manifest, 1, "CG-CONTRACT-MANIFEST"),
    "empty-manifest": ("空 manifest 对象", mutate_empty_manifest, 1, "CG-CONTRACT-MANIFEST"),
    "missing-source-index": ("缺少来源索引", mutate_missing_source_index, 1, "CG-SOURCE-BLOCK-COVERAGE"),
    "source-index-hash": ("来源索引哈希漂移", mutate_source_index_hash, 1, "CG-SOURCE-BLOCK-COVERAGE"),
    "source-index-not-deterministic": ("结构合法但非原稿确定性产生的索引", mutate_source_index_not_deterministic, 1, "CG-SOURCE-BLOCK-COVERAGE"),
    "uncovered-source-block": ("实质来源块未登记去向", mutate_uncovered_source_block, 1, "CG-SOURCE-BLOCK-COVERAGE"),
    "unknown-source-block": ("素材引用不存在的来源块", mutate_unknown_source_block, 1, "CG-SOURCE-BLOCK-COVERAGE"),
    "missing-reader-evidence": ("纳入素材缺少正文证据", mutate_missing_reader_evidence, 1, "CG-READER-EVIDENCE"),
    "short-reader-evidence": ("操作素材正文证据过短", mutate_short_reader_evidence, 1, "CG-READER-EVIDENCE"),
    "reader-quote-missing": ("正文证据摘录不在目标章节", mutate_missing_reader_quote, 1, "CG-READER-EVIDENCE"),
    "reader-term-missing": ("覆盖词不在正文证据摘录", mutate_reader_term_missing, 1, "CG-READER-EVIDENCE"),
    "invented-source-term": ("覆盖词由模型发明后回写摘要和正文", mutate_invented_source_term, 1, "CG-CLAIM-FIDELITY"),
    "invented-acronym-expansion": ("正文擅自补全来源未给出的缩写全称", mutate_invented_acronym_expansion, 1, "CG-CLAIM-FIDELITY"),
    "term-absent-summary": ("预承诺覆盖词不在素材摘要", mutate_term_absent_from_summary, 1, "CG-READER-EVIDENCE"),
    "single-coverage-term": ("include 素材只有一个预承诺词", mutate_single_coverage_term, 1, "CG-READER-EVIDENCE"),
    "generic-coverage-terms": ("预承诺覆盖词全为通用词", mutate_generic_coverage_terms, 1, "CG-READER-EVIDENCE"),
    "thin-reader-depth": ("来源很长但章节正文被压缩成摘要", mutate_thin_reader_depth, 1, "CG-READER-DEPTH"),
    "overmerged-material": ("单个 include 素材吞并过多来源块", mutate_overmerged_material, 1, "CG-READER-DEPTH"),
    "image-overload": ("短正文插入过多图片", mutate_image_overload, 1, "CG-IMAGE-DENSITY"),
    "omitted-source-image": ("来源图片未完整登记到 manifest", mutate_omitted_source_image, 1, "CG-IMAGE-SOURCE-COVERAGE"),
    "rich-source-zero-insert": ("图片密集来源未选任何代表图", mutate_rich_source_zero_insert, 1, "CG-IMAGE-SELECTION"),
    "source-traversal": ("来源路径穿越", mutate_source_traversal, 1, "CG-CONTRACT-MANIFEST"),
    "empty-chapter": ("空章节", mutate_empty_chapter, 1, "CG-OUTPUT-COMPLETE"),
    "missing-image": ("必插图片缺失", mutate_missing_image, 1, "CG-IMAGE-SET"),
    "wrong-order": ("图片集合相同但顺序错误", mutate_wrong_order, 1, "CG-IMAGE-ORDER"),
    "undeclared-image": ("正文含未声明图片", mutate_undeclared_image, 1, "CG-IMAGE-SET"),
    "material-link": ("素材双向映射断裂", mutate_material_link, 1, "CG-MATERIAL-TRACE"),
    "non-contiguous-material-id": ("素材 ID 未从 MAT-001 连续分配", mutate_non_contiguous_material_id, 1, "CG-CONTRACT-MANIFEST"),
    "speaker-actor": ("讲师作为动作发出者", mutate_speaker_actor, 1, "CG-BOOKLIKE-TONE"),
    "visible-trace": ("正文暴露来源审计元数据", mutate_visible_trace, 1, "CG-AUDIT-SEPARATION"),
    "asset-only-inserted": ("仅资产表图片进入正文", mutate_asset_only_inserted, 1, "CG-IMAGE-SET"),
    "extra-chapter": ("存在未声明章节", mutate_extra_chapter, 1, "CG-OUTPUT-COMPLETE"),
    "too-many-chapters": ("默认生成超过八个章节", mutate_too_many_chapters, 1, "CG-OUTPUT-COMPLETE"),
    "placeholder-filename": ("读者文件名残留模板占位符", mutate_placeholder_filename, 1, "CG-OUTPUT-COMPLETE"),
    "whole-source-omitted": ("整份来源文件未进入索引和 manifest", mutate_whole_source_omitted, 1, "CG-SOURCE-BLOCK-COVERAGE"),
}


def run_probe(case_id: str) -> int:
    name, mutation, expected_code, expected_constraint = CASES[case_id]
    with tempfile.TemporaryDirectory(prefix=f"course-generator-probe-{case_id}-") as temp_dir:
        root = Path(temp_dir) / "course"
        write_fixture(root)
        if mutation:
            mutation(root)
        code, result = run_verifier(root)
    result["probe"] = case_id
    result["probe_expectation"] = {"exit_code": expected_code, "constraint_id": expected_constraint}
    print(f"probe={case_id} ({name}), exit={code}")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Course Generator 验收器故障注入回归")
    parser.add_argument("--probe", choices=sorted(CASES), help="只运行一个探针，并透传领域验证器退出码")
    args = parser.parse_args(argv)
    if args.probe:
        return run_probe(args.probe)

    cases = list(CASES.values())
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="course-generator-selftest-") as temp_dir:
        for index, (name, mutation, expected_code, expected_constraint) in enumerate(cases, 1):
            case_root = Path(temp_dir) / f"case-{index:02d}" / "course"
            write_fixture(case_root)
            if mutation:
                mutation(case_root)
            code, result = run_verifier(case_root)
            failed_ids = result.get("failed_constraint_ids", [])
            ok = code == expected_code and (expected_constraint is None or expected_constraint in failed_ids)
            print(f"{'✅' if ok else '❌'} {name}: exit={code}, failed={failed_ids}")
            if not ok:
                failures.append(name)
        override_name = "用户明确要求时允许把章节上限提高到九章"
        override_root = Path(temp_dir) / "case-explicit-max" / "course"
        write_fixture(override_root)
        mutate_too_many_chapters(override_root)
        override_audit = verify_course(
            override_root.resolve(),
            source_root=override_root.parent / "sources",
            max_chapters=9,
        )
        override_ok = not override_audit.failed_ids
        print(f"{'✅' if override_ok else '❌'} {override_name}: failed={override_audit.failed_ids}")
        if not override_ok:
            failures.append(override_name)
    summary = {"status": "PASS" if not failures else "FAIL", "case_count": len(cases) + 1, "failed_cases": failures}
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
