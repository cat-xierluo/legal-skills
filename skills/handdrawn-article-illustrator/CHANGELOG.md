# Changelog

## [1.1.0] - 2026-07-23

### 新增

- 新增**主题包（Theme Pack）机制**：配色（重点色、纸面色、墨线色）从硬编码解耦为 `themes/` 目录下的独立主题包，律所或团队可注入自有主题色与参考图。
- 内置三套主题预设：`blue-gray`（蓝灰，默认，原作者个人定制）、`ink-black`（墨黑中性）、`terracotta`（赭石暖调）。
- 新增 `themes/README.md`：主题包使用、切换与自建指南（含律所主题包创建步骤、theme.json 模板、参考图替换说明）。
- `generate_prompts.py` 新增 `--theme` 参数；`batch_article_images.py` 同步透传 `--theme`。

### 改进

- 重构配置加载链：优先级为 `outline.style.<key>` > `config.overrides` > `theme.json.colors` > `DEFAULT_STYLE`，主题包缺失时优雅回退到中性兜底色（不崩溃）。
- `config/style.json` 从"色值仓库"改为"激活主题指针（`active_theme`）+ 本地覆盖层（`overrides`）+ 结构性配置"；色值统一由主题包提供。
- 去除 SKILL.md、references/、scripts 中所有蓝灰色值硬编码（Prompt 模板、隐喻库、架构文档），改为配置引用与占位符（`{accent_color}` 等），明确"Agent 生成 prompt 时必须从当前主题包读取实际色值"。
- `inverted` 模式与颜色解耦：明确反转底图使用当前主题的重点色，不再绑定"蓝灰"。
- 构图家族 `Blue rail blocks` 中性化为 `Accent rail blocks`。

### 技术优化

- `load_theme()` 解析主题包，缺失时回退 `FALLBACK_THEME_COLORS`，保证脚本健壮性。
- `build_composition_spec` 的 lock_rules 中硬编码的 "blue-gray accent" 改为动态 `{accent_name} accent`。
- 迁移到 `legal-skills/skills/` 公开发布（MIT 许可证），新增局部 `.gitignore` 覆盖运行产物（`local_preview/`、`prompts.json`、`secrets.env` 等）。
- 将 `secrets.env.example` 从根目录移至 `config/`，与 `style.json` 统一管理；`batch_article_images.py` 的 `--env` 默认路径同步改为 `config/secrets.env`；`.gitignore` 用 `!*.env.example` 取反规则保留模板文件，避免误删。
- 主题结构扁平化：从 `themes/<name>/theme.json` 二级目录简化为单文件 `themes/<name>.json`；移除未被代码消费的 `anchors_dir` 字段和 blue-gray 主题的 `anchors/` 软链接（参考锚点图统一由 `assets/style_anchors/` 提供，与配色解耦）；`load_theme()` 路径同步调整。
- 移除 `assets/style_anchors/`（12 张参考锚点图，11M）和 `assets/style_anchor_manifest.source.json`：经核实脚本从不读取这些图（构图家族已全部抽象为文字描述——隐喻库、`reference_family`、prompt 模板里的 `Composition family:` 文字），生图时也不再上传图片给模型，故删除以减小体积；SKILL.md、references/、scripts 中对 `target_gallery_core`/`style_anchors` 的路径引用全部改为通用文字表述（"构图家族"/"composition families"）。`assets/` 现仅保留 `outline_sample.json`。

### 待办事项

- 后续可为 `ink-black`、`terracotta` 主题补配套参考锚点图（当前复用 blue-gray 参考图）。
- 后续可用 git subtree 发布到独立 `.skill.git` 仓库（参考 `subtree-publish` skill）。

## [1.0.6] - 2026-06-14

### 新增

- 新增 `scripts/compress_images.py`，用于将 ImageGen 生成的文章配图原地压缩后再交付。

### 改进

- 将默认交付流程补充为“内置生图后压缩”：每张图硬上限低于 `500KB`，并尽量压到 `200KB` 以下，减少图床空间占用。
- 在 `SKILL.md` 中新增默认压缩命令、`pngquant` / `imagemagick` 依赖说明和输出检查项。

