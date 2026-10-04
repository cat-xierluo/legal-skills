#!/usr/bin/env node
/**
 * test-zcode-browser-config-adversarial.cjs — 浏览器配置门（R4 精确核验）独立对抗性验收 harness
 *
 * 任务：TASK-2026-10-04-ZGUI-CONFIG-ADVERSARIAL（冻结 base 4d3380b2）
 *
 * 与 test-zcode-browser-driver.cjs（原 42 契约测试）的关系：完全独立、互不导入、互不修改；
 * 本 harness 只读生产 zcode-browser-driver.cjs，面向"对抗性故障验收"：
 *   - 恶意/异常页面：DOM 配置元素重复/缺失/空属性；显示名与机器 ID 背离（label 陷阱）；
 *     草稿录入后、点击发送前配置漂移/消失（TOCTOU）
 *   - 参数门：--expected-provider/--expected-model/--expected-mode 三参数齐备且非空，
 *     部分提供/无值/空值必须在任何副作用前拒绝，不得静默降级为观察模式
 *   - state 侧：期望继承（严格性保持）、显式期望漂移冲突、既有任务事后追认拒绝
 *   - 重投门：sent-unconfirmed(unknown) / sent-bound 重复 submit 只对账、零新 click
 *   - 争用门：state 排他锁，多进程/并发争用 fail-closed 不抢占
 *   - 真实 CLI 子进程：独立消费者验证真实退出码 / 状态文件不变性 / 零残留，
 *     不只镜像纯函数断言（CLI 用例全部命中 fetchServerInfo/openPage/Playwright 加载之前的
 *     fail-closed 路径，因此不启动真实浏览器/服务/模型，不读取真实凭证）
 *   - 负控（--negative-control）：在私有 tmp 的冻结 driver 副本上注入安全相关弱化
 *     （移除发送前二次核验 / 移除唯一性门 / 移除三参数齐备门），
 *     证明本套测试对具体 fault 有杀伤力；生产 driver 全程 SHA256 前后校验不变。
 *
 * 模式：
 *   node test-zcode-browser-config-adversarial.cjs                     # 默认：对抗矩阵 vs 生产 driver
 *   node test-zcode-browser-config-adversarial.cjs --negative-control  # 负控：变异副本必须被击杀
 *   node test-zcode-browser-config-adversarial.cjs --list              # 列出测试注册表
 *   可选：--report <path>（JSON 摘要） --mutant-dir <dir> --tmp-root <dir>
 *
 * 退出码：0=通过；1=失败/harness 错误；2=参数错误；4=负控存在存活变异体（灵敏度不足）。
 * 边界声明：本 harness 不验证真实模型 E2E、不验证长期稳定性（见 references/
 * zcode-browser-config-adversarial.md 的 NOT_VERIFIED 清单）。
 */
'use strict';

const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');
const crypto = require('crypto');
const { DatabaseSync } = require('node:sqlite');

const DRIVER_PATH = path.join(__dirname, 'zcode-browser-driver.cjs');
const TASK_ID = 'TASK-2026-10-04-ZGUI-CONFIG-ADVERSARIAL';

// 期望机器 ID（与 2026-10-03 官方 3.14.4 DOM 实见一致，仅作测试常量）
const GOOD = Object.freeze({
  provider: 'account:bigmodel-individual-coding-plan',
  model: 'GLM-5.3',
  mode: 'yolo',
});
const LOOPBACK = 'http://127.0.0.1:18490/';

// ---------------------------------------------------------------------------
// harness 参数
// ---------------------------------------------------------------------------

function parseHarnessArgs(argv) {
  const out = { mode: 'default', report: null, mutantDir: null, tmpRoot: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--negative-control') out.mode = 'negative';
    else if (a === '--list') out.mode = 'list';
    else if (a === '--report') out.report = argv[++i];
    else if (a === '--mutant-dir') out.mutantDir = argv[++i];
    else if (a === '--tmp-root') out.tmpRoot = argv[++i];
    else { console.error(`未知参数: ${a}`); process.exit(2); }
  }
  return out;
}

function sha256File(p) {
  return crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
}

// ---------------------------------------------------------------------------
// Fake Playwright page（自包含；不导入原 42 测试文件）
// ---------------------------------------------------------------------------

class FakeLocator {
  constructor(page, key, opts = {}) {
    this.page = page; this.key = key; this.opts = opts;
  }
  async count() {
    if (this.opts.count !== undefined) return this.opts.count;
    if (this.opts.exists || this.opts.text !== undefined) return 1;
    return 0;
  }
  first() { return this; }
  nth() { return this; }
  async innerText() {
    return typeof this.opts.text === 'function' ? this.opts.text() : (this.opts.text || '');
  }
  async isDisabled() { return this.opts.disabled ? this.opts.disabled() : false; }
  async click() {
    if (this.page) this.page.events.push(`click:${this.key}`);
    if (this.key === 'v4-composer-send') return this.page._onSendClick();
    if (this.opts.onClick) return this.opts.onClick();
  }
  async waitFor() { if (this.opts.missing) throw new Error('waiting failed'); }
  async evaluate(fn) { return fn(this.opts.el || { parentElement: null, getAttribute: () => 'open' }); }
  async scrollIntoViewIfNeeded() {}
}

class FakePage {
  constructor(cfg = {}) {
    this.cfg = cfg;
    this.draft = '';
    this.rows = [];
    this.sendClicks = 0;
    this.events = [];
    this.keyboard = {
      insertText: async (t) => { this.draft += t; },
      press: async (k) => {
        if (k === 'Meta+a') this._selectAll = true;
        if (k === 'Backspace' && this._selectAll) { this.draft = ''; this._selectAll = false; }
      },
    };
  }
  async goto() {}
  async title() { return 'ZCode - Web (fake)'; }
  async $$eval() { return []; }
  async waitForTimeout(ms) { await new Promise(r => setTimeout(r, Math.min(ms, 5))); }
  getByTestId(id, drv) {
    const D = drv || require(DRIVER_PATH);
    if (id === D.LOC.composerInput) {
      return new FakeLocator(this, id, { exists: true, text: () => this.draft, onClick: async () => {} });
    }
    if (id === D.LOC.send) {
      return new FakeLocator(this, id, { exists: true, disabled: () => this.draft.trim() === '' });
    }
    if (id === D.LOC.workspaceTrigger) return new FakeLocator(this, id, { text: this.cfg.wsLabel || '选择项目' });
    if (id === D.LOC.modeTrigger) {
      const ml = this.cfg.modeLabel !== undefined ? this.cfg.modeLabel : '变更前确认';
      return new FakeLocator(this, id, { text: ml });
    }
    if (id === D.LOC.modelTrigger) {
      const ml = this.cfg.modelLabel !== undefined
        ? (typeof this.cfg.modelLabel === 'function' ? this.cfg.modelLabel() : this.cfg.modelLabel)
        : 'Fake/Model-X';
      return new FakeLocator(this, id, { text: ml });
    }
    if (id === D.LOC.taskNewButton) return new FakeLocator(this, id, { exists: true, onClick: async () => {} });
    if (id === D.LOC.row) {
      return new FakeLocator(this, id, { count: this.rows.length, text: () => this.rows.map(r => r.text).join('\n') });
    }
    return new FakeLocator(this, id, { count: 0 });
  }
  getByRole(role) {
    if (role === 'textbox') return new FakeLocator(this, 'role:textbox', { count: 1 });
    return new FakeLocator(this, 'role:' + role, { count: 0 });
  }
  locator(sel, drv) {
    const D = drv || require(DRIVER_PATH);
    // v4-model-config 机器 ID 模拟：
    // cfg.modelConfig：undefined=元素缺失；对象=唯一元素；数组=重复元素；函数(page)=>上述=动态漂移。
    if (sel === `[data-testid="${D.LOC.modelConfig}"]`) {
      const raw = typeof this.cfg.modelConfig === 'function' ? this.cfg.modelConfig(this) : this.cfg.modelConfig;
      if (raw === undefined || raw === null) return new FakeLocator(this, sel, { count: 0 });
      if (Array.isArray(raw)) return new FakeLocator(this, sel, { count: raw.length, el: raw[0] });
      return new FakeLocator(this, sel, { count: 1, el: raw });
    }
    return new FakeLocator(this, sel, { count: 0 });
  }
  async _onSendClick() {
    this.sendClicks++;
    const typed = this.draft;
    this.draft = '';
    if (this.cfg.onSendClick) await this.cfg.onSendClick(typed, this);
  }
}

