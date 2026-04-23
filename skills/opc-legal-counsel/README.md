# opc-legal-counsel

面向一人公司、单人创业者、AI 创业团队和小微企业的常年法律顾问 skill。它把公司治理、合同、财税、用工、AI 产品上线、数据与知识产权合规等经营问题，整理成可执行的风险提示和行动清单。

> 它不追求把法律概念讲全，而是帮助创始人判断：今天哪里是红线，缺什么事实，先做哪几件事，什么时候必须升级给律师或会计师。

## 适合谁用

- 一人有限公司、个体创业者和小微企业负责人
- 技术背景创始人、早期 AI 应用创业团队
- 还没有稳定法务支持，但需要日常经营法律分诊的人
- 律师或顾问团队，用于把高频咨询整理成稳定回答框架

## 典型场景

```text
用户：我一个人做 AI SaaS，现在先用个人微信收了客户款，后面准备注册一人公司，有什么风险？现在怎么补救？
AI：我会先判断公司阶段、资金路径和业务类型，再按公私分离、税务、合同、AI 合规等领域拆解。
    输出包括一句话结论、关键事实缺口、红线风险、24 小时/7 天/30 天行动和升级边界。
```

## 它能产出什么

- 一句话结论和风险等级
- 关键事实缺口与当前假设
- 红线风险和可能后果
- 24 小时、7 天、30 天行动清单
- 合同、股权、税务、用工、AI 合规等多领域联动判断
- 必须升级给律师、会计师、税务师或专业机构的边界
- 可复用的风险清单、条款建议和标准输出样稿

## 当前覆盖范围

### 小微企业基础盘

- 公司设立与主体形态选择
- 股权结构、联合创始人、代持、技术入股
- 合同审查、起草、履约和证据留痕
- 财税规范、收付款路径和发票风险
- 劳动用工、兼职、外包、保密和竞业
- 知识产权、数据合规、广告监管和争议应对

### OPC / AI 强化层

- 一人公司公私分离和股东责任风险
- 一人公司章程、重大事项决议和内部留痕
- AI 产品上线、公示、标识、投诉处置
- AIGC 著作权、算法保护、模型与数据边界

### 成长阶段与行业场景

- 融资分诊、顾问股、干股、期权、技术入股
- AI SaaS、电商、代运营/外包交付等行业 overlay
- 地方政策以“全国基线 + 地方覆盖层”方式处理

## 安装方式

1. 打开本仓库的 GitHub Releases。
2. 下载最新版本的 skill 压缩包。
3. 解压后将 `opc-legal-counsel/` 文件夹放入你的 skill 目录。
4. 在支持 `SKILL.md` 的 Agent / Claude 环境中启用该 skill。

如需运行评测检查脚本，本地需有 Python 3：

```bash
python3 scripts/check-evals.py
```

## 可以怎么用

- “我是一个人做 AI SaaS，注册一人有限公司还是个体户更合适？”
- “我把公司业务款收到了个人微信，现在怎么补救？”
- “客户给我的技术开发合同验收条款很模糊，应该怎么改？”
- “AI 产品上线前至少要做哪些合规动作？”
- “我准备招第一个人，先按顾问合作处理会不会形成劳动关系？”

## 使用边界

这个 skill 适合：

- 日常经营法律分诊
- 风险识别和优先级排序
- 第一轮合同、股权、税务、用工和 AI 合规问题整理
- 判断何时需要升级给专业人员

这个 skill 不适合：

- 替代正式法律意见书、律师函、诉讼或仲裁代理
- 处理刑事、跨境、金融、医疗、证券等高监管深度专项问题
- 在缺少地域、主体、合同、资金流水或产品事实时直接下最终结论
- 代替会计师、税务师或行政机关完成申报、登记、备案等流程

## 核心设计

### 双层定位

先保留小微企业基础盘，再叠加 OPC 和 AI 专项层。这样既不会把一人公司问题讲成普通公司百科，也不会忽略普通经营风险。

### 多领域路由

一个问题通常同时涉及治理、合同、税务、用工、知识产权、数据、监管和争议解决。skill 会先识别主矛盾，再调用对应领域文件。

### 下一跳协议

主 skill 负责分诊和综合判断；核心领域文件负责分析方法；成长阶段、行业 overlay、地方覆盖层和输出资产按需加载，避免把地方规则误答成全国统一规则。

## 质量支撑

- 固定输出协议，避免回答只有概念没有动作
- 24 条评测样本，覆盖基础盘、OPC/AI 强化层、成长阶段和跨领域场景
- 重点样本人工评分说明和机器可读断言
- `scripts/check-evals.py` 可检查评测样本结构和部分回答断言
- 三套标准输出样稿：AI 上线、公私分离、合同审查
- 公开 examples，帮助外部访客理解实际回答形态

## 关键文件

- [SKILL.md](./SKILL.md)：执行入口和输出协议
- [references/file-index.md](./references/file-index.md)：完整文件索引
- [references/governance.md](./references/governance.md)：公司治理与 OPC 风险
- [references/ai-compliance.md](./references/ai-compliance.md)：AI 产品上线合规
- [references/growth-financing.md](./references/growth-financing.md)：成长阶段、融资和股权安排
- [assets/risk-checklist.md](./assets/risk-checklist.md)：风险清单资产
- [examples/](./examples/)：公开示例问题
- [evals/](./evals/)：评测样本与断言

## 许可证

本作品采用 [CC BY-NC 4.0](./LICENSE.txt) 许可证。商用授权联系方式以 [LICENSE.txt](./LICENSE.txt) 为准。

## 关于作者 / 咨询与交流

杨卫薪律师（微信 ywxlaw）

如需就一人公司、小微企业经营、AI 产品合规、合同治理、复杂法律问题、企业内部落地或商用授权进一步沟通，欢迎添加微信（请注明来意）。

<div align="center">
  <img src="https://raw.githubusercontent.com/cat-xierluo/legal-skills/main/wechat-qr.jpg" width="200" alt="微信二维码"/>
  <p><em>微信：ywxlaw</em></p>
</div>

## 关联项目

本仓库是 [Legal Skills](https://github.com/cat-xierluo/legal-skills) 的子项目。如果需要合同、商标、专利、OPC、小微企业合规、文档处理等更多法律类开源 Skill，可以关注主仓库。

相关项目：

- [contract-copilot](https://github.com/cat-xierluo/legal-skills/tree/main/skills/contract-copilot)：合同审查、起草和 Word 修订批注
- [trademark-assistant](https://github.com/cat-xierluo/legal-skills/tree/main/skills/trademark-assistant)：商标类别规划、可注册性初筛和申请材料准备
- [patent-analysis](https://github.com/cat-xierluo/legal-skills/tree/main/skills/patent-analysis)：专利文件分析、侵权比对、FTO 和规避设计
- [code2patent](https://github.com/cat-xierluo/legal-skills/tree/main/skills/code2patent)：从代码仓库整理专利交底书和发明专利初稿
