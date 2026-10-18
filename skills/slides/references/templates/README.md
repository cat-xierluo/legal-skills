# HTML 幻灯片模板库

完整可渲染的 HTML 模板文件，每个模板包含设计系统 + 页面结构 + 示例内容。

## 使用方法

1. 从下表选择合适的页面模板
2. 复制对应 HTML 文件，替换占位内容
3. 切换主题变量（`:root` 中的颜色变量）应用不同风格
4. 所有模板共享 `_base.css` 设计系统

## 模板索引

| 文件 | 页面类型 | 主题 | 适用场景 |
|------|---------|------|---------|
| `01-cover.html` | 封面页 | dark | 演示开场、章节封面 |
| `02-content-list.html` | 标题+要点 | light | 观点罗列、规则说明 |
| `03-data-grid.html` | 大数据/KPI | dark | 指标汇报、成果展示 |
| `04-quote.html` | 金句/引用 | dark | 核心结论、转折悬念 |
| `05-timeline.html` | 横向时间线 | light | 案件经过、项目里程碑 |
| `06-two-column.html` | 左右对比 | light | 方案比较、新旧对比 |
| `07-section-divider.html` | 章节分隔 | dark | 幕间转场、节奏呼吸 |
| `08-case-evidence.html` | 证据卡片 | light | 判例拆解、证据链说明 |
| `09-process-flow.html` | 流程步骤 | light | 操作步骤、方法论 |
| `10-risk-matrix.html` | 风险矩阵 | light | 风险分级、审查摘要 |
| `11-training.html` | 培训讲义 | light | 法律培训、课程讲义 |
| `12-image-text.html` | 图文混排 | light | 案例展示、产品介绍 |

## 页面节奏建议

| 页码 | 推荐模板 | 主题 | 说明 |
|------|---------|------|------|
| 1 | 01-cover | dark | 开场 |
| 2 | 07-section-divider | dark | 第一幕 |
| 3 | 02-content-list | light | 核心观点 |
| 4 | 03-data-grid | dark | 数据冲击 |
| 5 | 05-timeline | light | 事件脉络 |
| 6 | 06-two-column | light | 对比分析 |
| 7 | 07-section-divider | dark | 转场 |
| 8 | 04-quote | dark | 金句收束 |
| 9 | 08-case-evidence | light | 证据展开 |
| 10 | 09-process-flow | light | 方法论 |
| 11 | 10-risk-matrix | light | 风险评估 |
| 12 | 01-cover | dark | 收尾 |

节奏规则：
- 禁止连续 3 页以上相同主题（dark 堆叠或 light 堆叠）
- 每 3-4 页插入 1 个 dark 页（cover/quote/divider）
- 8 页以上的 deck 至少 1 个 quote 页

## 设计系统

共享 `_base.css` 提供：
- 间距系统（--sp-xs 到 --sp-2xl）
- 排版刻度（--text-xs 到 --text-hero）
- 组件样式（.card, .callout, .badge, .stat-card 等）
- 布局工具（.grid-2, .grid-3, .grid-4, .grid-7-5, .grid-8-4）
- 动画系统（data-anim 属性，仅浏览器模式生效）
- PPTX 兼容约束（无渐变、无 inset 阴影、语义标签）
