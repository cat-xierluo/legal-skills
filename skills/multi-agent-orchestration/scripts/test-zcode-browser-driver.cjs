#!/usr/bin/env node
/**
 * test-zcode-browser-driver.cjs — zcode-browser-driver.cjs 契约/单元测试（node --test）。
 *
 * 覆盖任务要求的合同点：
 *   1) 重复 submit 不重复 click（同 state 不自动重发；不承诺跨进程 exactly-once）
 *   2) 发送后不确定不重投（sent-unconfirmed → 对账 only）
 *   3) 指纹冲突拒绝（url/workspace/task-id/prompt 任一变化）
 *   4) state 排他锁冲突
 *   5) 错误/损坏 state fail-closed
 *   6) 精确回合绑定 + 排除 reasoning/tool 文本
 *   7) follow-up 每轮去重（同 input-id 不二次 click）
 *   8) loopback URL 限制、原子写不残留 tmp、marker 歧义拒绝、目录错配不重试
 *
 * 不启动浏览器/网络/模型：FakePage 注入 + 临时 fixture SQLite（node:sqlite）。
 * 真实端到端由 PM 执行。
 */
'use strict';

const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const os = require('os');
const crypto = require('crypto');

const driver = require('./zcode-browser-driver.cjs');
const { DatabaseSync } = require('node:sqlite');

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------

function tmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'zgui-driver-test-'));
}

// 捕获 driver 的 emit 输出（__setEmitSink 测试钩子，不碰 test runner 的 stdout）
async function captureEmit(fn) {
  let captured = null;
  driver.__setEmitSink((obj, exitCode) => { captured = { json: obj, exitCode }; });
  try {
    await fn();
  } finally {
    driver.__setEmitSink(null);
  }
  assert(captured, '期望 driver 至少一次 emit 输出');
  return captured;
}

// ---------------------------------------------------------------------------
// Fake Playwright page
// ---------------------------------------------------------------------------

