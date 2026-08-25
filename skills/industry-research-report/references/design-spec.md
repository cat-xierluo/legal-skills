# 设计规范

## 设计定位：蓝皮书体例

律所对外正式发布物的经典版式(深蓝主色 + 金色装饰)。
**核心是文字版手册**,克制图形化强度。

## 配色（bluebook 默认）

| 角色 | 色值 | 用途 |
|---|---|---|
| 主背景 | `#FFFFFF` | 页面底色 |
| 次背景 | `#F4F1EA` | 米黄,偶用于卡片 / 引用块 / 偶数表行 |
| 主色 | `#1B3C59` | 封面底色 / 大标题 / 表格表头 / 页眉 |
| 强调色 | `#D4AF37` | 标题下划线 / h3 左边框 / 装饰线 |
| 文字主 | `#1A1A1A` | 正文 |
| 文字次 | `#2C3E50` | 段落 |
| 文字淡 | `#666666` | 辅助 / 页码 |
| 危险 | `#C53030` | 风险标签 |
| 确认 | `#2F855A` | 机会标签 |

> 配色组 `service-plan` 是备选（律所深棕系）。详见 SKILL.md "渲染管线 / 封面变体"。

## 字体

- 衬线中文（封面 / 大标题 / h2）:`Noto Serif SC / Source Han Serif SC / Songti SC / SimSun / 宋体`
- 无衬线中文（小标签 / 页码）:`Noto Sans SC / PingFang SC / Microsoft YaHei`

字号(单位 pt):

- 封面大标题:36pt 加粗,字间距 3px
- 封面副标:14pt
- h1（章节）:24pt 加粗
- h2:17pt 加粗 + 金色下划线
- h3:12pt 加粗 + 5px 金色左边框
- 正文:11pt,行距 1.85,首行缩进 2em
- 表格:10pt

## 页面尺寸

A4（210mm × 297mm）。CSS：

```
@page { size: A4; margin: 0; }
```

正文 page padding：上 22mm,左右 22mm,下 25mm（让出页脚空间）。
Playwright margin 仅在底部预留 16mm 给页脚。

## 封面变体

| 变体 | 视觉特征 |
|---|---|
| C-geo | 顶部几何圆形装饰 + 律所名 band,正文下移到 1/3 处 |
| D-diagonal | 对角线斜切封面,大标题压暗金色 |
| E-flip | 左右镜像对称,标题压在大圆盘上 |
| F-grid | 顶部网格 + 多色块,信息量大 |

> 四个 cover HTML 在 `references/covers/`,由 `scripts/render.py` 按 `report-profile.md` 的 `cover_style` 选择注入。

## 页眉页脚

- 页眉（每页正文顶部 14mm 高度）：
  - 左侧：系列名 + 章节名（如"XX 律所实务手册 · 第 3 章 行业概览"）
  - 右侧：报告编号（如"YWX-IR-2026-01"）
  - 底部 1px 主色横线
- 页脚（每页正文底部 16mm 高度）：
  - 左侧：律所名 + 系列名
  - 右侧：报告名（footer_brand）+ 页码/总页数
  - 顶部 1px 金色横线

## 表格

- 表头：深蓝底白字 + 9px 加粗 + 6px 10px padding
- 行：白底 / 米黄底交替
- 行高：单行不跨页（`page-break-inside: avoid`）,整表可跨页（thead 自动重复）

## h3 子节装饰

```
border-left: 5px solid #D4AF37;
padding-left: 11px;
```

不可用大字号（保持 12pt,像加粗段落而非大字标题,法律文书风格）。

## 章节页（C 章前空白页）

- 上方"PREFACE / CHAPTER XX · 编号"小标签（10pt,字间距 4px,主色）
- 下方大号衬线章节标题（24pt 加粗,主色）
- 底部 2px 主色水平分割线
- 标题下留 1 个空行给导语段落
