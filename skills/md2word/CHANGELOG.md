# 更新日志

本文件记录 md2word 技能的所有重要变更。

## [1.3.4] - 2026-08-26

### 新增
- **书籍尾部模块原生分页（DEC-021）**：新增 `pagination.page_break_before_headings` 精确标题列表。`book-publish` 默认配置“本章小结”“动手练习”，单章和 `--book` 均在命中标题段自身写入 `w:pageBreakBefore`；其他预设、硬编码 fallback、配置模板和模板提取基底默认空列表。
- **精确且隔离的匹配**：只对 Markdown `#` 至 `####` 标题去除首尾空白后完整匹配。正文、HTML 表题、代码块和“本章小结与展望”等包含或近似文字不触发；命中不插入空段、分页 run 或新 section，标题既有字号、粗体、缩进与段间距保持。

### 文档完善
- 更新 `SKILL.md`、README、配置参考和样式映射，新增 DEC-021 / Task-014，并把根 README 的 md2word 版本与最近更新摘要同步为 v1.3.4。

### 验证
- 完整回归 23/23、`py_compile`、7/7 YAML 解析与 `git diff --check` 通过。端到端 fixture 覆盖 H2“本章小结”、H2/H3“动手练习”以及正文/HTML 表题/代码块/近似标题负例；book-publish 恰好 3 个 `w:pageBreakBefore`、0 个分页 `w:br`、1 个 section、0 个额外空段，legal 与自定义空列表均为 0，H2/H3 原格式不变。
- 全书 15 章静态扫描得到 15 个 H2“本章小结”与 12 个“动手练习”（H2 11、ch14 H3 1），共 27 个精确目标标题。真实 ch12 得到 2 个原生标题分页、0 个分页 `w:br`、1 个 section；同时保留 10 张表 + 10 个表后 spacer、6 个 quote 段（含 2 个同底色 spacer）、11 组图片/图注和 1 个脚注。DOCX 包完整、15 个 XML well-formed，SHA-256 为 `e1121d10d206b4466d86264f5c57a679f6b8401f081f447cef0ff21f74d57be5`。按用户要求不打开 Word、不做逐页 GUI 验收。
- 官方 `quick_validate.py` 仍因本仓要求保留的 `author`、`homepage`、`version` frontmatter 键退出 1，记为 `NOT_VERIFIED`；未删除仓库要求字段。

## [1.3.3] - 2026-08-26

### 修复
- **引用框与代码框背景完全同色（DEC-020）**：根据用户视觉确认后的颜色纠偏，全部内置预设、fallback config、配置模板和模板提取基底把 `quote.background_color` 从 `#EDF2F7` 统一为 fenced code block 同款中性浅灰 `#F5F5F5`；承载 padding 的不可见同色 paragraph border 与缺省 fallback 同步。
- **连续 callout 结构保持**：v1.3.2 的 paragraph callout、同底色 6pt exact 内部 spacer、连续空行折叠、无引用 `w:tbl`、首尾 padding/块外间距全部不变；数据表 6pt exact spacer 与图片/图注链路不变。

### 文档完善
- 更新 `SKILL.md`、README、配置参考和样式映射，明确引用框复用 `code_block.content.background_color` 的视觉 token；两项仍分别显式配置，允许高级用户独立覆盖。新增 Task-013 / DEC-020，DEC-020 仅 supersede DEC-019 的颜色选择，不回退其连续 shaded spacer 决策。

