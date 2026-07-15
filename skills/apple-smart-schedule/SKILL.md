---
name: apple-smart-schedule
description: 把一句自然语言(机票/高铁/开庭/会议/截止日期/聚会/看病等)或一张票据截图，自动变成苹果「日历」事件 + 一串按事件类型智能提前的「提醒事项」。在 macOS 上运行、经 iCloud 同步到 iPhone/iPad。当用户说「帮我加个日程/提醒」「机票 MU5137 8:30 起飞提醒我」「下周三下午开庭提前提醒」「G1234 高铁」「上诉期 15 号截止」「提前 2 小时提醒我」「把这个行程加到日历」等任何要把时间安排写进苹果日历或提醒事项的场景，都必须用本 skill。仅 macOS。
---

# apple-smart-schedule · 苹果智能日程提醒

## ⚠️ 平台限制(先读)

本 skill **仅在 macOS 上运行**：它通过 `osascript`/`remindctl` 调用 Mac 自带的「日历」和「提醒事项」App 来创建日程。

- ✅ 创建结果经 **iCloud 自动同步**到你登录同一 Apple ID 的 iPhone / iPad。
- ❌ 不能直接在 Windows / Android / Linux 上用，也不能在 iPhone 上直接运行这些脚本。
- **授权（重要）**：首次运行脚本时，macOS 会弹出「xxx 想要控制「日历」/「提醒事项」」对话框，**点「好」即可**（只此一次）。**每换一个终端 App 或新环境首次用，都会再弹一次**——因为授权是按"调用的终端 App"分别记录的（Terminal 授权了不代表 iTerm 也授权了）；点过就好，无需去设置里找。只有当弹窗没出现、或曾经点过"不允许"时，才去「系统设置 › 隐私与安全性 › 自动化」把对应终端的 Calendar / Reminders 开关手动打开。

## 它做什么

用户用大白话说一件事（或发张截图），本 skill：

1. 解析出 **事件标题、开始时间、结束时间(可选)、地点、事件类型**；
2. 按事件类型套用 **默认提前量**（飞机/高铁/开庭/会议/截止/社交 各不同）；
3. 在苹果日历建 **1 个事件**，在提醒事项建 **一串提前提醒**；
4. 回执告诉用户建了什么。

通用场景（同一套逻辑，不限于出行）：

| 类型 | 示例输入 | 智能默认提前量 |
|---|---|---|
| ✈️ 航班 | "东航 MU5137 7/20 8:30 浦东起飞" | 前1天9点 + 前3h + 前1h |
| 🚄 高铁 | "G1234 北京南→上海虹桥 8/1 14:00" | 前1h + 前30min |
| ⚖️ 开庭 | "下周三 14:00 开庭" | 前1天9点 + 前3h + 前1h |
| 💼 会议 | "明天上午 10 点开会" | 前1天9点 + 前1h |
| ⏰ 期限 | "15 号上诉期截止" | 前3天 + 前1天 + 当天9点 |
| 🍻 社交 | "周五晚和张总吃饭" | 前1天9点 + 前2h |
| 🎯 其他 | "后天上午去体检" | 前1h |

## 核心流程（AI 执行步骤）

### 第 0 步：读配置（每次都要）

读 `$SKILL_DIR/config/config.json`，拿到：时区、默认日历名 `default_calendar`、默认提醒清单名 `default_reminder_list`、各类事件提前量 `lead_times`。
再读 `$SKILL_DIR/references/lead-times.md`，掌握**事件类型判断规则**和**提前量计算方法**。

### 第 1 步：解析输入

- **文字输入**：直接从用户消息提取 时间(日期+时分)、事件、地点、航班号/车次 等。
- **截图输入**（机票确认页、12306、微信邀约等）：用视觉能力读出上述字段。
- 时间按 `config.timezone`（默认 Asia/Shanghai）理解。含糊时（如"下周三"未指定时区、只说"下午"），按最常见理解并**在回执里点明你的理解**，让用户一眼能纠正。
- 没给结束时间 → 事件默认时长 60 分钟（会议/社交够用；航班/高铁若能推断时长更好）。

### 第 2 步：判断事件类型

