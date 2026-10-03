# 合同审查与小微企业顾问专家套件

> 整套源码 v0.1.0 待首次发布（尚无公开下载）

面向合同起草、审查及 OPC / 小微企业日常经营分诊。按任务选择合同入口或经营入口，不要求每次调用全部成员。

本套件仅策展与分发，不提供运行时编排或套件入口 Skill。

## 适用场景

- 签约前审查、谈判修订，以及具备必要背景的新合同起草；
- OPC / 小微企业的主体隔离、合同履行、用工、数据与知识产权等联动风险初步判断；
- 履约出现争议后整理材料、核验依据并形成沟通方案；

## 不适用场景

- 不将小微企业分诊宣传为覆盖所有企业的专项合规、并购尽调或财税服务；
- 不替代正式法律意见、专业税务判断、代理签约或诉讼文书提交；
- 不在审查立场、目的或口径缺失时自行作出实质审查结论；

## 包含的 Skills

| Skill | 在本套件中的作用 | 单独下载 |
| :--- | :--- | :--- |
| [contract-copilot](../../skills/contract-copilot/) | 合同起草、风险审查、DOCX 批注修订与审查意见书 | [已发布 v1.6.3](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/contract-copilot-1.6.3.zip) |
| [opc-legal-counsel](../../skills/opc-legal-counsel/) | OPC 与小微企业经营问题分诊、联动风险和行动优先级 | [已发布 v1.0.2](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/opc-legal-counsel-1.0.2.zip) |
| [legal-case-analysis](../../skills/legal-case-analysis/) | 对已出现的履约争议梳理事实、证据与争点 | [已发布 v1.0.0](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/legal-case-analysis-1.0.0.zip) |
| [yuandian-law-search](../../skills/yuandian-law-search/) | 核验现行法、监管规则与正反类案，回填检索依据 | [已发布 v1.10.0](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/yuandian-law-search-1.10.0.zip) |
| [legal-proposal-generator](../../skills/legal-proposal-generator/) | 将已核验的分析整理为咨询、沟通或服务方案 | [已发布 v0.4.1](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/legal-proposal-generator-0.4.1.zip) |
| [legal-ocr](../../skills/legal-ocr/) | 把扫描合同及附件转成可读文本，保留原件供核对 | [已发布 v1.6.0](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/legal-ocr-1.6.0.zip) |

## 建议使用方式

1. 先区分入口：具体合同用 `contract-copilot`；经营问题用 `opc-legal-counsel`，先确认主体、目标、地域、时间和材料缺口；
2. 扫描件先用 `legal-ocr` 转换并与原件核对；合同任务确认审查立场、目的、口径后再进入实质审查；
3. 涉及现行规则时用 `yuandian-law-search` 核验；出现争议时按需用 `legal-case-analysis` 整理事实—证据—争点，不把每次合同审查都转成诉讼分析；
4. 合同 DOCX 交付沿用 `contract-copilot` 自有文件链路；需要独立咨询或服务方案时再用 `legal-proposal-generator`；
5. 律师复核修改内容、法源、商业取舍及文件版本后，按用户授权交付；

## 安装方法

下载并解压套件 ZIP，把其中 `skills/*` 复制到 Agent 的 Skills 根目录；不要把套件外层目录当作单个 Skill 安装。发布前可下载通过 CI 后生成的 PR Preview 构建产物。也可按成员表单独安装。多个套件有同名成员时，先核对版本，避免旧包覆盖新版；源码符号链接不是跨平台安装包。

按所用成员配置 OCR、DOCX 文件处理依赖和法律检索渠道。检索工具或账号需用户另行提供；扫描文本不能替代原件。

## 人工复核与使用边界

合同助手已能生成修订版与审查意见书 DOCX，不需要强制再经过 Markdown 转 Word。`md2word`、`legal-visualization` 未打入本套件，仅在另有排版或复杂交易图需求时单独选用。原始合同、OCR 文本和修订结果需交叉核对；现行规则无法核验时保留待核项，不冒充正式意见。

## 版本与许可证

当前套件版本为 `0.1.0`，尚未完成真实业务端到端验证。套件本身不设独立许可证；各成员 Skill 按其目录内 `LICENSE.txt` 分别授权，下载或使用套件不改变成员原有许可条件。含 CC BY-NC 成员，不得把整套宣传为全部 MIT 或可自由商用。
