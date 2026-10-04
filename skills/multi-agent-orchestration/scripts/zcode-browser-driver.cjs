#!/usr/bin/env node
/**
 * zcode-browser-driver.cjs — ZCode localhost GUI 浏览器驱动 MVP（Node CJS，输出 JSON）。
 *
 * 合同来源：multi-agent-orchestration references/34、35（2026-10-02 runtime 3.14.3 页面映射）。
 * 所有任务输入仅经 GUI DOM（文本框键入 + 发送按钮点击），不调用隐藏 RPC、不直接 CLI 模型调用。
 *
 * 命令：
 *   inspect    --url URL [--workspace ABS] [--headed]
 *   submit     --url URL --workspace ABS --task-id ID --prompt-file PATH --state PATH
 *              [--timeout-ms N] [--ready-timeout-ms N] [--headed]
 *   （R3：发送前有界等待具体模型/模式就绪；空值或「管理模型」占位 → CONFIG_NOT_READY 拒绝，不盲发）
 *   observe | collect --state PATH
 *   follow-up  --state PATH --prompt-file PATH --input-id ID [--timeout-ms N] [--headed]
 *
 * 输出：stdout 单个 JSON。ok:true 为可判定结果；ok:false 为错误（error.code/message/hint）。
 * 退出码：0 成功/已对账；1 错误（fail-closed）；2 状态保留 unknown（未确认，绝不自动重发）；
 *         3 明确 UNSUPPORTED（能力未证明，不伪造支持）。
 *
 * 状态文件（--state）的去重合同：点击发送前先原子写入 intent；同一 state 的重复调用只对账，
 * 不再点击发送（本驱动不承诺跨进程 exactly-once——DOM 点击本身无法绝对保证，配套排他锁与
 * DB 对账把重复发送窗口压到最小）。旧 state 的 url/workspace/task-id/prompt 指纹任一不同 → 拒绝。
 * state 排他锁：<state>.lock 目录 + nonce 属主；锁已存在一律拒绝（含 owner 缺失/损坏/陈旧），
 * 释放时核 nonce 只删自身；残留锁由 PM 人工核实后清理。
 *
 * 本脚本不修改全局配置、不停止共享 Web 服务、只在 finally 关闭自己启动的浏览器。
 */
'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const crypto = require('crypto');

const DRIVER_VERSION = '0.2.0';
const STATE_SCHEMA = 1;
const DEFAULT_TIMEOUT_MS = 120000;
const POLL_INTERVAL_MS = 1500;

// ---------------------------------------------------------------------------
// 错误与输出
// ---------------------------------------------------------------------------

class DriverError extends Error {
  constructor(code, message, hint) {
    super(message);
    this.code = code;
    this.hint = hint;
  }
}

let emitSink = null; // 测试注入，避免截获 test runner 的 stdout
function __setEmitSink(fn) { emitSink = fn; }

function emit(obj, exitCode) {
  const line = JSON.stringify(obj, null, 2) + '\n';
  if (emitSink) { emitSink(JSON.parse(JSON.stringify(obj)), exitCode); return; }
  process.stdout.write(line);
  process.exitCode = exitCode;
}

function okResult(command, extra) {
  emit(Object.assign({ ok: true, command, driverVersion: DRIVER_VERSION }, extra), 0);
}

function unknownResult(command, extra) {
  emit(Object.assign({ ok: true, command, status: 'unknown', driverVersion: DRIVER_VERSION }, extra), 2);
}

function unsupportedResult(command, extra) {
  emit(Object.assign({ ok: true, command, status: 'unsupported', driverVersion: DRIVER_VERSION }, extra), 3);
}

function fail(command, err) {
  const code = err instanceof DriverError ? err.code : 'INTERNAL_ERROR';
  emit({
    ok: false,
    command,
    error: { code, message: err.message, hint: err.hint || undefined },
  }, 1);
}

// ---------------------------------------------------------------------------
// 参数
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  const args = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) {
      const key = a.slice(2);
      const next = argv[i + 1];
      if (next === undefined || next.startsWith('--')) args[key] = true;
      else { args[key] = next; i++; }
    } else args._.push(a);
  }
  return args;
}

function requireString(args, name) {
  const v = args[name];
  if (typeof v !== 'string' || !v.trim()) throw new DriverError('ARG_MISSING', `缺少必填参数 --${name}`);
  return v;
}

function assertLoopbackUrl(raw) {
  let u;
  try { u = new URL(raw); } catch { throw new DriverError('URL_INVALID', `URL 无法解析: ${raw}`); }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') {
    throw new DriverError('URL_NOT_LOOPBACK', `仅接受 http(s) loopback URL，收到 ${u.protocol}`);
  }
  // R2：拒绝 userinfo/query/hash，避免凭证或可变参数进入 state 落盘或请求。
  if (u.username || u.password) {
    throw new DriverError('URL_NOT_LOOPBACK', 'URL 含 userinfo（user:pass@），拒绝');
  }
  if (u.search) throw new DriverError('URL_NOT_LOOPBACK', `URL 含 query（${u.search}），拒绝`);
  if (u.hash) throw new DriverError('URL_NOT_LOOPBACK', `URL 含 hash（${u.hash}），拒绝`);
  const h = u.hostname.replace(/^\[|\]$/g, ''); // IPv6 字面量去括号
  if (!['127.0.0.1', 'localhost', '::1'].includes(h)) {
    throw new DriverError('URL_NOT_LOOPBACK', `仅接受 loopback 主机（127.0.0.1/localhost/::1），收到 ${u.hostname}`);
  }
  return u;
}

function assertAbsPath(p, name) {
  if (!path.isAbsolute(p)) throw new DriverError('ARG_INVALID', `--${name} 必须是绝对路径: ${p}`);
  return p;
}

// ---------------------------------------------------------------------------
// Playwright 加载（缺失时清晰报错，不自动安装）
// ---------------------------------------------------------------------------

let playwrightMod = null;
function loadPlaywright() {
  if (playwrightMod) return playwrightMod;
  const candidates = ['playwright', path.join(os.homedir(), 'node_modules', 'playwright')];
  for (const c of candidates) {
    try { playwrightMod = require(c); return playwrightMod; } catch { /* next */ }
  }
  throw new DriverError(
    'PLAYWRIGHT_MISSING',
    '未找到 playwright 依赖（尝试 require("playwright") 与 ~/node_modules/playwright）',
    '本机约定：仓库 cwd 可解析 pnpm 提升的 playwright 1.61.1；或在含 playwright 的目录运行。按环境管理规则安装，本脚本不自动安装。'
  );
}

// 依赖注入点：测试用 fakeDeps.openPage / .fetchServerInfo 替换浏览器与网络。
function defaultDeps(headless) {
  return {
    async openPage(url) {
      const { chromium } = loadPlaywright();
      const browser = await chromium.launch({ headless });
      let context;
      try {
        context = await browser.newContext();
        const page = await context.newPage();
        return {
          page,
          async close() {
            try { await context.close(); } catch { /* ignore */ }
            try { await browser.close(); } catch { /* ignore */ }
          },
        };
      } catch (e) {
        // R2：context/page 创建失败也必须关闭已启动的浏览器进程。
        try { await browser.close(); } catch { /* ignore */ }
        throw e;
      }
    },
    async fetchServerInfo(url) {
      const res = await fetch(url, { signal: AbortSignal.timeout(8000) });
      if (!res.ok) throw new DriverError('SERVICE_UNREACHABLE', `server-info HTTP ${res.status}`);
      return res.json();
    },
  };
}

// ---------------------------------------------------------------------------
// 只读 SQLite（node:sqlite 优先，回退 sqlite3 CLI；一律只读打开）
// ---------------------------------------------------------------------------

function openDbReadOnly(dbPath, label) {
  if (!fs.existsSync(dbPath)) {
    throw new DriverError('DB_UNAVAILABLE', `${label} 不存在: ${dbPath}`);
  }
  try {
    const { DatabaseSync } = require('node:sqlite');
    return { mode: 'node:sqlite', db: new DatabaseSync(dbPath, { readOnly: true }) };
  } catch (e) {
    // 回退 sqlite3 CLI（mode=ro URI，逐条查询 JSON 输出）
    const { execFileSync } = require('child_process');
    return {
      mode: 'sqlite3-cli',
      all(sql, params) {
        const stmt = sql.replace(/\?/g, () => {
          const p = params.shift();
          return typeof p === 'number' ? String(p) : `'${String(p).replace(/'/g, "''")}'`;
        });
        let out;
        try {
          out = execFileSync('sqlite3', ['-json', `file:${dbPath}?mode=ro`, stmt], { encoding: 'utf8' });
        } catch (e2) {
          throw new DriverError('DB_QUERY_FAILED', `${label} 查询失败: ${e2.message.split('\n')[0]}`);
        }
        return out.trim() ? JSON.parse(out) : [];
      },
    };
  }
}

