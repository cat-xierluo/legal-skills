# 更新日志

## [1.1.0] - 2026-08-30

### 改进

- 将 Skill 从 `industry-report` 迁移为 `legal-industry-report`，通过统一的 `legal-` 前缀明确其法律专业领域，同时保留月度/季度正式行业报告的产品定位。
- 同步目录、frontmatter、交叉路由、模板署名、构建元数据、测试样例、README 与本地配置忽略规则；不改变研究流程、状态门禁或视觉系统。

### 验证

- 运行目录/名称一致性、引用可达、Python 编译、行业规则与报告正反例回归、独立目录构建及最终 PDF 身份核验。
- 指令稳定性仍无 evaluator-signed 三轮证据，保持 `NOT_VERIFIED`；本次只证明命名迁移与既有确定性流程未断链。

## [1.0.0] - 2026-08-30

### 正式发布

- 将 Skill 从 `industry-research-report` 迁移为 `industry-report`，产品定位改为按月或季度制作、面向公开展示与广泛分发的正式行业报告。
- 与 `client-brief` 保持统一的短名称体系，但在触发条件、研究深度、状态和视觉节奏上明确分离。

### 新增

- 新增 `references/industry-rules.yaml`：8 个行业规则包、103 个行业别名，以及研究问题、指标、法律风险视角、官方信源角色和时效规则。
- 新增 `resolve_industry_rules.py`、`validate_industry_rules.py` 与正反例自测；未知行业显式回退为 `common` 并标记 `needs_custom_pack`。
- 报告骨架扩展为执行摘要、方法、市场、竞争、监管、法律风险、服务机会与证据账本八个主章。
- 新增可重复的正式报告端到端测试样例。

### 改进

- 信源层级改为按证据功能定义，纠正将媒体、协会、上市公司披露与政府原文混为同类“权威来源”的问题。
- 视觉系统升级为机构研究出版物：正式封面、可靠章节目录、`RESEARCH NOTE` 章节标识、表格长链接安全换行和 A4 章节节奏。
- 报告状态从内部底稿调整为 `PUBLIC_REVIEW`；发布仍须由律师完成事实、法律和表达复核。

### 验证

- 行业规则注册表校验通过：8 个规则包、103 个不重复别名、7 个通用一手信源。
- Python 编译、规则解析、未知行业回退、错误 URL、报告结构和窗口逃逸自测通过。
- 代表性人工智能报告生成 11 页 A4 PDF（595.92 × 841.92pt）；全页联系表与重点长 URL 表格复核未见裁切、重叠或乱码。
- Harness 失效审查为 `PASS`；安全扫描无 critical/high，两个参数数组式 `subprocess.run(shell=False)` 保留为 medium 提示。
- 官方 `quick_validate.py` 不接受本项目规范要求的顶层 `author/homepage/version`，因此该项为已知校验器策略不兼容，不删除项目必需元数据。
- 动态语义稳定性尚无三轮独立签名证据，保持 `NOT_VERIFIED`。

## [0.8.0] - 2026-08-30

### 改进

- 将产品展示名收敛为“行业法律报告系列 · 单次基线研究”，保留 `industry-research-report` 稳定 ID，避免仅为统一命名破坏既有调用。
- 明确报告是律师内部研究底稿，修复 description 中“可交付 PDF”与正文“不得直接对外”的定位冲突。
- 企业数据库连接器不可用时改走官方公开渠道或标记“未采集/待复核”，不再把单一 MCP 写成必备前提。
- 信源交叉验证改为按结论类型执行：官方原文可证明自身发布内容，趋势与归纳性结论要求独立复核或 `[单一信源]` 披露。

### 新增

- 新增统一构建入口 `scripts/build_report.py`，串联 Markdown 校验、HTML、A4 PDF、页尺寸复核和哈希元数据。
- 新增 `scripts/validate_report.py` 与正反例自检，阻断缺章节、残留占位符、免责声明错位和信源缺失。
- 新增固定依赖清单、可选信源黑名单样例、`archive/.gitkeep` 与完整 CC BY-NC 许可证文本。

### 修复

