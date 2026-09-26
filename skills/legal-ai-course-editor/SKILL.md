---
name: legal-ai-course-editor
name_en: Legal AI Course Editor
name_zh: 法律 AI 课程讲义整理
description: "整理法律 AI 课程录音转写文字稿，将口语稿转为结构化书面讲义 Markdown。Use when 用户提供听悟/FunASR 等转写逐字稿，要求整理成课程讲义、学习笔记或书面稿；触发词：整理课程稿、口语转书面、课程讲义、逐字稿整理、课程笔记。"
description_en: "Turns raw speech-to-text transcripts of legal AI courses into structured written lecture notes in Markdown. Use when the user provides a raw transcript (Tingwu/FunASR etc.) and asks to polish it into lecture notes; triggers: 整理课程稿, 口语转书面, 课程讲义, 逐字稿整理, 课程笔记."
description_zh: 整理法律 AI 课程录音转写文字稿，将口语稿转为结构化书面讲义 Markdown。用户提供听悟/FunASR 等转写逐字稿并要求整理成课程讲义或书面稿时使用。
argument-hint: 附上转写稿文件路径，可选说明课程主题与讲者
argument-hint-en: Attach the transcript file path, optionally note the course topic and speaker
argument-hint-zh: 附上转写稿文件路径，可选说明课程主题与讲者
user-invocable: true
version: "1.0.0"
license: CC-BY-NC
author: 杨卫薪律师（微信ywxlaw）
homepage: https://github.com/cat-xierluo/legal-skills
---

# legal-ai-course-editor（法律 AI 课程讲义整理）

> 口语转书面操作细则见 [references/polishing-guide.md](references/polishing-guide.md)，讲义输出模板见 [references/lecture-notes-template.md](references/lecture-notes-template.md)——整理前必读。设计决策见 DECISIONS.md。

## 概述

将法律 AI 课程的录音转写文字稿（听悟/FunASR/剪映等工具产出的口语逐字稿）整理为**结构化书面讲义 Markdown**：去除口语冗余、修正转写错误、重组为模块化讲义，供发布、存档或学习使用。

与 `lecture-review` 的边界：本 skill 只做**内容整理**（口语→书面），不评讲师表现、不分析口癖节奏；`lecture-review` 只做讲授表现复盘，不改写内容。两 skill 输入相同、输出完全不同，用户要求"整理成讲义/书面稿"走本 skill，要求"复盘讲课表现"走 `lecture-review`。

## 依赖

无外部依赖，开箱即用：本 skill 为纯文本整理流程，由 agent 直接通读与改写，不依赖任何脚本或 Python 包。法条核验可选用环境中已连接的法律检索工具（如 yuandian MCP），无该环境时按"待核实"标注处理（见核心原则 4）。

## 核心原则（不可妥协）

1. **忠实原意，只整理不创作**。删除口语冗余、修正转写错误、重组结构，但**不新增观点、不改写结论、不补充讲者没讲的内容**。整理稿是讲者的稿，不是 agent 的稿。
2. **口语转书面的尺度**：允许补全主语、合并口误、调整语序、书面化连接词；不允许把讲者的大白话观点"包装"成他没说过的专业表述（细则见 polishing-guide.md）。
3. **引用可回溯**。讲义中的金句、案例、数据应有出处意识——保留段落在原稿中的大致位置（时间戳或顺序号），便于用户对照原文核查。
4. **不确定即标注**。转写稿中的法条编号、案例名称、工具名/版本、数字数据无法确证时，标注「⚠ 待核实」，不擅自更正。有法律检索工具可用时先核对再标注。
5. **缺失信息显式标注**。课程主题、讲者、日期等元信息转写稿中没有的，在讲义信息头标「未提及/待补充」，不臆测。
6. **敏感信息提醒**。转写稿含真实当事人、未公开案件信息时，整理完成后提醒用户审查隐私与合规。

## 工作流程

```
任务进度：
- [ ] Step 1 预检输入
- [ ] Step 2 通读全文，识别课程结构
- [ ] Step 3 拟定大纲（长稿先确认）
- [ ] Step 4 口语转书面整理
- [ ] Step 5 专业内容核对
- [ ] Step 6 按模板生成讲义
- [ ] Step 7 校验与交付
```

### Step 1：预检输入

- 用 Read 读取转写稿，确认完整性（开头结尾是否截断、是否混杂多人发言）。
- 记录可用元信息：时间戳有无、发言人数、稿件字数。无时间戳的稿，回溯定位改用「原稿顺序号（第 N 段附近）」。
- 元信息（课程名/讲者/日期）转写稿没有时，问用户一次；用户不答则在信息头标「待补充」并继续。

### Step 2：通读全文，识别课程结构

完整通读（超长分页读完），标记：

- 课程骨架：开场引入 → 各知识模块 → 案例讲解 → 操作演示 → 答疑 → 收尾
- 内容类型：概念讲解 / 法律分析 / 工具演示（含提示词）/ 案例 / 个人经验观点 / 互动问答
- 口语问题区：明显口误、转写错字（同音字）、重复段落

### Step 3：拟定大纲（长稿先确认）

- 稿件 ≤ 5000 字：直接整理，大纲写入讲义目录即可。
- 稿件 > 5000 字：先给用户一页大纲（模块划分 + 各模块要点），确认后再展开。用户明确说"直接整理"则跳过确认。

### Step 4：口语转书面整理

按 [references/polishing-guide.md](references/polishing-guide.md) 执行，记住三类操作的边界：

- **删**：语气词（嗯/啊/这个那个）、无信息重复、离题闲聊（可移入附录"题外话"而非直接丢弃）
- **改**：补主语、断句重组、书面连接词、修正同音错字（仅限明显转写错误）
- **留**：讲者金句（保留原话加引用块）、第一人称经验、案例细节、现场有价值的问答

### Step 5：专业内容核对

- 法条引用：编号与条文内容对不上时标注「⚠ 待核实」；环境有法律检索工具（如 yuandian MCP）则先检索核对，核对结果与讲者原话不一致时**保留讲者原话并加注**「讲者口述为 X，经检索为 Y」。
- AI 工具名/功能/版本：明显过时或错写时同样"保留原话 + 编者注"。
- 数字（日期、金额、比例）：上下文可自证的修正，不可自证的标待核实。

### Step 6：按模板生成讲义

按 [references/lecture-notes-template.md](references/lecture-notes-template.md) 输出 Markdown 讲义，落盘到用户指定位置；未指定时与转写稿同目录，命名 `{课程名}-讲义.md`（课程名未知用 `course-notes-{日期}.md`）。

### Step 7：校验与交付

交付前逐项自查：

- [ ] 无新增观点：抽查每个模块的结论句，能对应回原稿
- [ ] 无口语残留：随机抽 3 段读一遍，无"嗯/啊/就是说"堆积
- [ ] 所有「⚠ 待核实」「未提及」标注集中可查（讲义附录有清单）
- [ ] 金句引用未改动原话
- [ ] 元信息头完整（没有的项标待补充而非留空）

交付时向用户报告：讲义结构概览、整理幅度（删改比例的粗略描述）、待核实清单条数、敏感信息提醒（如适用）。

## 输出物

| 产物 | 说明 | 默认 |
|------|------|------|
| 讲义 Markdown | 结构化书面讲义（模板见 references） | 必产 |
| 题外话/花絮附录 | 离题但有价值的内容移入讲义附录 | 默认并入讲义 |
| 纯净金句集 | 仅当用户要求时单独输出 `*-quotes.md` | 不产 |
