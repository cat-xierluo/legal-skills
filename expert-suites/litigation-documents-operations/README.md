# 诉讼文书与案件推进专家套件

> [下载完整专家套件](https://github.com/cat-xierluo/legal-skills/releases/latest/download/suite-litigation-documents-operations-0.1.0.zip)

用于把已完成的案件研判继续转化为起诉、答辩、裁判分析、上诉再审决策和客户沟通材料，并维持案件目录与法院来文衔接。

## 适用场景

- 生成或改造要素式起诉状、答辩和诉讼方案；
- 分析判决书、庭审材料并评估上诉或再审路径；
- 把案件进展整理成律师内部工作稿或客户交付文件。

## 不适用场景

- 不代替律师签发、提交或发送文书；
- 不自动操作法院系统或承诺程序结果；
- 不在缺少事实和证据基础时直接套用文书模板。

## 包含的 Skills

| Skill | 在本套件中的作用 | 单独下载 |
| :--- | :--- | :--- |
| [elements-complaint-generator](../../skills/elements-complaint-generator/) | 把常规起诉状转成官方要素式示范文本结构 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/elements-complaint-generator-0.15.0.zip) |
| [litigation-analysis](../../skills/litigation-analysis/) | 深度分析裁判、庭审和上诉再审可行性 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/litigation-analysis-1.4.0.zip) |
| [legal-proposal-generator](../../skills/legal-proposal-generator/) | 生成诉讼方案、沟通报告和结案汇报 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/legal-proposal-generator-0.3.2.zip) |
| [md2word](../../skills/md2word/) | 输出符合中文专业排版的 Word 文档 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/md2word-1.3.6.zip) |
| [legal-case-analysis](../../skills/legal-case-analysis/) | 为文书起草持续提供事实、证据和争点底稿 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/legal-case-analysis-1.0.0.zip) |
| [yuandian-law-search](../../skills/yuandian-law-search/) | 对文书中的法律依据和类案进行复核 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/yuandian-law-search-1.8.9.zip) |
| [new-case](../../skills/new-case/) | 维持案件目录、基本信息和期限结构 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/new-case-1.4.0.zip) |
| [court-sms](../../skills/court-sms/) | 获取法院文书并归档最新程序材料 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/court-sms-1.5.1.zip) |
| [legal-visualization](../../skills/legal-visualization/) | 制作庭审路线、证据矩阵和客户沟通图 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/legal-visualization-0.8.2.zip) |

## 建议使用方式

1. 用 `new-case` 和 `court-sms` 保持案件结构与来文同步；
2. 以 `legal-case-analysis` 的工作底稿为基础，用 `yuandian-law-search` 核验依据；
3. 按任务选择 `elements-complaint-generator`、`litigation-analysis` 或 `legal-proposal-generator`；
4. 需要解释复杂结构时调用 `legal-visualization`；
5. 经律师逐段审定后，再用 `md2word` 生成正式版。

## 安装方法

下载并解压完整套件 ZIP，把其中 `skills/*` 复制到 Agent 的 Skills 根目录，然后按成员 `SKILL.md` 配置环境。单一文书任务也可以只下载对应成员 Skill。

## 人工复核与使用边界

文书中的主体、请求、金额、案号、期限、证据编号、引文和程序选择必须逐项复核。套件不执行提交、发送、签章或案件状态写回；对外文件只能在律师确认后使用。

## 版本与许可证

当前套件版本为 `0.1.0`。套件外层文件按 [LICENSE.txt](LICENSE.txt) 的 CC BY-NC 4.0 授权；各成员 Skill 按其目录内 `LICENSE.txt` 分别授权。下载或使用套件不改变成员原有许可条件。
