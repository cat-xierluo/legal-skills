#!/usr/bin/env node
/**
 * load-profile.js - slides 本地配置解析（生成脚本与导出流程共用）
 *
 * 设计约束（见 references/configuration.md）：
 *   - 一次运行只加载一个身份配置，不逐层混合姓名/单位/二维码。
 *   - 相对路径相对于被选配置文件所在目录解析；按当前工作目录猜路径是错误。
 *   - 显式指定的路径错误或 JSON 损坏时直接报错，绝不回退到他人资料。
 *   - show_* = false 时不读取对应图片与来源文件。
 *
 * 解析顺序：
 *   1. 显式 --config / 环境变量 SLIDES_PROFILE
 *   2. 课件项目配置：从工作目录向上查找 .slides/profile.json
 *   3. 技能目录本地配置：<skill>/config/profile.local.json
 *   4. 用户数据目录：$SLIDES_HOME 或 ~/.config/slides/profile.local.json
 *   5. 以上都没有 → 匿名安全默认值
 *
 * USAGE:
 *   node load-profile.js                     # 摘要（来源、启用项、缺失项；不打印个人资料值）
 *   node load-profile.js --json              # 输出解析后的完整配置 JSON（供生成流程消费）
 *   node load-profile.js --field identity.name
 *   node load-profile.js --footer            # 仅输出页脚文本（未配置则空行）
 *   node load-profile.js --assets            # 列出受 show_* 控制且已解析的素材路径
 *   node load-profile.js --config ./my.json  # 显式指定配置
 */

'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');

const SKILL_ROOT = path.resolve(__dirname, '..');
const PROJECT_CONFIG_REL = path.join('.slides', 'profile.json');
const LOCAL_CONFIG_REL = path.join('config', 'profile.local.json');
const DEFAULT_USER_DIR = path.join(os.homedir(), '.config', 'slides');

const SUPPORTED_SCHEMA_VERSIONS = [1];

// ── 匿名安全默认值：没有姓名、联系方式或素材，不生成身份相关页面 ──
const ANONYMOUS_PROFILE = Object.freeze({
  schema_version: 1,
  identity: { name: '', titles: [], organization: '', bio: '' },
  contact: { wechat: '', email: '', website: '' },
  assets: { avatar: '', logo: '', wechat_qr: '', public_account_qr: '', footprint_photos: [] },
  brand: { style: '', custom_style_file: '', footer_text: '', footer_style: 'minimal' },
  presentation: {
    locale: 'zh-CN',
    aspect_ratio: '16:9',
    font_families: [],
    show_profile: false,
    show_footprints: false,
    show_wechat_qr: false,
    show_public_account_qr: false,
    intro_pages: 0,
    closing_mode: 'summary'
  },
  sources: { bio_file: '', footprints_file: '' },
  preferences_file: ''
});

// 素材/来源的开关映射：key → 控制它的 presentation 字段
const ASSET_GATES = {
  avatar: 'show_profile',
  logo: 'show_profile',
  wechat_qr: 'show_wechat_qr',
  public_account_qr: 'show_public_account_qr',
  footprint_photos: 'show_footprints'
};

const SOURCE_GATES = {
  bio_file: 'show_profile',
  footprints_file: 'show_footprints'
};

// 一旦启用就必须存在的素材：二维码是「明确要求展示」的承诺，缺项要阻塞；
// 头像/Logo/照片及来源指针缺失只提示，生成时省略并重排（对应验收矩阵「缺项省略」）。
const ASSET_REQUIRED = {
  wechat_qr: true,
  public_account_qr: true
};

// ── 基础工具 ──────────────────────────────────────────────────────────

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function getUserDir(env = process.env) {
  return path.resolve(env.SLIDES_HOME || DEFAULT_USER_DIR);
}