class FakeLocator {
  constructor(page, key, opts = {}) {
    this.page = page; this.key = key; this.opts = opts;
  }
  _ev(kind) { if (this.page && this.page.events) this.page.events.push(`${kind}:${this.key}`); }
  async count() {
    if (this.opts.count !== undefined) return this.opts.count;
    if (this.opts.exists || this.opts.text !== undefined) return 1; // 带 text 的定位器视为存在
    return 0;
  }
  first() { return this; }
  nth(_i) { return this; }
  async innerText() { this._ev('read'); return typeof this.opts.text === 'function' ? this.opts.text() : (this.opts.text || ''); }
  async isDisabled() { return this.opts.disabled ? this.opts.disabled() : false; }
  async click() {
    this._ev('click');
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
    this.rows = []; // [{text}]
    this.sendClicks = 0;
    this.events = []; // R2: 顺序断言（new-task → workspace → mode/model）
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
  getByTestId(id) {
    if (id === driver.LOC.composerInput) {
      return new FakeLocator(this, id, { exists: true, text: () => this.draft, onClick: async () => {} });
    }
    if (id === driver.LOC.send) {
      return new FakeLocator(this, id, { exists: true, disabled: () => this.draft.trim() === '' });
    }
    if (id === driver.LOC.workspaceTrigger) return new FakeLocator(this, id, { text: this.cfg.wsLabel || '选择项目' });
    if (id === driver.LOC.modeTrigger) {
      const ml = this.cfg.modeLabel !== undefined ? this.cfg.modeLabel : '变更前确认';
      return new FakeLocator(this, id, { text: ml });
    }
    if (id === driver.LOC.modelTrigger) {
      const ml = this.cfg.modelLabel !== undefined
        ? (typeof this.cfg.modelLabel === 'function' ? this.cfg.modelLabel() : this.cfg.modelLabel)
        : 'Fake/Model-X';
      return new FakeLocator(this, id, { text: ml });
    }
    if (id === driver.LOC.taskNewButton) return new FakeLocator(this, id, { exists: true, onClick: async () => {} });
    if (id === driver.LOC.row) {
      return new FakeLocator(this, id, { count: this.rows.length, text: () => this.rows.map(r => r.text).join('\n') });
    }
    if (id === driver.LOC.sessionTitle) return new FakeLocator(this, id, { text: this.cfg.sessionTitle || '' });
    if (id.startsWith(driver.LOC.taskItemPrefix)) return new FakeLocator(this, id, this.cfg.taskItem || { count: 0 });
    return new FakeLocator(this, id, { count: 0 });
  }
  getByRole(role) {
    if (role === 'textbox') return new FakeLocator(this, 'role:textbox', { count: 1 });
    return new FakeLocator(this, 'role:' + role, { count: 0 });
  }
  locator(sel) {
    // task-item 精确选择器
    const m = /^\[data-testid="task-item-(.+)"\]$/.exec(sel);
    if (m) {
      const want = m[1];
      const present = this.cfg.openSessionId === want;
      return new FakeLocator(this, sel, {
        count: present ? 1 : 0,
        onClick: async () => {
          // 打开会话：时间线出现原 marker 行
          this.rows.push({ text: this.cfg.openRows ? this.cfg.openRows.join('\n') : '' });
        },
      });
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

function makeDeps(fakePage, fixtureDbPath, workspace) {
  return {
    async openPage() { return { page: fakePage, close: async () => { fakePage.closed = true; } }; },
    async fetchServerInfo() {
      return { serverId: 'fake', version: '0.0.0-test', authRequired: false, workspaces: [{ path: workspace, label: 'default' }] };
    },
    nativeDbPath: () => fixtureDbPath,
  };
}

// ---------------------------------------------------------------------------
// fixture SQLite：最小 schema（与生产查询一致）
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

function insertSession(db, { id, directory, title = 'T' }) {
  db.prepare('INSERT INTO session (id, directory, title) VALUES (?,?,?)').run(id, directory, title);
}

function insertInput(db, { id, sessionId, text, status = 'promoted', promotedMessageId = null }) {
  db.prepare('INSERT INTO session_input (id, session_id, payload, status, promoted_message_id) VALUES (?,?,?,?,?)')
    .run(id, sessionId, JSON.stringify({ text }), status, promotedMessageId);
}

function insertMessage(db, { id, sessionId, parent, role, completed = null, seq = 0 }) {
  const time = { created: 1 };
  if (completed) time.completed = completed;
  db.prepare('INSERT INTO message (id, session_id, data, sequence) VALUES (?,?,?,?)')
    .run(id, sessionId, JSON.stringify({ role, parentID: parent, time }), seq);
}

function insertPart(db, { id, messageId, sessionId, type, text = null, seq = 0 }) {
  const data = type === 'text' ? { type, text } : { type, text: text || 'x', opaque: true };
  db.prepare('INSERT INTO part (id, message_id, session_id, data, sequence) VALUES (?,?,?,?,?)')
    .run(id, messageId, sessionId, JSON.stringify(data), seq);
}

// ---------------------------------------------------------------------------
// 场景构造：一次“成功接收”的完整 DB 侧落库
// ---------------------------------------------------------------------------

function seedReceivedTurn(db, { sessionId, directory, inputId, marker, userMsgId,
  assistantMsgs, turnId = 'turn_1', turnStatus = 'completed' }) {
  insertSession(db, { id: sessionId, directory });
  insertInput(db, { id: inputId, sessionId, text: `任务内容 ${marker}`, promotedMessageId: userMsgId });
  insertMessage(db, { id: userMsgId, sessionId, parent: null, role: 'user', seq: 0 });
  db.prepare('INSERT INTO turn_usage (session_id, turn_id, user_message_id, status, started_at, completed_at) VALUES (?,?,?,?,?,?)')
    .run(sessionId, turnId, userMsgId, turnStatus, 1, turnStatus === 'completed' ? 2 : null);
  let seq = 1;
  for (const am of assistantMsgs) {
    insertMessage(db, { id: am.id, sessionId, parent: userMsgId, role: 'assistant', completed: am.completed || 123, seq: seq++ });
    let p = 0;
    for (const part of am.parts) {
      insertPart(db, { id: `${am.id}-p${p++}`, messageId: am.id, sessionId, type: part.type, text: part.text, seq: p });
    }
  }
}

// 提交一组公共参数
function submitArgs(dir, opts = {}) {
  return {
    url: 'http://127.0.0.1:18490/',
    workspace: opts.workspace || '/tmp/zgui-ws',
    'task-id': opts.taskId || 'TASK-1',
    'prompt-file': opts.promptFile,
    state: path.join(dir, 'state.json'),
    'timeout-ms': opts.timeoutMs || 1500,
  };
}

function writePrompt(dir, name, text) {
  const p = path.join(dir, name);
  fs.writeFileSync(p, text);
  return p;
}

// ---------------------------------------------------------------------------
// 测试
// ---------------------------------------------------------------------------

test('loopback URL 限制：非 loopback/userinfo/query/hash 拒绝；IPv6 放行', () => {
  assert.throws(() => driver.assertLoopbackUrl('http://192.168.1.5:8080/'), e => e.code === 'URL_NOT_LOOPBACK');
  assert.throws(() => driver.assertLoopbackUrl('http://example.com/'), e => e.code === 'URL_NOT_LOOPBACK');
  assert.throws(() => driver.assertLoopbackUrl('ftp://127.0.0.1/'), e => e.code === 'URL_NOT_LOOPBACK');
  assert.throws(() => driver.assertLoopbackUrl('http://user:pass@127.0.0.1:18490/'), e => e.code === 'URL_NOT_LOOPBACK');
  assert.throws(() => driver.assertLoopbackUrl('http://127.0.0.1:18490/?token=abc'), e => e.code === 'URL_NOT_LOOPBACK');
  assert.throws(() => driver.assertLoopbackUrl('http://127.0.0.1:18490/#sect'), e => e.code === 'URL_NOT_LOOPBACK');
  const u = driver.assertLoopbackUrl('http://localhost:18490/');
  assert.equal(u.hostname, 'localhost');
  const u6 = driver.assertLoopbackUrl('http://[::1]:18490/');
  assert.equal(u6.hostname.replace(/^\[|\]$/g, ''), '::1');
});

test('submit 唯一发送并精确绑定；重复调用只对账不再点击', async () => {
  const dir = tmpDir();
  const ws = '/tmp/zgui-ws';
  const fixture = path.join(dir, 'native.sqlite');
  const db = buildFixtureDb(fixture);
  const prompt = writePrompt(dir, 'p.txt', '任务 TASK-1：完成某研究。');

  let seeded = false;
  const page = new FakePage({
    onSendClick: async (typed, pg) => {
      // 模拟服务接收：落库 session/input/turn + DOM 行
      const m = /\[ZGUI-M-(TASK-1|[A-Za-z0-9_-]+)-[0-9a-f]+\]/.exec(typed);
      const marker = m ? m[0].slice(1, -1) : 'ZGUI-M-unknown';
      seeded = true;
      seedReceivedTurn(db, {
        sessionId: 'sess_test1', directory: ws, inputId: 'in_test1', marker,
        userMsgId: 'msg_u1',
        assistantMsgs: [
          { id: 'msg_a1', parts: [{ type: 'step-start' }, { type: 'reasoning', text: '机密推理不应出现' }, { type: 'tool' }] },
          { id: 'msg_a2', parts: [{ type: 'text', text: '中途状态文本不应作为 final。' }] },
          { id: 'msg_a3', parts: [{ type: 'text', text: '最后一段交付正文。' }] },
        ],
      });
      pg.rows.push({ text: typed });
    },
  });
  const deps = makeDeps(page, fixture, ws);
  const args = submitArgs(dir, { promptFile: prompt, workspace: ws });

  const r1 = await captureEmit(() => driver.__internalsForTest.cmdSubmit({ ...args }, deps));
  assert.equal(r1.json.ok, true, JSON.stringify(r1.json));
  assert.equal(r1.json.status, 'sent-bound');
  assert.equal(page.sendClicks, 1, '必须恰好点击一次发送');
  assert.equal(r1.json.binding.sessionId, 'sess_test1');
  assert.equal(r1.json.binding.inputId, 'in_test1');
  assert.equal(page.closed, true, '浏览器必须被关闭');

  const st = driver.readState(args.state);
  assert.equal(st.phase, 'sent-bound');
  assert.equal(st.binding.sessionId, 'sess_test1');
  assert.ok(st.prompt.marker.startsWith('ZGUI-M-'));

  // 第二次同参调用：对账，不打开浏览器、不再点击
  const page2 = new FakePage({});
  const deps2 = makeDeps(page2, fixture, ws);
  const r2 = await captureEmit(() => driver.__internalsForTest.cmdSubmit({ ...args }, deps2));
  assert.equal(r2.json.status, 'reconciled');
  assert.equal(r2.json.inputId, 'in_test1');
  assert.equal(page2.sendClicks, 0, '对账路径绝不允许再点击');
  assert.equal(r2.json.finalText, '最后一段交付正文。', 'finalText=最后一条 assistant 消息的 text parts');
  assert.equal(r2.json.finalTextAvailability, 'available');
  assert.ok(!r2.json.finalText.includes('机密推理'), '不得混入 reasoning');
  // R2 顺序：先 new-task，再 workspace，再 mode/model
  const ev = page.events;
  const iNew = ev.indexOf('click:task-new-button');
  const iWs = ev.indexOf('read:composer-workspace-trigger');
  const iMode = ev.indexOf('read:chat-mode-select-trigger');
  const iModel = ev.indexOf('read:chat-model-select-trigger');
  assert.ok(iNew >= 0 && iWs > iNew && iMode > iWs && iModel > iWs, `顺序错误: ${JSON.stringify(ev.filter(e => !e.startsWith('read:v4-row') && !e.startsWith('read:v4-composer-input')))}`);
  // R2：state 无 prompt 预览；文件 0600
  assert.equal(st.prompt.preview, undefined, 'state 不保存 prompt 预览');
  assert.equal(fs.statSync(args.state).mode & 0o777, 0o600, 'state 文件权限 0600');
});

test('发送后不确定：保留 unknown 且不重投', async () => {
  const dir = tmpDir();
  const ws = '/tmp/zgui-ws2';
  const fixture = path.join(dir, 'native.sqlite');
  buildFixtureDb(fixture); // 空 DB：服务从未落库
  const prompt = writePrompt(dir, 'p.txt', '任务内容 X');
  const page = new FakePage({ onSendClick: async (t, pg) => pg.rows.push({ text: t }) }); // DOM 有行，DB 无
  const deps = makeDeps(page, fixture, ws);
  const args = submitArgs(dir, { promptFile: prompt, workspace: ws });

  const r1 = await captureEmit(() => driver.__internalsForTest.cmdSubmit({ ...args }, deps));
  assert.equal(r1.json.ok, true);
  assert.equal(r1.json.status, 'unknown');
  assert.equal(r1.json.domRowObserved, true);
  assert.equal(page.sendClicks, 1);
  const st = driver.readState(args.state);
  assert.equal(st.phase, 'sent-unconfirmed');

  // 再次调用：仍 unknown，且不开浏览器（对账路径）
  const page2 = new FakePage({});
  const r2 = await captureEmit(() => driver.__internalsForTest.cmdSubmit({ ...args }, makeDeps(page2, fixture, ws)));
  assert.equal(r2.json.status, 'unknown');
  assert.equal(page2.sendClicks, 0, '不确定状态绝不重投');
});

test('指纹冲突：同 state 换 task/workspace/prompt 均拒绝', async () => {
  const dir = tmpDir();
  const ws = '/tmp/zgui-ws3';
  const fixture = path.join(dir, 'native.sqlite');
  const db = buildFixtureDb(fixture);
  const prompt1 = writePrompt(dir, 'p1.txt', '原始任务输入');
  const prompt2 = writePrompt(dir, 'p2.txt', '不同的任务输入');

  const page = new FakePage({
    onSendClick: async (typed, pg) => {
      const m = /\[ZGUI-M-[^\]]+\]/.exec(typed);
      seedReceivedTurn(db, {
        sessionId: 'sess_t3', directory: ws, inputId: 'in_t3', marker: m[0].slice(1, -1),
        userMsgId: 'msg_u3', assistantMsgs: [{ id: 'msg_a3', parts: [{ type: 'text', text: 'ok' }] }],
      });
      pg.rows.push({ text: typed });
    },
  });
  const deps = makeDeps(page, fixture, ws);
  const args = submitArgs(dir, { promptFile: prompt1, workspace: ws });
  const r1 = await captureEmit(() => driver.__internalsForTest.cmdSubmit({ ...args }, deps));
  assert.equal(r1.json.status, 'sent-bound');

  // 换 task-id
  await assert.rejects(
    () => driver.__internalsForTest.cmdSubmit({ ...args, 'task-id': 'TASK-OTHER' }, makeDeps(new FakePage(), fixture, ws)),
    e => { assert.equal(e.code, 'STATE_FINGERPRINT_CONFLICT'); return true; }
  );
  // 换 workspace
  await assert.rejects(
    () => driver.__internalsForTest.cmdSubmit({ ...args, workspace: '/tmp/other-ws' }, makeDeps(new FakePage(), fixture, '/tmp/other-ws')),
    e => { assert.equal(e.code, 'STATE_FINGERPRINT_CONFLICT'); return true; }
  );
  // 换 prompt 内容
  await assert.rejects(
    () => driver.__internalsForTest.cmdSubmit({ ...args, 'prompt-file': prompt2 }, deps),
    e => { assert.equal(e.code, 'STATE_FINGERPRINT_CONFLICT'); return true; }
  );
  // 换 url
  await assert.rejects(
    () => driver.__internalsForTest.cmdSubmit({ ...args, url: 'http://127.0.0.1:19999/' }, deps),
    e => { assert.equal(e.code, 'STATE_FINGERPRINT_CONFLICT'); return true; }
  );
  assert.equal(page.sendClicks, 1, '冲突路径无额外点击');
});

test('锁存在一律拒绝：owner 缺失/损坏/同 PID/陈旧死 PID，均不删锁不抢占', async () => {
  const dir = tmpDir();
  const statePath = path.join(dir, 'state.json');
  const lockDir = `${statePath}.lock`;
  const ownerFile = path.join(lockDir, 'owner.json');

  const expectRefused = async (label) => {
    let ran = false;
    await assert.rejects(
      () => driver.withStateLock(statePath, async () => { ran = true; }),
      e => { assert.equal(e.code, 'LOCK_HELD', label); return true; }
    );
    assert.equal(ran, false, label + '：不得进入临界区');
    assert.equal(fs.existsSync(lockDir), true, label + '：拒绝时不得删除锁');
  };

  fs.mkdirSync(lockDir);                      // owner 缺失（mkdir 后崩溃窗口）
  await expectRefused('owner 缺失');
  fs.writeFileSync(ownerFile, '{ 损坏');        // owner 损坏
  await expectRefused('owner 损坏');
  fs.writeFileSync(ownerFile, JSON.stringify({ pid: process.pid, nonce: 'x' })); // 同 PID
  await expectRefused('同 PID');
  fs.writeFileSync(ownerFile, JSON.stringify({ pid: 999999999, nonce: 'x' }));   // 陈旧死 PID
  await expectRefused('陈旧死 PID');

  fs.rmSync(lockDir, { recursive: true, force: true }); // 人工清理后才可用
  let ran = false;
  await driver.withStateLock(statePath, async () => { ran = true; });
  assert.equal(ran, true);
  assert.equal(fs.existsSync(lockDir), false, '正常释放后锁消失');
});

test('锁：真实子进程持锁 → LOCK_HELD；子进程退出未释放 → 仍拒绝（不自动清理）', async () => {
  const { spawn } = require('child_process');
  const dir = tmpDir();
  const statePath = path.join(dir, 'state.json');
  const lockDir = `${statePath}.lock`;
  const child = spawn(process.execPath, ['-e',
    "const fs=require('fs');fs.mkdirSync(process.argv[1]);" +
    "fs.writeFileSync(process.argv[1]+'/owner.json',JSON.stringify({pid:process.pid,nonce:'child'}));" +
    "setTimeout(()=>{},2000);",
    lockDir]);
  await new Promise((resolve) => {
    const iv = setInterval(() => { if (fs.existsSync(lockDir)) { clearInterval(iv); resolve(); } }, 50);
  });
  await assert.rejects(
    () => driver.withStateLock(statePath, async () => {}),
    e => e.code === 'LOCK_HELD'
  );
  await new Promise((resolve) => child.on('exit', resolve));
  // 子进程崩溃式退出未释放 → 锁仍在，仍拒绝
  await assert.rejects(
    () => driver.withStateLock(statePath, async () => {}),
    e => e.code === 'LOCK_HELD'
  );
  assert.equal(fs.existsSync(lockDir), true);
  fs.rmSync(lockDir, { recursive: true, force: true });
});

test('锁释放核 nonce：持锁期间被换成他人 nonce → 不删除他人锁', async () => {
  const dir = tmpDir();
  const statePath = path.join(dir, 'state.json');
  const lockDir = `${statePath}.lock`;
  await driver.withStateLock(statePath, async () => {
    fs.writeFileSync(path.join(lockDir, 'owner.json'), JSON.stringify({ pid: 4242, nonce: 'foreign' }));
  });
  assert.equal(fs.existsSync(lockDir), true, 'nonce 不匹配时不得删除锁');
  fs.rmSync(lockDir, { recursive: true, force: true });
});

test('损坏/缺失 state fail-closed', () => {
  const dir = tmpDir();
  const sp = path.join(dir, 's.json');
  fs.writeFileSync(sp, '{ not json');
  assert.throws(() => driver.readState(sp), e => e.code === 'STATE_CORRUPT');
  const sp2 = path.join(dir, 's2.json');
  fs.writeFileSync(sp2, JSON.stringify({ schema: 1, url: 'x' })); // 缺身份字段
  assert.throws(() => driver.readState(sp2), e => e.code === 'STATE_CORRUPT');
    // 缺失文件：readState 返回 null（submit 用于判断新任务；observe/follow-up 则 STATE_MISSING fail-closed）
  assert.equal(driver.readState(path.join(dir, 'missing.json')), null);
});

test('精确回合绑定与 reasoning/tool 排除（含身份不一致 fail-closed）', async () => {
  const dir = tmpDir();
  const fixture = path.join(dir, 'native.sqlite');
  const db = buildFixtureDb(fixture);
  const ws = '/tmp/zgui-ws4';
  seedReceivedTurn(db, {
    sessionId: 'sess_r1', directory: ws, inputId: 'in_r1', marker: 'ZGUI-M-R1-abc12345',
    userMsgId: 'msg_ur1',
    assistantMsgs: [
      { id: 'msg_ar0', parts: [{ type: 'step-start' }, { type: 'reasoning', text: 'REASONING_MUST_NOT_APPEAR' }, { type: 'tool' }] },
      { id: 'msg_ar1', parts: [{ type: 'text', text: '中间状态：正在查资料。' }, { type: 'step-finish' }] },
      { id: 'msg_ar2', parts: [{ type: 'reasoning', text: 'MORE_REASONING' }, { type: 'text', text: '交付正文第一段。' }, { type: 'text', text: '交付正文第二段。' }] },
    ],
  });
  // 另一个无关 session 的同 marker 输入 → 歧义
  // （单独测试歧义用例，这里先测绑定路径）
  const state = {
    schema: 1, url: 'http://127.0.0.1:18490/', workspace: ws, taskId: 'T',
    prompt: { sha256: 'a'.repeat(64), marker: 'ZGUI-M-R1-abc12345' },
    phase: 'sent-bound',
    binding: { sessionId: 'sess_r1', inputId: 'in_r1' },
  };
  const st = driver.collectStatus(state, fixture);
  assert.equal(st.found, true);
  assert.equal(st.inputId, 'in_r1');
  assert.equal(st.finalText, '交付正文第一段。\n交付正文第二段。');
  assert.equal(st.finalTextAvailability, 'available');
  assert.ok(!st.finalText.includes('REASONING'));
  assert.ok(!st.finalText.includes('中间状态'), 'finalText 不取中途含 text 的消息');
  assert.equal(st.final.lastMessageCompleted, true);

  // 身份不一致：state 绑定的 inputId 指向无 marker 的行 → fail-closed
  insertSession(db, { id: 'sess_r2', directory: ws });
  insertInput(db, { id: 'in_r2', sessionId: 'sess_r2', text: '别人的输入，无 marker' });
  const stateBad = {
    ...state, binding: { sessionId: 'sess_r2', inputId: 'in_r2' },
  };
  assert.throws(() => driver.collectStatus(stateBad, fixture), e => e.code === 'IDENTITY_MISMATCH');

  // marker 歧义：两行同 marker 且无 binding → 拒绝自动选择
  insertSession(db, { id: 'sess_r3', directory: ws });
  insertInput(db, { id: 'in_r3', sessionId: 'sess_r3', text: '重复 ZGUI-M-R1-abc12345' });
  assert.throws(() => driver.collectStatus({ ...state, binding: null }, fixture), e => e.code === 'BINDING_AMBIGUOUS');
});

test('finalText 门控：turn running / cancelled / 工具后无文本 → 空 + 明确原因', async () => {
  const mk = (turnStatus, assistantMsgs) => {
    const dir = tmpDir();
    const fixture = path.join(dir, 'n.sqlite');
    const db = buildFixtureDb(fixture);
    const marker = 'ZGUI-M-GATE-' + Math.random().toString(16).slice(2, 10);
    seedReceivedTurn(db, {
      sessionId: 'sess_gate', directory: '/tmp/ws-gate', inputId: 'in_gate', marker,
      userMsgId: 'msg_ug', assistantMsgs, turnStatus,
    });
    const state = {
      schema: 1, url: 'http://127.0.0.1:18490/', workspace: '/tmp/ws-gate', taskId: 'T',
      prompt: { sha256: 'a'.repeat(64), marker }, phase: 'sent-bound',
      binding: { sessionId: 'sess_gate', inputId: 'in_gate' },
    };
    return driver.collectStatus(state, fixture);
  };
  // turn 运行中：中途文本不得作为 final
  let st = mk('running', [
    { id: 'm1', parts: [{ type: 'text', text: '正在处理…' }] },
  ]);
  assert.equal(st.turn.status, 'running');
  assert.equal(st.finalText, null);
  assert.equal(st.finalTextAvailability, 'turn-running');
  // turn cancelled
  st = mk('cancelled', [{ id: 'm1', parts: [{ type: 'text', text: '部分输出' }] }]);
  assert.equal(st.finalText, null);
  assert.equal(st.finalTextAvailability, 'turn-cancelled');
  // completed 但最后一条 assistant 消息只有工具调用、无文本（新增工具后无最终文本）
  st = mk('completed', [
    { id: 'm1', parts: [{ type: 'text', text: '我先查一下资料。' }] },
    { id: 'm2', parts: [{ type: 'tool' }, { type: 'step-finish' }] },
  ]);
  assert.equal(st.finalText, null, '最后消息无文本时不得回退取中途文本');
  assert.equal(st.finalTextAvailability, 'no-text-in-last-assistant-message');
  assert.equal(st.final.messageCount, 2);
  // completed 且最后消息含文本 → available
  st = mk('completed', [
    { id: 'm1', parts: [{ type: 'tool' }] },
    { id: 'm2', parts: [{ type: 'text', text: '最终交付文本。' }] },
  ]);
  assert.equal(st.finalText, '最终交付文本。');
  assert.equal(st.finalTextAvailability, 'available');
});

test('对账冲突一律拒绝：目录不符 / promotedMessageId 冲突 / turnId 冲突', async () => {
  const dir = tmpDir();
  const fixture = path.join(dir, 'n.sqlite');
  const db = buildFixtureDb(fixture);
  const ws = '/tmp/ws-conf';
  const marker = 'ZGUI-M-CONF-77777777';
  seedReceivedTurn(db, {
    sessionId: 'sess_conf', directory: ws, inputId: 'in_conf', marker,
    userMsgId: 'msg_uc', turnId: 'turn_real',
    assistantMsgs: [{ id: 'msg_ac', parts: [{ type: 'text', text: 'x' }] }],
  });
  const base = {
    schema: 1, url: 'http://127.0.0.1:18490/', workspace: ws, taskId: 'T',
    prompt: { sha256: 'a'.repeat(64), marker }, phase: 'sent-bound',
    binding: { sessionId: 'sess_conf', inputId: 'in_conf', promotedMessageId: 'msg_uc', turnId: 'turn_real' },
  };
  // 目录不符（绑定路径）：state.workspace 与 session.directory 不一致
  assert.throws(
    () => driver.collectStatus({ ...base, workspace: '/tmp/other' }, fixture),
    e => e.code === 'DIRECTORY_MISMATCH');
  // 目录不符（无绑定、单候选路径）
  assert.throws(
    () => driver.collectStatus({ ...base, workspace: '/tmp/other2', binding: null }, fixture),
    e => e.code === 'DIRECTORY_MISMATCH');
  // promotedMessageId 冲突
  assert.throws(
    () => driver.collectStatus({ ...base, binding: { ...base.binding, promotedMessageId: 'msg_OTHER' } }, fixture),
    e => e.code === 'IDENTITY_MISMATCH');
  // turnId 冲突
  assert.throws(
    () => driver.collectStatus({ ...base, binding: { ...base.binding, turnId: 'turn_OTHER' } }, fixture),
    e => e.code === 'IDENTITY_MISMATCH');
});

test('marker 查询用 instr：SQL 通配符按字面量处理', async () => {
  const dir = tmpDir();
  const fixture = path.join(dir, 'n.sqlite');
  const db = buildFixtureDb(fixture);
  insertSession(db, { id: 'sess_w1', directory: '/tmp/w' });
  insertSession(db, { id: 'sess_w2', directory: '/tmp/w' });
  insertInput(db, { id: 'in_w1', sessionId: 'sess_w1', text: 'literal a%b marker' }); // 含 %
  insertInput(db, { id: 'in_w2', sessionId: 'sess_w2', text: 'aXb and aYb both match underscore?' }); // 会被 _ 通配误命中（LIKE 语义）
  const handle = driver.openDbReadOnly(fixture, 'fixture');
  try {
    const rows = driver.findInputByMarker(handle, 'a%b');
    assert.equal(rows.length, 1, `instr 只命中字面量 a%b，实得 ${rows.length}`);
    assert.equal(rows[0].input_id, 'in_w1');
  } finally {
    // 关闭句柄（driver 导出的 handle 支持 closeDb 语义）
    handle.db.close();
  }
});

test('parseConcreteModel：剥离「管理模型」占位行，剩具体模型名才算就绪', () => {
  assert.equal(driver.parseConcreteModel('管理模型'), null);
  assert.equal(driver.parseConcreteModel('管理模型\nMiniMax/MiniMax-M3.1-Flash-Preview'), 'MiniMax/MiniMax-M3.1-Flash-Preview');
  assert.equal(driver.parseConcreteModel(null), null);
  assert.equal(driver.parseConcreteModel('  '), null);
  assert.equal(driver.parseConcreteModel('GLM-5.3'), 'GLM-5.3');
});

test('submit：模型仅为「管理模型」占位 → CONFIG_NOT_READY 拒绝，不落 intent 不点击', async () => {
  const dir = tmpDir();
  const ws = '/tmp/zgui-ws-r3a';
  const fixture = path.join(dir, 'n.sqlite');
  buildFixtureDb(fixture);
  const prompt = writePrompt(dir, 'p.txt', '任务内容 R3A');
  const page = new FakePage({ modelLabel: '管理模型' }); // 持续占位
  const deps = makeDeps(page, fixture, ws);
  const args = submitArgs(dir, { promptFile: prompt, workspace: ws });
  args['ready-timeout-ms'] = 300;
  await assert.rejects(
    () => driver.__internalsForTest.cmdSubmit(args, deps),
    e => { assert.equal(e.code, 'CONFIG_NOT_READY'); assert.ok(/model/.test(e.message)); return true; }
  );
  assert.equal(page.sendClicks, 0, '未盲发');
  assert.equal(fs.existsSync(args.state), false, '拒绝时不落 state 文件');
});

test('submit：模型延迟就绪 → 有界等待后回读具体模型并正常发送', async () => {
  const dir = tmpDir();
  const ws = '/tmp/zgui-ws-r3b';
  const fixture = path.join(dir, 'n.sqlite');
  const db = buildFixtureDb(fixture);
  const prompt = writePrompt(dir, 'p.txt', '任务内容 R3B');
  let reads = 0;
  const page = new FakePage({
    modelLabel: () => (++reads <= 2 ? '管理模型' : '管理模型\nMiniMax/Test-X'),
    onSendClick: async (typed, pg) => {
      const m = /\[ZGUI-M-[^\]]+\]/.exec(typed);
      seedReceivedTurn(db, {
        sessionId: 'sess_r3b', directory: ws, inputId: 'in_r3b', marker: m[0].slice(1, -1),
        userMsgId: 'msg_u3b', assistantMsgs: [{ id: 'msg_a3b', parts: [{ type: 'text', text: 'ok' }] }],
      });
      pg.rows.push({ text: typed });
    },
  });
  const deps = makeDeps(page, fixture, ws);
  const args = submitArgs(dir, { promptFile: prompt, workspace: ws });
  args['ready-timeout-ms'] = 5000;
  const r = await captureEmit(() => driver.__internalsForTest.cmdSubmit(args, deps));
  assert.equal(r.json.status, 'sent-bound');
  assert.equal(page.sendClicks, 1);
  const st = driver.readState(args.state);
  assert.equal(st.page.concreteModel, 'MiniMax/Test-X');
  assert.equal(st.page.configReady, true);
});

test('submit：模式为空 → CONFIG_NOT_READY 拒绝', async () => {
  const dir = tmpDir();
  const ws = '/tmp/zgui-ws-r3c';
  const fixture = path.join(dir, 'n.sqlite');
  buildFixtureDb(fixture);
  const prompt = writePrompt(dir, 'p.txt', '任务内容 R3C');
  const page = new FakePage({ modelLabel: 'GLM-Test', modeLabel: '' });
  const args = submitArgs(dir, { promptFile: prompt, workspace: ws });
  args['ready-timeout-ms'] = 200;
  await assert.rejects(
    () => driver.__internalsForTest.cmdSubmit(args, makeDeps(page, fixture, ws)),
    e => { assert.equal(e.code, 'CONFIG_NOT_READY'); assert.ok(/mode/.test(e.message)); return true; }
  );
  assert.equal(page.sendClicks, 0);
});

test('follow-up：模型占位 → CONFIG_NOT_READY 拒绝，不点击', async () => {
  const dir = tmpDir();
  const ws = '/tmp/zgui-ws-r3d';
  const fixture = path.join(dir, 'n.sqlite');
  const db = buildFixtureDb(fixture);
  seedReceivedTurn(db, {
    sessionId: 'sess_fu3', directory: ws, inputId: 'in_fu3', marker: 'ZGUI-M-ORIG-44444444',
    userMsgId: 'msg_fu3', assistantMsgs: [{ id: 'msg_a4', parts: [{ type: 'text', text: '首版' }] }],
  });
  const statePath = path.join(dir, 'state.json');
  driver.writeStateAtomic(statePath, {
    schema: 1, url: 'http://127.0.0.1:18490/', workspace: ws, taskId: 'T3',
    prompt: { sha256: 'e'.repeat(64), marker: 'ZGUI-M-ORIG-44444444' },
    phase: 'sent-bound',
    binding: { sessionId: 'sess_fu3', inputId: 'in_fu3' },
    followUps: {},
  });
  const fuPrompt = writePrompt(dir, 'fu.txt', '反馈 R3D');
  const page = new FakePage({ openSessionId: 'sess_fu3', openRows: ['ZGUI-M-ORIG-44444444 首版'], modelLabel: '管理模型' });
  const args = { state: statePath, 'prompt-file': fuPrompt, 'input-id': 'FU-R3', 'ready-timeout-ms': 200, 'restore-wait-ms': 200 };
  await assert.rejects(
    () => driver.__internalsForTest.cmdFollowUp(args, makeDeps(page, fixture, ws)),
    e => { assert.equal(e.code, 'CONFIG_NOT_READY'); return true; }
  );
  assert.equal(page.sendClicks, 0, 'follow-up 未盲发');
});

test('inspect：模型占位 → status=not-ready 且不作为有效配置', async () => {
  const dir = tmpDir();
  const page = new FakePage({ modelLabel: '管理模型' });
  const deps = makeDeps(page, '/nonexistent.sqlite', '/tmp/x');
  const r = await captureEmit(() => driver.__internalsForTest.cmdInspect(
    { url: 'http://127.0.0.1:18490/', 'ready-timeout-ms': 0 }, deps));
  assert.equal(r.json.ok, true);
  assert.equal(r.json.status, 'not-ready');
  assert.equal(r.json.configReady, false);
  assert.equal(r.json.concreteModel, null);
  assert.ok(r.json.configIssue && /默认模型/.test(r.json.configIssue.hint));
});

test('绑定目录错配：BINDING_MISMATCH 且不重试', async () => {
  const dir = tmpDir();
  const ws = '/tmp/zgui-ws5';
  const fixture = path.join(dir, 'native.sqlite');
  const db = buildFixtureDb(fixture);
  const prompt = writePrompt(dir, 'p.txt', '任务内容 Y');
  const page = new FakePage({
    onSendClick: async (typed, pg) => {
      const m = /\[ZGUI-M-[^\]]+\]/.exec(typed);
      seedReceivedTurn(db, {
        sessionId: 'sess_w5', directory: '/tmp/WRONG-ws', inputId: 'in_w5', marker: m[0].slice(1, -1),
        userMsgId: 'msg_uw5', assistantMsgs: [],
      });
      pg.rows.push({ text: typed });
    },
  });
  const deps = makeDeps(page, fixture, ws);
  const args = submitArgs(dir, { promptFile: prompt, workspace: ws, timeoutMs: 1200 });
  await assert.rejects(
    () => driver.__internalsForTest.cmdSubmit(args, deps),
    e => { assert.equal(e.code, 'BINDING_MISMATCH'); return true; }
  );
  assert.equal(page.sendClicks, 1, '错配后不重发');
  const st = driver.readState(args.state);
  assert.equal(st.phase, 'intent', '错配时停留在 intent（已点击但未绑定），绝不升级为已发送可重投');
});

test('composer 非空 → 拒绝写入（不碰他人草稿）', async () => {
  const dir = tmpDir();
  const ws = '/tmp/zgui-ws6';
  const fixture = path.join(dir, 'native.sqlite');
  buildFixtureDb(fixture);
  const prompt = writePrompt(dir, 'p.txt', '任务内容 Z');
  const page = new FakePage();
  page.draft = '别人未发送的草稿内容';
  const deps = makeDeps(page, fixture, ws);
  const args = submitArgs(dir, { promptFile: prompt, workspace: ws });
  await assert.rejects(
    () => driver.__internalsForTest.cmdSubmit(args, deps),
    e => { assert.equal(e.code, 'COMPOSER_NOT_EMPTY'); return true; }
  );
  assert.equal(page.sendClicks, 0);
  assert.equal(page.draft, '别人未发送的草稿内容', '草稿原样保留');
});

test('follow-up：每轮去重，同 input-id 不二次点击；不同 prompt 同 id 拒绝', async () => {
  const dir = tmpDir();
  const ws = '/tmp/zgui-ws7';
  const fixture = path.join(dir, 'native.sqlite');
  const db = buildFixtureDb(fixture);
  // 原任务已绑定
  const originalMarker = 'ZGUI-M-ORIG-11111111';
  seedReceivedTurn(db, {
    sessionId: 'sess_fu', directory: ws, inputId: 'in_fu0', marker: originalMarker,
    userMsgId: 'msg_fu0',
    assistantMsgs: [{ id: 'msg_fuA', parts: [{ type: 'text', text: '首版交付' }] }],
  });
  const statePath = path.join(dir, 'state.json');
  driver.writeStateAtomic(statePath, {
    schema: 1, url: 'http://127.0.0.1:18490/', workspace: ws, taskId: 'TASK-FU',
    prompt: { sha256: 'b'.repeat(64), marker: originalMarker },
    phase: 'sent-bound',
    binding: { sessionId: 'sess_fu', inputId: 'in_fu0' },
    followUps: {},
  });
  const fuPrompt = writePrompt(dir, 'fu.txt', '窄反馈：修复问题1。');
  const fuPrompt2 = writePrompt(dir, 'fu2.txt', '不同的反馈内容。');

  const page = new FakePage({
    openSessionId: 'sess_fu',
    openRows: [`任务内容 ${originalMarker}`, '首版交付'],
    onSendClick: async (typed, pg) => {
      const m = /\[ZGUI-F-[^\]]+\]/.exec(typed);
      const marker = m[0].slice(1, -1);
      insertInput(db, { id: 'in_fu1_' + marker.slice(-4), sessionId: 'sess_fu', text: `反馈 ${marker}`, promotedMessageId: 'msg_fu1' + marker.slice(-4) });
      pg.rows.push({ text: typed });
    },
  });
  const deps = makeDeps(page, fixture, ws);
  const args = { state: statePath, 'prompt-file': fuPrompt, 'input-id': 'FU-1', 'timeout-ms': 1500 };

  const r1 = await captureEmit(() => driver.__internalsForTest.cmdFollowUp({ ...args }, deps));
  assert.equal(r1.json.ok, true, JSON.stringify(r1.json));
  assert.equal(r1.json.status, 'sent-bound');
  assert.equal(r1.json.sessionId, 'sess_fu');
  assert.equal(page.sendClicks, 1);

  // 同 input-id 再来：对账该轮自身，不点击
  const page2 = new FakePage({});
  const r2 = await captureEmit(() => driver.__internalsForTest.cmdFollowUp({ ...args }, makeDeps(page2, fixture, ws)));
  assert.equal(page2.sendClicks, 0, '同 input-id 重复调用绝不点击');
  assert.equal(r2.json.status, 'reconciled');

  // 同 input-id 换 prompt → 冲突
  await assert.rejects(
    () => driver.__internalsForTest.cmdFollowUp({ ...args, 'prompt-file': fuPrompt2 }, deps),
    e => { assert.equal(e.code, 'STATE_FINGERPRINT_CONFLICT'); return true; }
  );

  // observe --input-id FU-1 能看到该轮绑定
  const r3 = await captureEmit(() => driver.__internalsForTest.cmdObserve(
    { state: statePath, 'input-id': 'FU-1', _: ['observe'] }, makeDeps(new FakePage(), fixture, ws)));
  assert.equal(r3.json.ok, true);
  assert.ok(r3.json.inputId.startsWith('in_fu1_'), JSON.stringify(r3.json));
});

