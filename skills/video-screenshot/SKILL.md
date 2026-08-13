---
name: video-screenshot
description: 视频截图提取与精筛工具。从微信、小红书、网页、会议等录屏中自动抽取关键帧，以有界高召回保留短时真实页，再按前后帧时间簇和滚动内容增量控制密度；可用本地 OCR 保护新增金额或正文，并为普通或较弱的多模态模型生成只做减法、受预算、单目标和覆盖存活门禁约束的联系表审计包。纯文字模型自动停在本地基础结果。触发词：视频截图、录屏截图、聊天记录截图、抽帧去重、视频关键帧提取、截图太密、过渡帧、切换页、弱多模态截图审计。不要用于视频压缩、视频剪辑或音频提取。
version: "0.7.0"
author: 杨卫薪律师（微信ywxlaw）
homepage: https://github.com/cat-xierluo/legal-skills
license: MIT
---

# video-screenshot — 视频截图提取与精筛

从录屏中提取可追溯的证据截图。默认先在本地执行时间簇择优、内容增量精筛和高置信加载态过滤；只有当前模型支持图像输入且基础结果仍需精简时，才准备少量多模态审计材料。

## 工作流

### 1. 确认输入与输出

取得一个本地视频路径。支持 `.mp4`、`.mov`、`.avi`、`.mkv`、`.webm`、`.flv`、`.wmv`、`.ts`。默认输出到视频同级 `<视频名>_frames/`；如该目录可能含其他材料，显式指定新的 `-o` 目录。

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

### 4. 按能力选择多模态分支

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

### 5. 应用视觉审计

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
| `_review_candidates/` | 仅显式开启时保存的算法丢弃候选 |
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
- 默认复制结果到 Skill `archive/`；批量回归或临时验证使用 `--no-archive`，避免重复占用空间且不改变基础报告。
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

## 验收与安全边界

- 运行 `uv run scripts/check_pipeline.py --case all`，要求全部领域回归通过并输出 `DOMAIN_CHECKS_PASSED`。
- 行为变化必须用代表视频复测，并通过联系表或逐图查看进行视觉抽查；静态检查或帧数减少不能单独证明准确。
- 不修改原视频，不把完整录屏默认上传云端。
- 保留基础帧和全链路 SHA256；视觉层只能生成非破坏性精选副本。
- 法律证据中的金额、身份、地址、承诺和关键对话不确定是否被覆盖时，选择保留并提示人工复核。

## 所需权限与安全说明

- **本地文件访问**：读取用户明确提供的视频，只向显式输出目录和本 Skill 的 `archive/` 写入图片、JSON 与归档副本；不扫描无关目录。
- **本地进程执行**：以参数数组调用本机 `ffmpeg`、`ffprobe` 和 Python 脚本，不使用 shell 拼接执行用户输入。
- **受控清理**：只删除本次临时目录和可由文件名规则确认的旧基础输出；若发现视觉审计、精选结果或未知文件，拒绝自动覆盖并提示改用新目录。
- **网络与依赖**：抽帧和 OCR 均可离线运行；`uv run` 首次缺少 Pillow 时可能联网下载依赖。多模态审计是否上传联系表取决于当前模型提供方，处理未脱敏证据前先确认其隐私政策。
- **凭据与环境变量**：本 Skill 不读取 API Key、Token、密码或云端凭据，也不自行调用外部视觉 API。
