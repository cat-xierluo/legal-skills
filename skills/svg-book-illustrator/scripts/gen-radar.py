#!/usr/bin/env python3
# Radar chart SVG generator for svg-book-illustrator v1.8.0.
# Edit TITLE/LABELS/SERIES/CX/CY/R at top, then: python3 gen-radar.py out.svg
import math, sys

# ---- parameters ----
W, H = 720, 505
TITLE = "法律 AI 生态六层：理论能力 vs 实际部署"
CX, CY, R = 360, 250, 150  # center, radius
LABELS = ["数据/知识库", "模型能力", "Agent/Skill", "工具/MCP", "安全/合规", "生态/平台"]
N = len(LABELS)
# series: (name, values 0..1, fill, stroke)
SERIES = [
    ("理论能力", [0.92, 0.88, 0.85, 0.90, 0.80, 0.86], "#B8CFE0", "#7CA0BC"),
    ("实际部署", [0.48, 0.58, 0.55, 0.50, 0.62, 0.40], "#E8D8C0", "#B8A282"),
]
GRID_LEVELS = 4  # concentric polygons
GRID_STROKE = "#E8E8E8"
AXIS_STROKE = "#B2BEC3"
TEXT_DARK = "#2D3436"
TEXT_SUB = "#636E72"

def axis_angle(i):
    # i=0 at top (-90°), clockwise
    return -math.pi/2 + i * (2*math.pi/N)

def point(i, r):
    a = axis_angle(i)
    return (CX + r*math.cos(a), CY + r*math.sin(a))

def fmt(p):
    return f"{p[0]:.1f},{p[1]:.1f}"

out = []
out.append(f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg">')
out.append('<style>text{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}</style>')
out.append(f'<!-- title -->')
out.append(f'<text x="{CX}" y="34" text-anchor="middle" font-size="22" font-weight="600" fill="{TEXT_DARK}">{TITLE}</text>')

# grid concentric polygons
out.append('<!-- grid levels -->')
for lv in range(1, GRID_LEVELS+1):
    r = R * lv / GRID_LEVELS
    pts = " ".join(fmt(point(i, r)) for i in range(N))
    out.append(f'<polygon points="{pts}" fill="none" stroke="{GRID_STROKE}" stroke-width="1"/>')

# axes
out.append('<!-- axes -->')
for i in range(N):
    p = point(i, R)
    out.append(f'<line x1="{CX}" y1="{CY}" x2="{p[0]:.1f}" y2="{p[1]:.1f}" stroke="{AXIS_STROKE}" stroke-width="1"/>')

# data series
out.append('<!-- data series -->')
for name, vals, fill, stroke in SERIES:
    pts = " ".join(fmt(point(i, R*vals[i])) for i in range(N))
    out.append(f'<polygon points="{pts}" fill="{fill}" fill-opacity="0.5" stroke="{stroke}" stroke-width="2"/>')
    # vertex dots
    for i in range(N):
        p = point(i, R*vals[i])
        out.append(f'<circle cx="{p[0]:.1f}" cy="{p[1]:.1f}" r="3" fill="{stroke}"/>')

# axis labels (outside, at 1.16*R)
out.append('<!-- axis labels -->')
LR = R * 1.18
for i, lab in enumerate(LABELS):
    p = point(i, LR)
    a = axis_angle(i)
    # anchor based on direction
    cos_a = math.cos(a)
    if abs(cos_a) < 0.2:
        anchor = "middle"
    elif cos_a > 0:
        anchor = "start"
    else:
        anchor = "end"
    # nudge vertical for top/bottom
    dy = 5
    if i == 0: dy = -2  # top, label sits above
    if i == N//2: dy = 14  # bottom, label sits below
    yval = p[1] + dy
    out.append(f'<text x="{p[0]:.1f}" y="{yval:.1f}" text-anchor="{anchor}" font-size="18" fill="{TEXT_DARK}">{lab}</text>')

# legend
out.append('<!-- legend -->')
leg_y = int(CY + R*1.18 + 50)  # 底部轴标签(i=N//2, y≈CY+R*1.18+14)下方约 36px，避免与图例重叠
lx = 200
for name, vals, fill, stroke in SERIES:
    out.append(f'<rect x="{lx}" y="{leg_y-12}" width="18" height="13" fill="{fill}" fill-opacity="0.6" stroke="{stroke}" stroke-width="1.5"/>')
    out.append(f'<text x="{lx+26}" y="{leg_y-1}" font-size="16" fill="{TEXT_DARK}">{name}</text>')
    lx += 160

out.append('</svg>')

svg = "\n".join(out)
dest = sys.argv[1] if len(sys.argv) > 1 else "/tmp/radar-demo-ch03.svg"
with open(dest, "w", encoding="utf-8") as f:
    f.write(svg)
print("wrote", dest, f"({len(svg)} bytes)")
