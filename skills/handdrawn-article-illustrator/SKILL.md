---
name: handdrawn-article-illustrator
description: 为微信公众号文章、长文、博客或 Newsletter 生成一组统一视觉系统的手绘风格配图（公众号首图、正文横图、方形卡片）。先理解文章结构与段落核心观点，再为每张图写 Image Brief 和英文视觉 prompt，最终由内置图片生成能力出图；同一篇文章只用一种重点色，配色通过主题包（themes/）配置，可切换或自定义。适用于“手绘配图”“文章配图”“公众号配图”“给文章配图”等需求。
version: "1.1.0"
license: MIT
author: 杨卫薪律师（微信ywxlaw）
homepage: https://github.com/cat-xierluo/legal-skills
---

# 手绘文章配图

为微信公众号文章、博客和 Newsletter 生成一组同一视觉系统的手绘风格配图。核心不是绑定某个品牌，而是稳定产出：大留白、对象卡片、单一固定重点色（由主题包配置）、受控粗黑手绘墨线、低信息密度和清晰隐喻。配图首先服务于理解文章，其次才是风格探索；不要为了新奇牺牲可读性。

## 核心流程

1. 读取文章材料。
   - 如果用户给的是微信公众号链接，先获取正文内容，再进入配图规划。
   - 如果用户给的是 Markdown 或粘贴文本，直接分析标题、二级标题、转折段、案例段和结论段。
2. 生成配图计划。
   - 默认生成：1 张公众号首图 + 高密度正文横图。
   - 短文可以降到 6-8 张正文横图；中长文默认 12-16 张正文横图；长文、案例复盘或产品复盘默认 18-24 张正文横图。
   - 公众号长文优先按“每个二级标题或重要三级标题 2-3 张图”规划，而不是每章只放 1 张分隔图；大致每 250-450 个中文字符安排 1 张。
   - 长文按每个二级标题、三级标题、关键转折段、功能清单段、案例段、金句段和结论段布图。
   - 每张图只承载一个概念，不把整段文章做成信息图。
3. 选择图像类型。
   - **首图**：手绘对象卡片架构，中心为一个方形物件插画，四周留白，适配公众号首图裁切。
   - **正文横图**：16:9 横向插画，用一个隐喻解释当前段落。
   - **方形卡片**：1:1，用于朋友圈、文章列表或单概念卡片。
4. 生成提示词或批量出图。
   - 默认正式路线是 ImageGen/Codex/ChatGPT 内置生图：Agent 先写 `Image Brief` 和最终英文视觉 prompt，再调用宿主环境提供的内置图片生成能力产出 PNG。
   - 批量时使用 `--mode codex` 生成内置生图队列；队列不是终稿，Agent 需要逐张调用内置生图工具。
   - 默认不要运行 `--mode local`，不要生成 `local_preview/`，不要把本地预览纳入默认交付。
   - 只有用户明确要求“构图草图”“占位预览”“本地预览检查”时，才可以运行 `--mode local`；输出必须标注为草图，不能算终图。
   - 当用户要求“测试效果”“生成效果给我看”“跑几轮看看”时，必须调用 ImageGen/内置图片生成能力生成真实样图；本地预览不算成片测试。
   - 不要为了“提升默认效果”主动调用外部图片 API；只有用户明确要求模型对照、API 实测或候选探索时，才走 `guided-edit`、`t2i` 或 `edit`。
   - 只需要提示词时，输出中文配图计划 + 英文图片 prompt。
5. 压缩交付图片。
   - ImageGen 生成后的 PNG 通常偏大。默认使用 `scripts/compress_images.py` 原地压缩最终交付图。
   - 压缩目标是每张尽量低于 `200KB`，硬上限低于 `500KB`；除非用户明确要求保留原始大图，否则覆盖原图。
6. 做质量复核。
   - 检查是否出现可读文字、Logo、写实照片、复杂背景、过多元素或直接复刻任何品牌官网图案。

## 手绘风格要点

先阅读 `references/builtin_image_generation_workflow.md`，理解构图家族的文字描述。执行时抓住这些要点：

