# 变更日志 (CHANGELOG.md)

本文档记录 github-star-manager 技能的所有变更。

---

## [0.8.1] - 2026-10-15

### 新增

- **快照补 repo 数字主键 `id`（D-00 对账发现的缺口闭合）**：`original_latest.json` 的 repos 条目新增 `id` 字段（GitHub 数字主键，改名后保持稳定）。此前 id 只存在于 export 路径的 data.js，快照侧缺失——下游消费者（Hermes star-board 插件 sync 以 id 为主键）无法用快照锚定改名仓库，会把改名误判为新仓库。消费方应以 id 为主键、full_name 为展示名。附加字段向后兼容，schema_version 维持 2

## [0.8.0] - 2026-10-15

### 新增

- **Agent 查询接口（批次 B，审计 §3 落地）**：新增 `scripts/star_query.py`，五个只读命令——`recent`（按真实 starred_at 时间窗列新关注，未知/非法时间单独归 unknown_time_items 不冒充）、`interests`（可比窗口的主题计数与 delta，无分类数据明确返回 needs_analysis 不暗中调模型）、`match`（项目需求关键词召回，分数只是召回依据）、`evidence`（单仓库缓存证据包，缺缓存显式 missing）、`research`（组装供 Agent 分析的最小候选+证据包）。统一 JSON envelope（schema_version/account_id/snapshot_id/status/coverage/warnings/errors），stdout 只写 JSON、日志走 stderr、失败非零、partial 显式标注
- **显式联网取证 `evidence-fetch`（审计 §2「README 证据」回迁 / §3「取证与查询分离」）**：抓取仓库 meta/README/最新 Release 写入 `output/evidence/<owner>__<repo>/`——README 记录 blob sha 证据锚点、超限截断显式标记、原文权威不翻译；`evidence` 缓存导出升级为含 README 摘录/repo 元数据/Release/抓取时间/新鲜度（过期标 stale 并建议重取）
- **机会卡与采用反馈（批次 C 核心，审计 §4 落地）**：新增 `scripts/opportunity.py`——机会卡七字段必答校验（signal/target/evidence/gap/hypothesis/experiment/decision）、decision 状态机（tested 必须带 run_evidence、adopted 必须再有 adoption_evidence，无证据只允许 researched/experiment_proposed）、gap 六值枚举（含「已有等价能力」合法结论）、反馈持久化到 output/feedback/、拒绝抑制查询（同候选同方向默认跳过，新 repo revision 允许重新评估）
- **项目登记**：`output/projects/<id>.json`（project_id/capabilities/needs/constraints），match/research 对齐项目需求；未登记时 match 退化通用召回并警告

### 修复

- **envelope 合同违规**：interests 调 `_load_categories` 时其内部警告 print 会混入 stdout 污染 JSON（stdout 现重定向到 stderr）
- **interests 静默冒充**：分类文件不存在时此前回落内置默认分类继续计数（把「没有你自己的分类数据」伪装成分析结果）——现在明确返回 needs_analysis
- **同秒反馈覆盖丢数据**：opportunity record 的文件名时间戳精确到秒，同候选同秒两次反馈互相覆盖——改毫秒时间戳+冲突递增序号

### 改进

- **分类匹配算法收敛（审计「分类/导出分叉」收口）**：`common.match_categories` 成为唯一评分实现，quick_export 多标签导出与 star_tracker 在线单分类选择（=多标签首个）共用同一规则——同一仓库两条路径不再可能评出不同分类

### 技术优化

- 离线回归套件 `tests/test_batch_b.py`：65 用例覆盖五命令 envelope 合同、partial 警示、needs_analysis 拒绝、召回截断、证据缺失标记、未登记项目指路、机会卡全字段拒绝矩阵、tested/adopted 证据红线、拒绝抑制与 list 过滤、evidence-fetch 取证闭环（mock 网络：blob_sha/截断/404 分支/陈旧缓存）、算法收敛对齐（单分类=多标签首个）；批次 A 套件 33 用例无回归
- **真实 CLI 全链路验证（批次 A 验收标准「真实 CLI 正反例通过」）**：真实账户完整跑通 init（775 仓完整快照 complete=True）→ check（0 新增/33 更新/完整保存）→ recent（7 天窗 34 个）→ interests（30 天 142 vs 前 30 天 7，纯时间数据复算）→ match（5 命中+截断可见）→ evidence-fetch/evidence（blob_sha 锚点+新鲜度）→ research（code-video 需求召回 3 真实候选）→ opportunity validate/record/list/suppress 闭环

