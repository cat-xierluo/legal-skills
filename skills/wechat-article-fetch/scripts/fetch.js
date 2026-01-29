#!/usr/bin/env node

/**
 * 微信公众号文章抓取脚本
 * 使用 Playwright headless 模式,无弹窗后台抓取
 * 自动检测并安装 Playwright
 *
 * 用法: node fetch.js <URL> [output.md]
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

// 检测平台
const isWindows = process.platform === 'win32';

// 图片筛选配置
const IMAGE_FILTER_CONFIG = {
  // 最小文件大小（字节），小于此值的图片将被过滤
  // 默认 15KB，可以过滤掉小的表情符号、按钮图标等
  minFileSize: 15 * 1024,

  // 是否启用筛选
  enabled: true
};

// 获取适当的命令和参数
function getNpxCommand() {
  if (isWindows) {
    // Windows: 使用 cmd.exe
    return {
      command: 'cmd',
      args: ['/c', 'npx', '-y', 'playwright', 'install', 'chromium'],
      shell: false
    };
  } else {
    // Unix-like: 直接使用 npx
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
    // 尝试导入 playwright
    await import('playwright');
    return true;
  } catch (error) {
    console.log('⚠️  未检测到 Playwright,正在自动安装...');
    console.log('这可能需要几分钟时间,请耐心等待...\n');

    return new Promise((resolve, reject) => {
      const { command, args, shell } = getNpxCommand();

      // 安装 playwright
      const install = spawn(command, args, {
        stdio: 'inherit',
        shell
      });

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

async function fetchWechatArticle(url, retries = 3, autoSavePath = null) {
  // 确保 Playwright 已安装
  await ensurePlaywright();

  // 动态导入 playwright
  const { chromium } = await import('playwright');

  // 首先尝试无头模式
  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      console.log(`尝试 ${attempt}/${retries}: 抓取 ${url}`);
      const result = await attemptFetch(chromium, url, { headless: true });
      console.log('✅ 抓取成功！');

      // 如果指定了保存路径，保存为 Markdown 文件
      if (autoSavePath) {
        await saveAsMarkdown(result, autoSavePath);
      }

      return result;
    } catch (error) {
      console.error(`❌ 尝试 ${attempt} 失败:`, error.message);
      if (attempt === retries) {
        console.log('⚠️  无头模式失败，尝试使用有头模式...');
        try {
          const result = await attemptFetch(chromium, url, { headless: false });
          console.log('✅ 有头模式抓取成功！');

          // 如果指定了保存路径，保存为 Markdown 文件
          if (autoSavePath) {
            await saveAsMarkdown(result, autoSavePath);
          }

          return result;
        } catch (headedError) {
          console.error('❌ 有头模式也失败了:', headedError.message);
          throw headedError;
        }
      }
      console.log(`⏳ 等待 3 秒后重试...`);
      await new Promise(resolve => setTimeout(resolve, 3000));
    }
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
    // 创建浏览器上下文，指定 User-Agent
    const context = await browser.newContext({
      userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      viewport: { width: 1366, height: 768 }
    });

    // 创建页面
    const page = await context.newPage();

    // 反检测设置
    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
      Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
      Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
      window.chrome = { runtime: {} };
    });

    console.log('正在访问:', url);
    await page.goto(url, {
      waitUntil: 'networkidle',
      timeout: 30000
    });

    // 等待页面加载完成
    await page.waitForTimeout(3000);

    // 滚动页面触发懒加载
    await page.evaluate(() => {
      window.scrollTo(0, document.body.scrollHeight);
    });
    await page.waitForTimeout(2000);

    // 提取文章内容和图片信息
    const content = await page.evaluate(() => {
      // 获取微信公众号文章主体
      const article = document.querySelector('#js_content') ||
                     document.querySelector('.rich_media_content') ||
                     document.body;

      const rawHtml = article.innerHTML;

      // 检测错误页面
      const isErrorPage = rawHtml.includes('参数错误') ||
                         rawHtml.includes('访问异常') ||
                         rawHtml.includes('此内容无法查看') ||
                         document.title === '微信公众平台';

      if (isErrorPage) {
        throw new Error('检测到错误页面,可能URL无效或需要登录');
      }

      // 提取所有图片信息
      const images = [];
      const imgElements = article.querySelectorAll('img');
      imgElements.forEach((img, index) => {
        const src = img.getAttribute('data-src') || img.src || img.getAttribute('src');
        const alt = img.alt || `图片${index + 1}`;
        if (src && !src.startsWith('data:')) {
          images.push({
            url: src,
            alt: alt,
            index: index
          });
        }
      });

      // 清理HTML,保留段落结构和图片位置
      let processedContent = rawHtml;

      // 将图片标签替换为占位符，保留图片在文档中的位置
      let imageIndex = 0;
      processedContent = processedContent.replace(/<img[^>]*>/gi, (match) => {
        // 提取图片的 data-src 或 src
        const srcMatch = match.match(/data-src=["']([^"']+)["']/) ||
                        match.match(/src=["']([^"']+)["']/);
        if (srcMatch) {
          const placeholder = `{{IMAGE_${imageIndex}}}`;
          imageIndex++;
          return `\n\n${placeholder}\n\n`;
        }
        return '';
      });

      // 清理剩余的HTML标签，保留结构
      let cleanText = processedContent
        // 段落标签替换为双换行
        .replace(/<p[^>]*>/gi, '\n\n')
        .replace(/<\/p>/gi, '')
        // 标题标签
        .replace(/<h[1-6][^>]*>/gi, '\n\n### ')
        .replace(/<\/h[1-6]>/gi, '\n\n')
        // br标签替换为换行
        .replace(/<br\s*\/?>/gi, '\n')
        // 移除剩余HTML标签（不包括图片占位符）
        .replace(/<[^>]+>/g, '')
        // 处理HTML实体
        .replace(/&nbsp;/g, ' ')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&amp;/g, '&')
        .replace(/&quot;/g, '"')
        .replace(/&#39;/g, "'")
        // 清理多余空行(最多保留两个连续换行)
        .replace(/\n{3,}/g, '\n\n')
        .replace(/^\n+/, '')
        .replace(/\n+$/, '')
        .trim();

      return {
        title: document.title.replace('微信公众平台', '').trim(),
        content: cleanText,
        url: window.location.href,
        images: images
      };
    });

    console.log('抓取成功！');
    console.log('标题:', content.title);
    console.log('内容长度:', content.content.length, '字符');

    return content;

  } catch (error) {
    console.error('抓取失败:', error.message);
    throw error;
  } finally {
    await browser.close();
  }
}

/**
 * 下载单个图片
 * @param {string} url - 图片URL
 * @param {string} filepath - 保存路径
 * @returns {Promise<void>}
 */
