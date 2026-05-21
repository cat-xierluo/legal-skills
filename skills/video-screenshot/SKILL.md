---
name: video-screenshot
description: 视频截图提取工具。从录屏视频（微信聊天录屏、会议录屏等）中自动抽取关键帧、去重并保存为图片文件，可用作法律证据。支持场景变化检测、关键帧提取、固定间隔、智能去重四种策略，配合内容区 dHash、像素差异、SSIM、滚动帧合并和 OCR 文本去重。触发词：视频截图、录屏截图、聊天记录截图、抽帧去重、视频截帧、视频关键帧提取。不要用于：视频压缩、视频剪辑、音频提取。
version: "0.3.1"
author: 杨卫薪律师（微信ywxlaw）
homepage: https://github.com/cat-xierluo/legal-skills
license: MIT
---

# video-screenshot — 视频截图提取工具

从录屏视频（微信聊天录屏、会议录屏等）中自动抽取关键帧、去重并保存为可用作法律证据的图片文件。独立 Python CLI，无 Django 依赖。

## 适用场景

- 微信聊天录屏需要提取为逐页截图
- 会议录屏需要提取关键画面作为证据
- 长时间录屏需要去除重复帧，只保留有信息量的画面
- 需要将视频内容转换为可打印、可提交的图片证据

## 默认工作流

### 1. 确认输入

确认用户提供的视频文件路径。支持常见视频格式：`.mp4` `.mov` `.avi` `.mkv` `.webm` `.flv` `.wmv` `.ts`

### 2. 确认参数

默认配置（大多数场景无需调整）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 抽帧策略 | scene | 场景变化检测 |
| 场景阈值 | 0.10 | 变化幅度阈值（越小越敏感） |
| 定期采样间隔 | 5.0s | 静态画面保底采样（0=禁用） |
| 内容区裁剪 | 上 12% / 下 12% / 左右 4% | 排除状态栏、导航栏和边缘黑边后再比较 |
| dHash 去重阈值 | 4 | 对内容区计算汉明距离（0=禁用） |
| SSIM 阈值 | 0.85 | 结构相似度补充去重（0=禁用） |
| 滚动帧合并 | 关闭 | 需显式 `--scroll-merge` 开启 |
| OCR 去重 | 关闭 | 需显式开启 |
| 最长边像素 | 0 | 保持原始分辨率（可设如 1920 限制尺寸） |
| JPEG 质量 | 2 | 最高质量（范围 1-31，越小越清晰） |

详细参数说明见 `references/strategy-and-params.md`，安装指南见 `references/setup.md`。

### 3. 执行抽帧

```bash
# 默认：场景检测 + 图像去重
uv run scripts/extract.py -i <视频文件路径>

# 场景检测 + OCR 去重（推荐用于聊天录屏）
uv run scripts/extract.py -i <视频文件路径> --ocr-dedup

# 固定间隔，每 0.5 秒一帧
uv run scripts/extract.py -i <视频文件路径> -s interval --interval 0.5

# 关键帧提取，不去重
uv run scripts/extract.py -i <视频文件路径> -s keyframe -d 0

# 自定义输出目录
uv run scripts/extract.py -i <视频文件路径> -o /evidence/case_001/

# 更严格的场景检测（更多帧）
uv run scripts/extract.py -i <视频文件路径> --scene-threshold 0.15

# 禁用滚动帧合并（需要逐步滚动全过程时）
uv run scripts/extract.py -i <视频文件路径> --no-scroll-merge
```

### 4. 输出说明

输出目录包含：

| 文件 | 说明 |
|------|------|
| `frame_001_00m00s.jpg` | 保留帧（序号 + 时间戳命名） |
| `frame_002_00m03s.jpg` | 下一帧 |
| `_report.json` | 元数据报告（输入信息、去重统计、每帧 SHA256） |

`_report.json` 可用于证据链追溯，记录了每帧的 SHA256 哈希、捕获时间戳和去重统计。

归档目录中的 `frames/` 只保留 `_report.json` 清单内的本次有效帧。每次运行前会清理输出目录中旧的 `frame_*.jpg` 和本工具报告文件，避免旧帧混入新结果；不会删除其他用户文件。

## 抽帧策略

| 策略 | 说明 | 推荐场景 |
|------|------|----------|
| `scene` | 场景变化检测，画面有显著变化时提取 | 聊天录屏、操作录屏（**默认推荐**） |
| `keyframe` | 仅提取视频关键帧（I 帧） | 压缩视频、快速浏览 |
| `interval` | 固定时间间隔提取 | 需要均匀时间采样 |
| `smart` | ffmpeg 智能去重 | 不确定时尝试 |

## 去重与过滤机制

八级级联去重 + 可选过滤，每一级通过后才进入下一级：

1. **SHA256 精确去重** — 完全相同的帧直接跳过
2. **内容区 dHash 感知哈希** — 排除顶部状态栏、底部导航栏和边缘黑边后比较结构
3. **内容区像素差异** — 48×48 灰度缩略图的平均绝对差值
4. **SSIM 结构相似度** — 对内容区缩略图计算结构相似度，补充 dHash 漏检
5. **滚动帧合并**（默认开启）— 检测连续帧纵向位移后的重叠区域，只保留代表性画面
6. **内容质量过滤**（默认开启）— 自动过滤空白页、启动/控制画面、页面切换过渡帧
7. **模糊帧过滤** — Laplacian 方差低于阈值的帧视为模糊跳过，需 `--filter-blur` 开启
8. **OCR 文本相似度** — 比较最近 4 帧的 OCR 文本（SequenceMatcher + Jaccard），需 `--ocr-dedup` 开启

## 依赖

| 依赖 | 版本要求 | 安装方式 |
|------|----------|----------|
| `ffmpeg` | ≥ 5.0 | `brew install ffmpeg` |
| `Python` | ≥ 3.10 | 系统自带或 `brew install python` |
| `uv` | 最新 | `brew install uv` |
| `Pillow` | ≥ 10.0 | 自动安装（PEP 723 内联依赖） |
| `rapidocr-onnxruntime` | ≥ 1.0 | `pip install rapidocr-onnxruntime`（仅 OCR 去重需要） |

## 与其他技能配合

- `pdf`：输出帧可组装为 PDF 证据包
- `paddle-ocr`：需要更高质量的 OCR 内容识别时，用输出帧作为输入
- `legal-text-format`：帧内容 OCR 后格式化
- `video-compressor`：抽帧前先压缩视频，减小 I/O 时间

## 硬约束

- 不修改原视频文件
- 输出图片使用 JPEG 格式，最长边不超过 `--max-size` 参数
- `_report.json` 始终生成，确保证据可追溯
