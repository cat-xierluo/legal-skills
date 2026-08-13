#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "Pillow>=10.0.0",
# ]
# ///

"""为基础截图生成非破坏性的证据线索索引与联系表。"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import (
    calc_blur_score,
    calc_dhash_hex,
    calc_thumb_bytes,
    create_ocr_engine,
    hamming_distance_hex,
    mean_abs_diff,
    ocr_extract_text,
)


SCHEMA_VERSION = "1.0"
SIGNAL_VERSION = "evidence-leads-1.0"
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TAXONOMY = ROOT / "config" / "evidence-lead-taxonomy.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成高价值证据线索索引与联系表")
    parser.add_argument("-i", "--input", required=True, help="extract.py 的基础输出目录")
    parser.add_argument("-o", "--output", default=None, help="默认: <input>/_evidence_leads")
    parser.add_argument("--taxonomy", default=str(DEFAULT_TAXONOMY), help="证据线索分类配置")
    parser.add_argument("--ocr", action=argparse.BooleanOptionalAction, default=True, help="使用本地 RapidOCR 多锚点识别（默认开启，缺失时降级）")
    parser.add_argument("--max-leads", type=int, default=24, help="联系表最多展示的高价值线索数（默认: 24）")
    parser.add_argument("--max-sheets", type=int, default=4, help="最多联系表数量（默认: 4）")
    parser.add_argument("--columns", type=int, default=2, help="联系表列数（默认: 2，适合较弱视觉模型）")
    parser.add_argument("--thumb-width", type=int, default=400)
    parser.add_argument("--thumb-height", type=int, default=712)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{label} 必须是 JSON 对象")
    return data


def _safe_output(output: Path) -> None:
    if output.is_symlink():
        raise ValueError("证据线索目录是符号链接，拒绝跟随")
    if output.exists():
        template_path = output / "vision_template.json"
        if template_path.is_file() and not template_path.is_symlink():
            try:
                template = _load_json(template_path, "既有视觉复核模板")
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"既有视觉复核模板无法安全识别，拒绝覆盖: {exc}") from exc
            answers = template.get("answers")
            has_answer = isinstance(answers, list) and any(
                isinstance(answer, dict)
                and (
                    bool(answer.get("categories"))
                    or bool(str(answer.get("visible_fact_summary") or "").strip())
                    or bool(str(answer.get("potential_use") or "").strip())
                    or answer.get("confidence") is not None
                )
                for answer in answers
            )
            if template.get("status") == "completed" or has_answer:
                raise ValueError("视觉复核模板已填写，拒绝重建证据线索包")
        unknown = [
            path for path in output.iterdir()
            if path.is_symlink()
            or not path.is_file()
            or (
                path.name not in {"evidence_index.json", "VISION_INSTRUCTIONS.md", "vision_template.json"}
                and not re.fullmatch(r"evidence_sheet_\d{3}\.jpg", path.name)
            )
        ]
        if unknown:
            raise ValueError("证据线索目录含非本工具文件，拒绝覆盖: " + ", ".join(path.name for path in unknown[:5]))
        for path in output.iterdir():
            path.unlink()
    output.mkdir(parents=True, exist_ok=True)


def _validate_report(root: Path) -> tuple[Path, dict[str, Any], list[dict[str, Any]]]:
    report_path = root / "_report.json"
    if report_path.is_symlink() or not report_path.is_file():
        raise ValueError("基础报告不存在或为符号链接")
    report = _load_json(report_path, "基础报告")
    frames = report.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("基础报告缺少 frames")
    actual = {path.name for path in root.glob("frame_*.jpg") if path.is_file() and not path.is_symlink()}
    expected: set[str] = set()
    for index, frame in enumerate(frames, 1):
        if not isinstance(frame, dict):
            raise ValueError(f"frame #{index} 格式错误")
        filename = str(frame.get("filename") or "")
        if not re.fullmatch(r"frame_\d{3}_\d{2}m\d{2}s\.jpg", filename):
            raise ValueError(f"非法基础帧文件名: {filename}")
        path = root / filename
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"基础帧不存在或为符号链接: {filename}")
        if str(frame.get("sha256") or "") != sha256_file(path):
            raise ValueError(f"基础帧 SHA256 不一致: {filename}")
        expected.add(filename)
    if expected != actual:
        raise ValueError("基础报告与 frame_*.jpg 清单不一致")
    return report_path, report, frames


def _load_taxonomy(path: Path) -> dict[str, Any]:
    taxonomy = _load_json(path, "证据线索分类")
    if taxonomy.get("schema_version") != "1.0" or not isinstance(taxonomy.get("categories"), list):
        raise ValueError("证据线索分类 schema 不受支持")
    ids: set[str] = set()
    for category in taxonomy["categories"]:
        if not isinstance(category, dict) or set(category) != {"id", "label", "anchors", "patterns", "minimum_anchor_hits"}:
            raise ValueError("证据线索分类字段不完整")
        category_id = str(category["id"])
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,63}", category_id) or category_id in ids:
            raise ValueError(f"非法或重复分类 ID: {category_id}")
        ids.add(category_id)
        if not isinstance(category["anchors"], list) or not isinstance(category["patterns"], list):
            raise ValueError(f"分类词表格式错误: {category_id}")
        minimum = category["minimum_anchor_hits"]
        if not isinstance(minimum, int) or isinstance(minimum, bool) or not 1 <= minimum <= 6:
            raise ValueError(f"minimum_anchor_hits 非法: {category_id}")
        if not 1 <= len(category["anchors"]) <= 64 or not 0 <= len(category["patterns"]) <= 32:
            raise ValueError(f"分类词表数量超限: {category_id}")
        if any(not isinstance(anchor, str) or not 1 <= len(anchor) <= 40 for anchor in category["anchors"]):
            raise ValueError(f"分类锚点非法: {category_id}")
        for pattern in category["patterns"]:
            if not isinstance(pattern, str) or not 1 <= len(pattern) <= 120:
                raise ValueError(f"分类正则非法: {category_id}")
            re.compile(str(pattern))
    return taxonomy


def _normalize_ocr(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def classify_evidence_text(text: str, taxonomy: dict[str, Any]) -> list[dict[str, Any]]:
    """只返回类别和命中强度，不返回 OCR 原文或具体实体。"""
    normalized = _normalize_ocr(text)
    if not normalized:
        return []
    findings: list[dict[str, Any]] = []
    for category in taxonomy["categories"]:
        anchor_hits = sum(1 for anchor in category["anchors"] if str(anchor).lower() in normalized)
        pattern_hits = sum(1 for pattern in category["patterns"] if re.search(str(pattern), normalized, re.IGNORECASE))
        minimum = max(1, int(category["minimum_anchor_hits"]))
        combined = anchor_hits + pattern_hits
        # 正则（金额、编号、日期）只能作辅证，单独命中不形成类别。
        qualified = anchor_hits >= minimum or (anchor_hits >= 1 and pattern_hits >= 1 and combined >= minimum)
        if not qualified:
            continue
        confidence = min(0.95, 0.48 + 0.13 * anchor_hits + 0.09 * pattern_hits)
        findings.append({
            "category_id": category["id"],
            "category_label": category["label"],
            "anchor_hit_count": anchor_hits,
            "pattern_hit_count": pattern_hits,
            "confidence_band": "high" if confidence >= 0.78 else "medium",
            "score": round(confidence, 4),
        })
    return sorted(findings, key=lambda item: (-float(item["score"]), str(item["category_id"])))


def visual_content_signals(image_bytes: bytes, previous_thumb: bytes | None) -> tuple[dict[str, Any], bytes]:
    image = Image.open(io.BytesIO(image_bytes))
    rgb = image.convert("RGB")
    gray = ImageOps.grayscale(rgb)
    small = gray.resize((96, 160))
    stat = ImageStat.Stat(small)
    luminance_std = float(stat.stddev[0])
    edges = small.filter(ImageFilter.FIND_EDGES)
    edge_ratio = sum(value >= 35 for value in edges.tobytes()) / float(96 * 160)
    small_rgb = rgb.resize((96, 160))
    photo_tiles = 0
    color_tiles = 0
    tile_count = 0
    for top in range(0, 160, 16):
        for left in range(0, 96, 16):
            tile_count += 1
            rgb_tile = small_rgb.crop((left, top, left + 16, top + 16))
            gray_tile = ImageOps.grayscale(rgb_tile)
            gray_values = gray_tile.tobytes()
            rgb_values = rgb_tile.tobytes()
            midtone_ratio = sum(35 <= value <= 225 for value in gray_values) / len(gray_values)
            tile_std = float(ImageStat.Stat(gray_tile).stddev[0])
            saturated = 0
            for offset in range(0, len(rgb_values), 3):
                red, green, blue = rgb_values[offset: offset + 3]
                saturated += max(red, green, blue) - min(red, green, blue) >= 22
            saturated_ratio = saturated / (len(rgb_values) / 3)
            if midtone_ratio >= 0.60 and tile_std >= 10.0:
                photo_tiles += 1
            if saturated_ratio >= 0.50 and tile_std >= 8.0:
                color_tiles += 1
    photo_area_ratio = photo_tiles / tile_count
    color_area_ratio = color_tiles / tile_count
    # 细碎文字边缘会抬高全图方差，只有连续块状的中间调或色彩区域才视为图像主体线索。
    photo_richness = min(
        1.0,
        0.65 * min(1.0, photo_area_ratio / 0.45)
        + 0.35 * min(1.0, color_area_ratio / 0.40),
    )
    thumb = calc_thumb_bytes(image_bytes, size=48, autocontrast=True)
    delta = mean_abs_diff(thumb, previous_thumb) if previous_thumb else None
    visual_delta = min(1.0, float(delta or 0.0) / 45.0)
    return ({
        "photo_richness": round(max(0.0, photo_richness), 4),
        "edge_ratio": round(edge_ratio, 4),
        "photo_area_ratio": round(photo_area_ratio, 4),
        "color_area_ratio": round(color_area_ratio, 4),
        "visual_delta_from_previous": round(visual_delta, 4),
        "text_independent_content": bool(photo_area_ratio >= 0.25 or color_area_ratio >= 0.18),
    }, thumb)


def _context_signals(frame: dict[str, Any]) -> list[str]:
    signals: list[str] = []
    if frame.get("temporal_reason") in {"short_motion_representative", "ocr_short_motion_rescue"}:
        signals.append("brief_page")
    if frame.get("selection_confidence") == "high":
        signals.append("stable_page")
    if float(frame.get("scroll_match_ratio") or 0.0) >= 0.55:
        signals.append("scroll_sequence")
    if bool((frame.get("content_delta") or {}).get("has_new_content")):
        signals.append("ocr_increment")
    return signals


def _score_lead(text_findings: list[dict[str, Any]], visual: dict[str, Any], context: list[str], blur_score: float) -> tuple[float, list[str]]:
    reasons: list[str] = []
    text_score = max((float(item["score"]) for item in text_findings), default=0.0)
    if text_findings:
        reasons.append("multi_anchor_text")
    visual_score = float(visual["photo_richness"])
    if visual["text_independent_content"]:
        reasons.append("text_independent_visual_content")
    context_score = min(1.0, 0.28 * len(context))
    if context:
        reasons.extend(context)
    clarity = min(1.0, max(0.0, math.log1p(max(0.0, blur_score)) / math.log(401.0)))
    # 文字和视觉取较强者，避免无文字商品大图被 OCR 分支压低；上下文只作有限加分。
    primary = max(text_score, visual_score * 0.82)
    score = min(1.0, primary * 0.70 + context_score * 0.18 + clarity * 0.12)
    return round(score, 4), list(dict.fromkeys(reasons))


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(name).exists():
            try:
                return ImageFont.truetype(name, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def _render_sheet(items: list[dict[str, Any]], root: Path, output: Path, columns: int, width: int, height: int) -> None:
    padding, header, label_height = 14, 54, 104
    rows = math.ceil(len(items) / columns)
    canvas = Image.new("RGB", (padding + columns * (width + padding), header + rows * (height + label_height) + padding), "#ececec")
    draw = ImageDraw.Draw(canvas)
    draw.text((padding, 12), "证据线索联系表（仅排序，不代表证据成立）", fill="#111111", font=_font(20))
    for index, item in enumerate(items):
        image = Image.open(root / item["filename"]).convert("RGB")
        fitted = ImageOps.contain(image, (width, height))
        row, col = divmod(index, columns)
        x = padding + col * (width + padding)
        y = header + row * (height + label_height)
        canvas.paste(fitted, (x + (width - fitted.width) // 2, y + (height - fitted.height) // 2))
        draw.rectangle((x, y, x + width, y + height), outline="#355c7d", width=3)
        categories = "、".join(item["category_labels"][:2]) or "图像内容线索"
        label = f"{item['lead_id']} | {item['capture_time_seconds']:.2f}s | {item['lead_score']:.2f}\n{categories}\n{item['filename']}"
        draw.multiline_text((x, y + height + 7), label, fill="#111111", font=_font(16), spacing=3)
    canvas.save(output, format="JPEG", quality=88, optimize=True)


def _select_leads(leads: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    selected: list[dict[str, Any]] = []
    remaining = sorted(leads, key=lambda item: (-float(item["lead_score"]), float(item["capture_time_seconds"])))
    category_counts: dict[str, int] = {}
    buckets: set[int] = set()
    while remaining and len(selected) < limit:
        remaining.sort(key=lambda item: (
            -(
                float(item["lead_score"])
                + (0.10 if int(float(item["capture_time_seconds"]) // 30) not in buckets else 0.0)
                + min(0.12, sum(0.04 for category in item["category_ids"] if category_counts.get(category, 0) == 0))
            ),
            float(item["capture_time_seconds"]),
        ))
        item = remaining.pop(0)
        selected.append(item)
        buckets.add(int(float(item["capture_time_seconds"]) // 30))
        for category in item["category_ids"]:
            category_counts[category] = category_counts.get(category, 0) + 1
        # 联系表只需代表性线索；近重复商品大图或同页小变化留在完整索引，不重复占弱模型预算。
        filtered: list[dict[str, Any]] = []
        for candidate in remaining:
            distance = hamming_distance_hex(str(item["visual_dhash"]), str(candidate["visual_dhash"]))
            close_time = abs(float(item["capture_time_seconds"]) - float(candidate["capture_time_seconds"])) <= 5.0
            if distance is not None and (distance <= 5 or (close_time and distance <= 9)):
                continue
            filtered.append(candidate)
        remaining = filtered
    return selected


def _vision_instructions(index_sha: str) -> str:
    return f"""# 证据线索视觉复核说明

