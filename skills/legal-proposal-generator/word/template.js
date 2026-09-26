// template.js — OOXML 模板入口：生成 token 化的 legal-proposal-OOXML-template.docx
// 所有 {{TOKEN}} 占位符可用 fill.py（python-docx）填充；正文样例章仅作样式演示，可整章替换。
// 用法：NODE_PATH=$(npm root -g) node template.js
const {
  Document, Packer, Paragraph, TextRun, AlignmentType,
} = require("docx");
const fs = require("fs");
const path = require("path");
const B = require("./builders");

const coverStyle = ((process.argv.find(a => a.startsWith("--cover=")) || "--cover=C").split("=")[1] || "C").toUpperCase();
const OUT = (process.argv.find((a, i) => i >= 2 && !a.startsWith("--")) || path.join(__dirname, "legal-proposal-OOXML-template.docx"));
const FIRM_TOKEN = "{{LAW_FIRM}}";

// ══════════════════ 正文样例（演示全部组件；整章可替换）══════════════════
const bodyChildren = [];
bodyChildren.push(...B.sectionHeader("PROPOSAL", "{{PROPOSAL_TITLE}}"));

bodyChildren.push(B.h1("一、{{CHAPTER_TITLE}}"));
bodyChildren.push(B.body("本章为正文样例段：12pt 宋体、行距 2.1 倍、首行缩进两字符、两端对齐。生成正式方案时，将样例章整体替换为案件内容即可，样式由 builders.js 组件保证。"));
bodyChildren.push(B.bodyRuns([
  { t: "加粗引导词样式：" },
  { t: "重点结论以主色加粗呈现，用于风险点、档位名称、核心结论等。", bold: true },
  { t: "后续正文保持常规字重，一段只安排一处加粗引导，避免满屏重音。" },
]));
bodyChildren.push(B.h2("（一）{{SECTION_TITLE}}"));
bodyChildren.push(B.listItem("list-demo", "列表项样式：编号自动生成，悬挂缩进，用于模式要素、工作阶段、确认问题清单；"));
bodyChildren.push(B.listItem("list-demo", "第二条列表项。列表前后建议以正文段承上启下，避免整篇皆为列表。"));
bodyChildren.push(...B.lawQuote("法条引用块样式（《示例法》第 X 条）：", [
  "法条原文置于浅灰底、金色左线的引用块内，11.5pt。正式客户版方案通常仅引条号不录原文；此组件主要用于内部备忘、法律意见书等场景。",
]));
bodyChildren.push(B.makeTable(
  ["表头一", "表头二", "档位列"],
  [
    ["表格样式演示：主色表头白字", "数据行米白与白色斑马纹交替，仅横向细灰线", "基础档已含"],
    ["第二行数据", "跨页时表头自动重复，行内容不跨页断行", "完整档增补"],
  ],
  [26, 52, 22], true));
bodyChildren.push(B.body("表格后应有说明性正文承接，保持段落节奏。", { after: 160 }));

// 落款（designer align_signature 对应物）
bodyChildren.push(...B.signatureBlock("{{SIGN_FIRM}}", "{{SIGN_LAWYER}}", "{{SIGN_DATE}}"));

// ══════════════════ 后部固定页（与 designer back pages 对应）══════════════════
// 承办团队
const teamChildren = [...B.sectionHeader("OUR TEAM", "服务团队介绍")];
teamChildren.push(B.body("以下卡片为承办律师信息位，两名律师为样式演示，可增删：整表复制后按 TEAM3 系列命名新占位符即可。"));
teamChildren.push(B.teamCard({
  photo: "{{TEAM1_PHOTO}}", name: "{{TEAM1_NAME}}", title: "{{TEAM1_TITLE}}",
  edu: "{{TEAM1_EDU}}", corp: "{{TEAM1_CORP}}", field: "{{TEAM1_FIELD}}",
}));
teamChildren.push(new Paragraph({ spacing: { before: 0, after: 160 }, children: [] }));
teamChildren.push(B.teamCard({
  photo: "{{TEAM2_PHOTO}}", name: "{{TEAM2_NAME}}", title: "{{TEAM2_TITLE}}",
  edu: "{{TEAM2_EDU}}", corp: "{{TEAM2_CORP}}", field: "{{TEAM2_FIELD}}",
}));

// 典型案例
const caseChildren = [...B.sectionHeader("CASE SHOWCASE", "典型案例与既往判决")];
caseChildren.push(B.body("以下 2×2 网格为案例成果图位（判决书截图、成果照片等），图片位由 fill.py 的 --photo 参数填充真实图片，图注随案替换。"));
caseChildren.push(B.caseGrid([
  { img: "{{CASE1_IMG}}", cap: "{{CASE1_CAP}}" },
  { img: "{{CASE2_IMG}}", cap: "{{CASE2_CAP}}" },
  { img: "{{CASE3_IMG}}", cap: "{{CASE3_CAP}}" },
  { img: "{{CASE4_IMG}}", cap: "{{CASE4_CAP}}" },
]));

// 律所简介
const firmChildren = [...B.sectionHeader("ABOUT US", "律所简介")];
firmChildren.push(B.firmIntroCard([
  "{{FIRM_INTRO_1}}",
  "{{FIRM_INTRO_2}}",
], "{{FIRM_PHOTO}}"));

// 律所荣誉
const honorsChildren = [...B.sectionHeader("HONORS", "律所荣誉与资质")];
honorsChildren.push(B.honorTable([
  { num: "01", title: "{{HONOR1_TITLE}}", desc: "{{HONOR1_DESC}}" },
  { num: "02", title: "{{HONOR2_TITLE}}", desc: "{{HONOR2_DESC}}" },
  { num: "03", title: "{{HONOR3_TITLE}}", desc: "{{HONOR3_DESC}}" },
  { num: "04", title: "{{HONOR4_TITLE}}", desc: "{{HONOR4_DESC}}" },
]));

// ══════════════════ 文档装配 ══════════════════
const doc = new Document({
  styles: B.docStyles(),
  numbering: B.makeNumbering(["list-demo"]),
  sections: [
    B.makeSection({
      cover: true,
      ...(() => { const c = B.buildCover(coverStyle, {
        lawFirm: FIRM_TOKEN,
        badge: "{{YEAR}} · 法律服务方案",
        title: "{{PROPOSAL_TITLE}}",
        subtitle: "{{PROPOSAL_SUBTITLE}}",
        client: "{{CLIENT}}",
        lawyer: "{{LAWYER}}",
        date: "{{DATE}}",
      }, __dirname); return { footer: c.footer, children: c.children }; })(),
    }),
    B.makeSection({
      pageNumbersStart: 1, footer: B.bodyFooter(FIRM_TOKEN),
      children: bodyChildren,
    }),
    B.makeSection({ footer: B.backFooter(FIRM_TOKEN, "服务团队"), children: teamChildren }),
    B.makeSection({ footer: B.backFooter(FIRM_TOKEN, "典型案例"), children: caseChildren }),
    B.makeSection({ footer: B.backFooter(FIRM_TOKEN, "律所简介"), children: firmChildren }),
    B.makeSection({ footer: B.backFooter(FIRM_TOKEN, "荣誉资质"), children: honorsChildren }),
  ],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(OUT, buf);
  console.log("OK ->", OUT, buf.length, "bytes  [cover " + coverStyle + "]");
}).catch(e => { console.error("FAILED:", e); process.exit(1); });
