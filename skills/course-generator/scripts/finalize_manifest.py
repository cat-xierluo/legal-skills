#!/usr/bin/env python3
"""Deterministically reconcile a Course Generator manifest with final reader files.

The script never writes reader prose. It derives audit-only fields from the frozen
source index and the actual Markdown artifacts, then reports any semantic gap that
still requires the producer to improve the reader text.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any


IMAGE_RE = re.compile(r"!\[[^\]\n]*\]\((?:[^()\\\n]|\\.|\([^()\n]*\))*\)")
HEADING_RE = re.compile(r"^#{1,6}\s+")
H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
EXPANDED_MATERIAL_TYPES = {"案例", "操作", "踩坑", "取舍", "疑问"}


def is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def visible_length(text: str) -> int:
    without_images = IMAGE_RE.sub("", text)
    return len(re.sub(r"[#>*_`\-\s]", "", without_images))


def required_evidence_length(material: dict[str, Any]) -> int:
    block_count = max(1, len(material.get("source_block_ids") or []))
    if material.get("type") in EXPANDED_MATERIAL_TYPES:
        return max(80, min(240, 35 * block_count))
    return max(30, min(180, 25 * block_count))


def safe_child(root: Path, relative: Any, label: str) -> Path:
    if not is_nonempty_string(relative):
        raise ValueError(f"{label} 必须是非空相对路径")
    value = str(relative)
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} 不得逃逸课程目录: {value}") from exc
    return candidate


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def paragraphs(text: str) -> list[str]:
    result: list[str] = []
    for raw in re.split(r"\n\s*\n", text):
        paragraph = raw.strip()
        if len(paragraph) < 20 or HEADING_RE.match(paragraph):
            continue
        if visible_length(paragraph) < 20:
            continue
        result.append(paragraph)
    return result


def h2_sections(text: str) -> dict[str, str]:
    """Return uniquely named H2 sections without leaking headings into evidence."""
    matches = list(H2_RE.finditer(text))
    sections: dict[str, str] = {}
    duplicates: set[str] = set()
    for index, match in enumerate(matches):
        heading = match.group(1).strip()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        if heading in sections:
            duplicates.add(heading)
        else:
            sections[heading] = body
    for heading in duplicates:
        sections.pop(heading, None)
    return sections


def evidence_is_valid(
    material: dict[str, Any],
    quotes: Any,
    target_text: str,
    used_signatures: set[str],
) -> bool:
    if not isinstance(quotes, list) or not 1 <= len(quotes) <= 3:
        return False
    normalized = [quote.strip() for quote in quotes if is_nonempty_string(quote)]
    if len(normalized) != len(quotes) or any(len(quote) < 20 for quote in normalized):
        return False
    if any(quote not in target_text for quote in normalized):
        return False
    combined = "\n".join(normalized)
    if any(term not in combined for term in material.get("coverage_terms") or []):
        return False
    if visible_length(combined) < required_evidence_length(material):
        return False
    signature = "\u241e".join(normalized)
    return signature not in used_signatures


def choose_evidence(
    material: dict[str, Any],
    target_text: str,
    used_signatures: set[str],
) -> tuple[list[str] | None, dict[str, Any] | None]:
    terms = [term.strip() for term in material.get("coverage_terms") or [] if is_nonempty_string(term)]
    chapter_paragraphs = paragraphs(target_text)
    missing_terms = [term for term in terms if not any(term in paragraph for paragraph in chapter_paragraphs)]
    if missing_terms:
        return None, {"reason": "coverage_terms 未进入目标正文", "missing_terms": missing_terms}

    term_indexes = {
        index
        for index, paragraph in enumerate(chapter_paragraphs)
        if any(term in paragraph for term in terms)
    }
    pool = set(term_indexes)
    for index in list(term_indexes):
        if index > 0:
            pool.add(index - 1)
        if index + 1 < len(chapter_paragraphs):
            pool.add(index + 1)

    if len(pool) > 18:
        ranked = sorted(
            pool,
            key=lambda index: (
                -sum(term in chapter_paragraphs[index] for term in terms),
                -visible_length(chapter_paragraphs[index]),
                index,
            ),
        )
        keep = set(ranked[:18]) | term_indexes
        pool = set(sorted(keep)[:24])

    minimum = required_evidence_length(material)
    choices: list[tuple[tuple[int, int, int, tuple[int, ...]], list[str]]] = []
    ordered_pool = sorted(pool)
    for size in range(1, 4):
        for indexes in itertools.combinations(ordered_pool, size):
            quotes = [chapter_paragraphs[index] for index in indexes]
            combined = "\n".join(quotes)
            if any(term not in combined for term in terms):
                continue
            length = visible_length(combined)
            if length < minimum:
                continue
            signature = "\u241e".join(quotes)
            if signature in used_signatures:
                continue
            span = indexes[-1] - indexes[0] if len(indexes) > 1 else 0
            choices.append(((size, span, length - minimum, indexes), quotes))

    if not choices:
        return None, {
            "reason": "最多 3 段正文无法同时满足覆盖词、最低长度和证据唯一性",
            "required_length": minimum,
        }
    choices.sort(key=lambda item: item[0])
    return choices[0][1], None


def extract_document_images(text: str) -> list[str]:
    return IMAGE_RE.findall(text)


def finish_result(
    manifest: dict[str, Any],
    manifest_path: Path,
    write: bool,
    updated: dict[str, int],
    unresolved: list[dict[str, Any]],
) -> dict[str, Any]:
    new_text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    original_text = manifest_path.read_text(encoding="utf-8")
    changed = new_text != original_text
    if write and changed:
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{manifest_path.name}.",
            suffix=".tmp",
            dir=manifest_path.parent,
        )
        try:
            os.fchmod(file_descriptor, manifest_path.stat().st_mode & 0o777)
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
                handle.write(new_text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, manifest_path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise
    return {
        "status": "PASS" if not unresolved else "FAIL",
        "written": bool(write and changed),
        "changed": changed,
        "updated": dict(sorted(updated.items())),
        "unresolved_count": len(unresolved),
        "unresolved": unresolved,
        "manifest_sha256": hashlib.sha256(new_text.encode("utf-8")).hexdigest(),
    }


def reconcile_manifest(
    manifest_path: Path,
    write: bool = False,
    phase: str = "final",
) -> dict[str, Any]:
    if phase not in {"ledger", "final"}:
        raise ValueError(f"未知 phase: {phase}")
    manifest_path = manifest_path.resolve()
    course_root = manifest_path.parent
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError("manifest 顶层必须是对象")

    source_index_info = manifest.get("source_index")
    if not isinstance(source_index_info, dict):
        raise ValueError("manifest.source_index 必须是对象")
    source_index_path = safe_child(course_root, source_index_info.get("file"), "source_index.file")
    source_index = load_json(source_index_path)
    if not isinstance(source_index, dict):
        raise ValueError("source-index 顶层必须是对象")

    blocks: list[dict[str, Any]] = []
    for source in source_index.get("sources") or []:
        if isinstance(source, dict):
            blocks.extend(block for block in source.get("blocks") or [] if isinstance(block, dict))
    block_refs = {
        block.get("id"): block.get("source_ref")
        for block in blocks
        if is_nonempty_string(block.get("id")) and is_nonempty_string(block.get("source_ref"))
    }

    unresolved: list[dict[str, Any]] = []
    updated = defaultdict(int)

    actual_index_sha256 = hashlib.sha256(source_index_path.read_bytes()).hexdigest()
    if source_index_info.get("sha256") != actual_index_sha256:
        source_index_info["sha256"] = actual_index_sha256
        updated["source_index_sha256"] += 1

    for material in manifest.get("materials") or []:
        if not isinstance(material, dict):
            continue
        material_id = material.get("id") or "<unknown>"
        source_refs: list[str] = []
        missing_blocks: list[str] = []
        for block_id in material.get("source_block_ids") or []:
            source_ref = block_refs.get(block_id)
            if not source_ref:
                missing_blocks.append(str(block_id))
            elif source_ref not in source_refs:
                source_refs.append(source_ref)
        if missing_blocks:
            unresolved.append({"kind": "source_refs", "id": material_id, "missing_blocks": missing_blocks})
        elif source_refs and material.get("source_refs") != source_refs:
            material["source_refs"] = source_refs
            updated["material_source_refs"] += 1

    chapters_by_id = {
        chapter.get("id"): chapter
        for chapter in manifest.get("chapters") or []
        if isinstance(chapter, dict) and is_nonempty_string(chapter.get("id"))
    }
    material_ids_by_chapter: dict[str, list[str]] = defaultdict(list)
    source_refs_by_chapter: dict[str, list[str]] = defaultdict(list)
    section_counts: dict[tuple[str, str], int] = defaultdict(int)
    for material in manifest.get("materials") or []:
        if not isinstance(material, dict) or material.get("disposition") != "include":
            continue
        material_id = material.get("id")
        chapter_id = material.get("target_chapter_id")
        section_heading = material.get("target_section_heading")
        chapter = chapters_by_id.get(chapter_id)
        if chapter is None:
            unresolved.append({"kind": "chapter_target", "id": material_id or "<unknown>", "reason": f"目标章节 {chapter_id!r} 不存在"})
            continue
        declared_sections = chapter.get("section_headings")
        if not is_nonempty_string(section_heading) or not isinstance(declared_sections, list) or section_heading not in declared_sections:
            unresolved.append(
                {
                    "kind": "section_target",
                    "id": material_id or "<unknown>",
                    "reason": f"目标小节 {section_heading!r} 未在 {chapter_id} 的 section_headings 声明",
                }
            )
            continue
        if is_nonempty_string(material_id):
            material_ids_by_chapter[chapter_id].append(material_id)
        section_counts[(chapter_id, section_heading)] += 1
        for source_ref in material.get("source_refs") or []:
            if is_nonempty_string(source_ref) and source_ref not in source_refs_by_chapter[chapter_id]:
                source_refs_by_chapter[chapter_id].append(source_ref)

    for chapter_id, chapter in chapters_by_id.items():
        material_ids = material_ids_by_chapter.get(chapter_id, [])
        source_refs = source_refs_by_chapter.get(chapter_id, [])
        if chapter.get("material_ids") != material_ids:
            chapter["material_ids"] = material_ids
            updated["chapter_material_ids"] += 1
        if chapter.get("source_refs") != source_refs:
            chapter["source_refs"] = source_refs
            updated["chapter_source_refs"] += 1
        for heading in chapter.get("section_headings") or []:
            if is_nonempty_string(heading) and section_counts.get((chapter_id, heading), 0) == 0:
                unresolved.append(
                    {
                        "kind": "section_target",
                        "id": chapter_id,
                        "reason": f"小节 {heading!r} 没有任何 include 素材",
                    }
                )

    if phase == "ledger":
        return finish_result(manifest, manifest_path, write, updated, unresolved)

    document_records: list[tuple[str, dict[str, Any]]] = []
    overview = manifest.get("overview")
    if isinstance(overview, dict):
        document_records.append(("OVERVIEW", overview))
    for chapter in manifest.get("chapters") or []:
        if isinstance(chapter, dict) and is_nonempty_string(chapter.get("id")):
            document_records.append((chapter["id"], chapter))

    reader_texts: dict[str, str] = {}
    reader_sections: dict[str, dict[str, str]] = {}
    document_images: dict[str, list[str]] = {}
    unreadable_documents: set[str] = set()
    for document_id, record in document_records:
        try:
            path = safe_child(course_root, record.get("file"), f"{document_id}.file")
            text = path.read_text(encoding="utf-8")
        except (OSError, ValueError) as exc:
            unresolved.append({"kind": "reader_file", "id": document_id, "reason": str(exc)})
            unreadable_documents.add(document_id)
            continue
        reader_texts[document_id] = text
        reader_sections[document_id] = h2_sections(text)
        document_images[document_id] = extract_document_images(text)

    image_records = [item for item in manifest.get("images") or [] if isinstance(item, dict)]
    markdown_to_ids: dict[str, list[str]] = defaultdict(list)
    image_by_id: dict[str, dict[str, Any]] = {}
    for image in image_records:
        image_id = image.get("id")
        markdown = image.get("original_markdown")
        if is_nonempty_string(image_id):
            image_by_id[image_id] = image
        if is_nonempty_string(image_id) and is_nonempty_string(markdown):
            markdown_to_ids[markdown].append(image_id)

    observed_targets: dict[str, str] = {}
    used_image_ids: set[str] = set()
    for document_id, record in document_records:
        if document_id in unreadable_documents:
            continue
        actual_ids: list[str] = []
        for markdown in document_images.get(document_id, []):
            candidates = [image_id for image_id in markdown_to_ids.get(markdown, []) if image_id not in used_image_ids]
            if not candidates:
                unresolved.append({"kind": "image", "id": document_id, "reason": "正文图片未能唯一匹配 manifest", "markdown": markdown})
                continue
            image_id = candidates[0]
            actual_ids.append(image_id)
            used_image_ids.add(image_id)
            observed_targets[image_id] = document_id
        if record.get("image_ids") != actual_ids:
            record["image_ids"] = actual_ids
            updated["document_image_ids"] += 1

    for image_id, image in image_by_id.items():
        target = observed_targets.get(image_id)
        if target:
            if image.get("body_action") != "insert" or image.get("target_document_id") != target:
                image["body_action"] = "insert"
                image["target_document_id"] = target
                updated["image_records"] += 1
        elif image.get("target_document_id") in unreadable_documents:
            continue
        elif image.get("body_action") == "insert" or image.get("target_document_id") is not None:
            image["body_action"] = "asset_only"
            image["target_document_id"] = None
            image.setdefault("reason", "未进入最终读者正文，保留为来源资产。")
            updated["image_records"] += 1

    used_signatures: set[str] = set()
    for material in manifest.get("materials") or []:
        if not isinstance(material, dict) or material.get("disposition") != "include":
            continue
        material_id = material.get("id") or "<unknown>"
        target = material.get("target_chapter_id")
        target_heading = material.get("target_section_heading")
        target_text = reader_texts.get(str(target))
        if target_text is None:
            unresolved.append({"kind": "reader_evidence", "id": material_id, "reason": f"目标章节 {target!r} 不可读"})
            continue
        if not is_nonempty_string(target_heading):
            unresolved.append({"kind": "reader_evidence", "id": material_id, "reason": "缺少 target_section_heading"})
            continue
        section_text = reader_sections.get(str(target), {}).get(str(target_heading).strip())
        if section_text is None:
            unresolved.append(
                {
                    "kind": "reader_evidence",
                    "id": material_id,
                    "reason": f"目标小节 {target_heading!r} 在章节 {target!r} 中不存在或重复",
                }
            )
            continue
        current = material.get("reader_evidence")
        current_quotes = current.get("quotes") if isinstance(current, dict) else None
        if evidence_is_valid(material, current_quotes, section_text, used_signatures):
            used_signatures.add("\u241e".join(quote.strip() for quote in current_quotes))
            continue
        quotes, problem = choose_evidence(material, section_text, used_signatures)
        if quotes is None:
            unresolved.append({"kind": "reader_evidence", "id": material_id, **(problem or {})})
            continue
        material["reader_evidence"] = {"quotes": quotes}
        used_signatures.add("\u241e".join(quotes))
        updated["reader_evidence"] += 1

    return finish_result(manifest, manifest_path, write, updated, unresolved)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从 source-index 和最终 Markdown 确定性收口 course-manifest.json"
    )
    parser.add_argument("manifest", type=Path, help="课程目录内的 course-manifest.json")
    parser.add_argument(
        "--phase",
        choices=("ledger", "final"),
        default="final",
        help="ledger 只同步索引可推导字段；final 另同步正文证据和图片映射",
    )
    parser.add_argument("--write", action="store_true", help="原子写回可确定修复；默认只预览")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        result = reconcile_manifest(args.manifest, write=args.write, phase=args.phase)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
