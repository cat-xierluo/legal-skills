# md2html 使用示例

## 基本使用

### 1. 转换单个文件

```bash
# 最简单的用法
python scripts/md2html.py report.md

# 输出: report.html
```

### 2. 指定输出路径

```bash
python scripts/md2html.py input.md -o output.html
```

### 3. 使用主题

```bash
# 学术报告风格
python scripts/md2html.py thesis.md --theme=academic

# 极简风格
python scripts/md2html.py notes.md --theme=minimal

# 法律文书风格（默认）
python scripts/md2html.py judgment.md --theme=legal
```

### 4. 启用目录导航

```bash
python scripts/md2html.py report.md --toc
```

## 高级用法

### 5. 批量转换

```bash
# 转换当前目录所有 Markdown 文件
python scripts/md2html.py *.md

# 指定输出目录
python scripts/md2html.py *.md --output-dir=./html/
```

### 6. 禁用打印样式

```bash
python scripts/md2html.py report.md --no-print-style
```

### 7. 内联所有资源

```bash
# 生成独立的 HTML 文件（无外部依赖）
python scripts/md2html.py report.md --inline
```

## 与 litigation-analysis 集成

### 工作流

```bash
# 1. 生成 Markdown 报告
/litigation-analysis @判决书.md

# 2. 转换为 HTML
python scripts/md2html.py "案件123 深度分析报告内部版.md" --toc --theme=legal

# 3. 在浏览器中打开 HTML，打印为 PDF
open "案件123 深度分析报告内部版.html"
# ⌘P → 另存为 PDF
```

### 批量脚本

```bash
#!/bin/bash
# convert_all.sh - 批量转换 litigation-analysis 输出

for md in cases/*内部版.md; do
    echo "转换: $md"
    python scripts/md2html.py "$md" --toc --theme=legal
done

echo "全部转换完成！"
```

## 在 Python 中调用

```python
from scripts.md2html import MarkdownToHTMLConverter

# 创建转换器
converter = MarkdownToHTMLConverter(
    theme="legal",
    toc=True,
    print_style=True
)

# 转换
with open("report.md", "r", encoding="utf-8") as f:
    md_content = f.read()

html_content = converter.convert(md_content, title="案件分析报告")

# 保存
with open("report.html", "w", encoding="utf-8") as f:
    f.write(html_content)
```

## 自定义样式

### 方法 1：修改主题 CSS

编辑 `assets/themes/legal.css`：

```css
/* 修改主色调 */
body {
    color: #1a1a1a;
}

h2 {
    border-left-color: #e74c3c;
}
```

### 方法 2：创建新主题

1. 复制现有主题：
   ```bash
   cp assets/themes/legal.css assets/themes/custom.css
   ```

2. 修改样式

3. 使用新主题：
   ```bash
   python scripts/md2html.py report.md --theme=custom
   ```

## 输出示例

### 输入 Markdown

```markdown
# 张三诉李四专利权纠纷 - 深度分析报告

## 案件基本信息

| 项目 | 内容 |
|------|------|
| 案号 | (2024)京01民初123号 |
| 案由 | 专利权纠纷 |
| 法院 | 北京知识产权法院 |

## 争议焦点

### 焦点一：技术特征是否相同

**法院认定**：
被诉侵权产品的技术特征与专利权利要求1记载的技术特征相同。
```

### 输出 HTML 特性

- ✅ 自动生成目录导航（如启用 --toc）
- ✅ 表格添加斑马纹样式
- ✅ 案件信息表格特殊样式
- ✅ 争议焦点标题高亮
- ✅ 打印时隐藏目录，优化布局
- ✅ 响应式设计，适配移动端

## 打印为 PDF

### 方法 1：浏览器打印

1. 在浏览器中打开 HTML 文件
2. 按 `⌘P` (Mac) 或 `Ctrl+P` (Windows)
3. 选择"另存为 PDF"
4. 调整页边距、方向等选项

### 方法 2：命令行（需要 wkhtmltopdf）

```bash
wkhtmltopdf --encoding utf-8 report.html report.pdf
```

### 方法 3：Python 脚本（需要 WeasyPrint）

```python
from weasyprint import HTML

HTML('report.html').write_pdf('report.pdf')
```

---

## 常见问题

**Q: 中文显示乱码？**
A: 确保文件编码为 UTF-8，且 HTML meta 标签正确设置 charset。

**Q: 表格太宽，超出页面？**
A: 表格会自动响应式处理。打印时选择"缩小以适应页面"。

**Q: 目录不显示？**
A: 需要添加 `--toc` 参数，且 Markdown 文件需要有标题。

**Q: 如何修改字体？**
A: 编辑对应主题的 CSS 文件，修改 `body` 的 `font-family` 属性。
