# CHANGELOG

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
