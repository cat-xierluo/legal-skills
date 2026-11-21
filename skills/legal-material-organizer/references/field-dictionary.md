# Manifest 字段字典

**版本**: v0.17.0

## 字段治理原则

1. `materials_manifest.json` 是本案件材料包的局部元数据事实源，源材料目录中的 Markdown 是给律师阅读的投影。
2. `material_id` 是后台稳定主键，只写入运行时元数据 archive JSON；律师交付物、整理后文件名和报告只展示 `display_code`。
3. 固定语义使用结构化字段；不稳定或实验性内容统一放入 `extra_json`，避免后续出现 `importance`、`value_level` 等同义漂移。
4. OCR、ASR、视觉理解、文本清洗等衍生内容不直接混入 `materials` 主记录，应通过 `variants` 和 `processing_runs` 追踪。
5. 不在 Skill 包或运行时元数据 archive 保存客户材料文件、OCR/ASR 全文；解压结果和处理变体进入独立 work 目录。
6. 顶层 `archive_dir` 与 `work_dir` 保持分离，并且都不要指向 Skill 包内 `archive/`。

## 顶层结构

| 字段 | 类型 | 含义 |
|------|------|------|
| `materials` | array | 单份材料入库记录，以 `material_id` 为主键 |
| `material_sets` | array | 需要共同读取的一组材料，如聊天沟通组、文档材料组、待人工复核组 |
| `variants` | array | 同一材料的不同可读形态，如原始文件、OCR Markdown、ASR 转写、视觉摘要、清洗稿 |
| `processing_runs` | array | 解压、OCR、ASR、视觉理解、文本清洗等处理过程记录 |
| `follow_up_candidates` | array | 后续候选动作，如补材料、重 OCR、人工复核、交给后续法律分析 Skill |

顶层运行路径：

| 字段 | 含义 |
|------|------|
| `archive_dir` | 本次运行的结构化元数据目录 |
| `work_dir` | 解压结果等真实材料工作副本目录 |

## `materials` 核心字段

| 字段 | 含义 | 说明 |
|------|------|------|
| `material_id` | 后台稳定主键 | 格式 `M-000001`，不进入 Markdown 报告 |
| `display_code` | 前台展示编号 | 格式 `A001/B003/D005`，按参照度排序生成，可随整理方案变化 |
| `reference_level` | 参照度等级 | A/B/C/D，服务材料管理和排序，不等同法律证据评价 |
| `reference_score` | 参照度分数 | 0-100，区内排序使用 |
| `reference_basis` | 参照度依据 | 说明为什么给出该等级或分数 |
| `material_key` | 材料指纹键 | 通常为 `sha256:{hash}`，用于增量匹配 |
| `scan_order` | 初始扫描顺序 | 展示编号排序的兜底依据 |
| `legacy_ids` | 旧编号 | 迁移旧 manifest 时保存 `M-XXX`、`D-XXX`、`A-XXX` 等旧值 |
| `material_set_id` | 所属材料组 ID | 对应 `material_sets.set_id` |
| `material_set_name` | 所属材料组名称 | 用于 Markdown 清单展示 |
| `primary_variant_id` | 主变体 ID | 默认指向原始文件变体 |
| `primary_readable_variant_id` | 主可读变体 ID | 文本、Markdown 等可直接读取材料默认指向原始变体；PDF、图片、音视频处理前可为空 |
| `readability_status` | 可读性状态 | 表示当前是否已有可直接读取内容 |
| `processing_need` | 待处理动作 | 表示是否需要 OCR、ASR、解压、人工复核等 |
| `parent_material_id` | 父级材料 | 压缩包、导出包等来源链使用 |
| `source_chain` | 来源链 | 记录从外层容器到当前材料的路径 |
| `display_path` | 当前展示路径 | 整理后的当前路径；未整理时为原始相对路径 |
| `original_display_path` | 初始路径 | 首次入库时的原始相对路径，不随整理覆盖 |
| `organized_path` | 整理后路径 | Step 6 实际整理后的路径 |
| `needs_human_review` | 是否需人工复核 | 不确定、损坏、无法读取或安全拒绝时为 true |
| `review_reasons` | 复核原因 | 结构化列明为什么需要人工确认 |
| `extra_json` | 扩展字段 | 放置暂不稳定的实验性内容 |

## `material_sets`

