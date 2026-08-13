"""video-screenshot 共享工具函数。

从 fachuan chat_records/services/ 移植，去除 Django 依赖。
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import math
import re
import select
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, cast

try:
    from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps, ImageStat
except ImportError:
    print("❌ 缺少依赖: Pillow", file=sys.stderr)
    print("   请使用 uv 运行: uv run scripts/extract.py --help", file=sys.stderr)
    print("   或运行: pip install Pillow", file=sys.stderr)
    raise SystemExit(1)

logger = logging.getLogger("video-screenshot")

_LANCZOS: Any = getattr(Image, "Resampling", Image).LANCZOS

# ======================================================================
# A. FFmpeg 工具
# ======================================================================


@dataclass(frozen=True)
class FFProbeInfo:
    duration_seconds: float
    time_base_seconds: float | None = None
    frame_rate_fps: float | None = None


def _parse_rate(value: Any) -> float | None:
    text = str(value or "")
    if not text or text == "0/0":
        return None
    try:
        if "/" in text:
            n, d = text.split("/", 1)
            denom = float(d)
            return float(n) / denom if denom else None
        rate = float(text)
        return rate if rate > 0 else None
    except Exception:
        return None


def find_tool(name: str) -> str | None:
    p = shutil.which(name)
    if p:
        return p
    for root in ("/usr/local/bin", "/opt/homebrew/bin", "/usr/bin"):
        candidate = str(Path(root) / name)
        if Path(candidate).exists() and Path(candidate).stat().st_mode & 0o111:
            return candidate
    return None


def probe_video(video_path: str) -> FFProbeInfo:
    if not video_path or not Path(video_path).exists():
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    duration = 0.0
    time_base_seconds: float | None = None
    frame_rate_fps: float | None = None
    ffprobe = find_tool("ffprobe")
    if ffprobe:
        cmd = [
            ffprobe, "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "format=duration:stream=time_base,avg_frame_rate,r_frame_rate",
            "-of", "json",
            video_path,
        ]
        try:
            result = subprocess.run(cmd, timeout=10, check=True, capture_output=True, text=True)
            data = json.loads(result.stdout or "{}")
            duration = float((data.get("format") or {}).get("duration") or 0.0)
            streams = data.get("streams") or []
            if streams:
                tb = str((streams[0] or {}).get("time_base") or "")
                if "/" in tb:
                    n, d = tb.split("/", 1)
                    time_base_seconds = float(n) / float(d) if float(d) else None
                frame_rate_fps = (
                    _parse_rate((streams[0] or {}).get("avg_frame_rate"))
                    or _parse_rate((streams[0] or {}).get("r_frame_rate"))
                )
        except Exception:
            logger.exception("ffprobe 解析失败: %s", video_path)
            duration = 0.0
            frame_rate_fps = None
    else:
        duration = _probe_duration_by_ffmpeg(video_path)
        frame_rate_fps = None

    if duration <= 0:
        raise RuntimeError(f"无法解析视频时长: {video_path}")

    return FFProbeInfo(
        duration_seconds=duration,
        time_base_seconds=time_base_seconds,
        frame_rate_fps=frame_rate_fps,
    )


def _probe_duration_by_ffmpeg(video_path: str) -> float:
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        return 0.0
    cmd = [ffmpeg, "-hide_banner", "-i", video_path]
    try:
        result = subprocess.run(cmd, timeout=10, check=False, capture_output=True, text=True)
    except Exception:
        return 0.0
    text = (result.stderr or "") + "\n" + (result.stdout or "")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", text)
    if not m:
        return 0.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def build_ffmpeg_filter_args(
    strategy: str,
    interval_seconds: float,
    scene_threshold: float,
    max_size: int = 0,
    frame_rate_fps: float | None = None,
    sample_interval: float = 5.0,
) -> tuple[list[str], str, list[str]]:
    """构建 ffmpeg 滤镜参数，返回 (input_args, vf, extra_args)。"""
    # max_size=0 时保持原始分辨率，不缩放
    if max_size and max_size > 0:
        scale = (
            f"scale='if(gt(iw,ih),min({max_size},iw),-2)':"
            f"'if(gt(iw,ih),-2,min({max_size},ih))'"
        )
    else:
        scale = ""
    vfr_args = ["-vsync", "vfr", "-frame_pts", "1"]

    fmt = ",format=yuvj420p"
    # 构建 scale 部分的滤镜链（可能为空）
    scale_part = f",{scale}" if scale else ""

    # scene 策略：场景检测 + 定期采样保底（确保静态画面也有覆盖）
    scene_expr = f"gt(scene,{float(scene_threshold)})"
    if frame_rate_fps and frame_rate_fps > 0 and sample_interval and sample_interval > 0:
        n_frames = max(1, round(frame_rate_fps * sample_interval))
        scene_expr = f"{scene_expr}+not(mod(n\\,{n_frames}))"
    scene_vf = f"select='{scene_expr}'{scale_part}{fmt}"

    strategy_map: dict[str, tuple[list[str], str, list[str]]] = {
        "scene": ([], scene_vf, vfr_args),
        "keyframe": (["-skip_frame", "nokey"], f"{scale_part[1:]},mpdecimate{fmt}" if scale_part else f"mpdecimate{fmt}", vfr_args),
        "smart": ([], f"{scale_part[1:]},mpdecimate{fmt}" if scale_part else f"mpdecimate{fmt}", vfr_args),
    }

    if strategy in strategy_map:
        return strategy_map[strategy]

    fps = 1.0 / interval_seconds
    return [], f"fps={fps}{scale_part},mpdecimate{fmt}", []


def _force_kill_proc(proc: subprocess.Popen[str]) -> None:
    with contextlib.suppress(Exception):
        proc.terminate()
    try:
        proc.wait(timeout=2)
    except Exception:
        with contextlib.suppress(Exception):
            proc.kill()


def _read_progress_lines(
    proc: subprocess.Popen[str],
    timeout_seconds: float | None,
    started: float,
) -> Any:
    if proc.stdout is None:
        return
    while True:
        if timeout_seconds is not None and time.monotonic() - started > timeout_seconds:
            _force_kill_proc(proc)
            raise RuntimeError("ffmpeg 抽帧超时")
        if proc.poll() is not None:
            break
        rlist, _, _ = select.select([proc.stdout], [], [], 0.2)
        if not rlist:
            continue
        line = proc.stdout.readline()
        if not line:
            break
        line = (line or "").strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        yield {k: v}


def _check_exit(proc: subprocess.Popen[str]) -> None:
    try:
        rc = proc.wait(timeout=5)
    except Exception:
        with contextlib.suppress(Exception):
            proc.kill()
        rc = proc.wait()
    if rc != 0:
        err = ""
        try:
            if proc.stderr is not None:
                err = proc.stderr.read() or ""
        except Exception:
            err = ""
        err = (err or "").strip()
        if err:
            tail = "\n".join(err.splitlines()[-12:])
            raise RuntimeError(f"ffmpeg 抽帧失败:\n{tail}")
        raise RuntimeError("ffmpeg 抽帧失败，请检查视频文件或 ffmpeg 安装")


def run_ffmpeg_extract(
    *,
    video_path: str,
    output_pattern: str,
    strategy: str = "scene",
    interval_seconds: float = 1.0,
    scene_threshold: float = 0.25,
    max_size: int = 1280,
    quality: int = 6,
    timeout_seconds: float | None = None,
    frame_rate_fps: float | None = None,
    sample_interval: float = 5.0,
) -> Any:
    """运行 ffmpeg 抽帧，yield 进度字典。"""
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("未检测到 ffmpeg，请先安装 (brew install ffmpeg)")

    input_args, vf, extra_args = build_ffmpeg_filter_args(
        strategy, interval_seconds, scene_threshold, max_size,
        frame_rate_fps=frame_rate_fps,
        sample_interval=sample_interval,
    )

    cmd = [
        ffmpeg, "-hide_banner", "-nostats",
        "-loglevel", "error",
        "-progress", "pipe:1",
        *input_args,
        "-i", video_path,
        "-vf", vf,
        *extra_args,
        "-q:v", str(quality),
        output_pattern,
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    started = time.monotonic()

    yield from _read_progress_lines(proc, timeout_seconds, started)
    _check_exit(proc)


# ======================================================================
# B. 图像处理
# ======================================================================


def _content_crop_box(
    width: int,
    height: int,
    *,
    top_ratio: float = 0.12,
    bottom_ratio: float = 0.12,
    left_ratio: float = 0.04,
    right_ratio: float = 0.04,
) -> tuple[int, int, int, int]:
    top = int(max(0, min(height - 1, round(height * top_ratio))))
    bottom_cut = int(max(0, min(height - 1, round(height * bottom_ratio))))
    left = int(max(0, min(width - 1, round(width * left_ratio))))
    right_cut = int(max(0, min(width - 1, round(width * right_ratio))))
    bottom = max(top + 1, height - bottom_cut)
    right = max(left + 1, width - right_cut)
    return left, top, right, bottom


def _crop_content(
    img: Image.Image,
    *,
    top_ratio: float = 0.12,
    bottom_ratio: float = 0.12,
    left_ratio: float = 0.04,
    right_ratio: float = 0.04,
) -> Image.Image:
    w, h = img.size
    if w <= 0 or h <= 0:
        return img
    return img.crop(
        _content_crop_box(
            w,
            h,
            top_ratio=top_ratio,
            bottom_ratio=bottom_ratio,
            left_ratio=left_ratio,
            right_ratio=right_ratio,
        )
    )


def calc_dhash_hex(
    image_bytes: bytes,
    *,
    hash_size: int = 8,
    crop_top_ratio: float = 0.12,
    crop_bottom_ratio: float = 0.12,
    crop_left_ratio: float = 0.04,
    crop_right_ratio: float = 0.04,
) -> str:
    if not image_bytes or hash_size <= 0:
        return ""
    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert("L")
    img = _crop_content(
        img,
        top_ratio=crop_top_ratio,
        bottom_ratio=crop_bottom_ratio,
        left_ratio=crop_left_ratio,
        right_ratio=crop_right_ratio,
    )
    img = img.resize((hash_size + 1, hash_size), _LANCZOS)
    pixels = list(img.getdata())
    bits = 0
    for row in range(hash_size):
        row_start = row * (hash_size + 1)
        for col in range(hash_size):
            left = pixels[row_start + col]
            right = pixels[row_start + col + 1]
            if left > right:
                bits |= 1 << (row * hash_size + col)
    hex_len = (hash_size * hash_size) // 4
    return f"{bits:0{hex_len}x}"


def hamming_distance_hex(a: str, b: str) -> int | None:
    if not a or not b:
        return None
    try:
        x = int(a, 16)
        y = int(b, 16)
    except Exception:
        return None
    return (x ^ y).bit_count()


def calc_thumb_bytes(
    image_bytes: bytes,
    *,
    size: int = 48,
    crop_top_ratio: float = 0.12,
    crop_bottom_ratio: float = 0.12,
    crop_left_ratio: float = 0.04,
    crop_right_ratio: float = 0.04,
    autocontrast: bool = False,
) -> bytes:
    if not image_bytes or size <= 0:
        return b""
    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert("L")
    w, h = img.size
    if w <= 0 or h <= 0:
        return b""
    img = _crop_content(
        img,
        top_ratio=crop_top_ratio,
        bottom_ratio=crop_bottom_ratio,
        left_ratio=crop_left_ratio,
        right_ratio=crop_right_ratio,
    )
    if autocontrast:
        img = ImageOps.autocontrast(img)
    img = img.resize((size, size), _LANCZOS)
    return cast(bytes, img.tobytes())


def mean_abs_diff(a: bytes, b: bytes) -> float | None:
    if not a or not b or len(a) != len(b):
        return None
    total = 0
    for x, y in zip(a, b):
        total += x - y if x >= y else y - x
    return total / float(len(a))


def ssim_bytes(a: bytes, b: bytes) -> float | None:
    """计算两个等长灰度缩略图的全局 SSIM。"""
    if not a or not b or len(a) != len(b):
        return None
    n = len(a)
    mean_a = sum(a) / float(n)
    mean_b = sum(b) / float(n)
    denom = max(n - 1, 1)
    var_a = sum((x - mean_a) ** 2 for x in a) / float(denom)
    var_b = sum((y - mean_b) ** 2 for y in b) / float(denom)
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b)) / float(denom)
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    divisor = (mean_a * mean_a + mean_b * mean_b + c1) * (var_a + var_b + c2)
    if not divisor:
        return None
    return ((2 * mean_a * mean_b + c1) * (2 * cov + c2)) / divisor


def calc_scroll_image(
    image_bytes: bytes,
    *,
    width: int = 96,
    height: int = 160,
    crop_top_ratio: float = 0.12,
    crop_bottom_ratio: float = 0.12,
    crop_left_ratio: float = 0.04,
    crop_right_ratio: float = 0.04,
) -> Image.Image | None:
    if not image_bytes or width <= 0 or height <= 0:
        return None
    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert("L")
    img = _crop_content(
        img,
        top_ratio=crop_top_ratio,
        bottom_ratio=crop_bottom_ratio,
        left_ratio=crop_left_ratio,
        right_ratio=crop_right_ratio,
    )
    img = ImageOps.autocontrast(img)
    return img.resize((width, height), _LANCZOS)


def _shifted_mean_abs_diff(a: Image.Image, b: Image.Image, shift: int) -> tuple[float, float]:
    width, height = a.size
    if b.size != a.size or width <= 0 or height <= 0:
        return 999.0, 0.0
    if shift >= 0:
        box_a = (0, shift, width, height)
        box_b = (0, 0, width, height - shift)
    else:
        box_a = (0, 0, width, height + shift)
        box_b = (0, -shift, width, height)
    crop_a = a.crop(box_a)
    crop_b = b.crop(box_b)
    if crop_a.size[1] <= 0 or crop_b.size[1] <= 0:
        return 999.0, 0.0
    diff = ImageChops.difference(crop_a, crop_b)
    return ImageStat.Stat(diff).mean[0], crop_a.size[1] / float(height)


def scroll_overlap_duplicate(
    current: Image.Image,
    previous_images: list[Image.Image],
    *,
    threshold: float,
    min_shift: int = 4,
    max_shift_ratio: float = 0.35,
    min_overlap_ratio: float = 0.70,
    step: int = 4,
) -> bool:
    """检测当前帧是否只是最近保留帧的轻微纵向滚动版本。"""
    if current is None or not previous_images or threshold <= 0:
        return False
    width, height = current.size
    if width <= 0 or height <= 0:
        return False
    max_shift = max(min_shift, int(round(height * max_shift_ratio)))
    for prev in reversed(previous_images):
        if prev.size != current.size:
            continue
        best_diff = 999.0
        best_shift = 0
        best_overlap = 0.0
        for shift in range(-max_shift, max_shift + 1, step):
            diff, overlap = _shifted_mean_abs_diff(prev, current, shift)
            if overlap < min_overlap_ratio:
                continue
            if diff < best_diff:
                best_diff = diff
                best_shift = shift
                best_overlap = overlap
        if abs(best_shift) >= min_shift and best_overlap >= min_overlap_ratio and best_diff <= threshold:
            return True
    return False


def scroll_overlap_metrics(
    previous: Image.Image | None,
    current: Image.Image | None,
    *,
    min_shift: int = 4,
    max_shift_ratio: float = 0.35,
    min_overlap_ratio: float = 0.70,
    step: int = 4,
) -> dict[str, Any]:
    """返回相邻两帧的最佳纵向滚动重叠指标，不直接作删除决定。"""
    empty = {"diff": 999.0, "overlap_ratio": 0.0, "shift": 0, "matched": False}
    if previous is None or current is None or previous.size != current.size:
        return empty
    width, height = current.size
    if width <= 0 or height <= 0:
        return empty
    max_shift = max(min_shift, int(round(height * max_shift_ratio)))
    best = dict(empty)
    for shift in range(-max_shift, max_shift + 1, max(1, step)):
        if abs(shift) < min_shift:
            continue
        diff, overlap = _shifted_mean_abs_diff(previous, current, shift)
        if overlap < min_overlap_ratio:
            continue
        if diff < float(best["diff"]):
            best = {
                "diff": float(diff),
                "overlap_ratio": float(overlap),
                "shift": int(shift),
                "matched": True,
            }
    return best


# 3x3 Laplacian 卷积核（用于模糊检测）
_LAPLACIAN = ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1, offset=0)


def calc_blur_score(image_bytes: bytes, *, size: int = 128) -> float:
    """计算帧的 Laplacian 方差，值越低越模糊。"""
    if not image_bytes:
        return 0.0
    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert("L")
    img = img.resize((size, size), _LANCZOS)
    filtered = img.filter(_LAPLACIAN)
    return ImageStat.Stat(filtered).var[0]


def calc_content_quality(image_bytes: bytes) -> dict[str, Any]:
    """分析帧的内容质量，返回指标字典。"""
    if not image_bytes:
        return {"label": "empty", "content_std": 0.0, "white_ratio": 0.0, "grid_flat": 9}
    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    w, h = img.size
    if w <= 0 or h <= 0:
        return {"label": "empty", "content_std": 0.0, "white_ratio": 0.0, "grid_flat": 9}

    # 直方图分析
    hist = img.histogram()
    total = w * h
    white_ratio = sum(hist[240:]) / total
    black_ratio = sum(hist[:15]) / total

    # 内容区域（排除顶部 8% 和底部 8% 的状态栏）
    content_crop = img.crop((0, int(h * 0.08), w, int(h * 0.92)))
    content_std = ImageStat.Stat(content_crop).stddev[0]

    # 3×3 网格分析
    grid_stds: list[float] = []
    for row in range(3):
        for col in range(3):
            y1, y2 = row * h // 3, (row + 1) * h // 3
            x1, x2 = col * w // 3, (col + 1) * w // 3
            grid_stds.append(ImageStat.Stat(img.crop((x1, y1, x2, y2))).stddev[0])

    grid_flat = sum(1 for s in grid_stds if s < 10)
    grid_high = sum(1 for s in grid_stds if s > 50)
    grid_spread = max(grid_stds) - min(grid_stds)

    # 分类
    label = ""
    if content_std < 10 or white_ratio > 0.95 or black_ratio > 0.95:
        label = "blank"
    elif content_std < 35 and grid_high <= 2:
        label = "startup"
    elif grid_spread > 45 and grid_flat >= 2:
        label = "transition"

    return {
        "label": label,
        "content_std": content_std,
        "white_ratio": white_ratio,
        "black_ratio": black_ratio,
        "grid_flat": grid_flat,
        "grid_high": grid_high,
        "grid_spread": grid_spread,
    }


def calc_loading_overlay_score(image_bytes: bytes) -> dict[str, Any]:
    """保守估计居中加载遮罩风险；只在高置信时供本地质量过滤使用。"""
    empty = {
        "score": 0.0,
        "label": "",
        "center_bright_ratio": 0.0,
        "center_std": 0.0,
        "surround_darkening": 0.0,
        "center_border_contrast": 0.0,
    }
    if not image_bytes:
        return empty
    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    width, height = img.size
    if width < 40 or height < 80:
        return empty
    # 手机加载框通常位于中部，面积约为画面的 12%—25%。同时要求外围被遮罩压暗，
    # 避免把普通白色内容卡片、聊天气泡或大面积白底页面误判成加载态。
    box = (
        int(width * 0.27),
        int(height * 0.35),
        int(width * 0.73),
        int(height * 0.68),
    )
    inner = (
        int(width * 0.35),
        int(height * 0.42),
        int(width * 0.65),
        int(height * 0.61),
    )
    center = img.crop(box)
    inner_center = img.crop(inner)
    full_mean = float(ImageStat.Stat(img).mean[0])
    center_stat = ImageStat.Stat(center)
    center_mean = float(center_stat.mean[0])
    center_std = float(center_stat.stddev[0])
    hist = inner_center.histogram()
    total = max(1, inner_center.size[0] * inner_center.size[1])
    bright_ratio = sum(hist[238:]) / float(total)
    surround_darkening = max(0.0, center_mean - full_mean)
    # 中央亮块与稍大邻域的亮度落差，用于识别弹出的白色加载卡片边界。
    side_regions = [
        img.crop((int(width * 0.23), int(height * 0.42), int(width * 0.34), int(height * 0.61))),
        img.crop((int(width * 0.66), int(height * 0.42), int(width * 0.77), int(height * 0.61))),
        img.crop((int(width * 0.27), int(height * 0.35), int(width * 0.73), int(height * 0.42))),
    ]
    side_means = [float(ImageStat.Stat(region).mean[0]) for region in side_regions]
    side_stds = [float(ImageStat.Stat(region).stddev[0]) for region in side_regions]
    surround_mean = sum(side_means) / float(len(side_means))
    surround_std = sum(side_stds) / float(len(side_stds))
    border_contrast = max(0.0, float(ImageStat.Stat(inner_center).mean[0]) - surround_mean)
    score = 0.0
    if bright_ratio >= 0.58:
        score += min(0.42, (bright_ratio - 0.58) * 1.4 + 0.18)
    if surround_darkening >= 22.0:
        score += min(0.32, (surround_darkening - 22.0) / 80.0 + 0.12)
    if border_contrast >= 20.0:
        score += min(0.26, (border_contrast - 20.0) / 70.0 + 0.08)
    overlay_shape = surround_std <= 22.0 and border_contrast >= 55.0
    if overlay_shape:
        score += 0.28
    # 纯白空页的中央区域过于平坦且外围并不明显变暗，不应命中。
    if center_std < 8.0 and surround_darkening < 28.0:
        score *= 0.25
    final_score = max(0.0, min(1.0, score))
    label = ""
    if final_score >= 0.88:
        label = "loading_overlay" if overlay_shape else "incomplete_page"
    return {
        "score": final_score,
        "label": label,
        "center_bright_ratio": bright_ratio,
        "center_std": center_std,
        "surround_darkening": surround_darkening,
        "center_border_contrast": border_contrast,
    }


def transient_ui_drop_reason(metrics: dict[str, Any]) -> str:
    """仅把高置信加载浮层交给代码自动丢弃；未完成页留给视觉审计。"""
    if (
        str(metrics.get("label") or "") == "loading_overlay"
        and float(metrics.get("score") or 0.0) >= 0.92
        and float(metrics.get("center_border_contrast") or 0.0) >= 55.0
    ):
        return "quality_loading_overlay"
    return ""


def calc_vertical_seam_score(image_bytes: bytes, *, width: int = 96, height: int = 160) -> float:
    """估计画面内部纵向拼接缝强度；只用于排序，不单独作为删除依据。"""
    if not image_bytes:
        return 0.0
    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    img = img.resize((width, height), _LANCZOS)
    # 排除外侧黑边、状态栏与底部导航栏，避免把手机画幅边界当成拼接缝。
    top = max(0, int(height * 0.10))
    bottom = max(top + 1, int(height * 0.90))
    left = max(2, int(width * 0.12))
    right = min(width - 2, int(width * 0.88))
    pixels = img.load()
    edge_scores: list[float] = []
    darkness_scores: list[float] = []
    for x in range(left, right):
        diffs: list[int] = []
        dark = 0
        for y in range(top, bottom):
            value = int(pixels[x, y])
            diffs.append(abs(value - int(pixels[x - 1, y])))
            if value < 24:
                dark += 1
        edge_scores.append(sum(diffs) / float(len(diffs) or 1))
        darkness_scores.append(dark / float(max(1, bottom - top)))
    if not edge_scores:
        return 0.0
    ordered = sorted(edge_scores)
    median = ordered[len(ordered) // 2]
    edge_peak = max(edge_scores)
    edge_ratio = edge_peak / max(2.0, median)
    dark_band = max(darkness_scores) if darkness_scores else 0.0
    # 0—1 归一化。内部强边缘和贯穿式暗条同时出现时得分最高。
    return max(0.0, min(1.0, (edge_ratio - 2.0) / 6.0 * 0.65 + dark_band * 0.55))


def calc_transition_image(
    image_bytes: bytes,
    *,
    width: int = 72,
    height: int = 120,
    crop_top_ratio: float = 0.08,
    crop_bottom_ratio: float = 0.10,
    crop_left_ratio: float = 0.03,
    crop_right_ratio: float = 0.03,
) -> Image.Image | None:
    if not image_bytes:
        return None
    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    img = _crop_content(
        img,
        top_ratio=crop_top_ratio,
        bottom_ratio=crop_bottom_ratio,
        left_ratio=crop_left_ratio,
        right_ratio=crop_right_ratio,
    )
    return img.resize((width, height), _LANCZOS)


def _image_mad(a: Image.Image, b: Image.Image) -> float:
    if a.size != b.size or a.size[0] <= 0 or a.size[1] <= 0:
        return 999.0
    return float(ImageStat.Stat(ImageChops.difference(a, b)).mean[0])


def horizontal_mixed_transition_score(
    previous: Image.Image | None,
    current: Image.Image | None,
    following: Image.Image | None,
) -> dict[str, Any]:
    """判断 current 是否可由前后两页横向滑动拼合得到。"""
    empty = {"score": 0.0, "orientation": "", "cut_ratio": 0.0, "mix_error": 999.0, "neighbor_diff": 0.0}
    if previous is None or current is None or following is None:
        return empty
    if previous.size != current.size or following.size != current.size:
        return empty
    width, height = current.size
    if width < 16 or height < 16:
        return empty
    neighbor_diff = _image_mad(previous, following)
    if neighbor_diff < 10.0:
        return empty

    best_error = 999.0
    best_orientation = ""
    best_cut = 0
    for cut in range(max(4, width // 4), min(width - 4, width * 3 // 4) + 1, max(2, width // 24)):
        # 页面向左滑：旧页尾部在左，新页头部在右。
        left_cur = current.crop((0, 0, cut, height))
        right_cur = current.crop((cut, 0, width, height))
        left_old = previous.crop((width - cut, 0, width, height))
        right_new = following.crop((0, 0, width - cut, height))
        left_error = _image_mad(left_cur, left_old)
        right_error = _image_mad(right_cur, right_new)
        error = (left_error * cut + right_error * (width - cut)) / float(width)
        if error < best_error:
            best_error = error
            best_orientation = "swipe_left"
            best_cut = cut

        # 页面向右滑：新页尾部在左，旧页头部在右。
        left_new = following.crop((width - cut, 0, width, height))
        right_old = previous.crop((0, 0, width - cut, height))
        left_error = _image_mad(left_cur, left_new)
        right_error = _image_mad(right_cur, right_old)
        error = (left_error * cut + right_error * (width - cut)) / float(width)
        if error < best_error:
            best_error = error
            best_orientation = "swipe_right"
            best_cut = cut

    # 只有拼合误差显著小于前后页差异时才给高分；绝对误差过大时衰减。
    relative_gain = max(0.0, (neighbor_diff - best_error) / max(neighbor_diff, 1.0))
    # JPEG/缩略重采样会让真实拼接的 MAD 落在 20—25；40 以上才视为解释力不足。
    absolute_factor = max(0.0, min(1.0, (40.0 - best_error) / 30.0))
    score = max(0.0, min(1.0, relative_gain * absolute_factor * 1.35))
    return {
        "score": score,
        "orientation": best_orientation,
        "cut_ratio": best_cut / float(width),
        "mix_error": best_error,
        "neighbor_diff": neighbor_diff,
    }


def temporal_frame_metrics(
    image_bytes: bytes,
    *,
    crop_top_ratio: float = 0.12,
    crop_bottom_ratio: float = 0.12,
    crop_left_ratio: float = 0.04,
    crop_right_ratio: float = 0.04,
) -> dict[str, Any]:
    """计算时间簇择优使用的轻量指标。"""
    quality = calc_content_quality(image_bytes)
    thumb = calc_thumb_bytes(
        image_bytes,
        size=48,
        crop_top_ratio=crop_top_ratio,
        crop_bottom_ratio=crop_bottom_ratio,
        crop_left_ratio=crop_left_ratio,
        crop_right_ratio=crop_right_ratio,
    )
    ssim_thumb = calc_thumb_bytes(
        image_bytes,
        size=32,
        crop_top_ratio=crop_top_ratio,
        crop_bottom_ratio=crop_bottom_ratio,
        crop_left_ratio=crop_left_ratio,
        crop_right_ratio=crop_right_ratio,
        autocontrast=True,
    )
    return {
        "thumb": thumb,
        "ssim_thumb": ssim_thumb,
        "blur_score": calc_blur_score(image_bytes),
        "quality": quality,
        "loading_overlay": calc_loading_overlay_score(image_bytes),
        "seam_score": calc_vertical_seam_score(image_bytes),
        "scroll_image": calc_scroll_image(
            image_bytes,
            crop_top_ratio=crop_top_ratio,
            crop_bottom_ratio=crop_bottom_ratio,
            crop_left_ratio=crop_left_ratio,
            crop_right_ratio=crop_right_ratio,
        ),
        "transition_image": calc_transition_image(image_bytes),
    }


def _temporal_pair_is_stable(
    previous: dict[str, Any],
    current: dict[str, Any],
    *,
    max_gap_seconds: float,
    pixel_diff_threshold: float,
    ssim_threshold: float,
) -> bool:
    prev_time = previous.get("capture_time_seconds")
    cur_time = current.get("capture_time_seconds")
    if prev_time is None or cur_time is None:
        return False
    gap = float(cur_time) - float(prev_time)
    if gap < 0 or gap > max_gap_seconds:
        return False
    diff = mean_abs_diff(previous.get("thumb") or b"", current.get("thumb") or b"")
    sim = ssim_bytes(previous.get("ssim_thumb") or b"", current.get("ssim_thumb") or b"")
    return bool(
        (diff is not None and diff <= pixel_diff_threshold)
        or (sim is not None and sim >= ssim_threshold)
    )


def _temporal_selection_score(
    item: dict[str, Any],
    *,
    dwell_after_seconds: float,
    prefer_later: float = 0.0,
) -> float:
    """给簇内候选打分；清晰、稳定、无拼接缝的后期帧优先。"""
    blur = max(0.0, float(item.get("blur_score") or 0.0))
    blur_component = min(2.0, math.log1p(blur) / 3.2)
    dwell_component = min(1.5, max(0.0, dwell_after_seconds) * 1.5)
    seam_penalty = min(1.4, max(0.0, float(item.get("seam_score") or 0.0)) * 1.4)
    mixed_penalty = min(2.5, max(0.0, float(item.get("mixed_transition_score") or 0.0)) * 2.5)
    label = str((item.get("quality") or {}).get("label") or "")
    quality_penalty = {
        "empty": 4.0,
        "blank": 4.0,
        "startup": 1.5,
        "transition": 1.2,
    }.get(label, 0.0)
    loading_metrics = item.get("loading_overlay") or {}
    loading_score = max(0.0, float(loading_metrics.get("score") or 0.0))
    loading_penalty = min(
        4.0,
        loading_score * (4.0 if loading_metrics.get("label") == "loading_overlay" else 1.0),
    )
    return (
        blur_component + dwell_component + prefer_later
        - seam_penalty - mixed_penalty - quality_penalty - loading_penalty
    )


def _adaptive_motion_chunk_seconds(
    positions: list[int],
    items: list[dict[str, Any]],
    base_seconds: float,
) -> tuple[float, str, float]:
    """按相邻滚动重叠估计运动段密度；仅在高重叠时放宽保留跨度。"""
    if len(positions) < 2:
        return base_seconds, "base", 0.0
    matches = 0
    comparable = 0
    for previous_pos, current_pos in zip(positions, positions[1:]):
        metric = scroll_overlap_metrics(
            items[previous_pos].get("scroll_image"),
            items[current_pos].get("scroll_image"),
        )
        if not metric["matched"]:
            continue
        comparable += 1
        if float(metric["diff"]) <= 28.0 and float(metric["overlap_ratio"]) >= 0.70:
            matches += 1
    ratio = matches / float(comparable or 1)
    if comparable >= 2 and ratio >= 0.65:
        return min(4.5, base_seconds * 1.45), "scroll_redundant", ratio
    if comparable >= 2 and ratio >= 0.35:
        return min(4.0, base_seconds * 1.25), "scroll_mixed", ratio
    if comparable >= 2 and ratio <= 0.20:
        return max(1.4, base_seconds * 0.80), "content_rich", ratio
    return base_seconds, "base", ratio


def select_temporal_representatives(
    items: list[dict[str, Any]],
    *,
    stable_max_gap_seconds: float = 0.80,
    stable_pixel_diff_threshold: float = 5.0,
    stable_ssim_threshold: float = 0.965,
    transition_max_seconds: float = 1.60,
    motion_chunk_seconds: float = 2.20,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """基于前后帧选择稳定终态，返回 (保留, 丢弃, 统计)。

    输入项必须按时间排序并包含 capture_time_seconds、thumb、ssim_thumb、
    blur_score、quality 和 seam_score。函数不修改图片文件。
    """
    if not items:
        return [], [], {
            "stable_run_count": 0,
            "motion_segment_count": 0,
            "transition_drop_count": 0,
            "stable_duplicate_drop_count": 0,
            "low_confidence_selection_count": 0,
        }

    # 三帧时序证据：当前帧能由前后两页横向拼合解释，才视为高置信滑页中间态。
    mixed_transition_indices: set[int] = set()
    for idx in range(1, len(items) - 1):
        prev_time = items[idx - 1].get("capture_time_seconds")
        cur_time = items[idx].get("capture_time_seconds")
        next_time = items[idx + 1].get("capture_time_seconds")
        if prev_time is None or cur_time is None or next_time is None:
            continue
        if float(cur_time) - float(prev_time) > 1.25 or float(next_time) - float(cur_time) > 1.25:
            continue
        mix = horizontal_mixed_transition_score(
            items[idx - 1].get("transition_image"),
            items[idx].get("transition_image"),
            items[idx + 1].get("transition_image"),
        )
        items[idx]["mixed_transition_score"] = float(mix["score"])
        items[idx]["mixed_transition"] = mix
        if float(mix["score"]) >= 0.58:
            mixed_transition_indices.add(idx)

    stable_edges = [False] * len(items)
    for idx in range(1, len(items)):
        stable_edges[idx] = _temporal_pair_is_stable(
            items[idx - 1],
            items[idx],
            max_gap_seconds=stable_max_gap_seconds,
            pixel_diff_threshold=stable_pixel_diff_threshold,
            ssim_threshold=stable_ssim_threshold,
        )

    # anchor 是至少含两帧、由稳定边连接的区间。
    anchors: list[tuple[int, int]] = []
    idx = 1
    while idx < len(items):
        if not stable_edges[idx] or idx in mixed_transition_indices or idx - 1 in mixed_transition_indices:
            idx += 1
            continue
        start = idx - 1
        end = idx
        while (
            end + 1 < len(items)
            and stable_edges[end + 1]
            and end + 1 not in mixed_transition_indices
            and end not in mixed_transition_indices
        ):
            end += 1
        anchors.append((start, end))
        idx = end + 1

    selected: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    selected_indices: set[int] = set()
    dropped_indices: set[int] = set()
    stable_group_by_index: dict[int, int] = {}

    def dwell_after(pos: int) -> float:
        cur = items[pos].get("capture_time_seconds")
        nxt = items[pos + 1].get("capture_time_seconds") if pos + 1 < len(items) else None
        if cur is None or nxt is None:
            return 0.0
        return max(0.0, float(nxt) - float(cur))

    for pos in sorted(mixed_transition_indices):
        item = dict(items[pos])
        item.update({
            "drop_reason": "temporal_mixed_transition",
            "temporal_group_id": "mixed-transition",
            "selection_confidence": "high",
        })
        dropped.append(item)
        dropped_indices.add(pos)

    for group_id, (start, end) in enumerate(anchors, 1):
        for pos in range(start, end + 1):
            stable_group_by_index[pos] = group_id
        best = max(
            range(start, end + 1),
            key=lambda pos: _temporal_selection_score(
                items[pos],
                dwell_after_seconds=dwell_after(pos),
                prefer_later=(pos - start) * 0.03,
            ),
        )
        chosen = dict(items[best])
        chosen.update({
            "temporal_reason": "stable_representative",
            "temporal_group_id": f"stable-{group_id:03d}",
            "selection_confidence": "high",
        })
        selected.append(chosen)
        selected_indices.add(best)
        for pos in range(start, end + 1):
            if pos == best:
                continue
            item = dict(items[pos])
            item.update({
                "drop_reason": "temporal_stable_duplicate",
                "temporal_group_id": f"stable-{group_id:03d}",
                "selection_confidence": "high",
            })
            dropped.append(item)
            dropped_indices.add(pos)

    # 稳定段之间的非 anchor 项属于运动段。短且前后都有稳定终态时，视为切换中间态；
    # 较长运动段按固定跨度留代表帧，避免滚动或视频内容被整段吞掉。
    gaps: list[tuple[int, int, bool, bool]] = []
    cursor = 0
    for start, end in anchors:
        if cursor < start:
            gaps.append((cursor, start - 1, cursor > 0, True))
        cursor = end + 1
    if cursor < len(items):
        gaps.append((cursor, len(items) - 1, cursor > 0, False))
    if not anchors:
        gaps = [(0, len(items) - 1, False, False)]

    motion_group_count = 0
    transition_drop_count = 0
    low_confidence_count = 0
    for start, end, bounded_before, bounded_after in gaps:
        positions = [pos for pos in range(start, end + 1) if pos not in dropped_indices and pos not in selected_indices]
        if not positions:
            continue
        motion_group_count += 1
        first_time = items[positions[0]].get("capture_time_seconds")
        last_time = items[positions[-1]].get("capture_time_seconds")
        span = (
            max(0.0, float(last_time) - float(first_time))
            if first_time is not None and last_time is not None
            else float("inf")
        )
        # 单张运动候选自身的 span 为 0。改用两侧稳定锚点之间的真实时间跨度，
        # 避免把停留很久、但只采到一张的独立证据页误删为“短切换”。
        if bounded_before and bounded_after and start > 0 and end + 1 < len(items):
            before_time = items[start - 1].get("capture_time_seconds")
            after_time = items[end + 1].get("capture_time_seconds")
            if before_time is not None and after_time is not None:
                span = max(0.0, float(after_time) - float(before_time))
        group_name = f"motion-{motion_group_count:03d}"
        if bounded_before and bounded_after and span <= transition_max_seconds:
            for pos in positions:
                item = dict(items[pos])
                item.update({
                    "drop_reason": "temporal_transition",
                    "temporal_group_id": group_name,
                    "selection_confidence": "medium",
                })
                dropped.append(item)
                dropped_indices.add(pos)
                transition_drop_count += 1
            continue

        adaptive_chunk_seconds, density_mode, scroll_match_ratio = _adaptive_motion_chunk_seconds(
            positions,
            items,
            motion_chunk_seconds,
        )

        chunks: list[list[int]] = []
        chunk: list[int] = []
        chunk_start_time: float | None = None
        for pos in positions:
            cur_time = items[pos].get("capture_time_seconds")
            cur_float = float(cur_time) if cur_time is not None else None
            if (
                chunk
                and chunk_start_time is not None
                and cur_float is not None
                and cur_float - chunk_start_time > adaptive_chunk_seconds
            ):
                chunks.append(chunk)
                chunk = []
                chunk_start_time = None
            if not chunk:
                chunk_start_time = cur_float
            chunk.append(pos)
        if chunk:
            chunks.append(chunk)

        for chunk_id, chunk_positions in enumerate(chunks, 1):
            best = max(
                chunk_positions,
                key=lambda pos: _temporal_selection_score(
                    items[pos],
                    dwell_after_seconds=dwell_after(pos),
                    prefer_later=(pos - chunk_positions[0]) * 0.02,
                ),
            )
            chosen = dict(items[best])
            chosen.update({
                "temporal_reason": "motion_representative",
                "temporal_group_id": f"{group_name}-{chunk_id:02d}",
                "selection_confidence": "low",
                "adaptive_chunk_seconds": adaptive_chunk_seconds,
                "motion_density_mode": density_mode,
                "scroll_match_ratio": scroll_match_ratio,
            })
            selected.append(chosen)
            selected_indices.add(best)
            low_confidence_count += 1
            for pos in chunk_positions:
                if pos == best:
                    continue
                item = dict(items[pos])
                item.update({
                    "drop_reason": "temporal_motion_redundant",
                    "temporal_group_id": f"{group_name}-{chunk_id:02d}",
                    "selection_confidence": "low",
                })
                dropped.append(item)
                dropped_indices.add(pos)

    selected.sort(key=lambda item: (float(item.get("capture_time_seconds") or 0.0), int(item.get("source_index") or 0)))
    dropped.sort(key=lambda item: int(item.get("source_index") or 0))
    return selected, dropped, {
        "stable_run_count": len(anchors),
        "motion_segment_count": motion_group_count,
        "transition_drop_count": transition_drop_count,
        "mixed_transition_drop_count": len(mixed_transition_indices),
        "stable_duplicate_drop_count": sum(1 for item in dropped if item.get("drop_reason") == "temporal_stable_duplicate"),
        "motion_redundant_drop_count": sum(1 for item in dropped if item.get("drop_reason") == "temporal_motion_redundant"),
        "low_confidence_selection_count": low_confidence_count,
        "selected_before_dedup": len(selected),
        "adaptive_motion_group_count": sum(
            1 for item in selected if item.get("motion_density_mode") not in (None, "base")
        ),
    }


def crop_for_ocr_bytes_with_range(
    image_bytes: bytes,
    *,
    crop_top_ratio: float = 0.16,
    crop_bottom_ratio: float = 0.14,
    crop_left_ratio: float = 0.06,
    crop_right_ratio: float = 0.06,
    max_width: int = 720,
) -> tuple[bytes, int]:
    if not image_bytes:
        return (b"", 0)
    img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size
    if w <= 0 or h <= 0:
        return (b"", 0)

    top = int(max(0, min(h - 1, round(h * crop_top_ratio))))
    bottom_cut = int(max(0, min(h - 1, round(h * crop_bottom_ratio))))
    bottom = max(top + 1, h - bottom_cut)
    left = int(max(0, min(w - 1, round(w * crop_left_ratio))))
    right_cut = int(max(0, min(w - 1, round(w * crop_right_ratio))))
    right = max(left + 1, w - right_cut)
    img = img.crop((left, top, right, bottom))

    if max_width and img.size[0] > max_width:
        new_w = int(max_width)
        new_h = round(img.size[1] * (new_w / float(img.size[0])))
        img = img.resize((new_w, max(1, new_h)), _LANCZOS)

    img = img.convert("L")
    img = ImageOps.autocontrast(img)
    img = ImageEnhance.Contrast(img).enhance(1.35)
    img = ImageEnhance.Sharpness(img).enhance(1.15)

    dynamic_range = 0
    try:
        extrema = img.getextrema()
        if isinstance(extrema, tuple) and len(extrema) == 2:
            lo_val, hi_val = extrema
            if isinstance(lo_val, (int, float)) and isinstance(hi_val, (int, float)):
                dynamic_range = int(hi_val) - int(lo_val)
    except Exception:
        pass

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return (buf.getvalue(), max(0, dynamic_range))


# ======================================================================
# C. 去重逻辑
# ======================================================================


def shingles(s: str, n: int = 3) -> set[str]:
    s = s or ""
    if not s:
        return set()
    if len(s) <= n:
        return {s}
    return {s[i : i + n] for i in range(0, len(s) - n + 1)}


def jaccard_sets(sa: set[str], sb: set[str]) -> float:
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return float(inter) / float(union) if union else 0.0


@dataclass
class ExtractParams:
    interval_seconds: float = 1.0
    strategy: str = "scene"
    dedup_threshold: int = 8
    ocr_similarity_threshold: float = 0.92
    ocr_min_new_chars: int = 8
    content_crop_top: float = 0.12
    content_crop_bottom: float = 0.12
    content_crop_left: float = 0.04
    content_crop_right: float = 0.04
    ssim_threshold: float = 0.93
    scroll_merge: bool = True
    scroll_diff_threshold: float = 32.0


@dataclass
class DedupState:
    seen_sha256: set[str] = field(default_factory=set)
    kept_dhashes: list[str] = field(default_factory=list)
    kept_thumbs: list[bytes] = field(default_factory=list)
    kept_ssim_thumbs: list[bytes] = field(default_factory=list)
    kept_scroll_images: list[Image.Image] = field(default_factory=list)
    kept_ocr_texts: list[str] = field(default_factory=list)
    kept_ocr_shingles: list[set[str]] = field(default_factory=list)
    sha256_dups: int = 0
    dhash_dups: int = 0
    pixel_dups: int = 0
    ssim_dups: int = 0
    scroll_dups: int = 0
    ocr_dups: int = 0
    blur_drops: int = 0
    quality_drops: int = 0
    min_gap_drops: int = 0
    temporal_drops: int = 0
    temporal_transition_drops: int = 0
    transient_ui_drops: int = 0
    ocr_visual_overrides: int = 0
    kept_count: int = 0
    total_count: int = 0


def is_dhash_duplicate(
    dhash_hex: str,
    kept_dhashes: list[str],
    window: int,
    threshold: int,
) -> bool:
    for prev in kept_dhashes[-window:]:
        dist = hamming_distance_hex(prev, dhash_hex)
        if dist is not None and dist <= threshold:
            return True
    return False


def is_pixel_duplicate(
    thumb: bytes,
    kept_thumbs: list[bytes],
    window: int,
    threshold: float,
) -> bool:
    for prev_thumb in kept_thumbs[-window:]:
        diff = mean_abs_diff(prev_thumb, thumb)
        if diff is not None and diff <= threshold:
            return True
    return False


def is_ssim_duplicate(
    thumb: bytes,
    kept_thumbs: list[bytes],
    window: int,
    threshold: float,
) -> bool:
    for prev_thumb in kept_thumbs[-window:]:
        sim = ssim_bytes(prev_thumb, thumb)
        if sim is not None and sim >= threshold:
            return True
    return False


def check_ocr_similarity(
    ocr_text: str,
    kept_ocr_texts: list[str],
    kept_ocr_shingles: list[set[str]],
    ocr_similarity_threshold: float,
    ocr_min_new_chars: int,
) -> bool:
    """检查 OCR 文本是否与最近帧重复，返回 True 表示重复应跳过。"""
    return bool(ocr_content_delta(
        ocr_text,
        kept_ocr_texts,
        kept_ocr_shingles,
        ocr_similarity_threshold,
        ocr_min_new_chars,
    )["redundant"])


def ocr_content_delta(
    ocr_text: str,
    kept_ocr_texts: list[str],
    kept_ocr_shingles: list[set[str]],
    ocr_similarity_threshold: float,
    ocr_min_new_chars: int,
) -> dict[str, Any]:
    """比较最近 OCR 内容，返回可报告的增量指标；不保存原文到报告。"""
    cur_set = shingles(ocr_text)
    # 排除视频时间码、状态栏时钟等 1—2 位易变数字；金额或至少 3 位的
    # 连续编号才作为潜在证据数字，避免 OCR 把每秒变化误判为内容增量。
    evidence_number_pattern = r"(?:￥|¥)\s*\d[\d,.]*|(?<![\d:])\d{3,}(?:[,.]\d+)?(?![\d:])"
    current_numbers = set(re.findall(evidence_number_pattern, ocr_text or ""))
    if not ocr_text or not kept_ocr_texts:
        return {
            "available": bool(ocr_text),
            "similarity": 0.0,
            "new_token_count": len(cur_set),
            "new_numeric_count": len(current_numbers),
            "redundant": False,
            "has_new_content": bool(cur_set or current_numbers),
            "protect_visual_duplicate": False,
        }
    best_similarity = 0.0
    min_new_tokens = len(cur_set)
    recent_numbers: set[str] = set()
    for prev_text, prev_set in zip(
        kept_ocr_texts[-4:],
        kept_ocr_shingles[-4:],
    ):
        if not prev_text:
            continue
        seq_sim = float(SequenceMatcher(None, prev_text, ocr_text).ratio())
        jac_sim = jaccard_sets(prev_set, cur_set)
        sim = max(seq_sim, jac_sim)
        new_tokens = len(cur_set - prev_set) if prev_set else len(cur_set)
        best_similarity = max(best_similarity, sim)
        min_new_tokens = min(min_new_tokens, new_tokens)
        recent_numbers.update(re.findall(evidence_number_pattern, prev_text or ""))
    new_numbers = current_numbers - recent_numbers
    has_new_content = min_new_tokens >= ocr_min_new_chars or bool(new_numbers)
    redundant = best_similarity >= ocr_similarity_threshold and not has_new_content
    protect_visual_duplicate = (
        (bool(new_numbers) and best_similarity >= 0.72)
        or (
            best_similarity >= 0.82
            and min_new_tokens >= max(16, ocr_min_new_chars * 2)
        )
    )
    return {
        "available": True,
        "similarity": best_similarity,
        "new_token_count": min_new_tokens,
        "new_numeric_count": len(new_numbers),
        "redundant": redundant,
        "has_new_content": has_new_content,
        "protect_visual_duplicate": protect_visual_duplicate,
    }


def is_frame_duplicate(
    content: bytes,
    digest: str,
    dhash_hex: str,
    state: DedupState,
    params: ExtractParams,
    window: int = 20,
    pixel_diff_threshold: float = 8.0,
) -> tuple[bool, str, bytes, bytes, Image.Image | None]:
    """图像层级去重，返回 (is_dup, reason, pixel_thumb, ssim_thumb, scroll_image)。"""
    if digest in state.seen_sha256:
        state.sha256_dups += 1
        return True, "duplicate_sha256", b"", b"", None

    if (
        params.dedup_threshold
        and state.kept_dhashes
        and is_dhash_duplicate(dhash_hex, state.kept_dhashes, window, params.dedup_threshold)
    ):
        state.dhash_dups += 1
        return True, "duplicate_dhash", b"", b"", None

    thumb = b""
    if pixel_diff_threshold and state.kept_thumbs:
        thumb = calc_thumb_bytes(
            content,
            crop_top_ratio=params.content_crop_top,
            crop_bottom_ratio=params.content_crop_bottom,
            crop_left_ratio=params.content_crop_left,
            crop_right_ratio=params.content_crop_right,
        )
        if thumb and is_pixel_duplicate(thumb, state.kept_thumbs, window, pixel_diff_threshold):
            state.pixel_dups += 1
            return True, "duplicate_pixel", thumb, b"", None

    ssim_thumb = b""
    if params.ssim_threshold and params.ssim_threshold > 0 and state.kept_ssim_thumbs:
        ssim_thumb = calc_thumb_bytes(
            content,
            size=32,
            crop_top_ratio=params.content_crop_top,
            crop_bottom_ratio=params.content_crop_bottom,
            crop_left_ratio=params.content_crop_left,
            crop_right_ratio=params.content_crop_right,
            autocontrast=True,
        )
        if ssim_thumb and is_ssim_duplicate(ssim_thumb, state.kept_ssim_thumbs, window, params.ssim_threshold):
            state.ssim_dups += 1
            return True, "duplicate_ssim", thumb, ssim_thumb, None

    scroll_image = None
    if params.scroll_merge and params.scroll_diff_threshold > 0 and state.kept_scroll_images:
        scroll_image = calc_scroll_image(
            content,
            crop_top_ratio=params.content_crop_top,
            crop_bottom_ratio=params.content_crop_bottom,
            crop_left_ratio=params.content_crop_left,
            crop_right_ratio=params.content_crop_right,
        )
        if scroll_image and scroll_overlap_duplicate(
            scroll_image,
            state.kept_scroll_images[-8:],
            threshold=params.scroll_diff_threshold,
        ):
            state.scroll_dups += 1
            return True, "duplicate_scroll", thumb, ssim_thumb, scroll_image

    return False, "", thumb, ssim_thumb, scroll_image


def calc_capture_time(
    path: str,
    index: int,
    params: ExtractParams,
    info: FFProbeInfo,
) -> float | None:
    interval_based = params.strategy in ("interval",)
    if not interval_based and (info.time_base_seconds or info.frame_rate_fps):
        m = re.search(r"(\d+)", Path(path).name)
        if not m:
            return None
        pts = int(m.group(1))
        if info.frame_rate_fps and info.frame_rate_fps > 0:
            fps_time = float(pts) / float(info.frame_rate_fps)
            if 0 <= fps_time <= info.duration_seconds * 1.1:
                return fps_time
        return float(pts * float(info.time_base_seconds)) if info.time_base_seconds else None
    return float(index - 1) * float(params.interval_seconds)


def collect_frame_files(tmpdir: str) -> list[str]:
    frame_files = [
        str(Path(tmpdir) / f.name)
        for f in Path(tmpdir).iterdir()
        if f.name.lower().endswith((".jpg", ".jpeg", ".png"))
    ]
    frame_files.sort()
    return frame_files


# ======================================================================
# D. OCR 集成
# ======================================================================

_ocr_engine = None


def create_ocr_engine():
    """创建本地 RapidOCR 引擎（懒加载单例）。"""
    global _ocr_engine
    if _ocr_engine is not None:
        return _ocr_engine
    try:
        from rapidocr_onnxruntime import RapidOCR
        _ocr_engine = RapidOCR()
        return _ocr_engine
    except ImportError:
        logger.warning(
            "rapidocr-onnxruntime 未安装，OCR 内容增量不可用。"
            "运行方式: uv run --with rapidocr-onnxruntime scripts/extract.py ... --ocr-dedup"
        )
        return None


def ocr_extract_text(ocr_engine: Any, image_bytes: bytes) -> str:
    """调用 OCR 提取文本。"""
    if ocr_engine is None:
        return ""
    try:
        result, _ = ocr_engine(image_bytes)
        if result:
            texts: list[str] = []
            for line in result:
                # RapidOCR 行结构是 [box, text, confidence]；旧实现取 line[-1]
                # 实际拼接了置信度数字，导致 OCR 去重几乎失效。
                if isinstance(line, (list, tuple)) and len(line) >= 2:
                    text = str(line[1] or "").strip()
                    if text:
                        texts.append(text)
            return "|".join(texts)
    except Exception:
        logger.debug("OCR 识别失败", exc_info=True)
    return ""