test('follow-up：目标会话不在 sidebar → UNSUPPORTED（不点其他任务）', async () => {
  const dir = tmpDir();
  const ws = '/tmp/zgui-ws8';
  const fixture = path.join(dir, 'native.sqlite');
  buildFixtureDb(fixture);
  const statePath = path.join(dir, 'state.json');
  driver.writeStateAtomic(statePath, {
    schema: 1, url: 'http://127.0.0.1:18490/', workspace: ws, taskId: 'TASK-FU2',
    prompt: { sha256: 'c'.repeat(64), marker: 'ZGUI-M-ORIG-22222222' },
    phase: 'sent-bound',
    binding: { sessionId: 'sess_missing', inputId: 'in_x' },
    followUps: {},
  });
  const fuPrompt = writePrompt(dir, 'fu.txt', '反馈内容');
  const page = new FakePage({ openSessionId: null }); // task-item 不存在
  const deps = makeDeps(page, fixture, ws);
  const r = await captureEmit(() => driver.__internalsForTest.cmdFollowUp(
    { state: statePath, 'prompt-file': fuPrompt, 'input-id': 'FU-9', 'restore-wait-ms': 200 }, deps));
  assert.equal(r.json.ok, true);
  assert.equal(r.json.status, 'unsupported');
  assert.ok(/task-item-sess_missing/.test(r.json.reason));
  assert.equal(page.sendClicks, 0);
});

