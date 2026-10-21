#!/usr/bin/env python3
"""Skill 改名后的本机软链收敛工具。

场景：skill 目录改名/迁移后（如 multi-agent-orchestration → multi-agent-orca），
本机用户级与项目级 Agent 配置目录里仍残留指向旧路径的符号链接（悬空）。
本工具在有界扫描根内找出这些链接并批量规划/执行修复。

只处理符号链接，不移动任何实体文件；默认 dry-run，--apply 才执行。

用法：
  python3 relink-skill.py --old /path/to/old-skill-dir --new /path/to/new-skill-dir
  python3 relink-skill.py --old ... --new ... --apply --report /tmp/relink-report.json
  python3 relink-skill.py --old ... --new ... --exclude-glob '*/visualizations/*'
  # 项目不在用户级配置目录时，把项目根传进来（浅层查其 .claude/.codex 等子目录）：
  python3 relink-skill.py --old ... --new ... --roots /path/to/project-a --roots /path/to/project-b
  # 三档扫描深度：浅层（默认，毫秒级，查配置根顶层+skills/+commands/）
  #              → --deep（对根完整递归）
  #              → --full-home（整个用户主目录，穷尽兜底，耗时长）
  python3 relink-skill.py --old ... --new ... --full-home
"""
import argparse
import fnmatch
import json
import os
import sys
import time
from datetime import datetime, timezone

# registry 与脚本相对位置（skills/skill-manager/assets/skill-registry.json，本地文件可能不存在）；
# 可用环境变量 SKILL_MANAGER_REGISTRY 覆盖（测试或非标准安装位置）
REGISTRY_PATH = os.environ.get(
    "SKILL_MANAGER_REGISTRY",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "assets", "skill-registry.json"))

# 默认只扫通用的用户级 Agent 配置目录（对任何机器成立）；
# 项目级安装位置因人而异，用 --roots 追加或 --full-home 全盘兜底，不内置猜测。
HARNESS_DIRS = [".claude", ".codex", ".agents", ".zcode", ".openclaw",
                ".workbuddy", ".qoderworkcn", ".codebuddy", ".hermes", ".myagents"]
# 每个配置根内只看这些子目录一层（安装链 99% 挂在这）+ 根顶层（脚本链）
HARNESS_SUBDIRS = ["skills", "commands"]
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".Trash"}

# --full-home 模式追加跳过的目录名：确定不承载 Agent 配置/项目代码的重资源区，
# 跳过以控制全盘耗时；~/Library/Application Support（用户项目常驻处）不跳。
FULL_HOME_SKIP_NAMES = {
    "Caches", "Containers", "Group Containers", "MobileSync", "Metadata",
    "Saved Application State", "WebKit", "Logs", "Developer", "CloudStorage",
    "com.apple.metadata.mdsbackup", "knowledge-csp", "FaceTime", "iCloud",
}
# --full-home 模式按绝对路径跳过的目录（名字太通用不能按名跳）
FULL_HOME_SKIP_PATHS = {
    "~/Library/Photos",
    "~/Pictures/Photos Library.photoslibrary",
    "~/Library/Messages",
    "~/Library/Mail",
    "~/Library/Metadata/MobileMeAccounts",
}


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--old", required=True, help="旧技能目录绝对路径（链接命中前缀）")
    ap.add_argument("--new", required=True, help="新技能目录绝对路径（修复后的指向）")
    ap.add_argument("--roots", action="append", default=[],
                    help="追加扫描根（可多次，如各项目根目录）；路径以 ~ 开头会展开")
    ap.add_argument("--roots-only", action="store_true", help="只用 --roots 提供的根，忽略内置默认根")
    ap.add_argument("--deep", action="store_true",
                    help="对扫描根完整递归（默认只浅层查 skills/commands/根顶层，毫秒级；"
                         "深链只出现在历史快照/归档里，一般无需 --deep）")
    ap.add_argument("--full-home", action="store_true",
                    help="全盘扫描整个用户主目录（穷尽兜底，耗时可能很长；自动跳过 Caches/Containers/iCloud 等重资源区），"
                         "外置卷请另用 --roots /Volumes/xxx 追加")
    ap.add_argument("--exclude-glob", action="append", default=[],
                    help="fnmatch 排除模式（可多次），命中的链接跳过，如 '*/visualizations/*'")
    ap.add_argument("--from-registry", action="store_true",
                    help="不扫描：直接读 skill-registry.json 里登记的安装位置逐个检查（毫秒级；"
                         "registry 无记录时自动回退浅层扫描并提示）")
    ap.add_argument("--register", action="store_true",
                    help="只登记不修复：把扫描到的指向 --new 的活链接写入 registry install_links，"
                         "供下次改名 --from-registry 秒查")
    ap.add_argument("--apply", action="store_true", help="执行修复（默认 dry-run 只打印计划）")
    ap.add_argument("--report", help="把扫描与修复结果写为 JSON 报告（追溯用）")
    ap.add_argument("--quiet", action="store_true", help="不打印逐条进度")
    return ap.parse_args()