## [0.7.0] - 2026-10-15

### 修复

- **F01 快照完整性守卫（严重）**：`get_starred_repos` 分页失败不再静默返回子集——抓取状态记录在 `self.last_fetch_meta`（complete/failed_pages/账户/时间戳/limit 截断标志）并写入快照 `snapshot_meta` 字段；`--check`/`--init` 在抓取不完整且已有旧快照时**自动放弃保存**，部分数据不再被误判为「用户取消收藏」而覆盖基线；`--export` 允许部分数据展示但显式警告；无元数据的 v1 旧快照加载时标记「完整性未知」
- **F03 三断点（严重）**：① `generate_report` 里 `load_latest(username)` 多传参数的 TypeError（改为 `load_latest()`）；② 分类 schema 两口径不一致——`generate_categories.py` 写根对象 `{categories:[...]}` 而加载方按裸列表遍历（`_load_categories` 现两种格式兼容）；③ AI 摘要引用未定义的 `HAS_OPENAI`/`OpenAI`（模块顶部 try/except import + 可选依赖降级标志，未安装 openai 自动用基础摘要）
- **批量 Star/Unstar 计数器崩溃**：`batch_star`/`batch_unstar` 的 `failed` 初始化为列表却做 `+= 1`，任何一次失败即 TypeError（改为整数计数）
- **时区 naive/aware 相减崩溃**：`cleanup_stale_repos` 用 UTC aware 时间减 naive `datetime.now()` 直接 TypeError（统一 `datetime.now(timezone.utc)`；`get_recent_commits` 的弃用 `utcnow()` 同步替换）
- **版本对比名实不符**：`get_version_diff` 此前只取最近 20 条 commits 加 compare_url，未做真实版本比较（改用 GitHub compare API，返回 ahead/behind/status 与真实 commits）
- **CLI 交互断点**：`--version-diff` 旧实现把「旧版本」输入当 owner/repo 解析且与核心函数参数错位（重写为非交互式 `--repo` + `--old-version` + `--new-version` 三参数，缺参明确报错）；各子命令返回码规范化（失败返回 1）
- **import-config 只校验不应用**：配置导入此前打印后即弃（修复后持久化到 `output/user_settings.json`，`assess_value` 实际读取 value_keywords/阈值）
- **摘要文件头荒谬表达式**：`--init --summarize` 写 `tracker.get_readme.__self__` 当生成时间（改为真实时间戳）；摘要/报告输出路径锚定技能 `output/` 目录，不再随 cwd 漂移

### 改进

- **Dashboard「我的 Star 时间」统计口径（F02）**：`starred_at` 缺失时不再回退用 `updated_at`（仓库更新时间）冒充 Star 时间，也不再计入「3 年+」桶——新增独立「未知时间」桶（star/activity 两个面板都有 chip，可筛选）；未来日期与非法日期串同样归入未知
- **Dashboard innerHTML 注入面**：新增 `escapeHtml`，仓库自述文本（full_name/description/topics/owner 等）拼入 innerHTML 前统一转义
- **分类/导出分叉收敛**：新增 `scripts/common.py` 共享价值评估（在线导出与 quick_export 的关键词集/阈值此前不一致，同一仓库两条路径可能评出不同价值）
- **依赖防护**：requests 硬缺失时输出安装提示并退出（不再裸 ImportError）；pyyaml 缺失给出清晰提示与降级路径；`requirements.txt` 补上此前遗漏的 `pyyaml`；`_load_categories` 同时清掉 `get_categories_map` return 后不可达的死代码
- **文档-实现对齐**：SKILL.md 删除不存在的 `--weekly` 参数示例（改为 cron 指引）、修正「配置复制到 ~/.github-star-manager/」的错误描述（实际在技能 `output/`）、修复 SKILL-GUIDE.md 死链（指向 skill-lint 唯一维护源）、新增数据完整性保障章节与 version-diff 用法

