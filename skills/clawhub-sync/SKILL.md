---
name: clawhub-sync
description: 批量同步 Claude Code Skills 到 ClawHub 平台。本技能应在用户需要将 skills 发布到 ClawHub、批量同步技能、检查发布状态时使用。
license: MIT
author: 杨卫薪律师（微信ywxlaw）
---

# ClawHub 同步工具

批量同步 skills 目录中的技能到 ClawHub 平台。

## 前置条件

SKILL.md frontmatter 需包含必要字段：

```yaml
---
name: skill-name
description: 技能描述
version: "1.0.0"  # 推荐但不强制
homepage: https://github.com/cat-xierluo/legal-skills  # 自动设置
---
```

## 使用方式

### 1. 登录 ClawHub（首次使用）

```bash
clawhub login
```

### 2. 验证发布内容

执行 dry-run 检查配置是否正确，不实际发布：

```bash
clawhub sync --dry-run
```

### 3. 同步技能

**同步单个技能**：

```bash
clawhub sync skills/<skill-name>
```

**同步所有技能**：

```bash
clawhub sync --all
```

**交互式选择同步**：

用户可以指定要同步的技能列表，我会逐个执行同步命令。

## 同步策略

### 版本号处理

- 从技能的 `CHANGELOG.md` 第一行提取版本号
- 格式要求：`## [x.y.z] - YYYY-MM-DD`
- 自动处理 `v` 前缀（`v1.0.0` → `1.0.0`）

### 自动字段

| 字段      | 处理方式                                     |
| --------- | -------------------------------------------- |
| `homepage` | 自动设置为 GitHub 仓库地址                   |
| `version`  | 从 CHANGELOG.md 提取（如 SKILL.md 中未指定） |

### 忽略规则

以下目录默认不同步：

- `test/` - 测试中的技能
- `private-skills/` - 私有技能
- `skills/*/node_modules/` - 依赖目录

## 常见问题

### 版本号未更新？

检查 CHANGELOG.md 格式：

```markdown
## [1.0.0] - 2026-03-21

### 新增
- 新功能描述
```

### 同步失败？

1. 运行 `clawhub sync --dry-run` 检查配置
2. 确认 SKILL.md frontmatter 格式正确
3. 检查登录状态：`clawhub whoami`

## 输入/输出

### 输入

- 必需：`skills/` 目录下的技能
- 可选：指定技能名称列表

### 输出

- 同步结果报告（成功/失败列表）
- 错误信息（如有）