function dbAll(handle, sql, params) {
  if (handle.mode === 'node:sqlite') {
    return handle.db.prepare(sql).all(...params);
  }
  return handle.all(sql, [...params]);
}

function closeDb(handle) {
  if (handle && handle.mode === 'node:sqlite') {
    try { handle.db.close(); } catch { /* ignore */ }
  }
}

// 只读打开并在 fn 结束后关闭句柄（R2：不泄漏 sqlite 连接）。
function withDb(dbPath, label, fn) {
  const handle = openDbReadOnly(dbPath, label);
  try {
    return fn(handle);
  } finally {
    closeDb(handle);
  }
}

async function withOpenDbAsync(dbPath, label, fn) {
  const handle = openDbReadOnly(dbPath, label);
  try {
    return await fn(handle);
  } finally {
    closeDb(handle);
  }
}

function nativeDbPath() { return path.join(os.homedir(), '.zcode', 'cli', 'db', 'db.sqlite'); }
function tasksIndexPath() { return path.join(os.homedir(), '.zcode', 'v2', 'tasks-index.sqlite'); }

// ---------------------------------------------------------------------------
// 状态文件：原子写 + 排他锁 + 指纹校验
// ---------------------------------------------------------------------------

function sha256File(p) {
  return crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
}

// R2 合同：prompt 单次读取——SHA256 与正文取自同一原始 Buffer，两次读取之间
// 的并发改写不再可能造成“记录 SHA ≠ 发送正文”。SHA 按原始字节计算，
// 不得改为对解码后字符串求哈希。
function readPromptFileOnce(promptFile) {
  const bytes = fs.readFileSync(promptFile);
  return {
    bytes,
    sha256: crypto.createHash('sha256').update(bytes).digest('hex'),
    text: bytes.toString('utf8'),
  };
}

function makeMarker(kind, taskId) {
  const rnd = crypto.randomBytes(8).toString('hex');
  return `ZGUI-${kind}-${taskId}-${rnd}`;
}

function stateFingerprint(state) {
  return {
    url: state.url,
    workspace: state.workspace,
    taskId: state.taskId,
    promptSha256: state.prompt && state.prompt.sha256,
  };
}

function readState(statePath) {
  let raw;
  try { raw = fs.readFileSync(statePath, 'utf8'); }
  catch (e) {
    if (e.code === 'ENOENT') return null;
    throw new DriverError('STATE_UNREADABLE', `state 文件读取失败: ${e.message}`);
  }
  let obj;
  try { obj = JSON.parse(raw); } catch {
    throw new DriverError('STATE_CORRUPT', 'state 文件不是合法 JSON（fail-closed，不猜测、不覆写）');
  }
  if (!obj || obj.schema !== STATE_SCHEMA || !obj.url || !obj.workspace || !obj.taskId
    || !obj.prompt || !obj.prompt.sha256 || !obj.prompt.marker || !obj.phase) {
    throw new DriverError('STATE_CORRUPT', 'state 缺少必备身份字段（schema/url/workspace/taskId/prompt/phase），fail-closed');
  }
  return obj;
}

function writeStateAtomic(statePath, state) {
  state.updatedAt = Date.now();
  const tmp = `${statePath}.tmp-${process.pid}-${crypto.randomBytes(4).toString('hex')}`;
  const dir = path.dirname(statePath);
  fs.mkdirSync(dir, { recursive: true });
  const body = JSON.stringify(state, null, 2);
  const fd = fs.openSync(tmp, 'w', 0o600); // R2：临时文件仅属主可读（prompt 摘要在 state 内）
  try {
    fs.writeFileSync(fd, body, 'utf8');
    fs.fsyncSync(fd);
  } finally { fs.closeSync(fd); }
  fs.renameSync(tmp, statePath);
}

function pidAlive(pid) {
  if (!pid || typeof pid !== 'number') return false;
  try { process.kill(pid, 0); return true; } catch (e) { return e.code === 'EPERM'; }
}

async function withStateLock(statePath, fn) {
  const lockDir = `${statePath}.lock`;
  const ownerFile = path.join(lockDir, 'owner.json');
  fs.mkdirSync(path.dirname(statePath), { recursive: true });
  const nonce = crypto.randomBytes(16).toString('hex');
  // R2 合同：锁已存在一律拒绝（同 PID/陈旧/owner 缺失或损坏都不抢、不删）。
  // 不自动清理的原因：mkdir 到 owner 写入存在窗口，任何“识别后抢占”都可能造成并发重投；
  // 残留锁由 PM 人工核实后清理。
  try {
    fs.mkdirSync(lockDir);
  } catch (e) {
    if (e.code === 'EEXIST') {
      let ownerDesc = 'unknown';
      try { ownerDesc = fs.readFileSync(ownerFile, 'utf8').slice(0, 120); } catch { ownerDesc = 'owner.json 缺失或不可读'; }
      throw new DriverError('LOCK_HELD',
        `state 锁已存在，拒绝执行（不自动抢占/删除）: ${statePath}.lock；owner: ${ownerDesc}`,
        '若确认无并发持锁者，由 PM 人工删除该锁目录后重试。');
    }
    throw new DriverError('LOCK_ERROR', `无法创建锁: ${e.message}`);
  }
  try {
    fs.writeFileSync(ownerFile, JSON.stringify({ pid: process.pid, nonce, startedAt: Date.now(), host: os.hostname() }));
  } catch (e) {
    try { fs.rmSync(lockDir, { recursive: true, force: true }); } catch { /* ignore */ }
    throw new DriverError('LOCK_ERROR', `写入锁 owner 失败: ${e.message}`);
  }
  try {
    return await fn();
  } finally {
    // 释放核 nonce：只删除属于自己的锁；不匹配则原样保留（不是我们的锁）。
    try {
      const cur = JSON.parse(fs.readFileSync(ownerFile, 'utf8'));
      if (cur && cur.nonce === nonce) fs.rmSync(lockDir, { recursive: true, force: true });
    } catch { /* owner 缺失/损坏时不删，保守留下 */ }
  }
}

function assertSameFingerprint(existing, { url, workspace, taskId, promptSha256 }) {
  const fp = stateFingerprint(existing);
  const diffs = [];
  if (fp.url !== url) diffs.push(`url: ${fp.url} != ${url}`);
  if (fp.workspace !== workspace) diffs.push(`workspace: ${fp.workspace} != ${workspace}`);
  if (fp.taskId !== taskId) diffs.push(`taskId: ${fp.taskId} != ${taskId}`);
  if (fp.promptSha256 !== promptSha256) diffs.push('prompt sha256 不同（--prompt-file 内容已变化）');
  if (diffs.length) {
    throw new DriverError('STATE_FINGERPRINT_CONFLICT',
      `旧 state 与本次调用指纹不一致，拒绝:\n  ${diffs.join('\n  ')}`,
      '同一 state 只能对应同一任务输入；换任务请换新的 --state 路径。');
  }
}

function recordEvent(state, event) {
  state.history = state.history || [];
  state.history.push({ ts: new Date().toISOString(), event });
  if (state.history.length > 200) state.history.splice(0, state.history.length - 200);
}

// ---------------------------------------------------------------------------
// 页面合同（2026-10-02 runtime 3.14.3 实测定位器，见 references/35）
// ---------------------------------------------------------------------------

const LOC = {
  composerInput: 'v4-composer-input',
  send: 'v4-composer-send',
  workspaceTrigger: 'composer-workspace-trigger',
  workspaceItemPrefix: 'workspace-item-',     // data-testid="workspace-item-<绝对路径>"
  modeTrigger: 'chat-mode-select-trigger',
  modelTrigger: 'chat-model-select-trigger',
  taskNewButton: 'task-new-button',
  taskItemPrefix: 'task-item-',               // data-testid="task-item-<sessionId>"
  row: 'v4-row',
  sessionTitle: 'v4-session-title',
  modelConfig: 'v4-model-config', // R4：唯一模型配置节点，data-provider/data-model/data-mode 为机器 ID
};

async function waitComposerReady(page, timeout = 30000) {
  const send = page.getByTestId(LOC.send);
  await send.waitFor({ state: 'visible', timeout });
  const input = page.getByTestId(LOC.composerInput);
  await input.waitFor({ state: 'visible', timeout });
  const n = await page.getByRole('textbox').count();
  if (n !== 1) throw new DriverError('PAGE_STRUCTURE_CHANGED', `textbox 角色元素数量=${n}（预期唯一）`);
  if (await input.count() !== 1) throw new DriverError('PAGE_STRUCTURE_CHANGED', 'v4-composer-input 不唯一');
  return { send, input };
}

