#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
法律材料初始扫描与编目脚本

能力边界：
1. 扫描目录或单文件输入
2. 识别常见材料类型
3. 尝试解压常见压缩包并建立父子来源关系
4. 将 Markdown 清单写入源材料目录，将 JSON 元数据写入源材料旁的运行归档
5. 将解压出的真实材料写入独立工作目录，不写入 Skill 包或元数据归档

本脚本不负责 OCR、转录、正文抽取，只负责初始编目层。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import subprocess
import sys
import sys as _chat_html_sys
import tarfile
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Optional

if str(Path(__file__).resolve().parent) not in _chat_html_sys.path:
    _chat_html_sys.path.insert(0, str(Path(__file__).resolve().parent))

from chat_html_extract import (  # noqa: E402
    recognize_chat_html as _chat_html_recognize,
    extract_external_resources as _chat_html_extract,
    download_resource as _chat_html_download,
)


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_VERSION = "0.17.0"
MAX_ARCHIVE_MEMBERS = 10_000
MAX_ARCHIVE_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024
REFERENCE_LEVELS = ("A", "B", "C", "D")
REFERENCE_ORDER = {level: index for index, level in enumerate(REFERENCE_LEVELS)}
MATERIAL_SET_DEFINITIONS = {
    "文档材料": ("set_documents", "文档材料组", "共同读取合同、说明、文书、证书等文档材料。"),
    "图片截图": ("set_images", "图片截图组", "共同读取图片、截图、拍照件和扫描图片。"),
    "聊天沟通": ("set_communications", "聊天沟通组", "共同读取聊天记录、沟通导出和短信材料。"),
    "音视频": ("set_media", "音视频组", "共同读取音频、视频、录屏及其转写结果。"),
    "网页链接": ("set_web", "网页链接组", "共同读取网页、链接文件和网页快照。"),
    "表格清单": ("set_tables", "表格清单组", "共同读取表格、清单和结构化导出。"),
    "压缩包/导出包": ("set_containers", "压缩包与导出包组", "共同读取压缩包、导出包及其内部来源链。"),
    "待确认": ("set_review", "待人工复核组", "集中复核无法自动识别或需要人工确认的材料。"),
}

ARCHIVE_EXTENSIONS = {
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".tar.gz",
    ".tgz",
    ".tar.bz2",
    ".tbz2",
    ".tar.xz",
    ".txz",
}
ARCHIVE_SUFFIX_GROUPS = [
    (".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz"),
    (".zip", ".rar", ".7z", ".tar"),
]
AI_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".amr"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".wmv", ".flv", ".webm", ".m4v"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".bmp", ".tiff", ".tif", ".webp", ".gif"}
PDF_EXTENSIONS = {".pdf"}
WORD_EXTENSIONS = {".doc", ".docx", ".wps", ".odt"}
SPREADSHEET_EXTENSIONS = {".xls", ".xlsx", ".csv", ".numbers"}
PRESENTATION_EXTENSIONS = {".ppt", ".pptx", ".key"}
EMAIL_EXTENSIONS = {".eml", ".msg", ".mbox"}
TEXT_EXTENSIONS = {".md", ".txt", ".rtf", ".text"}
STRUCTURED_EXTENSIONS = {".json", ".xml", ".yaml", ".yml"}
SHORTCUT_EXTENSIONS = {".url", ".webloc"}
HTML_EXTENSIONS = {".html", ".htm"}

GENERATED_SOURCE_FILES = {
    "材料清单.md",
    "材料说明.md",
    "待人工复核.md",
    "materials_manifest.json",
    "run_meta.json",
}
GENERATED_SOURCE_DIRS = {"processed", "organized", "整理输出"}

CHAT_KEYWORDS = ("聊天", "微信", "weixin", "wechat", "message", "chat", "飞书", "lark", "短信", "msg")
SCREENSHOT_KEYWORDS = ("截图", "screen", "shot", "聊天", "微信", "weixin", "wechat")


@dataclass
class MaterialRecord:
    material_id: str
    parent_material_id: Optional[str]
    display_code: str
    reference_level: str
    reference_score: float
    reference_basis: Optional[str]
    scan_order: int
    legacy_ids: list[str]
    material_key: Optional[str]
    material_set_id: str
    material_set_name: str
    variant_kind: str
    primary_variant_id: str
    primary_readable_variant_id: Optional[str]
    readability_status: str
    processing_need: str
    original_name: str
    display_path: str
    absolute_path: str
    material_type: str
    file_extension: str
    is_container: bool
    needs_preprocess: bool
    processing_hint: str
    status: str
    size_bytes: int
    extracted_from_archive: bool
    note: str
    fingerprint: Optional[str]
    source_chain: list[str]
    lifecycle_status: str = "active"
    content_status: str = "pending"
    ocr_output_path: Optional[str] = None
    ocr_status: Optional[str] = "pending"
    transcript_output_path: Optional[str] = None
    annotation_summary: Optional[str] = None
    annotation_keywords: Optional[list[str]] = None
    annotation_case_relevance: Optional[str] = None
    category: Optional[str] = None
    suggested_name: Optional[str] = None
    organized_path: Optional[str] = None
    naming_basis: Optional[str] = None
    confirmation_status: str = "待处理"
    needs_human_review: bool = False
    review_reasons: list[str] | None = None
    confidence: Optional[float] = None
    extra_json: dict = field(default_factory=dict)


