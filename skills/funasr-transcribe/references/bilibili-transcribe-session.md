# Bilibili 视频转录实战笔记（2026-05-10）

## 任务背景

下载 B 站视频 `BV1TfRfBJEZw`（标题：《解读Deepseek V4带来的杠杆机会，顺便聊聊我实践出的Token Efficiency》，作者：小天 fotos）并转录。

## 踩坑记录

### 坑1：服务路径错误（根因）

**现象**：`funasr-onnx` 依赖明明已装，但 `/transcribe` 始终返回 500，错误 "缺少 funasr-onnx 依赖"。

**根因**：服务从 `.claude/skills/funasr-transcribe/` 启动，但 `auto_transcribe.py` 的 import 链加载了 `legal-skills/skills/funasr-transcribe/scripts/server.py`（另一份旧版代码），后者路径下的依赖检查逻辑报了错误。

**排查命令**：
```bash
# 检查 funasr 和 funasr_onnx 是否可用
python3 -c "import funasr; print(funasr.__file__)"
python3 -c "import funasr_onnx"  # 如果报错找不到，正常

# 检查 yt-dlp 下载字幕（需登录）
yt-dlp --list-subs "https://www.bilibili.com/video/BV1TfRfBJEZw/"

# 检查视频时长
ffprobe -v quiet -show_entries format=duration -of csv=p=0 "/path/to/video.mp4"
```

### 坑2：pip 安装 funasr-onnx 超时

`pip install funasr-onnx --break-system-packages` 在 300s 内无法完成（需要下载大模型文件）。

## 最终解决方案：Whisper CLI

系统已装 Whisper CLI（homebrew），作为 FunASR 的 fallback：

```bash
# Step 1: 提取音频（16kHz 单声道）
ffmpeg -i "/path/to/video.mp4" -vn -acodec pcm_s16le -ar 16000 -ac 1 -y "/tmp/audio.wav"

# Step 2: Whisper 转录（推荐 tiny 模型，速度快）
# 模型列表：tiny, base, small, medium, large
/opt/homebrew/bin/whisper "/tmp/audio.wav" \
  --model tiny \
  --language Chinese \
  --output_dir /tmp/transcript \
  --output_format all
```

**性能参考**：19 分钟音频，tiny 模型约 3-5 分钟跑完（Mac CPU）。

## 关键文件路径

| 文件 | 路径 |
|------|------|
| 视频下载脚本 | `.claude/skills/universal-media-downloader/scripts/download_media.py` |
| FunASR 服务 | `.claude/skills/funasr-transcribe/scripts/server-onnx.py` |
| Whisper CLI | `/opt/homebrew/bin/whisper` |
| 视频输出 | `/private/tmp/bilibili_video/` |
| 音频临时 | `/tmp/audio.wav` |

## 教训

1. FunASR ONNX 安装慢，B 站视频优先用 Whisper CLI 转录
2. 服务路径问题看进程日志最准：`process_log`
3. B 站字幕需登录才能导出，最好直接用 ASR 而非读字幕
