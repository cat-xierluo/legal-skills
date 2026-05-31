#!/usr/bin/env python3
"""Run repeatable end-to-end OCR benchmarks for pdf-processor."""

import argparse
import csv
import json
import platform
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import fitz
except ImportError as e:
    from pdf_runtime import exit_for_missing_dependencies

    exit_for_missing_dependencies(
        "PDF OCR benchmark",
        missing_python=["pymupdf"],
        install_commands=["pip install pymupdf"],
        extra_notes=[f"原始错误: {e}"],
    )


SCRIPT_DIR = Path(__file__).resolve().parent
PREPROCESS_OCR_SCRIPT = SCRIPT_DIR / "pdf-preprocess-ocr.py"


def parse_keyword_args(keyword_values: list[str] | None) -> list[str]:
    """Parse repeated/comma-separated keyword arguments."""
    keywords: list[str] = []
    for value in keyword_values or []:
        for keyword in value.split(","):
            keyword = keyword.strip()
            if keyword:
                keywords.append(keyword)
    return keywords


def pdf_metrics(
    pdf_path: str | Path,
    *,
    reference_page_sizes: list[tuple[float, float]] | None = None,
    keywords: list[str] | None = None,
) -> dict[str, Any]:
    """Collect structural and searchable-text metrics from a PDF."""
    pdf_path = Path(pdf_path)
    with fitz.open(pdf_path) as doc:
        page_sizes = [
            (round(float(page.rect.width), 2), round(float(page.rect.height), 2))
            for page in doc
        ]
        page_texts = [page.get_text() or "" for page in doc]

    text = "\n".join(page_texts)
    text_stripped = text.strip()
    keyword_hits = {
        keyword: text.count(keyword)
        for keyword in (keywords or [])
    }
    page_text_chars = [len(page_text.strip()) for page_text in page_texts]

    return {
        "path": str(pdf_path),
        "exists": pdf_path.exists(),
        "size_bytes": pdf_path.stat().st_size if pdf_path.exists() else 0,
        "size_mb": round(pdf_path.stat().st_size / 1024 / 1024, 4) if pdf_path.exists() else 0.0,
        "pages": len(page_sizes),
        "page_sizes": page_sizes,
        "page_sizes_match": (
            page_sizes == reference_page_sizes
            if reference_page_sizes is not None
            else None
        ),
        "text_chars": len(text_stripped),
        "searchable": bool(text_stripped),
        "page_text_chars": page_text_chars,
        "pages_with_text": sum(1 for count in page_text_chars if count > 0),
        "keyword_hits": keyword_hits,
    }


def create_sample_pdf(input_path: Path, output_dir: Path, sample_pages: int) -> Path:
    """Create a first-N-pages sample PDF for quick benchmark runs."""
    if sample_pages <= 0:
        return input_path

    sample_path = output_dir / f"{input_path.stem}_sample_{sample_pages}p.pdf"
    with fitz.open(input_path) as src:
        page_count = len(src)
        if page_count == 0:
            raise ValueError(f"输入 PDF 无页面: {input_path}")
        last_page = min(sample_pages, page_count) - 1
        dst = fitz.open()
        try:
            dst.insert_pdf(src, from_page=0, to_page=last_page)
            dst.save(sample_path)
        finally:
            dst.close()
    return sample_path


def strip_remainder_separator(values: list[str]) -> list[str]:
    """Remove argparse REMAINDER separator when present."""
    if values and values[0] == "--":
        return values[1:]
    return values


