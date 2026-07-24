---
name: patent-download
description: 专利 PDF 批量下载工具。当用户需要下载专利全文 PDF、查询专利信息、批量导出专利文件时使用。支持多平台（Google Patents 优先），自动处理申请号和公告号格式。
version: "2.6.0"
license: MIT
author: 杨卫薪律师（微信 ywxlaw）
homepage: https://github.com/cat-xierluo/legal-skills
---
# patent-download - 专利下载工具

根据专利号从多个平台下载专利文本（PDF / 摘要 / 全文）。

## 何时用 / 何时不用

**用**：下载专利全文 PDF、批量导出专利文件、查询专利基本信息。
**不用**：专利侵权比对 / 权利要求分析 / 有效性核查 → 用 `patent-analysis`；法条与案例检索 → 用 `yuandian-law-search`。

## 推荐通道

Google Patents（API、免费免登录）为首选，度衍专利（浏览器）为备选。各平台实测状态、推荐度与接入方式见 `references/platform-status.md`。

## 专利号格式（关键）

用户给的往往是**申请号**（如 `202421964517.8`），Google Patents 用**公告号**（如 `CN223081266U`）索引。两者无数学对应关系，`google_patents.py` 会尝试自动匹配但不保证成功。

完整的申请号/公告号结构、种类代码（A/B/U/S）、发明 A vs B 区别、默认下载规则见 `references/patent-number-formats.md`。

## 使用方法

### 统一入口（推荐）

```bash
# 进入脚本目录（相对 skill 根）
cd scripts

# 查看支持的平台及状态
python cli.py --list

# Google Patents 下载（推荐，免费免登录）
python cli.py google CN223081266U
python cli.py google 202421964517.8      # 申请号自动匹配

# 仅查询专利信息，不下载
python cli.py google CN223081266U --info

# 度衍浏览器自动化（账号自动从环境变量读取）
python cli.py uyanip CN223081266U -m browser

# 批量下载
python cli.py google CN223081266U CN118198150A CN118198150B
```

### 直接调用平台脚本

```bash
python platforms/google_patents.py CN223081266U
python platforms/google_patents.py 202421964517.8 -o ~/Downloads
python platforms/uyanip.py 2024214535561
```

## 凭证（环境变量，公开发布版）

各平台账号通过**环境变量**配置，代码不硬编码、仓库不存储任何账号密码。

命名：`PATENT_<平台>_USERNAME` / `PATENT_<平台>_PASSWORD`（如 `PATENT_UYANIP_USERNAME`）。

配置流程：
1. `cp config/.env.example config/.env`
2. 编辑 `config/.env`，填入你注册的账号（已 .gitignore，不入库）
3. 账号自动从环境变量 / `.env` 加载（`scripts/platforms/_creds.py`，无需额外依赖）
4. **安全自检**：`python scripts/platforms/_creds.py` —— 检查 `.env` 是否被误提交到 git，并显示各平台账号是否就绪（不打印密码）

各平台账号获取方式与 **ToS 合规提示**见 `references/accounts-setup.md`。Google Patents 与 CNIPA epub 为公开免登录，无需配置。

## 参数说明

| 参数 | 说明 |
|------|------|
| `-m, --method` | 下载方式：api 或 browser |
| `-u, --username` | 用户名（默认从环境变量读） |
| `-p, --password` | 密码（默认从环境变量读） |
| `-o, --output` | 输出目录（默认当前目录） |
| `--headless` | 无头模式（浏览器方式） |
| `--info` | 仅查询信息，不下载（仅 Google Patents） |

## 依赖

### 开箱即用（无需安装）

- **Google Patents 信息查询**：`python cli.py google <号> --info` 仅用标准库，零依赖
- **凭证自检**：`python cli.py --list`、`python platforms/_creds.py` 零依赖
- 缺少下述可选依赖时，脚本会打印清晰提示并退出，不会抛晦涩的 `ImportError`

### 需安装依赖

首次下载前按所用通道安装（统一命令：`pip install -r scripts/requirements.txt`）：

| 通道 | 依赖 | 安装命令 |
|------|------|----------|
| Google Patents 下载（推荐） | `patent-downloader` | `pip install patent-downloader` |
| 度衍/粤港澳/PSS 浏览器自动化 | `playwright` + 浏览器 | `pip install playwright && playwright install chromium` |
| PatentStar/epub API 等 | `requests` | `pip install requests` |

一条命令装全部：`pip install -r scripts/requirements.txt`。

## 目录结构

```
patent-download/
├── SKILL.md
├── LICENSE.txt                    # MIT
├── CHANGELOG.md
├── config/
│   ├── .env.example               # 账号模板（入库，复制为 .env 填写）
│   └── platforms.yaml             # 平台元数据（无账号）
├── references/
│   ├── accounts-setup.md          # 各平台账号获取 + ToS 合规
│   ├── examples.md                # 使用示例与故障排除
│   ├── patent-number-formats.md   # 申请号/公告号格式详解
│   └── platform-status.md         # 各平台实测状态与详情
└── scripts/
    ├── cli.py                     # 统一入口 ⭐
    ├── patent-download.sh         # wrapper（google 走 cli，其他走 download.py）
    ├── download.py                # 旧入口（epub 兼容）
    ├── requirements.txt
    └── platforms/                 # 各平台独立脚本
        ├── _creds.py              # 共享凭证加载（ENV + .env）
        ├── google_patents.py      # Google Patents ⭐推荐
        ├── uyanip.py              # 度衍专利
        ├── patentstar.py          # 专利之星 API（失效）
        ├── patentstar_browser.py
        ├── gpic.py                # 粤粤港澳平台
        ├── pss.py                 # PSS 系统
        └── epub.py                # 专利公布公告
```

## 更多

- 使用示例与故障排除：`references/examples.md`
- 变更历史：`CHANGELOG.md`
