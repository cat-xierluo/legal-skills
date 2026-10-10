# 查询操作序列（EMS / 顺丰）

实测与 FachuanHybridSystem 源码对照整理（2026-10-09 全流程实测 EMS；顺丰部分来自法穿源码未实测，首次使用时校正）。

## 0. 登录态与 cookie（2026-10-09 实测结论）

- 专属 Chrome 持久 profile（`~/.cache/express-tracking/chrome-profile`）= 法穿的 `launch_persistent_context(user_data_dir)` 同构：cookie/localStorage/sessionStorage 全落盘，**tab 不需要常开，浏览器重启登录态仍在**。
- EMS cookie 实测：`gehCYwtM3CvqO`（httpOnly 登录身份）**有效期一年**；`gehCYwtM3CvqP`（风控验证标记）**有效期 7 天**——即扫码登录一次管一年，过验证一次管七天。
- **tab 内 UI 显示"登录/注册"不一定是未登录**：登录后旧页面 DOM 不刷新不识别，reload 后即恢复（cookie 生效）。判定以 cookie 为准（`Network.getCookies` 查 `gehCYwtM3CvqO`）。
- 登录动作要发生在查询页 tab（法穿做法：goto 查询页 → 弹扫码 → 原地等）。

## 0.5 反风控铁律：一切输入/点击必须 trusted

**合成事件（`dispatchEvent`/`el.click()`，isTrusted=false）会被 EMS 风控识别 → 每次查询弹图文验证 + 登录 UI 重置。**（2026-10-09 踩坑：同一段查询，合成事件必弹验证，CDP 原生输入不弹。）

- 填文本：`Input.insertText`（浏览器输入管道，isTrusted=true）
- 点击：`Input.dispatchMouseEvent`（mousePressed/Released 带坐标）
- `cdp_ems.js` 已内置 `trustedFill`/`trustedClick`，禁止退回 evaluate 合成事件。

## 1. EMS（11183.com.cn）

### 打开与登录

1. `page.goto("https://www.11183.com.cn/query_express_delivery")`（会被重定向到 `/?to=%2Fquery_express_delivery`，正常）
2. 登录弹窗（el-dialog，含"扫码登录/手机号登录" tab）出现时：
   - 先尝试点弹窗 Close（`dialog "dialog"` 内 button）——**免登录查询有时可行，弹的是图文安全验证**
   - 弹"安全验证"（请依次点击图中文字）或强制登录 → `task.handOff()` 让用户人工完成后恢复
3. 登录成功判定（法穿口径）：弹窗消失 + 停在查询页 + 页面出现"邮件号/物流"字样，或跳 personal_center，或出现"退出/我的EMS/个人中心"

### 查询与展开

1. 查询输入框 `loc=css:input[placeholder="请输入邮件号进行查询"]`，fill 单号（多个用空格分隔，≤20）
   - 注意：fill 后单号变成标签 chip，placeholder 会换成"输入最多20个邮件号(多个请用空格或,隔开)"
2. 点"查询"按钮：`text=查询` 会命中多个元素（导航"运费&时效查询"等）——用 JS 精确点击
   `el.textContent.trim() === '查询'` 且可见的最后一个（实测命中 `SPAN.search-btn`）；或 Enter
3. 结果页点运单号文本/详情按钮打开详情，再点"展开全部轨迹"（5 轮循环兜底）
4. EMS 加载慢：`waitForLoadState("networkidle")` + 额外 2s

## 2. 顺丰（sf-express.com）

法穿流程（sf_query_handler.py，280 行）：

1. `goto https://www.sf-express.com/`（networkidle）→ 消弹窗（10 轮：Escape → close_selectors → overlay 点击 → mask 移除）→ 点"登录" → 等扫码（≤300s，检测 avatar/退出登录出现）
2. `goto https://www.sf-express.com/chn/sc/waybill/list`（networkidle）→ 再消弹窗
3. 填单号 → 搜索/Enter → 点"展开详情"（button/[role=button]/span/text= 多选择器，DOM 搜索兜底）
4. "展开全部轨迹"（展开全部轨迹/展开全部/查看全部/查看更多/展开 多文案尝试）
5. 验证展开成功：页面含"签收时间/签收详情/收方/寄方"

## 3. PDF 导出（ego-browser 经 CDP）

ego-browser Page API 无 pdf()，用 `page.cdp("Page.printToPDF", params)`：

```js
// 1) 注入水印（页眉：时间 + URL）
await page.evaluate(([ts, url]) => {
  const d = document.createElement('div');
  d.id = '__track_wm__';
  d.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:2147483647;' +
    'background:rgba(0,0,0,0.75);color:#fff;padding:6px 16px;font-size:12px;' +
    'display:flex;justify-content:space-between;pointer-events:none;';
  d.innerHTML = `<span>${ts}</span><span style="opacity:.7;max-width:60%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${url}</span>`;
  document.body.appendChild(d);
}, [ts, url]);

// 2) 导出（Node 侧）
const r = await page.cdp("Page.printToPDF", {
  printBackground: true, paperWidth: 8.27, paperHeight: 11.69,  // A4 英寸
  marginTop: 0.5, marginBottom: 0.3, marginLeft: 0.3, marginRight: 0.3,
});
const { writeFileSync } = await import("node:fs");
writeFileSync(pdfPath, Buffer.from(r.data, "base64"));

// 3) 移除水印 DOM
await page.evaluate(() => document.getElementById('__track_wm__')?.remove());
```

CDP 返回 `{data: "<base64 pdf>"}`。若 ego-browser 的 cdp() 包装不透传 base64 大对象，退化方案：`page.screenshot({path})` 存整页 PNG + 在 08 目录留 .md 溯源说明（时间+URL），标注"截图凭证"。

## 4. 常见故障

| 现象 | 处置 |
| --- | --- |
| 免登录查询弹"安全验证"（点文字图） | handOff 人工过；或改走登录会话 |
| 单号 fill 后变 chip、查询按钮点了没反应 | 确认点的是 `text=查询` 精确匹配的按钮（JS 点击），非导航项 |
| "查无结果"但确已交寄 | 当日新交寄 EMS 官网有延迟；隔日再查；核对单号 13 位 |
| 顺丰轨迹不展开 | 法穿的多选择器循环 + DOM 搜索兜底（遍历 body * 找"展开详情"文本可点击父元素） |
| 浏览器被反爬识别（页面行为异常/秒弹验证） | 法穿用 CloakBrowser 反检测启动器（`apps.core.services.browser.create_browser_async`，headless=False）；ego-browser 路线被持续针对时参考其启动参数 |

> 2026-10-09 上游同步核验：FachuanHybridSystem 1b358ae4→6514ee95（46 提交）中 express_query 仅日志降噪、协议勾选 timeout guard 修复与 README 新增，**查询 URL/选择器/流程无变化**。
