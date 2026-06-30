---
name: release-workflow
description: 本技能应在 GitHub 项目发布新版本时使用，覆盖版本号管理、CHANGELOG 同步、Release Notes 撰写、tag 创建、CI 构建监控、发布验证和历史清理全流程。适用于桌面应用、CLI 工具、Web 应用、库/SDK 等任何基于 GitHub 的软件项目。当用户提到"发布"、"release"、"打 tag"、"新版本"、"更新版本号"、"写 release notes"、"发布失败了"、"CI 挂了"、"Actions 配额告急"、"短时间内多次发版"、"monorepo"、"批量打包"、"多 skill 发布"、"skill zip"时触发。也用于拒绝把 release 当作 CI 验证机制（"打 tag 看一下"）的反模式场景。不要用于非 GitHub 项目（如纯 GitLab / Gitea 项目）或无需 CI 的手动发布场景。
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

## ⚠️ Release ≠ 测试 — 强制约束

**打 tag / 创建 GitHub Release 是把版本号给真实用户**，不是 CI 验证机制。**把 release workflow 当作"看 CI 跑没跑通"或"我下载个 artifact 自己测一下"是反模式，必须禁止。**

### 为什么是绝对规则

- **Actions 配额是有限共享资源**。单次跨平台 release（macOS × N + Windows + Linux）通常消耗 300-600 配额分钟，macOS runner 是 10× 费率，贡献最大。
- **错把 release 当测试的隐性成本**：
  - GitHub Release 一旦创建（即使是 draft）就被计入资产历史，污染 release feed
  - tag 推送后 commit 被人看到会误以为已发布
  - 自动更新用户可能在升级检查时看到不稳定的版本
  - 配额快速耗尽，真正紧急的 hotfix 反而跑不动 CI
- **过去能这么干不代表现在该这么干**。GitHub 免费配额调整、macOS runner 涨价都发生过，使用模式必须随成本变化更新。

### 禁止的反模式

| 反模式 | 表现 | 为什么错 |
|--------|------|----------|
| **把 tag 当 smoke test** | "我改了一行，打个 tag 看看 CI 跑不跑得通" | 一次 release 吃掉 300+ 配额分钟，5 次测试 = 一月配额清零 |
| **用 release 验证构建产物** | "我想看 .dmg 长什么样，必须跑 release" | 应该用专门的 preview / draft build workflow（见下） |
| **同一天 / 24h 内发多个 patch** | v0.3.16 / 17 / 18 一天内连发，各是同一个 bug 的连续小修 | 全部攒到下次一起发，成本立省 60%+ |
| **draft release 当"先跑一次试试"** | "我先 draft release 看 artifact 行不行" | draft 一样跑完整 CI，一样消耗配额，一样污染 release 历史 |
| **单平台 dry-run 验构建** | "先跑 Linux dry-run 看看，不发全平台" | dry-run 一样消耗 CI 时间，开了口子就停不下来；改走 preview workflow |
| **小改动发 patch** | "我改了 typo / 改了一行文档，必须 vX.Y.Z" | 纯 typo / 文档小改 / 单文件改动不构成发版理由，合并到下个有实质内容的版本 |
| **"已经打 tag 了，跑都跑了"** | "v0.3.22 tag 已经推上去了，CI 反正也在跑" | "已经做了"不是继续做的理由；记录这次浪费并阻止下次重复 |

### 正确做法

**A. 想验证 CI 跑不跑得通 / 看构建产物长什么样？**

- 用 `pull_request` 触发的 preview workflow（可只跑 ubuntu / 单一平台，几十分钟完成）
- 或在 main 上用 `workflow_dispatch` 手动触发 dry build，**不**触发 release workflow
- 这两种都不消耗 macOS 高倍率配额，artifact 只对自己可见

**B. 真的有用户能拿到的修复要发？**

- 等攒到 3-5 个实质修复（bug fix / feature / 性能 / 兼容性改动）
- 一次性打 tag 发版，**只发一次**
- CHANGELOG 必须有结构化条目，不能空
- 距离上次 tag 至少 24 小时（防止把单个 hotfix 拆成多个 patch）

### 打 tag 前强制自检（AI 不得跳过）

打 tag 之前，**必须回答下面 5 个问题**。AI 代理被请求发布新版本时，必须**主动**逐条打印结果让用户确认，禁止直接进入打 tag 流程。

1. 这是给真实用户装的，还是只给自己看 artifact？
2. CHANGELOG 已经有结构化的本版本条目（不是空、不是单行 typo）？
3. 距上次 tag ≥ 24 小时？
4. 本次累计有 ≥ 1 个实质修复 / 特性 / 改动（纯文档 / typo / 单行 README 修改不算）？
5. 如果上述任一不满足：能合并到下次发版吗？

