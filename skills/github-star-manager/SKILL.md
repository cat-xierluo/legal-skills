---
name: github-star-manager
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "0.6.6"
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
   - 评论区/回复也是提取源：作者在评论区亲授的 `owner/repo` 全称是最高优先级证据，优先于一切启发式消歧

2. **仓库发现与智能匹配**
   - 直接匹配：内容中找到的完整 GitHub URL
   - 半截 URL 补全：owner 确定而 name 截断（如 `mcncarl/jianyi…`）时，列该 owner 名下仓库（`gh api users/OWNER/repos`），按名称前缀 + description 语义匹配补全（实测：jianyi…→jianying-headless，yichen…→yichen-skills）
   - owner 拼写修正：截图直读的 owner 404 时先怀疑 OCR 误读而非仓库不存在——按 repo 名搜索锁定真身，用星数量级与截图侧栏数字互证（实测：截图误读 `webadderalorg`→真身 `webadderallorg/Recordly`，30.9k⭐ 与侧栏 20.1k 同量级确认）
   - 社交账号名 ↔ GitHub owner 互证：博主昵称与 owner 名常有派生关系，可作中优先级佐证（实测：抖音"耳朵"→erduo1998-cell、"姚老师"→yaojingang、"文森特"→Vincentwei1021），但不单独定论
   - 改名仓库识别：内容中的旧名 404 时，查 `gh api repos/旧名` 是否返回 301/新 full_name——GitHub API 对改名仓库自动重定向，返回的 full_name 即新名；若新仓库已在库则视为同一项目跳过（实测：erduo-hyperframes-broll → erduo-broll-loop-engineering）
   - 按名称搜索：当只有项目名时使用 `gh search repos`
   - 同名候选消歧（社交内容常只给项目名，同名候选多为 fork/搬运/衍生项目）。**证据优先级：来源亲授全称 > 语义比对 > 排除规则 > 版本轨迹；Star 数量级只是参考信号，永不单独定论**——实测反例：taste-skill 同名的 Leonxlnx 版 8.9 万⭐比目标 senlindesign 版（366⭐）高两个数量级，靠语义（"Reverse-engineer any website's design taste" 与帖内 tastelab 页面吻合）+ 作者评论区亲授全称才锁定 senlindesign 版：
     1. **来源亲授证据**：作者/评论区给出的 owner/repo 全称直接采信，跳过其余消歧
     2. **语义锚定**：不要只比对项目名文字——把内容展示的功能场景与各候选仓库 description 逐一比对（如"单色印刷审美"帖 ↔ "One-ink editorial print"；"英文内嵌字幕视频截图" ↔ "保留视频内嵌字幕，精确取帧生成长图"；"逆向网站设计品味" ↔ "reverse-engineer any website's design taste"）
     3. **衍生仓库排除**：name 带 `-lite`/`-editor`/`-skills` 等后缀、description 自述"基于上游/fork 适配/补原仓库不做的半边"的直接排除
     4. **版本交叉核对**：内容提到版本号（如"升级到 2.0"）时，查候选仓库 releases/tags，原仓库应存在对应版本轨迹
     5. **Star 数量级（仅参考）**：多数情况下原仓库比 fork/搬运高 1–2 个数量级（mono-color-skill 3250 vs 0~3；native-subtitle-quote-image 795 vs 5/7），但同名高星同类项目随时可能推翻它——高星候选与亲授/语义证据冲突时，以后者为准
   - 候选仍无法唯一确定时：不凭猜测 star，列出候选与判断依据请用户确认
   - 上下文相关性验证：检查 topics、description、技术栈是否匹配

3. **检查是否已 Star**
   ```bash
   gh api user/starred/owner/repo 2>/dev/null
   ```
   HTTP 204 = 已 star，404 = 未 star。

4. **Star 仓库**
   `gh repo star` 子命令在部分 gh 版本不存在（如 2.83.0 报 unknown command），统一用 API，幂等且跨版本可用：
   ```bash
   gh api -X PUT user/starred/owner/repo
   ```
   成功后用第 3 步的 GET 回读，204 才算完成，不要以 PUT 退出码为准。
   批量任务（一次内容提取出多个仓库）时循环执行"查重→star→回读"，单个仓库失败不阻断其余，最后按第 5 步汇总成功/跳过/失败。

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
cp assets/.env.example .env

# 2. 编辑 .env 文件，填入你的 API 密钥
# GITHUB_PAT=ghp_xxxxxxxxxxxxxxxxx
# OPENAI_API_KEY=sk-xxxxxxxxxxxx

# 3. 安装依赖
pip install -r assets/requirements.txt
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
# 产物固定落在技能目录 output/ 下（绝对路径，与当前工作目录无关），脚本结束时会打印完整路径
python scripts/main.py --export --user 你的用户名
open skills/github-star-manager/output/dashboard.html
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

首次运行时，配置文件会自动复制到 `~/.github-star-manager/` 目录。

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

## 汇报格式规范

当 GitHub Star 同步任务需要汇报时，使用以下**固定格式**：

```
⭐ GitHub Stars 同步报告 — YYYY-MM-DD HH:MM

总项目数: XXX 个（±Y）

---

**🔄 仓库转移**（同一项目，owner/name 变了）
- ~~旧路径~~ → **新路径**（⭐ N）

**➕ 新增 Star (N)**
- 项目名（⭐ N）
  描述（如果有）

**➖ 取消 Star (N)**
- 项目名

---

**📊 汇总**
- 新增: X 个
- 取消: Y 个
- 转移: Z 个
- 当前总数: XXX
```

**规则：**
- **无变化时完全静默**，不发送任何消息
- 新增和取消分开列出，清晰的 emoji 区分
- 仓库转移放在最前面（因为容易被忽略）
- 最后有汇总行，方便快速扫视

## 参考文档

- [SKILL-GUIDE.md](../../../SKILL-GUIDE.md) - 技能开发指南
- [AGENTS.md](../../../AGENTS.md) - 项目协作规范
