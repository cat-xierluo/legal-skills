#!/usr/bin/env python3
"""check-readme-coverage.py — 校验 Release 资产在 README 技能表的覆盖完整性

背景：update-readme.py 只能改写已有表行（链接刷新/版本列对齐），不能补行。
新技能上传时若漏维护 README 技能表格行（AGENTS.md 已要求维护），该技能的 zip
进了 Release 但用户在 README 里找不到下载入口——回写机制对此无能为力。
本脚本在发版前后核对：每个 skill zip 资产必须在 README 有表行且有本仓库下载
链接（独立仓库下载行豁免），把"漏行"从静默变成显式拦截。

用法:
  python3 check-readme-coverage.py <owner/repo> [README 路径]
  python3 check-readme-coverage.py --assets-json assets.json <owner/repo> [README 路径]

退出码: 0 覆盖完整; 1 有缺行/缺链接(或参数错误)
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


def fetch_assets(repo: str) -> list[str]:
    owner, name = repo.split("/", 1)
    api = f"https://api.github.com/repos/{owner}/{name}/releases/latest"
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    req = urllib.request.Request(
        api, headers={"Authorization": f"token {token}"} if token else {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return [a["name"] for a in data.get("assets", [])
            if isinstance(a, dict) and str(a.get("name", "")).endswith(".zip")]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--assets-json", type=Path,
                        help="从本地 release JSON 读取 assets（离线模式）")
    parser.add_argument("repo", help="owner/repo")
    parser.add_argument("readme", type=Path, nargs="?", default=Path("README.md"))
    args = parser.parse_args()

    try:
        if args.assets_json:
            data = json.loads(args.assets_json.read_text(encoding="utf-8"))
            assets = [a["name"] for a in data.get("assets", [])
                      if str(a.get("name", "")).endswith(".zip")]
        else:
            assets = fetch_assets(args.repo)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(f"ERROR: 获取 Release 资产失败: {exc}", file=sys.stderr)
        return 1

    skill_ver = {a[:-4].rpartition("-")[0]: a[:-4].rpartition("-")[2] for a in assets}

    if not args.readme.is_file():
        print(f"ERROR: README 不存在: {args.readme}", file=sys.stderr)
        return 1
    readme = args.readme.read_text(encoding="utf-8")

    missing: list[tuple[str, str]] = []
    for skill, ver in sorted(skill_ver.items()):
        idx = readme.find(f'href="skills/{skill}/"')
        seg = readme[idx:idx + 2500].split("</tr>")[0] if idx >= 0 else ""
        if not seg:
            missing.append((skill, f"整行缺失({ver} 已发布但无表行)"))
            continue
        has_link = re.search(
            rf"/releases/(?:latest/download|download/[^/\s]+/)"
            rf"{re.escape(skill)}-[\d.]+\.zip", seg)
        indep = ".skill/releases" in seg or "独立仓库" in seg
        if not has_link and not indep:
            missing.append((skill, "有行但无本仓库下载链接"))

    if missing:
        print(f"❌ {len(missing)}/{len(skill_ver)} 个资产的 README 覆盖不完整:", file=sys.stderr)
        for skill, why in missing:
            print(f"  - {skill}: {why}", file=sys.stderr)
        print("处置: 按 AGENTS.md「README 最近更新区维护」规范补表格行; "
              "新技能上传时必须同步维护 README 技能列表与下载链接", file=sys.stderr)
        return 1

    print(f"✅ 覆盖完整: {len(skill_ver)} 个资产在 README 均有行有链接(独立仓库行豁免)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