- 背景以暖米白为主（具体色值由当前主题包的 `paper_background` 决定，默认蓝灰主题用 `#FAF9F5` / `#F5F4ED` 这类暖白）。
- 主线条用近黑墨线（具体色值由当前主题包的 `ink_color` 决定，默认 `#141413`），更接近“手工描摹出来的填充墨块路径”。轮廓要先稳定干净，但不能像机械矢量图标；粗细变化来自单遍手绘墨线的起笔、收笔、转角压痕和重叠处笔压，长边有自然收放但不随机抖动。
- 重点色固定从当前主题包读取（`config/style.json` 的 `active_theme` 决定用哪个主题，默认蓝灰主题是 `#435C68`）；同一篇文章只使用这一种重点色。
- 背景支持两种模式：`paper` 是暖米白底 + 重点色局部点缀；`inverted` 是重点色底 + 米白主体 + 近黑墨线。长文成组配图必须混用这两种模式：大多数使用 `paper`，少数关键图使用 `inverted` 做节奏重音。
- `inverted` 不是新配色，而是同一重点色的颜色反转：背景整面使用当前主题的重点色，主体块面使用暖米白，线条仍使用近黑墨线；不要在反转底图里再加入第二种强调色。
- 图片像“对象卡片”，不是复杂场景：一个主物件 + 少量贴近主体的辅助元素；主体必须足够大，不要退化成留白中的小图标。
- 以本技能沉淀的构图家族作为主要风格基准：链路、书页/容器、重点色轨道、云团漏斗、放射网络、活动链块、档案堆叠、嵌套框、流程到网络、文件夹归档、模块拼接。多样性应在这些家族内展开，而不是发明难懂的新怪异物件。
- 物件优先选择关系型抽象隐喻：漏斗、棱镜、迷宫、飞轮、脚手架、广播扩散、指南针地图、样品托盘、天平、窗口、放大镜、节点、门、桥、仪表盘、文件夹和流程轨道。每张图都要能一眼看出它在表达压缩、筛选、分发、判断、路径、沉淀或协作中的哪一种关系。
- 第 4-5 轮测试中的“轻微异样机制感”只作为边界探索记录，不作为默认方向。不要主动追求诡异、神秘、器官感或过度抽象；如果某个意象不能帮助读者理解当前章节，就换回参考图里的清晰构图家族。
- 使用 Codex/ChatGPT 内置生图时，抽象程度要受控：可以使用 `object-card mechanism`、`hand-drawn workflow object`、`blank slabs`、`rounded capsules`、`thick connector band`、`archive tray`、`nested frame`、`funnel output` 等词；谨慎使用 `nameless abstract mechanism`、`soft shell`、`organic plume` 这类更容易跑偏的词；少写 `role card`、`document card`、`permission`、`dashboard` 等容易被直译的词。
- 长文同组配图必须控制隐喻重复：不要连续使用“方框 + 圆圈 + 连线”的节点图；优先在压缩、分发、筛选、判断、路径、沉淀、协作等关系之间轮换，并按构图家族轮换。
- 长文同组配图还必须控制版式重复：不要让多张图都变成“左侧输入 - 中间收束/闸门/滤波 - 右侧输出”的横向机制图。这个版式最多作为少量压缩、筛选、转化章节使用，不是默认安全构图。
- 不使用可读文字；如果需要表现“文档/合同/条款”，只画短线和块面，不画真实字。
- 不使用 checkmark、人像、星标、铅笔、工具、app 符号、箭头等熟悉 UI 图标；角色、权限、节点关系要用空白卡片、圆点、短线和抽象块表达。
- 不使用植物枝叶、花草、装饰性散点和边角装饰；模型容易把“自然手绘”误解成插画装饰，必须主动排除。
- 不使用脸、眼睛、嘴、身体部位、恐怖符号、宗教神秘符号、超现实物件或难以解释的陌生器械；不要把“抽象”做成读者看不懂的谜题。
- 不把文章标题、章节标题、关键词原样放进图片 prompt；先改写成 visual-only 概念，避免模型把英文标题、产品名、技术词画进图里。
- 不复制任何品牌官网现成 SVG、Logo、字标或具体图案，只提取通用的结构语言。
- 本 Skill 是后续文章配图的唯一主入口。不要再为相近风格新建并列 Skill；如需调风格，优先切换或新建主题（`themes/`）、调 `abstraction_strength` 或改 `references/`，不要在 SKILL.md 或脚本里硬编码色值。

## 主题包（Theme Pack）

本 Skill 的配色（重点色、纸面色、墨线色）不再硬编码，而是由**主题文件**提供。一个主题文件 = 一组配色。这样不同律所、团队或作者可以复用同一套构图与流程，只替换色彩。

内置主题包在 `themes/` 目录：

| 主题包 | 重点色 | 适用 |
|--------|--------|------|
| `blue-gray`（默认） | `#435C68` 蓝灰 | 法律、公众号长文、编辑类 |
| `ink-black` | `#2A2A28` 墨黑 | 极简、无品牌色需求；复用 blue-gray 参考图 |
| `terracotta` | `#A65A3D` 赭石 | 人文、文化、生活方式；复用 blue-gray 参考图 |

`blue-gray` 是默认激活主题。完整说明见 `themes/README.md`。

### 切换主题

三选一，优先级从高到低：

1. **命令行参数**（单次出图）：`generate_prompts.py --theme ink-black` 或 `batch_article_images.py --theme ink-black`。
2. **大纲级覆盖**（整篇文章生效）：在 outline JSON 里写 `"style": { "theme": "terracotta" }`。
3. **改默认激活主题**（长期生效）：编辑 `config/style.json`，把 `active_theme` 改成主题包名。

