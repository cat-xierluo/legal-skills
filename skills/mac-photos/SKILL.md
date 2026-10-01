---
name: mac-photos
description: 读取 Mac 照片图库（含 iCloud 同步的 iPhone 照片与截图）：按类型（截图优先）、日期、相簿筛选导出，Vision OCR 全文索引，按内容关键词搜索定位照片并批量导出。当用户要"找手机截图"、"按内容搜相册照片"、"批量导出照片保存"时使用。
license: MIT
version: "1.0.0"
author: 杨卫薪律师（微信ywxlaw）
homepage: https://github.com/cat-xierluo/legal-skills
---

# mac-photos：Mac 相册读取与截图内容检索

把 Mac「照片」图库变成可用命令行检索的资料库：筛选（默认只看截图）→ 导出到本地 → OCR 全文索引 → 按内容关键词搜索 → 命中即导出保存。手机照片经 iCloud 同步进图库后即可被检索，全程本地运行，照片不上传任何外部服务。

## 工作原理

```
照片图库(含 iCloud 同步的 iPhone 截图)
   │  osxphotos 按条件筛选导出（增量，可从 iCloud 补下载原片）
   ▼
~/Pictures/PhotosReader/exports/     ← 原片文件（uuid_原文件名）
~/Pictures/PhotosReader/index.jsonl  ← OCR 全文索引（Apple Vision，本地识别）
   │
   ▼
search "关键词" → 命中照片的日期/上下文/路径 → export 复制保存 / --open 预览
```

## 快速开始

### 第 0 步：开启完全磁盘访问（一次性，必做）

系统设置 → 隐私与安全性 → 完全磁盘访问权限 → 为你运行终端的应用（Terminal / iTerm / ZCode 等）打开开关。未开启时所有读取都会被 macOS 拒绝，`doctor` 会明确指出。

### 第 1 步：安装依赖（一次性）

```bash
bash scripts/setup.sh
# 国内网络慢时：
OSXPHOTOS_PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple bash scripts/setup.sh
```

setup 会创建 venv 安装 osxphotos、用 swiftc 编译 Vision OCR 工具，并自动运行自检。

### 第 2 步：自检

```bash
python3 scripts/photos_read.py doctor
```

五项全 ✅ 即就绪（其中"照片图库读取权限"一项红 = 完全磁盘访问没开）。

### 第 3 步：扫描建索引

```bash
# 只扫截图（默认），从 2026-01-01 起，首次先小批量试跑：
python3 scripts/photos_read.py scan --limit 20

# 全量扫描全部截图（增量，重复执行安全）：
python3 scripts/photos_read.py scan

# 扫全部类型照片（不只截图）：
python3 scripts/photos_read.py scan --all-types
```

### 第 4 步：搜索与导出

```bash
# 按内容搜：多个词默认要求同时出现
python3 scripts/photos_read.py search 违约金
python3 scripts/photos_read.py search 合同 2026-0918
python3 scripts/photos_read.py search 微信 转账 --or      # 任一词命中
python3 scripts/photos_read.py search 起诉状 --open       # QuickLook 逐张预览
python3 scripts/photos_read.py search 调解书 --reveal     # 在 Finder 中定位

# 把命中照片复制出来保存：
python3 scripts/photos_read.py export 违约金 --dest ~/Documents/本案证据
```

## 命令一览

| 命令 | 用途 | 关键参数 |
|------|------|----------|
| `doctor` | 环境自检（依赖/权限/OCR 链路） | `--library` 指定非默认图库 |
| `scan` | 从图库导出并 OCR 建索引（默认仅截图、增量） | `--from-date` `--to-date` `--limit` `--all-types` `--album` `--keyword` `--workers` |
| `search` | 按 OCR 出的文字内容搜索 | 多词默认 AND；`--or` 任一命中；`--open` 预览；`--reveal` Finder 定位；`--json` |
| `list` | 按日期倒序浏览索引 | `--limit N` |
| `export` | 把命中（或 `--uuid`）照片复制到目录 | `--dest`（默认 `./photos-export`） |
| `stats` | 索引统计（数量/日期范围/含文字比例） | — |

## 依赖

### 系统依赖

| 依赖 | 用途 | 安装方式 |
|------|------|----------|
| macOS 13+ | Vision 框架中文识别（zh-Hans 需 rev3） | 系统自带 |
| Xcode Command Line Tools | swiftc 编译 OCR 工具 | `xcode-select --install` |
| 完全磁盘访问权限 | 读取照片图库 | 系统设置 → 隐私与安全性，为终端应用开启 |

### Python 包

| 包名 | 用途 | 安装命令 |
|------|------|----------|
| `osxphotos` | 读取/筛选/导出照片图库（装在独立 venv，主脚本零 import 依赖） | `bash scripts/setup.sh` |

**开箱即用 vs 需安装**：`setup.sh` 跑过一次后全部功能可用；未安装时 `doctor`/`search`/`list`/`stats`（依赖本地索引）仍可运行，`scan` 与图库相关自检会给出安装指引。

## 工作区与数据

- 默认工作区 `~/Pictures/PhotosReader/`（`--workspace` 可改）：`exports/` 存原片副本，`index.jsonl` 存索引；原始照片库只读不写。
- 索引增量：同一张图（uuid 相同、文件大小不变）不重复 OCR；重复 `scan` 只处理新增。
- 删除工作区目录即完全清理，对照片库无影响。

## 常见问题

- **`无权读取照片图库` / `authorization denied`**：完全磁盘访问未开（见第 0 步）。开了仍报错，确认授权对象是实际运行脚本的终端应用。
- **导出慢 / 大量 `download missing`**：iPhone 开了"优化储存空间"，图库只有缩略图，`--download-missing` 正在从 iCloud 拉原片，属正常现象；首次全量扫描建议分批（`--limit` + 重复执行）。
- **搜索不到**：先 `stats` 看索引覆盖范围，`list` 抽查内容；该照片可能未被扫入（日期范围外或非截图类型，加 `--all-types` / 放宽日期）。
- **OCR 漏字**：截图过小或文字过淡时可能漏；`search` 用较短的关键词重试。OCR 质量问题不要修改照片库，仅影响索引，可删工作区重建。
