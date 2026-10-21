# 变更日志

## [1.9.1] - 2026-10-16

### 修复
- **`--apply --register` 组合失效**：REGISTER 分支优先级高于修复分支，导致组合使用时只登记不修复（真实踩坑：一批链接连续两轮"修复"实际零动作，靠旧链接 mtime 未变发现）。现改为 register 仅在**不带 --apply** 时走纯登记；组合使用正常执行修复并在尾部统一登记。

### 改进
- 默认 harness 列表扩充 `.hermes`、`.myagents`（真实存在且承载技能安装的 Agent 框架，实测全盘扫描发现其内有漏网旧链）。
- 浅层模式支持 skills/commands 下的**分类子目录一层**（如 `~/.hermes/skills/personal/<skill>` 三层结构），仍毫秒级。
- `--full-home` 耗时描述如实修正：全 home 树实测可达十余小时（视目录规模），非"数分钟"；分层设计的默认档（浅层）与登记档（--from-registry）才是日常路径。

### 验证
- 云同步目录（Documents/Mac同步文件夹）深层漏网链接修复后 20s/15s 两次复扫零回滚；.hermes/.myagents/Documents 三根 deep 终验 0；registry 累计登记 multi-agent-orca 56 处。


## [1.9.0] - 2026-10-16

### 新增
- **安装即登记（链接出生带建档）**：install.sh 创建符号链接的四个路径（单 skill/command/批量 skills 集合/批量 commands 集合）全部调用 record_install；record.py 的 record_install 把本次安装位置追加进 registry `install_links`（幂等去重、保留历史登记不被覆盖）。经 skill-manager 安装的链接从此天然进建档，改名时 `relink-skill.py --from-registry` 直接查表，无需事后 `--register` 补录；手工建的链接仍可用 --register 兜底。
- record.py 的 registry 路径支持 `SKILL_MANAGER_REGISTRY` 环境变量覆盖（与 relink-skill.py 一致，测试/非标准安装位置）。

### 验证
- 端到端：install.sh 安装 → registry 自动含 install_links（via=install）→ 源目录改名 → relink --from-registry 0.0s 修复并回写新名条目 → 重复安装同位置去重（links 恒 1）。


## [1.8.4] - 2026-10-15

### 改进
- **relink-skill.py 浅层模式支持项目集合目录**：--roots 传入的目录除自身 8 类 harness 外，自动向下发现一层子项目的 harness（如把项目集合根传入，其下每个子项目的 .claude/.codex 都会被检查），毫秒级完成（实测 432 个展开根 0.1s）。真实建档验证：multi-agent-orca 一次登记 35 处链接位置（用户级 5 + 9 个子项目 26 + 两层深项目 4）。


## [1.8.3] - 2026-10-15

### 新增
- **relink-skill.py 登记优先模式（`--register` / `--from-registry`）**：回答"能否按目标文件夹反查其符号链接位置"——文件系统不维护反向索引（symlink 是单向字符串、Spotlight 不索引），唯一秒级路径是登记表。`--register` 把链接位置写入 registry `install_links`（位置导向）；`--apply` 修复后自动登记；`--from-registry` 下次改名直接查表定位（实测 0.23s 含修复与回写），无登记自动回退浅层扫描。registry 路径支持 `SKILL_MANAGER_REGISTRY` 环境变量覆盖（测试/非标准安装位置）。


## [1.8.2] - 2026-10-15

### 改进
- **relink-skill.py 扫描改三档分级，默认档提速数千倍**：默认浅层只查 8 类用户级 harness（.claude/.codex/.agents/.zcode/.openclaw/.workbuddy/.qoderworkcn/.codebuddy）与 --roots 项目根各自的顶层、skills/、commands/ 一层，毫秒级完成（实测 16 根 0.05s，对比全盘 20 分钟+）；`--deep` 完整递归；`--full-home` 全盘兜底不变。依据：真实消费者链接全部挂在配置根浅层，深层链接属于历史快照/归档（40 链接实测清单验证）。
- --roots 传项目根时自动展开按 `<项目>/<harness>/` 浅层检查，传 harness 根（basename 为 .claude 等）则直用；--deep --roots-only 只递归指定根。
- 明确记录：Spotlight（mdfind）实测不索引符号链接（存量查询只返回实体目录、新建链接不出现），不能作为快路径，勿再尝试。


