# priority-clauses

---

## 一、使用顺序

1. 先读 `review-framework.md`，确认宏观 / 中观 / 微观三层骨架。
2. 再读 `contract-routing.md`，确定合同归类和主文件入口。
3. 用本文件先抓高风险条款。
4. 进入 `contract-types/` 下对应主文件做条款级细审。
5. 最后结合 `revision-strategy.md` 决定每个问题是直接修订、局部删减、局部补入、整条重写，还是仅作批注。

---

## 二、12 类合同的优先审查顺序

| 类型 | 先看哪几组条款 | 对应主目录 |
|:---|:---|:---|
| 买卖合同 | 标的权属 -> 交付验收 -> 价款税费 -> 风险转移 -> 违约解除 | `references/contract-types/01-sale/` |
| 租赁合同 | 租赁物现状 -> 租期用途 -> 租金押金 -> 维修改造 -> 返还退出 | `references/contract-types/02-lease/` |
| 服务类合同 | 服务边界 -> 交付件/验收 -> 配合义务 -> 费用结算 -> 数据/IP -> 退出交接 | `references/contract-types/03-service/` |
| 知识产权类合同 | 权利链 -> 授权/转让范围 -> 成果归属 -> 交付与登记 -> 侵权处置 | `references/contract-types/04-ip/` |
| 担保类合同 | 主债权 -> 担保范围 -> 担保物状态 -> 设立生效 -> 实现路径 | `references/contract-types/05-guarantee/` |
| 借贷与赠与合同 | 金额/标的 -> 交付凭证 -> 利率或条件 -> 到期返还 -> 担保与提前到期 | `references/contract-types/06-lending-gift/` |
| 互联网协议 | 服务规则 -> 账号边界 -> 数据处理 -> 版本更新 -> 通知封禁 -> 争议解决 | `references/contract-types/07-internet/` |
| 婚姻家事类合同 | 身份关系 -> 财产范围 -> 债务承担 -> 抚养扶养 -> 生效程序 | `references/contract-types/08-marriage-family/` |
| 劳动用工类合同 | 用工类型 -> 岗位报酬 -> 社保考勤 -> 保密竞业 -> 解除交接 | `references/contract-types/09-employment/` |
| 房地产类合同 | 权属与状态 -> 审批程序 -> 价款税费 -> 交付过户 -> 开发建设义务 -> 退出 | `references/contract-types/10-real-estate/` |
| 建设工程类合同 | 工程范围 -> 工期节点 -> 计价结算 -> 变更签证 -> 质量安全 -> 保修争议 | `references/contract-types/11-construction/` |
| 公司投资类合同 | 交易结构 -> 先决条件 -> 交割文件 -> 陈述保证 -> 治理保护 -> 退出回购 | `references/contract-types/12-corporate-investment/` |

---

## 三、当前定位说明

- 本文件当前是“总控速查页”，先解决“先看什么”。
- 更细的分类型速查表，后续继续沉淀到本文件或各类型目录下。
- 如发现某类合同总是反复遗漏同一组高风险条款，优先回写到这里，而不是再增加新的零散导航文件。
