# 变更日志

## [0.5.3] - 2026-08-07

### 文档完善
- **清单模板与实例同目录**：`scripts/manifest.local.json`（个人实例）与 `scripts/manifest.example.json`（模板）统一放在 `scripts/` 下，不再设独立的 `config/` 目录；SKILL.md「文件结构」「个人清单机制」「准备清单」等章节同步改指 `scripts/` 路径。
- **移除技能自带 `.gitignore`**：清单是否入库交由外部仓库统一配置，技能内不再单独维护 `.gitignore`（原仅忽略 `config/manifest.local.json` 与 Python 缓存）。
- **精简 `description`**：SKILL.md frontmatter 描述缩短为「按来源清单批量导入/更新到 Multica skill 数据库，支持 init / update / plan 三种模式」，保留触发关键词；frontmatter 版本号对齐至 0.5.3。

### 技术优化
- `sync_skills.py` 默认清单路径由 `<skill根>/config/manifest.local.json` 改为 `<skill根>/scripts/manifest.local.json`；缺失清单时的复制提示同步改为 `cp scripts/manifest.example.json scripts/manifest.local.json`。

## [0.5.2] - 2026-08-07

### 文档完善
- **结构重构（Progressive Disclosure）**：拆分过长的 SKILL.md（318 行）为三个 references 文件，入口只保留核心流程与链接：
  - `references/manifest-format.md`：清单字段说明、取值、分类标签用法（原 SKILL.md「清单格式」章节）。
  - `references/multica-importing-alignment.md`：与平台内置 `multica-skill-importing` 的分工、8 条语义对齐、服务端限制与媒体剔除（原 SKILL.md 同名章节）。
  - `references/workflow-examples.md`：真实调用示例与反向溯源工作流（原 SKILL.md「真实调用示例」「反向溯源」章节）。
- **消除第三份冗余 JSON**：SKILL.md 内联的清单示例 JSON 移除，统一引用模板文件与格式文档，避免与清单模板三处重复。
- **SKILL.md frontmatter 版本号对齐**：`0.4.0` → `0.5.1`，与 CHANGELOG 最新版本一致。

### 技术优化
- **清单模板位置迁移**：`references/manifest.example.json` 移至 `scripts/manifest.example.json`（模板随脚本归位，不再与 `config/manifest.local.json` 分处两个目录造成"同文件两处"的观感）；同步更新 `sync_skills.py` 缺失清单时的提示路径。

## [0.5.1] - 2026-08-06

### 改进
- **排除规则新增"媒体资产"两层剔除（方案 B，解决 `visual-card` 无法导入）**：`sync_skills.py` 在目录黑名单（`PACK_EXCLUDE_DIRS`）之外，新增两层媒体剔除：
  1. **演示目录媒体**：路径落在 `examples`/`sample`/`samples`/`demo`/`demos` 下且后缀命中 `PACK_EXCLUDE_MEDIA_SUFFIXES`（图片/视频）的文件剔除，但**保留其中的 `.md` 等文档**（避免误删 `legal-case-analysis/examples/*.md` 这类运行所需范文）。
  2. **通用体积兜底**：任意目录下体积超过 `PACK_MEDIA_MAX_SIZE`（256 KiB）且命中媒体后缀的文件也剔除。
- 两步都用"媒体后缀 + （目录或体积）"双条件，只剃展示性大图，**不误伤**运行所需的非媒体大文件（模型权重、数据文件）与文档。
- 解决 `visual-card` 因 `assets/examples/` 的 154 张示例图（21.2 MiB）卡在 8 MiB 与 256 文件双限制、无法导入的问题——实测剔除后降至 164 文件 / 2.0 MiB，达标。
- 剔除明细打印到日志（最多 8 条 + 余数），便于回查技能为何体积骤降。

### 文档完善
- SKILL.md 排除逻辑章节新增「大体积媒体资产自动剔除（体积兜底）」说明，记录 `visual-card` 实证与两层设计理由（演示目录只剔媒体、留文档）。

## [0.5.0] - 2026-08-06

