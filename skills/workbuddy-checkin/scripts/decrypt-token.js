#!/usr/bin/env node
/**
 * WorkBuddy 每日签到 - 令牌读取脚本（通用版，可分发）
 *
 * 优先读取 WorkBuddy v5.3.8+ 的新版明文登录态；缺失时回退到旧版
 * state.vscdb + Electron safeStorage 解密。最终输出 accessToken。
 *
 * 安全警示（务必阅读）：
 *   - 本脚本输出的 accessToken 等同 WorkBuddy 账号密码，属于高敏感凭据。
 *   - token 仅通过 stdout 的 DECRYPT_RESULT:<token> 单行输出，由调用方经管道立即消费；
 *     切勿 tee/重定向到文件、切勿粘贴分享、切勿提交到任何仓库。
 *   - 日志只记录签到结果（积分/连续天数），绝不记录 token 原文。
 *   - 读取/解密成功时会向 stderr 打印一行安全提示（不进入 stdout，不会污染 token 管道）。
 *
 * 输出：stdout 单行 DECRYPT_RESULT:<accessToken>；失败输出 DECRYPT_RESULT:ERR ...
 *   兼容输出（供 checkin 脚本拼装鉴权头）：
 *     ACCOUNT_UID:<account.uid>
 *     AUTH_DOMAIN:<auth.domain>
 *     ENTERPRISE_ID:<account.enterpriseId>
 */
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");

let app = null;
let safeStorage = null;
try {
  const electron = require("electron");
  app = electron.app || null;
  safeStorage = electron.safeStorage || null;
} catch (e) {
  // 纯 Node 运行（无 Electron）：仅新版明文分支可用，旧版 state.vscdb 分支自动禁用。
}

function emitAndExit(code, line) {
  process.stdout.write(line + "\n");
  const exitFn = app ? () => app.exit(code) : () => process.exit(code);
  setTimeout(exitFn, 200);
}

// 新版明文认证文件候选路径（按平台）
function desktopAuthFileCandidates() {
  const home = os.homedir();
  const ap = process.env.APPDATA || "";
  const xdg = process.env.XDG_CONFIG_HOME || path.join(home, ".config");
  const rel = path.join(
    "CodeBuddyExtension",
    "Data",
    "Public",
    "auth",
    "workbuddy-desktop.info",
  );
  if (process.platform === "darwin") {
    return [path.join(home, "Library", "Application Support", rel)];
  }
  if (process.platform === "win32") {
    const localAp = process.env.LOCALAPPDATA || "";
    // 当前 WorkBuddy 桌面端把明文登录态写在 %LOCALAPPDATA%（非 %APPDATA%），
    // 优先探测 LOCALAPPDATA，缺失时回退 APPDATA，确保 Windows 能读到令牌。
    return [path.join(localAp, rel), path.join(ap, rel)];
  }
  return [path.join(xdg, rel)];
}

// 旧版 state.vscdb 会话库候选路径（按优先级）
function legacyVscdbCandidates() {
  const home = os.homedir();
  const ap = process.env.APPDATA || "";
  const xdg = process.env.XDG_CONFIG_HOME || path.join(home, ".config");
  const apps = ["WorkBuddy", "CodeBuddy"];
  const roots =
    process.platform === "darwin"
      ? apps.map((a) => path.join(home, "Library", "Application Support", a))
      : process.platform === "win32"
        ? apps.map((a) => path.join(ap, a))
        : apps.map((a) => path.join(xdg, a));
  return roots.map((r) => path.join(r, "User", "globalStorage", "state.vscdb"));
}

const SESSION_KEYS = [
  'secret://{"extensionId":"tencent-cloud.coding-copilot","key":"planning-genie.new.accessTokencn"}',
];

