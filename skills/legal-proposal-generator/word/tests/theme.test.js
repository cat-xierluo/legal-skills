const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('fs'),path=require('path'),os=require('os');
const {spawnSync}=require('child_process');
const {loadTheme}=require('../theme');
const {convert,checkVisual}=require('../visuals');
let sharp;try{sharp=require('sharp')}catch(_){}
const word=path.resolve(__dirname,'..');
const temporary=fn=>async()=>{const dir=fs.mkdtempSync(path.join(os.tmpdir(),'proposal-theme-test-'));try{await fn(dir)}finally{fs.rmSync(dir,{recursive:true,force:true})}};

test('自定义主题继承、排错与关键颜色对比度',temporary(async dir=>{
  const file=path.join(dir,'brand.json');
  fs.writeFileSync(file,JSON.stringify({extends:'navy',id:'brand',name:'品牌',colors:{primary:'#234567'}}));
  const t=loadTheme(file);assert.equal(t.colors.primary,'234567');assert.equal(t.colors.cream,loadTheme('navy').colors.cream);
  fs.writeFileSync(file,JSON.stringify({colors:{primary:'FFFFFF',onPrimary:'FFFFFF'}}));
  assert.throws(()=>loadTheme(file),/对比度/);
  fs.writeFileSync(file,JSON.stringify({colors:{primray:'234567'}}));assert.throws(()=>loadTheme(file),/未知主题字段/);
}));

test('图件真实着色并阻断错主题、过时源文件和被改写图片',{skip:!sharp&&'需安装 sharp'},temporary(async dir=>{
  const input=path.join(dir,'chart.svg'),png=path.join(dir,'assets/chart.png'),t=loadTheme('navy');
  fs.writeFileSync(input,'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 605 100"><rect width="605" height="100" fill="{{primary}}"/></svg>');
  await convert(input,png,t);
  const {data,info}=await sharp(png).removeAlpha().raw().toBuffer({resolveWithObject:true});
  const center=(Math.floor(info.height/2)*info.width+Math.floor(info.width/2))*info.channels;
  assert.deepEqual([...data.subarray(center,center+3)],[0x29,0x46,0x5b]);
  assert.ok(Math.abs(info.width/info.height-6.05)<0.03);
  assert.equal(checkVisual(png,t).widthMm,160);
  assert.throws(()=>checkVisual(png,loadTheme('forest')),/主题不一致/);
  fs.appendFileSync(input,'\n');assert.throws(()=>checkVisual(png,t),/源文件/);
  await convert(input,png,t);fs.appendFileSync(png,'changed');assert.throws(()=>checkVisual(png,t),/PNG 已改变/);
}));

test('SVG 非主题固定色与外部资源不会被贴上有效主题标签',{skip:!sharp&&'需安装 sharp'},temporary(async dir=>{
  const input=path.join(dir,'chart.svg'),png=path.join(dir,'assets/chart.png');
  fs.writeFileSync(input,'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 605 100"><rect fill="#ff00ff" width="605" height="100"/></svg>');
  await assert.rejects(convert(input,png,loadTheme()),/非主题颜色/);assert.equal(fs.existsSync(png),false);
  fs.writeFileSync(input,'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 605 100"><image href="https://example.invalid/image.png"/></svg>');
  await assert.rejects(convert(input,png,loadTheme()),/外部资源/);assert.equal(fs.existsSync(png),false);
}));

test('保留默认主题名称但修改颜色时，封面也重建',{skip:!sharp&&'需安装 sharp'},async()=>{
  const t=loadTheme();t.colors.primary='29465B';t.colors.gold='738A99';
  const buffers=await require('../decor').loadDecor(t);
  const {data,info}=await sharp(buffers['cover-C']).removeAlpha().raw().toBuffer({resolveWithObject:true});
  const offset=(20*info.width+20)*info.channels;
  assert.deepEqual([...data.subarray(offset,offset+3)],[0x29,0x46,0x5b]);
});

test('MD frontmatter 主题与命令行覆盖在真实 Word 入口生效',{skip:!sharp&&'需安装 sharp'},temporary(async dir=>{
  const input=path.join(dir,'chart.svg'),png=path.join(dir,'assets/chart.png');
  fs.writeFileSync(input,'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 605 100"><rect width="605" height="100" fill="{{primary}}"/></svg>');
  await convert(input,png,loadTheme('navy'));
  const md=path.join(dir,'proposal.md'),output=path.join(dir,'proposal.docx');
  fs.writeFileSync(md,'---\nlaw_firm: 示例律所\nclient: 示例客户\nlawyer: 测试律师\ndate: 2026年9月27日\ntheme: navy\n---\n# 主题样稿\n\n![图表](assets/chart.png)\n');
  const args=[path.join(word,'render.js'),'--input',md,'--output',output];
  let run=spawnSync(process.execPath,args,{encoding:'utf8'});assert.equal(run.status,0,run.stderr);assert.ok(fs.statSync(output).size>1000);
  const before=fs.readFileSync(output);
  run=spawnSync(process.execPath,[...args,'--theme','forest'],{encoding:'utf8'});assert.notEqual(run.status,0);assert.match(run.stderr,/主题不一致/);assert.deepEqual(fs.readFileSync(output),before);
}));