// 构造 v4-model-config 元素（getAttribute 协议）；over 中 undefined 回退 GOOD，null/'' 表示空。
function elWith(over = {}) {
  return {
    getAttribute: (k) => {
      const key = { 'data-provider': 'provider', 'data-model': 'model', 'data-mode': 'mode' }[k];
      if (!key) return null;
      return over[key] !== undefined ? over[key] : GOOD[key];
    },
  };
}

function makeDeps(fakePage, fixtureDbPath, workspace, onOpenPage) {
  return {
    openPageCalls: 0,
    async openPage() {
      this.openPageCalls++;
      if (onOpenPage) onOpenPage();
      return { page: fakePage, close: async () => { fakePage.closed = true; } };
    },
    async fetchServerInfo() {
      return { serverId: 'fake', version: '0.0.0-test', authRequired: false, workspaces: [{ path: workspace, label: 'default' }] };
    },
    nativeDbPath: () => fixtureDbPath,
  };
}

// ---------------------------------------------------------------------------
// fixture SQLite（最小 schema，与生产查询一致；同原 42 测试协议但自包含）
// ---------------------------------------------------------------------------

function buildFixtureDb(p) {
  const db = new DatabaseSync(p);
  db.exec(`
    CREATE TABLE session (
      id text primary key, project_id text not null default 'p', workspace_id text,
      parent_id text, slug text not null default 's', directory text not null, path text,
      title text not null default '', version text not null default 'v', share_url text,
      summary_additions integer, summary_deletions integer, summary_files integer,
      summary_diffs text, revert text, permission text,
      time_created integer not null default 0, time_updated integer not null default 0,
      time_compacting integer, time_archived integer,
      task_type text not null default 'interactive',
      title_source text not null default 'first_input',
      title_message_id text, time_title_updated integer, trace_id text);
    CREATE TABLE session_input (
      id text primary key, session_id text not null, kind text not null default 'sendText',
      delivery text not null default 'startNow', payload text not null,
      admitted_sequence integer not null default 0, promoted_sequence integer,
      promoted_message_id text,
      status text not null check(status in ('admitted','promoted','cancelled','discarded','failed')),
      status_reason text, time_created integer not null default 0, time_updated integer not null default 0);
    CREATE TABLE message (
      id text primary key, session_id text not null, time_created integer not null default 0,
      time_updated integer not null default 0, data text not null, sequence integer);
    CREATE TABLE part (
      id text primary key, message_id text not null, session_id text not null,
      time_created integer not null default 0, time_updated integer not null default 0,
      data text not null, sequence integer);
    CREATE TABLE turn_usage (
      session_id text not null, turn_id text not null, trace_id text,
      user_message_id text, status text not null,
      started_at integer not null default 0, first_model_start_at integer,
      first_token_at integer, completed_at integer, duration_ms integer,
      time_to_first_token_ms integer, model_request_count integer not null default 0,
      model_retry_count integer not null default 0, tool_call_count integer not null default 0);
  `);
  return db;
}

function seedReceivedTurn(db, { sessionId, directory, inputId, marker, userMsgId, finalText = '对抗测试最终交付正文。' }) {
  db.prepare('INSERT INTO session (id, directory, title) VALUES (?,?,?)').run(sessionId, directory, 'T');
  db.prepare('INSERT INTO session_input (id, session_id, payload, status, promoted_message_id) VALUES (?,?,?,?,?)')
    .run(inputId, sessionId, JSON.stringify({ text: `任务内容 ${marker}` }), 'promoted', userMsgId);
  db.prepare('INSERT INTO message (id, session_id, data, sequence) VALUES (?,?,?,?)')
    .run(userMsgId, sessionId, JSON.stringify({ role: 'user', parentID: null, time: { created: 1 } }), 0);
  db.prepare('INSERT INTO turn_usage (session_id, turn_id, user_message_id, status, started_at, completed_at) VALUES (?,?,?,?,?,?)')
    .run(sessionId, 'turn_1', userMsgId, 'completed', 1, 2);
  db.prepare('INSERT INTO message (id, session_id, data, sequence) VALUES (?,?,?,?)')
    .run(`${userMsgId}-a1`, sessionId, JSON.stringify({ role: 'assistant', parentID: userMsgId, time: { created: 1, completed: 123 } }), 1);
  db.prepare('INSERT INTO part (id, message_id, session_id, data, sequence) VALUES (?,?,?,?,?)')
    .run(`${userMsgId}-a1-p0`, `${userMsgId}-a1`, sessionId, JSON.stringify({ type: 'text', text: finalText }), 0);
}

// ---------------------------------------------------------------------------
// 通用工具
// ---------------------------------------------------------------------------

function tmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'zgui-config-adversarial-'));
}

class Ctx {
  constructor(root) { this.root = root; }
  dir(id) {
    const d = path.join(this.root, `t-${id}-${crypto.randomBytes(3).toString('hex')}`);
    fs.mkdirSync(d, { recursive: true });
    return d;
  }
}

function writePrompt(dir, name, text) {
  const p = path.join(dir, name);
  fs.writeFileSync(p, text);
  return p;
}

function expectedToArgs(exp) {
  return { 'expected-provider': exp.provider, 'expected-model': exp.model, 'expected-mode': exp.mode };
}

function submitArgs(dir, opts = {}, expected = null) {
  const base = {
    url: LOOPBACK,
    workspace: opts.workspace || '/tmp/zgui-ws-adv',
    'task-id': opts.taskId || 'TASK-ADV',
    'prompt-file': opts.promptFile,
    state: path.join(dir, 'state.json'),
    'timeout-ms': opts.timeoutMs || 1200,
    'ready-timeout-ms': opts.readyTimeoutMs || 600,
  };
  return expected ? Object.assign(base, expectedToArgs(expected)) : base;
}