def expand(path):
    return os.path.abspath(os.path.expanduser(path))


def load_registry():
    try:
        with open(REGISTRY_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_registry(registry):
    os.makedirs(os.path.dirname(expand(REGISTRY_PATH)), exist_ok=True)
    with open(expand(REGISTRY_PATH), "w") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)


def registry_link_paths(registry, *roots):
    """收集 source 指向任一 root 的技能条目里登记过的安装位置。"""
    paths = []
    for rec in registry.values():
        if not isinstance(rec, dict):
            continue
        src = rec.get("source") or ""
        if any(src == r or src.startswith(r + os.sep) for r in roots if r):
            for item in rec.get("install_links") or []:
                p = item.get("path") if isinstance(item, dict) else item
                if p:
                    paths.append(p)
    return paths


def register_links(registry, new, links, note="relink"):
    """把链接位置登记到新技能名条目的 install_links（幂等，保留原登记时间）。"""
    name = os.path.basename(new.rstrip("/"))
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    rec = registry.get(name)
    if not isinstance(rec, dict):
        rec = {"name": name, "source": new, "install_type": "local",
               "installed_at": now, "last_updated": now}
        registry[name] = rec
    else:
        rec["source"] = new
    known = {i.get("path") for i in rec.get("install_links", []) if isinstance(i, dict)}
    for link, target in links:
        if link not in known:
            rec.setdefault("install_links", []).append(
                {"path": link, "target": target, "recorded_at": now, "via": note})
    rec["last_updated"] = now


def resolve_target(link_path, target):
    """相对链接按链接所在目录解析为绝对路径。"""
    if target.startswith("/"):
        return os.path.normpath(target)
    return os.path.normpath(os.path.join(os.path.dirname(link_path), target))


def iter_shallow(harness_roots):
    """浅层模式：只看每个配置根的顶层 + skills/ + commands/ 一层。

    真实消费者链接（安装链、脚本链）几乎全挂在这几层；更深的链接
    属于历史快照/归档，默认不碰。毫秒级完成。
    """
    for root in harness_roots:
        root = expand(root)
        try:
            for entry in os.scandir(root):
                if entry.is_symlink():
                    yield entry.path
        except OSError:
            continue
        for sub in HARNESS_SUBDIRS:
            d = os.path.join(root, sub)
            try:
                for entry in os.scandir(d):
                    if entry.is_symlink():
                        yield entry.path
                    # 分类子目录一层（如 ~/.hermes/skills/personal/<skill>）
                    elif entry.is_dir(follow_symlinks=False):
                        try:
                            for inner in os.scandir(entry.path):
                                if inner.is_symlink():
                                    yield inner.path
                        except OSError:
                            continue
            except OSError:
                continue


def default_harness_roots(extra_roots):
    """默认根：8 类 harness 的用户级目录 + 调用方传入的根。"""
    home = expand("~")
    roots = [os.path.join(home, h) for h in HARNESS_DIRS]
    roots += [expand(r) for r in extra_roots]
    return roots


