// 可选维护工具；默认主题普通生成使用随包 PNG。
const fs = require('fs'), path = require('path');
const {loadTheme} = require('./theme');
const {sources,rasterize,manifest} = require('./decor');
(async()=>{
 const args=process.argv.slice(2); let theme='law-firm-brown', output=path.join(__dirname,'assets');
 for(let i=0;i<args.length;i++) {
  if(args[i]==='--theme')theme=args[++i];
  else if(args[i]==='--output')output=args[++i];
  else throw new Error('用法：node word/build-decor.js [--theme 名称或JSON] [--output 目录]');
 }
 const selected=loadTheme(theme), svgs=sources(selected), pngs=await rasterize(selected);
 if(theme!=='law-firm-brown' && path.resolve(output)===path.join(__dirname,'assets'))throw new Error('其他主题请指定 --output，避免覆盖默认底图');
 fs.mkdirSync(output,{recursive:true});
 for(const name of Object.keys(svgs)) {
  fs.writeFileSync(path.join(output,name+'.svg'),svgs[name]+'\n');
  fs.writeFileSync(path.join(output,name+'.png'),pngs[name]);
 }
 fs.writeFileSync(path.join(output,'decor-manifest.json'),JSON.stringify(manifest(selected,pngs),null,2)+'\n');
 console.log('已重建：'+selected.name+' → '+output);
})().catch(e=>{console.error(e.message);process.exitCode=1});
