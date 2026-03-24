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
