# 变更日志

## [1.4.1] - 2026-05-19

### 改进

- 明确 `git-batch-commit` 是提交快捷按钮，只负责已暂存变更的拆分和提交信息生成。
- 新增轻量 Issue/Task 引用：`--issue N` 在标题追加 `(#N)` 并写入 `Refs #N`，`--local-ref` 写入本地任务引用。
- 明确本 Skill 不生成 `Closes #N`；Issue 关闭、PR 合并、push 和分支安全规则仍由 `git-workflow` 管理。

## [1.4.0] - 2026-05-15

### 变更

- 将 `references/issue-pr-format.md`（Issue 与 PR 命名规范）迁移到 `git-workflow` skill，该规范与 Git 全流程工作流更相关
- git-batch-commit 聚焦于"提交"本职，不再管理 Issue/PR 命名

## [1.3.0] - 2026-05-14

### 新增

- 工作流新增 Subtree 推送检查（第6步）：当 `skills/subtree-publish/config/subtree-skills.json` 存在时自动执行

## [1.2.5] - 2026-04-10

### 新增

- 新增 `references/issue-pr-format.md`：定义 Issue 与 PR 命名规范
- Issue 类型前缀：`feat`、`bug`、`enhancement`、`docs`、`question`
- Issue 状态标记：`[done]`（自己完成）、`[resolved]`/`[answered]`（外部）
- PR 格式与 Commit 保持一致：`类型(模块): 描述`
- AI 读取规则：根据状态标记区分已处理和待处理任务

## [1.2.4] - 2026-04-06

### 新增

- ClawHub 同步检测新增「检测 B：新增 MIT 技能首次同步」：当提交新增 MIT 技能时，提示用户是否加入白名单并同步
- ClawHub 同步检测新增「检测 C：白名单新增但未同步」：检测白名单中有条目但同步记录缺失的情况
- 新增发布前敏感文件检查：确保临时发布目录不含 .env、密钥等敏感文件

## [1.2.1] - 2026-03-26

### 修复

- ClawHub 同步工作流添加 `--slug` 和 `--name` 参数
- 避免因临时目录名导致的 skill 标识符和显示名称错误

## [1.2.0] - 2026-03-26

### 新增

- ✨ SKILL.md 新增「ClawHub 同步工作流」章节
- ✨ 支持提交后自动检测并同步版本更新的 skills 到 ClawHub
- ✨ 触发条件检测：clawhub-sync 存在、涉及 skills 目录、版本号更新、在白名单中

### 变更

- 📝 更新执行步骤，使用 prepare-publish.sh + clawhub sync 组合方式
- 📝 添加示例场景表格，清晰说明各种情况的处理方式

## [1.1.0] - 2026-02-07

### 改进

- 📝 提交格式规范：使用小写英文前缀（docs:, feat:, fix: 等）加英文冒号，支持 GitHub 彩色标签显示
- 📝 描述保持中文：提交信息描述部分使用中文，保持内容一致性
- 📝 更新文档：SKILL.md 和 references/commit-types.md 反映新的提交格式

### 技术优化

- 更新 `scripts/generate_commit_message.py` - 从中文前缀改为小写英文前缀
- 更新 `CATEGORY_TO_TYPE` 映射 - 使用小写英文类型名称
- 提交信息格式从 `类型：描述` 改为 `type: 描述`

### 文档更新

- 更新 SKILL.md - 反映新的提交格式规范
- 更新 references/commit-types.md - 添加 GitHub 彩色标签支持说明
- 新增 CHANGELOG.md - 版本变更记录

---

## [1.0.0] - 2025-12-15

### 新增

- ✨ 初始版本发布：智能 Git 批量提交工具
- ✨ 自动分类功能：按文件类型和内容自动分类修改
- ✨ 交互式提交：支持确认预览后再创建提交
- ✨ 命令行工具：categorize_changes.py 和 generate_commit_message.py
- ✨ 提交分类支持：deps, docs, license, config, test, chore, feat, fix, refactor, style

### 核心功能

- 文件模式匹配：基于路径和扩展名进行分类
- Diff 内容分析：对源代码进行深度分析，区分功能、修复、重构和风格变更
- 关键字检测：识别 fix/bug/error 和 add/new/implement 等关键字
- 行变更比率：比较添加与删除行数推断变更意图
