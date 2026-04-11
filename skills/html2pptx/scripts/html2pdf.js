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

/**
 * Convert HTML file to PDF
 * @param {string} htmlFile - Path to HTML file
 * @param {string} pdfPath - Output PDF path
 * @param {object} options - Conversion options
 */
async function html2pdf(htmlFile, pdfPath, options = {}) {
  const {
    format = null,
    landscape = null,
    printBackground = true,
    margin = { top: '0', bottom: '0', left: '0', right: '0' },
    scale = 1.0,
  } = options;

  const filePath = path.isAbsolute(htmlFile) ? htmlFile : path.join(process.cwd(), htmlFile);

  const launchOptions = {};
  if (process.platform === 'darwin') {
    launchOptions.channel = 'chrome';
  }

  const browser = await chromium.launch(launchOptions);

  try {
    const page = await browser.newPage();
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

      await page.evaluate(({ pageW, pageH, slideSel }) => {
        const style = document.createElement('style');
        style.textContent = `
          @page {
            size: ${pageW}mm ${pageH}mm;
            margin: 0;
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
        `;
        document.head.appendChild(style);
      }, { pageW: slideWidthMm, pageH: slideHeightMm, slideSel: sel });

      // Wait for injected styles to apply
      await page.waitForTimeout(100);

      await page.pdf({
        path: pdfPath,
        printBackground,
        margin: { top: '0', bottom: '0', left: '0', right: '0' },
        scale,
        preferCSSPageSize: true,
      });
    } else {
      // Single page HTML
      const pdfOptions = {
        path: pdfPath,
        printBackground,
        margin,
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

      await page.pdf(pdfOptions);
    }

    console.log(`PDF 已保存: ${pdfPath}`);
    return pdfPath;
  } finally {
    await browser.close();
  }
}

module.exports = html2pdf;
