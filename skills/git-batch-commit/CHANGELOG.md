# 变更日志

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
