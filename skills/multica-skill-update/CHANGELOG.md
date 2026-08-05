# 变更日志

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
