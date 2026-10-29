---
name: svg-article-illustrator
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.1.1"
license: MIT
description: 根据文章内容创作静态SVG、SMIL过程动画或界面操作配图，提供秒数时间轴编译、离线预览与浏览器布局测量，也支持PNG导出。用于文章配图、SVG插图或SVG转PNG；不用于完整视频制作或自动发布。
---
# SVG Article Illustrator

读取全文与调用项目的视觉、画幅、嵌入、归档约定，再做配图。以需要解释的内容选择静态或动态；关系对比已经清楚时保留静态，不为箭头、虚线框或装饰强加动画。

## 工作方法

1. **内容 → 配图计划**：为每张图记录对应段落、读者需要理解的关系/变化、图的作用、插入点、输出模式。按信息增益决定数量，不按标题数或固定张数配图。
2. **计划 → 对象/状态**：列出对象、标签、容器、坐标系、初末状态和互斥关系。先布置关键停留帧；界面演示要表现操作与反馈，机制图要表现条件、流转或状态改变。
3. **状态 → 秒数时间轴**：写清出现、移动、反馈、阅读停留和复位的秒数。先给读者看清变化的时间，再安排运动。静态图跳过时间轴步骤。
4. **骨架 + 时间轴 → SVG**：动态使用唯一 `data-cue` 定位实际图形；通过 [时间轴工具](references/timeline-tools.md) 编译，不手算大量 keyTimes。静态直接输出可读 SVG。变换坐标合同和修正示例见 [动态规范](references/dynamic-svg.md)。
5. **SVG → 实测**：运行结构校验；打开自包含 HTML，在桌面与 375 CSS px 宽度测量真实文字与对象，检查截图。覆盖初态、停留、运动中段、循环末与下一轮；实际播放两个完整周期。测量方法及边界见 [布局验收](references/layout-verification.md)。
6. **实测 → 交付**：按调用项目要求内联 SVG、保存文件或插入 PNG；回读实际交付内容，确认动画、ID 引用和文本仍完整。通过 publish 剥离制作标记，保留原生 SMIL；预览 HTML 的 JS 不进入发布 SVG。本地 HTML 片段交接见工具参考。提供源骨架、时间轴和验证记录以便修改。

## 按需加载

| 任务 | 参考 |
|---|---|
| 选画幅、安排文字与对象 | [共享原则](references/core-principles.md) |
| 操作演示、机制或状态变化 | [动态 SVG](references/dynamic-svg.md) |
| 编译 JSON、校验与预览 CLI | [时间轴工具](references/timeline-tools.md) |
| DOM 测量、长文本、重叠反馈 | [布局验收](references/layout-verification.md) |
| 关系、分类、并列对照 | [静态 SVG](references/static-svg.md) |
| 输出 PNG | [PNG 导出](references/png-export.md) |
| 多图有界委派 | [并行协作](references/multi-agent-generation.md) |
| 维护与回归、独立复验 | [验证设计](references/verification.md) |
| 借鉴来源与评估边界 | [来源记录](references/provenance.md) |

## 工具入口

以下命令在 Skill 目录运行，输出路径可指定；已有文件默认拒绝覆盖，确认替换时加 `--force`。Python 工具仅使用标准库，不安装第三方套件。

```bash
python3 scripts/svg_motion.py compile assets/demo.skeleton.svg assets/demo.timeline.json -o /tmp/demo.svg
python3 scripts/svg_motion.py validate /tmp/demo.svg
python3 scripts/svg_motion.py preview /tmp/demo.svg -o /tmp/demo.html
python3 scripts/svg_motion.py publish /tmp/demo.svg -o /tmp/demo.publish.svg
```

在浏览器打开生成的 HTML；播放、暂停、重置、逐秒步进与时间滑杆只服务于制作预览。其测量函数 `window.measureSvgLayout(svg)` 也可由浏览器自动化调用。示例是小型操作状态演示，风格、尺寸与节奏不是通用模板。

PNG 路径保留 `node scripts/svg2png.js input.svg [output.png] [dpi]`，需要既有 Node.js、Puppeteer和浏览器；缺少时按环境约定准备项目本地依赖，不自动做全局安装。

## 交付边界

- XML/时序检查通过仅代表本工具支持的保守 SVG 子集通过；未知语法会拒绝，检查边界见工具参考。
- 布局测量基于实际 DOM，可发现边界问题与碰撞候选；不能仅凭字符估宽、一个时点或文字边界交集断言画面正确。容器、互斥状态与有意遮挡都保留可观察证据。
- 浏览器成功不证明公众号编辑器、保存后预览或手机 WebView 成功。逐环境记录实测时间、入口与结果；未测项写 `NOT_VERIFIED`。静态 SVG 与 PNG 也要核对实际字体、裁切和发布入口。
- 默认交回计划、源码和本地验证结果；内容发布、外部上传和安装不包含在本 Skill 的默认动作内。
