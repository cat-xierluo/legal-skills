# 分支、Issue 与 PR 命名规范

本规范统一维护新分支名称、GitHub Issue / PR 标题、关闭标记和提交格式；PR 执行沿 [PR 流程](pr-workflow.md)，生命周期与资源删除沿 [清理合同](branch-lifecycle-and-cleanup.md)。

边界说明：项目任务状态不由本文档维护。常规任务领取、依赖和状态判断以项目自己的任务源为准；若项目配置协调技能，仍以其明确的任务源为准。GitHub Issue 只作为远程协作入口或外部问题追踪入口。

## 分支名称：先看角色，再看 Skill 和目标

新命名区分“单项任务”和“里程碑迭代线”。分支名是人可读的用途提示；实际生命周期、owner、PR base、完整 OID 与清理权限仍以任务合同和当前现场为准，不因 `fix/` 就判可删，也不因 `milestone/` 就认定已注册长期保护。

| 角色 | 新分支格式 | 示例 | 通常的 PR base |
|---|---|---|---|
| 独立短任务 | `<type>/<skill>/<topic>` | `fix/legal-ai-wiki/module-index` | 声明的默认主干 |
| 有限里程碑迭代线 | `milestone/<skill>/<goal>` | `milestone/legal-ai-wiki/workshop-v2` | 声明的默认主干 |
| 里程碑内的短子任务 | `<type>/<skill>/<goal>--<topic>` | `feat/legal-ai-wiki/workshop-v2--student-pack` | 完整父分支 `milestone/legal-ai-wiki/workshop-v2` |

短任务的 type 使用 `feat`、`fix`、`docs`、`test`、`refactor`、`chore`，必要时使用 `style`、`config`、`license`、`research`。`feat` 表示新增功能，不表示长期；大版本整体使用 `milestone/`，其 PR/commit 仍按真实改动使用 feat/refactor 等类型，不创建 `milestone:` commit 类型。

### 字段和长度

- skill 使用仓库正式 Skill slug；跨 Skill 的具名套件使用其明确的套件 slug，仓库级事项用 `repo`。不放客户名称、案件号、机器用户、Agent/Session ID。
- topic/goal 使用简短英文小写、数字和连字符；`--` 专门分隔父目标与子任务，字段自身不含连续连字符。一个名称只表达一个交付目标，避免 `misc`、`latest`、`temp`、`dev`、`fix2` 等无法解释范围的词。
- 已明确的目标版本可写入 goal，如 `workshop-v2`；未确定发布版本时用能力名，不能为命名而虚构版本或提前改稳定版版本号。日期只在确有重名时作区分，不表示过期/删除期限。
- 不用 `short/long`、运行平台或执行主体代替语义；也不写 `draft/ready/done/merged` 等会变化的状态。阶段放任务卡，PR 用真实 Draft/Ready 状态。
- 新建前运行 `git check-ref-format --branch '<完整分支名>'`，并查本地/远端的同名及 ref 路径前缀冲突（如已存在 `feat/foo`，不能再建 `feat/foo/bar`）。该检查只证明 Git 格式合法，不证明符合本命名约定、没有远端重名或可以清理。

### 旧线接续与查询

已有分支不因新格式批量改名，特别是有 open PR、worktree 或活跃 owner 的线。继续原目标时优先复用；短任务扩大成里程碑时，先在原任务中登记 `long-lived`、目标与退出条件，保留旧名并明确映射也可以。若确需改名或迁移，逐项核远端、PR、worktree、自动化引用与 owner 后具名处理，不以“整理名称”重建成果或改写历史。命名约定不自动修改现有 launcher/清理脚本。

可以用 `git branch --list 'milestone/*'` 快速查看采用新格式的本地里程碑线；旧名和仅远端的分支不会被该命令列全，所以它不能替代完整盘点。

