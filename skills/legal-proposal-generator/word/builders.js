// builders.js — legal-proposal-word 设计组件库（OOXML via docx-js）
// 视觉基准：legal-proposal-designer（律所棕 #5A4E48 系 / cover-C 几何封面 / prose 规范）
// 供 render.js（逐案内容）与 template.js（OOXML 模板）共用。
// ⚠️ 跨引擎守则见 README「跨引擎兼容守则」：封面 wrapper 高度必须 ≤ 页高−下边距；
//    底部锚定用真页脚；exact 行内容不超行高 85%；改版后在真实 WPS + MS Word 各验证一次。
const path = require("path");
const {
  Document, Paragraph, TextRun, Table, TableRow, TableCell,
  Footer, PageNumber, NumberFormat, AlignmentType, HeadingLevel,
  WidthType, BorderStyle, ShadingType, SectionType, TableLayoutType,
  LevelFormat, PageOrientation, ImageRun,
  HorizontalPositionRelativeFrom, VerticalPositionRelativeFrom, TextWrappingType,
} = require("docx");
const fs = require("fs");

// ── 配色（与 legal-proposal-designer :root 一一对应）──
const LP = {
  primary: "5A4E48", deep: "3D342F", soft: "6E5F56", gold: "927F76",
  text: "1A1A1A", softText: "333333", muted: "666666",
  cream: "F5F0ED", card: "FAF7F4", softbg: "FAFAFA", rule: "CCCCCC",
};

const NB = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const noBorders = { top: NB, bottom: NB, left: NB, right: NB };
const allNoBorders = { top: NB, bottom: NB, left: NB, right: NB, insideHorizontal: NB, insideVertical: NB };

const FONT = { eastAsia: "SimSun", ascii: "Times New Roman" };

// 按路径嵌入照片（96dpi 像素 = 宽 cm×37.8）；无路径时返回占位框段落
function photoOrPlaceholder(pathOrToken, widthCm, placeholderText, ratio) {
  if (pathOrToken && !pathOrToken.includes("{{") && fs.existsSync(pathOrToken)) {
    const type = pathOrToken.toLowerCase().endsWith(".png") ? "png" : "jpg";
    return new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { after: 0 },
      children: [new ImageRun({ data: fs.readFileSync(pathOrToken), type,
        transformation: { width: Math.round(widthCm * 37.8), height: Math.round(widthCm * 37.8 * (ratio || 1.35)) } })],
    });
  }
  return new Paragraph({
    alignment: AlignmentType.CENTER, border: boxBorder(4, LP.rule),
    spacing: { line: Math.round(widthCm * 56.7), lineRule: "exact" },
    children: [new TextRun({ text: placeholderText || "照片", size: 18, color: LP.muted, font: FONT })],
  });
}

// 四边同色边框（照片位框等）
const boxBorder = (size, color) => { const b = { style: BorderStyle.SINGLE, size, color }; return { top: b, bottom: b, left: b, right: b }; };

// A4 页面常量
const PAGE = { width: 11906, height: 16838, margin: { top: 1417, bottom: 1200, left: 1417, right: 1417, footer: 794 } };
// 封面节边距：下边距 25mm 容纳页脚（14mm 距离 + 8mm 高），不触发引擎自动扩边距
const COVER_MARGIN = { top: 0, bottom: 1417, left: 0, right: 0, footer: 794 };

