# md2word 任务清单

## 已完成

### Task-015：修复全书合并的章节本地图片路径

- **状态**：✅ 已完成（PR #104）
- **目标**：让 `--book` 串联合并多个 Markdown 后，仍以每个章节源文件自己的目录解析本地图片，消除因输出目录改变产生的图片加载占位符。
- **范围**：Markdown 图片目标与 HTML `<img src>` 的合并前重定位、含空格/URL 编码/尖括号/可选 title 路径、双目录整书 DOCX 回归、单章隔离、版本与文档。
- **非目标**：不改变单章转换；不下载或改写 HTTP/HTTPS、data URI、锚点、绝对路径；不复制资源文件、不改变输出目录、不修改图片渲染器或安装依赖。
- **验收证据**：完整回归 24/24、`py_compile`、7/7 YAML 解析与 `git diff --check` 通过。双目录端到端 fixture 覆盖共享 `../../figures`、同目录、子目录含空格/中文、URL 编码、可选 title 与 HTML 图片，整书 DOCX 得到 5 个 `w:drawing`，无本地图片警告或占位；远程/data/锚点/绝对路径/fenced code 保持，单章仍按源文件目录嵌入 1 图且输入不变。真实 ch12 + ch13 得到 31 个 drawing/media、37 表、2 section、0 占位，16 XML well-formed，ZIP 完整且 merged 临时稿已删除，SHA-256 `708c5cd4c3a396968645a81ed57e8e3e67d1b0ddf4d944841522333f8599b7bc`。官方 `quick_validate.py` 因本仓强制 frontmatter 键退出 1，记为 `NOT_VERIFIED`。
- **关联**：DEC-022；用户 2026-08-26 全书导出反馈。

### Task-014：本章小结与动手练习从新页开始

- **状态**：✅ 已完成（PR #103）
- **目标**：让书籍预设中的精确“本章小结”“动手练习”Markdown 标题从新页开始，同时避免额外空白页与误匹配。
- **范围**：标题自身 `pageBreakBefore`、分页配置 SSoT、全部预设/fallback/config-template/模板提取基底、文档、回归测试、全书静态扫描和真实 ch12 结构验收。
- **非目标**：不插入独立分页段或 `w:br`；不新增 section；不修改普通正文、表题、代码块、标题既有格式或书稿源文件；不打开 Word。
- **验收证据**：完整回归 23/23、`py_compile`、7/7 YAML 解析与 `git diff --check` 通过。fixture 对 H2/H3 正例与正文/表题/代码块/近似标题负例得到 3 个 `pageBreakBefore`、0 个分页 `w:br`、1 个 section、0 个额外空段；legal 与自定义空列表为 0，标题原格式不变。全书静态扫描 15 个“本章小结”+12 个“动手练习”（含 ch14 H3）共 27 个精确标题。真实 ch12 命中 2 个标题分页并保留 10 表+10 spacer、6 quote 段、11 图注链与 1 脚注；DOCX 15 个 XML well-formed，SHA-256 `e1121d10d206b4466d86264f5c57a679f6b8401f081f447cef0ff21f74d57be5`。官方 `quick_validate.py` 因本仓强制 frontmatter 键退出 1，记为 `NOT_VERIFIED`。
- **关联**：DEC-021；用户 2026-08-26 书籍展示反馈。

### Task-013：引用框与代码框统一为中性浅灰

- **状态**：✅ 已完成（PR #102）
- **目标**：保留已确认的连续段落型 callout 结构，只把导读/案例背景及其同色 padding border 统一为代码框同款 `#F5F5F5`。
- **范围**：quote fallback、全部内置预设、config-template、模板提取基底、配置与样式文档、版本和回归/真实 ch12 结构验收。
- **非目标**：不改变 shaded exact spacer、引用段落结构、表后 6pt 留白、图片/图注、书稿源文件或第十二章 `confirmed` SVG；不打开 Word。
- **验收证据**：完整回归 22/22、`py_compile`、7/7 YAML 解析和 `git diff --check` 通过；`book-publish` / `legal` 的 quote 与 code block 背景均为 `#F5F5F5`。真实 ch12 得到 10 张数据表 + 10 个表后 spacer、6 个 quote 段（4 内容 + 2 同底色 exact spacer）、11 组图片/图注和 1 个脚注；全部 quote shading/border 为 `F5F5F5`、无引用表格，DOCX 包完整、15 个 XML well-formed，SHA-256 `75dc5691c7676602e837a6e7b7b2f87289190918184238429b8c50724b590baa`。官方 `quick_validate.py` 因本仓强制 frontmatter 键退出 1，记为 `NOT_VERIFIED`。
- **关联**：DEC-020；用户 2026-08-26 视觉确认后的颜色纠偏。

### Task-012：消除多段引用白缝并统一 confirmed 灰

- **状态**：✅ 已完成（PR #101）
- **目标**：让导读/案例的多段 callout 在 Word 中成为视觉连续的一整块 `#EDF2F7` 灰底，内部空行保留稳定呼吸区但不露白。
- **范围**：空引用行的 shaded exact spacer、连续空行折叠规则、全部 quote 颜色 SSoT、预设/fallback/config-template/模板提取基底、配置和样式文档、fixture 与真实 ch12 结构验收。
- **非目标**：不恢复表格引用容器；不改变数据表的 `space_after`；不调整图片/图注、正文全局行距或书稿源文件；不打开 Word。
- **验收证据**：完整回归 22/22、`py_compile`、7/7 YAML 解析通过。fixture 的连续空引用行折叠为 1 个 shaded spacer，多段案例形成 3 个内容段 + 2 个同底色 exact spacer；所有段均为 `EDF2F7` 且无引用表格，内容段内部间距为 0，spacer 只有左右同色 border，脚注/粗体/列表保持。真实 ch12 得到 10 张数据表 + 10 个既有表后 spacer、6 个 quote 段（导读内容 1 + 案例内容 3 + 案例灰底 spacer 2）、11 组图片/图注和 1 个脚注；DOCX 包完整、15 个 XML well-formed。官方 `quick_validate.py` 仍因本仓强制 frontmatter 键退出 1，记为 `NOT_VERIFIED`。
- **关联**：DEC-019；用户 2026-08-26 截图反馈。

