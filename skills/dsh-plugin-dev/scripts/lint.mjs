#!/usr/bin/env node
/**
 * dsh-plugin-lint §1 机械层 v2：声明一致性 + client 工件契约 + harness 溯源 + 版本感知规则。
 * 用法: node lint.mjs <插件目录> [--harness-root <DSH 源码仓库>] [--json]
 *
 * harness 根解析优先级：--harness-root > 环境变量 DSH_HARNESS_ROOT >
 * config/harness-path.local.yaml。解析不到时 harness 依赖项检查标 NOT_VERIFIED（不误判 PASS）。
 *
 * 事实源全部来自当前 harness 源码声明（platform.ts / tsdown.client.ts / ui-theme styles / 包 manifest），
 * 或官方 dsh 可执行门（apps/cli/lib/bin.js --version）；不冻结任何版本号假设。
 *
 * 退出码 = FAIL 数（0 为全过）。语义不确定的结论只出 WARN / NOT_VERIFIED，不出 PASS。
 */

import { execFileSync } from 'node:child_process'
import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs'
import { isBuiltin } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url))
const SKILL_DIR = path.resolve(SCRIPT_DIR, '..')

// ── CLI 参数 ────────────────────────────────────────────────────────────────
function parseArgv(argv) {
  const parsed = { target: undefined, harnessRoot: undefined, json: false }
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]
    if (arg === '--harness-root') {
      parsed.harnessRoot = argv[i + 1]
      i += 1
    } else if (arg.startsWith('--harness-root=')) {
      parsed.harnessRoot = arg.slice('--harness-root='.length)
    } else if (arg === '--json') {
      parsed.json = true
    } else if (parsed.target === undefined) {
      parsed.target = arg
    }
  }
  return parsed
}

const argv = parseArgv(process.argv.slice(2))
const target = argv.target
if (target === undefined || !existsSync(target)) {
  console.error('用法: node lint.mjs <插件目录> [--harness-root <DSH 源码仓库>] [--json]')
  process.exit(1)
}
const dir = path.resolve(target)

// ── 结果收集 ────────────────────────────────────────────────────────────────
let fails = 0
let warns = 0
let notVerified = 0
const findings = []
const emit = (level, message) => {
  findings.push({ level, message })
  if (level === 'FAIL') { fails += 1; console.log(`  [FAIL] ${message}`) }
  else if (level === 'WARN') { warns += 1; console.log(`  [WARN] ${message}`) }
  else if (level === 'NOT_VERIFIED') { notVerified += 1; console.log(`  [NOT_VERIFIED] ${message}`) }
  else console.log(`  [PASS] ${message}`)
}
const fail = (msg) => emit('FAIL', msg)
const pass = (msg) => emit('PASS', msg)
const warn = (msg) => emit('WARN', msg)
const unverifiable = (msg) => emit('NOT_VERIFIED', msg)
const na = (msg) => console.log(`  [NA] ${msg}`)

// ── harness 根解析 ──────────────────────────────────────────────────────────
function readHarnessConfig() {
  const local = path.join(SKILL_DIR, 'config', 'harness-path.local.yaml')
  if (!existsSync(local)) return {}
  const text = readFileSync(local, 'utf8')
  const root = text.match(/^harness_root:\s*["']?([^"'\n#]+)["']?\s*$/m)?.[1]?.trim()
  const baseline = text.match(/^harness_baseline:\s*["']?([^"'\n#]+)["']?\s*$/m)?.[1]?.trim()
  return { root, baseline, configPath: local }
}

function resolveHarnessRoot() {
  if (argv.harnessRoot !== undefined) {
    return { root: path.resolve(argv.harnessRoot), source: '--harness-root 参数' }
  }
  if (process.env.DSH_HARNESS_ROOT) {
    return { root: path.resolve(process.env.DSH_HARNESS_ROOT), source: '环境变量 DSH_HARNESS_ROOT' }
  }
  const config = readHarnessConfig()
  if (config.root) {
    return { root: path.resolve(config.root), source: `config (${path.basename(config.configPath)})`, baseline: config.baseline }
  }
  return { root: undefined, source: '未解析' }
}

const harness = resolveHarnessRoot()
const harnessAvailable = harness.root !== undefined && existsSync(harness.root)

// ── harness 事实源读取 ──────────────────────────────────────────────────────
function runNode(scriptPath, args) {
  return execFileSync(process.execPath, [scriptPath, ...args], { timeout: 20_000, encoding: 'utf8' })
}

function runGit(root, args) {
  return execFileSync('git', ['-C', root, ...args], { timeout: 10_000, encoding: 'utf8' })
}

function readJsonSafe(file) {
  try {
    return JSON.parse(readFileSync(file, 'utf8'))
  } catch {
    return undefined
  }
}

function readTextSafe(file) {
  try {
    return readFileSync(file, 'utf8')
  } catch {
    return undefined
  }
}

/** 平台模块表：来自当前 harness 的 packages/client/web/src/platform.ts 声明。 */
function loadPlatformModules(root) {
  const file = path.join(root, 'packages', 'client', 'web', 'src', 'platform.ts')
  const text = readTextSafe(file)
  if (text === undefined) return undefined
  const extract = (name) => text.match(new RegExp(`${name}\\s*=\\s*\\[([^\\]]*)\\]`, 's'))?.[1] ?? ''
  const literals = [...extract('PLATFORM_MODULES').matchAll(/['"]([^'"]+)['"]/g)].map(m => m[1])
  const preloaded = [...extract('PRELOADED_CLIENT_EXTERNALS').matchAll(/['"]([^'"]+)['"]/g)].map(m => m[1])
  if (literals.length === 0) return undefined
  return { baseline: [...literals, ...preloaded], file }
}

