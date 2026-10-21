# 中文课件排版与去冗余细则

> 来源：多轮真实培训课件（半天版 HTML deck）反复精修沉淀。生成/审计**中文**演示文稿时按本细则，避免重复踩坑。与 `style-reference.md`（设计哲学/反 AI-slop）、`layout-theme-playbook.md`（版式家族）互补——那两份讲"怎么好看"，本份讲"中文课件常见的冗余与隐形坑怎么避"。

## 1. 中文强调不用斜体

- CJK 字体无真斜体，浏览器合成斜体（fake oblique）非常难看——这是中文课件最常见的一眼假。
- 强调一律用「**加粗 + 金色**」：去 `font-style:italic`，加 `font-weight:600`。
- 英文/数字的 Playfair 斜体可保留（"the real bar"、①②③、序号数字类）——那些不是中文，斜体好看。
- 落地：`.nb-gold` / `em` 规则不要 `font-style:italic`；中文 gold 内联 span（`style="color:var(--gold);font-style:italic"`）改成 `font-weight:600`。

## 2. 页眉页脚极简

- chrome（顶部）一句够了：章节代号 + 页码（如 `MODULE 02 / SCENE 03`）；**不重复**主办/日期/讲师署名。
- foot（底部）常空（`<div class="foot"></div>` 留 `margin-top:auto` 占位、去文字）——底部空间留给 nav 圆点/大纲。
- 删 `FRONT xx / N · COVER` + `半天版 · 约 N 小时` 这类与 chrome/封面重复的底部元数据。
- 参照基准：chrome 极简、foot 多为空的克制型 magazine deck（正文附录的排版基准值即从其抽取）。

## 3. 封面与分节 hero 去冗余

- 封面只留：主题 hero + 主讲 + 日期地点。**不写**主办方 / 面向对象 / 时长——这些在封面/通知/方案里已有，再写一遍是噪声。
- 模块分节 hero 只留 kicker + 主题 h1 + lead。**不重复**「讲师·主讲 / 律协 / 日期地点 / 模块描述 / 时长」整块。
- hero 页内容默认顶对齐会下半留空——加 `.slide.hero .frame{justify-content:center}` 垂直居中。

## 4. 去说明性小标签 / 出处标注

- 删 `.cite` 类出处标注（"— XX 话术 / — S5 核心论点 / — 六步法总览·半天版"）——金句/引语本身够有力，不需要"— 出处"小字。
- 删与正文重复的 callout label（"半天版关键 / 核心观点 / 为什么听这位讲者"）。
- 原则：每句话要么承担信息，要么删掉；"说明这句是什么"的元标签基本都可去。

## 5. 照片比例：完整显示，勿强裁

- 头像（人像照）用 `object-fit:contain`（完整显示，不裁头切脚）；slot 太宽时配 `max-width/max-height:auto`。
- 内容截图/培训照片用**匹配宽高比**（`aspect-ratio:16/9` 或 `4/3`），勿 `fixed-height` 把横向图强裁成方/扁条。
- **"图变两行" 与 "图显示全" 会冲突**：两行 + 足尺寸横向图单页放不下。取舍时**优先"显示全"**——宁可 1 行足比例，不要 2 行强裁。

## 6. 内联色必须与页底匹配（防隐形字）

- 深色页里 `color:var(--ink)` = 深字深底 = **隐形**；浅色页里 `color:var(--paper)` = 浅字浅底 = **隐形**。源 HTML 里手写内联色最易踩。
- 兜底 CSS（一处修全部同类 bug，`!important` 压内联）：
  ```css
  .slide.dark [style*="color:var(--ink)"]{color:var(--paper)!important}
  .slide.light [style*="color:var(--paper)"]{color:var(--ink)!important}
  ```
- 更彻底：用 role 变量（`--fg` 随 `.slide.dark/.light` 翻转），元素统一 `color:var(--fg)`，从根上避免。

## 7. 章节计数全链路同步

- 删一个场景/演示时，**grep 全 deck** 改：「N 个 Skill」「N 场景」「N 类场景」「N 个执业场景」+ Skill tag 清单 + 目录 + 过渡页预告——数字必须一致，别出现"hero 说五个、目录说六个、tag 列六个"打架。
- 过渡页（"下一模块看 N 场景"）和收束页（"N 场景的共同点"）最易漏。