async function readTriggerText(page, testId) {
  try {
    const el = page.getByTestId(testId);
    if (await el.count() === 0) return null;
    return (await el.first().innerText({ timeout: 3000 })).trim();
  } catch { return null; }
}

async function readComposerText(page) {
  const el = page.getByTestId(LOC.composerInput).first();
  return (await el.innerText({ timeout: 5000 })).trim();
}

async function typeDraft(page, text) {
  const input = page.getByTestId(LOC.composerInput).first();
  await input.click();
  await page.keyboard.insertText(text);
  await page.waitForTimeout(250);
}

async function clearDraft(page) {
  const input = page.getByTestId(LOC.composerInput).first();
  await input.click();
  await page.keyboard.press('Meta+a');
  await page.keyboard.press('Backspace');
  await page.waitForTimeout(200);
}

function normText(s) { return s.replace(/\s+/g, ' ').trim(); }

// R3：模型 trigger 可能显示占位行「管理模型」；剥离后无具体模型名 = 未就绪。
function parseConcreteModel(modelLabel) {
  if (!modelLabel) return null;
  const lines = String(modelLabel).split('\n').map(x => x.trim()).filter(x => x && x !== '管理模型');
  return lines.length ? lines[0] : null;
}

// R3：发送前有界等待具体模型/模式就绪并回读；空值/「管理模型」占位不算有效配置。
async function waitForComposerConfig(page, timeoutMs, pollMs = 1000) {
  const deadline = Date.now() + timeoutMs;
  let modelLabel = null, modeLabel = null, model = null;
  for (;;) {
    modelLabel = await readTriggerText(page, LOC.modelTrigger);
    modeLabel = await readTriggerText(page, LOC.modeTrigger);
    model = parseConcreteModel(modelLabel);
    if (model && modeLabel) return { ready: true, modelLabel, modeLabel, concreteModel: model };
    if (Date.now() >= deadline) break;
    await page.waitForTimeout(pollMs);
  }
  return { ready: false, modelLabel, modeLabel, concreteModel: model,
    missing: [model ? null : 'model(具体模型名，非空且非「管理模型」占位)', modeLabel ? null : 'mode(模式标签)'].filter(Boolean) };
}

// ---------------------------------------------------------------------------
// R4：精确模型/provider/权限核验（--expected-provider/--expected-model/--expected-mode）
// 页面唯一 v4-model-config 的 data-provider/data-model/data-mode 是可靠机器 ID
//（2026-10-03 官方 3.14.4 DOM 实见：account:bigmodel-individual-coding-plan / GLM-5.3 / yolo）。
// 只读断言：严格等值、大小写敏感，不拿显示 label 推断套餐/权限，不按前缀放行；
// metadata 缺失/空/重复/不一致 fail-closed、零发送；不自动修改全局/会话模型配置。
// ---------------------------------------------------------------------------

const EXPECTED_CONFIG_KEYS = ['expected-provider', 'expected-model', 'expected-mode'];

async function readModelConfigIds(page) {
  const sel = `[data-testid="${LOC.modelConfig}"]`;
  const loc = page.locator(sel);
  const count = await loc.count();
  if (count !== 1) {
    return { ok: false, code: count === 0 ? 'MISSING' : 'DUPLICATE', count,
      provider: null, model: null, mode: null };
  }
  const attrs = await loc.evaluate((el) => ({
    provider: el.getAttribute('data-provider'),
    model: el.getAttribute('data-model'),
    mode: el.getAttribute('data-mode'),
  }));
  const empty = ['provider', 'model', 'mode'].filter(k => typeof attrs[k] !== 'string' || !attrs[k].trim());
  if (empty.length) {
    return { ok: false, code: 'EMPTY_ATTR', count, empty, ...attrs };
  }
  return { ok: true, code: 'OK', count, provider: attrs.provider, model: attrs.model, mode: attrs.mode };
}

// 有界等待 v4-model-config 元素与三属性齐备（只等待可读，不做期望比较）。
async function waitForModelConfigIds(page, timeoutMs, pollMs = 500) {
  const deadline = Date.now() + timeoutMs;
  let last = null;
  for (;;) {
    last = await readModelConfigIds(page);
    if (last.ok) return last;
    if (Date.now() >= deadline) return last;
    await page.waitForTimeout(pollMs);
  }
}

function expectedConfigDiffs(expected, actual) {
  const diffs = [];
  if (actual.provider !== expected.provider) diffs.push(`provider: actual=${JSON.stringify(actual.provider)} != expected=${JSON.stringify(expected.provider)}`);
  if (actual.model !== expected.model) diffs.push(`model: actual=${JSON.stringify(actual.model)} != expected=${JSON.stringify(expected.model)}`);
  if (actual.mode !== expected.mode) diffs.push(`mode: actual=${JSON.stringify(actual.mode)} != expected=${JSON.stringify(expected.mode)}`);
  return diffs;
}

// 严格核验并返回实际 IDs 证据（无授权 URL/凭证，仅三字段名值）。
async function assertExpectedConfig(page, expected, { stage, timeoutMs }) {
  const actual = await waitForModelConfigIds(page, timeoutMs);
  if (!actual.ok) {
    throw new DriverError('EXPECTED_CONFIG_UNREADABLE',
      `v4-model-config 不可读（stage=${stage}，code=${actual.code}${actual.empty ? `，空属性: ${actual.empty.join('/')}` : ''}，count=${actual.count}）`,
      '精确核验 fail-closed：元素缺失/重复或属性缺失/空一律零发送；由 PM 在可见 GUI 修正页面配置后重试，本驱动不自动改模型配置。');
  }
  const diffs = expectedConfigDiffs(expected, actual);
  if (diffs.length) {
    throw new DriverError('EXPECTED_CONFIG_MISMATCH',
      `页面模型配置与期望不一致（stage=${stage}）：\n  ${diffs.join('\n  ')}`,
      '严格等值比较（大小写敏感，不按显示 label 推断，不按前缀放行）；零发送。');
  }
  return { provider: actual.provider, model: actual.model, mode: actual.mode, stage, at: Date.now() };
}

// 三 flag 必须齐备且为非空字符串；无值/部分提供/空值在副作用前拒绝；全部不提供=兼容观察模式。
function parseExpectedConfigArgs(args, command) {
  const noValue = EXPECTED_CONFIG_KEYS.filter(k => args[k] === true);
  if (noValue.length) {
    throw new DriverError('EXPECTED_CONFIG_INVALID',
      `--${noValue[0]} 未提供值；${command} 的精确核验三参数（${EXPECTED_CONFIG_KEYS.map(k => `--${k}`).join(' ')}）必须齐备且为非空字符串`,
      '要么三参数齐备进入严格核验，要么全部不提供保持兼容观察模式（不得声称已精确核验）。');
  }
  const provided = EXPECTED_CONFIG_KEYS.filter(k => typeof args[k] === 'string' && args[k].trim() !== '');
  const present = EXPECTED_CONFIG_KEYS.filter(k => args[k] !== undefined);
  if (present.length !== provided.length || (provided.length !== 0 && provided.length !== 3)) {
    throw new DriverError('EXPECTED_CONFIG_INVALID',
      `精确核验参数部分提供（非空 ${provided.length}/3，出现 ${present.length}/3：${present.map(k => `--${k}`).join(' ') || '无'}）`,
      '三参数齐备且非空，或全部不提供；部分/空值在打开浏览器等副作用前拒绝。');
  }
  if (provided.length === 3) {
    return { provider: args['expected-provider'].trim(), model: args['expected-model'].trim(), mode: args['expected-mode'].trim() };
  }
  return null;
}

// state 期望继承/一致性（不降级、不静默升级，冲突在打开 browser 前拒绝）：
// - 显式期望与既有 state.expectedConfig 逐字段一致才放行；
// - 既有任务已过 fresh 阶段而无期望记录时，拒绝追加显式期望（不能事后追认已核验）；
// - 无显式期望但 state 有期望 → 继承原期望（严格性保持）。
function resolveExpectedConfig(explicit, state, command) {
  const existing = state && state.expectedConfig ? state.expectedConfig : null;
  if (explicit && !existing) {
    if (state && state.phase && state.phase !== 'fresh') {
      throw new DriverError('EXPECTED_CONFIG_CONFLICT',
        `state（phase=${state.phase}）无既有期望记录，${command} 不能在既有任务上追加显式期望（旧兼容 state 不能静默升级为已核验）`,
        '精确期望应在首次 submit 时提供；旧兼容任务保持观察语义，需要精确核验请开新任务/新 state。');
    }
    return explicit;
  }
  if (explicit && existing) {
    const diffs = expectedConfigDiffs(explicit, existing);
    if (diffs.length) {
      throw new DriverError('EXPECTED_CONFIG_CONFLICT',
        `显式期望与 state 既有期望不一致（${command}）：\n  ${diffs.join('\n  ')}`,
        '同一 state 期望不得漂移；如需不同期望请使用新任务/新 state。');
    }
    return existing;
  }
  if (!explicit && existing) return existing;
  return null;
}

