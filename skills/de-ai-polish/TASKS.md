# de-ai-polish TASKS

> 本文件本地维护（被 .gitignore 排除），用于追踪 skill 自身的方法论迭代。版本号与 CHANGELOG.md / SKILL.md frontmatter 保持一致。

## v1.5.0 — Protected Spans + 场景分流 + 评分门禁（小版本，不碰类型学）✅ 已完成

- [x] A. Protected Spans（禁改项先划）
  - [x] SKILL.md 在 Step 1 后加"Protected Spans 划定"动作，列法律场景默认保护范围（法条与司法解释编号 / 当事人·机构·律所全称 / 程序术语 / 直接引语与引证 / 合同条款编号 / 数值·日期·比例·金额 / URL 与文书编号）
  - [x] Step 2-4 加"不得触碰已划定 Protected Span"约束；若 span 表面像 AI 味（如机构全称带"有限公司"），仍保留，只在备注提示
- [x] B. 场景分流
  - [x] SKILL.md 加"启动闸门：场景判定"小节，定义法律文书 / 公众号·公开评论 / 口语·即时回复 / 通用 四场景及默认力度
  - [x] 启动闸门"先判场景"：场景决定力度 + Protected Spans 宽度 + 重点扫描哪几类污染
- [x] C. 评分门禁接入
  - [x] SKILL.md 新增 Step 7 交付前评分门禁，定义回炉阈值（总分 <7.0 / 自然度 <1.5 / 个性度 =0 / 法律文书专业度 <1.5）
  - [x] references/quality-scoring.md 补"作为交付门禁使用"节 + "直接度 / 信任读者"辅助视角（不新增维度）
- [x] 同步 CHANGELOG（v1.5.0 条目）+ frontmatter version → 1.5.0

## v2.0.0 — Voice Calibration 改造 Step 5（大版本）✅ 已完成

- [x] 改造 references/personal-style-guide.md 为"声音抽取流程 + author profile 模板"
  - [x] 定义 voice profile 七维度（句长分布 / 词选层级 / 段首习惯 / 标点习惯 / 口头禅与过渡 / 观点密度 / 语气倾向）
  - [x] 加"从作者样本提取 voice profile"的可操作流程（通读 → 逐维填 → 标记反例 → 产出画像）
  - [x] 加 author profile 可填模板
- [x] SKILL.md Step 5 重构：有样本走 Voice Calibration / 无样本用默认特征（两条路径）
- [x] 保留现有正向特征清单作为"无样本时的默认 voice"
- [x] 比喻 / 句式标注为示例（在"默认 voice"分隔说明里统一标注，非通用规则）
- [x] 同步 CHANGELOG（v2.0.0 条目）+ frontmatter version → 2.0.0

## v2.0.1 — Voice Calibration 边界与门禁收口（小版本）✅ 已完成

- [x] A. 样本使用边界
  - [x] 在 Step 5 与 `references/personal-style-guide.md` 明确：只使用用户提供或确认可用于本次任务的作者样本
  - [x] 明确 Voice Calibration 只学习表达特征，不冒充作者身份、不复制样本原句、不引入样本事实
- [x] B. 评分门禁闭环
  - [x] 在 Step 7 与 `references/quality-scoring.md` 加入 voice profile 匹配检查
  - [x] 明确有作者样本时，profile 严重偏离、复现反例或复制高辨识短语均需回炉 Step 4/5
- [x] C. 发布同步
  - [x] 同步 `SKILL.md` / `CHANGELOG.md` / README / Marketplace 版本到 v2.0.1
  - [x] 更新独立 README 的核心设计与关键文件说明，补齐 Voice Calibration 口径

## 观察项（暂不动，待实战检验）

- [ ] 三轴分离（Tier 问题强度 / 档位改写力度 / scope 改写范围）：等 v1.4.0 类型学在真实文章上跑 3-5 次后评估。若"7 类归类不稳定"或"类型既当归因又当力度"问题重现，作为类型学 v2 启动（可能 v2.1.0 或 v3.0.0）。在此之前，v1.5.0 的场景分流 + 评分门禁已部分缓解"力度不分"问题。
