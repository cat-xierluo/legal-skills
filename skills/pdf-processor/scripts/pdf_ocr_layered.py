#!/usr/bin/env python3
"""
PDF 双层叠层核心模块。

将 OCR 结果（文字 + 坐标）叠入 PDF 透明文字层。
支持两种来源：
1. 本地 PaddleOCR predict 输出
2. 外部 API 返回的 payload

公共函数：
- normalize_cjk_spacing
- page_has_text_layer
- parse_paddle_predict_result
- calculate_font_size
- extract_page_image_size
- extract_page_entries_from_api_payload
- infer_page_scale
- apply_page_entries_as_layered_pdf
- apply_api_payload_as_layered_pdf
- save_output_from_api_payload
"""

from __future__ import annotations

import base64
import math
import os
import platform
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from pdf_runtime import http_get_bytes


# ---------- 通用 Payload 提取 ----------

def extract_payload(resp: dict) -> dict:
    """
    提取有效载荷。
    支持两类格式：
    1) 顶层直接放 output 字段
    2) `data` 字段中放 output 字段
    """
    result = resp.get("result")
    if isinstance(result, dict):
        return result
    if isinstance(result, list):
        return {"ocrResults": result}

    data = resp.get("data")
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        return {"ocrResults": data}
    return resp


# ---------- CJK 空格归一化 ----------

_CJK_SPACE_RE = re.compile(
    r"(?<=[㐀-䶿一-鿿豈-﫿　-〿＀-￯])"
    r"\s+"
    r"(?=[㐀-䶿一-鿿豈-﫿　-〿＀-￯])"
)
_CJK_BEFORE_PUNC_SPACE_RE = re.compile(r"\s+([，。！？；：、）》】」』）])")
_CJK_AFTER_OPEN_PUNC_SPACE_RE = re.compile(r"([（《【「『])\s+")


