'use strict';
// Entirely synthetic date components, assembled into test inputs below.
const syntheticDate = ['27', '03', '15'].join('');
const releaseDate = ['2026', '10', '18'].join('-');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { scan } = require('../check-privacy');
function inspect(text, rel = 'sample.md') {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'slides-privacy-'));
  try {
    fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), text);
    return scan([rel], root).findings;
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
}
test('abbreviated institution and contextual identifiers are blocked', () => {
  const cases = [
    [['海岚', '政法'].join(''), 'G1'],
    [['案例：', syntheticDate, ' 海岚 37 页宣讲课件'].join(''), 'G9'],
    [['海岚 ', syntheticDate, ' deck v3'].join(''), 'G9'],
    [['用户反馈（', '海岚', '）：布局需要调整'].join(''), 'G10'],
    [['来源（', '海岚', ' v4）：布局修复'].join(''), 'G10'],
  ];
  for (const [text, id] of cases) assert.ok(inspect(text).some(f => f.id === id), id);
});
test('nearby legitimate release, palette and generic examples remain valid', () => {
  for (const text of [`## [1.5.15] - ${releaseDate} — 课件转换修复`, '课件配色 #111111 / #FBF8F2', '用户反馈（课件）：页码错误', '案例（合成）：测试布局', '默认行为与 v1.5.10 一致']) {
    assert.deepEqual(inspect(text), [], text);
  }
});
test('identity templates cannot contain data and author exemptions stay narrow', () => {
  assert.ok(inspect(JSON.stringify({identity:{name:'Synthetic Presenter'}}), 'config/profile.example.json').some(f=>f.id==='G8'));
  assert.deepEqual(inspect(JSON.stringify({identity:{name:''}}), 'config/profile.example.json'), []);
  const marker = ['杨卫薪', '律师（微信ywxlaw）'].join('');
  assert.deepEqual(inspect('author: '+marker, 'SKILL.md'), []);
  assert.ok(inspect('author: '+marker+' '+['海岚','政法'].join(''), 'SKILL.md').some(f=>f.id==='G1'));
});
test('missing files and links fail closed', () => {
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'slides-scan-'));
  try {
    assert.throws(()=>scan(['absent.md'],root));
    fs.writeFileSync(path.join(root,'real.md'),'anonymous');
    fs.symlinkSync('real.md',path.join(root,'link.md'));
    assert.throws(()=>scan(['link.md'],root));
    assert.throws(()=>scan(['../outside.md'],root));
  } finally {fs.rmSync(root,{recursive:true,force:true});}
});
