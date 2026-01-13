---
name: fetch-wechat-article
description: 抓取微信公众号文章内容的工具,使用Playwright headless模式,无弹窗后台抓取,支持动态加载内容,自动提取标题和正文,返回纯文本格式
---
# 微信公众号文章抓取工具

## 概述

使用 Playwright headless 模式抓取微信公众号文章,后台运行无弹窗,自动处理动态加载,提取干净的文章内容。

## 功能特性

- ✅ **无头模式运行**: 后台抓取,不弹出浏览器窗口
- ✅ **动态内容支持**: 自动等待页面加载完成,处理懒加载图片
- ✅ **内容清洗**: 移除HTML标签,保留段落结构,输出纯文本
- ✅ **自动重试**: 失败时自动重试3次,提高成功率
- ✅ **错误检测**: 识别"参数错误"等异常页面

## 使用方法

### 在Claude Code中调用

```javascript
// 抓取文章
const result = await fetchWechatArticle("https://mp.weixin.qq.com/s/xxxxx");

// 返回格式
{
  title: "文章标题",
  content: "文章正文...",
  url: "文章URL"
}
```

### 命令行调用

```bash
cd .claude/skills/fetch-wechat-article
node scripts/fetch.js "https://mp.weixin.qq.com/s/xxxxx"
```

## 输出格式

抓取的文章会被清洗为纯文本格式:

```
标题: 文章标题

文章正文第一段...

文章正文第二段...
```

## 技术实现

### 依赖要求

- Playwright (`npx playwright install chromium`)
- Node.js >= 14.0.0

### 抓取流程

1. 启动 Playwright headless 浏览器
2. 设置反检测参数(User-Agent, webdriver隐藏等)
3. 导航到目标URL,等待网络空闲
4. 滚动页面触发懒加载
5. 提取 `#js_content`或 `.rich_media_content`区域
6. 清理HTML标签,保留段落结构
7. 返回标题和纯文本内容

### 错误处理

- 自动重试3次,每次失败后等待3秒
- 检测错误页面(参数错误、访问异常)
- 超时设置30秒

## 适用场景

- 内容转换工具的输入源
- 文章分析和处理
- 自动化内容抓取
- 批量文章下载

## 注意事项

⚠️ 仅用于个人学习和研究,请遵守网站服务条款
⚠️ 频繁抓取可能被限流,建议控制请求频率
⚠️ 抓取的内容版权归原作者所有
