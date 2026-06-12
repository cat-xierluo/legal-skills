# Repository Skill Discovery Standards

本文件用于在审查仓库、GitHub 项目或不确定路径时，先定位“最小 Skill 单元”。只有找到或选定最小单元后，才进入结构、frontmatter、发布和业务流审查。

## 为什么先做发现

一个仓库不一定等于一个 Skill。常见情况包括：

- 单 Skill 仓库：仓库根目录就是 Skill 根目录，直接包含 `SKILL.md`。
- monorepo / Skill 集合：仓库根目录只是容器，多个子目录分别是 Skill。
- 插件仓库：根目录包含 marketplace、README、docs，Skill 在约定子目录下。
- 提示词集合：没有标准 `SKILL.md`，但有多个带 `name` / `description` 的 Markdown 或 README 索引。
- 普通代码仓库：没有可识别的 Skill 单元。

因此，不能只看仓库根目录是否存在 `SKILL.md`。根目录缺少 `SKILL.md` 不是 monorepo 的结构错误。

## 发现顺序

按以下顺序判断：

1. 用户是否明确指定了某个子目录或文件。
2. 目标目录自身是否包含 `SKILL.md`。
3. 目标仓库内是否存在一个或多个 `*/SKILL.md`。
4. README、marketplace、插件清单或目录名是否指向 Skill 子目录。
5. 是否存在带 `name` 和 `description` frontmatter 的非 `SKILL.md` Markdown 文件。
6. 是否只是普通文档或代码仓库。

默认扫描深度可先到 4 层；仓库很大时，优先扫描 `skills/`、`.claude/skills/`、`custom-skills/`、`private-skills/`、`packages/`、`plugins/`、`examples/` 等常见容器目录，并跳过 `.git/`、`node_modules/`、`.venv/`、`dist/`、`build/`、`archive/` 等运行或构建目录。

## 候选单元分级

| 级别 | 识别条件 | 审查口径 |
|------|----------|----------|
| 已确认 Skill 单元 | 目录直接包含 `SKILL.md` | 按标准 Skill 审查，缺 frontmatter 或引用断裂可判严重 |
| 弱结构 Skill 单元 | 目录内有 `SKILL.md` 但 frontmatter 不完整 | 仍按 Skill 单元审查，记录 frontmatter 问题 |
| Skill-like 文档 | 非 `SKILL.md` 文件带 `name` / `description` frontmatter | 标为迁移候选，不直接视为标准 Skill |
| README 索引项 | README 表格或清单把文件称为 skill | 标为候选范围，需要进一步确认或迁移 |
| 普通参考资料 | 法源、案例、提示词、说明文档 | 只在被 Skill 引用或用户要求时审查 |

## 单元选择规则

如果用户指定具体 Skill 单元，优先审查该单元。

如果用户只给仓库：

- 有 1 个 `SKILL.md`：审查该单元，并检查仓库级发布治理。
- 有多个 `SKILL.md`：列出所有单元；按用户目标全量审查或抽样审查；报告中必须写明范围。
- 没有 `SKILL.md` 但有 Skill-like 文档：按“改造评估”审查，不要直接写成标准 Skill 不通过；重点说明如何迁移成标准 Skill。
- 没有任何候选：说明未发现 Skill 单元，停止 Skill 质量审查，除非用户要求做普通文档或代码审查。

## monorepo 报告要求

审查 monorepo 或外部仓库时，报告必须先给出发现结果：

| 单元 | 类型 | 状态 | 说明 |
|------|------|------|------|
| `<path>` | 已确认 Skill / Skill-like 文档 / README 索引项 | 纳入审查 / 未纳入 | `<原因>` |

然后再分别报告：

- 仓库级治理问题：README、LICENSE、CHANGELOG、marketplace、Git 历史、发布索引。
- 单元级问题：每个 Skill 的 `SKILL.md`、frontmatter、references、templates、业务流和可评估性。

不要用一个根目录结论替代所有子 Skill 的结论。

## Git 历史辅助检查

审查 GitHub 仓库或 Git 仓库时，提交历史可分两层看：

- 仓库级：总体提交频率、提交信息规范、版本标签、发布节奏。
- 单元级：对每个 Skill 单元使用路径过滤查看提交，例如 `git log -- <skill-path>`。

如果某个 Skill 单元长期没有独立提交记录，或大量变更都以泛化提交信息上传，应记录为维护可追溯性风险，而不是直接等同内容质量不合格。

## 严重程度边界

以下情形才把“缺少 `SKILL.md`”列为严重问题：

- 用户明确指定的目标路径应当是一个 Skill 单元。
- README、marketplace 或发布文档声明某目录是标准 Skill，但该目录没有 `SKILL.md`。
- 仓库宣称自身可作为单个 Skill 安装或加载，但根目录没有 `SKILL.md`。

以下情形不应直接判为严重：

- 仓库根目录是 monorepo 容器，子目录中存在标准 Skill。
- 仓库是 prompt toolkit 或知识库，目标是改造成 Skill。
- 单个 Markdown 是可复制提示词，而不是声明可加载的 Skill 单元。
