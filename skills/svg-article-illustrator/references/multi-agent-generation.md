# 多 Agent 并行生成指南

> 当配图数量 ≥ 8 张时，启用并行生成以提升效率。

## 核心思路

```
主 Agent (分析 + 协调)
    │
    ├── 并行 Task Agent 1 → 生成配图 1-4
    ├── 并行 Task Agent 2 → 生成配图 5-8
    ├── 并行 Task Agent 3 → 生成配图 9-12
    └── ...
    │
    主 Agent (收集 + 插入 + 归档)
```

每批 3-5 张配图，避免单次 token 超限。

---

## 占位符格式

### 标准格式

```markdown
[[ILLUSTRATION:ID:简短描述]]
```

### 示例

```markdown
## 第一章：背景介绍

随着 AI 技术的发展...

[[ILLUSTRATION:01:AI技术演进时间线]]

在这一趋势下，企业面临新的选择。

[[ILLUSTRATION:02:传统vsAI工作流程对比]]

### 1.1 传统方式

[[ILLUSTRATION:03:传统方式示意图]]
```

### 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `ID` | ✅ | 序号，从 01 开始，递增 |
| `简短描述` | ✅ | 1-5 个词，描述核心概念 |

---

## 主 Agent 工作流程

### Step 1: 解析占位符

扫描文章，提取所有 `[[ILLUSTRATION:ID:描述]]`：

```javascript
// 输出格式
const illustrations = [
  { id: "01", description: "AI技术演进时间线", line: 15 },
  { id: "02", description: "传统vsAI工作流程对比", line: 23 },
  { id: "03", description: "传统方式示意图", line: 31 },
  // ...
];
```

### Step 2: 动态注入 Reference 文件

根据输出模式收集需要的 reference 文件，然后注入 Task Agent：

```javascript
// 根据模式选择 reference
const referenceFiles = {
  // 所有模式都需要
  always: ["core-principles.md"],

  // 按模式选择
  "dynamic-svg": ["dynamic-svg.md"],
  "static-svg": ["static-svg.md"],
  "png-export": ["png-export.md"]
};

// 合并需要的 reference
const neededRefs = [
  ...referenceFiles.always,
  ...referenceFiles[outputMode] || []
];
```

### Step 2.5: 构建 Task Agent Prompt

将 reference 内容注入到 prompt 中：

```markdown
# SVG 配图生成任务

## 模式
输出模式：{dynamic-svg | static-svg | png-export}

## 必须遵循的设计规范

### 核心原则（所有模式必须遵循）
【读取并嵌入 references/core-principles.md 完整内容】

### 模式特定规范
【根据 outputMode 读取并嵌入对应文件】
- dynamic-svg：references/dynamic-svg.md
- static-svg：references/static-svg.md
- png-export：references/png-export.md

## 任务

文章背景：
{文章摘要或相关章节内容}

配图需求（JSON）：
```json
[
  { "id": "01", "description": "..." },
  { "id": "02", "description": "..." }
]
```

要求：
- 为每张配图生成 SVG 代码
- 严格遵循上述设计规范
- ID 必须与输入一致

## 输出格式
```json
{
  "illustrations": [
    { "id": "01", "svg": "<svg>...</svg>" },
    { "id": "02", "svg": "<svg>...</svg>" }
  ]
}
```

### Step 3: 并行执行 Task Agent

```javascript
const results = [];
for (const batch of batches) {
  // 并行执行（Promise.all）
  const batchResults = await Promise.all(
    batches.map(batch => invokeTaskAgent(batch))
  );
  results.push(...batchResults.flat());
}
```

### Step 4: 插入并归档

按 ID 顺序替换占位符，然后归档。

---

## Task Agent 职责

### 主 Agent 需传递的内容

| 内容 | 来源 | 说明 |
|------|------|------|
| **核心原则** | references/core-principles.md | 所有模式都必须 |
| **模式规范** | references/{mode}.md | dynamic/static/png 对应文件 |
| 文章背景 | 源文件解析 | 相关章节内容 |
| 配图需求 | 占位符解析 | JSON 数组 |

### 输出

```json
{
  "illustrations": [
    { "id": "01", "svg": "<svg xmlns='http://www.w3.org/2000/svg'>...</svg>" },
    { "id": "02", "svg": "<svg xmlns='http://www.w3.org/2000/svg'>...</svg>" }
  ]
}
```

### 注意事项

- 每张图独立生成，不要相互引用
- ID 必须与输入一致
- SVG 包含完整 xmlns
- 遵循共享设计原则

---

## 批量规模建议

| 配图数量 | 批次建议 | 并行度 |
|---------|---------|--------|
| 1-4 张 | 1 批 | 顺序生成即可 |
| 5-8 张 | 2 批 | 2 个并行 |
| 9-12 张 | 3 批 | 3 个并行 |
| 13+ 张 | 4 批 | 4 个并行 |

---

## 完整流程示例

```markdown
# 用户输入
/svg-article-illustrator @article.md

# 主 Agent 流程
1. 扫描文章，发现 10 个 [[ILLUSTRATION:XX:描述]]
2. 分成 3 批（4+4+2）
3. 并行启动 3 个 Task Agent
4. 收集 10 个 SVG 结果
5. 按 01-10 顺序插入文章
6. 执行归档
```

---

## 自动检测阈值

在 SKILL.md 中已定义：

> 当配图数量 ≥ 8 张时，启用并行生成模式

主 Agent 应自动检测并切换模式，无需用户指定。