// 选择 composer 工作区。返回实际动作。default/无项目场景（目标=服务自身 workspace）保持
// “选择项目”状态不点菜单——此前 ZLOCAL_GUI 会话即在该状态下创建于服务 workspace 目录。
async function ensureComposerWorkspace(page, workspaceAbs, serverInfo) {
  const trigger = page.getByTestId(LOC.workspaceTrigger);
  const before = await readTriggerText(page, LOC.workspaceTrigger);
  const serviceDefault = serverInfo && Array.isArray(serverInfo.workspaces) && serverInfo.workspaces[0]
    ? serverInfo.workspaces[0].path : null;
  if (before && before !== '选择项目') {
    // 已有选择：若当前标签匹配目标 workspace 的注册标签则不动，否则重开菜单精确选择
    const entry = (serverInfo.workspaces || []).find(w => path.resolve(w.path) === path.resolve(workspaceAbs));
    if (entry && normText(before) === normText(entry.label || '')) {
      return { action: 'already-selected', triggerLabel: before };
    }
  }
  if (serviceDefault && path.resolve(workspaceAbs) === path.resolve(serviceDefault)) {
    // 服务自带 workspace：无项目状态即落在该目录；不点击任何项目项。
    if (before && before !== '选择项目') {
      throw new DriverError('PAGE_WORKSPACE_MISMATCH',
        `目标为服务默认 workspace（无项目），但 composer 已选中项目「${before}」`, '刷新后重试；不接受未知初始态。');
    }
    return { action: 'service-default-no-project', triggerLabel: before };
  }
  await trigger.click();
  await page.waitForTimeout(600);
  const item = page.locator(`[data-testid="${LOC.workspaceItemPrefix}${workspaceAbs}"]`);
  const cnt = await item.count();
  if (cnt !== 1) {
    await page.keyboard.press('Escape').catch(() => {});
    throw new DriverError('PAGE_WORKSPACE_MISMATCH',
      `workspace 菜单中未找到唯一项 ${LOC.workspaceItemPrefix}${workspaceAbs}（count=${cnt}）`,
      '服务 server-info 未列出或页面未渲染该 workspace；确认 --workspace 与服务注册一致。');
  }
  await item.click();
  await page.waitForTimeout(800);
  const after = await readTriggerText(page, LOC.workspaceTrigger);
  if (!after || after === '选择项目') {
    throw new DriverError('PAGE_WORKSPACE_MISMATCH', `选择 workspace 后 trigger 仍为「${after}」`);
  }
  return { action: 'selected-from-menu', triggerLabel: after };
}

// 发送后 DOM 侧证据：出现包含 marker 的时间线行。
async function domEvidenceOfRow(page, marker, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const rows = page.getByTestId(LOC.row);
      const n = await rows.count();
      for (let i = 0; i < n; i++) {
        const t = (await rows.nth(i).innerText({ timeout: 2000 }).catch(() => ''));
        if (t.includes(marker)) return true;
      }
    } catch { /* 页面切换中 */ }
    await page.waitForTimeout(POLL_INTERVAL_MS);
  }
  return false;
}

// ---------------------------------------------------------------------------
// DB 绑定：marker → session_input → session/message（只读）
// ---------------------------------------------------------------------------

function findInputByMarker(native, marker) {
  // R2：instr 字面量匹配，marker 中的 %/_ 不再被当 SQL 通配符。
  const rows = dbAll(native,
    `SELECT si.id AS input_id, si.session_id, si.kind, si.delivery, si.status AS input_status,
            si.promoted_message_id, si.admitted_sequence, si.time_created, si.time_updated,
            s.directory AS session_directory, s.title AS session_title
     FROM session_input si JOIN session s ON s.id = si.session_id
     WHERE instr(si.payload, ?) > 0
     ORDER BY si.time_created DESC LIMIT 5`, [marker]);
  return rows;
}

function getTurnInfo(native, sessionId, userMessageId) {
  const rows = dbAll(native,
    `SELECT turn_id, status AS turn_status, user_message_id, started_at, completed_at
     FROM turn_usage WHERE session_id = ? AND user_message_id = ?
     ORDER BY started_at DESC LIMIT 1`, [sessionId, userMessageId]);
  return rows[0] || null;
}

function getAssistantFinal(native, sessionId, userMessageId) {
  // R2 合同：只报告“最后一条 assistant 消息”的文本与状态；
  // 是否可作为最终交付由调用方按 turn completed 门控，绝不拿中途含 text 的消息充当 final。
  const msgs = dbAll(native,
    `SELECT id, sequence, data FROM message
     WHERE session_id = ? AND json_extract(data, '$.parentID') = ?
     ORDER BY sequence`, [sessionId, userMessageId]);
  const assistant = msgs.filter(m => {
    try { return JSON.parse(m.data).role === 'assistant'; } catch { return false; }
  });
  if (!assistant.length) {
    return {
      messageCount: 0, lastMessageId: null, lastMessageCompleted: false,
      lastMessageHasText: false, finalText: null,
      rawStatus: 'no-assistant-message',
    };
  }
  const last = assistant[assistant.length - 1];
  let meta = {};
  try { meta = JSON.parse(last.data); } catch { /* ignore */ }
  const parts = dbAll(native,
    `SELECT id, json_extract(data, '$.type') AS ptype, json_extract(data, '$.text') AS ptext
     FROM part WHERE message_id = ? ORDER BY sequence`, [last.id]);
  const textParts = parts.filter(p => p.ptype === 'text').map(p => String(p.ptext || ''));
  return {
    messageCount: assistant.length,
    lastMessageId: last.id,
    lastMessageCompleted: Boolean(meta.time && meta.time.completed) && !meta.error,
    lastMessageHasText: textParts.length > 0,
    finalText: textParts.length ? textParts.join('\n') : null,
    rawStatus: 'reported',
  };
}

