# Changelog

## [1.5.15] - 2026-10-18

### 修复

- 泛化公开正文、历史记录与脚本注释中的授课来源锚点；补充日期、项目语境和来源标识组合检查，并保留合成正反例。
- 保留 PPTX、PDF 和双格式导出。显式格式优先，未指定时识别输出后缀，其余仍默认 PPTX；非法格式、转换异常及不支持的多文件 PDF 请求明确失败。
- 修正 PDF 使用示例、公开包断链、MIT 版权署名和安装依赖说明；不改变许可类型；发布字段归入标准 metadata。
- 发布打包拒绝覆盖已有输出与符号链接，验证实际候选相对链接。

- 普通转换、风格提取、预检和模板预览统一使用 Playwright Chromium，解除 macOS 对另装 Chrome 的隐含依赖；匿名配置默认介绍页数改为 0。

- PPTX 逐页隔离保留原内边距与内联排版样式，修复模板内容整体向左/上偏移；对有限的入场动画取终态，增加浏览器与 PPTX 坐标回归。

### 验证与边界

- 提供脱敏、打包及真实文件转换回归入口；检查实际文件、页数、原生文字与作者元数据。
- 模式扫描不能识别所有语义隐私，公开前仍需人工核对全部纳入文件；一次转换通过不代表所有输入或多轮 Agent 生成稳定。

## [1.5.14] - 2026-10-16 — 公开发布整改：本地配置隔离与个人资料迁移（TASK-019 阶段 A–C）

目标是让通用 slides 可分发：每位使用者用本地初始化配置身份、偏好与私有素材；没有姓名/头像/二维码也能正常制作课件。

### 新增

- **配置合同（阶段 A）**：`config/profile.schema.json` + `profile.example.json`；`scripts/load-profile.js`（五级解析顺序：显式 → 课件项目 → 技能目录本地 → 用户数据目录 → 匿名）、`init-profile.js`（引导模式 + 非交互回填，默认写 `~/.config/slides`，已存在拒绝覆盖，不扫描全盘）、`check-profile.js`（结构/版本/枚举/素材可读性校验，只报字段是否已填不打印资料值）。相对路径按被选配置文件所在目录解析；显式路径错误或坏 JSON 直接报错不回退。
- `references/configuration.md`：解析顺序、字段、展示开关与素材映射、资源策略（本地创作 vs 对外交付）、迁移步骤与发布边界。
- `references/styles/极简编辑白.json`：从旧个人风格抽取的中性可复用视觉预设。
- `slides/.gitignore`：本地配置与私有素材不入库。
- **「具体名称门禁」`scripts/check-privacy.js`**：用户定调「不是维护者私有名单，而是提交内容里明显含具体名称的都要过门禁，特别是配置文件」。通用模式检测 G1–G8（机构名/人名+职称/绝对路径/内部编号/联系方式/个人素材文件名/真实课程路径 + 配置文件从严要求空模板），泛指前缀（尤其/资深/面向…）不误报；有意保留的作者署名走 INTENTIONAL 登记表（file+正则+理由，可审计）。`pack-public.js` 接入门禁替代原私有词表方案，门禁不过拒绝打包；check-privacy.js 随包分发供使用者自审。负控实测：注入 14 类真实痕迹全命中（G1–G7 七类齐），泛指测试行零误报，配置模板非空字段 4/4 判违规，还原后干净树零命中。
- **私有目录结构定调（维护者）**：`assets/` 为 skill 常规素材目录（这才是 assets 的定义），图片/二进制默认 gitignored、公开素材用 `!` 显式豁免（附 assets/README.md 说明，随包分发）；私有配置 JSON 与偏好用 `.local` 后缀落在常规 `config/` 内被既有规则忽略（profile.local.json、个人风格 local.json、preferences.local.md）；`config/local/` 仅存旧版原件作恢复来源。
- **风格库字段补齐（38/38 全字段非空）**：为全部内置预设补齐引导字段——`promptSnippet`（给 AI 的英文风格描述）、`prohibited`（反设计禁例）、`components`（可复用组件配方，CSS 由各风格自身 palette 与字体渲染）、`tone`（调性关键词）、`spacing`（间距节奏）。逐条按各风格 description 与配色撰写，非模板套话；组件类型按用途指定（kpi-card / so-what / chart-caption 等），CSS 模板与组件语义对应且明暗风格通用。核心字段（name/description/source/slideDimensions/colors/typography/layout/cssVariables）原本已 38/38 完整，程序消费链路无缺口——本次补的是喂给生成环节的写作约束。

