#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

let chromium;
try {
  ({ chromium } = require('playwright'));
} catch (err) {
  const message = err && err.message ? err.message : String(err);
  console.error('❌ 缺少依赖: playwright');
  console.error(`   原因: ${message}`);
  console.error('   请先运行: npm install');
  console.error('   如浏览器未安装，再运行: npx playwright install chromium');
  process.exit(1);
}

function printHelp() {
  console.log(`用法:
  node validate-slides.js <html-file> [options]

选项:
  --strict                 存在 error 时退出非零
  --selector <css>          指定 slide 容器选择器，默认自动检测 .slide 与 section
  --viewport <宽x高>        固定视口，默认 1000x562.5
  --json                   输出 JSON
  -h, --help               显示帮助

示例:
  node validate-slides.js ../example.html --strict
  node validate-slides.js ../example.html --viewport 1000x750 --strict`);
}

function parseArgs(argv) {
  const options = {
    strict: false,
    selector: null,
    viewport: { width: 1000, height: 562.5 },
    json: false,
  };
  const positional = [];

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--strict') {
      options.strict = true;
    } else if (arg === '--json') {
      options.json = true;
    } else if (arg === '--selector') {
      const value = argv[i + 1];
      if (!value) throw new Error('--selector 需要一个 CSS 选择器');
      options.selector = value;
      i += 1;
    } else if (arg === '--viewport') {
      const value = argv[i + 1];
      if (!value) throw new Error('--viewport 需要形如 1000x562.5 的值');
      const match = value.match(/^(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)$/i);
      if (!match) throw new Error('--viewport 格式应为 宽x高，例如 1000x562.5');
      options.viewport = { width: Number(match[1]), height: Number(match[2]) };
      i += 1;
    } else if (arg === '-h' || arg === '--help') {
      options.help = true;
    } else if (arg.startsWith('-')) {
      throw new Error(`未知参数: ${arg}`);
    } else {
      positional.push(arg);
    }
  }

  return { file: positional[0], options };
}

function summarize(result) {
  const errors = result.issues.filter(issue => issue.severity === 'error');
  const warnings = result.issues.filter(issue => issue.severity === 'warning');
  const infos = result.issues.filter(issue => issue.severity === 'info');
  return { errors, warnings, infos };
}

function printReport(result, options) {
  if (options.json) {
    console.log(JSON.stringify(result, null, 2));
    return;
  }

  const { errors, warnings, infos } = summarize(result);
  console.log(`\nslides 预检结果: ${result.file}`);
  console.log(`- 视口: ${result.viewport.width}×${result.viewport.height}`);
  console.log(`- slide 数量: ${result.slideCount}`);
  console.log(`- errors: ${errors.length}, warnings: ${warnings.length}, infos: ${infos.length}`);

  for (const issue of result.issues) {
    const label = issue.severity === 'error' ? 'ERROR' : issue.severity === 'warning' ? 'WARN' : 'INFO';
    const scope = issue.slide ? ` [${issue.slide}]` : '';
    console.log(`  [${label}]${scope} ${issue.message}`);
  }

  if (errors.length === 0) {
    console.log('\n✅ 未发现阻塞转换的错误。');
  } else if (options.strict) {
    console.log('\n❌ strict 模式：存在错误，已判定为失败。');
  } else {
    console.log('\n⚠️ 存在错误；当前为宽松模式，修复后再转换，或使用 --strict 阻断输出。');
  }
}