### 验证
- 完整回归 22/22、`py_compile`、7/7 YAML 解析与 `git diff --check` 通过；测试额外断言 `book-publish` / `legal` 的 quote 背景均等于各自 `code_block.content.background_color`，且值为 `#F5F5F5`。多段引用、灰底 exact spacer、脚注/粗体/列表与无引用表格断言继续通过。
- 真实 ch12 得到 10 张数据表 + 10 个表后 spacer、6 个 quote 段（4 个内容段 + 2 个同底色 exact spacer）、11 组图片/图注和 1 个脚注；全部 quote shading/border 为 `F5F5F5`，无引用表格，图注既有 `3pt/8pt + 1.2` 节奏不变。DOCX 包完整、15 个 XML well-formed，SHA-256 为 `75dc5691c7676602e837a6e7b7b2f87289190918184238429b8c50724b590baa`。按用户要求不打开 Word、不做逐页 GUI 验收。
- 官方 `quick_validate.py` 仍因本仓要求保留的 `author`、`homepage`、`version` frontmatter 键退出 1，记为 `NOT_VERIFIED`；未删除仓库要求字段。

## [1.3.2] - 2026-08-26

### 修复
- **多段引用灰底不再出现白缝（DEC-019）**：内部空引用行不再写成上一内容段的 `space_after`，改为同底色空白 callout paragraph。该 spacer 段前/段后为 0、行高读取 `quote.paragraph_spacing`（默认 6pt exact），只带左右同色 padding border，不重复 top/bottom padding；普通内容段内部间距保持 0，整个框只在首/末段保留块外 6pt。
- **连续空行确定性归一**：连续多个内部 `>` 空行折叠为一个 shaded spacer；首尾空引用行忽略，由首尾 padding 提供留白。脚注、粗体、列表 marker 和引用不生成 `w:tbl` 的规则保持。
- **引用灰统一为 confirmed token**：全部内置预设、fallback config、配置模板和模板提取基底把 `quote.background_color` 统一为 `#EDF2F7`，同色不可见 paragraph border 同步，避免引用框与本书 confirmed 状态出现两级浅灰。

### 文档完善
- 更新 `SKILL.md`、配置参考、样式映射和使用说明，明确 shaded exact spacer 的 OOXML 语义与连续空行折叠规则；Task-010 补记已合并 PR #97 / merge `2c3ff091`。

### 验证
- 完整回归 22/22、`py_compile` 与 7/7 YAML 解析通过。fixture 端到端断言连续空引用行折叠为 1 个 shaded spacer，多段案例为 3 个内容段 + 2 个 `EDF2F7` exact spacer；整个 quote body 每段均有同色 shading/border，内容段内部间距为 0，spacer 只有左右 border，脚注/粗体/列表保持且不产生引用表格。
- 真实 ch12 得到 10 张数据表 + 10 个既有表后 spacer、6 个 quote 段（导读内容 1 + 案例内容 3 + 案例灰底 spacer 2）、11 组图片/图注和 1 个导读脚注；全部 quote shading/border 为 `EDF2F7`，图注既有 `3pt/8pt + 1.2` 节奏不变。DOCX 包完整、15 个 XML well-formed，SHA-256 为 `80216357de8e5c4b4b6f7f5c0cb908aad658fa71afa40b5566ed9a4c51aa8527`。用户明确自行核实桌面示例视觉，本轮不打开 Word、不做逐页 GUI 验收。
- 官方 `quick_validate.py` 仍因本仓要求保留的 `author`、`homepage`、`version` frontmatter 键退出 1，记为 `NOT_VERIFIED`；未删除仓库要求字段。

## [1.3.1] - 2026-08-26

### 修复
- **引用框不再显示 Word 表格虚线（DEC-018）**：所有 Markdown `>` 导读/案例继续共用同一视觉语义，但由单单元格表格改为正文流中的段落灰底，输出不再为引用内容创建 `w:tbl`。Word 即使开启“查看网格线”也不会出现引用框虚线轮廓。
- **多段灰底只在整块首尾留垂直 padding**：每段保留左右 6pt；首段独占上 5pt、末段独占下 5pt，中间段不重复累计上下留白。空引用行才折算为 6pt `paragraph_spacing`；脚注、粗体、列表 marker、正文 12pt/1.5 倍行距继续保留。
- **数据表自行承载表后留白**：Markdown 与 HTML 表格统一读取 `table.space_after`，默认在表后追加一个 6pt exact 空段。随后正文仍为普通正文的段前/段后 0、1.5 倍自动行距；图片和图注不受影响。