切换后，`generate_prompts.py` 会从 `themes/<name>.json` 读取配色注入 prompt，无需改其他文件。

### 创建自己的律所主题包

适合律所、品牌号或个人作者注入自己的主题色。核心步骤：

1. 新建 `themes/my-firm.json` 文件。
2. 定义 `colors`（`accent_color` 重点色、`paper_background` 纸面色、`ink_color` 墨线色）。
3. 用 `--theme my-firm` 或改 `active_theme` 激活。

详细模板见 `themes/README.md`。**关键约束**：一篇文章只用一种重点色；纸面色保持低饱和暖白。

### 色值微调（不改主题包）

如果只想临时改一个色值、不想新建主题包，在 `config/style.json` 的 `overrides` 里写：

```json
{ "active_theme": "blue-gray", "overrides": { "accent_color": "#3A4F5C" } }
```

`overrides` 优先级高于主题包，低于命令行 `--theme` 和 outline `style.accent_color`。

## 抽象强度

本 Skill 内置三档抽象强度，写在 `config/style.json` 的 `abstraction_strength`，也可以在 outline 的 `style.abstraction_strength` 或单张 `illustrations[].abstraction_strength` 覆盖：

| 档位 | 使用场景 | 风格边界 |
|------|----------|----------|
| `reference_card` | 想更接近前序参考图、优先服务理解、避免跑偏 | 优先 `folder archive`、`cloud funnel output`、`nested frame`、`workflow book`、`chain active block` 等可解释构图；少用无名机制、软壳、雾状扩散 |
| `balanced` | 默认档，适合大多数公众号文章 | 在参考图家族内适度抽象，避免直译成文档卡片、UI 面板、权限图标或 dashboard，但保留一句话能讲清的隐喻 |
| `high_abstract` | 想使用最近测试里抽象程度更高的机制感 | 可用 `nameless abstract mechanism`、`soft slabs`、`rounded shells`、`slots`、`hinges`、`vessels`、`organic plumes`、`endpoint capsules`，但必须有清晰 `reader_takeaway_zh` |

默认使用 `balanced`。长文成组配图可以混用：关键章节或结论图用 `reference_card` 保持清晰，少数更概念化的章节用 `high_abstract` 提升风格变化。不要连续多张使用 `high_abstract`，除非用户明确要更实验化的视觉方向。

## 比例与尺寸

沿用本技能从前序配图流程沉淀下来的比例策略：

| 用途 | 默认生成比例 | 默认生成尺寸 | 交付建议 |
|------|--------------|--------------|----------|
| 公众号首图 | 宽画幅生成后导出 | 内置生图宽画幅；API 实验可用 `2048x872` | 导出 `2400x1024`，主物件放中心安全区 |
| 正文横图 | 宽画幅 | 内置生图宽画幅；API 实验可用 `2048x872` | 直接用于正文，或按需要等比缩放 |
| 方形卡片 | 1:1 | `1024x1024` 或模型默认方图 | 用于封面、列表、朋友圈卡片 |

首图最终是 `2400x1024`。默认内置生图路线用宽画幅 prompt 生成，再按需要导出或裁切到 `2400x1024`。外部 API 实验路线沿用旧尺寸策略：Z-Image 可用 `2048x872`，显式切回 `Qwen/Qwen-Image` 时使用 `1664x928`。提示词要明确 `center-safe composition`，避免主体贴近上下边缘；同时主体不要太小，默认应占画面宽度约 60-72%。

## 主体占比

默认采用“大主体、少元素、适度留白”的公众号正文图策略：

- **首图**：主体占画面宽度约 60-72%，高度约 55-68%，放在中心安全区。
- **正文横图**：主体占画面宽度或视觉重量约 55-68%，辅助符号不超过 2 个，并贴近主体。
- **方形卡片**：主体占方形画面约 68-76%。

这些比例写在 `config/style.json` 的 `cover_subject_scale`、`inline_subject_scale` 和 `card_subject_scale` 中。若文章需要更空灵的手绘对象卡片感，可以调低；公众号正文默认不要低于上述范围。

## 生成路线

正式交付路线是 **ImageGen / Built-in Image First**：Agent 负责理解文章、确定语义和构图，终图由 ImageGen/Codex/ChatGPT 的内置图片生成能力完成。不要把 Python 本地渲染器误认为“内置生图能力”，也不要把本地预览或外部 API 调试路线当作默认路线。

如果当前宿主环境提供 ImageGen 工具，真实成片测试优先直接调用 ImageGen。`codex_generation_queue.md` 只是给 Agent 调用 ImageGen 的队列；只有队列没有出图时，不能宣称已经完成“成片测试”。

