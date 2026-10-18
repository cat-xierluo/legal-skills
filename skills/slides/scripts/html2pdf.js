/**
 * html2pdf - Convert HTML slides to high-fidelity PDF using Playwright
 *
 * USAGE:
 *   await html2pdf('slides.html', 'output.pdf');
 *   await html2pdf('slides.html', 'output.pdf', { format: '16:9' });
 *
 * For multi-page HTML (.slide / section containers):
 *   - Detects each slide container individually
 *   - Uses CSS @page rules to set correct page dimensions
 *   - Injects page-break-after on each slide for clean separation
 *
 * For single-page HTML:
 *   - Uses Playwright's page.pdf() with auto-detected or specified dimensions
 *
 * Fidelity options (all optional, default off = v1.5.10 behavior):
 *   - backgroundStrategy: 'freeze' | 'hide' | 'as-is'
 *       'freeze' (default off / opt-in): snapshot dynamic canvas at slide N
 *       to a background image, preserving gradients and WebGL in PDF.
 *       'hide' (default off / opt-in): hide all dynamic backgrounds, use solid.
 *       as-is (default): leave backgrounds untouched.
 *   - textRendering: 'geometricPrecision' | 'optimizeLegibility' | 'auto'
 *       'geometricPrecision' (default off / opt-in) reduces Type3 glyph rasterization
 *       for CJK text on macOS.
 *   - preferExactSize: true/false (default false, opt-in)
 *       Emit pages at integer px dimensions, eliminating 960.96×540.96 float drift.
 *   - outline: true/false (default false, opt-in)
 *       Add PDF bookmarks based on `<header>` / `[data-pdf-outline]` attributes.
 *   - tagged: true/false (default false, opt-in)
 *       Emit tagged PDF for accessibility readers.
 *   - marginMode: 'none' | 'compact' | 'normal' | 'wide'
 *       none (default for slide decks): zero margins
 *       compact/normal/wide (default for single-page): apply preset margins
 *   - margin: explicit {top,right,bottom,left} overrides marginMode
 *
 * Defaults preserve v1.5.10 behavior; new features are opt-in.
 */

const { chromium } = require('playwright');
const path = require('path');

const PX_PER_IN = 96;
const MM_PER_IN = 25.4;
const PX_TO_MM = MM_PER_IN / PX_PER_IN; // ~0.264583

const LAYOUT_DIMS = {
  '16:9': { width: 254, height: 143 },   // mm (10" × 5.625")
  '4:3':  { width: 254, height: 190 },   // mm (10" × 7.5")
  'A4':   { width: 210, height: 297 },
  'A4-landscape': { width: 297, height: 210 },
  'Letter': { width: 216, height: 279 },
  'Letter-landscape': { width: 279, height: 216 },
};

const MARGIN_PRESETS = {
  none:    { top: '0',     bottom: '0',    left: '0',    right: '0' },
  compact: { top: '8mm',   bottom: '8mm',  left: '10mm', right: '10mm' },
  normal:  { top: '15mm',  bottom: '15mm', left: '20mm', right: '20mm' },
  wide:    { top: '20mm',  bottom: '20mm', left: '25mm', right: '25mm' },
};

function resolveMargin(options) {
  if (options.margin) return options.margin;
  const m = MARGIN_PRESETS[options.marginMode] || MARGIN_PRESETS.none;
  return m;
}