| 字段 | 含义 |
|------|------|
| `set_id` | 材料组 ID，如 `set_documents` |
| `set_name` | 材料组名称，如 `文档材料组` |
| `set_type` | 分组类型，当前默认 `reading_set` |
| `purpose` | 共同读取该组材料的用途说明 |
| `material_ids` | 组内后台材料 ID 列表 |
| `display_codes` | 组内展示编号列表 |
| `summary` | 组级理解摘要，初次扫描可为空 |
| `extra_json` | 扩展字段 |

## `variants`

| 字段 | 含义 |
|------|------|
| `variant_id` | 变体 ID，如 `variant_M_000001_original` |
| `material_id` | 所属材料 ID |
| `parent_variant_id` | 来源变体 ID，原始文件为 null |
| `variant_kind` | 变体类型 |
| `file_path` | 变体文件路径 |
| `file_hash` | 变体文件指纹 |
| `generator` | 生成者，如 `scan_materials.py`、OCR 或 ASR 工具 |
| `readability_status` | 该变体可读性 |
| `processing_status` | 处理状态 |
| `is_primary` | 是否主变体 |
| `is_primary_readable` | 是否当前首选可读变体 |
| `extra_json` | 扩展字段 |

## `processing_runs`

| 字段 | 含义 |
|------|------|
| `run_id` | 处理运行 ID |
| `material_id` | 被处理材料 ID |
| `candidate_id` | 触发本次处理的预处理候选 ID；外部结果回写时必填 |
| `run_type` | 处理类型 |
| `status` | 运行状态 |
| `producer` | 执行工具或脚本 |
| `input_path` / `output_path` | 输入和输出路径 |
| `input_variant_id` / `output_variant_id` | 输入和输出变体 |
| `started_at` / `completed_at` | 开始和完成时间 |
| `error_message` | 失败原因 |
| `extra_json` | 扩展字段 |

## `follow_up_candidates`

| 字段 | 含义 |
|------|------|
| `candidate_id` | 候选动作 ID |
| `material_id` | 关联材料 ID |
| `display_code` | 律师可见展示编号 |
| `candidate_type` | 候选动作类型 |
| `title` | 简短标题 |
| `suggested_action` | 建议动作 |
| `priority` | 候选优先级 |
| `status` | 当前状态，初始为 `candidate` |
| `reason` | 触发原因 |
| `extra_json` | 扩展字段 |

## 工具中立的处理交接合同

运行 `scripts/material_processing_handoff.py export`，从仍处于候选状态的 `preprocess_material` 生成待处理任务。任务只提供输入路径、`processing_need`、可接受的能力类型和回写字段，不指定具体 Skill、模型、服务或内部脚本。

处理结果 JSON 的公共字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `schema_version` | int | 固定为 `1` |
| `material_id` | str | 必须与待处理任务一致 |
| `candidate_id` | str | 必须引用该材料的预处理候选 |
| `status` | str | `completed`、`failed` 或 `needs_review` |
| `capability` | str | 实际使用的能力类型，不记录固定工具依赖 |
| `producer` | str | 本次执行者的审计标签，由运行环境填写 |
| `started_at` / `completed_at` | str（可选） | ISO 时间；省略时由回写脚本生成 |
| `extra_json` | object（可选） | 不稳定的扩展元数据，不放材料正文 |

`capability` 可使用 `ocr`、`asr`、`visual_understanding`、`text_extract`、`web_capture`、`clean_markdown` 或 `other`。压缩包展开由 `scan_materials.py` 自身记录为 `extract` 运行；成功展开后重新编目内部材料，不通过可读变体回写合同登记目录。

`completed` 还必须包含：

| 字段 | 说明 |
|------|------|
| `output_path` | 已存在的普通文件，必须位于 manifest 的 `work_dir` 内，不能是符号链接 |
| `variant_kind` | 受控的变体类型 |
| `readability_status` | 仅可为 `readable` 或 `partial` |
| `text_quality` | 可选的质量说明或量化值 |

`failed` 或 `needs_review` 必须包含非空 `error_message`，且不得登记 `output_path` 或 `variant_kind`。结果 JSON 只接受本节列明的字段；`extra_json` 最大 8KB，且不得包含材料正文、完整转写或 Markdown 全文。提取全文、转写稿、图片或其他真实材料内容继续留在 `work_dir`。

## 受控值

### `reference_level`

| 值 | 含义 |
|----|------|
| `A` | 活文档，优先阅读和引用 |
| `B` | 常查材料，经常作为背景或支撑 |
| `C` | 存档材料，主要用于留痕 |
| `D` | 待激活材料，未处理、未识别或暂不确定 |

