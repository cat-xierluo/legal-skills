---
name: svg-article-illustrator
description: AI驱动的SVG文章配图生成工具，支持动态SVG、静态SVG和PNG导出三种输出模式。当用户需要为文章生成配图、创建SVG插图、将SVG转换为PNG，或提到"为文章配图"、"生成插图"时使用此技能。
---
# SVG Article Illustrator

AI 驱动的文章配图生成工具，使用 SVG 技术为公众号文章生成高质量配图。

> **重要说明**：默认模式（dynamic-svg 和 static-svg）将 **SVG 代码直接嵌入**到 Markdown 文件中，而不是使用 `![](path.svg)` 的图片引用语法。这确保了动画效果和最佳兼容性。

## 快速开始

```
/svg-article-illustrator @path/to/article.md
```

## 依赖说明

- **dynamic-svg / static-svg 模式**：无需安装任何依赖
- **png-export 模式**：需要安装 Node.js 和 puppeteer，详见 [references/png-export.md](references/png-export.md#依赖)

---

## 选择输出模式

根据用户需求和发布平台选择合适的输出模式：

| 用户场景           | 使用模式              | 加载参考文件              |
| ------------------ | --------------------- | ------------------------- |
| 默认/未指定        | **dynamic-svg** | references/dynamic-svg.md |
| 需要动画效果       | **dynamic-svg** | references/dynamic-svg.md |
| 需要 PNG 兼容性    | **png-export**  | references/png-export.md  |
| 不知道如何使用 SVG | **png-export**  | references/png-export.md  |
| 明确要求静态效果   | **static-svg**  | references/static-svg.md  |
| 需要静态 SVG 代码  | **static-svg**  | references/static-svg.md  |

**默认模式**：当用户未明确指定时，使用 **dynamic-svg** 模式。

---

## 并行生成模式

当配图数量 ≥ 8 张时，自动启用多 Agent 并行生成以提升效率。

详见：[references/multi-agent-generation.md](references/multi-agent-generation.md)

**核心思路**：
1. 主 Agent 分析文章内容并规划配图
2. 插入占位符 `[[ILLUSTRATION:ID:简短描述]]` 到文章
3. 解析占位符，按批次分发（每批 3-5 张）
4. 并行启动多个 Task Agent 生成
5. 主 Agent 按 ID 顺序收集并替换占位符

**启用条件**：
- 规划的配图数量 ≥ 8 张

---

## 核心工作流程

### 第一阶段：内容分析

1. 读取源文章 Markdown 文件
2. 识别核心概念和关键信息点
3. 规划配图位置：
   - 每个二级标题（##）后至少 1 张图
   - 每 2-3 个重要段落 1 张图
   - 重要概念转折点额外配图
   - 在规划位置插入占位符 `[[ILLUSTRATION:ID:简短描述]]`

4. 评估并选择生成模式：
   - ≥ 8 张 → 并行生成（多 Task Agent）
   - < 8 张 → 顺序生成

### 第二阶段：设计 SVG

1. 根据选择的输出模式应用相应规范
   - **dynamic-svg**：添加 SMIL 动画效果
   - **static-svg**：生成静态 SVG 代码
   - **png-export**：生成 SVG 文件
2. 遵循共享设计原则：[references/core-principles.md](references/core-principles.md)

### 第三阶段：生成与输出

1. **解析占位符**：提取所有 `[[ILLUSTRATION:ID:描述]]`
2. **并行/顺序生成**：
   - ≥ 8 张：并行生成（多 Task Agent）
   - < 8 张：顺序生成
3. **替换占位符**：将生成的 SVG 代码替换占位符

> **默认行为**：除非用户明确要求 PNG 格式或图片文件引用，否则**必须直接将 SVG 代码嵌入**到 Markdown 文件中。

- **dynamic-svg**：将 SVG 代码直接嵌入 Markdown 文件（使用 `<svg>` 标签）
- **static-svg**：将 SVG 代码直接嵌入 Markdown 文件（使用 `<svg>` 标签）
- **png-export**（仅当用户明确要求时）：
  1. 保存 SVG 文件到源文章目录
  2. 使用 `scripts/svg2png.js` 转换为 PNG
  3. 在 Markdown 中插入图片引用 `![](path.png)`

### 第四阶段：归档

每次完成配图生成后，将文章中的 SVG 代码提取并归档到 Skill 内部：

```bash
# 归档目录结构
.claude/skills/svg-article-illustrator/archive/YYYYMMDD_HHMMSS_文章名/
├── 1_配图名称.svg  # 提取的 SVG 文件
├── 2_配图名称.svg
└── ...
```

**归档命名规则**：

- 格式：`YYYYMMDD_HHMMSS_文章标题`
- 文章标题取自 Markdown 的第一个一级标题（`# 标题`），去除特殊字符
- SVG 文件命名：`序号_配图名称.svg`
- 示例：`20260209_163045_AI_Agent法律工作流未来范式/`
  - `1_AI_Agent_演进概览.svg`
  - `2_提示词设计.svg`
  - ...

**归档执行命令**：

```bash
# 归档 SVG（提取文章中的 SVG 代码并保存为独立文件）
scripts/archive.sh @path/to/article.md
```

---

## 共享设计原则

所有输出模式都遵循相同的核心设计原则，详见：[references/core-principles.md](references/core-principles.md)

核心要点：

- 概念聚焦：每张图只表达 1-2 个核心概念
- 极简设计：浅色主题，大图形，少文字
- 画布尺寸：800x450（16:9 比例）
- 边界控制：所有元素在有效区域内（60px 安全边距）

---

## 模式特定规范

### Dynamic SVG 模式

**默认模式**，支持 SMIL 动画效果。

详见：[references/dynamic-svg.md](references/dynamic-svg.md)

核心特性：

- SMIL 动画：浮动、虚线流动、箭头绘制
- Emoji 动画：浮动、脉冲效果
- 逻辑性动画优先：箭头和虚线框必须有动画
- SVG 代码直接嵌入 Markdown

### Static SVG 模式

静态 SVG 代码直接嵌入 Markdown。

详见：[references/static-svg.md](references/static-svg.md)

核心特性：

- 无动画效果
- SVG 代码直接嵌入 Markdown
- 公众号完美支持

### PNG Export 模式

生成独立的 SVG 和 PNG 文件。

详见：[references/png-export.md](references/png-export.md)

核心特性：

- 文件命名：短名-序号.svg（≤15 字符）
- 保存位置：与源文章同目录
- PNG 转换：使用 `scripts/svg2png.js`
- 跨平台兼容性最佳

---

## PNG 转换脚本

使用 `scripts/svg2png.js` 进行高保真转换：

```bash
node scripts/svg2png.js input.svg [output.png] [dpi]
```

- **默认 DPI**：600
- **支持**：emoji、中文、CSS
- **输出位置**：总是生成到 SVG 源文件所在目录

---

## 成功标准

- 配图密度 10-15 张，有效增强视觉吸引力
- 每张配图概念聚焦准确
- 极简风格贯穿始终
- 公众号显示正常
- 跨平台兼容性良好
