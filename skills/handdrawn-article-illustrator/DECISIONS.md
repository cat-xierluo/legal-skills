# Decisions

## 2026-07-23

### 配色解耦为主题包机制

**背景**：原 skill 的蓝灰重点色（`#435C68`）、纸面色、墨线色是作者个人定制，硬编码在 SKILL.md 的 Prompt 模板、references 文档和 `generate_prompts.py` 的 `DEFAULT_STYLE` 中。这导致其他律所或作者无法复用同一套构图与流程——要么忍受别人的品牌色，要么手动改多处文件，容易遗漏。

**方案**：引入主题包（Theme Pack）机制——每个主题包 = 一个 `theme.json`（定义 colors）+ 可选 `anchors/`（参考锚点图目录）。配色不再写死，而是由 `config/style.json` 的 `active_theme` 指向当前主题包动态注入。

**决策**：

1. 新增 `themes/` 目录，内置三套预设：`blue-gray`（默认，原作者主题）、`ink-black`（中性通用）、`terracotta`（暖调示例），让"多预设"成立而非单一默认。
2. 配置加载链优先级：`outline.style.<key>` > `config.overrides` > `theme.json.colors` > `DEFAULT_STYLE`；`--theme` 命令行参数最高。
3. `config/style.json` 从"色值仓库"改为"激活指针 + 覆盖层"：`active_theme` 指向主题包，`overrides` 允许不改主题包就微调单值。
4. `DEFAULT_STYLE` 的颜色字段移除，改为中性兜底 `FALLBACK_THEME_COLORS`，主题包缺失时优雅回退不崩溃。
5. 去除所有文档与脚本中的蓝灰硬编码：Prompt 模板改用 `{accent_color}` 占位符并明确"Agent 必须从主题包读取实际色值"；隐喻库、架构文档、构图家族名（`Blue rail blocks` → `Accent rail blocks`）全部中性化。
6. `inverted` 模式与颜色解耦：明确反转底图用当前主题重点色，不一定是蓝灰。

**理由**：主题包让"换色"从"改 N 处文件"变成"改 1 个 active_theme 或传 1 个 --theme"，降低出错概率；多预设让用户直观看到可定制性；向后兼容（老的 outline `style.accent_color` 字段仍生效，只是底层默认从主题包来）保证老用户无感知。

### 迁移到 legal-skills 公开发布

**背景**：原 skill 在 `private-skills/`（私有仓库），主题包解耦后具备了公开发布条件。

**方案**：复制（非 symlink，否则被 .gitignore 忽略）到 `legal-skills/skills/handdrawn-article-illustrator/`，用 MIT 许可证（属于"通用工具类"），同步更新根 README 技能列表与 marketplace.json。

**决策**：

1. 复制时排除 `archive/`（158M 测试轮次）、`__pycache__/`、`.DS_Store`。
2. 新增局部 `.gitignore` 覆盖运行产物（`local_preview/`、`prompts.json`、`composition_guides/`、`secrets.env`）和敏感配置。
3. `private-skills/` 原件保留（作者个人定制版本仍可用），公开发布版是独立副本。
4. 暂不做 git subtree 独立仓库发布，留作后续（参考 `subtree-publish` skill）。

## 2026-06-14

### 默认压缩 ImageGen 交付图

背景：用户反馈内置 ImageGen 生成的文章配图文件偏大，上传图床会占用过多空间。公众号文章配图更重视阅读展示和统一风格，不需要长期保留超大 PNG 原图作为默认交付物。

决策：

- 新增 `scripts/compress_images.py`，作为手绘文章配图的默认交付后处理步骤。
- 默认原地覆盖生成图，目标是每张尽量低于 `200KB`，硬上限低于 `500KB`。
- 优先使用 `pngquant` 保持 PNG 工作流；仅在普通压缩无法达到硬上限时，才通过 `--allow-resize` 启用缩放兜底。
- 除非用户明确要求保留原始大图，否则生成到文章目录后的图片直接走压缩流程。

影响：

- 后续使用本 Skill 给文章配图时，ImageGen 生成终图后必须运行压缩脚本并检查文件大小。
- 用户上传图床时默认拿到的是压缩后的交付图，而不是未经处理的大 PNG。

## 2026-06-02

### 限制左中右收束版式的过度重复

背景：用户指出最近为“异质关联/草创生态”文章生成的总览图中，`00/01`、`05`、`07/08/09` 等多张图都呈现类似的“左侧输入 - 中间收束/滤波/闸门 - 右侧输出”结构，导致整组布局多样性不足。复核 Skill 后发现，虽然文档列出了多个构图家族，但默认 prompt 和 `balanced` 档脚本补充语仍高频使用 `input / output / funnel / filter / threshold / channel / endpoint` 这组安全词，容易把不同语义压回横向转化机制。