### 技术优化

- 离线回归套件 `tests/test_batch_a.py`：13 项用例覆盖 F01 守卫（部分抓取不覆盖基线/无旧快照允许建基线/旧 v1 快照标记未知）、F03 三断点、批量计数器、时区、分类双格式加载、价值配置读取、version-diff 参数校验、Dashboard unknown 桶与 escapeHtml（node --check + 冒烟断言）

## [0.6.8] - 2026-10-13

### 新增

- **Owner/Repo 视觉消歧手册（截图/视频帧输入专用）**：新增 `references/owner-repo-disambiguation.md`，沉淀从 50+ 张抖音/小红书截图提取 GitHub 仓库时实测的 OCR 误读消歧经验：5 类高频失败模式（整 owner 完全错读、owner 前缀/中段缺失、字母形态相似漂移如 l/i、f/t、0/o、README 迁移公告致 archived 仓库返 404 而非 301、截图只露目录名）对应 7 条消歧规则、完整消歧流程（变体生成→repo 名精确搜→README 迁移公告→语义锚定→姊妹项目互引）与 3 条「不要做」清单
- SKILL.md §2 追加「截图/视频帧输入专用」入口规则：OCR 直读 owner/repo 404 时**不**判定「找不到」，先按手册做视觉消歧，再走同名候选消歧

## [0.6.7] - 2026-10-06

### 改进

- **对话模块消歧经验扩充（模糊线索推理子规则入 SKILL.md）**：原"仓库发现与智能匹配"步骤只覆盖了"内容里含 GitHub URL / 半截 URL / 完整项目名"三类有显式锚的发现路径，对**用户口述零散线索（项目主题词 + 创建时间窗口 + 用户名片段，无任何完整 owner/repo）**没有可操作判据——而实测中此类请求 GitHub 站内搜索常因关键词含 OCR 噪声、用户名被拼写截断、过长关键词串而 0 命中。新增三步推理协议：① 拆解口述线索为可枚举字段（主题关键词、创建时间窗口、用户名片段、其他外联候选）；② GitHub Search API 多条件缩范围（关键词 OR/AND 顺序：先粗后细，长串拼接必 0 命中），时间窗口比关键词更重要；③ 候选消歧走原有证据链（亲授全称 > 语义锚定 > 衍生排除 > 创建时间匹配 > Star 数量级仅参考），但本场景无亲授/截图，所以三条验收（`created_at` 落窗口内 ±3 天、`description` 含线索关键词、owner 名含用户片段前缀）同时满足才定为唯一，候选命中但创建时间偏离超 ±5 天与用户核对或放弃
- **口径统一**：本规则与"同名候选消歧"复用同一证据链（亲授全称 > 语义锚定 > 衍生排除 > 版本/创建时间 > 数量级），仅在"内容来源名"维度展开：本规则是**口述零散线索**而非**截图/帖子完整项目名**——前者需要先按字段拆解生成候选列表，后者直接进消歧

## [0.6.6] - 2026-09-24

### 修复

- **导出脚本网络重试加固（重要）**：`star_tracker.py` 全部 14 处裸 `requests.get/put/delete` 改走新增的 `_request_with_retry()` 封装——指数退避重试（2s 起步、60s 封顶、最多 8 次），覆盖网络异常（ProxyError/RemoteDisconnected/Timeout 等）与 429/5xx 状态码，429 尊重 `Retry-After` 头。事故背景：全量导出 673 仓（约 2000+ 次请求）在代理环境下连续两晚失败——首次 HTTP 503 隧道错误（处理到 multica-ai/multica 时）、次次 `RemoteDisconnected`，裸调用一次即崩，长窗口任务必折。修复后全量导出 681 仓一次通过、零失败
- **导出产物路径不再随 cwd 漂移**：`main.py` 导出 Dashboard 与 config 原写入相对路径 `output/`，从其他目录（如仓库根）启动时产物散落工作区、污染共享仓库（实测：`scripts/output/` 出现 data.js/dashboard.html 两个 untracked 脏文件）；现统一锚定技能自身 `output/` 目录（`StarTracker.CACHE_DIR`，已被 .gitignore 覆盖）。`dashboard_generator.py` 模板查找同步从相对路径改为锚定技能目录，否则非技能根目录启动时永远走简化模板

