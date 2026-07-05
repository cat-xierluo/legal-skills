# CHANGELOG

## [v1.8.5] - 2026-07-05

### 修复（radar 图例与轴标签重叠 + three-col 子卡片溢出）

用户实际预览 demo 发现两处目检漏检的缺陷，改用**字宽/坐标硬算**补检修复：
- **radar**：底部图例(y≈438) 与底部轴标签"工具/MCP"(y=441) 垂直重叠。修：图例下移到轴标签下方 +50px（gap 24px），H 460→505。`scripts/gen-radar.py`。
- **three-col**：子卡片单行"标签：内容"在 193px 窄列里 ~240px 溢出框。修：改 2 行（标签 14px 加粗 + 内容 13px），CARD_H 50→62。`scripts/gen-three-col.py`。

### 验证（字宽硬算，非视觉工具）
- three-col 9 张卡内容宽 91-167px，全 ≤ COL_W 193px ✅
- radar 图例 rect 顶 465 vs 底部轴标签底 441，间距 24px ✅；图例底 478 vs H 505，余 27px ✅

### 教训（已记入 review-checklist 待办）
视觉多模态目检对"轻微溢出/贴近"易判 OK；以后生成器产出后**首要跑字宽/坐标硬算自检**（CJK≈Fpx/字、Latin≈0.55Fpx/字），视觉工具仅作辅助。

> 注：layout-templates.md §8/§12 骨架示例坐标同步为后续跟进（生成器为真理之源，骨架仅示意）。

## [v1.8.4] - 2026-07-05

### 新增（three-col 三栏并列对比）

新增 three-col 模板：三分类/三版本/三种打法/三层递进的对仗并列（每栏深色表头 + 3-4 子卡片"标签：内容"）。补 matrix（2 列）与 matrix-grid（N×M 网格）之间"卡片化三栏对比"的空缺。

### 改动
- **新模板 `three-col`**（`references/layout-templates.md` §12）：3 等宽栏（gap 30）+ P8 三色相表头（雾蓝/嫩绿/暖米）+ 浅一档子卡片 + "标签：内容"格式 + 可选虚框脚注。
- **生成器 `scripts/gen-three-col.py`**：参数化（TITLE/COLUMNS/FOOTNOTE/调色板）。
- **SKILL.md**：模板表加 three-col 行（"13 种布局模板，11 基础 + 2 组合"）；第一阶段触发词加"三分类/三版本→three-col"；第二阶段模板列表加 three-col；version 1.8.3→1.8.4。
- **决策 DEC-018**：three-col 设计取舍（严格 3 栏、P8 三色相、子卡片对等、与 matrix/matrix-grid 边界）。

### 验证
demo「Skill 的三种典型结构」（3 栏 × 3 卡 + 脚注）生成 + rsvg 渲染 + 多模态目检通过：三栏对仗工整、三色相区分、子卡片清晰、无溢出。

## [v1.8.3] - 2026-07-05

### 新增（matrix-grid N×M 网格矩阵）

新增 matrix-grid 模板：两维交叉对照（风险 × 条款、特征 × 产品、能力 × 模型），单元格用状态符号（√/×/○/—）+ 柔和填充色编码 + 底部图例。补 v1.7.x matrix 仅 2 列对比、不支持 N×M 交叉的局限。

### 改动
- **新模板 `matrix-grid`**（`references/layout-templates.md` §11）：corner label + 顶部/左侧表头（P1 带）+ N×M 单元格 + 状态符号（√/○/×/—）+ 柔和状态色（P3/P7/P4/中性）+ 底部图例。
- **生成器 `scripts/gen-matrix-grid.py`**：参数化（TITLE/CORNER_LABEL/ROW_LABELS/COL_LABELS/CELLS）；CELLS 支持 yes/no/partial/na 或自由文本。
- **SKILL.md**：模板表加 matrix-grid 行（"12 种布局模板，10 基础 + 2 组合"）；第一阶段触发词加"两维交叉对照→matrix-grid"；第二阶段模板列表加 matrix-grid；version 1.8.2→1.8.3。
- **决策 DEC-017**：matrix-grid 设计取舍（4 档状态符号、柔和状态色禁高饱和红绿、N×M 上限、符号须黑白可辨）。

