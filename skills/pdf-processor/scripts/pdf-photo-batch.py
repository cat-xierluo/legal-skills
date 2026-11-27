#!/usr/bin/env python3
"""Normalize multiple photographed pages and merge them into one PDF."""

import argparse
import importlib.util
import json
import os
import re
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz


SCRIPT_DIR = Path(__file__).resolve().parent
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


def load_normalizer():
    spec = importlib.util.spec_from_file_location(
        "pdf_photo_normalize", SCRIPT_DIR / "pdf-photo-normalize.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load pdf-photo-normalize.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _natural_key(path: Path) -> tuple[list[str | int], str, str]:
    stem_key = [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", path.stem)
    ]
    return stem_key, path.suffix.lower(), path.name.lower()


def collect_photo_paths(inputs: list[str]) -> list[Path]:
    photos: list[Path] = []
    for input_value in inputs:
        source = Path(input_value)
        if source.is_file():
            photos.append(source)
        elif source.is_dir():
            photos.extend(
                path
                for path in sorted(source.iterdir(), key=_natural_key)
                if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
            )
        else:
            raise ValueError(f"输入路径不存在: {source}")

    normalized = [path.resolve() for path in photos]
    if not normalized:
        raise ValueError("未找到可处理的单帧拍照件")
    if len(normalized) != len(set(normalized)):
        raise ValueError("输入列表包含重复照片")
    unsupported = [path for path in normalized if path.suffix.lower() not in SUPPORTED_EXTENSIONS]
    if unsupported:
        raise ValueError(f"不支持的拍照件格式: {unsupported[0].suffix}")
    return normalized


def load_quad_overrides(
    path: str | Path, photos: list[Path],
) -> dict[str, list[list[float]]]:
    """Load per-photo normalized corners keyed by file name."""
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"四角覆盖文件不存在: {source}")
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("四角覆盖文件必须是 JSON 对象，键为文件名，值为 4 个 [x, y] 点")
    overrides: dict[str, list[list[float]]] = {}
    for key, points in data.items():
        if not isinstance(points, (list, tuple)) or len(points) != 4:
            raise ValueError(f"四角覆盖格式错误: {key} 应为 4 个 [x, y] 点")
        name = Path(key).name
        if name in overrides:
            raise ValueError(f"四角覆盖文件存在重复文件名: {name}")
        overrides[name] = [[float(value) for value in point] for point in points]
    unknown = sorted(set(overrides) - {photo.name for photo in photos})
    if unknown:
        raise ValueError(f"四角覆盖文件包含未匹配的照片: {unknown[0]}")
    return overrides


