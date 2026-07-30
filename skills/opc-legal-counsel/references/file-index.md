# 文件路由

运行时按问题加载必要文件，不要整体读取。

## 核心领域

| 文件 | 业务判断重点 |
|---|---|
| `references/governance.md` | 主体选择、控制、公私分离和治理留痕 |
| `references/contracts.md` | 交易结构、交付、验收、付款、责任和退出 |
| `references/tax.md` | 业务、资金、票据、申报与专业协同 |
| `references/ai-compliance.md` | AI 产品角色、开放范围、模型与内容风险 |
| `references/data-compliance.md` | 数据角色、目的、权限、共享和事故响应 |
| `references/ip.md` | 权利来源、授权、成果归属、保护和投诉 |
| `references/employment.md` | 实际用工管理、报酬、成果和离职交接 |
| `references/regulatory.md` | 准入、宣传、交易公平和监管响应 |
| `references/disputes.md` | 请求、证据、期限、资产与程序策略 |

## 专项叠加

| 文件 | 何时加载 |
|---|---|
| `references/growth-financing.md` | 融资、顾问股、期权、技术入股、员工激励 |
| `references/industry-ai-saas.md` | AI SaaS 行业特性改变风险组合时 |
| `references/industry-ecommerce.md` | 电商平台、消费者和履约链条改变风险组合时 |
| `references/industry-agency-outsourcing.md` | 代运营、外包和多方交付链改变风险组合时 |

## 外部依据接口

| 文件 | 用途 |
|---|---|
| `references/legal-retrieval-protocol.md` | 生成工具中立的检索任务、验收来源、管理依据状态 |

本技能不内置国家政策背景、地方政策、地方办事流程、现行税率、名录或阶段性监管口径。涉及这些内容时，一律走外部检索协议。

## 输出资产

| 文件 | 用途 |
|---|---|
| `assets/contract-clauses.md` | 合同条款结构和谈判方向 |
| `assets/risk-checklist.md` | 经营法律风险自检 |
| `assets/template-ai-launch-report.md` | AI 产品上线核查输出骨架 |
| `assets/template-opc-separation-report.md` | 公私分离体检与补救输出骨架 |
| `assets/template-contract-review-report.md` | 合同审查意见输出骨架 |

## 示例与评测

- `examples/`：展示业务判断、检索任务和收口方式；
- `evals/evals.json`：代表性场景契约；
- `evals/assertions.json`：硬失败和软质量断言；
- `evals/manual-review.md`：人工评审标准；
- `scripts/check-evals.py`：结构检查、回答断言和故障注入自测。