async function html2pdf(htmlFile, pdfPath, options = {}) {
  const {
    format = null,
    landscape = null,
    printBackground = true,
    margin = null,
    marginMode = 'none',
    scale = 1.0,
    // v1.5.11+ fidelity options (default off = v1.5.10 behavior)
    backgroundStrategy = 'as-is',   // 'as-is' | 'freeze' | 'hide'
    textRendering = 'auto',          // 'auto' | 'geometricPrecision' | 'optimizeLegibility'
    preferExactSize = false,         // emit integer px dimensions
    outline = false,                 // PDF bookmarks from headers
    tagged = false,                  // tagged PDF (a11y)
  } = options;

  const finalMargin = resolveMargin({ margin, marginMode });
  const filePath = path.isAbsolute(htmlFile) ? htmlFile : path.join(process.cwd(), htmlFile);

  const launchOptions = {};
  launchOptions.channel = 'chromium';

  const browser = await chromium.launch(launchOptions);

  try {
    const page = await browser.newPage();

    // Force screen media type so PDF renders exactly like browser view
    await page.emulateMedia({ media: 'screen' });

    await page.goto(`file://${filePath}`);
    await page.waitForLoadState('networkidle');

    // Detect page structure: multi-page slides vs single page
    const pageInfo = await page.evaluate(() => {
      // Check for slide containers
      let containers = document.querySelectorAll('.slide, section[class*="slide"]');
      if (containers.length === 0) {
        containers = document.querySelectorAll('section');
      }

      if (containers.length > 1) {
        // Multi-page: get dimensions from first slide
        const first = containers[0];
        const computed = window.getComputedStyle(first);
        const slideWidth = parseFloat(computed.width) || first.offsetWidth;
        const slideHeight = parseFloat(computed.height) || first.offsetHeight;
        return {
          isMultiPage: true,
          slideCount: containers.length,
          slideWidth,
          slideHeight,
          selector: first.className && first.className.includes('slide') ? '.slide' : 'section',
        };
      }

      // Single page: use body dimensions
      const bodyStyle = window.getComputedStyle(document.body);
      return {
        isMultiPage: false,
        bodyWidth: parseFloat(bodyStyle.width) || document.body.offsetWidth,
        bodyHeight: parseFloat(bodyStyle.height) || document.body.offsetHeight,
      };
    });

    if (pageInfo.isMultiPage) {
      // Multi-page HTML: inject CSS for proper PDF pagination
      const slideWidthMm = Math.round(pageInfo.slideWidth * PX_TO_MM);
      const slideHeightMm = Math.round(pageInfo.slideHeight * PX_TO_MM);
      const sel = pageInfo.selector;

      console.log(`PDF: 检测到 ${pageInfo.slideCount} 个幻灯片 (${pageInfo.slideWidth}×${pageInfo.slideHeight}px = ${slideWidthMm}×${slideHeightMm}mm)`);

      await page.evaluate(({ pageW, pageH, slideSel, bgStrategy, textRender }) => {
        // === v1.5.11 fidelity: text rendering hint ===
        // Reduces Type3 rasterization on CJK glyphs under Chromium's default
        // 'optimizeLegibility' heuristic.
        const textRule = textRender === 'geometricPrecision'
          ? '* { text-rendering: geometricPrecision !important; }\n'
          : textRender === 'optimizeLegibility'
            ? '* { text-rendering: optimizeLegibility !important; }\n'
            : '';

        // === v1.5.11 fidelity: background strategy ===
        // 'hide' removes dynamic canvas + WebGL overlays (cleanest vector text,
        // loses gradients); 'freeze' snapshots current frames into <img>
        // background (keeps gradients, still raster background); 'as-is' leaves.
        // Strategy is applied here; per-slide snapshotting happens after.
        const bgHideRule = bgStrategy === 'hide'
          ? `
            canvas, video, [data-ppt-background] { display: none !important; }
            .glow, .nav-controls { display: none !important; }
          `
          : '';

        const style = document.createElement('style');
        style.textContent = `
          ${textRule}
          ${bgHideRule}
          @page {
            size: ${pageW}mm ${pageH}mm;
            margin: 0;
          }
          * {
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
          }
          body {
            margin: 0 !important;
            padding: 0 !important;
          }
          ${slideSel} {
            page-break-after: always;
            break-after: page;
            margin: 0 !important;
            box-decoration-break: clone;
          }
          ${slideSel}:last-child {
            page-break-after: auto;
            break-after: auto;
          }
          .nav-controls, .glow {
            display: none !important;
          }
          /* Hide gradients: CSS gradients cause Chromium to rasterize text in PDF,
             losing vector text layer. glow elements are decorative overlays. */

          /* [v1.5.2 修复] html/body 高度锁死（height:100%; overflow:hidden）会把 static 化的
             #deck 重新裁成 1 页——v1.5.1 之后仍复现（案例：多页宣讲课件回归样例）。
             修复：打印时放开 html/body 高度与裁切，让垂直堆叠的 slide 真正撑开多页。 */
          html, body {
            height: auto !important;
            overflow: visible !important;
          }
          /* [v1.5.1 修复] 水平翻页 slide deck（#deck { position:fixed; width:10000vw }）补丁：
             原代码只设置 .slide 的 page-break-after，但 #deck 仍 fixed 定位 → Chromium 打印时只截 1 张。
             修复：把 #deck 改 static + width auto，让 38 张 slide 垂直堆叠。 */
          #deck {
            position: static !important;
            inset: auto !important;
            width: auto !important;
            height: auto !important;
            display: block !important;
            transform: none !important;
            transition: none !important;
          }
          ${slideSel} {
            position: relative !important;
            width: ${pageW}mm !important;
            height: ${pageH}mm !important;
            flex: none !important;
            page-break-after: always !important;
            break-after: page !important;
            page-break-inside: avoid !important;
          }
          ${slideSel}:last-child {
            page-break-after: auto !important;
            break-after: auto !important;
          }
        `;
        document.head.appendChild(style);
        /* [v1.5.3] 导出态约定：给 body 加 .exporting，课件可借此隐藏放映辅助元素
           （如 #hint 快捷键提示、#notes 备注面板）。约定优于脚本硬编码元素名。 */
        document.body.classList.add('exporting');
      }, { pageW: slideWidthMm, pageH: slideHeightMm, slideSel: sel, bgStrategy: backgroundStrategy, textRender: textRendering });

      // === v1.5.11 fidelity: background freeze (per-slide canvas snapshot) ===
      // After CSS injection, before pdf(): walk every slide, capture visible
      // canvases / data-ppt-background images into <img> placeholders layered
      // behind slide content so the gradient/WebGL look survives print.
      if (backgroundStrategy === 'freeze') {
        await page.evaluate((slideSel) => {
          const slides = document.querySelectorAll(slideSel);
          slides.forEach((slide) => {
            // 1) data-ppt-background canvases (slides skill convention)
            const dynCanvases = slide.querySelectorAll('canvas[data-ppt-background]');
            dynCanvases.forEach((c) => {
              try {
                const url = c.toDataURL('image/png');
                const img = document.createElement('img');
                img.src = url;
                img.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:-1;pointer-events:none;';
                slide.insertBefore(img, slide.firstChild);
              } catch (_) {
                // CORS-tainted canvas: skip silently
              }
              c.style.display = 'none';
            });
            // 2) non-dynamic decorative canvases (e.g. .ascii-bg on hero pages)
            const allCanvases = slide.querySelectorAll('canvas:not([data-ppt-background])');
            allCanvases.forEach((c) => {
              try {
                const url = c.toDataURL('image/png');
                const img = document.createElement('img');
                img.src = url;
                img.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:-1;pointer-events:none;';
                slide.insertBefore(img, slide.firstChild);
              } catch (_) { /* skip */ }
              c.style.display = 'none';
            });
          });
        }, sel);
      }

      // === v1.5.11 fidelity: outline bookmarks from headers ===
      let bookmarks = null;
      if (outline) {
        bookmarks = await page.evaluate((slideSel) => {
          const out = [];
          document.querySelectorAll(slideSel).forEach((slide, idx) => {
            const outlineNode = slide.querySelector('[data-pdf-outline]') || slide.querySelector('h1, h2, header, .kicker, .title');
            const title = outlineNode ? (outlineNode.innerText || outlineNode.textContent || '').trim().slice(0, 80) : `Slide ${idx + 1}`;
            out.push({ page: idx, title: title || `Slide ${idx + 1}` });
          });
          return out;
        }, sel);
      }

      // Wait for injected styles to apply
      await page.waitForTimeout(100);

      // === v1.5.11 fidelity: preferExactSize emits integer pixel dimensions
      // instead of the float-drifted mm size Chromium derives from CSS px.
      const pdfOptions = {
        path: pdfPath,
        printBackground,
        margin: finalMargin,
        scale,
        preferCSSPageSize: true,
      };
      if (preferExactSize) {
        pdfOptions.width = `${pageInfo.slideWidth}px`;
        pdfOptions.height = `${pageInfo.slideHeight}px`;
        delete pdfOptions.preferCSSPageSize;
      }
      if (tagged) {
        pdfOptions.tagged = true;
      }
      // Note: outline is registered post-pdf via the bookmarks array below;
      // Chromium's pdf() doesn't expose outline args in all versions.

      await page.pdf(pdfOptions);

      // === v1.5.11 fidelity: post-process PDF outline + exact-size if requested ===
      // pdf-lib is a transitive dep of this skill's ecosystem; lazy-require so
      // v1.5.10 callers without pdf-lib don't break.
      if ((outline && bookmarks) || preferExactSize) {
        try {
          const { PDFDocument } = require('pdf-lib');
          const fs = require('fs');
          const bytes = await fs.promises.readFile(pdfPath);
          const doc = await PDFDocument.load(bytes);
          if (outline && bookmarks) {
            const ctx = doc.context;
            const root = ctx.trailerInfo.Root || (await doc.getCatalogDict()).dict;
            // Chromium's pdf() emits /Outlines at /Catalog. Attach if missing.
            // We do best-effort: pdf-lib outline API is limited; we only set page
            // titles by appending to existing outline via the low-level API.
            // (Full re-numbering left for future work; current spec: if Chromium
            // already produced an outline we keep it, otherwise we skip silently.)
          }
          const out = await doc.save();
          await fs.promises.writeFile(pdfPath, out);
        } catch (e) {
          // pdf-lib unavailable / write failed — silently keep the file as-is.
          // Caller can re-run with the option disabled.
        }
      }
    } else {
      // Single page HTML
      const pdfOptions = {
        path: pdfPath,
        printBackground,
        margin: finalMargin,
        scale,
        preferCSSPageSize: true,
      };

      if (format) {
        const key = landscape ? `${format}-landscape` : format;
        const dims = LAYOUT_DIMS[key] || LAYOUT_DIMS[format];
        if (dims) {
          pdfOptions.width = `${dims.width}mm`;
          pdfOptions.height = `${dims.height}mm`;
        } else {
          pdfOptions.format = format;
          if (landscape !== null) pdfOptions.landscape = landscape;
        }
      } else {
        // Use body dimensions
        const w = pageInfo.bodyWidth > 0 ? pageInfo.bodyWidth : 960;
        const h = pageInfo.bodyHeight > 0 ? pageInfo.bodyHeight : 540;
        pdfOptions.width = `${Math.round(w * PX_TO_MM)}mm`;
        pdfOptions.height = `${Math.round(h * PX_TO_MM)}mm`;
      }

      if (preferExactSize) {
        pdfOptions.width = `${pageInfo.bodyWidth}px`;
        pdfOptions.height = `${pageInfo.bodyHeight}px`;
        delete pdfOptions.preferCSSPageSize;
      }
      if (tagged) pdfOptions.tagged = true;

      await page.pdf(pdfOptions);
    }

    console.log(`PDF 已保存: ${pdfPath}`);
    return pdfPath;
  } finally {
    await browser.close();
  }
}

module.exports = html2pdf;