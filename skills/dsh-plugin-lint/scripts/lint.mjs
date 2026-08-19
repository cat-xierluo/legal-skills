#!/usr/bin/env node
/**
 * dsh-plugin-lint §1 机械层：声明一致性 + client 工件契约。
 * 用法: node lint.mjs <插件目录>
 * 退出码 = FAIL 数（0 为全过）。
 */

import { readFileSync, existsSync } from 'node:fs'
import path from 'node:path'

const target = process.argv[2]
if (target === undefined || !existsSync(target)) {
  console.error('用法: node lint.mjs <插件目录>')
  process.exit(1)
}
const dir = path.resolve(target)

let fails = 0
let warns = 0
const fail = (msg) => { fails += 1; console.log(`  [FAIL] ${msg}`) }
const pass = (msg) => console.log(`  [PASS] ${msg}`)
const warn = (msg) => { warns += 1; console.log(`  [WARN] ${msg}`) }

// ── package.json ────────────────────────────────────────────────────────────
console.log('§ package.json')
let pkg
try {
  pkg = JSON.parse(readFileSync(path.join(dir, 'package.json'), 'utf8'))
  pass(`name = ${pkg.name}`)
} catch (error) {
  fail(`package.json 解析失败: ${error instanceof Error ? error.message : String(error)}`)
  process.exit(fails)
}

// ── dsh.bundle ──────────────────────────────────────────────────────────────
console.log('§ dsh.bundle')
const bundlePatch = pkg.dsh?.bundle?.patch
if (typeof bundlePatch === 'string') {
  const patchFile = path.join(dir, bundlePatch)
  if (existsSync(patchFile)) {
    pass(`patch 文件存在: ${bundlePatch}`)
    const patchText = readFileSync(patchFile, 'utf8')
    // cordis.patch.yml 里引用本包名的 row 应与 package.json name 一致
    if (patchText.includes(pkg.name)) pass(`patch row 引用了 ${pkg.name}`)
    else fail(`cordis.patch.yml 中未找到包名 ${pkg.name}（row name 不一致则 Loader 解析不到）`)
  } else fail(`dsh.bundle.patch 指向的文件不存在: ${bundlePatch}`)
} else {
  warn('无 dsh.bundle 声明（纯库可忽略；插件必须有）')
}

// ── exports["."] ────────────────────────────────────────────────────────────
console.log('§ exports["."]')
const mainExport = pkg.exports?.['.']?.default ?? pkg.main
if (typeof mainExport === 'string' && existsSync(path.join(dir, mainExport))) {
  pass(`node half 入口存在: ${mainExport}`)
} else fail(`exports["."].default / main 指向的文件不存在: ${String(mainExport)}`)

// ── dsh.client + 工件契约 ──────────────────────────────────────────────────
console.log('§ dsh.client')
const clientDecl = pkg.dsh?.client
if (clientDecl === undefined) {
  console.log('  [NA] 无浏览器 half')
} else {
  if (clientDecl.platform !== 'web') fail(`dsh.client.platform 应为 "web"，实际 ${JSON.stringify(clientDecl.platform)}`)
  else pass('platform = web')
  if (!Array.isArray(clientDecl.inject) || clientDecl.inject.length === 0) warn('dsh.client.inject 为空（依赖 slot 声明包时应列出）')

  const clientExport = pkg.exports?.['./client']?.default ?? pkg.exports?.['./client']
  if (typeof clientExport !== 'string') {
    fail('声明了 dsh.client 但 exports["./client"] 缺失或非字符串 default')
  } else {
    const clientFile = path.join(dir, clientExport)
    if (!existsSync(clientFile)) {
      fail(`client 工件不存在: ${clientExport}（先构建）`)
    } else {
      pass(`client 工件存在: ${clientExport}`)
      if (clientFile.endsWith('.cjs')) fail('工件后缀是 .cjs——registry 只认 exports 指向路径；"type":"module" 包需 outExtensions 强制 .js')
      else pass('工件后缀 .js')
      const head = readFileSync(clientFile, 'utf8').slice(0, 400)
      const tail = readFileSync(clientFile, 'utf8').slice(-200)
      if (!head.includes('window.__ModuleLoader__.load(')) fail('banner 缺 __ModuleLoader__.load（非 closure-factory 工件）')
      else if (!head.includes('var module = { exports: {} }')) fail('banner 缺 module/exports 构造（浏览器端会 exports is not defined）')
      else pass('banner 契约完整（load + module/exports 构造）')
      if (!tail.includes('return module.exports;')) fail('footer 缺 return module.exports')
      else pass('footer 契约完整')
    }
  }
}

// ── 常规卫生 ────────────────────────────────────────────────────────────────
console.log('§ 卫生')
if (pkg.private !== true && pkg.publishConfig?.access !== 'public' && pkg.name?.startsWith('@')) {
  warn('scoped 包名且未声明 publishConfig.access——将来 npm 发布需 --access public')
}
for (const script of ['build', 'test']) {
  if (pkg.scripts?.[script] === undefined) warn(`缺 scripts.${script}`)
  else pass(`scripts.${script} = ${pkg.scripts[script]}`)
}

console.log(`\n结论: ${fails} FAIL / ${warns} WARN${fails === 0 ? ' — §1 机械层通过' : ' — 修复后重跑'}`)
console.log('人工续做: §2 事实溯源 / §3 契约清单 / §4 文档 / §5 候选绑定验收（见 SKILL.md）')
process.exit(fails)