### 新增
- **分类标签（本地清单侧）**：每条清单支持 `category` 字段（复用 project-init 的
  development / legal-document / content-writing 维度），便于按 agent 类型筛选导入。
  Multica 服务端不支持 skill 标签（源映射证实无 tags 字段、CLI 无 --tag），故标签**只存本地清单**，
  不参与导入，仅作 `--category` 过滤维度
- **`--category` 过滤参数**：`sync_skills.py` 支持只同步指定分类的技能
  （如 `--category legal-document`），配合"针对性给某个 agent 配一批 skill"
- **反向溯源工作流文档**：SKILL.md 新增「反向溯源」章节。清单 `url` 即本机源目录，
  Multica 内的 skill 是本地源的投影；约定"在 Multica 发现问题 → 改本地源文件 →
  重导（--mode update）"流程，明确不修改服务端投影。溯源依据含服务端 `config.origin`

### 文档完善
- SKILL.md 字段表新增 `category` / `group` 说明与分类用途注释、`--category` 示例、
  「反向溯源」章节（含为何不在 Multica 内直接改的理由）

## [0.4.1] - 2026-08-06

### 修复
- **个人清单路径合规化**：按 SkillLint 审计要求，个人配置文件从 skill 根目录的 `manifest.json`
  移至 `config/manifest.local.json`（与模板 `references/manifest.example.json` 分离）。
  根目录的 `manifest.json` 既违反 SkillLint 目录约定，又会因 `.gitignore` 失效而误入库泄露本机路径。
- 重建 `.gitignore`（此前因切分支丢失），明确忽略 `config/manifest.local.json`、`__pycache__/`、`*.pyc`

### 改进
- `sync_skills.py` 默认清单路径改为 `config/manifest.local.json`；`--manifest` 未指定时自动回退到此；
  找不到清单时给出「复制 references/manifest.example.json 为 config/manifest.local.json」的明确提示
- SKILL.md 全量同步路径表述（目录树、清单格式标题、使用步骤、对照表），与实际布局一致

## [0.4.0] - 2026-08-05

### 新增
- **本地技能目录直接导入**：`source=file` 的 `url` 现支持技能目录（含符号链接），
  脚本自动打包成临时 zip 后调用 `import --file`，用完即删。
  起因：`multica skill import --file` 仅接受 `.skill`/`.zip` 归档，不接受目录
- **结构化结果解析** `_handle_result()`：按 Multica 导入结果信封的 `status` 字段
  （`created`/`updated`/`conflict`/`skipped`/`failed`）判定，替代原先的 exit code +
  字符串匹配；报告中输出 skill id 与 files 数；`existing_skill.can_overwrite=false`
  时把 `failed` 归类为「非本人创建」而非真实错误。旧版服务端响应回退到字符串判断
- **服务端限制预检** `_precheck()`：打包后按单文件 1 MiB / 整包 8 MiB / 文件数 256 /
  上传 16 MiB 四项阈值告警（不阻断），并提示会被静默丢弃的同名 `SKILL.md` 支持文件
- SKILL.md 新增「与平台内置 `multica-skill-importing` 的分工」章节：
  说明上下游关系、八条语义对齐点（唯一合法路径、结果信封、overwrite 语义、
  服务端限制、丢弃规则、保留文件名、zip 布局、agent 绑定用 add 不用 set）

### 改进
- 打包排除名单扩充：新增 `archive`/`output`/`outputs`/`tmp`/`.cache`/`dist`/`build`/
  `.mypy_cache`/`.idea`/`.vscode` 目录及 `.pyd`/`.so`/`.dylib` 后缀、`Thumbs.db`；
  并排除所有 dotfile 目录（服务端本就会丢弃）。
  实测 `legal-ocr` 的 `archive/` 达 7.6 GB / 11 万文件，剔除后仅 21 文件 / 82 KB
- `_run()` 超时 120s → 300s（大包上传需要更久）；stdout 为空时回落读 stderr，
  避免冲突/失败时结构化信封丢失

### 验证
- 本地目录导入实测通过：`git-batch-commit`、`git-workflow`、`legal-ocr` 均成功落库
- 重复导入返回 `status: updated` 且 skill ID 不变（`f7d522b6...`），
  证实 `overwrite` 保留 ID / `created_by` / agent 绑定的语义
