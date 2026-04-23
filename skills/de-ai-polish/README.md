# de-ai-polish

检测并去除中文文章里的 AI 化表述模式，让文章从“工整但假滑”回到更自然、更像真人写作的状态。

> 它不是简单同义改写，而是识别对比句式、空洞总结、排比堆砌、模板化转折和夸张语气，再决定删、合并还是重写。

## 典型场景

```text
用户：这篇文章读起来很 AI，帮我处理一下，但不要改掉我的核心观点。
AI：我会先扫描 AI 化表述模式，标出问题句，再按“删 / 合并 / 改写”处理。
    最后输出检测报告和修订后的自然版本。
```

写作流程完成初稿后，也应在输出给用户前调用本 skill 做最后一轮 AI 腔检查。

## 它能产出什么

- AI 化表述检测报告
- 问题句和问题类型标注
- 删、合并、改写三类处理建议
- 修订后的自然文本
- 质量评分和二次修订建议

## 当前覆盖范围

重点检测：

- “不是...而是...”等机械对比句
- “首先、其次、此外、综上所述”等程式化连接词
- “越来越、其实、往往、很多时候”等高频模板词
- 三项以上工整排比和虚假层次感
- “深入探讨、彰显、复杂性、格局”等 AI 词汇库
- 空洞意义拔高、模糊归因、公式化展望
- 过度粗体、表情符号和协作交流痕迹

## 安装方式

1. 打开本仓库的 GitHub Releases。
2. 下载最新版本的 skill 压缩包。
3. 解压后将 `de-ai-polish/` 文件夹放入你的 skill 目录。
4. 在支持 `SKILL.md` 的 Agent / Claude 环境中启用该 skill。

本 skill 不需要额外依赖。

## 可以怎么用

- “请检测这篇文章的 AI 腔，并给出修改建议”
- “直接把这篇文章改得自然一点，但保留原观点”
- “请只标注问题句，不要直接改正文”
- “文章准备发公众号，请最后过一遍 AI 化表达”

## 使用边界

这个 skill 适合：

- 中文文章、评论、公众号、报告、演讲稿的自然化润色
- 识别 AI 生成文本中常见的模板句式和空洞表达
- 在保留原观点的前提下提高文字节奏和人味

这个 skill 不适合：

- 英文文本或多语言翻译润色
- 把低质量内容改造成有事实深度的原创研究
- 删除必要的法律术语、技术术语或固定表达
- 代替作者判断观点是否准确、证据是否充分

## 核心设计

### 识别模板家族

AI 化表达常常换皮出现，不会完全匹配固定词表。skill 会把新表述向上归类到已知模板家族，再判断是否需要处理。

### 频次和相邻重复

单个词未必有问题，但短文中反复出现“其实、越来越、往往、看起来”等词，会形成明显机器感。相邻句重复同一结构也会被优先处理。

### 不机械替换

同一句问题可能适合删除、合并或改写。skill 不追求把每个模板换成另一个模板，而是根据上下文判断这句话是否还有独立价值。

## 关键文件

- [SKILL.md](./SKILL.md)：检测规则和执行入口
- [reference/expression-transformations.md](./reference/expression-transformations.md)：表达转换参考
- [reference/personal-style-guide.md](./reference/personal-style-guide.md)：个人风格保持规则
- [reference/quality-scoring.md](./reference/quality-scoring.md)：质量评分
- [reference/sentence-rhythm-guide.md](./reference/sentence-rhythm-guide.md)：句子节奏处理

## 许可证

本作品采用 [MIT](https://opensource.org/licenses/MIT) 许可证。

## 关于作者 / 咨询与交流

杨卫薪律师（微信 ywxlaw）

如需使用交流、企业内部落地、定制开发或商用授权，欢迎添加微信（请注明来意）。

<div align="center">
  <img src="https://raw.githubusercontent.com/cat-xierluo/legal-skills/main/wechat-qr.jpg" width="200" alt="微信二维码"/>
  <p><em>微信：ywxlaw</em></p>
</div>

## 关联项目

本仓库是 [Legal Skills](https://github.com/cat-xierluo/legal-skills) 的子项目。如果需要合同、商标、专利、OPC、小微企业合规、文档处理等更多法律类开源 Skill，可以关注主仓库。

相关项目：

- [md2word](https://github.com/cat-xierluo/legal-skills/tree/main/skills/md2word)：Markdown 转专业排版 Word 文档
- [legal-proposal-generator](https://github.com/cat-xierluo/legal-skills/tree/main/skills/legal-proposal-generator)：法律服务方案生成
- [contract-copilot](https://github.com/cat-xierluo/legal-skills/tree/main/skills/contract-copilot)：合同审查、起草和 Word 修订批注
