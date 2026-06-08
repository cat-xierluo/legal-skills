# legal-ocr 整合路线图

> Last updated: 2026-05-12
> 状态：规划中，未开始实施

## 背景

当前 `paddle-ocr`（Python，百度 PaddleOCR API）和 `mineru-ocr`（JXA，MinerU API）功能高度重叠——都将 PDF/图片转为 Markdown 并归档。合并为统一 Skill 的收益：

- 消除用户在两个 OCR 工具间选择的困惑
- 统一归档格式和配置体验
- 根据文件类型/大小自动路由到最优后端
- 加入法律文档后处理（词典纠错、标题结构、标点规范化）

## 新 Skill 命名

**`legal-ocr`** — 传达三个信息：(a) OCR 工具 (b) 法律文档优化 (c) 生态内主 OCR Skill。

---

## 目录结构

```
skills/legal-ocr/
├── SKILL.md
├── CHANGELOG.md
├── DECISIONS.md
├── LICENSE.txt
├── config/
│   ├── .env.example                # 统一配置
│   └── legal_dictionaries/
│       ├── general_legal_terms.md      # 预置：法律 OCR 常见纠错
│       ├── court_document_patterns.md  # 预置：法院文书结构识别
│       └── seal_detection_rules.md     # 预置：印章标注规则
├── scripts/
│   ├── convert.py                  # 统一入口 + 路由
│   ├── backends/
│   │   ├── base.py                 # 抽象接口 + OCRResult
│   │   ├── paddle_ocr.py           # 从 paddle-ocr/scripts/lib.py 提取
│   │   └── mineru_ocr.py           # 从 convert.js (JXA) 重写为 Python
│   ├── router.py                   # 自动路由决策
│   ├── postprocess/
│   │   ├── legal_postprocess.py    # 后处理管线
│   │   ├── punctuation_fix.py      # 标点规范化
│   │   ├── heading_structure.py    # 法律标题结构检测
│   │   └── blank_line_cleanup.py   # 空行整理
│   ├── optimize_file.py            # 沿用 paddle-ocr
│   ├── split_pdf.py                # 沿用 paddle-ocr
│   ├── smoke_test.py               # 统一健康检查
│   └── convert.js                  # JXA 兼容层
├── references/
│   └── output_schema.md
└── archive/
    └── .gitkeep
```

---

## 统一配置

所有现有变量名**完全保留**，用户只需复制值到新 `.env`：

```ini
# ===== 后端选择 =====
LEGAL_OCR_BACKEND=auto          # auto | paddle | mineru

# ===== PaddleOCR 后端（变量名不变） =====
PADDLEOCR_DOC_PARSING_API_URL=
PADDLEOCR_ACCESS_TOKEN=
PADDLEOCR_DOC_ORIENTATION=false
PADDLEOCR_DOC_UNWARP=false
PADDLEOCR_CHART_RECOG=false
PADDLEOCR_DOC_PARSING_TIMEOUT=600
PADDLEOCR_BATCH_PAGES=40
PADDLEOCR_MAX_BASE64_MB=20

# ===== MinerU 后端（变量名不变） =====
MINERU_API_BASE=https://mineru.net/api/v4
MINERU_API_TOKEN=
MINERU_ENABLE_OCR=true
MINERU_ENABLE_TABLE=true
MINERU_ENABLE_FORMULA=false
MINERU_LANGUAGE_CODE=ch
MINERU_MODEL_VERSION=pipeline
MINERU_PAGE_RANGES=
MINERU_POLL_MAX=20
MINERU_POLL_SLEEP=10

# ===== 统一设置 =====
LEGAL_OCR_LOG_LEVEL=medium
LEGAL_OCR_POST_PROCESS=true     # 开启法律后处理管线
LEGAL_OCR_LEGAL_DICT=true       # 启用法律词典纠错
```

---

## 自动路由规则

按顺序评估，命中即停止：

| # | 条件 | 路由到 | 原因 |
|---|------|--------|------|
| R1 | DOC/DOCX/PPT/PPTX 文件 | MinerU | PaddleOCR 不支持 |
| R2 | 网页 URL（非文档链接） | MinerU (需 token) | 仅 MinerU 支持网页提取 |
| R3 | 远程文档 URL | MinerU 优先 | MinerU 处理远程 URL 更顺畅 |
| R4 | PDF > 600 页 | PaddleOCR | PaddleOCR 无限页数自动分批 |
| R5 | 启用印章/图表检测 | PaddleOCR | 专用印章检测能力 |
| R6 | 小文件 (<10MB, <20页)，无 MinerU token | MinerU Light | 零配置即用 |
| R7 | 本地 PDF/图片（默认） | PaddleOCR | 法律场景优化更好 |
| R8 | 首选后端失败 | 回退到另一个 | 双后端互为兜底 |