test('observe：state 缺失 fail-closed；崩溃恢复 intent → 绑定升级', async () => {
  const dir = tmpDir();
  const ws = '/tmp/zgui-ws9';
  const fixture = path.join(dir, 'native.sqlite');
  const db = buildFixtureDb(fixture);
  // 缺失
  await assert.rejects(
    () => driver.__internalsForTest.cmdObserve({ state: path.join(dir, 'none.json'), _: ['observe'] }),
    e => { assert.equal(e.code, 'STATE_MISSING'); return true; }
  );
  // intent + DB 已有行 → 恢复绑定
  const marker = 'ZGUI-M-REC-33333333';
  seedReceivedTurn(db, {
    sessionId: 'sess_rec', directory: ws, inputId: 'in_rec', marker,
    userMsgId: 'msg_urec',
    assistantMsgs: [{ id: 'msg_arec', parts: [{ type: 'text', text: '崩溃前已完成的回复' }] }],
  });
  const statePath = path.join(dir, 'state.json');
  driver.writeStateAtomic(statePath, {
    schema: 1, url: 'http://127.0.0.1:18490/', workspace: ws, taskId: 'TASK-REC',
    prompt: { sha256: 'd'.repeat(64), marker },
    phase: 'intent',
    followUps: {},
  });
  const r = await captureEmit(() => driver.__internalsForTest.cmdObserve(
    { state: statePath, _: ['observe'] }, makeDeps(new FakePage(), fixture, ws)));
  assert.equal(r.json.ok, true);
  assert.equal(r.json.phase, 'sent-bound-recovered');
  assert.equal(r.json.inputId, 'in_rec');
  const st = driver.readState(statePath);
  assert.equal(st.phase, 'sent-bound-recovered');
});

