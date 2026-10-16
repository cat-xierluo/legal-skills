# Publishing Standards

本文件检查公开发布相关要求，包括 LICENSE、CHANGELOG、version、README 和 Marketplace。普通私有 Skill 不默认套用本文件的全部要求。

## 何时读取

在以下场景读取本文件：

- 用户要求发布前审查
- Skill 已列入 README、Marketplace、ClawHub 或同步配置
- 项目规则要求公开分发
- frontmatter 已声明 `version`、`license`、`homepage`、`author` 等发布字段

## License

| 场景 | 缺少 LICENSE 的处理 |
|------|---------------------|
| 私人草稿 Skill | 信息提示 |
| 第三方普通 Skill | 一般不判错，按用户目标判断 |
| 本仓库公开 Skill | 警告或严重问题，按项目规则 |
| frontmatter 已声明 `license` | 应检查 LICENSE 文本或项目许可证说明 |

许可证属于发布治理，不属于基础目录结构。不要因为普通 Skill 没有 `LICENSE.txt` 就直接判定不合格。

## 项目发布配置

发布要求取自被审查项目已确认的规则，不把本Skill所在仓库的配置套给所有目标。维护legal-skills公仓公开Skill时，按需读取[本项目发布配置](legal-skills-project-profile.md)：许可证/版权/公开字段、Command迁移历史和README维护仅在那里维护。其他目标无明确项目配置时沿通用发布检查，不继承个人作者、联系方式、主页或版本起点。

## 发布字段

| 字段 | 审查口径 |
|------|----------|
| `version` | 存在时必须与 CHANGELOG 最新版本一致 |
| `license` | 存在时必须与许可证文本或项目规则一致 |
| `author` | 项目发布字段，不是普通 Skill 通用必填 |
| `homepage` | 项目发布字段，不是普通 Skill 通用必填 |
| `source` | 平台需要时使用；已有 `homepage` 时可省略 |

字段分层的通用规则见 `frontmatter-metadata-policy.md`。

## CHANGELOG

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 文件存在 | ✅/⚠️ | 公开 Skill 推荐必备 |
| 最新版本在顶部 | ✅/⚠️ | 便于同步版本 |
| 日期格式统一 | ✅/⚠️ | 使用 `YYYY-MM-DD` |
| 分类清楚 | ✅/⚠️ | 新增、改进、修复、技术优化、文档完善 |
| 不使用 `Unreleased` 作为版本号 | ✅/⚠️ | 项目规则要求明确版本 |
| 历史不穿越 | ✅/⚠️ | 旧版本段落不描述后续才出现的能力 |

## 版本同步

公开 Skill 应同步以下位置：

- `SKILL.md` frontmatter `version`
- `CHANGELOG.md` 最新版本
- README 技能列表
- Marketplace / ClawHub 同步配置

版本不一致一般标为警告；已进入发布流程且会导致用户安装旧版本时，可标为严重问题。

## 发布索引

按目标项目当前启用的README/平台索引规则同步。legal-skills的最近8条、日期顺序和公开目录范围见上述项目配置；其它仓库不强制采用这些数值。

## 发布内容清洁度

发布配置、README 和平台索引中不得夹带真实客户、案件、未经授权的联系方式、私有路径或不可公开项目名；项目明确公开的作者/许可联系标识按其项目配置核对，不误当客户材料。示例值用占位符或泛化描述。
