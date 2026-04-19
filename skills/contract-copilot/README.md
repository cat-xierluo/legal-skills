# Contract Copilot

面向律师与法务的合同审查与起草 Skill，基于三层分析 + 四步流程，输出可直接交付的修订批注版和正式审查意见书。

> 让 AI 按照真实律师的审查习惯完成合同风险扫描、正文修订和意见书撰写，而不是只给一段笼统的文字建议。

## 关于作者

**杨卫薪律师** - 专注于技术类纠纷领域（知识产权、数据与 AI），同时热衷于将 AI 技术应用于法律实务。

欢迎添加微信交流（请注明来意）：

<div align="center">
  <img src="https://raw.githubusercontent.com/cat-xierluo/legal-skills/main/wechat-qr.jpg" width="200" alt="微信二维码"/>
  <p><em>微信：ywxlaw</em></p>
</div>

---

## 适合谁用

- 需要批量或高频审查合同的执业律师、法务
- 希望统一审查口径和交付格式的律所团队
- 对合同起草有专业要求但不希望从零开始的法务人员

## 典型场景

```text
用户：请站在甲方立场，以常规口径审查这份设计委托合同。
AI：好的，我先确认一下审查人信息……接下来我会按三层（交易结构、合同形式、条款语言）逐步扫描。
    完成后你会收到两个文件：修订批注一体版 .docx 和正式审查意见书 .docx。
```

## 它能产出什么

- **修订批注一体版** — 在 Word 中直接可见的修订痕迹与批注，可逐条接受或拒绝
- **正式审查意见书** — 符合律师交付习惯的结构化意见书（Word 格式）
- **合同起草信息清单** — 起草前的信息采集表，确保关键要素不遗漏

## 可以怎么用

- "请站在乙方立场，以克制口径审查这份租赁合同"
- "帮我把这份买卖合同的付款条款补齐"
- "按甲方视角审查，重点关注违约责任和解除条款"

## 使用边界

这个 skill 适合：

- 中文商业合同的常规审查与起草
- 需要统一交付格式的批量合同审查
- 12 类主要合同类型（买卖、租赁、服务、知识产权、担保、借贷、互联网协议、婚姻家事、劳动用工、房地产、建设工程、公司投资）

这个 skill 不适合：

- 非中文合同或涉外合同（未覆盖其他语言的法律语境）
- 替代律师的最终专业判断（输出应作为辅助意见，由律师复核后对外使用）
- 涉及行政审批、登记备案等需要线下操作的流程

## 当前覆盖范围

- 固定 12 类合同体系，每类下含多个具体合同类型的审查要点
- 支持甲方、乙方、中立三种审查立场
- 支持克制、常规、强势三种审查口径
- DOCX 原生批注与修订（不依赖人工复制粘贴）
- Word 审查意见书直出（含正式版式）
- 审查人配置与客户/立场/口径记忆

## 关联项目

更多法律专业 AI Skills，见 [legal-skills](https://github.com/cat-xierluo/legal-skills)：

- [litigation-analysis](https://github.com/cat-xierluo/legal-skills/tree/main/skills/litigation-analysis) — 诉讼案件分析
- [patent-analysis](https://github.com/cat-xierluo/legal-skills/tree/main/skills/patent-analysis) — 专利分析与侵权比对
- [trademark-assistant](https://github.com/cat-xierluo/legal-skills/tree/main/skills/trademark-assistant) — 商标申请辅助
- [opc-legal-counsel](https://github.com/cat-xierluo/legal-skills/tree/main/skills/opc-legal-counsel) — 一人公司常年法律顾问
- [legal-proposal-generator](https://github.com/cat-xierluo/legal-skills/tree/main/skills/legal-proposal-generator) — 法律服务方案生成
- [court-sms](https://github.com/cat-xierluo/legal-skills/tree/main/skills/court-sms) — 法院短信解析与案件管理
- [code2patent](https://github.com/cat-xierluo/legal-skills/tree/main/skills/code2patent) — 交底书转专利申请文件

## 许可证

本作品采用 [CC BY-NC 4.0](./LICENSE.txt) 许可证。如需商用授权，请联系微信 ywxlaw。