## 8. 个人介绍：按配置决定拆几页（勿一页塞满）

> 是否生成介绍页、生成几页由本地配置决定：`presentation.intro_pages`（`0` 不生成 / `2` 两页 / `3` 三页）。**匿名默认（未配置身份）不生成介绍页**，不要用原作者资料补位。

- 两页形态：身份 + 实践成果一页；代表性现场一页。
- 三页形态：身份页；授课路径总览页；代表性现场照片页（不为凑两页而缩小名单和照片）。
- 不要把"一句话 hook / 履历 / 开源 / 照片 / 二维码"全塞一页——信息过载。
- 身份页只留支撑本次主题的证据，不做完整简历；缺项省略，不虚构。

## 9. 收尾页

> 形态由 `presentation.closing_mode` 决定：`summary`（总结金句）/ `thanks` / `none`。

- 收尾用「总结金句」，**不用** `thank you / 下课 / 微信群见 / 讲师·日期·地点签名行`（冗余）。
- 金句要有记忆点（范例："你教助理怎么做，就教 Agent 怎么做。"）。
- 二维码是否出现完全由 `show_wechat_qr` / `show_public_account_qr` 决定：关闭时**不读取图片**，也不留占位框；启用而缺图片按校验错误处理，不得用旧码或生成假码顶替。

---

## 10. 招牌背景要"看得见"（ASCII/WebGL 混合模式）

- 浅底 hero 的 ASCII 金色层用 `mix-blend-mode:multiply`（**screen 在浅底会把金色滤到几乎不可见**——这是"动态效果看不清"的常见根因）；深底用 screen。
- 落地：加更特异性规则覆盖默认——`.slide.light.hero canvas.ascii-bg{mix-blend-mode:multiply;opacity:.95}`。
- ASCII 金色 alpha 上限别太低（`Math.min(0.7+, alpha)`，原 0.55 偏淡）；"稍微明显一些"通常 = 调高 alpha + 确认 blend mode 与页底匹配。

## 11. 配色：深浅搭配，勿走极端

- 不要"全浅"（太平、缺节奏）也不要"全深"（压抑）。用 **浅（封面 / 介绍 / 目录 / 内容页）+ 深（分节 hero / 章节分隔 / accent 页）** 的节奏。
- 双底驱动：`.slide.dark`(ink 底 + paper 字) / `.slide.light`(paper 底 + ink 字)；WebGL 双 canvas 随 `body.light-bg` 切明暗。
- 一页之内不要混用底色（除非有意 accent）。

## 12. 翻页与导航交互（浏览器投屏）

- 形态：保留 scroll-snap 全屏滚动，叠加——`← →/space/PgUp/PgDn/Home/End` 键盘翻页 + 底部 `#nav` 圆点（active 金色拉长）+ `ESC` 大纲缩略图网格（点卡片跳转）+ `B` 静态切换。
- 圆点**深浅自适应**：默认白点（深底可见）+ `body.light-bg #nav .dot` 墨点（浅底可见）+ active 金色双用。
- 大纲 DOM 由 JS 自建（不写死 HTML），克隆各 slide 缩放成缩略图。

## 13. 素材走配置路径（本地创作不复制）

- 头像 / 二维码 / 字体等私有素材路径来自本地配置 `assets.*`（见 [configuration.md](configuration.md)）；**相对路径相对于被选配置文件所在目录解析**，也允许显式本机绝对路径。本地创作时直接引用配置里的路径，不复制到课件目录 → 单一来源，素材更新全 deck 跟着走。
- **发给他人的 HTML/PPTX 必须另做资源打包**：把本次明确启用的素材复制进该课件的资源目录并改为相对引用，核移动目录后可打开。不得把"路径写进了配置"当成图片已脱离发布范围。
- file:// 下带空格的绝对路径用**字面空格**即可（Chromium 实测 naturalWidth 真值，无需 %20 编码）。

---

## 附录：排版基准值（从规范样板抽取）

> 以下基准值取自一套主题化 magazine deck（chrome/foot 最克制的克制型样板）。新 deck 可直接对齐这些数值，再按内容密度微调。