def normalize_photo_batch(
    inputs: list[str | Path],
    output_path: str | Path,
    *,
    dpi: int = 300,
    jpeg_quality: int = 90,
    page_size: str = "a4",
    rotation: str = "auto",
    illumination_strength: float = 0.78,
    contrast_strength: float = 0.7,
    quad_file: str | Path | None = None,
    binarize: bool = False,
    binarize_high: float = 235.0,
    binarize_low: float = 195.0,
    report_file: str | Path | None = None,
) -> dict:
    """Normalize each photo, preserve natural filename order, and merge one PDF."""
    normalizer = load_normalizer()
    output = Path(output_path)
    report_path = Path(report_file) if report_file is not None else None
    quad_path = Path(quad_file) if quad_file is not None else None
    destinations = [destination for destination in (output, report_path) if destination is not None]
    if any(destination.exists() for destination in destinations):
        raise ValueError("输出 PDF 和报告必须指向尚不存在的新文件")
    if not output.parent.is_dir():
        raise ValueError(f"输出目录不存在: {output.parent}")
    if report_path is not None and not report_path.parent.is_dir():
        raise ValueError(f"报告目录不存在: {report_path.parent}")
    if not 0 <= binarize_low < binarize_high <= 255:
        raise ValueError("黑白化阈值必须满足 0 <= 下阈值 < 上阈值 <= 255")

    photos = collect_photo_paths([*inputs])
    quads = load_quad_overrides(quad_path, photos) if quad_path is not None else {}
    if report_path is not None and output.resolve() == report_path.resolve():
        raise ValueError("输出 PDF 和报告必须使用不同文件")
    if output.resolve() in {path.resolve() for path in photos}:
        raise ValueError("输出 PDF 不能覆盖输入照片")
    page_reports = []
    with TemporaryDirectory(prefix=".pdf-photo-batch-", dir=output.parent) as tempdir:
        temporary_root = Path(tempdir)
        page_pdfs = []
        for page_number, photo in enumerate(photos, start=1):
            page_pdf = temporary_root / f"page-{page_number:04d}.pdf"
            page_report = temporary_root / f"page-{page_number:04d}.json"
            metadata = normalizer.normalize_photo_pdf(
                photo,
                page_pdf,
                dpi=dpi,
                jpeg_quality=jpeg_quality,
                page_size=page_size,
                rotation=rotation,
                illumination_strength=illumination_strength,
                contrast_strength=contrast_strength,
                quad=quads.get(photo.name),
                binarize=binarize,
                binarize_high=binarize_high,
                binarize_low=binarize_low,
                report_file=page_report,
            )
            metadata = dict(metadata)
            metadata.pop("output", None)
            metadata["page_number"] = page_number
            page_reports.append(metadata)
            page_pdfs.append(page_pdf)

        temporary_pdf = temporary_root / "merged.pdf"
        with fitz.open() as merged:
            for page_pdf in page_pdfs:
                with fitz.open(page_pdf) as page_document:
                    if len(page_document) != 1:
                        raise ValueError(f"单张照片生成了多页 PDF: {page_pdf.name}")
                    merged.insert_pdf(page_document)
            if len(merged) != len(page_pdfs):
                raise ValueError("合并后的页数与照片数量不一致")
            merged.save(temporary_pdf, garbage=4, deflate=True)

        final_report = {
            "output": str(output),
            "photo_count": len(photos),
            "page_count": len(page_pdfs),
            "photos": page_reports,
            "dpi": dpi,
        }
        if quad_path is not None:
            final_report["quad_file"] = str(quad_path)
        staged_report = temporary_root / "report.json"
        if report_path is not None:
            staged_report.write_text(
                json.dumps(final_report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        published: list[Path] = []
        try:
            if report_path is not None:
                _publish_exclusive(staged_report, report_path)
                published.append(report_path)
            _publish_exclusive(temporary_pdf, output)
        except Exception:
            rollback_errors = []
            for destination in published:
                try:
                    destination.unlink()
                except OSError as rollback_error:
                    rollback_errors.append(rollback_error)
            if rollback_errors:
                raise RuntimeError("批量 PDF 发布失败且回滚报告失败") from rollback_errors[0]
            raise
    return final_report


def _publish_exclusive(source: Path, destination: Path) -> None:
    payload = source.read_bytes()
    created = False
    try:
        exclusive = os.open(
            destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        created = True
        with os.fdopen(exclusive, "wb") as output:
            output.write(payload)
    except Exception:
        if created:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="把多张拍照文书逐页规整并合并为一个 PDF",
    )
    parser.add_argument(
        "-i", "--input", required=True, nargs="+",
        help="一个或多个图像文件；也可传目录，目录内按自然文件名排序",
    )
    parser.add_argument("-o", "--output", required=True, help="输出合并 PDF")
    parser.add_argument("--dpi", type=int, default=300, help="输出 DPI，默认 300")
    parser.add_argument("--jpeg-quality", type=int, default=90, help="PDF JPEG 质量，默认 90")
    parser.add_argument(
        "--page-size", choices=["auto", "a4", "letter", "original"], default="a4",
        help="默认 A4；完整纸边可铺满 A4，内容主体按可见比例等比排版",
    )
    parser.add_argument(
        "--rotate", choices=["auto", "0", "90", "180", "270"], default="auto",
        help="粗方向；auto 使用 Tesseract OSD",
    )
    parser.add_argument("--illumination-strength", type=float, default=0.78)
    parser.add_argument("--contrast-strength", type=float, default=0.7)
    parser.add_argument(
        "--quad-file",
        help="JSON 四角覆盖表，键为照片文件名，值为 4 个 [x, y] 归一化坐标点",
    )
    parser.add_argument(
        "--bw", "--black-white", dest="bw", action="store_true",
        help="输出黑白页面：背景归一后把墨迹映射为纯黑，保留签名与印章边缘",
    )
    parser.add_argument(
        "--bw-high", type=float, default=235.0,
        help="黑白化上阈值，高于该值视为纸面，默认 235",
    )
    parser.add_argument(
        "--bw-low", type=float, default=195.0,
        help="黑白化下阈值，低于该值视为墨迹，默认 195",
    )
    parser.add_argument("--report", help="保存逐页和合并 JSON 报告")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not 1 <= args.dpi <= 600:
        parser.error("输出 DPI 必须在 1-600")
    if not 1 <= args.jpeg_quality <= 100:
        parser.error("JPEG 质量必须在 1-100")
    if not 0 <= args.illumination_strength <= 1:
        parser.error("阴影归一化强度必须在 0-1")
    if not 0 <= args.contrast_strength <= 1:
        parser.error("对比度增强强度必须在 0-1")
    if not 0 <= args.bw_low < args.bw_high <= 255:
        parser.error("黑白化阈值必须满足 0 <= 下阈值 < 上阈值 <= 255")

    try:
        report = normalize_photo_batch(
            args.input,
            args.output,
            dpi=args.dpi,
            jpeg_quality=args.jpeg_quality,
            page_size=args.page_size,
            rotation=args.rotate,
            illumination_strength=args.illumination_strength,
            contrast_strength=args.contrast_strength,
            quad_file=args.quad_file,
            binarize=args.bw,
            binarize_high=args.bw_high,
            binarize_low=args.bw_low,
            report_file=args.report,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    print("拍照件批量规整合并完成")
    print(f"照片数量: {report['photo_count']}；PDF 页数: {report['page_count']}")
    sources = [Path(item) for item in args.input]
    print(f"输入: {', '.join(str(source) for source in sources)}")
    print(f"输出文件: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
