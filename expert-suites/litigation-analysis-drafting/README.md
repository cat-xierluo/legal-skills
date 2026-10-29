# 诉讼分析及文书撰写专家套件

> 整套源码 v0.2.0 待首次发布（尚无公开下载）

面向具体诉讼案件的一体化工作流：接收和整理材料，形成事实、证据、争点与策略判断，再生成起诉、答辩、方案和客户交付文书。分析和写作是同一案件中的连续工作，不在两个套件之间切换。

## 适用场景

- 从新案接收、材料整理和事实证据分析，推进到法律检索、风险判断和诉讼策略；
- 对起诉状、答辩材料提出证据初评，或把已形成的判断转成方案和客户可读材料；
- 对一份判决做法理深析，并结合卷宗、证据和检索材料判断上诉或再审路径；
- 在同一案件里反复修订事实、争点、请求和文书，需要保持同一组证据编号和法律依据。

## 不适用场景

- 不替代承办律师阅卷、会见、庭审判断和正式法律意见；
- 不执行签章、提交、发送或法院系统操作；
- 材料不足时不得把推断写成已确认事实，也不得凭模板补造请求、金额、期限、案号或证据。

## 包含的 Skills

| Skill | 在本套件中的作用 | 单独下载 |
| :--- | :--- | :--- |
| [new-case](../../skills/new-case/) | 建立标准案件目录、信息底板和期限结构 | [已发布 v1.5.0](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/new-case-1.5.0.zip) |
| [court-sms](../../skills/court-sms/) | 解析法院短信、获取法院文书并回填案件材料；源码 v1.5.4 待发布 | [已发布 v1.5.1](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/court-sms-1.5.1.zip) |
| [legal-ocr](../../skills/legal-ocr/) | 把扫描件和多格式材料转换为可分析文本 | [已发布 v1.6.0](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/legal-ocr-1.6.0.zip) |
| [pdf-organizer](../../skills/pdf-organizer/) | 建立页码和证据索引，拆分、合并并规范材料；源码 v0.6.1 待发布 | [已发布 v0.6.0](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/pdf-organizer-0.6.0.zip) |
| [legal-case-analysis](../../skills/legal-case-analysis/) | 综合材料、起诉状证据初评、庭审复盘和上诉再审判断，形成风险与诉讼策略；源码 v1.1.2 待发布 | [已发布 v1.0.0](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/legal-case-analysis-1.0.0.zip) |
| [judgment-analysis](../../skills/judgment-analysis/) | 深析单份判决的事实认定、裁判理由、主文和文内疑点；源码 v2.0.0 待发布 | 尚无公开下载 |
| [yuandian-law-search](../../skills/yuandian-law-search/) | 设计检索命题并核验法规、正反类案和文内法律依据；源码 v1.10.1 待发布 | [已发布 v1.10.0](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/yuandian-law-search-1.10.0.zip) |
| [legal-visualization](../../skills/legal-visualization/) | 生成时间线、主体关系、争点证据矩阵和庭审路线图 | [已发布 v0.8.2](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/legal-visualization-0.8.2.zip) |
| [elements-complaint-generator](../../skills/elements-complaint-generator/) | 把已写好的常规起诉状或答辩材料转成官方要素式示范文本结构；源码 v0.16.1 待发布 | [已发布 v0.16.0](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/elements-complaint-generator-0.16.0.zip) |
| [legal-proposal-generator](../../skills/legal-proposal-generator/) | 把案件判断转成诉讼方案、建议书、咨询报告、结案汇报和客户沟通材料 | [已发布 v0.4.1](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/legal-proposal-generator-0.4.1.zip) |
| [md2word](../../skills/md2word/) | 把审定后的 Markdown 转成正式 Word 文档 | [已发布 v1.3.8](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/md2word-1.3.8.zip) |

## 工作流

本套件按案件目标选择入口，不要求按固定顺序跑完全部成员。

| 阶段 | 主要入口 | 形成的结果 |
| :--- | :--- | :--- |
| 案件与材料底座 | `new-case`、`court-sms`、`legal-ocr`、`pdf-organizer` | 案件目录、法院文书、可检索材料和证据索引 |
| 案件专项分析 | `legal-case-analysis`、`judgment-analysis`、`yuandian-law-search` | 事实、证据、争点、法律依据、风险和策略选项 |
| 文书撰写与交付 | `elements-complaint-generator`、`legal-proposal-generator`、`md2word` | 起诉答辩、诉讼方案、客户材料和正式 Word |
| 表达与复盘 | `legal-visualization`、`legal-case-analysis` | 时间线、关系图、庭审复盘和补强清单 |

分析和文书撰写会循环迭代：发现证据缺口时回到材料与分析，形成新的判断后再修订对应文书。所有版本围绕同一案件目录和同一组证据编号延续。

## 与法律材料与证据处理套件的边界

「法律材料与证据处理」面向任意业务场景，解决扫描、OCR、音视频转录、PDF 处理和法院来文归档。本套件面向诉讼案件，只保留完成诉讼分析和文书所必需的材料处理成员；需要音视频转录、证据截图或批量 PDF 预处理时，可组合使用前者。

## 历史套件

原「诉讼案件前期研判」和「诉讼文书与案件推进」两个套件已合并为本套件。历史下载仍可访问：

- [suite-litigation-assessment-0.1.0.zip](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/suite-litigation-assessment-0.1.0.zip)
- [suite-litigation-documents-operations-0.1.0.zip](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/suite-litigation-documents-operations-0.1.0.zip)

旧 ZIP 不包含本次合并后的名称、成员组织和工作流说明。

## 安装方法

下载并解压完整套件 ZIP，把其中 `skills/*` 复制到 Agent 的 Skills 根目录，再按各成员 `SKILL.md` 配置依赖。只做单一任务时，也可以只安装成员表中的相应 Skill。

## 人工复核与使用边界

案件事实、证据编号、请求权基础、诉讼请求、金额、期限、管辖和程序选择必须逐项回溯到原始材料和有效法源。文书只能在律师确认后签发、提交或对外发送；套件不自动写回法院系统或案件状态。

## 版本与许可证

当前套件版本为 `0.2.0`。套件本身不设独立许可证；各成员 Skill 按其目录内 `LICENSE.txt` 分别授权，下载或使用套件不改变成员原有许可条件。