### 验证
demo「合同审查：4 类风险 × 5 类条款 对照矩阵」（4×5）生成 + rsvg 渲染 + 多模态目检通过：符号居中、颜色区分清晰、列宽均匀、图例齐全。

## [v1.8.2] - 2026-07-05

### 新增（timeline-lane 多泳道时间轴）

新增 timeline-lane 模板：多角色/多主体在时间维度上的事件推进（诉讼多角色时间线、案件流程节点、项目多部门进度）。升级 v1.7.x "时间线只能 flow 变通（无刻度）" 的局限。

### 改动
- **新模板 `timeline-lane`**（`references/layout-templates.md` §10）：顶部时间刻度轴（4-6 标签）+ N 条横向泳道（3-5，左侧标签）+ 菱形事件标记（落在时间刻度×泳道中心）+ 标签上下交替减少碰撞；泳道交替极浅带 + 浅灰分隔。
- **生成器 `scripts/gen-timeline-lane.py`**：参数化（TITLE/LANES/TICKS/EVENTS/调色板）。
- **SKILL.md**：模板表加 timeline-lane 行（"11 种布局模板，9 基础 + 2 组合"）；第一阶段触发词加"多角色时间推进→timeline-lane"；第二阶段模板列表加 timeline-lane；可变通表标注"时间线/多角色并行 v1.8.2 起改用 timeline-lane"；version 1.8.1→1.8.2。
- **决策 DEC-016**：timeline-lane 设计取舍（菱形标记、标签上下交替、泳道数上限、单色 vs 多色相）。

### 验证
demo「案件多角色推进时间轴」（4 泳道 13 事件）生成 + rsvg 渲染 + 多模态目检通过：结构清晰、标记对齐泳道中心与刻度、标签上下交替减少碰撞、可读。

## [v1.8.1] - 2026-07-05

### 新增（skill-card Skill 结构模板图）

新增 skill-card 模板：介绍单个 Skill 时的标准骨架（输入 → Skill 三件套 references/scripts/SKILL.md + 流程步骤 → 输出，可选联动虚框脚注）。填补"Skill 结构介绍"这一高频复用场景的模板空缺。

### 改动
- **新模板 `skill-card`**（`references/layout-templates.md` §9）：顶/中/底三层数据流；中央 Skill 主框含深色名称带 + 三件套横排 + SKILL.md 定义的流程步骤列表（①②③④ 编号，3-5 步）；可选底部虚线联动脚注。
- **生成器 `scripts/gen-skill-card.py`**：参数化（TITLE/INPUTS/SKILL_NAME/SATELLITES/STEPS/OUTPUTS/FOOTNOTE/调色板顶部可改）。
- **SKILL.md**：模板表加 skill-card 行（"10 种布局模板，8 基础 + 2 组合"）；第一阶段触发词加"Skill 介绍/结构描述处→skill-card"；第二阶段模板列表加 skill-card；version 1.8.0→1.8.1。
- **决策 DEC-015**：skill-card 设计取舍（单组 P 色建层级、名称带深一档、三件套顺序固定、步骤 3-5 上限）。

### 验证
demo「法律研究 Skill 结构图」（2 输入 + 4 步 + 1 输出 + 联动脚注）生成 + rsvg 渲染 + 多模态目检通过：结构清晰、无重叠、名称带/箭头/文字均正常。

## [v1.8.0] - 2026-07-05

### 新增（radar 雷达图模板，填补"数据可视化不在范围"最大缺口）

补齐 v1.7.x 明确"复杂数据可视化（柱状/折线/饼图）不在范围"留下的缺口：本次解禁并新增 radar 雷达图（多维数值对比）；柱/折/饼仍维持禁用。

