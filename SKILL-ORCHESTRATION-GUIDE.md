# Skill 编排指南 (Skill Orchestration Guide)

本指南是 [SKILL-DEV-GUIDE.md](SKILL-DEV-GUIDE.md) 的补充文档。

- **SKILL-DEV-GUIDE.md**：单个 Skill 的开发规范
- **SKILL-ORCHESTRATION-GUIDE.md**：多个 Skill 的协作编排规范

---

## 1. 核心理念

### 1.1 为什么叫 Orchestration 而不是 Workflow？

为了避免与 N8N、Dify、Coze 等可视化 Workflow 工具混淆。

### 1.2 AI Agent + Skill vs 传统 Workflow

| 特性 | 传统 Workflow (N8N/Dify) | AI Agent + Skill |
|:-----|:-------------------------|:-----------------|
| 编排方式 | 可视化拖拽节点 | 自然语言描述 |
| 执行引擎 | 平台运行时 | AI (LLM) |
| 灵活性 | 节点有限，需预设 | AI 自主理解决策 |
| 运行环境 | 依赖平台 | 本地 CLI，完全自主 |

**核心差异**：AI 是编排引擎，而非预定义的节点连接。

```
传统 Workflow:
  用户 → 拖拽配置 → 平台执行 → 固定输出

AI Agent + Skill:
  用户意图 → AI 理解 → 动态编排 → 智能输出
```

### 1.3 解耦设计的价值

将功能拆分成独立 Skill，而非做成单体：

- 各 Skill 独立可复用
- 可灵活组合成不同编排流程
- 修改隔离，影响可控

---

## 2. AI 如何理解编排

AI 的编排能力来源于：

1. **SKILL.md 的 description**：触发 Skill 匹配
2. **自然语言描述**：SKILL.md 中的"与其他技能配合"章节
3. **references/workflow.md**：复杂编排流程的详细描述（可选，按需加载）

### 2.1 简单协作：在 SKILL.md 中描述

```markdown
## 与其他技能配合

下载的视频可以使用 [funasr-transcribe] 转录为 Markdown 文件。
两个技能独立运行，可根据需要灵活组合使用。
```

### 2.2 复杂编排：创建 references/workflow.md

对于定时运行、多步骤、有条件判断的编排，在 Skill 的 `references/` 目录下创建 `workflow.md`。

**目录结构**：

```text
skill-name/
├── SKILL.md
├── references/
│   └── workflow.md    # 复杂编排流程（可选）
├── scripts/
└── assets/
```

**示例**：GitHub Star 周报流程

```markdown
# GitHub Star 周报生成

每周检查新增 Star，筛选高价值项目并生成周报。

## Step 1: 更新数据
python scripts/main.py --check --user=maoking

## Step 2: 筛选高价值项目
从新增 Star 中筛选：
- Stars > 500
- 描述包含 "ai" / "llm" / "agent"

## Step 3: 深度研究
对筛选出的项目，使用 [repo-research] 进行深度分析

## Step 4: 生成周报
汇总保存到 output/weekly-report.md
```

---

## 3. 可编排 Skill 设计要点

### 3.1 明确输入/输出

在 SKILL.md 中声明：

```markdown
## 输入/输出

### 输入
- 必需：GitHub 仓库 URL
- 可选：--compare-with 本地项目路径

### 输出
- 研究报告：./research/YYYYMMDD-topic/REPORT.md
```

### 3.2 单一职责

每个 Skill 只做一件事，便于灵活组合。

### 3.3 幂等性

多次执行结果相同，避免重复执行产生副作用。

---

## 4. 定时运行

使用 macOS launchd 或 cron 配置定时任务。

**launchd 示例**：

```xml
<key>StartCalendarInterval</key>
<dict>
    <key>Weekday</key>
    <integer>1</integer>  <!-- 每周一 -->
    <key>Hour</key>
    <integer>9</integer>
</dict>
```

---

## 变更历史

| 版本 | 日期 | 更新内容 |
|:-----|:-----|:---------|
| v1.2.0 | 2026-02-14 | 大幅精简，聚焦核心理念，移除冗余示例和理论内容 |
| v1.1.0 | 2026-02-14 | 重命名为 SKILL-ORCHESTRATION-GUIDE.md；新增与传统 Workflow 工具对比 |
| v1.0.0 | 2026-02-14 | 初始版本 |
