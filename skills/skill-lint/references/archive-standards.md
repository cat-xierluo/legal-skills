# Archive Standards

本文件定义 `skill-lint` 的内部归档机制。归档用于保留审查结论和复查依据，不用于公开发布真实审查材料。

## 何时归档

默认归档以下场景：

- 用户要求最终质量意见报告
- 发布前验收报告
- 第三方 Skill 正式评估报告
- GitHub 项目或外部仓库的 Skill 质量审查报告
- 修复后复查报告

以下场景不默认归档：

- 临时口头反馈
- 用户只要求快速检查一个单点问题
- 报告中包含尚未脱敏的客户、案件、合同、账号或联系方式信息

## 归档目录

归档写入 `skill-lint/archive/`，使用单次审查一个目录的方式：

```text
archive/
└── YYYYMMDD_HHMMSS_<target-slug>/
    ├── quality-opinion-report.md
    ├── review-metadata.json
    └── evidence-index.md
```

命名规则：

- `YYYYMMDD_HHMMSS` 使用本地时间。
- `<target-slug>` 使用目标 Skill 名、仓库名或项目名的安全化短名。
- 只使用小写字母、数字和连字符。
- 不把客户名、案件名、案号、手机号、邮箱或私有项目代号写入目录名。

## 归档文件

| 文件 | 用途 | 注意 |
|------|------|------|
| `quality-opinion-report.md` | 最终质量意见报告 | 使用 `templates/skill-quality-opinion-report.md` 生成 |
| `review-metadata.json` | 机器可读元数据 | 只记录审查范围、时间、目标、规则版本、结论和问题数量 |
| `evidence-index.md` | 证据索引 | 只写相对路径、提交摘要、检查命令摘要，不粘贴大段原文 |

`review-metadata.json` 示例：

```json
{
  "schema_version": 1,
  "reviewed_at": "YYYY-MM-DD HH:MM:SS",
  "target": "<target-path-or-url>",
  "target_type": "local-skill|github-repository|third-party-skill",
  "skill_lint_version": "<skill-lint-version>",
  "result": "pass|conditional_pass|fail",
  "issue_counts": {
    "critical": 0,
    "warning": 0,
    "info": 0
  },
  "archived_files": [
    "quality-opinion-report.md",
    "evidence-index.md"
  ]
}
```

## Git 规则

`archive/` 是运行归档目录，不提交真实内容：

- Git 只保留 `archive/.gitkeep`。
- 真实归档内容被根目录 `.gitignore` 的 `**/archive/*` 忽略。
- 不要为了展示示例把真实审查报告放入 `archive/`。
- 如果需要公开示例，应使用完全虚构材料，并放在 `examples/` 或 `templates/`，不放在 `archive/`。

## 隐私与安全

归档前必须检查：

- 不含真实人名、客户名、案件项目、案号、联系方式、地址、账号或密钥。
- 不复制外部仓库的大段原文，只记录必要位置和摘要。
- 如果用户提供本地 review profile，不写入真实配置值。
- GitHub 项目审查可以记录提交哈希和提交信息摘要，但不要记录访问令牌或私有远程地址。

无法确认是否可公开时，归档只保留脱敏摘要；必要时不归档，改为在对话中说明原因。

## 复查关系

同一目标多次审查时，不覆盖旧归档。新建新的时间戳目录，并在报告中说明：

- 本次是否为复查
- 对应的上次归档目录
- 已关闭的问题
- 仍未关闭的问题
- 新增问题
