---
name: douyin-topic-radar
description: 通过浏览器检索抖音关键词，采集搜索结果的结构化数据（点赞、评论、收藏、分享、精确发布时间、话题标签、相关搜索），计算话题热度信号与选题线索，生成候选短名单并下载作品，供后续对标拆解。用于“这个主题最近热不热”“同行都在拍什么”“帮我找几个能做的选题”。不要用于批量下载某个博主的全部作品（用 douyin-batch-download），也不要把结果当成平台官方流量数据。
license: MIT
metadata:
  version: "0.1.0"
  homepage: https://github.com/cat-xierluo/legal-skills
  author: 杨卫薪律师（微信ywxlaw）
---

# 抖音选题雷达

用已登录的浏览器打开抖音搜索页，按关键词采集作品级结构化数据，算出话题的时间分布、互动分布、高频标签和相关搜索，产出一份可读报告和一份可直接下载的短名单。数据只落本地。

## 它解决什么

输入一个主题（例如“律师案源”），回答三个问题：

1. 这个话题现在还有多少人在更新？近期占比多少？
2. 哪些作品和作者在承载互动？什么样的切入口最集中？
3. 值得下载下来逐条拆解的，是哪几条？

它不回答“搜索量是多少”——抖音不公开这个数字。报告里的热度是**可见观察值**，不是平台流量口径。

## 前置条件

- 已安装并可用 `ego-browser`，且浏览器里的抖音处于登录态。
- Python 3.10+，只用标准库。
- 需要下载时可选 `yt-dlp`；没有也能完成检索、报告和短名单。

登录态失效、出现验证码或人工验证时，调用 `task.handOff()` 停下来让用户处理，不要猜凭证或绕过。

## 执行流程

多步任务自建进度清单。`SKILL_DIR` 替换为本 Skill 的绝对路径，`WS` 是本次输出目录（建议 `~/.local/state/douyin-topic-radar/<主题>-<日期>`，不要放进媒体库或仓库）。

1. **定关键词**：主题词之外，补 2–5 个同义或长尾词（“律师案源”“律师如何找案源”“青年律师案源”）。一次只跑一个词也可以，但样本会偏窄。

2. **生成采集脚本**（每个关键词一次）：

   ```bash
   python3 "$SKILL_DIR/scripts/radar.py" driver --keyword "律师案源" \
     --mode comprehensive --rounds 6 --workspace "$WS"
   ```

   `--mode` 三选一：`comprehensive`（综合排序深滚，默认，样本最全）、`latest`（最新发布 + 一周内，看近期）、`top`（最多点赞，看存量爆款）。`--rounds` 每轮约新增 10–20 条。

3. **执行采集**。生成的脚本交给 ego-browser，输出路径由 `driver` 的回执给出：

   ```bash
   ego-browser nodejs < "$WS/drivers/<关键词>-<模式>.mjs"
   ```

   同一批的最后一个脚本加 `--finish` 生成，才会关闭 TaskSpace；中间的脚本保留页面，复用同一个 `--space-id` 更快。

4. **归一化**（多个关键词、多种模式一起）：

   ```bash
   python3 "$SKILL_DIR/scripts/radar.py" normalize --raw "$WS/raw/*.json" \
     --workspace "$WS" --topic "律师案源"
   ```

5. **算信号 + 出报告**：

   ```bash
   python3 "$SKILL_DIR/scripts/radar.py" rank --workspace "$WS" \
     --exclude-terms "请律师" "找律师"
   ```

   短名单在这一步就定下来，同时写入报告和 `shortlist.json`，是本流程唯一的短名单来源。短名单只收与主题相关的作品：要么直接命中主题词，要么命中至少两个主题片段。`--include-terms` 追加主题词，`--exclude-terms` 排除指定说法。每条入选作品都带 `matched_terms`，说明它为什么切题。

6. **出短名单和链接清单**：

   ```bash
   python3 "$SKILL_DIR/scripts/radar.py" shortlist --workspace "$WS"
   ```

   这一步复用第 5 步的短名单生成 `links.txt`，不会重新挑选。要换筛选条件，回到第 5 步重跑 `rank`。

7. **校验**（报告、短名单、链接三方一致才继续）：

   ```bash
   python3 "$SKILL_DIR/scripts/radar.py" verify --workspace "$WS"
   ```

