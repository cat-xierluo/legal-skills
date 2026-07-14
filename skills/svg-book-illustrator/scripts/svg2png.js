/**
 * svg2png.js
 * SVG → PNG 高分辨率转换，适用于书籍印刷。
 *
 * 由 svg-article-illustrator/scripts/svg2png.js 简化而来：
 * - 去掉"强制输出到 SVG 源目录"限制，允许指定任意输出路径
 * - 默认 DPI 改为 600（印刷推荐）
 *
 * 依赖：npm install puppeteer（需要 Chrome/Chromium）
 *
 * 用法：
 *   node svg2png.js input.svg                      # 同目录输出，600 DPI
 *   node svg2png.js input.svg output.png 300        # 指定输出和 DPI
 *   node svg2png.js input/ output/                  # 批量转换目录
 */

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const DEFAULT_DPI = 600;
const MIN_DPI = 72;
const MAX_DPI = 2400;
const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const RENDER_FONT_CSS = path.resolve(SCRIPT_DIR, "../assets/render-fonts.css");

async function loadPuppeteer() {
  try {
    const module = await import("puppeteer");
    return module.default;
  } catch {
    throw new Error(
      "缺少依赖: puppeteer\n请先运行: npm install puppeteer"
    );
  }
}

function findChrome() {
  const paths = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
  ];
  for (const p of paths) {
    if (fs.existsSync(p)) return p;
  }
  return undefined;
}

async function svgToPng(inputPath, outputPath, dpi = DEFAULT_DPI) {
  if (!fs.existsSync(inputPath)) {
    throw new Error(`文件不存在: ${inputPath}`);
  }

  const puppeteer = await loadPuppeteer();
  const svgContent = fs.readFileSync(inputPath, "utf8");
  if (!fs.existsSync(RENDER_FONT_CSS)) {
    throw new Error(`受控字体样式不存在: ${RENDER_FONT_CSS}`);
  }
  const renderFontCss = fs.readFileSync(RENDER_FONT_CSS, "utf8");
  const html = `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    ${renderFontCss}
    html, body { margin: 0; padding: 0; background: transparent; }
    svg { display: block; }
  </style>
</head>
<body>${svgContent}</body>
</html>`;
  let browser;

  try {
    browser = await puppeteer.launch({
      headless: "new",
      args: [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--no-first-run",
        "--no-zygote",
      ],
      executablePath: findChrome(),
    });

    const page = await browser.newPage();
    await page.setContent(html, { waitUntil: "domcontentloaded", timeout: 10000 });
    await page.waitForSelector("svg", { timeout: 10000 });
    await page.evaluate(async () => {
      if (document.fonts) await document.fonts.ready;
    });

    const dimensions = await page.evaluate(() => {
      const svg = document.querySelector("svg");
      if (!svg) throw new Error("未找到 <svg> 元素");
      const vb = svg.viewBox.baseVal;
      const w = svg.getAttribute("width");
      const h = svg.getAttribute("height");
      return {
        width: w ? parseFloat(w) : vb.width || 720,
        height: h ? parseFloat(h) : vb.height || 400,
      };
    });

    const scale = dpi / 96;
    await page.setViewport({
      width: Math.round(dimensions.width),
      height: Math.round(dimensions.height),
      deviceScaleFactor: scale,
    });

    const element = await page.$("svg");
    if (!element) throw new Error("SVG 元素未加载");

    fs.mkdirSync(path.dirname(outputPath), { recursive: true });
    await element.screenshot({ path: outputPath, omitBackground: true });

    const pxW = Math.round(dimensions.width * scale);
    const pxH = Math.round(dimensions.height * scale);
    console.log(`  ${dpi}DPI ${pxW}×${pxH}px → ${outputPath}`);
  } finally {
    if (browser) {
      await browser.close().catch(() => {});
    }
  }
}

async function convertFile(input, output, dpi) {
  if (output) {
    const outDir = path.dirname(output);
    if (outDir) fs.mkdirSync(outDir, { recursive: true });
  } else {
    output = input.replace(/\.svg$/i, ".png");
  }
  await svgToPng(input, output, dpi);
}

async function convertDir(inputDir, outputDir, dpi) {
  const files = fs.readdirSync(inputDir).filter((f) => f.endsWith(".svg"));
  if (files.length === 0) {
    console.log(`目录中无 SVG 文件: ${inputDir}`);
    return;
  }
  fs.mkdirSync(outputDir, { recursive: true });
  console.log(`批量转换 ${files.length} 个文件 (${dpi} DPI)...`);
  for (const f of files) {
    await convertFile(
      path.join(inputDir, f),
      path.join(outputDir, f.replace(/\.svg$/i, ".png")),
      dpi
    );
  }
  console.log(`完成: ${files.length} 张 PNG → ${outputDir}`);
}

// CLI
const [,, arg1, arg2, arg3] = process.argv;

if (!arg1) {
  console.log("SVG → PNG 转换（书籍印刷用）");
  console.log("");
  console.log("用法:");
  console.log("  node svg2png.js <input.svg> [output.png] [dpi]");
  console.log("  node svg2png.js <input-dir> <output-dir> [dpi]");
  console.log("");
  console.log("示例:");
  console.log("  node svg2png.js fig1.svg                  # 同目录，600 DPI");
  console.log("  node svg2png.js fig1.svg fig1.png 300     # 300 DPI");
  console.log("  node svg2png.js figures/ output/ 600      # 批量转换");
  console.log("");
  console.log(`DPI 范围: ${MIN_DPI}–${MAX_DPI}，默认 ${DEFAULT_DPI}`);
  process.exit(0);
}

if (!fs.existsSync(arg1)) {
  console.error(`路径不存在: ${arg1}`);
  process.exit(1);
}

const dpi = parseInt(arg3 || arg2) || DEFAULT_DPI;
if (dpi < MIN_DPI || dpi > MAX_DPI) {
  console.error(`DPI 应在 ${MIN_DPI}–${MAX_DPI} 之间`);
  process.exit(1);
}

const stat = fs.statSync(arg1);
if (stat.isDirectory()) {
  const outDir = arg2 || path.join(arg1, "png");
  convertDir(arg1, outDir, dpi).catch((err) => {
    console.error("批量转换失败:", err.message);
    process.exit(1);
  });
} else {
  const output = arg2 && !arg2.match(/^\d+$/) ? arg2 : undefined;
  convertFile(arg1, output, dpi).catch((err) => {
    console.error("转换失败:", err.message);
    process.exit(1);
  });
}
