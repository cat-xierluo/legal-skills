# douyin-content-manager 定时任务

> 抖音视频内容管理:下载 → 压缩 → 转录(FunASR)→ 纠错(DeepSeek) 一条龙,每天凌晨自动跑。
> 入口 skill:`private-skills/douyin-content-manager/`(symlink 独立仓库,提交去 private-skills 真仓库)。

## 当前状态 (2026-07-15)

- **活跃 cron**: `2fe76c31-3cf0-48c9-b132-80425b841690`,name "douyin 下载+转录 每日一条龙"
- **schedule**: `20 3 * * *` Asia/Shanghai(**实测触发偏晚 ~40min-1h**,MyAgents cron 引擎层 bug,无法外部修;7/14 实际 04:02 触发)
- **已实跑**: 7/14 一次(2540s≈42min ✓ 成功),下次 7/15 03:20
- **prompt 文件**: `private-skills/douyin-content-manager/config/cron-prompt.txt`(稳定路径,不放 /tmp)
- 两步:Step1 `batch-download.py --all --yes`(用 `.venv/bin/python`,F2 框架)+ Step2 `content_manager_pipeline.py`(系统 python3,FunASR 自启停)

## 关联脚本

- 下载:`skills/douyin-batch-download/scripts/batch-download.py`(--all/--sample/--uid;--yes 跳确认;--daemon 后台)。依赖 `.venv`(f2 0.0.1.7),Cookie 在 `config/config.yaml`(有效期~2026-09)。博主名单真值源是 `douyin_users.db`(24 博主,含 peer_type)
- Pipeline:`private-skills/douyin-content-manager/scripts/content_manager_pipeline.py`(端到端状态机,定时任务友好)。followed 视频压缩,peer 保留原画质;FunASR 离线自启 `--preload` 跑完自停
- 纠错:`correct_transcript.py`(DeepSeek-V3.2 主力 + Qwen3.5-9B fallback)
- 同步:`sync-following.py`(2026-07-12 重构:从 db 全量重建 following.json,不再扫空目录;commit b489bcb)

## 踩过的坑 (按重要性)

### 1. MyAgents `cron update --prompt-file` 静默失败 (2026-07-13 发现)
报 `✓ Updated` 但 prompt 实际没写回(还是旧版)。**改 prompt 必须删了用 `cron add --prompt-file` 重建**,别信 update。验证方法:建完立即 `cron list --json` 查 prompt 内容。
- 本次 session 中招:update 后以为 prompt 更新了,实际还是单步版(只转录没下载),直到查 JSON 才发现。

### 2. cron 时区:必须带显式 tz,且触发仍偏晚 (2026-07-12/13)
- `--schedule "20 3 * * *"`(裸表达式)会被当 **UTC** 解释 → 实际跑在 11:20(差 8h)
- `--schedule '{"kind":"cron","expr":"20 3 * * *","tz":"Asia/Shanghai"}'` 才对
- 但即使带 tz,**实测触发仍比 schedule 晚 ~40min-1h**(7/14: 03:20→04:02;book-ocr: 03:00→04:00)。引擎层 bug,无法外部修,只能接受。
- 同期修了 2 个被 UTC 误伤的:douyin(11:20→03:20)、skill-showcase 轮换(12:30→04:30)

### 3. httpx + Python3.14 解析 NO_PROXY 里 `[::1]` 抛 Invalid port (2026-07-12 修)
- 现象:`correct_transcript` 报 `Invalid port: ':1]'`,所有纠错失败(不阻塞转录)
- 根因:httpx 默认 `trust_env=True` 读 NO_PROXY,把 IPv6 字面量 `[::1]` 误当 host:port 解析
- 修复:`correct_transcript.py` 创建 openai client 时传 `http_client=httpx.Client(trust_env=False)`(调公网 API 本不需本地代理)
- 验证:DeepSeek-V3.2 真实调用成功(952+304 tokens)。**未提交**(session 中改完没 commit)

### 4. F2 框架默认 Bark 推送报错(无害噪音)
下载结尾报 `Bark 通知发送失败 / https://api.day.app/ 405`(没配 Bark key)。无害,不影响下载。cron prompt 已注明忽略。

### 5. 重命名冲突容错(用户担心,未复现)
用户有个"重命名/改旧数据"任务(未定位,可能手动会话)。pipeline prompt 加了 FileNotFoundError 容错:文件被占用就跳过不中断。

## 与其他 cron 的资源错峰

凌晨时段密集(均 Asia/Shanghai,实际触发晚 ~1h):
- 02:00/02:30 Self Evolve 系列
- 03:00 daily-book-ocr(连续超时失败,3600s timeout)
- 03:10 Self Evolve 历史回填
- **03:20 douyin 下载+转录**(本任务)
- 04:30 skill-showcase 轮换

douyin 与 book-ocr 都吃资源(FunASR/OCR),错峰 20min,但 book-ocr 常超时到 04:00,可能仍与 douyin 实际触发(04:02)撞上——观察中。

## 待办

- [ ] correct_transcript.py 的 trust_env 修复**未提交**,需 git-batch-commit
- [ ] 观察 douyin 实际触发时间是否稳定偏晚(确认引擎 bug 规律)
- [ ] 定位用户的"重命名任务",如确与抖音目录冲突则进一步错峰或加文件锁
