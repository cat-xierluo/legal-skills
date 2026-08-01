## 👨‍💼 关于作者与合作

**杨卫薪律师** - 专注于技术类纠纷领域（知识产权、数据与 AI），同时持续探索 AI 技术在法律实务中的真实应用。

我正在探索法律领域的 FDE（Forward Deployed Engineer）协作模式：深入真实法律业务场景，在法律专业判断与 AI 工程实现之间搭桥，把具体问题转化为可运行、可验证、可持续迭代的 AI 工作流和解决方案。

如果你也在思考如何将 AI 真正应用到法律业务中，欢迎联系交流，一起探索法律 FDE 的合作方式。添加微信时可备注「法律 FDE」。

如需交流 Skill 使用，或获取标注「非商用」许可证的 Skill 商业授权，也可以通过下方微信联系（见下方说明）：

<details>
<summary>📚 许可证说明</summary>

本项目采用两种许可证：

| 许可证             | 说明                                                         | 示例技能                                                          |
| :----------------- | :----------------------------------------------------------- | :---------------------------------------------------------------- |
| **MIT**      | 可自由使用，包括商用，但需保留署名                           | wechat-article-fetch、mineru-ocr、md2word 等                      |
| **CC-BY-NC** | 可自由使用，但**不可商用**，且需保留署名             | litigation-analysis、patent-analysis、legal-proposal-generator 等 |

> 💡 如需将技能用于商业目的，请添加微信（ywxlaw）联系授权

</details>

<div align="center">
  <img src="docs/wechat-qr.jpg" width="200" alt="微信二维码"/>
  <p><em>微信：ywxlaw</em></p>
</div>

---

<details>
<summary>🆕 最近更新的 Skill</summary>

| 日期       | 类型   | Skill                                                                 | 版本    | 更新要点                                                                                                                                                                                                                                       |
| :--------- | :----- | :-------------------------------------------------------------------- | :------ | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-07-30 | 正式发布 | [opc-legal-counsel](skills/opc-legal-counsel/)                       | v1.0.0  | 从内置法规与地方政策重构为法律业务判断内核和工具中立检索协议；移除动态政策资料，引入五种依据状态、检索失败收口和硬失败不可抵消的评测门禁 |
| 2026-07-30 | 更新   | [patent-analysis](skills/patent-analysis/)                             | v2.1.2  | 新增覆盖十个场景的代表性提示词、hard/soft 机器断言和独立校验器；侵权、规避、等同及无效样本锁定无网页链接的多条款法源与证据停止门禁 |
| 2026-07-30 | 更新   | [trademark-assistant](skills/trademark-assistant/)                     | v1.7.2  | 修复 NCL13 消防车跨类残留、风险等级合成冲突与商标说明错误口径；收紧 Excel 输入校验，新增关键迁移回归检查和单元测试，并改为仅向用户确认目录保存客户材料 |
| 2026-07-30 | 更新   | [skill-lint](skills/skill-lint/)                                       | v2.6.2  | 稳定性合同兼容顶层 `version` 与官方 `metadata.version`，并对双位置版本冲突保持 fail-closed，避免合法发布候选被误报为身份缺失 |
| 2026-07-30 | 更新   | [project-init](skills/project-init/)                                   | v1.2.4  | TASKS 改为流动的当前任务入口；移除归档索引并禁止创建 before 快照，历史分别归入 CHANGELOG 与 DECISIONS                                                        |
| 2026-07-30 | 更新   | [trademark-assistant](skills/trademark-assistant/)                     | v1.7.1  | references 顺序编号与法规独立子目录：5 份流程文件加 `NN-` 前缀按执行顺序排列、侵权判断标准迁入 `references/laws-regulations/`、脚本归位到 `scripts/`、删除冗余索引并把图像理解工具改为按环境能力分档的选择策略（不再写死具体工具名）                                                                                                       |
| 2026-07-28 | 更新   | [trademark-assistant](skills/trademark-assistant/)                     | v1.7.0  | 尼斯分类 NCL13-2026 内容差别补齐：清除 class-09 消防车迁移残留、class-03 标题与注释同步至 NCL13（香水/加香精油）                                                                                                                               |
| 2026-07-28 | 更新   | [trademark-assistant](skills/trademark-assistant/)                     | v1.6.0  | 硬缺陷 + 法律口径修复：落地可运行的商品清单脚本、修复 NCL13 眼镜迁移残留、输入清单补官方检索证据字段；修正商标说明口径与误导模板、服务主体表述加合规边界、可注册性拆绝对/相对理由并加未检索不可评级门禁                                        |

