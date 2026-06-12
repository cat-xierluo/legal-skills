# Frontmatter 元数据分层策略

本策略用于区分 Claude Code Skill 的通用加载字段和项目发布字段，避免把个人或项目默认配置误写成所有 Skill 都必须遵守的通用规范。

## 1. 通用最小 Frontmatter

普通 Skill 只要求两个字段：

```yaml
---
name: skill-name
description: 本技能应在用户需要...时使用。不要用于：...
---
```

- `name`：技能唯一名称，使用小写字母和连字符
- `description`：触发指纹，说明功能、触发场景和不触发场景

缺少 `name` 或 `description` 是严重问题。

## 2. 发布字段

以下字段属于项目发布策略，不是普通 Skill 的通用硬要求：

- `version`
- `license`
- `author`
- `homepage`
- `source`

审查规则：

- 普通 Skill 缺少这些字段，不应判为问题
- 如果字段存在，应检查格式和一致性
- 如果项目规则、Marketplace 或发布平台明确要求这些字段，再按该项目规则审查
- 不应在通用模板中硬编码个人作者、个人主页或特定仓库地址

## 3. 个人 / 项目默认值

个人或项目默认值应来自外部规则，而不是写入通用 Skill 模板。

可接受来源：

- 项目级 `AGENTS.md`
- 项目 README 或发布规范
- Marketplace 清单
- 本地个人规则文件，例如从 `config/review-profile.example.yaml` 复制得到的 `config/review-profile.local.yaml`
- 用户当轮明确指定的发布配置

本地个人规则文件只作为审查上下文，不应写入公开仓库。

## 4. 可复用配置模板

`config/review-profile.example.yaml` 提供可复制的审查配置结构：

- `frontmatter.minimal_required`：普通 Skill 的通用必需字段
- `frontmatter.publishing_fields`：项目发布字段及默认来源
- `frontmatter.third_party_review`：审查他人 Skill 时如何处理发布字段缺失
- `privacy`：公开文件去具体化规则
- `severity`：问题严重程度映射
- `report`：报告是否暴露本地配置值

使用方式：

1. 复制 `config/review-profile.example.yaml` 为 `config/review-profile.local.yaml`
2. 在 local 文件中填写个人或项目默认值
3. 审查时把 local 文件作为本地上下文
4. 不提交 local 文件

## 5. legal-skills 项目特例

在本仓库中，`version`、`license`、`author`、`homepage` 可以作为发布字段维护，因为项目规范要求公开 Skill 支持 Marketplace / ClawHub / README 索引同步。

但这只是本仓库的发布策略，不应被 `skill-lint` 当成所有 Skill 的通用要求。

审查第三方 Skill 时：

- 不因为缺少 `homepage`、`author`、`version`、`license` 直接判错
- 若这些字段明显复制了本项目个人配置，且目标不是本项目 Skill，应标为警告
- 若这些字段含真实个人信息、客户信息或不可公开地址，应按公开内容清洁度规则处理

## 6. 报告建议

当发现发布字段问题时，报告应区分两类：

```markdown
### Frontmatter

- 通用必填字段：通过 / 不通过
- 发布字段：适用 / 不适用 / 需按项目规则补充
- 个人或项目默认值：未发现 / 疑似误写入 / 明显误写入
```
