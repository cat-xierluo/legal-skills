# 决策记录

本文档记录 `md2word` 技能的重要设计决策与工作日志。

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
