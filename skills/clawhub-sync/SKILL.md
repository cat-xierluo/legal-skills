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

> 注意：`--all` 会受 `skills/clawhub-sync/sync-allowlist.yaml` 约束。如果存在白名单文件，只同步其中列出的 skill。

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

### 同步范围控制（白名单机制）

**配置文件：** `skills/clawhub-sync/sync-allowlist.yaml`（自包含在 skill 内部）

**优先级：白名单 > 默认忽略规则**

- 如果 `skills/clawhub-sync/sync-allowlist.yaml` **存在**：只同步文件中列出的 skill
- 如果 `skills/clawhub-sync/sync-allowlist.yaml` **不存在**：使用默认忽略规则（忽略 test/、private-skills/、node_modules/）

**配置格式：**

```yaml
# legal-qa-extractor:    # 带 # 表示不发布
legal-qa-extractor:       # 无 # 表示发布
litigation-analysis:
```

**配置文件：** `skills/clawhub-sync/sync-allowlist.yaml`（skill 自包含）

### 默认忽略规则

（当白名单文件不存在时生效）

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

## 同步记录

每次同步后，会更新 `sync-records.yaml` 记录文件，便于溯源和增量同步。

### 记录字段

| 字段 | 说明 |
|------|------|
| `version` | 同步时的版本号 |
| `last_sync` | 最后同步时间 (ISO 8601) |
| `git_hash` | 同步时的 commit hash |
| `status` | `synced` / `pending` / `failed` |
| `changelog_summary` | 变更摘要 |
| `url` | ClawHub 发布地址 |
| `publish_id` | ClawHub 内部 ID |

### 记录示例

```yaml
trademark-assistant:
  version: "1.5.0"
  last_sync: "2026-03-24T16:42:00+08:00"
  git_hash: "f5f0726"
  status: synced
  changelog_summary: "新增商标说明撰写、图形商标分析、商品清单生成"
  url: "https://clawhub.ai/skills/trademark-assistant"
  publish_id: "k97fmhvcnrh1tn2msya98nbxxd83gspe"
```

### 用途

1. **增量同步**：只同步 `status: pending` 或版本更新的 skill
2. **溯源**：通过 `git_hash` 追溯发布时的代码状态
3. **快速访问**：通过 `url` 直接访问 ClawHub 上的 skill 页面
