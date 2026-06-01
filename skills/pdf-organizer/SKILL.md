---
name: pdf-organizer
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "0.5.0"
description: 当需要整理法律 PDF 时使用：检测文字层，生成页面索引、整理草稿和下游交接文件，按内容拆分、合并或直接重命名 OCR 后双层扫描件并规范命名；可做旋转与倾斜校正，不做 OCR 或压缩。
license: MIT
---

# PDF Organizer

## 定位

本技能处理“PDF 文件和法律文书逻辑不一致”的问题。它关注的不是普通文件拼接，而是按文书内容把 PDF 整理成律师实际会使用的文件。

核心职责：

1. 按内容把整份扫描/OCR PDF 拆成多份独立文书。
2. 按内容把被拆散的同一份文书合并回一个 PDF。
3. 对不需要拆分或合并的 PDF，直接根据内容识别结果规范命名。
4. 根据标题、主体、相对方、案由、日期等要素生成规范文件名。
5. 生成页面级检查索引和 manifest 草稿，供 AI/人工复核。
6. 生成下游 `handoff.json`，供案件材料整理、合同审查、诉讼分析等 Skill 协同使用。
7. 在整理前后做轻量页面方向处理，例如 90/180/270 度旋转；倾斜校正作为可选预处理能力。
8. 将 PDF 每页标准化为 A4 尺寸：横向页面自动适配 A4 横版（842×595 pt），竖向页面自动适配 A4 竖版（595×842 pt），等比缩放居中。

本技能不做 OCR、不压缩 PDF，也不替代案件材料整体归类。若 PDF 还没有可检索文字层，先使用 OCR 工具；若需要复杂裁边、压缩、批量 OCR 或高质量图像预处理，优先使用 PDF Processor。

## 与其他技能配合

- OCR 前处理、双层 PDF、压缩、复杂裁边等工作交给 PDF Processor。
- 复杂版面识别、PDF 转 Markdown 或需要结构化 OCR 结果时，先使用 OCR 解析工具。
- 本技能输出的整理后 PDF 可以继续交给材料整理、案件分析或文书生成技能。

## 依赖

### 系统依赖

| 依赖 | 安装方式 |
|------|----------|
| `python3` | macOS 通常已内置 |
| `ocrmypdf` | 可选，仅 `deskew` 倾斜校正需要；macOS: `brew install ocrmypdf` |

### Python 包

| 包名 | 用途 | 安装命令 |
|------|------|----------|
| `pypdf` | 拆分、合并、复制、页面旋转 | `python3 -m pip install -r scripts/requirements.txt` |

只做清单规划时不需要安装依赖；执行拆分、合并或旋转时需要 `pypdf`。倾斜校正依赖 `ocrmypdf` 命令行工具，未安装时应提示用户改用 PDF Processor 或先安装。

## 输入/输出

### 输入

- 整份 OCR 后 PDF：例如一份 16 页的扫描合并件。
- 已拆散的多个 PDF：例如同一份起诉状被拆成 `第 1-2 页.pdf`、`第 3-4 页.pdf`。
- 独立 PDF 文件：整份 PDF 已经是一份完整文书，不需要拆分或合并，只需要根据内容规范命名。
- 可选 OCR Markdown 或文字片段：用于辅助判断标题、边界和合并关系。
- 可选命名偏好：是否保留日期、是否写案由、是否使用简称。

### 输出

- 整理后的 PDF 文件。交付目录默认只放最终 PDF。
- 过程文件统一归档到 `archive/YYYYMMDD_HHMMSS_{来源名}/`。

archive 默认包含：

- `organize_manifest.input.json`：本次输入清单副本。
- `organize_manifest.resolved.json`：实际输出路径、页码、状态和命名依据。
- `organize_report.md`：给人工复核的摘要报告。
- `handoff.json`：面向下游 Skill 的交接文件。
- `run_meta.json`：运行元数据。

## 工作流程

### 1. 清点与预处理判断

1. 确认输入是整份 PDF、多个碎片 PDF、独立 PDF 文件（只需重命名），还是以上几类的混合。
2. 读取页数，建立页码与文件的对应关系。
3. 先做文字层检测，确认 PDF 是 OCR 后双层 PDF；没有可检索文字层时，停止内容拆分/合并判断，提示用户先走 PDF Processor 生成双层 PDF。
4. 运行页面检查，提取每页文字量、疑似标题、页码、日期、主体候选和边界信号。
5. 可先生成 `organize_manifest.json` 草稿，再由 AI 根据页面证据和命名规则复核。
6. 判断是否需要先做页面方向处理：
   - 页面整体横竖方向错误：使用 90/180/270 度旋转。
   - 轻微倾斜影响阅读或 OCR：可用 `deskew`，但复杂图像问题优先交给 PDF Processor。
