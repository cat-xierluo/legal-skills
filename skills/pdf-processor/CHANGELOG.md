# 更新日志

## [2.10.2] - 2026-08-01

### 新增

- 新增 `--dump-and-pdf`：配合 `--ocr-dump` 使用时，保存 dump 后继续生成双层 PDF，不再需要"先 dump 再 resume"两步走。原有 `--ocr-dump` 单独使用仍保持"仅 dump 不出 PDF"语义（向后兼容 v2.5.0 审查工作流）。
- 把 `--actualtext` 接入 `pdf-ocr.py` 主流程并默认开启：文字层生成后自动调用 PP-StructureV3 拿版面，融合自然段并以 `/ActualText` marked-content 写入 PDF，让从 PDF 复制的文字按段落连续。`--no-actualtext` 关闭；`--layout-dump FILE` 复用已有版面 dump 避免二次 API 调用。失败时降级为行级 PDF，不阻塞主流程。

### 改进

- 修复双层 PDF `/ActualText` 完整性校验过严的问题：自然段因物理行不连续（如跳过印章碎片）无法包裹时，不再让整页失败回退，而是把该段降级为行级（文字不丢失，仅该段复制按行断行）。校验仍会对"row_indices 指向不存在行或文字拼接不匹配"这类真正的映射错误抛完整性异常。

### 技术优化

- `_apply_semantic_actual_text` 返回值由 `int` 改为 `(applied, invalid_mapping_count)`，精确区分"行不连续降级"与"映射错误失败"。
- 新增辅助函数 `_actualtext_enabled`、`_entries_already_have_paragraphs`、`_inject_semantic_paragraphs`（paddle_api 后端）；避免对已带 `semantic_paragraphs` 的 dump/resume 重复融合，避免对 VL/Structure 文字模型（本就含版面）二次调用 API。
- 实测阅读器兼容性：Poppler（`pdftotext -raw`、默认）能拿到整段连续文本；PyMuPDF、pypdf、macOS 预览（PDFKit）仍按物理行断行。结论已写入 SKILL.md 表格。
- 基于《民事起诉状》真实 2 页扫描件端到端验证：`--dump-and-pdf` 一次调用同时出 dump + 含 ActualText 的双层 PDF；第 1 页 13/13 段全部写入，第 2 页 3/4 段（"此致"段因跨印章碎片降级）；Poppler 提取的"事实与理由"段为整段连续 0 换行。
- 回归测试由 88 项扩展到 96 项，新增 `_actualtext_enabled` 默认/关闭、VL/Structure 跳过二次调用、`--layout-dump` 复用、失败降级、不连续段不抛异常等用例。

### 范围说明

- 本次外部 API 调用基于用户明确授权的《民事起诉状》文件；OCR 全文、dump 等中间产物只保存临时目录，不写入 Skill 或版本库。
- macOS 预览（PDFKit）不支持 `/ActualText` 是已知局限，跨阅读器稳定的段落文本仍以独立 Markdown 为准。

## [2.10.1] - 2026-08-01

### 修复

- 修复 PP-StructureV3 在连续合同正文中把每个条款拆成多个 `text` 块时，融合器把高覆盖率误当成可靠段界、继续输出物理行空行的问题；版面块现在只是段落候选，正文区域会按行距、右边界、句末标点和条款编号做确定性块内及跨块合并。
- 修复同一视觉行的 OCR 碎片因轻微纵坐标抖动而顺序颠倒或被拆成多个段的问题；同一表格行按横坐标恢复单元格次序，并在自然段 Markdown 中用 ` | ` 分隔。
- 新增 PP-OCRv6 低置信行的 PP-StructureV3 行级兜底：仅在主结果置信度低于 0.80、Structure 不低于 0.90、置信度至少高 0.10 且坐标双向重叠不低于 0.50 时替换；仍不读取 Structure/VL 的块文本。
- 规范紧凑条款编号与中文正文之间的空格，例如把 `5-4甲方` 整理为 `5-4 甲方`。

### 技术优化

- 用 4 个不含个案信息的通用模板单页复测：空白资料交接表、空白证据目录、勾选/填空合同页和连续条款正文页的 Structure 行覆盖率均为 100%，自然段分别由 27/10/14/22 个 OCR 行整理为 15/7/10/8 个结构单元；未触发 PaddleOCR-VL。
- 资料交接表和连续条款页相对原生文字层在忽略空白与表格分隔符后 CER 均为 0%；另外两页的原生文字层存在标题缺失或阅读顺序错误，因此只作为差异参考，不冒充人工真值。
- 把 4 页分别栅格化为无文字层扫描副本后生成双层 PDF：4/4 页可检索、12/12 关键词命中，Poppler `-raw`、PyMuPDF、pypdf 均与实际写入行文字完全一致；OCR 前后页面渲染 SHA-256 逐页相同。
- 对空白交接表和连续条款页重复调用 v6 与 Structure：两轮 `pages` 结果的规范化 SHA-256 分别完全一致，融合 Markdown 与诊断指标也一致；该重复性证据只覆盖这两个固定输入。
- 自然段融合回归测试增至 18 项，覆盖宽行距正文、同视觉行排序、表格行、跨块条款、编号空格及低置信行级兜底。

### 范围说明

- 本轮外部 API 只处理通用空白模板，不上传法院传票、病历等敏感材料；结论覆盖代表性单页版式，不等同于 117 页病历或所有复杂多栏文档的全量稳定性证明。

## [2.10.0] - 2026-08-01

### 新增

- 新增 `scripts/pdf_ocr_paragraphs.py`：把 PP-OCR 行级文字与 PP-Structure/VL 版面块按坐标融合，输出段内无回车、段间单空行的自然段 Markdown；可同时生成不含正文的覆盖率诊断和过滤印章噪声后的 OCR dump。
- Paddle 异步 API 新增 `PP-OCRv6`，并保留 `PP-OCRv5`、`PP-StructureV3`、`PaddleOCR-VL-1.5/1.6` 五模型兼容。
- 新增实验性 `--actualtext`：在 filtered dump 中记录自然段行映射，`--ocr-resume` 以 PDF `/ActualText` 提示复制语义，同时保留原有行级字形坐标；映射不完整时事务式失败。

### 改进

- 双层 PDF 默认文字模型由 `PP-OCRv5` 升级为 `PP-OCRv6`；v5 继续作为显式兼容和对照模型。
- 自然段链路固定采用“PP-OCRv6 文字真值 + PP-StructureV3 版面真值”：不使用 Structure/VL 块文本覆盖 OCR 行文字，不合并 PDF 行坐标；Structure 覆盖率低于 0.75 时自动退回纯几何规则，VL-1.5 仅作为显式低置信兜底。
- 中文段内空白按 Unicode 空白和 CJK 邻接规则清理，原字符形态及拉丁词之间的必要空格继续保留；版面 `seal` 区域只按坐标排除 OCR 噪声，不写死具体印章文字。

### 技术优化

- PP-StructureV3 与 VL 解析保留 `bbox`、`label`、阅读顺序及分段标志等最小版面元数据，OCR dump/resume 全程保留这些字段。
- 新增自然段合并、标题隔离、页边界、脚注拆分、CJK 空白、印章过滤、坐标缩放、低覆盖回退和五模型分发测试。
- 同一真实单页样本多轮复测：v5/v6 原始全文 CER 均为 2.98%，Structure 块文本 2.55%，VL-1.5 4.26%，VL-1.6 11.91%；v6 + Structure 过滤 2 行印章噪声后得到 15 个自然段、470 字符 CER 0%、段落边界 F1 1.00。
- 外部 API 首轮观测延迟约为 v6 9.2 秒、VL-1.5 11.9 秒、Structure 30 秒以上、VL-1.6 110 秒以上；随后 v5/v6/Structure 热复测均在约 15 秒内完成。该数据包含服务排队和网络波动，只用于本样本选型，不作为 SLA。
- 最终双层 PDF 1/1 页，24 个透明文字 span 全部在页内且无零面积框，span 宽度/检测框比 0.9989–1.0000；原始图像流和页面渲染逐像素不变，PyMuPDF、pypdf、Poppler 抽取完全一致。
- `/ActualText` 兼容性实验中，Poppler `-raw` 能按 15 段顺序提取，但 PyMuPDF 仍按物理行排版，pypdf 与 macOS PDFKit 忽略提示，Poppler 默认布局排序会把段落倒序；因此跨阅读器默认仍交付行级双层 PDF + 自然段 Markdown，不把实验模式冒充通用修复。

### 范围说明

- 模型准确率和延迟结论只适用于用户明确授权上传的 `IMG_4304.pdf`，不扩大为跨版式稳定性结论；原始响应、全文、账号和中间产物仅存临时目录。

## [2.9.3] - 2026-08-01

### 修复

- 修复 `PP-OCRv5` 行级检测框写入透明文字层后，CJK 字形自然宽度只占原框约 60%–90%、导致选区横向明显偏短的问题；对可信范围内的单行未旋转文字按检测框做水平缩放，极端空白框及多行/旋转路径保持原行为。
- 修复统一入口默认 PaddleOCR 路径仍先栅格化、预压缩的问题；显式 `paddle_api` 或 `auto` 首选 Paddle 时现在直送原 PDF，`--enable-crop`、`--force-raster-preprocess` 等显式请求继续覆盖默认值。

