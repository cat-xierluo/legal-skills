## [0.3.0] - 2026-08-05

### 新增
- **部署踩坑文档**：`references/setup-troubleshooting.md`，汇总他人从零部署必须跨过的三道门槛（安装 dws + 开启组织 CLI 访问开关 + 授权登录）及高频参数陷阱
- SKILL.md 新增「依赖」章节：dws 安装命令（含正确 `scripts/install.sh` 路径）、PATH 配置、授权与组织开关说明、开箱即用/需依赖功能划分
- 发布形态：补全 `version` frontmatter 字段、`LICENSE.txt`（MIT，统一版权），可直接发布到 `skills/`

### 改进
- 文档通用化：去除个人账号/组织绑定示例，面向任意钉钉用户（自装 dws、自授权、自开组织开关）
- 前置条件章节引用踩坑文档，避免重复且保持单一事实来源

### 文档完善
- README 最近更新区维护（由发布流程统一登记）

## [0.2.0] - 2026-08-05

### 新增
- 本地归档 + 增量同步机制：`scripts/sync.py`
- 存档结构：`archive/<uuid>/meta.json`（元数据+摘要+待办+关键词）与 `archive/<uuid>/transcript.md`（逐字稿，已翻页拉全）；状态文件 `archive/index.json`（last_sync + synced_uuids）
- 增量原理：以 `index.json` 的 `last_sync` 作 `dws minutes list all --start` 参数，服务端只返新增；本地已同步 uuid 跳过
- 支持 `--full`（全量重扫）/ `--list-new`（仅列新增）/ `--dry-run`（预览）/ `--archive-dir`（自定义目录）

### 改进
- SKILL.md 新增「本地归档与增量同步」章节，说明存档结构、命令、增量原理与使用约定

### 待办事项
- 视需求补充"听记→法律文书"业务封装层（当前为纯能力薄壳）

## [0.1.0] - 2026-08-05

### 新增
- 基于钉钉官方 dws CLI 的 `minutes` 服务，封装 AI 听记（妙记）**只读**能力薄壳技能
- 覆盖：听记列表查询（mine/shared/all）、聚合详情（+detail）、摘要/转写原文/关键词/待办/音频地址读取
- 复用 dws 内置 `dingtalk-minutes` 的 minutes.md / 07-minutes.md / lite-recipes.md 与通用规范，精简为只读边界
- 附带脚本：近期摘要合并、待办提取、列表解析

### 技术优化
- 明确剔除写操作（update/replace-text/upload/record/permission/speaker 等），避免薄壳误用

## [0.1.0] - 2026-08-05

### 新增
- 基于钉钉官方 dws CLI 的 `minutes` 服务，封装 AI 听记（妙记）**只读**能力薄壳技能
- 覆盖：听记列表查询（mine/shared/all）、聚合详情（+detail）、摘要/转写原文/关键词/待办/音频地址读取
- 复用 dws 内置 `dingtalk-minutes` 的 minutes.md / 07-minutes.md / lite-recipes.md 与通用规范，精简为只读边界
- 附带脚本：近期摘要合并、待办提取、列表解析

### 技术优化
- 明确剔除写操作（update/replace-text/upload/record/permission/speaker 等），避免薄壳误用

### 待办事项
- 视需求补充"听记→法律文书"业务封装层（当前为纯能力薄壳）
- private-skills 目录需初始化为独立私有 Git 仓库并配置 .gitignore
