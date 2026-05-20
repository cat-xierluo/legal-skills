# 策略与参数详解

## 抽帧策略

### scene（场景检测，默认）

使用 ffmpeg 的 `select='gt(scene,<threshold>)'` 滤镜。当连续帧之间的画面差异超过阈值时，提取该帧。配合 `mpdecimate` 去除接近重复的帧。

适用：聊天录屏（页面滚动、消息变化时自动捕获）、操作录屏。

参数：
- `--scene-threshold 0.25`（默认）：中等敏感度，画面有 25% 以上变化才提取
- `--scene-threshold 0.15`：更敏感，适合变化缓慢的录屏
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
- `8`（默认）：平衡，允许轻微变化
- `4`：严格，仅非常相似的帧才被去除
- `12`：宽松，更多帧被去除

### 像素差异阈值

固定为 8.0（内部参数，暂不暴露 CLI 选项）。对内容区生成 48×48 灰度缩略图后计算平均绝对差值。

### SSIM 结构相似度 (`--ssim-threshold`)

SSIM（结构相似性指数）用于补充 dHash。它在内容区生成 32×32 灰度缩略图后比较亮度、对比度和结构一致性，更适合识别视觉上接近但 dHash 距离偏大的帧。

- `--ssim-threshold 0.70`（默认）：保守去重，只跳过结构高度接近的帧
- `--ssim-threshold 0`：禁用 SSIM 去重
- `--ssim-threshold 0.60`：更激进，可能减少更多滚动冗余，但需要抽查输出

### 滚动帧合并 (`--scroll-merge`)

滚动帧合并用于处理聊天录屏、网页滚动、App 列表滚动等场景。它会比较当前帧与最近保留帧在纵向位移后的重叠区域：如果大部分内容只是上下移动，且重叠区域平均像素差低于阈值，则跳过当前帧。

- `--scroll-merge`：启用滚动帧合并（默认开启）
- `--no-scroll-merge`：禁用滚动帧合并，适合需要完整保留滚动过程的场景
- `--scroll-diff-threshold 32.0`（默认）：阈值越大，合并越激进

调参建议：
- 证据需要尽量少图且便于审阅：可尝试 `--scroll-diff-threshold 36`
- 担心漏掉边缘新内容：使用默认值或 `--scroll-diff-threshold 24`
- 需要每个滚动位置都保留：使用 `--no-scroll-merge`

### OCR 去重参数

需要 `--ocr-dedup` 标志开启，需要安装 `rapidocr-onnxruntime`。

- `--ocr-threshold 0.92`（默认）：OCR 文本相似度超过 92% 且新字符少于 8 个时视为重复
- `--ocr-min-new 8`（默认）：最少新字符数，防止因少量文字变化被误判为重复

OCR 预处理流程：裁剪边缘（顶部 16%、底部 14%、左右 6%）→ 灰度 → 自动对比度 → 对比度增强 1.35x → 锐化 1.15x。动态范围 < 18 的帧跳过 OCR（如纯黑/纯白画面）。

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
