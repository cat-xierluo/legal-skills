# 变更日志

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
