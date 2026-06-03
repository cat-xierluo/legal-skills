#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "Pillow>=10.0.0",
#   "rapidocr-onnxruntime",
# ]
# ///

"""video-screenshot 视频截图提取工具。

从录屏视频中抽取关键帧、去重并保存为图片文件。
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime
from hashlib import sha256
from pathlib import Path

# 将 scripts/ 同级目录加入搜索路径以便导入 lib
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import (
    DedupState,
    ExtractParams,
    FFProbeInfo,
    calc_blur_score,
    calc_capture_time,
    calc_content_quality,
    calc_dhash_hex,
    calc_scroll_image,
    calc_thumb_bytes,
    check_ocr_similarity,
    collect_frame_files,
    create_ocr_engine,
    crop_for_ocr_bytes_with_range,
    find_tool,
    is_frame_duplicate,
    ocr_extract_text,
    probe_video,
    run_ffmpeg_extract,
    shingles,
)

logger = logging.getLogger("video-screenshot")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="视频取证关键帧提取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
示例:
  # 场景检测 + 图像去重（默认）
  uv run scripts/extract.py -i recording.mp4

  # 固定间隔，每 0.5 秒一帧
  uv run scripts/extract.py -i recording.mp4 -s interval --interval 0.5

  # 场景检测 + OCR 去重（适合聊天录屏）
  uv run scripts/extract.py -i recording.mp4 --ocr-dedup

  # 关键帧提取，不去重
  uv run scripts/extract.py -i recording.mp4 -s keyframe -d 0
""",
    )
    p.add_argument("-i", "--input", required=True, help="输入视频文件路径")
    p.add_argument("-o", "--output", default=None, help="输出目录（默认: <视频名>_frames/）")
    p.add_argument("-s", "--strategy", default="scene",
                   choices=["scene", "keyframe", "interval", "smart"],
                   help="抽帧策略（默认: scene）")
    p.add_argument("--interval", type=float, default=1.0, help="间隔秒数（interval 模式，默认: 1.0）")
    p.add_argument("--scene-threshold", type=float, default=0.10, help="场景变化阈值（scene 模式，默认: 0.10）")
    p.add_argument("--sample-interval", type=float, default=2.0, help="定期采样间隔秒数（scene 模式保底，默认: 2.0，0=禁用）")
    p.add_argument("-d", "--dedup-threshold", type=int, default=4, help="dHash 汉明距离阈值（0=禁用，默认: 4）")
    p.add_argument("--content-crop-top", type=float, default=0.12, help="内容区顶部裁剪比例（默认: 0.12）")
    p.add_argument("--content-crop-bottom", type=float, default=0.12, help="内容区底部裁剪比例（默认: 0.12）")
    p.add_argument("--content-crop-left", type=float, default=0.04, help="内容区左侧裁剪比例（默认: 0.04）")
    p.add_argument("--content-crop-right", type=float, default=0.04, help="内容区右侧裁剪比例（默认: 0.04）")
    p.add_argument("--ssim-threshold", type=float, default=0.93, help="SSIM 结构相似度阈值（0=禁用，默认: 0.93）")
    p.add_argument("--scroll-merge", action="store_true", default=False, help="滚动帧合并（默认关闭）")
    p.add_argument("--no-scroll-merge", action="store_false", dest="scroll_merge", help="禁用滚动帧合并")
    p.add_argument("--scroll-diff-threshold", type=float, default=32.0, help="滚动重叠平均像素差阈值（默认: 32.0）")
    p.add_argument("--ocr-dedup", action="store_true", help="启用 OCR 文本去重")
    p.add_argument("--ocr-threshold", type=float, default=0.92, help="OCR 相似度阈值（默认: 0.92）")
    p.add_argument("--ocr-min-new", type=int, default=8, help="OCR 最少新字符数（默认: 8）")
    p.add_argument("--max-size", type=int, default=0, help="输出最长边像素限制（0=保持原始分辨率，默认: 0）")
    p.add_argument("-q", "--quality", type=int, default=2, help="JPEG 输出质量 1-31，越小越清晰（默认: 2）")
    p.add_argument("--timeout", type=float, default=1800, help="超时秒数（默认: 1800）")
    p.add_argument("--filter-blur", action="store_true", help="启用模糊帧过滤")
    p.add_argument("--blur-threshold", type=float, default=50.0, help="模糊阈值，Laplacian 方差低于此值视为模糊（默认: 50.0）")
    p.add_argument("--filter-quality", action="store_true", default=True, help="内容质量过滤（默认开启，过滤空白页、启动画面、过渡帧）")
    p.add_argument("--no-filter-quality", action="store_false", dest="filter_quality", help="禁用内容质量过滤")
    p.add_argument("--min-gap", type=float, default=0.5, help="保留帧之间的最小时间间隔秒数（默认: 0.5）")
    p.add_argument(
        "--keep-drop-candidates",
        action="store_true",
        help="保存被去重或过滤丢弃的候选帧，供多模态复核",
    )
    p.add_argument(
        "--drop-candidate-limit",
        type=int,
        default=200,
        help="最多保存多少张丢弃候选帧（默认: 200，0=不限）",
    )
    p.add_argument("--keep-temp", action="store_true", help="保留临时 ffmpeg 输出文件")
    return p.parse_args(argv)


