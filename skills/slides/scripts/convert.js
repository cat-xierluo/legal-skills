#!/usr/bin/env node
/**
 * convert.js - CLI entry point for HTML → PPTX/PDF conversion
 *
 * Usage:
 *   node convert.js slides.html -o output.pptx
 *   node convert.js slides.html -o output.pdf --format pdf
 *   node convert.js ./slides-dir/ -o output.pptx --format both
 *   node convert.js page1.html page2.html page3.html -o output.pptx
 *
 * Supports:
 *   - Single HTML file (auto-detect single/multi-page)
 *   - Directory of HTML files (sorted by filename)
 *   - Multiple explicit files
 *   - Output to PPTX, PDF, or both
 */

const fs = require('fs');
const path = require('path');
const { program, Option } = require('commander');
const PptxGenJS = require('pptxgenjs');
const { html2pptxMulti } = require('./html2pptx');
const html2pdf = require('./html2pdf');
const { extractStyle, listStyles, saveStyle } = require('./extract-style');
const { loadProfile } = require('./load-profile');

program
  .name('html2pptx')
  .description('将 HTML 幻灯片转换为高保真可编辑 PPTX 或 PDF')
  .argument('[input...]', 'HTML 文件或目录（多个文件由 shell 展开）')
  .option('-o, --output <path>', '输出文件路径（默认：与源文件同目录）')
  .addOption(new Option('-f, --format <type>', '输出格式；未指定则按输出后缀选择，其余默认 pptx').choices(['pptx', 'pdf', 'both']))
  .addOption(new Option('--layout <ratio>', '幻灯片比例').choices(['16:9', '4:3']).default('16:9'))
  .option('--selector <css>', '幻灯片容器 CSS 选择器（多页 HTML）')
  .addOption(new Option('--background-mode <mode>', 'PPTX 背景策略').choices(['auto', 'freeze', 'native']).default('auto'))
  .option('--config <path>', 'slides 本地配置（profile）路径；不传则按课件项目/用户目录顺序解析')
  .option('--strict', '严格模式（验证错误时中止）')
  .option('--landscape', 'PDF 横向输出')
  .option('--extract-style', '从 HTML 提取风格定义（输出 JSON）')
  .option('--save-style <name>', '提取风格并保存到个人风格目录')
  .option('--save <name>', '--save-style 的别名')
  .option('--list-styles', '列出风格库中所有可用风格')
  .parse();

const opts = program.opts();
const inputs = program.args;

// ── 本地配置：一次运行只加载一份；坏配置直接报错，不静默降级为匿名 ──
const profileLoad = loadProfile({ configPath: opts.config });
if (profileLoad.errors.length > 0) {
  for (const err of profileLoad.errors) console.error(`配置错误: ${err}`);
  console.error('修正配置或移除 --config 后重试；不会以匿名身份继续。');
  process.exit(1);
}
const profile = profileLoad.profile;
console.log(
  `配置来源: ${profileLoad.source}` +
  (profileLoad.configPath ? ` (${profileLoad.configPath})` : '') +
  (profileLoad.warnings.length > 0 ? ` — ${profileLoad.warnings.length} 条提示` : '')
);

const saveStyleName = opts.saveStyle || opts.save;

// ── Style management commands ──
if (opts.listStyles) {
  listStyles();
  process.exit(0);
}

const styleMode = !!(opts.extractStyle || saveStyleName);

async function runStyleCommand() {
  if (inputs.length === 0) {
    console.error('请指定 HTML 文件进行风格提取');
    process.exit(1);
  }
  const style = await extractStyle(inputs[0], { name: saveStyleName });
  if (saveStyleName) {
    saveStyle(style, saveStyleName);
  } else {
    const outPath = opts.output || inputs[0].replace(/\.html?$/i, '-style.json');
    fs.writeFileSync(outPath, JSON.stringify(style, null, 2), 'utf-8');
    console.log(`\n风格已导出: ${outPath}`);
  }
}

