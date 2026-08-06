#!/usr/bin/env node
/**
 * WorkBuddy 每日签到 - 令牌读取脚本（通用版，可分发）
 *
 * 优先读取 WorkBuddy v5.3.8+ 的新版明文登录态；缺失时回退到旧版
 * state.vscdb + Electron safeStorage 解密。最终输出 accessToken。
 *
 * ⚠️ 安全警示（务必阅读）：
 *   - 本脚本输出的 accessToken 等同 WorkBuddy 账号密码，属于高敏感凭据。
 *   - token 仅通过 stdout 的 `DECRYPT_RESULT:<token>` 单行输出，由调用方（checkin.sh/ps1）
 *     经管道立即消费；切勿 `tee`/重定向到文件、切勿粘贴分享、切勿提交到任何仓库。
 *   - 日志只记录签到结果（积分/连续天数），绝不记录 token 原文。
 *   - 读取/解密成功时会向 stderr 打印一行安全提示（不进入 stdout，不会污染 token 管道）。
 *
 * 依赖：
 *   - 新版明文分支：仅需 Node.js（无版本特殊要求），纯 Node 读取 JSON。
 *   - 旧版 state.vscdb 分支：需要 Electron 运行时（≥ 30，使用 node:sqlite + safeStorage）。
 *
 * 运行方式（两种都支持，调用方按运行时可用性选择）：
 *   node decrypt-token.js                                          # 新版明文优先，纯 Node 即可
 *   env -u ELECTRON_RUN_AS_NODE <electron二进制> decrypt-token.js  # 旧版回退需要 Electron
 *
 * 输出：stdout 单行 `DECRYPT_RESULT:<accessToken>`；失败输出 DECRYPT_RESULT:ERR ...
 *
 * 跨平台登录态位置：
 *   新版明文（v5.3.8+，主路径）：
 *     - macOS:   ~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info
 *     - Windows: %APPDATA%\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info
 *     - Linux:   ~/.config/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info
 *   旧版 state.vscdb（回退路径，兼容 WorkBuddy / CodeBuddy 早期版本）：
 *     - macOS:   ~/Library/Application Support/{WorkBuddy,CodeBuddy}/User/globalStorage/state.vscdb
 *     - Windows: %APPDATA%\{WorkBuddy,CodeBuddy}\User\globalStorage\state.vscdb
 *     - Linux:   ~/.config/{WorkBuddy,CodeBuddy}/User/globalStorage/state.vscdb
 */
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");

// Electron 仅旧版 state.vscdb 分支需要；try/catch 使脚本可在纯 node 下执行。
// 新版明文分支不依赖 Electron，require 失败时自动跳过旧版分支。
let app = null;
let safeStorage = null;
try {
  const electron = require("electron");
  app = electron.app || null;
  safeStorage = electron.safeStorage || null;
} catch (e) {
  // 纯 Node 运行（无 Electron）：仅新版明文分支可用，旧版 state.vscdb 分支自动禁用。
}

// ---------- 统一输出：先 flush stdout，延迟退出 ----------
// 旧实现 console.log 后立即 app.exit() 在某些环境下会截断未 flush 的 stdout，
// 改为 process.stdout.write 后延迟约 200ms 再退出，确保 token 完整送达调用方管道。
function emitAndExit(code, line) {
  process.stdout.write(line + "\n");
  const exitFn = app ? () => app.exit(code) : () => process.exit(code);
  setTimeout(exitFn, 200);
}

// ---------- 新版明文认证文件候选路径（按平台） ----------
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
    return [path.join(ap, rel)];
  }
  return [path.join(xdg, rel)];
}

// ---------- 旧版 state.vscdb 会话库候选路径（按优先级） ----------
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

// ---------- 旧版会话 key 候选 ----------
const SESSION_KEYS = [
  'secret://{"extensionId":"tencent-cloud.coding-copilot","key":"planning-genie.new.accessTokencn"}',
];

// ---------- 读取 vscdb（node:sqlite 优先，失败回退 python3，需显式开启） ----------
// 安全说明：python3 回退会扩展本地执行信任边界（调用外部解释器读取凭据库）。
// 默认关闭；仅在确需回退时设置 WB_CHECKIN_ALLOW_PY_FALLBACK=1 启用。
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

// ============================================================
// 主流程：新版明文文件优先，旧版 state.vscdb 回退
// ============================================================

// ---------- 1. 新版明文认证文件（WorkBuddy v5.3.8+，纯 Node 读取，优先）----------
// 命中且含 accessToken 即输出；文件缺失 / 无 token / 解析失败均不硬失败，
// 统一落入下方旧版 state.vscdb 分支兜底（覆盖升级中途、文件写入中等场景）。
for (const f of desktopAuthFileCandidates()) {
  if (!fs.existsSync(f)) continue;
  try {
    const j = JSON.parse(fs.readFileSync(f, "utf8"));
    const token = j && j.auth && j.auth.accessToken;
    if (token && typeof token === "string") {
      process.stderr.write(
        "[安全提示] 已从本地登录态读取 accessToken（新版明文存储），仅用于 WorkBuddy 官方签到接口；" +
        "请勿将其写入日志、分享或提交。\n"
      );
      emitAndExit(0, "DECRYPT_RESULT:" + token);
      return;
    }
    // 文件存在但无 accessToken：落入旧版分支兜底
  } catch (e) {
    // 解析失败（文件损坏 / 写入中）：忽略，落入旧版分支兜底
  }
}

// ---------- 2. 回退：旧版 state.vscdb + Electron safeStorage ----------
if (!app || !safeStorage) {
  // 纯 Node 运行且无新版明文文件：无法走 safeStorage 分支，给出明确指引。
  emitAndExit(
    6,
    "DECRYPT_RESULT:ERR 未找到新版明文认证文件，且当前为纯 Node 运行（无 Electron）无法解密旧版 state.vscdb。" +
    "请确认已安装并登录 WorkBuddy 桌面端 v5.3.8+；旧版账户请改用 Electron 运行时执行本脚本。"
  );
  return;
}

// 注意：app.setName 必须在 ready 之前调用，否则 safeStorage 会以默认应用名
// 绑定钥匙串服务，导致解不到 WorkBuddy 的密钥。旧版应用名可通过环境变量覆盖。
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
      legacyReadErr = e; // 记录但不中断，继续尝试其他候选 key/库
    }
  }
  if (raw) break;
}
if (!raw) {
  // 读取旧版库本身报错时附带原因，避免「未知原因」式失败（issue #68 投诉点）
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
      process.stderr.write(
        "[安全提示] 已从本地会话解密 accessToken（旧版 state.vscdb），仅用于 WorkBuddy 官方签到接口；" +
        "请勿将其写入日志、分享或提交。\n"
      );
      emitAndExit(0, "DECRYPT_RESULT:" + token);
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
