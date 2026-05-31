# 外部 PaddleOCR API 接入指引

本文档用于指导 `pdf-processor` 使用外部 PaddleOCR API 完成 OCR，再由本 Skill 自动生成双层 PDF。

> 若需接入 MinerU API，请另见：`references/mineru-api-guide.md`
> 当 Paddle 与 MinerU 同时配置时，可在 `config/.env` 中通过 `OCR_API_ORDER` 指定优先级（如 `paddle,mineru`）。

## 1. 推荐模型与使用建议

- **推荐首选（双层 PDF）**：`PP-OCRv5`（默认）— 行级 OCR 坐标，双层 PDF 叠层定位最精确
- **推荐首选（MD 输出）**：`PaddleOCR-VL-1.5` — 版面分析 + 方向矫正 + 去畸变 + 印章识别 + 异形框定位，94.5% 精度（OmniDocBench v1.5）
- 适用场景：合同、诉讼材料、证据扫描件、拍照件等法律文档
- 说明：外部 API 返回 OCR 结构化结果，本 Skill 基于返回结果自动叠层生成双层 PDF

模型对比：

| 模型 | 特点 | 适用场景 |
| --- | --- | --- |
| `PaddleOCR-VL-1.5` | block 级结构、版面分析、方向/去畸变矫正、图表识别、印章识别、异形框定位 | 拍照件、复杂版面、需 MD 输出的文档 |
| `PP-OCRv5` | 文本行级 OCR、速度更快、支持手写体/竖排文本 | 平扫件、纯文字文档、双层 PDF 首选 |
| `PP-StructureV3` | 复杂版面/表格/图文混排 | 表格密集型文档 |

> 当前 PaddleX 版本 3.4.0，PaddlePaddle 版本 3.2.1

## 2. 官方文档入口

- PaddleOCR-VL-1.5：https://ai.baidu.com/ai-doc/AISTUDIO/Cmkz2m0ma
- PP-OCRv5：https://ai.baidu.com/ai-doc/AISTUDIO/Kmfl2ycs0
- PP-StructureV3：https://ai.baidu.com/ai-doc/AISTUDIO/Fmfz6oh2e
- PaddleOCR-VL（旧版）：https://ai.baidu.com/ai-doc/AISTUDIO/2mh4okm66

## 3. API_URL 与 TOKEN 获取方式

1. 访问 https://aistudio.baidu.com/paddleocr/task
2. 选择或创建对应 API 服务
3. 打开该服务的"API 调用示例"
4. 复制示例中的 `API_URL` 与 `TOKEN`

## 4. 在本 Skill 中配置

### 4.1 推荐做法（使用 config/.env）

```bash
cp config/.env.example config/.env
```

在 `config/.env` 中填写：

```bash
PADDLE_OCR_API_ENDPOINT="https://your-aistudio-app.com/ocr"
PADDLE_OCR_API_KEY="your_access_token"
```

兼容别名（脚本会自动映射）：

```bash
API_URL="https://your-aistudio-app.com/ocr"      # → PADDLE_OCR_API_ENDPOINT
TOKEN="your_access_token"                          # → PADDLE_OCR_API_KEY
```

### 4.2 运行命令

```bash
# 零参数自动流程（默认使用 PP-OCRv5，适用双层 PDF）
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf

# 显式指定后端和模型
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf --backend paddle_api --paddle-model PP-OCRv5

# 使用 VL-1.5 获得 MD 输出（版面分析 + 表格/公式识别）
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf --backend paddle_api --paddle-model PaddleOCR-VL-1.5
```

## 5. API 协议说明

### 5.1 鉴权

```http
Authorization: token {TOKEN}
Content-Type: application/json
```

### 5.2 通用请求参数

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | string | 是 | 文件的 Base64 编码（或服务器可访问的 URL）。默认超过 100 页的 PDF 仅处理前 100 页，可通过产线配置 `Serving.extra.max_num_input_imgs: null` 解除限制 |
| `fileType` | integer | 否 | `0` = PDF 文件，`1` = 图像文件。若缺失则根据 URL 推断 |