def format_timestamp(seconds: float | None) -> str:
    if seconds is None:
        return "00m00s"
    total = int(max(0, seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:02d}h{m:02d}m{s:02d}s"
    return f"{m:02d}m{s:02d}s"


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    args = parse_args()

    # 验证输入
    video_path = str(Path(args.input).resolve())
    if not Path(video_path).exists():
        print(f"错误: 视频文件不存在: {video_path}", file=sys.stderr)
        sys.exit(1)

    # 验证 ffmpeg
    if not find_tool("ffmpeg"):
        print("错误: 未检测到 ffmpeg，请先安装: brew install ffmpeg", file=sys.stderr)
        sys.exit(1)

    # 确定输出目录（默认在视频文件同级目录下）
    video_stem = Path(video_path).stem
    output_dir = args.output or str(Path(video_path).parent / f"{video_stem}_frames")
    output_dir = str(Path(output_dir).resolve())
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    cleanup_stats = _clean_output_dir(output_dir)
    if cleanup_stats["stale_deleted_count"]:
        print(f"  已清理旧输出文件: {cleanup_stats['stale_deleted_count']}")

    # 探测视频
    print(f"探测视频: {video_path}")
    try:
        info = probe_video(video_path)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"  时长: {info.duration_seconds:.1f}s")

    # 参数
    params = ExtractParams(
        interval_seconds=args.interval,
        strategy=args.strategy,
        dedup_threshold=args.dedup_threshold,
        ocr_similarity_threshold=args.ocr_threshold,
        ocr_min_new_chars=args.ocr_min_new,
        content_crop_top=args.content_crop_top,
        content_crop_bottom=args.content_crop_bottom,
        content_crop_left=args.content_crop_left,
        content_crop_right=args.content_crop_right,
        ssim_threshold=args.ssim_threshold,
        scroll_merge=args.scroll_merge,
        scroll_diff_threshold=args.scroll_diff_threshold,
    )

    # OCR 引擎
    ocr_engine = None
    if args.ocr_dedup:
        ocr_engine = create_ocr_engine()
        if ocr_engine is None:
            print("警告: RapidOCR 未安装，OCR 去重已禁用。安装: pip install rapidocr-onnxruntime", file=sys.stderr)
            args.ocr_dedup = False
        else:
            print("  OCR: RapidOCR (本地)（SSIM 去重已自动禁用）")
            params.ssim_threshold = 0

    # 创建临时目录
    started_at = time.monotonic()
    tmpdir = tempfile.mkdtemp(prefix="video-screenshot-")
    try:
        # FFmpeg 抽帧
        interval_based = params.strategy == "interval"
        output_pattern = str(
            Path(tmpdir) / ("frame_%06d.jpg" if interval_based else "frame_%010d.jpg")
        )
        print(f"抽帧中 (策略: {params.strategy})...")
        ffmpeg_timeout = max(30.0, args.timeout - 5.0)

        for kv in run_ffmpeg_extract(
            video_path=video_path,
            output_pattern=output_pattern,
            strategy=params.strategy,
            interval_seconds=params.interval_seconds,
            scene_threshold=args.scene_threshold,
            max_size=args.max_size,
            quality=args.quality,
            timeout_seconds=ffmpeg_timeout,
            frame_rate_fps=info.frame_rate_fps,
            sample_interval=args.sample_interval,
        ):
            if "out_time_ms" in kv:
                try:
                    out_us = int(kv["out_time_ms"])
                    out_s = out_us / 1_000_000.0
                    pct = int(out_s * 100 / info.duration_seconds) if info.duration_seconds else 0
                    pct = min(max(pct, 0), 99)
                    print(f"\r  进度: {pct}% ({out_s:.1f}s/{info.duration_seconds:.1f}s)", end="", flush=True)
                except Exception:
                    pass
        print()  # 换行

        # 收集帧文件
        frame_files = collect_frame_files(tmpdir)
        total_extracted = len(frame_files)
        print(f"提取帧数: {total_extracted}")

        if not frame_files:
            print("警告: 未提取到任何帧", file=sys.stderr)
            _write_report(
                output_dir, video_path, info, params, 0, DedupState(), [], cleanup_stats,
                [], args.keep_drop_candidates, args.drop_candidate_limit,
            )
            return

        # 去重
        state = DedupState()
        window = 20
        pixel_diff_threshold = 8.0
        frames_meta: list[dict] = []
        drop_candidates_meta: list[dict] = []
        last_kept_time: float | None = None

        print("去重中...")
        for idx, frame_path in enumerate(frame_files, 1):
            state.total_count += 1

            with open(frame_path, "rb") as fp:
                content = fp.read()

            digest = sha256(content).hexdigest()
            dhash_hex = calc_dhash_hex(
                content,
                crop_top_ratio=params.content_crop_top,
                crop_bottom_ratio=params.content_crop_bottom,
                crop_left_ratio=params.content_crop_left,
                crop_right_ratio=params.content_crop_right,
            )

            capture_time = calc_capture_time(frame_path, idx, params, info)

            # 图像去重
            is_dup, drop_reason, thumb, ssim_thumb, scroll_image = is_frame_duplicate(
                content, digest, dhash_hex, state, params, window, pixel_diff_threshold,
            )
            if is_dup:
                _record_drop_candidate(
                    output_dir,
                    frame_path,
                    idx,
                    drop_reason,
                    capture_time,
                    digest,
                    drop_candidates_meta,
                    enabled=args.keep_drop_candidates,
                    limit=args.drop_candidate_limit,
                )
                continue

            # 最小时间间隔过滤
            if args.min_gap > 0 and last_kept_time is not None and capture_time is not None:
                if capture_time - last_kept_time < args.min_gap:
                    state.min_gap_drops += 1
                    _record_drop_candidate(
                        output_dir,
                        frame_path,
                        idx,
                        "min_gap",
                        capture_time,
                        digest,
                        drop_candidates_meta,
                        enabled=args.keep_drop_candidates,
                        limit=args.drop_candidate_limit,
                    )
                    continue

            # 内容质量过滤（空白页、启动画面、过渡帧）
            if args.filter_quality:
                quality = calc_content_quality(content)
                if quality["label"]:
                    state.quality_drops += 1
                    _record_drop_candidate(
                        output_dir,
                        frame_path,
                        idx,
                        f"quality_{quality['label']}",
                        capture_time,
                        digest,
                        drop_candidates_meta,
                        enabled=args.keep_drop_candidates,
                        limit=args.drop_candidate_limit,
                        extra={"quality": quality},
                    )
                    continue

            # 模糊帧过滤
            if args.filter_blur:
                blur_score = calc_blur_score(content)
                if blur_score < args.blur_threshold:
                    state.blur_drops += 1
                    _record_drop_candidate(
                        output_dir,
                        frame_path,
                        idx,
                        "blur",
                        capture_time,
                        digest,
                        drop_candidates_meta,
                        enabled=args.keep_drop_candidates,
                        limit=args.drop_candidate_limit,
                        extra={"blur_score": blur_score},
                    )
                    continue

            # OCR 去重
            if args.ocr_dedup and ocr_engine is not None:
                crop_bytes, crop_range = crop_for_ocr_bytes_with_range(content)
                ocr_text = ""
                if crop_bytes and crop_range >= 18:
                    ocr_text = ocr_extract_text(ocr_engine, crop_bytes)
                    ocr_text = re.sub(r"\s+", "", ocr_text or "")
                    ocr_text = re.sub(r"[^\w一-鿿]+", "", ocr_text)

                if ocr_text and check_ocr_similarity(
                    ocr_text,
                    state.kept_ocr_texts,
                    state.kept_ocr_shingles,
                    params.ocr_similarity_threshold,
                    params.ocr_min_new_chars,
                ):
                    state.ocr_dups += 1
                    _record_drop_candidate(
                        output_dir,
                        frame_path,
                        idx,
                        "ocr_duplicate",
                        capture_time,
                        digest,
                        drop_candidates_meta,
                        enabled=args.keep_drop_candidates,
                        limit=args.drop_candidate_limit,
                    )
                    continue
            else:
                ocr_text = ""

            # 保留帧
            state.kept_count += 1
            state.seen_sha256.add(digest)
            if dhash_hex:
                state.kept_dhashes.append(dhash_hex)
            if not thumb:
                thumb = calc_thumb_bytes(
                    content,
                    crop_top_ratio=params.content_crop_top,
                    crop_bottom_ratio=params.content_crop_bottom,
                    crop_left_ratio=params.content_crop_left,
                    crop_right_ratio=params.content_crop_right,
                )
            if thumb:
                state.kept_thumbs.append(thumb)
            if not ssim_thumb and params.ssim_threshold and params.ssim_threshold > 0:
                ssim_thumb = calc_thumb_bytes(
                    content,
                    size=32,
                    crop_top_ratio=params.content_crop_top,
                    crop_bottom_ratio=params.content_crop_bottom,
                    crop_left_ratio=params.content_crop_left,
                    crop_right_ratio=params.content_crop_right,
                    autocontrast=True,
                )
            if ssim_thumb:
                state.kept_ssim_thumbs.append(ssim_thumb)
            if not scroll_image and params.scroll_merge:
                scroll_image = calc_scroll_image(
                    content,
                    crop_top_ratio=params.content_crop_top,
                    crop_bottom_ratio=params.content_crop_bottom,
                    crop_left_ratio=params.content_crop_left,
                    crop_right_ratio=params.content_crop_right,
                )
            if scroll_image:
                state.kept_scroll_images.append(scroll_image)
            if ocr_text:
                state.kept_ocr_texts.append(ocr_text)
                state.kept_ocr_shingles.append(shingles(ocr_text))

            # 复制到输出目录
            ts = format_timestamp(capture_time)
            out_name = f"frame_{state.kept_count:03d}_{ts}.jpg"
            out_path = str(Path(output_dir) / out_name)
            shutil.copy2(frame_path, out_path)
            last_kept_time = capture_time

            frames_meta.append({
                "index": state.kept_count,
                "filename": out_name,
                "capture_time_seconds": capture_time,
                "sha256": digest,
            })

            if idx % 50 == 0 or idx == total_extracted:
                print(
                    f"\r  已处理: {idx}/{total_extracted}, "
                    f"保留: {state.kept_count}, "
                    f"去重: {idx - state.kept_count}",
                    end="", flush=True,
                )
        print()  # 换行

        # 写入报告
        _write_report(
            output_dir, video_path, info, params, total_extracted, state, frames_meta, cleanup_stats,
            drop_candidates_meta, args.keep_drop_candidates, args.drop_candidate_limit,
        )

        # 归档
        archive_dir = _archive_result(
            output_dir, video_path, info, params, args, state, frames_meta, cleanup_stats,
            drop_candidates_meta,
            elapsed_seconds=time.monotonic() - started_at,
        )

        # 汇总
        print(f"\n完成!")
        print(f"  输出目录: {output_dir}")
        print(f"  提取帧: {total_extracted}")
        print(f"  保留帧: {state.kept_count}")
        print(f"  去重统计:")
        print(f"    SHA256 重复: {state.sha256_dups}")
        print(f"    dHash 重复:  {state.dhash_dups}")
        print(f"    像素重复:    {state.pixel_dups}")
        print(f"    SSIM 重复:    {state.ssim_dups}")
        print(f"    滚动合并:    {state.scroll_dups}")
        print(f"    OCR 重复:    {state.ocr_dups}")
        if state.blur_drops:
            print(f"    模糊过滤:    {state.blur_drops}")
        if state.quality_drops:
            print(f"    质量过滤:    {state.quality_drops}")
        if state.min_gap_drops:
            print(f"    时间间隔过滤: {state.min_gap_drops}")
        if args.keep_drop_candidates:
            print(f"  复核候选帧: {len(drop_candidates_meta)}")
        if archive_dir:
            print(f"  归档: {archive_dir}")

    finally:
        if not args.keep_temp:
            shutil.rmtree(tmpdir, ignore_errors=True)
        else:
            print(f"  临时文件: {tmpdir}")