8. **下载**（默认只打印计划，确认后再执行）：

   ```bash
   python3 "$SKILL_DIR/scripts/radar.py" download --workspace "$WS"
   python3 "$SKILL_DIR/scripts/radar.py" download --workspace "$WS" --execute
   ```

   `download --execute` 会先校验每条链接，再按作品 ID 回查本次新增或变化的媒体文件。回执里的 `verified` 才是真正取到媒体的数量，`media_path` 可直接交给转录环节；目标目录里运行前就存在的旧文件不会被计入。

## 产物

| 文件 | 内容 |
|---|---|
| `raw/*.json` | 原始采集结果，含每张卡片的完整字段 |
| `observations.jsonl` | 归一化、去重后的作品记录 |
| `signals.json` | 信号数据，供程序复用 |
| `candidates.md` | 给人看的报告 |
| `shortlist.json` | 入选作品与入选理由 |
| `links.txt` | 一行一个作品链接，供下载器消费 |
| `download_receipt.json` | 下载回执，含逐条 `media_path`、字节数与失败原因 |

## 判断口径

读 `candidates.md` 时按这个顺序：

1. 先看**口径与局限**，确认样本量、采集时间和模式。样本小于 20 条时结论只能当线索。
2. 看**时间分布**：近 30 天占比高说明话题在更新，适合做时效型内容；占比低说明存量为主，适合做长青体系。判断时效以**分采集模式的时间分布**里的综合排序为基线，「一周内」筛选的比例只在它自己那一列内有意义。
3. 看**互动分布**的中位数和 P90，而不是最大值——单条爆款会严重拉高均值。
4. 看**高频话题标签**里“出现次数 × 点赞中位数”都靠前的，那是这个话题真正的切入口。
5. 看**相关搜索**里的疑问式词，那是现成的选题句式。
6. **选题线索**是规则生成的初筛，必须人工判断后再用。

作者粉丝数、获赞数在搜索结果页常为 0，报告按缺失显示。需要准确值时另开作者主页核对，不要拿 0 当真实数据。

## 采集故障

- **首次点击被吞**：抖音搜索页导航完成后会吞掉第一下点击。驱动脚本对“打开筛选”和“选中筛选项”都做了点击后校验与重试，三次仍失败会抛错，此时按 `references/collection-notes.md` 排查。
- **卡片没有作品 ID**：抖音不在卡片 DOM 里输出作品 ID，采集器从页面组件数据读取。读不到时该卡片只参与聚合，不进短名单，也无法下载——报告里“无法读取 ID 的卡片”就是这一项。
- **滚动不再增长**：连续两轮卡片数不变就停止，`truncated` 为 `true` 说明没滚到底。
- **登录墙 / 验证码**：`task.handOff()`，交给用户。

## 后续衔接

- 拆解：把 `shortlist.json` 和下载目录交给 `lawyer-ip-teardown`，按平台识别后逐条拆解。
- 转录：下载后用 `local-asr` 出文字稿，再做对标分析。
- 沉淀：把值得长期跟踪的主题写进 `douyin-content-manager` 的素材库，下一轮复跑对比时间分布变化。

## 依赖

系统依赖：Python 3.10+、`ego-browser`；下载可选 `yt-dlp`。Python 包：无（全部标准库）。缺工具时报告缺口，不自动安装。

## 权限与安全

能力边界：

- **文件访问**：只写调用方通过 `--workspace` 与 `--out-dir` 指定的目录；不扫描主目录、不读媒体库、不碰浏览器 profile。
- **子进程**：只有 `download --execute` 会调用 `yt-dlp`，命令用参数数组传递，不经过 shell，不拼接不可信输入。其余子命令不启动任何外部进程。
- **网络**：Python 脚本不发起任何网络请求；抓取由 ego-browser 在已登录的浏览器里完成。
- **环境变量与凭据**：不读取 `os.environ`，不读取 `.env`、cookie 或令牌文件。

采集只读取当前已打开页面的 DOM 与页面组件数据，不发起额外网络请求，不读写浏览器 profile，不上传任何内容。输出目录由调用方指定，包含标题、作者昵称和作品链接，属本地私有材料。
