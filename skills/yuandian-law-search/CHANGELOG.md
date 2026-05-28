# 变更日志

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