- **chrome（顶）**：`font:mono`、`text-transform:uppercase`、`letter-spacing:.18–.2em`、`opacity:.6–.7`；内容只放**单一标识**（`02 / SPEAKER PROFILE`、`课程结构`），不堆日期/讲师/时长。
- **foot（底）**：`font:mono`、`opacity:.5–.55`；**内容页常空** `<div class="foot"></div>`（留 `margin-top:auto` 占位），封面才放课程名。
- **kicker（h2 眉标）**：`font:mono`、`letter-spacing:.28–.3em`、`opacity:.6–.7`；不要与 chrome 重复同一章节名（重复=左上角两份）。
- **标题刻度**（按密度选）：`.h-hero` 8–14vw / `.h-xl` 4.4–9vw / `.h-sub` 2.6–3.1vw / `.h-md` 2.3vw / `.lead` 1.7–2.6vw / `.big-num`/`.stat .n` 5–10vw。
- **组件**：`.callout`(border-left 3px + serif-zh + `max(15–17px,1.2–1.4vw)`)、`.rowline`(`N:2:N` 网格 + border-top)、`.pillar`(flex column gap)、`.pipeline`(`repeat-N`)、`.stat-card`(label/nb/unit/note)。
- **网格 API**：`.split`(1:1)、`.split-55`(55:45)、命名比例网格（`grid-2-7-5`=7:5、`grid-3-3`）——用名字而非裸 `1fr 1fr`，可读。
- **主题变量**：`:root` 集中定义 `--ink/--paper/--accent` 等，散落的 `rgba()` 一律走 `var(--ink-rgb)/var(--paper-rgb)`，换主题只改 :root。

---

**生成时**按 §1–22 逐条过；**审计已有 deck** 时按此 grep 排查：斜体 / `.cite` / foot 文字 / 内联 ink-on-dark / 计数打架 / 浅底 screen-blend / **素材是否按 [configuration.md](configuration.md) 的「本地创作引用 / 对外交付打包」两种策略** / **`overflow:hidden` on `.slide / .frame / .canvas`（见 §14）** / **流程类是否有总览+每步一页（§15）** / **并列卡 2×2 vs 1×N 是否按内容密度（§16）** / **Skill 名是否核对真实（§17）** / **专有名词 hero+目录+正文是否统一（§18）** / **同职责元素跨页字号是否统一到 17.92px 基准（§19）** / **复用组件前是否 grep 过其 CSS 布局方向（§20）** / **新改页内容是否 DOM 实测装进 720（§21）** / **结构变动后页码计数器是否全量重编且连续（§22）**。

## 14. 1280×720 固定画布的 overflow 三层陷阱（硬裁切 vs 内容可见）

固定 1280×720 browser-deck（`body.scroll-snap-type:y proximity` + `.slide 100vh`）的画布裁切来自**三个层级**，每一层都会硬截掉超 720 的内容——讲者讲不到溢出部分，学员也看不到：

| 层级 | CSS | 影响 |
|---|---|---|
| `.slide` | `overflow:hidden` | 整页超 100vh 截掉 |
| `.frame` | `overflow:hidden` | frame 内（h2+body+主内容区）超 flex 可用高截掉 |
| `.canvas` | `overflow:hidden` | 1280×720 缩放画布外的内容截掉（最常踩，因 hard 尺寸+`transform:scale`） |

**用户原则**（课件迭代 反馈）："不要做硬性限制，不要超出了就直接裁掉，这非常不好。"

**正确做法**：**三处全部改 `overflow:visible`**。scroll-snap 仍按 `.slide` 边界对齐（页面跳转正常），但页内超出不被裁，讲者可滚到看到；`.canvas` 改 visible 后超 1280×720 的内容会显示在缩放画布外（不模糊，缩放容器外层是 `.slide` 的 visible 区域）。

**修复模板**（grep 三个 `overflow:hidden` 一起改）：
```css
.slide  { overflow:visible; scroll-snap-align:start; }   /* 替代 overflow:hidden */
.frame  { overflow:visible; }                            /* 替代 overflow:hidden */
.canvas { overflow:visible; transform:scale(var(--s,1)); } /* 替代 overflow:hidden, 保留缩放 */
```

