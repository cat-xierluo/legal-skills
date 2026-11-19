---
name: legal-material-organizer
description: 对律师收到的混合案件材料执行清点、解包、处理分流、内容注解、归类命名和结构化交接。本技能应在用户要求“整理案件材料”“生成材料清单/说明”“理解后归档”，或输入包含目录、压缩包、聊天导出、图片、PDF、音视频、办公文档等多源材料时使用。不要用于直接形成案情结论、争议焦点、证据证明目的或正式法律意见；只需处理单个文件时交给当前环境中合适的专项能力。
license: CC-BY-NC
metadata:
  version: "0.16.1"
  author: "杨卫薪律师（微信ywxlaw）"
  homepage: "https://github.com/cat-xierluo/legal-skills"
---

# 法律材料整理

坚持“先理解，后整理”。把混合材料转成可阅读、可追溯、可移交的标准化材料包，但不越界代替案情分析或法律意见。

## 职责边界

执行以下工作：

1. 清点目录、单文件、压缩包和聊天导出件，记录来源链。
2. 为需要预处理的材料选择 OCR、ASR、视觉理解或正文提取能力。
3. 区分材料原文、AI 归纳和待人工确认事项。
4. 生成材料清单、文件夹级材料说明和根级综合整理说明。
5. 经用户确认后归类、移动或重命名，并回写路径映射。

不要执行以下工作：

- 不直接判断案件事实成立与否、争议焦点、证明目的、责任或诉讼策略。
- 不把内容注解写成正式法律意见、起诉状、答辩状或代理词。
- 不对无法辨认的主体、日期、金额、文件性质或材料关系作确定性推断。
- 不在未确认范围内上传、发送、公开或跨项目复制客户材料。

## 输入

### 必需输入

- 一个用户明确指定的本地文件、目录、压缩包或聊天导出件。
- 用户希望执行的范围：仅清点、清点并理解、或理解后整理。

### 可选上下文

| 字段 | 用途 |
|------|------|
| 案件类型 | 帮助识别材料常见角色，不用于直接下结论 |
| 当事人角色 | 区分材料来源方和沟通对象 |
| 核心事项 | 帮助生成中性注解 |
| 需求方材料清单 | 用于核对缺项和完整性 |

缺少上下文时仍可做客观清点和通用摘要；需要上下文才能解释的内容标记“待人工确认”。

## 输出与存储

### 人工交付物

默认只在源材料目录写入 Markdown：

- `材料清单.md`
- `{文件夹名称} - 材料说明.md`
- `{源目录名称} - 材料综合分析.md`

这些文件只展示 `display_code`（如 `A001`、`B003`），不展示后台 `material_id`。

### 元数据归档与工作目录

把元数据与真实材料工作副本分开：

```text
<源材料父目录>/
├── <源材料>/
└── .legal-material-organizer/<源材料名称>/
    ├── archive/
    │   └── YYYYMMDD_HHMMSS_<名称>/
    │       ├── materials_manifest.json
    │       ├── filing_plan.json
    │       ├── renaming_map.json
    │       ├── run_meta.json
    │       └── 材料清单.md
    └── work/
        └── extracted_containers/
```

遵守以下约束：

<!-- skill-lint:constraint STORAGE-SEPARATION -->
- Skill 包内的 `archive/` 只保留 `.gitignore` 与 `.gitkeep`，不得存放真实材料或运行记录。
- 运行时 `archive/` 只保存结构化元数据和 Markdown 投影，不复制图片、录音、视频、PDF、办公文档或 OCR 全文。
- 解压产生的真实文件只进入 `work/`；每次扫描前重建其中的 `extracted_containers/`，避免累计膨胀。
- manifest 仍可能含文件名、路径、指纹和摘要，属于敏感元数据，不要随 Skill 发布或上传。
- 使用 `--archive-dir`、`--work-dir` 可以显式覆盖两个路径。

字段语义以 [references/field-dictionary.md](references/field-dictionary.md) 为准，完整结构见 [references/output-template.md](references/output-template.md)。

## 依赖

### 系统依赖

| 依赖 | 适用功能 | 安装方式 |
|------|----------|----------|
| Python 3.9+ | 扫描、编目、chat-html 抽取 | 系统 Python 或官方安装包 |
| `7z` 或 `unar`（可选） | 经用户确认后解压 RAR/7z | macOS: `brew install sevenzip` 或 `brew install unar`<br>Linux: `sudo apt-get install p7zip-full` |

### Python 包

核心脚本只使用标准库，无需安装第三方 Python 包。RAR/7z 默认只标记为“待外部解压”；确认使用本机外部解压器后，再传入 `--allow-external-extractor`。缺少 `7z`/`unar` 时其他扫描继续执行。

