# 决策记录

本文档记录 `md2word` 技能的重要设计决策与工作日志。

## [DEC-017] - 2026-08-26 - 所有 Markdown 引用块共用全宽无框灰底 callout

### 背景
法律 AI Skill 书的章首“本章导读”和正文“案例”都使用 Markdown `>` 引用语法，但旧实现按段落逐行加底纹，配置中的外部缩进与边框没有完整生效，也没有可靠的左右内边距。`book-publish` / `legal` 又曾把引用配置设成无视觉样式，导致两个语义相同的引用框与正文难以区分。

### 决策
1. 所有连续 `>` 行只走 `add_quote()` 一条路径，不读取或匹配“本章导读”“案例”等文字标签。
2. 引用容器采用单单元格固定布局表格：宽度按正文可用区计算，`tblW`、唯一 `gridCol` 和 `tcW` 同源，`tblInd=0`；灰底写在 cell，边框显式写 `nil`，内边距写 `tblCellMar`。
3. `legal` / `book-publish` 使用 `#F5F5F5`、100% 正文宽、上下 100 twips / 左右 120 twips 内边距；正文 12pt 与 1.5 倍行距通过 `null` 继承。
4. 块前块后各使用 6pt exact 空段，避免 Word 默认空段按 12pt 放大；块内 `> ` 空行折算为前段的 6pt `space_after`，不生成空白内容段。
5. 不写 `w:cantSplit`，允许多段长案例随页面跨页；脚注和行内 Markdown 继续复用统一解析器。

### 方案取舍
- 不继续使用段落底纹：段落底纹难以同时提供可配置的真实左右内边距和稳定的整块灰底，多段之间也更容易出现接缝。
- 不创建“导读样式”和“案例样式”：两者共享 Markdown 语义，按标签分支会造成配置漂移；如需视觉变化，应统一修改 `quote` 配置。
- 不用可见边框模拟内边距：边框关闭仍应有真实 cell margins，避免在 Word 主题或打印链路中意外出现线条。

### 验证
- fixture 端到端回归验证两个 callout 样式快照一致；精确核对全宽、无外缩进、六条边框为 `nil`、四边内边距、上下 exact spacer、空引用行段距、脚注/粗体和普通正文不回归；最小引用列表回归另核对 bullet marker 与脚注仍在 callout 内。与 v1.2.9 合并后的全量 20/20 通过。
- 真实 ch12 临时转换识别出 2 个 `w:tblCaption=md2word-quote` 容器和 10 张数据表；导读/案例容器均为 `8504 twips` 正文宽、`tblInd=0`、灰底 `F5F5F5`、无 `cantSplit`，导读脚注与两类标题粗体保留。

### 影响与回退
- Word 对象模型中的 `document.tables` 会同时包含引用 callout 与数据表；消费者应通过 `w:tblCaption=md2word-quote` 区分。
- v1.2.x 的 `left_indent_inches` 不再缩窄引用容器；自定义配置应迁移到 `cell_margin.left/right`。回退时应整体撤销表格容器、配置映射和对应 fixture，避免文档与实现再次分叉。

## [DEC-016] - 2026-08-26 - 下划线强调采用单词边界并统一正文与表格规则

### 背景
法律 AI Skill 书第十四章表格中的 `payment_instance_id`、`dispute_amount_band`、`manual_review_required` 和 `audit_log_summary` 在 Word 中丢失下划线并出现斜体。根因不是预设配置，而是正文与表格各自使用的宽泛 underscore 正则：它会把技术标识中间的 `_instance_` 一类片段当作 Markdown 斜体；表格的格式预判还另有 `_.*?_`，即使解析语义修正也可能继续误分派。

### 决策
1. underscore 斜体、粗体和粗斜体的起止分隔符必须位于单词边界。边界按 Python Unicode `\w` 判断，同时覆盖 ASCII 字母数字、中文与下划线；因此这些字符内部的 `_` / `__` 不作为强调分隔符。
2. 在 `formatter.py` 维护唯一的生产行内格式规则，正文与 Markdown 表格解析共同使用；表格的 `contains_markdown_formatting()` 调用同一判定帮助函数，只另外识别图片与 `<br>`。
3. 保留 `_正常斜体_`、`__正常粗体__`、`___正常粗斜体___`，不改变星号强调、数学、HTML、脚注、图片或已有行内代码保护，不引入第三方 Markdown 解析依赖。

### 方案取舍
- 不要求作者给所有字段补反引号：反引号可以临时绕过，但普通技术标识本就不应被转换器破坏，且全书既有字段数量多。
- 不全局禁用 underscore 强调：这会破坏已支持的 Markdown 语义；单词边界能在保留明确强调的同时排除技术标识。
- 不只修改表格预判：正文解析与表格解析原本各自复制正则，只修一处会留下继续漂移的根因。

### 验证
- RED：正文回归把 `payment_instance_id` 等转换为 `paymentinstanceid`，表格预判对同一字段返回 `True`；两项测试均失败。
- GREEN：正文与 Markdown 表格中的 10 类标识（含 ASCII 数字和中文词边界样例）完整保留下划线且无意外斜体/粗体；三种明确 underscore 强调语义保持，19/19 回归通过。
- 真实 ch14 DOCX 的四个表格字段均各自构成 exact run；正文中的 `manual_review_required`、ch12 的 `main_chart_type` 与 ch04 的 `API_SERVER_KEY` 则完整存在于可能包含相邻正文的普通 run。所有匹配 run 的 `run.italic` 均为 `None`、OOXML 无 `w:i`。QuickLook 最小首屏 fixture 目检也显示字段完整。

