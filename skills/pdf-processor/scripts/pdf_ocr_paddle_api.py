#!/usr/bin/env python3
"""
外部 PaddleOCR API 后端模块（异步任务模式）。

负责：
- Paddle API 异步任务提交（文件上传 → 轮询 → JSONL 结果下载）
- 支持 PP-OCRv5（纯 OCR）和 PaddleOCR-VL-1.5（版面分析 + OCR）
- JSONL 结果解析为分页 OCR 坐标
- 本地叠层生成双层 PDF
- 超 100 页自动分片提交

依赖：
- pdf_runtime: HTTP 工具、response_success
- pdf_ocr_layered: parse_paddle_predict_result, apply_page_entries_as_layered_pdf, extract_page_image_size
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

from pdf_runtime import (
    http_get_json,
    http_get_text,
    http_post_multipart,
)

from pdf_ocr_layered import (
    apply_page_entries_as_layered_pdf,
    extract_page_image_size,
    parse_paddle_predict_result,
)

from pdf_ocr_corrections import (
    apply_agent_corrections,
    archive_ocr_result,
    dump_page_entries,
    generate_readable_text,
    load_agent_corrections,
    load_page_entries,
)


# ---------- Paddle API 常量 ----------

PADDLE_JOB_MODEL = "PP-OCRv5"
PADDLE_VL_MODEL = "PaddleOCR-VL-1.5"
PADDLE_VL_MAX_PAGES = 9999
PADDLE_POLL_INTERVAL = 5
PADDLE_POLL_TIMEOUT = 1800

# VL-1.5 可识别的文本类 block_label
_VL_TEXT_LABELS = {
    "text", "doc_title", "title", "header", "footer",
    "list", "reference", "abstract", "catalog", "code",
    "table", "table_caption", "content",
    "paragraph_title", "section_title",
}
# number 类型只含页码，不纳入 OCR 文本层
_NUMBER_LABELS = {"number"}


# ---------- VL-1.5 内容清洗 ----------

def _clean_vl_text(text: str) -> str:
    """清洗 VL-1.5 block_content：去除 LaTeX/Markdown 标记，保留纯文本。"""
    if not text:
        return ""
    # $ \underline{\text{...}} $ → ...
    text = re.sub(
        r'\$?\s*\\underline\{\\text\{([^}]*)\}\}\s*\$?', r'\1', text,
    )
    # $$...$$ 块级数学 → 移除
    text = re.sub(r'\$\$[^$]*\$\$', '', text)
    # $...$ 行内数学 → 保留纯文字部分
    text = re.sub(r'\$([^$]*)\$', lambda m: m.group(1).strip(), text)
    # Markdown 标题标记
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Markdown 粗体/斜体
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    # 清理多余空白
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


# ---------- VL-1.5 块级结果转 rows ----------

def _convert_vl_blocks_to_rows(
    blocks: list[dict],
    page_width: float | None,
    page_height: float | None,
) -> list[tuple[str, float, list[list[float]]]]:
    """
    将 VL-1.5 parsing_res_list 转换为 rows 格式：
    [(text, score, poly4), ...]

    poly4: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
    """
    rows = []
    for block in blocks:
        label = block.get("block_label", "")
        # 文本类型纳入双层 PDF + MD 输出
        if label in _VL_TEXT_LABELS:
            is_number = False
        elif label in _NUMBER_LABELS:
            is_number = True
        else:
            continue

        content = _clean_vl_text(block.get("block_content", ""))
        if not content:
            continue

        bbox = block.get("block_bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
            continue

        try:
            x1, y1, x2, y2 = (float(v) for v in bbox[:4])
        except (ValueError, TypeError):
            continue

        poly4 = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
        # number 类型 score=0：双层 PDF 保留但 MD 输出时过滤
        score = 0.0 if is_number else 1.0
        rows.append((content, score, poly4))

    return rows


# ---------- VL-1.5 JSONL 解析 ----------

def parse_vl_jsonl_to_page_entries(jsonl_text: str) -> list[dict]:
    """
    解析 VL-1.5 的 JSONL 结果为分页 entries。

    VL-1.5 JSONL 结构：每行包含一个子批次（如 5 页），
    多行合并即为完整的分片结果。例如 100 页 = 20 行 × 5 页/行。
    """
    all_entries = []

    for line in jsonl_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        result = obj.get("result") if isinstance(obj, dict) else obj
        if not isinstance(result, dict):
            continue

        layout_results = result.get("layoutParsingResults")
        if not isinstance(layout_results, list):
            continue

        # 提取本行 dataInfo 中的页面尺寸（与 layoutParsingResults 一一对应）
        data_info = result.get("dataInfo")
        page_sizes = []
        if isinstance(data_info, dict):
            for p in data_info.get("pages", []):
                if isinstance(p, dict):
                    page_sizes.append((p.get("width"), p.get("height")))

        for idx, page_result in enumerate(layout_results):
            if not isinstance(page_result, dict):
                continue

            pruned = page_result.get("prunedResult")
            if isinstance(pruned, str):
                try:
                    pruned = json.loads(pruned)
                except json.JSONDecodeError:
                    pruned = None
            if not isinstance(pruned, dict):
                continue

            blocks = pruned.get("parsing_res_list", [])
            w, h = None, None

            # 优先从 prunedResult 取尺寸
            pw = pruned.get("width")
            ph = pruned.get("height")
            if pw and ph:
                w, h = float(pw), float(ph)

            # 回退到 dataInfo
            if (not w or not h) and idx < len(page_sizes):
                sw, sh = page_sizes[idx]
                if sw and sh:
                    w, h = float(sw), float(sh)

            rows = _convert_vl_blocks_to_rows(blocks, w, h)
            all_entries.append({"rows": rows, "width": w, "height": h})

    return all_entries


# ---------- 异步任务辅助 ----------

def _build_headers(api_key: str) -> dict:
    headers = {}
    if api_key:
        headers["Authorization"] = f"bearer {api_key}"
    return headers


def _build_optional_payload(model: str, args) -> dict:
    """根据模型和用户参数构建 optionalPayload。"""
    if model == PADDLE_VL_MODEL:
        payload = {
            "useDocOrientationClassify": getattr(args, "paddle_vl_doc_orientation", False),
            "useDocUnwarping": getattr(args, "paddle_vl_doc_unwarping", False),
            "useLayoutDetection": getattr(args, "paddle_vl_layout_detection", True),
            "useChartRecognition": getattr(args, "paddle_vl_chart_recognition", False),
            "layoutShapeMode": getattr(args, "paddle_vl_layout_shape_mode", "rect"),
        }
    else:
        # PP-OCRv5 payload: 默认关闭方向矫正和去畸变
        # 启用时 API 会在服务端预处理图片（矫正/去畸变），OCR 坐标对应预处理后的图片，
        # 但报告的图片尺寸不变，导致坐标偏移。关闭后坐标与原始图片一致，双层 PDF 对齐准确。
        payload = {
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
            "useTextlineOrientation": False,
        }

    # 合并用户通过 --paddle-api-extra-json 传入的额外参数
    extra_path = getattr(args, "paddle_api_extra_json", None)
    if extra_path:
        try:
            with open(extra_path, "r", encoding="utf-8") as f:
                extra = json.load(f)
            if isinstance(extra, dict):
                payload.update(extra)
        except Exception as exc:
            if not getattr(args, "quiet", False):
                print(f"  警告: 无法加载额外 JSON ({extra_path}): {exc}")

    return payload


def submit_paddle_job(
    endpoint: str,
    file_bytes: bytes,
    filename: str,
    api_key: str,
    timeout: int,
    model: str = PADDLE_JOB_MODEL,
    optional_payload: dict | None = None,
) -> str:
    """提交 PaddleOCR 异步任务，返回 jobId。"""
    headers = _build_headers(api_key)
    if optional_payload is None:
        optional_payload = _build_default_payload(model)
    fields = {
        "model": model,
        "optionalPayload": json.dumps(optional_payload),
    }
    files = {"file": (filename, file_bytes)}

    resp = http_post_multipart(endpoint, fields, files, headers, timeout)

    if not isinstance(resp, dict):
        raise RuntimeError(f"PaddleOCR API 返回格式不是 JSON: {resp}")

    data = resp.get("data") if isinstance(resp.get("data"), dict) else resp
    job_id = (data.get("jobId") or "").strip() if isinstance(data, dict) else ""
    if not job_id:
        raise RuntimeError(f"PaddleOCR API 未返回 jobId: {resp}")
    return job_id


def _build_default_payload(model: str) -> dict:
    """无 args 时根据模型构建默认 payload（供直接调用）。"""
    if model == PADDLE_VL_MODEL:
        return {
            "useDocOrientationClassify": True,
            "useDocUnwarping": True,
            "useLayoutDetection": True,
            "useChartRecognition": False,
            "layoutShapeMode": "rect",
        }
    return {
        "useDocOrientationClassify": True,
        "useDocUnwarping": True,
        "useTextlineOrientation": False,
    }


def poll_paddle_job(
    endpoint: str,
    job_id: str,
    api_key: str,
    timeout: int,
    poll_interval: int,
    poll_timeout: int,
    quiet: bool,
) -> str:
    """轮询任务状态，完成后返回 JSONL 下载 URL。"""
    headers = _build_headers(api_key)
    poll_url = f"{endpoint.rstrip('/')}/{job_id}"

    deadline = time.time() + max(1, poll_timeout)
    while True:
        resp = http_get_json(poll_url, headers=headers, timeout=timeout)
        data = resp.get("data") if isinstance(resp.get("data"), dict) else resp
        if not isinstance(data, dict):
            raise RuntimeError(f"PaddleOCR 轮询返回格式错误: {resp}")

        state = str(data.get("state", "")).lower()

        if state == "done":
            result_url = data.get("resultUrl")
            jsonl_url = ""
            if isinstance(result_url, dict):
                jsonl_url = str(result_url.get("jsonUrl") or "").strip()
            if not jsonl_url:
                raise RuntimeError(f"PaddleOCR 任务完成但未返回 jsonUrl: {data}")
            return jsonl_url

        if state == "failed":
            err_msg = data.get("errorMsg") or data.get("errorMessage") or state
            raise RuntimeError(f"PaddleOCR 任务失败: {err_msg}")

        if not quiet:
            progress = data.get("extractProgress")
            if isinstance(progress, dict):
                total = progress.get("totalPages", "?")
                extracted = progress.get("extractedPages", "?")
                print(f"  OCR 进度: {extracted}/{total} 页")
            else:
                print(f"  OCR 状态: {state}...")

        if time.time() >= deadline:
            raise RuntimeError(f"PaddleOCR 任务轮询超时（{poll_timeout}s）")

        time.sleep(max(1, poll_interval))


# ---------- PP-OCRv5 JSONL 解析（原逻辑） ----------

def parse_jsonl_to_page_entries(jsonl_text: str) -> list[dict]:
    """解析 PP-OCRv5 的 JSONL 文本为分页 entries。"""
    entries = []
    for line in jsonl_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        result = obj.get("result") if isinstance(obj, dict) else obj
        if not isinstance(result, dict):
            continue

        ocr_results = result.get("ocrResults") or result.get("ocrResult") or []

        # 从 dataInfo.pages 提取每页原始图片尺寸
        data_info = result.get("dataInfo")
        page_sizes = []
        if isinstance(data_info, dict):
            for p in data_info.get("pages", []):
                if isinstance(p, dict):
                    page_sizes.append((p.get("width"), p.get("height")))

        if isinstance(ocr_results, dict):
            ocr_results = [ocr_results]

        if not isinstance(ocr_results, list) or not ocr_results:
            rows = parse_paddle_predict_result(result)
            width, height = extract_page_image_size(result)
            if (not width or not height) and page_sizes:
                width, height = page_sizes[0]
            entries.append({"rows": rows, "width": width, "height": height})
            continue

        for idx, page_result in enumerate(ocr_results):
            if not isinstance(page_result, dict):
                continue
            pruned = page_result.get("prunedResult")
            if isinstance(pruned, str) and pruned.strip():
                try:
                    pruned = json.loads(pruned)
                except json.JSONDecodeError:
                    pruned = None
            candidate = pruned if isinstance(pruned, dict) else page_result
            rows = parse_paddle_predict_result(candidate)
            width, height = extract_page_image_size(candidate, page_result, result)
            # 回退到 dataInfo.pages[idx] 的尺寸
            if (not width or not height) and idx < len(page_sizes):
                dw, dh = page_sizes[idx]
                if dw and dh:
                    width, height = float(dw), float(dh)
            entries.append({"rows": rows, "width": width, "height": height})

    return entries


# ---------- 拍照件矫正 ----------

def extract_page_correction_info(
    jsonl_text: str,
    *,
    orientation_enabled: bool = False,
    unwarping_enabled: bool = False,
) -> list[dict]:
    """从 JSONL 提取每页的矫正信息（方向角度 + 预处理图 URL）。

    Args:
        orientation_enabled: 请求中是否启用了方向矫正。
        unwarping_enabled: 请求中是否启用了去畸变。

    Returns:
        [{"angle": int, "image_url": str, "needs_correction": bool}, ...]

    needs_correction 逻辑：
    - angle != 0: API 检测到方向偏转，需要替换（仅 orientation 启用时 API 会检测）
    - unwarping_enabled and img_url: 用户显式请求了去畸变，API 返回了预处理图
    API 默认对每页都返回 preprocessedImages URL（即使未做任何处理），
    所以不能仅靠 URL 存在就触发替换，否则会丢失压缩。
    """
    corrections = []
    for line in jsonl_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        result = obj.get("result") if isinstance(obj, dict) else obj
        if not isinstance(result, dict):
            continue

        pp_images = result.get("preprocessedImages") or []

        # PP-OCRv5: ocrResults 含 doc_preprocessor_res.angle
        # VL-1.5: layoutParsingResults，无 angle 但有 preprocessedImages
        ocr_results = result.get("ocrResults") or []
        layout_results = result.get("layoutParsingResults") or []
        page_results = ocr_results if ocr_results else layout_results

        for i, page in enumerate(page_results):
            if not isinstance(page, dict):
                continue
            angle = 0
            pruned = page.get("prunedResult")
            if isinstance(pruned, str):
                try:
                    pruned = json.loads(pruned)
                except json.JSONDecodeError:
                    pruned = None
            if isinstance(pruned, dict):
                doc_pp = pruned.get("doc_preprocessor_res", {})
                if isinstance(doc_pp, dict):
                    angle = int(doc_pp.get("angle", 0) or 0)

            img_url = str(pp_images[i]) if i < len(pp_images) else ""
            needs = angle != 0 or (unwarping_enabled and bool(img_url))
            corrections.append({
                "angle": angle,
                "image_url": img_url,
                "needs_correction": needs,
            })

    return corrections


def _apply_photo_correction(
    input_path: str,
    page_corrections: list[dict],
    quiet: bool = False,
) -> str | None:
    """下载预处理矫正图片，对需要矫正的页面替换为矫正图。

    对 angle != 0 的页面，下载 preprocessedImage 并替换该页图像。
    保留原文件不变，输出到临时文件。

    Returns:
        矫正后的临时 PDF 路径；若无页需要矫正则返回 None。
    """
    need_correction = [i for i, c in enumerate(page_corrections) if c.get("needs_correction")]
    if not need_correction:
        return None

    import fitz
    from pdf_runtime import http_get_bytes

    doc = fitz.open(input_path)
    corrected_any = False

    for pno, correction in enumerate(page_corrections):
        if not correction.get("needs_correction"):
            continue
        img_url = correction.get("image_url", "")
        if not img_url:
            continue

        angle = correction.get("angle", 0)
        if not quiet:
            print(f"  第 {pno + 1} 页: 方向矫正 {angle}°, 下载矫正图片...")

        try:
            img_bytes = http_get_bytes(img_url, timeout=60)
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp.write(img_bytes)
                img_path = tmp.name

            page = doc[pno]
            rect = page.rect
            # 90°/270° 旋转时图像尺寸互换（竖版↔横版）
            if angle in (90, 270):
                new_rect = fitz.Rect(0, 0, rect.height, rect.width)
            else:
                new_rect = fitz.Rect(0, 0, rect.width, rect.height)
            new_page = doc.new_page(pno=pno, width=new_rect.width, height=new_rect.height)
            new_page.insert_image(new_page.rect, filename=img_path)
            doc.delete_page(pno + 1)

            os.unlink(img_path)
            corrected_any = True
        except Exception as e:
            if not quiet:
                print(f"    警告: 矫正图片下载或替换失败: {e}")
            continue

    if not corrected_any:
        doc.close()
        return None

    corrected_path = tempfile.mktemp(suffix=".pdf", prefix="photo_corrected_")
    doc.subset_fonts()
    doc.save(
        corrected_path,
        garbage=4, clean=1, deflate=1, deflate_images=1, deflate_fonts=1,
        use_objstms=1, compression_effort=100,
    )
    doc.close()
    return corrected_path


# ---------- 智能解析分发 ----------

def _parse_jsonl(jsonl_text: str, model: str) -> list[dict]:
    """根据模型自动选择 PP-OCRv5 或 VL-1.5 解析器。"""
    if model == PADDLE_VL_MODEL:
        return parse_vl_jsonl_to_page_entries(jsonl_text)
    return parse_jsonl_to_page_entries(jsonl_text)


# ---------- 分片提交（处理 >100 页） ----------

def _split_pdf(input_path: str, max_pages: int) -> list[str]:
    """
    将 PDF 按页数上限拆分为临时文件列表。
    返回临时文件路径列表（调用方负责清理）。
    """
    import fitz

    doc = fitz.open(input_path)
    total = len(doc)
    if total <= max_pages:
        doc.close()
        return [input_path]

    paths = []
    for start in range(0, total, max_pages):
        end = min(start + max_pages, total)
        chunk = fitz.open()
        chunk.insert_pdf(doc, from_page=start, to_page=end - 1)
        tmp = tempfile.mktemp(suffix=".pdf", prefix=f"paddle_chunk_{start}_")
        chunk.save(tmp)
        chunk.close()
        paths.append(tmp)

    doc.close()
    return paths


def _submit_and_collect(
    input_path: str,
    endpoint: str,
    api_key: str,
    timeout: int,
    model: str,
    optional_payload: dict,
    poll_interval: int,
    poll_timeout: int,
    quiet: bool,
) -> tuple[list[dict], str]:
    """提交单个 PDF 文件并返回 (page_entries, jsonl_text)。"""
    file_bytes = Path(input_path).read_bytes()
    filename = Path(input_path).name

    if not quiet:
        print(f"  提交任务 ({len(file_bytes) / 1024 / 1024:.1f} MB, model={model})...")

    job_id = submit_paddle_job(
        endpoint, file_bytes, filename, api_key, timeout,
        model=model, optional_payload=optional_payload,
    )
    if not quiet:
        print(f"  任务已提交, jobId: {job_id}")

    jsonl_url = poll_paddle_job(
        endpoint, job_id, api_key, timeout,
        poll_interval, poll_timeout, quiet,
    )
    if not quiet:
        print("  下载 OCR 结果...")

    jsonl_text = http_get_text(jsonl_url, timeout=timeout)
    return _parse_jsonl(jsonl_text, model), jsonl_text


# ---------- Paddle API 后端执行 ----------

def run_paddle_api_backend(args):
    """
    执行 PaddleOCR API 后端（异步任务 + JSONL 解析 + 本地叠层）。

    支持 PP-OCRv5 和 PaddleOCR-VL-1.5 两种模型。
    VL-1.5 模式下自动处理 >100 页的分片提交。
    """
    if not args.paddle_api_endpoint:
        raise ValueError("使用 --backend paddle_api 时必须提供 --paddle-api-endpoint")

    import importlib
    pdf_ocr = importlib.import_module("pdf-ocr")
    run_local_ocrmypdf_backend = pdf_ocr.run_local_ocrmypdf_backend

    model = getattr(args, "paddle_model", PADDLE_JOB_MODEL) or PADDLE_JOB_MODEL
    optional_payload = _build_optional_payload(model, args)
    is_vl = model == PADDLE_VL_MODEL

    if not args.quiet:
        print("\nPaddleOCR API 后端参数:")
        print(f"  endpoint: {args.paddle_api_endpoint}")
        print(f"  model: {model}")
        if is_vl:
            print(f"  layout_detection: {optional_payload.get('useLayoutDetection')}")
            print(f"  chart_recognition: {optional_payload.get('useChartRecognition')}")
            print(f"  layout_shape_mode: {optional_payload.get('layoutShapeMode')}")
        print(f"  doc_orientation: {optional_payload.get('useDocOrientationClassify')}")
        print(f"  doc_unwarping: {optional_payload.get('useDocUnwarping')}")
        print(f"  timeout: {args.paddle_api_timeout}s")
        print(f"  fallback_local: {not args.no_paddle_fallback_local}")

    if args.dry_run:
        print("[DRY-RUN] PaddleOCR API 后端参数已输出，未实际请求。")
        args.backend_used = f"paddle_api({model})"
        return

    # --ocr-resume: 跳过 OCR，从 dump 文件加载
    resume_path = getattr(args, "ocr_resume", None)
    if resume_path:
        if not args.quiet:
            print(f"\n  从 dump 文件恢复 OCR 结果: {resume_path}")
        page_entries, meta = load_page_entries(resume_path)
        if not page_entries:
            raise RuntimeError(f"Dump 文件中无有效 OCR 结果: {resume_path}")
        if not args.quiet:
            print(f"  加载 {len(page_entries)} 页 OCR 结果 (model={meta.get('model', '?')})")

        # Agent 修正（from/to）
        corrections_file = getattr(args, "corrections_file", None)
        if corrections_file:
            agent_corrections = load_agent_corrections(corrections_file)
            if agent_corrections:
                page_entries, _ = apply_agent_corrections(
                    page_entries, agent_corrections, quiet=args.quiet,
                )

        layered_ok = apply_page_entries_as_layered_pdf(
            page_entries, args, source_name=f"PaddleOCR({meta.get('model', model)})",
        )
        if not layered_ok:
            raise RuntimeError("PaddleOCR 叠层失败")
        args.backend_used = f"paddle_api({meta.get('model', model)},layered)"
        return

    api_key = os.getenv(args.paddle_api_key_env, "").strip()
    if not api_key and args.paddle_api_key_env != "TOKEN":
        api_key = os.getenv("TOKEN", "").strip()

    try:
        # 检查页数，决定是否分片
        import fitz
        with fitz.open(args.input) as probe:
            total_pages = len(probe)

        max_per_job = PADDLE_VL_MAX_PAGES if is_vl else 9999
        needs_chunking = is_vl and total_pages > max_per_job

        if needs_chunking:
            if not args.quiet:
                print(f"  文档 {total_pages} 页超过 VL 限制 ({max_per_job} 页)，分片提交...")

            chunk_paths = _split_pdf(args.input, max_per_job)
            all_entries = []
            all_jsonl_texts = []

            try:
                for ci, chunk_path in enumerate(chunk_paths):
                    if not args.quiet:
                        pages_in_chunk = min(max_per_job, total_pages - ci * max_per_job)
                        print(f"\n  === 分片 {ci + 1}/{len(chunk_paths)} ({pages_in_chunk} 页) ===")

                    entries, jsonl_text = _submit_and_collect(
                        chunk_path,
                        args.paddle_api_endpoint,
                        api_key,
                        args.paddle_api_timeout,
                        model,
                        optional_payload,
                        PADDLE_POLL_INTERVAL,
                        PADDLE_POLL_TIMEOUT,
                        args.quiet,
                    )
                    all_entries.extend(entries)
                    all_jsonl_texts.append(jsonl_text)
            finally:
                # 清理临时文件（第一个可能是原文件）
                for p in chunk_paths[1:]:
                    try:
                        os.unlink(p)
                    except OSError:
                        pass

            page_entries = all_entries
            jsonl_text = "\n".join(all_jsonl_texts)
        else:
            page_entries, jsonl_text = _submit_and_collect(
                args.input,
                args.paddle_api_endpoint,
                api_key,
                args.paddle_api_timeout,
                model,
                optional_payload,
                PADDLE_POLL_INTERVAL,
                PADDLE_POLL_TIMEOUT,
                args.quiet,
            )

        if not page_entries:
            raise RuntimeError("PaddleOCR 结果中未解析到可叠层文字坐标")

        # 拍照件矫正：检测方向偏差，下载预处理矫正图替换 PDF 页面
        original_input = args.input
        if not getattr(args, "no_photo_correct", False):
            try:
                orientation_on = bool(optional_payload.get("useDocOrientationClassify"))
                unwarping_on = bool(optional_payload.get("useDocUnwarping"))
                correction_info = extract_page_correction_info(
                    jsonl_text,
                    orientation_enabled=orientation_on,
                    unwarping_enabled=unwarping_on,
                )
                corrected_count = sum(1 for c in correction_info if c.get("needs_correction"))
                if corrected_count > 0:
                    # 同步 page_entries 的尺寸为矫正图坐标空间（90/270° 时宽高互换）
                    for pno, ci in enumerate(correction_info):
                        if ci.get("needs_correction") and pno < len(page_entries):
                            angle = ci.get("angle", 0)
                            if angle in (90, 270):
                                e = page_entries[pno]
                                w, h = e.get("width"), e.get("height")
                                if w and h:
                                    e["width"], e["height"] = h, w
                    if not args.quiet:
                        rotation_count = sum(1 for c in correction_info if c.get("angle", 0) != 0)
                        unwarp_count = corrected_count - rotation_count
                        msg = f"\n  云端矫正: {corrected_count} 页需要矫正"
                        if rotation_count:
                            msg += f"（{rotation_count} 页方向旋转"
                            if unwarp_count:
                                msg += f", {unwarp_count} 页去畸变"
                            msg += "）"
                        elif unwarp_count:
                            msg += f"（{unwarp_count} 页去畸变）"
                        print(msg)
                corrected_input_path = _apply_photo_correction(
                    original_input, correction_info, quiet=args.quiet,
                )
                if corrected_input_path:
                    args.input = corrected_input_path
                    if not args.quiet:
                        print(f"  拍照矫正: 已使用矫正后 PDF (原文件未修改)")
            except Exception:
                pass  # 矫正失败不阻塞主流程

        # Archive: 保存 OCR 可读文本到 archive/ + 原文件同目录
        if not getattr(args, "no_archive", False):
            try:
                # 构造归档元数据：拍照矫正信息 + 预处理参数
                archive_extra = {}
                if corrected_input_path:
                    archive_extra["photo_correction"] = {
                        "corrected_pages": corrected_count,
                        "original_input": str(original_input),
                        "corrected_input": str(corrected_input_path),
                    }
                preprocess_meta = getattr(args, "preprocess_meta", None)
                if preprocess_meta:
                    archive_extra["preprocess_meta"] = preprocess_meta

                original_input_path = getattr(args, "original_input", None)
                archived_md, source_md = archive_ocr_result(
                    args.input, page_entries, model=model,
                    backend=f"paddle_api({model})",
                    extra_meta=archive_extra if archive_extra else None,
                    original_source_path=original_input_path,
                )
                if not args.quiet:
                    print(f"  Archive: {archived_md}")
                    print(f"  Markdown: {source_md}")
            except Exception:
                pass  # archive 失败不阻塞主流程

        # --ocr-dump: 保存 OCR 结果，不生成 PDF，等 agent 审查
        dump_path = getattr(args, "ocr_dump", None)
        if dump_path:
            dump_page_entries(page_entries, dump_path,
                              source=args.input, model=model)
            if not args.quiet:
                readable = generate_readable_text(page_entries)
                readable_path = dump_path.replace(".json", "_readable.txt")
                with open(readable_path, "w", encoding="utf-8") as f:
                    f.write(readable)
                print(f"\n  OCR 结果已保存（供 agent 审查）:")
                print(f"    完整数据: {dump_path}")
                print(f"    可读文本: {readable_path}")
                print(f"    共 {len(page_entries)} 页")
                print(f"\n  审查后请运行:")
                print(f"    pdf-ocr.py -i {args.input} -o {args.output} \\")
                print(f"      --ocr-resume {dump_path} --backend paddle_api \\")
                print(f"      --env-file {getattr(args, 'env_file', '')}")
            args.backend_used = f"paddle_api({model},dumped)"
            return

        # Agent 修正（from/to）
        corrections_file = getattr(args, "corrections_file", None)
        if corrections_file:
            agent_corrections = load_agent_corrections(corrections_file)
            if agent_corrections:
                page_entries, _ = apply_agent_corrections(
                    page_entries, agent_corrections, quiet=args.quiet,
                )

        layered_ok = apply_page_entries_as_layered_pdf(
            page_entries, args, source_name=f"PaddleOCR({model})",
        )
        if not layered_ok:
            raise RuntimeError("PaddleOCR 叠层失败")

        # 若使用了矫正后临时文件，从原始文件恢复时间戳
        if args.input != original_input:
            try:
                shutil.copystat(original_input, args.output)
            except Exception:
                pass

        args.backend_used = f"paddle_api({model},layered)"
        return

    except Exception as e:
        err_msg = str(e)

        if args.no_paddle_fallback_local:
            raise RuntimeError(f"PaddleOCR API 后端失败: {err_msg}")

        if not args.quiet:
            print(f"警告: PaddleOCR API 后端失败，回退到本地 ocrmypdf。原因: {err_msg}")
        run_local_ocrmypdf_backend(args)