test('原子写：不残留 tmp 文件；内容即时可读', () => {
  const dir = tmpDir();
  const sp = path.join(dir, 's.json');
  driver.writeStateAtomic(sp, { schema: 1, hello: 'world' });
  driver.writeStateAtomic(sp, { schema: 1, hello: 'world2' });
  const files = fs.readdirSync(dir).filter(f => f.includes('.tmp-'));
  assert.equal(files.length, 0, '无 tmp 残留');
  assert.equal(JSON.parse(fs.readFileSync(sp, 'utf8')).hello, 'world2');
});

test('PM 回归：服务默认目录已显示注册项目标签，不能误报无项目', async () => {
  const dir=tmpDir(), ws='/tmp/legal-skills', fixture=path.join(dir,'native.sqlite');
  const db=buildFixtureDb(fixture);
  const prompt=writePrompt(dir,'prompt.txt','本任务只用于fixture');
  const page=new FakePage({wsLabel:'legal-skills',onSendClick:async(typed,pg)=>{
    const marker=typed.match(/\[(ZGUI-M-[^\]]+)\]/)[1];
    seedReceivedTurn(db,{sessionId:'sess_project',directory:ws,inputId:'input_project',marker,userMsgId:'msg_project',assistantMsgs:[]});
    pg.rows.push({text:typed});
  }});
  const deps=makeDeps(page,fixture,ws);
  deps.fetchServerInfo=async()=>({workspaces:[{path:ws,label:'legal-skills'}]});
  const r=await captureEmit(()=>driver.__internalsForTest.cmdSubmit(submitArgs(dir,{workspace:ws,promptFile:prompt}),deps));
  assert.equal(r.json.status,'sent-bound');assert.equal(r.json.page.wsAction,'already-selected');assert.equal(page.sendClicks,1);db.close();
});

