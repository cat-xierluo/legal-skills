# 秒数时间轴工具

命令在 Skill 目录运行。`scripts/svg_motion.py` 仅依赖 Python 3.9+ 标准库；读显式输入、写显式输出，不联网、不安装、不修改源文件。已有输出默认拒绝，确认替换用 `--force`。错误退出码 1，命令行用法错误为 2；validate 总是输出 JSON，失败不出成功标记。

```bash
python3 scripts/svg_motion.py compile assets/demo.skeleton.svg assets/demo.timeline.json -o /tmp/demo.svg
python3 scripts/svg_motion.py validate /tmp/demo.svg
python3 scripts/svg_motion.py preview /tmp/demo.svg -o /tmp/demo.html
python3 scripts/svg_motion.py publish /tmp/demo.svg -o /tmp/demo.publish.svg
```

## JSON 契约

```json
{"duration":12,"loop":true,"tracks":[
  {"target":"status","attribute":"opacity","calcMode":"linear","keyframes":[[0,0],[1,0],[1.3,1],[10.8,1],[11.2,0],[12,0]]},
  {"target":"cursor","attribute":"transform","type":"translate","keyframes":[[0,"600 320"],[2,"200 220"],[12,"600 320"]]}
]}
```

- 顶层仅接受 `duration`（正的有限秒数）、可选 `loop`（boolean，默认 true）、非空 `tracks`。
- 每轨 `target` 对应骨架唯一且非空的 `data-cue`，支持中文。目标要有实际图形或文字。transform 目标限非空 `<g>`；opacity 可用于图形或组。
- `attribute` 仅 `opacity` 或 `transform`。transform 的 `type` 仅 `translate`、`scale`。同 target/attribute/type 不得重复，opacity 与多个不同类型的 transform 可共存。
- `keyframes` 为至少两个 `[秒数,值]`。首点 0、末点 duration，秒数严格递增，不自动 clamp 或纠正错误时码。静止段写两点相同值；瞬间切换用 discrete，不写重复时点。
- opacity 值为 `[0,1]` 数字。translate 为两个有限数字的字符串（`"20 30"`）或数组（`[20,30]`）。scale 为正数，或一/二个正数的字符串/数组；同轨维数一致。
- `calcMode` 可选 linear（默认）、discrete、spline。spline 额外提供 `keySplines` 数组，每区间一项，每项四个 `[0,1]` 数字，可为数组或空格分隔字符串。非 spline 不接收 keySplines。
- 未知字段、重复 JSON key、NaN、缺字段和非法目标均失败。所有轨道使用同一 duration、begin=0s 与 repeatCount（loop true 为 indefinite，false 为 1），末帧 freeze。浮点归一化若使极近时点合并，会被最终校验拒绝。

例如 spline 两个区间：`"keySplines":[[0.4,0,0.2,1],[0.4,0,0.2,1]]`。多个图可有不同 duration；同张图内共用周期，便于对齐状态与 scrub。

## 变换编译

骨架先通过校验且不含动画；重编译使用原骨架，不能把编译输出再当骨架。编译时在目标组内部增加运动 `<g>`，原静态 transform 不动。translate/scale 轨按 JSON 顺序从外到内嵌套；opacity 仍作用于 cue 外层。详见 [相对位移与绝对坐标](dynamic-svg.md)。

编译器不猜坐标意图、不重排文字、不静默调整轨道。外层静态坐标和绝对轨迹混用会双倍位移，只有浏览器测真实位置才发现作者意图偏差。

## validate 的 fail-closed 边界

这里的通过仅指下列检查，不是完整 SVG 规范验证或公众号白名单认证：

