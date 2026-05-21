---
name: skill-manager
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.5.0"
description: 管理 Claude Code、Codex 和 OpenClaw Skills 的安装、版本追踪和更新检查。支持从本地路径或 GitHub 仓库安装，自动识别 .codex/.claude/.openclaw 目标目录，记录每个 Skill 的安装时间、来源 URL 和版本号，并检查 GitHub 更新。
license: Complete terms in LICENSE.txt
---

# Skill Manager

管理 Claude Code、Codex 和 OpenClaw Skills/Commands 的安装、同步、卸载和列表查看。

## 前置条件

- Git 已安装（用于 GitHub 克隆）
- 有写入目标 Agent 配置目录的权限，例如 `.codex/skills/`、`.claude/skills/`、`.openclaw/skills/`

## 安装行为

- **本地路径 (Skill)** → 符号链接（保持与源同步）
- **本地路径 (Command)** → 符号链接（保持与源同步）
- **本地集合目录** → 批量符号链接
- **GitHub 仓库/子目录** → 克隆后删除 .git（静态复制）+ 自动安全检查

## 目标目录识别

执行安装、列表、卸载、更新时，脚本会从调用目录向上查找 Agent 配置目录：

- 在 `/Users/maoking/.codex` 或其子目录调用时，目标为 `/Users/maoking/.codex/skills/`
- 在项目根目录包含 `.codex/`、`.claude/` 或 `.openclaw/` 时，目标为对应配置目录下的 `skills/` 或 `commands/`
- 在 `.codex/skills/`、`.claude/skills/`、`.openclaw/skills/` 内调用时，目标为其上级配置目录
- 如需显式指定目标根目录，可使用 `--target` 参数或设置 `SKILL_MANAGER_TARGET_DIR=/path/to/.codex`
- 从全局配置目录（如 `~/.claude`）调用时，会尝试通过 git 自动发现项目本地目录，并打印告警

## 支持的来源类型

### 本地路径（符号链接）
```bash
# 单个 skill 目录
skill-manager install ~/skills/pdf-tool

# 单个 command 文件
skill-manager install ~/commands/deepresearch.md

# 包含多个 skills 的目录（批量安装）
skill-manager install ~/skills/external-skills/

# 包含多个 commands 的目录（批量安装）
skill-manager install ~/commands/
```

### GitHub 仓库根目录（克隆，删除 .git）
```bash
skill-manager install https://github.com/owner/skill-repo
skill-manager install owner/skill-repo
```

### GitHub 子目录（稀疏克隆，删除 .git）
```bash
# 完整 URL 到子目录
skill-manager install https://github.com/jgtolentino/insightpulse-odoo/tree/main/docs/claude-code-skills/community

# 简写格式：owner/repo/branch/path/to/skills-directory
skill-manager install jgtolentino/insightpulse-odoo/main/docs/claude-code-skills/community
```

## 工作流程

### 安装

1. **检测来源类型** - 自动识别本地路径、GitHub 仓库或子目录
2. **检测 Item 类型** - 自动识别是 Skill（目录）还是 Command（.md 文件）
3. **检测是否为集合目录** - 检查目录是否包含多个 items
4. **批量处理模式** - 如果是集合目录，遍历所有 items 并分别安装
5. **本地来源** - 创建符号链接，保持与源同步更新
6. **GitHub 仓库根** - 使用 `git clone --depth 1` 浅克隆
7. **GitHub 子目录** - 使用稀疏克隆（sparse checkout）仅获取指定目录
8. **冲突处理** - 已存在时先备份为 `.backup`，然后安装新版本

#### 安装命令

```bash
# 使用脚本安装
scripts/install.sh [--target <dir>] <source>

# 示例
scripts/install.sh ~/dev/my-skills/pdf-tool
scripts/install.sh ~/dev/my-commands/deepresearch.md
scripts/install.sh ~/dev/my-skills/
scripts/install.sh ~/dev/my-commands/
scripts/install.sh https://github.com/anthropics/claude-code
scripts/install.sh jgtolentino/insightpulse-odoo/main/docs/claude-code-skills/community

# 显式指定目标（从非项目目录调用时使用）
scripts/install.sh --target /path/to/project/.claude ~/dev/my-skills/pdf-tool
```

### 列出已安装 Items

```bash
scripts/list.sh
```

显示当前识别到的 Agent 配置目录下所有已安装的 items 及其类型（符号链接或克隆）。

### 卸载

```bash
scripts/remove.sh <name>
```

删除指定的 skill 或 command（自动识别类型）。

### 更新

```bash
scripts/update.sh [name]
```

- 不指定参数：更新所有通过 git 克隆的 skills
- 指定名称：更新指定的 skill
- **注意**：符号链接的 items 会自动与源同步，无需手动更新

### 检查更新

```bash
scripts/check.sh
```

检查所有远程安装 Skills 的更新状态，检测策略：
- **有版本号** → 直接比较本地与远程版本号
- **无版本号** → 检查远程仓库最近 Commits，与安装时间对比
- **子目录安装** → 精确检查 Skill 所在子目录的 Commits

显示：
- 📦 有可用更新的 Skills
- ✅ 已是最新版本的 Skills
- ⚠️ 检查失败的 Skills（无来源信息等）