function isPlainObject(value) {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

/**
 * 从 startDir 向上查找相对路径 rel。
 * 走到用户主目录时检查后停止（避免误命中 / 或 /Users 下的杂散配置）。
 */
function findUp(rel, startDir, { home = os.homedir() } = {}) {
  let dir = path.resolve(startDir);
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const candidate = path.join(dir, rel);
    if (fs.existsSync(candidate)) return candidate;
    if (dir === home) return null;
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

/** 相对路径按 baseDir 解析；绝对路径原样保留。空值返回 null。 */
function resolveFrom(baseDir, value) {
  if (!value || typeof value !== 'string') return null;
  return path.isAbsolute(value) ? value : path.resolve(baseDir, value);
}

// ── 形状校验（不引入 ajv 依赖） ────────────────────────────────────────

const TYPE_MAP = {
  schema_version: 'number',
  identity: 'object',
  contact: 'object',
  assets: 'object',
  brand: 'object',
  presentation: 'object',
  sources: 'object',
  preferences_file: 'string'
};

function validateShape(raw) {
  const errors = [];
  const warnings = [];

  if (!isPlainObject(raw)) {
    return { errors: ['配置根节点必须是 JSON 对象'], warnings };
  }

  for (const [key, expected] of Object.entries(TYPE_MAP)) {
    if (!(key in raw)) continue;
    const value = raw[key];
    const actual = Array.isArray(value) ? 'array' : typeof value;
    if (actual !== expected) {
      errors.push(`${key}: 期望 ${expected}，实际 ${actual}`);
    }
  }

  for (const key of Object.keys(raw)) {
    if (!(key in TYPE_MAP)) {
      warnings.push(`${key}: 未知字段（已忽略，请核对 schema）`);
    }
  }

  if ('schema_version' in raw) {
    if (!SUPPORTED_SCHEMA_VERSIONS.includes(raw.schema_version)) {
      errors.push(
        `schema_version: 不支持的版本 ${JSON.stringify(raw.schema_version)}（支持 ${SUPPORTED_SCHEMA_VERSIONS.join(', ')}）`
      );
    }
  }

  const stringFields = [
    ['identity', ['name', 'organization', 'bio']],
    ['contact', ['wechat', 'email', 'website']],
    ['assets', ['avatar', 'logo', 'wechat_qr', 'public_account_qr']],
    ['brand', ['style', 'custom_style_file', 'footer_text', 'footer_style']],
    ['presentation', ['locale', 'aspect_ratio', 'closing_mode']],
    ['sources', ['bio_file', 'footprints_file']]
  ];
  for (const [section, keys] of stringFields) {
    const obj = raw[section];
    if (!isPlainObject(obj)) continue;
    for (const key of keys) {
      if (key in obj && typeof obj[key] !== 'string') {
        errors.push(`${section}.${key}: 期望 string，实际 ${typeof obj[key]}`);
      }
    }
  }

  const arrayFields = [
    ['identity', 'titles'],
    ['assets', 'footprint_photos'],
    ['presentation', 'font_families']
  ];
  for (const [section, key] of arrayFields) {
    const obj = raw[section];
    if (!isPlainObject(obj) || !(key in obj)) continue;
    if (!Array.isArray(obj[key]) || obj[key].some((v) => typeof v !== 'string')) {
      errors.push(`${section}.${key}: 期望 string[]`);
    }
  }

  const boolFields = [
    'show_profile',
    'show_footprints',
    'show_wechat_qr',
    'show_public_account_qr'
  ];
  if (isPlainObject(raw.presentation)) {
    for (const key of boolFields) {
      if (key in raw.presentation && typeof raw.presentation[key] !== 'boolean') {
        errors.push(`presentation.${key}: 期望 boolean，实际 ${typeof raw.presentation[key]}`);
      }
    }
    if ('intro_pages' in raw.presentation && ![0, 2, 3].includes(raw.presentation.intro_pages)) {
      errors.push(`presentation.intro_pages: 只接受 0 / 2 / 3`);
    }
    if (
      'aspect_ratio' in raw.presentation &&
      !['16:9', '4:3'].includes(raw.presentation.aspect_ratio)
    ) {
      errors.push(`presentation.aspect_ratio: 只接受 16:9 / 4:3`);
    }
    if (
      'closing_mode' in raw.presentation &&
      !['summary', 'thanks', 'none'].includes(raw.presentation.closing_mode)
    ) {
      errors.push(`presentation.closing_mode: 只接受 summary / thanks / none`);
    }
  }

  if (isPlainObject(raw.brand) && 'footer_style' in raw.brand &&
      !['minimal', 'classic', 'modern', ''].includes(raw.brand.footer_style)) {
    errors.push(`brand.footer_style: 只接受 minimal / classic / modern`);
  }

  if (typeof raw.preferences_file !== 'undefined' && typeof raw.preferences_file !== 'string') {
    errors.push('preferences_file: 期望 string');
  }

  return { errors, warnings };
}

/**
 * 用匿名默认值补齐缺失键。只补结构，不引入任何身份信息——
 * 因此不会把两个使用者的姓名/单位/二维码拼在一起。
 */
function fillDefaults(raw) {
  const out = clone(ANONYMOUS_PROFILE);
  const isObj = isPlainObject;
  const sections = ['identity', 'contact', 'assets', 'brand', 'presentation', 'sources'];
  for (const section of sections) {
    if (isObj(raw[section])) {
      for (const [key, value] of Object.entries(raw[section])) {
        out[section][key] = value;
      }
    }
  }
  if (typeof raw.schema_version === 'number') out.schema_version = raw.schema_version;
  if (typeof raw.preferences_file === 'string') out.preferences_file = raw.preferences_file;
  return out;
}

// ── 核心解析 ──────────────────────────────────────────────────────────

/**
 * @param {object} [options]
 * @param {string} [options.configPath] 显式配置路径（相对 cwd 或绝对）
 * @param {string} [options.cwd]        起点目录，默认 process.cwd()
 * @param {object} [options.env]        环境变量，默认 process.env
 * @returns {{profile: object|null, source: string, configPath: string|null,
 *            baseDir: string, warnings: string[], errors: string[]}}
 */
function loadProfile(options = {}) {
  const env = options.env || process.env;
  const cwd = path.resolve(options.cwd || process.cwd());
  const result = {
    profile: null,
    source: 'anonymous',
    configPath: null,
    baseDir: null,
    warnings: [],
    errors: []
  };

  const explicit = options.configPath || env.SLIDES_PROFILE || null;
  let chosen = null;

  if (explicit) {
    const abs = path.resolve(cwd, explicit);
    result.source = 'explicit';
    result.configPath = abs;
    result.baseDir = path.dirname(abs);
    if (!fs.existsSync(abs)) {
      result.errors.push(`显式指定的配置文件不存在: ${abs}`);
      return result;
    }
    chosen = abs;
  } else {
    const projectConfig = findUp(PROJECT_CONFIG_REL, cwd);
    const localConfig = path.join(SKILL_ROOT, LOCAL_CONFIG_REL);
    const userConfig = path.join(getUserDir(env), 'profile.local.json');

    if (projectConfig) {
      chosen = projectConfig;
      result.source = 'project';
    } else if (fs.existsSync(localConfig)) {
      chosen = localConfig;
      result.source = 'skill-local';
    } else if (fs.existsSync(userConfig)) {
      chosen = userConfig;
      result.source = 'user';
    }
  }

  if (!chosen) {
    result.profile = clone(ANONYMOUS_PROFILE);
    result.baseDir = getUserDir(env);
    return result;
  }

  result.configPath = chosen;
  result.baseDir = path.dirname(chosen);

  let raw;
  try {
    raw = JSON.parse(fs.readFileSync(chosen, 'utf-8'));
  } catch (err) {
    // 损坏的 JSON 一律报错，不回退——回退会静默换上另一个人的资料。
    result.errors.push(`配置文件无法解析（${path.basename(chosen)}）: ${err.message}`);
    return result;
  }

  const { errors, warnings } = validateShape(raw);
  result.warnings.push(...warnings);
  if (errors.length > 0) {
    result.errors.push(...errors.map((e) => `配置校验失败 — ${e}`));
    return result;
  }

  result.profile = fillDefaults(raw);
  return result;
}

/**
 * 列出素材解析结果：只包含受 show_* 控制且被启用的项。
 * 关闭的项 enabled=false 且不解析路径（不读取文件）。
 */
function collectAssets(profile, baseDir) {
  const presentation = (profile && profile.presentation) || {};
  const assets = (profile && profile.assets) || {};
  const entries = [];

  for (const key of Object.keys(ASSET_GATES)) {
    const gate = ASSET_GATES[key];
    const enabled = presentation[gate] === true;
    const raw = assets[key];
    const values = Array.isArray(raw) ? raw : raw ? [raw] : [];
    if (!enabled) {
      entries.push({ key, gate, enabled: false, values: [] });
      continue;
    }
    entries.push({
      key,
      gate,
      enabled: true,
      values: values.map((v) => ({
        raw: v,
        resolved: resolveFrom(baseDir, v),
        exists: fs.existsSync(resolveFrom(baseDir, v) || '')
      }))
    });
  }

  return entries;
}

/** 列出权威来源文件：同样受 show_* 控制。 */
function collectSources(profile, baseDir) {
  const presentation = (profile && profile.presentation) || {};
  const sources = (profile && profile.sources) || {};
  const entries = [];

  for (const key of Object.keys(SOURCE_GATES)) {
    const gate = SOURCE_GATES[key];
    const enabled = presentation[gate] === true;
    const raw = sources[key];
    if (!enabled || !raw) {
      entries.push({ key, gate, enabled, raw: raw || '', resolved: null, exists: false });
      continue;
    }
    const resolved = resolveFrom(baseDir, raw);
    entries.push({ key, gate, enabled, raw, resolved, exists: fs.existsSync(resolved) });
  }

  return entries;
}

function getField(profile, dotted) {
  return dotted.split('.').reduce((acc, part) => {
    if (acc === null || acc === undefined) return undefined;
    return acc[part];
  }, profile);
}

/** 摘要只列名称与状态，不打印姓名、微信、简介等资料值。 */
function summarize(loaded) {
  const { profile, source, configPath, baseDir, warnings, errors } = loaded;
  const lines = [];
  const sourceLabels = {
    explicit: '显式指定',
    project: '课件项目配置 (.slides/profile.json)',
    'skill-local': '技能目录本地配置 (config/profile.local.json)',
    user: '用户数据目录 (~/.config/slides/profile.local.json)',
    anonymous: '匿名默认值（未找到任何配置）'
  };
  lines.push(`配置来源: ${sourceLabels[source] || source}`);
  if (configPath) lines.push(`配置文件: ${configPath}`);
  lines.push(`路径基准: ${baseDir}`);

  if (!profile) {
    if (errors.length) {
      lines.push('');
      lines.push('错误:');
      for (const e of errors) lines.push(`  - ${e}`);
    }
    return lines.join('\n');
  }

  const identityFields = ['identity.name', 'identity.organization', 'identity.bio'];
  const present = identityFields.filter((f) => !!getField(profile, f));
  lines.push(`身份字段已填: ${present.length ? present.join(', ') : '（无）'}`);
  lines.push(
    `联系字段已填: ${['contact.wechat', 'contact.email', 'contact.website']
      .filter((f) => !!getField(profile, f))
      .join(', ') || '（无）'}`
  );

  lines.push('');
  lines.push('展示开关:');
  const presentation = profile.presentation || {};
  for (const key of [
    'show_profile',
    'show_footprints',
    'show_wechat_qr',
    'show_public_account_qr'
  ]) {
    lines.push(`  ${key} = ${presentation[key] === true}`);
  }
  lines.push(`  intro_pages = ${presentation.intro_pages}`);
  lines.push(`  closing_mode = ${presentation.closing_mode}`);
  lines.push(`  默认风格 = ${profile.brand?.style || '（未指定）'}`);
  lines.push(`  页脚文本 = ${profile.brand?.footer_text ? '已设置' : '（空）'}`);

  const assetEntries = collectAssets(profile, baseDir);
  const enabledAssets = assetEntries.filter((e) => e.enabled);
  if (enabledAssets.length > 0) {
    lines.push('');
    lines.push('已启用素材:');
    for (const entry of enabledAssets) {
      for (const item of entry.values) {
        lines.push(`  ${entry.key}: ${item.exists ? 'OK' : '缺失'} ${item.resolved}`);
      }
      if (entry.values.length === 0) {
        lines.push(`  ${entry.key}: 已启用但未配置路径`);
      }
    }
  } else {
    lines.push('');
    lines.push('已启用素材: （无——所有 show_* 为 false）');
  }

  const warningsOut = [...warnings];
  for (const entry of enabledAssets) {
    if (entry.values.length === 0) {
      warningsOut.push(`素材 ${entry.key} 已启用但未配置路径`);
    }
    for (const item of entry.values) {
      if (!item.exists) warningsOut.push(`素材 ${entry.key} 路径不可读: ${item.resolved}`);
    }
  }
  if (!profile.preferences_file) {
    warningsOut.push('未配置 preferences_file（可选）');
  }

  if (warningsOut.length > 0) {
    lines.push('');
    lines.push('提示:');
    for (const w of warningsOut) lines.push(`  - ${w}`);
  }
  if (errors.length > 0) {
    lines.push('');
    lines.push('错误:');
    for (const e of errors) lines.push(`  - ${e}`);
  }

  return lines.join('\n');
}

module.exports = {
  SKILL_ROOT,
  DEFAULT_USER_DIR,
  PROJECT_CONFIG_REL,
  LOCAL_CONFIG_REL,
  ANONYMOUS_PROFILE,
  ASSET_GATES,
  SOURCE_GATES,
  ASSET_REQUIRED,
  getUserDir,
  findUp,
  resolveFrom,
  validateShape,
  fillDefaults,
  loadProfile,
  collectAssets,
  collectSources,
  getField,
  summarize
};

// ── CLI ───────────────────────────────────────────────────────────────

function parseArgs(argv) {
  const out = { configPath: null, cwd: null, mode: 'summary', field: null };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--json') out.mode = 'json';
    else if (arg === '--footer') out.mode = 'footer';
    else if (arg === '--assets') out.mode = 'assets';
    else if (arg === '--config') out.configPath = argv[++i];
    else if (arg === '--cwd') out.cwd = argv[++i];
    else if (arg === '--field') {
      out.mode = 'field';
      out.field = argv[++i];
    } else if (arg === '--help' || arg === '-h') out.mode = 'help';
  }
  return out;
}

function main() {
  const args = parseArgs(process.argv.slice(2));

  if (args.mode === 'help') {
    console.log(
      [
        '用法: node load-profile.js [选项]',
        '',
        '  --json               输出解析后的完整配置 JSON',
        '  --field <路径>       输出单个字段，如 identity.name',
        '  --footer             仅输出页脚文本',
        '  --assets             列出已启用素材的解析路径',
        '  --config <路径>      显式指定配置文件',
        '  --cwd <目录>         查找起点（默认当前目录）'
      ].join('\n')
    );
    return;
  }

  const loaded = loadProfile({ configPath: args.configPath, cwd: args.cwd });

  if (args.mode === 'json') {
    if (loaded.profile) {
      console.log(JSON.stringify({
        source: loaded.source,
        configPath: loaded.configPath,
        baseDir: loaded.baseDir,
        profile: loaded.profile
      }, null, 2));
    }
    for (const w of loaded.warnings) console.error(`提示: ${w}`);
    for (const e of loaded.errors) console.error(`错误: ${e}`);
    process.exit(loaded.errors.length > 0 ? 1 : 0);
  }

  if (args.mode === 'field') {
    if (loaded.errors.length > 0) {
      for (const e of loaded.errors) console.error(`错误: ${e}`);
      process.exit(1);
    }
    const value = getField(loaded.profile, args.field);
    if (value === undefined || value === null) process.exit(0);
    console.log(Array.isArray(value) ? value.join('\n') : String(value));
    return;
  }

  if (args.mode === 'footer') {
    if (loaded.errors.length > 0) {
      for (const e of loaded.errors) console.error(`错误: ${e}`);
      process.exit(1);
    }
    console.log(loaded.profile?.brand?.footer_text || '');
    return;
  }

  if (args.mode === 'assets') {
    if (loaded.errors.length > 0) {
      for (const e of loaded.errors) console.error(`错误: ${e}`);
      process.exit(1);
    }
    const entries = collectAssets(loaded.profile, loaded.baseDir);
    for (const entry of entries) {
      if (!entry.enabled) {
        console.log(`${entry.key}\t关闭\t(受 ${entry.gate} 控制)`);
        continue;
      }
      if (entry.values.length === 0) {
        console.log(`${entry.key}\t已启用未配置\t(受 ${entry.gate} 控制)`);
        continue;
      }
      for (const item of entry.values) {
        console.log(`${entry.key}\t${item.exists ? 'OK' : '缺失'}\t${item.resolved}`);
      }
    }
    const sources = collectSources(loaded.profile, loaded.baseDir);
    for (const entry of sources) {
      if (!entry.resolved) {
        console.log(`sources.${entry.key}\t${entry.enabled ? '已启用未配置' : '关闭'}\t(受 ${entry.gate} 控制)`);
        continue;
      }
      console.log(`sources.${entry.key}\t${entry.exists ? 'OK' : '缺失'}\t${entry.resolved}`);
    }
    return;
  }

  console.log(summarize(loaded));
  process.exit(loaded.errors.length > 0 ? 1 : 0);
}

if (require.main === module) main();