| 检查 | 失败条件/边界 |
|---|---|
| XML | 非 SVG 命名空间根、XML 无法解析、DTD/实体/外部样式处理指令 |
| 元素与属性 | 未列入脚本 TAGS/ATTRS 的元素、属性或命名空间；script、foreignObject、style 块、image、filter 均不在当前子集 |
| 资源与引用 | href 只允许现有本地 #id；url() 只允许现有本地 #id；拒绝外链、file、data URI、CSS @规则/转义/注释；id/cue 重复、use 引用递归失败。data-/aria- 是文字元数据，不作为资源解析 |
| CSS | 仅脚本 CSS 列出的内联属性；不支持 CSS 动画或任意样式表。此检查不替代完整 CSS 值语法验证 |
| viewBox | 四个有限数字，宽高为正。其他图形几何、path d 与所有静态属性值不作完整语义校验，留 DOM/截图验证 |
| 动画 | 仅 opacity animate 和 translate/scale animateTransform；要求 values、keyTimes、共同正秒数 dur、begin=0s、repeatCount、合法 calcMode；数量、严格递增、首尾、值范围、向量维数、spline 数量和范围分别核验 |
| 变换目标 | 空目标、定义区动画、同元素静态 transform 与 animateTransform、同属性竞争动画、additive=sum 或动画 href 均失败；使用有内容的嵌套组 |
| 循环 | 所有动画周期/repeatCount 一致；首尾值不同只警告，因为作者可能有意隐藏后复位；仍需查跨循环画面 |

有效的 SVG 可能超出此保守子集。失败后改为本子集、选择其他可验证路径，或明确缺失验证；不要因为浏览器显示就略过失败。要扩展子集，先加独立验证与正反例，再改 allowlist。引用检查确认目标存在和 use 无递归，不验证每一种引用目标类型、无障碍语义或 CSS 像素效果。

报告包含 UTF-8 字节数、SHA-256、动画数、错误与警告，便于绑定当前源码。无外部资源的通过不代表纯矢量统计包含了字体文件，字体仍依赖浏览器环境。

## 自包含预览

preview 将 SVG、布局测量函数与控制脚本嵌入单 HTML，可用 file:// 打开，不启动服务、不复制富文本、不自动发布。支持播放、暂停、重置、±1 秒、0.01 秒滑杆、375px/800px 切换与当前帧测量。小窗口可滚动查看 800px 版本，正式测量须核实际 `width`。

程序定位可用 `svg.pauseAnimations(); svg.setCurrentTime(seconds)`，调用 `window.measureSvgLayout(svg)`，函数自行有界等待字体和两帧；后台或超过 2 秒抛 NOT_VERIFIED，不能当成该时点通过。HTML 的 JS 是制作工具，最终发布的 SVG 无 JS。

## 本地 SVG/HTML 片段交接

`publish input.svg -o output.svg [--force]` 接收已经编译的动态 SVG，也可接收已验证静态 SVG。先执行完整现有校验，再删除所有元素上的制作 `data-*` 属性，序列化后重新校验。保留 id、viewBox、文字、图形层级、局部引用、`animate` / `animateTransform` 及其关键属性；不重新编译时间轴，不添加 JS、CSS 动画或外链。现有输出默认拒绝覆盖，`--force` 也不能把输入路径作为输出。无效输入即使配 --force 也不改已有输出。

这是本地交付文件整理，命令名不代表已经向公众号发布或通过其后台认证。制作源 SVG 与 timeline 另行保留；清理版不再含 DOM 布局标注，布局测量继续使用制作源，交接后核动画与视觉是否保留。

1. 在本地文本编辑器打开生成的 publish.svg，复制完整 `<svg ...>…</svg>`，不要复制 Markdown 代码围栏、preview.html 的脚本或控制栏。多个图保留各自唯一 id 前缀。
2. 如已有富文本格式化器/编辑器支持 HTML 源码片段，将 SVG 放入其内容区；可手动组成 `<section>完整SVG源码</section>`。需要本地浏览器查看时，把该片段放入普通 HTML 的 body 即可，动画由 SVG 自身 SMIL 播放，无需 JS。
3. 普通公众号可视编辑区不等于 HTML 源码入口，直接粘贴 `<svg>` 字符串可能显示为文字。用户可从本地 HTML 选择渲染内容手动复制粘贴，或沿其已有可保留 SVG 的源码/富文本工具交接；两条路径都需实际核对，不能用浏览器播放成功代替后台解析证据。
4. 用户手动交接后，逐项记录编辑器保存、重新打开、公众号预览与手机结果；核 XML 层级、SMIL 标签/时码是否仍在、无脚本依赖及实际循环。被清洗或尚未验证就记录 NOT_VERIFIED；此 Skill 不操作微信账号，也不自动发送/发布。
