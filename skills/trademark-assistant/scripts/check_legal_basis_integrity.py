#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
法源数据完整性自检（trademark-assistant 维护工具）
==================================================
检查 skill 自带的尼斯分类 NCL13-2026 与《商标审查审理指南》的结构完整性，
并校验已经确认过的关键迁移不变量，用于发现材料转换或批量迁移遗漏。

注意：关键迁移不变量仅覆盖历史上已发现的回归点，不等于完成 NCL13-2026
全部 transfer/delete/change 的内容级复核。

用法：
    python3 scripts/check_legal_basis_integrity.py
    python3 scripts/check_legal_basis_integrity.py --candidate-root /path/to/trademark-assistant

全部只读，不修改任何文件。退出码：0=无严重问题，1=发现严重问题。
"""

import argparse
import re
import statistics
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description="检查商标助手法源数据的结构和关键迁移不变量")
parser.add_argument(
    "--candidate-root",
    type=Path,
    default=Path(__file__).resolve().parent.parent,
    help="待检查的 trademark-assistant 技能根目录",
)
args = parser.parse_args()

SKILL_DIR = args.candidate_root.resolve()
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


# ==================== 已知迁移回归 ====================
print("\n" + "=" * 64)
print("NCL13-2026 已知迁移回归检查")
print("=" * 64)


def section_before_groups(text):
    """提取类文件第一个 ### 类似群标题之前的类别标题和注释。"""
    return text.split("\n### ", 1)[0]


def split_notes(text):
    """拆分“尤其包括/尤其不包括”，格式异常时返回空串并报严重问题。"""
    if "本类尤其包括：" not in text or "本类尤其不包括：" not in text:
        return None, None
    included = text.split("本类尤其包括：", 1)[1].split("本类尤其不包括：", 1)[0]
    excluded = text.split("本类尤其不包括：", 1)[1].split("\n## ", 1)[0]
    return included, excluded


known_checks = 0
class09 = nice_files.get(9)
if class09:
    text09 = class09.read_text(encoding="utf-8")
    included09, excluded09 = split_notes(section_before_groups(text09))
    if included09 is None:
        flag(SEVERE, "class-09 注释缺少“本类尤其包括/不包括”结构")
    else:
        known_checks += 3
        if "消防车" in included09:
            flag(SEVERE, "class-09“本类尤其包括”仍包含消防车（NCL13 应移入第12类）")
        if "应急和救援用运载工具" not in excluded09 or "消防车" not in excluded09:
            flag(SEVERE, "class-09“本类尤其不包括”缺少应急和救援用运载工具/消防车（第12类）")
        if "眼镜，隐形眼镜" in included09 or "眼镜套" in included09:
            flag(SEVERE, "class-09“本类尤其包括”仍包含已移入第10类的普通眼镜项目")

class12 = nice_files.get(12)
if class12:
    text12 = class12.read_text(encoding="utf-8")
    _, excluded12 = split_notes(section_before_groups(text12))
    known_checks += 2
    if excluded12 is None:
        flag(SEVERE, "class-12 注释缺少“本类尤其包括/不包括”结构")
    elif "消防车（第九类）" in excluded12:
        flag(SEVERE, "class-12“本类尤其不包括”仍错误保留消防车（第九类）")
    if not re.search(r"消防车\s+120352", text12):
        flag(SEVERE, "class-12 缺少消防车 120352 项")

class03 = nice_files.get(3)
if class03:
    text03 = class03.read_text(encoding="utf-8")
    heading03 = text03.split("【注释】", 1)[0]
    known_checks += 2
    if "；香水；" not in heading03 or "香料，香精油" in heading03:
        flag(SEVERE, "class-03 类标题内容未同步为包含“香水”且删除旧“香料，香精油”")
    if "防腐剂，香精油和抗氧化剂" not in section_before_groups(text03):
        flag(SEVERE, "class-03 注释缺少 NCL13 新增的“香精油”")

print(f"✓ 已执行 {known_checks} 项关键迁移不变量检查")


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

# 转换后的指南和法规材料可能保留本地图片链接，但压缩包未携带对应资产。
asset_docs = list(guide_files.values()) + list((REF / "laws-regulations").glob("*.md"))
missing_images = []
for doc in asset_docs:
    text = doc.read_text(encoding="utf-8")
    for target in re.findall(r"!\[[^]]*\]\(([^)]+)\)", text):
        if "://" in target or target.startswith("data:"):
            continue
        if not (doc.parent / target).exists():
            missing_images.append((doc.relative_to(REF), target))

if missing_images:
    affected = sorted({str(doc) for doc, _ in missing_images})
    print(f"ℹ 原始材料未附本地图片资产: {len(missing_images)} 个引用 / {len(affected)} 份文件（已知来源限制，不计入问题）")
else:
    print("✓ 审查指南与法规材料的本地图片引用均可达")


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
    print("\n✅ 完整性检查通过：未发现结构缺失或已知迁移回归。")
    print("   注：已知迁移不变量通过 ≠ 全量内容迁移已经核验。")

sys.exit(1 if severe else 0)
