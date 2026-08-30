# 更新日志

## [1.1.0] - 2026-08-30

### 改进

- 将 Skill 从 `client-brief` 迁移为 `legal-client-brief`，通过统一的 `legal-` 前缀明确其法律专业领域，同时保留每日、每周或事件触发的既有客户日常简报定位。
- 同步目录、frontmatter、交叉路由、调度提示词、模板署名、构建元数据、测试样例、README 与本地配置忽略规则；不改变增量窗口、三渠道交付、DRAFT 门禁或视觉系统。

### 验证

- 运行目录/名称一致性、引用可达、Python 编译、行业规则/主稿/三渠道正反例回归、独立目录构建及最终 PDF 身份核验。
- 指令稳定性仍无 evaluator-signed 三轮证据，保持 `NOT_VERIFIED`；本次只证明命名迁移与既有确定性流程未断链。

## [1.0.0] - 2026-08-30

### 正式发布

- 将 Skill 从 `weekly-legal-briefing` 迁移为 `client-brief`，覆盖每日、每周与事件触发的既有客户日常触达，不再被“周报”单一频率限制。
- 明确与 `industry-report` 的产品阶段：本技能只追踪相对上期的新变化，服务既有客户关系维护。

### 新增

- 强制生成完整简报、朋友圈文案和公众号文章三件套；新增 `validate_channels.py` 校验 DRAFT、长度、章节、白名单 URL、免责声明，并阻断渠道稿擅自新增完整简报未使用的信源。
- 新增 `cadence / period_start / period_end` 构建契约，元数据绑定三份 Markdown、PDF、画像、白名单和品牌配置哈希。
- 内置与正式报告相同版本的行业规则注册表与解析器；候选行业信源仍须经过本地白名单。
- 新增可重复的三渠道与 PDF 端到端测试样例。

### 改进

- PDF 从“一节一页”改为封面后的紧凑连续信息流，使用 `SIGNAL` 章节标识、无首行缩进、紧凑表格与移动阅读节奏。
- 修复 PDF 分部分渲染时丢失 `body` 产品类型 class、导致连续流回退为 9 页的问题；元数据改为接续正文自然排版，修复后同一代表性简报为 4 页。
- 部署说明改为增量窗口与三渠道任务，不再依赖期数或把纯 cron 描述成研究 Agent。

### 验证

- Python 编译、行业规则、日期窗口、白名单、朋友圈长度、公众号结构和渠道反例自测通过。
- 代表性客户简报三件套完整构建；PDF 为 4 页 A4（595.92 × 841.92pt），全页联系表复核未见裁切、重叠或乱码，正文连续流生效。
- Harness 失效审查为 `PASS`；安全扫描无 critical/high，两个参数数组式 `subprocess.run(shell=False)` 保留为 medium 提示。
- 官方 `quick_validate.py` 不接受本项目规范要求的顶层 `author/homepage/version`，因此该项为已知校验器策略不兼容，不删除项目必需元数据。
- 动态语义稳定性尚无三轮独立签名证据，保持 `NOT_VERIFIED`；任何发布仍由人工完成。

## [0.7.0] - 2026-08-30

### 改进

- 将产品展示名收敛为“行业法律报告系列 · 周期追踪更新”，保留 `weekly-legal-briefing` 稳定 ID。
- 把“自动生成”改为真实的两阶段能力：Agent 负责研究与起草，确定性脚本只负责校验和打包；纯 cron 不再冒充语义研究。
- 案例核验不再绑定单一网站，改为“案号 + 法院 + 裁判日期 + 可点击核验链接 + 核验日期”的证据组合。

### 新增

- 新增统一构建入口 `scripts/build_report.py`、Markdown 硬门禁 `scripts/validate_report.py` 及正反例自检。
- 新增白名单 URL 校验、案例证据校验、DRAFT 文件名/正文双门禁、A4 页尺寸复核和哈希元数据。
- 期数改从 `YYYY第NN期_DRAFT` 文件名/标题识别，构建时强制显式传入起止日期；期数、窗口与配置哈希写入元数据。
- 新增完整依赖清单、`archive/.gitkeep` 与完整 CC BY-NC 许可证文本。

### 修复

- 将跨 Skill 符号链接替换为目录内版本化副本，周报现在可以独立安装、打包和校验。
- 修复 `report-profile.example.md` 缺 `report_kind: wb`、封面仍为 IR 类型、目录默认开启和期数字段缺失的问题。
- 修复周报封面重复塞入受众和期数导致标题生硬换行的问题；封面主标题仅保留产品名，受众与期数使用专属信息位。
- 删除不存在的 `run_one_period.py`、虚假的自动递增声明和省略内容生成却继续上传 PDF 的部署样例。
- 周报动态表新增可点击来源链接，案例模板删除无必要的当事人身份字段。

### 安全与文档

- 明确不自动外发、不推送附件、不自动改名/复制发布版；调度完成只报告本地 `_DRAFT` 路径。
- 新增联网、文件写入、浏览器和本地进程权限说明；真实客户画像和白名单继续留在本地配置。

### 验证

- Python 编译与 IR/WB 正反例自检通过；Harness 失效审查为 `PASS`，Skill 树内无符号链接。
- 端到端生成 8 页周报，全部页面为 A4（595.92 × 841.92pt）；确认使用 W1 轻量封面、编号 `YWX-WB-2026-N01`，日期窗口和三个配置哈希进入元数据与清单；复制到无兄弟 Skill 的临时目录后仍可独立构建。
- 安全扫描无 critical/high；两处 `subprocess.run` 因固定参数数组且 `shell=False` 保留为 medium 提示。
- 尚无三轮独立语义稳定性证据，Instruction Stability 保持 `NOT_VERIFIED`；律师复核前不宣称内容稳定完成。

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


## [0.5.2] - 2026-08-25

### 修复(书籍连续流继承)

继承 Skill 1 v0.6.2 的书籍连续流改造:
- 章节页无固定高度,`page-break-before/after: always` 每章新起一页,内容自然流动不裁切
- header/footer 改 `@page` margin box(@top-*/@bottom-*),跨页自动重复
- 页边距加大(天头 80px / 地脚 60px / 左右 56px ≈ 21/16/15mm)
- 字号/行高进一步加大(WB 章节 16pt / 正文 11pt / 行高 1.85)

### 验证

- 端到端 WB:HTML 8 .page → PDF **8 页**,每页 595.9×841.9pt(A4)
- 封面 W1-minimal(期数胶囊/受众标签/居中标题/大留白)完整渲染
- 章节页灰色细线 + 紧凑标题 + 宽松边距
- 桌面对照:`~/Desktop/skill-demo-20260825/法律周报-科技型制造企业-2026第01期-DRAFT.pdf` 8 页

## [0.6.0] - 2026-08-25

### 改进(全面精简版式继承)

继承 Skill 1 v0.7.0 的精简版式:
- 页眉只居中显示报告编号
- 页脚只居中显示页码
- 章节标题去掉副标
- 表格扁平化,引用块浅灰边框
- 字号调整:WB 章节 14pt / 正文 10.5pt

### 验证

- 端到端 WB:HTML 8 .page → PDF **8 页**,每页 595.9×841.9pt(A4)
- 章节页非常简洁:无多余装饰,只有报告编号 + 章节标题 + 章节内容 + 页码
- 桌面对照:`~/Desktop/skill-demo-20260825/法律周报-科技型制造企业-2026第01期-DRAFT.pdf` 8 页