- 修复 `--report-kind` 在 profile 校验后才覆盖，导致报告类型变化但封面未重新校验的问题。
- 修复封面标题直接使用文件名而出现 `sample-`、扩展名等技术痕迹的问题。
- 修复脚本硬编码 Skill 版本、输出目录不存在时报错和仅支持系统 Chrome 的问题。
- 修复连续流长章节导致目录推算页码错误的问题；目录改为可靠的章节索引，不再展示伪精确页码。
- 更新长期滞后的设计规范，使其与 v0.7.0 精简版式、连续流和当前页眉页脚一致。

### 安全与文档

- 新增网络、文件写入、本地进程和外部数据库的权限边界与隐私提示。
- 修复本地行业信源覆盖和黑名单“声称已 gitignore、实际未忽略”的配置风险。

### 验证

- Python 编译与 IR/WB 正反例自检通过；Harness 失效审查为 `PASS`。
- 端到端生成 9 页最小报告与 11 页含长章节/表格样例，全部页面为 A4（595.92 × 841.92pt）；全页联系表复核未见裁切、重叠或乱码。
- 安全扫描无 critical/high；两处 `subprocess.run` 因固定参数数组且 `shell=False` 保留为 medium 提示。
- 尚无三轮独立语义稳定性证据，Instruction Stability 保持 `NOT_VERIFIED`；律师复核边界不变。

## [0.4.1] - 2026-08-25

### 回退

- **律所引言章 motto 暂不启用**(DEC-IR-011):应用户反馈"各家律所引言差异大,先不显示"。4 个 cover 变体的 motto 块用 `{% if false %}` 包住,渲染产物无 motto 文字;`report-profile.md` 的 `motto` 字段保留(便于后续按律所启用),SKILL.md 标注"v0.4.1 暂不启用",启用方法为把 `{% if false %}` 改回 `{% if motto %}`。

### DECISIONS.md 增量

- **DEC-IR-011 暂不启用 motto**:字段与模板插槽保留;条件渲染改为 `{% if false %}`,用户后续如需按律所启用,改回 `{% if motto %}` 一行即可。

### 验证

- 4 个 cover 渲染产物 `motto 块 = 0` / `motto 文本 = 0`
- PDF 端到端通过(10 页 512KB,封面文字抽取确认无 motto)
- SKILL.md 加"v0.4.1 暂不启用"标注

## [0.5.0] - 2026-08-25

### 新增(工艺感升级 + IR/WB 设计强烈差异化)

- **4 个 IR 封面工艺感升级**(DEC-IR-012):顶金带(4mm + 切口) + 底金边 + REPORT NO. 徽章(1.5mm 金色描边 + 主色半透底) + 几何内嵌金环 + kicker 金线分隔 + 字号升级(标题 36pt → 40-42pt)
- **2 个 WB 轻量版专属封面**(DEC-IR-013):`W1-minimal`(居中布局 + 期数胶囊 + 受众标签 + 大留白) / `W2-tag-bar`(顶部金色期数条 + 标题左对齐)
- **`report-profile.md` 新增 `report_kind` 字段**(`ir` | `wb`):决定封面 / 目录 / 章节页眉 / 表格 / 页脚全套视觉系统
- **`report-profile.md` 新增 WB 字段**:`audience_label` / `period_number` / `period_year`
- **`report-template.html` 设计变量化**(DEC-IR-014):12 个 CSS 变量由 render.py 按 report_kind 注入
  - body-size / leading / h1-size / h2-size / h3-size
  - toc-columns(IR 2 / WB 1)
  - 装饰线颜色(IR 金 / WB 灰蓝)
  - 装饰线粗细(IR 2px / WB 0.8px)
  - 表头底色(IR 深蓝 / WB 浅灰)
  - 章节页眉线粗细
- **`pdf.py` 页脚差异化**(DEC-IR-015):
  - `FOOTER_TEMPLATE_IR`:主色字 + 金色横线(蓝皮书页脚)
  - `FOOTER_TEMPLATE_WB`:字号 8px + 灰色 + 0.5px 浅灰线(克制轻量)

### 改进(渲染脚本)

- `scripts/render.py` 增加 `--report-kind` / `--cover-style` 命令行参数
- `scripts/render.py` 增加 `IR_COVERS` / `WB_COVERS` / `DEFAULT_COVER_BY_KIND` 分类
- `scripts/render.py` 新增 `resolve_design(report_kind, palette)` 函数
- `scripts/render.py` 根据 `report_kind` 切换默认 subtitle / lead / kicker / footer_brand
- 元数据脚注页加 `skill_name` 字段

