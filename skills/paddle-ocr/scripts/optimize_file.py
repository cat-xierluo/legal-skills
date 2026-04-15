#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "Pillow>=10.0.0",
# ]
# ///

"""扫描图片压缩工具，适合先压缩后做 OCR。"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image

DEFAULT_QUALITY = 85
DEFAULT_TARGET_MB = 20.0
SUPPORTED_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp")


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1 or parsed > 100:
        raise argparse.ArgumentTypeError("quality 必须在 1-100 之间")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("target-size 必须大于 0")
    return parsed


def optimize_image(input_path: Path, output_path: Path, quality: int, target_mb: float) -> None:
    image = Image.open(input_path)
    original_size = input_path.stat().st_size / 1024 / 1024
    print(f"原始大小：{original_size:.2f} MB")
    print(f"原始尺寸：{image.size[0]}x{image.size[1]}")

    is_jpeg_like = output_path.suffix.lower() in {".jpg", ".jpeg", ".webp"}
    if is_jpeg_like and image.mode in {"RGBA", "LA", "P"}:
        background = Image.new("RGB", image.size, (255, 255, 255))
        if image.mode == "P":
            image = image.convert("RGBA")
        background.paste(image, mask=image.split()[-1] if image.mode in {"RGBA", "LA"} else None)
        image = background

    save_kwargs = {"optimize": True}
    if is_jpeg_like:
        save_kwargs["quality"] = quality

    def save_current(current_image: Image.Image) -> float:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        current_image.save(output_path, **save_kwargs)
        return output_path.stat().st_size / 1024 / 1024

    current_size = save_current(image)
    scale_factor = 0.9
    while current_size > target_mb and scale_factor >= 0.4:
        width = max(1, int(image.size[0] * scale_factor))
        height = max(1, int(image.size[1] * scale_factor))
        resized = image.resize((width, height), Image.Resampling.LANCZOS)
        current_size = save_current(resized)
        print(f"调整后尺寸：{width}x{height}，大小：{current_size:.2f} MB")
        scale_factor -= 0.1

    print(f"优化后大小：{current_size:.2f} MB")
    print(f"已输出：{output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="压缩 OCR 输入图片")
    parser.add_argument("input", help="输入图片")
    parser.add_argument("output", help="输出图片")
    parser.add_argument("--quality", type=positive_int, default=DEFAULT_QUALITY)
    parser.add_argument("--target-size", type=positive_float, default=DEFAULT_TARGET_MB)
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    if not input_path.exists():
        print(f"错误：文件不存在：{input_path}")
        return 1
    if input_path.suffix.lower() not in SUPPORTED_SUFFIXES:
        print(f"错误：不支持的图片格式：{input_path.suffix.lower()}")
        return 1

    optimize_image(input_path, output_path, args.quality, args.target_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
