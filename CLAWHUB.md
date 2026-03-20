# ClawHub 发布适配指南

本文档定义如何将本项目中的 Skill 适配并发布到 ClawHub。

## 为什么需要适配（原因）

ClawHub 与 Claude Code 对 Skill 的要求不同：

| 差异 | Claude Code | ClawHub | 不适配的后果 |
|------|------------|---------|--------------|
| **version 字段** | 可选 | **必填** | 无法发布，ClawHub 拒绝无版本号的 Skill |
| **author 字段** | 可选 | **必填** | 发布时 ClawHub 无法识别作者 |
| **homepage/source** | 可选 | **必填** | ClawHub 要求完整的来源信息 |
| **发布流程** | 即时生效 | 需要 sync/publish | Claude Code 的 Skill 不能直接在 ClawHub 搜索到 |

**核心原因**：ClawHub 是一个 Skill **市场**，需要版本控制、作者归属和来源追踪，而 Claude Code 的 Skill 是本地自用为主的。

## 字段调整规则

### 1. version 字段——为什么必须有

**原因**：ClawHub 基于语义化版本（semver）管理 Skill 更新。
- 用户安装后可以 `clawhub update` 升级到新版本
- 降级、回滚需要明确的版本号
- 没有版本号，ClawHub 无法判断哪个版本更新

**规则**：从 CHANGELOG.md 第一行读取最新版本号，作为 SKILL.md 的 `version` 字段值。

### 2. author/homepage/source——为什么必须有

**原因**：ClawHub 需要知道这个 Skill 是谁做的、从哪里来的。
- 展示在 Skill 详情页
- 用户可以追溯原始项目
- 便于作者维护和更新

**规则**：固定值：
- `author`: `杨卫薪律师（微信ywxlaw）`
- `homepage`: `https://github.com/cat-xierluo/legal-skills`
- `source`: `https://github.com/cat-xierluo/legal-skills`

### 3. name 字段——为什么必须与目录名一致

**原因**：ClawHub 用 slug（URL 友好名称）标识 Skill，安装命令是 `clawhub install <slug>`。
- slug 直接来自 name 字段
- name 与目录名一致确保本地和远程一致

**规则**：name = 目录名（全小写、连字符分隔）

### 4. license 字段——为什么必须明确

**原因**：ClawHub 是开源社区市场，用户需要知道能不能商用、要不要署名。
- 没有 license，ClawHub 默认全限
- 法律类 Skill 通常是 CC BY-NC-SA（非商业使用）

**规则**：遵守 AGENTS.md 中的许可证规范。

## 与 Claude Code Skill 的主要区别

| 项目 | Claude Code | ClawHub |
|------|------------|---------|
| 版本号 | 可选 | **必须**，从 CHANGELOG 读取 |
| frontmatter | 基本字段 | 扩展字段（author、homepage、source） |
| 发布方式 | 即时生效 | 需要 `clawhub sync` 或 `clawhub publish` |

## SKILL.md Frontmatter 要求

ClawHub 要求所有 Skill 必须包含以下 frontmatter 字段：

```yaml
---
name: <skill-name>           # 必须，与目录名一致
description: <描述>          # 必须，简洁描述技能用途
version: "<semver>"          # 必须，格式：1.0.0（无 v 前缀）
license: <许可证>             # 必须
author: <作者名>              # ClawHub 必填
homepage: <项目主页>           # ClawHub 必填
source: <源码地址>             # ClawHub 必填
---
```

### 字段说明

| 字段 | 来源 | 示例 |
|------|------|------|
| `name` | 目录名 | `legal-proposal-generator` |
| `description` | 现有 description 字段 | 根据案件材料生成... |
| `version` | **从 CHANGELOG 提取** | `1.0.0`（无 v 前缀） |
| `license` | 现有 license 字段 | `CC-BY-NC-SA-4.0` / `MIT` |
| `author` | 固定值 | `杨卫薪律师（微信ywxlaw）` |
| `homepage` | 固定值 | `https://github.com/cat-xierluo/legal-skills` |
| `source` | 固定值 | `https://github.com/cat-xierluo/legal-skills` |

### version 字段提取规则

CHANGELOG.md 中的版本号格式有三种，需要统一转换：

```markdown
## [1.3.1] - 2026-02-10    →  version: "1.3.1"
## [v1.3.0] - 2026-02-10   →  version: "1.3.0"
## v1.2.0 - 2026-02-21      →  version: "1.2.0"
```

