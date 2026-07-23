#!/usr/bin/env python3
"""Compress generated article images in place.

The default target is optimized for image-host uploads:
- try to reach about 200 KB per image
- require every output to stay under 500 KB unless explicitly changed
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def collect_images(paths: list[str]) -> list[Path]:
    images: list[Path] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if path.is_dir():
            images.extend(
                p
                for p in sorted(path.rglob("*"))
                if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
            )
        elif path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            images.append(path)
        else:
            print(f"skip non-image path: {path}", file=sys.stderr)
    return images


def require_tool(name: str) -> str:
    tool = shutil.which(name)
    if not tool:
        print(f"Missing dependency: {name}", file=sys.stderr)
        if name == "pngquant":
            print("Install it with: brew install pngquant", file=sys.stderr)
        elif name == "magick":
            print("Install it with: brew install imagemagick", file=sys.stderr)
        raise SystemExit(1)
    return tool


def run_pngquant(src: Path, dst: Path, *, quality_min: int, quality_max: int) -> bool:
    pngquant = require_tool("pngquant")
    command = [
        pngquant,
        "--force",
        "--strip",
        "--speed",
        "1",
        "--quality",
        f"{quality_min}-{quality_max}",
        "--output",
        str(dst),
        str(src),
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.returncode == 0 and dst.exists()


def run_magick_resize(src: Path, dst: Path, *, scale_percent: int) -> None:
    magick = require_tool("magick")
    command = [
        magick,
        str(src),
        "-strip",
        "-resize",
        f"{scale_percent}%",
        str(dst),
    ]
    subprocess.check_call(command)


def compress_png(path: Path, *, target_kb: int, max_kb: int, allow_resize: bool) -> tuple[int, int]:
    original_size = path.stat().st_size
    best_file: Path | None = None
    best_size = original_size

    quality_ranges = [(55, 85), (45, 80), (35, 75), (25, 70), (15, 65)]
    with tempfile.TemporaryDirectory() as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        for quality_min, quality_max in quality_ranges:
            candidate = temp_dir / f"{path.stem}_{quality_min}_{quality_max}.png"
            if not run_pngquant(path, candidate, quality_min=quality_min, quality_max=quality_max):
                continue
            size = candidate.stat().st_size
            if size < best_size:
                best_file = candidate
                best_size = size
            if size <= target_kb * 1024:
                shutil.copy2(candidate, path)
                return original_size, size

        if best_file and best_size <= max_kb * 1024:
            shutil.copy2(best_file, path)
            return original_size, best_size

        if not allow_resize:
            if best_file:
                shutil.copy2(best_file, path)
            return original_size, best_size

        current = best_file or path
        for scale in (90, 82, 75, 68, 60):
            resized = temp_dir / f"{path.stem}_resized_{scale}.png"
            run_magick_resize(current, resized, scale_percent=scale)
            quantized = temp_dir / f"{path.stem}_resized_{scale}_quant.png"
            if run_pngquant(resized, quantized, quality_min=25, quality_max=75):
                size = quantized.stat().st_size
                if size < best_size:
                    best_file = quantized
                    best_size = size
                if size <= max_kb * 1024:
                    shutil.copy2(quantized, path)
                    return original_size, size

        if best_file:
            shutil.copy2(best_file, path)
        return original_size, best_size


def compress_non_png(path: Path, *, target_kb: int, max_kb: int, allow_resize: bool) -> tuple[int, int]:
    original_size = path.stat().st_size
    magick = require_tool("magick")
    with tempfile.TemporaryDirectory() as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        best = path
        best_size = original_size
        for quality in (82, 74, 66, 58, 50):
            candidate = temp_dir / path.name
            subprocess.check_call([magick, str(path), "-strip", "-quality", str(quality), str(candidate)])
            size = candidate.stat().st_size
            if size < best_size:
                best = candidate
                best_size = size
            if size <= target_kb * 1024:
                shutil.copy2(candidate, path)
                return original_size, size
        if best_size <= max_kb * 1024 or not allow_resize:
            shutil.copy2(best, path)
            return original_size, best_size
        for scale in (90, 82, 75, 68, 60):
            candidate = temp_dir / f"{path.stem}_{scale}{path.suffix}"
            subprocess.check_call(
                [magick, str(best), "-strip", "-resize", f"{scale}%", "-quality", "66", str(candidate)]
            )
            size = candidate.stat().st_size
            if size <= max_kb * 1024:
                shutil.copy2(candidate, path)
                return original_size, size
        shutil.copy2(best, path)
        return original_size, best_size


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", help="Image files or directories to compress in place.")
    parser.add_argument("--target-kb", type=int, default=200, help="Preferred size target per image.")
    parser.add_argument("--max-kb", type=int, default=500, help="Required maximum size per image.")
    parser.add_argument("--allow-resize", action="store_true", help="Resize images only if compression cannot hit max-kb.")
    args = parser.parse_args()

    if args.target_kb <= 0 or args.max_kb <= 0:
        raise SystemExit("target-kb and max-kb must be positive")
    if args.target_kb > args.max_kb:
        raise SystemExit("target-kb must be less than or equal to max-kb")

    images = collect_images(args.paths)
    if not images:
        raise SystemExit("No images found")

    failed: list[Path] = []
    for image in images:
        if image.suffix.lower() == ".png":
            before, after = compress_png(
                image,
                target_kb=args.target_kb,
                max_kb=args.max_kb,
                allow_resize=args.allow_resize,
            )
        else:
            before, after = compress_non_png(
                image,
                target_kb=args.target_kb,
                max_kb=args.max_kb,
                allow_resize=args.allow_resize,
            )
        status = "OK" if after <= args.max_kb * 1024 else "TOO_BIG"
        if status != "OK":
            failed.append(image)
        print(f"{status} {before / 1024:.1f}KB -> {after / 1024:.1f}KB {image}")

    if failed:
        print("Some images are still above the maximum size:", file=sys.stderr)
        for image in failed:
            print(f"- {image}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
