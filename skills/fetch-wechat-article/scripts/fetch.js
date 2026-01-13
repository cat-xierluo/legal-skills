#!/usr/bin/env node

/**
 * 微信公众号文章抓取脚本
 * 使用 Playwright headless 模式,无弹窗后台抓取
 * 自动检测并安装 Playwright
 *
 * 用法: node fetch.js <URL>
 */

import { spawn } from 'child_process';

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
      // 安装 playwright
      const install = spawn('npx', ['-y', 'playwright', 'install', 'chromium'], {
        stdio: 'inherit',
        shell: true
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
    });
  }
}

async function fetchWechatArticle(url, retries = 3) {
  // 确保 Playwright 已安装
  await ensurePlaywright();

  // 动态导入 playwright
  const { chromium } = await import('playwright');

  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      console.log(`尝试 ${attempt}/${retries}: 抓取 ${url}`);
      const result = await attemptFetch(chromium, url);
      console.log('✅ 抓取成功！');
      return result;
    } catch (error) {
      console.error(`❌ 尝试 ${attempt} 失败:`, error.message);
      if (attempt === retries) {
        throw error;
      }
      console.log(`⏳ 等待 3 秒后重试...`);
      await new Promise(resolve => setTimeout(resolve, 3000));
    }
  }
}

async function attemptFetch(chromium, url) {
  const browser = await chromium.launch({
    headless: true,
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

// 命令行调用
const isMainModule = import.meta.url === `file://${process.argv[1]}` ||
                    import.meta.url.startsWith('file://') && process.argv[1].includes('fetch.js');

if (isMainModule) {
  const url = process.argv[2];
  if (!url) {
    console.error('用法: node fetch.js <微信公众号文章URL>');
    console.error('示例: node fetch.js "https://mp.weixin.qq.com/s/xxxxx"');
    process.exit(1);
  }

  fetchWechatArticle(url)
    .then(result => {
      console.log('\n=== 抓取结果 ===');
      console.log('标题:', result.title);
      console.log('URL:', result.url);
      console.log('\n=== 文章内容 ===');
      console.log(result.content);
    })
    .catch(error => {
      console.error('错误:', error);
      process.exit(1);
    });
}

// 导出供其他模块使用
export { fetchWechatArticle };