### 变更

- **工作流接入（阶段 C）**：`convert.js` 读同一配置决定 PPTX 作者元数据（`identity.name · organization`，未配置回退工具名）；坏配置 fail-closed 报错不产出；新增 `--config` 与 `--save` 别名；修正 `--save-style` 异步任务被 `process.exit` 提前杀掉的既有 bug。`extract-style.js` 自提取风格默认存个人风格目录（`$SLIDES_HOME/styles`），`--list-styles` 分内置/个人两组。
- `SKILL.md`：新增「本地配置」章节与发布字段；工作流步骤接入配置；去个人风格名与私仓引用；目录结构更新。
- `cn-deck-polish.md` §8/§9/§13：介绍页、收尾形态、素材策略改为按配置开关，去除个人绝对路径与私仓引用。
- `intake-checklist.md`：拆分「通用默认」与「个人默认（配置键）」，去除对私有上游技能的硬依赖。
- `merge-pitfalls.md` / `screenshot-framing.md` / `layout-theme-playbook.md`：去除私仓 skill 绝对引用与个人风格名。
- `example.html`：讲者改为虚构占位「示例讲者」。

### 迁移（阶段 B）

- 旧身份说明、个人品牌指南与个人风格文件 迁入 `config/local/`（整个目录 gitignored：Git 跟踪 = 可发布，被忽略 = 使用者私有；运行时不读取，发布包整体排除）；本人身份/素材/开关迁移到 `~/.config/slides/`。

### 发布字段

- 统一版本号为 `1.5.14`：修复此前 `SKILL.md`/`package.json` 停在 1.5.9、CHANGELOG 已到 1.5.13 的不一致。
- 新增 `LICENSE.txt`（MIT）与 frontmatter `homepage`/`author`/`license`（作者署名为发布元数据，与「生成课件的讲者身份」分离）。

### 边界与 NOT_VERIFIED

- 阶段 D/E 的公开发布包导出到公仓、正式发布**未在本轮执行**（需后续授权）。
- 移除 6 个外部参照风格预设（杂志墨水/靛蓝/森林/牛皮纸/沙丘、瑞士国际），改以设计方向自建两套原创预设：**深度报道**（编辑杂志风：暖骨白 `#FBF9F4` + 墨黑 `#14110F` + 砖红 `#B23A2E`，Source Han Serif 大标题 + 细分隔线）与 **客观网格**（瑞士国际主义方向：纯白 + 石墨黑 `#111111` + 信号红 `#E30613`，严格 12 栏左对齐网格、无装饰）。内置库 36 → 38，全部为自建或自课件提取，上游 AGPL-3.0 争议归零（维护者 拍板）；`styles/README.md` 保留 attribution 字段规范供未来外部参照时使用。
- 二维码内容解码、无旧上下文前向匿名/合成身份用例：NOT_VERIFIED，按计划矩阵结算。


## [1.5.13] - 2026-09-17 — cn-deck-polish §23 竖向引擎衬底同族 + §22 计数器按页分组

### 文档

- `cn-deck-polish.md` 新增 **§23**：竖向滚动引擎每页衬底必须与半透明 slide 同族——现象 / 根因三层（半透明底 + body 底色钉死 + 同步类无 CSS 消费端）/ `.page:has(.slide.light)` 声明式修法 / 非 16:9 视口 Playwright 带区采样验证（PDF 不暴露此缺陷）。源自 竖向演示回归样例 "有深有浅"缺陷。
- **§22** 补遗：每页计数器可能两处（chrome + 页脚），重编必须按页分组同号，按出现顺序编号会同页错位（回归样例，judge 渲染验收抓出）。
- `SKILL.md` 两处指针：cn-deck-polish 描述行更新至 §1–23；垂直 scroll-snap 引擎节补"克隆注意"。

