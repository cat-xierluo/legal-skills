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

## 进行中 — 受保护区域闭环与指令稳定性

- [x] A. 将图片保护从自然语言提醒升级为修改前后主动门禁
  - [x] 在任何改写前生成受保护区域 manifest，至少记录 Markdown 图片所在整行的原文、顺序、数量和 SHA-256
  - [x] 在最终交付前由独立 checker 比对修改前后 manifest；整行删除、移动、改写或数量变化时返回非零退出码，不接受 Agent 自报“已保留”
  - [x] 明确合法例外及其显式授权方式；没有授权时 fail-closed
- [x] B. 修正生产实现与规则范围不一致
  - [x] 审查并改造 `scripts/fix_punctuation.py`：图片所在整行在任何标点转换前整体替换为受保护占位符
  - [x] 覆盖图片 URL 含括号、图片前后同一行存在文本、连续多图、引用块内图片等边界样本
  - [x] LLM 改写路径由 Step 1/7 快照门禁覆盖，标点脚本路径同时按整行保护
- [ ] C. 建立指令稳定性合同与历史回归
  - [x] 为图片整行保护分配稳定 constraint ID；Protected Spans、场景分流和最终评分仍待增加可独立验证的 ID/checker
  - [x] 已建立图片整行保护的“约束 → checker → 产物阶段 → 正例/变异例/历史反例”机器可读映射；其余约束待补
  - [x] 固化“只保留 `![]()` 语法但改写整行”的历史反例并要求阻断
  - [ ] 使用相同输入和配置至少独立运行三轮，逐约束检查真实最终产物；仅在候选绑定证据有效时声明稳定
- [x] D. 当前图片门禁验收
  - [x] 原样保留全部图片整行的正例通过
  - [x] 删除一条、改写一条、调换顺序及只保护语法片段的反例分别被 checker 精确阻断
  - [x] checker 输出绑定修改前后产物 hash、失败 constraint ID 和可复查 measurement
  - [x] `skill-lint` 已识别 checker 与历史反例，未再出现 ISG-005；因尚无外部签名基线，整体状态仍为 `NOT_VERIFIED`（ISG-006）

## 观察项（暂不动，待实战检验）

- [ ] 三轴分离（Tier 问题强度 / 档位改写力度 / scope 改写范围）：等 v1.4.0 类型学在真实文章上跑 3-5 次后评估。若"7 类归类不稳定"或"类型既当归因又当力度"问题重现，作为类型学 v2 启动（可能 v2.1.0 或 v3.0.0）。在此之前，v1.5.0 的场景分流 + 评分门禁已部分缓解"力度不分"问题。