### 文档完善
- 全部内置预设、fallback config、配置模板与模板提取基底改用 `quote.padding` 并加入 `table.space_after`；v1.3.0 自定义 `quote.cell_margin` 按 `20 twips = 1pt` 兼容迁移。配置参考与样式映射明确表格时代字段不再控制引用框。

### 验证
- 新增/更新端到端回归，精确断言引用内容不产生 Word 表格、浅灰底连续语义、同色 `single` 边界无可见轮廓、首/中/尾 padding、脚注/粗体/列表保持，并覆盖 v1.3.0 `cell_margin` 迁移；Markdown/HTML 数据表后各恰好一个 6pt exact spacer，下一正文样式不变，图片/图注链路未插入该 spacer。完整 `unittest` 22/22 通过。
- 真实 ch12 临时转换得到 10 张数据表及 10 个 exact 6pt spacer、4 个 paragraph callout 段（导读 1 + 案例 3）、0 个引用表格、11 组图片/图注和 1 个导读脚注；首/中/尾 padding、`pBdr → shd → spacing → ind` OOXML 顺序和图注既有 `3pt/8pt + 1.2` 节奏均通过结构断言。临时 DOCX SHA-256 为 `ded0d635396796918f1c3f08c816a7f81addf2f059b9fde77414cb917801630e`。用户明确由其自行核实桌面示例视觉，本轮不打开 Word、不做逐页 GUI 验收。
- 官方 `quick_validate.py` 因本仓规范要求的 `author`、`homepage`、`version` frontmatter 键退出 1，记为 `NOT_VERIFIED`；未删除这些仓库要求字段。

## [1.3.0] - 2026-08-26

### 改进
- **统一 Markdown 引用框（DEC-017）**：所有连续 `>` 引用块不再按“本章导读”“案例”等文字标签分流，统一渲染为单单元格 callout 表格。`legal` 与 `book-publish` 默认采用正文全宽、无边框 `#F5F5F5` 浅灰底；`tblW`、`tblGrid` 与 `tcW` 共用正文可用宽度，`tblInd=0`。
- **真实内边距与紧凑垂直节奏**：新增 `cell_margin`、`space_before`、`space_after`、`paragraph_spacing`、`first_line_indent`、`align` 等明确配置。左右/上下留白由真实 cell margins 承载；块外间距用 6pt exact spacer，引用空行折算为 6pt 段距，避免默认空段放大留白。
- **长案例可跨页**：引用表格不写 `w:cantSplit`，保留 Word 对单行长内容的跨页拆分能力；脚注、Markdown 粗体及正文 12pt / 1.5 倍行距继续保留。

### 文档完善
- `book-publish`、`legal`、其余内置预设、fallback config、配置模板和模板提取基底统一迁移到新的 `quote` 配置语义；配置参考明确旧 `left_indent_inches` 不再用于缩窄灰底块。

### 验证
- 新增同一 fixture 覆盖单段导读 + 页面脚注、多段案例 + 空引用行及普通正文；端到端断言两个 callout 的容器/样式一致、全宽、灰底、无边框、四边内边距、块外 exact 间距、块内段距、0 首行缩进、粗体和脚注保留，普通正文仍为 24pt 首行缩进、12pt / 1.5 倍行距；另保留最小引用列表回归，核对 bullet marker 与脚注均留在 callout 内。与 v1.2.9 回归合并后的完整 `unittest` 20/20 通过。
- 真实 ch12 临时转换得到 2 个 `md2word-quote` callout（导读 1 段、案例 3 段）和 10 张数据表；两个 callout 均为 `tblW/gridW/tcW=8504 twips`、`tblInd=0`、四边框 `nil`、灰底 `F5F5F5`、cell margins `100/120/100/120`，且 row 未写 `cantSplit`。导读脚注 1 个、两类标题粗体均保留。

