---
name: tingwu-asr
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "0.4.5"
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
- `playwright` (登录时) — 内置登录脚本 `login_pw.py` 使用（`pip3 install playwright && playwright install chromium`）

安装:
```bash
pip3 install -r skills/tingwu-asr/config/requirements.txt
```

## 首次使用：登录（首选：内置 Playwright 脚本）

**方式一（推荐）**：skill 内置 `login_pw.py`，一条命令完成"开浏览器 → 自动填凭证 → 等
登录 → cookie 落盘"：

```bash
python3 skills/tingwu-asr/scripts/login_pw.py
```

- 凭证从 `config/.env` 读取（从 `config/.env.example` 复制填写）
- 浏览器以可见窗口打开；若出现滑块/验证码，人工在窗口内完成即可，脚本自动轮询等待
- 脚本通过 `context.cookies()` 取 cookie（含 HttpOnly 的 `login_aliyunid_ticket`），
  **直接写入** `config/cookies.json`，cookie 值不经过 stdout/对话记录
- 完成后可用 `check_auth.py` 验证登录态

**方式二（备用）**：Agent 用 MCP Playwright 浏览器工具手工流程：

1. 用 MCP Playwright 打开 `https://tingwu.aliyun.com/home`
2. 如果跳转到登录页，用账号密码或扫码登录
3. 登录成功后，将提取的 cookie 保存到文件（注意 `document.cookie` 拿不到 HttpOnly
   cookie，仅作兜底）：
   ```bash
   python3 skills/tingwu-asr/scripts/login.py --save-cookies '{"cna":"xxx",...}'
   ```

账号密码可预配置在 `config/.env` 文件中（从 `config/.env.example` 复制）。

## 每日签到（领取免费额度）

每天登录听悟网页可领取 2 小时免费转录额度。Agent 签到流程：

1. 运行内置登录脚本（会打开 `https://tingwu.aliyun.com/home` 触发每日额度并保存 Cookie）：
   ```bash
   python3 skills/tingwu-asr/scripts/login_pw.py
   ```
2. 运行检查脚本确认状态：
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
# 直接给链接(自动 yt-dlp 下载,默认多人分离):小宇宙/YouTube/B站等
python3 skills/tingwu-asr/scripts/transcribe.py "https://www.xiaoyuzhoufm.com/episode/xxx"

# 单文件转录(默认多人分离)
python3 skills/tingwu-asr/scripts/transcribe.py /path/to/audio.mp3 --lang cn

# 多文件并行转录（自动保存到文件所在目录 + archive 目录）
python3 skills/tingwu-asr/scripts/transcribe.py /path/to/audio1.mp3 /path/to/audio2.mp3 /path/to/video.mp4

# 批量转录目录下所有文件（并行）
python3 skills/tingwu-asr/scripts/transcribe.py /path/to/media_folder/ --batch

# 指定并行数（默认3）
python3 skills/tingwu-asr/scripts/transcribe.py /path/to/audio1.mp3 /path/to/audio2.mp3 --parallel 5
```

参数说明:
- `paths` 音频/视频文件路径**或链接**（http(s) 开头自动用 yt-dlp 下载到临时目录；支持小宇宙/YouTube/B站等；支持多个混用）
- `--lang cn` 语言: cn(中文,默认) / en(英文) / ja(日文) / cant(粤语) / cn_en(中英混合)
- `--speakers` 说话人分离: 2=区分发言人(**默认**,实测唯一有效值,分 2 人) / 0=不区分 / 1=单人。**注:3 与 4 实测均无效(不分离),原"4=多人"为误注**
- `--batch` 批量转录目录下所有文件
- `--parallel N` 并行转录的最大文件数 (默认: 3)
- `--force` 强制重新上传，即使该文件已有转录结果（默认会跳过已转录的文件）
- `-o output.md` 指定输出路径（单文件模式）
- `--no-archive` 不保存归档
- `--no-lab` 不获取智能分析（关键词/议程/重点等）
- `--ppt` 下载 PPT 幻灯片图片并嵌入 Markdown（仅视频有效）

**关于「给链接转写」与说话人分离（重要设计取舍）**：传入链接时，skill 走「yt-dlp 下载 → 本地上传」路径，以保证说话人分离生效。听悟网页端的「播客链接转写」(底层 net_source 网络源通道)虽能省本地带宽，但实测其「区分发言人」选项不生效（提交时 roleSplitNum 被强制为 0，不做分离）。此外经实测，听悟 roleSplitNum **仅 `2` 为有效分离值（分 2 人）**，`0/1/3/4` 均不分离（原 skill 注释"4=多人"为误注，已更正）。故 skill 默认 `--speakers 2` 走本地上传通道，换取可靠的 2 人分离，代价是下载+上传的带宽。如只需纯文字稿不在乎分离，可自行调用听悟网页端播客链接转写。

### 3. 输出说明

转录结果会同时保存到两个位置：
1. **源文件所在目录**：例如 `/path/to/audio.mp3` → `/path/to/audio.md`
2. **archive 归档目录**：`archive/YYYYMMDD_HHMMSS_audio/audio.md`

这样做的好处是：
- 源文件目录方便直接访问
- archive 目录便于集中管理和备份

**PPT 幻灯片**: 视频文件会自动提取 PPT 幻灯片，图片保存在 `{文件名}_slides/` 子目录中（每个文件独立目录，避免同目录下多视频冲突）。

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

### 2. 后台监控（按 Agent 运行时选择）

监控进程的生命周期是关键差异点：**Agent 的后台进程普遍随会话结束被回收**（Hermes 会话切换界面、Claude Code 会话退出同理）。监控一死，Agent 就收不到"转录完成"信号，长任务静默搁浅。因此分两档：

**档位 A — 会话无关监控（推荐，长任务首选）**：让监控完全脱离 Agent 会话，进度写日志文件，Agent 回来只读状态、不持有进程。

```bash
# Claude Code / 任意运行时：nohup 脱离会话，日志落盘
nohup python3 skills/tingwu-asr/scripts/poll_tasks.py --monitor --timeout 7200 --interval 120 \
  >> /tmp/tingwu_monitor.log 2>&1 &

