// 无文字的装饰图；布局固定，颜色来自当前主题。
const fs = require('fs'), path = require('path');
const crypto = require('crypto');
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
function manifest(theme,pngs) {
 return {schemaVersion:1,colorsSha256:sha(JSON.stringify(theme.colors)),files:Object.fromEntries(Object.entries(pngs).map(([name,data])=>[name+'.png',sha(data)]))};
}
function sources(theme) {
const c = Object.fromEntries(Object.entries(theme.colors).map(([k,v])=>[k,'#'+v]));
const svg = body => `<svg xmlns="http://www.w3.org/2000/svg" width="1260" height="1782" viewBox="0 0 210 297"><rect width="210" height="297" fill="${c.paper}"/>${body}</svg>`;
const art = {
  C: `<defs><clipPath id="band"><rect width="210" height="95"/></clipPath></defs><g clip-path="url(#band)"><rect width="210" height="95" fill="${c.primary}"/><circle cx="180" cy="10" r="69" fill="none" stroke="${c.gold}" stroke-width="2" opacity=".5"/><circle cx="185" cy="15" r="45" fill="${c.deep}"/></g><path d="M22 231.5H188" stroke="${c.primary}" stroke-width=".529"/><path d="M77.33 238.5V251 M132.67 238.5V251" stroke="${c.rule}" stroke-width=".265"/><path d="M0 273H210" stroke="${c.rule}" stroke-width=".265"/>`,
  D: `<path d="M0 0H210V82.5L0 150Z" fill="${c.primary}"/><circle cx="168" cy="94" r="23.25" fill="none" stroke="${c.gold}" stroke-width="1.5" opacity=".55"/><path d="M22 258.3H188" stroke="${c.primary}" stroke-width=".529"/>`,
  E: `<defs><clipPath id="band"><rect y="223.5" width="210" height="73.5"/></clipPath></defs><g clip-path="url(#band)"><rect y="223.5" width="210" height="73.5" fill="${c.primary}"/><circle cx="35" cy="282" r="64" fill="none" stroke="${c.gold}" stroke-width="2" opacity=".45"/><circle cx="25" cy="282" r="40" fill="${c.deep}"/></g><path d="M22 243.5H188 M77.33 249.7V261.3 M132.67 249.7V261.3" stroke="${c.gold}" stroke-width=".35"/>`,
  F: `<path d="M0 21.7H210 M0 274.7H210" stroke="${c.primary}" stroke-width=".6"/><path d="M22 22V274.7 M188 22V274.7" stroke="${c.rule}" stroke-width=".3"/><rect x="174" y="28" width="14" height="14" fill="${c.primary}"/>`,
};

const result = Object.fromEntries(Object.entries(art).map(([key,body])=>['cover-'+key,svg(body)]));
result['honor-badge'] = `<svg xmlns="http://www.w3.org/2000/svg" width="108" height="108" viewBox="0 0 100 100"><circle cx="50" cy="50" r="50" fill="${c.gold}"/><path fill="${c.onPrimary}" d="M50 25L57 43L77 43L61 55L67 75L50 63L33 75L39 55L23 43L43 43Z"/></svg>`;
return result;
}
async function rasterize(theme) {
 let sharp;
 try {sharp = require('sharp');} catch (_) {throw new Error('自定义主题/重建装饰需要 sharp：npm install -g sharp；设置 NODE_PATH 后重试');}
 const result={};
 for (const [name,svg] of Object.entries(sources(theme))) result[name]=await sharp(Buffer.from(svg)).png().toBuffer();
 return result;
}
async function loadDecor(theme) {
 const file=path.join(__dirname,'assets','decor-manifest.json');
 const saved=fs.existsSync(file)?JSON.parse(fs.readFileSync(file,'utf8')):null;
 if (saved?.schemaVersion===1 && saved.colorsSha256===sha(JSON.stringify(theme.colors))) {
  const buffers={};
  for(const name of ['cover-C','cover-D','cover-E','cover-F','honor-badge']) {
   const png=path.join(__dirname,'assets',name+'.png');
   if(!fs.existsSync(png))return rasterize(theme);
   buffers[name]=fs.readFileSync(png);
   if(saved.files[name+'.png']!==sha(buffers[name]))return rasterize(theme);
  }
  return buffers;
 }
 return rasterize(theme);
}
module.exports={sources,rasterize,loadDecor,manifest};
