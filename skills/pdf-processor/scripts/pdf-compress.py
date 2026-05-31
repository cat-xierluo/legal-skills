#!/usr/bin/env python3
"""
PDF 压缩工具

使用流式替换方法压缩 PDF，自动保留批注、文字层、书签、色彩空间和文件时间戳。
"""

import io
import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError as e:
    print(f"错误: 缺少必需的依赖 - {e}")
    print("\n请运行以下命令安装:")
    print("  pip install pymupdf")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    Image = None


PRESETS = {
    "low": {"quality": 85, "max_dimension": 4200, "grayscale": False, "min_pixels": 500_000},
    "medium": {"quality": 65, "max_dimension": 2000, "grayscale": False, "min_pixels": 250_000},
    "high": {"quality": 45, "max_dimension": 1600, "grayscale": False, "min_pixels": 150_000},
}

if Image is not None:
    _resampling = getattr(Image, "Resampling", Image)
    RESAMPLE_FILTER = _resampling.LANCZOS
else:
    RESAMPLE_FILTER = None


def log(message: str, quiet: bool = False) -> None:
    if not quiet:
        print(message)


def get_file_size_mb(file_path: Path) -> float:
    return file_path.stat().st_size / (1024 * 1024)


def count_annotations(doc) -> int:
    total = 0
    for page in doc:
        annot = page.first_annot
        while annot:
            total += 1
            annot = annot.next
    return total


def get_image_colorspace(doc, xref: int) -> str:
    try:
        obj_str = doc.xref_object(xref)
        for cs_name in ("/DeviceGray", "/DeviceRGB", "/DeviceCMYK"):
            if cs_name in obj_str:
                return cs_name
    except Exception:
        pass
    return "Unknown"


def get_file_times(file_path: Path) -> tuple[float, float]:
    stat = file_path.stat()
    mtime = stat.st_mtime
    birthtime = getattr(stat, "st_birthtime", mtime)
    return birthtime, mtime


