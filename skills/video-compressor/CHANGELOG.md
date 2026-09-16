# 变更日志

本项目的所有重要变更都将记录在此文件。

## [1.5.1] - 2026-09-16

### 修复

- **批量混压编码器误判**（`compress.py` / `hw_detect.py`）：此前仅探测首个输入文件的码率决定全局编码器，批量压缩"高码率视频 + 低码率录屏"混合目录时，低码率文件被拖进硬件路径（写死 2000k 目标码率、无 CRF），压缩收益极低
  - 自动模式改为**逐文件码率自适应**：每个文件编码前单独 ffprobe，低码率走 x264 CRF、高码率走硬件路径，分流时打印 `[自适应] 文件名: 编码器` 提示
  - 显式 `--codec` 优先级不变：全局统一使用指定编码器，不做逐文件覆盖
  - `select_profile()` 中 3 Mbps 阈值提取为常量 `LOW_BITRATE_THRESHOLD`，消除魔法数字
  - 混合批次的全局并发数仍按首个文件 profile 推荐（如硬件=1），个别软件编码文件可能未跑满，属速度与简单性的可接受权衡
- 端到端验证：合成 6.1 Mbps 高码率 + 0.07 Mbps 低码率黑屏混合批次，高码率输出 hevc（硬件）、低码率输出 h264（x264 CRF 自适应），分流正确 ✓

---

## [1.5.0] - 2026-09-16

### 新增

- **源码率感知的编码器自动选择**（`hw_detect.py`）：新增 `probe_bitrate()`，`select_profile()` 接受 `source_bitrate` 参数
  - 源总码率 ≤3 Mbps（录屏/课件特征）时自动选用 x264 CRF 自适应编码，不再误走写死 2000k 目标码率的硬件路径
  - 硬件路径（hevc_vt/h264_vt）在 `build_encode_args` 中固定 `-b:v 2000k` 且不支持 CRF，对低码率源压完接近原大小（实测 1.1 GB → 1.0 GB，仅 11%）
  - x264 CRF 自适应对静止画面几乎不耗码率：同批录屏实测压缩比 80-88%、速度 12-20x 实时，快于硬件路径
  - 显式 `--codec` 优先级最高，始终尊重用户选择；探测失败回落硬件默认
- **输出防覆盖**（`compress.py`）：输出文件已存在时自动改用 `_compressed_2.mp4` 序号递增，新增 `--overwrite` 才允许覆盖，不再静默毁掉旧压缩结果

### 修复

- **Python 3.9 兼容**：三个脚本补充 `from __future__ import annotations`。此前 `dict | None` 等注解语法在系统默认 python3（macOS 自带 3.9）下直接 `TypeError` 崩溃，必须手动找 python3.10+ 才能运行

### 文档完善

- SKILL.md 新增"录屏/课件源码率陷阱"说明：先 `ffprobe` 查源码率再选编码器，附 60 秒采样估算法
- 依赖表中 Python 版本要求从 ≥3.10 放宽到 ≥3.9

### 踩坑复盘

本次修复源于 2026-09-15 两个录屏压缩任务（1.1 GB + 1.3 GB）：

1. **默认硬件路径压低码率源几乎无效**：Apple Silicon 自动选择命中 hevc_vt，14.54.48 录屏（源 1.5 Mbps）第一版仅压缩 11%，白跑 18 分钟
2. **历史决策无声丢失**：D-2026-06-29-02 记录"默认统一 x265、硬件 opt-in"，但该改动未随 v1.4.0 的 `hw_detect.py` 重写入库，代码实际仍是"Apple Silicon 默认硬件"，且无人发现。本次以码率感知选择取代"全默认 x265"方案：高码率源保留硬件速度优势，低码率源自动走 CRF
3. **长视频压缩进程两次被杀**：前台运行被会话 420 秒超时连带终止；Hermes 托管后台任务整体收到 SIGTERM（exit -15）。两残缺输出均无 moov atom。教训：**凡是预期超过几分钟的编码，一律 `--detach`**，ffmpeg 脱离进程组后第三次顺利完成
4. **`-y` 静默覆盖旧输出**：重跑压缩时无声覆盖了上一版结果（万幸旧版压缩比差本无保留价值，但行为本身危险），已由防覆盖机制修复

### 验证

- python3.9 编译三个脚本通过；低码率端到端自动选 x264 ✓；重复运行输出 `_compressed_2` ✓；`--overwrite` 覆盖 ✓；`select_profile` 五个分支单测（低/高码率、3.0/3.1 边界、显式 codec 优先、探测失败回落）全过 ✓

---

## [1.4.0] - 2026-08-24

### 新增

- **`ffmpeg_smoke_test()`**（`scripts/hw_detect.py`）：脚本启动前验证 ffmpeg 二进制能否正常运行
  - 检测 dyld Library not loaded 等 brew 依赖冲突，崩溃时立即输出诊断信息和 `brew upgrade ffmpeg` 修复命令
  - 不再让 `ffmpeg -encoders` 静默 fallback 到会同样崩的软件编码
  - 完整诊断日志写入 `/tmp/ffmpeg_smoke_test_*.log`
- **`--detach` 模式**（`compress.py` 和 `trim_silences.py`）：脚本启动 ffmpeg 后立即返回，进程脱离会话组（`start_new_session`）
  - 兜底机制，父进程被杀不影响编码
  - 输出 `PID=<pid> 日志=<path>`，可用 `tail -f` 跟进
  - 默认行为不变，保留 agent 介入诊断能力

### 变更

- **完整 stderr 日志**（`compress.py` / `trim_silences.py`）：失败时保存完整 stderr 到 `/tmp/ffmpeg_<视频名>_<时间戳>.log`，不再截断 500 字符丢失关键诊断信息
- **VideoToolbox 并发数调优**：`_profile_hevc_vt()` 和 `_profile_h264_vt()` 的 `optimal_workers` 从 3 改为 1
  - Apple Silicon 的 VideoToolbox 是共享硬件编码器，多 ffmpeg 进程并行争抢会让单任务速度从 2-3x 降到 1-1.5x
- **SKILL.md 文档诚实标注**：1080p60 实测约 2-5x 实时（非原宣传 5-15x），3 小时视频约需 50 分钟
- **新增故障排查章节**：覆盖 dyld Library not loaded 等环境崩溃场景的诊断与修复

### 踩坑复盘

本次修复源于一次 6.1GB 视频压缩任务：

1. ffmpeg 8.1 二进制因 x265 升级未重新链接，启动即崩，脚本却 fallback 到 x264 继续报错
2. 升级 ffmpeg 后用 Python 包装进程同步等结果，Claude Code 会话超时停止包装进程，孤儿 ffmpeg 被 SIGHUP 杀死，输出文件无 moov atom 不完整
3. agent 反复 `ps`/`ls`/`tail` 轮询进度浪费上下文

修复后的正确流程：
- 长视频主动加 `--detach`：脚本输出 PID + 日志，agent 可立即返回
- ffmpeg 崩溃：smoke test 5 秒内给出 dyld 符号 + brew 修复命令
- 失败诊断：完整 stderr 日志，不再被截断丢信息

---

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
