---
name: video-screenshot
description: 视频截图提取与证据线索精筛工具。从微信、小红书、网页、会议等录屏中以有界高召回抽取关键帧，控制截图密度并过滤切换中间态；可用本地 OCR 多锚点和无文字图像主体生成不保存原文的证据线索索引，再为普通或较弱多模态模型提供受预算、封闭类别、非破坏性的分类/概括包，以及只做减法且有覆盖存活门禁的去重审计包。纯文字模型可完成全部本地代码流程。触发词：视频截图、录屏截图、聊天记录截图、证据截图、视频证据线索、抽帧去重、关键帧提取、截图太密、过渡帧、切换页、弱多模态截图审计。不要用于视频压缩、视频剪辑、法律证明力认定或音频提取。
version: "0.8.2"
author: 杨卫薪律师（微信ywxlaw）
homepage: https://github.com/cat-xierluo/legal-skills
license: MIT
---

# video-screenshot — 视频截图提取与精筛

从录屏中提取可追溯的证据截图。默认先在本地执行时间簇择优、内容增量精筛和高置信加载态过滤；只有当前模型支持图像输入且基础结果仍需精简时，才准备少量多模态审计材料。

## 工作流

### 1. 确认输入与输出

取得一个本地视频路径。支持 `.mp4`、`.mov`、`.avi`、`.mkv`、`.webm`、`.flv`、`.wmv`、`.ts`。默认输出到视频同级 `<视频名>_frames/`；如该目录可能含其他材料，显式指定新的 `-o` 目录。

<!-- skill-lint:constraint TRANSACTIONAL-OUTPUT-SAFETY -->
脚本必须先完成参数检查和视频探测，再在目标目录同级的隐藏 staging 中生成完整结果。只有帧、报告、所有权标记和可选归档全部成功后，才一次性替换旧的本工具输出；任一步失败都保留旧结果。输出根目录或其中任一文件是符号链接、目录含未知文件，或已经生成 `_evidence_leads`、`_vision_audit`、`_curated`、`_vision_review.json` 时，拒绝原地覆盖并要求使用新的 `-o`。旧版无所有权标记的结果只有在 `_report.json` 与实际基础帧清单完全一致时才允许兼容替换。

### 2. 运行基础精筛

```bash
# 默认：场景候选 + 自适应时间簇择优 + 图像去重
uv run scripts/extract.py -i <视频路径>

# 聊天记录等文字型录屏：增加本地 OCR 内容增量保护与去重
uv run --with rapidocr-onnxruntime scripts/extract.py -i <视频路径> --ocr-dedup

# 调试漏帧时才保存被丢弃候选；不要作为多模态默认输入
uv run scripts/extract.py -i <视频路径> --keep-drop-candidates --drop-candidate-limit 80
```

默认流程：

1. 用 ffmpeg 场景变化和 2 秒保底采样生成高召回候选；
2. 计算候选帧清晰度、内容质量、相似度、滚动重叠、加载态和拼接风险；
3. 按前后帧形成稳定段与连续运动段；
4. 稳定段选择清晰、完整、停留时间更长的代表帧，不机械保留第一张；
<!-- skill-lint:constraint BASE-HIGH-RECALL -->
5. 前后均有稳定页的短运动段至少保留一张低置信代表帧；只有三帧像素拼合能直接证明是前后页面合成时才自动删除，持续滚动段依据相邻内容重叠自适应调整保留跨度；
6. 自动丢弃高置信居中加载浮层；疑似未完成页只有在 1.25 秒内出现同一页面骨架、主内容明显增加且完整后帧最终被基础层保留时才删除；
7. 用三帧像素拼合与分区覆盖共同估计横向、纵向或缩放切换风险；分区风险只用于提权审计，不单独自动删除；
8. 单帧 `transition` 质量标签只记录风险，不单独删除；再执行 SHA256、dHash、像素差异、SSIM、可选滚动合并和 OCR 内容增量判断。OCR 对短运动段最多检查 24 张高风险图片，并在新增金额、长编号或足量正文时否决近似去重和最小间隔删除；启用 OCR 时关闭未完成页的纯视觉自动删除。

需要调参时读取 `references/strategy-and-params.md`。依赖安装见 `references/setup.md`。

### 3. 检查基础结果

检查：

- `_report.json` 中 `frames` 与实际 `frame_*.jpg` 是否一致；
- `temporal_selection` 的稳定段、运动段、自适应密度和切换丢弃统计；
- 联系表总览中是否仍有左右两页拼接、上下切换中间态或明显重复页；
- 视频开头、结尾、长滚动和关键主体/金额/地址页面是否有覆盖。

不要只因帧数减少就判定准确率提高。基础结果不调用大模型，并在报告中保留 `vision_audit_status=not_prepared`。

### 4. 生成高价值证据线索包

基础结果确认完整后，先用代码生成一个独立的高价值索引；这一步也适用于纯文字模型：