## [1.8.1] - 2026-10-15

### 新增
- **relink-skill.py 增加 `--full-home` 全盘扫描模式**：项目不一定集中在已知根目录（如项目住在 `~/Library/Application Support` 等非常规位置），`--full-home` 扫描整个用户主目录，自动跳过确定不承载 Agent 配置的重资源区（Caches、Containers、Group Containers、MobileSync、iCloud/CloudStorage 挂载、Photos 图库、Developer、.Trash 等）控制耗时；`~/Library/Application Support`（项目常驻处）不跳。外置卷不默认扫，用 `--roots /Volumes/卷名` 追加。

### 改进
- **默认扫描根去机器特定化**（公开分发要求）：默认只扫通用的用户级 Agent 配置目录（`~/.agents/skills`、`~/.claude`、`~/.codex`、`~/.zcode`），移除上一版内置的本机项目根；项目级位置因人而异，一律用 `--roots` 显式传入或 `--full-home` 兜底，不做猜测。


## [1.8.0] - 2026-10-15

### 新增
- **改名后的本机软链收敛工具 `scripts/relink-skill.py`**：skill 目录改名/迁移后，有界扫描用户级（~/.claude/.codex/.agents/.zcode）与项目级（maoscripts、~/orca/workspaces）配置根，找出指向旧路径的符号链接并批量修复。默认 dry-run，--apply 执行，--exclude-glob 跳过历史快照，--report 输出 JSON 追溯报告。来源：multi-agent-orca v3.0.1 改名实战（40 链接盘点、13 处手工修复暴露的链式断链问题）。

### 技术优化
- 目录级符号链接纳入扫描（os.walk 将其归入 dirnames 而非 filenames，须单独检查，否则 skills 安装链全部漏扫）；相对链接修复后保持相对形态，避免把本机绝对路径写进仓库内相对链接。
- 分类修复策略：同名安装链在目标已有新名链接时只删旧链，无异名脚本链（如 night-watch.sh）保持链接名重指新路径。


## [1.7.2] - 2026-08-13

### 改进
- **`.claude` 优先安装**：项目根同时存在多个 Agent 配置目录时（如 `.claude` + `.workbuddy`），`find_agent_config_dir` 与 `find_all_agent_config_dirs` 改为**优先返回 `.claude`**，不再批量安装到所有 Agent 目录。契合「`.claude/skills` 为单一技能来源、其他 Agent 通过符号链接指向它」的架构。
- SKILL 触发描述同步补充 WorkBuddy/CodeBuddy 与 `.codebuddy/.workbuddy` 识别边界。

### 修复
- **`~/.codebuddy` 误判为目标目录**：此前从 CodeBuddy 配置目录内部（如 `~/.codebuddy/skills/skill-manager`）调用时，向上查找会撞上 `~/.codebuddy/.claude` 并误装。现将 `.codebuddy` 纳入全局配置根名单（`target.sh` 两处 global-config-roots 循环 + `install.sh` 的 `_is_global_config_root()`），使其被识别为全局根并走 git 救援 / 提示 `--target`，不再静默误装。

### 重新应用
本版本为对上游 skill-manager 的本地定制补丁。若日后通过 `skill-manager update` 更新被覆盖，重新应用步骤与完整 diff 见 `DECISIONS.md` 的 `[DEC-007]`。

## [1.7.1] - 2026-07-07

### 修复
- **install.sh 自循环软链防护**：批量安装 skills 集合目录时，若 `SKILLS_DIR` 解析到与 source 同一路径（或 source 处于 target 内部），原本会为每个子 skill 产生 `skill/skill -> ../skill` 的自循环死链。修复后改为：
  - 用 `cd -P` 解析 source 与 target 真实路径
  - 当 `source` 路径前缀是 `target` 路径时跳过该 skill 并提示 `⏭  跳过（自循环）`
  - 同时给 commands 集合分支加同款保护
  - 用 `|| true` 包裹 `cd` 调用，避开 `set -e` 在 target 还不存在时的提前退出
