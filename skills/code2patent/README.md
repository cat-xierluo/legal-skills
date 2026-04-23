# code2patent

把已经开发完成的代码仓库，整理成专利代理师能继续起草和判断的交付材料：代码证据映射、技术交底书、权利要求布局卡，以及接近可申报版的中国发明专利初稿。

> 它解决的不是“把代码翻译成专利语言”，而是先把真实实现、技术效果和证据位置说清楚，再进入专利起草。

## 适合谁用

- 已有产品或代码项目，准备挖掘软件、算法、Agent 系统等技术方案的创业团队
- 需要把研发实现转交给专利代理师的技术负责人或知识产权负责人
- 希望先形成交底书、证据矩阵和权利要求布局，再决定是否正式申报的律师或代理师

## 典型场景

```text
用户：这是我们的代码仓库和三个候选专利点，请帮我整理成技术交底书，并标出每个技术特征对应的代码证据。
AI：我会先读 PRD、README 和候选清单，再盘点自研代码与第三方依赖边界。
    输出会包含方案-代码证据映射、技术交底书、权利要求布局卡和待研发确认事项。
```

如果用户还没有候选专利点，skill 会先进入“候选方案挖掘”模式，输出待人工筛选的候选清单；未经人工确认，不直接生成交底书或专利初稿。

## 它能产出什么

- 代码仓库边界与依赖画像
- 候选专利方案清单和优先级建议
- 方案、模块、函数、配置、数据流之间的证据映射表
- 发明专利技术交底书
- 权利要求布局卡与权利要求-代码证据矩阵
- 中国发明专利初稿，包括说明书、权利要求书草稿、摘要和自检表
- 待研发、代理师或申请主体补充确认的问题清单

## 当前覆盖范围

- 默认法域：中国发明专利
- 主要对象：已开发代码项目、软件系统、算法流程、Agent / AI 应用系统
- 默认写作链路：`代码证据映射 -> 技术交底书 -> 权利要求布局 -> 专利初稿 -> 自检`
- 主要依据：《专利审查指南》中与说明书、权利要求书、摘要撰写直接相关的规则，并结合计算机程序相关发明的保护主题要求

## 安装方式

1. 打开本仓库的 GitHub Releases。
2. 下载最新版本的 skill 压缩包。
3. 解压后将 `code2patent/` 文件夹放入你的 skill 目录。
4. 在支持 `SKILL.md` 的 Agent / Claude 环境中启用该 skill。

本 skill 不要求额外 Python 依赖。实际使用时，应让 Agent 能读取目标代码仓库、PRD、候选方案清单和客户模板。

## 可以怎么用

- “请读取这个代码仓库，围绕我列出的 3 个候选专利点生成技术交底书”
- “我还没有专利点，请先从代码里挖掘可能适合申请的技术方案”
- “请在交底书基础上继续生成权利要求布局卡和代码证据矩阵”
- “请输出一版中国发明专利初稿，并列出需要代理师确认的问题”

## 使用边界

这个 skill 适合：

- 从真实代码实现中抽取可追溯的技术证据
- 帮研发、企业知识产权人员和专利代理师建立协作底稿
- 在证据充分时起草接近可申报版的中国发明专利初稿

这个 skill 不适合：

- 替代专利代理师完成最终申请文件定稿
- 在没有代码、PRD、方案说明或技术效果信息时直接编造创新点
- 对专利授权前景、稳定性、侵权风险作最终法律判断
- 处理非中国法域的专利申请文件，除非另行提供当地规则和模板

## 核心设计

### 证据优先

每个技术特征都尽量回勾到代码文件、函数、配置、数据结构或调用链。证据不足的内容会标注为“待确认”，避免把未实现内容写进申请材料。

### 两步起草

不直接从交底书跳到完整专利初稿，而是先生成权利要求布局卡和证据矩阵，再扩展为说明书、权利要求书草稿和摘要。这样更方便代理师调整保护范围。

### 人工筛选闸门

自动挖掘候选方案时，先让人筛选、合并、拆分或排序；确认方向后才进入定向检索和起草，降低跑偏风险。

## 关键文件

- [SKILL.md](./SKILL.md)：执行入口和完整流程规则
- [references/project-analysis-spec.md](./references/project-analysis-spec.md)：项目结构与依赖分析规范
- [references/code-extraction-spec.md](./references/code-extraction-spec.md)：代码证据抽取和证据分级规则
- [references/patent-drafting-quick-reference.md](./references/patent-drafting-quick-reference.md)：发明专利起草速查卡
- [templates/](./templates/)：交底书、权利要求布局、证据矩阵、初稿和自检模板

## 许可证

本作品采用 [CC BY-NC 4.0](./LICENSE.txt) 许可证。商用授权联系方式以 [LICENSE.txt](./LICENSE.txt) 为准。

## 关于作者 / 咨询与交流

杨卫薪律师（微信 ywxlaw）

如需就代码挖掘专利点、技术交底书、发明专利初稿、企业内部落地或商用授权进一步沟通，欢迎添加微信（请注明来意）。

<div align="center">
  <img src="https://raw.githubusercontent.com/cat-xierluo/legal-skills/main/wechat-qr.jpg" width="200" alt="微信二维码"/>
  <p><em>微信：ywxlaw</em></p>
</div>

## 关联项目

本仓库是 [Legal Skills](https://github.com/cat-xierluo/legal-skills) 的子项目。如果需要合同、商标、专利、OPC、小微企业合规、文档处理等更多法律类开源 Skill，可以关注主仓库。

相关项目：

- [patent-analysis](https://github.com/cat-xierluo/legal-skills/tree/main/skills/patent-analysis)：专利文件分析、侵权比对、FTO 和规避设计
- [contract-copilot](https://github.com/cat-xierluo/legal-skills/tree/main/skills/contract-copilot)：合同审查、起草和 Word 修订批注
- [opc-legal-counsel](https://github.com/cat-xierluo/legal-skills/tree/main/skills/opc-legal-counsel)：一人公司、AI 创业团队和小微企业法律顾问
