#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "Pillow>=10.0.0",
# ]
# ///

"""video-screenshot 的确定性回归检查，不读取真实案件材料。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract as extract_module
from extract import (
    _archive_result,
    _build_coverage_requirements,
    _directory_tree_sha256,
    _inspect_existing_output,
    _promote_staged_output,
    _record_drop_candidate,
    _rescue_short_motion_with_ocr,
    _write_output_marker,
    parse_args as parse_extract_args,
)
from lib import (
    DedupState,
    ExtractParams,
    FFProbeInfo,
    calc_content_quality,
    calc_loading_overlay_score,
    content_quality_drop_reason,
    coverage_eligibility_metrics,
    horizontal_mixed_transition_score,
    ocr_content_delta,
    ocr_extract_text,
    regional_mixed_transition_score,
    select_temporal_representatives,
    temporal_completion_metrics,
    transient_ui_drop_reason,
    find_tool,
)
from prepare_evidence_leads import (
    _load_taxonomy,
    classify_evidence_text,
    visual_content_signals,
)


ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="video-screenshot 回归检查")
    parser.add_argument(
        "--case",
        choices=[
            "all",
            "temporal",
            "mixed-transition",
            "content-delta",
            "transient-ui",
            "temporal-completion",
            "adaptive-density",
            "vision-budget",
            "vision-diversity",
            "weak-vision-package",
            "weak-review-gate",
            "weak-membership",
            "valid-review",
            "replace-review",
            "coverage-survival",
            "invalid-review",
            "output-protection",
            "transactional-output",
            "archive-metadata",
            "evidence-signals",
            "evidence-package",
            "evidence-review",
            "evidence-review-boundary",
            "fault-invalid-review",
            "fault-evidence-review-boundary",
        ],
        default="all",
    )
    return parser.parse_args()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _test_temporal() -> None:
    base_thumb = bytes([80] * (48 * 48))
    base_ssim = bytes([80] * (32 * 32))
    items = [
        {
            "source_index": 1,
            "capture_time_seconds": 0.0,
            "thumb": base_thumb,
            "ssim_thumb": base_ssim,
            "blur_score": 20.0,
            "quality": {"label": ""},
            "seam_score": 0.7,
        },
        {
            "source_index": 2,
            "capture_time_seconds": 0.5,
            "thumb": base_thumb,
            "ssim_thumb": base_ssim,
            "blur_score": 360.0,
            "quality": {"label": ""},
            "seam_score": 0.0,
        },
        {
            "source_index": 3,
            "capture_time_seconds": 1.0,
            "thumb": base_thumb,
            "ssim_thumb": base_ssim,
            "blur_score": 80.0,
            "quality": {"label": ""},
            "seam_score": 0.1,
        },
    ]
    selected, dropped, stats = select_temporal_representatives(items, stable_max_gap_seconds=0.8)
    assert len(selected) == 1, selected
    assert selected[0]["source_index"] == 2, "簇内择优不得机械保留第一张"
    assert len(dropped) == 2
    assert stats["stable_duplicate_drop_count"] == 2

    # 没有前后稳定锚点的长运动段必须按跨度保留，不能整段判作切换。
    moving = []
    for idx in range(8):
        moving.append({
            "source_index": idx + 1,
            "capture_time_seconds": float(idx),
            "thumb": bytes([(idx * 23) % 255] * (48 * 48)),
            "ssim_thumb": bytes([(idx * 23) % 255] * (32 * 32)),
            "blur_score": 100.0 + idx,
            "quality": {"label": ""},
            "seam_score": 0.0,
        })
    selected, dropped, stats = select_temporal_representatives(moving, motion_chunk_seconds=2.5)
    assert len(selected) >= 3, "持续运动段必须周期性保留代表帧"
    assert stats["transition_drop_count"] == 0

    # 两个稳定页之间只有一个稀疏候选时，不能因候选自身 span=0 就当成短切换。
    sparse = []
    for idx, (seconds, shade) in enumerate(((0.0, 40), (0.5, 40), (50.0, 130), (100.0, 220), (100.5, 220)), 1):
        sparse.append({
            "source_index": idx,
            "capture_time_seconds": seconds,
            "thumb": bytes([shade] * (48 * 48)),
            "ssim_thumb": bytes([shade] * (32 * 32)),
            "blur_score": 100.0,
            "quality": {"label": ""},
            "seam_score": 0.0,
        })
    selected, dropped, _stats = select_temporal_representatives(
        sparse,
        stable_max_gap_seconds=1.0,
        transition_max_seconds=2.4,
    )
    assert any(item["source_index"] == 3 for item in selected), "长时间独立页不得误判为切换中间态"
    assert not any(
        item["source_index"] == 3 and item.get("drop_reason") == "temporal_transition"
        for item in dropped
    )

    # 短暂独立页即使夹在两个稳定页之间，也必须至少保留一张供视觉层做减法。
    brief = []
    for idx, (seconds, shade) in enumerate(
        ((0.0, 30), (0.4, 30), (0.9, 125), (1.4, 220), (1.8, 220)),
        1,
    ):
        brief.append({
            "source_index": idx,
            "capture_time_seconds": seconds,
            "thumb": bytes([shade] * (48 * 48)),
            "ssim_thumb": bytes([shade] * (32 * 32)),
            "blur_score": 120.0,
            "quality": {"label": ""},
            "seam_score": 0.0,
        })
    selected, dropped, stats = select_temporal_representatives(
        brief,
        stable_max_gap_seconds=0.8,
        transition_max_seconds=2.4,
    )
    assert any(item["source_index"] == 3 for item in selected), selected
    assert stats["short_motion_preserved_count"] == 1, stats
    assert not any(item.get("drop_reason") == "temporal_transition" for item in dropped), dropped


def _pattern(width: int, height: int, invert: bool = False) -> Image.Image:
    image = Image.new("L", (width, height), 230 if not invert else 30)
    draw = ImageDraw.Draw(image)
    for x in range(0, width, 8):
        shade = (40 + x * 3) % 210
        if invert:
            shade = 255 - shade
        draw.rectangle((x, 0, min(width - 1, x + 3), height - 1), fill=shade)
    for y in range(5, height, 14):
        draw.line((0, y, width - 1, y), fill=30 if not invert else 220, width=2)
    return image


def _test_mixed_transition() -> None:
    width, height = 72, 120
    previous = _pattern(width, height, invert=False)
    following = _pattern(width, height, invert=True)
    cut = 34
    current = Image.new("L", (width, height))
    current.paste(previous.crop((width - cut, 0, width, height)), (0, 0))
    current.paste(following.crop((0, 0, width - cut, height)), (cut, 0))
    result = horizontal_mixed_transition_score(previous, current, following)
    assert result["score"] >= 0.58, result
    assert result["orientation"] == "swipe_left", result

    ordinary = _pattern(width, height, invert=False)
    result = horizontal_mixed_transition_score(previous, ordinary, following)
    assert result["score"] < 0.58, result

    # 真实 UI 动画可能含缩放/位移，无法像素级拼合；分区归属仍应识别由两侧邻帧共同覆盖。
    regional_current = Image.new("L", (width, height), 128)
    regional_current.paste(previous.crop((0, 0, width, height // 2)), (0, 0))
    regional_current.paste(following.crop((0, height // 2, width, height)), (0, height // 2))
    regional = regional_mixed_transition_score(previous, regional_current, following)
    assert regional["score"] >= 0.35, regional
    assert regional["previous_regions"] > 0 and regional["following_regions"] > 0, regional


def _test_content_delta() -> None:
    previous = "用户张三订单金额￥1200收货地址北京市朝阳区"
    previous_set = set(previous[idx:idx + 3] for idx in range(len(previous) - 2))
    redundant = ocr_content_delta(previous, [previous], [previous_set], 0.92, 8)
    assert redundant["redundant"] is True, redundant
    assert redundant["has_new_content"] is False, redundant

    # 近似页面新增金额属于关键证据，即使整体文字高度相似也必须保留。
    changed = previous + "另行支付￥680"
    changed_delta = ocr_content_delta(changed, [previous], [previous_set], 0.80, 20)
    assert changed_delta["has_new_content"] is True, changed_delta
    assert changed_delta["new_numeric_count"] >= 1, changed_delta
    assert changed_delta["redundant"] is False, changed_delta
    assert changed_delta["protect_visual_duplicate"] is True, changed_delta

    # 1—2 位时间码变化不是证据数字，不得推翻图像去重。
    clock_changed = ocr_content_delta(previous + "00:01:13", [previous + "00:01:12"], [previous_set], 0.80, 20)
    assert clock_changed["new_numeric_count"] == 0, clock_changed
    assert clock_changed["protect_visual_duplicate"] is False, clock_changed

    def fake_ocr(_image_bytes: bytes) -> tuple[list[list[object]], None]:
        return [
            [[[0, 0], [1, 0], [1, 1], [0, 1]], "订单金额1200元", 0.98],
            [[[0, 2], [1, 2], [1, 3], [0, 3]], "收货地址北京", 0.96],
        ], None

    parsed = ocr_extract_text(fake_ocr, b"fixture")
    assert parsed == "订单金额1200元|收货地址北京", parsed

    # 非对称正文页会触发单帧 transition 启发式，但该标签只能提权审计，不能删除。
    asymmetric = Image.new("RGB", (360, 640), "white")
    draw = ImageDraw.Draw(asymmetric)
    draw.rectangle((15, 40, 155, 595), fill=(230, 230, 230))
    for y in range(55, 590, 18):
        draw.rectangle((25, y, 145, y + 5), fill=(10, 10, 10))
    quality = calc_content_quality(_image_bytes(asymmetric))
    assert quality["label"] == "transition", quality
    assert content_quality_drop_reason(quality) == "", quality

    # OCR 只检查短运动段的小集合，且每组最多补回一张有强新增编号的落选帧。
    with tempfile.TemporaryDirectory(prefix="video-screenshot-check-") as tmp:
        root = Path(tmp)
        representative_path = root / "representative.png"
        candidate_path = root / "candidate.png"
        asymmetric.save(representative_path)
        asymmetric.save(candidate_path)

        calls = iter(["订单页面", "订单页面编号123456新增证据正文甲乙丙丁"])

        def fake_engine(_image_bytes: bytes) -> tuple[list[list[object]], None]:
            text = next(calls)
            return [[[[0, 0], [1, 0], [1, 1], [0, 1]], text, 0.99]], None

        selected, dropped, stats = _rescue_short_motion_with_ocr(
            [{
                "source_index": 1,
                "frame_path": str(representative_path),
                "capture_time_seconds": 0.0,
                "temporal_group_id": "motion-001",
                "temporal_reason": "short_motion_representative",
            }],
            [{
                "source_index": 2,
                "frame_path": str(candidate_path),
                "capture_time_seconds": 0.2,
                "temporal_group_id": "motion-001",
                "drop_reason": "temporal_short_motion_redundant",
                "blur_score": 100.0,
                "quality": {"content_std": 60.0},
            }],
            fake_engine,
            ExtractParams(),
        )
        assert stats["ocr_short_motion_rescue_count"] == 1, stats
        assert any(item.get("temporal_reason") == "ocr_short_motion_rescue" for item in selected), selected
        assert not dropped, dropped

    related_a = Image.new("RGB", (180, 320), (245, 245, 245))
    draw = ImageDraw.Draw(related_a)
    draw.rectangle((11, 20, 160, 280), outline=(17, 50, 80), width=5)
    related_b = related_a.copy()
    ImageDraw.Draw(related_b).text((20, 45), "new", fill=(0, 0, 0))
    unrelated = Image.new("RGB", (180, 320), (0, 0, 0))
    ImageDraw.Draw(unrelated).ellipse((30, 100, 150, 220), fill=(255, 255, 255))
    assert coverage_eligibility_metrics(
        _image_bytes(related_a), _image_bytes(related_b)
    )["eligible"] is True
    assert coverage_eligibility_metrics(
        _image_bytes(related_a), _image_bytes(unrelated)
    )["eligible"] is False


def _image_bytes(image: Image.Image) -> bytes:
    import io
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _test_transient_ui() -> None:
    width, height = 360, 640
    loading = Image.new("L", (width, height), 95)
    draw = ImageDraw.Draw(loading)
    draw.rectangle((126, 224, 234, 435), fill=245)
    draw.ellipse((155, 285, 205, 335), outline=150, width=7)
    draw.text((140, 350), "loading", fill=80)
    loading_result = calc_loading_overlay_score(_image_bytes(loading))
    assert loading_result["label"] in {"loading_overlay", "incomplete_page"}, loading_result
    if loading_result["label"] == "loading_overlay":
        assert transient_ui_drop_reason(loading_result) == "quality_loading_overlay", loading_result

    # 低信息白页可能值得审计，但代码不得因“疑似未完成”就直接删除。
    incomplete = dict(loading_result)
    incomplete["label"] = "incomplete_page"
    incomplete["score"] = 0.99
    assert transient_ui_drop_reason(incomplete) == "", incomplete

    # 合法白底长页可包含大量文字/线条，不能只因白色比例高而判加载或未完成页。
    legal_page = Image.new("L", (width, height), 250)
    draw = ImageDraw.Draw(legal_page)
    for row in range(30, 610, 28):
        draw.line((28, row, 330, row), fill=55, width=3)
    legal_result = calc_loading_overlay_score(_image_bytes(legal_page))
    assert not legal_result["label"], legal_result

    # 候选池已满时，高风险加载浮层必须替换普通候选，不能因时间靠后丢失审计证据。
    with tempfile.TemporaryDirectory(prefix="video-screenshot-check-") as tmp:
        root = Path(tmp)
        source = root / "source.jpg"
        loading.convert("RGB").save(source)
        candidates: list[dict] = []
        _record_drop_candidate(str(root), str(source), 1, "min_gap", 1.0, "a" * 64, candidates, enabled=True, limit=1)
        _record_drop_candidate(
            str(root), str(source), 2, "quality_loading_overlay", 2.0, "b" * 64,
            candidates, enabled=True, limit=1, extra={"transient_ui": loading_result},
        )
        assert len(candidates) == 1, candidates
        assert candidates[0]["reason"] == "quality_loading_overlay", candidates
        assert len(list((root / "_review_candidates").glob("candidate_*.jpg"))) == 1


def _test_temporal_completion() -> None:
    width, height = 72, 120
    incomplete = Image.new("L", (width, height), 245)
    complete = Image.new("L", (width, height), 245)
    incomplete_draw = ImageDraw.Draw(incomplete)
    complete_draw = ImageDraw.Draw(complete)
    # 共同页面骨架位于上部；完整页的主内容区增加多行信息。
    for draw in (incomplete_draw, complete_draw):
        draw.rectangle((4, 15, 67, 42), outline=35, width=2)
        draw.line((9, 24, 58, 24), fill=80, width=2)
        draw.line((9, 33, 45, 33), fill=100, width=2)
    for y in range(58, 108, 8):
        complete_draw.line((7, y, 65, y), fill=40, width=2)
    loading = {"label": "incomplete_page", "score": 0.99}
    completion = temporal_completion_metrics(incomplete, complete, loading)
    assert completion["resolved"] is True, completion

    complete_items = []
    for index, (seconds, image, loading_metrics) in enumerate((
        (0.0, incomplete, loading),
        (0.5, complete, {"label": "", "score": 0.0}),
        (1.0, complete, {"label": "", "score": 0.0}),
    ), 1):
        complete_items.append({
            "source_index": index,
            "capture_time_seconds": seconds,
            "thumb": bytes([index * 50] * (48 * 48)),
            "ssim_thumb": bytes([index * 50] * (32 * 32)),
            "blur_score": 120.0,
            "quality": {"label": ""},
            "loading_overlay": loading_metrics,
            "seam_score": 0.0,
            "transition_image": image,
            "scroll_image": image,
        })
    _selected, dropped, stats = select_temporal_representatives(complete_items)
    assert any(item.get("drop_reason") == "temporal_incomplete_resolved" for item in dropped), dropped
    assert stats["resolved_incomplete_drop_count"] == 1, stats
    requirements = _build_coverage_requirements(dropped)
    assert requirements == {2: [1]}, requirements

    # OCR 模式须禁用自动删除，以便后续内容增量保护完整运行。
    _selected, dropped, stats = select_temporal_representatives(
        complete_items,
        allow_incomplete_resolution=False,
    )
    assert not any(item.get("drop_reason") == "temporal_incomplete_resolved" for item in dropped), dropped
    assert stats["resolved_incomplete_drop_count"] == 0, stats

    # 后帧没有新增主内容时不得仅凭 loading 标签删除。
    unresolved = temporal_completion_metrics(incomplete, incomplete.copy(), loading)
    assert unresolved["resolved"] is False, unresolved


def _temporal_item(index: int, seconds: float, scroll: Image.Image) -> dict:
    return {
        "source_index": index,
        "capture_time_seconds": seconds,
        "thumb": bytes([(index * 37) % 255] * (48 * 48)),
        "ssim_thumb": bytes([(index * 37) % 255] * (32 * 32)),
        "blur_score": 180.0,
        "quality": {"label": ""},
        "loading_overlay": {"score": 0.0, "label": ""},
        "seam_score": 0.0,
        "scroll_image": scroll,
    }


def _test_adaptive_density() -> None:
    base = _pattern(96, 240)
    scrolling: list[dict] = []
    for idx in range(8):
        # 同一长页逐步滚动：相邻帧有高重叠，应放宽 motion chunk，减少过密代表帧。
        canvas = Image.new("L", (96, 160), 255)
        canvas.paste(base.crop((0, idx * 8, 96, idx * 8 + 160)), (0, 0))
        scrolling.append(_temporal_item(idx + 1, float(idx), canvas))
    selected, _dropped, stats = select_temporal_representatives(scrolling, motion_chunk_seconds=2.5)
    assert stats["adaptive_motion_group_count"] >= 1, stats
    assert any(item.get("motion_density_mode") == "scroll_redundant" for item in selected), selected
    assert len(selected) <= 3, selected


def _write_fixture(root: Path) -> tuple[Path, Path]:
    frames: list[dict] = []
    for idx in range(1, 13):
        image = Image.new("RGB", (180, 320), (245, 245, 245))
        draw = ImageDraw.Draw(image)
        draw.rectangle((10 + idx, 20, 160, 280), outline=(idx * 17 % 255, 50, 80), width=5)
        draw.text((20, 40 + idx * 3), f"frame {idx}", fill=(0, 0, 0))
        filename = f"frame_{idx:03d}_00m{idx:02d}s.jpg"
        path = root / filename
        image.save(path, quality=92)
        frames.append({
            "index": idx,
            "filename": filename,
            "capture_time_seconds": float(idx),
            "sha256": _sha(path),
            "selection_confidence": "low" if idx % 2 else "high",
            "seam_score": 0.8 if idx % 3 == 0 else 0.0,
            "mixed_transition_score": 0.0,
        })
    report = {
        "input": "synthetic.mp4",
        "frames": frames,
        "review": {"drop_candidates": []},
    }
    report_path = root / "_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report_path, root / "_vision_audit" / "audit_manifest.json"


def _test_vision_budget() -> None:
    with tempfile.TemporaryDirectory(prefix="video-screenshot-check-") as tmp:
        root = Path(tmp)
        _report_path, manifest_path = _write_fixture(root)
        command = [
            sys.executable,
            str(ROOT / "prepare_vision_audit.py"),
            "-i",
            str(root),
            "--max-groups",
            "3",
            "--max-images",
            "7",
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["budget"]["actual_groups"] <= 3
        assert manifest["budget"]["actual_images"] <= 7
        assert len(list(manifest_path.parent.glob("contact_sheet_*.jpg"))) == manifest["budget"]["actual_groups"]


def _test_vision_diversity() -> None:
    with tempfile.TemporaryDirectory(prefix="video-screenshot-check-") as tmp:
        root = Path(tmp)
        report_path, manifest_path = _write_fixture(root)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        # 拉开为多个时间簇，同时保留簇内相似覆盖帧，验证预算会分散到不同阶段。
        for idx, frame in enumerate(report["frames"]):
            frame["capture_time_seconds"] = float((idx // 2) * 30 + (idx % 2))
            frame["selection_confidence"] = "low"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ROOT / "prepare_vision_audit.py"), "-i", str(root), "--max-groups", "4", "--max-images", "12"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        buckets = manifest["budget"]["covered_time_buckets"]
        assert len(buckets) >= 3, buckets


def _test_weak_vision_package() -> None:
    with tempfile.TemporaryDirectory(prefix="video-screenshot-check-") as tmp:
        root = Path(tmp)
        report_path, manifest_path = _write_fixture(root)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        review_dir = root / "_review_candidates"
        review_dir.mkdir()
        discarded = review_dir / "candidate_001_quality_loading_overlay_00m01s.jpg"
        Image.open(root / report["frames"][0]["filename"]).save(discarded)
        report["review"]["drop_candidates"] = [{
            "filename": str(Path("_review_candidates") / discarded.name),
            "reason": "quality_loading_overlay",
            "capture_time_seconds": 1.1,
            "sha256": _sha(discarded),
        }]
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "prepare_vision_audit.py"),
                "-i",
                str(root),
                "--profile",
                "weak",
                "--max-groups",
                "2",
                "--max-images",
                "6",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["profile"] == "weak"
        assert manifest["budget"]["actual_groups"] <= 2
        for group in manifest["groups"]:
            targets = [
                item for item in group["images"]
                if item["audit_id"] == group["decision_target_audit_id"]
            ]
            assert len(targets) == 1, group
            assert group["task_type"] == "kept_target_review"
            assert group["allowed_outcomes"], group
        template = json.loads((manifest_path.parent / "review_template.json").read_text(encoding="utf-8"))
        assert template["schema_version"] == "1.1"
        assert template["profile"] == "weak"
        assert len(template["answers"]) == manifest["budget"]["actual_groups"]
        assert manifest["decision_contract"]["mode"] == "weak_group_answers"
        assert manifest["decision_contract"]["mutation_gate"]["fallback"] == "safe_noop"
        assert manifest["budget"]["ineligible_or_restore_groups_skipped"] >= 1
        assert template["answers"][0]["reason_codes_by_outcome"], template["answers"][0]
        assert "allowed_coverage_audit_ids" in template["answers"][0]
        assert (manifest_path.parent / "MODEL_INSTRUCTIONS.md").is_file()
        first_sheet = Image.open(manifest_path.parent / manifest["groups"][0]["contact_sheet"])
        assert first_sheet.width >= 800, first_sheet.size
        assert all("restore" not in group["allowed_outcomes"] for group in manifest["groups"])


def _run_weak_review(*, confidence: float, coverage_mode: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="video-screenshot-check-") as tmp:
        root = Path(tmp)
        _report_path, manifest_path = _write_fixture(root)
        prepare = subprocess.run(
            [sys.executable, str(ROOT / "prepare_vision_audit.py"), "-i", str(root), "--profile", "weak", "--max-groups", "2", "--max-images", "6"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert prepare.returncode == 0, prepare.stderr
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        group = next(item for item in manifest["groups"] if item["task_type"] == "kept_target_review")
        target = group["decision_target_audit_id"]
        same_group = group["allowed_coverage_audit_ids"][0]
        other_group = next(
            item["audit_id"]
            for candidate_group in manifest["groups"]
            if candidate_group["group_id"] != group["group_id"]
            for item in candidate_group["images"]
            if item["audit_id"] != target
        )
        coverage = same_group if coverage_mode == "same" else other_group
        review_path = root / "_vision_review.json"
        template = json.loads((manifest_path.parent / "review_template.json").read_text(encoding="utf-8"))
        for answer in template["answers"]:
            answer["outcome"] = "keep" if answer["task_type"] == "kept_target_review" else "leave_discarded"
            answer["coverage_audit_id"] = ""
            answer["reason_code"] = "other"
            answer["reason"] = "合成用例：默认维持基础结果"
            answer["confidence"] = 0.80
        selected_answer = next(answer for answer in template["answers"] if answer["group_id"] == group["group_id"])
        selected_answer.update({
            "outcome": "drop",
            "coverage_audit_id": coverage,
            "reason_code": "transition",
            "reason": "合成用例：相邻完整帧覆盖目标内容",
            "confidence": confidence,
        })
        template["status"] = "completed"
        review_path.write_text(
            json.dumps({
                **template,
                "source_manifest_sha256": _sha(manifest_path),
            }, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        apply_result = subprocess.run(
            [sys.executable, str(ROOT / "apply_vision_review.py"), "-i", str(root), "-r", str(review_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert apply_result.returncode == 0, apply_result.stdout + apply_result.stderr
        return json.loads((root / "_curated" / "_curated_report.json").read_text(encoding="utf-8"))


def _test_weak_review_gate() -> None:
    low = _run_weak_review(confidence=0.82, coverage_mode="same")
    assert low["curated_frame_count"] == 12, low["decision_summary"]
    assert low["decision_summary"]["dropped"] == 0
    assert low["decision_summary"]["safe_noop_count"] == 1

    cross_group = _run_weak_review(confidence=0.97, coverage_mode="other")
    assert cross_group["curated_frame_count"] == 12, cross_group["decision_summary"]
    assert cross_group["decision_summary"]["safe_noop_count"] == 1

    accepted = _run_weak_review(confidence=0.97, coverage_mode="same")
    assert accepted["curated_frame_count"] == 11, accepted["decision_summary"]
    assert accepted["decision_summary"]["dropped"] == 1


def _test_weak_repeated_image_group_membership() -> None:
    manifest = {
        "groups": [
            {"group_id": "group-001", "images": [{"audit_id": "img-shared"}, {"audit_id": "img-a"}]},
            {"group_id": "group-002", "images": [{"audit_id": "img-shared"}, {"audit_id": "img-b"}]},
        ]
    }
    from apply_vision_review import _group_index
    _groups, memberships = _group_index(manifest)
    assert memberships["img-shared"] == {"group-001", "group-002"}, memberships


def _run_invalid_review_fault() -> tuple[int, str, bool]:
    with tempfile.TemporaryDirectory(prefix="video-screenshot-check-") as tmp:
        root = Path(tmp)
        _report_path, manifest_path = _write_fixture(root)
        prepare = subprocess.run(
            [sys.executable, str(ROOT / "prepare_vision_audit.py"), "-i", str(root), "--max-groups", "2", "--max-images", "5"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert prepare.returncode == 0, prepare.stderr
        invalid_review = root / "_vision_review.json"
        invalid_review.write_text(
            json.dumps({
                "schema_version": "1.0",
                "status": "completed",
                "source_manifest_sha256": _sha(manifest_path),
                "decisions": [{
                    "audit_id": "img-outside-manifest",
                    "decision": "drop",
                    "reason_code": "transition",
                    "reason": "故障注入：越界引用",
                    "confidence": 0.99,
                }],
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        apply_result = subprocess.run(
            [sys.executable, str(ROOT / "apply_vision_review.py"), "-i", str(root), "-r", str(invalid_review)],
            capture_output=True,
            text=True,
            check=False,
        )
        return (
            apply_result.returncode,
            apply_result.stdout + apply_result.stderr,
            (root / "_curated").exists(),
        )


def _test_invalid_review() -> None:
    returncode, output, curated_exists = _run_invalid_review_fault()
    assert returncode == 2, output
    assert not curated_exists, "错误审计不得产生精选目录"


def _test_valid_review() -> None:
    with tempfile.TemporaryDirectory(prefix="video-screenshot-check-") as tmp:
        root = Path(tmp)
        _report_path, manifest_path = _write_fixture(root)
        prepare = subprocess.run(
            [sys.executable, str(ROOT / "prepare_vision_audit.py"), "-i", str(root), "--max-groups", "2", "--max-images", "5"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert prepare.returncode == 0, prepare.stderr
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        group = next(item for item in manifest["groups"] if item["allowed_coverage_audit_ids"])
        target_id = group["decision_target_audit_id"]
        coverage_id = group["allowed_coverage_audit_ids"][0]
        review_path = root / "_vision_review.json"
        review_path.write_text(
            json.dumps({
                "schema_version": "1.0",
                "status": "completed",
                "source_manifest_sha256": _sha(manifest_path),
                "decisions": [{
                    "audit_id": target_id,
                    "decision": "drop",
                    "coverage_audit_id": coverage_id,
                    "reason_code": "transition",
                    "reason": "合成正向用例：该目标帧视为切换中间态",
                    "confidence": 0.95,
                }],
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(ROOT / "apply_vision_review.py"), "-i", str(root), "-r", str(review_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        curated = json.loads((root / "_curated" / "_curated_report.json").read_text(encoding="utf-8"))
        assert curated["curated_frame_count"] == 11
        assert curated["decision_summary"]["dropped"] == 1
        assert len(curated["excluded_by_vision"]) == 1
        assert len(list((root / "_curated").glob("curated_*.jpg"))) == 11


def _test_replace_review() -> None:
    with tempfile.TemporaryDirectory(prefix="video-screenshot-check-") as tmp:
        root = Path(tmp)
        _report_path, manifest_path = _write_fixture(root)
        prepare = subprocess.run(
            [sys.executable, str(ROOT / "prepare_vision_audit.py"), "-i", str(root), "--max-groups", "2", "--max-images", "5"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert prepare.returncode == 0, prepare.stderr
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        group = next(item for item in manifest["groups"] if item["allowed_coverage_audit_ids"])
        target_id = group["decision_target_audit_id"]
        coverage_id = group["allowed_coverage_audit_ids"][0]
        review_path = root / "_vision_review.json"
        review_path.write_text(
            json.dumps({
                "schema_version": "1.0",
                "status": "completed",
                "source_manifest_sha256": _sha(manifest_path),
                "decisions": [{
                    "audit_id": target_id,
                    "decision": "replace",
                    "replacement_audit_id": coverage_id,
                    "coverage_audit_id": coverage_id,
                    "reason_code": "clearer_replacement",
                    "reason": "合成正向用例：后一张覆盖同一内容且更清晰",
                    "confidence": 0.96,
                }],
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(ROOT / "apply_vision_review.py"), "-i", str(root), "-r", str(review_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        curated = json.loads((root / "_curated" / "_curated_report.json").read_text(encoding="utf-8"))
        assert curated["curated_frame_count"] == 11
        assert curated["decision_summary"]["replaced"] == 1
        assert len(curated["excluded_by_vision"]) == 1


def _test_coverage_survival() -> None:
    from apply_vision_review import _enforce_final_coverage_survival

    chain, chain_noops = _enforce_final_coverage_survival({
        "img-a": {"decision": "drop", "coverage_audit_id": "img-b"},
        "img-b": {"decision": "drop", "coverage_audit_id": "img-c"},
    }, [])
    assert set(chain) == {"img-b"}, chain
    assert len(chain_noops) == 1 and chain_noops[0]["target_audit_id"] == "img-a", chain_noops

    cycle, cycle_noops = _enforce_final_coverage_survival({
        "img-a": {"decision": "drop", "coverage_audit_id": "img-b"},
        "img-b": {"decision": "drop", "coverage_audit_id": "img-a"},
    }, [])
    assert cycle == {}, cycle
    assert len(cycle_noops) == 2, cycle_noops


def _test_output_protection() -> None:
    with tempfile.TemporaryDirectory(prefix="video-screenshot-check-") as tmp:
        root = Path(tmp)
        review = root / "_vision_review.json"
        review.write_text("{}\n", encoding="utf-8")
        try:
            _inspect_existing_output(root)
        except RuntimeError as exc:
            assert "拒绝覆盖" in str(exc)
        else:
            raise AssertionError("既有视觉审计不得被基础抽帧自动删除")
        assert review.is_file()

    with tempfile.TemporaryDirectory(prefix="video-screenshot-check-") as tmp:
        root = Path(tmp)
        _write_fixture(root)
        review = root / "_vision_review.json"
        review.write_text("{}\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ROOT / "prepare_vision_audit.py"), "-i", str(root)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 2
        assert "拒绝重建" in result.stderr
        assert review.is_file()
        assert not (root / "_vision_audit").exists()


def _make_tiny_video(path: Path) -> None:
    ffmpeg = find_tool("ffmpeg")
    assert ffmpeg, "事务性 CLI 回归需要 ffmpeg"
    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=160x96:rate=5:duration=2",
            "-c:v",
            "mpeg4",
            "-q:v",
            "3",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0 and path.is_file(), result.stderr


def _run_extract(input_path: Path, output_path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "extract.py"),
            "-i",
            str(input_path),
            "-o",
            str(output_path),
            "--no-archive",
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )


def _test_transactional_output() -> None:
    with tempfile.TemporaryDirectory(prefix="video-screenshot-transaction-") as tmp:
        root = Path(tmp)
        valid_video = root / "valid.mp4"
        broken_video = root / "broken.mp4"
        broken_video.write_bytes(b"not a video\n")
        _make_tiny_video(valid_video)

        # 损坏输入必须在读取旧输出之前失败，旧结果逐字节不变。
        old_output = root / "old-output"
        old_output.mkdir()
        _write_fixture(old_output)
        before_broken = _directory_tree_sha256(old_output)
        broken_result = _run_extract(broken_video, old_output)
        assert broken_result.returncode != 0, broken_result.stdout
        assert _directory_tree_sha256(old_output) == before_broken

        # 参数错误也不得触碰旧输出。
        invalid_result = _run_extract(valid_video, old_output, "--quality", "99")
        assert invalid_result.returncode != 0, invalid_result.stdout
        assert _directory_tree_sha256(old_output) == before_broken

        # 非空未知目录失败关闭，不删除用户文件。
        unknown_output = root / "unknown-output"
        unknown_output.mkdir()
        sentinel = unknown_output / "user-note.txt"
        sentinel.write_text("keep me\n", encoding="utf-8")
        unknown_before = _directory_tree_sha256(unknown_output)
        unknown_result = _run_extract(valid_video, unknown_output)
        assert unknown_result.returncode != 0, unknown_result.stdout
        assert _directory_tree_sha256(unknown_output) == unknown_before

        # 下游证据线索产物存在时不得原地重跑基础抽帧。
        evidence_output = root / "evidence-output"
        evidence_output.mkdir()
        _write_fixture(evidence_output)
        evidence_dir = evidence_output / "_evidence_leads"
        evidence_dir.mkdir()
        (evidence_dir / "evidence_index.json").write_text("{}\n", encoding="utf-8")
        evidence_before = _directory_tree_sha256(evidence_output)
        evidence_result = _run_extract(valid_video, evidence_output)
        assert evidence_result.returncode != 0, evidence_result.stdout
        assert _directory_tree_sha256(evidence_output) == evidence_before

        # 输出根符号链接不得被跟随。
        real_output = root / "real-output"
        real_output.mkdir()
        real_sentinel = real_output / "sentinel.txt"
        real_sentinel.write_text("untouched\n", encoding="utf-8")
        linked_output = root / "linked-output"
        linked_output.symlink_to(real_output, target_is_directory=True)
        linked_result = _run_extract(valid_video, linked_output)
        assert linked_result.returncode != 0, linked_result.stdout
        assert real_sentinel.read_text(encoding="utf-8") == "untouched\n"

        # 合法旧版结果可在完整生成后一次性替换，并写入所有权标记。
        success_result = _run_extract(
            valid_video,
            old_output,
            "--strategy",
            "interval",
            "--interval",
            "0.5",
            "--no-temporal-select",
            "--no-filter-quality",
            "--dedup-threshold",
            "0",
            "--ssim-threshold",
            "0",
            "--min-gap",
            "0",
        )
        assert success_result.returncode == 0, success_result.stderr
        assert (old_output / "_video_screenshot_output.json").is_file()
        committed_state = _inspect_existing_output(old_output)
        assert committed_state["ownership_mode"] == "marker", committed_state

        # 所有权标记还要绑定真实内容；手工改过的旧帧不能被当作纯工具输出删除。
        tampered_frame = next(old_output.glob("frame_*.jpg"))
        tampered_frame.write_bytes(tampered_frame.read_bytes() + b"manual-edit")
        tampered_before = _directory_tree_sha256(old_output)
        tampered_result = _run_extract(valid_video, old_output)
        assert tampered_result.returncode != 0, tampered_result.stdout
        assert _directory_tree_sha256(old_output) == tampered_before

        # 提交动作自身失败时，已经移到备份位的旧目录必须自动恢复。
        rollback_target = root / "rollback-output"
        rollback_target.mkdir()
        _write_fixture(rollback_target)
        _write_output_marker(rollback_target)
        expected_state = _inspect_existing_output(rollback_target)
        rollback_before = _directory_tree_sha256(rollback_target)
        rollback_stage = root / ".rollback-output.staging-test"
        rollback_stage.mkdir()
        _write_fixture(rollback_stage)
        _write_output_marker(rollback_stage)
        original_rename = Path.rename

        def fail_staging_rename(self: Path, target: Path) -> Path:
            if self == rollback_stage:
                raise OSError("injected promotion failure")
            return original_rename(self, target)

        with patch.object(Path, "rename", fail_staging_rename):
            try:
                _promote_staged_output(rollback_stage, rollback_target, expected_state)
            except RuntimeError as exc:
                assert "旧输出已保留" in str(exc), exc
            else:
                raise AssertionError("注入提交失败后必须返回失败")
        assert _directory_tree_sha256(rollback_target) == rollback_before
        assert rollback_stage.is_dir(), "失败的新结果应留给调用方 finally 清理"


def _test_archive_metadata_only() -> None:
    with tempfile.TemporaryDirectory(prefix="video-screenshot-archive-") as tmp:
        temp_root = Path(tmp)
        output_root = temp_root / "output"
        output_root.mkdir()
        report_path, _manifest_path = _write_fixture(output_root)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        review_dir = output_root / "_review_candidates"
        review_dir.mkdir()
        review_image = review_dir / "candidate_001_min_gap_00m01s.jpg"
        Image.new("RGB", (32, 32), "white").save(review_image)

        archive_root = temp_root / "archive-result"
        archive_root.mkdir()
        original_builder = extract_module._build_archive_subdir
        extract_module._build_archive_subdir = lambda _video_path: archive_root
        try:
            args = parse_extract_args(["-i", str(temp_root / "synthetic.mp4")])
            state = DedupState(total_count=15, kept_count=len(report["frames"]))
            result = _archive_result(
                str(output_root),
                str(temp_root / "synthetic.mp4"),
                FFProbeInfo(duration_seconds=12.0, frame_rate_fps=30.0),
                ExtractParams(),
                args,
                state,
                report["frames"],
                {},
                [{"filename": str(Path("_review_candidates") / review_image.name)}],
                elapsed_seconds=1.25,
            )
        finally:
            extract_module._build_archive_subdir = original_builder

        assert result == archive_root
        assert sorted(path.name for path in archive_root.iterdir()) == ["_report.json", "extraction_meta.json"]
        assert not list(archive_root.rglob("*.jpg")), "metadata-only 归档不得复制基础帧或丢弃候选"
        meta = json.loads((archive_root / "extraction_meta.json").read_text(encoding="utf-8"))
        assert meta["archive_validation"] == {
            "mode": "metadata_only",
            "report_copied": True,
            "frame_count_in_report": len(report["frames"]),
        }
        assert meta["review"]["drop_candidates_archived"] is False


def _test_evidence_signals() -> None:
    taxonomy = _load_taxonomy(ROOT.parent / "config" / "evidence-lead-taxonomy.json")
    samples = {
        "identity_qualification": "营业执照 统一社会信用代码 91110101ABCDEFGH12 法定代表人",
        "product_work_service": "商品详情 立即购买 ￥3680",
        "transaction_performance": "订单 支付 退款 物流",
        "communication_commitment": "聊天记录 私信 承诺 确认",
        "publicity_representation": "广告 宣传 正品 材质",
        "review_feedback_dispute": "评论 投诉 差评 质量问题",
        "reach_metric_timeline": "点赞 收藏 分享 粉丝",
        "document_record": "合同 协议 凭证 编号：ABC-1234",
    }
    for category_id, sample in samples.items():
        findings = classify_evidence_text(sample, taxonomy)
        assert any(item["category_id"] == category_id for item in findings), (category_id, findings)
    serialized_identity = json.dumps(classify_evidence_text(samples["identity_qualification"], taxonomy), ensure_ascii=False)
    assert "91110101ABCDEFGH12" not in serialized_identity, serialized_identity
    assert classify_evidence_text("商品", taxonomy) == [], "单个宽泛关键词不得触发证据类别"
    assert classify_evidence_text("", taxonomy) == []

    blank = Image.new("RGB", (180, 320), "white")
    blank_signal, blank_thumb = visual_content_signals(_image_bytes(blank), None)
    assert blank_signal["text_independent_content"] is False, blank_signal
    rich = _pattern(180, 320).convert("RGB")
    rich_signal, _ = visual_content_signals(_image_bytes(rich), blank_thumb)
    assert rich_signal["text_independent_content"] is True, rich_signal


def _prepare_evidence_fixture(root: Path, *, max_leads: int = 4) -> tuple[Path, dict[str, str]]:
    _write_fixture(root)
    frame_hashes = {path.name: _sha(path) for path in root.glob("frame_*.jpg")}
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "prepare_evidence_leads.py"),
            "-i",
            str(root),
            "--no-ocr",
            "--max-leads",
            str(max_leads),
            "--max-sheets",
            "2",
            "--columns",
            "2",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return root / "_evidence_leads", frame_hashes


def _test_evidence_package() -> None:
    with tempfile.TemporaryDirectory(prefix="video-screenshot-evidence-") as tmp:
        root = Path(tmp)
        evidence_dir, frame_hashes = _prepare_evidence_fixture(root)
        index_path = evidence_dir / "evidence_index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index["purpose"] == "ranking_only_non_destructive_evidence_leads"
        assert index["privacy"] == {"ocr_text_stored": False, "entity_text_stored": False}
        assert index["vision_contract"]["may_delete_base_frames"] is False
        selected = [item for item in index["leads"] if item["selected_for_contact_sheet"]]
        assert 1 <= len(selected) <= 4, selected
        assert sorted(item["selection_rank"] for item in selected) == list(range(1, len(selected) + 1))
        assert len(list(evidence_dir.glob("evidence_sheet_*.jpg"))) == index["budget"]["actual_sheets"]
        serialized = index_path.read_text(encoding="utf-8")
        assert "ocr_text\"" not in serialized and "entity_text\"" not in serialized
        assert all(_sha(root / filename) == digest for filename, digest in frame_hashes.items())
        template_path = evidence_dir / "vision_template.json"
        template = json.loads(template_path.read_text(encoding="utf-8"))
        template["answers"][0]["categories"] = ["uncertain"]
        template_path.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        rebuild = subprocess.run(
            [sys.executable, str(ROOT / "prepare_evidence_leads.py"), "-i", str(root), "--no-ocr"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert rebuild.returncode == 2 and "已填写" in rebuild.stderr, rebuild.stdout + rebuild.stderr
        assert json.loads(template_path.read_text(encoding="utf-8"))["answers"][0]["categories"] == ["uncertain"]


def _complete_evidence_template(evidence_dir: Path, *, overclaim: bool = False) -> Path:
    template_path = evidence_dir / "vision_template.json"
    template = json.loads(template_path.read_text(encoding="utf-8"))
    template["status"] = "completed"
    for answer in template["answers"]:
        answer["categories"] = ["uncertain"]
        answer["visible_fact_summary"] = "画面中存在可见内容，具体对象需人工核对"
        answer["potential_use"] = "足以证明相关法律事实" if overclaim else "可能用于定位后续人工复核范围"
        answer["confidence"] = 0.65
    review_path = evidence_dir.parent / ("bad_evidence_review.json" if overclaim else "evidence_review_input.json")
    review_path.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return review_path


def _write_sensitive_evidence_review(evidence_dir: Path) -> Path:
    review_path = _complete_evidence_template(evidence_dir)
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["answers"][0]["visible_fact_summary"] = "画面显示商品价格￥3680"
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return review_path


def _test_evidence_review() -> None:
    with tempfile.TemporaryDirectory(prefix="video-screenshot-evidence-") as tmp:
        root = Path(tmp)
        evidence_dir, frame_hashes = _prepare_evidence_fixture(root)
        review_path = _complete_evidence_template(evidence_dir)
        result = subprocess.run(
            [sys.executable, str(ROOT / "apply_evidence_review.py"), "-i", str(root), "-r", str(review_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        applied = json.loads((evidence_dir / "evidence_review.json").read_text(encoding="utf-8"))
        assert applied["operation"] == "classify_and_summarize_only"
        assert applied["base_frames_modified"] is False
        assert all(_sha(root / filename) == digest for filename, digest in frame_hashes.items())


def _run_evidence_review_boundary_fault() -> tuple[int, str, bool]:
    with tempfile.TemporaryDirectory(prefix="video-screenshot-evidence-") as tmp:
        root = Path(tmp)
        evidence_dir, _frame_hashes = _prepare_evidence_fixture(root)
        review_path = _complete_evidence_template(evidence_dir, overclaim=True)
        result = subprocess.run(
            [sys.executable, str(ROOT / "apply_evidence_review.py"), "-i", str(root), "-r", str(review_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode, result.stdout + result.stderr, (evidence_dir / "evidence_review.json").exists()


def _test_evidence_review_boundary() -> None:
    returncode, output, result_exists = _run_evidence_review_boundary_fault()
    assert returncode == 2, output
    assert not result_exists, "越过法律判断边界的答案不得生成复核结果"
    with tempfile.TemporaryDirectory(prefix="video-screenshot-evidence-") as tmp:
        root = Path(tmp)
        evidence_dir, _frame_hashes = _prepare_evidence_fixture(root)
        review_path = _write_sensitive_evidence_review(evidence_dir)
        result = subprocess.run(
            [sys.executable, str(ROOT / "apply_evidence_review.py"), "-i", str(root), "-r", str(review_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 2 and "泛化概括" in result.stderr, result.stdout + result.stderr
        assert not (evidence_dir / "evidence_review.json").exists()


def main() -> int:
    args = parse_args()
    if args.case == "fault-invalid-review":
        returncode, output, curated_exists = _run_invalid_review_fault()
        if output.strip():
            print(output.strip(), file=sys.stderr if returncode else sys.stdout)
        if curated_exists:
            print("FAULT_CONTRACT_BROKEN: 错误审计产生了精选目录", file=sys.stderr)
            return 1
        return returncode
    if args.case == "fault-evidence-review-boundary":
        returncode, output, result_exists = _run_evidence_review_boundary_fault()
        if output.strip():
            print(output.strip(), file=sys.stderr if returncode else sys.stdout)
        if result_exists:
            print("FAULT_CONTRACT_BROKEN: 越界答案产生了证据复核结果", file=sys.stderr)
            return 1
        return returncode

    tests = {
        "temporal": _test_temporal,
        "mixed-transition": _test_mixed_transition,
        "content-delta": _test_content_delta,
        "transient-ui": _test_transient_ui,
        "temporal-completion": _test_temporal_completion,
        "adaptive-density": _test_adaptive_density,
        "vision-budget": _test_vision_budget,
        "vision-diversity": _test_vision_diversity,
        "weak-vision-package": _test_weak_vision_package,
        "weak-review-gate": _test_weak_review_gate,
        "weak-membership": _test_weak_repeated_image_group_membership,
        "valid-review": _test_valid_review,
        "replace-review": _test_replace_review,
        "coverage-survival": _test_coverage_survival,
        "invalid-review": _test_invalid_review,
        "output-protection": _test_output_protection,
        "transactional-output": _test_transactional_output,
        "archive-metadata": _test_archive_metadata_only,
        "evidence-signals": _test_evidence_signals,
        "evidence-package": _test_evidence_package,
        "evidence-review": _test_evidence_review,
        "evidence-review-boundary": _test_evidence_review_boundary,
    }
    selected = tests.items() if args.case == "all" else [(args.case, tests[args.case])]
    try:
        for name, test in selected:
            test()
            print(f"PASS {name}")
        print("DOMAIN_CHECKS_PASSED")
        return 0
    except Exception as exc:
        print(f"FAIL {args.case}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
