# PDF 单项工具参数参考

本文档收纳 `SKILL.md` 中不需要常驻加载的命令细节。默认一键流程仍以 `scripts/pdf-preprocess-ocr.py` 为入口。

## 输出命名规则

- 输出文件不覆盖原始文件。
- 原文件名已有日期前缀时原样保留。
- 输出路径冲突时在文件名末尾追加 `_1`、`_2` 等序号。
- 示例：`合同.pdf` -> `合同_已处理.pdf`；若同名文件已存在，则为 `合同_已处理_1.pdf`。

## 预处理参数

```bash
# 一键预处理 + OCR
python3 scripts/pdf-preprocess-ocr.py --input input.pdf --output output.pdf

# 只预处理，不 OCR
python3 scripts/pdf-preprocess-ocr.py --input input.pdf --output output.pdf --preprocess-only

# 只页面矫正，不压缩、不 OCR
python3 scripts/pdf-preprocess-ocr.py --input input.pdf --output output.pdf \
  --preprocess-only --no-compress

# 页面方向已正确的大文件提速
python3 scripts/pdf-preprocess-ocr.py --input input.pdf --output output.pdf \
  --skip-coarse-rotation --preprocess-jobs 6 --preprocess-chunk-pages 80

# 需要裁剪白边时显式启用
python3 scripts/pdf-preprocess-ocr.py --input input.pdf --output output.pdf --enable-crop
```

默认 `medium` 合并输出参数：

| 档位 | 预处理 DPI | JPEG 质量 | 色度子采样 | 适用场景 |
| --- | ---: | ---: | ---: | --- |
| `low` | 300 | 85 | 0 | 打印或高清保留 |
| `medium` | 200 | 72 | 1 | 默认，兼顾法院上传与放大阅读 |
| `high` | 130 | 45 | 2 | 文件大小限制严格 |

## OCR 参数

```bash
# 默认 auto
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf

# 仅对无文字层页面做 OCR
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf --mode skip

# 强制全量重建 OCR 层，高风险
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf --mode force

# 已预处理文件，不重复 rotate/deskew
python3 scripts/pdf-ocr.py -i preprocessed.pdf -o output.pdf --preprocessed

# 指定 API 顺序
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf --backend auto --api-order paddle,mineru
```

## 压缩参数

单独压缩只在用户明确要求“压缩 PDF”时执行。

```bash
# 默认中等压缩
python3 scripts/pdf-compress.py -i input.pdf -o output.pdf

# 指定压缩级别
python3 scripts/pdf-compress.py -i input.pdf -o output.pdf --level high

# 移除元数据
python3 scripts/pdf-compress.py -i input.pdf -o output.pdf --remove-metadata
```

独立压缩脚本的参数与统一入口的合并输出参数不是同一套实现；统一入口的 `medium` 默认更偏扫描件文字清晰度。

| 级别 | JPEG 质量 | 等效 DPI | 适用场景 |
| --- | ---: | --- | --- |
| `low` | 85 | 300 DPI | 打印 |
| `medium` | 65 | 200 DPI | 屏幕阅读 |
| `high` | 45 | 150 DPI | 小体积归档 |

## 页码参数

```bash
# 默认：底端右边，Helvetica 15pt，上10mm/下5mm/左右15mm
python3 scripts/pdf-add-page-numbers.py -i input.pdf -o output.pdf

# 自定义位置和字体大小
python3 scripts/pdf-add-page-numbers.py -i input.pdf -o output.pdf \
  --position bottom-center --font-size 12

# 自定义边距
python3 scripts/pdf-add-page-numbers.py -i input.pdf -o output.pdf \
  --margin-top 15 --margin-bottom 10

# 从第 5 页开始编号
python3 scripts/pdf-add-page-numbers.py -i input.pdf -o output.pdf --start 5

# 使用 Times 字体
python3 scripts/pdf-add-page-numbers.py -i input.pdf -o output.pdf --font times
```

页码位置：`bottom-right`、`bottom-center`、`bottom-left`、`top-right`、`top-center`、`top-left`。

字体：`helv`、`times`、`cour`。

## 合并参数

```bash
# 基本合并
python3 scripts/pdf-merge.py -i file1.pdf file2.pdf file3.pdf -o merged.pdf

# 合并并为每个文件独立编号
python3 scripts/pdf-merge.py -i file1.pdf file2.pdf -o merged.pdf --add-numbers

# 合并并全局连续编号
python3 scripts/pdf-merge.py -i file1.pdf file2.pdf -o merged.pdf --add-numbers --continuous

# 自定义页码位置和字体
python3 scripts/pdf-merge.py -i file1.pdf file2.pdf -o merged.pdf \
  --add-numbers --position bottom-center --font-size 12
```

合并只做合并和可选编号，不自动预处理输入文件。
