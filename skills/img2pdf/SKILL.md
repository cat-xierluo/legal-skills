---
name: img2pdf
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.0.0"
description: 将图片或 PDF 页面按 N 张/页编排为标准化 A4 PDF，或将长截图渲染为单张自适应高度 PDF。本技能应在用户需要将截图（手机截图、视频截图）、照片、已有 PDF 页面或长截图（微信聊天、庭审笔录）合并为 PDF 时使用。不要用于：OCR 文字识别、PDF 内容编辑、图片格式转换。
license: MIT
---

# img2pdf

## 定位

本技能解决"大量截图/照片需要编排为紧凑 PDF 提交"以及"超长截图（微信聊天、庭审笔录）需要保留上下逻辑转为 PDF"的问题。核心场景是法律证据材料整理。

核心职责：

1. 将图片目录或多个图片文件编排为 A4 PDF，支持 1/2/3/4 张每页。
2. 将已有 PDF 的每页重新编排为 N 张每页的紧凑布局。
3. 自动检测图片横竖方向，选择合适的 A4 页面方向。
4. 可配置页边距，确保打印效果良好。
5. **v1.2.0** 长截图模式：按 A4 比例自动切割超长图再编排（微信聊天场景），或将整张长图渲染为单张自适应高度 PDF（庭审笔录场景）。

本技能不做 OCR、不编辑 PDF 内容、不处理视频文件。若需要从视频提取截图，先使用 video-screenshot。

## 与其他技能配合

- 上游：video-screenshot 提取视频截图后，用本技能编排为 PDF。
- 上游：截图工具（手机截图、浏览器截图）产出的图片文件。
- 下游：pdf-organizer 可对编排后的 PDF 做进一步整理（拆分、合并、命名）。
- 替代：pdf-organizer 的 `--normalize-a4` 只做页面标准化，不做多图编排。

## 依赖

### 系统依赖

无额外系统依赖。

### Python 包

| 包名 | 用途 | 安装命令 |
|------|------|----------|
| `pypdf>=4.0.0` | PDF 页面变换与合并 | `python3 -m pip install -r scripts/requirements.txt` |
| `Pillow>=10.0.0` | 图片格式检测 | 同上 |
| `PyMuPDF>=1.24.0` | 图片转 PDF 页面 | 同上 |

## 输入/输出

### 输入

- 图片目录：扫描目录下所有 JPG/PNG/WebP 文件。
- 多个图片文件：直接列出图片路径。
- 已有 PDF：将 PDF 每页当作图片重新编排。

### 输出

- 单个 A4 PDF 文件，每页包含 1-4 张图片，等比缩放居中。

## 工作流程

### 1. 收集输入

根据 `--input` 参数收集图片或 PDF 文件。如果是目录，扫描其中所有支持格式的图片。按文件名或修改时间排序。

### 2. 转换为页面

- 图片文件：通过 PyMuPDF 转为单页 PDF。
- PDF 文件：读取每一页作为独立页面。

### 3. 计算布局

根据 `--per-page` 和页面方向计算每张图片的可用区域：

- `per-page=1`：整页减去边距，横竖由图片方向决定。
- `per-page=1`：整页减去边距，横竖由图片方向决定。
- `per-page=2`：A4 横版，左右两列。
- `per-page=3`：A4 横版，三列并排。
- `per-page=4`：A4 横版或竖版，2×2 网格。
- `per-page=auto`（默认）：竖版图多 → 3张/页，横版图多 → 1张/页。

每张图片等比缩放适配其可用区域，居中放置。

### 4. 生成 PDF

将编排后的页面写入输出 PDF。不修改任何原始文件。

## 执行脚本

首次使用时安装依赖：

```bash
python3 -m pip install -r scripts/requirements.txt
```

### 手机截图（自动 3 张/页）

```bash
python3 scripts/img_to_pdf.py \
  --input /path/to/screenshots/ \
  --output /path/to/output.pdf
# 自动检测：竖版图多 → 3张/页
```

### 电脑截图（自动 1 张/页）

```bash
python3 scripts/img_to_pdf.py \
  --input /path/to/desktop-screenshots/ \
  --output /path/to/output.pdf
# 自动检测：横版图多 → 1张/页（A4横版）
```

