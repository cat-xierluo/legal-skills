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
| 2026-09-21 | 更新   | [elements-complaint-generator](skills/elements-complaint-generator/)   | v0.15.2 | **含空格路径 Harness 恢复修复**：伪产物路径改用数组保留边界，避免仓库或文件名含空格时备份恢复命令错误分词、遗留伪 DOCX；新增显式空格文件名回归，Harness 28/28。 |
| 2026-09-21 | 更新   | [multi-agent-orchestration](skills/multi-agent-orchestration/)         | v2.27.6 | **tracked 文件删除权限**：`git rm` 改为 receipt 绑定的高风险分类，仅允许冻结范围内单一 tracked 文件/符号链接；flags、多路径、目录/gitlink、pathspec、Shell 包装与普通 allowlist 绕过全部失败关闭，并明确 prompt-only backend 不具机械保护。 |
| 2026-09-20 | 更新 | [moot-court](skills/moot-court/) | v1.2.1 | **Runtime 分级验证门禁**：按命令入口、模型、子任务、落盘、四发言短闭环和完整民事流程逐级验收；Claude Code短闭环实测通过但有语义发现，完整候选仍待验证；WorkBuddy、千问办公等办公类Agent列入后续实测。 |
| 2026-09-19 | 正式发布 | [legal-skill-alignment](skills/legal-skill-alignment/) | v1.0.7 | **迁移公开发布（自私有仓整树快照迁移）**：写法律 Skill 前的五问目标对齐（question-set/v1），把零散经验／办案 SOP／咨询记录厘清为结构化 Legal Skill Brief v1 交给 skill-creator 编译；私有仓内部技能引用泛化为通用表述（五问流程与 Brief 契约无变更）；evals 附 2026-08-23 独立复核全套 sha256 固化证据。 |
| 2026-09-19 | 正式发布 | [legal-skill-evaluation](skills/legal-skill-evaluation/) | v0.8.12 | **迁移公开发布（自私有仓整树快照迁移）**：法律 Skill 分层质量评测（skill-lint 通用门禁 + 三份测试材料／六维度／律师 taste 领域评测 + 最小修复单元定位）；修正 frontmatter 版本漂移（0.8.1→0.8.12）与 homepage；20 例 capability suite 执行证据链与 suite／receipt 双门禁齐全。 |
| 2026-09-18 | 更新   | [yuandian-law-search](skills/yuandian-law-search/)                     | v1.9.1  | **归档失败与响应交付解耦（issue #158 修复）**：归档目录不可写只降级 stderr 告警，不再吞掉已取得的 API 响应、不自动重试（杜绝误判重试重复扣积分）；新增 `--no-archive` 关闭全部本地留存（查重仍读已有归档）与 `--archive-dir`/`YD_ARCHIVE_DIR` 自定义归档目录；修正 `--no-report` 失实语义；补 4 项无网络故障注入回归。 |
| 2026-09-18 | 更新   | [tingwu-asr](skills/tingwu-asr/)                                       | v0.4.4→v0.4.6 | **跨 runtime 鲁棒性 + 异步监控会话无关化 + OSS 上传代理隔离**：cryptography≤41 OpenSSL 探测死循环自动绕过；监控改 nohup 脱离会话 + 恢复接管四步（进程丢失≠任务丢失）；上传 session 默认 trust_env=False 直连国内 OSS（常驻代理掐断 771MB 上传的根治，TINGWU_OSS_USE_PROXY=1 逃生阀），yt-dlp 不受影响；：上传 session 默认 `trust_env=False` 无条件忽略环境代理直连国内 OSS——v0.4.5 只做了文档提醒，常驻 Clash 代理仍会掐断 771MB 级大文件分片上传（50% 处 ProxyError）；`TINGWU_OSS_USE_PROXY=1` 逃生阀恢复旧行为；requests 兜底 PUT 同样隔离；yt-dlp 下载不受影响。新增 5 用例代理隔离回归测试。 |
| 2026-09-18 | 更新   | [piclist-upload](skills/piclist-upload/)                               | v1.4.0  | **跨系统兼容性根修 + 两个存量 bug**：脚本去 bash4+ 依赖（关联数组→换行列表），macOS 自带 bash 3.2 开箱即用（旧版 `declare -A` 直接报错，v1.1.1 只改 shebang 未根治，`/usr/bin/env bash` 在 macOS 仍解析到 3.2）；`bc`→`awk`、`lsof` 缺失回退 `/dev/tcp`；修复重复引用图片在本地文件删除后留死链（现复用已传 URL）；修复路径含括号（如 `file (1).png`）在首个 `)` 截断解析失败。 |
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
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/wechat-article-fetch-1.4.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/legal-ocr/"><strong>legal-ocr</strong></a></td>
<td>工具·OCR</td>
<td style="word-break:break-word">OCR、扫描识别、图片文字识别和文档识别工具，支持 PDF、图片、Office 文档和 URL 转 Markdown；法律材料可进行保守的术语与文书结构优化</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.5.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/legal-ocr-1.6.0.zip">下载</a></td>
<td>推荐统一入口</td>
</tr>
<tr>
<td><a href="skills/funasr-transcribe/"><strong>funasr-transcribe</strong></a></td>
<td>工具·ASR</td>
<td style="word-break:break-word">本地语音识别服务，将音频/视频转录为带时间戳的 Markdown，支持说话人分离、会议记录、视频字幕、播客转录</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.9.4</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/funasr-transcribe-1.9.4.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/tingwu-asr/"><strong>tingwu-asr</strong></a></td>
<td>工具·ASR</td>
<td style="word-break:break-word">阿里云通义听悟云端语音转录，适用于长音频、高精度场景，支持说话人分离和 AI 摘要生成</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v0.3.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/tingwu-asr-0.4.6.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/universal-media-downloader/"><strong>universal-media-downloader</strong></a></td>
<td>工具·下载</td>
<td style="word-break:break-word">输入视频网站/播客平台链接后自动下载，支持抖音/B站/YouTube/小宇宙等平台，可下载字幕和音频</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v0.2.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/universal-media-downloader-0.5.1.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/douyin-batch-download/"><strong>douyin-batch-download</strong></a></td>
<td>工具·下载</td>
<td style="word-break:break-word">抖音视频批量下载工具，基于 F2 框架，支持单个/批量博主下载，自动 Cookie 管理，差量更新机制</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.8.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/douyin-batch-download-1.8.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/dingtalk-minutes/"><strong>dingtalk-minutes</strong></a></td>
<td>工具·会议</td>
<td style="word-break:break-word">基于钉钉官方 dws CLI 封装 AI 听记（妙记）只读能力：列表/摘要/语音转写原文/关键词/待办/音频地址；本地归档与增量同步（archive 按 YYMMDD_标题 命名，index.json 记录同步状态）；镜像 transcript/summary/todos 到外部文件夹</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v0.7.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/dingtalk-minutes-1.1.0.zip">下载</a></td>
<td>使用需自行安装 dws CLI、开启组织 CLI 访问开关并扫码授权</td>
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
<td style="word-break:break-word">元典检索机制感知型法律研究中间层：先做轻量案件研判、正反命题和查询矩阵，再按向量／关键词／结构化字段调用 API 或 MCP，复核对位度并生成可追溯法律检索报告</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.8.9</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/yuandian-law-search-1.9.1.zip">下载</a></td>
<td>真实 API 调用需配置 Key；离线检索规划无需</td>
</tr>
<tr>
<td><a href="skills/court-sms/"><strong>court-sms</strong></a></td>
<td>通用·案件管理</td>
<td style="word-break:break-word">法院短信识别与文书下载技能，自动解析法院短信（文书送达、立案通知、开庭提醒等），提取案号、当事人、下载链接，下载文书并归档到对应案件目录</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.5.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/court-sms-1.5.1.zip">下载</a></td>
<td>参考自 <a href="https://github.com/Lawyer-ray/FachuanHybridSystem">法穿</a></td>
</tr>
<tr>
<td><a href="skills/invoice-organizer/"><strong>invoice-organizer</strong></a></td>
<td>通用·报销整理</td>
<td style="word-break:break-word">整理一批发票/票据 PDF（增值税普通发票、铁路电子客票、住宿交通餐饮等），按购买方抬头匹配所属案件项目，向上回溯读取项目上下文自动填补事由，复制归档（原件不动）并出具报销清单（可切换消费清单/对账流水）</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v0.1.1</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/invoice-organizer-0.1.1.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/new-case/"><strong>new-case</strong></a></td>
<td>通用·案件管理</td>
<td style="word-break:break-word">将案件/咨询材料整理成标准化目录结构。支持诉讼案件（12目录）和潜在项目/咨询（3目录）两种预设，自动生成案件信息看板、工时记录和期限管理文件</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.3.5</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/new-case-1.4.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/litigation-analysis/"><strong>litigation-analysis</strong></a></td>
<td>通用·诉讼</td>
<td style="word-break:break-word">诉讼分析工具，支持起诉状与证据分析、判决书深度分析、庭审笔录复盘。覆盖诉讼全流程：案件初期评估→判决分析→庭审复盘，生成内部版/研究版/客户版三层输出，支持上诉/再审决策支持</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.4.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/litigation-analysis-1.4.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/moot-court/"><strong>moot-court</strong></a></td>
<td>通用·诉讼</td>
<td style="word-break:break-word">基于案卷自动组织多角色模拟庭审：法官与民事原被告／刑事控辩通过书记员记录交换发言；支持版本化材料、取消重派与进度恢复，交付庭审笔录、争点复盘和庭前补强清单</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.2.1</td>
<td></td>
<td></td>
</tr>
<tr>
<td><a href="skills/contract-copilot/"><strong>contract-copilot</strong></a></td>
<td>通用·合同</td>
<td style="word-break:break-word">合同起草与审查助手，基于分层分析与四步流程，输出可执行的风险清单、起草骨架、修改建议、推荐措辞和审查意见书，支持批注与修订两种文档处理方式</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.6.3</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/contract-copilot-1.6.3.zip">下载</a></td>
<td><a href="https://github.com/cat-xierluo/contract-copilot.skill">独立仓库</a></td>
</tr>
<tr>
<td><a href="skills/legal-case-analysis/"><strong>legal-case-analysis</strong></a></td>
<td>通用·分析</td>
<td style="word-break:break-word">通用法律分析技能，基于案件材料、咨询材料、合同资料、证据材料或检索结果进行法律分析、案件研判、风险评估与诉讼/非诉策略；前置分析引擎，报告为可选交付形态</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v0.3.3</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/legal-case-analysis-1.0.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/legal-proposal-generator/"><strong>legal-proposal-generator</strong></a></td>
<td>通用·文书</td>
<td style="word-break:break-word">根据案件材料或沟通记录生成各类法律服务文档（诉讼方案、咨询报告、非诉方案、建议书、沟通报告、结案汇报等）。采用模块化架构自动匹配场景，生成接近定稿质量的专业文档</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v0.3.1</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/legal-proposal-generator-0.3.2.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/legal-client-brief/"><strong>legal-client-brief</strong></a></td>
<td>专业·行业追踪</td>
<td style="word-break:break-word">面向既有客户的每日、每周或事件增量追踪：在白名单内生成完整简报、朋友圈和公众号三件套，校验窗口、案例、跨渠道事实与 A4 PDF</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.1.0</td>
<td style="text-align:center">待发布</td>
<td>不自动改名或外发</td>
</tr>
<tr>
<td><a href="skills/legal-industry-report/"><strong>legal-industry-report</strong></a></td>
<td>专业·行业研究</td>
<td style="word-break:break-word">面向公开展示与广泛分发的月度/季度行业报告：通过行业规则包组织市场、产业链、政策监管、企业、法律风险与服务机会，并生成可追溯的正式报告包</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.1.0</td>
<td style="text-align:center">待发布</td>
<td>律师复核前为 PUBLIC_REVIEW</td>
</tr>
<tr>
<td><a href="skills/legal-text-format/"><strong>legal-text-format</strong></a></td>
<td>通用·文书</td>
<td style="word-break:break-word">将法律文本（法律条文或法律案例）转换为规范的 Markdown 格式，采用 archive 归档结构存储。推荐与 <a href="skills/wechat-article-fetch/"><strong>wechat-article-fetch</strong></a> 配合使用实现完整工作流</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.2.2</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/legal-text-format-1.2.2.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/legal-qa-extractor/"><strong>legal-qa-extractor</strong></a></td>
<td>通用·文书</td>
<td style="word-break:break-word">从律师与客户沟通记录中提取有价值的法律问答对，生成结构化知识库内容。支持严格客户信息脱敏处理，适用于整理咨询记录、创建问答知识库、准备内容营销素材</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.1.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/legal-qa-extractor-1.1.0.zip">下载</a></td>
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
<td style="word-break:break-word">中国发明与实用新型专利分析工具，支持10种场景；以 A/B/C/D 证据门禁、无网址多条款法源登记和2026年指南影响映射约束侵权、无效、FTO、规避设计、估值和可视化结论</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v2.2.0</td>
<td style="text-align:center">待发布</td>
<td><a href="https://github.com/cat-xierluo/patent-analysis.skill">独立仓库</a></td>
</tr>
<tr>
<td><a href="skills/patent-download/"><strong>patent-download</strong></a></td>
<td>工具·知产</td>
<td style="word-break:break-word">专利 PDF 批量下载工具，Google Patents 为首选通道（免费免登录），支持多平台、自动处理申请号和公告号格式；凭证环境变量化 + 防泄露自检</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v2.8.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/patent-download-2.7.1.zip">下载 v2.7.1</a></td>
<td>本仓库</td>
</tr>
<tr>
<td><a href="skills/code2patent/"><strong>code2patent</strong></a></td>
<td>专业·知产</td>
<td style="word-break:break-word">从已开发代码项目中提取技术实现证据，围绕候选专利方案生成算法/软件类说明书式技术交底书，并以"权利要求布局卡 → 发明专利初稿"两步法生成接近可申报版的中国发明专利起草材料；内置《专利审查指南》撰写规则、计算机程序发明保护主题提示和 agent 速查卡</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.6.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/code2patent-1.6.0.zip">下载</a></td>
<td><a href="https://github.com/cat-xierluo/code2patent.skill">独立仓库</a></td>
</tr>
<tr>
<td><a href="skills/opc-legal-counsel/"><strong>opc-legal-counsel</strong></a></td>
<td>专业·顾问</td>
<td style="word-break:break-word">面向一人公司、单人创业者与小微企业的法律业务判断技能：识别经营主矛盾、跨领域风险、行动和升级边界；现行法条、税率、名录、地方政策与平台规则通过工具中立协议交由法律数据库、MCP 或官方来源核验</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.0.1</td>
<td style="text-align:center">待发布</td>
<td><a href="https://github.com/cat-xierluo/opc-legal-counsel.skill">独立仓库</a></td>
</tr>
<tr>
<td><a href="skills/legal-visualization/"><strong>legal-visualization</strong></a></td>
<td>专业·可视化</td>
<td style="word-break:break-word">面向法律业务场景的法律图解与图表生成技能，把案件、合同、合规、交易、证据链和诉讼流程整理成关系图/流程图/时间轴/风险图；通过 VizSpec 2.1、几何守恒视觉编译、三套受众主题、容器感知重叠与文字容量门禁阻断坏图，默认交付 .drawio + .svg + .png 三件套</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v0.8.2</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/legal-visualization-0.8.2.zip">下载 v0.8.2</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/legal-skill-alignment/"><strong>legal-skill-alignment</strong></a></td>
<td>专业·Skill开发</td>
<td style="word-break:break-word">写法律 Skill 前的前置目标对齐：通过苏格拉底式五问（question-set/v1）把零散的法律经验、办案 SOP、咨询记录厘清为结构化 Legal Skill Brief v1，交给 skill-creator 等下游编译；含法源溯源三列、敏感材料边界与 blocker/warning 待确认清单</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v1.0.7</td>
<td></td>
<td></td>
</tr>
<tr>
<td><a href="skills/legal-skill-evaluation/"><strong>legal-skill-evaluation</strong></a></td>
<td>专业·Skill开发</td>
<td style="word-break:break-word">法律 Skill 分层质量评测：消费 skill-lint 通用质量结论，再用三份测试材料、通用六维度、场景微调与律师 taste 评估法律产出并定位最小修复单元；含评测包结构化契约、运行收据门禁与指令稳定性边界</td>
<td style="text-align:center">CC-BY-NC</td>
<td style="text-align:center">v0.8.12</td>
<td></td>
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
<td style="text-align:center">v2.12.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/pdf-processor-2.13.0.zip">下载 v2.10.2</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/img2pdf/"><strong>img2pdf</strong></a></td>
<td>工具·PDF排版</td>
<td style="word-break:break-word">将图片或 PDF 页面按 N 张/页编排为标准化 A4 PDF，或将长截图渲染为单张自适应高度 PDF；支持 1/2/3/4 张每页布局，自动检测图片横竖方向，适用于法律证据材料整理（手机截图、视频取证截图、现场照片、长截图等）</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.2.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/img2pdf-1.2.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/pdf-organizer/"><strong>pdf-organizer</strong></a></td>
<td>通用·PDF整理</td>
<td style="word-break:break-word">法律 PDF 文书整理工具：按内容拆分、合并或直接重命名 OCR 后双层扫描件，生成页面索引、manifest 草稿和下游交接文件；支持旋转与倾斜校正，不做 OCR 或压缩</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v0.5.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/pdf-organizer-0.6.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/course-generator/"><strong>course-generator</strong></a></td>
<td>工具·课程</td>
<td style="word-break:break-word">将长转录稿或文献整理为可独立阅读、可溯源验收的课程：以确定性来源块、细粒度素材去向、预承诺覆盖词和真实正文证据守住长材料精华，并用脚本自动收口可推导的 source refs、证据与图片映射；支持用户词典、专名保真、图片克制插入和确定性验收，归档/定制方案提取仅在明确要求时执行</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v2.10.1</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/course-generator-2.10.2.zip">下载</a></td>
<td>下载版 v2.3.3</td>
</tr>
<tr>
<td><a href="skills/transcription-corrector/"><strong>transcription-corrector</strong></a></td>
<td>工具·校对</td>
<td style="word-break:break-word">ASR 转录稿纠错与轻度优化工具：按用户词典统一替换同音字与英文专有名称漂移，可选合并同发言人发言、清理标点和切分段落；与 course-generator 共用词典格式，原始文件保持不动并双写归档</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.0.8</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/transcription-corrector-1.0.8.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/video-screenshot/"><strong>video-screenshot</strong></a></td>
<td>工具·视频处理</td>
<td style="word-break:break-word">从录屏视频中以有界高召回抽取证据截图并过滤切换中间态；可用本地 OCR 多锚点与无文字图像主体生成不保存原文的证据线索包，再为普通或较弱多模态模型提供封闭分类/概括及只做减法的去重审计</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v0.8.2</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/video-screenshot-0.8.2.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/article2book/"><strong>article2book</strong></a></td>
<td>工具·内容</td>
<td style="word-break:break-word">现有内容资产再组织技能。基于文章、专栏、课程讲稿、逐字稿、访谈、课件、会议纪要、案例材料、PDF 文本、Word 文档和笔记等素材，判断最适合转化为书、小册子、课程、系列文章、实务手册或知识库，并输出精简策划意见</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.0.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/article2book-1.0.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/svg-article-illustrator/"><strong>svg-article-illustrator</strong></a></td>
<td>工具·配图</td>
<td style="word-break:break-word">AI 驱动的 SVG 文章配图生成工具，支持动态 SVG、静态 SVG 和 PNG 导出三种模式，专为公众号文章等需要丰富视觉内容的平台设计</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.0.5</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/svg-article-illustrator-1.0.5.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/handdrawn-article-illustrator/"><strong>handdrawn-article-illustrator</strong></a></td>
<td>工具·配图</td>
<td style="word-break:break-word">手绘风格文章配图：先理解文章写 Image Brief 和 prompt，再用内置生图能力出图；配色通过主题文件（themes/）配置，内置蓝灰/墨黑/赭石三套预设，可切换或自定义</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.1.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/handdrawn-article-illustrator-1.1.0.zip">下载</a></td>
<td>配色可定制</td>
</tr>
<tr>
<td><a href="skills/svg-book-illustrator/"><strong>svg-book-illustrator</strong></a></td>
<td>工具·配图</td>
<td style="word-break:break-word">书籍/文章 SVG 配图生成工具，专注于架构图、流程图、层次图等专业技术配图，针对印刷出版场景优化，字号间距按物理尺寸反推</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.8.10</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/svg-book-illustrator-1.9.2.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/piclist-upload/"><strong>piclist-upload</strong></a></td>
<td>工具·图床</td>
<td style="word-break:break-word">通过 PicList HTTP Server 将 Markdown 中的本地图片上传到图床，自动替换为云端链接，支持批量处理和跨设备访问</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.2.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/piclist-upload-1.4.1.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/md2word/"><strong>md2word</strong></a></td>
<td>工具·格式转换</td>
<td style="word-break:break-word">将 Markdown 文档转换为专业格式 Word 文档，支持法律文书标准，自动应用字体、字号、行距和段落格式</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.3.5</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/md2word-1.3.5.zip">下载</a></td>
<td><a href="https://github.com/cat-xierluo/md2word.skill">独立仓库</a></td>
</tr>
<tr>
<td><a href="skills/de-ai-polish/"><strong>de-ai-polish</strong></a></td>
<td>工具·写作</td>
<td style="word-break:break-word">检测并去除文章正文中的 AI 化表述模式。无样本时执行最小清理；支持作者证据卡、十维 Voice Calibration、本机私有 VoiceAnchor、功能性列举保护、标题结构保护、修复伪影复扫和候选绑定门禁</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v3.2.6</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/de-ai-polish.skill/releases/download/v2.0.1/de-ai-polish-2.0.1.zip">下载 v2.0.1</a></td>
<td><a href="https://github.com/cat-xierluo/de-ai-polish.skill">独立仓库</a></td>
</tr>
<tr>
<td><a href="skills/video-compressor/"><strong>video-compressor</strong></a></td>
<td>工具·格式转换</td>
<td style="word-break:break-word">视频压缩与静默片段剪切工具，使用 FFmpeg CRF 模式压缩视频，自动检测硬件选择最优编码方案（Apple Silicon VideoToolbox 硬件加速），支持检测并去除静默静止片段</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.3.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/video-compressor-1.5.1.zip">下载</a></td>
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
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/apple-smart-schedule-0.2.0.zip">下载</a></td>
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
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/agent-email-0.4.1.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/project-init/"><strong>project-init</strong></a></td>
<td>工具·项目管理</td>
<td style="word-break:break-word">项目初始化工具，读取全局协议，分析项目实际情况，按配置检测项目类型并生成项目特定的 AGENTS.md、CLAUDE.md、docs/ 文档体系与 .claude/ 配置</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.2.4</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/project-init-1.2.4.zip">下载 v1.2.4</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/legal-harness-init/"><strong>legal-harness-init</strong></a></td>
<td>工具·Agent配置</td>
<td style="word-break:break-word">面向法律工作者初始化和增量治理 AGENTS.md/CLAUDE.md：三种引导模式、三档隐私治理、法律安全基线、受管区块安全合并及新会话行为验证</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v0.5.2</td>
<td style="text-align:center"></td>
<td>写入成功不等于已加载；无法新建会话时标 NOT_VERIFIED</td>
</tr>
<tr>
<td><a href="skills/multica-skill-update/"><strong>multica-skill-update</strong></a></td>
<td>工具·Skill同步</td>
<td style="word-break:break-word">Multica 工作区 Skill 同步工具：维护来源清单（manifest.json），批量导入/更新 Multica skill 数据库；支持 init（初始化导入）/ update（更新刷新）/ plan（预览）三模式，结果结构化报告；可接 Autopilot 每周定时同步</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v0.1.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/multica-skill-update-0.5.3.zip">下载</a></td>
<td>需安装 multica CLI</td>
</tr>
<tr>
<td><a href="skills/skill-manager/"><strong>skill-manager</strong></a></td>
<td>工具·Skill开发</td>
<td style="word-break:break-word">管理 AI Agent Skills 的安装、同步、卸载和列表查看，支持本地路径和 GitHub 仓库/子目录，自动识别 Codex、Claude Code 和 OpenClaw 目标目录并批量处理</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.7.2</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/skill-manager-1.7.2.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/skill-lint/"><strong>skill-lint</strong></a></td>
<td>工具·Skill开发</td>
<td style="word-break:break-word">Skill 创建预检与可靠性验收工具，支持具体 Harness 失效模式批量定位、旧版指令失稳识别、领域 checker 双向充分性边界、硬要求来源定位、逐约束追踪、验证模态/产物阶段匹配、Ed25519 签名证据与多轮漂移门禁、业务流和安全风险审查</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v2.9.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/skill-lint-2.9.0.zip">下载 v2.8.0</a></td>
<td>正式验收需区分 Harness 审查、指令稳定性与领域功能验证</td>
</tr>
<tr>
<td><a href="skills/verification-gate/"><strong>verification-gate</strong></a></td>
<td>工具·Skill开发</td>
<td style="word-break:break-word">代码改完后的验证门禁 skill，跑 8 阶段验证（构建/类型/lint/单测/e2e 功能/真机/安全/diff），其中 e2e 功能 + 真机是 READY 的硬门禁，覆盖 Tauri 桌面/Web/服务/Skill 四类项目分支；本地即可跑完整验证，CI 是可选自动化强化</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.0.2</td>
<td style="text-align:center"></td>
<td>编译过 ≠ 功能可用，e2e + 真机为完成硬门禁</td>
</tr>
<tr>
<td><a href="skills/git-batch-commit/"><strong>git-batch-commit</strong></a></td>
<td>工具·Git</td>
<td style="word-break:break-word">智能 Git 批量提交工具，自动将混合的文件修改按类型分类并创建多个清晰聚焦的提交，使用标准化的提交信息格式</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.4.1</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/git-batch-commit-1.4.2.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/git-workflow/"><strong>git-workflow</strong></a></td>
<td>工具·Git</td>
<td style="word-break:break-word">Git 工作流安全助手，覆盖分支管理、长期集成分支、Monorepo 安全合并、PR、冲突处理、安全回退、分支清理和身份绑定 safe-push</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.8.2</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/git-workflow-1.8.7.zip">下载 v1.6.0</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/cross-agent-coordination/"><strong>cross-agent-coordination</strong></a></td>
<td>工具·Agent协作</td>
<td style="word-break:break-word">跨平台 Agent 任务协调枢纽，围绕项目任务源分配任务、标记归属、能力路由并保留交接上下文</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.0.0</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/cross-agent-coordination-1.0.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/multi-agent-orchestration/"><strong>multi-agent-orchestration</strong></a></td>
<td>工具·Agent协作</td>
<td style="word-break:break-word">Orca-first 多 Agent 本地编排，支持 Wave receipt、worktree/terminal UI、Run/Task/Dispatch、worker transcript、Orca 429 idle 巡检与错峰唤醒、严格 lifecycle 结算、五后端总控、Harness 层级门禁、Wave Autopilot live-session 快路径与 L2 跨会话持久 controller core</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v2.27.6</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/multi-agent-orchestration-2.27.4.zip">下载 v2.27.4</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/release-workflow/"><strong>release-workflow</strong></a></td>
<td>工具·发布</td>
<td style="word-break:break-word">GitHub 项目全流程发布工作流：版本号管理、CHANGELOG 同步、Release Notes 撰写、tag 创建、CI 构建监控、发布验证和历史清理，含 Tauri 桌面应用和 CI 故障排查专项指南</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.4.1</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/release-workflow-1.5.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/github-star-manager/"><strong>github-star-manager</strong></a></td>
<td>工具·Star管理</td>
<td style="word-break:break-word">GitHub Star 项目管理工具，从内容自动发现并 Star 项目，同步追踪已 Star 项目更新，生成可视化 Dashboard，支持分类管理和标签系统</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v0.6.2</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/github-star-manager-0.6.2.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/skill-publish-sync/"><strong>skill-publish-sync</strong></a></td>
<td>工具·发布</td>
<td style="word-break:break-word">将本地 Skills 同步到 ClawHub、腾讯 SkillHub 与联想开放平台，支持智能忽略过滤、平台独立白名单、增量同步与发布记录</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.7.1</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.08.06/clawhub-sync-1.6.1.zip">下载</a></td>
<td><a href="https://github.com/openclaw/clawhub/blob/main/docs/skill-format.md">ClawHub 要求 MIT-0</a></td>
</tr>
<tr>
<td><a href="skills/subtree-publish/"><strong>subtree-publish</strong></a></td>
<td>工具·发布</td>
<td style="word-break:break-word">将 monorepo 中的子目录通过 git subtree 推送到独立 GitHub 仓库，支持注册清单、变更自动检测、增量推送</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.7.1</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.09.21/subtree-publish-1.7.1.zip">下载</a></td>
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
| mineru-ocr               | v1.2.0 | 已归档（2026-09-04）。OCR 能力由 [legal-ocr](skills/legal-ocr/) 统一覆盖，推荐使用 legal-ocr 作为唯一入口。原 skill 依然可用：需自行配置 MinerU API Token 才能正常使用 |
| paddle-ocr               | v1.1.1 | 已归档（2026-09-04）。OCR 能力由 [legal-ocr](skills/legal-ocr/) 统一覆盖，推荐使用 legal-ocr 作为唯一入口。原 skill 依然可用：需自行配置 PaddleOCR API 才能正常使用 |
| multi-search             | v1.1.0 | 智能多主题深度研究工具，功能被[multi-agent-orchestration](skills/multi-agent-orchestration/) v1.16+ 内置的并行 Subagent 能力覆盖，停止独立维护 |
| skill-architect          | v1.6.2 | 已重定位为[skill-lint](skills/skill-lint/) v2.0.0，创建能力不再作为本仓库独立入口维护                                                          |
| minimax-image-understand | v0.1.0 | 各平台已原生支持 MiniMax MCP 图像理解，无需独立 skill                                                                                         |
| minimax-web-search       | v0.1.1 | 各平台已原生支持 MiniMax MCP 网络搜索，无需独立 skill                                                                                         |
| repo-research            | v0.7.0 | 功能较简单，不再维护                                                                                                                          |
| zhihe-legal-research     | v1.2.2 | 已归档（2026-08-09 复测：报告接口自 2026-04-08 起 has_report 持续 false，智合法律研究已整体迁移至新平台 zhiexa.com；老 API submit 端点持续 500，无法提交新问题。技能暂不可用，待后续迁移至新平台 zhiexa.com）。技能目录已从仓库移除                                                                                                          |

## 🔒 隐私守门（pre-commit）

本仓库公开，**禁止提交任何真实当事人/案件信息**。启用守门钩子（克隆后执行一次）：

```bash
git config core.hooksPath .githooks
```

之后每次提交自动拦截：手机号 / 18 位身份证 / 座机 / 本机绝对路径 / 真实法院案号（示例请用 `(2026)苏XXXX民初XXXX号` 占位形式），以及 `.githooks/local-denylist` 中的自定义敏感词（该文件由 `.git/info/exclude` 排除，本地维护、绝不入库）。确认内容确属虚构时可用 `git commit --no-verify` 绕过。