async function validateHtml(htmlFile, options) {
  let browser = null;
  try {
    browser = await chromium.launch({ channel: 'chromium', headless: true });
  } catch (err) {
    const message = err && err.message ? err.message : String(err);
    console.error('❌ Playwright Chromium 不可用');
    console.error(`   原因: ${message}`);
    console.error('   请运行: npx playwright install chromium');
    process.exit(1);
  }

  try {
    const page = await browser.newPage({
      viewport: {
        width: Math.round(options.viewport.width),
        height: Math.round(options.viewport.height),
      },
      deviceScaleFactor: 1,
    });

    const url = pathToFileURL(htmlFile).href;
    await page.goto(url, { waitUntil: 'load' });
    await page.waitForTimeout(120);

    return await page.evaluate(({ selector, viewport, file }) => {
      const issues = [];
      const textTags = new Set(['P', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'LI', 'SPAN', 'A', 'STRONG', 'EM', 'SMALL', 'LABEL', 'BLOCKQUOTE']);

      function add(severity, message, slide) {
        issues.push({ severity, message, slide: slide || null });
      }

      function uniqueElements(elements) {
        return Array.from(new Set(elements));
      }

      function getSlideCandidates() {
        if (selector) return Array.from(document.querySelectorAll(selector));
        return uniqueElements([
          ...Array.from(document.querySelectorAll('.slide')),
          ...Array.from(document.querySelectorAll('section')),
        ]);
      }

      function compactText(text) {
        const normalized = String(text || '').replace(/\s+/g, ' ').trim();
        return normalized.length > 42 ? `${normalized.slice(0, 42)}…` : normalized;
      }

      function elementName(el) {
        const id = el.id ? `#${el.id}` : '';
        const className = typeof el.className === 'string' && el.className.trim()
          ? `.${el.className.trim().split(/\s+/).slice(0, 2).join('.')}`
          : '';
        const text = compactText(el.textContent || '');
        return `${el.tagName.toLowerCase()}${id}${className}${text ? `「${text}」` : ''}`;
      }

      function isVisible(el) {
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== 'none'
          && style.visibility !== 'hidden'
          && Number(style.opacity) !== 0
          && rect.width > 0
          && rect.height > 0;
      }

      function colorVisible(color) {
        if (!color || color === 'transparent') return false;
        const normalized = color.replace(/\s+/g, '').toLowerCase();
        if (normalized === 'rgba(0,0,0,0)') return false;
        const rgba = normalized.match(/^rgba\((\d+),(\d+),(\d+),([\d.]+)\)$/);
        if (rgba && Number(rgba[4]) === 0) return false;
        return true;
      }

      function hasBorder(style) {
        const widths = [style.borderTopWidth, style.borderRightWidth, style.borderBottomWidth, style.borderLeftWidth];
        const styles = [style.borderTopStyle, style.borderRightStyle, style.borderBottomStyle, style.borderLeftStyle];
        return widths.some((width, index) => parseFloat(width) > 0 && styles[index] !== 'none');
      }

      function backgroundUrls(backgroundImage) {
        if (!backgroundImage || backgroundImage === 'none') return [];
        const matches = Array.from(backgroundImage.matchAll(/url\(["']?([^"')]+)["']?\)/g));
        return matches.map(match => match[1]);
      }

      const slides = getSlideCandidates();
      if (slides.length === 0) {
        add('error', selector
          ? `未找到指定 slide 容器: ${selector}`
          : '未找到 slide 容器；请使用 .slide 或 section 包裹每一页');
      }

      if (document.body.scrollWidth > Math.round(viewport.width) + 2) {
        add('error', `body 横向溢出：scrollWidth=${document.body.scrollWidth}px，视口=${viewport.width}px`);
      }

      slides.forEach((slide, index) => {
        const slideName = `第 ${index + 1} 页`;
        const rect = slide.getBoundingClientRect();
        const widthDelta = Math.abs(rect.width - viewport.width);
        const heightDelta = Math.abs(rect.height - viewport.height);

        if (rect.width <= 0 || rect.height <= 0) {
          add('error', `${elementName(slide)} 尺寸为 0，无法转换`, slideName);
        } else if (widthDelta > 3 || heightDelta > 3) {
          add('error', `${elementName(slide)} 尺寸 ${rect.width.toFixed(1)}×${rect.height.toFixed(1)}px 与视口 ${viewport.width}×${viewport.height}px 不一致`, slideName);
        }

        if (slide.scrollWidth > Math.ceil(rect.width) + 2 || slide.scrollHeight > Math.ceil(rect.height) + 2) {
          add('error', `${elementName(slide)} 内容溢出：scroll=${slide.scrollWidth}×${slide.scrollHeight}px，容器=${rect.width.toFixed(1)}×${rect.height.toFixed(1)}px`, slideName);
        }

        const all = Array.from(slide.querySelectorAll('*'));
        for (const el of all) {
          if (!isVisible(el)) continue;

          const style = window.getComputedStyle(el);
          const name = elementName(el);
          const bgImage = style.backgroundImage || '';
          const boxShadow = style.boxShadow || '';

          if (/gradient\(/i.test(bgImage)) {
            add('warning', `${name} 使用 CSS 渐变；PPTX 需改为纯色或本地图片，PDF 可能光栅化`, slideName);
          }

          if (/\binset\b/i.test(boxShadow)) {
            add('error', `${name} 使用 inset 阴影，可能损坏 PPTX 文件`, slideName);
          }

          for (const url of backgroundUrls(bgImage)) {
            if (/^https?:\/\//i.test(url)) {
              add('error', `${name} 使用远程背景图片：${url}`, slideName);
            } else if (/^data:/i.test(url)) {
              add('error', `${name} 使用 base64 背景图片，PPTX 不稳定`, slideName);
            }
          }

          if (el.tagName === 'DIV') {
            const directText = Array.from(el.childNodes)
              .filter(node => node.nodeType === Node.TEXT_NODE)
              .map(node => node.textContent)
              .join(' ')
              .replace(/\s+/g, ' ')
              .trim();
            if (directText) {
              add('error', `${name} 含裸 div 文本“${compactText(directText)}”，请改用 p/span/h* 包裹`, slideName);
            }
          }

          if (textTags.has(el.tagName)) {
            if (colorVisible(style.backgroundColor) || hasBorder(style)) {
              add('error', `${name} 是文字元素但直接带背景或边框；请把背景/边框放到父级容器`, slideName);
            }
            if (el.scrollWidth > el.clientWidth + 2 || el.scrollHeight > el.clientHeight + 2) {
              add('warning', `${name} 文本内容可能被裁切：scroll=${el.scrollWidth}×${el.scrollHeight}px，client=${el.clientWidth}×${el.clientHeight}px`, slideName);
            }
          }

          const childRect = el.getBoundingClientRect();
          if (childRect.right > rect.right + 2 || childRect.left < rect.left - 2 || childRect.bottom > rect.bottom + 2 || childRect.top < rect.top - 2) {
            add('error', `${name} 超出 slide 边界`, slideName);
          }
        }

        const images = Array.from(slide.querySelectorAll('img'));
        for (const img of images) {
          const rawSrc = img.getAttribute('src') || '';
          const resolvedSrc = img.currentSrc || rawSrc;
          const name = elementName(img);
          if (/^https?:\/\//i.test(rawSrc) || /^https?:\/\//i.test(resolvedSrc)) {
            add('error', `${name} 使用远程图片：${rawSrc || resolvedSrc}`, slideName);
          } else if (/^data:/i.test(rawSrc) || /^data:/i.test(resolvedSrc)) {
            add('error', `${name} 使用 base64 图片，PPTX 不稳定`, slideName);
          } else if (!img.complete || img.naturalWidth === 0 || img.naturalHeight === 0) {
            add('error', `${name} 图片加载失败，请检查本地路径：${rawSrc || resolvedSrc}`, slideName);
          }
        }
      });

      if (slides.length > 0) {
        add('info', `检测到 ${slides.length} 个 slide 容器`);
      }

      return {
        file,
        viewport,
        slideCount: slides.length,
        issues,
      };
    }, { selector: options.selector, viewport: options.viewport, file: htmlFile });
  } finally {
    try {
      await browser.close();
    } catch (err) {
      const message = err && err.message ? err.message : String(err);
      console.error(`⚠️ 关闭浏览器失败: ${message}`);
    }
  }
}

async function main() {
  const { file, options } = parseArgs(process.argv.slice(2));
  if (options.help) {
    printHelp();
    return;
  }
  if (!file) {
    printHelp();
    process.exit(1);
  }

  const htmlFile = path.resolve(file);
  if (!fs.existsSync(htmlFile)) {
    console.error(`❌ 文件不存在: ${htmlFile}`);
    process.exit(1);
  }
  if (!fs.statSync(htmlFile).isFile()) {
    console.error(`❌ 不是文件: ${htmlFile}`);
    process.exit(1);
  }

  const result = await validateHtml(htmlFile, options);
  printReport(result, options);

  const { errors } = summarize(result);
  if (options.strict && errors.length > 0) {
    process.exit(2);
  }
}

main().catch(err => {
  const message = err && err.message ? err.message : String(err);
  console.error(`❌ 验证失败: ${message}`);
  process.exit(1);
});
