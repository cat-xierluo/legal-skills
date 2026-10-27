# Skill 升级提案内容模板

机器生成的 Markdown 只是待审产物；规范状态保存在 proposal store 中，不从正文猜测人工决定。

```markdown
# <目标 Skill> 升级提案

## 提案摘要

- Proposal ID：`<stable-id>`
- 目标 Skill：`<skill-id>`
- 目标版本：`<version>`
- 机器处置：`candidate | duplicate | covered | recommended | filtered`
- 隐私状态：`pending | passed | quarantined`
- 产物内容哈希：`<sha256>`

## 建议变更点

1. <可独立判断的变更点>
2. <可独立判断的变更点>

## 证据索引

- `<evidence-id>`：说明跨 session 重复信号，不写原始私有路径或原文。

## 当前能力与差距

- 当前已覆盖：<现状>
- 新颖部分：<为什么不是 duplicate/covered>
- 不建议自动处理：<边界>

## 建议验证

- <synthetic fixture 或行为断言>
- <人工实操步骤>
```

要求：

- 先通过隐私门控，再写入 Review Inbox；
- change points 应原子化，以便稳定 fingerprint 和部分接受；
- 不在模板中预填“已接受”“已实施”或“已验证”；
- 不复制 transcript、密钥、完整用户目录或案件身份信息；
- 人工决定、应用 commit 与验证结果只通过追加事件登记。