## [1.2.9] - 2026-08-26

### 修复
- **普通技术标识内部下划线不再误解析为强调（DEC-016）**：underscore 斜体、粗体和粗斜体分隔符必须位于单词边界。正文与 Markdown 表格中的 `payment_instance_id`、`dispute_amount_band`、`manual_review_required`、`audit_log_summary`、`API_SERVER_KEY`、`main_chart_type`、`matter_id` 及 `foo__bar__baz` 均按字面量保留下划线，不产生意外斜体或粗体。
- **正文与表格规则统一**：把生产行内格式规则集中到 `formatter.py`，正文解析、Markdown 表格解析与表格格式预判共用同一规则源，避免表格继续以宽泛的 `_.*?_` / `__.*?__` 预判技术标识。星号强调、数学、HTML、脚注和图片路径不变，未引入第三方 Markdown 依赖。
- **明确的下划线强调保持兼容**：`_正常斜体_`、`__正常粗体__` 与 `___正常粗斜体___` 仍分别生成斜体、粗体与粗斜体；单词内部的 `foo__bar__baz` 不触发粗体。

### 验证
- RED：新增正文与 Markdown 表格两项回归后，v1.2.8 分别复现“下划线被吞并”和“表格格式预判误报”两类失败；GREEN：修复后 `python3 -m unittest discover -s skills/md2word/scripts -p 'test_*.py' -v` 为 19/19 通过。
- 真实书稿转换：ch14 的四个表格字段均各自构成 exact run，另有正文中的 `manual_review_required` 完整存在于一个可能包含相邻正文的普通 run；ch12 的 `main_chart_type` 与 ch04 的 `API_SERVER_KEY` 也分别完整存在于一个可能包含相邻正文的普通 run。所有匹配 run 的 `run.italic` 均为 `None`，OOXML 均无 `w:i`。
- `/tmp/md2word-v1.2.9-intraword-fixture.docx` 已生成，QuickLook 首屏缩略图 `/tmp/md2word-v1.2.9-quicklook/md2word-v1.2.9-intraword-fixture.docx.png` 经目检确认表格字段下划线完整，明确的斜体、粗体与粗斜体仍可见。

## [1.2.8] - 2026-08-25

### 改进
- **代码框外部垂直间距（DEC-015）**：为所有 fenced code block 的既有 `code_block.content` 配置新增 `space_before` / `space_after`。`book-publish` 预设均为 6pt，且只应用于单个框的首行段前与末行段后；多行框内部继续为 0 间距、1.2 倍行距。
- 不改变代码框的等宽字体、9pt 字号、浅灰底、边框策略、左右缩进或框内行距。

### 验证
- 端到端回归断言三行 `text` 代码框的首行段前 6pt、末行段后 6pt、中间行上下均为 0；同时保持 Courier New、9pt、1.2 倍行距与 `#F5F5F5` 底纹。

## [1.2.6] - 2026-08-25

### 修复
- **多列长表头不再把表格撑出正文区（DEC-013）**：保留既有 P80 分配逻辑，并增加总宽硬预算；当各列表头期望宽合计超过正文可用宽度时，每列先保留动态可读下限，再按相对需求压缩并允许表头换行。最终整数列宽总和不超过且铺满页面宽减左右页边距，不针对特定表格硬编码。
- **表格 OOXML 宽度统一**：Markdown 表格固定布局下，`tblW`、`tblGrid/gridCol` 与每行 `tcW` 使用同一组整数 twips，舍入余数确定性分配，避免 Word 在固定布局中按冲突宽度二次解释。
- **Markdown 与显式居中表题统一取消缩进**：`**表 X-Y：...**` 与不带粗体标记的同类表题自动水平居中、取消首行和左缩进；`<div align="center">**表 X-Y：...**</div>` 同样清除表题缩进。只在表题语义下覆盖段落对齐与缩进，普通居中 `<div>` 仍沿用正文缩进，表题字号/粗体与图注既有小一号样式不变。
- **引用块脚注不再显示字面标记（DEC-014）**：Markdown `>` 引用块的正文内容改走与普通正文相同的脚注解析入口；有效 `[^label]` 会生成原生 `w:footnoteReference` 与对应定义，不再把标签留在 `document.xml`。引用段落格式、导读加粗和引用块内列表 marker 保持不变。