## [1.0.5] - 2026-06-14

### 改进

- 根据“异质关联/草创生态”文章配图总览反馈，新增成组配图的构图审计规则，避免多张图重复成“左侧输入 - 中间收束/滤波/闸门 - 右侧输出”。
- 将 `left_to_right_transform`、`funnel`、`filter`、`threshold`、`channel`、`pipeline`、`output bands`、`endpoint capsules` 归为同一类“收束输出版式”，长文中限量使用且不得连续出现。
- 扩展非线性构图家族：`Orbit / ring table`、`Map / compass field`、`Balance / tension frame`、`Scaffold / temporary frame`、`Seed / rare signal`。
- 调整 `balanced` 档脚本补充语，降低 `funnel outputs` 和 `thick connector bands` 的默认权重，增加 orbit、map、balance、scaffold、modular grid、rare-signal 等版式。
- 在 `config/style.json` 中新增 `layout_diversity_rule`，方便后续协作者直接看到布局多样性约束。

## [1.0.4] - 2026-06-02

### 改进

- 将默认生图路线进一步收紧为 ImageGen/Codex/ChatGPT 内置生图：`--mode codex` 生成队列后必须调用内置生图工具产出真实 PNG。
- 明确默认不运行 `--mode local`，不生成 `local_preview/`，不把本地预览纳入默认交付。
- 将 `local` 降级为显式诊断工具：只有用户明确要求构图草图、占位预览或本地预览检查时才使用，并必须标注为草图。
- 更新 `references/builtin_image_generation_workflow.md` 和 `scripts/batch_article_images.py` 帮助文案，避免协作者误把本地预览当默认步骤。

## [1.0.3] - 2026-06-02

### 改进

- 明确区分 ImageGen/内置生图真实成片与本地构图预览：用户要求“测试效果”“生成效果给我看”时，必须实际调用 ImageGen，不能只生成 `local_preview`。
- 新增 `archive/20260602_imagegen_strength_probe/`，保存 `reference_card`、`balanced`、`high_abstract` 三档真实 ImageGen 样图和对照板。
- 根据真实 ImageGen 测试更新初步判断：`balanced` 作为默认档最稳，`reference_card` 可解释但易文档化，`high_abstract` 适合少量概念图但不宜连续使用。

## [1.0.2] - 2026-06-02

### 改进

- 收紧顶层 `Archive/` 归档机制：退役旧 Skill 不再保留 `SKILL.md` 入口，归档说明改为 `ARCHIVE_NOTICE.md`，原始内容保留在 `ARCHIVED_SKILL.md`。
- 更新 `Archive/README.md` 和主 Skill 归档说明，明确文章配图唯一入口继续是 `handdrawn-article-illustrator`。

## [1.0.1] - 2026-06-02

### 新增

- 新增 `abstraction_strength` 抽象强度配置，支持 `reference_card`、`balanced`、`high_abstract` 三档。
- 支持在 `config/style.json`、outline 的 `style.abstraction_strength` 或单张 `illustrations[].abstraction_strength` 中调节抽象程度。
- 新增归档机制说明：顶层 `Archive/` 存放退役旧 Skill，本 Skill 内部 `archive/` 存放测试轮次和样图。
- 新增 `archive/20260602_abstraction_strength_article_probe/`，用真实文章对三档抽象强度生成测试队列和本地构图预览。

### 改进

- 将 Skill 名称从 `handdrawn-article-illustration` 调整为 `handdrawn-article-illustrator`，中文标题改为“手绘文章配图”，让触发入口更像一个可调用的配图工具。
- 将内置生图队列中原本偏高抽象的补充提示拆成可切换档位：默认 `balanced`，需要更接近前序参考图时用 `reference_card`，需要最近测试中更高抽象机制感时用 `high_abstract`。
- 更新样例 outline，示范全篇默认 `balanced`，并在单张图上混用 `reference_card` 与 `high_abstract`。
- 将旧 `claude-blog-wechat-illustration` 与 `claude-style-illustration` 移入顶层 `Archive/`，避免继续作为配图触发入口。