test('PM 回归：最后助手消息含 error，不能作为成功最终文本',()=>{
  const dir=tmpDir(),fixture=path.join(dir,'native.sqlite'),db=buildFixtureDb(fixture),marker='PM_ERROR_MARKER';
  seedReceivedTurn(db,{sessionId:'sess_error',directory:'/tmp/ws',inputId:'in_error',marker,userMsgId:'msg_error',assistantMsgs:[{id:'assistant_error',parts:[{type:'text',text:'部分文本'}]}]});
  db.prepare("UPDATE message SET data=json_set(data,'$.error',json(?)) WHERE id=?").run('{"name":"TestError"}','assistant_error');
  const st=driver.collectStatus({workspace:'/tmp/ws',prompt:{marker},binding:{sessionId:'sess_error',inputId:'in_error'}},fixture);
  assert.equal(st.finalText,null);db.close();
});

// ===========================================================================
// R2 增测（ZREMOTE_DRIVER_REVISION_R2_20261002）— prompt 单次读取修复回归
//
// 修复合同（r2/zcode-browser-driver.cjs）：cmdSubmit / cmdFollowUp 对 prompt
// 只做一次 readFileSync（原始 Buffer），SHA256 与 toString('utf8') 正文取自
// 同一 Buffer；SHA 按原始字节计算。本组测试走真实命令路径
// （__internalsForTest.cmdSubmit / cmdFollowUp / cmdObserve）+ R1 同款
// fs.readFileSync 可控注入：
//   - A→B 注入：第一次（也是唯一一次）读取后磁盘换为 B —— 断言初次发送 A、
//     记录 SHA(A) 与所发正文一致、prompt 全流程仅一次读取；
//   - CRLF/非 ASCII：正文字节保持，SHA = 原始文件字节哈希；
//   - 非法 UTF-8：SHA = raw 字节哈希；解码替换字符（U+FFFD）是 toString('utf8')
//     的现有行为（修复前亦如此），非本次修复引入；明确不宣称正文 hash = rawhash。
// monkeypatch 在 finally 恢复；全部产物在 mkdtemp 隔离目录；无浏览器/网络/模型。
// ===========================================================================