**任一答"否"或"不知道"：不要打 tag，改走 preview workflow 或合并到下次。**

**AI 代理实操规则**：用户说「发布新版本」「打 tag」「release」时，AI 必须先在响应中**显式列出 5 问的答案**，等用户确认后再继续。这是硬约束，不允许跳过——v0.4.0 发布时 AI 跳过此步骤导致 3 次重打 tag 才修好，是真实教训。

### 借口反驳表

| 借口 | 现实 |
|------|------|
| "我就看一眼，tag 一下马上回滚" | tag 推送已经触发了完整 CI，回滚 tag 不能退款 Actions 分钟 |
| "用户催着要" | 用户不知道你的 Actions 配额，告诉 ta 合并到明天的成本和时间，让 ta 选 |
| "反正之前都这么干" | 之前能用不等于现在合理，这正是 91% 配额的直接成因 |
| "只有 release workflow 跑完整矩阵" | 加一个 preview workflow（成本是 release 的 10-20%），不要用 release 凑合 |
| "draft release 不算正式发布" | draft 一样跑完整 CI、一样消耗配额、一样污染 release 历史 |
| "小改动发 patch 很常见" | 纯 typo / 文档 / 单行不构成发版理由，合并到下个有实质内容的版本 |
| "我已经打 tag 了，跑都跑了" | "已经做了"不是继续做的理由；记录这次浪费，阻止下次重复 |
| "单平台先 dry-run 一下" | dry-run 一样消耗 CI 时间，开了口子就停不下来；改走 preview workflow |
| "这次不一样，这次真的需要发" | SemVer 的 patch 版本本来就允许累积；下次发版不是更优解吗 |

### 红灯（看到任一就停）

- 同一工作日内想发第二次 tag
- 距上次 tag < 24 小时
- CHANGELOG 没有本版本的结构化条目就想发
- 想用 "draft release" 当测试
- 想用 `workflow_dispatch` 触发 release workflow 当测试（应该触发独立的 preview workflow）
- 本次只有 typo / 文档 / 单行修改
- macOS 10× 配额当月累计用量已 > 70%

**以上任一出现：删掉 tag（如已打），改走 preview workflow 或合并到下次。**

## 🔥 修复 hotfix 与 CI retry 边界（关键）

patch 版本（X.Y.Z+1）可以是 **新功能累积**，也可以是 **hotfix 单一修复**。区分清楚才能避免「把 release 当测试」反模式。

### 何时属于「hotfix 真实修复」（可以重打 tag）

- 第一次 release 后用户**实际收到 broken build**（自动更新坏 / 安装失败 / 启动崩溃）
- CI 日志明确指向**代码层 bug**（编译错、依赖配置错、产物链断裂）
- 每次重打 tag 都**有可验证的 commit 推进**（修一行、改一个配置、新增测试）

判定信号：`gh run view --log-failed` 输出包含具体 error line（不是单纯的 `Timeout` / `Resource exhausted` 这种 transient 错误）。

### 何时属于「把 release 当测试」（禁止重打 tag）

- 单纯想看 CI 跑没跑通、看 artifact 长什么样
- 上一次 build 失败但**没看失败原因**就直接重打
- 第三次以上重打同一个版本号（按成本曲线，超过 3 次几乎都在反复折腾 transient）

### transient vs 真实 bug 的快速判定

```
build job 失败：
  - 输出含 E0599 / Cargo compile error / 链接错误 → 真实代码 bug，修代码再重打
  - 输出含 "Timeout" / "Resource exceeded" / "Killed" → transient，可直接重试

publish job 失败：
  - 输出 "Missing signatures" + 产物清单缺 sig → 检查 includeUpdaterJson + bundle.targets（详见 tauri-release.md 红线 8）
  - 输出 "Signature not found for the updater JSON. Skipping upload..." → tauri-action 跳过整批 updater，检查 build 产物目录
  - 输出 "Unable to download" / "rate limit" → transient

最佳实践：先 `gh release view <tag> --json assets` 看产物清单，再决定修代码还是重打 tag。
```

### 修复 hotfix 的标准动作序列

1. 删旧 tag + draft release（如已创建）：`git push origin :refs/tags/vX.Y.Z` + `gh release delete vX.Y.Z --yes`
2. 在 main 上 commit 修复（**必须包括版本号同步**——commit history 必须含 4 处版本号文件：package.json / Cargo.toml / tauri.conf.json / pyproject.toml 等）
3. 重打 tag 指向修复 commit
4. 推 tag 触发 CI
5. **重打 tag 总次数上限 3 次**（含初始 publish）。超过说明根因判断有误，应停下来重新调查。

