# trademark-assistant

面向中国商标申请的类别规划、可注册性初筛和申请材料准备 skill。它基于尼斯分类、中国商标法律法规和审查规则，输出结构化风险分级、类别建议、商品清单和商标说明。

> 从“这个名字能不能注册、该选哪些类别”开始，把商标申请前最容易漏掉的信息和风险先整理清楚。

## 适合谁用

- 准备申请中国商标的企业、创业者和个人
- 需要快速做类别规划和可注册性初筛的律师、商标代理人和品牌负责人
- 已确定商标设计方案，需要准备商品清单和商标说明的人

## 典型场景

```text
用户：我想注册“星火”这个商标，做教育软件和在线课程，帮我看看能不能注册，需要选哪些类别。
AI：我会先收集申请主体、商标构成和使用场景，再做尼斯分类规划和可注册性初筛。
    输出包括类别建议、风险分级、待补充信息、免责声明和升级建议。
```

## 它能产出什么

- 商标咨询输入清单
- 按尼斯分类整理的类别规划表
- 可注册性初筛报告，包含高/中/低风险或“待补充”
- 商品清单，支持按官方导入模板生成 Excel
- 图形或组合商标的商标说明文本
- 免责声明、升级建议和需要专业律师/代理机构进一步核验的问题

## 当前覆盖范围

- 主要法域：中国大陆商标注册申请
- 分类依据：尼斯分类，当前默认使用 NCL13-2026，并保留 NCL12-2025 作为历史回溯
- 法律依据：《中华人民共和国商标法》《商标法实施条例》《商标审查审理指南》等中国法资料
- 交付格式：统一输出 Markdown 结构化结论；申请材料阶段可生成 Excel 商品清单

尼斯分类具有国际通用性，因此类别规划思路可作国际申请参考；但可注册性初筛、审查标准和法律判断仅面向中国商标申请。

## 安装方式

1. 打开本仓库的 GitHub Releases。
2. 下载最新版本的 skill 压缩包。
3. 解压后将 `trademark-assistant/` 文件夹放入你的 skill 目录。
4. 在支持 `SKILL.md` 的 Agent / Claude 环境中启用该 skill。

如需生成商品清单 Excel，安装依赖：

```bash
pip install openpyxl
```

## 可以怎么用

- “我想注册这个商标，请帮我做类别规划”
- “这个商标名用于教育软件，大概能不能注册？”
- “客户已经确定图形设计，请帮我写商标说明”
- “请基于第 9 类和第 41 类生成商品清单 Excel”

## 使用边界

这个 skill 适合：

- 中国商标申请前的类别规划
- 可注册性初步筛查和风险分级
- 申请材料中的商品清单和商标说明准备

这个 skill 不适合：

- 替代律师或商标代理机构出具正式法律意见
- 承诺商标注册成功率
- 处理复杂商标争议、异议、无效、撤三、驰名商标或跨类大规模冲突
- 在未检索官方数据库、未核验近似商标和申请主体事实时作最终判断

## 核心设计

### 先收集信息再判断

申请主体、商标构成、使用商品/服务、目标市场和设计稿都会影响结论。关键信息不足时，输出“待补充”，不强行评级。

### 类别规划与可注册性分开

尼斯分类解决“应该保护哪些商品/服务”，可注册性初筛解决“这个标识是否可能被驳回”。两者分开分析，再合并成行动建议。

### 材料准备可落地

客户确认设计方案后，可进一步生成商品清单和商标说明，用于申请材料准备，而不是停留在咨询建议。

## 关键文件

- [SKILL.md](./SKILL.md)：执行入口和输出要求
- [references/service-intake-checklist.md](./references/service-intake-checklist.md)：服务输入清单
- [references/classification-planning-guide.md](./references/classification-planning-guide.md)：类别规划规则
- [references/registrability-prescreen-guide.md](./references/registrability-prescreen-guide.md)：可注册性初筛规则
- [references/output-contract.md](./references/output-contract.md)：交付格式
- [references/trademark-description-guide.md](./references/trademark-description-guide.md)：商标说明撰写规则
- [templates/导入商品信息.xlsx](./templates/导入商品信息.xlsx)：商品清单导入模板

## 许可证

本作品采用 [CC BY-NC 4.0](./LICENSE.txt) 许可证。商用授权联系方式以 [LICENSE.txt](./LICENSE.txt) 为准。

## 关于作者 / 咨询与交流

杨卫薪律师（微信 ywxlaw）

如需就商标申请、类别规划、可注册性初筛、复杂商标问题、企业内部落地或商用授权进一步沟通，欢迎添加微信（请注明来意）。

<div align="center">
  <img src="https://raw.githubusercontent.com/cat-xierluo/legal-skills/main/wechat-qr.jpg" width="200" alt="微信二维码"/>
  <p><em>微信：ywxlaw</em></p>
</div>

## 关联项目

本仓库是 [Legal Skills](https://github.com/cat-xierluo/legal-skills) 的子项目。如果需要合同、商标、专利、OPC、小微企业合规、文档处理等更多法律类开源 Skill，可以关注主仓库。

相关项目：

- [opc-legal-counsel](https://github.com/cat-xierluo/legal-skills/tree/main/skills/opc-legal-counsel)：一人公司、AI 创业团队和小微企业法律顾问
- [contract-copilot](https://github.com/cat-xierluo/legal-skills/tree/main/skills/contract-copilot)：合同审查、起草和 Word 修订批注
- [patent-analysis](https://github.com/cat-xierluo/legal-skills/tree/main/skills/patent-analysis)：专利文件分析、侵权比对、FTO 和规避设计