```bash
# 推荐：本地 RapidOCR 多锚点 + 无文字图像主体 + 时序信号
uv run --with rapidocr-onnxruntime scripts/prepare_evidence_leads.py \
  -i <基础输出目录>

# 未安装 OCR 时仍可运行，自动保留图像主体与时序排序
uv run scripts/prepare_evidence_leads.py \
  -i <基础输出目录> --no-ocr
```

脚本生成 `_evidence_leads/evidence_index.json`、最多 24 张线索组成的 4 页大图联系表，以及弱模型可直接填写的 `vision_template.json`。代码只记录主体/资质、商品/作品/服务、交易履行、沟通承诺、公开陈述、评论争议、传播时间线、文书记录等**类别和组合命中计数**；不保存 OCR 原文、企业名、商品名、价格或沟通正文。单个“商品”“消息”等宽泛词不得独立触发类别。

<!-- skill-lint:constraint EVIDENCE-LEADS-NON-DESTRUCTIVE -->
OCR 不是价值总开关。商品外观、包装/标识、作品画面、缺陷状态、经营场所和人物行为等少文字画面，仍通过连续图像主体面积进入线索排序；具体含义留给多模态或人工判断。证据线索阶段只做排序、分类和概括，绝不删除、替换或覆盖基础 `frame_*.jpg`，也不认定真实性、合法性、关联性或证明力。

如果当前模型可读取图片，逐页查看 `evidence_sheet_NNN.jpg`，按 `_evidence_leads/VISION_INSTRUCTIONS.md` 原位填写模板，再应用：

```bash
python3 scripts/apply_evidence_review.py \
  -i <基础输出目录> \
  -r <填写完成的 vision_template.json>
```

应用器只接受封闭类别、可见事实和“可能用途”，拒绝“足以证明”等法律结论，并生成 `_evidence_leads/evidence_review.json`。能力较弱的模型使用默认 2 列大图，不扩大图片预算；不能读图时交付代码排序结果，并明确 `evidence_review` 未执行。详细合同见 `references/evidence-leads.md`。

### 5. 按能力选择去重多模态分支

如果当前模型或工具不能读取图片，停止在基础结果，明确说明视觉审计未执行。不要根据文件名或算法分数伪造图像判断。

如果支持图片，并且用户希望进一步精简，生成经济型审计包：

```bash
uv run scripts/prepare_vision_audit.py \
  -i <基础输出目录> \
  --max-groups 8 \
  --max-images 24
```

<!-- skill-lint:constraint VISION-SUBTRACT-ONLY -->
脚本先要求目标与至少一个上下文通过严格的近像素一致或高质量滚动重叠校验，再按风险分数与时间覆盖选择少量组，生成 `_vision_audit/audit_manifest.json` 与联系表。多模态层只做减法，不恢复基础层漏掉或已丢弃的图片；没有安全可删题时允许生成 0 组。按照 `references/vision-audit.md` 查看同组前后帧，输出 `_vision_review.json`。默认不得突破 8 组、24 张唯一图片；确需扩大时先向用户说明成本和隐私影响。

模型视觉能力较弱或输出稳定性一般时，优先使用弱模型档位：

```bash
uv run scripts/prepare_vision_audit.py \
  -i <基础输出目录> \
  --profile weak
```

<!-- skill-lint:constraint FINAL-COVERAGE-SURVIVAL -->
`weak` 默认最多 6 组、18 张唯一图片；每张联系表只有一个红框判断目标，A/B/C 角色清晰标注，并生成 `review_template.json` 与 `MODEL_INSTRUCTIONS.md`。按组逐张查看，原位填写模板。weak 与 balanced 提出的删除或替换都只有在“置信度至少 0.90 + 本地核准覆盖候选 + 本地风险信号 + 覆盖帧最终存活”同时满足时才会生效；覆盖链、覆盖环或其他不足均安全降级为保留。

### 6. 应用去重视觉审计

```bash
python3 scripts/apply_vision_review.py \
  -i <基础输出目录> \
  -r <基础输出目录>/_vision_review.json
```

应用脚本必须复算基础报告、manifest 和图片 SHA256。成功后生成 `_curated/` 与 `_curated/_curated_report.json`；不得删除或覆盖基础 `frame_*.jpg`。非法引用、过期 manifest、缺理由、哈希不符或空精选集必须失败关闭。

## 主要输出