每次安装和更新都会自动记录到 `assets/skill-registry.json`。

### 查看已安装记录

```bash
python3 scripts/record.py list
```

显示所有已安装 Skills 的详细记录，包括：
- 安装时间
- 来源 URL
- 当前版本
- 描述信息

## 识别规则

### Skill 目录规则
一个目录被视为有效的 skill 目录，如果它包含：
- `SKILL.md` 文件（标准 skill）
- 或 `skill.md` 文件（变体）
- 或 `.codex` / `.claude` / `.openclaw` 子目录

### Command 文件规则
- 文件扩展名为 `.md`

### 集合目录规则
- **Skills 集合**：包含多个 skill 子目录
- **Commands 集合**：包含多个 `.md` 文件

## 使用示例

```bash
# ========== 安装 ==========
# 安装本地单个 skill
skill-manager install ~/dev/my-skills/pdf-tool

# 批量安装本地目录下的所有 skills
skill-manager install ~/dev/my-skills/
skill-manager install ../other-project/.claude/skills/

# 在 Codex 全局目录中调用时，安装到 ~/.codex/skills/
cd /Users/maoking/.codex
skill-manager install ~/dev/my-skills/pdf-tool

# 从全局目录调用但安装到指定项目（使用 --target 避免装错位置）
skill-manager install --target /path/to/project/.claude ~/dev/my-skills/pdf-tool

# 从 GitHub 仓库根目录安装
skill-manager install https://github.com/anthropics/claude-code
skill-manager install anthropics/claude-code

# 从 GitHub 子目录安装
skill-manager install https://github.com/jgtolentino/insightpulse-odoo/tree/main/docs/claude-code-skills/community
skill-manager install jgtolentino/insightpulse-odoo/main/docs/claude-code-skills/community

# ========== 查看与管理 ==========
# 列出已安装的 skills
skill-manager list

# 卸载 skill
skill-manager remove pdf-tool

# ========== 更新与检查 ==========
# 检查所有 skills 的更新
skill-manager check

# 更新所有 git 克隆的 skills
skill-manager update

# 更新指定 skill
skill-manager update claude-code

# 查看安装记录
python3 scripts/record.py list
```

## 安全检查

从 GitHub 安装 skill 时，会自动进行安全检查（本地安装不检查）。

### 检测内容

| 类别 | 说明 |
|------|------|
| **危险代码模式** | 命令执行、敏感文件访问、数据外泄、代码混淆、权限提升等 |
| **Skill 特有风险** | 安装钩子、MCP 服务器配置等 |
| **提示词安全** | 提示注入、数据收集指令、执行指令、欺骗性描述等 |
| **硬编码凭证** | API Key、Token、密码等敏感信息 |

### 风险等级

- 🔴 **CRITICAL** - 极高风险，强烈建议不要使用
- 🟠 **HIGH** - 高风险，需审计后使用
- 🟡 **MEDIUM** - 中等风险，使用前请检查
- 🟢 **LOW** - 低风险，建议定期检查
- ✅ **NONE** - 未发现明显风险

### 注意事项

- 安全检查需要 Python 3 环境，无 Python 时静默跳过
- 检查发现问题不会阻止安装，仅输出警告报告
- 建议在安装外部 skill 后仔细阅读安全报告

## 注册表 Schema

每个已安装的 Skill 记录在 `assets/skill-registry.json` 中，包含以下字段：

| 字段 | 说明 |
|------|------|
| `name` | Skill 目录名 |
| `source` | 原始安装来源（本地路径或 GitHub URL） |
| `install_type` | `"local"`（符号链接）或 `"remote"`（GitHub 克隆） |
| `installed_at` | 初始安装时间（ISO 8601） |
| `last_updated` | 最后版本更新时间 |
| `last_check_at` | 最后一次更新检查时间（仅远程） |
| `installed_version` | 安装时的版本号 |
| `current_version` | 当前已安装版本 |
| `latest_version` | 远程最新版本 |
| `install_commit` | 安装时的 Git commit hash（仅远程） |
| `install_branch` | 安装时使用的 Git branch（仅远程） |
| `remote_url` | 完整 GitHub URL，含子目录路径（仅远程） |
| `remote_subpath` | Skill 在仓库中的子路径（仅子目录安装） |
| `description` | Skill 描述 |
| `homepage` | 主页 URL |

## 目录结构

```
skill-manager/
├── SKILL.md                    # 本文件
├── CHANGELOG.md                # 变更日志
├── CLAUDE.md                   # AI 开发助手说明
├── LICENSE.txt                 # 许可证
├── scripts/
│   ├── install.sh              # 安装脚本
│   ├── list.sh                 # 列表脚本
│   ├── remove.sh               # 卸载脚本
│   ├── update.sh               # 更新脚本
│   ├── check.sh                # 更新检查脚本
│   ├── auto-check.sh           # 定期自动检查触发器
│   ├── target.sh               # Agent 配置目录识别模块
│   ├── record.py               # 记录管理模块
│   └── security.py             # 安全检查模块
└── assets/                     # 资源文件
    ├── skill-registry.json     # Skill 安装记录（运行时生成）
    └── skill-registry.example.json  # 注册表示例
```