### 验证
- 测试先行复现六列长表头合计 `17.84 cm > 15.00 cm`、表格 `tblW=auto/0` 与 grid/tcW 不同源、普通表题两端对齐且首行缩进三类失败；集成验收又复现显式居中表题虽有 `jc=center`、却仍继承 `firstLine=480`。修复后全量 15 项测试通过，并以普通居中 `<div>` 仍保留 24 pt 正文缩进作为反例，证明清零范围仅限表题。
- 真实第 7 章临时转换中，表 7-15 的 grid 总宽由 `10115 twips（17.8417 cm）` 收敛为 `8503 twips（14.9982 cm）`；`tblW=8503 dxa`、6 列 grid 与每行 6 个 `tcW` 完全一致，布局保持 `fixed`。
- 用已合并为 `<div align="center">**表 10-5：...**</div>` 的 canonical 第 10 章重新转换，修复后的表题为 `jc=center / firstLine=0 / left=0`，粗体与 `24 half-points（12 pt）` 字号保持不变。临时 DOCX 均保存在 `/tmp`，未提交仓库。
- 引用块脚注回归先复现“无 `footnotes.xml`、marker 原样进入正文”，修复后端到端断言正文无 marker、存在 `footnoteReference` 和定义，并验证导读加粗、引用段落缩进及列表 marker 未退化；全量由 15 项增至 16 项并全部通过。
- 真实 canonical ch10 转换后 `[^ch10-skills]` 为 0，导读段含 1 个脚注引用，全文引用/定义均为 `21/21`；真实 15 章合并转换的任意 `[^...]` 字面 marker 为 0，引用/定义/唯一引用 ID 均为 `131/131/131`，集合完全一致，保持 15 sections 与 118 张表。全书临时输出因位于 `/tmp`，既有相对截图路径降级为占位符，因此只作为脚注与结构证据，不作为视觉交付稿。

## [1.2.5] - 2026-08-25

### 修复
- **行内代码下划线不再误触发斜体（DEC-012）**：正文格式解析先识别反引号代码范围，并忽略起止标记落在代码范围内的非代码匹配。连续出现 `` `law_keyword` ``、`` `case_vector` `` 等标识时，下划线不再跨代码段配成 `_斜体_`，反引号会按行内代码语义移除，代码文本与样式完整保留。
- **既有外层格式行为保持**：仅阻止格式标记从代码范围内部起止；完整包围代码段的外层格式继续沿用现有解析结果，普通 `_正常斜体_` 不受影响。

### 验证
- RED：v1.2.4 将四个元典 Tool 名称转成 5 个正文 run，吞掉全部下划线、残留反引号，并把 `keyword…case`、`detail…case` 两段写成斜体。
- GREEN：新增正文级回归后，`law_keyword`、`case_vector`、`law_detail`、`case_detail` 均成为独立 Courier New 代码 run，无斜体；普通下划线斜体仍通过。完整回归由 11 项增至 12 项，全部通过。
- 真实 ch06 临时转换成功，目标四个 Word run 均为 Courier New、浅灰底且不含 `w:i`；`document.xml` 中异常字面反引号文本节点为 0。临时 DOCX SHA-256 为 `cdf81fb56861597313ea4bb42b809af67baa0719b4dea3ede8a6f0aee0e8b927`，仅保存在 `/tmp`，未覆盖交付稿。

## [1.2.4] - 2026-08-24

