---
name: clawhub-sync
description: 将本地开发的 Skills 批量同步到 ClawHub 平台。支持智能 .gitignore 过滤、白名单控制、增量同步。本技能应在用户需要将本地 skills 发布到 ClawHub、批量同步技能、检查发布状态时使用。
license: MIT
---

# ClawHub 同步工具

将本地开发的 Skills 批量同步到 ClawHub 平台。支持读取 `.gitignore` 智能忽略敏感文件和临时文件。

## ⚠️ ClawHub 许可证说明

> **ClawHub 平台强制使用 MIT-0 许可证**（无需署名，允许商业使用）。
> - MIT 许可证的 skill 可以同步
> - CC-BY-NC-SA-4.0 等限制性许可证与 MIT-0 冲突，不应同步
>
> 详见 [ClawHub Skill Format](https://github.com/openclaw/clawhub/blob/main/docs/skill-format.md)

---

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

> 注意：`--all` 会受 `skills/clawhub-sync/config/sync-allowlist.yaml` 约束。如果存在白名单文件，只同步其中列出的 skill。

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

**配置文件：** `skills/clawhub-sync/config/sync-allowlist.yaml`（skill 自包含）

**优先级：白名单 > 默认忽略规则**

- 如果 `skills/clawhub-sync/config/sync-allowlist.yaml` **存在**：只同步文件中列出的 skill
- 如果 `skills/clawhub-sync/config/sync-allowlist.yaml` **不存在**：使用默认忽略规则（忽略 test/、private-skills/、node_modules/）

**配置格式：**

```yaml
# legal-qa-extractor:    # 带 # 表示不发布
legal-qa-extractor:       # 无 # 表示发布
litigation-analysis:
```

**配置文件：** `skills/clawhub-sync/sync-allowlist.yaml`（skill 自包含）

### 文件过滤规则

发布时会自动应用 .gitignore 过滤规则，确保敏感文件和临时文件不会被上传。

**双重过滤机制**：

1. **项目根目录 .gitignore** - 自动检测 Git 仓库根目录的 `.gitignore`
2. **技能内部 .gitignore** - 如果技能目录有自己的 `.gitignore`，会额外应用

**默认排除**（始终生效）：

- `.git/` - Git 目录
- `node_modules/` - Node.js 依赖
- `__pycache__/` - Python 缓存
- `.DS_Store` - macOS 系统文件

### 同步流程

每次同步前，会自动：

1. **创建临时目录** - 在 `/tmp/clawhub-publish-<skill-name>` 创建临时目录
2. **复制过滤后的文件** - 使用 rsync 遵循 .gitignore 规则复制文件
3. **发布到 ClawHub** - 从临时目录执行发布命令
4. **清理临时目录** - 发布完成后自动清理

### 手动准备发布目录

如需手动检查将要发布的文件：

```bash
# 准备发布目录（不实际发布）
bash skills/clawhub-sync/scripts/prepare-publish.sh skills/trademark-assistant

# 检查临时目录内容
ls -la /tmp/clawhub-publish-trademark-assistant/
```

## 安全最佳实践

### 发布前检查清单

- [ ] 确认 `.gitignore` 包含所有敏感文件模式
- [ ] 使用 `prepare-publish.sh` 检查将要发布的文件
- [ ] 不要在技能中包含 API keys、密码等
- [ ] 使用 `.env.example` 代替 `.env` 文件

### 常见敏感文件

- `.env` - 环境变量（使用 `.env.example` 作为模板）
- `config.yaml` - 配置文件（使用 `config.example.yaml` 作为模板）
- `*.db`, `*.sqlite` - 数据库文件
- `logs/` - 日志目录
- `downloads/`, `output/` - 输出目录

### 修复已发布的技能

如果发现已发布的技能包含敏感信息：

1. **立即更新** - 从技能目录中删除敏感文件
2. **更新 .gitignore** - 确保未来不会再次包含
3. **重新发布** - 使用 `clawnet publish` 更新 ClawHub 上的技能
4. **联系 ClawHub 支持** - 如果需要删除旧版本

**重要提醒**：

- **ClawHub 是公开平台**：发布的技能任何人都可以访问
- **不要包含客户信息**：案例文件、沟通记录等应排除
- **不要包含凭证**：API keys、tokens 等应使用环境变量

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

- 必需：本地开发的 skill 目录
- 可选：指定技能名称列表、白名单配置

### 输出

- 同步结果报告（成功/失败列表）
- 错误信息（如有）

## 同步记录

每次同步后，会更新 `config/sync-records.yaml` 记录文件，便于溯源和增量同步。

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