### 改进

- `auto` 的原图直送判断与 `OCR_API_ORDER` 保持一致；默认按 `paddle,mineru`，若显式把 MinerU 放在首位则不误用 Paddle 短路。
- 明确敏感 PDF 的文件级授权边界：首次上传外部 OCR 前需说明会传输完整文件并取得确认，授权不自动扩展到同目录或其他材料。
- 保留原始 Paddle 识别版与人工复核版的职责区分；不为单份样本写死印章文本过滤规则，也不接入视觉大模型生产后端。

### 技术优化

- 新增 Paddle 原图路由、显式预处理覆盖、单行横向框贴合及极端缩放保护测试。
- 经用户授权将真实单页样本 `IMG_4304.pdf` 上传 PaddleOCR API：PP-OCRv5 原图直送全文 CER 2.98%，统一预处理版 3.40%，PP-StructureV3 原图直送 3.62%，本地 Tesseract 6.81%；原始 Paddle 的正文、日期、金额和账号均识别正确，剩余差异为印章噪声及一处标点。
- 最终 Paddle 原始版和人工复核版均 1/1 页可检索、无越界或零面积词框，原始图像流与页面渲染逐像素不变；修复后文字 span 宽度/检测框比例为 0.9989–1.0000，人工复核版 470 字符基准 CER 为 0%，PyMuPDF、pypdf、Poppler 抽取完全一致。

### 范围说明

- 本次外部上传严格限于用户明确授权的 `IMG_4304.pdf`；OCR 全文、账号信息、API dump 和复核文件只保存在临时目录，不写入 Skill 或版本库。单页结果不扩大为跨文档稳定性结论。

## [2.9.2] - 2026-08-01

### 修复

- 修复统一入口在确定使用本地 `ocrmypdf` 时仍先对扫描页重栅格化、预压缩，导致 Tesseract 中文识别率显著下降的问题；本地路径现在直接保留原扫描分辨率并启用 OCRmyPDF 自带的方向检测、纠偏和清理。
- 本地原生短路同时覆盖显式 `--backend local_ocrmypdf`、`--local-only` 及 `auto` 未配置外部 API 的场景；`--enable-crop`、`--force-raster-preprocess`、`--preprocess-only` 和显式 `--skip-preprocess` 继续按用户指令执行。

### 改进

- 补充“文字框对齐但复制文字错误”的诊断口径：三种 PDF 提取器与 OCR sidecar 一致只能证明文字层写入真实，不代表 OCR 字符正确；逐字准确率须用人工基准或已审核真值评估。
- PaddleOCR API 默认优先策略保持不变；本版本不新增视觉大模型，也不把 macOS Vision 纳入生产后端。

### 技术优化

- 新增本地原生预处理选择及显式覆盖项回归测试；聚焦测试 26 项通过。
- 真实单页扫描样本 `IMG_4304.pdf` 本地回归：按包含姓名、日期、金额和账号的 470 字符完整基准，旧统一流程全文 CER 约 22.13%，修复后约 6.81%；原始嵌入图像保持 2305×3310，不再先放大到 4162×5977。另用 macOS 本地 Vision 生成仅限本次样本的人工核对版，完整基准 CER 为 0%，但未接入技能生产链路。

### 范围说明

- 样本含医疗案件及银行账号信息，全程仅在本机处理，未上传 PaddleOCR/MinerU，也未归档 OCR 全文。Tesseract 修复版仍有明显中文误识别，不作为高精度法律文本推荐结果。

## [2.9.1] - 2026-08-01

### 修复

- 统一预处理入口新增 25MP 单页像素保护：遇到把图像像素尺寸直接写成 PDF point 的异常大画布时，自动降低实际渲染 DPI，避免默认 200/300 DPI 生成 50MP 以上位图后又被 `ocrmypdf --skip-big 50` 静默跳过。
- OCR 质量验收与 benchmark 的关键词匹配统一改为 NFKC、大小写和空白归一化，修复 Tesseract 在汉字间插入空格后把已识别关键词误判为未命中的问题。

### 改进

- 新增 `--max-preprocess-megapixels`，默认 25；可显式调高，设为 0 时关闭保护。预处理元数据同时记录请求 DPI、实际 DPI、保护前后像素量和触发原因。

### 技术优化

- 新增正常页面不降 DPI、异常大画布自动限幅、保护可关闭、中文空白关键词匹配及 benchmark 同口径回归测试。
- 真实单页扫描样本 `IMG_4304.pdf` 回归：修复前默认统一入口生成 58.9MP 页面并跳过 OCR；修复后自动使用 130 DPI / 24.9MP，1/1 页可检索、10/11 验收关键词命中、138 个词框无越界或零面积，质量门禁通过。

### 范围说明

- 样本含医疗案件及银行账号信息，本轮只做本地 `ocrmypdf` 测试，未上传外部 PaddleOCR；该样本的 Paddle 多模型效果为 `NOT_VERIFIED`。

## [2.9.0] - 2026-08-01

### 改进

- `auto` 恢复已配置 PaddleOCR API 默认优先，随后尝试 MinerU，外部服务失败后回退本地 `ocrmypdf`；新增 `--local-only` 作为敏感材料的强制本地开关，旧 `--allow-external-upload` 保留为兼容参数。
- Paddle API 模型扩展为 `PP-OCRv5`、`PaddleOCR-VL-1.5`、`PaddleOCR-VL-1.6` 和 `PP-StructureV3`；双层 PDF 默认仍用 `PP-OCRv5` 的行级坐标。

### 修复

- 新增 PP-StructureV3 `layoutParsingResults[].prunedResult.overall_ocr_res` 行级结果解析，并兼容 `dt_polys`、`rec_polys` 与四值 `rec_boxes`。
- PP-StructureV3 不再把 `parsing_res_list` 的整段块文本覆盖到单行坐标；服务端方向矫正和去畸变默认关闭，避免坐标空间偏移。

### 技术优化

- 新增 4 模型响应分发、Structure 字符串/对象 `prunedResult`、默认 payload、Paddle 默认路由和 `--local-only` 回归。
- 同一份 2 页无隐私中文扫描件实测：Paddle `PP-OCRv5` 字符错误率约 1.08%，本地 `ocrmypdf` 约 10.04%；两者均 2/2 页可检索、词框无越界，Paddle 输出与输入逐像素一致。

### 范围说明

- 本版本不接入 Qwen/GLM 等视觉模型，不提供字段/签章 grounding，也不宣称字符级坐标。
- 真实 7 页病历只完成本地回归；因医疗隐私未上传外部 PaddleOCR，该材料的 Paddle 效果为 `NOT_VERIFIED`。

## [2.8.0] - 2026-07-30

### 修复

- 修复 Tesseract OSD 使用错误字段名且旋转方向换算错误的问题，兼容 `pytesseract.Output.DICT` 的小写键。
- 透明文字层改用字体真实 ascender/descender 指标定位 baseline，修复选区垂直越界；文字框无法容纳完整内容时不再静默截断。
- 修复斜切检测条件数学上不可达的问题，改按 polygon 主边相对页面轴的真实夹角判定。
- 缺少 OCR 坐标空间宽高时不再用内容最大坐标猜测全页缩放；只有坐标可验证为 PDF 点单位才继续，否则安全回退。
- 修复外部 OCR 结果缺页、空页、低健康度或部分文字块失败时仍保存为成功的问题；现在只在全部页面通过后原子写出，否则回退本地 OCR。
- 修复 `pypdf 6` 移除 `PdfMerger` 导致合并入口无法启动的问题，并消除连续编号页数重复扫描和异常时临时目录残留。
- 修复 OCR 质量检查无阈值时空通过及文档示例参数错误；默认要求页数一致、全部输出页可检索，关键词存在时默认全部命中。
- 修正统一入口 CLI 示例仍把默认 OCR 模式误写为 `redo` 的残留文案，现与实际 `skip` 默认值一致。

### 改进

- 电子/混合 PDF 默认保留文字、矢量、图片和批注层，跳过栅格化预处理与重压缩；新增 `--force-raster-preprocess` 显式覆盖。
- OCR 默认模式改为 `skip`，外部坐标叠层在 `redo` / `force` 遇到既有文字层时安全回退。
- `auto` 后端默认不上传文件，新增 `--allow-external-upload`；OCR 文本和预处理元数据默认不归档，新增 `--archive-results`。
- 对齐研究 harness 改用当前 Skill 动态路径和显式样本目录，移除失效的历史 worktree 与固定 `/tmp` 输入依赖，并修复 block/line/paragraph 基准错误读取空 TSV 层级行的问题。

### 技术优化

- 回归测试由 37 项扩展到 51 项，覆盖文字完整性、实际 span 边界、事务式缺页失败、不可验证坐标降级、真实斜切告警、电子/混合层保护、OSD 字段映射、外部上传门禁、合并兼容、TSV 聚合和质量检查退出码。

## [2.7.0] - 2026-07-10

### 修复（双层 PDF 文字层与图片层对齐根治）

