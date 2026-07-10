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
import os
import platform
import re
import shutil
import subprocess
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
    if polys is None:
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

# 经验系数：CJK 字体的视觉字号（em）与文字行外接框高度的比值。
# PyMuPDF 默认 "cjk" 字体的实际渲染高度约为字号的 0.72（西文 cap-height）至
# 1.0（全高），CJK 实测在 0.72-0.85 区间；0.78 是覆盖常见中文字体的稳健中值。
# 用这一比例由「bbox 高度」反推 fontsize，可避免 v2.6 及之前版本中
# 「字号=框高」导致文字溢出 bbox（baseline 落到框外）的对齐偏差。
_CAP_HEIGHT_RATIO_CJK = 0.78
# 同字号下相邻行之间的行高系数；CJK 实际行高约 1.15-1.25 倍字号。
_LINE_HEIGHT_RATIO_CJK = 1.20


def calculate_font_size(font, text: str, w: float, h: float) -> float:
    """计算贴合文本框的字号，支持单行 / 多行文本。

    v2.7 重写策略（修复 v2.6 之前「字号=框高」溢出 + 多行估算不可靠的问题）：
    1. **单行优先**：如果文本在 fontsize = h / _CAP_HEIGHT_RATIO_CJK 下能塞进
       bbox 宽度，直接用该字号 — baseline 落在 bbox 内，视觉对齐最稳。
    2. **多行回退**：若单行装不下，按 line_height = fontsize × _LINE_HEIGHT_RATIO_CJK
       反推可容纳行数，再用「能塞下全部文字」的最大字号二分搜索。
    3. 字号上限 = h / _CAP_HEIGHT_RATIO_CJK（防溢出），下限 5.0（防过小看不见）。
    """
    if not text:
        # 空文本不渲染，返回任意合理值即可
        return max(1.0, h)
    if w <= 0 or h <= 0:
        return 5.0

    min_size = 5.0
    # bbox 高度反推字号：单行情况下 fontsize ≈ h / 0.78
    # 这是 v2.7 的核心修正（旧版直接 fontsize=h，导致 baseline 越界）
    size_from_height = h / _CAP_HEIGHT_RATIO_CJK
    max_size = size_from_height

    def text_len(size: float) -> float:
        return font.text_length(text, fontsize=size)

    # Case 1：单行装得下，直接用「由框高反推」的字号
    single_line_width = text_len(size_from_height)
    if single_line_width <= w:
        return max(min_size, min(size_from_height, max_size))

    # Case 2：单行装不下，需要换行。按行高系数估算可容纳行数，
    # 然后二分搜索能塞下全部文本的最大字号。
    # 容许的最大行数（防止字号被压到过小）
    max_lines = max(1, int(h / (min_size * _LINE_HEIGHT_RATIO_CJK)))
    # 二分搜索：寻找最大 fontsize，使得 text 在 width 内分成 n 行（n<=max_lines）能塞下
    lo, hi = min_size, size_from_height
    best = min_size
    for _ in range(20):  # 20 次二分足以收敛到 0.5pt
        mid = (lo + hi) / 2.0
        if mid <= min_size:
            break
        line_h = mid * _LINE_HEIGHT_RATIO_CJK
        n_lines = max(1, int(h // line_h))
        if n_lines > max_lines:
            n_lines = max_lines
        # mid 字号下，单行容许的宽度
        per_line_capacity = w * n_lines
        if text_len(mid) <= per_line_capacity:
            best = mid
            lo = mid
        else:
            hi = mid
    return max(min_size, best)


def _split_text_to_lines(font, text: str, fontsize: float, max_width: float) -> list[str]:
    """v2.7 新增：按 max_width 把 text 拆成多行（贪婪换行）。

    优先按已有的空白断点换行；CJK 字符间允许任意位置断行。
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

    line_height = fontsize * _LINE_HEIGHT_RATIO_CJK
    # 看是否需要多行：text 在 fontsize 下的总宽 vs bbox 宽
    total_w = font.text_length(text, fontsize=fontsize)
    if total_w <= w + 0.5:
        # 单行
        point = fitz.Point(x0, y1)
        if apply_derotation:
            point = point * page.derotation_matrix
        page.insert_text(
            point, text,
            fontsize=fontsize, fontname=fontname,
            rotate=page_rotation,
            stroke_opacity=0, fill_opacity=0, render_mode=3,
        )
        return 1

    # 多行：拆分
    lines = _split_text_to_lines(font, text, fontsize, w)
    # 行数受 bbox 高度限制：最多 h / line_height 行；至少 1 行
    # （即使 bbox 高度容纳不下完整字号，也要写出第一行，避免标点等窄字
    #   在小 bbox 里被静默丢弃 — v2.7.1 修正）
    max_lines_by_height = max(1, int(round(h / line_height)))
    if len(lines) > max_lines_by_height:
        lines = lines[:max_lines_by_height]
    # 第一行 baseline 在 bbox 顶部 + ascender
    # bbox 顶部 = y1 - h；baseline ≈ top + fontsize
    first_baseline_y = (y1 - h) + fontsize
    written = 0
    for i, line in enumerate(lines):
        ly = first_baseline_y + i * line_height
        # 不超出 bbox 底部过多（fontsize × 0.5 的容差）
        # 但第一行始终写 — 否则窄标点会丢失（v2.7.1 修正）
        if i > 0 and ly > y1 + fontsize * 0.5:
            break
        point = fitz.Point(x0, ly)
        if apply_derotation:
            point = point * page.derotation_matrix
        page.insert_text(
            point, line,
            fontsize=fontsize, fontname=fontname,
            rotate=page_rotation,
            stroke_opacity=0, fill_opacity=0, render_mode=3,
        )
        written += 1
    return max(1, written)


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

    v2.7 改进：
    - 当 source_w/source_h 缺失时，使用所有 row 的 poly 宽高比 **中位数**
      （旧版只用单个 max_x/max_y，对孤立离群框很敏感）。
    - 当 OCR 坐标看起来已经是 PDF 页面坐标（max 值在页面尺寸 1.25x 以内）时，
      返回 1.0 而不是再算一次比率（避免浮点漂移）。
    """
    if source_w and source_h:
        return page_rect.width / source_w, page_rect.height / source_h

    max_x = 0.0
    max_y = 0.0
    width_ratios_x = []  # poly_x_range / page_width 候选
    height_ratios_y = []  # poly_y_range / page_height 候选
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
        # poly 自身宽高
        try:
            xs = [float(p[0]) for p in poly]
            ys = [float(p[1]) for p in poly]
            if xs and ys:
                rx = (max(xs) - min(xs)) / page_rect.width if page_rect.width else 0
                ry = (max(ys) - min(ys)) / page_rect.height if page_rect.height else 0
                if rx > 0:
                    width_ratios_x.append(rx)
                if ry > 0:
                    height_ratios_y.append(ry)
        except Exception:
            continue

    # 如果最大坐标已在页面尺寸 1.25x 内，视为「已是 PDF 坐标」
    if max_x <= page_rect.width * 1.25 and max_y <= page_rect.height * 1.25:
        return 1.0, 1.0

    if max_x <= 0 or max_y <= 0:
        return 1.0, 1.0

    # v2.7：优先用中位数 ratio 反推（抵御离群框噪声）
    if width_ratios_x and height_ratios_y:
        width_ratios_x.sort()
        height_ratios_y.sort()
        med_rx = width_ratios_x[len(width_ratios_x) // 2]
        med_ry = height_ratios_y[len(height_ratios_y) // 2]
        if 0 < med_rx < 1 and 0 < med_ry < 1:
            # poly 宽占页宽的比例 = med_rx → 整体 poly 宽 = med_rx × page_width
            # 但我们不知道 OCR 坐标空间的 absolute width，只能用 max 值估
            # 这里保留 max_x/max_y 估算法，但用 median ratio 做合理性校验
            scale_by_max_x = page_rect.width / max_x
            scale_by_max_y = page_rect.height / max_y
            # 若 max 估算法给出的 scale < 1/median_ratio 的 50%，说明 max 离群
            # 此时用 max 算会过度缩放，回退到 median 估算（假设 OCR 空间 = PDF 空间）
            if scale_by_max_x < 0.5 / max(med_rx, 0.01):
                return 1.0, 1.0
            return scale_by_max_x, scale_by_max_y

    return page_rect.width / max_x, page_rect.height / max_y


def assess_ocr_coordinate_health(rows, page_rect, scale_x: float, scale_y: float) -> dict:
    """v2.7 新增：评估 OCR 坐标空间与 PDF 页面空间的一致性。

    用于仿 DataInfra「坐标判定可证化」思路：当 OCR 端做了方向矫正 / 去畸变
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
        return {"fit_score": 0.0, "skew_warn": False, "scale_drift_warn": False,
                "out_of_page_ratio": 1.0, "n_rows": 0}

    n = len(rows)
    # 1) 检查 scale_x/scale_y 是否失衡
    if scale_x > 0 and scale_y > 0:
        ratio = scale_x / scale_y
        scale_drift = not (0.95 <= ratio <= 1.0526)  # ±5%
    else:
        scale_drift = True

    # 2) 检查 poly 主轴方向：取最长 poly 的 4 个顶点，看其 bbox 边长比对角线
    #    如果 polys 看起来「旋转过」，对角线远长于 bbox 长边
    skew_warn = False
    sample_polys = rows[: min(20, n)]
    diag_ratios = []
    for _, _, poly in sample_polys:
        try:
            xs = [float(p[0]) * scale_x for p in poly]
            ys = [float(p[1]) * scale_y for p in poly]
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            bw, bh = x1 - x0, y1 - y0
            # 用 poly 顶点之间的最长距离 vs bbox 对角线
            dists = []
            for i in range(len(xs)):
                for j in range(i + 1, len(xs)):
                    dists.append(((xs[i] - xs[j]) ** 2 + (ys[i] - ys[j]) ** 2) ** 0.5)
            max_d = max(dists) if dists else 0
            diag = (bw ** 2 + bh ** 2) ** 0.5
            if diag > 0:
                diag_ratios.append(max_d / diag)
        except Exception:
            continue
    # 若 poly 顶点之间的最长距 > bbox 对角线的 1.05 倍，说明 poly 是斜的（skewed）
    if diag_ratios:
        med = sorted(diag_ratios)[len(diag_ratios) // 2]
        if med > 1.05:
            skew_warn = True

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
    if skew_warn:
        score -= 0.4
    if scale_drift:
        score -= 0.3
    score -= min(0.4, out_ratio * 0.8)
    score = max(0.0, min(1.0, score))

    return {
        "fit_score": score,
        "skew_warn": skew_warn,
        "scale_drift_warn": scale_drift,
        "out_of_page_ratio": out_ratio,
        "n_rows": n,
    }


# ---------- 透明文字块插入（去重后的共享函数） ----------

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
) -> int:
    import fitz
    """
    向单个 PDF 页面插入透明文字块。

    Returns:
        插入的文本块数量。
    """
    font_inserted = False
    page_inserted = 0

    page.clean_contents()

    # v2.7：page.rotation == 0 时 derotation_matrix 是恒等矩阵，直接跳过点坐标变换
    # 避免浮点矩阵乘法引入的累积漂移（哪怕只有 1e-6 量级，叠到上千行也会偏）。
    apply_derotation = bool(page_rotation)

    for text, score, poly in rows:
        if score < min_score:
            continue
        content = text.strip()
        if not content:
            continue
        if cjk_normalize:
            content = normalize_cjk_spacing(content)
            if not content:
                continue

        xs = [p[0] * scale_x for p in poly]
        ys = [p[1] * scale_y for p in poly]

        x0 = min(xs)
        x1 = max(xs)
        y0 = min(ys)
        y1 = max(ys)

        w = max(1.0, x1 - x0)
        h = max(1.0, y1 - y0)
        fontsize = calculate_font_size(font, content, w, h)

        if not font_inserted:
            page.insert_font(fontname="cjk", fontbuffer=font.buffer)
            font_inserted = True

        # v2.7：多行排版 — text 在 bbox 宽度内自动换行，避免 insert_text
        # 单行限制导致文字溢出 bbox（这是「文字层与图片层不对齐」的最大根因）
        n_lines = _layout_text_into_bbox(
            page, font, content,
            x0=x0, y1=y1, w=w, h=h, fontsize=fontsize,
            fontname="cjk",
            page_rotation=page_rotation,
            apply_derotation=apply_derotation,
        )
        page_inserted += n_lines

    if not quiet:
        print(f"  第 {pno}/{total_pages} 页({source_name}): 新增 {page_inserted} 文本块")

    return page_inserted


# ---------- 叠层 PDF（分页 entries） ----------

def apply_page_entries_as_layered_pdf(page_entries: list[dict], args, source_name: str) -> bool:
    """将分页 OCR 结果叠层为双层 PDF。"""
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

    cjk_normalize = not args.no_paddle_cjk_space_normalize
    # v2.7: 健康度阈值（仿 DataInfra「坐标判定可证化」）
    # fit_score < 此值时，本页文字层不铺（让用户走 ocrmypdf 兜底）
    health_floor = float(getattr(args, "layered_health_floor", 0.5))

    for pno, page in enumerate(doc, start=1):
        if pno - 1 >= len(page_entries):
            continue

        if args.mode == "skip" and page_has_text_layer(page, args.paddle_skip_text_min_chars):
            skipped_pages += 1
            continue

        entry = page_entries[pno - 1]
        rows = entry.get("rows") or []
        if not rows:
            continue

        scale_x, scale_y = infer_page_scale(
            page.rect,
            rows,
            entry.get("width"),
            entry.get("height"),
        )

        # v2.7: 坐标健康度评估 — 仿 DataInfra「证不出就退化」
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
            continue

        page_rotation = int(page.rotation) if page.rotation else 0

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
        )

        if page_inserted > 0:
            inserted_pages += 1
            inserted_blocks += page_inserted

    if inserted_pages == 0:
        doc.close()
        src = Path(args.input).resolve()
        dst = Path(args.output).resolve()
        if src != dst:
            shutil.copy2(src, dst)
        if not args.quiet:
            print(f"{source_name} 已返回 OCR 结果，但无可叠层文本块，已原样输出。")
        return True

    try:
        doc.subset_fonts()
    except Exception:
        pass

    doc.save(
        args.output,
        garbage=4,
        clean=1, deflate=1, deflate_images=1, deflate_fonts=1,
        use_objstms=1, compression_effort=100,
    )
    doc.close()

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
    return True


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