### 权限与安全边界

- 只读取用户明确指定的源材料，写入路径仅限源目录 Markdown 投影、显式指定的 `archive-dir` 与 `work-dir`。
- 可选外部解压器仅以参数数组调用 `7z` 或 `unar`，不通过 shell 拼接命令。
- 清理操作仅限本次运行控制的 `work/extracted_containers/`，不删除源材料或用户其他目录。
- chat-html 下载必须先获得用户确认，仅接受公网 HTTP/HTTPS 或受限 `data:image`；主机名须经 DNS 解析且全部指向公网地址，重定向目标同样复核；其他网络识别、OCR、ASR 或视觉理解由外部能力按其自身权限声明执行。

## 快速开始

先运行编目脚本：

```bash
python3 scripts/scan_materials.py "/path/to/案件材料"
```

常用选项：

```bash
python3 scripts/scan_materials.py "/path/to/案件材料" --no-write-md
python3 scripts/scan_materials.py "/path/to/案件材料" --no-expand-archives
python3 scripts/scan_materials.py "/path/to/案件材料" --allow-external-extractor
python3 scripts/scan_materials.py "/path/to/案件材料" --fresh
python3 scripts/scan_materials.py "/path/to/案件材料" \
  --archive-dir "/path/to/metadata" \
  --work-dir "/path/to/work"
```

该脚本只负责扫描、解包、编目和 chat-html 资源识别；不自动完成 OCR、ASR、视觉理解、批量移动或重命名。

## 工作流程

### 1. 确认范围与副作用

1. 确认输入路径、材料范围和是否包含多个案件。
2. 确认执行到哪一步；用户说“只要 OCR”“不用整理”时跳过移动与重命名。
3. 在下载外链、批量移动、批量重命名或创建文件夹快照前说明目标路径和影响。
4. 提醒含个人信息、商业秘密或未脱敏聊天记录的材料不要直接对外发布。

### 2. 扫描、拆包与编目

运行 `scripts/scan_materials.py`，检查退出码和真实生成物。

为每份材料维护：

- `material_id`：后台稳定身份，仅保存在 manifest。
- `display_code`：人工交付物中的展示编号。
- `original_display_path`：首次扫描路径。
- `display_path` / `organized_path`：当前或整理后路径。
- `source_chain`：容器与内部文件的来源关系。

<!-- skill-lint:constraint TRACEABILITY-INTEGRITY -->
每份材料必须使用唯一 `material_id`，并让展示编号、变体、材料组、父子来源和后续候选都引用存在的材料记录。

压缩包保留原包不动。解压内容进入独立 `work/`，不要进入 Skill 包或元数据归档。

### 3. 提取内容

按 [references/material-source-matrix.md](references/material-source-matrix.md) 选择处理能力：

- 图片、截图、扫描 PDF：OCR；必要时补视觉理解。
- 文本型 PDF、Word、PPT、表格：直接提取可读内容。
- 音视频：ASR；必要时补关键帧说明。
- 聊天记录：识别参与者角色、时间范围和话题，不推断未显示身份。
- 网页或外链：先确认是否允许联网和下载，再留存来源与失败状态。

本 Skill 不自行检测 PDF 文字层，也不内置 OCR、ASR、视觉理解、网页读取或办公文档解析。先导出工具中立的待处理任务，再交给当前环境中合适的可用能力；具体能力自行决定识别或提取方法：

```bash
python3 scripts/material_processing_handoff.py export \
  --manifest "/path/to/materials_manifest.json"
```

处理产物必须写入 manifest 所列 `work_dir`。按 [references/field-dictionary.md](references/field-dictionary.md) 准备结果 JSON 后统一回写：

```bash
python3 scripts/material_processing_handoff.py record \
  --manifest "/path/to/materials_manifest.json" \
  --result "/path/to/result.json"
```

<!-- skill-lint:constraint PROCESSING-CLOSURE -->
成功结果必须同时关联材料、预处理候选、处理运行和主可读变体；失败或部分可读结果必须保留原因并进入人工复核。不得仅修改状态字段来冒充处理完成。

<!-- skill-lint:constraint UNCERTAINTY-ROUTING -->
可读性未知、部分可读或仍需预处理的材料，必须生成后续处理候选或明确的人工复核标记。

### 4. 生成材料说明

按文件夹生成 `{文件夹名称} - 材料说明.md`。每条材料至少区分：

1. 原始文件与展示编号。
2. 可回溯的提取文字或内容摘要。
3. AI 归纳，明确标识为“注解”。
4. 识别失败、冲突或不确定项。

