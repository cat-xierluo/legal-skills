#!/usr/bin/env python3
"""RapidOCR 本地双层后端。

以本地 onnx 推理（RapidOCR，默认随包的 PP-OCRv4/v5 mobile 检测+识别模型）
逐页识别整页文字，复用 pdf_ocr_layered 的透明文字层叠层，生成可搜索双层 PDF。

定位：中文扫描件的本地高识别质量兜底。相较 tesseract（ocrmypdf）路径，
RapidOCR 的中文行级识别与坐标明显更稳，且全程不出本机，适合敏感材料
--local-only 场景；作为 auto 链的本地第一优先（未安装时仍回退 ocrmypdf）。

依赖（可选）：
    pip install rapidocr              # 推荐：新版统一包（默认 onnxruntime 引擎）
    # 或
    pip install rapidocr_onnxruntime  # 经典包，接口等价
"""

from __future__ import annotations

import shutil
from pathlib import Path

from pdf_runtime import print_dependency_help
from pdf_ocr_layered import _insert_text_blocks, page_has_text_layer

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except Exception:
    HAS_PYMUPDF = False

try:
    import numpy as np
    HAS_NUMPY = True
except Exception:
    HAS_NUMPY = False

RapidOCR = None
RAPID_FLAVOR: str | None = None  # "rapidocr" / "rapidocr_onnxruntime"
_RAPID_IMPORT_TRIED = False


def _try_import_rapidocr() -> bool:
    global RapidOCR, RAPID_FLAVOR, _RAPID_IMPORT_TRIED
    if _RAPID_IMPORT_TRIED:
        return RapidOCR is not None
    _RAPID_IMPORT_TRIED = True
    try:
        from rapidocr import RapidOCR as _RapidOCR  # 新统一包

        RapidOCR = _RapidOCR
        RAPID_FLAVOR = "rapidocr"
        return True
    except Exception:
        pass
    try:
        from rapidocr_onnxruntime import RapidOCR as _RapidOCR  # 经典包

        RapidOCR = _RapidOCR
        RAPID_FLAVOR = "rapidocr_onnxruntime"
        return True
    except Exception:
        return False


def get_rapid_missing_dependencies() -> list[str]:
    """检测 RapidOCR 后端缺失的 Python 依赖。"""
    missing = []
    if not HAS_PYMUPDF:
        missing.append("pymupdf")
    if not HAS_NUMPY:
        missing.append("numpy")
    if not _try_import_rapidocr():
        missing.append("rapidocr")
    return missing


def is_rapidocr_available() -> bool:
    """本地 RapidOCR 后端是否可用（不含首次模型加载）。"""
    return not get_rapid_missing_dependencies()


def ensure_rapidocr_available() -> bool:
    missing = get_rapid_missing_dependencies()
    if missing:
        print_dependency_help(
            "本地 RapidOCR 双层引擎",
            missing_python=missing,
            install_commands=[
                "pip install rapidocr pymupdf numpy",
            ],
            extra_notes=[
                "未安装 RapidOCR 时，auto/local-only 会继续回退 ocrmypdf。",
                "首次运行会自动下载检测/识别 onnx 模型（仅一次）。",
            ],
        )
        return False
    return True


def _poly_to_points(poly) -> list[list[float]]:
    """把任意 box 表示（(4,2) 数组 / 8 扁平数 / list）统一为 4 角点。"""
    try:
        arr = np.asarray(poly, dtype=float).reshape(-1, 2)
    except Exception:
        return []
    if len(arr) < 4:
        return []
    return [[float(x), float(y)] for x, y in arr[:4]]


def _rapid_rows_from_attrs(obj) -> list[tuple[str, float, list[list[float]]]] | None:
    """rapidocr 2.x/3.x 的 OCRResult 对象：boxes / txts / scores 属性。"""
    boxes = getattr(obj, "boxes", None)
    txts = getattr(obj, "txts", None)
    if txts is None:
        txts = getattr(obj, "texts", None)
    if boxes is None or txts is None:
        return None
    scores = getattr(obj, "scores", None)
    try:
        n = len(txts)
    except TypeError:
        return None
    if n == 0 or len(boxes) < n:
        return None
    rows: list[tuple[str, float, list[list[float]]]] = []
    for i in range(n):
        text = str(txts[i]).strip()
        if not text:
            continue
        score = 1.0
        if scores is not None and i < len(scores):
            try:
                score = float(scores[i])
            except (TypeError, ValueError):
                score = 1.0
        poly = _poly_to_points(boxes[i])
        if len(poly) == 4:
            rows.append((text, score, poly))
    return rows