function readValue(dbPath, key) {
  try {
    const { DatabaseSync } = require("node:sqlite");
    const db = new DatabaseSync(dbPath, { readOnly: true });
    const row = db.prepare("SELECT value FROM ItemTable WHERE key = ?").get(key);
    db.close();
    return row ? row.value : null;
  } catch (e) {
    if (process.env.WB_CHECKIN_ALLOW_PY_FALLBACK !== "1") {
      throw new Error(
        "无法用 node:sqlite 读取会话数据库，且未开启 python3 回退。" +
        "如需回退请设置 WB_CHECKIN_ALLOW_PY_FALLBACK=1（会调用外部 python3 解释器）"
      );
    }
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

// 主流程：新版明文文件优先，旧版 state.vscdb 回退

for (const f of desktopAuthFileCandidates()) {
  if (!fs.existsSync(f)) continue;
  try {
    const j = JSON.parse(fs.readFileSync(f, "utf8"));
    const token = j && j.auth && j.auth.accessToken;
    if (token && typeof token === "string") {
      const acct = j && j.account;
      const authObj = j && j.auth;
      const uid = acct && acct.uid != null ? String(acct.uid) : "";
      const domain = authObj && authObj.domain != null ? String(authObj.domain) : "";
      const eid = acct && acct.enterpriseId != null ? String(acct.enterpriseId) : "";
      process.stderr.write(
        "[安全提示] 已从本地登录态读取 accessToken（新版明文存储），仅用于 WorkBuddy 官方签到接口；" +
        "请勿将其写入日志、分享或提交。\n"
      );
      // 额外输出 uid/domain/enterpriseId，供 checkin 脚本拼装 X-User-Id 等鉴权头（逆向自客户端 buildHeaders）
      emitAndExit(0, "DECRYPT_RESULT:" + token + "\nACCOUNT_UID:" + uid + "\nAUTH_DOMAIN:" + domain + "\nENTERPRISE_ID:" + eid);
      return;
    }
  } catch (e) {
    // 解析失败（文件损坏 / 写入中）：忽略，落入旧版分支兜底
  }
}

if (!app || !safeStorage) {
  emitAndExit(
    6,
    "DECRYPT_RESULT:ERR 未找到新版明文认证文件，且当前为纯 Node 运行（无 Electron）无法解密旧版 state.vscdb。" +
    "请确认已安装并登录 WorkBuddy 桌面端 v5.3.8+；旧版账户请改用 Electron 运行时执行本脚本。"
  );
  return;
}

const APP_NAME = process.env.WB_CHECKIN_APP_NAME || "WorkBuddy";
app.setName(APP_NAME);

let dbPath = null;
let raw = null;
let legacyReadErr = null;
for (const p of legacyVscdbCandidates()) {
  if (!fs.existsSync(p)) continue;
  for (const k of SESSION_KEYS) {
    try {
      const v = readValue(p, k);
      if (v) { dbPath = p; raw = v; break; }
    } catch (e) {
      legacyReadErr = e;
    }
  }
  if (raw) break;
}
if (!raw) {
  const hint = legacyReadErr ? "（读取旧版 state.vscdb 失败：" + legacyReadErr.message + "）" : "";
  emitAndExit(2, "DECRYPT_RESULT:ERR 未找到 WorkBuddy 本地登录态（新版明文文件与旧版 state.vscdb 均未命中" + hint + "，请先安装并登录 WorkBuddy 桌面端）");
  return;
}

app.whenReady().then(() => {
  if (!safeStorage.isEncryptionAvailable()) {
    emitAndExit(3, "DECRYPT_RESULT:ERR 系统加密不可用");
    return;
  }
  try {
    const buf = toBuffer(JSON.parse(raw));
    if (!buf) throw new Error("未知的存储格式");
    const decrypted = safeStorage.decryptString(buf);
    const session = JSON.parse(decrypted);
    const token = session && session.auth && session.auth.accessToken;
    if (token) {
      const acct = session && session.account;
      const authObj = session && session.auth;
      const uid = acct && acct.uid != null ? String(acct.uid) : "";
      const domain = authObj && authObj.domain != null ? String(authObj.domain) : "";
      const eid = acct && acct.enterpriseId != null ? String(acct.enterpriseId) : "";
      process.stderr.write(
        "[安全提示] 已从本地会话解密 accessToken（旧版 state.vscdb），仅用于 WorkBuddy 官方签到接口；" +
        "请勿将其写入日志、分享或提交。\n"
      );
      emitAndExit(0, "DECRYPT_RESULT:" + token + "\nACCOUNT_UID:" + uid + "\nAUTH_DOMAIN:" + domain + "\nENTERPRISE_ID:" + eid);
      return;
    }
    emitAndExit(4, "DECRYPT_RESULT:ERR 会话中无 accessToken");
  } catch (e) {
    emitAndExit(
      4,
      "DECRYPT_RESULT:ERR 解密失败(" + e.message +
      ")。若为旧版应用（CodeBuddy），请设置环境变量 WB_CHECKIN_APP_NAME=CodeBuddy 后重试；" +
      "或打开 WorkBuddy 桌面端刷新登录态"
    );
  }
});