### `readability_status`

| 值 | 含义 |
|----|------|
| `readable` | 已有可直接读取文本 |
| `partial` | 部分可读 |
| `not_readable` | 当前不可读 |
| `failed` | 处理失败 |
| `unknown` | 尚未判断 |
| `not_applicable` | 不适用 |

### `processing_need`

| 值 | 含义 |
|----|------|
| `none` | 暂无待处理动作 |
| `need_extract` | 需要解压或展开容器 |
| `need_ocr_or_visual` | 需要 OCR 或视觉理解 |
| `need_asr` | 需要音视频转写或关键帧理解 |
| `need_text_extract` | 需要文档正文提取 |
| `need_web_capture` | 需要网页留痕 |
| `need_review` | 需要人工复核 |

### `variant_kind`

| 值 | 含义 |
|----|------|
| `original` | 原始文件 |
| `ocr_markdown` | OCR Markdown |
| `audio_transcript` | ASR 转写 |
| `visual_summary` | 视觉理解摘要 |
| `clean_markdown` | 清洗稿 |
| `word_export` | Word 导出 |
| `other` | 其他 |

### `processing_runs.run_type`

| 值 | 含义 |
|----|------|
| `extract` | 解压或展开容器 |
| `ocr` | OCR |
| `asr` | 音视频转写 |
| `visual_understanding` | 视觉理解 |
| `text_extract` | 文档正文提取 |
| `clean_markdown` | 文本清洗 |
| `web_capture` | 网页读取或留痕 |
| `other` | 其他工具中立处理能力 |

### `processing_runs.status`

| 值 | 含义 |
|----|------|
| `completed` | 已生成可登记的结果；部分可读结果仍需转人工复核 |
| `failed` | 处理失败并记录原因 |
| `needs_review` | 无法自动确认结果，需要人工复核 |

### `follow_up_candidates.candidate_type`

| 值 | 含义 |
|----|------|
| `preprocess_material` | 后续预处理 |
| `human_review` | 人工复核 |
| `supplement_request` | 补材料 |
| `downstream_skill` | 交给后续法律分析 Skill |

### `follow_up_candidates.status`

| 值 | 含义 |
|----|------|
| `candidate` / `pending` / `retry` / `in_progress` | 尚可导出的待处理候选 |
| `completed` | 已有完整可读结果，并完成引用闭环 |
| `failed` | 处理失败，必须同时保留人工复核候选 |
| `needs_review` | 只有部分结果或结果无法自动确认 |
| `dismissed` / `cancelled` | 经确认后不再处理 |

### `extra_json.chat_html`（v0.12.0 引入）

| 字段 | 类型 | 说明 |
|------|------|------|
| `recognized` | bool | 是否通过 chat-html 形态识别 |
| `downloader` | str | 当前实现版本（`SKILL_VERSION` 常量值） |
| `resource_count` | int | 抽取到的资源总数 |
| `counts_by_kind` | dict {kind: int} | 按 download / image / video 分组计数 |
| `resources` | list[dict] | 每条资源的 resource_id / kind / url / display_filename / context |
| `downloads` | list[dict]（可选） | 仅在 `--chat-html-download` 时写入，每条资源的 status / path / attempts / bytes / error |
| `download_dir` | str（可选） | 下载目录绝对路径 |

## 变更历史

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| v0.17.0 | 2026-11-21 | 新材料统一入库，整理时优先适配既有案件结构 |
| v0.16.1 | 2026-11-19 | chat-html 下载增加 DNS 公网绑定与重定向复核 |
| v0.16.0 | 2026-11-19 | 公开化候选加入材料处理套件，并补充匿名混合材料示例 |
| v0.15.0 | 2026-08-01 | 增加工具中立的处理任务与结果回写合同，固定成功、失败和部分可读结果的闭环字段 |
| v0.14.0 | 2026-07-30 | 增加材料清单完整性、存储分离和不确定性路由的机器校验合同 |
| v0.13.0 | 2026-07-30 | 分离元数据 archive 与真实材料 work 目录，Skill 包不再留存运行材料 |
| v0.12.0 | 2026-07-12 | 新增 `extra_json.chat_html` 段，固定 chat-html 子路径抽取资源、计数与下载结果字段 |
| v0.11.0 | 2026-05-20 | 新增局部 registry 字段字典，固定 material_sets、variants、processing_runs、follow_up_candidates 语义 |