### 影响与回退
- 影响正文与普通 Markdown 表格中的 underscore 强调识别；单词内下划线现在固定按字面量输出。
- 如需回退，应整体撤销共享规则与边界约束，不应只恢复表格或正文中的一份重复正则。

## [DEC-015] - 2026-08-25 - 统一增加代码框与正文的外部垂直间距

### 背景
书籍第十一章的 `text` 代码框与前后正文贴得过近。问题在代码框外部留白，而不是围栏语言或框内字体、行距、底纹。

### 决策
1. 不新增围栏语言；所有 fenced code block 均继续走 `add_code_block()`。
2. 在 `code_block.content` 新增 `space_before` / `space_after`，仅用于一个框的首段和末段；book-publish 取 6pt / 6pt。
3. 保持字体、字号、底纹、边框策略、左右缩进和框内 1.2 倍行距不变。

### 方案取舍
- 不改 `text` 的行距或字号：全书已有多种代码围栏，内容样式应保持稳定。
- 不新增边框或虚线：只解决框与正文之间的距离。

### 验证
- 端到端回归确认三行 `text` 代码框仅首段前和末段后为 6pt，中间段仍为 0；字体、字号、底纹与行距保持原值。
- `python3 -m unittest skills/md2word/scripts/test_regressions.py -v`：17/17 通过。

### 影响与回退
- 所有围栏统一适用；如需回退，仅删除两个外部间距配置及首末段分派。

## [DEC-014] - 2026-08-25 - 引用块正文复用统一脚注解析入口

### 背景
页面脚注管理器会在解析前提取所有 `[^label]: 定义`，但 Markdown 引用块由 `add_quote()` 单独处理，其正文仍直接调用 `parse_text_formatting()`，没有经过 `parse_text_with_footnotes()`。因此定义虽然存在，引用块内的 `[^chNN-skills]` 仍作为普通文本写入 `document.xml`，也不会登记到 `FootnoteManager.refs`。全书第二轮 DOCX 扫描发现 ch07、ch10—ch15 共 7 个章首导读 marker 均沿此路径逃逸。

### 决策
1. 仅把 `add_quote()` 中引用正文的解析调用改为 `parse_text_with_footnotes(..., is_quote=True)`，与普通正文共享脚注分派；不调整列表、标题、HTML 块或其他解析路径。
2. 保留引用块既有执行顺序：先单独写入 bullet / number marker，再解析剩余正文，最后应用 `set_paragraph_format(..., is_quote=True)`。因此列表 marker、引用段落格式与字体配置不变。
3. 继续把 `is_quote=True` 传入行内格式解析，使 `**本章导读**` 等加粗、斜体和引用字号沿用原语义；脚注引用 run 由现有 FootnoteManager 创建，不另写引用块专用 OOXML。

### 方案取舍
- 不在 `add_quote()` 内另写脚注正则或 OOXML：统一入口已经处理重复 label、相邻引用、footnote/endnote 分流和格式，复制逻辑会造成新的行为分叉。
- 不扩大到所有 block helper：本轮真实失败只来自引用块；其他路径没有测试证据时不顺带重构。
- 不改 Markdown 源稿或删除脚注：marker 逃逸是转换器遗漏，不应要求作者把章首导读移出引用块。

### 验证
- RED：最小引用块 fixture 的 `[^chapter-skills]` 原样进入 `document.xml`，转换包中没有 `word/footnotes.xml`。
- GREEN：新增端到端回归确认 marker 消失、生成 1 个 `w:footnoteReference` 与对应定义；`本章导读` 仍加粗，引用段落首行缩进仍为 0，引用块列表仍包含 bullet marker。全量 16 项测试通过。
- 真实 canonical ch10：`[^ch10-skills]` 字面量为 0，导读段含引用 ID 1，全文引用与正数定义为 `21/21`。
- 真实 15 章合并：`document.xml` 任意 `[^...]` 字面 marker 为 0，引用/定义/唯一引用 ID 为 `131/131/131` 且集合一致；15 sections、118 张表保持。临时全书输出位于 `/tmp`，相对截图路径因此降级为占位符，只用于脚注与结构验证。

### 影响与回退
- 影响限于 Markdown 引用块中的 `[^label]`；没有定义的悬空引用继续沿用 FootnoteManager 的既有行为（不创建脚注）。
- 如需回退，撤销 `add_quote()` 的统一入口调用及对应回归；不应改动普通正文脚注或脚注 OOXML 注入器。

---

## [DEC-013] - 2026-08-25 - 以正文区硬预算收敛表格宽度并统一 OOXML 宽度源

### 背景
现有 `_calc_column_widths` 在表头期望宽合计超过正文区时，只压缩单列宽度超过页面 70% 的列。真实表 7-15 有 6 列，每列均未触发 70% 阈值，但期望宽合计达到 17.84 cm，超过 book-publish 的 15.00 cm 正文区；fixed layout 又把超宽 grid 写入 Word，导致右侧越过正文边界。转换器同时保留 `tblW=auto/0`，与 `tblGrid`、`tcW` 的固定宽度口径冲突。

普通 Markdown 表题 `**表 10-5：...**` 没有进入既有图注分支，因而按正文输出为两端对齐和 24 pt 首行缩进。显式 `<div align="center">` 能把表题改为居中，却仍在 `set_paragraph_format()` 后继承 `firstLine=480`；因此两条合法表题路径都需要在保留文字样式的同时清除表题缩进。

