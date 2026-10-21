# 诉讼文书与案件推进专家套件

> [下载已发布套件（0.1.0）](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/suite-litigation-documents-operations-0.1.0.zip)
> 整套源码 v0.1.2 待发布
> 上方旧包内容不随源码变化。

用于把已完成的案件研判继续转化为起诉、答辩、裁判分析、上诉再审决策和客户沟通材料，并维持案件目录与法院来文衔接。

## 适用场景

- 生成或改造要素式起诉状、答辩和诉讼方案；
- 独立解读一份判决，或按另一综合研判入口分析庭审、评估上诉再审；
- 把案件进展整理成律师内部工作稿或客户交付文件。

## 不适用场景

- 不代替律师签发、提交或发送文书；
- 不自动操作法院系统或承诺程序结果；
- 不在缺少事实和证据基础时直接套用文书模板。

## 包含的 Skills

| Skill | 在本套件中的作用 | 单独下载 |
| :--- | :--- | :--- |
| [elements-complaint-generator](../../skills/elements-complaint-generator/) | 把常规起诉状转成官方要素式示范文本结构；源码 v0.16.1 待发布 | [已发布 v0.16.0](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/elements-complaint-generator-0.16.0.zip) |
| [judgment-analysis](../../skills/judgment-analysis/) | 单份判决的事实认定、裁判理由与主文深析（由 `litigation-analysis` 更名）；源码 v2.0.0 待发布 | 尚无公开下载 |
| [legal-proposal-generator](../../skills/legal-proposal-generator/) | 生成诉讼方案、沟通报告和结案汇报 | [已发布 v0.4.1](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/legal-proposal-generator-0.4.1.zip) |
| [md2word](../../skills/md2word/) | 输出符合中文专业排版的 Word 文档 | [已发布 v1.3.8](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/md2word-1.3.8.zip) |
| [legal-case-analysis](../../skills/legal-case-analysis/) | 主导综合研判、庭审复盘与上诉再审判断；源码 v1.1.2 待发布 | [已发布 v1.0.0](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/legal-case-analysis-1.0.0.zip) |
| [yuandian-law-search](../../skills/yuandian-law-search/) | 对文书中的法律依据和类案进行复核；源码 v1.10.1 待发布 | [已发布 v1.10.0](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/yuandian-law-search-1.10.0.zip) |
| [new-case](../../skills/new-case/) | 维持案件目录、基本信息和期限结构 | [已发布 v1.5.0](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/new-case-1.5.0.zip) |
| [court-sms](../../skills/court-sms/) | 获取法院文书并归档最新程序材料；源码 v1.5.3 待发布 | [已发布 v1.5.1](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/court-sms-1.5.1.zip) |
| [legal-visualization](../../skills/legal-visualization/) | 制作庭审路线、证据矩阵和客户沟通图 | [已发布 v0.8.2](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/legal-visualization-0.8.2.zip) |

## 历史包

旧名 [litigation-analysis v1.4.0](https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.30/litigation-analysis-1.4.0.zip) 仍可下载；该历史包不包含 `judgment-analysis` 更名后的内容。

## 建议使用方式

按用户目标选择主入口，不要求顺序调用全部成员：

| 用户要完成的事 | 主入口与完成边界 |
|---|---|
| “读懂这份判决，分析法院的理由” | `judgment-analysis` 单独完成，不要求先读卷宗或做法律检索 |
| “根据判决和新证据，判断是否上诉” | `legal-case-analysis` 主导；复用判决节点成果，再组织检索和综合论证 |
| “复盘庭审、整理质证和庭后待办” | `legal-case-analysis` 按需加载庭审参考；单纯整理不强制生成全案报告 |
| “把已写好的起诉状转成要素式文本” | `elements-complaint-generator` |
| “把已有判断写成服务方案或结案汇报” | `legal-proposal-generator`；缺实质判断时先完成研判 |

`new-case`、`court-sms` 按需维护材料；需要法源时用 `yuandian-law-search`，需要图解或正式排版时再使用对应工具。判决节点交接原文位置、争点、文内疑点与未核事项，综合研判复用这些成果，不重复生成同一份判决报告。

以上为当前源码职责；下载链接仍指向旧发布包，旧包不包含本次解耦。

## 安装方法

下载并解压完整套件 ZIP，把其中 `skills/*` 复制到 Agent 的 Skills 根目录，然后按成员 `SKILL.md` 配置环境。单一文书任务也可以只下载对应成员 Skill。

## 人工复核与使用边界

文书中的主体、请求、金额、案号、期限、证据编号、引文和程序选择必须逐项复核。套件不执行提交、发送、签章或案件状态写回；对外文件只能在律师确认后使用。

## 版本与许可证

当前套件版本为 `0.1.2`。套件本身不设独立许可证；各成员 Skill 按其目录内 `LICENSE.txt` 分别授权，下载或使用套件不改变成员原有许可条件。
