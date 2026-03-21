# 变更日志

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