1. 先读取文章，按 `references/builtin_image_generation_workflow.md` 写每张图的 `Image Brief`：
   - `chapter_claim_en`：这一节真正的判断。
   - `visual_thesis_en`：可画出来的视觉命题。
   - `main_relation_en`：第一眼必须看出的关系。
   - `support_structure_en`：帮助理解关系的最小补充结构。
   - `final_prompt_en`：Agent 直接写给内置生图工具的最终英文画面 prompt。
2. `generate_prompts.py` 将 outline、配置色和风格约束编译成 `prompts.json`。如果有 `final_prompt_en`，脚本优先保留 Agent 写好的画面，而不是用固定模板覆盖。
3. `batch_article_images.py --mode codex` 输出 `codex_generation_queue.json` 和 `codex_generation_queue.md`。
4. Agent 逐条读取队列，调用 ImageGen/Codex/ChatGPT 内置图片生成工具生成最终 PNG；生成后按建议文件名保存，并插入 Markdown 或交付目录。
5. 默认流程到真实生图为止，不再额外跑本地预览。本地渲染器只在用户明确要求构图草图、占位检查或 API guided-edit skeleton 时使用。
6. 交付前运行 `scripts/compress_images.py` 压缩最终图片，默认目标 `200KB`、硬上限 `500KB`。

默认命令：

```bash
python3 scripts/batch_article_images.py \
  --outline assets/outline_sample.json \
  --outdir out \
  --mode codex
```

这条路线不会读取 API Key，也不会调用 SiliconFlow、MiniMax 或其它外部图片接口。脚本会输出：

- `prompts.json`：常规提示词与构图契约。
- `codex_generation_queue.json`：给 Agent 调用内置图片生成能力的结构化队列。
- `codex_generation_queue.md`：人工可读的逐图 prompt。

重要边界：Codex/ChatGPT 的内置图片生成能力是 Agent/宿主环境能力，不是当前 Python 进程里的本地模型。因此 `--mode codex` 只能准备队列和目标文件名，不能像外部 API 那样由脚本直接返回 PNG。执行时由 Agent 在对话中调用内置图片生成工具；如果宿主环境返回可保存文件，再按队列里的建议文件名归档。

外部 API 仅作为显式实验路线。只有用户明确要求“跑 API”“模型对比”“再试外部模型”时，才区分这些约束强度；否则不要调用 SiliconFlow、MiniMax、Qwen 或其它外部图片接口。

- **文字转述约束**：`t2i` 只接收 prompt，模型仍可能改布局、加字或换风格。
- **图像构图约束**：`guided-edit` 先用本地渲染生成 `composition_guides/`，再让编辑模型沿着输入图重绘；这是 API 路线中更接近本地预览的方式。
- **候选筛选要求**：实测 `guided-edit` 能明显保住布局，但仍可能引入非配置色、旧纸感、红点或浅棕块。API 输出必须先和 `composition_guides/` 对照，并检查是否只使用当前主题包的重点色、近黑和米白（不引入第二种强调色）。

## 配图计划格式

只在对话里交付时，使用这个结构：

```markdown
## 配图计划

| 序号 | 位置 | 用途 | 画面隐喻 | 核心概念 | 比例 |
|------|------|------|----------|----------|------|
| 01 | 标题后 | 首图 | [对象卡片] | [一句话] | 2400x1024 |
| 02 | 第一个二级标题后 | 正文横图 | [隐喻] | [一句话] | 16:9 |

## 图片提示词

### 01 首图
Prompt: ...
Negative prompt: ...
```

Prompt 用英文写，配图计划用中文写。这样既方便中文审稿，也更适合常见图片模型。

注意：图片 prompt 不能包含文章标题、章节标题或关键词原文。标题只用于配图计划和文件命名；真正进入图片模型的内容必须是去文字化视觉概念，例如把 `HTML table` 改成 `complex merged-cell grid`，把产品名改成 `the lightweight reading tool`。

## 配图密度

公众号文章默认是“高密度正文配图”，不要只做少量章节分隔图。除非用户明确要求少图，否则按下面节奏规划：

- **短文**：1 张首图 + 6-8 张正文横图。
- **中长文**：1 张首图 + 12-16 张正文横图。
- **长文或案例/产品复盘文**：1 张首图 + 18-24 张正文横图。

长文密度基准：

- 每个 `##` 二级标题默认安排 2-3 张正文图。
- 内容较长或有多个转折的 `###` 三级标题，也按 2 张左右处理。
- 单章如果只有 1 张图，通常只适合作为章节分隔，不足以覆盖公众号阅读节奏；除非该章非常短，否则继续补关键判断图。
- 同一章的多张图必须分别对应不同判断：问题定义、机制变化、信任/资产/边界/判断等关系，不要只是同义反复。

正文图位优先覆盖这些位置：