- **清理 legal-skills/skills 残留 33 个自循环软链**：因 1.7.0 重装 install.sh 之前对自身跑过 install，遗留一批 `skill-name/skill-name` 自循环，已逐个删除

## [1.7.0] - 2026-07-06

### 新增
- **项目 Agent 初始化**：新增 `scripts/init.sh`，为项目创建 Agent skills 符号链接结构
  - 默认初始化 `.codex`、`.openclaw`、`.workbuddy`、`.qoderworkcn` 四个 Agent
  - 核心操作： `{agent}/skills -> ../.claude/skills` 相对符号链接，`.claude/skills/` 为单一技能来源
  - 支持 `--all`、`--qoderwork`、`--workbuddy`、`--codex`、`--openclaw`、`--claude` 灵活选择 Agent
  - 支持 `--dry-run` 预览模式和 `--gitignore` 自动更新 `.gitignore`
  - 智能冲突处理：正确 symlink 跳过，错误指向重建，实体目录带时间戳备份

### 改进
- SKILL.md 新增「项目初始化」章节，完整文档化 init 命令选项、冲突处理和项目根查找逻辑
- 目录结构图加入 `init.sh` 条目

## [1.6.0] - 2026-07-06

### 新增
- **QoderWork 支持**：新增 `.qoderworkcn` 作为受支持的 Agent 配置目录，自动检测 `~/.qoderworkcn/skills/` 作为安装目标
- **全局根目录识别**：在 `~/.qoderworkcn` 或其子目录调用时，自动将目标设为 `~/.qoderworkcn/skills/`
- **项目级 QoderWork 配置识别**：项目根目录包含 `.qoderworkcn/` 时，自动选择为目标目录

### 改进
- `target.sh` 中所有 Agent 配置目录检测循环统一扩展 `.qoderworkcn`
- `install.sh` 的 `_is_global_config_root()` 新增 `.qoderworkcn` 判定
- 更新 SKILL.md 文档描述、目标目录识别和使用示例，涵盖 QoderWork 场景

## [1.5.0] - 2026-05-17

### 新增
- **远程安装元数据追踪**：注册表新增 `install_type`、`install_commit`、`install_branch`、`remote_url`、`remote_subpath` 字段，记录 GitHub 安装的完整上下文
- **智能更新检测**：双策略检测远程 Skill 更新 — 有版本号时比较版本，无版本号时检查 Commits 与安装时间对比
- **子目录精确追踪**：GitHub 子目录安装时记录完整子路径，commit 检查精确到 Skill 所在子目录
- **可配置检查间隔**：通过 `SKILL_MANAGER_CHECK_THRESHOLD` 环境变量自定义自动检查间隔（默认 7 天）
- **向后兼容迁移**：旧注册表条目自动填充新字段默认值

### 修复
- **GitHub 子目录安装缺少记录**：修复从 GitHub 子目录安装时未调用 `record_install` 的问题
- **GitHub Commits 抓取**：修复 `get_github_commits()` 因 GitHub 页面结构变更导致无法获取 commit 的问题

### 改进
- `install.sh` 在删除 `.git` 前捕获 commit hash 和 branch
- `check-all` 跳过本地安装的 Skill（符号链接自动同步，无需远程检查），仅检查远程安装的 Skill
- `record.py list` 显示安装类型、commit、branch 等新增字段

## [1.4.0] - 2026-05-17

### 新增
- **Codex 目标目录支持**：在 `/Users/maoking/.codex` 或其子目录调用时，自动将 Skill/Command 安装到 `.codex/skills/` 或 `.codex/commands/`
- **项目级 Codex 配置识别**：当调用目录或上级目录包含 `.codex/`、`.claude/`、`.openclaw/` 时，自动选择对应 Agent 配置目录
- **目标目录覆盖变量**：支持通过 `SKILL_MANAGER_TARGET_DIR` 显式指定目标 Agent 配置根目录

### 改进
- 抽取 `scripts/target.sh` 作为安装、列表、卸载、更新脚本共用的目标目录识别模块
- `list.sh`、`remove.sh`、`update.sh` 改为从调用目录识别目标，行为与 `install.sh` 保持一致
- Skill 目录识别规则扩展到 `.codex` 和 `.openclaw` 子目录
- 修正文档中的注册表路径说明为 `assets/skill-registry.json`

