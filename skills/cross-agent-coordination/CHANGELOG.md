# 变更记录

## [1.0.0] - 2026-06-01

### 文档完善
- 将版本定为正式发布候选版本，保留任务协调、Agent 归属、能力路由和交接上下文等核心边界。
- 收口发布包参考文档，只保留任务命名、Agent 指南、身份归属、邮件触发、旧任务迁移和任务类型注册表。

### 移除
- 移除弱相关的 Git LFS 策略和 Profile 模板参考文档，避免把 Git 存储策略或项目偏好模板混入任务协调 Skill。
- 清理旧 monorepo 模板空目录、书籍写作项目 adapter 样例、macOS 缓存文件和脚本冲突副本。
- 移除通用 project-starter 目录，避免公开发布包包含会被仓库忽略规则挡住的嵌套 config/templates 资源。

## [0.7.0] - 2026-05-20

### 重构
- 重命名 Skill：`cross-agent-collab` → `cross-agent-coordination`，标题改为 Cross-Agent Coordination，以突出“跨平台任务协调”而非泛化协作。
- 同步更新脚本提示、邮件主题前缀、测试文件名和相关参考文档中的 Skill 名称。
- 保留 `config/collab.yaml` 文件名，避免破坏既有项目配置。

## [0.6.4] - 2026-05-20

### 改进
- 同步相关 Skill 引用：`multi-agent-workflow` 定稿为 `multi-agent-orchestration` 后，更新边界说明、Related Skills 和 Agent guide。

## [0.6.3] - 2026-05-20

### 改进
- 同步相关 Skill 引用：`parallel-agent-workflow` 更名为 `multi-agent-workflow` 后，更新边界说明、Related Skills 和 Agent guide。

## [0.6.2] - 2026-05-19

### 改进
- 将任务源表述改为“项目配置或项目上下文指定的任务源”，不再在 Skill 中把固定文件路径写成唯一标准。
- 保留 `project.issue_file` 作为可配置字段示例，具体路径由项目决定。

## [0.6.0] - 2026-05-17

### 新增
- **外部 Agent Adapter 声明**：`config/collab.yaml.example` 增加 `capabilities`、`trigger_modes`、`handoff_format` 示例，用于声明 Manus、AnyGen 等外部 Agent 的能力边界。
- **Adapter 能力路由**：文档补充 `web_research`、`citation_collection`、`image_generation`、`browser_ops` 等能力如何映射到外部 Agent。

### 改进
- 明确外部 Agent 只是执行通道，不拥有任务状态；所有常规任务仍以 `docs/TASKS.md` 为主状态源。
- 邮件触发协议要求外部 Agent 通过 branch、PR 或 durable handoff note 返回结果，不接受无仓库回写的 chat-only 结果作为默认完成。

## [0.5.0] - 2026-05-17

### 新增
- **TASKS.md 主状态源**：新增 `docs/TASKS.md` 解析能力，支持 Issue 编号、标题、状态标记、类型、负责人/Lead Author、依赖、目标、素材来源和验收标准。
- **Task 可执行过滤**：`find_task.py --available` 默认基于 `docs/TASKS.md` 返回状态可执行、依赖满足、负责人匹配的任务。
- **Task 邮件触发**：`email_trigger.py --issue N` 可从 `docs/TASKS.md` 注入目标、验收标准、依赖、调研任务和交接要求。
- **书籍写作 adapter 状态映射**：示例配置将 `⬜`、`✅`、`🟢` 映射为 `pending_confirmation`、`ready`、`created`，默认只有 `ready` / `created` / `todo` 可执行。

### 改进
- 任务文件夹明确降级为材料包、产物包和交接包，不再作为常规任务状态源。
- 对未显式声明类型的章节类 Issue 增加保守推断，支持书籍项目中 `chXX` 写作任务的现有格式。
- 邮件草稿不再引用已删除 dashboard 脚本，交接要求统一要求更新 `docs/TASKS.md`。
- 相关文档补充三层边界：`cross-agent-coordination` 管任务状态，`multi-agent-orchestration` 管本地会话，`git-workflow` 管 Git 安全。

## [0.4.0] - 2026-05-17

### 新增
- **项目适配层**：新增 `project.mode`、`task_types_file`、`template_dir`、`claim_policy`、`default_agent` 配置，支持不同项目通过配置和模板适配。
- **动态任务类型**：脚本读取项目级 `config/task-types.yaml` 并回退到 Skill 默认注册表，支持 `整合`、`审阅` 等泛化任务类型。
- **任务模板**：新增 `templates/tasks/default.md`，支持项目级 `templates/tasks/{type}.md` 和 `--field key=value` 写入自定义 frontmatter。
- **依赖过滤**：`find_task.py --available` 支持按 `dependencies`、`assignee` 和 `claim_policy` 过滤可执行任务。
- **回归测试**：新增 `scripts/test_cross_agent_coordination.py`，覆盖配置读取、任务类型、模板字段、依赖过滤和邮件触发。

