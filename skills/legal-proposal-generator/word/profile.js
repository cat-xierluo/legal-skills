// 只读取本地 team-config.md；不复制个人资料到公开 Skill。
const fs = require('fs');
const path = require('path');

function section(source, heading) {
  const escaped = heading.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = source.match(new RegExp(`^##\\s*${escaped}\\s*\\n([\\s\\S]*?)(?=^##\\s|$(?![\\s\\S]))`, 'm'));
  return match ? match[1].trim() : '';
}

function cleanHtml(value) {
  return value.replace(/<br\s*\/?\s*>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;|&#160;/gi, ' ')
    .replace(/&amp;/gi, '&').replace(/&lt;/gi, '<').replace(/&gt;/gi, '>')
    .replace(/&quot;/gi, '"').replace(/&#39;/gi, "'")
    .replace(/\s+/g, ' ').trim();
}

function imagePath(value, baseDir) {
  if (!value) return null;
  if (/^(https?:|data:)/i.test(value)) throw new Error('团队图片只允许本地文件：' + value);
  const resolved = path.resolve(baseDir, value);
  if (!fs.existsSync(resolved)) throw new Error('团队图片不存在：' + resolved);
  if (!/\.(png|jpe?g)$/i.test(resolved)) throw new Error('团队图片仅支持 PNG/JPEG：' + resolved);
  return resolved;
}

function imageRatio(file) {
  if (!file) return undefined;
  const b = fs.readFileSync(file);
  if (file.toLowerCase().endsWith('.png')) return b.readUInt32BE(20) / b.readUInt32BE(16);
  let offset = 2;
  while (offset + 9 < b.length) {
    if (b[offset] !== 0xff) break;
    const marker = b[offset + 1];
    const length = b.readUInt16BE(offset + 2);
    if ([0xc0, 0xc1, 0xc2, 0xc3].includes(marker)) return b.readUInt16BE(offset + 5) / b.readUInt16BE(offset + 7);
    offset += length + 2;
  }
  throw new Error('无法读取图片宽高比：' + file);
}

function markdownImages(source, baseDir) {
  const found = [];
  const re = /!\[[^\]]*\]\(([^)]+)\)|<img\b[^>]*src=["']([^"']+)["'][^>]*>/gi;
  for (const m of source.matchAll(re)) found.push(imagePath(m[1] || m[2], baseDir));
  return found;
}

function field(content, label) {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const re = new RegExp(`<strong[^>]*>\\s*${escaped}[：:]?\\s*<\\/strong>([\\s\\S]*?)(?=<strong|<\\/td>|<\\/tr>|$)`, 'i');
  const m = content.match(re);
  return m ? cleanHtml(m[1]).replace(/^[：:]\s*/, '') : '';
}

function parseLawyers(source, baseDir) {
  const part = section(source, '主办律师介绍');
  const lawyers = [];
  // 实际配置使用 <!-- 姓名 --> 标记一位律师的 HTML 片段。
  const chunks = [...part.matchAll(/<!--\s*([^>]+?)\s*-->([\s\S]*?)(?=<!--\s*[^>]+?\s*-->|$)/g)];
  for (const m of chunks) {
    const chunk = m[2];
    const photo = chunk.match(/<img\b[^>]*src=["']([^"']+)["']/i);
    const strong = chunk.match(/<strong[^>]*>([\s\S]*?)<\/strong>/i);
    const name = cleanHtml(m[1]);
    if (!name) continue;
    const first = strong ? cleanHtml(strong[1]) : '';
    const photoPath = photo ? imagePath(photo[1], baseDir) : null;
    lawyers.push({name, title: first.startsWith(name) ? first.slice(name.length).replace(/^[\/\s]+/, '') : first,
      edu: field(chunk, '教育背景'), corp: field(chunk, '服务企业'), field: field(chunk, '专业领域'),
      photoPath, photoRatio: imageRatio(photoPath)});
  }
  if (lawyers.length) return lawyers;
  // example 配置的 Markdown 表格也可使用。
  for (const line of part.split('\n')) {
    if (!/^\|/.test(line) || /姓名|^\|[\s|:-]+$/.test(line)) continue;
    const cells = line.split('|').slice(1, -1).map(s => s.trim());
    if (cells.length < 6 || !cells[0]) continue;
    const photo = markdownImages(cells[5], baseDir)[0] || null;
    lawyers.push({name: cells[0], title: cells[1], edu: cells[2], corp: cells[3], field: cells[4],
      photoPath: photo, photoRatio: imageRatio(photo)});
  }
  return lawyers;
}

function loadProfile(configPath, selectedNames) {
  if (!fs.existsSync(configPath)) throw new Error('找不到团队配置：' + configPath);
  const source = fs.readFileSync(configPath, 'utf8');
  const base = path.dirname(configPath);
  const available = parseLawyers(source, base);
  const names = selectedNames.filter(Boolean);
  const team = names.length ? names.map(name => {
    const found = available.find(item => item.name === name);
    if (!found) throw new Error('团队配置中找不到主办律师：' + name);
    return found;
  }) : available;
  if (!team.length) throw new Error('完整版缺少可用的承办律师资料');
  const intro = section(source, '律所简介');
  const introImages = markdownImages(intro, base);
  const paragraphs = intro.split(/\n\s*\n/).map(s => cleanHtml(s.replace(/!\[[^\]]*\]\([^)]+\)/g, ''))).filter(Boolean);
  const honorsPart = section(source, '律所荣誉');
  const honors = honorsPart ? honorsPart.split('\n').filter(s => /^[-*]\s/.test(s)).map(s => ({title: s.replace(/^[-*]\s+/, '').trim(), desc: ''}))
    : paragraphs.join(' ').split(/(?<=[。；])/).map(s => s.trim()).filter(s => /荣获|授予|上榜|入选|登录|蝉联|评为|入围/.test(s) && s.length < 120).map(s => ({title: s, desc: ''}));
  const judgments = markdownImages(section(source, '相关法院判决书'), base).map(photoPath => ({photoPath, photoRatio: imageRatio(photoPath), cap: '相关裁判文书'}));
  return {team, firm: {paragraphs: paragraphs.slice(0, 3), photoPath: introImages[0] || null,
    photoRatio: imageRatio(introImages[0])}, honors: honors.slice(0, 6), judgments: judgments.slice(0, 4)};
}

module.exports = {loadProfile};
