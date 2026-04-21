---
name: tingwu-asr
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "0.1.0"
license: MIT
description: 使用阿里云通义听悟进行云端音频/视频转录。本技能应在用户需要云端语音转文字、长音频转录、本地 FunASR 不可用或需要更高精度时使用。不适用于无网络环境或需要完全离线的场景。
---

# 通义听悟云端转录 (tingwu-asr)

通过逆向封装通义听悟网页端内部 REST API，实现云端音频/视频文件转录，输出与 `funasr-transcribe` 兼容的 Markdown 格式。

## 功能

- 上传本地音频/视频文件到阿里云 OSS
- 云端转录，支持说话人分离（单人/2人/多人）
- 支持中文、英文、日文、粤语、中英文混合
- 输出 funasr-transcribe 兼容的 Markdown，可直接用 `summary.py` 注入 AI 总结

## 依赖

- Python 3.8+
- `requests` (必须) — HTTP 请求
- `oss2` (必须) — 阿里云 OSS SDK（STS 直传）

安装:
```bash
pip3 install -r skills/tingwu-asr/config/requirements.txt
```

## 首次使用：登录（通过 MCP Playwright）

登录需要 Agent 使用 MCP Playwright 浏览器工具完成：

1. 用 MCP Playwright 打开 `https://tingwu.aliyun.com/home`
2. 如果跳转到登录页，用账号密码或扫码登录
3. 登录成功后，用 `browser_evaluate` 提取 cookie：
   ```javascript
   () => document.cookie
   ```
4. 将提取的 cookie 保存到文件：
   ```bash
   python3 skills/tingwu-asr/scripts/login.py --save-cookies '{"cna":"xxx","login_aliyunid_ticket":"xxx",...}'
   ```

账号密码可预配置在 `config/.env` 文件中（从 `config/.env.example` 复制）。

## 每日签到（领取免费额度）

每天登录听悟网页可领取 2 小时免费转录额度。Agent 签到流程：

1. 用 MCP Playwright 打开 `https://tingwu.aliyun.com/home`（触发每日额度）
2. 提取并保存 Cookie（同登录步骤 3-4）
3. 运行检查脚本确认状态：
   ```bash
   python3 skills/tingwu-asr/scripts/daily_checkin.py
   ```

可在 OpenClaw 中配置定时任务，让 Agent 每天自动执行此流程。

## Agent 工作流

当用户要求转录音频/视频文件时，执行以下步骤：

### 1. 检查登录状态

```bash
python3 skills/tingwu-asr/scripts/check_auth.py
```

如果返回"无效"，先运行 `login.py`。

### 2. 执行转录

```bash
# 单文件转录
python3 skills/tingwu-asr/scripts/transcribe.py /path/to/audio.mp3 --lang cn --speakers 4

# 多文件并行转录（自动保存到文件所在目录 + archive 目录）
python3 skills/tingwu-asr/scripts/transcribe.py /path/to/audio1.mp3 /path/to/audio2.mp3 /path/to/video.mp4

# 批量转录目录下所有文件（并行）
python3 skills/tingwu-asr/scripts/transcribe.py /path/to/media_folder/ --batch

# 指定并行数（默认3）
python3 skills/tingwu-asr/scripts/transcribe.py /path/to/audio1.mp3 /path/to/audio2.mp3 --parallel 5
```

参数说明:
- `paths` 音频/视频文件路径（支持多个文件并行转录）
- `--lang cn` 语言: cn(中文,默认) / en(英文) / ja(日文) / cant(粤语) / cn_en(中英混合)
- `--speakers 2` 说话人: 0(不区分) / 1(单人) / 2(两人,默认) / 4(多人)
- `--batch` 批量转录目录下所有文件
- `--parallel N` 并行转录的最大文件数 (默认: 3)
- `-o output.md` 指定输出路径（单文件模式）
- `--no-archive` 不保存归档
- `--no-lab` 不获取智能分析（关键词/议程/重点等）
- `--ppt` 下载 PPT 幻灯片图片并嵌入 Markdown（仅视频有效）

### 3. 输出说明

转录结果会同时保存到两个位置：
1. **源文件所在目录**：例如 `/path/to/audio.mp3` → `/path/to/audio.md`
2. **archive 归档目录**：`archive/YYYYMMDD_HHMMSS_audio/audio.md`

这样做的好处是：
- 源文件目录方便直接访问
- archive 目录便于集中管理和备份

### 3. 生成 AI 总结（复用 funasr-transcribe）

转录完成后，复用 funasr-transcribe 的 summary 模块:
```bash
python3 skills/funasr-transcribe/scripts/summary.py inject transcript.md summary.json
python3 skills/funasr-transcribe/scripts/summary.py verify transcript.md
```

## 文件结构

```
skills/tingwu-asr/
  SKILL.md              ← 本文件
  scripts/
    tingwu.py           ← 核心 API 客户端
    transcribe.py       ← CLI 入口
    format_output.py    ← 听悟 JSON → Markdown 转换
    login.py            ← Cookie 保存工具
    daily_checkin.py    ← 额度检查 + 记录
    check_auth.py       ← 认证检查
  config/
    .env                ← 账号密码凭证（gitignore，不提交）
    .env.example        ← 账号密码模板
    cookies.json        ← 登录 Cookie（gitignore，不提交）
    cookie.example.json ← Cookie 文件模板
    quota_history.jsonl ← 额度变更记录（gitignore，不提交）
    requirements.txt    ← Python 依赖
  references/           ← API 文档和决策记录
  archive/              ← 转录结果归档
```

## 异步转录模式（推荐用于长视频）

对于 1 小时以上的长视频，转录可能需要 20-30 分钟。使用异步模式上传后立即返回，后台自动轮询。

### 1. 异步提交

```bash
python3 skills/tingwu-asr/scripts/transcribe.py /path/to/video.mp4 --async --speakers 2
```

上传完成后立即返回任务 ID，任务信息保存到 `config/pending_tasks.json`。

### 2. 后台监控（Claude Code 增强模式）

提交后，用 `Bash` 工具的 `run_in_background` 启动后台监控：

```
command: "python3 skills/tingwu-asr/scripts/poll_tasks.py --monitor --timeout 3600 --interval 120"
run_in_background: true
timeout: 600000
```

**注意**：`timeout` 必须设为 `600000`（10 分钟），否则默认 2 分钟会超时。

监控完成后会自动收到通知，此时展示转录结果路径给用户。

### 3. 手动查询

```bash
# 检查所有待处理任务的状态
python3 skills/tingwu-asr/scripts/poll_tasks.py

# 阻塞式监控
python3 skills/tingwu-asr/scripts/poll_tasks.py --monitor
```

## 注意事项

- Cookie 会过期，过期后需重新运行 `login.py`
- 网页端免费额度有限，大文件或高频使用可能触发风控
- 支持格式: mp3/wav/m4a/wma/aac/ogg/amr/flac/aiff/mp4/wmv/mov/mkv/webm/avi 等
- 音频最大 500M，视频最大 6G，单文件最长 6 小时