// ══════════════════ 封面 C（顶部几何，designer cover-C-geo）══════════════════
function buildCoverC(config, decorPngPath) {
  // 右上角装饰（金环+深棕圆）为透明前景层；棕色带本体由原生表格底色承担，
  // 即使浮动图在某引擎定位偏差，色带也绝不出错。
  const decor = new ImageRun({
    data: fs.readFileSync(decorPngPath), type: "png",
    transformation: { width: 794, height: 359 }, // 96dpi 像素 = 210mm × 95mm
    floating: {
      horizontalPosition: { relative: HorizontalPositionRelativeFrom.PAGE, offset: 0 },
      verticalPosition: { relative: VerticalPositionRelativeFrom.PAGE, offset: 0 },
      behindDocument: false, allowOverlap: true,
      wrap: { type: TextWrappingType.NONE },
    },
  });

  const inner = [];
  // 色带内：band-mark（金色小字，18mm）；首段承载装饰图锚点（line 40 exact 不占高度）
  inner.push(new Paragraph({
    spacing: { before: 1021, after: 0, line: 240, lineRule: "atLeast" },
    children: [
      decor,
      new TextRun({ text: "LEGAL SERVICE PROPOSAL", size: 17, color: LP.gold,
        characterSpacing: 60, font: FONT }),
    ],
  }));
  // 色带内：律所名（米白大字）
  inner.push(new Paragraph({
    spacing: { before: 2800, after: 0, line: 340, lineRule: "atLeast" },
    children: [new TextRun({ text: config.lawFirm, size: 24, bold: true, color: "F5F0ED",
      characterSpacing: 120, font: FONT })],
  }));
  // 徽章框：年份 · 法律服务方案
  const badgeBorder = { style: BorderStyle.SINGLE, size: 9, color: LP.primary, space: 4 };
  inner.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    indent: { right: 6200 }, // 配合 cell margins 1247 得约 57mm 框宽，改徽章文字需同步调整
    spacing: { before: 1250, after: 0, line: 280, lineRule: "atLeast" },
    border: { top: badgeBorder, bottom: badgeBorder, left: badgeBorder, right: badgeBorder },
    children: [new TextRun({ text: config.badge, size: 17, color: LP.primary,
      characterSpacing: 50, font: FONT })],
  }));
  // 主标题
  inner.push(new Paragraph({
    spacing: { before: 700, after: 0, line: 640, lineRule: "atLeast" },
    children: [new TextRun({ text: config.title, size: 54, bold: true, color: LP.deep,
      characterSpacing: 45, font: FONT })],
  }));
  // 副标题（金色）
  inner.push(new Paragraph({
    spacing: { before: 350, after: 0, line: 340, lineRule: "atLeast" },
    children: [new TextRun({ text: config.subtitle, size: 24, color: LP.gold,
      characterSpacing: 30, font: FONT })],
  }));
  // 信息栏顶线对齐 designer C 封面约 186mm；保留短 spacer，避免固定高度行挤压。
  inner.push(new Paragraph({ spacing: { before: 640, after: 0, line: 40, lineRule: "exact" }, children: [] }));
  inner.push(new Paragraph({ spacing: { before: 640, after: 0, line: 40, lineRule: "exact" }, children: [] }));
  const metaCell = (label, value, withLeftRule) => new TableCell({
    width: { size: 33.3, type: WidthType.PERCENTAGE },
    borders: withLeftRule ? { top: NB, bottom: NB, right: NB,
      left: { style: BorderStyle.SINGLE, size: 6, color: LP.rule } } : noBorders,
    margins: { top: 340, bottom: 100, left: withLeftRule ? 227 : 113, right: 113 },
    children: [
      new Paragraph({ spacing: { after: 80, line: 220, lineRule: "atLeast" },
        children: [new TextRun({ text: label, size: 15, color: LP.gold, characterSpacing: 30, font: FONT })] }),
      new Paragraph({ spacing: { line: 300, lineRule: "atLeast" },
        children: [new TextRun({ text: value, size: 21, bold: true, color: LP.text, characterSpacing: 15, font: FONT })] }),
    ],
  });
  // 信息表顶线用独立段落边框（避免表格边框与竖线交叉穿模）
  inner.push(new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: LP.primary, space: 1 } },
    spacing: { before: 0, after: 0, line: 40, lineRule: "exact" }, children: [],
  }));
  inner.push(new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    borders: allNoBorders,
    rows: [new TableRow({ cantSplit: true, children: [
      metaCell("委 托 人", config.client, false),
      metaCell("承办律师", config.lawyer, true),
      metaCell("出具日期", config.date, true),
    ] })],
  }));

  // 双行结构：行1 棕色带（原生底色 exact 95mm）；行2 白区。
  // ⚠️ 高度守恒：两行合计 15361 = 页高 16838 − 封面节下边距 1417 − 60 缇舍入缓冲。
  //    wrapper 总高绝不得超过正文可用区，否则 WPS 把溢出行推到新页（封面变两页）。
  const bandRow = new TableRow({
    height: { value: 5386, rule: "exact" },
    children: [new TableCell({
      shading: { type: ShadingType.CLEAR, fill: LP.primary }, borders: noBorders,
      verticalAlign: "top", margins: { left: 1247, right: 1247 },
      children: [inner[0], inner[1]],
    })],
  });
  const restRow = new TableRow({
    height: { value: 9975, rule: "exact" },
    children: [new TableCell({
      borders: noBorders, verticalAlign: "top", margins: { left: 1247, right: 1247 },
      children: inner.slice(2),
    })],
  });
  return [new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    layout: TableLayoutType.FIXED,
    borders: allNoBorders,
    rows: [bandRow, restRow],
  })];
}

// 最小空页脚：⚠️ 封面节必须挂任意页脚——零边距页 + 通高 exact 表格 + 无页脚会让
// LibreOffice/预览陷入布局死循环（挂死）；空页脚占位即可规避，不产生可见内容。
function coverFooterBlank() {
  return new Footer({ children: [new Paragraph({
    spacing: { before: 0, after: 0, line: 40, lineRule: "exact" }, children: [] })] });
}

// 封面页脚：灰细线（designer cover-footer 用 --rule 灰，区别于正文页脚的金线）+ 左律所 / 右 CONFIDENTIAL
function coverFooter(lawFirm) {
  return new Footer({ children: [new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    borders: allNoBorders,
    rows: [new TableRow({ children: [new TableCell({
      borders: noBorders, margins: { left: 0, right: 0, top: 0, bottom: 0 },
      children: [
        new Paragraph({
          border: { top: { style: BorderStyle.SINGLE, size: 6, color: LP.rule, space: 1 } },
          spacing: { before: 0, after: 280, line: 40, lineRule: "exact" }, children: [],
        }),
        new Table({
          width: { size: 100, type: WidthType.PERCENTAGE },
          borders: allNoBorders,
          rows: [new TableRow({ cantSplit: true, children: [
            new TableCell({ width: { size: 60, type: WidthType.PERCENTAGE }, borders: noBorders,
              margins: { top: 0, bottom: 0, left: 1247, right: 0 },
              children: [new Paragraph({ spacing: { line: 220, lineRule: "atLeast" },
                children: [new TextRun({ text: lawFirm, size: 15, color: LP.gold, characterSpacing: 22, font: FONT })] })] }),
            new TableCell({ width: { size: 40, type: WidthType.PERCENTAGE }, borders: noBorders,
              margins: { top: 0, bottom: 0, left: 0, right: 1247 },
              children: [new Paragraph({ alignment: AlignmentType.RIGHT, spacing: { line: 220, lineRule: "atLeast" },
                children: [new TextRun({ text: "CONFIDENTIAL", size: 15, color: LP.gold, characterSpacing: 22, font: FONT })] })] }),
          ] })],
        }),
      ],
    })] })],
  })] });
}