// 汇总（submit 对账 / observe 共用）：按 state 的 marker+binding 精确取数。
// R2：目录不符 / promotedMessageId / turnId 冲突一律拒绝（fail-closed），不再“提示后继续”。
// nativePath 仅供测试注入；生产恒为真实原生 DB 只读。
function collectStatus(state, nativePath) {
  const dbp = nativePath || nativeDbPath();
  const result = { sources: { nativeDb: dbp, mode: 'ro' } };
  const marker = state.prompt.marker;
  const out = withDb(dbp, '原生 DB', (native) => {
    const candidates = findInputByMarker(native, marker);
    const bound = state.binding || null;
    let inputRow = null;
    if (bound) {
      const exact = dbAll(native,
        `SELECT si.id AS input_id, si.session_id, si.status AS input_status, si.promoted_message_id,
                si.payload, s.directory AS session_directory, s.title AS session_title
         FROM session_input si JOIN session s ON s.id = si.session_id
         WHERE si.id = ?`, [bound.inputId]);
      if (!exact.length) throw new DriverError('IDENTITY_MISMATCH', `state 绑定的 input ${bound.inputId} 在 DB 中不存在`);
      if (!String(exact[0].payload || '').includes(marker)) {
        throw new DriverError('IDENTITY_MISMATCH', `input ${bound.inputId} payload 不含 marker，身份不一致（fail-closed）`);
      }
      if (exact[0].session_id !== bound.sessionId) {
        throw new DriverError('IDENTITY_MISMATCH', `input ${bound.inputId} 的 session 与 state 绑定不符`);
      }
      if (bound.promotedMessageId && exact[0].promoted_message_id
          && bound.promotedMessageId !== exact[0].promoted_message_id) {
        throw new DriverError('IDENTITY_MISMATCH',
          `promotedMessageId 冲突：state=${bound.promotedMessageId}，DB=${exact[0].promoted_message_id}`);
      }
      if (path.resolve(exact[0].session_directory) !== path.resolve(state.workspace)) {
        throw new DriverError('DIRECTORY_MISMATCH',
          `session.directory=${exact[0].session_directory} 与 state.workspace=${state.workspace} 不符，拒绝对账`);
      }
      inputRow = exact[0];
    } else if (candidates.length === 1) {
      inputRow = candidates[0];
      if (path.resolve(inputRow.session_directory) !== path.resolve(state.workspace)) {
        throw new DriverError('DIRECTORY_MISMATCH',
          `session.directory=${inputRow.session_directory} 与 state.workspace=${state.workspace} 不符，拒绝对账`);
      }
    } else if (candidates.length > 1) {
      throw new DriverError('BINDING_AMBIGUOUS', `marker 命中 ${candidates.length} 条 input，拒绝自动选择`, '此 marker 不应复用；请人工核对 DB。');
    }
    return { candidates: candidates.length, inputRow };
  });
  result.markerHits = out.candidates;
  const inputRow = out.inputRow;
  if (!inputRow) {
    return { found: false, ...result };
  }
  // 二次（含 turn 冲突核验与 final 门控）也要在句柄存活期内完成 → 重新开句柄。
  const detail = withDb(dbp, '原生 DB', (native) => {
    const turn = inputRow.promoted_message_id
      ? getTurnInfo(native, inputRow.session_id, inputRow.promoted_message_id) : null;
    const turnStatus = turn ? turn.turn_status : 'not-recorded';
    if (state.binding && state.binding.turnId && turn && turn.turn_id
        && state.binding.turnId !== turn.turn_id) {
      throw new DriverError('IDENTITY_MISMATCH',
        `turnId 冲突：state=${state.binding.turnId}，DB=${turn.turn_id}`);
    }
    const final = inputRow.promoted_message_id
      ? getAssistantFinal(native, inputRow.session_id, inputRow.promoted_message_id) : null;
    // R2 门控：仅在 精确 turn completed + 最后 assistant 消息已完成 + 含文本 + input promoted 时给 finalText。
    let finalText = null;
    let finalTextAvailability;
    if (!final || !inputRow.promoted_message_id) {
      finalTextAvailability = 'not-promoted-no-turn';
    } else if (inputRow.input_status !== 'promoted') {
      finalTextAvailability = `input-${inputRow.input_status}`;
    } else if (turnStatus !== 'completed') {
      finalTextAvailability = `turn-${turnStatus}`;
    } else if (!final.lastMessageCompleted) {
      finalTextAvailability = 'last-assistant-message-open';
    } else if (!final.lastMessageHasText) {
      finalTextAvailability = 'no-text-in-last-assistant-message';
    } else {
      finalText = final.finalText;
      finalTextAvailability = 'available';
    }
    return { turn, turnStatus, final, finalText, finalTextAvailability };
  });
  return {
    found: true,
    ...result,
    inputId: inputRow.input_id,
    sessionId: inputRow.session_id,
    inputStatus: inputRow.input_status,           // 接收（admitted/promoted/...）
    promotedMessageId: inputRow.promoted_message_id || null,
    sessionDirectory: inputRow.session_directory,
    sessionTitle: inputRow.session_title,
    turn: detail.turn
      ? { turnId: detail.turn.turn_id, status: detail.turn.turn_status }   // 回合完成与接收分开上报
      : { status: 'not-recorded', note: 'turn_usage 无该 user_message 行（GUI 交互会话常见）' },
    final: detail.final ? {
      messageCount: detail.final.messageCount,
      lastMessageId: detail.final.lastMessageId,
      lastMessageCompleted: detail.final.lastMessageCompleted,
      lastMessageHasText: detail.final.lastMessageHasText,
    } : null,
    finalText: detail.finalText,
    finalTextAvailability: detail.finalTextAvailability,
  };
}

// ---------------------------------------------------------------------------
// inspect
// ---------------------------------------------------------------------------

async function cmdInspect(args, deps) {
  const rawUrl = requireString(args, 'url');
  assertLoopbackUrl(rawUrl);
  const expected = parseExpectedConfigArgs(args, 'inspect'); // 部分提供等在副作用前拒绝
  const headless = args.headed !== true;
  const d = deps || defaultDeps(headless);
  const serverInfo = await d.fetchServerInfo(`${new URL(rawUrl).origin}/api/server-info`).catch(e => {
    throw new DriverError('SERVICE_UNREACHABLE', `server-info 获取失败: ${e.message}`);
  });
  let workspaceAbs = null;
  if (args.workspace) {
    workspaceAbs = assertAbsPath(args.workspace, 'workspace');
  }

  const handle = await d.openPage(rawUrl);
  try {
    await handle.page.goto(rawUrl, { waitUntil: 'domcontentloaded', timeout: 20000 });
    const { send } = await waitComposerReady(handle.page);
    const page = handle.page;
    // R3：有界等待具体模型/模式；未就绪时 inspect 不再报普通 ok。
    const readyTimeoutMs = Number(args['ready-timeout-ms']) >= 0 ? Number(args['ready-timeout-ms']) : 8000;
    const cfg = await waitForComposerConfig(page, readyTimeoutMs);
    // R4：机器 ID 读取（只读）。expected 未提供时 match 保持 null（兼容观察模式，不能称已精确核验）。
    const ids = await waitForModelConfigIds(page, readyTimeoutMs);
    const expectedMatch = expected
      ? (ids.ok ? expectedConfigDiffs(expected, ids).length === 0 : 'unknown')
      : null;
    const out = {
      status: cfg.ready ? 'ok' : 'not-ready',
      url: rawUrl,
      pageTitle: await page.title(),
      serverInfo: {
        serverId: serverInfo.serverId, version: serverInfo.version,
        authRequired: serverInfo.authRequired,
        workspaces: (serverInfo.workspaces || []).map(w => w.path),
      },
      locators: {
        composerInput: await page.getByTestId(LOC.composerInput).count(),
        sendButton: await page.getByTestId(LOC.send).count(),
        sendDisabledOnEmpty: await send.isDisabled(),
        workspaceTrigger: await page.getByTestId(LOC.workspaceTrigger).count(),
        modeTrigger: await page.getByTestId(LOC.modeTrigger).count(),
        modelTrigger: await page.getByTestId(LOC.modelTrigger).count(),
        taskNewButton: await page.getByTestId(LOC.taskNewButton).count(),
        textboxRole: await page.getByRole('textbox').count(),
      },
      observed: {
        workspaceTriggerLabel: await readTriggerText(page, LOC.workspaceTrigger),
        modeLabel: cfg.modeLabel,
        modelLabel: cfg.modelLabel,
      },
      configReady: cfg.ready,
      concreteModel: cfg.concreteModel,
      modelConfig: {
        readable: ids.ok, code: ids.code, count: ids.count,
        provider: ids.provider || null, model: ids.model || null, mode: ids.mode || null,
        note: '唯一 v4-model-config 的 data-provider/data-model/data-mode 机器 ID（只读）；不按显示 label 推断套餐/权限。',
      },
      expectedConfig: expected,
      expectedMatch,
    };
    if (!cfg.ready) {
      out.configIssue = {
        missing: cfg.missing,
        hint: '新浏览器 context 未见具体默认模型/模式（modelLabel 为空或仅为「管理模型」占位）。submit/follow-up 在此状态下会拒绝发送；由 PM 在可见 GUI 确认默认模型后重试。',
      };
    }
    // workspace 菜单项（打开→采集→关闭；不写入任何草稿）
    try {
      await page.getByTestId(LOC.workspaceTrigger).click();
      await page.waitForTimeout(700);
      out.workspaceMenuItems = await page.$$eval(`[data-testid^="${LOC.workspaceItemPrefix}"]`, els =>
        els.map(e => e.getAttribute('data-testid').slice('workspace-item-'.length)));
      await page.keyboard.press('Escape').catch(() => {});
    } catch (e) {
      out.workspaceMenuError = e.message.split('\n')[0];
    }
    if (workspaceAbs) {
      const inServer = (serverInfo.workspaces || []).some(w => path.resolve(w.path) === path.resolve(workspaceAbs));
      const inMenu = (out.workspaceMenuItems || []).some(p => path.resolve(p) === path.resolve(workspaceAbs));
      out.workspaceCheck = {
        workspace: workspaceAbs,
        inServerInfo: inServer,
        inComposerMenu: inMenu,
        note: inServer && !inMenu
          ? '服务自带 workspace（server-info 首项）：composer 保持「选择项目」即落在该目录，不点菜单'
          : (!inServer && !inMenu ? '既不在 server-info 也不在菜单——submit 将拒绝' : undefined),
      };
    }
    out.note = 'inspect 为只读探针：未键入草稿、未点击发送、未创建任何模型任务。';
    okResult('inspect', out);
  } finally {
    await handle.close();
  }
}

// ---------------------------------------------------------------------------
// submit（唯一新任务输入；同 state 不自动重发，跨进程不承诺 exactly-once）
// ---------------------------------------------------------------------------

async function pollDbUntilBoundOrTimeout(native, marker, workspace, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let lastErr = null;
  while (Date.now() < deadline) {
    try {
      const rows = findInputByMarker(native, marker);
      if (rows.length === 1) {
        const r = rows[0];
        if (path.resolve(r.session_directory) !== path.resolve(workspace)) {
          throw new DriverError('BINDING_MISMATCH',
            `新 session directory=${r.session_directory} 与目标 workspace=${workspace} 不符（不重试，人工处理）`);
        }
        return r;
      }
      if (rows.length > 1) {
        throw new DriverError('BINDING_AMBIGUOUS', `marker 命中 ${rows.length} 条 input`);
      }
    } catch (e) {
      if (e instanceof DriverError) throw e;
      lastErr = e; // DB 暂不可读（如 WAL 锁）→ 继续轮询
    }
    await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
  }
  if (lastErr) return { pollError: lastErr.message };
  return null;
}

