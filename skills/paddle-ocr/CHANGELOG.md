# 变更记录

## [1.1.1] - 2026-04-05

### 改进
- 将对外配置字段统一收敛为官方命名：`PADDLEOCR_DOC_PARSING_API_URL` 与 `PADDLEOCR_ACCESS_TOKEN`。
- `SKILL.md` 与 `.env.example` 删除旧别名说明，避免用户在配置时产生歧义。

### 技术优化
- `scripts/lib.py` 不再从旧别名字段读取 API 地址和 Token，配置接口与官方保持一致。

### 文档完善
- 更新配置章节，明确只按官方字段填写 `.env`。

## [1.1.0] - 2026-04-05

### 新增
- 新增 `scripts/lib.py`，统一配置读取、接口调用、稳定 JSON envelope 与错误包装。
- 新增 `scripts/layout_caller.py`，支持直接调试底层 JSON 结果。
- 新增 `scripts/split_pdf.py`，支持 PDF 页码提取与自动分批。
- 新增 `scripts/smoke_test.py`，支持配置检查与 API 连通性自检。
- 新增 `scripts/optimize_file.py`，支持对扫描图片做压缩优化。
- 新增 `references/output_schema.md`，说明底层 JSON envelope 与 archive 结构。
- 新增 `TASKS.md` 与 `DECISIONS.md`，补齐技能级协作文档。
- 新增 `LICENSE.txt`，统一许可证文件名与版权信息。

### 改进
- 将技能定位收敛为“面向法律 PDF / 扫描件的 Markdown + archive 工作流”。
- 默认输出保持为 Markdown 文件，并在技能内部保留可追溯 archive。
- 为卷宗、病历、证据材料等长文档增加自动分批逻辑，优先保障稳定性。
- `convert.js` 改为兼容层，转而调用 Python 主链路，不再内置核心 OCR 逻辑。
- `SKILL.md` 重写为以法律文档场景为中心的说明文档，并补充适用/不适用场景。

### 技术优化
- 移除旧的固定 `test/paddle-ocr` 路径依赖，改为基于脚本位置动态推导 skill 根目录。
- 用 `pypdfium2` 替代 Ghostscript 方案，降低系统依赖。
- 统一支持新旧环境变量字段，兼容已有 `.env` 配置。
- 归档目录新增 `metadata.json`、批次 JSON 和输出结构说明，增强复核与追溯能力。

### 文档完善
- 将配置说明更新为 `PADDLEOCR_DOC_PARSING_API_URL` / `PADDLEOCR_ACCESS_TOKEN` 主字段。
- 补充大文件策略、页码范围、主入口与底层入口的分工说明。

### 待办事项
- 增加真实法律 PDF 样本的回归测试集。
- 评估页眉页脚、印章、批注的后处理去噪规则。

## [1.0.0] - 2026-01-15

### 新增
- 初始版本发布。
- 支持将 PDF 和图片转换为 Markdown。
- 集成 PaddleOCR 文档解析接口。
- 支持 OCR、表格识别、公式识别与图片提取。
- 增加基础 archive 归档能力。

### 技术优化
- 使用 JXA 与 Python 组合实现基础转换流程。
- 支持 Base64 上传与 `fileType` 自动检测。

### 文档完善
- 提供基础配置说明、故障排除和与 MinerU 的差异说明。
