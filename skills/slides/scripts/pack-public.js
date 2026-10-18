#!/usr/bin/env node
/**
 * pack-public.js - 构建 slides 公开发布候选清单/压缩包
 *
 * 明确允许清单（allow-list）：只复制白名单条目，不用「整目录减黑名单」。
 * 排除：本地配置、私有素材、个人风格、内部工作文档、运行产物、node_modules、缓存。
 * 打包后对实际纳入条目过「具体名称门禁」（check-privacy.js，通用模式检测，
 * 不依赖维护者私有名单——机构名/人名+职称/绝对路径/内部编号/联系方式/
 * 个人素材文件名/真实课程路径，配置文件从严要求空模板；有意保留的作者署名
 * 走 INTENTIONAL 登记表豁免）。门禁不过则拒绝打包。
 *
 * USAGE:
 *   node pack-public.js --list            # 打印纳入/排除/缺失，并扫描（不写盘）
 *   node pack-public.js --out-dir <dir>   # 解包到目录，便于逐项检查
 *   node pack-public.js --out <zip>       # 生成 zip（需系统 zip 命令）
 *
 * 公私区分约定：Git 跟踪的 = 可发布通用内容；被 .gitignore 忽略的
 * （config/local/、config/*.local.*、assets/local/ 等）= 使用者私有，永不入包。
 */

'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..');

// 允许清单：相对技能根目录的条目（目录递归纳入其内容）。
const ALLOW = [
  'SKILL.md',
  'LICENSE.txt',
  'CHANGELOG.md',
  '.gitignore',                 // 随包分发：使用者装包后仍需本规则保护自己的私有配置
  'example.html',
  'assets/README.md',            // 素材目录说明（图片本身默认私有不入包）
  'config/profile.schema.json',
  'config/profile.example.json',
  'references/configuration.md',
  'references/pptx-guide.md',
  'references/native-pptx-rebuild.md',
  'references/layout-theme-playbook.md',
  'references/browser-guide.md',
  'references/style-reference.md',
  'references/cn-deck-polish.md',
  'references/ppt-writing-rules.md',
  'references/intake-checklist.md',
  'references/merge-pitfalls.md',
  'references/icon-system.md',
  'references/screenshot-framing.md',
  'references/templates.md',
  'references/templates',
  'references/styles',
  'references/research',
  'scripts/convert.js',
  'scripts/html2pptx.js',
  'scripts/html2pdf.js',
  'scripts/html2pdf-carousel-hd.js',
  'scripts/html2pdf-scrollsnap-hd.js',
  'scripts/extract-style.js',
  'scripts/validate-slides.js',
  'scripts/load-profile.js',
  'scripts/init-profile.js',
  'scripts/check-profile.js',
  'scripts/pack-public.js',
  'scripts/check-privacy.js', // 具体名称门禁（通用检测，随包分发，使用者可自审）
  'scripts/generate-previews.js',
  'scripts/package.json',
  'scripts/tests'
];

// 即使在 ALLOW 目录下也跳过。
const SKIP_DIR_NAMES = new Set(['node_modules', 'legacy-private', 'local', '.git', '__pycache__']);
const SKIP_BASENAME = /\.local\.|profile\.local\.|\.DS_Store$/;
const SKIP_EXT = new Set(['.pptx', '.pdf', '.docx']);

// 内部工作文档：含私仓历史 / 未发布规划，不进公开包（留在私仓作权威记录）。
const INTERNAL_DOCS = new Set([
  'TASKS.md',
  'DECISIONS.md',
  'references/publication-remediation-plan.md'
]);

// 不得入包的泄露：私有机绝对路径 / 个人素材文件名。

function toRel(abs) {
  return path.relative(ROOT, abs).split(path.sep).join('/');
}

function skipReason(rel) {
  const parts = rel.split('/');
  if (parts.some((p) => SKIP_DIR_NAMES.has(p))) return '私有/运行目录';
  if (SKIP_BASENAME.test(path.basename(rel))) return '本地配置/私有文件';
  if (SKIP_EXT.has(path.extname(rel))) return '运行产物';
  if (INTERNAL_DOCS.has(rel)) return '内部工作文档（私仓历史/未发布规划）';
  return null;
}

function walk(rel, acc) {
  const abs = path.join(ROOT, rel);
  if (!fs.existsSync(abs)) {
    acc.missing.push(rel);
    return;
  }
  const why = skipReason(rel);
  if (why) { acc.seen.push(rel); return; }
  const st = fs.lstatSync(abs);
  if (st.isSymbolicLink()) throw new Error(`禁止发布符号链接: ${rel}`);
  if (st.isDirectory()) {
    for (const name of fs.readdirSync(abs).sort()) {
      walk(path.join(rel, name), acc);
    }
  } else {
    if (!st.isFile()) throw new Error(`不支持的发布文件类型: ${rel}`);
    acc.seen.push(rel);
  }
}

function buildList() {
  const acc = { seen: [], missing: [] };
  for (const entry of ALLOW) walk(entry, acc);

  const files = [];
  const excluded = [];
  for (const rel of [...new Set(acc.seen)]) {
    const why = skipReason(rel);
    if (why) { excluded.push({ rel, why }); continue; }
    files.push(rel);
  }
  return { files, missing: acc.missing, excluded };
}