- `on_conflict` 三种策略实测符合内置 skill 文档：`fail`→`conflict`、
  `skip`→`skipped`、`overwrite`→`updated`
- 33 条个人清单全量预检：排除工作产物目录后仅 3 个技能存在 >1 MiB 二进制资产
  （docx 模板、头像图），均属服务端会主动丢弃的类型，不影响技能可用性

### 待办事项
- 33 条清单全量 `--mode init` 尚未执行（待用户确认后跑）
- `project-init/config/profiles.yaml` 存在 3 条失效引用（`skill-architect`、
  `zhihe-legal-research`、`contract-review`），建议清理

## [0.3.0] - 2026-08-05

### 新增
- 个人来源清单机制：skill 根目录 `manifest.json` 为私有同步清单（含本地文件路径/云端地址），
  已由本 skill 的 `.gitignore` 忽略，**不进公开仓库**；`references/manifest.example.json` 为入库模板
- `references/manifest.example.json` 补全四类来源示例：file（本地 .skill/.zip）、github、clawhub、skills.sh
- SKILL.md 更新文件结构与「准备清单」章节：说明本地 file 与云端地址的两种录入方式

### 待办事项
- 服务端恢复后实测一次真实 import 成功路径
- manifest.json 由用户填入真实本地/云端来源

## [0.2.0] - 2026-08-05

### 新增
- 实测确认 multica CLI（v0.4.19）已随 Multica 桌面 App 内置，路径：
  `/Applications/Multica.app/Contents/Resources/app.asar.unpacked/resources/bin/multica`（无需单独安装）
- sync_skills.py 新增 `--multica-bin`（显式指定 CLI 路径，默认自动探测 PATH → App 内置）、
  `--profile`（Multica profile，如 `desktop-api.multica.ai`）、`--workspace-id`
- 新增连接预检 `_check_connection`：`workspace list` 失败时提示加 `--profile`/`--workspace-id`
- SKILL.md 补充「真实调用示例」：profile/workspace 查找、plan/init 完整命令、实测要点

### 改进
- CLI 调用改为 `ctx.base_args()`（bin + profile + workspace-id），所有命令统一携带连接参数

### 验证
- 本机实测：自动探测 CLI 正确；`workspace list` 返回 `xierluo`；`skill list` 返回空（工作区暂无 skill）
- plan 模式正确拼接完整命令；`skill import --url` 命令格式与规划稿一致（服务端偶发不可用为 Multica 服务端问题）

### 待办事项
- 服务端恢复后需实测一次真实 import 成功路径（当前工作区为空，import 应返回 created）
- manifest.json（真实来源清单）由用户创建后嵌入 skill

## [0.1.0] - 2026-08-05

### 新增
- 基于 Multica 规划稿（`multica-skill-update` plan）落地实现：维护同步清单 → 批量导入/更新 Multica 工作区 skill
- `scripts/sync_skills.py`：init / update / plan 三模式执行脚本
  - init：初始化导入，同名已存在（conflict）视为正常，不报错退出
  - update：按清单 on_conflict 策略刷新（overwrite 更新 / skip 跳过非本人）
  - plan：无副作用预览，只列出将执行的操作
  - 支持 `--manifest`、`--dry-run`；multica CLI 缺失时预检报错退出码 2
  - 输出结构化同步报告（imported/conflict/skipped/failed），有失败时退出码非零
- `references/manifest.example.json`：清单模板（version/skills[]/source/url/on_conflict/enabled）
- SKILL.md：触发条件、核心原则、清单格式、两种模式、关键澄清（`import --on-conflict overwrite` 而非 `skill update`）、Autopilot 定时集成、验收标准

### 待办事项
- 本机尚未安装 multica CLI；安装后需实测 init/update 真实执行（当前以 plan/dry-run 验证）
- `autopilot create` / `trigger-add` 的 flags 需在本机 `--help` 确认后定稿
- manifest.json（真实来源清单）由用户创建后嵌入 skill
