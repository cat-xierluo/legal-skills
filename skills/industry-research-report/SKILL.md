---
name: industry-research-report
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: 0.7.0
license: CC-BY-NC
description: 输入一个行业（可选区域与业务方向），输出一份可交付的精排 A4 PDF 行业法律调研报告。设计风格采用律所蓝皮书体例（深蓝主色 + 白色页面 + 衬线大标题 + 顶部品牌带），内置 report-profile.md 个性化配置（律所抬头 / 配色 / 主办律师 / 封面变体 / 联系方式），数据源来自企查查 MCP（企业名录 + 司法/经营风险标签）+ 网络检索（政策文件、产业园名录、产业链结构）。建议在用户说"做一份行业调研报告 / 见客户前先了解下 XX 行业 / 这周要去 XX 行业跑客户帮我准备背景资料 / 开拓新行业之前知己知彼"时使用；不要用于：客户名下的具体法律意见、对单一企业的尽调（用 opc-legal-counsel）、按周推送的对外研报（用 weekly-legal-briefing）。
---

# industry-research-report · 行业法律调研报告

## 定位

获客端的情报底稿。**消费者是律师自己**——见客户前、做讲座前、开拓新行业前用,不直接发给客户,只在交付时附免责声明与统计口径。

本 skill 是XX 律师法律 AI 课程体系（详见 `知识整理/课程体系/XX 律师法律AI课程主题体系.md`）中**客户关系主轴的获客端**。中段（接谈清单 / 服务方案 / 员工手册 / 律师函）由既有套件（litigation-analysis / legal-proposal-generator / contract-copilot）参数化覆盖,本 skill 只补"行业背景情报"这一段缺。

⚠️ **不做的事**(本 skill 边界)

- 不做具体客户名下的法律意见（那是 opc-legal-counsel / litigation-analysis 的事）
- 不做单一企业的尽调（用 opc-legal-counsel）
- 不做对外发布（草稿层内部用,对外发布前必须人工复核并改用 weekly-legal-briefing 或 legal-proposal-generator 的对外版式）
- 不做 PDF 之外的排版（不做 docx、不做 HTML 交互页、不做 PPT）

## 触发场景

- "做一份 XX 行业的法律调研报告"
- "下周二见 XX 客户,帮我先把 XX 行业摸一遍"
- "我们要开拓低空经济,准备一份背景资料"
- "XX 区域的零部件制造企业有哪些,挑几家画像"

## 个性化配置（先填这个,再跑报告）

报告抬头、配色、主办律师、封面样式等所有"律所风格"信息集中在 `config/report-profile.md`,用户一次性填好即可。每次生成报告时由 `scripts/render.py` 读取,生成器不感知硬编码律所信息。

### 首启向导（首次使用 · 一次性）

> 不同 harness 的提问机制不一致(终端 read / AskUserQuestion / 微信 IM / Notion 嵌入 等),本 skill 不绑死任何特定 tool;**Agent 根据自己 harness 选择合适的提问方式**。下面是建议问题清单,按顺序一次问完:

**问题清单(7 个,按顺序):**

1. **律所全称**(必填)
   - 提问示例：「请提供律所全称,将作为报告封面顶部 / 页脚左侧的抬头」
   - 示例回答：「XX 律所」

2. **报告系列名**(必填)
   - 提问示例：「报告想放在哪个系列下?如「XX 律所实务手册」「XX 法律观察」等」
   - 示例回答：「XX 律所实务手册」

