#!/usr/bin/env python3
"""Verify a Course Generator v2.9.4 course directory against its source index and manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from index_sources import discover_sources, iter_file_blocks, sha256_bytes


ALL_CONSTRAINTS = (
    "CG-CONTRACT-MANIFEST",
    "CG-OUTPUT-COMPLETE",
    "CG-MATERIAL-TRACE",
    "CG-SOURCE-BLOCK-COVERAGE",
    "CG-READER-EVIDENCE",
    "CG-CLAIM-FIDELITY",
    "CG-READER-DEPTH",
    "CG-IMAGE-SOURCE-COVERAGE",
    "CG-IMAGE-SET",
    "CG-IMAGE-ORDER",
    "CG-IMAGE-SELECTION",
    "CG-IMAGE-DENSITY",
    "CG-BOOKLIKE-TONE",
    "CG-AUDIT-SEPARATION",
)

ID_PATTERNS = {
    "source": re.compile(r"^SRC-[0-9]{3,}$"),
    "chapter": re.compile(r"^CH-[0-9]{2,3}$"),
    "material": re.compile(r"^MAT-[0-9]{3,}$"),
    "block": re.compile(r"^BLK-[0-9]{5,}$"),
    "image": re.compile(r"^IMG-[0-9]{3,}$"),
}

OVERVIEW_FILE_RE = re.compile(r"^00[ _-].+\.md$")
CHAPTER_FILE_RE = re.compile(r"^[0-9]{2}[ _-].+\.md$")
NUMBERED_MD_RE = re.compile(r"^[0-9]{2}[ _-].+\.md$")
IMAGE_RE = re.compile(r"!\[[^\]\n]*\]\((?:[^()\\\n]|\\.|\([^()\n]*\))*\)")
SPEAKER_AS_ACTOR_RE = re.compile(
    r"(?:讲者|讲师|主讲人)(?:在[^，。；：\n]{0,8})?"
    r"(?:强调|指出|提到|认为|表示|推荐|演示|警告|坦言|自嘲|说道|说|介绍|解释|建议|提醒|分享)"
)
SOURCE_FRAME_RE = re.compile(
    r"现场演示|课程现场|现场问答|本次分享中|根据原文|原文中|主讲人提到"
)
FILLER_RE = re.compile(r"这样的一个|也而且|这个那个|的话就是说")
VISIBLE_TRACE_RE = re.compile(
    r"^\s*>?\s*(?:原文区间|内容来源|生成来源|素材编号)\s*[:：]", re.MULTILINE
)
SOURCE_BLOCK_REF_RE = re.compile(r"^(SRC-[0-9]{3,})#L[0-9]{4,}-L[0-9]{4,}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SOURCE_BLOCK_KINDS = {"content", "derived", "heading", "image", "timestamp", "speaker", "separator"}
SKIP_CODES = {"derived_duplicate", "meeting", "device", "chatter", "pure_repeat", "no_course_value"}
EXPANDED_MATERIAL_TYPES = {"案例", "操作", "踩坑", "取舍", "疑问"}
GENERIC_COVERAGE_TERMS = {
    "ai", "agent", "skill", "word", "markdown", "内容", "结果", "过程", "任务", "工作",
    "方法", "材料", "操作", "课程", "生成", "进行", "这个", "可以",
}
MAX_INCLUDE_BLOCKS_PER_MATERIAL = 6
GLOBAL_READER_DEPTH_RATIO = 0.55
CHAPTER_READER_DEPTH_RATIO = 0.40
IMAGE_PROSE_BUDGET = 500
MIN_DOCUMENT_IMAGE_BUDGET = 3
RICH_SOURCE_IMAGE_THRESHOLD = 12
SOURCE_IMAGES_PER_REQUIRED_READER_IMAGE = 20
DEFAULT_MAX_CHAPTERS = 8
INVALID_FILENAME_RE = re.compile(r'[:*?"<>|]')
TEMPLATE_MARKER_RE = re.compile(
    r"\[(?:课程名称|主题名称|基于原文生成|待替换|TBD|TODO)[^\]]*\]"
    r"|<\s*(?:课程名称|主题名称|待替换)\s*>"
    r"|基于原文生成|待替换|\bTBD\b|\bTODO\b",
    re.IGNORECASE,
)
BODY_TEMPLATE_MARKER_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\[(?:课程名称|主题名称|基于原文生成|待替换|TBD|TODO)[^\]]*\]"
    r"|<\s*(?:课程名称|主题名称|待替换)\s*>|基于原文生成|待替换|TBD|TODO)"
    r"(?:\s*[-—:：].*)?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
ACRONYM_EXPANSION_RE = re.compile(
    r"\b([A-Z][A-Z0-9._-]{1,15})\s*[（(]([^）)\n]{2,80})[）)]"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_images(text: str) -> list[str]:
    return IMAGE_RE.findall(text)


def visible_prose_char_count(text: str) -> int:
    """Count reader-facing text while excluding image markup and Markdown syntax."""
    visible = IMAGE_RE.sub("", text)
    visible = re.sub(r"```.*?```", "", visible, flags=re.DOTALL)
    visible = re.sub(r"\[([^\]\n]+)\]\([^\n)]+\)", r"\1", visible)
    visible = re.sub(r"^\s{0,3}#{1,6}\s*", "", visible, flags=re.MULTILINE)
    visible = re.sub(r"^\s*(?:[-*+]|[0-9]+[.)、])\s+", "", visible, flags=re.MULTILINE)
    visible = re.sub(r"[#>*_`~|\\\s]", "", visible)
    return len(visible)


def normalize_fidelity_text(text: str) -> str:
    """Normalize only presentation differences; retain the underlying words."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(char for char in normalized if char.isalnum())


def validate_reader_filename(value: Any, label: str, audit: "Audit") -> None:
    if not isinstance(value, str):
        return
    if "/" in value or Path(value).name != value:
        audit.fail("CG-OUTPUT-COMPLETE", f"{label} 必须是课程根目录下的单个文件名: {value}")
    if "[" in value or "]" in value or INVALID_FILENAME_RE.search(value):
        audit.fail("CG-OUTPUT-COMPLETE", f"{label} 含模板括号或跨平台非法字符: {value}")
    if TEMPLATE_MARKER_RE.search(value):
        audit.fail("CG-OUTPUT-COMPLETE", f"{label} 含未替换模板标记: {value}")


class Audit:
    def __init__(self) -> None:
        self.failures: dict[str, list[str]] = defaultdict(list)
        self.warnings: list[str] = []
        self.measurements: dict[str, dict[str, Any]] = {}
        self.observables: dict[str, Any] = {}
        self.artifact_sha256: dict[str, str] = {}

    def fail(self, constraint_id: str, message: str) -> None:
        if message not in self.failures[constraint_id]:
            self.failures[constraint_id].append(message)

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    @property
    def failed_ids(self) -> list[str]:
        return [item for item in ALL_CONSTRAINTS if item in self.failures]

    @property
    def passed_ids(self) -> list[str]:
        return [item for item in ALL_CONSTRAINTS if item not in self.failures]


def is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def duplicate_items(values: list[str]) -> list[str]:
    counts = Counter(values)
    return sorted(item for item, count in counts.items() if count > 1)


