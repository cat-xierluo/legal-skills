# 一步到位输出流程

Legal Visualization 的默认目标是一次交付 `.drawio + .svg + .png` 三件套。

## 文件组合

每次出图默认输出三件套：

- `[图名].drawio`：源文件，可在 draw.io / diagrams.net 打开编辑。
- `[图名].svg`：由 draw.io / diagrams.net 从 `.drawio` 导出的矢量图，文字清晰，可缩放，适合 Word/PPT/网页。
- `[图名].png`：由 draw.io / diagrams.net 从 `.drawio` 导出的高清预览和分享格式；自动导出默认使用 2 倍倍率，降低微信、飞书、文档插图中的模糊感。
- `[图名].pdf`：用户要求正式附件、打印或归档时生成。

如果只能生成一种图片，优先 `SVG`。如果导出工具不可用，仍应交付 `.drawio`，并明确说明未能导出图片的原因。

## 归档机制

自动导出的 `.drawio`、SVG、PNG 和报告默认写入 `archive/<timestamp>/`。`archive/` 只保留 `.gitignore` 与 `.gitkeep`，目录内运行产物不进入版本库，适合保存本次导出的 `.drawio`、SVG/PNG/PDF 与 `export-report.json`。

需要把图片放回 `.drawio` 同目录时，使用：

```bash
python scripts/export_drawio.py path/to/file.drawio --format svg,png --in-place
```

需要指定归档目录时，使用 `--output-dir`。

需要更高清 PNG 时，使用：

```bash
python scripts/export_drawio.py path/to/file.drawio --format png --png-scale 3
```

## 输入抽取

生成图表前，先从材料中整理以下信息：

| 字段 | 说明 |
|------|------|
| 图表标题 | 用案件名称或争点命名 |
| 受众 | 法官、客户、团队、对方或公众 |
| 核心观点 | 一句话说明本图要表达什么 |
| 案由/场景 | 对应 `scene-library.md` 的 ID |
| 主体 | 当事人、第三人、法院、行政机关、银行、项目等 |
| 行为 | 签约、付款、交付、背书、贴现、施工、验收、转让等 |
| 时间 | 关键日期、期间、先后顺序 |
| 金额/比例 | 借款、还款、出资、工程款、股权比例等 |
| 证据 | 支撑节点的证据编号、名称、页码或来源 |
| 争议状态 | 已证实、待证、对方主张、己方主张 |
| 背景事实 | 市场、政策、行业价格或项目状态等用于解释行为的外部线索 |

## draw.io 生成规则

- 使用完整 `mxGraphModel`，保留 `id="0"` 和 `id="1"`。
- 所有 edge 必须包含 `<mxGeometry relative="1" as="geometry" />`。
- 节点坐标、字号、字体、颜色、节点尺寸等视觉常量全部按 `references/legal-visual-constants.md` 取值（页面 origin、字体、调色板、线型绑定、节点尺寸参考）。
- 节点命名按 `references/naming-conventions.md` 规范。
- 文字过长时增加节点宽度、换行或使用脚注，不缩到不可读。
- 图例、注释、证据来源放在右侧或底部。
- 复杂案件、高阶论证图、制度路径对比和背景趋势叠加图，先按 `references/advanced-case-patterns.md` 选套路，再写 draw.io。

## 导出策略

优先使用当前环境中可用的方式导出：

1. draw.io / diagrams.net CLI：直接从 `.drawio` 导出 SVG、PNG、PDF，并把 `.drawio` 源文件复制到输出目录。可执行版见 `scripts/export_drawio.py`，脚本会检测常见 CLI 命令和 macOS 应用路径；默认生成 `.drawio + .svg + .png` 三件套并输出到 `archive/<timestamp>/`。
2. draw.io MCP、浏览器或桌面应用：按当前环境能力打开 `.drawio` 后导出，适合需要人工确认的复杂图。
3. 无导出环境：只生成 `.drawio`，并给出明确说明。

`scripts/export_drawio.py` 的报告会记录 `source_drawio`，并只对图片做轻量文件检查：文件大小、空白风险、SVG viewBox、PNG/PDF 文件头。文字截断、箭头丢失、布局拥挤等图面质量仍按下方图片自检人工确认。

PNG 导出报告会记录 `png_scale`。默认 `2.0` 适合普通文档和聊天分享；打印、大屏投影或需要裁剪放大的图片可用 `3.0` 或 `4.0`。

导出 SVG 时，优先嵌入 diagram 数据，使 SVG 仍可回到 draw.io 编辑。导出 PNG 时，确认分辨率足够用于文档或演示。

## 图片自检

导出后至少检查：

- 图片不是空白，画面主体完整。
- SVG 的 viewBox 没有裁切内容。
- 文字没有超出节点边界，没有被边框遮挡。
- 线条方向清楚，箭头没有丢失。
- 图例与图中颜色、线型一一对应。
- 主图无需口头解释即可理解核心结构。

## 交付说明

最终回复用户时，说明：

- 生成了哪些文件。
- 主图采用了哪个场景和为什么。
- 是否完成图片导出和自检。
- 哪些事实被标为待补充或争议事实。
