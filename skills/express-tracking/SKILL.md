---
name: express-tracking
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "0.1.0"
license: CC-BY-NC
description: |
  快递邮寄跟踪与证据留痕。当用户说"查快递""查物流""EMS 到哪了""顺丰单号""邮寄凭证"
  "把运单截图录进去""批量刷新在途快递"时使用。登记寄件（add-mailing）、浏览器自动化
  查 EMS/顺丰官网轨迹、生成带时间戳+URL 水印的 PDF 凭证归档 08 目录、回写签收状态。
  不走第三方聚合 API（证据效力与费用考虑），不自动扫码登录（风控风险，弹码人工扫）。
---

# express-tracking - 快递邮寄跟踪与留痕

## 定位

寄件交割的证据链工具：**登记 → 查询 → 留痕 → 回写**。数据真值在 case.yaml `邮寄跟踪` 节
（case-progress skill 的 add-mailing / set-mailing 维护，schema 见其 references/schema.md §2.17），
轨迹 PDF 凭证落案件 `08 - 🏛️ 法院送达/` 目录。

设计参考 FachuanHybridSystem express_query 模块（浏览器自动化官网查询 + 水印 PDF），本 skill 是其在 ZCode + ego-browser 环境的轻量复刻。

## 浏览器会话与登录态管理（免反复登录——核心设计）

**目标：扫码登录一次管一年、过验证一次管七天，Chrome 关掉重启都不丢。**

| 机制 | 说明 |
| --- | --- |
| 持久 profile | `~/.cache/express-tracking/chrome-profile`（法穿 `launch_persistent_context(user_data_dir)` 同构）——cookies/localStorage/sessionStorage 全落盘，**tab 不需常开** |
| 登录 cookie | `gehCYwtM3CvqO`（httpOnly）实测有效期**一年**；风控验证标记 `gehCYwtM3CvqP` 有效期**七天** |
| 登录态判定 | **以 cookie 为准**（`Network.getCookies` 有无 `gehCYwtM3CvqO`），页面右上角显示"登录/注册"可能只是旧 DOM 未刷新——reload 即恢复 |
| 幂等启动 | 一律先跑 `scripts/ensure_chrome.sh`：CDP 9222 活着就复用（**绝不重启已跑实例**，登录态在内存+磁盘），没跑才启动 |
| trusted 输入 | 填单/点击必须走 `Input.insertText`/`Input.dispatchMouseEvent`（isTrusted=true）；合成事件会被风控识别 → 弹验证+重置登录 UI（见 references §0.5） |

会话过期特征：查询页弹出扫码登录窗（而非安全验证）→ 让用户在**查询页 tab** 原地扫码（法穿做法），约一年一次。

## 触发场景

- 寄件后：用户给出下单截图/短信截图/运单照片 → 登记邮寄
- 在途中：用户说"查一下快递" → 查询轨迹出凭证
- 签收后：轨迹显示签收 → 回写状态 + 签收日期
- 批量：用户说"刷新所有在途快递" → 跨案件枚举在途单号批量查

## 工作流

### 1. 登记（寄件时）

单号来源（按优先级）：截图/短信里的单号（模型直接看图提取）> 用户口述 > 运单条码照片
（iPhone 拍照经 iCloud 进照片库，Vision 可识别 Code128 条码）。

```bash
/usr/bin/python3 .claude/skills/case-progress/scripts/case_store.py add-mailing <短码> <单号> \
  --carrier ems|sf|other --content "内装材料" --sent YYYY-MM-DD \
  --sender 寄件人 --to 收件方 --file "08 - 🏛️ 法院送达/YYMMDD 邮寄凭证 <单号>.jpg"
```

注意：`/usr/bin/python3`（默认 brew python3 + 旧 pyyaml 必崩，见环境备注）。凭证图片先复制入 08 目录再登记相对路径。

### 2. 轨迹查询（CDP 直连 Chrome——主路线）

**不要用 ego-lite 内嵌浏览器**：其窗口 handOff 后会隐藏、不可见不可控（2026-10-09 实测踩坑）。主路线与法穿同构：CDP 直连真实 Chrome 窗口（9222 + 持久 profile），窗口永远可见，登录/验证态可累积。

