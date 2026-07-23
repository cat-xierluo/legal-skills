# Built-in Image Generation Workflow

本文件用于把公众号文章稳定转成手绘风格配图。默认终图由 ImageGen/Codex/ChatGPT 内置图片生成能力完成；本地脚本默认只做规划和队列。

## 默认路线

1. 读取文章，先提炼章节判断，不要直接把标题、产品名或关键词交给图片模型。
2. 为每张图写 `Image Brief`，确认语义、关系、构图和读者能理解的画面隐喻。
3. 写 `final_prompt_en`，这是给内置生图工具的最终英文 prompt。
4. 用 `batch_article_images.py --mode codex` 生成队列，或在少量图片时直接按 brief 调用 ImageGen/内置生图工具。
5. 逐张生成终图，保存到文章同级或用户指定目录，再插入 Markdown。
6. 默认不要运行 `--mode local`，不要生成 `local_preview/`。只有用户明确要求构图草图、占位预览或本地预览检查时，才额外跑 `--mode local`，并明确标注为诊断草图。

## Image Brief 字段

每张图优先补齐这些字段：

- `chapter_claim_en`：这一节真正的判断，例如“AI capability should be understood as a changing operating environment, not a static tool.”
- `visual_thesis_en`：可画的视觉命题，例如“old rear-view blocks face backward while a new route opens forward through a threshold in the active accent color.”
- `main_relation_en`：图中第一眼必须看出的关系，例如 transition、compression、screening、distribution、layering、handoff、feedback loop。
- `support_structure_en`：帮助理解关系的最小补充结构，例如 “one small trailing input cluster, one threshold object, one clean output path.”
- `reader_takeaway_zh`：这张图帮助读者理解什么，用一句中文写清楚。
- `reference_family`：从本技能的构图家族中选择一个，例如 `cloud funnel output`、`folder archive`、`nested frame`。
- `layout_archetype`：整组构图审计用的版式标签，例如 `left_to_right_transform`、`central_object`、`radial_orbit`、`stack_archive`、`map_field`、`balance_tension`、`scaffold_frame`、`modular_grid`、`single_rare_signal`。
- `abstraction_strength`：可选，控制抽象强度。支持 `reference_card`、`balanced`、`high_abstract`；缺省使用 `config/style.json`。
- `final_prompt_en`：最终英文画面 prompt。它应直接描述画面，不要解释写作意图。

如果 `reader_takeaway_zh` 写不清楚，先继续读文章和提炼章节判断，不要急着出图；难以解释的意象通常不会帮助公众号读者理解文章。

## Prompt 写法

`final_prompt_en` 使用这个结构，不要加入中文、标题原文或可读字词：

> 色值说明：下面的 `#435C68` 等只是 blue-gray 默认主题的示例。生成 prompt 前先从当前主题包（`themes/<active_theme>/theme.json`）读取实际的重点色、纸面色和墨线色填入，不要照抄示例色。主题包切换见 SKILL.md「主题包」章节和 `themes/README.md`。

```text
Wide 16:9 editorial object-card illustration for a WeChat article section. Composition family: [composition family from this skill's families]. [Core visual thesis]. Use a large clear article-serving metaphor, not a centered icon and not a cryptic surreal mechanism. Main relation: [main relation]. Structure: [main object + support structure]. Warm off-white paper background ({paper_background}) or configured flat solid inverted background using the active theme accent color ({accent_name} {accent_color}). Use exactly one accent color ({accent_name} {accent_color}), as a structural hinge, thick connector, active edge, or background field. Near-black bold single-pass hand-inked contour strokes ({ink_color}) with subtle variable width, rounded joins, crisp readable edges, and slight contour irregularity only at outer boundaries. Non-readable abstract marks only. No readable text, no logo, no UI screenshot, no arrows, no plants, no leaves, no decorative corner marks, no face, no eye, no body part, no cryptic surreal object, no photo, no 3D, no gradient, no vignette, no shadow.
```

## Codex 内置生图抽象强度

2026-06-01 多轮小样确认，Codex/ChatGPT 内置生图对手绘线条和固定配色遵循较好，但容易把语义词直译成图标或文档卡片。抽象程度不要写死，使用 `abstraction_strength` 控制。

### `reference_card`

更接近前序参考图，适合需要稳定、清晰、服务理解的正文配图。优先使用：

