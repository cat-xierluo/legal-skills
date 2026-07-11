# 更新日志

本文件记录 md2word 技能的所有重要变更。

## [1.1.5] - 2026-07-11

### 修复
- **脚注 markdown 星号进 XML（footnote_handler）**：原实现把脚注 text 直接 `_xml_escape` 塞进单个 `<w:t>`，`*需律师现场确认*` 的星号原样进 footnotes.xml，Word 显示字面星号。新增 `_footnote_text_to_runs_xml()`：解析 `**bold**`/`*italic*`/`` `code` `` 转 Word runs（`<w:b/>`/`<w:i/>`/Consolas 等宽），既不显示字面星号、又保留斜体/粗体/代码格式。不处理 `_italic_`（避免下划线变量名误判）、嵌套与 `[link](url)`（留 follow-up）。
- **中文撇号误判为英文所有格（formatter.py isalpha）**：`convert_quotes_to_chinese` 原用 `prev_c.isalpha() and next_c.isalpha()` 保留英文缩写/所有格撇号（don't/O'Brien），但 `'需'.isalpha()` 在 Python 返回 True（中文属 Unicode Lo），导致「中文'中文」被误判为英文所有格、本该转中文单引号 ‘’ 却保留 ASCII `'`。修：加 `.isascii()` 限定，只 ASCII 字母-撇号-ASCII 字母保留。

### 验证（眼见为实）
- 单元测试：footnote runs 6 case ALL PASS（`*x*`→`<w:i/>`、`**x**`→`<w:b/>`、无字面星号；code/空/普通文本 OK）；convert_quotes_to_chinese 6 case（中文边界→中文单引号 ‘’；don't/O'Brien/API's→保留 ASCII `'`）。
- 集成验证：造含中文撇号 + 星号脚注的 md 转 docx（legal preset, footnote 模式）—— document.xml `需律师现场确认`→中文单引号、don't/API's 保留 ASCII；footnotes.xml 无字面 `*`、含 `<w:i/>`/`<w:b/>`、脚注拆 runs。

## [1.1.4] - 2026-07-09

### 改进
- **T139 表格配色规范对齐（方案 A · DEC-114）**：legal/book-publish preset 与 fallback config 的 table body 文字色从 `#1A202C` 统一改为 `#2D3436`（T139 深灰主色），配图风格规范配色保持一致。

### 文档完善
- **style-mappings.md 新增 T139 表格配色映射章节**：完整记录表头/表体/边框/圆角/斑马纹的配色映射关系与设计原则。

## [1.1.3] - 2026-07-07

### 改进
- **表格渲染套 FIGURES-OUTLINE 配图风格规范配色**：表头主蓝底 `#2C5282` + 白字 `#FFFFFF`，正文深色文字 `#1A202C`，隔行浅灰斑马纹 `#EDF2F7`，边框细线 `#CBD5E0`，四角单元格外边框变浅模拟圆角效果。配置项新增 `table.rounded_corners`、`table.header.background_color`、`table.row_even.background_color`、`table.row_odd.background_color`。legal 预设与 fallback config 同步更新。

### 技术优化
- 新增 `_apply_rounded_corners()` 函数（`table_handler.py`）：通过 OOXML `w:tcBorders` 为四角单元格单独设置外部边框（细线 + 浅色），模拟 CSS 圆角视觉层次。
- 新增 `_lighten_color()` 辅助函数：将十六进制颜色向白色混合，用于圆角边框的柔和过渡色。

## 待优化事项

### Word 格式微调（持续优化中）

**已完成（已并入 [1.0.3]）：**
- 表格中含格式文本（加粗等）的单元格未居中
- 二级/三级标题段前段后硬编码为 0pt
- 二级标题前自动插入空段落

**仍待观察/后续可能调整：**
- 四级标题的 space_before/space_after 同样硬编码为 0pt，是否需要读取配置
- 正文段落的段前段后间距（目前为 0pt），实际使用中是否需要微调
- 表格列宽自动分配策略，当前列宽是否合理
- 列表项的行距和缩进，与正文的协调性

## [1.1.2] - 2026-07-05

