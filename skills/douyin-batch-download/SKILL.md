---
name: douyin-batch-download
description: 抖音视频批量下载工具 - 基于 F2 框架实现高效、增量的视频下载功能。支持单个/批量博主下载，自动 Cookie 管理，差量更新机制。本技能应在用户需要批量下载特定博主视频、服务器部署自动化下载、或定期更新视频库时使用。
license: MIT
---

# 抖音视频批量下载

本技能基于 **F2 框架**实现抖音视频批量下载，提供高效、稳定的批量下载能力。

## 功能概述

- **单个博主下载** - 输入主页链接或 ID，下载全部或指定数量
- **批量下载** - 一次指定多个博主，批量处理
- **增量下载** - 自动跳过已下载的视频（按 aweme_id 判断）
- **Cookie 管理** - 优先从浏览器自动读取，失败则提示手动配置
- **关注列表管理** - 维护 following.json 记录已处理的博主
- **差量更新** - 支持只下载主页有但本地没有的视频
- **目录兼容** - 用数字 ID + 三层结构（视频/封面/转录文字）
- **视频压缩** - 使用 ffmpeg 压缩视频，节省存储空间
- **视频元数据** - 抓取并保存视频统计数据（点赞、评论、收藏、分享数）
- **数据可视化** - Web 界面展示博主和视频的统计信息，支持排序和筛选

## 使用场景

- 服务器批量下载：部署在专用服务器上，定时批量抓取特定博主视频
- 定期更新视频库：自动检测新视频，只下载缺失部分
- 备份与迁移：视频文件分类存储，便于备份和后续处理
- 内容分析：基于视频统计数据（点赞、评论、收藏）进行博主内容分析

## 视频元数据

下载视频时，系统会自动提取并保存以下数据：

| 字段 | 说明 |
|------|------|
| `aweme_id` | 视频唯一 ID |
| `uid` | 作者 UID |
| `desc` | 视频描述/文案 |
| `create_time` | 发布时间 |
| `duration` | 视频时长 |
| `digg_count` | 点赞数 |
| `comment_count` | 评论数 |
| `collect_count` | 收藏数 |
| `share_count` | 分享数 |

数据存储在 `douyin_users.db` 的 `video_metadata` 表中。

### 手动提取/更新元数据

```bash
# 扫描本地视频并提取元数据（基本信息）
python scripts/extract-metadata.py

# 查看统计摘要
python scripts/extract-metadata.py --stats
```

> ⚠️ **注意**: `--fetch` 选项已废弃。推荐使用 `download-v2.py` 重新下载视频，会自动保存统计数据。

## 快速开始

```bash
# 创建配置
mkdir -p config
cp config/config.yaml.example config/config.yaml

# 编辑配置（填写 Cookie）
${EDITOR:-nano} config/config.yaml

# 单个下载（推荐）
python scripts/download-v2.py "https://www.douyin.com/user/MS4wLjABAAAA..."

# 批量下载
python scripts/batch-download.py --all

# 交互式选择博主下载
python scripts/batch-download.py

# 采样下载（每个博主1个视频，快速更新数据）
python scripts/batch-download.py --sample

# 生成 Web 界面数据
python scripts/generate-data.py

# 查看 Web 界面
open downloads/index.html
```

## 推荐工作流

```
1. 添加博主 → python scripts/manage-following.py --batch
2. 批量下载 → python scripts/batch-download.py --all
3. 查看数据 → open downloads/index.html
```

下载时自动保存：
- ✅ 视频文件
- ✅ 点赞、评论、收藏、分享数
- ✅ 视频描述、发布时间、时长

## 目录结构

```
skills/douyin-batch-download/
├── SKILL.md                  # 本文件
├── references/
│   ├── INSTALLATION.md        # 详细安装依赖说明
│   └── USAGE.md              # 详细使用说明
├── scripts/
│   ├── download-v2.py        # ✅ 推荐下载脚本（自动保存统计数据）
│   ├── batch-download.py     # 批量下载入口
│   ├── download.py           # ⚠️ 旧版下载脚本（已废弃）
│   ├── manage-following.py   # 关注列表管理（添加/删除/搜索）
│   ├── sync-following.py     # 从 F2 数据库同步 following.json
│   ├── compress.py           # 视频压缩脚本
│   ├── extract-metadata.py   # 视频元数据提取
│   ├── generate-data.py      # 生成 Web 界面数据文件
│   ├── following.py          # following.json 操作库
│   └── login.py              # 扫码登录脚本
├── config/
│   ├── config.yaml.example  # 配置模板
│   └── following.json       # 关注列表（已下载的博主）
├── downloads/
│   ├── {uid}/               # 按博主 UID 分类的视频目录
│   ├── data.js              # Web 界面数据文件
│   └── index.html           # Web 管理界面
└── douyin_users.db          # SQLite 数据库（用户信息 + 视频元数据）
```

## 依赖

### 系统依赖

| 依赖 | 安装方式 |
|:-----|:---------|
| Chrome/Chromium | [下载地址](https://www.google.com/chrome/) |
| ffmpeg | macOS: `brew install ffmpeg` / Ubuntu: `sudo apt install ffmpeg` |

**ffmpeg** 用于视频压缩功能，如仅需下载功能可不安装。

### Python 包

| 包名 | 用途 |
|------|------|----------|
| `f2` | 抖音视频下载框架 |
| `playwright` | 浏览器自动化（扫码登录） |
| `pyyaml` | YAML 配置文件解析 |
| `httpx` | 异步 HTTP 客户端 |
| `aiofiles` | 异步文件操作 |

**详细安装说明**：见 [references/INSTALLATION.md](references/INSTALLATION.md)

**详细使用说明**：见 [references/USAGE.md](references/USAGE.md)

## 参考资源

- F2 官方文档：https://f2.wiki
- F2 GitHub：https://github.com/Johnserf-Seed/f2

## 与其他技能配合

### FunASR 语音转文字

下载的视频可以使用 [funasr-transcribe](../../skills/funasr-transcribe/) 技能将视频转录为带时间戳的 Markdown 文件。

**配合方式**：先使用抖音下载技能获取视频，再使用 FunASR 技能进行转录。两个技能独立运行，可根据需要灵活组合使用。
