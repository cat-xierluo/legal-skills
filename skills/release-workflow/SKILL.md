---
name: release-workflow
description: 本技能应在 GitHub 项目发布新版本时使用，覆盖版本号管理、CHANGELOG 同步、Release Notes 撰写、tag 创建、CI 构建监控、发布验证和历史清理全流程。适用于桌面应用、CLI 工具、Web 应用、库/SDK 等任何基于 GitHub 的软件项目。当用户提到"发布"、"release"、"打 tag"、"新版本"、"更新版本号"、"写 release notes"、"发布失败了"、"CI 挂了"时触发。不要用于非 GitHub 项目（如纯 GitLab / Gitea 项目）或无需 CI 的手动发布场景。
license: MIT License - 详见 LICENSE.txt
---

# Release Workflow

软件项目的全流程发布工作流。适用于 GitHub 上的任何类型项目。

## 适用场景

GitHub 项目的完整发布周期：从版本号确定到 CI 构建验证。CI 故障排查（`references/ci-troubleshooting.md`）和特定项目类型指南（`references/` 下各文档）作为发布流程的补充参考。

## 项目配置

`config/projects.yaml` 集中管理各项目的发布配置（仓库、平台、自动更新、排除产物等）。发布时先读取对应项目配置，按配置决定构建矩阵和预期产物。模板见 `config/projects.example.yaml`。

## 发布前检查

| 检查项 | 说明 |
|--------|------|
| 工作区干净 | `git status` 无未提交变更 |
| 版本号一致 | 所有版本号文件（package.json / Cargo.toml / pyproject.toml 等）与 CHANGELOG.md 最新条目一致 |
| CHANGELOG 已更新 | 包含目标版本的结构化条目 |
| CI 工作流存在 | `.github/workflows/` 中有 release 相关工作流且 tag 触发配置正确 |

任一条件不满足，先修复再继续。

## 发布流程

### 第 1 步：确定版本号

从用户处获取或从 CHANGELOG.md 读取目标版本号。

统一所有版本号文件（按项目类型选取）：
- Node.js 项目：`package.json` → `version`
- Rust 项目：`Cargo.toml` → `version`
- Python 项目：`pyproject.toml` → `version`
- 桌面应用：对应配置文件（如 Tauri 的 `tauri.conf.json`）
- CHANGELOG.md → 最新 `## [x.y.z]` 条目

版本号规则（SemVer）：

| 类型 | 示例 | 适用场景 |
|------|------|----------|
| PATCH | 0.3.7 → 0.3.8 | Bug 修复、小改进 |
| MINOR | 0.3.x → 0.4.0 | 新功能、向后兼容 |
| MAJOR | 0.x → 1.0.0 | 重大架构变更、破坏性改动 |

### 第 2 步：生成 Release Notes

信息来源有两个，必须综合使用：

**来源 1 — `CHANGELOG.md`**：结构化的变更分类（Added / Changed / Fixed 等）

**来源 2 — `git log`**：两个 tag 之间的 commit 历史，补充上下文和细节

```bash
# 获取上一个 tag
PREV_TAG=$(git describe --tags --abbrev=0 HEAD^ 2>/dev/null || echo "")

# 查看 commit 历史
git log ${PREV_TAG}..HEAD --oneline

# 查看详细变更（含 PR 链接）
git log ${PREV_TAG}..HEAD --format="- %s (%h)"
```

综合两个来源，按模板组织 Release Notes。模板和格式指南见 `references/release-notes-guide.md`。如果 `config/projects.yaml` 中存在 `release_notes.profile`，优先使用项目配置指定的结构；未配置时按项目类型选择默认结构。

### 第 3 步：提交并打 Tag

```bash
# 确保所有变更已提交
git status

# 打 tag
git tag "vX.Y.Z"

# 推送 tag 触发 CI
git push origin "vX.Y.Z"
```

如果有同名旧 tag（如发布失败后重试）：

```bash
git push origin :refs/tags/vX.Y.Z
git tag -d vX.Y.Z 2>/dev/null
git tag vX.Y.Z
git push origin vX.Y.Z
```

### 第 4 步：监控 CI 构建

```bash
# 查看构建状态
gh run list --limit 3

# 各平台 job 状态
gh run view <RUN_ID> --json jobs --jq '.jobs[] | "\(.name): \(.conclusion)"'

# 失败日志
gh run view <RUN_ID> --log-failed
```

项目类型的特定构建产物和验证方法，见 `references/` 下对应文档。

### 第 5 步：更新 Release Notes

CI 构建成功后，用第 2 步准备的草稿更新 GitHub Release：

```bash
gh release edit vX.Y.Z --repo <owner>/<repo> --notes "$(cat <<'EOF'
<Release Notes 内容>
EOF
)"
```

Release Notes 正文不要再写 `# <项目名> vX.Y.Z` 或其他重复版本标题；GitHub Release 页面自身已经显示标题，正文应直接从摘要、升级提示或 Highlights 开始。

### 第 6 步：验证

```bash
# 检查产物是否完整
gh release view vX.Y.Z --json assets --jq '.assets[].name'
```

对照 `config/projects.yaml` 中该项目的配置检查：
1. 预期产物是否齐全（根据 `platforms` 和 `auto_update` 推导）
2. `exclude_assets` 中列出的产物是否意外出现
3. 产物命名是否符合规范
4. Release Notes 是否符合 `release_notes.required_sections` 和 `release_notes.always_include` 约束

### 第 7 步：清理

- 删除失败的 Actions runs：`gh run delete <ID>`
- 清理旧的 draft release（如有）
- 确认镜像同步是否成功（如已配置）

## 特定项目类型指南

| 项目类型 | 参考文档 |
|----------|----------|
| Tauri 桌面应用 | `references/tauri-release.md` |

## 检查清单

发布完成后确认：

- [ ] 所有平台 / 矩阵构建全部成功
- [ ] GitHub Release 产物完整
- [ ] Release Notes 已更新，且正文没有重复的版本标题
- [ ] 镜像同步成功（如已配置）
- [ ] 旧的失败 Actions runs 已清理
- [ ] 项目文档已更新（TASKS / DECISIONS / CHANGELOG 等）
- [ ] tag 指向正确的 commit
