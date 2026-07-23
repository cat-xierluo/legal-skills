#!/usr/bin/env python3
"""内联 SVG 源码、几何与真实 PNG 渲染门禁。"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET
import io
import json
import math
import re
import shutil
import subprocess

from gate_models import (
    CheckerOutput,
    Finding,
    GateContext,
    canonical_hash,
    line_number,
    sha256_bytes,
)


_SVG_RE = re.compile(r"<svg\b[\s\S]*?</svg>", re.IGNORECASE)
_URL_ID_RE = re.compile(r"url\(#([^)]+)\)")
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_WHITE_FILLS = {"#fff", "#ffffff", "white", "rgb(255,255,255)"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _num(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    match = _NUMBER_RE.search(str(value))
    return float(match.group()) if match else default


def _inline_svgs(ctx: GateContext, requirement: dict) -> list[dict]:
    artifacts: list[dict] = []
    for path in ctx.scope_files(requirement):
        if path.suffix.lower() != ".md":
            continue
        text = path.read_text(encoding="utf-8")
        matches = list(_SVG_RE.finditer(text))
        for ordinal, match in enumerate(matches, 1):
            svg_text = match.group(0)
            line = line_number(text, match.start())
            artifact_id = "svg-" + sha256_bytes(
                f"{ctx.rel(path)}:{ordinal}:".encode("utf-8") + svg_text.encode("utf-8")
            )[:16]
            artifacts.append({
                "artifact_id": artifact_id,
                "kind": "inline_svg",
                "source_file": ctx.rel(path),
                "line": line,
                "ordinal": ordinal,
                "svg": svg_text,
                "svg_sha256": sha256_bytes(svg_text.encode("utf-8")),
                "caption": _nearby_caption(text, match.end()),
                "context_before": _context_before(text, match.start()),
                "context_after": _context_after(text, match.end()),
            })
    return artifacts


def _nearby_caption(text: str, offset: int) -> str:
    for line in text[offset:].splitlines()[:5]:
        clean = line.strip()
        if clean:
            return clean[:240]
    return ""


def _context_before(text: str, offset: int) -> str:
    for line in reversed(text[:offset].splitlines()):
        clean = line.strip()
        if clean and not clean.startswith(("<", "<!--", "**图", "*图")):
            return clean[:300]
    return ""


def _context_after(text: str, offset: int) -> str:
    nonempty = [line.strip() for line in text[offset:].splitlines() if line.strip()]
    for clean in nonempty[1:6]:
        if not clean.startswith(("<svg", "<!--", "**图", "*图")):
            return clean[:300]
    return ""


def source_policy(ctx: GateContext, requirement: dict) -> CheckerOutput:
    rid = requirement["id"]
    findings: list[Finding] = []
    artifacts = _inline_svgs(ctx, requirement)
    for artifact in artifacts:
        source = artifact["source_file"]
        line = artifact["line"]
        aid = artifact["artifact_id"]
        try:
            root = ET.fromstring(artifact["svg"])
        except ET.ParseError as exc:
            findings.append(Finding(
                rid, source, line, "hard", f"SVG XML 不是 well-formed：{exc}",
                "修复 XML 后重新渲染；解析失败不得降级为文本。", aid,
            ))
            continue

        for attr in ("viewBox", "width", "height"):
            if not root.get(attr):
                findings.append(Finding(
                    rid, source, line, "hard", f"SVG 缺少 {attr}。",
                    "显式设置 viewBox、width、height。", aid,
                ))

        ids: list[str] = []
        for element in root.iter():
            if _local(element.tag) == "style":
                findings.append(Finding(
                    rid, source, line, "hard", "SVG 含 <style> 块。",
                    "把颜色与样式写为元素的 fill/stroke 等内联属性。", aid,
                ))
            if element.get("font-family") or "font-family" in element.get("style", "").lower():
                findings.append(Finding(
                    rid, source, line, "hard", "SVG 含 font-family。",
                    "删除 font-family，交给宿主环境选择可用中文字体。", aid,
                ))
            if element.get("id"):
                ids.append(element.get("id", ""))
        duplicate_ids = sorted({item for item in ids if ids.count(item) > 1})
        for duplicate in duplicate_ids:
            findings.append(Finding(
                rid, source, line, "hard", f"SVG id 重复：{duplicate}",
                "同一 SVG 内每个 id 必须唯一。", aid,
            ))

        view_box = [_num(v) for v in root.get("viewBox", "").replace(",", " ").split()]
        if len(view_box) == 4:
            _, _, canvas_w, canvas_h = view_box
            for element in root.iter():
                if _local(element.tag) != "rect":
                    continue
                fill = element.get("fill", "").replace(" ", "").lower()
                x = _num(element.get("x"))
                y = _num(element.get("y"))
                width_raw = element.get("width", "")
                height_raw = element.get("height", "")
                width = canvas_w if width_raw == "100%" else _num(width_raw)
                height = canvas_h if height_raw == "100%" else _num(height_raw)
                if (
                    fill in _WHITE_FILLS
                    and abs(x - view_box[0]) <= 1
                    and abs(y - view_box[1]) <= 1
                    and width >= canvas_w * 0.95
                    and height >= canvas_h * 0.95
                ):
                    findings.append(Finding(
                        rid, source, line, "hard", "SVG 含近乎全画布白底矩形。",
                        "删除全画布底色，保持透明背景。", aid,
                    ))
    return CheckerOutput(
        findings=findings,
        metrics={"inline_svg_count": len(artifacts)},
        artifacts=[{k: v for k, v in a.items() if k != "svg"} for a in artifacts],
    )


def marker_integrity(ctx: GateContext, requirement: dict) -> CheckerOutput:
    rid = requirement["id"]
    options = requirement.get("options", {}) or {}
    max_distance = float(options.get("max_endpoint_distance", 18))
    require_single = bool(options.get("single_marker_id", True))
    findings: list[Finding] = []
    artifacts = _inline_svgs(ctx, requirement)
    for artifact in artifacts:
        try:
            root = ET.fromstring(artifact["svg"])
        except ET.ParseError:
            continue
        aid = artifact["artifact_id"]
        source = artifact["source_file"]
        line = artifact["line"]
        markers = [item for item in root.iter() if _local(item.tag) == "marker"]
        marker_ids = {item.get("id", "") for item in markers if item.get("id")}
        if require_single and len(marker_ids) > 1:
            findings.append(Finding(
                rid, source, line, "hard",
                f"同一 SVG 定义了 {len(marker_ids)} 个 marker id：{sorted(marker_ids)}",
                "同一张图只保留一个通用 arrow marker。", aid,
            ))
        for marker in markers:
            if marker.get("orient") != "auto" or marker.get("markerUnits") != "userSpaceOnUse":
                findings.append(Finding(
                    rid, source, line, "hard",
                    "marker 必须同时使用 orient=auto 与 markerUnits=userSpaceOnUse。",
                    "按 SVG 生成规范修正 marker 属性。", aid,
                ))

        shapes = _target_shapes(root)
        for element in root.iter():
            marker_end = element.get("marker-end", "")
            if not marker_end:
                continue
            reference = _URL_ID_RE.search(marker_end)
            if not reference or reference.group(1) not in marker_ids:
                findings.append(Finding(
                    rid, source, line, "hard",
                    f"marker-end 引用无法解析：{marker_end}",
                    "确保 url(#id) 指向本 SVG 中唯一存在的 marker。", aid,
                ))
                continue
            endpoint = _endpoint(element)
            if endpoint is None or not shapes:
                continue
            distance = min(_distance_to_shape(endpoint, shape) for shape in shapes)
            if distance > max_distance:
                findings.append(Finding(
                    rid, source, line, "hard",
                    f"箭头端点距最近目标边界 {distance:.1f}px，超过 {max_distance:.1f}px。",
                    "把箭头终点收敛到目标框边界外约 4px；渲染后再核方向。",
                    aid,
                    {"endpoint": endpoint, "nearest_distance": round(distance, 2)},
                ))
    return CheckerOutput(findings=findings, metrics={"inline_svg_count": len(artifacts)})


def _target_shapes(root: ET.Element) -> list[tuple[str, tuple[float, ...]]]:
    shapes: list[tuple[str, tuple[float, ...]]] = []
    for element in root.iter():
        tag = _local(element.tag)
        if tag == "rect":
            shapes.append(("rect", (
                _num(element.get("x")), _num(element.get("y")),
                _num(element.get("width")), _num(element.get("height")),
            )))
        elif tag == "circle":
            shapes.append(("circle", (
                _num(element.get("cx")), _num(element.get("cy")), _num(element.get("r")),
            )))
    return shapes


def _endpoint(element: ET.Element) -> tuple[float, float] | None:
    tag = _local(element.tag)
    if element.get("transform"):
        return None
    if tag == "line":
        return (_num(element.get("x2")), _num(element.get("y2")))
    if tag in {"polyline", "polygon"}:
        numbers = [float(item) for item in _NUMBER_RE.findall(element.get("points", ""))]
        if len(numbers) >= 2:
            return (numbers[-2], numbers[-1])
    if tag == "path":
        numbers = [float(item) for item in _NUMBER_RE.findall(element.get("d", ""))]
        if len(numbers) >= 2:
            return (numbers[-2], numbers[-1])
    return None


def _distance_to_shape(point: tuple[float, float], shape: tuple[str, tuple[float, ...]]) -> float:
    x, y = point
    kind, values = shape
    if kind == "circle":
        cx, cy, radius = values
        return abs(math.hypot(x - cx, y - cy) - radius)
    left, top, width, height = values
    right, bottom = left + width, top + height
    if left <= x <= right and top <= y <= bottom:
        return min(x - left, right - x, y - top, bottom - y)
    nearest_x = min(max(x, left), right)
    nearest_y = min(max(y, top), bottom)
    return math.hypot(x - nearest_x, y - nearest_y)


def render_and_measure(ctx: GateContext, requirement: dict) -> CheckerOutput:
    rid = requirement["id"]
    options = requirement.get("options", {}) or {}
    width = int(options.get("render_width", 1440))
    max_padding = float(options.get("max_padding_ratio", 0.22))
    findings: list[Finding] = []
    artifacts = _inline_svgs(ctx, requirement)
    renderer = shutil.which("rsvg-convert")
    if not renderer:
        raise RuntimeError("缺少 rsvg-convert；macOS 请运行 brew install librsvg")
    try:
        from PIL import Image, ImageDraw, ImageOps
    except ImportError as exc:
        raise RuntimeError("缺少 Pillow；请运行 python3 -m pip install Pillow") from exc

    render_dir = ctx.output_dir / f"rendered-{ctx.candidate_sha[:12]}"
    packet_dir = ctx.output_dir / f"packets-{ctx.candidate_sha[:12]}"
    render_dir.mkdir(parents=True, exist_ok=True)
    packet_dir.mkdir(parents=True, exist_ok=True)
    manifest_items: list[dict] = []

    for artifact in artifacts:
        png_path = render_dir / f"{artifact['artifact_id']}.png"
        command = [renderer, "--format", "png", "--width", str(width), "--output", str(png_path)]
        process = subprocess.run(
            command,
            input=artifact["svg"].encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if process.returncode != 0 or not png_path.exists():
            findings.append(Finding(
                rid, artifact["source_file"], artifact["line"], "hard",
                f"rsvg-convert 渲染失败：{process.stderr.decode('utf-8', 'replace')[:300]}",
                "修复 SVG 后重新生成 PNG；禁止静默跳过。", artifact["artifact_id"],
            ))
            continue
        warning = process.stderr.decode("utf-8", "replace").strip()
        if warning:
            findings.append(Finding(
                rid, artifact["source_file"], artifact["line"], "hard",
                f"rsvg-convert 输出警告：{warning[:300]}",
                "消除渲染警告后再放行。", artifact["artifact_id"],
            ))
        try:
            with Image.open(png_path) as image:
                rgba = image.convert("RGBA")
                alpha = rgba.getchannel("A")
                bbox = alpha.getbbox()
                if bbox is None:
                    findings.append(Finding(
                        rid, artifact["source_file"], artifact["line"], "hard",
                        "渲染结果完全透明或为空白。",
                        "检查 fill/stroke、viewBox 与元素坐标。", artifact["artifact_id"],
                    ))
                    padding = None
                else:
                    left, top, right, bottom = bbox
                    padding = {
                        "left": round(left / rgba.width, 4),
                        "top": round(top / rgba.height, 4),
                        "right": round((rgba.width - right) / rgba.width, 4),
                        "bottom": round((rgba.height - bottom) / rgba.height, 4),
                    }
                    for side, ratio in padding.items():
                        if ratio > max_padding:
                            findings.append(Finding(
                                rid, artifact["source_file"], artifact["line"], "hard",
                                f"PNG 可见内容 {side} 边留白占 {ratio:.1%}，超过 {max_padding:.1%}。",
                                "收紧 viewBox 或调整布局；以渲染后的可见 bbox 为准。",
                                artifact["artifact_id"], {"padding": padding},
                            ))
                item = {
                    **{k: v for k, v in artifact.items() if k != "svg"},
                    "png": png_path.relative_to(ctx.output_dir).as_posix(),
                    "png_sha256": sha256_bytes(png_path.read_bytes()),
                    "pixel_size": [rgba.width, rgba.height],
                    "visible_bbox": list(bbox) if bbox else None,
                    "padding_ratio": padding,
                }
                manifest_items.append(item)
        except Exception as exc:
            findings.append(Finding(
                rid, artifact["source_file"], artifact["line"], "hard",
                f"无法读取渲染 PNG：{type(exc).__name__}: {exc}",
                "确认 PNG 完整且 Pillow 可读取。", artifact["artifact_id"],
            ))

    manifest = {
        "schema_version": "1.0.0",
        "candidate_sha": ctx.candidate_sha,
        "artifact_count": len(manifest_items),
        "artifacts": manifest_items,
    }
    manifest_sha = canonical_hash(manifest)
    manifest["render_manifest_sha"] = manifest_sha
    manifest_path = ctx.output_dir / f"render-manifest-{ctx.candidate_sha[:12]}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    dimensions = ctx.config.get("visual_review", {}).get("dimensions", [])
    template = {
        "schema_version": "1.0.0",
        "candidate_sha": ctx.candidate_sha,
        "render_manifest_sha": manifest_sha,
        "producer_id": ctx.producer_id,
        "reviewer_id": "",
        "reviewer_session_id": "",
        "independent": False,
        "reviewed_at": "",
        "artifacts": [
            {
                "artifact_id": item["artifact_id"],
                "kind": item.get("kind"),
                "png_sha256": item["png_sha256"],
                "verdict": "UNREVIEWED",
                "dimensions": {
                    dimension["id"]: {
                        "verdict": "UNREVIEWED",
                        "note": "",
                    }
                    for dimension in dimensions
                    if not dimension.get("applies_to")
                    or item.get("kind") in dimension.get("applies_to", [])
                },
                "note": "",
            }
            for item in manifest_items
        ],
    }
    template_path = ctx.output_dir / f"visual-review-{ctx.candidate_sha[:12]}.template.json"
    template_path.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    packet_paths = _create_contact_sheets(manifest_items, ctx.output_dir, packet_dir, Image, ImageDraw, ImageOps)

    if len(manifest_items) != len(artifacts):
        findings.append(Finding(
            rid, "", 0, "hard",
            f"应渲染 {len(artifacts)} 张内联 SVG，实际成功 {len(manifest_items)} 张。",
            "逐一修复失败图；数量不一致不得放行。",
        ))
    return CheckerOutput(
        findings=findings,
        metrics={
            "inline_svg_count": len(artifacts),
            "rendered_count": len(manifest_items),
            "render_manifest": manifest_path.name,
            "render_manifest_sha": manifest_sha,
            "visual_review_template": template_path.name,
            "contact_sheets": packet_paths,
        },
        artifacts=manifest_items,
    )


def _create_contact_sheets(items, output_dir, packet_dir, Image, ImageDraw, ImageOps) -> list[str]:
    packet_paths: list[str] = []
    per_packet = 8
    cell_w, cell_h = 480, 330
    for start in range(0, len(items), per_packet):
        subset = items[start:start + per_packet]
        sheet = Image.new("RGB", (cell_w * 2, cell_h * 4), "white")
        draw = ImageDraw.Draw(sheet)
        for position, item in enumerate(subset):
            column, row = position % 2, position // 2
            x, y = column * cell_w, row * cell_h
            with Image.open(output_dir / item["png"]) as original:
                thumb = ImageOps.contain(original.convert("RGBA"), (cell_w - 24, cell_h - 60))
                background = Image.new("RGBA", thumb.size, "white")
                background.alpha_composite(thumb)
                sheet.paste(background.convert("RGB"), (x + 12, y + 34))
            label = f"{item['artifact_id']}  {item['source_file']}:{item['line']}"
            draw.text((x + 12, y + 10), label[:78], fill="black")
        packet_index = start // per_packet + 1
        packet_path = packet_dir / f"packet-{packet_index:03d}.png"
        sheet.save(packet_path, format="PNG", optimize=True)
        packet_paths.append(packet_path.relative_to(output_dir).as_posix())
    return packet_paths
