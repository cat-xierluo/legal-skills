# Legal Skills 专家套件设计与发布方案

- 状态：`DRAFT`
- 日期：2026-09-03
- 适用仓库：`cat-xierluo/legal-skills`

## 1. 核心定义

Legal Skills 第一阶段的“专家套件”定位为一个面向使用者的策展与分发集合：

- 围绕一个法律工作或 Skill 工程场景，选择一组相关 Skill；
- 在一个 README 中说明场景、成员、用途和下载方式；
- 在仓库中通过相对符号链接引用真实 Skill；
- 在 GitHub Release 中生成一个包含全部成员 Skill 的自包含 ZIP；
- 用户既可以下载整套，也可以通过 README 单独下载某个 Skill。

专家套件第一阶段不承担运行时编排，不要求 Agent 识别新的 Suite 协议，也不改变单个 Skill 的触发和执行方式。

```text
Skill             最小可复用能力单元
Expert Suite      面向场景的 Skill 选择与下载集合
Release ZIP       Expert Suite 的自包含分发产物
Workflow / Agent  未来如有需要，另行设计运行时编排
```

README 可以给出建议使用顺序，但这只是用户指引，不是机器执行合同。现有 `docs/SKILL-ORCHESTRATION-GUIDE.md` 和 `docs/SKILL-HANDOFF-GUIDE.md` 继续管理真正的跨 Skill 工作流，不塞进专家套件第一阶段。

## 2. 目标与非目标

### 2.1 目标

- 让用户从业务场景出发选择一组 Skill；
- 让用户只下载一个 ZIP 就能取得整套 Skill；
- 保留每个 Skill 的独立下载入口；
- 保证 Skill 源码仍只在 `skills/<id>/` 维护一份；
- 允许同一个 Skill 同时出现在多个专家套件；
- 利用现有 monorepo Release 能力自动构建和上传套件 ZIP；
- 让专家套件目录对人直观，对构建脚本也足够确定。

### 2.2 非目标

第一阶段不做：

- 不创建 `suite.yaml`、`suite.json` 或 README frontmatter；
- 不创建 `suite.lock.json` 或套件安装注册表；
- 不默认创建 `references/`；
- 不建立套件嵌套、继承或 `includes`；
- 不创建 Suite Agent 或套件入口 Skill；
- 不自动编排成员 Skill；
- 不把私有 Skill、Customer Skill 或仓库外 Skill 打入公开套件；
- 不改变成员 Skill 的许可证；
- 不用正式 Release 测试打包逻辑。

如果未来真实使用证明需要运行时编排，再基于独立需求设计 Workflow 或 Agent，不提前把这类复杂度放进分发套件。

## 3. 仓库结构

### 3.1 标准目录

```text
skills/                                      # 唯一 Skill 源码
├── legal-ocr/
├── pdf-organizer/
├── legal-case-analysis/
└── ...

expert-suites/                               # 套件定义
├── legal-material-evidence/
│   ├── README.md
│   ├── CHANGELOG.md
│   ├── LICENSE.txt
│   └── skills/
│       ├── legal-ocr -> ../../../skills/legal-ocr
│       ├── pdf-organizer -> ../../../skills/pdf-organizer
│       └── pdf-processor -> ../../../skills/pdf-processor
├── litigation-assessment/
│   ├── README.md
│   ├── CHANGELOG.md
│   ├── LICENSE.txt
│   └── skills/
│       ├── legal-ocr -> ../../../skills/legal-ocr
│       ├── legal-case-analysis -> ../../../skills/legal-case-analysis
│       └── yuandian-law-search -> ../../../skills/yuandian-law-search
└── ...

pack-skills/                                 # 本地/CI 构建产物，继续忽略
├── legal-ocr-1.5.0.zip
├── suite-legal-material-evidence-0.1.0.zip
└── suite-litigation-assessment-0.1.0.zip
```

每个专家套件默认只维护：

```text
README.md
CHANGELOG.md
LICENSE.txt
skills/               # 成员符号链接
```