**审计 grep**：`grep -nE '\.(slide|frame|canvas)\{[^}]*overflow:\s*hidden'`——任何命中都按上表规则改 visible。

**唯一保留 `overflow:hidden` 的例外**：`.avatar-slot`（头像圆形裁切）、`.fp-thumb` / `.fp-card`（固定 aspect-ratio 截图墙）、`.icon-sprite`（隐藏 sprite）。这些是「单元素内裁切」，不是「画布级硬裁」，不影响内容可见性。

## 15. 流程/套件类内容：总览在前 + 每步单独一页

多步骤流程 / 多 Skill 套件类内容（流水线、链路、服务流程），不要只做一页"步骤卡总览"就结束——**先总览（让学员看到全貌），再每步单独一页讲清该步的功能**。

- **总览页在前**：grid `repeat(N,1fr)` 步骤卡展示全流程（N 步、每步 Skill 名 + 一句功能 + 留下什么），让学员先建立"整条线"的心智。
- **每步一页**：总览后每步独立一页，用 scene-board 三段式（输入 → 过程 → 输出 → 沉淀），单独讲清该步的输入、动作、交付和沉淀。
- 用户原话（课件迭代）："35 页应该放到前面，然后后面再讲第一步、第二步、第三步……一个一个流程"——**总览是"地图"，分步页是"放大镜"**。
- 页数预算：总览 1 页 + 每步 1 页（6 步 ≈ 7 页），比单页挤 6 卡更清晰、更可讲。
- 反例：只做一页 6 段 pipeline（每步一句）就结束 = "非常单薄"，讲师讲不透、学员记不住。

## 16. 并列卡布局：内容少用 2×2，内容多用 1×N

并列信息卡（红黄绿灯、风险分级、分类对号入座）的网格列数，**按内容密度定，不按"有几项"定**：

- **每卡 3 行内容以上**（标题+说明+处理动作+举例）→ **2×2**（每卡加宽，内容铺开，不拥挤）
- **每卡只有 1-2 行**（标题+一句）→ 1×N（4 卡一排，紧凑）
- 用户反馈（状态卡片布局）："中间空白太多，不符合要求"——1×4 时每卡只 2-3 行，横向挤、卡内空；改 2×2 后每卡三行铺开，无空白。
- **信号**：用户说"中间空""留白太多" → 多半是 1×N 列 + 内容稀疏；改成 2×2 或 2 行布局，或给每卡补内容行。

## 17. 链路/Skill 命名要精确，别想当然

涉及具体 Skill / 产品 / 组件名时，**必须核对真实名称**（源仓库 / 手册 / 用户确认），不要凭"看着像"推断：

- 反例（课件迭代）：把“单份文书解读”误写为“综合案件研判”——两类任务的输入与输出不同，应核对目标工具的实际名称和能力。
- 规则：
  - 链路/套件页 → 按**该步在该工作流中的真实角色**选 Skill（前置分析用 legal-case-analysis，判决书深读用 litigation-analysis）
  - 单 Skill 演示页 → 按**实际演示的那个 Skill** 命名
  - 不确定时查源仓库 `legal-skills/skills/<name>/SKILL.md` 的 `name` + `description`，不要猜
- 用户说"XX 不是 YY，是 ZZ"时，**立即全 deck grep 该名**（chrome/正文/Skill 文件结构/识别场景列表），全部改齐，不要只改一处。

## 18. 产品专有名词（套件/专家套件）在 hero + 目录 + 正文统一

新引入的产品专有名词（如"律师服务套件""专家套件"），**必须全 deck 统一**：

- **hero 分节标题**：主标题明确用该词（如"单 Skill + Skill 专家套件 全程演示"），如需换行用 `<br/>` 拆成 3 行（单 Skill / + Skill 专家套件 / 全程演示）更清晰
- **课程目录页**：与 hero 用同一词（"单 Skill 与专家套件"）
- **正文**：概念页 / callout / 收束页用同一词，避免"链路""套件""流水线"混用
- **grep 审计**：`grep -n '链路' deck.html` 找残留，逐处判断是"内部环描述"（保留）还是"应统一为套件"（改）
- 用户原话（课件迭代）："肯定要改成单 Skill 加 Skill 专家套件"——hero 用专家套件，但内部"链路准备/链路第 0X 步"作为套件的环描述可保留（套件由多个环/步组成）。