def normalize_cjk_spacing(text: str) -> str:
    """移除 CJK 字符间误插入空格，保留英文词间空格。"""
    if not text:
        return text
    text = _CJK_SPACE_RE.sub("", text)
    text = _CJK_BEFORE_PUNC_SPACE_RE.sub(r"\1", text)
    text = _CJK_AFTER_OPEN_PUNC_SPACE_RE.sub(r"\1", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


# ---------- 几何工具 ----------

def _poly_to_points(poly) -> list[list[float]]:
    """将多种 polygon 表示统一为 [[x,y], ...]。"""
    if poly is None:
        return []
    if not isinstance(poly, (list, tuple)):
        return []
    if not poly:
        return []

    first = poly[0]
    if isinstance(first, (list, tuple)):
        out = []
        for p in poly:
            if not isinstance(p, (list, tuple)) or len(p) < 2:
                continue
            try:
                out.append([float(p[0]), float(p[1])])
            except Exception:
                continue
        return out

    # 扁平数组: [x1,y1,x2,y2,...]
    out = []
    if len(poly) >= 8:
        for i in range(0, len(poly) - 1, 2):
            try:
                out.append([float(poly[i]), float(poly[i + 1])])
            except Exception:
                continue
    return out


def _as_float(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except Exception:
        return default


def _as_num_list(obj, length: int) -> list[float] | None:
    if not isinstance(obj, (list, tuple)) or len(obj) < length:
        return None
    nums = []
    for i in range(length):
        try:
            nums.append(float(obj[i]))
        except Exception:
            return None
    return nums


def _bbox_to_poly4(bbox) -> list[list[float]]:
    nums = _as_num_list(bbox, 4)
    if not nums:
        return []
    x0, y0, x1, y1 = nums
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


# ---------- 页面判断 ----------

def page_has_text_layer(page, min_chars: int) -> bool:
    """判断页面是否已有较明显文本层。"""
    text = page.get_text("text")
    return len(text.strip()) >= min_chars


# ---------- PaddleOCR 结果解析 ----------

def _parse_rec_dict(item: dict) -> list[tuple[str, float, list[list[float]]]]:
    texts = item.get("rec_texts")
    scores = item.get("rec_scores")
    polys = item.get("rec_polys")

    if texts is None and "texts" in item:
        texts = item.get("texts")
    if scores is None and "scores" in item:
        scores = item.get("scores")
    if not isinstance(polys, list) or not polys:
        polys = (
            item.get("dt_polys")
            or item.get("rec_boxes")
            or item.get("polys")
            or item.get("text_region")
        )

    if not isinstance(texts, list) or not isinstance(polys, list):
        return []

    if not isinstance(scores, list):
        scores = []

    parsed = []
    for i, text in enumerate(texts):
        poly = polys[i] if i < len(polys) else None
        # PP-StructureV3 / PP-OCRv5 有时返回 rec_boxes=[x0,y0,x1,y1]，
        # 与 dt_polys 的四点数组并存。先识别四值 bbox，再走通用 polygon 解析。
        if (
            isinstance(poly, (list, tuple))
            and len(poly) == 4
            and not isinstance(poly[0], (list, tuple))
        ):
            poly4 = _bbox_to_poly4(poly)
        else:
            poly4 = _poly_to_points(poly)
        if len(poly4) < 4:
            continue
        score = _as_float(scores[i], default=1.0) if i < len(scores) else 1.0
        parsed.append((str(text), score, poly4[:4]))
    return parsed


def parse_paddle_predict_result(result) -> list[tuple[str, float, list[list[float]]]]:
    """
    解析 PaddleOCR 输出，统一为: [(text, score, poly4), ...]
    poly4: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
    """
    if result is None:
        return []

    # 允许直接传 dict（常见于 API 的 prunedResult）
    if isinstance(result, dict):
        parsed = _parse_rec_dict(result)
        if parsed:
            return parsed

        for key in ("prunedResult", "ocrResult", "result", "data"):
            nested = result.get(key)
            nested_rows = parse_paddle_predict_result(nested)
            if nested_rows:
                return nested_rows
        return []

    # 新版 `predict` 常见结构: [ {rec_texts, rec_scores, rec_polys, ...} ]
    if isinstance(result, list) and result and isinstance(result[0], dict):
        rows = []
        for item in result:
            rows.extend(parse_paddle_predict_result(item))
        return rows

    # 旧版结构: [ [poly, (text, score)], ... ]
    if isinstance(result, list) and result and isinstance(result[0], list):
        blocks = result[0]
        parsed = []
        if isinstance(blocks, list):
            for block in blocks:
                if not isinstance(block, list) or len(block) < 2:
                    continue
                poly = block[0]
                rec = block[1]
                if not isinstance(rec, (list, tuple)) or len(rec) < 2:
                    continue
                text = str(rec[0])
                score = _as_float(rec[1], default=1.0)
                poly4 = _poly_to_points(poly)
                if len(poly4) >= 4:
                    parsed.append((text, score, poly4[:4]))
        return parsed

    return []


# ---------- 字号计算 ----------

_MIN_LAYER_FONT_SIZE = 0.5
_MIN_SINGLE_LINE_HORIZONTAL_SCALE = 0.5
_MAX_SINGLE_LINE_HORIZONTAL_SCALE = 2.0


class TextLayerIntegrityError(RuntimeError):
    """文字块无法在给定坐标框内完整排版。"""


def _font_vertical_metrics(font) -> tuple[float, float, float]:
    """返回 ascender、descender 和真实行高（均为相对字号的比例）。"""
    ascender = float(getattr(font, "ascender", 1.0) or 1.0)
    descender = float(getattr(font, "descender", -0.25) or -0.25)
    metric_height = ascender - descender
    if not math.isfinite(metric_height) or metric_height <= 0:
        ascender, descender, metric_height = 1.0, -0.25, 1.25
    return ascender, descender, metric_height


def calculate_font_size(font, text: str, w: float, h: float) -> float:
    """返回能在 bbox 中完整容纳全部文字的最大字号；无法容纳时返回 0。"""
    if not text or w <= 0 or h <= 0:
        return 0.0

    _, _, metric_height = _font_vertical_metrics(font)
    max_size = h / metric_height
    if max_size < _MIN_LAYER_FONT_SIZE:
        return 0.0

    def fits(size: float) -> bool:
        lines = _split_text_to_lines(font, text, size, w)
        if not lines or "".join(lines) != text:
            return False
        if any(font.text_length(line, fontsize=size) > w + 0.25 for line in lines):
            return False
        return len(lines) * metric_height * size <= h + 0.25

    if not fits(_MIN_LAYER_FONT_SIZE):
        return 0.0

    lo, hi = _MIN_LAYER_FONT_SIZE, max_size
    best = lo
    for _ in range(28):
        mid = (lo + hi) / 2.0
        if fits(mid):
            best = mid
            lo = mid
        else:
            hi = mid
    return best


def _split_text_to_lines(font, text: str, fontsize: float, max_width: float) -> list[str]:
    """v2.7 新增：按 max_width 把 text 拆成多行（贪婪换行）。

    逐字符贪婪换行；CJK 与西文都不会丢失字符。
    """
    if max_width <= 0 or fontsize <= 0:
        return [text]
    lines = []
    cur = ""
    cur_w = 0.0
    # 用 grapheme cluster 近似：逐字符迭代
    # 简单策略：逐字累加，超宽就换行
    for ch in text:
        ch_w = font.text_length(ch, fontsize=fontsize)
        if cur and cur_w + ch_w > max_width + 0.5:
            lines.append(cur)
            cur = ch
            cur_w = ch_w
        else:
            cur += ch
            cur_w += ch_w
    if cur:
        lines.append(cur)
    return lines


def _layout_text_into_bbox(
    page,
    font,
    text: str,
    x0: float,
    y1: float,
    w: float,
    h: float,
    fontsize: float,
    *,
    fontname: str = "cjk",
    page_rotation: int = 0,
    apply_derotation: bool = False,
) -> int:
    """v2.7 新增：把 text 按 bbox 多行排版到 page。

    PyMuPDF 的 `insert_text` 只写一行；多行场景下若不拆分，文字会溢出 bbox 宽度。
    本函数用 `_split_text_to_lines` 按宽度和 fontsize 拆分，逐行写入。

    Args:
        page: fitz.Page
        font: fitz.Font
        text: 待排版文本
        x0, y1: bbox 左下角（PDF 坐标）
        w, h: bbox 宽高
        fontsize: 计算好的字号
        page_rotation: 页面旋转
        apply_derotation: 是否需要 derotation_matrix 变换

    Returns:
        实际写入的行数
    """
    import fitz

    if not text or fontsize <= 0 or w <= 0 or h <= 0:
        raise TextLayerIntegrityError("空文字或无效文字框")

    ascender, _, metric_height = _font_vertical_metrics(font)
    line_height = fontsize * metric_height
    lines = _split_text_to_lines(font, text, fontsize, w)
    if not lines or "".join(lines) != text:
        raise TextLayerIntegrityError("换行后文字不完整")
    if any(font.text_length(line, fontsize=fontsize) > w + 0.25 for line in lines):
        raise TextLayerIntegrityError("文字行超出坐标框宽度")
    if len(lines) * line_height > h + 0.25:
        raise TextLayerIntegrityError("文字行超出坐标框高度")

    first_baseline_y = (y1 - h) + ascender * fontsize
    single_line_scale = 1.0
    if len(lines) == 1 and not apply_derotation and page_rotation == 0:
        natural_width = font.text_length(lines[0], fontsize=fontsize)
        if natural_width > 0:
            candidate_scale = w / natural_width
            if (
                math.isfinite(candidate_scale)
                and _MIN_SINGLE_LINE_HORIZONTAL_SCALE
                <= candidate_scale
                <= _MAX_SINGLE_LINE_HORIZONTAL_SCALE
            ):
                single_line_scale = candidate_scale

    written = 0
    for i, line in enumerate(lines):
        ly = first_baseline_y + i * line_height
        point = fitz.Point(x0, ly)
        if apply_derotation:
            point = point * page.derotation_matrix
        morph = None
        if single_line_scale != 1.0:
            # Paddle 返回的是整行检测框。字体按框高排版后，CJK 字体的自然字宽
            # 往往只覆盖检测框的 60%-90%，导致选择高亮横向明显偏短。
            # 单行、未旋转且缩放幅度可信时，以左侧基点做水平缩放贴合检测框。
            morph = (point, fitz.Matrix(single_line_scale, 1.0))
        page.insert_text(
            point, line,
            fontsize=fontsize, fontname=fontname,
            rotate=page_rotation,
            morph=morph,
            stroke_opacity=0, fill_opacity=0, render_mode=3,
        )
        written += 1
    if written != len(lines):
        raise TextLayerIntegrityError("文字写入行数不完整")
    return written


# ---------- 页面图像尺寸 ----------

def _pick_positive_number(value):
    try:
        num = float(value)
    except Exception:
        return None
    return num if num > 0 else None


def extract_page_image_size(*objs) -> tuple[float | None, float | None]:
    """从页面结果中提取 OCR 坐标空间的宽高。"""
    key_pairs = [
        ("imageWidth", "imageHeight"),
        ("image_width", "image_height"),
        ("imgW", "imgH"),
        ("img_w", "img_h"),
        ("pageWidth", "pageHeight"),
        ("page_width", "page_height"),
        ("width", "height"),
    ]
    shape_keys = (
        "imageShape",
        "image_shape",
        "inputImageShape",
        "input_image_shape",
        "shape",
    )

    for obj in objs:
        if not isinstance(obj, dict):
            continue
        for wk, hk in key_pairs:
            if wk in obj and hk in obj:
                w = _pick_positive_number(obj.get(wk))
                h = _pick_positive_number(obj.get(hk))
                if w and h:
                    return w, h

        for sk in shape_keys:
            shape = obj.get(sk)
            if isinstance(shape, (list, tuple)) and len(shape) >= 2:
                h = _pick_positive_number(shape[0])
                w = _pick_positive_number(shape[1])
                if w and h:
                    return w, h
            if isinstance(shape, dict):
                w = _pick_positive_number(shape.get("w") or shape.get("width"))
                h = _pick_positive_number(shape.get("h") or shape.get("height"))
                if w and h:
                    return w, h

    return None, None


# ---------- API payload -> 分页 entries ----------

def extract_page_entries_from_api_payload(payload: dict) -> list[dict]:
    """
    从外部 API 返回中提取分页 OCR 结果。
    返回: [{"rows": [...], "width": x, "height": y}, ...]
    """
    page_sources = None
    if isinstance(payload, list):
        page_sources = payload
    elif isinstance(payload, dict):
        for key in ("ocrResults", "layoutParsingResults", "pageResults", "pages", "results"):
            if isinstance(payload.get(key), list):
                page_sources = payload.get(key)
                break
        if page_sources is None and (
            isinstance(payload.get("prunedResult"), dict) or "rec_texts" in payload
        ):
            page_sources = [payload]

    if not isinstance(page_sources, list):
        return []

    entries = []
    for page_obj in page_sources:
        pruned = None
        if isinstance(page_obj, dict):
            pruned = page_obj.get("prunedResult")

        candidate = pruned if isinstance(pruned, dict) else page_obj
        rows = parse_paddle_predict_result(candidate)
        width, height = extract_page_image_size(page_obj, pruned)
        entries.append(
            {
                "rows": rows,
                "width": width,
                "height": height,
            }
        )
    return entries


# ---------- 缩放推断 ----------

def infer_page_scale(page_rect, rows, source_w, source_h) -> tuple[float, float]:
    """推断 OCR 坐标到 PDF 页面坐标的缩放系数。

    有明确 source_w/source_h 时使用确定性缩放；缺少坐标空间尺寸时，只有
    坐标本身可验证为 PDF 点单位才返回单位缩放，否则返回 (0, 0) 触发降级。
    """
    if source_w and source_h:
        return page_rect.width / source_w, page_rect.height / source_h

    max_x = 0.0
    max_y = 0.0
    for _, _, poly in rows:
        for p in poly:
            try:
                fx = float(p[0])
                fy = float(p[1])
                if fx > max_x:
                    max_x = fx
                if fy > max_y:
                    max_y = fy
            except Exception:
                continue

    # 如果最大坐标已在页面尺寸 1.25x 内，视为「已是 PDF 坐标」
    if max_x <= page_rect.width * 1.25 and max_y <= page_rect.height * 1.25:
        return 1.0, 1.0

    return 0.0, 0.0


def assess_ocr_coordinate_health(rows, page_rect, scale_x: float, scale_y: float) -> dict:
    """v2.7 新增：评估 OCR 坐标空间与 PDF 页面空间的一致性。

    用于坐标判定可证化思路：当 OCR 端做了方向矫正 / 去畸变
    （非线性变换），硬铺文字层会产生系统性偏移。本函数返回一个健康度报告，
    供调用方决定是否「证不出就退化」（不铺文字层、走 ocrmypdf 兜底）。

    Returns:
        {
            "fit_score": 0.0-1.0,            # 整体一致性得分
            "skew_warn": bool,                # 检测到斜切（poly 主轴与页面轴夹角 > 1°）
            "scale_drift_warn": bool,         # x/y 方向 scale 差异 > 5%（纵横比失真）
            "out_of_page_ratio": 0.0-1.0,     # 缩放后落在页面外的 poly 顶点比例
            "n_rows": int,
        }
    """
    if not rows:
        return {"fit_score": 0.0, "skew_warn": False, "median_skew_degrees": 0.0,
                "scale_drift_warn": False, "out_of_page_ratio": 1.0, "n_rows": 0}

    n = len(rows)
    # 1) 检查 scale_x/scale_y 是否失衡
    valid_scale = scale_x > 0 and scale_y > 0
    if valid_scale:
        ratio = scale_x / scale_y
        scale_drift = not (0.95 <= ratio <= 1.0526)  # ±5%
    else:
        scale_drift = True

    # 2) 检查 poly 主轴相对页面水平/垂直轴的夹角。
    # 旧实现比较“点间最长距离 / bbox 对角线”，该比值数学上不可能 > 1，
    # 导致 skew_warn 永远无法触发。
    skew_warn = False
    sample_polys = rows[: min(20, n)]
    skew_degrees = []
    for _, _, poly in sample_polys:
        try:
            points = [
                (float(p[0]) * scale_x, float(p[1]) * scale_y)
                for p in poly
            ]
            edges = []
            for i, point in enumerate(points):
                nxt = points[(i + 1) % len(points)]
                dx, dy = nxt[0] - point[0], nxt[1] - point[1]
                length = math.hypot(dx, dy)
                if length > 0:
                    edges.append((length, dx, dy))
            if edges:
                _, dx, dy = max(edges, key=lambda item: item[0])
                angle = abs(math.degrees(math.atan2(dy, dx))) % 90.0
                skew_degrees.append(min(angle, 90.0 - angle))
        except Exception:
            continue
    median_skew = 0.0
    if skew_degrees:
        median_skew = sorted(skew_degrees)[len(skew_degrees) // 2]
        skew_warn = median_skew > 1.0

    # 3) 检查落在页面外的顶点比例
    total_pts = 0
    out_pts = 0
    for _, _, poly in rows:
        for p in poly:
            try:
                px = float(p[0]) * scale_x
                py = float(p[1]) * scale_y
                total_pts += 1
                if px < -2 or px > page_rect.width + 2 or py < -2 or py > page_rect.height + 2:
                    out_pts += 1
            except Exception:
                continue
    out_ratio = (out_pts / total_pts) if total_pts else 1.0

    # 综合得分
    score = 1.0
    if not valid_scale:
        score = 0.0
    if skew_warn:
        score -= 0.4
    if scale_drift:
        score -= 0.3
    score -= min(0.4, out_ratio * 0.8)
    score = max(0.0, min(1.0, score))

    return {
        "fit_score": score,
        "skew_warn": skew_warn,
        "median_skew_degrees": median_skew,
        "scale_drift_warn": scale_drift,
        "out_of_page_ratio": out_ratio,
        "n_rows": n,
    }


# ---------- 透明文字块插入（去重后的共享函数） ----------

def _actual_text_prefix(text: str) -> bytes:
    """生成 PDF marked-content 的 UTF-16BE /ActualText 前缀。"""
    encoded = (b"\xfe\xff" + text.encode("utf-16-be")).hex().upper().encode("ascii")
    return b"/Span << /ActualText <" + encoded + b">>> BDC\n"


def _apply_semantic_actual_text(
    page,
    row_content_xrefs: dict[int, list[int]],
    row_texts: dict[int, str],
    semantic_paragraphs: list[dict],
) -> int:
    """为连续行流添加 /ActualText；不改变行级字形与选区坐标。"""
    if not semantic_paragraphs:
        return 0

    doc = page.parent
    page_contents = list(page.get_contents())
    content_positions = {xref: index for index, xref in enumerate(page_contents)}
    used_xrefs: set[int] = set()
    applied = 0

    for paragraph in semantic_paragraphs:
        if not isinstance(paragraph, dict):
            continue
        text = str(paragraph.get("text") or "").strip()
        row_indices = paragraph.get("row_indices")
        if not text or not isinstance(row_indices, list) or not row_indices:
            continue
        try:
            indices = [int(value) for value in row_indices]
        except (TypeError, ValueError):
            continue
        if any(index not in row_content_xrefs or index not in row_texts for index in indices):
            continue
        physical_text = "".join(row_texts[index] for index in indices)
        if re.sub(r"\s+", "", physical_text) != re.sub(r"\s+", "", text):
            continue

        xrefs = [xref for index in indices for xref in row_content_xrefs[index]]
        if not xrefs or any(xref in used_xrefs or xref not in content_positions for xref in xrefs):
            continue
        positions = [content_positions[xref] for xref in xrefs]
        if positions != list(range(min(positions), max(positions) + 1)):
            continue

        first_xref, last_xref = xrefs[0], xrefs[-1]
        first_stream = doc.xref_stream(first_xref)
        if first_xref == last_xref:
            doc.update_stream(
                first_xref,
                _actual_text_prefix(text) + first_stream + b"\nEMC",
            )
        else:
            doc.update_stream(first_xref, _actual_text_prefix(text) + first_stream)
            doc.update_stream(last_xref, doc.xref_stream(last_xref) + b"\nEMC")
        used_xrefs.update(xrefs)
        applied += 1

    return applied


def _insert_text_blocks(
    page,
    font,
    rows: list[tuple[str, float, list[list[float]]]],
    *,
    scale_x: float,
    scale_y: float,
    min_score: float,
    cjk_normalize: bool,
    page_rotation: int,
    source_name: str,
    pno: int,
    total_pages: int,
    quiet: bool,
    semantic_paragraphs: list[dict] | None = None,
) -> int:
    import fitz
    """
    向单个 PDF 页面插入透明文字块。

    Returns:
        插入的文本块数量。
    """
    page_inserted = 0
    plans = []

    # v2.7：page.rotation == 0 时 derotation_matrix 是恒等矩阵，直接跳过点坐标变换
    # 避免浮点矩阵乘法引入的累积漂移（哪怕只有 1e-6 量级，叠到上千行也会偏）。
    apply_derotation = bool(page_rotation)

    for row_index, (text, score, poly) in enumerate(rows, start=1):
        if score < min_score:
            continue
        content = text.strip()
        if not content:
            continue
        if cjk_normalize:
            content = normalize_cjk_spacing(content)
            if not content:
                continue
        # API 的 block 文本可能含换行；坐标框内由本模块重新排版，先将控制换行
        # 规范为空格，避免 insert_text 把单个计划行再次隐式拆开。
        content = re.sub(r"[\r\n]+", " ", content).strip()
        if not content:
            continue

        try:
            xs = [float(p[0]) * scale_x for p in poly]
            ys = [float(p[1]) * scale_y for p in poly]
        except Exception as exc:
            raise TextLayerIntegrityError(f"第 {row_index} 个文字块坐标无效") from exc
        if len(xs) < 4 or not all(math.isfinite(v) for v in [*xs, *ys]):
            raise TextLayerIntegrityError(f"第 {row_index} 个文字块坐标不完整")

        x0 = min(xs)
        x1 = max(xs)
        y0 = min(ys)
        y1 = max(ys)

        w = x1 - x0
        h = y1 - y0
        if w <= 0 or h <= 0:
            raise TextLayerIntegrityError(f"第 {row_index} 个文字块边界无效")
        fontsize = calculate_font_size(font, content, w, h)
        if fontsize <= 0:
            raise TextLayerIntegrityError(
                f"第 {row_index} 个文字块无法完整放入坐标框"
            )
        plans.append((row_index - 1, content, x0, y1, w, h, fontsize))

    if not plans:
        return 0

    # 所有文字块预检通过后再修改页面，避免出现“前半页写入、后半页失败”。
    page.insert_font(fontname="cjk", fontbuffer=font.buffer)

    row_content_xrefs: dict[int, list[int]] = {}
    row_texts: dict[int, str] = {}
    for source_row_index, content, x0, y1, w, h, fontsize in plans:
        before_xrefs = set(page.get_contents())
        n_lines = _layout_text_into_bbox(
            page, font, content,
            x0=x0, y1=y1, w=w, h=h, fontsize=fontsize,
            fontname="cjk",
            page_rotation=page_rotation,
            apply_derotation=apply_derotation,
        )
        row_content_xrefs[source_row_index] = [
            xref for xref in page.get_contents() if xref not in before_xrefs
        ]
        row_texts[source_row_index] = content
        page_inserted += n_lines

    actual_text_count = _apply_semantic_actual_text(
        page,
        row_content_xrefs,
        row_texts,
        semantic_paragraphs or [],
    )
    if semantic_paragraphs and actual_text_count != len(semantic_paragraphs):
        raise TextLayerIntegrityError(
            f"ActualText 自然段写入不完整（{actual_text_count}/{len(semantic_paragraphs)}）"
        )

    if not quiet:
        print(f"  第 {pno}/{total_pages} 页({source_name}): 新增 {page_inserted} 文本块")
        if semantic_paragraphs:
            print(f"    ActualText 自然段: {actual_text_count}/{len(semantic_paragraphs)}")

    return page_inserted


# ---------- 叠层 PDF（分页 entries） ----------

def apply_page_entries_as_layered_pdf(page_entries: list[dict], args, source_name: str) -> bool:
    """将分页 OCR 结果事务式叠层为双层 PDF。

    任一页缺失、坐标不健康、文字被过滤为空或无法完整排版时都返回 False，
    且不写出部分成功文件；调用方可据此回退到 ocrmypdf。
    """
    if not page_entries:
        return False

    import fitz

    doc = fitz.open(args.input)
    font = fitz.Font("cjk")

    inserted_pages = 0
    inserted_blocks = 0
    skipped_pages = 0
    degraded_pages = 0  # v2.7: 健康度低、被降级（不铺文字层）的页数
    total_pages = len(doc)
    health_log = []  # v2.7: 每页健康度评估结果（用于诊断）
    failure_reason = None

    def finish(success: bool, reason: str | None = None) -> bool:
        result = {
            "success": success,
            "reason": reason,
            "total_pages": total_pages,
            "entry_pages": len(page_entries),
            "inserted_pages": inserted_pages,
            "inserted_blocks": inserted_blocks,
            "skipped_pages": skipped_pages,
            "degraded_pages": degraded_pages,
            "health_log": health_log,
        }
        setattr(args, "layered_result", result)
        if not success and not args.quiet:
            print(f"  {source_name} 叠层未写出：{reason}")
        return success

    cjk_normalize = not args.no_paddle_cjk_space_normalize
    # v2.7: 健康度阈值（坐标判定可证化）
    # fit_score < 此值时，本页文字层不铺（让用户走 ocrmypdf 兜底）
    health_floor = float(getattr(args, "layered_health_floor", 0.5))

    if len(page_entries) != total_pages:
        doc.close()
        return finish(
            False,
            f"OCR 结果页数与 PDF 不一致（{len(page_entries)}/{total_pages}）",
        )

    if args.mode in {"redo", "force"}:
        conflict_pages = [
            pno
            for pno, page in enumerate(doc, start=1)
            if page_has_text_layer(page, 1)
        ]
        if conflict_pages:
            doc.close()
            preview = ",".join(str(x) for x in conflict_pages[:10])
            suffix = "…" if len(conflict_pages) > 10 else ""
            return finish(
                False,
                f"{args.mode} 模式无法安全移除既有文字层（页 {preview}{suffix}），需回退 ocrmypdf",
            )

    for pno, page in enumerate(doc, start=1):
        if args.mode == "skip" and page_has_text_layer(page, args.paddle_skip_text_min_chars):
            skipped_pages += 1
            continue

        entry = page_entries[pno - 1]
        rows = entry.get("rows") or []
        if not rows:
            failure_reason = f"第 {pno} 页没有可验证的 OCR 坐标结果"
            break

        source_w, source_h = entry.get("width"), entry.get("height")
        if not source_w or not source_h:
            coords = [
                (float(point[0]), float(point[1]))
                for _, _, poly in rows
                for point in poly
                if len(point) >= 2
            ]
            max_x = max((point[0] for point in coords), default=0.0)
            max_y = max((point[1] for point in coords), default=0.0)
            if max_x > page.rect.width * 1.25 or max_y > page.rect.height * 1.25:
                failure_reason = (
                    f"第 {pno} 页缺少 OCR 坐标空间宽高，且坐标不是可验证的 PDF 点单位"
                )
                break

        scale_x, scale_y = infer_page_scale(
            page.rect,
            rows,
            source_w,
            source_h,
        )

        # v2.7: 坐标健康度评估 — 证不出就退化
        health = assess_ocr_coordinate_health(rows, page.rect, scale_x, scale_y)
        health_log.append({"page": pno, **health})
        if health["fit_score"] < health_floor and not getattr(args, "layered_force", False):
            degraded_pages += 1
            if not args.quiet:
                print(
                    f"  第 {pno}/{total_pages} 页({source_name}): 坐标健康度低 "
                    f"(fit={health['fit_score']:.2f}, skew={health['skew_warn']}, "
                    f"drift={health['scale_drift_warn']}, oob={health['out_of_page_ratio']:.0%}); "
                    f"已跳过文字层（建议改走 ocrmypdf 兜底）"
                )
            failure_reason = f"第 {pno} 页坐标健康度不足（fit={health['fit_score']:.2f}）"
            break

        page_rotation = int(page.rotation) if page.rotation else 0

        try:
            page_inserted = _insert_text_blocks(
                page,
                font,
                rows,
                scale_x=scale_x,
                scale_y=scale_y,
                min_score=args.paddle_min_score,
                cjk_normalize=cjk_normalize,
                page_rotation=page_rotation,
                source_name=source_name,
                pno=pno,
                total_pages=total_pages,
                quiet=args.quiet,
                semantic_paragraphs=entry.get("semantic_paragraphs") or [],
            )
        except TextLayerIntegrityError as exc:
            failure_reason = f"第 {pno} 页文字层不完整：{exc}"
            break

        if page_inserted > 0:
            inserted_pages += 1
            inserted_blocks += page_inserted
        else:
            failure_reason = f"第 {pno} 页 OCR 结果经阈值过滤后为空"
            break

    if failure_reason:
        doc.close()
        return finish(False, failure_reason)

    if inserted_pages + skipped_pages != total_pages:
        doc.close()
        return finish(False, "并非所有页面都已插入或按 skip 规则验证跳过")

    try:
        doc.subset_fonts()
    except Exception:
        pass

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = tempfile.NamedTemporaryFile(
        delete=False,
        dir=output_path.parent,
        prefix=f".{output_path.stem}.",
        suffix=".tmp.pdf",
    )
    temp_output = Path(temp_file.name)
    temp_file.close()
    try:
        doc.save(
            temp_output,
            garbage=4,
            clean=1, deflate=1, deflate_images=1, deflate_fonts=1,
            use_objstms=1, compression_effort=100,
        )
        doc.close()
        os.replace(temp_output, output_path)
    except Exception:
        doc.close()
        try:
            temp_output.unlink(missing_ok=True)
        except Exception:
            pass
        raise

    # 保留原文件时间戳（创建时间 + 修改时间）
    try:
        src_stat = Path(args.input).stat()
        mtime = src_stat.st_mtime
        birthtime = getattr(src_stat, "st_birthtime", mtime)
        os.utime(args.output, (mtime, mtime))
        if platform.system() == "Darwin":
            try:
                dt = datetime.fromtimestamp(birthtime)
                date_str = dt.strftime("%m/%d/%Y %H:%M:%S")
                subprocess.run(
                    ["SetFile", "-d", date_str, str(args.output)],
                    check=True, capture_output=True,
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
    except Exception:
        pass

    if not args.quiet:
        print(f"\n{source_name} OCR 叠层完成:")
        print(f"  新增页面: {inserted_pages}/{total_pages}")
        print(f"  新增文本块: {inserted_blocks}")
        print(f"  跳过页面（已有文本层）: {skipped_pages}")
        if degraded_pages:
            print(f"  降级页面（坐标健康度低）: {degraded_pages}")
            print(f"  → 这些页建议改走 ocrmypdf 兜底以保证搜索可用性")
    return finish(True)


# ---------- 叠层 PDF（API payload） ----------

def apply_api_payload_as_layered_pdf(payload: dict, args) -> bool:
    """将 API 返回的 OCR 结果叠层为双层 PDF。"""
    page_entries = extract_page_entries_from_api_payload(payload)
    return apply_page_entries_as_layered_pdf(page_entries, args, source_name="API")


# ---------- 保存 API 输出 PDF ----------

def save_output_from_api_payload(payload: dict, output_path: Path, timeout: int):
    """从 API payload 保存输出 PDF。"""
    if "output_pdf_base64" in payload:
        raw = base64.b64decode(payload["output_pdf_base64"])
        output_path.write_bytes(raw)
        return

    if "output_pdf_url" in payload:
        raw = http_get_bytes(payload["output_pdf_url"], timeout=timeout)
        output_path.write_bytes(raw)
        return

    if "output_pdf_path" in payload:
        p = Path(payload["output_pdf_path"])
        if not p.exists():
            raise RuntimeError(f"API 返回的输出路径不存在: {p}")
        shutil.copy2(p, output_path)
        return

    raise RuntimeError(
        "API 响应未直接返回 PDF。可继续尝试解析 OCR 结果并本地叠层。"
    )
