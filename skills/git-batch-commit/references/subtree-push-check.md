# Subtree 推送检查（工作流第6步）

> **核心规则：按下文「配置解析」命中登记（按仓库个性化配置或默认 `skills/subtree-publish/config/subtree-skills.json`）才执行——未命中则静默跳过，不输出任何提示。**

> **⚠️ 能力边界披露**：本步骤会把子树内容**推送到独立 remote 仓库**，超出"仅提交"职责，**推送前必须获得用户显式确认**；用户未确认时一律不推送。详细披露见 SKILL.md「所需权限与能力边界」。

完成 Git 提交后（或按登记的触发时点），检查本次提交是否涉及已注册的 subtree 子项目。

## 配置解析（先于触发条件，命中即用其参数）

1. **按仓库登记（个性化）**：检查本技能 `config/subtree-repos.yaml`（模板见 `config/subtree-repos.example.yaml`）。以当前仓库根目录（`git rev-parse --show-toplevel`）的目录名匹配顶层键；条目带 `path` 时须与绝对路径一致，防止同名仓库误匹配。登记项可定制：
   - `config_path`：目标仓库内的 subtree 登记清单路径（下方触发条件①改为检查该文件；清单内 `prefix` 字段/条目 `remote` 字段优先于本处 `prefix` 与默认 remote 命名）
   - `prefix`：子目录前缀（默认 `skills`）
   - `trigger`：`after-commit`（默认，提交后即检查）或 `after-merge-to-main`（PR 流程仓库——批量提交发生在特性分支时**不提示**，待 PR 合入 main 后再提示，防止把未合并分支内容派发到独立镜像）
   - `push_command`：用户确认后的推送入口（优先；通常是目标仓自带守卫的脚本，如 dsh-plugins 的 `bash scripts/subtree-push.sh --auto`）
2. **默认（legal-skills 布局）**：仓库内存在 `skills/subtree-publish/config/subtree-skills.json` 时按本文件原流程执行（`prefix` 取该文件字段，remote 为 `<name>-standalone`）。
3. 两者皆未命中：静默跳过。

> 首例登记：dsh-plugins（`trigger: after-merge-to-main`、`push_command: bash scripts/subtree-push.sh --auto`、清单 `config/subtree-standalone.json`、`prefix: plugins`）。

## 触发条件

1. **配置文件存在**（路径以配置解析结果为准；默认为 `skills/subtree-publish/config/subtree-skills.json`）
   - **不存在则静默跳过，不提示用户**
   - `trigger: after-merge-to-main` 且当前不在 main 分支时同样静默跳过，留待合入后检查

2. **提交涉及已注册的子目录**
   - 读取登记清单中的 `prefix` 和子项目列表
   - 获取本次提交涉及的文件列表（`git diff --name-only HEAD~1 HEAD`，或批量提交时使用最后一次 commit）
   - 检查是否有文件路径以 `<prefix>/<skill-name>/` 开头
   - 如果命中，收集所有命中的 skill 名称

3. **remote 已配置**
   - 检查是否存在对应 remote（默认 `<name>-standalone`，登记清单各项可用 `remote` 字段覆盖，如 dsh-plugins 用 `contract-copilot`）
   - 如果 remote 不存在，说明该子项目尚未完成首次注册，跳过

## 提示与执行

满足触发条件时，向用户提示：

```
本次提交涉及已注册的 subtree 子项目：<name1>, <name2>
是否推送到独立仓库？

选项：
  y - 推送所有命中的子项目
  n - 跳过，暂不推送
  s - 选择性推送
```

用户确认后：登记了 `push_command` 时执行该命令（一条命令覆盖全部命中项，脚本自带分支/一致性守卫）；否则对每个命中的子项目执行：

```bash
git subtree push --prefix=<prefix>/<name> <remote> main
```

用户选择 `s` 时，逐个询问是否推送。

## 失败处理

- 推送失败时仅显示警告信息
- non-fast-forward 失败通常意味着独立仓被直接修改过——提示用户回主仓流程处理，**不要 force**
- 不影响 Git 提交结果
- 继续处理其他子项目

## 示例场景

| 场景 | 配置解析 | 提交涉及子目录 | remote 存在 | 结果 |
|------|----------|---------------|-------------|------|
| 正常推送（默认布局） | 默认配置存在 | 是 | 是 | ✅ 提示用户推送 |
| 按仓库登记推送 | subtree-repos.yaml 命中 | 是 | 是 | ✅ 提示，确认后执行登记的 push_command |
| after-merge-to-main 未到时点 | 命中但当前在特性分支 | 是 | 是 | ❌ 静默跳过（合入 main 后再检查） |
| 未涉及子目录 | 命中 | 否 | - | ❌ 静默跳过 |
| 配置未命中 | 均不存在 | - | - | ❌ 静默跳过 |
| 首次注册未完成 | 命中 | 是 | 否 | ❌ 跳过（提示用户先完成首次注册） |
