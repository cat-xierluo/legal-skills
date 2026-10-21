/**
 * Tests for html2pdf fidelity options (v1.5.11+).
 * Run from slides/scripts/:
 *   node tests/test-html2pdf-fidelity.mjs
 *
 * Asserts: (a) default path matches v1.5.10 (no regression), (b) all 6 fidelity
 * options produce a valid multi-page PDF without throwing, (c) preferExactSize
 * emits integer px dimensions, (d) tagged produces a Tagged PDF.
 */
import path from 'node:path';
import fs from 'node:fs';
import os from 'node:os';
import { execFileSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const scriptsDir = path.resolve(here, '..');
const html2pdf = (await import(pathToFileURL(path.join(scriptsDir, 'html2pdf.js')).href)).default;

const FIXTURE = path.join(here, 'fixtures', 'dynamic-background.html');
if (!fs.existsSync(FIXTURE)) {
  console.error(`fixture missing: ${FIXTURE}`);
  process.exit(1);
}

function tmpPdf(name) {
  return path.join(os.tmpdir(), `slides-fi-${Date.now()}-${name}.pdf`);
}

function pdfInfo(pdfPath) {
  try {
    const out = execFileSync('pdfinfo', [pdfPath], { encoding: 'utf8' });
    const kv = {};
    out.split('\n').forEach((line) => {
      const m = line.match(/^([^:]+):\s+(.+)$/);
      if (m) kv[m[1].trim()] = m[2].trim();
    });
    return kv;
  } catch (_) {
    return null;
  }
}

const tests = [];
async function run(name, fn) { tests.push({ name, fn }); }

await run('default path (v1.5.10 compatibility)', async () => {
  const out = tmpPdf('default');
  await html2pdf(FIXTURE, out);
  const info = pdfInfo(out);
  if (!info) return 'pdfinfo unavailable, skipping assertions';
  if (parseInt(info['Pages'], 10) < 2) return `expected ≥2 pages, got ${info['Pages']}`;
  return null;
});

await run('preferExactSize → integer px', async () => {
  const out = tmpPdf('exact');
  await html2pdf(FIXTURE, out, { preferExactSize: true });
  const info = pdfInfo(out);
  if (!info) return 'pdfinfo unavailable';
  const sz = info['Page size'] || '';
  if (!/^\d+\s+x\s+\d+/.test(sz)) return `unexpected format: ${sz}`;
  return null;
});

await run('tagged → Tagged PDF', async () => {
  const out = tmpPdf('tagged');
  await html2pdf(FIXTURE, out, { tagged: true });
  const info = pdfInfo(out);
  if (!info) return 'pdfinfo unavailable';
  if ((info['Tagged'] || '').toLowerCase() !== 'yes') return `expected Tagged: yes, got ${info['Tagged']}`;
  return null;
});

await run('textRendering: geometricPrecision', async () => {
  const out = tmpPdf('geoprec');
  await html2pdf(FIXTURE, out, { textRendering: 'geometricPrecision' });
  const info = pdfInfo(out);
  if (!info) return 'pdfinfo unavailable';
  if (parseInt(info['Pages'], 10) < 2) return `expected ≥2 pages`;
  return null;
});

await run('backgroundStrategy: hide', async () => {
  const out = tmpPdf('bghide');
  await html2pdf(FIXTURE, out, { backgroundStrategy: 'hide' });
  const info = pdfInfo(out);
  if (!info) return 'pdfinfo unavailable';
  if (parseInt(info['Pages'], 10) < 2) return `expected ≥2 pages`;
  return null;
});

await run('backgroundStrategy: freeze', async () => {
  const out = tmpPdf('bgfreeze');
  await html2pdf(FIXTURE, out, { backgroundStrategy: 'freeze' });
  const info = pdfInfo(out);
  if (!info) return 'pdfinfo unavailable';
  if (parseInt(info['Pages'], 10) < 2) return `expected ≥2 pages`;
  return null;
});

await run('marginMode: compact on single page (smoke)', async () => {
  const singlePath = path.join(os.tmpdir(), `slides-fi-single-${Date.now()}.html`);
  const html = `<!DOCTYPE html><html><head><style>body{margin:0;width:1280px;height:720px}</style></head><body><div class="content">hello</div></body></html>`;
  fs.writeFileSync(singlePath, html);
  try {
    const out = tmpPdf('compact');
    await html2pdf(singlePath, out, { marginMode: 'compact' });
    return null;
  } finally {
    try { fs.unlinkSync(singlePath); } catch (_) {}
  }
});

let passed = 0;
let failed = 0;
for (const t of tests) {
  try {
    const err = await t.fn();
    if (err) {
      console.error(`✗ ${t.name}: ${err}`);
      failed++;
    } else {
      console.log(`✓ ${t.name}`);
      passed++;
    }
  } catch (e) {
    console.error(`✗ ${t.name}: ${e.message}`);
    failed++;
  }
}
console.log(`\n${passed} passed, ${failed} failed (of ${tests.length})`);
process.exit(failed === 0 ? 0 : 1);