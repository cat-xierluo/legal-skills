# 变更记录

## [1.3.2] - 2026-06-03

### 优化
- archive 不再单独保存输入副本：移除 `archive/<时间戳>_<名称>/input/` 目录及对应的 `shutil.copy2` / `source_url.txt` 写入逻辑。
- 输入文件元信息继续保留在 `metadata.json` 的 `source` 字段：本地文件记录 `path` / `sha256` / `size_bytes`；远程 URL 记录原始字符串。
- 同步更新 `SKILL.md` 与 `references/output_schema.md` 的 archive 结构说明。

### Reason
- 现状：`skills/legal-ocr/archive/` 累计 649 MB；6 个 archive 平均 100 MB+，主要来自 `input/` 下的原 PDF 副本。
- 风险：随着 OCR 任务增多本地磁盘会持续膨胀；archive 已在 `.gitignore` 内，不会被 push，但本地占用无法控制。
- 取舍：放弃 archive 内"可重放原文件"的能力，换取固定占用；如需重新转换，使用 `metadata.json.source.path`（本地）或 `metadata.json.source.raw`（URL）重跑即可。

## [1.3.1] - 2026-05-20

### 文档完善
- 精简 SKILL.md frontmatter description，仅保留 OCR/扫描识别/文档识别等功能触发条件和必要边界，不再描述后端路由等实现细节。
- 同步 README 与 marketplace 中的 `legal-ocr` 简介。

## [1.3.0] - 2026-05-20

### 改进
- 将技能定位调整为“通用 OCR + 法律材料自动增强”：用户需要 OCR、扫描识别、图片文字识别或文档识别时可直接调用，非法律材料默认保持通用 OCR 输出。
- `LEGAL_OCR_LEGAL_TERMS` 默认改为 `auto`，仅在检测到法院文书、案号、当事人标签、判决/裁定结构等法律信号时启用法律术语优化。
- 新增 `--legal-terms auto|always|never` 参数，支持单次自动、强制或关闭法律术语优化。
- `result.json` 与 `metadata.json` 新增法律上下文检测记录，便于复核为什么启用或跳过法律增强。

### 文档完善
- 更新 `SKILL.md` 触发条件，明确可替代普通 OCR 场景，并说明法律增强的自动检测机制。
- 更新 `.env.example`、`references/output_schema.md` 和 `references/legal_terms.md`，同步 `auto` 模式说明。

## [1.2.2] - 2026-05-20

### 技术优化
- 按 `skill-lint` 规范扁平化 `scripts/` 目录，移除 `scripts/backends/` 与 `scripts/postprocess/` 子目录。
- 优化脚本依赖防护，缺少 `httpx` 或 `pypdfium2` 时给出清晰安装提示。
- 优化 `SKILL.md` frontmatter 描述，明确触发场景和不适用边界。

### 文档完善
- 补充 Python 包依赖表和输入/输出说明。

## [1.2.1] - 2026-05-20

### 改进
- 法律术语断字合并支持跨单个换行，处理 `本院认\n为`、`人\n民\n法\n院` 等 OCR 断行场景。
- 新增保守型 OCR 硬换行整理，合并明显属于同一中文段落的物理换行，同时保留标题、当事人标签、编号、表格和 Markdown 结构。
- 扩充常见法律词表，补充审理经过、争议焦点、执行标的、案件受理费、迟延履行期间等常见文书词。
- 新增 `LEGAL_OCR_LINE_MERGE` 与 `--no-line-merge`，可关闭硬换行整理。

### 文档完善
- 补充换行整理边界说明，强调不做事实改写和过度纠错。

## [1.2.0] - 2026-05-20

### 新增
- 新增保守型法律术语优化后处理，默认修正常见 OCR 断字、异体字和法律文书标签格式。
- 新增自定义术语文件支持，可通过 `LEGAL_OCR_CUSTOM_TERMS_PATH` 加载 JSON 替换表。
- 新增 `--no-legal-terms` 参数，可单次跳过法律术语优化。
- 新增 `references/legal_terms.md` 与 `config/legal_terms.example.json`，说明默认处理范围和自定义格式。

