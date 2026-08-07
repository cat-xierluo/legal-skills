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

**方案**：真实 `manifest.json` 由维护者创建在 skill 根目录；`references/manifest.example.json` 为模板（后于 2026-08-07 迁至 `scripts/manifest.example.json`，见 D6）。

**理由**：清单随 skill 安装，便于版本化与分发；example 模板供他人复制填写。

## D6：清单模板迁至 scripts/ + SKILL.md 拆分 references（2026-08-07）

**背景**：用户指出清单模板同时出现在 `config/`（私有实例）与 `references/`（模板）两个目录，观感上"同一文件两处"；且 SKILL.md 已达 318 行，含内联清单 JSON 形成"第三份冗余"。

**方案**：
- 模板 `manifest.example.json` 从 `references/` 迁至 `scripts/`，与执行脚本归位；`sync_skills.py` 缺失清单时的提示路径同步更新。
- SKILL.md 拆为三个 references：`manifest-format.md`、`multica-importing-alignment.md`、`workflow-examples.md`；入口只保留核心流程并链接，内联清单 JSON 移除，统一引用模板文件与格式文档。

**理由**：保留"私有实例（config/）↔ 入库模板（scripts/）"的规范分离（符合 AGENTS.md / SkillLint 约定），消除观感上的重复；用 Progressive Disclosure 让入口更精简、深度内容按需加载。

## D7：取消 config/ 目录与自带 .gitignore（2026-08-07）

**背景**：用户指出清单实例与模板不应分处 `config/` 与 `scripts/` 两个目录（观感上仍是"同文件两处"），且技能自带 `.gitignore` 多余——是否入库由外部仓库统一调整。

**方案**：
- 删除 `config/` 目录，个人实例 `manifest.local.json` 与模板 `manifest.example.json` 同置于 `scripts/` 下；`sync_skills.py` 默认路径相应改为 `scripts/manifest.local.json`。
- 删除技能根目录 `.gitignore`（原忽略 `config/manifest.local.json` 与 Python 缓存）；清单入库与否交外部仓库统一管控。

**理由**：单一目录收纳两份清单，消除"分处两目录"的歧义；gitignore 收归仓库统一管理，避免技能各自为政。

## D5：发布到 skills/ 正式目录（2026-08-05）

**背景**：用户选择"skills/ 正式发布"。

**方案**：作为公开技能放 `legal-skills/skills/multica-skill-update/`，走 marketplace 登记 + README 更新。

**理由**：该 skill 是通用工具（不绑定个人账号），可公开分发；依赖 multica CLI 需自装自配，文档已写清。