- 🐛 **`pdf_ocr_layered.py` 多行排版根治**：v2.6 及之前 `calculate_font_size` 用「字号=框高」反推字号，CJK 字符 baseline 越界；`insert_text` 单行限制导致 block/line 级长文本溢出 bbox 宽度（PaddleOCR API 返回的正是 line/block 级外接框），文字层落在远离墨迹的位置——这是用户长期反映的「文字层和底下图片没那么对应」根因。v2.7 重写为 cap-height 模型（`_CAP_HEIGHT_RATIO_CJK=0.78`）+ 多行贪婪换行（`_split_text_to_lines`）+ 多行 `insert_text`（`_layout_text_into_bbox`），并在 v2.7.1 修正窄标点在小 bbox 被丢弃的回归。

- 🛡️ **坐标健康度评估 + 降级模式**：新增 `assess_ocr_coordinate_health(rows, page_rect, scale_x, scale_y)` 返回 `fit_score / skew_warn / scale_drift_warn / out_of_page_ratio`；当 `fit_score < 0.5` 时本页跳过文字层铺入（采用「坐标判定可证化，证不出就退化」思路），并在产物报告里给出降级页数与「建议改走 ocrmypdf 兜底」提示。

- 🔍 **`infer_page_scale` 中位数 ratio 回退**：当 OCR 端未提供 source_w/source_h 时，旧版用单个 max_x/max_y 反推 scale，对孤立离群框很敏感；v2.7 改为对所有 row 的 poly 宽高比取中位数做合理性校验，离群时回退到「OCR 坐标 = PDF 坐标」单位 scale。

- 🧮 **`page.rotation==0` 跳过 `derotation_matrix`**：恒等矩阵乘法虽无几何影响，但叠到上千行文本会有浮点累积漂移；v2.7 显式跳过此变换。

### 技术优化

- ✅ 新增 `scripts/test_pdf_ocr_layered_v27.py` 15 个单元测试，覆盖：cap-height 字号、多行二分搜索、贪婪换行、单行/多行排版、窄标点不丢失（v2.7.1 回归）、scale 中位数回退、坐标健康度评估；全部通过
- ✅ 新增 `references/v27-alignment-baseline/`：含研究 harness、确定性基准 JSON、前后对比 overlay PNG、最终对比摘要 JSON；用合成样本（电子件/扫描件/倾斜页各一）横向比较 scheme A（ocrmypdf 闭环）、D-word / D-line / D-para（pdf_ocr_layered.py 喂 tesseract TSV 的不同粒度）
- ✅ **确定性 A/B 数据**（同一份 TSV 输入，只切换 `pdf_ocr_layered.py`）：

| sample      | scheme | CER before→after | align% before→after | IoU before→after | dist_pt before→after |
|-------------|--------|------------------|---------------------|------------------|----------------------|
| scanned.pdf | D_para | 0.0244 → 0.0285  | 26% → 84%           | 0.140 → 0.441    | 58.97 → 26.96        |
| skewed.pdf  | D_line | 0.5519 → 0.5519  | 54% → 91%           | 0.315 → 0.591    | 42.84 → 6.87         |
| skewed.pdf  | D_para | 0.5519 → 0.5560  | 31% → 95%           | 0.178 → 0.599    | 48.81 → 8.14         |
| scanned.pdf | D_word | 0.0244 → 0.0285  | 98% → 97%           | 0.545 → 0.494    | 2.55 → 2.20          |

D_block（line/para 级 polys，对应 PaddleOCR API 实际输出粒度）对齐度大幅提升；D_word CER 微升 0.0244→0.0285，仍远低于 8% 验收线。

### 关联

- 关闭 v2.5.0 遗留项「双层 PDF 坐标偏移修复」与「MinerU vlm 坐标粒度」本轮范围（MinerU vlm 评估保留为后续 P2 项）
- 详见 `references/v27-alignment-baseline/v27-improved/v27_final_summary.json` 与工作树 `DECISIONS.md` / `TASKS.md` v2.7 段

## [2.6.8] - 2026-05-31

### 改进

- 🧭 **SKILL.md 瘦身**：将页码、合并、压缩、OCR 参数细节迁移到 `references/pdf-workflows.md`，核心文档收敛为统一入口、触发规则、依赖和交付检查
- 🧩 **本地 Paddle 历史实现解耦**：新增 `scripts/pdf_ocr_paddle_local.py`，将本地 Paddle 双层 PDF 实验后端从 `pdf-ocr.py` 主入口中拆出，保留未来恢复空间

### 修复

- 🐛 **单页分块预处理空 PDF**：修复单页 PDF 传入 `--preprocess-chunk-pages 1` 时误跳过渲染、生成空临时 PDF，导致后续 `ocrmypdf` 报 “Input file is empty” 的问题
- 📝 **默认参数说明同步**：修正故障排除与任务说明中的旧默认值，明确当前统一入口 `medium` 合并输出为约 200 DPI / JPEG 质量 72

### 技术优化

- ✅ 增加单页分块请求回归测试
- ✅ 使用真实康复医院病历样本前 1 页跑通本地 `ocrmypdf` 烟测，输出 1 页、可检索、关键词 `康复医院` 命中 1 次

## [2.6.7] - 2026-05-29

### 改进

- 📄 **默认清晰度提升**：`pdf-preprocess-ocr.py` 的默认 `medium` 合并输出从 150 DPI / JPEG 质量 65 / 子采样 2 调整为 200 DPI / JPEG 质量 72 / 子采样 1，减少扫描件文字在放大查看时发糊
- ⚖️ **法院上传场景平衡**：基于 `20260529145736.pdf` 跑多组参数对比，推荐默认档在 16 页样本上输出约 2.97 MB，较原始 6.34 MB 仍压缩约 53%，但内嵌图像从 1242×1755 提升到 1655×2340

### 文档完善

- 📝 `SKILL.md` 补充统一入口默认 `medium` 合并输出的清晰度取向，并提示文件大小限制严格时可显式使用 `--compress-level high`

### 技术优化

- ✅ 更新回归测试，覆盖新的默认合并输出 DPI、JPEG 质量和色度子采样参数

## [2.6.6] - 2026-05-17

### 新增

- 🧩 **显式仅预处理模式**：`scripts/pdf-preprocess-ocr.py` 新增 `--preprocess-only` / `--only-preprocess`，用于在用户明确要求“只做预处理、不要 OCR”时，仅执行解密、页面旋转/倾斜矫正和默认压缩，然后跳过 OCR 文字层生成

### 改进

- 📝 **触发规则收敛**：`SKILL.md` 新增“仅预处理模式（不 OCR）”工作流，明确该模式不是默认路径；默认完整流程仍是预处理后继续生成双层 PDF
- 🧭 **保真选项说明**：补充 `--preprocess-only --no-compress` 示例，用于只做页面矫正、不压缩、不 OCR 的场景

### 技术优化

- ✅ 新增 `write_preprocess_only_output()` 写出逻辑，复用统一入口的解密、预处理、压缩阶段，并保留原始文件时间戳
- ✅ 扩展 `scripts/test_pdf_preprocess_speed_options.py`，覆盖仅预处理输出写出与 dry-run 不写文件行为

## [2.6.5] - 2026-05-15

### 新增

- 📊 **OCR 端到端基准脚本**：新增 `scripts/pdf-ocr-benchmark.py`，用于运行完整“预处理 + 压缩合并输出 + OCR”链路基准，默认报告总耗时、页数、输出体积、页面尺寸一致性、可提取文字量和关键词命中
- 📄 **JSON/CSV 报告输出**：每次 benchmark 自动生成 `benchmark_report.json` 与 `benchmark_report.csv`，并保存 stdout/stderr 日志，便于横向比较本地 `ocrmypdf`、Paddle API、MinerU API 以及不同预处理参数

### 修复

- 🐛 **恢复 OCR 主链路脚本**：恢复合并过程中被删除的 `pdf-ocr.py`、`pdf_runtime.py`、`pdf_ocr_layered.py`、`pdf_ocr_mineru.py`、`pdf_ocr_paddle_api.py`、`pdf-compress.py` 等 OCR/压缩依赖脚本，避免 `pdf-preprocess-ocr.py` 导入失败

### 技术优化

- ✅ 新增 `scripts/test_pdf_ocr_benchmark.py`，覆盖 PDF 指标采集、抽样 PDF 生成和 benchmark 命令构建
- ✅ `SKILL.md` 新增端到端 OCR benchmark 示例，默认使用当前推荐的 `--preprocess-jobs 6 --preprocess-chunk-pages 80`
- ✅ 基于真实病历样本前 2 页跑通本地 `ocrmypdf` benchmark 烟测：总耗时约 9.55s，输出 2 页，可提取文字约 3792 字符

## [2.6.4] - 2026-05-15

### 改进

- ⚡ **预处理分块流水线**：`pdf-preprocess-core.py` 与 `pdf-preprocess-ocr.py` 新增 `--preprocess-chunk-pages`，支持按块渲染、处理并顺序写入输出 PDF，避免一次性持有完整文档图像
- ⚡ **后台预渲染下一块**：分块模式下使用单独渲染线程提前加载下一块页面，与当前块的倾斜检测和 JPEG 编码阶段重叠
- 📊 **耗时拆分统计**：预处理统计新增渲染耗时、保存耗时和实际分块页数，便于继续定位瓶颈
- 📝 **使用说明同步**：`SKILL.md` 的大批量扫描件示例改为 `--preprocess-jobs 6 --preprocess-chunk-pages 80`

### 技术优化