### 决策
1. 保留 DEC-008 恢复的 P80 基础算法，不重新引入 DEC-007 已回退的短/中/长分类。
2. 把“正文宽度”提升为最终硬预算。期望宽未超页时继续按 P80 分配剩余空间；超页时允许长表头换行，为每列保留 1.2 cm 或按列数动态降低的可读下限，再按表头期望宽超出下限的相对需求分配剩余预算。
3. 浮点结果统一量化为整数 twips，按最大余数法分配舍入余数，使列宽总和精确等于正文可用宽度。写入前校验 Markdown 表格的 `tblGrid` 和每行列数与计算列数一致，再用同一组整数同步 `tblW`、`gridCol`、每行 `tcW`，并保持 `fixed layout`。
4. 表题识别沿用图注的编号形式，并兼容“表10-5”与“表 10-5”。普通 Markdown 表题直接覆盖水平居中、首行缩进和左缩进；显式 HTML 路径只在“对齐值为 center 且文本为表题”时清除两类缩进，普通居中块仍沿用正文缩进。两条路径都不复用图注 10 pt 字号规则，不改变 Markdown 粗体解析。

### 方案取舍
- 不继续采用“只压超过页面 70% 的单列”：它无法处理多列分别合理、合计超宽的场景。
- 不整体等比缩放到任意极窄宽度：先留动态可读下限，避免短列被压成不可读细条；预算不足时由长表头换行承担物理约束。
- 不把表 7-15、表 10-5 编号写入生产逻辑：编号只作为真实回归证据，算法与识别规则适用于任意 `X-Y` 表题和列数组合。
- 本次只约束普通 Markdown 表格；不扩张 HTML 合并单元格的宽度语义。

### 验证
- RED：六列 fixture 的 `_calc_column_widths` 返回 17.84 cm；端到端 grid 合计 9752 twips，超过向下量化后的 8503 twips 正文区；普通表题为 `JUSTIFY`。后续集成验收再以显式居中表题复现 `jc=center / firstLine=480`。
- GREEN：全量 15 项测试通过；六列计算宽度铺满且不超过正文区，端到端 `tblW/grid/tcW` 完全一致；普通与显式居中表题都得到 `center/0/0` 并保留粗体、正文 12 pt 字号，普通居中非表题块仍保留 24 pt 正文缩进。
- 真实 ch07 表 7-15：`10115 twips（17.8417 cm）→8503 twips（14.9982 cm）`。以已合并 canonical `<div align="center">**表 10-5：...**</div>` 重新转换 ch10，修复后表题为 `jc=center / firstLine=0 / left=0`，run 仍为粗体、24 half-points。

### 影响与回退
- 影响所有普通 Markdown 表格：此前超出正文区的表格会压缩长表头并换行；未超页表格仍沿用 P80 相对分配，仅统一 OOXML 宽度源和整数舍入。
- 如需回退，应整体撤销硬预算、twips 同步与表题识别；不得只撤销 `tblW` 写入，否则会重新形成相互冲突的宽度口径。

---

## [DEC-012] - 2026-08-25 - 只屏蔽起止标记落入行内代码的格式匹配

### 背景
法律 AI Skill 书 ch06 同一正文段连续出现 `` `law_keyword` ``、`` `case_vector` ``、`` `law_detail` ``、`` `case_detail` ``。v1.2.4 会先收集 `_内容_` 与反引号代码的全部正则匹配，再在重叠时保留更长匹配：第一个标识中的下划线与下一个标识中的下划线被跨段配对，更长的斜体匹配覆盖两个较短代码匹配，最终造成下划线消失、反引号残留和中间文本斜体。

### 决策
1. `parse_formatted_text()` 先收集全部反引号代码范围；非代码匹配只要起始或结束标记位于代码范围内，就不进入后续重叠竞争。
2. 不改现有“同优先级重叠时选择更长匹配”的通用逻辑；完整包围代码段的外层格式起止标记都在代码范围外，继续维持既有结果。
3. 不删除 `_斜体_` 支持，也不要求书稿改写真实 Tool 名称。回归同时断言四个下划线标识完整输出、无斜体、使用 book-publish 行内代码字体，并断言普通下划线斜体仍有效。

### 方案取舍
- 不只调整 `format_patterns` 顺序：匹配最终按起点和长度处理，单纯把代码正则前移不能阻止更长斜体匹配替换代码匹配。
- 不全局禁用下划线斜体：这会改变已支持的 Markdown 语法，影响面大于本次缺陷。
- 不整体改用第三方 Markdown AST：当前缺陷可在既有零新增依赖架构中窄修；替换解析器需要重新定义嵌套、HTML、数学公式和表格兼容语义，留给独立重构任务。

### 验证
- v1.2.4 基线 11 项测试全绿但真实最小样例失败，证明原测试未覆盖代码范围与下划线斜体冲突。
- 新增回归后共 12 项全部通过；四个 Tool 名称分别输出为 Courier New 行内代码 run，普通 `_正常斜体_` 仍输出斜体。
- 用法律 AI Skill 书 canonical ch06 真实转换，目标 run 的 OOXML 均保留下划线、浅灰底与 Courier New 字体，不含 `w:i`；全文字面反引号文本节点为 0，40 个页面脚注与 8 个内联 SVG 正常生成。

### 影响与回退
- 修复对正文与 Markdown 表格单元格共同生效，因为两条路径复用 `parse_formatted_text()`；脚注使用独立 inline parser，不受影响。
- 如需回退，整体撤销代码范围保护与对应回归；不应通过改写源稿标识或手工编辑 DOCX 绕过。

---

## [DEC-011] - 2026-08-24 - 相邻原生脚注用上标 NBSP 分隔并固定脚注段落间距

