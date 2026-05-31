#!/usr/bin/env python3
"""Historical local PaddleOCR layered-PDF backend.

This module is intentionally kept outside the public OCR entrypoint. The
production path prefers external PaddleOCR / MinerU APIs and local ocrmypdf
fallback, but this local implementation is preserved for future hardware-rich
environments and controlled experiments.
"""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path

from pdf_runtime import print_dependency_help
from pdf_ocr_layered import (
    _insert_text_blocks,
    page_has_text_layer,
    parse_paddle_predict_result,
)

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

PaddleOCR = None
HAS_PADDLEOCR = None


PADDLE_PROFILE_PRESETS = {
    "quality": {
        "det_model": "PP-OCRv5_server_det",
        "rec_model": "PP-OCRv5_server_rec",
        "dpi": 300,
        "det_limit_side_len": 1536,
    },
    "balanced": {
        "det_model": "PP-OCRv5_mobile_det",
        "rec_model": "PP-OCRv5_mobile_rec",
        "dpi": 300,
        "det_limit_side_len": 1216,
    },
    "speed": {
        "det_model": "PP-OCRv5_mobile_det",
        "rec_model": "PP-OCRv5_mobile_rec",
        "dpi": 260,
        "det_limit_side_len": 960,
    },
}


def get_paddle_layered_missing_dependencies() -> list[str]:
    """Detect Python dependencies required by the local Paddle backend."""
    global PaddleOCR, HAS_PADDLEOCR

    missing = []
    if not HAS_PYMUPDF:
        missing.append("pymupdf")
    if not HAS_NUMPY:
        missing.append("numpy")
    if HAS_PADDLEOCR is None:
        try:
            from paddleocr import PaddleOCR as _PaddleOCR  # lazy import
            PaddleOCR = _PaddleOCR
            HAS_PADDLEOCR = True
        except Exception:
            HAS_PADDLEOCR = False
    if not HAS_PADDLEOCR:
        missing.extend(["paddleocr", "paddlepaddle"])
    return missing


def ensure_paddle_layered_available() -> bool:
    """Check local Paddle backend dependencies."""
    missing = get_paddle_layered_missing_dependencies()
    if missing:
        print_dependency_help(
            "本地 Paddle 双层引擎",
            missing_python=missing,
            install_commands=[
                "pip install pymupdf numpy paddleocr paddlepaddle",
            ],
            extra_notes=[
                "本地 Paddle 后端是历史实验能力，不属于默认生产链路。",
                "首次运行 Paddle 相关能力时，模型初始化也可能继续耗时。",
            ],
        )
        return False
    return True


def map_tesseract_lang_to_paddle(language: str) -> str:
    """Map Tesseract-style language values to PaddleOCR language values."""
    lang = (language or "").lower()
    if "chi_sim" in lang or "chi_tra" in lang or "ch" in lang:
        return "ch"
    if "jpn" in lang or "jap" in lang:
        return "japan"
    if "kor" in lang:
        return "korean"
    if "eng" in lang:
        return "en"
    return "ch"


def detect_cuda_device_count() -> int:
    """Detect available CUDA devices on Windows/Linux."""
    system = platform.system().lower()
    if system not in {"windows", "linux"}:
        return 0

    try:
        import paddle  # type: ignore
    except Exception:
        return 0

    try:
        device_mod = getattr(paddle, "device", None)
        if device_mod is None:
            return 0

        is_cuda_fn = getattr(device_mod, "is_compiled_with_cuda", None)
        if not callable(is_cuda_fn) or not is_cuda_fn():
            return 0

        cuda_mod = getattr(device_mod, "cuda", None)
        if cuda_mod is None:
            return 1

        count_fn = getattr(cuda_mod, "device_count", None)
        if callable(count_fn):
            count = int(count_fn() or 0)
            return max(0, count)

        return 1
    except Exception:
        return 0


def resolve_paddle_device(args) -> tuple[bool, str]:
    """Resolve local Paddle runtime device."""
    if args.paddle_use_gpu:
        return True, "用户显式指定 GPU"

    cuda_count = detect_cuda_device_count()
    if cuda_count > 0:
        return True, f"{platform.system()} 自动检测到 CUDA GPU x{cuda_count}"

    return False, f"{platform.system()} 默认 CPU"


def resolve_paddle_profile(args, total_pages: int, use_gpu: bool) -> tuple[str, str]:
    """Resolve local Paddle profile."""
    requested = args.paddle_profile
    if requested != "auto":
        return requested, "用户显式指定"

    if args.paddle_long_doc_pages > 0 and total_pages >= args.paddle_long_doc_pages:
        return "speed", f"页数 {total_pages} >= 阈值 {args.paddle_long_doc_pages}"

    if use_gpu:
        return "quality", "启用 GPU"

    system = platform.system().lower()
    if system in {"darwin", "windows"}:
        return "balanced", f"{platform.system()} CPU 默认平衡档"

    return "quality", f"{platform.system()} 默认高精度档"


def build_paddle_runtime_config(args, total_pages: int, use_gpu: bool) -> dict:
    """Build final local Paddle runtime config from profile and CLI args."""
    profile, reason = resolve_paddle_profile(args, total_pages, use_gpu)
    preset = PADDLE_PROFILE_PRESETS[profile]

    det_model = args.paddle_det_model_name or preset["det_model"]
    rec_model = args.paddle_rec_model_name or preset["rec_model"]
    dpi = args.paddle_dpi if args.paddle_dpi_user_set else preset["dpi"]
    det_limit = (
        args.paddle_det_limit_side_len
        if args.paddle_det_limit_user_set
        else preset["det_limit_side_len"]
    )

    return {
        "profile": profile,
        "profile_reason": reason,
        "use_gpu": bool(use_gpu),
        "det_model": det_model,
        "rec_model": rec_model,
        "dpi": int(dpi),
        "det_limit_side_len": int(det_limit),
    }


