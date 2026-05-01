---
name: video-compressor
description: 视频压缩与静默片段剪切工具。使用 FFmpeg CRF 模式压缩视频，适配屏幕录制/课件场景；支持检测并去除静默静止片段。自动检测硬件并选择最优编码方案（Apple Silicon 默认使用 VideoToolbox 硬件加速，速度提升 5-15x）。本技能应在用户需要压缩视频、减小视频大小、去除视频空档时使用。不要用于：视频剪辑、音频提取、格式转换。
author: 杨卫薪律师（微信ywxlaw）
homepage: https://github.com/cat-xierluo/legal-skills
license: MIT
---

# video-compressor — 视频压缩工具

使用 FFmpeg 将视频文件压缩为低比特率 MP4，减小文件体积的同时保留清晰的音频。自动检测硬件并选择最优编码方案（Apple Silicon 默认使用 VideoToolbox 硬件加速）。

## 适用场景

- 视频文件过大，只需保留音频信息，视频画面作为辅助参考
- 批量压缩目录下多个视频文件
- 降低视频比特率以节省存储空间
- 去除视频中间的静默静止片段（如休息时间、黑屏、无声空档），同时保留被剪片段供复查

## 功能模式

本技能支持两种工作模式：

### 模式一：压缩（默认）

将视频压缩为低比特率 MP4，减小文件体积。

### 模式二：静默/静止片段剪切

检测并去除视频中**同时满足**以下条件的片段：
1. **音频静默**（无声）
2. **画面静止**（连续帧几乎无变化，如休息时无操作、黑屏）

适用于：课程录制中途休息、会议室无人时的静默等待等无效内容。

## 默认工作流（压缩模式）

### 1. 确认输入

确认用户提供的文件路径或目录路径。支持以下视频格式：

`.mp4` `.mov` `.avi` `.mkv` `.webm` `.flv` `.wmv` `.ts`

### 2. 确认参数

默认配置（大多数场景无需调整）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| CRF 质量值 | 23 | 自适应质量，越小质量越高（仅软件编码） |
| 最大码率 | 2500k | VBV 码率上限 |
| 音频比特率 | 96k | AAC 语音音质 |
| 编码预设 | veryfast | 速度与压缩比平衡（仅软件编码） |
| 编码器 | 自动检测 | Apple Silicon 默认 HEVC VT，其他 x264 |
| 并发线程 | 3 | 同时压缩的视频数 |
| 输出后缀 | `_compressed` | 输出文件名后缀 |

详细配置说明见 `references/config.md`。

### 3. 执行压缩

```bash
# 单个文件
python3 scripts/compress.py -i <文件路径>

# 多个文件（并发压缩）
python3 scripts/compress.py -i <文件1> <文件2> <文件3>

# 整个目录
python3 scripts/compress.py -i <目录路径>

# 混合：文件 + 目录
python3 scripts/compress.py -i <文件1> <目录路径> <文件2>
```

指定自定义参数：

```bash
python3 scripts/compress.py -i <文件1> <文件2> --crf 28 -a 64k --preset medium -j 2
```

### 4. 输出报告

压缩完成后输出每个文件的结果：

```text
文件名                    原始大小    压缩后大小   压缩比
video1.mp4                120.5 MB    28.3 MB     76.5%
─────────────────────────────────────────────────
合计                       205.7 MB    47.4 MB     77.0%
```

## 静默/静止片段剪切工作流

### 何时使用

当用户提到以下场景时使用此模式：
- 视频中间有休息时间，需要剪掉
- 视频有长时间静止/无声的片段
- 去除录制中的空档、静默、黑屏

### 1. 执行剪切

```bash
python3 scripts/trim_silences.py -i <视频文件路径>
```

使用默认参数（同时检测静音+静止，最短3秒才计入）。

指定自定义参数：

```bash
# 仅检测静音片段（不考虑画面是否静止）
python3 scripts/trim_silences.py -i <路径> --mode silence

# 仅检测画面静止片段（不考虑是否有声音）
python3 scripts/trim_silences.py -i <路径> --mode static

# 自定义阈值：更严格的静默检测
python3 scripts/trim_silences.py -i <路径> --noise-db -40 --min-duration 5
```