function cliFlagArgs(a) {
  // in-process args 对象 → CLI --flag 形式
  const out = [];
  for (const [k, v] of Object.entries(a)) {
    if (k === '_') continue;
    out.push(`--${k}`);
    if (v !== true) out.push(String(v));
  }
  return out;
}

// 捕获某个 driver 副本的 emit（每副本模块级 sink 独立）
async function captureEmit(drv, fn) {
  let captured = null;
  drv.__setEmitSink((obj, exitCode) => { captured = { json: obj, exitCode }; });
  try {
    await fn();
  } finally {
    drv.__setEmitSink(null);
  }
  if (!captured) throw new Error('期望 driver 至少一次 emit 输出（未发生即失败）');
  return captured;
}

async function withEmitRecord(drv, fn) {
  const events = [];
  drv.__setEmitSink((obj, exitCode) => { events.push({ json: obj, exitCode }); });
  try {
    const result = await fn();
    return { events, result };
  } finally {
    drv.__setEmitSink(null);
  }
}

async function waitFor(cond, timeoutMs, label) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (cond()) return;
    await new Promise(r => setTimeout(r, 5));
  }
  throw new Error(`waitFor 超时: ${label}`);
}

function assertNoResidue(dir, statePath, label) {
  if (fs.existsSync(statePath)) throw new Error(`${label}: state 文件不应存在`);
  if (fs.existsSync(`${statePath}.lock`)) throw new Error(`${label}: 锁目录残留`);
  const stray = fs.readdirSync(dir).filter(f => f.includes('.tmp-'));
  if (stray.length) throw new Error(`${label}: 原子写临时文件残留 ${stray.join(',')}`);
}

// 真实 CLI 子进程（独立消费者）：返回 {status, json, stderr}
function runCli(driverPath, flagArgs, opts = {}) {
  const r = spawnSync(process.execPath, [driverPath, ...flagArgs], {
    encoding: 'utf8', timeout: opts.timeoutMs || 30000, cwd: path.dirname(driverPath),
  });
  let json = null;
  try { json = r.stdout ? JSON.parse(r.stdout) : null; } catch { json = null; }
  return { status: r.status, json, stderrTail: (r.stderr || '').split('\n').slice(-3).join(' ').slice(0, 160) };
}

// ---------------------------------------------------------------------------
// 测试注册表。run(drv, ctx, driverPath)：默认模式必须通过（不抛）；
// 负控模式：targets 命中的变异体下必须失败（抛）才算"击杀"。
// ---------------------------------------------------------------------------

