#!/usr/bin/env python3
# N×M grid matrix SVG generator for svg-book-illustrator v1.8.3.
# Edit TITLE/CORNER_LABEL/ROW_LABELS/COL_LABELS/CELLS/PALETTE at top,
# then: python3 gen-matrix-grid.py out.svg --figure-id fig-ch03-s2-01
from figure_id import parse_output_and_figure_id


dest, figure_id = parse_output_and_figure_id("/tmp/matrix-grid-demo.svg")

# ---------- parameters ----------
TITLE = "合同审查：4 类风险 × 5 类条款 对照矩阵"
CORNER_LABEL = "风险 \\ 条款"     # top-left corner cell
ROW_LABELS = ["商业风险", "法律合规风险", "财务风险", "操作风险"]
COL_LABELS = ["违约责任", "付款条款", "知识产权", "保密", "终止"]
# CELLS[r][c]: one of "yes"(√) / "no"(×) / "partial"(○) / "na"(—) or free text
CELLS = [
    ["yes",     "yes",     "partial", "no",  "yes"],
    ["yes",     "no",      "yes",     "yes", "partial"],
    ["partial", "yes",     "no",      "no",  "partial"],
    ["no",      "partial", "no",      "yes", "no"],
]

# status palette (柔和 P 色, 符合 v1.5.0+ 打印友好约束)
STATUS = {
    "yes":     {"fill": "#C8EBC8", "sym": "√", "label": "重点关注"},   # P3 嫩绿
    "no":      {"fill": "#EDDFC8", "sym": "×", "label": "基本无关"},   # P4 暖米浅
    "partial": {"fill": "#E8DFD0", "sym": "○", "label": "部分相关"},   # P7 暖灰
    "na":      {"fill": "#F0F0F0", "sym": "—", "label": "不适用"},
}
C_TEXT = "#2D3436"
C_SUB = "#636E72"
C_BORDER = "#2D3436"
C_HEADER_FILL = "#D6E4F0"   # P1 header band

# ---------- layout ----------
W = 720
LEFT = 40
LABEL_W = 130             # row-label column width
GRID_LEFT = LEFT + LABEL_W + 8
GRID_RIGHT = 685
TITLE_Y = 32
HEADER_TOP = 62
HEADER_H = 50             # column header band height
GRID_TOP = HEADER_TOP + HEADER_H + 4
CELL_H = 44

N = len(ROW_LABELS)
M = len(COL_LABELS)
CELL_W = (GRID_RIGHT - GRID_LEFT) / M
GRID_BOTTOM = GRID_TOP + N * CELL_H
H = GRID_BOTTOM + 60       # room for legend

out = []
def emit(s): out.append(s)

emit(f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" data-figure-id="{figure_id}" xmlns="http://www.w3.org/2000/svg">')

# title
emit(f'<text x="{W/2}" y="{TITLE_Y}" text-anchor="middle" font-size="22" font-weight="600" fill="{C_TEXT}">{TITLE}</text>')

# corner label cell
emit(f'<rect x="{LEFT}" y="{HEADER_TOP}" width="{LABEL_W}" height="{HEADER_H}" fill="{C_HEADER_FILL}" stroke="{C_BORDER}" stroke-width="1.5"/>')
emit(f'<text x="{LEFT+LABEL_W/2}" y="{HEADER_TOP+HEADER_H/2+5}" text-anchor="middle" font-size="14" font-weight="600" fill="{C_TEXT}">{CORNER_LABEL}</text>')

# column headers
for j, cl in enumerate(COL_LABELS):
    x = GRID_LEFT + j * CELL_W
    emit(f'<rect x="{x}" y="{HEADER_TOP}" width="{CELL_W}" height="{HEADER_H}" fill="{C_HEADER_FILL}" stroke="{C_BORDER}" stroke-width="1.5"/>')
    emit(f'<text x="{x+CELL_W/2}" y="{HEADER_TOP+HEADER_H/2+5}" text-anchor="middle" font-size="15" font-weight="600" fill="{C_TEXT}">{cl}</text>')

# rows
for i, rl in enumerate(ROW_LABELS):
    y = GRID_TOP + i * CELL_H
    # row label
    emit(f'<rect x="{LEFT}" y="{y}" width="{LABEL_W}" height="{CELL_H}" fill="{C_HEADER_FILL}" stroke="{C_BORDER}" stroke-width="1.5"/>')
    emit(f'<text x="{LEFT+LABEL_W/2}" y="{y+CELL_H/2+5}" text-anchor="middle" font-size="15" font-weight="600" fill="{C_TEXT}">{rl}</text>')
    # cells
    for j, cell in enumerate(CELLS[i]):
        cx = GRID_LEFT + j * CELL_W
        st = STATUS.get(cell, None)
        if st:
            fill, sym = st["fill"], st["sym"]
        else:
            fill, sym = "#F0F0F0", cell   # free text
        emit(f'<rect x="{cx}" y="{y}" width="{CELL_W}" height="{CELL_H}" fill="{fill}" stroke="{C_BORDER}" stroke-width="1"/>')
        emit(f'<text x="{cx+CELL_W/2}" y="{y+CELL_H/2+7}" text-anchor="middle" font-size="20" font-weight="700" fill="{C_TEXT}">{sym}</text>')

# legend
LEG_Y = GRID_BOTTOM + 28
lx = LEFT
emit(f'<text x="{lx}" y="{LEG_Y}" font-size="14" font-weight="600" fill="{C_TEXT}">图例：</text>')
lx += 50
for key in ["yes", "partial", "no", "na"]:
    st = STATUS[key]
    emit(f'<rect x="{lx}" y="{LEG_Y-13}" width="20" height="16" fill="{st["fill"]}" stroke="{C_BORDER}" stroke-width="1"/>')
    emit(f'<text x="{lx+10}" y="{LEG_Y}" text-anchor="middle" font-size="14" font-weight="700" fill="{C_TEXT}">{st["sym"]}</text>')
    emit(f'<text x="{lx+26}" y="{LEG_Y}" font-size="13" fill="{C_SUB}">{st["label"]}</text>')
    lx += 26 + len(st["label"]) * 14 + 20

emit('</svg>')

with open(dest, "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("wrote", dest, f"({len(out)} lines)")
