#!/usr/bin/env node
// express-tracking · EMS 官网轨迹 CDP 客户端（法穿 express_query 模式的独立复刻）
// 依赖：Chrome 以 --remote-debugging-port=9222 --user-data-dir=<持久profile> 启动（见 SKILL.md）
// 用法：
//   node cdp_ems.js status              # 报页面状态（验证码/登录/轨迹/输入框）
//   node cdp_ems.js query <单号>         # 填单号并点查询，报结果状态
//   node cdp_ems.js pdf <单号> <输出路径> # 注入水印并导出 A4 PDF
//   node cdp_ems.js text                 # dump 页面可见文本（轨迹解析用）
const CDP_HTTP = "http://127.0.0.1:9222";

async function findPageTarget() {
  // 双源取 target（Chrome 155 的 /json 偶发返回空，/json/list 兜底）
  let targets = [];
  for (const ep of ["/json", "/json/list"]) {
    try {
      const r = await fetch(`${CDP_HTTP}${ep}`);
      const t = await r.json();
      if (Array.isArray(t) && t.length) { targets = t; break; }
    } catch { /* next */ }
  }
  const ems = targets.find(t => t.type === "page" && /11183\.com\.cn/.test(t.url));
  if (ems) return ems;
  // 无现成 EMS 页 → 新开 tab（PUT /json/new；url 参数在新版 Chrome 会被忽略，随后显式导航）
  const r = await fetch(`${CDP_HTTP}/json/new`, { method: "PUT" });
  const t = await r.json();
  t.__need_navigate = true;
  return t;
}

function connect(wsUrl) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl);
    let id = 0;
    const pending = new Map();
    ws.onopen = () => resolve({
      send: (method, params = {}) => new Promise((res, rej) => {
        const mid = ++id;
        pending.set(mid, { res, rej });
        ws.send(JSON.stringify({ id: mid, method, params }));
      }),
      close: () => ws.close(),
    });
    ws.onerror = reject;
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.id && pending.has(m.id)) {
        const { res, rej } = pending.get(m.id);
        pending.delete(m.id);
        m.error ? rej(new Error(`${m.error.message}`)) : res(m.result);
      }
    };
  });
}

async function evalJS(cdp, expr) {
  const r = await cdp.send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.text || "eval failed");
  return r.result.value;
}

// trusted 输入（合成事件 isTrusted=false 会被 EMS 风控识别弹验证，法穿同理由 Playwright 原生输入）
async function trustedFill(cdp, selectorExpr, text) {
  const box = await evalJS(cdp, `(() => {
    const inp = ${selectorExpr};
    if (!inp) return null;
    inp.focus();
    const r = inp.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width, h: r.height };
  })()`);
  if (!box) return "NO_INPUT";
  await cdp.send("Input.insertText", { text });
  return "FILLED";
}

async function trustedClick(cdp, selectorExpr) {
  const pos = await evalJS(cdp, `(() => {
    const el = ${selectorExpr};
    if (!el) return null;
    el.scrollIntoView({ block: "center" });
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
  })()`);
  if (!pos) return "NO_EL";
  for (const type of ["mousePressed", "mouseReleased"]) {
    await cdp.send("Input.dispatchMouseEvent", {
      type, x: pos.x, y: pos.y, button: "left", clickCount: 1,
    });
  }
  return "CLICKED";
}

const STATE_PROBE = `(() => {
  const t = document.body.innerText || '';
  return {
    url: location.href,
    title: document.title,
    hasSafeVerify: t.includes('安全验证'),
    hasLoginDialog: t.includes('扫码登录') && t.includes('请使用微信'),
    hasTrackDetail: /轨迹|已收件|已签收|离开|到达|投递/.test(t),
    hasQueryInput: !!document.querySelector('input[placeholder*="邮件号"]'),
    snippet: t.replace(/\\s+/g, ' ').slice(0, 300),
  };
})()`;

const [,, cmd, ...rest] = process.argv;
const target = await findPageTarget();
if (!target) { console.error("未找到可用页面 target（Chrome 是否已启动并打开 EMS 页？）"); process.exit(1); }
const cdp = await connect(target.webSocketDebuggerUrl);
await cdp.send("Runtime.enable");
await cdp.send("Page.enable");
if (target.__need_navigate) {
  await cdp.send("Page.navigate", { url: "https://www.11183.com.cn/query_express_delivery" });
  await new Promise(r => setTimeout(r, 5000));
}

