# 设计版 Word 管线

`legal-proposal-generator` 先生成逐案 Markdown，再由 `render.js` 调用 `builders.js` 输出可编辑的 `.docx`。视觉组件从已验证的 `legal-proposal-word` 资产包迁入，与 `legal-proposal-designer` 的 C/D/E/F 封面和律所棕色系对应。`legal-proposal-designer` 继续承载 HTML/PDF 交付及后续设计化页面。

## 与 HTML/PDF 模板的版式关系

- C 封面的色带、标题、三栏信息线和页脚分隔线按 designer 的 `cover-geo.html` 对齐；D/E/F 保留各自装饰构图。封面不编入正文页码。
- 正文采用 HTML `.prose` 的 12pt、2.1 倍行距、两字首行缩进；无序列表保留圆点，有序列表保留编号；引文使用带内边距的浅灰卡片。正文从第 1 页起算。
- 完整版附页各自成节，页脚显示“服务团队”“典型案例”“律所简介”“荣誉资质”，与 HTML 后部页的页名相同。
- HTML/PDF 正文页脚可显示“当前页 / 正文总页数”；Word 当前只显示可更新的“第 N 页”。`SECTIONPAGES` 分节总页数字段在 LibreOffice 导出时为空，静态写入总数又会在编辑正文后失效。若客户需要精确的 N/M，请在最终定稿的 PDF 中确认；不要把临时页数写死在可编辑 Word 中。
- HTML 的 flex/grid、SVG/Mermaid 和 CSS 像素级位置无法在 Word 跨 WPS、Microsoft Word、LibreOffice 保证完全一致。需严格复现设计图或复杂可视化时，使用 designer 的 HTML/PDF 路径。
- Word 默认按封面元数据补落款；HTML 按源稿内容渲染。同源稿比较时，若源稿没有落款，可在 Markdown frontmatter 写 `signature: false` 关闭 Word 自动落款；正式交付仍应检查两种格式的落款内容一致。

## 安装与运行

**主路径依赖**：Node.js ≥ 22 和 `docx`。首次运行前安装：`npm install -g docx`。无需 Python 或 LibreOffice 即可生成 Word。若 `docx` 安装在全局目录，使用 `NODE_PATH=$(npm root -g)` 让 Node 找到它。

```bash
NODE_PATH=$(npm root -g) node word/render.js \
  --input /绝对路径/方案.md --output /绝对路径/方案.docx --cover C

# 完整版：选择承办律师，读取本地团队配置，追加团队、裁判文书、律所和荣誉页
NODE_PATH=$(npm root -g) node word/render.js \
  --input /绝对路径/方案.md --output /绝对路径/方案-完整版.docx \
  --cover F --full --team-config config/team-config.md --lawyers 张三,李四
```

在本 Skill 根目录执行上述命令。`--cover` 可选 C（顶部几何，默认）、D（对角斜切）、E（底部反转）、F（瑞士网格）。`--full` 的后部页数由律师与材料数量决定，不保证固定 10 页。团队配置默认读取 `config/team-config.md`，可用 `--team-config` 指向另一份本地文件。找不到选定姓名或引用图片不存在时立即报错。交付裁判文书图片前核对脱敏。

## Markdown 输入契约

```markdown
---
law_firm: 示例律师事务所
client: 示例公司
lawyer: 张三
date: 2026年9月23日
subtitle: 专项服务
---
# 某项目法律服务方案

## 一、项目概况

根据现有材料，拟开展**专项核查**。

### （一）服务范围

- 核对业务资料
- 沟通风险和建议

| 阶段 | 内容 |
| --- | --- |
| 一 | 资料核查 |
```

封面必需 `law_firm`、`client`、`lawyer`、`date` 和标题（首个 `#` 或 frontmatter 的 `title`）。已有 Markdown 没有 frontmatter 时，可通过 `--law-firm`、`--client`、`--lawyer`、`--date`、`--title`、`--subtitle` 补充。正文支持 `##` 章标题、`###` 及更低层小节、段落、`**加粗**`、简单列表、表格和 `>` 引文。正文中的代码块、原生 HTML 与图片会报错，避免静默漏掉内容；复杂图表可改用 JSON blocks 或另行排版。Word 路径生成正文时，不要把 `team-config.md` 的 HTML 表格复制入 Markdown；完整版会直接读取该配置。

## 结构化 JSON 输入

复杂表格或引文可将输入写成 `.json`，结构为 `{"cover": {...}, "blocks": [...]}`。`cover` 字段为 `lawFirm/title/subtitle/client/lawyer/date/badge`；`blocks` 的类型为 `h1`、`h2`、`body`（`text` 或 `runs: [{"t":"...","bold":true}]`）、`list`、`quote`（`label/lines`）、`table`（`headers/rows/widths/boldLastCol`）。`signature: false` 可关闭自动落款。JSON 的所有文本须来自方案内容和已核实资料，不能由排版器补造事实。

## 少量变量的 OOXML 模板通道

`legal-proposal-OOXML-template.docx` 与 `template.js` 是样式演示和 token 骨架，正文示例并非真实方案。仅当已有固定正文、只替换少量字段时使用 `fill.py`；逐案完整方案使用 `render.js`。

**此通道依赖**：Python 3 和 `python-docx`。首次使用前安装：`python3 -m pip install python-docx`。

```bash
python3 word/fill.py word/legal-proposal-OOXML-template.docx --list
python3 word/fill.py word/legal-proposal-OOXML-template.docx -o /绝对路径/填充版.docx \
  --set LAW_FIRM=示例律师事务所 CLIENT=示例公司
```

`fill.py` 会报告剩余 token；存在未填 token 或正文样例章时不能当作正式方案交付。修改模板时用 `NODE_PATH=$(npm root -g) node word/template.js /绝对路径/新模板.docx --cover=C` 重建，再逐页验收。

## 验收

1. 检查 DOCX 能打开、正文标题/表格/页脚/图片完整，且没有未替换的 `{{TOKEN}}`。
2. 用 LibreOffice 导出 PDF 并逐页看封面、表格分页、落款和后部页。macOS 如果无头 LibreOffice 中文变方框，可先设置 `FONTCONFIG_FILE=/opt/homebrew/etc/fonts/fonts.conf`；应确认 PDF 已嵌入中文字体。代码改动后可运行 `python3 -m unittest discover -s word/tests -v` 检查分节页脚、列表和引文结构。
3. 正式交付前在实际 WPS 和 Microsoft Word 各打开一次，核对封面没有变两页、照片不变形、表格列宽和页脚正常。当前环境无法替代这一步的真实客户端验收。

跨引擎不变量：封面 exact 行总高不得超过页面可用高度；C/D/E/F 均须有封面页脚；装饰 PNG 只承载几何图形，色带由原生表格底色绘制；多列表格使用固定布局；段落组件直接放入 children，不能嵌套 Paragraph。完整事故说明见 `builders.js` 注释与交接文档。
