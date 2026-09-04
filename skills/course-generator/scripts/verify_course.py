#!/usr/bin/env python3
"""Verify a Course Generator v2.10.0 course directory against its source index and manifest."""

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

from index_sources import build_index_data


ALL_CONSTRAINTS = (
    "CG-CONTRACT-MANIFEST",
    "CG-OUTPUT-COMPLETE",
    "CG-MATERIAL-TRACE",
    "CG-SOURCE-BLOCK-COVERAGE",
    "CG-SOURCE-AUTHORITY",
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
VISIBLE_TRACE_RE = re.compile(
    r"^\s*>?\s*(?:原文区间|内容来源|生成来源|素材编号)\s*[:：]", re.MULTILINE
)
PRIVATE_AUDIT_TERM_RE = re.compile(
    r"(?i)(?:source-index\.json|course-manifest\.json)|\b(?:SRC|BLK|MAT|IMG)-(?:[0-9]{3,}|x{3,})\b"
)
AUDIT_PATCH_RE = re.compile(
    r"正文证据补丁|证据补丁|原文痕迹|coverage[_ ]?terms?|覆盖足够长度以满足证据|本节按[^\n]{0,40}MAT-xxx"
    r"|面向门禁|生成过程术语|读者正文[^\n]{0,24}(?:门禁|审计)",
    re.IGNORECASE,
)
UNSUPPORTED_SCOPE_RE = re.compile(r"普遍适用|普遍存在|常见规模|行业惯例|标准做法|属于常态|无一例外")
ASCII_CJK_PUNCT_RE = re.compile(r"(?<=[\u3400-\u9fff])[,;:!?](?=[\u3400-\u9fffA-Za-z0-9\"“])")
SOURCE_BLOCK_REF_RE = re.compile(r"^(SRC-[0-9]{3,})#L[0-9]{4,}-L[0-9]{4,}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SOURCE_BLOCK_KINDS = {"content", "derived", "authority", "control", "heading", "image", "timestamp", "speaker", "separator"}
SKIP_CODES = {"derived_duplicate", "meeting", "device", "chatter", "pure_repeat", "no_course_value", "authority_superseded"}
GENERIC_SKIP_CODES = {"pure_repeat", "no_course_value"}
EXPANDED_MATERIAL_TYPES = {"案例", "操作", "踩坑", "取舍", "疑问"}
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
CHAPTER_READER_DEPTH_RATIO = 0.40
MAX_CHAPTER_READER_EXPANSION_RATIO = 2.50
MAX_CHAPTER_READER_EXPANSION_FLOOR = 1400
MIN_MATERIAL_COUNT_BUDGET = 60
MATERIAL_COUNT_BUDGET_RATIO = 0.50
IMAGE_PROSE_BUDGET = 500
MIN_DOCUMENT_IMAGE_BUDGET = 3
RICH_SOURCE_IMAGE_THRESHOLD = 12
SOURCE_IMAGES_PER_REQUIRED_READER_IMAGE = 20
DEFAULT_MAX_CHAPTERS = 8
GENERIC_SKIP_RATIO = 0.05
GENERIC_SKIP_MIN_ALLOWANCE = 1200
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
H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
FORBIDDEN_TRANSIENT_SUFFIXES = {".py", ".sh", ".js", ".ts", ".command"}
FORBIDDEN_TRANSIENT_DIRS = {".course-work", "__pycache__"}
ALLOWED_MACHINE_JSON_FILES = {"course-manifest.json", "source-index.json"}


def material_count_budget(content_block_count: int) -> int:
    """Cap ledger fragmentation while leaving headroom for short sources."""
    return max(MIN_MATERIAL_COUNT_BUDGET, math.ceil(content_block_count * MATERIAL_COUNT_BUDGET_RATIO))


def style_prose(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`[^`\n]+`", "", text)
    text = IMAGE_RE.sub("", text)
    return text


def repeated_paragraph_pairs(text: str) -> list[tuple[int, int, float]]:
    paragraphs: list[str] = []
    for raw in re.split(r"\n\s*\n", style_prose(text)):
        value = raw.strip()
        if not value or value.startswith(("#", ">", "|", "![")):
            continue
        normalized = re.sub(r"[^\w\u3400-\u9fff]+", "", value.casefold())
        if len(normalized) >= 120:
            paragraphs.append(normalized)
    grams = [{value[i : i + 5] for i in range(len(value) - 4)} for value in paragraphs]
    pairs: list[tuple[int, int, float]] = []
    for left in range(len(grams)):
        for right in range(left + 1, len(grams)):
            overlap = len(grams[left] & grams[right])
            denominator = min(len(grams[left]), len(grams[right]))
            ratio = overlap / denominator if denominator else 0.0
            if overlap >= 60 and ratio >= 0.40:
                pairs.append((left + 1, right + 1, ratio))
    return pairs


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def low_signal_coverage_term(value: str) -> bool:
    normalized = re.sub(r"\s+", "", value.strip())
    if not normalized:
        return True
    if LOW_SIGNAL_COVERAGE_RE.search(normalized) or LOW_SIGNAL_COVERAGE_PREFIX_RE.search(normalized):
        return True
    return bool(re.fullmatch(r"[\u4e00-\u9fff]+", normalized) and LOW_SIGNAL_COVERAGE_SUFFIX_RE.search(normalized))


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


def pattern_hit_summary(text: str, pattern: re.Pattern[str], limit: int = 6) -> tuple[int, str]:
    hits: list[str] = []
    total = 0
    for match in pattern.finditer(text):
        total += 1
        if len(hits) < limit:
            line = text.count("\n", 0, match.start()) + 1
            hits.append(f"L{line} {match.group(0)!r}")
    suffix = "；".join(hits)
    if total > limit:
        suffix += f"；另 {total - limit} 处"
    return total, suffix


def h2_sections(text: str) -> tuple[list[str], dict[str, str], set[str]]:
    matches = list(H2_RE.finditer(text))
    headings: list[str] = []
    bodies: dict[str, str] = {}
    duplicates: set[str] = set()
    for index, match in enumerate(matches):
        heading = match.group(1).strip()
        headings.append(heading)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        if heading in bodies:
            duplicates.add(heading)
        else:
            bodies[heading] = text[match.end() : end].strip()
    return headings, bodies, duplicates


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


def validate_authority(
    value: Any,
    label: str,
    source_ids: set[str],
    all_block_ids: set[str] | None,
    audit: Audit,
    *,
    require_acknowledgements: bool,
    block_previews: dict[str, str] | None = None,
) -> dict[str, Any]:
    required = (
        {"mode", "notices", "corrections", "acknowledgements", "correction_routes"}
        if require_acknowledgements
        else {"mode", "notices", "corrections"}
    )
    authority = check_allowed_keys(value, required, set(), label, audit)
    mode = authority.get("mode")
    if mode not in {"current", "historical"}:
        audit.fail("CG-SOURCE-AUTHORITY", f"{label}.mode 必须为 current 或 historical")
    notices = require_list(authority.get("notices"), f"{label}.notices", audit)
    notice_ids: list[str] = []
    for index, raw in enumerate(notices, 1):
        notice_label = f"{label}.notices[{index}]"
        notice = check_allowed_keys(
            raw,
            {"id", "source_block_id", "source_ref", "controlling_titles", "controlling_source_ids", "section_hint"},
            set(),
            notice_label,
            audit,
        )
        notice_id = notice.get("id")
        if not isinstance(notice_id, str) or not re.fullmatch(r"AUTH-[0-9]{3,}", notice_id):
            audit.fail("CG-SOURCE-AUTHORITY", f"{notice_label}.id 非法")
        else:
            notice_ids.append(notice_id)
        block_id = notice.get("source_block_id")
        if not isinstance(block_id, str) or not ID_PATTERNS["block"].fullmatch(block_id):
            audit.fail("CG-SOURCE-AUTHORITY", f"{notice_label}.source_block_id 非法")
        elif all_block_ids is not None and block_id not in all_block_ids:
            audit.fail("CG-SOURCE-AUTHORITY", f"{notice_label} 引用了不存在的 authority block {block_id}")
        validate_source_refs([notice.get("source_ref")], f"{notice_label}.source_ref", source_ids, audit)
        titles = require_list(notice.get("controlling_titles"), f"{notice_label}.controlling_titles", audit, nonempty=True)
        if not all(is_nonempty_string(item) for item in titles):
            audit.fail("CG-SOURCE-AUTHORITY", f"{notice_label}.controlling_titles 必须是非空字符串数组")
        controls = require_list(notice.get("controlling_source_ids"), f"{notice_label}.controlling_source_ids", audit)
        if any(control not in source_ids for control in controls):
            audit.fail("CG-SOURCE-AUTHORITY", f"{notice_label} 含不存在的控制来源 ID")
        if mode == "current" and not controls:
            audit.fail("CG-SOURCE-AUTHORITY", f"{notice_id or notice_label} current 模式必须解析至少一个控制来源")
        if notice.get("section_hint") is not None and not is_nonempty_string(notice.get("section_hint")):
            audit.fail("CG-SOURCE-AUTHORITY", f"{notice_label}.section_hint 必须为非空字符串或 null")
    if notice_ids != [f"AUTH-{index:03d}" for index in range(1, len(notice_ids) + 1)]:
        audit.fail("CG-SOURCE-AUTHORITY", f"{label}.notices 必须从 AUTH-001 连续编号")

    corrections = require_list(authority.get("corrections"), f"{label}.corrections", audit)
    correction_ids: list[str] = []
    for index, raw in enumerate(corrections, 1):
        correction_label = f"{label}.corrections[{index}]"
        correction = check_allowed_keys(
            raw,
            {"id", "authority_id", "source_id", "source_ref", "original_text", "revised_text", "deprecated_terms", "superseded_candidate_block_ids"},
            set(),
            correction_label,
            audit,
        )
        correction_id = correction.get("id")
        if not isinstance(correction_id, str) or not re.fullmatch(r"COR-[0-9]{3,}", correction_id):
            audit.fail("CG-SOURCE-AUTHORITY", f"{correction_label}.id 非法")
        else:
            correction_ids.append(correction_id)
        if correction.get("authority_id") not in notice_ids:
            audit.fail("CG-SOURCE-AUTHORITY", f"{correction_label}.authority_id 未绑定有效声明")
        source_id = correction.get("source_id")
        if source_id not in source_ids:
            audit.fail("CG-SOURCE-AUTHORITY", f"{correction_label}.source_id 未绑定有效控制来源")
        refs = validate_source_refs([correction.get("source_ref")], f"{correction_label}.source_ref", source_ids, audit)
        if refs and source_id and refs[0].split("#", 1)[0] != source_id:
            audit.fail("CG-SOURCE-AUTHORITY", f"{correction_label}.source_ref 与 source_id 不一致")
        if not is_nonempty_string(correction.get("original_text")) or not is_nonempty_string(correction.get("revised_text")):
            audit.fail("CG-SOURCE-AUTHORITY", f"{correction_label} 必须保留原口径与修订口径")
        deprecated_terms = require_list(correction.get("deprecated_terms"), f"{correction_label}.deprecated_terms", audit)
        if not all(is_nonempty_string(item) for item in deprecated_terms) or duplicate_items(deprecated_terms):
            audit.fail("CG-SOURCE-AUTHORITY", f"{correction_label}.deprecated_terms 必须是无重复非空字符串数组")
        candidate_ids = require_list(
            correction.get("superseded_candidate_block_ids"),
            f"{correction_label}.superseded_candidate_block_ids",
            audit,
        )
        if len(candidate_ids) > 8 or duplicate_items(candidate_ids):
            audit.fail("CG-SOURCE-AUTHORITY", f"{correction_label}.superseded_candidate_block_ids 必须无重复且最多 8 项")
        for block_id in candidate_ids:
            if not isinstance(block_id, str) or not ID_PATTERNS["block"].fullmatch(block_id):
                audit.fail("CG-SOURCE-AUTHORITY", f"{correction_label} 含非法候选来源块 {block_id!r}")
            elif all_block_ids is not None and block_id not in all_block_ids:
                audit.fail("CG-SOURCE-AUTHORITY", f"{correction_label} 含不存在的候选来源块 {block_id}")
    if correction_ids != [f"COR-{index:03d}" for index in range(1, len(correction_ids) + 1)]:
        audit.fail("CG-SOURCE-AUTHORITY", f"{label}.corrections 必须从 COR-001 连续编号")
    if mode == "historical" and corrections:
        audit.fail("CG-SOURCE-AUTHORITY", f"{label} historical 模式不得加载 current 修正规则")

    if require_acknowledgements:
        acknowledgements = require_list(authority.get("acknowledgements"), f"{label}.acknowledgements", audit)
        if len(acknowledgements) != len(notices):
            audit.fail("CG-SOURCE-AUTHORITY", "全部来源权威声明必须在 plan 阶段逐项确认")
        for notice, raw in zip(notices, acknowledgements):
            acknowledgement = check_allowed_keys(
                raw,
                {"id", "action", "controlling_source_ids", "reader_notice"},
                set(),
                f"{label}.acknowledgements",
                audit,
            )
            if acknowledgement.get("id") != notice.get("id"):
                audit.fail("CG-SOURCE-AUTHORITY", f"{notice.get('id')} acknowledgement 缺失或错位")
            if mode == "current":
                if acknowledgement.get("action") != "apply_control" or acknowledgement.get("controlling_source_ids") != notice.get("controlling_source_ids"):
                    audit.fail("CG-SOURCE-AUTHORITY", f"{notice.get('id')} 未精确确认控制来源")
                if acknowledgement.get("reader_notice") is not None:
                    audit.fail("CG-SOURCE-AUTHORITY", f"{notice.get('id')} current 模式的 reader_notice 必须为 null")
            elif mode == "historical":
                if acknowledgement.get("action") != "historical_disclaimer" or acknowledgement.get("controlling_source_ids") != []:
                    audit.fail("CG-SOURCE-AUTHORITY", f"{notice.get('id')} historical 模式 acknowledgement 非法")
                if not is_nonempty_string(acknowledgement.get("reader_notice")) or len(acknowledgement["reader_notice"].strip()) < 12:
                    audit.fail("CG-SOURCE-AUTHORITY", f"{notice.get('id')} historical 模式缺少至少 12 字读者提示")
        routes = require_list(authority.get("correction_routes"), f"{label}.correction_routes", audit)
        route_ids: list[str] = []
        all_candidate_reviews: list[dict[str, Any]] = []
        for index, raw in enumerate(routes, 1):
            route_label = f"{label}.correction_routes[{index}]"
            route = check_allowed_keys(
                raw,
                {"id", "target_chapter_id", "target_section_heading", "supersession_status", "superseded_source_block_ids", "supersession_note", "candidate_block_reviews"},
                set(),
                route_label,
                audit,
            )
            if route.get("id") not in correction_ids:
                audit.fail("CG-SOURCE-AUTHORITY", f"{route_label}.id 未绑定有效修正规则")
            else:
                route_ids.append(route["id"])
            if not isinstance(route.get("target_chapter_id"), str) or not ID_PATTERNS["chapter"].fullmatch(route["target_chapter_id"]):
                audit.fail("CG-SOURCE-AUTHORITY", f"{route_label}.target_chapter_id 非法")
            if not is_nonempty_string(route.get("target_section_heading")):
                audit.fail("CG-SOURCE-AUTHORITY", f"{route_label}.target_section_heading 必须非空")
            supersession_status = route.get("supersession_status")
            superseded_ids = require_list(
                route.get("superseded_source_block_ids"),
                f"{route_label}.superseded_source_block_ids",
                audit,
            )
            if supersession_status not in {"blocks_identified", "no_matching_source_block"}:
                audit.fail("CG-SOURCE-AUTHORITY", f"{route_label}.supersession_status 非法")
            if duplicate_items(superseded_ids):
                audit.fail("CG-SOURCE-AUTHORITY", f"{route_label}.superseded_source_block_ids 不得重复")
            for block_id in superseded_ids:
                if not isinstance(block_id, str) or not ID_PATTERNS["block"].fullmatch(block_id):
                    audit.fail("CG-SOURCE-AUTHORITY", f"{route_label} 含非法被替代来源块 {block_id!r}")
                elif all_block_ids is not None and block_id not in all_block_ids:
                    audit.fail("CG-SOURCE-AUTHORITY", f"{route_label} 含不存在的被替代来源块 {block_id}")
            if supersession_status == "blocks_identified" and not superseded_ids:
                audit.fail("CG-SOURCE-AUTHORITY", f"{route_label} 标记 blocks_identified 时必须列出来源块")
            if supersession_status == "no_matching_source_block" and superseded_ids:
                audit.fail("CG-SOURCE-AUTHORITY", f"{route_label} 标记 no_matching_source_block 时来源块列表必须为空")
            note = route.get("supersession_note")
            if not is_nonempty_string(note) or len(note.strip()) < 12:
                audit.fail("CG-SOURCE-AUTHORITY", f"{route_label}.supersession_note 必须至少 12 字")
            correction = next(
                (item for item in corrections if isinstance(item, dict) and item.get("id") == route.get("id")),
                {},
            )
            expected_candidate_ids = correction.get("superseded_candidate_block_ids") or []
            raw_candidate_reviews = route.get("candidate_block_reviews")
            if not isinstance(raw_candidate_reviews, list):
                audit.fail(
                    "CG-SOURCE-AUTHORITY",
                    f"{route_label}.candidate_block_reviews 必须逐项审查全部候选来源块",
                )
            candidate_reviews = require_list(
                raw_candidate_reviews,
                f"{route_label}.candidate_block_reviews",
                audit,
            )
            reviewed_candidate_ids: list[str] = []
            superseded_candidate_ids: set[str] = set()
            retained_candidate_ids: set[str] = set()
            for review_index, review_raw in enumerate(candidate_reviews, 1):
                review_label = f"{route_label}.candidate_block_reviews[{review_index}]"
                review = check_allowed_keys(
                    review_raw,
                    {"source_block_id", "decision", "evidence_quote", "reason"},
                    set(),
                    review_label,
                    audit,
                )
                block_id = review.get("source_block_id")
                if not isinstance(block_id, str) or not ID_PATTERNS["block"].fullmatch(block_id):
                    audit.fail("CG-SOURCE-AUTHORITY", f"{review_label}.source_block_id 非法")
                else:
                    reviewed_candidate_ids.append(block_id)
                decision = review.get("decision")
                if decision not in {"superseded", "retained_current"}:
                    audit.fail("CG-SOURCE-AUTHORITY", f"{review_label}.decision 非法")
                elif isinstance(block_id, str):
                    if decision == "superseded":
                        superseded_candidate_ids.add(block_id)
                    else:
                        retained_candidate_ids.add(block_id)
                reason = review.get("reason")
                if not is_nonempty_string(reason) or len(reason.strip()) < 12:
                    audit.fail("CG-SOURCE-AUTHORITY", f"{review_label}.reason 必须至少 12 字")
                evidence_quote = review.get("evidence_quote")
                if not is_nonempty_string(evidence_quote) or len(evidence_quote.strip()) < 6:
                    audit.fail("CG-SOURCE-AUTHORITY", f"{review_label}.evidence_quote 必须摘录至少 6 字候选预览原文")
                elif isinstance(block_id, str) and evidence_quote.strip() not in (block_previews or {}).get(block_id, ""):
                    audit.fail("CG-SOURCE-AUTHORITY", f"{review_label}.evidence_quote 必须逐字来自该候选预览")
                all_candidate_reviews.append(review)
            if reviewed_candidate_ids != expected_candidate_ids:
                audit.fail(
                    "CG-SOURCE-AUTHORITY",
                    f"{route.get('id')} 必须按索引顺序逐项审查全部候选块；"
                    f"期望 {expected_candidate_ids!r}，实际 {reviewed_candidate_ids!r}",
                )
            normalized_reasons = [
                re.sub(r"\s+", "", str(review.get("reason") or "")).casefold()
                for review in candidate_reviews
                if isinstance(review, dict) and is_nonempty_string(review.get("reason"))
            ]
            if len(normalized_reasons) > 1 and len(set(normalized_reasons)) == 1:
                audit.fail("CG-SOURCE-AUTHORITY", f"{route.get('id')}.candidate_block_reviews 不得为全部候选复制同一判断理由")
            if superseded_candidate_ids - set(superseded_ids):
                audit.fail(
                    "CG-SOURCE-AUTHORITY",
                    f"{route.get('id')} 判定 superseded 的候选块未进入隔离列表: "
                    f"{', '.join(sorted(superseded_candidate_ids - set(superseded_ids)))}",
                )
            if retained_candidate_ids & set(superseded_ids):
                audit.fail(
                    "CG-SOURCE-AUTHORITY",
                    f"{route.get('id')} 判定 retained_current 的候选块被误列入隔离列表: "
                    f"{', '.join(sorted(retained_candidate_ids & set(superseded_ids)))}",
                )
        if len(all_candidate_reviews) >= 12 and all(
            isinstance(review, dict) and review.get("decision") == "superseded"
            for review in all_candidate_reviews
        ):
            audit.fail("CG-SOURCE-AUTHORITY", "候选审查不得把整张高召回矩阵一律判为 superseded；须逐块区分旧结论与相邻主题")
        if route_ids != correction_ids:
            audit.fail("CG-SOURCE-AUTHORITY", "全部控制文档修正必须按 COR 编号顺序各路由一次")
    return authority


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
        {"schema_version", "generator_version", "course", "sources", "source_index", "source_authority", "overview", "chapters", "materials", "images"},
        {"audit_files"},
        "manifest",
        audit,
    )
    if top.get("schema_version") != "1.8":
        audit.fail("CG-CONTRACT-MANIFEST", "schema_version 必须为 1.8；旧版课程需重建逐块证据审查契约后升级")
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
    block_previews: dict[str, str] = {}
    indexed_image_blocks: list[tuple[str, str]] = []
    source_index_pairs: list[tuple[str, str]] = []
    source_index_authority: dict[str, Any] = {}
    if source_index:
        index_top = check_allowed_keys(source_index, {"schema_version", "authority", "sources"}, set(), "source-index", audit)
        if index_top.get("schema_version") != "1.4":
            audit.fail("CG-SOURCE-BLOCK-COVERAGE", "source-index.schema_version 必须为 1.4")
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
                elif block_id:
                    block_previews[block_id] = block["preview"]
        if source_index_pairs != manifest_sources:
            audit.fail(
                "CG-SOURCE-BLOCK-COVERAGE",
                f"source-index 来源清单与 manifest 不一致: {source_index_pairs!r} != {manifest_sources!r}",
            )
        if not content_block_ids:
            audit.fail("CG-SOURCE-BLOCK-COVERAGE", "source-index 未产生任何 content block")

        source_index_authority = validate_authority(
            index_top.get("authority"),
            "source-index.authority",
            source_ids,
            all_block_ids,
            audit,
            require_acknowledgements=False,
        )

    manifest_authority = validate_authority(
        top.get("source_authority"),
        "source_authority",
        source_ids,
        all_block_ids,
        audit,
        require_acknowledgements=True,
        block_previews=block_previews,
    )
    if source_index_authority:
        if (
            manifest_authority.get("mode") != source_index_authority.get("mode")
            or manifest_authority.get("notices") != source_index_authority.get("notices")
            or manifest_authority.get("corrections") != source_index_authority.get("corrections")
        ):
            audit.fail("CG-SOURCE-AUTHORITY", "manifest.source_authority 必须与 source-index.authority 的模式、声明和修正规则完全一致")

    raw_source_block_texts: dict[str, str] = {}
    raw_source_text_parts: list[str] = []
    source_root_rebound = False
    if source_root is not None:
        raw_input = source_root.expanduser().resolve()
        output_hint = source_index_path or (root / "source-index.json")
        try:
            authority_mode = source_index_authority.get("mode", "current")
            rebuilt_index, raw_source_block_texts = build_index_data(raw_input, output_hint, authority_mode)
        except (OSError, UnicodeError, ValueError) as exc:
            audit.fail("CG-SOURCE-BLOCK-COVERAGE", f"无法按来源权威模式重建 source_root: {exc}")
        else:
            expected_manifest_sources = [
                (item.get("id"), item.get("path"))
                for item in rebuilt_index.get("sources") or []
            ]
            if manifest_sources != expected_manifest_sources:
                audit.fail(
                    "CG-SOURCE-BLOCK-COVERAGE",
                    f"source_root 完整来源清单与 manifest 不一致: {expected_manifest_sources!r} != {manifest_sources!r}",
                )
            if source_index != rebuilt_index:
                audit.fail(
                    "CG-SOURCE-BLOCK-COVERAGE",
                    "source-index 不是当前原始来源按确定性分块与权威解析算法产生的完整结果",
                )
            else:
                source_root_rebound = True
                raw_source_text_parts.extend(raw_source_block_texts.values())
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
    chapter_section_headings: dict[str, list[str]] = {}
    raw_chapters = require_list(top.get("chapters"), "chapters", audit, nonempty=True)
    if len(raw_chapters) > max_chapters:
        audit.fail(
            "CG-OUTPUT-COMPLETE",
            f"章节数为 {len(raw_chapters)}，超过本次上限 {max_chapters}；"
            "先合并结构性薄章，只有用户明确要求超过 8 章时才读取高级覆盖说明",
        )
    for index, item in enumerate(raw_chapters, 1):
        label = f"chapters[{index}]"
        chapter = check_allowed_keys(item, {"id", "file", "title", "section_headings", "source_refs", "material_ids", "image_ids"}, set(), label, audit)
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
        section_values = require_list(chapter.get("section_headings"), f"{label}.section_headings", audit, nonempty=True)
        valid_sections: list[str] = []
        for heading in section_values:
            if not is_nonempty_string(heading):
                audit.fail("CG-CONTRACT-MANIFEST", f"{label}.section_headings 含空或非字符串值")
            else:
                valid_sections.append(heading.strip())
        if duplicate_items(valid_sections):
            audit.fail("CG-CONTRACT-MANIFEST", f"{label}.section_headings 不得重复")
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
            chapter_section_headings[chapter_id] = valid_sections
        chapter_records.append({"id": chapter_id, "file": file_name, "path": safe_relative_path(root, file_name, f"{label}.file", audit), "image_ids": image_values, "section_headings": valid_sections})

    material_ids: set[str] = set()
    included_materials = 0
    covered_content_blocks: set[str] = set()
    block_dispositions: dict[str, set[str]] = defaultdict(set)
    included_blocks_by_chapter: dict[str, set[str]] = defaultdict(set)
    included_blocks_by_section: dict[tuple[str, str], set[str]] = defaultdict(set)
    generic_skip_block_ids: set[str] = set()
    planned_superseded_block_ids = {
        block_id
        for route in manifest_authority.get("correction_routes") or []
        if isinstance(route, dict)
        for block_id in route.get("superseded_source_block_ids") or []
        if isinstance(block_id, str)
    }
    non_content_superseded = sorted(planned_superseded_block_ids - content_block_ids)
    if non_content_superseded:
        audit.fail(
            "CG-SOURCE-AUTHORITY",
            "被当前修订替代的来源块必须都是 content block: " + ", ".join(non_content_superseded[:12]),
        )
    quarantined_superseded_block_ids: set[str] = set()
    evidence_records: list[dict[str, Any]] = []
    section_material_counts: dict[tuple[str, str], int] = defaultdict(int)
    raw_materials = require_list(top.get("materials"), "materials", audit, nonempty=True)
    maximum_materials = material_count_budget(len(content_block_ids))
    if len(raw_materials) > maximum_materials:
        audit.fail(
            "CG-MATERIAL-TRACE",
            f"素材共 {len(raw_materials)} 项，超过 {len(content_block_ids)} 个 content block 对应的 {maximum_materials} 项预算；请合并同一观点、连续操作阶段或同一 skip 理由",
        )
    for index, item in enumerate(raw_materials, 1):
        label = f"materials[{index}]"
        material = check_allowed_keys(
            item,
            {"id", "type", "summary", "source_refs", "source_block_ids", "coverage_terms", "disposition", "target_chapter_id", "target_section_heading", "reader_evidence"},
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
        target_section = material.get("target_section_heading")
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
        if len(valid_terms) > 3:
            audit.fail("CG-READER-EVIDENCE", f"{material_id or label} 的 coverage_terms 最多 3 项")
        if duplicate_items(valid_terms):
            audit.fail("CG-READER-EVIDENCE", f"{material_id or label} 的 coverage_terms 不得重复")
        for term in valid_terms:
            if low_signal_coverage_term(term):
                audit.fail(
                    "CG-READER-EVIDENCE",
                    f"{material_id or label} 的 coverage term {term!r} 是口语指代、语气词或截断片段",
                )
        if source_root_rebound and valid_block_values:
            bound_source_text = "\n".join(raw_source_block_texts.get(block_id, "") for block_id in valid_block_values)
            for term in valid_terms:
                if term not in bound_source_text:
                    audit.fail(
                        "CG-CLAIM-FIDELITY",
                        f"{material_id or label} 的覆盖词 {term!r} 未出现在其绑定的原始来源块；不得发明抽象词后回写正文",
                    )
        for block_id in valid_block_values:
            if isinstance(disposition, str):
                block_dispositions[block_id].add(disposition)
        if disposition == "include":
            reintroduced = sorted(set(valid_block_values) & planned_superseded_block_ids)
            if reintroduced:
                audit.fail(
                    "CG-SOURCE-AUTHORITY",
                    f"{material_id or label} 把已由当前修订替代的来源块重新作为 include: {', '.join(reintroduced)}",
                )
            if len(valid_block_values) > MAX_INCLUDE_BLOCKS_PER_MATERIAL:
                audit.fail(
                    "CG-READER-DEPTH",
                    f"{material_id or label} 合并了 {len(valid_block_values)} 个来源块；include 素材最多 {MAX_INCLUDE_BLOCKS_PER_MATERIAL} 个，应按可复用信息单元拆分",
                )
            required_term_count = max(1, min(3, math.ceil(len(valid_block_values) / 3)))
            if len(valid_terms) < required_term_count:
                audit.fail(
                    "CG-READER-DEPTH",
                    f"{material_id or label} 覆盖 {len(valid_block_values)} 个来源块时至少需要 {required_term_count} 个具体 coverage_terms，实际 {len(valid_terms)} 个",
                )
            if len(valid_terms) < 1:
                audit.fail("CG-READER-EVIDENCE", f"{material_id or label} 为 include 时至少预承诺 1 个 coverage_term")
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
            if not is_nonempty_string(target_section):
                audit.fail("CG-READER-EVIDENCE", f"{material_id or label} 为 include 时必须填写 target_section_heading")
            elif target_section not in chapter_section_headings.get(str(target), []):
                audit.fail("CG-READER-EVIDENCE", f"{material_id or label} 的目标小节未在 {target} 声明: {target_section!r}")
            else:
                target_section = target_section.strip()
                section_material_counts[(str(target), target_section)] += 1
                included_blocks_by_section[(str(target), target_section)].update(valid_block_values)
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
                        "section": target_section,
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
            if target_section is not None:
                audit.fail("CG-READER-EVIDENCE", f"{material_id or label} 为 skip 时 target_section_heading 必须为 null")
            if not is_nonempty_string(material.get("skip_reason")):
                audit.fail("CG-MATERIAL-TRACE", f"{material_id or label} 为 skip 时必须填写 skip_reason")
            skip_code = material.get("skip_code")
            if skip_code not in SKIP_CODES:
                audit.fail("CG-SOURCE-BLOCK-COVERAGE", f"{material_id or label} 为 skip 时必须填写受控 skip_code")
            elif skip_code in GENERIC_SKIP_CODES:
                generic_skip_block_ids.update(valid_block_values)
            if skip_code == "authority_superseded":
                unexpected = sorted(set(valid_block_values) - planned_superseded_block_ids)
                if unexpected:
                    audit.fail(
                        "CG-SOURCE-AUTHORITY",
                        f"{material_id or label} 把未确认的来源块误标为 authority_superseded: {', '.join(unexpected)}",
                    )
                quarantined_superseded_block_ids.update(set(valid_block_values) & planned_superseded_block_ids)
            elif set(valid_block_values) & planned_superseded_block_ids:
                audit.fail(
                    "CG-SOURCE-AUTHORITY",
                    f"{material_id or label} 的被替代来源块必须使用 skip_code=authority_superseded",
                )
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
    missing_quarantine = sorted(planned_superseded_block_ids - quarantined_superseded_block_ids)
    if missing_quarantine:
        audit.fail(
            "CG-SOURCE-AUTHORITY",
            "plan 已确认的被替代来源块必须全部进入 authority_superseded skip: "
            + ", ".join(missing_quarantine[:12]),
        )
    total_content_chars = sum(content_block_char_counts.values())
    generic_skip_chars = sum(
        content_block_char_counts.get(block_id, 0)
        for block_id in generic_skip_block_ids
    )
    generic_skip_allowance = max(
        GENERIC_SKIP_MIN_ALLOWANCE,
        math.ceil(total_content_chars * GENERIC_SKIP_RATIO),
    )
    if generic_skip_chars > generic_skip_allowance:
        audit.fail(
            "CG-SOURCE-BLOCK-COVERAGE",
            f"pure_repeat/no_course_value 共跳过 {generic_skip_chars} 字，超过 {generic_skip_allowance} 字预算；"
            "拆分并纳入其中的案例、操作、踩坑、取舍或疑问，只保留真正重复或无课程价值的片段",
        )

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
    reader_sections: dict[str, dict[str, str]] = {}
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
        headings, section_bodies, duplicate_headings = h2_sections(text)
        reader_sections[document_id] = section_bodies
        if document_id != "OVERVIEW":
            declared_headings = record.get("section_headings") or []
            if duplicate_headings:
                audit.fail("CG-READER-EVIDENCE", f"{file_name} 含重复二级标题: {', '.join(sorted(duplicate_headings))}")
            if headings != declared_headings:
                audit.fail(
                    "CG-READER-EVIDENCE",
                    f"{file_name} 的二级标题序列必须与 manifest.section_headings 完全一致；实际 {headings!r}",
                )
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
        speaker_count, speaker_hits = pattern_hit_summary(text, SPEAKER_TERM_RE)
        if speaker_count:
            audit.fail(
                "CG-BOOKLIKE-TONE",
                f"{file_name} 残留模糊讲者/讲师/主讲人指代（共 {speaker_count} 处：{speaker_hits}）",
            )
        frame_count, frame_hits = pattern_hit_summary(text, SOURCE_FRAME_RE)
        if frame_count:
            audit.fail(
                "CG-BOOKLIKE-TONE",
                f"{file_name} 残留课程现场或原文框架词（共 {frame_count} 处：{frame_hits}）",
            )
        filler_count, filler_hits = pattern_hit_summary(text, FILLER_RE)
        if filler_count:
            audit.fail(
                "CG-BOOKLIKE-TONE",
                f"{file_name} 残留明确口语赘词（共 {filler_count} 处：{filler_hits}）",
            )
        prose_for_style = style_prose(text)
        ascii_punctuation = ASCII_CJK_PUNCT_RE.findall(prose_for_style)
        if len(ascii_punctuation) >= 4:
            audit.fail(
                "CG-BOOKLIKE-TONE",
                f"{file_name} 中文正文混用半角标点 {len(ascii_punctuation)} 处，应统一为中文全角标点",
            )
        if prose_for_style.count('"') % 2 or prose_for_style.count("“") != prose_for_style.count("”"):
            audit.fail("CG-BOOKLIKE-TONE", f"{file_name} 存在未闭合或不成对的引号")
        repeated_pairs = repeated_paragraph_pairs(text)
        if repeated_pairs:
            preview = "、".join(f"第{left}/{right}段({ratio:.0%})" for left, right, ratio in repeated_pairs[:4])
            audit.fail("CG-BOOKLIKE-TONE", f"{file_name} 存在高度近重复长段，疑似为补足篇幅重复展开：{preview}")
        if document_id != "OVERVIEW" and source_root_rebound:
            for heading, section_text in section_bodies.items():
                bound_source_text = "\n".join(
                    raw_source_block_texts.get(block_id, "")
                    for block_id in included_blocks_by_section.get((document_id, heading), set())
                )
                unsupported = sorted(
                    {
                        match.group(0)
                        for match in UNSUPPORTED_SCOPE_RE.finditer(style_prose(section_text))
                        if match.group(0) not in bound_source_text
                    }
                )
                if unsupported:
                    audit.fail(
                        "CG-CLAIM-FIDELITY",
                        f"{file_name}::{heading} 把单个观察扩成来源未支持的范围结论: {', '.join(unsupported)}",
                    )
        if VISIBLE_TRACE_RE.search(text):
            audit.fail("CG-AUDIT-SEPARATION", f"{file_name} 暴露审计元数据，应移入 manifest/审计文件")
        leaked_private_terms: list[str] = []
        for match in PRIVATE_AUDIT_TERM_RE.finditer(text):
            token = match.group(0)
            if normalize_fidelity_text(token) not in normalized_raw_source and token not in leaked_private_terms:
                leaked_private_terms.append(token)
        if leaked_private_terms:
            audit.fail(
                "CG-AUDIT-SEPARATION",
                f"{file_name} 暴露来源中不存在的生成器内部术语: {', '.join(leaked_private_terms[:8])}",
            )
        leaked_patch_terms: list[str] = []
        for match in AUDIT_PATCH_RE.finditer(text):
            token = match.group(0)
            if normalize_fidelity_text(token) not in normalized_raw_source and token not in leaked_patch_terms:
                leaked_patch_terms.append(token)
        if leaked_patch_terms:
            audit.fail(
                "CG-AUDIT-SEPARATION",
                f"{file_name} 暴露面向门禁的证据补丁措辞: {', '.join(leaked_patch_terms[:6])}",
            )
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

    if manifest_authority.get("mode") == "historical":
        overview_text = reader_texts.get("OVERVIEW", "")
        for acknowledgement in manifest_authority.get("acknowledgements") or []:
            reader_notice = acknowledgement.get("reader_notice") if isinstance(acknowledgement, dict) else None
            if is_nonempty_string(reader_notice) and reader_notice not in overview_text:
                audit.fail(
                    "CG-SOURCE-AUTHORITY",
                    f"{acknowledgement.get('id')} 的 historical reader_notice 未原样出现在总览",
                )
    elif manifest_authority.get("mode") == "current":
        correction_catalog = {
            item.get("id"): item
            for item in manifest_authority.get("corrections") or []
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        for route in manifest_authority.get("correction_routes") or []:
            if not isinstance(route, dict):
                continue
            correction = correction_catalog.get(route.get("id"))
            chapter_id = route.get("target_chapter_id")
            section_heading = route.get("target_section_heading")
            if chapter_id not in chapter_section_headings:
                audit.fail("CG-SOURCE-AUTHORITY", f"{route.get('id')} 指向不存在的章节 {chapter_id!r}")
                continue
            if section_heading not in chapter_section_headings.get(chapter_id, []):
                audit.fail("CG-SOURCE-AUTHORITY", f"{route.get('id')} 指向未声明的小节 {section_heading!r}")
                continue
            revised_text = correction.get("revised_text") if isinstance(correction, dict) else None
            if not isinstance(revised_text, str) or revised_text not in reader_sections.get(chapter_id, {}).get(section_heading, ""):
                audit.fail(
                    "CG-SOURCE-AUTHORITY",
                    f"{route.get('id')} 的修订口径未原样保留在 {chapter_id}::{section_heading}",
                )
        for correction in correction_catalog.values():
            for term in correction.get("deprecated_terms") or []:
                if not isinstance(term, str):
                    continue
                hits = [document_id for document_id, text in reader_texts.items() if term.casefold() in text.casefold()]
                if hits:
                    audit.fail(
                        "CG-SOURCE-AUTHORITY",
                        f"{correction.get('id')} 已废弃术语 {term!r} 仍出现在读者文档: {', '.join(hits)}",
                    )

    evidence_signatures: list[str] = []
    for evidence in evidence_records:
        material_id = evidence.get("id") or "<unknown>"
        target = evidence.get("target")
        target_section = evidence.get("section")
        quotes = evidence.get("quotes") or []
        target_text = reader_texts.get(target, "")
        section_text = reader_sections.get(target, {}).get(target_section, "")
        if not quotes:
            continue
        evidence_signatures.append("\u241e".join(quotes))
        for quote_index, quote in enumerate(quotes, 1):
            if quote not in target_text:
                audit.fail(
                    "CG-READER-EVIDENCE",
                    f"{material_id} 的 reader_evidence.quotes[{quote_index}] 未出现在目标章节 {target}",
                )
            elif quote not in section_text:
                audit.fail(
                    "CG-READER-EVIDENCE",
                    f"{material_id} 的 reader_evidence.quotes[{quote_index}] 未出现在目标小节 {target_section!r}",
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
    for chapter_id, headings in chapter_section_headings.items():
        for heading in headings:
            if section_material_counts.get((chapter_id, heading), 0) == 0:
                audit.fail("CG-READER-EVIDENCE", f"{chapter_id} 的小节 {heading!r} 没有任何 include 素材绑定")

    included_block_ids = set().union(*included_blocks_by_chapter.values()) if included_blocks_by_chapter else set()
    included_source_chars = sum(content_block_char_counts.get(block_id, 0) for block_id in included_block_ids)
    chapter_reader_prose_chars = sum(reader_prose_chars.get(chapter_id, 0) for chapter_id in chapter_ids)
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
        maximum_chars = max(
            MAX_CHAPTER_READER_EXPANSION_FLOOR,
            math.ceil(source_chars * MAX_CHAPTER_READER_EXPANSION_RATIO),
        )
        chapter_depth_measurements[chapter_id]["maximum-reader-prose-chars"] = maximum_chars
        if source_chars and prose_chars > maximum_chars:
            audit.fail(
                "CG-READER-DEPTH",
                f"{chapter_id} 可见文字 {prose_chars} 字，超过本章纳入来源允许的扩写上限 {maximum_chars} 字；应合并到有充分来源的章节或删除来源外延伸",
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
    transient_files = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in FORBIDDEN_TRANSIENT_SUFFIXES
    )
    transient_dirs = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_dir() and path.name in FORBIDDEN_TRANSIENT_DIRS
    )
    transient_machine_files = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".json", ".yaml", ".yml"}
        and path.relative_to(root).as_posix() not in ALLOWED_MACHINE_JSON_FILES
    )
    if transient_files or transient_dirs or transient_machine_files:
        samples = (transient_files + transient_dirs + transient_machine_files)[:12]
        audit.fail(
            "CG-OUTPUT-COMPLETE",
            "候选目录残留一次性脚本、批次/计划文件或中间工作目录: " + ", ".join(samples),
        )

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
        "CG-MATERIAL-TRACE": {
            "included-material-count": included_materials,
            "total-material-count": len(raw_materials),
            "maximum-material-count": maximum_materials,
        },
        "CG-SOURCE-BLOCK-COVERAGE": {
            "content-block-count": len(content_block_ids),
            "covered-content-block-count": len(covered_content_blocks),
            "generic-skip-char-count": generic_skip_chars,
            "generic-skip-char-allowance": generic_skip_allowance,
        },
        "CG-SOURCE-AUTHORITY": {
            "authority-mode": manifest_authority.get("mode"),
            "authority-notice-count": len(manifest_authority.get("notices") or []),
            "authority-acknowledgement-count": len(manifest_authority.get("acknowledgements") or []),
            "authority-correction-count": len(manifest_authority.get("corrections") or []),
            "authority-correction-route-count": len(manifest_authority.get("correction_routes") or []),
        },
        "CG-READER-EVIDENCE": {
            "evidence-count": len(evidence_records),
            "declared-section-count": sum(len(values) for values in chapter_section_headings.values()),
            "grounded-section-count": sum(1 for count in section_material_counts.values() if count > 0),
        },
        "CG-CLAIM-FIDELITY": {
            "source-root-rebound": source_root_rebound,
            "source-block-text-count": len(raw_source_block_texts),
        },
        "CG-READER-DEPTH": {
            "included-source-char-count": included_source_chars,
            "chapter-reader-prose-char-count": chapter_reader_prose_chars,
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
        "authority-ids": [item.get("id") for item in manifest_authority.get("notices") or [] if isinstance(item, dict)],
        "image-ids": sorted(image_records),
    }
    audit.warn("需人工复核：覆盖词与缩写门禁只拦截可确定的来源外补写，不证明全部事实忠实度、跨章一致性或图片视觉价值")
    return audit


def emit_result(audit: Audit, root: Path) -> int:
    print("========== course-generator v2.10.0 验收 ==========")
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
    parser = argparse.ArgumentParser(description="按 source-index.json 与 course-manifest.json 验收 Course Generator v2.10.0 课程目录")
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