决策：

- 将 `left_to_right_transform` 识别为一种需要限量的版式，而不是默认安全构图。
- 每 10-14 张正文图中，左中右转化/收束版式最多 2-3 张，且不得相邻。
- 每 5 张正文图至少安排 2 张非线性版式，例如 `radial_orbit`、`stack_archive`、`map_field`、`balance_tension`、`scaffold_frame`、`modular_grid` 或 `single_rare_signal`。
- `funnel/filter/threshold/channel/pipeline/output bands/endpoint capsules` 统一视为同一类“收束输出版式”，只在章节关系确实是压缩、筛选或转化时使用。
- 更新 `SKILL.md`、`references/builtin_image_generation_workflow.md`、`config/style.json` 和 `scripts/generate_prompts.py`，让默认 `balanced` 档更多使用 orbit、map、balance、scaffold、rare-signal 等非线性构图。

影响：

- 后续生成长文配图时，必须先做整组构图审计，再调用 ImageGen。
- 如果总览图里 4 张以上出现相似的左宽右窄、左散右整或左输入右输出轮廓，应视为跑偏并重写 prompt。

### 默认禁用本地预览路线

背景：用户进一步确认，后续默认生图必须使用 ImageGen/内置图片生成能力，不要使用任何 `local_preview` 或 Python 本地预览作为默认生图步骤。

决策：

- 默认生图路线统一为 ImageGen/Codex/ChatGPT 内置生图。
- `--mode codex` 只负责生成 ImageGen/内置生图队列；队列之后必须由 Agent 调用 ImageGen/内置生图工具产出真实 PNG。
- 默认不运行 `--mode local`，不生成 `local_preview/`，也不把本地预览纳入默认交付。
- 只有用户明确要求“构图草图”“占位预览”“本地预览检查”时，才允许运行 `--mode local`，且输出必须标注为诊断草图。

影响：

- `local` 不再是默认流程的辅助步骤，而是显式诊断工具。
- 后续任何真实效果测试都以 ImageGen/内置生图输出为准。

### 区分 ImageGen 成片测试与本地预览

背景：用户指出此前归档的“三档测试”主要是 `local_preview` 和生图队列，并没有真正使用 ImageGen/内置图片生成模型，因此不能代表最终效果。

决策：

- 后续用户要求“测试效果”“生成效果给我看”“跑几轮看看”时，必须调用 ImageGen/内置图片生成能力生成真实样图。
- `--mode codex` 生成的队列只是给 Agent 调用 ImageGen 的任务清单，不等于已经完成出图。
- `--mode local` 和 `local_preview/` 只用于检查图位、主体占比、蓝底节奏和构图安全区，不能作为终图质量判断。
- 新增 `archive/20260602_imagegen_strength_probe/`，保存 `reference_card`、`balanced`、`high_abstract` 三档真实 ImageGen 输出。

影响：

- 当前三档初步判断以真实 ImageGen 图为准：`balanced` 最适合作为默认档；`reference_card` 更稳但可能偏文档化；`high_abstract` 抽象感强但不宜连续大量使用。

### 增加抽象强度档位

背景：用户希望同一个手绘配图 Skill 内部同时保留两类方向：一类是最近测试中抽象程度更高的机制感，另一类是更接近前序参考图、可理解性更强的手绘对象卡片风格。两者不应拆成两个 Skill，而应作为同一 Skill 内的可调强度。

决策：

- 增加 `abstraction_strength` 配置，支持 `reference_card`、`balanced`、`high_abstract` 三档。
- 默认使用 `balanced`，避免新用户误入过度抽象或过度直译。
- `reference_card` 用于更接近内置参考锚点的可解释构图，优先服务文章理解。
- `high_abstract` 保留最近测试中的高抽象机制语法，但必须以 `reader_takeaway_zh` 和清晰关系为前提。
- 脚本生成 `prompts.json` 和 `codex_generation_queue` 时同步写入抽象强度与对应的内置生图补充提示。

影响：

- 同一篇长文可以混用档位：关键章节用 `reference_card` 保稳定，少数概念章节用 `high_abstract` 提升变化。
- 后续调风格优先改 `config/style.json` 或 outline 字段，不需要复制新 Skill。

### 重命名为手绘文章配图

背景：用户确认这是后续配图的唯一 Skill，同时认为 `handdrawn-article-illustration` 不够直观。当前目录名更像产物名，不像一个可调用工具。

决策：

- 将 Skill `name` 和目录调整为 `handdrawn-article-illustrator`。
- 中文标题改为“手绘文章配图”，保留“手绘风格配图 / 手绘配图 / 公众号文章配图”等触发词在 description 中。
- 旧名称只在历史记录中保留，用于追溯迁移过程。

影响：

