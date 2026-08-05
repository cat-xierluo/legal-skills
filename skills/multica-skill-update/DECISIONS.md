# 决策记录

## D1：同步对象是 Multica skill 数据库，不是本地路径（2026-08-05）

**背景**：规划稿明确"同步对象 = Multica skill 数据库，不是本地 `.codebuddy/skills/` 路径"。

**方案**：脚本所有命令都是 `multica skill import ...`，操作的是 Multica 数据库；不碰本地 `.codebuddy/skills/` 目录。

**理由**：本地路径是平台下发的，改它不会让 agent 读到，还易被覆盖。同步以 Multica 为唯一权威目标。

## D2：来源刷新用 `import --on-conflict overwrite`，不用 `skill update`（2026-08-05）

**背景**：规划稿 §6 关键澄清——`multica skill update <id>` 只是按 ID 编辑字段，不会去 GitHub 拉最新。

**方案**：同步逻辑统一走 `multica skill import --url <url> --on-conflict overwrite`；SKILL.md 显式写入该澄清。

**理由**：`import` 才真正从来源拉取内容；`overwrite` 保留 skill ID 与 agent 绑定（仅限原始创建者）。

## D3：实现为 SKILL.md + 脚本，三模式 init/update/plan（2026-08-05）

**背景**：用户选择"SKILL.md + 脚本"实现，而非纯文档。

**方案**：`scripts/sync_skills.py` 实现 init/update/plan 三模式；plan 无副作用预览；脚本做 multica CLI 预检（缺失时输出安装提示、退出码 2）。

**理由**：脚本可重复、结果可结构化报告，便于 Autopilot/CI 调用；plan 模式满足规划稿"是否需要 diff 预览"的开放问题（加 plan 模式做无副作用预览）。

## D4：manifest 嵌入 skill 内部（2026-08-05）

**背景**：用户选择"manifest 放 skill 内部"（规划稿默认，随 skill 一起安装/版本化）。

**方案**：真实 `manifest.json` 由维护者创建在 skill 根目录；`references/manifest.example.json` 为模板。

**理由**：清单随 skill 安装，便于版本化与分发；example 模板供他人复制填写。

## D5：发布到 skills/ 正式目录（2026-08-05）

**背景**：用户选择"skills/ 正式发布"。

**方案**：作为公开技能放 `legal-skills/skills/multica-skill-update/`，走 marketplace 登记 + README 更新。

**理由**：该 skill 是通用工具（不绑定个人账号），可公开分发；依赖 multica CLI 需自装自配，文档已写清。