---

## 法律后处理管线

OCR 后自动执行（可通过 `--no-post-process` 关闭）：

### Stage 1：标点规范化
- 英文标点 → 中文标点（`, . ; : ( ) ? !`）
- 保护 URL 和代码块内的标点不被替换
- 参考：`legal-text-format/scripts/format_step2_v2.py` 的占位符保护机制

### Stage 2：法律标题结构检测
自动识别并标记：
- "第X条" → 加粗
- "第X章" / "第X节" → `##` / `###` 标题
- 案号："(20XX)X民初X号"
- 法院文书段落："原告诉称"、"被告辩称"、"本院认为"、"判决如下"
- 参考：`legal-text-format/scripts/format_legal_cases.py`

### Stage 3：空行整理
- 折叠 3+ 连续空行为 2
- 确保段落间单个空行
- 去除行尾空白

### Stage 4：词典纠错
三层词典体系（参考 `post-ocr-formatter` 的四类型设计）：

| 类型 | 行为 |
|------|------|
| 强制替换 | 命中即替换，记录日志。仅高置信度。如 "但保"→"担保" |
| 术语白名单 | 不做批量替换，用于确认近似写法的正确形式 |
| 标题词表 | 不做替换，用于提升标题检测置信度 |
| 禁止改写 | 命中则保留原文，标记人工复核。如 "权力/权利" |

词典文件：
- `config/legal_dictionaries/general_legal_terms.md` — 预置通用纠错
- `config/legal_dictionaries/court_document_patterns.md` — 预置法院文书正则
- `config/legal_dictionaries/user_dictionary.md` — 用户自定义（首次运行自动创建）

### Stage 5：印章/图表标注
- PaddleOCR 后端检测到的印章区域自动添加标注
- 格式：`![印章](image_path)`
- 关联图片与 Markdown 输出路径

---

## CLI 统一入口

```bash
legal-ocr <input_path_or_url>
  --output <path>         # 输出 Markdown 路径
  --pages <spec>          # 页码范围（如 "1-20"）
  --backend <name>        # paddle | mineru | auto（默认）
  --no-post-process       # 跳过法律后处理
  --no-archive            # 跳过归档
  --archive-name <name>   # 自定义归档目录名
  --seal-detection        # 启用印章检测（PaddleOCR）
  --model <version>       # MinerU 模型：pipeline | vlm
```

---

## 统一归档格式

```
archive/
└── 20260512_153000_某案卷宗/
    ├── input/
    │   └── 某案卷宗.pdf
    ├── output/
    │   ├── result.md            # 最终 Markdown（后处理后）
    │   ├── result_raw.md        # OCR 原始输出（后处理前）
    │   ├── result.json          # 结构化结果元数据
    │   └── images/
    ├── batches/                 # PaddleOCR 分批 JSON（如适用）
    ├── backend_result/          # 后端特定原始输出
    │   └── [content_list.json, layout.json 等]
    ├── postprocess_log.json     # 纠正记录、词典命中
    └── metadata.json            # 含 backend、post_processing 统计
```

---

## 两个后端的能力对比

| 能力 | PaddleOCR | MinerU |
|------|-----------|--------|
| 本地 PDF | ✅ 自动分批 | ✅ 最大 600 页 |
| 本地图片 | ✅ | ✅ |
| DOC/DOCX/PPT/PPTX | ❌ | ✅ |
| 远程文档 URL | ⚠️ 有限制 | ✅ |
| 网页提取 | ❌ | ✅ (需 token) |
| 表格识别 | ✅ | ✅ (需 token) |
| 公式识别 | ✅ | ✅ (需 token) |
| 印章检测 | ✅ 专用能力 | ❌ |
| 图表识别 | ✅ 可开关 | ✅ |
| 零配置使用 | ❌ 需 token | ✅ Light 模式 |
| 图片预压缩 | ✅ | ❌ |
| 大文件分批 | ✅ 自动 | ❌ 单次上限 |
| 结构化内容提取 | ❌ | ✅ content_list.json |

---

## 实施阶段

### Phase 1：基础框架 + PaddleOCR 后端

**目标**：创建 legal-ocr 骨架，PaddleOCR 后端可用。

