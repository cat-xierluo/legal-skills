# 诉讼案件前期研判专家套件

> [下载完整专家套件](https://github.com/cat-xierluo/legal-skills/releases/latest/download/suite-litigation-assessment-0.1.0.zip)

用于从新案接收、材料整理和事实证据分析，一路推进到法律检索、风险判断、策略方案和客户可读交付。

## 适用场景

- 新收民商事、行政或刑事相关案件的初步筛查与建档；
- 梳理事实时间线、证据链、争议焦点和待核事实；
- 制定正反检索命题，形成诉讼路径、风险与下一步行动建议。

## 不适用场景

- 不代替承办律师阅卷、会见、庭审判断和正式法律意见；
- 不直接生成最终签发文书；
- 材料不足时不得把推断写成已确认事实。

## 包含的 Skills

| Skill | 在本套件中的作用 | 单独下载 |
| :--- | :--- | :--- |
| [new-case](../../skills/new-case/) | 建立标准案件目录、信息看板和期限底座 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/new-case-1.4.0.zip) |
| [legal-case-analysis](../../skills/legal-case-analysis/) | 梳理事实、证据、争点、风险和诉讼策略 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/legal-case-analysis-1.0.0.zip) |
| [yuandian-law-search](../../skills/yuandian-law-search/) | 设计检索矩阵并核验法规与正反类案 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/yuandian-law-search-1.9.1.zip) |
| [legal-proposal-generator](../../skills/legal-proposal-generator/) | 把研判结果转成诉讼方案、咨询或沟通报告 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/legal-proposal-generator-0.3.2.zip) |
| [legal-ocr](../../skills/legal-ocr/) | 把扫描件和多格式材料转换为可分析文本 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/legal-ocr-1.6.0.zip) |
| [pdf-organizer](../../skills/pdf-organizer/) | 建立页码索引并按材料内容整理 PDF | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/pdf-organizer-0.6.0.zip) |
| [legal-visualization](../../skills/legal-visualization/) | 生成时间线、主体关系、争点证据矩阵等图解 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/legal-visualization-0.8.2.zip) |
| [md2word](../../skills/md2word/) | 把审定后的 Markdown 转成正式 Word 文档 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/md2word-1.3.6.zip) |
| [court-sms](../../skills/court-sms/) | 解析法院通知、获取文书并回填案件材料 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/court-sms-1.5.1.zip) |

## 建议使用方式

1. 以 `new-case` 建档，并用 `court-sms`、`legal-ocr`、`pdf-organizer` 补齐材料底座；
2. 让 `legal-case-analysis` 形成事实—证据—争点工作底稿，明确未知项；
3. 将争点和正反命题交给 `yuandian-law-search` 检索并回灌分析；
4. 需要沟通时用 `legal-visualization` 解释复杂关系；
5. 用 `legal-proposal-generator` 形成可交付方案，审定后再用 `md2word` 排版。

## 安装方法

下载并解压完整套件 ZIP，把其中 `skills/*` 复制到 Agent 的 Skills 根目录，然后按各成员 `SKILL.md` 配置依赖。也可以只下载成员表中的单个 Skill。

## 人工复核与使用边界

案件结论必须能够回溯到原始材料和有效法源。对时效、管辖、举证责任、证据能力、类案对位度和程序期限，应由承办律师逐项复核；任何“未提及”或“待补充”信息不得自动补写。

## 版本与许可证

当前套件版本为 `0.1.0`。套件外层文件按 [LICENSE.txt](LICENSE.txt) 的 CC BY-NC 4.0 授权；各成员 Skill 按其目录内 `LICENSE.txt` 分别授权。包含 MIT 成员不代表整套可忽略 CC BY-NC 条件，下载套件也不改变任何成员原有许可。
