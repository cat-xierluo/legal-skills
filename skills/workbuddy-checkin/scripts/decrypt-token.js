#!/usr/bin/env node
/**
 * WorkBuddy 每日签到 - 令牌读取脚本（通用版，可分发）
 *
 * 优先读取 WorkBuddy v5.3.8+ 的新版登录态文件：
 *   - v5.3.8 ~ 5.5.x：accessToken 为明文字符串，纯 Node 直接读取；
 *   - v5.6.2+：accessToken 改为 $wbEncrypted 信封对象（AES-256-GCM，AtRestCrypto），
 *     需借助 WorkBuddy 自带的定制 Electron 二进制（ELECTRON_RUN_AS_NODE=1）取
 *     静态对称钥后在本进程解密（issue #191）。
 * 登录态文件缺失时回退到旧版 state.vscdb + Electron safeStorage 解密。
 *
 * 安全警示（务必阅读）：
 *   - 本脚本输出的 accessToken 等同 WorkBuddy 账号密码，属于高敏感凭据。
 *   - token 仅通过 stdout 的 DECRYPT_RESULT:<token> 首行输出，由调用方经管道立即消费；
 *     切勿 tee/重定向到文件、切勿粘贴分享、切勿提交到任何仓库。
 *   - 日志只记录签到结果（积分/连续天数），绝不记录 token 原文。
 *   - 读取/解密成功时会向 stderr 打印一行安全提示（不进入 stdout，不会污染 token 管道）。
 *
 * 依赖：
 *   - 新版明文/信封分支：仅需 Node.js + 本机 WorkBuddy 安装（信封分支会以
 *     ELECTRON_RUN_AS_NODE=1 调用其定制 Electron 取静态钥，不启动 GUI）。
 *   - 旧版 state.vscdb 分支：需要 Electron 运行时（≥ 30，使用 node:sqlite + safeStorage）。
 *
 * 运行方式（两种都支持，调用方按运行时可用性选择）：
 *   node decrypt-token.js                                          # 新版明文优先，纯 Node 即可
 *   env -u ELECTRON_RUN_AS_NODE <electron二进制> decrypt-token.js  # 旧版回退需要 Electron
 *
 * 输出：stdout 首行 DECRYPT_RESULT:<accessToken>；失败输出 DECRYPT_RESULT:ERR ...
 *   随后追加三行账号字段（供 checkin 脚本拼装鉴权头，逆向自客户端 buildHeaders）：
 *     ACCOUNT_UID:<account.uid>
 *     AUTH_DOMAIN:<auth.domain>
 *     ENTERPRISE_ID:<account.enterpriseId>
 *   注意：调用方必须按行前缀过滤（grep '^DECRYPT_RESULT:' / Select-String），
 *   不可整段捕获 stdout，否则账号字段会混入 token。
 *
 * 跨平台登录态位置：
 *   新版明文（v5.3.8+，主路径）：
 *     - macOS:   ~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info
 *     - Windows: %LOCALAPPDATA%\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info
 *                （旧实现只探 %APPDATA%，实测当前桌面端写在 LOCALAPPDATA；APPDATA 保留为回退）
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
const crypto = require("crypto");
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

// 统一输出：先 flush stdout，延迟退出。
// 旧实现 console.log 后立即 app.exit() 在某些环境下会截断未 flush 的 stdout，
// 改为 process.stdout.write 后延迟约 200ms 再退出，确保 token 完整送达调用方管道。
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

// 旧版会话 key 候选
const SESSION_KEYS = [
  'secret://{"extensionId":"tencent-cloud.coding-copilot","key":"planning-genie.new.accessTokencn"}',
];

// 读取 vscdb（node:sqlite 优先，失败回退 python3，需显式开启）
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
    try {
      // node:sqlite 不可用时，用 python3 读（macOS/Linux 一般自带）
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
// v5.6.2+ 信封加密分支（issue #191）
//
// WorkBuddy 5.6.2 起，登录态文件中的 auth.accessToken / refreshToken 从明文字符串
// 改为信封对象：{ $wbEncrypted: 1, envelope: "<base64>" }。envelope 解码后为
// { suite: 1, keyId, nonce, authTag, ciphertext }，加密算法 AES-256-GCM，
// AAD 按 WorkBuddy AtRestCrypto 的 sym-v1 域分离格式构建。
//
// 对称密钥为编译进定制 Electron 的静态钥：loggerGet() 返回
// { version: 1, atRestSecretKey: "<44字符base64>", ... }，
// key = sha256(atRestSecretKey 字符串的 UTF-8 字节)，keyId = sha256(key) 前 16 hex。
// 定制二进制在 ELECTRON_RUN_AS_NODE=1（纯 Node 模式）下仍暴露
// process._linkedBinding("electron_browser_workbuddy_storage")，因此可以不启动
// GUI、不附加调试器地取到静态钥，随后在本进程完成解密。
// ============================================================

// 子进程脚本：从定制 Electron 取静态钥原始字符串（仅经管道返回，不落盘不打印）
const GET_AT_REST_SECRET_SCRIPT =
  'try {' +
  '  var b = process._linkedBinding("electron_browser_workbuddy_storage");' +
  '  var raw = b.loggerGet();' +
  '  var p = JSON.parse(raw);' +
  '  if (!p || typeof p.atRestSecretKey !== "string" || p.atRestSecretKey.length !== 44)' +
  '    throw new Error("payload missing atRestSecretKey");' +
  '  process.stdout.write(p.atRestSecretKey);' +
  '} catch (e) {' +
  '  process.stderr.write("loggerGet failed: " + (e && e.message || e));' +
  '  process.exit(1);' +
  '}';

// WorkBuddy 定制 Electron 二进制候选路径（信封解密需要它的原生绑定取静态钥）
function workbuddyBinaryCandidates() {
  const out = [];
  if (process.env.WB_CHECKIN_WORKBUDDY_BIN) out.push(process.env.WB_CHECKIN_WORKBUDDY_BIN);
  const home = os.homedir();
  if (process.platform === "darwin") {
    // Contents/MacOS 下的主二进制：实测名为 Electron，不同渠道版本可能叫 WorkBuddy，
    // 因此直接枚举目录内可执行文件（目录通常只有一个主二进制）。
    const macDirs = [
      "/Applications/WorkBuddy.app/Contents/MacOS",
      path.join(home, "Applications", "WorkBuddy.app", "Contents", "MacOS"),
    ];
    for (const dir of macDirs) {
      try {
        for (const name of fs.readdirSync(dir).sort()) {
          const p = path.join(dir, name);
          try {
            const st = fs.statSync(p);
            if (st.isFile() && st.mode & 0o111) out.push(p);
          } catch (e) { /* 跳过不可 stat 的条目 */ }
        }
      } catch (e) { /* 目录不存在：跳过 */ }
    }
  } else if (process.platform === "win32") {
    const la = process.env.LOCALAPPDATA || "";
    const pf = process.env.ProgramFiles || "C:\\Program Files";
    const pf86 = process.env["ProgramFiles(x86)"] || "C:\\Program Files (x86)";
    if (la) out.push(path.join(la, "Programs", "WorkBuddy", "WorkBuddy.exe"));
    out.push(path.join(pf, "WorkBuddy", "WorkBuddy.exe"));
    out.push(path.join(pf86, "WorkBuddy", "WorkBuddy.exe"));
    if (la) out.push(path.join(la, "WorkBuddy", "WorkBuddy.exe"));
  } else {
    // Linux：桌面端主二进制的常见安装位置（未尽列举，可用环境变量指定）
    out.push("/usr/share/workbuddy/workbuddy", "/opt/WorkBuddy/workbuddy", "/usr/bin/workbuddy");
  }
  return out.filter(Boolean);
}