const TESTS = [
  {
    id: 'ADV-01', targets: ['W3'], cli: false,
    title: '显式 expected 三参数门：无值/部分/空值拒绝，齐备返回裁剪三元组，缺省为 null',
    async run(drv) {
      const mustThrow = (args, why) => {
        let err = null;
        try { drv.parseExpectedConfigArgs(args, 'submit'); } catch (e) { err = e; }
        if (!err) throw new Error(`ADV-01: ${why} 应抛 EXPECTED_CONFIG_INVALID`);
        if (!(err instanceof drv.DriverError) || err.code !== 'EXPECTED_CONFIG_INVALID') {
          throw new Error(`ADV-01: ${why} 错误码不符: ${err.code}`);
        }
      };
      mustThrow({ 'expected-provider': true, 'expected-model': 'm1', 'expected-mode': 'yolo' }, '无值 flag');
      mustThrow({ 'expected-provider': 'p1' }, '仅提供 1/3');
      mustThrow({ 'expected-provider': 'p1', 'expected-model': 'm1' }, '部分提供 2/3');
      mustThrow({ 'expected-provider': '  ', 'expected-model': 'm1', 'expected-mode': 'yolo' }, '空白值');
      const ok3 = drv.parseExpectedConfigArgs(
        { 'expected-provider': 'p1', 'expected-model': '  m1  ', 'expected-mode': 'yolo' }, 'submit');
      if (!ok3 || ok3.model !== 'm1' || ok3.provider !== 'p1' || ok3.mode !== 'yolo') {
        throw new Error('ADV-01: 三参数齐备应返回裁剪后的三元组');
      }
      if (drv.parseExpectedConfigArgs({}, 'submit') !== null) {
        throw new Error('ADV-01: 全部不提供应返回 null（观察兼容模式），不得伪称已核验');
      }
    },
  },
  {
    id: 'ADV-02', targets: ['W2'], cli: false,
    title: 'DOM 配置元素重复（且两个元素机器 ID 冲突）→ UNREADABLE(DUPLICATE) 零 click 零 state',
    async run(drv, ctx) {
      const dir = ctx.dir('ADV-02');
      const page = new FakePage({ modelConfig: [elWith(), elWith({ model: 'GLM-4.6-Air' })] });
      const deps = makeDeps(page, path.join(dir, 'native.sqlite'), '/tmp/zgui-ws-adv');
      const args = submitArgs(dir, { promptFile: writePrompt(dir, 'p.txt', '任务 ADV-02。') }, GOOD);
      let err = null;
      try { await drv.__internalsForTest.cmdSubmit(args, deps); } catch (e) { err = e; }
      if (!err || err.code !== 'EXPECTED_CONFIG_UNREADABLE' || !/DUPLICATE/.test(err.message)) {
        throw new Error(`ADV-02: 期望 UNREADABLE(DUPLICATE)，得到 ${err && err.code}: ${err && err.message}`);
      }
      if (page.sendClicks !== 0) throw new Error(`ADV-02: 拒绝路径产生 ${page.sendClicks} 次发送点击`);
      assertNoResidue(dir, args.state, 'ADV-02');
    },
  },
  {
    id: 'ADV-03', targets: [], cli: false,
    title: 'DOM 配置元素缺失 → UNREADABLE(MISSING) 零 click 零 state',
    async run(drv, ctx) {
      const dir = ctx.dir('ADV-03');
      const page = new FakePage({ modelConfig: undefined });
      const deps = makeDeps(page, path.join(dir, 'native.sqlite'), '/tmp/zgui-ws-adv');
      const args = submitArgs(dir, { promptFile: writePrompt(dir, 'p.txt', '任务 ADV-03。') }, GOOD);
      let err = null;
      try { await drv.__internalsForTest.cmdSubmit(args, deps); } catch (e) { err = e; }
      if (!err || err.code !== 'EXPECTED_CONFIG_UNREADABLE' || !/MISSING/.test(err.message)) {
        throw new Error(`ADV-03: 期望 UNREADABLE(MISSING)，得到 ${err && err.code}`);
      }
      if (page.sendClicks !== 0) throw new Error('ADV-03: 拒绝路径产生发送点击');
      assertNoResidue(dir, args.state, 'ADV-03');
    },
  },
  {
    id: 'ADV-04', targets: [], cli: false,
    title: '机器 ID 属性空值/缺失 → UNREADABLE(EMPTY_ATTR) 零 click 零 state',
    async run(drv, ctx) {
      for (const [name, el] of [['空字符串', elWith({ model: '' })], ['属性缺失(null)', elWith({ mode: null })]]) {
        const dir = ctx.dir('ADV-04');
        const page = new FakePage({ modelConfig: el });
        const deps = makeDeps(page, path.join(dir, 'native.sqlite'), '/tmp/zgui-ws-adv');
        const args = submitArgs(dir, { promptFile: writePrompt(dir, 'p.txt', '任务 ADV-04。') }, GOOD);
        let err = null;
        try { await drv.__internalsForTest.cmdSubmit(args, deps); } catch (e) { err = e; }
        if (!err || err.code !== 'EXPECTED_CONFIG_UNREADABLE' || !/EMPTY_ATTR/.test(err.message)) {
          throw new Error(`ADV-04(${name}): 期望 UNREADABLE(EMPTY_ATTR)，得到 ${err && err.code}`);
        }
        if (page.sendClicks !== 0) throw new Error(`ADV-04(${name}): 拒绝路径产生发送点击`);
        assertNoResidue(dir, args.state, `ADV-04(${name})`);
      }
    },
  },
  {
    id: 'ADV-05', targets: [], cli: false,
    title: '机器 ID 相似显示名冲突：显示 label 与期望一致但机器 ID 背离/大小写漂移/mode 漂移 → MISMATCH 零 click',
    async run(drv, ctx) {
      const cases = [
        { name: 'label 陷阱（显示名=GLM-5.3，data-model=GLM-4.6-Air）', el: elWith({ model: 'GLM-4.6-Air' }), modelLabel: 'GLM-5.3', exp: GOOD, want: /model:/ },
        { name: '大小写敏感（期望 glm-5.3 ≠ 实际 GLM-5.3）', el: elWith(), modelLabel: 'Fake/Model-X', exp: { ...GOOD, model: 'glm-5.3' }, want: /model:/ },
        { name: 'mode 漂移（期望 yolo ≠ 实际 plan）', el: elWith({ mode: 'plan' }), modelLabel: 'Fake/Model-X', exp: GOOD, want: /mode:/ },
      ];
      for (const c of cases) {
        const dir = ctx.dir('ADV-05');
        const page = new FakePage({ modelConfig: c.el, modelLabel: c.modelLabel });
        const deps = makeDeps(page, path.join(dir, 'native.sqlite'), '/tmp/zgui-ws-adv');
        const args = submitArgs(dir, { promptFile: writePrompt(dir, 'p.txt', '任务 ADV-05。') }, c.exp);
        let err = null;
        try { await drv.__internalsForTest.cmdSubmit(args, deps); } catch (e) { err = e; }
        if (!err || err.code !== 'EXPECTED_CONFIG_MISMATCH' || !c.want.test(err.message)) {
          throw new Error(`ADV-05(${c.name}): 期望 MISMATCH(${c.want})，得到 ${err && err.code}: ${err && err.message}`);
        }
        if (page.sendClicks !== 0) throw new Error(`ADV-05(${c.name}): 拒绝路径产生发送点击`);
        assertNoResidue(dir, args.state, `ADV-05(${c.name})`);
      }
    },
  },
  {
    id: 'ADV-06', targets: ['W1'], cli: false,
    title: '草稿后发送前配置漂移/消失（TOCTOU）→ 第二次核验拒绝、草稿清理、零 click 零 intent',
    async run(drv, ctx) {
      const sub = async (name, driftTo) => {
        const dir = ctx.dir('ADV-06');
        // 机器 ID 随草稿内容动态翻转：pre-draft 检查时草稿为空=GOOD；typeDraft 后含 marker=漂移
        const page = new FakePage({
          modelConfig: (pg) => (pg.draft.includes('[ZGUI-M-') ? driftTo : elWith()),
        });
        const deps = makeDeps(page, path.join(dir, 'native.sqlite'), '/tmp/zgui-ws-adv');
        const args = submitArgs(dir, { promptFile: writePrompt(dir, 'p.txt', '任务 ADV-06。') }, GOOD);
        let err = null;
        try { await drv.__internalsForTest.cmdSubmit(args, deps); } catch (e) { err = e; }
        if (!err || err.code !== 'EXPECTED_CONFIG_MISMATCH') {
          throw new Error(`ADV-06(${name}): 期望第二次核验 MISMATCH，得到 ${err && err.code}: ${err && err.message}`);
        }
        if (page.sendClicks !== 0) throw new Error(`ADV-06(${name}): 漂移后仍发生 ${page.sendClicks} 次发送点击`);
        if (page.draft !== '') throw new Error(`ADV-06(${name}): 拒绝后应清理本 driver 键入的草稿，实际残留`);
        assertNoResidue(dir, args.state, `ADV-06(${name})`); // 不写 intent → 不可盲重投
      };
      await sub('漂移为 Flash', elWith({ model: 'GLM-5.3-Flash' }));
      await sub('漂移为其他 provider', elWith({ provider: 'account:other-plan' }));
    },
  },
  {
    id: 'ADV-07', targets: [], cli: false,
    title: 'state 期望继承/冲突：成功 submit 记录期望与两次核验；重复 submit 继承只对账；显式漂移与事后追认拒绝',
    async run(drv, ctx) {
      const dir = ctx.dir('ADV-07');
      const ws = '/tmp/zgui-ws-a7';
      const dbPath = path.join(dir, 'native.sqlite');
      const db = buildFixtureDb(dbPath);
      const page = new FakePage({
        modelConfig: elWith(),
        onSendClick: async (typed, pg) => {
          const m = /\[ZGUI-M-[A-Za-z0-9_-]+-[0-9a-f]+\]/.exec(typed);
          const marker = m ? m[0].slice(1, -1) : 'ZGUI-M-unknown';
          seedReceivedTurn(db, { sessionId: 's_a7', directory: ws, inputId: 'i_a7', marker, userMsgId: 'u_a7' });
          pg.rows.push({ text: typed });
        },
      });
      const deps = makeDeps(page, dbPath, ws);
      const args = submitArgs(dir, { promptFile: writePrompt(dir, 'p.txt', '任务 ADV-07。'), workspace: ws }, GOOD);

      // (a) 首次成功：expectedConfig 持久化 + 两次核验证据
      const cap1 = await captureEmit(drv, () => drv.__internalsForTest.cmdSubmit(args, deps));
      if (cap1.exitCode !== 0 || cap1.json.status !== 'sent-bound') {
        throw new Error(`ADV-07(a): 期望 sent-bound/exit0，得到 ${cap1.json.status}/${cap1.exitCode}`);
      }
      const st = JSON.parse(fs.readFileSync(args.state, 'utf8'));
      if (!st.expectedConfig || st.expectedConfig.model !== GOOD.model || st.expectedConfig.provider !== GOOD.provider || st.expectedConfig.mode !== GOOD.mode) {
        throw new Error('ADV-07(a): state.expectedConfig 未按机器 ID 记录');
      }
      const stages = (st.page.expectedChecks || []).map(c => c.stage);
      if (stages.join(',') !== 'submit-pre-draft,submit-pre-click') {
        throw new Error(`ADV-07(a): 期望两次核验证据，实际 ${stages.join(',')}`);
      }
      if (page.sendClicks !== 1 || deps.openPageCalls !== 1) throw new Error('ADV-07(a): 唯一 click/唯一 openPage 不成立');

      // (b) 重复 submit（同期望显式）→ 只对账 reconciled，零新 click / 零新 openPage
      const cap2 = await captureEmit(drv, () => drv.__internalsForTest.cmdSubmit(args, deps));
      if (cap2.exitCode !== 0 || cap2.json.status !== 'reconciled') {
        throw new Error(`ADV-07(b): 期望 reconciled/exit0，得到 ${cap2.json.status}/${cap2.exitCode}`);
      }
      if (page.sendClicks !== 1 || deps.openPageCalls !== 1) throw new Error('ADV-07(b): 重复 submit 产生了新副作用');

      // (c) 显式期望漂移（model 不同）→ EXPECTED_CONFIG_CONFLICT（打开浏览器前）
      let err = null;
      try { await drv.__internalsForTest.cmdSubmit({ ...args, 'expected-model': 'glm-4.6-air' }, deps); } catch (e) { err = e; }
      if (!err || err.code !== 'EXPECTED_CONFIG_CONFLICT') {
        throw new Error(`ADV-07(c): 期望 EXPECTED_CONFIG_CONFLICT，得到 ${err && err.code}`);
      }
      if (page.sendClicks !== 1 || deps.openPageCalls !== 1) throw new Error('ADV-07(c): 冲突路径产生了新副作用');

      // (d) 事后追认：既有任务 state 无期望记录 → 追加显式期望必须拒绝（不能静默升级为已核验）
      const dir2 = ctx.dir('ADV-07d');
      const prompt2 = writePrompt(dir2, 'p.txt', '任务 ADV-07d。');
      const state2 = path.join(dir2, 'state.json');
      const sha2 = crypto.createHash('sha256').update(fs.readFileSync(prompt2)).digest('hex');
      fs.writeFileSync(state2, JSON.stringify({
        schema: drv.STATE_SCHEMA, driverVersion: drv.DRIVER_VERSION,
        url: LOOPBACK, workspace: '/tmp/zgui-ws-adv', taskId: 'TASK-ADV', phase: 'sent-bound',
        prompt: { file: prompt2, sha256: sha2, bytes: 99, marker: 'ZGUI-M-TASK-ADV-abc123' },
      }));
      const deps2 = makeDeps(new FakePage({ modelConfig: elWith() }), path.join(dir2, 'native.sqlite'), '/tmp/zgui-ws-adv');
      let err2 = null;
      try {
        await drv.__internalsForTest.cmdSubmit(submitArgs(dir2, { promptFile: prompt2 }, GOOD), deps2);
      } catch (e) { err2 = e; }
      if (!err2 || err2.code !== 'EXPECTED_CONFIG_CONFLICT') {
        throw new Error(`ADV-07(d): 事后追认应 EXPECTED_CONFIG_CONFLICT，得到 ${err2 && err2.code}`);
      }
      if (deps2.openPageCalls !== 0) throw new Error('ADV-07(d): 冲突应在打开浏览器前裁决');
      if (fs.existsSync(`${state2}.lock`)) throw new Error('ADV-07(d): 拒绝路径不得残留锁目录');
      const st2 = JSON.parse(fs.readFileSync(state2, 'utf8'));
      if (st2.expectedConfig) throw new Error('ADV-07(d): 拒绝路径不得写入 expectedConfig');
    },
  },
  {
    id: 'ADV-08', targets: [], cli: false,
    title: 'unknown/duplicate 零重投：unconfirmed→重复 submit 保持 unknown 不点击；DB 补齐后仅对账',
    async run(drv, ctx) {
      const dir = ctx.dir('ADV-08');
      const ws = '/tmp/zgui-ws-a8';
      const dbPath = path.join(dir, 'native.sqlite');
      const db = buildFixtureDb(dbPath);
      const page = new FakePage({ modelConfig: elWith() }); // 不 seed DB → 发送后无法绑定
      const deps = makeDeps(page, dbPath, ws);
      const args = submitArgs(dir, { promptFile: writePrompt(dir, 'p.txt', '任务 ADV-08。'), workspace: ws }, GOOD);

      // (a) 点击后 DB 无记录 → unknown / exit 2 / sent-unconfirmed
      const cap1 = await captureEmit(drv, () => drv.__internalsForTest.cmdSubmit(args, deps));
      if (cap1.exitCode !== 2 || cap1.json.status !== 'unknown') {
        throw new Error(`ADV-08(a): 期望 unknown/exit2，得到 ${cap1.json.status}/${cap1.exitCode}`);
      }
      if (page.sendClicks !== 1) throw new Error('ADV-08(a): 应恰好一次发送点击');
      let st = JSON.parse(fs.readFileSync(args.state, 'utf8'));
      if (st.phase !== 'sent-unconfirmed') throw new Error(`ADV-08(a): phase=${st.phase}`);

      // (b) unknown 后重复 submit → 仍 unknown、只对账、零新 click / 零新 openPage
      const cap2 = await captureEmit(drv, () => drv.__internalsForTest.cmdSubmit(args, deps));
      if (cap2.exitCode !== 2 || cap2.json.status !== 'unknown') {
        throw new Error(`ADV-08(b): 期望 unknown/exit2（零重投），得到 ${cap2.json.status}/${cap2.exitCode}`);
      }
      if (page.sendClicks !== 1 || deps.openPageCalls !== 1) throw new Error('ADV-08(b): unknown 路径产生了重投副作用');

      // (c) DB 侧补齐（模拟延迟落库）→ 重复 submit 仅对账 reconciled，仍零新 click
      st = JSON.parse(fs.readFileSync(args.state, 'utf8'));
      seedReceivedTurn(db, { sessionId: 's_a8', directory: ws, inputId: 'i_a8', marker: st.prompt.marker, userMsgId: 'u_a8', finalText: 'ADV-08 补齐后最终正文。' });
      const cap3 = await captureEmit(drv, () => drv.__internalsForTest.cmdSubmit(args, deps));
      if (cap3.exitCode !== 0 || cap3.json.status !== 'reconciled') {
        throw new Error(`ADV-08(c): 期望 reconciled/exit0，得到 ${cap3.json.status}/${cap3.exitCode}`);
      }
      if (page.sendClicks !== 1 || deps.openPageCalls !== 1) throw new Error('ADV-08(c): 对账路径产生了新点击');
    },
  },
  {
    id: 'ADV-09', targets: [], cli: false,
    title: '多进程/并发争用：持锁期间第二提交者 LOCK_HELD 零副作用；锁随持有者释放；胜者唯一 click',
    async run(drv, ctx) {
      const dir = ctx.dir('ADV-09');
      const ws = '/tmp/zgui-ws-a9';
      const dbPath = path.join(dir, 'native.sqlite');
      const db = buildFixtureDb(dbPath);
      let release;
      const gate = new Promise(r => { release = r; });
      const page1 = new FakePage({
        modelConfig: elWith(),
        onSendClick: async (typed, pg) => {
          const m = /\[ZGUI-M-[A-Za-z0-9_-]+-[0-9a-f]+\]/.exec(typed);
          seedReceivedTurn(db, { sessionId: 's_a9', directory: ws, inputId: 'i_a9', marker: m ? m[0].slice(1, -1) : 'ZGUI-M-x', userMsgId: 'u_a9' });
          pg.rows.push({ text: typed });
          await gate; // 胜者在点击后持锁等待，制造确定性争用窗口
        },
      });
      const deps1 = makeDeps(page1, dbPath, ws);
      const args = submitArgs(dir, { promptFile: writePrompt(dir, 'p.txt', '任务 ADV-09。'), workspace: ws }, GOOD);

      const winner = withEmitRecord(drv, () => drv.__internalsForTest.cmdSubmit(args, deps1));
      await waitFor(() => fs.existsSync(`${args.state}.lock`), 3000, '胜者持锁');

      // 争用者：同 state 并发提交 → LOCK_HELD，且不得打开页面/点击
      const deps2 = makeDeps(new FakePage({ modelConfig: elWith() }), path.join(dir, 'native2.sqlite'), ws);
      let err = null;
      try { await drv.__internalsForTest.cmdSubmit({ ...args }, deps2); } catch (e) { err = e; }
      if (!err || err.code !== 'LOCK_HELD') {
        throw new Error(`ADV-09: 争用者期望 LOCK_HELD，得到 ${err && err.code}: ${err && err.message}`);
      }
      if (deps2.openPageCalls !== 0) throw new Error('ADV-09: 争用者在锁拒绝后仍打开了页面');

      release();
      const w = await winner;
      if (w.events.length !== 1 || w.events[0].exitCode !== 0 || w.events[0].json.status !== 'sent-bound') {
        throw new Error(`ADV-09: 胜者期望 sent-bound/exit0，events=${JSON.stringify(w.events.map(e => e.json.status))}`);
      }
      if (page1.sendClicks !== 1) throw new Error('ADV-09: 全程应恰好一次发送点击');
      await waitFor(() => !fs.existsSync(`${args.state}.lock`), 3000, '锁释放');
      const st = JSON.parse(fs.readFileSync(args.state, 'utf8'));
      if (st.phase !== 'sent-bound') throw new Error(`ADV-09: 最终 phase=${st.phase}`);
    },
  },
  {
    id: 'ADV-10', targets: [], cli: false,
    title: '零 click 拒绝（副作用前）：部分期望参数在 openPage/锁/state 之前拒绝',
    async run(drv, ctx) {
      const dir = ctx.dir('ADV-10');
      const page = new FakePage({ modelConfig: elWith() });
      const deps = makeDeps(page, path.join(dir, 'native.sqlite'), '/tmp/zgui-ws-adv');
      const args = submitArgs(dir, { promptFile: writePrompt(dir, 'p.txt', '任务 ADV-10。') });
      const partial = { ...args, 'expected-provider': GOOD.provider, 'expected-model': GOOD.model }; // 2/3
      let err = null;
      try { await drv.__internalsForTest.cmdSubmit(partial, deps); } catch (e) { err = e; }
      if (!err || err.code !== 'EXPECTED_CONFIG_INVALID') {
        throw new Error(`ADV-10: 期望 EXPECTED_CONFIG_INVALID，得到 ${err && err.code}`);
      }
      if (deps.openPageCalls !== 0) throw new Error('ADV-10: 参数门应在打开页面前拒绝');
      if (page.sendClicks !== 0) throw new Error('ADV-10: 参数门路径产生点击');
      assertNoResidue(dir, args.state, 'ADV-10');
    },
  },
  // ---- 真实 CLI 子进程（独立消费者）：真实退出码 + 状态文件不变性 ----
  {
    id: 'ADV-C1', targets: ['W3'], cli: true,
    title: '[CLI] 部分提供/无值期望参数 → 真实退出码 1 + EXPECTED_CONFIG_INVALID + 零副作用残留',
    async run(drv, ctx, driverPath) {
      const sub = async (name, flagArgs) => {
        const dir = ctx.dir('ADV-C1');
        const statePath = path.join(dir, 'state.json');
        const base = {
          '--url': LOOPBACK, '--workspace': '/tmp/zgui-ws-adv', '--task-id': 'TASK-ADVCLI',
          '--prompt-file': writePrompt(dir, 'p.txt', '任务 ADV-C1。'), '--state': statePath,
        };
        const flat = [];
        for (const [k, v] of Object.entries(base)) flat.push(k, v);
        const r = runCli(driverPath, ['submit', ...flat, ...flagArgs]);
        if (r.status !== 1) throw new Error(`ADV-C1(${name}): 期望退出码 1，实际 ${r.status}；stderr尾: ${r.stderrTail}`);
        if (!r.json || !r.json.error || r.json.error.code !== 'EXPECTED_CONFIG_INVALID') {
          throw new Error(`ADV-C1(${name}): 期望 error.code=EXPECTED_CONFIG_INVALID，实际 ${r.json && r.json.error && r.json.error.code}`);
        }
        assertNoResidue(dir, statePath, `ADV-C1(${name})`);
      };
      await sub('部分提供 2/3', ['--expected-provider', 'p1', '--expected-model', 'm1']);
      await sub('无值 flag', ['--expected-provider', 'p1', '--expected-model', 'm1', '--expected-mode']);
    },
  },
  {
    id: 'ADV-C2', targets: [], cli: true,
    title: '[CLI] 外部持锁下两个独立 OS 进程争用 → 双双 LOCK_HELD 退出码 1，锁与 owner 原样保留',
    async run(drv, ctx, driverPath) {
      const dir = ctx.dir('ADV-C2');
      const statePath = path.join(dir, 'state.json');
      const lockDir = `${statePath}.lock`;
      fs.mkdirSync(lockDir);
      const owner = { pid: 424242, nonce: 'foreign-owner-nonce', startedAt: Date.now(), host: 'harness' };
      fs.writeFileSync(path.join(lockDir, 'owner.json'), JSON.stringify(owner));
      const flat = ['--url', LOOPBACK, '--workspace', '/tmp/zgui-ws-adv', '--task-id', 'TASK-ADVCLI',
        '--prompt-file', writePrompt(dir, 'p.txt', '任务 ADV-C2。'), '--state', statePath];
      const results = [0, 1].map(() => runCli(driverPath, ['submit', ...flat]));
      results.forEach((r, i) => {
        if (r.status !== 1) throw new Error(`ADV-C2(进程${i + 1}): 期望退出码 1，实际 ${r.status}`);
        if (!r.json || r.json.error.code !== 'LOCK_HELD') {
          throw new Error(`ADV-C2(进程${i + 1}): 期望 LOCK_HELD，实际 ${r.json && r.json.error && r.json.error.code}`);
        }
      });
      if (!fs.existsSync(lockDir)) throw new Error('ADV-C2: 外部锁不得被删除');
      const kept = JSON.parse(fs.readFileSync(path.join(lockDir, 'owner.json'), 'utf8'));
      if (kept.nonce !== owner.nonce) throw new Error('ADV-C2: owner.json 被篡改');
      if (fs.existsSync(statePath)) throw new Error('ADV-C2: 锁拒绝路径不得创建 state');
    },
  },
  {
    id: 'ADV-C3', targets: [], cli: true,
    title: '[CLI] 损坏 state（非法 JSON）→ STATE_CORRUPT 退出码 1，state 字节不变、锁自清理',
    async run(drv, ctx, driverPath) {
      const dir = ctx.dir('ADV-C3');
      const statePath = path.join(dir, 'state.json');
      const bad = '{not-json';
      fs.writeFileSync(statePath, bad);
      const flat = ['--url', LOOPBACK, '--workspace', '/tmp/zgui-ws-adv', '--task-id', 'TASK-ADVCLI',
        '--prompt-file', writePrompt(dir, 'p.txt', '任务 ADV-C3。'), '--state', statePath,
        '--expected-provider', 'p1', '--expected-model', 'm1', '--expected-mode', 'yolo'];
      const r = runCli(driverPath, ['submit', ...flat]);
      if (r.status !== 1) throw new Error(`ADV-C3: 期望退出码 1，实际 ${r.status}`);
      if (!r.json || r.json.error.code !== 'STATE_CORRUPT') {
        throw new Error(`ADV-C3: 期望 STATE_CORRUPT，实际 ${r.json && r.json.error && r.json.error.code}`);
      }
      if (fs.readFileSync(statePath, 'utf8') !== bad) throw new Error('ADV-C3: 损坏 state 被改写（应 fail-closed 不覆写）');
      if (fs.existsSync(`${statePath}.lock`)) throw new Error('ADV-C3: 自建锁未释放');
    },
  },
  {
    id: 'ADV-C4', targets: [], cli: true,
    title: '[CLI] 既有 state 期望漂移 → EXPECTED_CONFIG_CONFLICT 退出码 1，state 字节级不变',
    async run(drv, ctx, driverPath) {
      const dir = ctx.dir('ADV-C4');
      const statePath = path.join(dir, 'state.json');
      const prompt = writePrompt(dir, 'p.txt', '任务 ADV-C4。');
      const sha = crypto.createHash('sha256').update(fs.readFileSync(prompt)).digest('hex');
      const stateObj = {
        schema: drv.STATE_SCHEMA, driverVersion: drv.DRIVER_VERSION,
        url: LOOPBACK, workspace: '/tmp/zgui-ws-adv', taskId: 'TASK-ADVCLI', phase: 'sent-bound',
        prompt: { file: prompt, sha256: sha, bytes: 99, marker: 'ZGUI-M-TASK-ADVCLI-abc123' },
        expectedConfig: { ...GOOD },
      };
      const before = JSON.stringify(stateObj, null, 2);
      fs.writeFileSync(statePath, before);
      const flat = ['--url', LOOPBACK, '--workspace', '/tmp/zgui-ws-adv', '--task-id', 'TASK-ADVCLI',
        '--prompt-file', prompt, '--state', statePath,
        '--expected-provider', GOOD.provider, '--expected-model', 'glm-4.6-air', '--expected-mode', GOOD.mode];
      const r = runCli(driverPath, ['submit', ...flat]);
      if (r.status !== 1) throw new Error(`ADV-C4: 期望退出码 1，实际 ${r.status}`);
      if (!r.json || r.json.error.code !== 'EXPECTED_CONFIG_CONFLICT') {
        throw new Error(`ADV-C4: 期望 EXPECTED_CONFIG_CONFLICT，实际 ${r.json && r.json.error && r.json.error.code}`);
      }
      if (fs.readFileSync(statePath, 'utf8') !== before) throw new Error('ADV-C4: state 在冲突拒绝后被改写');
      if (fs.existsSync(`${statePath}.lock`)) throw new Error('ADV-C4: 锁未释放');
    },
  },
  {
    id: 'ADV-C5', targets: [], cli: true,
    title: '[CLI] 既有任务无期望记录 + 全量显式期望 → 事后追认 EXPECTED_CONFIG_CONFLICT 退出码 1',
    async run(drv, ctx, driverPath) {
      const dir = ctx.dir('ADV-C5');
      const statePath = path.join(dir, 'state.json');
      const prompt = writePrompt(dir, 'p.txt', '任务 ADV-C5。');
      const sha = crypto.createHash('sha256').update(fs.readFileSync(prompt)).digest('hex');
      const stateObj = {
        schema: drv.STATE_SCHEMA, driverVersion: drv.DRIVER_VERSION,
        url: LOOPBACK, workspace: '/tmp/zgui-ws-adv', taskId: 'TASK-ADVCLI', phase: 'sent-bound',
        prompt: { file: prompt, sha256: sha, bytes: 99, marker: 'ZGUI-M-TASK-ADVCLI-def456' },
      };
      const before = JSON.stringify(stateObj, null, 2);
      fs.writeFileSync(statePath, before);
      const flat = ['--url', LOOPBACK, '--workspace', '/tmp/zgui-ws-adv', '--task-id', 'TASK-ADVCLI',
        '--prompt-file', prompt, '--state', statePath,
        '--expected-provider', GOOD.provider, '--expected-model', GOOD.model, '--expected-mode', GOOD.mode];
      const r = runCli(driverPath, ['submit', ...flat]);
      if (r.status !== 1) throw new Error(`ADV-C5: 期望退出码 1，实际 ${r.status}`);
      if (!r.json || r.json.error.code !== 'EXPECTED_CONFIG_CONFLICT') {
        throw new Error(`ADV-C5: 期望 EXPECTED_CONFIG_CONFLICT（拒绝追认），实际 ${r.json && r.json.error && r.json.error.code}`);
      }
      if (fs.readFileSync(statePath, 'utf8') !== before) throw new Error('ADV-C5: state 在追认拒绝后被改写');
    },
  },
];