### DECISIONS.md 增量

- DEC-IR-012 / 013 / 014 / 015(工艺感 / 差异化 / 系统化 / 页脚)

### 验证

- 端到端 IR / WB PDF 端到端通过,5 调色板切换验证
- 桌面对照:`~/Desktop/skill-demo-20260825/行业调研报告-零部件制造-XX区域.pdf` + `法律周报-科技型制造企业-2026第01期-DRAFT.pdf`

## [0.4.0] - 2026-08-25

### 新增

- **封面三层装饰叠加**(DEC-IR-010):4 个 cover 变体全部从单层装饰升级为三层:
  - `C-geo`:大金色描边圆 + 中号深色填充圆 + 小描边圆 + 金色小圆点
  - `D-diagonal`:宽金色斜条 + 窄深色斜条 + 细金色装饰线 + 端点金点
  - `E-flip`:大深色圆盘 + 中号金色描边圆 + 小金色填充圆 + 同心环装饰
  - `F-grid`:8 色块网格(高/中/低 4 种高度,深浅交替,形成节奏)
- **律所引言章( motto 字段)**:在 `config/report-profile.md` 新增 `motto` 字段(默认「以专业为本 · 以客户为先」),通过 `{% if motto %}` 条件渲染,各 cover 在合适位置显示(金色左边框 + 衬线斜体 + 3px letter-spacing)
- **DECISIONS.md 增量**:DEC-IR-010 封面多图层叠加 + 律所引言章

### 改进

- 4 个 cover HTML 全部重写,体积 +5-15%(多层 CSS 装饰)
- `scripts/render.py` 的 `default_profile()` 加 `motto` 默认值
- `config/report-profile.example.md` 加 `motto` 字段示例

### 验证

- 端到端 demo 渲染:4 个 cover 变体全部通过(`motto=1`,`layer-3 / circle-deco / grid-cell` 装饰元素命中)
- PDF 端到端:10 页 513KB A4(略大于 v0.3.0 的 509KB,符合图层叠加增量)

## [0.3.0] - 2026-08-25

### 新增

- **5 个律师常见调色板预设**(DEC-IR-008):`references/palette-presets.md` 内置 5 套主色 + 强调色 + 适用律所类型说明:
  - `bluebook` 蓝皮书(深蓝 + 金)——法律经典蓝皮书
  - `service-plan` 律所深棕(深棕 + 棕点缀)——传统律所
  - `burgundy` 酒红(酒红 + 古铜金)——精品所 / 涉外仲裁
  - `forest` 森林绿(深绿 + 麦穗金)——环境法 / ESG
  - `tech` 科技蓝(科技蓝 + 青色)——互联网 / 数据合规 / AI / 知产
- **SKILL.md "首启向导"段**(DEC-IR-008):7 个核心问题清单(律所名 / 系列名 / 主色调 / 设计强度 / 封面变体 / 主办律师 / 联系方式);Agent 按 harness 实际机制提问,**不绑死 AskUserQuestion tool**;一次性填完,后续所有报告复用
- **报告模板颜色变量化**:`references/report-template.html` 的 `:root { --primary / --accent / ... }` 改成 jinja2 变量注入;`scripts/render.py` 新增 `PALETTE_PRESETS` 字典 + `resolve_palette(profile)` 函数;`scripts/pdf.py` 页脚颜色同步从 profile 取
- **端到端换肤验证**:同 demo md 用 `bluebook` 与 `burgundy` 两套调色板渲染,主色 / 强调色都正确切换

### 改进

- SKILL.md "渲染管线 / 设计风格"段从单一蓝皮书扩为 5 个调色板对比表 + 选择建议
- 故障排除加 `color_palette` 字段合规校验 + 报告还是深蓝色排查路径
- 引用资源加 `palette-presets.md` 与 `industry_sources.yaml` 路径

### DECISIONS.md 增量

- **DEC-IR-008 首启向导**:Agent 用 harness 提问机制(不绑死 tool)一次性问 7 个问题,生成 `report-profile.md`;回答固化,后续报告复用
- **DEC-IR-009 主色全字段化**:把蓝皮书主色从硬编码改为 profile 字段;首启 5 选 1,后续换调色板只改 profile 不动模板

