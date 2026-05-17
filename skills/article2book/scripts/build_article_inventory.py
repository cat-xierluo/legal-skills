#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

TEXT_EXTENSIONS = {".md", ".markdown", ".mdx", ".txt", ".srt", ".vtt"}
PREPROCESS_EXTENSIONS = {".docx", ".pdf"}
ALLOWED_EXTENSIONS = TEXT_EXTENSIONS | PREPROCESS_EXTENSIONS
IGNORED_DIR_NAMES = {
    ".git",
    ".obsidian",
    ".trash",
    "node_modules",
    "assets",
    "attachments",
    "images",
    "img",
    "书稿策划输出",
    "processed",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="扫描现有内容资产目录并输出可用于内容形态判断和成书分析的清单。"
    )
    parser.add_argument("source_dir", help="待扫描的素材目录")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="输出目录，脚本会在该目录下写入 article_inventory.csv/jsonl/md",
    )
    return parser.parse_args()


def should_skip(path: Path) -> bool:
    return any(part in IGNORED_DIR_NAMES for part in path.parts)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def is_preprocess_only(path: Path) -> bool:
    return path.suffix.lower() in PREPROCESS_EXTENSIONS


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text

    lines = text.splitlines()
    end_index = None
    for index in range(1, min(len(lines), 200)):
        if lines[index].strip() == "---":
            end_index = index
            break

    if end_index is None:
        return {}, text

    metadata: dict[str, str] = {}
    for raw_line in lines[1:end_index]:
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        metadata[key.strip()] = value.strip()

    body = "\n".join(lines[end_index + 1 :])
    return metadata, body


def extract_title(path: Path, metadata: dict[str, str], body: str) -> str:
    for key in ("title", "标题"):
        if metadata.get(key):
            return metadata[key]

    match = re.search(r"^#\s+(.+)$", body, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()

    return path.stem


def clean_markdown(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^>\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def make_preview(text: str, limit: int = 120) -> str:
    cleaned = clean_markdown(text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "..."


def detect_source_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".srt", ".vtt"}:
        return "逐字稿"
    if suffix in {".md", ".markdown", ".mdx"}:
        return "文章/笔记"
    if suffix == ".txt":
        return "讲稿/纯文本"
    if suffix == ".docx":
        return "需预处理：Word 文档"
    if suffix == ".pdf":
        return "需预处理：PDF 文档"
    return "其他文本"


def detect_processing_status(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return "可直接通读"
    if suffix == ".docx":
        return "需转换格式"
    if suffix == ".pdf":
        return "需提取文本或 OCR"
    return "需人工确认"


def make_preprocess_preview(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return "需先转换为 Markdown/TXT 或提取正文后再纳入通读判断。"
    if suffix == ".pdf":
        return "需先确认是否为可复制文本；扫描件需 OCR 后再纳入通读判断。"
    return "需先转换为可读文本后再纳入通读判断。"


def collect_records(source_dir: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    candidate_files = sorted(
        path
        for path in source_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in ALLOWED_EXTENSIONS
        and not should_skip(path.relative_to(source_dir))
    )

    for index, path in enumerate(candidate_files, start=1):
        relative_path = path.relative_to(source_dir).as_posix()
        preprocess_only = is_preprocess_only(path)

        if preprocess_only:
            metadata: dict[str, str] = {}
            body = ""
            cleaned = ""
            title = path.stem
            preview = make_preprocess_preview(path)
        else:
            raw_text = read_text(path)
            metadata, body = split_frontmatter(raw_text)
            cleaned = clean_markdown(body)
            title = extract_title(path, metadata, body)
            preview = make_preview(body)

        record = {
            "id": f"A-{index:03d}",
            "relative_path": relative_path,
            "title": title,
            "source_type": detect_source_type(path),
            "processing_status": detect_processing_status(path),
            "extension": path.suffix.lower(),
            "has_frontmatter": bool(metadata),
            "frontmatter_keys": ", ".join(sorted(metadata.keys())),
            "publish_status": metadata.get("公众号发布", metadata.get("published", "")),
            "chars": len(cleaned.replace(" ", "")),
            "lines": len(body.splitlines()),
            "h1_count": len(re.findall(r"^#\s+.+$", body, flags=re.MULTILINE)),
            "preview": preview,
        }
        records.append(record)

    return records


def write_csv(path: Path, records: list[dict[str, object]]) -> None:
    fieldnames = [
        "id",
        "relative_path",
        "title",
        "source_type",
        "processing_status",
        "extension",
        "has_frontmatter",
        "frontmatter_keys",
        "publish_status",
        "chars",
        "lines",
        "h1_count",
        "preview",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_markdown(path: Path, records: list[dict[str, object]]) -> None:
    lines = [
        "# 素材清单",
        "",
        f"- 共扫描到 **{len(records)}** 份候选素材",
        "",
        "| 编号 | 标题 | 素材类型 | 处理状态 | 路径 | 字数估计 | 发布状态 | 预览 |",
        "|------|------|----------|----------|------|----------|----------|------|",
    ]

    for record in records:
        preview = str(record["preview"]).replace("|", "/")
        title = str(record["title"]).replace("|", "/")
        source_type = str(record["source_type"]).replace("|", "/")
        processing_status = str(record["processing_status"]).replace("|", "/")
        relative_path = str(record["relative_path"]).replace("|", "/")
        publish_status = str(record["publish_status"] or "未知").replace("|", "/")
        lines.append(
            f"| {record['id']} | {title} | {source_type} | {processing_status} | `{relative_path}` | {record['chars']} | {publish_status} | {preview} |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    source_dir = Path(args.source_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    records = collect_records(source_dir)

    write_csv(output_dir / "article_inventory.csv", records)
    write_jsonl(output_dir / "article_inventory.jsonl", records)
    write_markdown(output_dir / "article_inventory.md", records)

    summary = {
        "source_dir": str(source_dir),
        "output_dir": str(output_dir),
        "source_count": len(records),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
