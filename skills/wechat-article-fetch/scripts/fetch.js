#!/usr/bin/env node

/**
 * 微信公众号文章抓取脚本
 *
 * 双引擎：
 *   - HTTP 直抓（默认主路线）：微信文章为服务端渲染，正文与图片地址都在初始 HTML 里，
 *     直接请求即可拿到，零依赖、速度快。带微信 UA + Referer。
 *   - Playwright 浏览器兜底：HTTP 路线失败或页面需 JS 渲染时自动切换（--engine auto）。
 *
 * 双产出（--mode both 默认）：
 *   - Markdown 整理版：清理为纯文本段落 + 图片本地化，供检索、引用、下游加工。
 *   - HTML 原件保真归档：完整页面 + 全部图片本地化，离线双击可读，供保真留痕。
 *     原图外链保留在 data-src 属性中备查。
 *
 * 用法: node fetch.js <URL> [输出路径] [--engine auto|http|playwright] [--mode markdown|archive|both]
 */

import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname, join, basename } from 'path';
import { writeFile, mkdir, stat, unlink } from 'fs/promises';
import { existsSync, createWriteStream } from 'fs';
import https from 'https';
import http from 'http';

// 获取当前文件路径（兼容 Windows）
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// skill 根目录（默认 archive 将创建在此目录下；本文件位于其下 scripts/ 内）
const SKILL_ROOT = dirname(__dirname);

// 检测平台
const isWindows = process.platform === 'win32';

// HTTP 直抓使用的请求头（微信 UA + Referer，缺 Referer 时部分图床/页面会拒绝）
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';
const HTTP_HEADERS = { 'User-Agent': UA, 'Referer': 'https://mp.weixin.qq.com/' };

// wx_fmt 参数到扩展名的映射（微信图 URL 通常无 .jpg 后缀，扩展名靠 wx_fmt 推断）
const EXT_MAP = { jpeg: '.jpg', jpg: '.jpg', png: '.png', gif: '.gif', webp: '.webp', svg: '.svg' };

// 图片筛选配置（仅作用于 Markdown 整理版；HTML 原件全量保真，不过滤）
const IMAGE_FILTER_CONFIG = {
  // 最小文件大小（字节），小于此值的图片将被过滤（表情符号、按钮图标等装饰图）
  minFileSize: 15 * 1024,
  enabled: true
};

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

/* ============================================================
 * 通用工具
 * ============================================================ */

/**
 * HTML 实体解码（&amp; 放最后，保证 &amp;lt; 只解码一次成字面量 &lt;）
 */
function decodeEntities(s) {
  return s
    .replace(/&nbsp;/g, ' ')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(parseInt(n, 10)))
    .replace(/&amp;/g, '&');
}

/**
 * HTML 属性值编码（改写 HTML 时把 URL 放回属性用）
 */
function encodeHtmlAttr(s) {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;');
}

/**
 * 标题净化为安全文件名
 */
