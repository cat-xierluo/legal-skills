# 变更日志

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
