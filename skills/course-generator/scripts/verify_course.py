#!/usr/bin/env python3
"""Verify a Course Generator v2.8 course directory against its manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any


ALL_CONSTRAINTS = (
    "CG-CONTRACT-MANIFEST",
    "CG-OUTPUT-COMPLETE",
    "CG-MATERIAL-TRACE",
    "CG-IMAGE-SET",
    "CG-IMAGE-ORDER",
    "CG-BOOKLIKE-TONE",
    "CG-AUDIT-SEPARATION",
)

ID_PATTERNS = {
    "source": re.compile(r"^SRC-[0-9]{3,}$"),
    "chapter": re.compile(r"^CH-[0-9]{2,3}$"),
    "material": re.compile(r"^MAT-[0-9]{3,}$"),
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_images(text: str) -> list[str]:
    return IMAGE_RE.findall(text)


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


def verify_course(root: Path, manifest_name: str = "course-manifest.json") -> Audit:
    audit = Audit()
    manifest, _ = load_manifest(root, manifest_name, audit)
    if not manifest:
        if "CG-CONTRACT-MANIFEST" not in audit.failures:
            audit.fail("CG-CONTRACT-MANIFEST", "manifest 不得是空对象")
        for constraint_id in ALL_CONSTRAINTS[1:]:
            audit.fail(constraint_id, "manifest 不可用，无法执行该项检查")
        return audit

    top = check_allowed_keys(
        manifest,
        {"schema_version", "generator_version", "course", "sources", "overview", "chapters", "materials", "images"},
        {"audit_files"},
        "manifest",
        audit,
    )
    if top.get("schema_version") != "1.0":
        audit.fail("CG-CONTRACT-MANIFEST", "schema_version 必须为 1.0")
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

    source_ids: set[str] = set()
    source_paths: list[str] = []
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
    if duplicate_items(source_paths):
        audit.fail("CG-CONTRACT-MANIFEST", "sources.path 不得重复")

    overview = check_allowed_keys(top.get("overview"), {"file", "image_ids"}, set(), "overview", audit)
    overview_file = overview.get("file")
    if not isinstance(overview_file, str) or not OVERVIEW_FILE_RE.fullmatch(overview_file):
        audit.fail("CG-CONTRACT-MANIFEST", "overview.file 必须匹配 00 [名称].md")
    overview_path = safe_relative_path(root, overview_file, "overview.file", audit)
    overview_image_ids = require_list(overview.get("image_ids"), "overview.image_ids", audit)
    overview_image_ids = [item for item in overview_image_ids if validate_id(item, "image", "overview.image_ids[]", audit)]
    if duplicate_items(overview_image_ids):
        audit.fail("CG-CONTRACT-MANIFEST", "overview.image_ids 不得重复")

    chapter_ids: set[str] = set()
    chapter_files: set[str] = set()
    chapter_records: list[dict[str, Any]] = []
    chapter_material_membership: dict[str, list[str]] = defaultdict(list)
    chapter_image_membership: dict[str, list[str]] = defaultdict(list)
    for index, item in enumerate(require_list(top.get("chapters"), "chapters", audit, nonempty=True), 1):
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
        if not is_nonempty_string(chapter.get("title")):
            audit.fail("CG-CONTRACT-MANIFEST", f"{label}.title 必须非空")
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
    for index, item in enumerate(require_list(top.get("materials"), "materials", audit, nonempty=True), 1):
        label = f"materials[{index}]"
        material = check_allowed_keys(item, {"id", "type", "summary", "source_refs", "disposition", "target_chapter_id"}, {"skip_reason"}, label, audit)
        material_id = validate_id(material.get("id"), "material", f"{label}.id", audit)
        if material_id:
            if material_id in material_ids:
                audit.fail("CG-CONTRACT-MANIFEST", f"重复素材 ID: {material_id}")
            material_ids.add(material_id)
        if material.get("type") not in {"案例", "操作", "观点", "金句", "踩坑", "取舍", "疑问", "其他"}:
            audit.fail("CG-CONTRACT-MANIFEST", f"{label}.type 非法")
        if not is_nonempty_string(material.get("summary")):
            audit.fail("CG-CONTRACT-MANIFEST", f"{label}.summary 必须非空")
        validate_source_refs(material.get("source_refs"), f"{label}.source_refs", source_ids, audit)
        disposition = material.get("disposition")
        target = material.get("target_chapter_id")
        if disposition == "include":
            included_materials += 1
            if target not in chapter_ids:
                audit.fail("CG-MATERIAL-TRACE", f"{material_id or label} 指向不存在的章节 {target!r}")
            elif material_id:
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
        elif disposition == "skip":
            if target is not None:
                audit.fail("CG-MATERIAL-TRACE", f"{material_id or label} 为 skip 时 target_chapter_id 必须为 null")
            if not is_nonempty_string(material.get("skip_reason")):
                audit.fail("CG-MATERIAL-TRACE", f"{material_id or label} 为 skip 时必须填写 skip_reason")
            if material_id and any(material_id in values for values in chapter_material_membership.values()):
                audit.fail("CG-MATERIAL-TRACE", f"skip 素材 {material_id} 不得出现在章节 material_ids")
        else:
            audit.fail("CG-CONTRACT-MANIFEST", f"{label}.disposition 必须为 include 或 skip")
    for chapter_id, values in chapter_material_membership.items():
        for material_id in values:
            if material_id not in material_ids:
                audit.fail("CG-MATERIAL-TRACE", f"{chapter_id} 引用了不存在的素材 {material_id}")

    image_records: dict[str, dict[str, Any]] = {}
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

    all_declared_reader_images = overview_image_ids + [value for values in chapter_image_membership.values() for value in values]
    if duplicate_items(all_declared_reader_images):
        audit.fail("CG-IMAGE-SET", "同一 IMG ID 不得分配给多个读者文档")
    for image_id in all_declared_reader_images:
        if image_id not in image_records:
            audit.fail("CG-IMAGE-SET", f"读者文档引用了不存在的图片 ID {image_id}")

    reader_records = [{"id": "OVERVIEW", "file": overview_file, "path": overview_path, "image_ids": overview_image_ids}] + chapter_records
    reader_files: list[str] = []
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
        actual_images = extract_images(text)
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
        "CG-OUTPUT-COMPLETE": {"reader-file-count": len(reader_records)},
        "CG-MATERIAL-TRACE": {"included-material-count": included_materials},
        "CG-IMAGE-SET": {"declared-reader-image-count": len(all_declared_reader_images), "actual-reader-image-count": actual_image_total},
        "CG-IMAGE-ORDER": {"ordered-document-count": len(reader_records)},
        "CG-BOOKLIKE-TONE": {"checked-document-count": len(reader_records)},
        "CG-AUDIT-SEPARATION": {"checked-document-count": len(reader_records)},
    }
    audit.observables = {"reader-files": reader_files, "chapter-ids": sorted(chapter_ids), "material-ids": sorted(material_ids), "image-ids": sorted(image_records)}
    audit.warn("需人工复核：素材展开充分性、原文溯源、跨章一致性与图片语义价值")
    return audit


def emit_result(audit: Audit, root: Path) -> int:
    print("========== course-generator v2.8 验收 ==========")
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
    parser = argparse.ArgumentParser(description="按 course-manifest.json 验收 Course Generator v2.8 课程目录")
    parser.add_argument("course_dir", help="课程输出目录")
    parser.add_argument("--manifest", default="course-manifest.json", help="相对课程目录的 manifest 路径（默认: course-manifest.json）")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = Path(args.course_dir).expanduser().resolve()
    if not root.is_dir():
        print(f"❌ 课程目录不存在: {root}")
        print(json.dumps({"status": "ERROR", "passed_constraint_ids": [], "failed_constraint_ids": ["CG-VERIFIER-RUNTIME"], "artifact_sha256": {}, "measurements": {}, "observables": {}, "manual_checks": []}, ensure_ascii=False, sort_keys=True))
        return 2
    try:
        return emit_result(verify_course(root, args.manifest), root)
    except Exception as exc:  # fail closed on unexpected verifier defects
        print(f"❌ 验收器异常（按失败处理）: {type(exc).__name__}: {exc}")
        print(json.dumps({"status": "ERROR", "passed_constraint_ids": [], "failed_constraint_ids": ["CG-VERIFIER-RUNTIME"], "artifact_sha256": {}, "measurements": {}, "observables": {}, "manual_checks": []}, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