- 开篇后的问题定义。
- 每个 `##` 二级标题后的第一个核心判断。
- 重要 `###` 小节。
- 功能清单、对比段、技术选择、流程描述、开发节奏、关键抉择、结论段。

如果文章有 5 个以上二级标题，每个二级标题至少安排 1 张；内容较长的二级标题下再补 1-2 张。配图多时，通过 `paper` / `inverted` 背景模式轮换和不同隐喻保持节奏，但仍保持同一线条、固定重点色和低信息密度。

反转图数量按组控制：

- 6-8 张正文图：安排 1-2 张 `inverted`。
- 10-14 张正文图：安排 2-4 张 `inverted`，默认约每 4 张出现 1 张。
- 首图默认用 `paper`，不要一上来就整页蓝底；反转图优先放在关键转折、结论、系统边界、分发放大、人的判断等章节。
- 同一组图不要连续出现两张 `inverted`，除非用户明确要求强烈节奏。

## 多样性策略

不要只靠 `soft shell / slot / hinge` 一组语法出图。把同一篇文章的图分配到不同构图家族。多样性的目标是让不同章节的关系更容易理解，不是制造更奇怪的抽象物。

| 构图家族 | 适合关系 | 画面特征 |
|----------|----------|----------|
| Sparse chain | 顺序、阶段、交接 | 少量圆角块沿横线推进，一个重点色活动块 |
| Workflow book / vessel | 经验沉淀、方法展开 | 厚书页、容器、出口或侧向输出 |
| Accent rail blocks | 系统边界、组织秩序、反转图 | 重点色底或重点色轨道，米白块沿轨道排列 |
| Cloud funnel output | 混乱输入到清晰输出 | 有机云团、漏斗/喇叭口、清晰端点 |
| Radial network | 扩散、外部感知、反馈 | 中心节点向外发散，但节点数量受控 |
| Chain active block | 审批、准入、判断、状态变化 | 横向链路中一个重点色活动模块 |
| Stack / camera / archive | 证据、材料、复用资产 | 堆叠块、档案盒、观察孔、存储结构 |
| Nested frame | 抽象层级、解释框架、观察位置 | 多层嵌套框，中间重点色核心 |
| Process to network | 从流程到协作网络 | 输入列表、过程块、网络化输出 |
| Folder archive | 归档、知识库、样品 | 文件夹、抽屉、托盘、样品块 |
| Module puzzle chain | 模块拼接、能力组合 | 拼图式连接件、模块链、插槽结构 |
| Orbit / ring table | 开放讨论、共识尚未形成、中心空位 | 环形桌面、圆环结构、中心留空，周围卡片松散连接 |
| Map / compass field | 方向、定位、路径选择、可移植姿态 | 折叠地图、指南针、路径片段、少量标记点 |
| Balance / tension frame | 悖论、权衡、阈值张力 | 中心支点、两侧块面、张力框、悬置结构 |
| Scaffold / temporary frame | 草创、搭建、临时秩序 | 脚手架、未封闭框架、支撑杆、半成型对象 |
| Seed / rare signal | 稀缺信号、诚实无知、小而重要的发现 | 大结构中的小胶囊、样本托盘中的单个异质块 |

执行规则：

- 每 6 张正文图至少使用 4 个不同构图家族。
- 同一章内 2-3 张图必须使用不同构图家族，避免连续“方框 + 连线”。
- 如果前一张用了链路，下一张优先用容器、云团、嵌套框、放射或档案结构。
- 每组 10-14 张正文图中，“左侧输入 - 中间处理/收束 - 右侧输出”的横向转化版式最多 2-3 张；相邻两张不得使用这个版式。
- `funnel`、`filter`、`threshold gate`、`channel`、`pipeline`、`output bands`、`endpoint capsules` 属于同一类“收束输出版式”。除非章节关系明确是压缩、筛选、交付或转化，否则不要使用。
- 每 5 张正文图至少安排 2 张非线性版式，例如环形讨论、地图定位、堆叠档案、样本托盘、平衡张力、脚手架、中心留空、模块拼接或单点稀缺信号。
- 多样性来自构图和关系，不来自增加颜色、文字、人物、图标或复杂背景。
- 每张图都要通过一句中文先说明“这张图帮助读者理解什么”。如果这句话说不清，说明该意象不合格，应回到构图家族重写。
- `Sparse chain` 必须明确写成“小圆角块沿细线推进、其中一个重点色活动块”，不要只写 `chain` 或 `slot`，否则模型容易画成难懂的抽象插槽物。
- 避免连续使用 `sealed chamber`、`oracle frame`、`aperture`、`offset sieve` 等第 4-5 轮探索意象；这些容易脱离手绘风和文章理解，不作为默认构图家族。
- 写 prompt 时先声明构图家族，再写章节语义。例如：`Composition family: nested frame. Visual thesis: ...`

## 构图审计