- [ ] 创建 `legal-ocr/` 目录结构
- [ ] 实现 `backends/base.py`（抽象接口 + OCRResult 数据类）
- [ ] 实现 `backends/paddle_ocr.py`（从 `paddle-ocr/scripts/lib.py` + `convert.py` 提取适配）
- [ ] 沿用 `optimize_file.py`、`split_pdf.py`
- [ ] 实现统一配置加载
- [ ] 实现统一 `convert.py` 入口（仅 PaddleOCR 后端）
- [ ] 实现 `smoke_test.py`
- [ ] 编写 `SKILL.md`

**关键源文件：**
- `paddle-ocr/scripts/lib.py`（334 行，核心 HTTP 逻辑）
- `paddle-ocr/scripts/convert.py`（批处理、归档、图片保存）

### Phase 2：MinerU Python 后端

**目标**：MinerU 后端从 JXA 迁移到 Python，功能对齐。

- [ ] 实现 `backends/mineru_ocr.py`（从 convert.js 1107 行 JXA 重写为 Python + httpx）
- [ ] 四条转换路径：local/token、local/light、remote/token、remote/light
- [ ] Token 解析链：`.env` → 环境变量 → `~/.mineru/config.yaml`
- [ ] Light 模式限制检查（10MB、20 页）
- [ ] URL 类型检测（文档 vs 网页）
- [ ] 远程图片下载
- [ ] 更新 smoke_test

**关键源文件：**
- `mineru-ocr/scripts/convert.js`（1107 行，需完整重写）

### Phase 3：路由 + 后处理

**目标**：自动路由和法律后处理管线可用。

- [ ] 实现 `router.py`（8 条路由规则）
- [ ] 实现后处理管线（标点/标题/空行/词典/印章）
- [ ] 创建预置法律词典
- [ ] 实现 `convert.js` JXA 兼容层

**参考文件：**
- `private-skills/post-ocr-formatter/assets/correction-dictionary.template.md`
- `legal-text-format/scripts/format_legal_cases.py`

### Phase 4：文档 + 迁移

**目标**：文档齐全，迁移路径清晰。

- [ ] 编写 `references/output_schema.md`
- [ ] 编写 `DECISIONS.md`
- [ ] 编写 `CHANGELOG.md`（v1.0.0）
- [ ] 端到端测试：两条后端路径、自动路由、后处理、归档
- [ ] 在旧 Skill 中添加废弃提示

---

## 用户迁移路径

1. 安装 `legal-ocr` skill
2. 将 `paddle-ocr/config/.env` 中的 `PADDLEOCR_*` 值复制到 `legal-ocr/config/.env`
3. 将 `mineru-ocr/config/.env` 中的 `MINERU_*` 值复制到 `legal-ocr/config/.env`
4. 设置 `LEGAL_OCR_BACKEND=auto`
5. 旧 Skill 保持功能不变，无破坏性

稳定后（2-4 周）在旧 Skill 中添加废弃提示，最终归档。

---

## 验证方式

1. **PaddleOCR 路径**：用一份法律 PDF 运行 `legal-ocr`，确认输出与原 paddle-ocr 一致
2. **MinerU 路径**：同一 PDF 运行 `--backend mineru`，确认输出与原 mineru-ocr 一致
3. **自动路由**：传入 .docx、网页 URL、>600 页 PDF，确认路由正确
4. **后处理**：对比 raw Markdown 和 processed Markdown，确认标题/标点/词典效果
5. **回退**：模拟一个后端失败，确认自动切换

---

## 关键架构决策

### D-1：Python-first，不是 JXA-first
PaddleOCR 已是 Python。MinerU 的 JXA 逻辑是纯 HTTP+JSON，映射到 Python+httpx 很直接。统一 Python 代码库才能共享工具函数和模块化。

### D-2：后端接口模式，不是适配器模式
每个后端直接实现 OCRBackend 接口，代码扁平可调试。`convert()` 方法各自负责分批、轮询、错误处理。

### D-3：后处理默认开启，可关闭
`LEGAL_OCR_POST_PROCESS=true` 默认开启。需要原始 OCR 输出的用户可关闭。

### D-4：保留所有现有环境变量名
`PADDLEOCR_*` 和 `MINERU_*` 全部保留，消除迁移摩擦。

### D-5：PaddleOCR 为本地 PDF/图片的默认后端
PaddleOCR 有印章检测、大文件分批、图片预压缩等法律文档专用能力，更适合作为默认选择。MinerU 作为 PaddleOCR 不支持格式（DOCX、PPTX、网页）的默认选择。