### 模式选择建议

| 视频类型 | 推荐模式 | 说明 |
|----------|---------|------|
| 课程录制休息时 | `both` | 同时满足静音+静止，不误剪 |
| 会议无人时段 | `both` 或 `static` | 若全程有空调白噪声用 `both` |
| 比赛/电影解说（全程有声音） | `static` | 仅剪画面静止部分 |
| 监控录像（画面固定） | `static` | 几乎不需要音频 |

### 2. 理解输出

剪切完成后，输出：

| 文件 | 说明 |
|------|------|
| `原文件名_trimmed.mp4` | 精剪版（去除了目标片段） |
| `原文件名_cuts/` | 存放被剪片段的目录 |
| `原文件名_cuts/_report.json` | 被剪片段的时间戳报告 |

被剪片段目录中，每个片段保存为一个独立的 MP4 文件，文件名包含起止时间，方便复查。

### 3. 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--noise-db` | -30 | 静默检测分贝阈值，越小越严格 |
| `--scene-threshold` | 0.05 | 画面静止阈值 0~1，越小越严格（轻微页面变化可接受） |
| `--min-duration` | 120 | 最短片段时长(秒)，默认2分钟，仅剪掉长片段 |
| `--mode` | both | 检测模式：both=同时静音+静止，silence=仅静音，static=仅画面静止 |
| `--crf` | 23 | CRF 质量值 |
| `--maxrate` | 2500k | 最大码率限制 |
| `--bufsize` | 2500k | VBV 缓冲区大小 |
| `--audio-bitrate` | 96k | 输出音频比特率 |
| `--preset` | veryfast | 编码预设 |
| `--codec` | 自动检测 | 编码器选择（hevc_vt / h264_vt / x264 / x265 / x264_fast） |

## 硬件加速

本工具自动检测系统硬件并选择最优编码方案：

| 平台 | 编码器 | 速度提升 | 输出格式 | 说明 |
|------|--------|----------|----------|------|
| Apple Silicon (M1/M2/M3/M4) | hevc_videotoolbox | 5-15x | HEVC/H.265 | 自动使用硬件编码 |
| Apple Silicon (备用) | h264_videotoolbox | 3-8x | H.264 | HEVC 不可用时的回退 |
| 其他平台 | libx264 | 1x | H.264 | 标准软件编码 |

启动时自动打印检测结果，如：
```
硬件检测: Apple Silicon (10 核 / 64 GB)
编码器: HEVC VideoToolbox (硬件加速) — 预计速度提升 5-15x
FFmpeg: 8.1 (VideoToolbox 支持: H.264 + HEVC)
```

手动指定编码器：
```bash
python3 scripts/compress.py -i <路径> --codec hevc_vt   # 强制 HEVC 硬件编码
python3 scripts/compress.py -i <路径> --codec h264_vt   # 强制 H.264 硬件编码
python3 scripts/compress.py -i <路径> --codec x264      # 强制软件编码
python3 scripts/compress.py -i <路径> --codec x265      # 软件 HEVC 编码（高压缩）
```

可选编码器：`hevc_vt` `h264_vt` `x264` `x265` `x264_fast`

## 硬约束

- **不覆盖原文件**：输出文件始终添加后缀
- **输出到同目录**：精剪版和被剪片段目录都与原文件在同一目录
- **保留音频质量**：音频使用 AAC 编码，默认 96k
- **固定 MP4 输出**：所有输出文件均为 MP4 格式（硬件编码 HEVC/H.264 + AAC，软件编码 x264 + AAC）

## 依赖

| 依赖 | 版本要求 | 安装方式 |
|------|----------|----------|
| `ffmpeg` | ≥ 5.0（推荐 ≥ 7.0 for VideoToolbox `-q:v`） | `brew install ffmpeg` |
| `Python` | ≥ 3.10 | 系统自带或 `brew install python` |

## 与其他技能配合

- 可与 `universal-media-downloader` 配合：下载视频后压缩节省空间
- 可与 `funasr-transcribe` / `tingwu-asr` 配合：压缩后再转录，减少文件传输时间