// ---------------------------------------------------------------------------
// 负控变异体：只作用于私有 tmp 的冻结副本，生产 driver 只读
// ---------------------------------------------------------------------------

const MUTANTS = [
  {
    id: 'W1',
    desc: '安全弱化：移除草稿后/点击前的第二次配置核验（submit-pre-click re-check bypass）',
    find: "const secondCheck = await assertExpectedConfig(page, expected, { stage: 'submit-pre-click', timeoutMs: readyTimeoutMs });",
    replace: "const secondCheck = { provider: expected.provider, model: expected.model, mode: expected.mode, stage: 'submit-pre-click', at: Date.now() };",
    kills: ['ADV-06'],
  },
  {
    id: 'W2',
    desc: '安全弱化：移除 v4-model-config 唯一性门（重复元素不再拒绝，静默取第一个）',
    find: "if (count !== 1) {\n    return { ok: false, code: count === 0 ? 'MISSING' : 'DUPLICATE', count,",
    replace: "if (count === 0) {\n    return { ok: false, code: 'MISSING', count,",
    kills: ['ADV-02'],
  },
  {
    id: 'W3',
    desc: '安全弱化：移除三参数齐备门（部分提供静默降级为观察模式，伪称已核验）',
    find: "if (present.length !== provided.length || (provided.length !== 0 && provided.length !== 3)) {",
    replace: "if (false && (present.length !== provided.length || (provided.length !== 0 && provided.length !== 3))) {",
    kills: ['ADV-01', 'ADV-C1'],
  },
];

