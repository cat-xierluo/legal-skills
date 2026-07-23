#!/usr/bin/env python3
"""Deterministically render hand-drawn article illustration sketches.

This renderer creates composition previews for this skill. Built-in image
generation is the production route, while this script guarantees a local
contract for planning: no readable text, fixed accent color, large subject
occupancy, and consistent object-card geometry.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Missing dependency: pillow")
    print("Install it with: python3 -m pip install -r scripts/requirements.txt")
    raise SystemExit(1)


PAPER = (250, 249, 245)
SURFACE = (245, 244, 237)
SURFACE_2 = (240, 238, 230)
INK = (20, 20, 19)
GUIDE = (218, 216, 205)
DEFAULT_ACCENT = (67, 92, 104)
SS = 3
INK_WEIGHT = 1.55


SUBJECT_BOUNDS = {
    "browser_window": (700, 390),
    "timeline": (860, 300),
    "bridge": (850, 330),
    "folder": (700, 350),
    "magnifier": (840, 430),
    "gate": (820, 360),
    "building_blocks": (620, 360),
    "radar": (760, 430),
    "network": (780, 470),
    "dashboard": (740, 370),
    "evidence_box": (700, 350),
    "funnel": (900, 390),
    "broadcast": (900, 420),
    "prism": (850, 360),
    "maze": (760, 430),
    "flywheel": (760, 470),
    "scaffold": (760, 430),
    "compass_map": (760, 440),
    "sample_tray": (760, 360),
    "balance": (760, 360),
}


SUBJECT_SCALE_BIAS = {
    "browser_window": 1.08,
    "folder": 1.04,
    "building_blocks": 1.10,
    "radar": 1.08,
    "funnel": 1.05,
    "broadcast": 1.04,
    "flywheel": 1.06,
    "sample_tray": 1.08,
}


def hex_to_rgb(value: str, fallback: tuple[int, int, int] = DEFAULT_ACCENT) -> tuple[int, int, int]:
    raw = str(value or "").strip().lstrip("#")
    if len(raw) != 6:
        return fallback
    try:
        return tuple(int(raw[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return fallback


def parse_size(value: str) -> tuple[int, int]:
    try:
        width, height = str(value).lower().split("x", 1)
        return int(width), int(height)
    except ValueError as exc:
        raise SystemExit(f"Invalid size: {value}. Use WIDTHxHEIGHT, for example 1664x928") from exc


def safe_name(value: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|]+", "-", str(value)).strip()
    value = re.sub(r"\s+", "_", value)
    return value[:80] or "illustration"


def sc(value: float) -> int:
    return int(round(value * SS))


def ink_width(width: int, fill: tuple[int, int, int]) -> int:
    if width <= 0:
        return 0
    if fill == GUIDE:
        return max(1, round(width * 1.18))
    if fill == INK:
        return max(1, round(width * INK_WEIGHT))
    return width


def resolve_subject_scale(metaphor: str, target: str, canvas_width: int, canvas_height: int) -> float:
    base_width, base_height = SUBJECT_BOUNDS.get(metaphor, SUBJECT_BOUNDS["dashboard"])
    if target == "cover":
        target_width, target_height = 0.68, 0.72
    elif target == "card":
        target_width, target_height = 0.74, 0.76
    else:
        target_width, target_height = 0.64, 0.74

    scale = min(
        (canvas_width * target_width) / base_width,
        (canvas_height * target_height) / base_height,
    )
    scale *= SUBJECT_SCALE_BIAS.get(metaphor, 1.0)

    max_scale = min(
        (canvas_width * 0.82) / base_width,
        (canvas_height * 0.84) / base_height,
    )
    return min(scale, max_scale)


def draw_line(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[float, float]],
    *,
    fill: tuple[int, int, int] = INK,
    width: int = 5,
    taper: bool = True,
    anchor: bool = False,
) -> None:
    if len(points) < 2:
        return
    base_width = ink_width(width, fill)
    if base_width <= 0:
        return

    scaled = [tuple(map(sc, point)) for point in points]
    draw.line(scaled, fill=fill, width=sc(base_width), joint="curve")
    if anchor:
        anchor_points = [points[0], points[-1], *points[1:-1]]
        for x, y in (tuple(map(sc, point)) for point in anchor_points):
            radius = sc(max(2, base_width * 0.48))
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)


def draw_detail_line(
    draw: ImageDraw.ImageDraw,
    rng: random.Random,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    *,
    fill: tuple[int, int, int] = GUIDE,
    width: int = 2,
) -> None:
    mx = (x0 + x1) / 2 + rng.uniform(-1.4, 1.4)
    my = (y0 + y1) / 2 + rng.uniform(-1.4, 1.4)
    draw_line(draw, [(x0, y0), (mx, my), (x1, y1)], fill=fill, width=width, taper=True)


def draw_poly(
    draw: ImageDraw.ImageDraw,
    rng: random.Random,
    points: list[tuple[float, float]],
    *,
    fill: tuple[int, int, int] | None = SURFACE,
    outline: tuple[int, int, int] = INK,
    width: int = 5,
    pressure_edges: tuple[int, ...] = (0, 2),
) -> None:
    scaled = [(sc(x), sc(y)) for x, y in points]
    if fill is not None:
        draw.polygon(scaled, fill=fill)
    total = len(points)
    for index in range(total):
        a = points[index]
        b = points[(index + 1) % total]
        mx = (a[0] + b[0]) / 2 + rng.uniform(-2.2, 2.2)
        my = (a[1] + b[1]) / 2 + rng.uniform(-2.2, 2.2)
        local_width = width + (2 if index in pressure_edges else 0)
        draw_line(draw, [a, (mx, my), b], fill=outline, width=local_width, taper=True, anchor=index in pressure_edges)


def draw_rect(
    draw: ImageDraw.ImageDraw,
    rng: random.Random,
    box: tuple[float, float, float, float],
    *,
    fill: tuple[int, int, int] | None = SURFACE,
    outline: tuple[int, int, int] = INK,
    width: int = 5,
    pressure: str = "tlbr",
) -> None:
    x0, y0, x1, y1 = box
    points = [
        (x0 + rng.uniform(-2, 2), y0 + rng.uniform(-1, 2)),
        (x1 + rng.uniform(-2, 2), y0 + rng.uniform(-2, 1)),
        (x1 + rng.uniform(-1, 2), y1 + rng.uniform(-2, 2)),
        (x0 + rng.uniform(-2, 1), y1 + rng.uniform(-1, 2)),
    ]
    pressure_edges: list[int] = []
    if "t" in pressure:
        pressure_edges.append(0)
    if "r" in pressure:
        pressure_edges.append(1)
    if "b" in pressure:
        pressure_edges.append(2)
    if "l" in pressure:
        pressure_edges.append(3)
    draw_poly(draw, rng, points, fill=fill, outline=outline, width=width, pressure_edges=tuple(pressure_edges))


def draw_circle(
    draw: ImageDraw.ImageDraw,
    rng: random.Random,
    cx: float,
    cy: float,
    radius: float,
    *,
    fill: tuple[int, int, int] | None = SURFACE,
    outline: tuple[int, int, int] = INK,
    width: int = 5,
) -> None:
    points = []
    for index in range(32):
        angle = math.tau * index / 32
        local_radius = radius + math.sin(angle * 3.0) * 1.3 + rng.uniform(-0.7, 0.7)
        points.append((cx + math.cos(angle) * local_radius, cy + math.sin(angle) * local_radius))
    draw_poly(draw, rng, points, fill=fill, outline=outline, width=width, pressure_edges=(3, 12, 23))


def draw_blob(
    draw: ImageDraw.ImageDraw,
    rng: random.Random,
    cx: float,
    cy: float,
    radius_x: float,
    radius_y: float,
    *,
    fill: tuple[int, int, int] | None = SURFACE,
    outline: tuple[int, int, int] = INK,
    width: int = 5,
) -> None:
    points = []
    for index in range(18):
        angle = math.tau * index / 18
        wobble = 1.0 + math.sin(angle * 2.7) * 0.06 + rng.uniform(-0.035, 0.035)
        points.append((cx + math.cos(angle) * radius_x * wobble, cy + math.sin(angle) * radius_y * wobble))
    draw_poly(draw, rng, points, fill=fill, outline=outline, width=width, pressure_edges=(2, 8, 14))


def draw_arc(
    draw: ImageDraw.ImageDraw,
    box: tuple[float, float, float, float],
    start: float,
    end: float,
    *,
    fill: tuple[int, int, int] = INK,
    width: int = 5,
) -> None:
    x0, y0, x1, y1 = box
    draw.arc((sc(x0), sc(y0), sc(x1), sc(y1)), start=start, end=end, fill=fill, width=sc(ink_width(width, fill)))


def draw_browser(draw: ImageDraw.ImageDraw, rng: random.Random, cx: float, cy: float, scale: float, accent: tuple[int, int, int]) -> None:
    width, height = 620 * scale, 365 * scale
    x0, y0 = cx - width / 2, cy - height / 2
    draw_rect(draw, rng, (x0, y0, x0 + width, y0 + height), width=6)
    draw_detail_line(draw, rng, x0 + 30 * scale, y0 + 68 * scale, x0 + width - 28 * scale, y0 + 68 * scale, fill=INK, width=4)
    for index in range(3):
        x = x0 + (30 + 34 * index) * scale
        draw_detail_line(draw, rng, x, y0 + 34 * scale, x + 16 * scale, y0 + 34 * scale, fill=INK, width=2)
    for index in range(4):
        y = y0 + (118 + index * 52) * scale
        draw_detail_line(draw, rng, x0 + 70 * scale, y, x0 + width - 95 * scale, y, width=2)
    draw_rect(draw, rng, (x0 + 155 * scale, y0 + 125 * scale, x0 + 335 * scale, y0 + 177 * scale), fill=accent, width=5, pressure="tr")
    draw_rect(draw, rng, (x0 + width - 88 * scale, y0 + height - 93 * scale, x0 + width + 58 * scale, y0 + height - 24 * scale), fill=SURFACE_2, width=5, pressure="br")


def draw_timeline(draw: ImageDraw.ImageDraw, rng: random.Random, cx: float, cy: float, scale: float, accent: tuple[int, int, int]) -> None:
    x0, x1, y = cx - 430 * scale, cx + 430 * scale, cy
    draw_line(draw, [(x0, y), (cx - 120 * scale, y + 2 * scale), (cx + 150 * scale, y - scale), (x1, y)], width=5)
    for index in range(6):
        x = x0 + index * (x1 - x0) / 5
        draw_circle(draw, rng, x, y, 21 * scale, fill=PAPER, width=4)
    draw_circle(draw, rng, x1, y, 21 * scale, fill=accent, width=4)
    for offset in (-315, -60, 210):
        draw_rect(draw, rng, (cx + offset * scale, cy - 118 * scale, cx + (offset + 125) * scale, cy - 64 * scale), width=4, pressure="tr")
    for offset in (-360, -70, 245):
        draw_rect(draw, rng, (cx + offset * scale, cy + 70 * scale, cx + (offset + 125) * scale, cy + 126 * scale), width=4, pressure="lb")


def draw_bridge(draw: ImageDraw.ImageDraw, rng: random.Random, cx: float, cy: float, scale: float, accent: tuple[int, int, int]) -> None:
    draw_rect(draw, rng, (cx - 425 * scale, cy - 95 * scale, cx - 280 * scale, cy + 95 * scale), width=5, pressure="tl")
    draw_rect(draw, rng, (cx + 280 * scale, cy - 95 * scale, cx + 425 * scale, cy + 95 * scale), width=5, pressure="br")
    draw_line(draw, [(cx - 280 * scale, cy - 70 * scale), (cx - 110 * scale, cy - 155 * scale), (cx + 110 * scale, cy - 155 * scale), (cx + 280 * scale, cy - 70 * scale)], width=5)
    draw_line(draw, [(cx - 280 * scale, cy + 70 * scale), (cx - 110 * scale, cy + 155 * scale), (cx + 110 * scale, cy + 155 * scale), (cx + 280 * scale, cy + 70 * scale)], width=5)
    draw_rect(draw, rng, (cx - 85 * scale, cy - 130 * scale, cx + 85 * scale, cy - 72 * scale), fill=accent, width=5, pressure="tr")
    draw_rect(draw, rng, (cx - 58 * scale, cy + 60 * scale, cx + 58 * scale, cy + 116 * scale), width=4, pressure="b")


def draw_folder(draw: ImageDraw.ImageDraw, rng: random.Random, cx: float, cy: float, scale: float, accent: tuple[int, int, int]) -> None:
    x0, y0 = cx - 345 * scale, cy - 150 * scale
    points = [
        (x0, y0 + 52 * scale),
        (x0 + 118 * scale, y0 + 52 * scale),
        (x0 + 152 * scale, y0),
        (x0 + 350 * scale, y0),
        (x0 + 385 * scale, y0 + 52 * scale),
        (x0 + 690 * scale, y0 + 52 * scale),
        (x0 + 690 * scale, y0 + 295 * scale),
        (x0, y0 + 295 * scale),
    ]
    draw_poly(draw, rng, points, width=6, pressure_edges=(0, 2, 6))
    for index in range(3):
        draw_rect(draw, rng, (x0 + 90 * scale, y0 + (105 + index * 58) * scale, x0 + 500 * scale, y0 + (145 + index * 58) * scale), fill=PAPER, width=4, pressure="r")
    draw_rect(draw, rng, (x0 + 435 * scale, y0 + 100 * scale, x0 + 535 * scale, y0 + 147 * scale), fill=accent, width=4, pressure="tr")


def draw_magnifier(draw: ImageDraw.ImageDraw, rng: random.Random, cx: float, cy: float, scale: float, accent: tuple[int, int, int]) -> None:
    draw_rect(draw, rng, (cx - 410 * scale, cy - 165 * scale, cx + 410 * scale, cy + 165 * scale), width=6)
    for index in range(5):
        x = cx - 360 * scale + index * 170 * scale
        draw_detail_line(draw, rng, x, cy - 132 * scale, x, cy + 132 * scale, fill=GUIDE, width=3)
    for index in range(5):
        y = cy - 125 * scale + index * 62 * scale
        draw_detail_line(draw, rng, cx - 380 * scale, y, cx + 380 * scale, y, fill=GUIDE, width=3)
    draw_rect(draw, rng, (cx - 120 * scale, cy - 62 * scale, cx + 15 * scale, cy + 70 * scale), fill=accent, width=0)
    draw_circle(draw, rng, cx - 20 * scale, cy - 8 * scale, 152 * scale, fill=(236, 247, 248), width=9)
    draw_circle(draw, rng, cx - 60 * scale, cy - 35 * scale, 48 * scale, fill=PAPER, width=4)
    draw_line(draw, [(cx + 108 * scale, cy + 105 * scale), (cx + 210 * scale, cy + 200 * scale), (cx + 258 * scale, cy + 244 * scale)], width=8)


def draw_gate(draw: ImageDraw.ImageDraw, rng: random.Random, cx: float, cy: float, scale: float, accent: tuple[int, int, int]) -> None:
    draw_rect(draw, rng, (cx - 82 * scale, cy - 178 * scale, cx + 82 * scale, cy + 178 * scale), width=6)
    draw_rect(draw, rng, (cx - 45 * scale, cy - 128 * scale, cx + 45 * scale, cy + 128 * scale), fill=accent, width=5, pressure="r")
    for yy in (-115, 0, 98):
        draw_rect(draw, rng, (cx - 390 * scale, cy + yy * scale - 27 * scale, cx - 250 * scale, cy + yy * scale + 27 * scale), width=4, pressure="l")
    draw_rect(draw, rng, (cx + 260 * scale, cy - 35 * scale, cx + 410 * scale, cy + 35 * scale), width=4, pressure="r")
    draw_circle(draw, rng, cx + 352 * scale, cy, 16 * scale, fill=accent, width=3)
    draw_line(draw, [(cx - 250 * scale, cy), (cx - 82 * scale, cy + scale), (cx + 82 * scale, cy - scale), (cx + 260 * scale, cy)], width=4)


def draw_blocks(draw: ImageDraw.ImageDraw, rng: random.Random, cx: float, cy: float, scale: float, accent: tuple[int, int, int]) -> None:
    for row, yy in enumerate((95, 20, -55)):
        count = 3 if row != 1 else 2
        start = -250 if count == 3 else -170
        for index in range(count):
            draw_rect(draw, rng, (cx + (start + index * 175) * scale, cy + yy * scale, cx + (start + index * 175 + 135) * scale, cy + (yy + 65) * scale), width=4)
    draw_rect(draw, rng, (cx - 88 * scale, cy - 145 * scale, cx + 88 * scale, cy - 80 * scale), fill=accent, width=5, pressure="t")
    for x in (-45, 45):
        draw_circle(draw, rng, cx + x * scale, cy - 112 * scale, 16 * scale, fill=PAPER, width=3)
    draw_line(draw, [(cx - 310 * scale, cy + 185 * scale), (cx, cy + 180 * scale), (cx + 310 * scale, cy + 185 * scale)], width=4)


def draw_radar(draw: ImageDraw.ImageDraw, rng: random.Random, cx: float, cy: float, scale: float, accent: tuple[int, int, int]) -> None:
    radius = 190 * scale
    draw_circle(draw, rng, cx, cy, radius, fill=PAPER, width=5)
    for side in (-1, 1):
        x0 = cx + side * 300 * scale
        draw_detail_line(draw, rng, cx + side * radius * 0.82, cy - 15 * scale, x0 - side * 70 * scale, cy - 48 * scale, fill=INK, width=3)
        draw_rect(
            draw,
            rng,
            (x0 - 64 * scale, cy - 78 * scale, x0 + 64 * scale, cy - 28 * scale),
            fill=accent if side > 0 else SURFACE,
            width=4,
            pressure="tr" if side > 0 else "lb",
        )
    for local_radius in (65 * scale, 125 * scale):
        draw.ellipse((sc(cx - local_radius), sc(cy - local_radius), sc(cx + local_radius), sc(cy + local_radius)), outline=GUIDE, width=sc(2))
    for degrees in (88, 210, 330):
        ex = cx + math.cos(math.radians(degrees)) * radius
        ey = cy + math.sin(math.radians(degrees)) * radius
        draw_detail_line(draw, rng, cx, cy, ex, ey, fill=INK, width=3)
    for degrees, color in ((28, accent), (155, PAPER), (245, PAPER)):
        x = cx + math.cos(math.radians(degrees)) * radius * 0.82
        y = cy + math.sin(math.radians(degrees)) * radius * 0.82
        draw_circle(draw, rng, x, y, 17 * scale, fill=color, width=3)


def draw_network(draw: ImageDraw.ImageDraw, rng: random.Random, cx: float, cy: float, scale: float, accent: tuple[int, int, int]) -> None:
    draw_circle(draw, rng, cx, cy, 88 * scale, fill=PAPER, width=6)
    nodes = []
    for degrees in (0, 60, 120, 180, 240, 300):
        x = cx + math.cos(math.radians(degrees)) * 315 * scale
        y = cy + math.sin(math.radians(degrees)) * 205 * scale
        nodes.append((x, y))
        draw_detail_line(draw, rng, cx, cy, x, y, fill=INK, width=3)
    for index, (x, y) in enumerate(nodes):
        draw_rect(draw, rng, (x - 75 * scale, y - 30 * scale, x + 75 * scale, y + 30 * scale), fill=accent if index == 4 else SURFACE, width=4, pressure="tr")
    for radius in (34 * scale, 63 * scale):
        draw.ellipse((sc(cx - radius), sc(cy - radius), sc(cx + radius), sc(cy + radius)), outline=INK, width=sc(3))


def draw_dashboard(draw: ImageDraw.ImageDraw, rng: random.Random, cx: float, cy: float, scale: float, accent: tuple[int, int, int]) -> None:
    draw_rect(draw, rng, (cx - 365 * scale, cy - 180 * scale, cx + 365 * scale, cy + 180 * scale), width=6)
    draw_rect(draw, rng, (cx - 280 * scale, cy - 105 * scale, cx - 90 * scale, cy + 105 * scale), fill=accent, width=5, pressure="r")
    draw_line(draw, [(cx - 10 * scale, cy - 10 * scale), (cx + 112 * scale, cy - 86 * scale), (cx + 255 * scale, cy - 45 * scale)], width=4)
    for index in range(4):
        draw_circle(draw, rng, cx + (40 + index * 62) * scale, cy + 78 * scale, 9 * scale, fill=SURFACE, width=2)
    draw_rect(draw, rng, (cx + 300 * scale, cy - 72 * scale, cx + 348 * scale, cy + 48 * scale), width=4, pressure="r")


def draw_funnel(draw: ImageDraw.ImageDraw, rng: random.Random, cx: float, cy: float, scale: float, accent: tuple[int, int, int]) -> None:
    input_points = [(-400, -110), (-340, 18), (-420, 112), (-250, -78), (-220, 92)]
    for index, (x, y) in enumerate(input_points):
        if index % 2 == 0:
            draw_blob(draw, rng, cx + x * scale, cy + y * scale, 54 * scale, 34 * scale, fill=SURFACE_2, width=4)
        else:
            draw_rect(draw, rng, (cx + (x - 58) * scale, cy + (y - 28) * scale, cx + (x + 58) * scale, cy + (y + 28) * scale), fill=SURFACE, width=4, pressure="tr")
    funnel = [
        (cx - 130 * scale, cy - 142 * scale),
        (cx + 78 * scale, cy - 82 * scale),
        (cx + 78 * scale, cy + 82 * scale),
        (cx - 130 * scale, cy + 142 * scale),
        (cx - 58 * scale, cy + 48 * scale),
        (cx - 58 * scale, cy - 48 * scale),
    ]
    draw_poly(draw, rng, funnel, fill=PAPER, outline=INK, width=7, pressure_edges=(0, 2, 4))
    draw_line(draw, [(cx + 78 * scale, cy), (cx + 250 * scale, cy), (cx + 360 * scale, cy - 52 * scale)], fill=accent, width=12, anchor=True)
    for offset in (-80, 40, 150):
        draw_circle(draw, rng, cx + (330 + offset) * scale, cy + (42 if offset == 40 else -42) * scale, 34 * scale, fill=PAPER, width=4)


def draw_broadcast(draw: ImageDraw.ImageDraw, rng: random.Random, cx: float, cy: float, scale: float, accent: tuple[int, int, int]) -> None:
    draw_blob(draw, rng, cx - 355 * scale, cy, 105 * scale, 126 * scale, fill=SURFACE, width=7)
    draw_rect(draw, rng, (cx - 412 * scale, cy - 32 * scale, cx - 285 * scale, cy + 34 * scale), fill=accent, width=4, pressure="r")
    plume = [(-200, -95), (-95, -42), (-20, 65), (70, -92), (165, 18), (255, 105)]
    for index, (x, y) in enumerate(plume):
        fill = SURFACE_2 if index % 2 else PAPER
        if index in (1, 4):
            draw_blob(draw, rng, cx + x * scale, cy + y * scale, 58 * scale, 34 * scale, fill=fill, width=4)
        else:
            draw_rect(draw, rng, (cx + (x - 62) * scale, cy + (y - 26) * scale, cx + (x + 62) * scale, cy + (y + 26) * scale), fill=fill, width=4, pressure="tr")
    draw_line(draw, [(cx - 245 * scale, cy - 12 * scale), (cx - 65 * scale, cy - 70 * scale), (cx + 175 * scale, cy - 25 * scale), (cx + 330 * scale, cy - 110 * scale)], fill=accent, width=8)
    draw_line(draw, [(cx - 228 * scale, cy + 48 * scale), (cx - 10 * scale, cy + 86 * scale), (cx + 185 * scale, cy + 52 * scale), (cx + 350 * scale, cy + 105 * scale)], width=5)
    for x, y in ((375, -120), (420, 8), (365, 128)):
        draw_circle(draw, rng, cx + x * scale, cy + y * scale, 42 * scale, fill=PAPER, width=5)


def draw_prism(draw: ImageDraw.ImageDraw, rng: random.Random, cx: float, cy: float, scale: float, accent: tuple[int, int, int]) -> None:
    draw_line(draw, [(cx - 405 * scale, cy - 20 * scale), (cx - 120 * scale, cy - 20 * scale)], width=9)
    prism = [
        (cx - 120 * scale, cy - 150 * scale),
        (cx + 118 * scale, cy),
        (cx - 120 * scale, cy + 150 * scale),
    ]
    draw_poly(draw, rng, prism, fill=SURFACE, outline=INK, width=7, pressure_edges=(0, 1, 2))
    draw_line(draw, [(cx + 118 * scale, cy), (cx + 355 * scale, cy - 115 * scale)], fill=accent, width=8)
    draw_line(draw, [(cx + 118 * scale, cy), (cx + 392 * scale, cy)], width=6)
    draw_line(draw, [(cx + 118 * scale, cy), (cx + 355 * scale, cy + 118 * scale)], width=6)
    for x, y in ((390, -122), (425, 0), (390, 126)):
        draw_rect(draw, rng, (cx + (x - 46) * scale, cy + (y - 24) * scale, cx + (x + 46) * scale, cy + (y + 24) * scale), fill=PAPER, width=3, pressure="r")


def draw_maze(draw: ImageDraw.ImageDraw, rng: random.Random, cx: float, cy: float, scale: float, accent: tuple[int, int, int]) -> None:
    draw_rect(draw, rng, (cx - 330 * scale, cy - 185 * scale, cx + 330 * scale, cy + 185 * scale), fill=PAPER, width=7)
    walls = [
        [(-250, -105), (-95, -105), (-95, -20), (20, -20)],
        [(-250, 45), (-140, 45), (-140, 125), (-10, 125)],
        [(75, -150), (75, -55), (210, -55), (210, 50)],
        [(38, 62), (155, 62), (155, 145), (270, 145)],
        [(-312, -5), (-225, -5), (-225, 115)],
    ]
    for points in walls:
        draw_line(draw, [(cx + x * scale, cy + y * scale) for x, y in points], width=6, anchor=True)
    route = [(-290, -150), (-210, -150), (-210, -55), (-38, -55), (-38, 72), (232, 72), (232, -8), (318, -8)]
    draw_line(draw, [(cx + x * scale, cy + y * scale) for x, y in route], fill=accent, width=10)
    draw_circle(draw, rng, cx - 290 * scale, cy - 150 * scale, 18 * scale, fill=PAPER, width=4)
    draw_blob(draw, rng, cx + 318 * scale, cy - 8 * scale, 34 * scale, 24 * scale, fill=accent, width=4)


def draw_flywheel(draw: ImageDraw.ImageDraw, rng: random.Random, cx: float, cy: float, scale: float, accent: tuple[int, int, int]) -> None:
    radius = 188 * scale
    draw_circle(draw, rng, cx, cy, radius, fill=PAPER, width=6)
    for start, end in ((-25, 75), (105, 205), (232, 332)):
        draw_arc(draw, (cx - radius, cy - radius, cx + radius, cy + radius), start, end, fill=accent if start == -25 else INK, width=8 if start == -25 else 5)
    stations = ((0, -245), (245, 8), (-205, 160))
    for index, (x, y) in enumerate(stations):
        draw_rect(draw, rng, (cx + (x - 75) * scale, cy + (y - 34) * scale, cx + (x + 75) * scale, cy + (y + 34) * scale), fill=accent if index == 0 else SURFACE, width=4, pressure="tr")
    draw_line(draw, [(cx - 55 * scale, cy + 20 * scale), (cx + 45 * scale, cy - 35 * scale), (cx + 112 * scale, cy + 56 * scale)], width=4)


def draw_scaffold(draw: ImageDraw.ImageDraw, rng: random.Random, cx: float, cy: float, scale: float, accent: tuple[int, int, int]) -> None:
    for x in (-275, -80, 115, 285):
        draw_line(draw, [(cx + x * scale, cy - 180 * scale), (cx + (x - 26) * scale, cy + 178 * scale)], width=5)
    for y in (-140, -35, 80, 170):
        draw_line(draw, [(cx - 330 * scale, cy + y * scale), (cx + 330 * scale, cy + (y + 4) * scale)], width=5)
    for x0, x1 in ((-330, -80), (-80, 115), (115, 330)):
        draw_line(draw, [(cx + x0 * scale, cy + 170 * scale), (cx + x1 * scale, cy - 140 * scale)], width=4)
    draw_rect(draw, rng, (cx - 145 * scale, cy - 86 * scale, cx + 145 * scale, cy + 78 * scale), fill=SURFACE, width=7, pressure="tlbr")
    draw_rect(draw, rng, (cx - 88 * scale, cy - 34 * scale, cx + 88 * scale, cy + 24 * scale), fill=accent, width=4, pressure="tr")


def draw_compass_map(draw: ImageDraw.ImageDraw, rng: random.Random, cx: float, cy: float, scale: float, accent: tuple[int, int, int]) -> None:
    map_shape = [
        (cx - 350 * scale, cy - 130 * scale),
        (cx - 135 * scale, cy - 176 * scale),
        (cx + 85 * scale, cy - 118 * scale),
        (cx + 350 * scale, cy - 160 * scale),
        (cx + 300 * scale, cy + 145 * scale),
        (cx + 55 * scale, cy + 108 * scale),
        (cx - 150 * scale, cy + 172 * scale),
        (cx - 360 * scale, cy + 108 * scale),
    ]
    draw_poly(draw, rng, map_shape, fill=SURFACE, outline=INK, width=6, pressure_edges=(0, 3, 6))
    draw_line(draw, [(cx - 132 * scale, cy - 165 * scale), (cx - 100 * scale, cy + 148 * scale)], width=3)
    draw_line(draw, [(cx + 92 * scale, cy - 115 * scale), (cx + 48 * scale, cy + 108 * scale)], width=3)
    draw_circle(draw, rng, cx + 48 * scale, cy - 5 * scale, 88 * scale, fill=PAPER, width=5)
    needle = [
        (cx + 48 * scale, cy - 92 * scale),
        (cx + 78 * scale, cy + 12 * scale),
        (cx + 48 * scale, cy + 42 * scale),
        (cx + 18 * scale, cy + 12 * scale),
    ]
    draw_poly(draw, rng, needle, fill=accent, outline=INK, width=4, pressure_edges=(0, 2))
    draw_line(draw, [(cx - 250 * scale, cy + 64 * scale), (cx - 78 * scale, cy + 22 * scale), (cx + 162 * scale, cy + 80 * scale), (cx + 285 * scale, cy + 20 * scale)], fill=accent, width=5)


def draw_sample_tray(draw: ImageDraw.ImageDraw, rng: random.Random, cx: float, cy: float, scale: float, accent: tuple[int, int, int]) -> None:
    tray = [
        (cx - 360 * scale, cy - 84 * scale),
        (cx + 320 * scale, cy - 84 * scale),
        (cx + 370 * scale, cy + 115 * scale),
        (cx - 310 * scale, cy + 115 * scale),
    ]
    draw_poly(draw, rng, tray, fill=SURFACE_2, outline=INK, width=6, pressure_edges=(0, 2))
    for index, x in enumerate((-215, -35, 145)):
        y = -10 if index != 1 else -32
        fill = accent if index == 1 else PAPER
        draw_blob(draw, rng, cx + x * scale, cy + y * scale, 62 * scale, 44 * scale, fill=fill, width=5)
        if index != 1:
            draw_detail_line(draw, rng, cx + (x - 30) * scale, cy + (y - 5) * scale, cx + (x + 30) * scale, cy + (y - 5) * scale, width=2)
    draw_line(draw, [(cx - 300 * scale, cy + 116 * scale), (cx - 15 * scale, cy + 165 * scale), (cx + 355 * scale, cy + 118 * scale)], width=5)


def draw_balance(draw: ImageDraw.ImageDraw, rng: random.Random, cx: float, cy: float, scale: float, accent: tuple[int, int, int]) -> None:
    draw_line(draw, [(cx, cy - 160 * scale), (cx, cy + 150 * scale)], width=7)
    draw_circle(draw, rng, cx, cy - 168 * scale, 34 * scale, fill=accent, width=5)
    draw_line(draw, [(cx - 300 * scale, cy - 92 * scale), (cx, cy - 138 * scale), (cx + 300 * scale, cy - 92 * scale)], width=6)
    for side, fill in ((-1, SURFACE), (1, PAPER)):
        px = cx + side * 245 * scale
        draw_line(draw, [(cx + side * 210 * scale, cy - 100 * scale), (px - side * 75 * scale, cy + 18 * scale)], width=3)
        draw_line(draw, [(cx + side * 210 * scale, cy - 100 * scale), (px + side * 75 * scale, cy + 18 * scale)], width=3)
        draw_poly(
            draw,
            rng,
            [
                (px - 105 * scale, cy + 18 * scale),
                (px + 105 * scale, cy + 18 * scale),
                (px + 62 * scale, cy + 88 * scale),
                (px - 62 * scale, cy + 88 * scale),
            ],
            fill=accent if side > 0 else fill,
            outline=INK,
            width=5,
            pressure_edges=(0, 2),
        )


DRAWERS = {
    "browser_window": draw_browser,
    "timeline": draw_timeline,
    "bridge": draw_bridge,
    "folder": draw_folder,
    "magnifier": draw_magnifier,
    "gate": draw_gate,
    "building_blocks": draw_blocks,
    "radar": draw_radar,
    "network": draw_network,
    "dashboard": draw_dashboard,
    "evidence_box": draw_folder,
    "funnel": draw_funnel,
    "broadcast": draw_broadcast,
    "prism": draw_prism,
    "maze": draw_maze,
    "flywheel": draw_flywheel,
    "scaffold": draw_scaffold,
    "compass_map": draw_compass_map,
    "sample_tray": draw_sample_tray,
    "balance": draw_balance,
}


def resize_center_crop(in_path: Path, out_path: Path, target_w: int, target_h: int) -> None:
    image = Image.open(in_path).convert("RGB")
    scale = max(target_w / image.width, target_h / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2
    cropped = resized.crop((left, top, left + target_w, top + target_h))
    cropped.save(out_path, format="PNG", optimize=True)


def render_item(item: dict, out_path: Path, *, size: tuple[int, int], accent: tuple[int, int, int]) -> None:
    seed = str(item.get("id", "")) + ":" + str(item.get("metaphor", "")) + ":" + str(item.get("title", ""))
    rng = random.Random(seed)
    width, height = size
    background = accent if item.get("background_mode") == "inverted" else PAPER
    image = Image.new("RGB", (width * SS, height * SS), background)
    draw = ImageDraw.Draw(image)
    target = str(item.get("target", "inline"))
    metaphor = str(item.get("metaphor", "dashboard"))
    scale = resolve_subject_scale(metaphor, target, width, height)
    drawer = DRAWERS.get(metaphor, draw_dashboard)
    drawer(draw, rng, width / 2, height / 2, scale, accent)
    image = image.resize((width, height), Image.Resampling.LANCZOS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, format="PNG", optimize=True)


def build_board(paths: list[Path], out_path: Path) -> None:
    if not paths:
        return
    thumb_w, thumb_h = 920, 512
    cols = 3
    gap = 80
    rows = math.ceil(len(paths) / cols)
    board = Image.new("RGB", (cols * thumb_w + (cols + 1) * gap, rows * thumb_h + (rows + 1) * gap), PAPER)
    for index, path in enumerate(paths):
        image = Image.open(path).convert("RGB")
        image.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        cell_x = gap + (index % cols) * (thumb_w + gap)
        cell_y = gap + (index // cols) * (thumb_h + gap)
        x = cell_x + (thumb_w - image.width) // 2
        y = cell_y + (thumb_h - image.height) // 2
        board.paste(image, (x, y))
    board.save(out_path, format="PNG", optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompts", required=True, help="prompts.json generated by generate_prompts.py")
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--size", default="1664x928", help="Default wide image size")
    parser.add_argument("--card-size", default="1024x1024")
    parser.add_argument("--final-size", default="2400x1024")
    parser.add_argument("--board", action="store_true")
    args = parser.parse_args()

    items = json.loads(Path(args.prompts).read_text(encoding="utf-8"))
    wide_size = parse_size(args.size)
    card_size = parse_size(args.card_size)
    final_size = parse_size(args.final_size) if args.final_size else None
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    rendered: list[Path] = []
    files: list[str] = []
    for item in items:
        item_id = safe_name(item.get("id") or "item")
        title = safe_name(item.get("title") or item.get("target") or "image")
        item_size = card_size if item.get("aspect") == "1:1" else wide_size
        accent = hex_to_rgb(item.get("accent_color", ""))
        out_path = outdir / f"{item_id}_{title}.png"
        render_item(item, out_path, size=item_size, accent=accent)
        rendered.append(out_path)
        files.append(out_path.name)

        if item.get("final_size") and final_size:
            final_path = outdir / f"{item_id}_{title}_{args.final_size}.png"
            resize_center_crop(out_path, final_path, final_size[0], final_size[1])
            files.append(final_path.name)

    if args.board:
        board_path = outdir / "overview_board.png"
        build_board(rendered, board_path)
        files.append(board_path.name)

    summary = {
        "source": "deterministic local renderer",
        "count": len(items),
        "wide_size": args.size,
        "card_size": args.card_size,
        "files": files,
    }
    (outdir / "RUN_SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
