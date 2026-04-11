#!/usr/bin/env node
/**
 * convert.js - CLI entry point for HTML → PPTX/PDF conversion
 *
 * Usage:
 *   node convert.js slides.html -o output.pptx
 *   node convert.js slides.html -o output.pdf
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
const { program } = require('commander');
const PptxGenJS = require('pptxgenjs');
const html2pptx = require('./html2pptx');
const { html2pptxMulti } = require('./html2pptx');
const html2pdf = require('./html2pdf');

program
  .name('html2pptx')
  .description('将 HTML 幻灯片转换为高保真可编辑 PPTX 或 PDF')
  .argument('<input...>', 'HTML 文件、目录或 glob 模式')
  .option('-o, --output <path>', '输出文件路径（默认：与源文件同目录）')
  .option('-f, --format <type>', '输出格式: pptx, pdf, both', 'pptx')
  .option('--layout <ratio>', '幻灯片比例: 16:9, 4:3', '16:9')
  .option('--selector <css>', '幻灯片容器 CSS 选择器（多页 HTML）')
  .option('--strict', '严格模式（验证错误时中止）')
  .option('--landscape', 'PDF 横向输出')
  .parse();

const opts = program.opts();
const inputs = program.args;

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

async function main() {
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
  const format = opts.format;
  const baseName = outputPath
    ? outputPath.replace(/\.(pptx|pdf)$/i, '')
    : defaultOutputBase;

  const pptxPath = format === 'pdf' ? null : (outputPath?.endsWith('.pptx') ? outputPath : `${baseName}.pptx`);
  const pdfPath = format === 'pptx' ? null : (outputPath?.endsWith('.pdf') ? outputPath : `${baseName}.pdf`);

  const allWarnings = [];
  let totalSlides = 0;

  // --- PPTX conversion ---
  if (pptxPath) {
    const pptx = new PptxGenJS();
    pptx.layout = opts.layout === '4:3' ? 'LAYOUT_4x3' : 'LAYOUT_16x9';
    pptx.author = 'html2pptx';

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      console.log(`[${i + 1}/${files.length}] 转换: ${path.basename(file)}`);

      try {
        // Try multi-page first
        const results = await html2pptxMulti(file, pptx, {
          slideSelector: opts.selector || null,
          lenient: !opts.strict,
          forceViewport: true,
        });

        for (const result of results) {
          totalSlides++;
          if (result.warnings && result.warnings.length > 0) {
            allWarnings.push({ file: path.basename(file), warnings: result.warnings });
          }
        }
      } catch (err) {
        console.error(`  错误: ${err.message}`);
        if (opts.strict) process.exit(1);
      }
    }

    await pptx.writeFile({ fileName: pptxPath });
    console.log(`\nPPTX 已保存: ${pptxPath} (${totalSlides} 页)`);
  }

  // --- PDF conversion ---
  if (pdfPath) {
    // For PDF, use the first HTML file or concatenate
    // If single multi-page HTML, convert directly
    // If multiple files, convert each and merge concept via Playwright
    if (files.length === 1) {
      console.log(`生成 PDF...`);
      await html2pdf(files[0], pdfPath, {
        format: opts.layout === '4:3' ? '4:3' : '16:9',
        landscape: opts.landscape,
      });
      console.log(`PDF 已保存: ${pdfPath}`);
    } else {
      // Multiple files: convert first file (multi-page handling)
      // For true multi-file PDF, would need a merge step
      console.log(`生成 PDF（仅处理首个文件）...`);
      await html2pdf(files[0], pdfPath, {
        format: opts.layout === '4:3' ? '4:3' : '16:9',
        landscape: opts.landscape,
      });
      console.log(`PDF 已保存: ${pdfPath}`);
      if (files.length > 1) {
        console.log(`注意: PDF 模式当前仅处理第一个 HTML 文件。如需多文件，请先合并为一个 HTML。`);
      }
    }
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

main().catch(err => {
  console.error(`致命错误: ${err.message}`);
  process.exit(1);
});
