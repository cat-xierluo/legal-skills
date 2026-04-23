# patent-analysis

系统化分析专利文件，支持技术特征提取、权利要求拆解、侵权比对、稳定性分析、FTO、规避设计和专利价值评估。

> 给一份专利和一个产品方案，先拆权利要求，再逐项比对技术特征，最后输出结构化风险判断和待核验事项。

## 适合谁用

- 需要快速理解专利保护范围的律师、专利代理师和企业知识产权人员
- 需要初步评估产品侵权风险或 FTO 风险的研发、产品和法务团队
- 需要把专利分析材料整理成报告底稿的争议解决或交易支持团队

## 典型场景

```text
用户：请分析这件专利和我们产品的侵权风险，产品资料在这个文件夹里。
AI：我会先拆解独立权利要求的技术特征，再逐项比对产品方案。
    结论会区分字面覆盖、等同风险、缺失特征、从属权利要求稳定性和待补证据。
```

## 它能产出什么

- 单专利技术要点提取报告
- 多专利保护范围比对报告
- 产品-专利侵权比对表
- 专利稳定性或无效风险分析
- FTO 风险初筛报告
- 规避设计建议
- 专利价值评估底稿

## 当前覆盖范围

内置 7 个分析场景：

| 场景 | 适用问题 | 模板 |
|------|----------|------|
| 单专利技术要点提取 | 快速理解保护范围 | `references/01-single-patent-summary.md` |
| 多专利比对分析 | 比较专利组合差异 | `references/02-multi-patent-comparison.md` |
| 产品-专利侵权比对 | 判断产品是否落入保护范围 | `references/03-infringement-comparison.md` |
| 专利稳定性/无效分析 | 评估被无效风险 | `references/04-validity-analysis.md` |
| FTO 分析 | 产品上市前风险初筛 | `references/05-fto-analysis.md` |
| 规避设计分析 | 设计绕开方案 | `references/06-design-around.md` |
| 专利价值评估 | 交易、融资、许可支持 | `references/07-patent-valuation.md` |

## 安装方式

1. 打开本仓库的 GitHub Releases。
2. 下载最新版本的 skill 压缩包。
3. 解压后将 `patent-analysis/` 文件夹放入你的 skill 目录。
4. 在支持 `SKILL.md` 的 Agent / Claude 环境中启用该 skill。

本 skill 不含专利下载或 OCR 能力。PDF 扫描件应先转换为可读文本或 Markdown。

## 可以怎么用

- “请提取这件专利的独立权利要求技术特征”
- “请比较这三件专利的保护范围差异”
- “请把我们的产品方案与权利要求 1 做侵权比对”
- “请评估这件专利的稳定性和可能的无效理由”
- “请给出规避设计方向，但不要直接给最终法律意见”

## 使用边界

这个 skill 适合：

- 专利文件的结构化阅读和初步分析
- 侵权比对、FTO 和规避设计的底稿整理
- 帮助团队识别需要律师、代理师或技术人员进一步确认的问题

这个 skill 不适合：

- 替代专利律师或专利代理师出具正式法律意见
- 在未核验专利法律状态、权利人、同族、审查历史和现有技术时作最终结论
- 独立完成无效宣告、诉讼策略或跨国专利争议评估
- 只凭摘要判断保护范围；分析必须回到权利要求书和说明书

## 核心设计

### 权利要求优先

专利保护范围以权利要求为准，摘要只能辅助理解。侵权比对先看独立权利要求，再评估从属权利要求对稳定性的影响。

### 特征逐项比对

不直接给“侵权/不侵权”的跳跃结论，而是先拆解技术特征，再标注产品中对应结构、缺失点、等同风险和证据来源。

### 关键事实核验

产出法律文书或正式意见前，必须核对专利权人、专利状态、保护期限、权利要求有效性和相关程序历史。

## 许可证

本作品采用 [CC BY-NC-SA 4.0](./LICENSE.txt) 许可证。商用授权联系方式以 [LICENSE.txt](./LICENSE.txt) 为准。

## 关于作者 / 咨询与交流

杨卫薪律师（微信 ywxlaw）

如需就专利侵权比对、FTO、规避设计、专利价值评估、复杂法律问题、企业内部落地或商用授权进一步沟通，欢迎添加微信（请注明来意）。

<div align="center">
  <img src="https://raw.githubusercontent.com/cat-xierluo/legal-skills/main/wechat-qr.jpg" width="200" alt="微信二维码"/>
  <p><em>微信：ywxlaw</em></p>
</div>

## 关联项目

本仓库是 [Legal Skills](https://github.com/cat-xierluo/legal-skills) 的子项目。如果需要合同、商标、专利、OPC、小微企业合规、文档处理等更多法律类开源 Skill，可以关注主仓库。

相关项目：

- [code2patent](https://github.com/cat-xierluo/legal-skills/tree/main/skills/code2patent)：从代码仓库整理专利交底书和发明专利初稿
- [contract-copilot](https://github.com/cat-xierluo/legal-skills/tree/main/skills/contract-copilot)：合同审查、起草和 Word 修订批注
- [trademark-assistant](https://github.com/cat-xierluo/legal-skills/tree/main/skills/trademark-assistant)：商标类别规划、可注册性初筛和申请材料准备