def resolve_harness_roots(raw_roots, discover_children=True):
    """浅层模式的根解析：basename 是 harness 名（如 .claude）的当配置根直用；
    否则视为项目根，展开为其 8 个 harness 子目录。

    discover_children=True 时再向下发现一层子项目（项目集合目录场景：
    如把 ~/code 传进来，其下每个子项目的 .claude/.codex 都会被检查）。
    """
    out = []
    for r in raw_roots:
        r = expand(r)
        if os.path.basename(r) in HARNESS_DIRS:
            out.append(r)
            continue
        out += [os.path.join(r, h) for h in HARNESS_DIRS]
        if not discover_children:
            continue
        try:
            for entry in os.scandir(r):
                if entry.is_dir(follow_symlinks=False) and entry.name not in SKIP_DIRS:
                    out += [os.path.join(entry.path, h) for h in HARNESS_DIRS]
        except OSError:
            continue
    return out


def iter_symlinks(roots, quiet, skip_names=None):
    """基于 os.scandir 的遍历：d_type 免额外 lstat，全盘扫描性能关键。

    指向目录的软链只 yield 不深入（等价 walk followlinks=False），
    否则 skills 安装链这类目录级链接会漏扫或成环。
    """
    skip_names = SKIP_DIRS if skip_names is None else skip_names
    skip_paths = {expand(p) for p in FULL_HOME_SKIP_PATHS}

    def walk_dir(dirpath):
        try:
            with os.scandir(dirpath) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            yield entry.path
                        elif entry.is_dir(follow_symlinks=False):
                            if entry.name not in skip_names and entry.path not in skip_paths:
                                yield from walk_dir(entry.path)
                    except OSError:
                        continue
        except OSError:
            return

    for root in roots:
        root = expand(root)
        if not os.path.isdir(root):
            if not quiet:
                print(f"  跳过不存在根: {root}", file=sys.stderr)
            continue
        yield from walk_dir(root)


def classify(link_path, target, old, new):
    """对一条命中链接给出修复动作。

    - basename 等于旧技能名（skills 安装链）：
        目标父目录已有新名链接/目录 → remove_old；否则 → remove_old + create_new
    - basename 不同（如 night-watch.sh、指向 config/references 子路径）：
        链接名保持，target 中 old 前缀替换为 new（repoint）
    """
    base = os.path.basename(link_path.rstrip("/"))
    old_base = os.path.basename(old.rstrip("/"))
    new_base = os.path.basename(new.rstrip("/"))
    # 先解析到绝对再替换前缀，再按原链接形态输出：
    # 绝对链保持绝对；相对链转回相对，避免把本机绝对路径写进仓库内相对链接。
    resolved_old = resolve_target(link_path, target)
    resolved_new = resolved_old.replace(old, new, 1)
    if target.startswith("/"):
        new_target = os.path.normpath(resolved_new)
    else:
        new_target = os.path.relpath(resolved_new, os.path.dirname(link_path))
    if base == old_base:
        sibling = os.path.join(os.path.dirname(link_path), new_base)
        if os.path.lexists(sibling):
            return {"action": "remove_old", "link": link_path, "old_target": target,
                    "note": f"已有 {new_base}，只删旧链"}
        return {"action": "replace_named", "link": link_path, "old_target": target,
                "new_link": sibling, "new_target": new_target, "note": "删旧链+以新名建新链"}
    return {"action": "repoint", "link": link_path, "old_target": target,
            "new_target": new_target, "note": "链接名不变，重指新路径"}


def excluded(path, patterns):
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)


