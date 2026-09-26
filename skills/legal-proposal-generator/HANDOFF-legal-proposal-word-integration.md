# HANDOFF · legal-proposal-word 整合交付（Word 设计版管线并入 generator）

> 交接日期：2026-09-23 ｜ 交接人：ZCode（Claude 会话，浙江易驱车灯管家方案项目期间沉淀）
> 接收人：负责整合 legal-proposal-generator 与 legal-proposal-designer 的 agent
> 状态：**Word 设计版管线已可用、已验证**，本文件交代它是什么、怎么来的、坑在哪、接下来怎么并入 generator。

---

## 1. 目标（用户原话的工程化转述）

用户（杨卫薪律师）最终想要的形态：**只保留 legal-proposal-generator 一个 skill，由它直接生成「带设计稿的 Word 文件」**——即 designer 的视觉品质 + generator 的内容管线，产物为可编辑 docx。中间沉淀出的 Word 模板资产已完成并验证，本文件负责把它交接到整合工作里。

用户明确的取舍（背景，勿反向推翻）：
- **Word 是交付主线**（客户可改、格式牢、无环境依赖），HTML/PDF 版（designer 现管线）保留给「要设计感、直接发送、不再改」的正式场合；
- 内容与版式分离：内容以 Markdown/数据为单一来源，设计由模板资产保证；
- 律师的真实痛点是 designer 两个老问题：HTML 产物无法手改（改了会被重渲染冲掉）、MD 中间稿与最终 HTML 是「重组关系」（团队/律所/荣誉由 config 注入固定位置，`--lawyers` 只能选人不能改布局）。

## 2. 三方现状（接手前必读）

| 资产 | 位置 | 说明 |
|---|---|---|
| legal-proposal-designer v0.4.0 | `~/Library/Application Support/maoscripts/skills/private-skills/legal-proposal-designer/` | MD → A4 设计版 HTML/PDF。`references/cover-variants/cover-[CDEF]-*.html` 是四种封面的设计真源；`references/design-spec.md` 是配色/字体/版式规范；`references/proposal-template.html` 是主模板。视觉基准一律以它为准 |
| legal-proposal-generator v0.3.2 | `~/Library/Application Support/maoscripts/skills/legal-skills/skills/legal-proposal-generator/` | 内容管线：案件材料 → 方案 markdown。`config/team-config.md` 含**真实个人信息**（律师资料/判决书截图/律所照片，已在 .gitignore，严禁外传或提交公开仓库）；`config/images/` 含头像/判决书/律所照片原图 |
| **legal-proposal-word（本次新增）** | `/Users/maoking/Documents/Mac同步文件夹/工作文档/009 - X模板/legal-proposal-word/` | **Word 设计版模板资产包（OOXML）**，就是本次要并入 generator 的东西。详见其 README.md（三条集成路径、token 清单、封面风格表、跨引擎守则八条） |

**重要**：designer 与 generator 均为用户本人（杨卫薪，github cat-xierluo/legal-skills）的作品，CC-BY-NC；改造无许可障碍。Word 资产包的视觉规格**逐项对照 designer 的 CSS 写成**（builders.js 内有对应注释），整合时不要凭感觉重调。

## 3. Word 资产包（本次沉淀的核心交付）

### 3.1 文件构成

```
009 - X模板/legal-proposal-word/
├── builders.js            # 设计组件库（唯一视觉事实来源）
│   ├── buildCover(style, config, assetsDir)   # 封面调度器，C/D/E/F 四风格
│   ├── coverFooter / coverFooterBlank         # 封面页脚（灰线版 / 空占位版）
│   ├── sectionHeader / h1 / h2 / body / bodyRuns / listItem / lawQuote
│   ├── makeTable（棕表头+斑马纹，FIXED 布局）/ bodyFooter（金线页脚）
│   ├── teamCard / firmIntroCard / honorTable / caseGrid   # 后部固定页组件
│   ├── signatureBlock（落款右对齐）
│   ├── photoOrPlaceholder(pathOrToken, widthCm, placeholder, ratio)  # 照片/占位框双模
│   └── docStyles / makeNumbering / makeSection / LP 配色常量
├── generate.js            # 真实方案入口：node generate.js "输出.docx" --cover=C --full
├── template.js            # OOXML 模板入口 → legal-proposal-OOXML-template.docx（43 个 {{TOKEN}}）
├── fill.py                # python-docx 填充工具（--set/--photo/--list）
├── legal-proposal-OOXML-template.docx    # 模板成品（含后部固定页 token 骨架）
├── cover-decor.png / cover-D-decor.png / cover-E-decor.png   # 封面装饰（PIL 烘焙的透明层）
├── cover-previews/preview-C/D/E/F.png     # 四风格封面预览图
└── README.md              # 完整文档：集成路径/token 表/designer 对应表/跨引擎守则八条
```

### 3.2 已验证的能力（全部视觉验收 PASS）