### 修复
- **相邻原生脚注编号可辨（DEC-011）**：仅当两个 Markdown 脚注标记在源码中直接相邻时，在两个 `w:footnoteReference` 之间插入一个 9pt 上标 NBSP；源码已有空格、逗号、顿号等字符时不额外插入，`endnote` 行为不变。
- **页面脚注段落收紧**：每个正数脚注段落显式写入段前 0、段后 0、单倍自动行距，避免脚注 34–40 一类连续脚注受默认段落间距影响而显得松散；separator 与 continuationSeparator 不变。

### 验证
- 测试先行准确复现旧行为：相邻引用之间没有 NBSP，正数脚注段落没有显式 spacing；修复后新增两项回归连同既有测试共 11 项全部通过。
- 真实 ch06 转换中，企查查段的脚注结构为 `ref 9 / NBSP / ref 10`，NBSP 仅 1 个且为上标 9pt；40 个正数脚注段落全部具有目标 spacing，引用 / 定义 / 唯一 ID 仍为 `40/40/40`、重复 ID 为 0，表 / 图 / 占位符维持 `0/13/0`。
- QuickLook 成功生成首屏缩略图与 HTML 预览，首屏未见明显异常；目标企查查段及脚注 34–40 不在缩略图可见范围，本机无 `soffice`，因此目标区域标记为 `NOT_VISUALLY_RENDERED`，未安装依赖或打开 Word。

## [1.2.3] - 2026-08-24

### 修复
- **重复原生脚注不再漏失（DEC-010）**：同一 Markdown `[^label]` 多次出现时，`footnote` 模式为每次引用分配独立 `w:id`，并在 `footnotes.xml` 写入内容相同的独立定义，避免多个 `w:footnoteReference` 复用同一 ID 时后续位置不显示脚注。
- **尾注兼容语义保持不变**：`endnote` 模式仍按 label 复用同一编号与一条尾注定义。

### 验证
- 测试先行准确复现旧行为：重复 footnote 的 2 个引用实际只有 1 个唯一 `w:id`；修复后新增的 footnote 与 endnote 端到端回归连同既有测试共 9 项全部通过。
- 真实 ch03 / ch04 / ch05 / ch06 单章转换的“引用 / 定义 / 唯一 ID”分别为 `6/6/6`、`22/22/22`、`16/16/16`、`40/40/40`，重复引用 ID 均为 0。
- 真实 15 章全书转换保持 15 sections、9 条水平线、118 表、180 图、0 图片占位符；源稿 128 个引用标记中，已解析的 121 个引用对应 121 条定义与 121 个唯一 ID，重复 ID 为 0。另 7 个章节导读引用块标记仍为既有字面文本缺口，不属于本次重复脚注修复。

## [1.2.2] - 2026-08-24

### 修复
- **全书章间边界与 Markdown 水平线解耦（DEC-009）**：`create_book()` 改用带固定高熵后缀的内部章间 marker 拼接章节，book parser 只对该 marker 创建 `WD_SECTION.NEW_PAGE`。章节正文中的 `---`、`***`、`___` 不再被误判为新 section，仍由 `add_horizontal_line()` 渲染。
- **移除单章首条水平线分页启发式**：单章模式不再把第一条 `---` 当作“封面分页”；三种 Markdown 水平线从第一条起均按原语义保留。

### 技术优化
- `scripts/test_regressions.py` 新增两项端到端回归：两章合并同时含章内水平线时必须恰好 2 个 section，并保留脚注分节重置、TOC 与页眉；单章首条 `---` 及后续 `***` / `___` 均须保留且不能产生 page break。

### 验证
- 测试先行红灯准确复现旧行为：两章输出 3 sections（预期 2），单章只保留 2/3 条水平线；修复后 `python3 -m unittest discover -s skills/md2word/scripts -p 'test_*.py' -v` 共 7 项全部通过。
- 真实 15 章书稿只读前向验证：15 sections、9 条水平线（ch12=1、ch13=8）、118 表、180 图、0 图片占位符，均符合预期。源稿共有 128 个脚注引用标记，其中 121 个生成 Word 脚注引用，7 个位于章节导读引用块内并保留为字面标记；该引用块解析缺口来自既有实现，本次章间边界修复未改该路径。

