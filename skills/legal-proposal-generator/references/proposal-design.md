# 设计版方案：源稿、主题与图表契约

生成带设计版 Word 的方案时，先确定主题，再写 MD 和制作图表。MD 保存内容、结构和图件引用；主题文件保存外观；封面与正文由 Word 组件排版。需要自由构图、复杂叠层、跨栏或其他 Word 难以可靠表达的设计时，交给独立维护的 `legal-proposal-designer`。

## 1. 先选择一份主题

默认使用 [律所棕](../config/themes/law-firm-brown.json)，另有 [深蓝](../config/themes/navy.json) 与 [墨绿](../config/themes/forest.json)。三个预设共用版式；不同颜色不改变法律含义。

主题配置分为三组：

| 配置组 | 内容 | 应用范围 |
|---|---|---|
| `colors` | 主色、深色、辅助色、文字色、浅底、分隔线、风险/待核/正向色 | 封面底图、标题、表头、正文卡片、荣誉徽章与图表 |
| `fonts` | `eastAsia` 中文正文、`ascii` 西文正文、`diagram` 图表字体 | Word 正文和图表；图表默认用无衬线字提高小字号可读性 |
| `diagram` | `widthMm`、`dpi`、`fontPt`、`linePt`、`radiusPx` | 图表导出宽度、清晰度、文字与连线；`radiusPx` 用于 SVG 模板，Mermaid 节点形状由语法决定 |

沿用 `gold` 这一旧字段名，含义为主题的辅助强调色，深蓝和墨绿主题不要求使用金色。默认图宽 160mm、300dpi（约 1890px），基础图表文字 11pt。内容太多时拆图，不把整张图缩到难以阅读。

自定义时在项目中保存 JSON，例如：

```json
{
  "extends": "navy",
  "schemaVersion": 1,
  "id": "client-brand",
  "name": "客户品牌主题",
  "colors": {"primary": "284B63", "deep": "183143"},
  "fonts": {"eastAsia": "SimSun", "diagram": "Microsoft YaHei"}
}
```

`extends` 只接受三个内置预设；六位 HEX 可带 `#`。未知字段、无效颜色、关键文字/底色对比度不足会报错。主题校验不代替实际渲染检查。字体由运行机器提供；字体不存在时会替代，需在目标机器检查。

## 2. MD 是可迁移的内容源稿

```markdown
---
law_firm: 示例律师事务所
client: 示例企业
lawyer: 测试律师
date: 2026年9月27日
theme: navy
subtitle: 专项服务方案
---
# 项目法律服务方案

## 一、项目理解

在段落中说明本节结论、来源和尚待核实的事项。

![图 1｜主体关系示意](assets/relations.png)

说明图中实线、虚线及待核标记的含义，不能用图形替代尚未查明的事实。
```

- 每份文件只设置一个主标题；`##` 为章，`###` 为节，普通段落、列表、表格与引文使用语义 Markdown。
- 图件单独占一行。默认使用相对路径，便于连同 `assets/` 一起移动；绝对路径也可读取。
- `theme` 可以是预设名，或相对 MD 的 JSON 路径。命令行 `--theme` 优先，路径相对运行目录；JSON 正文的顶层 `theme` 同样支持。
- 不在正文嵌入 HTML 布局、原始 SVG、Mermaid 代码块、人工空行定位或手写页码；这些只保留在图表源文件或设计稿中。
- 对外 Word 的团队、案例、律所和荣誉来自选定的团队配置；源稿不再复制同一套 HTML 附页。
- 正文末尾保留一段简短结语，与自动落款相邻；避免以大图或长表格直接结束。最终分页仍需实查，不靠缩小图中文字解决溢出。
- 配图中的人物、金额、日期、关系和风险判断应能回到正文材料；主题色不表示胜诉概率或责任比例。

推荐保留：

```text
项目/
  proposal.md
  theme.json                 # 选用内置预设时可省略
  diagrams/relations.svg     # 或 .mmd / .drawio 底稿
  assets/relations.svg       # 解析主题后的矢量图
  assets/relations.png       # Word 插图
  assets/relations.visual.json
  proposal.docx
```

## 3. Mermaid 与 SVG 按图的任务选择