### 改动
- **新模板 `radar`**（`references/layout-templates.md` §8）：6-12 维多维度数值对比，1-2 系列；同心多边形网格 + 半透明数据多边形；P1/P4 双色相区分两系列；顶点小圆点增强可读性。布局公式（θ_i = -π/2 + i·2π/N）+ SVG 骨架 + 维度选择纪律（MECE、6-12 维、v_i∈[0,1] 归一化）。
- **生成器 `scripts/gen-radar.py`**：雷达几何随 N 变化手算易错，参数化生成（TITLE/LABELS/SERIES/CX/CY/R 顶部可改）→ `python3 scripts/gen-radar.py out.svg` + `rsvg-convert -w 720 out.svg -o out.png` 目检。
- **SKILL.md**：模板表加 radar 行（"9 种布局模板，7 基础 + 2 组合"）；第一阶段触发词加"多维数值对比描述处→radar"；第二阶段模板列表加 radar；version 1.7.1→1.8.0。
- **决策 DEC-014**：radar 模板设计取舍（几何用生成器、双色相区分系列、网格弱线不抢戏）。

### 验证（眼见为实）
demo「法律 AI 生态六层：理论能力 vs 实际部署」（6 轴 2 系列）生成 + rsvg 渲染 +多模态目检通过：布局正确、标签无碰撞、雾蓝/暖米两系列清晰可辨、无渲染缺陷。

### 后续（v1.8.x 计划）
- `timeline-lane`（多泳道时间轴，真时间刻度，flow 变通的升级）
- `skill-card`（Skill 结构模板图，介绍具体 Skill 时的标准骨架）
- `matrix-grid` 扩展（N×M 网格矩阵，当前 matrix 仅 2 列对比）

## [v1.7.1] - 2026-06-30

### 修复（viewBox 高度按内容裁剪，DEC-013 supersede DEC-001 固定高度部分）

用户 2026-06-30 反馈：SVG 转 PNG 后，图的下边缘离图注间距忽大忽小。排查根因：画布**固定 720×400**（DEC-001），但不同模板内容高度参差（layer 3 层内容底 y=330、flow 水平 4 节点底 y=224、tree 2 层底 y=308），底部留白 70-176px 不一致 → 渲染 PNG 时整个 720×400 都渲染，底部留白被保留 → 图注（在 SVG 下方）与图实际内容底边间距不统一。

### 改动

- **画布规则**：宽度 720px 固定（16开 115mm 通栏），**高度按内容裁剪**——viewBox="0 0 720 H"，H = 内容底边最大 y + 40px。**不再固定 400**。
- **SKILL.md §设计规范**：画布规则、语法门禁（viewBox="0 0 720 H"）、目检渲染命令（`rsvg-convert -w 720` 不指定 -h）。
- **style-guide.md §一画布**：viewBox / 安全边距 / 有效绘图区 / 渲染命令同步。
- **layout-templates.md**：顶部加 v1.7.1 裁剪说明（骨架 `viewBox="0 0 720 400"` 仅为坐标参考系，实际 H 按内容底 + 40；附 layer/flow/tree 示例 H）。骨架内节点坐标不变，只裁底部多余画布。
- **review-checklist.md**：rsvg 命令去 -h、留白项加 viewBox 裁剪、多模态 prompt 描述改 720×H、背景矩形 grep 泛化 height。
- **svg2png.js 不改**：已按 viewBox 自动渲染（行 90-96 读 `vb.height`）。

### 边界（老图不动）

- 仅新生成图走 v1.7.1 裁剪规则；main 既有 SVG（含 v1.5.0-v1.7.0 已生成的）**保持稳定不回改**（沿用"老图不动"原则）。
- 游初定稿 ch01/02/03/09 复用的旧 SVG：Wave 2 配图时按 v1.7.1 回改其 viewBox（用户 2026-06-30 指示"游初那部分先改，其他章后续 review 统一排查"，已记入主项目 TASKS）。

## [v1.7.0] - 2026-06-25

### 重大变更（配色按模板语义分类，DEC-012 supersede DEC-010 部分）

用户 2026-06-25 反馈 ch11 第八节"克制原则 · 五层框架"（图 11-8）颜色太杂——五层用了 5 种完全不同的色相（紫/蓝/绿/米/粉）混搭，破坏层级归属的视觉语义。排查后确认是 v1.5.0 DEC-010 规范的缺陷："内部模块多色"规则**统一应用**到所有 8 种模板，但 layer/tree/金字塔（**层级归属**关系：上层包下层）和 flow/matrix/hub/cycle（**多样性区分**关系：步骤/对比/辐射）的视觉语义**根本不一样**。

### 修复