在调用 ImageGen 之前，先做一遍整组构图审计。不要逐张孤立写 prompt，否则 Agent 很容易把抽象论证统一翻译成横向收束机制图。

为每张图列出：

| 图位 | reader_takeaway_zh | reference_family | layout_archetype | 是否横向收束 |
|------|--------------------|------------------|------------------|--------------|

`layout_archetype` 使用这些更具体的版式标签：

- `left_to_right_transform`：左输入、中处理、右输出。严格限量。
- `central_object`：单个中心对象，周围少量辅助块。
- `radial_orbit`：环形、圆桌、中心空位、周围节点。
- `stack_archive`：堆叠、档案、抽屉、样本盒。
- `map_field`：地图、指南针、路径片段。
- `balance_tension`：张力、权衡、阈值、支点。
- `scaffold_frame`：脚手架、临时框架、半成型结构。
- `modular_grid`：模块拼接、网格但非 UI。
- `single_rare_signal`：大结构中的小而清晰的异质信号。

审计规则：

- 如果 `left_to_right_transform` 超过全组 25%，重写多余图位。
- 如果连续两张都是 `left_to_right_transform`，重写后一张。
- 如果 `funnel/filter/channel/gate/output` 相关词在 5 张内出现 3 次以上，改用 `radial_orbit`、`map_field`、`stack_archive`、`balance_tension` 或 `scaffold_frame`。
- 如果总览图里 4 张以上都呈现“左宽右窄”或“左散右整”的轮廓，说明已经跑偏，必须重写提示词再生图。

## Prompt 模板

> **重要**：以下模板里的色值（`#FAF9F5`、`#141413`、`#435C68` 等）只是 blue-gray 默认主题的示例。生成 prompt 时必须先从当前主题文件（`themes/<active_theme>.json`，由 `config/style.json` 的 `active_theme` 决定）读取实际色值，替换进 prompt；不要照抄模板里的示例色。命令行或 outline 指定了 `--theme` 时，以该主题的色值为准。

### 公众号首图

```text
Wide WeChat article cover illustration, generated in 16:9 and center-safe for 2400x1024 crop. Hand-drawn editorial object-card style based on this skill's composition families, not a copy of any brand asset. Warm off-white paper background ({paper_background}), flat with no vignette or lighting effect, one large centered symbolic object occupying 60-72% of the canvas width and 55-68% of the canvas height, near-black hand-inked filled contours ({ink_color}), stable silhouette that feels hand traced in one confident pass, subtle imperfect parallel edges, tapered stroke starts and ends, small pressure flattening at corners and overlaps, flat muted accent block in the active theme color ({accent_name} {accent_color}). Article-serving metaphor: [隐喻]. It should help readers understand: [当前段落核心观点]. Show only [1 个主物件] plus [1-2 个贴近主体的辅助元素]. Generous but not excessive negative space, quiet editorial composition, no cryptic surreal mechanism, no mechanical vector icon, no arrows, no plants, no leaves, no decorative corner marks, no ruler-straight edges, no tiny centered icon, no readable text, no logo, no watermark, no gradients, no vignette, no shadows, no 3D, no photorealism.
```

线条必须进一步写成：

```text
near-black hand-inked filled contour paths, stable readable silhouettes, single-pass confident hand tracing, subtle imperfect parallel edges, gently tapered stroke starts and ends, small pressure flattening at corners/overlaps/joints/terminal caps, long edges calm with organic tapering, not a smooth uniform rounded stroke and not a mechanical vector outline
```

更精确地说：使用“自然但受控的手绘”，不是“随机的不规则”。轮廓主体应稳定、清晰、可识别；粗细变化来自起笔、收笔、转角压痕和结构锚点，不来自整条线的乱抖，也不要让每条边都出现墨块噪声。内部细线可以更细，并带轻微收笔。

### 正文横图

```text
16:9 horizontal editorial illustration for a WeChat article section. Hand-drawn object illustration system based on this skill's composition families, not a direct copy. Warm off-white paper background ({paper_background}), flat with no vignette or lighting effect. Use exactly one accent color from the active theme ({accent_name} {accent_color}), about 8-15% of the image. Near-black hand-inked filled contours ({ink_color}): stable readable silhouettes first, single-pass confident hand tracing, slight human asymmetry, gently tapered starts and ends, small pressure flattening at corners and overlaps; long edges stay calm with organic tapering, no random contour noise. One clear article-serving metaphor: [隐喻]. Help readers understand this concept: [当前段落核心观点]. Use one dominant main object occupying 55-68% of the canvas width or visual footprint, plus up to 2 close supporting marks. Spacious but not empty, calm, low-detail, understandable, no cryptic surreal mechanism, no mechanical vector icon, no arrows, no plants, no leaves, no decorative corner marks, no ruler-straight edges, no tiny centered icon, no readable text, no logo, no gradient, no vignette, no shadow, no 3D, no photo.
```