// ---------------------------------------------------------------------------
// 运行器
// ---------------------------------------------------------------------------

function findTest(id) {
  const t = TESTS.find(x => x.id === id);
  if (!t) throw new Error(`未知测试: ${id}`);
  return t;
}

async function runDefault(HARNESS) {
  const drv = require(DRIVER_PATH);
  const shaBefore = sha256File(DRIVER_PATH);
  const ctx = new Ctx(HARNESS.tmpRoot || tmpDir());
  console.log(`[adversarial] driver=${path.basename(DRIVER_PATH)} sha256=${shaBefore.slice(0, 16)}… tests=${TESTS.length}`);
  const results = [];
  let failed = 0;
  for (const t of TESTS) {
    const t0 = Date.now();
    let ok = true, errMsg = null;
    try {
      await t.run(drv, ctx, DRIVER_PATH);
    } catch (e) {
      ok = false; failed++;
      errMsg = String(e && e.message || e).slice(0, 300);
    }
    results.push({ id: t.id, title: t.title, ok, ms: Date.now() - t0, error: errMsg });
    console.log(`${ok ? 'PASS' : 'FAIL'} ${t.id} — ${t.title}${ok ? '' : `\n      ↳ ${errMsg}`}`);
  }
  const shaAfter = sha256File(DRIVER_PATH);
  const unchanged = shaAfter === shaBefore;
  if (!unchanged) { failed++; console.log('FAIL 生产 driver SHA 发生变化（harness 禁止修改生产 driver）'); }
  const exitCode = failed ? 1 : 0;
  console.log(`[adversarial] ${TESTS.length - failed}/${TESTS.length} 通过；生产 driver 未修改: ${unchanged}；退出码 ${exitCode}`);
  return { results, exitCode, driverSha256: shaBefore, driverUnchanged: unchanged, tmpRoot: ctx.root };
}

