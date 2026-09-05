---
name: course-generator
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "2.10.2"
license: MIT
description: 将课程转录稿、逐字稿、讲稿或文献整理为可独立阅读的 Markdown 课程，并通过来源索引、素材账本和确定性验收保留关键案例、操作步骤与专业判断。用户要求从一份或多份现有文本生成课程总览、章节或完整课程时使用。
---

# 课程内容整理

## 任务目标

把现有文本整理成读者无需接触原始转录稿也能理解和使用的课程。正文应完整保留来源中的重要观点、案例、操作过程、失败修正和判断方法，同时去除现场口语、会务信息和转录噪声。

本技能默认生成课程，不自动归档、移动原文件或改造成其他内容产品。用户明确要求生成后的归档或培训方案提取时，再读取 [post-generation-actions.md](references/post-generation-actions.md)。

## 输入与交付

开始前确认：

- 一份来源文件或一个来源目录；优先处理 `.md`、`.txt`。
- 课程输出目录；未指定时在来源旁建立新的课程目录，并在写入前说明位置。
- 是否存在勘误、编校说明或指定的现行口径文件。
- 是否需要使用用户词典纠正专名或固定术语；需要时从 `config/user_dictionary.example.yaml` 复制为 `config/user_dictionary.yaml`，只登记能够确认的替换。
- 目标目录是否已有内容；不得静默覆盖。

默认交付包括：

- `00 <课程名称> - 总览.md`
- 按阅读顺序编号的课程章节
- `source-index.json`
- `course-manifest.json`

原始材料保持只读。临时计划、批次文件、辅助脚本和缓存放在课程目录之外。

## 核心要求

1. **忠实来源**：数字、动作、结果、建议和专有名称必须能回到来源；原文没有的能力、流程、案例和结论不得用常识补齐。
2. **保留精华**：每个有效来源块都要进入素材账本或使用受控理由跳过。案例、操作、踩坑、取舍和判断技巧不得被压成一句摘要。
3. **遵守现行口径**：来源存在明确修订时，以控制文档为准；旧口径只进入审计记录，不得重新出现在读者正文。
4. **证据跟随章节**：每个二级标题必须有绑定素材，素材正文证据只能来自自己的目标小节，不跨节借用。
5. **书面化而不扩写**：删除逐字稿框架和口语赘词，但保留原文的不确定、举例和设想语气；单一样本不得扩成普遍规律或行业惯例。
6. **生产与验收分离**：生成者完成正文，脚本检查客观约束，最后再由独立审阅者检查素材守恒、事实忠实和阅读质量。

冲突时依次保护：事实忠实与现行口径、核心素材完整、章节证据边界、读者可读性、审计便利。

## 工作流程

生成任务开始后，先完整读取 [generation-workflow.md](references/generation-workflow.md)，再按以下顺序执行；不得跳过账本预检直接写正文。

1. 运行 `index_sources.py` 建立确定性来源索引。
2. 用 `ledger_tool.py init` 初始化 manifest，确认权威声明并冻结章、节计划。
3. 按 `status` 返回的来源块分批建立素材账本，运行 ledger 阶段自动收口和预检。
4. 选择少量有教学价值的代表图，由工具生成章节标题和修订句脚手架。
5. 读取 [overview_prompt.md](references/overview_prompt.md) 和 [chapter_prompt.md](references/chapter_prompt.md)，先写总览，再逐章生成；每章通过 `check-chapter` 后才进入下一章。
6. 运行 final 阶段自动收口和 `verify.sh`，再完成人工语义复核。

大纲和素材判断规则见 [outline_prompt.md](references/outline_prompt.md)。机器字段及 JSON 示例见 [course-manifest.md](references/course-manifest.md)。默认最多 8 章；只有用户明确要求超过 8 章时才读取 [advanced-overrides.md](references/advanced-overrides.md)。

## 完成标准

只有同时满足以下条件，才可交付：

- 总览、manifest 声明的全部章节和两份强制 JSON 均存在。
- 素材账本覆盖全部有效来源块，跳过项有受控理由，高价值内容没有无理由净丢失。
- 每章 `check-chapter` 通过，最终 `verify.sh` 退出码为 `0`。
- 独立审阅者读取 [quality-evaluation.md](references/quality-evaluation.md)，按证据完成语义验收；人工抽查确认数字、动作链、建议、结果和专名可回溯，修订口径无冲突，章节之间没有明显重复。
- 读者正文不出现 `SRC/BLK/MAT/IMG`、门禁解释、生成日志、临时文件或来源没有讨论的内部术语。

脚本通过只证明客观契约成立，不等于语义质量已经通过。交付时分别报告脚本结果、人工复核范围和未验证部分。

配额、网络或平台异常时保留现场并报告，不从头重跑，不把半成品或执行者自报记为成功。

## 权限与隐私

- 只读取用户指定的来源，只向已说明的课程目录写入。
- 脚本不联网、不安装依赖、不修改原始材料；`init/plan/merge/select-images` 原子更新索引或 manifest，`scaffold` 只创建缺失的标题脚手架，`finalize_manifest.py --write` 只更新 manifest。
- 未脱敏转录稿和课程材料按最小必要原则处理，不写入公开示例、变更记录或配置模板。

## 依赖

### 系统依赖

| 依赖 | 用途 | 安装方式 |
|---|---|---|
| `python3 >= 3.10` | 运行来源索引、账本和验收脚本 | macOS: `brew install python`<br>Linux: `sudo apt-get install python3` |

### Python 包

无需第三方 Python 包，全部脚本只使用标准库。

## 资源索引

- [generation-workflow.md](references/generation-workflow.md)：完整生成步骤、命令顺序和失败处理；每次生成课程时读取。
- [outline_prompt.md](references/outline_prompt.md)：素材分类、章节规划和图片判断；建立计划与账本时读取。
- [overview_prompt.md](references/overview_prompt.md)：总览写作要求；生成总览时读取。
- [chapter_prompt.md](references/chapter_prompt.md)：章节写作和单章自检；逐章生成时读取。
- [course-manifest.md](references/course-manifest.md)：manifest 字段和 JSON 示例；准备计划、批次或图片选择文件时按需查询。
- [quality-evaluation.md](references/quality-evaluation.md)：课程成品的语义硬失败、质量评分和版本晋级标准；独立验收或回归比较时读取，不提供给生成者作为写作提纲。
- [post-generation-actions.md](references/post-generation-actions.md)：归档和培训方案提取；仅在用户明确要求时读取。
- [verify.sh](scripts/verify.sh)：最终确定性验收入口。