## [1.0.0] - 2026-06-01

### 新增

- 新建合并后的主 Skill：`handdrawn-article-illustration`（手绘风格配图），用于替代 `claude-blog-wechat-illustration` 与 `claude-style-illustration` 两条趋同路线。
- 内置旧 `claude-style-illustration` 的 12 张 `target_gallery_core` 参考锚点到 `assets/style_anchors/target_gallery_core/`，新 Skill 不再依赖旧目录读取参考图。

### 改进

- 默认正式路线统一为 Codex/ChatGPT 内置图片生成能力：Agent 先理解文章、写 `reader_takeaway_zh`、`Image Brief`、`reference_family` 和 `final_prompt_en`，再调用内置生图。
- 外部 API 路线降级为显式实验：不再默认调教或调用 SiliconFlow、MiniMax、Qwen 等外部图片 API。
- 名称和提示词从 Claude 绑定改为中性的“手绘风格配图”：保留对象卡片、粗黑墨线、蓝灰重点色、浅底/反转底和参考构图家族，但不要求绑定具体品牌。

### 文档完善

- 增加 `assets/style_anchors/README.md`，说明 12 张参考锚点的用途和边界。
- 将生产说明、脚本 prompt 和参考文档进一步中性化，主参考文档改为 `references/handdrawn_style_architecture.md`。

## [0.1.15] - 2026-06-01

### 改进

- 根据用户反馈将默认方向从第 4-5 轮“轻微异样机制感”收回，重新以旧 `claude-style-illustration` 的 `target_gallery_core` 示例图为主要风格锚点。
- 强化“文章理解优先”原则：每张图必须先写清 `reader_takeaway_zh`，说明它帮助读者理解什么；如果一句话说不清，就回到参考锚点重写。
- 将 `sealed chamber`、`aperture`、`offset sieve`、`oracle frame`、`divided capsule archive` 等探索意象降级为边界测试，不作为默认构图家族。
- Prompt 模板新增 `article-serving metaphor`、`old claude-style-illustration reference families` 和 `no cryptic surreal mechanism` 等约束，避免为了多样性牺牲手绘感和可理解性。

### 文档完善

- `references/builtin_image_generation_workflow.md` 新增 `reader_takeaway_zh` 和 `reference_family` 字段，明确先理解文章，再选择参考构图家族。
- 追加第 6 轮参考锚点回归测试记录：8 张样图确认旧示例图家族更适合作为默认方向；同时补充 `Sparse chain` prompt 需明确“小圆角块沿细线推进”，避免过度抽象化。

## [0.1.14] - 2026-06-01

### 改进

- 将公众号文章默认配图密度升级为更适合长文阅读节奏的高密度方案：短文 6-8 张正文图，中长文 12-16 张正文图，长文、案例复盘或产品复盘默认 18-24 张正文图。
- 明确长文按每个二级标题或重要三级标题 2-3 张图规划，并以约每 250-450 个中文字符 1 张图作为密度参考。
- 新增构图家族轮换策略，参考旧 `claude-style-illustration` 的 `target_gallery_core`：链路、容器、蓝底轨道、云团漏斗、放射网络、档案堆叠、嵌套框、流程到网络、文件夹归档、模块拼接等家族交替使用。
- 规定每 6 张正文图至少使用 4 个不同构图家族，同一章节内的 2-3 张图必须避免同构图重复。
- 在内置生图流程文档中补充 `Composition family` prompt 写法，要求先确定构图家族，再把章节语义转成视觉命题。
- 根据三轮测试样图补充反向约束：禁止箭头、植物枝叶、边角装饰和蓝底暗角/渐变，避免模型把“关系”和“自然手绘”误解为 UI 流程或装饰插画。
- 根据第 4-5 轮测试，将“安静但略微异样的抽象机制感”固化为可用方向：优先用 sealed chamber、aperture、offset sieve、divided capsule archive 等结构表达，但明确排除脸、眼睛、嘴、身体部位、恐怖或神秘符号。

### 技术优化

