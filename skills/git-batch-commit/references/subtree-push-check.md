# Subtree 推送检查（工作流第6步）

> **核心规则：仅当项目目录下存在 `skills/subtree-publish/config/subtree-skills.json` 时才执行——不存在则静默跳过，不输出任何提示。**

完成 Git 提交后，检查本次提交是否涉及已注册的 subtree 子项目。

## 触发条件

1. **配置文件存在**
   - 检查 `skills/subtree-publish/config/subtree-skills.json` 是否存在
   - **不存在则静默跳过，不提示用户**

2. **提交涉及已注册的子目录**
   - 读取 `skills/subtree-publish/config/subtree-skills.json` 中的 `prefix` 和 `skills` 列表
   - 获取本次提交涉及的文件列表（`git diff --name-only HEAD~1 HEAD`，或批量提交时使用最后一次 commit）
   - 检查是否有文件路径以 `<prefix>/<skill-name>/` 开头
   - 如果命中，收集所有命中的 skill 名称

3. **remote 已配置**
   - 检查是否存在对应的 `<name>-standalone` remote
   - 如果 remote 不存在，说明该子项目尚未完成首次注册，跳过

## 提示与执行

满足触发条件时，向用户提示：

```
本次提交涉及已注册的 subtree 子项目：<name1>, <name2>
是否推送到独立仓库？

选项：
  y - 推送所有命中的子项目
  n - 跳过，暂不推送
  s - 选择性推送
```

用户选择 `y` 时，对每个命中的子项目执行：

```bash
git subtree push --prefix=<prefix>/<name> <name>-standalone main
```

用户选择 `s` 时，逐个询问是否推送。

## 失败处理

- 推送失败时仅显示警告信息
- 不影响 Git 提交结果
- 继续处理其他子项目

## 示例场景

| 场景 | 配置文件 | 提交涉及子目录 | remote 存在 | 结果 |
|------|----------|---------------|-------------|------|
| 正常推送 | 存在 | 是 | 是 | ✅ 提示用户推送 |
| 未涉及子目录 | 存在 | 否 | - | ❌ 静默跳过 |
| 配置文件不存在 | 不存在 | - | - | ❌ 静默跳过 |
| 首次注册未完成 | 存在 | 是 | 否 | ❌ 跳过（提示用户先完成首次注册） |
