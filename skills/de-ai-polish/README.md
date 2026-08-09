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
- 有作者样本时的 voice profile 与匹配检查
- 无样本时的 `cleanup_only` 最小清理，不强加默认人设
- 功能性列举保护、分析型例证关系层、隐藏列表与修复伪影复扫
- 跨节重复语义骨架复检，以及 VoiceAnchor 新增长连续重合门禁
- 原有二级、三级标题及编号的逐行保护，不把正文润色扩大成目录重写
- Markdown 图片整行保护快照与最终门禁证据
- 质量评分和二次修订建议

## 当前覆盖范围

重点检测：

- “不是...而是...”等机械对比句
- “首先、其次、此外、综上所述”等程式化连接词
- “越来越、其实、往往、很多时候”等高频模板词
- 修辞性排比、隐藏列表、假排名和固定短句节拍
- 五层、五种、步骤、清单等功能性列举的误伤保护
- 多个例子被逐项扩成同构段落，以及换词后仍重复的能力—边界骨架
- “深入探讨、彰显、复杂性、格局”等 AI 词汇库
- 空洞意义拔高、模糊归因、公式化展望
- 过度粗体、表情符号和协作交流痕迹
- 有作者样本时的 Voice Calibration：提取句长、词选、段落开头、标点、过渡、观点密度和语气倾向

## 安装方式

本 skill 通过 legal-skills monorepo + subtree 独立仓库两种渠道分发：

- **monorepo**：从 `cat-xierluo/legal-skills` 仓库直接使用或复制 `skills/de-ai-polish/`。
- **subtree 独立仓库**：独立远程仓库 `https://github.com/cat-xierluo/de-ai-polish.skill.git` 含完整 skill 目录，可直接 clone 或作为 subtree 加到你的项目。子仓库与 monorepo 同步发布，子仓库为镜像，权威入口以 monorepo 为准（`homepage` 指向主仓库）。

不需要手动下载 Releases 压缩包(本 skill 不发布该形式)。

本 skill 不需要额外依赖。

## 可以怎么用

- “请检测这篇文章的 AI 腔，并给出修改建议”
- “直接把这篇文章改得自然一点，但保留原观点”
- “请只标注问题句，不要直接改正文”
- “文章准备发公众号，请最后过一遍 AI 化表达”
- “参考这段我自己的文章，改得更像我的表达，但不要复制原句”

## 使用边界

这个 skill 适合：

- 中文文章、评论、公众号、报告、演讲稿的自然化润色
- 识别 AI 生成文本中常见的模板句式和空洞表达
- 在保留原观点的前提下提高文字节奏和人味

这个 skill 不适合：

- 英文文本或多语言翻译润色
- 把低质量内容改造成有事实深度的原创研究
- 在作者没有提供材料时编造经历、感受或立场变化
- 删除必要的法律术语、技术术语或固定表达
- 代替作者判断观点是否准确、证据是否充分
- 未经确认使用第三方私人写作样本
- 冒充某位作者本人，或复制样本原句、独有比喻、私人事实
- 调整二级、三级标题的文字、层级、编号或文章导航；这属于 WeChat Article Writer 等写作流程

## 核心设计

### 识别模板家族

AI 化表达常常换皮出现，不会完全匹配固定词表。skill 会把新表述向上归类到已知模板家族，再判断是否需要处理。

### 频次和相邻重复

单个词未必有问题，但短文中反复出现“其实、越来越、往往、看起来”等词，会形成明显机器感。相邻句重复同一结构也会被优先处理。

### 不机械替换

同一句问题可能适合删除、合并或改写。skill 不追求把每个模板换成另一个模板，而是根据上下文判断这句话是否还有独立价值。

### Voice Calibration

无样本时只做 `cleanup_only`，不再套默认第一人称、比喻、口语和短句配方。用户提供样本或明确选择本机私有 anchor 时，skill 会从句长、词选、段落动力、认识来源和不确定性等十个维度提取 voice profile。它只学习稳定特征，不冒充作者身份、不复制样本原句、不把样本事实写进目标文本。

本机 anchor 放在 `assets/local-voice-anchors/`，目录由项目 `.gitignore` 排除。目录内的 `config.json` 可登记多个命名 anchor，并以 `default_voice_anchor_id` 指定本机缺省项；该缺省只在用户已经选择 `local_anchor` 模式时生效，不会把普通清理自动改成个人声音。公共 Skill 只提供读取协议，不收录个人样本、作者 profile 或 anchor 注册表；本机文件不存在时不得假装已经完成 voice 校准。

启用样本后，`scripts/voice_anchor_copy_gate.py` 会比较源稿、最终稿与样本，只阻断改写后新出现的长连续重合。默认结果只给出位置、长度和片段哈希，不把私有样本文字写进日志。它不能替代人工检查同义复刻、结构模仿和事实泄漏。

### 功能性列举与分析型例证

Skill 不再把所有多项目结构都当成需要保护的清单。分类、步骤、责任分配以及读者需要逐项执行或核对的内容继续保留；几个例子若只用于共同证明一个判断，则按源稿已有的条件、相互作用、冲突、时间、审查或责任关系组织。源稿没有关系材料时宁可压缩列举，也不虚构场景。

每组关系写入正文前必须填写候选外的“关系证据卡”，除两端各自的源稿锚点外，还要提供“关系本身”的原文锚点：同一处原文必须同时提到两端，或明确用同一个具体变量约束两端。A 与 B 各自有材料，不证明 A 与 B 之间有关系；不得以专业常识补出时间顺序、程序路径或共同目标。若关系本身没有锚点，Skill 保留两项各自成立或压缩列举，并标记 `AUTHOR_MATERIAL_NEEDED`。Voice 校准同样不得把源稿的保留、可能性和未知升级成更强裁断或普遍频率。