同一 Skill、同一目标默认一条权威迭代线；分支长期性、观察验证和续线条件统一见 [里程碑合同](long-lived-integration-branch.md)。开 PR、合并后收尾与未合并关闭的对应关系见 [PR 路径](pr-workflow.md#0-按分支角色确定-pr-路径)。

## Issue 命名格式

### 格式

```
<类型>: <描述>
```

### 类型前缀

与 Commit 类型保持一致：

| 类型 | 描述 | 示例 |
|------|------|------|
| `feat` | 新功能需求 | `feat: github-star-manager 支持自动刷新存量项目元数据` |
| `bug` | Bug 报告 | `bug: description 为 null 时不重试` |
| `enhancement` | 改进建议 | `enhancement: skill-manager 添加版本对比功能` |
| `docs` | 文档相关 | `docs: 更新某技能的使用说明` |
| `question` | 问题咨询 | `question: 能接入 qclaw 吗` |

### 状态标记（关闭时添加）

用于标记 GitHub Issue 的关闭结果：

| 状态 | 来源 | 说明 |
|------|------|------|
| `[done]` | 自己 | 已完成的任务（owner 自己提出的待办） |
| `[resolved]` | 外部 | 问题已解决 |
| `[answered]` | 外部 | 咨询已答复 |
| `[wontfix]` | - | 不打算修复 |
| `[duplicate]` | - | 重复 issue |

**来源区分**：
- **自己提出的待办** → 关闭时标记 `[done]`
- **外部用户提出的** → 关闭时标记 `[resolved]`、`[answered]`、`[wontfix]`、`[duplicate]`

### AI 读取规则

AI 读取 GitHub Issue 标题或关闭评论时：
- 看到 `[done]` → 已完成，跳过
- 看到 `[resolved]`/`[answered]` 等 → 已处理，跳过
- 其他 → 可作为待处理 GitHub 事项，但不得覆盖项目任务源中的状态

### 示例

```
feat: github-star-manager 支持自动刷新存量项目元数据
bug: 修复 description 为 null 时不重试的问题
enhancement: skill-manager 添加版本对比功能
docs: 更新 litigation-analysis 使用文档
question: 能接入 qclaw 吗
[done] 已完成上述任务
[resolved] description 为 null 问题已修复
[wontfix] 该建议暂不采纳
```

## PR 命名格式

### 格式

```
<类型>(<模块>): <描述>
```

### 类型前缀

与 Commit 类型一致：

| 类型 | 描述 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat(skill-manager): 添加版本检查功能` |
| `fix` | Bug 修复 | `fix(skill-manager): 修复符号链接问题` |
| `docs` | 文档更新 | `docs(litigation-analysis): 更新使用文档` |
| `chore` | 工具/依赖 | `chore: 更新 GitHub Actions 版本` |
| `refactor` | 重构 | `refactor(skill-manager): 重构同步逻辑` |
| `style` | 代码风格 | `style: 格式化代码` |
| `license` | 许可证更新 | `license: 更新 XXX 许可证` |
| `config` | 配置变更 | `config: 更新 CI 配置` |
| `test` | 测试相关 | `test: 添加单元测试` |

### 里程碑与子 PR 的可读标识

保留上述 `<类型>(<模块>): <描述>`，里程碑整体交付的描述末尾加 `（里程碑）`，子 PR 不冒充整体完成。例如：

```text
feat(legal-ai-wiki): 完成一日共创教学包 v2（里程碑）
feat(legal-ai-wiki): 增加 workshop-v2 学员练习包
fix(legal-ai-wiki): 修正模块索引
```

里程碑 PR 的摘要先说明最终能力和交付范围，再列实际子 PR/证据；子 PR 明确父线和自身退出条件。状态使用 GitHub 的 Draft/Ready 与任务记录，不额外在标题中维护 `[完成]` 等重复状态。`Refs` 用于父任务/父 PR 关联；子 PR 合并不能用 `Closes` 自动关闭尚未整体达标的里程碑 Issue。

### 模块名称（用于多 Skill 仓库）

对于包含多个独立技能的仓库（如 legal-skills），PR 描述中应包含模块名称：

```
feat(course-generator): 添加多文件支持
fix(piclist-upload): 修复图片上传路径问题
docs(legal-proposal-generator): 更新模板文档
```

### 示例

```
feat(skill-manager): 添加版本检查功能
fix(github-star-manager): 修复 description 为 null 的问题
docs(litigation-analysis): 更新分析报告模板
chore: 更新 GitHub Actions 依赖版本
```

## PR 合并提交格式

使用 squash merge 合并 PR 时，commit 标题**必须包含 PR 编号**。

### 格式

```
<类型>(<模块>): <描述> (#<PR编号>)
```

### 规则

1. **commit 标题末尾必须带 `(#N)`**，其中 N 是 PR 编号
2. 通过 GitHub API 的 `merge_pull_request` 执行 squash merge 时，自定义 `commit_title` 不会自动追加编号，必须手动写入
3. 只有实际完成且已授权关闭的 GitHub Issue 才使用 `Closes #<issue编号>`；仅关联或本地任务使用 `Refs`，不误关 GitHub Issue

### 示例

```
# 正确
feat(local-asr): 新增 ONNX 优化转录路径 (#16)
fix(skill-manager): 修复符号链接创建位置问题 (#12)
docs: 更新 README (#8)

# 错误 — 缺少 PR 编号
feat(local-asr): 新增 ONNX 优化转录路径
```

### 为什么需要手动加编号？

GitHub 网页端 squash merge 会自动在标题末尾追加 `(#N)`，但通过 GitHub API 自定义 `commit_title` 时**不会自动追加**。因此在 API 合并时必须手动在标题中包含编号，确保 `git log` 中可直接追溯 PR。

## 格式对比

| 对象 | 格式 | 模块标识 | PR 编号 |
|------|------|----------|--------|
| Commit | `<类型>: <描述>` | 多 Skill/模块必须加 | 不需要 |
| Issue | `<类型>: <描述>` | 不需要 | 不需要 |
| PR | `<类型>(<模块>): <描述>` | 必须（多 Skill 仓库） | 不需要 |
| Merge Commit | `<类型>(<模块>): <描述> (#N)` | 必须 | **必须** |

## 提交正文与任务来源

提交信息使用英文类型前缀与中文内容，每笔含说明正文；一个提交表达一个目的，独立 Skill/模块按目的拆分。用户明确要求批量拆分/生成提交说明时由 git-batch-commit 处理，仍满足[身份](identity-and-push.md)和[隐私](privacy-preflight.md)合同。

```text
fix(skill-name): 修复解析失败

- 描述实际修改与验证
Refs: <项目任务 ID>
```

直接解决 GitHub Issue 时标题带 `(#N)`，正文使用已授权的 `Closes #N`；它与 PR 编号相似，但来源须核清。不把项目本地 Issue #13 写成 `Closes #13`，改用 `Refs: project-task Issue #13`。