### 新增
- **每章脚注从 1 重置编号**（`--book` 全书合并 + `--notes=footnote` 模式）：中文出版常见诉求。实现路径：① 章间 `---` 由 `doc.add_page_break()` 改为 `doc.add_section(WD_SECTION.NEW_PAGE)`，每章成为独立 section（python-docx 新 section 默认 `header.is_linked_to_previous=True`，页眉书名保持、页码默认 continuous 不重置）；② `save` 前对每个 section 的 `sectPr` 注入 `<w:footnotePr><w:numRestart w:val="eachSec"/></w:footnotePr>`（OOXML CT_SectPr 序列里 footnotePr 是首位子元素，故 `insert(0, ...)`；已存在则仅覆盖 val，不重复注入）。新增 `footnote_handler.set_footnote_restart_per_section(doc)`。ch04（15 脚注）+ ch06（39 脚注）合并实测：ch06 第一个脚注渲染为 `1`（旧版全书连续编号下会延续为 16），符合预期。仅 `footnote` 模式生效；`endnote` 模式与单章模式不受影响（单章只有一个 section，重置无意义）。
- **同一脚注多次引用去重**：markdown `[^id]` 同一 id 在正文多次引用时，旧版给每次引用都新建一个 footnote（`footnotes.xml` 出现重复条目，如 ch06 的"元典开放平台 MCP 配置页"被引用 3 次就出现 3 条）。改为按 note_id 复用 `w:id`：`FootnoteManager` 加 `_id_map`，同一 note_id 复用 seq、`refs` 仅首次登记——正文多个 `footnoteReference` 指向同一 `w:id`，Word 自动渲染为同号、脚注块只一条（标准 markdown 多次引用同一脚注语义）。ch06 实测：footnotes.xml 条目 39→37，"MCP 配置页"重复 3→1。

### 改进
- **book-publish 代码字体 Consolas → JetBrains Mono**：`code_block.content.font` 与 `inline_code.font` 同步换为 `JetBrains Mono`（现代编程字体，0/O 与 l/I/1 区分清晰，印刷友好）。`east_asia_font` 仍为「等线」（代码里的中文）。
- **book-publish 代码框去外边框**：`code_block.content.border_color` `#D0D0D0`→`null`（保留浅灰底纹 `#F5F5F5`，去掉外边框，配图验证反馈）。
- **book-publish 字体方案对齐 legal（仿宋 + Times New Roman）**：正文 `宋体`→`仿宋`（`name_alt` 仿宋_GB2312）；标题 `黑体`→`仿宋` 并加 `font_alt: "Times New Roman"`（标题里的英文/数字走 Times，不跟随中文标题字体——修正旧版标题 `rFonts ascii="黑体"` 把英文也渲染成黑体的问题）。ch06 实测正文/标题 `rFonts` 均为 `eastAsia="仿宋" ascii="Times New Roman"`，加粗保留。引用块 `quote` 配置本就与 legal 一致（无视觉样式），未动。
- **book-publish 节标题样式对齐样章**：`level2`/`level3` 由 `indent:0, align:left`（西式顶格左对齐）改为 `indent:24, align:justify`（中文节标题首行缩进 2 字符 + 两端对齐）。ch06 二级标题实测 `firstLine` 0→480、`jc` left→both，与样章一致。

### 修复
- **图片路径 URL 解析 NameError**：`md2word.py` 处理 markdown 图片 `![](...)` 时调用 `unquote()`，但顶部仅 `import urllib.parse` 未导入 `unquote` 符号，遇任意图片即 `NameError: name 'unquote' is not defined` 中断生成。改为 `urllib.parse.unquote(...)`（复用现有 module import，零新增依赖，与同文件 `urllib.request.Request` / `urllib.request.urlopen` 风格一致）。ch06（含截图 + 39 个 `[^id]` 脚注）实测重新生成通过，footnote 模式端到端 OK。

## [1.1.1] - 2026-06-25

### 修复（书稿实测反馈）
- **行内代码样式**：字体改等宽 Consolas（原 Times New Roman 与正文无区分，看着像没渲染）+ 浅灰底（`inline_code.background_color`），与代码块风格一致。`inline_code` 配置加 `east_asia_font` / `background_color`。
- **代码框语言标签**：默认不显示 `[python]`/`[markdown]` 等（`code_block.label.enabled` 默认 false）。
- **SVG 清晰度**：渲染 zoom 3→6；嵌入 target_dpi legal 260→400 / book-publish 300→600（SVG PNG 不再被过度下采样）。
- **图注居中**：识别 `**图 X-X：...**` / `图 X-X：` 段落，居中、无首行缩进、小一号字（原被当正文首行缩进）。实测 ch11 13 个图注全部居中。

