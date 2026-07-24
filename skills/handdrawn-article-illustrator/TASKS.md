# Tasks

## 当前任务

- [x] 2026-07-23 将配色从硬编码解耦为主题包机制：新增 `themes/` 目录、`blue-gray`/`ink-black`/`terracotta` 三套预设、`--theme` 参数、`config/style.json` 改造为激活指针+覆盖层。
- [x] 2026-07-23 去除 SKILL.md、references/、scripts 中所有蓝灰色值硬编码，改为配置引用与占位符。
- [x] 2026-07-23 将 skill 从 `private-skills/` 迁移到 `legal-skills/skills/` 公开发布（MIT），更新根 README 技能列表与 marketplace.json，新增局部 `.gitignore`。
- [x] 2026-06-02 将旧 `claude-blog-wechat-illustration` 与 `claude-style-illustration` 移入顶层 `Archive/`，主配图入口只保留 `handdrawn-article-illustrator`。
- [x] 2026-06-14 新增默认图片压缩脚本，将 ImageGen 交付图原地压缩到 `500KB` 以下，并尽量压到 `200KB` 以下。
- [x] 2026-06-02 将默认生图路线进一步收紧为 ImageGen/内置生图，默认不再运行 `--mode local` 或生成 `local_preview/`。
- [x] 2026-06-14 根据“异质关联/草创生态”配图总览反馈，限制左中右收束版式重复，新增构图审计和非线性版式轮换规则。
- [x] 2026-06-02 将归档旧 Skill 的入口文件从 `SKILL.md` 改为 `ARCHIVE_NOTICE.md`，避免 Archive 内目录被误触发。
- [x] 2026-06-02 纠正三档测试方式：用 ImageGen 真实生成 `reference_card`、`balanced`、`high_abstract` 三张样图，并归档到 `archive/20260602_imagegen_strength_probe/`。
- [x] 2026-06-02 在 `SKILL.md` 中明确：用户要求看效果时必须调用 ImageGen/内置生图，本地预览不能算成片测试。
- [x] 2026-06-02 用真实文章建立 `archive/20260602_abstraction_strength_article_probe/`，按 `reference_card`、`balanced`、`high_abstract` 三档生成 `codex` 队列、本地预览和测试说明。
- [x] 2026-06-02 在 `SKILL.md` 中补充归档机制：顶层 `Archive/` 存退役 Skill，当前 Skill 内部 `archive/` 存测试轮次和样图。
- [x] 2026-06-02 将主 Skill 重命名为 `handdrawn-article-illustrator`，中文标题调整为“手绘文章配图”。
- [x] 2026-06-02 增加 `abstraction_strength` 三档抽象强度：`reference_card`、`balanced`、`high_abstract`，并接入配置、outline、prompt 编译和 Codex 生图队列。
- [x] 2026-06-01 合并 `claude-blog-wechat-illustration` 与 `claude-style-illustration` 路线，新建主 Skill `handdrawn-article-illustration`（手绘风格配图）。
- [x] 2026-06-01 将旧 `claude-style-illustration` 的 12 张 `target_gallery_core` 参考锚点复制到新 Skill 的 `assets/style_anchors/target_gallery_core/`。
- [x] 2026-06-01 将默认生图路线统一为 Codex/ChatGPT 内置图片生成能力，外部 API 仅保留为用户明确要求时的实验路线。
- [x] 2026-06-01 将旧 `claude-blog-wechat-illustration` 与 `claude-style-illustration` 改为归档跳转入口，并保留原始 `SKILL.md` 为 `ARCHIVED_SKILL.md`。
- [x] 2026-06-01 将生产说明、脚本 prompt 和参考文档改为中性的“手绘风格配图 / 手绘对象卡片”表述，不再绑定具体品牌名称。
- [x] 2026-05-29 新建 `claude-blog-wechat-illustration`：基于 Claude Blog 架构，为公众号文章生成首图、正文横图和方形卡片配图提示词与批量出图流程。
- [x] 2026-05-29 补齐批量脚本并完成最小验证：语法检查、样例大纲生成 `prompts.json`、批量入口 `--prompts-only`、两个入口脚本 `--help`。
- [x] 2026-05-29 根据用户反馈提高长文配图密度：默认改为首图 + 10-14 张正文横图，并用 Folia 文章重跑一版密集样图。
- [x] 2026-05-29 根据用户反馈强化 Claude Blog 墨线感：固定蓝灰重点色 `#435C68`，增加白底/蓝底模式，prompt 改为粗细不均的填充墨块轮廓。
- [x] 2026-05-29 根据用户反馈收敛墨线随机感：将线条规则改为稳定轮廓 + 局部压力变化，避免随机抖动和草稿线。
- [x] 2026-05-29 根据用户二次反馈校准墨线：将粗细不均限制到结构锚点，避免整圈随机墨块和边缘噪声。
- [x] 2026-05-29 根据用户反馈放大主体占比：新增可配置主体比例，避免正文图主体过小。
- [x] 2026-05-29 根据用户反馈提升手绘线条自然度：从机械矢量轮廓改为单遍手工描摹、端点收笔和转角压痕。
- [x] 2026-05-29 根据模型矩阵测试修正 prompt 泄字问题：文章标题、章节标题和关键词不再原样进入图片 prompt。
- [x] 2026-05-29 根据用户反馈改为 local-first：新增确定性本地结构渲染脚本，并将批量入口默认模式改为 local。
- [x] 2026-05-29 根据用户反馈修正本地预览与对比图差距：按隐喻模板计算主体尺度、加粗受控墨线，并保持总览图真实比例。
- [x] 2026-05-30 根据用户建议增加 API 构图锁定路线：先生成 `composition_spec` 和本地构图草图，再用 `guided-edit` 交给编辑模型做受控风格化。
- [x] 2026-05-30 用 Folia 文章跑完整 `guided-edit` API 实测，确认构图保持有效，但 Qwen edit 仍会偶发非配置色和纸面暖化。
- [x] 2026-05-30 根据 API 实测收紧 `guided-edit` 颜色约束，并移除构图草图中易触发橙色窗口按钮的小圆点。
- [x] 2026-05-30 根据用户判断确认 Local First 为正式交付路线，外部 API 只保留为用户明确要求时的实验/对照路线。
- [x] 2026-05-31 增加 `--allow-api` 防误触发保护，并同步 API 实验命令示例；该保护继续适用于当前内置生图默认路线。
- [x] 2026-05-31 根据长文配图反馈扩展本地抽象隐喻库，新增漏斗、棱镜、迷宫、飞轮、脚手架、广播扩散、指南针地图、样品托盘和天平模板，减少方框圆圈重复。
- [x] 2026-05-31 新增 `--mode codex`，为 Codex/ChatGPT 内置图片生成能力输出生图队列，不调用外部图片 API。
- [x] 2026-05-31 根据用户纠偏重新定义默认路线：正式终图由 Codex/ChatGPT 内置生图完成，`local` 降级为构图草图/预览，不再把本地渲染器称为默认终稿来源。
- [x] 2026-05-31 根据 Codex 内置生图小样补强图标禁用，避免角色/权限语义被画成打勾、人像、星标、铅笔等 UI 图标。
- [x] 2026-06-01 基于 5 张 Codex 内置生图小样调校抽象程度：将默认语法从文档/角色/权限卡片转向无名抽象机制、slot、hinge、shell、organic plume 和 endpoint capsule。
- [x] 2026-06-01 根据用户反馈强化重点色节奏：长文配图以米白底局部蓝灰为主，并穿插少数蓝灰底米白主体的反转图。
- [x] 2026-06-01 根据用户反馈升级公众号长文配图密度：长文、案例复盘和产品复盘默认 1 张首图 + 18-24 张正文横图，并按每个二级标题或重要三级标题 2-3 张图规划。
- [x] 2026-06-01 根据旧 `claude-style-illustration` 参考图库新增构图家族轮换策略，减少方框、圆圈、连线的重复感。
- [x] 2026-06-01 在 `archive/20260601_density_diversity_probe/` 中跑多轮 Codex/ChatGPT 内置生图小样，验证高密度、多构图家族和统一风格是否平衡。
- [x] 2026-06-01 继续追加第 4-5 轮内置生图测试，验证“安静但略微异样”的抽象机制感是否可控，并补充相关 prompt 边界。
- [x] 2026-06-01 根据用户反馈收回第 4-5 轮过偏方向：默认回到旧 `claude-style-illustration` 示例图锚点，并强化文章理解优先。
- [x] 2026-06-01 追加第 6 轮参考锚点回归测试：以旧示例图家族和 `reader_takeaway_zh` 为约束生成 8 张样图，确认默认方向回到可理解的手绘配图。

## 后续待办

- [x] 基于真实公众号文章跑一轮样图，评估隐喻库和 palette 轮换是否需要收敛。
- [x] 将 `claude-blog-wechat-illustration` 迁移到 `private-skills/` 私有技能仓库。
- [x] 增加 `config/style.json`，允许用户修改固定重点色、背景模式和线条风格。
- [x] 增加 `archive/20260529_folia_ink_refined_probe/`，用于观察受控墨线版本。
- [ ] 如用户再次明确要求 API 实验，再为 `guided-edit` 增加自动色彩 QA：检测红/橙/棕等非配置色，失败时标记重跑或回退本地渲染。
- [x] 如果正式发布到 `skills/`，同步更新根目录 README 和 marketplace 配置。
- [ ] 后续如继续追求更自然笔触，应优先优化内置生图 prompt 与参考 brief；本地纹理后处理只作为草图增强，不作为默认终稿路线。
- [ ] 后续可继续从旧 `claude-style-illustration` 的目标图库中提炼更多内置生图隐喻 brief，但必须附带 `reader_takeaway_zh`，确保服务文章理解。
- [ ] 后续用一篇真实长文跑完整 Codex 内置生图队列，检查 18-24 张图是否能在参考图风格内保持多样性，同时避免难懂意象。