// ══════════════════ 正文构件（designer prose 规范）══════════════════
// 章标题：.prose h2 —— 13pt 加粗主色 + 左侧粗竖线
function h1(text, opts = {}) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1, keepNext: true,
    pageBreakBefore: !!opts.pageBreakBefore,
    spacing: { before: opts.pageBreakBefore ? 120 : 510, after: 227, line: 400, lineRule: "atLeast" },
    border: { left: { style: BorderStyle.SINGLE, size: 30, color: LP.primary, space: 8 } },
    children: [new TextRun({ text, bold: true, size: 26, color: LP.primary, font: FONT })],
  });
}
// 节标题：.prose h3 —— 法律文书式，12pt 加粗黑字 + 首行缩进
function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2, keepNext: true,
    indent: { firstLine: 480 },
    spacing: { before: 227, after: 113, line: 360, lineRule: "atLeast" },
    children: [new TextRun({ text, bold: true, size: 24, color: LP.text, font: FONT })],
  });
}
// 正文段：对应 HTML .prose p 的 12pt / 2.1 倍行距 / 首行缩进 2 字符
function body(text, opts = {}) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    indent: { firstLine: 480 },
    spacing: { line: 504, after: opts.after !== undefined ? opts.after : 170 },
    children: [new TextRun({ text, size: 24, color: LP.text, font: FONT })],
  });
}
// 富文本段：加粗词用主色（.prose strong）
function bodyRuns(runs, opts = {}) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    indent: { firstLine: 480 },
    spacing: { line: 504, after: opts.after !== undefined ? opts.after : 170 },
    children: runs.map(r => new TextRun({ text: r.t, bold: !!r.bold, size: 24,
      color: r.bold ? LP.primary : LP.text, font: FONT })),
  });
}
function listItem(reference, text) {
  return new Paragraph({
    numbering: { reference, level: 0 },
    alignment: AlignmentType.JUSTIFIED,
    spacing: { line: 432, after: 68 },
    children: [new TextRun({ text, size: 24, color: LP.text, font: FONT })],
  });
}
// 法条/引文块：.prose blockquote —— 浅灰底 + 金色左线 + 11.5pt
function lawQuote(label, lines) {
  const paragraphs = [];
  if (label) paragraphs.push(new Paragraph({
    spacing: { after: lines.length ? 80 : 0, line: 345 },
    children: [new TextRun({ text: label, bold: true, size: 23, color: LP.primary, font: FONT })],
  }));
  lines.forEach((t, i) => paragraphs.push(new Paragraph({
    alignment: AlignmentType.JUSTIFIED, spacing: { after: i === lines.length - 1 ? 0 : 80, line: 345 },
    children: [new TextRun({ text: t, size: 23, color: LP.softText, font: FONT })],
  })));
  return [new Table({
    width: { size: 100, type: WidthType.PERCENTAGE }, layout: TableLayoutType.FIXED,
    borders: allNoBorders,
    rows: [new TableRow({ cantSplit: true, children: [new TableCell({
      shading: { type: ShadingType.CLEAR, fill: LP.softbg },
      borders: { top: NB, bottom: NB, right: NB,
        left: { style: BorderStyle.SINGLE, size: 18, color: LP.gold } },
      margins: { top: 170, bottom: 170, left: 340, right: 340 },
      children: paragraphs,
    })] })],
  })];
}
// 表格：主色表头白字 + 米白斑马纹 + 灰色横线（.prose table）
function makeTable(headers, rows, widths, boldLastCol) {
  const headerRow = new TableRow({
    tableHeader: true, cantSplit: true,
    children: headers.map((text, i) => new TableCell({
      children: [new Paragraph({ spacing: { line: 280 },
        children: [new TextRun({ text, bold: true, size: 21, color: "FFFFFF", font: FONT })] })],
      shading: { type: ShadingType.CLEAR, fill: LP.primary },
      margins: { top: 100, bottom: 100, left: 120, right: 120 },
      width: { size: widths[i], type: WidthType.PERCENTAGE },
    })),
  });
  const dataRows = rows.map((cells, ri) => new TableRow({
    cantSplit: true,
    children: cells.map((text, i) => {
      const isLast = boldLastCol && i === cells.length - 1;
      return new TableCell({
        children: [new Paragraph({
          alignment: isLast ? AlignmentType.CENTER : AlignmentType.JUSTIFIED,
          spacing: { line: 280 },
          children: [new TextRun({ text, size: 21, bold: isLast,
            color: isLast ? LP.primary : LP.text, font: FONT })] })],
        shading: { type: ShadingType.CLEAR, fill: ri % 2 === 0 ? LP.cream : "FFFFFF" },
        margins: { top: 100, bottom: 100, left: 120, right: 120 },
        width: { size: widths[i], type: WidthType.PERCENTAGE },
      });
    }),
  }));
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    layout: TableLayoutType.FIXED,
    borders: { top: NB, bottom: { style: BorderStyle.SINGLE, size: 6, color: LP.rule },
      left: NB, right: NB, insideVertical: NB,
      insideHorizontal: { style: BorderStyle.SINGLE, size: 6, color: LP.rule } },
    rows: [headerRow, ...dataRows],
  });
}
// 正文首页/后部页 section-header：小标签 + 题名 + 主色粗底线
function sectionHeader(label, title, opts = {}) {
  return [
    new Paragraph({
      pageBreakBefore: !!opts.pageBreakBefore,
      spacing: { before: 0, after: 60, line: 240, lineRule: "atLeast" },
      children: [new TextRun({ text: label, size: 15, color: LP.muted, characterSpacing: 60, font: FONT })] }),
    new Paragraph({
      spacing: { after: opts.pageBreakBefore ? 400 : 510, line: 400, lineRule: "atLeast" },
      border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: LP.primary, space: 4 } },
      children: [new TextRun({ text: title, bold: true, size: 32, color: LP.primary, characterSpacing: 30, font: FONT })],
    }),
  ];
}
// 正文页脚使用跨 Word/LibreOffice 可更新的 PAGE 字段；后部页脚按 HTML 显示页名。
function sectionFooter(lawFirm, rightChildren) {
  return new Footer({ children: [new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    borders: { top: { style: BorderStyle.SINGLE, size: 6, color: LP.gold },
      bottom: NB, left: NB, right: NB, insideHorizontal: NB, insideVertical: NB },
    rows: [new TableRow({ children: [
      new TableCell({ width: { size: 45, type: WidthType.PERCENTAGE }, margins: { top: 100, left: 0, right: 0 },
        children: [new Paragraph({ spacing: { line: 220, lineRule: "atLeast" },
          children: [new TextRun({ text: lawFirm, size: 15, color: LP.muted, characterSpacing: 20, font: FONT })] })] }),
      new TableCell({ width: { size: 55, type: WidthType.PERCENTAGE }, margins: { top: 100, left: 0, right: 0 },
        children: [new Paragraph({ alignment: AlignmentType.RIGHT, spacing: { line: 220, lineRule: "atLeast" },
          children: rightChildren })] }),
    ] })],
  })] });
}
const footerRun = (text) => new TextRun({ text, size: 15, color: LP.muted, characterSpacing: 20, font: FONT });
function bodyFooter(lawFirm) {
  return sectionFooter(lawFirm, [
    footerRun("法律服务方案 · 第 "),
    new TextRun({ children: [PageNumber.CURRENT], size: 15, color: LP.muted, font: FONT }),
    footerRun(" 页"),
  ]);
}
function backFooter(lawFirm, label) { return sectionFooter(lawFirm, [footerRun(label)]); }