def safe_relative_path(root: Path, raw: Any, label: str, audit: Audit) -> Path | None:
    if not is_nonempty_string(raw):
        audit.fail("CG-CONTRACT-MANIFEST", f"{label} 必须是非空相对路径")
        return None
    value = raw.strip()
    if "\\" in value or value.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", value):
        audit.fail("CG-CONTRACT-MANIFEST", f"{label} 不允许绝对路径或反斜杠: {value}")
        return None
    parts = Path(value).parts
    if ".." in parts:
        audit.fail("CG-CONTRACT-MANIFEST", f"{label} 不允许路径穿越: {value}")
        return None
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        audit.fail("CG-CONTRACT-MANIFEST", f"{label} 超出课程目录: {value}")
        return None
    return candidate


def validate_portable_relative(value: Any, label: str, audit: Audit) -> str | None:
    if not is_nonempty_string(value):
        audit.fail("CG-CONTRACT-MANIFEST", f"{label} 必须是非空相对路径")
        return None
    raw = value.strip()
    if "\\" in raw or raw.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", raw) or ".." in Path(raw).parts:
        audit.fail("CG-CONTRACT-MANIFEST", f"{label} 必须是无路径穿越的可移植相对路径: {raw}")
        return None
    return raw


def require_list(value: Any, label: str, audit: Audit, *, nonempty: bool = False) -> list[Any]:
    if not isinstance(value, list):
        audit.fail("CG-CONTRACT-MANIFEST", f"{label} 必须是数组")
        return []
    if nonempty and not value:
        audit.fail("CG-CONTRACT-MANIFEST", f"{label} 不得为空")
    return value


def check_allowed_keys(obj: Any, required: set[str], optional: set[str], label: str, audit: Audit) -> dict[str, Any]:
    if not isinstance(obj, dict):
        audit.fail("CG-CONTRACT-MANIFEST", f"{label} 必须是对象")
        return {}
    missing = sorted(required - set(obj))
    unknown = sorted(set(obj) - required - optional)
    if missing:
        audit.fail("CG-CONTRACT-MANIFEST", f"{label} 缺少字段: {', '.join(missing)}")
    if unknown:
        audit.fail("CG-CONTRACT-MANIFEST", f"{label} 含未知字段: {', '.join(unknown)}")
    return obj


def validate_id(value: Any, kind: str, label: str, audit: Audit) -> str | None:
    if not isinstance(value, str) or not ID_PATTERNS[kind].fullmatch(value):
        audit.fail("CG-CONTRACT-MANIFEST", f"{label} 格式非法: {value!r}")
        return None
    return value


def validate_source_refs(value: Any, label: str, source_ids: set[str], audit: Audit, *, nonempty: bool = True) -> list[str]:
    refs = require_list(value, label, audit, nonempty=nonempty)
    valid: list[str] = []
    for ref in refs:
        if not is_nonempty_string(ref):
            audit.fail("CG-CONTRACT-MANIFEST", f"{label} 含空或非字符串引用")
            continue
        source_id = ref.split("#", 1)[0]
        if source_id not in source_ids:
            audit.fail("CG-MATERIAL-TRACE", f"{label} 引用了不存在的来源 {source_id}")
            continue
        valid.append(ref)
    if duplicate_items(valid):
        audit.fail("CG-CONTRACT-MANIFEST", f"{label} 含重复引用")
    return valid


def read_required_text(path: Path | None, label: str, audit: Audit) -> str | None:
    if path is None:
        return None
    if not path.is_file():
        audit.fail("CG-OUTPUT-COMPLETE", f"{label} 不存在: {path.name}")
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        audit.fail("CG-OUTPUT-COMPLETE", f"{label} 无法按 UTF-8 读取: {exc}")
        return None
    if not text.strip():
        audit.fail("CG-OUTPUT-COMPLETE", f"{label} 为空文件: {path.name}")
    return text


def load_manifest(root: Path, manifest_name: str, audit: Audit) -> tuple[dict[str, Any], Path | None]:
    manifest_path = safe_relative_path(root, manifest_name, "manifest", audit)
    if manifest_path is None:
        return {}, None
    if not manifest_path.is_file():
        audit.fail("CG-CONTRACT-MANIFEST", f"缺少 {manifest_name}")
        return {}, manifest_path
    try:
        raw = manifest_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        audit.fail("CG-CONTRACT-MANIFEST", f"manifest 无法读取或 JSON 非法: {exc}")
        return {}, manifest_path
    if not isinstance(data, dict):
        audit.fail("CG-CONTRACT-MANIFEST", "manifest 顶层必须是对象")
        return {}, manifest_path
    audit.artifact_sha256["course-manifest"] = sha256_file(manifest_path)
    return data, manifest_path


def load_json_artifact(path: Path | None, label: str, audit: Audit, constraint_id: str) -> dict[str, Any]:
    if path is None or not path.is_file():
        audit.fail(constraint_id, f"缺少 {label}")
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        audit.fail(constraint_id, f"{label} 无法读取或 JSON 非法: {exc}")
        return {}
    if not isinstance(data, dict):
        audit.fail(constraint_id, f"{label} 顶层必须是对象")
        return {}
    return data


