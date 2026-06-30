# Monorepo 多子项目批量发布 SOP

## 适用场景

- 仓库内含 N 个独立可发布的子项目(skill、CLI、npm 包、binary 等)
- 每个子项目自己的 `CHANGELOG.md` 维护 semver(如 `v1.3.1`)
- 希望一次 `git push tag` 同时发布所有子项目的 zip
- README 表格含「下载(latest)」列,自动同步到 GitHub Release

## 端到端流程

### 1. 准备工作(一次性)

- [x] 仓库根 `.gitattributes` 加 `export-ignore` 规则
- [x] `config/projects.yaml` 加项目条目(`type: monorepo-skills`)
- [x] `references/release-notes-guide.md` 加 `monorepo-skills` profile
- [x] `SKILL.md` description 加 monorepo 触发词 + 「模式 B」章节
- [x] `scripts/build-zips.sh` + `scripts/release-monorepo.sh` 已就位
- [x] `.github/workflows/release.yml` 与 `update-readme.yml` 已部署到仓库根

### 2. 发布前(每次)

1. 确认各子项目 `CHANGELOG.md` 头部 semver 已更新
2. 确认 README 的「最近更新」表格已记录本次变更
3. 确认工作区干净(`git status` 无未提交变更)
4. **不需要**手动改顶层版本号(如 `.claude-plugin/plugin.json` 与本流程无关)

### 3. 发布(每次)

```bash
cd /path/to/<repo>
bash <path-to-release-workflow>/scripts/release-monorepo.sh <YYYY.MM.DD-tag>
```

**一气呵成完成 6 步**:

1. `build-zips.sh <tag>` 遍历 `skills/`(或配置的根目录),按 `CHANGELOG.md` 头部 semver 命名 zip → `<output_dir>/`
2. `git tag <YYYY.MM.DD-tag>` 打 tag
3. `git push origin <YYYY.MM.DD-tag>` 推 tag,触发 `.github/workflows/release.yml`
4. Actions 跑 `build-zips.sh`,用 `softprops/action-gh-release` 上传 `<output_dir>/*.zip`
5. `gh run watch --exit-status` 等 Actions 完成
6. **`update-readme.py` 内嵌调用**:从 GitHub API 拿最新 release 的 assets,
   用真实 `browser_download_url` 替换 README 表格占位,
   若有变更自动 commit + push(无需依赖 `.github/workflows/update-readme.yml` 跨 workflow 事件)

> 设计取舍:`update-readme` 逻辑优先内嵌在 `release-monorepo.sh` 末尾(单脚本完成全流程),
> `.github/workflows/update-readme.yml` 仍保留作为兜底(给直接用 `workflow_dispatch` 触发 release 的用户)。
> 首次 release 出现过 `.github/workflows/update-readme.yml` 未自动触发的事件路由问题,内嵌后 100% 保证。

### 4. 发布后(每次)

- 检查 release page:`https://github.com/<owner>/<repo>/releases/tag/<tag>`
- 抽查 1-2 个 zip:`curl -L -o /tmp/test.zip <URL>; unzip -l /tmp/test.zip | head -20`
- 检查 README「下载(latest)」列点击能否下载
- 通知用户(沟通用业务语言,不说"CI 过了")

## 关键设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| tag 频率 | CalVer,每周/每月一次 | 子项目用户不期望每天有新版本 |
| zip 命名 | `<item>-<semver>.zip` | 用户能直接看到版本;CHANGELOG 是真理来源 |
| zip 内路径 | `<skills_root>/<name>/...`(不设 prefix) | 用户解压后看到子目录,直接复制到自己的目标目录 |
| README 列 | 两列:版本 + 下载(latest) | 保留语义可读性 + 一键下载 |
| 包排除 | `.gitattributes` export-ignore | git 原生,跨平台一致,不依赖 .gitignore |
| README 回写 | Actions 触发,占位 URL 模式 | 用户无需 push README;Actions 自动同步 |

## 已知限制 / 后续可优化

- **Symlink 子项目跳过**:指向外部目录的 symlink 不打包(避免重复或外部污染)
- **无 CHANGELOG / 无 semver 的子项目跳过**:首次发布前需补 CHANGELOG
- **并发发布**:CalVer 频率下基本不会撞车,但建议在 `release.yml` 加 `concurrency:` 控制
- **CI 配额**:`gh release upload` 1000 asset 上限、单个 2GiB,目前远低于

## 与现有 7 步流程的关系

模式 B(本文件)与模式 A(单应用 7 步)是**并列**关系:

- 模式 A:单仓库单应用(桌面应用 / CLI / Web / 库),`type: tauri` + `references/tauri-release.md` build matrix
- 模式 B:monorepo 多子项目,`type: monorepo-skills` + `scripts/build-zips.sh`

两者入口都在 `SKILL.md`,通过项目 `type` 字段路由,互不干扰。同一仓库若同时存在两类项目,可分别配 `projects.yaml` 的不同 key。

## 实例:legal-skills 项目

`cat-xierluo/legal-skills` 是模式 B 的典型用例:

- `skills/` 根目录下 50 个独立 skill,各自维护 semver
- 6 个 symlink skill(hatch-pet、myagents-cli 等)被自动跳过
- 50 个 zip 上传到同一 release
- README 表格 50 个 skill 全部有 download 列(7 个独立仓库 skill 除外但仍打 zip)
- `projects.yaml` 配置:

  ```yaml
  legal-skills:
    repo: cat-xierluo/legal-skills
    type: monorepo-skills
    skills_root: skills
    output_dir: pack-skills
    exclude_globs:
      - "**/archive/**"
      - "**/downloads/**"
      - "**/output/**"
      - "**/DECISIONS.md"
      - "**/TASKS.md"
      - "**/.claude/**"
    tag:
      scheme: calver
      format: "vYYYY.MM.DD"
      example: v2026.06.30
  ```

- 跳过归档的 skill:`SKIP_ARCHIVED="skill-architect repo-research" bash build-zips.sh ...`

其他项目接入模式 B 时,只需复制 build-zips.sh / release-monorepo.sh 两个脚本 + 在 `projects.yaml` 加自己的条目即可,无需修改 release-workflow skill 本身。