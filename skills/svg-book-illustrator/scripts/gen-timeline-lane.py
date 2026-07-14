#!/usr/bin/env python3
# Multi-lane timeline SVG generator for svg-book-illustrator v1.8.2.
# Edit TITLE/LANES/TICKS/EVENTS/PALETTE at top, then: python3 gen-timeline-lane.py out.svg
import sys

# ---------- parameters ----------
TITLE = "案件多角色推进时间轴"
LANES = ["原告律师", "被告律师", "法院", "当事人"]
TICKS = ["1月", "3月", "6月", "9月", "12月"]            # 4-6 time labels
# EVENTS: (lane_index, fraction 0..1, label)
EVENTS = [
    (0, 0.02, "立案"), (0, 0.22, "举证"), (0, 0.48, "一审开庭"), (0, 0.74, "一审判决"),
    (1, 0.10, "答辩"), (1, 0.38, "反诉"), (1, 0.55, "庭审质证"),
    (2, 0.04, "受理"), (2, 0.50, "开庭"), (2, 0.74, "判决"), (2, 0.92, "二审立案"),
    (3, 0.00, "委托"), (3, 0.50, "旁听"),
]

# palette P2 浅青系 (lanes alternate 2 shades); markers P2 deep
C_LANE_A = "#EDF5F3"       # subtle alt lane band A (very light)
C_LANE_B = "none"          # band B transparent (alternating)
C_LANE_LABEL = "#2D3436"
C_AXIS = "#B2BEC3"
C_AXIS_LABEL = "#636E72"
C_MARKER = "#2D3436"
C_MARKER_FILL = "#A8D2C9"  # P2 mid
C_TEXT = "#2D3436"
C_BORDER = "#2D3436"

# ---------- layout ----------
W = 720
LEFT_AXIS = 175            # axis start x (lane labels occupy 40-170)
RIGHT_AXIS = 680           # axis end x
TITLE_Y = 32
TICK_Y = 58                # tick labels (above axis line)
AXIS_Y = 74                # axis horizontal line
LANE_TOP = 90              # first lane top
LANE_H = 50                # lane height
LANE_LABEL_X = 162         # right-anchored lane labels

N = len(LANES)
H = LANE_TOP + N * LANE_H + 30

def lane_center(i): return LANE_TOP + i * LANE_H + LANE_H / 2
def x_for_frac(f): return LEFT_AXIS + f * (RIGHT_AXIS - LEFT_AXIS)

out = []
def emit(s): out.append(s)

emit(f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg">')

# title
emit(f'<text x="{W/2}" y="{TITLE_Y}" text-anchor="middle" font-size="22" font-weight="600" fill="{C_TEXT}">{TITLE}</text>')

# tick labels + axis line
for i, tk in enumerate(TICKS):
    f = i / (len(TICKS) - 1) if len(TICKS) > 1 else 0.5
    x = x_for_frac(f)
    emit(f'<text x="{x}" y="{TICK_Y}" text-anchor="middle" font-size="14" fill="{C_AXIS_LABEL}">{tk}</text>')
    emit(f'<line x1="{x}" y1="{AXIS_Y}" x2="{x}" y2="{AXIS_Y+5}" stroke="{C_AXIS}" stroke-width="1.2"/>')
emit(f'<line x1="{LEFT_AXIS}" y1="{AXIS_Y}" x2="{RIGHT_AXIS}" y2="{AXIS_Y}" stroke="{C_AXIS}" stroke-width="1.5"/>')

# lanes
for i, name in enumerate(LANES):
    top = LANE_TOP + i * LANE_H
    cy = lane_center(i)
    # alternating subtle band
    fill = C_LANE_A if i % 2 == 0 else C_LANE_B
    if fill != "none":
        emit(f'<rect x="{LEFT_AXIS}" y="{top}" width="{RIGHT_AXIS-LEFT_AXIS}" height="{LANE_H}" fill="{fill}"/>')
    # separator (top of lane)
    emit(f'<line x1="{LEFT_AXIS}" y1="{top}" x2="{RIGHT_AXIS}" y2="{top}" stroke="#E8E8E8" stroke-width="1"/>')
    # lane label
    emit(f'<text x="{LANE_LABEL_X}" y="{cy+5}" text-anchor="end" font-size="16" font-weight="600" fill="{C_LANE_LABEL}">{name}</text>')
# bottom separator
emit(f'<line x1="{LEFT_AXIS}" y1="{LANE_TOP+N*LANE_H}" x2="{RIGHT_AXIS}" y2="{LANE_TOP+N*LANE_H}" stroke="#E8E8E8" stroke-width="1"/>')
# lane label column divider
emit(f'<line x1="{LEFT_AXIS-5}" y1="{AXIS_Y}" x2="{LEFT_AXIS-5}" y2="{LANE_TOP+N*LANE_H}" stroke="{C_AXIS}" stroke-width="1"/>')

# events: marker diamond + label (alternate above/below to reduce collision)
for idx, (li, f, lab) in enumerate(EVENTS):
    x = x_for_frac(f)
    cy = lane_center(li)
    above = (idx % 2 == 0)
    ly = cy - 12 if above else cy + 20
    # diamond marker
    pts = f'{x},{cy-5} {x+5},{cy} {x},{cy+5} {x-5},{cy}'
    emit(f'<polygon points="{pts}" fill="{C_MARKER_FILL}" stroke="{C_MARKER}" stroke-width="1.5"/>')
    emit(f'<text x="{x}" y="{ly}" text-anchor="middle" font-size="13" fill="{C_TEXT}">{lab}</text>')

emit('</svg>')

dest = sys.argv[1] if len(sys.argv) > 1 else "/tmp/timeline-lane-demo.svg"
with open(dest, "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("wrote", dest, f"({len(out)} lines)")
