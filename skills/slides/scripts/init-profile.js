#!/usr/bin/env node
/**
 * init-profile.js - 初始化 slides 本地配置
 *
 * 两种用法：
 *   A. Agent 引导（无输入参数）：打印需要向使用者收集的字段清单，供 Agent 逐项询问后
 *      再用非交互参数回填。不会自行扫描磁盘寻找头像、二维码或通讯录。
 *   B. 非交互回填：用下方参数一次性写入，或用 --from-json 整份导入。
 *
 * USAGE:
 *   node init-profile.js                                  # 引导模式：打印提问清单
 *   node init-profile.js --name 张三 --organization 某某律所 --wechat-qr ./wx.png
 *   node init-profile.js --from-json ./my-profile.json
 *   echo '{...}' | node init-profile.js --from-json -
 *   node init-profile.js --dir ~/.config/slides --force
 *
 * 默认写入用户数据目录（$SLIDES_HOME 或 ~/.config/slides/profile.local.json），
 * 避免技能升级或重装丢失。--skill-local 写入技能目录（便携安装用，发布时须排除）。
 * 目标已存在且未加 --force 时拒绝覆盖。
 */

'use strict';

const fs = require('fs');
const path = require('path');

const {
  SKILL_ROOT,
  LOCAL_CONFIG_REL,
  ANONYMOUS_PROFILE,
  getUserDir,
  validateShape,
  fillDefaults,
  collectAssets,
  collectSources
} = require('./load-profile');

const GUIDE = `slides 配置初始化 — 需要向使用者收集的字段（每项都可以跳过）

1. 身份（可留空）
   --name <姓名>
   --title <头衔>            （可重复，如：律师 / 专利代理师）
   --organization <单位>
   --bio <一句话简介>         （不要写会变动的统计数字）

2. 联系方式（可留空）
   --email <邮箱>  --wechat <微信号>  --website <网站>

3. 素材路径（有就填；区分个人微信与公众号，不必人人都有两张码）
   --avatar <头像图片路径>
   --logo <Logo 路径>
   --wechat-qr <微信二维码路径>
   --public-account-qr <公众号二维码路径>
   --footprint-photo <授课现场照片路径>   （可重复）

4. 展示开关（默认全部关闭）
   --profile-pages <0|2|3>   介绍页数，0=不生成
   --closing <summary|thanks|none>
   --show-profile / --hide-profile
   --show-footprints / --hide-footprints
   --show-wechat-qr / --hide-wechat-qr
   --show-public-account-qr / --hide-public-account-qr

5. 品牌与偏好（可留空）
   --style <默认风格名>       （对应 references/styles/*.json 的 name）
   --custom-style-file <个人风格 JSON 路径>
   --footer-text <页脚文本>
   --footer-style <minimal|classic|modern>
   --preferences-file <个人偏好说明文件路径>

6. 权威来源（只作核对入口，不内联内容）
   --bio-file <个人介绍来源文件>
   --footprints-file <授课足迹来源文件>

写入位置：默认 ~/.config/slides/profile.local.json（可用 --dir 或 --skill-local 改变）。
收集完成后重新运行本脚本并带上上述参数即可落盘。`;

function parseArgs(argv) {
  const out = {
    overrides: { identity: {}, contact: {}, assets: {}, brand: {}, presentation: {}, sources: {} },
    titles: [],
    footprintPhotos: [],
    fromJson: null,
    dir: null,
    out: null,
    skillLocal: false,
    force: false,
    dryRun: false,
    help: false
  };
  const next = (i) => argv[i + 1];
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    switch (arg) {
      case '--name': out.overrides.identity.name = next(i); i++; break;
      case '--title': out.titles.push(next(i)); i++; break;
      case '--organization': out.overrides.identity.organization = next(i); i++; break;
      case '--bio': out.overrides.identity.bio = next(i); i++; break;
      case '--email': out.overrides.contact.email = next(i); i++; break;
      case '--wechat': out.overrides.contact.wechat = next(i); i++; break;
      case '--website': out.overrides.contact.website = next(i); i++; break;
      case '--avatar': out.overrides.assets.avatar = next(i); i++; break;
      case '--logo': out.overrides.assets.logo = next(i); i++; break;
      case '--wechat-qr': out.overrides.assets.wechat_qr = next(i); i++; break;
      case '--public-account-qr': out.overrides.assets.public_account_qr = next(i); i++; break;
      case '--footprint-photo': out.footprintPhotos.push(next(i)); i++; break;
      case '--style': out.overrides.brand.style = next(i); i++; break;
      case '--custom-style-file': out.overrides.brand.custom_style_file = next(i); i++; break;
      case '--footer-text': out.overrides.brand.footer_text = next(i); i++; break;
      case '--footer-style': out.overrides.brand.footer_style = next(i); i++; break;
      case '--profile-pages': out.overrides.presentation.intro_pages = Number(next(i)); i++; break;
      case '--closing': out.overrides.presentation.closing_mode = next(i); i++; break;
      case '--show-profile': out.overrides.presentation.show_profile = true; break;
      case '--hide-profile': out.overrides.presentation.show_profile = false; break;
      case '--show-footprints': out.overrides.presentation.show_footprints = true; break;
      case '--hide-footprints': out.overrides.presentation.show_footprints = false; break;
      case '--show-wechat-qr': out.overrides.presentation.show_wechat_qr = true; break;
      case '--hide-wechat-qr': out.overrides.presentation.show_wechat_qr = false; break;
      case '--show-public-account-qr': out.overrides.presentation.show_public_account_qr = true; break;
      case '--hide-public-account-qr': out.overrides.presentation.show_public_account_qr = false; break;
      case '--bio-file': out.overrides.sources.bio_file = next(i); i++; break;
      case '--footprints-file': out.overrides.sources.footprints_file = next(i); i++; break;
      case '--preferences-file': out.preferencesFile = next(i); i++; break;
      case '--locale': out.overrides.presentation.locale = next(i); i++; break;
      case '--aspect-ratio': out.overrides.presentation.aspect_ratio = next(i); i++; break;
      case '--font': out.fontFamilies = out.fontFamilies || []; out.fontFamilies.push(next(i)); i++; break;
      case '--from-json': out.fromJson = next(i); i++; break;
      case '--dir': out.dir = next(i); i++; break;
      case '--out': out.out = next(i); i++; break;
      case '--skill-local': out.skillLocal = true; break;
      case '--force': out.force = true; break;
      case '--dry-run': out.dryRun = true; break;
      case '--help': case '-h': out.help = true; break;
      default: break;
    }
  }
  return out;
}