function sanitizeTitle(t) {
  return (t || '')
    .replace(/[<>:"/\\|?*\n\r]/g, '')
    .replace(/\s+/g, '_')
    .substring(0, 100)
    .replace(/^[_.]+|[_.]+$/g, '') || 'untitled';
}

/**
 * 从微信图 URL 的 wx_fmt 参数推断扩展名（如 ?wx_fmt=jpeg → .jpg）
 */
function extFromWxFmt(url) {
  const m = url.match(/wx_fmt=([a-zA-Z0-9]+)/);
  if (!m) return null;
  const fmt = m[1].toLowerCase();
  return EXT_MAP[fmt] || `.${fmt}`;
}

/* ============================================================
 * HTTP 直抓路线（零依赖主路线）
 * ============================================================ */

/**
 * 通用 GET 请求（跟随重定向），返回响应文本
 */
function httpGetText(url, depth = 0) {
  return new Promise((resolve, reject) => {
    if (depth > 5) return reject(new Error('重定向次数过多'));
    const mod = url.startsWith('https') ? https : http;
    const req = mod.get(url, { headers: HTTP_HEADERS, timeout: 30000 }, (res) => {
      if ([301, 302, 303, 307, 308].includes(res.statusCode)) {
        res.resume();
        const loc = new URL(res.headers.location, url).href;
        return resolve(httpGetText(loc, depth + 1));
      }
      if (res.statusCode !== 200) {
        res.resume();
        return reject(new Error(`HTTP ${res.statusCode}`));
      }
      const chunks = [];
      res.on('data', c => chunks.push(c));
      res.on('end', () => resolve(Buffer.concat(chunks).toString('utf-8')));
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('请求超时')); });
  });
}

/**
 * 检测异常页面（链接失效 / 需验证 / 被删除）
 * @returns {string|null} 异常原因，null 表示正常
 */
function detectErrorPage(raw) {
  if (raw.includes('该内容已被发布者删除')) return '文章已被发布者删除';
  if (raw.includes('环境异常')) return '环境异常（访问被限制）';
  if (raw.includes('参数错误')) return '参数错误';
  if (raw.includes('此内容无法查看')) return '此内容无法查看';
  if (raw.includes('去验证')) return '操作频繁，需要验证';
  return null;
}

/**
 * 从页面 HTML 提取标题（msg_title JS 变量优先，比 <title> 稳）
 */
function extractTitleFromRaw(raw) {
  let m = raw.match(/var\s+msg_title\s*=\s*['"]([\s\S]*?)['"]\s*[;.]/);
  if (!m) m = raw.match(/<title>([\s\S]*?)<\/title>/);
  if (!m) return '';
  return decodeEntities(m[1])
    .replace(/\\x26/g, '&')  // 微信 JS 变量里的 & 有时写作 \x26
    .trim();
}

/**
 * 按 id 提取完整元素 HTML（标签栈扫描，比正则配对可靠；
 * 页面 HTML 不规范时宁可多吞尾部，由后续 script/style 清理兜底）
 */
function extractElementById(html, id) {
  const tagRe = /<(\/?)([a-zA-Z][a-zA-Z0-9]*)((?:"[^"]*"|'[^']*'|[^"'>])*)>/g;
  let start = -1, startTagLen = 0, tagName = '';
  let m;
  while ((m = tagRe.exec(html)) !== null) {
    if (m[1]) continue; // 跳过闭标签
    const idMatch = (m[3] || '').match(/\bid\s*=\s*["']([^"']+)["']/);
    if (idMatch && idMatch[1] === id) {
      start = m.index;
      startTagLen = m[0].length;
      tagName = m[2].toLowerCase();
      break;
    }
  }
  if (start === -1) return null;

  const voidTags = new Set(['img', 'br', 'input', 'hr', 'meta', 'link', 'source', 'area', 'col', 'embed']);
  let depth = 1;
  let end = html.length;
  tagRe.lastIndex = start + startTagLen;
  while ((m = tagRe.exec(html)) !== null) {
    const name = m[2].toLowerCase();
    const selfClosing = m[0].endsWith('/>') || voidTags.has(name);
    if (m[1]) { // 闭标签
      if (name === tagName) {
        depth--;
        if (depth === 0) { end = m.index + m[0].length; break; }
      }
    } else if (!selfClosing && name === tagName) {
      depth++;
    }
  }
  return html.slice(start, end);
}

/**
 * 解析微信文章页面：提取标题与正文区域 HTML
 */
function parseWechatArticle(raw) {
  const title = extractTitleFromRaw(raw);
  const contentHtml = extractElementById(raw, 'js_content') ||
                      raw.match(/<div[^>]*class="[^"]*rich_media_content[^"]*"[^>]*>[\s\S]*/i)?.[0] ||
                      null;
  if (!contentHtml) {
    throw new Error('未找到正文区域（js_content），页面结构异常');
  }
  return { title: title || 'untitled', contentHtml };
}

/**
 * 正文 HTML → Markdown 文本 + 图片清单（单遍扫描，占位符下标与图片天然对齐）
 * 图片只认微信图床（qpic.cn，含 mmbiz/mmecoa 等子域），过滤统计像素等杂图
 */
function extractMarkdownAndImages(contentHtml) {
  const images = [];
  let out = contentHtml;

  // 去 script/style（extractElementById 容错多吞尾部时靠这里兜底）
  out = out.replace(/<script[\s\S]*?<\/script>/gi, '');
  out = out.replace(/<style[\s\S]*?<\/style>/gi, '');

  // 图片 → 占位符（data-src 优先；懒加载真图地址在 data-src，src 多为 base64 占位）
  out = out.replace(/<img\b[^>]*>/gi, (tag) => {
    const m = tag.match(/data-src\s*=\s*["']([^"']+)["']/i) || tag.match(/\bsrc\s*=\s*["']([^"']+)["']/i);
    if (!m) return '';
    const u = decodeEntities(m[1]); // 属性里是 &amp;，解码后才能下载
    if (!/^https?:\/\//i.test(u) || !/qpic\.cn/i.test(u)) return '';
    const altMatch = tag.match(/\balt\s*=\s*["']([^"']*)["']/i);
    images.push({ url: u, alt: (altMatch && altMatch[1]) || `图片${images.length + 1}`, index: images.length });
    return `\n\n{{IMAGE_${images.length - 1}}}\n\n`;
  });

  // 结构标签 → Markdown 等价物
  out = out
    .replace(/<h([1-6])[^>]*>/gi, (_, n) => `\n\n${'#'.repeat(Math.min(6, parseInt(n, 10) + 1))} `)
    .replace(/<\/h[1-6]>/gi, '\n\n')
    .replace(/<li[^>]*>/gi, '\n- ')
    .replace(/<\/li>/gi, '\n')
    .replace(/<br\s*\/?\s*>/gi, '\n')
    .replace(/<\/?(p|div|section|blockquote|figure|figcaption|ul|ol|table|tr|pre)[^>]*>/gi, '\n\n')
    .replace(/<[^>]+>/g, '');

  out = decodeEntities(out);
  out = out.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
  return { text: out, images };
}

/* ============================================================
 * Playwright 兜底路线
 * ============================================================ */

// 获取适当的命令和参数
function getNpxCommand() {
  if (isWindows) {
    return {
      command: 'cmd',
      args: ['/c', 'npx', '-y', 'playwright', 'install', 'chromium'],
      shell: false
    };
  } else {
    return {
      command: 'npx',
      args: ['-y', 'playwright', 'install', 'chromium'],
      shell: false
    };
  }
}

// 检查并安装 Playwright
async function ensurePlaywright() {
  try {
    await import('playwright');
    return true;
  } catch (error) {
    console.log('⚠️  未检测到 Playwright,正在自动安装...');
    console.log('这可能需要几分钟时间,请耐心等待...\n');

    return new Promise((resolve, reject) => {
      const { command, args, shell } = getNpxCommand();
      const install = spawn(command, args, { stdio: 'inherit', shell });

      install.on('close', (code) => {
        if (code === 0) {
          console.log('\n✅ Playwright 安装完成！');
          resolve(true);
        } else {
          console.error('\n❌ Playwright 安装失败');
          reject(new Error('Playwright installation failed'));
        }
      });

      install.on('error', (err) => {
        console.error('\n❌ 启动安装进程失败:', err.message);
        reject(err);
      });
    });
  }
}

async function attemptFetch(chromium, url, options = {}) {
  const { headless = true } = options;

  const browser = await chromium.launch({
    headless,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-web-security',
      '--disable-features=VizDisplayCompositor'
    ]
  });

  try {
    const context = await browser.newContext({
      userAgent: UA,
      viewport: { width: 1366, height: 768 }
    });

    const page = await context.newPage();

    // 反检测设置
    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
      Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
      Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
      window.chrome = { runtime: {} };
    });

    console.log('正在访问:', url);
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(3000);

    // 滚动页面触发懒加载
    await page.evaluate(() => {
      window.scrollTo(0, document.body.scrollHeight);
    });
    await page.waitForTimeout(2000);

    // 提取文章内容和图片信息
    const content = await page.evaluate(() => {
      const article = document.querySelector('#js_content') ||
                     document.querySelector('.rich_media_content') ||
                     document.body;

      const rawHtml = article.innerHTML;

      const isErrorPage = rawHtml.includes('参数错误') ||
                         rawHtml.includes('访问异常') ||
                         rawHtml.includes('此内容无法查看') ||
                         document.title === '微信公众平台';

      if (isErrorPage) {
        throw new Error('检测到错误页面,可能URL无效或需要登录');
      }

      const images = [];
      const imgElements = article.querySelectorAll('img');
      imgElements.forEach((img, index) => {
        const src = img.getAttribute('data-src') || img.src || img.getAttribute('src');
        const alt = img.alt || `图片${index + 1}`;
        if (src && !src.startsWith('data:')) {
          images.push({ url: src, alt, index });
        }
      });

      // 将图片标签替换为占位符，保留图片在文档中的位置
      let imageIndex = 0;
      let processedContent = rawHtml.replace(/<img[^>]*>/gi, (match) => {
        const srcMatch = match.match(/data-src=["']([^"']+)["']/) ||
                        match.match(/src=["']([^"']+)["']/);
        if (srcMatch) {
          const placeholder = `{{IMAGE_${imageIndex}}}`;
          imageIndex++;
          return `\n\n${placeholder}\n\n`;
        }
        return '';
      });

      let cleanText = processedContent
        .replace(/<p[^>]*>/gi, '\n\n')
        .replace(/<\/p>/gi, '')
        .replace(/<h[1-6][^>]*>/gi, '\n\n### ')
        .replace(/<\/h[1-6]>/gi, '\n\n')
        .replace(/<br\s*\/?>/gi, '\n')
        .replace(/<[^>]+>/g, '')
        .replace(/&nbsp;/g, ' ')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&amp;/g, '&')
        .replace(/&quot;/g, '"')
        .replace(/&#39;/g, "'")
        .replace(/\n{3,}/g, '\n\n')
        .replace(/^\n+/, '')
        .replace(/\n+$/, '')
        .trim();

      return {
        title: document.title.replace('微信公众平台', '').trim(),
        content: cleanText,
        url: window.location.href,
        images
      };
    });

    // 渲染后的完整页面 HTML（用于 HTML 原件保真归档）
    content.rawHtml = await page.content();

    return content;

  } finally {
    await browser.close();
  }
}

/* ============================================================
 * 产物落盘（两条引擎路线共用）
 * ============================================================ */

/**
 * 解析输出位置。返回产物路径集合：
 *   未传路径      → archive/<YYYYMMDD_HHMMSS>_<标题>/
 *   传目录        → <目录>/<YYYYMMDD_HHMMSS>_<标题>/
 *   传 .md 文件   → 兼容旧用法：md 落该路径，其余产物同目录同名前缀平铺
 */
function resolveOutput(outputPath, title) {
  const safeTitle = sanitizeTitle(title);
  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;

  let dir, prefix;
  if (!outputPath) {
    dir = join(SKILL_ROOT, 'archive', `${stamp}_${safeTitle.substring(0, 40)}`);
    prefix = safeTitle;
  } else if (/\.md$/i.test(outputPath)) {
    dir = dirname(outputPath);
    prefix = basename(outputPath).replace(/\.md$/i, '');
  } else {
    dir = join(outputPath, `${stamp}_${safeTitle.substring(0, 40)}`);
    prefix = safeTitle;
  }
  return {
    dir,
    mdPath: join(dir, `${prefix}.md`),
    assetsDir: join(dir, `${prefix}_assets`),
    htmlPath: join(dir, `${prefix}.html`),
    htmlAssetsDir: join(dir, `${prefix}_html_assets`)
  };
}

/**
 * 下载单个图片（带微信 UA + Referer，跟随重定向）
 */
function downloadImage(url, filepath) {
  return new Promise((resolve, reject) => {
    const protocol = url.startsWith('https') ? https : http;
    const request = protocol.get(url, { headers: HTTP_HEADERS }, (response) => {
      if ([301, 302, 303, 307, 308].includes(response.statusCode)) {
        response.resume();
        downloadImage(new URL(response.headers.location, url).href, filepath).then(resolve).catch(reject);
        return;
      }

      if (response.statusCode !== 200) {
        response.resume();
        reject(new Error(`下载图片失败: ${response.statusCode}`));
        return;
      }

      const fileStream = createWriteStream(filepath);
      response.pipe(fileStream);

      fileStream.on('finish', () => {
        fileStream.close();
        resolve();
      });

      fileStream.on('error', async (err) => {
        // 删除不完整的文件
        await unlink(filepath).catch(() => {});
        reject(err);
      });
    });

    request.on('error', reject);
    request.setTimeout(30000, () => {
      request.destroy();
      reject(new Error('下载图片超时'));
    });
  });
}

/**
 * 批量下载图片（Markdown 整理版用：智能过滤小装饰图）
 * @returns {Promise<Object>} 图片索引到文件名的映射
 */
async function downloadImages(images, imagesDir) {
  if (!images || images.length === 0) {
    return {};
  }

  console.log(`\n📥 发现 ${images.length} 张图片，开始下载...`);

  await mkdir(imagesDir, { recursive: true });

  const imageMap = {};
  let successCount = 0;
  let failCount = 0;
  let filteredCount = 0;

  for (let i = 0; i < images.length; i++) {
    const img = images[i];
    try {
      // 扩展名优先从 wx_fmt 参数推断，其次 URL 后缀，最后默认 .jpg
      let ext = extFromWxFmt(img.url);
      if (!ext) {
        const urlMatch = img.url.match(/\.([a-z]{3,4})(?:\?|$)/i);
        ext = urlMatch ? '.' + urlMatch[1].toLowerCase() : '.jpg';
      }

      const filename = `image_${Date.now()}_${i}${ext}`;
      const filepath = join(imagesDir, filename);

      await downloadImage(img.url, filepath);

      // 检查文件大小，过滤太小的装饰性图片
      if (IMAGE_FILTER_CONFIG.enabled) {
        const stats = await stat(filepath);
        if (stats.size < IMAGE_FILTER_CONFIG.minFileSize) {
          await unlink(filepath);
          filteredCount++;
          const sizeKB = (stats.size / 1024).toFixed(2);
          console.log(`  🔍 [${i + 1}/${images.length}] 已过滤 (${sizeKB}KB < ${IMAGE_FILTER_CONFIG.minFileSize / 1024}KB): ${img.alt}`);
          continue;
        }
      }

      imageMap[i] = { filename, alt: img.alt };
      successCount++;
      console.log(`  ✅ [${i + 1}/${images.length}] ${img.alt}`);
    } catch (error) {
      failCount++;
      console.log(`  ❌ [${i + 1}/${images.length}] 下载失败: ${error.message}`);
    }
  }

  console.log(`📊 整理版图片: 成功 ${successCount} 张, 过滤 ${filteredCount} 张, 失败 ${failCount} 张\n`);

  return imageMap;
}

/**
 * 保存 Markdown 整理版（占位符替换为本地图片引用）
 */
async function saveMarkdown(article, out, opts = {}) {
  await mkdir(out.dir, { recursive: true });

  let content = article.content || article.text;

  if (article.images && article.images.length > 0) {
    const imageMap = await downloadImages(article.images, out.assetsDir);
    content = content.replace(/\{\{IMAGE_(\d+)\}\}/g, (_, idx) => {
      const entry = imageMap[parseInt(idx, 10)];
      if (entry) {
        return `![${entry.alt}](${join(basename(out.assetsDir), entry.filename)})`;
      }
      return ''; // 被过滤掉的图片，移除占位符
    });
    content = content.replace(/\n{3,}/g, '\n\n');
  }

  const archiveNote = opts.hasArchive
    ? `> HTML 原件: ${basename(out.htmlPath)}（同目录，离线保真）\n`
    : '';

  const markdown = `# ${article.title}

> 原文链接: ${article.url}
> 抓取时间: ${new Date().toLocaleString('zh-CN')}
${archiveNote}
---

${content}
`;

  await writeFile(out.mdPath, markdown, 'utf-8');
  console.log(`✅ Markdown 整理版: ${out.mdPath}`);
  return out.mdPath;
}

/**
 * 保存 HTML 原件（保真归档）：
 *   正文图（data-src）与头像等外链图全部下载本地化（不过滤小图——原件保真），
 *   原 URL 保留在 data-src 属性备查；清除 base64 占位与 visibility:hidden，
 *   最后输出校验报告（缺失本地图 / 残留外链 / 下载失败）。
 */
async function saveHtmlArchive(rawHtml, out) {
  await mkdir(out.htmlAssetsDir, { recursive: true });

  // 收集需要本地化的图片 URL（正文 data-src 任意 qpic.cn 子域 + 页面 src 直链 mmbiz 图）
  const seen = new Set();
  const jobs = [];
  let m;
  const dataSrcRe = /data-src\s*=\s*["'](https?:\/\/[^"']*qpic\.cn[^"']*)["']/gi;
  while ((m = dataSrcRe.exec(rawHtml)) !== null) {
    const u = decodeEntities(m[1]);
    if (!seen.has(u)) { seen.add(u); jobs.push(u); }
  }
  const srcRe = /\ssrc\s*=\s*["'](https?:\/\/mmbiz\.qpic\.cn\/[^"']+)["']/gi;
  while ((m = srcRe.exec(rawHtml)) !== null) {
    const u = decodeEntities(m[1]);
    if (!seen.has(u)) { seen.add(u); jobs.push(u); }
  }

  // 下载（全量保真，含小装饰图标）
  const urlToLocal = new Map();
  const failed = [];
  for (let i = 0; i < jobs.length; i++) {
    const u = jobs[i];
    const ext = extFromWxFmt(u) || '.jpg';
    const name = `img${String(i + 1).padStart(2, '0')}${ext}`;
    const filepath = join(out.htmlAssetsDir, name);
    try {
      await downloadImage(u, filepath);
      const size = (await stat(filepath)).size;
      if (size === 0) {
        await unlink(filepath).catch(() => {});
        failed.push(u);
        continue;
      }
      urlToLocal.set(u, `${basename(out.htmlAssetsDir)}/${name}`);
    } catch (e) {
      failed.push(`${u} (${e.message})`);
    }
  }

  // 改写 HTML：data-src → 本地 src（原 URL 保留备查）。
  // 用哨兵属性名两步走：先打上本地地址，再清除 base64 占位 src 属性（而不是删整个 img 标签，
  // 避免误删已带本地地址的正文图），最后哨兵转正。
  let html = rawHtml;
  for (const [u, local] of urlToLocal) {
    for (const variant of [u, encodeHtmlAttr(u)]) {
      html = html.split(`data-src="${variant}"`).join(`__LOCAL_SRC__="${local}" data-src="${variant}"`);
    }
  }
  html = html.replace(/\ssrc="data:image[^"]*"/gi, ''); // 清除懒加载 base64 占位属性
  html = html.split('__LOCAL_SRC__').join('src');
  // 头像等无 data-src 的外链图直接替换 src
  for (const [u, local] of urlToLocal) {
    for (const variant of [u, encodeHtmlAttr(u)]) {
      html = html.split(`src="${variant}"`).join(`src="${local}"`);
    }
  }
  // 清除隐藏样式，保证离线可见
  html = html.split('visibility: hidden;').join('');

  await writeFile(out.htmlPath, html, 'utf-8');

  // 校验报告（剥离 script/style 后再扫，避免误报 JS 代码里的 img 模板字符串）
  const htmlNoScript = html.replace(/<script[\s\S]*?<\/script>/gi, '').replace(/<style[\s\S]*?<\/style>/gi, '');
  const localRefs = [...htmlNoScript.matchAll(/<img[^>]*\ssrc="([^"]+)"/gi)]
    .map(x => decodeEntities(x[1]))
    .filter(s => s && !/^https?:|^data:/.test(s));
  const missing = [...new Set(localRefs.filter(p => !existsSync(join(out.dir, p))))];
  const remoteLeft = [...new Set(
    [...htmlNoScript.matchAll(/<img(?![^>]*data-src)[^>]*\ssrc="(https?:\/\/[^"]+)"/gi)]
      .map(x => decodeEntities(x[1]))
      .filter(u => !u.includes('pic_blank.gif') && !urlToLocal.has(u))
  )];

  const flag = (missing.length === 0 && remoteLeft.length === 0) ? 'OK ' : '警告';
  console.log(`[${flag}] HTML 原件: ${out.htmlPath}`);
  console.log(`       ${basename(out.htmlPath)} ${(Buffer.byteLength(html) / 1024).toFixed(0)}KB | 本地化图片 ${urlToLocal.size} 张`);
  if (missing.length) console.log(`       缺失本地图: ${missing.slice(0, 5).join(', ')}`);
  if (remoteLeft.length) console.log(`       残留外链: ${remoteLeft.slice(0, 3).join(', ')}`);
  if (failed.length) console.log(`       下载失败: ${failed.slice(0, 3).join(', ')}`);

  return { htmlPath: out.htmlPath, images: urlToLocal.size, missing, remoteLeft, failed };
}

/* ============================================================
 * 主流程
 * ============================================================ */

function printUsage() {
  console.error('用法: node fetch.js <微信公众号文章URL> [输出路径] [选项]');
  console.error('');
  console.error('参数:');
  console.error('  URL          微信公众号文章链接（必填）');
  console.error('  输出路径      可选。目录（文章产物归入其下子目录）或 .md 文件路径（兼容旧用法）；');
  console.error('                省略时保存到 skill 内 archive/<时间戳>_<标题>/');
  console.error('  --engine     抓取引擎: auto（默认，HTTP 直抓失败后 Playwright 兜底）| http | playwright');
  console.error('  --mode       产出模式: both（默认，Markdown 整理版 + HTML 原件保真）| markdown | archive');
  console.error('  --retries    重试次数（默认 3，仅 Playwright 兜底路线使用）');
  console.error('');
  console.error('示例:');
  console.error('  node fetch.js "https://mp.weixin.qq.com/s/xxxxx"');
  console.error('  node fetch.js "https://mp.weixin.qq.com/s/xxxxx" "./articles/"');
  console.error('  node fetch.js "https://mp.weixin.qq.com/s/xxxxx" --mode markdown');
  console.error('  node fetch.js "https://mp.weixin.qq.com/s/xxxxx" --engine playwright');
}

function parseArgs(argv) {
  const opts = { url: null, outputPath: null, engine: 'auto', mode: 'both', retries: 3 };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--engine') opts.engine = (argv[++i] || '').toLowerCase();
    else if (a === '--mode') opts.mode = (argv[++i] || '').toLowerCase();
    else if (a === '--retries') opts.retries = parseInt(argv[++i], 10) || 3;
    else if (a === '--help' || a === '-h') { printUsage(); process.exit(0); }
    else if (!opts.url) opts.url = a;
    else if (!opts.outputPath) opts.outputPath = a;
  }
  if (!['auto', 'http', 'playwright'].includes(opts.engine)) {
    console.error(`❌ 无效的 --engine: ${opts.engine}（可选 auto | http | playwright）`);
    process.exit(1);
  }
  if (!['markdown', 'archive', 'both'].includes(opts.mode)) {
    console.error(`❌ 无效的 --mode: ${opts.mode}（可选 markdown | archive | both）`);
    process.exit(1);
  }
  return opts;
}

/**
 * 统一保存收尾（两条引擎路线共用）
 */
async function saveOutputs(article, out, opts) {
  const report = { title: article.title, url: article.url, engine: opts.engineUsed, md: null, archive: null };
  const hasMd = opts.mode !== 'archive';
  const hasArchive = opts.mode !== 'markdown';

  if (hasMd) {
    report.md = await saveMarkdown(article, out, { hasArchive });
  }
  if (hasArchive && article.rawHtml) {
    report.archive = await saveHtmlArchive(article.rawHtml, out);
  } else if (hasArchive) {
    console.log('⚠️  未获取到页面 HTML，跳过原件归档');
  }
  return report;
}

/**
 * HTTP 直抓路线
 */
async function httpRoute(url, opts) {
  console.log('🚀 引擎: HTTP 直抓（零依赖）');
  const raw = await httpGetText(url);

  const err = detectErrorPage(raw);
  if (err) throw new Error(`HTTP 直抓遇到异常页面: ${err}`);

  const { title, contentHtml } = parseWechatArticle(raw);
  const { text, images } = extractMarkdownAndImages(contentHtml);

  console.log('✅ 抓取成功！');
  console.log('标题:', title);
  console.log('内容长度:', text.length, '字符');

  const out = resolveOutput(opts.outputPath, title);
  return saveOutputs({ title, text, content: text, url, images, rawHtml: raw }, out, opts);
}

/**
 * Playwright 浏览器路线（兜底）
 */
async function playwrightRoute(url, opts) {
  console.log('🌐 引擎: Playwright 浏览器');
  await ensurePlaywright();
  const { chromium } = await import('playwright');

  let result = null;
  for (let attempt = 1; attempt <= opts.retries; attempt++) {
    try {
      console.log(`尝试 ${attempt}/${opts.retries}: 抓取 ${url}`);
      result = await attemptFetch(chromium, url, { headless: true });
      break;
    } catch (error) {
      console.error(`❌ 尝试 ${attempt} 失败: ${error.message}`);
      if (attempt < opts.retries) {
        console.log('⏳ 等待 3 秒后重试...');
        await sleep(3000);
      }
    }
  }

  if (!result) {
    console.log('⚠️  无头模式失败，尝试使用有头模式...');
    result = await attemptFetch(chromium, url, { headless: false });
  }

  console.log('✅ 抓取成功！');
  console.log('标题:', result.title);
  console.log('内容长度:', result.content.length, '字符');

  const out = resolveOutput(opts.outputPath, result.title);
  return saveOutputs(result, out, opts);
}

/**
 * 主入口：按引擎策略分发
 */
async function run(url, opts) {
  if (opts.engine === 'http') {
    opts.engineUsed = 'http';
    return httpRoute(url, opts);
  }
  if (opts.engine === 'playwright') {
    opts.engineUsed = 'playwright';
    return playwrightRoute(url, opts);
  }
  // auto：HTTP 直抓优先，失败切 Playwright
  try {
    opts.engineUsed = 'http';
    return await httpRoute(url, opts);
  } catch (error) {
    console.error(`❌ HTTP 直抓失败: ${error.message}`);
    console.log('🔄 切换 Playwright 浏览器兜底...\n');
    opts.engineUsed = 'playwright';
    return playwrightRoute(url, opts);
  }
}

/**
 * 编程接口（供其他模块 import）
 * 兼容旧签名 fetchWechatArticle(url, retries, autoSavePath)
 */
async function fetchWechatArticle(url, options = {}) {
  if (typeof options === 'number') options = { retries: options };
  const opts = {
    engine: 'auto',
    mode: 'both',
    retries: 3,
    outputPath: options.outputPath || options.autoSavePath || null,
    ...options
  };
  return run(url, opts);
}

// 命令行调用
const isMainModule = (() => {
  try {
    const mainPath = fileURLToPath(import.meta.url).replace(/\\/g, '/');
    const argvPath = (process.argv[1] || '').replace(/\\/g, '/');
    if (mainPath === argvPath) return true;
    const mainFileName = basename(mainPath);
    const argvFileName = basename(argvPath);
    return mainFileName === argvFileName && argvFileName.includes('fetch.js');
  } catch {
    return (process.argv[1] || '').includes('fetch.js');
  }
})();

if (isMainModule) {
  const opts = parseArgs(process.argv.slice(2));

  if (!opts.url) {
    printUsage();
    process.exit(1);
  }
  if (!/^https?:\/\//i.test(opts.url)) {
    console.error('❌ URL 需以 http(s):// 开头');
    process.exit(1);
  }

  run(opts.url, opts)
    .then(report => {
      console.log('\n=== 抓取结果 ===');
      console.log('标题:', report.title);
      console.log('URL:', report.url);
      console.log('引擎:', report.engine);
      if (report.md) console.log('Markdown 整理版:', report.md);
      if (report.archive) console.log('HTML 原件:', report.archive.htmlPath);
      console.log('\n✅ 完成！');
    })
    .catch(error => {
      console.error('\n❌ 错误:', error.message);
      process.exit(1);
    });
}

// 导出供其他模块使用
export { fetchWechatArticle };
