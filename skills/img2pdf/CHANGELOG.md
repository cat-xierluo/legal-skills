# Changelog

## v1.2.0 (2026-06-11)

长截图模式：解决"超长截图（微信聊天、庭审笔录）→ PDF"的两种典型需求。

### 新增

- **`--mode {nup, vertical}`** 编排模式切换
  - `nup`（默认）：复用现有 N 张/页编排
  - `vertical`：单图成单页，页面高度按图等比自适应，强制 portrait
- **`--split`** 长截图切割开关（nup 模式）
  - 启用后按 `--split-height` 把超长图切成多段再走 N 张/页
  - 切割段存临时目录（`/tmp/img2pdf-splits-*`），流程结束自动清理
- **`--split-height N`** 显式覆盖切割段高（像素）
  - 不传时按 A4 比例自动算（`图宽 × √2 ≈ 图宽 × 1.414`），让每段宽高比 1:1.414
  - 适合 N 张/页编排不留白
- **短图自动跳过切割**：图高 ≤ 段高时不切，打印 `图片 xxx.png 高度 Hpx，未触发切割`
- **健康检查**：总切出段数 > 原图数 × 5 时打印警告，建议调大 `--split-height`
- **vertical 模式 + 误用提示**：vertical 模式下传 `--split` / `--split-height` 静默忽略 + 打印 `⚠️ vertical 模式不支持切割，--split / --split-height 被忽略`
- **vertical 模式 + PDF 跳过**：vertical 模式不处理 PDF 输入（PDF 自带分页），跳过并提示

### 适用场景

- 微信聊天记录长截图：`--split --per-page 3`（按 A4 比例自动切，3 张/页编排）
- 庭审笔录长截图：`--mode vertical`（不切，整图一长页，保留上下逻辑）

### 兼容性

- 默认行为完全不变：`--mode nup`、未传 `--split`，所有 v1.0.0 / v1.1.0 用法零迁移
- 现有测试用例继续通过

### 文档

- `SKILL.md` 增加 vertical 模式 + 长截图切割 examples、参数表、模式对照表
- `references/layout-examples.md` 增加 vertical 模式与长截图切割示意图
- `DECISIONS.md` DEC-004 记录设计决策

### 实机验证

5 个测试用例全部通过（详见 `TASKS.md` v1.2.0 实机测试清单）：

1. 微信场景（1080×6000 + `--split --per-page 3`）→ 切 4 段、2 页 A4 横版
2. 笔录场景（1080×5000 + `--mode vertical`）→ 不切、1 页 595×2573pt
3. vertical + `--split-height 1500` → 提示忽略，仍不切
4. 短图（1080×1500 + `--split`）→ 提示未触发切割
5. vertical + PDF 输入 → PDF 跳过，仅图出页

## v1.1.0 (2026-06-01)

- `--per-page` 默认改为 auto 模式：竖版图多 → 3张/页，横版图多 → 1张/页
- 修复 `process()` 中重复处理输入文件的 bug

## v1.0.0 (2026-06-01)

- 初始版本
- 支持图片目录、多图片文件、已有 PDF 三种输入模式
- 支持 1/2/3/4 张每页编排
- 自动检测横竖方向选择 A4 横版或竖版
- 可配置页边距
- 支持 dry-run 预览