| 路线 | 适合的内容 | 交付规则 |
|---|---|---|
| Mermaid | 少量节点、关系明确的流程或分支；修改结构频繁 | `.mmd` 保存逻辑，注入统一配置后导出 SVG/PNG；不用 Mermaid 默认彩色主题 |
| SVG / draw.io | 需要控制层次、对齐、分组、注释、时间轴、关系图和精确布局 | 保留 `.svg` 或 `.drawio` 源文件，按主题颜色和图宽制作；Word 使用 PNG |
| Word 原生表格 | 费用、范围、清单、方案比较等需要逐项编辑的内容 | 优先保持表格可编辑；不为视觉效果全部转图片 |
| Designer | 大幅主视觉、复杂叠层、自由构图、跨栏或特殊设计风格 | 使用独立设计版 HTML/PDF；共享内容与主题意图，但分别验收 |

SVG 是图件载体，也可以由 Mermaid 或 draw.io 导出。Word 当前使用 PNG 作为兼容插入格式；图中的节点和文字并非 Word 原生可编辑对象。

## 4. 让外部制图工具拿到同一份设计要求

调用 `legal-visualization` 或其他匹配的制图工具时，传入本次解析后的主题、最终物理宽度、受众、正文对应段落、允许的语义角色与事实来源。保留该工具的图形与事实校验，不以换色替代校验。不修改其他可视化 Skill 的全局默认风格。

导出可交给其他工具的主题资料：

```bash
NODE_PATH=$(npm root -g) node word/visuals.js --theme navy --export-theme /项目/assets/theme
```

生成 `theme.resolved.json`、`mermaid-config.json` 与 `theme.css`。CSS 仅是交接资料；designer 当前尚未自动消费这些新主题文件，不能声称其页面已经同步换色。

## 5. 图表导出与 Word 生成

SVG/PNG 导出需要 `sharp`：`npm install -g sharp`。Mermaid 路线还需 `npm install -g @mermaid-js/mermaid-cli` 和可用本地 Chrome/Chromium；可用 `PUPPETEER_EXECUTABLE_PATH` 指定浏览器。

```bash
NODE_PATH=$(npm root -g) node word/visuals.js \
  --input /项目/diagrams/relations.svg --output /项目/assets/relations.png --theme navy

NODE_PATH=$(npm root -g) node word/render.js \
  --input /项目/proposal.md --output /项目/proposal.docx --cover C
```

`--input` 也支持简单流程图 `.mmd`。本入口不自动编译任意 Mermaid 图型；复杂图由专业工具导出自包含静态 SVG。Mermaid 节点可标注 `:::focus`、`:::risk`、`:::warning`、`:::success`，由主题定义颜色；只在内容确实有该语义时使用。

SVG 支持 `{{primary}}`、`{{cream}}` 等颜色字段及 `{{diagramFont}}`、`{{fontSize}}`、`{{strokeWidth}}`、`{{radius}}` 变量，数值按 96dpi 图形单位提供。参考 [SVG 示例](../word/examples/diagrams/service-roadmap.svg) 和 [Mermaid 示例](../word/examples/diagrams/service-flow.mmd)。SVG 须有有效 `viewBox`，使用主题内 HEX 色；脚本、外部资源、HTML 标签与非主题固定色会报错。工具不自动猜测如何把一张旧图中的颜色映射到新主题。

PNG 旁的 `.visual.json` 绑定主题、源文件及 PNG 内容。生成 Word 时检查这些绑定和物理尺寸；换了主题、改了源文件或手改了 PNG，就先重新导出。没有记录的既有照片/扫描件仍可插入，其审美一致性由人工复核；不能借此声称任意图片都通过主题检查。照片和证照保留原色，不统一染色。

## 6. 交付前复核

先看 MD 的层级与图文关系，再看最终 PDF/Word：主题是否贯穿封面、正文和附页；图中中文是否清晰，连线是否完整；颜色是否辅以文字/线型而非独自承担语义；图注是否与本节内容相邻；分页和页码是否正确。至少按正文实际宽度检查图件，不只放大看 PNG。

更换颜色后须重新生成图件和 DOCX。任意正文、任意字体与 Word/WPS 客户端的分页一致性不在主题配置的保证范围内。
