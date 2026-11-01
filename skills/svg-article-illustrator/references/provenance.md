# 借鉴来源与评估边界

本次 1.1.0 研究参考 [JamieJustTang/wechat-animating](https://github.com/JamieJustTang/wechat-animating)，固定评估提交为 [`372f3b2df2429c1d438dc742910c41ea94b00407`](https://github.com/JamieJustTang/wechat-animating/tree/372f3b2df2429c1d438dc742910c41ea94b00407)，评估日期 2026-10-29。提交通过 git ls-remote 获取；只读原始文件，不安装套件、不执行其脚本。不是对后续 main 的持续认证。

核对内容：该提交 README、authoring 的 timeline DSL、timeline_compile.py、validate_svg.py，以及 editor 的 zine-editor.html（setCurrentTime、pauseAnimations 和 unpauseAnimations）与预览入口。参考将静态骨架、秒数时码、编译校验和逐时点预览分离的方式；本 Skill 用独立的小型 tracks schema、XML 标准库、保守检查范围与本地 HTML 实现，不包含长卷编辑器、打字机、点击冒泡或上游效果 DSL。

已核 [固定提交的 LICENSE](https://github.com/JamieJustTang/wechat-animating/blob/372f3b2df2429c1d438dc742910c41ea94b00407/LICENSE)：MIT，Copyright (c) 2026 JamieJustTang。本次没有复制上游实现代码或样图，仅借鉴工作方法，来源在此归因。将来如实质复用其代码，需要同时保留相应许可与版权，不把本记录替代许可证。

上游的公众号白名单、纯矢量或跨设备兼容性描述是其项目声明，不作为本 Skill 的实测证据，也不据此推断任何公众号文章使用了该项目。引用外部图片的图要另列资源、用途与大小；不能把 SVG 源码体积当作完整传输体积。
