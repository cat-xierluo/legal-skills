# Legal Skills

> 面向法律从业者的 AI Agent Skills 集合，支持从内容获取、处理到专业写作的全流程 AI 协作。兼容 Claude Code、OpenClaw 等主流 AI Agent 平台。

[![GitHub](https://img.shields.io/badge/GitHub-cat--xierluo-blue)](https://github.com/cat-xierluo/legal-skills)

## 👨‍💼 关于作者

**杨卫薪律师** - 专注于技术类纠纷领域（知识产权、数据与 AI），同时热衷于将 AI 技术应用于法律实务。

欢迎添加微信交流（请注明来意），对于标注「非商用」许可证的 Skill 也可联系获取授权（见下方说明）：

<details>
<summary>📚 许可证说明</summary>

本项目采用两种许可证：

| 许可证 | 说明 | 示例技能 |
|:------|:-----|:---------|
| **MIT** | 可自由使用，包括商用，但需保留署名 | wechat-article-fetch、mineru-ocr、md2word 等 |
| **CC-BY-NC** | 可自由使用，但**不可商用**，且需保留署名和相同方式共享 | litigation-analysis、patent-analysis、legal-proposal-generator 等 |

> 💡 如需将技能用于商业目的，请添加微信（ywxlaw）联系授权

</details>

<div align="center">
  <img src="wechat-qr.jpg" width="200" alt="微信二维码"/>
  <p><em>微信：ywxlaw</em></p>
</div>

---

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

### 推荐技能

来自官方或其他优秀开发者的通用技能：

| 技能                                                         | 说明                                         | 许可证       |
| :----------------------------------------------------------- | :------------------------------------------- | :----------- |
| **[skill-creator](https://github.com/anthropics/skills)** | 技能创建指南和工具集                         | 参照官方许可 |
| **[pdf](https://github.com/anthropics/skills)**           | PDF 处理工具包：文本提取、表单填写、合并拆分 | 参照官方许可 |
| **[docx](https://github.com/anthropics/skills)**          | Word 文档处理工具包                          | 参照官方许可 |

### 自研技能

面向法律工作者的实用技能：

#### 📥 内容获取

从各种来源收集研究资料：

<table>
<thead>
<tr>
<th style="text-align:left">技能</th>
<th style="text-align:left">说明</th>
<th style="text-align:center">许可证</th>
<th style="text-align:center">版本</th>
<th style="text-align:center">作者</th>
<th style="text-align:left">备注</th>
</tr>
</thead>
<tbody>
<tr>
<td><a href="skills/wechat-article-fetch/"><strong>wechat-article-fetch</strong></a></td>
<td style="word-break:break-word">使用 Playwright 无头模式抓取微信公众号文章，支持动态加载内容，保存为 Markdown</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.2.0</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/mineru-ocr/"><strong>mineru-ocr</strong></a></td>
<td style="word-break:break-word">通过 MinerU API 将 PDF、图片等文档转换为 Markdown，支持 OCR 文字识别、表格识别和数学公式识别</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.2.0</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/paddle-ocr/"><strong>paddle-ocr</strong></a></td>
<td style="word-break:break-word">面向法律 PDF 与扫描件的 PaddleOCR 结构化解析，将 PDF 或图片转换为 Markdown，支持表格识别、公式识别、版面分析，保留 archive 归档</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.1.1</td>
<td style="text-align:center">杨卫薪</td>
<td>需配置 API Token</td>
</tr>
<tr>
<td><a href="skills/funasr-transcribe/"><strong>funasr-transcribe</strong></a></td>
<td style="word-break:break-word">本地语音识别服务，将音频/视频转录为带时间戳的 Markdown，支持说话人分离、会议记录、视频字幕、播客转录</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.9.4</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/tingwu-asr/"><strong>tingwu-asr</strong></a></td>
<td style="word-break:break-word">阿里云通义听悟云端语音转录，适用于长音频、高精度场景，支持说话人分离和 AI 摘要生成</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v0.1.0</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/universal-media-downloader/"><strong>universal-media-downloader</strong></a></td>
<td style="word-break:break-word">输入视频网站/播客平台链接后自动下载，支持抖音/B站/YouTube/小宇宙等平台，可下载字幕和音频</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v0.2.0</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/douyin-batch-download/"><strong>douyin-batch-download</strong></a></td>
<td style="word-break:break-word">抖音视频批量下载工具，基于 F2 框架，支持单个/批量博主下载，自动 Cookie 管理，差量更新机制</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.8.0</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/multi-search/"><strong>multi-search</strong></a></td>
<td style="word-break:break-word">智能多主题深度研究工具，使用独立 Subagent 进行并行深度检索，生成系统化研究文档</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.1.0</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/minimax-web-search/"><strong>minimax-web-search</strong></a></td>
<td style="word-break:break-word">通过 MiniMax MCP 进行网络搜索</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v0.1.1</td>
<td style="text-align:center">杨卫薪</td>
<td>适用于 OpenClaw</td>
</tr>
<tr>
<td><a href="skills/minimax-image-understand/"><strong>minimax-image-understand</strong></a></td>
<td style="word-break:break-word">通过 MiniMax MCP 进行图像理解</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v0.1.0</td>
<td style="text-align:center">杨卫薪</td>
<td>适用于 OpenClaw</td>
</tr>
</tbody>
</table>

#### ⚖️ 法律专业应用

专门面向法律业务场景的专业技能：

<table>
<thead>
<tr>
<th style="text-align:left">技能</th>
<th style="text-align:left">说明</th>
<th style="text-align:center">许可证</th>
<th style="text-align:center">版本</th>
<th style="text-align:center">作者</th>
<th style="text-align:left">备注</th>
</tr>
</thead>
<tbody>
<tr>
<td><a href="skills/court-sms/"><strong>court-sms</strong></a></td>
<td style="word-break:break-word">法院短信识别与文书下载技能，自动解析法院短信（文书送达、立案通知、开庭提醒等），提取案号、当事人、下载链接，下载文书并归档到对应案件目录</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.5.0</td>
<td style="text-align:center">杨卫薪</td>
<td>参考自 <a href="https://github.com/Lawyer-ray/FachuanHybridSystem">法穿</a></td>
</tr>
<tr>
<td><a href="skills/trademark-assistant/"><strong>trademark-assistant</strong></a></td>
<td style="word-break:break-word">商标服务助手，提供类别规划、可注册性初筛及申请材料准备。支持商品清单生成、商标说明撰写，整合尼斯分类与审查指南</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.5.4</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/patent-analysis/"><strong>patent-analysis</strong></a></td>
<td style="word-break:break-word">专利分析工具，支持7种场景：单专利技术要点提取、多专利比对、侵权比对、稳定性/无效分析、FTO分析、规避设计分析、专利价值评估。强调权利要求解读方法论与侵权判断流程</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.2.0</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/code2patent/"><strong>code2patent</strong></a></td>
<td style="word-break:break-word">从已开发代码项目中提取技术实现证据，围绕候选专利方案生成技术交底书，并以"权利要求布局卡 → 发明专利初稿"两步法生成接近可申报版的中国发明专利起草材料；内置《专利审查指南》撰写规则、计算机程序发明保护主题提示和 agent 速查卡</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.4.2</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/litigation-analysis/"><strong>litigation-analysis</strong></a></td>
<td style="word-break:break-word">诉讼分析工具，支持起诉状与证据分析、判决书深度分析、庭审笔录复盘。覆盖诉讼全流程：案件初期评估→判决分析→庭审复盘，生成内部版/研究版/客户版三层输出，支持上诉/再审决策支持</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.3.2</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/legal-proposal-generator/"><strong>legal-proposal-generator</strong></a></td>
<td style="word-break:break-word">根据案件材料或沟通记录生成各类法律服务文档（诉讼方案、咨询报告、非诉方案、建议书、沟通报告、结案汇报等）。采用模块化架构自动匹配场景，生成接近定稿质量的专业文档</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v0.2.0</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/legal-text-format/"><strong>legal-text-format</strong></a></td>
<td style="word-break:break-word">将法律文本（法律条文或法律案例）转换为规范的 Markdown 格式，采用 archive 归档结构存储。推荐与 <a href="skills/wechat-article-fetch/"><strong>wechat-article-fetch</strong></a> 配合使用实现完整工作流</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.1.0</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/legal-qa-extractor/"><strong>legal-qa-extractor</strong></a></td>
<td style="word-break:break-word">从律师与客户沟通记录中提取有价值的法律问答对，生成结构化知识库内容。支持严格客户信息脱敏处理，适用于整理咨询记录、创建问答知识库、准备内容营销素材</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.0.0</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/yuandian-law-search/"><strong>yuandian-law-search</strong></a></td>
<td style="word-break:break-word">元典法条与案例检索，通过元典 API 检索中国法律法规条文和案例。支持法条语义/关键词/详情检索和案例关键词/向量语义检索，共 5 种检索模式</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.1.1</td>
<td style="text-align:center">杨卫薪</td>
<td>需配置 API Key</td>
</tr>
<tr>
<td><a href="skills/zhihe-legal-research/"><strong>zhihe-legal-research</strong></a></td>
<td style="word-break:break-word">连接智合AI法律大模型平台进行法律研究，提交法律问题后自动进行调研分析，生成文字分析结果和 docx 格式研究报告</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.2.0</td>
<td style="text-align:center">杨卫薪</td>
<td>需智合AI平台会员</td>
</tr>
<tr>
<td><a href="skills/opc-legal-counsel/"><strong>opc-legal-counsel</strong></a></td>
<td style="word-break:break-word">面向一人公司/单人创业者的常年法律顾问技能，覆盖公司设立、股权架构、融资、合同、税务、AI 产品合规、劳动等全场景，自动判断地域、阶段与问题性质并路由</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v0.2.5</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/contract-copilot/"><strong>contract-copilot</strong></a></td>
<td style="word-break:break-word">合同起草与审查助手，基于分层分析与四步流程，输出可执行的风险清单、起草骨架、修改建议、推荐措辞和审查意见书，支持批注与修订两种文档处理方式</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.4.50</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
</tbody>
</table>

#### 📤 内容处理

格式转换、媒体处理、配图生成，为专业写作做好准备：

<table>
<thead>
<tr>
<th style="text-align:left">技能</th>
<th style="text-align:left">说明</th>
<th style="text-align:center">许可证</th>
<th style="text-align:center">版本</th>
<th style="text-align:center">作者</th>
<th style="text-align:left">备注</th>
</tr>
</thead>
<tbody>
<tr>
<td><a href="skills/course-generator/"><strong>course-generator</strong></a></td>
<td style="word-break:break-word">课程内容管理平台。支持三种工作模式：从转录稿/文献生成结构化课程、将课程归档到知识库、根据客户需求从现有素材中提取并重组定制化培训方案；支持绝对路径配置、用户词典术语纠错、结构适配、问答融入、总览/章节生成和旧命名兼容</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v2.2.0</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/svg-article-illustrator/"><strong>svg-article-illustrator</strong></a></td>
<td style="word-break:break-word">AI 驱动的 SVG 文章配图生成工具，支持动态 SVG、静态 SVG 和 PNG 导出三种模式，专为公众号文章等需要丰富视觉内容的平台设计</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.0.4</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/piclist-upload/"><strong>piclist-upload</strong></a></td>
<td style="word-break:break-word">通过 PicList HTTP Server 将 Markdown 中的本地图片上传到图床，自动替换为云端链接，支持批量处理和跨设备访问</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.1.2</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/md2word/"><strong>md2word</strong></a></td>
<td style="word-break:break-word">将 Markdown 文档转换为专业格式 Word 文档，支持法律文书标准，自动应用字体、字号、行距和段落格式</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.0.1</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/de-ai-polish/"><strong>de-ai-polish</strong></a></td>
<td style="word-break:break-word">检测并去除文章中的 AI 化表述模式，用于写作润色、文本优化、去 AI 腔。整合 24 种 AI 写作检测规则，配备 5 维度质量评分系统</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.0.0</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
</tbody>
</table>

#### 🔧 开发工具

技能开发、插件管理等开发工具：

<table>
<thead>
<tr>
<th style="text-align:left">技能</th>
<th style="text-align:left">说明</th>
<th style="text-align:center">许可证</th>
<th style="text-align:center">版本</th>
<th style="text-align:center">作者</th>
<th style="text-align:left">备注</th>
</tr>
</thead>
<tbody>
<tr>
<td><a href="skills/skill-manager/"><strong>skill-manager</strong></a></td>
<td style="word-break:break-word">管理 AI Agent Skills 的安装、同步、卸载和列表查看，支持本地路径和 GitHub 仓库/子目录，自动识别并批量处理</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.3.0</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/skill-architect/"><strong>skill-architect</strong></a></td>
<td style="word-break:break-word">技能架构师向导与审查工具，整合官方 skill-creator 流程与内置合规检查，支持创建新技能、编辑现有技能、打包技能、审查格式合规性</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.3.0</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/git-batch-commit/"><strong>git-batch-commit</strong></a></td>
<td style="word-break:break-word">智能 Git 批量提交工具，自动将混合的文件修改按类型分类并创建多个清晰聚焦的提交，使用标准化的提交信息格式</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.2.5</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/github-star-manager/"><strong>github-star-manager</strong></a></td>
<td style="word-break:break-word">GitHub Star 项目管理工具，从内容自动发现并 Star 项目，同步追踪已 Star 项目更新，生成可视化 Dashboard，支持分类管理和标签系统</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v0.6.1</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/skill-lint/"><strong>skill-lint</strong></a></td>
<td style="word-break:break-word">Skill 格式审查工具，基于 SKILL-DEV-GUIDE.md 规范对技能进行合规性审计，检查文档与代码一致性，识别冗余内容，生成技能审计报告</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.3.0</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/repo-research/"><strong>repo-research</strong></a></td>
<td style="word-break:break-word">GitHub 仓库深度研究工具，支持单/多仓库研究、与本地项目对比分析、启发式整合建议。支持主题驱动搜索模式：自动搜索相关仓库、克隆、分析并生成报告</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v0.7.0</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
<tr>
<td><a href="skills/clawhub-sync/"><strong>clawhub-sync</strong></a></td>
<td style="word-break:break-word">将本地开发的 Skills 批量同步到 ClawHub 平台，支持智能 .gitignore 过滤、白名单控制、增量同步</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.4.1</td>
<td style="text-align:center">杨卫薪</td>
<td><a href="https://github.com/openclaw/clawhub/blob/main/docs/skill-format.md">ClawHub 要求 MIT-0</a></td>
</tr>
<tr>
<td><a href="skills/subtree-publish/"><strong>subtree-publish</strong></a></td>
<td style="word-break:break-word">将 monorepo 中的子目录通过 git subtree 推送到独立 GitHub 仓库，支持注册清单、变更自动检测、增量推送</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.5.0</td>
<td style="text-align:center">杨卫薪</td>
<td></td>
</tr>
</tbody>
</table>

> 💡 **为什么包含通用工具？** 法律从业者兼具专业工作者与创作者的双重身份。撰写专业文章、整理研究资料、分享知识都需要内容获取与处理能力。这些通用工具是法律专业写作的基础设施。

## 📚 开发与编排指南

- [SKILL-DEV-GUIDE.md](SKILL-DEV-GUIDE.md)：单个 Skill 的开发规范
- [SKILL-ORCHESTRATION-GUIDE.md](SKILL-ORCHESTRATION-GUIDE.md)：多个 Skill 的协作编排规范
- [SKILL-HANDOFF-GUIDE.md](SKILL-HANDOFF-GUIDE.md)：多个 Skill 之间的交接契约与 handoff package 规范

---

## 📖 协作规范

本项目遵循 [AGENTS.md](AGENTS.md) 定义的协作规范：

- **技能导向**：每个技能独立成树，根目录包含 SKILL.md 和配套文档
- **文档即上下文**：关键决策、任务、变更记录在文档中
- **透明变更**：所有修改写入 CHANGELOG.md，遵循版本号规范
- **保留证据**：输出引用可回溯，缺失信息明确标注

## 🚀 安装方法

### 方式一：让 Agent 安装（推荐）

将以下内容复制给你的 Agent，让它帮你安装：

> 请帮我从 GitHub 安装 legal-skills 技能集合：
>
> - 仓库地址：<https://github.com/cat-xierluo/legal-skills>
> - 安装方式：使用 `/skill install` 命令从仓库安装

### 方式二：OpenClaw 平台

将技能目录复制到 OpenClaw 的 skills 目录：

```bash
cp -r legal-skills/skills/* /path/to/openclaw/skills/
```

### 方式三：手动安装

下载本项目压缩包，解压后将技能目录复制到对应平台的 skills 目录：

| 平台 | 默认路径 |
| :--- | :--- |
| Claude Code (macOS/Linux) | `~/.claude/skills/` |
| Claude Code (Windows) | `%USERPROFILE%\.claude\skills\` |
| OpenClaw | 根据配置文件指定 |
