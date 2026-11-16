'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');

const skill = path.resolve(__dirname, '../..');
const example = path.join(skill, 'references/templates/motion-example.html');
const options = { viewport: { width: 1280, height: 720 }, offline: true };

test('replayable states, keyboard ownership and static reading on the actual template', async () => {
  const browser = await chromium.launch({ channel: 'chromium' });
  try {
    const page = await browser.newPage(options);
    await page.goto(pathToFileURL(example).href);
    const result = page.locator('[data-ready]');
    assert.ok(await result.isHidden());
    await page.keyboard.press('Space');
    assert.equal(await page.locator('.motion').getAttribute('data-step'), '1');
    assert.ok(await result.isHidden(), 'ready is separate from summarized');
    await page.keyboard.press('Space');
    await result.waitFor({ state: 'visible' });
    const stays = await page.evaluate(() => {
      const normal = new KeyboardEvent('keydown', { key: ' ', cancelable: true, bubbles: true });
      document.body.dispatchEvent(normal);
      const held = new KeyboardEvent('keydown', { key: ' ', repeat: true, cancelable: true, bubbles: true });
      document.body.dispatchEvent(held);
      return [normal.defaultPrevented, held.defaultPrevented];
    });
    assert.deepEqual(stays, [false, true], 'a fresh key may turn the page, a held key must not');
    await page.keyboard.press('Shift+Space');
    await result.waitFor({ state: 'hidden' });
    await page.getByRole('button', { name: '汇总' }).focus();
    await page.keyboard.press('Space');
    await result.waitFor({ state: 'visible' });
    await page.getByRole('button', { name: '输入' }).click();
    await result.waitFor({ state: 'hidden' });
    await page.keyboard.press('b');
    assert.ok(await page.getByText('回看范围：摘要中的事实仍能追溯到原始记录。').isVisible());
    const noScript = await browser.newPage({ ...options, javaScriptEnabled: false });
    await noScript.goto(pathToFileURL(example).href);
    assert.ok(await noScript.getByRole('heading', { name: '证据摘要', exact: true }).isVisible());
    assert.equal(await noScript.getByRole('button').count(), 0);
  } finally {
    await browser.close();
  }
});

test('real PPTX and PDF use the authored fallback instead of the live first cue', { timeout: 100000 }, () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'slides-motion-'));
  try {
    const output = path.join(tmp, 'motion');
    execFileSync(process.execPath, [
      path.join(skill, 'scripts/convert.js'), example, '-o', output,
      '--format', 'both', '--background-mode', 'native',
      '--config', path.join(skill, 'config/profile.example.json'),
    ], { cwd: tmp, encoding: 'utf8', timeout: 90000 });
    const pdf = execFileSync('pdftotext', [output + '.pdf', '-'], { encoding: 'utf8' });
    assert.equal(pdf.trimEnd().split('\f').length, 2, 'PDF retains both pages');
    assert.match(pdf, /回看范围/);
    assert.doesNotMatch(pdf, /下一步|汇总区/);
    const ppt = execFileSync('unzip', ['-p', output + '.pptx', 'ppt/slides/slide1.xml'], { encoding: 'utf8' });
    assert.match(ppt, /<a:t>回看范围/);
    assert.doesNotMatch(ppt, /下一步|汇总区/);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