## 19. 同职责元素跨页字号统一（配色可异，字号必须齐）

不同页面里**承担同一职责**的元素（收尾金句 callout、页面底部警示框、底部独立说明块等）应当用同一字号层级。**配色可以随语义区分（金=收尾、红=警示），字号不随配色走**。

用户原话（课件迭代）："同样的这个说明，在不同页它的配色、字体大小都不太一样。我理解有一些地方它是为了有一些颜色的这个区分，但是尽量字体大小它最好是比较统一。"

### 字号基准

与 §2、§6、附录排版基准保持一致：

| 层级 | 字体 | 字号 | 备注 |
|---|---|---|---|
| 标签（ct / kicker） | mono | ~11px | letter-spacing .1–.28em |
| 主句 / 金句 | serif-zh 700 | **17.92px** | line-height 1.3–1.45 |
| 副句 / 要点 | sans-zh body | **14.85px** | line-height 1.55–1.7 |

### 适用范围

- `.callout`、`.callout.gold`、`.callout.gold.tail` 内的主句/副句
- 页面底部独立说明框（警示框、收尾块）：保持"标签+主句+副句"三层结构
- 主句、警示、收尾语义都按这套层级走

### 动态调整原则

> **能一致则一致，版面容不下才调。**

- 内容较长（4+ 条要点、长引语）或卡片高度受限时，可拆成"主句+副句"分层；仍放不下时下调一档到 ~16px
- 但版面有空间时必须回到 17.92px 基准——不要为了节省空间就用小字

### 审计 grep

```bash
# 找 callout 内仍用 h-md (29.44px) 的主句 — 应改为内联 17.92px
grep -nE 'class="callout[^"]*"[^>]*>[^<]*<[^>]*class="h-md"' deck.html
# 找 callout 内非基准字号
grep -nE 'class="callout[^"]*"' deck.html | grep -E 'font-size:.*px'
# 找 body 类被作为主句使用（应为 17.92 而非 14.85）
grep -nB1 'class="body"' deck.html | grep -E 'callout'
```

### 反例

课件 早期版本：`.callout.gold.tail` 主句字号出现 **5 档**：29.44px（h-md）、19px、17.92px、14.4px、14.85px（body）——同一 deck 内同职责元素字号不一致。修复后统一到 17.92px 主句 + 14.85px 副句 + 11px 标签，跨页 10+ 处 callout 一致。

## 20. 复用既有组件前先读它的 CSS（横排组件 ≠ 竖排卡片）

事故（课件多轮迭代）：`.guardrail` 的 CSS 是 `display:grid;grid-template-columns:100px 180px 1fr`——标签|标题|正文**横排**，为全宽行（guardrail-stack）设计。把它放进 `repeat(3,1fr)` 三栏网格后，每卡仅 ~380px 宽，正文列被挤到 **28–59px，文字竖排成细条**——三页共 9 张卡同病，且视觉模型截图检查两次报"排版正常"，最终靠 DOM 宽度测量才抓到。

规则：

- 复用任何既有 class 前，**先 grep 它的 CSS 定义**，确认布局方向（横排 row / 竖排 column）与列宽语义是否匹配使用场景；行式组件（`grid-template-columns:A B 1fr`）不得放进多栏网格当卡片
- 多栏并列卡片一律用**纯内联竖排卡片**（不依赖组件 CSS，任何宽度下安全）：

```html
<div style="padding:16px 20px;border-top:4px solid var(--gold);background:rgba(255,255,255,.55);display:flex;flex-direction:column;gap:8px">
  <span style="font-family:var(--mono);font-size:11px;color:var(--gold);letter-spacing:.12em;font-weight:700">标签</span>
  <h3 style="font-family:var(--serif-zh);font-size:21px;margin:0">标题</h3>
  <p style="font-size:14px;line-height:1.55;opacity:.72;margin:0">说明文字。</p>
</div>
```

- 验证信号：卡片正文 `p` 的 `getBoundingClientRect().width < 200px` = 布局已坏（正常应 ≥ 300px）

## 21. 720p 视口预算：改页前先估高，验证只认 DOM 几何

