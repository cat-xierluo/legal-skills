#!/usr/bin/env node
// 通用方案 Markdown/JSON → 设计版 Word。版式只调用 builders.js。
const fs = require('fs');
const path = require('path');
let docx;
try { docx = require('docx'); }
catch (_) { console.error('缺少 docx 包。安装：npm install -g docx；运行：NODE_PATH=$(npm root -g) node word/render.js ...'); process.exit(2); }
const {Document, Packer, Paragraph} = docx;
const B = require('./builders');
const {loadProfile} = require('./profile');

function args(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--full') { out.full = true; continue; }
    if (!arg.startsWith('--')) throw new Error('未知参数：' + arg);
    const split = arg.indexOf('=');
    const key = arg.slice(2, split < 0 ? undefined : split);
    const value = split < 0 ? argv[++i] : arg.slice(split + 1);
    if (!['input', 'output', 'cover', 'team-config', 'lawyers', 'law-firm', 'client', 'lawyer', 'date', 'title', 'subtitle'].includes(key) || !value || value.startsWith('--')) throw new Error('无效参数：' + arg);
    out[key] = value;
  }
  if (!out.input || !out.output) throw new Error('用法：node word/render.js --input 方案.md --output 方案.docx [--cover C|D|E|F] [--full --team-config config/team-config.md --lawyers 姓名1,姓名2]');
  if (!/\.docx$/i.test(out.output)) throw new Error('输出文件须为 .docx');
  out.cover = (out.cover || 'C').toUpperCase();
  if (!'CDEF'.includes(out.cover) || out.cover.length !== 1) throw new Error('封面风格只支持 C/D/E/F');
  if (out.full && !out.lawyers) throw new Error('完整版须使用 --lawyers 明确选择承办律师');
  return out;
}

function frontmatter(source) {
  if (!source.startsWith('---\n')) return [{}, source];
  const close = source.indexOf('\n---', 4);
  if (close < 0) throw new Error('Markdown frontmatter 未闭合');
  const meta = {};
  for (const line of source.slice(4, close).split('\n')) {
    if (!line.trim() || line.trim().startsWith('#')) continue;
    const m = line.match(/^([\w-]+):\s*(.*)$/);
    if (!m) throw new Error('仅支持 frontmatter 单行键值：' + line);
    meta[m[1]] = m[2].trim().replace(/^(?:"(.*)"|'(.*)')$/, (_, a, b) => a ?? b);
  }
  return [meta, source.slice(close + 4).replace(/^\n/, '')];
}

function isSpecial(line) {
  return /^\s*(?:#{1,6}\s|[-*+]\s|\d+[.)]\s|>\s|\|)|^\s*```|^\s*---\s*$/.test(line);
}

function inlineRuns(text) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map(p => p.startsWith('**') && p.endsWith('**') ? {t: p.slice(2, -2), bold: true} : {t: p, bold: false});
}

function tableCells(line) { return line.trim().replace(/^\||\|$/g, '').split(/(?<!\\)\|/).map(s => s.trim().replace(/\\\|/g, '|')); }