def run_local_paddle_layered_backend(args, fallback_backend=None):
    """Run local PaddleOCR + PyMuPDF transparent text-layer generation."""
    if not args.keep_paddle_model_source_check:
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        os.environ.setdefault("DISABLE_MODEL_SOURCE_CHECK", "True")

    if args.paddle_model_source:
        os.environ["PADDLE_PDX_MODEL_SOURCE"] = args.paddle_model_source.lower()

    if not ensure_paddle_layered_available():
        raise RuntimeError("本地 Paddle 双层引擎不可用")

    paddle_lang = args.paddle_lang or map_tesseract_lang_to_paddle(args.language)

    with fitz.open(args.input) as probe_doc:
        total_pages = len(probe_doc)
        has_text_pages = [
            i + 1
            for i, page in enumerate(probe_doc)
            if page_has_text_layer(page, args.paddle_skip_text_min_chars)
        ]

    use_gpu, device_reason = resolve_paddle_device(args)
    runtime_cfg = build_paddle_runtime_config(args, total_pages, use_gpu)

    if not args.quiet:
        print("\n本地 Paddle 双层后端参数:")
        print(f"  profile: {runtime_cfg['profile']} ({runtime_cfg['profile_reason']})")
        print(f"  device: {'gpu' if runtime_cfg['use_gpu'] else 'cpu'} ({device_reason})")
        print(f"  lang: {paddle_lang}")
        print(f"  dpi: {runtime_cfg['dpi']}")
        print(f"  min_score: {args.paddle_min_score}")
        print(f"  skip_text_min_chars: {args.paddle_skip_text_min_chars}")
        print(f"  textline_orientation: {args.paddle_textline_orientation}")
        print(f"  det_limit_side_len: {runtime_cfg['det_limit_side_len']}")
        print(f"  det_model: {runtime_cfg['det_model']}")
        print(f"  rec_model: {runtime_cfg['rec_model']}")
        print(f"  model_source_check: {'keep' if args.keep_paddle_model_source_check else 'disabled'}")
        if args.paddle_model_source:
            print(f"  model_source: {args.paddle_model_source.lower()}")
        print(f"  normalize_cjk_spaces: {not args.no_paddle_cjk_space_normalize}")

    if args.dry_run:
        print("[DRY-RUN] 本地 Paddle 双层后端参数已输出，未实际执行。")
        args.backend_used = "local_paddle_layered"
        return

    if has_text_pages and args.mode in {"redo", "force"}:
        if fallback_backend is None:
            raise RuntimeError("检测到已有文本层，local_paddle_layered 需要 ocrmypdf 兜底处理 redo/force")
        if not args.quiet:
            print(
                "警告: 检测到已有文本层，`redo/force` 语义下自动回退 ocrmypdf，"
                "以避免重复文字层或旧层残留。"
            )
        fallback_backend(args)
        return

    ocr_kwargs = {
        "lang": paddle_lang,
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": args.paddle_textline_orientation,
        "text_det_limit_side_len": runtime_cfg["det_limit_side_len"],
        "text_det_limit_type": "max",
        "text_detection_model_name": runtime_cfg["det_model"],
        "text_recognition_model_name": runtime_cfg["rec_model"],
    }
    if runtime_cfg["use_gpu"]:
        ocr_kwargs["device"] = "gpu"

    try:
        ocr = PaddleOCR(**ocr_kwargs)
    except TypeError:
        ocr_kwargs.pop("device", None)
        ocr = PaddleOCR(**ocr_kwargs)
    except Exception as e:
        if runtime_cfg["use_gpu"] and not args.quiet:
            print(f"警告: PaddleOCR GPU 初始化失败，回退 CPU。原因: {e}")
            ocr_kwargs.pop("device", None)
            ocr = PaddleOCR(**ocr_kwargs)
        else:
            raise

    doc = fitz.open(args.input)
    font = fitz.Font("cjk")
    inserted_pages = 0
    inserted_blocks = 0
    skipped_pages = 0
    cjk_normalize = not args.no_paddle_cjk_space_normalize

    for pno, page in enumerate(doc, start=1):
        if args.mode == "skip" and page_has_text_layer(page, args.paddle_skip_text_min_chars):
            skipped_pages += 1
            continue

        pix = page.get_pixmap(dpi=runtime_cfg["dpi"], alpha=False)
        arr = np.frombuffer(pix.samples, dtype=np.uint8)
        arr = arr.reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            arr = arr[:, :, :3]

        rows = parse_paddle_predict_result(ocr.predict(arr))
        if not rows:
            continue

        page_inserted = _insert_text_blocks(
            page,
            font,
            rows,
            scale_x=page.rect.width / float(pix.width),
            scale_y=page.rect.height / float(pix.height),
            min_score=args.paddle_min_score,
            cjk_normalize=cjk_normalize,
            page_rotation=int(page.rotation) if page.rotation else 0,
            source_name="Paddle",
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
        args.backend_used = "local_paddle_layered"
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
        print("\n本地 Paddle 双层完成:")
        print(f"  新增页面: {inserted_pages}/{total_pages}")
        print(f"  新增文本块: {inserted_blocks}")
        print(f"  跳过页面: {skipped_pages}")

    args.backend_used = "local_paddle_layered"
