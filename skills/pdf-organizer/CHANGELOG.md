# 变更日志

## [0.5.0] - 2026-05-31

### 新增

- 将"单纯重命名"纳入核心场景：对不需要拆分或合并的 PDF，直接根据内容识别结果规范命名。
- SKILL.md 定位、输入、工作流程和 Manifest 部分补充重命名场景说明和示例。
- `references/organize-manifest-schema.md` 新增重命名示例。

### 改进

- 核心职责从 6 条扩展为 7 条，明确"拆分、合并、重命名"三种操作模式。
- frontmatter description 新增"重命名"关键词。

## [0.4.2] - 2026-05-31

### 改进

- `suggested_downstream` 从具体 Skill 名称改为按文书类别的路由标签（合同审查、诉讼分析、材料整理、复核），下游消费方根据标签和当前上下文自行映射。
- `recommended_next_steps` 同步去除具体 Skill 名称，改为描述性建议。
- `SKILL.md` 下游交接章节重写，明确标签路由策略。

## [0.4.1] - 2026-05-29

### 新增

- 新增 `handoff.json` 归档输出，面向下游 Skill 暴露整理后的文书清单、类型、页码、主体、置信度和建议接力 Skill。

### 改进

- `run_meta.json` 增加 `handoff_file`，便于快速定位交接文件。
- `SKILL.md` 补充与 `contract-copilot`、`litigation-analysis`、`legal-material-organizer`、`new-case` 的协作流向。

## [0.4.0] - 2026-05-29

### 新增

- 新增 `--inspect` 页面检查能力，输出每页文字量、疑似标题、页码、日期、主体候选、旋转状态和边界信号。
- 新增 `--suggest-manifest` 草稿生成能力，可基于页面检查结果生成待复核的 `organize_manifest.json`。

### 改进

- 将流程升级为“脚本先整理页面证据 + AI/人工复核 manifest + 脚本执行”，减少直接凭文件名或整篇文本判断边界的风险。
- 自动草稿默认保守使用 `待确认` 和 `needs_review: true`，避免把低置信度主体写入最终文件名。

## [0.3.2] - 2026-05-29

### 新增

- 新增 PDF 文字层预检：脚本支持 `--check-text-layer`，并在默认 `strict` 模式下阻止对无可检索文字层的 PDF 做内容整理。
- manifest schema 新增 `text_check` 和 `require_text_layer` 字段，允许纯旋转/复制场景关闭文字层检测。

### 改进

- 在 `SKILL.md` 工作流程中明确：按内容拆分、合并和命名前，应先确认 PDF 已经由 PDF Processor 处理为双层 PDF。

## [0.3.1] - 2026-05-29

### 改进

- 精简 `SKILL.md` frontmatter description，保留拆分、合并、命名、旋转、倾斜校正和排除项等核心触发边界。

## [0.3.0] - 2026-05-29

### 新增

- Skill 正式更名为 `pdf-organizer`，定位从“PDF 拆分重命名”扩展为“法律 PDF 文书整理”。
- 新增按内容合并能力：manifest 支持 `source_items` / `input_files`，可把被拆散的同一份文书恢复成一个 PDF。
- 新增轻量方向预处理能力：manifest 支持 `rotate`，可对输出 PDF 做 90/180/270 度旋转。
- 新增可选倾斜校正能力：manifest 支持 `deskew`，在系统安装 `ocrmypdf` 时可执行轻量 deskew。
- 脚本更名为 `scripts/pdf_organizer.py`，archive 输出改为 `organize_manifest.input.json`、`organize_manifest.resolved.json` 和 `organize_report.md`。
- 参考文档更名为 `references/organize-manifest-schema.md`，补充拆分、合并、旋转字段说明。

### 改进

- 明确本 Skill 与 PDF Processor 的边界：本 Skill 聚焦文书逻辑整理，复杂 OCR、压缩、裁边和图像增强仍交给 PDF Processor。

## [0.2.2] - 2026-05-29

### 改进

- 默认文件名分隔符从下划线改为空格；脚本会将建议文件名中的下划线规范化为空格。
- 同名冲突后缀从 `_1`、`_2` 改为 ` 1`、` 2`。
- 将起诉状表格版本表述调整为“要素式起诉状”，文件名末尾使用“要素式”。

## [0.2.1] - 2026-05-29

### 改进

- 明确合同类文件命名的主体选择规则：优先写客户、相对方和案由/法律关系，不默认写我方律所或承办律师。
- 更新委托代理合同命名示例，推荐 `委托代理合同 客户与相对方 案由.pdf`。

## [0.2.0] - 2026-05-29

### 新增

- 新增 `archive/` 机制：执行后自动创建 `archive/YYYYMMDD_HHMMSS_{来源名}/`，保存输入 manifest、resolved manifest、执行报告和运行元数据。
- 新增 `--archive-root` 参数，允许覆盖归档根目录。
- 新增 `archive/.gitignore` 和 `.gitkeep`，默认忽略运行归档内容。

### 改进

- 交付目录默认只输出最终 PDF，不再写入 JSON、manifest 或运行报告。

## [0.1.1] - 2026-05-29

### 改进

- 调整默认命名规则：不再默认添加顺序号，优先使用“文书名称_关键主体_补充区分”。
- 新增 `references/recognition-rules.md`，沉淀合同、授权委托书、律师事务所函、普通版民事起诉状、要素式民事起诉状等基础识别规则。
- 明确同为“民事起诉状”的多个版本要根据版式和用途继续区分，不能只因标题相同而合并。

### 验证

- 使用桌面示例 `20260529145736_已处理.pdf` 完成 16 页总 PDF 的按内容拆分测试，输出 6 份 PDF。

## [0.1.0] - 2026-05-29

### 新增

- 新增 `pdf-split-renamer` 私有 Skill，聚焦 OCR 后合并 PDF 的内容拆分与规范命名。
- 新增 `scripts/split_and_rename.py`，支持按 manifest 从整份 PDF 拆页，或复制已拆分 PDF 并重命名。
- 新增 `references/manifest-schema.md`，定义 `split_manifest.json` 顶层字段和 segment 字段。
- 新增技能级 `TASKS.md`、`DECISIONS.md`、`LICENSE.txt`。

### 改进

- 将该流程从通用 PDF 处理与案件材料整体整理中拆出，先以私有 Skill 方式验证。

### 待办事项

- 使用真实但脱敏的 OCR PDF 验证命名规则和边界识别流程。
- 评估后续是否并入 PDF 处理工具的 OCR 后处理阶段。
