# 验证设计与回归入口

本工具的实现者运行回归，交回真实产物供另一位审阅者复验；不以生产者自报替代独立视觉审阅，不把单轮测试称作多轮指令稳定性认证。

| 设计层 | 本 Skill 的落实 |
|---|---|
| Contract | 时间轴字段、文件副作用、失败码及支持子集见 timeline-tools；项目视觉要求保留在调用方 |
| Producer | 标准库编译器、独立骨架/JSON、可指定输出、默认不覆盖；PNG 为可选依赖 |
| Verifier | 输出重新解析；独立回归断言结构与数值；浏览器检查真实 DOM 与截图；PM/审阅者审内容 |
| Evidence binding | validate 的源码 SHA-256/字节数；测量记录当前产物、浏览器宽度、秒数和截图；变更后重跑 |
| Fault injection | 错 keyTimes、空目标、重复 cue、同层变换、外部资源、长中文与混排、双重位移反例 |
| Closure | 本地工具结果、文章回填、平台保存与真机分别结算；未验项明确 NOT_VERIFIED |
| Composition | 样式、画幅、归档、发布由调用项目控制；协作者交源文件与证据而非只报 PASS |

Hard Fail：结构/时码/资源校验失败、当前输出未测却声明布局通过、未测真机却声明公众号成功、预览 JS 混入发布 SVG。语义质量、遮挡意图和连续时间全覆盖不伪装成自动证明。

文章动态配图有两个默认门禁：每段 SVG 至少包含一组原生 SMIL，循环时长为 **3–5 秒**。`validate` 与 `publish` 默认拒绝静态文件，也拒绝没有 `animate` / `animateTransform` 的文件；编译和校验同时拒绝 3–5 秒范围外的循环。只有配图计划与交付说明已逐图写明理由的静态例外，才可显式使用 `--allow-static`。测试绑定 3、4、5 秒正例，2.9、5.1 秒反例，以及静态默认拒绝/显式放行两条路径。压缩时长后必须重测初态、过程、关键结果停留、循环交界和两个完整周期；只核动画仍存在，不能证明过程仍可读。

逃逸反例：给合法静态 `translate(100 120)` 的组再配绝对轨迹 `100 120 → 110 130`，XML 和 SMIL 都合法，但实际位置是 `(200,240) → (210,250)`。编译成功不能识别作者意图；浏览器坐标断言与真实消费审阅负责发现。另一反例是长混排文字在窄容器溢出；XML 通过，DOM 测量需失败。合法近似正例为分行文字与真正隐藏的互斥状态。

## 命令

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_svg_motion.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_svg_motion.py --browser-fixture /tmp/svg-browser-test
```

第二条生成一个自包含 HTML、编译 SVG 与输入样例到指定空目录，使用当前工具与回归脚本。打开 HTML 后，在控制台或自动化 evaluate 调用 `await runSvgMotionBrowserChecks()`。它使用浏览器 SMIL 和真实几何断言相对/绝对位置、重复定位反例、跨循环、长混排溢出、分行近似正例及互斥状态。返回通过数或抛错；不会用文字匹配代替几何。自动化单次 evaluate 有时间限制时可分批调用，例如 `runSvgMotionBrowserChecks({phase:"geometry",widths:[375],times:[0,1]})`；geometry 的完整时点为 0、1、2、3.999、4.001、8.001，layout 可用 `{phase:"layout",widths:[375]}` 独立调用；`{phase:"wait"}` 注入 hidden 与不回调 rAF，验证拒绝和有界超时，不把注入测试当作所有真实后台调度场景的证明。

此外仍需通过预览 UI 实际执行播放、暂停、逐秒与宽度切换，播放两个周期并检查关键截图。浏览器回归函数覆盖的是固定场景，不能代替真实文章逐图验收。

正式 Skill-lint 的候选绑定签名与三轮前向评估未由这些命令执行，不应声称 `HARNESS_REVIEW_VERIFIED` 或 `INSTRUCTION_STABILITY_VERIFIED`。无旧上下文的创作前向测试、目标项目采用与真机证据由相应审阅者补充。
