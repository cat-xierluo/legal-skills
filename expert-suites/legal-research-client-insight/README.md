# 法律研究与客户洞察专家套件

> [下载完整专家套件](https://github.com/cat-xierluo/legal-skills/releases/latest/download/suite-legal-research-client-insight-0.1.0.zip)
> 新增套件尚未发布；上方为下次 Release 的预留入口，发布前可下载通过 CI 后生成的 PR Preview 产物。成员独立下载以已发布资产为准，可能早于源码版本。

区分既有客户的高频增量触达与月季行业全景研究，把信息获取、法律核验、内容组织和文本规范放在一个轻量入口中。

本套件仅策展与分发，不提供运行时编排或套件入口 Skill。

## 适用场景

- 每日、每周或重大事件的客户相关法律信息筛选；
- 行业月报、季报及面向潜在客户的公开研究报告；
- 公众号材料获取、来源复核与研究文稿格式整理；

## 不适用场景

- 不替代单一企业尽调、具体客户法律意见或完整商业情报系统；
- 不自动发送微信、邮件、朋友圈或公众号，不承诺自动定时研究；
- 不将公众号观点、未核验案例或过期法源直接作为结论依据；

## 包含的 Skills

| Skill | 在本套件中的作用 | 单独下载 |
| :--- | :--- | :--- |
| [legal-client-brief](../../skills/legal-client-brief/) | 面向既有客户生成每日、每周或事件触发的增量简报草稿及渠道稿 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/legal-client-brief-1.1.0.zip) |
| [legal-industry-report](../../skills/legal-industry-report/) | 面向月度、季度研究形成正式行业报告待复核稿 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/legal-industry-report-1.1.0.zip) |
| [yuandian-law-search](../../skills/yuandian-law-search/) | 核验法规、政策与案例，形成可追溯研究依据 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/yuandian-law-search-1.10.0.zip) |
| [wechat-article-fetch](../../skills/wechat-article-fetch/) | 获取用户选定的公众号文章作为研究线索与材料 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/wechat-article-fetch-1.4.0.zip) |
| [legal-text-format](../../skills/legal-text-format/) | 规范法律文本的标点、层级和表达格式 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/legal-text-format-1.2.2.zip) |

## 建议使用方式

1. 先确认读者、行业、区域、信息窗口和交付目标：高频增量选 `legal-client-brief`，月季全景选 `legal-industry-report`；
2. 客户简报先完成本地报告配置、去标识化画像与信源白名单；没有有效增量时不凑条目；
3. 按需用 `wechat-article-fetch` 获取文章线索，再用官方来源、授权数据库和 `yuandian-law-search` 核验关键事实、案例与法源；
4. 按所选成员完成研究、出处登记及其内置校验，再按需用 `legal-text-format` 整理文本；格式调整后再次核对引用和事实；
5. 简报停在 `DRAFT`，行业报告停在 `PUBLIC_REVIEW`；律师审核后在套件之外另行执行获授权的发布；

## 安装方法

下载并解压套件 ZIP，把其中 `skills/*` 复制到 Agent 的 Skills 根目录；不要把套件外层目录当作单个 Skill 安装。发布前可下载通过 CI 后生成的 PR Preview 构建产物。也可按成员表单独安装。多个套件有同名成员时，先核对版本，避免旧包覆盖新版；源码符号链接不是跨平台安装包。

公众号抓取、联网检索和报告导出按各成员配置浏览器、Python 或渲染依赖及必要账号。`legal-visualization`、`md2word` 等额外图解/排版工具未打包，现有报告导出链路按成员说明使用。

## 人工复核与使用边界

客户画像只保留研究所需的行业、规模区间、业务阶段和风险主题。获取文章不等于获得再发布授权。检索记录需注明截止日、来源和待核事项；内容校验通过不等于法律准确性已获确认。套件没有调度器或自动发布能力。

## 版本与许可证

当前套件版本为 `0.1.0`，尚未完成真实业务端到端验证。套件本身不设独立许可证；各成员 Skill 按其目录内 `LICENSE.txt` 分别授权，下载或使用套件不改变成员原有许可条件。含 CC BY-NC 成员，不得把整套宣传为全部 MIT 或可自由商用。