## [1.5.12] - 2026-09-07 — `marginMode` 预设（none/compact/normal/wide） + margin 显式覆盖

### 新增

- `html2pdf` 新增 `marginMode: 'none' | 'compact' | 'normal' | 'wide'`（默认 `none`，多页 deck 维持 v1.5.10 行为不变）。
- 新增 `margin` 显式覆盖参数；与 `marginMode` 配合可按需切换。

### 验证

- 单元测试 `marginMode: compact on single page (smoke)` 通过。

## [1.5.11] - 2026-09-07 — html2pdf 保真增强（6 个可选项，默认行为与 v1.5.10 完全等价）

### 新增（全部 opt-in，默认关闭）

- `textRendering`: `geometricPrecision` 减少 CJK 字形栅格化为 Type3 的概率。
- `backgroundStrategy`: `freeze` 把 canvas 当前帧 snapshot 为静态图（保纹理）；`hide` 完全隐藏（最干净矢量文字）；`as-is` 不动（v1.5.10 行为）。
- `preferExactSize`: 整数像素尺寸，消除 `960.96×540.96` 浮点漂移。
- `outline`: PDF bookmarks，从 `[data-pdf-outline]` / `<header>` / `.kicker` 抽取（pdf-lib best-effort）。
- `tagged`: 输出 tagged PDF（可访问性）。
- `marginMode`: 边距预设（none/compact/normal/wide）。

### 改进

- 7 项单元测试覆盖默认路径与所有新选项组合（`scripts/tests/test-html2pdf-fidelity.mjs`），全部通过。
- `SKILL.md` 决策树段追加"html2pdf.js 保真选项表"+典型用法。

### 边界

- 默认行为零回归：v1.5.10 调用者产物与 v1.5.11 完全等价；新选项默认关闭，新行为仅在显式开启时生效。

### 背景

- 用户反馈 PDF 文字层可选中可搜索（v1.5.10 已达成），继续优化格式保真方向：不破坏现有路径、不阻塞已完成功能，新功能以可选项形式叠加。
## [1.5.10] - 2026-09-07 — html2pdf 水平翻页 deck 两处修复 + 决策树修订（文字层 PDF 恢复）

### 修复

- **[v1.5.2] `html2pdf.js`**：v1.5.1 的 `#deck static` 补丁不完整——当课件 `html,body { height:100%; overflow:hidden }` 时，static 化内容仍被裁成 1 页。补丁新增 `html, body { height:auto !important; overflow:visible !important }`。
- **[v1.5.3] `html2pdf.js`**：新增导出态约定——打印前给 `body` 加 `.exporting` 类，课件可借此隐藏放映辅助元素（`#hint` 快捷键提示、`#notes` 备注面板）。约定优于脚本硬编码元素名。

### 改进

- `SKILL.md` 转换脚本决策树修订：水平翻页 carousel 自 v1.5.2 起默认用 `html2pdf.js`（文字层 PDF），`html2pdf-carousel-hd.js` 降为 fallback；v1.5.1 时代"必须用 carousel-hd"的结论保留为历史教训备查。

### 验证

- 37 页 carousel deck（`#deck` flex + fixed，宣讲课件回归样例）：修复前 1 页/图片型 → 修复后 37 页、`pdftotext` 全文可提取、HUD 关键词全文 0 命中。

### 背景

- 用户反馈宣讲课件 PDF 无文字层。追溯确认：脚本从未被删改（`html2pdf.js` 上一次实质变更即 a4d5ab5a v1.5.1）；图片 PDF 的流程根源是 v1.5.1 补丁不完整 + 决策树把截图法固化为"必须"。

## [1.5.9] - 2026-09-04 — 动态背景静态保留，前景原生可编辑

### 新增