- ✅ 扩展 `scripts/test_pdf_preprocess_speed_options.py`，覆盖分块页数解析，以及两页样本分块处理后的页序与页面尺寸
- ✅ 完整 244 页样本基准（150 DPI、跳过粗方向检测、medium 合并输出）：不分块自动并行约 17.68s；`--preprocess-chunk-pages 80 --preprocess-jobs 6` 约 14.97s
- ✅ 分块基准输出均为 244 页，页面尺寸完全一致，52.59 MB 输入生成 43.14 MB PDF
- ✅ 抽取样本前 2 页跑分块预处理 + 本地 `ocrmypdf` 烟测，输出 2 页且可提取文字（约 3792 字符）

## [2.6.3] - 2026-05-15

### 改进

- ⚡ **预处理页面并行处理**：`pdf-preprocess-core.py` 与 `pdf-preprocess-ocr.py` 新增 `--preprocess-jobs`，支持对页面级倾斜检测/裁剪流程并行执行；`1` 为串行，`0` 为自动按 CPU 与页数选择
- ⚡ **PDF 保存阶段并行 JPEG 编码**：使用 PyMuPDF 组装输出 PDF 前，可按同一并行数预编码页面 JPEG，减少保存阶段等待时间
- 📊 **耗时统计更清晰**：预处理统计新增墙钟耗时与实际并行数，并将原“总耗时”口径改为“页面累计耗时”，避免并行模式下误读
- 📝 **使用说明同步**：`SKILL.md` 新增大批量扫描件的并行预处理示例，并修正仅预处理示例入口

### 技术优化

- ✅ 扩展 `scripts/test_pdf_preprocess_speed_options.py`，覆盖预处理并行数解析逻辑
- ✅ 完整 244 页样本基准（150 DPI、跳过粗方向检测、medium 合并输出）：串行约 32.13s；`--preprocess-jobs 4` 约 20.34s；`--preprocess-jobs 8` 约 17.41s；`--preprocess-jobs 0` 自动解析为 10 并行约 17.21s
- ✅ 上述基准输出均为 244 页，页面尺寸完全一致，52.59 MB 输入生成 43.14 MB PDF
- ✅ 抽取样本前 2 页跑本地 `ocrmypdf` 烟测，输出 2 页且可提取文字（约 3792 字符）

## [2.6.2] - 2026-05-14

### 改进

- ⚡ **预处理 DPI 随压缩档位自动调整**：`pdf-preprocess-ocr.py` 未显式传入 `--dpi` 时，按压缩档位选择预处理 DPI（合并压缩输出时 `medium=150`；禁用合并压缩时 `medium=200`；跳过压缩时保持 `300`），避免先 300 DPI 渲染再被 medium 压缩降采样的重复成本
- ⚡ **可跳过粗方向检测**：新增 `--skip-coarse-rotation`，适用于页面方向已经正确的扫描件，可跳过 Tesseract OSD 90° 检测；`PDFPreprocessor` 和 `process_pdf()` 同步支持 `enable_coarse_rotation`
- ⚡ **预处理与压缩合并输出**：默认在预处理阶段直接应用压缩档位的 DPI/JPEG 参数，跳过二次打开、解码、重编码；可用 `--no-merge-preprocess-compress` 回退为旧的两阶段压缩
- ⚡ **跳过未使用页面分析**：`process_page()` 不再执行未被后续逻辑使用的 `analyze_page()`，减少每页一次 Canny 边缘检测
- ⚡ **投影法两阶段搜索**：倾斜检测的投影剖面法改为 `0.5°` 粗扫 + `0.2°` 精扫，保持旧版 `0.2°` 角度网格，降低旋转搜索次数
- 📐 **低 DPI 输出尺寸保真**：预处理保存 PDF 时优先使用 PyMuPDF 按原始页面尺寸组装，避免 200 DPI 像素取整导致页面宽度轻微变化

### 技术优化

- ✅ 新增 `scripts/test_pdf_preprocess_speed_options.py`，覆盖跳过粗方向检测、压缩档位输出决策、合并压缩跳过逻辑和尺寸保真
- ✅ 扩展 `scripts/test_pdf_preprocess_skew.py`，覆盖投影法快速两阶段搜索和默认角度网格兼容
- ✅ 基于 13 页样本基准测试：300 DPI + 粗方向检测约 14.31s；200 DPI + 跳过粗方向检测约 3.58s，预处理阶段约提速 75%
- ✅ 完整 244 页预处理 + medium 压缩基准：总耗时约 87.92s，输出 244 页，页面尺寸完全一致，52.59 MB 输入生成 47.98 MB 压缩 PDF
- ✅ 完整 244 页合并输出基准：总耗时约 29.88s，输出 244 页，页面尺寸完全一致，52.59 MB 输入生成 43.14 MB PDF；与旧投影法最终矫正决策一致

## [2.6.1] - 2026-05-13

### 修复

- 🐛 **Hough 高置信误判**：倾斜检测不再因 Hough 置信度高就直接采用角度，必须与投影剖面法方向一致且角度接近；当 Hough 与投影法冲突时优先采用投影法，投影法也低于阈值则跳过矫正
- 🐛 **局部长线污染导致过度旋转**：降低单条超长边框、影像矩形、页脚横线对 Hough 角度的支配，并加入角度集中度约束，避免第 201/202/207 类页面被误判为 4° 以上倾斜
- 🐛 **轻微歪斜页漏矫正**：预处理默认倾斜阈值从 `0.5°` 调整为 `0.3°`，覆盖第 1/5 页这类约 `0.4°` 的轻微倾斜

### 技术优化

- ♻️ **倾斜检测模块解耦**：新增 `scripts/pdf_preprocess_skew.py`，将 Hough 检测、投影剖面法和角度决策从 `pdf-preprocess-core.py` 拆出；核心预处理脚本保留兼容包装方法，仅负责 PDF 流程编排
- ✅ 新增 `scripts/test_pdf_preprocess_skew.py` 覆盖 Hough/投影冲突、低置信 Hough、接近角度取平均等决策场景
- ✅ 基于样本 `251106-251231 康复医院病历（第二次入院）.pdf` 验证重点页：
  - 第 1/5 页在默认参数下触发轻微矫正
  - 第 201/202 页不再被 4°+ 过度旋转
  - 第 207 页改为按投影法轻微矫正
  - 第 110/115/117 页不再因 Hough 低估而跳过或欠矫正
- ✅ 完整 244 页仅预处理回归：默认阈值下倾斜矫正 204 页，输出页数 244、页面尺寸一致，残余角度候选（>=1.5°）为 0

## [2.6.0] - 2026-05-13

### 新增

- 📐 **Hough 竖线检测**：倾斜检测新增近竖直线（>75°）支持，表格竖线贯穿页面高度，对倾斜更敏感。水平线和竖线联合检测，线长平方加权，以占比更大的结构作为矫正依据
- 📊 **置信度决策机制**：Hough 返回 (角度, 置信度)。高置信（多长水平线=表格结构）→ 信任 Hough；低置信（纯文字页）→ 回退投影剖面法；低置信+Hough 小角度 → 两者平均
- ⏱️ **创建时间保留**：macOS 下使用 `SetFile -d` 保留 birthtime，配合 `os.utime` 保留 mtime，所有处理阶段（预处理/压缩/OCR）均保留原文件时间戳

### 修复

- 🐛 **300 DPI 下倾斜检测失效**：`minLineLength = page_w * 20%` 在 300 DPI 时为 496px，表格线全部被过滤导致检测为 0°。降为 10% 后 150/300 DPI 检测结果一致
- 🐛 **API 图片替换覆盖压缩**：`needs_correction` 误用 `bool(img_url)` 判断（API 默认对每页返回 preprocessedImages URL），导致所有页面被全尺寸原图替换，压缩白做。改为检查 payload 中 `useDocOrientationClassify`/`useDocUnwarping` 是否启用
- 🐛 **预处理短路误触发**：不再因使用 PaddleOCR API 就跳过本地预处理，只有 API payload 中确实启用了方向/去畸变时才短路
- 🐛 **大角度误检测**：表格线导致 Hough 检测到 6-7° 虚假角度（旧版 HoughLines 含竖线污染）。重写为 HoughLinesP + 只取近水平/竖直线 + 线长加权，消除误检
- 🐛 **双层 PDF 体积膨胀**：OCR 叠层保存参数从 `garbage=3, deflate=True` 升级为 `garbage=4, deflate_images=1, deflate_fonts=1, use_objstms=1, compression_effort=100`

### 改进

- 📦 **归档路径修复**：`archive_ocr_result()` 新增 `original_source_path` 参数，归档目录名和伴生 .md 以原始用户文件为准，`conversion_meta.json` 记录 `source_file`（原始路径）+ `working_file`（临时路径）+ `preprocess_meta`（完整预处理参数）
- 🔌 **--paddle-api-extra-json 合并修复**：`_build_optional_payload()` 现在正确合并额外 JSON 到 API payload
- 📦 **压缩预设调整**：medium 级别 max_dimension 从 3200 降至 2000，high 从 2600 降至 1600，压缩效果从 ~10% 提升至 ~35%

## [2.5.0] - 2026-05-12

### 新增

