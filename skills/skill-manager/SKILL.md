---
name: skill-manager
description: 管理 Claude Code Skills 和 Commands 的安装、同步、卸载和列表查看，支持从本地路径或 GitHub 仓库/子目录安装。本技能应在用户需要安装外部 skill/command、从 GitHub 仓库同步、批量安装本地目录、查看已安装的 items、或卸载不需要的 item 时使用。
license: Complete terms in LICENSE.txt
---

# Skill & Command Manager

管理 Claude Code Skills 和 Commands 的安装、同步、卸载和列表查看。

## 前置条件

- Git 已安装（用于 GitHub 克隆）
- 有写入 `.claude/skills/` 和 `.claude/commands/` 目录的权限

## 安装行为

- **本地路径 (Skill)** → 符号链接（保持与源同步）
- **本地路径 (Command)** → 符号链接（保持与源同步）
- **本地集合目录** → 批量符号链接
- **GitHub 仓库/子目录** → 克隆后删除 .git（静态复制）

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
scripts/install.sh <source>

# 示例
scripts/install.sh ~/dev/my-skills/pdf-tool
scripts/install.sh ~/dev/my-commands/deepresearch.md
scripts/install.sh ~/dev/my-skills/
scripts/install.sh ~/dev/my-commands/
scripts/install.sh https://github.com/anthropics/claude-code
scripts/install.sh jgtolentino/insightpulse-odoo/main/docs/claude-code-skills/community
```

### 列出已安装 Items

```bash
scripts/list.sh
```

显示 `.claude/skills/` 和 `.claude/commands/` 目录下所有已安装的 items 及其类型（符号链接或克隆）。

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

## 识别规则

### Skill 目录规则
一个目录被视为有效的 skill 目录，如果它包含：
- `SKILL.md` 文件（标准 skill）
- 或 `skill.md` 文件（变体）
- 或 `.claude` 子目录

### Command 文件规则
- 文件扩展名为 `.md`

### 集合目录规则
- **Skills 集合**：包含多个 skill 子目录
- **Commands 集合**：包含多个 `.md` 文件

## 使用示例

```bash
# ========== Skills ==========
# 安装本地单个 skill
skill-manager install ~/dev/my-skills/pdf-tool

# 批量安装本地目录下的所有 skills
skill-manager install ~/dev/my-skills/
skill-manager install ../other-project/.claude/skills/

# 从 GitHub 仓库根目录安装
skill-manager install https://github.com/anthropics/claude-code
skill-manager install anthropics/claude-code

# 从 GitHub 子目录安装
skill-manager install https://github.com/jgtolentino/insightpulse-odoo/tree/main/docs/claude-code-skills/community
skill-manager install jgtolentino/insightpulse-odoo/main/docs/claude-code-skills/community

# ========== Commands ==========
# 安装本地单个 command
skill-manager install ~/dev/my-commands/deepresearch.md

# 批量安装本地目录下的所有 commands
skill-manager install ~/dev/my-commands/

# ========== 通用操作 ==========
# 列出已安装的 skills 和 commands
skill-manager list

# 卸载 skill
skill-manager remove pdf-tool

# 卸载 command
skill-manager remove deepresearch

# 更新所有 git 克隆的 skills
skill-manager update

# 更新指定 skill
skill-manager update claude-code
```

## 目录结构

```
skill-manager/
├── SKILL.md              # 本文件
├── scripts/
│   ├── install.sh        # 安装脚本
│   ├── list.sh           # 列表脚本
│   ├── remove.sh         # 卸载脚本
│   └── update.sh         # 更新脚本
└── CHANGELOG.md          # 变更日志
```
