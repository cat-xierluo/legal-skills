# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/lang/zh-CN/).

## [0.4.4] - 2026-09-16

### 修复
- `tingwu.py` / `browser_auth.py`：macOS Apple Silicon 上 `cryptography<=41` 的 `_rust.abi3.so` 在 OpenSSL CPU 探测（`_armv8_sve_probe`）死循环，任何 import oss2 的脚本无输出挂死（dlopen 阶段）。入口自动设置 `OPENSSL_armcap=0` 绕过；`browser_auth.py` 被 MCP Playwright 单独加载，补同款防护
- `transcribe.py` / `poll_tasks.py`：AI 总结环节每次必报「总结文件不存在」——`summary.py inject` 需要 Agent 预先生成 `{out}.json`（prompt → LLM → inject），纯脚本 runtime 里 json 不存在属正常态。改为三分支：无 json 打印延后提示、有 json 真实注入并校验 rc、summary.py 缺失时跳过。顺带子进程 `python3` 改 `sys.executable`（venv/其他解释器 runtime 下不再错调系统 Python）

### 新增
- `poll_tasks.py` 落地 9ae3c71f 预定但从未实现的软错误识别：后端把拒绝类错误（如「仅支持16k及以上采样率文件」）归到 status=2（名义"转录中"），仅看 status 会无限轮询（2026-06-22 抖音无声视频真实案例）。从 statusMsg 关键词识别，命中即判失败并记录 `后端拒绝(status=2): ...`
- `poll_tasks.py` 补 `check_once(task_id_filter=)` 签名与 CLI `--once` / `--task-id` 参数——watch_active.sh 一直调用的就是这组参数，此前 argparse 直接报错；过滤模式下写回 pending 按 trans_id 剔除，不再误抹其他任务
- `tests/test_summary_flow.py`：AI 总结三分支回归测试（无 json / 有 json 真实注入 / verify 校验）

### 验证
- 65 分钟培训视频全流程实测（261MB，说话人 2 分离，56 张幻灯片，17,460 字）
- 存量 4 个 poll_tasks 单测从全挂到 4/4 通过；新增 summary 三分支测试 ALL PASS；watch_active.sh `bash -n` 语法通过

## [0.4.3] - 2026-09-13

### Fixed
- `poll_tasks.py` / `tingwu.py` 修复异步任务刚提交即被误判"已完成"：实测听悟 `status=0` 有二义性（刚提交、转录未开始 与 真正完成 均为 0），原 `status in (0, 3)` 判定在提交后首轮轮询就拉取空结果，生成空 Markdown 并写入空归档
- 完成判定改为 `status == 3 or (status == 0 and transStartTime 已设置)`；transStartTime 在转录实际开始后才会下发，可区分"刚创建"与"已完成"
- 状态标签同步修正：`0` 显示为"已提交，待转录开始"，`1` 显示为"排队中/转录中"

### 验证
- Vol21 全场回放（116 分钟）实测复现误判并修复后重新拉取：36,575 字、说话人 2 人分离、43 张幻灯片、章节索引覆盖 00:00–01:56:23
- 边界用例 5/5：刚提交（status=0 无 transStartTime）→ 未完成；转录中（status=1）→ 未完成；上传中（status=11）→ 未完成；status=3 → 完成；status=0 + transStartTime → 完成

## [0.4.2] - 2026-09-09

### Fixed
- `login_pw.py` 修复偶发 `[CMN.NotLogin]: 未登录`：此前保存 cookie 前仅固定等待 3 秒，SPA 第二批关键 cookie（`XSRF-TOKEN` / `JSESSIONID` / `arms_uid` / `_bl_uid` / `aliyun_lang` 等）尚未下发即落盘，导致 API 双重校验失败
- 保存前先导航 `/home` 并主动触发 `user/info`、`tingwu/account/info` 两个 API 暖机，促使第二批 cookie 下发（暖机失败不阻断，降级继续）
- 多轮 `ctx.cookies()` 轮询直到 cookie 数连续 2 轮稳定（阈值 ≥20，最多 20 轮 × 1.5s），覆盖分批下发窗口期
- 新增关键 cookie 校验：`login_aliyunid_ticket` / `login_aliyunid` / `XSRF-TOKEN` / `JSESSIONID` / `atpsida` / `isg`，缺失则 `sys.exit(4)` 并给出重试与排查提示
- cookies.json 新增 `verified_critical_cookies` 字段留痕，便于事后排错

### 验证
- 完整登录实测：抓到 26 个 cookie（此前仅 19 个），`check_auth.py` 返回账户信息