7. 不修改原始文件，最终 PDF 写入输出目录，manifest、报告、交接文件和运行记录写入 Skill archive。

### 2. 判断拆分还是合并

**拆分场景**：

- 一份 PDF 中包含多份文书。
- 页面顶部出现新的文书标题。
- 页码从“第1页共N页”或 `1/N` 重新开始。
- 出现新的落款、函号、案号、收件法院、合同编号或签署页。
- 版式从正文续页切换为新的表单、封面或附件。

**合并场景**：

- 多个 PDF 是同一份文书的连续页。
- 标题相同，页码连续，例如第1页共2页、第2页共2页。
- 后一文件明显是前一文件的续页、签署页、付款页或附件页。
- 文件名只是机械页码，不能代表独立文书。

**重命名场景**：

- 整份 PDF 就是一份完整文书，不需要拆分也不需要合并。
- 当前文件名只有页码、日期或扫描仪默认名，不能反映文书内容。
- 在 manifest 中使用 `input_file` 指定来源，用 `suggested_filename` 给出规范文件名。
- 如果同时需要旋转或倾斜校正，可以在同一条 segment 中加上 `rotate` 或 `deskew`。

如果边界不确定，不要强行合并或拆开；在 manifest 中标记 `needs_review: true`，并在文件名中保留页码提示。

常见法律文书的细分识别规则见 `references/recognition-rules.md`。

### 3. 命名规则

默认文件名格式：

```text
文书名称 关键主体 补充区分.pdf
```

规则：

1. 默认不添加序号；只有用户明确要求排序编号，或同名文件无法通过内容区分时，才添加序号。
2. 文书名称优先使用首页标题，不使用“第 1-2 页”这类临时名。
3. 关键主体优先写客户/委托人、相对方和案由/法律关系。
4. 我方律所、承办律师、常见出具机构通常不写入文件名，因为这些信息对用户来说已知且重复。
5. 日期能稳定识别时用 `YYYYMMDD`；日期缺失或 OCR 可疑时省略。
6. 文件名内部默认用空格分隔，不使用下划线。
7. 同名文件由脚本自动追加 ` 1`、` 2`，不覆盖已有文件。
8. 低置信度文件使用 `待确认 页码.pdf` 或 `疑似文书名称 页码.pdf`。

示例：

```text
专项法律服务合同 北京青柏教育咨询有限公司.pdf
委托代理合同 张家宁与杭州叠影科技有限公司 著作权权属侵权纠纷.pdf
授权委托书 张家宁.pdf
律师事务所函 张家宁诉杭州叠影科技有限公司.pdf
民事起诉状 张家宁诉杭州叠影科技有限公司 普通版.pdf
民事起诉状 张家宁诉杭州叠影科技有限公司 要素式.pdf
```

## Manifest

执行前先生成 `organize_manifest.json`。字段说明见 `references/organize-manifest-schema.md`。

### 拆分示例

```json
{
  "source_pdf": "/path/to/ocr.pdf",
  "output_dir": "/path/to/output",
  "segments": [
    {
      "id": "D001",
      "pages": "1-2",
      "suggested_filename": "专项法律服务合同 北京青柏教育咨询有限公司.pdf",
      "title": "专项法律服务合同",
      "confidence": "high",
      "needs_review": false,
      "evidence": "第 1 页标题为专项法律服务合同，页脚显示第1页共2页。"
    }
  ]
}
```

### 合并示例

```json
{
  "output_dir": "/path/to/output",
  "segments": [
    {
      "id": "D001",
      "source_items": [
        {"file": "/path/to/起诉状 第1-2页.pdf"},
        {"file": "/path/to/起诉状 第3-4页.pdf"}
      ],
      "suggested_filename": "民事起诉状 张家宁诉杭州叠影科技有限公司 普通版.pdf",
      "title": "民事起诉状",
      "confidence": "high",
      "needs_review": false,
      "evidence": "两份 PDF 标题一致且页码连续，第二份为同一份起诉状续页。"
    }
  ]
}
```

### 方向处理示例

```json
{
  "output_dir": "/path/to/output",
  "segments": [
    {
      "id": "D001",
      "input_file": "/path/to/横向扫描.pdf",
      "rotate": 90,
      "suggested_filename": "授权委托书 张家宁.pdf",
      "confidence": "medium",
      "needs_review": true
    }
  ]
}
```

