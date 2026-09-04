# CHANGELOG

## [0.2.0] - 2026-09-04

### 新增

- **创建前查重更新**：SKILL.md 核心流程第 4 步改为「查重与写入（更新还是新建）」——先查当天已有事件，唯一匹配则更新，不重复新建。解决用户补充机票/酒店/改签信息时被重复建事件的痛点（0.1.x 只有创建路径）。
- `scripts/find_event.sh`：按日期窗口(+可选标题关键词)查已有事件，输出 uid/日历/起止/标题/地点/备注；日历名传 `ALL` 遍历所有日历；无匹配退出码 0（查重语义）。
- `scripts/update_event.sh`：修改已有事件——按 UID 精确匹配，匹配不到按标题关键词兜底；标题命中多个时**拒绝修改**并返回候选（防误改）；第 2–6 参数传 `-` 表示不改该项。
- SKILL.md 查重匹配规则：同日 + 标题含相同关键标识（航班号/车次/案号）或时间相近 ±3h 视为同一事件；多个候选列给用户选不猜；走了更新路径不再重复建提醒。
- SKILL.md 明确 **lead_times 就是个人配置入口**：用户表达「提醒太多/只要提前 3 小时」类偏好时写入 config.json 长期生效，不要每次口头覆盖。
- SKILL.md 新增 **一次出差 = 一个日历事件** 规则：去程/住宿/返程合并进一个事件（起止=去程出发→返程落地，标题=行程名，细节分层进备注），不按交通/住宿拆多条；提醒按行程内关键节点（每个航班前 3h 等）建。
- `update_event.sh` 搜索默认带时间窗（`[今天-7天, 今天+400天]`），全量遍历日历极慢的问题可用 `BACK_DAYS`/`AHEAD_DAYS` 环境变量调节。

### 踩坑记录（AppleScript）

- 变量名 `nd` 会导致语法错误（`set nd to 5` 都不编译），命名避开；改用 `newStart` 通过。
- 改事件日期：组件必须先 `day=1` 再 year/month/day；**禁止**用「day=9, hours=0 再减 N 小时」表示当天稍早时刻——减法跨天回退会把两天行程压进一天。
- Reminders 大清单上 `whose name is` 精确匹配极慢（可超时）；用 `due date` 窗口过滤再在循环里比对名称，快一个量级。
- 往 AppleScript 注入多行文本：换行只能在**行间**转 `" & linefeed & "` 拼接；每行都追加会让单行字段（如 UID 关键词）尾部带上换行符，等值匹配静默失败（NOT_FOUND 假象）。

## [0.1.2] - 2026-08-25

### 修正

- ClawHub 发布元数据：v0.1.1 首次发布漏传 `--name`，display name 退化为临时目录名 `Clawhub Publish Apple Smart Schedule`。bump 版本带 `--name "苹果智能日程提醒"` 重新发布，修正为正确显示名。本地 skill 本身无功能改动。

## [0.1.1] - 2026-08-25

### 修复

- `scripts/create_event.sh` / `scripts/create_reminder.sh`：日历/清单查找由 `if exists ... else` 改为 `try/on error` 容错（`first calendar whose name is ...` / `first list whose name is ...`）。修复部分 macOS 状态（系统首次提示未授权、名称含特殊字符）下偶发的 -1728 误报「找不到」——命中失败直接回退 default list / 第一个日历，保留「找不到时落到默认」行为并打印 warning。

## [0.1.0] - 2026-07-15

### 新增

- 首版 `apple-smart-schedule`：把一句自然语言（机票/高铁/开庭/会议/截止/聚会/看病等）或一张票据截图，自动变成苹果「日历」事件 + 按事件类型智能提前的「提醒事项」。
- 5 个脚本：
  - `scripts/create_event.sh`（osascript 建日历事件，python3 解析日期规避 locale 坑）
  - `scripts/create_reminder.sh`（remindctl 优先，未装则 osascript 降级）
  - `scripts/list_calendars.sh` / `list_reminder_lists.sh`（列日历/清单名，供首次配置）
  - `scripts/setup_check.sh`（首次自检 + 授权指引）
- `config/config.json`：时区、默认日历/清单、各类事件提前量（flight/train/court/meeting/deadline/social/default）。
- `references/lead-times.md`：事件类型判断规则 + 提前量格式 + 航班/高铁字段录入模板。

### 约定

- 仅 macOS 运行；建好的日历/提醒经 iCloud 同步到 iPhone/iPad。
- 航班/高铁备注只录行程有用字段（航司/舱位/机型/时长、车次/检票口/座位），**不录**乘客/票号/订单号。
- 首次在每个终端运行会弹授权窗，点「好」即可（授权按调用的终端分别记录）。