### 改进
- 后处理顺序调整为先做法律术语优化，再做标题和条文结构整理，提升 `本院认为`、`判决如下` 等文书结构识别稳定性。
- 法律术语替换记录写入 `postprocess_log.json`，并保留 `result_raw.md` 便于人工复核。

## [1.1.1] - 2026-05-20

### 改进
- 自动路由调整为配置优先：只配置 PaddleOCR 时优先使用 PaddleOCR，只配置 MinerU Token 时所有支持输入统一走 MinerU，两套 API 都配置时再按材料类型选择最优后端。
- 两套 API 都配置时保留候选后端；首选后端失败后可自动尝试下一后端。
- 转换失败记录新增错误分类，支持识别额度/频率限制、鉴权失败、轻量接口超限、不支持类型、超时和网络问题。

### 文档完善
- 补充自动分流说明，明确当前额度判断来自 API 响应码和错误信息，暂未接入独立额度预检接口。

## [1.1.0] - 2026-05-20

### 新增
- 复制旧 `paddle-ocr` 与 `mineru-ocr` 的本地 `.env` 配置到 `legal-ocr/config/.env`，保留原 Token 和后端设置；该文件继续被 Git 忽略。
- PaddleOCR 后端新增 `pdf-processor` 同源能力：兼容 `PADDLE_OCR_API_ENDPOINT` / `PADDLE_OCR_API_KEY` / `API_URL` / `TOKEN` 变量别名。
- PaddleOCR 后端新增异步任务协议支持，可调用 `/api/v2/ocr/jobs` 并轮询 JSONL 结果。
- 新增 `PP-OCRv5` 与 `PaddleOCR-VL-1.5` 模型选择，支持 `--paddle-model` 参数和 `PADDLEOCR_MODEL` 配置。
- 新增 PaddleOCR optionalPayload 扩展：支持 VL 版面检测、图表识别、方向/去畸变、文本行方向、可视化和额外 JSON payload。

### 改进
- `checktoken` / smoke test 可识别 PaddleOCR 旧变量和 `pdf-processor` 变量别名。
- PaddleOCR archive 中记录 API 协议、模型、轮询参数和 payload 配置。

## [1.0.0] - 2026-05-20

### 新增
- 新增 `legal-ocr` 统一 OCR Skill，整合 PaddleOCR 与 MinerU 双后端。
- 新增自动路由：本地 PDF/图片默认走 PaddleOCR，Office 文档、远程文档 URL 和网页 URL 默认走 MinerU。
- 新增统一 Python 主入口 `scripts/convert.py`，支持 `--backend`、`--output`、`--pages`、`--archive-name`、`--no-archive`、`--no-post-process`、`--model`。
- 新增 MinerU Python 后端，覆盖 local/token、local/light、remote/token、remote/light 四条转换链路。
- 新增 PaddleOCR Python 后端，保留本地 PDF 自动分批、图片提取和 Markdown 输出能力。
- 新增统一 archive 结构，保留输入、最终 Markdown、原始 Markdown、结构化 JSON、后端原始结果和元数据。
- 新增基础法律后处理，支持空行清理和简单法律标题结构识别。
- 新增 `scripts/smoke_test.py` 和 JXA 兼容入口 `scripts/convert.js`。

### 文档完善
- 新增 `SKILL.md`、`references/output_schema.md`、`TASKS.md`、`DECISIONS.md` 和 `LICENSE.txt`。
- 新增统一 `.env.example`，保留 `PADDLEOCR_*` 与 `MINERU_*` 变量名并补充 `LEGAL_OCR_*` 设置。

### 待办事项
- 增加真实法律 PDF、病历、票据和网页 URL 的回归样本。
- 评估复杂法律词典纠错、印章标注和图表标注规则。
