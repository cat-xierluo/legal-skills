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
| 2026-08-27 | 更新   | [multi-agent-orchestration](skills/multi-agent-orchestration/)         | v2.8.1 | **并行总控可靠性修复**：守夜探针精确区分额度、配置、认证、网络和超时，只有同一 watcher 观察到 `quota → available` 才唤醒 PM；Orca worktree create 固定到已验证的项目仓并核对 repoId，阻断符号链接 Skill cwd 导致的错仓；判活拆分运行时活性与业务进展，静止信号不再直接等同假死 |
| 2026-08-26 | 更新   | [course-generator](skills/course-generator/)                           | v2.9.4 | **弱模型前向实测与账本 fail-fast**：GLM 三门真实课程首轮均通过 14/14 领域门禁、主模型语义评分 90—93；第二轮配额失败严格记为 0/3，并据完整失败样本新增生成前素材账本预检，统一 include/skip 的连续 `MAT-*` 编号、阻断 `SKIP-*` 平行命名；同步保留个人判断、事故转述和产品效果的认识论边界，稳定性继续标记 `NOT_VERIFIED` |
| 2026-08-26 | 更新   | [md2word](skills/md2word/)                                             | v1.3.5  | **全书本地图片路径修复**：`--book` 在合并前按各章 Markdown 自己的目录重定位 Markdown/HTML 本地相对图片，含空格、URL 编码和可选标题的路径均可嵌入；单章与远程图片行为不变 || 2026-08-25 | 新增   | [industry-research-report](skills/industry-research-report/)           | v0.7.0 | **行业法律调研报告（获客端）**：**v0.7.0 全面精简版式（Less is more：页眉只留报告编号、页脚只留页码，砍掉横线/kicker/多列冗余装饰）**；输入 industry/region/focus/depth，输出精排 A4 PDF 行业法律调研报告；蓝皮书体例（深蓝 #1B3C59 + 金色 #D4AF37 + 白色页面）+ 4 个封面变体（顶金带+底金边+REPORT NO. 徽章工艺感）+ 5 个律师常见调色板；**v0.6.2 书籍连续流改造**（DEC-IR-019）：放弃杂志固定画布裁切，改 @page margin box 跨页 header/footer + 章节自然流动不截断 + 大边距（天头80px/地脚60px/左右56px≈21/16/15mm）；**v0.6.1 杂志Studio book-style 排版优化**（加大字号 IR 22/12pt + 行高 2.0）；**v0.6.0 三连环视觉修复**（封面 CSS 注入 / px 单位 / 按 H2 拆章）；**v0.5.0 report_kind 字段 + 正文设计系统差异化路由**（IR 蓝皮书感 vs WB 通讯感，12 维度全表）；内置 report-profile.md 个性化配置 + 首启向导；行业特定信源映射内置 20 个高频行业；数据源走企查查 MCP + 网络检索 5 级信源优先级；md 基底 → jinja2 → Playwright + Chrome headless，一键出精排 A4 PDF |
| 2026-08-25 | 新增   | [weekly-legal-briefing](skills/weekly-legal-briefing/)                 | v0.6.0 | **定时法律研报（留存端）**：**v0.6.0 继承 v0.7.0 精简版式（页眉页脚只留编号/页码）**；配置一次，定期自动生成行业/法律研报草稿（如"科技型制造企业 周报"）；**v0.5.2 书籍连续流继承**（Skill 1 v0.6.2：@page margin box 跨页 header/footer + 章节自然流动不裁切 + 大边距）；**v0.5.0 三连环视觉修复同步**；**v0.4.0 新增 2 个专属轻量封面 (W1-minimal / W2-tag-bar) + 正文设计系统强烈差异化**（字号小 + 灰色细线 + 单栏目录，与 IR 蓝皮书感拉开）；白名单信源制（白名单外默认丢弃）+ 案例必带案号 + 案号裁判文书网回查；输出文件一律带 `_DRAFT` 标记，**永不自动外发**（硬约束，发布动作物理上留给人工）；渲染管线 symlink 复用 industry-research-report，避免双份维护；附 WorkBuddy / OpenClaw cron / GitHub Actions 三平台部署说明 |
| 2026-08-25 | 更新   | [md2word](skills/md2word/)                                             | v1.2.6  | **Word 出版逃逸修复**：多列长表头受正文区硬预算约束，`tblW`、grid 与单元格宽度统一；普通及显式居中表题取消缩进且保留文字样式；引用块 `[^label]` 正确生成原生 Word 脚注，不再显示字面 marker |
| 2026-08-24 | 更新   | [course-generator](skills/course-generator/)                           | v2.8.1 | **课程产物契约化**：新增 `course-manifest.json`，以稳定 SRC/MAT/IMG 关系绑定来源、素材、章节和图片；标准库验证器精确检查文件、素材映射与图片集合/目标/顺序，13 类正反例覆盖旧版漏报；长材料改用索引化两遍流程，生成不再自动归档，并收窄与转录纠错、讲课复盘、成书 Skill 的触发边界 |
| 2026-08-24 | 更新   | [lecture-review](skills/lecture-review/)                               | v1.2.1 | **讲课复盘三轮迭代**：v1.1.0 新增 deck 课件对照（六段 → 七段：实讲/半讲/跳过/挪位回收/主动宣判五枚举 + min/页双口径）；v1.2.0 高级模式课程结构复盘（评人/评课分离 + 双向比对三方向）；v1.2.1 产物落点约定（七段报告/review.md/stats.json/profile 落点表 + 评课不进讲师档案）；脚本 `analyze_stats.py` 新增 `--deck` 课件解析与 `self_check` 三个候选生成器（module_distribution / near_dup_pages / title_term_index），references/metrics.md 同步补「课件对照」节；`references/structural-review-template.md` 沉淀九节+附录的高级模式复盘骨架 |
<td><a href="skills/course-generator/"><strong>course-generator</strong></a></td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.08.06/course-generator-2.3.3.zip">下载</a></td>
<td style="word-break:break-word">ASR 转录稿纠错与轻度优化工具：按用户词典统一替换同音字与英文专有名称漂移，可选合并同发言人发言、清理标点和切分段落；与 course-generator 共用词典格式，原始文件保持不动并双写归档</td>
<td><a href="skills/multi-agent-orchestration/"><strong>multi-agent-orchestration</strong></a></td><td style="text-align:center">MIT</td>
<td style="text-align:center">v2.8.1</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.08.06/multi-agent-orchestration-1.20.5.zip">下载 v1.20.5</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/release-workflow/"><strong>release-workflow</strong></a></td>
<td>工具·发布</td>
<td style="word-break:break-word">GitHub 项目全流程发布工作流：版本号管理、CHANGELOG 同步、Release Notes 撰写、tag 创建、CI 构建监控、发布验证和历史清理，含 Tauri 桌面应用和 CI 故障排查专项指南</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v1.4.1</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.08.06/release-workflow-1.4.0.zip">下载</a></td>
<td></td>
</tr>
<tr>
<td><a href="skills/github-star-manager/"><strong>github-star-manager</strong></a></td>
<td>工具·Star管理</td>
<td style="word-break:break-word">GitHub Star 项目管理工具，从内容自动发现并 Star 项目，同步追踪已 Star 项目更新，生成可视化 Dashboard，支持分类管理和标签系统</td>
<td style="text-align:center">MIT</td>
<td style="text-align:center">v0.6.2</td>
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.08.06/github-star-manager-0.6.2.zip">下载</a></td>
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
<td style="text-align:center"><a href="https://github.com/cat-xierluo/legal-skills/releases/download/v2026.08.06/subtree-publish-1.7.1.zip">下载</a></td>
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
| zhihe-legal-research     | v1.2.2 | 已归档（2026-08-09 复测：报告接口自 2026-04-08 起 has_report 持续 false，智合法律研究已整体迁移至新平台 zhiexa.com；老 API submit 端点持续 500，无法提交新问题。技能暂不可用，待后续迁移至新平台 zhiexa.com）。技能目录已从仓库移除                                                                                                          |

## 🔒 隐私守门（pre-commit）

本仓库公开，**禁止提交任何真实当事人/案件信息**。启用守门钩子（克隆后执行一次）：

```bash
git config core.hooksPath .githooks
```

之后每次提交自动拦截：手机号 / 18 位身份证 / 座机 / 本机绝对路径 / 真实法院案号（示例请用 `(2026)苏XXXX民初XXXX号` 占位形式），以及 `.githooks/local-denylist` 中的自定义敏感词（该文件由 `.git/info/exclude` 排除，本地维护、绝不入库）。确认内容确属虚构时可用 `git commit --no-verify` 绕过。
