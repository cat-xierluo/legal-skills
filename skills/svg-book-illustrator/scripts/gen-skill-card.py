#!/usr/bin/env python3
# Skill-structure card SVG generator for svg-book-illustrator v1.8.1.
# Edit TITLE/INPUTS/SKILL_NAME/SATELLITES/STEPS/OUTPUTS/FOOTNOTE/PALETTE at top,
# then: python3 gen-skill-card.py out.svg
import sys

# ---------- parameters ----------
TITLE = "法律研究 Skill 结构图"
INPUTS = ["案件事实", "法律问题"]            # 1-2 inputs
SKILL_NAME = "legal-research"
SATELLITES = [("references/", "清单/模板"), ("scripts/", "脚本"), ("SKILL.md", "流程定义")]
STEPS = ["识别法律问题", "检索类案", "归纳裁判观点", "输出研究备忘录"]
OUTPUTS = ["研究备忘录.md"]                   # 1-3 outputs
FOOTNOTE = "联动：可接入起诉状 Skill / 庭审大纲 Skill"

# palette (P1 雾蓝系) — keep generic, no book refs
C_NAME_BAND = "#B8CFE0"   # skill name band (deeper)
C_SAT       = "#D6E4F0"   # satellite boxes (3 件套)
C_INPUT     = "#EDF3F8"
C_OUTPUT    = "#EDF3F8"
C_TEXT      = "#2D3436"
C_SUB       = "#636E72"
C_BORDER    = "#2D3436"
C_ARROW     = "#2D3436"

# ---------- layout ----------
W = 720
LEFT, RIGHT = 70, 650          # content x range (width 580)
CENTER_X = (LEFT + RIGHT) // 2

def row_boxes(n, y_top, h):
    """Return list of (x, w) for n boxes centered in LEFT..RIGHT."""
    gap = 24
    total_w = RIGHT - LEFT
    w = (total_w - gap * (n - 1)) // n
    out = []
    for i in range(n):
        x = LEFT + i * (w + gap)
        out.append((x, w))
    return out, y_top, h

out = []
def emit(s): out.append(s)

# compute H dynamically
TITLE_Y = 32
INPUT_TOP, INPUT_H = 56, 46
SKILL_TOP, SKILL_H = 150, 240
OUT_TOP, OUT_H = 425, 46
HAS_FOOT = bool(FOOTNOTE)
FOOT_TOP, FOOT_H = (485, 36) if HAS_FOOT else (0, 0)
H = (FOOT_TOP + FOOT_H + 40) if HAS_FOOT else (OUT_TOP + OUT_H + 40)

