# opc-legal-counsel

面向一人公司、单人创业者、AI 创业团队和小微企业的法律业务分诊 skill。它帮助用户识别经营主矛盾、联动风险、行动优先级和专业升级边界，并把需要现行规则支撑的命题交给外部法律数据库、MCP 或官方来源核验。

> 这个 skill 沉淀的是律师处理经营问题的判断方法，不是法规、政策和地方办事资料的离线副本。

## v1.0 的核心变化

- 从“内置知识 + 地方覆盖层”重构为“业务判断内核 + 工具中立检索协议”；
- 移除国家政策背景、地方政策、注册流程和静态法源登记表；
- 现行法条、期限、税率、名录、地方口径和平台规则必须外部核验；
- 引入五种依据状态和 fail-closed 收口，检索不可用或来源冲突时不输出精确规则结论；
- 重写九个领域参考文件、模板、示例和评测契约，降低过期知识对回答的污染。

## 适合谁用

- 一人有限公司、个体创业者和小微企业负责人；
- 技术背景创始人和早期 AI 应用团队；
- 还没有完整法务体系，需要日常经营法律分诊的团队；
- 希望把专业检索能力与稳定业务判断组合使用的律师或顾问团队。

## 能解决什么

- 主体选择、公私分离、联合创始人和股权安排；
- 合同结构、履约、验收、付款、责任和退出；
- 资金票据链、税务风险识别与专业协同；
- AI 产品、数据、知识产权、用工和监管风险；
- 投诉、催收、事故与监管联系的第一轮处置；
- 融资、顾问股、期权、技术入股和行业场景分诊。

## 工作方式

1. 区分法律主体 OPC 与经营模式 OPC；
2. 补齐地域、时间、主体、角色、交易链和用户目标；
3. 识别主领域和联动领域，形成业务风险判断；
4. 将精确规则命题写成结构化检索请求；
5. 使用当前环境可用的法律数据库、MCP 或官方来源取得依据；
6. 用依据状态收口结论，给出止损、补救、证据和升级清单。

检索接口不绑定某个 MCP。更换法律数据库或运行环境时，只要返回字段满足 `references/legal-retrieval-protocol.md`，业务判断层无需重写。

## 依据状态

- `VERIFIED_CURRENT`：来源字段完整，且确认当前有效；
- `VERIFIED_AS_OF_DATE`：只确认在指定日期有效；
- `NEEDS_RETRIEVAL`：已定义待证命题，来源仍不足；
- `CONFLICTING_SOURCES`：来源在效力、时间、地域或口径上冲突；
- `RETRIEVAL_UNAVAILABLE`：当前没有可靠检索能力。

没有可靠来源时，skill 仍可给出业务判断、临时动作和检索清单，但不会编造法条、期限、税率、政策条件或地方办理结论。

## 典型用法

- “我和联合创始人还没签协议，代码和客户资源怎么换股？”
- “公司款收到了个人微信，怎样止损和整理材料？”
- “客户合同没有验收和变更机制，谈判重点是什么？”
- “AI 客服接入客户工单，上线前要判断和检索哪些问题？”
- “现在没有法律数据库，能否先给我最新税率和地方材料清单？”
- “官方文件、地方指南和窗口说法冲突时，怎样收口？”

## 不适合

- 代替正式法律意见、律师函、诉讼或仲裁代理；
- 代替会计师、税务师完成计算和申报；
- 在没有外部检索能力时提供“最新法规答案”；
- 代替深度合同批注、商标申请、专利分析等专项能力；
- 直接用于法院、监管、交易文件或其他需正式专业签署的场景。

## 关键文件

- [SKILL.md](./SKILL.md)：运行时入口、判断流程和输出协议；
- [references/legal-retrieval-protocol.md](./references/legal-retrieval-protocol.md)：外部检索请求、结果验收和状态管理；
- [references/file-index.md](./references/file-index.md)：按问题加载的文件路由；
- [assets/risk-checklist.md](./assets/risk-checklist.md)：经营风险自检；
- [examples/](./examples/)：业务判断与检索收口示例；
- [evals/evals.json](./evals/evals.json)：12 条代表性业务、检索与故障场景；
- [evals/manual-review.md](./evals/manual-review.md)：人工评审和硬失败标准。

## 评测维护

脚本仅使用 Python 标准库：

```bash
python3 scripts/check-evals.py --self-test
```

检查外部生成的回答：

```bash
python3 scripts/check-evals.py --outputs-dir /path/to/answers
```

机器断言只能验证结构和部分硬边界，不能证明法律结论正确或来源真实。未进行无旧上下文的真实 Agent 运行与人工复核时，行为稳定性状态为 `NOT_VERIFIED`。

## 许可证

本作品采用 [CC BY-NC 4.0](./LICENSE.txt) 许可证。商用授权联系方式以 [LICENSE.txt](./LICENSE.txt) 为准。

## 作者与交流

杨卫薪律师（微信 ywxlaw）

<div align="center">
  <img src="https://raw.githubusercontent.com/cat-xierluo/legal-skills/main/wechat-qr.jpg" width="200" alt="微信二维码"/>
  <p><em>微信：ywxlaw</em></p>
</div>

本 skill 属于 [Legal Skills](https://github.com/cat-xierluo/legal-skills) 项目。需要深度合同、商标、专利或法律文档处理时，可组合相应专项 skill。
