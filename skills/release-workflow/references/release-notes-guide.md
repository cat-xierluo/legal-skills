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

## 推荐模板

```markdown
# <项目名> vX.Y.Z

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
| 中文撰写 | Clash Verge Rev（Tauri 项目）验证中文 Release Notes 完全可行 |
| 顶部一句话 Highlights | Zettlr / Clash Verge 实践：小项目用户不会逐条读 changelog |
| 表格列下载链接 | 比 `###` / `####` 分级轻量，比纯链接结构化 |
| `> [!WARNING]` 标注破坏性变更 | GitHub 原生 callout，视觉醒目 |
| 每条附 PR 号 | Zettlr / SiYuan / bat 的共识做法，可追溯 |
| Full Changelog 比较链接 | Zettlr 的做法，一键查看完整 diff |

## 不同项目类型的适配

### 桌面应用（Tauri / Electron）

下载表格列出各平台安装包。标注"推荐"和"不常用"。自动更新产物（`.tar.gz` / `.sig`）单独说明。

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