- 后续所有公众号文章配图、手绘配图和正文横图任务，都使用 `handdrawn-article-illustrator`。

### 统一归档机制

背景：用户确认本 Skill 是唯一配图入口，并询问旧 Skill 是否已归档、能否移入 Archive 文件夹，以及当前 Skill 是否有 archive 机制。

决策：

- 顶层 `Archive/` 用于退役旧 Skill；已将 `claude-blog-wechat-illustration` 与 `claude-style-illustration` 移入该目录。
- 归档目录不保留可被扫描为入口的 `SKILL.md`；归档说明改用 `ARCHIVE_NOTICE.md`，原始技能说明保存在 `ARCHIVED_SKILL.md`。
- `handdrawn-article-illustrator/archive/` 继续作为当前 Skill 的测试轮次、样图、prompt 队列和实验报告归档目录。
- 新测试目录统一使用 `YYYYMMDD_topic_probe/` 命名，并配套 `README.md` 记录输入、配置和观察。

影响：

- 后续不再通过旧 Claude 相关 Skill 承接文章配图任务。
- 新风格实验不新建 Skill，统一沉淀到当前 Skill 的配置、参考文档和内部 archive。
- 即使未来的 Skill 扫描器递归读取目录，`Archive/` 内的旧配图 Skill 也不会再因为 `SKILL.md` 被误触发。

## 2026-06-01

### 合并为手绘风格配图主 Skill

背景：用户判断 `claude-blog-wechat-illustration` 与 `claude-style-illustration` 已经趋同，而且外部 API 图片生成长期存在不可控问题。与其继续调教外部 API，不如直接让 Codex/ChatGPT 或其它更强的内置图片生成能力完成终图。同时，技能名称不必继续绑定 Claude。

决策：

- 新建 `handdrawn-article-illustration` 作为主 Skill，后续重命名为 `handdrawn-article-illustrator`，中文标题为“手绘文章配图”。
- 继承 `claude-blog-wechat-illustration` 的 Built-in Image First 路线、配图密度、`reader_takeaway_zh`、参考构图家族轮换和固定蓝灰重点色配置。
- 继承 `claude-style-illustration` 的 12 张 `target_gallery_core` 风格锚点，并复制到新 Skill 的 `assets/style_anchors/target_gallery_core/`。
- 不再把 SiliconFlow、MiniMax、Qwen 等外部 API 作为默认路线；外部 API 仅在用户明确要求模型对照或 API 实验时使用。
- 生产说明、脚本 prompt 和参考文档统一改为“手绘风格配图 / 手绘对象卡片”表述；历史来源只在记录和归档说明中保留。
- 旧 `claude-blog-wechat-illustration` 与 `claude-style-illustration` 改为归档跳转入口，保留 `ARCHIVED_SKILL.md` 用于追溯历史。

影响：

- 后续用户说“手绘配图”“手绘风格配图”“公众号文章配图”“给文章配图”时，应使用 `handdrawn-article-illustrator`。
- 旧 Skill 不再承接新任务，避免两个 Skill 同时触发或 API 路线误导。

### 回归参考图锚点与文章理解优先

背景：用户反馈第 4-5 轮继续测试后已经跑偏，脱离了手绘风，意象也不够好理解。用户希望仍以旧 `claude-style-illustration` 中提供的示例图为基础，配图更多服务于理解文章。

决策：

- 默认方向重新回到旧 `claude-style-illustration` 的 `target_gallery_core` 示例图锚点。
- 第 4-5 轮的 `sealed chamber`、`aperture`、`offset sieve`、`oracle frame`、`divided capsule archive` 等意象只保留为探索记录，不作为默认构图家族。
- 每张图必须先写 `reader_takeaway_zh`：用一句中文说明这张图帮助读者理解什么。
- 只有当 `reader_takeaway_zh` 明确、且构图能落回旧参考图家族时，才继续写英文 prompt。
- 多样性从参考图家族内部获得，不再主动追求“轻微异样感”、神秘感或难懂的新机制。

影响：

- 后续生成长文配图时，Agent 应先做文章语义计划，再选择参考构图家族；不能先想一个有趣画面再硬套文章段落。
- `round_04` 和 `round_05` 测试图可作为“跑偏边界”的参考，不作为生产默认样式。

验证：

- 第 6 轮回归测试使用 8 个旧参考家族生成样图：sparse chain、cloud funnel output、folder archive、nested frame、blue rail blocks、workflow book / vessel、radial network、module puzzle chain。
- `folder archive`、`cloud funnel output`、`nested frame`、`module puzzle chain`、`radial network` 和 `workflow book / vessel` 明显比第 4-5 轮更可理解，也更接近手绘对象卡片。
- `sparse chain` 仍需在 prompt 中明确“小圆角块沿细线推进”，否则模型可能简化成抽象插槽物。
- 结论：当前生产默认应以第 6 轮为方向，而不是第 4-5 轮。

