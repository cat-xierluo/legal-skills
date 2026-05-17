# CHANGELOG

## [v1.3.0] - 2026-05-17

### 新增

- `scripts/svg2png.js`：SVG → PNG 高分辨率转换（由 svg-article-illustrator 简化而来）
  - 支持单文件和目录批量转换
  - 默认 600 DPI，支持 72–2400 DPI
  - SKILL.md 新增 PNG 导出使用说明
- 新增 `LICENSE.txt`，补齐 MIT 许可证全文

### 修复

- 修复 `scripts/svg2png.js` 使用 `networkidle0` 导致简单 SVG 转换超时的问题，改为 `domcontentloaded` 并增加 SVG 加载等待
- 修复 PNG 转换失败时浏览器进程可能未关闭的问题，使用 `finally` 兜底关闭
- 修复水平 `flow` 模板 4 节点尺寸不一致的问题，统一为 140px 节点并重算坐标

### 优化

- SKILL.md 精简：去掉"通用性"、"per-book 配置"等冗余说明，以功能说话

### 文档完善

- 将技能级任务跟踪文件从 `ROADMAP.md` 更正为 `TASKS.md`，符合本仓库 Skill 文档约定
- 调整第一阶段流程描述：默认插入占位符并继续生成，仅在用户明确要求时等待确认

## [v1.2.0] - 2026-05-17

### 重大变更：从物理尺寸反推所有参数

- **字号全面校准**：基于 16开 115mm 通栏印刷宽度推算
  - 节点标签：14px → **18px**（物理 2.88mm = 8.2pt，过中文印刷 8pt 下限）
  - 子标签：12px → **16px**（物理 2.56mm = 7.3pt，仅限简短补充）
  - 层标签：14px → **20px**（物理 3.20mm = 9.1pt）
  - 图标题：16px → **22px**（物理 3.52mm = 10pt）
- **标签字数限制收紧**：18px 下每节点最多 8 个汉字（原 14px 下 12 字）
- **元素密度下调**：水平 flow 最多 4 节点（原 5），hub 最多 5 外围（原 6）
- **间距放大**：最小间距 20px → **24px**，水平间距 24px → **28px**
- **新增完整印刷推算章节**：style-guide.md 第二节，含中国开本尺寸表、pt 换算公式、不同开本的最低字号表

### 其他

- layout-templates.md 所有 SVG 骨架的字号、节点尺寸、坐标同步更新
- 新增大32开适配说明（大32开建议缩小 viewBox 或放大字号）

## [v1.1.0] - 2026-05-17

### 新增与优化

- 组合模板、印刷黑白兼容、通用化
- 去掉书籍绑定，diagram-catalog.md 改为纯格式模板
- 场景覆盖分析

## v1.0.0 (2026-05-17)

由 `svg-article-illustrator`（公众号文章配图 Skill）演化而来。针对印刷出版场景重新设计：去掉 SMIL 动画/emoji/非白底等微信适配特性，画布改为 720×400（书籍版面比例），字号和间距按物理尺寸反推，扩展为 6 种通用布局模板。

初始包含：SKILL.md、style-guide.md、layout-templates.md、diagram-catalog.md、extract_svgs.py