- 新增密度与多样性测试目录 `archive/20260601_density_diversity_probe/`，用于多轮小样测试、参考图库对照和后续人工 A/B；目前共保存 31 张内置生图测试样图和多张总览板。

## [0.1.13] - 2026-06-01

### 改进

- 根据 Codex/ChatGPT 内置生图多轮小样，将默认抽象语法从“文档卡片/角色卡片/权限节点”进一步调整为“无名抽象机制”：soft shell、slot、hinge、vessel、organic plume、capsule、hollow endpoint 和 thick connector band。
- `batch_article_images.py` 的 Codex 队列 prompt 新增内置模型专用约束：将 roles、permissions、policies、tools、files 和 workflows 转译成抽象形体，避免文档卡片和 UI 面板直译。
- `network` 隐喻从治理节点/角色卡片改为抽象 boundary mechanism，减少人像、勾选、星标、铅笔等图标触发。
- `references/builtin_image_generation_workflow.md` 新增 Codex 内置生图抽象度调校记录，保留 2026-06-01 五张小样的经验结论。
- 强化重点色节奏规则：长文配图应以米白底 + 蓝灰局部重点色为主，并穿插少数蓝灰底 + 米白主体的反转图；10-14 张正文图默认安排 2-4 张反转图。

## [0.1.12] - 2026-05-31

### 新增

- 新增 `--mode codex` 生图来源，用于 Codex/ChatGPT 内置图片生成路线：脚本生成 `codex_generation_queue.json` 和 `codex_generation_queue.md`，由 Agent 在对话里调用内置生图能力，不调用 SiliconFlow、MiniMax 或其它外部图片 API。
- 新增 `references/builtin_image_generation_workflow.md`，固化 `Image Brief` 字段、内置生图 prompt 写法和本地草图边界。

### 改进

- `SKILL.md` 将默认正式路线改为 Built-in Image First：终图由 Codex/ChatGPT 内置图片生成能力完成，`local` 仅作为构图草图、占位预览或 API skeleton。
- `batch_article_images.py` 默认模式从 `local` 调整为 `codex`，避免协作者误把本地渲染器当成正式生图来源。
- `generate_prompts.py` 支持 `chapter_claim_en`、`visual_thesis_en`、`main_relation_en`、`support_structure_en` 和 `final_prompt_en`，优先保留 Agent 写好的最终视觉 prompt。
- 根据 Codex 内置生图小样，进一步禁止 checkmark、人像、星标、铅笔、工具等语义图标，避免“权限/角色”被画成 UI 图标。

## [0.1.11] - 2026-05-31

### 改进

- 根据真实长文配图反馈，扩大 Local First 本地渲染的抽象隐喻库，减少“方框、圆圈、连线”重复感。
- 新增关系型隐喻建议：漏斗、棱镜、迷宫、飞轮、脚手架、广播扩散、指南针地图、样品托盘和天平。
- 更新 `SKILL.md` 隐喻库，明确长文同组配图应在压缩、分发、筛选、判断、路径、沉淀、协作等关系之间轮换。

### 技术优化

- `render_local_images.py` 新增多个确定性本地模板：`funnel`、`broadcast`、`prism`、`maze`、`flywheel`、`scaffold`、`compass_map`、`sample_tray`、`balance`。
- `generate_prompts.py` 同步扩展 `METAPHORS`，确保 prompt、构图契约和本地渲染模板保持一致。

## [0.1.10] - 2026-05-31

### 改进

- 将外部 API 路线进一步收紧为显式实验功能：文档中的 `t2i`、`guided-edit` 和 `edit` 示例均要求加入 `--allow-api`。
- 明确默认交付无需配置 API Key，只有用户要求 API 实验时才读取 `SILICONFLOW_AK`。

### 技术优化

- 为批量入口加入 API 防误触发保护：非 `local` 模式必须显式传入 `--allow-api` 才会调用外部图片接口。
- 更新 API 参考和脚本帮助文案，明确 `--prompts-only` 只生成提示词，不渲染图片也不调用图片接口。

## [0.1.9] - 2026-05-30

### 改进