</details>

## 📋 项目概述

本项目旨在沉淀并分发面向法律工作者的 AI Agent Skills。法律从业者兼具专业工作者与创作者的双重身份——既要处理法律业务，也需要撰写专业文章、整理资料、分享知识。我们的技能围绕这一特点，构建完整的工作流支持。

### 技能体系

我们的技能覆盖法律工作者的核心工作场景：

1. **内容获取** - 从多种来源收集和转换研究资料

   - 微信公众号文章抓取、OCR 识别、语音转文字
2. **内容处理** - 格式转换、媒体处理，为写作做好准备

   - PDF/图片转 Markdown、图片上传到图床
3. **专业应用** - 法律业务场景的专业技能

   - 诉讼分析、法律方案生成、法律文本格式化、法律问答提取、法院短信处理等专业应用

### 核心特点

- 🎯 **全流程覆盖**：从内容获取到处理归档的完整工作流
- 📦 **独立自包含**：每个技能都是完整的模块，可单独使用或组合使用
- 📝 **文档完善**：每个技能配备决策记录、任务跟踪、变更日志
- 🌐 **跨平台支持**：全面支持 Windows、macOS 和 Linux

## 🛠️ 技能列表

以下均为本项目自研技能，面向法律工作者的实际工作流按场景整理：

> “版本”为仓库当前版本；下载项如另标版本号，表示当前可下载的最新公开版本。

### 📥 内容获取

从各种来源收集研究资料：

<table>
<thead>
<tr>
<th style="text-align:left">技能</th>
<th style="text-align:left">标签</th>
<th style="text-align:left">说明</th>
<th style="text-align:center">许可证</th>
<th style="text-align:center">版本</th>
<th style="text-align:center">下载</th>
<th style="text-align:left">备注</th>
</tr>
</thead>
<tbody>
<tr>
<td><a href="skills/wechat-article-fetch/"><strong>wechat-article-fetch</strong></a></td>
<td>工具·搜索</td>
<td style="word-break:break-word">使用 Playwright 无头模式抓取微信公众号文章，支持动态加载内容，保存为 Markdown</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.3.1</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/wechat-article-fetch-1.3.1.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/legal-ocr/"><strong>legal-ocr</strong></a></td>
<td>工具·OCR</td>
<td style="word-break:break-word">OCR、扫描识别、图片文字识别和文档识别工具，支持 PDF、图片、Office 文档和 URL 转 Markdown；法律材料可进行保守的术语与文书结构优化</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.5.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/legal-ocr-1.5.0.zip">下载</a></td>
<td>推荐统一入口</td>
</tr>
<tr>
<td><a href="skills/mineru-ocr/"><strong>mineru-ocr</strong></a></td>
<td>工具·OCR</td>
<td style="word-break:break-word">通过 MinerU API 将 PDF、图片等文档转换为 Markdown，支持 OCR 文字识别、表格识别和数学公式识别</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.2.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/mineru-ocr-1.2.0.zip">下载</a></td>
<td>功能已由 legal-ocr 覆盖；建议新用户使用 legal-ocr</td>
</tr>
<tr>
<td><a href="skills/paddle-ocr/"><strong>paddle-ocr</strong></a></td>
<td>工具·OCR</td>
<td style="word-break:break-word">面向法律 PDF 与扫描件的 PaddleOCR 结构化解析，将 PDF 或图片转换为 Markdown，支持表格识别、公式识别、版面分析，保留 archive 归档</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.1.1</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/paddle-ocr-1.1.1.zip">下载</a></td>
<td>功能已由 legal-ocr 覆盖；保留兼容旧工作流，需配置 API Token</td>
</tr>
<tr>
<td><a href="skills/funasr-transcribe/"><strong>funasr-transcribe</strong></a></td>
<td>工具·ASR</td>
<td style="word-break:break-word">本地语音识别服务，将音频/视频转录为带时间戳的 Markdown，支持说话人分离、会议记录、视频字幕、播客转录</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.9.4</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/funasr-transcribe-1.9.4.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/tingwu-asr/"><strong>tingwu-asr</strong></a></td>
<td>工具·ASR</td>
<td style="word-break:break-word">阿里云通义听悟云端语音转录，适用于长音频、高精度场景，支持说话人分离和 AI 摘要生成</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v0.3.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/tingwu-asr-0.3.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/universal-media-downloader/"><strong>universal-media-downloader</strong></a></td>
<td>工具·下载</td>
<td style="word-break:break-word">输入视频网站/播客平台链接后自动下载，支持抖音/B站/YouTube/小宇宙等平台，可下载字幕和音频</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v0.2.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/universal-media-downloader-0.2.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/douyin-batch-download/"><strong>douyin-batch-download</strong></a></td>
<td>工具·下载</td>
<td style="word-break:break-word">抖音视频批量下载工具，基于 F2 框架，支持单个/批量博主下载，自动 Cookie 管理，差量更新机制</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.8.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/douyin-batch-download-1.8.0.zip">下载</a></td>
<td></td>
</tr>
</tbody>
</table>