async function collectFiles(inputs) {
  const files = [];
  for (const input of inputs) {
    const stat = fs.statSync(input);
    if (stat.isDirectory()) {
      const dirFiles = fs.readdirSync(input)
        .filter(f => f.endsWith('.html') || f.endsWith('.htm'))
        .sort()
        .map(f => path.join(input, f));
      files.push(...dirFiles);
    } else if (stat.isFile()) {
      files.push(input);
    }
  }
  return files;
}

async function runConversion() {
  const files = await collectFiles(inputs);

  if (files.length === 0) {
    console.error('未找到 HTML 文件');
    process.exit(1);
  }

  console.log(`找到 ${files.length} 个 HTML 文件`);

  // Determine output paths — default to same directory as first input file
  const firstFile = files[0];
  const inputDir = path.dirname(path.resolve(firstFile));
  const inputBase = path.basename(firstFile, path.extname(firstFile));
  const defaultOutputBase = path.join(inputDir, inputBase);

  const outputPath = opts.output;
  const outputExtension = path.extname(outputPath || '').toLowerCase();
  const format = opts.format || (outputExtension === '.pdf' ? 'pdf' : 'pptx');
  if (files.length > 1 && format !== 'pptx') {
    throw new Error('PDF/双格式仅支持一个多页 HTML；请先合并输入，或使用 --format pptx。');
  }
  const baseName = outputPath
    ? outputPath.replace(/\.(pptx|pdf)$/i, '')
    : defaultOutputBase;

  const pptxPath = format === 'pdf' ? null : (outputExtension === '.pptx' ? outputPath : `${baseName}.pptx`);
  const pdfPath = format === 'pptx' ? null : (outputExtension === '.pdf' ? outputPath : `${baseName}.pdf`);

  const allWarnings = [];
  let totalSlides = 0;

  // --- PPTX conversion ---
  if (pptxPath) {
    const pptx = new PptxGenJS();
    pptx.layout = opts.layout === '4:3' ? 'LAYOUT_4x3' : 'LAYOUT_16x9';
    // 导出元数据跟随本地配置；未配置身份时回退到工具名，不写死个人信息。
    const authorParts = [profile.identity?.name, profile.identity?.organization].filter(Boolean);
    pptx.author = authorParts.length > 0 ? authorParts.join(' · ') : 'html2pptx';

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      console.log(`[${i + 1}/${files.length}] 转换: ${path.basename(file)}`);

      try {
        // Try multi-page first
        const results = await html2pptxMulti(file, pptx, {
          slideSelector: opts.selector || null,
          lenient: !opts.strict,
          forceViewport: true,
          backgroundMode: opts.backgroundMode,
        });

        for (const result of results) {
          totalSlides++;
          if (result.warnings && result.warnings.length > 0) {
            allWarnings.push({ file: path.basename(file), warnings: result.warnings });
          }
        }
      } catch (err) {
        throw new Error(`转换失败（${path.basename(file)}）：${err.message}`);
      }
    }

    if (totalSlides === 0) throw new Error('未生成任何幻灯片，停止导出。');
    await pptx.writeFile({ fileName: pptxPath });
    console.log(`\nPPTX 已保存: ${pptxPath} (${totalSlides} 页)`);
  }

  // --- PDF conversion ---
  if (pdfPath) {
    console.log('生成 PDF...');
    await html2pdf(files[0], pdfPath, {
      format: opts.layout === '4:3' ? '4:3' : '16:9',
      landscape: opts.landscape,
    });
    console.log(`PDF 已保存: ${pdfPath}`);
  }

  // Print warnings
  if (allWarnings.length > 0) {
    console.log(`\n--- 警告 ---`);
    for (const { file, warnings } of allWarnings) {
      for (const w of warnings) {
        console.log(`  [${file}] ${w}`);
      }
    }
  }

  console.log(`\n完成!`);
}

if (styleMode) {
  // 异步工作必须先 await 完成再退出——否则 process.exit 会抢在风格提取前杀掉进程。
  runStyleCommand().then(
    () => process.exit(0),
    (err) => {
      console.error(`错误: ${err.message}`);
      process.exit(1);
    }
  );
} else {
  if (inputs.length === 0) {
    program.help();
    process.exit(0);
  }
  runConversion().catch(err => {
    console.error(`致命错误: ${err.message}`);
    process.exit(1);
  });
}
