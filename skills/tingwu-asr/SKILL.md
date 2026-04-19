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
pip3 install -r skills/tingwu-asr/assets/requirements.txt
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

账号密码可预配置在 `.env` 文件中（从 `assets/.env.example` 复制）。

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
python3 skills/tingwu-asr/scripts/transcribe.py /path/to/audio.mp3 --lang cn --speakers 4
```

参数说明:
- `--lang cn` 语言: cn(中文,默认) / en(英文) / ja(日文) / cant(粤语) / cn_en(中英混合)
- `--speakers 4` 说话人: 0(不区分) / 1(单人) / 2(两人) / 4(多人,默认)
- `--batch` 批量转录目录下所有文件
- `-o output.md` 指定输出路径

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
  .env                  ← 账号密码凭证（gitignore，不提交）
  scripts/
    tingwu.py           ← 核心 API 客户端
    transcribe.py       ← CLI 入口
    format_output.py    ← 听悟 JSON → Markdown 转换
    login.py            ← Cookie 保存工具
    daily_checkin.py    ← 额度检查 + 记录
    check_auth.py       ← 认证检查
  config/
    cookies.json        ← 登录 Cookie（gitignore，不提交）
    quota_history.jsonl ← 额度变更记录（gitignore，不提交）
  assets/
    requirements.txt    ← Python 依赖
    cookie.example.json ← Cookie 文件模板
    .env.example        ← 账号密码模板
  references/           ← API 文档和决策记录
  archive/              ← 转录结果归档
```

## 注意事项

- Cookie 会过期，过期后需重新运行 `login.py`
- 网页端免费额度有限，大文件或高频使用可能触发风控
- 支持格式: mp3/wav/m4a/wma/aac/ogg/amr/flac/aiff/mp4/wmv/mov/mkv/webm/avi 等
- 音频最大 500M，视频最大 6G，单文件最长 6 小时