### 改进

- **对话模块消歧经验扩充（3 条实战模式入 SKILL.md）**：① owner 拼写修正——截图直读 owner 404 时先怀疑 OCR 误读，按 repo 名搜索锁定真身并用星数量级与截图侧栏数字互证（实测 webadderalorg→webadderallorg/Recordly）；② 社交账号名 ↔ GitHub owner 互证——博主昵称与 owner 名的派生关系作中优先级佐证（实测：耳朵→erduo1998-cell、姚老师→yaojingang、文森特→Vincentwei1021）；③ 改名仓库识别——旧名 404 时查 API 301 重定向，返回的 full_name 即新名，已在库则跳过（实测：erduo-hyperframes-broll→erduo-broll-loop-engineering）
- SKILL.md Dashboard 使用说明同步产物路径变化

---

## [0.6.5] - 2026-09-23

### 改进

- **消歧协议重排（重要）**：证据优先级明确为「来源亲授全称 > 语义比对 > 排除规则 > 版本轨迹」，Star 数量级从第 1 位降为第 5 位仅参考信号、永不单独定论。实测反例：taste-skill 同名的 Leonxlnx 版 8.9 万⭐ 比目标 senlindesign 版（366⭐）高两个数量级，若按旧协议"数量级快筛"会 star 错；实际靠语义比对 + 作者评论区亲授全称锁定

### 新增

- **评论区/回复作为提取源**：作者在评论区亲授的 owner/repo 全称是最高优先级证据，优先于一切启发式消歧
- **半截 URL 补全策略**：owner 确定而 name 截断（如 `mcncarl/jianyi…`）时，列该 owner 名下仓库按名称前缀 + description 语义匹配补全（实测：jianyi…→jianying-headless，yichen…→yichen-skills）
- **批量 star 执行模式**：一次内容提取出多个仓库时循环"查重→star→回读"，单仓失败不阻断，最后汇总成功/跳过/失败

### 背景

四连 star 实战（taste-skill、jianying-headless、yichen-skills、hypit）中，数量级启发式首次遇到同名高星反例，暴露 0.6.4 协议的优先级缺陷；同时半截 URL 补全、评论区提取、批量执行三种实战模式均未成文，本次一并固化。

## [0.6.4] - 2026-09-23

### 新增

- **同名候选消歧协议**：社交内容（截图/帖子）常只给项目名，同名候选多为 fork/搬运/衍生项目。对话模块新增四步锚定：Star 数量级判别（原仓库通常高 1–2 个数量级）、图片语义锚定（截图功能场景与候选 description 比对，而非只提取项目名文字）、衍生仓库排除（后缀/自述"基于上游"）、版本交叉核对（内容提到版本号时查 releases/tags）
- **消歧兜底**：候选无法唯一确定时不凭猜测 star，列出候选与判断依据请用户确认

### 背景

实测两起截图 star 案例（mono-color-skill 3250⭐ vs 0~3⭐ 搬运；native-subtitle-quote-image 795⭐ vs 5/7⭐ 衍生）均依赖上述锚定手法锁定原仓库，但原 SKILL.md 仅有一行"上下文相关性验证"，无可操作判据，本次将实战验证过的协议固化。

## [0.6.3] - 2026-09-23

### 修复

- **对话模块 star 命令在 gh 2.83.0 不可用**：SKILL.md 中 `gh repo star owner/repo` 实际报 `unknown command "star" for "gh repo"`（该子命令并非所有 gh 版本都有），改用 REST API `gh api -X PUT user/starred/owner/repo`，幂等且跨版本可用
- **star 结果验证语义**：补充检查是否已 star 的响应语义（HTTP 204 = 已 star，404 = 未 star），并要求 star 后以 GET 回读 204 为完成标准，不以 PUT 退出码为准
- **frontmatter 版本滞后**：SKILL.md version 停留在 0.6.1，与 CHANGELOG 已发布的 0.6.2 脱节，本次一并同步到 0.6.3