自解释文件可只保留提取结果；截图、聊天片段、照片等需要上下文的材料才追加中性注解。不要把“可能关联”写成已证明的事实。

### 5. 汇总与完整性核对

子文件夹完成后再生成父级摘要；全部材料完成后，按 [references/comprehensive-analysis-template.md](references/comprehensive-analysis-template.md) 生成根级综合整理说明。

综合说明只回答：

- 收到哪些材料、来自哪里、当前可读性如何。
- 哪些材料互相关联，依据是什么。
- 哪些材料缺失、重复、损坏、无法识别或需要补充。
- 哪些内容应交给后续案情分析或证据分析 Skill。

### 6. 生成并确认整理计划

先按 [references/organization-and-naming-rules.md](references/organization-and-naming-rules.md) 生成 `filing_plan.json` 和 `renaming_map.json`，再向用户展示变更摘要。

未经用户确认，不批量移动或重命名。执行前确保：

- 压缩包来源保留原包。
- 文件夹来源存在用户认可的快照或其他可恢复方案。
- 目标路径无冲突；冲突时停止并列出清单。
- 不移动来源不明或识别不清的材料。

### 7. 执行整理并回写

确认后再创建分类目录、移动或重命名文件。执行完同步更新：

- `materials_manifest.json`
- `filing_plan.json`
- `renaming_map.json`
- `材料清单.md`
- 受路径变化影响的材料说明

重新扫描实际目录，核对文件总数、相对路径集合和缺失记录；不要只采信计划文件中的 `applied: true`。

## chat-html 专项路径

识别 Cubox、微信、企微或钉钉等聊天 HTML 导出件时，先读取 [references/chat-html-extract.md](references/chat-html-extract.md)。

默认只识别和生成 dry-run 清单：

```bash
python3 scripts/scan_materials.py "/path/to/chat.html" --chat-html-dry-run
```

只有用户确认域名、资源数量和下载目录后，才执行：

```bash
python3 scripts/scan_materials.py "/path/to/chat.html" --chat-html-download
```

下载器只接受公网 HTTP/HTTPS 或受限的 `data:image`，拒绝 `file://`、localhost、私网字面地址、伪造白名单域名和超过 100MB 的单个资源；同名文件使用序号避让，不覆盖既有文件。

## 阻断条件与人工复核

出现以下任一情况时，任务保持未完成：

- 输入路径不存在、扫描退出码非零或关键输出缺失。
- manifest 的材料数量与实际扫描集合不一致且无法解释。
- 解压出现路径穿越、符号链接、硬链接、设备文件或越界写入。
- 下载资源数为 0、下载失败或被拒绝，却未写入复核原因。
- OCR/ASR/视觉理解失败，却把材料标记为已理解。
- 移动或重命名后，文件总数、路径映射或 Markdown 引用无法对账。
- 输出混淆原文、AI 归纳和法律判断。
- 真实材料、运行归档、缓存或具名 benchmark 进入 Skill 发布包。

## 完成验收

交付前执行：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/validate_release.py
python3 scripts/check_material_manifest.py --input "/path/to/materials_manifest.json"
```

公开候选冒烟测试可使用 [examples/mixed-material-pack](examples/mixed-material-pack/README.md)；该示例只包含合成材料，用于验证扫描、manifest 生成和处理任务导出。

并人工核对：

- 所有引用文件可达，`SKILL.md` 不超过 500 行。
- Skill 内 `archive/` 只有 `.gitignore` 与 `.gitkeep`。
- 无 `docs/`、`evals/`、`__pycache__/`、`.DS_Store` 或真实案件材料。
- `version`、CHANGELOG 与脚本版本一致；许可证为 CC BY-NC。
- 源目录交付物、元数据归档和真实材料工作区边界清楚。
- 任何未动态验证的 OCR、ASR、视觉语义或完整性判断标记 `NOT_VERIFIED` 或“待人工确认”。

## 参考文件路由

- 需要字段定义时读取 [references/field-dictionary.md](references/field-dictionary.md)。
- 需要输出结构时读取 [references/output-template.md](references/output-template.md)。
- 需要处理路由与逐步检查时读取 [references/material-processing-checklist.md](references/material-processing-checklist.md)。
- 需要材料类型策略时读取 [references/material-source-matrix.md](references/material-source-matrix.md)。
- 需要命名与整理规则时读取 [references/organization-and-naming-rules.md](references/organization-and-naming-rules.md)。
- 需要根级综合整理说明时读取 [references/comprehensive-analysis-template.md](references/comprehensive-analysis-template.md)。
- 需要 chat-html 识别、白名单和下载规则时读取 [references/chat-html-extract.md](references/chat-html-extract.md)。
