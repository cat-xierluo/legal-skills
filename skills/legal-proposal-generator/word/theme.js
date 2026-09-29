// 文档、封面和图表共用主题。配置仅作为数据读取，不执行配置中的代码。
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const directory = path.join(__dirname, '..', 'config', 'themes');
const base = JSON.parse(fs.readFileSync(path.join(directory, 'law-firm-brown.json'), 'utf8'));
const presets = ['law-firm-brown', 'navy', 'forest'];

function merge(parent, child) {
  if (!child || typeof child !== 'object' || Array.isArray(child)) throw new Error('主题须为 JSON 对象');
  for (const key of Object.keys(child)) if (!['schemaVersion', 'id', 'name', 'extends', 'colors', 'fonts', 'diagram'].includes(key)) throw new Error('未知主题字段：' + key);
  const out = {...parent, ...child};
  delete out.extends;
  for (const group of ['colors', 'fonts', 'diagram']) {
    const value = child[group] ?? {};
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('主题字段须为对象：' + group);
    for (const key of Object.keys(value)) if (!Object.hasOwn(base[group], key)) throw new Error('未知主题字段：' + group + '.' + key);
    out[group] = {...parent[group], ...value};
  }
  return out;
}
function validate(t) {
  if (t.schemaVersion !== 1) throw new Error('主题 schemaVersion 仅支持 1');
  if (typeof t.id !== 'string' || !/^[a-z][a-z0-9-]{0,63}$/.test(t.id)) throw new Error('主题 id 须为小写字母、数字或短横线');
  if (typeof t.name !== 'string' || !t.name.trim()) throw new Error('主题缺少 name');
  for (const [key, value] of Object.entries(t.colors)) {
    if (typeof value !== 'string' || !/^#?[0-9a-f]{6}$/i.test(value)) throw new Error('主题颜色须为六位 HEX：' + key);
    t.colors[key] = value.replace(/^#/, '').toUpperCase();
  }
  for (const [key, value] of Object.entries(t.fonts)) if (typeof value !== 'string' || !/^[\p{L}\p{N} ,._-]{1,100}$/u.test(value)) throw new Error('无效主题字体：' + key);
  for (const [key, min, max] of [['widthMm',80,160], ['dpi',150,600], ['fontPt',10,16], ['linePt',0.5,2], ['radiusPx',0,12]]) {
    if (!Number.isFinite(t.diagram[key]) || t.diagram[key] < min || t.diagram[key] > max) throw new Error(`diagram.${key} 须在 ${min}–${max} 之间`);
  }
  const luminance = hex => {
    const c = hex.match(/../g).map(h => parseInt(h,16)/255).map(v => v <= .04045 ? v/12.92 : ((v+.055)/1.055)**2.4);
    return c[0]*.2126+c[1]*.7152+c[2]*.0722;
  };
  for (const [fg,bg] of [['text','paper'], ['text','cream'], ['text','card'], ['onPrimary','primary']]) {
    const a=luminance(t.colors[fg]), b=luminance(t.colors[bg]);
    if ((Math.max(a,b)+.05)/(Math.min(a,b)+.05) < 4.5) throw new Error(`主题 ${fg}/${bg} 对比度不足 4.5，请调整文字或背景色`);
  }
  return t;
}
function loadTheme(selector = 'law-firm-brown', baseDir = process.cwd()) {
  if (typeof selector !== 'string') throw new Error('theme 须为预设名或 JSON 文件路径');
  const file = presets.includes(selector) ? path.join(directory, selector + '.json') : path.resolve(baseDir, selector);
  if (!fs.existsSync(file)) throw new Error('找不到主题：' + file);
  const input = JSON.parse(fs.readFileSync(file, 'utf8'));
  let parent = base;
  if (input.extends !== undefined) {
    if (!presets.includes(input.extends)) throw new Error('extends 仅允许内置主题：' + presets.join(', '));
    if (input.extends !== 'law-firm-brown') parent = merge(base, JSON.parse(fs.readFileSync(path.join(directory, input.extends+'.json'), 'utf8')));
  }
  return validate(merge(parent, input));
}
function themeHash(t) {
  // 只绑定影响外观的数据；主题显示名变化不要求重新导出图片。
  return crypto.createHash('sha256').update(JSON.stringify([t.colors,t.fonts,t.diagram])).digest('hex');
}
function mermaidConfig(t) {
  const c=t.colors, h=k=>'#'+c[k];
  return {theme:'base', securityLevel:'strict', htmlLabels:false, fontFamily:t.fonts.diagram,
    themeCSS:`.node rect,.node circle,.node polygon{stroke-width:${t.diagram.linePt*96/72}px}.flowchart-link{stroke-width:${t.diagram.linePt*96/72}px}`,
    flowchart:{htmlLabels:false, curve:'linear', useMaxWidth:false},
    themeVariables:{fontFamily:t.fonts.diagram, fontSize:`${t.diagram.fontPt*96/72}px`,
      primaryColor:h('cream'), primaryTextColor:h('text'), primaryBorderColor:h('primary'),
      secondaryColor:h('card'), secondaryTextColor:h('text'), secondaryBorderColor:h('gold'),
      tertiaryColor:h('softbg'), tertiaryTextColor:h('text'), tertiaryBorderColor:h('rule'),
      lineColor:h('primary'), textColor:h('text'), mainBkg:h('cream'),
      nodeBorder:h('primary'), edgeLabelBackground:h('paper'), clusterBkg:h('card'), clusterBorder:h('rule'),
      background:h('paper')}};
}
module.exports = {loadTheme, themeHash, mermaidConfig, presets};