### 背景
真实 ch06 中同一句 `[^qcc-agent][^qcc-guide]` 转成 Word 后，连续脚注编号 9、10 紧贴显示成“910”，读者难以区分两个引用。页面脚注 34–40 又因正数脚注段落没有显式 spacing，受默认段落格式影响而出现过大的段落间距。

### 决策
1. 仅在原生 `footnote` 模式、且两个有效 Markdown 脚注标记在源码中直接相邻时，在对应的两个 `w:footnoteReference` run 之间插入一个 `U+00A0` NBSP run；该 run 使用上标与 9pt（`w:sz=18`）。
2. 源码两个标记之间只要已有任何字符，包括普通空格、逗号或顿号，就保留源文本且不再插入 NBSP。`endnote` 暂不增加分隔字符。
3. 每个正数 `<w:footnote>` 的 `<w:p>` 显式加入 `<w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>`；separator 与 continuationSeparator 的段落不改，既有脚注 run 仍为 9pt。

### 方案取舍
- 不修改 Markdown 源稿：编号黏连与脚注段落间距是 Word 输出层问题，不应要求作者逐处补空格或标点。
- 不统一插普通空格：普通空格可能被 Word 折叠，且会给已有分隔字符的源文本重复加空白；窄条件 NBSP 能稳定保留视觉间隔。
- 不改全局段落样式：全局样式会影响正文或其他 Word 元素；在正数脚注段落上写明确的本地 spacing，范围最小且 OOXML 可直接验证。

### 验证
- RED：相邻 fixture 的两个脚注引用之间实际有 0 个 NBSP；正数脚注段落找不到显式 `w:spacing`。
- GREEN：相邻引用之间恰有 1 个 NBSP run，且具备上标与 `w:sz=18`；已有空格、逗号、顿号的三组引用不新增 NBSP。所有正数脚注段落的四个 spacing 属性精确匹配，连同既有回归共 11 项全部通过。
- 真实 ch06 中企查查段精确得到 `ref 9 / NBSP / ref 10`，NBSP 仅含一个 `w:sz=18`；40 个正数脚注段落全部具有 `before=0 / after=0 / line=240 / lineRule=auto`。引用 / 定义 / 唯一 ID 为 `40/40/40`、重复 ID 为 0；表 / 图 / 占位符维持 `0/13/0`，无缺图警告。
- QuickLook 可生成首屏缩略图与 HTML 预览，首屏未见明显异常；但目标企查查段和脚注 34–40 未获得页面级可见渲染，且本机无 `soffice`。视觉结论为 `NOT_VISUALLY_RENDERED`，未安装依赖、未打开 Word。

### 影响与回退
- 影响仅限原生 footnote 的源码直接相邻引用和正数脚注段落；单个引用、已有分隔文本、endnote 与 separator 脚注不变。
- 如需回退，应整体撤销相邻引用分隔与正数脚注 spacing；不得把 NBSP 扩大到已有源文本的引用对。

---

## [DEC-010] - 2026-08-24 - 重复原生脚注使用独立 Word ID

### 背景
Markdown 允许同一 `[^label]` 在正文重复出现。旧实现把 label 永久映射为一个序号，使多个 `<w:footnoteReference>` 指向同一 `w:id`，`footnotes.xml` 也只写一条定义；真实 Word 转换中，后续引用位置可能不显示脚注。伪 endnote 则没有这个 OOXML 约束，同一 label 复用编号本就是既有语义。

### 决策
1. 在原生 `footnote` 模式中，每次有效引用都递增序号、生成独立 `w:footnoteReference` ID，并把相同定义文本作为独立条目写入 `footnotes.xml`。此时 Markdown label 只负责查找定义文本，不再代表可复用的 Word 脚注实体。
2. 在 `endnote` 模式中保留 `_id_map`：同一 label 继续复用同一上标编号和一条尾注定义。
3. 不改变悬空引用、脚注内联格式、每节编号重置、全书章间 section 或尾注渲染逻辑。

### 方案取舍
- 不生成 Word `NOTEREF` 交叉引用字段：它需要为首个脚注建立可定位书签，并依赖 Word 更新域；交叉引用也不等同于在每个引用位置生成页面脚注，兼容性与呈现均偏离本次目标。
- 不要求作者把重复 label 手工拆成多个源稿定义：改写源稿虽能绕开旧实现，但把 OOXML 兼容负担转嫁给作者，也不能修复转换器默认行为。
- 选择独立 ID + 重复文本：OOXML 结构直观，每个出现位置都具备自己的页面脚注，代价是同文定义在文件中重复；这是可接受且可验证的确定性结果。

### 验证
- RED：同一 label 两次引用时，旧实现得到 2 个引用但只有 1 个唯一 `w:id` 和 1 条定义。
- GREEN：原生 footnote 回归要求 2 个不同引用 ID、2 条同文定义；endnote 兼容回归要求编号仍为 `1、1` 且只有 1 条尾注定义。连同既有回归共 9 项全部通过。
- 真实 ch03 / ch04 / ch05 / ch06 单章转换的“引用 / 定义 / 唯一 ID”分别为 `6/6/6`、`22/22/22`、`16/16/16`、`40/40/40`；四章均无重复引用 ID。
- 真实 15 章全书转换得到 15 sections、9 条水平线、118 表、180 图、0 图片占位符。源稿 128 个引用标记中，121 个被既有解析路径转换为 Word 引用；其引用数、定义数、唯一 ID 数均为 121，重复 ID 为 0，引用与定义 ID 集完全一致。剩余 7 个章节导读引用块标记仍为字面文本，本决策不扩大范围修复该既有缺口。