- **轻量版**（客户方案形态）：封面 + 正文，6 页。实测案例：260922 车灯管家商家入驻方案（`011 - 潜在项目/260922 浙江易驱 车灯管家 商家入驻合规项目/`）。
- **完整版**（`--full`）：封面 + 正文 + 后部固定页 4 页（承办团队卡片×2、相关裁判文书 2×2、律所简介卡、律所荣誉 6 条），10 页。四种封面各出一份实测，位于 `011 - 潜在项目/260922 .../完整版预览/`（docx+PDF）。
- **照片嵌入**：`--photo`（fill.py）或 `photoPath`（builders）均可，真实头像/判决书/律所合影已实测，按 `photoRatio` 传宽高比防变形（team-config 的 7 张图实测比例记录在 generate.js 的后部页数据里）。
- **四封面风格**：与 designer `--cover-style` 一一对应（C 顶部几何/D 对角斜切/E 底部反转/F 瑞士网格），几何装饰用 PIL 烘焙的透明 PNG 叠层，**色块本体全部是原生表格底色**——单引擎渲染挂了也不会色带错位。

### 3.3 运行环境依赖

- Node ≥ 22 + 全局 `docx` 包（`npm i -g docx`；运行时 `NODE_PATH=$(npm root -g)`）；
- python3 + `python-docx`（1.2.0 实测可用，仅 fill.py 需要）+ `Pillow`（仅重新烘焙装饰图时需要）；
- LibreOffice（仅 QA 渲染验收用，非产出依赖）+ docx skill 的 `fix_footer_fields.py`（页码域后处理，必须跑）与 `postcheck.py`（质量自检，image-overflow 对全出血装饰图为已知误报）。

## 4. 工作记录时间线（含每个决定的理由）

1. **起点**：车灯管家方案先是 12 页「太正式」的 docx（法条原文块+目录）→ 用户要求客户版瘦身 → 去法条原文/去目录 → 6 页精简版（法条原文移入内部评估文件第九节留档）。
2. **定价与口径演进**：单份协议 300-500 锚点 → 2000/3000 两档 → 完整档上调 **2000/4000 定稿**，「基础档起步+补差价升级」销售路径；费用段删去各阶段工作日天数（期限留给委托合同）。
3. **Word 化**：用户确认「Word 主线 + designer 视觉」→ 依 designer 的 `design-spec.md` + `cover-geo.html` 逐项翻译为 docx-js（WR-2 绿色系先做，后按用户要求换成 designer 棕系 `#5A4E48`）。
4. **封面三轮精修**：v2 色带原生化（双行表格，装饰图只做圆环）；v3 CONFIDENTIAL 行移入真页脚；v4 高度守恒修复（详见 §5 事故一）。
5. **页数压缩**：7→6 页（风险段六段各砍半、间距档收紧），docs 里同步。
6. **署名定稿**：全文江苏剑桥颐华律师事务所 / 杨卫薪，无占位符（用户明确要求直接填好）。
7. **四封面提取**：读 designer `references/cover-variants/` 四个 HTML → builders.js 各一个构建器 + `buildCover` 调度器 + PIL 烘焙 D/E 装饰图 → 逐个修 z-order/遮挡/竖线问题 → 四张 PASS。
8. **完整版管线**：`generate.js --full` 追加后部固定页（数据硬编码自 team-config.md 真实内容）→ 修 docx-js 嵌套段落丢图 bug → 四封面 × 10 页全部 PASS。

## 5. 事故与坑清单（守则全文见 Word 包 README「跨引擎兼容守则」，此处按「症状→根因→规」重述，**整合时逐条对照实现**）

| # | 症状 | 根因 | 规（实现层落点） |
|---|---|---|---|
| 1 | **WPS 打开封面变两页**，MS Word/预览正常 | 封面节下边距 907 缇但 wrapper 表格仍占满 16838 缇 → 超出正文区；WPS 把溢出行推新页，Word/LO 吸收 | **高度守恒**：wrapper 各 exact 行之和 ≤ 16838 − 下边距；每风格独立核算（见 builders.js 各 buildCover 注释） |
| 2 | python-docx 处理后封面被挤压分页 | 访问不存在的页眉会**凭空创建空页眉部件**，空页眉占页眉距离空间挤压零边距封面 | fill.py `collect_documents()` 先 `is_linked_to_previous` 过滤 |
| 3 | **LibreOffice 转换挂死**（转不出 PDF），仅限 D/E/F | 封面节无页脚 + 零边距 + 通高 exact 表格 → LO 布局死循环；MS Word 正常（极具迷惑性） | **封面节必须挂页脚**，D/E/F 挂 `coverFooterBlank()` 空页脚 |
| 4 | D 封面律所名消失 | 前景浮动图的不透明区盖住同段文字 | 需透字的底图 `behindDocument: true` 且所在行底为白；前景图只允许在文字不经过的区域 |
| 5 | 荣誉页横线 / F 网格竖线消失 | **单元格级边框覆盖表格级边框**（子单元格 noBorders 抵消 tblBorders） | 线必须声明在最终生效的层级；排查口诀「表格线消失先查子单元格」 |
| 6 | 裁判文书图整页空白 | **段落嵌套段落**（组件返回 Paragraph 又被包进 Paragraph）——docx-js 静默丢弃不报错 | 组件返回段落时直接入 children 数组 |
| 7 | JS 语法错误（中文引号） | heredoc/管道传输把弯引号 ASCII 化成直引号，破坏字符串 | 生成 JS 内容一律走 Write 工具或 python 精确替换；写完先 `node --check` |
| 8 | 荣誉/表格列宽失控 | 表格未设 FIXED 布局时引擎 autofit 无视百分比列宽 | 多列表格一律 `layout: TableLayoutType.FIXED` |