async function cmdSubmit(args, deps) {
  const rawUrl = requireString(args, 'url');
  const u = assertLoopbackUrl(rawUrl);
  const workspace = assertAbsPath(requireString(args, 'workspace'), 'workspace');
  const taskId = requireString(args, 'task-id');
  const promptFile = requireString(args, 'prompt-file');
  const statePath = assertAbsPath(requireString(args, 'state'), 'state');
  const timeoutMs = Number(args['timeout-ms']) > 0 ? Number(args['timeout-ms']) : DEFAULT_TIMEOUT_MS;
  const headless = args.headed !== true;
  const d = deps || defaultDeps(headless);
  const expectedExplicit = parseExpectedConfigArgs(args, 'submit'); // R4：部分/无值在副作用前拒绝

  if (!fs.existsSync(promptFile)) throw new DriverError('ARG_INVALID', `--prompt-file 不存在: ${promptFile}`);
  const promptRead = readPromptFileOnce(promptFile); // R2：单次读取，SHA 与正文同源
  const promptSha = promptRead.sha256;
  const promptText = promptRead.text;

  await withStateLock(statePath, async () => {
    const existing = readState(statePath);
    if (existing) {
      assertSameFingerprint(existing, { url: rawUrl, workspace, taskId, promptSha256: promptSha });
    }
    // R4：期望继承/一致性在打开 browser 前裁决（显式不同/漂移拒绝且不重发）。
    const expected = resolveExpectedConfig(expectedExplicit, existing, 'submit');

    // 幂等路径：state 已有 intent/sent 记录 → 只对账，不再打开发送流程。
    if (existing && existing.phase !== 'fresh') {
      const status = await reconcileOnly(existing, 'submit', d.nativeDbPath ? d.nativeDbPath() : undefined);
      if (status.unconfirmed) {
        unknownResult('submit', status.payload);
      } else {
        okResult('submit', status.payload);
      }
      return;
    }

    const serverInfo = await d.fetchServerInfo(`${u.origin}/api/server-info`).catch(e => {
      throw new DriverError('SERVICE_UNREACHABLE', `server-info 获取失败: ${e.message}`);
    });
    const inServer = (serverInfo.workspaces || []).some(w => path.resolve(w.path) === path.resolve(workspace));
    if (!inServer) {
      throw new DriverError('PAGE_WORKSPACE_MISMATCH',
        `--workspace ${workspace} 不在服务 server-info workspaces 中`,
        '服务只管理其注册 workspace；核对 --url 服务与 --workspace。');
    }

    const state = existing || {
      schema: STATE_SCHEMA,
      driverVersion: DRIVER_VERSION,
      url: rawUrl, workspace, taskId,
      phase: 'fresh',
      createdAt: Date.now(),
      history: [],
      followUps: {},
    };
    if (!state.prompt) {
      const marker = makeMarker('M', taskId.replace(/[^A-Za-z0-9_-]/g, '_'));
      state.prompt = {
        file: path.resolve(promptFile),
        sha256: promptSha,
        bytes: Buffer.byteLength(promptText),
        marker, // R2：不保存 prompt 内容预览，避免任务文本在 state 中扩散
      };
      recordEvent(state, 'prompt-registered');
    }

    const handle = await d.openPage(rawUrl);
    try {
      const page = handle.page;
      await page.goto(rawUrl, { waitUntil: 'domcontentloaded', timeout: 20000 });
      await waitComposerReady(page);

      // 全新草稿页：不碰他人草稿。到达时 composer 非空 → fail-closed。
      const initialDraft = await readComposerText(page);
      if (initialDraft) {
        throw new DriverError('COMPOSER_NOT_EMPTY',
          `composer 已有内容（${initialDraft.slice(0, 60)}…），拒绝写入`, '本驱动不覆盖任何既有草稿。');
      }
      // R2 顺序：先进入新任务草稿（task-new-button），再选 workspace，最后回读 mode/model。
      const newBtn = page.getByTestId(LOC.taskNewButton);
      if (await newBtn.count() !== 1) {
        throw new DriverError('PAGE_STRUCTURE_CHANGED', `task-new-button count=${await newBtn.count()}（预期 1）`);
      }
      await newBtn.click();
      await page.waitForTimeout(600);

      const wsInfo = await ensureComposerWorkspace(page, workspace, serverInfo);
      // R3：发送前有界等待具体模型/模式就绪并回读；空值或「管理模型」占位一律拒绝，不盲发。
      const readyTimeoutMs = Number(args['ready-timeout-ms']) > 0 ? Number(args['ready-timeout-ms']) : 30000;
      const cfg = await waitForComposerConfig(page, readyTimeoutMs);
      if (!cfg.ready) {
        throw new DriverError('CONFIG_NOT_READY',
          `composer 配置未就绪：缺失 ${cfg.missing.join('、')}（modelLabel=${JSON.stringify(cfg.modelLabel)}，modeLabel=${JSON.stringify(cfg.modeLabel)}）`,
          '新浏览器 context 可能未自动选定默认模型。由 PM 在可见 GUI 确认/选择默认模型后重试；本驱动不自动改选模型、不盲发。');
      }
      state.page = {
        wsTriggerLabel: wsInfo.triggerLabel,
        wsAction: wsInfo.action,
        modeObserved: cfg.modeLabel,
        modelObserved: cfg.modelLabel,
        concreteModel: cfg.concreteModel,
        configReady: true,
        note: 'mode/model 为页面实际配置的只读观测（已回读具体值）；未修改全局默认，不据此声称套餐。',
      };
      // R4：期望持久化进 state 身份（不降级；兼容模式不写、不追认）。
      if (expected) state.expectedConfig = { ...expected };
      recordEvent(state, 'new-task-then-workspace-then-mode-model-ready');

      // R4 第一次核验：typeDraft 前严格等值（provider/model/mode 机器 ID）。
      if (expected) {
        state.page.expectedChecks = state.page.expectedChecks || [];
        state.page.expectedChecks.push(await assertExpectedConfig(page, expected, { stage: 'submit-pre-draft', timeoutMs: readyTimeoutMs }));
      }

      const draftNow = await readComposerText(page);
      if (draftNow) {
        throw new DriverError('COMPOSER_NOT_EMPTY', `新任务 composer 非空（${draftNow.slice(0, 60)}…），拒绝`);
      }

      const marker = state.prompt.marker;
      const fullText = `${promptText}\n\n[${marker}]`;
      await typeDraft(page, fullText);
      const readBack = await readComposerText(page);
      if (!readBack.includes(marker) || normText(readBack) !== normText(fullText)) {
        await clearDraft(page).catch(() => {});
        throw new DriverError('DRAFT_READBACK_MISMATCH', '草稿回读与输入不一致（清空后放弃，未发送）');
      }
      const send = page.getByTestId(LOC.send);
      if (await send.isDisabled()) {
        await clearDraft(page).catch(() => {});
        throw new DriverError('SEND_DISABLED', '草稿就绪但发送按钮禁用（未发送）');
      }

      // R4 第二次核验：草稿回读后、intent 写入与唯一 click 前紧邻再核；
      // 第一次正确而第二次漂移（变 Flash/不同 provider/非期望 mode/不可读）必须零 click，
      // 仅清理本 driver 自己键入的草稿，state 不写 intent、不可盲重投。
      if (expected) {
        try {
          const secondCheck = await assertExpectedConfig(page, expected, { stage: 'submit-pre-click', timeoutMs: readyTimeoutMs });
          state.page.expectedChecks.push(secondCheck);
        } catch (e) {
          await clearDraft(page).catch(() => {});
          throw e;
        }
      }

      // ★ intent 先行持久化，再唯一一次点击
      state.phase = 'intent';
      state.intentAt = Date.now();
      recordEvent(state, 'send-intent-written(before single click)');
      writeStateAtomic(statePath, state);

      await send.click();
      recordEvent(state, 'send-clicked-once');
      writeStateAtomic(statePath, state);

      // 确认接收：DOM 行证据 + DB input 行（DB 为准做绑定）
      const domSeen = await domEvidenceOfRow(page, marker, Math.min(timeoutMs, 30000));
      const nativePath2 = d.nativeDbPath ? d.nativeDbPath() : nativeDbPath();
      const bound = await withOpenDbAsync(nativePath2, '原生 DB', async (native) =>
        pollDbUntilBoundOrTimeout(native, marker, workspace, timeoutMs));

      if (bound && !bound.pollError && bound.input_id) {
        const turn = bound.promoted_message_id
          ? withDb(nativePath2, '原生 DB', (nh) => getTurnInfo(nh, bound.session_id, bound.promoted_message_id))
          : null;
        state.phase = 'sent-bound';
        state.binding = {
          sessionId: bound.session_id,
          inputId: bound.input_id,
          inputStatus: bound.input_status,
          promotedMessageId: bound.promoted_message_id || null,
          sessionDirectory: bound.session_directory,
          sessionTitle: bound.session_title,
          turnId: turn ? turn.turn_id : null,
          boundAt: Date.now(),
          domRowObserved: domSeen,
          evidence: ['intent-before-click', 'dom-row-marker', 'db-session-input-marker'],
        };
        recordEvent(state, 'sent-bound');
        writeStateAtomic(statePath, state);
        okResult('submit', {
          status: 'sent-bound',
          taskId, marker,
          binding: state.binding,
          page: state.page,
          note: '本次调用完成一次 GUI DOM 发送并绑定 session/input（同 state 重复调用不会再发送）；turn 完成与 PM 验收另行 observe。',
        });
      } else {
        state.phase = 'sent-unconfirmed';
        state.unconfirmed = {
          since: Date.now(),
          domRowObserved: domSeen,
          pollError: bound && bound.pollError,
          reason: '点击后未在超时内取到唯一 DB input 行；状态保留 unknown，不自动重试。',
        };
        recordEvent(state, 'sent-unconfirmed');
        writeStateAtomic(statePath, state);
        unknownResult('submit', {
          status: 'unknown',
          taskId, marker,
          domRowObserved: domSeen,
          pollError: bound && bound.pollError,
          note: '发送点击已发生且 intent 已持久化；但未确认接收。下一步：observe 对账；禁止重复 submit。',
        });
      }
    } finally {
      await handle.close();
    }
  });
}

