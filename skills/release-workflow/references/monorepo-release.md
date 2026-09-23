# Monorepo 多子项目批量发布 SOP

## 适用场景

- 仓库内含 N 个独立可发布的子项目(skill、CLI、npm 包、binary 等)
- 每个子项目自己的 `CHANGELOG.md` 维护 semver(如 `v1.3.1`)
- 希望一次 `git push tag` 同时发布所有子项目的 zip
- 希望把仓库内符号链接定义的专家套件展开为自包含 zip
- README 表格含「下载(latest)」列,自动同步到 GitHub Release

## 端到端流程

### 1. 准备工作(一次性)

- [x] 仓库根 `.gitattributes` 加 `export-ignore` 规则
- [x] `config/projects.yaml` 加项目条目(`type: monorepo-skills`)
- [x] `references/release-notes-guide.md` 加 `monorepo-skills` profile
- [x] `SKILL.md` description 加 monorepo 触发词 + 「模式 B」章节
- [x] `scripts/build-zips.sh` + `scripts/release-monorepo.sh` 已就位
- [x] 启用专家套件时，`validate-expert-suites.py` + `build-suite-zips.sh` 已就位
- [x] `.github/workflows/release.yml` 与 `update-readme.yml` 已部署到仓库根

### 2. 发布前(每次)

1. 确认各子项目 `CHANGELOG.md` 头部 semver 已更新
2. 确认 README 的「最近更新」表格已记录本次变更
3. 确认工作区干净(`git status` 无未提交变更)
4. 本仓库没有顶层插件版本号；只需同步各 Skill 的版本、CHANGELOG、根 README 与实际启用的发布渠道

### 3. 发布(每次)

```bash
cd /path/to/<repo>
bash <path-to-release-workflow>/scripts/release-monorepo.sh <YYYY.MM.DD-tag>
```

**一气呵成完成 7 步**:

1. `build-zips.sh <tag>` 遍历 `skills/`(或配置的根目录),按 `CHANGELOG.md` 头部 semver 命名单 Skill zip → `<output_dir>/`
2. 如配置 `expert_suites_root`，校验套件链接和 README 后，由 `build-suite-zips.sh <tag>` 从 Git tree 展开成员，生成 `suite-<id>-<semver>.zip`
3. 完成 Release 五问后，仅从与 `origin/main` 完全一致的干净 `main` 创建 annotated tag，并核验 tagger 与目标 commit
4. 把已核验的不可变 tag object 精确推送到目标 ref，触发 `.github/workflows/release.yml`
5. Actions 构建两类 zip,用 `softprops/action-gh-release` 上传 `<output_dir>/*.zip`,并生成含「专家套件」清单节的 Release Notes
6. `gh run watch --exit-status` 等 Actions 完成并核对资产总数 = 单 Skill ZIP 数 + 套件 ZIP 数
7. **README 回写(三层,均调同一份 `scripts/update-readme.py`,幂等)**:
   - `release.yml` 末尾内嵌步骤:checkout main → 同步根 README 与 `expert-suites/*/README.md` 下载链接 → commit + push(主路径,CI 发版)
   - `update-readme.yml` 在 release workflow 成功后通过 `workflow_run` 触发兜底(也可 `workflow_dispatch` 手动补跑);checkout 显式 `ref: main`
   - `release-monorepo.sh` 末尾本地调用(本地驱动路径)

> 设计取舍:README 回写不走 `on: release` 跨 workflow 事件——release.yml 用内置
> GITHUB_TOKEN 创建 Release,GitHub 防递归机制下该事件**不会**级联触发其他 workflow
> (`update-readme.yml` 的 `release: published` 因此从未自动生效,v1.4.0 首次观察到,
> v1.5.1 定位根因)。主路径内嵌在 release.yml 末尾 100% 保证;`workflow_run` 兜底
> 以 release workflow 的成功终态为触发源;本地发布脚本不直接提交、推送 main。

### 4a. monorepo-skills README 结构约定（回写的通用性边界）

`update-readme.py` 的表行回写**不是仓库个性化补丁，而是本类型的项目约定**：凡
`type: monorepo-skills` 的项目，根 README 技能表须遵循以下结构，回写脚本按此实现；
新项目按约定书写即可复用全部回写能力（链接刷新 + 版本列对齐 + 改名死链自愈）。

1. **HTML 技能表**：每个技能一行 `<tr>`，行内以 `href="skills/<skill-name>/"` 声明技能名
   （回写按此**行内名**映射资产，不信任链接里的旧 slug）；版本列 `<td>vX.Y.Z</td>`
   紧邻下载列 `<td><a href=".../<skill>-<semver>.zip">下载</a></td>`（版本列会被
   自动对齐到 zip 实际版本，`vA.B.C→vX.Y.Z` 区间写法整体替换）。
2. **独立仓库行**：下载链接域名非本仓库的行（配"独立仓库"列）整行不动。
3. **套件 README（可选）**：成员表行以 `](../skills/<name>/)` 声明成员名，成员
   下载链接按行内成员名映射；正文散链（blockquote 整套下载等）按链接自身 slug 映射。

