# Release Notes 撰写指南

## 调研来源

综合以下项目的 Release Notes 实践：

| 项目 | 类型 | 特点 |
|------|------|------|
| Zettlr | Electron Markdown 编辑器 | 自然语言概述 + 分类条目 + PR 链接 |
| Clash Verge Rev | Tauri 桌面应用 | 中文撰写 + emoji 分节 + 平台下载链接 |
| SiYuan | Electron 笔记应用 | shields.io badge + issue 链接式 |
| bat | Rust CLI 工具 | 极简分类 + @贡献者 |
| Typst | Rust 排版系统 | 叙述式安全问题 + 贡献者致谢 |
| Claude Code | CLI 工具 | 高频发布，平铺条目 |
| NiceHash | 桌面应用 | 安装指引优先 + 安全验证 |

参考样例：
- Clash Verge Rev v2.5.1: https://github.com/clash-verge-rev/clash-verge-rev/releases/tag/v2.5.1
- Zettlr v4.5.0: https://github.com/Zettlr/Zettlr/releases/tag/v4.5.0
- Obsidian v1.12.7: https://github.com/obsidianmd/obsidian-releases/releases/tag/v1.12.7
- Tauri CLI v2.11.2: https://github.com/tauri-apps/tauri/releases/tag/tauri-cli-v2.11.2

## 结构选择

发布时先读取 `config/projects.yaml`：

- 配置了 `release_notes.profile`：按项目配置指定的结构生成。
- 未配置：桌面应用默认用 `desktop-standard`，CLI / 库 / Web 按下方适配规则简化。

## 固定结构

### desktop-standard

适用于 Tauri / Electron 桌面应用，尤其是需要用户下载安装包、处理 Gatekeeper / SmartScreen / 终端命令提示的项目。结构固定如下：

1. 一句话摘要：正文第一行，使用 blockquote，不写版本标题。
2. `## Highlights`：2-5 条用户最关心的变化。
3. `## 新增`：仅在有新增功能时出现。
4. `## 变更`：仅在有行为、流程、配置、依赖或发布链路变化时出现。
5. `## 修复`：仅在有 bug fix 时出现。
6. `> [!WARNING]`：有安装限制、终端命令、破坏性变更、安全提示时必须出现。
7. `## 下载`：桌面应用必须出现，列出面向用户的安装包。
8. 自动更新产物说明：有 `.tar.gz` / `.sig` / `latest.json` 时必须说明普通用户无需下载。
9. 完整变更日志：最后一行使用 compare 链接。

`新增 / 变更 / 修复` 中没有内容的分区直接省略，不保留空标题。

## 推荐模板

```markdown
> 一句话概括本版本核心变更（让用户 5 秒内理解为什么要升级）

---

> [!NOTE]
> 升级提示（仅在有需要时出现）

## Highlights

- **核心特性 1**：简短描述，突出用户价值
- **核心特性 2**：简短描述

---

## 新增

- 功能描述 (#PR号)

## 变更

- 行为变更描述 (#PR号)

## 修复

- 修复描述 (#PR号)

---

> [!WARNING]
> 破坏性变更说明（仅在存在时包含此节）

---

## 下载

| 平台 | 架构 | 文件 |
|------|------|------|
| macOS | Apple Silicon | `<项目>_<版本>_aarch64.dmg` |
| macOS | Intel | `<项目>_<版本>_x64.dmg` |
| Windows | x64 | `<项目>_<版本>_x64-setup.exe` |

> `.tar.gz` + `.sig` 为自动更新专用，无需手动下载。

---

**完整变更日志**: https://github.com/<owner>/<repo>/compare/<上个tag>...vX.Y.Z
```

## 设计决策

| 决策 | 依据 |
|------|------|
| 正文不写版本标题 | GitHub Release 页面已经显示 release title，正文再写 `# <项目名> vX.Y.Z` 会重复；正文应直接从摘要、提示或 Highlights 开始 |
| 中文撰写 | Clash Verge Rev（Tauri 项目）验证中文 Release Notes 完全可行 |
| 顶部一句话 Highlights | Zettlr / Clash Verge 实践：小项目用户不会逐条读 changelog |
| 固定桌面应用结构 | Clash Verge Rev 重视下载区，Zettlr 重视摘要和 changelog，Folia 需要额外稳定呈现 macOS 终端提示 |
| 表格列下载链接 | 比 `###` / `####` 分级轻量，比纯链接结构化，适合 Folia 这种多平台桌面应用 |
| `> [!WARNING]` 标注破坏性变更 | GitHub 原生 callout，视觉醒目 |
| 每条附 PR 号 | Zettlr / SiYuan / bat 的共识做法，可追溯 |
| Full Changelog 比较链接 | Zettlr 的做法，一键查看完整 diff |

## 不同项目类型的适配

### 桌面应用（Tauri / Electron）

默认使用 `desktop-standard`。下载表格列出各平台安装包。标注"推荐"和"不常用"。自动更新产物（`.tar.gz` / `.sig` / `latest.json`）单独说明。

### CLI 工具 / 库

不需要下载表格。改为安装命令：

```markdown
## 安装

npm install <package>@X.Y.Z
# 或
cargo install <package>
```

### Web 应用

不需要下载表格。改为部署说明或 changelog 链接。

### 高频发布项目（每天/每周）

参考 Claude Code 的极简格式：所有条目平铺在 `## What's changed` 下，不做分类。

## 不需要的内容

- shields.io badge（适合大项目，小项目过于复杂）
- 安全 checksums（除非面向安全敏感用户或用户明确要求）
- Cargo audit / 构建日志（框架层细节，应用层不需要）
- 赞助提示（可选，非必须）