按 `references/lead-times.md` 的关键词表归类到 `flight / train / court / meeting / deadline / social / default` 之一。一条消息可能含多个事件（如出差=航班+到达后会议），分别处理。

### 第 3 步：算出每条提醒的绝对时间

从 `config.lead_times[类型]` 取数组，按 `lead-times.md` 的格式规则把每条换算成**绝对时间**（ISO，Asia/Shanghai）。

**用户当次覆盖优先**：若用户明说"提前 X 小时""只提醒一次"，则当次只用用户指定的，忽略默认。

### 第 4 步：创建

调用脚本（路径用 `$SKILL_DIR/scripts/`）：

```
# 建 1 个日历事件
$SKILL_DIR/scripts/create_event.sh "<标题>" "<default_calendar>" "<开始ISO>" ["<结束ISO>"] ["<地点>"] ["<备注>"]

# 对每个提前量，建一条提醒
$SKILL_DIR/scripts/create_reminder.sh "<标题>" "<default_reminder_list>" "<提醒绝对ISO>"
```

- 日历事件标题示例：`✈️ MU5137 上海浦东→北京首都`
- **航班/出行录关键字段**：参照 `references/lead-times.md` 的「航班详细字段录入模板」，把 航司/舱位/机型/飞行时长 整理进事件**备注**(create_event.sh 第6参数)，航站楼进**地点**(第5参数)。**不录**乘客/机票号/订单号（没必要、有隐私顾虑）。
- 提醒标题加区分后缀，让用户在清单里一眼看清：`✈️ MU5137 值机打包(前1天)`、`🚄 G1234 该去车站了(前1h)`、`⚖️ 开庭准备(前3h)`。
- 脚本会自动降级：未装 `remindctl` 时用 `osascript`（提醒仍能创建，只是不能查/改/删）。

### 第 5 步：回执

给用户一个简短清单，例如：

```
已为你安排 ✈️ MU5137（2026-07-20 08:30，上海浦东 T2）
📅 日历事件已建 →「个人」日历
⏰ 提醒事项已建 3 条：
   • 07-19 09:00  值机打包(前1天)
   • 07-20 05:30  该去机场了(前3h)
   • 07-20 07:30  开始登机(前1h)
（经 iCloud 同步到你的 iPhone/iPad，稍等片刻可在手机上看到）
```

## 首次使用配置（重要）

1. 若 `config/config.json` 还不存在，从模板复制一份：
   ```
   cp config/config.example.json config/config.json
   ```
2. 跑自检，拿到你机器上真实的日历名和提醒清单名：
   ```
   bash $SKILL_DIR/scripts/setup_check.sh
   ```
3. 把输出里的**日历名**填进 `config.json` 的 `default_calendar`，**清单名**填进 `default_reminder_list`。填错不会报错——脚本会兜底落到第一个日历/默认清单，但名字对才会落到你想要的地方。

> `config.json` 是你的本地配置（被 .gitignore 忽略、不提交）；`config.example.json` 是入库的默认模板。

想调整各类事件的提前量，直接改 `config.json` 的 `lead_times`（格式见 `references/lead-times.md`）。

## 安装更强后端（可选）

提醒事项默认用 `osascript`（只能创建）。装上 `remindctl` 后还能查/改/删：

```
brew install steipete/tap/remindctl
```

装不装不影响创建功能，本 skill 会自动探测。

## 脚本参考

| 脚本 | 作用 |
|---|---|
| `scripts/create_event.sh` | 建日历事件（osascript） |
| `scripts/create_reminder.sh` | 建提醒（remindctl 优先，降级 osascript） |
| `scripts/list_calendars.sh` | 列出所有日历名 |
| `scripts/list_reminder_lists.sh` | 列出所有提醒清单 |
| `scripts/setup_check.sh` | 首次自检：依赖、权限、日历/清单名 |

## 注意

- 这是改用户个人日历/提醒的操作。**创建**是安全的、可逆的（用户可在 App 里删）；但如本 skill 未来扩展删除/批量操作，务必先和用户确认目标。
- 提醒数据是个人隐私，不要把日历/提醒内容发到网络或第三方服务。解析只在本地完成。
- 若用户其实想要的是飞书/钉钉/Outlook 等非苹果日历，本 skill 不适用——那些需要各自的工具。
