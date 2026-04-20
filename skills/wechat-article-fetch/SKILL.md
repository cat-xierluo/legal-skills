---
name: wechat-article-fetch
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.3.1"
description: 抓取微信公众号文章内容，使用 Playwright headless 模式无弹窗后台抓取，支持动态加载内容，自动提取标题和正文并保存为 Markdown 文件。本技能应在用户需要抓取微信公众号文章内容时使用。检测到法律内容且项目中存在 legal-text-format 时自动链式调用格式化。默认保存到 skill 内部 archive 目录。
license: Complete terms in LICENSE.txt
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
- ✅ **法律内容自动格式化**: 检测到法律内容时自动链式调用 legal-text-format（强制执行协议）
- ✅ **图片下载**: 自动下载文章中的所有图片到本地
- ✅ **智能图片筛选**: 自动过滤小的装饰性图片（如社交媒体按钮、表情符号）
- ✅ **图片位置保持**: 保留图片在原文档中的位置
- ✅ **自动文件命名**: 根据文章标题生成文件名和资源文件夹

## 抓取后法律格式化协议（强制执行）

**本节为必须遵守的执行指令，而非可选建议。**

### 法律内容判定清单

完成抓取后，你必须立即按以下清单判定内容是否为法律文本。**满足任意一条即为法律内容**：

- **标题关键词**：案例、裁判、判决、法规、条例、规定、办法、解释、通知、意见、规则、最高法、最高检、法院、检察院、司法解释
- **内容特征**：包含案号（如 `(202X)XX民初XX号`）、法院名称、法律条文引用（如 `第X条第X款`）
- **结构特征**：符合法律案例典型结构（基本案情、裁判结果、典型意义等）

### 自动链式调用条件

**以下两个条件同时满足时，必须立即调用 `legal-text-format`，不询问用户确认**：

1. 上方判定结果为"是法律内容"
2. 本项目中存在 `skills/legal-text-format/SKILL.md`（通过 `ls skills/legal-text-format/SKILL.md` 或等效方式检查）

### 链式调用步骤

条件满足时，按以下顺序执行：

1. 完成抓取，将 Markdown 保存到本技能 `archive/` 目录
2. 按判定清单判断内容类型
3. 如果是法律内容，检查 `skills/legal-text-format/SKILL.md` 是否存在
4. **如果存在，立即调用 `legal-text-format` 技能**，传入抓取到的文件路径作为输入
5. 使用下方对应模板汇报最终结果

### 降级处理

如果 `legal-text-format` 不存在：正常结束抓取流程，在汇报中附加提示：

> 已检测到法律内容，但项目中未安装 `legal-text-format` 格式化技能。如需自动格式化，可通过 skill-manager 安装。

### 结果存储

- **抓取的原始内容**：保存在本技能的 `archive/` 目录（默认行为不变）
- **格式化后的内容**：保存在 `legal-text-format` 的 `archive/` 目录（由该技能自行管理）

### 汇报模板

**仅抓取**（非法律内容，或 legal-text-format 未安装）：
> 已完成抓取：{标题}
> 保存位置：{文件路径}

**抓取 + 格式化**（法律内容且 legal-text-format 已安装）：
> 已完成抓取 + 法律格式化：{标题}
> 原始内容：{wechat-article-fetch archive 路径}
> 格式化内容：{legal-text-format archive 路径}
> 文本类型：{法律条文/法律案例}

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

![图片描述](文章标题_assets/image_xxx_0.jpg)

文章正文第二段...
```

### 文件结构

当文章包含图片时，会自动生成以下文件结构：

```
输出目录/
├── 文章标题.md              # Markdown 文件
└── 文章标题_assets/         # 图片资源文件夹
    ├── image_xxx_0.jpg
    ├── image_xxx_1.jpg
    └── ...
```

### 图片筛选

默认启用智能图片筛选，自动过滤小于 15KB 的装饰性图片（如社交媒体按钮、表情符号等）。

可以在 `scripts/fetch.js` 中修改筛选配置：

```javascript
const IMAGE_FILTER_CONFIG = {
  minFileSize: 15 * 1024,  // 最小文件大小（字节）
  enabled: true            // 是否启用筛选
};
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
- **法律文档自动格式化**（检测到法律内容时）
- **图文文章完整保存**（包含图片的离线归档）
- **图片资源管理**（自动下载并组织文章中的图片）

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