- `folder archive / archive tray`
- `cloud funnel output`
- `nested frame`
- `workflow book / vessel`
- `chain active block`
- `blue rail blocks`
- `module puzzle chain`

避免 `nameless abstract mechanism`、`soft shell`、`organic plume`、`sealed chamber`、`oracle frame` 等更容易跑偏的语法。

### `balanced`

默认档。以参考图家族为基础，适度提高抽象程度，避免模型把“角色、权限、工具、文件、流程”直译成 UI 图标、文档卡片、dashboard 或软件截图。

优先使用这些可理解、接近参考图的语法：

- `hand-drawn workflow object`
- `object-card mechanism`
- `folder archive / archive tray`
- `nested frame`
- `blue rail blocks`
- `module puzzle chain`
- `chain active block`
- `workflow book / vessel`
- `rounded capsules / hollow endpoints`
- `thick accent-color connector band`
- `blank slabs / pebble-like slabs / abstract blocks`
- `radial orbit / ring table`
- `map field / compass sheet`
- `balance tension frame`
- `scaffold frame`
- `single rare signal inside a larger structure`

把 `cloud funnel output`、`filter gate`、`threshold channel`、`left-to-right output path` 视为限量构图，只在章节关系确实是压缩、筛选或转化时使用。

### `high_abstract`

更接近最近测试中抽象程度更高的机制感，适合少量关键概念图或用户明确想提高抽象度时使用。可以使用：

- `nameless abstract mechanism`
- `soft slabs`
- `rounded shells`
- `slots / hinges`
- `vessels`
- `organic plumes`
- `endpoint capsules / hollow endpoints`
- `thick connector bands`

即使使用高抽象档，也必须先写清 `reader_takeaway_zh`。如果一句中文讲不清读者看这张图能理解什么，就回到 `balanced` 或 `reference_card`。

谨慎使用或避免这些更容易跑偏的词：

- `sealed chamber / aperture / offset sieve / oracle frame / divided capsule archive`
- `role card`
- `permission card`
- `document card`
- `dashboard`
- `profile / user / approval / check`
- `tool / pencil / star / badge / shield`
- `UI panel`
- `face / eye / mouth / body part`
- `horror / mystical symbol / religious symbol`

实测结论：

- “治理、角色、权限”如果直接写，会生成打勾、人像、铅笔、星标等 UI 图标。
- “blank cards / no icons” 能去掉图标，但仍会偏文档卡片。
- “nameless abstract boundary machine / shell / slot / hinge / capsules” 更接近用户参考图的抽象机制语言。
- 漏斗类 `funnel object` 很接近 Workflow 示例，但容易泛化为固定漏斗隐喻；应只在章节关系确实是压缩、筛选或汇聚时使用。
- 第 4-5 轮探索出的 `sealed chamber / aperture / offset sieve / oracle frame` 虽有辨识度，但容易偏离手绘感和文章理解，只作为反例或极少数边界测试，不作为默认方向。

首图补充：

```text
Center-safe for 2400x1024 crop. One dominant object or left-to-right mechanism occupying 60-72% of the canvas width and 55-68% of the canvas height.
```

正文横图补充：

```text
One dominant main object or mechanism occupying 55-68% of the canvas width or visual footprint, with no more than two close supporting marks.
```

方形卡片补充：

```text
1:1 square object-card composition. Centered symbolic object occupying 68-76% of the square canvas.
```

## 抽象隐喻优先级

优先使用能表达关系的隐喻：

- 过渡态：桥、门槛、脚手架、中间层。
- 压缩与筛选：漏斗、样品托盘、过滤盒、收束通道。
- 分发与放大：源对象、扩散云团、粗连接带、大端点对象。
- 分层与治理：层架、轨道、天平、权限门。
- 归档与沉淀：文件夹、证据盒、能力模块、堆叠卡片。
- 反馈与循环：飞轮、回路、仪表盘、时间轴。
- 观察与定位：棱镜、地图、指南针、窗口、放大镜。

低优先级隐喻包括纯节点网络、雷达、放大镜和简单方框连线。它们可以用，但同一篇长文中不要连续重复。

## 构图家族轮换

长文配图要先规划构图家族，再写单张 prompt。这样可以避免所有图片都退化成“方框 + 圆圈 + 连线”，也能避免为了追求多样性而跑到难懂的抽象物件。