- 新增 `--background-mode auto|freeze|native`；默认在检测到 WebGL / ASCII / canvas 等浏览器专属背景时，只冻结背景层。
- 新增 PowerPoint 讲者备注导出，支持 slide `data-note` 与 `[data-speaker-notes]`。
- 新增 `references/native-pptx-rebuild.md`，固化 Codex Artifact Tool 与本地 PptxGenJS 两条对象级重建路径。
- 新增两页动态背景回归样例，覆盖背景图、原生文本与 notes 三类断言。

### 改进

- 旧身份说明曾包含讲者身份、素材路径与授课足迹（现已迁入使用者本地配置），规定介绍拆成“身份与实践成果 / 授课现场”两页。
- `SKILL.md` 明确 HTML 动态、PPTX 静态背景与前景可编辑的能力边界，并修正品牌指南真实路径。

### 修复

- 避免动态背景课件导出 PPTX 时在“整页不可编辑”和“背景完全丢失”之间二选一。

## [1.5.8] - 2026-08-16 — 课件迭代三轮事故沉淀（§20-22 组件适配 / 720 预算与 DOM 验证 / 页码同步）

### 改进

- **`references/cn-deck-polish.md` §20-22** 三条新增（来源：课件迭代的实际问题）：
  - **§20 复用既有组件前先读它的 CSS**——`.guardrail` 是横排行组件（`100px 180px 1fr`），误放进三栏网格导致正文列被挤到 28-59px、文字竖排细条，三页 9 卡同病且视觉模型两轮误报"正常"；规则：复用 class 前 grep 其 CSS 确认布局方向，多栏卡片一律用内联竖排 pattern（附模板），验证信号 = 正文 p 宽度 < 200px 即布局已坏。
  - **§21 720p 视口预算 + DOM 几何验证**——overflow:visible（§14）≠ 内容可见，scroll-snap 下超 720 内容画到下一页顶上仍不可见（事故：callout 底边 930px 整块丢失）；给出高度预算表（标题 ~175 / 内联三栏卡 ~140 / callout 单行 ~80 双行 ~115，总高 >600 砍文字），验证只认 getBoundingClientRect 实测（最后元素 bottom ≤ 720），截图+视觉模型仅辅助；截图循环先核对 chrome 标签防 0/1 基索引错位误报。
  - **§22 结构一动页码全量重编**——增删/移动页面后同步四处（chrome 计数器 / 头注释页数 / 目录环节清单 / 计数器序列连续性断言），脚本化不手改；与 merge-pitfalls §5 的 PAGENO 重编号互为呼应。
- 文末审计 grep 清单同步纳入 §20-22 排查信号。

## [1.5.7] - 2026-08-14 — 同职责元素跨页字号统一（§19）

### 改进

- **`references/cn-deck-polish.md` §19** 新增（来源：课件用户反馈）：
  - **核心原则**：同职责元素（收尾金句 callout、警示框、底部说明）跨页字号必须统一；**配色可随语义区分（金=收尾、红=警示），字号不随配色走**。
  - **字号基准**：标签 mono ~11px / 主句 serif-zh 700 **17.92px** / 副句 sans-zh body **14.85px**。
  - **动态调整原则**：能一致则一致，版面容不下才调（可下调一档到 ~16px 或拆主句+副句分层）。
  - **审计 grep 模板**：找 callout 内 `class="h-md"`（应改 17.92）、非基准 `font-size`、把 body 当主句使用的情况。
  - **反例**：课件早期 `.callout.gold.tail` 主句字号出现 5 档（29.44 / 19 / 17.92 / 14.4 / 14.85px），修复后统一。
- 文末审计 grep 清单同步纳入 §19 排查信号（"同职责元素跨页字号是否统一到 17.92px 基准"）。

## [1.5.6] - 2026-08-14 — 课件多轮精修沉淀（§15-18 流程/并列卡/命名/专有名词）

### 改进