// ══════════════════ 后部固定页构件（designer back pages）══════════════════
// 承办团队卡片：.team-card —— 卡片底 + 主色左粗线，左照片位 + 右五组字段
function teamCard(f) {
  const cardBorder = { top: NB, bottom: NB, right: NB,
    left: { style: BorderStyle.SINGLE, size: 24, color: LP.primary } };
  const field = (label, value) => value ? new Paragraph({
    alignment: AlignmentType.JUSTIFIED, spacing: { after: 60, line: 300 },
    children: [
      new TextRun({ text: label, bold: true, size: 21, color: LP.primary, font: FONT }),
      new TextRun({ text: value, size: 21, color: LP.softText, font: FONT }),
    ],
  }) : null;
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    borders: { top: NB, bottom: NB, right: NB, left: cardBorder.left, insideHorizontal: NB, insideVertical: NB },
    rows: [new TableRow({ cantSplit: true, children: [
      new TableCell({
        width: { size: 24, type: WidthType.PERCENTAGE },
        shading: { type: ShadingType.CLEAR, fill: LP.card }, borders: noBorders,
        margins: { top: 200, bottom: 200, left: 240, right: 120 },
        verticalAlign: "center",
        children: [f.photoPath
          ? photoOrPlaceholder(f.photoPath, 3.0, null, f.photoRatio)
          : new Paragraph({
              alignment: AlignmentType.CENTER, border: boxBorder(4, LP.rule),
              spacing: { line: 1985, lineRule: "exact" }, // 3.5cm 照片位框
              children: [new TextRun({ text: f.photo || "头像待补充", size: 18, color: LP.muted, font: FONT })],
            })],
      }),
      new TableCell({
        width: { size: 76, type: WidthType.PERCENTAGE },
        shading: { type: ShadingType.CLEAR, fill: LP.card }, borders: noBorders,
        margins: { top: 200, bottom: 200, left: 200, right: 240 },
        children: [
          new Paragraph({ spacing: { after: 40, line: 340, lineRule: "atLeast" },
            children: [new TextRun({ text: f.name, bold: true, size: 26, color: LP.primary, font: FONT })] }),
          new Paragraph({ spacing: { after: 120, line: 240, lineRule: "atLeast" },
            children: [new TextRun({ text: f.title || '', size: 18, color: LP.muted, font: FONT })] }),
          field("教育背景：", f.edu),
          field("服务企业：", f.corp),
          field("专业领域：", f.field),
        ].filter(Boolean),
      }),
    ] })],
  });
}
// 律所简介卡：.firm-intro —— 米白底 + 金色左粗线，可含照片位与多段简介
function firmIntroCard(paragraphTexts, photoToken, photoRatio) {
  const children = [];
  if (photoToken && photoToken.includes("{{")) children.push(new Paragraph({
    alignment: AlignmentType.CENTER, border: boxBorder(4, LP.rule),
    spacing: { before: 0, after: 160, line: 2260, lineRule: "exact" }, // 4cm 照片位框
    children: [new TextRun({ text: photoToken, size: 18, color: LP.muted, font: FONT })],
  }));
  else if (photoToken) children.push(photoOrPlaceholder(photoToken, 8.0, null, photoRatio));
  paragraphTexts.forEach((t, i) => children.push(new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    indent: { firstLine: 480 },
    spacing: { after: i === paragraphTexts.length - 1 ? 0 : 120, line: 400 },
    children: [new TextRun({ text: t, size: 24, color: LP.text, font: FONT })],
  })));
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    borders: { top: NB, bottom: NB, right: NB,
      left: { style: BorderStyle.SINGLE, size: 24, color: LP.gold },
      insideHorizontal: NB, insideVertical: NB },
    rows: [new TableRow({ children: [new TableCell({
      shading: { type: ShadingType.CLEAR, fill: LP.cream }, borders: noBorders,
      margins: { top: 300, bottom: 300, left: 340, right: 340 },
      children,
    })] })],
  });
}
// 律所荣誉列表：金棕序号 + 加粗条目 + 说明，条目间灰横线（.honor-item）
function honorTable(items) {
  const rows = items.map(it => new TableRow({
    cantSplit: true,
    children: [
      new TableCell({
        width: { size: 9, type: WidthType.PERCENTAGE },
        // 不声明单元格级 borders——否则会覆盖表格级 insideHorizontal 灰横线
        margins: { top: 160, bottom: 160, left: 60, right: 120 },
        children: [new Paragraph({ spacing: { line: 300 },
          children: [new TextRun({ text: it.num, bold: true, size: 24, color: LP.gold, font: FONT })] })],
      }),
      new TableCell({
        width: { size: 91, type: WidthType.PERCENTAGE },
        margins: { top: 160, bottom: 160, left: 60, right: 60 },
        children: [
          new Paragraph({ spacing: { after: 40, line: 320, lineRule: "atLeast" },
            children: [new TextRun({ text: it.title, bold: true, size: 24, color: LP.primary, font: FONT })] }),
          it.desc ? new Paragraph({ alignment: AlignmentType.JUSTIFIED, spacing: { line: 320 },
            children: [new TextRun({ text: it.desc, size: 22, color: LP.softText, font: FONT })] }) : null,
        ].filter(Boolean),
      }),
    ],
  }));
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    layout: TableLayoutType.FIXED, // 无此设置时引擎 autofit 会无视百分比列宽（序号列被拉宽）
    borders: { top: NB, bottom: NB, left: NB, right: NB,
      insideHorizontal: { style: BorderStyle.SINGLE, size: 6, color: LP.rule }, insideVertical: NB },
    rows,
  });
}
// 典型案例 2×2 网格：照片位框 + 图注
function caseGrid(items) { // items: [{img, cap}] × 4
  const mkCell = (it) => new TableCell({
    width: { size: 50, type: WidthType.PERCENTAGE }, borders: noBorders,
    margins: { top: 120, bottom: 120, left: 100, right: 100 },
    children: [
      it.photoPath
        ? photoOrPlaceholder(it.photoPath, 5.0, null, it.photoRatio) // ⚠️ 直接用返回的段落，不可再包一层 Paragraph（嵌套段落会被 docx-js 静默丢弃）
        : new Paragraph({
            alignment: AlignmentType.CENTER, border: boxBorder(4, LP.rule),
            spacing: { line: 2835, lineRule: "exact" }, // 5cm 照片位框
            children: [new TextRun({ text: it.img, size: 18, color: LP.muted, font: FONT })],
          }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80, line: 260 },
        children: [new TextRun({ text: it.cap, size: 19, color: LP.softText, font: FONT })] }),
    ],
  });
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    borders: allNoBorders,
    rows: [
      new TableRow({ cantSplit: true, children: [mkCell(items[0]), mkCell(items[1])] }),
      new TableRow({ cantSplit: true, children: [mkCell(items[2]), mkCell(items[3])] }),
    ],
  });
}
// 落款：右对齐 律所 / 律师 / 日期（render.py align_signature 的对应物）
function signatureBlock(firm, lawyer, date) {
  const line = (text, before) => new Paragraph({
    alignment: AlignmentType.RIGHT,
    spacing: { before, after: 40, line: 360 },
    children: [new TextRun({ text, size: 24, color: LP.text, font: FONT })],
  });
  return [line(firm, 480), line(lawyer, 40), line(date, 40)];
}