## 模式 B:monorepo 多组件批量发布

适用:一个仓库下有 N 个独立可发布的子项目(skill 集、CLI 工具集、npm 包集等),希望一次 tag 同时发布所有子项目的 zip,但保留各自的版本号。

**前置**:对应项目需在 `config/projects.yaml` 有 `type: monorepo-skills` 条目,并配套 `scripts/build-zips.sh` + `scripts/release-monorepo.sh` 两个脚本(完整 SOP 见 `references/monorepo-release.md`)。

**与模式 A 的关键差异**(相对单仓库单应用):

| 维度 | 模式 A(单应用) | 模式 B(monorepo) |
|---|---|---|
| tag 频率 | 每应用 1 tag | 每发布轮次 1 tag(常用 CalVer) |
| zip 命名 | `<App>-<ver>.<ext>` | `<skill>-<semver>.zip` |
| Release Notes | 单应用 changelog | N 个 skill changelog 合并 |
| 验证 | 平台矩阵(win/mac/linux) | 子项目数量清单 + 关键项抽查 |
| 回写 README | 不适用 | 是(把 latest URL 写进表格) |

**核心流程**(详见 `references/monorepo-release.md`):

1. 读 `projects.yaml` 的 `<project-key>` 条目,获取 `skills_root`、`output_dir`、`exclude_globs`
2. 跑 `build-zips.sh <tag>` 生成 `<output_dir>/<item>-<semver>.zip`
3. 打 tag、推 tag
4. GitHub Actions 自动:上传 zip + 触发 update-readme.yml
5. update-readme.yml 调 GitHub API 拿 assets 列表,替换 README 里的占位 URL
6. 验证 release 页 assets 数量 = 期望子项目数

不要用于:单应用桌面/CLI/Web 项目(用模式 A 上文 7 步流程)、跨仓库分发(用 subtree-publish skill)。

---

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

# ⚠️ 必须校验：tag 指向的 commit 包含版本号同步 commit。
# 重打 hotfix 时常见坑：只改了 release.yml 没把 4 处版本号文件也升到 X.Y.Z，
# 导致产物文件名仍带旧版本号（如 Folia_0.4.0_* 但 tag 是 v0.4.1）。
git show vX.Y.Z --stat | head -20
# 确认 package.json / Cargo.toml / tauri.conf.json / CHANGELOG.md 都在 commit 里

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
5. **产物完整矩阵对照**（带自动更新项目必查）：见下表，对照产物清单逐行打勾

| 平台 | 安装包 | updater binary | .sig | latest.json entry |
|------|--------|---------------|------|-------------------|
| darwin-aarch64 | `App_X.Y.Z_aarch64.dmg` | `App_aarch64.app.tar.gz` | `App_aarch64.app.tar.gz.sig` | `darwin-aarch64` |
| darwin-x86_64 | `App_X.Y.Z_x64.dmg` | `App_x64.app.tar.gz` | `App_x64.app.tar.gz.sig` | `darwin-x86_64` |
| windows-x86_64 | `App_X.Y.Z_x64-setup.exe` | （NSIS 自带） | `App_X.Y.Z_x64-setup.exe.sig` | `windows-x86_64` |

macOS .app.tar.gz / .sig 文件名**不带版本号前缀**（tauri-action 历史约定），Windows .exe.sig 带版本号。任何一项缺失都让该平台用户升不到 vX.Y.Z——**不要 publish draft release**，先修配置 / 代码再重打 tag。

### 第 7 步：清理

- 删除失败的 Actions runs：`gh run delete <ID>`
- 清理旧的 draft release（如有）
- 确认镜像同步是否成功（如已配置）

## 特定项目类型指南

| 项目类型 | 参考文档 |
|----------|----------|
| Tauri 桌面应用 | `references/tauri-release.md` |

## 检查清单

**打 tag 前（强制）** — 见上文 `## ⚠️ Release ≠ 测试 — 强制约束`：

- [ ] 这是给真实用户装的，不是只给自己看 artifact
- [ ] CHANGELOG 有结构化的本版本条目
- [ ] 距上次 tag ≥ 24 小时
- [ ] 本次有 ≥ 1 个实质修复 / 特性 / 改动
- [ ] 已通过五问自检

**发布完成后确认：**

- [ ] 所有平台 / 矩阵构建全部成功
- [ ] GitHub Release 产物完整
- [ ] Release Notes 已更新，且正文没有重复的版本标题
- [ ] 镜像同步成功（如已配置）
- [ ] 旧的失败 Actions runs 已清理
- [ ] 项目文档已更新（TASKS / DECISIONS / CHANGELOG 等）
- [ ] tag 指向正确的 commit
