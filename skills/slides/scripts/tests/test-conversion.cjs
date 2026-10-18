'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {spawnSync,execFileSync}=require('node:child_process');
const scripts=path.resolve(__dirname,'..');
const fixture=path.join(__dirname,'fixtures/dynamic-background.html');
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'slides-conversion-'));
const env={...process.env,SLIDES_HOME:path.join(tmp,'empty-profile')};delete env.SLIDES_PROFILE;
// Explicit empty template isolates installed personal configuration as well.
const anonymous=path.join(scripts,'../config/profile.example.json');
function run(args){return spawnSync(process.execPath,[path.join(scripts,'convert.js'),'--config',anonymous,...args],{cwd:tmp,env,encoding:'utf8',timeout:90000});}
function inspectPptx(file,creator){
 const script=`import zipfile,json,re,sys,xml.etree.ElementTree as E
with zipfile.ZipFile(sys.argv[1]) as z:
 assert z.testzip() is None
 slides=[n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\\d+\\.xml',n)]
 assert len(slides)==2,slides
 core=E.fromstring(z.read('docProps/core.xml'))
 assert core.find('{http://purl.org/dc/elements/1.1/}creator').text==sys.argv[2]
 assert all(b'<a:t>' in z.read(n) for n in slides)
 assert any(n.startswith('ppt/media/') for n in z.namelist())
 assert any(n.startswith('ppt/notesSlides/notesSlide') and n.endswith('.xml') for n in z.namelist())
 print(json.dumps({'pages':len(slides),'native_text':True,'background':True,'notes':True}))`;
 execFileSync('python3',['-c',script,file,creator],{encoding:'utf8'});
}
function inspectPdf(file){assert.equal(fs.readFileSync(file).subarray(0,5).toString(),'%PDF-');const info=execFileSync('pdfinfo',[file],{encoding:'utf8'});assert.match(info,/Pages:\s+2\b/);}
test('real default PPTX, inferred PDF and explicit both outputs',{timeout:240000},()=>{
 for(const [name,args,formats] of [
  ['default',[],['pptx']],
  ['inferred.pdf',[],['pdf']],
  ['both',['--format','both'],['pptx','pdf']],
 ]){
  const result=run([fixture,'-o',name,...args]);assert.equal(result.status,0,result.stdout+result.stderr);
  const base=name.replace(/\.pdf$/,'');
  for(const fmt of formats){const file=path.join(tmp,base+'.'+fmt);if(fmt==='pptx')inspectPptx(file,'html2pptx');else inspectPdf(file);}
  if(formats.length===1)assert.ok(!fs.existsSync(path.join(tmp,base+(formats[0]==='pdf'?'.pptx':'.pdf'))));
 }
});
test('explicit PPTX overrides PDF suffix and synthetic author stays isolated',{timeout:90000},()=>{
 const profile=JSON.parse(fs.readFileSync(anonymous,'utf8'));profile.identity.name='Synthetic Presenter';
 const config=path.join(tmp,'synthetic.json');fs.writeFileSync(config,JSON.stringify(profile));
 const result=run([fixture,'--config',config,'-o','override.pdf','--format','pptx']);assert.equal(result.status,0,result.stdout+result.stderr);
 inspectPptx(path.join(tmp,'override.pptx'),'Synthetic Presenter');assert.ok(!fs.existsSync(path.join(tmp,'override.pdf')));
});
test('bad formats, missing inputs and multi-file PDF never report successful export',()=>{
 for(const args of [[fixture,'--format','typo'],['missing.html'],[fixture,fixture,'--format','pdf']]){
  const result=run([...args,'-o','invalid']);assert.notEqual(result.status,0,result.stdout+result.stderr);assert.ok(!fs.existsSync(path.join(tmp,'invalid.pdf')));assert.ok(!fs.existsSync(path.join(tmp,'invalid.pptx')));
 }
});
test('template padding, inline layout and final entrance animation survive PPTX extraction',{timeout:90000},async()=>{
 const html=path.join(tmp,'padding.html');
 fs.writeFileSync(html,`<!doctype html><style>body{margin:0}.slide{box-sizing:border-box;width:1280px;height:720px}p{margin:0;font-size:24px}[data-anim]{animation:enter 1s 3s both}@keyframes enter{from{transform:translateY(40px);opacity:0}to{transform:translateY(0);opacity:1}}</style><section class="slide" style="padding:42px 60px;display:flex;flex-direction:column;font-family:Arial"><p id="marker" data-anim>PaddingMarker</p><p>Second line</p></section>`);
 const {chromium}=require('playwright');const browser=await chromium.launch({channel:'chromium'});
 let expected;
 try{const page=await browser.newPage({viewport:{width:1280,height:720}});await page.goto(require('node:url').pathToFileURL(html).href);await page.evaluate(()=>document.getAnimations().forEach(a=>a.finish()));expected=await page.locator('#marker').boundingBox();}finally{await browser.close();}
 const result=run([html,'-o','padding.pptx']);assert.equal(result.status,0,result.stdout+result.stderr);
 const inspect=`import zipfile,xml.etree.ElementTree as E,json,sys
ns={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
with zipfile.ZipFile(sys.argv[1]) as z:
 root=E.fromstring(z.read('ppt/slides/slide1.xml'))
 shapes=[s for s in root.findall('.//p:sp',ns) if ''.join(t.text or '' for t in s.findall('.//a:t',ns))=='PaddingMarker']
 assert len(shapes)==1
 off=shapes[0].find('.//a:xfrm/a:off',ns)
 print(json.dumps({'x':int(off.attrib['x'])/9525,'y':int(off.attrib['y'])/9525}))`;
 const actual=JSON.parse(execFileSync('python3',['-c',inspect,path.join(tmp,'padding.pptx')],{encoding:'utf8'}));
 assert.ok(Math.abs(actual.x-expected.x)<1,JSON.stringify({expected,actual}));
 // Text boxes include a small vertical font-metric adjustment, but must retain padding.
 assert.ok(Math.abs(actual.y-expected.y)<8,JSON.stringify({expected,actual}));
});
test('local file URLs preserve spaces, Unicode, hash and percent characters',{timeout:90000},()=>{
 const {pathToFileURL}=require('node:url');
 const dir=path.join(tmp,'本地 素材 #50%');fs.mkdirSync(dir);
 const img=path.join(dir,'图片 #1%.png');
 // Tiny synthetic PNG; no personal material enters the fixture or package.
 fs.writeFileSync(img,Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6s3sAAAAASUVORK5CYII=','base64'));
 const html=path.join(dir,'课件 #1%.html');const uri=pathToFileURL(img).href;
 fs.writeFileSync(html,`<!doctype html><style>body{margin:0}.slide{width:1280px;height:720px;position:relative;display:flex;flex-direction:column;overflow:hidden}p{font:24px Arial;margin:30px}img{width:100px;height:100px}</style><section class="slide"><p>Local image</p><img src="${uri}"></section><section class="slide" style="background-image:url('${uri}')"><p>Local background</p></section>`);
 const out=path.join(dir,'结果 #1%');
 const result=run([html,'-o',out,'--format','both']);assert.equal(result.status,0,result.stdout+result.stderr);
 inspectPdf(out+'.pdf');
 execFileSync('python3',['-c',`import zipfile,sys
with zipfile.ZipFile(sys.argv[1]) as z:
 media=[z.read(n) for n in z.namelist() if n.startswith('ppt/media/')]
 original=open(sys.argv[2],'rb').read()
 assert media.count(original)>=2, 'Both inline image and background must retain original bytes'
`,out+'.pptx',img]);
});
process.on('exit',()=>{fs.rmSync(tmp,{recursive:true,force:true});});
