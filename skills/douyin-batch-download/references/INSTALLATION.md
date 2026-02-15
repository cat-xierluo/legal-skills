# 安装指南

本技能依赖以下环境和软件包。

## 系统依赖

| 依赖 | 安装方式 |
|:-----|:---------|
| Chrome/Chromium | [下载地址](https://www.google.com/chrome/) |
| ffmpeg | macOS: `brew install ffmpeg` / Ubuntu: `sudo apt install ffmpeg` |

**ffmpeg** 用于视频压缩功能，如仅需下载功能可不安装。

## Python 包

| 包名 | 用途 | 安装命令 |
|------|------|----------|
| `f2` | 抖音视频下载框架 | `pip install f2` |
| `playwright` | 浏览器自动化（扫码登录） | `pip install playwright` |
| `pyyaml` | YAML 配置文件解析 | `pip install pyyaml` |
| `httpx` | 异步 HTTP 客户端 | `pip install httpx` |
| `aiofiles` | 异步文件操作 | `pip install aiofiles` |

## 快速安装

```bash
# 1. 安装 Python 依赖
pip install f2 playwright pyyaml httpx aiofiles

# 2. 安装 Playwright 浏览器
playwright install chromium
```

## Playwright 浏览器要求

扫码登录功能需要 Chromium 浏览器：

```bash
# 查看已安装的浏览器
playwright --version

# 安装/重新安装 Chromium
playwright install chromium
```