### 长文配图密度与构图家族轮换

背景：用户反馈当前长文配图密度接近目标，应固化为默认策略；同时指出抽象风格仍过于固定，主要重复为方框、圆圈和连线。旧 `claude-style-illustration` 的参考图库中有更多构图变化，可以作为新 Skill 的构图家族来源。

决策：

- 公众号文章默认不再按“每章 1 张分隔图”规划，而按阅读节奏做高密度正文图。
- 短文默认首图 + 6-8 张正文图；中长文默认首图 + 12-16 张正文图；长文、案例复盘和产品复盘默认首图 + 18-24 张正文图。
- 每个二级标题或重要三级标题默认 2-3 张图，大致每 250-450 个中文字符 1 张图。
- 从旧 `claude-style-illustration` 的 `target_gallery_core` 抽取构图家族：链路、容器/书页、蓝底轨道、云团漏斗、放射网络、活动链块、档案堆叠、嵌套框、流程到网络、文件夹归档和模块拼接。
- 每 6 张正文图至少使用 4 个不同构图家族；同一章节的 2-3 张图必须使用不同构图家族。
- 多样性来自构图和关系，不通过增加颜色、文字、人物、UI 图标或复杂背景制造差异。

影响：

- 后续为长文生成配图时，应先建立全篇图位表和构图家族表，再逐张写 `Image Brief` 与 `final_prompt_en`。
- `Composition family` 成为内置生图 prompt 的显式字段，帮助 Agent 在生成多张图时主动避免同构图重复。

验证：

- 在 `archive/20260601_density_diversity_probe/` 生成 3 轮共 19 张 Codex/ChatGPT 内置生图小样。
- 第一轮证明显式构图家族能打开多样性，但 `radial network` 易出现箭头化倾向，`folder archive` 易出现植物枝叶装饰。
- 第二轮改用更抽象的 `shell / plume / vessel / tray / flywheel / bridge` 机制语言后，整体更接近目标，图标和装饰问题明显减少。
- 第三轮复合结构可用于正文图位，但 `process to network` 容易重复为输入块 + 输出端点，需要在真实文章中避免连续使用。
- 因此在模板和工作流中追加 `no arrows / no plants / no leaves / no decorative corner marks / no vignette` 等约束。

### 可控的轻微异样感（探索记录，后续已收回为非默认方向）

背景：用户认可新测试图开始形成自己的风格，甚至有一点轻微诡异感，并认为这种感觉可以接受。继续测试第 4-5 轮后确认，这种风格可以作为区别于普通扁平插画的方向，但必须被限制在“抽象机制”层面。

后续修订：用户进一步反馈这些意象已经偏离手绘风，也不够服务文章理解。因此本节仅作为探索记录保留；默认方向以“回归参考图锚点与文章理解优先”为准。

决策：

- 不再把“安静但略微异样”的抽象机制感作为默认目标。
- 封存容器、腔室、观察孔、偏移筛板、分隔胶囊、厚重铰链和嵌套框只作为边界测试记录。
- 不通过脸、眼睛、嘴、身体部位、恐怖符号、宗教神秘符号或装饰性图案制造异样感。
- 真实文章成组配图时，默认不使用轻微异样图；只有用户明确要求，且 `reader_takeaway_zh` 能说清楚，才可少量使用。

验证：

- `round_04` 中 `sealed_memory_vessel`、`divided_capsule_archive`、`offset_sieve_lattice` 方向可用，既有异样感又保持对象卡片风格。
- `round_04` 中 aperture / oracle frame 类结构有辨识度，但接近眼睛或黑洞感时需要继续加 `not a face / not an eye / not mystical` 约束。
- `round_05` 的长文图位模拟整体更稳定，适合与前几轮的 shell / plume / bridge / tray / flywheel 家族混排。

### 重点色与反转图节奏

背景：用户再次强调重点色应沿用旧思路：同一篇文章固定使用蓝灰重点色，可以是米白底 + 蓝灰重点色，也可以是蓝灰底 + 米白主体的颜色反转，并且一组配图里应有几张反转图。

决策：

- 保持 `#435C68` 为唯一重点色，不引入第二强调色。
- `paper` 模式作为主模式：暖米白底，蓝灰只放在语义枢纽、连接带、活动边、厚边或结构块上。
- `inverted` 模式作为节奏重音：整面蓝灰底，主体块面反转为暖米白，线条仍为近黑。
- 10-14 张正文图默认安排 2-4 张 `inverted`，优先放在关键转折、结论、系统边界、分发放大、人的判断等章节；首图默认不反转。
- 同一组图避免连续两张反转，防止节奏过重。

影响：

- 后续手工调用内置生图时，不能只生成一张蓝底图；长文应按组安排 2-4 张反转图。