只有套件确实出现无法放入 README 的独有材料时，才按需增加 `references/`。不创建空目录或占位文件。

### 3.2 单一真值

| 信息 | 权威来源 |
| :--- | :--- |
| Skill 源码 | `skills/<id>/` |
| 套件成员 | `expert-suites/<suite-id>/skills/` 下的符号链接集合 |
| 套件用户说明 | 套件 `README.md` |
| 套件版本 | 套件 `CHANGELOG.md` 最新版本 |
| 套件外层许可证 | 套件 `LICENSE.txt` |
| 成员许可证 | 各成员自己的 `LICENSE.txt` |
| Release 产物 | GitHub Release 中的套件 ZIP |

README 中的成员表是面向用户的展示，符号链接集合是构建时的成员真值。发布前校验器必须检查二者一致，避免 README 漏写或多写成员。

## 4. 符号链接规则

### 4.1 为什么使用符号链接

符号链接适合当前的仓库内表达：

- 目录中可以直接看到套件包含哪些 Skill；
- 同一个 Skill 可以出现在多个套件中；
- 不复制 `SKILL.md`、脚本、模板和许可证；
- Skill 更新后，所有套件在下次构建时自动取得最新源码；
- 不需要额外维护机器清单文件。

### 4.2 多对多关系

专家套件不是互斥分类：

```text
一个 Expert Suite → 包含多个 Skill 链接
一个 Skill        → 可以被多个 Expert Suite 链接
```

例如：

| Skill | 可以出现的专家套件 |
| :--- | :--- |
| `legal-ocr` | 法律材料与证据、诉讼研判、合同顾问、知识产权 |
| `legal-case-analysis` | 诉讼研判、诉讼推进、合同顾问、知识产权 |
| `yuandian-law-search` | 诉讼研判、合同顾问、知识产权、客户洞察 |
| `legal-proposal-generator` | 诉讼研判、诉讼推进、合同顾问、知识产权 |
| `legal-visualization` | 诉讼研判、知识产权、客户洞察、知识生产 |
| `md2word` | 诉讼推进、合同顾问、客户洞察、知识生产 |

多个套件链接同一个 `skills/<id>/`，不构成源码重复。

### 4.3 链接约束

每个成员链接必须满足：

- 使用相对链接，不写本机绝对路径；
- 位于 `expert-suites/<suite-id>/skills/<skill-id>`；
- 链接目标固定为 `../../../skills/<skill-id>`；
- 链接名与目标目录名一致；
- 目标位于当前仓库公开 `skills/` 下；
- 目标被 Git 跟踪，并包含 `SKILL.md`；
- 不允许链接链、目录逃逸、仓库外目标或损坏链接；
- 不允许链接到 `private-skills/`、`custom-skills/` 或 `~/.myagents/skills/`。

标准创建方式：

```bash
ln -s ../../../skills/legal-ocr \
  expert-suites/legal-material-evidence/skills/legal-ocr
```

Windows 或关闭符号链接支持的 Git 环境可能把链接检出为普通文本文件。因此符号链接用于仓库组织和 CI 构建，不作为用户安装形态；GitHub Release ZIP 中必须全部展开成真实目录。

## 5. README 规范

README 是专家套件的核心用户入口，不承担隐藏的机器协议。

### 5.1 推荐结构

```markdown
# 诉讼案件前期研判专家套件

> [下载完整专家套件](<suite-download-url>)

## 适用场景

## 不适用场景

## 包含的 Skills

| Skill | 在本套件中的作用 | 单独下载 |
| :--- | :--- | :--- |
| [legal-case-analysis](../../skills/legal-case-analysis/) | 案件事实与证据分析 | [下载](<skill-download-url>) |
| [yuandian-law-search](../../skills/yuandian-law-search/) | 法律法规与类案检索 | [下载](<skill-download-url>) |

## 建议使用方式

## 安装方法

## 人工复核与使用边界

## 版本与许可证
```

### 5.2 下载链接

README 同时提供：

1. 页面顶部的完整套件 ZIP 下载链接；
2. 成员表中每个 Skill 的独立下载链接；
3. 每个 Skill 在仓库中的源码链接。

