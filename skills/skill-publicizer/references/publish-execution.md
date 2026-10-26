# 发布执行与授权边界

执行对外动作前读取。本参考只规定公开化场景的顺序与授权分层；具体命令、身份门禁和隐私预检以 git-workflow 为权威。

## 授权分层

| 层 | 动作 | 授权要求 |
|---|---|---|
| 整理 | 分层、剥离、写文档、写测试、本地提交 | 任务授权即可 |
| 交付候选 | push 分支、创建 Draft PR | 核会话已有明确授权；走 safe-push / safe-pr |
| 采纳入库 | PR 转 Ready、合并、公仓采用 | 用户明确授权 + 独立 review + checks 通过 |
| 公开发布 | tag/Release/平台上传/独立仓推送 | 用户明确授权；平台合同由 skill-publish-sync / release-workflow 维护 |
| 后续运行 | 定时部署、生产安装 | 与发布分开授权；安装入口存在不等于实际可调用 |

任何一层完成不隐含下一层授权。「候选已通过门禁」「review 已 approve」「测试全绿」都不是发布授权。

## 候选交付顺序

1. 独立 worktree 内完成整理与门禁（单 writer）。
2. 身份自检：`identity-audit.sh whoami`；用单次 `GIT_AUTHOR_*` / `GIT_COMMITTER_*` 环境变量提交，不写仓库级 config。
3. `safe-push.sh --base origin/main --remote origin --branch <branch> --expected-name <name> --expected-email <email>`：完整 PR range 身份 + 隐私核验，推送绑定 OID；身份值来自用户/项目确认，不用仓库级 config。
4. PR 标题与正文分别写入文件，用 `safe-pr.py create --base <base> --head <branch> --expected-head <full-oid> --title-file <title> --body-file <body>` 建 Draft；PR 文本隐私由 helper 内置检查覆盖，后验 PR 元数据。完整参数以 git-workflow 为准。
5. 独立 review + checks；用户授权后才可能合并——默认不合并、不转 Ready。

## 发布包构建要点

- **允许清单**：显式列入的条目才进包；不做「整目录减黑名单」。
- **二次排除**：允许清单内仍排除运行产物、缓存、私有目录、内部维护文档。
- **候选绑定**：从绑定的 OID/干净导出目录打包（不由运行缓存树直接交包）；产物已存在则拒绝覆盖。
- **manifest**：逐文件 SHA-256 + 整体摘要 + excluded 清单；homepage 未公开时在 manifest 登记。
- **`.gitignore` 随包**：使用者装包后仍受私有层规则保护。

## 私仓 → 公仓迁移

从私仓导出公开 Skill 到公仓目录时：

1. 默认**清洁历史**：在公仓新目录提交当前候选内容，不携带私仓历史。
2. **禁止改 remote 直推**：私仓改名为公仓再推送等于公开全部历史。
3. **本地私有文件不入库**：迁移后工作区可能残留 `*.local.*` 文件（slides 现象），它们被 ignore 保护但不属于公开层；清理时保留本地副本。
4. **版本衔接**：私仓版本轨迹按项目规范处理——新公开版本从既有确认版本续编（如私仓 1.5.x → 公仓 1.5.x+1），不重置也不凭空跳号；CHANGELOG 历史条目同样去具体化后保留。
5. **索引同步**：README 技能列表 + 最近更新区 + 所属专家套件页一次对齐；条目数量与排序按目标项目现行规范执行，不在本 Skill 固定数值。

## 发布后验证

- 对公开树重跑同一发布门禁（内容一致性）。
- 安装到独立目录核加载入口与版本（文件存在不等于可调用）。
- 平台上传后核平台侧实际条目与字段。
- 回写任务卡：真实远端/平台回执、OID、剩余 NOT_VERIFIED。
