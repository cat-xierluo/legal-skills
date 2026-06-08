#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "httpx>=0.27.0",
#   "pypdfium2>=4.30.0",
# ]
# ///

"""面向法律 PDF 的高层转换入口：产出 Markdown，并写入 archive。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import sys
import tempfile
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import (  # noqa: E402
    SUPPORTED_LOCAL_SUFFIXES,
    extract_markdown_and_images,
    get_runtime_config,
    get_skill_root,
    is_pdf_file,
    parse_document,
    sanitize_name,
)
from split_pdf import (  # noqa: E402
    extract_pages_to_pdf,
    format_pages_compact,
    get_pdf_page_count,
    parse_pages_spec,
    split_pdf_by_batch_size,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将法律 PDF / 图片转换为 Markdown，并保留 archive 归档"
    )
    parser.add_argument("input", help="本地 PDF 或图片路径")
    parser.add_argument(
        "--output",
        help="输出 Markdown 路径；如果不是 .md，则按目录处理",
    )
    parser.add_argument(
        "--pages",
        help='只处理指定页码，例如 "1-20" 或 "1-5,8,10-12"（仅 PDF）',
    )
    parser.add_argument(
        "--archive-name",
        help="自定义 archive 目录名后缀，默认使用输入文件名",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="不写入 archive，仅输出 Markdown",
    )
    return parser.parse_args()


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def estimate_base64_mb(path: Path) -> float:
    return (path.stat().st_size * 4 / 3) / 1024 / 1024


def resolve_output_markdown_path(input_path: Path, output_arg: str | None) -> Path:
    if not output_arg:
        return input_path.with_suffix(".md").resolve()

    output_path = Path(output_arg).expanduser()
    if output_path.suffix.lower() == ".md":
        return output_path.resolve()

    if output_arg.endswith("/") or output_path.is_dir() or not output_path.suffix:
        return (output_path / f"{input_path.stem}.md").resolve()

    return output_path.resolve()


def resolve_images_dir(markdown_path: Path) -> Path:
    return markdown_path.with_name(f"{markdown_path.stem}_images")


def write_markdown(markdown_path: Path, content: str) -> None:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(content, encoding="utf-8")


def decode_base64_image(raw_data: str) -> bytes:
    payload = raw_data.strip()
    if payload.startswith("data:") and "," in payload:
        payload = payload.split(",", 1)[1]
    return base64.b64decode(payload)


def save_images(
    batch_outputs: list[dict[str, Any]],
    images_dir: Path,
) -> list[dict[str, str]]:
    saved: list[dict[str, str]] = []
    if images_dir.exists():
        shutil.rmtree(images_dir)
    if not any(batch["images"] for batch in batch_outputs):
        return saved

    images_dir.mkdir(parents=True, exist_ok=True)
    used_names: set[str] = set()

    for batch in batch_outputs:
        batch_label = sanitize_name(batch["label"])
        for index, (source_path, image_data) in enumerate(
            sorted(batch["images"].items()),
            start=1,
        ):
            suffix = Path(source_path).suffix.lower() or ".png"
            filename = f"{batch_label}_{index:03d}{suffix}"
            while filename in used_names:
                filename = f"{batch_label}_{index:03d}_{len(used_names):03d}{suffix}"
            used_names.add(filename)

            target_path = images_dir / filename
            if str(image_data).startswith(("http://", "https://")):
                urllib.request.urlretrieve(str(image_data), target_path)
            else:
                target_path.write_bytes(decode_base64_image(str(image_data)))

            saved.append(
                {
                    "batch": batch["label"],
                    "source": str(source_path),
                    "path": str(target_path),
                    "filename": filename,
                }
            )

    return saved


def build_archive_paths(archive_root: Path, archive_name: str) -> dict[str, Path]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = sanitize_name(archive_name)
    base = archive_root / f"{timestamp}_{slug}"
    return {
        "root": base,
        "input": base / "input",
        "output": base / "output",
        "images": base / "output" / "images",
        "batches": base / "batches",
        "metadata": base / "metadata.json",
        "result_md": base / "output" / "result.md",
        "result_json": base / "output" / "result.json",
    }


def copy_into_archive(
    archive_paths: dict[str, Path],
    input_path: Path,
    output_md_path: Path,
    images_dir: Path,
    result_json: dict[str, Any],
    batch_outputs: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> Path:
    archive_paths["input"].mkdir(parents=True, exist_ok=True)
    archive_paths["output"].mkdir(parents=True, exist_ok=True)
    archive_paths["batches"].mkdir(parents=True, exist_ok=True)

    shutil.copy2(input_path, archive_paths["input"] / input_path.name)
    shutil.copy2(output_md_path, archive_paths["result_md"])

    archive_paths["result_json"].write_text(
        json.dumps(result_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    archive_paths["metadata"].write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if images_dir.exists():
        shutil.copytree(images_dir, archive_paths["images"], dirs_exist_ok=True)

    for index, batch in enumerate(batch_outputs, start=1):
        label = sanitize_name(batch["label"])
        batch_json_path = archive_paths["batches"] / f"batch_{index:03d}_{label}.json"
        batch_json_path.write_text(
            json.dumps(batch["envelope"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return archive_paths["root"]


def build_batch_output(
    label: str,
    input_path: Path,
) -> dict[str, Any]:
    envelope = parse_document(file_path=str(input_path))
    if not envelope.get("ok"):
        error = envelope.get("error") or {}
        raise RuntimeError(f"{label} 处理失败：{error.get('message', '未知错误')}")

    text, images = extract_markdown_and_images(envelope["result"])
    if not text.strip():
        raise RuntimeError(f"{label} OCR 完成，但未提取到有效文本")

    return {
        "label": label,
        "input_path": str(input_path),
        "envelope": envelope,
        "text": text,
        "images": images,
    }


def prepare_pdf_batches(
    input_path: Path,
    pages_spec: str | None,
    temp_dir: Path,
    batch_pages: int,
    max_base64_mb: float,
) -> tuple[list[tuple[str, Path]], dict[str, Any]]:
    total_pages = get_pdf_page_count(input_path)
    selected_pages = (
        parse_pages_spec(pages_spec, total_pages)
        if pages_spec
        else list(range(total_pages))
    )
    selected_label = format_pages_compact(selected_pages)
    processed_page_count = len(selected_pages)

    estimated_subset_base64_mb = estimate_base64_mb(input_path)
    if processed_page_count and total_pages:
        estimated_subset_base64_mb *= processed_page_count / total_pages

    needs_batch = (
        processed_page_count > batch_pages or estimated_subset_base64_mb > max_base64_mb
    )

    if needs_batch:
        batch_specs = split_pdf_by_batch_size(
            input_path=input_path,
            output_dir=temp_dir / "pdf-batches",
            batch_size=batch_pages,
            page_indices=selected_pages,
        )
        batches = [(spec["label"], spec["path"]) for spec in batch_specs]
    else:
        if pages_spec:
            single_path = temp_dir / f"{input_path.stem}_selected.pdf"
            extract_pages_to_pdf(input_path, single_path, selected_pages)
            batches = [(selected_label, single_path)]
        else:
            batches = [("all-pages", input_path)]

    info = {
        "total_pages": total_pages,
        "processed_pages": processed_page_count,
        "selected_pages": selected_label,
        "needs_batch": needs_batch,
        "batch_pages": batch_pages,
        "estimated_base64_mb": round(estimated_subset_base64_mb, 2),
    }
    return batches, info


def process_input(
    input_path: Path,
    pages_spec: str | None,
    batch_pages: int,
    max_base64_mb: float,
    temp_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if is_pdf_file(input_path):
        batch_inputs, pdf_info = prepare_pdf_batches(
            input_path=input_path,
            pages_spec=pages_spec,
            temp_dir=temp_dir,
            batch_pages=batch_pages,
            max_base64_mb=max_base64_mb,
        )
    else:
        if pages_spec:
            raise ValueError("--pages 仅适用于 PDF 文件")
        batch_inputs = [(input_path.stem, input_path)]
        pdf_info = {
            "total_pages": None,
            "processed_pages": 1,
            "selected_pages": None,
            "needs_batch": False,
            "batch_pages": None,
            "estimated_base64_mb": round(estimate_base64_mb(input_path), 2),
        }

    outputs = [build_batch_output(label, path) for label, path in batch_inputs]
    return outputs, pdf_info


def main() -> int:
    args = parse_args()
    runtime = get_runtime_config()
    input_path = Path(args.input).expanduser().resolve()

    if not input_path.exists():
        print(f"错误：文件不存在：{input_path}", file=sys.stderr)
        return 1
    if input_path.suffix.lower() not in SUPPORTED_LOCAL_SUFFIXES:
        print(
            f"错误：不支持的文件类型：{input_path.suffix.lower()}",
            file=sys.stderr,
        )
        return 1

    output_md_path = resolve_output_markdown_path(input_path, args.output)
    output_images_dir = resolve_images_dir(output_md_path)
    archive_root = get_skill_root() / "archive"
    archive_name = args.archive_name or input_path.stem

    temp_dir = Path(tempfile.mkdtemp(prefix="paddleocr_convert_"))
    archive_path: Path | None = None

    try:
        batch_outputs, pdf_info = process_input(
            input_path=input_path,
            pages_spec=args.pages,
            batch_pages=runtime["batch_pages"],
            max_base64_mb=runtime["max_base64_mb"],
            temp_dir=temp_dir,
        )

        merged_text = "\n\n".join(batch["text"].strip() for batch in batch_outputs).strip()
        write_markdown(output_md_path, merged_text)
        saved_images = save_images(batch_outputs, output_images_dir)

        result_json = {
            "ok": True,
            "source": {
                "path": str(input_path),
                "name": input_path.name,
                "sha256": sha256_of_file(input_path),
                "kind": "pdf" if is_pdf_file(input_path) else "image",
            },
            "processing": {
                "mode": "batched" if len(batch_outputs) > 1 else "single",
                "batch_count": len(batch_outputs),
                **pdf_info,
            },
            "text": merged_text,
            "images": [
                {
                    "batch": image["batch"],
                    "source": image["source"],
                    "filename": image["filename"],
                    "path": image["path"],
                }
                for image in saved_images
            ],
            "batches": [
                {
                    "index": index,
                    "label": batch["label"],
                    "input_path": batch["input_path"],
                    "text_length": len(batch["text"]),
                    "image_count": len(batch["images"]),
                }
                for index, batch in enumerate(batch_outputs, start=1)
            ],
        }

        metadata = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "provider": "PaddleOCR Document Parsing API",
            "purpose": "法律 PDF / 图片 OCR，主产出为 Markdown，保留 archive 追溯链",
            "config": {
                "timeout_seconds": runtime["timeout_seconds"],
                "doc_orientation": runtime["doc_orientation"],
                "doc_unwarp": runtime["doc_unwarp"],
                "chart_recognition": runtime["chart_recognition"],
                "batch_pages": runtime["batch_pages"],
                "max_base64_mb": runtime["max_base64_mb"],
            },
            "output_markdown": str(output_md_path),
            "image_output_dir": str(output_images_dir) if saved_images else None,
        }

        if not args.no_archive:
            archive_paths = build_archive_paths(archive_root, archive_name)
            archive_path = copy_into_archive(
                archive_paths=archive_paths,
                input_path=input_path,
                output_md_path=output_md_path,
                images_dir=output_images_dir,
                result_json=result_json,
                batch_outputs=batch_outputs,
                metadata=metadata,
            )

        print("转换完成")
        print(f"Markdown: {output_md_path}")
        if saved_images:
            print(f"图片目录: {output_images_dir}")
        if archive_path:
            print(f"Archive: {archive_path}")
        print(
            "模式: "
            + ("自动分批" if len(batch_outputs) > 1 else "单次请求")
        )
        return 0
    except Exception as error:  # noqa: BLE001
        print(f"转换失败：{error}", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
