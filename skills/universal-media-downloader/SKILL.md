---
name: universal-media-downloader
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "0.5.1"
description: 输入各类视频网站/播客平台链接后，自动下载对应媒体文件并交付给用户。优先使用 yt-dlp 覆盖抖音(Douyin)、B站(Bilibili)、YouTube 等常见视频网站，也可用于可直接暴露音频地址的播客平台（如小宇宙单集链接）。当遇到 403/登录/年龄或地区限制时，支持使用 cookies.txt 重试；对于可能存在 DRM/加密或条款限制的平台（例如部分 Spotify 内容），应提示用户仅下载其有权保存的内容，并在不可下载时建议改用官方离线/导出渠道或提供原始 RSS/直链。抖音视频在 yt-dlp 撞签名墙（"Fresh cookies needed"）时自动三级 fallback：无登录直连 aweme.snssdk.com/v1/play → 本机浏览器游客 cookie（无需登录抖音）重跑 yt-dlp，全程无感；抖音图文笔记暂不支持自动下载，需手动处理。
license: MIT
---

# Universal Media Downloader（通用视频/播客下载）

## 适用范围

**优先覆盖（通常可直接用）**
- **抖音视频**：`douyin.com`、`v.douyin.com` 等视频链接
- **抖音图文笔记**：暂不支持自动下载（反爬限制），需手动截图
- **B站**：`bilibili.com`、`b23.tv` 等
- **YouTube**：`youtube.com`、`youtu.be`
- 以及其它 **yt-dlp 支持的网站**（数量很多）

**播客平台**
- **小宇宙（单集/节目页）**：多数情况下可直接下载音频（yt-dlp 通常能用）
- 其它播客平台：如果页面可解析出音频直链，通常也能下载

> 合规提示：仅用于下载你**有权保存**的内容（例如你自己上传/拥有版权/获得授权/平台允许离线的内容）。遇到 DRM/加密或平台限制时，不要尝试绕过。

## 快速开始

### 1）下载视频（默认）

- 命令：
  - `python scripts/download_media.py "<URL>"`

- 默认保存目录：
  - 用户主目录下的 `~/Downloads/`（不再自包含，方便日常访问；见 DEC-004）
  - 可通过 `--out-dir` 参数自定义输出路径

### 2）只下载音频（适合播客 / 只想要 MP3）

- 命令：
  - `python scripts/download_media.py --audio-only --audio-format mp3 "<URL>"`

### 3）遇到 403 / 需要登录 / 风控拦截：用 cookies 重试

**更省事（推荐）——直接读浏览器 cookies：**

- 用户已在浏览器（Chrome/Firefox/Safari/Edge）登录过该站点的话，直接指定浏览器，免手动导出：
  - `python scripts/download_media.py --cookies-from-browser chrome "<URL>"`
  - 适用：B站 412、YouTube 年龄限制、抖音带登录态等

**或手动导出 cookies.txt（Netscape 格式）：**

- 让用户导出 `cookies.txt`，然后重试：
  - `python scripts/download_media.py --cookies "/path/to/cookies.txt" "<URL>"`

> `--cookies` 与 `--cookies-from-browser` 互斥，二选一。抖音视频无需手动传 cookie——脚本会自动走三级 fallback（见下文「平台差异」），其中最后一环就是自动带本机浏览器游客 cookie 重试（无需登录抖音）。

### 4）需要代理（可选）

- 例如：
  - `--proxy "socks5://127.0.0.1:7890"`

### 5）指定下载路径

- 用户可通过自然语言指定保存位置，AI 应自动转换为 `--out-dir` 参数
- 示例：
  - 用户说"下载到桌面" → `--out-dir ~/Desktop`
  - 用户说"保存到 Videos/bilibili" → `--out-dir "~/Videos/bilibili"`
  - 用户说"下载到这个文件夹"（指定某路径）→ 使用用户指定的绝对路径
- **注意**：确保目标目录存在，如不存在可自动创建

## 平台差异与限制（重要）

- **YouTube / B站**：
  - 常见失败原因：年龄限制、地区限制、频繁请求触发风控、需要登录
  - 处理方式：cookies、代理、或降低并发/等待后重试
  - YouTube 额外提示：若出现 *Signature solving failed / JS challenge* 警告，可按 yt-dlp 的 EJS 指引启用挑战求解组件（例如加 `--remote-components ejs:github`），或让用户提供 cookies

