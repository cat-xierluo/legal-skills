---
name: md2word
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.3.2"
license: MIT
description: Markdown转Word文档技能。将Markdown文档转换为符合中文排版标准的专业格式Word文档，支持多种预设格式。适用于正式文档、论文、报告等需要规范排版的文档转换。
---

# Markdown转Word文档Skill

## 概述

将 Markdown 文档转换为符合中文排版标准的 Word 文档。支持完整的 Markdown 语法，自动应用专业格式设置。

## 依赖要求

### Python 依赖

```bash
pip install python-docx Pillow beautifulsoup4 PyYAML
```

### 可选依赖

```bash
npm install -g @mermaid-js/mermaid-cli   # Mermaid 图表渲染
brew install librsvg                       # SVG→PNG（推荐，rsvg-convert）
# 或 pip install cairosvg                  # SVG→PNG 备选
# 或 npm install puppeteer                 # SVG→PNG 备选（scripts/svg2png.js）
```

> 正文内联 `<svg>...</svg>` 块会自动渲染为 PNG 嵌入，渲染优先级 rsvg-convert → cairosvg → svg2png.js(puppeteer)，三者任一即可；全部不可用时降级为代码框显示 SVG 源码。

## 快速开始

主转换脚本：`scripts/md2word.py`

```bash
# 基本转换
python scripts/md2word.py input.md output.docx

# 使用预设格式
python scripts/md2word.py input.md --preset=academic

# 使用自定义配置
python scripts/md2word.py input.md --config=my-config.yaml

# 脚注/尾注模式（默认 footnote 页面脚注；endnote=文档末注释+上标编号）
python scripts/md2word.py input.md --notes=endnote

# 全书合并：多章 md → 单 docx（目录+按输入文件分章+页眉，配合 -o 指定输出）
python scripts/md2word.py --book ch01.md ch02.md ch03.md -o book.docx --preset=book-publish
```

> `--book` 只把相邻输入文件的边界转换为新 section。章节正文里的 Markdown 水平线 `---`、`***`、`___` 在单章和全书模式下都会保留为水平线，不承担分页或分章语义。

> 同一 `[^label]` 在正文重复出现时，原生 `footnote` 模式会为每次出现生成独立的 Word 脚注，并重复相同定义文本，确保每个引用位置都能看到脚注；`endnote` 模式仍复用同一编号与一条尾注定义。

> 原生 `footnote` 模式下，两个脚注标记在源码中直接相邻时，输出会在两个上标之间加入一个同为 9pt 上标的 NBSP；源码已有空格或标点时不额外添加。页面脚注段落固定为段前段后 0、单倍自动行距；`endnote` 不应用这两项规则。

> 页面脚注在普通正文与 Markdown 引用块（`>`）中都可使用；引用块内的 `[^label]` 会生成原生 Word 脚注引用，不会作为字面标记留在正文，同时保留引用段落和加粗等行内格式。

> 所有 Markdown 引用块统一读取一套 `quote` 配置，不按“本章导读”“案例”等文字标签分流。内置预设统一使用与 `confirmed` 状态一致的 `#EDF2F7`，样式为正文全宽、无可见边框的浅灰段落底纹；不使用表格容器，因此 Word 的“查看网格线”不会出现虚线外框。文字通过 `padding` 保留左右和首尾内边距；内部空引用行会生成同底色的 `paragraph_spacing` exact 空段，使多段 callout 保持一整块连续灰底。连续多个内部空引用行确定性折叠为一个，首尾空引用行忽略。

> 行内代码优先保护反引号范围：其中的 `_`、`*` 等 Markdown 标记按字面量保留，不会与相邻代码段拼成斜体或粗体；例如 `` `law_keyword` `` 会完整输出为一个代码 run。

> 普通技术标识内部的下划线按字面量保留：正文与 Markdown 表格中的 `payment_instance_id`、`API_SERVER_KEY` 等名称不会被解释为斜体或粗体。下划线强调须位于单词边界，明确的 `_斜体_`、`__粗体__` 与 `___粗斜体___` 仍按原语义渲染。

> 所有 fenced code block（包括 `text`、`markdown` 与无语言围栏）均沿用既有等宽、紧凑的代码内容样式；可通过 `code_block.content.space_before` 与 `space_after` 仅调整整个框与前后正文的垂直间距。

> Markdown 表格固定在页面正文可用宽度内；多列长表头会自动换行，转换器会统一表格总宽、网格列宽和单元格宽度，避免表格越过左右页边距。

> Markdown 与 HTML 数据表都由表格组件自身追加 `table.space_after` 固定高度留白（默认 6pt exact）；后续正文保持普通正文的 1.5 倍行距与 0 段前距。图片和图注不使用这项表格留白。