### 反转底图（inverted）

```text
16:9 horizontal editorial illustration for a WeChat article section. Hand-drawn object illustration system, not a direct copy. Flat solid background using the active theme accent color ({accent_name} {accent_color}) as the whole canvas field, with no vignette, no lighting effect, no gradient, and no texture. Warm off-white object surfaces ({paper_surface}), near-black hand-inked filled contours ({ink_color}), stable silhouette, single-pass confident hand tracing, subtle tapering at stroke ends, small pressure flattening at structural corners and joins, one clear metaphor: [隐喻]. Main object occupies 55-68% of the canvas width or visual footprint. No mechanical vector icon, no arrows, no plants, no leaves, no decorative corner marks, no ruler-straight edges, no tiny centered icon, no random shaky lines, no lumpy edge noise, no second accent color, no readable text, no logo, no gradient, no vignette, no shadow, no 3D, no photo.
```

### 方形卡片

```text
1:1 square object-card illustration in hand-drawn editorial style. Use paper mode or inverted mode from config/style.json. Centered symbolic object occupying about 68-76% of the square canvas, near-black hand-inked filled contours with stable silhouette, single-pass confident hand tracing, tapered ends, and a few structural pressure accents, flat off-white inner surfaces, one concise metaphor for [概念]. Minimal composition, no mechanical vector icon, no arrows, no plants, no leaves, no decorative corner marks, no tiny icon, no readable text, no logo, no photorealism.
```

## 隐喻库

| 场景 | 优先隐喻 |
|------|----------|
| 经验显性化、解释、观察位置 | 棱镜、指南针地图、窗口、放大镜 |
| 复杂输入到清晰输出 | 漏斗、样品托盘、文件夹、证据盒 |
| 分发、放大、外部感知 | 广播扩散、节点网络、桥 |
| 组织治理、责任边界 | 脚手架、分层框架、天平、门闸 |
| 审批、准入、权限 | 门闸、桥、钥匙孔、迷宫出口 |
| 风险识别、预警、分级 | 雷达、仪表盘、迷宫路径 |
| 资产化、复用、长期循环 | 文件夹、飞轮、时间轴、积木 |
| 协作、Agent 工作流 | 桥、浏览器窗口、轨道、广播扩散 |

法律公众号文章优先使用“关系型隐喻”，也就是能看出压缩、筛选、分发、判断、路径、沉淀或协作关系的画面。放大镜、雷达、节点网络属于低风险但容易重复的基础隐喻；一篇长文中不要大量重复使用。避免过度科技感、营销海报感和纯流程图感。

## 批量规划与 ImageGen 出图

默认 `codex` 队列只依赖 Python 标准库。首次使用显式诊断工具、`guided-edit` 或其它 API 实验前，在本目录运行：

```bash
python3 -m pip install -r scripts/requirements.txt
```

准备大纲 JSON，可从 `assets/outline_sample.json` 复制修改。核心字段：

- `title`：文章标题
- `title_en`：英文标题，用于图片 prompt；如果没有，脚本会退回 `title`
- `aspect`：默认 `16:9`
- `style.background_mode_sequence`：每张图轮换 `paper` / `inverted` 两种背景模式。
- `style.abstraction_strength`：全篇抽象强度，支持 `reference_card`、`balanced`、`high_abstract`；默认从 `config/style.json` 读取。
- `illustrations[].abstraction_strength`：单张图覆盖抽象强度，用于在一篇文章内混排更接近参考图和更高抽象度的画面。
- `config/style.json`：激活主题指针（`active_theme`）、本地色值覆盖层（`overrides`）和墨线、抽象度等结构性配置；重点色实际值来自主题文件 `themes/<active_theme>.json`。
- `illustrations[]`：每张图的位置、用途、隐喻、关键词和强调对象；建议为每项补 `title_en`、`concept_en`，保证最终 prompt 主要为英文
- 正式高质量生成时，为每项补 `chapter_claim_en`、`visual_thesis_en`、`main_relation_en`、`support_structure_en` 和 `final_prompt_en`；脚本会优先使用 Agent 写好的 `final_prompt_en`。

默认内置生图队列：

```bash
python3 scripts/batch_article_images.py \
  --outline assets/outline_sample.json \
  --outdir out
```

该命令等价于 `--mode codex`，会输出 `prompts.json`、`codex_generation_queue.json` 和 `codex_generation_queue.md`。随后由 Agent 调用 ImageGen/Codex/ChatGPT 内置图片生成能力生成终图。默认到这里就进入真实生图，不再额外跑 `local` 预览。

显式诊断工具：本地构图草图。默认不要运行；只有用户明确要求构图草图、占位预览或本地预览检查时才使用：

```bash
python3 scripts/batch_article_images.py \
  --outline assets/outline_sample.json \
  --outdir out \
  --mode local
```

