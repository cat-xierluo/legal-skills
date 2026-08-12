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

from extract import _clean_output_dir
from lib import horizontal_mixed_transition_score, select_temporal_representatives


ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="video-screenshot 回归检查")
    parser.add_argument(
        "--case",
        choices=[
            "all",
            "temporal",
            "mixed-transition",
            "vision-budget",
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
        "vision-budget": _test_vision_budget,
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