### 5.3 PP-OCRv5 可选参数

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `useDocOrientationClassify` | boolean | false | 自动检测并矫正 0°/90°/180°/270° 方向 |
| `useDocUnwarping` | boolean | false | 自动去畸变矫正（透视/弯曲） |
| `useTextlineOrientation` | boolean | false | 自动识别和矫正 0°/180° 文本行方向 |
| `textDetLimitSideLen` | integer | 64 | 文本检测图像最大边长限制（像素） |
| `textDetLimitType` | string | min | 边长限制类型：`min`（不小于此值）/ `max`（不大于此值） |
| `textDetThresh` | number | 0.3 | 文本检测概率阈值（0-1），越低检测越敏感 |
| `textDetBoxThresh` | number | 0.6 | 文本检测框得分阈值（0-1），越高框质量要求越严 |
| `textDetUnclipRatio` | number | 1.5 | 文本检测框扩张系数，越大文本框越宽松 |
| `textRecScoreThresh` | number | 0.0 | 文本识别置信度阈值（0-1），低于此值的识别结果被丢弃 |
| `visualize` | boolean | null | 是否返回可视化结果图。`true`=返回，`false`=不返回，`null`=遵循产线配置。开启后增加响应时间 |

> 本 Skill 通过异步任务接口调用，以上参数通过 `optionalPayload` 传入。

#### PP-OCRv5 响应结构（异步任务 JSONL）

本 Skill 使用异步任务模式（`/api/v2/ocr/jobs`），每行 JSONL 对应一个子批次结果：

```json
{
  "result": {
    "ocrResults": [
      {
        "prunedResult": {
          "model_settings": {},
          "doc_preprocessor_res": { "angle": 0, "model_settings": {} },
          "dt_polys": [],
          "rec_texts": ["识别文字..."],
          "rec_scores": [0.99],
          "rec_polys": [],
          "rec_boxes": [],
          "textline_orientation_angles": [0]
        },
        "ocrImage": "https://...（OCR 处理后图像 URL）",
        "docPreprocessingImage": "https://...（方向/扭曲矫正后图像 URL）",
        "inputImage": "https://...（原始输入图像 URL）"
      }
    ],
    "preprocessedImages": ["https://...（每页矫正后图像 URL）"],
    "dataInfo": {
      "numPages": 4,
      "pages": [{"width": 1190, "height": 1682}]
    }
  }
}
```

关键字段说明：

| 字段 | 说明 |
| --- | --- |
| `prunedResult.rec_texts` | 识别文本数组 |
| `prunedResult.rec_scores` | 对应置信度数组 |
| `prunedResult.rec_polys` / `dt_polys` | 文本框四点坐标 |
| `prunedResult.doc_preprocessor_res.angle` | 方向检测角度（0/90/180/270），非零表示页面被旋转矫正 |
| `ocrImage` | OCR 处理后的可视化图像 URL |
| `docPreprocessingImage` | 方向/扭曲矫正后的图像 URL |
| `inputImage` | 原始输入图像 URL |
| `preprocessedImages` | 每页矫正后图像 URL 列表（若启用了方向/扭曲矫正） |
| `dataInfo.pages[i]` | 每页原始尺寸（width, height） |

### 5.4 PaddleOCR-VL-1.5 可选参数

#### 图像预处理

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `useDocOrientationClassify` | boolean | false | 自动检测并矫正 0°/90°/180°/270° 方向 |
| `useDocUnwarping` | boolean | false | 自动矫正扭曲图片（褶皱、倾斜等） |
| `minPixels` | number | null | 最小图像尺寸（像素），输入图片太小、文字看不清时适当调高 |
| `maxPixels` | number | null | 最大图像尺寸（像素），输入图片过大、处理变慢时适当调低 |