def _clean_output_dir(output_dir: str) -> dict[str, object]:
    """清理本工具生成的旧输出文件，避免本次结果混入残留帧。"""
    root = Path(output_dir)
    stale_files: list[Path] = []
    stale_files.extend(root.glob("frame_*.jpg"))
    stale_files.extend(root.glob("frame_*.jpeg"))
    for name in ("_report.json", "extraction_meta.json"):
        p = root / name
        if p.exists() and p.is_file():
            stale_files.append(p)

    stale_dirs: list[Path] = []
    candidates_dir = root / "_review_candidates"
    if candidates_dir.exists() and candidates_dir.is_dir():
        stale_dirs.append(candidates_dir)

    deleted: list[str] = []
    seen: set[Path] = set()
    for p in stale_files:
        if p in seen or not p.is_file():
            continue
        seen.add(p)
        p.unlink()
        deleted.append(p.name)
    for p in stale_dirs:
        shutil.rmtree(p, ignore_errors=True)
        deleted.append(p.name + "/")

    return {
        "stale_deleted_count": len(deleted),
        "stale_deleted_files": deleted,
    }


def _record_drop_candidate(
    output_dir: str,
    frame_path: str,
    source_index: int,
    reason: str,
    capture_time: float | None,
    digest: str,
    candidates: list[dict],
    *,
    enabled: bool,
    limit: int,
    extra: dict[str, object] | None = None,
) -> None:
    """保存被算法丢弃的候选帧，供后续视觉复核。"""
    if not enabled:
        return
    if limit > 0 and len(candidates) >= limit:
        return

    candidates_dir = Path(output_dir) / "_review_candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    safe_reason = re.sub(r"[^a-z0-9_]+", "_", (reason or "drop").lower()).strip("_") or "drop"
    seq = len(candidates) + 1
    filename = f"candidate_{seq:03d}_{safe_reason}_{format_timestamp(capture_time)}.jpg"
    dst = candidates_dir / filename
    shutil.copy2(frame_path, dst)

    item: dict[str, object] = {
        "index": seq,
        "filename": str(Path("_review_candidates") / filename),
        "source_frame_index": source_index,
        "source_temp_filename": Path(frame_path).name,
        "reason": reason,
        "capture_time_seconds": capture_time,
        "sha256": digest,
    }
    if extra:
        item.update(extra)
    candidates.append(item)