- 📷 **拍照件自动矫正**：PaddleOCR API 返回 `doc_preprocessor_res.angle`（0/90/180/270），非零页自动下载 `preprocessedImages` 替换 PDF 原始页面，处理 90/270° 旋转尺寸互换，坐标空间同步修正。通过 `--no-photo-correct` 禁用
- 📦 **Archive 运行记录**：新增 `conversion_meta.json` 记录运行元数据（时间戳、源文件、模型、后端、页数、文本块数），参照 mineru-ocr 规范
- 📄 **MD 同步输出**：OCR Markdown 文本同步输出到原文件同目录（与双层 PDF 平行），同时归档到内部 `archive/`
- ⏱️ **文件时间戳保留**：所有 PDF 输出路径通过 `shutil.copystat` 保留原文件的 mtime/atime

### 改进

- 🎯 **双层 PDF 坐标偏移修复**：关闭 PP-OCRv5 API 端 `useDocOrientationClassify` + `useDocUnwarping` 预处理。启用时 API 在服务端预处理图片（矫正/去畸变），OCR 坐标对应预处理后的图片但报告的图片尺寸不变，导致坐标偏移。关闭后坐标与原始图片一致，双层 PDF 对齐准确
- 📝 **段落合并尝试与回退**：尝试在双层 PDF 文字层中合并连续 OCR 行为段落文本，但因 `insert_text` 单行限制导致合并后字号过小、选中高亮异常，已回退。段落连续文本改为在 Markdown 输出中处理
- 🔌 **PaddleOCR API 预处理短路**：PP-OCRv5 和 VL-1.5 均启用 `useDocOrientationClassify` + `useDocUnwarping`，`pdf-preprocess-ocr.py` 检测到 PaddleOCR API 可用时自动跳过本地预处理（旋转/倾斜/裁剪），保留压缩阶段
- 🏷️ **VL-1.5 识别完整性**：补充 `content`、`paragraph_title`、`section_title` 标签，修复部分页面内容识别丢失
- 🔢 **页码过滤**：`number` 标签块 score=0，双层 PDF 保留但 MD 输出时过滤
- 🔙 **默认模型回切 PP-OCRv5**：PP-OCRv5 返回行级坐标，对双层 PDF 叠层定位更精确

### 删除

- 🗑️ **OCR 正则纠错规则层**：移除 `--ocr-corrections`/`--no-ocr-corrections` 参数，纠错由 agent dump/resume 语义审查完成
- 🗑️ **300+ 页流式处理任务**：PaddleOCR API 确认无页数限制，分片逻辑保留但不默认触发

### 任务管理

- 📝 TASKS.md 重构：已完成功能归入历史区，未完成项按 v2.5.0 组织
- 📝 新增已知问题（文件时间戳、大文档内存）

## [2.4.1] - 2026-05-08

### 技术优化

- ♻️ **脚本模块化拆分**（pdf-ocr.py 2197 行 → 1230 行）：
  - 新建 `pdf_ocr_layered.py`（572 行）：双层 PDF 叠层核心、OCR 结果解析、CJK 归一化
  - 新建 `pdf_ocr_mineru.py`（502 行）：MinerU API 后端
  - 新建 `pdf_ocr_paddle_api.py`（162 行）：PaddleOCR API 后端
  - 扩展 `pdf_runtime.py`：HTTP 工具函数 + API 环境变量常量
  - pdf-ocr.py 瘦身为 CLI 入口 + 后端分发（1230 行）
- ♻️ **消除跨文件重复代码**：
  - pdf-analyze.py 从 core 导入（-130 行，5 个重复函数）
  - pdf-rotate.py 从 core 导入（-101 行，3 个重复函数）
  - pdf-crop.py 从 core 导入（-24 行，1 个重复函数）
  - pdf-merge.py 从 pdf-add-page-numbers 导入（-47 行，1 个重复函数）
- ♻️ **消除 subprocess 耦合**：
  - pdf-preprocess-ocr.py 从 subprocess 调用改为直接函数调用 `run_ocr()`
  - 减少 ~170 行 argparse 重复，运行时更高效
  - pdf-preprocess-ocr.py 从 609 行瘦身至 439 行

## [2.4.0] - 2026-05-08

### 修改

- 🧹 **SKILL.md 瘦身**：从 580 行精简至 418 行
  - OCR 后端配置详情移入 `references/ocr-backend-guide.md`
  - 故障排除内容移入 `references/troubleshooting.md`
  - 可选依赖表格精简为一行 pip 引用
  - 注意事项合并精简
- 📝 frontmatter 补充负面触发词（`不要用于：...`）

### 删除

- 🗑️ 删除冗余文件：`README.md`（与 SKILL.md 重复）、`OPTIMIZATION-PLAN.md`（合入 TASKS.md）
- 🗑️ 删除废弃脚本：`pdf-ocr-paddle.py`、`pdf-ocr-rapid.py`（功能已收敛至 pdf-ocr.py）
- 🗑️ 删除 `pdf_deskew.py`（指向 pdf-deskew.py 的冗余 symlink）
- 🗑️ 删除 `scripts/legacy/` 目录（gentle-deskew.py、pdf-enhance-contrast.py 已长期归档）

### 文档完善

- 📝 TASKS.md 合入 OPTIMIZATION-PLAN.md 中的质量目标与后续计划
- 📝 新增 `references/ocr-backend-guide.md` 和 `references/troubleshooting.md`

## [2.3.21] - 2026-04-09

### 文档完善

- 📝 进一步明确 OCR 外部后端推荐顺序：
  - `PaddleOCR API` 标记为“预处理 + 双层 PDF”主链路的首选外部后端
  - `MinerU API` 明确为“同样支持，但当前链路更偏异步任务式”的可选后端
  - `README.md` 与 `SKILL.md` 补充后端选择建议与使用场景说明

## [2.3.20] - 2026-04-02

### 改进

- 🔀 收敛 OCR 默认生产路径为“外部 API 优先 -> 本地 `ocrmypdf` 兜底”：
  - `scripts/pdf-ocr.py` 的 `auto` 模式在未配置外部 API 时，不再尝试本地 Paddle 双层
  - 未配置外部 API 时会明确提示：建议优先配置 PaddleOCR API / MinerU API
  - 外部 API 不可用时继续直接回退本地 `ocrmypdf`
- 🔧 `pdf-ocr.py` 与 `pdf-preprocess-ocr.py` 的 `--backend` 公开选项移除 `local_paddle_layered`

### 文档完善

- 📝 更新 `README.md` 与 `SKILL.md`：
  - 默认 OCR 路径说明改为“外部 API 优先，否则 `ocrmypdf`”
  - 不再把本地 Paddle 作为公开默认方案或推荐安装依赖
- 📝 更新 `TASKS.md` 与 `DECISIONS.md`，记录本次生产策略收敛

## [2.3.19] - 2026-04-02

### 改进

- 🔧 为主链路与预处理脚本统一依赖提示：
  - 新增 `scripts/pdf_runtime.py` 收敛 `.env` 加载、API 别名兼容、缺依赖提示
  - 当首次缺失 OCR / 图像处理依赖时，额外提醒“安装和首次初始化可能较慢”
  - `pdf-ocr.py`、`pdf-preprocess-ocr.py`、`pdf-preprocess-core.py`、`pdf-crop.py`、`pdf-rotate.py`、`pdf-analyze.py` 全部改用统一提示

### 技术优化

- ♻️ 删除重复的 `.env` 加载 / API 别名代码，减少 `pdf-ocr.py` 与 `pdf-preprocess-ocr.py` 的重复实现

### 清理

- 🧹 删除零价值文件：
  - `scripts/CLAUDE.md`
  - 仓库内遗留 `.DS_Store`
- 📝 明确 `pdf-ocr-paddle.py` 与 `pdf-ocr-rapid.py` 仍为历史兼容 / 辅助脚本，暂不纳入本次清理

## [2.3.18] - 2026-03-22

### 改进

- 🔄 清理从旧 `doc-processor` / worktree 迁移遗留的技能文档：
  - 重写 `README.md`，移除过期的 `src/cli.py`、Word、LibreOffice、`requirements/*.txt` 等描述
  - 刷新 `TASKS.md`，聚焦当前 `pdf-processor` 技能的真实待办与已知问题
  - 更新 `DECISIONS.md`，补充本次迁移收尾决策与工作日志

### 技术优化

- 🗜️ 重构 `scripts/pdf-compress.py`：
  - 改为使用 PyMuPDF 对 PDF 做对象流压缩与资源整理
  - 对页面图像执行 JPEG 重编码，压缩级别不再只是“名义参数”
  - 在安装 `Pillow` 时，按压缩级别对超大图像做缩放

### 文档完善

- 📝 `SKILL.md` 许可证字段改为 `MIT`，与当前 `LICENSE` 文件保持一致
- 📝 更新依赖说明：`pymupdf` 的用途扩展到 PDF 压缩，`pypdf` 改为解密/合并辅助
- 📝 记录本次迁移收尾中 `.env` 风险暂缓处理的边界，便于后续接手

## [2.3.17] - 2026-02-16

### 修复

- 🐛 修复倾斜矫正中的跨页角度耦合（`scripts/pdf-preprocess-core.py`）：
  - 移除 `prev_angle` 跨页影响逻辑，改为“每页独立检测与决策”
  - 避免前页角度对后页矫正结果产生抑制或误导
- 🐛 修复预处理裁剪统计误报：
  - 仅在页面尺寸实际发生裁剪变化时才记录 `crop`
  - `裁剪页数` 与页面日志改为真实裁剪结果，不再按开关状态计数