function hasAnyInput(args) {
  const o = args.overrides;
  const anyOverride =
    Object.values(o.identity).some(Boolean) ||
    Object.values(o.contact).some(Boolean) ||
    Object.values(o.assets).some(Boolean) ||
    Object.values(o.brand).some(Boolean) ||
    Object.keys(o.presentation).length > 0 ||
    Object.values(o.sources).some(Boolean) ||
    args.titles.length > 0 ||
    args.footprintPhotos.length > 0 ||
    !!args.preferencesFile ||
    !!args.fontFamilies;
  return anyOverride || !!args.fromJson;
}

function readJsonInput(fromJson) {
  const text = fromJson === '-' ? fs.readFileSync(0, 'utf-8') : fs.readFileSync(fromJson, 'utf-8');
  return JSON.parse(text);
}

function buildProfile(args) {
  let profile;
  if (args.fromJson) {
    profile = readJsonInput(args.fromJson);
    if (profile && typeof profile === 'object' && 'profile' in profile && typeof profile.profile === 'object') {
      // 允许直接喂 load-profile.js --json 的输出
      profile = profile.profile;
    }
  } else {
    profile = JSON.parse(JSON.stringify(ANONYMOUS_PROFILE));
  }

  const base = fillDefaults(profile);
  const o = args.overrides;
  for (const section of ['identity', 'contact', 'assets', 'brand', 'presentation', 'sources']) {
    for (const [key, value] of Object.entries(o[section])) {
      if (value === undefined) continue;
      base[section][key] = value;
    }
  }
  if (args.titles.length > 0) base.identity.titles = args.titles;
  if (args.footprintPhotos.length > 0) base.assets.footprint_photos = args.footprintPhotos;
  if (args.preferencesFile) base.preferences_file = args.preferencesFile;
  if (args.fontFamilies) base.presentation.font_families = args.fontFamilies;
  return base;
}

function targetPath(args) {
  if (args.out) return path.resolve(args.out);
  if (args.skillLocal) return path.join(SKILL_ROOT, LOCAL_CONFIG_REL);
  return path.join(args.dir ? path.resolve(args.dir) : getUserDir(), 'profile.local.json');
}

function main() {
  const args = parseArgs(process.argv.slice(2));

  if (args.help) {
    console.log(GUIDE);
    return;
  }

  if (!hasAnyInput(args)) {
    // 引导模式：只打印提问清单，不写盘、不扫描。
    console.log(GUIDE);
    process.exit(0);
  }

  let profile;
  try {
    profile = buildProfile(args);
  } catch (err) {
    console.error(`错误: 输入无法解析 — ${err.message}`);
    process.exit(1);
  }

  const { errors, warnings } = validateShape(profile);
  if (errors.length > 0) {
    for (const e of errors) console.error(`错误: ${e}`);
    process.exit(1);
  }

  const outPath = targetPath(args);
  const outDir = path.dirname(outPath);

  if (fs.existsSync(outPath) && !args.force) {
    console.error(`错误: 目标已存在，未覆盖: ${outPath}`);
    console.error('如需覆盖请显式加 --force。');
    process.exit(1);
  }

  // 素材/来源缺项只提示，不阻塞初始化。
  const notes = [];
  for (const entry of collectAssets(profile, outDir)) {
    if (!entry.enabled) continue;
    if (entry.values.length === 0) {
      notes.push(`素材 ${entry.key} 已启用但未配置路径 (受 ${entry.gate} 控制)`);
      continue;
    }
    for (const item of entry.values) {
      if (!item.exists) notes.push(`素材 ${entry.key} 路径不可读: ${item.resolved}`);
    }
  }
  for (const entry of collectSources(profile, outDir)) {
    if (entry.enabled && entry.raw && !entry.exists) {
      notes.push(`来源 sources.${entry.key} 路径不可读: ${entry.resolved}`);
    }
    if (entry.enabled && !entry.raw) {
      notes.push(`来源 sources.${entry.key} 已启用但未配置路径`);
    }
  }
  for (const w of warnings) notes.push(w);

  if (args.dryRun) {
    console.log(JSON.stringify(profile, null, 2));
    console.error(`(dry-run) 未写入: ${outPath}`);
  } else {
    fs.mkdirSync(outDir, { recursive: true });
    fs.writeFileSync(outPath, JSON.stringify(profile, null, 2) + '\n', 'utf-8');
    console.log(`配置已写入: ${outPath}`);
  }

  if (notes.length > 0) {
    console.log('');
    console.log('提示（不影响写入）:');
    for (const n of notes) console.log(`  - ${n}`);
  }
  console.log('');
  console.log('下一步: node check-profile.js' + (args.out || args.skillLocal ? ` --config ${outPath}` : ''));
}

main();
