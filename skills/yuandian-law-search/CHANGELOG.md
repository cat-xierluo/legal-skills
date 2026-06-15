# 变更日志

## [1.7.4] - 2026-06-15

### 修复

- 修复 `keyword` / `case` / `regulation` 的 `--expand` 自动 OR 逻辑：参数解析层不再把 `--search-mode` 默认填成 `and`，处理函数可正确识别"用户未显式指定"并在扩展检索时切换为 OR。
- 修复 `references/03-report-consolidation.md` 与 `references/02-typical-workflows.md` 中重命名后的旧文件链接。
- 统一版本号：`SKILL.md`、`scripts/yd_search.py`、`scripts/MANIFEST.json`、根 `README.md` 与 marketplace 条目同步到 `1.7.4`。

### 改进

- 强化案件综合分析和标杆类案场景的检索执行约束：第一轮优先 `case-semantic`，关键词检索只保留 4-6 个高信息密度词，零命中时必须改用语义检索或 OR 复检。
- 补充 marketplace 条目，便于插件市场按当前版本发现和分发 `yuandian-law-search`。
- 调整 `.gitignore` 例外，使本技能的 `DECISIONS.md` 与 `TASKS.md` 可纳入版本控制。

## [1.7.3] - 2026-06-15

### 修正（v1.7.1 反思有误）

- v1.7.1 在"争议焦点识别"小节中错误地将二分法归入"用户原始争议焦点"——二分法实际是 AI **检索之后**才提炼出来的分析工具，不是用户最初提问的内容
- 真实情况：用户最初就已明确给出关键事实要素和法条抓手，**第一轮**应该直接用这些用户原话作为检索词，不需要先等"检索后再提炼二分法"
- **修正 `references/02-typical-workflows.md`**：
  - 删除"关键区分点"字段（避免诱导 AI 自己去找二分法）
  - 新增"用户已明确的论点"字段（强调直接用用户原话作检索词）
  - 关键提示新增"二分法是结果不是起点"
- 路径修正：因 v1.7.2 重命名 `00-typical-workflows.md` → `02-typical-workflows.md`，编辑目标相应更新

## [1.7.2] - 2026-06-15

### 整理
- **`references/` 序号重编**：6 个 `00-*.md` 工作流指南改为 `01-06` 顺序编号（按 SKILL.md Reference 文档索引的引用顺序），便于按序阅读和稳定排序
  - `01-keyword-expansion.md`（基础：关键词怎么扩）
  - `02-typical-workflows.md`（应用：典型场景）
  - `03-report-consolidation.md`（专题：报告整合）
  - `04-report-design-notes.md`（专题：报告设计原理）
  - `05-mcp-workflow.md`（专题：MCP 协同）
  - `06-enterprise-portrait.md`（专题：企业全息画像）
  - 同步更新 `SKILL.md`、`scripts/MANIFEST.json` 中所有引用

### 简化
- **"新接口策略矩阵"小节去重话术**：`SKILL.md` 调用策略章节尾部表格本身保留（hall-detect / enterprise-search / enterprise-base+summary / enterprise-list 四个接口在三种策略下的具体行为），仅去掉"新/旧接口"区分话术——所有接口统一视为同一层级，按其分层套用对应策略

## [1.7.1] - 2026-06-15

### 工作流补充（基于近期案件检索偏差复盘）

- **`references/00-typical-workflows.md` 新增 2 节强制工作流**：
  - **争议焦点识别优先场景**：第一轮检索前必须先填 5 字段识别表（行为主体 / 角色定位 / 行为模式 / 关键区分点 / 抗辩点），避免直接按泛化法律概念展开检索
  - **标杆案例对标检索场景**：用户第一轮提供标杆案例时，必须提取其"事实结构骨架"作为查询模板，并用"对标度评分"过滤命中案例
- **核心理念沉淀**：
  - 行业术语 > 法律术语（用户用什么行业说法就用什么行业说法作检索词，不要预先翻译成法律术语）
  - 二分法思维：争议焦点背后往往有关键二分，二分点决定结论方向
  - 主动找反面案例：搜完正面后专门搜一次"被告不担责""被告无过错"等反面表述，反面案例能反向锚定争议焦点的关键区分
- **典型反例**：错搜泛化法律概念 → 命中与案情不匹配的偏差案型；正搜基于用户原话 + 行业术语描述事实结构（语义检索）→ 命中对位案

