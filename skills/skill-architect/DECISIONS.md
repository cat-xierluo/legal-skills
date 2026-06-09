# Decisions

## D-2026-06-07-01 整合 skill-lint 到 skill-architect

- 背景：`skill-architect` 已包含创建、编辑和格式审查流程，`skill-lint` 只提供独立审查入口；两者的 `references/skill-standards.md` 内容完全一致，继续维护两个技能会造成触发与规则维护重复。
- 决策：保留 `skill-architect` 作为唯一公开 Skill，将 `skill-lint` 作为旧称兼容到审查模式；从 README、Marketplace 和发布配置示例中移除 `skill-lint` 独立入口，并删除 `skills/skill-lint/` 目录。
- 理由：`skill-architect` 是更完整的上位技能，已覆盖审查模式；合并后只需维护一套规范、一份触发描述和一条发布记录。
- 许可证：合并后的 `skill-architect` 使用 MIT，避免将原 MIT 的审查能力整合后变为更受限的许可证，并符合通用工具类 Skill 的许可证规范。

