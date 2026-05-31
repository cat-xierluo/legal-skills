#!/usr/bin/env python3
"""
PDF 预处理 + OCR（生产路径）

完整流程：
1) 可选自动解密
2) 可选页面预处理（旋转/倾斜/裁剪）
3) 可选压缩（默认 medium 200 DPI，兼顾法院上传清晰度与体积）
4) 默认调用 OCR 后端生成双层可搜索 PDF；显式 --preprocess-only 时在 OCR 前停止

说明：
- 默认后端：auto（按外部 API 顺序优先；未配置或失败时提示后回退 ocrmypdf）
- 通过直接调用 pdf-ocr.py 的 run_ocr() 函数实现，无 subprocess 开销
"""

import argparse
import importlib.util
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


def should_run_standalone_compress(
    no_compress: bool,
    preprocessed: bool,
    merge_preprocess_compress: bool,
) -> bool:
    """Whether to run the standalone compression stage."""
    if no_compress:
        return False
    return not (preprocessed and merge_preprocess_compress)


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
  # 推荐：先预处理再做双层 PDF（默认 redo）
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
        "--dpi",
        type=int,
        default=None,
        help=(
            "预处理 DPI（默认随压缩级别自动选择；合并压缩时 medium=200，"
            "禁用合并压缩时 medium=200；跳过压缩时为 300）"
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
        help="OCR 后端，默认 auto（外部 API 按顺序优先；未配置或失败时回退 ocrmypdf）",
    )
    parser.add_argument(
        "--api-order",
        help="auto 模式外部 API 顺序，逗号分隔（例如 paddle,mineru）",
    )
    parser.add_argument(
        "--mode",
        choices=["skip", "redo", "force"],
        default="redo",
        help="OCR 模式，默认 redo",
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

        # PaddleOCR API 预处理短路：仅当 API 端确实启用了方向/去畸变时才跳过本地预处理
        # 默认 useDocOrientationClassify=False, useDocUnwarping=False，不走短路
        # 如果用户显式请求了 --enable-crop，API 不做裁剪，必须走本地预处理
        api_preprocessing_shortcut = False
        if not args.skip_preprocess and not args.enable_crop:
            using_paddle_api = False
            if args.backend == "paddle_api":
                using_paddle_api = True
            elif args.backend == "auto":
                paddle_ep = args.paddle_api_endpoint
                if not paddle_ep:
                    import os as _os
                    paddle_ep = _os.getenv(DEFAULT_PADDLE_API_ENDPOINT_ENV, "").strip()
                if paddle_ep:
                    using_paddle_api = True

            if using_paddle_api:
                # 检查 --paddle-api-extra-json 是否启用了方向矫正或去畸变
                api_orientation = False
                api_unwarping = False
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
        if not args.skip_preprocess and not api_preprocessing_shortcut:
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
            elif api_preprocessing_shortcut:
                print("\n[跳过] 预处理阶段已跳过（PaddleOCR API 服务端预处理）")

        # 阶段 2：压缩（预处理后、OCR 前，减小上传体积）
        compress_result = None
        compress_merged_into_preprocess = (
            preprocessed
            and args.merge_preprocess_compress
            and not args.no_compress
        )
        if should_run_standalone_compress(
            no_compress=args.no_compress,
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
            print("\n[跳过] 压缩阶段已跳过（--no-compress）")

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
                "preprocess_skipped": args.skip_preprocess or api_preprocessing_shortcut,
                "preprocess_shortcut_reason": "paddle_api" if api_preprocessing_shortcut else None,
                "compress_skipped": args.no_compress,
                "compress_merged_into_preprocess": compress_merged_into_preprocess,
                "compress_level": args.compress_level if not args.no_compress else None,
                "compress_result": compress_result if compress_result else None,
            }

            write_preprocess_only_output(
                working_input,
                args.output,
                args.input,
                dry_run=args.dry_run,
            )

            # 归档预处理记录
            if not args.dry_run:
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
            "preprocess_skipped": args.skip_preprocess or api_preprocessing_shortcut,
            "preprocess_shortcut_reason": "paddle_api" if api_preprocessing_shortcut else None,
            "preprocess_params": {
                "dpi": args.dpi,
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
            "compress_skipped": args.no_compress,
            "compress_merged_into_preprocess": compress_merged_into_preprocess,
            "compress_level": args.compress_level if not args.no_compress else None,
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
            paddle_api_endpoint=args.paddle_api_endpoint,
            paddle_api_endpoint_env=DEFAULT_PADDLE_API_ENDPOINT_ENV,
            paddle_api_key_env=args.paddle_api_key_env,
            paddle_api_timeout=args.paddle_api_timeout,
            paddle_api_retries=args.paddle_api_retries,
            paddle_api_extra_json=args.paddle_api_extra_json,
            paddle_api_protocol=args.paddle_api_protocol,
            no_paddle_fallback_local=args.no_paddle_fallback_local,
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
            paddle_skip_text_min_chars=30,
            paddle_textline_orientation=False,
            paddle_use_gpu=False,
            no_paddle_cjk_space_normalize=False,
            keep_paddle_model_source_check=False,
            paddle_model_source=None,
            original_input=str(args.input),
            preprocess_meta=preprocess_meta,
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
