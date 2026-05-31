"""
OCR dump/resume 模块 + Agent 修正。

工作流：
  Step 1: pdf-ocr.py -i input.pdf -o output.pdf --ocr-dump /tmp/ocr_dump.json
          → OCR 识别，结果存入 JSON，同时生成可读文本，不生成 PDF
  Step 2: agent 审查可读文本，发现 OCR 错误
          → 直接编辑 dump JSON 文件中的 text 字段，或生成 corrections 文件
  Step 3: pdf-ocr.py -i input.pdf -o output.pdf --ocr-resume /tmp/ocr_dump.json
          → 加载 dump（含 agent 修正）+ 生成双层 PDF
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = _SKILL_ROOT / "archive"


# ---------- 序列化 / 反序列化 ----------

def _entries_to_serializable(entries: list[dict]) -> list[dict]:
    """将 page_entries 转为 JSON 可序列化格式。"""
    result = []
    for entry in entries:
        rows = []
        for text, score, poly in entry.get("rows", []):
            rows.append({
                "text": text,
                "score": score,
                "poly": poly,
            })
        result.append({
            "rows": rows,
            "width": entry.get("width"),
            "height": entry.get("height"),
        })
    return result


def _entries_from_serializable(data: list[dict]) -> list[dict]:
    """从 JSON 格式恢复 page_entries（含 tuple rows）。"""
    entries = []
    for page in data:
        rows = []
        for block in page.get("rows", []):
            text = block.get("text", "")
            score = block.get("score", 1.0)
            poly = block.get("poly", [[0, 0], [0, 0], [0, 0], [0, 0]])
            rows.append((text, score, poly))
        entries.append({
            "rows": rows,
            "width": page.get("width"),
            "height": page.get("height"),
        })
    return entries


def dump_page_entries(
    entries: list[dict],
    path: str | Path,
    source: str = "",
    model: str = "",
) -> None:
    """将 OCR 结果保存为 JSON 文件，供 agent 审查。"""
    p = Path(path)
    data = {
        "source": source,
        "model": model,
        "total_pages": len(entries),
        "pages": _entries_to_serializable(entries),
    }

    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_page_entries(path: str | Path) -> tuple[list[dict], dict]:
    """从 dump 文件加载 OCR 结果。

    Returns:
        (page_entries, metadata_dict)
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"OCR dump 文件不存在: {p}")

    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    pages = data.get("pages", [])
    entries = _entries_from_serializable(pages)
    metadata = {
        "source": data.get("source", ""),
        "model": data.get("model", ""),
    }
    return entries, metadata


# ---------- 可读文本生成 ----------

def generate_readable_text(entries: list[dict]) -> str:
    """从 page_entries 生成连续可读文本，同段落行自动拼接，段落间空行分隔。"""
    paragraphs: list[str] = []
    current: list[str] = []
    had_wrap = False
    prev_y_bot: float | None = None
    prev_x_left: float = 0.0
    prev_h: float = 0.0

    for entry in entries:
        for text, score, poly in entry.get("rows", []):
            content = text.strip()
            if not content or score <= 0:
                continue

            if not poly or len(poly) < 4:
                if current:
                    paragraphs.append("".join(current))
                    current = []
                paragraphs.append(content)
                prev_y_bot = None
                had_wrap = False
                continue

            ys = [p[1] for p in poly]
            xs = [p[0] for p in poly]
            y_top = min(ys)
            y_bot = max(ys)
            x_left = min(xs)
            h = max(y_bot - y_top, 1.0)

            if prev_y_bot is None:
                current = [content]
                had_wrap = False
                prev_y_bot = y_bot
                prev_x_left = x_left
                prev_h = h
                continue

            y_gap = y_top - prev_y_bot
            min_h = max(min(prev_h, h), 1.0)
            x_diff = x_left - prev_x_left

            # 段落边界：负间距（同行重叠）、大间距（跨段落）
            if y_gap <= 0 or y_gap >= min_h:
                if current:
                    paragraphs.append("".join(current))
                current = [content]
                had_wrap = False
            else:
                is_wrap = x_diff < -min_h * 0.3
                is_same_margin = abs(x_diff) < min_h * 0.15

                if is_wrap:
                    current.append(content)
                    had_wrap = True
                elif is_same_margin and had_wrap:
                    current.append(content)
                else:
                    if current:
                        paragraphs.append("".join(current))
                    current = [content]
                    had_wrap = False

            prev_y_bot = y_bot
            prev_x_left = x_left
            prev_h = h

    if current:
        paragraphs.append("".join(current))

    return "\n\n".join(paragraphs)


# ---------- Agent 修正（from/to 文本替换）----------

