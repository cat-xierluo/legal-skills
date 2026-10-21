#!/usr/bin/env node
/**
 * check-privacy.js - 发布内容「具体名称」门禁（通用检测，不依赖私有名单）
 *
 * 原则（用户 261016 定调）：
 *   不是维护者私有的客户名单，而是**通用模式**——凡是提交内容里明显包含
 *   「具体名称」的都必须过这道门禁；配置文件从严（发布出去的配置必须是空模板）。
 *
 * 检测类别（全部为模式，不含任何具体客户/项目名）：
 *   G1 具体机构名        2-5 个汉字 + 机构后缀（律协/检察院/法院/政法大学…），功能词开头豁免
 *   G2 具体人名+职称     2-4 个汉字 + 律师/检察官/法官/教授等，功能词开头豁免
 *   G3 绝对机路径        /Users/<name>/、/home/<name>/、C:\Users\
 *   G4 内部编号/memo     「DEC-加数字」编号、memo 冒号前缀这类内部追踪标识
 *   G5 联系方式          微信：ID、手机号、邮箱
 *   G6 个人素材文件名    含二维码、头像、个人介绍、身份证等字样的图片或文档文件
 *   G7 真实课程路径      讲课培训类目录引用、训练类课件目录
 *   G8 配置文件从严      config/ 与 profile/env 类文件中身份、联系、素材字段必须为空
 *   G9 日期与课件/项目语境组合；G10 来源标签与版本/页码组合需复核
 *
 * 有意保留的发布元数据（作者署名等）通过 INTENTIONAL 登记表豁免：
 *   登记表逐条给 file + 正则 + 理由，可审计、可评审——这与「客户名单」相反，
 *   名单是拿来拦未知项的（枚举不全），登记表是拿来说明「这一处为什么可以留」。
 *
 * USAGE:
 *   node check-privacy.js                 # 扫描技能目录（排除内部文档/私有目录）
 *   node check-privacy.js --quiet         # 只输出命中行
 *   作为库：const { scan } = require('./check-privacy')
 *
 * 已知边界（如实声明）：内部工具的英文名（如造词型产品名）无中文职称/机构/路径特征，
 *   通用模式抓不到——这类靠 G4 的 memo 上下文与人工评审兜底。
 */

'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');

// ── 有意保留的发布元数据登记表（file → [{re, reason}]）──────────────────
// 去个人化不删必要的作者署名（见 references/configuration.md §7）。
// 新增豁免必须写理由；登记表越长越可疑，评审时应质疑每一条。
const INTENTIONAL = {
  'LICENSE.txt': [
    { re: /杨卫薪律师（微信ywxlaw）/g, reason: '版权署名（发布元数据）' }
  ],
  'SKILL.md': [
    { re: /author: 杨卫薪律师（微信ywxlaw）/g, reason: 'frontmatter 作者署名（发布元数据）' }
  ],
  'scripts/check-privacy.js': [
    // 本文件 INTENTIONAL 登记表里用于演示豁免的作者署名正则——内容即发布元数据本身
    { re: /杨卫薪律师（微信ywxlaw）|author: 杨卫薪律师（微信ywxlaw）/g, reason: '登记表中的署名豁免示例（发布元数据）' }
  ]
};

// ── 通用检测模式（按行匹配；guard 返回 false 表示不判）─────────────────
const STOP_FIRST = /[该此本某每各其一位名作为是和与或及等的了在对于从被把]/;
// 泛指/修饰前缀：与职称、机构后缀连用时是泛指（「尤其检察官」「资深律师」「面向检察院」），不是具体名称
const STOP_PREFIXES = [
  '尤其', '包括', '面向', '针对', '例如', '比如', '所谓', '作为', '还是', '以及',
  '还有', '或是', '或者', '所有', '任何', '各级', '各地', '各位', '每位', '全体',
  '全省', '全市', '全国', '不少', '许多', '很多', '资深', '知名', '著名', '高级',
  '初级', '特级', '一级', '二级', '主任', '副主任', '合伙人', '专职', '兼职',
  '执业', '实习', '助理', '退休', '在职', '普通', '一般', '专业', '职业', '法律',
  '刑事', '民事', '行政', '首席', '年轻', '青年', '成年', '未成年'
];
function isGenericMention(hit) {
  if (STOP_FIRST.test(hit.slice(0, 1))) return true;
  return STOP_PREFIXES.some((p) => hit.startsWith(p));
}