### 影响与回退
- 影响限于同一 label 重复出现时的原生 footnote 结构；单次引用与 endnote 输出不变。
- 如需回退，应整体撤销 footnote 独立 ID 分流；不得删除 endnote 的 `_id_map`，否则会无意改变尾注编号语义。

---

## [DEC-009] - 2026-08-24 - 用内部 marker 区分章间边界与 Markdown 水平线

### 背景
`create_book()` 原先用 `\n\n---\n\n` 拼接章节，`create_word_document(..., book_mode=True)` 又把任何 `---`、`***`、`___` 都转换为 `WD_SECTION.NEW_PAGE`。因此章节内合法水平线会被误当成章间断点；单章模式另有“首条水平线等于封面分页”的无来源启发式，也会吞掉第一条 Markdown 水平线。真实书稿中 ch12 有 1 条、ch13 有 8 条水平线，旧实现会产生多余 section 和硬分页。

### 决策
1. 定义带固定高熵后缀、独占整行的 `BOOK_CHAPTER_BREAK_MARKER`，只供 `create_book()` 与 book parser 内部通信；`create_book()` 仅用该 marker 拼接相邻输入文件。
2. book parser 只在 `book_mode=True` 且整行严格等于内部 marker 时调用 `doc.add_section(WD_SECTION.NEW_PAGE)`；不用用户可输入的 Markdown 语法承担内部控制语义。
3. `---`、`***`、`___` 在单章和全书模式下统一调用 `add_horizontal_line()`；删除“首条水平线作为封面分页”的状态与分支。
4. 不改每章脚注 `numRestart=eachSec`、目录自动更新与页眉继承。内部 marker 仍产生每章独立 section，因此既有分节能力保持不变。

### 方案取舍
- 采用独立 marker：改动集中在既有“先合并 Markdown、再统一解析”的架构内，且不会与合法 Markdown 水平线碰撞。
- 不改为逐章直接操作同一个 `Document`：这会扩大解析、脚注命名与资源路径处理的重构面，超出本次缺陷修复。
- 不使用 HTML comment marker：当前预处理会先删除 HTML 注释，无法稳定传递章间边界。

### 验证
- RED：旧实现的两章 fixture 产生 3 sections（预期 2）；单章 `---` / `***` / `___` 只留下 2 条水平线（预期 3）。
- GREEN：两项端到端回归与既有测试共 7 项全部通过；同时断言每章脚注 `numRestart=eachSec`、TOC、`updateFields` 和页眉继承保持不变。
- 真实 15 章书稿只读前向验证：15 sections、9 条水平线（ch12=1、ch13=8）、118 表、180 图、0 图片占位符；临时 DOCX 与缓存仅保留在 `/tmp`，不进入仓库。
- 源稿共有 128 个脚注引用标记：121 个生成 `<w:footnoteReference>`，另 7 个位于章节导读引用块内并保留为字面标记。该引用块解析缺口来自既有实现，相关解析路径未被本次改动触及，单独披露但不扩大本次章间边界修复范围。

### 影响与回退
- 影响范围仅限 `scripts/md2word.py` 的章间拼接与水平线分派；普通段落、表格、图片、脚注内容和样式配置不变。
- 如需回退，应整体撤销内部 marker 与分派修改；不得只恢复 `---` 章间拼接，否则会重新引入章内硬分页逃逸。

---

## [DEC-008] - 2026-07-14 - v1.1.7 回退列宽智能化到旧版 P80 算法

### 背景
v1.1.6（DEC-007）升级 `_calc_column_widths` 为"列类型自适应（短/中/长三分类）"，旨在解决"短文本列被同行长行 P80 拉宽"的问题。但作者在 7/13-7/14 转换交付包中实际查看 Word 表格后反馈：新算法的分类逻辑导致部分表格列宽被过度拉长，整体表格视觉效果不如旧版。要求回退。

### 决策
回退 `_calc_column_widths` 到 v1.1.5 旧版实现（commit `a3f547d^`）：
- 旧版签名无 `cell_lengths_real_per_col` 参数，但新版调用方已传此 kwarg → 签名保留该参数向下兼容（无实际作用）。
- 旧版策略：短列先按 min_needed 保底不换行；长列按 P80 权重瓜分页面剩余宽度；超页时只压长列不改短列。
- `adjust_table_column_width` 中的双 lens 收集（cell_lengths + cell_lengths_real）保留不删（无副作用，若未来需再做分类可直接启用）。

### 影响
- 代码：`scripts/table_handler.py` _calc_column_widths 替换为旧版实现（+31/-73）。
- 全局生效：所有 preset 的表格列宽回到 v1.1.5 行为。
- DEC-007 被 supersede；标记为已回退但保留记录供未来参考。

---
## [DEC-007] - 2026-07-13 - v1.1.6 列宽分配智能化（短/中/长 列类型自适应）~~[已回退·superseded by DEC-008]~~

### 背景
法律 AI 书项目（260512）转换交付包 `法律AI-Agent书稿-Word-20260713` 时，作者反馈 **ch04 表 4-1**（2 列"项目 / 记录"）左列 4.19 cm 太宽——表头"项目"2 字本应 2-2.5 cm，但被同行 16 字"是否支持 Skill、MCP、插件或连接器"作为 P80 权重基准拉宽。调研发现 P80+min_needed 算法是"一行长内容拉宽整列"的根因：短列用最长单元格作权重基准，对"短文本列中偶有超长行"场景不鲁棒。