- 🐛 修复预处理与 OCR 阶段日志交错问题：
  - 页面处理日志补充 `flush=True`，避免多阶段输出串行时出现乱序粘连

### 技术优化

- ✅ 回归验证（样本：`20260126154823.pdf`）：
  - 预处理结果维持 `倾斜矫正: 1/3`（仅第一页）
  - 预处理 + OCR 端到端成功（`paddle_api(official:layered)`）
  - 质量验收通过：`searchable_ratio=100%`

## [2.3.16] - 2026-02-13

### 修复

- 🐛 修复预处理中“第 1 页矫正后带偏后续页面”的问题（`scripts/pdf-preprocess-core.py`）：
  - 细倾斜检测从“单方法命中即采用”调整为“多方法一致性判定”
  - 单方法小角度（<2°）结果不再直接触发矫正，降低误检
  - 跨页离群保护改为“当前页不矫正”，不再直接继承前一页角度

### 技术优化

- ✅ 基于样本 `20260126154823.pdf` 实测：
  - 预处理阶段倾斜矫正从 `3/3` 收敛为 `1/3`（仅第一页矫正）
  - 后续 MinerU 叠层链路保持正常，输出 `pdf-processor/test/20260126154823_preprocess_mineru_v2.pdf`

## [2.3.15] - 2026-02-13

### 修复

- 🐛 修复 MinerU 预签名上传在部分环境下失败（`Broken pipe`）的问题：
  - `scripts/pdf-ocr.py` 新增 MinerU 上传头解析（兼容 `headers` 返回结构）
  - 上传阶段不再强制附加 `Content-Type`，避免 OSS 签名不匹配
  - `urllib` PUT 失败时自动回退 `curl PUT`，提升跨网络栈兼容性

### 技术优化

- ✅ 基于真实 API 实测验证：
  - 样本：`20260126154823.pdf`
  - 后端：`mineru_api(layered)`
  - 输出：`pdf-processor/test/20260126154823_mineru_api.pdf`
  - 结果：3/3 页可检索，体积比约 `1.021`

## [2.3.14] - 2026-02-13

### 改进

- 🔀 默认外部 API 顺序调整为 Paddle 优先：
  - `scripts/pdf-ocr.py` 的默认顺序改为 `paddle,mineru`
  - `config/.env` 与 `config/.env.example` 默认 `OCR_API_ORDER` 改为 `paddle,mineru`
- 🔧 CLI 帮助示例更新为 `paddle,mineru`（`pdf-ocr.py` / `pdf-preprocess-ocr.py`）

### 文档完善

- 📝 更新 `SKILL.md`、`references/paddleocr-api-guide.md`、`references/mineru-api-guide.md` 的顺序示例
- 📝 更新 `TASKS.md`、`DECISIONS.md` 记录本次默认策略调整

## [2.3.13] - 2026-02-12

### 新增

- ✨ 新增 MinerU Token 过期/鉴权失败检测（`scripts/pdf-ocr.py`）
  - 覆盖 `401/403` 及常见 Unauthorized/Token 失效文案
  - 失败提示中明确 14 天有效期与更新地址：`https://mineru.net/apiManage/token`

### 改进

- 🔧 MinerU 环境变量对齐与兼容增强：
  - 默认 Base 变量改为 `MINERU_API_BASE`
  - 新增 `MINERU_USER_TOKEN` 支持（用于 `token` 请求头）
  - 兼容旧变量：`MINERU_API_BASE_URL`、`MINERU_BASE_URL`、`MINERU_API_ENDPOINT`
- 🔧 修复 MinerU Base 包含 `/api/v4` 时的路径重复拼接问题
- 🔧 `pdf-preprocess-ocr.py` 同步透传 `--mineru-user-token-env`

### 文档完善

- 📝 更新 `config/.env` 与 `config/.env.example`（MinerU + Paddle 顺序配置说明）
- 📝 更新 `references/mineru-api-guide.md`（新增 Token 14 天有效期与更新流程）
- 📝 更新 `TASKS.md`、`DECISIONS.md` 记录本次改动

## [2.3.12] - 2026-02-12

### 新增

- ✨ 新增 `mineru_api` 外部后端（`scripts/pdf-ocr.py`）
  - 支持 MinerU 异步任务流程：创建任务 -> 上传文件 -> 轮询结果 -> 下载 ZIP
  - 支持从 MinerU 结果包中的 `middle/model` JSON 解析文本与坐标，并本地叠层输出双层 PDF
- ✨ 新增 MinerU 相关参数透传（`scripts/pdf-preprocess-ocr.py`）

### 改进

- 🔀 `auto` 后端升级为“多外部 API 顺序优先”：
  - 同时支持 `mineru` 与 `paddle`
  - 外部 API 顺序支持：`--api-order`、`OCR_API_ORDER`、`.env` 配置顺序推断
- 🔧 新增 MinerU 环境变量与别名兼容：
  - 标准变量：`MINERU_API_BASE_URL`、`MINERU_API_TOKEN`
  - 别名：`MINERU_BASE_URL`、`MINERU_API_ENDPOINT`、`MINERU_TOKEN`、`MINERU_API_KEY`

### 文档完善

- 📝 更新 `config/.env.example`：支持 MinerU + Paddle 双配置与顺序控制
- 📝 新增 `references/mineru-api-guide.md`
- 📝 更新 `SKILL.md` 外部 API 章节，明确双 API 与顺序策略
- 📝 `TASKS.md`、`DECISIONS.md` 同步记录本次能力扩展

## [2.3.11] - 2026-02-12

### 改进

- 🗂️ 调整可选依赖清单目录位置：`assets/optional.txt` 迁移为 `references/optional-dependencies.txt`
- ✅ 依赖说明归类到 `references/`，减少 `assets/` 目录语义混淆

### 文档完善

- 📝 `SKILL.md` 依赖章节新增可选依赖清单入口（`references/optional-dependencies.txt`）
- 📝 `TASKS.md`、`DECISIONS.md` 同步记录本次迁移决策与完成状态

## [2.3.10] - 2026-02-12

### 技术优化

- 🗂️ 将零引用历史脚本归档到 `scripts/legacy/`（替代直接删除）：
  - `scripts/gentle-deskew.py` -> `scripts/legacy/gentle-deskew.py`
  - `scripts/pdf-enhance-contrast.py` -> `scripts/legacy/pdf-enhance-contrast.py`
- ✅ 主目录保留生产脚本，降低误删风险并提升分发可读性

### 文档完善

- 📝 `TASKS.md` 增补并勾选“归档零引用历史脚本”任务
- 📝 `DECISIONS.md` 新增 DEC-015，记录归档策略与影响

## [2.3.9] - 2026-02-12

### 技术优化

- 🧹 清理 `scripts` 目录冗余测试与缓存文件（保守策略）：
  - 删除 `scripts/test-paddleocr.py`
  - 删除 `scripts/__pycache__/` 下历史 `.pyc`
  - 删除仓库内遗留 `.DS_Store` 文件
- ✅ 保留当前生产链路与兼容脚本（如 `pdf-ocr.py`、`pdf-preprocess-ocr.py`、`pdf-ocr-rapid.py`），避免误删

### 文档完善

- 📝 `TASKS.md` 增补并勾选“冗余脚本清理”任务
- 📝 `DECISIONS.md` 新增 DEC-014，记录本次清理原则与范围

## [2.3.8] - 2026-02-12

### 新增

- ✨ 新增外部 API 参考指引：`references/paddleocr-api-guide.md`
  - 推荐法律文档优先使用 `PP-OCRv5_API`
  - 汇总 PaddleOCR 官方接口文档链接（PP-OCRv5 / PP-StructureV3 / PaddleOCR-VL / PaddleOCR-VL-1.5）
  - 明确 `API_URL` / `TOKEN` 获取路径与落地步骤

### 文档完善

- 📝 `SKILL.md` 外部 API 章节新增 references 入口，便于协作者快速定位接入说明
- 📝 `TASKS.md` 增补并勾选“外部 API 接入指引文档”任务
- 📝 `DECISIONS.md` 新增 DEC-013，记录推荐模型与文档结构决策

## [2.3.7] - 2026-02-12

### 新增

- ✨ 新增 `.env` 配置加载能力（`scripts/pdf-ocr.py`、`scripts/pdf-preprocess-ocr.py`）
  - 新增参数：`--env-file`、`--no-env-file`
  - 默认自动读取 `pdf-processor/config/.env`
- ✨ 新增 `config/.env.example` 模板
  - 标准变量：`PADDLE_OCR_API_ENDPOINT`、`PADDLE_OCR_API_KEY`
  - 兼容别名：`API_URL`、`TOKEN`

### 改进

- 🔧 外部 API 配置兼容增强
  - 自动映射 `API_URL -> PADDLE_OCR_API_ENDPOINT`
  - 自动映射 `TOKEN -> PADDLE_OCR_API_KEY`
- 🔧 鉴权头兼容增强
  - 同时发送 `Authorization: Bearer <token>` 与 `token: <token>`
  - 提升对不同网关实现的兼容性

### 技术优化

- 🧪 零参数链路验证：通过 `config/.env` 自动注入 endpoint/token，无需手工 `export`

## [2.3.6] - 2026-02-12

### 新增