### ⚖️ 法律专业应用

专门面向法律业务场景的专业技能：

<table>
<thead>
<tr>
<th style="text-align:left">技能</th>
<th style="text-align:left">标签</th>
<th style="text-align:left">说明</th>
<th style="text-align:center">许可证</th>
<th style="text-align:center">版本</th>
<th style="text-align:center">下载</th>
<th style="text-align:left">备注</th>
</tr>
</thead>
<tbody>
<tr>
<td><a href="skills/yuandian-law-search/"><strong>yuandian-law-search</strong></a></td>
<td>通用·检索</td>
<td style="word-break:break-word">元典法条与案例检索，通过元典 API 或官方 MCP 获取法条、案例、法规与企业信息，并自动归档；支持将多次检索汇总为 7 节结论先行法律检索报告</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.7.5</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/yuandian-law-search-1.7.5.zip">下载</a></td>
<td>需配置 API Key</td>
</tr>
<tr>
<td><a href="skills/court-sms/"><strong>court-sms</strong></a></td>
<td>通用·案件管理</td>
<td style="word-break:break-word">法院短信识别与文书下载技能，自动解析法院短信（文书送达、立案通知、开庭提醒等），提取案号、当事人、下载链接，下载文书并归档到对应案件目录</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.5.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/court-sms-1.5.0.zip">下载</a></td>
<td>参考自 <a href="https://github.com/Lawyer-ray/FachuanHybridSystem">法穿</a></td>
</tr>
<tr>
<td><a href="skills/invoice-organizer/"><strong>invoice-organizer</strong></a></td>
<td>通用·报销整理</td>
<td style="word-break:break-word">整理一批发票/票据 PDF（增值税普通发票、铁路电子客票、住宿交通餐饮等），按购买方抬头匹配所属案件项目，向上回溯读取项目上下文自动填补事由，复制归档（原件不动）并出具报销清单（可切换消费清单/对账流水）</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v0.1.1</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/invoice-organizer-0.1.1.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/new-case/"><strong>new-case</strong></a></td>
<td>通用·案件管理</td>
<td style="word-break:break-word">将案件/咨询材料整理成标准化目录结构。支持诉讼案件（12目录）和潜在项目/咨询（3目录）两种预设，自动生成案件信息看板、工时记录和期限管理文件</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.3.5</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/new-case-1.3.5.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/litigation-analysis/"><strong>litigation-analysis</strong></a></td>
<td>通用·诉讼</td>
<td style="word-break:break-word">诉讼分析工具，支持起诉状与证据分析、判决书深度分析、庭审笔录复盘。覆盖诉讼全流程：案件初期评估→判决分析→庭审复盘，生成内部版/研究版/客户版三层输出，支持上诉/再审决策支持</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.4.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/litigation-analysis-1.4.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/contract-copilot/"><strong>contract-copilot</strong></a></td>
<td>通用·合同</td>
<td style="word-break:break-word">合同起草与审查助手，基于分层分析与四步流程，输出可执行的风险清单、起草骨架、修改建议、推荐措辞和审查意见书，支持批注与修订两种文档处理方式</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.5.3</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/contract-copilot-1.5.3.zip">下载</a></td>
<td><a href="https://github.com/cat-xierluo/contract-copilot.skill">独立仓库</a></td>
</tr>
<tr>
<td><a href="skills/legal-case-analysis/"><strong>legal-case-analysis</strong></a></td>
<td>通用·分析</td>
<td style="word-break:break-word">通用法律分析技能，基于案件材料、咨询材料、合同资料、证据材料或检索结果进行法律分析、案件研判、风险评估与诉讼/非诉策略；前置分析引擎，报告为可选交付形态</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v0.3.3</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/legal-case-analysis-0.3.3.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/legal-proposal-generator/"><strong>legal-proposal-generator</strong></a></td>
<td>通用·文书</td>
<td style="word-break:break-word">根据案件材料或沟通记录生成各类法律服务文档（诉讼方案、咨询报告、非诉方案、建议书、沟通报告、结案汇报等）。采用模块化架构自动匹配场景，生成接近定稿质量的专业文档</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v0.3.1</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/legal-proposal-generator-0.3.1.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/legal-text-format/"><strong>legal-text-format</strong></a></td>
<td>通用·文书</td>
<td style="word-break:break-word">将法律文本（法律条文或法律案例）转换为规范的 Markdown 格式，采用 archive 归档结构存储。推荐与 <a href="skills/wechat-article-fetch/"><strong>wechat-article-fetch</strong></a> 配合使用实现完整工作流</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.2.1</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/legal-text-format-1.2.1.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/legal-qa-extractor/"><strong>legal-qa-extractor</strong></a></td>
<td>通用·文书</td>
<td style="word-break:break-word">从律师与客户沟通记录中提取有价值的法律问答对，生成结构化知识库内容。支持严格客户信息脱敏处理，适用于整理咨询记录、创建问答知识库、准备内容营销素材</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.1.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/legal-qa-extractor-1.1.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/trademark-assistant/"><strong>trademark-assistant</strong></a></td>
<td>专业·知产</td>
<td style="word-break:break-word">商标服务助手，提供类别规划、可注册性初筛及申请材料准备。支持商品清单生成、商标说明撰写，整合尼斯分类与审查指南</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.7.2</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/trademark-assistant.skill/releases/download/v1.7.0/trademark-assistant-1.7.0.zip">下载 v1.7.0</a></td>
<td><a href="https://github.com/cat-xierluo/trademark-assistant.skill">独立仓库</a></td>
</tr>
<tr>
<td><a href="skills/patent-analysis/"><strong>patent-analysis</strong></a></td>
<td>专业·知产</td>
<td style="word-break:break-word">中国发明与实用新型专利分析工具，支持10种场景；逐项分析选定权利要求，以 A/B/C/D 证据门禁约束侵权、无效、FTO、规避设计、估值和可视化结论</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v2.1.2</td>
<td style="text-align:center">待发布</td>
<td><a href="https://github.com/cat-xierluo/patent-analysis.skill">独立仓库</a></td>
</tr>
<tr>
<td><a href="skills/patent-download/"><strong>patent-download</strong></a></td>
<td>工具·知产</td>
<td style="word-break:break-word">专利 PDF 批量下载工具，Google Patents 为首选通道（免费免登录），支持多平台、自动处理申请号和公告号格式；凭证环境变量化 + 防泄露自检</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v2.7.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/patent-download-2.6.0.zip">下载 v2.6.0</a></td>
<td>本仓库</td>
</tr>
<tr>
<td><a href="skills/code2patent/"><strong>code2patent</strong></a></td>
<td>专业·知产</td>
<td style="word-break:break-word">从已开发代码项目中提取技术实现证据，围绕候选专利方案生成算法/软件类说明书式技术交底书，并以"权利要求布局卡 → 发明专利初稿"两步法生成接近可申报版的中国发明专利起草材料；内置《专利审查指南》撰写规则、计算机程序发明保护主题提示和 agent 速查卡</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.6.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/code2patent-1.6.0.zip">下载</a></td>
<td><a href="https://github.com/cat-xierluo/code2patent.skill">独立仓库</a></td>
</tr>
<tr>
<td><a href="skills/opc-legal-counsel/"><strong>opc-legal-counsel</strong></a></td>
<td>专业·顾问</td>
<td style="word-break:break-word">面向一人公司、单人创业者与小微企业的法律业务判断技能：识别经营主矛盾、跨领域风险、行动和升级边界；现行法条、税率、名录、地方政策与平台规则通过工具中立协议交由法律数据库、MCP 或官方来源核验</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.0.0</td>
<td style="text-align:center">待发布</td>
<td><a href="https://github.com/cat-xierluo/opc-legal-counsel.skill">独立仓库</a></td>
</tr>
<tr>
<td><a href="skills/legal-visualization/"><strong>legal-visualization</strong></a></td>
<td>专业·可视化</td>
<td style="word-break:break-word">面向法律业务场景的法律图解与图表生成技能，把案件、合同、合规、交易、证据链和诉讼流程整理成关系图/流程图/时间轴/风险图；通过 VizSpec 2.1、几何守恒视觉编译、三套受众主题、容器感知重叠与文字容量门禁阻断坏图，默认交付 .drawio + .svg + .png 三件套</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v0.8.2</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/legal-visualization-0.6.14.zip">下载 v0.6.14</a></td>
<td></td>
</tr>
</tbody>
</table>

