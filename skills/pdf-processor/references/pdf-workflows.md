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

# 确需处理超大栅格时调高单页像素上限；0 表示关闭保护（高内存风险）
python3 scripts/pdf-preprocess-ocr.py --input input.pdf --output output.pdf \
  --max-preprocess-megapixels 40
```

默认 `medium` 合并输出参数：

| 档位 | 预处理 DPI | JPEG 质量 | 色度子采样 | 适用场景 |
| --- | ---: | ---: | ---: | --- |
| `low` | 300 | 85 | 0 | 打印或高清保留 |
| `medium` | 200 | 72 | 1 | 默认，兼顾法院上传与放大阅读 |
| `high` | 130 | 45 | 2 | 文件大小限制严格 |

表中 DPI 是目标值。默认单页像素上限为 25MP；当手机图片 PDF 把 2305×3310 像素直接写成 2305×3310 point 等异常物理页面尺寸时，统一入口会自动降低实际 DPI，避免预处理生成超大位图后又被 OCR 的 `--skip-big` 跳过。普通 A4、Letter 页面通常不会触发。

## 拍照件规整参数

```bash
# 默认流程包含纸边透视、无纸边内容主体识别、表框精校、去阴影和 A4 排版
python3 scripts/pdf-photo-normalize.py \
  --input photo.jpg --output photo.pdf \
  --report /tmp/photo-report.json --debug-image /tmp/photo-debug.jpg

# 按校正后的纸面比例设置 PDF 页框
python3 scripts/pdf-photo-normalize.py \
  --input photo.jpg --output photo.pdf --page-size original

# 淡墨材料可减轻附加对比度增强
python3 scripts/pdf-photo-normalize.py \
  --input photo.jpg --output photo.pdf --contrast-strength 0.3

# 明确指定方向，跳过 Tesseract OSD
python3 scripts/pdf-photo-normalize.py \
  --input photo.jpg --output photo.pdf --rotate 90

# 多张照片逐页规整后合并；目录内按自然文件名排序
python3 scripts/pdf-photo-batch.py \
  --input /path/to/photo-dir --output merged.pdf \
  --report /tmp/photo-batch-report.json
```

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--page-size` | `a4` | A4 页框为 210 × 297 mm，横纵随纸面方向。纸边通过检测时，校正后的纸面铺满 A4。`auto` 按纸面比例选页，选中 A4 时采用同样规则。`letter` 等比居中，`original` 保留校正后的纸面估计比例 |
| `--rotate` | `auto` | 应用 EXIF 方向后，使用可用的 Tesseract OSD 检查 90° 倍数方向。也可指定顺时针角度 |
| `--illumination-strength` | `0.78` | 亮度阴影归一强度，取值 0–1 |
| `--contrast-strength` | `0.7` | 附加亮度曲线强度，取值 0–1。设 `0` 保留基础去阴影与局部对比度处理 |
| `--dpi` | `300` | 输出栅格分辨率。标准页框的物理尺寸固定 |
| `--jpeg-quality` | `90` | PDF 内嵌 JPEG 质量 |
| `--report` | 无 | 输出 JSON 报告，记录纸面四边、方向、表框精校状态和校正前的角度、亮度离散指标、页面和内容尺寸 |
| `--debug-image` | 无 | 在原图上标出检测到的纸面四边 |

表框精校适用于纸面或主体区域可定位且有连贯横竖边和多个单元格的平面表格。估计变形较大、表框残缺或纸面弯曲明显时，检查报告中的 `table_alignment.status`，并以实际渲染复核。自动裁纸边需要至少三条候选边能将纸面与较暗的外部区域区分开。纸边证据不足或候选框外有成片深色痕迹时，进入内容主体 fallback。

内容主体 fallback 使用本地自适应墨迹和形态学文本行检测，按横向重叠和纵向邻近聚簇，选择墨迹面积最大的主文书簇，并纳入邻近的印章、签名等非文本痕迹。至少需要 5 个文本行、主体墨迹覆盖率不低于 55%、主体面积在 15%–92% 且比例合理。重叠页中未被选择的文本行记为 `secondary_component_count`，纳入的非文本痕迹记为 `artifact_component_count`。证据不足或纳入痕迹后候选框过宽时不裁剪，不把半页主体补成完整 A4。报告 `quad.source` 为 `content_subject`，调试图使用绿色框；完整纸边仍为红色框。

2.16.1 起，“非文本痕迹”仅指通过归属检验的高饱和彩色印章/签章；存在可靠旁页文本行证据时，只有明显更近主文书的印章会保留。底缘仅剔除宽而稀疏的深色地面条带，并用延续到底的暗区识别纸张与桌面边界；密实贴底正文、页脚和签名日期行保留，主体框底部只保留较小排版余量。

单张入口一次处理一张单帧照片。多页 TIFF 或其他多帧图像须先拆为单页再处理。批量入口可传多个文件或目录，目录内按自然文件名排序；每张生成一页，全部成功后才写出合并 PDF。PDF 和报告均须指向尚不存在的新文件，已有文件请另选文件名重试。

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

# 兼容旧参数；auto 已全程本地，不再读取 API 顺序
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf \
  --backend auto --api-order paddle,mineru

# 兼容旧参数；auto 默认不上传
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf --local-only

# 电子/混合 PDF 只有在明确接受矢量、文字和批注层被栅格化的风险时才强制预处理
python3 scripts/pdf-preprocess-ocr.py -i input.pdf -o output.pdf --force-raster-preprocess
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
