---
name: md2html
description: Markdown转HTML可视化报告。将Markdown文档转换为结构化、可视化的HTML报告，支持打印样式、目录导航、多种主题。适用于判决书分析报告、法律文书、研究报告等需要专业可视化的场景。
license: CC-BY-NC-SA-4.0
---

# md2html - Markdown 转 HTML 可视化报告

**版本**: 1.0.0
**最后更新**: 2026-03-05
**说明**: 将 Markdown 文档转换为结构化、可视化的 HTML 报告，支持打印为 PDF

## 核心定位

**为什么需要 HTML 输出？**

- **可视化增强**：表格、时间轴、引用块等元素更直观
- **屏幕阅读友好**：适合在电脑/平板上阅读和演示
- **打印为 PDF**：通过浏览器打印生成高质量 PDF
- **分享便捷**：HTML 文件可直接发送，无需特殊软件

**与 md2word 的区别**：

| 特性 | md2html | md2word |
|------|---------|---------|
| 阅读场景 | 屏幕阅读、演示 | 打印、正式提交 |
| 可视化 | 丰富（图表、高亮） | 基础（表格、文本） |
| 文件格式 | HTML / PDF | DOCX |
| 交互性 | 支持（目录跳转） | 不支持 |
| 适用场景 | 内部分享、演示 | 正式文书、归档 |

## 设计思路

### 信息流转

```
Markdown (litigation-analysis 输出)
    ↓
md2html (结构化转换)
    ↓
HTML (可视化报告)
    ↓
浏览器打印 → PDF (正式文档)
```

### 核心特性

1. **结构化增强**
   - 自动生成目录导航
   - 表格样式优化
   - 引用块高亮
   - 代码块语法高亮

2. **法律文书优化**
   - 案件信息卡片
   - 争议焦点标注
   - 法条引用格式化
   - 时间轴可视化

3. **打印友好**
   - 打印样式优化
   - 页眉页脚
   - 分页控制

4. **多种主题**
   - legal：法律文书风格（默认）
   - academic：学术报告风格
   - minimal：极简风格

## 使用方式

### 基本使用

```bash
# 转换单个文件
python scripts/md2html.py input.md

# 指定输出路径
python scripts/md2html.py input.md -o output.html

# 使用主题
python scripts/md2html.py input.md --theme=academic

# 批量转换
python scripts/md2html.py *.md --output-dir=./html/
```

### 高级选项

```bash
# 启用目录导航
python scripts/md2html.py input.md --toc

# 禁用打印样式
python scripts/md2html.py input.md --no-print-style

# 自定义 CSS
python scripts/md2html.py input.md --css=custom.css

# 内联所有资源（单文件）
python scripts/md2html.py input.md --inline
```

### 在其他 Skill 中调用

```python
from md2html import convert

# 基本转换
html_path = convert("report.md")

# 自定义选项
html_path = convert(
    "report.md",
    output_path="custom.html",
    theme="academic",
    toc=True
)
```

## 输出结构

```
[案件编号]/
├── [案件编号] 深度分析报告内部版.md
├── [案件编号] 深度分析报告内部版.html  ← md2html 生成
└── [案件编号] 深度分析报告内部版.pdf    ← 浏览器打印
```

## HTML 增强功能

### 1. 自动目录导航

从标题自动生成侧边栏目录，支持：
- 点击跳转
- 滚动高亮
- 层级缩进

### 2. 表格样式优化

- 斑马纹行
- 表头固定
- 响应式宽度
- 高亮单元格

### 3. 法律文书专用元素

**案件信息卡片**：
```html
<div class="case-card">
  <div class="case-number">(2024)京01民初123号</div>
  <div class="case-title">张三诉李四专利权纠纷</div>
  <div class="case-meta">...</div>
</div>
```

**争议焦点标注**：
```html
<div class="focus-point">
  <span class="focus-label">争议焦点</span>
  <p>...</p>
</div>
```

**法条引用**：
```html
<blockquote class="law-quote">
  《专利法》第十一条：...
</blockquote>
```

### 4. 打印优化

- 打印时隐藏目录导航
- 优化页边距
- 控制分页位置
- 添加页眉页脚

## 主题系统

### legal（法律文书风格）

- 字体：仿宋、楷体
- 配色：沉稳的蓝灰色调
- 表格：简洁边框
- 适用：判决书分析、法律报告

### academic（学术报告风格）

- 字体：衬线体
- 配色：学术蓝
- 表格：三线表
- 适用：研究报告、论文

### minimal（极简风格）

- 字体：无衬线
- 配色：黑白灰
- 表格：无边框
- 适用：内部笔记、快速预览

## 依赖要求

详细安装指南见 [INSTALL.md](INSTALL.md)

### Python 依赖

```bash
# 推荐使用虚拟环境
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**核心依赖**:
- markdown>=3.4.0
- beautifulsoup4>=4.12.0

### 可选依赖

```bash
# 代码语法高亮
pip install pygments

# PDF 导出（可选）
pip install weasyprint
```

## 目录结构

```
md2html/
├── SKILL.md               # 本文档
├── CHANGELOG.md           # 版本记录
├── scripts/
│   ├── md2html.py         # 主转换脚本
│   ├── converter.py       # 转换核心
│   └── utils.py           # 工具函数
├── assets/
│   ├── themes/            # 主题 CSS
│   │   ├── legal.css
│   │   ├── academic.css
│   │   └── minimal.css
│   ├── templates/         # HTML 模板
│   │   ├── base.html
│   │   ├── report.html
│   │   └── print.html
│   └── fonts/             # 字体文件（可选）
└── references/
    ├── custom-styles.md   # 自定义样式指南
    └── examples.md        # 使用示例
```

## 与 litigation-analysis 集成

### 推荐工作流

1. **litigation-analysis** 产出 Markdown
2. **md2html** 转换为 HTML（内部版 + 客户版）
3. 浏览器打开 HTML，打印为 PDF
4. 发送 PDF 给客户或归档

### 自动化脚本示例

```bash
# 批量转换 litigation-analysis 输出
for md in cases/*内部版.md; do
    python scripts/md2html.py "$md" --theme=legal --toc
done
```

## 错误处理

- **文件编码**：自动检测 UTF-8 和 GBK
- **无效 Markdown**：跳过错误段落，记录警告
- **缺失资源**：内联或降级处理

## 未来扩展

- [ ] 支持图表（Mermaid、Chart.js）
- [ ] 支持数学公式（MathJax）
- [ ] PDF 直接导出（WeasyPrint）
- [ ] 多语言支持
- [ ] 自定义模板系统

---

md2html - 让法律文书更专业、更易读