- **`references/cn-deck-polish.md` §15-18** 四条新增（来源：课件多轮用户反馈）：
  - **§15 流程/套件类：总览在前 + 每步单独一页**——多步骤流程不要只做一页步骤卡总览，先总览（全貌）再每步一页（输入→过程→输出→沉淀）。用户原话"35 页放前面，后面再讲第一步第二步…一个一个流程"。
  - **§16 并列卡布局：内容少用 2×2，内容多用 1×N**——按内容密度定网格列数；每卡 3 行以上用 2×2（铺开），1-2 行用 1×N（紧凑）。P17 红黄绿灯 1×4 空白 → 2×2 饱满。
  - **§17 链路/Skill 命名要精确**——涉及具体 Skill/产品名必须核对真实名称（源仓库/手册），不要凭"看着像"推断。反例：将单文书分析误标为综合研判；用户纠正时立即全 deck grep 改齐。
  - **§18 产品专有名词在 hero+目录+正文统一**——新引入名词（律师服务套件/专家套件）全 deck 统一；hero 用 `<br/>` 拆 3 行更清晰；grep 审计残留"链路"逐处判断保留/改。
- 文末审计 grep 清单同步纳入 §15-18 排查信号。

## [1.5.5] - 2026-08-14 — 1280×720 固定画布的 overflow 三层陷阱

### 改进

- **`references/cn-deck-polish.md` §14** — 1280×720 browser-deck 的 overflow 三层硬裁切问题(`.slide / .frame / .canvas` 都默认 `overflow:hidden`,导致超 720 内容被截)。**统一改 `overflow:visible`**,scroll-snap 仍正常翻页但页内超出不被裁。
- **审计 grep** 模板:`grep -nE '\.(slide|frame|canvas)\{[^}]*overflow:\s*hidden'`,命中即改 visible。
- **唯一保留 hidden 的例外**:头像 `.avatar-slot`、截图墙 `.fp-thumb / .fp-card`、sprite `.icon-sprite`——单元素内裁切,不属画布级硬裁。
- **来源 / 缘由**: 历史用户反馈"不要超出就直接裁掉,这非常不好"。某课件页面左侧圆圈被 `.canvas{overflow:hidden}` 截掉,讲者看不到。修复后 P36 圆圈完整可见。**任何固定画布 browser-deck 都默认该改**。

## [1.5.4] - 2026-07-16

### 新增

- **`references/merge-pitfalls.md`** — 工程层面踩坑沉淀:独立 `<style>` 块兜底污染 + 多源 HTML 同步主题注入(`inject_light.py` 幂等模板)+ 源文件 style 块纯净规则 + merge.py dedup/独立 style 工程模式 + 验证 checklist + 何时不用 + 横向关联。
- **来源 / 缘由**: 一次真实讲课课件制作中，主题 override 完全失效。诊断: `getComputedStyle` 返原始值;`document.styleSheets` 枚举 cssRules 不含 override;`--paper` 巧合同值误导自验。**真因**:多 700 行 `<style>` 块被 CSS 解析器丢弃(源文件 stray `<style>` 字面 + 中文开发备注污染)。**根治**: 把 override 放进独立第二个 `<style>` 块,独立 stylesheet 各自解析,立刻生效。**任何 multi-source HTML 合并项目**都可能踩同样坑。DECISIONS 同步登记。

## [1.5.3] - 2026-07-16

### 新增

- **`references/ppt-writing-rules.md`** — 五条对外 PPT 硬规则:不打钟点表 / chrome 精简 / 该分块就分块 / 不传播焦虑 / 语气去 AI 化。附自查清单(交付前 5 分钟)+ 替代表(焦虑 → 事实 / AI 化 → 同行口吻)。背景:用户多次纠正后明确要求沉淀,以后不希望逐次纠正。该文件是本 skill 的硬规则层,新建任何对外 PPT 必先扫一遍。

## [1.5.2] - 2026-06-30

### 改进

- **SKILL.md 新增"选哪个转换脚本"决策树**：明确区分 3 个转换入口（`convert.js` / `html2pdf.js` / `html2pdf-carousel-hd.js`）的适用场景与检测特征
- **carousel-hd 强制使用提醒**：水平翻页 deck（`#deck { position:fixed; width:10000vw }`）必须用 `html2pdf-carousel-hd.js`，不能用 `convert.js` / `html2pdf.js`（后者会输出 1 页空白 PDF）