function downloadImage(url, filepath) {
  return new Promise((resolve, reject) => {
    const protocol = url.startsWith('https') ? https : http;
    const request = protocol.get(url, (response) => {
      // 处理重定向
      if (response.statusCode === 301 || response.statusCode === 302) {
        downloadImage(response.headers.location, filepath).then(resolve).catch(reject);
        return;
      }

      if (response.statusCode !== 200) {
        reject(new Error(`下载图片失败: ${response.statusCode}`));
        return;
      }

      const fileStream = createWriteStream(filepath);
      response.pipe(fileStream);

      fileStream.on('finish', () => {
        fileStream.close();
        resolve();
      });

      fileStream.on('error', (err) => {
        // 删除不完整的文件
        try {
          const fs = require('fs');
          fs.unlink(filepath, () => {});
        } catch (e) {}
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
 * 批量下载图片
 * @param {Array} images - 图片信息数组 [{url, alt, index}]
 * @param {string} imagesDir - 图片保存目录
 * @returns {Promise<Object>} 图片索引到文件名的映射
 */
async function downloadImages(images, imagesDir) {
  if (!images || images.length === 0) {
    return {};
  }

  console.log(`\n📥 发现 ${images.length} 张图片，开始下载...`);

  // 确保图片目录存在
  if (!existsSync(imagesDir)) {
    await mkdir(imagesDir, { recursive: true });
  }

  const imageMap = {};
  let successCount = 0;
  let failCount = 0;
  let filteredCount = 0;

  for (let i = 0; i < images.length; i++) {
    const img = images[i];
    try {
      // 从 URL 中提取文件扩展名，如果没有则使用 .jpg
      let ext = '.jpg';
      const urlMatch = img.url.match(/\.([a-z]{3,4})(?:\?|$)/i);
      if (urlMatch) {
        ext = '.' + urlMatch[1].toLowerCase();
      }

      // 生成文件名：使用时间戳和索引避免重名
      const filename = `image_${Date.now()}_${i}${ext}`;
      const filepath = join(imagesDir, filename);

      // 下载图片
      await downloadImage(img.url, filepath);

      // 检查文件大小，过滤掉太小的图片
      if (IMAGE_FILTER_CONFIG.enabled) {
        const stats = await stat(filepath);
        const fileSize = stats.size;

        if (fileSize < IMAGE_FILTER_CONFIG.minFileSize) {
          // 删除太小的图片
          await unlink(filepath);
          filteredCount++;
          const sizeKB = (fileSize / 1024).toFixed(2);
          console.log(`  🔍 [${i + 1}/${images.length}] 已过滤 (${sizeKB}KB < ${IMAGE_FILTER_CONFIG.minFileSize / 1024}KB): ${img.alt}`);
          continue;
        }
      }

      imageMap[i] = {
        filename: filename,
        alt: img.alt
      };
      successCount++;
      console.log(`  ✅ [${i + 1}/${images.length}] ${img.alt}`);
    } catch (error) {
      failCount++;
      console.log(`  ❌ [${i + 1}/${images.length}] 下载失败: ${error.message}`);
    }
  }

  console.log(`📊 图片下载完成: 成功 ${successCount} 张, 过滤 ${filteredCount} 张, 失败 ${failCount} 张\n`);

  return imageMap;
}

/**
 * 将抓取的文章保存为 Markdown 文件
 * @param {Object} article - 文章对象 {title, content, url, images}
 * @param {string} outputPath - 输出文件路径
 */
async function saveAsMarkdown(article, outputPath) {
  try {
    // 规范化文件名（移除非法字符）
    const safeTitle = article.title
      .replace(/[<>:"/\\|?*]/g, '') // 移除 Windows 非法字符
      .replace(/\s+/g, '_') // 空格替换为下划线
      .substring(0, 100); // 限制长度

    // 检查是目录还是文件路径
    let finalPath = outputPath;
    try {
      const stats = await stat(outputPath);
      if (stats.isDirectory()) {
        // 如果是目录，使用标题作为文件名
        finalPath = join(outputPath, `${safeTitle}.md`);
      }
    } catch {
      // 路径不存在或不是目录，直接使用给定的路径
      // 确保路径以 .md 结尾
      if (!finalPath.endsWith('.md')) {
        finalPath = `${finalPath}.md`;
      }
    }

    // 确保目录存在
    const dir = dirname(finalPath);
    if (!existsSync(dir)) {
      await mkdir(dir, { recursive: true });
    }

    // 下载图片并获取图片映射
    let content = article.content;
    let imagesDir = null;

    if (article.images && article.images.length > 0) {
      // 创建图片保存目录（与 Markdown 文件同名）
      const mdFileBasename = finalPath.replace(/\.md$/, '');
      imagesDir = `${mdFileBasename}_assets`;

      const imageMap = await downloadImages(article.images, imagesDir);

      // 替换内容中的图片占位符
      content = content.replace(/\{\{IMAGE_(\d+)\}\}/g, (match, index) => {
        const imgIndex = parseInt(index);
        if (imageMap[imgIndex]) {
          const { filename, alt } = imageMap[imgIndex];
          // 计算相对路径
          const relativePath = join(basename(imagesDir), filename);
          return `![${alt}](${relativePath})`;
        }
        // 被过滤掉的图片，移除占位符
        return '';
      });

      // 清理多余的空行（移除图片后可能产生的连续空行）
      content = content.replace(/\n{3,}/g, '\n\n');
    }

    // 生成 Markdown 内容
    const markdown = `# ${article.title}

> 原文链接: ${article.url}
> 抓取时间: ${new Date().toLocaleString('zh-CN')}

---

${content}
`;

    // 写入文件
    await writeFile(finalPath, markdown, 'utf-8');
    console.log(`✅ 文章已保存到: ${finalPath}`);
    if (imagesDir) {
      console.log(`📁 图片已保存到: ${imagesDir}`);
    }

    return finalPath;
  } catch (error) {
    console.error('❌ 保存文件失败:', error.message);
    throw error;
  }
}

/**
 * 检测是否为主模块（兼容 Windows）
 */
function isMainModuleCheck() {
  try {
    // 方法1: 直接路径比较（Windows 兼容）
    const mainPath = fileURLToPath(import.meta.url);
    const argvPath = process.argv[1];

    // 规范化路径后再比较
    const normalizedMain = mainPath.replace(/\\/g, '/');
    const normalizedArgv = argvPath.replace(/\\/g, '/');

    if (normalizedMain === normalizedArgv) {
      return true;
    }

    // 方法2: 检查是否包含文件名（备用方案）
    const mainFileName = basename(mainPath);
    const argvFileName = basename(argvPath);

    return mainFileName === argvFileName && argvFileName.includes('fetch.js');
  } catch (error) {
    // 如果路径检测失败，回退到简单检查
    return process.argv[1].includes('fetch.js');
  }
}

// 命令行调用
const isMainModule = isMainModuleCheck();

if (isMainModule) {
  const url = process.argv[2];
  const outputPath = process.argv[3]; // 可选的输出路径

  if (!url) {
    console.error('用法: node fetch.js <微信公众号文章URL> [输出路径]');
    console.error('');
    console.error('参数:');
    console.error('  URL          微信公众号文章链接（必填）');
    console.error('  输出路径      保存为 Markdown 文件的路径（可选）');
    console.error('                可以是文件路径或目录，如果是目录则使用文章标题作为文件名');
    console.error('');
    console.error('示例:');
    console.error('  node fetch.js "https://mp.weixin.qq.com/s/xxxxx"');
    console.error('  node fetch.js "https://mp.weixin.qq.com/s/xxxxx" "./articles/my-article.md"');
    console.error('  node fetch.js "https://mp.weixin.qq.com/s/xxxxx" "./articles/"');
    process.exit(1);
  }

  fetchWechatArticle(url, 3, outputPath)
    .then(result => {
      console.log('\n=== 抓取结果 ===');
      console.log('标题:', result.title);
      console.log('URL:', result.url);
      console.log('\n=== 文章内容 ===');
      console.log(result.content);
      console.log('\n✅ 完成！');
    })
    .catch(error => {
      console.error('\n❌ 错误:', error.message);
      process.exit(1);
    });
}

// 导出供其他模块使用
export { fetchWechatArticle };