- 将 Skill 的正式交付路线明确收敛为 Local First：默认只使用本地结构渲染，不再主动调用外部图片 API 作为增强步骤。
- 将 `guided-edit`、`t2i` 和 `edit` 统一降级为“用户明确要求时的实验/对照路线”，避免外部模型随机性污染默认结果。
- 更新输出检查规则：默认交付应检查是否未主动调用外部 API；API 结果只有在用户显式要求时才进入候选评估。

### 技术优化

- 关闭“替换 API Key 后继续默认实测”的后续待办，将 API 相关 QA 改为仅在用户再次明确要求 API 实验时推进。

## [0.1.8] - 2026-05-30

### 改进

- 基于 Folia 文章完整 `guided-edit` API 实测，继续收紧颜色约束：禁止旧纸、棕色、橙色、水彩纸纹和非配置色块。
- `guided-edit` prompt 增加“空白矩形、卡片、纸张、节点、面板只能保持米白或配置蓝灰”的明确规则。
- 本地构图草图的浏览器窗口不再绘制三颗圆点，避免编辑模型自动联想到红黄绿窗口按钮并引入橙色。

### 技术优化

- 记录 `guided-edit` 的真实边界：它能较好保住布局和主体，但仍需颜色 QA，不能无筛选替代 Local First。

## [0.1.7] - 2026-05-30

### 新增

- 新增 API 构图锁定路线 `--mode guided-edit`：先生成本地构图草图，再将草图作为输入图交给编辑模型做风格化。
- `generate_prompts.py` 为每张图输出 `composition_spec`，明确隐喻、背景模式、主体尺度、重点色和构图锁定规则。

### 改进

- API 路线从“直接文生图自由发挥”调整为“语义计划 + 构图契约 + 本地 skeleton + 编辑模型”的受控流程。
- `guided-edit` prompt 明确要求保留输入图的画幅、对象数量、位置、主体大小、背景模式和重点色位置，只做 Claude Blog 风格化。

## [0.1.6] - 2026-05-29

### 改进

- 优化本地结构渲染器的主体尺度计算：按 `browser_window`、`magnifier`、`folder`、`radar` 等隐喻模板单独计算缩放，避免 Z-Image 宽画幅尺寸下主体偏小。
- 加粗近黑墨线并将粗细变化收敛到端点、转角和结构锚点，减少机械细线感，同时避免随机墨块噪声。
- 为 `radar` 隐喻增加贴近主体的左右辅助块，扩大视觉占比，避免圆形主体在横图中显得过小。
- 修正 `overview_board.png` 预览方式，保持原图宽高比例，不再把宽图拉伸到固定缩略图比例。

### 技术优化

- 继续确认 local-first 是默认交付路线；API 模型输出作为候选探索，不直接替代本地结构渲染。

## [0.1.5] - 2026-05-29

### 新增

- 新增 `scripts/render_local_images.py`，将此前效果更接近目标的本地预览能力固化为确定性结构渲染器。

### 改进

- 批量入口 `batch_article_images.py` 新增 `--mode local`，并将默认模式改为 `local`。
- 默认交付路线调整为 local-first：稳定保证无文字、主体占比、固定蓝灰、手绘墨线和系列一致性；API 生图仅作为候选探索。
- 修复 edit 模式默认 `base-size=auto` 时无法创建底图的问题。

## [0.1.4] - 2026-05-29

### 改进

- 根据模型矩阵测试结果修正 prompt 泄字问题：不再把文章标题、章节标题和关键词原样写入图片模型 prompt。
- 新增 visual-only 文本改写逻辑，将 `HTML table`、`Markdown`、产品名等高风险词改写成抽象视觉概念。
- 增加 Z-Image、Qwen t2i、Qwen edit、MiniMax 的模型矩阵测试目录，用于比较当前风格任务的真实模型表现。
- 默认文生图主路从 `Qwen/Qwen-Image` 调整为 `Tongyi-MAI/Z-Image-Turbo`；`auto` 尺寸在 Z-Image 下使用 `2048x872`，Qwen 对照路径使用 `1664x928`。

## [0.1.3] - 2026-05-29

### 改进

