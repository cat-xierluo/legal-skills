# 约定式提交规范

本 skill 遵循约定式提交（Conventional Commits）规范进行提交信息格式化。

## 格式

```
<类型>: <描述>
```

## 支持的类型

| 类型 | 描述 |
|------|-------------|
| `Docs` | 文档变更 |
| `Feat` | 新功能 |
| `Fix` | Bug 修复 |
| `Refactor` | 代码重构 |
| `Style` | 代码风格变更 |
| `Chore` | 构建工具、依赖、工具链 |
| `Test` | 测试添加或修改 |
| `Config` | 配置变更 |
| `License` | License 文件更新 |

## 示例

```
Docs: 更新 README 文档
Feat: 添加用户认证
Fix: 修复解析器内存泄漏
Chore: 更新依赖
License: 更新 license 文件
Refactor: 简化数据层
```

## 为什么要使用标准化提交？

1. **更易阅读：** 快速理解改动内容
2. **更好的 git log：** 更清晰、更有意义的历史记录
3. **自动化 changelog：** 工具可以自动生成 CHANGELOG.md
4. **语义化版本控制：** 帮助确定版本升级
5. **团队一致性：** 所有人使用相同的格式
