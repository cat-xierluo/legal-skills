---
name: fetch-wechat-article
description: 抓取微信公众号文章内容的工具,使用Playwright headless模式,无弹窗后台抓取,支持动态加载内容,自动提取标题和正文,自动保存为Markdown文件,支持Windows平台
---
# 微信公众号文章抓取工具

## 概述

使用 Playwright 抓取微信公众号文章,后台运行无弹窗,自动处理动态加载,提取干净的文章内容,并支持自动保存为 Markdown 文件。

## 功能特性

- ✅ **无头模式运行**: 默认后台抓取,不弹出浏览器窗口
- ✅ **智能回退机制**: 无头模式失败时自动切换到有头模式
- ✅ **动态内容支持**: 自动等待页面加载完成,处理懒加载图片
- ✅ **自动保存为 Markdown**: 支持将抓取结果保存为格式化的 Markdown 文件
- ✅ **内容清洗**: 移除HTML标签,保留段落结构,输出纯文本
- ✅ **自动重试**: 失败时自动重试3次,提高成功率
- ✅ **错误检测**: 识别"参数错误"等异常页面
- ✅ **跨平台支持**: 完全支持 Windows、macOS 和 Linux

## 使用方法

### 在 Claude Code 中调用

```javascript
// 抓取文章（仅返回结果）
const result = await fetchWechatArticle("https://mp.weixin.qq.com/s/xxxxx");

// 抓取文章并自动保存为 Markdown 文件
const result = await fetchWechatArticle(
  "https://mp.weixin.qq.com/s/xxxxx",
  3,           // 重试次数（可选）
  "./output.md" // 保存路径（可选）
);

// 返回格式
{
  title: "文章标题",
  content: "文章正文...",
  url: "文章URL"
}
```

### 命令行调用

```bash
# 基本用法（仅输出到控制台）
node scripts/fetch.js "https://mp.weixin.qq.com/s/xxxxx"

# 保存为指定文件
node scripts/fetch.js "https://mp.weixin.qq.com/s/xxxxx" "./articles/my-article.md"

# 保存到目录（自动使用文章标题作为文件名）
node scripts/fetch.js "https://mp.weixin.qq.com/s/xxxxx" "./articles/"
```

## 输出格式

### 控制台输出

```text
标题: 文章标题

文章正文第一段...

文章正文第二段...
```

### Markdown 文件格式

```markdown
# 文章标题

> 原文链接: https://mp.weixin.qq.com/s/xxxxx
> 抓取时间: 2026-01-21 20:30:00

---

文章正文第一段...

文章正文第二段...
```

## 技术实现

### 依赖要求

- Playwright (`npx playwright install chromium`)
- Node.js >= 14.0.0

### 抓取流程

1. 检测并安装 Playwright（如需要）
2. 启动 Playwright headless 浏览器
3. 设置反检测参数(User-Agent, webdriver隐藏等)
4. 导航到目标URL,等待网络空闲
5. 滚动页面触发懒加载
6. 提取 `#js_content`或 `.rich_media_content`区域
7. 清理HTML标签,保留段落结构
8. 返回标题和纯文本内容
9. **如果指定了保存路径,自动保存为 Markdown 文件**
10. **如果无头模式失败,自动回退到有头模式重试**

### 错误处理

- 自动重试3次,每次失败后等待3秒
- **无头模式失败后自动回退到有头模式**
- 检测错误页面(参数错误、访问异常)
- 超时设置30秒
- **Windows 平台特殊处理（路径、命令格式）**

### 跨平台兼容性

- **Windows**: 自动检测并使用 `cmd.exe` 运行 npx 命令
- **macOS/Linux**: 直接使用 npx 命令
- **路径处理**: 自动规范化路径分隔符
- **文件名处理**: 自动移除 Windows 非法字符

## 适用场景

- 内容转换工具的输入源
- 文章分析和处理
- 自动化内容抓取
- 批量文章下载
- **文章归档和本地保存**
- **Markdown 格式转换**

## 使用示例

### 示例 1: 批量抓取并保存

```javascript
const urls = [
  "https://mp.weixin.qq.com/s/xxxx1",
  "https://mp.weixin.qq.com/s/xxxx2",
  "https://mp.weixin.qq.com/s/xxxx3"
];

for (const url of urls) {
  const result = await fetchWechatArticle(url, 3, "./articles/");
  console.log(`已保存: ${result.title}`);
}
```

### 示例 2: 在 Claude Code 中直接使用

```text
请帮我抓取这个微信公众号文章并保存为 Markdown 文件:
https://mp.weixin.qq.com/s/xxxxx
```

## 注意事项

⚠️ 仅用于个人学习和研究,请遵守网站服务条款
⚠️ 频繁抓取可能被限流,建议控制请求频率
⚠️ 抓取的内容版权归原作者所有
⚠️ **有头模式会弹出浏览器窗口,可能干扰工作流程**
⚠️ **Windows 用户首次使用需要安装 Playwright（会自动安装）**
