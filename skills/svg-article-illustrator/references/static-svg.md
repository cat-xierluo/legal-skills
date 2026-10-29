# 静态 SVG

适合关系、分类、并列比较、结构全景，以及读者需要随时回看的总结。箭头与虚线可以保持静态，静态图也可以使用多行文字和功能性容器。

按 [共享原则](core-principles.md) 规划尺寸与内容，按项目选择内联或独立文件。`assets/layouts.svg` 是可直接打开、测量或导出 PNG 的三步流程例子；不再是把 Markdown 片段存成 `.svg` 的模板集合。按实际内容重排，不把例子字号或配色当成要求。

运行 `python3 scripts/svg_motion.py validate assets/layouts.svg`，并使用 preview 生成 HTML，切到 375px 检查文字和图形。静态图也会裁切、字体回退、重叠；结构通过不证明布局通过。对不接受 SVG 的目标平台，保留可编辑 SVG 并按 [PNG 路径](png-export.md) 导出。

公众号编辑器保存、预览与真机结果分别记录；不使用“完美支持”或“所有平台通用”的保证。
