/**
 * html2pdf-carousel-hd - 高保真 carousel HTML 转多页 PDF
 *
 * 适用场景：HTML 是水平/垂直 carousel 导航（#deck + transform:translateX），
 * 标准 html2pdf 的 page-break-after 在 print 模式下无法正确分页。
 *
 * 算法：
 *   1. 打开 HTML，固定 viewport 到 1280×720（slide 自然尺寸）
 *   2. deviceScaleFactor=2 获得 2560×1440 像素 = HD
 *   3. 对每个 .slide：调用页内 go(i) 函数（或直接改 transform），等动画完成
 *   4. page.screenshot() 截取整页（仅当前 slide 可见，因为其它 slide 被 transform 推出视口）
 *   5. ImageMagick 把 36 张 PNG 合并为单个多页 PDF（PNG 序列 → 多页 PDF）
 *
 * 优点：保留矢量文字层、可搜索、像素清晰、无需复杂 CSS 重写
 */

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
const os = require('os');

const SLIDE_W = 1280;
const SLIDE_H = 720;
const DPR = 2; // HD: 2560×1440
const TRANSITION_WAIT_MS = 900; // 与 CSS transition .9s 对齐

async function html2pdfCarouselHD(htmlFile, pdfPath, options = {}) {
  const {
    onProgress = null,
    waitForFonts = true,
  } = options;

  const filePath = path.isAbsolute(htmlFile) ? htmlFile : path.join(process.cwd(), htmlFile);
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'slides-hd-'));

  const launchOptions = {};
  if (process.platform === 'darwin') launchOptions.channel = 'chrome';

  const browser = await chromium.launch(launchOptions);
  try {
    const context = await browser.newContext({
      viewport: { width: SLIDE_W, height: SLIDE_H },
      deviceScaleFactor: DPR,
    });
    const page = await context.newPage();
    await page.emulateMedia({ media: 'screen' });
    await page.goto(`file://${filePath}`);
    await page.waitForLoadState('networkidle');

    if (waitForFonts) {
      // 等 web fonts 加载完成，避免文字截图时字体回退
      try {
        await page.evaluate(() => document.fonts.ready);
      } catch (_) {}
    }

    // 探测总幻灯片数
    const slideCount = await page.evaluate(() => {
      const deck = document.getElementById('deck') || document.body;
      const slides = deck.querySelectorAll('.slide');
      return slides.length || 1;
    });

    console.log(`carousel-hd: 检测到 ${slideCount} 张幻灯片 @ ${SLIDE_W}×${SLIDE_H} ×${DPR}DPR (${SLIDE_W * DPR}×${SLIDE_H * DPR} px)`);

    // 注入截图专用 helper：强制把当前页所有 [data-anim] 元素全部显示
    await page.evaluate(() => {
      window.__revealForCapture = function () {
        // 取消所有正在运行的 web animation（Motion One / WAAPI）
        if (typeof document.getAnimations === 'function') {
          document.getAnimations().forEach((a) => {
            try { a.cancel(); } catch (_) {}
          });
        }
        // 当前 slide 内所有 [data-anim] 元素强制显示
        const deck = document.getElementById('deck');
        const cur = deck ? deck.children[idx] : null;
        const targets = cur ? cur.querySelectorAll('[data-anim]') : [];
        targets.forEach((el) => {
          el.style.opacity = '1';
          el.style.transform = 'none';
          el.style.animation = 'none';
        });
      };
    });

    const pngPaths = [];

    for (let i = 0; i < slideCount; i++) {
      if (onProgress) onProgress(i + 1, slideCount);

      // 翻到第 i 页；优先调用页内 go()，否则直接改 transform
      await page.evaluate((idx) => {
        const deck = document.getElementById('deck');
        if (typeof window.go === 'function') {
          window.go(idx);
        } else if (deck) {
          deck.style.transform = `translateX(${-idx * 100}vw)`;
        }
      }, i);

      // 等 transition + Motion One 入场动画完成
      await page.waitForTimeout(TRANSITION_WAIT_MS);

      // 强制展开所有内容（覆盖 pipeline 步骤、cascade 延迟、hero 入场等）
      await page.evaluate((idx) => {
        // 同步 idx 给 helper 用
        window.idx = idx;
        if (typeof window.__revealForCapture === 'function') {
          window.__revealForCapture();
        }
        // 兜底：再扫一次 deck 中当前可见 slide 的全部子元素（防止 [data-anim] 漏标）
        const deck = document.getElementById('deck');
        const cur = deck ? deck.children[idx] : null;
        if (cur) {
          cur.querySelectorAll('[data-anim]').forEach((el) => {
            el.style.opacity = '1';
            el.style.transform = 'none';
          });
        }
      }, i);

      // pipeline 页面：把所有步骤也强制展开（不依赖 click 触发）
      await page.evaluate((idx) => {
        const deck = document.getElementById('deck');
        const cur = deck ? deck.children[idx] : null;
        if (!cur) return;
        const allAnim = cur.querySelectorAll('[data-anim]');
        allAnim.forEach((el) => {
          // 把 inline opacity/transform 锁死，防止 screenshot 时还在过渡中
          el.style.setProperty('opacity', '1', 'important');
          el.style.setProperty('transform', 'none', 'important');
        });
      }, i);

      // 等两帧确保所有改动渲染到位 + WebGL 背景完成最新绘制
      await page.evaluate(
        () =>
          new Promise((r) =>
            requestAnimationFrame(() =>
              requestAnimationFrame(() => requestAnimationFrame(r))
            )
          )
      );

      // 再额外给 100ms 让 background-image / 渐变稳定
      await page.waitForTimeout(120);

      const pngPath = path.join(tmpDir, `slide-${String(i + 1).padStart(3, '0')}.png`);
      await page.screenshot({
        path: pngPath,
        clip: { x: 0, y: 0, width: SLIDE_W, height: SLIDE_H },
        omitBackground: false,
        type: 'png',
      });
      pngPaths.push(pngPath);
    }

    // 合并为多页 PDF：sharp 0.32 不支持多页 PDF 输出，
    // ImageMagick (magick) 直接吃 PNG 序列产出多页 PDF，最稳。
    console.log(`carousel-hd: 合并 ${pngPaths.length} 张 PNG → PDF (ImageMagick)`);
    const { spawnSync } = require('child_process');

    // 把 PNG 拷到一个稳定目录（避免 magick glob 在被清理的 tmp 上失败）
    const mergeDir = path.join(tmpDir, 'merge');
    fs.mkdirSync(mergeDir, { recursive: true });
    const sortedPngs = [...pngPaths].sort();
    for (const p of sortedPngs) {
      fs.copyFileSync(p, path.join(mergeDir, path.basename(p)));
    }

    // ImageMagick：按文件名字典序合并 PNG → 多页 PDF
    // -density 144 对应 2× DPR（144 DPI 是合理 HD 印刷分辨率）
    const result = spawnSync(
      'magick',
      [path.join(mergeDir, 'slide-*.png'), '-density', '144', pdfPath],
      { stdio: 'pipe' }
    );
    if (result.status !== 0) {
      throw new Error(
        `magick merge failed (status=${result.status}): ${result.stderr?.toString() || result.stdout?.toString() || 'unknown'}`
      );
    }

    console.log(`carousel-hd: PDF 已保存: ${pdfPath}`);
    return { pdfPath, slideCount, tmpDir };
  } finally {
    await browser.close();
    // 不删 tmpDir，留作调试
  }
}

module.exports = html2pdfCarouselHD;

// CLI 入口
if (require.main === module) {
  const args = process.argv.slice(2);
  if (args.length < 2) {
    console.error('Usage: node html2pdf-carousel-hd.js <input.html> <output.pdf>');
    process.exit(1);
  }
  html2pdfCarouselHD(args[0], args[1]).then(
    () => process.exit(0),
    (e) => {
      console.error(e);
      process.exit(1);
    }
  );
}