## [1.1.0] - 2026-06-24

### 新增
- **脚注/尾注双模式**（`--notes=footnote|endnote`，默认 footnote）：支持 markdown `[^id]` 引用 + `[^id]: 定义`。
  - `footnote`：Word 原生页面脚注（正文 footnoteReference + save 后 post-process 注入 footnotes.xml part，含 separator/continuationSeparator，自包含内联格式不依赖 styles.xml）。
  - `endnote`：文档末“注释”小节 + 正文上标编号（伪 endnote，因 Word 原生 endnote 只能放文档末、不能“每章末”）。
  - 全书合并时脚注 id 自动加章前缀（`[^1]`→`[^1-1]`）防跨章冲突。
- **内联 SVG → PNG 渲染**：识别正文中的 `<svg>...</svg>` 块，渲染为 PNG 嵌入。渲染优先级 `rsvg-convert` → `cairosvg` → `svg2png.js`(puppeteer)，全部失败则降级为代码框显示源码。
- **全书合并 `--book`**（配合 `book-publish` 预设 + `-o/--out`）：多章 md → 单 docx，含目录域（TOC field，Word 中 F9 更新）、章间分页、页眉书名。
- **book-publish 预设**：中文书籍出版规范（正文宋体、标题黑体、图片 300dpi、TOC/页眉书名）。
- 新增脚本：`footnote_handler.py`（脚注/尾注）、`svg_handler.py`（SVG 渲染编排）、`svg2png.js`（复用自 svg-book-illustrator，puppeteer 降级路径）。

### 改进
- **代码块出版级样式**：等宽字体（Consolas/等线）+ 浅灰底纹（w:shd）+ 细边框（w:pBdr，相邻代码行自动连成完整框）+ 关闭拼写检查（w:noProof）。
  - `code_block.content` 新增配置项：`east_asia_font`、`background_color`、`border_color`、`border_size`、`no_proofread`（未配置时向后兼容，行为同旧版）。
  - `code_block.label` 新增 `enabled`（可隐藏语言标签）。

### 依赖
- SVG 渲染（任一即可）：`rsvg-convert`（brew install librsvg，推荐）/ `cairosvg`（pip）/ `svg2png.js`（需 puppeteer，已内置脚本）。

## [1.0.3] - 2026-06-09

### 改进
- **HTML/CSS 对齐语法扩展**：原脚本只支持 CSS `style="text-align: ..."` 写法，现扩展为同时支持 HTML `align` 属性
  - 支持 `<div align="right">` / `<div align=right>`（无引号） / `<div align='right'>` 三种写法
  - 大小写不敏感：`<DIV ALIGN="RIGHT">` 也能正确识别
  - 支持中文引号（`align="right"`）
  - 块级标签范围扩展到 `span` / `section` / `article`（原仅 `div` / `p`）
  - 重构对齐解析为独立函数 `formatter.extract_alignment(style_attr)`，便于后续任务（HTML 样式扩展）复用
- **模板加载行为变更（默认关闭）**：`find_template_file()` 默认返回 `None`（`auto=False`），解决"默认 docx 带了律所 logo 页眉"问题
  - 根因：原 `find_template_file()` 默认会从 `assets/templates/` 自动加载第一个 `.docx` 模板，模板 header 含律所 logo
  - 用户显式需要时可用 `--template path/to/file.docx` 或新加的 `--auto-template` 开关
  - **`create_word_document(template_file=None)` 显式不加载模板的行为保持不变**（向后兼容）

### 修复
- **表格中含格式文本（加粗等）的单元格未居中**：修复 `table_handler.py:274` `parse_table_cell_formatting()` 缺少段落对齐设置（沿用 [1.0.2] 之后的格式微调）
- **二级/三级标题段前段后硬编码为 0pt**：改为读取 `formatter.py:358-359, 366-367` 中 `titles.levelN` 配置值（legal 预设为 9pt）
- **二级标题前自动插入空段落导致多余空行**：移除该逻辑，间距由标题样式的 `space_before` / `space_after` 控制
- **四级标题段前段后硬编码为 0pt**：`formatter.py:374-375` 改为读取 `titles.level4` 配置（与 H1-H3 对齐），未配置时回退 0pt。用户调 `legal.yaml` 的 `titles.level4.space_before/space_after` 现在生效。

