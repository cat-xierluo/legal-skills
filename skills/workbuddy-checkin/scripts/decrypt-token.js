#!/usr/bin/env node
/**
 * WorkBuddy 每日签到 - 令牌解密脚本（通用版，可分发）
 *
 * 从 WorkBuddy 桌面端的本地会话数据库（state.vscdb）读取用 Electron safeStorage
 * 加密的 auth session，解密后输出 accessToken，供签到脚本调用后端 API。
 *
 * 依赖：Electron 运行时（版本建议 >= 30，脚本内使用 node:sqlite 读取数据库）。
 * 运行方式：
 *   env -u ELECTRON_RUN_AS_NODE <electron二进制> decrypt-token.js
 *   （WorkBuddy 沙箱环境默认设置 ELECTRON_RUN_AS_NODE=1，会导致 require('electron')
 *     拿不到 safeStorage，因此必须显式取消该环境变量）
 *
 * 输出：stdout 单行 `DECRYPT_RESULT:<accessToken>`；失败输出 DECRYPT_RESULT:ERR ...
 *
 * 跨平台：
 *   - macOS:   ~/Library/Application Support/WorkBuddy/User/globalStorage/state.vscdb
 *   - Windows: %APPDATA%\WorkBuddy\User\globalStorage\state.vscdb
 *   - Linux:   ~/.config/WorkBuddy/User/globalStorage/state.vscdb
 *   - 兼容旧版应用名 CodeBuddy 的路径。
 */
"use strict";

const { app, safeStorage } = require("electron");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");

// ---------- 会话数据库候选路径（按优先级） ----------
function candidatePaths() {
  const home = os.homedir();
  const ap = process.env.APPDATA || "";
  const xdg = process.env.XDG_CONFIG_HOME || path.join(home, ".config");
  const list = [];
  const apps = ["WorkBuddy", "CodeBuddy"];
  const roots =
    process.platform === "darwin"
      ? apps.map((a) => path.join(home, "Library", "Application Support", a))
      : process.platform === "win32"
        ? apps.map((a) => path.join(ap, a))
        : apps.map((a) => path.join(xdg, a));
  for (const r of roots) {
    list.push(path.join(r, "User", "globalStorage", "state.vscdb"));
  }
  return list;
}

// ---------- 会话 key 候选 ----------
const SESSION_KEYS = [
  'secret://{"extensionId":"tencent-cloud.coding-copilot","key":"planning-genie.new.accessTokencn"}',
];

// ---------- 读取 vscdb（node:sqlite 优先，失败回退 python3） ----------
function readValue(dbPath, key) {
  try {
    const { DatabaseSync } = require("node:sqlite");
    const db = new DatabaseSync(dbPath, { readOnly: true });
    const row = db.prepare("SELECT value FROM ItemTable WHERE key = ?").get(key);
    db.close();
    return row ? row.value : null;
  } catch (e) {
    // node:sqlite 不可用时，用 python3 读（macOS/Linux 一般自带）
    try {
      const script =
        "import sqlite3,sys,json;c=sqlite3.connect(sys.argv[1]);r=c.execute('SELECT value FROM ItemTable WHERE key=?',(sys.argv[2],)).fetchone();print(json.dumps(r[0]) if r else '')";
      const out = execFileSync("python3", [ "-c", script, dbPath, key ], {
        encoding: "utf8",
        timeout: 15000,
      }).trim();
      return out ? JSON.parse(out) : null;
    } catch (e2) {
      throw new Error("无法读取会话数据库(需要 node:sqlite 或 python3): " + e2.message);
    }
  }
}

function toBuffer(parsed) {
  if (parsed && parsed.type === "Buffer" && Array.isArray(parsed.data)) return Buffer.from(parsed.data);
  if (typeof parsed === "string") return Buffer.from(parsed, "base64");
  if (Buffer.isBuffer(parsed)) return parsed;
  return null;
}

// ---------- 主流程 ----------
// 注意：app.setName 必须在 ready 之前调用，否则 safeStorage 会以默认应用名
// 绑定钥匙串服务，导致解不到 WorkBuddy 的密钥。旧版应用名可通过环境变量覆盖。
const APP_NAME = process.env.WB_CHECKIN_APP_NAME || "WorkBuddy";
app.setName(APP_NAME);

let dbPath = null;
let raw = null;
for (const p of candidatePaths()) {
  if (!fs.existsSync(p)) continue;
  for (const k of SESSION_KEYS) {
    const v = readValue(p, k);
    if (v) { dbPath = p; raw = v; break; }
  }
  if (raw) break;
}
if (!raw) {
  console.log("DECRYPT_RESULT:ERR 未找到 WorkBuddy 本地会话（请先安装并登录 WorkBuddy 桌面端）");
  app.exit(2);
  return;
}

app.whenReady().then(() => {
  // safeStorage 可用性
  if (!safeStorage.isEncryptionAvailable()) {
    console.log("DECRYPT_RESULT:ERR 系统加密不可用");
    app.exit(3);
    return;
  }
  try {
    const buf = toBuffer(JSON.parse(raw));
    if (!buf) throw new Error("未知的存储格式");
    const decrypted = safeStorage.decryptString(buf);
    const session = JSON.parse(decrypted);
    const token = session && session.auth && session.auth.accessToken;
    if (token) {
      process.stdout.write("DECRYPT_RESULT:" + token + "\n");
      app.exit(0);
      return;
    }
    console.log("DECRYPT_RESULT:ERR 会话中无 accessToken");
    app.exit(4);
  } catch (e) {
    console.log(
      "DECRYPT_RESULT:ERR 解密失败(" + e.message +
      ")。若为旧版应用（CodeBuddy），请设置环境变量 WB_CHECKIN_APP_NAME=CodeBuddy 后重试；" +
      "或打开 WorkBuddy 桌面端刷新登录态"
    );
    app.exit(4);
  }
});