// 取静态钥原始字符串（44 字符 base64）。逐个候选尝试，全部失败时抛出可操作的错误。
function getAtRestSecretKey() {
  const errs = [];
  for (const bin of workbuddyBinaryCandidates()) {
    if (!fs.existsSync(bin)) continue;
    try {
      const secret = execFileSync(bin, ["-e", GET_AT_REST_SECRET_SCRIPT], {
        env: Object.assign({}, process.env, { ELECTRON_RUN_AS_NODE: "1" }),
        encoding: "utf8",
        timeout: 30000,
        stdio: ["ignore", "pipe", "pipe"],
      }).trim();
      if (/^[A-Za-z0-9+/]{43}=$/.test(secret)) return secret;
      errs.push(bin + ": 非预期的静态钥格式");
    } catch (e) {
      errs.push(bin + ": " + (e.stderr ? String(e.stderr).trim() : e.message));
    }
  }
  throw new Error(
    "无法从 WorkBuddy 定制 Electron 获取静态钥（" +
    (errs.length ? errs.join("; ") : "未找到已安装的 WorkBuddy 桌面端二进制") +
    "）。请确认 WorkBuddy 桌面端已安装，或用环境变量 WB_CHECKIN_WORKBUDDY_BIN 指定其主程序路径"
  );
}

// 按 AtRestCrypto sym-v1 格式构建 AES-GCM 的 AAD（framing=field）
function buildFieldAad(keyId, suite) {
  function u32(v) {
    const b = Buffer.alloc(4);
    b.writeUInt32BE(v);
    return b;
  }
  function lp(s) {
    const b = Buffer.from(s, "utf8");
    return Buffer.concat([u32(b.length), b]);
  }
  return Buffer.concat([
    Buffer.from("WB-AAD\0", "ascii"), // 域分离前缀
    Buffer.from([1]), // 域版本
    lp("WBEV1"), // field framing 的格式标识
    lp("sym-v1"), // 方案标识
    u32(suite),
    lp(keyId),
    Buffer.from([2]), // FRAMING_CODE["field"]
    Buffer.from([0]), // encodeOptionalUint64(undefined)：无 sequence
    Buffer.from([0]), // final === undefined
  ]);
}