## [0.6.2] - 2026-05-10

### 修复

- **description 为 null 时自动重试**：增量同步和首次同步时，对 description 为 null 的项目自动调用 GitHub API 重新抓取最新元数据，同时刷新 language、topics、homepage 等字段（Closes #9）
- **star 变化触发元数据刷新**：检测到新增 star 时，同时刷新该项目的 description、language、topics 等元数据，确保存量项目改名后数据同步更新
- **数据质量日志**：新增 `log_null_descriptions()` 方法，记录哪些项目 description 为 null 并输出到 `output/data_quality.log`，方便排查数据质量问题

### 新增方法

| 方法 | 位置 | 功能 |
|------|------|------|
| `refresh_repo_metadata()` | `star_tracker.py` | 通过 GitHub API 刷新单个仓库的最新元数据 |
| `log_null_descriptions()` | `star_tracker.py` | 记录 description 为 null 的项目列表，写入数据质量日志 |
| `retry_null_descriptions()` | `star_tracker.py` | 批量重试 description 为 null 的项目，自动刷新元数据 |

---

## [0.6.1] - 2026-04-10

### 修复

- **文档路径修正**：环境配置示例统一改为当前目录结构
  - `cp .env.example .env` 修正为 `cp assets/.env.example .env`
  - `pip install -r requirements.txt` 修正为 `pip install -r assets/requirements.txt`
- **配置目录口径统一**：首次复制配置目录统一为 `~/.github-star-manager/`

### 文档完善

- `references/api-guide.md` 与 `references/dev-guide.md` 中的旧名称 `github-star-tracker` 已同步改为 `github-star-manager`
- 开发指南中的测试目录示例改为当前目录 `skills/github-star-manager`

---

## [0.6.0] - 2026-02-28

### 重构（Skill 整合）

| 变更 | 说明 |
|------|------|
| **Skill 整合** | 将 `github-auto-star` 整合到 `github-star-tracker`，统一为 `github-star-manager` |
| **目录重命名** | `github-star-tracker` → `github-star-manager` |
| **模块化设计** | 同一 Skill 包含两个模块：对话模块 + 脚本模块 |

### 新增（对话模块）

| 模块 | 触发方式 | 功能 |
|------|----------|------|
| **对话模块** | 对话触发 | 从内容提取项目并 Star |
| **脚本模块** | 命令行/定时任务 | 同步、Dashboard、追踪、批量管理 |

### 对话模块功能

- 从各种内容来源（URL/截图/文字）中自动提取 GitHub 仓库引用
- 智能匹配：直接匹配 + 按名称搜索 + 上下文相关性验证
- 自动检查是否已 Star，避免重复
- 使用 GitHub CLI (`gh`) 执行 Star 操作

### 删除

- 删除 `github-auto-star` 独立 Skill，功能已整合到 `github-star-manager`

---

## [0.5.1] - 2026-02-14

### 修复（Dashboard UI 问题修复）

| 变更 | 说明 |
|------|------|
| **刷新后默认不显示项目** | 修复默认筛选状态，加载后自动显示项目列表 |
| **标签云不显示** | 修复 `renderTagCloud()` 使用错误的字段，改用 `topics` |
| **Star 时间显示为零** | 修复统计函数未包含 twoyears/threeyears 选项 |
| **时间筛选器不工作** | 修复 `filterProjects()` 使用隐藏 select 而非变量的问题 |

### 增强（时间筛选扩展）

| 变更 | 说明 |
|------|------|
| **新增筛选选项** | 添加"2年"和"3年+"时间筛选选项 |
| **emoji 同步** | 活动标签和 Star 时间的 emoji 保持一致 |
| **默认显示调整** | 将"我的Star时间"设为默认显示标签（左侧） |

### 重构（项目命名）