## [1.2.1] - 2026-08-11

### 回退
- **book-publish 代码字体 JetBrains Mono → Courier New（作者确认，终选 supersede 同性质 Consolas 候选）**：`code_block.content.font` 与 `inline_code.font` 同步改为 `Courier New`。理由双重：(i) 交付安全——md2word 不做字体嵌入、依赖印刷厂 Windows 字体库，`Courier New` 为 Windows 自带零替换风险，本书代码非主角，交付稳健优先于字形精致；(ii) 内容适配——本书代码以 SKILL 配置 / JSON / CLI / 文件路径等“配置 / 数据引用”为主，Courier New 打字机体在书里更贴正文、更合经典技术书代码惯例（Consolas 偏 IDE 风、对配置型代码略显跳脱）。supersede 早先 Consolas→JetBrains Mono 与本次 Consolas 候选的调整。`config.py` 基底保留 `Consolas` 作为 skill 级回退（不动），book-publish 显式覆盖为 `Courier New`，非“打架”。见本书仓 DEC-173。

## [1.2.0] - 2026-08-05

### 回退
- **恢复外链图片默认下载（作者确认）**：撤销 v1.1.9 的 `--allow-remote-images` 开关与默认关闭行为。Markdown 中的外部 URL 图片重新**默认自动下载并嵌入 Word**（原行为），下载失败时降级为文字占位符。移除 `ALLOW_REMOTE_IMAGES` 门控与 CLI 参数。
- 对应回归测试更新：删除开关相关用例，新增断言默认下载函数可用、开关已移除。

### 文档完善
- SKILL.md「所需权限与安全说明」网络访问章节改为"默认启用"，明确外链图片下载是默认行为，并保留对 SSRF/隐私风险的提示（仅建议处理可信来源文档）。

## [1.1.9] - 2026-08-05

### 新增
- **外链图片下载开关（--allow-remote-images）**：`download_external_image()` 的网络行为默认关闭。未加开关时，Markdown 中的外部 URL 图片不再自动下载，改为跳过并以文字占位符替代；仅当用户显式传 `--allow-remote-images` 才向外部 URL 发起请求。消除转换不可信 Markdown 时的 SSRF/隐私泄露面。

### 文档完善
- **新增「所需权限与安全说明」章节**：披露本地代码执行（mmdc / rsvg-convert / cairosvg / node puppeteer）、网络访问（默认关闭的外链图片下载）、环境变量读取（MMDCCMD）、文件访问范围等能力边界，对应外部安全审查（SkillSpector）的 MCP Least Privilege / Missing User Warnings / Context-Inappropriate Capability 类问题。

## [1.1.8] - 2026-07-20

### 新增
- 全书模式打开时自动更新目录域（enable_update_fields）：settings.xml 注入 updateFields，Word 打开自动生成目录与页码，免手动 F9
- add_toc 插入「目录」居中加粗标题（非 Heading 样式，避免标题自身被收进目录）

## [1.1.7] - 2026-07-14

### 回退
- **列宽算法回退到 v1.1.5 旧版（DEC-008）**：v1.1.6 的"短/中/长三分类自适应"导致部分表格列宽被过度拉长，作者反馈不满意。`_calc_column_widths` 回退到旧版简洁的"P80+min_needed"算法：短列先按 min_needed 保底，长列按 P80 比例瓜分页面剩余宽度。签名保留 `cell_lengths_real_per_col=None` 参数向下兼容（无实际作用）。

## [1.1.6] - 2026-07-13

