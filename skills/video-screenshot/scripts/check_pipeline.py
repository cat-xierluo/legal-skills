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

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract import _clean_output_dir, _record_drop_candidate
from lib import (
    calc_loading_overlay_score,
    horizontal_mixed_transition_score,
    ocr_content_delta,
    ocr_extract_text,
    select_temporal_representatives,
    transient_ui_drop_reason,
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
            "adaptive-density",
            "vision-budget",
            "vision-diversity",
            "valid-review",
            "replace-review",
            "invalid-review",
            "output-protection",
            "fault-invalid-review",
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
        # 把 12 张合成帧拉开到 0—330 秒，制造多个风险相近的时间桶。
        for idx, frame in enumerate(report["frames"]):
            frame["capture_time_seconds"] = float(idx * 30)
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
        target = next(item for item in manifest["images"] if item["source"] == "kept")
        review_path = root / "_vision_review.json"
        review_path.write_text(
            json.dumps({
                "schema_version": "1.0",
                "status": "completed",
                "source_manifest_sha256": _sha(manifest_path),
                "decisions": [{
                    "audit_id": target["audit_id"],
                    "decision": "drop",
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
        kept = [item for item in manifest["images"] if item["source"] == "kept"]
        assert len(kept) >= 2
        review_path = root / "_vision_review.json"
        review_path.write_text(
            json.dumps({
                "schema_version": "1.0",
                "status": "completed",
                "source_manifest_sha256": _sha(manifest_path),
                "decisions": [{
                    "audit_id": kept[0]["audit_id"],
                    "decision": "replace",
                    "replacement_audit_id": kept[1]["audit_id"],
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


def _test_output_protection() -> None:
    with tempfile.TemporaryDirectory(prefix="video-screenshot-check-") as tmp:
        root = Path(tmp)
        review = root / "_vision_review.json"
        review.write_text("{}\n", encoding="utf-8")
        try:
            _clean_output_dir(str(root))
        except RuntimeError as exc:
            assert "拒绝自动删除" in str(exc)
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

    tests = {
        "temporal": _test_temporal,
        "mixed-transition": _test_mixed_transition,
        "content-delta": _test_content_delta,
        "transient-ui": _test_transient_ui,
        "adaptive-density": _test_adaptive_density,
        "vision-budget": _test_vision_budget,
        "vision-diversity": _test_vision_diversity,
        "valid-review": _test_valid_review,
        "replace-review": _test_replace_review,
        "invalid-review": _test_invalid_review,
        "output-protection": _test_output_protection,
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