| 文件 | 说明 |
|---|---|
| `frame_NNN_MMmSSs.jpg` | 本地算法保留的基础帧 |
| `_report.json` | 输入、参数、时间簇统计、丢弃统计、帧时间戳和 SHA256 |
| `_video_screenshot_output.json` | 不含源路径的输出所有权标记，绑定报告与目录内容哈希及根目录清单，供安全重跑校验 |
| `_review_candidates/` | 仅显式开启时保存的算法丢弃候选 |
| `_evidence_leads/evidence_index.json` | 证据线索排序、类别、信号计数、隐私声明和逐帧哈希；不含 OCR 原文 |
| `_evidence_leads/evidence_sheet_NNN.jpg` | 默认 2 列大图的高价值联系表；最多 24 张、4 页 |
| `_evidence_leads/vision_template.json` | 封闭类别、可见事实与可能用途模板 |
| `_evidence_leads/evidence_review.json` | 经应用器校验的非破坏性视觉分类结果 |
| `_vision_audit/audit_manifest.json` | 受预算限制的视觉审计清单与决策合同 |
| `_vision_audit/contact_sheet_NNN.jpg` | 同组前后帧联系表；weak 档位为一组一目标大图 |
| `_vision_audit/review_template.json` | weak 档位预填的受限答案模板 |
| `_vision_audit/MODEL_INSTRUCTIONS.md` | weak 档位逐组判断说明 |
| `_vision_review.json` | 多模态模型的结构化审计结果；weak 使用模板 schema 1.1 |
| `_curated/` | 不修改基础结果的视觉精选副本 |
| `_curated/_curated_report.json` | 精选帧来源、排除清单和全链路哈希 |

## 参数选择

- 默认使用 `scene`，适合手机 App、网页和聊天录屏。
- 默认启用 `--temporal-select`；只有复现旧版行为或排查算法时才用 `--no-temporal-select`。
- 持续快速滚动担心漏页时，降低 `--motion-chunk-seconds`；结果仍过密时再提高。默认值还会按滚动重叠自动乘以 0.8、1.25 或 1.45。
- OCR 是可选增强，未安装时必须清晰提示并降级；它可能为保护新增金额或正文而比纯视觉模式多留少量帧，不能把“帧数更少”作为唯一目标。
- `--keep-drop-candidates` 只用于人工排查基础层漏帧，不等于多模态审计；多模态生产路径不会补回这些图片。
- 默认仅将 `_report.json` 与 `extraction_meta.json` 归档到 Skill `archive/`（不复刻截图与视频，避免重复占用磁盘）；批量回归或临时验证使用 `--no-archive`，不改变基础报告与原始输出目录。
- 模型能力较弱时使用 `--profile weak`；不要通过放大审计组数弥补模型能力，优先保持小任务、高清目标和保守 no-op。

## 依赖

### 系统依赖

| 依赖 | 安装方式 |
|---|---|
| ffmpeg ≥ 5.0 | macOS: `brew install ffmpeg`<br>Linux: `sudo apt-get install ffmpeg` |
| Python ≥ 3.10 | macOS: `brew install python` |
| uv | macOS: `brew install uv` |

### Python 包

| 包名 | 用途 | 安装命令 |
|---|---|---|
| `Pillow>=10.0.0` | 图像指标、时间簇分析和联系表 | `uv run scripts/extract.py --help` 自动准备 |
| `rapidocr-onnxruntime` | 可选 OCR 内容增量与文本去重 | `uv run --with rapidocr-onnxruntime scripts/extract.py -i <视频> --ocr-dedup` |

同一可选依赖也用于证据线索多锚点分类：`uv run --with rapidocr-onnxruntime scripts/prepare_evidence_leads.py -i <基础输出目录>`。缺失时清晰降级为视觉主体与时序排序，不影响基础抽帧。

## 验收与安全边界

- 运行 `uv run scripts/check_pipeline.py --case all`，要求全部领域回归通过并输出 `DOMAIN_CHECKS_PASSED`。
- 输出事务可单独运行 `uv run scripts/check_pipeline.py --case transactional-output`，必须覆盖坏视频、非法参数、符号链接、未知文件、下游产物保护、成功替换和提交回滚。
- 行为变化必须用代表视频复测，并通过联系表或逐图查看进行视觉抽查；静态检查或帧数减少不能单独证明准确。
- 不修改原视频，不把完整录屏默认上传云端。
- 保留基础帧和全链路 SHA256；证据线索层只能排序、分类和概括，去重视觉层只能生成非破坏性精选副本。
- 法律证据中的金额、身份、地址、承诺和关键对话不确定是否被覆盖时，选择保留并提示人工复核。

## 所需权限与安全说明

- **本地文件访问**：读取用户明确提供的视频；图片与复核 JSON 只写入显式输出目录，Skill `archive/` 仅写入 `_report.json` 与 `extraction_meta.json` 元数据副本；不扫描无关目录。
- **本地进程执行**：以参数数组调用本机 `ffmpeg`、`ffprobe` 和 Python 脚本，不使用 shell 拼接执行用户输入。
- **事务性替换**：新结果只写入目标同级 staging；成功提交前不改动旧目录。旧目录必须通过所有权标记，或通过旧版报告与实际帧清单一致性校验；若发现证据线索、视觉复核、精选结果、符号链接或未知文件，拒绝覆盖并提示改用新目录。
- **网络与依赖**：抽帧和 OCR 均可离线运行；`uv run` 首次缺少 Pillow 时可能联网下载依赖。多模态审计是否上传联系表取决于当前模型提供方，处理未脱敏证据前先确认其隐私政策。
- **凭据与环境变量**：本 Skill 不读取 API Key、Token、密码或云端凭据，也不自行调用外部视觉 API。