// 只读对账（幂等路径 & observe 共用核心）
async function reconcileOnly(state, command, nativePath) {
  const status = collectStatus(state, nativePath); // 目录/身份/turn 冲突在此 fail-closed 抛出
  if (!status.found) {
    return {
      unconfirmed: true,
      payload: {
        status: 'unknown',
        phase: state.phase,
        taskId: state.taskId,
        marker: state.prompt.marker,
        note: 'state 已记录发送意图，但 DB 未见 marker input。不重发（可能未送达或 DB 延迟）；可稍后 observe 复查。',
      },
    };
  }
  const payload = {
    status: 'reconciled',
    phase: state.phase,
    taskId: state.taskId,
    marker: state.prompt.marker,
    inputId: status.inputId,
    sessionId: status.sessionId,
    inputStatus: status.inputStatus,
    sessionDirectory: status.sessionDirectory,
    sessionTitle: status.sessionTitle,
    turn: status.turn,
    final: status.final,
    finalText: status.finalText,
    finalTextAvailability: status.finalTextAvailability,
    note: '同 state 重复调用仅对账，不点击发送（本驱动只承诺同 state 内不自动重发，不承诺跨进程 exactly-once）。'
      + 'finalText 仅在 turn 精确 completed 且最后 assistant 消息完成且含文本时给出；接收（inputStatus）与回合完成（turn）分开判断；turn completed 不等于 PM 验收通过。',
  };
  return { unconfirmed: false, payload };
}

// ---------------------------------------------------------------------------
// observe / collect
// ---------------------------------------------------------------------------

async function cmdObserve(args, deps) {
  const statePath = assertAbsPath(requireString(args, 'state'), 'state');
  const state = readState(statePath); // 损坏 → readState 抛错
  if (!state) throw new DriverError('STATE_MISSING', `state 文件不存在: ${statePath}`, 'observe 只对已记录的任务对账；submit 先行。');
  const command = args._[0] || 'observe';
  // --input-id 可选：观察某条 follow-up 轮次（默认观察首轮提交）。
  let effective = state;
  if (args['input-id']) {
    const fu = (state.followUps || {})[args['input-id']];
    if (!fu) throw new DriverError('ARG_INVALID', `state 中不存在 follow-up input-id ${args['input-id']}`);
    effective = {
      ...state,
      prompt: fu.prompt,
      binding: fu.binding ? { ...fu.binding, sessionId: state.binding.sessionId } : null,
      phase: fu.phase,
    };
  }
  const status = await reconcileOnly(effective, command, deps && deps.nativeDbPath ? deps.nativeDbPath() : undefined);
  if (!status.unconfirmed && !args['input-id'] && state.phase === 'intent') {
    // 崩溃恢复：点击可能已发生但未及绑定 → 现在能绑上则升级记录（仍不点击）
    await withStateLock(statePath, async () => {
      const cur = readState(statePath);
      if (cur && cur.phase === 'intent') {
        cur.phase = 'sent-bound-recovered';
        cur.binding = cur.binding || {
          sessionId: status.payload.sessionId,
          inputId: status.payload.inputId,
          inputStatus: status.payload.inputStatus,
          recoveredAt: Date.now(),
          evidence: ['intent-recovered-from-db'],
        };
        recordEvent(cur, 'reconciled-recovered-binding');
        writeStateAtomic(statePath, cur);
      }
    });
    okResult(command, { ...status.payload, phase: 'sent-bound-recovered' });
    return;
  }
  if (status.unconfirmed) {
    unknownResult(command, status.payload);
  } else {
    okResult(command, status.payload);
  }
}

// ---------------------------------------------------------------------------
// follow-up（沿原 session 新轮次；恢复不可证 → UNSUPPORTED）
// ---------------------------------------------------------------------------