def main():
    args = parse_args()
    old = expand(args.old)
    new = expand(args.new)
    if not os.path.isdir(new):
        print(f"错误: 新路径不存在: {new}", file=sys.stderr)
        return 2
    # --register 允许 old==new（改名已完成、纯补登记：命中前缀即当前路径）
    if old == new and not args.register:
        print("错误: --old 与 --new 相同（仅 --register 补登记时允许）", file=sys.stderr)
        return 2

    # 链接来源四类：--from-registry 登记表（最快）→ 浅层（默认）→ --deep 递归 → --full-home 全盘
    registry = load_registry()
    if args.from_registry:
        known_paths = registry_link_paths(registry, old, new)
        if known_paths:
            link_iter = (p for p in known_paths if os.path.islink(p))
            roots = [f"registry({len(known_paths)} 处)"]
        else:
            if not args.quiet:
                print("registry 无该技能的 install_links 登记，回退浅层扫描", file=sys.stderr)
            raw = ([] if args.roots_only else [os.path.join(expand("~"), h) for h in HARNESS_DIRS]) + args.roots
            roots = resolve_harness_roots(raw)
            link_iter = iter_shallow(roots)
    elif args.full_home:
        home = expand("~")
        roots = [home] + [expand(r) for r in args.roots]
        link_iter = iter_symlinks(roots, args.quiet, SKIP_DIRS | FULL_HOME_SKIP_NAMES)
    elif args.deep:
        if args.roots_only:
            roots = [expand(r) for r in args.roots]
        else:
            roots = default_harness_roots(args.roots)
        link_iter = iter_symlinks(roots, args.quiet)
    else:
        raw = ([] if args.roots_only else [os.path.join(expand("~"), h) for h in HARNESS_DIRS]) + args.roots
        roots = resolve_harness_roots(raw)
        link_iter = iter_shallow(roots)
    # 旧目录已删除是常态（先退役再收敛）；扫描不要求它存在

    findings, skipped = [], []
    t0 = time.time()
    for link in link_iter:
        try:
            target = os.readlink(link)
        except OSError:
            continue
        resolved = resolve_target(link, target)
        if old == resolved or resolved.startswith(old + os.sep) or target.startswith(old + os.sep) or target == old:
            if excluded(link, args.exclude_glob):
                skipped.append({"link": link, "target": target, "reason": "exclude-glob"})
                continue
            item = classify(link, target, old, new)
            item["dangling"] = not os.path.exists(link)
            findings.append(item)

    results = []
    for item in findings:
        act = item["action"]
        if args.register and not args.apply:
            status = "REGISTER"  # 纯登记模式；--apply --register 组合仍执行修复（尾部统一登记）
        elif not args.apply:
            status = "PLAN"
        elif act == "remove_old":
            os.remove(item["link"]); status = "REMOVED"
        elif act == "replace_named":
            os.remove(item["link"])
            os.symlink(item["new_target"], item["new_link"]); status = "REPLACED"
        else:  # repoint
            os.remove(item["link"])
            os.symlink(item["new_target"], item["link"]); status = "REPOINTED"
        item["result"] = status
        results.append(item)
        if not args.quiet:
            mark = "悬空" if item["dangling"] else "活"
            extra = item.get("new_link") or item.get("new_target") or ""
            print(f"[{status}] {mark} {act} {item['link']} -> {extra}  ({item['note']})")

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"\n{mode}: 命中 {len(findings)} 条（悬空 {sum(1 for i in findings if i['dangling'])}），"
          f"排除 {len(skipped)} 条，根 {len(roots)} 个，耗时 {time.time()-t0:.1f}s")

    # --register 或 --apply 后：把链接位置登记进 registry，下次改名可 --from-registry 直接查表
    if args.register or args.apply:
        to_register = []
        for item in findings:
            # 登记的是位置：apply 后取新链接，register/预登记取原链接
            link = item.get("new_link") if (args.apply and item.get("new_link")) else item["link"]
            target = item.get("new_target") or item["old_target"]
            to_register.append((link, target))
        if to_register:
            register_links(registry, new, to_register,
                           note="relink-apply" if args.apply else "register")
            save_registry(registry)
            print(f"registry 登记: {len(to_register)} 处链接位置 → install_links（下次 --from-registry 直接查表）")
    if args.report:
        with open(args.report, "w") as f:
            json.dump({"old": old, "new": new, "mode": mode, "roots": roots,
                       "findings": findings, "skipped": skipped}, f, ensure_ascii=False, indent=2)
        print(f"报告: {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