## [1.7.0] - 2026-06-15

### 重构
- **目录结构重构**（按 skill-lint 审查建议解耦）：
  - 35 个 API 端点文档（`01-law-vector-search.md` ~ `35-enterprise-serious-illegal.md`）从 `references/` 迁入新建的 `endpoints/`
  - `references/MANIFEST.json` 同步迁入 `endpoints/MANIFEST.json`
  - `references/` 仅保留工作流指南，新增 6 个 `00-*.md`：
    - `00-keyword-expansion.md` — 关键词扩展三原则、`--expand` 参数、分阶段检索、策略兼容性
    - `00-typical-workflows.md` — 五大场景 + AI 向用户反馈的 8 条原则
    - `00-enterprise-portrait.md` — 企业信息类 4 个接口（`enterprise-search` / `base` / `summary` / `list`）的完整用法与 20 类 `--type` 维度
    - `00-report-consolidation.md` — consolidate 调用方式、项目子目录组织、目标目录归档规范
    - `00-report-design-notes.md` — 7 节"结论先行"的设计动机、反例、节号逻辑、质量要求
    - `00-mcp-workflow.md` — 元典 MCP 接入配置、Agent 三步法、ingest 子命令、模式选型表
- `templates/legal-research-report.md` 保留并明确为可维护的模板参考（`yd_search.py` 当前仍用代码内 f-string 渲染，模板作为格式约定）
- SKILL.md 由 809 行压到 494 行（-39%）：4 个大章节（关键词扩展、典型工作流、企业全息、MCP 协同）拆到 references/，7 节报告与目标目录归档保留短引用

### 发布治理
- `scripts/MANIFEST.json` 同步升到 1.7.0，完整覆盖 endpoints/ + references/ + templates/ 全部文件（之前仅列了 11 个 references，updater 实际未更新 12-35）
- README.md 中 `references/01~11-*.md` 改为 `endpoints/01~35-*.md`，`MANIFEST.txt` 改为 `MANIFEST.json`
- "版本演进"表格新增 v1.7.0 行

## [1.6.1] - 2026-06-15

### 改进
- 优化 `consolidate` 法律检索报告模板：从旧的"检索结果在前、结论在后"调整为 7 节结论先行结构，先呈现一句话定性、核心依据速查、风险与后续行动，再展示分析、方法、检索结果和明细。
- 新增 `templates/legal-research-report.md`，沉淀可维护的法律检索报告模板，便于后续单独调整报告结构。
- `consolidate` 报告头新增检索主体、检索平台、项目包等可核查信息；第七节检索明细改用可回溯本地链接。
- `consolidate` 新增 `--risks` 和 `--next-actions` 参数，用于填充结论区的风险与后续行动；`--conclusion` 未传时保留明确补写提示。

### 修复
- 修复 `consolidate` 将 per-call JSON 移入项目子目录后，后续分组读取仍指向旧路径，导致法律依据/案例/法规分组可能丢失的问题。

### 文档完善
- SKILL.md 同步更新 7 节报告结构、质量要求、调用方式和目标目录归档口径。

## [1.6.0] - 2026-06-11

### 战略转向
- 元典官方已发布 MCP（https://open.chineselaw.com/mcp-config），3 个 servers：yuandian-law / yuandian-case / yuandian-company
- 本 skill 价值从"API 包装"转向"**归档 + 法律检索报告生成**"——agent 用 MCP 调数据，本 skill 负责沉淀
- v1.6.0 起，本 skill 同时支持两种调用模式：
  1. **直接 API 模式**（原有 `search/case/...` 子命令，保留兼容）
  2. **MCP 协同模式**（新增 `ingest` 子命令，消费 MCP 输出 JSON）

### 新增
- **`ingest` 子命令**（v1.6.0 核心）：
  - 用法：`yd-run ingest --query "<Q>" --endpoint "/open/<E>" --input <file.json>`（或 stdin pipe）
  - 必填：`--query`、`--endpoint`
  - 可选：`--cost`（默认 "10 积分"）、`--no-report`、`--no-cwd-report`
  - 消费外部 JSON（来自 MCP 或其他源），路由到对应 formatter，**走与直接 API 相同的归档 + .md 流程**
  - 归档记录额外加 `"ingest": true` 标记，便于区分数据来源