### 改进
- **列宽分配智能化（DEC-007）**：`_calc_column_widths` 从"P80+min_needed"升级为"列类型自适应"。先把每列分成 short / mid / long 三类（用真实字数判定：表头≤4字 且 P50真实字≤8 且 P95真实字≤18/典型比≤3 判 short；表头≥6字 或 P75真实字≥12 或 P95真实字≥20 判 long），短列用真实字 P50 取小、给最小合理宽不参与瓜分，长/中间列用权重字 P80 比例瓜分余量。配合以下细节：
  - `adjust_table_column_width` 同时收集权重字+真实字两套 lens（dict 各自一列），传入 `_calc_column_widths` 新增 `cell_lengths_real_per_col` 参数。
  - 去掉 `seen.add(id(cell._tc))` 去重：python-docx 1.x 的 `row.cells` 对无合并多行表会返回大量重复 tc id，导致 lens 只收 4 行（表 4-1 实测只 4/13 行被收集，列宽严重偏差）。
- **表 4-1 列宽对比**（ch04-Agent 应用介绍与选择，2 列"项目/记录"）：旧版 4.19 cm / 10.80 cm（短列被同行 16 字长行 P80 拉宽）→ 新版 3.08 cm / 11.92 cm（短列固定基准、长列瓜分余量）。全书 36 张表 short 列普遍从 4-9cm 降到 2.1-3.1cm，长列瓜分到 10-12cm 上限。

### 验证（眼见为实）
- 仿真+实测：ch01-09 共 36 张表逐一读 gridCol dxa 值换算 cm，与改造前基线对比；表 4-1 单章 docx gridCol [3.08, 11.92]、全书 docx 内表 4-1 gridCol [3.08, 11.92] 完全一致。
- 转换 log ⚠️ 数 = 0（全书与 9 单章均无缺图/降级/占位符）。
- 短列覆盖度：ch01#T0 / ch02#T0,T1,T3 / ch05#T0,T1 / ch07#T0-T6,T8,T10-T12,T14-T16 / ch08#T1-T3 / ch09#T4 等多张表短列从旧 4-9cm 降到 2.1-3.1cm。

### 风险
- short 判定 `P95真实字≤18` 阈值在 110 表全集（仅 ch01-09 已测 36 表）需回归，未来跑完整书 14 章 ch10-14 需补一次 gridCol 扫描确认无退化。

## [1.1.5] - 2026-07-11

### 修复
- **脚注 markdown 星号进 XML（footnote_handler）**：原实现把脚注 text 直接 `_xml_escape` 塞进单个 `<w:t>`，`*需律师现场确认*` 的星号原样进 footnotes.xml，Word 显示字面星号。新增共享 inline parser：`footnote` 转 `<w:b/>`/`<w:i/>`/Consolas runs，`endnote` 同样拆成 python-docx runs；两条路径都不再显示字面星号/反引号。不处理 `_italic_`（避免下划线变量名误判）、嵌套与 `[link](url)`（留 follow-up）。
- **中文撇号误判为英文所有格（formatter.py isalpha）**：`convert_quotes_to_chinese` 原用 `prev_c.isalpha() and next_c.isalpha()` 保留英文缩写/所有格撇号（don't/O'Brien），但 `'需'.isalpha()` 在 Python 返回 True（中文属 Unicode Lo），导致「中文'中文」被误判为英文所有格、本该转中文单引号 ‘’ 却保留 ASCII `'`。修：加 `.isascii()` 限定，只 ASCII 字母-撇号-ASCII 字母保留。

### 验证（眼见为实）
- 正式回归文件：`scripts/test_regressions.py` 覆盖中文引号与英文撇号、footnote OOXML 注入、bold/italic/code runs、endnote 路径无字面 Markdown。
- 集成验证：构造含中文撇号 + 星号脚注的 docx，确认 document/footnotes XML 中中文单引号正确、don't/API's 保留 ASCII、footnotes.xml 无字面 `*` 且含 `<w:i/>`/`<w:b/>`。

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