源码 README 可以先使用 `releases/latest/download/<id>.zip` 形式的占位链接。现有 `.github/workflows/update-readme.yml` 后续扩展为扫描根 README 和 `expert-suites/*/README.md`，并同时识别占位链接与上一次 Release 的实际链接，确保每次发布都能刷新到最新资产 URL。

构建套件 ZIP 时，脚本应在 staging 副本中渲染当次 Release 的精确下载链接，不回写源文件。

### 5.3 成员表一致性

成员表使用固定三列：

```text
Skill | 在本套件中的作用 | 单独下载
```

校验器从第一列的 `../../skills/<id>/` 链接提取 Skill ID，与 `skills/` 下符号链接名称逐项对照：

- README 缺少一个链接成员：失败；
- README 多写一个不存在的成员：失败；
- ID、路径或大小写不一致：失败；
- 同一成员重复出现：失败。

## 6. CHANGELOG 与版本

每个专家套件维护独立 `CHANGELOG.md`，版本从最新版本标题读取，沿用项目已有格式：

```markdown
## [0.1.0] - 2026-09-03

### 新增
- 建立诉讼案件前期研判套件。
- 收录案件分析、法律检索和方案交付 Skills。
```

### 6.1 版本变化规则

以下变化需要升级套件版本并写 CHANGELOG：

- 新增或移除成员符号链接；
- 修改套件名称、定位、适用边界或建议使用方式；
- 修改套件 ZIP 结构或安装方法；
- 修改套件外层许可证；
- 修复 README 成员、下载链接或发布信息错误。

成员 Skill 自身的普通修复不要求同步升级所有引用它的套件版本。具体成员版本由其 `SKILL.md` 和 `CHANGELOG.md` 说明，套件 ZIP 所属的仓库 Release tag 表示本次打包快照。

新建但未公开验证的套件可以使用 `0.x.x`；达到可公开使用的成熟条件后再进入 `1.x.x`。

## 7. LICENSE

### 7.1 套件外层许可证

`expert-suites/<id>/LICENSE.txt` 只授权套件 README、成员选择和外层组织，不覆盖成员 Skill 的许可证。

建议分类：

| 套件 | 外层许可证 |
| :--- | :--- |
| 法律材料与证据处理 | MIT |
| 诉讼案件前期研判 | CC BY-NC |
| 诉讼文书与案件推进 | CC BY-NC |
| 合同审查与企业顾问 | CC BY-NC |
| 知识产权业务 | CC BY-NC |
| 法律研究与客户洞察 | CC BY-NC |
| 律师知识生产 | MIT |
| Skill 开发与质量保障 | MIT |
| Skill 发布与分发 | MIT |

### 7.2 成员许可证

Release ZIP 必须保留每个成员目录中的原始 `LICENSE.txt`。README 的“版本与许可证”一节明确：

> 本专家套件是多个独立 Skill 的集合。套件外层文件按本目录 LICENSE.txt 授权；各成员 Skill 按其目录内 LICENSE.txt 分别授权。下载或使用套件不改变成员原有许可条件。

包含 CC BY-NC 成员的套件不能被整体宣传为“全部 MIT”或“可自由商用”。

## 8. 专家套件版图

建议当前收敛为 9 个中等粒度套件：

