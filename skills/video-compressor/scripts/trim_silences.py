#!/usr/bin/env python3
"""
视频静默/静态片段检测与剪切工具。

检测视频中同时满足以下条件的片段：
  1. 音频静默（无声）
  2. 画面静止（连续帧几乎无变化）

将这类片段从原视频中剪切掉，输出：
  - 精剪版视频（去除了目标片段）
  - 被剪掉的片段汇总（方便复查）
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from hw_detect import build_encode_args, detect_hardware, print_hardware_info, select_profile


@dataclass
class Segment:
    start: float  # seconds
    end: float    # seconds

    def duration(self) -> float:
        return self.end - self.start


def sec_to_time(sec: float) -> str:
    h = int(sec) // 3600
    m = (int(sec) % 3600) // 60
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:05.2f}"


def human_size(size_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def run_cmd(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"命令失败: {' '.join(cmd[:5])}...")
        print(result.stderr[:300])
    return result.stdout


def get_duration(video_path: Path) -> float:
    try:
        out = run_cmd([
            shutil.which("ffprobe") or "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", str(video_path),
        ])
        return float(json.loads(out)["format"]["duration"])
    except Exception:
        return 0.0


def detect_silent_segments(
    video_path: Path, noise_db: float, min_duration: float
) -> list[Segment]:
    """使用 ffmpeg silencedetect 检测人声频段静默片段。

    策略：
    1. 用 highpass/lowpass 滤波器将音频限制在人声频段（300~3000Hz）
    2. 用较短的检测窗口（30s）捕获静默，避免被短暂噪音打断
    3. 合并相邻静默片段（间距<60s），形成连续的"无人声"区间
    4. 过滤掉总时长不足 min_duration 的片段
    """
    detect_window = 30.0  # 静默检测窗口（秒），比最终要求短很多
    merge_gap = 60.0      # 相邻静默片段间距<60s就合并

    output = run_cmd([
        shutil.which("ffmpeg") or "ffmpeg",
        "-i", str(video_path),
        "-af", f"highpass=f=300,lowpass=f=3000,silencedetect=noise={noise_db}dB:d={detect_window}",
        "-f", "null", "-",
    ])

    raw_segments: list[Segment] = []
    starts = [float(m.group(1)) for m in re.finditer(r"silence_start:\s*([\d.]+)", output)]
    ends = [float(m.group(1)) for m in re.finditer(r"silence_end:\s*([\d.]+)", output)]
    for s, e in zip(starts, ends):
        raw_segments.append(Segment(s, e))

    if not raw_segments:
        return []

    # 合并相邻静默片段
    merged = [raw_segments[0]]
    for seg in raw_segments[1:]:
        if seg.start <= merged[-1].end + merge_gap:
            merged[-1].end = max(merged[-1].end, seg.end)
        else:
            merged.append(seg)

    # 过滤总时长
    return [s for s in merged if s.duration() >= min_duration]


def detect_static_segments(
    video_path: Path, threshold: float, min_duration: float
) -> list[Segment]:
    """
    一次性批量采样 + 直方图指纹比较检测画面静止片段。

    策略：用 ffmpeg fps 滤镜按固定间隔采样帧，
    将帧缩放到 4x4 像素后直接输出为裸 RGB 数据，
    在 Python 中计算相邻帧的指纹差异，
    连续多帧差异小 → 静态区间。
    """
    duration = get_duration(video_path)
    if duration <= 0:
        print("  警告：无法获取视频时长，跳过静态片段检测")
        return []

    sample_interval = 2.0  # 每隔 N 秒采一帧
    frame_size = 4 * 4 * 3  # 4x4 RGB

    # 用 fps 滤镜一次性下采样到 1/interval fps，输出裸 RGB
    cmd = [
        shutil.which("ffmpeg") or "ffmpeg",
        "-i", str(video_path),
        "-vf", f"fps=1/{int(sample_interval)},scale=4:4",
        "-pix_fmt", "rgb24",
        "-f", "rawvideo",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True)

    if result.returncode != 0 or not result.stdout:
        print("  警告：帧采样失败，跳过静态片段检测")
        return []

    raw = result.stdout
    n_frames = len(raw) // frame_size

    if n_frames < 2:
        print("  警告：采样帧数不足，跳过静态片段检测")
        return []

    # 计算每帧的指纹：4 个 2x2 区域的 RGB 平均值（共 12 维）
    def fingerprint(data: bytes) -> tuple:
        r_avg = [0.0] * 4
        g_avg = [0.0] * 4
        b_avg = [0.0] * 4
        for i in range(16):
            idx = i * 3
            region = i // 4
            r_avg[region] += data[idx]
            g_avg[region] += data[idx + 1]
            b_avg[region] += data[idx + 2]
        return tuple(int(v / 4) for v in r_avg + g_avg + b_avg)

    # 提取所有帧指纹
    fingerprints: list[tuple[float, tuple]] = []
    for i in range(n_frames):
        frame_data = raw[i * frame_size:(i + 1) * frame_size]
        if len(frame_data) == frame_size:
            ts = i * sample_interval
            fingerprints.append((ts, fingerprint(frame_data)))

    if len(fingerprints) < 2:
        return []

    # 比较相邻帧：连续相似帧聚合为静态区间
    diff_threshold = int(threshold * 255)  # threshold 0~1 → 像素差阈值
    static_ranges: list[tuple[float, float]] = []

    i = 0
    while i < len(fingerprints) - 1:
        fp1 = fingerprints[i][1]
        j = i + 1
        while j < len(fingerprints):
            fp2 = fingerprints[j][1]
            diff = sum(abs(a - b) for a, b in zip(fp1, fp2))
            if diff <= diff_threshold:
                j += 1
            else:
                break
        # i 到 j-1 是连续的静态区间
        if j > i + 1:  # 至少2帧连续静态
            seg_start = fingerprints[i][0]
            seg_end = fingerprints[j - 1][0] + sample_interval
            static_ranges.append((seg_start, seg_end))
        i = j

    # 合并相邻区间（间距小于 sample_interval 的合并）
    merged: list[tuple[float, float]] = []
    for start, end in sorted(static_ranges):
        if merged and start <= merged[-1][1] + sample_interval:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    # 过滤时长太短的
    result = [Segment(start, end) for start, end in merged if end - start >= min_duration]
    return result


def merge_segments(segments: list[Segment], gap: float = 0.5) -> list[Segment]:
    """合并有重叠或间距过近的片段。"""
    if not segments:
        return []
    segments = sorted(segments, key=lambda s: s.start)
    merged = [segments[0]]
    for seg in segments[1:]:
        if seg.start <= merged[-1].end + gap:
            merged[-1].end = max(merged[-1].end, seg.end)
        else:
            merged.append(seg)
    return merged


def cut_segments(
    video_path: Path,
    segments: list[Segment],
    output_path: Path,
    encode_args: list[str],
) -> tuple[bool, str]:
    """根据片段列表剪切视频，保留所有非静态区间。"""
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    if not segments:
        cmd = [ffmpeg, "-y", "-i", str(video_path)] + encode_args + [str(output_path)]
        subprocess.run(cmd, capture_output=True)
        return True, "无片段需剪切，直接复制"

    duration = get_duration(video_path)

    # 构建保留区间（取静态片段的反面）
    segments_sorted = sorted(segments, key=lambda s: s.start)
    keep_segments: list[Segment] = []

    last_end = 0.0
    for seg in segments_sorted:
        if seg.start > last_end:
            keep_segments.append(Segment(last_end, seg.start))
        last_end = max(last_end, seg.end)
    if last_end < duration:
        keep_segments.append(Segment(last_end, duration))

    if not keep_segments:
        print("  警告：所有区间均被判定为静态，视频将保留开头")
        keep_segments = [Segment(0, min(1.0, duration))]

    # 用 concat 拼接保留区间
    seg_parts = "".join(
        f"[0:v]trim=start={s.start}:end={s.end},setpts=PTS-STARTPTS[v{i}];"
        f"[0:a]atrim=start={s.start}:end={s.end},asetpts=PTS-STARTPTS[a{i}];"
        for i, s in enumerate(keep_segments)
    )
    n = len(keep_segments)
    filter_complex = seg_parts + f"{''.join(f'[v{i}][a{i}]' for i in range(n))}concat=n={n}:v=1:a=1[outv][outa]"

    cmd = [
        ffmpeg, "-y", "-i", str(video_path),
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
    ] + encode_args + [str(output_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return False, result.stderr[:500]
    return True, "成功"


def save_removed_clips(
    video_path: Path,
    segments: list[Segment],
    output_dir: Path,
    encode_args: list[str],
) -> list[Path]:
    """把被剪掉的片段单独保存，供复查。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for i, seg in enumerate(segments):
        clip_path = output_dir / f"{video_path.stem}_cut_{i + 1}_{sec_to_time(seg.start).replace(':', '')}.mp4"
        cmd = [
            shutil.which("ffmpeg") or "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-ss", str(seg.start),
            "-t", str(seg.duration()),
        ] + encode_args + [str(clip_path)]
        subprocess.run(cmd, capture_output=True)
        if clip_path.exists():
            saved.append(clip_path)
    return saved