function parseMarkdown(source) {
  const [meta, markdown] = frontmatter(source.replace(/\r\n/g, '\n'));
  if (/^\s*```/m.test(markdown) || /<\/?(?:table|div|img|svg|p|h[1-6])\b/i.test(markdown) || /!\[[^\]]*\]\([^)]+\)/.test(markdown)) {
    throw new Error('正文含代码块、HTML 或图片。请将图表另行处理，或用 JSON blocks 明确构造，不要静默丢失内容。');
  }
  const lines = markdown.split('\n');
  const blocks = [];
  let title = meta.title || '';
  let listId = 0;
  let inList = false;
  let listOrdered = false;
  for (let i = 0; i < lines.length;) {
    const line = lines[i].trim();
    if (!line || /^---+$/.test(line)) { i++; inList = false; continue; }
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      if (heading[1].length === 1 && !title) title = heading[2];
      else if (heading[1].length === 1 && heading[2] !== title) blocks.push({type: 'h1', text: heading[2]});
      else if (heading[1].length === 2) blocks.push({type: 'h1', text: heading[2]});
      else blocks.push({type: 'h2', text: heading[2]});
      i++; inList = false; continue;
    }
    if (/^\|/.test(line) && i + 1 < lines.length && /^\|?[\s:|\-]+\|?$/.test(lines[i + 1].trim())) {
      const headers = tableCells(line); i += 2;
      const rows = [];
      while (i < lines.length && /^\|/.test(lines[i].trim())) rows.push(tableCells(lines[i++]));
      if (rows.some(row => row.length !== headers.length)) throw new Error('Markdown 表格列数不一致');
      blocks.push({type: 'table', headers, rows}); inList = false; continue;
    }
    if (/^>\s?/.test(line)) {
      const quote = [];
      while (i < lines.length && /^>\s?/.test(lines[i].trim())) quote.push(lines[i++].trim().replace(/^>\s?/, ''));
      blocks.push({type: 'quote', lines: quote}); inList = false; continue;
    }
    if (/^(?:[-*+]\s|\d+[.)]\s)/.test(line)) {
      const ordered = /^\d+[.)]\s/.test(line);
      if (!inList || listOrdered !== ordered) { listId++; inList = true; listOrdered = ordered; }
      blocks.push({type: 'list', text: line.replace(/^(?:[-*+]\s|\d+[.)]\s)/, ''),
        list: 'list-' + listId, ordered}); i++; continue;
    }
    const paragraph = [line]; i++;
    while (i < lines.length && lines[i].trim() && !isSpecial(lines[i])) paragraph.push(lines[i++].trim());
    const text = paragraph.join(' ');
    blocks.push({type: 'body', runs: inlineRuns(text)}); inList = false;
  }
  return {cover: {lawFirm: meta.law_firm || meta.lawFirm, title, subtitle: meta.subtitle || '',
    client: meta.client, lawyer: meta.lawyer || meta.lead_lawyer, date: meta.date,
    badge: meta.badge || ((meta.date || '').slice(0, 4) + ' · 法律服务方案')}, blocks,
    signature: meta.signature !== 'false'};
}

function requireText(value, key) {
  if (typeof value !== 'string' || !value.trim()) throw new Error('封面缺少 ' + key + '，请在 Markdown frontmatter 或 JSON cover 中提供');
  return value.trim();
}

function validate(data) {
  if (!data || typeof data !== 'object' || !Array.isArray(data.blocks) || !data.blocks.length) throw new Error('方案正文 blocks 不能为空');
  const cover = data.cover || {};
  for (const key of ['lawFirm', 'title', 'client', 'lawyer', 'date']) requireText(cover[key], key);
  cover.subtitle = typeof cover.subtitle === 'string' ? cover.subtitle : '';
  cover.badge = cover.badge || cover.date.slice(0, 4) + ' · 法律服务方案';
  for (const block of data.blocks) {
    if (!['h1', 'h2', 'body', 'list', 'quote', 'table'].includes(block.type)) throw new Error('未知正文块类型：' + block.type);
    if (block.type === 'table' && (!Array.isArray(block.headers) || !Array.isArray(block.rows) || !block.headers.length)) throw new Error('表格须有 headers 和 rows');
    if (block.type === 'quote' && (!Array.isArray(block.lines) || (!block.lines.length && !block.label))) throw new Error('引文块须有非空 lines 或 label');
  }
  return data;
}

function dropRepeatedSignature(data) {
  if (data.signature === false || data.blocks.length < 3) return;
  const tail = data.blocks.slice(-3).map(block => block.type === 'body'
    ? (block.text || (block.runs || []).map(run => run.t).join('')).trim() : '');
  if (tail.every((value, index) => value === [data.cover.lawFirm, data.cover.lawyer, data.cover.date][index])) {
    data.blocks.splice(-3);
  }
}

function bodyChildren(data) {
  const children = [...B.sectionHeader('PROPOSAL', data.cover.title)];
  const lists = new Map();
  for (const block of data.blocks) {
    if (block.type === 'h1') children.push(B.h1(block.text));
    else if (block.type === 'h2') children.push(B.h2(block.text));
    else if (block.type === 'body') children.push(block.runs ? B.bodyRuns(block.runs) : B.body(block.text));
    else if (block.type === 'list') {
      const ref = block.list || 'list-default';
      const ordered = block.ordered !== false;
      if (lists.has(ref) && lists.get(ref) !== ordered) throw new Error('同一列表编号不能混用有序与无序列表：' + ref);
      lists.set(ref, ordered);
      children.push(B.listItem(ref, block.text));
    }
    else if (block.type === 'quote') children.push(...B.lawQuote(block.label || '', block.lines));
    else if (block.type === 'table') {
      const widths = block.widths || block.headers.map(() => 100 / block.headers.length);
      children.push(B.makeTable(block.headers, block.rows, widths, !!block.boldLastCol));
    }
  }
  if (data.signature !== false) children.push(...B.signatureBlock(data.cover.lawFirm, data.cover.lawyer, data.cover.date));
  return {children, lists: [...lists].map(([reference, ordered]) => ({reference, ordered}))};
}

function backMatterPages(profile) {
  const pages = [];
  profile.team.forEach((person, index) => {
    if (index % 2 === 0) pages.push({label: '服务团队', children: B.sectionHeader('OUR TEAM', '服务团队介绍')});
    const page = pages[pages.length - 1];
    if (index % 2 === 1) page.children.push(new Paragraph({spacing: {before: 0, after: 160}, children: []}));
    page.children.push(B.teamCard(person));
  });
  if (profile.judgments.length) {
    const children = [...B.sectionHeader('CASE SHOWCASE', '典型案例与既往判决')];
    children.push(B.body('以下材料涉及隐私或商业秘密；交付前请确认已完成必要脱敏。'));
    const cases = [...profile.judgments];
    while (cases.length < 4) cases.push({img: '待补充', cap: '资料待补充'});
    children.push(B.caseGrid(cases));
    pages.push({label: '典型案例', children});
  }
  if (profile.firm.paragraphs.length) {
    const children = [...B.sectionHeader('ABOUT US', '律所简介')];
    children.push(B.firmIntroCard(profile.firm.paragraphs, profile.firm.photoPath, profile.firm.photoRatio));
    pages.push({label: '律所简介', children});
  }
  if (profile.honors.length) {
    const children = [...B.sectionHeader('HONORS', '律所荣誉与资质')];
    children.push(B.honorTable(profile.honors.map((item, i) => ({num: String(i + 1).padStart(2, '0'), ...item}))));
    pages.push({label: '荣誉资质', children});
  }
  return pages;
}

async function main() {
  const option = args(process.argv.slice(2));
  const input = path.resolve(option.input);
  const source = fs.readFileSync(input, 'utf8');
  const data = /\.json$/i.test(input) ? JSON.parse(source) : parseMarkdown(source);
  data.cover ||= {};
  for (const [arg, key] of [['law-firm', 'lawFirm'], ['client', 'client'], ['lawyer', 'lawyer'], ['date', 'date'], ['title', 'title'], ['subtitle', 'subtitle']]) {
    if (option[arg]) data.cover[key] = option[arg];
  }
  validate(data);
  dropRepeatedSignature(data);
  const rendered = bodyChildren(data);
  let backPages = [];
  if (option.full) {
    const config = path.resolve(option['team-config'] || path.join(__dirname, '..', 'config', 'team-config.md'));
    backPages = backMatterPages(loadProfile(config, option.lawyers.split(',').map(s => s.trim())));
  }
  const cover = B.buildCover(option.cover, data.cover, __dirname);
  const doc = new Document({styles: B.docStyles(), numbering: B.makeNumbering(rendered.lists), sections: [
    B.makeSection({cover: true, footer: cover.footer, children: cover.children}),
    B.makeSection({pageNumbersStart: 1, footer: B.bodyFooter(data.cover.lawFirm), children: rendered.children}),
    ...backPages.map(page => B.makeSection({footer: B.backFooter(data.cover.lawFirm, page.label), children: page.children})),
  ]});
  const output = path.resolve(option.output);
  fs.mkdirSync(path.dirname(output), {recursive: true});
  fs.writeFileSync(output, await Packer.toBuffer(doc));
  console.log('已生成：' + output);
}

main().catch(error => {console.error('生成失败：' + error.message); process.exitCode = 1;});