### Codex 内置生图抽象度调校

背景：用户认可 Codex/ChatGPT 内置生图的手绘风格更好，但指出抽象程度仍与参考图不一致。复测 5 张样图后确认，问题主要不是线条，而是语义词触发直译：`role card / permission / governance / document` 会被画成文档卡片、人像、勾选、铅笔、星标或 UI 图标。

决策：

- 将内置生图默认语法从“角色卡片/权限卡片/文档节点”转向“无名抽象机制”。
- 推荐使用 `soft shell / slot / hinge / vessel / organic plume / capsule / hollow endpoint / thick blue-gray connector band`。
- `network` 隐喻改为抽象 boundary mechanism：大圆角 shell + 蓝灰 hinge band + 左侧松散 slab + 右侧 endpoint capsule。
- `batch_article_images.py` 的 Codex prompt 增加专用约束，把 roles、permissions、policies、tools、files、workflows 转译为抽象形体。

验证：

- 01 “literal icons” 出现人像、勾选、铅笔和星标，判定为失败模式。
- 02 “strict no icons” 去掉图标但仍偏文档/流程卡片。
- 03 “threshold band” 接近 Workflow 机制结构，但仍有文档卡片和小碎片。
- 04 “abstract slot” 抽象程度、页面利用率和无图标约束最好，是当前推荐语法。
- 05 “funnel object” 最接近用户早期漏斗参考，但应只用于压缩/筛选关系，避免所有章节都漏斗化。

影响：

- 后续 Agent 写 `final_prompt_en` 时，不应从主题名直接落到文档、角色、权限图标；应先转成抽象机制物件。

## 2026-05-31

### 纠正默认生图路线

背景：用户指出此前把 `Local First` 实现成 Python 本地渲染器是方向偏差；用户希望默认生图来源是 Codex/ChatGPT 本身的图片生成能力，而不是本地几何渲染或外部 API。

决策：

- 将 Skill 的正式路线改为 Built-in Image First：Agent 先理解文章、写 `Image Brief` 和最终英文视觉 prompt，再调用 Codex/ChatGPT 内置图片生成能力产出终图。
- `batch_article_images.py` 的默认模式改为 `codex`，只输出内置生图队列，不直接生成 PNG。
- `render_local_images.py` 保留，但降级为构图草图、占位预览、批量规划检查和 `guided-edit` skeleton，不再作为默认终稿来源。
- 外部 API 继续必须显式传入 `--allow-api`，不作为默认增强步骤。
- 新增 `references/builtin_image_generation_workflow.md`，把 `chapter_claim_en`、`visual_thesis_en`、`main_relation_en`、`support_structure_en` 和 `final_prompt_en` 固化为高质量内置生图入口。

影响：

- 默认交付不再声称“本地渲染结果就是正式图”；正式图需要由 Agent 调用宿主内置生图工具生成。
- 本地草图仍有价值，但只用于验证主体大小、构图安全区、隐喻重复和外部 API skeleton。

### 增加 Codex/ChatGPT 内置生图队列

背景：用户希望为该 Skill 增加一个不使用外部 API 的生图来源，即由 Codex/ChatGPT 自身的内置图片生成能力产出图片，而不是调用 SiliconFlow、MiniMax 或 Qwen API。

决策：

- 新增 `batch_article_images.py --mode codex`。
- 该模式仍先复用 `generate_prompts.py` 的文章语义、风格和构图契约编译能力。
- Python 脚本只输出 `codex_generation_queue.json` 和 `codex_generation_queue.md`，不直接生成 PNG。
- 原因是 Codex/ChatGPT 内置生图能力属于 Agent/宿主环境工具，不是当前 Python 进程可直接调用的本地模型，也不应伪装成普通 provider API。
- `codex` 模式不需要 `--allow-api`，也不读取 API Key；外部 API 模式继续必须显式传入 `--allow-api`。

影响：

- 三条路线边界更清晰：`codex` 为默认内置生图队列，`local` 为确定性本地构图草图，`t2i/edit/guided-edit` 为外部 API 实验。

### 内置生图小样后的图标禁用补强

背景：用样例首图 prompt 调用一次 Codex/ChatGPT 内置图片生成后，画面能按 Claude Blog 对象卡片方向生成，但“角色/权限”语义被模型翻译成了打勾、人像、铅笔、星标等熟悉 UI 图标。

决策：

- 在 `generate_prompts.py` 的默认 negative prompt 中加入 `checkmark / person icon / user avatar / star icon / pencil icon / tool icon / familiar symbol`。
- 将 `network` 隐喻改为“blank governance block + blank role cards + plain permission dots”，明确卡片和节点内部不要出现图标。
- 在 `batch_article_images.py` 的 Codex 队列 prompt 中追加硬约束：只允许 blank cards、dots、short strokes 和 abstract blocks。