// 解密 $wbEncrypted 信封字段，返回明文字符串；失败抛错（含原因）
function openEncryptedField(envelopeB64) {
  let env;
  try {
    env = JSON.parse(Buffer.from(envelopeB64, "base64").toString("utf8"));
  } catch (e) {
    throw new Error("信封 envelope 不是有效 JSON");
  }
  if (env.suite !== 1) throw new Error("不支持的加密 suite: " + env.suite);
  if (typeof env.keyId !== "string" || !/^[0-9a-f]{16}$/.test(env.keyId)) {
    throw new Error("信封 keyId 格式异常");
  }
  const secret = getAtRestSecretKey();
  const key = crypto.createHash("sha256").update(secret, "utf8").digest();
  const derivedKeyId = crypto.createHash("sha256").update(key).digest("hex").slice(0, 16);
  if (derivedKeyId !== env.keyId) {
    throw new Error(
      "静态钥与信封 keyId 不匹配（派生 " + derivedKeyId + " ≠ 信封 " + env.keyId +
      "），WorkBuddy 可能已更换加密方案，请上报 issue 适配"
    );
  }
  const decipher = crypto.createDecipheriv(
    "aes-256-gcm", key, Buffer.from(env.nonce, "base64"), { authTagLength: 16 }
  );
  decipher.setAAD(buildFieldAad(env.keyId, env.suite));
  decipher.setAuthTag(Buffer.from(env.authTag, "base64"));
  try {
    const plaintext = Buffer.concat([
      decipher.update(Buffer.from(env.ciphertext, "base64")),
      decipher.final(),
    ]);
    return plaintext.toString("utf8");
  } catch (e) {
    throw new Error("AES-GCM 解密失败（" + e.message + "），信封可能已损坏");
  }
}

// ============================================================
// 主流程：新版登录态文件优先（明文 → 信封），旧版 state.vscdb 回退
// ============================================================

// 1. 新版认证文件（WorkBuddy v5.3.8+，优先）
// 命中即输出；文件缺失 / 解析失败不硬失败，统一落入下方旧版 state.vscdb 分支兜底。
// accessToken 形态三分支：
//   a) 字符串（v5.3.8 ~ 5.5.x 明文）→ 直接使用；
//   b) $wbEncrypted 信封对象（v5.6.2+）→ 解密后使用；
//   c) 其它/解密失败 → 报错并说明原因（不再静默落入误导性的旧版分支）。
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
    if (token && typeof token === "object" && !Array.isArray(token) &&
        token.$wbEncrypted === 1 && typeof token.envelope === "string") {
      // v5.6.2+ 信封加密（issue #191）：解密失败时给出确切原因后退出，
      // 不再落入旧版分支——那会报「未找到明文认证文件」，对用户是误导。
      let plaintext;
      try {
        plaintext = openEncryptedField(token.envelope);
      } catch (e) {
        emitAndExit(7, "DECRYPT_RESULT:ERR 登录态为 v5.6.2+ 信封加密，但解密失败：" + e.message);
        return;
      }
      const acct = j && j.account;
      const authObj = j && j.auth;
      const uid = acct && acct.uid != null ? String(acct.uid) : "";
      const domain = authObj && authObj.domain != null ? String(authObj.domain) : "";
      const eid = acct && acct.enterpriseId != null ? String(acct.enterpriseId) : "";
      process.stderr.write(
        "[安全提示] 已解密 v5.6.2+ 信封登录态取得 accessToken（AES-256-GCM，静态钥取自 WorkBuddy 定制 Electron），" +
        "仅用于 WorkBuddy 官方签到接口；请勿将其写入日志、分享或提交。\n"
      );
      emitAndExit(0, "DECRYPT_RESULT:" + plaintext + "\nACCOUNT_UID:" + uid + "\nAUTH_DOMAIN:" + domain + "\nENTERPRISE_ID:" + eid);
      return;
    }
    // 文件存在但无 accessToken：落入旧版分支兜底
  } catch (e) {
    // 解析失败（文件损坏 / 写入中）：忽略，落入旧版分支兜底
  }
}

// 2. 回退：旧版 state.vscdb + Electron safeStorage
if (!app || !safeStorage) {
  // 纯 Node 运行且无新版明文文件：无法走 safeStorage 分支，给出明确指引。
  emitAndExit(
    6,
    "DECRYPT_RESULT:ERR 未找到新版认证文件，且当前为纯 Node 运行（无 Electron）无法解密旧版 state.vscdb。" +
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
