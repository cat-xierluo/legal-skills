---
name: universal-media-downloader
description: 输入各类视频网站/播客平台链接后，自动下载对应媒体文件并交付给用户。优先使用 yt-dlp 覆盖抖音(Douyin)、B站(Bilibili)、YouTube 等常见视频网站，也可用于可直接暴露音频地址的播客平台（如小宇宙单集链接）。当遇到 403/登录/年龄或地区限制时，支持使用 cookies.txt 重试；对于可能存在 DRM/加密或条款限制的平台（例如部分 Spotify 内容），应提示用户仅下载其有权保存的内容，并在不可下载时建议改用官方离线/导出渠道或提供原始 RSS/直链。
license: MIT
---

# Universal Media Downloader（通用视频/播客下载）

## 适用范围

**优先覆盖（通常可直接用）**
- **抖音**：`douyin.com`、`v.douyin.com` 等分享/视频链接
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
  - 技能目录下的 `downloads/` 文件夹（自包含）
  - 可通过 `--out-dir` 参数自定义输出路径

### 2）只下载音频（适合播客 / 只想要 MP3）

- 命令：
  - `python scripts/download_media.py --audio-only --audio-format mp3 "<URL>"`

### 3）遇到 403 / 需要登录 / 风控拦截：用 cookies 重试

- 让用户提供浏览器导出的 **Netscape 格式** `cookies.txt`

- 然后重试：
  - `python scripts/download_media.py --cookies "/path/to/cookies.txt" "<URL>"`

### 4）需要代理（可选）

- 例如：
  - `--proxy "socks5://127.0.0.1:7890"`

## 平台差异与限制（重要）

- **YouTube/B站/抖音**：
  - 常见失败原因：年龄限制、地区限制、频繁请求触发风控、需要登录
  - 处理方式：cookies、代理、或降低并发/等待后重试
  - YouTube 额外提示：若出现 *Signature solving failed / JS challenge* 警告，可按 yt-dlp 的 EJS 指引启用挑战求解组件（例如加 `--remote-components ejs:github`），或让用户提供 cookies

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
  - 参数：
    - `url`（必填）
    - `--audio-only` / `--audio-format`
    - `--subtitles`（可选，自动下载字幕）
    - `--sub-lang`（可选，字幕语言，默认 all）
    - `--cookies`（可选）
    - `--proxy`（可选）
    - `--out-dir`（可选）

## 依赖

### 系统依赖

| 依赖 | 安装方式 |
|------|----------|
| `yt-dlp` | `pip install yt-dlp` |
| `ffmpeg`（可选，用于字幕提取和音频转换） | macOS: `brew install ffmpeg`<br>Linux: `sudo apt-get install ffmpeg` |

### Python 包

无需额外 Python 依赖，`yt-dlp` 已包含所需库。