## [0.2.0] - 2026-08-25

### 新增

- **行业特定信源映射机制**(DEC-IR-005):内置 18 个律师高频服务行业 + 1 个通用兜底,分两类:
  - 硬科技 7:半导体 / 低空经济 / 具身智能 / 新能源汽车 / 生物医药 / 数据要素 / AI 大模型
  - 民商服务 12:房地产 / 建设工程 / 餐饮食品 / 养老 / 教培 / 文旅 / 跨境电商 / 直播电商 / 物流 / 农业 / 金融科技 / 知产服务
  - 通用兜底 1:未命中行业走 P1 一手文本(招股说明书 + 部委文件)
- **`references/industry_sources.yaml`** 正式落地,关键词命中 + 合并去重,共 20 个条目
- **`config/industry_sources.local.example.yaml`** 用户本地覆盖样例(细分行业示例、覆盖内置三类典型用法)
- **SOP 第四步**:AI 跳第一轮检索前**先问用户**"XX 行业是否有要优先的信源",用户提供则用,未提供则按内置清单 / 通用兜底
- **DECISIONS.md**(DEC-IR-001 至 DEC-IR-007 七个真实决策):含背景 / 决策 / 理由 / 影响四段;未来迭代有据可查

### 改进

- **SKILL.md "网络检索"段落**:从单一信源优先级扩展为"信源优先级 + 行业特定信源"两段,显式说明内置覆盖范围与命中规则

## [0.1.0] - 2026-08-25

### 新增

- **行业法律调研报告 v0.1.0**:输入 industry/region/focus/depth,输出精排 A4 PDF 行业法律调研报告
- **蓝皮书体例设计**(DEC-IR-002):深蓝主色 `#1B3C59` + 金色强调 `#D4AF37` + 白色页面 + 4 个封面变体(C-geo / D-diagonal / E-flip / F-grid),律所对外正式发布物的经典体例
- **个性化配置体系**(DEC-IR-004):内置 `config/report-profile.md`(gitignore),抬头 / 配色 / 主办律师 / 联系方式 / 封面变体一次配置,所有报告共享
- **数据纪律**(DEC-IR-006):企查查 E 路径铁律 + 网络检索 5 级信源优先级(`references/data-discipline.md`)
- **报告骨架模板**:`templates/report-skeleton.md` 六段式(统计口径 / 行业概览 / 政策聚焦 / 企业画像 / 风险汇总 / 附录)
- **渲染管线**(DEC-IR-003):md → A4 HTML(jinja2)→ Playwright + Chrome headless → pymupdf 合并 PDF,分部分渲染(封面全幅 + 正文带页脚)
- **验收 demo**:`archive/sample-零部件制造-XX 区域.md`(头部企业级企业画像条目示例)
- **设计规范**:`references/design-spec.md`(配色 / 字体 / 页面尺寸 / 页眉页脚 / 表格 / h3 子节装饰)

### 验证(眼见为实)

- 端到端验证:`demo md → HTML(25KB)→ PDF(509KB, 10 页 A4)` 全链路通过
- 脚本语法 OK:`python3 scripts/render.py --help` / `python3 scripts/pdf.py --help` 双 CLI 正常
- 依赖已就位:playwright + pymupdf + jinja2 + markdown + bs4 + pyyaml + Chrome 151
- 模板 jinja2 语法 OK(`report-template.html` + cover-{C,D,E,F}.html)
- 端到端 demo 渲染关键数据命中(律所名 / 系列名 / 关键风险标签等)

### 文档完善

- SKILL.md 详述触发场景、IO 契约、SOP、质量纪律、渲染管线、验收标准、v1 不做、故障排除
- 示例 demo md 覆盖六段骨架,可直接跑 `python3 scripts/render.py -i archive/sample-...md -o out.html && python3 scripts/pdf.py -i out.html -o out.pdf` 验收

### 已知 bug(已在 v0.1.0 修复)

