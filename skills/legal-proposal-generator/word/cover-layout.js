// 封面：装饰底图按 A4 页面定位；文字保留为可编辑 Word 表格。
// 坐标来自 designer references/cover-variants 的 Chromium 实测（毫米）。
const fs = require('fs');
const path = require('path');
const {Paragraph, TextRun, Table, TableRow, TableCell, Footer, ImageRun,
  WidthType, TableLayoutType, TableAnchorType, OverlapType, BorderStyle,
  AlignmentType, HorizontalPositionRelativeFrom, VerticalPositionRelativeFrom,
  TextWrappingType} = require('docx');
const mm = n => Math.round(n * 1440 / 25.4);
const none = {style: BorderStyle.NONE, size: 0};
const borders = {top: none, bottom: none, left: none, right: none,
  insideHorizontal: none, insideVertical: none};

function createCover(style, data, assetsDir, palette, font, decorData) {
  if (!/^[CDEF]$/.test(style)) throw new Error('未知封面：' + style);
  const items = [];
  const run = (text, size, color, bold = false, spacing = 0) => new TextRun({
    text, size: size * 2, color, bold, font, characterSpacing: spacing * 20,
  });
  const paragraph = (text, size, color, opts = {}) => new Paragraph({
    alignment: opts.align || AlignmentType.LEFT,
    spacing: {before: 0, after: 0, line: Math.round(size * 20 * (opts.leading || 1.4)), lineRule: 'exact'},
    children: [run(text, size, color, !!opts.bold, opts.spacing || 0)],
  });
  function box(x, y, width, children, opts = {}) {
    items.push(new Table({
      width: {size: mm(width), type: WidthType.DXA}, columnWidths: [mm(width)],
      layout: TableLayoutType.FIXED, borders,
      float: {horizontalAnchor: TableAnchorType.PAGE, verticalAnchor: TableAnchorType.PAGE,
        absoluteHorizontalPosition: mm(x), absoluteVerticalPosition: mm(y),
        overlap: OverlapType.OVERLAP, topFromText: 0, bottomFromText: 0, leftFromText: 0, rightFromText: 0},
      rows: [new TableRow({cantSplit: true, children: [new TableCell({
        borders: opts.border ? {top: opts.border, bottom: opts.border, left: opts.border, right: opts.border} : borders,
        margins: {top: mm(opts.padY || 0), bottom: mm(opts.padY || 0), left: 0, right: 0},
        ...(opts.fill ? {shading: {fill: opts.fill}} : {}), children,
      })]})],
    }));
  }
  const text = (x, y, w, value, size, color, opts) => box(x, y, w, [paragraph(value, size, color, opts)]);
  const badge = (y, width, solid = false, small = false) => box(22, y, width,
    [paragraph(data.badge, small ? 7.5 : 8.25, solid ? palette.onPrimary : palette.primary,
      {align: AlignmentType.CENTER, spacing: small ? 3 : 3.3})],
    {border: solid ? undefined : {style: BorderStyle.SINGLE, color: palette.primary, size: 9},
      fill: solid ? palette.primary : undefined, padY: 1.6});
  const meta = (y, {light = false, grid = false, plain = false} = {}) => {
    const values = [data.client, data.lawyer, data.date];
    const labels = ['委 托 人', '承办律师', '出具日期'];
    for (let i = 0; i < 3; i++) {
      const x = 22 + i * 55.333 + (plain || grid ? 0 : 4);
      const size = plain || grid ? 9.75 : 10.5;
      text(x, y, 50, labels[i], grid || plain ? 6.75 : 7.5,
        light ? palette.cream : palette.gold, {spacing: 1.5});
      text(x, y + 6.2, 50, values[i], size, light ? palette.onPrimary : palette.text, {bold: true});
    }
  };
  // 预先换行让底部锚定版式为两行题名留出空间；不裁掉或压缩文字。
  function titleLines(size, letterSpacing) {
    const limit = 166 / 25.4 * 72;
    let lines = [], line = '', used = 0;
    for (const char of data.title) {
      const width = (/[^\x00-\x7F]/.test(char) ? size : size * 0.55) + letterSpacing;
      if (line && used + width > limit) {lines.push(line); line = ''; used = 0;}
      line += char; used += width;
    }
    if (line) lines.push(line);
    if (lines.length > 3) throw new Error('封面标题超过三行，请缩短主标题并将说明移入副标题');
    return lines;
  }
  function title(y, size, spacing, color, leading = 1.4) {
    const lines = titleLines(size, spacing);
    box(22, y, 166, lines.map(value => paragraph(value, size, color, {bold: true, spacing, leading})));
    return lines.length * size * leading / 72 * 25.4;
  }
  if (style === 'C') {
    text(22, 18, 160, 'LEGAL SERVICE PROPOSAL', 8.25, palette.gold, {spacing: 3});
    text(22, 76.5, 166, data.lawFirm, 12, palette.cream, {bold: true, spacing: 6});
    badge(117, 57.7);
    const height = title(136.9, 27, 2.25, palette.deep);
    text(22, 136.9 + height + 6, 166, data.subtitle, 12, palette.gold, {spacing: 1.5});
    meta(238.5);
    text(22, 279, 110, data.lawFirm, 7.5, palette.gold, {spacing: 1.125});
    text(132, 279, 56, 'CONFIDENTIAL', 7.5, palette.gold, {align: AlignmentType.RIGHT, spacing: 1.125});
  } else if (style === 'D') {
    text(22, 24, 166, data.lawFirm, 11.25, palette.cream, {bold: true, spacing: 6});
    text(22, 35.5, 166, 'LEGAL SERVICE PROPOSAL', 7.5, palette.gold, {spacing: 3});
    const extra = (titleLines(27, 2.25).length - 1) * 13.335;
    badge(205.4 - extra, 49.6, false, true);
    title(221.4 - extra, 27, 2.25, palette.deep);
    text(22, 239.8, 166, data.subtitle, 11.25, palette.gold, {spacing: 1.5});
    meta(264.5, {plain: true});
  } else if (style === 'E') {
    text(22, 24, 100, data.lawFirm, 10.5, palette.primary, {bold: true, spacing: 5.25});
    text(112, 24, 76, 'LEGAL SERVICE PROPOSAL', 7.5, palette.gold, {align: AlignmentType.RIGHT, spacing: 3});
    badge(55, 52.8, true);
    const height = title(76.4, 28.5, 2.25, palette.deep);
    text(22, 76.4 + height + 6, 166, data.subtitle, 12, palette.gold, {spacing: 1.5});
    meta(249.7, {light: true});
    text(22, 271.5, 110, data.lawFirm, 7.5, palette.gold, {spacing: 1.125});
    text(132, 271.5, 56, 'CONFIDENTIAL', 7.5, palette.gold, {align: AlignmentType.RIGHT, spacing: 1.125});
  } else {
    text(22, 8.5, 100, data.lawFirm, 9.75, palette.primary, {bold: true, spacing: 4.5});
    text(112, 8.5, 76, 'LEGAL SERVICE PROPOSAL', 6.75, palette.gold, {align: AlignmentType.RIGHT, spacing: 2.25});
    const extra = (titleLines(28.5, 1.5).length - 1) * 13.07;
    text(22, 97.2 - extra, 166, data.badge, 8.25, palette.gold, {spacing: 3});
    title(109.1 - extra, 28.5, 1.5, palette.text, 1.3);
    text(22, 129.2, 166, data.subtitle, 10.5, palette.muted, {spacing: 1.5});
    meta(251.3, {grid: true});
    text(22, 284.5, 83, 'CONFIDENTIAL', 6.75, palette.gold, {spacing: 1.5});
    text(105, 284.5, 83, data.lawFirm, 6.75, palette.gold, {align: AlignmentType.RIGHT, spacing: 1.5});
  }
  const decor = new ImageRun({data: decorData || fs.readFileSync(path.join(assetsDir, 'assets', `cover-${style}.png`)), type: 'png',
    transformation: {width: 210 / 25.4 * 96, height: 297 / 25.4 * 96},
    floating: {horizontalPosition: {relative: HorizontalPositionRelativeFrom.PAGE, offset: 0},
      verticalPosition: {relative: VerticalPositionRelativeFrom.PAGE, offset: 0},
      behindDocument: true, allowOverlap: true, wrap: {type: TextWrappingType.NONE}},
  });
  return {children: [new Paragraph({spacing: {line: 1, lineRule: 'exact', after: 0}, children: [decor]}), ...items],
    footer: new Footer({children: [new Paragraph({spacing: {line: 1, lineRule: 'exact', after: 0}, children: []})]})};
}

module.exports = {createCover};