// 泄露扫描 = 通用「具体名称门禁」（用户 261016 定调：不靠私有名单，靠模式）
function scanLeaks(files) {
  const { scan } = require('./check-privacy');
  const { findings } = scan(files);
  return findings.map((f) => ({ rel: f.file, why: `${f.id} ${f.why}`, snippet: f.snippet }));
}

function parseArgs(argv) {
  const out = { list: false, outZip: null, outDir: null };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--list') out.list = true;
    else if (argv[i] === '--out' || argv[i] === '--out-dir') {
      const key = argv[i] === '--out' ? 'outZip' : 'outDir';
      const value = argv[++i];
      if (!value || value.startsWith('--')) throw new Error('输出参数缺少路径');
      out[key] = value;
    }
    else if (argv[i] === '--help') out.help = true;
    else throw new Error(`未知参数: ${argv[i]}`);
  }
  return out;
}

function checkLinks(files) {
  const included = new Set(files);
  const broken = [];
  for (const rel of files.filter((f) => f.endsWith('.md'))) {
    const text = fs.readFileSync(path.join(ROOT, rel), 'utf8');
    for (const match of text.matchAll(/\[[^\]]*\]\(([^)]+)\)/g)) {
      const target = match[1].split('#')[0];
      if (!target || /^(?:[a-z]+:|\/)/i.test(target)) continue;
      const resolved = path.posix.normalize(path.posix.join(path.posix.dirname(rel), target));
      if (!included.has(resolved) && !files.some((f) => f.startsWith(resolved.replace(/\/$/, '') + '/'))) {
        broken.push(`${rel} → ${target}`);
      }
    }
  }
  return broken;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log('用法: node pack-public.js [--list] [--out <zip>] [--out-dir <dir>]');
    return;
  }
  const result = buildList();
  const leaks = scanLeaks(result.files);

  console.log('── slides 公开发布候选清单 ──');
  console.log(`纳入条目: ${result.files.length}`);
  console.log(`排除条目: ${result.excluded.length}`);
  if (result.missing.length) {
    console.log(`\n白名单中缺失（请核对路径）:`);
    for (const m of result.missing) console.log(`  ? ${m}`);
  }

  if (args.list) {
    console.log('\n纳入:');
    for (const f of result.files) console.log(`  + ${f}`);
    console.log('\n排除:');
    for (const e of result.excluded) console.log(`  - ${e.rel}  ← ${e.why}`);
  }

  console.log('\n泄露扫描（具体名称门禁 G1–G10）:');
  if (leaks.length === 0) {
    console.log('  模式扫描未命中；仍需人工复核语义隐私与二进制素材。');
  } else {
    for (const h of leaks) console.log(`  ! ${h.rel}: [${h.why}] ${h.snippet}`);
  }

  if (result.missing.length > 0) {
    console.error(`\n错误: ${result.missing.length} 个白名单条目不存在，先修正清单。`);
    process.exit(1);
  }
  if (leaks.length > 0) {
    console.error('\n错误: 纳入条目含禁止入包的泄露，禁止打包。');
    process.exit(1);
  }

  const broken = checkLinks(result.files);
  if (broken.length) throw new Error(`公开包相对链接缺失: ${broken.join(', ')}`);
  for (const target of [args.outZip, args.outDir].filter(Boolean)) {
    const absolute = path.resolve(target);
    const relative = path.relative(ROOT, absolute);
    if (!relative || (!relative.startsWith('..' + path.sep) && !path.isAbsolute(relative))) {
      throw new Error('发布输出必须位于技能目录之外');
    }
    try { fs.lstatSync(absolute); } catch (err) { if (err.code === 'ENOENT') continue; throw err; }
    throw new Error(`输出已存在，拒绝覆盖: ${absolute}`);
  }

  if (!args.outZip && !args.outDir) {
    console.log('\n(未指定 --out/--out-dir，仅列清单)');
    return;
  }

  const stage = fs.mkdtempSync(path.join(os.tmpdir(), 'slides-pub-'));
  const stageRoot = path.join(stage, 'slides');
  try {
    for (const rel of result.files) {
      const dst = path.join(stageRoot, rel);
      fs.mkdirSync(path.dirname(dst), { recursive: true });
      fs.copyFileSync(path.join(ROOT, rel), dst);
    }
    const stagedFindings = require('./check-privacy').scan(result.files, stageRoot).findings;
    if (stagedFindings.length) throw new Error('暂存包隐私检查失败，拒绝输出');
    if (args.outDir) {
      const destRoot = path.resolve(args.outDir);
      fs.mkdirSync(destRoot);
      fs.cpSync(stageRoot, destRoot, { recursive: true, force: false, errorOnExist: true });
      console.log(`\n已解包 ${result.files.length} 个条目到: ${destRoot}`);
    }
    if (args.outZip) {
      const zipPath = path.resolve(args.outZip);
      const stagedZip = path.join(stage, 'release.zip');
      execFileSync('zip', ['-r', '-q', stagedZip, 'slides'], { cwd: stage });
      fs.copyFileSync(stagedZip, zipPath, fs.constants.COPYFILE_EXCL);
      console.log(`\n已生成压缩包: ${zipPath}`);
    }
  } catch (err) {
    console.error(`打包失败: ${err.message}`);
    process.exit(1);
  } finally {
    fs.rmSync(stage, { recursive: true, force: true });
  }
}

module.exports = { buildList, checkLinks };
if (require.main === module) {
  try { main(); } catch (err) { console.error(`打包失败: ${err.message}`); process.exitCode = 1; }
}
