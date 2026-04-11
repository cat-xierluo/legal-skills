# Changelog

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
