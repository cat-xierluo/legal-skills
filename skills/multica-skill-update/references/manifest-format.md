# 清单格式（scripts/manifest.local.json）

个人清单的完整字段与取值约定。可直接复制 `scripts/manifest.example.json` 作为起点，再填入真实来源。

```json
{
  "version": 1,
  "skills": [
    {
      "name": "review-helper",
      "source": "github",
      "url": "https://github.com/owner/repo",
      "on_conflict": "overwrite",
      "enabled": true
    },
    {
      "name": "doc-gen",
      "source": "github",
      "url": "https://github.com/owner/doc-skill",
      "on_conflict": "skip",
      "enabled": true
    }
  ]
}
```

## 字段说明

| 字段 | 取值 | 说明 |
|------|------|------|
| `version` | `1` | 清单格式版本 |
| `skills[].name` | 字符串 | 技能名（仅作报告标识） |
| `skills[].source` | `github` \| `clawhub` \| `skills.sh` \| `file` | 来源类型；`import` 对 URL 来源用 `--url`，`file` 用 `--file` |
| `skills[].url` | URL 或本机路径 | 来源地址；`source=file` 时为本机路径，支持**技能目录**（含符号链接，脚本自动打包成临时 zip）或 `.skill`/`.zip` 归档 |
| `skills[].on_conflict` | `fail`(默认) \| `overwrite` \| `rename` \| `skip` | 同名冲突策略 |
| `skills[].enabled` | `true` \| `false` | `false` 跳过该条，方便临时停用不删记录 |
| `skills[].category` | `development` \| `legal-document` \| `content-writing` 等 | **分类标签（仅存于本地清单，用于按 agent 维度筛选导入）**。Multica 服务端不支持 skill 标签，标签不参与导入，仅作 `--category` 过滤维度 |
| `skills[].group` | 字符串 | 人类可读的分组说明（与 `category` 对应，如 `legal-document / 法律文档`），仅展示用 |

## 来源条目写法

- 本地 skill **目录**（推荐，含符号链接）：`{"name": "xxx", "source": "file", "url": "/path/to/skills/xxx", "on_conflict": "overwrite", "enabled": true}`
  —— 脚本自动打包成临时 zip 再上传，用完即删，无需手工压缩。
- 本地 skill 归档：`{"name": "xxx", "source": "file", "url": "/path/to/xxx.skill", ...}`（`.skill` 或 `.zip`）
- 云端 skill：`{"name": "xxx", "source": "github", "url": "https://github.com/owner/xxx", "on_conflict": "skip", "enabled": true}`

## 分类标签的用途

Multica 各 Agent 需要配置的 skill 类型不同。给清单每条打 `category` 后，
可用 `--category <值>` 只把某一类导入/刷新到工作区，便于「针对性给某个 agent 配一批 skill」。

分类维度复用本仓库 `project-init` 的 profile 分法（`development` / `legal-document` / `content-writing`）。
