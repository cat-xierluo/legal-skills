# Transcription Corrector 任务清单

## 当前目标

- [x] 创建 skill 目录结构（SKILL.md / config/ / references/ / archive/）
- [x] 编写 SKILL.md 主流程（Step 0~5）与边界说明
- [x] 编写 references/correction_patterns.md（判断准则版，非映射表）
- [x] 编写 config/user_dictionary.example.yaml，含"目标值+权重"原则注释
- [x] 用 260606 AI技能创新大赛.md 试跑验证
- [x] 采用"目标值+权重"词典原则（词典项不直接触发替换）
- [x] 创建 LICENSE.txt（MIT，自研版权）
- [x] 创建 CHANGELOG.md（v1.0.0）
- [x] 创建 DECISIONS.md
- [x] 修正 SKILL.md frontmatter 版本号（0.1.0 → 1.0.0，符合 skills/ 目录规则）
- [x] 登记到 `.claude-plugin/marketplace.json`
- [x] 添加到根 README "最近更新区"
- [x] 精简 frontmatter description（4 句 → 1 句）
- [x] 解耦 example 与真实配置（通过项目根 `.gitignore` 模式 `**/config/*.yaml` + `!**/config/*.example.yaml` 排除真实 yaml）
- [x] 从公开文件移除作者名（除 frontmatter 外）
- [x] 新增 Step 0.5：TXT → Markdown 转换
- [x] 加 v1.0.1 修订记录
- [x] 从公开文件移除对其他 skill 名称的引用（SKILL.md / CHANGELOG / DECISIONS / TASKS / references / example.yaml）
- [x] 创建本地 config/user_dictionary.yaml（git ignore），追加个人工作栈术语 + 个人身份项 + 业务领域术语
- [x] 新增 Step 3.5 基础空白清理（默认开启，无损）+ references §6
- [x] 扩展 Step 5 为双写策略（主归档 + 源文件目录镜像）
- [x] 升级 frontmatter version 到 1.0.2 + CHANGELOG 加 v1.0.2 修订记录
- [x] 采纳 §7.1 词典建议，扩展本地 user_dictionary.yaml（DeepSeek / Auto / AI / MCP / 腾讯元宝 / 豆包 / 智和 / Alpha / supreme legal analyzer / C1-C6 / 六大矛盾 / 四大图表）
- [x] 新增 Step 3.6 口语词精简（默认开启）+ references §7
- [x] 扩展 example.yaml 为"常见技术名词 + 常见法律术语"（35 项）
- [x] 升级 frontmatter version 到 1.0.3 + CHANGELOG 加 v1.0.3 修订记录
- [x] 新建 references/first_use.md：把"首次使用"小节下移到独立 references 文件
- [x] SKILL.md 一级标题去掉版本号（保留在 frontmatter）
- [x] "配置解耦原则"小节明确归类为"评价规范相关"
- [x] 升级 frontmatter version 到 1.0.4 + CHANGELOG 加 v1.0.4 修订记录
- [x] v2 补跑 260606 AI技能创新大赛.md：Step 3 词典替换 44 处 + Step 3.3 口语词精简 84 处（v1.0.2 漏跑整节，DEC-013 复盘）
- [x] 段首节奏标记默认删除（v2 激进版起）— SKILL.md §3.3.2 保留规则从"段首/段尾"改为"段尾"（DEC-013 落地）
- [x] v3 第三轮：按激进版段首删除跑，输出 52 处（v3 标 STABLE.md，226 处累计校对）
- [x] ASR 误转写高频模式沉淀到 references/correction_patterns.md §10（6 类模式 + 9 项 example.yaml 推荐）
- [x] 段中并列停顿 啊 识别模式写到 references/correction_patterns.md §11（决策树 + 边界案例）
- [x] 必检清单加到 references/correction_patterns.md §12（grep 自检命令，v1.0.2 bug 复盘）
- [x] Step 3.3 必检项加到 SKILL.md（防止 v1.0.2 漏跑整节 bug 重现）
- [x] 升级 frontmatter version 到 1.0.5 + CHANGELOG 加 v1.0.5 修订记录
- [x] Step 体系重构为 5 个 Phase（DEC-014）
- [x] references/correction_patterns.md 全面同步 step 引用（Step 0/3/3.5/3.6/4 → Step 1.x/3.x/4.x）
- [x] SKILL.md 拆分：6 章节（概述/适用/不适用/配置示例/配置解耦/参考文档）移到 references/skill_overview.md，SKILL.md 从 528 行降到 445 行（skill-architect 500 行建议内）

## 后续待办

- [x] ~~用 v1.0.3 重跑 260606 AI技能创新大赛.md，验证 Step 3.6 口语词精简在实战中的命中率与误判率~~（已由 v2/v3 完成，84 + 52 处命中，详细见 DEC-013）
- [ ] 用新课程稿/客户沟通稿试跑，验证 Step 4.x 润色行为（Phase 4 默认关闭，需要用户显式开启）
- [ ] 用 `.txt` 输入试跑 Step 1.2，验证发言人+时间戳识别正则在不同 ASR 引擎输出上的兼容
- [ ] 评估是否需要 scripts/verify_corrections.py（自动核对词典项在原文中是否有"目标值 vs 漂移形式"对比）
- [ ] 根据实战反馈，把 references/correction_patterns.md §10"ASR 误转写高频模式"持续补充（按主题分类累积）
- [ ] 若启用 Phase 4 润色模式，需要补一份 `speaker_merge_examples.md` 说明合并判定条件
- [ ] 评估是否需要支持自定义词典路径，让多入口场景可指向统一词典文件
- [ ] 在源文件目录镜像策略下，需要一个"是否覆盖"开关的明确语义（默认不覆盖、用户可显式 `--force`）
- [ ] Step 3.3 口语词精简的"易误判案例"清单根据实战持续补充（DEC-013 提到的"段中并列停顿 啊 识别"是首批）
- [ ] SKILL.md 补"STABLE 版本标记"工作流（v3 写了 STABLE.md 但 SKILL.md 没记录何时/如何标 stable）
- [ ] archive 旧版本清理策略文档化（4 个目录历史：v1.0.0 / v1.0.2 / v2 / v3）
