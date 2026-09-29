#!/usr/bin/env node
/**
 * dsh-plugin-lint 自测：自包含 fixture，证明每条规则抓得住无效样本、放行有效对照。
 * 用法: node test-lint.mjs
 * 退出码 0 = 全部断言通过。
 *
 * 运行时在临时目录合成一个迷你 harness（platform.ts / tsdown.client.ts / ui-theme styles /
 * 官方 bin 门 / workspace 包）与两个插件夹具（valid / invalid），用 --json 与
 * DSH_HARNESS_ROOT 两种 harness 根解析路径跑 lint.mjs 并断言结果。
 */

import assert from 'node:assert/strict'
import { execFileSync, spawnSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const SCRIPT = fileURLToPath(new URL('./lint.mjs', import.meta.url))
const FAKE_VERSION = '9.8.7-test.1'

let passed = 0
function ok(name, fn) {
  if (fn !== undefined) fn()
  passed += 1
  console.log(`  ✓ ${name}`)
}

function write(file, content) {
  mkdirSync(path.dirname(file), { recursive: true })
  writeFileSync(file, content)
}

// ── 合成迷你 harness ────────────────────────────────────────────────────────
function buildFakeHarness(root) {
  write(path.join(root, 'package.json'), JSON.stringify({ name: '@deepseek-ai/dsh-root', version: FAKE_VERSION }))
  // 官方可执行门替身：忽略参数，输出版本
  write(path.join(root, 'apps', 'cli', 'lib', 'bin.js'), `process.stdout.write(${JSON.stringify(`${FAKE_VERSION}\n`)})\n`)
  write(
    path.join(root, 'packages', 'client', 'web', 'src', 'platform.ts'),
    `export const PLATFORM_MODULES = [\n`
    + `  'react', 'react/jsx-runtime', '@deepseek-ai/cordis', '@deepseek-ai/dsh-client-ui-slots',\n`
    + `] as const\n\n`
    + `export const PRELOADED_CLIENT_EXTERNALS = [\n] as const\n`,
  )
  write(
    path.join(root, 'packages', 'client', 'tsdown.client.ts'),
    `export const INLINE_SAFE = /^@deepseek-ai\\/dsh-file-reference(?:\\/|$)/\n`
    + `const VENDORED_LIBRARY = /^@deepseek-ai\\/(cosmokit|schemastery)(\\/|$)/\n`
    + `const GENERATED_REMOTE = /^@deepseek-ai\\/dsh-[a-z0-9]+(?:-[a-z0-9]+)*\\/remote$/\n`,
  )
  write(
    path.join(root, 'packages', 'client', 'ui-theme', 'src', 'styles', 'design-platform.css'),
    ':root {\n  --dsw-alias-bg-base: rgb(255, 255, 255);\n  --dsw-alias-border-l2: rgb(229, 227, 221);\n}\n',
  )
  // 一个真实声明了 dsh.client 的 workspace 包（合法 inject 目标）
  write(
    path.join(root, 'packages', 'client', 'ui-thing', 'package.json'),
    JSON.stringify({ name: '@deepseek-ai/dsh-client-ui-thing', dsh: { client: { platform: 'web' } } }),
  )
  // 让 git commit 可解析；失败则测试回退为不断言 commit
  try {
    execFileSync('git', ['init', '-q'], { cwd: root })
    execFileSync('git', ['add', '-A'], { cwd: root })
    execFileSync('git', ['-c', 'user.email=t@local', '-c', 'user.name=t', 'commit', '-qm', 'fixture'], { cwd: root })
    return true
  } catch {
    return false
  }
}

// ── 有效插件夹具（对照：0 FAIL / 0 WARN）────────────────────────────────────
const VALID_ARTIFACT = [
  'window.__ModuleLoader__.load({ id: "@test/valid-plugin", factory: (require) => {',
  'var module = { exports: {} }; var exports = module.exports;',
  'const react = require("react");',
  "const slots = require('@deepseek-ai/dsh-client-ui-slots');",
  "exports.render = () => react.createElement('div', null, slots.name);",
  'return module.exports;',
  '} });',
  '//# sourceMappingURL=client.js.map',
].join('\n')

function buildValidPlugin(root) {
  write(path.join(root, 'package.json'), JSON.stringify({
    name: '@test/valid-plugin',
    type: 'module',
    main: 'lib/index.js',
    exports: { '.': './lib/index.js', './client': './lib/client.js' },
    dsh: {
      bundle: { patch: './cordis.patch.yml' },
      client: { platform: 'web', inject: ['@deepseek-ai/dsh-client-ui-thing'] },
    },
    dependencies: { '@deepseek-ai/dsh-tools': FAKE_VERSION },
    devDependencies: { '@deepseek-ai/dsh-client-ui-thing': FAKE_VERSION },
    publishConfig: { access: 'public' },
    scripts: { build: 'tsc', test: 'vitest run' },
  }, null, 2))
  write(path.join(root, 'cordis.patch.yml'), "- insert:\n    - id: valid-plugin\n      name: '@test/valid-plugin'\n")
  write(path.join(root, 'lib', 'index.js'), 'export const apply = () => {}\n')
  write(path.join(root, 'lib', 'client.js'), VALID_ARTIFACT)
  write(
    path.join(root, 'tsdown.client.config.ts'),
    'const EXTERNALS = new Set([\n'
    + "  'react',\n  'react/jsx-runtime',\n  '@deepseek-ai/cordis',\n  '@deepseek-ai/dsh-client-ui-slots',\n"
    + '])\n'
    + 'export default { deps: { neverBundle: s => EXTERNALS.has(s) } }\n',
  )
  write(
    path.join(root, 'src', 'client', 'index.tsx'),
    "import { createElement } from 'react'\n"
    + "import css from './index.module.css'\n"
    + 'export function Panel() {\n'
    + "  return <div className={css.panel} style={{ background: 'var(--dsw-alias-bg-base)' }} />\n"
    + '}\n',
  )
  write(
    path.join(root, 'src', 'client', 'locales.ts'),
    "export const zh = { 'panel.title': '面板' }\nexport const en = { 'panel.title': 'Panel' }\n",
  )
  write(path.join(root, 'README.md'), '# valid-plugin\n\n对照夹具：全部声明与当前 harness 一致。\n')
}

// ── 无效插件夹具（每条规则各埋一处违规）─────────────────────────────────────
const INVALID_ARTIFACT = [
  'window.__ModuleLoader__.load({ id: "@test/invalid-plugin", factory: (require) => {',
  'var module = { exports: {} }; var exports = module.exports;',
  'const react = require("react");',
  "const ghost = require('@deepseek-ai/dsh-client-ghost-bare');",
  "const wire = require('@deepseek-ai/dsh-file-reference');",
  'exports.render = () => ghost.concat(wire, react);',
  'return module.exports;',
  '} });',
].join('\n')

function buildInvalidPlugin(root) {
  write(path.join(root, 'package.json'), JSON.stringify({
    name: '@test/invalid-plugin',
    type: 'module',
    main: 'lib/index.js',
    exports: { '.': './lib/index.js', './client': './lib/client.cjs' },
    dsh: {
      bundle: { patch: './cordis.patch.yml' },
      client: {
        platform: 'web',
        inject: ['@deepseek-ai/dsh-client-ghost'],
        external: ['@deepseek-ai/dsh-client-unused', 'react'],
      },
    },
    scripts: { build: 'tsc' },
  }, null, 2))
  // cordis.patch.yml 故意缺失 → bundle FAIL
  write(path.join(root, 'lib', 'index.js'), 'export const apply = () => {}\n')
  // 后缀 .cjs（banner/footer 本身完整，隔离验证后缀规则）
  write(path.join(root, 'lib', 'client.cjs'), INVALID_ARTIFACT)
  write(
    path.join(root, 'tsdown.client.config.ts'),
    "const CLIENT_EXTERNALS = new Set(['react', '@deepseek-ai/dsh-client-ghost-bare'])\n"
    + 'export default { deps: { neverBundle: s => CLIENT_EXTERNALS.has(s) } }\n',
  )
  write(
    path.join(root, 'src', 'client', 'broken.tsx'),
    'export function Bar() {\n'
    + "  const LABEL = '中文标签'\n"
    + '  return (\n'
    + '    <div>\n'
    + '      <button placeholder="请输入中文" aria-label="打开面板">确认提交</button>\n'
    + "      <span title={LABEL}>{LABEL}</span>\n"
    + '    </div>\n'
    + '  )\n'
    + '}\n',
  )
  write(
    path.join(root, 'src', 'client', 'locales.ts'),
    "export const zh = { 'bar.ok': '确认', 'bar.cancel': '取消' }\nexport const en = { 'bar.ok': 'OK' }\n",
  )
  write(
    path.join(root, 'src', 'client', 'broken.css'),
    '.card {\n  color: var(--dsw-alias-fg-nonexistent);\n  border-color: var(--dsw-alias-border-l2);\n}\n',
  )
  write(path.join(root, 'README.md'), '# invalid-plugin\n\n基于 harness 0.1.0-rc.7 编写，声明已过期。\n')
}

// ── 运行 lint 并解析 --json ─────────────────────────────────────────────────
function runLint(target, harnessRoot, viaEnv = false) {
  const args = [SCRIPT, target]
  if (!viaEnv) args.push('--harness-root', harnessRoot)
  args.push('--json')
  const env = viaEnv ? { ...process.env, DSH_HARNESS_ROOT: harnessRoot } : { ...process.env }
  const res = spawnSync(process.execPath, args, { env, encoding: 'utf8' })
  const marker = '__DSH_LINT_JSON__'
  const line = (res.stdout ?? '').split('\n').find(l => l.startsWith(marker))
  assert.ok(line !== undefined, `lint 输出缺少 ${marker} 行；stderr: ${res.stderr}`)
  return { report: JSON.parse(line.slice(marker.length)), exitStatus: res.status }
}

function findingsOf(report, level) {
  return report.findings.filter(f => f.level === level).map(f => f.message)
}

function assertNoFinding(report, level, substring) {
  const hit = findingsOf(report, level).some(message => message.includes(substring))
  assert.ok(!hit, `不应出现 ${level}: ${substring}`)
}

function assertHasFinding(report, level, substring) {
  const hit = findingsOf(report, level).some(message => message.includes(substring))
  assert.ok(hit, `应出现 ${level}: ${substring}；实际 ${level} 列表: ${JSON.stringify(findingsOf(report, level))}`)
}

// ── 执行 ────────────────────────────────────────────────────────────────────
const workspace = mkdtempSync(path.join(tmpdir(), 'dsh-plugin-lint-test-'))
try {
  const harnessRoot = path.join(workspace, 'harness')
  const gitOk = buildFakeHarness(harnessRoot)
  const validDir = path.join(workspace, 'plugin-valid')
  const invalidDir = path.join(workspace, 'plugin-invalid')
  buildValidPlugin(validDir)
  buildInvalidPlugin(invalidDir)

  console.log('有效夹具（--harness-root 参数解析）')
  const valid = runLint(validDir, harnessRoot)
  ok('0 FAIL', () => assert.equal(valid.report.fails, 0, JSON.stringify(findingsOf(valid.report, 'FAIL'))))
  ok('0 WARN', () => assert.equal(valid.report.warns, 0, JSON.stringify(findingsOf(valid.report, 'WARN'))))
  ok('退出码 = FAIL 数 = 0', () => assert.equal(valid.exitStatus, 0))
  ok('harness 版本经官方 bin 门溯源', () => {
    assert.equal(valid.report.harness.dshVersion, FAKE_VERSION)
    assert.equal(valid.report.harness.binVersion, FAKE_VERSION)
  })
  ok('平台模块表从源码解析（4 项基线）', () => {
    assert.ok(findingsOf(valid.report, 'PASS').some(message => message.includes('平台模块表 4 项')))
  })
  if (gitOk) {
    ok('harness git commit 溯源', () => assert.match(valid.report.harness.commit ?? '', /^[0-9a-f]{40}$/))
  }

  console.log('无效夹具（DSH_HARNESS_ROOT 环境变量解析）')
  const invalid = runLint(invalidDir, harnessRoot, true)
  const { report } = invalid
  ok('harness 根经环境变量解析', () => {
    assert.equal(report.harness.source, '环境变量 DSH_HARNESS_ROOT')
    assert.equal(report.harness.dshVersion, FAKE_VERSION)
  })
  ok('退出码 = FAIL 数', () => assert.equal(invalid.exitStatus, report.fails))

  // 规则 1：bundle patch 文件缺失
  assertHasFinding(report, 'FAIL', 'dsh.bundle.patch 指向的文件不存在')
  ok('规则 bundle: patch 缺失被抓')
  // 规则 2：工件后缀 .cjs
  assertHasFinding(report, 'FAIL', '工件后缀是 .cjs')
  ok('规则 工件后缀: .cjs 被抓（banner 完整仍放行 banner 规则）', () => {
    assert.ok(findingsOf(report, 'PASS').some(message => message.includes('banner 契约完整')))
  })
  // 规则 3：模块表无法应答的 bare require
  assertHasFinding(report, 'FAIL', 'bare require("@deepseek-ai/dsh-client-ghost-bare")')
  ok('规则 产物 bare require: 未知说明符被抓')
  // 规则 4：内联安全层被外置
  assertHasFinding(report, 'FAIL', 'bare require("@deepseek-ai/dsh-file-reference")')
  ok('规则 纯度对账: INLINE_SAFE 说明符被外置被抓')
  // 规则 5：构建配置 external 越界
  assertHasFinding(report, 'FAIL', '把 "@deepseek-ai/dsh-client-ghost-bare" 标为 external')
  ok('规则 构建配置 external ↔ 声明对账: 越界被抓')
  // 规则 6：inject 目标无 dsh.client
  assertHasFinding(report, 'FAIL', '@deepseek-ai/dsh-client-ghost 在 harness workspace 与本地 node_modules 均未声明 dsh.client')
  ok('规则 inject 目标存在性: 幽灵包被抓')
  assertHasFinding(report, 'WARN', '不在 dependencies/devDependencies')
  ok('规则 inject ↔ devDep 双保险缺失被抓（WARN）')
  // 规则 7：基线冗余 external + 死行 external
  assertHasFinding(report, 'WARN', '"react" 已在平台基线中')
  assertHasFinding(report, 'WARN', '"@deepseek-ai/dsh-client-unused" 在产物中没有任何对应 require')
  ok('规则 external 声明: 基线冗余与死行都被抓（WARN）')
  // 规则 8：不存在的主题变量（有效对照中的合法变量不报）
  assertHasFinding(report, 'FAIL', '不存在的 DSH 主题变量 --dsw-alias-fg-nonexistent')
  ok('规则 主题变量: 不存在的变量被抓')
  // 规则 9/10：JSX 文本与用户可见属性硬编码
  assertHasFinding(report, 'FAIL', 'JSX 文本位置硬编码文案')
  assertHasFinding(report, 'FAIL', 'placeholder="请输入中文"')
  assertHasFinding(report, 'FAIL', 'aria-label="打开面板"')
  ok('规则 硬编码文案: JSX 文本 / placeholder / aria-label 都被抓')
  // 规则 11：CJK 字面量 WARN（有效夹具同位置不报）
  assertHasFinding(report, 'WARN', "CJK 字符串字面量")
  ok('规则 CJK 字面量: 字符串常量出 WARN（非 FAIL）')
  // 规则 12：zh/en 词典平价
  assertHasFinding(report, 'FAIL', 'zh/en 键集不平价')
  ok('规则 locale 词典平价: en 缺键被抓')
  // 规则 13：文档冻结版本声明
  assertHasFinding(report, 'WARN', '0.1.0-rc')
  ok('规则 文档版本声明: 冻结 rc 版本被抓（WARN）')
  // 规则 14：scripts 卫生
  assertHasFinding(report, 'WARN', '缺 scripts.test')
  ok('规则 卫生: 缺 scripts.test 被抓（WARN）')

  // 有效对照必须不放行无效夹具命中的同类缺陷
  for (const [level, substring] of [
    ['FAIL', 'dsw-alias-fg-nonexistent'],
    ['FAIL', 'JSX 文本位置硬编码'],
    ['FAIL', '键集不平价'],
    ['WARN', '已在平台基线中'],
    ['WARN', '0.1.0-rc'],
  ]) {
    assertNoFinding(valid.report, level, substring)
  }
  ok('有效对照对全部同类检查项保持沉默')

  console.log(`\n自测通过：${passed} 项断言全部成立（夹具: ${workspace}）`)
} finally {
  rmSync(workspace, { recursive: true, force: true })
}
