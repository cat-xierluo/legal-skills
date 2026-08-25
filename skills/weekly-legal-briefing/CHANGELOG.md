# 更新日志

## [0.3.1] - 2026-08-25

### 回退

- **motto 引言章继承 v0.4.1 暂不启用**:Skill 1 通过 symlink 自动继承,本 skill 同步无 motto 显示

## [0.3.0] - 2026-08-25

### 新增

- **封面三层装饰叠加继承**(Skill 1 v0.4.0):通过 symlink 复用 Skill 1 的 cover-{C,D,E,F}.html,自动获得多层叠加视觉增强 + motto 引言章能力

## [0.2.0] - 2026-08-25

### 新增

- **首启向导段**:复用 Skill 1 的 7 个核心问题清单;Agent 用 harness 实际提问机制逐项问,写入 `config/report-profile.md`,后续所有周报复用
- **5 个调色板预设继承**:通过 symlink 复用 Skill 1 的 `references/report-template.html` + `scripts/render.py` + `scripts/pdf.py`,自动获得 v0.3.0 的 5 个调色板支持
- **本 skill SKILL.md 加"首启向导"引用段**,避免与 Skill 1 重复说明

## [0.1.0] - 2026-08-25

### 新增

- **定时法律研报 v0.1.0**：配置一次，定期自动生成行业/法律研报草稿（如"科技型制造企业 周报"）
- **三件配置体系**：`config/report-profile.md`（个性化抬头/配色/署名）+ `config/audience-profile.md`（客户画像）+ `config/sources-whitelist.txt`（信源白名单）
- **白名单信源制**：白名单外信源默认丢弃,不入稿
- **案例必带案号 + 案号回查**：入"案例研究"板块的每条案例必须可在 https://wenshu.court.gov.cn 检索,查不到案号的剔除
- **DRAFT 闸门**：输出文件一律带 `_DRAFT` 后缀,永不做自动重命名/自动外发,发布动作物理上留给人工
- **蓝皮书体例设计**：与 Skill 1 industry-research-report 共用同一份模板体系,深蓝主色 + 金色强调 + 4 个封面变体
- **渲染管线复用 Skill 1**：scripts/ 与 references/ 通过 symlink 复用,避免双份维护
- **元数据累积**：`archive/_meta.jsonl` 增量追加每期元数据,便于年度服务报告素材汇总
- **DECISIONS.md**(DEC-WB-001 至 DEC-WB-007 七个真实决策)：含背景 / 决策 / 理由 / 影响四段；未来迭代有据可查

### 部署文档

- `deploy/workbuddy-deploy.md`：WorkBuddy 自动化任务三件套（名称 / 工作时间 / 提示词）
- `deploy/openclaw-deploy.md`：OpenClaw cron + 辅助脚本 `run_one_period.py`
- `deploy/generic-cron-deploy.md`：crontab / launchd / GitHub Actions 三平台部署样例

### 模板

- `templates/briefing-skeleton.md`：法律周报五段式骨架（本期要点 / 案例研究 / 本周动态 / 实务提示 / 页脚联系方式）
- `templates/checklist-template.md`：复核清单模板,自动产出 `..._DRAFT.checklist.md`

### 示例

- `archive/sample-科技型制造企业-2026第01期-DRAFT.md`：5 条本周动态 + 2 条案号可查的案例研究 + 3 条实务提示的完整示例

### 验证（眼见为实）

- 渲染管线复用 Skill 1 验证通过的 jinja2 模板 + Playwright + pymupdf
- 脚本 CLI 双验:`python3 scripts/render.py --help` / `python3 scripts/pdf.py --help` 正常
- symlink 路径已验证:`scripts/render.py` / `scripts/pdf.py` / `references/report-template.html` / `references/design-spec.md` / `references/covers/` 全部链到 Skill 1
- 端到端 demo 渲染 26 处关键数据命中（`XX 律所` / `XX 律所实务手册` / 竞业限制 / 商业秘密 等）；PDF 端到端 7 页 430KB A4

### 文档完善

- SKILL.md 详述触发场景、与 Skill 1 的关键差异、三件配置、IO 契约、SOP、质量纪律（白名单 + 案号 + DRAFT）、部署指南、验收标准、v1 不做、故障排除
- DECISIONS.md 七条决策记录完整

### 已知 bug(已在 v0.1.0 修复)

- **report-profile.example.md 花括号占位**：原 example 用 `{说明}` 占位导致 YAML 把整行当 value,改用合法 YAML 值 + 行尾 `# 说明` 注释
- **frontmatter 注释解析**：YAML 行尾 `# 注释` 被吞进 value,修复(`render.py` 正则改为 `(.+?)(?:\s+#.*)?$`)