```bash
# 0. 幂等确保工位（已跑则复用会话，不重启）
scripts/ensure_chrome.sh

# 1. 脚本化操作（scripts/cdp_ems.js，node≥22 免依赖，内置 trusted 输入）
node scripts/cdp_ems.js status                      # 探测页面状态（验证码/登录/输入框）
node scripts/cdp_ems.js query 1234567890123         # 填单查询（自动消登录弹窗、trusted 输入；示例单号，虚构）
node scripts/cdp_ems.js text                        # dump 页面文本（轨迹解析）
node scripts/cdp_ems.js pdf 1234567890123 <路径.pdf> # 水印注入 + printToPDF
```

要点：
- EMS 未登录可查但**只显示最近 2 条轨迹**；登录 cookie 在则完整（"请登录后查看完整物流信息"= 页面 UI 误报可能，先查 cookie）
- 安全验证/扫码登录出现时：Chrome 窗口可见，让用户人工处理；可挂后台轮询（每 5s status，验证消失即自动 pdf）

要点：
- EMS 未登录可查但**只显示最近 2 条轨迹**且弹图文安全验证；登录后完整轨迹（"请登录后查看完整物流信息"）
- 安全验证/扫码登录出现时：Chrome 窗口可见，让用户人工处理；可挂后台轮询（每 5s status，验证消失即自动 pdf）
- 顺丰流程参考 [references/query-flows.md](references/query-flows.md) §2（法穿移植，未实测）

### 3. PDF 留痕（水印 + printToPDF）

轨迹页完全加载后，`page.evaluate` 注入页眉水印（fixed 顶栏）：
左=当前时间 `YYYY-MM-DD HH:MM:SS`，右=页面 URL；再经 `page.cdp("Page.printToPDF", …)`
导出 A4 PDF（关键参数见 references/query-flows.md §3）。

命名：`YYMMDD <承运商>轨迹 <单号>.pdf`，落 08 目录。

### 4. 状态回写

```bash
/usr/bin/python3 .claude/skills/case-progress/scripts/case_store.py set-mailing <短码> <单号> \
  --status in_transit|signed|abnormal --latest "最近一条轨迹摘要" \
  [--signed YYYY-MM-DD] --file "08 - 🏛️ 法院送达/YYMMDD EMS轨迹 <单号>.pdf"
```

签收时同时补一条时间线事件（事件类型=举证，状态 done）。收尾 `log-work auto --type 整理`。

## 批量刷新流程

1. `list` 遍历案件 → 各 `show` 取 `邮寄跟踪` 中 `状态 ∈ {pending, in_transit}` 的单号
2. 按承运商分组；EMS 每批 ≤20 单粘入查询框，顺丰逐单（官网单号查询）
3. 逐单回写（签收/在途/异常 + 最新轨迹）；出问题的单列出待人工复核

## 边界

- 仅 ems / sf / other（other 只登记不查询）
- **不自动扫码、不自动过验证码**：模拟微信客户端有账号风控风险，一律 handOff 人工处理
- 不做后台定时监控：手动触发（"查快递"/"刷新在途"），需要自动推送再评估快递100 订阅（付费）
- PDF 凭证是查询时点快照，不替代公证件；重要证据固定需另行公证

## 环境备注

- case_store CLI 一律 `/usr/bin/python3`（brew python3.14 + pyyaml4.2 会 `collections.Hashable` 崩溃）
- `scripts/cdp_ems.js` 需 node ≥22（原生 WebSocket，零依赖）；Chrome CDP 的 `/json/list` 在 Chrome 155 返回空属正常，脚本已走 `/json/new` 兜底
- `scripts/ensure_chrome.sh` 幂等管理专属 Chrome 工位（CDP 9222 + 持久 profile `~/.cache/express-tracking/chrome-profile`）
- 2026-10-09 实测闭环：单号 13 位 EMS 查询 → trusted 输入免验证弹窗 → 水印 PDF（364KB）→ set-mailing 回写；cookie 机制确认（登录一年/验证七天）
