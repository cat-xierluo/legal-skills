# md2word 任务清单

## 已完成

### Task-010：普通技术标识内部下划线按字面量保留

- **状态**：✅ 已完成（待 PR 合并）
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
