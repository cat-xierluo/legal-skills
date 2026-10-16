# legal-skills 项目发布配置

仅在维护 **legal-skills 公仓中的公开 Skill** 或审查其发布时读取。它承接根 AGENTS.md 原有项目配置，不是第三方、普通私有 Skill 或所有仓库的默认要求；不要复制到通用模板。通用写法/依赖/脚本防护见[开发指南](skill-dev-guide.md)和[工作流与输出](workflow-output-standards.md)，通用发布检查见[publishing-standards.md](publishing-standards.md)。

## 目录与发布来源

公开正式交付源为 `skills/`，试验为 `test/`；目录名与 Skill name 一致。根目录包含 SKILL.md，config/references/scripts/assets及许可证/维护文档按对应规范和实际需要组织，示例/原始材料不混入其他技能。私有/custom目录不纳入公开索引。旧 `.claude-plugin/marketplace.json` / `plugin.json` 已停用，不为更新 Skill 重建。

## 许可与版权

| 类型 | frontmatter license | LICENSE.txt |
|---|---|---|
| 法律业务分析、文书或专业咨询 | `CC-BY-NC` | 完整 Creative Commons Attribution-NonCommercial 4.0 International 文本 |
| 通用内容获取、格式转换、开发工具 | `MIT` | 完整 MIT 文本 |
| 官方 Skill | 保持原值 | 保留原作者文本 |

自研 Skill 的版权行保持项目既有值，不因当前年份自动改写：

```text
Copyright (c) 2025 杨卫薪律师（微信ywxlaw）
```

协作/外部项目可保留其特定版权；官方 Skill 不替换版权。CC-BY-NC 的商用许可附文统一为：

```text
Commercial License

For commercial use licenses, please contact:
Email: secretxierluo@gmail.com
WeChat: ywxlaw (微信)
```

这些是项目作者主动公开的发布标识，不是示例客户信息。README Skill 列表含许可证列；许可字段与完整文本一致。平台许可/allowlist差异读取已安装的 skill-publish-sync，不因平台选择自行改原许可或扩大公开范围。

## 版本、变更记录与迁移

- `SKILL.md` 版本与 CHANGELOG 最新版本一致。新试验沿 `0.x.x`，正式 Skill 从 `1.0.0` 起；既有已确认版本轨迹不因本次规则迁移重新编号。
- CHANGELOG 最新在上，标题为 `## [版本号] - YYYY-MM-DD`，不用 `Unreleased`；按新增、改进、修复、技术优化、文档完善等分类写实际变化、原因和影响，不写执行流水或未经证实的能力。
- 从 Command/提示词迁移时，在 CHANGELOG 末尾保留“原始版本记录（Command时期）”，完整保留其已有版本/日期/摘要；新的Skill正式版本从1.0.0起，不沿用Command编号。没有历史材料时标待补，不编造记录。

## 公开字段与README

本项目的发布字段默认值如下；平台最终格式沿目标平台现行入口，不把此表施加给第三方 Skill：

| 字段 | 本项目口径 |
|---|---|
| `name` / `description` | 来自实际Skill，name与目录名一致 |
| `version` | 与CHANGELOG最新版本一致；使用metadata.version时按加载器规则，双处存在须一致 |
| `license` | 按上表类型与LICENSE一致 |
| `author` | 杨卫薪律师（微信ywxlaw） |
| `homepage` | https://github.com/cat-xierluo/legal-skills |
| `source` | 已有homepage时可省略；以实际平台要求为准 |

新增、正式迁移或更新公开 Skill 时，同步 README 技能索引及顶部最近更新区：

- 只留最近8条公开动态，按对应CHANGELOG最新日期倒序；类型使用“新上传”“正式发布”“更新”。
- 要点取自对应CHANGELOG，不包含private-skills/custom-skills，不推测能力。
- 不创建项目级CHANGELOG。平台上传使用skill-publish-sync；提交或更新版本不自动等于已获上传/发布授权。
