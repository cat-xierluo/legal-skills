# 变更日志

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