逐张查看 `evidence_sheet_NNN.jpg`，只判断图片中**可直接看见**的内容，不判断真实性、合法性、关联性或最终证明力。

1. OCR 类别只是代码提示；即使文字很少，也检查商品外观、包装/标识、作品画面、缺陷状态、经营场所、人物行为等视觉内容。
2. 为每个 `lead_id` 从模板允许类别中选择 1—3 个；无法判断时选择 `uncertain`，不要猜测具体企业名、商品名或身份。
3. `visible_fact_summary` 只作泛化概括，不抄录主体/账号/品牌/商品名、金额、编号、联系方式或沟通原句；`potential_use` 只写“可能用于定位/说明……”，不得写“足以证明”。
4. 不得据此删除基础帧。该阶段只为后续人工复核排序。

evidence_index SHA256：`{index_sha}`
"""


def main() -> int:
    args = parse_args()
    if args.max_leads <= 0 or args.max_sheets <= 0 or args.columns <= 0:
        print("错误: max-leads、max-sheets 和 columns 必须大于 0", file=sys.stderr)
        return 2
    raw_root = Path(args.input).expanduser()
    if raw_root.is_symlink():
        print("错误: 基础输出目录是符号链接，拒绝跟随", file=sys.stderr)
        return 2
    root = raw_root.resolve()
    raw_output = Path(args.output).expanduser() if args.output else root / "_evidence_leads"
    if raw_output.is_symlink():
        print("错误: 证据线索输出目录是符号链接，拒绝跟随", file=sys.stderr)
        return 2
    output = raw_output.resolve()
    taxonomy_path = Path(args.taxonomy).expanduser().resolve()
    try:
        report_path, report, frames = _validate_report(root)
        taxonomy = _load_taxonomy(taxonomy_path)
        _safe_output(output)
        ocr_engine = create_ocr_engine() if args.ocr else None
        ocr_available = ocr_engine is not None
        if args.ocr and not ocr_available:
            print("警告: RapidOCR 未安装，证据线索识别降级为视觉与时序信号", file=sys.stderr)

        leads: list[dict[str, Any]] = []
        previous_thumb: bytes | None = None
        for index, frame in enumerate(frames, 1):
            image_path = root / str(frame["filename"])
            image_bytes = image_path.read_bytes()
            text = ocr_extract_text(ocr_engine, image_bytes) if ocr_available else ""
            text_findings = classify_evidence_text(text, taxonomy)
            visual, thumb = visual_content_signals(image_bytes, previous_thumb)
            previous_thumb = thumb
            context = _context_signals(frame)
            blur_score = calc_blur_score(image_bytes)
            score, reasons = _score_lead(text_findings, visual, context, blur_score)
            category_ids = [str(item["category_id"]) for item in text_findings]
            category_labels = [str(item["category_label"]) for item in text_findings]
            if visual["text_independent_content"]:
                category_ids.append("visual_content_unclassified")
                category_labels.append("图像内容待视觉识别")
            leads.append({
                "lead_id": f"lead-{index:03d}",
                "frame_index": frame.get("index"),
                "filename": frame["filename"],
                "capture_time_seconds": round(float(frame.get("capture_time_seconds") or 0.0), 4),
                "sha256": frame["sha256"],
                "visual_dhash": calc_dhash_hex(image_bytes, hash_size=8),
                "lead_score": score,
                "priority_band": "high" if score >= 0.68 else "medium" if score >= 0.48 else "background",
                "category_ids": list(dict.fromkeys(category_ids)),
                "category_labels": list(dict.fromkeys(category_labels)),
                "signal_sources": {
                    "ocr_available": ocr_available,
                    "ocr_category_count": len(text_findings),
                    "ocr_anchor_hit_count": sum(int(item["anchor_hit_count"]) for item in text_findings),
                    "ocr_pattern_hit_count": sum(int(item["pattern_hit_count"]) for item in text_findings),
                    "visual": visual,
                    "context": context,
                },
                "ranking_reasons": reasons,
                "privacy": {"ocr_text_stored": False, "entity_text_stored": False},
            })

        selected = _select_leads(leads, min(args.max_leads, args.max_sheets * args.columns * 3))
        page_size = max(1, math.ceil(len(selected) / args.max_sheets))
        page_size = max(args.columns, min(page_size, args.columns * 3))
        sheets: list[dict[str, Any]] = []
        for offset in range(0, len(selected), page_size):
            if len(sheets) >= args.max_sheets:
                break
            page = selected[offset: offset + page_size]
            name = f"evidence_sheet_{len(sheets) + 1:03d}.jpg"
            _render_sheet(page, root, output / name, args.columns, args.thumb_width, args.thumb_height)
            sheets.append({"filename": name, "lead_ids": [item["lead_id"] for item in page]})

        selection_ranks = {item["lead_id"]: rank for rank, item in enumerate(selected, 1)}
        index_data = {
            "schema_version": SCHEMA_VERSION,
            "signal_version": SIGNAL_VERSION,
            "status": "prepared",
            "purpose": "ranking_only_non_destructive_evidence_leads",
            "legal_boundary": "线索分类不代表真实性、合法性、关联性或证明力已经成立",
            "source_report": "_report.json",
            "source_report_sha256": sha256_file(report_path),
            "taxonomy_sha256": sha256_file(taxonomy_path),
            "privacy": {"ocr_text_stored": False, "entity_text_stored": False},
            "budget": {"max_leads": args.max_leads, "max_sheets": args.max_sheets, "selected_leads": len(selected), "actual_sheets": len(sheets)},
            "summary": {
                "total_frames": len(leads),
                "high_priority": sum(item["priority_band"] == "high" for item in leads),
                "medium_priority": sum(item["priority_band"] == "medium" for item in leads),
                "text_independent_visual_leads": sum("visual_content_unclassified" in item["category_ids"] for item in leads),
                "ocr_available": ocr_available,
            },
            "sheets": sheets,
            "leads": [{
                **item,
                "selected_for_contact_sheet": item["lead_id"] in selection_ranks,
                "selection_rank": selection_ranks.get(item["lead_id"]),
            } for item in leads],
            "vision_contract": {
                "operation": "classify_and_summarize_only",
                "may_delete_base_frames": False,
                "allowed_categories": [category["id"] for category in taxonomy["categories"]] + ["visual_product_or_work", "visual_mark_or_packaging", "visual_defect_or_condition", "visual_place_or_behavior", "uncertain"],
            },
        }
        index_path = output / "evidence_index.json"
        index_path.write_text(json.dumps(index_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        index_sha = sha256_file(index_path)
        template = {
            "schema_version": "1.0",
            "status": "in_progress",
            "source_evidence_index_sha256": index_sha,
            "operation": "classify_and_summarize_only",
            "answers": [{
                "lead_id": item["lead_id"],
                "allowed_categories": index_data["vision_contract"]["allowed_categories"],
                "categories": [],
                "visible_fact_summary": "",
                "potential_use": "",
                "confidence": None,
            } for item in selected],
        }
        (output / "vision_template.json").write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (output / "VISION_INSTRUCTIONS.md").write_text(_vision_instructions(index_sha), encoding="utf-8")
        print(f"完成: {index_path}")
        print(f"  基础帧: {len(leads)}（未修改）")
        print(f"  联系表线索: {len(selected)}/{args.max_leads}")
        print(f"  联系表: {len(sheets)}/{args.max_sheets}")
        print(f"  OCR: {'available' if ocr_available else 'unavailable_visual_fallback'}")
        return 0
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