async function cmdFollowUp(args, deps) {
  const statePath = assertAbsPath(requireString(args, 'state'), 'state');
  const promptFile = requireString(args, 'prompt-file');
  const inputId = requireString(args, 'input-id');
  const timeoutMs = Number(args['timeout-ms']) > 0 ? Number(args['timeout-ms']) : DEFAULT_TIMEOUT_MS;
  const headless = args.headed !== true;
  const d = deps || defaultDeps(headless);
  const expectedExplicit = parseExpectedConfigArgs(args, 'follow-up'); // R4：部分/无值在副作用前拒绝

  if (!fs.existsSync(promptFile)) throw new DriverError('ARG_INVALID', `--prompt-file 不存在: ${promptFile}`);
  const promptRead = readPromptFileOnce(promptFile); // R2：单次读取，SHA 与正文同源
  const promptSha = promptRead.sha256;
  const promptText = promptRead.text;

  await withStateLock(statePath, async () => {
    const state = readState(statePath);
    if (!state) throw new DriverError('STATE_MISSING', `state 文件不存在: ${statePath}`, 'follow-up 只沿既有 state 的原 session 进行。');
    // R4：follow-up 默认继承 state 期望；显式传值必须与 state 既有期望逐字段一致（在打开 browser 前裁决）。
    const expected = resolveExpectedConfig(expectedExplicit, state, 'follow-up');
    if (state.url) assertLoopbackUrl(state.url);
    if (!state.binding || !state.binding.sessionId) {
      unsupportedResult('follow-up', {
        reason: `state phase=${state.phase} 无已绑定 session；follow-up 只沿已绑定原 session 进行`,
      });
      return;
    }
    const sessionId = state.binding.sessionId;
    const originalMarker = state.prompt.marker;
    state.followUps = state.followUps || {};

    // 每轮去重：同 input-id 已有记录 → 对账该轮自身绑定；prompt 指纹不同 → 冲突拒绝。
    const prev = state.followUps[inputId];
    if (prev) {
      if (prev.prompt.sha256 !== promptSha) {
        throw new DriverError('STATE_FINGERPRINT_CONFLICT',
          `input-id ${inputId} 已存在且 prompt sha 不同`, '一轮反馈对应一个 input-id；换内容请换 input-id。');
      }
      const effective = {
        ...state,
        prompt: prev.prompt,
        binding: prev.binding ? { ...prev.binding, sessionId } : null,
        phase: prev.phase,
      };
      const status = await reconcileOnly(effective, 'follow-up', d.nativeDbPath ? d.nativeDbPath() : undefined);
      if (status.unconfirmed) unknownResult('follow-up', { ...status.payload, inputId });
      else okResult('follow-up', { ...status.payload, inputId, note: '同 input-id 重复调用仅对账该轮，未再次点击。' });
      return;
    }

    const handle = await d.openPage(state.url);
    try {
      const page = handle.page;
      await page.goto(state.url, { waitUntil: 'domcontentloaded', timeout: 20000 });
      await waitComposerReady(page);

      // 恢复目标会话：仅按 state 绑定的 sessionId 精确匹配 task-item，绝不按标题模糊点击。
      const item = page.locator(`[data-testid="${LOC.taskItemPrefix}${sessionId}"]`);
      let cnt = 0;
      const restoreWaitMs = Number(args['restore-wait-ms']) > 0 ? Number(args['restore-wait-ms']) : 15000;
      const deadline = Date.now() + restoreWaitMs;
      while (Date.now() < deadline && (cnt = await item.count()) === 0) {
        await page.waitForTimeout(1000);
      }
      if (cnt !== 1) {
        unsupportedResult('follow-up', {
          reason: `sidebar 未出现 task-item-${sessionId}（count=${cnt}）`,
          detail: '本机 default workspace 任务的 sidebar 恢复尚未被证明；按合同不按模糊标题点其他任务。',
          suggestion: '保留原会话：由 PM 在 GUI 中人工打开原会话接管处理或继续排查可见性；本驱动不另起新任务替代原任务。',
        });
        return;
      }
      // 展开可能的折叠父级后点击
      await item.evaluate(el => {
        let p = el.parentElement;
        while (p) {
          if (p.getAttribute('data-state') === 'closed') { p.click(); break; }
          p = p.parentElement;
        }
      }).catch(() => {});
      await page.waitForTimeout(600);
      await item.scrollIntoViewIfNeeded().catch(() => {});
      await item.click();
      await page.getByTestId(LOC.row).first().waitFor({ timeout: 10000 });
      await page.waitForTimeout(1200);

      // 身份核验：原 marker 必须出现在该会话时间线里
      const rows = page.getByTestId(LOC.row);
      const n = await rows.count();
      let sawOriginal = false;
      for (let i = 0; i < n; i++) {
        const t = await rows.nth(i).innerText({ timeout: 2000 }).catch(() => '');
        if (t.includes(originalMarker)) { sawOriginal = true; break; }
      }
      if (!sawOriginal) {
        unsupportedResult('follow-up', {
          reason: `已打开 task-item-${sessionId}，但时间线未见原输入 marker，拒绝向其发送`,
        });
        return;
      }

      // composer 必须为空（不打断他人未发送草稿）
      const draft = await readComposerText(page);
      if (draft) {
        throw new DriverError('COMPOSER_NOT_EMPTY', `目标会话 composer 非空（${draft.slice(0, 60)}…），拒绝写入`);
      }
      // R3：follow-up 发送前同样等待具体模型/模式就绪并回读；占位/空值拒绝。
      const fuReadyTimeoutMs = Number(args['ready-timeout-ms']) > 0 ? Number(args['ready-timeout-ms']) : 30000;
      const fuCfg = await waitForComposerConfig(page, fuReadyTimeoutMs);
      if (!fuCfg.ready) {
        throw new DriverError('CONFIG_NOT_READY',
          `follow-up composer 配置未就绪：缺失 ${fuCfg.missing.join('、')}（modelLabel=${JSON.stringify(fuCfg.modelLabel)}）`,
          '由 PM 在可见 GUI 确认/选择默认模型后重试；本驱动不自动改选模型、不盲发。');
      }
      state.page = Object.assign({}, state.page, {
        modeObserved: fuCfg.modeLabel, modelObserved: fuCfg.modelLabel,
        concreteModel: fuCfg.concreteModel, configReady: true,
      });

      // R4 第一次核验（follow-up）：typeDraft 前严格等值；漂移/不可读零 click。
      let fuFirstCheck = null;
      if (expected) {
        fuFirstCheck = await assertExpectedConfig(page, expected, { stage: 'followup-pre-draft', timeoutMs: fuReadyTimeoutMs });
      }

      const marker = makeMarker('F', inputId.replace(/[^A-Za-z0-9_-]/g, '_'));
      const fullText = `${promptText}\n\n[${marker}]`;
      await typeDraft(page, fullText);
      const readBack = await readComposerText(page);
      if (!readBack.includes(marker) || normText(readBack) !== normText(fullText)) {
        await clearDraft(page).catch(() => {});
        throw new DriverError('DRAFT_READBACK_MISMATCH', 'follow-up 草稿回读不一致（已清空，未发送）');
      }
      const send = page.getByTestId(LOC.send);
      if (await send.isDisabled()) {
        await clearDraft(page).catch(() => {});
        throw new DriverError('SEND_DISABLED', 'follow-up 草稿就绪但发送禁用（未发送）');
      }

      // R4 第二次核验（follow-up）：草稿回读后、intent 与唯一 click 前紧邻再核；
      // 漂移（变 Flash/不同 provider/非期望 mode/不可读）清理自身草稿并零 click。
      let fuSecondCheck = null;
      if (expected) {
        try {
          fuSecondCheck = await assertExpectedConfig(page, expected, { stage: 'followup-pre-click', timeoutMs: fuReadyTimeoutMs });
        } catch (e) {
          await clearDraft(page).catch(() => {});
          throw e;
        }
      }

      // intent 先行（记录在 followUps[inputId]；期望核验证据随轮持久，不含授权 URL/凭证）
      state.followUps[inputId] = {
        prompt: { file: path.resolve(promptFile), sha256: promptSha, marker },
        phase: 'intent',
        sessionId,
        createdAt: Date.now(),
        ...(expected ? { expectedChecks: [fuFirstCheck, fuSecondCheck].filter(Boolean) } : {}),
      };
      recordEvent(state, `followup-intent:${inputId}`);
      writeStateAtomic(statePath, state);

      await send.click();
      state.followUps[inputId].phase = 'clicked';
      recordEvent(state, `followup-clicked:${inputId}`);
      writeStateAtomic(statePath, state);

      const fuNativePath = d.nativeDbPath ? d.nativeDbPath() : nativeDbPath();
      const bound = await withOpenDbAsync(fuNativePath, '原生 DB', async (native) => {
        const deadline2 = Date.now() + timeoutMs;
        for (;;) {
          const rows2 = findInputByMarker(native, marker);
          if (rows2.length === 1 && rows2[0].session_id === sessionId) return rows2[0];
          if (rows2.length > 1) {
            throw new DriverError('BINDING_AMBIGUOUS', `follow-up marker 命中 ${rows2.length} 条`);
          }
          if (Date.now() >= deadline2) return null;
          await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
        }
      });
      if (bound) {
        state.followUps[inputId].phase = 'sent-bound';
        state.followUps[inputId].binding = {
          inputId: bound.input_id,
          inputStatus: bound.input_status,
          promotedMessageId: bound.promoted_message_id || null,
          boundAt: Date.now(),
        };
        recordEvent(state, `followup-bound:${inputId}`);
        writeStateAtomic(statePath, state);
        okResult('follow-up', {
          status: 'sent-bound', inputId, sessionId,
          marker, binding: state.followUps[inputId].binding,
          note: '沿原 session 新轮次已发送并绑定；后续用 observe 查收。',
        });
      } else {
        state.followUps[inputId].phase = 'sent-unconfirmed';
        recordEvent(state, `followup-unconfirmed:${inputId}`);
        writeStateAtomic(statePath, state);
        unknownResult('follow-up', {
          status: 'unknown', inputId, sessionId, marker,
          note: 'follow-up 点击已发生但未确认接收；不自动重试，用 observe 对账。',
        });
      }
    } finally {
      await handle.close();
    }
  });
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------

async function main() {
  const argv = process.argv.slice(2);
  const command = argv[0];
  const args = parseArgs(argv.slice(1));
  try {
    switch (command) {
      case 'inspect': await cmdInspect(args); break;
      case 'submit': await cmdSubmit(args); break;
      case 'observe':
      case 'collect': args._[0] = command; await cmdObserve(args); break;
      case 'follow-up': await cmdFollowUp(args); break;
      default:
        throw new DriverError('ARG_MISSING', `未知命令: ${command || '(空)'}`,
          '用法: inspect|submit|observe|collect|follow-up（见文件头注释）');
    }
  } catch (e) {
    fail(command || 'cli', e);
  }
}

if (require.main === module) {
  main().catch(e => fail('cli', e));
}

// 测试导出（不触发浏览器/网络）
module.exports = {
  DRIVER_VERSION, STATE_SCHEMA, LOC,
  DriverError, parseArgs, assertLoopbackUrl, assertAbsPath,
  sha256File, makeMarker, normText,
  readState, writeStateAtomic, withStateLock, assertSameFingerprint, stateFingerprint,
  nativeDbPath, tasksIndexPath, openDbReadOnly, dbAll,
  findInputByMarker, getTurnInfo, getAssistantFinal, collectStatus,
  parseConcreteModel, waitForComposerConfig,
  readModelConfigIds, waitForModelConfigIds, expectedConfigDiffs,
  parseExpectedConfigArgs, resolveExpectedConfig,
  pidAlive,
  __internalsForTest: { cmdSubmit, cmdFollowUp, cmdInspect, cmdObserve, reconcileOnly, pollDbUntilBoundOrTimeout },
  __setEmitSink,
};
