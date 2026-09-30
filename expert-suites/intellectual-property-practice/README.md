# 知识产权实务专家套件

> [下载完整专家套件](https://github.com/cat-xierluo/legal-skills/releases/latest/download/suite-intellectual-property-practice-0.1.0.zip)
> 新增套件尚未发布；上方为下次 Release 的预留入口，发布前可下载通过 CI 后生成的 PR Preview 产物。成员独立下载以已发布资产为准，可能早于源码版本。

把仓库的专利与商标特色能力放在同一下载集合中，提供两个清晰入口：专利材料与初步分析、商标申请辅助。套件名称不表示覆盖知识产权全领域或全生命周期。

本套件仅策展与分发，不提供运行时编排或套件入口 Skill。

## 适用场景

- 专利全文获取，以及中国发明、实用新型的权利要求解释、产品比对与风险初步分析；
- 在材料、检索及法律状态基线充分时开展 FTO、规避设计等初步分析；
- 中国商标申请前的类别规划、可注册性初筛及商品清单、商标说明准备；

## 不适用场景

- 不覆盖著作权、商业秘密等全部知识产权领域，也不是全流程代理服务；
- 不把发明/实用新型的方法用于外观设计近似判断；外观设计需专门方法及人工复核；
- 不承担复杂商标争议、异议无效或侵权诉讼的完整办理，不承诺注册成功率；
- 不自动提交专利或商标申请，也不替代专利律师、专利代理师或商标专业人员的正式意见；

## 包含的 Skills

| Skill | 在本套件中的作用 | 单独下载 |
| :--- | :--- | :--- |
| [patent-download](../../skills/patent-download/) | 按专利号获取专利全文与基础材料 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/patent-download-2.7.1.zip) |
| [patent-analysis](../../skills/patent-analysis/) | 对中国发明和实用新型进行权利要求、产品比对及风险初步分析 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/patent-analysis-2.2.0.zip) |
| [trademark-assistant](../../skills/trademark-assistant/) | 中国商标申请的类别规划、可注册性初筛和申请材料准备 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/trademark-assistant-1.7.2.zip) |
| [yuandian-law-search](../../skills/yuandian-law-search/) | 按基准日核验相关法源、规则与案例 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/yuandian-law-search-1.10.0.zip) |
| [legal-visualization](../../skills/legal-visualization/) | 把已核验的技术特征、权利关系或申请安排转成沟通图解 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/legal-visualization-0.8.2.zip) |

## 建议使用方式

1. 专利入口：用 `patent-download` 获取全文并核对专利号、文本版本与文件完整性；下载成功不代表法律状态或有效权利要求已核实；
2. 交给 `patent-analysis` 前确认法域、基准日、类型、有效权利要求、法律状态及产品/方法版本；缺少关键材料时只列缺口，不给确定性评级；
3. 商标入口：用 `trademark-assistant` 确认申请主体、主营业务、拟申请标识与目标类别；先规划和初筛，方案确认后再准备申请材料；
4. 两个入口分别按任务用 `yuandian-law-search` 核验现行规则与时点。商标相对理由需官方检索证据；专利 FTO 需完整检索范围、实施行为和状态基线，不能以下载代替检索；
5. 需要沟通图时用 `legal-visualization` 呈现已核验内容，并明确待证、推断与缺口；由专业人员复核后另行决定申报、诉讼、交易或产品决策；

## 安装方法

下载并解压套件 ZIP，把其中 `skills/*` 复制到 Agent 的 Skills 根目录；不要把套件外层目录当作单个 Skill 安装。发布前可下载通过 CI 后生成的 PR Preview 构建产物。也可按成员表单独安装。多个套件有同名成员时，先核对版本，避免旧包覆盖新版；源码符号链接不是跨平台安装包。

专利下载平台、浏览器和法律数据库按成员说明配置；部分通道依赖用户账号或额外软件。账号和客户材料只按授权使用，不保存到公开源码；安装套件不附带数据库访问权。

## 人工复核与使用边界

专利与商标是并列入口，不强制串联。`patent-analysis` 当前范围以中国发明和实用新型为主；其他法域需重新核验适用规则。图解不能扩大原分析结论。`code2patent`、`legal-case-analysis` 等未打包，本套件不据此承诺专利撰写或完整知识产权诉讼流程。

## 版本与许可证

当前套件版本为 `0.1.0`，尚未完成真实业务端到端验证。套件本身不设独立许可证；各成员 Skill 按其目录内 `LICENSE.txt` 分别授权，下载或使用套件不改变成员原有许可条件。含 CC BY-NC 成员，不得把整套宣传为全部 MIT 或可自由商用。
