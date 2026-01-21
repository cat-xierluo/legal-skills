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
import { writeFile, mkdir, stat } from 'fs/promises';
import { existsSync } from 'fs';

// 获取当前文件路径（兼容 Windows）
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// 检测平台
const isWindows = process.platform === 'win32';

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

    // 提取文章内容
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

      // 清理HTML,保留段落结构
      let cleanText = rawHtml
        // 段落标签替换为双换行
        .replace(/<p[^>]*>/gi, '\n\n')
        .replace(/<\/p>/gi, '')
        // br标签替换为换行
        .replace(/<br\s*\/?>/gi, '\n')
        // 移除所有HTML标签
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
        url: window.location.href
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
 * 将抓取的文章保存为 Markdown 文件
 * @param {Object} article - 文章对象 {title, content, url}
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

    // 生成 Markdown 内容
    const markdown = `# ${article.title}

> 原文链接: ${article.url}
> 抓取时间: ${new Date().toLocaleString('zh-CN')}

---

${article.content}
`;

    // 写入文件
    await writeFile(finalPath, markdown, 'utf-8');
    console.log(`✅ 文章已保存到: ${finalPath}`);

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