def load_agent_corrections(path: str | Path) -> list[tuple[str, str]]:
    """加载 agent 修正文件。

    JSON 格式：
    [
      {"from": "性别芝", "to": "性别女"},
      {"from": "沙库巴去缬沙坦", "to": "沙库巴曲缬沙坦"}
    ]
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"修正文件不存在: {p}")

    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("修正文件格式错误：期望 JSON 数组 [{from, to}, ...]")

    corrections = []
    for item in data:
        if isinstance(item, dict):
            src = item.get("from")
            dst = item.get("to")
            if src and dst:
                corrections.append((str(src), str(dst)))

    return corrections


def apply_agent_corrections(
    entries: list[dict],
    corrections: list[tuple[str, str]],
    quiet: bool = False,
) -> tuple[list[dict], int]:
    """对 page entries 应用 agent 的 from/to 文本替换。"""
    total = 0
    for entry in entries:
        if "rows" not in entry:
            continue
        new_rows = []
        for text, score, poly in entry["rows"]:
            corrected = text
            for src, dst in corrections:
                if src in corrected:
                    corrected = corrected.replace(src, dst)
            if corrected != text:
                total += 1
            new_rows.append((corrected, score, poly))
        entry["rows"] = new_rows

    if total and not quiet:
        print(f"  Agent 修正: {total} 处文本已纠正")

    return entries, total


# ---------- Archive 归档（仅保存 MD）----------

def _sanitize_name(name: str) -> str:
    """清理文件名中的特殊字符，保留中文、字母、数字、下划线和连字符。"""
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    name = re.sub(r'[“”‘’]', '', name)  # 中文引号
    name = re.sub(r'\s+', ' ', name).strip()
    return name or "unnamed"


def archive_ocr_result(
    source_path: str | Path,
    entries: list[dict],
    model: str = "",
    backend: str = "",
    extra_meta: dict | None = None,
    original_source_path: str | Path | None = None,
) -> tuple[Path, Path]:
    """将 OCR 可读文本归档到 skill 内部 archive/，同时输出到原文件同目录。

    归档格式：archive/YYYYMMDD_HHMMSS_文件名/原文件名.md + conversion_meta.json
    同时在原文件同目录生成同名 .md 文件。

    Args:
        source_path: 实际处理的 PDF 路径（可能是临时文件）。
        original_source_path: 用户最初传入的原始 PDF 路径。
            如果提供，归档目录名和伴生 .md 以原始文件为准，
            source_file 记录原始路径，working_file 记录实际处理路径。

    Returns:
        (archive_md_path, source_dir_md_path)
    """
    working = Path(source_path)
    original = Path(original_source_path) if original_source_path else None

    # 归档命名和伴生 .md 以原始文件为准
    naming_source = original or working
    stem = _sanitize_name(naming_source.stem)
    md_name = naming_source.stem + ".md"
    md_content = generate_readable_text(entries)

    # archive 内部归档
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    archive_path = ARCHIVE_DIR / f"{timestamp}_{stem}"
    archive_path.mkdir(parents=True, exist_ok=True)
    archive_md = archive_path / md_name
    archive_md.write_text(md_content, encoding="utf-8")

    # 运行记录 JSON
    total_pages = len(entries)
    total_rows = sum(len(e.get("rows", [])) for e in entries)
    meta = {
        "timestamp": now.isoformat(),
        "source_file": str(naming_source),
        "archive_path": str(archive_path),
        "model": model,
        "backend": backend,
        "total_pages": total_pages,
        "total_text_blocks": total_rows,
    }
    if original and original != working:
        meta["working_file"] = str(working)
    if extra_meta:
        meta.update(extra_meta)
    meta_path = archive_path / "conversion_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # 原文件同目录输出（始终写到原始文件旁边）
    source_md = naming_source.parent / md_name
    source_md.write_text(md_content, encoding="utf-8")

    return archive_md, source_md


def archive_preprocess_result(
    source_path: str | Path,
    preprocess_meta: dict | None = None,
    output_path: str | Path | None = None,
    original_source_path: str | Path | None = None,
) -> Path:
    """仅预处理模式的轻量归档（无 OCR 文本，只记录元数据）。

    归档格式：archive/YYYYMMDD_HHMMSS_文件名/conversion_meta.json

    Args:
        source_path: 实际处理的 PDF 路径。
        preprocess_meta: 预处理参数和统计信息。
        output_path: 最终输出文件路径。
        original_source_path: 用户最初传入的原始 PDF 路径。

    Returns:
        archive_dir_path
    """
    working = Path(source_path)
    original = Path(original_source_path) if original_source_path else None
    naming_source = original or working
    stem = _sanitize_name(naming_source.stem)

    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    archive_path = ARCHIVE_DIR / f"{timestamp}_{stem}"
    archive_path.mkdir(parents=True, exist_ok=True)

    meta = {
        "timestamp": now.isoformat(),
        "source_file": str(naming_source),
        "archive_path": str(archive_path),
        "mode": "preprocess_only",
    }
    if output_path:
        meta["output_file"] = str(Path(output_path))
    if original and original != working:
        meta["working_file"] = str(working)
    if preprocess_meta:
        meta["preprocess"] = preprocess_meta

    meta_path = archive_path / "conversion_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return archive_path