- **`INGEST_ROUTING` 表**（36 个 endpoint 覆盖）：
  - 法条 4 个（law_vector_search / rh_ft_search / rh_ft_detail + 1）
  - 法规 2 个（rh_fg_search / rh_fg_detail）
  - 案例 4 个（case_vector_search / rh_ptal_search / rh_qwal_search / rh_case_details）
  - 企业主接口 4 个（rh_enterpriseSearch / rh_company_info / rh_company_detail / rh_enterpriseBaseInfo）
  - 企业分项列表 21 个（OutInvest/Brand/Patent/SoftRight/WorksRight/Icp/ChangeInfo/WritAgg/WritList/CourtSessionNotice/CourtNotice/Executions/ExecutedPerson/FrozenEquity/Punishment/Pledge/Guaranty/AbnormalOperation/CorporateTax/SeriousIllegal/AnnualReport）
  - 特殊 2 个（hall_detect 用对应 formatter；rh_enterpriseAggregationSummary 用 raw JSON 包装）
  - 未知 endpoint 走 raw JSON 兜底（包装为 ```json ... ``` 代码块）
- **`.mcp.json.example` 模板**（skill 根目录）：
  - 3 个 yuandian-* MCP servers 配置（law/case/company）
  - `Authorization: Bearer ${YD_API_KEY}` 鉴权
  - 用户复制为 `.mcp.json` 后让 Claude Code / Cursor / Codex 等客户端自动加载
- **企业分项列表 endpoint 自动 label 推断**（如 `/open/rh_enterpriseOutInvest` → "对外投资"），无需 --label 参数

### 改进
- SKILL.md 新增"MCP 协同工作流"章节，描述 agent 如何同时使用 `mcp__yuandian__*` 工具 + `yd-run ingest` + `yd-run consolidate`
- INGEST_ROUTING 路由表覆盖元典 MCP 暴露的全部 24 个数据 tools（不含 2 个 meta tools）

### 架构关系
```
agent 调用流程:
1. mcp__yuandian_law__yuandian_law_vector_search("违约金")  ← MCP 直接调元典
2. 把响应 JSON 喂给 yd-run ingest                             ← 本 skill 归档
3. 多次 ingest 后, yd-run consolidate --project "..."        ← 生成 6 节法律检索报告
```

向后兼容：原有 `search/case/detail/...` 直接 API 子命令完全保留，YD_API_KEY 用户可继续用。

## [1.5.1] - 2026-06-10

### 新增
- **consolidate 项目子目录组织**（用户反馈：一次研究任务会产生多个 .json + .md，平铺在 archive/ 不便按项目查找）
  - 新增 `--project "<name>"` 参数（可选，默认从 `--title` 自动 slugify）
  - consolidate 创建 `archive/<project>/` 子目录作为"项目包"
  - per-call .md 从 CWD **复制**到项目子目录（CWD 保留工作副本）
  - per-call .json 从 `archive/` 根目录**移动**到项目子目录（archive 根保持清爽，不重复）
  - 法律检索报告双写：`archive/<project>/<ts>_法律检索报告.md`（项目包）+ CWD（工作副本）
  - 报告末尾"项目包"标识：`> 项目包：archive/<project>/`
  - 重复运行 consolidate 同一项目：idempotent，文件已在子目录则跳过移动/复制

### 改进
- consolidate 报告头增加项目包路径引用，方便用户定位

## [1.5.0] - 2026-06-10

