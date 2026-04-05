---
name: github-star-manager
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "0.6.0"
license: MIT
description: GitHub Star 项目管理工具，支持从内容自动发现并 Star 项目，同步追踪更新，生成可视化 Dashboard
---

# GitHub Star 管理器 (GitHub Star Manager)

## 简介
专注于 GitHub Star 项目的更新追踪与同步工具。自动检测您 Star 的项目是否有新版本、新 Release、重要 Commit 变化，并生成结构化的更新报告。

**核心特色**: 提供 HTML 可视化 Dashboard，快速浏览所有 Star 项目。

## 何时使用

本技能在以下场景下触发：

- 用户需要**从内容中自动发现并 Star GitHub 项目**
- 用户需要**追踪 GitHub Star 项目的更新**
- 用户需要**监控依赖库的版本发布**
- 用户需要**查看项目活跃度和健康度**
- 用户需要**管理大量 starred 仓库**
- 用户需要**快速浏览和筛选 Star 项目**
- 用户需要**生成项目的可视化报告**

## 模块说明

本技能包含两个模块：

| 模块 | 触发方式 | 功能 |
|------|----------|------|
| **对话模块** | 对话触发 | 从内容提取项目并 Star |
| **脚本模块** | 命令行/定时任务 | 同步、Dashboard、追踪、批量管理 |

## 核心功能

### 1. 对话模块：自动发现并 Star

从各种内容来源中自动提取 GitHub 仓库引用，并在你的 GitHub 账户上 star 它们。

**支持的触发方式：**
- "分析这篇文章并 star 里面的项目"
- "从这张截图里找 GitHub 项目并 star"
- "Star [内容] 中提到的所有 GitHub 项目"

**工作流程：**

1. **内容提取与上下文分析**
   - 文字/URL：使用 WebFetch 获取文章内容，解析 GitHub URL
   - 截图/图片：使用图片分析 MCP 提取文字并识别项目引用

2. **仓库发现与智能匹配**
   - 直接匹配：内容中找到的完整 GitHub URL
   - 按名称搜索：当只有项目名时使用 `gh search repos`
   - 上下文相关性验证：检查 topics、description、技术栈是否匹配

3. **检查是否已 Star**
   ```bash
   gh api user/starred/owner/repo 2>/dev/null
   ```

4. **Star 仓库**
   ```bash
   gh repo star owner/repo
   ```

5. **生成报告**
   - 新 star 的仓库列表
   - 已 star 的仓库（跳过）
   - 需人工确认的仓库

### 2. 更新追踪
- **版本检测**：检测项目的新 Release 和 Tag
- **活跃度监控**：追踪最近的 Commit 活跃度
- **变更摘要**：使用 AI 总结版本变更内容

### 4. 智能分析
- **项目摘要**：自动生成项目核心功能说明
- **价值评估**：分析项目与您的关注领域匹配度（高/中/低）
- **健康度指标**：项目维护状态、Stars 增长趋势

### 5. HTML 可视化 Dashboard
- **信息密集卡片**：一屏展示更多项目
- **颜色编码状态**：活跃/近期更新/长期未更一目了然
- **筛选与搜索**：按状态、价值、关键词过滤
- **展开详情**：点击卡片查看更多信息

## 依赖

### 系统依赖

| 依赖 | 安装方式 |
|------|----------|
| Python 3.8+ | macOS: `brew install python3`<br>Linux: `sudo apt-get install python3` |

### Python 包

| 包名 | 用途 | 安装命令 |
|------|------|----------|
| `requests` | HTTP 请求，调用 GitHub API | `pip install requests` |
| `python-dotenv` | 从 .env 文件加载配置 | `pip install python-dotenv` |
| `openai` | AI 摘要生成（可选） | `pip install openai` |

### 依赖包文件

```bash
pip install -r assets/requirements.txt
```

## 使用方法

### 1. 环境准备

#### 方式 1：使用 .env 配置文件（推荐）

```bash
# 1. 复制示例配置文件
cp .env.example .env

# 2. 编辑 .env 文件，填入你的 API 密钥
# GITHUB_PAT=ghp_xxxxxxxxxxxxxxxxx
# OPENAI_API_KEY=sk-xxxxxxxxxxxx

# 3. 安装依赖
pip install -r requirements.txt
```

#### 方式 2：环境变量

```bash
# 直接设置环境变量
export GITHUB_PAT="你的_github_pat_token"
export OPENAI_API_KEY="你的_openai_api_key"
```

#### 如何获取 GitHub PAT

1. 访问 https://github.com/settings/tokens
2. 点击 "Generate new token (classic)"
3. 选择权限：
   - `public_repo`（访问公开仓库）
   - 如果需要访问私有 Star，勾选 `repo`
4. 生成后复制 token（只显示一次！）

**Token 作用**：
- 无 Token：60 次/小时请求限制
- 有 Token：5000 次/小时请求限制

### 2. 启动 Dashboard（推荐）
```bash
# 导出数据并打开 Dashboard
python scripts/main.py --export --user 你的用户名 && open dashboard.html
```

**首次使用说明**: 如果 `dashboard.html` 不存在，系统会自动从 `assets/dashboard.example.html` 复制一份。

Dashboard 功能：
- 📊 总览：总项目数、本周活跃数、新版本数
- 🔍 筛选：按状态（活跃/近期更新/长期未更）、价值（高/中）过滤
- 🔎 搜索：按项目名、描述、标签搜索
- 📦 卡片：显示项目名、描述、语言、标签、Stars、更新时间、价值评估
- 🖱️ 点击卡片：展开详细信息（创建时间、Forks、Issues、收藏理由）
- 🔗 快速跳转：点击 GitHub 图标直达项目

### 3. 首次同步（建立基准）
```bash
python scripts/main.py --init --user 你的用户名 --limit 50
```
首次运行会保存所有 Star 的快照作为后续对比基准。

### 4. 检查更新
```bash
python scripts/main.py --check --user 你的用户名
```
对比上次快照，生成更新报告。

### 5. 生成完整报告
```bash
python scripts/main.py --report --user 你的用户名 --days 7
```
生成包含项目摘要和更新状态的完整报告。

### 6. 定期运行（推荐）
```bash
# 每周检查一次
python scripts/main.py --check --user 你的用户名 --weekly
```

## 配置与自定义

### 配置文件

本技能使用以下配置文件：

| 文件 | 用途 |
|------|------|
| `assets/categories.yaml` | 分类定义和关键词规则 |
| `assets/tags.json` | 标签管理和别名配置 |
| `assets/.env.example` | 环境变量模板 |

首次运行时，配置文件会自动复制到 `~/.github-star-tracker/` 目录。

## 适用场景
- **开发者**：及时了解依赖库的版本更新
- **技术爱好者**：跟踪 AI/开源领域的最新动态
- **项目经理**：监控竞品或相关项目的进展

## 与其他技能的区别

| 功能 | github-star-manager | repo-research |
|------|---------------------|---------------|
| 焦点 | Star 项目发现 + 管理 + 追踪 | 单个仓库的深度研究 |
| 输出 | Dashboard + 变更摘要 | 架构分析、代码解读 |
| 用途 | 日常订阅更新 | 一次性深度调研 |

## 参考文档

- [SKILL-GUIDE.md](../../../SKILL-GUIDE.md) - 技能开发指南
- [AGENTS.md](../../../AGENTS.md) - 项目协作规范