def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def safe_name(value: str, max_len: int = 60) -> str:
    cleaned = "".join(
        ch
        if ch.isalnum() or ch in ("-", "_", " ", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十")
        else "_"
        for ch in value
    )
    cleaned = "_".join(part for part in cleaned.replace(" ", "_").split("_") if part)
    if not cleaned:
        cleaned = "material"
    return cleaned[:max_len]


def build_archive_subdir(source: Path, archive_root: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = safe_name(source.stem or source.name, max_len=48)
    candidate = archive_root / f"{stamp}_{base_name}"
    index = 2
    while candidate.exists():
        candidate = archive_root / f"{stamp}_{base_name}_{index}"
        index += 1
    return candidate


def default_runtime_root(source: Path) -> Path:
    """返回源材料旁的隐藏运行目录，确保运行产物不写入 Skill 包。"""
    source_name = source.stem if source.is_file() else source.name
    return source.parent / ".legal-material-organizer" / safe_name(source_name, max_len=48)


def combined_suffix(path: Path) -> str:
    suffixes = "".join(path.suffixes).lower()
    for group in ARCHIVE_SUFFIX_GROUPS:
        for suffix in group:
            if suffixes.endswith(suffix):
                return suffix
    return path.suffix.lower()


def looks_like_chat(name_lower: str) -> bool:
    return any(token in name_lower for token in CHAT_KEYWORDS)


def looks_like_screenshot(name_lower: str) -> bool:
    return any(token in name_lower for token in SCREENSHOT_KEYWORDS)


def classify_material(path: Path) -> tuple[str, bool, str, bool, str]:
    suffix = combined_suffix(path)
    name_lower = path.name.lower()

    if suffix in ARCHIVE_EXTENSIONS:
        return "压缩包", True, "先解压，再建立父子来源关系", True, "容器材料，建议先拆包"
    if suffix in AI_AUDIO_EXTENSIONS:
        return "音频", True, "转录为 Markdown，必要时说话人分离", False, "音频材料，建议转录"
    if suffix in VIDEO_EXTENSIONS:
        if "screen" in name_lower or "录屏" in name_lower:
            return "录屏视频", True, "转录音轨并补关键画面节点", False, "录屏材料，建议结合画面摘要"
        return "视频", True, "转录音轨，必要时补画面摘要", False, "视频材料，建议先转录"
    if suffix in IMAGE_EXTENSIONS:
        if looks_like_screenshot(name_lower):
            return "图片/截图", True, "OCR 或图像理解", False, "截图材料，建议提取文字与场景"
        return "图片/照片", True, "OCR 或图像理解", False, "图片材料，建议提取文字与场景"
    if suffix in PDF_EXTENSIONS:
        return "PDF", True, "文本型直接读取，扫描件先 OCR", False, "PDF 材料，需判断是否为扫描件"
    if suffix in WORD_EXTENSIONS:
        return "Word/WPS 文档", True, "提取正文、结构和落款信息", False, "办公文档，建议转为可读文本"
    if suffix in SPREADSHEET_EXTENSIONS:
        return "表格/清单", True, "提取列名、工作表与关键字段", False, "表格材料，注意多工作表"
    if suffix in PRESENTATION_EXTENSIONS:
        return "演示文稿", True, "提取页标题、图表说明与关键主张", False, "演示材料，建议摘录页面结构"
    if suffix in EMAIL_EXTENSIONS:
        return "邮件材料", True, "提取邮件头、正文和附件关系", False, "邮件材料，建议建立往来链"
    if suffix in SHORTCUT_EXTENSIONS:
        return "网页链接文件", True, "读取链接地址并记录来源", False, "链接文件，建议补正文与截图"
    if suffix in HTML_EXTENSIONS:
        if looks_like_chat(name_lower):
            return "聊天导出", True, "识别聊天对象、导出范围和附件结构，用于命名和归类", False, "聊天导出文件，建议生成命名依据"
        return "网页快照/HTML", True, "提取页面标题、来源和主题，用于命名和归类", False, "HTML 材料，建议区分网页正文与导出页面"
    if suffix in TEXT_EXTENSIONS:
        return "文本说明", False, "读取标题和首段，用于命名和归类", False, "文本材料，可直接读取"
    if suffix in STRUCTURED_EXTENSIONS:
        if looks_like_chat(name_lower):
            return "聊天导出", True, "识别字段、聊天对象和导出来源，用于命名和归类", False, "结构化聊天导出，建议生成命名依据"
        return "结构化导出", False, "识别字段含义和导出来源，用于命名和归类", False, "结构化数据，可直接读取"

    return "其他文件", False, "人工判断用途", False, "未识别材料类型，需人工判断"


def general_category(material_type: str) -> str:
    if material_type == "压缩包":
        return "压缩包/导出包"
    if material_type in {"音频", "视频", "录屏视频"}:
        return "音视频"
    if material_type in {"图片/截图", "图片/照片"}:
        return "图片截图"
    if material_type in {"聊天导出"}:
        return "聊天沟通"
    if material_type in {"网页链接文件", "网页快照/HTML"}:
        return "网页链接"
    if material_type in {"表格/清单", "结构化导出"}:
        return "表格清单"
    if material_type == "其他文件":
        return "待确认"
    return "文档材料"


def processing_need_for(material_type: str, needs_preprocess: bool) -> str:
    if not needs_preprocess:
        return "none"
    if material_type == "压缩包":
        return "need_extract"
    if material_type in {"音频", "视频", "录屏视频"}:
        return "need_asr"
    if material_type in {"图片/截图", "图片/照片", "PDF"}:
        return "need_ocr_or_visual"
    if material_type in {"Word/WPS 文档", "演示文稿"}:
        return "need_text_extract"
    if material_type in {"网页链接文件", "网页快照/HTML"}:
        return "need_web_capture"
    if material_type == "其他文件":
        return "need_review"
    return "need_text_extract"


def readability_status_for(material_type: str, needs_preprocess: bool) -> str:
    if not needs_preprocess:
        return "readable"
    if material_type == "压缩包":
        return "not_applicable"
    return "unknown"


def material_set_for_category(category: str) -> tuple[str, str, str]:
    return MATERIAL_SET_DEFINITIONS.get(category, MATERIAL_SET_DEFINITIONS["文档材料"])


def variant_id_for(material_id: str, kind: str = "original") -> str:
    return f"variant_{material_id.replace('-', '_')}_{kind}"


def is_hidden(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts if part not in ("", path.anchor))


def is_relative_to_path(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def ensure_within(base_dir: Path, target: Path) -> None:
    try:
        target.resolve().relative_to(base_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"检测到危险归档路径: {target}") from exc


def validate_archive_member_name(member_name: str) -> None:
    member_path = PurePosixPath(member_name)
    if member_path.is_absolute() or any(part in {"", ".."} for part in member_path.parts):
        raise ValueError(f"检测到危险归档路径: {member_name}")


def is_zip_symlink(member: zipfile.ZipInfo) -> bool:
    mode = (member.external_attr >> 16) & 0o170000
    return mode == stat.S_IFLNK


def safe_extract_zip(zip_path: Path, target_dir: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        members = zf.infolist()
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise ValueError(f"压缩包文件数超过限制: {len(members)} > {MAX_ARCHIVE_MEMBERS}")
        expanded_bytes = sum(member.file_size for member in members if not member.is_dir())
        if expanded_bytes > MAX_ARCHIVE_EXPANDED_BYTES:
            raise ValueError(
                f"压缩包展开体积超过限制: {expanded_bytes} > {MAX_ARCHIVE_EXPANDED_BYTES}"
            )
        for member in members:
            validate_archive_member_name(member.filename)
            if is_zip_symlink(member):
                raise ValueError(f"拒绝解压 zip 符号链接: {member.filename}")
            member_target = target_dir / member.filename
            ensure_within(target_dir, member_target)
            zf.extract(member, target_dir)


def safe_extract_tar(tar_path: Path, target_dir: Path) -> None:
    with tarfile.open(tar_path) as tf:
        members = tf.getmembers()
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise ValueError(f"压缩包文件数超过限制: {len(members)} > {MAX_ARCHIVE_MEMBERS}")
        expanded_bytes = sum(member.size for member in members if member.isfile())
        if expanded_bytes > MAX_ARCHIVE_EXPANDED_BYTES:
            raise ValueError(
                f"压缩包展开体积超过限制: {expanded_bytes} > {MAX_ARCHIVE_EXPANDED_BYTES}"
            )
        for member in members:
            validate_archive_member_name(member.name)
            if member.issym() or member.islnk() or member.isdev():
                raise ValueError(f"拒绝解压 tar 特殊文件: {member.name}")
            member_target = target_dir / member.name
            ensure_within(target_dir, member_target)
        tf.extractall(target_dir)


def extract_with_binary(binary: str, archive_path: Path, target_dir: Path) -> None:
    if binary == "7z":
        cmd = ["7z", "x", "-y", f"-o{target_dir}", str(archive_path)]
    else:
        cmd = ["unar", "-quiet", "-force-overwrite", "-output-directory", str(target_dir), str(archive_path)]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def safe_rmtree(target: Path, allowed_root: Path) -> None:
    ensure_within(allowed_root, target)
    if target.exists():
        shutil.rmtree(target)


def file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def previous_key(record: dict) -> tuple[str, Optional[str]]:
    return str(record.get("display_path", "")), record.get("fingerprint")


def material_number(material_id: str) -> int:
    normalized = normalize_material_id(material_id)
    try:
        return int(normalized.split("-", 1)[1])
    except (IndexError, ValueError):
        return 0


def normalize_reference_level(value: object) -> str:
    level = str(value or "").strip().upper()
    return level if level in REFERENCE_ORDER else "D"


def reference_level_from_legacy_id(material_id: str) -> str:
    try:
        level = material_id.split("-", 1)[0].upper()
        if level in REFERENCE_ORDER:
            return level
    except IndexError:
        pass
    return "D"


def normalize_material_id(material_id: object) -> str:
    raw = str(material_id or "").strip()
    if "-" in raw:
        prefix, number = raw.split("-", 1)
        if prefix.upper() in {"M", *REFERENCE_LEVELS}:
            try:
                return f"M-{int(number):06d}"
            except ValueError:
                pass
    if raw.startswith("M") and raw[1:].isdigit():
        return f"M-{int(raw[1:]):06d}"
    return raw


def normalize_previous_record(record: dict) -> dict:
    normalized = dict(record)
    raw_id = str(record.get("material_id", ""))
    material_id = normalize_material_id(raw_id)
    legacy_ids = list(record.get("legacy_ids") or [])
    if raw_id and raw_id != material_id and raw_id not in legacy_ids:
        legacy_ids.append(raw_id)
    normalized["material_id"] = material_id
    normalized["legacy_ids"] = legacy_ids
    if record.get("parent_material_id"):
        normalized["parent_material_id"] = normalize_material_id(record.get("parent_material_id"))
    level = record.get("reference_level", record.get("reference_density"))
    if not level:
        level = reference_level_from_legacy_id(raw_id)
    normalized["reference_level"] = normalize_reference_level(level)
    normalized["reference_score"] = float(record.get("reference_score", 0) or 0)
    normalized.setdefault("display_code", "")
    normalized.setdefault("reference_basis", None)
    normalized.setdefault("scan_order", material_number(material_id))
    normalized.setdefault("material_key", f"sha256:{record.get('fingerprint')}" if record.get("fingerprint") else None)
    category = str(record.get("category") or "文档材料")
    set_id, set_name, _ = material_set_for_category(category)
    normalized.setdefault("material_set_id", set_id)
    normalized.setdefault("material_set_name", set_name)
    normalized.setdefault("variant_kind", "original")
    normalized.setdefault("primary_variant_id", variant_id_for(material_id, "original"))
    normalized.setdefault(
        "primary_readable_variant_id",
        variant_id_for(material_id, "original") if record.get("readability_status") == "readable" else None,
    )
    normalized.setdefault("readability_status", record.get("readability_status", "unknown"))
    normalized.setdefault("processing_need", record.get("processing_need", "none"))
    normalized.setdefault("extra_json", {})
    return normalized


def find_latest_manifest(archive_root: Path, source: Path) -> Optional[dict]:
    if not archive_root.exists():
        return None
    source_value = str(source.resolve())
    for candidate in sorted((path for path in archive_root.iterdir() if path.is_dir()), reverse=True):
        manifest_path = candidate / "materials_manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if manifest.get("source") == source_value:
            return manifest
    return None


class MaterialScanner:
    def __init__(
        self,
        source: Path,
        markdown_output_dir: Path,
        archive_dir: Path,
        work_dir: Path,
        previous_manifest: Optional[dict],
        expand_archives: bool,
        allow_external_extractor: bool,
        max_archive_depth: int,
        include_hidden: bool,
        write_md: bool,
    ) -> None:
        self.source = source.resolve()
        self.markdown_output_dir = markdown_output_dir.resolve()
        self.archive_dir = archive_dir.resolve()
        self.work_dir = work_dir.resolve()
        self.expand_archives = expand_archives
        self.allow_external_extractor = allow_external_extractor
        self.max_archive_depth = max_archive_depth
        self.include_hidden = include_hidden
        self.write_md = write_md
        self.records: list[MaterialRecord] = []
        self.previous_manifest = previous_manifest or {}
        previous_records = [normalize_previous_record(record) for record in self.previous_manifest.get("materials", [])]
        self.previous_by_key = {
            previous_key(record): record
            for record in previous_records
            if record.get("lifecycle_status", "active") != "missing" and record.get("fingerprint")
        }
        self.previous_records = previous_records
        self.previous_variants = list(self.previous_manifest.get("variants", []))
        self.previous_processing_runs = list(self.previous_manifest.get("processing_runs", []))
        self.previous_follow_up_candidates = {
            str(item.get("candidate_id")): dict(item)
            for item in self.previous_manifest.get("follow_up_candidates", [])
            if item.get("candidate_id")
        }
        self.used_previous_ids: set[str] = set()
        self._next_id = max((material_number(str(record.get("material_id", ""))) for record in previous_records), default=0) + 1
        self._next_scan_order = max((int(record.get("scan_order") or 0) for record in previous_records), default=0) + 1
        self.processing_runs: list[dict] = []
        self._processing_run_index = 1

        self.extracted_dir = self.work_dir / "extracted_containers"

        self.archive_dir.mkdir(parents=True, exist_ok=True)
        if self.expand_archives:
            self.work_dir.mkdir(parents=True, exist_ok=True)
            if self.extracted_dir.exists():
                safe_rmtree(self.extracted_dir, self.work_dir)
            self.extracted_dir.mkdir(parents=True, exist_ok=True)
        if self.write_md:
            self.markdown_output_dir.mkdir(parents=True, exist_ok=True)

        # chat-html 子路径 flags；由 main() 在构造后赋值
        self.chat_html_dry_run: bool = False
        self.chat_html_download: bool = False
        self.chat_html_no_fail: bool = False
        self.chat_html_resource_dir: Optional[Path] = None
        self.chat_html_chat_meta: dict = {}

    def new_material_id(self) -> str:
        material_id = f"M-{self._next_id:06d}"
        self._next_id += 1
        return material_id

    def next_scan_order(self) -> int:
        scan_order = self._next_scan_order
        self._next_scan_order += 1
        return scan_order

    def resolve_material_id(self, display_path: str, fingerprint: str) -> tuple[str, Optional[dict]]:
        previous = self.previous_by_key.get((display_path, fingerprint))
        if previous:
            material_id = normalize_material_id(previous["material_id"])
            self.used_previous_ids.add(material_id)
            return material_id, previous
        mid = self.new_material_id()
        return mid, None

    def parent_display_code(self, material_id: Optional[str]) -> str:
        if not material_id:
            return "-"
        for record in self.records:
            if record.material_id == material_id:
                return record.display_code or material_id
        for record in self.previous_records:
            if record.get("material_id") == material_id:
                return record.get("display_code") or "-"
        return "-"

    def add_processing_run(
        self,
        material_id: str,
        run_type: str,
        status: str,
        reason: str,
        input_path: Optional[Path] = None,
        output_path: Optional[Path] = None,
        error_message: Optional[str] = None,
    ) -> None:
        run_id = f"run_{self.archive_dir.name}_{self._processing_run_index:03d}"
        self._processing_run_index += 1
        timestamp = iso_now()
        self.processing_runs.append(
            {
                "run_id": run_id,
                "material_id": material_id,
                "input_variant_id": variant_id_for(material_id, "original"),
                "output_variant_id": None,
                "run_type": run_type,
                "status": status,
                "producer": "scan_materials.py",
                "reason": reason,
                "input_path": str(input_path) if input_path else None,
                "output_path": str(output_path) if output_path else None,
                "error_message": error_message,
                "started_at": timestamp,
                "completed_at": timestamp if status in {"completed", "failed", "skipped"} else None,
                "extra_json": {},
            }
        )

    def should_skip(self, path: Path, skip_output_paths: bool) -> bool:
        if not self.include_hidden and is_hidden(path):
            return True
        if skip_output_paths:
            if path.name in GENERATED_SOURCE_FILES:
                return True
            if any(part in GENERATED_SOURCE_DIRS for part in path.parts):
                return True
            if self.markdown_output_dir != self.source and is_relative_to_path(path, self.markdown_output_dir):
                return True
        return False

    def scan(self) -> None:
        if self.source.is_dir():
            self.scan_directory(self.source, display_prefix="", parent_material_id=None, archive_depth=0)
        else:
            self.scan_file(self.source, display_path=self.source.name, parent_material_id=None, archive_depth=0)
        self._handle_chat_html()

    def _handle_chat_html(self) -> None:
        """识别单文件 chat-html 输入并跑 chat-html 子路径。

        - 当 records 数 == 1 且源是 .html/.htm 且 recognize 通过时执行
        - 不支持多文件输入
        - 写入 extra_json.chat_html；可选真下载；可选 dry-run 输出 dryrun_manifest.json
        """
        if not self.records:
            return
        if len(self.records) > 1:
            return  # 多文件输入不进入 chat-html 子路径

        record = self.records[0]
        source_path = Path(record.absolute_path)
        if source_path.suffix.lower() not in {".html", ".htm"}:
            return

        try:
            html_text = source_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            if self.chat_html_dry_run:
                print(f"warning: 无法读取 {source_path} 作为 chat-html 来源: {exc}", file=sys.stderr)
            return

        if not _chat_html_recognize(html_text):
            if self.chat_html_dry_run:
                print(f"info: {source_path} 不被识别为 chat-html 形态（已跳过子路径）", file=sys.stderr)
            return

        candidates = _chat_html_extract(html_text)
        counts = {
            "download": sum(1 for c in candidates if c.kind == "download"),
            "image": sum(1 for c in candidates if c.kind == "image"),
            "video": sum(1 for c in candidates if c.kind == "video"),
        }
        chat_meta: dict = {
            "recognized": True,
            "downloader": SKILL_VERSION,
            "resource_count": len(candidates),
            "counts_by_kind": counts,
            "resources": [c.to_manifest_extra() for c in candidates],
        }

        # 真下载
        if self.chat_html_download and candidates:
            download_dir = self.chat_html_resource_dir or source_path.parent / "外部资源"
            downloads = []
            for c in candidates:
                res = _chat_html_download(
                    url=c.url,
                    dest_dir=Path(download_dir),
                    display_filename=c.display_filename,
                )
                downloads.append({
                    "resource_id": c.resource_id,
                    "kind": c.kind,
                    "status": res.status,
                    "path": str(res.path) if res.path else None,
                    "attempts": res.attempts,
                    "bytes": res.bytes,
                    "error": res.error,
                })
            chat_meta["downloads"] = downloads
            chat_meta["download_dir"] = str(download_dir)

        # 写入 manifest
        if not isinstance(record.extra_json, dict):
            record.extra_json = {}
        record.extra_json["chat_html"] = chat_meta
        self.chat_html_chat_meta = chat_meta

        # 抽取 0 资源警告
        if not candidates and not self.chat_html_no_fail:
            existing_note = record.note or ""
            record.note = (existing_note + " [chat-html: 未抽取到任何资源]").strip()
            record.needs_human_review = True
            record.review_reasons = add_review_reason(record.review_reasons, "chat_html_extracted_zero")

        # TODO(Task 5/6): dryrun_manifest.json 后续可能扩 schema（tool_version / parser_version / strategy）；
        # 当前 Task 4 直接写出。如果 Task 5/6 改名或加字段，需要同步本方法。
        # dry-run 独立输出
        if self.chat_html_dry_run:
            dryrun = {
                "source": str(source_path),
                "resource_count": len(candidates),
                "counts_by_kind": counts,
                "resources": chat_meta["resources"],
            }
            (self.archive_dir / "dryrun_manifest.json").write_text(
                json.dumps(dryrun, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def _build_chat_html_checklist_section(self) -> str:
        """当某条记录含 chat_html 来源时产出对账小节 markdown；否则返回空字符串。

        假设：`meta["counts_by_kind"]` 一定含 `download` / `image` / `video` 三个键（由
        chat_html_extract.py 的 extract_external_resources 保证）。后续抽取增加新
        kind（如 audio）时需同步扩展本方法的表格行。
        """
        for record in self.records:
            meta = record.extra_json.get("chat_html") if isinstance(record.extra_json, dict) else None
            if meta:
                counts = meta["counts_by_kind"]
                return (
                    "## 外部资源抽取对账（chat-html download / image / video）\n\n"
                    "| 类别 | 应抽取 | 实际抽取 | 命中规则 |\n"
                    "| --- | --- | --- | --- |\n"
                    f"| 外链下载 (download) | — | {counts['download']} | `<a href>` + 域名白名单 |\n"
                    f"| 图片 (image) | — | {counts['image']} | `<img>` + cubox images 或 base64 |\n"
                    f"| 视频 (video) | — | {counts['video']} | `<video>`/`<source>` + mp4 等后缀或视频 CDN |\n"
                    f"| 合计 | — | {meta['resource_count']} | — |\n"
                )
        return ""

    def scan_directory(
        self,
        directory: Path,
        display_prefix: str,
        parent_material_id: Optional[str],
        archive_depth: int,
        skip_output_paths: bool = True,
    ) -> None:
        for path in sorted(directory.iterdir(), key=lambda item: (item.is_file(), item.name.lower())):
            if self.should_skip(path, skip_output_paths=skip_output_paths):
                continue
            if not display_prefix:
                child_display = path.name
            elif display_prefix.endswith("/"):
                child_display = f"{display_prefix}{path.name}"
            else:
                child_display = f"{display_prefix}/{path.name}"
            if path.is_dir():
                self.scan_directory(path, child_display, parent_material_id, archive_depth, skip_output_paths=skip_output_paths)
            elif path.is_file():
                self.scan_file(path, child_display, parent_material_id, archive_depth)

    def scan_file(
        self,
        path: Path,
        display_path: str,
        parent_material_id: Optional[str],
        archive_depth: int,
    ) -> None:
        fingerprint = file_fingerprint(path)
        material_id, previous = self.resolve_material_id(display_path, fingerprint)
        material_type, needs_preprocess, processing_hint, is_container, note = classify_material(path)
        processing_need = processing_need_for(material_type, needs_preprocess)
        readability_status = readability_status_for(material_type, needs_preprocess)
        category = previous.get("category", general_category(material_type)) if previous else general_category(material_type)
        set_id, set_name, _ = material_set_for_category(category)
        primary_variant_id = previous.get("primary_variant_id", variant_id_for(material_id, "original")) if previous else variant_id_for(material_id, "original")
        effective_readability_status = readability_status
        if previous:
            previous_readability_status = previous.get("readability_status")
            if readability_status == "readable" and previous_readability_status in {None, "", "unknown"}:
                effective_readability_status = "readable"
            else:
                effective_readability_status = previous_readability_status or readability_status
        default_primary_readable_variant_id = primary_variant_id if effective_readability_status == "readable" else None
        primary_readable_variant_id = (
            previous.get("primary_readable_variant_id") or default_primary_readable_variant_id
            if previous
            else default_primary_readable_variant_id
        )
        effective_processing_need = processing_need
        if previous:
            previous_processing_need = previous.get("processing_need")
            already_has_readable_output = bool(primary_readable_variant_id) or previous.get("ocr_status") == "completed" or previous.get("content_status") == "completed"
            if previous_processing_need in {None, ""}:
                effective_processing_need = processing_need
            elif previous_processing_need == "none" and processing_need != "none" and not already_has_readable_output:
                effective_processing_need = processing_need
            else:
                effective_processing_need = previous_processing_need
        status = "待处理" if needs_preprocess else "可直接读取"
        review_reasons: list[str] = []
        if material_type == "其他文件":
            review_reasons.append("材料类型无法自动识别")

        record = MaterialRecord(
            material_id=material_id,
            parent_material_id=parent_material_id,
            display_code=previous.get("display_code", "") if previous else "",
            reference_level=normalize_reference_level(previous.get("reference_level")) if previous else "D",
            reference_score=float(previous.get("reference_score", 0) or 0) if previous else 0,
            reference_basis=previous.get("reference_basis") if previous else "初始扫描，待内容理解后评估",
            scan_order=int(previous.get("scan_order") or material_number(material_id)) if previous else self.next_scan_order(),
            legacy_ids=previous.get("legacy_ids", []) if previous else [],
            material_key=f"sha256:{fingerprint}" if fingerprint else None,
            material_set_id=previous.get("material_set_id", set_id) if previous else set_id,
            material_set_name=previous.get("material_set_name", set_name) if previous else set_name,
            variant_kind=previous.get("variant_kind", "original") if previous else "original",
            primary_variant_id=primary_variant_id,
            primary_readable_variant_id=primary_readable_variant_id,
            readability_status=effective_readability_status,
            processing_need=effective_processing_need,
            original_name=path.name,
            display_path=display_path,
            absolute_path=str(path.resolve()),
            material_type=material_type,
            file_extension=combined_suffix(path),
            is_container=is_container,
            needs_preprocess=needs_preprocess,
            processing_hint=processing_hint,
            status=status,
            size_bytes=path.stat().st_size,
            extracted_from_archive=parent_material_id is not None,
            note=note,
            fingerprint=fingerprint,
            source_chain=[parent_material_id] if parent_material_id else [],
            content_status=previous.get("content_status", "pending") if previous else "pending",
            ocr_output_path=previous.get("ocr_output_path") if previous else None,
            ocr_status=previous.get("ocr_status", "pending") if previous else "pending",
            transcript_output_path=previous.get("transcript_output_path") if previous else None,
            annotation_summary=previous.get("annotation_summary") if previous else None,
            annotation_keywords=previous.get("annotation_keywords") if previous else None,
            annotation_case_relevance=previous.get("annotation_case_relevance") if previous else None,
            category=category,
            suggested_name=previous.get("suggested_name") if previous else None,
            organized_path=previous.get("organized_path") if previous else None,
            naming_basis=previous.get("naming_basis") if previous else None,
            confirmation_status=previous.get("confirmation_status", "待处理") if previous else "待处理",
            needs_human_review=bool(review_reasons) or bool(previous.get("needs_human_review", False)) if previous else bool(review_reasons),
            review_reasons=previous.get("review_reasons", review_reasons) if previous else review_reasons,
            confidence=previous.get("confidence") if previous else None,
            extra_json=previous.get("extra_json", {}) if previous else {},
        )
        self.records.append(record)

        if not (self.expand_archives and is_container):
            return
        if archive_depth >= self.max_archive_depth:
            record.status = "已识别压缩包，达到最大拆包层级"
            record.note = "达到最大拆包层级，未继续展开"
            record.needs_human_review = True
            record.review_reasons = add_review_reason(record.review_reasons, "达到最大拆包层级，需人工判断是否继续展开")
            self.add_processing_run(
                record.material_id,
                run_type="extract",
                status="skipped",
                reason="达到最大拆包层级，未继续展开",
                input_path=path,
            )
            return

        extracted = self.extract_archive(path, record.material_id)
        if extracted is None:
            record.status = "待外部解压"
            record.note = "当前环境无法稳定解压该格式，需补装 unar 或 7z，或人工解压"
            record.needs_human_review = True
            record.review_reasons = add_review_reason(record.review_reasons, "压缩包未能自动解压")
            self.add_processing_run(
                record.material_id,
                run_type="extract",
                status="failed",
                reason="自动解压失败",
                input_path=path,
                error_message=record.note,
            )
            return

        record.status = "已拆包"
        record.note = f"已展开到 {extracted}"
        record.processing_need = "none"
        record.content_status = "completed"
        self.add_processing_run(
            record.material_id,
            run_type="extract",
            status="completed",
            reason="压缩包自动解压",
            input_path=path,
            output_path=extracted,
        )
        self.scan_directory(
            extracted,
            display_prefix=f"{display_path}!/",
            parent_material_id=record.material_id,
            archive_depth=archive_depth + 1,
            skip_output_paths=False,
        )

    def extract_archive(self, archive_path: Path, material_id: str) -> Optional[Path]:
        target_dir = self.extracted_dir / f"{material_id}_{safe_name(archive_path.stem)}"
        if target_dir.exists():
            safe_rmtree(target_dir, self.extracted_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        suffix = combined_suffix(archive_path)
        try:
            if suffix == ".zip":
                safe_extract_zip(archive_path, target_dir)
                return target_dir
            if suffix in {".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz"}:
                safe_extract_tar(archive_path, target_dir)
                return target_dir
            if suffix in {".rar", ".7z"}:
                if not self.allow_external_extractor:
                    return None
                if shutil.which("7z"):
                    extract_with_binary("7z", archive_path, target_dir)
                    return target_dir
                if shutil.which("unar"):
                    extract_with_binary("unar", archive_path, target_dir)
                    return target_dir
                return None
            return None
        except (zipfile.BadZipFile, tarfile.TarError, subprocess.CalledProcessError, OSError, ValueError):
            shutil.rmtree(target_dir, ignore_errors=True)
            return None

    def build_missing_records(self) -> list[dict]:
        missing: list[dict] = []
        for record in self.previous_records:
            material_id = str(record.get("material_id", ""))
            if record.get("lifecycle_status") == "missing":
                missing.append(dict(record))
                continue
            if material_id in self.used_previous_ids:
                continue
            missing_record = dict(record)
            missing_record["lifecycle_status"] = "missing"
            missing_record["status"] = "missing"
            missing_record["needs_human_review"] = True
            missing_record["review_reasons"] = add_review_reason(
                missing_record.get("review_reasons"), "源文件未在本次扫描中发现"
            )
            missing.append(missing_record)
        return missing

    def assign_display_codes(self) -> None:
        sorted_records = sorted(
            self.records,
            key=lambda record: (
                REFERENCE_ORDER.get(record.reference_level, REFERENCE_ORDER["D"]),
                -float(record.reference_score or 0),
                record.scan_order,
            ),
        )
        for index, record in enumerate(sorted_records, start=1):
            record.display_code = f"{record.reference_level}{index:03d}"

    def sorted_records_for_report(self) -> list[MaterialRecord]:
        return sorted(
            self.records,
            key=lambda record: (
                REFERENCE_ORDER.get(record.reference_level, REFERENCE_ORDER["D"]),
                int(record.display_code[1:]) if len(record.display_code) > 1 and record.display_code[1:].isdigit() else record.scan_order,
            ),
        )

    def build_material_sets(self) -> list[dict]:
        grouped: dict[str, dict] = {}
        for record in self.sorted_records_for_report():
            if record.material_set_id not in grouped:
                _, _, purpose = material_set_for_category(record.category or "文档材料")
                grouped[record.material_set_id] = {
                    "set_id": record.material_set_id,
                    "set_name": record.material_set_name,
                    "set_type": "reading_set",
                    "purpose": purpose,
                    "material_ids": [],
                    "display_codes": [],
                    "primary_scope": "material_set",
                    "status": "active",
                    "summary": None,
                    "extra_json": {},
                }
            grouped[record.material_set_id]["material_ids"].append(record.material_id)
            grouped[record.material_set_id]["display_codes"].append(record.display_code)
        return list(grouped.values())

    def build_variants(self) -> list[dict]:
        variants_by_id = {str(item.get("variant_id")): dict(item) for item in self.previous_variants if item.get("variant_id")}
        active_ids = {record.material_id for record in self.records}
        missing_ids = {
            str(record.get("material_id"))
            for record in self.previous_records
            if str(record.get("material_id")) not in active_ids and record.get("lifecycle_status", "active") != "missing"
        }
        for record in self.records:
            variant_id = variant_id_for(record.material_id, "original")
            previous_variant = variants_by_id.get(variant_id, {})
            variants_by_id[variant_id] = {
                **previous_variant,
                "variant_id": variant_id,
                "material_id": record.material_id,
                "parent_variant_id": previous_variant.get("parent_variant_id"),
                "variant_kind": "original",
                "file_path": record.absolute_path,
                "display_path": record.display_path,
                "file_hash": record.fingerprint,
                "generator": previous_variant.get("generator", "scan_materials.py"),
                "readability_status": record.readability_status,
                "processing_status": "completed" if record.readability_status == "readable" else previous_variant.get("processing_status", "not_started"),
                "text_quality": previous_variant.get("text_quality"),
                "asset_status": "available",
                "is_primary": True,
                "is_primary_readable": record.primary_readable_variant_id == variant_id,
                "created_at": previous_variant.get("created_at", iso_now()),
                "extra_json": previous_variant.get("extra_json", {}),
            }
        for variant in variants_by_id.values():
            file_path = variant.get("file_path")
            if variant.get("material_id") in missing_ids and file_path and not Path(str(file_path)).exists():
                variant["asset_status"] = "missing"
                variant["is_primary_readable"] = False
        return sorted(variants_by_id.values(), key=lambda item: str(item.get("variant_id")))

    def build_processing_runs(self) -> list[dict]:
        runs_by_id = {str(item.get("run_id")): dict(item) for item in self.previous_processing_runs if item.get("run_id")}
        for run in self.processing_runs:
            runs_by_id[str(run["run_id"])] = run
        return sorted(runs_by_id.values(), key=lambda item: str(item.get("started_at", "")))

    def build_follow_up_candidates(self) -> list[dict]:
        candidates: list[dict] = []
        candidate_ids: set[str] = set()

        def append_candidate(candidate: dict) -> None:
            previous = self.previous_follow_up_candidates.get(str(candidate.get("candidate_id")), {})
            merged = {
                **candidate,
                "status": previous.get("status", candidate["status"]),
                "priority": previous.get("priority", candidate["priority"]),
                "extra_json": previous.get("extra_json", candidate["extra_json"]),
            }
            candidates.append(merged)
            candidate_ids.add(str(candidate["candidate_id"]))

        for record in self.sorted_records_for_report():
            if record.processing_need != "none":
                append_candidate(
                    {
                        "candidate_id": f"follow_{record.material_id.replace('-', '_')}_{record.processing_need}",
                        "material_id": record.material_id,
                        "display_code": record.display_code,
                        "candidate_type": "preprocess_material",
                        "title": f"{record.display_code} 需要预处理",
                        "suggested_action": record.processing_hint,
                        "priority": "P2" if record.reference_level in {"A", "B"} else "P3",
                        "status": "candidate",
                        "reason": record.processing_need,
                        "extra_json": {},
                    }
                )
            if record.needs_human_review:
                append_candidate(
                    {
                        "candidate_id": f"follow_{record.material_id.replace('-', '_')}_human_review",
                        "material_id": record.material_id,
                        "display_code": record.display_code,
                        "candidate_type": "human_review",
                        "title": f"{record.display_code} 需要人工复核",
                        "suggested_action": "人工确认材料类型、内容或处理失败原因",
                        "priority": "P2",
                        "status": "candidate",
                        "reason": "；".join(record.review_reasons or ["需要人工确认"]),
                        "extra_json": {},
                    }
                )
        for candidate_id, previous in self.previous_follow_up_candidates.items():
            if candidate_id not in candidate_ids and previous.get("status") not in {None, "", "candidate"}:
                candidates.append(previous)
        return candidates

    def build_manifest(self) -> dict:
        self.assign_display_codes()
        type_stats: dict[str, int] = {}
        for record in self.records:
            type_stats[record.material_type] = type_stats.get(record.material_type, 0) + 1

        active_records = [asdict(record) for record in self.records]
        missing_records = self.build_missing_records()
        all_records = active_records + missing_records

        container_relations = [
            {
                "material_id": record.material_id,
                "parent_material_id": record.parent_material_id,
                "display_code": record.display_code,
                "parent_display_code": self.parent_display_code(record.parent_material_id),
                "display_path": record.display_path,
            }
            for record in self.records
            if record.parent_material_id
        ]

        return {
            "generated_at": iso_now(),
            "skill": "legal-material-organizer",
            "skill_version": SKILL_VERSION,
            "source": str(self.source),
            "markdown_output_dir": str(self.markdown_output_dir),
            "archive_dir": str(self.archive_dir),
            "work_dir": str(self.work_dir),
            "write_markdown_to_source": self.write_md,
            "expand_archives": self.expand_archives,
            "max_archive_depth": self.max_archive_depth,
            "material_count": len(self.records),
            "total_record_count": len(all_records),
            "missing_count": len(missing_records),
            "type_stats": type_stats,
            "container_relations": container_relations,
            "material_sets": self.build_material_sets(),
            "variants": self.build_variants(),
            "processing_runs": self.build_processing_runs(),
            "follow_up_candidates": self.build_follow_up_candidates(),
            "materials": all_records,
        }

    def build_filing_plan(self, manifest: dict) -> dict:
        entries = []
        for record in self.sorted_records_for_report():
            entries.append(
                {
                    "material_id": record.material_id,
                    "display_code": record.display_code,
                    "material_set_id": record.material_set_id,
                    "material_set_name": record.material_set_name,
                    "reference_level": record.reference_level,
                    "reference_score": record.reference_score,
                    "reference_basis": record.reference_basis,
                    "current_path": record.organized_path or record.display_path,
                    "original_path": record.display_path,
                    "suggested_name": record.suggested_name,
                    "naming_basis": record.naming_basis,
                    "scan_order": record.scan_order,
                }
            )
        return {
            "generated_at": manifest["generated_at"],
            "skill": manifest["skill"],
            "skill_version": manifest["skill_version"],
            "plan_id": f"filing_{self.archive_dir.name}",
            "sort_policy": "reference_level(A-B-C-D), reference_score(desc), scan_order(asc); display_code uses global sequence",
            "material_sets": manifest["material_sets"],
            "entries": entries,
        }

    def build_renaming_map(self, manifest: dict) -> dict:
        entries = []
        for record in self.sorted_records_for_report():
            entries.append(
                {
                    "material_id": record.material_id,
                    "display_code": record.display_code,
                    "material_set_id": record.material_set_id,
                    "material_set_name": record.material_set_name,
                    "source_path": record.display_path,
                    "current_path": record.organized_path or record.display_path,
                    "display_filename_prefix": record.display_code,
                    "applied": bool(record.organized_path),
                }
            )
        return {
            "generated_at": manifest["generated_at"],
            "skill": manifest["skill"],
            "skill_version": manifest["skill_version"],
            "entries": entries,
        }

    def write_outputs(self, args: argparse.Namespace) -> tuple[Optional[Path], Path, Path]:
        manifest_path = self.archive_dir / "materials_manifest.json"
        filing_plan_path = self.archive_dir / "filing_plan.json"
        renaming_map_path = self.archive_dir / "renaming_map.json"
        archive_markdown_path = self.archive_dir / "材料清单.md"
        markdown_path = self.markdown_output_dir / "材料清单.md"

        manifest = self.build_manifest()
        filing_plan = self.build_filing_plan(manifest)
        renaming_map = self.build_renaming_map(manifest)
        markdown_content = self.render_markdown(manifest)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        filing_plan_path.write_text(json.dumps(filing_plan, ensure_ascii=False, indent=2), encoding="utf-8")
        renaming_map_path.write_text(json.dumps(renaming_map, ensure_ascii=False, indent=2), encoding="utf-8")
        archive_markdown_path.write_text(markdown_content, encoding="utf-8")
        source_markdown_path: Optional[Path] = None
        if self.write_md:
            markdown_path.write_text(markdown_content, encoding="utf-8")
            source_markdown_path = markdown_path

        run_meta_path = self.archive_dir / "run_meta.json"
        run_meta_path.write_text(
            json.dumps(
                {
                    "generated_at": manifest["generated_at"],
                    "skill": manifest["skill"],
                    "skill_version": manifest["skill_version"],
                    "source": manifest["source"],
                    "archive_dir": manifest["archive_dir"],
                    "work_dir": manifest["work_dir"],
                    "markdown_output_dir": manifest["markdown_output_dir"],
                    "write_markdown_to_source": manifest["write_markdown_to_source"],
                    "manifest_path": str(manifest_path),
                    "filing_plan_path": str(filing_plan_path),
                    "renaming_map_path": str(renaming_map_path),
                    "args": {
                        "source": str(args.source),
                        "output_dir": args.output_dir,
                        "archive_dir": args.archive_dir,
                        "work_dir": args.work_dir,
                        "no_write_md": args.no_write_md,
                        "fresh": args.fresh,
                        "no_expand_archives": args.no_expand_archives,
                        "allow_external_extractor": args.allow_external_extractor,
                        "max_archive_depth": args.max_archive_depth,
                        "include_hidden": args.include_hidden,
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return source_markdown_path, manifest_path, run_meta_path

    def render_markdown(self, manifest: dict) -> str:
        lines: list[str] = []
        lines.append("# 材料清单")
        lines.append("")
        lines.append("## 基本信息")
        lines.append("")
        lines.append(f"- 扫描时间：{now_ts()}")
        lines.append(f"- 输入来源：`{self.source}`")
        lines.append(f"- 记录归档：`{self.archive_dir}`")
        lines.append(f"- 材料总数：{manifest['material_count']}")
        lines.append(f"- 缺失材料：{manifest['missing_count']}")
        lines.append(f"- 是否自动拆包：{'是' if self.expand_archives else '否'}")
        lines.append("")
        lines.append("## 类型统计")
        lines.append("")
        for material_type, count in sorted(manifest["type_stats"].items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"- {material_type}：{count}")
        lines.append("")
        lines.append("## 清单（按参照度）")
        lines.append("")
        records_by_level = {level: [] for level in REFERENCE_LEVELS}
        for record in self.sorted_records_for_report():
            records_by_level.setdefault(record.reference_level, []).append(record)
        level_names = {
            "A": "A 活文档",
            "B": "B 常查材料",
            "C": "C 存档材料",
            "D": "D 待激活材料",
        }
        for level in REFERENCE_LEVELS:
            records = records_by_level.get(level, [])
            if not records:
                continue
            lines.append(f"### {level_names[level]}")
            lines.append("")
            lines.append("| 展示编号 | 所属材料组 | 原始名称 | 展示路径 | 父级材料 | 类型 | 可读性 | 待处理动作 | 处理状态 | 备注 |")
            lines.append("|----------|------------|----------|----------|----------|------|--------|------------|----------|------|")
            for record in records:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            escape_md_table(record.display_code),
                            escape_md_table(record.material_set_name),
                            escape_md_table(record.original_name),
                            escape_md_table(record.display_path),
                            escape_md_table(self.parent_display_code(record.parent_material_id)),
                            escape_md_table(record.material_type),
                            escape_md_table(record.readability_status),
                            escape_md_table(record.processing_need),
                            escape_md_table(record.status),
                            escape_md_table(record.note),
                        ]
                    )
                    + " |"
                )
            lines.append("")

        relations = manifest["container_relations"]
        if relations:
            lines.append("## 容器来源关系")
            lines.append("")
            lines.append("| 展示编号 | 父级材料 | 展示路径 |")
            lines.append("|----------|----------|----------|")
            for relation in relations:
                lines.append(
                    f"| {escape_md_table(relation['display_code'])} | "
                    f"{escape_md_table(relation['parent_display_code'])} | "
                    f"{escape_md_table(relation['display_path'])} |"
                )
            lines.append("")

        missing = [record for record in manifest["materials"] if record.get("lifecycle_status") == "missing"]
        if missing:
            lines.append("## 缺失材料")
            lines.append("")
            for record in missing:
                lines.append(f"- `{record.get('display_code', '-')}` {record.get('display_path', '-')}")
            lines.append("")

        pending = [record for record in self.records if record.status in {"待处理", "待外部解压"}]
        lines.append("## 待处理提示")
        lines.append("")
        if pending:
            for record in pending:
                lines.append(f"- `{record.display_code}` {record.original_name}：{record.status}，{record.processing_hint}")
        else:
            lines.append("- 当前没有额外待处理提示。")
        lines.append("")
        lines.append("## 机器记录")
        lines.append("")
        lines.append("- JSON、运行元数据和过程文件保存在 Skill 的 archive 目录，不写入本材料目录。")
        lines.append(f"- 本次归档：`{self.archive_dir}`")
        lines.append("")

        checklist_section = self._build_chat_html_checklist_section()
        if checklist_section:
            lines.append("")
            lines.append(checklist_section)

        return "\n".join(lines) + "\n"


def add_review_reason(existing: Optional[list[str]], reason: str) -> list[str]:
    reasons = list(existing or [])
    if reason not in reasons:
        reasons.append(reason)
    return reasons


def escape_md_table(value: object) -> str:
    text = str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def default_markdown_output_dir(source: Path) -> Path:
    return source if source.is_dir() else source.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="扫描法律材料目录，生成初始材料清单和 manifest。")
    parser.add_argument("source", help="源目录或单个文件路径")
    parser.add_argument("-o", "--output-dir", help="Markdown 输出目录；默认使用源目录或源文件所在目录")
    parser.add_argument(
        "--archive-dir",
        help="元数据归档根目录；默认使用源材料旁的 .legal-material-organizer/<名称>/archive/",
    )
    parser.add_argument(
        "--work-dir",
        help="真实材料工作目录；默认使用源材料旁的 .legal-material-organizer/<名称>/work/",
    )
    parser.add_argument(
        "--no-write-md",
        action="store_true",
        help="只生成元数据归档，不向源材料目录写入 Markdown",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="忽略最近一次同源 manifest，重新扫描并重新编号",
    )
    parser.add_argument(
        "--no-expand-archives",
        action="store_true",
        help="只识别压缩包，不自动解压",
    )
    parser.add_argument(
        "--allow-external-extractor",
        action="store_true",
        help="允许调用本机 7z/unar 解压 RAR/7z；默认只自动解压可由 Python 安全检查的 zip/tar",
    )
    parser.add_argument(
        "--max-archive-depth",
        type=int,
        default=2,
        help="最大拆包层级，默认 2",
    )
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="包含隐藏文件和隐藏目录",
    )
    parser.add_argument(
        "--chat-html-dry-run",
        action="store_true",
        help="chat-html 模式：只识别与抽取，生成 dryrun_manifest.json，不下载。",
    )
    parser.add_argument(
        "--chat-html-download",
        action="store_true",
        help="chat-html 模式：执行实际下载到 <source>/外部资源/（与 --chat-html-dry-run 可并存，但同时给会触发真下载）。",
    )
    parser.add_argument(
        "--chat-html-resource-dir",
        help="chat-html 下载目标目录覆盖；默认 <source>/外部资源/",
    )
    parser.add_argument(
        "--chat-html-no-fail",
        action="store_true",
        help="chat-html 抽取到 0 资源时不视为错误",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = Path(args.source).expanduser()
    if not source.exists():
        print(f"错误：输入路径不存在: {source}")
        return 1

    runtime_root = default_runtime_root(source)
    archive_root = Path(args.archive_dir).expanduser() if args.archive_dir else runtime_root / "archive"
    work_dir = Path(args.work_dir).expanduser() if args.work_dir else runtime_root / "work"
    archive_resolved = archive_root.resolve()
    work_resolved = work_dir.resolve()
    skill_root = SCRIPT_DIR.parent.resolve()
    if is_relative_to_path(archive_resolved, skill_root) or is_relative_to_path(work_resolved, skill_root):
        print("错误：元数据归档和真实材料工作目录不得位于 Skill 包内", file=sys.stderr)
        return 2
    if is_relative_to_path(archive_resolved, work_resolved) or is_relative_to_path(work_resolved, archive_resolved):
        print("错误：--archive-dir 与 --work-dir 必须彼此分离，不能相同或互相包含", file=sys.stderr)
        return 2

    try:
        archive_root.mkdir(parents=True, exist_ok=True)
        previous_manifest = None if args.fresh else find_latest_manifest(archive_root, source)
        archive_dir = build_archive_subdir(source, archive_root)
        markdown_output_dir = Path(args.output_dir).expanduser() if args.output_dir else default_markdown_output_dir(source)

        scanner = MaterialScanner(
            source=source,
            markdown_output_dir=markdown_output_dir,
            archive_dir=archive_dir,
            work_dir=work_dir,
            previous_manifest=previous_manifest,
            expand_archives=not args.no_expand_archives,
            allow_external_extractor=args.allow_external_extractor,
            max_archive_depth=max(0, args.max_archive_depth),
            include_hidden=args.include_hidden,
            write_md=not args.no_write_md,
        )
        scanner.chat_html_dry_run = args.chat_html_dry_run
        scanner.chat_html_download = args.chat_html_download
        scanner.chat_html_no_fail = args.chat_html_no_fail
        scanner.chat_html_resource_dir = (
            Path(args.chat_html_resource_dir).expanduser() if args.chat_html_resource_dir else None
        )
        scanner.scan()
        markdown_path, manifest_path, run_meta_path = scanner.write_outputs(args)
    except (OSError, ValueError) as exc:
        print(f"错误：扫描失败: {exc}", file=sys.stderr)
        return 1

    if markdown_path:
        print(f"已生成材料清单: {markdown_path}")
    else:
        print("已按 --no-write-md 跳过源目录 Markdown 写入")
    print(f"已生成 manifest: {manifest_path}")
    print(f"已生成运行记录: {run_meta_path}")
    print(f"归档目录: {scanner.archive_dir}")
    print(f"工作目录: {scanner.work_dir}")
    print(f"材料数量: {len(scanner.records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