### 📤 内容处理

格式转换、媒体处理、配图生成，为专业写作做好准备：

<table>
<thead>
<tr>
<th style="text-align:left">技能</th>
<th style="text-align:left">标签</th>
<th style="text-align:left">说明</th>
<th style="text-align:center">许可证</th>
<th style="text-align:center">版本</th>
<th style="text-align:center">下载</th>
<th style="text-align:left">备注</th>
</tr>
</thead>
<tbody>
<tr>
<td><a href="skills/pdf-processor/"><strong>pdf-processor</strong></a></td>
<td>工具·PDF处理</td>
<td style="word-break:break-word">PDF 处理工具，支持扫描件预处理、OCR 双层 PDF 生成、页码添加、PDF 合并、解密、水印去除和压缩。统一入口自动选择最短可用流程，配合 pdf-organizer 完成从预处理到文书整理的完整工作流</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v2.7.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/pdf-processor-2.7.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/img2pdf/"><strong>img2pdf</strong></a></td>
<td>工具·PDF排版</td>
<td style="word-break:break-word">将图片或 PDF 页面按 N 张/页编排为标准化 A4 PDF，或将长截图渲染为单张自适应高度 PDF；支持 1/2/3/4 张每页布局，自动检测图片横竖方向，适用于法律证据材料整理（手机截图、视频取证截图、现场照片、长截图等）</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.2.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/img2pdf-1.2.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/pdf-organizer/"><strong>pdf-organizer</strong></a></td>
<td>通用·PDF整理</td>
<td style="word-break:break-word">法律 PDF 文书整理工具：按内容拆分、合并或直接重命名 OCR 后双层扫描件，生成页面索引、manifest 草稿和下游交接文件；支持旋转与倾斜校正，不做 OCR 或压缩</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v0.5.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/pdf-organizer-0.5.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/course-generator/"><strong>course-generator</strong></a></td>
<td>工具·课程</td>
<td style="word-break:break-word">课程内容管理平台。支持三种工作模式：从转录稿/文献生成结构化课程、将课程归档到知识库、根据客户需求从现有素材中提取并重组定制化培训方案；支持绝对路径配置、用户词典术语纠错、英文专有名称保真、图片资产保真与正文插图克制、结构适配、问答融入、高保真正文增强、独立正文去来源痕迹、总览/章节生成和旧命名兼容</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v2.3.3</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/course-generator-2.3.3.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/transcription-corrector/"><strong>transcription-corrector</strong></a></td>
<td>工具·校对</td>
<td style="word-break:break-word">ASR 转录稿纠错与轻度优化工具：按用户词典统一替换同音字与英文专有名称漂移，可选合并同发言人发言、清理标点和切分段落；与 course-generator 共用词典格式，原始文件保持不动并双写归档</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.0.8</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/transcription-corrector-1.0.8.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/video-screenshot/"><strong>video-screenshot</strong></a></td>
<td>工具·视频处理</td>
<td style="word-break:break-word">从录屏视频（微信聊天录屏、会议录屏等）中自动抽取关键帧、去重并保存为图片文件，可用作法律证据。支持场景变化检测、关键帧提取、智能去重四种策略</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v0.3.2</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/video-screenshot-0.3.2.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/article2book/"><strong>article2book</strong></a></td>
<td>工具·内容</td>
<td style="word-break:break-word">现有内容资产再组织技能。基于文章、专栏、课程讲稿、逐字稿、访谈、课件、会议纪要、案例材料、PDF 文本、Word 文档和笔记等素材，判断最适合转化为书、小册子、课程、系列文章、实务手册或知识库，并输出精简策划意见</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.0.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/article2book-1.0.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/svg-article-illustrator/"><strong>svg-article-illustrator</strong></a></td>
<td>工具·配图</td>
<td style="word-break:break-word">AI 驱动的 SVG 文章配图生成工具，支持动态 SVG、静态 SVG 和 PNG 导出三种模式，专为公众号文章等需要丰富视觉内容的平台设计</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.0.5</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/svg-article-illustrator-1.0.5.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/handdrawn-article-illustrator/"><strong>handdrawn-article-illustrator</strong></a></td>
<td>工具·配图</td>
<td style="word-break:break-word">手绘风格文章配图：先理解文章写 Image Brief 和 prompt，再用内置生图能力出图；配色通过主题文件（themes/）配置，内置蓝灰/墨黑/赭石三套预设，可切换或自定义</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.1.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/handdrawn-article-illustrator-1.1.0.zip">下载</a></td>
<td>配色可定制</td>
</tr>
<tr>
<td><a href="skills/svg-book-illustrator/"><strong>svg-book-illustrator</strong></a></td>
<td>工具·配图</td>
<td style="word-break:break-word">书籍/文章 SVG 配图生成工具，专注于架构图、流程图、层次图等专业技术配图，针对印刷出版场景优化，字号间距按物理尺寸反推</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.8.10</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/svg-book-illustrator-1.8.10.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/piclist-upload/"><strong>piclist-upload</strong></a></td>
<td>工具·图床</td>
<td style="word-break:break-word">通过 PicList HTTP Server 将 Markdown 中的本地图片上传到图床，自动替换为云端链接，支持批量处理和跨设备访问</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.2.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/piclist-upload-1.2.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/md2word/"><strong>md2word</strong></a></td>
<td>工具·格式转换</td>
<td style="word-break:break-word">将 Markdown 文档转换为专业格式 Word 文档，支持法律文书标准，自动应用字体、字号、行距和段落格式</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.1.8</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/md2word-1.1.8.zip">下载</a></td>
<td><a href="https://github.com/cat-xierluo/md2word.skill">独立仓库</a></td>
</tr>
<tr>
<td><a href="skills/de-ai-polish/"><strong>de-ai-polish</strong></a></td>
<td>工具·写作</td>
<td style="word-break:break-word">检测并去除文章中的 AI 化表述模式，用于写作润色、文本优化、去 AI 腔。支持作者样本 Voice Calibration、Protected Spans、场景分流和候选绑定质量评分门禁</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v2.2.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/de-ai-polish.skill/releases/download/v2.0.1/de-ai-polish-2.0.1.zip">下载 v2.0.1</a></td>
<td><a href="https://github.com/cat-xierluo/de-ai-polish.skill">独立仓库</a></td>
</tr>
<tr>
<td><a href="skills/video-compressor/"><strong>video-compressor</strong></a></td>
<td>工具·格式转换</td>
<td style="word-break:break-word">视频压缩与静默片段剪切工具，使用 FFmpeg CRF 模式压缩视频，自动检测硬件选择最优编码方案（Apple Silicon VideoToolbox 硬件加速），支持检测并去除静默静止片段</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.3.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/video-compressor-1.3.0.zip">下载</a></td>
<td></td>
</tr>
</tbody>
</table>