def parse_rapidocr_result(result) -> list[tuple[str, float, list[list[float]]]]:
    """
    解析 RapidOCR 各版本输出，统一为: [(text, score, poly4), ...]
    poly4: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
    """
    if result is None:
        return []

    # 经典包 rapidocr_onnxruntime 1.x: (result, elapse) 二元组
    if isinstance(result, tuple):
        return parse_rapidocr_result(result[0] if result else None)

    # 新包 OCRResult：属性形式
    attr_rows = _rapid_rows_from_attrs(result)
    if attr_rows is not None:
        return attr_rows

    # dict 形式（部分版本/中间结构）
    if isinstance(result, dict):
        for key in ("res", "data", "result"):
            nested = result.get(key)
            if nested is not None and nested is not result:
                parsed = parse_rapidocr_result(nested)
                if parsed:
                    return parsed
        attr_rows = _rapid_rows_from_attrs(result)
        if attr_rows is not None:
            return attr_rows
        return []

    if not isinstance(result, list) or not result:
        return []

    # 列表形式：每行 [box, text, score]（新版扁平）或 [box, (text, score)]（旧版）
    rows: list[tuple[str, float, list[list[float]]]] = []
    for block in result:
        if not isinstance(block, (list, tuple)) or len(block) < 2:
            continue
        poly_raw = block[0]
        rec = block[1]
        if isinstance(rec, (list, tuple)) and len(rec) >= 2:
            # 旧版 [box, (text, score)]
            text = str(rec[0]).strip()
            try:
                score = float(rec[1])
            except (TypeError, ValueError):
                score = 1.0
        elif len(block) >= 3 and isinstance(block[2], (int, float, str)):
            # 新版扁平 [box, text, score]
            text = str(rec).strip()
            try:
                score = float(block[2])
            except (TypeError, ValueError):
                score = 1.0
        else:
            continue
        if not text:
            continue
        poly = _poly_to_points(poly_raw)
        if len(poly) == 4:
            rows.append((text, score, poly))
    return rows


def build_rapid_engine():
    """构造 RapidOCR 引擎（默认模型即可获得稳定中文行级结果）。"""
    if not _try_import_rapidocr():
        raise RuntimeError("RapidOCR 未安装")
    return RapidOCR()


def run_rapidocr_local_backend(args, fallback_backend=None):
    """RapidOCR + PyMuPDF 透明文字层：本地双层 PDF 生成。"""
    if not ensure_rapidocr_available():
        raise RuntimeError("本地 RapidOCR 双层引擎不可用")

    dpi = int(getattr(args, "rapid_dpi", 0) or 300)
    min_score = float(getattr(args, "rapid_min_score", 0) or 0.5)
    skip_min_chars = int(getattr(args, "rapid_skip_text_min_chars", 1) or 1)

    with fitz.open(args.input) as probe_doc:
        total_pages = len(probe_doc)
        has_text_pages = [
            i + 1
            for i, page in enumerate(probe_doc)
            if page_has_text_layer(page, skip_min_chars)
        ]

    if not args.quiet:
        print("\n本地 RapidOCR 双层后端参数:")
        print(f"  engine: {RAPID_FLAVOR}")
        print(f"  dpi: {dpi}")
        print(f"  min_score: {min_score}")
        print(f"  skip_text_min_chars: {skip_min_chars}")
        print(f"  pages: {total_pages}（已有文字层 {len(has_text_pages)} 页）")

    if args.dry_run:
        print("[DRY-RUN] 本地 RapidOCR 双层后端参数已输出，未实际执行。")
        args.backend_used = "rapidocr_local"
        return

    if has_text_pages and args.mode in {"redo", "force"}:
        if fallback_backend is None:
            raise RuntimeError("检测到已有文本层，rapidocr_local 需要 ocrmypdf 兜底处理 redo/force")
        if not args.quiet:
            print(
                "警告: 检测到已有文本层，`redo/force` 语义下自动回退 ocrmypdf，"
                "以避免重复文字层或旧层残留。"
            )
        fallback_backend(args)
        return

    engine = build_rapid_engine()

    doc = fitz.open(args.input)
    font = fitz.Font("cjk")
    inserted_pages = 0
    inserted_blocks = 0
    skipped_pages = 0

    for pno, page in enumerate(doc, start=1):
        if args.mode == "skip" and page_has_text_layer(page, skip_min_chars):
            skipped_pages += 1
            continue

        pix = page.get_pixmap(dpi=dpi, alpha=False)
        arr = np.frombuffer(pix.samples, dtype=np.uint8)
        arr = arr.reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            arr = arr[:, :, :3]
        # RapidOCR 按 OpenCV 约定接收 BGR
        arr = arr[:, :, ::-1]

        try:
            raw = engine(arr)
        except TypeError:
            raw = engine(arr.tobytes())
        rows = parse_rapidocr_result(raw)
        if not rows:
            continue

        page_inserted = _insert_text_blocks(
            page,
            font,
            rows,
            scale_x=page.rect.width / float(pix.width),
            scale_y=page.rect.height / float(pix.height),
            min_score=min_score,
            cjk_normalize=True,
            page_rotation=int(page.rotation) if page.rotation else 0,
            source_name="RapidOCR",
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
            print("未新增 OCR 文本层，已原样输出。")
        args.backend_used = "rapidocr_local"
        return

    try:
        doc.subset_fonts()
    except Exception:
        pass

    doc.save(args.output, garbage=3, deflate=True)
    doc.close()

    try:
        shutil.copystat(args.input, args.output)
    except Exception:
        pass

    if not args.quiet:
        print("\n本地 RapidOCR 双层完成:")
        print(f"  新增页面: {inserted_pages}/{total_pages}")
        print(f"  新增文本块: {inserted_blocks}")
        print(f"  跳过页面: {skipped_pages}")

    args.backend_used = "rapidocr_local"