### 改进
- `task_scaffold.py`、`find_task.py`、`email_trigger.py`、`gh_git.py`、`audit_repo.py` 统一使用共享 helper，避免多处硬编码配置和任务类型。
- `email_trigger.py` 自动注入任务 README 中的目标、验收标准、来源材料和交接要求，并统一使用 `python3` 命令示例。
- `gh_git.py` 在无 remote 场景下给出清晰错误，保留本地 Git author 归属能力。
- 新增 `assets/project-starter/` 通用 starter 和书籍写作适配样例。

### 移除
- 移除旧 dashboard workflow 与个人化模板残留。
- 脚本不再读取旧 `github-monorepo-collab` 或 `config/monorepo.yaml` 路径。

### 安全
- 在私有技能仓库 `.gitignore` 中忽略 `**/config/collab.yaml`，避免本地 Agent token 配置误提交。

## [0.3.0] - 2026-05-16

### 重构
- **重命名**：`github-monorepo-collab` → `cross-agent-collab`，去除 GitHub + Monorepo 绑定
- **重命名**：`config/monorepo.yaml.example` → `config/collab.yaml.example`
- **重命名**：`scripts/monorepo_scaffold.py` → `scripts/task_scaffold.py`
- **重命名**：`scripts/audit_monorepo.py` → `scripts/audit_repo.py`

### 新增
- **Agent 归属提升为第一优先级**：明确提交时必须标记 Agent 身份的规则
- **任务来源与分配机制**：支持 `docs/TASKS.md`（`assignee` 字段）和 GitHub Issues 双通道
- **单 Repo 模式**：不需要任务文件夹体系，通过 Git author + branch prefix + PR body 实现归属
- **Related Skills 章节**：明确与 `multi-agent-orchestration`、`git-workflow`、`git-batch-commit` 的边界
- **AnyGen** 正式列入支持的 Agent 平台

### 移除
- 删除 `scripts/generate_dashboard.py`（已过时）
- 删除 `scripts/sync_to_obsidian.py`（已过时）
- 移除 SKILL.md 中 Dashboard 和 Obsidian 相关描述

### 改进
- 配置文件注释去除 `monorepo` 字眼，改为通用描述
- `references/agent-identity.md` 更新脚本路径引用

## [0.2.0] - 2026-04-23

### 新增
- 增加 `scripts/audit_monorepo.py`，用于审计云端仓库中的历史 metadata 残留与不一致。
- 增加 `scripts/find_task.py`，用于在创建或上传前检索相似既有任务。
- 增加 `references/legacy-migration.md`，说明旧版本任务的低风险迁移顺序。
- 增加 `references/agent-identity.md`，说明 Git author 与 GitHub actor 的区别及配置方式。
- 增加 `scripts/email_trigger.py` 和 `references/email-trigger.md`，用于生成外部 Agent 的邮件触发草稿。
- 在配置模板中补充 Manus、AnyGen、OpenClaw、Codex、Claude Code、Coze 等 Agent 身份字段。

### 修复
- 修复 `gh_git.py` 子命令参数注册错误，恢复 CLI 可用性。
- 修复任务 ID 生成逻辑，按 `YYMMDDNNN` 扫描根目录和 `archive/` 中已有任务。
- `monorepo_scaffold.py create` 默认执行相似主题查重，命中既有任务时阻止新建，避免重复研究同一内容。
- 删除 `SKILL.md` 中不存在的 `scripts/gh_pr.py` 引用。

### 安全
- 将 `config/monorepo.yaml` 从 Git 跟踪中移除，并加入私有仓库 `.gitignore`，允许本地保留私有 token。
- 脚本优先通过 `GITHUB_TOKEN` 读取 GitHub 凭据，其次读取本地忽略配置，不再把 token 写入 git remote。

### 改进
- 读取云端 `Monorepo-Collab` 现状后，将任务模型统一为 `{YYMMDDNNN}-{中文分类}-{title}`，脚本兼容英文别名输入。
- dashboard 生成时优先使用任务文件夹名，避免旧 frontmatter slug 覆盖真实路径。
- `gh_git.py` 与 `monorepo_scaffold.py` 支持按 Agent 设置 repository-local Git author，并优先使用 Agent 专属 token 环境变量。
- `gh_git.py` 新增 `pr` 子命令，创建 PR 时自动写入 Agent ID、Git author 和预期 GitHub actor。
- Agent 配置新增 `trigger_email`、`reply_to`、`from_alias` 字段，可为支持邮箱入口的外部 Agent 生成标准触发邮件草稿。
- 精简 `SKILL.md`，把细节规则下沉到 `references/`。
- 增加 `scripts/requirements.txt` 和 PyYAML 缺失时的清晰安装提示。

### 待办事项
- 如泄露提交已推送到远端，评估是否需要撤销 token 或清理 Git 历史。
- 为脚本补充自动化测试。

## [0.1.0] - 2026-04-23

### 新增
- 初始版本：提供多 Agent GitHub monorepo 协作流程、任务脚手架、dashboard 生成和 Obsidian 同步脚本。