|  变更  |  说明 |
|--------|--------|
| **项目重命名** | `github-star-tracker` → `github-stars-tracker`（复数形式符合 GitHub 官方命名）|
| **HTML 标题更新** | 页面标题和 H1 标题改为 `GitHub Stars Tracker` |
| **模板文件同步** | 更新 `dashboard.example.html`、`.env.example` 等模板 |

### 模板文件更新

- `assets/dashboard.example.html` - 同步 Dashboard 修复和默认显示
- `assets/.env.example` - 更新标题为 `GitHub Stars Tracker`

---

## [0.5.0] - 2026-02-14

### 新增（数据维度增强 + 双重活跃度筛选）

| 变更 | 说明 |
|------|------|
| **数据字段扩展** | 从 3 个字段扩展到 27 个字段，丰富 AI 分析维度 |
| **starred_at 获取** | 使用认证 API 获取用户 star 的具体时间 |
| **项目更新活跃度筛选** | 按项目更新时间筛选（1周/1月/3月/半年/1年/超1年） |
| **Star 时间筛选** | 按用户 star 的时间筛选，了解近期关注领域 |
| **双维度统计卡片** | 同时显示项目活跃度和 Star 时间分布 |

### 数据字段清单

**基本信息：**
- `full_name`, `name`, `owner`, `html_url`, `description`, `homepage`

**时间维度（关键）：**
- `starred_at` - 用户何时 star 的
- `created_at` - 仓库创建时间
- `updated_at` - 最后更新时间
- `pushed_at` - 最后推送时间
- `local_fetched_at` - 本地抓取时间

**统计数据：**
- `stargazers_count`, `forks_count`, `watchers_count`, `open_issues_count`

**分类信息：**
- `language`, `topics`, `license`, `visibility`

**项目特征：**
- `is_fork`, `is_archived`, `is_template`, `has_wiki`, `has_pages`, `has_discussions`

### 使用示例

```bash
# 重新初始化获取完整数据（27个字段）
python scripts/main.py --init --user cat-xierluo

# 查看 Dashboard（包含活跃度筛选）
open output/dashboard.html
```

### 技术改进

- `save_latest()` 方法重写，保存完整仓库信息
- `get_starred_repos()` 添加 `include_starred_at` 参数，使用 `application/vnd.github.star+json` 获取 starred_at
- Dashboard 添加活跃度统计卡片和筛选下拉框
- JavaScript 添加 `getActivityCategory()` 和 `updateActivityStats()` 函数

---

## [0.4.2] - 2026-02-12

### 新增（输出目录规范）

| 变更 | 说明 |
|------|------|
| **output/ 目录** | 创建专用目录存放运行时生成的文件 |
| **文件组织** | `dashboard.html` 和 `projects.json` 移至 `output/` |
| **gitignore 更新** | 忽略整个 `output/` 目录 |

### 使用说明

运行 `--export` 后，生成的文件位于 `output/` 目录：

- `output/projects.json` - 导出的项目数据
- `output/dashboard.html` - 可视化面板

打开 `output/dashboard.html` 即可查看数据可视化。

---

## [0.4.1] - 2026-02-12

### 修复（目录结构规范化）

- **配置文件散落在根目录** → 移至 `assets/` 目录符合 SKILL-GUIDE.md 规范
- **文档路径引用错误** → 更新 SKILL.md 和 CHANGELOG.md 中的路径

### 变更内容

- 移动 `dashboard.example.html` → `assets/dashboard.example.html`
- 移动 `projects.example.json` → `assets/projects.example.json`
- 移动 `categories.yaml` → `assets/categories.yaml`
- 移动 `tags.json` → `assets/tags.json`
- 更新 `scripts/main.py` 中的模板路径引用
- 更新 `SKILL.md` 配置文件说明

---

## [0.4.0] - 2026-02-12

### 新增（分类与标签系统）