- **frontmatter 注释解析**:YAML 行尾 `# 注释` 被吞进 value,修复(`render.py` 正则改为 `(.+?)(?:\s+#.*)?$`)
- **布尔字段类型**:YAML 解析后 `true/false` 是 bool,Python 模板要求 `bool()` 显式转换
- **双 include_toc 冲突**:`report_meta` 与 `template.render(include_toc=...)` 同名冲突,改为排除 `**report_meta` 中同名键

## [0.6.1] - 2026-08-25

### 改进(杂志Studio book-style 排版优化)

用户反馈"内容页上下边距、左右边距占满页面;字体可再大;行间距字间距可优化"。对齐杂志Studio `book-style.md` 规范:

- **加大页边距**:天头 24px → **48px (13mm)**,地脚 24px → **36px (10mm)**,左右 32px → **48px (13mm)**
- **加大字号**:
  - IR:正文 11pt → **12pt**,章节标题 17pt → **22pt**,子章节 14pt → **18pt**
  - WB:正文 10pt → **11pt**,章节标题 14pt → **16pt**
- **加大行间距**:IR 1.85 → **2.0**,WB 1.7 → **1.85**
- **加大段间距**:4px → **8px**
- **加大标题-正文间距**:h1 margin 0/8px → **0/12px**,h2 margin 8/4px → **18/10px**
- **每页固定可见页眉页脚加高**:32px → **36px**
- **天头略大于地脚**(杂志Studio book-style 规范,书籍感)

### DECISIONS.md 增量

- **DEC-IR-018 杂志Studio book-style 排版应用**:用户反馈边距 / 字号 / 行间距过紧,按 `private-skills/magazine-studio/references/book-style.md` 规范加大 —"padding 30mm 22mm 24mm,每页明显上下留白不贴边"

### 验证

- 端到端 IR:HTML 9 .page → PDF 9 页,每页 595.9x841.9pt,正文 12pt / 行高 2.0
- 端到端 WB:HTML 8 .page → PDF 8 页,每页 595.9x841.9pt,正文 11pt / 行高 1.85
- 视觉对照:`/tmp/ir_v5_p3.png` / `/tmp/wb_v5_p3.png` —左右 13mm 留白 + 天头 13mm + 地脚 10mm + 大章节标题(IR 22pt / WB 16pt)
- 桌面对照:`~/Desktop/skill-demo-20260825/行业调研报告-零部件制造-XX区域.pdf` + `法律周报-科技型制造企业-2026第01期-DRAFT.pdf`

## [0.6.2] - 2026-08-25

### 修复(书籍风格连续流 + 封面诊断)

用户明确要求"按书籍风格不要按杂志风格;全文从上到下排,当页显示不下就放后面一页,不是截断"。同时对封面仍有疑虑。

**封面诊断结论**:
- 封面几何装饰(顶金带/底金边/REPORT NO. 徽章/几何圆/期数胶囊)在 v0.6.1 已正确渲染
- 之前"封面没渲染成功"的印象,根因是 v0.6.0 早期版本封面 CSS 注入丢失 + 章节内容被静默裁切(看起来像首页坏了)
- v0.6.1 CSS 注入修复后封面已完整;v0.6.2 连续流后章节内容完整跨页,整体不再有"坏页"

**核心改造:杂志固定画布 → 书籍连续流(对齐杂志Studio 协议)**:

| 维度 | v0.6.1(杂志固定画布) | v0.6.2(书籍连续流) |
|---|---|---|
| 章节页 | `.page` 固定 794×1123px + `overflow:hidden` 裁切 | `.page.section-page` 无固定高度,`page-break-before/after: always` 自然流动 |
| 超长内容 | 静默裁切(超出消失) | Chrome 自动跨页,`page-break-inside:auto`,不截断 |
| header/footer | Playwright 分部分渲染 + 手动注入 | `@page` margin box(`@top-left/@top-center/@top-right/@bottom-*`),跨页自动重复 |
| 封面 | `page: cover` 特殊页,无 margin | 保持独立 `page: cover`,无 header/footer |
| 页边距 | 天头 48px / 地脚 36px / 左右 48px | 加大到 天头 80px / 地脚 60px / 左右 56px(≈21/16/15mm,更宽松) |