> 普通 Markdown 表题（如 `**表 10-5：标题**`）会自动水平居中并取消首行缩进；显式 `<div align="center">...</div>` 仍可继续使用。表题原有字号和粗体不受自动对齐影响。

## 配置系统

### 内置预设

预设信息从 YAML 文件动态读取，运行以下命令查看完整列表：

```bash
python scripts/config.py --list
```

常用预设：

- **legal** — 法律文书格式（默认）
- **service-plan** — 法律服务方案（含分层配色）
- **minimal** — 极简格式
- **academic** — 学术论文格式
- **report** — 工作报告格式
- **book-publish** — 中文书籍出版格式（正文宋体、标题黑体、TOC/页眉书名，配合 `--book` 全书合并导出）

> 完整配置见 `assets/presets/*.yaml`，设计说明见 `assets/theme-notes/`

### 自定义配置

复制配置模板并修改：
```bash
cp assets/config-template.yaml my-config.yaml
```

### Word 模板文件

将 `.docx` 模板放入 `assets/templates/` 目录，或使用 `--template` 指定。

**Word 模板 vs 配置文件**：
- **Word 模板**：控制视觉元素（页眉、页脚、Logo）
- **配置文件**：控制格式参数（字号、行距、页边距）

## 参考文档

- **配置参考**: [references/config-reference.md](references/config-reference.md)
- **样式映射**: [references/style-mappings.md](references/style-mappings.md)
- **使用示例**: [references/examples.md](references/examples.md)

## 所需权限与安全说明

本技能会调用本地脚本执行文档转换，涉及以下能力边界，请在使用前知悉：

### 本地代码执行

- `scripts/md2word.py` 通过 `subprocess.run` 调用外部渲染工具渲染图表与 SVG：
  - **Mermaid 图表**：调用 `mmdc`（MMDCCMD 环境变量 → 脚本同目录 `node_modules/.bin/mmdc` → 系统 PATH），仅渲染用户输入的 mermaid 代码，命令以参数数组拼接，不经过 shell 字符串拼接。
  - **SVG 渲染**：按优先级调用 `rsvg-convert` → `cairosvg` → `node scripts/svg2png.js`（Puppeteer）。内联 SVG 为不可信输入时，可能触发渲染器解析问题或资源消耗，请只转换可信来源的文档。

### 网络访问（默认启用）

- 转换含外部 URL 图片的 Markdown 时会**自动向任意 HTTP/HTTPS 地址发起请求**（`urllib.request`，超时 20s），用于下载图片嵌入 Word。
- 这是**默认行为**：外链图片会正常下载并嵌入文档；下载失败时降级为文字占位符。
- 请知悉风险：处理不可信 Markdown 可能触发 **SSRF**（访问内网地址）、向第三方泄露转换方 IP/时间等元数据、引入恶意或超大图片负载。请仅转换可信来源的文档。
- 上述下载请求不会上传文档内容，只按 Markdown 中的图片 URL 拉取图片。

### 环境变量读取

- `chart_handler.py` 读取 `MMDCCMD` 环境变量以定位 mermaid-cli 可执行文件（可选，未设置时回退到脚本同目录 node_modules 与系统 PATH）。

### 文件访问

- 读取用户指定的 Markdown 输入文件、`assets/templates/` 下的 Word 模板与 `assets/presets/` 下的 YAML 配置。
- 在输出目录生成 Word 文档（`--book` 模式会生成临时合并 Markdown，转换结束后自动删除）。

## 错误处理

- **文件编码**：自动检测 UTF-8 和 GBK
- **模板找不到**：使用默认格式创建新文档
- **Mermaid 失败**：降级为文本描述
- **图片过大**：自动压缩和调整尺寸

## 目录结构

```
md2word/
├── SKILL.md               # 本文档
├── CHANGELOG.md           # 版本记录
├── references/            # 参考文档
│   ├── config-reference.md
│   ├── style-mappings.md
│   └── examples.md
├── scripts/               # 转换脚本
│   ├── md2word.py         # 主脚本
│   ├── config.py          # 配置模块（含 --list 查看预设）
│   ├── extract_template_config.py  # 从 Word 模板提取配置
│   ├── formatter.py       # 文本格式化模块
│   ├── table_handler.py   # 表格处理模块
│   └── chart_handler.py   # 图表渲染模块
└── assets/                # 资源文件
    ├── presets/           # YAML 预设配置
    ├── theme-notes/       # 预设设计说明文档
    ├── templates/         # Word 模板文件
    └── config-template.yaml
```
