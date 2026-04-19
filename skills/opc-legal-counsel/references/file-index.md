# 文件清单

本文件列出 `opc-legal-counsel` 技能的全部资料文件，供维护时快速查找。运行时无需整体加载。

## OPC 地方资料

| 文件 | 说明 |
|------|------|
| `references/local-policies/opc-使用说明.md` | 地方 OPC 资料目录与加载说明 |
| `references/local-policies/opc-国家政策背景.md` | OPC 政策背景（含省级政策：省-市-区-街道三级体系） |
| `references/local-policies/opc-公司注册流程.md` | 江苏 / 苏州注册流程参考 |
| `references/local-policies/opc-青岛OPC合规指引.md` | 青岛指引框架摘要 |
| `references/local-policies/opc-青岛指引-结构化摘录.md` | 清洗后的可直接引用摘要 |
| `references/local-policies/opc-姑苏区专项政策.md` | 姑苏区200万奖励、沧浪街道赋能平台、OPC创业人才贷 |
| `archive/04-青岛OPC合规指引全文.md` | 原始 OCR 归档，默认不直接加载 |

## 核心领域

| 文件 | 说明 |
|------|------|
| `references/contracts.md` | 合同审查、起草、履约与留痕 |
| `references/governance.md` | 组织形式、章程、公私分离、治理 |
| `references/tax.md` | 发票、股东借款、税务红线 |
| `references/ai-compliance.md` | AI 产品上线、标识、公示、备案 / 登记核验 |
| `references/ip.md` | AIGC 著作权、算法保护、商标、商业秘密 |
| `references/data-compliance.md` | 个人信息、隐私政策、SDK、数据出境 |
| `references/regulatory.md` | 广告、反不正当竞争、许可、监管检查 |
| `references/employment.md` | 劳动关系、兼职、竞业限制 |
| `references/disputes.md` | 证据、时效、诉讼 / 仲裁应对 |

## 成长阶段模块

| 文件 | 说明 |
|------|------|
| `references/growth-financing.md` | 成长阶段专项模块：融资分诊、股权激励、顾问股 / 干股 / 期权 / 技术入股分析框架 |

## 行业 overlay

| 文件 | 说明 |
|------|------|
| `references/industry-ai-saas.md` | AI SaaS 场景包 |
| `references/industry-ecommerce.md` | 电商场景包 |
| `references/industry-agency-outsourcing.md` | 代运营 / 外包交付场景包 |

## 输出资产

| 文件 | 说明 |
|------|------|
| `assets/contract-clauses.md` | 合同条款库 |
| `assets/risk-checklist.md` | 企业法律风险自检清单 |
| `assets/template-ai-launch-report.md` | AI 产品上线核查模板 |
| `assets/template-opc-separation-report.md` | 公私分离体检 / 补救模板 |
| `assets/template-contract-review-report.md` | 合同审查意见模板 |

## 公开示例

| 文件 | 说明 |
|------|------|
| `examples/01-联合创始人股权与技术入股.md` | 联合创始人 / 技术入股示例 |
| `examples/02-公私混同补救.md` | 公私混同补救示例 |
| `examples/03-AI功能上线检查.md` | AI 功能上线示例 |

## 评测样本

- `evals/evals.json`：24 条回归样本，按 `foundation`（基础盘）和 `reinforcement`（OPC/AI 强化层）分组
- 当前样本重点验证：多领域路由、固定输出协议、地方覆盖层触发、下一跳协议、样稿映射和升级边界判断
- `evals/manual-review.md`：10 条重点样本的人工评分说明和硬失败条件
- `evals/assertions.json`：10 条重点样本的机器可读断言，共 40 条关键词 / 禁用表述检查
- `scripts/check-evals.py`：纯标准库评测检查脚本，可校验样本结构、路径存在性，并可选检查回答文件