### 决策
升级 `_calc_column_widths` 为**列类型自适应算法**（全局生效，影响所有 preset 而非仅 book-publish，因为法律文书/服务方案等模板同样有此痛点）：

1. **双口径收集 lens**：`adjust_table_column_width` 同时存 cell_lengths（权重字=中文×2 ASCII×1，给 P80 瓜分用物理宽度）和 cell_lengths_real（真实字=中文×1 ASCII×0.5，给列类型判定）。新增 `_calc_column_widths(..., cell_lengths_real_per_col=None)` 可选参数。
2. **列类型三分类**（用真实字 + 多重约束）：
   - **short**：表头 ≤ 4 字 **且** P50 真实字 ≤ 8 **且** (P95 真实字 ≤ 18 **或** max_real ≤ P50_real × 3)
   - **long**：表头 ≥ 6 字 **或** P75 真实字 ≥ 12 **或** P95 真实字 ≥ 20
   - **mid**：其余
3. **基础宽公式**：short 用真实字 P50 取小（`max(h, p50_r) × 0.32 + 0.84`），long/mid 用权重字 P80/P60（物理宽度）。短列固定不参与瓜分，长/中间列按 P80 权重瓜分余量。超页面时只压长列（>MAX_REASONABLE=available_cm×0.7）保短列不变。
4. **去掉 `seen.add(id(cell._tc))` 去重**：python-docx 1.x 的 `row.cells` 对无合并多行表存在 tc id 重复 bug，导致表 4-1 实测只 4/13 行被收集 lens。无合并表不需要去重。

### 验证（眼见为实）
- 表 4-1（ch04，2 列"项目 / 记录"）：旧 [4.19, 10.80] → 新 [3.08, 11.92] cm，单章 docx 与全书 docx 一致。
- 全表扫描：ch01-09 共 36 张表逐一读 gridCol dxa 换算 cm，short 列普遍从 4-9cm 降到 2.1-3.1cm，长列瓜分到 10-12cm 上限。
- 转换 log ⚠️=0（全书与 9 单章均无缺图/降级/占位符）。

### 影响
- 代码：`scripts/table_handler.py` _calc_column_widths 重写 + adjust_table_column_width 双 lens 收集 + 去 seen 去重（+98/-28）。
- 全局生效：所有 preset（legal/academic/report/service-plan/minimal/book-publish）的表格都受新算法影响——对短列密集型法律文书/服务方案是正向改进。
- 风险：short `P95 ≤ 18` 阈值在 110 表全集（仅 ch01-09 已测 36 表）需回归；future work 跑完整书 14 章 ch10-14 需补一次 gridCol 扫描。
- 合并：feature `feature/smart-column-width` 在 legal-skills 主仓 + 本地 main FF merge（symlink 立即生效）；远端因 local/remote main 无共同历史走 GitHub UI 手动合（DEC-006 同样模式）。

---

## [DEC-006] - 2026-07-11 - v1.1.5 修复中文撇号误判 + 脚注星号进 XML（法律 AI 书 acceptance harness 修复轮）

### 背景
法律 AI 书 acceptance harness 诊断（PM 独立验证，ultra-research 研究触发）发现 md2word 两个真实 bug：
1. **formatter.py 中文撇号误判**：`convert_quotes_to_chinese` 用 `prev_c.isalpha() and next_c.isalpha()` 保留英文所有格撇号（don't/O'Brien），但 Python `'需'.isalpha()` 返回 True（中文属 Unicode Lo），导致「中文'中文」被误判为英文所有格、本该转中文单引号 ‘’ 却保留 ASCII `'`。
2. **footnote_handler 星号进 XML**：脚注 text 直接 `_xml_escape` 塞进单个 `<w:t>`，`*需律师现场确认*` 的星号原样进 footnotes.xml，Word 显示字面星号。

### 决策
1. formatter.py:78 `isalpha()` 前加 `.isascii()` 限定：只 ASCII 字母-撇号-ASCII 字母保留（英文缩写/所有格），中文边界走交替状态机转中文单引号。
2. footnote_handler.py 新增 `_footnote_text_to_runs_xml()`：解析 `**bold**`/`*italic*`/`` `code` `` 转 Word runs（`<w:b/>`/`<w:i/>`/Consolas），既不显示字面星号又保留格式。不处理 `_italic_`（避免下划线变量名误判）、嵌套、`[link](url)`（留 follow-up）。

### 验证（眼见为实）
- 单元测试：footnote runs 6 case + convert_quotes_to_chinese 6 case ALL PASS。
- 集成验证：造含中文撇号 + 星号脚注的 md 转 docx（legal preset, footnote 模式）——document.xml `需律师现场确认`→中文单引号、don't/API's 保留 ASCII；footnotes.xml 无字面 `*`、含 `<w:i/>`/`<w:b/>`、拆 runs。

### 影响
- 代码：formatter.py + footnote_handler.py（+66/-3）；CHANGELOG [1.1.5]。
- 合并：feature `fix/md2word-isalpha-footnote` pushed cat-xierluo/legal-skills；本地 main FF merge（symlink 立即生效）。远端因 legal-skills 本地/远端 main 无共同历史走 GitHub UI 手动合；本 DECISIONS 记录写本地 untracked，合并失败不丢。
- follow-up：脚注 `_italic_`/嵌套/链接 inline 解析（本版未做）。

---

## [DEC-005] - 2026-06-09 - 补齐技能级文档（TASKS.md / DECISIONS.md）

### 背景

项目 AGENTS.md 明确要求每个技能在根目录下包含 `DECISIONS.md`、`TASKS.md`、`CHANGELOG.md` 三件套。`md2word` 此前只有 `CHANGELOG.md`，任务清单散落在 `TODO.md` 与 CHANGELOG 顶部"待优化事项"两处，决策背景未沉淀。

### 决策

1. 新建 `TASKS.md`：合并 `TODO.md` 的待办与 CHANGELOG 顶部"待优化事项"段落，按"已完成 / 高优先级 / 待调研 / 远期"分类。
2. 新建 `DECISIONS.md`：按 `[DEC-XXX] - YYYY-MM-DD - 标题` 格式记录关键设计决策，从 CHANGELOG 中提炼而非凭空编写。
3. `TODO.md` 暂不删除：与新 `TASKS.md` 内容重叠，后续在下一次正式发版时统一清理（用户确认后再删）。
4. CHANGELOG 顶部"待优化事项"段落标记为"已并入代码，尚未正式发版入 CHANGELOG"，等待下次发版时正式记录到版本号下。

### 影响

- 任务清单和决策背景终于有"权威位置"，符合项目协作规范。
- `TODO.md` 与 `TASKS.md` 短期共存，用户应统一以 `TASKS.md` 为准。
- 文档三件套对齐后，便于未来 CI / Skill 评估工具扫描。

---

## [DEC-004] - 2026-04-11 - 外部 URL 图片支持与降级策略

### 背景

Markdown 中常出现 `https://...` 外链图片（Notion 导出、博客文章、用户素材库），原脚本只处理本地路径图片，导致外链图片直接丢失或显示为破图占位。