- ✨ 外部 PaddleOCR API 协议支持升级为“官方优先 + 旧协议兼容”（`scripts/pdf-ocr.py`）
  - 新增 `--paddle-api-protocol auto|official|legacy`（默认 `auto`）
  - `auto` 会先尝试官方请求格式（`file` + `fileType`），失败后自动尝试 legacy 协议
- ✨ 新增“API OCR 结果本地叠层”能力
  - 当 API 未返回 `output_pdf_*` 时，自动解析 `result/data` 中的 `ocrResults/layoutParsingResults`
  - 支持解析 `prunedResult.rec_texts/rec_scores/rec_polys` 并本地生成双层 PDF

### 改进

- 🔧 外部 API 成功判定增强
  - 支持官方字段 `errorCode == 0`
  - 支持从 `result` 或 `data` 提取有效载荷
- 🔧 OCR 结果解析增强
  - `parse_paddle_predict_result` 扩展支持 dict/list 多种返回结构
  - 兼容 polygon 的二维点格式与扁平坐标格式

### 技术优化

- 🧪 新增本地 mock 回归（官方 `errorCode/result/ocrResults/prunedResult`）验证：
  - 后端链路：`paddle_api(official:layered)` 成功输出双层 PDF
  - 样本：`20260126154823.pdf`，3 页均完成文字层叠加

## [2.3.5] - 2026-02-12

### 新增

- ✨ 新增本地 Paddle 自动设备检测（`scripts/pdf-ocr.py`）
  - 在 `Windows/Linux` 场景自动探测 CUDA 可用性
  - 检测到 CUDA 时，无需额外参数自动启用 GPU 推理
  - 未检测到或初始化失败时自动回退 CPU，保证流程稳定

### 改进

- 🚀 `auto` 档位在设备层面进一步自适应：
  - 本地检测到 GPU 时，自动联动 `quality` 档位
  - CPU 场景继续按既有策略（macOS/Windows 默认 `balanced`，长文档触发 `speed`）
- 🔍 本地 Paddle 日志新增设备信息输出（`device: cpu/gpu + reason`），便于分发排障

### 技术优化

- 🧪 在当前 macOS 样本 `20260126154823_input.pdf` 的回归实测：
  - 端到端命令：`scripts/pdf-preprocess-ocr.py --backend auto`
  - 结果：`real ≈ 41.41s`（日志：`bench_default/run_default_after_gpu_auto.log`）
  - 与 2.3.4 的 `39.16s` 同量级，保持在优化后的稳定区间

## [2.3.4] - 2026-02-12

### 新增

- ✨ 新增本地 Paddle 运行档位参数（`scripts/pdf-ocr.py` / `scripts/pdf-preprocess-ocr.py`）
  - `--paddle-profile auto|quality|balanced|speed`
  - `--paddle-long-doc-pages`（长文档自动切换 speed 的页数阈值，默认 60）
  - `--keep-paddle-model-source-check`（恢复模型源连通性检查）
  - `--paddle-model-source huggingface|bos`（指定模型下载源）

### 改进

- 🚀 新增设备自适应策略（默认 `--paddle-profile auto`）
  - `macOS / Windows` 默认 CPU 场景自动选择 `balanced`（`PP-OCRv5_mobile_det/rec`）
  - 长文档（页数达到阈值）自动切换 `speed`
  - Linux 场景默认保持 `quality`（可显式覆盖）
- 🚀 默认关闭 PDX 模型源连通性检查（`PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True`）
  - 减少每次调用本地 Paddle 时的额外等待
- 🔧 `pdf-preprocess-ocr.py` 改为“仅在显式传参时”透传 `--paddle-dpi / --paddle-det-limit-side-len`
  - 让自动档位可真正接管参数，避免被固定值覆盖

### 技术优化

- 🧪 基于样本 `20260126154823_input.pdf` 的回归实测（同机同环境）：
  - 旧默认链路（本地 server 模型）：平均 `real ≈ 66.71s`
  - 新默认链路（auto->balanced）：`real ≈ 39.16s`
  - 实测总耗时下降约 `41%`
  - 回归日志：`bench_default/run_default_after_opt.log`

## [2.3.3] - 2026-02-12

### 新增

- ✨ 新增 OCR 质量验收脚本 `scripts/pdf-ocr-quality-check.py`
  - 支持可检索页占比统计
  - 支持关键词命中率统计
  - 支持 CER（需参考文本）计算
  - 支持输出体积比与耗时校验（可配置阈值 + JSON 报告）

### 改进

- 🔧 `auto` 后端策略调整为“外部 API 优先”
  - 配置了 `--paddle-api-endpoint` 或环境变量 `PADDLE_OCR_API_ENDPOINT` 时，优先走 `paddle_api`
  - API 不可用时直接回退 `local_ocrmypdf`（避免触发本地 Paddle 模型下载）
  - 新增 `--paddle-api-endpoint-env`，支持自定义 endpoint 环境变量名
  - `PaddleOCR` 改为懒加载：外部 API 路径下不再触发本地模型初始化检查
- 🔧 本地双层 PDF 引擎进一步对齐 Umi-OCR 实践
  - `fitz.Font("cjk")` + `insert_font` 持续作为中文字体嵌入主路径
  - CJK 空格清理增强：新增中文标点邻接空格清理，减少中文文本中异常断裂
- 🔧 一键流程保真策略升级（零参数生效）
  - 预处理默认 DPI 调整为 `300`
  - 预处理输出 JPEG 质量默认调整为 `90`
  - `pdf-preprocess-ocr.py` 默认关闭裁剪（需 `--enable-crop` 才启用），降低不必要重采样导致的发糊
  - 本地 Paddle 双层渲染默认 DPI 调整为 `300`，提升中文识别稳定性

### 技术优化

- 🧭 默认自动流程保持：
  - 自动识别旋转/倾斜页（无需手工传参）
  - `auto` 后端优先 `local_paddle_layered`，失败自动回退 `local_ocrmypdf`
  - 修复 `ocrmypdf --redo-ocr` 与 `--deskew/--clean` 参数冲突（`redo` 模式下不再追加 `deskew/clean`）
- 🧪 新增回归产物（样本：`20260126154823_input.pdf`）
  - `output_auto_default_noargs_v10.pdf`（零参数默认链路）
  - `quality_v10.json`（质量验收报告）

---

## [2.3.2] - 2026-02-12

### 修复

- 🐛 修复预处理倾斜误判导致“应矫正页面被跳过”的问题
  - 在 `pdf-preprocess-core.py` 中为倾斜角增加合理范围拦截（>15° 视为异常值）
  - 修复跨页平滑初始化问题：第一页不再被“初始角度=0”误覆盖，同时保留跨页离群抑制

### 改进

- 🔧 OCR 默认优化策略调整为保真优先
  - `scripts/pdf-ocr.py` 默认 `--optimize 0`
  - `scripts/pdf-preprocess-ocr.py` 默认 `--optimize 0`
  - 默认输出类型从 `pdfa` 调整为 `pdf`
  - 降低输出双层 PDF 的清晰度损失风险
- 🤖 默认工作流收敛为零参数自动判定
  - 自动识别是否需要页面旋转与倾斜矫正
  - 减少人工传参成本，更适合自动化 Skill 调用

### 文档完善

- 📝 更新 `SKILL.md`：补充“发糊/清晰度下降”故障排查与保真命令示例

---

## [2.3.1] - 2026-02-11

### 新增

- ✨ 为 OCR 流程预留外部 PaddleOCR API 后端接口
  - `scripts/pdf-ocr.py` 新增 `--backend paddle_api`
  - 新增接口参数：`--paddle-api-endpoint`、超时、重试、额外 JSON、API Key 环境变量
  - 支持 API 返回 `output_pdf_base64 / output_pdf_url / output_pdf_path`

### 改进

- 🔄 `scripts/pdf-preprocess-ocr.py` 新增后端透传参数
  - 一键预处理流程可直接切换至外部 PaddleOCR API
  - 外部 API 失败时默认回退本地 `ocrmypdf`（可关闭回退）

### 修复

- 🐛 修复 `backend=paddle_api` 场景下的本地依赖误校验
  - 不再在程序启动时无条件检查 `ocrmypdf`
  - 仅在实际走本地后端或回退本地时才校验本地依赖

### 文档完善

- 📝 更新 `SKILL.md`：补充外部 PaddleOCR API 预留接口说明、调用示例与故障排查
- 📝 更新 `TASKS.md` 与 `DECISIONS.md`：记录接口预留任务与技术决策

---

## [2.3.0] - 2026-02-11

### 新增

- ✨ 新增统一双层 PDF 入口脚本 `scripts/pdf-ocr.py`
  - 基于 `ocrmypdf` 的生产主路径
  - 支持 `skip / redo / force` 三种 OCR 模式
  - 支持 `--preprocessed` 场景，避免重复 `rotate/deskew`
  - 支持 `pdf/pdfa` 输出、优化等级、大图跳过阈值、超时和并行参数

### 改进

- 🔄 重构 `scripts/pdf-preprocess-ocr.py`
  - 由原 RapidOCR 叠层方式，切换为“预处理 + ocrmypdf”流程
  - 保留自动解密能力，支持预处理跳过页/裁剪/尺寸恢复等参数
  - OCR 阶段统一调用 `scripts/pdf-ocr.py`，降低路径分裂

### 技术优化

