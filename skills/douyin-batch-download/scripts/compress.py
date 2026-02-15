#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音视频压缩脚本

使用 ffmpeg 对下载的视频进行压缩，支持：
- 单个视频压缩
- 指定用户目录压缩
- 全部下载目录压缩
- 默认直接替换原文件（节省空间）
- 可选保留原文件（使用 --keep）
- 智能跳过小文件（避免压缩后变大）

用法：
    python scripts/compress.py                          # 压缩全部视频
    python scripts/compress.py --user <uid>             # 压缩指定用户视频
    python scripts/compress.py --file <video.mp4>        # 压缩单个文件
    python scripts/compress.py --keep                    # 保留原文件
"""

import subprocess
import sys
import os
from pathlib import Path
import argparse

# 强制使用脚本所在目录作为工作目录
SKILL_DIR = Path(__file__).parent.parent.resolve()
os.chdir(SKILL_DIR)

DOWNLOADS_PATH = SKILL_DIR / "downloads"

# 小文件阈值（字节），小于此值的视频不压缩
# 原因：小视频压缩后可能变大（编码开销 > 压缩收益）
SMALL_FILE_THRESHOLD = 5 * 1024 * 1024  # 5MB

# 低分辨率阈值（高度），低于此值的视频跳过压缩
# 原因：激进模式会降低分辨率，对已低分辨率视频无意义
LOW_RESOLUTION_THRESHOLD = 720  # 720p 高度


def check_ffmpeg():
    """检查 ffmpeg 是否安装"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def get_video_info(video_path):
    """获取视频信息"""
    try:
        result = subprocess.run([
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            str(video_path)
        ], capture_output=True, text=True)

        if result.returncode == 0:
            import json
            info = json.loads(result.stdout)
            # 获取文件大小（字节）
            size = int(info["format"]["size"])
            # 获取时长（秒）
            duration = float(info["format"]["duration"])
            # 获取视频分辨率（高度）
            video_stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
            height = int(video_stream.get("height", 0)) if video_stream else 0
            return {"size": size, "duration": duration, "height": height}
    except Exception:
        pass
    return None


def format_size(bytes_size):
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} TB"


def compress_video(input_path, output_path, replace=True, crf=32, preset="fast", skip_small=True, aggressive=True):
    """
    压缩视频

    参数:
        input_path: 输入视频路径
        output_path: 输出视频路径
        replace: 是否替换原文件 (默认True，节省空间)
        crf: 压缩质量 (0-51, 越小质量越好, 默认32, 推荐28-38)
        preset: 压缩速度预设 (ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow)
        skip_small: 是否跳过小文件 (默认True)
        aggressive: 激进压缩模式 (默认False), 牺牲质量获得更高压缩率
    """
    info = get_video_info(input_path)
    original_size = info["size"] if info else 0
    height = info.get("height", 0) if info else 0

    print(f"  压缩: {input_path.name}")
    print(f"    原始大小: {format_size(original_size)}, 分辨率: {height}p")

    # 跳过小文件（避免压缩后反而变大）
    if skip_small and original_size < SMALL_FILE_THRESHOLD:
        print(f"    跳过 (文件小于 {format_size(SMALL_FILE_THRESHOLD)})")
        return None  # 返回 None 表示跳过

    # 跳过低分辨率视频（避免对已低分辨率视频进行压缩）
    if aggressive and height > 0 and height < LOW_RESOLUTION_THRESHOLD:
        print(f"    跳过 (分辨率 {height}p 已低于阈值 {LOW_RESOLUTION_THRESHOLD}p)")
        return None  # 返回 None 表示跳过

    # ffmpeg 命令
    if aggressive:
        # 激进模式：降低分辨率 + 降低音频码率
        cmd = [
            "ffmpeg", "-i", str(input_path),
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", preset,
            "-vf", "scale=iw/2:ih/2",  # 降低分辨率到一半
            "-c:a", "aac",
            "-b:a", "64k",  # 降低音频码率
            "-movflags", "+faststart",
            "-y",
            str(output_path)
        ]
    else:
        # 标准模式
        cmd = [
            "ffmpeg", "-i", str(input_path),
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", preset,
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            "-y",
            str(output_path)
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"    ✗ 压缩失败: {result.stderr}")
        return False

    # 获取压缩后大小
    compressed_info = get_video_info(output_path)
    compressed_size = compressed_info["size"] if compressed_info else 0

    # 计算压缩率
    if original_size > 0 and compressed_size > 0:
        ratio = (1 - compressed_size / original_size) * 100
        print(f"    压缩后: {format_size(compressed_size)} (压缩率: {ratio:.1f}%)")

    # 如果需要替换原文件
    if replace:
        input_path.unlink()
        output_path.rename(input_path)
        print(f"    已替换原文件")
    else:
        print(f"    输出: {output_path}")

    return True


def is_already_compressed(video_path):
    """检查视频是否已经是压缩版"""
    # 简单判断：文件名包含 compressed 或 compressed_ 前缀
    return "compressed" in video_path.stem.lower()