### 🚀 个人效率

日常行程、提醒等通用效率工具：

<table>
<thead>
<tr>
<th style="text-align:left">技能</th>
<th style="text-align:left">标签</th>
<th style="text-align:left">说明</th>
<th style="text-align:center">许可证</th>
<th style="text-align:center">版本</th>
<th style="text-align:center">下载</th>
<th style="text-align:left">备注</th>
</tr>
</thead>
<tbody>
<tr>
<td><a href="skills/apple-smart-schedule/"><strong>apple-smart-schedule</strong></a></td>
<td>工具·日程</td>
<td style="word-break:break-word">把自然语言(机票/高铁/开庭/会议/截止/聚会等)或票据截图，自动变成苹果日历事件 + 按事件类型智能提前的提醒事项；仅 macOS，经 iCloud 同步到 iPhone/iPad</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v0.1.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/apple-smart-schedule-0.1.0.zip">下载</a></td>
<td>仅 macOS</td>
</tr>
</tbody>
</table>

### 🔧 开发工具

技能开发、插件管理等开发工具：

<table>
<thead>
<tr>
<th style="text-align:left">技能</th>
<th style="text-align:left">标签</th>
<th style="text-align:left">说明</th>
<th style="text-align:center">许可证</th>
<th style="text-align:center">版本</th>
<th style="text-align:center">下载</th>
<th style="text-align:left">备注</th>
</tr>
</thead>
<tbody>
<tr>
<td><a href="skills/agent-email/"><strong>agent-email</strong></a></td>
<td>工具·邮件</td>
<td style="word-break:break-word">Agent 专用邮箱服务，通过邮件接收指令、发送结果、与其他 Agent 或人类通信。支持邮件收发、搜索、附件处理，目前支持网易 ClawEmail</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v0.4.1</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/agent-email-0.4.1.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/project-init/"><strong>project-init</strong></a></td>
<td>工具·项目管理</td>
<td style="word-break:break-word">项目初始化工具，读取全局协议，分析项目实际情况，按配置检测项目类型并生成项目特定的 AGENTS.md、CLAUDE.md、docs/ 文档体系与 .claude/ 配置</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.2.4</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/project-init-1.1.2.zip">下载 v1.1.2</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/skill-manager/"><strong>skill-manager</strong></a></td>
<td>工具·Skill开发</td>
<td style="word-break:break-word">管理 AI Agent Skills 的安装、同步、卸载和列表查看，支持本地路径和 GitHub 仓库/子目录，自动识别 Codex、Claude Code 和 OpenClaw 目标目录并批量处理</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.7.1</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/skill-manager-1.7.1.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/skill-lint/"><strong>skill-lint</strong></a></td>
<td>工具·Skill开发</td>
<td style="word-break:break-word">Skill 创建预检与可靠性验收工具，支持具体 Harness 失效模式批量定位、旧版指令失稳识别、领域 checker 双向充分性边界、硬要求来源定位、逐约束追踪、验证模态/产物阶段匹配、Ed25519 签名证据与多轮漂移门禁、业务流和安全风险审查</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v2.6.2</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/skill-lint-2.4.0.zip">下载 v2.4.0</a></td>
<td>正式验收需区分 Harness 审查、指令稳定性与领域功能验证</td>
</tr>
<tr>
<td><a href="skills/git-batch-commit/"><strong>git-batch-commit</strong></a></td>
<td>工具·Git</td>
<td style="word-break:break-word">智能 Git 批量提交工具，自动将混合的文件修改按类型分类并创建多个清晰聚焦的提交，使用标准化的提交信息格式</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.4.1</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/git-batch-commit-1.4.1.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/git-workflow/"><strong>git-workflow</strong></a></td>
<td>工具·Git</td>
<td style="word-break:break-word">Git 工作流安全助手，覆盖分支管理、Monorepo 安全合并、PR、冲突处理、安全回退、分支清理和身份绑定 safe-push</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.6.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/git-workflow-1.6.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/cross-agent-coordination/"><strong>cross-agent-coordination</strong></a></td>
<td>工具·Agent协作</td>
<td style="word-break:break-word">跨平台 Agent 任务协调枢纽，围绕项目任务源分配任务、标记归属、能力路由并保留交接上下文</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.0.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/cross-agent-coordination-1.0.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/multi-agent-orchestration/"><strong>multi-agent-orchestration</strong></a></td>
<td>工具·Agent协作</td>
<td style="word-break:break-word">多 Agent 本地执行编排，支持 worktree/session 隔离、tmux worker、PM 巡检、Shell/安装权限门禁与身份绑定 PR 收口</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.19.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/multi-agent-orchestration-1.19.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/release-workflow/"><strong>release-workflow</strong></a></td>
<td>工具·发布</td>
<td style="word-break:break-word">GitHub 项目全流程发布工作流：版本号管理、CHANGELOG 同步、Release Notes 撰写、tag 创建、CI 构建监控、发布验证和历史清理，含 Tauri 桌面应用和 CI 故障排查专项指南</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.4.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/release-workflow-1.4.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/github-star-manager/"><strong>github-star-manager</strong></a></td>
<td>工具·Star管理</td>
<td style="word-break:break-word">GitHub Star 项目管理工具，从内容自动发现并 Star 项目，同步追踪已 Star 项目更新，生成可视化 Dashboard，支持分类管理和标签系统</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v0.6.2</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/github-star-manager-0.6.2.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/clawhub-sync/"><strong>clawhub-sync</strong></a></td>
<td>工具·发布</td>
<td style="word-break:break-word">将本地开发的 Skills 批量同步到 ClawHub 平台，支持智能 .gitignore 过滤、白名单控制、增量同步</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.4.2</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/clawhub-sync-1.4.2.zip">下载</a></td>
<td><a href="https://github.com/openclaw/clawhub/blob/main/docs/skill-format.md">ClawHub 要求 MIT-0</a></td>
</tr>
<tr>
<td><a href="skills/subtree-publish/"><strong>subtree-publish</strong></a></td>
<td>工具·发布</td>
<td style="word-break:break-word">将 monorepo 中的子目录通过 git subtree 推送到独立 GitHub 仓库，支持注册清单、变更自动检测、增量推送</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.7.1</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.07.23/subtree-publish-1.7.1.zip">下载</a></td>
<td></td>
</tr>
</tbody>
</table>