def verify_course(
    root: Path,
    manifest_name: str = "course-manifest.json",
    source_root: Path | None = None,
    max_chapters: int = DEFAULT_MAX_CHAPTERS,
) -> Audit:
    audit = Audit()
    if max_chapters < 1:
        audit.fail("CG-CONTRACT-MANIFEST", "max_chapters 必须为正整数")
        max_chapters = DEFAULT_MAX_CHAPTERS
    manifest, _ = load_manifest(root, manifest_name, audit)
    if not manifest:
        if "CG-CONTRACT-MANIFEST" not in audit.failures:
            audit.fail("CG-CONTRACT-MANIFEST", "manifest 不得是空对象")
        for constraint_id in ALL_CONSTRAINTS[1:]:
            audit.fail(constraint_id, "manifest 不可用，无法执行该项检查")
        return audit

    top = check_allowed_keys(
        manifest,
        {"schema_version", "generator_version", "course", "sources", "source_index", "overview", "chapters", "materials", "images"},
        {"audit_files"},
        "manifest",
        audit,
    )
    if top.get("schema_version") != "1.2":
        audit.fail("CG-CONTRACT-MANIFEST", "schema_version 必须为 1.2；旧版课程需升级多摘录与忠实度契约")
    if not is_nonempty_string(top.get("generator_version")):
        audit.fail("CG-CONTRACT-MANIFEST", "generator_version 必须是非空字符串")
    course = check_allowed_keys(top.get("course"), {"title"}, {"training_date", "organizer"}, "course", audit)
    if not is_nonempty_string(course.get("title")):
        audit.fail("CG-CONTRACT-MANIFEST", "course.title 必须是非空字符串")
    if "training_date" in course:
        try:
            date.fromisoformat(course["training_date"])
        except (TypeError, ValueError):
            audit.fail("CG-CONTRACT-MANIFEST", "course.training_date 必须是有效的 YYYY-MM-DD 日期")
    if "organizer" in course and not is_nonempty_string(course["organizer"]):
        audit.fail("CG-CONTRACT-MANIFEST", "course.organizer 必须是非空字符串")
    if is_nonempty_string(course.get("title")) and TEMPLATE_MARKER_RE.search(course["title"]):
        audit.fail("CG-OUTPUT-COMPLETE", f"course.title 含未替换模板标记: {course['title']}")

    source_ids: set[str] = set()
    source_paths: list[str] = []
    manifest_sources: list[tuple[str, str]] = []
    for index, item in enumerate(require_list(top.get("sources"), "sources", audit, nonempty=True), 1):
        source = check_allowed_keys(item, {"id", "path"}, set(), f"sources[{index}]", audit)
        source_id = validate_id(source.get("id"), "source", f"sources[{index}].id", audit)
        if source_id:
            if source_id in source_ids:
                audit.fail("CG-CONTRACT-MANIFEST", f"重复来源 ID: {source_id}")
            source_ids.add(source_id)
        source_path = validate_portable_relative(source.get("path"), f"sources[{index}].path", audit)
        if source_path:
            source_paths.append(source_path)
        if source_id and source_path:
            manifest_sources.append((source_id, source_path))
    if duplicate_items(source_paths):
        audit.fail("CG-CONTRACT-MANIFEST", "sources.path 不得重复")

    source_index_contract = check_allowed_keys(
        top.get("source_index"), {"file", "sha256"}, set(), "source_index", audit
    )
    source_index_path = safe_relative_path(root, source_index_contract.get("file"), "source_index.file", audit)
    expected_source_index_sha = source_index_contract.get("sha256")
    if not isinstance(expected_source_index_sha, str) or not SHA256_RE.fullmatch(expected_source_index_sha):
        audit.fail("CG-CONTRACT-MANIFEST", "source_index.sha256 必须是小写 64 位 SHA-256")
    source_index = load_json_artifact(
        source_index_path, "source-index.json", audit, "CG-SOURCE-BLOCK-COVERAGE"
    )
    if source_index_path and source_index_path.is_file():
        actual_source_index_sha = sha256_file(source_index_path)
        audit.artifact_sha256["source-index"] = actual_source_index_sha
        if expected_source_index_sha != actual_source_index_sha:
            audit.fail("CG-SOURCE-BLOCK-COVERAGE", "source_index.sha256 与真实文件不一致")

    content_block_ids: set[str] = set()
    content_block_char_counts: dict[str, int] = {}
    all_block_ids: set[str] = set()
    indexed_image_blocks: list[tuple[str, str]] = []
    source_index_pairs: list[tuple[str, str]] = []
    indexed_source_sha: dict[str, str] = {}
    if source_index:
        index_top = check_allowed_keys(source_index, {"schema_version", "sources"}, set(), "source-index", audit)
        if index_top.get("schema_version") != "1.1":
            audit.fail("CG-SOURCE-BLOCK-COVERAGE", "source-index.schema_version 必须为 1.1")
        for index, item in enumerate(require_list(index_top.get("sources"), "source-index.sources", audit, nonempty=True), 1):
            label = f"source-index.sources[{index}]"
            source = check_allowed_keys(item, {"id", "path", "sha256", "blocks"}, set(), label, audit)
            source_id = validate_id(source.get("id"), "source", f"{label}.id", audit)
            source_path = validate_portable_relative(source.get("path"), f"{label}.path", audit)
            source_sha = source.get("sha256")
            if not isinstance(source_sha, str) or not SHA256_RE.fullmatch(source_sha):
                audit.fail("CG-SOURCE-BLOCK-COVERAGE", f"{label}.sha256 非法")
            if source_id and source_path:
                source_index_pairs.append((source_id, source_path))
                if isinstance(source_sha, str):
                    indexed_source_sha[source_path] = source_sha
            for block_index, block_item in enumerate(require_list(source.get("blocks"), f"{label}.blocks", audit), 1):
                block_label = f"{label}.blocks[{block_index}]"
                block = check_allowed_keys(
                    block_item,
                    {"id", "source_ref", "kind", "char_count", "sha256", "preview"},
                    set(),
                    block_label,
                    audit,
                )
                block_id = validate_id(block.get("id"), "block", f"{block_label}.id", audit)
                if block_id:
                    if block_id in all_block_ids:
                        audit.fail("CG-SOURCE-BLOCK-COVERAGE", f"重复来源块 ID: {block_id}")
                    all_block_ids.add(block_id)
                source_ref = block.get("source_ref")
                ref_match = SOURCE_BLOCK_REF_RE.fullmatch(source_ref) if isinstance(source_ref, str) else None
                if not ref_match or (source_id and ref_match.group(1) != source_id):
                    audit.fail("CG-SOURCE-BLOCK-COVERAGE", f"{block_label}.source_ref 与来源 ID 不一致")
                kind = block.get("kind")
                if kind not in SOURCE_BLOCK_KINDS:
                    audit.fail("CG-SOURCE-BLOCK-COVERAGE", f"{block_label}.kind 非法")
                if kind == "content" and block_id:
                    content_block_ids.add(block_id)
                char_count = block.get("char_count")
                if not isinstance(char_count, int) or char_count < 1:
                    audit.fail("CG-SOURCE-BLOCK-COVERAGE", f"{block_label}.char_count 必须为正整数")
                elif kind == "content" and block_id:
                    content_block_char_counts[block_id] = char_count
                block_sha = block.get("sha256")
                if not isinstance(block_sha, str) or not SHA256_RE.fullmatch(block_sha):
                    audit.fail("CG-SOURCE-BLOCK-COVERAGE", f"{block_label}.sha256 非法")
                elif kind == "image" and isinstance(source_ref, str):
                    indexed_image_blocks.append((source_ref, block_sha))
                if not is_nonempty_string(block.get("preview")) or len(str(block.get("preview", ""))) > 160:
                    audit.fail("CG-SOURCE-BLOCK-COVERAGE", f"{block_label}.preview 必须为 1—160 字符")
        if source_index_pairs != manifest_sources:
            audit.fail(
                "CG-SOURCE-BLOCK-COVERAGE",
                f"source-index 来源清单与 manifest 不一致: {source_index_pairs!r} != {manifest_sources!r}",
            )
        if not content_block_ids:
            audit.fail("CG-SOURCE-BLOCK-COVERAGE", "source-index 未产生任何 content block")

    raw_source_block_texts: dict[str, str] = {}
    raw_source_text_parts: list[str] = []
    source_root_rebound = False
    if source_root is not None:
        raw_input = source_root.expanduser().resolve()
        output_hint = source_index_path or (root / "source-index.json")
        try:
            raw_root, discovered_sources = discover_sources(raw_input, output_hint)
        except (OSError, ValueError) as exc:
            audit.fail("CG-SOURCE-BLOCK-COVERAGE", f"无法枚举 source_root: {exc}")
        else:
            expected_manifest_sources = [
                (f"SRC-{index:03d}", path.relative_to(raw_root).as_posix())
                for index, path in enumerate(discovered_sources, 1)
            ]
            if manifest_sources != expected_manifest_sources:
                audit.fail(
                    "CG-SOURCE-BLOCK-COVERAGE",
                    f"source_root 完整来源清单与 manifest 不一致: {expected_manifest_sources!r} != {manifest_sources!r}",
                )

            recomputed_sources: list[dict[str, Any]] = []
            block_ordinal = 0
            can_compare_index = True
            for source_id, raw_path in zip(
                (item[0] for item in expected_manifest_sources), discovered_sources
            ):
                relative = raw_path.relative_to(raw_root).as_posix()
                raw_sha = sha256_file(raw_path)
                if indexed_source_sha.get(relative) != raw_sha:
                    audit.fail("CG-SOURCE-BLOCK-COVERAGE", f"来源文件哈希与 source-index 不一致: {relative}")
                    can_compare_index = False
                recomputed_blocks = []
                try:
                    for kind, start_line, end_line, text in iter_file_blocks(raw_path):
                        block_ordinal += 1
                        block_id = f"BLK-{block_ordinal:05d}"
                        raw_source_block_texts[block_id] = text
                        raw_source_text_parts.append(text)
                        recomputed_blocks.append(
                            {
                                "id": block_id,
                                "source_ref": f"{source_id}#L{start_line:04d}-L{end_line:04d}",
                                "kind": kind,
                                "char_count": len(text),
                                "sha256": sha256_bytes(text.encode("utf-8")),
                                "preview": re.sub(r"\s+", " ", text).strip()[:160],
                            }
                        )
                except (OSError, UnicodeError) as exc:
                    audit.fail("CG-SOURCE-BLOCK-COVERAGE", f"来源无法重建索引 {relative}: {exc}")
                    can_compare_index = False
                    continue
                recomputed_sources.append(
                    {
                        "id": source_id,
                        "path": relative,
                        "sha256": raw_sha,
                        "blocks": recomputed_blocks,
                    }
                )
            if can_compare_index and source_index.get("sources") != recomputed_sources:
                audit.fail(
                    "CG-SOURCE-BLOCK-COVERAGE",
                    "source-index 不是当前原始来源按确定性分块算法产生的完整结果",
                )
            elif can_compare_index:
                source_root_rebound = True
    elif source_index:
        audit.warn("未提供 --source-root；已验证来源索引内部契约，但未重新绑定原始来源文件")
    if not source_root_rebound:
        audit.fail("CG-CLAIM-FIDELITY", "必须提供可重绑定的 --source-root，才能验证覆盖词与缩写释义未超出来源")
    normalized_raw_source = normalize_fidelity_text("\n".join(raw_source_text_parts))

    overview = check_allowed_keys(top.get("overview"), {"file", "image_ids"}, set(), "overview", audit)
    overview_file = overview.get("file")
    if not isinstance(overview_file, str) or not OVERVIEW_FILE_RE.fullmatch(overview_file):
        audit.fail("CG-CONTRACT-MANIFEST", "overview.file 必须匹配 00 [名称].md")
    overview_path = safe_relative_path(root, overview_file, "overview.file", audit)
    validate_reader_filename(overview_file, "overview.file", audit)
    overview_image_ids = require_list(overview.get("image_ids"), "overview.image_ids", audit)
    overview_image_ids = [item for item in overview_image_ids if validate_id(item, "image", "overview.image_ids[]", audit)]
    if duplicate_items(overview_image_ids):
        audit.fail("CG-CONTRACT-MANIFEST", "overview.image_ids 不得重复")

    chapter_ids: set[str] = set()
    chapter_files: set[str] = set()
    chapter_records: list[dict[str, Any]] = []
    chapter_material_membership: dict[str, list[str]] = defaultdict(list)
    chapter_image_membership: dict[str, list[str]] = defaultdict(list)
    raw_chapters = require_list(top.get("chapters"), "chapters", audit, nonempty=True)
    if len(raw_chapters) > max_chapters:
        audit.fail(
            "CG-OUTPUT-COMPLETE",
            f"章节数为 {len(raw_chapters)}，超过本次上限 {max_chapters}；只有用户明确要求时才可用 --max-chapters 提高上限",
        )
    for index, item in enumerate(raw_chapters, 1):
        label = f"chapters[{index}]"
        chapter = check_allowed_keys(item, {"id", "file", "title", "source_refs", "material_ids", "image_ids"}, set(), label, audit)
        chapter_id = validate_id(chapter.get("id"), "chapter", f"{label}.id", audit)
        file_name = chapter.get("file")
        if chapter_id:
            if chapter_id in chapter_ids:
                audit.fail("CG-CONTRACT-MANIFEST", f"重复章节 ID: {chapter_id}")
            chapter_ids.add(chapter_id)
        if not isinstance(file_name, str) or not CHAPTER_FILE_RE.fullmatch(file_name):
            audit.fail("CG-CONTRACT-MANIFEST", f"{label}.file 必须匹配两位编号章节 Markdown")
        elif file_name[:2] in {"00", "98", "99"}:
            audit.fail("CG-CONTRACT-MANIFEST", f"{label}.file 使用了保留编号: {file_name}")
        elif file_name in chapter_files:
            audit.fail("CG-CONTRACT-MANIFEST", f"重复章节文件: {file_name}")
        else:
            chapter_files.add(file_name)
        validate_reader_filename(file_name, f"{label}.file", audit)
        if not is_nonempty_string(chapter.get("title")):
            audit.fail("CG-CONTRACT-MANIFEST", f"{label}.title 必须非空")
        elif TEMPLATE_MARKER_RE.search(chapter["title"]):
            audit.fail("CG-OUTPUT-COMPLETE", f"{label}.title 含未替换模板标记: {chapter['title']}")
        validate_source_refs(chapter.get("source_refs"), f"{label}.source_refs", source_ids, audit)
        material_values = require_list(chapter.get("material_ids"), f"{label}.material_ids", audit)
        material_values = [value for value in material_values if validate_id(value, "material", f"{label}.material_ids[]", audit)]
        image_values = require_list(chapter.get("image_ids"), f"{label}.image_ids", audit)
        image_values = [value for value in image_values if validate_id(value, "image", f"{label}.image_ids[]", audit)]
        if duplicate_items(material_values):
            audit.fail("CG-MATERIAL-TRACE", f"{label}.material_ids 含重复项")
        if duplicate_items(image_values):
            audit.fail("CG-IMAGE-SET", f"{label}.image_ids 含重复项")
        if chapter_id:
            chapter_material_membership[chapter_id] = material_values
            chapter_image_membership[chapter_id] = image_values
        chapter_records.append({"id": chapter_id, "file": file_name, "path": safe_relative_path(root, file_name, f"{label}.file", audit), "image_ids": image_values})

    material_ids: set[str] = set()
    included_materials = 0
    covered_content_blocks: set[str] = set()
    block_dispositions: dict[str, set[str]] = defaultdict(set)
    included_blocks_by_chapter: dict[str, set[str]] = defaultdict(set)
    evidence_records: list[dict[str, Any]] = []
    raw_materials = require_list(top.get("materials"), "materials", audit, nonempty=True)
    for index, item in enumerate(raw_materials, 1):
        label = f"materials[{index}]"
        material = check_allowed_keys(
            item,
            {"id", "type", "summary", "source_refs", "source_block_ids", "coverage_terms", "disposition", "target_chapter_id", "reader_evidence"},
            {"skip_reason", "skip_code"},
            label,
            audit,
        )
        material_id = validate_id(material.get("id"), "material", f"{label}.id", audit)
        if material_id:
            if material_id in material_ids:
                audit.fail("CG-CONTRACT-MANIFEST", f"重复素材 ID: {material_id}")
            material_ids.add(material_id)
        if material.get("type") not in {"案例", "操作", "观点", "金句", "踩坑", "取舍", "疑问", "其他"}:
            audit.fail("CG-CONTRACT-MANIFEST", f"{label}.type 非法")
        summary = material.get("summary")
        if not is_nonempty_string(summary):
            audit.fail("CG-CONTRACT-MANIFEST", f"{label}.summary 必须非空")
        validate_source_refs(material.get("source_refs"), f"{label}.source_refs", source_ids, audit)
        block_values = require_list(material.get("source_block_ids"), f"{label}.source_block_ids", audit, nonempty=True)
        valid_block_values: list[str] = []
        for value in block_values:
            block_id = validate_id(value, "block", f"{label}.source_block_ids[]", audit)
            if not block_id:
                continue
            if block_id not in all_block_ids:
                audit.fail("CG-SOURCE-BLOCK-COVERAGE", f"{material_id or label} 引用了不存在的来源块 {block_id}")
            elif block_id not in content_block_ids:
                audit.fail("CG-SOURCE-BLOCK-COVERAGE", f"{material_id or label} 只能映射 content block，实际为 {block_id}")
            else:
                valid_block_values.append(block_id)
                covered_content_blocks.add(block_id)
        if duplicate_items(valid_block_values):
            audit.fail("CG-SOURCE-BLOCK-COVERAGE", f"{material_id or label}.source_block_ids 含重复项")
        disposition = material.get("disposition")
        target = material.get("target_chapter_id")
        term_values = require_list(
            material.get("coverage_terms"),
            f"{label}.coverage_terms",
            audit,
            nonempty=disposition == "include",
        )
        valid_terms: list[str] = []
        for term in term_values:
            if not is_nonempty_string(term) or len(term.strip()) < 2:
                audit.fail("CG-READER-EVIDENCE", f"{material_id or label} 的 coverage_terms 每项至少 2 字符")
                continue
            normalized = term.strip()
            valid_terms.append(normalized)
            if is_nonempty_string(summary) and normalized not in summary:
                audit.fail("CG-READER-EVIDENCE", f"{material_id or label} 的预承诺覆盖词 {normalized!r} 未出现在素材摘要")
        if len(valid_terms) > 5:
            audit.fail("CG-READER-EVIDENCE", f"{material_id or label} 的 coverage_terms 最多 5 项")
        if duplicate_items(valid_terms):
            audit.fail("CG-READER-EVIDENCE", f"{material_id or label} 的 coverage_terms 不得重复")
        if source_root_rebound and valid_block_values:
            bound_source_text = "\n".join(raw_source_block_texts.get(block_id, "") for block_id in valid_block_values)
            normalized_bound_source = normalize_fidelity_text(bound_source_text)
            for term in valid_terms:
                if normalize_fidelity_text(term) not in normalized_bound_source:
                    audit.fail(
                        "CG-CLAIM-FIDELITY",
                        f"{material_id or label} 的覆盖词 {term!r} 未出现在其绑定的原始来源块；不得发明抽象词后回写正文",
                    )
        for block_id in valid_block_values:
            if isinstance(disposition, str):
                block_dispositions[block_id].add(disposition)
        if disposition == "include":
            if len(valid_block_values) > MAX_INCLUDE_BLOCKS_PER_MATERIAL:
                audit.fail(
                    "CG-READER-DEPTH",
                    f"{material_id or label} 合并了 {len(valid_block_values)} 个来源块；include 素材最多 {MAX_INCLUDE_BLOCKS_PER_MATERIAL} 个，应按可复用信息单元拆分",
                )
            required_term_count = max(2, min(5, math.ceil(len(valid_block_values) / 2)))
            if len(valid_terms) < required_term_count:
                audit.fail(
                    "CG-READER-DEPTH",
                    f"{material_id or label} 覆盖 {len(valid_block_values)} 个来源块时至少需要 {required_term_count} 个具体 coverage_terms，实际 {len(valid_terms)} 个",
                )
            if len(valid_terms) < 2:
                audit.fail("CG-READER-EVIDENCE", f"{material_id or label} 为 include 时至少预承诺 2 个 coverage_terms")
            if valid_terms and all(term.casefold() in GENERIC_COVERAGE_TERMS for term in valid_terms):
                audit.fail("CG-READER-EVIDENCE", f"{material_id or label} 的 coverage_terms 不能全是通用词")
            included_materials += 1
            if target not in chapter_ids:
                audit.fail("CG-MATERIAL-TRACE", f"{material_id or label} 指向不存在的章节 {target!r}")
            elif material_id:
                included_blocks_by_chapter[target].update(valid_block_values)
                memberships = [
                    chapter_id
                    for chapter_id, values in chapter_material_membership.items()
                    if material_id in values
                ]
                if memberships != [target]:
                    audit.fail(
                        "CG-MATERIAL-TRACE",
                        f"{material_id} 的章节成员关系应仅为 {target}，实际为 {memberships}",
                    )
            evidence = material.get("reader_evidence")
            if not isinstance(evidence, dict):
                audit.fail("CG-READER-EVIDENCE", f"{material_id or label} 为 include 时必须填写 reader_evidence")
            else:
                checked = check_allowed_keys(evidence, {"quotes"}, set(), f"{label}.reader_evidence", audit)
                quotes = require_list(
                    checked.get("quotes"),
                    f"{label}.reader_evidence.quotes",
                    audit,
                    nonempty=True,
                )
                if len(quotes) > 3:
                    audit.fail("CG-READER-EVIDENCE", f"{material_id or label} 的 reader_evidence.quotes 最多 3 段")
                valid_quotes: list[str] = []
                for quote in quotes:
                    if not is_nonempty_string(quote):
                        audit.fail("CG-READER-EVIDENCE", f"{material_id or label} 的每段 reader_evidence.quotes 必须非空")
                    else:
                        normalized_quote = quote.strip()
                        if len(normalized_quote) < 20:
                            audit.fail("CG-READER-EVIDENCE", f"{material_id or label} 的每段 reader_evidence.quotes 至少 20 字符")
                        valid_quotes.append(normalized_quote)
                evidence_records.append(
                    {
                        "id": material_id,
                        "type": material.get("type"),
                        "target": target,
                        "quotes": valid_quotes,
                        "terms": valid_terms,
                        "source_block_count": len(valid_block_values),
                    }
                )
        elif disposition == "skip":
            if valid_terms:
                audit.fail("CG-READER-EVIDENCE", f"{material_id or label} 为 skip 时 coverage_terms 必须为空数组")
            if target is not None:
                audit.fail("CG-MATERIAL-TRACE", f"{material_id or label} 为 skip 时 target_chapter_id 必须为 null")
            if not is_nonempty_string(material.get("skip_reason")):
                audit.fail("CG-MATERIAL-TRACE", f"{material_id or label} 为 skip 时必须填写 skip_reason")
            if material.get("skip_code") not in SKIP_CODES:
                audit.fail("CG-SOURCE-BLOCK-COVERAGE", f"{material_id or label} 为 skip 时必须填写受控 skip_code")
            if material.get("reader_evidence") is not None:
                audit.fail("CG-READER-EVIDENCE", f"{material_id or label} 为 skip 时 reader_evidence 必须为 null")
            if material_id and any(material_id in values for values in chapter_material_membership.values()):
                audit.fail("CG-MATERIAL-TRACE", f"skip 素材 {material_id} 不得出现在章节 material_ids")
        else:
            audit.fail("CG-CONTRACT-MANIFEST", f"{label}.disposition 必须为 include 或 skip")
    expected_material_ids = {f"MAT-{index:03d}" for index in range(1, len(raw_materials) + 1)}
    if material_ids != expected_material_ids:
        missing = sorted(expected_material_ids - material_ids)
        unexpected = sorted(material_ids - expected_material_ids)
        details: list[str] = []
        if missing:
            details.append(f"缺少 {len(missing)} 个（示例: {', '.join(missing[:5])}）")
        if unexpected:
            details.append(f"越界 {len(unexpected)} 个（示例: {', '.join(unexpected[:5])}）")
        audit.fail(
            "CG-CONTRACT-MANIFEST",
            "materials.id 必须按数组长度从 MAT-001 连续分配；" + "；".join(details),
        )
    for chapter_id, values in chapter_material_membership.items():
        for material_id in values:
            if material_id not in material_ids:
                audit.fail("CG-MATERIAL-TRACE", f"{chapter_id} 引用了不存在的素材 {material_id}")
    uncovered_blocks = sorted(content_block_ids - covered_content_blocks)
    if uncovered_blocks:
        preview = ", ".join(uncovered_blocks[:12])
        suffix = "..." if len(uncovered_blocks) > 12 else ""
        audit.fail("CG-SOURCE-BLOCK-COVERAGE", f"有 {len(uncovered_blocks)} 个 content block 未登记去向: {preview}{suffix}")
    conflicted_blocks = sorted(block_id for block_id, values in block_dispositions.items() if len(values) > 1)
    if conflicted_blocks:
        audit.fail("CG-SOURCE-BLOCK-COVERAGE", f"来源块不得同时 include 与 skip: {', '.join(conflicted_blocks[:12])}")

    image_records: dict[str, dict[str, Any]] = {}
    manifest_image_sequence: list[tuple[str, str, str]] = []
    for index, item in enumerate(require_list(top.get("images"), "images", audit), 1):
        label = f"images[{index}]"
        image = check_allowed_keys(item, {"id", "source_ref", "original_markdown", "body_action", "target_document_id"}, {"reason"}, label, audit)
        image_id = validate_id(image.get("id"), "image", f"{label}.id", audit)
        if image_id:
            if image_id in image_records:
                audit.fail("CG-CONTRACT-MANIFEST", f"重复图片 ID: {image_id}")
            image_records[image_id] = image
        validate_source_refs([image.get("source_ref")], f"{label}.source_ref", source_ids, audit)
        markdown = image.get("original_markdown")
        if not is_nonempty_string(markdown) or "\n" in str(markdown) or extract_images(str(markdown)) != [markdown]:
            audit.fail("CG-CONTRACT-MANIFEST", f"{image_id or label}.original_markdown 必须是单行完整 Markdown 图片引用")
        elif image_id and isinstance(image.get("source_ref"), str):
            manifest_image_sequence.append(
                (
                    image_id,
                    image["source_ref"],
                    hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
                )
            )
        action = image.get("body_action")
        target = image.get("target_document_id")
        if action == "insert":
            if target != "OVERVIEW" and target not in chapter_ids:
                audit.fail("CG-IMAGE-SET", f"{image_id or label} 的插入目标不存在: {target!r}")
            expected_membership = overview_image_ids if target == "OVERVIEW" else chapter_image_membership.get(target, [])
            if image_id and expected_membership.count(image_id) != 1:
                audit.fail("CG-IMAGE-SET", f"{image_id} 未在目标 {target} 的 image_ids 中精确出现一次")
        elif action in {"asset_only", "skip"}:
            if target is not None:
                audit.fail("CG-IMAGE-SET", f"{image_id or label} 为 {action} 时 target_document_id 必须为 null")
            if not is_nonempty_string(image.get("reason")):
                audit.fail("CG-CONTRACT-MANIFEST", f"{image_id or label} 为 {action} 时必须填写 reason")
            all_membership = overview_image_ids + [value for values in chapter_image_membership.values() for value in values]
            if image_id and image_id in all_membership:
                audit.fail("CG-IMAGE-SET", f"{action} 图片 {image_id} 不得进入 reader image_ids")
        else:
            audit.fail("CG-CONTRACT-MANIFEST", f"{label}.body_action 非法")

    expected_image_ids = [f"IMG-{index:03d}" for index in range(1, len(indexed_image_blocks) + 1)]
    actual_image_ids = [item[0] for item in manifest_image_sequence]
    if actual_image_ids != expected_image_ids:
        audit.fail(
            "CG-IMAGE-SOURCE-COVERAGE",
            "images 必须按来源索引中的全部 image block 连续编号并保持原始顺序",
        )
    expected_image_refs = [item[0] for item in indexed_image_blocks]
    actual_image_refs = [item[1] for item in manifest_image_sequence]
    if actual_image_refs != expected_image_refs:
        audit.fail(
            "CG-IMAGE-SOURCE-COVERAGE",
            f"来源索引有 {len(indexed_image_blocks)} 个 image block，manifest 必须逐项且按原始顺序登记；当前登记 {len(manifest_image_sequence)} 项",
        )
    expected_image_hashes = [item[1] for item in indexed_image_blocks]
    actual_image_hashes = [item[2] for item in manifest_image_sequence]
    if actual_image_refs == expected_image_refs and actual_image_hashes != expected_image_hashes:
        audit.fail(
            "CG-IMAGE-SOURCE-COVERAGE",
            "manifest 的 original_markdown 与 source-index 对应 image block 哈希不一致，必须原样保留",
        )

    all_declared_reader_images = overview_image_ids + [value for values in chapter_image_membership.values() for value in values]
    if duplicate_items(all_declared_reader_images):
        audit.fail("CG-IMAGE-SET", "同一 IMG ID 不得分配给多个读者文档")
    for image_id in all_declared_reader_images:
        if image_id not in image_records:
            audit.fail("CG-IMAGE-SET", f"读者文档引用了不存在的图片 ID {image_id}")

    reader_records = [{"id": "OVERVIEW", "file": overview_file, "path": overview_path, "image_ids": overview_image_ids}] + chapter_records
    reader_files: list[str] = []
    reader_texts: dict[str, str] = {}
    reader_prose_chars: dict[str, int] = {}
    reader_image_counts: dict[str, int] = {}
    actual_image_total = 0
    for record in reader_records:
        document_id = record["id"] or "UNKNOWN"
        file_name = record["file"] or "<invalid>"
        text = read_required_text(record["path"], document_id, audit)
        if isinstance(file_name, str):
            reader_files.append(file_name)
        if record["path"] and record["path"].is_file():
            audit.artifact_sha256[document_id] = sha256_file(record["path"])
        if text is None:
            continue
        reader_texts[document_id] = text
        reader_prose_chars[document_id] = visible_prose_char_count(text)
        actual_images = extract_images(text)
        reader_image_counts[document_id] = len(actual_images)
        actual_image_total += len(actual_images)
        expected_markdown: list[str] = []
        for image_id in record["image_ids"]:
            image = image_records.get(image_id)
            if image and isinstance(image.get("original_markdown"), str):
                expected_markdown.append(image["original_markdown"])
        if Counter(actual_images) != Counter(expected_markdown):
            missing = list((Counter(expected_markdown) - Counter(actual_images)).elements())
            extra = list((Counter(actual_images) - Counter(expected_markdown)).elements())
            details = []
            if missing:
                details.append(f"缺少 {len(missing)} 张")
            if extra:
                details.append(f"多出/未声明 {len(extra)} 张")
            audit.fail("CG-IMAGE-SET", f"{file_name} 图片集合不符（{'，'.join(details)}）")
        elif actual_images != expected_markdown:
            audit.fail("CG-IMAGE-ORDER", f"{file_name} 图片出现顺序与 manifest 不一致")
        if SPEAKER_AS_ACTOR_RE.search(text):
            audit.fail("CG-BOOKLIKE-TONE", f"{file_name} 残留讲者/讲师/主讲人作为动作发出者")
        if SOURCE_FRAME_RE.search(text):
            audit.fail("CG-BOOKLIKE-TONE", f"{file_name} 残留课程现场或原文框架词")
        if FILLER_RE.search(text):
            audit.fail("CG-BOOKLIKE-TONE", f"{file_name} 残留明确口语赘词")
        if VISIBLE_TRACE_RE.search(text):
            audit.fail("CG-AUDIT-SEPARATION", f"{file_name} 暴露审计元数据，应移入 manifest/审计文件")
        if BODY_TEMPLATE_MARKER_RE.search(text):
            audit.fail("CG-OUTPUT-COMPLETE", f"{file_name} 残留未替换模板标记")
        if source_root_rebound:
            for match in ACRONYM_EXPANSION_RE.finditer(text):
                expansion = match.group(2)
                if not re.search(r"[A-Za-z]", expansion):
                    continue
                if normalize_fidelity_text(match.group(0)) not in normalized_raw_source:
                    audit.fail(
                        "CG-CLAIM-FIDELITY",
                        f"{file_name} 出现来源中不存在的缩写释义 {match.group(0)!r}；不得自行补全英文全称",
                    )

        image_budget = max(
            MIN_DOCUMENT_IMAGE_BUDGET,
            math.ceil(reader_prose_chars[document_id] / IMAGE_PROSE_BUDGET),
        )
        if len(actual_images) > image_budget:
            audit.fail(
                "CG-IMAGE-DENSITY",
                f"{file_name} 有 {len(actual_images)} 张正文图、{reader_prose_chars[document_id]} 个可见文字，密度上限为 {image_budget} 张；应保留代表图，其余转为 asset_only",
            )

    evidence_signatures: list[str] = []
    for evidence in evidence_records:
        material_id = evidence.get("id") or "<unknown>"
        target = evidence.get("target")
        quotes = evidence.get("quotes") or []
        target_text = reader_texts.get(target, "")
        if not quotes:
            continue
        evidence_signatures.append("\u241e".join(quotes))
        for quote_index, quote in enumerate(quotes, 1):
            if quote not in target_text:
                audit.fail(
                    "CG-READER-EVIDENCE",
                    f"{material_id} 的 reader_evidence.quotes[{quote_index}] 未出现在目标章节 {target}",
                )
        combined_quote = "\n".join(quotes)
        visible_quote = IMAGE_RE.sub("", combined_quote)
        visible_quote = re.sub(r"[#>*_`\-\s]", "", visible_quote)
        block_count = max(1, int(evidence.get("source_block_count") or 1))
        if evidence.get("type") in EXPANDED_MATERIAL_TYPES:
            minimum = max(80, min(240, 35 * block_count))
        else:
            minimum = max(30, min(180, 25 * block_count))
        if len(visible_quote) < minimum:
            audit.fail(
                "CG-READER-EVIDENCE",
                f"{material_id} 的正文证据仅 {len(visible_quote)} 字，{evidence.get('type')}类至少需要 {minimum} 字",
            )
        for term in evidence.get("terms", []):
            if term not in combined_quote:
                audit.fail("CG-READER-EVIDENCE", f"{material_id} 的覆盖词 {term!r} 未出现在 1—3 段证据摘录的合并文本中")
    duplicated_evidence = duplicate_items(evidence_signatures)
    if duplicated_evidence:
        audit.fail("CG-READER-EVIDENCE", f"不同素材不得复用完全相同的正文证据摘录（共 {len(duplicated_evidence)} 组）")

    included_block_ids = set().union(*included_blocks_by_chapter.values()) if included_blocks_by_chapter else set()
    included_source_chars = sum(content_block_char_counts.get(block_id, 0) for block_id in included_block_ids)
    chapter_reader_prose_chars = sum(reader_prose_chars.get(chapter_id, 0) for chapter_id in chapter_ids)
    required_global_prose_chars = math.ceil(included_source_chars * GLOBAL_READER_DEPTH_RATIO)
    if included_source_chars and chapter_reader_prose_chars < required_global_prose_chars:
        audit.fail(
            "CG-READER-DEPTH",
            f"章节可见文字共 {chapter_reader_prose_chars} 字，低于纳入来源 {included_source_chars} 字的 {GLOBAL_READER_DEPTH_RATIO:.0%} 下限（至少 {required_global_prose_chars} 字）",
        )
    chapter_depth_measurements: dict[str, dict[str, int]] = {}
    for chapter_id in sorted(chapter_ids):
        source_chars = sum(
            content_block_char_counts.get(block_id, 0)
            for block_id in included_blocks_by_chapter.get(chapter_id, set())
        )
        prose_chars = reader_prose_chars.get(chapter_id, 0)
        required_chars = math.ceil(source_chars * CHAPTER_READER_DEPTH_RATIO)
        chapter_depth_measurements[chapter_id] = {
            "included-source-chars": source_chars,
            "reader-prose-chars": prose_chars,
            "required-reader-prose-chars": required_chars,
        }
        if source_chars and prose_chars < required_chars:
            audit.fail(
                "CG-READER-DEPTH",
                f"{chapter_id} 可见文字 {prose_chars} 字，低于本章纳入来源 {source_chars} 字的 {CHAPTER_READER_DEPTH_RATIO:.0%} 下限（至少 {required_chars} 字）",
            )

    total_reader_prose_chars = sum(reader_prose_chars.values())
    global_image_budget = max(
        MIN_DOCUMENT_IMAGE_BUDGET,
        math.ceil(total_reader_prose_chars / IMAGE_PROSE_BUDGET),
    )
    if actual_image_total > global_image_budget:
        audit.fail(
            "CG-IMAGE-DENSITY",
            f"全部读者文档有 {actual_image_total} 张正文图、{total_reader_prose_chars} 个可见文字，密度上限为 {global_image_budget} 张",
        )

    minimum_reader_images = 0
    if len(indexed_image_blocks) >= RICH_SOURCE_IMAGE_THRESHOLD:
        minimum_reader_images = min(
            len(reader_records),
            math.ceil(len(indexed_image_blocks) / SOURCE_IMAGES_PER_REQUIRED_READER_IMAGE),
        )
    if actual_image_total < minimum_reader_images:
        audit.fail(
            "CG-IMAGE-SELECTION",
            f"来源含 {len(indexed_image_blocks)} 张图片，至少应从方法框架、关键界面、转折或结果中筛选 {minimum_reader_images} 张进入读者正文；实际 {actual_image_total} 张",
        )

    expected_files = {name for name in reader_files if isinstance(name, str)}
    actual_numbered = {path.name for path in root.iterdir() if path.is_file() and NUMBERED_MD_RE.fullmatch(path.name) and path.name[:2] not in {"98", "99"}}
    extras = sorted(actual_numbered - expected_files)
    if extras:
        audit.fail("CG-OUTPUT-COMPLETE", f"存在 manifest 未声明的读者文件: {', '.join(extras)}")

    audit_files = top.get("audit_files", {})
    if audit_files is not None:
        audit_files = check_allowed_keys(audit_files, set(), {"outline", "image_assets", "material_index"}, "audit_files", audit)
        audit_path_values = [value for value in audit_files.values() if isinstance(value, str)]
        if duplicate_items(audit_path_values):
            audit.fail("CG-CONTRACT-MANIFEST", "audit_files 不得把多个角色指向同一文件")
        for key, raw_path in audit_files.items():
            if raw_path in expected_files:
                audit.fail("CG-AUDIT-SEPARATION", f"audit_files.{key} 不得复用读者文件 {raw_path}")
            path = safe_relative_path(root, raw_path, f"audit_files.{key}", audit)
            text = read_required_text(path, f"audit_files.{key}", audit)
            if text is not None and path:
                audit.artifact_sha256[f"audit:{key}"] = sha256_file(path)

    audit.measurements = {
        "CG-CONTRACT-MANIFEST": {"schema-version": top.get("schema_version")},
        "CG-OUTPUT-COMPLETE": {
            "reader-file-count": len(reader_records),
            "chapter-count": len(chapter_records),
            "max-chapters": max_chapters,
        },
        "CG-MATERIAL-TRACE": {"included-material-count": included_materials},
        "CG-SOURCE-BLOCK-COVERAGE": {
            "content-block-count": len(content_block_ids),
            "covered-content-block-count": len(covered_content_blocks),
        },
        "CG-READER-EVIDENCE": {"evidence-count": len(evidence_records)},
        "CG-CLAIM-FIDELITY": {
            "source-root-rebound": source_root_rebound,
            "source-block-text-count": len(raw_source_block_texts),
        },
        "CG-READER-DEPTH": {
            "included-source-char-count": included_source_chars,
            "chapter-reader-prose-char-count": chapter_reader_prose_chars,
            "required-chapter-reader-prose-char-count": required_global_prose_chars,
            "chapter-depth": chapter_depth_measurements,
        },
        "CG-IMAGE-SOURCE-COVERAGE": {
            "source-image-block-count": len(indexed_image_blocks),
            "manifest-image-count": len(manifest_image_sequence),
        },
        "CG-IMAGE-SET": {"declared-reader-image-count": len(all_declared_reader_images), "actual-reader-image-count": actual_image_total},
        "CG-IMAGE-ORDER": {"ordered-document-count": len(reader_records)},
        "CG-IMAGE-SELECTION": {
            "source-image-block-count": len(indexed_image_blocks),
            "minimum-reader-image-count": minimum_reader_images,
            "actual-reader-image-count": actual_image_total,
        },
        "CG-IMAGE-DENSITY": {
            "reader-prose-char-count": total_reader_prose_chars,
            "actual-reader-image-count": actual_image_total,
            "global-image-budget": global_image_budget,
            "document-image-counts": reader_image_counts,
        },
        "CG-BOOKLIKE-TONE": {"checked-document-count": len(reader_records)},
        "CG-AUDIT-SEPARATION": {"checked-document-count": len(reader_records)},
    }
    audit.observables = {
        "reader-files": reader_files,
        "chapter-ids": sorted(chapter_ids),
        "material-ids": sorted(material_ids),
        "source-block-ids": sorted(content_block_ids),
        "image-ids": sorted(image_records),
    }
    audit.warn("需人工复核：覆盖词与缩写门禁只拦截可确定的来源外补写，不证明全部事实忠实度、跨章一致性或图片视觉价值")
    return audit