`local` 会输出每张 PNG、首图 `2400x1024` 导出版和 `overview_board.png`，用于检查构图、主体占比、隐喻重复和画幅安全区。它是显式诊断/草图路线，不是默认流程的一部分，不能用于替代 ImageGen 成片。

默认图片压缩：

```bash
python3 scripts/compress_images.py /path/to/generated-image-dir
```

该脚本会原地覆盖图片，默认尽量压到 `200KB` 以下，并要求每张低于 `500KB`。它优先使用 `pngquant`；如需安装：

```bash
brew install pngquant imagemagick
```

如果极少数图片仅靠压缩无法低于 `500KB`，可显式允许缩放：

```bash
python3 scripts/compress_images.py /path/to/generated-image-dir --allow-resize
```

外部 API 松约束实验：

```bash
python3 scripts/batch_article_images.py \
  --outline assets/outline_sample.json \
  --outdir out \
  --mode t2i \
  --allow-api \
  --image-size auto \
  --final-size 2400x1024
```

默认文生图模型为 `Tongyi-MAI/Z-Image-Turbo`。这条路线只用于显式实验和横向对照，不作为默认交付主路；`Qwen/Qwen-Image` 和 MiniMax `image-01` 只作为压力测试，`Qwen/Qwen-Image-Edit-2509` 作为 skeleton fallback。所有外部 API 模式都必须显式加入 `--allow-api`，否则脚本会拒绝执行，避免默认交付误触发 API。

外部 API 构图锁定实验：

```bash
python3 scripts/batch_article_images.py \
  --outline assets/outline_sample.json \
  --outdir out \
  --mode guided-edit \
  --allow-api
```

`guided-edit` 会先输出 `composition_guides/` 本地构图草图，再调用编辑模型。它比纯 `t2i` 更适合把“已确定的语义和构图”转述给 API，但仍只是候选实验，不能默认替代内置生图终稿。

如果使用空底图编辑模式保持系列一致性：

```bash
python3 scripts/batch_article_images.py \
  --outline assets/outline_sample.json \
  --outdir out \
  --mode edit \
  --allow-api
```

配置 API Key：

- 只有显式使用 `--allow-api` 的 API 实验路线才需要配置。
- 复制 `config/secrets.env.example` 为 `config/secrets.env`
- 填入 `SILICONFLOW_AK`
- 不要提交 `config/secrets.env`（已被 `.gitignore` 忽略）

## 输出检查

- [ ] 每张图是否只有一个核心概念。
- [ ] 默认交付是否由 Agent 调用 ImageGen/Codex/ChatGPT 内置图片生成能力完成，而不是把本地渲染草图当终图。
- [ ] 是否先写 `Image Brief`，再写最终英文视觉 prompt；不要只靠章节标题或关键词套模板。
- [ ] 是否使用 `--mode codex` 生成队列，并随后调用 ImageGen/内置生图工具生成真实 PNG。
- [ ] 是否没有默认运行 `--mode local` 或生成 `local_preview/`；如用户明确要求本地草图，是否标注为诊断草图而不是正式交付图。
- [ ] 是否已运行 `scripts/compress_images.py` 压缩最终图片，默认每张低于 `500KB`，尽量低于 `200KB`。
- [ ] 如果用户明确要求 API 实验，是否优先使用 `guided-edit`，并检查 `composition_guides/` 是否与最终图的主体、布局和背景模式一致。
- [ ] 主体是否在中心安全区，首图裁切后不丢关键信息。
- [ ] 主体是否足够大：正文横图不应像小图标，默认主体占画面宽度或视觉重量约 55-68%。
- [ ] 是否使用配置中的固定重点色（来自当前主题包）；白底图只做局部重点色，反转底图不引入第二种重点色。
- [ ] 墨线是否像单遍手工描摹：有起笔收笔和转角压痕，而不是机械矢量描边、统一圆润描边、整圈随机墨块或抖动草稿线。
- [ ] 是否避免了可读文字、Logo、水印、真实 UI 截图和照片质感。
- [ ] prompt 是否已去文字化：不得把文章标题、章节标题、关键词或产品名原样送进图片模型。
- [ ] 是否没有直接复刻任何品牌官网现成插画。
- [ ] 同一篇文章是否通过白底/蓝底节奏变化增强层次，但没有变成多色彩虹。

## 参考文件

- `references/handdrawn_style_architecture.md`：手绘对象卡片风格来源、结构语言与落地规则。
- `references/builtin_image_generation_workflow.md`：内置生图默认路线、Image Brief 字段和 prompt 写法。
- `references/siliconflow_images_api.md`：SiliconFlow 图片接口要点。
- `config/style.json`：激活主题指针、色值覆盖层与墨线风格等结构性配置。
- `themes/`：主题文件目录，每个文件定义一组配色（重点色、纸面色、墨线色）；详见 `themes/README.md`。