// ══════════════════ 文档级装配 ══════════════════
function docStyles() {
  return { default: {
    document: {
      run: { font: FONT, size: 24, color: LP.text },
      paragraph: { spacing: { line: 504 } },
    },
    heading1: {
      run: { font: FONT, size: 26, bold: true, color: LP.primary },
      paragraph: { spacing: { before: 510, after: 227, line: 400 }, outlineLevel: 0 },
    },
    heading2: {
      run: { font: FONT, size: 24, bold: true, color: LP.text },
      paragraph: { spacing: { before: 227, after: 113, line: 360 }, outlineLevel: 1 },
    },
  } };
}
function makeNumbering(references) {
  return { config: references.map(entry => {
    const {reference, ordered = true} = typeof entry === 'string' ? {reference: entry} : entry;
    return {
      reference,
      levels: [{ level: 0, format: ordered ? LevelFormat.DECIMAL : LevelFormat.BULLET,
        text: ordered ? "%1." : "•", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } } }],
    };
  }) };
}
function makeSection(opts) { // opts: { pageNumbersStart?, cover?:bool, footer, children }
  const margin = opts.cover ? COVER_MARGIN : PAGE.margin;
  const properties = {
    type: opts.cover ? undefined : SectionType.NEXT_PAGE,
    page: {
      size: { width: PAGE.width, height: PAGE.height, orientation: PageOrientation.PORTRAIT },
      margin,
      ...(opts.pageNumbersStart ? { pageNumbers: { start: opts.pageNumbersStart, formatType: NumberFormat.DECIMAL } } : {}),
    },
  };
  return {
    properties,
    ...(opts.footer ? { footers: { default: opts.footer } } : {}),
    children: opts.children,
  };
}


// 封面三栏信息表共享构件（C/D 用；顶线由调用方以独立段落边框绘制，竖线挂第二/三列左边框）
function coverMetaTable(config) {
  const metaCell = (label, value, withLeftRule) => new TableCell({
    width: { size: 33.3, type: WidthType.PERCENTAGE },
    borders: withLeftRule ? { top: NB, bottom: NB, right: NB,
      left: { style: BorderStyle.SINGLE, size: 6, color: LP.rule } } : noBorders,
    margins: { top: 340, bottom: 100, left: withLeftRule ? 227 : 113, right: 113 },
    children: [
      new Paragraph({ spacing: { after: 80, line: 220, lineRule: "atLeast" },
        children: [new TextRun({ text: label, size: 15, color: LP.gold, characterSpacing: 30, font: FONT })] }),
      new Paragraph({ spacing: { line: 300, lineRule: "atLeast" },
        children: [new TextRun({ text: value, size: 21, bold: true, color: LP.text, characterSpacing: 15, font: FONT })] }),
    ],
  });
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    borders: allNoBorders,
    rows: [new TableRow({ cantSplit: true, children: [
      metaCell("委 托 人", config.client, false),
      metaCell("承办律师", config.lawyer, true),
      metaCell("出具日期", config.date, true),
    ] })],
  });
}

