#!/usr/bin/env node
// 用同一套组件重建四款模板与匿名成品，避免只修代码而遗留旧 DOCX。
const fs = require('fs'), path = require('path'), {execFileSync} = require('child_process');
try {require.resolve('docx');} catch (_) {
  console.error('缺少 docx：npm install -g docx；设置 NODE_PATH 后重试。'); process.exit(2);
}
const root = __dirname;
for (const cover of ['C', 'D', 'E', 'F']) {
  execFileSync(process.execPath, [path.join(root, 'template.js'),
    path.join(root, 'templates', `legal-proposal-${cover}.docx`), '--cover=' + cover], {stdio: 'inherit'});
  execFileSync(process.execPath, [path.join(root, 'render.js'),
    '--input', path.join(root, 'examples', 'proposal.md'),
    '--output', path.join(root, 'previews', `proposal-${cover}.docx`),
    '--cover', cover, '--full', '--team-config', path.join(root, 'examples', 'team-config.md'),
    '--lawyers', '测试律师甲,测试律师乙'], {stdio: 'inherit'});
}
fs.copyFileSync(path.join(root, 'templates', 'legal-proposal-C.docx'), path.join(root, 'legal-proposal-OOXML-template.docx'));
execFileSync(process.execPath, [path.join(root, 'render.js'),
  '--input', path.join(root, 'examples', 'proposal-with-credentials.md'),
  '--output', path.join(root, 'previews', 'proposal-credentials.docx'),
  '--cover', 'C', '--full', '--team-config', path.join(root, 'examples', 'team-config.md'),
  '--lawyers', '测试律师甲,测试律师乙'], {stdio: 'inherit'});
console.log('已同步四款模板、四份匿名预览、证照示例和默认 C 模板。PDF/截图须另行渲染验收。');
