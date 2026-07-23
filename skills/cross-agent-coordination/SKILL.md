---
name: cross-agent-coordination
description: 跨平台 Agent 任务协调枢纽。本技能应在多个不同平台的 Agent 需要围绕项目任务源分配任务、标记归属、能力路由和交接上下文时使用。不要用于单一平台内的本地并行执行，或 Git 分支、提交、PR、merge 安全规则。
license: MIT
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: 1.0.0
---

# Cross-Agent Coordination

跨平台 Agent 任务协调枢纽。核心职责是让不同平台的 Agent 围绕项目配置或项目上下文指定的任务源分配任务、保留交接上下文，并在提交/PR 中标记 Agent 归属。

## 1. 何时使用

**使用本 Skill：**
- 多个不同平台的 Agent 需要在同一仓库协作
- 需要追溯某个提交/PR 是哪个 Agent 完成的
- 需要把任务派给 Manus、AnyGen、Coze 等外部 Agent
- 需要跨会话保留任务上下文、依赖和交接记录

**不使用本 Skill：**
- 单一平台内的并行执行：使用 `multi-agent-orchestration`
- 纯 Git 安全规范：使用 `git-workflow`

## 2. 核心规则

1. **任务源由项目定义**：常规任务状态以项目配置或项目上下文指定的任务源为准；任务文件夹只是材料包、产物包和交接包。
2. **归属优先**：提交前必须设置 Git Author；PR 正文应包含 Agent Attribution。
3. **任务按分配执行**：默认只处理项目任务源中负责人/委托对象匹配当前 Agent 的任务。
4. **项目可配置**：任务类型、模板、状态映射、认领策略由项目级配置决定，不改 Skill 源码。
5. **交接可追溯**：Issue、任务 README 或 `.agent-context/handoff.md` 必须记录目标、来源、决策、阻塞和下一步。

## 3. 项目配置

项目根目录使用本地忽略配置：

```bash
cp .claude/skills/cross-agent-coordination/config/collab.yaml.example config/collab.yaml
```

关键字段（示例；具体任务源由项目决定）：

```yaml
project:
  mode: task_folders          # task_folders | single_repo
  default_agent: codex
  issue_file: project-tasks.md
  task_context_mode: issues_primary
  status_map:
    "⬜": pending_confirmation
    "✅": ready
    "🟢": created
  available_statuses: [ready, created, todo]
  dependency_done_statuses: [ready, created, done, resolved, closed]
  claim_policy: assigned_only # assigned_only | claim_pool
  task_types_file: config/task-types.yaml
  template_dir: templates/tasks

agents:
  codex:
    name: "Codex"
    email: "codex@agents.local"
    github_user: "codex-bot"
    token_env: "CODEX_GITHUB_TOKEN"
```

配置路径固定为 `config/collab.yaml`。旧的 `github-monorepo-collab` 和 `config/monorepo.yaml` 不再读取。

## 4. 任务模型

项目配置中的 `project.issue_file` 或项目上下文指定的任务文件，是脚本读取任务的默认入口。脚本可解析如下格式：

```markdown
### ✅ Issue #9: 触发 Manus 调研任务

- **类型**: 研究（委托 Manus）
- **依赖**: Issue #7 确定后
- **目标**: 为 ch03 法律 AI 基础设施章节提供调研支撑

#### 验收标准
- [ ] 形成产品对比表
```

解析字段包括 Issue 编号、标题、状态标记、类型、负责人/委托 Agent、依赖、目标、素材来源和验收标准。状态由 `project.status_map` 映射；`find_task.py --available` 只返回状态可执行、依赖满足、负责人匹配的 Issue。

任务文件夹模式仍可使用 `{YYMMDDNNN}-{type}-{title}/README.md`，但它是重任务材料包/产物包/交接包，不覆盖主任务源状态：

```yaml
---
id: 260517001
slug: 260517001-研究-法律AI产品生态调查
title: 法律AI产品生态调查
type: 研究
status: todo
assignee: manus
dependencies: []
artifact_paths: []
progress: 0
created: 2026-05-17
updated: 2026-05-17
---
```

`assignee` 是材料包负责人字段；`agent` 只作为旧任务兼容读取，不再作为新任务必填字段。任务文件夹依赖仍按 `done` / `resolved` / `closed` 判断；Issue 依赖按 `dependency_done_statuses` 判断。

项目可在 `config/task-types.yaml` 扩展任务类型：

```yaml
task_types:
  整合:
    aliases: [integration]
    description: 多来源材料融合
    output_hint: 统一稿/整合报告
  审阅:
    aliases: [review]
    description: 质量审查/事实核查
    output_hint: 审阅意见/修订稿
```

项目可在 `templates/tasks/{type}.md` 或 `templates/tasks/default.md` 定义任务 README 模板。模板变量使用 `{{ id }}`、`{{ slug }}`、`{{ title }}`、`{{ type }}`、`{{ assignee }}`、`{{ created }}`、`{{ updated }}`。

## 5. 依赖

### Python 包

| 包名 | 用途 | 安装命令 |
|------|------|----------|
| `PyYAML` | 读取 `collab.yaml`、`task-types.yaml` 和 frontmatter | `python3 -m pip install -r scripts/requirements.txt` |

安装依赖（仅在脚本提示缺失时）：

```bash
python3 -m pip install -r scripts/requirements.txt
```

## 6. 常用脚本