def emit_result(audit: Audit, root: Path) -> int:
    print("========== course-generator v2.9.4 验收 ==========")
    print(f"目录: {root}")
    for constraint_id in ALL_CONSTRAINTS:
        messages = audit.failures.get(constraint_id)
        if messages:
            print(f"  ❌ {constraint_id}")
            for message in messages:
                print(f"     - {message}")
        else:
            print(f"  ✅ {constraint_id}")
    for warning in audit.warnings:
        print(f"  ⚠️  {warning}")
    status = "FAIL" if audit.failed_ids else "PASS"
    result = {
        "status": status,
        "passed_constraint_ids": audit.passed_ids,
        "failed_constraint_ids": audit.failed_ids,
        "artifact_sha256": audit.artifact_sha256,
        "measurements": audit.measurements,
        "observables": audit.observables,
        "manual_checks": audit.warnings,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 1 if audit.failed_ids else 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按 source-index.json 与 course-manifest.json 验收 Course Generator v2.9.4 课程目录")
    parser.add_argument("course_dir", help="课程输出目录")
    parser.add_argument("--manifest", default="course-manifest.json", help="相对课程目录的 manifest 路径（默认: course-manifest.json）")
    parser.add_argument("--source-root", help="可选：索引时使用的单个来源文件或来源根目录；提供时重新枚举并校验完整输入范围")
    parser.add_argument(
        "--max-chapters",
        type=int,
        default=DEFAULT_MAX_CHAPTERS,
        help=f"章节上限（默认: {DEFAULT_MAX_CHAPTERS}；仅在用户明确要求更多章节时提高）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = Path(args.course_dir).expanduser().resolve()
    if not root.is_dir():
        print(f"❌ 课程目录不存在: {root}")
        print(json.dumps({"status": "ERROR", "passed_constraint_ids": [], "failed_constraint_ids": ["CG-VERIFIER-RUNTIME"], "artifact_sha256": {}, "measurements": {}, "observables": {}, "manual_checks": []}, ensure_ascii=False, sort_keys=True))
        return 2
    try:
        source_root = Path(args.source_root).expanduser().resolve() if args.source_root else None
        return emit_result(verify_course(root, args.manifest, source_root, args.max_chapters), root)
    except Exception as exc:  # fail closed on unexpected verifier defects
        print(f"❌ 验收器异常（按失败处理）: {type(exc).__name__}: {exc}")
        print(json.dumps({"status": "ERROR", "passed_constraint_ids": [], "failed_constraint_ids": ["CG-VERIFIER-RUNTIME"], "artifact_sha256": {}, "measurements": {}, "observables": {}, "manual_checks": []}, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