// ══════════════════ 封面 D（对角斜切，designer cover-D-diagonal）══════════════════
// 上部棕色斜切多边形 + 金环由 cover-D-decor.png（210×150mm 透明层）承担；
// 行1 白底 exact 150mm 承载斜切区文字（左侧深在棕内），行2 白区承载底部块。
function buildCoverD(config, decorPngPath) {
  const decor = new ImageRun({
    data: fs.readFileSync(decorPngPath), type: "png",
    transformation: { width: 794, height: 567 }, // 210×150mm @96dpi
    floating: {
      horizontalPosition: { relative: HorizontalPositionRelativeFrom.PAGE, offset: 0 },
      verticalPosition: { relative: VerticalPositionRelativeFrom.PAGE, offset: 0 },
      behindDocument: true, // 行底为白色，棕色多边形由本图提供；衬于文字后避免盖住律所名
      allowOverlap: true,
      wrap: { type: TextWrappingType.NONE },
    },
  });
  const row1Children = [
    new Paragraph({ // 斜切区：律所名（米白）+ 小标签（金色），锚定装饰图
      spacing: { before: 1361, after: 0, line: 300, lineRule: "atLeast" },
      children: [
        decor,
        new TextRun({ text: config.lawFirm, size: 22, bold: true, color: "F5F0ED",
          characterSpacing: 110, font: FONT }),
      ],
    }),
    new Paragraph({
      spacing: { before: 340, after: 0, line: 220, lineRule: "atLeast" },
      children: [new TextRun({ text: "LEGAL SERVICE PROPOSAL", size: 15, color: LP.gold,
        characterSpacing: 55, font: FONT })],
    }),
  ];
  const badgeBorder = { style: BorderStyle.SINGLE, size: 9, color: LP.primary, space: 4 };
  const row2Children = [
    new Paragraph({ // 底部块整体下推（cv-bottom 钉底 → spacer 近似）
      spacing: { before: 1150, after: 0, line: 40, lineRule: "exact" }, children: [] }),
    new Paragraph({
      alignment: AlignmentType.CENTER, indent: { right: 6800 },
      spacing: { before: 0, after: 0, line: 260, lineRule: "atLeast" },
      border: { top: badgeBorder, bottom: badgeBorder, left: badgeBorder, right: badgeBorder },
      children: [new TextRun({ text: config.badge, size: 15, color: LP.primary,
        characterSpacing: 55, font: FONT })],
    }),
    new Paragraph({
      spacing: { before: 620, after: 0, line: 640, lineRule: "atLeast" },
      children: [new TextRun({ text: config.title, size: 54, bold: true, color: LP.deep,
        characterSpacing: 45, font: FONT })],
    }),
    new Paragraph({
      spacing: { before: 300, after: 0, line: 320, lineRule: "atLeast" },
      children: [new TextRun({ text: config.subtitle, size: 22, color: LP.gold,
        characterSpacing: 30, font: FONT })],
    }),
    new Paragraph({ spacing: { before: 740, after: 0, line: 40, lineRule: "exact" }, children: [] }),
    new Paragraph({
      border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: LP.primary, space: 1 } },
      spacing: { before: 0, after: 0, line: 40, lineRule: "exact" }, children: [],
    }),
    coverMetaTable(config),
  ];
  // 高度守恒：8505(150mm) + 6856 = 15361 ≤ 15421 ✓
  return [new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    layout: TableLayoutType.FIXED, borders: allNoBorders,
    rows: [
      new TableRow({ height: { value: 8505, rule: "exact" },
        children: [new TableCell({ borders: noBorders, verticalAlign: "top",
          margins: { left: 1247, right: 1247 }, children: row1Children })] }),
      new TableRow({ height: { value: 6856, rule: "exact" },
        children: [new TableCell({ borders: noBorders, verticalAlign: "top",
          margins: { left: 1247, right: 1247 }, children: row2Children })] }),
    ],
  })];
}