### 修复
- 修复安装记录时间戳使用 UTC 时间拼接本地时区偏移，导致显示时间偏早的问题

## [1.3.0] - 2026-04-08

### 新增
- **版本追踪**：自动记录每个 Skill 的安装时间、来源 URL 和版本号
- **更新检查**：新增 `scripts/check.sh` 脚本，检查所有已安装 Skills 的最新版本
- **更新提示**：显示有更新的 Skills 列表，包含版本对比和变更摘要
- **持久化存储**：安装记录保存在 `assets/skill-registry.json`
- **Changelog 获取**：自动从 GitHub 获取远程 CHANGELOG.md 内容
- **Commits 获取**：当没有 CHANGELOG 时，自动获取最近的 commits 作为更新内容参考
- **子目录支持**：支持 GitHub 仓库子目录中的 Skill 安装

### 改进
- 安装时自动调用记录模块，无需手动操作
- 更新时自动记录版本变更历史
- 无需 GitHub API，直接读取网页获取版本和变更信息
- 检查更新时区分三类状态：有更新 / 已是最新 / 检查失败

### 技术细节
- 新增 `scripts/record.py` 核心记录管理模块
- 新增 `scripts/check.sh` 更新检查脚本
- 新增 `assets/` 目录存储注册表数据
- 修改 `scripts/install.sh` 安装后自动记录
- 修改 `scripts/update.sh` 更新后自动记录

## [1.2.0] - 2026-02-21

### 新增
- **安全检查**：从 GitHub 安装 skill 时自动进行安全检测
  - 检测危险代码模式（命令执行、敏感文件访问、数据外泄等）
  - 检测 Skill 特有风险（安装钩子、MCP 服务器等）
  - 检测提示词安全风险（提示注入、数据收集指令等）
  - 检测硬编码凭证（API Key、Token 等）
  - 生成 Markdown 格式的安全报告

### 改进
- 仅 GitHub 安装触发安全检查，本地安装不检查
- 无 Python 环境时静默跳过安全检查
- 安全检查发现问题不会阻止安装，仅输出警告

### 技术细节
- 新增 `scripts/security.py` 安全分析模块
- 修改 `scripts/install.sh` 在 GitHub 安装后调用安全检查

## [1.1.1] - 2026-02-09

### 修复
- **项目目录检测**：修复通过 Skill 工具调用时，错误将符号链接创建到全局 `~/.claude/skills/` 而非项目本地 `.claude/skills/` 的问题
- **原始目录保存**：在脚本开头保存 `ORIGINAL_PWD`，确保 `find_claude_dir()` 从调用者的原始工作目录开始查找 `.claude`

## [1.1.0] - 2026-01-21

### 新增
- **Command 支持**：现在可以管理 `.claude/commands/` 目录下的命令文件
- **统一管理**：所有脚本（install、list、remove、update）同时支持 Skills 和 Commands
- **自动类型检测**：根据文件扩展名（.md）自动识别 Command，根据目录结构识别 Skill
- **批量安装 Commands**：支持批量安装 commands 目录下的所有 .md 文件

### 改进
- **路径解析优化**：新增 `find_claude_dir()` 函数，通过向上查找 `.claude` 目录，支持符号链接结构
- **更清晰的输出**：list.sh 分别显示 Skills 和 Commands，便于查看

### 技术细节
- Skill 识别规则：包含 `SKILL.md` / `skill.md` / `.claude/` 的目录
- Command 识别规则：`.md` 文件
- 集合目录规则：
  - Skills 集合：包含多个 skill 子目录
  - Commands 集合：包含多个 `.md` 文件

## [1.0.0] - 2026-01-21

### 新增
- 初始版本发布
- 支持从本地路径安装单个 skill（符号链接）
- 支持批量安装本地 skills 集合目录（符号链接）
- 支持从 GitHub 仓库根目录克隆 skill
- 支持从 GitHub 子目录稀疏克隆 skill
- 支持列出已安装的 skills
- 支持卸载 skills
- 支持更新 Git 克隆的 skills
- 自动识别 skill 目录（SKILL.md、skill.md 或 .claude 目录）
