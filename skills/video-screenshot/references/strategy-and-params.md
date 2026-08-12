# 策略与参数详解

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

### 短切换段与持续运动段

- 前后均有稳定页、持续不超过 `--transition-max-seconds 2.40` 的短运动段，记录为 `temporal_transition`；
- 三帧分析能把当前帧解释为“前一页尾部 + 后一页头部”横向拼合时，记录为 `temporal_mixed_transition`；
- 视频开头、结尾或没有双侧稳定锚点的运动段不得整段删除，默认每 `--motion-chunk-seconds 2.50` 选择一张代表帧；
- 需要更密地覆盖快速滚动时，把 `--motion-chunk-seconds` 降到 `1.5`；希望进一步精简时可提高到 `3.0`，但必须抽查覆盖。

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

检测并过滤无信息量的帧，包括：
- **空白页**：内容区域标准差接近 0，或大面积纯白/纯黑
- **启动/控制画面**：录屏开始/结束时的控制面板、系统界面（低信息密度）
- **过渡帧**：页面切换时上下半屏内容不一致（部分区域空白，部分有内容）

基于 3×3 网格分析帧的内容分布：计算每个网格区域的标准差，检测内容分布是否均匀。

- `--filter-quality`：启用内容质量过滤（默认开启）
- `--no-filter-quality`：禁用内容质量过滤

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

### OCR 去重参数

需要 `--ocr-dedup` 标志开启，需要安装 `rapidocr-onnxruntime`。

- `--ocr-threshold 0.92`（默认）：OCR 文本相似度超过 92% 且新字符少于 8 个时视为重复
- `--ocr-min-new 8`（默认）：最少新字符数，防止因少量文字变化被误判为重复

OCR 预处理流程：裁剪边缘（顶部 16%、底部 14%、左右 6%）→ 灰度 → 自动对比度 → 对比度增强 1.35x → 锐化 1.15x。动态范围 < 18 的帧跳过 OCR（如纯黑/纯白画面）。

## 复合复核参数

### 丢弃候选帧 (`--keep-drop-candidates`)

开启后，脚本会把被去重或过滤规则丢弃的候选帧复制到 `_review_candidates/`，并在 `_report.json` 的 `review.drop_candidates` 中记录：

- 候选帧文件名
- 原始抽帧序号
- 捕获时间戳
- 丢弃原因（如 `duplicate_ssim`、`duplicate_scroll`、`min_gap`、`quality_transition`、`ocr_duplicate`）
- SHA256 哈希

该模式用于漏帧排查，不是多模态审计的默认入口。它可能生成大量文件，并受 `--drop-candidate-limit` 截断。多模态默认先运行 `prepare_vision_audit.py`，只审计本地层选择的高风险短名单。

### 候选帧数量限制 (`--drop-candidate-limit`)

默认 `--drop-candidate-limit 200`；一般排查建议显式设为 `80`。如需完整回查可设为 `0`，但长视频可能产生大量图片。

```bash
uv run scripts/extract.py -i recording.mp4 --ocr-dedup --keep-drop-candidates
uv run scripts/extract.py -i recording.mp4 --keep-drop-candidates --drop-candidate-limit 0
```

## 多模态审计预算

运行：

```bash
uv run scripts/prepare_vision_audit.py -i <基础输出目录> --max-groups 8 --max-images 24
```

审计包按以下风险选组：

- `selection_confidence=low` 的持续运动代表帧；
- 纵向内部拼接缝风险较高；
- 三帧横向混合页风险；
- 与相邻保留帧间隔过密；
- 附近存在可替代的丢弃候选。

高度重叠的相邻三帧窗口只保留优先级更高者。`max_groups` 和 `max_images` 是硬预算，生成结果不得超过任一上限。决策合同、JSON 示例和应用方式见 `references/vision-audit.md`。

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
    "low_confidence_selection_count": 52
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
      "sha256": "abc123..."
    }
  ]
}
```