def set_file_times(file_path: Path, birthtime: float, mtime: float) -> None:
    os.utime(file_path, (mtime, mtime))
    if platform.system() == "Darwin":
        try:
            dt = datetime.fromtimestamp(birthtime)
            date_str = dt.strftime("%m/%d/%Y %H:%M:%S")
            subprocess.run(
                ["SetFile", "-d", date_str, str(file_path)],
                check=True, capture_output=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass


def normalize_pixmap(doc, xref: int, grayscale: bool):
    """返回 (pixmap, None) 或 (None, reason)。"""
    pix = fitz.Pixmap(doc, xref)
    if pix.colorspace is None:
        return None, "mask-image"
    if pix.alpha:
        return None, "alpha-image"
    if grayscale and pix.colorspace.n != 1:
        pix = fitz.Pixmap(fitz.csGRAY, pix)
    elif pix.colorspace.n not in (1, 3):
        pix = fitz.Pixmap(fitz.csRGB, pix)
    return pix, None


def encode_jpeg(pix, quality: int, max_dimension: int, force_mode: str | None = None) -> tuple[bytes, bool]:
    if Image is None or max(pix.width, pix.height) <= max_dimension:
        return pix.tobytes("jpg", jpg_quality=quality), False
    mode = force_mode or ("L" if pix.colorspace and pix.colorspace.n == 1 else "RGB")
    image = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    image.thumbnail((max_dimension, max_dimension), RESAMPLE_FILTER)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue(), True


def compress_stream(doc, profile: dict, quiet: bool) -> dict:
    images_seen = 0
    images_processed = 0
    images_skipped = 0
    used_downscale = False
    processed_xrefs: set[int] = set()

    for page_index in range(len(doc)):
        page = doc[page_index]
        page_images = page.get_images(full=True)
        if page_images:
            log(f"扫描第 {page_index + 1}/{len(doc)} 页图像资源...", quiet)

        for image_info in page_images:
            xref = image_info[0]
            if xref in processed_xrefs:
                continue
            processed_xrefs.add(xref)
            images_seen += 1

            width, height = image_info[2], image_info[3]
            if width * height < profile["min_pixels"]:
                images_skipped += 1
                continue

            try:
                orig_cs = get_image_colorspace(doc, xref)
                force_mode = "L" if orig_cs == "DeviceGray" and not profile["grayscale"] else None

                pix, skip_reason = normalize_pixmap(doc, xref, profile["grayscale"])
                if skip_reason:
                    images_skipped += 1
                    continue

                if orig_cs == "DeviceGray" and not profile["grayscale"] and pix.colorspace and pix.colorspace.n != 1:
                    pix = fitz.Pixmap(fitz.csGRAY, pix)

                encoded, downscaled = encode_jpeg(pix, quality=profile["quality"], max_dimension=profile["max_dimension"], force_mode=force_mode)

                doc.update_stream(xref, encoded, compress=0)
                doc.xref_set_key(xref, "Filter", "/DCTDecode")

                if downscaled and Image is not None:
                    img = Image.open(io.BytesIO(encoded))
                    doc.xref_set_key(xref, "Width", str(img.width))
                    doc.xref_set_key(xref, "Height", str(img.height))

                images_processed += 1
                used_downscale = used_downscale or downscaled
            except Exception as exc:
                images_skipped += 1
                log(f"警告: 图像 xref={xref} 压缩失败，已跳过。原因: {exc}", quiet)

    return {
        "images_seen": images_seen,
        "images_processed": images_processed,
        "images_skipped": images_skipped,
        "used_downscale": used_downscale,
        "total_pages": len(doc),
    }


def compress_pdf(
    input_pdf: str,
    output_pdf: str,
    compression_level: str = "medium",
    remove_metadata: bool = False,
    quiet: bool = False,
) -> dict:
    input_path = Path(input_pdf)
    output_path = Path(output_pdf)

    if input_path.resolve() == output_path.resolve():
        raise ValueError("输出文件不能与输入文件相同，请提供新的输出路径")

    original_size = get_file_size_mb(input_path)
    profile = dict(PRESETS[compression_level])

    birthtime, mtime = get_file_times(input_path)

    log(f"正在处理 PDF: {input_pdf}", quiet)
    log(f"原始大小: {original_size:.2f} MB", quiet)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with fitz.open(input_pdf) as doc:
        if doc.is_encrypted:
            if not doc.authenticate(""):
                raise ValueError("PDF 已加密，请先使用 pdf-decrypt.py 解密")

        if len(doc) == 0:
            raise ValueError("输入 PDF 没有页面")

        annot_count = count_annotations(doc)
        log(f"批注: {'发现 ' + str(annot_count) + ' 个' if annot_count > 0 else '无'}", quiet)

        if remove_metadata:
            doc.set_metadata({})

        stats = compress_stream(doc, profile, quiet)

        garbage_level = 3 if annot_count > 0 else 4
        doc.save(
            output_pdf,
            garbage=garbage_level,
            clean=1, deflate=1, deflate_images=1, deflate_fonts=1,
            use_objstms=1, compression_effort=100,
            preserve_metadata=0 if remove_metadata else 1,
        )

    set_file_times(output_path, birthtime, mtime)

    compressed_size = get_file_size_mb(output_path)
    reduction = original_size - compressed_size
    reduction_percent = (reduction / original_size) * 100 if original_size > 0 else 0

    return {
        "original_size_mb": original_size,
        "compressed_size_mb": compressed_size,
        "reduction_mb": reduction,
        "reduction_percent": reduction_percent,
        "total_pages": stats["total_pages"],
        "compression_level": compression_level,
        "annotations_found": annot_count,
        "images_seen": stats["images_seen"],
        "images_processed": stats["images_processed"],
        "images_skipped": stats["images_skipped"],
        "used_pillow": Image is not None,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="PDF 压缩工具 - 保留批注、文字层和书签",
        epilog="""
示例:
  python pdf-compress.py -i input.pdf -o output.pdf
  python pdf-compress.py -i input.pdf -o output.pdf --level high

压缩级别:
  low     质量 85, ~300 DPI, 适用打印
  medium  质量 65, ~200 DPI, 适用屏幕阅读（默认）
  high    质量 45, ~150 DPI, 适用归档
        """,
    )

    parser.add_argument("--input", "-i", required=True, help="输入 PDF 文件")
    parser.add_argument("--output", "-o", required=True, help="输出 PDF 文件")
    parser.add_argument("--level", "-l", choices=["low", "medium", "high"], default="medium", help="压缩级别（默认: medium）")
    parser.add_argument("--remove-metadata", "-m", action="store_true", help="移除 PDF 元数据")
    parser.add_argument("--quiet", action="store_true", help="静默模式")

    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"错误: 输入文件不存在: {args.input}", file=sys.stderr)
        sys.exit(1)

    try:
        result = compress_pdf(args.input, args.output, args.level, args.remove_metadata, args.quiet)
    except Exception as exc:
        print(f"\n错误: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n" + "=" * 50)
    print("压缩完成！")
    print("=" * 50)
    print(f"原始大小: {result['original_size_mb']:.2f} MB")
    print(f"压缩后大小: {result['compressed_size_mb']:.2f} MB")
    print(f"减少: {result['reduction_mb']:.2f} MB ({result['reduction_percent']:.1f}%)")
    print(f"总页数: {result['total_pages']}")
    print(f"压缩级别: {result['compression_level']}")
    print(f"批注: {'保留 ' + str(result['annotations_found']) + ' 个' if result['annotations_found'] > 0 else '无'}")
    print(f"处理图像: {result['images_processed']}/{result['images_seen']}（跳过 {result['images_skipped']}）")
    if Image is None:
        print("提示: 未安装 Pillow，仅执行图像重编码，不会额外缩放大图。")
    print("=" * 50)


if __name__ == "__main__":
    main()