async function runNegative(HARNESS) {
  const shaBefore = sha256File(DRIVER_PATH);
  const mutantRoot = HARNESS.mutantDir || fs.mkdtempSync(path.join(os.tmpdir(), 'zgui-config-adversarial-mutants-'));
  fs.mkdirSync(mutantRoot, { recursive: true });
  const ctx = new Ctx(HARNESS.tmpRoot || tmpDir());
  console.log(`[negative] 生产 driver sha256=${shaBefore.slice(0, 16)}…（全程只读，前后校验）`);
  console.log(`[negative] 变异目录（私有 tmp）: ${mutantRoot}`);
  const mutantReports = [];
  let survived = 0;
  for (const m of MUTANTS) {
    const mDir = path.join(mutantRoot, `${m.id}-${crypto.randomBytes(3).toString('hex')}`);
    fs.mkdirSync(mDir, { recursive: true });
    const src = fs.readFileSync(DRIVER_PATH, 'utf8');
    const n = src.split(m.find).length - 1;
    if (n !== 1) {
      mutantReports.push({ id: m.id, error: `find 串出现 ${n} 次（应恰 1 次），拒绝变异` });
      survived++;
      continue;
    }
    const mutantPath = path.join(mDir, 'zcode-browser-driver.mutated.cjs');
    fs.writeFileSync(mutantPath, src.replace(m.find, m.replace));
    const mutantSha = sha256File(mutantPath);
    const chk = spawnSync(process.execPath, ['--check', mutantPath], { encoding: 'utf8' });
    if (chk.status !== 0) {
      mutantReports.push({ id: m.id, error: `变异副本语法检查失败: ${chk.stderr.slice(0, 200)}` });
      survived++;
      continue;
    }
    let mdrv;
    try { mdrv = require(mutantPath); } catch (e) {
      mutantReports.push({ id: m.id, error: `变异副本加载失败: ${e.message}` });
      survived++;
      continue;
    }
    const kills = [];
    for (const testId of m.kills) {
      const t = findTest(testId);
      const t0 = Date.now();
      let killed = false, detail = null;
      try {
        await t.run(mdrv, ctx, mutantPath);
        killed = false; detail = '测试在弱化副本上仍然通过 → 未捕获该弱化';
      } catch (e) {
        killed = true; detail = String(e && e.message || e).slice(0, 240);
      }
      if (!killed) survived++;
      kills.push({ testId, killed, ms: Date.now() - t0, detail });
      console.log(`${killed ? 'KILL' : 'SURVIVE'} ${m.id} ⊃ ${testId}${killed ? ` — ${detail}` : ' ← 变异体存活（灵敏度不足）'}`);
    }
    mutantReports.push({ id: m.id, desc: m.desc, mutantPath, mutantSha256: mutantSha, syntaxOk: true, kills });
  }
  const shaAfter = sha256File(DRIVER_PATH);
  const unchanged = shaAfter === shaBefore;
  if (!unchanged) survived++;
  const exitCode = survived ? (unchanged ? 4 : 1) : 0;
  console.log(`[negative] 存活变异体: ${survived}；生产 driver 未修改: ${unchanged}；退出码 ${exitCode}`);
  return { exitCode, driverSha256: shaBefore, driverUnchanged: unchanged, mutants: mutantReports, mutantRoot, tmpRoot: ctx.root };
}