### 决策

1. 在 `scripts/md2word.py` 新增 `download_external_image()`，使用 `urllib.request` 下载 HTTP/HTTPS 图片。
2. 下载失败时**降级为文字占位符** `[图片: alt文本]`，而不是抛出错误中断整个转换流程。
3. 复用现有 `_postprocess_image_for_word()` 和 `insert_image_to_word()` 管线，自动居中插入。
4. 修复正则以兼容 URL 中含括号的情况（如 `no_upscale()?imageUrl=...`）。

### 影响

- v0.5.0 起支持更完整的图片场景，转换成功率提升。
- 网络失败不会让整个文档转换中断；占位符提示用户手工补图。
- 与 Mermaid 失败时的"降级为文本占位"形成统一的优雅降级原则。

---

## [DEC-003] - 2026-02-10 - 脚本模块化拆分（1955 行 → 4 模块）

### 背景

v0.3.0 之前的 `scripts/md2word.py` 单文件约 1955 行，混合了主流程、文本格式化、表格处理、图表渲染等多类职责。新增功能（如 v0.2.0 的完整配置系统）让维护成本急剧上升。

### 决策

按职责拆为 4 个模块：

| 模块 | 行数 | 职责 |
| --- | --- | --- |
| `md2word.py` | 800 | 主入口 + 核心转换流程（减少 59%） |
| `formatter.py` | 388 | 文本 / 段落格式化 |
| `table_handler.py` | 532 | 表格处理 |
| `chart_handler.py` | 248 | 图表渲染（Mermaid 等） |

同步清理：移除未使用的 `sys`、`requests`、`base64`、`io`、`WD_TAB_ALIGNMENT` 等导入与枚举；`BeautifulSoup` 移至 `table_handler.py`。

### 影响

- 后续扩展新图表类型时只需在 `chart_handler.py` 内部迭代，不影响主流程。
- v0.4.1 同步修复了因重构引入的循环导入（`get_config` / `set_config` 改在 `config.py`）。
- 测试与排错时可以聚焦单一文件。

---

## [DEC-002] - 2026-01-29 - 配置文件管格式参数，Word 模板管视觉元素

### 背景

用户使用过程中存在两类完全不同的"自定义"诉求：

1. **细排版调参**：字号、行距、页边距、缩进、引号转换等（重复性高、可参数化）
2. **企业视觉定制**：页眉 Logo、页脚、配色、字体品牌（每个客户 / 律所不同、不可参数化）

最初尝试用一种方案承载两类需求（要么纯配置、要么纯 Word 模板），都不顺手。

### 决策

采用**两套机制分工**：

- **YAML 配置文件**（`assets/presets/*.yaml`）：控制可参数化的格式（字号、行距、段间距、对齐、首行缩进、引号、表格列宽、代码块样式等）。
- **Word `.docx` 模板**（`assets/templates/`）：控制视觉元素（页眉、页脚、Logo、页码格式），通过 `--template` 指定。
- 模板找不到时**自动降级为默认格式创建新文档**，不阻断流程。

### 影响

- 用户只调字号 / 行距 → 用 YAML 预设即可，门槛低。
- 用户要全套律所视觉 → 用 Word 模板，AI 不用关心 Logo 怎么画。
- 两类需求互不污染，预设库与模板库可独立扩展。

---

## [DEC-001] - 2026-01-29 - 引入 YAML 配置 + 内置预设系统

### 背景

初版 `md2word.py` 把所有格式参数硬编码在脚本中（字号、行距、边距、引号规则等）。用户反馈两类问题：

1. 律师行业不同文书（起诉状 vs 服务方案 vs 论文）排版风格差异巨大，硬编码无法覆盖。
2. 每次改格式都要改 Python 源码，使用门槛高、不安全。

### 决策

1. 引入完整 YAML 配置系统，覆盖代码块、行内代码、引用块、数学公式、图片、分割线、列表、表格等所有可调参数。
2. 内置 4 套预设：`legal`（法律文书，默认）、`academic`（学术论文）、`report`（工作报告）、`simple`（简单文档）；后续按需扩展 `service-plan`、`minimal` 等。
3. `scripts/config.py` 提供 `get_config()` / `set_config()`，所有子模块通过它读取配置，**禁止硬编码**。
4. `scripts/md2word.py` 的所有 `add_xxx()` 函数重构为读取配置驱动。
5. 提供 `assets/config-template.yaml` 作为自定义配置起点。