- **拆分配色规则**（supersede DEC-010 部分）：
  - **layer / tree / 金字塔**模板 → **新 §5.2b G1-G4 单色灰度梯度**（同色相 5 档明度，顶层档 1 最浅、底层档 5 最深）
  - **flow / matrix / hub / cycle**模板 → 保持 §5.2 P1-P8 多色调色板
- **`references/style-guide.md` §5.2b 新增**：4 组灰度梯度
  - G1 蓝灰梯度：`#F0F4F8 / #D6E4F0 / #B8CFE0 / #9AB8D0 / #7CA0BC`（科技/AI/数据/系统）
  - G2 法律米梯度：`#F4ECDC / #E8D8C0 / #D8C4A4 / #C4AE88 / #B8A282`（**法律/合规/正式文书，本 skill 主推荐**）
  - G3 暖灰梯度：`#F0EDE8 / #E8DFD0 / #DCD3C4 / #D0C7B8 / #C4BBAC`（叙事/随笔/文化）
  - G4 蓝梯度：`#E8F0F8 / #C5D9E8 / #A0BED4 / #7CA0BC / #5A82A4`（系统/技术冷调）
- **`references/style-guide.md` §5.0 总则改写**：条件化拆分（layer/tree 走 G1-G4 vs flow/matrix/hub/cycle 走 P1-P8）。
- **`references/layout-templates.md` §2 layer 骨架 + §5 tree 骨架**：改用 G2 法律米梯度（layer 5 档全列；tree 根档 1、子档 2）。
- **`references/review-checklist.md` §③ 加配色分类门禁**：layer/tree 相邻模块 fill 转 HSL 取 hue 差 <30° 判同色梯度合规（违规拒绝）。

### 新增

- **`manuscript/04-实战篇/ch11-合同起草与审查.md` 图 11-8 五层框架**：按 G2 法律米梯度重画（从紫/蓝/绿/米/粉 → `#F4ECDC → #B8A282` 5 档暖色递进）。

### 边界（沿用 v1.5.0 / v1.6.0 原则）

- 仅新生成的 layer/tree/金字塔 走新规则；main 既有图（含 v1.5.0-v1.6.x 已生成的 layer/tree 类）**保持稳定不回改**，沿用"老图不动"原则。

## [v1.6.0] - 2026-06-25

### 修复（箭头规范三重缺陷，DEC-011）

排查用户报告的"箭头和线条、箭头和框对不上"问题，确认根因是 marker 规范三重缺陷叠加，逐一修复：

1. **`<marker>` 缺 `markerUnits="userSpaceOnUse"`**——SVG 规范中 `markerUnits` 默认是 `strokeWidth`（不是像素），导致原 `markerWidth="8"` 在 `stroke-width="2"` 下渲染为 16px、在 `stroke-width="1.5"` 下为 12px，箭头尺寸随线宽飘忽。修复：补 `markerUnits="userSpaceOnUse"`，箭头尺寸固定像素，与 stroke-width 解耦。
2. **模板只示范水平向右一个方向，模型被迫为多方向自造 marker**——实测产物 grep `<marker` 出现 `arrV` / `arrF` / `arrG` / `arrT` / `arrR` / `arrL` / `arrK` / `arrJ` / `arrH` / `arrE` / `arrD` 等 10+ 自创 marker，每个方向硬编码不同 `refX`/`refY`/`orient`，单一规范下方向混乱。修复：marker 强制 `orient="auto"` + 单一 `id="arrow"`，一个 marker 通吃水平/垂直/斜向所有方向。
3. **箭头线终点缺"贴目标框边 − 小间隙"的对齐规则**——hub 骨架 `y2=87` 把箭头扎进上节点（底边 y=94），flow 骨架 `x2=199` 悬空目标框 8px。修复：写明落点规则 `x1 = 源框边 + 4px`，`x2 = 目标框边 − 4px`（y 方向同理）。

### 新增