通用守则：底部锚定用真页脚不用 spacer；exact 行内容 ≤ 行高 85%（Word 行高膨胀余量）；校准只信 LibreOffice 渲染 + 安全余量；**每次改版在真实 WPS + MS Word 各开一次再交付**（三引擎行为差异表见 README）。

## 6. 整合路线建议（给接手 agent 的施工图）

**推荐架构：generator 做内容大脑，Word 管线做 sidecar。**

1. **内容契约**：generator 现有产出是方案 markdown。建议新增一层「case-data 结构化数据」（章节标题/段落 runs/表格/列表/引用块/照片清单），由 generator 从 markdown 或直接从案件材料抽取；`builders.js` 的组件粒度（bodyRuns/makeTable/lawQuote/listItem）就是按这个契约设计的，一一对应。
2. **渲染 sidecar**：`builders.js + generate.js + cover-*.png + fill.py` 原样并入 generator（建议路径 `skills/legal-proposal-generator/word/`），generator 通过 `child_process` 调 `node generate.js <out> --cover=X --full`。不要用 python-docx 重写组件（会丢失全部已验证的跨引擎处理，事故 1-6 全是渲染层细节）。
3. **数据注入两选一**（可并存）：
   - 路径 1（现有，适合「模板+少量变量」）：产出 token 模板 + fill.py 填充；
   - 路径 2（推荐为主，适合「每案全内容」）：generator 生成 case-data → 直接驱动 builders 组装（generate.js 的 bodyChildren 区块就是样例），token 模板保留作快速通道。
4. **team-config 复用**：后部页数据（律师卡片/判决书/律所简介/荣誉）已在 generate.js `--full` 段落硬编码自 `team-config.md`；整合时改为读取该文件（HTML 表格结构，含图片路径），实现「主办律师选定 → 卡片自动组装」（对齐 designer 的 `--lawyers` 能力，且用户要求过「能改布局/字段/顺序」——Word 表格结构天然满足）。
5. **QA 流水线固化**（整合后 generator 的出片前检查）：`fix_footer_fields.py` → `postcheck.py`（容忍 image-overflow 误报）→ LibreOffice 渲染逐页抽查 → 交付前 WPS/Word 实测。
6. **SKILL.md 更新点**：generator 的 description 加「生成带设计版式的 Word 方案」；触发场景补「用户要 Word 版服务方案/完整版（带团队律所页）」；文档类型里区分轻量版（6 页）与完整版（10 页）。

**开放问题（用户未拍板，整合时询问）**：
- E 封面棕带下 25mm 留白（高度守恒取舍，HTML 版贴页底）是否需要进一步逼近原版；
- 典型案例页在轻量版是否彻底移除（当前轻量版无后部页）；
- generator 并入后 designer 的 HTML/PDF 管线是否保留双轨（当前建议：保留）。

## 7. 验证记录摘要（260923）

- 四种封面单页验收：PASS（含像素测量：D 斜边左 148.8→右 84.4mm、E 棕带 199-270.3mm、F 竖线 22.0/187.8-188.0mm）；
- 轻量版（C 封面 6 页）：整册 PASS；完整版四册（各 10 页）：整册 PASS（首轮裁判文书图丢失已修复复验）；
- 真实方案（轻量·C 封面）即为发客户的终稿：`011 - 潜在项目/260922 .../01 - 📋 项目方案/260922 商家入驻项目法律服务方案（客户版）.docx`。

## 8. 相关文件索引

- Word 资产包本体与 README：`/Users/maoking/Documents/Mac同步文件夹/工作文档/009 - X模板/legal-proposal-word/`
- 完整版样例（4 封面 × docx+PDF）：`/Users/maoking/Documents/Mac同步文件夹/工作文档/011 - 潜在项目/260922 浙江易驱 车灯管家 商家入驻合规项目/03 - 🎨 完整版预览/`
- 内部评估（定价口径/法条留档）：同项目文件夹 `01 - 📋 项目方案/`；基础档三份核心文件 MD 初稿在 `02 - 📝 文件初稿/`（入驻合作协议/管理规则/用户协议修订版+起草说明）
- designer 设计规范：`designer/references/design-spec.md`；封面真源：`designer/references/cover-variants/`
- generator 团队数据：`generator/config/team-config.md`（含隐私，勿外传）与 `config/images/`
