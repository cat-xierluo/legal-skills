## [1.6.0] - 2026-08-03

### 新增

- **平台元数据与 skill 本体解耦**：`slug`/`displayName` 不再写进源 SKILL.md frontmatter，下沉到本地 `config/sync-allowlist.yaml`（`display_name` 必填、`slug` 可选默认取 name），发布前由 `prepare-publish.sh --platform skillhub` 自动注入临时副本 frontmatter。源 SKILL.md 回归干净，只保留 skill 标准字段。
- `prepare-publish.sh` 新增 SkillHub frontmatter 注入段：从 `sync-allowlist.yaml` 读取 display_name/slug，幂等注入临时副本 SKILL.md（先删已有再插入）；缺 display_name 时 fail-closed 报错退出。ClawHub 路径不触发（继续用 `--slug`/`--name` 命令行）。

### 改进

- **分发策略改为双平台分流**：一个 skill 只发一个平台，不重复分发。MIT 工具 → `[clawhub]`（已发 ClawHub 的不再发 SkillHub），CC-BY-NC 法律类 → `[skillhub]`，ClawHub slug 冲突 → `[skillhub]`。`platforms` 二选一，不再 `[clawhub, skillhub]`。详见 DECISIONS D-2026-08-03-02。
- `sync-allowlist.yaml`/`.example.yaml` 按分流重写：11 个 MIT 工具改 `[clawhub]`，6 个 CC-BY-NC 法律类保持 `[skillhub]`（`display_name` 仅留给走 SkillHub 的）。
- SKILL.md 策略章节、配置格式示例、同步示例、description 全面改为分流表述。
- 清理 19 个 skill 源 SKILL.md 的 slug/displayName 字段，frontmatter 不再为发布平台膨胀。
- `sync-allowlist.yaml` 与 `.example.yaml` 新增 `display_name`/`slug` 字段说明与示例（含 slug 冲突覆盖示例）。
- SKILL.md 文档全面修正误导表述：平台对比表、frontmatter 必需字段、SkillHub 专属说明、配置文件章节、FAQ 统一改为「slug/displayName 下沉配置、发布时注入」。
- 明确 `.gitignore` 过滤对 ClawHub/SkillHub 两平台均生效（两平台共用 `prepare-publish.sh` 过滤逻辑）；实测发布 clawhub-sync 自身时真实 `sync-allowlist.yaml`/`sync-records.yaml` 不进入临时目录，仅 `.example.yaml` 上传。

## [1.5.1] - 2026-08-01

### 改进

- 校准 ClawHub 许可证条款表述：根据 [官方 Skill Format 文档](https://docs.openclaw.ai/clawhub/skill-format) 核实，补充 5 条关键原文引用（MIT-0 强制、可商用、免署名、不支持 per-skill 覆盖、禁止 SKILL.md 内加冲突条款），避免后续误以为 frontmatter 写 license 即可覆盖平台策略。
- 修正官方文档链接：CLI 文档由 `github.com/openclaw/clawhub` 改为权威文档站 `docs.openclaw.ai/clawhub/cli`；许可证文档由 GitHub `docs/skill-format.md` 改为 `docs.openclaw.ai/clawhub/skill-format`。

## [1.5.0] - 2026-08-01

### 新增

- 支持腾讯 SkillHub 平台发布：官方 `skillhub` CLI（须 ≥ 2026.7.29，`skillhub self-upgrade` 升级）、`skillhub login --key skh_xxx`、`skillhub publish <path> [--version] [--changelog] [--dry-run]`
- SKILL.md 新增「依赖」章节：系统依赖表（rsync/git/Python 3）、CLI 工具表、腾讯 CLI 安装升级方式、首次安装清单
- SKILL.md 新增「平台对比」表、「SkillHub 专属说明」章节（Token 获取、slug 规则、SKILL.md frontmatter 要求、API host）
- 新增双平台许可证策略说明：SkillHub 无许可证限制，CC-BY-NC 法律类 skill 可公开发布（ClawHub 仅 MIT-0）
- 单个 Skill 同步工作流扩展为双平台通用，区分 ClawHub 与 SkillHub 的发布命令

### 改进

- 配置文件重构为多平台字段：
  - `sync-allowlist.yaml` 采用结构化 `platforms` 数组（如 `platforms: [clawhub, skillhub]`）
  - `sync-records.yaml` 采用 `records.<skill>.platforms.<platform>.<field>` 嵌套结构，按平台独立记录版本与状态
- CC-BY-NC 法律类 skill（legal-qa-extractor、legal-text-format、litigation-analysis、legal-proposal-generator、patent-analysis、trademark-assistant）启用并设为 `platforms: [skillhub]`
- `prepare-publish.sh` 参数化：新增 `--platform <clawhub|skillhub>`，临时目录前缀随平台变化，过滤逻辑零改动，旧调用完全向后兼容
- SKILL.md 新增「配置文件与隐私」章节，说明 example（公开模板，入库）与本地配置（gitignore 排除）的关系

### 修复

- 纠正 SkillHub 平台认知：早期版本误用讯飞体系（`@astron-team/skillhub` npm 包、`--visibility`、`skill.xfyun.cn`）。实际腾讯 SkillHub 用官方 `skillhub` CLI（Python 脚本，对接 `api.skillhub.cn`），用 `slug`+`displayName`（SKILL.md frontmatter）标识，登录用 `--key`（非 `--token`），查询身份用 `skillhub auth whoami`。
- namespace 二次纠正：上条曾误判「无 namespace 概念」并清除全部 namespace 字段。经 `skillhub search` 实测，腾讯 SkillHub **有 namespace**（服务端 `@<namespace>/<slug>` 格式，如 `@cat-xierluo/md2word`），但 namespace **绑定在账号上、发布命令不传参**。已将 namespace=cat-xierluo 加回 sync-records.yaml（21 条），文档恢复 namespace 说明。
- 补齐腾讯发布前置字段：新版 CLI（≥2026.7.29）要求 SKILL.md frontmatter 必含 `slug`+`version`+`displayName`（旧版靠 `name` 字段发布的历史 skill 如 md2word/court-sms/skill-lint 现在更新会预检失败）。已给 18 个待发布 skill 补 `slug`+`displayName` 字段，dry-run 全部通过。
- 标记 slug 冲突：`video-compressor`（@gaoq1 占用）、`multi-search`（@neverchenx 占用）在 SkillHub 也被占用，sync-records 标 `status: slug_conflict`，暂不发布。

### 技术优化

- 腾讯 SkillHub CLI 已升级至 2026.7.29（支持 publish/login），低于此版本只能搜索安装不能发布

## [1.4.2] - 2026-06-12

### 变更

- 同步示例配置：将 `skill-architect` 发布记录和白名单入口更新为 `skill-lint`。

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
