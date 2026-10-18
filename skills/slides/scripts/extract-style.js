#!/usr/bin/env node
/**
 * extract-style.js - 从 HTML 幻灯片提取结构化风格定义
 *
 * USAGE:
 *   node extract-style.js slides.html -o style.json
 *   node extract-style.js slides.html --save 商务法律风
 *   node extract-style.js --list
 *
 * OUTPUT (JSON):
 *   {
 *     name, source, slideDimensions,
 *     colors: { backgrounds, textColors, accents, palette },
 *     typography: { fontFamilies, titleSizes, bodySizes, lineHeight },
 *     layout: { positioning, marginPattern, contentWidth },
 *     components: [{ type, style }],
 *     cssVariables: { ... }
 *   }
 */

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const PX_PER_IN = 96;

// ── Color utilities ──────────────────────────────────────────────────

function rgbToHex(rgbStr) {
  if (!rgbStr || rgbStr === 'rgba(0, 0, 0, 0)' || rgbStr === 'transparent') return null;
  const match = rgbStr.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
  if (!match) return null;
  return '#' + match.slice(1).map(n => parseInt(n).toString(16).padStart(2, '0')).join('').toUpperCase();
}

function hexDistance(a, b) {
  const parse = (hex) => {
    const h = hex.replace('#', '');
    return [parseInt(h.substring(0, 2), 16), parseInt(h.substring(2, 4), 16), parseInt(h.substring(4, 6), 16)];
  };
  const [r1, g1, b1] = parse(a);
  const [r2, g2, b2] = parse(b);
  return Math.sqrt((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2);
}

function clusterColors(colors, threshold = 50) {
  // Simple clustering: group similar colors
  const clusters = [];
  for (const color of colors) {
    let found = false;
    for (const cluster of clusters) {
      if (hexDistance(color, cluster.representative) < threshold) {
        cluster.colors.push(color);
        found = true;
        break;
      }
    }
    if (!found) {
      clusters.push({ representative: color, colors: [color] });
    }
  }
  // Sort clusters by frequency (most common first)
  clusters.sort((a, b) => b.colors.length - a.colors.length);
  return clusters.map(c => c.representative);
}

function isNeutralColor(hex) {
  if (!hex) return false;
  const h = hex.replace('#', '');
  const r = parseInt(h.substring(0, 2), 16);
  const g = parseInt(h.substring(2, 4), 16);
  const b = parseInt(h.substring(4, 6), 16);
  const maxDiff = Math.max(Math.abs(r - g), Math.abs(g - b), Math.abs(r - b));
  return maxDiff < 30; // Low saturation = neutral
}

function isDarkColor(hex) {
  if (!hex) return false;
  const h = hex.replace('#', '');
  const r = parseInt(h.substring(0, 2), 16);
  const g = parseInt(h.substring(2, 4), 16);
  const b = parseInt(h.substring(4, 6), 16);
  return (r * 0.299 + g * 0.587 + b * 0.114) < 128;
}

// ── Core extraction ──────────────────────────────────────────────────

async function extractStyle(htmlFile, options = {}) {
  const filePath = path.isAbsolute(htmlFile) ? htmlFile : path.join(process.cwd(), htmlFile);

  const launchOptions = {};
  launchOptions.channel = 'chromium';

  const browser = await chromium.launch(launchOptions);

  try {
    const page = await browser.newPage();
    await page.goto(`file://${filePath}`);
    await page.waitForLoadState('networkidle');

    // Detect slide structure
    const slideInfo = await page.evaluate(() => {
      let containers = document.querySelectorAll('.slide, section[class*="slide"]');
      if (containers.length === 0) containers = document.querySelectorAll('section');
      if (containers.length === 0) return { multiPage: false, count: 1 };

      const first = containers[0];
      const computed = window.getComputedStyle(first);
      return {
        multiPage: true,
        count: containers.length,
        slideWidth: parseFloat(computed.width) || first.offsetWidth,
        slideHeight: parseFloat(computed.height) || first.offsetHeight
      };
    });

    // Set viewport to match first slide
    const targetWidth = slideInfo.slideWidth || 960;
    const targetHeight = slideInfo.slideHeight || 540;
    await page.setViewportSize({ width: Math.round(targetWidth), height: Math.round(targetHeight) });

    // Extract style data from page
    const styleData = await page.evaluate(() => {
      const rgbToHex = (rgbStr) => {
        if (!rgbStr || rgbStr === 'rgba(0, 0, 0, 0)' || rgbStr === 'transparent') return null;
        const match = rgbStr.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
        if (!match) return null;
        return '#' + match.slice(1).map(n => parseInt(n).toString(16).padStart(2, '0')).join('').toUpperCase();
      };

      const isNeutral = (hex) => {
        if (!hex) return false;
        const h = hex.replace('#', '');
        const r = parseInt(h.substring(0, 2), 16);
        const g = parseInt(h.substring(2, 4), 16);
        const b = parseInt(h.substring(4, 6), 16);
        return Math.max(Math.abs(r - g), Math.abs(g - b), Math.abs(r - b)) < 30;
      };

      const isDark = (hex) => {
        if (!hex) return false;
        const h = hex.replace('#', '');
        const r = parseInt(h.substring(0, 2), 16);
        const g = parseInt(h.substring(2, 4), 16);
        const b = parseInt(h.substring(4, 6), 16);
        return (r * 0.299 + g * 0.587 + b * 0.114) < 128;
      };

      // ── Collect CSS custom properties from :root ──
      const cssVars = {};
      for (const sheet of document.styleSheets) {
        try {
          for (const rule of sheet.cssRules) {
            if (rule.selectorText === ':root' || rule.selectorText === 'html') {
              for (const prop of rule.style) {
                if (prop.startsWith('--')) {
                  cssVars[prop] = rule.style.getPropertyValue(prop).trim();
                }
              }
            }
          }
        } catch (e) {
          // Cross-origin stylesheet, skip
        }
      }

      // ── Collect all colors and fonts from elements ──
      const bgColors = new Set();
      const textColors = new Set();
      const fontFamilies = new Set();
      const fontSizes = [];
      const lineHeights = new Set();
      const borderColors = new Set();
      const positionTypes = { absolute: 0, relative: 0, static: 0, other: 0 };
      const components = [];

      // Collect slide backgrounds
      const slideContainers = document.querySelectorAll('.slide, section[class*="slide"], section');
      for (const container of slideContainers) {
        const computed = window.getComputedStyle(container);
        const bg = rgbToHex(computed.backgroundColor);
        if (bg) bgColors.add(bg);
      }

      // Collect body background
      const bodyComputed = window.getComputedStyle(document.body);
      const bodyBg = rgbToHex(bodyComputed.backgroundColor);
      if (bodyBg) bgColors.add(bodyBg);

      // ── Walk all visible elements ──
      const allElements = document.querySelectorAll('*');
      let marginMinX = Infinity, marginMinY = Infinity;
      let contentMaxX = 0;

      for (const el of allElements) {
        const computed = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;

        // Skip tiny decorative elements (< 3px in both dimensions)
        if (rect.width < 3 && rect.height < 3) continue;

        // Position tracking
        if (computed.position === 'absolute' || computed.position === 'fixed') {
          positionTypes.absolute++;
        } else if (computed.position === 'relative') {
          positionTypes.relative++;
        } else if (computed.position === 'static') {
          positionTypes.static++;
        } else {
          positionTypes.other++;
        }

        // Background colors
        const bg = rgbToHex(computed.backgroundColor);
        if (bg) bgColors.add(bg);

        // Border colors
        if (parseFloat(computed.borderTopWidth) > 0 || parseFloat(computed.borderBottomWidth) > 0 ||
            parseFloat(computed.borderLeftWidth) > 0 || parseFloat(computed.borderRightWidth) > 0) {
          const bc = rgbToHex(computed.borderColor || computed.borderTopColor);
          if (bc) borderColors.add(bc);
        }

        // Text elements
        const textTags = ['P', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'SPAN', 'A', 'LI', 'DIV'];
        if (textTags.includes(el.tagName)) {
          const textColor = rgbToHex(computed.color);
          if (textColor) textColors.add(textColor);

          const fontFamily = computed.fontFamily.split(',')[0].replace(/['"]/g, '').trim();
          if (fontFamily) fontFamilies.add(fontFamily);

          const fontSize = parseFloat(computed.fontSize);
          if (fontSize > 0) {
            fontSizes.push({ size: fontSize, tag: el.tagName });
          }

          const lh = parseFloat(computed.lineHeight);
          if (lh > 0 && lh < 200) { // Sanity check
            lineHeights.add(Math.round(lh * 10) / 10);
          }

          // Margin tracking for content elements with text
          const text = el.textContent.trim();
          if (text && text.length > 2) {
            if (rect.left > 0 && rect.left < marginMinX) marginMinX = rect.left;
            if (rect.top > 0 && rect.top < marginMinY) marginMinY = rect.top;
            if (rect.right > contentMaxX) contentMaxX = rect.right;
          }
        }

        // Detect decorative components (div with background/border but no text children)
        if (el.tagName === 'DIV') {
          const hasBg = computed.backgroundColor !== 'rgba(0, 0, 0, 0)' && computed.backgroundColor !== 'transparent';
          const hasBorder = parseFloat(computed.borderTopWidth) > 0 || parseFloat(computed.borderBottomWidth) > 0 ||
                           parseFloat(computed.borderLeftWidth) > 0 || parseFloat(computed.borderRightWidth) > 0;
          const hasRadius = parseFloat(computed.borderRadius) > 0;
          const hasShadow = computed.boxShadow && computed.boxShadow !== 'none';

          // Check if it's a small decorative element or content container
          const isSmall = rect.width < 50 || rect.height < 10;
          const hasTextChildren = el.querySelector('p, h1, h2, h3, h4, h5, h6, ul, ol');
          const isFullSlide = rect.width > 900 && rect.height > 500;

          if ((hasBg || hasBorder || hasRadius) && !isFullSlide && !hasTextChildren) {
            const comp = {
              width: Math.round(rect.width),
              height: Math.round(rect.height),
              hasBackground: hasBg,
              hasBorder,
              borderRadius: hasRadius ? computed.borderRadius : null,
              hasShadow
            };
            if (hasBg) comp.backgroundColor = rgbToHex(computed.backgroundColor);
            if (hasBorder) comp.borderColor = rgbToHex(computed.borderColor || computed.borderTopColor);
            if (hasRadius) comp.borderRadiusValue = computed.borderRadius;

            components.push(comp);
          }
        }
      }

      // ── Classify colors ──
      const allBgColors = [...bgColors];
      const darkBgs = allBgColors.filter(c => isDark(c));
      const lightBgs = allBgColors.filter(c => !isDark(c));
      const neutralTexts = [...textColors].filter(c => isNeutral(c));
      const accentTexts = [...textColors].filter(c => !isNeutral(c));

      // ── Classify font sizes ──
      const titleSizes = [...new Set(
        fontSizes
          .filter(f => ['H1', 'H2'].includes(f.tag) || f.size >= 28)
          .map(f => Math.round(f.size * 10) / 10)
      )].sort((a, b) => b - a).slice(0, 5);

      const bodySizes = [...new Set(
        fontSizes
          .filter(f => !['H1', 'H2'].includes(f.tag) && f.size < 28 && f.size >= 10)
          .map(f => Math.round(f.size * 10) / 10)
      )].sort((a, b) => b - a).slice(0, 3);

      const smallSizes = [...new Set(
        fontSizes
          .filter(f => f.size < 10)
          .map(f => Math.round(f.size * 10) / 10)
      )].sort((a, b) => b - a).slice(0, 3);

      // ── Determine positioning mode ──
      const totalPositioned = positionTypes.absolute + positionTypes.relative + positionTypes.static + positionTypes.other;
      let positioning = 'mixed';
      if (totalPositioned > 0) {
        if (positionTypes.absolute / totalPositioned > 0.4) positioning = 'absolute';
        else if (positionTypes.static / totalPositioned > 0.6) positioning = 'flow';
        else positioning = 'flex-grid';
      }

      // ── Build margin pattern ──
      const marginPattern = [];
      if (marginMinX !== Infinity) marginPattern.push(Math.round(marginMinX));
      if (marginMinY !== Infinity) marginPattern.push(Math.round(marginMinY));

      const contentWidth = contentMaxX > 0 && marginMinX !== Infinity
        ? Math.round(contentMaxX - marginMinX)
        : null;

      // ── Build palette ──
      const palette = [];
      // Add backgrounds
      for (const c of darkBgs.slice(0, 2)) palette.push(c);
      for (const c of lightBgs.slice(0, 2)) palette.push(c);
      // Add accent text colors (non-neutral)
      for (const c of accentTexts.slice(0, 2)) palette.push(c);
      // Add border colors that aren't already in palette
      for (const c of [...borderColors]) {
        if (!palette.includes(c)) palette.push(c);
        if (palette.length >= 8) break;
      }
      // Add neutral text if missing
      for (const c of neutralTexts.slice(0, 1)) {
        if (!palette.includes(c)) palette.push(c);
      }

      return {
        cssVariables: Object.keys(cssVars).length > 0 ? cssVars : null,
        colors: {
          backgrounds: allBgColors.slice(0, 6),
          textColors: [...textColors].slice(0, 6),
          accents: [...accentTexts, ...borderColors].filter((v, i, a) => a.indexOf(v) === i).slice(0, 4),
          palette: [...new Set(palette)]
        },
        typography: {
          fontFamilies: [...fontFamilies].slice(0, 4),
          titleSizes,
          bodySizes,
          smallSizes,
          lineHeight: lineHeights.size > 0 ? [...lineHeights].sort((a, b) => a - b) : null
        },
        layout: {
          positioning,
          marginPattern: marginPattern.length > 0 ? marginPattern : null,
          contentWidth
        },
        components: components.slice(0, 10)
      };
    });

    // Assemble final style object
    const result = {
      name: options.name || path.basename(htmlFile, path.extname(htmlFile)),
      source: path.basename(htmlFile),
      extractedAt: new Date().toISOString().split('T')[0],
      slideDimensions: {
        width: targetWidth,
        height: targetHeight,
        ratio: (targetWidth / targetHeight).toFixed(2)
      },
      ...styleData
    };

    return result;

  } finally {
    await browser.close();
  }
}

// ── Style library management ──────────────────────────────────────────

const { getUserDir } = require('./load-profile');

/** 技能内置风格库（随发布包分发，只读）。 */
function getBuiltinStylesDir() {
  return path.join(__dirname, '..', 'references', 'styles');
}

/** 个人风格目录（技能目录之外，技能升级/重装不覆盖，也不进发布包）。 */
function getUserStylesDir() {
  return path.join(getUserDir(), 'styles');
}

function listStyles() {
  const groups = [
    { dir: getBuiltinStylesDir(), origin: '内置' },
    { dir: getUserStylesDir(), origin: '个人' }
  ];

  const styles = [];
  for (const group of groups) {
    if (!fs.existsSync(group.dir)) continue;
    const files = fs.readdirSync(group.dir).filter(f => f.endsWith('.json'));
    for (const file of files) {
      try {
        const data = JSON.parse(fs.readFileSync(path.join(group.dir, file), 'utf-8'));
        styles.push({
          origin: group.origin,
          dir: group.dir,
          file,
          name: data.name,
          source: data.source,
          palette: data.colors?.palette?.join(', ') || '(无配色)'
        });
      } catch (e) {
        styles.push({ origin: group.origin, dir: group.dir, file, name: '(解析失败)', source: '', palette: '' });
      }
    }
  }

  if (styles.length === 0) {
    console.log('风格库为空');
    return [];
  }

  console.log(`\n可用风格 (${styles.length}):\n`);
  for (const s of styles) {
    console.log(`  ${s.name}  [${s.origin}]`);
    console.log(`    文件: ${path.join(s.dir, s.file)}`);
    console.log(`    来源: ${s.source}`);
    console.log(`    配色: ${s.palette}`);
    console.log();
  }
  console.log(`个人风格保存目录: ${getUserStylesDir()}\n`);

  return styles;
}

/**
 * 保存自提取风格。
 * 默认写入个人风格目录（技能目录之外）——避免技能更新覆盖，也避免被误打包进公开包。
 * 显式传 { builtin: true } 才写回内置风格库（仅供技能作者维护）。
 */
function saveStyle(styleData, name, options = {}) {
  const stylesDir = options.builtin ? getBuiltinStylesDir() : getUserStylesDir();
  if (!fs.existsSync(stylesDir)) {
    fs.mkdirSync(stylesDir, { recursive: true });
  }

  const fileName = (name || styleData.name).replace(/[\/\\:*?"<>|]/g, '_') + '.json';
  const filePath = path.join(stylesDir, fileName);

  // If file exists, merge (user may extract from multiple slides of same style)
  if (fs.existsSync(filePath)) {
    const existing = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
    // Merge palettes, keep the richer one
    const mergedPalette = [...new Set([...(existing.colors?.palette || []), ...(styleData.colors?.palette || [])])];
    styleData.colors.palette = mergedPalette.slice(0, 10);
    // Keep more font info
    if (existing.typography?.fontFamilies?.length > (styleData.typography?.fontFamilies?.length || 0)) {
      styleData.typography.fontFamilies = existing.typography.fontFamilies;
    }
    // Merge title sizes
    const mergedTitleSizes = [...new Set([
      ...(existing.typography?.titleSizes || []),
      ...(styleData.typography?.titleSizes || [])
    ])].sort((a, b) => b - a).slice(0, 5);
    styleData.typography.titleSizes = mergedTitleSizes;

    // Merge components
    const mergedComponents = [...(existing.components || []), ...(styleData.components || [])];
    styleData.components = mergedComponents.slice(0, 15);
  }

  fs.writeFileSync(filePath, JSON.stringify(styleData, null, 2), 'utf-8');
  console.log(`风格已保存: ${filePath}`);
  return filePath;
}

// ── CLI ──────────────────────────────────────────────────────────────

async function main() {
  const args = process.argv.slice(2);

  // --list
  if (args.includes('--list') || args.includes('-l')) {
    listStyles();
    return;
  }

  // Must have input file
  const input = args.find(a => !a.startsWith('-') && !a.startsWith('--'));
  if (!input) {
    console.log('用法: node extract-style.js <html文件> [-o 输出.json] [--save 风格名称] [--list]');
    process.exit(1);
  }

  const outputIdx = args.indexOf('-o');
  const outputPath = outputIdx >= 0 ? args[outputIdx + 1] : null;

  const saveIdx = args.indexOf('--save');
  const saveName = saveIdx >= 0 ? args[saveIdx + 1] : null;

  console.log(`提取风格: ${input}`);
  const style = await extractStyle(input, { name: saveName });

  // Print summary
  console.log(`\n── 风格概要 ──`);
  console.log(`名称: ${style.name}`);
  console.log(`幻灯片尺寸: ${style.slideDimensions.width}×${style.slideDimensions.height}px (${style.slideDimensions.ratio})`);
  console.log(`配色: ${style.colors.palette.join(' ')}`);
  console.log(`字体: ${style.typography.fontFamilies.join(', ')}`);
  console.log(`标题字号: ${style.typography.titleSizes.join(', ')}px`);
  console.log(`正文字号: ${style.typography.bodySizes.join(', ')}px`);
  console.log(`布局模式: ${style.layout.positioning}`);
  if (style.layout.marginPattern) {
    console.log(`边距: ${style.layout.marginPattern.join(', ')}px`);
  }
  if (style.layout.contentWidth) {
    console.log(`内容宽度: ${style.layout.contentWidth}px`);
  }
  if (style.cssVariables) {
    const varCount = Object.keys(style.cssVariables).length;
    console.log(`CSS 变量: ${varCount} 个`);
  }
  console.log(`装饰组件: ${style.components.length} 个`);

  // Save to file
  if (outputPath) {
    fs.writeFileSync(outputPath, JSON.stringify(style, null, 2), 'utf-8');
    console.log(`\n风格已导出: ${outputPath}`);
  }

  if (saveName) {
    saveStyle(style, saveName);
  }

  if (!outputPath && !saveName) {
    // Default: print JSON to stdout
    console.log('\n' + JSON.stringify(style, null, 2));
  }
}

module.exports = { extractStyle, listStyles, saveStyle, getBuiltinStylesDir, getUserStylesDir };

// Run as CLI if called directly
if (require.main === module) {
  main().catch(err => {
    console.error(`错误: ${err.message}`);
    process.exit(1);
  });
}
