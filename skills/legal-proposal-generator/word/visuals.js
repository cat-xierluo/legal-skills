#!/usr/bin/env node
// SVG / Mermaid 源文件 → 同主题 SVG、高清 PNG、外观绑定记录。
const fs = require('fs'), path = require('path'), os = require('os');
const crypto = require('crypto'), {spawnSync} = require('child_process');
const {loadTheme, themeHash, mermaidConfig} = require('./theme');
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
const recordPath = file => file.replace(/\.png$/i, '.visual.json');
function variables(t) {
  return {...Object.fromEntries(Object.entries(t.colors).map(([k,v])=>[k,'#'+v])),
    diagramFont:t.fonts.diagram, fontSize:t.diagram.fontPt*96/72,
    strokeWidth:t.diagram.linePt*96/72, radius:t.diagram.radiusPx};
}
function themedSvg(source,t) {
  const vars=variables(t);
  return source.replace(/\{\{([\w]+)\}\}/g,(_,key)=>{
    if(!(key in vars)) throw new Error('未知 SVG 主题变量：'+key);
    return String(vars[key]);
  });
}
function staticSvg(source) {
  if(!/<svg\b/i.test(source) || /<!DOCTYPE|<!ENTITY|<(?:script|foreignObject|iframe)\b|\son\w+\s*=|@import|@font-face/i.test(source)) throw new Error('只接受静态、自包含 SVG；移除脚本、foreignObject、外部字体或实体声明');
  for(const match of source.matchAll(/(?:href\s*=\s*["']([^"']+)["']|url\(\s*["']?([^)'"\s]+))/gi)) {
    if(!(match[1]||match[2]).startsWith('#')) throw new Error('SVG 不允许外部资源引用，请先导出自包含矢量图');
  }
  return source;
}
function checkSvgPalette(svg,theme) {
  const allowed=new Set(Object.values(theme.colors));
  const values=[...svg.matchAll(/(?:fill|stroke|color|stop-color|flood-color)\s*(?:=\s*["']([^"']+)["']|:\s*([^;}"']+))/gi)];
  for(const match of values) {
    const value=(match[1]||match[2]).trim();
    if(/^(?:none|transparent|currentColor|inherit)$/i.test(value) || /^url\(#[^)]+\)$/.test(value))continue;
    let color=value.replace(/^#/,'').toUpperCase();
    if(/^[0-9A-F]{3}$/.test(color))color=color.split('').map(c=>c+c).join('');
    if(!value.startsWith('#') || !allowed.has(color))throw new Error('SVG 包含非主题颜色 '+value+'；使用主题变量或按导出的主题配置重画，不能只给旧图片换主题标记');
  }
}
function checkVisual(file,theme,maxWidthMm=160,maxHeightMm=180) {
  if(!/\.png$/i.test(file) || !fs.existsSync(recordPath(file))) return null;
  const record=JSON.parse(fs.readFileSync(recordPath(file),'utf8'));
  if(record.schemaVersion!==1 || record.kind!=='proposal-visual') throw new Error('图表记录格式无效：'+recordPath(file));
  if(record.themeHash!==themeHash(theme)) throw new Error('图表与文档主题不一致，请按当前主题重新导出：'+file);
  if(record.pngSha256!==sha(fs.readFileSync(file))) throw new Error('图表 PNG 已改变，请重新导出图表记录：'+file);
  const source = typeof record.source==='string' ? path.resolve(path.dirname(file),record.source) : '';
  if(!source || !fs.existsSync(source) || record.sourceSha256!==sha(fs.readFileSync(source))) throw new Error('图表源文件缺失或已修改，请重新导出：'+file);
  if(!(record.widthMm>0 && record.widthMm<=maxWidthMm && record.heightMm>0 && record.heightMm<=maxHeightMm)) throw new Error('图表超出此处版面，请拆图或调整画布：'+file);
  return record;
}
function exportTheme(t,dir) {
  fs.mkdirSync(dir,{recursive:true});
  fs.writeFileSync(path.join(dir,'theme.resolved.json'),JSON.stringify(t,null,2)+'\n');
  fs.writeFileSync(path.join(dir,'mermaid-config.json'),JSON.stringify(mermaidConfig(t),null,2)+'\n');
  const aliases={deep:'primary-deep',gold:'accent-gold',cream:'bg-cream',card:'bg-card'};
  fs.writeFileSync(path.join(dir,'theme.css'),':root {\n'+Object.entries(t.colors).map(([k,v])=>`  --${aliases[k]||k}: #${v};`).join('\n')+'\n}\n');
}
async function convert(input,output,theme) {
  if(!/\.png$/i.test(output)) throw new Error('输出须为 .png；同目录同时保留 .svg 和 .visual.json');
  if(!/\.(svg|mmd)$/i.test(input)) throw new Error('输入须为静态 .svg 或简单流程图 .mmd');
  if(fs.statSync(input).size>5*1024*1024) throw new Error('图表源文件超过 5MB，请先简化');
  let sharp; try {sharp=require('sharp');} catch(_){throw new Error('图表导出需要 sharp：npm install -g sharp；设置 NODE_PATH 后重试');}
  const raw=fs.readFileSync(input,'utf8'); let svg;
  if(/\.svg$/i.test(input)) {svg=staticSvg(themedSvg(raw,theme));checkSvgPalette(svg,theme);}
  else {
    if(!/^\s*(?:flowchart|graph)\s+(?:TD|TB|BT|LR|RL)\b/.test(raw)) throw new Error('此入口仅处理 Mermaid 简单流程图；其他图型请用专业可视化工具导出静态 SVG');
    if(/%%\{|^\s*---|(?:^|[;\n])\s*(?:style|classDef|linkStyle|click)\b|<|@\{/m.test(raw)) throw new Error('Mermaid 只保留节点与关系，移除内联配置、样式、链接及 HTML；主题类用 focus/risk/warning/success');
    const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'proposal-visual-'));
    try {
      const c=theme.colors, line=theme.diagram.linePt*96/72;
      const classes=['focus','risk','warning','success'].map(role=>`classDef ${role} fill:#${role==='focus'?c.primary:c.paper},color:#${role==='focus'?c.onPrimary:c.text},stroke:#${role==='focus'?c.primary:c[role]},stroke-width:${line}px;`).join('\n');
      fs.writeFileSync(path.join(tmp,'chart.mmd'),raw+'\n'+classes+'\n');
      fs.writeFileSync(path.join(tmp,'config.json'),JSON.stringify(mermaidConfig(theme)));
      const executable=process.env.PUPPETEER_EXECUTABLE_PATH || ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','/usr/bin/chromium','/usr/bin/google-chrome'].find(p=>fs.existsSync(p));
      fs.writeFileSync(path.join(tmp,'browser.json'),JSON.stringify(executable?{executablePath:executable}:{}));
      const result=spawnSync('mmdc',['-i',path.join(tmp,'chart.mmd'),'-o',path.join(tmp,'chart.svg'),'-c',path.join(tmp,'config.json'),'-p',path.join(tmp,'browser.json'),'-b','#'+c.paper,'-q'],{encoding:'utf8',timeout:60000});
      if(result.error?.code==='ENOENT') throw new Error('Mermaid 导出需要 mmdc：npm install -g @mermaid-js/mermaid-cli；也可改用静态 SVG');
      if(result.status!==0) throw new Error('Mermaid 渲染失败，请检查语法及本地浏览器：'+(result.stderr||result.error?.message||'无日志').slice(-1400));
      svg=staticSvg(fs.readFileSync(path.join(tmp,'chart.svg'),'utf8'));
    } finally {fs.rmSync(tmp,{recursive:true,force:true});}
  }
  const viewBox=svg.match(/<svg\b[^>]*\bviewBox\s*=\s*["']\s*([-\d.eE+]+)[,\s]+([-\d.eE+]+)[,\s]+([\d.eE+]+)[,\s]+([\d.eE+]+)\s*["']/i);
  if(!viewBox || !(+viewBox[3]>0 && +viewBox[4]>0)) throw new Error('SVG 须声明有效 viewBox');
  // 百分比宽度或缺失尺寸会让 SVG 渲染器采用默认画布并留白；按 viewBox 明确画布比例。
  svg=svg.replace(/<svg\b([^>]*)>/i,(_,attrs)=>'<svg'+attrs.replace(/\s+(?:width|height)\s*=\s*(?:"[^"]*"|'[^']*')/gi,'')+` width="${+viewBox[3]}" height="${+viewBox[4]}">`);
  const widthMm=theme.diagram.widthMm,heightMm=widthMm*(+viewBox[4])/(+viewBox[3]);
  if(heightMm>180) throw new Error('图表按正文宽度放置后高于 180mm，请拆成主图和附图');
  if(/\.mmd$/i.test(input) && theme.diagram.fontPt*(widthMm/25.4*96)/(+viewBox[3])<9.5) throw new Error('流程图按正文宽度缩放后字号小于 9.5pt，请拆图或减少横向节点');
  const widthPx=Math.round(widthMm/25.4*theme.diagram.dpi);
  const png=await sharp(Buffer.from(svg),{density:theme.diagram.dpi}).resize({width:widthPx}).flatten({background:'#'+theme.colors.paper}).png().toBuffer();
  const meta=await sharp(png).metadata();
  const svgOutput=output.replace(/\.png$/i,'.svg');
  if(path.resolve(svgOutput)===path.resolve(input)) throw new Error('导出 SVG 会覆盖源文件；请使用独立 assets 目录');
  fs.mkdirSync(path.dirname(output),{recursive:true});
  fs.writeFileSync(svgOutput,svg+'\n');fs.writeFileSync(output,png);
  fs.writeFileSync(recordPath(output),JSON.stringify({schemaVersion:1,kind:'proposal-visual',themeId:theme.id,themeHash:themeHash(theme),source:path.relative(path.dirname(output),input),sourceSha256:sha(raw),pngSha256:sha(png),widthMm,heightMm,pixels:[meta.width,meta.height],dpi:theme.diagram.dpi},null,2)+'\n');
  console.log('已导出主题图表：'+output);
}
async function main(argv) {
  const args={};for(let i=0;i<argv.length;i++) {
    if(!['--input','--output','--theme','--export-theme'].includes(argv[i]) || !argv[i+1]) throw new Error('用法：node word/visuals.js --input 图.svg|图.mmd --output assets/图.png [--theme 主题] [--export-theme 目录]');
    args[argv[i].slice(2)]=argv[++i];
  }
  const t=loadTheme(args.theme);
  if(args.input || args.output) {
    if(!args.input || !args.output) throw new Error('须同时提供 --input 和 --output');
    await convert(path.resolve(args.input),path.resolve(args.output),t);
  }
  if(args['export-theme']) exportTheme(t,path.resolve(args['export-theme']));
  if(!args.input && !args['export-theme']) throw new Error('请指定图表输入，或使用 --export-theme 导出主题给可视化工具');
}
if(require.main===module) main(process.argv.slice(2)).catch(e=>{console.error(e.message);process.exitCode=1});
module.exports={checkVisual,exportTheme,convert};
