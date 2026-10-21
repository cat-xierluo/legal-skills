#!/usr/bin/env node
/**
 * check-profile.js - 校验 slides 本地配置
 *
 * 检查项：
 *   - 配置来源与解析顺序命中结果
 *   - 结构/schema_version/枚举与类型
 *   - 已启用（show_* = true）的素材与来源路径是否可读
 *   - 未启用项确认不会被读取
 *
 * 只输出字段名、开关与路径状态，不打印姓名、微信、简介等资料值。
 * 存在错误时退出码非零。
 *
 * USAGE:
 *   node check-profile.js
 *   node check-profile.js --config ~/.config/slides/profile.local.json
 */

'use strict';

const {
  loadProfile,
  collectAssets,
  collectSources,
  getField,
  ASSET_REQUIRED
} = require('./load-profile');

function parseArgs(argv) {
  const out = { configPath: null, cwd: null };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--config') out.configPath = argv[++i];
    else if (argv[i] === '--cwd') out.cwd = argv[++i];
  }
  return out;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const loaded = loadProfile({ configPath: args.configPath, cwd: args.cwd });
  const { profile, source, configPath, baseDir, warnings } = loaded;
  const errors = [...loaded.errors];
  const notes = [...warnings];

  const sourceLabels = {
    explicit: '显式指定',
    project: '课件项目配置 (.slides/profile.json)',
    'skill-local': '技能目录本地配置 (config/profile.local.json)',
    user: '用户数据目录 (~/.config/slides/profile.local.json)',
    anonymous: '匿名默认值（未找到任何配置）'
  };

  console.log('── slides 配置检查 ──');
  console.log(`来源: ${sourceLabels[source] || source}`);
  if (configPath) console.log(`文件: ${configPath}`);
  console.log(`路径基准: ${baseDir}`);

  if (!profile) {
    console.log('');
    console.log('错误:');
    for (const e of errors) console.log(`  - ${e}`);
    process.exit(1);
  }

  console.log(`schema_version: ${profile.schema_version}`);

  const presentation = profile.presentation || {};
  console.log('');
  console.log('展示开关:');
  for (const key of [
    'show_profile',
    'show_footprints',
    'show_wechat_qr',
    'show_public_account_qr'
  ]) {
    console.log(`  ${key} = ${presentation[key] === true}`);
  }
  console.log(`  intro_pages = ${presentation.intro_pages}`);
  console.log(`  closing_mode = ${presentation.closing_mode}`);

  console.log('');
  console.log('身份/联系字段（只报是否已填）:');
  for (const field of [
    'identity.name',
    'identity.titles',
    'identity.organization',
    'identity.bio',
    'contact.wechat',
    'contact.email',
    'contact.website'
  ]) {
    const value = getField(profile, field);
    const filled = Array.isArray(value) ? value.length > 0 : !!value;
    console.log(`  ${field}: ${filled ? '已填' : '未填'}`);
  }

  console.log('');
  console.log('素材:');
  for (const entry of collectAssets(profile, baseDir)) {
    if (!entry.enabled) {
      console.log(`  ${entry.key}: 关闭（不读取，受 ${entry.gate} 控制）`);
      continue;
    }
    if (entry.values.length === 0) {
      if (ASSET_REQUIRED[entry.key]) {
        console.log(`  ${entry.key}: 已启用但未配置路径（受 ${entry.gate} 控制）`);
        errors.push(`素材 ${entry.key} 已启用但未配置路径`);
      } else {
        console.log(`  ${entry.key}: 已启用未配置（可选，生成时省略并重排）`);
        notes.push(`素材 ${entry.key} 已启用但未配置路径（可选）`);
      }
      continue;
    }
    for (const item of entry.values) {
      if (item.exists) {
        console.log(`  ${entry.key}: OK ${item.resolved}`);
      } else {
        console.log(`  ${entry.key}: 缺失 ${item.resolved}`);
        errors.push(`素材 ${entry.key} 路径不可读: ${item.resolved}`);
      }
    }
  }

  console.log('');
  console.log('权威来源:');
  for (const entry of collectSources(profile, baseDir)) {
    if (!entry.enabled) {
      console.log(`  sources.${entry.key}: 关闭（不读取，受 ${entry.gate} 控制）`);
      continue;
    }
    if (!entry.raw) {
      console.log(`  sources.${entry.key}: 已启用但未配置路径`);
      notes.push(`来源 sources.${entry.key} 已启用但未配置路径`);
      continue;
    }
    if (entry.exists) {
      console.log(`  sources.${entry.key}: OK ${entry.resolved}`);
    } else {
      console.log(`  sources.${entry.key}: 缺失 ${entry.resolved}`);
      errors.push(`来源 sources.${entry.key} 路径不可读: ${entry.resolved}`);
    }
  }

  if (profile.preferences_file) {
    const fs = require('fs');
    const path = require('path');
    const resolved = path.isAbsolute(profile.preferences_file)
      ? profile.preferences_file
      : path.resolve(baseDir, profile.preferences_file);
    if (fs.existsSync(resolved)) {
      console.log('');
      console.log(`偏好文件: OK ${resolved}`);
    } else {
      console.log('');
      console.log(`偏好文件: 缺失 ${resolved}`);
      errors.push(`preferences_file 路径不可读: ${resolved}`);
    }
  }

  if (notes.length > 0) {
    console.log('');
    console.log('提示:');
    for (const n of notes) console.log(`  - ${n}`);
  }

  if (errors.length > 0) {
    console.log('');
    console.log('错误:');
    for (const e of errors) console.log(`  - ${e}`);
    process.exit(1);
  }

  console.log('');
  console.log('检查通过。');
}

main();
