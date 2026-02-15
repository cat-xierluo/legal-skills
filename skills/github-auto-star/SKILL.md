---
name: github-auto-star
description: "从内容（文章、截图、文字）中自动提取 GitHub 仓库并 star。使用场景：(1) 用户要求分析内容并 star 相关 GitHub 项目，(2) 处理提到工具或库的文章/博客，(3) 分析包含技术引用的截图，(4) 设置定时任务自动发现并 star 仓库。"
license: MIT
---

# 自动 Star GitHub 项目

## 概述

这个 skill 可以从各种内容来源中自动提取 GitHub 仓库引用，并在你的 GitHub 账户上 star 它们。

**支持的触发方式：**
- "分析这篇文章并 star 里面的项目"
- "从这张截图里找 GitHub 项目并 star"
- "Star [内容] 中提到的所有 GitHub 项目"
- 设置自动化定时任务

## 依赖

### 系统依赖

| 依赖 | 安装方式 |
|------|----------|
| GitHub CLI (gh) | macOS: `brew install gh`<br>Linux: `sudo apt install gh` |

### 环境变量

| 变量 | 说明 | 配置方式 |
|------|------|----------|
| `GITHUB_TOKEN` | GitHub Personal Access Token（可选，推荐使用 gh CLI 登录） | 复制 `config/.env.example` 为 `config/.env` 并填入实际值 |

## 前置条件

使用本 skill 前需配置 GitHub 认证。配置步骤见 [github-config.md](references/github-config.md)。

## 工作流程

### 步骤 1：内容提取与上下文分析

从提供的来源提取内容和上下文信息：

**文字/URL：**
- 使用 WebFetch 获取文章内容
- 解析 GitHub URL（github.com/owner/repo）
- 识别项目名、库名、工具名
- **提取上下文**：文章主题、技术领域、功能描述

**截图/图片：**
- 使用图片分析 MCP（用户提供）
- 提取文字并识别项目引用
- **分析图片上下文**：
  - 识别技术领域（如：数据库、AI Agent、前端框架、DevOps 等）
  - 提取功能描述和特性关键词
  - 理解项目用途场景
  - 识别相关技术栈

### 步骤 2：仓库发现与智能匹配

对于每个识别到的项目，结合上下文进行智能匹配：

1. **直接匹配**：内容中找到的完整 GitHub URL，直接使用

2. **按名称搜索**（当只有项目名时）：
   ```bash
   gh search repos "项目名" --limit 10
   ```

3. **上下文相关性验证**（关键步骤）：

   当存在多个同名或相似项目时，必须基于上下文进行匹配：

   - **领域匹配**：检查仓库的 topics、description 是否与内容中的技术领域一致
     - 示例：内容提到"AI Agent"，优先选择 topics 包含 `ai`、`agent`、`llm` 的仓库
     - 示例：内容提到"数据库工具"，优先选择 topics 包含 `database`、`sql` 的仓库

   - **功能关键词匹配**：对比仓库描述与内容中的功能描述
     - 提取内容中的功能关键词
     - 与仓库的 description、README 进行匹配

   - **技术栈匹配**：检查仓库的主要语言和技术栈
     - 语言信息：`gh repo view owner/repo --json primaryLanguage`
     - 依赖分析：检查 package.json、requirements.txt 等

   - **热度和活跃度参考**（作为辅助）：
     - Star 数量、最近更新时间、Fork 数量

4. **匹配决策**：
   - 高置信度匹配：直接 star
   - 中等置信度：向用户展示候选列表，请求确认
   - 低置信度：跳过并记录，在报告中标注"需人工确认"

### 步骤 3：检查是否已 Star

Star 前验证仓库是否已被 star：

```bash
gh api user/starred/owner/repo 2>/dev/null && echo "已 star" || echo "未 star"
```

### 步骤 4：Star 仓库

执行 star 操作：

```bash
gh repo star owner/repo
```

### 步骤 5：生成报告

创建 star 报告，包含：
- 新 star 的仓库列表
- 已 star 的仓库（跳过）
- 需人工确认的仓库（多个候选或置信度不足）
- 未找到/失败的仓库

## 输出格式

提供汇总报告：

```
## Star 报告

### 新 Star (3)
- [owner/repo](url) - 描述（匹配依据：领域/功能/技术栈）

### 已 Star (2)
- owner/repo

### 需人工确认 (1)
- 项目名
  - 候选 1: [owner1/repo](url) - 描述 ⭐ 推荐（匹配度：高）
  - 候选 2: [owner2/repo](url) - 描述
  - 上下文提示：内容提到 AI Agent 开发，推荐选择候选 1

### 未找到 (1)
- 项目名（在 GitHub 上找不到匹配项）
```

## 定时任务配置

通过 hooks 实现自动化执行，在 settings.json 中配置：

```json
{
  "hooks": {
    "Prompt": [
      {
        "matcher": "star",
        "hooks": ["auto-star"]
      }
    ]
  }
}
```

用户可配置自定义定时任务来源：
- RSS feed URL
- 要监控的博客 URL
- 执行频率（如每 2 小时）

## 参考资料

- [GitHub 配置指南](references/github-config.md) - Token 设置说明

## 注意事项

- GitHub API 限制：未认证约 60 次/小时，通过 gh 认证后 5000 次/小时
- 考虑在 star 操作之间添加延迟
- Star 前始终验证仓库相关性