### 新增
- **session-level 法律检索报告**（`consolidate` 子命令）：把多次检索的 per-call 报告汇总成一份标准结构的法律检索报告
  - 调用方显式传 `--case` / `--strategy` / `--analysis` 三个核心字段（AI 填）
  - `--include` 必填，逗号分隔的查询子串，明确指定"本次任务范围"（不取最近 N 条）
  - 6 节标准结构：案情简介 / 检索目的与问题 / 检索思路与方法 / 检索结果（4.1 法条 + 4.2 案例 + 4.3 法规 + 4.4 其他，按 endpoint 自动分组）/ 分析与判断 / 检索结论
  - 附录"本次检索明细"表格：时间/检索词/接口/积分/[md](CWD相对路径)·[json](file://绝对路径)
  - 4.4 其他：自动收纳未归类到法律/案例/法规的检索（如 hall-detect、enterprise-*）
  - `--purpose` 可选：不传则基于检索词自动推断
  - `--conclusion` 可选：不传则提示"详见第五节"
  - `--output` 可选：默认 `<cwd>/<ts>_法律检索报告.md`

### 改进
- per-call .md 报告元信息移除"检索接口"字段（用户反馈：API 端点太技术化，不属于报告内容）

### 架构关系
- per-call .md = 检索明细（数据底稿，每次检索自动写 archive + CWD）
- session 报告 = 主交付物（法律检索报告，按任务粒度由 AI 触发 consolidate 生成）
- session 报告的"检索明细表"链接到 per-call .md，整套形成完整溯源链

## [1.4.0] - 2026-06-10

### 新增
- 检索报告 .md 自动落盘：每次实际检索（cache miss 时）落盘两份结构化 Markdown 报告
  - `archive/<ts>_<query>.md`：与 archive JSON 配对，技能内部归档
  - `<CWD>/<ts>_<query>.md`：用户运行命令时的工作目录副本，方便附卷/分享
- 报告模板：元信息（时间/接口/关键词/积分/原始数据路径/工作目录副本）+ 检索结果（与 stdout 一致）+ 引用来源（按类型分组）+ 数据来源声明
- 复用现有 5 个 formatter（format_law_results / format_case_results / format_regulation_results / format_enterprise_results / format_hall_detect_results）填充"检索结果"段，零行为变化
- 新增 `--no-report` 全局 flag：跳过 .md 报告生成（archive + CWD），仅写 archive JSON
- 新增 `--no-cwd-report` 全局 flag：仅跳过 CWD 副本，仍写 archive/ 报告
- 调用结束后 footer 追加报告路径提示（archive + CWD，CWD 失败时不显示第二行）
- CWD 副本写入失败时 stderr 警告但不中断（archive 副本是主落点，best-effort 容错）

### 改进
- `api_post` / `api_get` 返回值从 2-tuple 改为 3-tuple `(result, cached, archive_path)`，让 cmd_* 能拿到 archive 路径以驱动报告生成
- 5 个有自定义成本的端点（hall-detect 50、enterprise-search 1、enterprise-base 10、enterprise-summary 10、enterprise-list 5/10）准确把成本传递到报告元信息头

## [1.3.4] - 2026-05-27

### 新增
- 新增 `scripts/yd-run` 干净环境运行入口，默认清理 Codex/代理相关环境变量后再调用 `yd_search.py`。
- 新增 `scripts/yd-run --network-check` 网络预检，用于无积分消耗地检查 `open.chineselaw.com` 和 `ydzk.chineselaw.com` 的 DNS 与 TLS 连通性。

### 文档完善
- SKILL.md 和 README.md 改为推荐使用 `scripts/yd-run`，降低 Codex 网络沙箱、PATH 漂移和代理环境变量对元典检索的影响。

## [1.3.3] - 2026-05-13

### 新增
- archive 归档记录新增 `source_urls` 字段：自动提取/构造法条、案例、法规、企业的来源链接，方便后续检索时提供核实出处
- `backfill-urls` 子命令：一次性回填现有 archive 的 source_urls（已回填 36 个文件）

### 改进
- 法条语义检索（law_vector_search）和案例语义检索（case_vector_search）等无 URL 的接口，根据 fgid/scid 自动构造完整链接
- 法条详情（rh_ft_detail）、案例关键词（rh_ptal_search）等返回相对 URL 的接口，归档时自动转为完整 URL

## [1.3.2] - 2026-05-10

### 新增
- 新接口策略矩阵：为 hall-detect、enterprise-search、enterprise-base/summary、enterprise-list 四类新增接口补充 balanced/economical/aggressive 三种策略下的具体行为指导
- 企业尽调工作流：enterprise-search → enterprise-base → enterprise-summary → enterprise-list 四步尽调流程
- 幻觉检测工作流：引用识别 → AI 建议 → 用户确认 → hall-detect 检测 → 结果展示
- 企业风险排查工作流：enterprise-summary 总览 → enterprise-list 深挖高风险项 → 风险画像汇总

### 改进
- enterprise-list 子命令新增策略感知默认 size：economical 模式默认 10 条，aggressive 模式默认 50 条，balanced 保持 30 条

## [1.3.1] - 2026-05-10

### 新增
- 关键词扩展检索：`keyword`、`case`、`regulation` 子命令新增 `--expand` 参数，支持传入逗号分隔的扩展关键词，自动追加到原始查询并以 OR 模式检索
- 分阶段检索指引：SKILL.md 新增「关键词扩展与分阶段检索」章节，说明 AI 应如何主动扩展法律概念、执行广撒网+精提炼的两阶段检索
- 扩展方向提示：检索完成后 AI 应向用户建议可能相关的扩展检索方向
- 策略兼容矩阵：明确关键词扩展行为与 balanced/economical/aggressive 三种策略的兼容关系

## [1.3.0] - 2026-05-10

### 新增
- 适配 24 个元典开放平台新接口（从 11 个扩展至 35 个）
- 新增 5 个子命令：
  - `hall-detect`：法规/法条/案例幻觉检测（50 积分）
  - `enterprise-search`：企业轻量检索（1 积分），返回候选列表
  - `enterprise-base`：企业基本信息查询（含股东、核心成员、分支机构）
  - `enterprise-summary`：企业聚合总览
  - `enterprise-list`：企业分项列表查询，支持 20 种类型（对外投资、商标、专利、涉诉文书、行政处罚等）
- 新增 `format_hall_detect_results`：幻觉检测结果格式化（法规存在性、语义比对、案例核实）
- 新增 `format_enterprise_list_results`：企业分项列表通用格式化函数
- 新增 24 个 Reference 文档（12-35），覆盖幻觉检测和企业全息画像系列接口
- 所有新子命令支持 `--no-cache` 选项
- MANIFEST.json 全部 35 个接口标记为已适配（`adapted` 字段移除，改为完整元数据）
- SKILL.md 接口清单从 11 个扩展至 35 个，新增幻觉检测和企业全息画像使用说明

### 改进
- 接口分层新增"专项"层（hall-detect）
- 附属接口层扩展：新增 enterprise-search·enterprise-base·enterprise-summary·enterprise-list
- 积分消耗说明从"每次 10 积分"更新为"1-50 积分（视接口而定）"
- CLI 帮助示例新增 5 个新子命令用法

## [1.2.1] - 2026-05-10

### 改进
- 新增 `references/MANIFEST.json`：接口清单元数据文件，记录全部 11 个已适配接口的端点、子命令、分层和分类信息
- MANIFEST.json 包含 `check_history` 字段，记录每次平台接口排查的时间、方法和结论
- 排查元典开放平台（2026-05-10）：通过 Playwright 浏览器实际访问接口广场，发现平台从 11 个 API 扩展到了 35 个，新增 24 个未适配接口（1 个幻觉检测 + 23 个企业信息），已记录到 MANIFEST.json，待后续适配

## [1.2.0] - 2026-05-09

### 新增
- 可配置检索策略（`YD_STRATEGY`）：balanced（均衡，默认）、economical（省钱）、aggressive（激进）
- `strategy` 子命令：显示当前检索策略
- 策略感知的默认返回数量：economical 模式下语义检索默认 20 条，aggressive 模式下关键词检索默认 20 条

### 改进
- SKILL.md 调用策略章节重构为三策略矩阵，清晰区分接口确认要求、案例详情触发方式、补充检索行为
- .env.example 新增 YD_STRATEGY 配置说明

## [1.1.1] - 2026-04-18

### 修复

- `datetime` import 在 updater.py 重构时被误删，导致归档函数 `NameError`
- `detail` 子命令：API 返回单个 dict 而非列表，格式化函数崩溃
- `case` 子命令：API 返回 `{total, lst}` 结构而非裸列表，需从 `data.lst` 提取
- `format_law_results` 兼容 `ftmc`/`tid` 字段（detail 端点返回）
- `format_case_results` 兼容 `cprq` 字段（关键词检索返回的裁判日期）
- `format_enterprise_results` 兼容中文字段名（`企业名称`、`统一社会信用代码`、`企业类型` 等）
- 移除 `_print_footer` 中的缓存命中提示，归档重新定位为"历史检索记录"
- 新增 `archive-list` 子命令，支持按关键词浏览历史检索记录
- Reference 文档修正：05 案例关键词检索补充 `cprq`/`type`/`url`/`llm_content` 字段、07 案例详情补充返回结构、10 企业检索补充中英文字段映射
- 权威案例关键词检索（06）返回结构说明更新为 `{total, lst}` 包装格式

## [1.1.0] - 2026-04-17

### 重大变更
- SKILL.md 大幅精简（~260 行 → ~170 行），策略内容抽取至 `references/00-*.md`
- Reference 文件按前缀分层：`00-` 策略指南、`01-11` API 端点文档

### 新增
- 策略指南：检索模式选择指南（`references/00-retrieval-mode-guide.md`）
- 策略指南：接口优先级与选择规则（`references/00-interface-priority.md`）
- 积分节约策略合并回 SKILL.md，核心理念调整为"正确性优先于积分节约"
- SKILL.md 新增"积分消耗模式"小节，明确案例检索的两阶段消耗（摘要 10 积分 + 详情 10 积分/个）
- `case` 子命令新增 `--fxgc`、`--yyft`、`--ft-search-mode` 参数
- `format_law_results` 新增输出字段：发布日期、发布部门、发文字号、二级效力级别
- Reference 文件补充响应结构文档（02-law-keyword-search 完整 20 字段）
- `archive/.gitkeep` 确保归档目录不会被 git 忽略
- `check-update` 新增最近提交记录展示（通过 Atom feed，不依赖 GitHub API）
- `check-update` 新增 CHANGELOG 差异展示（读取远程 CHANGELOG.md 中本地版本之后的变更）
- `do-update` 子命令：仅下载本 skill 目录下的文件更新，不碰其他目录和 .env/归档
- 更新逻辑拆分为通用模块 `scripts/updater.py`（`SkillUpdater` 类），可被其他 skill 复用
- `MANIFEST.txt` 移至 `scripts/` 目录，列出所有可更新文件

### 修复
- `--rewrite-flag` 参数使用 `type=bool` 导致任何字符串均为 `True` 的 bug，改为 `store_true`/`--no-rewrite`
- 移除所有旧 API（aiapi.ailaw.cn）中文字段名 fallback 死代码
- SKILL.md 注册地址更新为 `https://open.chineselaw.com`

## [1.0.0] - 2026-04-17

### 重大变更
- API 平台迁移：从旧平台 (`aiapi.ailaw.cn:8319`) 迁移至开放平台 (`open.chineselaw.com`)
- 认证方式从 URL 查询参数改为 `X-API-Key` 请求头
- 语义检索请求体改为嵌套结构（`fatiao_filter` / `wenshu_filter`）
- 语义检索响应格式更新（`extra.fatiao` / `extra.wenshu`）
- 接口文档拆分为独立文件（`references/01~11-*.md`）

### 新增
- 法规关键词检索（`regulation` 子命令）
- 法规详情查询（`regulation-detail` 子命令）
- 案例详情查询（`case-detail` 子命令）
- 企业名称检索（`enterprise` 子命令）
- 企业详情查询（`enterprise-detail` 子命令）
- 语义检索新增 `--rewrite-flag` 和 `--return-num` 参数
- `raw` 子命令新增 `--get` 和 `--no-cache` 选项
- 归档机制：每次 API 调用自动归档至 `archive/`，相同查询命中归档不消耗积分
- 接口优先级分层：核心接口（5个）、扩展接口（4个）、附属接口（2个）

### 改进
- 案例关键词检索拆分为普通案例和权威案例两个端点
- 格式化函数兼容新旧字段名
- 超时时间从 30 秒提升至 60 秒

## [0.3.1] - 2026-04-07

### 改进

- 移除「与其他技能配合」章节，保持技能描述独立聚焦

## [0.3.0] - 2026-04-06

### 改进

- Front Matter 规范化：补充 homepage、author、version 字段

## [0.2.0] - 2026-04-05

### 改进
- skill name 从 `yd-law-search` 改为 `yuandian-law-search`，提升辨识度
- 目录同步重命名为 `yuandian-law-search`
- 标题从"元典法条检索"改为"元典法条与案例检索"，准确反映 API 覆盖范围
- 许可证从 CC BY-NC-SA 4.0 改为 MIT
- 前置要求新增注册登录指引（账号注册 → API Key 创建 → 配置 .env → 验证连接）

## [0.1.0] - 2026-04-03

### 设计缘由
- 元典法条检索 API 提供了法律条文和案例的语义/关键词检索能力，适合封装为 Skill 供法律分析场景使用。

### 思路演进
1. 分析 API 文档，梳理 5 个端点的功能和参数
2. 设计统一的 CLI 工具，用子命令区分不同检索模式
3. 输出格式化为 Markdown，方便 AI 直接引用

### 新增
- 初始版本，封装 5 个 API 端点
- 支持法条语义检索、关键词检索、详情检索
- 支持案例关键词检索、语义检索
- 输出 Markdown 格式化
- 支持原始 JSON 调试输出