推荐轮换这些家族：

- `Sparse chain`：顺序、阶段、交接。
- `Workflow book / vessel`：经验沉淀、方法展开、复用资产。
- `Accent rail blocks`：系统边界、组织秩序、反转底图节奏。
- `Cloud funnel output`：混乱输入到清晰输出。
- `Radial network`：扩散、外部感知、反馈。
- `Chain active block`：准入、判断、状态变化。
- `Stack / camera / archive`：证据、材料、观察和复用。
- `Nested frame`：抽象层级、解释框架、观察位置。
- `Process to network`：流程到协作网络。
- `Folder archive`：归档、知识库、样品托盘。
- `Module puzzle chain`：模块组合、插槽、能力拼接。
- `Orbit / ring table`：开放讨论、未定共识、中心空位。
- `Map / compass field`：方向、定位、路径选择。
- `Balance / tension frame`：悖论、权衡、阈值张力。
- `Scaffold / temporary frame`：草创、搭建、临时秩序。
- `Seed / rare signal`：小而重要的异质信号。

执行规则：

- 每 6 张正文图至少使用 4 个不同构图家族。
- 同一二级标题内的 2-3 张图必须使用不同构图家族。
- 如果前一张是链路结构，下一张优先换成容器、云团、嵌套框、放射网络或档案结构。
- 每组 10-14 张正文图中，`left_to_right_transform` 最多 2-3 张。相邻两张不得都是左输入、中处理、右输出。
- 每 5 张正文图至少安排 2 张非线性版式：`radial_orbit`、`stack_archive`、`map_field`、`balance_tension`、`scaffold_frame`、`modular_grid` 或 `single_rare_signal`。
- 如果 prompt 中 `input / output / funnel / filter / threshold / channel / pipeline / endpoint` 这些词在连续 5 张里出现 3 次以上，说明构图已经被压回收束机制，先重写再生图。
- 多样性只来自构图、关系和主体机制，不通过新增颜色、文字、人物、Logo、UI 图标或复杂背景实现。
- 每张图必须先写清 `reader_takeaway_zh`。如果不能用一句中文说明它帮助读者理解什么，就回到构图家族重写。
- 第 4-5 轮探索意象不作为默认构图家族；不要连续使用封存腔室、观察孔、偏移筛板、神秘框这类难懂对象。
- `final_prompt_en` 开头写明构图家族，例如 `Composition family: nested frame.`

## 手绘对象卡片架构约束

- 画面像低密度对象卡片，不像复杂信息图。
- 主体必须足够大，不能只在中心画一个小图标。
- 重点色（来自当前主题包 `accent_color`，blue-gray 主题默认 `#435C68`）要参与结构，例如语义枢纽、连接带、输出边、活动模块或反转底色，不要只做小点。
- 线条目标是稳定粗墨线，不是潦草手绘。使用 `bold single-pass black contour strokes`、`subtle variable stroke width`、`rounded joins`、`crisp readable edges`。
- 粗细变化来自端点、转角、接缝和重叠处，不来自整圈随机噪声。
- 允许文档块里有 2-4 条不可读短线或波浪线；禁止任何可读字母、数字、标题、标签和 UI 文本。
- 禁止 checkmark、人像、星标、铅笔、工具、app 符号、箭头等熟悉语义图标；用空白卡片、圆点、短线和抽象块表达角色、权限、状态和关系。
- 禁止植物、叶片、花草和边角装饰；它们会把结构化配图带向装饰插画。
- 不主动追求轻微异样感；默认回到本技能构图家族中的手绘对象卡片、清晰关系和可理解隐喻。
- 反转底图必须写明 `flat solid background using the active theme accent color ({accent_color}), no gradient, no vignette, no lighting effect`。

## 内置生图执行边界

- 内置生图是 Agent/宿主环境能力，不是 Python 脚本能力。
- `--mode codex` 只生成队列和目标文件名；真正出图必须由 Agent 调用内置图片生成工具。
- 默认不要跑 `--mode local`，也不要把 `--mode local` 的 PNG 说成 ImageGen/Codex/ChatGPT 生成图。
- 不要默认调用 SiliconFlow、MiniMax、Qwen 或其它外部 API。只有用户明确要求 API 对照或实测时，才使用 `--allow-api`。