证据卡的结论只约束处理方式，不进入读者正文。成稿不得解释“按源稿导航”“源稿材料不足”“这不是若干项检查任务”或其他编辑现场信息；材料不足时直接保留独立例子或压缩表达，补料标记只写在报告里。

“都属于风险、都要结合具体合作、都需要判断、都发生在履行或偏离阶段”不构成关系证据。只有源稿明确共享同一个具体变量，或一端会改变另一端的解释、效果、顺序时，才可据此组织承接。一组真实关系已经足够，不为段落好看继续配对。

标题承诺的“五层、五种”等导航结构仍受保护。上述关系层只发生在正文内部，不会生成新的二级或三级标题。

改写前还会建立候选外的“论证脊柱账本”，逐项记录源稿中不能被上位总结替代的区分、因果中间环节、例外、比较、风险分布和放大因素。每项必须在最终稿找到落点；“法律风险更高”不能代替“危险为何集中于中间层、哪些因素继续放大风险”。这道人工门禁用来阻止去 AI 过程把作者的论证压成一份干净摘要。

### 修复伪影复扫

改写后单独检查：显式序号是否被换成“最典型、最容易、也容易”等假排名；分析型例证是否被逐项扩成同功能段落；关系层是否偷用了源稿外专业常识或宽泛伪关系；候选外的“源稿、导航、证据不足、扫描、交付”是否泄漏进读者正文；是否从旧禁词逃到新口癖；是否把重复压成短金句；入口／门槛／内部空间图式是否跨三段复用；是否强加第一人称或虚构经历。已知的假排名、过程泄漏、框架启动语、压缩金句和空间隐喻重复由 `scripts/style_regression_gate.py` 兜底，“工具能力—限制—人的判断／责任”家族由 `scripts/semantic_repetition_gate.py` 扩大召回。

语义门禁把原始召回与硬计数分开：紧跟“第 N 层／种／步”导航的功能性说明全部报告，但不进入普通正文删除配额；普通正文全文最多 6 个、单节最多 2 个、相邻同功能候选最多 1 个，最后一节最多 1 个。功能性导航若仍用同一句人类接管结论逐项收束，人工复扫仍应处理。门禁不能靠删掉具体对象、条件和后果来通过，否则正文会变成干净但失去作者判断过程的分类摘要。

正文分析中识别出的临时分组不会自动变成小标题。Skill 默认逐行保留源稿全部 Markdown 标题，不新增、删除、改名、升降级或重排；标题本身的写作与层级调整交给 WeChat Article Writer。隐藏列表只能在既有标题框架内通过正文合并、承接或因果重组处理。

### 交付门禁

改写前先为 Markdown 图片所在整行生成 manifest，最终交付前由独立 checker 比较原文、顺序、数量和 hash。任何图片行删除、移动或改写都会阻断交付；用户明确授权变更后也必须重新建立基线，不得绕过 checker。

Protected Span 只绑定真正需要逐字、逐次数保留的内容。全文主题词和反复出现的核心概念保留名称与必要定义即可，不锁死出现次数；若误选导致精炼稿需要机械补词，应废弃候选并从只读源稿重建快照，而不是恢复重复。

图片门禁通过后，最终文本还需通过自然度、节奏感、专业度、个性度、精炼度评分。五维各 0-2 分并直接相加；机器阈值集中在 `config/quality-score-rubric.json`，并随场景、Protected Spans 一同绑定到候选 manifest/receipt，防止任务中途换尺。有作者样本时，还要检查是否匹配 voice profile。门禁证明步骤和阈值确已执行，但不把主观分数伪装成独立质量真值。

## 关键文件

- [SKILL.md](./SKILL.md)：检测规则和执行入口
- [references/expression-transformations.md](./references/expression-transformations.md)：表达转换参考
- [references/pollution-patterns.md](./references/pollution-patterns.md)：AI 化表达模式与假阳性边界
- [references/personal-style-guide.md](./references/personal-style-guide.md)：作者证据卡与十维 Voice Calibration
- `assets/local-voice-anchors/`：本机私有 VoiceAnchor 注册表与样本目录（由 `.gitignore` 排除，不属于公开 Skill）
- [references/quality-scoring.md](./references/quality-scoring.md)：质量评分和 voice profile 门禁
- [references/sentence-rhythm-guide.md](./references/sentence-rhythm-guide.md)：句子节奏处理
- [scripts/protected_markdown_gate.py](./scripts/protected_markdown_gate.py)：图片整行快照与最终主动门禁
- [scripts/heading_preservation_gate.py](./scripts/heading_preservation_gate.py)：Markdown 标题整行快照与结构越界门禁
- [scripts/delivery_gate.py](./scripts/delivery_gate.py)：场景、Protected Spans 和评分回执的候选绑定门禁
- [scripts/style_regression_gate.py](./scripts/style_regression_gate.py)：隐藏列表与假排名的已知回归门禁
- [scripts/semantic_repetition_gate.py](./scripts/semantic_repetition_gate.py)：能力—边界重复语义骨架启发式复检
- [scripts/voice_anchor_copy_gate.py](./scripts/voice_anchor_copy_gate.py)：相对源稿新出现的 VoiceAnchor 长连续重合门禁
- [config/quality-score-rubric.json](./config/quality-score-rubric.json)：五维范围、求和方式和硬阈值的机器可执行单点真相
- [config/instruction-stability-contract.json](./config/instruction-stability-contract.json)：约束、checker 和回归样本映射

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
