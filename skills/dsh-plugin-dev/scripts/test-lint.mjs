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
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
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

  // ── 审计回归（DPD-AUDIT-001 F01–F06 最小反例，每个修复绑定正反例）──────────
  console.log('审计回归（DPD-AUDIT-001 F01–F06）')
  const cloneValid = (name, mutate) => {
    const root = path.join(workspace, name)
    buildValidPlugin(root)
    if (mutate !== undefined) mutate(root)
    return root
  }
  const mutatePkg = (root, fn) => {
    const pkgFile = path.join(root, 'package.json')
    const p = JSON.parse(readFileSync(pkgFile, 'utf8'))
    fn(p)
    write(pkgFile, JSON.stringify(p, null, 2))
  }

  // F01 事实源缺失降级：无 harness 时同一有效基线不得误报 FAIL（此前 3 FAIL）
  const degraded = runLint(cloneValid('f01-no-harness'), '/nonexistent-harness', true)
  ok('F01 无 harness: 0 FAIL（此前误报 3 FAIL）', () => {
    assert.equal(degraded.report.fails, 0, JSON.stringify(findingsOf(degraded.report, 'FAIL')))
  })
  ok('F01 无 harness: inject/产物 require/构建 external 均降级 NOT_VERIFIED', () => {
    assertHasFinding(degraded.report, 'NOT_VERIFIED', 'inject 目标 @deepseek-ai/dsh-client-ui-thing 无法核验')
    assertHasFinding(degraded.report, 'NOT_VERIFIED', 'bare require("react") 无法与基线/声明对账')
    assertHasFinding(degraded.report, 'NOT_VERIFIED', '"react" 无法判定是否基线项')
  })

  // F01 事实无关 FAIL 在降级模式下保留：external 自引用仍抓
  const degradedSelf = runLint(cloneValid('f01-self-external', (root) => {
    mutatePkg(root, (p) => { p.dsh.client.external = ['@test/valid-plugin'] })
  }), '/nonexistent-harness', true)
  ok('F01 降级不吞事实无关 FAIL: external 自引用仍抓', () => {
    assertHasFinding(degradedSelf.report, 'FAIL', 'dsh.client.external 声明了自身包名')
  })

  // F02 嵌套键路径错位（此前压扁成集合误报平价 PASS）
  const f02a = runLint(cloneValid('f02-nested-swap', (root) => {
    write(path.join(root, 'src', 'client', 'locales.ts'),
      "export const zh = { a: { x: '甲' }, b: { y: '乙' } }\nexport const en = { a: { y: 'A' }, b: { x: 'B' } }\n")
  }), harnessRoot)
  ok('F02 嵌套键路径错位报不平价（此前假 PASS）', () => {
    assertHasFinding(f02a.report, 'FAIL', 'zh/en 键集不平价')
    assertHasFinding(f02a.report, 'FAIL', 'a.x')
  })

  // F02 同文件 const 展开：缺展开键被抓（此前 1 键假 PASS）
  const f02b = runLint(cloneValid('f02-spread-samefile', (root) => {
    write(path.join(root, 'src', 'client', 'locales.ts'),
      "const base = { hidden: '隐含' }\nexport const zh = { ...base, a: '甲' }\nexport const en = { a: 'A' }\n")
  }), harnessRoot)
  ok('F02 同文件展开解析后缺键被抓', () => {
    assertHasFinding(f02b.report, 'FAIL', 'hidden')
  })

  // F02 跨文件展开：键集不完整 → NOT_VERIFIED，不出假 PASS
  const f02c = runLint(cloneValid('f02-spread-import', (root) => {
    write(path.join(root, 'src', 'client', 'locales.ts'),
      "import { base } from './base'\nexport const zh = { ...base, a: '甲' }\nexport const en = { a: 'A' }\n")
  }), harnessRoot)
  ok('F02 跨文件展开 → NOT_VERIFIED 转人工', () => {
    assertHasFinding(f02c.report, 'NOT_VERIFIED', '展开源 base 不在同文件')
    assertNoFinding(f02c.report, 'PASS', '键集平价')
  })

  // F02 字符串值内的花括号/冒号不干扰叶路径解析
  const f02d = runLint(cloneValid('f02-brace-values', (root) => {
    write(path.join(root, 'src', 'client', 'locales.ts'),
      "export const zh = { a: '含有 { 和 : 与 } 的值', b: '}}' }\nexport const en = { a: 'v', b: 'w' }\n")
  }), harnessRoot)
  ok('F02 字符串值内花括号不干扰平价', () => {
    assertHasFinding(f02d.report, 'PASS', '键集平价（2 叶路径')
    assert.equal(f02d.report.fails, 0, JSON.stringify(findingsOf(f02d.report, 'FAIL')))
  })

  // F03 纯注释 patch（此前字符串 includes 假 PASS；宿主实际拒绝）
  const f03a = runLint(cloneValid('f03-comment-only', (root) => {
    write(path.join(root, 'cordis.patch.yml'), '# @test/valid-plugin\n')
  }), harnessRoot)
  ok('F03 纯注释 patch 报无有效声明（不再假 PASS）', () => {
    assertHasFinding(f03a.report, 'FAIL', '无有效声明行')
    assertNoFinding(f03a.report, 'PASS', 'patch row 引用')
  })

  // F03 包名仅在注释、row 声明的是别的包
  const f03b = runLint(cloneValid('f03-name-in-comment', (root) => {
    write(path.join(root, 'cordis.patch.yml'),
      "# 备注提到 @test/valid-plugin\n- insert:\n    - id: other\n      name: '@test/other-plugin'\n")
  }), harnessRoot)
  ok('F03 包名只在注释不算有效引用', () => {
    assertNoFinding(f03b.report, 'PASS', 'patch row 引用了')
    assertHasFinding(f03b.report, 'FAIL', '未找到 @test/valid-plugin 的有效声明行')
  })

  // F03 包名出现在非 id/name 值位置 → 转人工
  const f03c = runLint(cloneValid('f03-name-in-value', (root) => {
    write(path.join(root, 'cordis.patch.yml'),
      "- insert:\n    - id: other\n      name: '@test/other-plugin'\n      homepage: 'https://example.com/@test/valid-plugin'\n")
  }), harnessRoot)
  ok('F03 包名在非 id/name 值 → NOT_VERIFIED 不 PASS', () => {
    assertNoFinding(f03c.report, 'PASS', 'patch row 引用了')
    assertHasFinding(f03c.report, 'NOT_VERIFIED', '非 id/name 声明位置')
  })

  // F03 正例：合法 insert 行仍 PASS（valid 基线）
  ok('F03 合法 insert 行 PASS', () => {
    assertHasFinding(valid.report, 'PASS', 'patch row 引用了 @test/valid-plugin')
  })

  // F04 字符串 exports["."]（无 main；Node 实际可 import，此前误报 FAIL）
  const f04a = runLint(cloneValid('f04-string-exports', (root) => {
    mutatePkg(root, (p) => { delete p.main; p.exports['.'] = './lib/index.js' })
  }), harnessRoot)
  ok('F04 字符串 exports["."] 识别为合法入口', () => {
    assertHasFinding(f04a.report, 'PASS', 'node half 入口存在: ./lib/index.js')
    assertNoFinding(f04a.report, 'FAIL', '指向的文件不存在')
  })

  // F04 无法解析的条件导出 → 转人工
  const f04b = runLint(cloneValid('f04-cond-exports', (root) => {
    mutatePkg(root, (p) => { delete p.main; p.exports['.'] = { 'edge-light': './lib/index.js' } })
  }), harnessRoot)
  ok('F04 未知条件导出 → NOT_VERIFIED（不 FAIL 不假 PASS）', () => {
    assertHasFinding(f04b.report, 'NOT_VERIFIED', '条件导出')
    assertNoFinding(f04b.report, 'FAIL', '指向的文件不存在')
  })

  // F05 .js 源纳入扫描：坏主题变量与 CJK 文案在 .js 里同样被抓（同字节 .tsx 对照=invalid 夹具）
  const f05a = runLint(cloneValid('f05-js-source', (root) => {
    rmSync(path.join(root, 'src', 'client', 'index.tsx'))
    write(path.join(root, 'src', 'client', 'panel.js'),
      "export const title = '确认提交'\nexport const color = 'var(--dsw-alias-fg-nonexistent)'\n")
  }), harnessRoot)
  ok('F05 .js 源纳入扫描：坏主题变量被抓', () => {
    assertHasFinding(f05a.report, 'FAIL', '不存在的 DSH 主题变量 --dsw-alias-fg-nonexistent')
    assertHasFinding(f05a.report, 'WARN', 'panel.js')
  })

  // F05 扫描范围明示：有源 PASS 披露范围；无源 WARN 明示未覆盖（不冒充无违规）
  ok('F05 扫描范围明示（valid 基线）', () => assertHasFinding(valid.report, 'PASS', 'client 源扫描'))
  const f05b = runLint(cloneValid('f05-no-src', (root) => {
    rmSync(path.join(root, 'src', 'client'), { recursive: true, force: true })
  }), harnessRoot)
  ok('F05 无 client 源 → WARN 明示未覆盖', () => {
    assertHasFinding(f05b.report, 'WARN', '未发现 ts/tsx/js/mjs/jsx/css 源')
  })

  // F06 deps.alwaysBundle 是强制内联（tsdown 语义），不再当 external 误报
  const f06a = runLint(cloneValid('f06-always-bundle', (root) => {
    write(path.join(root, 'tsdown.client.config.ts'), "export default { deps: { alwaysBundle: ['local-utils'] } }\n")
  }), harnessRoot)
  ok('F06 alwaysBundle 不再误报为 external', () => {
    assertNoFinding(f06a.report, 'FAIL', 'local-utils')
    assertNoFinding(f06a.report, 'FAIL', '标为 external')
  })

  // F06 alwaysBundle × dsh.client.external 方向冲突
  const f06b = runLint(cloneValid('f06-bundle-conflict', (root) => {
    write(path.join(root, 'tsdown.client.config.ts'),
      "export default { deps: { alwaysBundle: ['@deepseek-ai/dsh-client-ui-slots'] } }\n")
    mutatePkg(root, (p) => { p.dsh.client.external = ['@deepseek-ai/dsh-client-ui-slots'] })
  }), harnessRoot)
  ok('F06 alwaysBundle 与 external 同名 → 方向冲突 FAIL', () => {
    assertHasFinding(f06b.report, 'FAIL', '方向冲突')
  })

  console.log(`\n自测通过：${passed} 项断言全部成立（夹具: ${workspace}）`)
} finally {
  rmSync(workspace, { recursive: true, force: true })
}