影响：

- 内置生图仍可表达角色、权限和治理关系，但应通过空白对象关系表达，不通过常见 UI 图标表达。

## 2026-05-29

### 新建独立 Skill，不覆盖旧 claude-style-illustration

背景：用户要求保留旧 `claude-style-illustration`，另建一个基于 Claude Blog 当前架构的公众号配图 Skill。

决策：

- 新 Skill 命名为 `claude-blog-wechat-illustration`，放在 `others/05-卡片配图/` 下，与旧 Skill 并列。
- 旧 Skill 不再承载本次重写，继续保留“极简手绘 + 单点陶土橙 + 4 张章节分隔图”的旧路线。
- 新 Skill 采用 Claude Blog 页面/文章页抽取出的 hero/card/inline 架构，并保留旧 Skill 的尺寸策略：`1664x928` 生成，公众号首图 `2400x1024` 导出。
- 新 Skill 明确禁止复制 Claude 官网现成插画资产，仅提取色彩、构图、线条和内容架构。

### 脚本边界

背景：该 Skill 需要支持两种使用方式：只输出图片提示词，以及通过 SiliconFlow 批量出图。

决策：

- `generate_prompts.py` 只做确定性的文章大纲到 prompt 转换，不调用外部模型。
- `batch_article_images.py` 作为批量入口，默认先生成 `prompts.json`，支持 `--prompts-only` 做无密钥验证。
- `siliconflow_generate.py` 只负责单次 API 调用和图片下载；API Key 从 `secrets.env` 或环境变量读取，不写入代码。

### Folia 文章样图测试

背景：用户提供文章 `Folia：一个律师为什么要重复造一个 Markdown 阅读器.md`，要求先跑一轮查看效果。

决策：

- 在 `archive/20260529_folia_probe/` 保存本次测试大纲、prompt、样图和总览图。
- SiliconFlow 接口返回 `Api key is invalid`，未生成 API 图片；不读取或暴露密钥内容。
- 为了先评估构图方向，使用本地降级渲染生成 1 张公众号首图和 5 张正文横图，按 `prompts.json` 的 Claude Blog palette 轮换配色。

### 提高公众号正文配图密度

背景：用户反馈 Folia 样图的正文横图偏少，公众号长文应在首图之外生成更多正文主图，类似这篇文章的体量应有 10 多张。

决策：

- 将 Skill 默认配图密度从 `1 张首图 + 3-6 张正文横图` 改为 `1 张首图 + 10-14 张正文横图`。
- 3000 字以上长文默认正文横图不少于 10 张；产品复盘、案例复盘、开发复盘类长文可到 12-16 张。
- 图位选择不只看二级标题，也覆盖三级标题、关键转折段、功能清单、技术选择、开发节奏和结论段。

### 迁移到 private-skills

背景：用户明确要求该 Skill 应放到 `private-skills` 当中。

决策：

- 将 Skill 从 `legal-skills/others/05-卡片配图/claude-blog-wechat-illustration` 迁移到 `private-skills/claude-blog-wechat-illustration`。
- 保留 Folia 测试目录，包含首轮 6 图样张和密集版 13 图样张，便于继续对比配图密度。
- 不更新公开 README 或 marketplace；当前仍按私有 Skill 管理。

### 固定蓝灰重点色与粗细不均墨线

背景：用户反馈本地样张抽象感可用，但手绘感不够明显，线条过于圆润；同时要求重点色规则与旧 Skill 一致，可以白底或蓝底，但重点色固定为同一个蓝灰色，并放入配置文件便于修改。

决策：

- 新增 `config/style.json`，默认 `accent_color` 为 `#435C68`。
- 提示词不再轮换 Claude Blog 多色 palette，而是固定使用 `#435C68`；通过 `paper` 与 `inverted` 背景模式制造节奏。
- 线条提示词改为 `near-black filled vector-like ink paths`、`pressure-variable thick contours`、`uneven hand-cut edges`，避免模型生成统一圆润描边。
- 重新生成 `archive/20260529_folia_ink_probe/`，用于观察蓝灰固定重点色和粗细不均墨线的效果。

### 收敛墨线随机感

背景：用户反馈“粗细不均的墨块轮廓”方向有优化，但上一版随机感过强，反而偏离真实手绘感觉。

决策：

- 将线条规则从强调 `uneven hand-cut edges` 调整为 `controlled pressure variation`。
- 正向 prompt 强调 `mostly stable silhouettes`、`confident clean contours`、`small handmade imperfections concentrated at corners and long edges`。
- 负面 prompt 增加 `jittery random wobble`、`chaotic deformation`、`scribbly sketch lines`、`noisy roughness`。
- 重新生成 `archive/20260529_folia_ink_refined_probe/`，作为“受控不规则”参考版本。