**规则**：
1. 去掉 `## [` 和 `]` 包裹符号
2. 去掉 `v` 前缀
3. 保留三位语义化版本号（x.y.z）

## 发布流程

### 首次发布

```bash
# 1. 登录 ClawHub
clawhub login

# 2. 验证发布内容（dry-run）
clawhub sync --dry-run

# 3. 确认后执行发布
clawhub sync --all
```

### 后续更新

版本号从 CHANGELOG 第一行读取，`clawhub sync` 会自动处理版本递增：

```bash
# 更新所有 Skill（版本从 CHANGELOG 读取）
clawhub sync --all
```

### 逐个发布（特定 Skill）

```bash
clawhub publish skills/<skill-name> --version <x.y.z>
```

## 版本号管理规范

### 什么时候必须更新 version

| 场景 | 是否更新 | 原因 |
|------|---------|------|
| 首次发布 | ✅ 必须 | ClawHub 要求每个 Skill 有起始版本 |
| 发布了新功能 | ✅ 更新 CHANGELOG | 保持版本与变更记录一致 |
| Bug 修复 | ✅ 更新 CHANGELOG | 版本记录真实状态 |
| 文档修改 | ❌ 不需要 | 不算功能变更 |
| 格式调整 | ❌ 不需要 | 不影响功能 |

### 为什么不手动指定版本号

`clawhub sync` 的 `--bump` 参数会自动处理版本递增：
- 默认 `patch`：修复时使用（1.0.0 → 1.0.1）
- `minor`：新增功能时使用（1.0.0 → 1.1.0）
- `major`：破坏性变更（1.0.0 → 2.0.0）

**规则**：在 CHANGELOG 记录变更即可，版本号由脚本维护。

### clawhub sync 的版本行为

```
clawhub sync 的版本处理逻辑：

1. 检查本地 SKILL.md 的 version 字段
2. 检查 ClawHub 上已注册的版本
3. 如果本地 > 远程 → 发布新版本
4. 如果相同 → 跳过（无变更）
5. 如果本地 < 远程 → 报错（版本回退不允许）
```

**规则**：永远不要在 ClawHub 上手动降版本。

## CHANGELOG 格式要求

### 为什么格式很重要

`sync-versions.sh` 脚本从 CHANGELOG 第一行提取版本号。
- 标准格式 `## [x.y.z]` → 直接提取
- 非标准格式 → 提取失败，脚本跳过

### 推荐格式（无 v 前缀）

```markdown
## [1.0.0] - YYYY-MM-DD

### 新增
- 新功能描述

### 修复
- Bug 修复描述
```

### 历史格式兼容

脚本支持三种格式自动转换：

| CHANGELOG 写法 | 提取结果 | 状态 |
|---------------|---------|------|
| `## [1.3.1]` | `1.3.1` | ✅ 标准 |
| `## [v1.3.0]` | `1.3.0` | ✅ 兼容 |
| `## v1.2.0` | `1.2.0` | ⚠️ 不推荐 |

**规则**：新建 CHANGELOG 条目时使用 `## [x.y.z]` 格式（无 v 前缀）。

## Skill 版本清单

| Skill | 版本 | 说明 |
|-------|------|------|
| course-generator | 1.3.1 | |
| de-ai-polish | 1.0.0 | |
| douyin-batch-download | 1.8.0 | |
| funasr-transcribe | 1.2.0 | |
| git-batch-commit | 1.1.0 | |
| github-star-manager | 0.6.0 | |
| legal-proposal-generator | 0.1.0 | |
| legal-qa-extractor | 1.0.0 | |
| legal-text-format | 1.1.0 | |
| litigation-analysis | 1.3.0 | |
| md2word | 0.4.1 | |
| mineru-ocr | 1.0.1 | |
| minimax-image-understand | 0.1.0 | |
| minimax-web-search | 0.1.0 | |
| multi-search | 1.1.0 | |
| piclist-upload | 1.1.1 | |
| repo-research | 0.7.0 | |
| skill-architect | 1.3.0 | |
| skill-lint | 1.3.0 | |
| skill-manager | 1.2.0 | |
| svg-article-illustrator | 1.0.4 | |
| universal-media-downloader | 0.2.0 | |
| wechat-article-fetch | 1.2.0 | |

## 变更历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.0.0 | 2026-03-20 | 初始版本，包含适配规则、版本管理规范、CHANGELOG 格式要求 |
