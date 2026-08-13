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

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import coverage_eligibility_metrics


SCHEMA_VERSION = "1.0"
WEAK_REASON_CODES_BY_OUTCOME = {
    "keep": ["new_evidence", "other"],
    "drop": ["transition", "visual_duplicate", "semantic_duplicate", "other"],
    "replace": ["clearer_replacement", "other"],
    "restore": ["new_evidence", "other"],
    "leave_discarded": ["transition", "visual_duplicate", "semantic_duplicate", "other"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成经济型多模态截图审计包")
    parser.add_argument("-i", "--input", required=True, help="基础抽帧输出目录（包含 _report.json）")
    parser.add_argument("-o", "--output", default=None, help="审计包目录（默认: <input>/_vision_audit）")
    parser.add_argument(
        "--profile",
        choices=["balanced", "weak"],
        default="balanced",
        help="视觉模型能力档位；weak 使用一组一题、大图和预填模板（默认: balanced）",
    )
    parser.add_argument("--max-groups", type=int, default=None, help="最多审计多少组（balanced 默认 8，weak 默认 6）")
    parser.add_argument("--max-images", type=int, default=None, help="最多纳入多少张唯一图片（balanced 默认 24，weak 默认 18）")
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
    transient_ui = item.get("transient_ui") if isinstance(item.get("transient_ui"), dict) else {}
    return {
        "source": source,
        "path": rel,
        "absolute_path": str(path),
        "capture_time_seconds": item.get("capture_time_seconds"),
        "sha256": actual_sha,
        "selection_confidence": item.get("selection_confidence"),
        "temporal_group_id": item.get("temporal_group_id"),
        "reason": item.get("reason"),
        "source_frame_index": item.get("source_frame_index"),
        "following_source_frame_index": item.get("following_source_frame_index"),
        "seam_score": float(item.get("seam_score") or 0.0),
        "mixed_transition_score": float(item.get("mixed_transition_score") or 0.0),
        "loading_overlay_score": float(item.get("loading_overlay_score") or transient_ui.get("score") or 0.0),
        "loading_overlay_label": item.get("loading_overlay_label") or transient_ui.get("label"),
        "quality_label": item.get("quality_label"),
        "quality_transition_risk": bool(item.get("quality_transition_risk")),
        "motion_density_mode": item.get("motion_density_mode"),
        "scroll_match_ratio": float(item.get("scroll_match_ratio") or 0.0),
        "content_delta": item.get("content_delta") if isinstance(item.get("content_delta"), dict) else {},
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
    loading = float(frame.get("loading_overlay_score") or 0.0)
    loading_label = str(frame.get("loading_overlay_label") or "")
    if loading_label == "loading_overlay":
        score += min(4.0, loading * 4.0)
        reasons.append("loading_overlay")
    elif loading_label == "incomplete_page":
        score += min(3.0, loading * 3.0)
        reasons.append("incomplete_page_risk")
    if bool(frame.get("quality_transition_risk")) or frame.get("quality_label") == "transition":
        score += 2.5
        reasons.append("quality_transition_risk")
    content_delta = frame.get("content_delta") or {}
    if bool(content_delta.get("ocr_available")):
        if not bool(content_delta.get("has_new_content")) and float(content_delta.get("ocr_similarity") or 0.0) >= 0.88:
            score += 2.5
            reasons.append("low_content_delta")
        elif int(content_delta.get("new_numeric_count") or 0) > 0:
            score += 1.0
            reasons.append("new_numeric_evidence")
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
                member_time = float(member.get("capture_time_seconds") or cur)
                if role != "target" and abs(member_time - cur) > 6.0:
                    continue
                member["role"] = role
                members.append(member)
        groups.append({
            "priority": round(score, 4),
            "reason_codes": reasons,
            "target_path": frame["path"],
            "target_time_seconds": cur,
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
            "temporal_short_motion_redundant",
            "temporal_mixed_transition",
            "temporal_motion_redundant",
            "quality_transition",
            "quality_loading_overlay",
            "quality_incomplete_page",
            "temporal_incomplete_resolved",
            "ocr_duplicate",
            "duplicate_scroll",
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

    # 高置信加载浮层或时序确认的未完成页已由代码自动删除，但仍应获得独立视觉复核入口；
    # 多模态若判断误删，可以对 discarded_candidate 使用 keep 补回。
    for item in validated_drops:
        reason = str(item.get("reason") or "")
        if reason not in {"quality_loading_overlay", "temporal_incomplete_resolved"}:
            continue
        target_time = float(item.get("capture_time_seconds") or 0.0)
        completion_source_index = item.get("following_source_frame_index")
        completion_context = next(
            (
                frame for frame in frames
                if completion_source_index is not None
                and frame.get("source_frame_index") is not None
                and int(frame["source_frame_index"]) == int(completion_source_index)
            ),
            None,
        )
        if reason == "temporal_incomplete_resolved" and completion_context is None:
            raise ValueError(
                "审计包缺少已删除未完成页所绑定的后续完整帧: "
                f"source_frame_index={completion_source_index}"
            )
        nearby_kept = sorted(
            frames,
            key=lambda frame: abs(float(frame.get("capture_time_seconds") or 0.0) - target_time),
        )[:2]
        if completion_context is not None and all(
            frame["path"] != completion_context["path"] for frame in nearby_kept
        ):
            nearby_kept = [completion_context, *nearby_kept[:1]]
        members: list[dict[str, Any]] = []
        for frame in sorted(nearby_kept, key=lambda frame: float(frame.get("capture_time_seconds") or 0.0)):
            member = dict(frame)
            member["role"] = "context"
            members.append(member)
        candidate = dict(item)
        candidate["role"] = "discarded_candidate"
        members.append(candidate)
        groups.append({
            "priority": 8.5 if reason == "quality_loading_overlay" else 9.2,
            "reason_codes": [
                "discarded_loading_overlay"
                if reason == "quality_loading_overlay"
                else "discarded_resolved_incomplete"
            ],
            "target_path": item["path"],
            "target_time_seconds": target_time,
            "images": members,
        })

    # 被时间簇阶段丢弃、但三帧分区覆盖风险较高的候选也需要独立恢复题。
    # 这能把算法已经吸收的切换中间态纳入抽样 QA，而不会把所有丢弃候选交给模型。
    regional_drops = sorted(
        (
            item for item in validated_drops
            if str(item.get("reason") or "") in {
                "temporal_motion_redundant",
                "temporal_short_motion_redundant",
                "temporal_transition",
            }
            and float(item.get("mixed_transition_score") or 0.0) >= 0.65
        ),
        key=lambda item: (-float(item.get("mixed_transition_score") or 0.0), float(item.get("capture_time_seconds") or 0.0)),
    )[:3]
    for item in regional_drops:
        target_time = float(item.get("capture_time_seconds") or 0.0)
        nearby_kept = sorted(
            frames,
            key=lambda frame: abs(float(frame.get("capture_time_seconds") or 0.0) - target_time),
        )[:2]
        members: list[dict[str, Any]] = []
        for frame in sorted(nearby_kept, key=lambda frame: float(frame.get("capture_time_seconds") or 0.0)):
            member = dict(frame)
            member["role"] = "context"
            members.append(member)
        candidate = dict(item)
        candidate["role"] = "discarded_candidate"
        members.append(candidate)
        groups.append({
            "priority": 9.0,
            "reason_codes": ["discarded_mixed_transition"],
            "target_path": item["path"],
            "target_time_seconds": target_time,
            "images": members,
        })

    # 多模态层只做减法：只有基础保留目标、且同组至少存在一个本地核准的
    # 同页覆盖候选时，才值得占用模型预算。丢弃候选可作为上下文，但不再成为恢复题。
    for group in groups:
        target = next((item for item in group["images"] if item.get("role") == "target"), None)
        group["has_eligible_coverage"] = False
        if target is None or target.get("source") != "kept":
            continue
        target_bytes = Path(str(target["absolute_path"])).read_bytes()
        for item in group["images"]:
            item["coverage_eligible_for_target"] = False
            if item.get("source") != "kept" or item["path"] == target["path"]:
                continue
            metrics = coverage_eligibility_metrics(
                target_bytes,
                Path(str(item["absolute_path"])).read_bytes(),
            )
            item["coverage_metrics"] = metrics
            item["coverage_eligible_for_target"] = bool(metrics.get("eligible"))
            if metrics.get("eligible"):
                group["has_eligible_coverage"] = True

    groups.sort(key=lambda item: (-float(item["priority"]), str(item["target_path"])))
    return groups


def _select_budgeted_groups(groups: list[dict[str, Any]], max_groups: int, max_images: int) -> list[dict[str, Any]]:
    if max_groups <= 0 or max_images <= 0:
        raise ValueError("--max-groups 和 --max-images 必须大于 0")
    selected: list[dict[str, Any]] = []
    unique_paths: set[str] = set()
    restore_group_count = 0
    restore_reason_families: set[str] = set()
    remaining = list(groups)
    while remaining:
        if selected:
            selected_times = [float(item.get("target_time_seconds") or 0.0) for item in selected]
            remaining.sort(
                key=lambda item: (
                    -(
                        float(item["priority"])
                        + min(
                            2.0,
                            min(
                                abs(float(item.get("target_time_seconds") or 0.0) - selected_time)
                                for selected_time in selected_times
                            ) / 30.0,
                        )
                    ),
                    str(item["target_path"]),
                )
            )
        group = remaining.pop(0)
        is_restore_group = not any(item.get("role") == "target" for item in group["images"])
        restore_family = next(
            (
                str(code) for code in group.get("reason_codes") or []
                if str(code).startswith("discarded_")
            ),
            "discarded_other",
        )
        restore_limit = min(2, max(1, max_groups // 3))
        if is_restore_group and (
            restore_group_count >= restore_limit
            or restore_family in restore_reason_families
        ):
            continue
        paths = {str(item["path"]) for item in group["images"]}
        # 相邻目标可能生成高度重叠的三帧窗口。重叠达到一半时保留优先级更高者，
        # 把稀缺的组预算留给其他时间区段。
        if any(
            len(paths & {str(item["path"]) for item in chosen["images"]})
            / float(max(1, min(len(paths), len(chosen["images"]))))
            >= 0.5
            for chosen in selected
        ):
            continue
        new_paths = paths - unique_paths
        if selected and len(unique_paths) + len(new_paths) > max_images:
            continue
        if not selected and len(paths) > max_images:
            group = dict(group)
            role_priority = {"target": 0, "discarded_candidate": 1, "context": 2, "previous": 3, "following": 4}
            group["images"] = sorted(
                group["images"],
                key=lambda item: role_priority.get(str(item.get("role") or ""), 9),
            )[:max_images]
            paths = {str(item["path"]) for item in group["images"]}
        selected.append(group)
        if is_restore_group:
            restore_group_count += 1
            restore_reason_families.add(restore_family)
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
                and path.name not in {"review_template.json", "MODEL_INSTRUCTIONS.md"}
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
        for name in ("review_template.json", "MODEL_INSTRUCTIONS.md"):
            path = output_dir / name
            if path.exists():
                path.unlink()
    output_dir.mkdir(parents=True, exist_ok=True)


def _font(size: int) -> ImageFont.ImageFont:
    for name in (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        path = Path(name)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def _render_contact_sheet(
    group: dict[str, Any],
    output_path: Path,
    width: int,
    height: int,
    *,
    profile: str,
) -> None:
    padding = 12
    header = 44
    label_height = 68 if profile == "weak" else 56
    count = len(group["images"])
    columns = min(count, 2) if profile == "weak" else count
    rows = (count + columns - 1) // columns
    cell_height = height + label_height
    canvas = Image.new(
        "RGB",
        (padding + columns * (width + padding), header + rows * cell_height + padding),
        "#ececec",
    )
    draw = ImageDraw.Draw(canvas)
    target_label = str(group.get("decision_target_visual_label") or "?")
    title = f"{group['group_id']} | 只判断 {target_label} | {', '.join(group['reason_codes'])}"
    draw.text((padding, 10), title, fill="#111111", font=_font(18))
    for idx, item in enumerate(group["images"]):
        image = Image.open(item["absolute_path"]).convert("RGB")
        fitted = ImageOps.contain(image, (width, height))
        row, col = divmod(idx, columns)
        x = padding + col * (width + padding)
        cell_top = header + row * cell_height
        y = cell_top + (height - fitted.height) // 2
        canvas.paste(fitted, (x + (width - fitted.width) // 2, y))
        is_decision_target = item["audit_id"] == group.get("decision_target_audit_id")
        border = "#d32f2f" if is_decision_target else "#355c7d"
        draw.rectangle(
            (x, cell_top, x + width, cell_top + height),
            outline=border,
            width=7 if is_decision_target else 3,
        )
        target_mark = " ← 唯一判断目标" if is_decision_target else ""
        label = (
            f"{item['visual_label']} / {item['audit_id']}{target_mark}\n"
            f"{item['role']} | {float(item.get('capture_time_seconds') or 0.0):.2f}s"
        )
        draw.multiline_text((x, cell_top + height + 6), label, fill="#111111", font=_font(17 if profile == "weak" else 15), spacing=2)
    canvas.save(output_path, format="JPEG", quality=88, optimize=True)


def _weak_model_instructions(manifest_sha256: str) -> str:
    return f"""# 弱多模态审计说明

一次只查看一张 `contact_sheet_NNN.jpg`，并只判断标题标出的“唯一判断目标”。不要判断其他图片。

1. 红框图片是目标；蓝框图片只是前后上下文。
2. 只有列在 `allowed_coverage_audit_ids` 中、且你确认完整覆盖目标全部内容的上下文，才能支持 `drop` 或 `replace`。
3. 看不清文字、不能确认覆盖、涉及金额/身份/地址/承诺时，选择 `keep`。
4. 在 `review_template.json` 原位填写：`outcome`、`coverage_audit_id`、`reason_code`、`reason`、`confidence`。覆盖帧只能从 `allowed_coverage_audit_ids` 选择；理由码按所选结果从 `reason_codes_by_outcome` 选择。不要新增组，不要修改任何 ID、哈希或允许选项。
5. `drop`/`replace` 必须填写同组蓝框图片的 `coverage_audit_id`；`keep` 留空。视觉层只对基础帧做减法，不恢复基础层未保留的图片。

manifest SHA256：`{manifest_sha256}`
"""


def _write_weak_review_template(output_dir: Path, manifest: dict[str, Any], manifest_path: Path) -> None:
    answers = []
    for group in manifest.get("groups") or []:
        coverage_ids = list(group.get("allowed_coverage_audit_ids") or [])
        answers.append({
            "group_id": group["group_id"],
            "target_audit_id": group["decision_target_audit_id"],
            "task_type": group["task_type"],
            "allowed_outcomes": group["allowed_outcomes"],
            "allowed_coverage_audit_ids": coverage_ids,
            "reason_codes_by_outcome": {
                outcome: WEAK_REASON_CODES_BY_OUTCOME[outcome]
                for outcome in group["allowed_outcomes"]
            },
            "outcome": "",
            "coverage_audit_id": "",
            "reason_code": "",
            "reason": "",
            "confidence": None,
        })
    manifest_sha = sha256_file(manifest_path)
    template = {
        "schema_version": "1.1",
        "status": "in_progress",
        "profile": "weak",
        "source_manifest_sha256": manifest_sha,
        "answers": answers,
    }
    (output_dir / "review_template.json").write_text(
        json.dumps(template, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "MODEL_INSTRUCTIONS.md").write_text(
        _weak_model_instructions(manifest_sha),
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    max_groups = args.max_groups if args.max_groups is not None else (6 if args.profile == "weak" else 8)
    max_images = args.max_images if args.max_images is not None else (18 if args.profile == "weak" else 24)
    thumb_width = args.thumb_width
    thumb_height = args.thumb_height
    if args.profile == "weak":
        if thumb_width == 240:
            thumb_width = 420
        if thumb_height == 426:
            thumb_height = 746
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
        all_groups = _candidate_groups(root, report)
        groups = [
            group for group in all_groups
            if any(item.get("role") == "target" for item in group.get("images") or [])
            and bool(group.get("has_eligible_coverage"))
        ]
        selected = _select_budgeted_groups(groups, max_groups, max_images)
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
            decision_target = next(
                (item for item in group["images"] if item.get("role") == "target"),
                None,
            )
            if decision_target is None:
                decision_target = next(
                    (item for item in group["images"] if item.get("role") == "discarded_candidate"),
                    None,
                )
            if decision_target is None:
                raise ValueError(f"审计组没有可判断目标: {group['group_id']}")
            for visual_index, item in enumerate(group["images"]):
                item["visual_label"] = chr(ord("A") + visual_index)
            group["decision_target_audit_id"] = decision_target["audit_id"]
            group["decision_target_visual_label"] = decision_target["visual_label"]
            if decision_target.get("source") == "drop_candidate":
                group["task_type"] = "discarded_candidate_review"
                group["allowed_outcomes"] = ["restore", "leave_discarded"]
                group["allowed_coverage_audit_ids"] = []
            else:
                group["task_type"] = "kept_target_review"
                allowed_coverage: list[str] = []
                for item in group["images"]:
                    if (
                        item.get("source") == "kept"
                        and item["audit_id"] != decision_target["audit_id"]
                        and item.get("coverage_eligible_for_target")
                    ):
                        allowed_coverage.append(str(item["audit_id"]))
                group["allowed_coverage_audit_ids"] = allowed_coverage
                if not allowed_coverage:
                    raise ValueError(f"减法审计组缺少本地核准覆盖帧: {group['group_id']}")
                group["allowed_outcomes"] = ["keep", "drop", "replace"]
            contact_name = f"contact_sheet_{group_index:03d}.jpg"
            group["contact_sheet"] = contact_name
            _render_contact_sheet(
                group,
                output_dir / contact_name,
                thumb_width,
                thumb_height,
                profile=args.profile,
            )

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
                "target_time_seconds": group.get("target_time_seconds"),
                "decision_target_audit_id": group["decision_target_audit_id"],
                "decision_target_visual_label": group["decision_target_visual_label"],
                "task_type": group["task_type"],
                "allowed_outcomes": group["allowed_outcomes"],
                "allowed_coverage_audit_ids": group["allowed_coverage_audit_ids"],
                "contact_sheet": group["contact_sheet"],
                "images": clean_images,
            })

        manifest: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "status": "prepared",
            "profile": args.profile,
            "source_root": str(root),
            "source_report": "_report.json",
            "source_report_sha256": sha256_file(report_path),
            "budget": {
                "max_groups": max_groups,
                "max_images": max_images,
                "actual_groups": len(clean_groups),
                "actual_images": len(unique_images),
                "candidate_groups_before_budget": len(groups),
                "candidate_groups_before_coverage_filter": len(all_groups),
                "ineligible_or_restore_groups_skipped": len(all_groups) - len(groups),
                "covered_time_buckets": sorted({
                    int(float(group.get("target_time_seconds") or 0.0) // 30.0)
                    for group in clean_groups
                }),
            },
            "decision_contract": (
                {
                    "mode": "weak_group_answers",
                    "schema_version": "1.1",
                    "operation": "subtract_only",
                    "rule": "每组只判断 decision_target_audit_id；填写 review_template.json，不修改任何 ID 或允许选项。",
                    "mutation_gate": {
                        "minimum_confidence": 0.90,
                        "coverage_source": "same_group_locally_eligible_kept_frame",
                        "requires_local_risk": True,
                        "requires_final_survival": True,
                        "fallback": "safe_noop",
                    },
                }
                if args.profile == "weak"
                else {
                    "mode": "image_decisions",
                    "schema_version": "1.0",
                    "operation": "subtract_only",
                    "allowed_decisions": ["keep", "drop", "replace"],
                    "allowed_reason_codes": [
                        "transition",
                        "visual_duplicate",
                        "semantic_duplicate",
                        "new_evidence",
                        "clearer_replacement",
                        "other",
                    ],
                    "mutation_gate": {
                        "minimum_confidence": 0.90,
                        "coverage_source": "same_group_locally_eligible_kept_frame",
                        "requires_local_risk": True,
                        "requires_final_survival": True,
                        "fallback": "safe_noop",
                    },
                    "rule": "只判断 manifest 内图片；drop/replace 必须填写代码核准且最终存活的 coverage_audit_id，replace 的 replacement_audit_id 必须与其相同。",
                }
            ),
            "groups": clean_groups,
            "images": list(unique_images.values()),
        }
        manifest_path = output_dir / "audit_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.profile == "weak":
            _write_weak_review_template(output_dir, manifest, manifest_path)
        print(f"完成: {manifest_path}")
        print(f"  候选组: {len(groups)}")
        print(f"  模型档位: {args.profile}")
        print(f"  审计组: {len(clean_groups)}/{max_groups}")
        print(f"  唯一图片: {len(unique_images)}/{max_images}")
        return 0
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
