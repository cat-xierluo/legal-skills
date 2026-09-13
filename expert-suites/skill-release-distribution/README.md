# Skill 发布与分发专家套件

> [下载完整专家套件](https://github.com/cat-xierluo/legal-skills/releases/latest/download/suite-skill-release-distribution-0.1.0.zip)

用于整理提交、管理版本与 GitHub Release、同步多渠道、发布独立子树，并在分发前完成质量和验证门禁。

## 适用场景

- 发布单个 Skill 或 monorepo 中的一批 Skill ZIP；
- 把 Skill 同步到 ClawHub、SkillHub 等已支持渠道；
- 将 monorepo 子目录发布为独立仓库，并维护用户下载入口。

## 不适用场景

- 不把正式 tag 或 Release 当作测试手段；
- 不未经确认执行强制推送、删除分支或第三方平台发布；
- 不替代各平台的账号、权限和许可证审查。

## 包含的 Skills

| Skill | 在本套件中的作用 | 单独下载 |
| :--- | :--- | :--- |
| [git-batch-commit](../../skills/git-batch-commit/) | 把混合改动拆成聚焦且可追溯的提交 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/git-batch-commit-1.4.3.zip) |
| [git-workflow](../../skills/git-workflow/) | 管理分支、PR、身份门禁、合并和清理 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/git-workflow-1.8.3.zip) |
| [release-workflow](../../skills/release-workflow/) | 管理版本、批量 ZIP、Release Notes 和发布验证 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/release-workflow-1.5.0.zip) |
| [skill-publish-sync](../../skills/skill-publish-sync/) | 同步 Skill 到多个发布平台 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/skill-publish-sync-1.7.2.zip) |
| [subtree-publish](../../skills/subtree-publish/) | 把 monorepo 子目录增量推送到独立仓库 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/subtree-publish-1.7.1.zip) |
| [skill-manager](../../skills/skill-manager/) | 管理多 Agent 平台的 Skill 安装、同步和状态 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/skill-manager-1.7.2.zip) |
| [skill-lint](../../skills/skill-lint/) | 在发布前审查 Skill 结构、安全和质量 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/skill-lint-2.8.0.zip) |
| [verification-gate](../../skills/verification-gate/) | 为脚本和发布链路生成真实验证证据 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/verification-gate-1.3.0.zip) |

## 建议使用方式

1. 用 `skill-lint` 和 `verification-gate` 完成发布前门禁；
2. 用 `git-batch-commit` 整理提交，分支与 PR 规则交给 `git-workflow`；
3. GitHub 版本和资产由 `release-workflow` 管理；
4. 需要独立仓库时使用 `subtree-publish`，需要平台同步时使用 `skill-publish-sync`；
5. 用户侧多平台安装和同步由 `skill-manager` 承接。

## 安装方法

下载并解压完整套件 ZIP，把其中 `skills/*` 复制到 Agent 的 Skills 根目录。执行发布前，逐一阅读各成员 `SKILL.md` 中的凭证、网络、Git 和外部写入权限说明。

## 人工复核与使用边界

Tag、Release、第三方平台上传和独立仓库推送都会改变外部状态，必须满足对应 Skill 的确认与门禁。PR Preview 仅用于验证产物，不代表已经正式发布；发布失败不得通过反复打 tag 试错。

## 版本与许可证

当前套件版本为 `0.1.0`。套件外层文件按 [LICENSE.txt](LICENSE.txt) 的 MIT License 授权；各成员 Skill 按其目录内 `LICENSE.txt` 分别授权。下载或使用套件不改变成员原有许可条件。
