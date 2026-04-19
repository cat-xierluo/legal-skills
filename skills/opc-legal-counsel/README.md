# opc-legal-counsel

面向一人公司、单人创业者、AI 创业团队和一般小微企业的开源法律顾问 skill。  
它的目标不是输出一堆法律概念，而是把常见经营问题落成可执行的结论、风险提示和下一步动作。

## 这个项目解决什么问题

很多小微企业和一人公司不是完全没有法律需求，而是：

- 没有稳定法务支持
- 很难快速判断哪些是红线，哪些只是流程问题
- 知道“有风险”，但不知道今天应该先做什么
- 在公司治理、合同、税务、用工、AI 产品上线这些问题上容易边干边踩坑

`opc-legal-counsel` 试图解决的，就是这一层“轻量但高频”的法律支持。

它默认输出：

1. 一句话结论
2. 涉及领域
3. 关键事实缺口 / 当前假设
4. 红线风险与风险等级
5. 现在就做什么（24 小时内）
6. 接下来怎么做（7 天 / 30 天）
7. 何时必须升级给外部律师 / 会计师 / 专业机构
8. 法律依据与适用层级

## 适合谁用

- 一人有限公司创始人
- 单人创业者或小微企业负责人
- 早期 AI 产品创业团队
- 需要先做经营法律分诊，再决定是否升级专业服务的人

## 当前覆盖范围

### 小微企业基础盘

- 公司设立与主体形态选择
- 股权结构、联合创始人、代持、技术入股
- 合同审查、起草、履约与留痕
- 财税规范、收付款和发票风险
- 劳动用工、兼职、外包、保密与竞业
- 知识产权、数据合规、广告监管、争议应对

### OPC / AI 强化层

- 一人公司公私分离与股东责任风险
- 一人公司章程和重大事项留痕
- AI 产品上线、公示、标识、投诉处置
- AIGC 著作权、算法保护、模型与数据边界

### 成长阶段模块

- 融资分诊
- 顾问股 / 干股 / 期权 / 技术入股区分
- 早期股权激励与股权结构表风险

### 行业 overlay

- AI SaaS
- 电商
- 代运营 / 外包交付

## 核心设计

### 1. 双层定位

这个 skill 不是只回答 OPC 特殊问题，也不是泛化成普通企业法律百科。  
它采用的是：

**小微企业基础盘 + OPC / AI 强化层**

也就是说：

- 基础盘不能丢
- OPC 风险要优先强调
- AI 场景要单独补专项义务

### 2. 多领域路由

复杂问题通常不是单一法律问题，而是多个领域叠加：

- `governance`
- `tax`
- `contracts`
- `ai-compliance`
- `ip`
- `data-compliance`
- `regulatory`
- `employment`
- `disputes`

### 3. 分析引擎 + 下一跳协议

这个项目不试图把所有高频问题都写成固定 FAQ，而是把回答分成几层：

- 主 skill 负责分诊、综合判断和升级边界
- 核心领域文件负责分析方法
- 成长阶段模块负责融资 / 股权激励
- 行业 overlay 负责行业差异
- 地方资料只作为地域覆盖层
- 输出资产负责条款、清单和样稿

### 4. 全国基线 + 地方覆盖层

地方政策、地方扶持和地方办事流程只作为覆盖层使用。  
默认先回答全国基线，再在确实命中地域时叠加地方材料，避免把地方规则误答成全国统一规则。

## 可以怎么用

如果你把它作为 skill 接入支持 `SKILL.md` 的 agent 系统，可以直接问类似问题：

- “我是一个人做 AI SaaS，应该注册一人有限公司还是个体户？”
- “我先用个人微信收了公司业务款，现在怎么补救？”
- “客户给我的技术开发合同里验收条款太模糊，应该怎么改？”
- “AI 产品上线前至少要做哪些合规动作？”
- “我准备招第一个人，想先按顾问合作处理，会不会形成劳动关系？”

## 当前项目结构

```text
opc-legal-counsel/
├── SKILL.md
├── README.md
├── DISCLAIMER.md
├── CHANGELOG.md
├── DECISIONS.md
├── TASKS.md
├── LICENSE.txt
├── references/
│   ├── contracts.md
│   ├── governance.md
│   ├── growth-financing.md
│   ├── tax.md
│   ├── ai-compliance.md
│   ├── industry/
│   └── ...
├── assets/
│   ├── contract-clauses.md
│   ├── risk-checklist.md
│   ├── compliance-quick-ref.md
│   └── output-samples/
├── examples/
│   └── README.md
├── evals/
│   ├── README.md
│   └── evals.json
├── scripts/
│   └── check-evals.py
└── archive/
    └── 04-青岛OPC合规指引全文.md
```

## 关键文件

- [SKILL.md](./SKILL.md)：正式 skill 入口
- [references/growth-financing.md](./references/growth-financing.md)：成长阶段模块
- [references/industry/README.md](./references/industry/README.md)：行业 overlay 说明
- [evals/evals.json](./evals/evals.json)：当前回归样本
- [evals/manual-review.md](./evals/manual-review.md)：重点样本人工评分说明
- [evals/assertions.json](./evals/assertions.json)：重点样本机器可读断言
- [scripts/check-evals.py](./scripts/check-evals.py)：评测结构与回答断言检查脚本
- [assets/output-samples/README.md](./assets/output-samples/README.md)：标准输出样稿索引
- [examples/README.md](./examples/README.md)：公开示例问题索引
- [DISCLAIMER.md](./DISCLAIMER.md)：使用边界与免责声明

## 当前已经有的质量支撑

- 固定输出协议，避免“知道很多但说不清楚”
- 下一跳协议，明确什么时候走专项模块、行业 overlay、地方覆盖层和输出资产
- 首批 24 条评测样本，覆盖基础盘、强化层、成长阶段模块、行业 overlay 和跨领域升级场景
- 重点样本人工评分说明，用于判断回答是否真的做到综合分析、下一跳正确和升级边界正确
- 10 条重点样本的机器可读断言与纯标准库检查脚本，便于后续半自动回归
- 三套标准输出样稿：AI 上线、公私分离、合同审查
- 成长阶段模块：融资分诊、股权激励、顾问股 / 干股 / 期权区分
- 首批行业 overlay：AI SaaS、电商、代运营 / 外包交付
- 公开 examples 目录，方便外部访客快速理解实际回答形态
- 地方政策独立收拢，避免污染全国基线

## 当前仍在继续完善

- 基于真实回答结果校准机器可读断言
- 将评测脚本接入发布前检查或 CI
- 根据实际高频问题继续扩充标准输出样稿
- 更多城市 / 省份的地方覆盖层
- 更多行业场景包和公开示例
- 视实际使用频率增加合规体检问卷或问题分诊模板脚本

## 使用边界

这个项目适合做：

- 日常法律分诊
- 风险识别
- 合同审查的第一轮整理
- 公司治理和经营风险的动作化建议

这个项目不替代：

- 正式法律意见书
- 律师函
- 诉讼 / 仲裁代理
- 刑事、重大交易、跨境、高监管行业的深度专项服务

详见 [DISCLAIMER.md](./DISCLAIMER.md)。

## 许可证

本项目采用 `CC BY-NC 4.0`。详见 [LICENSE.txt](./LICENSE.txt)。

## 发布前检查

每次发布新版本前，运行以下命令确认元数据和版本一致性：

```bash
cd opc-legal-counsel
python3 scripts/check-evals.py
```

如果有真实回答文件，可以额外运行断言检查：

```bash
python3 scripts/check-evals.py --outputs-dir evals/outputs
```
