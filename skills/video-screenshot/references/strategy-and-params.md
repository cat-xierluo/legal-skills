# 策略与参数详解

## 目录

- [证据线索排序](#证据线索排序基础抽帧后可选)
- [时间簇择优](#时间簇择优默认开启)
- [抽帧策略](#抽帧策略)
- [去重参数](#去重参数)
- [复合复核参数](#复合复核参数)
- [多模态审计预算](#多模态审计预算)
- [输出参数](#输出参数)
- [输出文件](#输出文件)

## 证据线索排序（基础抽帧后可选）

`prepare_evidence_leads.py` 不参与抽帧删除，只读取实际基础输出目录中 `_report.json` 清单内的基础 JPG 并生成独立 `_evidence_leads/`。默认最多选择 24 个代表线索、生成 4 页 2 列大图联系表；完整索引仍包含所有基础帧。不要把仅含元数据的 Skill `archive/` 目录传给它。

- 推荐用 `uv run --with rapidocr-onnxruntime scripts/prepare_evidence_leads.py -i <基础输出目录>` 启用内存 OCR 多锚点分类；
- 无 OCR 或主要是商品/作品画面时用 `--no-ocr`，连续图像主体和前后变化仍会参与排序；
- 调低 `--max-leads` 可节省模型成本，但不会删除基础帧；提高前应先确认默认联系表确有覆盖不足；
- `--columns` 默认 2，适合能力较弱的多模态模型读取手机竖屏文字；提高列数会缩小单图，不建议作为默认；
- 完整类别、隐私和弱模型答案合同见 `evidence-leads.md`。

价值分数只影响联系表优先级，不是证据成立评分，也不能作为去重删除理由。OCR 原文只在进程内短暂使用，索引仅保存类别、组合命中计数和不可逆图像摘要。

## 时间簇择优（默认开启）

`--temporal-select` 把 ffmpeg 候选先作为一条时间序列分析，再把每个稳定段或连续运动片段的代表帧交给传统去重器。它解决 `min-gap` 只能保留“先到帧”、无法等页面切换完成的问题。

### 稳定段

相邻候选在内容区像素差异或 SSIM 上足够接近，且间隔不超过 `--stable-max-gap 2.20` 时，归入同一稳定页。簇内综合比较：

- Laplacian 清晰度；
- 下一候选到来前的停留时间；
- 单帧空白、启动页和网格过渡风险；
- 内部纵向拼接缝风险；
- 在分数接近时轻微偏好后期终态。

只保留得分最高的代表帧，其余记录为 `temporal_stable_duplicate`。

### 短运动段与持续运动段

- 前后均有稳定页、持续不超过 `--transition-max-seconds 2.40` 的短运动段至少保留一张 `short_motion_representative`，其余同段候选记录为 `temporal_short_motion_redundant`；不能仅凭持续时间短自动删除整段；
- 三帧像素拼合能把当前帧解释为“前一页尾部 + 后一页头部”时，记录为 `temporal_mixed_transition`；分区覆盖还会估计横向、纵向和缩放动画风险，用于视觉审计提权但不单独自动删除；
- 疑似未完成页只有在短时间内出现同一页面骨架、主内容明显增加且完整后帧本来就会被时间簇保留时，才记录为 `temporal_incomplete_resolved`；该后帧作为必要覆盖帧绕过后续去重/过滤，最终缺失时失败关闭；启用 OCR 时关闭该纯视觉自动删除；
- 视频开头、结尾或没有双侧稳定锚点的运动段不得整段删除，默认每 `--motion-chunk-seconds 2.50` 选择一张代表帧；
- 默认跨度会按运动段的纵向滚动重叠自适应：高重叠连续滚动使用 `1.45×`，中等重叠使用 `1.25×`，内容快速变化使用 `0.8×`；最终值限制在 `1.4—4.5` 秒；
- 需要更密地覆盖快速滚动时，把 `--motion-chunk-seconds` 降到 `1.5`；希望进一步精简时可提高到 `3.0`，但必须抽查覆盖。

`_report.json` 每张运动代表帧记录 `adaptive_chunk_seconds`、`motion_density_mode` 和 `scroll_match_ratio`；汇总记录 `adaptive_motion_group_count`。这些字段解释密度选择，不单独作为删除证据。

用 `--no-temporal-select` 可复现旧版逐帧流程，只用于算法排查或兼容，不作为推荐默认值。

## 抽帧策略

### scene（场景检测，默认）

使用 ffmpeg 的 `select='gt(scene,<threshold>)'` 滤镜。当连续帧之间的画面差异超过阈值时，提取该帧。配合 `mpdecimate` 去除接近重复的帧。

适用：聊天录屏（页面滚动、消息变化时自动捕获）、操作录屏。

参数：
- `--scene-threshold 0.10`（默认）：较敏感，适合变化缓慢的录屏
- `--scene-threshold 0.15`：稍严格，减少轻微变化带来的候选帧
- `--scene-threshold 0.40`：更严格，只提取大幅变化

### keyframe（关键帧）

使用 `-skip_frame nokey` 仅解码视频的关键帧（I 帧）。速度最快，提取帧数最少。

适用：快速浏览视频内容、压缩视频。

### interval（固定间隔）

使用 `fps=N` 滤镜，按固定时间间隔提取帧。`--interval 1.0` 表示每秒一帧。

适用：需要均匀时间采样的场景。

### smart（智能去重）

使用 ffmpeg 的 `mpdecimate` 滤镜自动去除连续重复帧。介于 scene 和 interval 之间。

## 去重参数

### 内容质量过滤 (`--filter-quality`)

检测无信息量或高风险帧，包括：
- **空白页**：内容区域标准差接近 0，或大面积纯白/纯黑
- **启动/控制画面**：录屏开始/结束时的控制面板、系统界面（低信息密度）
- **过渡风险**：页面切换时上下半屏内容不一致；该单帧标签只提权审计，不直接删除
- **高置信加载浮层**：中央存在高对比亮卡片、周边一致压暗且综合分数达到保守阈值

基于 3×3 网格分析帧的内容分布：计算每个网格区域的标准差，检测内容分布是否均匀。

- `--filter-quality`：启用内容质量过滤（默认开启）
- `--no-filter-quality`：禁用内容质量过滤

代码自动丢弃 `loading_overlay`。`incomplete_page` 只有在 1.25 秒内出现页面上部共同骨架、主内容边缘密度显著增加，而且该后帧在未启用本规则时本来就会成为时间簇代表帧，才记录为 `temporal_incomplete_resolved` 并删除；否则保留并交由视觉审计。启用 OCR 时关闭这项纯视觉删除，让文字增量先完整运行。合法白底正文页不能只因白色比例高被删除。

### 模糊帧过滤 (`--filter-blur`)

基于 Laplacian 方差的模糊检测，识别页面滚动、手指触碰等导致的半模糊帧。使用 Pillow 实现的 3×3 Laplacian 卷积核，无需 OpenCV。

- `--filter-blur`：启用模糊帧过滤（默认关闭）
- `--blur-threshold 50.0`（默认）：Laplacian 方差低于此值的帧视为模糊

阈值参考：
- 清晰文字截图：通常 > 200
- 轻微模糊（手指触碰瞬间）：50-150
- 明显模糊（页面快速滚动中）：< 30
- 默认 50.0 只过滤明确模糊的帧，避免误杀

### 内容区裁剪参数

默认所有图像相似度比较都会先裁剪内容区，排除顶部状态栏、底部导航栏和左右边缘黑边：

- `--content-crop-top 0.12`：裁掉顶部 12%
- `--content-crop-bottom 0.12`：裁掉底部 12%
- `--content-crop-left 0.04`：裁掉左侧 4%
- `--content-crop-right 0.04`：裁掉右侧 4%

如果录屏本身没有状态栏或导航栏，可把对应比例调低到 `0`；如果是手机聊天录屏且底部输入区固定不变，可适当提高 `--content-crop-bottom`。

### dHash 阈值 (`-d` / `--dedup-threshold`)

dHash（差异哈希）将内容区缩至 9×8 灰度，比较相邻像素生成 64 位哈希。两帧的汉明距离（不同位数）小于阈值则视为重复。

- `0`：禁用 dHash 去重
- `4`（默认）：严格，仅非常相似的帧才被去除
- `8`：平衡，允许轻微变化
- `12`：宽松，更多帧被去除

### 像素差异阈值

固定为 8.0（内部参数，暂不暴露 CLI 选项）。对内容区生成 48×48 灰度缩略图后计算平均绝对差值。

### SSIM 结构相似度 (`--ssim-threshold`)

SSIM（结构相似性指数）用于补充 dHash。它在内容区生成 32×32 灰度缩略图后比较亮度、对比度和结构一致性，更适合识别视觉上接近但 dHash 距离偏大的帧。

- `--ssim-threshold 0.93`（默认）：严格去重，只跳过结构高度接近的帧
- `--ssim-threshold 0`：禁用 SSIM 去重
- `--ssim-threshold 0.85`：更激进，可能减少更多滚动冗余，但需要抽查输出

### 滚动帧合并 (`--scroll-merge`)

滚动帧合并用于处理聊天录屏、网页滚动、App 列表滚动等场景。它会比较当前帧与最近保留帧在纵向位移后的重叠区域：如果大部分内容只是上下移动，且重叠区域平均像素差低于阈值，则跳过当前帧。

- `--scroll-merge`：启用滚动帧合并（默认关闭）
- `--no-scroll-merge`：禁用滚动帧合并，适合需要完整保留滚动过程的场景
- `--scroll-diff-threshold 32.0`（默认）：阈值越大，合并越激进

调参建议：
- 证据需要尽量少图且便于审阅：可尝试 `--scroll-diff-threshold 36`
- 担心漏掉边缘新内容：使用默认值或 `--scroll-diff-threshold 24`
- 需要每个滚动位置都保留：使用 `--no-scroll-merge`

### 最小时间间隔 (`--min-gap`)

用于时间簇择优后的安全限流。默认 `--min-gap 0.5`，表示两个最终保留帧之间至少间隔 0.5 秒；它不再决定簇内保留哪一张。

- `--min-gap 0`：禁用时间间隔过滤
- `--min-gap 0.5`（默认）：减少同秒多图，同时尽量保留快速变化
- `--min-gap 1.0`：更严格，每秒最多保留约一张，适合先压缩冗余再人工复核

### OCR 内容增量参数

需要 `--ocr-dedup` 标志开启，需要安装 `rapidocr-onnxruntime`。

推荐直接运行：

```bash
uv run --with rapidocr-onnxruntime scripts/extract.py \
  -i <视频路径> --ocr-dedup
```

- `--ocr-threshold 0.92`（默认）：OCR 文本相似度超过 92% 且新字符少于 8 个时视为重复
- `--ocr-min-new 8`（默认）：最少新字符数，防止因少量文字变化被误判为重复

OCR 预处理流程：裁剪边缘（顶部 16%、底部 14%、左右 6%）→ 灰度 → 自动对比度 → 对比度增强 1.35x → 锐化 1.15x。动态范围 < 18 的帧跳过 OCR（如纯黑/纯白画面）。

OCR 先计算最近 4 张保留帧的文本相似度、新增三字片段和新增证据数字。1—2 位易变数字不参与保护，减少状态栏时钟和视频时间码带来的假增量。只有以下强增量可以否决 dHash、像素差或 SSIM 的近似删除：

- 页面相似度至少 0.72，且出现新的金额或至少 3 位连续编号；
- 页面相似度至少 0.82，且新增文字片段达到 `max(16, 2×--ocr-min-new)`。

SHA256 完全重复不接受 OCR 覆盖。强新增内容可以否决近似视觉去重和最终 `--min-gap`；短运动段还会在最多 24 张图片预算内检查落选项，每组最多补回一张。报告只保存相似度和增量计数，不保存 OCR 原文；`ocr_visual_overrides`、`ocr_min_gap_overrides` 和 `ocr_short_motion_rescue_count` 记录保护路径。

## 复合复核参数

### 丢弃候选帧 (`--keep-drop-candidates`)

开启后，脚本会把被去重或过滤规则丢弃的候选帧复制到 `_review_candidates/`，并在 `_report.json` 的 `review.drop_candidates` 中记录：

- 候选帧文件名
- 原始抽帧序号
- 捕获时间戳
- 丢弃原因（如 `duplicate_ssim`、`duplicate_scroll`、`min_gap`、`quality_transition`、`ocr_duplicate`）
- SHA256 哈希

该模式只用于人工排查基础层漏帧，不是多模态审计的默认入口。它可能生成大量文件，并受 `--drop-candidate-limit` 截断。v0.7.0 多模态生产路径只对基础帧做减法，不再从该目录生成恢复题。

候选池达到上限后，`quality_loading_overlay`、`quality_transition` 和 `temporal_incomplete_resolved` 可以替换一个普通低优先级候选，避免视频后段的高风险删除项因先到先得而失去人工排查机会；这些候选不会进入多模态自动恢复路径。

### 候选帧数量限制 (`--drop-candidate-limit`)

默认 `--drop-candidate-limit 200`；一般排查建议显式设为 `80`。如需完整回查可设为 `0`，但长视频可能产生大量图片。

```bash
uv run --with rapidocr-onnxruntime scripts/extract.py \
  -i recording.mp4 --ocr-dedup --keep-drop-candidates
uv run scripts/extract.py -i recording.mp4 --keep-drop-candidates --drop-candidate-limit 0
```

## 多模态审计预算

运行：

```bash
uv run scripts/prepare_vision_audit.py -i <基础输出目录> --max-groups 8 --max-images 24
```

审计包只保留同时满足“基础目标有本地风险 + 至少一个同组基础帧通过严格覆盖资格”的组。覆盖资格仅接受近像素一致或重叠区域差异极低的滚动关系；相同 App 外壳、时间相邻或普通结构相似均不足以授予删除资格。随后按以下风险排序：

- `selection_confidence=low` 的持续运动代表帧；
- 纵向内部拼接缝风险较高；
- 三帧横向混合页风险；
- 与相邻保留帧间隔过密；
- 疑似未加载完整页面；
- OCR 高相似低增量或新增证据数字；
- 附近存在可替代的丢弃候选。

高度重叠的相邻三帧窗口只保留优先级更高者。选组在风险优先基础上给未覆盖时间段有限加分，`budget.covered_time_buckets` 记录覆盖的 30 秒区段。`max_groups` 和 `max_images` 是硬预算，生成结果不得超过任一上限。决策合同、JSON 示例和应用方式见 `references/vision-audit.md`。

能力较弱的多模态模型使用：

```bash
uv run scripts/prepare_vision_audit.py -i <基础输出目录> --profile weak
```

weak 默认 6 组、18 张唯一图片，每组只有一个红框目标，联系表采用 2 列大图并生成预填答案模板。只允许对基础目标使用 `keep/drop/replace`；删除或替换必须引用模板列出的本地核准覆盖帧、置信度至少 0.90、本地风险信号成立，且覆盖帧最终存活。覆盖链、覆盖环、无关页面或证据内容不完整时记录安全无操作。没有合格覆盖关系时允许生成 0 组，避免让弱模型白看图或冒险删除。

### 归档开关

默认完成抽帧后仅将 `_report.json` + `extraction_meta.json` 归档到 Skill `archive/`，不再复制截图与视频（避免 archive 下重复占用磁盘）。截图以用户输出目录为准、原始视频保持在用户原路径。批量回归、临时调参或空间敏感场景使用 `--no-archive`；它只跳过归档副本，不影响输出目录中的基础帧与 `_report.json`。

归档目录是溯源元数据副本，不是可恢复的截图备份，也不是证据线索或视觉去重脚本的输入目录。需要生成 `_evidence_leads/`、`_vision_audit/` 或 `_curated/` 时，始终使用控制台显示的“输出目录”；若该目录中的基础帧已被移走，应回到原视频重新抽取，不能仅凭归档报告重建图片。

## 输出参数

### `--max-size`（默认 0，保持原始分辨率）

输出图片最长边的像素限制。设为 0 时不缩放，保持视频原始分辨率（推荐，保证证据清晰度）。如需限制可设如 `--max-size 1920`。

### `-q` / `--quality`（默认 2，最高质量）

JPEG 输出质量，对应 ffmpeg 的 `-q:v` 参数。范围 1-31，越小越清晰。法律证据场景建议保持默认 2：
- `2`：最高质量（**默认推荐**）
- `6`：高质量（文件较小）
- `10`：中等质量（不推荐用于证据）

### `--timeout`（默认 1800）

总超时时间（秒）。超时后 ffmpeg 进程被终止。

## 输出文件

### 帧命名规则

```
frame_NNN_MMmSSs.jpg
```

- `NNN`：保留帧序号（去重后的顺序）
- `MMmSSs`：视频中的捕获时间戳

### `_report.json` 结构

```json
{
  "input": "/path/to/video.mp4",
  "duration_seconds": 180.5,
  "strategy": "scene",
  "total_extracted": 156,
  "kept_after_dedup": 42,
  "review": {
    "drop_candidates_enabled": true,
    "drop_candidate_count": 12,
    "vision_audit_status": "not_prepared",
    "drop_candidates": [
      {
        "filename": "_review_candidates/candidate_001_min_gap_00m01s.jpg",
        "reason": "min_gap",
        "capture_time_seconds": 1.2
      }
    ]
  },
  "temporal_selection": {
    "enabled": true,
    "selected_before_dedup": 73,
    "stable_run_count": 21,
    "transition_drop_count": 57,
    "low_confidence_selection_count": 52,
    "adaptive_motion_group_count": 11
  },
  "dedup_stats": {
    "sha256_duplicates": 3,
    "dhash_duplicates": 89,
    "pixel_duplicates": 12,
    "ssim_duplicates": 4,
    "scroll_duplicates": 18,
    "ocr_duplicates": 10
  },
  "frames": [
    {
      "index": 1,
      "filename": "frame_001_00m00s.jpg",
      "capture_time_seconds": 0.0,
      "sha256": "abc123...",
      "loading_overlay_label": "",
      "adaptive_chunk_seconds": 3.125,
      "motion_density_mode": "scroll_mixed",
      "scroll_match_ratio": 0.48,
      "content_delta": {
        "ocr_available": false,
        "has_new_content": false,
        "protect_visual_duplicate": false
      }
    }
  ]
}
```