def build_ocr_command(args: argparse.Namespace, input_path: Path, output_path: Path) -> list[str]:
    """Build the pdf-preprocess-ocr.py command for one benchmark iteration."""
    command = [
        sys.executable,
        str(PREPROCESS_OCR_SCRIPT),
        "-i",
        str(input_path),
        "-o",
        str(output_path),
        "--backend",
        args.backend,
        "--mode",
        args.mode,
        "--language",
        args.language,
        "--output-type",
        args.output_type,
        "--optimize",
        str(args.optimize),
        "--compress-level",
        args.compress_level,
        "--tesseract-timeout",
        str(args.tesseract_timeout),
    ]

    if args.no_env_file:
        command.append("--no-env-file")
    if args.env_file:
        command.extend(["--env-file", args.env_file])
    if args.api_order:
        command.extend(["--api-order", args.api_order])
    if args.jobs is not None:
        command.extend(["--jobs", str(args.jobs)])

    if args.skip_preprocess:
        command.append("--skip-preprocess")
    else:
        if args.skip_coarse_rotation:
            command.append("--skip-coarse-rotation")
        if args.preprocess_jobs is not None:
            command.extend(["--preprocess-jobs", str(args.preprocess_jobs)])
        if args.preprocess_chunk_pages is not None:
            command.extend(["--preprocess-chunk-pages", str(args.preprocess_chunk_pages)])
        if args.dpi is not None:
            command.extend(["--dpi", str(args.dpi)])
        if args.skew_threshold is not None:
            command.extend(["--skew-threshold", str(args.skew_threshold)])
        if args.pdf_jpeg_quality is not None:
            command.extend(["--pdf-jpeg-quality", str(args.pdf_jpeg_quality)])
        if args.enable_crop:
            command.append("--enable-crop")
        if args.no_compress:
            command.append("--no-compress")
        if args.no_merge_preprocess_compress:
            command.append("--no-merge-preprocess-compress")

    command.extend(strip_remainder_separator(args.passthrough))
    return command


def run_iteration(
    args: argparse.Namespace,
    *,
    benchmark_input: Path,
    input_metrics: dict[str, Any],
    output_dir: Path,
    iteration: int,
    keywords: list[str],
) -> dict[str, Any]:
    """Run one OCR benchmark iteration and collect result metrics."""
    label = args.label or benchmark_input.stem
    iteration_dir = output_dir / f"{label}_run_{iteration:02d}"
    iteration_dir.mkdir(parents=True, exist_ok=True)
    output_pdf = iteration_dir / f"{label}_ocr.pdf"
    stdout_path = iteration_dir / "stdout.log"
    stderr_path = iteration_dir / "stderr.log"

    command = build_ocr_command(args, benchmark_input, output_pdf)
    started_at = datetime.now().isoformat(timespec="seconds")
    start = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=str(SCRIPT_DIR.parent),
        text=True,
        capture_output=True,
        timeout=args.timeout,
    )
    wall_seconds = time.perf_counter() - start

    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")

    output_metrics = None
    if completed.returncode == 0 and output_pdf.exists():
        output_metrics = pdf_metrics(
            output_pdf,
            reference_page_sizes=input_metrics["page_sizes"],
            keywords=keywords,
        )

    return {
        "label": label,
        "iteration": iteration,
        "started_at": started_at,
        "wall_seconds": round(wall_seconds, 4),
        "returncode": completed.returncode,
        "command": command,
        "input": input_metrics,
        "output": output_metrics,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "output_pdf": str(output_pdf) if output_pdf.exists() else None,
    }