#### 版面检测

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `useLayoutDetection` | boolean | false | 版面区域检测排序模块，自动检测文档各区域并排序 |
| `layoutThreshold` | number | 0.5 | 版面模型得分阈值（0-1），越高过滤越严格 |
| `layoutNms` | boolean | false | 是否使用 NMS 后处理，移除重复/高度重叠的区域框 |
| `layoutUnclipRatio` | number | 1.0 | 版面检测框扩张系数（>0），越大文本框越宽松 |
| `layoutMergeBboxesMode` | string | large | 重叠框过滤方式：`large`（保留最大外框，删除内部框）/ `small`（保留内部小框，删除外部框）/ `union`（内外框都保留） |
| `layoutShapeMode` | string | auto | 检测框几何形状：`rect`（矩形）/ `quad`（四边形）/ `poly`（多边形）/ `auto`（自动） |

#### 内容识别

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `useChartRecognition` | boolean | false | 图表解析模块，自动将柱状图、饼图等转换为表格 |
| `promptLabel` | string | ocr | VL prompt 类型，仅 `useLayoutDetection=false` 时生效。可选：`ocr` / `formula` / `table` / `chart` |
| `repetitionPenalty` | number | null | 重复抑制强度。出现重复文字/表格内容时适当调高 |
| `temperature` | number | null | 识别稳定性。结果不稳定或出现幻觉时调低；漏识别时可略微调高 |
| `topP` | number | null | 结果可信范围。结果发散、不够可信时适当调低 |

#### 多页处理

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `restructurePages` | boolean | false | 多页重构：跨页表格合并 + 段落标题识别 |
| `mergeTables` | boolean | true | 跨页表格合并，仅 `useLayoutDetection=false` 时生效 |
| `relevelTitles` | boolean | true | 段落标题级别识别，仅 `useLayoutDetection=false` 时生效 |

#### 输出控制

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `prettifyMarkdown` | boolean | false | 输出美化后的 Markdown 文本 |
| `showFormulaNumber` | boolean | false | Markdown 文本中是否包含公式编号 |
| `visualize` | boolean | null | 是否返回可视化结果图及中间图像。`true`=返回，`false`=不返回，`null`=遵循产线配置。开启后增加响应时间 |

> 本 Skill 通过异步任务接口调用，以上参数通过 `optionalPayload` 传入。

#### PaddleOCR-VL-1.5 响应结构（异步任务 JSONL）

本 Skill 使用异步任务模式（`/api/v2/ocr/jobs`），每行 JSONL 对应一个子批次结果：

```json
{
  "result": {
    "layoutParsingResults": [
      {
        "prunedResult": {
          "parsing_res_list": [
            {
              "block_label": "text",
              "block_content": "识别文字...",
              "block_bbox": [x1, y1, x2, y2],
              "block_id": 0,
              "block_order": 0,
              "group_id": 0
            }
          ],
          "width": 1190,
          "height": 1682
        },
        "markdown": {
          "text": "# 标题\n\n正文内容...",
          "images": { "img_0.jpg": "base64..." }
        },
        "outputImages": { "output_0.jpg": "base64..." },
        "inputImage": "base64..."
      }
    ],
    "preprocessedImages": ["https://...（每页矫正后图像 URL）"],
    "dataInfo": {
      "numPages": 4,
      "pages": [{"width": 1190, "height": 1682}]
    }
  }
}
```

关键字段说明：

| 字段 | 说明 |
| --- | --- |
| `prunedResult.parsing_res_list` | 版面解析块列表 |
| `parsing_res_list[].block_label` | 块类型：`text`/`title`/`doc_title`/`header`/`footer`/`list`/`reference`/`abstract`/`catalog`/`code`/`table`/`table_caption`/`number`/`content`/`paragraph_title`/`section_title`/`seal` |
| `parsing_res_list[].block_content` | 块内文本内容（含 Markdown/LaTeX 标记） |
| `parsing_res_list[].block_bbox` | 块边界框（四点坐标） |
| `markdown.text` | 完整 Markdown 格式文本 |
| `markdown.images` | Markdown 中引用的图片（相对路径 → Base64 数据） |
| `outputImages` | 可视化结果图（JPEG 格式，Base64 编码） |
| `inputImage` | 原始输入图像（JPEG 格式，Base64 编码） |
| `preprocessedImages` | 每页矫正后图像 URL 列表（若启用了方向/扭曲矫正） |

