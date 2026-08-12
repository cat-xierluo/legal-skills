#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "Pillow>=10.0.0",
# ]
# ///

"""从基础抽帧结果生成受预算限制的多模态审计包。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:
    print("❌ 缺少依赖: Pillow", file=sys.stderr)
    print("   请使用 uv 运行本脚本，或执行: pip install Pillow", file=sys.stderr)
    raise SystemExit(1)


SCHEMA_VERSION = "1.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成经济型多模态截图审计包")
    parser.add_argument("-i", "--input", required=True, help="基础抽帧输出目录（包含 _report.json）")
    parser.add_argument("-o", "--output", default=None, help="审计包目录（默认: <input>/_vision_audit）")
    parser.add_argument("--max-groups", type=int, default=8, help="最多审计多少组（默认: 8）")
    parser.add_argument("--max-images", type=int, default=24, help="最多纳入多少张唯一图片（默认: 24）")
    parser.add_argument("--thumb-width", type=int, default=240, help="联系表单图宽度（默认: 240）")
    parser.add_argument("--thumb-height", type=int, default=426, help="联系表单图高度（默认: 426）")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_report(root: Path) -> tuple[Path, dict[str, Any]]:
    report_path = root / "_report.json"
    if not report_path.is_file():
        raise ValueError(f"缺少基础报告: {report_path}")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"基础报告不是有效 JSON: {exc}") from exc
    frames = report.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("基础报告没有可审计的 frames 清单")
    return report_path, report


def _validate_entry(root: Path, item: dict[str, Any], *, source: str) -> dict[str, Any]:
    rel = str(item.get("filename") or "")
    if not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
        raise ValueError(f"非法图片相对路径: {rel!r}")
    path = (root / rel).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"图片路径越界: {rel}") from exc
    if not path.is_file():
        raise ValueError(f"报告图片不存在: {path}")
    actual_sha = sha256_file(path)
    expected_sha = str(item.get("sha256") or "")
    if expected_sha and expected_sha != actual_sha:
        raise ValueError(f"图片哈希与报告不一致: {rel}")
    return {
        "source": source,
        "path": rel,
        "absolute_path": str(path),
        "capture_time_seconds": item.get("capture_time_seconds"),
        "sha256": actual_sha,
        "selection_confidence": item.get("selection_confidence"),
        "temporal_group_id": item.get("temporal_group_id"),
        "reason": item.get("reason"),
        "seam_score": float(item.get("seam_score") or 0.0),
        "mixed_transition_score": float(item.get("mixed_transition_score") or 0.0),
    }


def _risk_score(frame: dict[str, Any], prev_gap: float, next_gap: float) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    if frame.get("selection_confidence") == "low":
        score += 3.0
        reasons.append("low_confidence")
    seam = float(frame.get("seam_score") or 0.0)
    mixed = float(frame.get("mixed_transition_score") or 0.0)
    if seam >= 0.55:
        score += min(2.0, seam * 2.0)
        reasons.append("vertical_seam")
    if mixed >= 0.20:
        score += min(3.0, mixed * 4.0)
        reasons.append("mixed_transition_risk")
    dense_gap = min(prev_gap, next_gap)
    if dense_gap < 2.0:
        score += max(0.0, 2.0 - dense_gap)
        reasons.append("dense_sequence")
    return score, reasons


def _candidate_groups(root: Path, report: dict[str, Any]) -> list[dict[str, Any]]:
    raw_frames = report["frames"]
    frames = [_validate_entry(root, item, source="kept") for item in raw_frames]
    groups: list[dict[str, Any]] = []
    for idx, frame in enumerate(frames):
        cur = float(frame.get("capture_time_seconds") or 0.0)
        prev = float(frames[idx - 1].get("capture_time_seconds") or cur) if idx > 0 else cur - 999.0
        nxt = float(frames[idx + 1].get("capture_time_seconds") or cur) if idx + 1 < len(frames) else cur + 999.0
        score, reasons = _risk_score(frame, cur - prev, nxt - cur)
        if score <= 0:
            continue
        members: list[dict[str, Any]] = []
        for pos, role in ((idx - 1, "previous"), (idx, "target"), (idx + 1, "following")):
            if 0 <= pos < len(frames):
                member = dict(frames[pos])
                member["role"] = role
                members.append(member)
        groups.append({
            "priority": round(score, 4),
            "reason_codes": reasons,
            "target_path": frame["path"],
            "images": members,
        })

    # 把同一时段被本地算法丢弃的切换候选加入附近高风险组，供 replace/补回判断。
    review = report.get("review") or {}
    drop_items = review.get("drop_candidates") or []
    validated_drops: list[dict[str, Any]] = []
    for item in drop_items:
        reason = str(item.get("reason") or "")
        if reason not in {
            "temporal_transition",
            "temporal_mixed_transition",
            "temporal_motion_redundant",
            "quality_transition",
            "min_gap",
        }:
            continue
        try:
            validated_drops.append(_validate_entry(root, item, source="drop_candidate"))
        except ValueError:
            # 报告可能记录了超过保存上限的历史项；准备审计时只使用真实存在且哈希有效者。
            continue

    for group in groups:
        target = next((item for item in group["images"] if item["role"] == "target"), None)
        if target is None:
            continue
        target_time = float(target.get("capture_time_seconds") or 0.0)
        nearby = sorted(
            (
                item for item in validated_drops
                if abs(float(item.get("capture_time_seconds") or 0.0) - target_time) <= 1.25
            ),
            key=lambda item: abs(float(item.get("capture_time_seconds") or 0.0) - target_time),
        )
        if nearby:
            candidate = dict(nearby[0])
            candidate["role"] = "discarded_candidate"
            group["images"].append(candidate)
            group["priority"] = round(float(group["priority"]) + 0.5, 4)
            group["reason_codes"] = list(dict.fromkeys([*group["reason_codes"], "nearby_discarded_candidate"]))

    groups.sort(key=lambda item: (-float(item["priority"]), str(item["target_path"])))
    return groups


def _select_budgeted_groups(groups: list[dict[str, Any]], max_groups: int, max_images: int) -> list[dict[str, Any]]:
    if max_groups <= 0 or max_images <= 0:
        raise ValueError("--max-groups 和 --max-images 必须大于 0")
    selected: list[dict[str, Any]] = []
    unique_paths: set[str] = set()
    for group in groups:
        paths = {str(item["path"]) for item in group["images"]}
        # 相邻目标可能生成高度重叠的三帧窗口。重叠超过 2/3 时保留优先级更高者，
        # 把稀缺的组预算留给其他时间区段。
        if any(
            len(paths & {str(item["path"]) for item in chosen["images"]})
            / float(max(1, min(len(paths), len(chosen["images"]))))
            >= 2.0 / 3.0
            for chosen in selected
        ):
            continue
        new_paths = paths - unique_paths
        if selected and len(unique_paths) + len(new_paths) > max_images:
            continue
        if not selected and len(paths) > max_images:
            group = dict(group)
            role_priority = {"target": 0, "previous": 1, "following": 2, "discarded_candidate": 3}
            group["images"] = sorted(
                group["images"],
                key=lambda item: role_priority.get(str(item.get("role") or ""), 9),
            )[:max_images]
            paths = {str(item["path"]) for item in group["images"]}
        selected.append(group)
        unique_paths.update(paths)
        if len(selected) >= max_groups or len(unique_paths) >= max_images:
            break
    return selected


def _safe_prepare_output(output_dir: Path) -> None:
    if output_dir.is_symlink():
        raise ValueError("审计输出目录是符号链接，拒绝跟随并覆盖")
    if output_dir.exists():
        unknown = [
            path for path in output_dir.iterdir()
            if path.is_symlink()
            or not path.is_file()
            or (
                path.name != "audit_manifest.json"
                and not re.fullmatch(r"contact_sheet_\d{3}\.jpg", path.name)
            )
        ]
        if unknown:
            names = ", ".join(p.name for p in unknown[:5])
            raise ValueError(f"审计输出目录含非本工具文件，拒绝覆盖: {names}")
        for path in output_dir.glob("contact_sheet_*.jpg"):
            path.unlink()
        manifest = output_dir / "audit_manifest.json"
        if manifest.exists():
            manifest.unlink()
    output_dir.mkdir(parents=True, exist_ok=True)


def _font(size: int) -> ImageFont.ImageFont:
    for name in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        path = Path(name)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def _render_contact_sheet(group: dict[str, Any], output_path: Path, width: int, height: int) -> None:
    padding = 12
    header = 44
    label_height = 56
    count = len(group["images"])
    canvas = Image.new("RGB", (padding + count * (width + padding), header + height + label_height + padding), "#ececec")
    draw = ImageDraw.Draw(canvas)
    draw.text((padding, 10), f"{group['group_id']} | {', '.join(group['reason_codes'])}", fill="#111111", font=_font(18))
    for idx, item in enumerate(group["images"]):
        image = Image.open(item["absolute_path"]).convert("RGB")
        fitted = ImageOps.contain(image, (width, height))
        x = padding + idx * (width + padding)
        y = header + (height - fitted.height) // 2
        canvas.paste(fitted, (x + (width - fitted.width) // 2, y))
        border = "#d32f2f" if item["role"] == "target" else "#444444"
        draw.rectangle((x, header, x + width, header + height), outline=border, width=4 if item["role"] == "target" else 2)
        label = f"{item['audit_id']}\n{item['role']} | {float(item.get('capture_time_seconds') or 0.0):.2f}s"
        draw.multiline_text((x, header + height + 6), label, fill="#111111", font=_font(15), spacing=2)
    canvas.save(output_path, format="JPEG", quality=88, optimize=True)


def main() -> int:
    args = parse_args()
    raw_root = Path(args.input).expanduser()
    if raw_root.is_symlink():
        print("错误: 基础输出目录是符号链接，拒绝跟随", file=sys.stderr)
        return 2
    root = raw_root.resolve()
    if not root.is_dir():
        print(f"错误: 输入目录不存在: {root}", file=sys.stderr)
        return 2
    raw_output = Path(args.output).expanduser() if args.output else root / "_vision_audit"
    if raw_output.is_symlink():
        print("错误: 审计输出目录是符号链接，拒绝跟随", file=sys.stderr)
        return 2
    output_dir = raw_output.resolve()
    try:
        if args.output is None:
            protected = [root / "_vision_review.json", root / "_curated"]
            existing = [path.name for path in protected if path.exists() or path.is_symlink()]
            if existing:
                names = "、".join(existing)
                raise ValueError(
                    f"基础目录含已完成的视觉复核产物（{names}），拒绝重建并使其失效；"
                    "请改用新的 -o 审计目录，或在备份后显式移走这些产物"
                )
        report_path, report = _load_report(root)
        groups = _candidate_groups(root, report)
        selected = _select_budgeted_groups(groups, args.max_groups, args.max_images)
        _safe_prepare_output(output_dir)
        audit_ids: dict[str, str] = {}
        next_id = 1
        for group_index, group in enumerate(selected, 1):
            group["group_id"] = f"group-{group_index:03d}"
            for item in group["images"]:
                rel = str(item["path"])
                if rel not in audit_ids:
                    audit_ids[rel] = f"img-{next_id:03d}"
                    next_id += 1
                item["audit_id"] = audit_ids[rel]
            contact_name = f"contact_sheet_{group_index:03d}.jpg"
            group["contact_sheet"] = contact_name
            _render_contact_sheet(group, output_dir / contact_name, args.thumb_width, args.thumb_height)

        unique_images: dict[str, dict[str, Any]] = {}
        clean_groups: list[dict[str, Any]] = []
        for group in selected:
            clean_images: list[dict[str, Any]] = []
            for item in group["images"]:
                clean = {key: value for key, value in item.items() if key != "absolute_path"}
                clean_images.append(clean)
                unique_images.setdefault(clean["audit_id"], clean)
            clean_groups.append({
                "group_id": group["group_id"],
                "priority": group["priority"],
                "reason_codes": group["reason_codes"],
                "target_path": group["target_path"],
                "contact_sheet": group["contact_sheet"],
                "images": clean_images,
            })

        manifest: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "status": "prepared",
            "source_root": str(root),
            "source_report": "_report.json",
            "source_report_sha256": sha256_file(report_path),
            "budget": {
                "max_groups": args.max_groups,
                "max_images": args.max_images,
                "actual_groups": len(clean_groups),
                "actual_images": len(unique_images),
                "candidate_groups_before_budget": len(groups),
            },
            "decision_contract": {
                "allowed_decisions": ["keep", "drop", "replace"],
                "allowed_reason_codes": [
                    "transition",
                    "visual_duplicate",
                    "semantic_duplicate",
                    "new_evidence",
                    "clearer_replacement",
                    "other",
                ],
                "rule": "只判断 manifest 内图片；replace 必须填写同一 manifest 内 replacement_audit_id。",
            },
            "groups": clean_groups,
            "images": list(unique_images.values()),
        }
        manifest_path = output_dir / "audit_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"完成: {manifest_path}")
        print(f"  候选组: {len(groups)}")
        print(f"  审计组: {len(clean_groups)}/{args.max_groups}")
        print(f"  唯一图片: {len(unique_images)}/{args.max_images}")
        return 0
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
