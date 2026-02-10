# 配置架构参考

本文档提供 md2word 配置系统的快速参考。

## 配置概述

md2word 使用 YAML 格式的配置文件来控制 Word 文档的格式化输出。配置采用层级结构，支持以下顶级分组：

| 分组 | 说明 |
|:-----|:-----|
| `page` | 页面尺寸和页边距 |
| `fonts` | 默认字体设置 |
| `titles` | 标题格式（4 级） |
| `paragraph` | 段落格式 |
| `page_number` | 页码设置 |
| `quotes` | 引号转换 |
| `table` | 表格格式 |
| `code_block` | 代码块格式 |
| `inline_code` | 行内代码格式 |
| `quote` | 引用块格式 |
| `math` | 数学公式格式 |
| `image` | 图片设置 |
| `horizontal_rule` | 分割线设置 |
| `lists` | 列表设置 |

---

## 配置分组

### 页面设置 (page)

```yaml
page:
  width: 21.0              # 纸张宽度 (cm)
  height: 29.7             # 纸张高度 (cm)
  margin_top: 2.54         # 上边距 (cm)
  margin_bottom: 2.54      # 下边距 (cm)
  margin_left: 3.18        # 左边距 (cm)
  margin_right: 3.18       # 右边距 (cm)
```

### 字体设置 (fonts)

```yaml
fonts:
  default:
    name: "仿宋_GB2312"    # 中文字体名称
    ascii: "Times New Roman"  # 英文字体名称
    size: 12               # 字号 (pt)
    color: "#000000"       # 字体颜色 (十六进制)
```

### 标题格式 (titles)

```yaml
titles:
  level1:
    size: 15               # 字号 (pt)
    bold: true             # 是否加粗
    align: "center"        # 对齐方式 (left/center/right/justify)
    space_before: 6        # 段前间距 (pt)
    space_after: 6         # 段后间距 (pt)
    indent: 0              # 首行缩进 (pt)
  level2:                  # 二级标题配置
  level3:                  # 三级标题配置
  level4:                  # 四级标题配置
```

### 段落格式 (paragraph)

```yaml
paragraph:
  line_spacing: 1.5        # 行距倍数
  first_line_indent: 24    # 首行缩进 (pt)
  align: "justify"         # 对齐方式
```

### 页码设置 (page_number)

```yaml
page_number:
  enabled: true            # 是否启用页码
  format: "1/x"            # 格式 ("1", "x", "1/x")
  font: "Times New Roman"  # 字体
  size: 10.5               # 字号 (pt)
  position: "center"       # 位置 (left/center/right)
```

### 表格格式 (table)

```yaml
table:
  border_enabled: true     # 是否显示边框
  border_color: "#000000"  # 边框颜色
  border_width: 4          # 边框宽度
  line_spacing: 1.2        # 行距
  row_height_cm: 0.8       # 行高 (cm)
  alignment: "center"      # 表格对齐
  cell_margin:             # 单元格边距
    top: 30
    bottom: 30
    left: 60
    right: 60
  vertical_align: "center" # 垂直对齐 (top/center/bottom)
  header:                  # 标题行格式
    font: "Times New Roman"
    size: 10.5
    bold: true
    color: "#000000"
  body:                    # 正文格式
    font: "仿宋_GB2312"
    size: 10.5
    color: "#000000"
```

### 代码块格式 (code_block)

```yaml
code_block:
  label:                   # 语言标签格式
    font: "Times New Roman"
    size: 10
    color: "#808080"
  content:                 # 代码内容格式
    font: "Times New Roman"
    size: 10
    color: "#333333"
    left_indent: 24
    line_spacing: 1.2
```

### 行内代码格式 (inline_code)

```yaml
inline_code:
  font: "Times New Roman"
  size: 10
  color: "#333333"
```

### 引用块格式 (quote)

```yaml
quote:
  background_color: "#EAEAEA"
  left_indent_inches: 0.2
  font_size: 9
  line_spacing: 1.5
```

### 数学公式格式 (math)

```yaml
math:
  font: "Times New Roman"
  size: 11
  italic: true
  color: "#00008B"
```

### 图片设置 (image)

```yaml
image:
  display_ratio: 0.92      # 相对于页面可用宽度的比例
  max_width_cm: 14.2       # 最大显示宽度 (cm)
  target_dpi: 260          # 目标 DPI
  show_caption: true       # 是否显示标题
```

### 分割线设置 (horizontal_rule)

```yaml
horizontal_rule:
  character: "─"           # 分割线字符
  repeat_count: 55         # 重复次数
  font: "Times New Roman"
  size: 12
  color: "#808080"
  alignment: "center"
```

### 列表设置 (lists)

```yaml
lists:
  bullet:                  # 无序列表
    marker: "•"            # 标记符号
    indent: 24
  numbered:                # 有序列表
    indent: 24
    preserve_format: true
  task:                    # 任务列表
    unchecked: "☐"
    checked: "☑"
```

### 引号设置 (quotes)

```yaml
quotes:
  convert_to_chinese: true  # 是否自动转换英文引号为中文引号
```

---

## 自定义配置

### 方法一：修改配置模板

1. 复制配置模板：
   ```bash
   cp assets/config-template.yaml my-config.yaml
   ```

2. 编辑配置文件，修改需要的参数

3. 使用自定义配置：
   ```bash
   python scripts/md2word.py input.md --config=my-config.yaml
   ```

### 方法二：基于预设修改

1. 复制预设文件：
   ```bash
   cp assets/presets/legal.yaml my-config.yaml
   ```

2. 在复制的文件基础上修改

3. 使用自定义配置

---

## 预设对比

| 预设 | 适用场景 | 字体 | 字号 | 行距 | 特点 |
|:-----|:---------|:-----|:-----|:-----|:-----|
| **legal** | 正式文档 | 仿宋_GB2312 | 12pt (小四) | 1.5 | 标准中文正式文档格式 |
| **academic** | 学术论文 | 宋体 | 12pt (小四) | 2.0 | 双倍行距，适合学术规范 |
| **report** | 工作报告 | 仿宋_GB2312 | 12pt (小四) | 1.5 | 黑体标题，适合报告 |
| **simple** | 简单文档 | 仿宋_GB2312 | 12pt (小四) | 1.5 | 无特殊要求，基础格式 |

---

## 完整配置文件

所有预设的完整配置文件位于 `assets/presets/` 目录：

- `assets/presets/legal.yaml` - 正式文档格式
- `assets/presets/academic.yaml` - 学术论文格式
- `assets/presets/report.yaml` - 工作报告格式
- `assets/presets/simple.yaml` - 简单文档格式

配置模板：`assets/config-template.yaml`