§14 把 overflow 改 visible 只是"不被容器硬裁"，**不等于内容可见**——scroll-snap 下超出 720 的内容会画到下一页顶上，投屏翻页时仍然看不到。真正的及格线是**内容装进 720px**。

事故（同日）：新增页 callout 底边做到 930px（超视口 210px 整块不可见）、另一页 741px，多轮才收敛。

预算参考（1280×720 deck 实测）：两行 h-xl 标题 + rule 到 ~175px；三栏内联卡片（§20 pattern，2 行正文）~140px，行式组件 400px+；底部 callout 单行 ~80px / 双行 ~115px。**一页堆完总高超过 ~600px 就砍文字，不是改组件 CSS。**

- 溢出修法优先级：**砍文字 > callout 收单行 + 紧凑 padding（10px 20px）> 压 margin**；不要动全局组件 CSS 兜一页
- 验证纪律：截图 + 视觉模型**只能当辅助**（同日两轮误报"正常"，且服务间歇不可用）；通过/失败判定必须用 DOM 几何——每页**最后一个元素 bottom ≤ 720**（相对页顶坐标，留 5px 余量），改动页逐一实测
- 截图循环先读该页 chrome 标签确认截到目标页再下结论（同日事故：0 基/1 基索引错位，把 Playbook 页当判决书页，误报"三版本页异常"）

## 22. 结构一动，页码全量重编

增/删/移动页面后必须同步四处：① 每页 chrome 计数器 `N / T` 全量重编；② 头注释 `XX 页 browser deck`；③ 目录页环节名清单（如有增删环节）；④ 验证计数器序列 == 2..T 连续（封面通常无计数器）。

- 脚本化处理 + 断言（分节后逐节 `re.sub` 首个 `N / T`，断言 `len(sections)==期望值`、计数器序列连续），不要手改
- **计数器可能每页两处**（chrome 右上 + 页脚右下）：重编必须**按页分组同号**（页号=页序），按"出现顺序"顺序编号会让同页两处错位 +1、越翻越乱（竖向演示回归样例，渲染验收才抓出）——断言要落到"每页块内各计数器 == 页序"，不是全局序列
- 关联：`merge-pitfalls.md` §5 的"slide id 重编号 + PAGENO → 真实页码"是同款纪律在多源合并场景的版本

## 23. 竖向滚动引擎：每页衬底必须与 slide 同族（半透明底 + body 底色钉死 = "有深有浅"）

**现象**（竖向演示回归样例）：非 16:9 视口（如 1440×900）下每页上下露出约 45px 底色带；浅色页整页发乌、像"被缩小一圈的深边卡片"，深色页却完全融入——整份 deck 观感"有深有浅"。PDF 全页出血**不会暴露此缺陷**，打开 HTML 才看得见。

**根因（三层叠加）**：

1. slide 底是**半透明**的（如 `.slide.light{background:rgba(var(--paper-rgb),.92)}`，`.dark`/`.mid` 为 .90）——设计上靠背后的衬底补足颜色；
2. 竖向引擎把衬底**钉死在一处**：`html,body{background:var(--ink)}`——浅色 slide 92% 白衬深墨 = 发乌；
3. **同步类没有 CSS 消费端**：引擎 JS 每页切 `body.light-bg`（这类明暗切换引擎都依赖配套 CSS 规则），克隆时把 JS 带来了、CSS 丢了——类在切、没人听，属"静默缺陷"，读 JS 看不出问题。

**修法（优先声明式，不依赖 JS 同步）**：衬底直接挂到每页容器，滚动中途即正确：

```css
.page:has(.slide.light){background:#ffffff}  /* 与 slide 实色同族；dark/mid 衬 body 深墨本就融入，不动 */
```

若引擎确需按页切 body 类：**每引入一个同步类必须同步写它的 CSS 规则**，验证清单加一条"类有消费者"。

**验证**：Playwright 在 **1440×900（非 16:9）** 加载，`elementFromPoint(20, 5)` 逐页采样带区背景色——浅色页应为白、深/中色页与 slide 同族；1280×720 / 1440×900 / 1728×1080 三视口各跑一遍。截图目检一页浅色页确认无"深边卡片"。
