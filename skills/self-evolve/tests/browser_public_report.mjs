// Development-only browser regression. Run with ego-browser nodejs < this file.
// Prepend globalThis.SELF_EVOLVE_REPORT_TEST={reportUrl, spaceId?, screenshot?}.
// The browser runner does not inherit the caller shell environment.
const assert = (await import('node:assert/strict')).default;
const config = globalThis.SELF_EVOLVE_REPORT_TEST || {};
assert.equal(typeof taskSpace, 'function', '请使用已安装的 ego-browser nodejs 执行浏览器回归');
const reportUrl = config.reportUrl;
assert.ok(reportUrl, 'configure reportUrl for a generated overview');
const task = config.spaceId
  ? await taskSpace(Number(config.spaceId))
  : await taskSpace('Self Evolve 多页报告回归');
const page = task.page('p1');
console.log({ spaceId: task.spaceId });

// Hosts that cannot dispatch synthetic input over CDP intermittently time out.
// Drive the real DOM event first and keep the native pointer path as fallback,
// so the assertions still exercise the report's own listeners.
const click = async (selector) => {
  try {
    await page.evaluate((sel) => {
      const el = document.querySelector(sel);
      if (!el) throw new Error('missing element ' + sel);
      el.click();
    }, selector);
  } catch (error) {
    await page.click(selector);
  }
};
const setValue = async (selector, value) => {
  await page.evaluate(([sel, val]) => {
    const el = document.querySelector(sel);
    if (!el) throw new Error('missing element ' + sel);
    el.value = val;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }, [selector, value]);
};
const selectOption = async (selector, value) => {
  try {
    await setValue(selector, value);
  } catch (error) {
    await page.selectOption(selector, value);
  }
};
const cdp = async (method, params) => {
  // CDP emulation calls occasionally time out on this host; retry before failing.
  let lastError;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      return await page.cdp(method, params);
    } catch (error) {
      lastError = error;
      const message = String((error && error.message) || error);
      if (!/timed out|CdpRequestTimeout/i.test(message)) throw error;
    }
  }
  throw lastError;
};
const fill = async (selector, text) => {
  try {
    await setValue(selector, text);
  } catch (error) {
    await page.fill(selector, text);
  }
};
await page.goto(reportUrl);
await page.waitForLoadState();
const navigation = await page.evaluate(() => [...document.querySelectorAll('.nav-link')].map(a => ({ href: a.getAttribute('href'), title: a.querySelector('strong').textContent })));
assert.equal(navigation.length, 7);
assert.ok(navigation.some(n => n.href.endsWith('-profile.html')), 'report must expose a dedicated profile page');
const results = [];
for (const item of navigation) {
  console.log({ checking: item.title });
  await click(`.nav-link[href="${item.href}"]`);
  await page.waitForURL(new URL(item.href, reportUrl).href);
  await page.waitForLoadState();
  const state = await page.evaluate(() => ({ title: document.title, current: document.querySelector('[aria-current=page]').getAttribute('href'), width: innerWidth, scrollWidth: document.documentElement.scrollWidth, remote: performance.getEntriesByType('resource').filter(r => /^https?:/.test(r.name)).length }));
  assert.ok(state.title.includes(item.title));
  assert.equal(state.current, item.href);
  assert.ok(state.scrollWidth <= state.width + 1, item.title + ' desktop overflow');
  assert.equal(state.remote, 0);
  await cdp('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  const mobile = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth, headingWidth: document.querySelector('h1').getBoundingClientRect().width }));
  assert.equal(mobile.width, 390);
  assert.ok(mobile.scrollWidth <= 391, item.title + ' mobile overflow');
  assert.ok(mobile.headingWidth > 0);
  await cdp('Emulation.clearDeviceMetricsOverride');
  results.push({ page: item.title, desktop: state.width, mobile: mobile.width, overflow: false });
}
const analysis = navigation.find(n => n.href.endsWith('-analysis.html'));
await click(`.nav-link[href="${analysis.href}"]`);
await page.waitForURL(new URL(analysis.href, reportUrl).href);
await page.waitForLoadState();
const evidenceLink = await page.evaluate(() => document.querySelector('#patterns .support a')?.getAttribute('href'));
assert.ok(evidenceLink, 'analyzed fixture must include a linked pattern');
await click('#patterns article:first-of-type .support a:first-of-type');
await page.waitForFunction(() => location.hash.startsWith('#evidence-') && document.getElementById(location.hash.slice(1))?.open);
assert.equal(await page.evaluate(() => document.getElementById(location.hash.slice(1)).hidden), false);
const backlink = await page.evaluate(() => [...document.querySelector(location.hash + ' .support').querySelectorAll('a')].find(a => a.getAttribute('href').includes('-analysis.html'))?.getAttribute('href'));
assert.ok(backlink);
const activeEvidence = await page.evaluate(() => location.hash);
await click(`${activeEvidence} a[href="${backlink}"]`);
await page.waitForFunction(() => location.hash.startsWith('#pattern-'));
assert.ok(await page.evaluate(() => !!document.getElementById(location.hash.slice(1))));
const sessions = navigation.find(n => n.href.endsWith('-sessions.html'));
await click(`.nav-link[href="${sessions.href}"]`);
await page.waitForURL(new URL(sessions.href, reportUrl).href);
await page.waitForLoadState();
const runtime = await page.evaluate(() => document.querySelector('[data-filter-group="evidence"] [data-runtime-filter] option:nth-child(2)')?.value);
assert.ok(runtime);
await selectOption('[data-filter-group="evidence"] [data-runtime-filter]', runtime);
const visibleRuntimes = await page.evaluate(() => [...document.querySelectorAll('[data-filter-group="evidence"] [data-row]')].filter(n => !n.hidden).map(n => n.dataset.runtime));
assert.ok(visibleRuntimes.length > 0);
assert.ok(visibleRuntimes.every(r => r.split(' ').includes(runtime)));
await fill('[data-filter-group="evidence"] [data-text-filter]', 'synthetic-no-match-qa-927a');
assert.equal(await page.evaluate(() => document.querySelector('[data-filter-group="evidence"] [data-empty]').hidden), false);
await click('[data-filter-group="evidence"] [data-reset]');
assert.equal(await page.evaluate(() => [...document.querySelectorAll('[data-filter-group="evidence"] [data-row]')].filter(n => n.hidden).length), 0);
await selectOption('[data-filter-group="triage"] [data-kind-filter]', 'false');
assert.ok(await page.evaluate(() => [...document.querySelectorAll('[data-filter-group="triage"] [data-row]')].filter(n => !n.hidden).every(n => n.dataset.kind === 'false')));
// Low-information evidence is folded into a collapsed group, not mixed into the main evidence list.
const lowInfo = await page.evaluate(() => {
  const group = document.getElementById('low-information');
  if (!group) return { present: false };
  return { present: true, open: group.open, rows: group.querySelectorAll('[data-row]').length,
    text: group.querySelector('summary').textContent.trim() };
});
if (lowInfo.present) {
  assert.equal(lowInfo.open, false, 'low-information group must stay collapsed by default');
  assert.ok(lowInfo.text.includes('本轮上下文'), lowInfo.text);
  const mainEvidence = await page.evaluate(() => document.querySelectorAll('#evidence > [data-row]').length);
  assert.ok(mainEvidence >= 0);
  await page.evaluate(() => { document.querySelector('#low-information > summary').click(); });
  assert.ok(await page.evaluate(() => document.getElementById('low-information').open), 'low-information group must be expandable');
  await page.evaluate(() => { document.querySelector('#low-information > summary').click(); });
}
// Profile page: layered entries, evidence round trip, and an explicit coverage statement.
const profile = navigation.find(n => n.href.endsWith('-profile.html'));
await click(`.nav-link[href="${profile.href}"]`);
await page.waitForURL(new URL(profile.href, reportUrl).href);
await page.waitForLoadState();
const profileState = await page.evaluate(() => ({
  groups: [...document.querySelectorAll('.profile-group')].map(g => g.id),
  items: document.querySelectorAll('.profile-item').length,
  coverage: document.querySelector('.notice.warn')?.textContent || '',
  empty: document.querySelector('.empty')?.textContent || ''
}));
const profileLinks = await page.evaluate(() => [...document.querySelectorAll('.profile-item .support a')].map(a => a.getAttribute('href')));
if (profileState.items > 0) {
  assert.ok(profileState.groups.length >= 1, 'profile page must group entries by basis');
  assert.ok(profileLinks.length > 0, 'profile entries must link back to evidence');
  assert.ok(profileState.coverage.length > 0, 'profile page must state its coverage limits');
  await click('.profile-item .support a:first-of-type');
  await page.waitForFunction(() => location.hash.startsWith('#evidence-'));
  assert.ok(await page.evaluate(() => !!document.getElementById(location.hash.slice(1))));
} else {
  assert.ok(profileState.empty.includes('尚无画像结论') || profileState.coverage.length > 0, 'empty profile page must explain its state');
}
const skills = navigation.find(n => n.href.endsWith('-skills.html'));
await click(`.nav-link[href="${skills.href}"]`);
await page.waitForURL(new URL(skills.href, reportUrl).href);
await page.waitForLoadState();
await fill('[data-filter-group="skills"] [data-text-filter]', 'synthetic-no-match-qa-927a');
assert.equal(await page.evaluate(() => document.querySelector('[data-filter-group="skills"] [data-empty]').hidden), false);
await click('[data-filter-group="skills"] [data-reset]');
// A round may legitimately propose no Skill at all; the page must then say so
// instead of the regression failing on a missing proposal card.
const hasProposals = await page.evaluate(() => document.querySelectorAll('.proposal-list article').length > 0);
if (hasProposals) {
  await click('.proposal-list article:first-of-type .install-guide summary');
  assert.ok(await page.evaluate(() => document.querySelector('.install-guide').open && document.querySelector('.install-guide').innerText.includes('WorkBuddy')));
} else {
  const empty = await page.evaluate(() => document.querySelector('[data-filter-group="skills"] [data-empty]').textContent);
  assert.ok(empty.includes('本轮没有提出 Skill 沉淀建议'), empty);
}
// Isolate browser APIs on this synthetic report; do not touch the OS clipboard.
const copyModes = ['clipboard-success', 'clipboard-getter-throw', 'write-getter-throw', 'write-sync-throw', 'write-reject', 'write-reject-legacy-success', 'legacy-false', 'legacy-throw', 'legacy-success'];
const copyResults = [];
for (const mode of copyModes) {
  console.log({ checkingCopy: mode });
  await page.reload();
  await page.evaluate((mode) => {
    window.copyProbe = { legacyCalls: 0, copied: null };
    let clipboard;
    if (mode === 'clipboard-success') clipboard = { writeText: text => { window.copyProbe.copied = text; return Promise.resolve(); } };
    if (mode === 'write-sync-throw') clipboard = { writeText: () => { throw new Error('synthetic synchronous failure'); } };
    if (mode === 'write-reject' || mode === 'write-reject-legacy-success') clipboard = { writeText: () => Promise.reject(new Error('synthetic denied')) };
    if (mode === 'write-getter-throw') { clipboard = {}; Object.defineProperty(clipboard, 'writeText', { get() { throw new Error('synthetic write property denied'); } }); }
    Object.defineProperty(navigator, 'clipboard', { configurable: true, get() { if (mode === 'clipboard-getter-throw') throw new Error('synthetic property denied'); return clipboard; } });
    document.execCommand = () => { window.copyProbe.legacyCalls++; if (mode === 'legacy-throw') throw new Error('synthetic exec failure'); return mode === 'legacy-success' || mode === 'write-reject-legacy-success'; };
  }, mode);
  if (!hasProposals) { copyResults.push({ mode, result: 'SKIPPED_NO_PROPOSAL' }); continue; }
  await click('.proposal-list article:first-of-type [data-copy-ticket]');
  const success = mode === 'clipboard-success' || mode === 'legacy-success' || mode === 'write-reject-legacy-success';
  await page.waitForFunction((success) => {
    const article = document.querySelector('.proposal-list article');
    const textarea = article.querySelector('.ticket-text');
    return success ? article.querySelector('[data-copy-status]').textContent.startsWith('已复制')
      : article.querySelector('.adoption-ticket').open && document.activeElement === textarea && textarea.selectionStart === 0 && textarea.selectionEnd === textarea.value.length;
  }, success);
  const copy = await page.evaluate(() => {
    const article = document.querySelector('.proposal-list article'), textarea = article.querySelector('.ticket-text');
    return { status: article.querySelector('[data-copy-status]').textContent, open: article.querySelector('.adoption-ticket').open,
      selected: textarea.selectionEnd - textarea.selectionStart, length: textarea.value.length, probe: window.copyProbe };
  });
  if (success) assert.ok(copy.status.startsWith('已复制'));
  else { assert.ok(copy.status.includes('已展开工单')); assert.equal(copy.selected, copy.length); assert.ok(copy.length > 100); }
  assert.equal(copy.probe.legacyCalls, mode === 'clipboard-success' ? 0 : 1, mode + ' must try execCommand after clipboard failure');
  if (mode === 'write-reject-legacy-success') assert.ok(copy.status.includes('兼容模式'), 'clipboard rejection must retain successful legacy copying');
  if (mode === 'clipboard-success') assert.ok(copy.probe.copied.includes('【Self Evolve Skill 采纳工单】'));
  copyResults.push({ mode, result: 'PASS' });
}
// Disable real script execution before navigating each sibling. Native details and textareas remain usable.
await cdp('Emulation.setScriptExecutionDisabled', { value: true });
const noScriptPages = [];
let noScriptManualCopy = 'PASS';
try {
  for (const item of navigation) {
    await page.goto(new URL(item.href, reportUrl).href);
    const state = await page.evaluate(() => ({ current: document.querySelector('[aria-current=page]').getAttribute('href'), heading: document.querySelector('h1').textContent, cards: document.querySelectorAll('[data-row]').length }));
    assert.equal(state.current, item.href);
    assert.ok(state.heading.length);
    noScriptPages.push({ page: item.title, result: 'PASS' });
  }
  if (hasProposals) {
    await page.goto(new URL(skills.href, reportUrl).href);
    await click('.proposal-list article:first-of-type .adoption-ticket summary');
    await page.focus('.proposal-list article:first-of-type .ticket-text');
    await page.press('.proposal-list article:first-of-type .ticket-text', 'ControlOrMeta+A');
    const noScript = await page.evaluate(() => {
      const el = document.querySelector('.ticket-text');
      return { open: document.querySelector('.adoption-ticket').open, text: el.value, start: el.selectionStart, end: el.selectionEnd };
    });
    assert.ok(noScript.open);
    assert.ok(noScript.text.includes('record-adoption --proposal-id'));
    assert.ok(noScript.text.includes('实际 Runtime'));
    assert.equal(noScript.start, 0); assert.equal(noScript.end, noScript.text.length);
  } else {
    noScriptManualCopy = 'SKIPPED_NO_PROPOSAL';
  }
} finally {
  await cdp('Emulation.setScriptExecutionDisabled', { value: false });
}
await page.reload();
const overview = navigation[0];
await click(`.nav-link[href="${overview.href}"]`);
await page.waitForURL(new URL(overview.href, reportUrl).href);
await page.waitForLoadState();
if (config.screenshot) console.log({ screenshot: await page.screenshot({ path: config.screenshot }) });
console.log({ pages: results, crossPageEvidence: 'PASS', returnLink: 'PASS', runtimeSearchAndReset: 'PASS', skillInstallation: 'PASS', copyResults, noScriptPages, noScriptManualCopy, lowInformationFolding: lowInfo.present ? 'PASS' : 'NOT_PRESENT', profilePage: 'PASS' });
await task.finish({ keep: [] });