- 根据用户反馈继续优化手绘线条自然度：将线条语言从“校准矢量轮廓”调整为“单遍手工描摹的填充墨线”。
- 更新默认 `line_style`，强调起笔、收笔、转角压痕、轻微不平行和内部细线的手工放置感。
- 强化反向提示，排除机械矢量图标、尺规直线、完美平行边和算法化均匀曲线。
- 增加 Folia 自然手绘墨线测试样张目录 `archive/20260529_folia_natural_ink_probe/` 和放大预览目录 `archive/20260529_folia_natural_ink_large_probe/`。

## [0.1.2] - 2026-05-29

### 改进

- 根据用户反馈放大默认主体占比，避免正文横图在公众号里显得像小图标。
- 新增 `cover_subject_scale`、`inline_subject_scale`、`card_subject_scale` 配置项，允许调整首图、正文横图和方形卡片的主体大小。
- 更新 prompt 模板，明确“适度留白但不要过空”，并将“小主体、过度留白”加入反向提示。
- 增加 Folia 主体放大测试样张目录 `archive/20260529_folia_large_subject_probe/`，用于观察更适合公众号正文的主体尺度。

## [0.1.1] - 2026-05-29

### 改进

- 根据用户反馈进一步收敛墨线随机感：将“粗细不均”定义为结构锚点上的笔压变化，而不是整圈轮廓随机起伏。
- 更新 prompt 模板和默认配置，要求每个主物件只在转角、端点、重叠、接缝等少数位置出现 2-4 个加重锚点。
- 强化反向提示，排除随机墨块、整边噪声、手抖线和过度粗糙轮廓。

## [0.1.0] - 2026-05-29

### 新增

- 新建 `claude-blog-wechat-illustration` Skill，专门为公众号文章生成 Claude Blog 架构风格配图。
- 支持首图、正文横图和方形卡片三类输出。
- 提供 Claude Blog 风格架构参考、公众号文章 outline 样例和批量 prompt 生成脚本。
- 增加 `config/style.json`，集中配置固定重点色、背景模式和墨线风格。

### 改进

- 将公众号长文默认配图密度调整为“首图 + 10-14 张正文横图”，避免正文配图过少。
- 新增配图密度规则：短文 6-8 张正文图，中长文 10-12 张，长文/产品复盘文 12-16 张。
- 将 Skill 迁移到 `private-skills/claude-blog-wechat-illustration`，按私有 Skill 管理。
- 将重点色策略改为固定蓝灰 `#435C68`，支持白底局部强调和蓝底反转两种模式。
- 强化 Claude Blog 墨线要求：从统一圆润描边改为粗细不均、边缘不规则的填充墨块轮廓。
- 收敛墨线随机感：改为稳定轮廓、局部压力变化和受控手工边缘，避免随机抖动草稿线。

### 技术优化

- 增加 `scripts/generate_prompts.py`，支持 `illustrations[]` 新结构、palette 轮换和 cover/inline/card 三类目标。
- 增加 SiliconFlow 批量出图脚本，默认使用 `python3` 与当前解释器调用子脚本。
- 增加脚本依赖友好提示；缺少 `requests` 或 `pillow` 时给出安装命令。
- 样例大纲增加 `title_en`、`concept_en` 字段，确保图片 prompt 优先使用英文语义。
- 通过语法检查、样例 prompt 生成和 `--prompts-only` 批量入口验证。
- 增加 Folia 真实文章测试样张目录 `archive/20260529_folia_probe/`，用于观察首图、正文横图和 palette 轮换效果。
- 增加 Folia 密集版测试样张目录 `archive/20260529_folia_dense_probe/`，包含 1 张首图和 12 张正文横图。
- 增加 Folia 墨线加强测试样张目录 `archive/20260529_folia_ink_probe/`，用于观察固定蓝灰重点色和粗细不均墨线效果。
- 增加 Folia 受控墨线测试样张目录 `archive/20260529_folia_ink_refined_probe/`，用于观察更接近 Claude Blog 的稳定手工轮廓。

### 待办事项

- 用真实公众号文章生成样图，进一步微调隐喻库与配色节奏。