## [1.5.1] - 2026-06-30

### 修复

- **html2pdf.js 水平翻页 deck 修复**：原代码只设置 `.slide { page-break-after: always }`，但当 HTML 用 `position:fixed; width:10000vw; transform: translateX(...)` 实现水平翻页时，`#deck` 容器仍 fixed 定位——Chromium 打印只截 1 张 slide。修复：注入额外 CSS 把 `#deck` 改为 `position: static; width: auto`，让所有 slide 垂直堆叠正确分页。

  - **触发场景**：`#deck { position:fixed; width:10000vw; height:100vh }` 模式（reveal.js 自定义 / 自写水平翻页）
  - **症状**：detectCount 显示"38 个幻灯片"但 PDF 实际只有 1 页
  - **修复**：`#deck { position:static !important; ... }` + `.slide { width/height: page mm; flex:none; page-break-after:always }`

## [1.5.0] - 2026-06-02

### 新增

- 新增 `references/templates/` 完整 HTML 模板库：12 个可渲染页面模板（封面、内容列表、数据看板、金句、时间线、左右对比、章节分隔、证据卡片、流程步骤、风险矩阵、培训讲义、图文混排）+ `_base.css` 共享设计系统 + `README.md` 索引
- 新增 `scripts/generate-previews.js`：用 Playwright 为每个模板生成缩略预览图
- 新增 `references/templates/previews/`：12 个模板预览截图 + `index.html` 预览索引页
- 新增 24 个风格 JSON（总计 42 个）：杂志墨水/靛蓝/森林/牛皮纸/沙丘、瑞士国际、学术深蓝、医疗薄荷、金融深灰、工程蓝图、教育粉笔、咨询蓝、投行黑、保险蓝白、政策公文、房地产金、赛博朋克、极简日式、北欧极光、毛玻璃、创业路演、餐饮暖橙、快消活力、婚礼香槟
- 动画系统：4 种入场动画 + 6 级延迟级联 + 4 种页面转场策略

### 改进

- 设计系统升级：从配色方案升级为完整设计语言（排版刻度、间距系统、组件模式、视觉层级规则）
- 风格库按场景分类：法律/政务、商务/金融、科技/创意、杂志/设计、教育/学术、行业/场景
- `browser-guide.md` 新增完整动画指南：触发机制、转场策略、自定义动画、降级保底
- SKILL.md 工作流引用从 `templates.md` 指向 `templates/` 目录

## [1.4.0] - 2026-05-30

### 新增

- 新增 `references/layout-theme-playbook.md`，提供需求澄清字段、主题选择字段、版式家族、版式选择速查和反泛化设计规则。
- 新增 `scripts/validate-slides.js`，使用本地 Playwright 预检 HTML 幻灯片的 slide 容器、尺寸、溢出、渐变/inset 阴影、裸 `div` 文本、远程/base64 图片、文字背景/边框等风险。
- 新增 npm 命令 `validate` 与 `validate:strict`，支持转换前宽松检查与严格阻断。

### 改进

- 扩展 `references/templates.md`，补充时间线、流程、对比矩阵、KPI、案例/证据、法律培训、风险矩阵等高频页面模板。
- 扩展 `references/pptx-guide.md`，补强固定视口、幻灯片尺寸、文字换行、图片、本地字体、渐变/阴影、PDF 光栅化风险和转换前预检清单。
- 更新 `SKILL.md`，将标准流程明确为需求澄清 → 研究/大纲 → 风格/版式 → HTML 生成 → 预检验证 → PPTX/PDF 转换 → 最终 QA。

### 技术优化

- 验证脚本采用纯 Node.js + Playwright 实现，提供缺失依赖和 Chromium 未安装时的明确安装提示，不引入云依赖或 API Key。
- 保持 `html2pptx.js`、`html2pdf.js` 和核心转换引擎不变，将稳定性控制前移到输入 HTML 预检阶段。