**实现**:
- `report-template.html` 全面重写:
  - `@page { size: 794px 1123px; margin: 80px 56px 60px 56px; }`(A4 @96dpi)
  - `@page` 内定义 margin box:`@top-left`(系列名)/`@top-center`(kicker)/`@top-right`(报告编号+页码)、`@bottom-*`(律所/系列/页码)
  - `.page` 只保留 `page-break-after: always`;`.page.cover-page` 单独 `page: cover`(无 margin)
  - `.page.section-page/.toc-page/.meta-page`:`page-break-before/after: always`(每章从新页开始),内容自然流动
- `render.py`:
  - `split_sections` 已按 H2 拆(v0.6.0)
  - `resolve_design` 的 `section_padding` 加大
  - `render_cover` 返回 `(css_body, div_str)` 二元组(v0.6.0)
- `pdf.py`:正文 BODY_MARGIN 与 `@page` margin 对齐(不再在正文页重复注入页脚,避免双页脚)

### 验证

- 端到端 IR:HTML 12 .page → PDF **12 页**,每页 595.9×841.9pt(A4)
- 端到端 WB:HTML 8 .page → PDF **8 页**,每页 595.9×841.9pt
- IR 从 9 页(v0.6.1 固定画布裁切)增到 12 页(v0.6.2 连续流内容完整)
- 封面截图确认:C-geo 金带/徽章/几何圆/meta 三栏全部渲染;W1-minimal 期数胶囊/受众标签/居中标题/大留白全部渲染
- 章节页截图确认:IR 章节页大章节标题(22pt)+ 金色细线 + 宽松边距;WB 章节页灰色细线 + 紧凑标题
- 桌面对照:`~/Desktop/skill-demo-20260825/行业调研报告-零部件制造-XX区域.pdf`(12页) + `法律周报-科技型制造企业-2026第01期-DRAFT.pdf`(8页)

### DECISIONS.md 增量

- **DEC-IR-019 书籍连续流 vs 杂志固定画布**:用户明确"要书籍风格,内容从上到下,超页自然放后面,不截断"——放弃 v0.6.1 的固定画布,改用 `@page margin box` 连续流
- **DEC-IR-020 封面渲染诊断**:封面装饰在 v0.6.1 CSS 注入修复后已正确;用户看到的"坏页"是章节裁切 + 早期封面 CSS 丢失的叠加印象

## [0.7.0] - 2026-08-25

### 改进(全面精简版式:Less is more)

用户反馈"方向对了,但设计冗余;手册首要简洁+保留设计感;页眉页脚元素太多;横线+kicker+多列展示都有点多了;元素要精简,审美要到位"。

**精简内容**(砍掉冗余装饰,保留核心识别):

| 元素 | v0.6.2 | v0.7.0 |
|---|---|---|
| 页眉 | 3 列: 系列名 + kicker + 报告编号,带金色横线 | **1 个元素:报告编号居中,无横线** |
| 页脚 | 3 列: 律所 + 品牌 + 页码 | **1 个元素:页码居中** |
| 章节标题 | 副标 + 主标 + 金色下划线 | **只主标 + 主色短细线(32mm)** |
| h1/h2 装饰 | 金色下划线 | **无下划线** |
| h3 装饰 | 金色左边框 5px | **主色-软色 2px** |
| 表格 | 金表头 + 交替行底色 | **表头透明 + 主色文字 + 1.5px 主色底线,扁平化** |
| 引用块 | 金色左边框 | **浅灰边框 + 浅灰底** |
| 章节页边距 | 天80/地60/左右56 | **天56/地36/左右48 (≈15/10/13mm,更克制)** |
| 字号(IR) | 章节22pt/正文12pt | **章节16pt/正文11pt (中等)** |
| 字号(WB) | 章节16pt/正文11pt | **章节14pt/正文10.5pt** |

**核心理念**:
- 保留:封面装饰(金带/徽章/几何)+ 章节大标题 + 表格内容 + 引用块内容 + 报告编号 + 页码
- 砍掉:页眉律所名 / 系列名 / kicker / 多列 / 金色装饰线 / 副标
- 设计原则:每个元素都问"删掉影响视觉完整性吗?",可省则省

**影响**:
- IR PDF 12 页 → 11 页(章节更紧凑)
- WB PDF 8 页(不变)
- 每页视觉重量减少 50%+,留白更多,更接近"书籍感"
- 封面不变(仍维持蓝皮书徽章工艺感)