> 💡 **为什么包含通用工具？** 法律从业者兼具专业工作者与创作者的双重身份。撰写专业文章、整理研究资料、分享知识都需要内容获取与处理能力。这些通用工具是法律专业写作的基础设施。

## 📚 开发与编排指南

- [SKILL-DEV-GUIDE.md](docs/SKILL-DEV-GUIDE.md)：单个 Skill 的开发规范
- [SKILL-ORCHESTRATION-GUIDE.md](docs/SKILL-ORCHESTRATION-GUIDE.md)：多个 Skill 的协作编排规范
- [SKILL-HANDOFF-GUIDE.md](docs/SKILL-HANDOFF-GUIDE.md)：多个 Skill 之间的交接契约与 handoff package 规范

---

## 📖 协作规范

本项目遵循 [AGENTS.md](AGENTS.md) 定义的协作规范：

- **技能导向**：每个技能独立成树，根目录包含 SKILL.md 和配套文档
- **文档即上下文**：关键决策、任务、变更记录在文档中
- **透明变更**：所有修改写入 CHANGELOG.md，遵循版本号规范
- **保留证据**：输出引用可回溯，缺失信息明确标注

## 🚀 安装方法

将以下内容复制到你的 Agent 平台，让它帮你安装：

> 请帮我从 GitHub 安装 legal-skills 技能集合：[https://github.com/cat-xierluo/legal-skills](https://github.com/cat-xierluo/legal-skills)

### 单独下载某个 skill（推荐，无需 Git）

进入 [GitHub Releases 最新版](https://github.com/cat-xierluo/legal-skills/releases/latest) 页面，
下载你需要的 skill 的 zip 文件，解压后直接得到 `<name>/` 文件夹，把整个文件夹复制到 Agent 的 skills 目录即可。

例如 `contract-copilot-1.5.3.zip` 解压后得到 `contract-copilot/` 文件夹，复制到 `~/.claude/skills/` 即可。

上表「下载」列已提供每个 skill 的最新版本直链（指向 latest），新增版本发布后由 GitHub Actions 自动同步。

## 📦 已归档/已合并技能

以下技能已停止维护、归档或合并到其他技能，不再作为独立 Skill 随仓库发布：

| 技能                     | 版本   | 说明                                                                                                                                          |
| ------------------------ | ------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| multi-search             | v1.1.0 | 智能多主题深度研究工具，功能被[multi-agent-orchestration](skills/multi-agent-orchestration/) v1.16+ 内置的并行 Subagent 能力覆盖，停止独立维护 |
| skill-architect          | v1.6.2 | 已重定位为[skill-lint](skills/skill-lint/) v2.0.0，创建能力不再作为本仓库独立入口维护                                                          |
| minimax-image-understand | v0.1.0 | 各平台已原生支持 MiniMax MCP 图像理解，无需独立 skill                                                                                         |
| minimax-web-search       | v0.1.1 | 各平台已原生支持 MiniMax MCP 网络搜索，无需独立 skill                                                                                         |
| repo-research            | v0.7.0 | 功能较简单，不再维护                                                                                                                          |
| zhihe-legal-research     | v1.2.2 | 已归档（智合AI平台接口已下线，返回 404；接口可能已迁移至智合自有平台）。技能目录已从仓库移除                                                                                                          |