def fmt_segs(segs: list[Segment]) -> str:
    if not segs:
        return "无"
    parts = []
    for s in segs:
        parts.append(f"{sec_to_time(s.start)}～{sec_to_time(s.end)} ({s.duration():.1f}s)")
    return ", ".join(parts)


def main():
    parser = argparse.ArgumentParser(description="视频静默/静态片段检测与剪切")
    parser.add_argument("-i", "--input", required=True, help="输入视频文件路径")
    parser.add_argument("--noise-db", type=float, default=-30.0, help="静默检测分贝阈值 (默认 -30dB)")
    parser.add_argument("--min-duration", type=float, default=120.0, help="最短片段时长(秒)，小于此值忽略 (默认 120s，即2分钟)")
    parser.add_argument("--scene-threshold", type=float, default=0.05,
                        help="画面静止阈值 0~1，越小越严格 (默认 0.05，差异<5%%视为静止)")
    parser.add_argument("--crf", type=int, default=23, help="CRF 质量值 (默认 23)")
    parser.add_argument("--maxrate", default="2500k", help="最大码率限制 (默认 2500k)")
    parser.add_argument("--bufsize", default="2500k", help="VBV 缓冲区大小 (默认 2500k)")
    parser.add_argument("--audio-bitrate", default="96k", help="输出音频比特率 (默认 96k)")
    parser.add_argument("--preset", default="veryfast", help="编码预设 (默认 veryfast)")
    parser.add_argument("--mode", default="both", choices=["both", "silence", "static"],
                        help="检测模式: both=同时满足音静+画面静止, silence=仅静音(不考虑画面), static=仅画面静止(不考虑声音) (默认 both)")
    parser.add_argument("--output-suffix", default="_trimmed", help="输出文件后缀 (默认 _trimmed)")
    parser.add_argument("--cut-dir-name", default="_cuts", help="被剪片段存放目录名 (默认 _cuts)")
    parser.add_argument("--codec", default=None,
                        choices=["hevc_vt", "h264_vt", "x264", "x265", "x264_fast"],
                        help="编码器选择 (默认自动检测最优方案)")
    args = parser.parse_args()

    video_path = Path(args.input).resolve()
    if not video_path.exists():
        print(f"文件不存在: {video_path}")
        sys.exit(1)

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

    print(f"正在分析: {video_path.name}")
    print(f"  静默阈值: {args.noise_db}dB | 画面静止阈值: {args.scene_threshold} | "
          f"最短片段: {args.min_duration}s | 模式: {args.mode}")

    # 1. 检测静音片段
    print("\n[1/3] 检测音频静默片段...")
    silent_segs = detect_silent_segments(video_path, args.noise_db, args.min_duration)
    print(f"  找到 {len(silent_segs)} 个静音片段")

    # 2. 检测画面静止片段
    print("\n[2/3] 检测画面静止片段（批量采样中...）...")
    static_segs = detect_static_segments(video_path, args.scene_threshold, args.min_duration)
    print(f"  找到 {len(static_segs)} 个静止片段")

    # 3. 取目标片段
    if args.mode == "both":
        target_segs: list[Segment] = []
        i = j = 0
        s_sorted = sorted(silent_segs, key=lambda s: s.start)
        st_sorted = sorted(static_segs, key=lambda s: s.start)
        while i < len(s_sorted) and j < len(st_sorted):
            a, b = s_sorted[i], st_sorted[j]
            start = max(a.start, b.start)
            end = min(a.end, b.end)
            if end > start:
                target_segs.append(Segment(start, end))
            if a.end < b.end:
                i += 1
            else:
                j += 1
        print(f"\n[3/3] 同时满足静音+静止的片段: {len(target_segs)} 个")
    elif args.mode == "silence":
        target_segs = silent_segs
        print(f"\n[3/3] 静音片段: {len(target_segs)} 个")
    else:
        target_segs = static_segs
        print(f"\n[3/3] 静止片段: {len(target_segs)} 个")

    # 合并相邻/重叠
    target_segs = merge_segments(target_segs)
    total_removed = sum(s.duration() for s in target_segs)
    print(f"  合并后片段数: {len(target_segs)}, 总时长: {total_removed:.1f}s")

    # 4. 输出精剪版
    output_path = video_path.parent / f"{video_path.stem}{args.output_suffix}.mp4"
    cut_dir = video_path.parent / f"{video_path.stem}{args.cut_dir_name}"

    print(f"\n正在生成精剪版...")
    ok, msg = cut_segments(
        video_path, target_segs, output_path, encode_args,
    )

    if not ok:
        print(f"剪切失败: {msg}")
        sys.exit(1)

    original_size = video_path.stat().st_size
    trimmed_size = output_path.stat().st_size

    # 5. 保存被剪片段
    if target_segs:
        print(f"正在保存被剪片段到: {cut_dir}/")
        saved = save_removed_clips(
            video_path, target_segs, cut_dir, encode_args,
        )
        print(f"  已保存 {len(saved)} 个片段")

    # 6. 报告
    print(f"\n{'═' * 60}")
    print(f"  原始文件: {video_path.name}  {human_size(original_size)}")
    print(f"  精剪版:   {output_path.name}  {human_size(trimmed_size)}")
    if target_segs:
        ratio = (1 - trimmed_size / original_size) * 100 if original_size else 0
        print(f"  节省:     {ratio:.1f}%")
        print(f"  被剪片段汇总: {fmt_segs(target_segs)}")
    else:
        print(f"  被剪片段: 无")
    print(f"{'═' * 60}")

    # 7. 保存报告
    if target_segs:
        cut_dir.mkdir(parents=True, exist_ok=True)
        report_path = cut_dir / "_report.json"
    else:
        report_path = video_path.parent / f"{video_path.stem}_no_cuts_report.json"

    report = {
        "original": str(video_path),
        "trimmed": str(output_path),
        "removed_segments": [
            {"start": s.start, "end": s.end, "duration": s.duration()}
            for s in target_segs
        ],
        "removed_summary": fmt_segs(target_segs),
        "original_size": original_size,
        "trimmed_size": trimmed_size,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\n报告已保存: {report_path}")


if __name__ == "__main__":
    main()