def write_csv_report(results: list[dict[str, Any]], csv_path: Path) -> None:
    """Write a flat CSV summary for spreadsheet comparison."""
    fieldnames = [
        "label",
        "iteration",
        "returncode",
        "wall_seconds",
        "input_pages",
        "output_pages",
        "input_size_mb",
        "output_size_mb",
        "output_searchable",
        "output_text_chars",
        "output_pages_with_text",
        "page_sizes_match",
        "keyword_hits_json",
        "output_pdf",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            output = result.get("output") or {}
            writer.writerow({
                "label": result["label"],
                "iteration": result["iteration"],
                "returncode": result["returncode"],
                "wall_seconds": result["wall_seconds"],
                "input_pages": result["input"]["pages"],
                "output_pages": output.get("pages"),
                "input_size_mb": result["input"]["size_mb"],
                "output_size_mb": output.get("size_mb"),
                "output_searchable": output.get("searchable"),
                "output_text_chars": output.get("text_chars"),
                "output_pages_with_text": output.get("pages_with_text"),
                "page_sizes_match": output.get("page_sizes_match"),
                "keyword_hits_json": json.dumps(output.get("keyword_hits", {}), ensure_ascii=False),
                "output_pdf": result.get("output_pdf"),
            })


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="运行 pdf-processor 预处理 + OCR 端到端基准，并输出 JSON/CSV 报告。",
    )
    parser.add_argument("--input", "-i", required=True, help="输入 PDF")
    parser.add_argument("--output-dir", help="基准输出目录；默认写入 /tmp")
    parser.add_argument("--label", help="本次基准标签，默认使用输入文件名")
    parser.add_argument("--iterations", type=int, default=1, help="重复次数，默认 1")
    parser.add_argument("--sample-pages", type=int, default=0, help="仅抽取前 N 页做快速基准，默认 0 表示全量")
    parser.add_argument("--timeout", type=int, default=3600, help="单次运行超时秒数，默认 3600")
    parser.add_argument("--keyword", action="append", help="检索关键词；可重复或用逗号分隔")

    parser.add_argument("--backend", default="local_ocrmypdf", choices=["auto", "local_ocrmypdf", "paddle_api", "mineru_api"])
    parser.add_argument("--mode", default="redo", choices=["skip", "redo", "force"])
    parser.add_argument("--language", default="chi_sim+eng")
    parser.add_argument("--output-type", default="pdf", choices=["pdf", "pdfa"])
    parser.add_argument("--optimize", type=int, default=0, choices=[0, 1, 2, 3])
    parser.add_argument("--jobs", type=int, help="OCR 并行任务数")
    parser.add_argument("--tesseract-timeout", type=int, default=180)
    parser.add_argument("--api-order")
    parser.add_argument("--env-file")
    parser.add_argument("--no-env-file", action="store_true")

    parser.add_argument("--skip-preprocess", action="store_true")
    parser.add_argument("--skip-coarse-rotation", action="store_true")
    parser.add_argument("--preprocess-jobs", type=int, default=6)
    parser.add_argument("--preprocess-chunk-pages", type=int, default=80)
    parser.add_argument("--dpi", type=int)
    parser.add_argument("--skew-threshold", type=float)
    parser.add_argument("--pdf-jpeg-quality", type=int)
    parser.add_argument("--enable-crop", action="store_true")
    parser.add_argument("--no-compress", action="store_true")
    parser.add_argument("--compress-level", default="medium", choices=["low", "medium", "high"])
    parser.add_argument("--no-merge-preprocess-compress", action="store_true")
    parser.add_argument(
        "passthrough",
        nargs=argparse.REMAINDER,
        help="传给 pdf-preprocess-ocr.py 的额外参数；放在 -- 之后。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        print(f"错误: 输入文件不存在: {input_path}", file=sys.stderr)
        return 1
    if args.iterations < 1:
        print("错误: --iterations 必须 >= 1", file=sys.stderr)
        return 1

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    default_root = Path(tempfile.gettempdir()) / "pdf-processor-ocr-benchmarks"
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else default_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    benchmark_input = create_sample_pdf(input_path, output_dir, args.sample_pages)
    keywords = parse_keyword_args(args.keyword)
    input_metrics = pdf_metrics(benchmark_input, keywords=keywords)

    results = [
        run_iteration(
            args,
            benchmark_input=benchmark_input,
            input_metrics=input_metrics,
            output_dir=output_dir,
            iteration=iteration,
            keywords=keywords,
        )
        for iteration in range(1, args.iterations + 1)
    ]

    report = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "system": {
            "platform": platform.platform(),
            "python": sys.version,
        },
        "source_input": str(input_path),
        "benchmark_input": str(benchmark_input),
        "sample_pages": args.sample_pages,
        "output_dir": str(output_dir),
        "results": results,
    }

    json_path = output_dir / "benchmark_report.json"
    csv_path = output_dir / "benchmark_report.csv"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv_report(results, csv_path)

    print(f"benchmark_report_json={json_path}")
    print(f"benchmark_report_csv={csv_path}")
    for result in results:
        output = result.get("output") or {}
        print(
            "run={iteration} returncode={returncode} wall_seconds={wall_seconds} "
            "pages={pages} searchable={searchable} text_chars={text_chars} size_mb={size_mb}".format(
                iteration=result["iteration"],
                returncode=result["returncode"],
                wall_seconds=result["wall_seconds"],
                pages=output.get("pages"),
                searchable=output.get("searchable"),
                text_chars=output.get("text_chars"),
                size_mb=output.get("size_mb"),
            )
        )

    return 0 if all(result["returncode"] == 0 for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
