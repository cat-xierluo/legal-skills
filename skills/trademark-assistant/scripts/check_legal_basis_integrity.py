#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
法源数据完整性自检（trademark-assistant 维护工具）
==================================================
检查 skill 自带的尼斯分类 NCL13-2026 与《商标审查审理指南》的**结构**完整性，
用于发现"材料转换 / 批量迁移"过程中的遗漏（例如 class-09 眼镜残留那类问题）。

注意：本脚本只做**结构级**检查（文件齐备、类号/章号一致、迁移记录段是否存在、
异常小文件、索引引用）。**内容级**的 transfer/delete/change 复核仍需对照官方
2026 变更文本单独进行——结构完整不代表内容迁移无误。

用法：
    python3 scripts/check_legal_basis_integrity.py

全部只读，不修改任何文件。退出码：0=无严重问题，1=发现严重问题。
"""

import re
import statistics
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
REF = SKILL_DIR / "references"
NICE = REF / "nice-classification-v13-2026"
GUIDE = REF / "trademark-examination-and-adjudication-guidelines"

SEVERE = "严重"
WATCH = "关注"
problems = []


def flag(level, msg):
    problems.append((level, msg))


# ==================== 尼斯分类 ====================
print("=" * 64)
print("尼斯分类 NCL13-2026 完整性检查")
print("=" * 64)

nice_files = {}
if NICE.exists():
    for p in sorted(NICE.glob("class-*.md")):
        m = re.search(r"class-(\d{2})\.md", p.name)
        if m:
            nice_files[int(m.group(1))] = p

expected_nice = set(range(1, 46))
have_nice = set(nice_files)

missing_nice = sorted(expected_nice - have_nice)
extra_nice = sorted(have_nice - expected_nice)
if missing_nice:
    flag(SEVERE, f"尼斯分类缺失类文件: {[f'{i:02d}' for i in missing_nice]}")
else:
    print(f"✓ 45 类文件齐备")
if extra_nice:
    flag(SEVERE, f"尼斯分类多余类文件: {[f'{i:02d}' for i in extra_nice]}")

title_mismatch = []
no_summary = []
no_fe = []
sizes = {}

for n, p in sorted(nice_files.items()):
    txt = p.read_text(encoding="utf-8")
    sizes[n] = len(txt)
    # 类号标题：## 第 09 类 / ## 第09类 / ## 第 9 类
    if not re.search(rf"##\s*第\s*0?{n}\s*类", txt):
        title_mismatch.append(n)
    # 迁移记录段（关键：class-09 漏删眼镜即与此相关）
    if "NCL13-2026 修订摘要" not in txt:
        no_summary.append(n)
    # 结构段
    if "非规范商品项" not in txt:
        no_fe.append(n)

if title_mismatch:
    flag(SEVERE, f"类号标题不匹配（文件名 vs '## 第X类'）: {title_mismatch}")
else:
    print("✓ 所有类文件标题类号与文件名一致")

print(f"\n缺失'NCL13-2026 修订摘要'段的类（{len(no_summary)} 个）:")
if no_summary:
    print(f"  ⚠ {no_summary}")
    flag(WATCH, f"{len(no_summary)} 个类缺'NCL13-2026 修订摘要'段 → 重点对照官方变更核对: {no_summary}")
else:
    print("  无，所有类都有修订摘要段")

print(f"\n缺失'非规范商品项'段的类（{len(no_fe)} 个）: {no_fe or '无'}")
if no_fe:
    flag(WATCH, f"{len(no_fe)} 个类缺'非规范商品项'段（可能转换遗漏）: {no_fe}")

if sizes:
    avg = statistics.mean(sizes.values())
    threshold = avg * 0.4
    small = sorted(n for n, s in sizes.items() if s < threshold)
    print(f"\n文件大小: 平均 {int(avg)} 字符，报警阈值 {int(threshold)}；范围 {min(sizes.values())}–{max(sizes.values())}")
    if small:
        flag(WATCH, f"异常小类文件（疑似截断/转换遗漏）: {[(n, sizes[n]) for n in small]}")
        for n in small:
            print(f"  ⚠ class-{n:02d}.md: {sizes[n]} 字符")
    else:
        print("  无异常小文件")

# 索引
nice_idx = NICE / "nice-classification-v13-2026-index.md"
if nice_idx.exists():
    idx_txt = nice_idx.read_text(encoding="utf-8")
    idx_refs = set(int(m) for m in re.findall(r"class-(\d{2})\.md", idx_txt))
    idx_missing = sorted(expected_nice - idx_refs)
    if idx_missing:
        flag(SEVERE, f"尼斯索引未引用的类: {idx_missing}")
    else:
        print("✓ 尼斯索引引用全部 45 类")
else:
    flag(SEVERE, "尼斯索引文件缺失")


# ==================== 审查审理指南 ====================
print("\n" + "=" * 64)
print("商标审查审理指南 完整性检查")
print("=" * 64)

guide_files = {}
if GUIDE.exists():
    for p in sorted(GUIDE.glob("chapter-*.md")):
        m = re.search(r"chapter-(\d{2})\.md", p.name)
        if m:
            guide_files[int(m.group(1))] = p

have_g = sorted(guide_files)
print(f"chapter 文件: {[f'{i:02d}' for i in have_g]}")
print(f"章数: {len(have_g)}")

if have_g:
    g_min, g_max = have_g[0], have_g[-1]
    full_range = set(range(g_min, g_max + 1))
    missing_g = sorted(full_range - set(have_g))
    if missing_g:
        flag(SEVERE, f"审查指南章号不连续，缺失: {missing_g}")
    else:
        print(f"✓ 章号连续（{g_min:02d}–{g_max:02d}）")

guide_idx = GUIDE / "trademark-examination-and-adjudication-guidelines-index.md"
if guide_idx.exists():
    print("✓ 审查指南索引存在")
else:
    flag(SEVERE, "审查指南索引文件缺失")


# ==================== 总结 ====================
print("\n" + "=" * 64)
print("检查总结")
print("=" * 64)

severe = [m for l, m in problems if l == SEVERE]
watch = [m for l, m in problems if l == WATCH]

print(f"\n🔴 严重问题: {len(severe)}")
for m in severe:
    print(f"   {m}")
print(f"\n🟡 关注项: {len(watch)}")
for m in watch:
    print(f"   {m}")

if not problems:
    print("\n✅ 结构完整性检查通过：未发现整类/整章缺失、类号错位或索引断裂。")
    print("   注：结构完整 ≠ 内容迁移正确。内容级 transfer/delete/change 复核仍需对照官方 2026 变更单独做。")

sys.exit(1 if severe else 0)