- 🧭 完成双层 PDF 主路径收敛：默认生产方案统一为 `ocrmypdf`
- 📝 更新 `SKILL.md` OCR 命令示例与故障排查，减少误用旧脚本的风险
- 📌 将遗留 `pdf-ocr-rapid.py` 明确标注为历史兼容脚本（非默认生产路径）

---

## [2.2.1] - 2026-02-11

### 新增

- ✨ 新增优化方案文档 `OPTIMIZATION-PLAN.md`
  - 明确两大优先方向：图像预处理升级、双层 PDF 质量稳定
  - 给出分阶段路线（P0 基线、P1 预处理、P2 双层 PDF 主路径、P3 发布治理）
  - 增加量化验收指标（搜索命中率、CER、单页耗时、输出体积）

### 改进

- 🧭 明确“双层 PDF 主路径收敛”策略：以 `ocrmypdf` 作为默认生产方案
- 🗂️ 更新任务拆分，新增 v2.3.0 优先任务清单，聚焦你最关注的双层 PDF 与畸变矫正

### 文档完善

- 📝 在 `DECISIONS.md` 新增 DEC-004，记录主路径收敛决策背景、选项与影响

---

## [2.2.0] - 2026-01-29

### 新增

#### PDF 合并与页码功能

- ✨ **PDF 合并工具** (`pdf-merge.py`)
  - 支持合并多个 PDF 文件
  - 可选添加页码序号
  - 两种编号模式：
    - 独立编号（每个文件从 1 开始）
    - 连续编号（全局连续编号）
  - 支持自定义页码位置（6 个位置）
  - 支持自定义字体大小

- ✨ **PDF 页码添加工具** (`pdf-add-page-numbers.py`)
  - 为现有 PDF 添加页码
  - 精确边距控制（毫米单位）
  - 默认设置符合常用配置：
    - 位置：底端右边
    - 字体：Helvetica 常规 15pt
    - 边距：上 10mm/下 5mm/左右 15mm
  - 支持 3 种字体（Helvetica、Times、Courier）
  - 支持 6 个页码位置

### 改进

- 📝 更新触发逻辑说明
  - 明确合并和添加页码时不自动预处理
  - 只有拖入文件或明确说"预处理"时才执行预处理
- 📝 更新 SKILL.md，添加新功能文档和使用示例

### 功能汇总

本技能现包含以下完整功能：

1. **PDF 预处理** - 倾斜矫正、页面旋转、边缘裁剪
2. **PDF OCR** - 为扫描版 PDF 添加可搜索的文字层（双层 PDF）
3. **PDF 添加页码** - 精确控制位置和边距
4. **PDF 合并** - 合并多个文件并可选添加页码
5. **PDF 解密** - 移除 PDF 密码保护
6. **水印去除** - 检测并移除 PDF 中的水印
7. **PDF 压缩** - 压缩 PDF 文件大小

---

## [2.1.0] - 2026-01-26

### 重大变更

- 🚀 **PDF 倾斜矫正算法全面升级** - 基于工程实践指南重构

### 新增

#### 核心处理模块

- ✨ 创建 `pdf-preprocess-core.py` 统一预处理流水线
  - PDF 类型自动检测（扫描件/电子原生/混合型）
  - 级联式处理：类型检测 → 90° 旋转检测 → 微小倾斜矫正
  - Tesseract OSD 集成（90° 倍数旋转检测）
  - 多算法冗余：minAreaRect → 投影剖面法 → 霍夫变换
  - 智能边界情况处理（页眉页脚排除、角度平滑）

#### 倾斜矫正 v2.1

- ✨ `pdf-deskew.py` 重构，使用新的核心模块
- 🎯 **页面跳过功能** (`--skip-pages`) - 避免误判正常页面
- 🔍 **Dry-run 预览模式** (`--dry-run`) - 处理前检查哪些页会被修改
- 📏 **原始尺寸恢复** - 确保所有页面尺寸一致
- ✂️ **激进裁剪模式** - 旋转后自动裁剪空白边缘
- 📊 **PDF 分析工具** (`pdf-analyze.py`) - 生成处理建议报告

#### 页面旋转 v2.0

- ✨ `pdf-rotate.py` 重构，集成 Tesseract OSD
- 🎯 自动旋转检测置信度控制
- 🔄 Fallback 机制（OSD 失败时使用宽高比检测）

#### OCR 工具改进

- 🔄 **采用 ocrmypdf 作为主要 OCR 解决方案**
  - PyMuPDF 内置字体无法支持中文字符
  - 尝试多种方法（`insert_text`、`insert_textbox`、HTML、字体选择）均无法解决
  - **最终方案**：使用 `ocrmypdf` 工具
- ✨ **ocrmypdf 优势**：
  - 原生支持中文（基于 Tesseract）
  - 自动处理双层PDF结构（文字层在下，图像在上）
  - 智能预处理（自动倾斜矫正、页面旋转）
  - 图像优化功能（减小文件大小 15%+）
  - 支持多语言（`chi_sim+eng`）
- 🗑️ **移除 simple-ocr.py** - 由于中文支持问题已删除
- 🗑️ **移除 RapidOCR 依赖** - 不再需要

### 改进

- 📝 更新 SKILL.md，添加 v2.1 新特性说明和使用示例
- 🗑️ 删除 DEPENDENCIES.md（依赖信息已整合到 SKILL.md）
- ⚙️ 优化默认参数：
  - `skew_threshold`: 0.5°（微小倾斜阈值）
  - `max_skew`: 15°（防止误判）
  - `rotation_confidence`: 0.5（OSD 置信度）
  - `dpi`: 200（平衡质量和速度）

### 技术细节

**级联流水线架构**：

```
PDF 输入 → 类型检测 → 粗矫正(90°) → 精细矫正(<15°) → 裁剪 → 尺寸恢复 → 输出
```

**新增核心类和方法**：

- `PDFPreprocessor` - 统一预处理流水线类
- `PDFType` - PDF 类型枚举（SCANNED/DIGITAL/HYBRID）
- `ProcessingResult` - 处理结果数据类
- `PageAnalysis` - 页面分析结果数据类
- `crop_blank_edges(aggressive=True)` - 激进裁剪模式
- `resize_to_original()` - 原始尺寸恢复

**问题修复**：

- 旋转后页面变大但裁剪不完整 → 添加激进裁剪模式
- 检测算法对正常页面误判 → 添加页面跳过功能
- 所有页面尺寸不一致 → 添加原始尺寸恢复
- 无法预览处理效果 → 添加 dry-run 模式
- **双层 PDF 视觉伪影** → 优化 OCR 过滤和文字层参数

### 依赖变更

**新增可选依赖**：

- `pytesseract>=0.3.10` - Tesseract OSD 支持（90° 旋转检测）
- `pymupdf>=1.23.0` - 矢量文本分析（PDF 类型检测）

**已安装依赖**：

- `rapidocr-onnxruntime` - PDF OCR

---

## [1.0.0] - 2026-01-22

### 重大变更

- 🔄 从 doc-processor 拆分，独立为 pdf-processor 技能
- 🔄 Word 文档转换功能迁移到 word-converter 技能
- 📝 简化依赖，移除 LibreOffice 和 Word 相关依赖

### 新增

- ✨ PDF 压缩功能
  - 新增 `pdf-compress.py` 脚本，压缩 PDF 文件大小
  - 支持多种压缩级别（low、medium、high、maximum）
  - 支持自定义图像质量（1-100）
  - 支持移除元数据以进一步减小文件大小
  - 显示压缩前后大小对比和压缩百分比
  - ⚠️ 压缩功能仅在用户明确请求时执行，不会自动触发

### 功能汇总

本技能整合了以下完整功能：

1. **PDF 预处理** - 倾斜矫正、页面旋转、边缘裁剪
2. **PDF OCR** - 为扫描版 PDF 添加可搜索的文字层（双层 PDF）
3. **PDF 解密** - 移除 PDF 密码保护
4. **水印去除** - 检测并移除 PDF 中的水印
5. **PDF 压缩** - 压缩 PDF 文件大小

### 改进

- 📝 更新 SKILL.md，专注 PDF 处理文档
- 📝 更新 DEPENDENCIES.md，移除 Word 相关依赖
- 📝 明确技能定位：专注 PDF 预处理、OCR、解密、水印去除、压缩

### 技术细节

- 使用 pypdf 进行 PDF 解密、加密检测和压缩
- 使用 RapidOCR 进行本地 OCR 识别和页面方向检测
- 使用 PyMuPDF (pymupdf) 创建双层 PDF、水印检测和移除
- 支持简体中文、繁体中文、英文等 80+ 种语言
- 完整流程：解密 → 去水印 → 旋转 → 矫正 → OCR

---

## 版本说明

### v2.x 系列 - PDF 预处理优化

- **v2.1.0** (2026-01-26) - 倾斜矫正算法全面升级，新增级联流水线和智能边界处理
- **v2.0.0** (2026-01-22) - 初始版本，从 doc-processor 拆分

### v1.x 系列 - doc-processor

- **v1.0.0** - PDF 预处理基础功能（倾斜矫正、页面旋转、边缘裁剪）
- **v0.2** - PDF OCR 功能（双层 PDF、页面方向检测）
- **v0.3** - PDF 解密和水印去除功能
- **v0.4** - PDF 压缩功能
