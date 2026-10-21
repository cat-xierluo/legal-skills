#!/usr/bin/env node

/**
 * 模板预览图生成器
 *
 * 为 references/templates/ 下的每个 HTML 模板生成缩略预览图，
 * 并输出一个预览索引页面供用户视觉对比选择。
 *
 * 用法：
 *   node generate-previews.js [--templates-dir ../references/templates]
 */

const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright');

const TEMPLATES_DIR = path.resolve(__dirname, '../references/templates');
const PREVIEWS_DIR = path.join(TEMPLATES_DIR, 'previews');
const THUMB_WIDTH = 480;
const THUMB_HEIGHT = 270;

async function main() {
  const args = process.argv.slice(2);
  let templatesDir = TEMPLATES_DIR;

  const dirIdx = args.indexOf('--templates-dir');
  if (dirIdx !== -1 && args[dirIdx + 1]) {
    templatesDir = path.resolve(args[dirIdx + 1]);
  }

  if (!fs.existsSync(templatesDir)) {
    console.error(`模板目录不存在: ${templatesDir}`);
    process.exit(1);
  }

  fs.mkdirSync(PREVIEWS_DIR, { recursive: true });

  const htmlFiles = fs.readdirSync(templatesDir)
    .filter(f => f.endsWith('.html') && f !== 'index.html')
    .sort();

  if (htmlFiles.length === 0) {
    console.error('未找到 HTML 模板文件');
    process.exit(1);
  }

  console.log(`找到 ${htmlFiles.length} 个模板文件，开始生成预览...\n`);

  const browser = await chromium.launch({ channel: 'chromium' });
  const context = await browser.newContext({
    viewport: { width: 1000, height: 563 },
    deviceScaleFactor: 1,
  });

  const results = [];

  for (const file of htmlFiles) {
    const filePath = path.join(templatesDir, file);
    const thumbName = file.replace('.html', '.png');
    const thumbPath = path.join(PREVIEWS_DIR, thumbName);

    console.log(`  渲染: ${file}`);

    try {
      const page = await context.newPage();
      await page.goto(`file://${filePath}`, { waitUntil: 'networkidle' });

      // 等待动画完成
      await page.waitForTimeout(500);

      await page.screenshot({
        path: thumbPath,
        clip: { x: 0, y: 0, width: 1000, height: 563 },
      });

      await page.close();

      // 从文件名提取信息
      const match = file.match(/^(\d+)-(.+)\.html$/);
      const num = match ? match[1] : '?';
      const slug = match ? match[2] : file.replace('.html', '');

      results.push({ file, thumbName, num, slug });
      console.log(`  ✓ ${thumbName}`);
    } catch (err) {
      console.error(`  ✗ ${file}: ${err.message}`);
    }
  }

  await browser.close();

  // 生成预览索引页
  if (results.length > 0) {
    generateIndexPage(results);
  }

  console.log(`\n完成！生成 ${results.length} 个预览图，保存在 references/templates/previews/`);
}

function generateIndexPage(results) {
  const cards = results.map(r => {
    const title = r.slug.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    return `
    <div class="card">
      <div class="thumb-wrap">
        <img src="previews/${r.thumbName}" alt="${title}" loading="lazy">
      </div>
      <div class="card-info">
        <span class="num">#${r.num}</span>
        <span class="name">${title}</span>
      </div>
    </div>`;
  }).join('');

  const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>幻灯片模板预览</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background: #f5f5f4; padding: 32px; }
  h1 { font-size: 24px; margin-bottom: 8px; color: #18181b; }
  p.subtitle { font-size: 14px; color: #71717a; margin-bottom: 32px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 24px; }
  .card { background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.08); transition: box-shadow 0.2s; }
  .card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.12); }
  .thumb-wrap { aspect-ratio: 16/9; background: #e4e4e7; overflow: hidden; }
  .thumb-wrap img { width: 100%; height: 100%; object-fit: cover; }
  .card-info { padding: 12px 16px; display: flex; align-items: center; gap: 10px; }
  .num { font-size: 12px; font-weight: 700; color: #d97706; letter-spacing: 0.5px; }
  .name { font-size: 14px; font-weight: 500; color: #3f3f46; }
</style>
</head>
<body>
  <h1>幻灯片模板预览</h1>
  <p class="subtitle">共 ${results.length} 个模板 · 点击查看大图</p>
  <div class="grid">${cards}
  </div>
</body>
</html>`;

  fs.writeFileSync(path.join(TEMPLATES_DIR, 'index.html'), html);
  console.log('  生成预览索引页: references/templates/index.html');
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