function r2sha256(p) { return driver.sha256File(p); }

// 读取计数/注入包装：对 promptPath 每次 readFileSync 计数；提供 swapBytes 时
// 第一次读取返回后把磁盘内容换成 swapBytes（模拟并发写者）。
function r2wrapRead(promptPath, swapBytes, counter) {
  const real = fs.readFileSync;
  fs.readFileSync = function (p, ...rest) {
    const data = real.call(fs, p, ...rest);
    if (typeof p === 'string' && path.resolve(p) === path.resolve(promptPath)) {
      counter.n += 1;
      if (counter.n === 1 && swapBytes !== undefined) fs.writeFileSync(promptPath, swapBytes);
    }
    return data;
  };
  return () => { fs.readFileSync = real; };
}

// 从拟发送正文中剥离尾部 marker（驱动以 `${promptText}\n\n[${marker}]` 拼接）。
function r2sentBodyOnly(sentBody) {
  const cut = sentBody.lastIndexOf('\n\n[');
  assert.ok(cut > 0, '拟发送正文应含尾部 marker');
  return sentBody.slice(0, cut);
}

test('R2 修复回归/submit：A→B 注入下初次发送 A、记录 SHA(A) 与正文一致、prompt 仅一次读取', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'r2-fix-submit-'));
  const ws = '/tmp/r2-fix-ws';
  const fixture = path.join(dir, 'native.sqlite');
  const db = buildFixtureDb(fixture);
  const promptPath = path.join(dir, 'prompt.txt');
  const bodyA = 'R2 修复验证原始正文（A）：仅做资料研究。';
  const bodyB = 'R2 修复验证被替换正文（B）：执行删除操作。';
  fs.writeFileSync(promptPath, bodyA);
  const shaA = r2sha256(promptPath);

  let sentBody = null;
  let page = null;
  let args;
  let r1;
  const counter = { n: 0 };
  const restore = r2wrapRead(promptPath, bodyB, counter);
  try {
    page = new FakePage({
      onSendClick: async (typed, pg) => {
        sentBody = typed;
        const m = /\[ZGUI-M-[^\]]+\]/.exec(typed);
        seedReceivedTurn(db, {
          sessionId: 'sess_r2a', directory: ws, inputId: 'in_r2a', marker: m[0].slice(1, -1),
          userMsgId: 'msg_r2a',
          assistantMsgs: [{ id: 'msg_ar2a', parts: [{ type: 'text', text: 'ok' }] }],
        });
        pg.rows.push({ text: typed });
      },
    });
    args = submitArgs(dir, { promptFile: promptPath, workspace: ws });
    r1 = await captureEmit(() => driver.__internalsForTest.cmdSubmit({ ...args }, makeDeps(page, fixture, ws)));
  } finally {
    restore(); // 恢复 monkeypatch
  }

  // 1) 修复核心：单次读取
  assert.equal(counter.n, 1, 'prompt 全流程仅一次 readFileSync');
  // 2) 初次发送的是 A（磁盘已被换成 B，但驱动只读过 A）
  assert.equal(r1.json.ok, true, JSON.stringify(r1.json));
  assert.equal(r1.json.status, 'sent-bound');
  assert.equal(r1.exitCode, 0);
  assert.equal(page.sendClicks, 1, '恰好一次点击');
  assert.ok(sentBody && sentBody.startsWith(bodyA), '实际发送正文 = A（读取时刻内容）');
  assert.ok(!sentBody.startsWith(bodyB), '实际发送正文不是替换后的 B');
  // 3) 记录与正文一致：SHA(A) === 所发正文哈希 === state 记录
  const sentPath = path.join(dir, 'sent-body.txt');
  fs.writeFileSync(sentPath, r2sentBodyOnly(sentBody));
  const sentSha = r2sha256(sentPath);
  const st = driver.readState(args.state);
  assert.equal(st.prompt.sha256, shaA, 'state 记录 SHA(A)');
  assert.equal(sentSha, shaA, '实际发送正文哈希 = SHA(A)');
  assert.equal(sentSha, st.prompt.sha256, '记录 SHA 与实际发送正文一致（修复目标）');
  // 4) 竞态确实发生（磁盘已是 B），驱动免疫
  assert.notEqual(r2sha256(promptPath), shaA, '注入确实把磁盘换成 B');
  // 5) 重放：磁盘 B 与记录 SHA(A) 指纹不符 → 正确拒绝（fail-closed 且记录可信）
  await assert.rejects(
    () => driver.__internalsForTest.cmdSubmit({ ...args }, makeDeps(new FakePage(), fixture, ws)),
    e => { assert.equal(e.code, 'STATE_FINGERPRINT_CONFLICT'); return true; }
  );
  // 6) observe 对账：A 正文任务照常交付
  const r2 = await captureEmit(() => driver.__internalsForTest.cmdObserve(
    { state: args.state, _: ['observe'] }, makeDeps(new FakePage(), fixture, ws)));
  assert.equal(r2.json.ok, true, JSON.stringify(r2.json));
  assert.equal(r2.json.status, 'reconciled');
  assert.equal(r2.json.finalTextAvailability, 'available');
  db.close();
});