emit(f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg">')
emit('<style>text{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}</style>')

# title
emit(f'<text x="{CENTER_X}" y="{TITLE_Y}" text-anchor="middle" font-size="22" font-weight="600" fill="{C_TEXT}">{TITLE}</text>')

# ---- inputs ----
boxes, iy, ih = row_boxes(len(INPUTS), INPUT_TOP, INPUT_H)
for (x, w), label in zip(boxes, INPUTS):
    emit(f'<rect x="{x}" y="{iy}" width="{w}" height="{ih}" rx="6" fill="{C_INPUT}" stroke="{C_BORDER}" stroke-width="1.5"/>')
    emit(f'<text x="{x+w/2}" y="{iy+ih/2+6}" text-anchor="middle" font-size="17" fill="{C_TEXT}">{label}</text>')
# arrow inputs -> skill
emit(f'<line x1="{CENTER_X}" y1="{iy+ih+2}" x2="{CENTER_X}" y2="{SKILL_TOP-8}" stroke="{C_ARROW}" stroke-width="2" marker-end="url(#arrow)"/>')

# ---- skill main box ----
emit(f'<rect x="{LEFT}" y="{SKILL_TOP}" width="{RIGHT-LEFT}" height="{SKILL_H}" rx="10" fill="none" stroke="{C_BORDER}" stroke-width="2.5"/>')
# name band
BAND_H = 38
emit(f'<rect x="{LEFT}" y="{SKILL_TOP}" width="{RIGHT-LEFT}" height="{BAND_H}" rx="10" fill="{C_NAME_BAND}" stroke="{C_BORDER}" stroke-width="2.5"/>')
# clip band bottom corners visually: overlay a thin rect to square off bottom of band
emit(f'<rect x="{LEFT}" y="{SKILL_TOP+BAND_H-10}" width="{RIGHT-LEFT}" height="10" fill="{C_NAME_BAND}"/>')
emit(f'<line x1="{LEFT}" y1="{SKILL_TOP+BAND_H}" x2="{RIGHT}" y2="{SKILL_TOP+BAND_H}" stroke="{C_BORDER}" stroke-width="2.5"/>')
emit(f'<text x="{CENTER_X}" y="{SKILL_TOP+25}" text-anchor="middle" font-size="19" font-weight="700" fill="{C_TEXT}">Skill: {SKILL_NAME}</text>')

# 3 件套 satellites row
SAT_TOP = SKILL_TOP + BAND_H + 16
SAT_H = 50
sats, _, _ = row_boxes(len(SATELLITES), SAT_TOP, SAT_H)
for (x, w), (name, sub) in zip(sats, SATELLITES):
    emit(f'<rect x="{x}" y="{SAT_TOP}" width="{w}" height="{SAT_H}" rx="6" fill="{C_SAT}" stroke="{C_BORDER}" stroke-width="1.5"/>')
    emit(f'<text x="{x+w/2}" y="{SAT_TOP+21}" text-anchor="middle" font-size="16" font-weight="600" fill="{C_TEXT}">{name}</text>')
    emit(f'<text x="{x+w/2}" y="{SAT_TOP+40}" text-anchor="middle" font-size="14" fill="{C_SUB}">{sub}</text>')

# steps list
STEPS_LABEL_Y = SAT_TOP + SAT_H + 28
emit(f'<text x="{LEFT+8}" y="{STEPS_LABEL_Y}" font-size="16" font-weight="600" fill="{C_TEXT}">SKILL.md 定义的流程：</text>')
circles = "①②③④⑤⑥⑦⑧"
step_y0 = STEPS_LABEL_Y + 24
for i, step in enumerate(STEPS):
    yy = step_y0 + i * 22
    mark = circles[i] if i < len(circles) else f"{i+1}."
    emit(f'<text x="{LEFT+20}" y="{yy}" font-size="16" fill="{C_TEXT}"><tspan font-weight="600">{mark}</tspan>  {step}</text>')

# arrow skill -> outputs
ARROW2_Y1 = SKILL_TOP + SKILL_H + 2
ARROW2_Y2 = OUT_TOP - 8
emit(f'<line x1="{CENTER_X}" y1="{ARROW2_Y1}" x2="{CENTER_X}" y2="{ARROW2_Y2}" stroke="{C_ARROW}" stroke-width="2" marker-end="url(#arrow)"/>')

# ---- outputs ----
boxes, oy, oh = row_boxes(len(OUTPUTS), OUT_TOP, OUT_H)
for (x, w), label in zip(boxes, OUTPUTS):
    emit(f'<rect x="{x}" y="{oy}" width="{w}" height="{oh}" rx="6" fill="{C_OUTPUT}" stroke="{C_BORDER}" stroke-width="1.5"/>')
    emit(f'<text x="{x+w/2}" y="{oy+oh/2+6}" text-anchor="middle" font-size="17" fill="{C_TEXT}">{label}</text>')

# ---- footnote (dashed) ----
if HAS_FOOT:
    emit(f'<rect x="{LEFT}" y="{FOOT_TOP}" width="{RIGHT-LEFT}" height="{FOOT_H}" rx="6" fill="none" stroke="{C_SUB}" stroke-width="1.5" stroke-dasharray="6 4"/>')
    emit(f'<text x="{CENTER_X}" y="{FOOT_TOP+FOOT_H/2+5}" text-anchor="middle" font-size="15" fill="{C_SUB}">{FOOTNOTE}</text>')

# arrow marker (single, per v1.6.0 marker rule)
emit('<defs>')
emit(f'<marker id="arrow" markerWidth="10" markerHeight="10" refX="6" refY="5" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L10,5 L0,10 z" fill="{C_ARROW}"/></marker>')
emit('</defs>')

emit('</svg>')

dest = sys.argv[1] if len(sys.argv) > 1 else "/tmp/skill-card-demo.svg"
with open(dest, "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("wrote", dest, f"({len(out)} lines)")
