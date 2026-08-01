#!/usr/bin/env python3
"""
PDF 预处理 + OCR（生产路径）

完整流程：
1) 可选自动解密
2) 可选页面预处理（旋转/倾斜/裁剪）
3) 可选压缩（默认 medium 200 DPI，兼顾法院上传清晰度与体积）
4) 默认调用 OCR 后端生成双层可搜索 PDF；显式 --preprocess-only 时在 OCR 前停止

说明：
- 默认后端：auto（优先使用已配置的 PaddleOCR/MinerU，失败后回退本地）
- 敏感材料使用 --local-only 强制不调用外部 API
- 通过直接调用 pdf-ocr.py 的 run_ocr() 函数实现，无 subprocess 开销
"""

import argparse
import importlib.util
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from pdf_runtime import (
    DEFAULT_MINERU_API_BASE_ENV,
    DEFAULT_MINERU_API_TOKEN_ENV,
    DEFAULT_MINERU_USER_TOKEN_ENV,
    DEFAULT_PADDLE_API_ENDPOINT_ENV,
    DEFAULT_PADDLE_API_KEY_ENV,
    apply_api_env_aliases,
    exit_for_missing_dependencies,
    load_env_file,
)
from pdf_ocr_paddle_api import PADDLE_VL_MODELS, PADDLE_STRUCTURE_MODEL, SUPPORTED_PADDLE_MODELS

try:
    import pypdf
except ImportError as e:
    exit_for_missing_dependencies(
        "PDF 预处理 + OCR 入口",
        missing_python=["pypdf"],
        install_commands=["pip install pypdf"],
        extra_notes=[f"原始错误: {e}"],
    )


SCRIPT_DIR = Path(__file__).parent
PREPROCESS_CORE_SCRIPT = SCRIPT_DIR / "pdf-preprocess-core.py"
DEFAULT_ENV_FILE_PATH = str((SCRIPT_DIR.parent / "config" / ".env").resolve())
PREPROCESS_DPI_BY_COMPRESS_LEVEL = {
    "low": 300,
    "medium": 200,
    "high": 150,
}
MERGED_PREPROCESS_OUTPUT_PROFILES = {
    "low": {
        "dpi": 300,
        "pdf_jpeg_quality": 85,
        "pdf_jpeg_subsampling": 0,
        "pdf_jpeg_optimize": True,
    },
    "medium": {
        "dpi": 200,
        "pdf_jpeg_quality": 72,
        "pdf_jpeg_subsampling": 1,
        "pdf_jpeg_optimize": True,
    },
    "high": {
        "dpi": 130,
        "pdf_jpeg_quality": 45,
        "pdf_jpeg_subsampling": 2,
        "pdf_jpeg_optimize": True,
    },
}
DEFAULT_MAX_PREPROCESS_MEGAPIXELS = 25.0
DEFAULT_OCR_API_ORDER_ENV = "OCR_API_ORDER"


