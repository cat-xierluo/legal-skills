# 变更日志

本项目的所有重要变更都将记录在此文件。

## [1.1.2] - 2026-04-05

### 新增

- 归档汇报格式拆分到 `references/report-format.md`：三段式结构（归档确认 → 文书清单 → 传票特别提醒），SKILL.md 只保留引用
- 当事人提取优先级明确：文书内容（起诉状/传票）> API 返回 > 短信文本；短信中的称呼仅为接收人，不作为当事人

### 改进

- 归档目录策略改为自动创建：未找到匹配案件时直接在当前项目下新建 `{案号} {当事人与案由}/08 - 🏛️ 法院送达/`，不再询问用户
- 传票提醒在汇报末尾以 ⚠️ 高亮，包含开庭时间（追加星期几）、地点、审理程序

## [1.1.1] - 2026-04-05

### 改进

- 基础文书解析：下载后提取 PDF 首页文本，快速识别传票（开庭时间/地点）、通知书（缴费期限）、起诉状（案由/当事人）等关键信息并告知用户
- 归档格式拆分到 `references/archive-format.md`，SKILL.md 只保留引用
- 收紧功能描述至实际范围：移除案件信息更新、复杂案件匹配、日程提醒等未实现功能
- frontmatter description 去除 Playwright 硆名实现细节
- CHANGELOG 措辞修正：去除"Claude NLP"和"替代正则解析"的说法，正则规则仍在 `sms-patterns.json` 中配合使用
- 新增 Playwright 安装指引（CLI 和 MCP 两种方式）
- 短信类型分类表简化，仅保留展示解析结果

## [1.1.0] - 2026-04-04

### 改进

- 下载策略改为三层回退：curl API 直连（优先）→ Playwright CLI → Playwright MCP
- 实测确认 zxfw 后端 API（`getWsListBySdbhNew`）可无头调用，无需浏览器即可下载全部文书
- 将 API 端点、请求格式、响应字段写入 `references/sms-patterns.json`，后续同类型短信直接走 curl
- 去除 SKILL.md 中"执行者"写法，保持 agent 无关性
- frontmatter 规范化：description 改为第三人称，新增 license 字段（MIT），去除关键词堆砌
- 触发方式从独立章节合并到功能概述，用示例替代关键词列表
- 归档机制从 Markdown 改为结构化 JSON（`archive/YYYYMMDD_HHMMSS_{案号后4位}.json`），记录短信原文、解析结果、下载参数、归档路径
- 目录结构规范化：`config/sms-patterns.json` 移入 `references/`，新增 `archive/.gitkeep`
- 补充 CHANGELOG 1.0.0 的设计缘由和思路演进
- 新增 LICENSE.txt（MIT）

### 新增

- 多平台送达链接支持：除 zxfw 外，新增 `sd.gdems.com`（广东电子送达）和 `jysd.10102368.com`（集约送达）的链接识别
- 平台分级下载策略：zxfw 走 curl API 直连，gdems/jysd 无公开 API，直接回退到浏览器自动化
- `sms-patterns.json` 新增 `download_strategy` 字段，区分 `api_first`（有 API）和 `browser_only`（需浏览器）
- 基础文书解析：下载后提取 PDF 首页文本，快速识别传票（开庭时间/地点）、通知书（缴费期限）、起诉状（案由/当事人）等关键信息
- 归档格式拆分到 `references/archive-format.md`，SKILL.md 只保留引用
- 收紧功能描述至实际范围：移除案件信息更新、复杂案件匹配等未实现功能

## [1.0.0] - 2026-04-04

### 设计缘由

- 律师日常频繁收到法院送达短信（传票、通知书等），需要手动从全国法院送达平台下载文书并归档到案件目录
- 手动操作流程繁琐：复制链接 → 打开网页 → 下载 PDF → 重命名 → 移入目录 → 更新案件记录
- 参考 FachuanHybridSystem 的短信解析设计思路，将其核心逻辑转化为 Skill 格式，结合 agent 的自然语言理解能力与结构化正则规则（`references/sms-patterns.json`）进行短信解析

### 思路演进

1. 调研阶段：发现 FachuanHybridSystem 已实现短信解析 → 下载 → 归档的完整流水线
2. 适配阶段：将 Python/Django 服务架构映射为 Skill 工作流（agent 自然语言理解 + 结构化规则），无需部署额外服务
3. 当前阶段：以 JSON 配置参考文件替代硬编码规则，保持技能的可维护性和可扩展性

### 新增

- 法院短信智能分类（文书送达 / 信息通知 / 立案通知）
- 案号自动提取，支持多种标准格式（圆括号、方括号、六角括号）
- 当事人名称提取（公司名、诉讼对峙模式、角色前缀）
- 从 zxfw.court.gov.cn 链接中提取下载参数（qdbh、sdbh、sdsin）
- 三级案件匹配策略（案号精确 → 当事人双向 → 特征筛选）
- Playwright 两级回退下载（API 拦截 → 页面点击）
- 文书自动重命名并归档到案件目录
- 短信原文归档到 archive/
- 解析规则可配置化（`references/sms-patterns.json`）

### 致谢

本技能参考了 [FachuanHybridSystem（法穿）](https://github.com/Lawyer-ray/FachuanHybridSystem) 中短信解析模块的设计思路和解析规则（非直接复制代码）。详见 [`references/ATTRIBUTION.md`](references/ATTRIBUTION.md)。