### 5.5 本 Skill 的异步任务模式

本 Skill 通过 PaddleOCR 云服务的异步任务接口调用：

- 任务提交：`POST multipart/form-data` 到 `/api/v2/ocr/jobs`
- 结果轮询：`GET /api/v2/ocr/jobs/{jobId}`（pending → running → done/failed）
- 结果格式：JSONL，每行包含一页或一批 OCR 结果（文字 + 坐标 + 矫正图片）
- 本地叠层：从 JSONL 解析坐标后本地生成双层 PDF

### 5.6 `/restructure-pages` 端点（可选）

用于对多页 PDF 解析结果进行重构，支持跨页表格合并和段落标题级别识别。

端点：`POST /restructure-pages`

请求参数：

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `mergeTables` | boolean | true | 跨页表格合并，仅 `useLayoutDetection=false` 时生效 |
| `relevelTitles` | boolean | true | 段落标题级别识别，仅 `useLayoutDetection=false` 时生效 |
| `concatenatePages` | boolean | false | 多页 PDF 解析结果重构 |
| `prettifyMarkdown` | boolean | false | 美化 Markdown 输出 |
| `showFormulaNumber` | boolean | false | 包含公式编号 |
| `pages` | array | 必填 | 每页元素包含 `prunedResult`（来自 `/layout-parsing` 返回）和 `markdownImages`（来自 `/layout-parsing` 返回的 `markdown.images`） |

响应格式：

```json
{
  "errorCode": 0,
  "result": {
    "layoutParsingResults": [
      {
        "prunedResult": { "parsing_res_list": [...] }
      }
    ]
  }
}
```

### 5.7 错误码

| errorCode | HTTP 状态码 | errorMsg | 说明 |
| --- | --- | --- | --- |
| 0 | 200 | "Success" | 成功 |
| 非零 | 等于 HTTP 状态码 | 具体错误描述 | 错误（鉴权失败、参数错误、服务异常等） |

响应示例：

```json
// 成功
{ "logId": "uuid", "errorCode": 0, "errorMsg": "Success", "result": {...} }

// 失败
{ "logId": "uuid", "errorCode": 401, "errorMsg": "Token 无效或已过期" }
```

### 5.8 限制与注意事项

1. **PDF 页数限制**：默认超过 100 页的 PDF 仅处理前 100 页。可在产线配置文件添加 `Serving.extra.max_num_input_imgs: null` 解除限制。本 Skill 的异步任务模式实测 300 页+ 无限制。
2. **可视化开销**：启用 `visualize=true` 会显著增加结果返回时间
3. **`promptLabel` 生效条件**：仅当 `useLayoutDetection=false` 时生效
4. **`mergeTables` 和 `relevelTitles` 生效条件**：仅当 `useLayoutDetection=false` 时生效
5. **跨页表格合并/标题识别**：需设置 `restructurePages=true`，通过 `infer` 参数或 `/restructure-pages` 端点实现
6. **Base64 编码**：大文件 Base64 编码后体积增加约 33%，建议图片文件通过 URL 方式提交

## 6. OCR dump/resume 工作流（Agent 纠错）

支持 OCR → Agent 审查 → 修正 → 生成 PDF 的完整流程：

```bash
# Step 1: OCR 识别，结果存入 JSON（不生成 PDF）
python3 scripts/pdf-ocr.py -i input.pdf --ocr-dump /tmp/ocr_dump.json

# Step 2: Agent 审查可读文本 /tmp/ocr_dump_readable.txt，发现 OCR 错误
#         直接编辑 dump JSON 或生成 corrections 文件 [{from, to}, ...]

# Step 3: 加载修正后的 dump，生成双层 PDF
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf --ocr-resume /tmp/ocr_dump.json --corrections-file /tmp/corrections.json
```

## 7. 安全注意事项

- `TOKEN` 属于敏感凭证，不要提交到 Git 仓库
- `config/.env` 已被仓库忽略；仅提交 `config/.env.example`
- 若凭证泄露，请立即在服务端吊销并重新生成