- **抖音视频（三级自动 fallback，v0.3.0 起 / v0.5.0 增强）**：
  - 抖音 `www.douyin.com` 业务 API 已全上 `a_bogus`/msToken 签名墙，yt-dlp 直接下会报 `Fresh cookies are needed`。
  - 「抖音域名 + 用户未显式传 cookie」且 yt-dlp 失败时，自动按序补救：
    1. **无登录直连**（v0.3.0，仅视频）：短链 → SSR share 页提 `video_id` → `aweme.snssdk.com/aweme/v1/play/` 拿 302 CDN 直链 → 带 referer 下载，无需 cookie/签名。
    2. **浏览器游客 cookie 重试**（v0.5.0，音视频均可）：自动依次从本机 `chrome`、`safari` 读一份**游客 cookie**（`s_v_web_id` 等访问 cookie，**无需登录抖音**）重跑 yt-dlp，即可过 "Fresh cookies are needed" 校验。
  - 边界：仅公开视频；私密/仅好友可见、已删除、异地限制、直播/直播回放、图文笔记均不适用（图文走 `download_douyin_note.py`）。浏览器 cookie 读取失败（如 Chrome 正在运行占用/无该浏览器）时自动换下一个，全失败则回显 yt-dlp 原始报错。
  - 无登录直链有效期约 1-2 小时，过期重跑即可。SSR share 页自 2026-08-30 起已对无 cookie 请求停止渲染 `play_addr`（监控信号 #2 命中，风控返回壳页），当前主力通道是游客 cookie；演进记录见 `references/douyin-nocookie-approach.md`。

- **Spotify**：
  - Spotify 上的内容可能存在 DRM、账号权限/订阅限制，且“下载”可能违反平台条款。
  - 本 skill **不保证** Spotify 链接一定可下载。
  - 可行替代：
    - 使用官方离线功能（若平台提供）
    - 提供该播客的 **RSS/音频直链**（如果你拥有/可获得），再用本脚本下载

## Bundled scripts

- `scripts/download_media.py`
  - 基于 `yt-dlp` 的通用下载器
  - 输出：成功时最后一行 `SAVED_FILEPATH=...`
  - **AI 使用指引**：当用户指定保存路径时，自动使用 `--out-dir` 参数
  - 参数：
    - `url`（必填）
    - `--audio-only` / `--audio-format`
    - `--subtitles`（可选，自动下载字幕）
    - `--sub-lang`（可选，字幕语言，默认 all）
    - `--cookies`（可选）
    - `--cookies-from-browser`（可选，chrome/firefox/safari/edge，与 `--cookies` 互斥）
    - `--proxy`（可选）
    - `--out-dir`（可选，自定义输出目录）

- `scripts/download_douyin_note.py`
  - 抖音**图文笔记**图片下载器（视频流接口对图文只返回首图，故图文单独走图片提取）
  - 注意：其依赖的旧版 `iteminfo` API 已被抖音加 `encrypt_data_miss` 拦截，当前提取能力有限，必要时手动截图

- `scripts/download_douyin_video_nocookie.py`
  - 抖音**视频**无登录直连下载器（`aweme.snssdk.com/v1/play`，无需 cookie/签名）
  - `download_media.py` 在抖音 yt-dlp 失败时会自动调用它；也可独立使用
  - 输出同样以 `SAVED_FILEPATH=` 结尾，便于下游脚本（cubox/content-manager）解析
  - 参数：`url`（必填）、`--out-dir`、`--ratio`（540p/720p/1080p，默认 540p）、`--out-name`
  - 原理与边界见 `references/douyin-nocookie-approach.md`

## 依赖

### 系统依赖

| 依赖 | 安装方式 |
|------|----------|
| `yt-dlp` | `pip install yt-dlp` |
| `ffmpeg`（可选，用于字幕提取和音频转换） | macOS: `brew install ffmpeg`<br>Linux: `sudo apt-get install ffmpeg` |
| `aria2c`（可选，抖音 fallback 大文件多线程加速 + 断点续传；未安装自动回退单线程） | macOS: `brew install aria2` |

### Python 包

无需额外 Python 依赖，`yt-dlp` 已包含所需库。
抖音相关脚本（`download_douyin_*.py`）额外依赖 `requests`（`pip install requests`）。