> 分层原则：`projects.yaml` 的 `type: monorepo-skills` 是通用/个性的分界——脚本行为
> 对本类型所有项目一致；确属单仓库的差异（如 intro 文案）走 `notes:` 配置，不进脚本。

### 4b. 已知摩擦与处置（长期 PR 的两条规律）

**摩擦一：main 上 Skill 升版本 → 套件成员链接过时。**
长期 feature PR 每次 merge main 时，若 main 期间有 Skill 升版本（CHANGELOG 头部变化），
分支里的 `expert-suites/*/README.md` 成员下载链接就会落后于当前版本，被
`validate-expert-suites.py` 拦截（它按 CHANGELOG 当前 semver 校验——这是设计行为，
不是误报）。处置：在 PR 分支跑
`python3 skills/release-workflow/scripts/align-suite-links.py`（`--dry-run` 可预览），
然后重跑 validate 确认 `PASS`。链接版本短暂超前于已发布 zip 属预期：
`latest/download` 占位在下次发版后生效。

**摩擦二：merge main 时 README 版本列冲突，一律取 PR 侧。**
main 侧版本列是**已发布快照**（对齐最近一次 Release 的实际 zip 版本，由
`update-readme.py` 自动回写）；PR 侧是**待发版时态**（新版本号 + `latest/download`
占位链接，等本 PR 合入后的下次发版回写）。两者必然不同值，冲突时取 PR 侧——
这是"版本列=下载版本"约定的时态推论，不是偏好。

**摩擦三：新技能未同步 README 表格行——回写无法自愈。**
`update-readme.py` 只能改写已有表行，不能补行：新技能上传时若漏维护 README
技能表格（AGENTS.md 已要求），其 zip 进了 Release 但 README 无下载入口。
用 `scripts/check-readme-coverage.py` 核对（对照最新 Release 资产与 README 行，
独立仓库下载行豁免；支持 `--assets-json` 离线）。缺行属内容维护：按现有行
结构补 `<tr>`（技能链接列/分类/描述/许可证/版本/下载链接）,并在
`skills/<name>/` 的 SKILL.md 与 CHANGELOG 就绪后提交。

> 附注：本仓库的 Skill Lint Harness / Orchestration CI 均有 `paths:` 过滤，
> release-workflow 路径的 PR 不会触发它们——合并前的等价验证（py_compile、
> workflow YAML 校验、`security_scan audit`、相关单测）在本地完成。

### 4. 发布后(每次)

- 检查 release page:`https://github.com/<owner>/<repo>/releases/tag/<tag>`
- 抽查 1-2 个 zip:`curl -L -o /tmp/test.zip <URL>; unzip -l /tmp/test.zip | head -20`
- 检查 README「下载(latest)」列点击能否下载
- **README 结构性同步核查**:`python3 skills/release-workflow/scripts/check-readme-coverage.py <owner>/<repo>`
  通过(无缺行/缺链接);抽查分节归属——通用工具类技能(报销整理/签到/复盘等)不得留在
  「法律专业应用」节(v2026.08.06–09.21 期间 invoice-organizer 曾错位、15 个技能缺行,
  均为发版环节无人负责 README 结构性维护所致)
- 通知用户(沟通用业务语言,不说"CI 过了")

## 关键设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| tag 频率 | CalVer,每周/每月一次 | 子项目用户不期望每天有新版本 |
| zip 命名 | `<item>-<semver>.zip` | 用户能直接看到版本;CHANGELOG 是真理来源 |
| 套件 zip 命名 | `suite-<id>-<semver>.zip` | 与单 Skill 资产区分，仍能从 CHANGELOG 解析版本 |
| zip 内路径 | `<name>/...`(用 git archive + tar --strip-components=1 去 `skills/` 前缀) | 用户解压后直接得到 `<name>/` 文件夹,复制到目标 skills 目录 |
| README 列 | 两列:版本 + 下载(latest) | 保留语义可读性 + 一键下载 |
| 包排除 | `.gitattributes` export-ignore | git 原生,跨平台一致,不依赖 .gitignore |
| README 回写 | Actions 触发,占位 URL 模式 | 用户无需 push README;Actions 自动同步 |

## 已知限制 / 后续可优化

- **Skill 根目录 Symlink 跳过**:指向外部目录的 symlink 不作为单 Skill 打包(避免外部污染)
- **专家套件 Symlink 只作成员指针**:必须严格指向当前仓库 `skills/<id>`；套件 ZIP 内展开为真实目录
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
- 首批 5 个专家套件通过仓库内相对符号链接复用公开 Skill
- 单 Skill zip 与 `suite-*.zip` 上传到同一 release
- README 表格 50 个 skill 全部有 download 列(7 个独立仓库 skill 除外但仍打 zip)
- `projects.yaml` 配置:

  ```yaml
  legal-skills:
    repo: cat-xierluo/legal-skills
    type: monorepo-skills
    skills_root: skills
    expert_suites_root: expert-suites
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

其他项目只发布单组件时，复制 `build-zips.sh` / `release-monorepo.sh` 即可；启用专家套件时，再复制校验与套件构建脚本并配置 `expert_suites_root`，无需修改 release-workflow skill 本身。