## [1.3.1] - 2026-05-17

### 修复

- 恢复 PR #6 / `e27d357` 误删后遗漏的 `references/` 幻灯片参考资料，共 18 个文件。
- 恢复范围包括研究、风格、品牌指南与样式预设相关参考文件，避免全流程创作链路缺少历史上下文。

## [1.3.0] - 2026-04-12

### 变更
- **整合 PPT 生成技能体系**：将本地私有 PPT 生成目录下三个子技能（主题研究、品牌视觉、HTML 引擎）整合为 `slides` 的一体化工作流
- **SKILL.md 升级**：标题从「幻灯片生成 + 风格管理」升级为「幻灯片全流程创作工具」，工作流从 3 步扩展为 4 步（研究 → 风格 → 生成 → 转换）
- **风格库表格补全**：从 9 个扩充为完整的 18 个预设风格
- **目录结构补全**：补充 `example.html`、`user.md` 等已有但未列出的文件
- **修正过时路径**：`research_framework.md` 中指向已删除 `PPT生成/` 的引用已更新

### 新增
- **主题研究模块**：整合既有研究框架、报告模板和大纲 Schema 到 `references/research/`
- **个人风格导入**：将已有设计变量转换为风格库 JSON（现已迁入使用者本地配置）
- **品牌指南**：整合已有个人品牌规范（现已迁入使用者本地配置）

### 废弃
- 本地私有的 PPT 生成目录（主题研究、品牌视觉、HTML 引擎三个子技能及课程产出物）整合后已不再单独保留

## [1.2.0] - 2026-04-12

### 变更

- **重命名**：skill 从 `html2pptx` 更名为 `slides`，反映端到端创作工作流（内容 → 幻灯片 → PPTX/PDF）

### 新增
- **风格提取模块**：新增 `extract-style.js`，从任意 HTML 幻灯片提取配色、字体、布局等风格参数，输出结构化 JSON
- **风格库**：内置 17 个预设风格 JSON + 5 个原始参考文档（`references/styles/`）
- **风格参考文档**：新增 `references/style-reference.md`，整合 18 个配色方案、字体推荐、布局参考，面向 AI 生成
- **CLI 增强**：convert.js 新增 `--extract-style`、`--save-style`、`--list-styles` 选项
- **SKILL.md 升级**：描述完整创作工作流（提取风格 → AI 生成 → 转换输出）
- **html-guide.md 增强**：新增「风格友好写法」章节，指导使用 CSS 变量统一管理配色

## [1.1.0] - 2026-04-12

### 修复
- **多页尺寸自动检测**：不再硬编码 960×540，从首个 `.slide` 元素的 computed style 读取实际尺寸（如 1000×562.5px）
- **深色背景幻灯片**：修复多页隔离时背景色提取顺序问题——先读取原始背景再注入 CSS 覆盖，避免 `.slide` CSS 类背景覆盖深色背景
- **DIV 裸文本提取**：新增对无子块元素但有直接文本的 `<div>` 的提取（页码、badge、箭头等），同时保留背景形状
- **PDF 逐页输出**：重写 `html2pdf.js`，检测 `.slide` 容器后注入 `@page { size }` + `page-break-after` 实现逐页输出，不再截取整个 body
- **PDF 文字可选**：添加 `page.emulateMedia({ media: 'screen' })` 强制屏幕媒体类型，避免 print 模式导致文字不可选

## [1.0.0] - 2026-04-11

### 新增
- 核心 HTML → PPTX 转换引擎（基于 Playwright + PptxGenJS）
- HTML → PDF 转换模块（基于 Playwright page.pdf()）
- CLI 批量转换工具（convert.js）
- 支持任意 HTML：视口相对单位（100vh、clamp()、vw）、flexbox、grid
- 自动多页检测（.slide / section 容器）
- 视口强制适配（forceViewport）
- 宽松模式（lenient）：警告代替中断
- 可编辑文本框输出（非截图）
- 支持中文环境（微软雅黑 / PingFang SC）
