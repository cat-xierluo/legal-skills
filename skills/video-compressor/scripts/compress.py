#!/usr/bin/env python3
"""视频压缩工具 — 使用 FFmpeg CRF 模式压缩视频，适配屏幕录制/课件场景。"""

import argparse
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from hw_detect import build_encode_args, detect_hardware, print_hardware_info, select_profile

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".ts"}


def human_size(size_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def compress_video(
    input_path: Path,
    encode_args: list[str],
    output_suffix: str,
) -> tuple[bool, str, int, int]:
    """压缩单个视频文件。返回 (成功?, 输出路径, 原始大小, 压缩后大小)。"""
    output_path = input_path.parent / f"{input_path.stem}{output_suffix}.mp4"

    original_size = input_path.stat().st_size

    cmd = [
        shutil.which("ffmpeg") or "ffmpeg",
        "-y",
        "-i", str(input_path),
    ] + encode_args + [
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        return False, result.stderr[:500], original_size, 0

    compressed_size = output_path.stat().st_size
    return True, str(output_path), original_size, compressed_size


def collect_videos(input_paths: list[Path]) -> list[Path]:
    """从多个路径（文件或目录）收集所有待压缩的视频文件。"""
    all_videos: list[Path] = []
    for input_path in input_paths:
        input_path = input_path.resolve()
        if input_path.is_file():
            if input_path.suffix.lower() in VIDEO_EXTENSIONS:
                all_videos.append(input_path)
            else:
                print(f"跳过不支持的格式: {input_path}")
        elif input_path.is_dir():
            files = sorted(
                f for f in input_path.rglob("*")
                if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS
                and "_compressed" not in f.stem
            )
            if not files:
                print(f"目录 {input_path} 中未找到视频文件")
            all_videos.extend(files)
        else:
            print(f"路径不存在: {input_path}")

    # 去重（可能多个路径包含相同文件）
    seen: set[Path] = set()
    unique: list[Path] = []
    for v in all_videos:
        if v not in seen:
            seen.add(v)
            unique.append(v)
    return unique


def main():
    parser = argparse.ArgumentParser(description="视频压缩工具")
    parser.add_argument("-i", "--input", nargs="+", required=True,
                        help="输入文件或目录路径（可指定多个）")
    parser.add_argument("--crf", type=int, default=23, help="CRF 质量值 (默认 23，越小质量越高)")
    parser.add_argument("--maxrate", default="2500k", help="最大码率限制 (默认 2500k)")
    parser.add_argument("--bufsize", default="2500k", help="VBV 缓冲区大小 (默认 2500k)")
    parser.add_argument("-a", "--audio-bitrate", default="96k", help="音频比特率 (默认 96k)")
    parser.add_argument("--preset", default="veryfast", help="编码预设 (默认 veryfast)")
    parser.add_argument("-j", "--workers", type=int, default=3,
                        help="并发压缩线程数 (默认 3)")
    parser.add_argument("--output-suffix", default="_compressed", help="输出文件后缀 (默认 _compressed)")
    parser.add_argument("--codec", default=None,
                        choices=["hevc_vt", "h264_vt", "x264", "x265", "x264_fast"],
                        help="编码器选择 (默认自动检测最优方案)")
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        print("错误：未找到 ffmpeg，请先安装: brew install ffmpeg")
        sys.exit(1)

    # 硬件检测与编码配置
    hw = detect_hardware()
    profile = select_profile(hw, user_codec=args.codec)
    encode_args = build_encode_args(
        profile,
        crf=args.crf if not profile["is_hardware"] else None,
        maxrate=args.maxrate if not profile["is_hardware"] else None,
        bufsize=args.bufsize if not profile["is_hardware"] else None,
        audio_bitrate=args.audio_bitrate,
        preset=args.preset if not profile["is_hardware"] else None,
    )
    print_hardware_info(hw, profile)
    print()

    videos = collect_videos([Path(p) for p in args.input])
    if not videos:
        print("未找到任何视频文件")
        sys.exit(0)

    # 自动优化并发数（用户未显式指定 -j 时使用 profile 推荐值）
    workers = min(args.workers, len(videos))
    print(f"找到 {len(videos)} 个视频文件，{workers} 线程并发压缩...\n")

    # results 按 index 存储，保证汇总报告按输入顺序输出
    results: dict[int, tuple[str, bool, int, int, str]] = {}

    def task(index: int, video: Path):
        ok, output, orig, comp = compress_video(
            video, encode_args, args.output_suffix,
        )
        return index, video, ok, output, orig, comp

    start_time = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(task, i, v): i for i, v in enumerate(videos)}
        done_count = 0
        for future in as_completed(futures):
            idx, video, ok, output, orig, comp = future.result()
            done_count += 1
            if ok:
                ratio = (1 - comp / orig) * 100 if orig > 0 else 0
                results[idx] = (video.name, True, orig, comp, output)
                print(f"[{done_count}/{len(videos)}] ✓ {video.name}  "
                      f"{human_size(orig)} → {human_size(comp)} ({ratio:.1f}%)")
            else:
                results[idx] = (video.name, False, orig, 0, output)
                print(f"[{done_count}/{len(videos)}] ✗ {video.name}  失败: {output}")

    # 汇总报告（按原始顺序）
    total_original = 0
    total_compressed = 0
    failed = 0

    print(f"\n{'─' * 60}")
    print(f"{'文件名':<30} {'原始大小':>10} {'压缩后':>10} {'压缩比':>8}")
    print(f"{'─' * 60}")
    for idx in sorted(results):
        name, ok, orig, comp, _ = results[idx]
        if ok:
            total_original += orig
            total_compressed += comp
            ratio = (1 - comp / orig) * 100 if orig > 0 else 0
            print(f"{name:<30} {human_size(orig):>10} {human_size(comp):>10} {ratio:>7.1f}%")
        else:
            failed += 1
            print(f"{name:<30} {'失败':>10}")
    print(f"{'─' * 60}")

    if total_original > 0:
        total_ratio = (1 - total_compressed / total_original) * 100
        print(f"{'合计':<30} {human_size(total_original):>10} {human_size(total_compressed):>10} {total_ratio:>7.1f}%")

    elapsed = time.monotonic() - start_time
    print(f"\n完成：{len(videos) - failed} 成功，{failed} 失败")
    print(f"耗时: {elapsed:.1f}s (编码器: {profile['display_name']})")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