### 重命名示例

不需要拆分或合并，只根据内容识别结果规范命名：

```json
{
  "output_dir": "/path/to/output",
  "segments": [
    {
      "id": "D001",
      "input_file": "/path/to/scan_20260531_001.pdf",
      "suggested_filename": "民事起诉状 张家宁诉杭州叠影科技有限公司 普通版.pdf",
      "title": "民事起诉状",
      "document_type": "民事起诉状",
      "confidence": "high",
      "needs_review": false,
      "evidence": "首页标题为民事起诉状，正文提及张家宁与杭州叠影科技有限公司著作权权属侵权纠纷。"
    },
    {
      "id": "D002",
      "input_file": "/path/to/scan_20260531_002.pdf",
      "suggested_filename": "授权委托书 张家宁.pdf",
      "title": "授权委托书",
      "document_type": "授权委托书",
      "confidence": "high",
      "needs_review": false,
      "evidence": "首页标题为授权委托书，委托人张家宁。"
    }
  ]
}
```

## 执行脚本

首次执行拆分、合并或旋转时，先安装依赖：

```bash
python3 -m pip install -r scripts/requirements.txt
```

预览计划：

```bash
python3 scripts/pdf_organizer.py --manifest organize_manifest.json --dry-run
```

只检测 PDF 是否有可检索文字层：

```bash
python3 scripts/pdf_organizer.py --check-text-layer "/path/to/file.pdf"
```

生成页面检查索引：

```bash
python3 scripts/pdf_organizer.py \
  --inspect "/path/to/ocr.pdf" \
  --inspect-output "/path/to/page_inspection.json"
```

生成 manifest 草稿：

```bash
python3 scripts/pdf_organizer.py \
  --suggest-manifest "/path/to/ocr.pdf" \
  --output-dir "/path/to/organized" \
  --manifest-output "/path/to/organize_manifest.json"
```

### A4 标准化

将一个或多个 PDF 的每页标准化为 A4 尺寸，横向页面→A4 横版，竖向页面→A4 竖版：

```bash
# 原地覆盖
python3 scripts/pdf_organizer.py --normalize-a4 file1.pdf file2.pdf

# 输出到指定目录
python3 scripts/pdf_organizer.py --normalize-a4 file1.pdf file2.pdf --normalize-output-dir /path/to/output
```

草稿只作为复核起点。脚本会保守使用 `待确认`，不要跳过人工/AI 复核直接执行。

确认后执行：

```bash
python3 scripts/pdf_organizer.py --manifest organize_manifest.json
```

常用覆盖参数：

```bash
python3 scripts/pdf_organizer.py \
  --manifest organize_manifest.json \
  --source "/path/to/ocr.pdf" \
  --output-dir "/path/to/organized" \
  --archive-root "/path/to/archive-root"
```

脚本默认以 `strict` 模式检测来源 PDF 的文字层；检测不到可检索文字层时会停止执行。只有在纯旋转、复制等不依赖内容判断的场景，才可在 manifest 中设置 `"text_check": "off"` 或命令行使用 `--text-check off`。

脚本只向输出目录写入最终 PDF，不修改源 PDF；manifest、resolved JSON、报告、`handoff.json` 和元数据写入 archive。

## 下游交接

每次正式执行都会在 archive 中生成 `handoff.json`。下游 Skill 优先读取该文件，而不是重新猜测文件名和文书类型。

`suggested_downstream` 按文书类别给出路由标签，不绑定具体 Skill 名称：

- 合同、协议 → `合同审查`。
- 起诉状、判决书、裁定书、答辩状、申请书、证据目录、庭审笔录 → `诉讼分析`。
- 授权委托书、律师事务所函和其他辅助材料 → `材料整理`。
- 低置信度或需复核 → 回到本 Skill 复核。
- 未命中以上类别的 → `材料整理`。

具体由哪个 Skill 消费，由下游根据当前可用的 Skill 和案件上下文自行决定。

## 交付检查

完成后检查：

1. 输出 PDF 数量与 manifest segment 数一致。
2. 拆分文件页数与 `pages` 对应；合并文件页数等于来源 PDF 页数之和。
3. archive 中的 `organize_report.md` 没有 `low` 且 `needs_review: true` 的未处理项；如果有，明确提示用户人工复核。
4. 原始 PDF 和原始碎片 PDF 未被覆盖或移动。
5. 命名依据能回溯到 OCR 文本或页面内容，没有臆测日期、案号或主体。