if (cmd === "status") {
  console.log(JSON.stringify(await evalJS(cdp, STATE_PROBE), null, 2));
} else if (cmd === "text") {
  console.log(await evalJS(cdp, `document.body.innerText`));
} else if (cmd === "query") {
  const num = rest[0];
  if (!num) { console.error("用法: query <单号>"); process.exit(1); }
  // 当前不在查询页则导航过去（登录态 cookie/sessionStorage 同 tab 保留）
  // 注意首页 URL /?to=%2Fquery_express_delivery 也含该串，必须看路径而非全 URL
  const curUrl = await evalJS(cdp, "location.pathname + '|' + location.href");
  const [path, full] = curUrl.split("|");
  const onQueryPage = path.startsWith("/query_express_delivery") || path === "/" && /to=%2Fquery/.test(full);
  if (!onQueryPage) {
    await cdp.send("Page.navigate", { url: "https://www.11183.com.cn/query_express_delivery" });
    await new Promise(r => setTimeout(r, 5000));
  }
  // 先消登录弹窗（法穿顺序：弹窗关闭 → 填单 → 查询）
  const dismissed = await evalJS(cdp, `(() => {
    const dlg = document.querySelector('.el-dialog');
    if (!dlg) return 'NO_DIALOG';
    const t = (dlg.innerText || '');
    if (!t.includes('扫码登录')) return 'NOT_LOGIN_DIALOG';
    const btn = dlg.querySelector('.el-dialog__headerbtn, button[class*=close], .close');
    if (btn) { btn.click(); return 'CLOSED'; }
    dlg.remove();
    document.querySelectorAll('.el-overlay, .v-modal, [class*=mask]').forEach(e => e.remove());
    return 'REMOVED';
  })()`);
  await new Promise(r => setTimeout(r, 800));
  const filled = await trustedFill(cdp, `document.querySelector('input[placeholder*="邮件号"]')`, num);
  await new Promise(r => setTimeout(r, 600));
  // 点查询按钮：text=查询 精确匹配的最后一个可见元素（trusted 鼠标点击）
  const clicked = await trustedClick(cdp, `(() => {
    const els = [...document.querySelectorAll('button, a, div, span')].filter(el => {
      const t = (el.textContent || '').trim();
      if (t !== '查询') return false;
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    });
    return els.length ? els[els.length - 1] : null;
  })()`);
  await new Promise(r => setTimeout(r, 4000));
  console.log(JSON.stringify({ filled, clicked, state: await evalJS(cdp, STATE_PROBE) }, null, 2));
  if (clicked !== "CLICKED") {
    // 查询按钮未命中：再试输入框右侧的放大镜/搜索按钮（trusted 点击）
    const alt = await trustedClick(cdp, `(() => {
      const inp = document.querySelector('input[placeholder*="邮件号"]');
      if (!inp) return null;
      const box = inp.closest('div[class*=search], div[class*=query]') || inp.parentElement;
      const btns = [...box.querySelectorAll('span, button, i, div')].filter(e => {
        const r = e.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && e !== inp;
      });
      return btns.length ? btns[btns.length - 1] : null;
    })()`);
    await new Promise(r => setTimeout(r, 4000));
    console.log(JSON.stringify({ alt, state: await evalJS(cdp, STATE_PROBE) }, null, 2));
  }
} else if (cmd === "pdf") {
  const [num, outPath] = rest;
  if (!num || !outPath) { console.error("用法: pdf <单号> <输出路径>"); process.exit(1); }
  const ts = new Date().toLocaleString("sv-SE").replace("T", " ");
  const url = await evalJS(cdp, "location.href");
  await evalJS(cdp, `(() => {
    const d = document.createElement('div');
    d.id = '__track_wm__';
    d.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:2147483647;' +
      'background:rgba(0,0,0,0.78);color:#fff;padding:6px 16px;font-size:12px;' +
      'display:flex;justify-content:space-between;pointer-events:none;';
    d.innerHTML = '<span>查询时间 ${ts}｜邮件号 ${num}</span>' +
      '<span style="opacity:.7;max-width:55%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${url}</span>';
    document.body.appendChild(d);
  })()`);
  await new Promise(r => setTimeout(r, 400));
  const pdf = await cdp.send("Page.printToPDF", {
    printBackground: true, paperWidth: 8.27, paperHeight: 11.69,
    marginTop: 0.5, marginBottom: 0.3, marginLeft: 0.3, marginRight: 0.3,
  });
  const { writeFileSync } = await import("node:fs");
  writeFileSync(outPath, Buffer.from(pdf.data, "base64"));
  await evalJS(cdp, `document.getElementById('__track_wm__')?.remove()`);
  console.log(`PDF_WRITTEN ${outPath} (${Math.round(pdf.data.length * 3/4 / 1024)} KB)`);
} else {
  console.error("用法: cdp_ems.js status|query|pdf|text");
  process.exit(1);
}
cdp.close();