def _copy_file_times(src: str | Path, dst: str | Path) -> None:
    """复制源文件的创建时间和修改时间到目标文件（macOS 含 birthtime）。"""
    src, dst = Path(src), Path(dst)
    stat = src.stat()
    mtime = stat.st_mtime
    birthtime = getattr(stat, "st_birthtime", mtime)
    os.utime(dst, (mtime, mtime))
    if platform.system() == "Darwin":
        try:
            dt = datetime.fromtimestamp(birthtime)
            date_str = dt.strftime("%m/%d/%Y %H:%M:%S")
            subprocess.run(
                ["SetFile", "-d", date_str, str(dst)],
                check=True, capture_output=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass


def parse_skip_pages(raw: str | None) -> set[int]:
    """解析 --skip-pages 参数。"""
    if not raw:
        return set()
    try:
        return set(int(x.strip()) for x in raw.split(",") if x.strip())
    except ValueError as exc:
        raise ValueError("--skip-pages 格式错误，应为逗号分隔的页码") from exc


def resolve_preprocess_dpi(explicit_dpi: int | None, no_compress: bool, compress_level: str) -> int:
    """Resolve preprocessing DPI from explicit input or compression profile."""
    if explicit_dpi is not None:
        return explicit_dpi
    if no_compress:
        return 300
    return PREPROCESS_DPI_BY_COMPRESS_LEVEL.get(compress_level, 200)


def resolve_preprocess_output_options(
    explicit_dpi: int | None,
    explicit_jpeg_quality: int | None,
    no_compress: bool,
    compress_level: str,
    merge_preprocess_compress: bool,
) -> dict:
    """Resolve output options for preprocessing PDF generation."""
    if no_compress or not merge_preprocess_compress:
        return {
            "dpi": resolve_preprocess_dpi(explicit_dpi, no_compress, compress_level),
            "pdf_jpeg_quality": explicit_jpeg_quality if explicit_jpeg_quality is not None else 90,
            "pdf_jpeg_subsampling": 0,
            "pdf_jpeg_optimize": False,
        }

    profile = MERGED_PREPROCESS_OUTPUT_PROFILES.get(
        compress_level,
        MERGED_PREPROCESS_OUTPUT_PROFILES["medium"],
    )
    return {
        "dpi": explicit_dpi if explicit_dpi is not None else profile["dpi"],
        "pdf_jpeg_quality": (
            explicit_jpeg_quality
            if explicit_jpeg_quality is not None
            else profile["pdf_jpeg_quality"]
        ),
        "pdf_jpeg_subsampling": profile["pdf_jpeg_subsampling"],
        "pdf_jpeg_optimize": profile["pdf_jpeg_optimize"],
    }


def resolve_bounded_preprocess_dpi(
    pdf_path: str | Path,
    requested_dpi: int,
    max_megapixels: float = DEFAULT_MAX_PREPROCESS_MEGAPIXELS,
) -> dict:
    """Limit raster preprocessing size for PDFs with abnormal physical page dimensions."""
    if requested_dpi <= 0:
        raise ValueError("预处理 DPI 必须大于 0")

    result = {
        "requested_dpi": requested_dpi,
        "effective_dpi": requested_dpi,
        "max_megapixels": max_megapixels,
        "predicted_megapixels": None,
        "effective_megapixels": None,
        "capped": False,
        "reason": None,
    }
    if max_megapixels <= 0:
        result["reason"] = "disabled"
        return result

    try:
        reader = pypdf.PdfReader(str(pdf_path))
        page_areas = []
        for page in reader.pages:
            box = page.cropbox
            width = abs(float(box.right) - float(box.left))
            height = abs(float(box.top) - float(box.bottom))
            if width > 0 and height > 0 and math.isfinite(width) and math.isfinite(height):
                page_areas.append(width * height)
    except Exception as exc:
        result["reason"] = f"inspection_failed:{type(exc).__name__}"
        return result

    if not page_areas:
        result["reason"] = "no_valid_page_size"
        return result

    max_area_points = max(page_areas)
    predicted = max_area_points * requested_dpi * requested_dpi / (72.0 * 72.0) / 1_000_000.0
    result["predicted_megapixels"] = round(predicted, 3)
    if predicted <= max_megapixels:
        result["effective_megapixels"] = round(predicted, 3)
        return result

    dpi_cap = max(
        1,
        int(math.floor(72.0 * math.sqrt(max_megapixels * 1_000_000.0 / max_area_points))),
    )
    effective_dpi = min(requested_dpi, dpi_cap)
    effective_mp = max_area_points * effective_dpi * effective_dpi / (72.0 * 72.0) / 1_000_000.0
    result.update(
        {
            "effective_dpi": effective_dpi,
            "effective_megapixels": round(effective_mp, 3),
            "capped": effective_dpi < requested_dpi,
            "reason": "page_pixel_guard" if effective_dpi < requested_dpi else None,
        }
    )
    return result


def should_run_standalone_compress(
    no_compress: bool,
    preprocessed: bool,
    merge_preprocess_compress: bool,
) -> bool:
    """Whether to run the standalone compression stage."""
    if no_compress:
        return False
    return not (preprocessed and merge_preprocess_compress)


def should_use_ocrmypdf_native_preprocess(
    *,
    backend: str,
    local_only: bool,
    external_backend_configured: bool,
    skip_preprocess: bool,
    preprocess_only: bool,
    enable_crop: bool,
    force_raster_preprocess: bool,
) -> bool:
    """Prefer OCRmyPDF's native cleanup when the effective backend is local.

    Re-rasterizing an already full-resolution scan before Tesseract can discard
    recognition detail.  Explicit preprocessing requests continue to win.
    """
    if skip_preprocess or preprocess_only or enable_crop or force_raster_preprocess:
        return False
    local_selected = backend == "local_ocrmypdf" or (
        backend == "auto" and (local_only or not external_backend_configured)
    )
    return local_selected


def resolve_configured_external_order(
    raw_order: str | None,
    *,
    paddle_configured: bool,
    mineru_configured: bool,
) -> list[str]:
    """Return configured external providers in the order auto will try them."""
    order = []
    for value in (raw_order or "").split(","):
        provider = value.strip().lower()
        if provider in {"paddle", "mineru"} and provider not in order:
            order.append(provider)
    if not order:
        order = ["paddle", "mineru"]
    return [
        provider
        for provider in order
        if (provider == "paddle" and paddle_configured)
        or (provider == "mineru" and mineru_configured)
    ]


def should_use_paddle_original_input(
    *,
    backend: str,
    local_only: bool,
    paddle_selected_by_auto: bool,
    skip_preprocess: bool,
    preprocess_only: bool,
    enable_crop: bool,
    force_raster_preprocess: bool,
) -> bool:
    """Keep the original PDF when Paddle is the effective first OCR backend."""
    if skip_preprocess or preprocess_only or enable_crop or force_raster_preprocess:
        return False
    paddle_selected = backend == "paddle_api" or (
        backend == "auto" and not local_only and paddle_selected_by_auto
    )
    return paddle_selected


def classify_pdf_layer_content(pdf_path: str | Path) -> dict:
    """识别 PDF 是否含需保留的文字、矢量或批注层。"""
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("检测 PDF 层结构需要 PyMuPDF：pip install pymupdf") from exc

    total_pages = 0
    text_pages = 0
    vector_pages = 0
    annotation_pages = 0
    image_pages = 0
    structured_pages = 0
    with fitz.open(pdf_path) as doc:
        total_pages = len(doc)
        for page in doc:
            has_text = bool((page.get_text("text") or "").strip())
            has_vector = False
            has_annotation = False
            if has_text:
                text_pages += 1
            try:
                if page.get_drawings():
                    has_vector = True
                    vector_pages += 1
            except Exception:
                pass
            try:
                if page.first_annot is not None:
                    has_annotation = True
                    annotation_pages += 1
            except Exception:
                pass
            try:
                if page.get_images(full=True):
                    image_pages += 1
            except Exception:
                pass
            if has_text or has_vector or has_annotation:
                structured_pages += 1

    if text_pages == 0 and vector_pages == 0 and annotation_pages == 0:
        kind = "scanned"
    elif image_pages == 0 and text_pages == total_pages:
        kind = "digital"
    else:
        kind = "hybrid"
    return {
        "kind": kind,
        "total_pages": total_pages,
        "text_pages": text_pages,
        "vector_pages": vector_pages,
        "annotation_pages": annotation_pages,
        "image_pages": image_pages,
        "structured_pages": structured_pages,
    }


def write_preprocess_only_output(
    source_path: str | Path,
    output_path: str | Path,
    original_input: str | Path,
    dry_run: bool = False,
) -> None:
    """写出仅预处理模式的最终 PDF，并按原始输入保留文件时间戳。"""
    if dry_run:
        return

    source = Path(source_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    if source.resolve() != output.resolve():
        shutil.copy2(source, output)
    _copy_file_times(original_input, output)


def load_preprocess_function():
    """动态加载预处理核心函数，避免在跳过预处理时强制依赖 OpenCV。"""
    spec = importlib.util.spec_from_file_location(
        "pdf_preprocess_core",
        PREPROCESS_CORE_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 pdf-preprocess-core.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.process_pdf


def decrypt_if_needed(input_pdf: str, password: str | None, auto_decrypt: bool) -> tuple[str | None, str | None]:
    """
    必要时解密 PDF。

    Returns:
        (decrypted_path_or_none, temp_file_path_or_none)
    """
    with open(input_pdf, "rb") as f:
        reader = pypdf.PdfReader(f)
        if not reader.is_encrypted:
            return input_pdf, None

    if not auto_decrypt:
        print("错误: 输入 PDF 已加密，请使用 --password 或启用自动解密。", file=sys.stderr)
        return None, None

    with open(input_pdf, "rb") as f:
        reader = pypdf.PdfReader(f)
        passwords = []
        if password:
            passwords.append(password)
        passwords.extend(["", "123456", "password", "123456789", "admin", "user"])

        for pwd in passwords:
            try:
                if reader.decrypt(pwd):
                    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                    temp_path = temp.name
                    temp.close()

                    writer = pypdf.PdfWriter()
                    for page in reader.pages:
                        writer.add_page(page)

                    with open(temp_path, "wb") as out_f:
                        writer.write(out_f)

                    return temp_path, temp_path
            except Exception:
                continue

    print("错误: 自动解密失败，请提供正确密码。", file=sys.stderr)
    return None, None


def main():
    parser = argparse.ArgumentParser(
        description="PDF 预处理 + OCR（默认 auto 后端，支持外部 API 与本地 ocrmypdf）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 推荐：先预处理再做双层 PDF（默认 skip）
  python3 scripts/pdf-preprocess-ocr.py -i input.pdf -o output.pdf

  # 仅做 OCR，不做预处理
  python3 scripts/pdf-preprocess-ocr.py -i input.pdf -o output.pdf --skip-preprocess

  # 仅做预处理和压缩，不生成 OCR 文字层
  python3 scripts/pdf-preprocess-ocr.py -i input.pdf -o output.pdf --preprocess-only

  # 跳过第 1、3 页预处理
  python3 scripts/pdf-preprocess-ocr.py -i input.pdf -o output.pdf --skip-pages 1,3

  # OCR 保守模式：已有文字层就跳过
  python3 scripts/pdf-preprocess-ocr.py -i input.pdf -o output.pdf --mode skip
        """
    )

    # 基础参数
    parser.add_argument("--input", "-i", required=True, help="输入 PDF 文件")
    parser.add_argument("--output", "-o", required=True, help="输出 PDF 文件")
    parser.add_argument("--quiet", "-q", action="store_true", help="静默模式")
    parser.add_argument("--dry-run", action="store_true", help="仅显示将执行的动作")
    parser.add_argument(
        "--env-file",
        default=DEFAULT_ENV_FILE_PATH,
        help=f".env 文件路径（默认 {DEFAULT_ENV_FILE_PATH}）",
    )
    parser.add_argument(
        "--no-env-file",
        action="store_true",
        help="禁用 .env 自动加载",
    )

    # 解密参数
    parser.add_argument("--no-auto-decrypt", action="store_true", help="禁用自动解密")
    parser.add_argument("--password", help="文档密码（优先尝试）")

    # 预处理参数
    parser.add_argument("--skip-preprocess", action="store_true", help="跳过预处理阶段")
    parser.add_argument(
        "--force-raster-preprocess",
        action="store_true",
        help=(
            "强制使用统一栅格化预处理，包括本地 OCR 路径；"
            "电子/混合 PDF 可能丢失矢量和批注层"
        ),
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=None,
        help=(
            "预处理 DPI（默认随压缩级别自动选择；合并压缩时 medium=200，"
            "禁用合并压缩时 medium=200；跳过压缩时为 300）"
        ),
    )
    parser.add_argument(
        "--max-preprocess-megapixels",
        type=float,
        default=DEFAULT_MAX_PREPROCESS_MEGAPIXELS,
        help=(
            "预处理单页像素上限（MP），默认 25；异常大物理页面会自动降低实际 DPI，"
            "设为 0 可禁用"
        ),
    )
    parser.add_argument(
        "--skew-threshold",
        type=float,
        default=0.3,
        help="预处理倾斜阈值（默认 0.3 度）",
    )
    parser.add_argument(
        "--rotation-confidence",
        type=float,
        default=0.5,
        help="预处理旋转检测置信度（默认 0.5）",
    )
    parser.add_argument(
        "--skip-coarse-rotation",
        action="store_true",
        help="跳过 90° 粗方向检测（提速；适用于页面方向已正确的扫描件）",
    )
    parser.add_argument(
        "--preprocess-jobs",
        type=int,
        default=1,
        help="预处理页面并行数（默认 1；0 表示自动）",
    )
    parser.add_argument(
        "--preprocess-chunk-pages",
        type=int,
        default=0,
        help="预处理分块页数（默认 0，不分块；如 40）",
    )
    parser.add_argument("--skip-pages", help="预处理跳过页，逗号分隔，例如 1,3,5")
    parser.add_argument(
        "--enable-crop",
        action="store_true",
        help="启用预处理裁剪（默认关闭，保真优先）",
    )
    parser.add_argument(
        "--no-crop",
        action="store_true",
        help="禁用预处理裁剪（兼容旧参数）",
    )
    parser.add_argument(
        "--pdf-jpeg-quality",
        type=int,
        default=None,
        help="预处理输出 PDF 的 JPEG 质量（1-100；默认随压缩档位选择，跳过压缩时为 90）",
    )
    parser.add_argument(
        "--no-merge-preprocess-compress",
        action="store_true",
        help="禁用预处理与压缩合并输出，恢复为预处理后再单独压缩",
    )
    parser.add_argument(
        "--no-restore-size",
        action="store_true",
        help="预处理后不恢复原始页面尺寸",
    )
    parser.add_argument(
        "--preprocess-only",
        "--only-preprocess",
        action="store_true",
        help="仅执行解密、页面预处理和压缩，不进入 OCR；只有用户明确要求只预处理时使用",
    )

    # 压缩参数
    parser.add_argument(
        "--no-compress",
        action="store_true",
        help="跳过压缩阶段（默认在预处理后、OCR 前压缩）",
    )
    parser.add_argument(
        "--compress-level",
        choices=["low", "medium", "high"],
        default="medium",
        help="压缩级别（默认: medium；预处理合并输出约 200 DPI，单独压缩为 max 2000px）",
    )

    # OCR 参数（透传给 pdf-ocr.py 的 run_ocr()）
    parser.add_argument(
        "--backend",
        choices=["auto", "local_ocrmypdf", "paddle_api", "mineru_api"],
        default="auto",
        help="OCR 后端，默认 auto（已配置时 Paddle/MinerU 优先，失败回退本地）",
    )
    parser.add_argument(
        "--api-order",
        help="auto 模式外部 API 顺序，逗号分隔（例如 paddle,mineru）",
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="强制不调用外部 OCR API，仅使用本地 ocrmypdf",
    )
    parser.add_argument(
        "--mode",
        choices=["skip", "redo", "force"],
        default="skip",
        help="OCR 模式，默认 skip（保留已有文字层）",
    )
    parser.add_argument("--language", default="chi_sim+eng", help="OCR 语言包，默认 chi_sim+eng")
    parser.add_argument(
        "--output-type",
        choices=["pdf", "pdfa"],
        default="pdf",
        help="OCR 输出类型，默认 pdf（保真优先）",
    )
    parser.add_argument(
        "--optimize",
        type=int,
        choices=[0, 1, 2, 3],
        default=0,
        help="OCR 优化级别 0-3，默认 0（保真优先）",
    )
    parser.add_argument("--skip-big", type=float, default=50.0, help="OCR 跳过大图阈值（MP），默认 50")
    parser.add_argument(
        "--tesseract-timeout",
        type=int,
        default=180,
        help="Tesseract 单页超时（秒），默认 180",
    )
    parser.add_argument("--jobs", type=int, help="OCR 并行任务数")

    parser.add_argument(
        "--paddle-model",
        choices=SUPPORTED_PADDLE_MODELS,
        default="PP-OCRv6",
        help="PaddleOCR 模型，默认 PP-OCRv6（行级坐标更适合双层 PDF）",
    )
    parser.add_argument("--paddle-api-endpoint", help="外部 PaddleOCR API 地址")
    parser.add_argument("--paddle-api-key-env", default=DEFAULT_PADDLE_API_KEY_ENV)
    parser.add_argument("--paddle-api-timeout", type=int, default=180)
    parser.add_argument("--paddle-api-retries", type=int, default=1)
    parser.add_argument("--paddle-api-extra-json", help="额外 API payload JSON 文件路径")
    parser.add_argument(
        "--paddle-api-protocol",
        choices=["auto", "official", "legacy"],
        default="auto",
        help="API 协议，默认 auto",
    )
    parser.add_argument(
        "--no-paddle-fallback-local",
        action="store_true",
        help="Paddle API 失败时不回退到本地 ocrmypdf",
    )
    parser.add_argument(
        "--paddle-vl-no-layout-detection",
        action="store_true",
        help="VL-1.5：禁用版面区域检测",
    )
    parser.add_argument(
        "--paddle-vl-chart-recognition",
        action="store_true",
        help="VL/Structure：启用图表解析",
    )
    parser.add_argument(
        "--paddle-vl-doc-orientation",
        action="store_true",
        help="VL/Structure：启用服务端页面方向矫正",
    )
    parser.add_argument(
        "--paddle-vl-doc-unwarping",
        action="store_true",
        help="VL/Structure：启用服务端页面去畸变",
    )
    parser.add_argument(
        "--paddle-vl-layout-shape-mode",
        choices=["rect", "quad", "poly", "auto"],
        default="rect",
        help="VL-1.5：版面检测框形状，默认 rect",
    )
    parser.add_argument("--mineru-api-base", help="MinerU API Base 地址")
    parser.add_argument("--mineru-api-base-env", default=DEFAULT_MINERU_API_BASE_ENV)
    parser.add_argument("--mineru-api-token-env", default=DEFAULT_MINERU_API_TOKEN_ENV)
    parser.add_argument("--mineru-user-token-env", default=DEFAULT_MINERU_USER_TOKEN_ENV)
    parser.add_argument("--mineru-api-timeout", type=int, default=180)
    parser.add_argument("--mineru-poll-interval", type=int, default=2)
    parser.add_argument("--mineru-poll-timeout", type=int, default=1800)
    parser.add_argument("--mineru-model-version", default="")
    parser.add_argument("--mineru-language", default="")
    parser.add_argument("--mineru-enable-formula", action="store_true")
    parser.add_argument("--mineru-enable-table", action="store_true")
    parser.add_argument("--mineru-api-extra-json", help="额外 MinerU create payload JSON 文件路径")
    parser.add_argument(
        "--allow-external-upload",
        action="store_true",
        help="兼容旧版本；auto 现已默认使用已配置 API，如需禁止外传请用 --local-only",
    )
    parser.add_argument(
        "--archive-results",
        action="store_true",
        help="显式归档 OCR 文本或预处理元数据；默认不归档案件材料",
    )

    args = parser.parse_args()
    stage_total = 2 if args.preprocess_only else 3
    args.merge_preprocess_compress = (
        not args.no_merge_preprocess_compress
        and not args.no_compress
    )
    preprocess_output_options = resolve_preprocess_output_options(
        explicit_dpi=args.dpi,
        explicit_jpeg_quality=args.pdf_jpeg_quality,
        no_compress=args.no_compress,
        compress_level=args.compress_level,
        merge_preprocess_compress=args.merge_preprocess_compress,
    )
    args.dpi = preprocess_output_options["dpi"]
    args.pdf_jpeg_quality = preprocess_output_options["pdf_jpeg_quality"]
    args.pdf_jpeg_subsampling = preprocess_output_options["pdf_jpeg_subsampling"]
    args.pdf_jpeg_optimize = preprocess_output_options["pdf_jpeg_optimize"]

    if not args.no_env_file:
        load_env_file(args.env_file, quiet=args.quiet)
    apply_api_env_aliases()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"错误: 输入文件不存在: {args.input}", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cleanup_files: list[str] = []

    try:
        # 阶段 0：解密
        if not args.quiet:
            print("=" * 60)
            print(f"阶段 0/{stage_total}：解密检查")
            print("=" * 60)

        working_input, decrypted_temp = decrypt_if_needed(
            args.input,
            args.password,
            auto_decrypt=not args.no_auto_decrypt,
        )
        if working_input is None:
            sys.exit(1)
        if decrypted_temp:
            cleanup_files.append(decrypted_temp)
            if not args.quiet:
                print(f"已生成解密临时文件: {decrypted_temp}")

        layer_profile = classify_pdf_layer_content(working_input)
        preserve_original_layers = (
            layer_profile["kind"] in {"digital", "hybrid"}
            and not args.force_raster_preprocess
        )
        if preserve_original_layers and not args.quiet:
            print(
                f"\n[层保护] 检测到 {layer_profile['kind']} PDF，"
                "默认跳过栅格化预处理与重压缩；如确需强制处理请传 --force-raster-preprocess"
            )

        paddle_endpoint = (
            args.paddle_api_endpoint
            or os.getenv(DEFAULT_PADDLE_API_ENDPOINT_ENV, "").strip()
        )
        mineru_endpoint = (
            args.mineru_api_base
            or os.getenv(args.mineru_api_base_env, "").strip()
        )
        external_backend_configured = bool(paddle_endpoint or mineru_endpoint)
        configured_external_order = resolve_configured_external_order(
            args.api_order or os.getenv(DEFAULT_OCR_API_ORDER_ENV, ""),
            paddle_configured=bool(paddle_endpoint),
            mineru_configured=bool(mineru_endpoint),
        )
        paddle_selected_by_auto = (
            bool(configured_external_order)
            and configured_external_order[0] == "paddle"
        )
        paddle_original_input_shortcut = (
            not preserve_original_layers
            and should_use_paddle_original_input(
                backend=args.backend,
                local_only=args.local_only,
                paddle_selected_by_auto=paddle_selected_by_auto,
                skip_preprocess=args.skip_preprocess,
                preprocess_only=args.preprocess_only,
                enable_crop=args.enable_crop,
                force_raster_preprocess=args.force_raster_preprocess,
            )
        )
        if paddle_original_input_shortcut and not args.quiet:
            print(
                "\n[PaddleOCR 原图短路] 跳过统一栅格化与预压缩；"
                "直接提交原 PDF，以保留扫描分辨率和原有图层"
            )
        local_native_preprocess_shortcut = (
            not preserve_original_layers
            and should_use_ocrmypdf_native_preprocess(
                backend=args.backend,
                local_only=args.local_only,
                external_backend_configured=external_backend_configured,
                skip_preprocess=args.skip_preprocess,
                preprocess_only=args.preprocess_only,
                enable_crop=args.enable_crop,
                force_raster_preprocess=args.force_raster_preprocess,
            )
        )
        if local_native_preprocess_shortcut and not args.quiet:
            print(
                "\n[本地 OCR 短路] 跳过统一栅格化与预压缩；"
                "交由 OCRmyPDF 对原始扫描页执行方向检测、纠偏和清理"
            )

        # PaddleOCR API 预处理短路：仅当 API 端确实启用了方向/去畸变时才跳过本地预处理
        # 默认 useDocOrientationClassify=False, useDocUnwarping=False，不走短路
        # 如果用户显式请求了 --enable-crop，API 不做裁剪，必须走本地预处理
        api_preprocessing_shortcut = False
        if not args.skip_preprocess and not preserve_original_layers and not args.enable_crop:
            using_paddle_api = False
            if args.backend == "paddle_api":
                using_paddle_api = True
            elif args.backend == "auto" and not args.local_only:
                if paddle_selected_by_auto:
                    using_paddle_api = True

            if using_paddle_api:
                # 检查 --paddle-api-extra-json 是否启用了方向矫正或去畸变
                supports_vl_preprocess = (
                    args.paddle_model in PADDLE_VL_MODELS
                    or args.paddle_model == PADDLE_STRUCTURE_MODEL
                )
                api_orientation = supports_vl_preprocess and args.paddle_vl_doc_orientation
                api_unwarping = supports_vl_preprocess and args.paddle_vl_doc_unwarping
                extra_path = getattr(args, "paddle_api_extra_json", None)
                if extra_path:
                    import json as _json
                    try:
                        with open(extra_path, "r", encoding="utf-8") as _f:
                            _extra = _json.load(_f)
                        if isinstance(_extra, dict):
                            api_orientation = _extra.get("useDocOrientationClassify", False)
                            api_unwarping = _extra.get("useDocUnwarping", False)
                    except Exception:
                        pass
                api_preprocessing_shortcut = api_orientation or api_unwarping

            if api_preprocessing_shortcut and not args.quiet:
                print("\n[预处理短路] PaddleOCR API 已启用服务端方向/扭曲矫正，跳过本地预处理阶段")

        # 阶段 1：预处理
        preprocessed = False
        preprocess_resolution_meta = None
        if (
            not args.skip_preprocess
            and not api_preprocessing_shortcut
            and not paddle_original_input_shortcut
            and not local_native_preprocess_shortcut
            and not preserve_original_layers
        ):
            preprocess_resolution_meta = resolve_bounded_preprocess_dpi(
                working_input,
                requested_dpi=args.dpi,
                max_megapixels=args.max_preprocess_megapixels,
            )
            args.dpi = preprocess_resolution_meta["effective_dpi"]
            if preprocess_resolution_meta["capped"] and not args.quiet:
                print(
                    "\n[像素保护] 页面物理尺寸异常偏大："
                    f"预处理 DPI {preprocess_resolution_meta['requested_dpi']} → {args.dpi}，"
                    f"预计单页 {preprocess_resolution_meta['predicted_megapixels']:.1f}MP → "
                    f"{preprocess_resolution_meta['effective_megapixels']:.1f}MP"
                )
            skip_pages = parse_skip_pages(args.skip_pages)
            preprocessed_temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            preprocessed_path = preprocessed_temp.name
            preprocessed_temp.close()
            cleanup_files.append(preprocessed_path)

            if not args.quiet:
                print("\n" + "=" * 60)
                print(f"阶段 1/{stage_total}：页面预处理")
                print("=" * 60)
                print(f"临时输出: {preprocessed_path}")

            if not args.dry_run:
                process_pdf = load_preprocess_function()
                stats = process_pdf(
                    working_input,
                    preprocessed_path,
                    dpi=args.dpi,
                    skew_threshold=args.skew_threshold,
                    rotation_confidence=args.rotation_confidence,
                    enable_coarse_rotation=not args.skip_coarse_rotation,
                    enable_crop=(args.enable_crop and (not args.no_crop)),
                    skip_pages=skip_pages,
                    restore_original_size=not args.no_restore_size,
                    pdf_jpeg_quality=args.pdf_jpeg_quality,
                    pdf_jpeg_subsampling=args.pdf_jpeg_subsampling,
                    pdf_jpeg_optimize=args.pdf_jpeg_optimize,
                    preprocess_jobs=args.preprocess_jobs,
                    preprocess_chunk_pages=args.preprocess_chunk_pages,
                    verbose=not args.quiet,
                )
                if not args.quiet:
                    print("预处理统计:")
                    print(f"  总页数: {stats['total_pages']}")
                    print(f"  旋转页数: {stats['rotated_pages']}")
                    print(f"  倾斜矫正: {stats['deskewed_pages']}")
                    print(f"  裁剪页数: {stats['cropped_pages']}")
                    print(f"  页面累计耗时: {stats['total_time']:.2f}s")
                    print(f"  墙钟耗时: {stats['page_wall_time']:.2f}s")
                    print(f"  渲染耗时: {stats['render_time']:.2f}s")
                    print(f"  保存耗时: {stats['save_time']:.2f}s")
                    print(f"  预处理并行数: {stats['preprocess_jobs']}")
                    print(f"  预处理分块页数: {stats['preprocess_chunk_pages']}")

            working_input = preprocessed_path
            preprocessed = True
        elif not args.quiet:
            if args.skip_preprocess:
                print("\n[跳过] 预处理阶段已跳过（--skip-preprocess）")
            elif paddle_original_input_shortcut:
                print("\n[跳过] 预处理阶段已跳过（PaddleOCR 原 PDF 直送）")
            elif api_preprocessing_shortcut:
                print("\n[跳过] 预处理阶段已跳过（PaddleOCR API 服务端预处理）")
            elif local_native_preprocess_shortcut:
                print("\n[跳过] 预处理阶段已跳过（OCRmyPDF 本地原生预处理）")
            elif preserve_original_layers:
                print("\n[跳过] 预处理阶段已跳过（电子/混合 PDF 层保护）")

        # 阶段 2：压缩（预处理后、OCR 前，减小上传体积）
        compress_result = None
        compress_merged_into_preprocess = (
            preprocessed
            and args.merge_preprocess_compress
            and not args.no_compress
        )
        if should_run_standalone_compress(
            no_compress=(
                args.no_compress
                or preserve_original_layers
                or paddle_original_input_shortcut
                or local_native_preprocess_shortcut
            ),
            preprocessed=preprocessed,
            merge_preprocess_compress=args.merge_preprocess_compress,
        ):
            compress_temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            compress_path = compress_temp.name
            compress_temp.close()
            cleanup_files.append(compress_path)

            if not args.quiet:
                print("\n" + "=" * 60)
                print(f"阶段 2/{stage_total}：PDF 压缩")
                print("=" * 60)

            if not args.dry_run:
                spec_compress = importlib.util.spec_from_file_location(
                    "pdf_compress",
                    SCRIPT_DIR / "pdf-compress.py",
                )
                if spec_compress and spec_compress.loader:
                    compress_mod = importlib.util.module_from_spec(spec_compress)
                    spec_compress.loader.exec_module(compress_mod)
                    compress_result = compress_mod.compress_pdf(
                        working_input,
                        compress_path,
                        compression_level=args.compress_level,
                        quiet=args.quiet,
                    )
                    if not args.quiet:
                        print(f"  {compress_result['original_size_mb']:.2f} MB → {compress_result['compressed_size_mb']:.2f} MB"
                              f"（-{compress_result['reduction_percent']:.1f}%）")
                else:
                    if not args.quiet:
                        print("[跳过] 无法加载压缩模块")
                    compress_path = working_input
            else:
                if not args.quiet:
                    print(f"[DRY-RUN] 压缩级别: {args.compress_level}")

            working_input = compress_path
        elif compress_merged_into_preprocess:
            compress_result = {
                "merged_into_preprocess": True,
                "compression_level": args.compress_level,
                "dpi": args.dpi,
                "pdf_jpeg_quality": args.pdf_jpeg_quality,
                "pdf_jpeg_subsampling": args.pdf_jpeg_subsampling,
                "pdf_jpeg_optimize": args.pdf_jpeg_optimize,
            }
            if not args.quiet:
                print("\n[跳过] 压缩阶段已合并到预处理输出")
        elif not args.quiet:
            reason = (
                "电子/混合 PDF 层保护"
                if preserve_original_layers
                else "PaddleOCR 原 PDF 直送"
                if paddle_original_input_shortcut
                else "OCRmyPDF 本地原生预处理"
                if local_native_preprocess_shortcut
                else "--no-compress"
            )
            print(f"\n[跳过] 压缩阶段已跳过（{reason}）")

        if args.preprocess_only:
            if not args.quiet:
                print("\n" + "=" * 60)
                print("仅预处理模式：跳过 OCR")
                print("=" * 60)

            # 构建预处理元数据
            preprocess_only_meta = {
                "original_file": str(args.input),
                "decrypted": bool(decrypted_temp),
                "preprocessed": preprocessed,
                "preprocess_skipped": (
                    args.skip_preprocess
                    or paddle_original_input_shortcut
                    or api_preprocessing_shortcut
                    or local_native_preprocess_shortcut
                    or preserve_original_layers
                ),
                "layer_profile": layer_profile,
                "preserve_original_layers": preserve_original_layers,
                "preprocess_shortcut_reason": (
                    "paddle_original"
                    if paddle_original_input_shortcut
                    else "paddle_api"
                    if api_preprocessing_shortcut
                    else "ocrmypdf_native"
                    if local_native_preprocess_shortcut
                    else None
                ),
                "compress_skipped": args.no_compress or preserve_original_layers,
                "compress_merged_into_preprocess": compress_merged_into_preprocess,
                "compress_level": args.compress_level if not (args.no_compress or preserve_original_layers) else None,
                "compress_result": compress_result if compress_result else None,
            }

            write_preprocess_only_output(
                working_input,
                args.output,
                args.input,
                dry_run=args.dry_run,
            )

            # 归档预处理记录
            if not args.dry_run and args.archive_results:
                try:
                    from pdf_ocr_corrections import archive_preprocess_result
                    archive_dir = archive_preprocess_result(
                        source_path=working_input,
                        preprocess_meta=preprocess_only_meta,
                        output_path=args.output,
                        original_source_path=args.input,
                    )
                    if not args.quiet:
                        print(f"归档记录: {archive_dir}")
                except Exception as e:
                    if not args.quiet:
                        print(f"[警告] 归档失败（不影响输出）: {e}")

            if not args.quiet:
                if args.dry_run:
                    print("[DRY-RUN] 不写出最终文件")
                else:
                    print("处理完成！")
                    print(f"输出文件: {args.output}")
                print("=" * 60)
            return

        # 阶段 3：OCR（直接调用 run_ocr 函数，无 subprocess 开销）
        if not args.quiet:
            print("\n" + "=" * 60)
            print(f"阶段 3/{stage_total}：OCR 生成双层 PDF")
            print("=" * 60)

        # 动态导入避免循环依赖
        spec = importlib.util.spec_from_file_location(
            "pdf_ocr",
            SCRIPT_DIR / "pdf-ocr.py",
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("无法加载 pdf-ocr.py")
        pdf_ocr_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pdf_ocr_module)

        # 构建预处理元数据，供归档记录
        preprocess_meta = {
            "original_file": str(args.input),
            "decrypted": bool(decrypted_temp),
            "preprocessed": preprocessed,
            "preprocess_skipped": (
                args.skip_preprocess
                or paddle_original_input_shortcut
                or api_preprocessing_shortcut
                or local_native_preprocess_shortcut
                or preserve_original_layers
            ),
            "layer_profile": layer_profile,
            "preserve_original_layers": preserve_original_layers,
            "preprocess_shortcut_reason": (
                "paddle_original"
                if paddle_original_input_shortcut
                else "paddle_api"
                if api_preprocessing_shortcut
                else "ocrmypdf_native"
                if local_native_preprocess_shortcut
                else None
            ),
            "preprocess_params": {
                "dpi": args.dpi,
                "requested_dpi": (
                    preprocess_resolution_meta["requested_dpi"]
                    if preprocess_resolution_meta else args.dpi
                ),
                "max_preprocess_megapixels": args.max_preprocess_megapixels,
                "resolution_guard": preprocess_resolution_meta,
                "skew_threshold": args.skew_threshold,
                "rotation_confidence": args.rotation_confidence,
                "enable_coarse_rotation": not args.skip_coarse_rotation,
                "enable_crop": args.enable_crop,
                "pdf_jpeg_quality": args.pdf_jpeg_quality,
                "pdf_jpeg_subsampling": args.pdf_jpeg_subsampling,
                "pdf_jpeg_optimize": args.pdf_jpeg_optimize,
                "restore_original_size": not args.no_restore_size,
                "preprocess_jobs": args.preprocess_jobs,
                "preprocess_chunk_pages": args.preprocess_chunk_pages,
                "skip_pages": args.skip_pages or None,
            } if preprocessed else None,
            "compress_skipped": (
                args.no_compress
                or preserve_original_layers
                or paddle_original_input_shortcut
                or local_native_preprocess_shortcut
            ),
            "compress_merged_into_preprocess": compress_merged_into_preprocess,
            "compress_level": (
                args.compress_level
                if not (
                    args.no_compress
                    or preserve_original_layers
                    or paddle_original_input_shortcut
                    or local_native_preprocess_shortcut
                )
                else None
            ),
            "compress_result": compress_result if compress_result else None,
            "ocr_params": {
                "mode": args.mode,
                "language": args.language,
                "output_type": args.output_type,
                "optimize": args.optimize,
                "backend": args.backend,
            },
        }

        pdf_ocr_module.run_ocr(
            input=working_input,
            output=args.output,
            backend=args.backend,
            mode=args.mode,
            language=args.language,
            output_type=args.output_type,
            optimize=args.optimize,
            skip_big=args.skip_big,
            tesseract_timeout=args.tesseract_timeout,
            jobs=args.jobs,
            sidecar=None,
            fast_web_view=None,
            preprocessed=preprocessed,
            no_rotate_pages=False,
            no_deskew=False,
            no_clean=False,
            quiet=args.quiet,
            dry_run=args.dry_run,
            env_file=args.env_file,
            no_env_file=args.no_env_file,
            api_order=args.api_order,
            local_only=args.local_only,
            paddle_model=args.paddle_model,
            paddle_api_endpoint=args.paddle_api_endpoint,
            paddle_api_endpoint_env=DEFAULT_PADDLE_API_ENDPOINT_ENV,
            paddle_api_key_env=args.paddle_api_key_env,
            paddle_api_timeout=args.paddle_api_timeout,
            paddle_api_retries=args.paddle_api_retries,
            paddle_api_extra_json=args.paddle_api_extra_json,
            paddle_api_protocol=args.paddle_api_protocol,
            no_paddle_fallback_local=args.no_paddle_fallback_local,
            paddle_vl_layout_detection=not args.paddle_vl_no_layout_detection,
            paddle_vl_no_layout_detection=args.paddle_vl_no_layout_detection,
            paddle_vl_chart_recognition=args.paddle_vl_chart_recognition,
            paddle_vl_doc_orientation=args.paddle_vl_doc_orientation,
            paddle_vl_doc_unwarping=args.paddle_vl_doc_unwarping,
            paddle_vl_layout_shape_mode=args.paddle_vl_layout_shape_mode,
            mineru_api_base=args.mineru_api_base,
            mineru_api_base_env=args.mineru_api_base_env,
            mineru_api_token_env=args.mineru_api_token_env,
            mineru_user_token_env=args.mineru_user_token_env,
            mineru_api_timeout=args.mineru_api_timeout,
            mineru_poll_interval=args.mineru_poll_interval,
            mineru_poll_timeout=args.mineru_poll_timeout,
            mineru_model_version=args.mineru_model_version,
            mineru_language=args.mineru_language,
            mineru_enable_formula=args.mineru_enable_formula,
            mineru_enable_table=args.mineru_enable_table,
            mineru_api_extra_json=args.mineru_api_extra_json,
            paddle_lang="",
            paddle_profile="auto",
            paddle_long_doc_pages=60,
            paddle_dpi=300,
            paddle_det_limit_side_len=1536,
            paddle_det_model_name="",
            paddle_rec_model_name="",
            paddle_min_score=0.5,
            paddle_skip_text_min_chars=1,
            paddle_textline_orientation=False,
            paddle_use_gpu=False,
            no_paddle_cjk_space_normalize=False,
            keep_paddle_model_source_check=False,
            paddle_model_source=None,
            original_input=str(args.input),
            preprocess_meta=preprocess_meta,
            allow_external_upload=args.allow_external_upload,
            archive_results=args.archive_results,
        )

        # 保留原始文件时间戳（创建时间 + 修改时间）
        try:
            _copy_file_times(args.input, args.output)
        except Exception:
            pass

        if not args.quiet:
            print("\n" + "=" * 60)
            print("处理完成！")
            print(f"输出文件: {args.output}")
            print("=" * 60)

    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"错误: 处理失败 - {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        for path in cleanup_files:
            try:
                p = Path(path)
                if p.exists():
                    p.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    main()
