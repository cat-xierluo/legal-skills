#!/usr/bin/env python3
"""用行级 OCR 文字和版面块重建自然段。

设计约束：
- 行级 OCR 是文字真值，版面模型只提供顺序、段落候选和印章区域；
- 不调用大语言模型，不使用版面块文本覆盖 OCR 文字；
- PDF 文字层仍保留行级坐标，自然段只写入 Markdown/纯文本输出。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


_CJK = r"\u2e80-\u2fff\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
_CJK_PUNCT = "，。！？；：、（）《》〈〉【】〔〕“”‘’—…"
_DEFAULT_EXCLUDED_LABELS = frozenset({"seal"})
_TEXT_LIKE_LABELS = frozenset({"text", "content", "paragraph"})
_STRONG_PARAGRAPH_START = re.compile(
    r"^(?:"
    r"第[一二三四五六七八九十百千万零〇0-9]+[章节条款项]|"
    r"[0-9０-９]+\s*[-－—]\s*[0-9０-９]+|"
    r"[0-9０-９]+\s*[、.．]|"
    r"[（(][一二三四五六七八九十百千万零〇0-9０-９]+[)）]|"
    r"[一二三四五六七八九十百千万零〇]+[、.．]"
    r")"
)


def normalize_inline_text(text: str) -> str:
    """清理段内冗余空白，同时保留拉丁词之间的必要空格。"""
    value = str(text or "")
    value = re.sub(r"[\t\r\n\u00a0\u3000]+", " ", value)
    value = re.sub(r" +", " ", value).strip()
    cjk_or_punct = f"{_CJK}{re.escape(_CJK_PUNCT)}"
    value = re.sub(rf"(?<=[{cjk_or_punct}]) +(?=[{cjk_or_punct}])", "", value)
    value = re.sub(rf"(?<=[{_CJK}]) +(?=[{re.escape(_CJK_PUNCT)}])", "", value)
    value = re.sub(rf"(?<=[{re.escape(_CJK_PUNCT)}]) +(?=[{_CJK}])", "", value)
    value = re.sub(rf"^([0-9０-９]+\s*[-－—]\s*[0-9０-９]+)(?=[{_CJK}])", r"\1 ", value)
    return value


def _join_fragments(parts: list[str]) -> str:
    result = ""
    for raw in parts:
        part = normalize_inline_text(raw)
        if not part:
            continue
        separator = ""
        if result and result[-1:].isascii() and result[-1:].isalpha():
            if part[:1].isascii() and part[:1].isalpha():
                separator = " "
        result += separator + part
    return normalize_inline_text(result)


def _bbox_from_poly(poly: object) -> tuple[float, float, float, float] | None:
    if not isinstance(poly, (list, tuple)) or len(poly) < 4:
        return None
    try:
        xs = [float(point[0]) for point in poly]
        ys = [float(point[1]) for point in poly]
    except (TypeError, ValueError, IndexError):
        return None
    if not xs or not ys:
        return None
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


def _intersection_ratio(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    x0 = max(first[0], second[0])
    y0 = max(first[1], second[1])
    x1 = min(first[2], second[2])
    y1 = min(first[3], second[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    intersection = (x1 - x0) * (y1 - y0)
    first_area = max((first[2] - first[0]) * (first[3] - first[1]), 1.0)
    return intersection / first_area


def _scaled_layout_blocks(text_page: dict, layout_page: dict) -> list[dict]:
    text_width = float(text_page.get("width") or 0)
    text_height = float(text_page.get("height") or 0)
    layout_width = float(layout_page.get("width") or 0)
    layout_height = float(layout_page.get("height") or 0)
    sx = text_width / layout_width if text_width > 0 and layout_width > 0 else 1.0
    sy = text_height / layout_height if text_height > 0 and layout_height > 0 else 1.0

    result = []
    for fallback_index, block in enumerate(layout_page.get("layout_blocks", [])):
        bbox = block.get("bbox") if isinstance(block, dict) else None
        if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
            continue
        try:
            scaled = (
                float(bbox[0]) * sx,
                float(bbox[1]) * sy,
                float(bbox[2]) * sx,
                float(bbox[3]) * sy,
            )
        except (TypeError, ValueError):
            continue
        item = dict(block)
        item["bbox"] = scaled
        try:
            item["index"] = int(block.get("index", fallback_index))
        except (TypeError, ValueError):
            item["index"] = fallback_index
        result.append(item)
    return sorted(result, key=lambda item: (item["index"], item["bbox"][1], item["bbox"][0]))


def _prepare_rows(page: dict, text_overrides: dict[int, tuple[str, float]] | None = None) -> list[dict]:
    rows = []
    for index, row in enumerate(page.get("rows", [])):
        if not isinstance(row, (list, tuple)) or len(row) < 3:
            continue
        text, score, poly = row[:3]
        try:
            numeric_score = float(score)
        except (TypeError, ValueError):
            numeric_score = 0.0
        if text_overrides and index in text_overrides:
            text, numeric_score = text_overrides[index]
        content = normalize_inline_text(text)
        if not content or numeric_score <= 0:
            continue
        rows.append({
            "index": index,
            "text": content,
            "score": numeric_score,
            "bbox": _bbox_from_poly(poly),
        })
    return rows


def _scaled_secondary_rows(text_page: dict, layout_page: dict) -> list[dict]:
    """把 PP-StructureV3 的行级 OCR 坐标缩放到主 OCR 坐标空间。"""
    text_width = float(text_page.get("width") or 0)
    text_height = float(text_page.get("height") or 0)
    layout_width = float(layout_page.get("width") or 0)
    layout_height = float(layout_page.get("height") or 0)
    sx = text_width / layout_width if text_width > 0 and layout_width > 0 else 1.0
    sy = text_height / layout_height if text_height > 0 and layout_height > 0 else 1.0
    secondary = _prepare_rows(layout_page)
    for row in secondary:
        bbox = row.get("bbox")
        if bbox:
            row["bbox"] = (
                bbox[0] * sx,
                bbox[1] * sy,
                bbox[2] * sx,
                bbox[3] * sy,
            )
    return secondary


def _structure_text_overrides(
    text_page: dict,
    layout_page: dict | None,
    *,
    primary_score_ceiling: float = 0.80,
    secondary_score_floor: float = 0.90,
    score_margin: float = 0.10,
) -> dict[int, tuple[str, float]]:
    """仅在主 OCR 低置信且坐标高度重合时，采用 Structure 行级高置信文字。"""
    if not layout_page or not layout_page.get("rows"):
        return {}
    primary = _prepare_rows(text_page)
    secondary = _scaled_secondary_rows(text_page, layout_page)
    overrides: dict[int, tuple[str, float]] = {}
    used_secondary: set[int] = set()
    for row in primary:
        bbox = row.get("bbox")
        if bbox is None or row["score"] >= primary_score_ceiling:
            continue
        candidates = []
        for candidate in secondary:
            if candidate["index"] in used_secondary:
                continue
            candidate_bbox = candidate.get("bbox")
            if candidate_bbox is None or candidate["score"] < secondary_score_floor:
                continue
            if candidate["score"] < row["score"] + score_margin:
                continue
            forward = _intersection_ratio(bbox, candidate_bbox)
            reverse = _intersection_ratio(candidate_bbox, bbox)
            mutual_overlap = min(forward, reverse)
            if mutual_overlap < 0.50:
                continue
            candidates.append((mutual_overlap, candidate["score"], candidate))
        if not candidates:
            continue
        selected = max(candidates, key=lambda item: (item[0], item[1]))[2]
        overrides[row["index"]] = (selected["text"], selected["score"])
        used_secondary.add(selected["index"])
    return overrides


def _vertical_overlap_ratio(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    overlap = min(first[3], second[3]) - max(first[1], second[1])
    if overlap <= 0:
        return 0.0
    return overlap / max(min(first[3] - first[1], second[3] - second[1]), 1.0)


def _rows_in_reading_order(rows: list[dict]) -> list[dict]:
    """先聚合同一视觉行，再按横坐标排序，避免轻微 y 抖动打乱片段顺序。"""
    pending = sorted(
        rows,
        key=lambda row: (
            row["bbox"][1] if row.get("bbox") else float(row["index"]),
            row["bbox"][0] if row.get("bbox") else 0.0,
            row["index"],
        ),
    )
    visual_lines: list[dict] = []
    for row in pending:
        bbox = row.get("bbox")
        if bbox is None:
            visual_lines.append({"bbox": None, "rows": [row]})
            continue
        selected = None
        for line in reversed(visual_lines):
            line_bbox = line["bbox"]
            if line_bbox is None:
                continue
            if _vertical_overlap_ratio(bbox, line_bbox) >= 0.45:
                selected = line
                break
            if line_bbox[3] < bbox[1]:
                break
        if selected is None:
            visual_lines.append({"bbox": bbox, "rows": [row]})
            continue
        selected["rows"].append(row)
        old = selected["bbox"]
        selected["bbox"] = (
            min(old[0], bbox[0]),
            min(old[1], bbox[1]),
            max(old[2], bbox[2]),
            max(old[3], bbox[3]),
        )
    visual_lines.sort(key=lambda line: (
        line["bbox"][1] if line["bbox"] else float(line["rows"][0]["index"]),
        line["bbox"][0] if line["bbox"] else 0.0,
    ))
    ordered = []
    for line in visual_lines:
        line["rows"].sort(key=lambda row: (
            row["bbox"][0] if row.get("bbox") else 0.0,
            row["index"],
        ))
        ordered.extend(line["rows"])
    return ordered


def _group_rows_by_geometry(
    rows: list[dict],
    content_bounds: tuple[float, float] | None = None,
    *,
    max_vertical_gap_ratio: float = 1.0,
    coalesce_same_line: bool = False,
) -> list[list[dict]]:
    """按行距、缩进和右边界判断物理换行是否属于同一自然段。"""
    if not rows:
        return []

    ordered = _rows_in_reading_order(rows)
    valid_boxes = [row["bbox"] for row in ordered if row.get("bbox")]
    if content_bounds is None:
        content_right = max((bbox[2] for bbox in valid_boxes), default=0.0)
        content_left = min((bbox[0] for bbox in valid_boxes), default=0.0)
    else:
        content_left, content_right = content_bounds

    groups: list[list[dict]] = []
    current: list[dict] = []
    had_wrap = False
    previous: dict | None = None

    for row in ordered:
        bbox = row.get("bbox")
        if previous is None:
            current = [row]
            previous = row
            continue

        previous_bbox = previous.get("bbox")
        if bbox is None or previous_bbox is None:
            groups.append(current)
            current = [row]
            previous = row
            had_wrap = False
            continue

        prev_height = max(previous_bbox[3] - previous_bbox[1], 1.0)
        height = max(bbox[3] - bbox[1], 1.0)
        min_height = min(prev_height, height)
        y_gap = bbox[1] - previous_bbox[3]
        x_diff = bbox[0] - previous_bbox[0]
        right_tolerance = max(min_height * 1.5, (content_right - content_left) * 0.06)
        starts_near_left = bbox[0] <= content_left + max(min_height * 2.0, 24.0)
        previous_fills_line = previous_bbox[2] >= content_right - right_tolerance

        same_visual_line = _vertical_overlap_ratio(previous_bbox, bbox) >= 0.45
        if same_visual_line:
            continues = coalesce_same_line
        elif y_gap <= -0.2 * min_height or y_gap >= max_vertical_gap_ratio * min_height:
            continues = False
        else:
            wraps_to_left = x_diff < -min_height * 0.3
            same_margin = abs(x_diff) < min_height * 0.15
            continues = previous_fills_line and (starts_near_left or wraps_to_left)
            if same_margin and had_wrap:
                continues = True

        if continues:
            current.append(row)
            had_wrap = True
        else:
            groups.append(current)
            current = [row]
            had_wrap = False

        previous = row

    if current:
        groups.append(current)
    return groups


def _group_bbox(group: list[dict]) -> tuple[float, float, float, float] | None:
    boxes = [row["bbox"] for row in group if row.get("bbox")]
    if not boxes:
        return None
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _group_text(group: list[dict], label: str = "") -> str:
    parts = [row["text"] for row in group]
    if label.lower() == "table":
        return " | ".join(normalize_inline_text(part) for part in parts if normalize_inline_text(part))
    return _join_fragments(parts)


def _should_merge_adjacent_text_blocks(
    previous_group: list[dict],
    previous_label: str,
    current_group: list[dict],
    current_label: str,
) -> bool:
    if previous_label.lower() not in _TEXT_LIKE_LABELS:
        return False
    if current_label.lower() not in _TEXT_LIKE_LABELS:
        return False
    previous_bbox = _group_bbox(previous_group)
    current_bbox = _group_bbox(current_group)
    if previous_bbox is None or current_bbox is None:
        return False
    previous_height = max(previous_bbox[3] - previous_bbox[1], 1.0)
    current_height = max(current_bbox[3] - current_bbox[1], 1.0)
    line_height = min(previous_height, current_height)
    vertical_gap = current_bbox[1] - previous_bbox[3]
    same_visual_line = _vertical_overlap_ratio(previous_bbox, current_bbox) >= 0.45
    if not same_visual_line and (vertical_gap < -0.25 * line_height or vertical_gap > 1.6 * line_height):
        return False
    horizontal_overlap = max(
        0.0,
        min(previous_bbox[2], current_bbox[2]) - max(previous_bbox[0], current_bbox[0]),
    )
    min_width = max(min(previous_bbox[2] - previous_bbox[0], current_bbox[2] - current_bbox[0]), 1.0)
    same_column = horizontal_overlap / min_width >= 0.60
    same_margin = abs(previous_bbox[0] - current_bbox[0]) <= 1.5 * line_height
    if not same_column and not same_margin:
        return False
    previous_text = _group_text(previous_group, previous_label)
    current_text = _group_text(current_group, current_label)
    if not previous_text or not current_text:
        return False
    if not same_visual_line and re.search(r"[。！？!?]$", previous_text):
        return False
    if _STRONG_PARAGRAPH_START.match(current_text):
        return False
    return True


def _row_matches_block(row_bbox: tuple[float, float, float, float], block_bbox: tuple[float, float, float, float]) -> float:
    row_height = max(row_bbox[3] - row_bbox[1], 1.0)
    cx = (row_bbox[0] + row_bbox[2]) / 2
    cy = (row_bbox[1] + row_bbox[3]) / 2
    tolerance = row_height * 0.55
    center_inside = (
        block_bbox[0] - tolerance <= cx <= block_bbox[2] + tolerance
        and block_bbox[1] - tolerance <= cy <= block_bbox[3] + tolerance
    )
    overlap = _intersection_ratio(row_bbox, block_bbox)
    if not center_inside and overlap < 0.2:
        return 0.0
    return overlap + (2.0 if center_inside else 0.0)


def _explicit_false(value: object) -> bool:
    return value is False or value == 0 or str(value).strip().lower() == "false"


def _page_paragraphs(
    text_page: dict,
    layout_page: dict | None,
    page_number: int,
    excluded_labels: frozenset[str],
    layout_coverage_floor: float,
) -> tuple[list[dict], dict]:
    text_overrides = _structure_text_overrides(text_page, layout_page)
    rows = _prepare_rows(text_page, text_overrides)
    page_boxes = [row["bbox"] for row in rows if row.get("bbox")]
    right_edges = sorted(bbox[2] for bbox in page_boxes)
    content_right = (
        right_edges[round((len(right_edges) - 1) * 0.8)]
        if right_edges else 0.0
    )
    page_bounds = (
        min((bbox[0] for bbox in page_boxes), default=0.0),
        content_right,
    )
    if not layout_page or not layout_page.get("layout_blocks"):
        groups = _group_rows_by_geometry(rows, page_bounds)
        return [
            {
                "page": page_number,
                "text": _group_text(group),
                "row_indices": [row["index"] for row in group],
                "source": "geometry",
                "label": "",
            }
            for group in groups
        ], {
            "strategy": "geometry",
            "rows": len(rows),
            "assigned_rows": 0,
            "excluded_rows": 0,
            "excluded_row_indices": [],
            "orphan_rows": len(rows),
            "layout_coverage": 0.0,
            "structure_text_fallbacks": 0,
            "structure_text_fallback_indices": [],
            "layout_boundary_merges": 0,
        }

    blocks = _scaled_layout_blocks(text_page, layout_page)
    excluded_blocks = [
        block for block in blocks
        if str(block.get("label", "")).lower() in excluded_labels
    ]
    content_blocks = [block for block in blocks if block not in excluded_blocks]
    block_rows: dict[int, list[dict]] = {id(block): [] for block in content_blocks}
    excluded_count = 0
    excluded_row_indices: list[int] = []
    orphan_rows: list[dict] = []

    for row in rows:
        bbox = row.get("bbox")
        if bbox and any(_row_matches_block(bbox, block["bbox"]) >= 2.0 for block in excluded_blocks):
            excluded_count += 1
            excluded_row_indices.append(row["index"])
            continue

        candidates = []
        if bbox:
            for block in content_blocks:
                match_score = _row_matches_block(bbox, block["bbox"])
                if match_score > 0:
                    candidates.append((match_score, -block["index"], block))
        if candidates:
            selected = max(candidates, key=lambda item: (item[0], item[1]))[2]
            block_rows[id(selected)].append(row)
        else:
            orphan_rows.append(row)

    usable_rows = max(len(rows) - excluded_count, 0)
    assigned_count = sum(len(items) for items in block_rows.values())
    coverage = assigned_count / usable_rows if usable_rows else 0.0
    if coverage < layout_coverage_floor:
        groups = _group_rows_by_geometry([
            row for row in rows
            if not (
                row.get("bbox")
                and any(_row_matches_block(row["bbox"], block["bbox"]) >= 2.0 for block in excluded_blocks)
            )
        ], page_bounds)
        return [
            {
                "page": page_number,
                "text": _group_text(group),
                "row_indices": [row["index"] for row in group],
                "source": "geometry_fallback",
                "label": "",
            }
            for group in groups
        ], {
            "strategy": "geometry_fallback",
            "rows": len(rows),
            "assigned_rows": assigned_count,
            "excluded_rows": excluded_count,
            "excluded_row_indices": excluded_row_indices,
            "orphan_rows": len(orphan_rows),
            "layout_coverage": coverage,
            "structure_text_fallbacks": len(text_overrides),
            "structure_text_fallback_indices": sorted(text_overrides),
            "layout_boundary_merges": 0,
        }

    ordered_segments: list[tuple[float, int, list[dict], str, str]] = []
    previous_populated_block: dict | None = None
    layout_boundary_merges = 0
    for block in content_blocks:
        assigned = block_rows[id(block)]
        if not assigned:
            continue
        block_label = str(block.get("label", "")).lower()
        if block_label in _TEXT_LIKE_LABELS:
            group_bounds = (block["bbox"][0], block["bbox"][2])
            max_gap_ratio = 2.0
        elif block_label == "table":
            group_bounds = (block["bbox"][0], block["bbox"][2])
            max_gap_ratio = 0.9
        else:
            group_bounds = page_bounds
            max_gap_ratio = 1.0
        groups = _group_rows_by_geometry(
            assigned,
            group_bounds,
            max_vertical_gap_ratio=max_gap_ratio,
            coalesce_same_line=True,
        )
        explicit_continuation = (
            previous_populated_block is not None
            and (
                _explicit_false(previous_populated_block.get("seg_end"))
                or _explicit_false(block.get("seg_start"))
            )
        )
        heuristic_continuation = (
            previous_populated_block is not None
            and bool(ordered_segments)
            and bool(groups)
            and _should_merge_adjacent_text_blocks(
                ordered_segments[-1][2],
                ordered_segments[-1][4],
                groups[0],
                str(block.get("label", "")),
            )
        )
        if (explicit_continuation or heuristic_continuation) and ordered_segments and groups:
            previous = ordered_segments[-1]
            ordered_segments[-1] = (
                previous[0],
                previous[1],
                previous[2] + groups[0],
                previous[3],
                previous[4],
            )
            groups = groups[1:]
            layout_boundary_merges += 1
        for split_index, group in enumerate(groups):
            ordered_segments.append((
                float(block["index"]),
                split_index,
                group,
                "layout",
                str(block.get("label", "")),
            ))
        previous_populated_block = block

    # 极少量未分配行仍保留；按其垂直中心插入最近的版面顺序位置。
    block_centers = [((block["bbox"][1] + block["bbox"][3]) / 2, block["index"]) for block in content_blocks]
    for orphan_index, group in enumerate(_group_rows_by_geometry(orphan_rows, page_bounds)):
        bbox = group[0].get("bbox")
        center_y = (bbox[1] + bbox[3]) / 2 if bbox else float(group[0]["index"])
        preceding = [index for block_y, index in block_centers if block_y <= center_y]
        approximate_order = (max(preceding) + 0.5) if preceding else -0.5
        ordered_segments.append((approximate_order, orphan_index, group, "layout_orphan", ""))

    ordered_segments.sort(key=lambda item: (item[0], item[1]))
    paragraphs = [
        {
            "page": page_number,
            "text": _group_text(group, label),
            "row_indices": [row["index"] for row in group],
            "source": source,
            "label": label,
        }
        for _, _, group, source, label in ordered_segments
    ]
    return paragraphs, {
        "strategy": "layout",
        "rows": len(rows),
        "assigned_rows": assigned_count,
        "excluded_rows": excluded_count,
        "excluded_row_indices": excluded_row_indices,
        "orphan_rows": len(orphan_rows),
        "layout_coverage": coverage,
        "structure_text_fallbacks": len(text_overrides),
        "structure_text_fallback_indices": sorted(text_overrides),
        "layout_boundary_merges": layout_boundary_merges,
    }


def reconstruct_paragraphs(
    text_entries: list[dict],
    layout_entries: list[dict] | None = None,
    *,
    excluded_labels: frozenset[str] = _DEFAULT_EXCLUDED_LABELS,
    layout_coverage_floor: float = 0.75,
) -> tuple[list[dict], dict]:
    """返回自然段列表及可审计的融合诊断。"""
    paragraphs: list[dict] = []
    page_diagnostics: list[dict] = []
    for page_index, text_page in enumerate(text_entries):
        layout_page = None
        if layout_entries is not None and page_index < len(layout_entries):
            layout_page = layout_entries[page_index]
        page_paragraphs, diagnostics = _page_paragraphs(
            text_page,
            layout_page,
            page_index + 1,
            frozenset(label.lower() for label in excluded_labels),
            layout_coverage_floor,
        )
        paragraphs.extend(item for item in page_paragraphs if item.get("text"))
        page_diagnostics.append(diagnostics)

    total_rows = sum(item["rows"] for item in page_diagnostics)
    total_assigned = sum(item["assigned_rows"] for item in page_diagnostics)
    total_excluded = sum(item["excluded_rows"] for item in page_diagnostics)
    total_text_fallbacks = sum(item["structure_text_fallbacks"] for item in page_diagnostics)
    total_layout_boundary_merges = sum(item["layout_boundary_merges"] for item in page_diagnostics)
    total_usable = max(total_rows - total_excluded, 0)
    diagnostics = {
        "pages": page_diagnostics,
        "paragraphs": len(paragraphs),
        "rows": total_rows,
        "assigned_rows": total_assigned,
        "excluded_rows": total_excluded,
        "layout_coverage": total_assigned / total_usable if total_usable else 0.0,
        "structure_text_fallbacks": total_text_fallbacks,
        "layout_boundary_merges": total_layout_boundary_merges,
    }
    return paragraphs, diagnostics


def generate_semantic_text(
    text_entries: list[dict],
    layout_entries: list[dict] | None = None,
) -> str:
    paragraphs, _ = reconstruct_paragraphs(text_entries, layout_entries)
    return "\n\n".join(item["text"] for item in paragraphs)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="融合 OCR 行坐标和版面块，输出自然段文本")
    parser.add_argument("--text-dump", required=True, help="行级 OCR dump JSON")
    parser.add_argument("--layout-dump", help="PP-StructureV3/VL 版面 dump JSON")
    parser.add_argument("--output", required=True, help="输出 Markdown/文本路径")
    parser.add_argument("--diagnostics", help="可选：输出不含正文的诊断 JSON")
    parser.add_argument("--filtered-dump", help="可选：输出移除印章区域噪声行后的 OCR dump")
    parser.add_argument(
        "--actualtext",
        action="store_true",
        help="实验性：在 filtered dump 中写入 PDF /ActualText 自然段元数据",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    from pdf_ocr_corrections import dump_page_entries, load_page_entries

    text_entries, text_meta = load_page_entries(args.text_dump)
    layout_entries = None
    layout_meta = {}
    if args.layout_dump:
        layout_entries, layout_meta = load_page_entries(args.layout_dump)

    paragraphs, diagnostics = reconstruct_paragraphs(text_entries, layout_entries)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n\n".join(item["text"] for item in paragraphs), encoding="utf-8")

    if args.diagnostics:
        report = {
            "text_model": text_meta.get("model", ""),
            "layout_model": layout_meta.get("model", ""),
            **diagnostics,
        }
        Path(args.diagnostics).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.filtered_dump:
        filtered_entries = []
        for page_index, entry in enumerate(text_entries):
            excluded = set(diagnostics["pages"][page_index]["excluded_row_indices"])
            layout_page = None
            if layout_entries is not None and page_index < len(layout_entries):
                layout_page = layout_entries[page_index]
            text_overrides = _structure_text_overrides(entry, layout_page)
            old_to_new: dict[int, int] = {}
            filtered_rows = []
            for row_index, item in enumerate(entry.get("rows", [])):
                if row_index in excluded:
                    continue
                old_to_new[row_index] = len(filtered_rows)
                if row_index in text_overrides:
                    replacement_text, replacement_score = text_overrides[row_index]
                    _, _, poly = item
                    filtered_rows.append((replacement_text, replacement_score, poly))
                else:
                    filtered_rows.append(item)
            filtered = dict(entry)
            filtered["rows"] = filtered_rows
            filtered.pop("semantic_paragraphs", None)
            if args.actualtext:
                filtered["semantic_paragraphs"] = [
                    {
                        "text": paragraph["text"],
                        "row_indices": [old_to_new[index] for index in paragraph["row_indices"]],
                    }
                    for paragraph in paragraphs
                    if paragraph["page"] == page_index + 1
                    and all(index in old_to_new for index in paragraph["row_indices"])
                ]
            filtered_entries.append(filtered)
        dump_page_entries(
            filtered_entries,
            args.filtered_dump,
            source=text_meta.get("source", ""),
            model=text_meta.get("model", ""),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
