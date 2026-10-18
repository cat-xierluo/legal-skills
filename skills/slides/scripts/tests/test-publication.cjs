'use strict';
// Entirely synthetic date components, assembled into test inputs below.
const syntheticDate = ['27', '03', '15'].join('');
const releaseDate = ['2026', '10', '18'].join('-');
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {spawnSync}=require('node:child_process');
const {buildList,checkLinks}=require('../pack-public');
const root=path.resolve(__dirname,'../..');
const baseline=buildList();
function run(stage,args){return spawnSync(process.execPath,[path.join(stage,'scripts/pack-public.js'),...args],{encoding:'utf8'});}
test('public candidate is complete and self-contained',()=>{
 assert.deepEqual(baseline.missing,[]); assert.deepEqual(checkLinks(baseline.files),[]);
 assert.ok(baseline.files.includes('.gitignore')); assert.ok(baseline.files.includes('LICENSE.txt'));
 for(const name of baseline.files) assert.ok(!/(?:^|\/)(?:TASKS|DECISIONS)\.md$|\.local\.|node_modules/.test(name),name);
});
test('packaging blocks leakage, missing links, symlinks and destructive destinations',()=>{
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'slides-publish-')); const stage=path.join(tmp,'source');
 try{
  for(const rel of baseline.files){const dest=path.join(stage,rel);fs.mkdirSync(path.dirname(dest),{recursive:true});fs.copyFileSync(path.join(root,rel),dest);}
  const clean=run(stage,['--out-dir',path.join(tmp,'bundle')]);assert.equal(clean.status,0,clean.stdout+clean.stderr);
  const sentinel=path.join(tmp,'bundle','sentinel');fs.writeFileSync(sentinel,'keep');
  assert.notEqual(run(stage,['--out-dir',path.join(tmp,'bundle')]).status,0);assert.equal(fs.readFileSync(sentinel,'utf8'),'keep');
  assert.notEqual(run(stage,['--out-dir']).status,0);assert.notEqual(run(stage,['--unknown']).status,0);
  const skill=path.join(stage,'SKILL.md');const original=fs.readFileSync(skill,'utf8');
  fs.appendFileSync(skill,['\n案例：',syntheticDate,' 海岚 deck\n'].join(''));
  const leak=run(stage,['--out-dir',path.join(tmp,'leak')]);assert.notEqual(leak.status,0);assert.match(leak.stdout,/G9/);assert.ok(!fs.existsSync(path.join(tmp,'leak')));
  fs.writeFileSync(skill,original+'\n[broken](references/absent.md)\n');assert.notEqual(run(stage,['--list']).status,0);
  fs.writeFileSync(skill,original);const html=path.join(stage,'example.html');fs.unlinkSync(html);fs.symlinkSync(skill,html);
  assert.notEqual(run(stage,['--list']).status,0);
 }finally{fs.rmSync(tmp,{recursive:true,force:true});}
});