### Task-011：引用框移除 Word 网格线，并收紧数据表组件后的间距

- **状态**：✅ 已完成（已合并 PR #99；merge `9d52b124132cf850d8726aa179d03abde46d8cb0`）
- **目标**：让导读/案例引用框在 Word 编辑界面只显示浅灰背景、绝不出现表格虚线轮廓；让 Markdown/HTML 数据表自行提供稳定、可配置的表后留白。
- **范围**：paragraph-based `add_quote()`、`quote.padding` 与 v1.3.0 `cell_margin` 兼容映射、`table.space_after`、全部预设/fallback/config-template/模板提取基底、配置与样式文档、端到端测试、真实 ch12 结构验收。
- **非目标**：不修改后续正文的行距或段前距；不改变图片/图注间距；不按“导读/案例”标签分叉；不打开 Word 或安装依赖。
- **验收证据**：完整回归 22/22 通过；引用 fixture 为 0 表且保留灰底/首尾与左右 padding/脚注/粗体/列表，并覆盖旧 `cell_margin` 迁移；Markdown/HTML 表后各恰好 1 个 exact 6pt spacer，下一正文保持 1.5 倍自动行距，图片图注链路无 spacer。真实 ch12 临时转换得到 10 张数据表及 10 个 exact spacer、4 个 paragraph callout 段（导读 1 + 案例 3）、0 个引用表格、11 组图片/图注和 1 个导读脚注；首/中/尾 padding 与 OOXML 属性顺序均通过结构断言。官方 `quick_validate.py` 因本仓强制保留的 `author`、`homepage`、`version` frontmatter 键退出 1，记为 `NOT_VERIFIED`（与 Task-010 已记录的仓库/验证器规则冲突相同）。
- **关联**：DEC-018；用户 2026-08-26 Word 示例反馈。

### Task-010：普通技术标识内部下划线按字面量保留

- **状态**：✅ 已完成（已合并 PR #97；merge `2c3ff091`）
- **目标**：修复正文与 Markdown 表格把技术标识内部 `_` / `__` 误解析为斜体或粗体的问题，同时保留明确的 underscore 强调语义。
- **范围**：正文与 Markdown 表格共享单词边界规则；表格格式预判与解析一致；覆盖 ASCII 字母数字、中文词和真实第 4、12、14 章字段。
- **非目标**：不改星号强调、数学、HTML、脚注、图片路径；不引入第三方 Markdown 依赖；不改书稿源文件。
- **验收证据**：RED 两项分别复现正文吞下划线与表格预判误报；GREEN 全量 19/19 通过。真实 ch14 四个表格字段均为 exact run；正文中的 `manual_review_required`、ch12 `main_chart_type`、ch04 `API_SERVER_KEY` 均完整存在于可能包含相邻正文的普通 run。所有匹配 run 的 `run.italic` 均为 `None` 且无 `w:i`；QuickLook 最小首屏 fixture 经目检通过。`quick_validate.py` 因 origin/main 已有且项目规范要求的 `author`、`homepage`、`version` frontmatter 键退出 1，记为 `NOT_VERIFIED`。
- **关联**：DEC-016；用户 2026-08-26 `md2word` 渲染缺陷。

### Task-009：统一导读与案例的 Markdown 引用框

- **状态**：✅ 已完成（待跨仓 PR 合并）
- **目标**：让所有 Markdown `>` 引用块共用正文全宽、无边框灰底的单一配置，并提供真实内边距和稳定的前后/段间距。
- **范围**：`add_quote()` 容器、quote 配置 schema、全部内置预设与 fallback/config-template、模板提取基底、配置参考、端到端 fixture。
- **非目标**：不按“本章导读”“案例”等标签创建分叉样式；不修改法律书 Markdown；不安装或打开 Word。
- **验收证据**：回归 fixture 覆盖单段导读+脚注、多段案例+空引用行、普通正文，最小列表回归另核对 bullet marker 与脚注；与 v1.2.9 合并后的完整 `python3 -m unittest skills/md2word/scripts/test_regressions.py -v` 为 20/20。真实 ch12 临时转换得到 2 个统一 callout 与 10 张数据表，宽度/底纹/边框/内外间距/脚注/粗体/跨页属性均通过 OOXML 结构检查。
- **关联**：DEC-017。

### Task-008：代码框与正文的外部垂直间距

- **状态**：✅ 已完成（已合并 PR #96）
- **目标**：为所有代码围栏增加与前后正文的外部间距，同时保持框内既有代码样式不变。
- **范围**：`scripts/md2word.py` 的首末段间距、`book-publish` 配置、回归测试和使用说明。
- **非目标**：不新增围栏语言；不调整代码框的字体、字号、底纹、边框、左右缩进或框内行距。
- **验收证据**：`python3 -m unittest skills/md2word/scripts/test_regressions.py -v` 通过；新增回归核对三行 `text` 框首行前 6pt、末行后 6pt、中间行 0，并保持 Courier New 9pt / 1.2 倍行距和既有底纹。
- **关联**：DEC-015；法律 AI Skill 书 T205 的窄范围第十一章预览。