| ID | 专家套件 | 主要成员 Skill | 主要用途 |
| :--- | :--- | :--- | :--- |
| `legal-material-evidence` | 法律材料与证据处理 | `legal-ocr`、`pdf-processor`、`pdf-organizer`、`video-screenshot`、`funasr-transcribe`、`transcription-corrector`、`paddle-ocr`、`mineru-ocr`、`tingwu-asr`、`court-sms`、`dingtalk-minutes` | 把原始文档、扫描件和音视频转成可分析材料 |
| `litigation-assessment` | 诉讼案件前期研判 | `new-case`、`legal-case-analysis`、`yuandian-law-search`、`legal-proposal-generator`、`legal-ocr`、`pdf-organizer`、`legal-visualization`、`md2word`、`court-sms` | 收案、事实证据、争点、检索和诉讼策略 |
| `litigation-documents-operations` | 诉讼文书与案件推进 | `elements-complaint-generator`、`litigation-analysis`、`legal-proposal-generator`、`md2word`、`legal-case-analysis`、`yuandian-law-search`、`new-case`、`court-sms`、`legal-visualization` | 起诉答辩、裁判分析、上诉再审和客户交付 |
| `contract-business-counsel` | 合同审查与企业顾问 | `opc-legal-counsel`、`contract-copilot`、`legal-case-analysis`、`yuandian-law-search`、`legal-proposal-generator`、`legal-ocr`、`legal-visualization`、`md2word` | 企业问题分诊、合同审查和顾问交付 |
| `intellectual-property-practice` | 知识产权业务 | `patent-download`、`patent-analysis`、`code2patent`、`trademark-assistant`、`new-case`、`legal-case-analysis`、`yuandian-law-search`、`legal-proposal-generator`、`legal-visualization` | 专利分析、代码专利化和商标申请规划 |
| `legal-research-client-insight` | 法律研究与客户洞察 | `yuandian-law-search`、`legal-client-brief`、`legal-industry-report`、`legal-text-format`、`wechat-article-fetch`、`legal-visualization`、`de-ai-polish`、`md2word`、`piclist-upload` | 法律研究、客户简报和行业报告 |
| `lawyer-knowledge-production` | 律师知识生产 | `dingtalk-minutes`、`funasr-transcribe`、`transcription-corrector`、`lecture-review`、`course-generator`、`article2book`、`de-ai-polish`、`md2word`、文章/书籍插图 Skills、`piclist-upload` | 从既有内容资产生成课程、书稿和文章 |
| `skill-development-quality` | Skill 开发与质量保障 | `project-init`、`legal-harness-init`、`skill-lint`、`verification-gate`、`git-workflow`、`multi-agent-orchestration`、`cross-agent-coordination`、`agent-email` | Skill 项目初始化、开发、验证与协作收口 |
| `skill-release-distribution` | Skill 发布与分发 | `git-batch-commit`、`git-workflow`、`release-workflow`、`skill-publish-sync`、`subtree-publish`、`skill-manager`、`skill-lint`、`verification-gate` | 版本、Release、多渠道同步和用户安装 |

同一个 Skill 在表中重复出现是有意设计，不需要为避免重复而删减场景成员。

第一批建议先建立：

1. `legal-material-evidence`；
2. `litigation-assessment`；
3. `litigation-documents-operations`；
4. `skill-development-quality`；
5. `skill-release-distribution`。

`case-progress`、`case-dashboard` 当前仍在各自 `SKILL.md` 中标为骨架版本，第一批不放入公开套件；达到可用状态后再考虑加入“诉讼文书与案件推进”。

## 9. Release 套件包

### 9.1 产物结构

仓库中的成员是符号链接，Release ZIP 中的成员必须是完整真实目录：

```text
suite-litigation-assessment-0.1.0.zip
└── litigation-assessment/
    ├── README.md
    ├── CHANGELOG.md
    ├── LICENSE.txt
    └── skills/
        ├── new-case/
        │   ├── SKILL.md
        │   ├── CHANGELOG.md
        │   ├── LICENSE.txt
        │   └── ...
        ├── legal-case-analysis/
        └── yuandian-law-search/
```

套件 ZIP 直接包含成员 Skill 目录，不在大 ZIP 中再次嵌套各个单 Skill ZIP。这样用户解压后可以直接把 `skills/*` 复制到 Agent 的 Skills 目录。每个单 Skill 的独立 ZIP 仍通过套件 README 提供。

### 9.2 构建原则

构建器不能简单执行 `zip -r` 或盲目跟随符号链接。推荐流程：