### 手机截图 2 张/页（A4 横版左右并排）

```bash
python3 scripts/img_to_pdf.py \
  --input /path/to/screenshots/ \
  --output /path/to/output.pdf \
  --per-page 2
```

### 视频截图 3 张/页

```bash
python3 scripts/img_to_pdf.py \
  --input /path/to/frames/ \
  --output /path/to/output.pdf \
  --per-page 3
```

### 已有 PDF 重新编排

```bash
python3 scripts/img_to_pdf.py \
  --input /path/to/original.pdf \
  --output /path/to/repacked.pdf \
  --per-page 2
```

### 多个图片文件

```bash
python3 scripts/img_to_pdf.py \
  --input img1.jpg img2.jpg img3.png \
  --output /path/to/output.pdf \
  --per-page 3
```

### 微信聊天长截图（v1.2.0，按 A4 比例自动切 + 3 张/页）

```bash
python3 scripts/img_to_pdf.py \
  --input /path/to/wechat_long.png \
  --output /path/to/wechat.pdf \
  --split \
  --per-page 3
# 1080×6000 → 按 1080×√2≈1527px 切 4 段 → 2 页 A4 横版
```

### 微信聊天长截图（显式切割段高）

```bash
python3 scripts/img_to_pdf.py \
  --input /path/to/wechat_long.png \
  --output /path/to/wechat.pdf \
  --split \
  --split-height 1500 \
  --per-page 3
```

### 庭审笔录长截图（v1.2.0 vertical 模式，整图一长页）

```bash
python3 scripts/img_to_pdf.py \
  --input /path/to/transcript.png \
  --output /path/to/transcript.pdf \
  --mode vertical
# 不切割，1080×5000 → 1 页 595×2573pt
# 页面高度按图等比缩放，保留上下逻辑
```

### 预览（不写入文件）

```bash
python3 scripts/img_to_pdf.py \
  --input /path/to/dir/ \
  --per-page 2 \
  --dry-run
```

### 常用参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--input` / `-i` | 图片文件、PDF 文件或目录（必填） | - |
| `--output` / `-o` | 输出 PDF 路径 | `<输入名>_编排.pdf` |
| `--mode` | 编排模式：`nup`（N 张/页）或 `vertical`（单图一长页） | `nup` |
| `--per-page` / `-n` | nup 模式下每页图片数：`1`/`2`/`3`/`4`，或省略自动 | `auto`（竖版3张，横版1张） |
| `--margin` / `-m` | 页边距（pt） | `25` |
| `--orientation` | nup 模式页面方向：`auto`/`landscape`/`portrait` | `auto` |
| `--sort` | 排序：`name`/`time`/`none` | `name` |
| `--split` | 启用长截图切割（nup 模式） | 关闭 |
| `--split-height` | 切割段高（px）；不传 = 按 A4 比例（`图宽 × √2`）；vertical 模式忽略 | A4 比例 |
| `--dry-run` | 仅预览不输出 | `false` |

### 两种模式对照

| 维度 | nup | vertical |
|------|-----|----------|
| 是否切割 | 视 `--split` 而定 | 不切（强制） |
| 每页图数 | 1/2/3/4 | 必为 1 |
| 页面尺寸 | A4 固定 | 宽度固定 A4 595pt，高度按图等比 |
| 适用场景 | 微信聊天、视频截图、证据照片 | 庭审笔录、单页长截图 |

## 交付检查

完成后检查：

1. 输出 PDF 页数 = ceil(总图片数 / per-page)（nup 模式）或 = 图片数（vertical 模式）。
2. 每页图片清晰可读，没有超出页面边界。
3. 页边距合理，打印时不会裁切内容。
4. 横竖方向正确（手机截图横版并排，视频截图三列等）。
5. 原始图片和 PDF 未被修改或删除。
6. **长截图模式**：切割段高符合 `--split-height` 或 A4 比例默认；vertical 模式页面高度 = 图高 × (A4 宽 - 2×margin) / 图宽 + 2×margin。
7. **vertical 模式**：临时目录已清理（`/tmp/img2pdf-splits-*` 不残留）。