## [0.4.1] - 2026-08-24

### Fixed
- `poll_tasks.py` 并发安全：新增 `pending_lock()` 文件锁（`fcntl.flock`），`check_once()` 整体加锁后再读 pending_tasks.json，避免后台 monitor 与前台轮询同时检测到任务完成而**重复归档、重复写入 completed_tasks.json**。抢不到锁立即返回 `[]`，由 monitor 下一轮重试
- `tingwu.py` 标签修正：`submit_transcribe()` / `transcribe()` 输出从"任务ID"改为"听悟转录任务 ID"，避免被误读为 OSS 上传会话 ID

### 数据清理
- 移除 archive 下重复归档（同一 trans_id 双进程写入导致），以及 `completed_tasks.json` 中 7 条历史重复记录

## [0.4.0] - 2026-08-17

### Added
- 内置 Playwright 登录脚本 `scripts/login_pw.py`:一条命令完成"开浏览器 → 自动填 .env 凭证 → 等待登录 → cookie 落盘"。经 `context.cookies()` 取含 HttpOnly 的 `login_aliyunid_ticket`(此前的 MCP Playwright `document.cookie` 路径拿不到),cookie 值全程不经过 stdout/对话记录;出现滑块时人工在可见窗口完成即可
- SKILL.md 登录章节重写:内置脚本为方式一(推荐),MCP Playwright 手工流程降为方式二兜底;每日签到流程同步改用 `login_pw.py`
- `requirements.txt` 增加 `playwright`

### Fixed
- 补齐归档缺失 slides 的实操路径确认:听悟云端仅保留近期转录记录(一个月前的任务已从云端删除,`getAllLabInfo` 无法拉取),旧任务幻灯片的可靠恢复方式是**重跑转录**(视频自动提取 PPT)。2026-08-17 以一例 167 分钟培训视频实测重跑,98 张 webp(8.6MB)回填原归档,原 MD 的 98 处图片引用全部恢复;新归档同步保留

### 已知限制(补充)
- `poll_tasks.py --monitor` 生成输出时,slides 目录不会自动复制进 archive(与 transcribe.py 主流程的 save_archive 缺口同源),需 Agent 手动补齐并回写 meta

## [0.3.0] - 2026-07-19

### Added
- 给链接自动转录:`paths` 支持 http(s) 链接,自动用 yt-dlp 下载(小宇宙 episode、YouTube、B站等),无需手动下载音频
- SKILL.md 补充「链接转写与说话人分离」设计取舍说明

### Changed
- `--speakers` 默认值确认为 2:经实测听悟 roleSplitNum **仅 `2` 为有效分离值(分 2 人)**,`3` 与 `4` 均不分离(原注释"4=多人"为误注,已更正)
- `requirements.txt` 补充 yt-dlp 依赖

### 已知限制(Playwright 实测听悟网页端 API 确认)
- 听悟网页端「播客链接转写」(底层 net_source 网络源通道)的「区分发言人」选项**不生效**:即使选中"多人讨论",提交的 roleSplitNum 仍被强制为 0,结果不做分离。故 skill 给链接时走"yt-dlp 下载 → 本地上传"路径以保证分离生效
- roleSplitNum **仅 `2` 有效(分 2 人)**,`0/1/3/4` 实测均不分离

## [0.2.0] - 2026-04-20

### Added
- 多文件并行转录：支持传入多个文件路径，自动并行上传（最大并发数可通过 `--parallel` 参数控制，默认3）
- 转录结果双路径保存：结果同时保存到源文件所在目录和 archive 目录
- `--parallel N` 参数：指定并行转录的最大文件数

### Changed
- CLI 参数 `path` 改为 `paths`，支持多个文件路径
- 批量模式（`--batch`）下目录内的文件也会并行处理

## [0.1.0] - 2026-04-18

### Added
- 核心功能：通过逆向通义听悟网页端 REST API 实现云端音频/视频转录
- 完整 6 步 API 流程：generatePutLink → OSS STS 上传 → syncPutLink → startTrans → 轮询状态 → getTransResult
- 支持语言：中文、英文、日文、粤语、中英文混合
- 说话人分离：不区分 / 单人 / 两人 / 多人
- 输出 funasr-transcribe 兼容的 Markdown 格式
- Playwright Cookie 提取登录（`login.py`）
- Cookie 认证检查（`check_auth.py`）
- 批量转录模式（`--batch`）
- 转录结果归档到 `archive/` 目录
- 复用 funasr-transcribe 的 `summary.py` 注入 AI 总结