# 单任务高频盯梢（含 macOS 原生通知）：watch_active.sh 本身就是会话无关的
nohup bash skills/tingwu-asr/scripts/watch_active.sh <task_id> >> /tmp/tingwu_watch.log 2>&1 &
```

Agent 恢复会话后按此顺序接管（不重新提交任务）：

1. `cat skills/tingwu-asr/config/pending_tasks.json` — 非空即有未完任务，拿 trans_id
2. `python3 skills/tingwu-asr/scripts/poll_tasks.py`（一次性）— 已完成则当场触发 finish_task 收尾（下载 PPT/生成 Markdown/归档），未完成则打印状态与预计剩余时间
3. finish_task 收尾可能耗时数分钟（185 张幻灯片下载+压缩实测约 3 分钟）：**用后台运行且不要设短超时**，或改用 watch_active.sh 接管
4. 需要持续监控再启动档位 A/B，重跑安全幂等（flock 防并发重复归档）

**档位 B — Agent 托管后台进程**：适合 Agent 会话确定存续的短等待。

- Claude Code：Bash 工具 `run_in_background: true` + `timeout: 600000`（必须 10 分钟，默认 2 分钟会掐断 finish_task）
- Hermes：`terminal(background=true)` 提交 + process_manage 轮询等待；会话切界面/退出后进程会被回收，此时回到恢复流程第 1 步

**无论哪档，重跑 poll_tasks.py 都是安全的**：任务状态以云端为准，pending_tasks.json 有 flock 互斥，不会重复转录、不会重复归档。进程丢失≠任务丢失。

### 3. 手动查询

```bash
# 检查所有待处理任务的状态（已完成会当场收尾并打印输出路径）
python3 skills/tingwu-asr/scripts/poll_tasks.py

# 阻塞式监控
python3 skills/tingwu-asr/scripts/poll_tasks.py --monitor
```

## 注意事项

- Cookie 会过期，过期后需重新运行 `login.py`
- 网页端免费额度有限，大文件或高频使用可能触发风控
- 支持格式: mp3/wav/m4a/wma/aac/ogg/amr/flac/aiff/mp4/wmv/mov/mkv/webm/avi 等
- 音频最大 500M，视频最大 6G，单文件最长 6 小时
- 代理环境下 OSS 上传可能中断：本机 shell 常驻 `HTTP_PROXY/HTTPS_PROXY`（如 Clash 系）时，
  oss2 上传会走代理，大文件分片上传易被代理掐断长连接（实测 771MB 视频在 50% 处
  `ProxyError: Cannot connect to proxy`）。听悟 OSS 为国内节点，无需代理，上传前剥掉：
  `unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy`
- macOS Apple Silicon 上 `cryptography<=41` 的 `_rust.abi3.so` 在 OpenSSL CPU 探测
  （`_armv8_sve_probe`）时会死循环挂起，症状是任何 import oss2 的脚本无输出卡死。
  已在 `tingwu.py` 入口自动设置 `OPENSSL_armcap=0` 绕过；若仍遇到，运行前手动
  `export OPENSSL_armcap=0`，或升级 cryptography>=42。