def _write_report(
    output_dir: str,
    video_path: str,
    info: FFProbeInfo,
    params: ExtractParams,
    total_extracted: int,
    state: DedupState,
    frames: list[dict],
    cleanup_stats: dict[str, object],
    drop_candidates: list[dict],
    keep_drop_candidates: bool,
    drop_candidate_limit: int,
) -> None:
    report = {
        "input": video_path,
        "duration_seconds": info.duration_seconds,
        "strategy": params.strategy,
        "options": {
            "interval_seconds": params.interval_seconds,
            "dedup_threshold": params.dedup_threshold,
            "ocr_similarity_threshold": params.ocr_similarity_threshold,
            "ocr_min_new_chars": params.ocr_min_new_chars,
            "content_crop": {
                "top": params.content_crop_top,
                "bottom": params.content_crop_bottom,
                "left": params.content_crop_left,
                "right": params.content_crop_right,
            },
            "ssim_threshold": params.ssim_threshold,
            "scroll_merge": params.scroll_merge,
            "scroll_diff_threshold": params.scroll_diff_threshold,
        },
        "total_extracted": total_extracted,
        "kept_after_dedup": state.kept_count,
        "cleanup": cleanup_stats,
        "review": {
            "drop_candidates_enabled": keep_drop_candidates,
            "drop_candidate_limit": drop_candidate_limit,
            "drop_candidate_count": len(drop_candidates),
            "drop_candidates": drop_candidates,
            "vision_review_status": "not_run",
            "vision_review_note": "脚本只导出复核候选帧；是否执行多模态复核由当前模型能力决定。",
        },
        "dedup_stats": {
            "sha256_duplicates": state.sha256_dups,
            "dhash_duplicates": state.dhash_dups,
            "pixel_duplicates": state.pixel_dups,
            "ssim_duplicates": state.ssim_dups,
            "scroll_duplicates": state.scroll_dups,
            "ocr_duplicates": state.ocr_dups,
            "blur_drops": state.blur_drops,
            "quality_drops": state.quality_drops,
            "min_gap_drops": state.min_gap_drops,
        },
        "frames": frames,
    }
    report_path = str(Path(output_dir) / "_report.json")
    with open(report_path, "w", encoding="utf-8") as fp:
        json.dump(report, fp, ensure_ascii=False, indent=2)


