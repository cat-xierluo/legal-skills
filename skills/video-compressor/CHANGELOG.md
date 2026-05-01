# 变更日志

本项目的所有重要变更都将记录在此文件。

## [1.3.0] - 2026-05-01

### 新增

- **硬件加速自适应编码**：自动检测系统硬件（Apple Silicon VideoToolbox 等）并选择最优编码方案
  - Apple Silicon 默认使用 `hevc_videotoolbox` 硬件编码，速度提升 5-15x
  - 新增 `--codec` 参数支持手动指定编码器：`hevc_vt` `h264_vt` `x264` `x265` `x264_fast`
  - 启动时自动打印硬件检测结果和编码配置
- **新增共享硬件检测模块** `scripts/hw_detect.py`：硬件检测、编码配置选择、FFmpeg 参数构建
- **耗时统计**：压缩完成后显示总耗时和使用的编码器名称

### 变更

- 压缩和剪切脚本从硬编码 `libx264` 参数改为通过 `hw_detect` 模块动态生成
- `compress_video()` 和 `cut_segments()` / `save_removed_clips()` 函数签名简化，编码参数统一为 `encode_args` 列表

### 技术细节

- 检测方式：`ffmpeg -encoders` 检测 VideoToolbox 可用性 + `sysctl` 检测 Apple Silicon
- HEVC VT 参数：`-q:v 65 -b:v 2000k -maxrate 3000k -bufsize 3000k -tag:v hvc1 -allow_sw 1`
- H.264 VT 参数：`-q:v 65 -b:v 2000k -maxrate 3000k -bufsize 3000k -allow_sw 1`
- 向后兼容：无 `--codec` 参数时行为由自动检测结果决定，所有现有参数继续有效

---

## [1.2.0] - 2026-04-30

### 变更

- **压缩编码从 CBR 改为 CRF 模式**：基于实际高压缩率视频的逆向分析，将默认编码策略从固定码率 (`-b:v`) 切换为 CRF 自适应质量 (`-crf 23 -maxrate 2500k -bufsize 2500k`)，屏幕录制/课件场景下压缩率提升约 50%+
- **添加 High Profile**：编码参数增加 `-profile:v high`，利用 8x8dct 提高压缩效率
- **音频默认码率下调**：从 128k 降至 96k，语音内容完全够用
- **支持多文件并发压缩**：`-i` 参数接受多个路径（文件或目录混搭），默认 3 线程并发处理，用完一个线程自动补入下一个文件。新增 `-j / --workers` 参数控制并发数

### 技术细节

- 分析参考视频（3.6h 1080p 仅 732MB）发现其使用 `rc=crf crf=23.0 vbv_maxrate=2500 vbv_bufsize=2500 bframes=0 ref=1 keyint=360`，平均码率仅 367kbps
- CRF 模式根据画面复杂度自适应：静态画面自动压至极低码率，动态画面自动提升质量
- `compress.py` 和 `trim_silences.py` 同步更新，参数从 `--video-bitrate` 改为 `--crf` / `--maxrate` / `--bufsize` 三件套

---

## [1.1.0] - 2026-04-25

### 新增

- **静默/静止片段剪切功能**：新增 `scripts/trim_silences.py`
  - 检测并去除视频中同时满足以下条件的片段：
    1. 音频静默（无声）
    2. 画面静止（连续帧几乎无变化，如休息时无操作、黑屏）
  - 输出精剪版视频（去除了目标片段）和被剪片段目录（供复查）
  - 默认参数：`--min-duration 120`（仅剪≥2分钟的片段）、`--scene-threshold 0.05`（轻微页面变化可接受）
  - 适用场景：课程录制中途休息、会议室无人等待等长时间无效内容

### 变更

- `--min-duration` 默认值从 3s 调整为 120s（2分钟）
- `--scene-threshold` 默认值从 0.1 调整为 0.05（更严格的静止判定）
- 场景检测算法从 ffmpeg scene detection 改为帧采样+像素指纹比较

### 技术优化

- 新增三种检测模式：`both`（同时满足静音+静止）、`silence`（仅静音）、`static`（仅静止）
- 被剪片段单独保存到 `原文件名_cuts/` 目录，每个片段一个 MP4 文件
- 生成 `_report.json` 记录被剪片段的精确时间戳

---

## [1.0.0] - 2026-04-25

### 新增

- video-compressor 技能初始版本
- `scripts/compress.py`：FFmpeg 低比特率视频压缩
- 支持 `.mp4` `.mov` `.avi` `.mkv` `.webm` `.flv` `.wmv` `.ts` 格式
- 保留 AAC 音频编码（默认 128k）
- 固定 MP4 输出（libx264 + AAC）
- 批量压缩目录下多个视频文件
- 完整的参数配置系统（video_bitrate、audio_bitrate、preset、output_suffix）
