# Contract Copilot

面向律师、法务和合同高频处理团队的合同审查与起草 skill。它按“交易结构、合同形式、条款语言”三层扫描合同，并输出可执行的风险清单、修订批注版和正式审查意见书。

> 目标不是给一段笼统建议，而是把风险定位、修改动作、推荐措辞和交付文档一次整理清楚。

## 适合谁用

- 需要高频审查中文商业合同的律师、法务和律所团队
- 希望统一审查口径、风险分级和 Word 交付格式的团队
- 需要从零起草合同，并先固定交易文件包、程序前提和待补事实的人

## 典型场景

```text
用户：请站在乙方立场，以常规口径审查这份设计委托合同，重点关注验收、付款和违约责任。
AI：我会先确认审查立场和口径，再按交易结构、合同形式、条款语言三层扫描。
    交付物包括审查报告，以及带修订和批注的 Word 文件。
```

## 它能产出什么

- 风险清单：风险等级、后果、判别标准、相关条款、整改建议
- 推荐措辞：可直接谈判或落入合同正文的条款文本
- 审查报告：可签结论、先决事项、谈判优先级和复核要点
- Word 修订批注版：在 `.docx` 中直接显示修改痕迹和批注
- 起草工作台：主合同类型、配套协议、必带附件、待补事实和条款骨架

## 当前覆盖范围

固定覆盖 12 类中文合同：

- 买卖、租赁、服务、知识产权
- 担保、借贷与赠与、互联网协议、婚姻家事
- 劳动用工、房地产、建设工程、公司投资

支持：

- 甲方、乙方、中立等审查立场
- 克制、常规、强势等审查口径
- 仅批注、直接修订、批注与修订结合等落痕策略
- DOCX 原生批注、修订和 Word 审查意见书输出

## 安装方式

1. 打开本仓库的 GitHub Releases。
2. 下载最新版本的 skill 压缩包。
3. 解压后将 `contract-copilot/` 文件夹放入你的 skill 目录。
4. 在支持 `SKILL.md` 的 Agent / Claude 环境中启用该 skill。
5. 如需生成 Word 批注、修订或报告，安装脚本依赖：

```bash
pip install -r scripts/requirements.txt
```

首次生成审查文件时，按 Agent 提示确认审查人姓名和机构；配置会写入本地 `config/`，不会作为公开发布内容使用。

## 可以怎么用

- “站在甲方立场，以强势口径审查这份买卖合同”
- “帮我把服务合同里的验收、付款和违约责任条款补齐”
- “请输出审查报告，并把确定性问题直接修订进 Word”
- “我要起草一份技术开发合同，请先列起草信息清单和待确认问题”

## 使用边界

这个 skill 适合：

- 中文商业合同的常规审查、起草和交付格式统一
- 批量合同的一轮风险扫描和修订底稿生成
- 律师或法务复核前的结构化整理

这个 skill 不适合：

- 替代律师对重大交易作最终签署意见
- 处理未提供事实背景、交易安排或业务目标的合同
- 覆盖所有涉外法域、外文合同和高监管行业专项审查
- 自动完成需要线下审批、登记、备案或主体授权核验的事项

## 核心设计

### 分层四步审查

先看交易结构，再看合同形式，最后看条款语言。每个风险点都尽量落到“能否签、如何改、谁来确认、优先级如何”的动作上。

### 分析与文档操作分工

Agent 负责识别风险、形成审查计划和推荐措辞；脚本负责在 DOCX 中稳定写入批注、修订和报告，减少复制粘贴导致的格式错误。

### 记忆但不静默代填

本地配置可记住审查人、客户和审查口径，但新环境或缺少关键身份信息时仍会要求确认，避免把历史配置误用到正式交付。

## 关键文件

- [SKILL.md](./SKILL.md)：执行入口和合同审查规则
- [references/review-framework.md](./references/review-framework.md)：通用审查框架
- [references/contract-routing.md](./references/contract-routing.md)：12 类合同路由
- [references/priority-clauses.md](./references/priority-clauses.md)：高风险条款入口
- [references/revision-strategy.md](./references/revision-strategy.md)：批注与修订策略
- [scripts/README.md](./scripts/README.md)：DOCX 自动化脚本说明

## 许可证

本作品采用 [CC BY-NC 4.0](./LICENSE.txt) 许可证。商用授权联系方式以 [LICENSE.txt](./LICENSE.txt) 为准。

## 关于作者 / 咨询与交流

杨卫薪律师（微信 ywxlaw）

如需就合同审查、合同起草、企业内部合同流程落地、复杂法律问题或商用授权进一步沟通，欢迎添加微信（请注明来意）。

<div align="center">
  <img src="https://raw.githubusercontent.com/cat-xierluo/legal-skills/main/wechat-qr.jpg" width="200" alt="微信二维码"/>
  <p><em>微信：ywxlaw</em></p>
</div>

## 关联项目

本仓库是 [Legal Skills](https://github.com/cat-xierluo/legal-skills) 的子项目。如果需要合同、商标、专利、OPC、小微企业合规、文档处理等更多法律类开源 Skill，可以关注主仓库。

相关项目：

- [opc-legal-counsel](https://github.com/cat-xierluo/legal-skills/tree/main/skills/opc-legal-counsel)：一人公司、AI 创业团队和小微企业法律顾问
- [trademark-assistant](https://github.com/cat-xierluo/legal-skills/tree/main/skills/trademark-assistant)：商标类别规划、可注册性初筛和申请材料准备
- [patent-analysis](https://github.com/cat-xierluo/legal-skills/tree/main/skills/patent-analysis)：专利文件分析、侵权比对、FTO 和规避设计
- [md2word](https://github.com/cat-xierluo/legal-skills/tree/main/skills/md2word)：Markdown 转专业排版 Word 文档
