# md2html - 法律文书可视化报告转换器

**版本**: 2.0.0
**说明**: 基于内容理解的法律文书 HTML 可视化转换，支持多种法律文书类型

---

## 核心设计理念

### 不是格式转换，而是内容可视化

- **理解文档结构**：识别争议焦点、证据表格、时间轴、行动建议
- **智能类型判断**：自动识别文书类型（判决书分析、客户版、研究版等）
- **统一视觉风格**：专业的法律文书审美

---

## 文档类型识别

### 支持的文档类型

| 类型 | 识别特征 | 核心展示 |
|------|---------|---------|
| `judgment_internal` | 包含"争议焦点"、"法院认定" | 争议焦点高亮、证据表格、判决结果 |
| `judgment_client` | 包含"案件核心问题"、"行动建议" | 核心结论、关键时间轴、行动清单 |
| `judgment_research` | 包含"法律问题"、"研究课题" | 问题列表、案例参考、裁判规则 |
| `legal_opinion` | 包含"法律分析"、"风险评估" | 法律依据、风险矩阵、建议 |
| `general` | 默认类型 | 标准文档展示 |

### 识别逻辑

```
1. 提取标题和关键章节
2. 匹配类型特征词
3. 选择对应的渲染模板
4. 应用类型专属样式
```

---

## 渲染模板

### 1. 判决书分析（judgment）

```html
<!-- 头部：案件信息卡片 -->
<header class="case-header">
  <div class="case-badge">判决书分析</div>
  <h1>案件名称</h1>
  <div class="case-meta">
    <span>案号</span>
    <span>法院</span>
    <span>日期</span>
  </div>
</header>

<!-- 核心要点速览 -->
<section class="key-points">
  <div class="point-card">
    <div class="point-label">判决结果</div>
    <div class="point-value">胜诉/败诉</div>
  </div>
  <!-- 更多要点卡片 -->
</section>

<!-- 争议焦点 -->
<section class="dispute-focus">
  <h2>争议焦点</h2>
  <div class="focus-item">
    <div class="focus-title">焦点一：xxx</div>
    <div class="focus-court">⭐ 法院认定：xxx</div>
    <div class="focus-reason">认定理由</div>
  </div>
</section>

<!-- 证据表格 -->
<section class="evidence-section">
  <h2>证据认定</h2>
  <table class="evidence-table">
    <thead>
      <tr>
        <th>证据</th>
        <th>提交方</th>
        <th>证明目的</th>
        <th>法院认定</th>
        <th>证明力</th>
      </tr>
    </thead>
    <tbody>...</tbody>
  </table>
</section>
```

### 2. 客户版报告（judgment_client）

```html
<!-- 简化头部 -->
<header class="client-header">
  <h1>案件概览</h1>
</header>

<!-- 可视化时间轴 -->
<section class="timeline">
  <div class="timeline-item">
    <div class="timeline-date">2024-01</div>
    <div class="timeline-content">立案</div>
  </div>
</section>

<!-- 核心问题 -->
<section class="core-issues">
  <div class="issue-card">
    <div class="issue-title">问题一</div>
    <div class="issue-desc">简单说明</div>
    <div class="issue-impact">对您的影响</div>
  </div>
</section>

<!-- 行动建议 -->
<section class="action-items">
  <h2>建议行动</h2>
  <div class="action-item pending">
    <input type="checkbox">
    <span>行动项</span>
  </div>
</section>
```

---

## 视觉风格

### 配色方案

```css
/* 法律文书专业配色 */
:root {
  /* 主色调：深蓝 */
  --primary: #1e3a5f;
  --primary-light: #2d5a87;
  
  /* 辅助色：暖橙（用于强调） */
  --accent: #e67e22;
  
  /* 中性色 */
  --text: #2c3e50;
  --text-light: #7f8c8d;
  --bg: #f8f9fa;
  --bg-white: #ffffff;
  
  /* 功能色 */
  --success: #27ae60;
  --warning: #f39c12;
  --danger: #e74c3c;
  
  /* 边框 */
  --border: #e0e6ed;
}
```

### 字体系统

```css
/* 标题：思源宋体 */
h1, h2, h3 {
  font-family: "Source Han Serif CN", "Noto Serif SC", serif;
}

/* 正文：思源黑体 */
body {
  font-family: "Source Han Sans CN", "Noto Sans SC", sans-serif;
}

/* 数字：等宽数字 */
.case-number, .dates {
  font-family: "SF Mono", Consolas, monospace;
}
```

### 组件设计

**要点卡片**：
- 圆角矩形（8px）
- 左侧色条标识类型
- 图标 + 标签 + 内容

**争议焦点块**：
- 标题用红色/橙色高亮
- "法院认定"用⭐标记，黄色背景
- 理由部分用引号样式

**证据表格**：
- 表头深蓝背景白字
- 斑马纹行
- "采信"绿色，"不采信"红色
- 证明力星级显示

---

## 使用方式

### 基本命令

```bash
# 自动识别类型
python scripts/md2html.py "判决书分析.md"

# 指定类型
python scripts/md2html.py "判决书分析.md" --type=judgment

# 指定模板
python scripts/md2html.py "判决书分析.md" --template=judgment
```

### Python 调用

```python
from md2html import convert

# 自动识别并转换
html = convert(
    "案件分析.md",
    auto_detect=True  # 默认开启
)

# 手动指定类型
html = convert(
    "案件分析.md",
    doc_type="judgment_internal"
)
```

---

## 与 litigation-analysis 集成

### 输出流程

```
litigation-analysis
    ↓ 生成
[案件编号] 深度分析报告内部版.md
    ↓ md2html (auto)
[案件编号] 深度分析报告内部版.html  ← 自动识别为 judgment_internal
    ↓ 打印
[案件编号] 深度分析报告内部版.pdf
```

### 批量转换

```bash
# 转换所有输出
for md in cases/*.md; do
    python scripts/md2html.py "$md" --toc
done
```

---

## 设计系统

### 配色主题

支持多套专业配色方案：

| 主题 | 主色 | 风格 |
|------|------|------|
| `default` | 深蓝 `#1e3a5f` | 稳重专业（默认） |
| `ocean` | 海洋蓝 `#0ea5e9` | 清新现代 |
| `forest` | 森林绿 `#059669` | 稳重生态 |
| `sunset` | 日落橙 `#ea580c` | 温暖活力 |
| `violet` | 紫罗兰 `#7c3aed` | 优雅创意 |

```bash
# 使用不同主题
python scripts/md2html.py report.md --theme=ocean
python scripts/md2html.py report.md --theme=forest
python scripts/md2html.py report.md --theme=sunset
```

### 图标系统

使用 SVG 图标替代 Emoji，保持专业统一：

- 线性风格
- 统一 stroke-width
- 颜色可自定义

```
📋 → ✓ 图标
📅 → 日历图标
⭐ → 星星图标
⚖ → 天平图标
📌 → 标记图标
```

---

## 未来计划

- [ ] 智能目录生成（基于内容结构）
- [ ] 证据链可视化
- [ ] 时间轴自动生成
- [ ] 图表嵌入（Mermaid）
