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

def calculate_font_size(font, text: str, w: float, h: float) -> float:
    """计算贴合文本框的字号，支持多行文本。

    策略：
    1. 估算文本在当前框内需要的行数
    2. 按行高算出初始字号
    3. 微调使每行尽量填满宽度
    4. 字号不超过框高
    """
    if not text:
        return max(1.0, h)
    if h > w:
        w, h = h, w
    min_size = 5.0
    if w <= 0 or h <= 0:
        return min_size

    def text_len(size: float) -> float:
        return font.text_length(text, fontsize=size)

    # 估算行数：在字号=h 时文本需要几行
    text_w_at_h = text_len(h)
    if text_w_at_h <= 0:
        return max(min_size, h)
    estimated_lines = max(1.0, text_w_at_h / w)

    # 按行数算出单行高度
    line_height = h / estimated_lines
    fontsize = max(min_size, round(line_height))

    # 微调：如果单行文字比框宽，缩小字号
    if text_len(fontsize) > w * estimated_lines * 1.1:
        while text_len(fontsize) > w * estimated_lines * 1.1 and fontsize > min_size:
            fontsize -= 0.5

    # 单行文本：字号不超过框高
    if estimated_lines <= 1.0:
        max_size = max(min_size, h)
        if fontsize > max_size:
            fontsize = max_size

    return max(min_size, fontsize)


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
    """推断 OCR 坐标到 PDF 页面坐标的缩放系数。"""
    if source_w and source_h:
        return page_rect.width / source_w, page_rect.height / source_h

    max_x = 0.0
    max_y = 0.0
    for _, _, poly in rows:
        for p in poly:
            try:
                max_x = max(max_x, float(p[0]))
                max_y = max(max_y, float(p[1]))
            except Exception:
                continue

    if max_x <= page_rect.width * 1.25 and max_y <= page_rect.height * 1.25:
        return 1.0, 1.0

    if max_x <= 0 or max_y <= 0:
        return 1.0, 1.0
    return page_rect.width / max_x, page_rect.height / max_y


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

        point = fitz.Point(x0, y1) * page.derotation_matrix
        page.insert_text(
            point,
            content,
            fontsize=fontsize,
            fontname="cjk",
            rotate=page_rotation,
            stroke_opacity=0,
            fill_opacity=0,
            render_mode=3,
        )
        page_inserted += 1

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
    total_pages = len(doc)

    cjk_normalize = not args.no_paddle_cjk_space_normalize

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
        print(f"  跳过页面: {skipped_pages}")
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
