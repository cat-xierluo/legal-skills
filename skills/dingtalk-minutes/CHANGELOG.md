## [1.1.0] - 2026-08-17

### 新增
- `sync.py` 同步后默认自动镜像：本次有新增存档且已配置 `config/mirror-target.local.json` 时，同步完成即自动调用 `mirror_output.py` 增量镜像（sha256 校验，顺带补齐之前未镜像成功的文件），外部文件夹不再依赖手动跑 mirror
- 新增 `--no-mirror` 参数：需要只存档、不镜像时显式关闭
- 未配置镜像目标（退出码 2）时提示跳过、不影响存档；镜像失败只报告不回滚——archive 仍是权威源

### 背景
- 修复"每次同步后外部文件夹停在旧状态"的体验问题：此前 sync 与 mirror 是两个独立步骤，忘记手动跑 mirror 就漏导出（用户反馈）

## [1.0.1] - 2026-08-08

### 修复
- 澄清"只读"措辞：明确"只读"指不改动钉钉云端数据，归档/镜像/音频下载为本地落盘显式操作，消除文档与行为不一致（SkillSpector 审计反馈）
- 依赖表安装命令改为先下载到 `/tmp` 再 `sh` 执行，与 `references/02-setup.md` 一致，去除 `curl | sh` 直接执行远端脚本
- PATH 配置命令补充说明：会修改 `~/.zshrc` 持久配置，并给出手动配置替代方案
- 「本地归档与增量同步」章节新增隐私与合规提示：归档/镜像内容可能含敏感信息，勿提交公开仓库或共享目录

### 文档完善
- 首页「薄壳封装」说明补充"只读"边界与本地落盘区别的注释

## [1.0.0] - 2026-08-06

### 改进
- 版本号对齐：自 `0.7.0` 升至 `1.0.0`，与 ClawHub 公开发布版本保持一致（首次对外发布即采用 1.0.0 作为正式版本号）

### 新增
- 镜像到外部文件夹功能：`scripts/mirror_output.py`，把 archive 听记成品单向复制到外部指定目录（参照 `transformer-content` 的 mirror 模式）
- `config/mirror-target.example.json` 模板 + `.local.json`（本机路径，`.gitignore` 排除）
- 支持全量 / `--since YYMMDD` 日期过滤 / `--archive <单条听记>` / `--dest` 覆盖 / `--items` 白名单 / `--dry-run`
- 默认只镜像 `transcript.md` + `summary.md` + `todos.md`（不含 meta.json 结构化内部数据）
- 每个听记子目录写 `.mirror-manifest.json`（源路径 + 文件列表 + sha256），增量时目标哈希一致则跳过

### 改进
- SKILL.md 新增「镜像到外部文件夹」章节，含用法/配置/白名单/目录结构/增量校验说明

### 待办事项
- 视需求补充"听记→法律文书"业务封装层（当前为纯能力薄壳）

## [0.6.0] - 2026-08-05

### 改进
- archive 存档信息拉满（内部留底，文字维度全量提取）：每条听记除 `transcript.md` 逐字稿外，新增独立 `summary.md`（AI 摘要全文）、`keywords.md`（关键词）、`todos.md`（待办含负责人）
- `transcript.md` 头部新增概览区：关键词 + AI 摘要 + 待办，单文件即可纵览
- `meta.json` 扩充：补 `audio`（videoUrl/size/duration + 过期提示）、`creator`、`durationMicros` 等字段
- `get_extra` 适配 keywords 的 NDJSON 返回与 todos 的 `actions`/`dingtalkTodoList` 结构；`run_dws` 对 NDJSON 透传 `_raw` 供逐行解析
- 新增 `--with-audio` 开关：显式下载原始音频 mp3 到 archive（默认不下载，URL 带过期鉴权、单条约 150MB）
- 存量 42 条听记已一次性补全上述附属文件

### 待办事项
- 视需求补充"听记→法律文书"业务封装层（当前为纯能力薄壳）

## [0.5.0] - 2026-08-05

### 改进
- 存档目录命名由长串 taskUuid 改为可读格式 `YYMMDD_标题`（如 `260805_08-05 图书出版协作优化`），与听记标题一致、便于浏览
- `scripts/sync.py` 新增 `uuid_to_dir` 映射（index.json 内），去重与增量判定仍以 uuid 为准，目录名仅可读化，通过映射回溯，保证增量稳定
- 同日期同标题冲突时追加短 uuid 后缀兜底
- 现有 42 条 archive 目录已一次性重命名为新格式并写回映射
- SKILL.md 存档结构说明同步更新

### 待办事项
- 视需求补充"听记→法律文书"业务封装层（当前为纯能力薄壳）

## [0.4.0] - 2026-08-05

### 改进
- 重构 references 目录，去除冗余：删除 `_common/conventions.md`、`07-minutes.md`、`lite-recipes.md`（均为 dws 官方多视角文档，含写操作与外部 skill 引用，对薄壳越界）
- 将 `minutes.md`（2517 行，含大量写操作）重写为精简版 `references/01-commands.md`（仅读取类命令：list/+detail/get *，含参数陷阱与翻页）
- 踩坑文档由 `setup-troubleshooting.md` 重命名为 `references/02-setup.md`，与命令文档统一编号
- SKILL.md 引用同步更新；version 升至 0.4.0

### 待办事项
- 视需求补充"听记→法律文书"业务封装层（当前为纯能力薄壳）

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
