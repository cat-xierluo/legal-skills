# 更新日志

## [0.4.1] - 2026-08-25

### 回退

- **律所引言章 motto 暂不启用**(DEC-IR-011):应用户反馈"各家律所引言差异大,先不显示"。4 个 cover 变体的 motto 块用 `{% if false %}` 包住,渲染产物无 motto 文字;`report-profile.md` 的 `motto` 字段保留(便于后续按律所启用),SKILL.md 标注"v0.4.1 暂不启用",启用方法为把 `{% if false %}` 改回 `{% if motto %}`。

### DECISIONS.md 增量

- **DEC-IR-011 暂不启用 motto**:字段与模板插槽保留;条件渲染改为 `{% if false %}`,用户后续如需按律所启用,改回 `{% if motto %}` 一行即可。

### 验证

- 4 个 cover 渲染产物 `motto 块 = 0` / `motto 文本 = 0`
- PDF 端到端通过(10 页 512KB,封面文字抽取确认无 motto)
- SKILL.md 加"v0.4.1 暂不启用"标注

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
