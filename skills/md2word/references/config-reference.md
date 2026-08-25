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
  orientation: portrait    # 页面方向: portrait(纵向,默认) / landscape(横向)
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
  space_after: 6           # 表格组件后的固定高度留白，单位 pt（exact 空段）
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

所有连续的 Markdown `>` 行统一渲染为段落型 callout，不根据“本章导读”“案例”等文字标签切换样式。段落底纹天然与正文左右边界齐平，不创建 `w:tbl`，因此 Word 的“查看网格线”不会显示虚线外框。与底纹同色的实线段落边界只用于承载文字内边距：首段承担上内边距、末段承担下内边距，每段承担左右内边距；线条与灰底同色，不形成可见轮廓。内部空引用行生成一个同底色、段前段后为 0 的 `paragraph_spacing` exact 空段，避免 Word 不给内容段段后距着色而产生白缝。连续多个内部空引用行确定性折叠为一个；首尾空引用行忽略，由 `padding` 承担块边缘留白。

```yaml
quote:
  background_color: "#EDF2F7" # 段落背景色；与 confirmed 状态灰统一
  padding:                     # 文字到灰底边缘的留白，单位 pt
    top: 5
    bottom: 5
    left: 6
    right: 6
  space_before: 6              # callout 外部段前间距，单位 pt
  space_after: 6               # callout 外部段后间距，单位 pt
  paragraph_spacing: 6         # 同底色内部 exact 空段高度，单位 pt
  font_size: null              # null = 继承正文
  line_spacing: null           # null = 继承正文
  first_line_indent: 0         # 引用段首行缩进，单位 pt
  align: justify               # left/center/right/justify
```

兼容迁移：若自定义配置仍只有 v1.3.0 的 `quote.cell_margin`，转换器会按 `20 twips = 1 pt` 映射到 `padding`，保持原物理留白。`width_percent`、`border_color`、`border_size` 与 v1.2.x 的 `left_indent_inches` 不再参与段落型引用框渲染；引用框固定为正文宽、无可见轮廓。新配置应直接使用 `padding`。

`table.space_after` 归属于数据表组件本身：每个成功生成的 Markdown 或 HTML 表格后恰好追加一个段前/段后均为 0、行高为配置值的 exact 空段。后续正文继续使用普通正文格式；无数据表时不生成该间隔，图片与图注链路也不应用。

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

## 预设列表

运行以下命令查看所有预设详情（从 YAML 动态读取）：

```bash
python scripts/config.py --list
```

完整配置文件位于 `assets/presets/` 目录，设计说明位于 `assets/theme-notes/`。