1. 遍历 `expert-suites/*/`；
2. 从套件 CHANGELOG 读取最新版本；
3. 验证 README、CHANGELOG、LICENSE 和 `skills/` 存在；
4. 枚举 `skills/` 下的成员符号链接；
5. 解析并确认每个目标严格位于仓库 `skills/<id>/`；
6. 检查目标被 Git 跟踪、包含 SKILL.md 和 LICENSE；
7. 对照 README 成员表，阻断漏写、多写和重复；
8. 使用 `git archive HEAD --worktree-attributes -- skills/<id>/` 从当前提交导出真实成员内容；
9. 把套件 README、CHANGELOG、LICENSE 和真实成员目录组装到临时 staging；
10. 生成 `pack-skills/suite-<suite-id>-<version>.zip`；
11. 解压回验后才把产物视为成功。

使用 `git archive` 而不是 `cp -L` 的原因：只发布当前 commit 已跟踪内容，并继续应用 `.gitattributes` 对 archive、缓存、数据库和本地配置的排除规则。

### 9.3 与现有 Release 的衔接

建议在 `skills/release-workflow/scripts/` 增加：

```text
build-suite-zips.sh
validate-expert-suites.py
test-build-suite-zips.sh
```

`.github/workflows/release.yml` 现有上传规则是：

```yaml
files: |
  pack-skills/*.zip
```

套件 ZIP 继续输出到 `pack-skills/`，因此上传资产 glob 不需要改变，只需在普通 Skill 构建之后增加套件构建和数量校验。

`.github/workflows/update-readme.yml` 应扩展为同时更新：

- 根目录 `README.md` 的单 Skill 和专家套件链接；
- `expert-suites/*/README.md` 的整套下载链接；
- `expert-suites/*/README.md` 中每个成员的单独下载链接。

### 9.4 Preview 门禁

套件打包先在本地和非发布 Preview 中验证：

- 本地构建全部套件；
- Pull Request 的 Ubuntu job 构建并上传 Actions artifact；
- 解压检查目录和成员；
- 从临时目录模拟安装。

正式 tag 和 GitHub Release 只发布已经通过 Preview 的产物，不能用来测试脚本。

## 10. 安装与使用

### 10.1 整套安装

用户下载套件 ZIP 后：

1. 解压 ZIP；
2. 阅读根目录 README；
3. 把其中 `skills/*` 复制到目标 Agent 的 Skills 根目录；
4. 按 README 检查需要的系统依赖、Python 包、Token 或平台限制；
5. 正常通过各成员 Skill 的 description 触发使用。

### 10.2 单 Skill 安装

如果用户只需要其中一个能力，直接使用 README 成员表里的单独下载链接，不必下载整个套件。

### 10.3 安装器不是第一阶段前提

第一阶段不要求 `skill-manager` 理解 Expert Suite。套件 ZIP 本身已经是可手工安装的目录集合。

后续如需一键安装，可以让 `skill-manager` 接受套件 ZIP，遍历其中 `skills/*` 并复用现有单 Skill 安装逻辑；不需要重新引入 `suite.yaml`。

## 11. 校验与安全

### 11.1 仓库静态校验

- 套件目录名使用英文短横线；
- README、CHANGELOG、LICENSE 和 `skills/` 齐全；
- CHANGELOG 最新版本可解析；
- 所有成员都是相对符号链接；
- 链接名、目标 Skill 目录名和 SKILL.md `name` 一致；
- 链接目标在公开 `skills/` 内并被 Git 跟踪；
- README 成员表与符号链接集合完全一致；
- README 包含整套下载和每个成员的单独下载入口；
- 不存在损坏、仓库外、私有或循环链接。

### 11.2 构建产物校验

- ZIP 中不存在符号链接，所有成员均为真实目录；
- 每个成员包含 SKILL.md、CHANGELOG 和 LICENSE；
- 成员数量与仓库符号链接数量一致；
- 同一成员不重复打包；
- ZIP 内没有 `.env`、Token、数据库、archive、缓存和本机绝对路径；
- 构建中途失败不会覆盖上一份完整产物；
- 解压后 `skills/*` 可以被目标 Agent 正常发现。

### 11.3 跨平台边界