const PATTERNS = [
  {
    id: 'G1', why: '具体机构名',
    re: /[\u4e00-\u9fa5]{2,5}(?:律协|律师协会|律师事务所|律所|检察院|人民法院|中级法院|高级法院|公安局|司法局|监狱管理局|仲裁委|公证处|政法(?:大学)?|警官学院|法官学院|税务师事务所)/g,
    guard: (hit) => !isGenericMention(hit)
  },
  {
    id: 'G2', why: '具体人名+职称',
    re: /[\u4e00-\u9fa5]{2,4}(?:律师|检察官|法官|教授|主任医师)/g,
    guard: (hit) => !isGenericMention(hit)
  },
  { id: 'G3', why: '绝对机路径', re: /\/(?:Users|home)\/[A-Za-z0-9._-]+\//g },
  { id: 'G4', why: '内部编号/memo', re: /\bDEC-\d{2,4}\b|\bmemo:\s*\S+/g },
  {
    id: 'G5', why: '联系方式',
    re: /(?:微信|WeChat|weixin)\s*[：:]\s*[A-Za-z][A-Za-z0-9_-]{2,}|\b1[3-9]\d{9}\b|[\w.+-]+@[\w-]+\.[\w.]{2,}/g
  },
  {
    id: 'G6', why: '个人素材文件名',
    re: /[\u4e00-\u9fa5]{0,10}(?:二维码|头像|照片|个人介绍|身份证|名片)[\u4e00-\u9fa5]{0,8}\.(?:png|jpe?g|gif|webp|md|pdf|docx?)/g
  },
  {
    id: 'G7', why: '真实课程路径',
    re: /讲课培训\/|[\u4e00-\u9fa5]{2,8}(?:培训班|训练营|特训营|青训营)\/|[\u4e00-\u9fa5]{0,8}(?:培训班|训练营|特训营|青训营)[\u4e00-\u9fa5]{0,4}课件/g
  },
  {
    id: 'G9', why: '日期与真实课件/项目语境组合需复核',
    re: /(?<![#\w])(?:20)?[2-9]\d(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?!\d)|\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b/g,
    guard: (_hit, line) => !/^## \[/.test(line) && /deck|课件|授课|宣讲|培训|客户|项目|用户反馈/i.test(line)
  },
  {
    id: 'G10', why: '具体来源标签或带版本/页码的项目名称需复核',
    re: /(?:案例|来源|用户原话|用户反馈)[（(]\s*[\u4e00-\u9fa5]{2,4}(?=\s*(?:[）)]|[vP]\d))|(?<=[（(：:—])[\u4e00-\u9fa5]{2,4}\s+(?:v\d+(?:\.\d+)*|P\d+)\b/g,
    guard: (hit) => !/(?:示例|匿名|合成|通用|课件|回归|样例|版本|代码|文档|同日)/.test(hit)
  }
];

// ── 配置文件从严：发布出去的配置必须是空模板 ───────────────────────────
function isConfigFile(rel) {
  const base = path.basename(rel);
  return rel.split(path.sep).join('/').startsWith('config/') ||
    /profile/i.test(base) ||
    /\.(env|toml|ini)$/.test(base) ||
    /^settings/i.test(base);
}

// 身份/联系/素材类字段：发布模板中必须为空（键名包含匹配，覆盖 wechat_qr/footprint_photos 等组合键）
const IDENTITY_KEYS = /(name|author|creator|wechat|weixin|email|phone|mobile|tel|avatar|logo|qr|photo|footprint|bio|titles|organization|website|footer_text)/i;

function checkConfigStrict(rel, text, findings) {
  let data;
  try { data = JSON.parse(text); } catch { return; } // 非 JSON 配置交由通用模式
  const walk = (node, trail) => {
    if (Array.isArray(node)) {
      // 数组：父键属身份类且含非空字符串即判（如 footprint_photos: ["a.jpg"]）
      const parentKey = String(trail[trail.length - 1] || '');
      if (IDENTITY_KEYS.test(parentKey) && node.some((v) => typeof v === 'string' && v.trim() !== '')) {
        findings.push({
          file: rel, line: 1, id: 'G8', why: `配置文件身份字段非空（${trail.join('.')}）`,
          snippet: `${parentKey} = [${node.filter(String).length} 项]`
        });
        return;
      }
      node.forEach((v, i) => walk(v, trail.concat(i)));
      return;
    }
    if (node && typeof node === 'object') {
      for (const [k, v] of Object.entries(node)) walk(v, trail.concat(k));
      return;
    }
    const leafKey = trail[trail.length - 1];
    if (typeof node === 'string' && leafKey && IDENTITY_KEYS.test(String(leafKey)) && node.trim() !== '') {
      findings.push({
        file: rel, line: 1, id: 'G8', why: `配置文件身份字段非空（${trail.join('.')}）`,
        snippet: `${leafKey} = ${node.slice(0, 40)}`
      });
    }
  };
  walk(data, []);
}

// ── 豁免区间：每文件预计算一次，命中落在任一区间内即放行 ────────────────
function permittedSpans(rel, text) {
  const rules = INTENTIONAL[rel.split(path.sep).join('/')] || [];
  const spans = [];
  for (const rule of rules) {
    const re = new RegExp(rule.re.source, rule.re.flags.includes('g') ? rule.re.flags : rule.re.flags + 'g');
    let m;
    while ((m = re.exec(text)) !== null) {
      if (m[0].length === 0) { re.lastIndex++; continue; }
      spans.push({ start: m.index, end: m.index + m[0].length, reason: rule.reason });
    }
  }
  return spans;
}

// ── 核心扫描（按行，O(文件数 × 行数 × 模式数)）─────────────────────────
/**
 * @param {string[]} files 相对 ROOT 的文件列表
 * @returns {{findings: Array, allowed: number}}
 */
function scan(files, root = ROOT) {
  const findings = [];
  let allowed = 0;

  for (const relInput of files) {
    const rel = relInput.split(path.sep).join('/');
    const abs = path.resolve(root, rel);
    if (path.relative(root, abs).startsWith('..') || path.isAbsolute(rel)) {
      throw new Error(`扫描路径超出根目录: ${rel}`);
    }
    if (!fs.lstatSync(abs).isFile()) throw new Error(`扫描目标必须为普通文件: ${rel}`);
    if (/\.(png|jpe?g|gif|webp|pdf|pptx|docx|zip)$/.test(rel)) continue; // 二进制不入文本扫描

    const text = fs.readFileSync(abs, 'utf-8');

    const spans = permittedSpans(rel, text);
    const lines = text.split('\n');
    let offset = 0;

    for (let li = 0; li < lines.length; li++) {
      const line = lines[li];
      const lineStart = offset;
      offset += line.length + 1;

      for (const { id, why, re, guard } of PATTERNS) {
        re.lastIndex = 0;
        let m;
        while ((m = re.exec(line)) !== null) {
          if (m[0].length === 0) { re.lastIndex++; continue; }
          const start = lineStart + m.index;
          const end = start + m[0].length;
          if (spans.some((s) => start >= s.start && end <= s.end)) { allowed++; continue; }
          if (guard && !guard(m[0], line)) continue;
          findings.push({
            file: rel, line: li + 1, id, why,
            snippet: `${m[0]}  |  ${line.trim().slice(0, 80)}`
          });
        }
      }
    }

    if (isConfigFile(rel)) checkConfigStrict(rel, text, findings);
  }

  findings.sort((a, b) => a.file.localeCompare(b.file) || a.line - b.line);
  return { findings, allowed };
}

// ── CLI ────────────────────────────────────────────────────────────────
function defaultFiles(root = ROOT) {
  // 扫全技能目录，排除内部文档、私有目录、依赖与产物
  const SKIP_DIR = new Set(['node_modules', 'local', 'legacy-private', 'archive', '__pycache__', '.git']);
  const SKIP_FILE = new Set(['TASKS.md', 'DECISIONS.md', 'check-privacy.js', 'pack-public.js']);
  const SKIP_EXT = /\.(pptx|pdf|zip|png|jpe?g)$/;
  const out = [];
  const walk = (dir) => {
    for (const name of fs.readdirSync(dir).sort()) {
      if (name.startsWith('publication-remediation-plan')) continue;
      const abs = path.join(dir, name);
      const rel = path.relative(root, abs);
      const st = fs.lstatSync(abs);
      if (st.isSymbolicLink()) throw new Error(`公开扫描不接受符号链接: ${rel}`);
      if (st.isDirectory()) { if (!SKIP_DIR.has(name)) walk(abs); continue; }
      if (SKIP_FILE.has(name) || SKIP_EXT.test(name) || /\.local\./.test(name) || /\.DS_Store$/.test(name)) continue;
      out.push(rel);
    }
  };
  walk(root);
  return out;
}

function main() {
  const quiet = process.argv.includes('--quiet');
  const files = defaultFiles();
  const { findings, allowed } = scan(files);

  if (!quiet) console.log(`── 具体名称门禁（通用检测）──\n扫描 ${files.length} 个文件；豁免发布元数据命中 ${allowed} 处`);
  if (findings.length === 0) {
    if (!quiet) console.log('未发现未登记的具体名称/身份内容。');
    return;
  }
  if (!quiet) {
    console.log(`\n发现 ${findings.length} 处待处置：`);
    for (const f of findings) console.log(`  ! [${f.id}] ${f.file}:${f.line} ${f.why}\n      ${f.snippet}`);
  } else {
    for (const f of findings) console.log(`! [${f.id}] ${f.file}:${f.line} ${f.why}`);
  }
  console.error(`\n门禁未通过：${findings.length} 处具体名称未登记豁免。泛化处理或在 INTENTIONAL 登记表加理由。`);
  process.exit(1);
}

module.exports = { scan, PATTERNS, INTENTIONAL, isConfigFile, defaultFiles };

if (require.main === module) {
  try { main(); } catch (err) { console.error(`扫描失败: ${err.message}`); process.exitCode = 1; }
}