// ══════════════════ 封面 E（底部反转，designer cover-E-flip）══════════════════
// 上白：左上律所名+右上小标签、实心棕底白字徽章、大标题；下棕带：金线三栏信息表+带内页脚。
// 装饰（左下金环+深棕圆）由 cover-E-decor.png（210×77mm 透明层）锚定棕带。
function buildCoverE(config, decorPngPath) {
  const bandTopMm = 199; // 带行顶 = wrapper 高 15361 缇 = 270.97mm − 带高 71.98mm ≈ 199mm
  const decorOffsetEmu = Math.round(bandTopMm / 25.4 * 914400);
  const decor = new ImageRun({
    data: fs.readFileSync(decorPngPath), type: "png",
    transformation: { width: 794, height: 272 }, // 210×72mm @96dpi，与带行精确对齐
    floating: {
      horizontalPosition: { relative: HorizontalPositionRelativeFrom.PAGE, offset: 0 },
      verticalPosition: { relative: VerticalPositionRelativeFrom.PAGE, offset: decorOffsetEmu },
      behindDocument: false, allowOverlap: true,
      wrap: { type: TextWrappingType.NONE },
    },
  });
  const row1Children = [
    new Table({ // 左上律所名 / 右上小标签
      width: { size: 100, type: WidthType.PERCENTAGE }, borders: allNoBorders,
      rows: [new TableRow({ children: [
        new TableCell({ width: { size: 55, type: WidthType.PERCENTAGE }, borders: noBorders,
          children: [new Paragraph({ spacing: { line: 260, lineRule: "atLeast" },
            children: [new TextRun({ text: config.lawFirm, size: 22, bold: true, color: LP.primary,
              characterSpacing: 95, font: FONT })] })] }),
        new TableCell({ width: { size: 45, type: WidthType.PERCENTAGE }, borders: noBorders,
          children: [new Paragraph({ alignment: AlignmentType.RIGHT, spacing: { line: 220, lineRule: "atLeast" },
            children: [new TextRun({ text: "LEGAL SERVICE PROPOSAL", size: 15, color: LP.gold,
              characterSpacing: 55, font: FONT })] })] }),
      ] })],
    }),
    new Paragraph({ spacing: { before: 2440, after: 0, line: 40, lineRule: "exact" }, children: [] }),
  ];
  // 实心棕底白字徽章（E 的识别特征；小表 hug 内容）
  row1Children.push(new Table({
    width: { size: 3230, type: WidthType.DXA }, borders: allNoBorders,
    rows: [new TableRow({ cantSplit: true, children: [new TableCell({
      shading: { type: ShadingType.CLEAR, fill: LP.primary }, borders: noBorders,
      margins: { top: 120, bottom: 120, left: 100, right: 100 },
      children: [new Paragraph({ alignment: AlignmentType.CENTER, spacing: { line: 240, lineRule: "atLeast" },
        children: [new TextRun({ text: config.badge, size: 17, color: "FFFFFF",
          characterSpacing: 55, font: FONT })] })],
    })] })],
  }));
  row1Children.push(new Paragraph({
    spacing: { before: 700, after: 0, line: 640, lineRule: "atLeast" },
    children: [new TextRun({ text: config.title, size: 54, bold: true, color: LP.deep,
      characterSpacing: 45, font: FONT })],
  }));
  row1Children.push(new Paragraph({
    spacing: { before: 340, after: 0, line: 340, lineRule: "atLeast" },
    children: [new TextRun({ text: config.subtitle, size: 24, color: LP.gold,
      characterSpacing: 30, font: FONT })],
  }));
  // 棕带（行2）：装饰锚点 + 金线三栏信息表（标签米白/数值纯白）+ 带内页脚
  const bandMetaCell = (label, value, withLeftRule) => new TableCell({
    width: { size: 33.3, type: WidthType.PERCENTAGE },
    borders: withLeftRule ? { top: NB, bottom: NB, right: NB,
      left: { style: BorderStyle.SINGLE, size: 6, color: LP.gold } } : noBorders,
    margins: { top: 240, bottom: 60, left: withLeftRule ? 227 : 113, right: 113 },
    children: [
      new Paragraph({ spacing: { after: 70, line: 210, lineRule: "atLeast" },
        children: [new TextRun({ text: label, size: 15, color: "F5F0ED", characterSpacing: 30, font: FONT })] }),
      new Paragraph({ spacing: { line: 290, lineRule: "atLeast" },
        children: [new TextRun({ text: value, size: 21, bold: true, color: "FFFFFF", characterSpacing: 15, font: FONT })] }),
    ],
  });
  const row2Children = [
    new Paragraph({ spacing: { before: 1134, after: 0, line: 40, lineRule: "exact" }, children: [decor] }),
    new Paragraph({
      border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: LP.gold, space: 1 } },
      spacing: { before: 0, after: 0, line: 40, lineRule: "exact" }, children: [],
    }),
    new Table({
      width: { size: 100, type: WidthType.PERCENTAGE }, borders: allNoBorders,
      rows: [new TableRow({ cantSplit: true, children: [
        bandMetaCell("委 托 人", config.client, false),
        bandMetaCell("承办律师", config.lawyer, true),
        bandMetaCell("出具日期", config.date, true),
      ] })],
    }),
    new Paragraph({ spacing: { before: 560, after: 0, line: 40, lineRule: "exact" }, children: [] }),
    new Table({
      width: { size: 100, type: WidthType.PERCENTAGE }, borders: allNoBorders,
      rows: [new TableRow({ children: [
        new TableCell({ width: { size: 60, type: WidthType.PERCENTAGE }, borders: noBorders,
          children: [new Paragraph({ spacing: { line: 220, lineRule: "atLeast" },
            children: [new TextRun({ text: config.lawFirm, size: 15, color: LP.gold, characterSpacing: 22, font: FONT })] })] }),
        new TableCell({ width: { size: 40, type: WidthType.PERCENTAGE }, borders: noBorders,
          children: [new Paragraph({ alignment: AlignmentType.RIGHT, spacing: { line: 220, lineRule: "atLeast" },
            children: [new TextRun({ text: "CONFIDENTIAL", size: 15, color: LP.gold, characterSpacing: 22, font: FONT })] })] }),
      ] })],
    }),
  ];
  // 高度守恒：11282 + 4079 = 15361 ✓（棕带 exact 4079 ≈ 72mm）
  return [new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    layout: TableLayoutType.FIXED, borders: allNoBorders,
    rows: [
      new TableRow({ height: { value: 11282, rule: "exact" },
        children: [new TableCell({ borders: noBorders, verticalAlign: "top",
          margins: { left: 1247, right: 1247 }, children: row1Children })] }),
      new TableRow({ height: { value: 4079, rule: "exact" },
        children: [new TableCell({
          shading: { type: ShadingType.CLEAR, fill: LP.primary }, borders: noBorders,
          verticalAlign: "top", margins: { left: 1247, right: 1247 }, children: row2Children })] }),
    ],
  })];
}