3. **主色调偏好**(必选 · 5 选 1)
   - 提问示例：「请从以下 5 个律师常见调色板中选择一个作为报告主调;详细对比见 `references/palette-presets.md`」
     - **bluebook 蓝皮书**(深蓝 #1B3C59 + 金色 #D4AF37)——法律经典蓝皮书,庄重权威,适合对外正式发布物
     - **service-plan 律所深棕**(深棕 #5A4E48 + 棕点缀 #927F76)——传统律所文书风,适合服务方案与顾问物料
     - **burgundy 酒红**(酒红 #722F37 + 古铜金 #B08D5C)——高端典雅,适合精品所 / 涉外仲裁
     - **forest 森林绿**(深绿 #1F4E3D + 麦穗金 #A8853A)——环境法 / ESG / 合规专项
     - **tech 科技蓝**(科技蓝 #1A3A6E + 青色 #00A6B6)——互联网 / 数据合规 / AI / 知产
   - 示例回答：「bluebook」

4. **设计强度**(必选 · 3 选 1)
   - 提问示例：「报告设计强度?默认 lite 文字版」
     - **lite**(默认):文字版手册,每页 0-1 个轻量组件,克制图形化
     - **balanced**:图文平衡,每页 1 个主组件或 2 个小组件
     - **visual**:强视觉,每页至少 1 个视觉主结构(信息图级)
   - 示例回答：「lite」

5. **封面变体**(必选 · 4 选 1)
   - 提问示例：「封面风格?默认 C-geo(几何顶部)」
     - **C-geo** 几何顶部:深蓝带 + 大圆盘装饰
     - **D-diagonal** 对角线斜切:现代感
     - **E-flip** 镜像对称:设计感强
     - **F-grid** 顶部网格:信息量大
   - 示例回答：「C-geo」

6. **主办律师**(必填)
   - 提问示例：「封面"主编"署名 + 抬头用哪位律师?」
   - 示例回答：「XX 律师」

7. **联系方式**(必填 · 至少微信 + 电话二选一)
   - 提问示例：「页脚右下联系方式?至少给一个」
   - 示例回答：「微信 {微信号占位} / 电话 {电话占位}」

**(v0.4.1 暂不启用) 律所引言章 motto** — v0.4.0 曾加入 motto 字段(律所品牌口号显示在封面),v0.4.1 应用户反馈"各家律所引言差异大,先不显示"已**临时关闭**(cover 模板里改成 `{% if false %}`),字段与插槽保留在 `report-profile.md`,后续如需启用,改为 `{% if motto %}` 一行即可。

**拿到回答后**,Agent 把这些信息按 `config/report-profile.example.md` 字段填到 `config/report-profile.md`(gitignore),后续所有报告都从这里读。

> ⚠️ Agent 不必逐字按上面问题清单问;可以根据 harness 实际情况简化或合并(如"律所全称和系列名一起填"、"调色板选一个")。目标是**一次性拿到 7 个核心信息,不再二次确认**。


> 复制 `config/report-profile.example.md` 为 `config/report-profile.md` 填入真实信息。**`config/report-profile.md` 已加入 `.gitignore`**,不入库。

可配置字段：

| 分组 | 字段 | 默认 | 说明 |
|---|---|---|---|
| 抬头 | `law_firm` | XX 律所 | 封面顶部律所名 + 页脚左侧 |
| 抬头 | `series_name` | XX 律所实务手册 | 封面顶部"系列名" |
| 抬头 | `series_subtitle` | AGENT EDITION / 法律实务版 | 封面顶部副标 |
| 抬头 | `report_code` | YWX-IR-{YYYY}-{NN} | 报告编号(印刷在封面右下+页脚右) |
| 主办律师 | `lead_lawyer` | XX 律师 | 报告封面"主编"署名 |
| 主办律师 | `lead_lawyer_title` | 律师 / 专利代理师 | 头衔 |
| 主办律师 | `lead_lawyer_avatar` | 路径 | 封面署名旁的头像(可选) |
| 联系方式 | `contact_wechat` | {微信号占位} | 页脚右下"联系方式" |
| 联系方式 | `contact_phone` | {电话占位} | 同上 |
| 联系方式 | `contact_email` | — | 同上 |
| 配色 | `cover_style` | `C-geo` | 封面变体 `C-geo / D-diagonal / E-flip / F-grid` 四选一 |
| 配色 | `color_palette` | `bluebook` | 配色组：`bluebook` 蓝皮书(深蓝主色) / `service-plan` 服务方案(律所深棕) |
| 配色 | `accent_color` | `#D4AF37` | 主强调色(蓝色组用金色,棕色组用铜色) |
| 报告设计 | `design_intensity` | `lite` | 设计强度三档：`lite` 文字版(本 skill 默认) / `balanced` 图文平衡 / `visual` 强视觉 |
| 报告设计 | `include_toc` | `true` | 是否生成目录 |
| 报告设计 | `include_methodology` | `true` | 是否生成"数据方法"小节(信源说明) |
| 页脚 | `footer_brand` | 行业法律调研报告 | 页脚右侧"报告名" |

> `report-profile.md` 修改后无需重启 skill,下次生成时自动生效。

## IO 契约

### 输入参数

| 参数 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `industry` | 是 | — | 目标行业词,例如「具身智能」「低空经济」「减速机制造」 |
| `region` | 否 | 全国 | 区域聚焦,例如「XX 区域」「长三角」 |
| `focus` | 否 | 全画像 | 业务方向过滤：`劳动 / 知识产权 / 投融资 / 诉讼执行`,可多选 |
| `depth` | 否 | `full` | `quick`（企业名录+风险标签） / `full`（含产业链与政策） |
| `output_dir` | 否 | `archive/` | 报告落盘目录 |

### 输出物

- `<output_dir>/行业调研报告_{industry}_{region}_{YYYYMMDD}.md`（中间稿,可编辑）
- `<output_dir>/行业调研报告_{industry}_{region}_{YYYYMMDD}.pdf`（终稿,A4 精排）
- `<output_dir>/行业调研报告_{industry}_{region}_{YYYYMMDD}.meta.json`（元数据,含 industry/region/focus/检索明细摘要/生成时间）

### 报告骨架（强制六段式）

1. **统计口径与免责声明** —— 数据来源、时间窗口、企查查覆盖范围、本报告不构成法律意见
2. **行业概览** —— 产业链结构（上游 / 中游 / 下游）、风险地图
3. **政策与区域聚焦** —— 市级/区级政策文件、产业园名录、本地企业名录（region 提供时）
4. **目标企业画像清单** —— 企查查企业名录 + 按 focus 过滤的代表性法律风险标签
5. **风险与需求汇总** —— 行业共性风险 + 投融资需求点（供拜访前知己知彼）
6. **附录** —— 检索明细（信源 URL、检索时间、可追溯）

> 完整模板见 `templates/report-skeleton.md`,六段必须齐全,每段至少一段实质内容,不得用"详见 XX"占位。

## 数据源依赖

### 企查查 MCP（E 路径 ⓪ 铁律）

所有企业类调用必须先经 `get_company_by_query` 做实体识别,不得对简称/股票简称/品牌名直接调用下游业务工具。

| 场景 | 工具 |
|---|---|
| 关键词 → 候选主体列表 | `qcc-company.get_company_by_query` |
| 主体 → 工商画像 | `qcc-company.get_company_registration_info` |
| 主体 → 一层股东 + 注册资本验证 | `qcc-company.get_shareholder_info` |
| 主体 → 风险扫描（先扫再下钻） | `qcc-risk.get_company_risk_scan` |
| 主体 → 行政处罚 / 裁判文书 / 失信 | `qcc-risk.*` 对应原子工具 |
| 主体 → 经营动态（招投标 / 资质） | `qcc-operation.*` |
| 主体 → 行业归属 | 工商信息里的「国标行业」字段 |

### 网络检索

报告骨架的 2-3 段（产业链 / 政策 / 产业园）靠网络检索补。**信源优先级写死在 `references/source-priority.md`**,从高到低：

1. 上市公司招股说明书 / 挂牌公司公开转让说明书 / 法律意见书中的行业分析与风险提示
2. 官媒产业报道（新华社 / 人民日报 / 经济日报 / 财新 / 第一财经）
3. 行业协会发布的白皮书 / 年报
4. 主流财经媒体专题报道
5. 一般网页（最后兜底,需在引用处标注）

> 任何关键结论必须有至少两个独立信源交叉验证；找不到第二信源时,在原文加 [单一信源] 标记。

### 行业特定信源（重要 · 内置 × 用户可注入）

**不同行业有特定的高质量信源**(比如低空经济要去民航局/工信部,具身智能要去科技部/招股书,半导体要去 SEMI/IC Insights),通用网络检索抓不到这些细分源头。本 skill 通过「行业 × 信源映射」机制优先用上:

- **内置默认清单**：`references/industry_sources.yaml`,已预置 **18 个律师高频服务行业**,分两类:
  - **硬科技类(7)**：半导体 / 低空经济 / 具身智能 / 新能源汽车 / 生物医药 / 数据要素 / AI 大模型
  - **民商服务类(11)**：房地产 / 建设工程 / 餐饮食品 / 养老 / 教培 / 文旅 / 跨境电商 / 直播电商 / 物流 / 农业 / 金融科技 / 知产服务(共 12 民商,加上 7 硬科技共 19)
  - **通用兜底(1)**：所有未命中行业走通用 P1 一手文本(招股说明书 + 部委文件)
- **用户本地覆盖**：`config/industry_sources.local.yaml`(gitignore),用户可补充细分行业(如「减速机」「苏州纳米所生态」)或覆盖内置条目
- **SOP 介入时机**：AI 在跳第一轮检索前,如果 industry 未命中内置清单 / 命中但清单不完整,**必须先问用户**:
  > 「XX 行业是否有要优先的信源(政府官网 / 行业协会 / 公众号 / 头部企业)?如有请列出域名或名称;否则我会按内置清单跑。」
- **命中规则**：industry 关键词不区分大小写,出现在清单的 `industry` 字段任一关键词中即命中;多个命中合并去重
- **回退**：用户未提供 / 拒绝提供 → 用内置通用兜底 + P1 一手文本(招股说明书 + 部委文件)

> 详见 `references/industry_sources.yaml` 与 `config/industry_sources.local.example.yaml`。

## SOP（流程主线）

1. **解析参数** —— 确认 industry / region / focus / depth,把空值用默认值填
2. **读取个性化配置** —— 加载 `config/report-profile.md`,确认律所抬头/封面变体/页脚品牌
3. **加载行业特定信源** —— 合并 `references/industry_sources.yaml`(内置)+ `config/industry_sources.local.yaml`(用户本地)
4. **询问行业特定信源（如有需要）** —— industry 未命中内置清单 / 命中但清单不完整时,先问用户；用户提供则记录到本次 session,提供为空则用通用兜底
5. **第一轮检索（行业概览）** —— 网络检索 industry + "产业链 / 行业研究 / 行业风险",按信源优先级过滤；优先用第 3 步加载的行业特定信源
6. **第二轮检索（区域聚焦）** —— region 提供时,收窄至该区域的「政策 + 园区 + 名录」
7. **企业检索（企查查）** —— 按 industry 行业词先做关键词检索,锁定候选主体清单（可能多候选时必须展示完整列表,不得自动选择）
8. **画像富化** —— 对筛选出的代表企业逐一查工商信息 + 风险扫描,过滤后的代表性标签写入第 4 段
9. **汇总生成 markdown** —— 按 templates/report-skeleton.md 六段式填充,关键结论标注信源层级
10. **渲染 HTML** —— `scripts/render.py` + 选择的封面变体 + jinja2 模板,产出 A4 HTML
11. **渲染 PDF** —— `scripts/pdf.py` (Playwright + Chrome headless) 出精排 A4 PDF
12. **落盘 + 写元数据** —— md / pdf / meta.json 三件归档

## 质量纪律（写进 SKILL.md 规则区）

- **信源分层**：每条关键结论标注来源层级（一手文本 / 权威数据库 / 媒体 / 一般网页）
- **交叉验证**：行业关键数据至少两个独立信源,否则标 [单一信源]
- **时效判定**：政策文件必须在引用处标注发布 / 施行日期；过期政策主动提示
- **不臆测**：企查查未收录的风险项写「未见公开信息」,不编造
- **不复制真实项目信息**：报告示例一律用 `XX 行业 / XX 地区 / XX 客户`,严禁出现真实客户名 / 申请号 / 内部案件编号
- **附录齐全**：每条信源必须可点击可追溯；缺一不可

## 渲染管线（产出 PDF 的技术路径）

文稿基底是 md,但**最终交付是精排 A4 PDF**。渲染三段式：

```
report-skeleton.md (填充后的 md)
  → scripts/render.py            # md → A4 HTML（jinja2 模板 + CSS 变量配色）
  → references/report-template.html + references/covers/cover-{C/D/E/F}.html
  → scripts/pdf.py               # HTML → PDF（Playwright + Chrome headless）
                                  # 封面/后部全幅 + 正文页眉页脚 + 分部分渲染 pymupdf 合并
```

### 设计风格（蓝皮书体例）

- **主色**：`#1B3C59` 深蓝(蓝皮书经典配色)
- **辅色**：`#D4AF37` 金色(标题下划线、强调左边框、装饰线)
- **页面底色**：`#FFFFFF` 纯白
- **次背景**：`#F4F1EA` 米黄(偶用于卡片、引用块)
- **文字色**：`#1A1A1A` 主文字、`#666666` 淡文字、`#2C3E50` 正文
- **字体**：`Noto Serif SC / Source Han Serif SC / Songti SC / SimSun / 宋体` 衬线中文
- **结构**：
  - 封面：深蓝全屏 + 大号衬线标题 + 金色水平分割线 + 作者块
  - 目录页：`目录 · 报告编号` 顶部标签 + 双栏目录(章节 + 起始页)
  - 章节页：顶部 "CHAPTER XX · 编号" 小标签 + 大号衬线章节标题 + 金色水平分割线
  - h3 子节：金色左边框 + 11px 左内边距
  - 表格：金色表头行 + 交替行底色
  - 页眉：左侧"系列名 + 章节名",右侧"报告编号"
  - 页脚：左侧"律所名 · 系列名",右侧"报告名 · 页码/总页数"
- **设计强度**：`lite` 文字版(每页 0-1 个轻量组件,优先表格/引用块/双栏卡片)

> 完整设计规范见 `references/design-spec.md`,配色变更走 `report-profile.md`,不改模板。

### 封面变体（4 选 1）

| 变体 | 风格 | 适用场景 |
|---|---|---|
| `C-geo` 几何顶部 | 顶部几何圆形装饰 + 律所名 band | 默认,严肃正式 |
| `D-diagonal` 对角线 | 对角线斜切 + 大标题压暗 | 偏现代、数据感 |
| `E-flip` 镜像 | 左右镜像对称 | 设计感强、轻盈 |
| `F-grid` 网格 | 顶部网格 + 多色块 | 信息量大、报告类 |

> 四个 cover HTML 在 `references/covers/`,由 `scripts/render.py` 按 `report-profile.md` 的 `cover_style` 选择注入;封面的具体颜色由当前调色板决定(注入 `--primary` / `--accent`)。

依赖(运行前确认)：

- Python 3.10+:playwright + pymupdf + jinja2 + markdown + beautifulsoup4 + pyyaml
- 系统 Chrome（macOS：`/Applications/Google Chrome.app`）
- （可选,带 mermaid 图时）`@mermaid-js/mermaid-cli` 全局命令 `mmdc`

## 配置（除个性化外）

- `config/source-blacklist.txt` —— 不可信信源黑名单,一行一个域名,检索结果命中则丢弃（默认空）

## 验收标准（三次对比法）

固定 demo 场景：`industry=零部件制造, region=XX 区域, focus=投融资`

- **带 skill**：跑本 skill,产出报告 + 附录检索明细 + 免责声明首段 + 头部上市零部件企业画像条目
- **不带 skill**：裸 LLM 用同一 prompt,产物对照
- **对比差异**：骨架六段齐全度、信源标注完备度、企查查企业画像条目数（≥5 家）、PDF 渲染保真度（封面变体应用 + 配色准确 + 页眉页脚齐）

**红线**：

- 附录检索明细必须可点可查
- 免责声明必须在 PDF 第一页（不可挪到末尾）
- 一键出 PDF,人工不再排版
- 封面变体必须按 report-profile.md 的 `cover_style` 应用,不得自行忽略

## v1 不做什么（最小可用边界）

- 不做定时调度（那是 weekly-legal-briefing 的事）
- 不做客户版 / 内部版双版本开关（v2 迭代）
- 不接华宇元典（行业调研非法条检索,v2 再议"行业相关法规动态"模块）
- 不做 PDF 版式精修（v1 用 4 个 cover 变体 + 一个正文模板够用）

## v2 迭代方向

- 模板参数化：换行业只换参数不换模板（模板与逻辑分离）
- 与 legal-proposal-generator 编排：本报告作为服务方案的"行业背景"上游章节
- 输出"客户版 / 内部版"双版本开关

## 故障排除

| 现象 | 排查 |
|---|---|
| `playwright 未安装` | `pip install playwright && python -m playwright install chromium` |
| `[warn] mmdc 未安装` | mermaid 图降级为代码块,不影响 PDF 主流程；如需 SVG 图：`npm i -g @mermaid-js/mermaid-cli` |
| Chrome 未找到 | macOS 装 Google Chrome；Linux：`apt install google-chrome-stable` |
| 企查查候选列表多匹配 | 必须把候选列表**完整展示给用户**,**不得自动选择排名第一的候选项**(E4 铁律) |
| 信源找不到第二独立来源 | 在引用处加 `[单一信源]` 标记,不得隐去 |
| 封面变体未应用 | 确认 `config/report-profile.md` 的 `cover_style` 字段,合法值：`C-geo / D-diagonal / E-flip / F-grid` |
| 调色板未应用 | 确认 `color_palette` 字段,合法值：`bluebook / service-plan / burgundy / forest / tech` |
| 报告还是深蓝色 | 检查 `color_palette` 字段是否填了非 bluebook；HTML 文件应能搜到对应主色 hex（如 `#722F37`） |
| 首启不知道填什么 | 参考 SKILL.md "首启向导"段的 7 个问题清单；Agent 用 harness 自带的提问机制（如 AskUserQuestion）逐项问 |

## 引用资源

- 模板：`templates/report-skeleton.md`
- 设计：`references/report-template.html` / `references/design-spec.md` / `references/palette-presets.md`（5 个调色板比较）/ `references/covers/cover-{C,D,E,F}.html`
- 脚本：`scripts/render.py` / `scripts/pdf.py`
- 配置：`config/report-profile.example.md` / `config/report-profile.md`(gitignore) / `config/source-blacklist.txt` / `config/industry_sources.local.example.yaml`
- 数据纪律：`references/data-discipline.md`(企查查 E 路径铁律 + 网络检索信源优先级) / `references/source-priority.md`
- 信源映射：`references/industry_sources.yaml`(20 个内置行业 + 用户本地覆盖)
- 归档：`archive/`(历史报告 + 元数据 JSONL)