- `references/style-guide.md` §六「箭头」节改写：补 markerUnits 解释 + orient 解释 + **落点对齐规则表**（含 flow 节点 1→2 坐标计算例）。
- `references/style-guide.md` §十二「SVG 代码模板 A」marker 同步修复。
- `references/layout-templates.md` §1 flow 骨架：marker defs 同步 + 3 条箭头 `x2` 从 `(199, 365, 532)` 改为 `(203, 369, 536)` 按"目标框边 − 4px"重算。
- `references/layout-templates.md` §4 hub 骨架：加 marker defs + 修 `y2=87 → 98`（外围上节点底边 y=94, +4px 间隙）+ 加 `marker-end`。
- `references/layout-templates.md` §5 tree 骨架：加 marker defs + 修 `y2=260 → 256`（子节点顶边 −4px 间隙）；连线仍**不**带 marker-end（tree 通常纯连线表示层级归属），需要方向箭头时按 style-guide §六 自行加。
- `references/review-checklist.md` §③ 视觉目检加**箭头硬约束门禁**：grep `<marker` 只允许**单个** `id="arrow" ... markerUnits="userSpaceOnUse" orient="auto"`，禁止 arrV/arrF/arrG 等自创 id、禁止为多方向硬编码 refX/refY/orient。
- `TASKS.md` 新增 v1.6.0 阶段（已完成·待作者复核）。
- `DECISIONS.md` 新增 DEC-011，记录三重缺陷诊断 + 修复方案 + 渲染实验坐实证据。

### 边界（沿用 v1.5.0 原则）

- 仅新生成图采用新 marker 规范；main 既有图（含 34 张白底老图 + 新生成的多色图里那些 arrV/arrF 自创 marker）**保持稳定不回改**，沿用"老图不动"原则。

### 验证

- 渲染实验 `/tmp/svg-arrow-test/`：A（缺 markerUnits）+ B（修复后）同数据对比。修复前箭头 ~16px 占短线(20px) 80%，流向对但几乎吞掉线；修复后箭头 ~5px 占短线 25%，比例协调，水平/垂直/斜向单 marker 通吃方向正确。

## [v1.5.0] - 2026-06-20

### 新增（全彩印刷配色，方向经作者 2026-06-20 纠正后定稿）
- **透明背景 + 内部模块多色柔和区分**（supersede DEC-002 纯白底 / DEC-003 单一强调色）：所有新生成图**透明背景、不加任何画布底色**；颜色用于 SVG 内部不同模块 / 不同方向之间的多色区分，颜色尽量多样但柔和（去饱和）。
  - `references/style-guide.md` §5.2 预定义 8 组柔和**模块色**调色板（P1 雾蓝 / P2 浅青 / P3 嫩绿 / P4 暖米 / P5 浅紫 / P6 浅粉 / P7 暖灰 / P8 混合柔和系），每组 5-6 个模块色用于内部多模块区分；文字统一深灰 `#2D3436`。
  - §5.3 打印友好：文字色 vs 所在**模块填充色**对比 ≥ 4.5:1（WCAG AA）、相邻模块区分度 ≥10%、模块填充明度 L*≥80、禁高饱和荧光、CMYK 不偏色、灰度可辨。
- `references/review-checklist.md` ③ 视觉目检：新增"透明背景（grep 源码无画布底矩形）" + "内部模块多色（一图 4-6 色、相邻不同色）"检查项；对比度口径改为文字 vs 模块填充色。

### 优化
- 颜色仅用 `fill` / `stroke` 属性内联（**不引入 `<style>` 块 / 不在 `<svg>` 开标签写 font-family / 不画背景矩形 / 不用 class·CSS 变量**），保持 xmllint well-formed + rsvg 无警告 + Obsidian 渲染三重兼容（沿用 `feedback_svg_embed_syntax` 硬约束）。
- `references/layout-templates.md` 5 个模板骨架删除背景矩形 + `<style>` 块，节点填充改用同色组不同模块色。

### 边界
- 仅新生成图采用透明底 + 内部多色；main 既有 34 张白底单色 SVG 保持稳定不回改（作者待确认）。透明底与白底是两种不同做法，老图白底属历史兼容。

## [v1.4.0] - 2026-06-17

### 新增