### 影响

- 用户只需选预设 / 改 YAML，不需要碰 Python 源码。
- 新增预设成本极低：复制 YAML + 改参数即可。
- 重构带来的副作用：v0.4.0 拆模块时必须把 `get_config` / `set_config` 放对位置，否则会循环导入（见 DEC-003）。

---

# 工作日志

### 2026-06-10 清理冗余文件与撤除 pytest 测试基建

- **目标：** 用户反馈 [0.5.1] 修复引入的冗余应当清理
- **操作：**
  - 删除 `tests/fixtures/` 下的 `信访材料_V3_alignment.docx`（1.1 MB）与 `.md`（695 B），无测试代码引用
  - 删除 `tests/` 目录 + `pytest.ini` + `.venv/`（67 MB）+ 各处 `__pycache__/` + `.pytest_cache/` + 3 处 `.DS_Store`
  - 工作区总大小从 69 MB 降至 1.4 MB
- **文档同步：**
  - `TASKS.md` 顶部去掉 TODO.md 引用段落（TODO.md 已不在仓库）
  - `TASKS.md` 任务 8 关闭（确认 CHANGELOG 与 SKILL.md 是双轨版本号）
  - `CHANGELOG.md` 顶部加双轨制说明（**已被 2026-06-10 下午日志覆盖**——CHANGELOG 不存在双轨制，应单轨按 `1.0.X` 推进）
- **结果：** 工作区干净，无冗余；测试基建的回归保护放弃（[0.5.1] 描述的 32 个测试已不存在）
- **下一步：** 后续如重新引入测试，需在 [0.5.1] 段落中追加一条"撤除"说明或在下一个版本号段中体现

### 2026-06-10 (下午) CHANGELOG 版本号重排为 1.0.X 单轨

- **背景**：上午清理冗余时我误判 CHANGELOG 段落编号（`0.x.x`）与 SKILL.md frontmatter（`1.0.1`）是"双轨制"，加了顶部说明段；用户纠正：`md2word` 已正式发布，版本号应单轨按 `1.0.X` 推进，不存在双轨
- **操作（第一轮）**：
  - 删除 `CHANGELOG.md` 顶部"双轨制说明"段
  - 8 个历史段（`0.1.0` - `0.5.1`）按时间顺序重排为 `1.0.0` - `1.0.7`
- **用户二次反馈**：早期版本（`0.1.0` - `0.3.0`）保持原样即可，不必重排
- **操作（第二轮）**：
  - 早期 4 段（`0.1.0` - `0.3.0`）恢复为 `0.x.x` 编号
  - 最近 4 段（`0.4.0` - `0.5.1`）重排为 `1.0.0` - `1.0.3`
  - 段内交叉引用（`已并入 [1.0.7]`、`沿用 [1.0.6]`、`v1.0.4`）同步更新为 `[1.0.3]` / `[1.0.2]` / `v1.0.0`
  - `TASKS.md` 任务 8 描述更新为新映射
- **结果**：`CHANGELOG [1.0.1]` 段 = `SKILL.md` frontmatter = `marketplace.json` 的 `1.0.1`，三处版本号一致
- **下一步**：下次发版到 marketplace 时按 CHANGELOG 新编号升 `SKILL.md` frontmatter 与 `marketplace.json`

### 2026-06-09 (Codex)

- **目标：** 按项目 AGENTS.md 规范补齐 `md2word` 技能级文档
- **操作：** 新建 `TASKS.md` 合并 `TODO.md` 任务与 CHANGELOG 顶部"待优化事项"；新建 `DECISIONS.md` 记录 5 个关键设计决策（任务清单补齐、URL 图片降级、模块化拆分、配置 vs 模板分工、YAML 配置系统）
- **结果：** 任务清单和决策背景终于有权威位置，与项目其他 skill 对齐
- **下一步：** 处理任务 1（HTML / CSS 对齐语法扩展）；用户确认后清理 `TODO.md` 与 CHANGELOG 顶部"待优化事项"段落

## 2026-06-24 v1.1.0 决策

- **选型 python-docx 增量，不切 pandoc**：复用现有代码框/表格/图表/预设能力，中文出版样式完全可控；脚注用 OOXML post-process 注入（save 后 zip 操作，自包含内联格式不依赖 styles.xml）。pandoc 唯一优势（脚注开箱）抵不过重写成本 + 样式失控，且"每章尾注"pandoc 也不原生支持。
- **脚注双模式**：footnote=Word 原生页面脚注（注入 footnotes.xml，含 separator/continuationSeparator）；endnote=伪 endnote（文档末"注释"+上标编号，因 Word 原生 endnote 只能文档末、不能"每章末"）。全书合并 id 加章前缀（`[^1]`→`[^1-1]`）防跨章冲突。
- **SVG 渲染**：复用 svg-book-illustrator 的 svg2png.js（puppeteer），渲染优先级 rsvg-convert（轻，已装）→ cairosvg → svg2png.js，三策略任一可用即可，全失败降级代码框。
- **代码框 CT_PPr 顺序**：pBdr→shd→spacing→ind（OOXML schema 合规，Word 不因乱序报错），相邻代码行同边框自动连成完整框。
- **--book 输出用 -o/--out**：argparse 中 --book nargs='+' 会贪婪吃位置参数，故输出路径必须用 flag，不能位置传。
