"""video-screenshot 共享工具函数。

从 fachuan chat_records/services/ 移植，去除 Django 依赖。
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import re
import select
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, cast

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps, ImageStat

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
    ssim_threshold: float = 0.70
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
    if not ocr_text or not kept_ocr_texts:
        return False
    cur_set = shingles(ocr_text)
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
        if sim >= ocr_similarity_threshold and new_tokens < ocr_min_new_chars:
            return True
    return False


def is_frame_duplicate(
    content: bytes,
    digest: str,
    dhash_hex: str,
    state: DedupState,
    params: ExtractParams,
    window: int = 20,
    pixel_diff_threshold: float = 8.0,
) -> tuple[bool, bytes, bytes, Image.Image | None]:
    """图像层级去重，返回 (is_dup, pixel_thumb, ssim_thumb, scroll_image)。"""
    if digest in state.seen_sha256:
        state.sha256_dups += 1
        return True, b"", b"", None

    if (
        params.dedup_threshold
        and state.kept_dhashes
        and is_dhash_duplicate(dhash_hex, state.kept_dhashes, window, params.dedup_threshold)
    ):
        state.dhash_dups += 1
        return True, b"", b"", None

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
            return True, thumb, b"", None

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
            return True, thumb, ssim_thumb, None

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
            return True, thumb, ssim_thumb, scroll_image

    return False, thumb, ssim_thumb, scroll_image


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
            "rapidocr-onnxruntime 未安装，OCR 去重不可用。"
            "安装方式: pip install rapidocr-onnxruntime"
        )
        return None


def ocr_extract_text(ocr_engine: Any, image_bytes: bytes) -> str:
    """调用 OCR 提取文本。"""
    if ocr_engine is None:
        return ""
    try:
        result, _ = ocr_engine(image_bytes)
        if result:
            return "|".join(line[-1] for line in result)
    except Exception:
        logger.debug("OCR 识别失败", exc_info=True)
    return ""
