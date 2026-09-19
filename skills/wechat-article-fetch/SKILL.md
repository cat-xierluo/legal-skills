---
name: wechat-article-fetch
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.4.0"
description: 抓取微信公众号文章（mp.weixin.qq.com）到本地。当用户发来公众号链接要求"抓取""保存""存下来""归档""留痕""转成 Markdown"时使用。默认双产出：Markdown 整理版（供检索引用）+ HTML 原件保真归档（离线双击可读，供回溯核对）。默认 HTTP 直抓零依赖，失败自动切浏览器兜底。
license: Complete terms in LICENSE.txt
---
# 微信公众号文章抓取工具

## 概述

抓取微信公众号文章到本地，默认一次产出两份：

| 产物 | 用途 | 特点 |
|---|---|---|
| Markdown 整理版 | 检索、引用、下游加工 | 纯文本段落 + 图片本地化，自动过滤小装饰图 |
| HTML 原件 | 保真留痕、回溯核对 | 完整页面 + 全部图片本地化（不过滤），离线双击可读，原外链保留在 `data-src` 备查 |

为什么两份都要：公众号分享链接常带 `tempkey` 临时凭证，过期后打不开；Markdown 整理会丢排版和配图，日后无法回溯核对原文。**原件保真，整理版好用，两者互补不互替。**

抓取引擎：

- **HTTP 直抓**（默认主路线）：微信文章是服务端渲染，正文与图片地址都在初始 HTML 里，直接请求即可。零依赖、速度快。
- **Playwright 浏览器兜底**（`--engine auto` 自动切换）：HTTP 路线失败或页面需要 JS 渲染时启用。

## 使用方法

```bash
# 默认：双产出，保存到 skill 内 archive/<时间戳>_<标题>/
node scripts/fetch.js "https://mp.weixin.qq.com/s/xxxxx"

# 指定输出根目录（文章产物归入其下子目录）
node scripts/fetch.js "https://mp.weixin.qq.com/s/xxxxx" "./articles/"

# 兼容旧用法：直接指定 .md 文件路径（其余产物同目录平铺）
node scripts/fetch.js "https://mp.weixin.qq.com/s/xxxxx" "./articles/my-article.md"

# 只要 Markdown 整理版 / 只要 HTML 原件
node scripts/fetch.js "https://mp.weixin.qq.com/s/xxxxx" --mode markdown
node scripts/fetch.js "https://mp.weixin.qq.com/s/xxxxx" --mode archive

# 强制走浏览器（或只走 HTTP 不装 Playwright）
node scripts/fetch.js "https://mp.weixin.qq.com/s/xxxxx" --engine playwright
node scripts/fetch.js "https://mp.weixin.qq.com/s/xxxxx" --engine http
```

完整参数运行 `node scripts/fetch.js --help` 查看。

### 产物结构

```
archive/<YYYYMMDD_HHMMSS>_<文章标题>/
├── <文章标题>.md            # 整理版（头部注明原文链接与 HTML 原件位置）
├── <文章标题>.html          # 原件（src 已本地化，离线可读）
├── <文章标题>_assets/       # 整理版图片（智能过滤小装饰图）
└── <文章标题>_html_assets/  # 原件图片（全量保真，含小图标）
```

### 编程接口

```javascript
import { fetchWechatArticle } from './scripts/fetch.js';

const report = await fetchWechatArticle("https://mp.weixin.qq.com/s/xxxxx", {
  engine: 'auto',        // 'auto' | 'http' | 'playwright'
  mode: 'both',          // 'both' | 'markdown' | 'archive'
  outputPath: null,      // 输出路径（可选）
  retries: 3             // Playwright 路线重试次数
});
// report: { title, url, engine, md, archive: { htmlPath, images, missing, remoteLeft, failed } }
```

## 抓取后检查（必做，不要跳过）

看脚本输出：

- HTML 原件行首为 `[OK ]` 即归档完整；`[警告]` 时查看"缺失本地图"与"残留外链"两项
- 残留外链只剩微信官方空白占位 `pic_blank.gif` 属正常，可忽略
- Markdown 的图片统计里"失败"应为 0，过滤数是装饰图属正常
- 页面报"该内容已被发布者删除""环境异常"等 → 链接失效，脚本会自动切换引擎重试；两条引擎都失败时不要再盲试链接

## 陷阱与要点

| 坑 | 处理 |
|---|---|
| `tempkey` 链接会过期 | **收到就立刻抓**，不要等"有空再存" |
| 图片真地址在 `data-src` 不在 `src` | `src` 多为 base64 占位；脚本已处理，手工排查时注意 |
| URL 属性里是 `&amp;` 不是 `&` | 解码后才能下载，否则 403；脚本已处理 |
| 图片域名不止 `mmbiz.qpic.cn` | 还有 `mmecoa.qpic.cn` 等，按 `qpic.cn` 后缀识别，别写死子域 |
| `wx_fmt` 参数定扩展名 | 微信图 URL 无 `.jpg` 后缀，靠 `?wx_fmt=jpeg` 推断，PNG 不会存成 jpg 名 |
| svg 小图标看着像 0KB | 原件目录里的几百字节装饰图标不是下载失败，别删（原件全量保真） |
| "环境异常"页 | 引擎自动切换重试；仍失败说明链接失效或需验证 |

## 下游加工建议

抓取完成后，如内容为法律法规、裁判文书等结构化法律文本，可在汇报时**提示用户**：如需进一步格式化整理，可指定相应的格式化技能（若环境中有）继续处理。是否调用、调用哪个技能由用户或上层流程决定——本技能不自动调用、不绑定任何下游技能。

## 注意事项

⚠️ 仅用于个人学习和研究，请遵守网站服务条款
⚠️ 频繁抓取可能被限流，建议控制请求频率
⚠️ 抓取内容版权归原作者所有
⚠️ Playwright 兜底路线首次使用会自动安装 chromium（`npx playwright install chromium`）；HTTP 直抓路线零依赖