def compress_user_dir(user_dir, replace=True, skip_small=True, **kwargs):
    """压缩指定用户目录下的所有视频"""
    if not user_dir.exists():
        print(f"目录不存在: {user_dir}")
        return

    mp4_files = list(user_dir.glob("*.mp4"))
    if not mp4_files:
        print(f"没有找到视频文件: {user_dir}")
        return

    print(f"\n处理用户目录: {user_dir.name}")
    print(f"找到 {len(mp4_files)} 个视频文件\n")

    success_count = 0
    skipped_count = 0
    failed_count = 0

    for video in mp4_files:
        # 跳过已经是压缩版的文件
        if is_already_compressed(video):
            print(f"  跳过 (已压缩): {video.name}")
            skipped_count += 1
            print()
            continue

        if replace:
            output = video.parent / f"{video.stem}.tmp.mp4"
        else:
            output = video.parent / f"{video.stem}_compressed.mp4"

        result = compress_video(video, output, replace, skip_small=skip_small, **kwargs)
        if result is True:
            success_count += 1
        elif result is False:
            failed_count += 1
        else:  # None - 跳过
            skipped_count += 1

        print()

    print(f"完成: {success_count} 成功, {skipped_count} 跳过, {failed_count} 失败")


def compress_all(replace=True, skip_small=True, **kwargs):
    """压缩 downloads 目录下所有用户的视频"""
    if not DOWNLOADS_PATH.exists():
        print(f"下载目录不存在: {DOWNLOADS_PATH}")
        return

    user_dirs = [d for d in DOWNLOADS_PATH.iterdir() if d.is_dir()]
    if not user_dirs:
        print("没有找到用户目录")
        return

    print(f"找到 {len(user_dirs)} 个用户目录\n")

    for user_dir in sorted(user_dirs):
        compress_user_dir(user_dir, replace, skip_small, **kwargs)


def main():
    parser = argparse.ArgumentParser(
        description="抖音视频压缩脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                          # 压缩全部视频（默认直接替换原文件）
  %(prog)s --user 123456789          # 压缩指定用户视频
  %(prog)s --file video.mp4           # 压缩单个文件
  %(prog)s --keep                    # 保留原文件（生成 xxx_compressed.mp4）
  %(prog)s --aggressive               # 激进压缩模式 (牺牲质量，压缩率70-80%%)
  %(prog)s --crf 38 --preset medium   # 指定压缩质量和速度
  %(prog)s --no-skip-small            # 不跳过小文件
        """
    )

    parser.add_argument(
        "--user", "-u",
        help="指定用户 UID，只压缩该用户的视频"
    )
    parser.add_argument(
        "--file", "-f",
        help="压缩单个视频文件"
    )
    parser.add_argument(
        "--keep", "-k",
        action="store_true",
        help="保留原文件（默认压缩后直接替换，节省空间）"
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=32,
        help="视频压缩质量 (0-51, 默认32). 数值越小质量越好，文件越大. 推荐28-38"
    )
    parser.add_argument(
        "--no-skip-small",
        action="store_true",
        help="不跳过小文件 (默认跳过小于5MB的文件)"
    )
    parser.add_argument(
        "--preset",
        default="fast",
        choices=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"],
        help="压缩速度预设 (默认: fast). 速度越慢压缩率越高"
    )
    parser.add_argument(
        "--aggressive", "-a",
        action="store_true",
        help="激进压缩模式 (牺牲质量获得更高压缩率，适合视频仅作留存用途)"
    )

    args = parser.parse_args()

    # 是否跳过小文件
    skip_small = not args.no_skip_small
    # 是否保留原文件（默认替换）
    replace = not args.keep

    # 检查 ffmpeg
    if not check_ffmpeg():
        print("错误: 未找到 ffmpeg")
        print("请先安装 ffmpeg:")
        print("  macOS:   brew install ffmpeg")
        print("  Ubuntu:  sudo apt install ffmpeg")
        print("  Windows: choco install ffmpeg")
        sys.exit(1)

    # 执行压缩
    if args.file:
        # 压缩单个文件
        file_path = Path(args.file)
        if not file_path.is_absolute():
            file_path = SKILL_DIR / file_path

        if not file_path.exists():
            print(f"文件不存在: {file_path}")
            sys.exit(1)

        if replace:
            output = file_path.parent / f"{file_path.stem}.tmp.mp4"
        else:
            output = file_path.parent / f"{file_path.stem}_compressed.mp4"

        compress_video(file_path, output, replace, args.crf, args.preset, skip_small, args.aggressive)

    elif args.user:
        # 压缩指定用户目录
        user_dir = DOWNLOADS_PATH / args.user
        compress_user_dir(user_dir, replace, skip_small, crf=args.crf, preset=args.preset, aggressive=args.aggressive)

    else:
        # 压缩全部
        compress_all(replace, skip_small, crf=args.crf, preset=args.preset, aggressive=args.aggressive)


if __name__ == "__main__":
    main()