/** 内联安全/内置库正则：来自当前 harness 的 packages/client/tsdown.client.ts 声明。 */
function loadPurityPatterns(root) {
  const file = path.join(root, 'packages', 'client', 'tsdown.client.ts')
  const text = readTextSafe(file)
  if (text === undefined) return undefined
  const extract = (name) => {
    const m = text.match(new RegExp(`(?:export )?const ${name}\\s*=\\s*/((?:\\\\.|[^/\\\\])*)/([a-z]*)`, 's'))
    if (m === null) return undefined
    try {
      return new RegExp(m[1], m[2].replace('g', ''))
    } catch {
      return undefined
    }
  }
  const inlineSafe = extract('INLINE_SAFE')
  const vendored = extract('VENDORED_LIBRARY')
  const generatedRemote = extract('GENERATED_REMOTE')
  if (inlineSafe === undefined && vendored === undefined) return undefined
  return { inlineSafe, vendored, generatedRemote, file }
}

const PLATFORM_DIR = path.join('packages', 'client')

/** harness workspace 内声明了 dsh.client 的包名 → manifest 映射（供 inject 目标核对）。
 *  packages/ 目录缺失时返回 undefined（区别于空索引）——调用方须降级为 NOT_VERIFIED 而非 FAIL。 */
function loadClientPackageIndex(root) {
  const index = new Map()
  const packagesDir = path.join(root, 'packages')
  if (!existsSync(packagesDir)) return undefined
  const walk = (current, depth) => {
    if (depth > 4) return
    let entries
    try {
      entries = readdirSync(current)
    } catch {
      return
    }
    for (const entry of entries) {
      const full = path.join(current, entry)
      let st
      try {
        st = statSync(full)
      } catch {
        continue
      }
      if (st.isDirectory()) {
        walk(full, depth + 1)
      } else if (entry === 'package.json') {
        const manifest = readJsonSafe(full)
        if (manifest?.name !== undefined && manifest.dsh?.client !== undefined) {
          index.set(manifest.name, { manifest, file: full })
        }
      }
    }
  }
  walk(packagesDir, 0)
  return index
}

const platform = harnessAvailable ? loadPlatformModules(harness.root) : undefined
const purity = harnessAvailable ? loadPurityPatterns(harness.root) : undefined
const clientPackages = harnessAvailable ? loadClientPackageIndex(harness.root) : undefined

const harnessProvenance = { root: harness.root, source: harness.source, version: undefined, binVersion: undefined, commit: undefined }
if (harnessAvailable) {
  const rootManifest = readJsonSafe(path.join(harness.root, 'package.json'))
  harnessProvenance.version = typeof rootManifest?.version === 'string' ? rootManifest.version : undefined
  const binJs = path.join(harness.root, 'apps', 'cli', 'lib', 'bin.js')
  if (existsSync(binJs)) {
    try {
      harnessProvenance.binVersion = runNode(binJs, ['--version']).trim()
    } catch {
      harnessProvenance.binVersion = undefined
    }
  }
  try {
    harnessProvenance.commit = runGit(harness.root, ['rev-parse', 'HEAD']).trim()
  } catch {
    harnessProvenance.commit = undefined
  }
}

// ── 工具函数 ────────────────────────────────────────────────────────────────
/** 逐字符剥离 JS/TS 注释（字符串/模板/正则感知），供产物与源码扫描用。 */
function stripJsComments(code) {
  let out = ''
  let i = 0
  const n = code.length
  let prevMeaningful = ''
  while (i < n) {
    const ch = code[i]
    const next = i + 1 < n ? code[i + 1] : ''
    if (ch === '/' && next === '/') {
      while (i < n && code[i] !== '\n') i += 1
      continue
    }
    if (ch === '/' && next === '*') {
      i += 2
      while (i < n && !(code[i] === '*' && i + 1 < n && code[i + 1] === '/')) i += 1
      i += 2
      continue
    }
    if (ch === '\'' || ch === '"') {
      const quote = ch
      out += ch
      i += 1
      while (i < n) {
        if (code[i] === '\\') { out += code.slice(i, i + 2); i += 2; continue }
        out += code[i]
        if (code[i] === quote || code[i] === '\n') { i += 1; break }
        i += 1
      }
      prevMeaningful = quote
      continue
    }
    if (ch === '`') {
      out += ch
      i += 1
      while (i < n) {
        if (code[i] === '\\') { out += code.slice(i, i + 2); i += 2; continue }
        out += code[i]
        if (code[i] === '`') { i += 1; break }
        i += 1
      }
      prevMeaningful = '`'
      continue
    }
    if (ch === '/' && '({[=,:;!&|?<>+-*%~^'.includes(prevMeaningful) || (ch === '/' && prevMeaningful === '')) {
      // 正则字面量启发式：跳过到收尾 /（避免把除号误当正则的常见情形由 prev 约束）
      let j = i + 1
      let closed = false
      let inClass = false
      while (j < n) {
        const c = code[j]
        if (c === '\\') { j += 2; continue }
        if (c === '\n') break
        if (inClass) { if (c === ']') inClass = false }
        else if (c === '[') inClass = true
        else if (c === '/') { closed = true; break }
        j += 1
      }
      if (closed) {
        out += ' '
        i = j + 1
        while (i < n && /[a-z]/i.test(code[i])) i += 1
        prevMeaningful = 'x'
        continue
      }
    }
    out += ch
    if (!/\s/.test(ch)) prevMeaningful = ch
    i += 1
  }
  return out
}

/** stripClientSuffix：与 harness manifest.ts 同语义（<pkg>/client 与 <pkg> 归一）。 */
function stripClientSuffix(spec) {
  return spec.endsWith('/client') ? spec.slice(0, -'/client'.length) : spec
}

