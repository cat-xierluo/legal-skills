#!/usr/bin/env python3
"""成稿一致性 scan：对书稿既有内联 SVG 全量跑硬规范规则，只报告、不改稿。

规则来源（只读引用，不复制维护规范正文）：
- SKILL.md「设计规范 / 成功标准」（v1.8.11）
- references/style-guide.md §一（画布/安全边距）、§5.4（颜色语法）、§5.5.3（marker 与落点）、§六（箭头/连线）
- references/review-checklist.md §⓪（源身份门禁）
- 书仓 figures/FIGURES-OUTLINE.md「配图风格规范」（DEC-128：非节点箭头须 data-arrow-role 声明）

用法：
    python3 scan_consistency.py --help
    python3 scan_consistency.py --book-root <书仓根目录> [--report <输出md>] \
        [--padding 40] [--arrow-gap 8] [--fail-on {none,hard,any}]

输出：
- stdout：汇总统计（SVG 总数 / findings 总数 / 按规则与严重度分布）
- --report：完整 markdown 报告（逐文件逐 SVG findings + 汇总 + 规则清单）

与 BLOCKED 任务的关系：
- Task-001（producer 与 Skill 硬规则冲突）：本脚本是只读检查器，不改 producer / 生成器，
  对历史书稿的 SYNTAX/IDENTITY 发现只是报告，不要求回改（与 v1.8.9「不回改历史书稿」口径一致）。
- Task-002（shape containment 语义）：本脚本不做 shape 包含/重叠几何判定（那是
  writing-reviewer v0.16+ render gate 的职责），不消费也不放宽 data-overlap-role 契约。
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_svgs import find_caption, find_svgs  # noqa: E402

# ---------------------------------------------------------------------------
# 规则登记表：rule_id -> (规则名, 严重度, 规范出处)
# 严重度口径：hard = 违反现行硬约束（渲染契约/marker/语法/箭头落点）；soft = 质量与同步类，
# 需结合历史口径人工研判。扫描只报告，不据此改稿。
# ---------------------------------------------------------------------------
RULES: dict[str, tuple[str, str, str]] = {
    'XML-01': ('XML 不可解析', 'hard', 'xmllint well-formed（SKILL.md 成功标准）'),
    'SYNTAX-01': ('存在 <style> 块', 'hard', 'style-guide §5.4（v1.8.9 源契约）'),
    'SYNTAX-02': ('元素带 style= 属性', 'hard', 'style-guide §5.4（v1.8.9 源契约）'),
    'SYNTAX-03': ('元素带 font-family', 'hard', 'style-guide §5.4（v1.8.9 源契约）'),
    'SYNTAX-04': ('整幅画布底色矩形（违反透明底）', 'hard', 'style-guide §一/§5.4（历史 34 张白底图除外口径见报告）'),
    'SYNTAX-05': ('根 width/height/viewBox 不合规', 'hard', 'SKILL.md 源契约：viewBox 0 0 720 H、width=720、height=H'),
    'MARKER-01': ('多套/非 arrow 的 marker 定义', 'hard', 'style-guide §六 + §5.5.3（v1.6.0 单 id="arrow"）'),
    'MARKER-02': ('arrow marker 缺 markerUnits=userSpaceOnUse 或 orient=auto', 'hard', 'style-guide §六 + §5.5.3（DEC-011）'),
    'MARKER-03': ('marker 引用指向未定义 id', 'hard', 'SVG 引用完整性（悬空 url(#id)）'),
    'PADDING-01': ('内容距画布边缘低于阈值', 'soft', 'style-guide §一：四周安全边距 40px（v1.7.1 H=内容底+40）'),
    'ARROW-01': ('箭头尖端穿入目标框内', 'hard', 'style-guide §5.5.3：落点=目标框边−4px，禁穿框'),
    'ARROW-02': ('悬空箭头：离最近目标框超过阈值且无 data-arrow-role 声明', 'hard', 'style-guide §5.5.3：禁离框>8px；FIGURES-OUTLINE DEC-128'),
    'ARROW-03': ('data-arrow-role 声明不完整（非法 role 或缺 note）', 'hard', 'FIGURES-OUTLINE DEC-128：非节点箭头须 role+非空 note'),
    'IDENTITY-01': ('根元素缺 data-figure-id', 'soft', 'review-checklist §⓪（v1.8.9 前历史图不回填口径）'),
    'IDENTITY-02': ('data-figure-id 跨图重复', 'hard', 'review-checklist §⓪：项目内唯一'),
    'IDENTITY-03': ('data-figure-id 格式不安全', 'soft', 'review-checklist §⓪：1–128 位字母数字._- 且首位字母数字'),
    'IDENTITY-04': ('data-figure-id 为模板 ID（fig-template-*）', 'hard', 'review-checklist §⓪：模板 ID 禁止落稿'),
    'SIDECAR-01': ('canonical 内联 SVG 与 sidecar 派生 SVG 内容不一致', 'hard', 'T261 派生缓存同步口径'),
    'SIDECAR-02': ('章节 sidecar 派生 SVG 文件缺失', 'soft', 'T261 派生缓存同步口径（_images 目录存在时逐张对齐）'),
    'GEOM-01': ('含 transform，几何规则结果按未变换坐标近似', 'soft', '本扫描器能力边界声明'),
}

FIGURE_ID_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')
ARROW_ROLES_ALLOWED = {'axis', 'annotation'}
ARROW_ROLE_ATTR = 'data-arrow-role'
ARROW_NOTE_ATTR = 'data-arrow-note'


def local_name(tag: str) -> str:
    return tag.rsplit('}', 1)[-1]


# ---------------------------------------------------------------------------
# Finding / 扫描数据结构
# ---------------------------------------------------------------------------
@dataclass
class Finding:
    rule_id: str
    severity: str
    file: str          # md 相对 book-root 的路径
    svg_index: int     # 0 基，与 sidecar <stem>-svg-N.svg 命名对齐
    figure_id: str     # 根 data-figure-id（可空）
    caption: str       # 紧随 SVG 的「图 N-X：标题」（可空）
    location: str      # 位置描述（元素/坐标）
    message: str       # 违规说明

    def format(self) -> str:
        head = f'[{self.rule_id}/{self.severity}] {self.file} 第{self.svg_index + 1}张SVG'
        if self.figure_id:
            head += f' ({self.figure_id})'
        if self.caption:
            head += f' 「{self.caption}」'
        return f'{head}：{self.location} —— {self.message}'


@dataclass
class SvgScanResult:
    file: str
    svg_index: int
    figure_id: str = ''
    caption: str = ''
    findings: list[Finding] = field(default_factory=list)

    def add(self, rule_id: str, location: str, message: str) -> None:
        name, severity, _ref = RULES[rule_id]
        self.findings.append(Finding(
            rule_id=rule_id, severity=severity, file=self.file,
            svg_index=self.svg_index, figure_id=self.figure_id,
            caption=self.caption, location=location, message=message,
        ))


# ---------------------------------------------------------------------------
# 几何：元素 bbox 与 path 解析
# ---------------------------------------------------------------------------
@dataclass
class BBox:
    x: float
    y: float
    w: float
    h: float

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h


def _f(value, default=0.0) -> float:
    try:
        return float(str(value).strip().rstrip('px'))
    except (TypeError, ValueError):
        return default


def text_width_estimate(content: str, font_size: float) -> float:
    """review-checklist §③ 口径：CJK ≈ F px/字、Latin ≈ 0.55F px/字。"""
    width = 0.0
    for ch in content:
        width += font_size if ord(ch) > 0x2E80 else 0.55 * font_size
    return width


PATH_COMMAND = re.compile(r'([MmLlHhVvCcSsQqTtAaZz])|(-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)')


def path_points_and_end(d: str) -> tuple[list[tuple[float, float]], tuple[float, float] | None]:
    """解析 path 的 d，返回（全部采样点用于 bbox，路径终点用于箭头落点）。

    arc（A/a）按端点近似（7 参数取末两位）；控制点计入 bbox 是保守近似，
    只影响 padding 边距判断的保守性，不影响 hard 规则判定方向。
    """
    tokens: list[str | float] = []
    for m in PATH_COMMAND.finditer(d or ''):
        cmd, num = m.group(1), m.group(2)
        if cmd:
            tokens.append(cmd)
        else:
            tokens.append(float(num))  # type: ignore[arg-type]

    points: list[tuple[float, float]] = []
    cur = (0.0, 0.0)
    start = (0.0, 0.0)
    i = 0
    rel = False

    def take(n: int) -> list[float]:
        nonlocal i
        vals = [float(t) for t in tokens[i:i + n] if not isinstance(t, str)]  # type: ignore[misc]
        i += n
        return vals

    while i < len(tokens):
        t = tokens[i]
        if isinstance(t, str):
            rel = t.islower()
            cmd = t.upper()
            i += 1
            if cmd == 'Z':
                cur = start
                points.append(cur)
                continue
            if cmd == 'M':
                v = take(2)
                if len(v) == 2:
                    cur = (cur[0] + v[0], cur[1] + v[1]) if rel else (v[0], v[1])
                    start = cur
                    points.append(cur)
            elif cmd == 'L':
                v = take(2)
                if len(v) == 2:
                    cur = (cur[0] + v[0], cur[1] + v[1]) if rel else (v[0], v[1])
                    points.append(cur)
            elif cmd in {'H', 'V'}:
                v = take(1)
                if v:
                    if cmd == 'H':
                        cur = (cur[0] + v[0] if rel else v[0], cur[1])
                    else:
                        cur = (cur[0], cur[1] + v[0] if rel else v[0])
                    points.append(cur)
            elif cmd in {'C', 'S'}:
                v = take(6)
                if len(v) == 6:
                    pts = [(v[0], v[1]), (v[2], v[3]), (v[4], v[5])]
                    if rel:
                        pts = [(cur[0] + px, cur[1] + py) for px, py in pts]
                    points.extend(pts)
                    cur = pts[-1]
            elif cmd in {'Q', 'T'}:
                n = 4 if cmd == 'Q' else 2
                v = take(n)
                if len(v) == n:
                    pts = [(v[k], v[k + 1]) for k in range(0, n, 2)]
                    if rel:
                        pts = [(cur[0] + px, cur[1] + py) for px, py in pts]
                    points.extend(pts)
                    cur = pts[-1]
            elif cmd == 'A':
                v = take(7)
                if len(v) == 7:
                    end = (cur[0] + v[5], cur[1] + v[6]) if rel else (v[5], v[6])
                    points.append(end)
                    cur = end
        else:
            i += 1  # 落单数字，跳过（防御）
    return points, (cur if points else None)


@dataclass
class ShapeEl:
    tag: str
    bbox: BBox
    label: str          # 位置描述用
    is_closed: bool     # 是否可作箭头目标框
    is_canvas_bg: bool = False  # 整幅画布底色矩形：不计入 padding 基准（它就是画布本身）


@dataclass
class ArrowEl:
    tag: str
    tip: tuple[float, float]
    label: str
    role: str
    note: str


@dataclass
class ParsedSvg:
    ok: bool
    root: ET.Element | None = None
    vb: tuple[float, float, float, float] = (0.0, 0.0, 720.0, 400.0)
    shapes: list[ShapeEl] = field(default_factory=list)
    arrows: list[ArrowEl] = field(default_factory=list)
    texts: list[BBox] = field(default_factory=list)
    has_transform: bool = False


def _is_full_canvas_rect(bbox: BBox, vb: tuple[float, float, float, float], tag: str) -> bool:
    """整幅画布底色矩形判定（SYNTAX-04 同口径）：面积 ≥99% 画布且贴 viewBox 原点。"""
    if tag != 'rect':
        return False
    vb_x, vb_y, vb_w, vb_h = vb
    if bbox.w <= 0 or bbox.h <= 0:
        return False
    if bbox.w * bbox.h < 0.99 * vb_w * vb_h:
        return False
    return not (bbox.x - vb_x > 1 or bbox.y - vb_y > 1)


def parse_svg(svg_text: str) -> ParsedSvg:
    result = ParsedSvg(ok=False)
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError:
        return result
    result.ok = True
    result.root = root

    vb_raw = root.get('viewBox')
    if vb_raw:
        parts = vb_raw.replace(',', ' ').split()
        if len(parts) == 4:
            try:
                result.vb = tuple(float(p) for p in parts)  # type: ignore[assignment]
            except ValueError:
                pass

    def walk(el: ET.Element, in_defs: bool) -> None:
        tag = local_name(el.tag)
        if tag == 'defs':
            for child in el:
                walk(child, True)
            return
        if tag in ('marker', 'linearGradient', 'radialGradient', 'filter', 'pattern', 'clipPath', 'symbol'):
            for child in el:
                walk(child, True)
            return
        if in_defs:
            return
        if el.get('transform') not in (None, '', 'none'):
            result.has_transform = True

        if tag == 'rect':
            x, y = _f(el.get('x')), _f(el.get('y'))
            w, h = _f(el.get('width')), _f(el.get('height'))
            bbox = BBox(x, y, w, h)
            result.shapes.append(ShapeEl(tag, bbox, _desc(el, tag), True,
                                         is_canvas_bg=_is_full_canvas_rect(bbox, result.vb, tag)))
        elif tag == 'circle':
            cx, cy, r = _f(el.get('cx')), _f(el.get('cy')), _f(el.get('r'))
            result.shapes.append(ShapeEl(tag, BBox(cx - r, cy - r, 2 * r, 2 * r), _desc(el, tag), True))
        elif tag == 'ellipse':
            cx, cy = _f(el.get('cx')), _f(el.get('cy'))
            rx, ry = _f(el.get('rx')), _f(el.get('ry'))
            result.shapes.append(ShapeEl(tag, BBox(cx - rx, cy - ry, 2 * rx, 2 * ry), _desc(el, tag), True))
        elif tag in ('polygon', 'polyline'):
            pts: list[tuple[float, float]] = []
            for pair in (el.get('points') or '').replace('\n', ' ').replace('\t', ' ').split():
                if ',' not in pair:
                    continue
                try:
                    pts.append((float(pair.split(',')[0]), float(pair.split(',')[1])))
                except ValueError:
                    continue
            if pts:
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                bbox = BBox(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
                result.shapes.append(ShapeEl(tag, bbox, _desc(el, tag), tag == 'polygon'))
        elif tag == 'path':
            pts, end = path_points_and_end(el.get('d') or '')
            if pts:
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                bbox = BBox(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
                result.shapes.append(ShapeEl(tag, bbox, _desc(el, tag), True))
            marker_end = el.get('marker-end')
            if marker_end and end:
                result.arrows.append(ArrowEl(
                    tag, end, _desc(el, tag),
                    el.get(ARROW_ROLE_ATTR, ''), el.get(ARROW_NOTE_ATTR, ''),
                ))
        elif tag == 'line':
            x1, y1 = _f(el.get('x1')), _f(el.get('y1'))
            x2, y2 = _f(el.get('x2')), _f(el.get('y2'))
            result.shapes.append(ShapeEl(tag, BBox(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)), _desc(el, tag), False))
            if el.get('marker-end'):
                result.arrows.append(ArrowEl(
                    tag, (x2, y2), _desc(el, tag),
                    el.get(ARROW_ROLE_ATTR, ''), el.get(ARROW_NOTE_ATTR, ''),
                ))
            if el.get('marker-start'):
                result.arrows.append(ArrowEl(
                    tag, (x1, y1), _desc(el, tag) + '(起点)',
                    el.get(ARROW_ROLE_ATTR, ''), el.get(ARROW_NOTE_ATTR, ''),
                ))
        elif tag == 'text':
            x, y = _f(el.get('x')), _f(el.get('y'))
            fs = _f(el.get('font-size'), 18.0) or 18.0
            anchor = el.get('text-anchor', 'start')
            width = text_width_estimate(''.join(el.itertext()), fs)
            tx = x - width / 2 if anchor == 'middle' else (x - width if anchor == 'end' else x)
            result.texts.append(BBox(tx, y - fs, width, fs))
        for child in el:
            walk(child, in_defs)

    walk(root, False)
    return result


def _desc(el: ET.Element, tag: str) -> str:
    for key in ('id', 'data-figure-id'):
        v = el.get(key)
        if v:
            return f'<{tag} id={v}>'
    if tag in ('rect',):
        return f'<rect x={el.get("x")} y={el.get("y")} w={el.get("width")} h={el.get("height")}>'
    if tag == 'line':
        return f'<line x1={el.get("x1")} y1={el.get("y1")} x2={el.get("x2")} y2={el.get("y2")}>'
    return f'<{tag}>'


def gap_to_bbox(point: tuple[float, float], box: BBox) -> float:
    """点到 bbox 的距离；点在框内返回负的穿入深度（取最浅穿入边）。"""
    px, py = point
    dx = max(box.x - px, 0.0, px - box.x2)
    dy = max(box.y - py, 0.0, py - box.y2)
    if dx > 0 or dy > 0:
        return math.hypot(dx, dy)
    return -min(px - box.x, box.x2 - px, py - box.y, box.y2 - py)


# ---------------------------------------------------------------------------
# 单张 SVG 规则
# ---------------------------------------------------------------------------
def scan_svg(svg_text: str, ctx: SvgScanResult, padding: float, arrow_gap: float) -> ParsedSvg | None:
    parsed = parse_svg(svg_text)
    if not parsed.ok or parsed.root is None:
        ctx.add('XML-01', '<svg> 块', 'XML 解析失败，其余规则跳过（xmllint well-formed 不满足）')
        return parsed

    root = parsed.root
    ctx.figure_id = root.get('data-figure-id', '')
    fid = ctx.figure_id
    if not fid:
        ctx.add('IDENTITY-01', '<svg> 根元素', '缺 data-figure-id（v1.8.9 前历史图不强制回填，登记供后续迁移决策）')
    else:
        if not FIGURE_ID_PATTERN.match(fid):
            ctx.add('IDENTITY-03', f'data-figure-id={fid!r}', '格式不安全（1–128 位字母数字._-，首位字母数字）')
        if fid.startswith('fig-template-'):
            ctx.add('IDENTITY-04', f'data-figure-id={fid!r}', '模板 ID 禁止落稿，须替换为项目内唯一 fig-chNN-sN-NN')
    _scan_syntax(parsed, ctx)
    _scan_marker(parsed, ctx)
    _scan_padding(parsed, ctx, padding)
    _scan_arrow(parsed, ctx, arrow_gap)
    return parsed


def _iter_elements(root: ET.Element):
    stack = [root]
    while stack:
        el = stack.pop()
        yield el
        stack.extend(el)


def _scan_syntax(parsed: ParsedSvg, ctx: SvgScanResult) -> None:
    root = parsed.root
    assert root is not None
    vb_x, vb_y, vb_w, vb_h = parsed.vb

    for el in _iter_elements(root):
        tag = local_name(el.tag)
        if tag == 'style':
            ctx.add('SYNTAX-01', '<style> 块', '源 SVG 禁止 <style>（颜色/字体只走 fill/stroke 属性内联）')
        if el.get('style') is not None:
            ctx.add('SYNTAX-02', _desc(el, tag), '元素禁止 style= 内联样式属性')
        if el.get('font-family') is not None:
            ctx.add('SYNTAX-03', _desc(el, tag), '元素禁止 font-family（字体由 assets/render-fonts.css 统一注入）')

    # 透明底：整幅画布底色矩形
    for s in parsed.shapes:
        if s.is_canvas_bg:
            ctx.add('SYNTAX-04', s.label,
                    '整幅画布底色矩形违反透明底硬约束（历史 34 张白底图按「保持稳定不回改」口径登记，不要求本次回改）')

    # 显式 width/height 与 viewBox 契约
    problems = []
    if root.get('viewBox') is None:
        problems.append('根元素缺 viewBox')
    w_attr, h_attr = root.get('width'), root.get('height')
    if w_attr is None or h_attr is None:
        problems.append('根元素缺显式 width/height')
    else:
        if abs(_f(w_attr, -1) - vb_w) > 0.5:
            problems.append(f'width={w_attr} 与 viewBox 宽 {vb_w:g} 不一致')
        if abs(_f(h_attr, -1) - vb_h) > 0.5:
            problems.append(f'height={h_attr} 与 viewBox 高 {vb_h:g} 不一致')
    if abs(vb_w - 720) > 0.5:
        problems.append(f'viewBox 宽 {vb_w:g} ≠ 720（16开 115mm 通栏画布硬规范）')
    if abs(vb_x) > 0.01 or abs(vb_y) > 0.01:
        problems.append(f'viewBox 原点 ({vb_x:g},{vb_y:g}) 非 (0,0)')
    if problems:
        ctx.add('SYNTAX-05', f'viewBox="{root.get("viewBox")}" width={w_attr} height={h_attr}',
                '；'.join(problems))


def _scan_marker(parsed: ParsedSvg, ctx: SvgScanResult) -> None:
    markers: list[ET.Element] = []
    referenced: set[str] = set()
    for el in _iter_elements(parsed.root):
        tag = local_name(el.tag)
        if tag == 'marker':
            markers.append(el)
        for attr in ('marker-end', 'marker-start', 'marker-mid'):
            v = el.get(attr)
            if v:
                m = re.match(r'url\(#([^)]+)\)', v.strip())
                if m:
                    referenced.add(m.group(1))

    ids = [m.get('id', '') for m in markers]
    bad_ids = [i for i in ids if i != 'arrow']
    dup_arrow = ids.count('arrow') > 1
    if bad_ids or dup_arrow:
        detail = []
        if bad_ids:
            detail.append(f'非 arrow 的 marker id：{bad_ids}（v1.6.0 起单 id="arrow" + orient="auto" 通吃全方向）')
        if dup_arrow:
            detail.append('id="arrow" 重复定义')
        ctx.add('MARKER-01', f'<marker> ids={ids}', '；'.join(detail))

    for m in markers:
        if m.get('id') != 'arrow':
            continue
        misses = []
        if m.get('markerUnits') != 'userSpaceOnUse':
            misses.append(f'markerUnits={m.get("markerUnits")!r}（默认 strokeWidth 会随线宽漂移，DEC-011）')
        if m.get('orient') != 'auto':
            misses.append(f'orient={m.get("orient")!r}')
        if misses:
            ctx.add('MARKER-02', f'<marker id="arrow" …>', '；'.join(misses))

    defined = set(ids)
    for ref in sorted(referenced - defined):
        ctx.add('MARKER-03', f'url(#{ref})', 'marker 引用指向本 SVG 未定义的 id（悬空引用）')


def _scan_padding(parsed: ParsedSvg, ctx: SvgScanResult, padding: float) -> None:
    vb_x, vb_y, vb_w, vb_h = parsed.vb
    # 画布底色矩形本身不计入 padding 基准（它就是画布，不是内容）
    boxes = [s.bbox for s in parsed.shapes if not s.is_canvas_bg] + parsed.texts  # 线段 bbox 允许零宽/零高
    if not boxes:
        return
    xmin = min(b.x for b in boxes)
    ymin = min(b.y for b in boxes)
    xmax = max(b.x2 for b in boxes)
    ymax = max(b.y2 for b in boxes)
    gaps = {
        '左': xmin - vb_x,
        '顶': ymin - vb_y,
        '右': (vb_x + vb_w) - xmax,
        '底': (vb_y + vb_h) - ymax,
    }
    bad = [(side, g) for side, g in gaps.items() if g < padding - 1e-6]
    if bad:
        detail = '，'.join(f'{side}边距 {g:.0f}px' for side, g in bad)
        ctx.add('PADDING-01', f'内容 bbox=({xmin:.0f},{ymin:.0f})-({xmax:.0f},{ymax:.0f})，画布 {vb_w:g}×{vb_h:g}',
                f'{detail} < 阈值 {padding:g}px（安全边距规范；v1.7.1 前 720×400 固定高的历史图常见底边距不足）')


def _scan_arrow(parsed: ParsedSvg, ctx: SvgScanResult, arrow_gap: float) -> None:
    # 画布底色矩形不是箭头目标框（它承载整个画布，会把所有箭头误判为穿框）
    targets = [s for s in parsed.shapes if s.is_closed and not s.is_canvas_bg]
    for a in parsed.arrows:
        if a.role and (a.role not in ARROW_ROLES_ALLOWED or not a.note.strip()):
            ctx.add('ARROW-03', a.label,
                    f'data-arrow-role={a.role!r} note={a.note!r}（DEC-128：非节点箭头 role 只允许 axis/annotation 且必须带非空 note）')
        inside = [(t, gap_to_bbox(a.tip, t.bbox)) for t in targets]
        inside = [(t, g) for t, g in inside if g < -0.5]
        if inside:
            t, g = min(inside, key=lambda p: -p[1])
            ctx.add('ARROW-01', f'{a.label} 尖端({a.tip[0]:.0f},{a.tip[1]:.0f})',
                    f'穿入目标框 {t.label} 达 {-g:.0f}px（落点应为目标框边−4px，禁穿框）')
            continue
        if not targets:
            gap = None
        else:
            gap = min(gap_to_bbox(a.tip, t.bbox) for t in targets)
        if gap is None or gap > arrow_gap:
            if a.role in ARROW_ROLES_ALLOWED and a.note.strip():
                continue  # 已按 DEC-128 声明的轴线/注释箭头，豁免落点距离
            dist = '无任何闭合目标框' if gap is None else f'距最近目标框 {gap:.0f}px'
            ctx.add('ARROW-02', f'{a.label} 尖端({a.tip[0]:.0f},{a.tip[1]:.0f})',
                    f'{dist} > 阈值 {arrow_gap:g}px，悬空箭头；若为坐标轴/注释箭头须写 data-arrow-role="axis|annotation" + 非空 data-arrow-note（DEC-128）')


# ---------------------------------------------------------------------------
# 成书扫描：canonical md ↔ sidecar
# ---------------------------------------------------------------------------
@dataclass
class FileScan:
    path: str
    rel: str
    svg_count: int = 0
    results: list[SvgScanResult] = field(default_factory=list)
    sidecar_dir: str = ''
    sidecar_notes: list[str] = field(default_factory=list)
    sidecar_findings: list[Finding] = field(default_factory=list)


def scan_file(md_path: Path, book_root: Path, padding: float, arrow_gap: float,
              id_registry: dict[str, str]) -> FileScan:
    rel = md_path.relative_to(book_root).as_posix()
    fs = FileScan(path=str(md_path), rel=rel)
    content = md_path.read_text(encoding='utf-8')
    blocks = find_svgs(content)

    for idx, (_start, end, svg_code) in enumerate(blocks):
        ctx = SvgScanResult(file=rel, svg_index=idx)
        cap = find_caption(content, end)
        if cap:
            ctx.caption = f'图 {cap[0]}-{cap[1]}：{cap[2]}'
        parsed = scan_svg(svg_code, ctx, padding, arrow_gap)
        fs.results.append(ctx)

        fid = ctx.figure_id
        if parsed and parsed.ok and fid:
            if fid in id_registry:
                ctx.add('IDENTITY-02', f'data-figure-id={fid!r}', f'与 {id_registry[fid]} 重复（项目内必须唯一）')
            else:
                id_registry[fid] = f'{rel}#svg{idx}'

        if parsed and parsed.has_transform:
            ctx.add('GEOM-01', 'transform 属性', '几何规则按未变换坐标近似，结果保守，需渲染复核')

    fs.svg_count = len(blocks)

    # sidecar：<stem>_images/<stem>-svg-<i>.svg 逐张对齐
    sidecar_dir = md_path.parent / f'{md_path.stem}_images'
    if fs.svg_count == 0:
        return fs
    if not sidecar_dir.is_dir():
        fs.sidecar_notes.append(
            f'无 sidecar 目录 {sidecar_dir.name}/（按 FIGURES-OUTLINE 口径仅 15 章正文维护 _images 派生缓存；'
            '序言/附录/后记等不视为缺同步）')
        return fs
    fs.sidecar_dir = sidecar_dir.name
    for idx in range(fs.svg_count):
        sidecar = sidecar_dir / f'{md_path.stem}-svg-{idx}.svg'
        block_text = blocks[idx][2]
        if not sidecar.is_file():
            fs.sidecar_findings.append(Finding(
                rule_id='SIDECAR-02', severity=RULES['SIDECAR-02'][1], file=rel, svg_index=idx,
                figure_id=fs.results[idx].figure_id, caption=fs.results[idx].caption,
                location=f'{sidecar_dir.name}/{sidecar.name}',
                message='_images 目录存在但缺该序号的派生 SVG（T261 派生缓存同步）'))
            continue
        file_text = sidecar.read_text(encoding='utf-8')
        if block_text == file_text:
            continue
        if block_text.rstrip() == file_text.rstrip():
            detail = '仅尾随空白差异（内容一致）'
        elif re.sub(r'\s+', '', block_text) == re.sub(r'\s+', '', file_text):
            detail = '空白归一后一致（缩进/换行差异）'
        else:
            detail = '内容存在实质差异'
        fs.sidecar_findings.append(Finding(
            rule_id='SIDECAR-01', severity=RULES['SIDECAR-01'][1], file=rel, svg_index=idx,
            figure_id=fs.results[idx].figure_id, caption=fs.results[idx].caption,
            location=f'{sidecar_dir.name}/{sidecar.name}',
            message=f'canonical 内联 SVG 与 sidecar 派生 SVG 不一致：{detail}（需重新生成派生缓存）'))
    return fs


def discover_canonical(book_root: Path) -> list[Path]:
    """书仓 canonical：manuscript/ 下全部 .md，排除 *_images 派生缓存目录。"""
    manuscript = book_root / 'manuscript'
    base = manuscript if manuscript.is_dir() else book_root
    return sorted(
        p for p in base.rglob('*.md')
        if '_images' not in p.parts
    )


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------
def build_report(files: list[FileScan], args_ns) -> str:
    all_findings: list[Finding] = []
    for fs in files:
        for r in fs.results:
            all_findings.extend(r.findings)
        all_findings.extend(fs.sidecar_findings)
    total_svg = sum(fs.svg_count for fs in files)
    by_rule: Counter[str] = Counter(f.rule_id for f in all_findings)
    by_sev: Counter[str] = Counter(f.severity for f in all_findings)

    lines: list[str] = []
    lines.append('# svg-book-illustrator 成稿一致性 scan 报告')
    lines.append('')
    lines.append(f'- 生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    lines.append(f'- 扫描根：`{args_ns.book_root}`')
    lines.append(f'- 阈值：padding={args_ns.padding}px，arrow-gap={args_ns.arrow_gap}px')
    lines.append(f'- 范围：{len(files)} 份 canonical md，{total_svg} 张内联 SVG')
    lines.append(f'- findings：{len(all_findings)}（hard={by_sev.get("hard", 0)}，soft={by_sev.get("soft", 0)}）')
    lines.append('- 性质：只报告，不改稿；不替代 writing-reviewer render gate 的几何/视觉审计')
    lines.append('')
    lines.append('## 按规则分布')
    lines.append('')
    lines.append('| 规则 | 严重度 | 命名 | 出处 | 数量 |')
    lines.append('|---|---|---|---|---|')
    for rid in sorted(by_rule, key=lambda r: -by_rule[r]):
        name, sev, ref = RULES[rid]
        lines.append(f'| {rid} | {sev} | {name} | {ref} | {by_rule[rid]} |')
    lines.append('')
    lines.append('## 逐文件明细')
    for fs in files:
        lines.append('')
        lines.append(f'### {fs.rel}（{fs.svg_count} 张 SVG）')
        if fs.svg_count == 0:
            lines.append('')
            lines.append('- 无内联 SVG')
            continue
        if fs.sidecar_dir:
            lines.append(f'- sidecar：`{fs.sidecar_dir}/`')
        for note in fs.sidecar_notes:
            lines.append(f'- 注：{note}')
        for r in fs.results:
            fid = f' `{r.figure_id}`' if r.figure_id else ''
            cap = f' 「{r.caption}」' if r.caption else ''
            if not r.findings:
                lines.append(f'- svg#{r.svg_index}{fid}{cap}：0 finding ✓')
            else:
                lines.append(f'- svg#{r.svg_index}{fid}{cap}：{len(r.findings)} findings')
                for f in r.findings:
                    lines.append(f'  - {f.format()}')
        for f in fs.sidecar_findings:
            lines.append(f'  - {f.format()}')
    lines.append('')
    lines.append('## 与 BLOCKED 任务的关系')
    lines.append('')
    lines.append('- Task-001（producer 与 Skill 硬规则冲突）：本 scan 是只读检查器，不改 producer；'
                 'SYNTAX/IDENTITY 类 finding 对历史书稿只登记，不要求回改（v1.8.9「不回改历史书稿」口径）。')
    lines.append('- Task-002（shape containment 语义）：本 scan 不做 shape 包含/重叠几何判定，'
                 '不消费、不放宽 data-overlap-role 容器窄契约；该语义仍由 writing-reviewer v0.16+ render gate 负责。')
    lines.append('')
    return '\n'.join(lines)


def load_exemptions(path: Path) -> dict[tuple[str, int, str], dict]:
    """加载逐项豁免台账（JSON）。

    schema_version 1：items: [{file, svg_index, rule_id, reason?, adjudicated?}]
    键 = (file, svg_index, rule_id)；file 为 md 相对 book-root 路径，svg_index 0 基。
    逐项豁免而非整规则豁免：新图违规永远照报，豁免只覆盖已裁决的历史项。
    """
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as e:
        print(f'豁免台账不可读（fail-closed）：{path}：{e}', file=sys.stderr)
        raise SystemExit(2)
    if data.get('schema_version') != 1 or not isinstance(data.get('items'), list):
        print(f'豁免台账结构不符 schema_version 1：{path}', file=sys.stderr)
        raise SystemExit(2)
    table: dict[tuple[str, int, str], dict] = {}
    for it in data['items']:
        try:
            key = (str(it['file']), int(it['svg_index']), str(it['rule_id']))
        except (KeyError, TypeError, ValueError):
            print(f'豁免条目缺字段/类型错误：{it!r}', file=sys.stderr)
            raise SystemExit(2)
        if it['rule_id'] not in RULES:
            print(f'豁免条目 rule_id 未登记：{it["rule_id"]}', file=sys.stderr)
            raise SystemExit(2)
        table[key] = it
    return table


def apply_exemptions(files: list, table: dict[tuple[str, int, str], dict]) -> set[tuple[str, int, str]]:
    """把命中的豁免项从各文件 findings 中移除，返回实际命中的键集合。"""
    used: set[tuple[str, int, str]] = set()
    for fs in files:
        for r in fs.results:
            kept = []
            for f in r.findings:
                k = (f.file, f.svg_index, f.rule_id)
                if k in table:
                    used.add(k)
                else:
                    kept.append(f)
            r.findings = kept
        kept_side = []
        for f in fs.sidecar_findings:
            k = (f.file, f.svg_index, f.rule_id)
            if k in table:
                used.add(k)
            else:
                kept_side.append(f)
        fs.sidecar_findings = kept_side
    return used


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog='scan_consistency.py',
        description='svg-book-illustrator 成稿一致性 scan：对书稿内联 SVG 跑留白/箭头落点/marker/语法/sidecar 同步规则，只报告不改稿',
    )
    parser.add_argument('--book-root', help='书仓根目录（含 manuscript/；缺省时不扫描，仅显示本帮助性自检）')
    parser.add_argument('--report', help='完整 markdown 报告输出路径（缺省仅 stdout 汇总）')
    parser.add_argument('--padding', type=float, default=40.0, help='画布安全边距阈值 px（默认 40，style-guide §一）')
    parser.add_argument('--arrow-gap', type=float, default=8.0, help='箭头悬空判定阈值 px（默认 8，style-guide §5.5.3）')
    parser.add_argument('--fail-on', choices=('none', 'hard', 'any'), default='none',
                        help='按 findings 置非零退出码：none=总为0（只报告），hard=存在 hard，any=存在任意')
    parser.add_argument('--exemptions', help='逐项豁免台账 JSON 路径（schema_version 1；命中项不计 findings，未命中条目报警防台账漂移）')
    args = parser.parse_args(argv)

    if not args.book_root:
        parser.print_help()
        return 0
    book_root = Path(args.book_root).expanduser()
    if not book_root.is_dir():
        print(f'书仓根目录不存在：{book_root}', file=sys.stderr)
        return 2

    exemption_table: dict[tuple[str, int, str], dict] = {}
    if args.exemptions:
        exemption_table = load_exemptions(Path(args.exemptions).expanduser())

    md_files = discover_canonical(book_root)
    id_registry: dict[str, str] = {}
    files = [scan_file(p, book_root, args.padding, args.arrow_gap, id_registry) for p in md_files]

    used_keys: set[tuple[str, int, str]] = set()
    if exemption_table:
        used_keys = apply_exemptions(files, exemption_table)

    all_findings: list[Finding] = []
    for fs in files:
        for r in fs.results:
            all_findings.extend(r.findings)
        all_findings.extend(fs.sidecar_findings)
    total_svg = sum(fs.svg_count for fs in files)
    by_rule: Counter[str] = Counter(f.rule_id for f in all_findings)
    by_sev: Counter[str] = Counter(f.severity for f in all_findings)

    print(f'扫描完成：{len(files)} 份 canonical md，{total_svg} 张内联 SVG，'
          f'findings {len(all_findings)}（hard={by_sev.get("hard", 0)}，soft={by_sev.get("soft", 0)}）')
    if by_rule:
        print('按规则分布：')
        for rid in sorted(by_rule, key=lambda r: (-by_rule[r], r)):
            name, sev, _ = RULES[rid]
            print(f'  {rid}({sev}) {name}: {by_rule[rid]}')

    if exemption_table:
        unused = set(exemption_table) - used_keys
        print(f'豁免台账：命中 {len(used_keys)}/{len(exemption_table)} 项'
              f'（已裁决历史项,不计 findings;裁决日分布见台账）')
        if unused:
            print(f'⚠️ 未命中豁免条目 {len(unused)} 项（对应 finding 已消失或图已改,台账漂移,应清理）：',
                  file=sys.stderr)
            for k in sorted(unused):
                it = exemption_table[k]
                print(f'  - {k[2]} {k[0]} svg#{k[1]}（{it.get("adjudicated", "?")} 裁决）', file=sys.stderr)

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(build_report(files, args) + '\n', encoding='utf-8')
        print(f'完整报告已写入：{report_path}')

    if args.fail_on == 'hard' and by_sev.get('hard', 0):
        return 1
    if args.fail_on == 'any' and all_findings:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