// ══════════════════ 封面 F（瑞士网格，designer cover-F-grid）══════════════════
// 全白、无图片：上下通栏主色横线 + 左右灰竖线（行2/行3 单元格边框）+ 主色方块 + 极简字排。
function buildCoverF(config) {
  const gridRule = { style: BorderStyle.SINGLE, size: 7, color: LP.rule };   // 0.3mm 灰竖线
  const strongRule = { style: BorderStyle.SINGLE, size: 12, color: LP.primary }; // 0.6mm 主色横线
  const metaCell = (label, value) => new TableCell({
    width: { size: 33.3, type: WidthType.PERCENTAGE }, borders: noBorders,
    margins: { top: 0, bottom: 0, left: 0, right: 200 },
    children: [
      new Paragraph({ spacing: { after: 70, line: 210, lineRule: "atLeast" },
        children: [new TextRun({ text: label, size: 15, color: LP.gold, characterSpacing: 40, font: FONT })] }),
      new Paragraph({ spacing: { line: 290, lineRule: "atLeast" },
        children: [new TextRun({ text: value, size: 21, bold: true, color: LP.text, font: FONT })] }),
    ],
  });
  const cellWithSideRules = (children, height) => new TableRow({
    height: { value: height, rule: "exact" },
    children: [new TableCell({
      borders: noBorders, verticalAlign: "top", margins: { left: 1247, right: 1247 },
      children: [new Table({ // 嵌套表边界 = 22/188mm 内容列边界，左右灰竖线画在此处
        width: { size: 100, type: WidthType.PERCENTAGE },
        borders: { top: NB, bottom: NB, insideHorizontal: NB, insideVertical: NB,
          left: gridRule, right: gridRule },
        rows: [new TableRow({ children: [new TableCell({
          // ⚠️ 竖线必须声明在单元格级：单元格 noBorders 会覆盖表格级左右边框（荣誉页同款坑）
          borders: { top: NB, bottom: NB, left: gridRule, right: gridRule },
          verticalAlign: "top", margins: { left: 120, right: 120 },
          children,
        })] })],
      })],
    })],
  });
  const row1 = new TableRow({
    height: { value: 1247, rule: "exact" },
    children: [new TableCell({ borders: { top: NB, left: NB, right: NB, bottom: strongRule },
      verticalAlign: "top", margins: { left: 1247, right: 1247 },
      children: [new Table({
        width: { size: 100, type: WidthType.PERCENTAGE }, borders: allNoBorders,
        rows: [new TableRow({ children: [
          new TableCell({ width: { size: 55, type: WidthType.PERCENTAGE }, borders: noBorders,
            children: [new Paragraph({ spacing: { before: 480, line: 260, lineRule: "atLeast" },
              children: [new TextRun({ text: config.lawFirm, size: 21, bold: true, color: LP.primary,
                characterSpacing: 85, font: FONT })] })] }),
          new TableCell({ width: { size: 45, type: WidthType.PERCENTAGE }, borders: noBorders,
            children: [new Paragraph({ alignment: AlignmentType.RIGHT, spacing: { before: 540, line: 220, lineRule: "atLeast" },
              children: [new TextRun({ text: "LEGAL SERVICE PROPOSAL", size: 14, color: LP.gold,
                characterSpacing: 40, font: FONT })] })] }),
        ] })],
      })] })],
  });
  const row2 = cellWithSideRules([
    new Table({ // 主色方块 14mm，右对齐（cv-dot）
      alignment: AlignmentType.RIGHT,
      width: { size: 794, type: WidthType.DXA }, borders: allNoBorders,
      rows: [new TableRow({ height: { value: 794, rule: "exact" }, children: [new TableCell({
        shading: { type: ShadingType.CLEAR, fill: LP.primary }, borders: noBorders,
        children: [new Paragraph({ spacing: { line: 40, lineRule: "exact" }, children: [] })] })] })],
    }),
    new Paragraph({ spacing: { before: 2680, after: 0, line: 40, lineRule: "exact" }, children: [] }),
    new Paragraph({ spacing: { after: 160, line: 240, lineRule: "atLeast" },
      children: [new TextRun({ text: config.badge, size: 17, color: LP.gold, characterSpacing: 55, font: FONT })] }),
    new Paragraph({ spacing: { after: 140, line: 620, lineRule: "atLeast" },
      children: [new TextRun({ text: config.title, size: 54, bold: true, color: LP.text,
        characterSpacing: 30, font: FONT })] }),
    new Paragraph({ spacing: { line: 320, lineRule: "atLeast" },
      children: [new TextRun({ text: config.subtitle, size: 22, color: LP.muted,
        characterSpacing: 30, font: FONT })] }),
  ], 6434);
  const row3 = cellWithSideRules([
    new Paragraph({ spacing: { before: 2900, after: 0, line: 40, lineRule: "exact" }, children: [] }),
    new Table({
      width: { size: 100, type: WidthType.PERCENTAGE }, borders: allNoBorders,
      rows: [new TableRow({ cantSplit: true, children: [
        metaCell("委 托 人", config.client), metaCell("承办律师", config.lawyer), metaCell("出具日期", config.date),
      ] })],
    }),
    new Paragraph({ spacing: { before: 340, after: 0, line: 40, lineRule: "exact" }, children: [] }),
  ], 6433);
  const row4 = new TableRow({
    height: { value: 1147, rule: "exact" },
    children: [new TableCell({ borders: { bottom: NB, left: NB, right: NB, top: strongRule },
      verticalAlign: "top", margins: { left: 1247, right: 1247 },
      children: [new Table({
        width: { size: 100, type: WidthType.PERCENTAGE }, borders: allNoBorders,
        rows: [new TableRow({ children: [
          new TableCell({ width: { size: 50, type: WidthType.PERCENTAGE }, borders: noBorders,
            children: [new Paragraph({ spacing: { before: 340, line: 220, lineRule: "atLeast" },
              children: [new TextRun({ text: "CONFIDENTIAL", size: 14, color: LP.gold, characterSpacing: 30, font: FONT })] })] }),
          new TableCell({ width: { size: 50, type: WidthType.PERCENTAGE }, borders: noBorders,
            children: [new Paragraph({ alignment: AlignmentType.RIGHT, spacing: { before: 340, line: 220, lineRule: "atLeast" },
              children: [new TextRun({ text: config.lawFirm, size: 14, color: LP.gold, characterSpacing: 30, font: FONT })] })] }),
        ] })],
      })] })],
  });
  // 高度守恒：1247 + 6434 + 6433 + 1147 = 15361 ✓（F 无 section 页脚，全部元素在 wrapper 内）
  return [new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    layout: TableLayoutType.FIXED, borders: allNoBorders,
    rows: [row1, row2, row3, row4],
  })];
}

// 封面调度器：style C/D/E/F → { children, footer }（footer=null 表示该风格自带页脚语义或无页脚）
function buildCover(style, config, assetsDir) {
  const st = (style || "C").toUpperCase();
  switch (st) {
    case "C": return { children: buildCoverC(config, path.join(assetsDir, "cover-decor.png")),
      footer: coverFooter(config.lawFirm), bandMm: 95 };
    case "D": return { children: buildCoverD(config, path.join(assetsDir, "cover-D-decor.png")),
      footer: coverFooterBlank(), bandMm: 150 };
    case "E": return { children: buildCoverE(config, path.join(assetsDir, "cover-E-decor.png")),
      footer: coverFooterBlank(), bandMm: 77 };
    case "F": return { children: buildCoverF(config), footer: coverFooterBlank(), bandMm: 0 };
    default: throw new Error("未知封面风格: " + style + "（可选 C/D/E/F）");
  }
}

module.exports = {
  LP, FONT, NB, noBorders, allNoBorders, PAGE, COVER_MARGIN, boxBorder,
  buildCoverLP: buildCoverC, buildCoverC, buildCoverD, buildCoverE, buildCoverF, buildCover, coverFooter, coverFooterBlank, sectionHeader,
  h1, h2, body, bodyRuns, listItem, lawQuote, makeTable, bodyFooter, backFooter,
  teamCard, firmIntroCard, honorTable, caseGrid, signatureBlock, photoOrPlaceholder,
  docStyles, makeNumbering, makeSection,
};
