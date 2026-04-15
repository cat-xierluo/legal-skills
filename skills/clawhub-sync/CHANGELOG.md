## [1.4.1] - 2026-03-26

### 修复

- 发布命令添加 `--slug` 参数：避免临时目录名导致的 slug 错误
- 发布命令添加 `--name` 参数：确保 ClawHub 显示正确的名称
- 删除错误命名的 skills：`clawhub-publish-clawhub-sync`、`clawhub-publish-git-batch-commit`

## [1.4.0] - 2026-03-26

### 新增

- SKILL.md 新增「单个 Skill 同步工作流」章节
- 支持版本号检测：比较 SKILL.md frontmatter 与 sync-records.yaml 中的版本
- 支持前置检查：登录状态、白名单、许可证验证
- 支持增量同步：只同步版本号有更新的 skill

### 变更

- description 更新，增加「单个 skill 同步」功能说明
- **改用 `clawhub publish` 命令**：避免 `clawhub sync` 扫描其他目录导致的 slug 冲突

## [1.3.0] - 2026-03-24

### 新增

- SKILL.md 新增「ClawHub 许可证政策」章节，详细说明 MIT-0 与其他许可证的兼容性
- 添加许可证兼容性对照表（MIT-0 vs CC-BY-NC）
- sync-allowlist.yaml 添加许可证标注，区分可同步/不可同步的 skill

### 变更

- 白名单中注释掉 CC-BY-NC 许可证的 skill（legal-*, patent-analysis, trademark-assistant 等）
- 仅保留 MIT 许可证的 skill 为可同步状态

### 删除

- 从 ClawHub 删除 trademark-assistant（许可证冲突）

## [1.2.0] - 2026-03-24

### 新增

- 添加 `scripts/prepare-publish.sh` 发布目录准备脚本
- 支持 .gitignore 双重过滤机制（项目根目录 + 技能内部）
- 使用 rsync 过滤敏感文件，- 添加安全最佳实践指南

## [1.1.1] - 2026-03-23

### 变更

- 白名单配置文件迁移至 skill 内部（自包含）
- 配置路径：`.clawhub/sync-allowlist.yaml` → `skills/clawhub-sync/sync-allowlist.yaml`
- 配置路径：`.clawhub/sync-allowlist.yaml.example` → `skills/clawhub-sync/sync-allowlist.yaml.example`
- SKILL.md 文档路径同步更新

## [1.1.0] - 2026-03-23

### 新增

- 支持 `.clawhub/sync-allowlist.yaml` 白名单配置
- 批量同步时只同步白名单中列出的 skill
- 未列出的 skill 不会被同步（精确控制发布内容）
- 提供 `sync-allowlist.yaml.example` 模板参考

### 变更

- 同步策略优先级：白名单文件存在时 > 默认忽略规则

## [1.0.0] - 2026-03-21

### 新增

- 初版发布
- 支持登录、验证、同步单个/批量技能
- 版本号自动从 CHANGELOG.md 提取
- 自动设置 homepage 字段
- 忽略 test/、private-skills/ 等目录