test('R2 修复回归/follow-up：A→B 注入下初次发送 A、followUps 记录 SHA(A) 与正文一致、仅一次读取', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'r2-fix-fu-'));
  const ws = '/tmp/r2-fix-fu-ws';
  const fixture = path.join(dir, 'native.sqlite');
  const db = buildFixtureDb(fixture);
  const originalMarker = 'ZGUI-M-R2ORIG-87654321';
  seedReceivedTurn(db, {
    sessionId: 'sess_r2fu', directory: ws, inputId: 'in_r2fu0', marker: originalMarker,
    userMsgId: 'msg_r2fu0',
    assistantMsgs: [{ id: 'msg_r2fuA', parts: [{ type: 'text', text: '首版交付' }] }],
  });
  const statePath = path.join(dir, 'state.json');
  driver.writeStateAtomic(statePath, {
    schema: 1, url: 'http://127.0.0.1:18490/', workspace: ws, taskId: 'R2-FU',
    prompt: { sha256: 'e'.repeat(64), marker: originalMarker },
    phase: 'sent-bound',
    binding: { sessionId: 'sess_r2fu', inputId: 'in_r2fu0' },
    followUps: {},
  });
  const fuPath = path.join(dir, 'fu.txt');
  const bodyA2 = 'R2 反馈原始稿（A）：请补充第一节。';
  const bodyB2 = 'R2 反馈被换稿（B）：请删除全部内容。';
  fs.writeFileSync(fuPath, bodyA2);
  const shaA2 = r2sha256(fuPath);

  let fuSentBody = null;
  let page = null;
  let r;
  const fuArgs = { state: statePath, 'prompt-file': fuPath, 'input-id': 'R2-FU-1', 'timeout-ms': 1500 };
  const counter = { n: 0 };
  const restore = r2wrapRead(fuPath, bodyB2, counter);
  try {
    page = new FakePage({
      openSessionId: 'sess_r2fu',
      openRows: [`任务内容 ${originalMarker}`, '首版交付'],
      onSendClick: async (typed, pg) => {
        fuSentBody = typed;
        const m = /\[ZGUI-F-[^\]]+\]/.exec(typed);
        insertInput(db, { id: 'in_r2fu1', sessionId: 'sess_r2fu', text: `反馈 ${m[0].slice(1, -1)}`, promotedMessageId: 'msg_r2fu1' });
        pg.rows.push({ text: typed });
      },
    });
    r = await captureEmit(() => driver.__internalsForTest.cmdFollowUp({ ...fuArgs }, makeDeps(page, fixture, ws)));
  } finally {
    restore(); // 恢复 monkeypatch
  }

  assert.equal(counter.n, 1, 'follow-up prompt 全流程仅一次 readFileSync（修复核心）');
  assert.equal(r.json.ok, true, JSON.stringify(r.json));
  assert.equal(r.json.status, 'sent-bound');
  assert.equal(r.exitCode, 0);
  assert.equal(page.sendClicks, 1, 'follow-up 恰好一次点击');
  assert.ok(fuSentBody && fuSentBody.startsWith(bodyA2), '实际发送正文 = A（读取时刻内容）');
  assert.ok(!fuSentBody.startsWith(bodyB2), '实际发送正文不是替换后的 B');
  const sentPath = path.join(dir, 'sent-body.txt');
  fs.writeFileSync(sentPath, r2sentBodyOnly(fuSentBody));
  const st = driver.readState(statePath);
  assert.equal(st.followUps['R2-FU-1'].prompt.sha256, shaA2, 'followUps 记录 SHA(A)');
  assert.equal(r2sha256(sentPath), shaA2, '实际发送正文哈希 = SHA(A)（记录与正文一致）');
  assert.notEqual(r2sha256(fuPath), shaA2, '注入确实把磁盘换成 B');
  await assert.rejects(
    () => driver.__internalsForTest.cmdFollowUp({ ...fuArgs }, makeDeps(new FakePage(), fixture, ws)),
    e => { assert.equal(e.code, 'STATE_FINGERPRINT_CONFLICT'); return true; }
  );
  db.close();
});

test('R2 回归/字节保持：CRLF 与非 ASCII 正文原样发送，SHA 与记录按原始字节一致', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'r2-bytes-'));
  const ws = '/tmp/r2-bytes-ws';
  const fixture = path.join(dir, 'native.sqlite');
  const db = buildFixtureDb(fixture);
  const promptPath = path.join(dir, 'prompt.txt');
  const body = 'R2 字节保持第一行\r\n第二行：中文、全角（：）、emoji 🎯。\r\n第三行制表符:\tEND';
  fs.writeFileSync(promptPath, body, 'utf8');
  const shaFile = r2sha256(promptPath); // 原始文件字节哈希

  let sentBody = null;
  let page = null;
  let args;
  let r;
  const counter = { n: 0 };
  const restore = r2wrapRead(promptPath, undefined, counter); // 只计数，不换内容
  try {
    page = new FakePage({
      onSendClick: async (typed, pg) => {
        sentBody = typed;
        const m = /\[ZGUI-M-[^\]]+\]/.exec(typed);
        seedReceivedTurn(db, {
          sessionId: 'sess_r2b', directory: ws, inputId: 'in_r2b', marker: m[0].slice(1, -1),
          userMsgId: 'msg_r2b',
          assistantMsgs: [{ id: 'msg_ar2b', parts: [{ type: 'text', text: 'ok' }] }],
        });
        pg.rows.push({ text: typed });
      },
    });
    args = submitArgs(dir, { promptFile: promptPath, workspace: ws });
    r = await captureEmit(() => driver.__internalsForTest.cmdSubmit({ ...args }, makeDeps(page, fixture, ws)));
  } finally {
    restore();
  }

  assert.equal(counter.n, 1, 'prompt 仅一次读取');
  assert.equal(r.json.ok, true, JSON.stringify(r.json));
  assert.equal(r.json.status, 'sent-bound');
  assert.equal(page.sendClicks, 1);
  // 合法 UTF-8（含 CRLF/非 ASCII）解码→再编码往返无损：正文（剥 marker）与原文件字节哈希一致
  const sentPath = path.join(dir, 'sent-body.txt');
  fs.writeFileSync(sentPath, r2sentBodyOnly(sentBody), 'utf8');
  assert.equal(r2sha256(sentPath), shaFile, 'CRLF/非 ASCII 正文字节原样保持');
  const st = driver.readState(args.state);
  assert.equal(st.prompt.sha256, shaFile, '记录 SHA = 原始字节哈希');
  db.close();
});

test('R2 回归/非法 UTF-8：SHA 按 raw 字节计算；解码替换字符是现有行为，正文哈希≠rawhash', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'r2-raw-'));
  const ws = '/tmp/r2-raw-ws';
  const fixture = path.join(dir, 'native.sqlite');
  const db = buildFixtureDb(fixture);
  const promptPath = path.join(dir, 'prompt.txt');
  // 含非法 UTF-8 序列：0xFF、0xFE、截断双字节 0xC3 0x28
  const raw = Buffer.concat([
    Buffer.from('R2 raw 前缀 ', 'utf8'),
    Buffer.from([0xFF, 0xFE, 0xC3, 0x28]),
    Buffer.from(' 后缀', 'utf8'),
  ]);
  fs.writeFileSync(promptPath, raw);
  const rawSha = r2sha256(promptPath); // 原始字节哈希

  let sentBody = null;
  let page = null;
  let args;
  let r;
  const counter = { n: 0 };
  const restore = r2wrapRead(promptPath, undefined, counter);
  try {
    page = new FakePage({
      onSendClick: async (typed, pg) => {
        sentBody = typed;
        const m = /\[ZGUI-M-[^\]]+\]/.exec(typed);
        seedReceivedTurn(db, {
          sessionId: 'sess_r2c', directory: ws, inputId: 'in_r2c', marker: m[0].slice(1, -1),
          userMsgId: 'msg_r2c',
          assistantMsgs: [{ id: 'msg_ar2c', parts: [{ type: 'text', text: 'ok' }] }],
        });
        pg.rows.push({ text: typed });
      },
    });
    args = submitArgs(dir, { promptFile: promptPath, workspace: ws });
    r = await captureEmit(() => driver.__internalsForTest.cmdSubmit({ ...args }, makeDeps(page, fixture, ws)));
  } finally {
    restore();
  }

  assert.equal(counter.n, 1, 'prompt 仅一次读取');
  assert.equal(r.json.ok, true, JSON.stringify(r.json));
  assert.equal(r.json.status, 'sent-bound');
  assert.equal(page.sendClicks, 1);
  const st = driver.readState(args.state);
  assert.equal(st.prompt.sha256, rawSha, '记录 SHA = 原始字节（raw）哈希，不随解码改变');
  // 现有解码行为声明：toString('utf8') 对非法序列产生 U+FFFD 替换字符（修复前亦如此），非本次修复引入
  assert.ok(sentBody.includes('\uFFFD'), '正文含 U+FFFD（现有解码行为）');
  const sentPath = path.join(dir, 'sent-body.txt');
  fs.writeFileSync(sentPath, r2sentBodyOnly(sentBody), 'utf8');
  assert.notEqual(r2sha256(sentPath), rawSha, '不宣称正文 hash = rawhash：替换字符再编码与原始字节不同（现有行为）');
  db.close();
});