| 功能 | 说明 |
|------|------|
| **分类配置** | `assets/categories.yaml` - 8种预设分类，可自定义 |
| **标签管理** | `assets/tags.json` - 添加、编辑、删除标签 |
| **智能分类** | 根据关键词自动匹配分类（语言/topics/description）|
| **标签云** | Dashboard 顶部显示所有标签，点击筛选 |
| **分类筛选** | 按预设分类（AI/Web/桌面/移动等）筛选项目 |
| **搜索增强** | 支持标签名和关键词搜索 |
| **统计增强** | 显示已分类项目数量 |

### 使用示例

```bash
# 导出数据（现在包含分类和标签）
python scripts/main.py --export

# 编辑分类配置
vim ~/.github-star-tracker/categories.yaml

# 添加新标签
python scripts/main.py --add-tag "游戏引擎" --color "#f472b6"

# 按分类查看
# 然后在 Dashboard 中点击对应分类标签
```

### 技术改进

- 新增 `assets/categories.yaml` 和 `assets/tags.json` 配置文件
- `StarTracker` 添加 `_load_categories()`, `_load_tags()`, `get_categories_map()` 方法
- `StarTracker` 添加 `_match_category()` 方法，根据关键词智能匹配分类
- `get_starred_repos()` 返回的每个仓库包含 `category` 和 `matched_keywords` 字段
- Dashboard 全面重构，支持标签云、分类筛选、搜索

---

## [0.3.1] - 2026-02-12

### 修复

| 问题 | 解决方案 |
|------|----------|
| 只能获取 100 个 Star | 移除 limit 限制，支持分页获取全部 Star |
| 用户名必须手动输入 | 添加 `get_authenticated_user()` 自动获取 Token 对应的用户名 |
| `language=None` 导致崩溃 | 修复空值检查 |
| 符号链接报错 | 修复 `save_snapshot()` 文件覆盖逻辑 |

### 改进

- 默认 limit 从 100 提升到 9999（获取全部）
- Dashboard 修复本地文件加载问题
- `--user` 参数改为可选，未提供时自动获取

---

## [0.3.0] - 2026-02-12

### 新增（Star 管理功能）

| 命令      | 说明                           |
|-----------|------------------------------|
| `--star owner/repo`    | 为单个仓库添加 Star            |
| `--unstar owner/repo`  | 取消单个仓库的 Star           |
| `--cleanup --days 90`   | 查找并清理长期未更新的仓库     |
| `--batch-unstar file.json` | 批量取消 Star（从 JSON 文件） |
| `--batch-star file.json`  | 批量添加 Star（从 JSON 文件）  |

### 使用示例

```bash
# 单个操作
python scripts/main.py --star owner/repo           # 添加 Star
python scripts/main.py --unstar owner/repo        # 取消 Star

# 清理陈旧项目
python scripts/main.py --cleanup --days 90         # 预览（默认）
python scripts/main.py --cleanup --days 90 --execute  # 实际执行

# 批量操作
python scripts/main.py --batch-unstar repos.json   # 批量取消
python scripts/main.py --batch-star repos.json    # 批量添加
```

### 技术改进

- `StarTracker` 类新增 `star_repo()`, `unstar_repo()`, `is_starred()` 等方法
- 添加 `--execute` 安全确认机制，避免误操作
- 所有破坏性操作（取消 Star）默认预览，需要 `--execute` 确认

---

## [0.2.0] - 2026-02-12

### 新增

- **HTML Dashboard**：实现信息密集型可视化面板，支持一屏浏览大量项目
- **数据导出功能**：新增 `--export` 命令，生成 projects.json 供 Dashboard 使用
- **状态筛选**：支持按活跃度（活跃/近期更新/长期未更）和价值（高/中）筛选
- **搜索功能**：支持按项目名、描述、标签进行关键词搜索
- **示例文件机制**：创建 dashboard.example.html 作为模板，首次运行自动复制

### 改进

- 从 knowledge-retention skill 重构，移除社交媒体截图转化功能
- 专注核心功能：更新追踪、版本检测、活跃度分析
- 卡片点击展开详情：显示创建时间、Forks、Issues 等信息

### 技术优化

- 使用 CSS 变量管理主题色值
- 响应式布局，支持移动端浏览
- 本地 JSON 数据缓存，减少 API 请求