- **第四阶段：审查与验收（三道门禁）**：生成 + 嵌入后逐章过审查，作为配图验收依据
  - ① 配图密度审查：图/节 ≥ 0.7、图/万字 ≥ 0.8，低于判「偏少」并定位可补图小节；纯 walkthrough / 总结节可省；跨章密度比 < 2×
  - ② 图-正文论点一致性审查：逐图回溯所在小节，核对节点数 / 层级名 / 流程方向 / 对比维度与正文一致，替换 mermaid/ASCII 图信息无损
  - ③ 视觉目检：SVG 渲染为 PNG 后多模态逐图眼检，查文字溢出 / 框重叠 / 箭头错位 / 字号可读 / 黑白可辨
- `references/review-checklist.md`：三道审查的量化指标、判定表、逐图核对清单与多模态目检 prompt 模板（含 legal-ai-skill-book 2026-06-17 实测密度参考）

### 优化

- 插图密度基准从「每章 3-8 张」改为「一节一张为基准，数万字章节 6-8 张」+ 量化指标（图/节 ≥ 0.7、图/万字 ≥ 0.8）
- 强调语法门禁（xmllint well-formed / rsvg 无警告 / 无 font-family / 无 `<style>`）只是**必要不充分**条件——只保证 SVG 合法，不保证图正确美观；密度 + 一致性 + 目检三道审查才是验收依据

## [v1.3.0] - 2026-05-17

### 新增

- `scripts/svg2png.js`：SVG → PNG 高分辨率转换（由 svg-article-illustrator 简化而来）
  - 支持单文件和目录批量转换
  - 默认 600 DPI，支持 72–2400 DPI
  - SKILL.md 新增 PNG 导出使用说明
- 新增 `LICENSE.txt`，补齐 MIT 许可证全文

### 修复

- 修复 `scripts/svg2png.js` 使用 `networkidle0` 导致简单 SVG 转换超时的问题，改为 `domcontentloaded` 并增加 SVG 加载等待
- 修复 PNG 转换失败时浏览器进程可能未关闭的问题，使用 `finally` 兜底关闭
- 修复水平 `flow` 模板 4 节点尺寸不一致的问题，统一为 140px 节点并重算坐标

### 优化

- SKILL.md 精简：去掉"通用性"、"per-book 配置"等冗余说明，以功能说话

### 文档完善

- 将技能级任务跟踪文件从 `ROADMAP.md` 更正为 `TASKS.md`，符合本仓库 Skill 文档约定
- 调整第一阶段流程描述：默认插入占位符并继续生成，仅在用户明确要求时等待确认

## [v1.2.0] - 2026-05-17

### 重大变更：从物理尺寸反推所有参数

- **字号全面校准**：基于 16开 115mm 通栏印刷宽度推算
  - 节点标签：14px → **18px**（物理 2.88mm = 8.2pt，过中文印刷 8pt 下限）
  - 子标签：12px → **16px**（物理 2.56mm = 7.3pt，仅限简短补充）
  - 层标签：14px → **20px**（物理 3.20mm = 9.1pt）
  - 图标题：16px → **22px**（物理 3.52mm = 10pt）
- **标签字数限制收紧**：18px 下每节点最多 8 个汉字（原 14px 下 12 字）
- **元素密度下调**：水平 flow 最多 4 节点（原 5），hub 最多 5 外围（原 6）
- **间距放大**：最小间距 20px → **24px**，水平间距 24px → **28px**
- **新增完整印刷推算章节**：style-guide.md 第二节，含中国开本尺寸表、pt 换算公式、不同开本的最低字号表

### 其他

- layout-templates.md 所有 SVG 骨架的字号、节点尺寸、坐标同步更新
- 新增大32开适配说明（大32开建议缩小 viewBox 或放大字号）

## [v1.1.0] - 2026-05-17

### 新增与优化

- 组合模板、印刷黑白兼容、通用化
- 去掉书籍绑定，diagram-catalog.md 改为纯格式模板
- 场景覆盖分析

## v1.0.0 (2026-05-17)

由 `svg-article-illustrator`（公众号文章配图 Skill）演化而来。针对印刷出版场景重新设计：去掉 SMIL 动画/emoji/非白底等微信适配特性，画布改为 720×400（书籍版面比例），字号和间距按物理尺寸反推，扩展为 6 种通用布局模板。

初始包含：SKILL.md、style-guide.md、layout-templates.md、diagram-catalog.md、extract_svgs.py
