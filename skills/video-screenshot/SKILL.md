---
name: video-screenshot
description: 视频截图提取与精筛工具。从微信、小红书、网页、会议等录屏中自动抽取关键帧，按前后帧时间簇选择稳定终态，减少过密截图并过滤翻页、滑页和页面切换中间态；可生成受预算限制的联系表，交给支持图像输入的多模态模型审计重复页和可疑帧，纯文字模型自动停在本地基础结果。触发词：视频截图、录屏截图、聊天记录截图、抽帧去重、视频关键帧提取、截图太密、过渡帧、切换页、多模态截图审计。不要用于视频压缩、视频剪辑或音频提取。
version: "0.4.0"
author: 杨卫薪律师（微信ywxlaw）
homepage: https://github.com/cat-xierluo/legal-skills
license: MIT
---

# video-screenshot — 视频截图提取与精筛

从录屏中提取可追溯的证据截图。默认先在本地执行两遍式时间簇择优；只有当前模型支持图像输入且基础结果仍需精简时，才准备少量多模态审计材料。

## 工作流

### 1. 确认输入与输出

取得一个本地视频路径。支持 `.mp4`、`.mov`、`.avi`、`.mkv`、`.webm`、`.flv`、`.wmv`、`.ts`。默认输出到视频同级 `<视频名>_frames/`；如该目录可能含其他材料，显式指定新的 `-o` 目录。

### 2. 运行基础精筛

```bash
# 默认：场景候选 + 时间簇择优 + 图像去重
uv run scripts/extract.py -i <视频路径>

# 聊天记录等文字型录屏：增加本地 OCR 去重
uv run scripts/extract.py -i <视频路径> --ocr-dedup

# 调试漏帧时才保存被丢弃候选；不要作为多模态默认输入
uv run scripts/extract.py -i <视频路径> --keep-drop-candidates --drop-candidate-limit 80
```

默认流程：

1. 用 ffmpeg 场景变化和 2 秒保底采样生成高召回候选；
2. 计算候选帧清晰度、内容质量、相似度和拼接风险；
3. 按前后帧形成稳定段与连续运动段；
4. 稳定段选择清晰、完整、停留时间更长的代表帧，不机械保留第一张；
5. 前后均有稳定页的短运动段按切换过程处理；无双侧锚点或持续时间较长的滚动段按时间跨度保留代表帧；
6. 再执行 SHA256、dHash、像素差异、SSIM、可选滚动合并和 OCR 去重。

需要调参时读取 `references/strategy-and-params.md`。依赖安装见 `references/setup.md`。

### 3. 检查基础结果

检查：

- `_report.json` 中 `frames` 与实际 `frame_*.jpg` 是否一致；
- `temporal_selection` 的稳定段、运动段和切换丢弃统计；
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

脚本只选择低置信、疑似拼接和相邻过密的少量组，生成 `_vision_audit/audit_manifest.json` 与联系表。按照 `references/vision-audit.md` 查看同组前后帧，输出 `_vision_review.json`。默认不得突破 8 组、24 张唯一图片；确需扩大时先向用户说明成本和隐私影响。

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
| `_vision_audit/contact_sheet_NNN.jpg` | 同组前后帧联系表 |
| `_vision_review.json` | 多模态模型的 `keep/drop/replace` 结构化审计结果 |
| `_curated/` | 不修改基础结果的视觉精选副本 |
| `_curated/_curated_report.json` | 精选帧来源、排除清单和全链路哈希 |

## 参数选择

- 默认使用 `scene`，适合手机 App、网页和聊天录屏。
- 默认启用 `--temporal-select`；只有复现旧版行为或排查算法时才用 `--no-temporal-select`。
- 持续快速滚动担心漏页时，降低 `--motion-chunk-seconds`；结果仍过密时再提高。
- OCR 是可选增强，未安装时必须清晰提示并降级；OCR 与 SSIM 并行，不再自动关闭 SSIM。
- `--keep-drop-candidates` 用于漏帧排查，不等于多模态审计；多模态默认读取预算 manifest。

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
| `rapidocr-onnxruntime` | 可选 OCR 文本去重 | `pip install rapidocr-onnxruntime` |

## 验收与安全边界

- 运行 `uv run scripts/check_pipeline.py --case all`，要求输出 `DOMAIN_CHECKS_PASSED`。
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