- GitHub Actions 的 Ubuntu runner 作为正式打包环境；
- macOS 和 Linux 可以正常使用仓库符号链接；
- Windows 仓库检出可能受 Git symlink 配置影响，但不影响用户下载 Release ZIP；
- 不把仓库源码 ZIP 当作专家套件安装包，用户应下载 Release 资产。

## 12. 分阶段实施

### 阶段 1：第一批套件目录

- 创建首批 5 个 `expert-suites/<id>/`；
- 编写 README、CHANGELOG 和 LICENSE；
- 创建成员相对符号链接；
- 增加静态校验器；
- 暂不修改正式 Release。

### 阶段 2：本地打包与 Preview

- 实现 `build-suite-zips.sh`；
- 增加链接逃逸、损坏链接、README 漂移和构建回滚测试；
- 增加非发布 Preview job；
- 实际解压并模拟安装至少一个套件。

### 阶段 3：README 展示与正式发布

- 在根 README 增加专家套件区；
- 扩展下载链接更新工作流；
- 完成 Release 五问自检；
- 同时发布单 Skill ZIP 与套件 ZIP；
- 从 Release 下载产物并复验。

### 阶段 4：补齐剩余套件

- 合同审查与企业顾问；
- 知识产权业务；
- 法律研究与客户洞察；
- 律师知识生产。

每套独立验证后再进入公开列表。

## 13. 预计涉及文件

真正实施时预计涉及：

```text
expert-suites/*
README.md
.github/workflows/release.yml
.github/workflows/update-readme.yml
.github/workflows/<suite-preview>.yml
skills/release-workflow/scripts/build-suite-zips.sh
skills/release-workflow/scripts/validate-expert-suites.py
skills/release-workflow/scripts/test-build-suite-zips.sh
skills/release-workflow/SKILL.md
skills/release-workflow/TASKS.md
skills/release-workflow/DECISIONS.md
skills/release-workflow/CHANGELOG.md
```

如果后续升级 `skill-manager` 支持套件 ZIP，再单独修改其 SKILL、脚本、测试和技能级文档，不与第一批套件目录和 Release 构建混在同一个任务中。

## 14. 验收标准

- [ ] 每个专家套件只维护 README、CHANGELOG、LICENSE 和成员链接；
- [ ] 不存在 `suite.yaml`、README 机器 frontmatter 或默认 `references/`；
- [ ] 每个成员链接都指向仓库公开 `skills/<id>/`；
- [ ] 同一个 Skill 可以被多个套件链接；
- [ ] README 成员表与符号链接完全一致；
- [ ] README 提供整套 ZIP 和单 Skill 下载链接；
- [ ] 套件 ZIP 包含 README、CHANGELOG、LICENSE 和真实 Skill 目录；
- [ ] 套件 ZIP 不包含符号链接或嵌套的单 Skill ZIP；
- [ ] 成员原始 LICENSE 全部保留；
- [ ] 本地和 Preview 构建、解压、敏感文件检查及模拟安装通过；
- [ ] 正式 Release 前不使用 tag 测试构建；
- [ ] 从 GitHub Release 下载的套件能够直接解压并安装。

## 15. 最终决策

1. Expert Suite v1 是场景化 Skill 下载集合，不是运行时工作流；
2. 不创建 `suite.yaml`，也不把 README 变成隐藏 manifest；
3. 套件成员由 `skills/` 子目录中的相对符号链接表达；
4. `skills/` 仍是全部 Skill 源码的唯一真实位置；
5. Skill 与套件是多对多关系；
6. 每套默认维护 README、CHANGELOG、LICENSE 和成员链接；
7. `references/` 只在出现套件独有材料时按需创建；
8. Release 构建解析并校验符号链接，再从 Git commit 导出真实 Skill 目录；
9. 套件 ZIP 不保留符号链接，不嵌套单 Skill ZIP；
10. README 同时提供完整套件和成员单独下载入口；
11. 第一批先做 5 套，打包链路稳定后再补剩余 4 套；
12. 运行时编排、Suite Agent 和自动安装留给未来独立需求。
