#!/usr/bin/env node
// 重建三种主题的同源对照；PDF / 页面截图另行渲染。
const fs=require('fs'),path=require('path'),{execFileSync}=require('child_process');
const {presets}=require('./theme');
const root=__dirname;
try {
 for(const id of presets) {
  const out=path.join(root,'previews','themes',id);
  fs.mkdirSync(out,{recursive:true});
  for(const [name,ext] of [['service-flow','mmd'],['service-roadmap','svg']]) {
   execFileSync(process.execPath,[path.join(root,'visuals.js'),'--input',path.join(root,'examples','diagrams',name+'.'+ext),'--output',path.join(out,'assets',name+'.png'),'--theme',id,'--export-theme',path.join(out,'assets')],{stdio:'inherit'});
  }
  const text=fs.readFileSync(path.join(root,'examples','theme-proposal.md'),'utf8').replace('theme: law-firm-brown','theme: '+id);
  fs.writeFileSync(path.join(out,'proposal.md'),text);
  execFileSync(process.execPath,[path.join(root,'render.js'),'--input',path.join(out,'proposal.md'),'--output',path.join(out,'proposal.docx'),'--cover','C','--full','--team-config',path.join(root,'examples','team-config.md'),'--lawyers','测试律师甲,测试律师乙'],{stdio:'inherit'});
 }
} catch(e) {console.error('主题样稿生成失败：'+e.message);process.exitCode=1;}
