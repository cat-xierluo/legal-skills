---
name: skill-manager
description: 管理 Claude Code skills 的安装、同步、卸载和列表查看。支持从本地路径或 GitHub 仓库/子目录安装 skills，自动识别并批量处理 skills 集合目录。使用场景：(1) 用户请求安装外部 skill，(2) 从 GitHub 仓库或子目录同步 skill，(3) 批量安装本地 skills 目录，(4) 查看已安装的 skills，(5) 卸载不需要的 skill。
---

# Skill Manager

管理 Claude Code skills 的安装、同步、卸载和列表查看。

## 前置条件

- Git 已安装（用于 GitHub 克隆）
- 有写入 `.claude/skills/` 目录的权限

## 安装行为

- **本地路径** → 符号链接（保持与源同步）
- **本地 skills 集合** → 批量符号链接
- **GitHub 仓库/子目录** → 克隆后删除 .git（静态复制）

## 支持的来源类型

### 本地路径（符号链接）
```bash
# 单个 skill 目录
skill-manager install ~/skills/pdf-tool

# 包含多个 skills 的目录（批量安装）
skill-manager install ~/skills/external-skills/
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

### 安装 Skills

1. **检测来源类型** - 自动识别本地路径、GitHub 仓库或子目录
2. **检测是否为集合目录** - 检查目录是否包含多个 skill 子文件夹
3. **批量处理模式** - 如果是集合目录，遍历所有 skill 子文件夹并分别安装
4. **本地来源** - 创建符号链接，保持与源同步更新
5. **GitHub 仓库根** - 使用 `git clone --depth 1` 浅克隆
6. **GitHub 子目录** - 使用稀疏克隆（sparse checkout）仅获取指定目录
7. **冲突处理** - 已存在时先备份为 `.backup`，然后安装新版本

#### 安装命令

```bash
# 使用脚本安装
scripts/install.sh <source>

# 示例
scripts/install.sh ~/dev/my-skills/pdf-tool
scripts/install.sh ~/dev/my-skills/
scripts/install.sh https://github.com/anthropics/claude-code
scripts/install.sh jgtolentino/insightpulse-odoo/main/docs/claude-code-skills/community
```

### 列出已安装 Skills

```bash
scripts/list.sh
```

显示 `.claude/skills/` 目录下所有已安装的 skills 及其类型（符号链接或克隆）。

### 卸载 Skills

```bash
scripts/remove.sh <skill-name>
```

删除指定的 skill，如果是符号链接则直接删除，如果是克隆目录则删除整个目录。

### 更新 Skills

```bash
scripts/update.sh [skill-name]
```

- 不指定参数：更新所有通过 git 克隆的 skills
- 指定 skill 名称：更新指定的 skill

## 识别 Skill 目录规则

一个目录被视为有效的 skill 目录，如果它包含：
- `SKILL.md` 文件（标准 skill）
- 或 `skill.md` 文件（变体）
- 或 `.claude` 子目录

## 使用示例

```bash
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

# 列出已安装的 skills
skill-manager list

# 卸载 skill
skill-manager remove pdf-tool

# 更新所有 skills
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
