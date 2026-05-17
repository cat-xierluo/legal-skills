# 变更日志

## [1.0.0] - 2026-05-17

### 新增

- 正式迁入 `legal-skills/skills/git-workflow/`，作为公开技能集合中的 Git 全流程工作流 Skill。
- 补齐正式发布元数据：`homepage`、MIT 许可证文件、README 技能列表和 Marketplace 条目。

### 改进

- 按正式发布版本规则将 Skill 版本设为 `1.0.0`，保留私有开发阶段 `0.3.0` 及以下历史记录。

## [0.3.0] - 2026-05-17

### 新增

- PR 合并前检查命令序列：读取 PR 状态、draft 状态、mergeable、reviewDecision、diff 文件列表和 checks。
- Cherry-pick 安全流程：工作区干净、先看 commit 范围、默认 `-x` 保留来源、回补后检查范围。
- Monorepo 场景下的目录级提取规则，避免 cherry-pick 整个 commit 带入无关文件。
- Issue / PR 命名参考增加边界说明：GitHub Issue 不作为项目常规任务状态源，项目任务仍以 `docs/ISSUES.md` 为准。

### 改进

- `references/gh-cli-quickref.md` 增加 fail-closed merge gate 速查。
- `TASKS.md` 同步标记 PR 合并检查和 Cherry-pick 规则已完成。

## [0.2.2] - 2026-05-17

### 新增

- 新增 `TASKS.md`，补齐 `git-workflow` 的维护任务上下文。

### 改进

- `SKILL.md` 参考资源增加 `TASKS.md`，方便后续代理查看当前关注和后续优化方向。

## [0.2.1] - 2026-05-17

### 改进

- 将提交规范内置到 `SKILL.md`，不再在主流程中引用其他 Skill 的提交规范文档。
- 保持职责边界：`git-workflow` 拥有 Git 流程中需要用到的提交格式要求，批量提交自动化仍由专门的提交工具负责。

## [0.2.0] - 2026-05-17

### 新增

- PR review / merge 默认 fail-closed：diff 不可读、CI/checks 未知、review 结论不明确时不得自动合并。
- 明确 `git-workflow` 只拥有 Git 安全规则；任务状态归 `cross-agent-collab`，本地 Agent 会话归 `parallel-agent-workflow`。

## [0.1.0] - 2026-05-15

### 新增

- 创建 git-workflow skill，覆盖 Git 全流程操作
- Git 安全协议：禁止操作清单和安全原则
- 分支管理：命名规范、创建/清理流程、Worktree 使用
- Monorepo 安全合并：目录级 checkout 规范（从 AGENTS.md v1.7.4 迁移）
- PR 工作流：创建/审查/合并（基于 gh CLI）
- 合并冲突解决：检测、解决原则、lock 文件处理
- Issue 与 PR 命名规范（从 git-batch-commit v1.2.5 迁移）
- 常用 Git 操作速查：撤销、暂存、cherry-pick、tag
- `references/gh-cli-quickref.md`：gh CLI 命令速查
- `references/issue-pr-format.md`：Issue 与 PR 命名详细规范

### 参考

- 整合自 github/awesome-copilot@git-commit（30.8K 安装）
- 整合自 github/awesome-copilot@gh-cli（21.3K 安装）
- 整合自 cursor/plugins@fix-merge-conflicts
- 整合自 cursor/plugins@new-branch-and-pr