### 结构锚点式墨线校准

背景：用户进一步指出上一版“粗细不均的墨块轮廓”仍有过度随机的问题，导致不像真实手绘。

决策：

- 将线条规范从“边缘轻微手工不齐”进一步改为“稳定外形 + 结构锚点笔压变化”。
- 每个主物件只允许少量加重锚点，优先放在转角、端点、重叠、接缝位置。
- 长边保持连续和轻微收放，明确排除整圈随机墨块、边缘噪声和手抖线效果。

### 放大公众号正文图主体占比

背景：用户反馈校准版样图的主体内容占页面大小太小，公众号正文中可读性不足。

决策：

- 将默认构图从偏 Claude Blog 官网卡片的“小对象 + 大留白”改为更适合公众号的“大主体 + 适度留白”。
- 首图主体默认占画面宽度 60-72%，正文横图主体占画面宽度或视觉重量 55-68%，方形卡片主体占 68-76%。
- 在 `config/style.json` 暴露三类主体占比配置，方便后续按文章类型继续调整。

### 手绘线条自然度校准

背景：用户认可主体放大后的效果，但反馈手绘线条仍然不够自然。

决策：

- 降低 `vector-like`、`calibrated contour` 等容易导向机械矢量图标的提示词权重。
- 将线条风格改为 `Natural Claude Blog hand-inked contour style`，强调单遍手工描摹、起笔收笔、转角压痕和轻微不平行。
- 保留稳定轮廓和结构锚点原则，避免从“机械”滑向“随机抖动”。

### 模型矩阵测试与去文字化 prompt

背景：用户要求按旧 `claude-style-illustration` 内部模型配置逐个测试。第一轮使用当前 prompt 时，Z-Image 和 Qwen t2i 都把文章标题、章节标题或关键词画进图里。

决策：

- 按旧 Skill 配置测试四条路线：`Tongyi-MAI/Z-Image-Turbo`、`Qwen/Qwen-Image`、`Qwen/Qwen-Image-Edit-2509`、MiniMax `image-01`。
- 结论是：当前 Claude Blog 微信配图任务优先使用 Z-Image t2i；Qwen t2i 和 MiniMax 只作为对照；Qwen edit 可作为 skeleton fallback，但终稿感偏弱。
- 默认模型同步调整为 `Tongyi-MAI/Z-Image-Turbo`，`auto` 尺寸在 Z-Image 下使用 `2048x872`；显式切回 `Qwen/Qwen-Image` 时使用 `1664x928`。
- 新 Skill 的 prompt 生成器不再把文章标题、章节标题和关键词原样送入图片模型，只保留去文字化视觉概念和隐喻。

### Local-first 确定性渲染（历史决策，后续已修订）

背景：用户指出模型矩阵对比图与期望差距很大，也明显不如早期本地预览。实际原因是 t2i 模型会自由发挥，而早期本地预览是先由 Agent 做语义翻译，再用确定性图形规则绘制。

修订说明：该阶段解决了外部 API 随机性问题，但后续用户明确指出“Local First”应指内置生图，不应指 Python 本地渲染器。因此本节只保留为历史记录。

决策：

- 当时将本地结构渲染固化为 `scripts/render_local_images.py`，作为默认交付路线；后续已降级为构图草图。
- 当时 `batch_article_images.py` 默认模式改为 `local`；后续已改为 `codex`。
- 本地渲染器仍保留用于功能性检查：无文字、语义清楚、主体够大、色彩一致和系列稳定。

### 本地预览与对比图差距修正

背景：用户进一步反馈后续模型对比图与目标差距很大，也与此前认可的本地预览差距大。复核发现差距来自两处：API 模型直出会自由改变构图和线条；本地渲染器在 Z-Image `2048x872` 宽画幅下仍用统一缩放，导致主体偏小、墨线偏细，总览图还会拉伸原始宽图。

决策：

- 当时不继续把“调模型”作为默认优化方向，继续以 local-first 保证构图和系列一致性；后续已明确默认终图由内置生图完成。
- `render_local_images.py` 改为按隐喻模板的基准宽高计算主体尺度，并设置安全上限，避免不同对象在宽画幅下视觉大小不一致。
- 墨线从均匀细线调整为更厚的近黑线，并把加重位置控制在端点、转角、接缝等结构锚点，避免长边分段或随机噪声。
- 总览图保持原图宽高比例居中排版，不再强制拉伸缩略图，保证用户看到的预览和实际 PNG 一致。

### API 构图锁定路线

背景：用户提出 API 路线是否也能先确定语义和构图，再转述给 API。复核后认为纯文字 prompt 只能弱约束构图，真正接近本地预览的方式是先生成视觉 skeleton，再用编辑模型沿 skeleton 风格化。