function writeReport(HARNESS, payload) {
  if (!HARNESS.report) return;
  const body = Object.assign({
    taskId: TASK_ID,
    harness: path.basename(__filename),
    driverPath: DRIVER_PATH,
    mode: HARNESS.mode,
    node: process.version,
    finishedAt: new Date().toISOString(),
  }, payload);
  fs.mkdirSync(path.dirname(path.resolve(HARNESS.report)), { recursive: true });
  fs.writeFileSync(HARNESS.report, JSON.stringify(body, null, 2) + '\n');
  console.log(`[report] ${HARNESS.report}`);
}

async function main() {
  const HARNESS = parseHarnessArgs(process.argv.slice(2));
  const startedAt = new Date().toISOString();
  if (HARNESS.mode === 'list') {
    for (const t of TESTS) {
      console.log(`${t.id}\tcli=${t.cli ? 'Y' : 'n'}\tkills=${t.targets.join(',') || '-'}\t${t.title}`);
    }
    for (const m of MUTANTS) console.log(`${m.id}\tmutant\tkills=${m.kills.join(',')}\t${m.desc}`);
    process.exit(0);
  }
  let payload;
  if (HARNESS.mode === 'negative') {
    payload = await runNegative(HARNESS);
  } else {
    payload = await runDefault(HARNESS);
  }
  payload.startedAt = startedAt;
  writeReport(HARNESS, payload);
  process.exit(payload.exitCode);
}

main().catch(e => {
  console.error(`[adversarial] harness 错误: ${e && e.stack || e}`);
  process.exit(1);
});