### 技术优化
- **测试基建**：建立 `pytest` 测试体系（`pytest.ini` + `tests/conftest.py` + `.venv/`），含 6 个端到端测试（`tests/test_html_alignment.py`）、17 个 `extract_alignment` 单元测试（`tests/test_extract_alignment.py`）、5 个模板加载测试（`tests/test_template_loading.py`）、4 个标题间距测试（`tests/test_heading_spacing.py`），全部 32 个测试通过
- **解析函数抽离**：将 HTML 对齐解析从主流程 `md2word.py` 抽到 `formatter.extract_alignment`，明确职责边界
- **依赖防护**：`.venv/` 包含 `pytest` / `python-docx` / `beautifulsoup4` / `Pillow` / `PyYAML`，完整可运行环境

### 文档完善
- **TASKS.md 结构化**：从简单 bullet 升级为结构化任务卡片（字段：优先级 / 关联文件 / 估计工作量 / 依赖 / 背景 / 验收）；原 8 条任务按"已完成/高/中/调研/远期"5 档重排，所有远期任务补全详细说明

## [1.0.2] - 2026-04-11

### 新增
- **外部URL图片支持**: 支持从 Markdown 中的外部 URL 图片自动下载并嵌入 Word 文档
  - 新增 `download_external_image()` 函数，通过 `urllib.request` 下载外链图片
  - 支持本地路径图片和 HTTP/HTTPS 外链图片
  - 自动居中插入图片，复用现有 `_postprocess_image_for_word()` 和 `insert_image_to_word()` 管线
  - 图片下载失败时自动降级为文字占位符 `[图片: alt文本]`
  - 修复正则表达式以兼容 URL 中含括号的情况（如 `no_upscale()?imageUrl=...`）

### 文档完善
- 2026-04-22：按独立仓库 README 新规范重写首页，补充典型场景、预设范围、可执行安装命令、使用示例、边界说明、关键文件入口、Legal Skills 关联项目导流、作者联系入口和微信二维码

## [1.0.1] - 2026-02-11

### 修复

- **导入错误修复**: 修复模块化重构后导致的 `ImportError: cannot import name 'get_config' from 'config'`

  - 将 `get_config()` 和 `set_config()` 函数从 `md2word.py` 移至 `config.py`
  - 这些函数被所有子模块（formatter.py, table_handler.py, chart_handler.py）依赖，应属于配置管理模块
  - 修复了 v1.0.0 重构时引入的循环导入问题

## [1.0.0] - 2026-02-10

### 重构
- **脚本模块化拆分**: 将 1955 行的单文件脚本拆分为 4 个模块
  - `md2word.py`: 主入口 + 核心转换流程（800 行，减少 59%）
  - `formatter.py`: 文本/段落格式化模块（388 行）
  - `table_handler.py`: 表格处理模块（532 行）
  - `chart_handler.py`: 图表渲染模块（248 行）
  - 便于扩展新的图表类型支持

- **依赖清理**: 移除冗余导入
  - 移除未使用的 `sys`, `requests`, `base64`, `io` 等模块
  - 移除未使用的 `WD_TAB_ALIGNMENT` 等 docx 枚举
  - `BeautifulSoup` 移至 table_handler.py

## [0.3.0] - 2026-02-10

### 变更
- **Skill 结构重构**: 按照 Skill 开发指南最佳实践重构
  - 新增 `references/` 目录，实现渐进式披露
  - 新增 `references/config-reference.md`：配置架构快速参考
  - 新增 `references/examples.md`：使用示例和常见场景
  - 精简 SKILL.md（从 ~350 行减至 ~90 行）
  - 简化 `scripts/md2word.py` 头部注释
  - 移除 `scripts/requirements.txt`（依赖在 SKILL.md 中说明）