决策：

- `generate_prompts.py` 为每张图增加 `composition_spec`，把隐喻、主体尺度、背景模式、重点色和禁止新增元素等规则结构化保存。
- `batch_article_images.py` 增加 `--mode guided-edit`：先调用本地渲染器输出 `composition_guides/`，再把每张 guide 作为编辑模型输入图。
- `guided-edit` prompt 强调保留画幅、对象数量、主体大小、位置、背景模式和重点色位置，只允许做 Claude Blog 风格化。
- 保留 `t2i` 作为松约束探索路线，但不将其视为默认终稿路线；后续真实 API 测试应优先比较 `composition_guides/` 与 `guided-edit` 结果的布局保持度。

### Guided-edit API 实测结论

背景：用户要求直接用 API 跑完整 Folia 文章。先用默认 `guided-edit` 跑 13 张，随后根据色彩漂移问题收紧 prompt 并移除构图草图中的浏览器圆点，再跑 tightened v2 full。

决策：

- `guided-edit` 确实比纯 t2i 更能保住本地预览的布局、主体大小和对象数量，适合作为“API 候选”路线。
- Qwen edit 仍会基于视觉常识主动补色，例如浏览器按钮橙色、红点、浅棕卡片、纸面暖化；文字禁令不能完全压住这些偏移。
- 默认交付仍保持 Local First；API 输出必须经过颜色 QA 和人工筛选，不应直接覆盖本地渲染终稿。
- 本地构图草图移除 browser traffic-light 圆点，降低橙色触发；`guided-edit` prompt 增加严格调色板和空白块保持米白/蓝灰的要求。
- 后续如果继续走 API，应优先增加自动色彩 QA：检测红/橙/棕等非配置色，失败则局部重跑、降级到本地渲染，或改用 Z-Image t2i 多候选。

### Local First 作为正式路线（历史决策，后续已修订）

背景：用户确认如果 Local First 已经成立，就不需要为了默认交付继续走外部 API；外部 API 的生图理解与稳定性不如当前本地结构渲染路线。

修订说明：该决策后续被 2026-05-31 的“纠正默认生图路线”覆盖。当前 `Local First` 不再指 Python 本地渲染器出终图，而是指不走外部 API，由 Agent 调用 Codex/ChatGPT 内置图片生成能力出终图。

决策：

- 当时将 Skill 的正式交付路线明确为 Local First，并默认使用本地结构渲染生成公众号配图；该点后续已修订为内置生图。
- 不再主动调用外部图片 API 作为质量增强步骤，也不把替换/更新 API Key 后继续实测列为默认待办。
- `guided-edit`、`t2i` 和 `edit` 保留为用户明确要求时的实验/对照工具；其输出必须经过布局、颜色和文字 QA，不直接覆盖终稿。
- 当时后续优化优先放在本地渲染器；该方向后续已调整为优先优化内置生图 brief 和 prompt。

## 2026-05-31

### API 调用显式解锁（历史决策，后续已修订）

背景：用户进一步确认该 Skill 默认不使用外部 API，只使用 Agent 自身的 Local First 图片生成能力，以保证语义理解、构图和系列一致性。

修订说明：该决策中的“本地出图”后续明确为“内置生图”，不是 Python 本地渲染器。

决策：

- 当时 `batch_article_images.py` 保持 `local` 为默认模式；后续已改为 `codex` 默认模式，`local` 只保留为构图草图。
- `t2i`、`edit` 和 `guided-edit` 必须显式传入 `--allow-api` 才能调用外部图片接口。
- API Key 只在通过 `--allow-api` 后读取；默认内置生图队列和本地草图都不读取 `secrets.env` 或 `SILICONFLOW_AK`。
- `SKILL.md` 中所有 API 实验命令示例同步加入 `--allow-api`，防止协作者误把实验路线当成默认交付路线。

### 本地隐喻库多样性扩展

背景：用户指出“法律人为什么要研究 AI”一文的 Local First 结果多样性不足，抽象内容过多落在方框、圆圈和连线上；旧 `claude-style-illustration` 内部抽象对象更丰富。

决策：

- 保持不走外部 API 的默认路线，不因多样性问题回退到外部 API；后续已明确终图来源为 Codex/ChatGPT 内置生图。
- 从旧 Skill 的关系型隐喻思路中抽取适合 Claude Blog 低密度对象卡片的模板，新增漏斗、广播扩散、棱镜、迷宫、飞轮、脚手架、指南针地图、样品托盘和天平。
- 长文配图规划时优先按“关系”选择隐喻：压缩、分发、筛选、判断、路径、沉淀、协作，而不是只按题材选择放大镜、雷达、节点网络。
- 基础隐喻仍保留，但在同一篇长文里应避免连续重复“方框 + 圆圈 + 连线”的节点式画面。
