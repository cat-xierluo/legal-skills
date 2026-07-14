#!/usr/bin/env python3
# Three-column comparison SVG generator for svg-book-illustrator v1.8.4.
import sys

# ---------- parameters ----------
TITLE = "Skill 的三种典型结构"
FOOTNOTE = "三种结构可叠加使用；复杂 Skill 常混合 2-3 种"
# each column: (header, [sub-cards])
COLUMNS = [
    ("纯 SKILL.md 型",    ["特征：流程全写在 SKILL.md", "适用：步骤明确的文书任务", "示例：委托材料批量生成"]),
    ("Skill + 工具 型",   ["特征：SKILL.md 调用 scripts/", "适用：需要精确计算的任务", "示例：利息/违约金计算"]),
    ("场景串联 型",        ["特征：多个 Skill 经案件文件夹串接", "适用：长链路办案流程", "示例：证据→裁判预测→庭审大纲"]),
]

# palette P8 混合柔和系（三栏天然多色，每栏一色）
COL_COLORS = [
    {"head": "#B8CFE0", "card": "#EDF3F8"},   # P1 雾蓝
    {"head": "#C8EBC8", "card": "#EDF7ED"},   # P3 嫩绿
    {"head": "#E8D8C0", "card": "#F4ECDC"},   # P4 暖米
]
C_TEXT = "#2D3436"
C_SUB = "#636E72"
C_BORDER = "#2D3436"

# ---------- layout ----------
W = 720
MARGIN = 40
GAP = 30
COL_W = (W - 2 * MARGIN - (len(COLUMNS) - 1) * GAP) / len(COLUMNS)
TITLE_Y = 32
HEAD_TOP = 60
HEAD_H = 50
CARD_TOP = HEAD_TOP + HEAD_H + 16
CARD_H = 62
CARD_GAP = 12
N_CARDS = max(len(c[1]) for c in COLUMNS)
CARDS_BOTTOM = CARD_TOP + N_CARDS * CARD_H + (N_CARDS - 1) * CARD_GAP
HAS_FOOT = bool(FOOTNOTE)
FOOT_TOP = CARDS_BOTTOM + 22
FOOT_H = 36 if HAS_FOOT else 0
H = (FOOT_TOP + FOOT_H + 30) if HAS_FOOT else (CARDS_BOTTOM + 40)

def col_x(j): return MARGIN + j * (COL_W + GAP)

out = []
def emit(s): out.append(s)

emit(f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg">')
emit(f'<text x="{W/2}" y="{TITLE_Y}" text-anchor="middle" font-size="22" font-weight="600" fill="{C_TEXT}">{TITLE}</text>')

for j, (header, cards) in enumerate(COLUMNS):
    x = col_x(j)
    colors = COL_COLORS[j % len(COL_COLORS)]
    # header
    emit(f'<rect x="{x}" y="{HEAD_TOP}" width="{COL_W}" height="{HEAD_H}" rx="6" fill="{colors["head"]}" stroke="{C_BORDER}" stroke-width="2"/>')
    emit(f'<text x="{x+COL_W/2}" y="{HEAD_TOP+HEAD_H/2+6}" text-anchor="middle" font-size="18" font-weight="700" fill="{C_TEXT}">{header}</text>')
    # sub-cards
    for i, card_text in enumerate(cards):
        cy = CARD_TOP + i * (CARD_H + CARD_GAP)
        emit(f'<rect x="{x}" y="{cy}" width="{COL_W}" height="{CARD_H}" rx="6" fill="{colors["card"]}" stroke="{C_BORDER}" stroke-width="1.5"/>')
        # 2-line: 标签(加粗)第 1 行 + 内容第 2 行——避免单行"标签：内容"在窄列(193px)溢出
        if "：" in card_text:
            label, rest = card_text.split("：", 1)
            emit(f'<text x="{x+COL_W/2}" y="{cy+24}" text-anchor="middle" font-size="14" font-weight="700" fill="{C_TEXT}">{label}</text>')
            emit(f'<text x="{x+COL_W/2}" y="{cy+47}" text-anchor="middle" font-size="13" fill="{C_SUB}">{rest}</text>')
        else:
            emit(f'<text x="{x+COL_W/2}" y="{cy+CARD_H/2+5}" text-anchor="middle" font-size="14" fill="{C_TEXT}">{card_text}</text>')

# footnote
if HAS_FOOT:
    emit(f'<rect x="{MARGIN}" y="{FOOT_TOP}" width="{W-2*MARGIN}" height="{FOOT_H}" rx="6" fill="none" stroke="{C_SUB}" stroke-width="1.5" stroke-dasharray="6 4"/>')
    emit(f'<text x="{W/2}" y="{FOOT_TOP+FOOT_H/2+5}" text-anchor="middle" font-size="14" fill="{C_SUB}">{FOOTNOTE}</text>')

emit('</svg>')

dest = sys.argv[1] if len(sys.argv) > 1 else "/tmp/three-col-demo.svg"
with open(dest, "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("wrote", dest, f"({len(out)} lines)")