def _build_archive_subdir(video_path: str) -> Path:
    """创建 archive 子目录，命名格式: YYYYMMDD_HHMMSS_{视频名}"""
    skill_root = Path(__file__).resolve().parent.parent
    archive_root = skill_root / "archive"
    video_stem = Path(video_path).stem
    # 截断过长的文件名
    if len(video_stem) > 60:
        video_stem = video_stem[:60]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir = archive_root / f"{ts}_{video_stem}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    return archive_dir


def _archive_result(
    output_dir: str,
    video_path: str,
    info: FFProbeInfo,
    params: ExtractParams,
    args: argparse.Namespace,
    state: DedupState,
    frames_meta: list[dict],
    cleanup_stats: dict[str, object],
    drop_candidates: list[dict],
    elapsed_seconds: float,
) -> Path | None:
    """将分析结果归档到 archive/ 目录。"""
    archive_dir = _build_archive_subdir(video_path)

    frames_dir = archive_dir / "frames"
    frames_dir.mkdir(exist_ok=True)
    expected_names = [str(frame["filename"]) for frame in frames_meta]
    for name in expected_names:
        src = Path(output_dir) / name
        if not src.exists():
            raise FileNotFoundError(f"归档失败，报告帧不存在: {src}")
        shutil.copy2(src, frames_dir / name)

    report_src = Path(output_dir) / "_report.json"
    if not report_src.exists():
        raise FileNotFoundError(f"归档失败，报告文件不存在: {report_src}")
    shutil.copy2(report_src, archive_dir / "_report.json")

    actual_names = sorted(p.name for p in frames_dir.glob("*.jpg"))
    expected_sorted = sorted(expected_names)
    if actual_names != expected_sorted:
        extra = sorted(set(actual_names) - set(expected_sorted))
        missing = sorted(set(expected_sorted) - set(actual_names))
        raise RuntimeError(
            "归档一致性校验失败: "
            f"expected={len(expected_sorted)}, actual={len(actual_names)}, "
            f"extra={extra[:5]}, missing={missing[:5]}"
        )

    review_dir = archive_dir / "_review_candidates"
    if drop_candidates:
        review_dir.mkdir(exist_ok=True)
        for item in drop_candidates:
            rel_name = str(item.get("filename") or "")
            src = Path(output_dir) / rel_name
            if src.exists() and src.is_file():
                shutil.copy2(src, review_dir / src.name)

    meta = {
        "source_file": video_path,
        "archive_path": str(archive_dir),
        "timestamp": datetime.now().isoformat(),
        "elapsed_seconds": round(elapsed_seconds, 1),
        "video_info": {
            "duration_seconds": info.duration_seconds,
            "time_base_seconds": info.time_base_seconds,
            "frame_rate_fps": info.frame_rate_fps,
        },
        "options": {
            "strategy": params.strategy,
            "interval_seconds": params.interval_seconds,
            "scene_threshold": args.scene_threshold,
            "dedup_threshold": params.dedup_threshold,
            "content_crop": {
                "top": params.content_crop_top,
                "bottom": params.content_crop_bottom,
                "left": params.content_crop_left,
                "right": params.content_crop_right,
            },
            "ssim_threshold": params.ssim_threshold,
            "scroll_merge": params.scroll_merge,
            "scroll_diff_threshold": params.scroll_diff_threshold,
            "ocr_dedup": args.ocr_dedup,
            "ocr_similarity_threshold": params.ocr_similarity_threshold,
            "ocr_min_new_chars": params.ocr_min_new_chars,
            "max_size": args.max_size,
            "quality": args.quality,
            "filter_blur": args.filter_blur,
            "blur_threshold": args.blur_threshold,
            "filter_quality": args.filter_quality,
            "keep_drop_candidates": args.keep_drop_candidates,
            "drop_candidate_limit": args.drop_candidate_limit,
        },
        "cleanup": cleanup_stats,
        "archive_validation": {
            "frames_match_report": True,
            "expected_frame_count": len(expected_sorted),
            "actual_frame_count": len(actual_names),
        },
        "review": {
            "drop_candidate_count": len(drop_candidates),
            "drop_candidates_archived": bool(drop_candidates),
            "vision_review_status": "not_run",
        },
        "result": {
            "total_extracted": state.total_count,
            "kept_after_dedup": state.kept_count,
            "dedup_stats": {
                "sha256_duplicates": state.sha256_dups,
                "dhash_duplicates": state.dhash_dups,
                "pixel_duplicates": state.pixel_dups,
                "ssim_duplicates": state.ssim_dups,
                "scroll_duplicates": state.scroll_dups,
                "ocr_duplicates": state.ocr_dups,
                "blur_drops": state.blur_drops,
                "quality_drops": state.quality_drops,
                "min_gap_drops": state.min_gap_drops,
            },
        },
        "frame_count": state.kept_count,
    }
    with open(archive_dir / "extraction_meta.json", "w", encoding="utf-8") as fp:
        json.dump(meta, fp, ensure_ascii=False, indent=2)

    return archive_dir


if __name__ == "__main__":
    main()
