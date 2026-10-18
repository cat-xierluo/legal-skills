/**
 * html2pdf-scrollsnap-hd - 高保真「垂直 scroll-snap + WebGL 招牌背景」HTML 转多页 PDF
 *
 * 适用场景:HTML 用 body{scroll-snap-type:y} + .slide{width:100vw;height:100vh}
 * 形态(非 #deck translateX carousel),且叠加 WebGL 动态背景 / ASCII 封面层 /
 * IntersectionObserver 按 slide 切 light-bg / data-anim 入场动画。
 * 标准 convert.js / html2pdf.js 的 @page+page-break 在 position:fixed WebGL canvas
 * 与 scroll-snap 下分页不可靠,故采用「逐张 scrollIntoView → 截视口 → 合并」法,
 * 视觉 100% 还原(含招牌 WebGL),代价是 PDF 文字为图片(不可选/搜索)。
 *
 * 算法:
 *   1. channel=chrome + --use-gl=swiftshader 让 headless 下 WebGL 真实绘制
 *   2. emulateMedia reducedMotion:'no-preference' 防止 low-power 降级(canvas 不画)
 *   3. 注入 CSS:隐藏 #nav/#hint/#overview(导航 UI 不进 PDF)、关掉 scroll-snap
 *      避免干扰 scrollIntoView 精确定位
 *   4. document.fonts.ready + 初始等待,让 webfont/本地字体就绪
 *   5. 逐张:scrollIntoView(instant) → 强制 [data-anim] opacity:1/transform:none
 *      → 等 IntersectionObserver 切 light-bg + WebGL 绘制稳定 → screenshot(clip 视口)
 *   6. ImageMagick (magick) 按字典序合并 PNG → 多页 PDF
 *
 * 已在多套真实 scroll-snap + WebGL 课件上验证。
 */
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
const os = require('os');

const SLIDE_W = 1280;
const SLIDE_H = 720;
const DPR = 2; // 2560×1440 HD
const STABILIZE_MS = 1100; // IntersectionObserver + WebGL 帧 + transition

async function html2pdfScrollsnapHD(htmlFile, pdfPath, options = {}) {
  const { onProgress = null } = options;
  const filePath = path.isAbsolute(htmlFile) ? htmlFile : path.join(process.cwd(), htmlFile);
  const absPdf = path.isAbsolute(pdfPath) ? pdfPath : path.join(process.cwd(), pdfPath);
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'slides-snaphd-'));

  const browser = await chromium.launch({
    channel: 'chrome',
    args: [
      '--use-gl=swiftshader',
      '--enable-webgl',
      '--ignore-gpu-blocklist',
      '--enable-features=VaapiVideoDecoder',
    ],
  });
  try {
    const context = await browser.newContext({
      viewport: { width: SLIDE_W, height: SLIDE_H },
      deviceScaleFactor: DPR,
    });
    const page = await context.newPage();
    await page.emulateMedia({ media: 'screen', reducedMotion: 'no-preference' });
    await page.goto(`file://${filePath}`, { waitUntil: 'load', timeout: 60000 });

    // 隐藏导航 UI + 关闭 scroll-snap 干扰
    await page.addStyleTag({
      content: `
        #nav,#hint,#overview{display:none!important;}
        html,body{scroll-snap-type:none!important;}
        .slide{scroll-snap-align:none!important;}
      `,
    });

    // 关 low-power,确保 WebGL 持续绘制
    await page.evaluate(() => {
      document.body.classList.remove('low-power');
      try {
        window.dispatchEvent(new CustomEvent('bg-lowpower', { detail: { on: false } }));
      } catch (_) {}
    });

    // 字体就绪
    try { await page.evaluate(() => document.fonts.ready); } catch (_) {}
    await page.waitForTimeout(900);

    const slideCount = await page.evaluate(() => document.querySelectorAll('.slide').length || 1);
    console.log(`scrollsnap-hd: 检测到 ${slideCount} 张幻灯片 @ ${SLIDE_W}×${SLIDE_H} ×${DPR}DPR (${SLIDE_W * DPR}×${SLIDE_H * DPR} px)`);

    const pngPaths = [];
    for (let i = 0; i < slideCount; i++) {
      if (onProgress) onProgress(i + 1, slideCount);

      await page.evaluate((idx) => {
        const slides = document.querySelectorAll('.slide');
        const cur = slides[idx];
        if (!cur) return;
        cur.scrollIntoView({ block: 'start', behavior: 'instant' });
        // 强制展开当前 slide 的入场动画元素
        cur.querySelectorAll('[data-anim]').forEach((el) => {
          el.style.setProperty('opacity', '1', 'important');
          el.style.setProperty('transform', 'none', 'important');
          el.style.setProperty('animation', 'none', 'important');
        });
      }, i);

      // 等 IntersectionObserver 切 light-bg + WebGL 多帧绘制 + transition
      await page.waitForTimeout(STABILIZE_MS);
      await page.evaluate(
        () =>
          new Promise((r) =>
            requestAnimationFrame(() =>
              requestAnimationFrame(() => requestAnimationFrame(r))
            )
          )
      );

      const pngPath = path.join(tmpDir, `slide-${String(i + 1).padStart(3, '0')}.png`);
      await page.screenshot({
        path: pngPath,
        clip: { x: 0, y: 0, width: SLIDE_W, height: SLIDE_H },
        type: 'png',
        omitBackground: false,
      });
      pngPaths.push(pngPath);
      if ((i + 1) % 5 === 0 || i === 0 || i === slideCount - 1) {
        console.log(`  截图 ${i + 1}/${slideCount}`);
      }
    }

    // 合并 PNG → 多页 PDF
    console.log(`scrollsnap-hd: 合并 ${pngPaths.length} 张 PNG → PDF (ImageMagick)`);
    const mergeDir = path.join(tmpDir, 'merge');
    fs.mkdirSync(mergeDir, { recursive: true });
    [...pngPaths].sort().forEach((p) => {
      fs.copyFileSync(p, path.join(mergeDir, path.basename(p)));
    });

    const { spawnSync } = require('child_process');
    const result = spawnSync(
      'magick',
      [path.join(mergeDir, 'slide-*.png'), '-density', '144', absPdf],
      { stdio: 'pipe' }
    );
    if (result.status !== 0) {
      throw new Error(
        `magick merge failed (status=${result.status}): ${result.stderr?.toString() || result.stdout?.toString() || 'unknown'}`
      );
    }
    console.log(`scrollsnap-hd: PDF 已保存: ${absPdf}`);
    return { pdfPath: absPdf, slideCount, tmpDir };
  } finally {
    await browser.close();
  }
}

module.exports = html2pdfScrollsnapHD;

if (require.main === module) {
  const args = process.argv.slice(2);
  if (args.length < 2) {
    console.error('Usage: node html2pdf-scrollsnap-hd.js <input.html> <output.pdf>');
    process.exit(1);
  }
  html2pdfScrollsnapHD(args[0], args[1]).then(
    () => process.exit(0),
    (e) => { console.error(e); process.exit(1); }
  );
}