- **描述更新**: SKILL.md frontmatter description 更新为更通用的表述
  - 去除"法律文书"的限定性描述
  - 改为"符合中文排版标准的专业格式"
  - 强调适用于正式文档、论文、报告等多种场景

### 改进
- 配置参考文档指向 `assets/presets/*.yaml` 避免重复
- 参考文档与 SKILL.md 通过链接实现渐进式披露
- 文档结构更清晰，便于维护和扩展
- 移除 references 文档中的目录，保持简洁

## [0.2.1] - 2026-02-10

### 修复
- **引号转换修复**: 修复英文引号转中文引号的左右配对问题
  - 将"上下文感知"逻辑改为更可靠的"交替状态机"方法
  - 修复了连续引号都变成闭引号的bug
  - 修复了部分引号未被正确转换的问题
  - 使用Unicode转义序列避免Python语法警告

### 变更
- **文档中文化**: SKILL.md 和 CHANGELOG.md 完全中文化
  - frontmatter 的 name 和 description 改为中文
  - 版本记录标题翻译（Added → 新增，Changed → 变更等）

## [0.2.0] - 2026-01-29

### 新增
- **配置系统增强**: 添加完整的配置选项到 YAML 模板和预设文件
  - 代码块格式配置: 语言标签、内容字体、缩进、行距
  - 行内代码格式配置: 字体、字号、颜色
  - 引用块格式配置: 背景色、缩进、字号
  - 数学公式格式配置: 字体、字号、斜体、颜色
  - 图片设置配置: 显示比例、最大宽度、目标DPI
  - 分割线设置配置: 字符、重复次数、字体、颜色
  - 列表设置配置: 无序列表、有序列表、任务列表标记
  - 表格增强配置: 行高、单元格边距、垂直对齐、标题/正文格式

### 变更
- **md2word.py**: 重构所有格式化函数使用配置读取
  - `add_horizontal_line()`: 使用 `horizontal_rule` 配置
  - `add_code_block()`: 使用 `code_block` 配置
  - `add_quote()`: 使用 `quote` 配置
  - `add_bullet_list()`, `add_task_list()`: 使用 `lists` 配置
  - `set_run_format_with_styles()`: 使用 `inline_code` 和 `math` 配置
  - `set_table_run_format()`, `set_table_cell_format()`: 使用 `table` 配置
  - `create_word_table()`, `create_word_table_from_html()`: 使用 `table` 配置
  - `insert_image_to_word()`: 使用 `image` 配置
  - 新增 `hex_to_rgb()`: 十六进制颜色转换函数

- **所有预设文件**: 同步新增配置选项
  - `legal.yaml`: 法律文书格式预设（与原始脚本完全一致）
  - `academic.yaml`: 学术论文格式预设
  - `report.yaml`: 工作报告格式预设
  - `simple.yaml`: 简单文档格式预设

- **config-template.yaml**: 更新配置模板，包含所有新配置选项

## [0.1.0] - 2026-01-29

### 新增
- **初始版本**: md2word 技能 - Markdown转Word配置化工具
  - YAML 配置系统支持
  - 4 种内置预设格式 (legal/academic/report/simple)
  - 自定义配置文件支持
  - Word 模板文件支持 (.docx)
  - 命令行参数: `--preset`, `--config`, `--list-presets`, `--template`

### 功能特性
- 完整的 Markdown 到 Word 转换
- 页面格式设置 (A4, 页边距)
- 字体和字号配置
- 标题格式配置 (4 级标题)
- 段落格式配置 (行距、首行缩进、对齐)
- 页码自动生成 (支持 1/x 格式)
- 引号自动转换 (英文 → 中文)
- 表格转换支持 (Markdown 和 HTML 表格)
- 图片插入和优化
- Mermaid 图表本地渲染
- 格式支持: **加粗**、*斜体*、<u>下划线</u>、~~删除线~~
- 代码块和行内代码支持
- 数学公式支持 ($LaTeX$)
- 列表支持 (无序、有序、任务列表)
- 引用块支持

### 目录结构
```
md2word/
├── assets/
│   ├── presets/          # YAML 格式预设
│   ├── templates/        # Word .docx 模板文件
│   └── config-template.yaml
├── scripts/
│   ├── md2word.py       # 主转换脚本
│   └── config.py        # 配置管理模块
└── SKILL.md             # 技能文档
```