/** 从产物/源码中提取 bare require 的模块说明符。 */
function extractBareRequires(js) {
  const code = stripJsComments(js)
  const specs = new Set()
  const re = /(?:^|[^\w$.])require\s*\(\s*(["'])([^"'\n]+?)\1\s*\)/g
  for (const m of code.matchAll(re)) {
    const spec = m[2]
    if (spec.startsWith('.') || spec.startsWith('/') || spec.startsWith('\0')) continue
    specs.add(spec)
  }
  return [...specs]
}

const CJK_RE = /[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/

/** 从 TS/TSX 源提取含 CJK 的字符串字面量与 JSX 文本位置（注释已剥离）。 */
function findHardcodedCopy(tsx) {
  const code = stripJsComments(tsx)
  const literals = []
  const jsxTexts = []
  const attrTexts = []
  const litRe = /(["'])((?:\\.|(?!\1)[^\\])*)\1/g
  for (const m of code.matchAll(litRe)) {
    if (CJK_RE.test(m[2])) literals.push(m[2].trim())
  }
  const tplRe = /`((?:\\.|[^`\\])*)`/g
  for (const m of code.matchAll(tplRe)) {
    if (CJK_RE.test(m[1])) literals.push(m[1].trim())
  }
  const jsxRe = />([^<>{}]*\n?[^<>{}]*)</g
  for (const m of code.matchAll(jsxRe)) {
    if (CJK_RE.test(m[1])) jsxTexts.push(m[1].trim())
  }
  const attrRe = /\b(placeholder|title|aria-label|alt|label)\s*=\s*(["'])((?:\\.|(?!\2)[^\\])*)\2/g
  for (const m of code.matchAll(attrRe)) {
    if (CJK_RE.test(m[3])) attrTexts.push(`${m[1]}="${m[3].trim()}"`)
  }
  return { literals, jsxTexts, attrTexts }
}

/**
 * 从 locale 词典源码静态解析导出对象的完整叶路径集（zh/en 平价校验用；不执行词典代码）。
 * 嵌套对象按 `a.x` 完整路径计入；同文件 const 展开可解析合并；跨文件展开/计算键/
 * 方法简写等不可静态确定形态记入 unsupported——调用方须转 NOT_VERIFIED，不出假 PASS。
 */
function parseDictPaths(source, constName) {
  const code = stripJsComments(source)
  const startMatch = code.match(new RegExp(`(?:export\\s+)?const\\s+${constName}\\s*(?::[^=\\n]+)?=\\s*\\{`))
  if (startMatch === null) return undefined
  const unsupported = []
  let cursor = startMatch.index + startMatch[0].length

  const skipStringAt = (quote) => {
    cursor += 1
    while (cursor < code.length) {
      const c = code[cursor]
      if (c === '\\') { cursor += 2; continue }
      cursor += 1
      if (c === quote || c === '\n') return
    }
  }
  const skipTemplateAt = () => {
    cursor += 1
    let depth = 0
    while (cursor < code.length) {
      const c = code[cursor]
      if (c === '\\') { cursor += 2; continue }
      if (c === '`' && depth === 0) { cursor += 1; return }
      if (c === '$' && code[cursor + 1] === '{') { depth += 1; cursor += 2; continue }
      if (c === '}' && depth > 0) { depth -= 1; cursor += 1; continue }
      if (depth > 0 && (c === '"' || c === "'")) { skipStringAt(c); continue }
      cursor += 1
    }
  }
  const skipBalancedAt = (open, close) => {
    let depth = 0
    while (cursor < code.length) {
      const c = code[cursor]
      if (c === '"' || c === "'") { skipStringAt(c); continue }
      if (c === '`') { skipTemplateAt(); continue }
      if (c === open) depth += 1
      else if (c === close) {
        depth -= 1
        if (depth === 0) { cursor += 1; return }
      }
      cursor += 1
    }
  }
  const skipValueAt = () => {
    let depth = 0
    while (cursor < code.length) {
      const c = code[cursor]
      if (c === '"' || c === "'") { skipStringAt(c); continue }
      if (c === '`') { skipTemplateAt(); continue }
      if (c === '(' || c === '[' || c === '{') { depth += 1; cursor += 1; continue }
      if (c === ')' || c === ']') { depth -= 1; cursor += 1; continue }
      if (c === '}') { if (depth === 0) return; depth -= 1; cursor += 1; continue }
      if (c === ',' && depth === 0) return
      cursor += 1
    }
  }

  /** 解析 code[cursor-1] === '{' 起的对象体，返回 { paths, spreads, closed }。 */
  const parseObject = () => {
    const paths = new Set()
    const spreads = []
    while (cursor < code.length) {
      while (cursor < code.length && /[\s,]/.test(code[cursor])) cursor += 1
      if (cursor >= code.length) break
      const c = code[cursor]
      if (c === '}') { cursor += 1; return { paths, spreads, closed: true } }
      if (code.startsWith('...', cursor)) {
        cursor += 3
        while (cursor < code.length && /\s/.test(code[cursor])) cursor += 1
        const m = /^[A-Za-z_$][\w$]*/.exec(code.slice(cursor))
        if (m === null) { unsupported.push('展开目标不可解析'); skipValueAt(); continue }
        cursor += m[0].length
        if (cursor < code.length && /[.(]/.test(code[cursor])) {
          unsupported.push('展开源为成员表达式/调用，不可静态解析')
          skipValueAt()
          continue
        }
        spreads.push(m[0])
        continue
      }
      if (c === '[') { unsupported.push('计算键'); skipBalancedAt('[', ']'); skipValueAt(); continue }
      let key = null
      if (c === '"' || c === "'") {
        const start = cursor
        skipStringAt(c)
        key = code.slice(start + 1, cursor - 1)
      } else {
        const m = /^[A-Za-z_$][\w$]*|^\d[\d.]*/.exec(code.slice(cursor))
        if (m === null) {
          unsupported.push(`条目起点不可解析: ${JSON.stringify(code.slice(cursor, cursor + 10))}`)
          skipValueAt()
          continue
        }
        key = m[0]
        cursor += m[0].length
      }
      while (cursor < code.length && /\s/.test(code[cursor])) cursor += 1
      if (code[cursor] !== ':') { unsupported.push(`键 ${key} 非简单键值形态（方法简写/getter 等）`); skipValueAt(); continue }
      cursor += 1
      while (cursor < code.length && /\s/.test(code[cursor])) cursor += 1
      if (code[cursor] === '{') {
        cursor += 1
        const sub = parseObject()
        if (!sub.closed) unsupported.push('嵌套对象未闭合')
        if (sub.paths.size === 0) paths.add(key)
        else for (const p of sub.paths) paths.add(`${key}.${p}`)
        spreads.push(...sub.spreads)
      } else {
        paths.add(key)
        skipValueAt()
      }
    }
    unsupported.push('对象未闭合')
    return { paths, spreads, closed: false }
  }

  const root = parseObject()
  // 同文件 const 展开源解析（带循环引用防护）
  const resolved = new Map()
  const resolving = new Set()
  const resolveSpread = (name) => {
    if (resolved.has(name)) return resolved.get(name)
    if (resolving.has(name)) {
      unsupported.push(`展开源 ${name} 循环引用`)
      return { paths: new Set(), spreads: [] }
    }
    resolving.add(name)
    let result = { paths: new Set(), spreads: [] }
    const m = code.match(new RegExp(`(?:export\\s+)?const\\s+${name}\\s*(?::[^=\\n]+)?=\\s*\\{`))
    if (m === null) unsupported.push(`展开源 ${name} 不在同文件（import/运行时构造），键集不完整`)
    else {
      const saved = cursor
      cursor = m.index + m[0].length
      const obj = parseObject()
      if (!obj.closed) unsupported.push(`展开源 ${name} 对象未闭合`)
      for (const s of obj.spreads) {
        const sub = resolveSpread(s)
        for (const p of sub.paths) obj.paths.add(p)
      }
      result = { paths: obj.paths, spreads: [] }
      cursor = saved
    }
    resolving.delete(name)
    resolved.set(name, result)
    return result
  }
  for (const name of root.spreads) {
    const sub = resolveSpread(name)
    for (const p of sub.paths) root.paths.add(p)
  }
  return { paths: root.paths, unsupported }
}

function listClientSourceFiles(rootDir) {
  const files = []
  const clientDir = path.join(rootDir, 'src', 'client')
  const walk = (current) => {
    if (!existsSync(current)) return
    for (const entry of readdirSync(current)) {
      const full = path.join(current, entry)
      if (statSync(full).isDirectory()) walk(full)
      else if (/\.(ts|tsx|js|mjs|jsx|css)$/.test(entry)) files.push(full)
    }
  }
  walk(clientDir)
  return files
}

function rel(file) {
  return path.relative(dir, file).split(path.sep).join('/')
}

// ── 报告头 ──────────────────────────────────────────────────────────────────
console.log(`dsh-plugin-lint v2 — 目标: ${dir}`)
console.log(`harness: ${harnessAvailable ? `${harness.root}（溯源: ${harness.source}）` : '未解析'}`)

// ══ §0 harness 溯源 ═══════════════════════════════════════════════════════
console.log('\n§ 0 harness 溯源')
if (!harnessAvailable) {
  unverifiable('未解析 harness 根：--harness-root / DSH_HARNESS_ROOT / config/harness-path.local.yaml 均未提供；版本相关检查将标 NOT_VERIFIED')
} else {
  const versions = [harnessProvenance.binVersion, harnessProvenance.version].filter(v => v !== undefined)
  const unique = [...new Set(versions)]
  if (unique.length > 1) {
    warn(`官方 dsh 门版本（${harnessProvenance.binVersion}）与根 manifest 版本（${harnessProvenance.version}）不一致——以官方门为准并核对 harness 构建新鲜度`)
  }
  if (unique.length === 0) {
    unverifiable('无法读取 harness 版本（根 package.json 与 apps/cli/lib/bin.js 均不可用）')
  } else {
    harnessProvenance.dshVersion = unique[0]
    pass(`DSH 版本 = ${unique[0]}${harnessProvenance.binVersion !== undefined ? '（官方 dsh --version 门）' : ''}`)
  }
  if (harnessProvenance.commit !== undefined) pass(`harness git commit = ${harnessProvenance.commit}`)
  else unverifiable('harness 所在目录不是 git 仓库或 git 不可用，commit 未知')
  if (platform === undefined) unverifiable('无法从 packages/client/web/src/platform.ts 解析平台模块表——基线对账类检查降级')
  else pass(`平台模块表 ${platform.baseline.length} 项（${path.relative(harness.root, platform.file)}）`)
  if (purity === undefined) unverifiable('无法从 packages/client/tsdown.client.ts 解析内联安全正则——纯度复核降级')
  if (clientPackages === undefined) unverifiable('harness packages/ 目录不可读——inject 目标 workspace 侧核验降级')
  if (harness.baseline !== undefined && harnessProvenance.dshVersion !== undefined && harness.baseline !== harnessProvenance.dshVersion) {
    warn(`config 声明的基线版本 ${harness.baseline} 与当前 harness 版本 ${harnessProvenance.dshVersion} 不一致——先复核规范再审查`)
  }
}

// ══ §1 package.json ═══════════════════════════════════════════════════════
console.log('\n§ 1 package.json')
let pkg
try {
  pkg = JSON.parse(readFileSync(path.join(dir, 'package.json'), 'utf8'))
  pass(`name = ${pkg.name}`)
} catch (error) {
  fail(`package.json 解析失败: ${error instanceof Error ? error.message : String(error)}`)
  console.log(`\n结论: ${fails} FAIL / ${warns} WARN / ${notVerified} NOT_VERIFIED — 修复后重跑`)
  process.exit(fails)
}

// DSH 依赖与当前 harness 版本漂移（cordis 等独立版本线包不参与对账）
if (harnessProvenance.dshVersion !== undefined) {
  const depSections = ['dependencies', 'devDependencies', 'peerDependencies']
  const drifted = []
  for (const section of depSections) {
    for (const [name, range] of Object.entries(pkg[section] ?? {})) {
      if (!name.startsWith('@deepseek-ai/dsh-')) continue
      const pinned = String(range).match(/^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/)?.[0]
      if (pinned !== undefined && pinned !== harnessProvenance.dshVersion) drifted.push(`${name}@${range}`)
    }
  }
  if (drifted.length > 0) warn(`以下 @deepseek-ai/dsh-* 依赖钉定版本与当前 harness ${harnessProvenance.dshVersion} 不同: ${drifted.join(', ')}`)
  else pass('@deepseek-ai/dsh-* 依赖钉定版本与当前 harness 版本一致')
}

// ══ §2 dsh.bundle ═════════════════════════════════════════════════════════
console.log('\n§ 2 dsh.bundle')
const bundlePatch = pkg.dsh?.bundle?.patch
if (typeof bundlePatch === 'string') {
  const patchFile = path.join(dir, bundlePatch)
  if (existsSync(patchFile)) {
    pass(`patch 文件存在: ${bundlePatch}`)
    const patchText = readFileSync(patchFile, 'utf8')
    // 区分文本出现与有效声明：剥除注释行与空行后，核 id/name 声明值（结构不可辨时转人工，不出假 PASS）
    const nonComment = patchText.split('\n').filter(line => !/^\s*(?:#.*)?$/.test(line)).join('\n')
    const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const nameValueRe = new RegExp(`(?:^|\\n)[ \\t]*(?:id|name)[ \\t]*:[ \\t]*['"]?${escapeRe(pkg.name)}['"]?[ \\t]*(?:$|\\n|#)`)
    const rowStartRe = /^\s*-\s*\w|^\s*\w+\s*:/m
    if (!nonComment.trim()) {
      fail(`cordis.patch.yml 无有效声明行（仅注释/空行）——宿主不会装载 ${pkg.name}`)
    } else if (nameValueRe.test(nonComment)) {
      pass(`patch row 引用了 ${pkg.name}（id/name 声明值）`)
    } else if (!rowStartRe.test(nonComment)) {
      unverifiable(`patch 结构无法机械解析（未识别到 insert/键值行）——转人工核对 ${pkg.name} 的 row 声明`)
    } else if (nonComment.includes(pkg.name)) {
      unverifiable(`包名 ${pkg.name} 出现在非 id/name 声明位置——转人工核对 patch row`)
    } else {
      fail(`cordis.patch.yml 中未找到 ${pkg.name} 的有效声明行（row name 不一致则 Loader 解析不到）`)
    }
  } else fail(`dsh.bundle.patch 指向的文件不存在: ${bundlePatch}`)
} else {
  warn('无 dsh.bundle 声明（纯库可忽略；插件必须有）')
}

// ══ §3 exports["."] ═══════════════════════════════════════════════════════
console.log('\n§ 3 exports["."]')
/** 按 Node 语义解析 exports["."]：字符串 / default / node>import>require>default 条件 / fallback 数组。
 *  无法机械解析的条件形态返回 undefined——调用方转 NOT_VERIFIED，不误判 FAIL 也不出假 PASS。 */
function resolveDotExportValue(spec, depth = 0) {
  if (depth > 6 || spec === null || spec === undefined) return undefined
  if (typeof spec === 'string') return spec
  if (Array.isArray(spec)) {
    for (const item of spec) {
      const r = resolveDotExportValue(item, depth + 1)
      if (r !== undefined) return r
    }
    return undefined
  }
  if (typeof spec === 'object') {
    if (Object.prototype.hasOwnProperty.call(spec, 'default')) {
      const r = resolveDotExportValue(spec.default, depth + 1)
      if (r !== undefined) return r
    }
    for (const cond of ['node', 'import', 'require', 'default']) {
      if (cond !== 'default' && Object.prototype.hasOwnProperty.call(spec, cond)) {
        const r = resolveDotExportValue(spec[cond], depth + 1)
        if (r !== undefined) return r
      }
    }
    return undefined
  }
  return undefined
}
const dotExportRaw = typeof pkg.exports === 'string'
  ? pkg.exports
  : (pkg.exports !== null && typeof pkg.exports === 'object' && !Array.isArray(pkg.exports) ? pkg.exports['.'] : undefined)
let mainExport
if (dotExportRaw !== undefined) {
  const resolvedEntry = resolveDotExportValue(dotExportRaw)
  if (typeof resolvedEntry === 'string') mainExport = resolvedEntry
  else {
    unverifiable('exports["."] 为无法机械解析的条件导出形态——入口转人工（可 node --input-type=module -e \'import("<pkg>").then(...)\' 验证）')
    mainExport = undefined
  }
} else {
  mainExport = pkg.main
}
if (mainExport === undefined && dotExportRaw !== undefined) {
  // 已转 NOT_VERIFIED，跳过存在性判定
} else if (typeof mainExport === 'string' && existsSync(path.join(dir, mainExport))) {
  pass(`node half 入口存在: ${mainExport}`)
} else {
  fail(`exports["."].default / main 指向的文件不存在: ${String(mainExport)}`)
}

// ══ §4 dsh.client + inject/external 对账 ══════════════════════════════════
console.log('\n§ 4 dsh.client（inject/external 对账）')
const clientDecl = pkg.dsh?.client
const declaredExternal = new Set()
if (clientDecl === undefined) {
  na('无浏览器 half')
} else {
  if (clientDecl.platform !== 'web') fail(`dsh.client.platform 应为 "web"，实际 ${JSON.stringify(clientDecl.platform)}`)
  else pass('platform = web')
  if (!Array.isArray(clientDecl.inject) || clientDecl.inject.length === 0) warn('dsh.client.inject 为空（依赖 slot 声明包时应列出）')

  const inject = Array.isArray(clientDecl.inject) ? clientDecl.inject : []
  for (const entry of inject) {
    if (typeof entry !== 'string' || entry.length === 0) {
      fail(`dsh.client.inject 含非字符串项: ${JSON.stringify(entry)}`)
      continue
    }
    if (entry === pkg.name) fail('dsh.client.inject 声明了自身包名（自注入边）')
    const inHarness = clientPackages !== undefined && clientPackages.has(entry)
    const localManifest = readJsonSafe(path.join(dir, 'node_modules', entry, 'package.json'))
    if (inHarness || localManifest?.dsh?.client !== undefined) {
      pass(`inject 目标声明了 dsh.client: ${entry}${inHarness ? '（harness workspace）' : '（本地 node_modules）'}`)
    } else if (clientPackages === undefined) {
      unverifiable(`inject 目标 ${entry} 无法核验——harness workspace 包索引不可用（本地 node_modules 亦未见 dsh.client 声明）`)
    } else {
      fail(`inject 目标 ${entry} 在 harness workspace 与本地 node_modules 均未声明 dsh.client——该边永远等不到工厂`)
    }
    const devDeps = pkg.devDependencies ?? {}
    if (devDeps[entry] === undefined && pkg.dependencies?.[entry] === undefined) {
      warn(`inject 目标 ${entry} 不在 dependencies/devDependencies（类型声明双保险缺失）`)
    }
  }

  if (clientDecl.external !== undefined && !Array.isArray(clientDecl.external)) {
    fail('dsh.client.external 存在但不是字符串数组（harness 会整包拒绝激活）')
  } else if (Array.isArray(clientDecl.external)) {
    for (const entry of clientDecl.external) {
      if (typeof entry !== 'string' || entry.length === 0) {
        fail(`dsh.client.external 含非字符串项: ${JSON.stringify(entry)}`)
        continue
      }
      declaredExternal.add(entry)
      if (entry === pkg.name || stripClientSuffix(entry) === pkg.name) {
        fail('dsh.client.external 声明了自身包名（harness 会抛错拒绝启动）')
      }
      if (platform !== undefined && (platform.baseline.includes(entry) || platform.baseline.includes(stripClientSuffix(entry)))) {
        warn(`dsh.client.external "${entry}" 已在平台基线中（基线请求是隐式的，声明为冗余行）`)
      }
    }
  }
}

// ══ §5 client 工件契约 + 产物 bare require 对账 ═══════════════════════════
console.log('\n§ 5 client 工件（banner/footer/后缀/bare require）')
const clientExport = pkg.exports?.['./client']?.default ?? pkg.exports?.['./client']
let artifactText
if (clientDecl !== undefined) {
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
      artifactText = readFileSync(clientFile, 'utf8')
      const head = artifactText.slice(0, 4000)
      const tail = artifactText.slice(-2000)
      if (!head.includes('window.__ModuleLoader__.load(')) fail('banner 缺 __ModuleLoader__.load（非 closure-factory 工件）')
      else if (!head.includes('var module = { exports: {} }')) fail('banner 缺 module/exports 构造（浏览器端会 exports is not defined）')
      else pass('banner 契约完整（load + module/exports 构造）')
      if (!tail.includes('return module.exports;')) fail('footer 缺 return module.exports')
      else pass('footer 契约完整')

      // bare require ↔ 平台基线 / dsh.client.external 对账
      const bare = extractBareRequires(artifactText)
      const builtins = []
      let externalsOk = 0
      const unknowns = []
      const unknownNeedsPlatform = []
      const impure = []
      for (const spec of bare) {
        if (isBuiltin(spec) || spec.startsWith('node:')) { builtins.push(spec); continue }
        const normalized = stripClientSuffix(spec)
        if (
          platform !== undefined
          && (platform.baseline.includes(spec) || platform.baseline.includes(normalized))
        ) { externalsOk += 1; continue }
        if (declaredExternal.has(spec) || declaredExternal.has(normalized)) { externalsOk += 1; continue }
        if (
          purity !== undefined
          && ((purity.inlineSafe?.test(spec) ?? false) || (purity.vendored?.test(spec) ?? false) || (purity.generatedRemote?.test(spec) ?? false))
        ) { impure.push(spec); continue }
        if (platform === undefined) unknownNeedsPlatform.push(spec)
        else unknowns.push(spec)
      }
      if (externalsOk > 0) pass(`bare require 与模块表对账通过 ${externalsOk} 项`)
      if (unknowns.length > 0) {
        for (const spec of unknowns) {
          fail(`产物 bare require("${spec}") 不在平台基线也不在 dsh.client.external——模块表无法应答，浏览器端必抛`)
        }
      }
      if (unknownNeedsPlatform.length > 0) {
        for (const spec of unknownNeedsPlatform) {
          unverifiable(`平台模块表不可用——bare require("${spec}") 无法与基线/声明对账（不判 FAIL，补 --harness-root 后重跑）`)
        }
      }
      if (impure.length > 0) {
        for (const spec of impure) {
          fail(`产物 bare require("${spec}") 属内联安全层却被外置——构建 externals 配置与 dsh.client 声明不一致`)
        }
      }
      if (builtins.length > 0) {
        warn(`产物含 bare builtin require: ${[...new Set(builtins)].join(', ')}——若位于 inliner 的 try/catch 特征探测内则合法，须人工确认未被顶层依赖`)
      }
      for (const entry of declaredExternal) {
        const normalized = stripClientSuffix(entry)
        const used = bare.some(spec => spec === entry || stripClientSuffix(spec) === normalized)
        if (!used) warn(`dsh.client.external "${entry}" 在产物中没有任何对应 require（冗余声明行，徒增 boot 图边）`)
      }
    }
  }
}

// 构建配置 externals ↔ 平台基线对账（mission: inject/external 声明与构建 externals 的一致性）
const buildConfigFile = ['tsdown.client.config.ts', 'tsdown.config.ts', 'tsdown.client.ts']
  .map(name => path.join(dir, name))
  .find(file => existsSync(file))
if (clientDecl !== undefined && buildConfigFile !== undefined) {
  const configText = readTextSafe(buildConfigFile) ?? ''
  // 只取 externals 语义的声明体：*external*/EXTERNAL 命名的 Set/数组字面量，或 neverBundle/external 的内联数组。
  // deps.alwaysBundle 是强制内联（tsdown 语义，与 external 方向相反），单独收集，不入 external 集。
  const bodies = []
  for (const m of configText.matchAll(/[\w$]*external[\w$]*\s*(?::[^=\n]*)?=\s*(?:new\s+Set\s*\(\s*)?\[([^\]]*)\]/gi)) bodies.push(m[1])
  for (const m of configText.matchAll(/\b(?:neverBundle|external)\s*:\s*\[([^\]]*)\]/g)) bodies.push(m[1])
  const stringSpecs = (body) => [...body.matchAll(/['"]([^'"]+)['"]/g)]
    .map(m => m[1])
    .filter(spec => !/\.(ts|tsx|js|mjs|cjs|css|json|yml|yaml)$/.test(spec))
  const configExternals = new Set(bodies.flatMap(stringSpecs))
  const alwaysBundleSpecs = new Set([...configText.matchAll(/\balwaysBundle\s*:\s*\[([^\]]*)\]/g)].flatMap(m => stringSpecs(m[1])))
  for (const spec of alwaysBundleSpecs) {
    if (declaredExternal.has(spec) || declaredExternal.has(stripClientSuffix(spec))) {
      fail(`构建配置把 "${spec}" 声明为 alwaysBundle 强制内联，dsh.client.external 又声明为外置——方向冲突，运行时模块表与产物必不一致`)
    }
  }
  if (bodies.length === 0) {
    warn(`构建配置 ${path.basename(buildConfigFile)} 未找到 externals 声明体（external/neverBundle 命名的 Set 或数组）——构建侧对账转人工`)
  } else {
    const unknown = [...configExternals].filter(spec =>
      !isBuiltin(spec)
      && !(platform !== undefined && (platform.baseline.includes(spec) || platform.baseline.includes(stripClientSuffix(spec))))
      && !declaredExternal.has(spec) && !declaredExternal.has(stripClientSuffix(spec)))
    if (platform === undefined) {
      for (const spec of unknown) {
        unverifiable(`平台模块表不可用——构建配置标为 external 的 "${spec}" 无法判定是否基线项，转人工`)
      }
      if (unknown.length === 0) pass(`构建配置 external 集 ⊆ dsh.client.external（${path.basename(buildConfigFile)}，${configExternals.size} 项；平台基线不可用未参与判定）`)
    } else if (unknown.length > 0) {
      for (const spec of unknown) {
        fail(`构建配置 ${path.basename(buildConfigFile)} 把 "${spec}" 标为 external，但既非平台基线也未声明 dsh.client.external——运行时模块表无法应答`)
      }
    } else {
      pass(`构建配置 external 集 ⊆ 平台基线 ∪ dsh.client.external（${path.basename(buildConfigFile)}，${configExternals.size} 项）`)
    }
  }
}

// ══ §6 主题变量 ═══════════════════════════════════════════════════════════
console.log('\n§ 6 主题变量（DSH 声明集对账）')
const DSH_VAR_PREFIXES = ['--dsw-', '--ds-', '--shiki-']
const harnessThemeDir = harnessAvailable ? path.join(harness.root, 'packages', 'client', 'ui-theme', 'src', 'styles') : undefined
const harnessVars = new Set()
if (harnessThemeDir !== undefined && existsSync(harnessThemeDir)) {
  for (const entry of readdirSync(harnessThemeDir)) {
    if (!entry.endsWith('.css')) continue
    const text = readFileSync(path.join(harnessThemeDir, entry), 'utf8')
    for (const m of text.matchAll(/(--[A-Za-z0-9-]+)\s*:/g)) harnessVars.add(m[1])
  }
} else if (harnessAvailable) {
  unverifiable(`未找到 harness 主题声明目录 ${path.relative(harness.root, harnessThemeDir ?? '')}——主题变量对账不可用`)
}

const pluginFiles = listClientSourceFiles(dir)
if (pluginFiles.length > 0) {
  pass(`client 源扫描: ${pluginFiles.length} 文件（范围 src/client，扩展名 ts/tsx/js/mjs/jsx/css）`)
} else {
  warn('src/client 未发现 ts/tsx/js/mjs/jsx/css 源——其他源布局（如 lib/client）不在机械扫描范围：主题变量/文案/locale 检查未覆盖（不等于无违规），转人工')
}
const pluginDeclared = new Set()
const pluginUsed = new Map()
for (const file of pluginFiles) {
  const text = readFileSync(file, 'utf8')
  const code = file.endsWith('.css') ? text.replace(/\/\*[\s\S]*?\*\//g, '') : stripJsComments(text)
  for (const m of code.matchAll(/(--[A-Za-z0-9-]+)\s*:/g)) pluginDeclared.add(m[1])
  for (const m of code.matchAll(/var\(\s*(--[A-Za-z0-9-]+)/g)) {
    if (!pluginUsed.has(m[1])) pluginUsed.set(m[1], [])
    pluginUsed.get(m[1]).push(rel(file))
  }
}
if (pluginUsed.size === 0) {
  na('client 源未使用任何 var(--) 主题变量')
} else if (!harnessAvailable || (harnessVars.size === 0 && harnessThemeDir !== undefined && !existsSync(harnessThemeDir))) {
  unverifiable(`client 源使用了 ${pluginUsed.size} 个主题变量，但 harness 主题声明集不可用——无法对账`)
} else {
  let okCount = 0
  for (const [varName, files] of [...pluginUsed].sort()) {
    if (!DSH_VAR_PREFIXES.some(prefix => varName.startsWith(prefix))) continue
    if (harnessVars.has(varName) || pluginDeclared.has(varName)) { okCount += 1; continue }
    fail(`不存在的 DSH 主题变量 ${varName}（harness 主题声明集与插件自身声明均无；回退值会掩盖主题断链）——使用处: ${[...new Set(files)].join(', ')}`)
  }
  if (okCount > 0) pass(`DSH 主题变量引用对账通过 ${okCount} 项`)
}

// ══ §7 文案与类型化 locale ════════════════════════════════════════════════
console.log('\n§ 7 文案与类型化 locale')
const isExempt = (file) => {
  const base = path.basename(file)
  const relPath = rel(file)
  return /(^|[/.])locales?[/.]/.test(relPath) || /locales\.(ts|tsx|js|mjs)$/.test(base) || /\.(spec|test)\./.test(base)
}
const copyFiles = pluginFiles.filter(file => !isExempt(file))
const cjkFiles = []
for (const file of copyFiles) {
  const text = readFileSync(file, 'utf8')
  const copy = findHardcodedCopy(text)
  if (copy.jsxTexts.length > 0) {
    fail(`JSX 文本位置硬编码文案（应走类型化 locale）: ${rel(file)} — 例: ${JSON.stringify(copy.jsxTexts[0])}（共 ${copy.jsxTexts.length} 处）`)
  }
  if (copy.attrTexts.length > 0) {
    fail(`用户可见属性硬编码文案: ${rel(file)} — ${copy.attrTexts.slice(0, 3).join('; ')}（共 ${copy.attrTexts.length} 处）`)
  }
  if (copy.literals.length > 0) {
    cjkFiles.push({ file, samples: copy.literals, count: copy.literals.length })
  }
}
for (const { file, samples, count } of cjkFiles) {
  warn(`源码含 CJK 字符串字面量 ${count} 处（若渲染为产品文案需迁入 locale 词典）: ${rel(file)} — 例: ${JSON.stringify(samples[0])}`)
}

// zh/en 词典平价（类型化 locale 所有权正向检查；按完整叶路径比较，不可静态解析形态转人工）
const dictCandidates = [
  path.join(dir, 'src', 'client', 'locales.ts'),
  path.join(dir, 'src', 'client', 'locales.js'),
  path.join(dir, 'src', 'client', 'locales', 'zh.ts'),
  path.join(dir, 'src', 'client', 'locales', 'zh.js'),
]
const dictFile = dictCandidates.find(file => existsSync(file))
if (dictFile !== undefined) {
  const zhParsed = parseDictPaths(readFileSync(dictFile, 'utf8'), 'zh')
  let enParsed
  if (/^locales\.[a-z]+$/.test(path.basename(dictFile))) {
    enParsed = parseDictPaths(readFileSync(dictFile, 'utf8'), 'en')
  } else {
    const enFile = path.join(path.dirname(dictFile), `en${path.extname(dictFile)}`)
    enParsed = existsSync(enFile) ? parseDictPaths(readFileSync(enFile, 'utf8'), 'en') : undefined
  }
  if (zhParsed === undefined || enParsed === undefined) {
    unverifiable(`locale 词典存在但未找到可解析的 zh/en 导出对象: ${rel(dictFile)}（转人工核对 en 是否对齐 zh 键集）`)
  } else if (zhParsed.unsupported.length > 0 || enParsed.unsupported.length > 0) {
    const reasons = [...new Set([...zhParsed.unsupported, ...enParsed.unsupported])].join('；')
    unverifiable(`locale 词典存在不可静态解析形态（${reasons}）——键集平价转人工: ${rel(dictFile)}`)
  } else {
    const zhKeys = zhParsed.paths
    const enKeys = enParsed.paths
    const missingInEn = [...zhKeys].filter(key => !enKeys.has(key)).sort()
    const extraInEn = [...enKeys].filter(key => !zhKeys.has(key)).sort()
    if (missingInEn.length > 0 || extraInEn.length > 0) {
      fail(`locale 词典 zh/en 键集不平价（完整叶路径）: en 缺 [${missingInEn.join(', ')}] en 多 [${extraInEn.join(', ')}]（en 必须对齐 zh 键集）`)
    } else {
      pass(`locale 词典 zh/en 键集平价（${zhKeys.size} 叶路径，含嵌套完整路径）`)
    }
  }
}

// ══ §8 常规卫生 ═══════════════════════════════════════════════════════════
console.log('\n§ 8 卫生')
if (pkg.private !== true && pkg.publishConfig?.access !== 'public' && pkg.name?.startsWith('@')) {
  warn('scoped 包名且未声明 publishConfig.access——将来 npm 发布需 --access public')
}
for (const script of ['build', 'test']) {
  if (pkg.scripts?.[script] === undefined) warn(`缺 scripts.${script}`)
  else pass(`scripts.${script} = ${pkg.scripts[script]}`)
}

// ══ §9 文档版本声明 ═══════════════════════════════════════════════════════
console.log('\n§ 9 文档版本声明')
const FROZEN_PATTERNS = [
  { re: /0\.1\.0-rc\.\d+/g, why: '冻结的 0.1.0-rc.x 版本假设' },
  { re: /dsh-client-runtime(?![-\w])/g, why: '引用已移除的平台模块 dsh-client-runtime（0.1.2 起移除）' },
]
const docFiles = ['README.md', 'AGENTS.md', 'CLAUDE.md']
const docsDir = path.join(dir, 'docs')
if (existsSync(docsDir)) {
  const walk = (current, depth) => {
    if (depth > 3) return
    for (const entry of readdirSync(current)) {
      const full = path.join(current, entry)
      if (statSync(full).isDirectory()) {
        if (path.basename(full) !== 'acceptance') walk(full, depth + 1)
      } else if (entry.endsWith('.md') && entry !== 'CHANGELOG.md') docFiles.push(path.relative(dir, full))
    }
  }
  walk(docsDir, 0)
}
const docHits = []
for (const relPath of docFiles) {
  const full = path.join(dir, relPath)
  const text = readTextSafe(full)
  if (text === undefined) continue
  for (const { re, why } of FROZEN_PATTERNS) {
    re.lastIndex = 0
    for (const m of text.matchAll(re)) {
      const lineNo = text.slice(0, m.index).split('\n').length
      docHits.push(`${relPath}:${lineNo} ${why}（"${m[0]}"）`)
    }
  }
}
if (docHits.length > 0) {
  warn(`当前态文档存在过期版本声明 ${docHits.length} 处（CHANGELOG 与 acceptance 证据不在此列）— 例: ${docHits[0]}`)
} else {
  pass('当前态文档无冻结版本声明')
}

// ── 结论 ───────────────────────────────────────────────────────────────────
console.log(`\n结论: ${fails} FAIL / ${warns} WARN / ${notVerified} NOT_VERIFIED${fails === 0 ? ' — §1 机械层通过' : ' — 修复后重跑'}`)
console.log('人工续做: §2 事实溯源 / §3 契约清单 / §4 文档 / §5 候选绑定验收（见 SKILL.md）')

if (argv.json) {
  console.log(`__DSH_LINT_JSON__${JSON.stringify({
    target: dir,
    harness: harnessProvenance,
    fails,
    warns,
    notVerified,
    findings,
  })}`)
}
process.exit(fails)