| 脚本 | 用途 |
|------|------|
| `scripts/task_scaffold.py` | 创建任务文件夹，分配稳定 Task ID，按项目模板写 README |
| `scripts/find_task.py` | 按主题搜索项目任务源和任务文件夹，支持 `--available` 依赖/分配过滤 |
| `scripts/gh_git.py` | 带 Agent 归属的 clone/branch/commit/push/PR/merge |
| `scripts/email_trigger.py` | 为外部 Agent 生成标准邮件触发草稿 |
| `scripts/audit_repo.py` | 审计任务 metadata 与项目类型注册表是否一致 |

示例：

```bash
python3 scripts/task_scaffold.py create --root . --type 研究 --topic "法律AI产品生态调查" --assignee manus
python3 scripts/task_scaffold.py create --root . --type 写作 --topic "ch01 Agent发展阶段" --field chapter=ch01 --field target_words=15000
python3 scripts/find_task.py . --available --agent manus
python3 scripts/gh_git.py commit --dest . --agent manus --message "docs: update handoff"
python3 scripts/gh_git.py pr --dest . --agent manus --title "docs: Manus handoff update"
python3 scripts/email_trigger.py . --agent manus --issue 9
```

## 7. Agent 归属

每次提交涉及两层身份：

| 层级 | 控制方式 | 证明什么 |
|------|---------|---------|
| Git Author | `git config user.name` / `user.email` | 谁写了提交内容 |
| GitHub Actor / PR Opener | 使用的 Token 或 GitHub App | 哪个账号执行平台操作 |

脚本会设置 Git Author。PR Opener 由 token 决定；如果要让 PR actor 区分 Agent，需要给该 Agent 配置独立 token 环境变量。详细规则见 `references/agent-identity.md`。

## 8. 工作流

### Issue / Task 主状态模式

1. 读取 `config/collab.yaml`、`config/task-types.yaml`、项目模板和项目上下文。
2. 用 `find_task.py --available --agent <agent-id>` 从项目任务源领取可执行任务。
3. 只有任务需要较多材料、产物或交接记录时，才用 `task_scaffold.py create` 创建或复用任务文件夹。
4. 在 `agent/{agent-id}/{slug}` 分支上工作。
5. 提交时用 `gh_git.py commit` 标记 Git Author。
6. 完成后更新项目任务源状态；若有任务文件夹，同时更新 README 交接记录，并开 PR。

若某个 Issue / Task 不通过 PR，而是在当前分支或 `main` 上直接解决，提交信息仍必须保留任务来源。GitHub Issue、项目本地任务条目或任务文件夹 ID 的具体提交格式、引用格式和关闭规则遵循 `git-workflow`；本 Skill 只负责确认任务来源和交接上下文。

### 单 Repo 模式

不创建任务文件夹；仍需用 Agent 分支、Git Author、PR Attribution 和 `.agent-context/handoff.md` 保留交接上下文。

### 邮箱触发

对支持邮箱入口的外部 Agent，使用 `email_trigger.py` 生成草稿。邮件可通过 `--issue` 绑定项目任务源中的任务，并包含目标、验收标准、来源材料、依赖、查重命令、分支和 PR 要求。默认不发送真实邮件。

### 外部 Agent Adapter

外部 Agent（如 Manus、AnyGen、Coze）只作为执行通道或能力 adapter，不拥有任务状态。项目应在 `config/collab.yaml` 的 `agents.<id>` 中声明该 Agent 的能力和触发方式：

```yaml
agents:
  manus:
    name: "Manus Bot"
    email: "manus@agents.local"
    github_user: "manus-bot"
    token_env: "MANUS_GITHUB_TOKEN"
    trigger_email: "manus-agent-inbox@example.com"
    capabilities: [web_research, citation_collection]
    trigger_modes: [email_draft]
    handoff_format: pull_request
```

Adapter 选择规则：
- 复杂网络搜索、资料收集、网页操作：优先分配给具备 `web_research` / `browser_ops` 能力的 Agent。
- 图片生成、视觉资产：优先分配给具备 `image_generation` 能力的 Agent。
- 代码修改、本地测试、worktree 执行：交给本地 Agent，并由 `multi-agent-orchestration` 管 session。
- 任何 adapter 都必须绑定项目任务源中的任务或先查重；结果通过分支、PR、handoff note 回到仓库。

## 9. 参考文档

- `references/naming.md`：任务命名、frontmatter、归档规则
- `references/agent-guide.md`：Agent 启动、交接和完成检查清单
- `references/agent-identity.md`：Git Author 与 GitHub Actor 归属
- `references/email-trigger.md`：邮箱触发协议
- `references/legacy-migration.md`：旧任务迁移提示

## 10. Related Skills

| 维度 | cross-agent-coordination | multi-agent-orchestration | git-workflow |
|------|-------------------|----------------------|--------------|
| 定位 | 任务协调层 | 本地执行层 | Git 安全层 |
| 主责 | 项目任务源状态、Agent 归属、交接上下文 | Agent Teams / tmux 会话、worktree、PM 巡检 | 分支、PR、diff、review、merge 安全规则 |
| 不负责 | 本地会话管理、Git 合并策略 | 任务主状态、外部 Agent 邮件触发 | 任务分配、本地 Agent 调度 |

协作模式：先由 `cross-agent-coordination` 从项目任务源确定任务；同平台需要并行执行时使用 `multi-agent-orchestration`；涉及分支、PR、review 或 merge 时遵循 `git-workflow`。
